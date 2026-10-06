# -*- coding: utf-8 -*-
"""B1 共情 episode 数据集生成器（2026-10-02 拍板开工）。

每条 episode = {
  场景文本 scene_text, 人类情绪标签 human_emotion,
  台灯响应 response = {5-DOF 轨迹 + RGBW 灯光 + 台词 caption}
}

两类 episode：
  A. 共情程序（7 情绪 × 8 场景 = 56 条）：library.EMOTIONS 参数化程序，
     每条加幅度/时标抖动（±15% / ±10%）产生变体。
  B. 响应式手势（4 手势 × 6 措辞 = 24 条）：对用户话语的直接反应——
     nod（点头·肯定）、shake（摇头·否定）、curious（好奇·侧头注视）、
     startle（惊吓·猛烈扭头远离 + 高频红闪）。
     这 4 条是用户指定的「好懂、好测、好实现」的最小闭环。

轨迹经 engine.render()（Catmull-Rom + 限幅 + 限速时间拉伸），
JSONL 中以 10 Hz 重采样存储（原始 50 Hz 可由种子复现）。

用法（LeLampEmpathy 根目录）：
    python tools/gen_episodes.py            # 生成 data/episodes/episodes_v1.jsonl
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configs.joints import ZERO, CONTROL_HZ
from primitives.engine import Primitive, render
from primitives import library as lib

OUT_PATH = os.path.join("data", "episodes", "episodes_v2.jsonl")
STORE_HZ = 10                      # JSONL 重采样率
AMP_JITTER, TIME_JITTER = 0.15, 0.10

# ---------------- A 类：共情场景模板（每情绪 8 条） ----------------

SCENARIOS = {
    "joy":     ["用户笑着分享今天升职的消息", "用户哼着歌走近台灯",
                "用户说『今天天气真好啊』", "用户展示刚完成的画作",
                "用户打游戏赢了，挥了一下拳", "用户收到朋友的礼物并道谢",
                "用户说『周末要去露营，太期待了』", "用户逗猫时笑出了声",
                "用户的项目终于跑通了，长舒一口气", "用户发现喜欢的博主更新了视频"],
    "love":    ["用户轻声说『有你陪着真好』", "用户深夜加班时摸了摸台灯",
                "用户对台灯说『晚安』", "用户和远方的家人视频通话",
                "用户抱着宠物坐在桌前", "用户说『今天好想有人陪陪』",
                "用户精心擦拭台灯外壳", "用户对台灯说『明天也拜托你啦』",
                "用户给台灯旁边放了一小盆绿植", "用户生病时裹着毯子坐在灯下"],
    "angry":   ["用户摔下鼠标抱怨工作", "用户大声说『别烦我！』",
                "用户看到坏消息后猛拍桌子", "用户反复尝试失败后咒骂",
                "用户被电话吵醒，语气很差", "用户说『这东西怎么又坏了』",
                "用户和家人争执后坐下生闷气", "用户被噪音打扰，捂住耳朵",
                "用户写的文档没保存就崩溃了", "用户网购退货被拒，越说越气"],
    "fear":    ["房间里突然传来巨响", "窗外闪电后立刻停电",
                "用户看恐怖片时缩进椅子", "一只飞虫突然扑向用户",
                "深夜门锁发出异响", "用户说『刚才好像有人在外面』",
                "椅子突然滑动，用户惊呼", "用户接到令人不安的电话",
                "用户独自在家听到楼上有脚步声", "烤箱突然冒出浓烟"],
    "surprise": ["用户突然回头看到台灯在动", "用户拆开意料之外的快递",
                 "用户说『居然中奖了？！』", "朋友突然出现在用户身后",
                 "用户发现植物开花了", "用户看到股票暴涨的消息",
                 "用户收到久未联系老友的信息", "用户意外打翻水杯",
                 "用户发现家里的猫学会了开抽屉", "用户查成绩时捂住眼睛不敢看"],
    "sad":     ["用户看完悲剧电影后沉默", "用户说『今天搞砸了一切』",
                "用户独自坐着发呆很久", "用户得知宠物生病的消息",
                "用户翻着旧照片叹气", "用户说『朋友要搬走了』",
                "用户被批评后趴在桌上", "雨夜用户望着窗外出神",
                "用户的植物枯死了，默默收拾花盆", "用户投的简历又被拒了"],
    "neutral": ["用户安静地在桌前看书", "用户例行整理桌面",
                "用户在房间里边走边打电话", "用户调试台灯的角度",
                "用户边吃午饭边看屏幕", "用户在房间里做伸展运动",
                "用户扫地经过台灯旁边", "用户坐着闭目养神",
                "用户给植物浇水", "用户戴着手套做手工"],
}

# ---------------- B 类：响应式手势（对用户话语的直接反应） ----------------

def _gesture_curious():
    """好奇：侧头（roll）+ 注视（gaze 前倾）——ELEGNT kinesics: tilt+gaze。"""
    return [lib.gaze_shift(0.25, 0.7),
            Primitive("tilt_hold", lib.move_to(lib._off(roll=0.30, p5=-0.10), 0.9, attack=0.8)),
            lib.hold(1.2),
            Primitive("tilt_back", lib.move_to(lib._off(), 0.8, attack=0.6))]


def _gesture_startle():
    """惊吓：猛烈扭头远离（avoid+yaw）+ 高频红闪（LED 在 led 字段）。"""
    return [Primitive("startle_turn", lib.move_to(
                lib._off(yaw=-0.65, p2=0.50, p3=0.35), 0.22, attack=3.0)),
            lib.tremble(0.035, 10.0, 0.9),
            Primitive("recover", lib.move_to(lib._off(yaw=-0.15), 1.0, attack=0.5))]


GESTURES = {
    "nod": {
        "label": "点头（肯定/同意）",
        "primitives": lambda: [lib.nod(0.28, 1.5, 2)],
        "led": {"rgbw": [120, 255, 120, 60], "pattern": "pulse",
                "freq_hz": 1.5, "intensity": [40, 90]},
        "line": "嗯，我明白你的意思。",
        "utterances": ["『你觉得我这个想法怎么样？』", "『这样做好不好？』",
                       "『今天能帮我个忙吗？』", "『我是不是说得有道理？』",
                       "『我们就这样定了吧？』", "『你听懂了吗？』",
                       "『这段代码写得还行吧？』", "『今晚早点睡，好不好？』"],
    },
    "shake": {
        "label": "摇头（否定/不赞同）",
        "primitives": lambda: [lib.shake(0.38, 1.6, 2)],
        "led": {"rgbw": [255, 160, 40, 0], "pattern": "double_pulse",
                "freq_hz": 1.2, "intensity": [40, 80]},
        "line": "嗯……我觉得不太行。",
        "utterances": ["『要不要再来一杯奶茶？』（深夜）", "『我这代码不用测试了吧？』",
                       "『明天再锻炼也行吧？』", "『熬夜没关系吧？』",
                       "『这个bug肯定不是我的问题吧？』", "『可以直接上生产环境吧？』",
                       "『周末就不用学习了吧？』", "『再吃一块蛋糕没关系吧？』"],
    },
    "curious": {
        "label": "Curious (head-tilt gaze at user)",
        "primitives": _gesture_curious,
        "led": {"rgbw": [120, 180, 255, 60], "pattern": "double_pulse",
                "freq_hz": 0.8, "intensity": [35, 85]},
        "line": "Hmm? What's that? Let me see.",
        "utterances": ["用户在桌上放了一个新物件", "用户轻声自言自语",
                       "用户拿出一本没见过的书", "用户做出奇怪的手势",
                       "用户说『你猜我今天遇到谁了？』", "房间里传来陌生的声音",
                       "用户换了一个新发型", "用户对着台灯欲言又止"],
    },
    "startle": {
        "label": "惊吓（猛烈扭头远离 + 高频红闪）",
        "primitives": _gesture_startle,
        "led": {"rgbw": [255, 0, 0, 0], "pattern": "strobe",
                "freq_hz": 10.0, "intensity": [100, 100]},
        "line": "哇！吓我一跳！",
        "utterances": ["用户突然拍了一下桌子", "用户从背后突然喊台灯的名字",
                       "用户猛地拉开窗帘", "用户不小心碰倒了水杯",
                       "气球在用户手边突然爆掉", "用户突然把脸凑到台灯前",
                       "用户的手机突然大声响起闹钟", "窗外突然炸响一声雷"],
    },
}


# ---------------- 规则初标：valence/arousal（circumplex，待人工抽检） ----------------

VA_TABLE = {
    "joy": (0.8, 0.6), "love": (0.7, -0.2), "angry": (-0.7, 0.8),
    "fear": (-0.8, 0.9), "surprise": (0.2, 0.8), "sad": (-0.7, -0.6),
    "neutral": (0.0, 0.0),
    "nod": (0.5, 0.3), "shake": (-0.3, 0.3),
    "curious": (0.3, 0.5), "startle": (-0.6, 0.95),
}


def va_annotation(key, rng):
    v0, a0 = VA_TABLE[key]
    return {"valence": round(float(np.clip(v0 + rng.uniform(-0.05, 0.05), -1, 1)), 3),
            "arousal": round(float(np.clip(a0 + rng.uniform(-0.05, 0.05), -1, 1)), 3),
            "method": "rule_based_v1", "reviewed": False}


def jitter_primitives(prims, rng):
    """幅度 ±15%、时标 ±10% 的参数抖动（作用于关键帧）。"""
    amp_s = 1.0 + rng.uniform(-AMP_JITTER, AMP_JITTER)
    time_s = 1.0 + rng.uniform(-TIME_JITTER, TIME_JITTER)
    out = []
    for p in prims:
        kfs = [(t * time_s, np.asarray(q, float) * amp_s) for (t, q) in p.keyframes]
        out.append(Primitive(p.name, kfs, meta=p.meta))
    return out


def make_episode(eid, category, scene_text, human_emotion, program_name,
                 prims, led, line, gamma, seed):
    rng = np.random.default_rng(seed)
    prims_j = jitter_primitives(prims, rng)
    traj = render(prims_j)
    t, q = traj["t"], traj["q"]
    step = max(1, CONTROL_HZ // STORE_HZ)
    va_key = program_name if program_name in VA_TABLE else human_emotion
    return {
        "episode_id": eid,
        "category": category,
        "scene_text": scene_text,
        "human_emotion": human_emotion,
        "annotation": va_annotation(va_key, rng),
        "response": {
            "program": program_name,
            "primitives": [p.name for p in prims_j],
            "trajectory": {
                "hz": STORE_HZ,
                "duration_s": round(float(t[-1]), 3),
                "base_pose": [round(float(v), 5) for v in ZERO],
                "q": [[round(float(v), 4) for v in row] for row in q[::step]],
            },
            "led": led,
            "caption": line,
            "gamma": gamma,
        },
        "quality": traj["info"],
        "provenance": {"source": "synthetic:parametric_library_v1+jitter",
                       "seed": seed, "license": "project-internal"},
    }


def main():
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    episodes, seed = [], 1000

    # A 类：共情程序
    for emo, spec in lib.EMOTIONS.items():
        for scene in SCENARIOS[emo]:
            seed += 1
            episodes.append(make_episode(
                f"emp_{emo}_{seed}", "empathy", scene, emo, emo,
                spec["primitives"](), spec["led"], spec["caption"],
                spec["gamma"], seed))

    # B 类：响应式手势
    for gname, g in GESTURES.items():
        for utt in g["utterances"]:
            seed += 1
            episodes.append(make_episode(
                f"react_{gname}_{seed}", "reactive_gesture", utt,
                f"user_query:{gname}", gname,
                g["primitives"](), g["led"], g["line"], None, seed))

    bad = [e["episode_id"] for e in episodes
           if not e["quality"]["limits_ok"]]
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        for e in episodes:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    durs = [e["response"]["trajectory"]["duration_s"] for e in episodes]
    mb = os.path.getsize(OUT_PATH) / 1e6
    print(f"episodes: {len(episodes)}  (empathy {sum(1 for e in episodes if e['category']=='empathy')}, "
          f"reactive {sum(1 for e in episodes if e['category']=='reactive_gesture')})")
    print(f"duration: mean {np.mean(durs):.2f}s  max {max(durs):.2f}s")
    print(f"limits_ok: {len(episodes) - len(bad)}/{len(episodes)}"
          + (f"  越限: {bad}" if bad else ""))
    print(f"written: {OUT_PATH} ({mb:.2f} MB)")


if __name__ == "__main__":
    main()
