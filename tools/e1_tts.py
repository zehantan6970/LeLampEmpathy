# -*- coding: utf-8 -*-
"""E1.4 TTS 模块：Qwen TTS API 直接合成（CosyVoice-v3-Flash）→ wav + 喇叭播放。

每情绪默认音色（viewer 可覆盖，见设计文档 §5）：
  joy/surprise → longfeifei_v3（明亮）   sad/love → longanshuo_v3（舒缓）
  angry/fear   → longanyang（低沉）      neutral  → longanhuan（中性）

自测：.venv/Scripts/python.exe tools/e1_tts.py --text "Glad to interact with you!" --emotion joy --play
"""
import argparse
import os
import time

from env_config import load_llm_config

_cfg = load_llm_config()

MODEL = "cosyvoice-v3-flash"
VOICE_BY_EMOTION = {
    "joy": "longfeifei_v3", "surprise": "longfeifei_v3",
    "sad": "longanshuo_v3", "love": "longanshuo_v3",
    "angry": "longanyang", "fear": "longanyang",
    "neutral": "longanhuan",
}
# 说话风格 = 语速(speech_rate) + 音调(pitch_rate)。
# 注：cosyvoice-v3-flash 不支持自然语言 instruction（实测 error 428），
#     风格用韵律参数实现；每情绪有默认，viewer 可用预设风格覆盖。
PROSODY_BY_EMOTION = {          # (speech_rate, pitch_rate)
    "joy": (1.1, 1.1), "surprise": (1.15, 1.1),
    "sad": (0.85, 0.9), "love": (0.9, 1.0),
    "angry": (1.0, 0.9), "fear": (1.15, 1.05),
    "neutral": (1.0, 1.0),
}
STYLE_PRESETS = {               # viewer 可选风格 → (speech_rate, pitch_rate)
    "开朗轻快": (1.1, 1.1),
    "温柔安慰": (0.85, 0.95),
    "沉稳平静": (0.95, 0.9),
    "活泼惊讶": (1.2, 1.1),
    "缓慢低沉": (0.8, 0.85),
}
DEFAULT_VOICE = "longanhuan"


def voice_for(emotion, override=None):
    if override:
        return override
    return VOICE_BY_EMOTION.get(str(emotion).lower(), DEFAULT_VOICE)


def prosody_for(emotion, style_override=None):
    if style_override and style_override in STYLE_PRESETS:
        return STYLE_PRESETS[style_override], f"preset:{style_override}"
    return PROSODY_BY_EMOTION.get(str(emotion).lower(), (1.0, 1.0)), \
        f"emo:{emotion}"


def synthesize_wav(text, emotion="neutral", voice_override=None,
                   style_override=None, persona=None):
    """文本 → wav bytes（24kHz mono 16bit）。失败返回 (None, err)。

    style_override：STYLE_PRESETS 中的风格名；None=按情绪默认韵律。
    persona：人设 dict（含 voice/speech_rate/pitch_rate）；人设韵律与
    情绪韵律相乘（clamp 0.5~2.0），voice_override > persona.voice > 情绪默认。
    """
    import dashscope
    from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer
    dashscope.api_key = _cfg["DASHSCOPE_API_KEY"]
    voice = voice_for(emotion, voice_override or (persona or {}).get("voice"))
    (rate, pitch), style_desc = prosody_for(emotion, style_override)
    if persona and not style_override:
        rate = min(2.0, max(0.5, rate * float(persona.get("speech_rate", 1.0))))
        pitch = min(2.0, max(0.5, pitch * float(persona.get("pitch_rate", 1.0))))
        style_desc += "+persona"
    t0 = time.time()
    try:
        synth = SpeechSynthesizer(
            model=MODEL, voice=voice,
            format=AudioFormat.WAV_24000HZ_MONO_16BIT,
            speech_rate=rate, pitch_rate=pitch)
        audio = synth.call(text)
        latency = time.time() - t0
        if not audio:
            return None, f"empty audio (model={MODEL} voice={voice})"
        return bytes(audio), {"voice": voice, "model": MODEL,
                              "style": style_desc,
                              "speech_rate": rate, "pitch_rate": pitch,
                              "latency_ms": int(latency * 1000),
                              "bytes": len(audio)}
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def play_wav(wav_bytes):
    """pyaudio 播喇叭（24kHz mono 16bit）。跳过 44 字节 wav 头。"""
    import pyaudio
    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1,
                     rate=24000, output=True)
    try:
        stream.write(wav_bytes[44:])
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="Glad to interact with you!")
    ap.add_argument("--emotion", default="joy")
    ap.add_argument("--voice", default=None)
    ap.add_argument("--play", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    wav, info = synthesize_wav(args.text, args.emotion, args.voice)
    if wav is None:
        print(f"[e1.4] 合成失败: {info}")
        raise SystemExit(1)
    print(f"[e1.4] 合成成功: {info}")
    if args.out:
        with open(args.out, "wb") as f:
            f.write(wav)
        print(f"[e1.4] 已保存 → {args.out}")
    if args.play:
        print("[e1.4] 播放中…")
        play_wav(wav)
        print("[e1.4] 播放完成")


if __name__ == "__main__":
    main()
