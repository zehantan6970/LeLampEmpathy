# -*- coding: utf-8 -*-
"""E1.3+E1.5 本地桥接服务（端口 8318）。

E1.3：感知循环 + 响应引擎 + HTTP + Live Viewer
E1.5：运行日志（logs/live_日期_时分秒/）+ ASR 语音通道 + 说话策略收敛 + 定时提醒

说话策略（用户冻结）：lamp 只在以下情况开口——
  ① 用户主动交互：ASR 听到用户说话 / viewer 注入按钮
  ② 危险警报：检测到 fear/angry（conf≥0.6）
  ③ 定时提醒触发
  普通情绪切换 → 只动动作+LED，不说话。

用法：
  .venv/Scripts/python.exe tools/live_bridge.py [--interval 3] [--mute] [--no-camera] [--no-asr]

端点：
  GET  /  /live/status  /live/latest  /live/frame.jpg  /live/audio/<f>.wav
  POST /live/inject {"emotion":"joy"}
  POST /live/say {"text":"..."}                       # 模拟 ASR 文本输入
  POST /live/voice {"voice":"", "style":""}           # 音色/风格覆盖，空=自动
  POST /live/persona {"persona":"friend"}             # 5 人设切换（E2）
  POST /live/sleep  /live/wake                        # 睡眠/唤醒（=语音「退出/打开lamp」）
  POST /live/shutdown                                 # 完全退出（=命令行 Ctrl+C）
  POST /live/reminder {"text":"20分钟后提醒我吃药"}   # 也可用 ASR 直接说

语音命令（对 lamp 直接说）：
  「退出lamp」/「关闭lamp」/「lamp休息」 → 睡眠（不做响应，提醒仍生效）
  「打开lamp」/「唤醒lamp」            → 唤醒恢复
完全退出：命令行窗口按 Ctrl+C，或 POST /live/shutdown（viewer 有 exit 按钮）。
"""
import argparse
import json
import os
import queue
import re
import threading
import time
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))

_state_lock = threading.Lock()
STATE = {
    "started_ts": time.time(),
    "camera_ok": False,
    "asr_ok": False,
    "perception": None,
    "last_error": None,
    "rounds": 0,
    "voice_override": None,
    "style_override": None,
    "tts_last": None,
    "last_asr": None,          # {"text":..., "ts":...}
    "last_reply": None,        # {"text":..., "ts":...}
    "reminders": [],           # [{"id":, "due_ts":, "message":, "source":}]
    "log_dir": None,
    "persona": "friend",       # e1_personas.json 的 key
    "sleeping": False,         # 语音命令「退出lamp」→ True；「打开lamp」→ False
}
LATEST = {"payload": None}
LAST_FRAME = {"jpg": None, "ts": 0.0}
AUDIO_DIR = os.path.join(TOOLS, "live_audio")
TTSQ = queue.Queue()
REPLYQ = queue.Queue()               # (user_text, emotion_state, seq) → LLM 应答
FLAGS = {"mute": False, "no_asr": False}
LOGGER = None                # main 里初始化
ALERT_EMOTIONS = {"fear", "angry"}
ALERT_CONF = 0.6
_reminder_seq = [0]

# ── 对话上下文与长期记忆（E2 自强方案，docs/agent_runtime_eval.md §5）────────────
CHAT_HISTORY = deque(maxlen=12)      # [{"role":"user"/"assistant","content":...}] 最近 6 轮
PROFILE_PATH = os.path.join(ROOT, "logs", "user_profile.json")


def load_profile():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"facts": []}


def save_profile_fact(fact):
    """往长期记忆追加一条用户事实（去重，上限 50 条）。返回是否新增。"""
    prof = load_profile()
    facts = prof.setdefault("facts", [])
    if any(x.get("fact") == fact for x in facts):
        return False
    facts.append({"ts": datetime.now().isoformat(timespec="seconds"),
                  "fact": fact})
    del facts[:-50]
    os.makedirs(os.path.dirname(PROFILE_PATH), exist_ok=True)
    with open(PROFILE_PATH, "w", encoding="utf-8") as f:
        json.dump(prof, f, ensure_ascii=False, indent=1)
    return True

# ── 人设（E2，docs/persona_empathy_design.md）─────────────────────────────────
with open(os.path.join(TOOLS, "e1_personas.json"), encoding="utf-8") as _f:
    PERSONAS = json.load(_f)
REPLY_RULES = ("规则：不超过40个汉字或20个英文单词；"
               "必须严格使用用户本条消息的语言回复（用户说英文就必须回英文，"
               "说中文就回中文），不要用其他语言；"
               "不要emoji、不要引号、不要解释，只输出要说的话。")
CRISIS_CLAUSE = ("安全条款（最高优先级）：如果用户表达自伤、自杀或伤害他人的意图，"
                 "回应要表达关心，并温和但明确地建议Ta寻求专业心理帮助或"
                 "联系信任的人/紧急求助；不做诊断，不扮演医生。")
# 语音命令：动词 + (lamp|台灯|灯) 组合识别
SLEEP_VERBS = ("退出", "关闭", "關閉", "休息", "睡觉", "睡覺", "睡吧",
               "关机", "關機", "下班")
WAKE_VERBS = ("打开", "打開", "开启", "開啟", "唤醒", "喚醒", "醒醒",
              "起床", "上班")
LAMP_NOUNS = ("lamp", "台灯", "檯燈", "灯", "燈")


def current_persona():
    with _state_lock:
        return PERSONAS.get(STATE["persona"], PERSONAS["friend"])


def set_status(**kw):
    with _state_lock:
        STATE.update(kw)


def get_status():
    with _state_lock:
        d = dict(STATE)
    d["uptime_s"] = round(time.time() - d.pop("started_ts"), 1)
    d["seq"] = LATEST["payload"]["seq"] if LATEST["payload"] else 0
    d["history_turns"] = len(CHAT_HISTORY) // 2
    d["memory_facts"] = len(load_profile().get("facts", []))
    return d


def current_frame():
    with _state_lock:
        return LAST_FRAME["jpg"]


# ── 响应下发 + 说话策略 ───────────────────────────────────────────────────────
def publish(payload, speak_reason=None, frame_tag=None):
    from e1_logger import pose_summary
    with _state_lock:
        LATEST["payload"] = payload
    frame_fn = LOGGER.save_frame(current_frame(),
                                 frame_tag or f"seq{payload['seq']}")
    LOGGER.log("response", seq=payload["seq"],
               emotion=payload["emotion_state"].get("filtered_emotion"),
               speak=speak_reason or False,
               caption=(payload["episode"].get("response") or {}).get("caption"),
               frame=frame_fn,
               pose=pose_summary(payload["episode"]),
               transition=bool(payload["transition"]))
    if speak_reason:
        caption = (payload["episode"].get("response") or {}).get("caption") or ""
        if caption.strip():
            TTSQ.put((payload["seq"], caption,
                      payload["emotion_state"].get("filtered_emotion",
                                                   "neutral"),
                      speak_reason))


# ── TTS 工作线程 ─────────────────────────────────────────────────────────────
def tts_worker():
    from e1_tts import synthesize_wav, play_wav
    done_seqs = set()
    while True:
        seq, text, emotion, reason = TTSQ.get()
        try:
            if isinstance(seq, int) and seq in done_seqs:
                continue
            with _state_lock:
                override = STATE.get("voice_override")
                style = STATE.get("style_override")
            wav, info = synthesize_wav(text, emotion, override, style,
                                       persona=current_persona())
            if wav is None:
                set_status(tts_last={"seq": seq, "err": info})
                LOGGER.log("error", where="tts", err=info, seq=seq)
                continue
            if isinstance(seq, int):
                done_seqs.add(seq)
            fn = f"seq{seq}_{emotion}.wav" if isinstance(seq, int) \
                else f"{seq}_{emotion}.wav"
            with open(os.path.join(AUDIO_DIR, fn), "wb") as f:
                f.write(wav)
            info = dict(info, seq=str(seq), file=fn, reason=reason)
            set_status(tts_last=info)
            LOGGER.log("tts", text=text, **info)
            with _state_lock:
                if LATEST["payload"] and LATEST["payload"]["seq"] == seq:
                    LATEST["payload"]["audio_url"] = f"/live/audio/{fn}"
            if not FLAGS["mute"]:
                try:
                    # 播放期间+尾音 2.5s 内屏蔽 ASR（防喇叭回声自触发）
                    dur = max(0.5, (len(wav) - 44) / 48000.0)
                    with _state_lock:
                        STATE["asr_mute_until"] = time.time() + dur + 2.5
                    play_wav(wav)
                except Exception as e:  # noqa: BLE001
                    set_status(last_error=f"playback: {e}")
                    LOGGER.log("error", where="playback",
                               err=f"{type(e).__name__}: {e}", seq=str(seq))
        except Exception as e:  # noqa: BLE001
            # 线程永不死：任何单条失败都记日志并继续消费队列
            try:
                set_status(last_error=f"tts_worker: {e}")
                LOGGER.log("error", where="tts_worker",
                           err=f"{type(e).__name__}: {e}", seq=str(seq))
            except Exception:  # noqa: BLE001
                pass


def speak_text(text, emotion="neutral", reason="reminder"):
    """直接说一句（提醒等不经 episode 的语音）。"""
    TTSQ.put((f"rem{int(time.time())}", text, emotion, reason))


# ── LLM 上下文应答 ────────────────────────────────────────────────────────────
def generate_reply(user_text, emotion, valence, arousal, persona=None):
    """按【人设+用户说话内容+当前情绪+对话历史+用户记忆】生成上下文应答。"""
    import dashscope
    from dashscope import Generation
    from env_config import load_llm_config
    dashscope.api_key = load_llm_config()["DASHSCOPE_API_KEY"]
    persona = persona or PERSONAS["friend"]
    with _state_lock:
        voice_name = STATE.get("voice_override") or persona.get("voice", "")
        style_name = STATE.get("style_override") or "按情绪自动"
    facts = [x["fact"] for x in load_profile().get("facts", [])][-15:]
    user_knowledge = ("关于用户（你长期记住的信息，自然使用，不要逐条背诵）："
                      + "；".join(facts)) if facts else ""
    self_knowledge = (
        "关于你自己（被问到时如实回答，不要编造）："
        f"你当前的人设是「{persona.get('name_cn', '')}」；"
        f"你说话用的音色是 {voice_name}；说话风格是{style_name}。"
        "你能通过摄像头看用户的表情、通过麦克风听用户说话，"
        "用动作、灯光和语音回应。可选人设还有："
        + "、".join(v.get("name_cn", k) for k, v in PERSONAS.items()
                   if v is not persona)
        + "，用户可以在面板上随时切换。")
    sys_prompt = (persona["system_prompt"]
                  + "根据用户说的话和Ta当前的情绪，生成一句回应。" + REPLY_RULES
                  + self_knowledge + user_knowledge
                  + CRISIS_CLAUSE)
    # 粗判用户语言（ASCII 字母占比高→英文），双语包装避免带偏 LLM 的输出语言
    letters = sum(1 for c in user_text if c.isascii() and c.isalpha())
    cjk = sum(1 for c in user_text if "一" <= c <= "鿿")
    if letters > cjk:
        usr = (f"User said: {user_text}\n"
               f"User's current emotion (camera): {emotion}, "
               f"valence {valence:.2f}, arousal {arousal:.2f} (0~1).\n"
               f"Reply in English.")
    else:
        usr = (f"用户说：{user_text}\n"
               f"用户当前情绪（摄像头判定）：{emotion}，"
               f"愉悦度{valence:.2f}，激活度{arousal:.2f}（0~1）\n"
               f"请用中文回复。")
    # 多轮上下文：system + 最近历史 + 本轮（历史里的 user 是原话，assistant 是 lamp 应答）
    with _state_lock:
        history = list(CHAT_HISTORY)
    messages = ([{"role": "system", "content": sys_prompt}]
                + history
                + [{"role": "user", "content": usr}])
    t0 = time.time()
    try:
        resp = Generation.call(model="qwen-turbo",
                               messages=messages,
                               max_tokens=80, result_format="message")
        if resp.status_code == 200:
            reply = resp.output.choices[0].message.content.strip().strip('"“”')
            if reply:
                return reply, int((time.time() - t0) * 1000)
    except Exception:  # noqa: BLE001
        pass
    return None, int((time.time() - t0) * 1000)


def extract_user_fact(user_text):
    """从用户一句话中抽取值得长期记住的事实（名字/偏好/重要事件）。
    无则返回 None。轻量单轮 LLM 调用。"""
    import dashscope
    from dashscope import Generation
    from env_config import load_llm_config
    dashscope.api_key = load_llm_config()["DASHSCOPE_API_KEY"]
    prompt = ("从下面这句话中提取值得长期记住的用户信息"
              "（姓名/称呼、偏好、习惯、重要事件、人际关系）。"
              "输出要求：一条简短的事实陈述（不超过20字），"
              "用第三人称（如\"用户叫小明\"\"用户喜欢吃辣\"）；"
              "疑问句、请求、闲聊不算事实；"
              "如果没有值得记住的信息，只输出 NONE。\n"
              f"用户的话：{user_text}")
    try:
        resp = Generation.call(model="qwen-turbo",
                               messages=[{"role": "user", "content": prompt}],
                               max_tokens=40, result_format="message")
        if resp.status_code == 200:
            out = resp.output.choices[0].message.content.strip().strip('"“”。')
            if (out and out.upper() != "NONE" and len(out) <= 40
                    and not out.endswith(("？", "?"))
                    and "什么" not in out):
                return out
    except Exception:  # noqa: BLE001
        pass
    return None


def reply_worker():
    """消费 REPLYQ：LLM 生成应答 → 交给 TTS。线程永不死。"""
    while True:
        user_text, st, seq = REPLYQ.get()
        try:
            emotion = st.get("filtered_emotion", "neutral")
            persona = current_persona()
            reply, lat = generate_reply(user_text, emotion,
                                        st.get("valence", .5),
                                        st.get("arousal", .5),
                                        persona=persona)
            if not reply:
                LOGGER.log("error", where="reply_llm", seq=seq)
                continue
            with _state_lock:
                pkey = STATE["persona"]
            LOGGER.log("reply", seq=seq, user_text=user_text, reply=reply,
                       emotion=emotion, persona=pkey, latency_ms=lat)
            set_status(last_reply={"text": reply, "ts": round(time.time(), 1)})
            TTSQ.put((seq, reply, emotion, "user_reply"))
            # 多轮上下文：本轮（用户原话 + lamp 应答）入历史
            with _state_lock:
                CHAT_HISTORY.append({"role": "user", "content": user_text})
                CHAT_HISTORY.append({"role": "assistant", "content": reply})
            # 长期记忆：抽取值得记住的用户事实
            try:
                fact = extract_user_fact(user_text)
                if fact and save_profile_fact(fact):
                    LOGGER.log("memory_add", fact=fact)
            except Exception as e:  # noqa: BLE001
                LOGGER.log("error", where="memory_extract",
                           err=f"{type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            try:
                LOGGER.log("error", where="reply_worker",
                           err=f"{type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001
                pass


# ── 定时提醒 ──────────────────────────────────────────────────────────────────
def parse_reminder(text):
    """自然语言 → {"delay_seconds":int, "message":str}；LLM 失败回退正则。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = (f"现在是 {now}。解析以下提醒请求，输出严格 JSON：\n"
              f'{{"delay_seconds": <整数秒>, "message": "<到点要说的话，简短>"}}\n'
              f"只输出 JSON。请求：{text}")
    try:
        import dashscope
        from dashscope import Generation
        from env_config import load_llm_config
        dashscope.api_key = load_llm_config()["DASHSCOPE_API_KEY"]
        resp = Generation.call(model="qwen-turbo",
                               messages=[{"role": "user", "content": prompt}],
                               max_tokens=100, result_format="message")
        if resp.status_code == 200:
            t = resp.output.choices[0].message.content.strip()
            if t.startswith("```"):
                t = t.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            d = json.loads(t)
            return {"delay_seconds": max(5, int(d["delay_seconds"])),
                    "message": str(d["message"])}
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"(\d+)\s*(个)?\s*(小时|分钟|秒钟?|min|h|s)", text)
    if m:
        n, unit = int(m.group(1)), m.group(3)
        sec = n * 3600 if unit in ("小时", "h") else \
            n * 60 if unit in ("分钟", "min") else n
        msg = re.sub(r".*?提醒我", "", text).strip(" ，。") or "时间到了"
        return {"delay_seconds": max(5, sec), "message": msg}
    return None


def add_reminder(text, source):
    parsed = parse_reminder(text)
    if not parsed:
        LOGGER.log("error", where="reminder_parse", text=text)
        return None
    with _state_lock:
        # 去重：已有同 message 且到点时间相差 ≤15s 的待触发提醒 → 跳过
        now = time.time()
        new_due = now + parsed["delay_seconds"]
        for r in STATE["reminders"]:
            if r["message"] == parsed["message"] \
                    and abs(r["due_ts"] - new_due) <= 15:
                LOGGER.log("reminder_dup", text=text, source=source,
                           existing_id=r["id"])
                return {"id": r["id"], **parsed, "dedup": True}
        _reminder_seq[0] += 1
        rid = _reminder_seq[0]
        STATE["reminders"].append(
            {"id": rid, "due_ts": new_due,
             "message": parsed["message"], "source": source})
    LOGGER.log("reminder_add", id=rid, text=text, source=source, **parsed)
    return {"id": rid, **parsed}


def reminder_loop():
    while True:
        try:
            now = time.time()
            due = []
            with _state_lock:
                keep = []
                for r in STATE["reminders"]:
                    (due if r["due_ts"] <= now else keep).append(r)
                STATE["reminders"] = keep
            for r in due:
                LOGGER.log("reminder_fire", **r)
                speak_text(f"提醒：{r['message']}", "neutral", "reminder")
                set_status(tts_last={"reminder": r["message"]})
        except Exception as e:  # noqa: BLE001
            try:
                LOGGER.log("error", where="reminder_loop",
                           err=f"{type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001
                pass
        time.sleep(1)


def _mentions_lamp(text):
    low = text.lower()
    return any(n in low for n in LAMP_NOUNS)


def _sleep_lamp(reason):
    set_status(sleeping=True)
    LOGGER.log("sleep", reason=reason)


def _wake_lamp(reason):
    set_status(sleeping=False)
    LOGGER.log("wake", reason=reason)
    speak_text(current_persona()["greeting"], "joy", "wake")


# ── ASR 语音通道 ─────────────────────────────────────────────────────────────
def on_user_sentence(text, responder):
    if not text:
        return
    # 回声防护：lamp 正在说话/刚说完时，忽略 ASR 听到的内容（多半是喇叭回声）
    with _state_lock:
        mute_until = STATE.get("asr_mute_until", 0.0)
    if time.time() < mute_until:
        LOGGER.log("asr_muted", text=text)
        return
    # ── 睡眠/唤醒语音命令（最高优先级，睡眠中仍可唤醒）──
    with _state_lock:
        sleeping = STATE.get("sleeping", False)
    if sleeping:
        if _mentions_lamp(text) and any(v in text for v in WAKE_VERBS):
            frame_fn = LOGGER.save_frame(current_frame(), "asr")
            LOGGER.log("asr", text=text, frame=frame_fn)
            set_status(last_asr={"text": text, "ts": round(time.time(), 1)})
            _wake_lamp("voice")
        else:
            LOGGER.log("asr_sleep_ignored", text=text)
        return
    if _mentions_lamp(text) and any(v in text for v in SLEEP_VERBS):
        frame_fn = LOGGER.save_frame(current_frame(), "asr")
        LOGGER.log("asr", text=text, frame=frame_fn)
        set_status(last_asr={"text": text, "ts": round(time.time(), 1)})
        speak_text("好的，我休息了。想叫我的时候，说「打开lamp」就行。",
                   "neutral", "sleep")
        _sleep_lamp("voice")
        return
    frame_fn = LOGGER.save_frame(current_frame(), "asr")
    LOGGER.log("asr", text=text, frame=frame_fn)
    set_status(last_asr={"text": text, "ts": round(time.time(), 1)})
    if "提醒" in text:
        add_reminder(text, "asr")
        return
    # 应答冷却：5s 内的连续断句（含回声残句、语气词）只响应第一次
    with _state_lock:
        last_sp = STATE.get("last_user_speech_ts", 0.0)
    if time.time() - last_sp < 5.0:
        LOGGER.log("asr_cooldown", text=text)
        return
    # 过短语气词（"嗯。"/"うん。"/"哦"）不触发开口应答，只做情绪感知
    core = re.sub(r"[\s\W_]+", "", text)
    if len(core) < 3:
        LOGGER.log("asr_trivial", text=text)
        return
    with _state_lock:
        STATE["last_user_speech_ts"] = time.time()
    # 用户主动交互 → 动作按情绪 episode 播放；开口走 LLM 上下文应答
    with _state_lock:
        perc = STATE.get("perception") or {}
    st = dict(perc) if perc else {"emotion": "neutral",
                                  "filtered_emotion": "neutral",
                                  "valence": .5, "arousal": .5,
                                  "confidence": 1.0, "face_visible": True}
    st["evidence"] = f"user said: {text[:30]}"
    payload = responder.respond(st)
    publish(payload, speak_reason=None, frame_tag="user_speech")
    REPLYQ.put((text, st, payload["seq"]))


# ── 感知循环 ──────────────────────────────────────────────────────────────────
def perception_loop(responder, interval, no_camera):
    from e1_perception import Camera, judge_emotion, EmotionFilter
    filt = EmotionFilter()
    cam = None
    if not no_camera:
        try:
            cam = Camera()
            set_status(camera_ok=True)
        except Exception as e:  # noqa: BLE001
            set_status(last_error=f"camera: {e}")
            LOGGER.log("error", where="camera", err=str(e))
    publish(responder.respond({"emotion": "neutral", "filtered_emotion": "neutral",
                               "valence": .5, "arousal": .4, "confidence": 1.0,
                               "face_visible": True, "err": None,
                               "evidence": "startup"}),
            speak_reason=None, frame_tag="startup")
    while True:
        t0 = time.time()
        if cam is not None:
            jpg = cam.grab_jpeg()
            if jpg is None:
                set_status(last_error="grab frame failed")
            else:
                with _state_lock:
                    LAST_FRAME["jpg"] = jpg
                    LAST_FRAME["ts"] = time.time()
                raw = judge_emotion(jpg)
                out = filt.update(raw)
                with _state_lock:
                    STATE["rounds"] += 1
                set_status(perception=out, last_error=raw.get("err"))
                LOGGER.log("perception", emotion=out["emotion"],
                           filtered=out["filtered_emotion"],
                           confidence=out["confidence"],
                           valence=out["valence"], arousal=out["arousal"],
                           face=out["face_visible"],
                           latency_ms=out.get("latency_ms"),
                           switched=out["switched"], err=out.get("err"))
                if out["switched"] and not STATE.get("sleeping"):
                    emo, conf = out["filtered_emotion"], out["confidence"]
                    alert = emo in ALERT_EMOTIONS and conf >= ALERT_CONF
                    publish(responder.respond(out),
                            speak_reason="alert" if alert else None,
                            frame_tag="alert" if alert else "switch")
        dt = time.time() - t0
        time.sleep(max(0.1, interval - dt))


# ── HTTP ─────────────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    responder = None

    def _send(self, code, body=b"", ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/live_viewer.html":
            with open(os.path.join(TOOLS, "live_viewer.html"), "rb") as f:
                self._send(200, f.read(), "text/html; charset=utf-8")
        elif path == "/live/status":
            self._send(200, json.dumps(get_status(), ensure_ascii=False).encode())
        elif path == "/live/latest":
            p = LATEST["payload"]
            self._send(200 if p else 204,
                       json.dumps(p, ensure_ascii=False).encode() if p else b"")
        elif path == "/live/frame.jpg":
            jpg = current_frame()
            if jpg:
                self._send(200, jpg, "image/jpeg")
            else:
                self._send(204)
        elif path.startswith("/live/audio/"):
            fn = os.path.basename(path)
            fp = os.path.join(AUDIO_DIR, fn)
            if os.path.isfile(fp):
                with open(fp, "rb") as f:
                    self._send(200, f.read(), "audio/wav")
            else:
                self._send(404, json.dumps({"err": "no such audio"}).encode())
        else:
            self._send(404, json.dumps({"err": "unknown path"}).encode())

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        n = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa: BLE001
            body = {}
        if path == "/live/say":
            # 模拟 ASR 文本输入（测试语音交互链路，无需麦克风）
            text = str(body.get("text", "")).strip()
            if text:
                on_user_sentence(text, self.responder)
            self._send(200, json.dumps({"ok": bool(text)}).encode())
        elif path == "/live/inject":
            if STATE.get("sleeping"):
                self._send(409, json.dumps(
                    {"err": "lamp 睡眠中，先「打开lamp」"}).encode())
                return
            emo = str(body.get("emotion", "neutral")).lower()
            LOGGER.log("inject", emotion=emo)
            st = {"emotion": emo, "filtered_emotion": emo,
                  "valence": float(body.get("valence", 0.5)),
                  "arousal": float(body.get("arousal", 0.6)),
                  "confidence": 1.0, "face_visible": True, "err": None,
                  "evidence": "manual inject"}
            publish(self.responder.respond(st),
                    speak_reason="manual_inject", frame_tag="inject")
            set_status(perception=st)
            self._send(200, json.dumps({"ok": True, "seq":
                                        LATEST["payload"]["seq"]}).encode())
        elif path == "/live/persona":
            p = str(body.get("persona", "")).lower()
            if p not in PERSONAS:
                self._send(400, json.dumps(
                    {"err": f"unknown persona, 可选: {list(PERSONAS)}"}
                ).encode())
                return
            set_status(persona=p)
            LOGGER.log("persona_set", persona=p)
            speak_text(PERSONAS[p]["greeting"], "neutral", "persona")
            self._send(200, json.dumps(
                {"ok": True, "persona": p,
                 "name_cn": PERSONAS[p]["name_cn"],
                 "voice": PERSONAS[p]["voice"]}).encode())
        elif path == "/live/sleep":
            speak_text("好的，我休息了。想叫我的时候，说「打开lamp」就行。",
                       "neutral", "sleep")
            _sleep_lamp("api")
            self._send(200, json.dumps({"ok": True, "sleeping": True}).encode())
        elif path == "/live/wake":
            _wake_lamp("api")
            self._send(200, json.dumps({"ok": True, "sleeping": False}).encode())
        elif path == "/live/shutdown":
            LOGGER.log("shutdown", source="api")
            speak_text("好的，lamp 系统关闭，再见。", "neutral", "shutdown")
            self._send(200, json.dumps({"ok": True, "bye": True}).encode())
            threading.Timer(3.0, lambda: os._exit(0)).start()
        elif path == "/live/voice":
            voice = body.get("voice") or None
            style = body.get("style")
            style = style.strip() if isinstance(style, str) \
                and style.strip() else None
            set_status(voice_override=voice, style_override=style)
            LOGGER.log("voice_set", voice=voice, style=style)
            self._send(200, json.dumps({"ok": True, "voice_override": voice,
                                        "style_override": style}).encode())
        elif path == "/live/reminder":
            text = str(body.get("text", "")).strip()
            r = add_reminder(text, "viewer") if text else None
            self._send(200 if r else 400,
                       json.dumps(r or {"err": "无法解析提醒"}).encode())
        elif path == "/live/reminder/cancel":
            rid = body.get("id")
            with _state_lock:
                before = len(STATE["reminders"])
                STATE["reminders"] = [r for r in STATE["reminders"]
                                      if rid and r["id"] != rid] if rid else []
                n = before - len(STATE["reminders"])
            LOGGER.log("reminder_cancel", id=rid, cancelled=n)
            self._send(200, json.dumps({"ok": True, "cancelled": n}).encode())
        else:
            self._send(404, json.dumps({"err": "unknown path"}).encode())


def main():
    global LOGGER
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8318)
    ap.add_argument("--interval", type=float, default=3.0)
    ap.add_argument("--no-camera", action="store_true")
    ap.add_argument("--no-asr", action="store_true")
    ap.add_argument("--mute", action="store_true", help="TTS 只存 wav 不播喇叭")
    args = ap.parse_args()

    os.makedirs(AUDIO_DIR, exist_ok=True)
    FLAGS["mute"] = args.mute
    FLAGS["no_asr"] = args.no_asr

    from e1_logger import RunLogger
    LOGGER = RunLogger()
    set_status(log_dir=LOGGER.dir)

    from e1_responder import Responder
    responder = Responder()
    Handler.responder = responder

    threading.Thread(target=tts_worker, daemon=True).start()
    threading.Thread(target=reply_worker, daemon=True).start()
    threading.Thread(target=reminder_loop, daemon=True).start()
    threading.Thread(target=perception_loop,
                     args=(responder, args.interval, args.no_camera),
                     daemon=True).start()
    if not args.no_asr:
        from e1_asr import AsrWorker
        def _asr_err(msg):
            set_status(last_error=msg)
            LOGGER.log("error", where="asr", err=msg)
        AsrWorker(lambda t: on_user_sentence(t, responder), _asr_err).start()
        set_status(asr_ok=True)

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"[live_bridge] http://127.0.0.1:{args.port}/  "
          f"(interval={args.interval}s, "
          f"camera={'off' if args.no_camera else 'on'}, "
          f"asr={'off' if args.no_asr else 'on'}, "
          f"speaker={'mute' if args.mute else 'on'})")
    print(f"[live_bridge] log dir: {LOGGER.dir}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[live_bridge] stopped")


if __name__ == "__main__":
    main()
