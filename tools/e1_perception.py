# -*- coding: utf-8 -*-
"""E1.1 视觉情绪通道：摄像头 → qwen-vl-max → 7 类情绪 JSON（含防抖滤波）。

模块函数供 live_bridge 调用；也可单独自测：
  .venv/Scripts/python.exe tools/e1_perception.py --rounds 3 --interval 2
"""
import argparse
import base64
import json
import os
import time

import cv2

from env_config import load_llm_config

EMOTIONS = ["joy", "sad", "angry", "fear", "love", "surprise", "neutral"]
CONF_THRESHOLD = 0.5          # 低于此置信度 → neutral
HYSTERESIS_N = 2              # 连续 N 次一致才切换（防抖）

PROMPT = """You are the emotion-recognition module of an empathetic desk lamp.
Look at the person in the image and judge their current emotion.

Output STRICT JSON only (no markdown, no extra text):
{"emotion": "<one of: joy|sad|angry|fear|love|surprise|neutral>",
 "valence": <float 0..1, unpleasant..pleasant>,
 "arousal": <float 0..1, calm..excited>,
 "confidence": <float 0..1>,
 "face_visible": <true|false>,
 "evidence": "<=20 chars brief cue>"}

Criteria:
- joy: smiling, happy, amused
- sad: frowning, downcast, tearful, disappointed
- angry: brows furrowed, hostile, frustrated
- fear: wide eyes, tense, scared, anxious
- love: warm, tender, affectionate expression
- surprise: raised brows, open mouth, astonished
- neutral: calm, no clear emotion
If no human face is visible: face_visible=false and emotion="neutral"."""


# ── 摄像头 ──────────────────────────────────────────────────────────────────
class Camera:
    def __init__(self, device=0, width=640, height=480):
        self.cap = cv2.VideoCapture(device, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        if not self.cap.isOpened():
            raise RuntimeError(f"摄像头 device={device} 打不开")

    def grab_jpeg(self, quality=80):
        """抓一帧 → JPEG bytes；失败返回 None。"""
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame,
                               [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def release(self):
        self.cap.release()


# ── qwen-vl 情绪判定 ─────────────────────────────────────────────────────────
_cfg = load_llm_config()


def judge_emotion(jpeg_bytes, model="qwen-vl-max", timeout=30):
    """JPEG → 情绪 dict。任何异常返回 neutral 兜底（err 字段带原因）。"""
    import dashscope
    from dashscope import MultiModalConversation
    dashscope.api_key = _cfg["DASHSCOPE_API_KEY"]
    b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    msg = [{"role": "user", "content": [
        {"image": f"data:image/jpeg;base64,{b64}"},
        {"text": PROMPT}]}]
    t0 = time.time()
    try:
        resp = MultiModalConversation.call(model=model, messages=msg,
                                           result_format="message")
    except Exception as e:  # noqa: BLE001
        return _fallback(f"api_exc:{type(e).__name__}")
    latency = time.time() - t0
    if resp.status_code != 200:
        return _fallback(f"api_{resp.status_code}:{getattr(resp,'code','?')}")
    try:
        text = resp.output.choices[0].message.content
        if isinstance(text, list):           # 部分版本返回 content 列表
            text = "".join(c.get("text", "") for c in text)
        parsed = _parse_json(text)
    except Exception as e:  # noqa: BLE001
        return _fallback(f"parse:{type(e).__name__}:{str(text)[:80]}")
    parsed["latency_ms"] = int(latency * 1000)
    parsed["raw_model"] = model
    return parsed


def _parse_json(text):
    text = text.strip()
    if text.startswith("```"):               # 剥 markdown 围栏
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    d = json.loads(text)
    emo = str(d.get("emotion", "neutral")).lower().strip()
    if emo not in EMOTIONS:
        emo = "neutral"
    clip = lambda x: max(0.0, min(1.0, float(x)))
    return {"emotion": emo,
            "valence": clip(d.get("valence", 0.5)),
            "arousal": clip(d.get("arousal", 0.5)),
            "confidence": clip(d.get("confidence", 0.5)),
            "face_visible": bool(d.get("face_visible", True)),
            "evidence": str(d.get("evidence", ""))[:40],
            "err": None}


def _fallback(err):
    return {"emotion": "neutral", "valence": 0.5, "arousal": 0.3,
            "confidence": 0.0, "face_visible": False, "evidence": "",
            "err": err, "latency_ms": -1, "raw_model": None}


# ── 防抖/阈值滤波 ─────────────────────────────────────────────────────────────
class EmotionFilter:
    """conf<阈值→neutral；连续 HYSTERESIS_N 次一致才提交切换。"""

    def __init__(self):
        self.committed = "neutral"
        self._pending = None
        self._pending_count = 0

    def update(self, raw):
        prev = self.committed
        emo = raw["emotion"]
        if not raw["face_visible"] or raw["confidence"] < CONF_THRESHOLD:
            emo = "neutral"
        if emo == self.committed:
            self._pending = None
            self._pending_count = 0
        elif emo == self._pending:
            self._pending_count += 1
            if self._pending_count >= HYSTERESIS_N:
                self.committed = emo
                self._pending = None
                self._pending_count = 0
        else:
            self._pending = emo
            self._pending_count = 1
        out = dict(raw)
        out["filtered_emotion"] = self.committed
        out["switched"] = self.committed != prev
        return out


# ── 自测 ─────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--model", default="qwen-vl-max")
    args = ap.parse_args()

    cam = Camera()
    filt = EmotionFilter()
    print(f"[e1.1] 摄像头已开，{args.rounds} 轮 × 间隔 {args.interval}s")
    try:
        for i in range(args.rounds):
            jpg = cam.grab_jpeg()
            if jpg is None:
                print(f"[{i}] 抓帧失败")
                continue
            raw = judge_emotion(jpg, model=args.model)
            out = filt.update(raw)
            print(f"[{i}] {json.dumps(out, ensure_ascii=False)}")
            if i + 1 < args.rounds:
                time.sleep(args.interval)
    finally:
        cam.release()


if __name__ == "__main__":
    main()
