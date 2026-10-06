# -*- coding: utf-8 -*-
"""B1 emotion expression library — 7 emotions x parametric primitives.

Implements docs/mapping_contract.md §1/§4: ELEGNT-informed vocabulary
(kinesics: nod/shake/tilt/lean/sway/tremble/gaze_shift/fold/scan/breathe;
proxemics: approach/avoid) with dynamics modifiers (amplitude, frequency,
hesitation, attack). All trajectories are offsets from an emotion-specific
base pose; engine.render() handles spline + limits + rate.

Each emotion program = {gamma, base(offsets), primitives, led, caption,
tts_style} — one Episode-record-ready bundle (contract §5).
"""
import numpy as np

from configs.joints import YAW, PITCH2, PITCH3, ROLL4, PITCH5
from primitives.engine import Primitive


def _off(**kw):
    """Build a 5-vector offset from named joint components."""
    v = np.zeros(5)
    lut = {"yaw": YAW, "p2": PITCH2, "p3": PITCH3, "roll": ROLL4, "p5": PITCH5}
    for k, val in kw.items():
        v[lut[k]] = val
    return v


# ---------- kinesics generators ----------

def oscillate(joint_key, amp, freq, duration, phase=0.0, center=None):
    """Generic sinusoidal oscillation as keyframes (8 per period)."""
    n_per, k_per = max(1, int(duration * freq)), 8
    center = _off() if center is None else center
    kfs = [(0.0, center.copy())]
    for i in range(1, n_per * k_per + 1):
        tt = i / (k_per * freq)
        s = np.sin(2 * np.pi * freq * tt + phase)
        kfs.append((tt, center + _off(**{joint_key: amp * s})))
    return kfs


def move_to(target, duration, attack=1.0):
    """Point-to-point with attack modifier (>1 = snappier start)."""
    mid = np.asarray(target, float) * min(0.9, 0.5 * attack)
    return [(0.0, _off()), (duration * 0.45, mid),
            (duration, np.asarray(target, float))]


def hold(duration):
    return Primitive("hold", [(0.0, _off()), (duration, _off())])


def nod(amp=0.25, freq=1.2, count=2):
    return Primitive("nod", oscillate("p5", amp, freq, count / freq))


def shake(amp=0.35, freq=1.6, count=2):
    return Primitive("shake", oscillate("yaw", amp, freq, count / freq))


def sway(amp=0.30, freq=0.6, duration=3.0):
    """Tail-wagging analog: slow wide yaw oscillation with head counter-phase."""
    kfs = oscillate("yaw", amp, freq, duration)
    # counter-phase head roll for organic feel
    kfs = [(t, q + _off(roll=0.12 * np.sin(2 * np.pi * freq * t + np.pi / 2)))
           for (t, q) in kfs]
    return Primitive("sway", kfs)


def tremble(amp=0.03, freq=9.0, duration=1.2):
    """Startle/fear tremor: high-freq small-amplitude on arm joints."""
    kfs = oscillate("p3", amp, freq, duration)
    kfs = [(t, q + _off(p5=amp * 0.7 * np.sin(2 * np.pi * freq * 1.13 * t)))
           for (t, q) in kfs]
    return Primitive("tremble", kfs)


def breathe(amp=0.02, freq=0.22, duration=4.5):
    return Primitive("breathe", oscillate("p3", amp, freq, duration))


def lean(amount=-0.45, duration=1.0, attack=1.0):
    """Proxemic approach (negative p2/p3 = lean forward toward user)."""
    tgt = _off(p2=amount, p3=amount * 0.5)
    return Primitive("lean", move_to(tgt, duration, attack))


def avoid(amount=0.55, duration=0.5):
    """Fast retract away from stimulus (fear)."""
    tgt = _off(p2=amount, p3=amount * 0.6, p5=0.2)
    return Primitive("avoid", move_to(tgt, duration, attack=2.0))


def gaze_shift(yaw_target, duration=0.8):
    return Primitive("gaze_shift", move_to(_off(yaw=yaw_target), duration))


def scan(sweep=0.9, period=6.0):
    """Vigilance scan: slow yaw sweep left->right->center."""
    half = period / 2
    kfs = [(0.0, _off()), (half * 0.5, _off(yaw=sweep)),
           (half, _off()), (half * 1.5, _off(yaw=-sweep)),
           (period, _off())]
    return Primitive("scan", kfs)


def fold(depth=0.5, duration=1.6):
    """Retract into rest/grooming posture."""
    tgt = _off(p2=depth, p3=-depth * 0.7, p5=depth * 0.5)
    return Primitive("fold", move_to(tgt, duration, attack=0.7))


def groom(duration=2.4):
    """Self-soothing rub: small high-freq head circles (grooming analog)."""
    kfs = oscillate("p5", 0.04, 3.5, duration)
    kfs = [(t, q + _off(roll=0.04 * np.cos(2 * np.pi * 3.5 * t)))
           for (t, q) in kfs]
    return Primitive("groom", kfs)


def dip(depth=0.35, duration=3.4, n=26):
    """Comfort bow: slow symmetric sink-and-rise (raised-cosine profile).

    Zero velocity at start, at the bottom, and at the end — out and return
    legs take equal time by construction. Reads as empathic lowering /
    "I sink with you", not as a nod. (QC review R8, 2026-10-03.)
    """
    tgt = _off(p2=depth, p3=-depth * 0.6, p5=depth * 0.8)
    kfs = []
    for k in range(n + 1):
        u = k / n
        env = 0.5 - 0.5 * np.cos(2 * np.pi * u)   # 0→1→0, v=0 at u=0,.5,1
        kfs.append((u * duration, tgt * env))
    return Primitive("dip", kfs)


def sway_gentle(amp=0.22, duration=5.0, cycles=2, n=40):
    """Slow symmetric left↔right sway with raised-cosine envelope.

    Starts and ends centred and still (no boundary velocity), left and
    right excursions equal — a low-arousal "accompanying" motion.
    (QC review R8, 2026-10-03.)
    """
    raw = []
    for k in range(n + 1):
        u = k / n
        env = 0.5 - 0.5 * np.cos(2 * np.pi * u)
        raw.append((u * duration, env * np.sin(2 * np.pi * cycles * u),
                    env * np.cos(2 * np.pi * cycles * u)))
    peak = max(max(abs(s), abs(c)) for _, s, c in raw) or 1.0
    kfs = [(t, _off(yaw=amp * s / peak, roll=0.10 * amp * c / peak))
           for (t, s, c) in raw]
    return Primitive("sway_gentle", kfs)


# ---------- emotion programs (contract §1 mapping) ----------

EMOTIONS = {
    "joy": {
        "gamma": [0.8, 0.2, 0.5],
        "base": _off(p2=-0.15, p3=0.10, p5=-0.05),
        "primitives": lambda: [nod(0.22, 1.4, 2), sway(0.30, 0.8, 2.6),
                               nod(0.18, 1.6, 2)],
        "led": {"rgbw": [255, 215, 0, 100], "pattern": "double_pulse",
                "freq_hz": 1.5, "intensity": [60, 100]},
        "caption": "Glad to interact with you!",
        "tts_style": "bright-upbeat",
    },
    "love": {
        "gamma": [0.7, 0.1, 0.6],
        "base": _off(p2=-0.20, p3=0.05),
        "primitives": lambda: [lean(-0.35, 1.4, attack=0.8),
                               sway(0.18, 0.5, 3.2), breathe(0.02, 0.2, 3.0)],
        "led": {"rgbw": [255, 180, 120, 60], "pattern": "breath",
                "freq_hz": 0.15, "intensity": [68, 78]},
        "caption": "I am here for you.",
        "tts_style": "soft-low",
    },
    "angry": {
        "gamma": [0.3, 0.4, 0.9],
        "base": _off(p2=-0.25, p5=-0.10),
        "primitives": lambda: [lean(-0.45, 0.5, attack=2.0),
                               nod(0.35, 2.2, 3), shake(0.2, 2.0, 1)],
        "led": {"rgbw": [255, 40, 0, 0], "pattern": "solid",
                "freq_hz": 0.0, "intensity": [90, 100]},
        "caption": "Hey. Back off a little.",
        "tts_style": "sharp-loud",
    },
    "fear": {
        "gamma": [0.8, 0.9, 0.2],
        "base": _off(),
        "primitives": lambda: [avoid(0.55, 0.4), tremble(0.03, 9.0, 1.5),
                               gaze_shift(-0.5, 0.5)],
        "led": {"rgbw": [255, 0, 0, 0], "pattern": "strobe",
                "freq_hz": 9.0, "intensity": [100, 100]},
        "caption": "Watch out!",
        "tts_style": "fast-high",
    },
    "surprise": {
        "gamma": [0.7, 0.8, 0.3],
        "base": _off(),
        "primitives": lambda: [Primitive("startle", move_to(
                                   _off(p3=0.35, p5=-0.25), 0.25, attack=2.5)),
                               hold(0.6), tremble(0.02, 8.0, 0.8),
                               gaze_shift(0.4, 0.6)],
        "led": {"rgbw": [255, 255, 255, 200], "pattern": "strobe",
                "freq_hz": 4.0, "intensity": [100, 100]},
        "caption": "Whoa! What was that?",
        "tts_style": "sudden-high",
    },
    "sad": {
        "gamma": [0.1, 0.1, 0.8],
        "base": _off(p2=0.15, p3=-0.10, p5=0.15),
        # R8 redesign (2026-10-03): symmetric slow comfort motions only —
        # dip (sink with you) → gentle L↔R sway → dip → ultra-slow breath.
        # No wrist fidget (groom read as happy/curious, removed); out and
        # return legs are equally slow by construction (raised-cosine).
        "primitives": lambda: [dip(0.35, 3.4), sway_gentle(0.22, 5.0, 2),
                               dip(0.28, 3.0), breathe(0.015, 0.15, 3.0)],
        "led": {"rgbw": [60, 30, 90, 25], "pattern": "breath",
                "freq_hz": 0.1, "intensity": [15, 30]},
        "caption": "I feel you... take your time.",
        "tts_style": "slow-low",
    },
    "neutral": {
        "gamma": [0.5, 0.5, 0.4],
        "base": _off(),
        "primitives": lambda: [scan(0.8, 6.0), breathe(0.02, 0.22, 4.0),
                               gaze_shift(0.3, 1.0)],
        "led": {"rgbw": [120, 180, 255, 60], "pattern": "double_pulse",
                "freq_hz": 0.8, "intensity": [35, 85]},
        "caption": "Exploring surroundings.",
        "tts_style": "calm-flat",
    },
}

EMOTION_NAMES = list(EMOTIONS.keys())
