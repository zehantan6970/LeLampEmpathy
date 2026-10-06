# -*- coding: utf-8 -*-
"""B1 闭环演示「录屏」（2026-10-02）。

沙箱无法截屏 GUI，改用 pybullet DIRECT 离屏渲染逐帧捕获：
4 个响应式手势（点头/摇头/好奇/惊吓）按 episode 轨迹连续播放，
LED 颜色同步（惊吓为高频红闪——交替帧明暗模拟 strobe），
底部叠加字幕条（手势名 + 场景文本 + 台词）。输出 GIF。

用法（LeLampEmpathy 根目录）：
    python tools/record_demo_gif.py
产物：data/episodes/qc/demo_gestures.gif
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import JOINT_NAMES  # noqa: E402

EP_PATH = os.path.join("data", "episodes", "episodes_v2.jsonl")
OUT_GIF = os.path.join("data", "episodes", "qc", "demo_gestures.gif")
GESTURES = ["nod", "shake", "curious", "startle"]
EN = {"nod": "Nod - agreement", "shake": "Shake - refusal",
      "curious": "Curious - tilted-head gaze",
      "startle": "Startle - sharp turn-away + red strobe"}
# English response lines for the published GIF (episode captions are Chinese)
EN_LINE = {"nod": "Got it - I understand you.",
           "shake": "Hmm - I would not do that.",
           "curious": "Oh? What is this?",
           "startle": "Whoa! You scared me!"}
W, H = 480, 360
FPS = 10


def _font(size):
    from PIL import ImageFont
    for cand in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_episode_frames(p, robot, jidx, view, proj, ep):
    from PIL import Image, ImageDraw
    q = np.array(ep["response"]["trajectory"]["q"], dtype=float)
    led = ep["response"]["led"]
    strobe = led["pattern"] == "strobe"
    base_rgba = [c / 255 for c in led["rgbw"][:3]] + [1.0]
    font = _font(18)
    font_s = _font(14)
    prog = ep["response"]["program"]
    frames = []
    for fi, row in enumerate(q):
        for idx, val in zip(jidx, row):
            p.resetJointState(robot, idx, float(val))
        rgba = base_rgba if not (strobe and fi % 2) else [0.15, 0.0, 0.0, 1.0]
        p.changeVisualShape(robot, jidx[-1], rgbaColor=rgba)
        p.stepSimulation()
        _, _, rgb, _, _ = p.getCameraImage(W, H, view, proj)
        img = Image.fromarray(
            np.frombuffer(rgb, dtype=np.uint8).reshape(H, W, 4)[:, :, :3])
        dr = ImageDraw.Draw(img)
        dr.rectangle([0, H - 46, W, H], fill=(20, 20, 26))
        dr.text((10, H - 42), f"{prog} | {EN.get(prog, '')}",
                fill=(255, 215, 90), font=font)
        dr.text((10, H - 20), f'response: "{EN_LINE.get(prog, "")}"',
                fill=(220, 220, 220), font=font_s)
        frames.append(img)
    return frames


def main():
    import pybullet as p
    import pybullet_data

    eps = [json.loads(l) for l in open(EP_PATH, encoding="utf-8")]
    picks = {g: next(e for e in eps if e["response"]["program"] == g)
             for g in GESTURES}

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

    all_frames = []
    for g in GESTURES:
        fr = render_episode_frames(p, robot, jidx, view, proj, picks[g])
        all_frames.extend(fr + [fr[-1]] * (FPS // 2))  # 手势间停 0.5s
        print(f"  {g}: {len(fr)} frames", flush=True)
    p.disconnect(cid)

    os.makedirs(os.path.dirname(OUT_GIF), exist_ok=True)
    all_frames[0].save(OUT_GIF, save_all=True, append_images=all_frames[1:],
                       duration=int(1000 / FPS), loop=0, optimize=True)
    mb = os.path.getsize(OUT_GIF) / 1e6
    print(f"GIF: {OUT_GIF} ({len(all_frames)} frames, {mb:.1f} MB)")


if __name__ == "__main__":
    main()
