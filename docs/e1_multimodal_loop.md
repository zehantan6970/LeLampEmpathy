# E1 — 多模态共情闭环设计文档（冻结稿 v1.0）

> Date: 2026-10-04 · Status: **E1.0–E1.4 已实现（2026-10-04），待用户实测验收**
> 实现状态：✅ E1.0 环境（5/5 PASS）· ✅ E1.1 视觉情绪（qwen-vl-max，延迟 ~1.5–1.8s）
> ✅ E1.2 响应引擎（7 情绪 demo 全合规）· ✅ E1.3 bridge+viewer（端点冒烟全过）
> ✅ E1.4 TTS（CosyVoice-v3-Flash 947–1073ms，音色映射生效）
> 运行：`.venv/Scripts/python.exe tools/live_bridge.py` → http://127.0.0.1:8318/
> 遗留：ASR 语音情感辅通道（§3.2）未实现，列 E1.5；防抖致切换响应 ~4–6s（超 2.5s 预算，可调）
> 所属：LeLampEmpathy（项目 B）应用主线；插入于 P1.5 与 P2 之间
> 用户已确认决策：① 先冻结本文档再动工；② 喇叭发声 = **Qwen TTS API 直接合成**（非 UUMO 内置 LLM 对话），参考实现为独立的 Qwen API demo 工程
> 上游资产：episodes_v3.1、mapping_contract v1.2、primitives 引擎、episode_viewer.html（保留不动）

---

## 1. 目标与非目标

**目标**：笔记本麦克风 + 摄像头 → Qwen 多模态 API 判用户情绪 → 仿真 lamp 按契约 v1.2 产出动作 + LED + 文字 + 语音 → 升级版实时 viewer 观察验证。

**非目标**（本阶段不做）：
- 真实硬件舵机/灯环驱动（lamp 保持仿真）
- UUMO 全双工自由对话（lamp 话术来自我们的 episodes/契约，不由 LLM 即兴生成）
- SNN 逃避反射接入（P2 的事，但架构预留挂载点，见 §12）

## 2. 总体架构

```
笔记本摄像头 ──抓拍(2s/帧或VAD触发)──► qwen-vl-max ──► 情绪JSON {label∈7类, valence, arousal, conf}
笔记本麦克风 ──流式──► ASR(paraformer/gummy) ──► 文本 ──► qwen 文本情感 ──┐
                                                                          ├─► 情绪融合(§3.3)
                                                                          ▼
                                              情绪状态 {label, V/A, conf, 时间戳}
                                                                          ▼
                                    响应引擎(§4)：episodes_v3.1 检索 / 原语合成 + §8 过渡
                                                                          ▼
                              ┌── live episode JSON（轨迹+LED+caption）──┐
                              ▼                                          ▼
              Qwen TTS 直接合成(§5)                         live_bridge.py 状态缓存(§6)
               CosyVoice-v3-Flash                                    │ HTTP :8318
               PCM 24k → AudioPlayer → 喇叭                           ▼
               同步存 wav ──────────────────► live_viewer.html(§7) 实时模式
                                              动作+LED+文字+音频同步+识别状态面板
```

## 3. 感知层

### 3.1 视觉情绪（主通道）
- 每 **2s** 抓拍一帧（`opencv-python`，640×480 JPEG），或检测到语音活动时立即补拍
- `qwen-vl-max`，prompt 硬约束输出 JSON（禁止自由文本）：

```json
{"emotion": "joy|sad|angry|fear|love|surprise|neutral",
 "valence": 0.0-1.0, "arousal": 0.0-1.0, "confidence": 0.0-1.0,
 "face_visible": true/false, "evidence": "≤20字依据"}
```

- 7 类标签与我们契约类一一同名，**无需映射表**（prompt 内给每类一句判别标准）

### 3.2 语音情感（辅通道）
- 麦克风 → ASR（paraformer-realtime / gummy，E1.0 时按 demo 现状选型）→ 文本
- 文本 → qwen（turbo/plus）轻量情感判别，同样输出 7 类 + V/A
- 无语音时本通道静默，不投票

### 3.3 融合与稳定规则
| 情况 | 仲裁 |
|---|---|
| 仅视觉 | 直接用，conf < 0.5 → neutral |
| 双通道一致 | conf = max(两者) |
| 双通道冲突 | 视觉权重 0.6 / 语音 0.4 按 V/A 距离裁决；仍不明 → neutral |
| face_visible=false | 仅用语音；语音也静默 → 保持上一状态 ≤10s 后回 §7 idle |
| **防抖（hysteresis）** | 新情绪需连续 2 次判定一致才切换，防止灯光/动作抖动 |

## 4. 响应引擎（消费已冻结资产）

1. **检索优先**：按情绪类从 episodes_v3.1 取候选 → 按 V/A 欧氏距离最近邻取 top-5 → 轮换取 1（避免连续重复）
2. **合成兜底**：neutral 或检索不满意时调 primitives 引擎现合成
3. **衔接**：相邻响应之间**必须**走契约 §8 过渡段（cosine blend，不回零位）；长时间无交互 → §7 idle 模式（相机自适应照明 + 微动）
4. **文案**：caption 直接用 episode 的 `scene_text_en` 响应句（英文）——E1 阶段 lamp 说英文台词；中文回译属遗留项，本阶段不做

## 5. TTS 与喇叭（用户指定：Qwen TTS API 直接合成）

- **模型**：CosyVoice-v3-Flash（dashscope TTS API，websocket 流式；备选 qwen3-tts-flash，E1.0 验证后定）
- **接口参考**：Qwen TTS demo 的 websocket/PCM 管线 + 多模态对话 demo 的 `AudioPlayer`（pyaudio，支持打断）
- **音色可选**（`.env` 注释给出的可用音色）：`longanhuan / longanyang / longhuhu_v3 / longfeifei_v3 / longanshuo_v3` 等
- **默认音色映射**（viewer 面板可手动覆盖）：

| 情绪 | 默认音色 | 理由 |
|---|---|---|
| joy/surprise | longfeifei_v3 | 明亮 |
| sad/love | longanshuo_v3 | 舒缓 |
| angry/fear | longanyang | 低沉 |
| neutral | longanhuan | 中性 |

- **输出双写**：PCM 24kHz → AudioPlayer 实时播喇叭；同时写 `live_audio/<episode_id>.wav` 供 viewer 同步播放与回放
- 语音与动作**异步并行**：动作立即开始，TTS 首包到达即播，不强求唇同步（台灯无嘴）

## 6. live_bridge.py（本地桥接服务，新文件）

- 端口 **8318**（避开 viewer 静态服务器 8317）；纯标准库 http.server 扩展 + 后台线程
- 线程：① 摄像头抓拍 ② 麦克风/ASR ③ 情绪判定调度 ④ 响应生成 ⑤ TTS
- HTTP 端点：
  - `GET /live/status` → 当前情绪状态、置信度、ASR 文本、各阶段延迟（供状态面板轮询）
  - `GET /live/latest` → 最新 live episode JSON（含 `seq` 序号，viewer 据此去重）
  - `GET /live/audio/<episode_id>.wav` → 对应音频
  - `GET /` → live_viewer.html
- **key 安全**：统一由 `tools/env_config.py` 解析（环境变量 → 仓库根 `.env`）；代码零硬编码；`.env` 确认在 .gitignore

## 7. live_viewer.html（升级版查看器，新文件）

- **原 `episode_viewer.html` 一字不动保留**；新文件复用其渲染核心（FK 经 pybullet 验证 <1e-4m）
- 两种模式：文件模式（原有功能全保留）+ **Live 模式**（默认）：
  - 每 1s 轮询 `/live/latest`，`seq` 更新即播新 episode（含 LED、caption）
  - `<audio>` 同步拉 `/live/audio/...wav`
  - **状态面板**：识别情绪标签（七色徽标）、置信度条、V/A 值、ASR 最近一句、各阶段延迟 ms、音色选择下拉（可实时覆盖默认映射）
  - 手动测试区：7 个按钮直接注入指定情绪（绕过感知，验证响应链路）

## 8. 延迟预算（验收硬指标）

| 环节 | 预算 |
|---|---|
| 抓拍 → qwen-vl 情绪 JSON | < 1.5 s |
| 情绪 → 首帧动作上屏 | < 0.3 s（本地检索） |
| TTS 首包 → 喇叭出声 | < 1.0 s |
| **端到端（画面变化→lamp 开始反应）** | **< 2.5 s** |

## 9. 风险与缓解

| 风险 | 缓解 |
|---|---|
| qwen-vl 情绪误判 | conf 阈值 + 防抖 + 手动注入按钮可对照验证 |
| API 限流/成本 | 抓拍间隔 2s 自适应（无变化画面降频到 5s）；文本情感走 turbo |
| 网络断 | 全部 API 调用带超时与重试；失败回退 neutral + 状态面板显式报错 |
| 隐私 | 状态面板常驻"摄像帧上传云端"提示；不存原始帧（仅存情绪 JSON 日志） |
| 中英混杂 | 台词英文（episodes 现状）；ASR 中文照常判别情绪，不受影响 |

## 10. 实施步骤与验收

| 步骤 | 内容 | 验收 |
|---|---|---|
| E1.0 | 建 venv 装依赖（dashscope/pyaudio/opencv-python/python-dotenv/websocket-client），用 .env 的 key 跑通 demo | demo 能对话出声 |
| E1.1 | 摄像头→qwen-vl 情绪 JSON（含 prompt 调优） | 对镜头做 7 种表情，标签合理 ≥6/7 |
| E1.2 | 响应引擎：情绪→检索/合成→live episode | 7 情绪各产 1 条，QC 轨迹合规（速度预算内） |
| E1.3 | live_bridge + live_viewer 实时模式 | viewer 实时播放动作+文字+状态面板 |
| E1.4 | TTS 接入 + 音色映射 + 延迟实测 | 喇叭出声、音色可切、端到端 < 2.5s |

## 11. 文件清单（将创建）

```
LeLampEmpathy/
  tools/live_bridge.py          # 桥接服务（感知+响应+TTS+HTTP）
  tools/live_viewer.html        # 升级版查看器（文件/Live 双模式）
  tools/live_audio/             # TTS wav 缓存（gitignore）
  docs/e1_multimodal_loop.md    # 本文档
```

## 12. 与后续阶段的接口

- **P2 反射通道**：SNN 逃避（P1.5 闭环）将来作为"快通道"写同一份 live episode 流（优先级高于共情慢通道，契约 §9 已定义信号）——本架构的 viewer/bridge 无需改动即可挂载
- **BEAT/EMD**：后置到 E1 验收之后；BEAT 重定向产物同样以 episode 形式进本 viewer 核查

---

*冻结确认后，从 E1.0 开始。*

## 13. 修订记录（2026-10-04 晚）

- **TTS 线程崩溃修复**：`LOGGER.log("tts", reason=reason, **info)` 重复键致 tts_worker 首任务即死 → 全部语音无声（含提醒）。修复+线程加固（永不死）。
- **回声防护**：喇叭播放期间+2.5s 尾音内 ASR 输入记 `asr_muted` 不动作（防自触发递归提醒）。
- **提醒去重**：同 message 且 due 差 ≤15s → `reminder_dup` 跳过。
- **ASR 应答去抖**：5s 冷却（`asr_cooldown`）+ <3 字语气词过滤（`asr_trivial`）。
- **LLM 上下文应答（§3.2 落地）**：用户说话 → 动作仍走情绪 episode，开口改为 qwen-turbo 按【说话内容+视觉情绪】生成一句 ≤40 字上下文应答（实测 369–609ms）→ TTS（reason=user_reply）。罐头 caption 仅保留于 inject 演示。新增测试端点 `POST /live/say {"text":...}` 模拟 ASR；viewer 第二栏新增 "💬 lamp reply" 显示。
