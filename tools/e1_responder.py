# -*- coding: utf-8 -*-
"""E1.2 响应引擎：情绪状态 → episodes_v3.1 检索（V/A 最近邻+轮换）→ live episode。

契约：mapping_contract v1.2 §8（过渡 cosine blend）、§3.1（速度预算）。
live payload 结构：
  {"seq": int, "ts": float, "emotion_state": {...},
   "transition": {...}|null,          # 与上一响应的 §8 过渡段
   "episode": {...},                  # 完整 episode（轨迹/LED/caption）
   "audio_url": str|null}             # E1.4 填入

自测：.venv/Scripts/python.exe tools/e1_responder.py --demo --save qc/e1_responder_demo.jsonl
"""
import argparse
import itertools
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_transition import make_transition  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EPISODES = os.path.join(ROOT, "data", "episodes", "episodes_v3.jsonl")
EMOTIONS = ["joy", "sad", "angry", "fear", "love", "surprise", "neutral"]


class EpisodeIndex:
    """按情绪分组 + V/A 归一化到 [0,1]（数据集 min-max，与 qwen-vl 输出同域）。"""

    def __init__(self, path=EPISODES):
        self.by_emo = {e: [] for e in EMOTIONS}
        eps = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    eps.append(json.loads(line))
        vs = [e["annotation"]["valence"] for e in eps]
        as_ = [e["annotation"]["arousal"] for e in eps]
        v0, v1 = min(vs), max(vs)
        a0, a1 = min(as_), max(as_)
        for e in eps:
            ann = e["annotation"]
            e["_v"] = (ann["valence"] - v0) / (v1 - v0 + 1e-9)
            e["_a"] = (ann["arousal"] - a0) / (a1 - a0 + 1e-9)
            emo = e.get("human_emotion", "neutral")
            if emo in self.by_emo:
                self.by_emo[emo].append(e)
        self.counts = {k: len(v) for k, v in self.by_emo.items()}


class Responder:
    def __init__(self, index=None):
        self.idx = index or EpisodeIndex()
        self._rr = {e: itertools.count() for e in EMOTIONS}  # 轮换游标
        self._last_id = {e: None for e in EMOTIONS}
        self._prev_payload_ep = None   # 上一个实际下发的 episode（过渡起点）
        self._seq = 0

    def select(self, emotion, valence=0.5, arousal=0.5, top_k=5):
        """同类候选 → V/A 最近 top_k → 轮换取 1（避开上次同条）。"""
        emo = emotion if emotion in EMOTIONS else "neutral"
        pool = self.idx.by_emo[emo] or self.idx.by_emo["neutral"]
        ranked = sorted(pool, key=lambda e: (e["_v"] - valence) ** 2
                        + (e["_a"] - arousal) ** 2)[:top_k]
        for _ in range(len(ranked) + 1):
            pick = ranked[next(self._rr[emo]) % len(ranked)]
            if pick["episode_id"] != self._last_id[emo]:
                self._last_id[emo] = pick["episode_id"]
                return pick
        return ranked[0]

    def respond(self, emotion_state):
        """emotion_state = e1_perception 的输出 dict → live payload。"""
        self._seq += 1
        ep = self.select(emotion_state.get("filtered_emotion",
                                           emotion_state.get("emotion", "neutral")),
                         emotion_state.get("valence", 0.5),
                         emotion_state.get("arousal", 0.5))
        trans = None
        if self._prev_payload_ep is not None and \
                self._prev_payload_ep["episode_id"] != ep["episode_id"]:
            trans = make_transition(self._prev_payload_ep, ep)
        self._prev_payload_ep = ep
        return {"seq": self._seq, "ts": round(time.time(), 3),
                "emotion_state": emotion_state,
                "transition": trans,
                "episode": ep,
                "audio_url": None}


# ── 自测 ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="7 情绪各产 1 条")
    ap.add_argument("--save", default=None, help="保存 live payload 序列 jsonl")
    args = ap.parse_args()

    idx = EpisodeIndex()
    print(f"[e1.2] 索引: {idx.counts}")
    resp = Responder(idx)

    demo_states = [
        {"emotion": e, "filtered_emotion": e, "valence": v, "arousal": a,
         "confidence": 0.9, "face_visible": True, "err": None}
        for e, v, a in [("joy", .8, .8), ("sad", .2, .3), ("angry", .2, .9),
                        ("fear", .3, .85), ("love", .85, .5), ("surprise", .7, .9),
                        ("neutral", .5, .4)]]

    payloads, fails = [], []
    for st in (demo_states if args.demo else demo_states[:1]):
        p = resp.respond(st)
        payloads.append(p)
        ep, tr = p["episode"], p["transition"]
        ok_budget = ep["quality"]["limits_ok"]
        ok_trans = tr is None or tr["quality"]["vmax_ok"]
        if not (ok_budget and ok_trans):
            fails.append((st["emotion"], ok_budget, ok_trans))
        tr_info = "-"
        if tr is not None:
            tr_info = (f"{tr['duration_s']:.2f}s "
                       f"vmax_ok={tr['quality']['vmax_ok']}")
        print(f"  seq={p['seq']} {st['emotion']:8s} → {ep['episode_id']:16s} "
              f"dur={ep['response']['trajectory']['duration_s']:.1f}s "
              f"trans={tr_info} budget_ok={ok_budget}")

    if args.save:
        path = args.save if os.path.isabs(args.save) else os.path.join(ROOT, args.save)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for p in payloads:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")
        print(f"[e1.2] 已保存 {len(payloads)} 条 → {path}")

    print("[e1.2] " + ("全部合规 ✅" if not fails else f"不合规: {fails} ❌"))
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
