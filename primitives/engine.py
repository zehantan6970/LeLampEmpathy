# -*- coding: utf-8 -*-
"""Parametric motion-primitive engine (B1).

Keyframe templates -> Catmull-Rom spline -> 50 Hz joint trajectory with
joint-limit clamping and per-step rate limiting (time-stretch, never clip
shape). Pure element-wise numpy (no BLAS calls — see Project A env notes).

Contract: docs/mapping_contract.md §4 (vocabulary) and §3 (output format).
"""
import numpy as np

from configs.joints import (ZERO, JOINT_LOWER, JOINT_UPPER,
                            MAX_DQ_PER_STEP, MAX_DDQ_PER_STEP, CONTROL_HZ)


def catmull_rom(tk, qk, t):
    """Catmull-Rom spline through keyframes.

    tk: (K,) keyframe times (ascending); qk: (K, 5) joint offsets;
    t:  (T,) sample times within [tk[0], tk[-1]].
    Returns (T, 5). Element-wise ops only.
    """
    tk = np.asarray(tk, dtype=float)
    qk = np.asarray(qk, dtype=float)
    t = np.asarray(t, dtype=float)
    K = len(tk)
    # pad endpoints (zero-slope boundary)
    tke = np.concatenate([[2 * tk[0] - tk[1]], tk, [2 * tk[-1] - tk[-2]]])
    qke = np.concatenate([qk[:1], qk, qk[-1:]], axis=0)
    idx = np.searchsorted(tk, t, side="right") - 1
    idx = np.clip(idx, 0, K - 2)
    out = np.zeros((len(t), qk.shape[1]))
    for j in range(len(t)):
        i = idx[j]
        t0, t1 = tk[i], tk[i + 1]
        u = 0.0 if t1 == t0 else (t[j] - t0) / (t1 - t0)
        p0, p1, p2, p3 = qke[i], qke[i + 1], qke[i + 2], qke[i + 3]
        out[j] = 0.5 * ((2 * p1) + (-p0 + p2) * u
                        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                        + (-p0 + 3 * p1 - 3 * p2 + p3) * u * u * u)
    return out


class Primitive:
    """One parametric motion primitive.

    keyframes: list of (time_s, q_offset[5]) — offsets relative to base pose.
    """

    def __init__(self, name, keyframes, meta=None):
        self.name = name
        self.keyframes = keyframes
        self.meta = meta or {}

    @property
    def duration(self):
        return self.keyframes[-1][0]


def _track_limit(q, max_dq, max_ddq, hz):
    """Causal tracking limiter (second-order slew) on a sampled trajectory.

    Per-step: position error -> velocity command (clipped to max_dq) ->
    velocity increment (clipped to max_ddq) -> integrate. Guarantees
    |dq| <= max_dq and |ddq| <= max_ddq per control step with bounded,
    self-correcting lag and NO drift (unlike POCS re-integration, which
    accumulates DC error). This mirrors how the real STS3215 position
    controller behaves under speed/accel limits.

    A settle tail (repeat of the final target) is appended until the
    tracker converges (max 2 s), so end pose matches the spline's end pose.
    Returns (q_limited, settle_seconds).
    """
    q = np.asarray(q, float)
    n = len(q)
    tail_n = 0
    pos = q[0].copy()
    vel = np.zeros(q.shape[1])
    out = np.empty_like(q)
    out[0] = pos
    i = 0
    total = n + int(2.0 * hz)          # budget incl. settle tail
    for step in range(1, total):
        tgt = q[i] if i < n else q[-1]
        if i >= n:
            tail_n += 1
            if np.max(np.abs(tgt - pos)) < 1e-3:
                out = out[:step]
                break
        err = tgt - pos
        v_des = np.clip(err, -max_dq, max_dq)
        dv = np.clip(v_des - vel, -max_ddq, max_ddq)
        vel = vel + dv
        pos = pos + vel
        if step < n:
            out[step] = pos
        else:
            out = np.concatenate([out, pos[None, :]], axis=0)
        if i < n:
            i += 1
    return out, tail_n / float(hz)


def render(primitives, base_pose=None, hz=CONTROL_HZ, gap_s=0.35,
           max_dq=MAX_DQ_PER_STEP, max_ddq=MAX_DDQ_PER_STEP):
    """Render a primitive sequence to a joint trajectory.

    primitives: list[Primitive] (concatenated with short settle gaps)
    base_pose:  absolute 5-vector the offsets apply to (default ZERO)
    Returns dict(t, q, info). Trajectory is limit-clamped and passed through
    a causal rate+accel tracking limiter (shape preserved, duration extended
    only by a short settle tail).

    v3.1: gap_s 0.15 -> 0.35 s; time-stretch replaced by tracking limiter
    (QC review R1 — time-stretch could not reduce knot ddq spikes; POCS
    drifted; causal tracking is both exact and servo-faithful).
    """
    base = ZERO.copy() if base_pose is None else np.asarray(base_pose, float)
    # 1) assemble keyframe timeline (lead-in from current base, gaps between)
    tk, qk = [0.0], [np.zeros(5)]
    t_cursor = 0.0
    for p in primitives:
        for (dt, off) in p.keyframes:
            tk.append(t_cursor + gap_s + dt)
            qk.append(np.asarray(off, dtype=float))
        t_cursor += gap_s + p.duration
    tk = np.array(tk)
    qk = np.stack(qk)

    # 2) sample spline at control rate
    t = np.arange(0.0, tk[-1] + 1.0 / hz, 1.0 / hz)
    q = catmull_rom(tk, qk, t)

    # 3) causal rate + accel limiting, then absolute pose + clamp
    q, settle_s = _track_limit(q, max_dq, max_ddq, hz)
    t = np.arange(0.0, len(q) / hz, 1.0 / hz)[: len(q)]
    q_abs = np.clip(base + q, JOINT_LOWER, JOINT_UPPER)
    clip_count = int(np.count_nonzero((base + q) != q_abs))
    max_dq_real = float(np.max(np.abs(np.diff(q_abs, axis=0)))) if len(t) > 1 else 0.0
    smooth = float(np.max(np.abs(np.diff(q_abs, n=2, axis=0)))) if len(t) > 2 else 0.0
    return {"t": t, "q": q_abs,
            "info": {"stretch": 1.0,
                     "settle_s": round(settle_s, 3),
                     "clip_count": clip_count,
                     "max_dq": max_dq_real,
                     "max_jerk_step2": smooth,
                     "gap_s": gap_s,
                     "budget": {"max_dq": max_dq, "max_ddq": max_ddq},
                     "limits_ok": bool(np.all(q_abs >= JOINT_LOWER - 1e-9)
                                       and np.all(q_abs <= JOINT_UPPER + 1e-9))}}
