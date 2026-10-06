# -*- coding: utf-8 -*-
"""B1 demo: render all 7 emotion programs -> pose CSVs + episode records.

Outputs (contract §5 conformant):
    dataset/episodes/ep_<emotion>_v1_pose.csv   (t, q0..q4 @50Hz)
    dataset/episodes/ep_<emotion>_v1.json       (episode record)
Prints a validation report (limits / rate / smoothness / duration).

Usage:  python tools/demo_b1.py
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import ZERO, MAX_DQ_PER_STEP  # noqa: E402
from primitives.engine import render  # noqa: E402
from primitives.library import EMOTIONS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dataset", "episodes")
os.makedirs(OUT, exist_ok=True)


def main():
    print(f"{'emotion':<10} {'dur(s)':>7} {'steps':>6} {'max|dq|':>9} "
          f"{'stretch':>8} {'limits':>7} {'jerk2':>8}")
    all_ok = True
    for name, spec in EMOTIONS.items():
        base = ZERO + spec["base"]
        traj = render(spec["primitives"](), base_pose=base)
        info = traj["info"]
        eid = f"ep_{name}_v1"
        pose_path = os.path.join(OUT, f"{eid}_pose.csv")
        with open(pose_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "q0", "q1", "q2", "q3", "q4"])
            for i in range(len(traj["t"])):
                w.writerow([f"{traj['t'][i]:.3f}"]
                           + [f"{v:.5f}" for v in traj["q"][i]])
        record = {
            "id": eid,
            "human_input": {"text": None, "emotion": name,
                            "valence": None, "arousal": None,
                            "intensity": None},
            "fly_instinct": None,
            "gamma": spec["gamma"],
            "expression": {
                "primitives": [p.name for p in spec["primitives"]()],
                "pose_seq": f"episodes/{eid}_pose.csv",
                "led": spec["led"],
                "caption": spec["caption"],
                "tts_style": spec["tts_style"],
            },
            "provenance": {"source": "manual",
                           "source_url": None, "license": "GPL-3.0",
                           "annotator": "workbuddy-b1-library",
                           "reviewed": False,
                           "collected_at": "2026-09-30"},
        }
        with open(os.path.join(OUT, f"{eid}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        ok = info["limits_ok"] and info["max_dq"] <= MAX_DQ_PER_STEP + 1e-9
        all_ok &= ok
        print(f"{name:<10} {traj['t'][-1]:>7.2f} {len(traj['t']):>6} "
              f"{info['max_dq']:>9.4f} {info['stretch']:>8.2f} "
              f"{'OK' if info['limits_ok'] else 'FAIL':>7} "
              f"{info['max_jerk_step2']:>8.4f}")
    print(f"\nvalidation: {'ALL PASS' if all_ok else 'SOME FAILED'}  "
          f"(rate limit {MAX_DQ_PER_STEP} rad/step @50Hz)")
    print(f"episodes written to {OUT}")


if __name__ == "__main__":
    main()
