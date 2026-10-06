# -*- coding: utf-8 -*-
"""E1.0 环境自检：依赖导入 / .env 三件套 / Qwen API 连通 / 摄像头 / 音频设备。

用法: .venv/Scripts/python.exe tools/e1_env_check.py
退出码: 0 = 全部通过（音频设备缺失仅警告，不阻断——可在无麦环境先跑视觉通道）
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from env_config import load_llm_config  # noqa: E402

results = []  # (name, ok, detail)


def check(name):
    def deco(fn):
        try:
            detail = fn()
            results.append((name, True, detail))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))
        return None
    return deco


@check("依赖导入")
def _():
    import dashscope  # noqa: F401
    import dotenv  # noqa: F401
    import websocket  # noqa: F401
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    import aiohttp  # noqa: F401
    import sounddevice  # noqa: F401
    import dashscope as ds
    return f"dashscope={ds.version.__version__ if hasattr(ds,'version') else '?'}"


@check(".env 三件套")
def _():
    cfg = load_llm_config()
    missing = [k for k in ("DASHSCOPE_API_KEY", "WORKSPACE_ID", "APP_ID")
               if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"缺少键: {missing}")
    key = cfg["DASHSCOPE_API_KEY"]
    return f"key={key[:6]}...{key[-4:]} (len={len(key)}), WORKSPACE_ID/APP_ID 就位"


@check("Qwen API 连通 (qwen-turbo ping)")
def _():
    import dashscope
    cfg = load_llm_config()
    dashscope.api_key = cfg["DASHSCOPE_API_KEY"]
    from dashscope import Generation
    t0 = time.time()
    resp = Generation.call(model="qwen-turbo",
                           messages=[{"role": "user", "content": "reply with the single word: ok"}],
                           max_tokens=8, result_format="message")
    dt = time.time() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"status={resp.status_code} code={resp.code} msg={resp.message}")
    text = resp.output.choices[0].message.content
    return f"status=200, {dt:.2f}s, reply={text[:30]!r}"


@check("摄像头抓帧 (cv2 device 0)")
def _():
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise RuntimeError("VideoCapture(0) 打不开")
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise RuntimeError("打开了但读不到帧")
    h, w = frame.shape[:2]
    return f"frame={w}x{h}"


@check("音频设备枚举")
def _():
    import sounddevice as sd
    devs = sd.query_devices()
    n_in = sum(1 for d in devs if d["max_input_channels"] > 0)
    n_out = sum(1 for d in devs if d["max_output_channels"] > 0)
    if n_in == 0 or n_out == 0:
        raise RuntimeError(f"输入设备 {n_in} / 输出设备 {n_out}")
    default = sd.default.device
    return f"输入x{n_in} 输出x{n_out}, 默认设备={default}"


def main():
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")
    n_fail = sum(1 for _, ok, _ in results if not ok)
    audio_fail = any((not ok) and "音频" in n for n, ok, _ in results)
    hard_fail = n_fail - (1 if audio_fail and n_fail == 1 else 0)
    print("-" * 60)
    if hard_fail == 0:
        print("E1.0 自检通过" + ("（音频设备缺失仅警告）" if audio_fail else ""))
        sys.exit(0)
    print(f"E1.0 存在 {hard_fail} 项硬失败")
    sys.exit(1)


if __name__ == "__main__":
    main()
