# -*- coding: utf-8 -*-
"""E1.5 运行日志：每次启动一个目录，按 日期_时分秒 命名。

目录结构（root = LeLampEmpathy/logs/）：
  live_2026-10-04_181530/
    events.jsonl        # 全部事件，一行一条：{"ts":..., "kind":..., ...}
    frames/             # 事件相关摄像头帧（asr/alert/inject/reminder 时保存）
      181533_asr.jpg

事件 kind：perception（每轮情绪判定）/ asr（语音识别句）/ response（lamp 响应，
含 episode、caption、pose 摘要）/ tts / inject / reminder_add / reminder_fire /
error / startup
"""
import json
import os
import threading
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_ROOT = os.path.join(ROOT, "logs")


class RunLogger:
    def __init__(self, root=LOGS_ROOT):
        ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        self.dir = os.path.join(root, f"live_{ts}")
        self.frames = os.path.join(self.dir, "frames")
        os.makedirs(self.frames, exist_ok=True)
        self.events_path = os.path.join(self.dir, "events.jsonl")
        self._lock = threading.Lock()
        self.log("startup", log_dir=self.dir)

    def log(self, kind, **kw):
        rec = {"ts": datetime.now().isoformat(timespec="milliseconds"),
               "kind": kind, **kw}
        line = json.dumps(rec, ensure_ascii=False)
        with self._lock:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return rec

    def save_frame(self, jpg, tag):
        """保存摄像头帧 → 相对 log 目录的文件名（写进事件记录）。"""
        if not jpg:
            return None
        fn = f"frames/{datetime.now().strftime('%H%M%S')}_{tag}.jpg"
        path = os.path.join(self.dir, fn)
        with self._lock:
            with open(path, "wb") as f:
                f.write(jpg)
        return fn


def pose_summary(episode):
    """响应 pose 摘要：首/末关节角 + 时长 + 预算合规。"""
    tr = (episode.get("response") or {}).get("trajectory") or {}
    q = tr.get("q") or []
    return {"episode_id": episode.get("episode_id"),
            "duration_s": tr.get("duration_s"),
            "hz": tr.get("hz"),
            "q_first": q[0] if q else None,
            "q_last": q[-1] if q else None,
            "limits_ok": (episode.get("quality") or {}).get("limits_ok")}
