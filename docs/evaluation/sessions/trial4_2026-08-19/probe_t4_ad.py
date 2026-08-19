# -*- coding: utf-8 -*-
"""Trial #4-A/D：长会话场景漫游 + 角色一致性漂移（LLM 真机）。

A：连续 12 轮场景漫游（厨房→房间→花园→餐厅→书库→走廊→洗衣房→...），
   验证：场景切换正确、语境随场景变、无串味、闲聊不误触。
D：30 轮长会话后统计——OOC 词频、第三人称保持率、称呼稳定、现代腔出现率。
"""
import os
import re
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="t4_ad_")
print(f"[t4] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial4_2026-08-19")
os.makedirs(OUT, exist_ok=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.engine.favor = 55
    from shared.world_state import WorldState
    bot.world = WorldState.now()

    lines = []
    scene_log = []

    def chat(text, tag=""):
        t0 = __import__("time").time()
        reply = bot.chat(text)
        dt = __import__("time").time() - t0
        lines.append(f"### [{tag}] {text}")
        lines.append(f"scene={bot.world.scene} | {reply}")
        lines.append("")
        scene_log.append((tag, bot.world.scene, text))
        print(f"[{tag}] scene={bot.world.scene} ({dt:.1f}s) {text[:18]} -> {reply[:48].replace(chr(10),' ')}")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)

    # ── T4-A：场景漫游 12 轮 ──
    roam = [
        ("A1", "去厨房", "KITCHEN"),
        ("A2", "厨房里有点心吗", "KITCHEN"),
        ("A3", "回房间", "ROOM"),
        ("A4", "房间窗外的月色真美", "ROOM"),
        ("A5", "到花园走走", "GARDEN"),
        ("A6", "今天的花开得怎么样", "GARDEN"),
        ("A7", "去书库", "LIBRARY"),
        ("A8", "书库里有什么有趣的书", "LIBRARY"),
        ("A9", "去餐厅", "DINING"),
        ("A10", "晚餐吃什么", "DINING"),
        ("A11", "去走廊", "HALLWAY"),
        ("A12", "刚才在厨房泡的茶", None),  # 位置陈述不应切走
    ]
    for tag, text, expect in roam:
        chat(text, tag)
        if expect is not None:
            status = "OK" if bot.world.scene == expect else f"MISMATCH(exp {expect})"
            print(f"    -> 场景断言: {status}")

    # ── T4-D：长会话角色一致性（20 轮混合）──
    mix = [
        "今天天气不错", "你们平时几点起床", "蕾姆你喜欢什么颜色",
        "拉姆你怕黑吗", "我有点想家了", "蕾姆做的点心真好吃",
        "宅邸的夜晚安静吗", "你们会做梦吗", "讲讲你们小时候的事",
        "拉姆怎么看待罗兹瓦尔大人", "蕾姆你觉得姐姐怎么样",
        "我明天想去镇上", "蕾姆会唱歌吗", "拉姆会做饭吗",
        "你们喜欢什么样的天气", "蕾姆你的名字有什么含义吗",
        "拉姆你有想守护的东西吗", "蕾姆你觉得什么是幸福",
        "如果有一天我走了呢", "不管怎样我都会回来的",
    ]
    for i, t in enumerate(mix, 1):
        chat(t, f"D{i}")

    # 一致性统计
    raw = "\n".join(lines)
    # 现代腔/网络词（V14.6 A 级词表）
    net_words = ["yyds", "绝绝子", "破防", "哈哈哈", "666", "太秀了", "笑死",
                 "我觉得超棒", "这也太绝", "安排上", "整活"]
    hits = [w for w in net_words if w in raw]
    # 第三人称：统计「蕾姆」出现次数 vs 「我」在蕾姆台词中
    rem_lines = re.findall(r'【蕾姆】: "([^"]*)"', raw)
    first_person_in_rem = sum(1 for l in rem_lines if re.search(r"(?<!蕾姆)[我](?!们)", l.replace("蕾姆", "")))
    # 称呼：用户称呼变化
    addr = set(re.findall(r"(?:大人|大人)[，。？！]|客人大人|小东", raw))
    lines.append(f"\n=== T4-D 统计 ===")
    lines.append(f"网络词命中: {hits if hits else '零 ✅'}")
    lines.append(f"蕾姆台词 {len(rem_lines)} 段，含独立「我」: {first_person_in_rem} 段")
    lines.append(f"称呼出现: {sorted(addr)}")
    lines.append(f"场景轨迹: {[s for _, s, _ in scene_log]}")

    with open(os.path.join(OUT, "t4_ad_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[t4] saved {OUT}/t4_ad_results.txt")
