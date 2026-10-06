# -*- coding: utf-8 -*-
"""7-emotion showcase GIF (English captions, GitHub-publish ready).

Renders each library.EMOTIONS program (base pose + primitive sequence) per
mapping_contract v1.1 §1, with synced LED color/pattern (strobe approximated
by frame-alternating brightness, breath by slow intensity modulation).
Captions: emotion / fly instinct / caption line / gamma.

Usage (LeLampEmpathy root): python tools/demo_emotions_gif.py
Output: data/episodes/qc/demo_emotions.gif
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import JOINT_NAMES, ZERO  # noqa: E402
from primitives.engine import render  # noqa: E402
from primitives.library import EMOTIONS, EMOTION_NAMES  # noqa: E402

OUT_GIF = os.path.join("data", "episodes", "qc", "demo_emotions.gif")
W, H = 480, 360
FPS = 15

META_EN = {
    "joy":      ("Joy", "Sugar reward - DA burst"),
    "love":     ("Love", "Courtship/social - sustained P1 DA"),
    "angry":    ("Angry", "Aggression/territoriality - 5-HT surge"),
    "fear":     ("Fear", "Avoidance/escape - OA surge"),
    "surprise": ("Surprise", "Startle reflex - Giant Fiber pulse"),
    "sad":      ("Sad", "Hypoactivity/grooming - suppressed tonus"),
    "neutral":  ("Neutral", "Exploration/foraging - sparse baseline"),
}


def _font(size):
    from PIL import ImageFont
    for cand in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def led_rgba(led, t):
    """rgbw + pattern -> (rgba 近似, 亮度系数)。仿真仅用 RGB 通道。"""
    r, g, b = [c / 255 for c in led["rgbw"][:3]]
    pat, fq = led["pattern"], led["freq_hz"]
    k = 1.0
    if pat == "strobe":
        k = 1.0 if np.sin(2 * np.pi * fq * t) > 0 else 0.12
    elif pat == "breath":
        lo, hi = [x / 100 for x in led["intensity"]]
        k = lo + (hi - lo) * (0.5 + 0.5 * np.sin(2 * np.pi * fq * t))
    elif pat == "double_pulse":
        k = 0.7 + 0.3 * max(0.0, np.sin(2 * np.pi * fq * t))
    elif pat == "chase":
        k = 0.75 + 0.25 * np.sin(2 * np.pi * fq * t)
    return [r * k, g * k, b * k, 1.0]


def main():
    import pybullet as p
    import pybullet_data
    from PIL import Image, ImageDraw

    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.loadURDF("plane.urdf")
    robot = p.loadURDF(os.path.join("assets", "lelamp_5dof.urdf"),
                       basePosition=[0, 0, 0], useFixedBase=True)
    name2idx = {p.getJointInfo(robot, i)[1].decode(): i
                for i in range(p.getNumJoints(robot))}
    jidx = [name2idx[n] for n in JOINT_NAMES]
    view = p.computeViewMatrixFromYawPitchRoll([0, 0, 0.45], 0.62, 26, -10, 0, 2)
    proj = p.computeProjectionMatrixFOV(50, W / H, 0.05, 5.0)
    f_t, f_m, f_s = _font(20), _font(15), _font(14)

    all_frames = []
    for name in EMOTION_NAMES:
        emo = EMOTIONS[name]
        base = ZERO + np.asarray(emo["base"], float)
        traj = render(emo["primitives"](), base_pose=base)
        t_arr, q_arr = traj["t"], traj["q"]
        step = max(1, int(50 / FPS))          # 50Hz -> 15fps 抽帧
        en, instinct = META_EN[name]
        n = 0
        for i in range(0, len(t_arr), step):
            for idx, val in zip(jidx, q_arr[i]):
                p.resetJointState(robot, idx, float(val))
            p.changeVisualShape(robot, jidx[-1],
                                rgbaColor=led_rgba(emo["led"], t_arr[i]))
            p.stepSimulation()
            _, _, rgb, _, _ = p.getCameraImage(W, H, view, proj)
            img = Image.fromarray(
                np.frombuffer(rgb, dtype=np.uint8).reshape(H, W, 4)[:, :, :3])
            dr = ImageDraw.Draw(img)
            dr.rectangle([0, H - 62, W, H], fill=(20, 20, 26))
            dr.text((10, H - 56), en, fill=(255, 215, 90), font=f_t)
            dr.text((10, H - 32), f"instinct: {instinct}",
                    fill=(150, 200, 255), font=f_m)
            dr.text((10, H - 14), f'"{emo["caption"]}"  gamma={emo["gamma"]}',
                    fill=(220, 220, 220), font=f_s)
            all_frames.append(img)
            n += 1
        all_frames.extend([all_frames[-1]] * (FPS // 2))   # 情绪间停 0.5s
        print(f"  {name}: {n} frames", flush=True)
    p.disconnect(cid)

    os.makedirs(os.path.dirname(OUT_GIF), exist_ok=True)
    all_frames[0].save(OUT_GIF, save_all=True, append_images=all_frames[1:],
                       duration=int(1000 / FPS), loop=0, optimize=True)
    print(f"GIF: {OUT_GIF} ({len(all_frames)} frames, "
          f"{os.path.getsize(OUT_GIF)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
