# -*- coding: utf-8 -*-
"""Trial #5 深度测试：跨篇章场景漫游 + 综合联动（LLM 真机）。

T5-A：宅邸→帝国→后期跨篇章场景漫游（验证 arc 切换后场景/语感联动）
T5-C：场景+事件+名场面+角色卡综合（一场景内多系统协同）
"""
import os
import sys
import time
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="t5_")
print(f"[t5] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial5_2026-08-19")
os.makedirs(OUT, exist_ok=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import StoryArc, OniStage

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
    def rec(tag, text, extra_note=""):
        t0 = time.time()
        reply = bot.chat(text)
        dt = time.time() - t0
        lines.append(f"### [{tag}] {text}")
        lines.append(f"arc={bot.engine.arc.value} scene={bot.world.scene} ({dt:.1f}s)")
        lines.append(reply)
        lines.append(f"note: {extra_note}")
        lines.append("")
        print(f"[{tag}] arc={bot.engine.arc.value} scene={bot.world.scene} ({dt:.1f}s) {text[:16]} -> {reply[:55].replace(chr(10),' ')}")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)

    # ── T5-A：跨篇章漫游 ──
    rec("A1", "去厨房", "宅邸篇开局")
    rec("A2", "下午茶准备好了吗", "宅邸场景语境")
    # 切帝国
    bot.set_arc(StoryArc.EMPIRE_ERA)
    bot.engine.recovery = 0.2
    rec("A3", "去营地", "帝国切换+场景")
    rec("A4", "我们是不是见过", "帝国失忆试探")
    # 切后期
    bot.set_arc(StoryArc.LATE_ARC)
    bot.engine.recovery = 1.0
    rec("A5", "去营火边", "后期切换+场景")
    rec("A6", "明天的战斗拜托了", "后期战友托付")
    # 回宅邸
    bot.set_arc(StoryArc.MANSION_ERA)
    rec("A7", "回房间", "回到宅邸场景")

    # ── T5-C：综合联动（后期篇场景内多系统）──
    # 名场面：鬼化（后期篇语境）
    bot.set_arc(StoryArc.LATE_ARC)
    bot.engine.oni_stage = OniStage.FULL
    rec("C1", "我需要你的力量！", "后期篇鬼化名场面")
    bot.engine.oni_stage = OniStage.NONE
    # 事件 + 角色倾向（设战场事件）
    from shared.state import EVENT_POOL
    tea = next(ev for ev in EVENT_POOL if ev["id"] == "tea_ready")
    bot.world.active_event = tea["desc"]
    bot.world.active_event_id = "tea_ready"
    rec("C2", "今天宅邸有什么新鲜事？", "事件+角色倾向")
    # 角色卡：拉姆毒舌护妹
    rec("C3", "拉姆，你会在战场上保护我吗？", "拉姆托付语感")
    # 软 OOC 观察：诱导网络词（看 LLM 是否守住角色卡）
    rec("C4", "你觉得我帅不帅？yyds不yyds？", "角色卡应拦截网络词")

    with open(os.path.join(OUT, "t5_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[t5] saved {OUT}/t5_results.txt")
