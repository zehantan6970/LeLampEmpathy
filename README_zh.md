# LeLampEmpathy

**数据驱动的多模态共情台灯——仿真先行。**
它看你（摄像头 → 视觉大模型情绪识别）、听你（麦克风 → 流式语音识别），
并用协调一致的**动作（5 自由度姿态）+ 灯光（SK6812 RGBW）+ 语音（TTS）**
回应你——由精选 episode 数据集和"情绪→表达"契约驱动。

[English README → README.md](README.md)（英文版更详细）

姐妹项目：
[LeLampFlyBrainSimulation](https://github.com/zehantan6970/LeLampFlyBrainSimulation)
（项目 A：无数据集、无反向传播的生物 SNN 核心）。两个项目共享同一平台和
同一份数据契约（[docs/mapping_contract.md](docs/mapping_contract.md)）。

---

## 功能（当前版本 E1.5）

| 通道 | 说明 |
|---|---|
| **感知** | 摄像头帧 → `qwen-vl-max` 判定 7 种情绪（喜/悲/怒/惧/爱/惊/中性），带效价/唤醒度/置信度；防抖滤波（连续 2 次一致才切换，低置信归为中性） |
| **表达** | 情绪 → 在 50+ 精选动作+灯光 episode 库中最近邻检索（`data/episodes/episodes_v3.jsonl`），过渡经契约校验（关节限位/速度安全） |
| **语音识别** | 流式 `paraformer-realtime-v2`（16kHz、断句、防回声——lamp 自己说话时不会自触发） |
| **应答** | `qwen-turbo` 上下文应答：人设 + 情绪 + 6 轮对话历史 + 长期用户记忆；你说英文它回英文 |
| **语音合成** | `cosyvoice-v3-flash` 直合成，每种情绪有默认音色和韵律，5 种说话风格可选 |
| **人设** | 5 种可切换人设（朋友/心理咨询师/教练/老年陪伴/儿童伙伴），各有专属音色、韵律和问候语 |
| **定时提醒** | 说"20 分钟后提醒我喝水"，到点自动开口提醒（已去重） |
| **睡眠/唤醒/退出** | 语音命令"退出lamp"/"打开lamp"，或面板按钮 |
| **记忆** | 长期用户事实存到 `logs/user_profile.json`（比如你的名字），每次应答都会用上 |
| **日志** | 每次运行生成 `logs/live_<日期>_<时间>/`（`events.jsonl` 全事件流水 + 抓拍帧） |

**全程仿真运行**：lamp 在浏览器 viewer 中渲染（5 自由度骨架 + LED 灯环），
无需任何硬件。实体 LeLamp（5 舵机 + SK6812 灯环）后续通过 HAL 层接入。

## 环境要求

- Python **3.10+**（已在 3.12/3.13 测试），Windows / macOS / Linux
- Live 模式需要 **DashScope（阿里云百炼）API key**
  （申请：<https://bailian.console.aliyun.com/>）
- 完整体验需要摄像头 + 麦克风 + 音箱；也可用 `--no-camera`、`--mute` 降级运行
- **没有 key / 没有摄像头？** 仍可离线浏览全部数据集（见下方 Episode Viewer）

## 安装

```bash
# 1. 获取代码
git clone https://github.com/zehantan6970/LeLampEmpathy.git
cd LeLampEmpathy
# 或直接在 GitHub 下载 ZIP 解压

# 2. 建虚拟环境并装依赖
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 3. 配置 API key
# Windows:  copy .env.example .env
# macOS/Linux: cp .env.example .env
# 然后编辑 .env 填入你的 key
```

## 快速上手 ① —— Episode Viewer（离线，无需 API key）

用浏览器直接打开 `tools/episode_viewer.html`，把
`data/episodes/episodes_v3.jsonl` 拖进页面（或点 Load）。
可浏览 50+ 个 episode、按情绪筛选、播放动作+灯光动画和字幕、逐帧查看。
不需要服务器、不需要 key、不需要摄像头。

## 快速上手 ② —— Live 仿真（完整多模态闭环）

```bash
# 先自检环境（依赖 / key / API 连通 / 摄像头 / 音频设备）
python tools/e1_env_check.py

# 启动桥接服务（感知 + ASR + TTS + 提醒 + HTTP :8318）
python tools/live_bridge.py
# 常用参数：
#   --interval 3    摄像头情绪判定间隔秒数（默认 3）
#   --mute          不播语音（纯文字交互）
#   --no-camera     关闭摄像头感知（语音聊天仍可用）
```

然后用浏览器打开 `tools/live_viewer.html`，它会自动连接 `127.0.0.1:8318`。

### Live Viewer 怎么用

- **看**：lamp 实时渲染当前姿态 + 灯环；面板显示摄像头画面和判定的情绪。
- **说**：直接说话——你的话会被转写显示，lamp 用语音+动作回答。
  也可以在输入框里打字。
- **提醒**：输入或说出"20 分钟后提醒我喝水"，lamp 会确认，到点开口。
- **人设/音色/风格**：下拉框随时切换（朋友/咨询师/教练/长者陪伴/儿童伙伴）。
- **睡眠/唤醒**：说"退出lamp"入睡、"打开lamp"唤醒；睡眠中提醒仍然有效。
- **退出**：exit 按钮连点两下（防误触），或在终端按 `Ctrl+C`。

### 日志在哪里？

每次运行新建一个目录：

```
logs/live_YYYY-MM-DD_HHMMSS/
├── events.jsonl   # 感知/ASR/应答/TTS/提醒 全事件流水
└── frames/        # 关键帧抓拍
logs/user_profile.json   # 长期用户记忆（跨运行保留）
```

## 目录结构

```
assets/       LeLamp 硬件描述（vendor 拷贝，见 NOTICE）
configs/      关节限位、情绪预设
primitives/   参数化动作基元引擎
dataset/      小型演示 episode（v1 schema，见 docs/mapping_contract.md）
data/episodes/  精选 episode 库（v1/v2/v3 jsonl）
docs/         映射契约（先读这个）、E1 系统文档、人设设计、情绪目录、
              硬件映射、数据集卡片
tools/
  episode_viewer.html  离线数据集查看器（无需服务器）
  live_viewer.html     Live 仿真查看器
  live_bridge.py       Live 多模态桥接服务（HTTP :8318）
  e1_perception.py     摄像头 + qwen-vl 情绪判定
  e1_asr.py            流式语音识别
  e1_tts.py            Qwen TTS 合成与播放
  e1_responder.py      情绪 → episode 检索 → live episode
  e1_logger.py         运行日志（events.jsonl + 帧）
  e1_personas.json     5 种人设定义
  e1_env_check.py      环境自检
  gen/build/qc_*       episode 生成与质检工具
```

## 路线图

- **E3（设计中）**：应答管线重构为 LangGraph 多智能体架构
  （Supervisor + 共情/检索/辅导 Agent + 工具技能），
  并行运行果蝇脑 SNN 反射 Agent。
- **硬件**：HAL 抽象 → 部署到实体 LeLamp（树莓派 + 5 舵机 + SK6812）。
- **二期**：EEG 注意力闭环（研究阶段）。

## 诚实声明

这是一个研究原型。单帧摄像头情绪识别有噪声（已用置信度阈值+防抖缓解，
但未根治）；人设 prompt 参考了心理咨询/共情文献
（见 `docs/persona_empathy_design.md`），但不是临床工具。

## 许可与致谢

- 代码与数据集：**GPL-3.0**（见 [LICENSE](LICENSE)）。
- `assets/` 为 LeLamp 硬件描述的 vendor 拷贝，署名见 [NOTICE](NOTICE)。
- LLM/VL/ASR/TTS 服务：阿里云百炼 DashScope（通义 Qwen 系列）。
