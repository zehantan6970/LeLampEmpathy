# 多模态共情数据集策略（Dataset Strategy v0.1）

> 冻结日期：2026-10-03 · 状态：思路冻结，待 P1 完成后按 §5 顺序动工
> 触发：用户指出「网络上没有 5-DOF 台灯动作数据」的判断需要核查（ELEGNT 论文、LeLamp 视频、人际共情视频三条线索）

---

## 1. 核查结论

### 1.1 ELEGNT（arXiv:2501.12493）—— LeLamp 的源头论文

Apple（Yuhan Hu 等，2025-01）：*ELEGNT: Expressive and Functional Movement Design for Non-anthropomorphic Robot*。

- **图 5** = 表达性运动**设计空间示意图**：kinesics（身体运动：姿态原语=点头/摇头/低头/"摇尾巴"/"坐下"；时间原语=速度/停顿/顿挫）+ proxemics（空间关系：静态=注视/距离/朝向；动态=接近/回避/方向切换）。**无关节角数值、无轨迹、无关键帧参数**。
- **图 6** = 交互场景**四象限图**（功能↔社交 × 主动↔被动），与运动参数无关。
- 论文原文明确声明：*"Rather than offering an exhaustive list of design parameters…"* —— **不提供参数化原语库**。
- **无代码/数据开源**（v1 全文无 GitHub 链接）；唯一补充材料是用户研究视频。硬件为 WidowX 250S（6-DOF），非 LeLamp 的 5×STS3215。
- **对本项目的真实价值**（引用依据，非数据源）：
  1. 原语分类学背书——我方 7 情绪库可对齐 kinesics/proxemics 分类框架；
  2. 核心实证：expression-driven 全面优于 function-driven（M=56.16 vs 28.77，p<0.0001，N=21），**社交任务中差异尤甚**——直接支撑共情映射路线的立项逻辑；
  3. 六个评测场景（摄影灯光/投影辅助/故障指示/提醒喝水/社交对话/播放音乐）可作我方评测域设计参考。

### 1.2 LeLamp 官方生态

- `humancomputerlab/LeLamp`（GPL-3.0，硬件/CAD/BOM）+ `lelamp_runtime`（控制软件，**注意：截至 2026-09 上游无 LICENSE 文件，引用其代码前需复核权利状态**）。
- runtime 提供 **record / replay**：手可掰动舵机示教并回放 → **官方没有动作数据集，但示教自产是一等公民路径**；社区 fork 中含 simulation 目录与演示视频。

### 1.3 对此前判断的修正

原表述「网络上没有 5-DOF 台灯的动作数据」**修正**为：

| 判断 | 状态 |
|---|---|
| 无现成**参数化**台灯动作库（ELEGNT 未开源数值） | ✅ 仍成立 |
| 数据不可获得 | ❌ 修正——三条可得路径：(a) 示教自产（record/replay）；(b) 人体动捕/视频**重定向**到 5 舵机；(c) 论文补充视频 + 社区视频作定性参考 |

---

## 2. 对外部方案（AI 生成调研文本）的事实核查

**已核实真实存在**：BEAT（ECCV 2022，76h / 30 人 / **8 情绪** / 4 语言，动捕+面部+音频+文本，需注册，pantomatrix.github.io/BEAT）✅；IEMOCAP（双人动捕对话金标准，需签数据协议）✅；MELD（《老友记》13k 切片）✅；CMU-MOSEI / MOSI ✅；M3ED（中文影视多模态对话）✅；EMAGE / DiffGesture / SadTalker / LivePortrait / ChatTTS ✅。

**未能核实（疑似幻觉或误名，引用/依赖前必须重新查证）**：`GeneGesture`、`ShowMeTheBody (SMTB)`、`Ch-LiTS`。——检索零结果，**禁止写入论文或代码依赖**。

**硬件事实错误**：外部方案 A 假设「电机 5 = 夹爪/手掌张合」——LeLamp **无夹爪**。以我方 `configs/joints.py` 为准：ID4 = wrist_roll（翻掌：掌心向上=接纳倾听 / 掌心向下=稳定安抚），ID5 = wrist_pitch（微动=呼吸感）。外部文本第二段已自行修正，以修正版为准。

**仿真栈差异**：外部给的 MuJoCo position-actuator 代码仅供参考思路；本栈为自研 URDF + Pillow 渲染（本机 matplotlib/BLAS 硬崩溃），重定向输出应对齐我方 episode 的 `response.trajectory`（10Hz × 5 关节弧度）格式，不引入 MuJoCo 依赖。

---

## 3. 分层数据集策略

```
Layer 1 文本层     EmpatheticDialogues (CC-BY-4.0) ──→ scene_text_en + 32→7 情绪归并
                   GoEmotions (Apache-2.0) ──────────→ valence/arousal 回归监督
                   DailyDialog（标签最近但 CC BY-NC-SA 传染）──→ 仅作内部评测，不再发布
Layer 2 动作源层   BEAT 动捕（8 情绪，截手臂链）──────→ 重定向到 5 舵机轨迹
                   （后期）共情视频挖掘：YouTube therapy session simulation /
                   comforting movie scenes（如 Good Will Hunting "It's not your fault"）/
                   ASMR comfort roleplay；Bilibili 心理咨询模拟/共情演技
Layer 3 设计验证层 ELEGNT 原语分类 + 六场景 ──────────→ 我方 7 情绪库与评测域的对标
                   LeLamp record/replay 示教 ──────────→ 实机金标准 episode（硬件到位后）
```

原则：**文本学「何时共情、共情什么」，动捕/视频学「怎么动」，ELEGNT 背书「为什么这样动有效」**。

## 4. 人体 → 5 舵机重定向管线（Layer 2 核心）

```
人体手臂链（BEAT mocap 或 MediaPipe 视频估计）
  → 提取：手腕 3D 位置 (X,Y,Z) + 手掌平面法向量 (pitch, roll)
  → 映射：base_yaw   = 水平方位角 atan2(Y,X)
          base_pitch + elbow_pitch = 2 连杆 IK（前伸/上下抚动）
          wrist_roll  = 翻掌角（向上=接纳 / 向下=安抚）
          wrist_pitch = 掌俯仰（微动/呼吸感）
  → 情感滤波：一阶低通（α≈0.05–0.15）+ 加速度限幅（安慰动作忌 jerk）
  → 安全限幅：前伸工作空间硬约束（防「打」到用户）
  → 输出：10Hz × 5 关节弧度序列 = episode response.trajectory 原生格式
```

该管线使「用真实人类共情动作训练/测试映射」可行，且输出与 mapping contract v1.1 原生兼容。手势先于语音 100–200ms（人类习惯）可作为未来语音同步规则。

## 5. 实施顺序（并入 P2，P1 完成后动工）

| 步骤 | 内容 | 产出 |
|---|---|---|
| P2-a | episode 人工抽检 20% | qc_report 更新 |
| P2-b | EmpatheticDialogues 下载脚本 + 32→7 归并 + `scene_text_en` 回填 v2 | episodes_v3.jsonl |
| P2-c | BEAT 注册下载 + 手臂链重定向 PoC（先 1 情绪 × 10 条） | retarget PoC + GIF 对比 |
| P2-d | 共情视频挖掘管线（视 PoC 结果决定是否投入） | 待定 |

**许可证纪律**：第三方数据一律「下载脚本 + 处理子集 + ATTRIBUTION 文件」，**不 vendor 原始数据**进 GPL-3.0 仓库；DailyDialog 类 NC-SA 数据不进发布物。

---

## 6. P0-data：真实数据 500–1000 条获取方案（v0.2 ✅ 已执行 2026-10-03）

> 背景：用户决定 GitHub push 暂缓（须先确认最终版本 + env 风险核查），数据获取优先于 P1。
> **env 扫描（2026-10-03 已做，只读）**：LeLampEmpathy 与 LeLampFlyBrainSimulation 均无 .env / 密钥文件 / 硬编码 token；A 仓库 README 中 DEEPSEEK_API_KEY 等仅为占位注释，代码经 `os.getenv` 读取 → **扫描通过**，push 前仅剩「最终版本确认」一项。

### 6.0 执行结果（Q1–Q4 全部确认后动工，当日完成）

- **产出 `data/episodes/episodes_v3.jsonl`：1,120 条**（7 类 × 160，train 896 / test 224，conversation 级分层），全部 `limits_ok` 通过。
- 真实文本 + 真实标签（ED 23,062 conversations 去重池），V/A/D 用 NRC VAD v1（覆盖率 ~0.34，52 条回退规则质心）。
- **发现并修复两个实现问题**：① ED 的 `speaker_idx` 是工人 ID 非 0/1 角色标记（误过滤致池缩到 705，已改）；② 契约第 7 类名为 **neutral**（探索本能），anticipating→neutral 走响应式手势版 curious 程序。
- 文档：`docs/dataset_card.md`（格式+描述，用户要求）、`data/external/ATTRIBUTION.md`、`data/external/` 已入 .gitignore（不 vendor）。
- 已知偏差：NRC VAD 句均值有正向基线偏移（类间排序正确），dataset card §5 已声明。
- 留待 v3.1：scene_text 中文回译、QC 20 条人工复核翻 reviewed 标志、可选 V/A 去基线。

### 6.1 目标

P1 动工前，把 episode 数据从「全合成」升级为「**真实场景文本 + 真实情绪标签 + 契约生成轨迹**」，规模 500–1000 条（目标 ~700–1000）。

### 6.2 范围决策（为什么文本层先行）

| 源 | 获取门槛 | 结论 |
|---|---|---|
| EmpatheticDialogues | CC-BY-4.0，HF/ParlAI 直接下载 | ✅ 最快路径，P0-data 主源 |
| BEAT | 需注册审批（数天） | 注册动作并行发起，数据到手后走 §4 重定向（P2-c） |
| IEMOCAP | 需签数据协议 | 同上，并行发起 |

因此本批 500–1000 条 = 真实 scene_text + 真实标签 + **contract v1.1 生成轨迹（轨迹仍为合成，诚实声明）**；真实动捕轨迹属下一阶段。

### 6.3 执行步骤

1. **下载与归并**：HF `empathetic_dialogues`（25k conversations / 32 情绪 / 每条带 situation 场景句）→ 按 §6.5 归并表映射到 7 类。
2. **采样与切分**：以 conversation 为单位去重（同一对话不跨切分）；每类上限 ~150 条、小类全取；分层 80/20 train/test。
3. **生成 episodes_v3.jsonl**：
   - `scene_text_en` = ED situation 原句（英文优先，利 GitHub 发布；中文 scene_text 后置翻译或留空）
   - `annotation.method = "ed_situation_v1"`，`reviewed = false`
   - V/A：可选 NRC VAD 词典对 situation 句打分，替代 rule_based_v1（待定，见 §6.6-Q3）
   - `response` 轨迹沿用现有 gen_episodes 管线（contract v1.1）
4. **质检**：随机抽 20 条人工复核，qc 摘要入库。

### 6.4 产出

`data/episodes/episodes_v3.jsonl` + `tools/build_episodes_v3.py`（下载/归并/采样脚本）+ qc 摘要 + ATTRIBUTION 文件。**不 vendor ED 原始数据**。

### 6.5 32→7 归并表（草案，待确认）

| 我方 7 类 | ← EmpatheticDialogues 32 标签 | 估可采样量 |
|---|---|---|
| joy | joyful, excited, content, proud, hopeful, confident, prepared | 充足 |
| sad | sad, devastated, lonely, disappointed, guilty, ashamed, nostalgic, embarrassed | 充足 |
| angry | angry, furious, annoyed, disgusted, jealous | 充足 |
| fear | afraid, anxious, terrified, apprehensive | 充足 |
| love | loving, caring, grateful, faithful, trusting, sentimental | 中等 |
| surprise | surprised, impressed | 偏少 |
| curious | anticipating（**低置信**） | ⚠️ 严重不足 |

### 6.6 待确认问题（Q1–Q4）

- **Q1 归并表**：§6.5 的归类是否认可？（尤其 jealous→angry、nostalgic/embarrassed→sad、impressed→surprise）
- **Q2 curious 缺口**：ED 无"好奇"类。(a) curious 维持规则合成、真实数据仅 6 类；(b) anticipating 归入 curious 并打低置信标记；(c) curious 从别处补源（后期）。倾向 (a)+(b) 混合？
- **Q3 V/A 方案**：(a) 保留 rule_based_v1；(b) 引入 NRC VAD 词典按 situation 句打分（更真实，多一步下载）。倾向 (b)？
- **Q4 规模上限**：每类 ~150 / 总量 ~1000 是否合适？还是先 500 条轻量验证管线？
