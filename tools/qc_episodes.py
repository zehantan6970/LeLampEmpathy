# -*- coding: utf-8 -*-
"""B1 episode 种子集质检（2026-10-02）。

三层检查：
  L1 数值质检：限位 / 时长 / 各关节行程（excursion）/ 反转次数
  L2 手势可辨识度：nod/shake/curious/startle 各自的「看得懂」硬指标
  L3 视觉质检：pybullet DIRECT 离屏渲染关键帧拼图 + Pillow 轨迹图
      （本机 matplotlib 硬崩溃，绘图一律 Pillow 4x 超采样，见项目环境基线）

用法（LeLampEmpathy 根目录）：
    python tools/qc_episodes.py
产物：data/episodes/qc/{qc_report.json, qc_report.md,
      contact_sheet_gestures.png, traj_<gesture>.png}
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import (JOINT_NAMES, JOINT_LOWER, JOINT_UPPER,  # noqa: E402
                            JOINT_SHORT)

EP_PATH = os.path.join("data", "episodes", "episodes_v2.jsonl")
QC_DIR = os.path.join("data", "episodes", "qc")
GESTURES = ["nod", "shake", "curious", "startle"]
EMOTIONS = ["joy", "love", "angry", "fear", "surprise", "sad", "neutral"]
FRAME_W, FRAME_H = 640, 480


# ---------------------------------------------------------------- L1/L2

def reversals(x, thresh=0.02):
    """方向反转次数（滞回 thresh 防抖）。"""
    d = np.diff(x)
    sign, count, last = np.sign(d), 0, 0.0
    for s, m in zip(sign, np.abs(d)):
        if m < thresh:
            continue
        if last != 0.0 and s != 0.0 and s != last:
            count += 1
        if s != 0.0:
            last = s
    return count


def qc_episode(ep):
    q = np.array(ep["response"]["trajectory"]["q"], dtype=float)
    hz = ep["response"]["trajectory"]["hz"]
    exc = q.max(axis=0) - q.min(axis=0)
    ok_limits = bool(np.all(q >= JOINT_LOWER - 1e-4)
                     and np.all(q <= JOINT_UPPER + 1e-4))
    m = {"limits_ok": ok_limits,
         "duration_s": ep["response"]["trajectory"]["duration_s"],
         "excursion": {JOINT_NAMES[j]: round(float(exc[j]), 3)
                       for j in range(5)}}
    prog = ep["response"]["program"]
    checks = {}
    if prog == "nod":
        checks = {"p5_p2p>=0.25": exc[4] >= 0.25,
                  "p5_reversals>=2": reversals(q[:, 4]) >= 2}
    elif prog == "shake":
        checks = {"yaw_p2p>=0.35": exc[0] >= 0.35,
                  "yaw_reversals>=2": reversals(q[:, 0]) >= 2}
    elif prog == "curious":
        checks = {"roll_exc>=0.20": exc[3] >= 0.20,
                  "yaw_exc>=0.15": exc[0] >= 0.15}
    elif prog == "startle":
        dyaw = np.abs(np.diff(q[:, 0]))
        onset = float(np.argmax(dyaw)) / max(1, len(dyaw))
        checks = {"yaw_exc>=0.40": exc[0] >= 0.40,
                  "onset<30%时长": onset < 0.30,
                  "峰值速度>=1.5rad/s": float(dyaw.max() * hz) >= 1.5}
    m["checks"] = {k: bool(v) for k, v in checks.items()}
    m["pass"] = bool(ok_limits and all(checks.values()))
    return m


# ---------------------------------------------------------------- L3 渲染

DRIVE_JOINT = {"nod": 4, "shake": 0, "curious": 3, "startle": 0}


def pick_extreme_frames(ep, k=4):
    """按驱动关节的极值选帧（起点 / 最小 / 最大 / 终点），保证帧间对比可见。"""
    q = np.array(ep["response"]["trajectory"]["q"], dtype=float)
    j = DRIVE_JOINT.get(ep["response"]["program"], 0)
    picks = [0, int(np.argmin(q[:, j])), int(np.argmax(q[:, j])), len(q) - 1]
    # 去重保序（极端情况下极值与端点重合时用等间距补齐）
    seen = []
    for i in picks + list(np.linspace(0, len(q) - 1, k).astype(int)):
        if i not in seen:
            seen.append(int(i))
        if len(seen) == k:
            break
    return seen


def render_frames(ep, k=4):
    """pybullet DIRECT 离屏渲染 k 个关键帧，返回 PIL Image 列表。"""
    import pybullet as p
    import pybullet_data
    from PIL import Image

    cid = p.connect(p.DIRECT)
    p.setAdditionalSearchPath(pybullet_data.getDataPath())
    p.loadURDF("plane.urdf")
    robot = p.loadURDF(os.path.join("assets", "lelamp_5dof.urdf"),
                       basePosition=[0, 0, 0], useFixedBase=True)
    name2idx = {p.getJointInfo(robot, i)[1].decode(): i
                for i in range(p.getNumJoints(robot))}
    jidx = [name2idx[n] for n in JOINT_NAMES]

    q = np.array(ep["response"]["trajectory"]["q"], dtype=float)
    led = ep["response"]["led"]["rgbw"]
    rgba = [led[0] / 255, led[1] / 255, led[2] / 255, 1.0]

    # 近景：对准灯头，保证手势可读
    view = p.computeViewMatrixFromYawPitchRoll([0, 0, 0.42], 0.55, 30, -12, 0, 2)
    proj = p.computeProjectionMatrixFOV(50, FRAME_W / FRAME_H, 0.05, 5.0)
    frames = []
    for i in pick_extreme_frames(ep, k):
        for idx, val in zip(jidx, q[i]):
            p.resetJointState(robot, idx, float(val))
        p.changeVisualShape(robot, jidx[-1], rgbaColor=rgba)
        p.stepSimulation()
        _, _, rgb, _, _ = p.getCameraImage(FRAME_W, FRAME_H, view, proj,
                                           renderer=p.ER_BULLET_HARDWARE_OPENGL)
        frames.append(Image.fromarray(
            np.frombuffer(rgb, dtype=np.uint8).reshape(FRAME_H, FRAME_W, 4)[:, :, :3]))
    p.disconnect(cid)
    return frames


def _cjk_font(size):
    from PIL import ImageFont
    for cand in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(ep_frames):
    """{gesture: [frames]} -> 4 行 x K 列拼图（行首留标签条）。"""
    from PIL import Image, ImageDraw
    rows = list(ep_frames.items())
    k = len(rows[0][1])
    label_w = 200
    sheet = Image.new("RGB", (label_w + k * FRAME_W, len(rows) * FRAME_H),
                      (24, 24, 28))
    draw = ImageDraw.Draw(sheet)
    font = _cjk_font(30)
    zh = {"nod": "点头", "shake": "摇头", "curious": "好奇", "startle": "惊吓"}
    for r, (name, frames) in enumerate(rows):
        draw.text((14, r * FRAME_H + FRAME_H // 2 - 20),
                  f"{name}\n{zh.get(name, '')}", fill=(240, 240, 240), font=font)
        for c, fr in enumerate(frames):
            sheet.paste(fr, (label_w + c * FRAME_W, r * FRAME_H))
    return sheet


def traj_plot(ep, path, base=1600):
    """5 关节轨迹图：4x 超采样绘制后 LANCZOS 降采样（项目绘图纪律）。"""
    from PIL import Image, ImageDraw, ImageFont
    S = 4
    W, H = base * S, int(base * 0.625) * S
    img = Image.new("RGB", (W, H), (250, 250, 250))
    dr = ImageDraw.Draw(img)
    font = _cjk_font(22 * S)
    font_s = _cjk_font(18 * S)

    q = np.array(ep["response"]["trajectory"]["q"], dtype=float)
    hz = ep["response"]["trajectory"]["hz"]
    t = np.arange(len(q)) / hz
    L, R, T, B = 90 * S, W - 40 * S, 70 * S, H - 70 * S
    colors = [(214, 39, 40), (44, 160, 44), (31, 119, 180),
              (148, 103, 189), (255, 127, 14)]
    ymin = min(JOINT_LOWER.min(), q.min()) - 0.1
    ymax = max(JOINT_UPPER.max(), q.max()) + 0.1

    def xy(i, v):
        return (L + (R - L) * (t[i] / t[-1]),
                B - (B - T) * ((v - ymin) / (ymax - ymin)))

    dr.rectangle([L, T, R, B], outline=(60, 60, 60), width=2 * S)
    for j in range(5):
        pts = [xy(i, q[i, j]) for i in range(len(q))]
        dr.line(pts, fill=colors[j], width=3 * S)
        dr.text((L + 10 * S, T + (8 + j * 26) * S), JOINT_SHORT[j],
                fill=colors[j], font=font_s)
    dr.text((L, 20 * S), f"{ep['response']['program']}  |  {ep['scene_text'][:28]}",
            fill=(20, 20, 20), font=font)
    dr.text((L, H - 45 * S), "time (s)", fill=(80, 80, 80), font=font_s)
    img = img.resize((base, int(base * 0.625)), Image.LANCZOS)
    img.save(path)


# ---------------------------------------------------------------- main

def main():
    os.makedirs(QC_DIR, exist_ok=True)
    eps = [json.loads(l) for l in open(EP_PATH, encoding="utf-8")]

    picks = {}
    for g in GESTURES:
        picks[g] = next(e for e in eps if e["response"]["program"] == g)
    for emo in EMOTIONS:
        picks[f"emp_{emo}"] = next(
            e for e in eps if e["category"] == "empathy"
            and e["response"]["program"] == emo)

    report = {"episodes_total": len(eps), "sampled": {}, "verdict": {}}
    for key, ep in picks.items():
        report["sampled"][key] = qc_episode(ep)

    # 全量 L1（限位+时长），不只抽样
    all_limits = all(np.all(np.array(e["response"]["trajectory"]["q"])
                            >= JOINT_LOWER - 1e-4)
                     and np.all(np.array(e["response"]["trajectory"]["q"])
                                <= JOINT_UPPER + 1e-4) for e in eps)
    report["all_80_limits_ok"] = bool(all_limits)
    report["verdict"]["L1_numeric"] = bool(
        all_limits and all(m["limits_ok"] for m in report["sampled"].values()))
    report["verdict"]["L2_gesture"] = bool(all(
        report["sampled"][g]["pass"] for g in GESTURES))

    # L3：视觉产物
    ep_frames = {}
    for g in GESTURES:
        ep = picks[g]
        ep_frames[g] = render_frames(ep, k=4)
        traj_plot(ep, os.path.join(QC_DIR, f"traj_{g}.png"))
    contact_sheet(ep_frames).save(
        os.path.join(QC_DIR, "contact_sheet_gestures.png"))
    report["verdict"]["L3_visual"] = True   # 产物生成成功；观感由人终审

    with open(os.path.join(QC_DIR, "qc_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    lines = ["# B1 episode 种子集质检报告（80 条 v1）", "",
             f"- 全量限位：{'80/80 PASS' if all_limits else 'FAIL'}",
             f"- L2 手势可辨识度：{sum(report['sampled'][g]['pass'] for g in GESTURES)}/4 PASS",
             "", "| 抽样 | 时长s | 主要行程 | 检查 | 判定 |",
             "|---|---|---|---|---|"]
    for key, m in report["sampled"].items():
        top = sorted(m["excursion"].items(), key=lambda kv: -kv[1])[:2]
        exc = ", ".join(f"{k.split('_')[1]}={v:.2f}" for k, v in top)
        chk = "; ".join(f"{k}{'✓' if v else '✗'}" for k, v in m["checks"].items()) or "—"
        lines.append(f"| {key} | {m['duration_s']:.1f} | {exc} | {chk} | "
                     f"{'PASS' if m['pass'] else 'FAIL'} |")
    lines += ["", "视觉产物：contact_sheet_gestures.png（4 手势×4 关键帧）、"
                  "traj_<gesture>.png（5 关节轨迹）"]
    with open(os.path.join(QC_DIR, "qc_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(json.dumps(report["verdict"], ensure_ascii=False))
    for g in GESTURES:
        m = report["sampled"][g]
        print(f"  {g:<8s} {'PASS' if m['pass'] else 'FAIL'}  {m['checks']}")
    print(f"QC 产物 -> {QC_DIR}")


if __name__ == "__main__":
    main()
