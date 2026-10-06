# LeLamp 硬件映射核查（2026-10-02）

> 结论：**仿真配置与实物标准配置一致，无需结构性改动**；本次修订为
> 可视化保真（灯头非对称化、连杆分色）与文档对齐。

## 1. 舵机映射（官方 lelamp_runtime / LeLamp-Extend-Board = 5× STS3215 总线舵机）

| 舵机 ID | 官方关节名 | 作用 | 仿真关节（URDF） | 限位（rad） |
|---|---|---|---|---|
| 1 | base_yaw | 底座水平旋转（左右转头） | joint1_yaw | [-5.021, +1.262] |
| 2 | base_pitch | 底座俯仰（抬头低头） | joint2_pitch | [-1.084, +2.057] |
| 3 | elbow_pitch | 肘部俯仰（大臂弯曲） | joint3_pitch | [-2.820, +0.322] |
| 4 | wrist_roll | 手腕旋转（灯头滚转） | joint4_roll | [-3.787, +2.497] |
| 5 | wrist_pitch | 手腕俯仰（灯头上下） | joint5_pitch | [-0.853, +2.288] |

- 限位数值与官方 robot.urdf 完全一致（阶段一 F5 修正时已核对，2026-10-02 复核不变）。
- 逻辑零位 = 各关节限位中点（`ZERO`），`MAX_DQ_PER_STEP = 0.06 rad @50Hz` 为实机安全速率。
- 语义一一对应：官方 base_pitch 控制下臂俯仰 = 仿真 joint2_pitch；elbow_pitch = joint3_pitch。
- 验证产物：`data/episodes/qc/verify_5dof.gif`——5 个舵机逐个扫掠，字幕标注 ID/官方名/仿真关节名/当前弧度。

## 2. 「GIF 里看不出 5 个电机」的原因与修复

原因有三，均为**可视化问题而非配置错误**：
1. 旧 URDF 灯头是**球体**——wrist_roll（ID 4）旋转球体在视觉上完全不可见；
2. 全部连杆同色（浅灰）——base_yaw（ID 1）带动下臂转动时难以分辨是哪一节在动；
3. 演示原语本身按语义驱动子集（点头只用 ID 5，摇头只用 ID 1）——这是设计使然。

修复（2026-10-02）：
- `assets/lelamp_5dof.urdf` 灯头改为**非对称三件套**（半球壳 + 偏心 LED 面板 + 顶部散热鳍），滚转/俯仰均肉眼可辨；
- 五节连杆分色（底座深灰 / j1 灰蓝 / 下臂蓝 / 上臂绿 / 腕节橙褐 / 灯头橙）；
- A 项目 vendor 副本（`sim_workbuddy/assets/`）已同步。

## 3. LED：SK6812 RGBW（暖白）

- 实物：**SK6812 内置 IC、RGBW 四通道（暖白 W）、单点高亮可编程灯条**。
- 仿真表示：episode 的 `led.rgbw: [r,g,b,w] 0-255` 四通道字段 + `pattern/freq_hz/intensity`（contract §3）；渲染时以 lamp_head link 变色近似（仅用 RGB 三通道，W 通道保留给实机驱动层）。
- 实机接入时注意：SK6812 RGBW 与 WS2812B 协议时序兼容但**数据帧为 32bit**（多一个 W 字节），驱动库需选 RGBW 模式；W 通道为暖白（约 3000K），适合 Joy/Love 类暖色表情的亮度基底。

## 4. 仿真 → 实机迁移检查单（未来 B2 遥操作/部署用）

| 项 | 仿真 | 实机注意 |
|---|---|---|
| 关节角单位 | rad | STS3215 为 0-4095 tick，需 rad→tick 标定（中位 2048） |
| 控制频率 | 50 Hz | 总线舵机建议 ≤50Hz 写命令，与仿真一致 |
| 速率限制 | 每情绪分层 1.0–2.2 rad/s + 加速度 25–80 rad/s²（v3.1 / 契约 §3.1） | 首次上电务必保留，防舵机扫齿/撞限位 |
| 轨迹格式 | (t, q0..q4) CSV/JSONL | 可直接重放；joint order 即 ID 1-5 |
| LED | rgbw 字段 + pattern | SK6812 RGBW 32bit 帧；pattern 在实机端展开 |
| 零位 | 限位中点 | 实机需先做单舵机零位标定再重放轨迹 |
| ⚠️ 供电电压 | 假设 12V 规格 | **首要实测项**：LeLamp Prerequisites 写「主供电 5V」——若舵机母线确为 5V，STS3215-C018 额定力矩将显著低于 10 kg·cm@12V，运动预算需再降；查 BOM + Extend-Board 电源轨后用万用表确认 |
| 力矩余量 | 仿真不做动力学 | base_pitch 下游质量 ~0.40 kg、质心 ~0.15–0.25 m → 静态保持力矩 0.6–1.0 N·m，已贴近 12V 额定力矩（0.98 N·m）；共情程序**避免长时间满前伸**；官方 robot.xml 执行器 forcerange=±3.35 N·m、kp=17.8 可对齐 |
| 结构强度 | — | PLA 15% 填充 + POM 塑料 horn：v3.1 的加速度预算（≤80 rad/s²）即结构保护预算，勿在实机上放开 |
| 情绪过渡 | 契约 §8（blend + LED crossfade） | 实机播放层必须实现 §8 过渡段，禁止直接切换 episode 首帧 |
