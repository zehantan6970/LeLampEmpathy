# LeLampEmpathy

**A data-driven multimodal empathy lamp — simulation-first.**
It watches you (webcam → vision-LLM emotion recognition), listens to you
(microphone → streaming ASR), and responds with coordinated **motion (5-DOF
pose) + light (SK6812 RGBW) + speech (TTS)** driven by a curated episode
dataset and an emotion→expression contract.

[中文说明 → README_zh.md](README_zh.md)

Sister project of
[LeLampFlyBrainSimulation](https://github.com/zehantan6970/LeLampFlyBrainSimulation)
(Project A: dataset-free, backprop-free bio-SNN core). The two projects share
one platform and one dataset contract
([docs/mapping_contract.md](docs/mapping_contract.md)).

---

## Features (current: E1.5)

| Channel | What it does |
|---|---|
| **Perception** | Webcam frames → `qwen-vl-max` judges 7 emotions (joy/sad/angry/fear/love/surprise/neutral) with valence/arousal/confidence; hysteresis filter (2-consistent switch, low-confidence → neutral) |
| **Expression** | Emotion → nearest-neighbor retrieval over 50+ curated motion+light episodes (`data/episodes/episodes_v3.jsonl`), contract-validated transitions (joint-limit & speed safe) |
| **ASR** | Streaming `paraformer-realtime-v2` (16 kHz, sentence-end detection, echo guard while the lamp itself is speaking) |
| **Replies** | Contextual LLM answers (`qwen-turbo`) with persona + emotion + 6-turn history + long-term user memory; replies in the language you speak |
| **TTS** | `cosyvoice-v3-flash` direct synthesis, per-emotion voices & prosody, 5 selectable style presets |
| **Personas** | 5 switchable personas (friend / counselor / coach / elder companion / kid buddy), each with its own voice, prosody and greeting |
| **Reminders** | "Remind me to drink water in 20 minutes" — parsed by LLM, spoken at due time, de-duplicated |
| **Sleep / wake / exit** | Voice commands ("退出lamp" / "打开lamp") and panel buttons |
| **Memory** | Long-term user facts persisted to `logs/user_profile.json` (e.g. your name), injected into every reply |
| **Logging** | Every run creates `logs/live_<date>_<time>/` with `events.jsonl` (all perception/ASR/TTS/reply events) + captured frames |

Runs fully **in simulation**: the lamp is rendered in the browser viewer
(skeletal 5-DOF + LED ring). No hardware required. The physical LeLamp
(5 servos + SK6812 ring) is supported later via a HAL layer.

## Requirements

- Python **3.10+** (3.12/3.13 tested), Windows / macOS / Linux
- A **DashScope (Alibaba Cloud Bailian) API key** for the live mode
  (get one at <https://bailian.console.aliyun.com/>)
- Webcam + microphone + speaker for the full live experience
  (optional: `--no-camera` and `--mute` flags degrade gracefully)
- **No key / no camera?** You can still explore the whole dataset offline
  with the Episode Viewer (see below) — zero API calls.

## Installation

```bash
# 1. Get the code
git clone https://github.com/zehantan6970/LeLampEmpathy.git
cd LeLampEmpathy
# …or just download and unzip the ZIP from GitHub

# 2. Create a virtual environment and install dependencies
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# 3. Configure your API key
# Windows:  copy .env.example .env
# macOS/Linux: cp .env.example .env
# then edit .env and paste your key
```

## Quick start ① — Episode Viewer (offline, no API key)

Open `tools/episode_viewer.html` in any browser, then drag
`data/episodes/episodes_v3.jsonl` onto the page (or click *Load*).
You can browse 50+ episodes, filter by emotion, play the motion + LED
animation with captions, and step frame by frame. This needs no server,
no key, no camera.

## Quick start ② — Live simulation (full multimodal loop)

```bash
# Sanity-check your environment first (deps / key / API / camera / audio)
python tools/e1_env_check.py

# Start the bridge (perception + ASR + TTS + reminders + HTTP server :8318)
python tools/live_bridge.py
# useful flags:
#   --interval 3    seconds between webcam emotion judgments (default 3)
#   --mute          no TTS playback (text-only)
#   --no-camera     disable webcam perception (ASR/chat still works)
```

Then open `tools/live_viewer.html` in your browser. It connects to
`127.0.0.1:8318` automatically.

### Using the live viewer

- **Watch**: the lamp mirrors its current pose + LED ring; the webcam
  snapshot and the judged emotion appear in the panel.
- **Talk**: just speak — your words are transcribed and shown, and the lamp
  answers with voice + motion. You can also type into the inject box.
- **Remind**: type or say "20分钟后提醒我喝水" / "remind me to stretch in
  10 minutes"; the lamp confirms and speaks up at due time.
- **Persona / voice / style**: switch anytime from the dropdowns
  (friend, counselor, coach, elder companion, kid buddy).
- **Sleep / wake**: say "退出lamp" (sleep) and "打开lamp" (wake); reminders
  still fire while asleep.
- **Exit**: click the exit button twice (two-click confirm), or `Ctrl+C`
  in the terminal.

### Where are the logs?

Every run creates a new folder:

```
logs/live_YYYY-MM-DD_HHMMSS/
├── events.jsonl   # every perception / ASR / reply / TTS / reminder event
└── frames/        # captured key frames
logs/user_profile.json   # long-term user memory (persists across runs)
```

## Repository layout

```
assets/       vendored LeLamp hardware descriptions (see NOTICE)
configs/      joint limits, emotion presets
primitives/   parametric motion-primitive engine
dataset/      small demo episodes (v1 schema, see docs/mapping_contract.md)
data/episodes/  curated episode library (v1/v2/v3 jsonl)
docs/         mapping contract (READ FIRST), E1 system doc, persona design,
              emotion catalog, hardware mapping, dataset cards
tools/
  episode_viewer.html  offline dataset viewer (no server needed)
  live_viewer.html     live simulation viewer
  live_bridge.py       the live multimodal bridge (HTTP :8318)
  e1_perception.py     webcam + qwen-vl emotion judgment
  e1_asr.py            streaming ASR worker
  e1_tts.py            Qwen TTS synthesis & playback
  e1_responder.py      emotion → episode retrieval → live episode
  e1_logger.py         run logger (events.jsonl + frames)
  e1_personas.json     5 persona definitions
  e1_env_check.py      environment self-check
  gen/build/qc_*       episode generation & QC utilities
```

## Roadmap

- **E3 (in design)**: refactor the reply pipeline into a LangGraph multi-agent
  architecture (Supervisor + Empathy/Research/Tutor agents + tool skills),
  with a fly-brain SNN reflex agent running in parallel.
- **Hardware**: HAL abstraction → run on the physical LeLamp (Pi + 5 servos
  + SK6812).
- **Phase 2**: EEG-attention closed loop (research stage).

## Honest status

This is a research prototype. Emotion recognition from a single webcam frame
is noisy (mitigated by confidence thresholds + hysteresis, not solved);
the persona prompts are informed by the counseling/empathy literature
(see `docs/persona_empathy_design.md`) but are not clinical tools.

## License & credits

- Code and dataset: **GPL-3.0** (see [LICENSE](LICENSE)).
- `assets/` contains vendored LeLamp hardware descriptions — see
  [NOTICE](NOTICE) for attribution.
- LLM/VL/ASR/TTS services: Alibaba Cloud DashScope (Qwen family).
