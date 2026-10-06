# LeLampEmpathy 情绪姿态目录（2026-10-02 修订版）

> 单一权威：`docs/mapping_contract.md` v1.1 §1。本目录 = 每类情绪的
> 可演示说明（生物学原理 → 情绪对齐 → 台灯表现 → 程序实现 → 演示）。
> 全表演示：`data/episodes/qc/demo_emotions.gif`（7 段连续播放）；
> 响应式手势演示：`demo_gestures.gif`（点头/摇头/好奇/惊吓）；
> 5 舵机验证：`verify_5dof.gif`。

## 0. 体系核查：项目从最开始到现在对应人的几种情绪姿态？

**两层结构，从冻结起未变：**

| 层 | 位置 | 数量 | 内容 | 角色 |
|---|---|---|---|---|
| 果蝇内部状态层 | 项目 A `core/states.py` | **6 状态** | Emotional_Comfort / Fear_Arousal / Approach_Reward / Vigilance_Defense / Exploration_Seeking / Grooming_Rest | T1 训练真值 + γ 先验（继承 gemini 设计） |
| 人类情绪分类层 | 项目 B `mapping_contract` §1 + `primitives/library.py` + 数据集 | **7 情绪** | joy / love / angry / fear / surprise / sad / neutral | 共情感知-表达分类法 |

两侧对照：Approach_Reward≈joy、Emotional_Comfort≈love、Fear_Arousal≈fear/surprise、
Exploration_Seeking≈neutral、Grooming_Rest≈sad、Vigilance_Defense≈警戒（介于
neutral 与 angry 之间）。**A 侧 6 状态没有独立的 angry**（攻击/防御在果蝇侧由
5-HT 通路表达，A 侧未单设真值状态）——这是已知的覆盖差异，B 侧 7 类为完整集。
2026-10-02 用户提供的「五本能 × 七情绪」表述已冻结进 contract v1.1 §1.1，
library.py 现有 7 程序与之逐条核对**全部一致**（见下表「程序」列）。

## 1. 警戒/惊跳本能（Arousal / Startle）→ Surprise / Fear

- **生物学**：突发巨响或视野巨大阴影 → Giant Fiber 快通路 → 瞬间僵直或无方向疯狂逃逸。
- **Surprise**：startle 急动（p3+p5，0.25s 高 attack）→ 僵直 hold → 高频微颤 → 回正扫视；白灯 4Hz 骤变爆闪。台词「Whoa! What was that?」
- **Fear**：avoid 猛烈后撤（0.4s）→ 9Hz 震颤 → 逃离注视；**高频红闪**（9Hz strobe）。台词「Watch out!」
- 程序：`library.EMOTIONS["surprise"/"fear"]`；响应式手势版 `startle`（扭头远离+红闪）。

## 2. 求偶/社交向往本能（Courtship / Social）→ Love（及温和 Joy）

- **生物学**：DA 由 P1 神经元激活持续驱动跟随/振翅「唱歌」/绕圈。
- **Love**：lean 温柔前倾 → 小幅度 sway 摇摆（像跳舞）→ 慢呼吸；暖粉光 0.2Hz 呼吸。台词「I am here for you.」
- 程序：`EMOTIONS["love"]`。人脸追踪版属 B2（实机视觉接入后）。

## 3. 探索/好奇本能（Exploration / Foraging）→ Neutral

- **生物学**：营养基线正常且无威胁时，OA+DA 微弱联合调控下的自主随机探测。
- **Neutral**：scan 缓慢左右扫视（6s 周期）→ 呼吸 → 视线微调；浅绿光。台词「Exploring surroundings.」
- 程序：`EMOTIONS["neutral"]`；响应式手势版 `curious`（侧头注视=roll+yaw）。

## 4. 攻击/防御本能（Aggression / Territoriality）→ Angry / Disgust

- **生物学**：资源竞争/同类入侵 → 特定脑区 5-HT 激增 → 抬足拍打/冲撞。
- **Angry**：高 attack 前冲 lean → 快速重 nod（警告冲撞）→ 短 shake；刺眼纯红光 solid。台词「Hey. Back off a little.」
- 程序：`EMOTIONS["angry"]`。

## 5. 梳理/清洁本能（Grooming）→ Sad（过渡期/倾诉委屈）

- **生物学**：机械刺激或压力后恢复期的自我安抚（前足擦头/后足清翅）。
- **Sad**（R8 重设计 2026-10-03）：dip 缓慢下沉（去程=回程同速，raised-cosine 两端零速）
  → sway_gentle 左右对称慢摆 → 二次 dip → 极慢呼吸；暗暖紫 0.1Hz 慢呼吸。台词「I feel you... take your time.」
  设计依据：安慰 = 慢、沉、对称（用户 QC：旧 fold 回程过快、groom 腕部 3.5Hz 微颤读作开心/好奇，已移除）。
- 程序：`EMOTIONS["sad"]`。

## 6. 糖分奖赏本能（Reward）→ Joy

- **生物学**：「吃到糖」→ DA 高爆发 → 趋近与活跃。
- **Joy**：轻快点头 ×2 → 欢快 sway → 再点头；暖黄光 double_pulse。台词「Glad to interact with you!」
- 程序：`EMOTIONS["joy"]`；响应式手势版 `nod`（肯定）/`shake`（否定）为社交信号层补充。

## 7. γ 向量与数据

每类情绪的 γ=[DA,OA,5-HT]、RGBW、pattern、valence/arousal 初标均随 episode
记录（`episodes_v2.jsonl`，102 条：7 情绪 × 10 场景 + 4 手势 × 8 措辞，
全部限位合规、三层质检通过）。
