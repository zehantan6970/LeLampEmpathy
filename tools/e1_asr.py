# -*- coding: utf-8 -*-
"""E1.5 ASR 语音通道：麦克风 → paraformer-realtime-v2 流式识别。

on_sentence(text) —— 一句说完（VAD 自动断句）回调；on_error(msg) 错误回调。
线程内自动重连。用法见 live_bridge.py。
"""
import threading
import time

from env_config import load_llm_config

_cfg = load_llm_config()
MODEL = "paraformer-realtime-v2"
SAMPLE_RATE = 16000
BLOCK = 3200  # 100ms @16kHz


class AsrWorker(threading.Thread):
    def __init__(self, on_sentence, on_error=None):
        super().__init__(daemon=True)
        self.on_sentence = on_sentence
        self.on_error = on_error or (lambda m: None)
        self._stop_flag = threading.Event()

    def stop(self):
        self._stop_flag.set()

    def run(self):
        import dashscope
        dashscope.api_key = _cfg["DASHSCOPE_API_KEY"]
        while not self._stop_flag.is_set():
            try:
                self._session()
            except Exception as e:  # noqa: BLE001
                self.on_error(f"asr_session: {type(e).__name__}: {e}")
            if not self._stop_flag.is_set():
                time.sleep(3)  # 重连间隔

    def _session(self):
        import sounddevice as sd
        from dashscope.audio.asr import (Recognition, RecognitionCallback,
                                         RecognitionResult)
        worker = self

        class CB(RecognitionCallback):
            def on_open(self):
                pass

            def on_event(self, result):
                try:
                    sent = result.get_sentence()
                    if sent and sent.get("text") and \
                            RecognitionResult.is_sentence_end(sent):
                        worker.on_sentence(sent["text"].strip())
                except Exception as e:  # noqa: BLE001
                    worker.on_error(f"asr_event: {e}")

            def on_error(self, message):
                worker.on_error(f"asr_srv: {message}")

            def on_close(self):
                pass

        rec = Recognition(model=MODEL, format="pcm",
                          sample_rate=SAMPLE_RATE, callback=CB())
        rec.start()
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="int16", blocksize=BLOCK) as stream:
            while not self._stop_flag.is_set():
                data, overflowed = stream.read(BLOCK)
                rec.send_audio_frame(data.tobytes())
        rec.stop()
