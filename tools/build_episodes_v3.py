# -*- coding: utf-8 -*-
"""P0-data：episodes_v3 构建器（2026-10-03 用户确认后开工）。

数据源：EmpatheticDialogues（CC-BY-4.0，ParlAI 镜像，data/external/empatheticdialogues/）
V/A 标注：NRC VAD Lexicon v1（非商业研究用途，data/external/NRC-VAD-Lexicon.txt）

每条 episode = 真实场景句（ED situation，英文）+ 真实情绪标签（32→7 归并）
             + contract v1.1 生成轨迹（轨迹仍为参数化合成，provenance 诚实标注）。

确认记录（dataset_strategy.md §6.6）：
  Q1 归并表认可；Q2 混合方案（anticipating→curious，label_confidence=low）；
  Q3 NRC VAD；Q4 总量 ≥1000（每类上限 160，7×160=1120 上限）。

用法（LeLampEmpathy 根目录）：
    python tools/build_episodes_v3.py            # 生成 data/episodes/episodes_v3.jsonl
"""
import csv
import json
import os
import re
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import ZERO, CONTROL_HZ
from primitives.engine import render
from primitives import library as lib
from tools.gen_episodes import jitter_primitives, VA_TABLE, GESTURES

ED_DIR = os.path.join("data", "external", "empatheticdialogues")
VAD_PATH = os.path.join("data", "external", "NRC-VAD-Lexicon.txt")
OUT_PATH = os.path.join("data", "episodes", "episodes_v3.jsonl")
STORE_HZ = 10
SEED = 42
PER_CLASS_CAP = 160          # 7 × 160 = 1120 上限（用户要求 ≥1000）
TEST_FRAC = 0.2
VA_MIN_COVER = 0.20          # 低于此覆盖率回退规则质心

# 用户确认的 32→7 归并表（dataset_strategy.md §6.5）
EMOTION_MAP = {
    "joy":     ["joyful", "excited", "content", "proud", "hopeful",
                "confident", "prepared"],
    "sad":     ["sad", "devastated", "lonely", "disappointed", "guilty",
                "ashamed", "nostalgic", "embarrassed"],
    "angry":   ["angry", "furious", "annoyed", "disgusted", "jealous"],
    "fear":    ["afraid", "anxious", "terrified", "apprehensive"],
    "love":    ["loving", "caring", "grateful", "faithful", "trusting",
                "sentimental"],
    "surprise": ["surprised", "impressed"],
    # 契约 7 类的第 7 类名为 neutral（探索/好奇本能，emotions_catalog §3）；
    # anticipating→curious(exploration) 即此类，低置信（混合方案 Q2）。
    "neutral": ["anticipating"],
}
LABEL2EMO = {lab: emo for emo, labs in EMOTION_MAP.items() for lab in labs}
LOW_CONF_LABELS = {"anticipating"}
# neutral 类的响应程序：响应式手势版 curious（侧头注视=roll+yaw）
NEUTRAL_VIA_GESTURE = "curious"


# ---------------- 数据读取 ----------------

def load_ed_pool():
    """按 conversation 去重：取每个 conv 的开场句（utterance_idx==1，
    其 prompt 即 situation 场景句）。注意 speaker_idx 是工人 ID（非 0/1 角色），
    不能用作过滤条件。"""
    pool = {}
    for split in ("train", "valid", "test"):
        with open(os.path.join(ED_DIR, f"{split}.csv"), encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["utterance_idx"] != "1":
                    continue
                cid = row["conv_id"]
                if cid in pool:
                    continue
                scene = row["prompt"].replace("_comma_", ",").strip()
                if len(scene) < 10:
                    continue
                pool[cid] = {"conv_id": cid, "ed_label": row["context"],
                             "scene_en": scene, "ed_split": split}
    return list(pool.values())


# ---------------- NRC VAD ----------------

_TOKEN_RE = re.compile(r"[a-z']+")


def load_vad(path):
    vad = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 4:
                continue
            w, v, a, d = parts
            try:
                # NRC VAD v1 量程 [0,1] → 归一到 [-1,1]
                vad[w] = (float(v) * 2 - 1, float(a) * 2 - 1, float(d) * 2 - 1)
            except ValueError:
                continue
    return vad


def vad_score(text, vad):
    toks = _TOKEN_RE.findall(text.lower())
    hits = [vad[t] for t in toks if t in vad]
    cover = len(hits) / max(1, len(toks))
    if not hits:
        return None, None, None, cover
    arr = np.mean(np.asarray(hits), axis=0)
    return float(arr[0]), float(arr[1]), float(arr[2]), cover


def make_annotation(scene_en, emo, vad):
    v, a, d, cover = vad_score(scene_en, vad)
    if v is None or cover < VA_MIN_COVER:
        va_key = NEUTRAL_VIA_GESTURE if emo == "neutral" else emo
        v0, a0 = VA_TABLE[va_key]
        return {"valence": v0, "arousal": a0, "dominance": 0.0,
                "method": "rule_based_v1_fallback", "va_coverage": round(cover, 3),
                "reviewed": False}
    return {"valence": round(v, 3), "arousal": round(a, 3),
            "dominance": round(d, 3), "method": "nrc_vad_v1",
            "va_coverage": round(cover, 3), "reviewed": False}


# ---------------- episode 组装 ----------------

# v3.1 每情绪运动预算（QC review R1）：(max_dq rad/step, max_ddq rad/step^2) @50Hz
# sad/love 最慢（共情安抚），fear/surprise 允许快但仍 capped。
MOTION_BUDGET = {
    "sad":      (0.020, 0.010),   # 1.0 rad/s, 25 rad/s^2
    "love":     (0.020, 0.010),
    "neutral":  (0.024, 0.012),   # 1.2 rad/s
    "joy":      (0.030, 0.016),   # 1.5 rad/s, 40 rad/s^2
    "angry":    (0.036, 0.024),   # 1.8 rad/s
    "surprise": (0.044, 0.032),   # 2.2 rad/s, 80 rad/s^2
    "fear":     (0.044, 0.032),
}


def _assert_ascii(s, field, eid):
    if s and any(ord(c) > 127 for c in s):
        raise ValueError(f"non-ASCII {field} in {eid}: {s!r}")


def build_episode(eid, item, emo, split, vad, seed):
    rng = np.random.default_rng(seed)
    if emo == "neutral":
        # 探索/期待（anticipating）→ 响应式手势版 curious：侧头注视
        g = GESTURES[NEUTRAL_VIA_GESTURE]
        prims = jitter_primitives(g["primitives"](), rng)
        led, caption, gamma, program = g["led"], g["line"], None, NEUTRAL_VIA_GESTURE
    else:
        spec = lib.EMOTIONS[emo]
        prims = jitter_primitives(spec["primitives"](), rng)
        led, caption, gamma, program = (spec["led"], spec["caption"],
                                        spec["gamma"], emo)
    _assert_ascii(caption, "caption", eid)
    dq, ddq = MOTION_BUDGET[emo]
    traj = render(prims, max_dq=dq, max_ddq=ddq)
    t, q = traj["t"], traj["q"]
    step = max(1, CONTROL_HZ // STORE_HZ)
    return {
        "episode_id": eid,
        "category": "empathy",
        "split": split,
        "scene_text": "",                      # 中文后置翻译（v3.1 任务）
        "scene_text_en": item["scene_en"],
        "human_emotion": emo,
        "annotation": make_annotation(item["scene_en"], emo, vad),
        "response": {
            "program": program,
            "primitives": [p.name for p in prims],
            "trajectory": {
                "hz": STORE_HZ,
                "duration_s": round(float(t[-1]), 3),
                "base_pose": [round(float(v), 5) for v in ZERO],
                "q": [[round(float(v), 4) for v in row] for row in q[::step]],
            },
            "led": led,
            "caption": caption,
            "gamma": gamma,
        },
        "quality": traj["info"],
        "source": {
            "dataset": "EmpatheticDialogues",
            "conv_id": item["conv_id"],
            "ed_label": item["ed_label"],
            "label_confidence": ("low" if item["ed_label"] in LOW_CONF_LABELS
                                 else "normal"),
        },
        "provenance": {
            "text": "EmpatheticDialogues situation (CC-BY-4.0)",
            "va": "NRC-VAD-Lexicon v1 (non-commercial research)",
            "trajectory": "synthetic:parametric_library_v1+jitter",
            "seed": seed,
        },
    }


def main():
    pool = load_ed_pool()
    vad = load_vad(VAD_PATH)
    rng = np.random.default_rng(SEED)

    # 按目标类分桶（保留子标签，用于多样性轮抽）
    buckets = defaultdict(lambda: defaultdict(list))   # emo -> ed_label -> items
    for it in pool:
        emo = LABEL2EMO.get(it["ed_label"])
        if emo:
            buckets[emo][it["ed_label"]].append(it)

    # 每类：跨子标签轮抽至 cap（保证 32 标签多样性）
    selected = {}
    for emo, by_lab in buckets.items():
        for items in by_lab.values():
            rng.shuffle(items)
        picked, labs = [], sorted(by_lab)
        i = 0
        while len(picked) < PER_CLASS_CAP:
            lab = labs[i % len(labs)]
            if by_lab[lab]:
                picked.append(by_lab[lab].pop())
            i += 1
            if all(not v for v in by_lab.values()):
                break
        selected[emo] = picked

    # conversation 级分层 80/20
    episodes, n = [], 0
    for emo in EMOTION_MAP:
        items = selected.get(emo, [])
        rng.shuffle(items)
        k = int(round(len(items) * (1 - TEST_FRAC)))
        for split, chunk in (("train", items[:k]), ("test", items[k:])):
            for it in chunk:
                n += 1
                episodes.append(build_episode(
                    f"ed_{emo}_{n:04d}", it, emo, split, vad, SEED + n))

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for e in episodes:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ---- 摘要 ----
    print(f"ED pool (dedup conversations): {len(pool)}")
    print(f"NRC VAD entries: {len(vad)}")
    print(f"episodes written: {len(episodes)}  -> {OUT_PATH} "
          f"({os.path.getsize(OUT_PATH)/1e6:.2f} MB)")
    print(f"{'class':<10}{'train':>6}{'test':>6}{'sub-labels':>12}"
          f"{'mean_V':>8}{'mean_A':>8}{'cov':>6}")
    for emo in EMOTION_MAP:
        es = [e for e in episodes if e["human_emotion"] == emo]
        tr = sum(1 for e in es if e["split"] == "train")
        sub = len({e["source"]["ed_label"] for e in es})
        mv = np.mean([e["annotation"]["valence"] for e in es]) if es else 0
        ma = np.mean([e["annotation"]["arousal"] for e in es]) if es else 0
        mc = np.mean([e["annotation"]["va_coverage"] for e in es]) if es else 0
        print(f"{emo:<10}{tr:>6}{len(es)-tr:>6}{sub:>12}"
              f"{mv:>8.3f}{ma:>8.3f}{mc:>6.2f}")
    bad = [e["episode_id"] for e in episodes if not e["quality"]["limits_ok"]]
    fb = sum(1 for e in episodes
             if e["annotation"]["method"] == "rule_based_v1_fallback")
    lowc = sum(1 for e in episodes
               if e["source"]["label_confidence"] == "low")
    print(f"limits_ok: {len(episodes)-len(bad)}/{len(episodes)}"
          + (f"  越限: {bad[:5]}..." if bad else ""))
    print(f"V/A fallback(rule): {fb}   low-confidence(curious): {lowc}")


if __name__ == "__main__":
    main()
