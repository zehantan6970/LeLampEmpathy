# -*- coding: utf-8 -*-
"""Joint configuration — mirrors assets/lelamp_5dof.urdf (single source:
Project A configs/default_config.py; values verified identical 2026-09-30).

官方 LeLamp（lelamp_runtime / LeLamp-Extend-Board）标准配置 = 5x STS3215
总线舵机，与本仿真关节一一对应（2026-10-02 核查修订）：

    舵机 ID  官方关节名    作用                    仿真关节 (URDF)
    1        base_yaw     底座水平旋转(左右转头)  joint1_yaw
    2        base_pitch   底座俯仰(抬头低头)      joint2_pitch
    3        elbow_pitch  肘部俯仰(大臂弯曲)      joint3_pitch
    4        wrist_roll   手腕旋转(灯头滚转)      joint4_roll
    5        wrist_pitch  手腕俯仰(灯头上下)      joint5_pitch

LED：SK6812 内置芯片 RGBW（暖白）单点高亮可编程灯条 → 仿真以 lamp_head
link 变色 + episode 的 rgbw 四通道字段表示（W=暖白通道，仿真渲染只用
RGB 三通道，W 通道保留给实机驱动）。

Joint semantics (5-DOF LeLamp):
    joint1_yaw    base rotation (left/right look)
    joint2_pitch  lower arm (forward lean / backward retract)
    joint3_pitch  upper arm (raise / lower head assembly)
    joint4_roll   head roll (tilt, "questioning" lean)
    joint5_pitch  head pitch (nod / look up-down)
"""
import numpy as np

JOINT_NAMES = ["joint1_yaw", "joint2_pitch", "joint3_pitch",
               "joint4_roll", "joint5_pitch"]
JOINT_LOWER = np.array([-5.021034, -1.084258, -2.820024, -3.786540, -0.853337])
JOINT_UPPER = np.array([1.262151, 2.057335, 0.321569, 2.496645, 2.288255])
ZERO = (JOINT_LOWER + JOINT_UPPER) / 2.0     # neutral = range midpoint (F5)
# --- v3.1 motion budget (QC review 2026-10-03, docs/qc_review_v3_analysis.md R1)
# Hardware refs: STS3215 no-load 4.71 rad/s @12V, rated torque 10 kg*cm;
# PLA structure (15% infill). Budget = empathy-conservative tier:
#   vmax <= 1.5 rad/s (32% of no-load), amax <= 40 rad/s^2.
# Per-emotion overrides live in tools/build_episodes_v3.py (sad/love slower,
# fear/surprise faster but still capped).
MAX_DQ_PER_STEP = 0.030                       # rad per control step @50 Hz (=1.5 rad/s)
MAX_DDQ_PER_STEP = 0.016                      # rad per step^2 @50 Hz (=40 rad/s^2)
CONTROL_HZ = 50

# Convenience indices
YAW, PITCH2, PITCH3, ROLL4, PITCH5 = range(5)

# 图例短名（qc/绘图用）
JOINT_SHORT = ["yaw", "p2", "p3", "roll", "p5"]
