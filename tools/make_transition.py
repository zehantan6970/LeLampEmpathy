# -*- coding: utf-8 -*-
"""Transition segment generator (contract v1.2 §transition, QC review R6).

Given two episodes (prev -> nxt), produce a rate-limited blend segment that
carries the lamp from the END pose of prev to the START pose of nxt, plus an
LED crossfade spec. No forced return-to-home (a home swing reads as an
"emotion reset" and breaks empathic continuity).

Rules (frozen in docs/qc_review_v3_analysis.md, 2026-10-03):
  duration = max(t_min, dq_max / rate)
    normal targets: rate = 1.0 rad/s, t_min = 0.8 s
    urgent targets (fear/angry): rate = 2.2 rad/s, t_min = 0.4 s
  easing: cosine (zero end velocities)
  LED: 0.5 s linear crossfade (rgbw + intensity), pattern switches at midpoint

CLI:
  python tools/make_transition.py EPISODES_JSONL PREV_ID NEXT_ID [--out seg.json]
  python tools/make_transition.py EPISODES_JSONL --seq id1,id2,id3 [--out seq.json]
  python tools/make_transition.py EPISODES_JSONL --seq ... --from-frac 0.8 --to-frac 0.15

--from-frac/--to-frac (playlist QC demo mode): dataset episodes lead in from
and back out to the ZERO pose, so end-to-start transitions would be trivial.
With fractions set, the blend runs from prev's expressive keypose (at
from-frac of its duration) into nxt's keypose entry (at to-frac), and the
playlist carries per-episode play windows so the viewer stays continuous.
Pure stdlib + numpy-free math (project env note: no BLAS calls).
"""
import argparse
import json
import math

URGENT = {"fear", "angry"}
RATE_NORMAL, TMIN_NORMAL = 1.0, 0.8
RATE_URGENT, TMIN_URGENT = 2.2, 0.4
CROSSFADE_S = 0.5
HZ = 50  # control-rate output, runtime can downsample


def load_episodes(path):
    with open(path, encoding="utf-8") as f:
        return {json.loads(l)["episode_id"]: json.loads(l)
                for l in f if l.strip()}


def _q_at(traj, t):
    q, hz = traj["q"], traj.get("hz", 10)
    x = min(max(t * hz, 0.0), len(q) - 1)
    i, f = int(math.floor(x)), x - math.floor(x)
    a, b = q[i], q[min(i + 1, len(q) - 1)]
    return [av + (bv - av) * f for av, bv in zip(a, b)]


def make_transition(prev, nxt, hz=HZ, from_frac=None, to_frac=None):
    tr_p, tr_n = prev["response"]["trajectory"], nxt["response"]["trajectory"]
    dur_p = tr_p.get("duration_s", 1.0)
    q0 = _q_at(tr_p, dur_p if from_frac is None else from_frac * dur_p)
    q1 = _q_at(tr_n, 0.0 if to_frac is None else to_frac * tr_n.get("duration_s", 1.0))
    dq_max = max(abs(a - b) for a, b in zip(q0, q1))
    urgent = nxt.get("human_emotion") in URGENT
    rate = RATE_URGENT if urgent else RATE_NORMAL
    tmin = TMIN_URGENT if urgent else TMIN_NORMAL
    dur = max(tmin, dq_max / rate)
    n = max(2, int(round(dur * hz)) + 1)
    qs = []
    for k in range(n):
        u = k / (n - 1)
        e = 0.5 - 0.5 * math.cos(math.pi * u)     # cosine ease, v(0)=v(1)=0
        qs.append([round(a + (b - a) * e, 4) for a, b in zip(q0, q1)])
    # verify rate budget
    vmax = max(abs(qs[k + 1][j] - qs[k][j]) * hz
               for k in range(n - 1) for j in range(5))
    return {
        "type": "transition",
        "from_episode": prev["episode_id"],
        "to_episode": nxt["episode_id"],
        "to_emotion": nxt.get("human_emotion"),
        "urgent": urgent,
        "hz": hz,
        "duration_s": round(dur, 3),
        "q": qs,
        "led_crossfade": {
            "duration_s": CROSSFADE_S,
            "from": prev["response"].get("led"),
            "to": nxt["response"].get("led"),
            "note": "linear rgbw+intensity lerp; pattern switches at midpoint",
        },
        "quality": {"dq_max_rad": round(dq_max, 4),
                    "rate_budget_rad_s": rate,
                    "vmax_rad_s": round(vmax, 3),
                    "vmax_ok": vmax <= rate + 1e-6},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jsonl")
    ap.add_argument("prev", nargs="?")
    ap.add_argument("next", nargs="?")
    ap.add_argument("--seq", help="comma-separated episode ids; emits a playlist")
    ap.add_argument("--from-frac", type=float, default=None,
                    help="blend starts at this fraction of prev duration")
    ap.add_argument("--to-frac", type=float, default=None,
                    help="blend ends at this fraction of next duration")
    ap.add_argument("--out")
    args = ap.parse_args()
    eps = load_episodes(args.jsonl)

    if args.seq:
        ids = [s.strip() for s in args.seq.split(",") if s.strip()]
        segs = [make_transition(eps[a], eps[b],
                                from_frac=args.from_frac, to_frac=args.to_frac)
                for a, b in zip(ids, ids[1:])]
        out = {"type": "playlist", "episodes": ids, "transitions": segs}
        if args.from_frac is not None or args.to_frac is not None:
            ff = 0.8 if args.from_frac is None else args.from_frac
            tf = 0.15 if args.to_frac is None else args.to_frac
            windows = {}
            for k, eid in enumerate(ids):
                dur = eps[eid]["response"]["trajectory"].get("duration_s", 1.0)
                t0 = 0.0 if k == 0 else round(tf * dur, 3)
                t1 = round(dur, 3) if k == len(ids) - 1 else round(ff * dur, 3)
                windows[eid] = [t0, t1]
            out["windows"] = windows
            out["note"] = ("play each episode inside its window; transitions "
                           "blend keypose->keypose (dataset episodes lead in/out "
                           "to ZERO pose, end-to-start blends would be trivial)")
    else:
        if not (args.prev and args.next):
            ap.error("need PREV NEXT or --seq")
        out = make_transition(eps[args.prev], eps[args.next])

    txt = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(txt)
        print("written ->", args.out)
    else:
        print(txt)
    if args.seq or args.prev:
        segs = out["transitions"] if args.seq else [out]
        for s in segs:
            q = s["quality"]
            print(f"  {s['from_episode']} -> {s['to_episode']}: "
                  f"dur={s['duration_s']}s dq_max={q['dq_max_rad']}rad "
                  f"vmax={q['vmax_rad_s']}rad/s ok={q['vmax_ok']} "
                  f"urgent={s['urgent']}")


if __name__ == "__main__":
    main()
