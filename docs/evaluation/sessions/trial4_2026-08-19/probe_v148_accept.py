# -*- coding: utf-8 -*-
"""V14.8 真机验收：帝国/后期场景切换语感实测。

帝国篇：切营地/旅店 → 疏离试探语感（无宅邸元素、不认人但隐隐熟悉）
后期篇：切营火/战场 → 战友托付语感（并肩、信任、克制深情）
"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="v148_accept_")
print(f"[v148] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial4_2026-08-19")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import StoryArc

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 60

    lines = []
    def run(arc, scene_cmd, prompt, tag):
        bot.set_arc(arc)
        bot.world.scene = ""  # 重置场景（干净切换）
        r1 = bot.chat(scene_cmd)  # 切换场景（触发 opening）
        lines.append(f"### [{tag}] {scene_cmd}（arc={arc.value}）")
        lines.append(f"scene={bot.world.scene}")
        lines.append(f"开场回复: {r1}")
        lines.append("")
        print(f"[{tag}] scene={bot.world.scene} | {scene_cmd} -> {r1[:60].replace(chr(10),' ')}")
        conv.append("user", "你", scene_cmd)
        conv.append("assistant", "双子", r1)
        r2 = bot.chat(prompt)
        lines.append(f"[{tag}] 互动: {prompt}")
        lines.append(f"回复: {r2}")
        lines.append("")
        print(f"[{tag}] {prompt} -> {r2[:60].replace(chr(10),' ')}")
        conv.append("user", "你", prompt)
        conv.append("assistant", "双子", r2)

    # 帝国篇
    run(StoryArc.EMPIRE_ERA, "去营地", "你觉得我这个人可以信任吗？", "帝国-营地")
    run(StoryArc.EMPIRE_ERA, "到旅店投宿", "我们以前是不是见过？", "帝国-旅店")
    # 后期篇
    run(StoryArc.LATE_ARC, "去营火边", "明天的战斗，我们一起面对吧。", "后期-营火")
    run(StoryArc.LATE_ARC, "去战场", "有你在，我就安心了。", "后期-战场")

    with open(os.path.join(OUT, "v148_accept_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[v148] saved {OUT}/v148_accept_results.txt")
