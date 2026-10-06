# Mapping Contract v1.2 — Shared Data Contract between Project A and Project B

> Status: **v1.2 2026-10-03**（QC review 后修订：§3 运动预算改为每情绪分层
> + 加速度上限、LED 亮度下限；新增 §7 idle 照明模式与 §8 情绪过渡规范；
> 依据 docs/qc_review_v3_analysis.md R1–R6，用户四项决策已确认）。
> v1.1 2026-10-02（§1 吸收用户五本能叙述）；v1.0 frozen 2026-09-30。
> This document — not code — is the single shared asset between
> `LeLampFlyBrainSimulation` (Project A, dataset-free bio-SNN core) and
> `LeLampEmpathy` (Project B, data-driven empathy). Project A's static
> six-state table (`core/states.py`) is the v0 reference; Project B evolves
> this contract into a data-driven schema. Changes require editing THIS file
> first, then updating both sides.

## 1. Emotion taxonomy (7 classes, perception side)

| Emotion | Valence | Arousal | Fly-brain instinct mapping | Core neural marker (analogy) | Lamp expression |
|---|---|---|---|---|---|
| Joy | + | mid | Sugar reward（糖分奖赏） | DA burst（多巴胺高爆发） | 暖黄光，轻微点头 |
| Love | + | low-mid | Courtship / social grooming（求偶/社交） | P1-like sustained DA | 暖粉光，平滑追随人脸/摇摆 |
| Angry | − | high | Aggression / territoriality（攻击/领地） | 5-HT surge（5-HT 飙升/强突触输出） | 刺眼红光，向前冲撞/警告 |
| Fear | − | high | Avoidance / escape（撤退/逃跑） | OA surge（章鱼胺暴增） | 闪烁红光，瞬间猛烈扭头远离 |
| Surprise | ± | spike | Startle reflex（惊跳反射） | Giant-fiber-like pulse（GF 瞬间脉冲） | 灯光骤变，机械颤抖抖动 |
| Sad | − | low | Hypoactivity / grooming（低动力/梳理） | suppressed tonus（电位受限/5-HT 抑制） | 暗蓝光，无精打采垂下灯头 |
| Neutral | 0 | low | Exploration / foraging（自主探索） | sparse baseline（基线稳定/脉冲稀疏） | 浅绿光，每隔片刻随机微调视线 |

### 1.1 五本能组（行为叙述层，2026-10-02 用户表述冻结）

上表的工程展开按五组本能组织（一组本能可覆盖多个情绪类）：

1. **警戒/惊跳本能（Arousal / Startle）**——突发巨响或视野巨大阴影触发
   Giant Fiber 通路，瞬间僵直或无方向疯狂逃逸。对齐 Surprise/Terror：
   大幅度快速扭头远离 + 高频微幅抖动，高频红闪。
2. **求偶/社交向往本能（Courtship / Social）**——DA 由 P1 神经元激活
   持续驱动跟随/振翅「唱歌」/绕圈。对齐 Love、温和 Joy：「粘人模式」，
   灯头平滑小幅左右摇摆（像跳舞）或追踪人脸，暖粉/暖黄光。
3. **探索/好奇本能（Exploration / Foraging）**——营养基线正常且无威胁时，
   OA+DA 微弱联合调控下的自主随机探测。对齐 Neutral：不死板呆立，每隔
   十几秒轻轻转动角度环顾房间，平稳绿/白光呼吸。
4. **攻击/防御本能（Aggression / Territoriality）**——资源竞争或同类入侵时
   特定脑区 5-HT 激增，触发抬足拍打/冲撞。对齐 Angry/Disgust：检测到主人
   愤怒大吼/拍桌时进入「防卫攻击状态」，灯头猛烈向前点头冲撞（警告），
   刺眼明红/橙光。
5. **梳理/清洁本能（Grooming）**——机械刺激或压力后恢复期的自我安抚
   （前足擦头/后足清翅）。对齐 Sad 过渡期/倾诉委屈：「同情与自我安抚」，
   灯头缓缓降低 + 微小高频摩擦动作（像抹眼泪），淡紫蓝光。

Rationale: the fly instinct column is an **engineering analogy**, not a
biological claim (same discipline as Project A's README honesty clause).

## 2. Internal state vector

```
gamma = [DA, OA, 5-HT]   each in [0, 1]
```

Project A consumes gamma as neuromodulation (leak / sensory gain / learning
gate). Project B uses gamma as an intermediate representational layer between
perceived emotion and expression parameters, keeping the two projects
comparable on the same episodes.

## 3. Expression contract (lamp side, per timestep)

Three output modalities, always produced together:

| Channel | Format | Notes |
|---|---|---|
| Pose | `q(t) ∈ R^5`, rad, 50 Hz | Joint order: yaw, pitch2, pitch3, roll4, pitch5 (per `assets/lelamp_5dof.urdf`). Must respect joint limits and the per-emotion motion budget below (v1.2). |
| Light (RGBW) | `{rgbw: [r,g,b,w] 0-255, pattern, freq_hz, intensity}` | SK6812 RGBW 4-channel; pattern ∈ {solid, breath, pulse, double_pulse, chase, strobe, fade}. **Brightness floor: intensity low ≥ 15 for every emotion** (v1.2 — the lamp never goes near-black; dim ≠ off). |
| Text/Speech | `{caption: str, tts_style: str, t_start, t_end}` | Floating-subtitle semantics + TTS prosody tag. **caption language must match scene language** (v1.2). |

### 3.1 Motion budget (v1.2, QC review R1)

Hardware basis: STS3215 no-load 4.71 rad/s @12V, rated torque 10 kg·cm;
PLA structure (15% infill). Budgets are hard QC gates per episode
(`quality.budget` records the values used; engine enforces via a causal
tracking limiter that mirrors the servo controller):

| Emotion tier | vmax | amax | Rationale |
|---|---|---|---|
| sad, love | 1.0 rad/s | 25 rad/s² | Comfort/soothing must be slow |
| neutral | 1.2 rad/s | 30 rad/s² | Calm exploration |
| joy | 1.5 rad/s | 40 rad/s² | Lively but gentle |
| angry | 1.8 rad/s | 60 rad/s² | Warning thrust, still capped |
| surprise, fear | 2.2 rad/s | 80 rad/s² | Startle is allowed to be fast |

Global default: MAX_DQ_PER_STEP = 0.030 rad/step @50 Hz (=1.5 rad/s),
MAX_DDQ_PER_STEP = 0.016 rad/step² (=40 rad/s²); inter-primitive settle
gap = 0.35 s. Long full-extension holds of base_pitch are discouraged
(static torque margin, see docs/hardware_mapping.md checklist).

## 4. Primitive vocabulary (ELEGNT-informed, parametric)

Kinesics (form): `nod`, `shake`, `tilt`, `lean`, `sway` (tail-wagging analog),
`tremble`, `gaze_shift`, `fold`, `scan`.
Proxemics (relation): `approach`, `avoid`, `follow`, `orient_to`.
Dynamics modifiers: amplitude, frequency, hesitation (pause count), attack
(acceleration profile), decay (settling).

Each primitive = parametric keyframe template → cubic-spline trajectory in
joint space. See `primitives/` for the reference implementation.

## 5. Episode record schema (dataset v0)

```json
{
  "id": "ep_0001",
  "human_input": {"text": "...", "emotion": "sad", "valence": -0.6,
                  "arousal": 0.2, "intensity": 0.7},
  "fly_instinct": "hypoactivity/grooming",
  "gamma": [0.1, 0.1, 0.8],
  "expression": {
    "primitives": [{"name": "dip", "params": {...}}, ...],
    "pose_seq": "episodes/ep_0001_pose.csv  (t, q0..q4)",
    "led": {"rgbw": [0, 10, 50, 5], "pattern": "breath",
            "freq_hz": 0.05, "intensity": [5, 15]},
    "caption": "I am here for you.",
    "tts_style": "soft-low"
  },
  "provenance": {"source": "manual|ELEGNT-derived|LLM-generated|teleop",
                 "source_url": "...or null", "license": "...",
                 "annotator": "...", "reviewed": false,
                 "collected_at": "2026-09-30"}
}
```

Hard rules (from user decision "尽量多爬" with mitigations):
1. `provenance` is **mandatory** on every record; records without it are rejected.
2. Unclear-license source material: publish **annotations + links only**; raw
   media never enters the repo or the GitHub dataset release.
3. Academic datasets and CC-licensed sources form the publishable subset.

## 6. Scale targets

- B1: 50–100 curated episodes (7 emotions × 8–15 variants), LLM pre-annotated
  + user spot-check 10–20% (100% review on mapping-matrix core entries).
- B2: teleoperation demos on the physical LeLamp (hardware already available).
- B3: end-to-end policy variant = Project A's behavior-cloning ablation
  baseline. One dataset serves both projects.

## 7. Idle / illumination mode (v1.2, QC review R4)

`idle` is the **8th mode and the runtime default** — NOT an emotion class and
not part of dataset episodes. The lamp is a lamp first: when no emotion
response is active, it provides illumination.

| Aspect | Spec |
|---|---|
| Trigger | No active emotion episode; also the hub state long after any episode ends |
| Light | Camera-ambient-adaptive brightness: dark room → supplement light; bright room → lower power. CCT warm (W channel dominant). Pattern: solid. Floor 15 %, ceiling per thermal limit |
| Motion | Breathing-level micro-motion only: sway/breathe amplitude ≤ 0.05 rad, speed ≤ 0.3 rad/s; NO large gestures (ELEGNT: expressive motion interferes with the primary lighting function — "remain steady while maintaining the light") |
| Exit | Any detected emotion event triggers a §8 transition into the response episode |

Evidence base: ELEGNT (2501.12493) treats illumination as the pure functional
task and reports user preference for stillness while the light serves its
function; dim-warm lighting literature supports comfort (see
docs/qc_review_v3_analysis.md §2-problem-2a references).

## 8. Emotion transition spec (v1.2, QC review R6)

Emotion switches NEVER hard-cut. Between the end pose of episode A and the
start pose of episode B the runtime/dataset inserts a generated transition
segment (`tools/make_transition.py`):

1. **Pose blend**: cosine-eased spline from A's end pose to B's start pose;
   duration = `max(t_min, dq_max / rate)` with rate = 1.0 rad/s, t_min = 0.8 s.
2. **Urgency exception**: targets fear/angry use rate = 2.2 rad/s,
   t_min = 0.4 s (a startled lamp is allowed to snap).
3. **No forced return-to-home**: blending goes direct A→B; a home swing reads
   as an "emotion reset" and breaks empathic continuity.
4. **LED crossfade**: 0.5 s linear lerp of rgbw + intensity; pattern switches
   at the midpoint (strobe-class patterns drop to solid before fading).
5. **Text/speech**: captions do not overlap; the new caption starts when the
   pose blend completes.

## 9. A→B parametric escape mapping（P1, 2026-10-03）

A 侧检出信号 → B 侧逃避行为的**连续**映射（取代离散触发）。参考实现：
`LeLampFlyBrainSimulation/tools/ab_parametric_escape.py`。

**输入**（每条件，A 侧 DN 群体率检出器 + N≥4 个噪声种子）：

| 信号 | 定义 |
|---|---|
| `p_det` | 种子中成功检出的比例（检测鲁棒性=置信度） |
| `ttc_det` | 检出种子的中位"距碰撞时间"（秒，越大越从容） |
| `az_cls` | 威胁方向 3 类 {左, 正前, 右}——**P1.5 起由 DN 首超特征解码**，不用真值 |

> 实测注记：单 trial 的 DN 峰值超出量在所有条件下饱和 ≈3.6σ（无分辨力），
> 因此置信度必须用**跨种子鲁棒性**而非单次幅值。
> 网格实测（33 条件×4 种子，2026-10-03 v2 修正版）：flywire 臂 p_det=1.00
> 全条件、u 由时间压力分级（0.63–1.00）；rewired 对照臂 p_det=0.00 全条件
> （z-max 2.92 < 3σ 阈值，与 D2 AUC 判决一致）→ u=0 保持 idle。
> v2 勘误：v1 曾把弧度当度传入编码器，"±45° 方位"实为正前方；修正后
> 方位对检测有小但系统的影响（慢速 loom 侧向检出略早，u 偏移 ≤0.10）。
>
> **P1.5 方向通道（2026-10-03）**：`az_cls` = DN 群体首超特征（均值首超
> 基线+1σ 时刻起 30ms 窗、基线减除、和归一化模式）的最近质心 3 类解码，
> 逐种子解码后多数投票；训练/测试种子分离。泛化准确率 flywire 0.909 /
> rewired 1.000（20 条件×4 种子）；RF 质心（传感器级）为工程兜底
> （MAE 0.4°）。参考实现：`LeLampFlyBrainSimulation/tools/p15_azimuth_decode.py`。

**映射**：

```
u_time  = clip(1 - (ttc_det - 0.02)/0.18, 0, 1)   # 时间压力（主，τ 生态学）
u_conf  = clip((p_det - 0.25)/0.75, 0, 1)         # 置信度（辅）
u       = 0.6*u_time + 0.4*u_conf                 # 急迫度 ∈ [0,1]

avoid_amp  = 0.25 + 0.45 u
yaw_target = -az_cls * (0.30 + 0.70 u)            # 远离威胁；az_cls=0 默认左转
tremble    = (0.02+0.02u rad, 4+5u Hz, 0.6+0.8u s)
strobe     = 2+7u Hz（红）
速度预算   = lerp(0.6 → 2.2 rad/s, u)（不超过 §3.1 fear 档）
触发延迟   = 检出后 100ms（工程假设）
未检出     → u=0，保持 idle，不产生逃避
```

**硬规则**：任何 u 下轨迹不得超过 §3.1 fear 预算（2.2 rad/s / 80 rad/s²）；
方向必须远离威胁方位（镜像对称）；映射只依赖 A 侧输出信号，不接触刺激真值
（P1.5 后方向通道亦由 DN 群体解码，全链路无真值）。
