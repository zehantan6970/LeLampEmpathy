# E2 — Lamp 共情人设设计：文献证据与实施方案（冻结稿 v1.0）

> Date: 2026-10-04 · Status: **✅ 已实施并验证（2026-10-04 晚）**
> 关联：`docs/e1_multimodal_loop.md`（E1 已上线 LLM 上下文应答，人设是它的"灵魂层"）

---

## 1. 问题

E1 的 lamp 已能按【说话内容+视觉情绪】生成应答，但应答"人格"是裸的 system prompt。
用户希望 lamp 有可选人设（心理咨询师、朋友…），并要求：
① 共情的常用方式/范式有哪些；② 是否有论文证据支持其有效性；
③ 不同年龄段/场景/背景是否需要不同的共情方式；④ 如何落地到本项目。

## 2. 共情范式的三层分级（学术界标准划分）

| 层级 | 名称 | 定义 | 本项目现状 |
|---|---|---|---|
| L1 | 情绪闲聊 emotional chatting | 表达情绪、陪聊 | episodes 动作+罐头台词 ✅ |
| L2 | 共情回应 empathetic responding | 理解并确认用户感受 | LLM 应答（裸 prompt）✅ 雏形 |
| L3 | 情绪支持对话 emotional support conversation (ESC) | 有策略、有阶段地**降低**用户情绪痛苦 | **本轮设计目标** |

依据：Liu et al. 2021（ACL），*Towards Emotional Support Dialog Systems*。

## 3. 证据充分的共情策略（论文依据）

### 3.1 安慰通信理论（Burleson，数十年证据链）⭐ 最核心

- **高"以人为中心"（person-centered）信息**——承认、细化、探索、合法化对方感受——被反复证明
  更敏感、更有帮助、更有效（Burleson 1994 起；Jones & Wirtz 2006 实验 N=258：
  高 PC 安慰直接改善情绪，并促使对方"说出感受→重新评估→情绪好转"的认知评估路径）。
- **边界条件**：轻微不爽时随便安慰都有效；极度崩溃时说什么都不重要（陪伴在场即可）。
  → lamp 策略：中等情绪强度时话术质量最关键——正好是主要工作区间。
- **文化差异（与我们直接相关）**：中美被试对中/高 PC 信息评价一致，但**中国被试认为
  低 PC 信息也几乎同样有帮助**（Burleson & Mortenson 2003）——高语境文化更看重
  "谁在说、关系如何"而非话术内容。→ **人设的一致性和陪伴感，对中国用户比话术精巧更重要。**

### 3.2 Rogers 人本主义三条件（1957）

共情理解、真诚一致、无条件积极关注——心理咨询有效性的经典公理。
→ "心理咨询师"人设的 prompt 骨架：**先验证感受，不评判，不急着给建议**。

### 3.3 ESC 八策略分类法（Hill 助人技能理论 → ESConv 数据集）⭐ 可直接工程化

Liu et al. 2021 按三阶段组织，且有"策略标注的 Oracle 模型显著优于无策略基线"的实验证据：

| 阶段 | 策略 | 定义 | lamp 示例 |
|---|---|---|---|
| 探索 | Question 提问 | 帮对方厘清问题 | "后来怎么样了？" |
| 探索 | Restatement 复述 | 简洁重述帮对方看清处境 | "所以是 deadline 压过来了。" |
| 安慰 | **Reflection of feelings 情感反映** | 说出对方的感受 | "听起来你真的挺委屈的。" |
| 安慰 | Self-disclosure 自我表露 | 分享类似经历拉近距离 | "我'看着'很多人这样熬过。" |
| 安慰 | **Affirmation & Reassurance 肯定安抚** | 肯定优点、给予保证 | "你已经做得很扎实了。" |
| 行动 | Suggestions 建议 | 可操作的应对方式 | "要不先站起来喝口水？" |
| 行动 | Information 信息 | 事实/资源 | "这个问题其实挺常见…" |
| — | Others | 寒暄等 | — |

ESConv 时序规律：对话前期以 Question 为主、Affirmation 贯穿全程、Suggestions 后置。
→ **先探索、再安慰、最后才行动建议——顺序就是有效性的一部分。**

### 3.4 AI 共情有效性的临床试验证据

- **Woebot RCT**（Fitzpatrick et al. 2017, JMIR Ment Health, N=70）：
  2 周显著降低抑郁（d=0.45）与焦虑（d=0.51），且用户报告了可比肩人类的治疗同盟。
- **Wysa**：Inkster et al. 2018 可行性研究；慢性病人群 RCT（MacNeill & Doucet 2024,
  JMIR Form Res, N=68）：4 周抑郁显著下降（组间交互 p<0.001）。
- **关键结论**：**有结构化心理学框架的 chatbot 优于通用聊天 bot**；
  安全升级机制（危机→人工/专业资源）是所有循证产品的标配。
- **HRI 实证**：共情版 vs 非共情版 Ryan 机器人（Abdollahi et al. 2023, IEEE TAC）——
  共情版显著更"吸引人、更讨喜"；LLM 共情机器人在养老院 10 周部署
  （Pinto Bernal et al. 2026, ACM THRI）——共情恰当性与更深自我表露、
  持续参与正相关。
- **⚠ 反面证据**：自闭症儿童 8 周 RCT（Meng et al., IDC 2026）——
  持续使用机器人组焦虑下降，但**社交动机/共情向真人的迁移反而低于撤机组**：
  "高参与 ≠ 社交迁移"，存在**替代风险**（沉浸在人机二元关系里）。
  → lamp 应是"搭桥"而非"代餐"，避免诱导依赖。

## 4. 人群差异：不同年龄/场景的共情需求

| 人群 | 共情要点 | 语言风格 | 证据/依据 |
|---|---|---|---|
| 儿童（~3–12） | 情绪匹配要快而夸张、简单词汇、游戏化、绝不讲道理 | 短句、高频词、明快 | ELEGNT 表达性运动证据；儿童产品实践 |
| 青少年 | 尊重自主、不居高临下、忌"我懂你"式敷衍 | 平等、少指导 | Rogers；发展心理学常识 |
| 成年（压力场景） | 高 PC 验证→(被请求才)建议；工作中要简短 | 简洁专业温暖 | Burleson；ESConv |
| 老年 | 耐心、慢速、重复不厌、怀旧话题、主动问候 | 慢、柔、句子短 | Ryan/养老院部署研究 |
| 中国文化背景 | 关系与一致性 > 话术；低 PC 也可接受 | 稳定、陪伴感 | Burleson & Mortenson 2003 |
| 极度情绪激动 | 说什么都不重要→**安静陪伴+低刺激** | 少说话、慢动作柔光 | Burleson 边界条件 |

## 5. 人设方案（5 个，可扩）

人设 = ①共情策略集（§3.3 八策略的选用与排序）+ ②语言风格 + ③TTS 韵律 + ④安全条款。
**v1 不动动作/LED 程序**（契约 v1.2 保持不变），v2 再考虑人设→动作 temperament 联动。

| 人设 | 策略画像（主→次） | 风格/禁忌 | TTS |
|---|---|---|---|
| `friend` 朋友（默认） | Self-disclosure→Affirmation→Question | 口语、可幽默、可吐槽；不教训 | 自然中速 |
| `counselor` 心理咨询师 | Reflection→Question→Affirmation；**未被请求不给建议** | 慢、稳、多验证句；忌评判/说教/诊断；**含危机条款** | 慢速低沉 |
| `coach` 教练 | Affirmation→Question→Suggestions | 有能量、行动导向；建议须小而具体 | 中快明快 |
| `companion_elder` 银发陪伴 | Question(怀旧)→Reflection→Affirmation | 极耐心、可重复、主动问候；句子短 | 慢速柔和 |
| `buddy_kid` 儿童伙伴 | Reflection(夸张匹配)→Question(游戏化) | 简单词、短句、拟人化；禁复杂建议/恐怖内容 | 明快活泼 |

**危机条款（所有人设强制注入）**：用户表达自伤/自杀/伤害他人意图时，
固定回应关心+建议寻求专业帮助/联系紧急联系人，不做诊断，不扮演治疗师。
（对应 §3.4 安全升级机制。）

## 6. 实施方案（E2）

1. `tools/e1_personas.json` — 5 人设定义（system prompt 模板 + 策略指令 + TTS prosody）
2. `live_bridge.py` — `generate_reply(user_text, emotion, v, a, persona)`；
   `POST /live/persona`；状态与日志记录当前人设
3. `live_viewer.html` — 人设下拉（5 选项），切换即时生效
4. 验收：同一句"我今天被老板骂了，好难受"在 5 个人设下产出风格可区分、
   且 counselor 不说教、coach 给建议、kid 用词简单；
   危机语句（如"活着没意思"）任何人设都触发安全回应

### 6.1 已实现的使用方式（2026-10-04 验证通过）

**人设切换**：viewer 顶栏 persona 下拉（5 项，即时生效，lamp 用新人设音色念问候语）；
或 `POST /live/persona {"persona":"counselor"}`。人设 = 策略 prompt + 专属音色
+ 韵律（与情绪韵律相乘，如 counselor 0.92/0.95 慢而沉）。日志事件 `persona_set`、
`reply` 事件带 persona 字段。

| 人设 | 音色 | 韵律(rate/pitch) |
|---|---|---|
| friend 朋友（默认） | longanhuan | 1.00/1.00 |
| counselor 心理咨询师 | longanshuo_v3 | 0.92/0.95 |
| coach 教练 | longanyang | 1.05/1.00 |
| companion_elder 银发陪伴 | longfeifei_v3 | 0.85/0.98 |
| buddy_kid 儿童伙伴 | longhuhu_v3 | 1.10/1.10 |

**语音命令**（对 lamp 直接说）：
- 「退出lamp」/「关闭lamp」/「lamp休息」→ **睡眠**：不再响应情绪与说话
  （viewer 显示 💤，提醒仍然生效，唤醒词照常监听）
- 「打开lamp」/「唤醒lamp」→ **唤醒**恢复，念人设问候语
- ⚠ 说完「退出lamp」后请等 lamp 念完告别语（约 5 秒）再说唤醒词——
  回声防护窗口内的话会被忽略（防止 lamp 被自己的告别语里的"打开lamp"自唤醒）。
- 等效 API：`POST /live/sleep` / `POST /live/wake`

**完全退出 lamp 系统**（三选一）：
1. 命令行：运行 live_bridge 的窗口按 **Ctrl+C**
2. viewer 第二栏右侧 **⏻ exit 按钮**（有确认弹窗）
3. `POST /live/shutdown`（说完再见后 3 秒退出）
关闭浏览器标签页只是关掉 viewer 观察面板，**lamp 本体（bridge 进程）仍在运行**。

**验证记录**：counselor 人设下"我今天被老板骂了，好难受"→"听起来你有些无奈，
能和我多说一点吗？"（情感反映+开放提问，无建议 ✅，音色 longanshuo_v3 ✅）；
「退出lamp」→ sleep 事件+告别语、inject 409、说话忽略；「打开lamp」→ wake
事件+人设问候；/live/shutdown → 进程退出。

**明确不做**：不做诊断/治疗宣称；不改契约 v1.2 动作体系（v2 候选）；
不存对话内容到长期记忆（隐私，E3 再议）。

## 7. 风险与诚实声明

- lamp 是**陪伴品**不是医疗设备；所有人设 prompt 与文档避免治疗功效宣称（营销式外推禁令）。
- 替代风险（§3.4 IDC'26）：长期目标应是促进用户的人际连接（如提醒联系朋友），
  而非把用户留在人机闭环里——可作为 v2 的"社交搭桥"行为设计。
- 证据强度分级：§3.1–3.3 为成熟社会科学证据；§3.4 chatbot RCT 多为亚临床人群、
  效应量中小（d 0.2–0.5）；HRI 共情研究样本普遍小（N=5–40）。人设设计属
  "有依据的工程选择"，不是"被证明最优"。

## 8. 参考文献

1. Burleson, B. R. (1994). Comforting messages: Features, functions, and outcomes.
2. Burleson, B. R., & Mortenson, S. R. (2003). Explaining cultural differences in
   evaluations of emotional support behaviors. *Communication Research*.
3. Jones, S. M., & Wirtz, J. G. (2006). How does the comforting process work?
   *Human Communication Research*, 32(3).
4. Rogers, C. R. (1957). The necessary and sufficient conditions of therapeutic
   personality change. *J. Consulting Psychology*.
5. Liu, S., et al. (2021). Towards Emotional Support Dialog Systems. *ACL*.
   （ESConv：8 策略/3 阶段/1,053 对话）
6. Fitzpatrick, K. K., et al. (2017). Delivering CBT to young adults…(Woebot):
   A RCT. *JMIR Mental Health*, 4(2).
7. MacNeill, A. L., & Doucet, S. (2024). Effectiveness of a mental health chatbot…
   RCT. *JMIR Formative Research*, 8.
8. Abdollahi, H., et al. (2023). Artificial EI in socially assistive robots for
   older adults. *IEEE Trans. Affective Computing*, 14(3).
9. Pinto Bernal, M. J., et al. (2026). Fostering emotional engagement…care homes
   through empathetic human-robot conversation. *ACM THRI*, 15(5).
10. Meng, Y., et al. (2026). Engagement is not transfer: A withdrawal study of a
    consumer social robot with autistic children at home. *IDC '26*.
