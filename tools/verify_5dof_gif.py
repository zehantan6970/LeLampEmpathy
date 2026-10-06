# -*- coding: utf-8 -*-
"""5-servo sweep verification GIF (English captions, GitHub-publish ready).

Each joint sweeps from lower limit to upper limit and back to neutral, one at
a time, with captions showing the official servo ID / joint name / function.
Directly checkable against the physical LeLamp (5x STS3215 bus servos).

Usage (LeLampEmpathy root): python tools/verify_5dof_gif.py
Output: data/episodes/qc/verify_5dof.gif
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import (JOINT_LOWER, JOINT_NAMES, JOINT_UPPER,  # noqa: E402
                            ZERO)

OUT_GIF = os.path.join("data", "episodes", "qc", "verify_5dof.gif")
W, H = 480, 360
FPS = 15

# Official LeLamp config (lelamp_runtime / LeLamp-Extend-Board, 5x STS3215)
SERVO_TABLE = [
    ("ID 1", "base_yaw",    "base rotation (turn head left/right)"),
    ("ID 2", "base_pitch",  "base pitch (look up/down)"),
    ("ID 3", "elbow_pitch", "elbow pitch (upper-arm bend)"),
    ("ID 4", "wrist_roll",  "wrist roll (head tilt/roll)"),
    ("ID 5", "wrist_pitch", "wrist pitch (lamp-head up/down)"),
]


def _font(size):
    from PIL import ImageFont
    for cand in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


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
    view = p.computeViewMatrixFromYawPitchRoll([0, 0, 0.42], 0.55, 30, -12, 0, 2)
    proj = p.computeProjectionMatrixFOV(50, W / H, 0.05, 5.0)
    f_t, f_s = _font(20), _font(15)

    frames = []
    for j, (sid, official, desc) in enumerate(SERVO_TABLE):
        lo, hi = float(JOINT_LOWER[j]), float(JOINT_UPPER[j])
        # 中位 -> 上限 -> 下限 -> 中位（各 0.8s）
        seg = np.concatenate([
            np.linspace(ZERO[j], hi, int(0.8 * FPS)),
            np.linspace(hi, lo, int(1.6 * FPS)),
            np.linspace(lo, ZERO[j], int(0.8 * FPS)),
        ])
        for v in seg:
            q = ZERO.copy()
            q[j] = v
            for idx, val in zip(jidx, q):
                p.resetJointState(robot, idx, float(val))
            p.stepSimulation()
            _, _, rgb, _, _ = p.getCameraImage(W, H, view, proj)
            img = Image.fromarray(
                np.frombuffer(rgb, dtype=np.uint8).reshape(H, W, 4)[:, :, :3])
            dr = ImageDraw.Draw(img)
            dr.rectangle([0, H - 62, W, H], fill=(20, 20, 26))
            dr.text((10, H - 56), f"{sid}  {official}", fill=(255, 215, 90),
                    font=f_t)
            dr.text((10, H - 30),
                    f"{desc}   [{JOINT_NAMES[j]}]  q={v:+.2f} rad",
                    fill=(220, 220, 220), font=f_s)
            # joint position as fraction of its limit range (progress bar)
            frac = (v - lo) / (hi - lo)
            dr.rectangle([10, H - 8, 10 + int(frac * (W - 20)), H - 4],
                         fill=(90, 180, 255))
            frames.append(img)
        frames.extend([frames[-1]] * (FPS // 3))
        print(f"  {sid} {official}: {len(seg)} frames", flush=True)
    p.disconnect(cid)

    os.makedirs(os.path.dirname(OUT_GIF), exist_ok=True)
    frames[0].save(OUT_GIF, save_all=True, append_images=frames[1:],
                   duration=int(1000 / FPS), loop=0, optimize=True)
    print(f"GIF: {OUT_GIF} ({len(frames)} frames, "
          f"{os.path.getsize(OUT_GIF)/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
