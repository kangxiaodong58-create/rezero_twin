# -*- coding: utf-8 -*-
"""H-1 修复真机验证：后期来信回应语感对齐。"""
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

tmp = tempfile.mkdtemp(prefix="h1_fix_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import StoryArc
    from shared.letter_manager import LetterManager

    now = time.time()
    # 触发后期来信（离线 5 天）
    ws = WorldState.now()
    ws.last_interaction_ts = now - 5 * 86400
    ws.last_period = "上午"
    ws.period = "午后"
    ws.weather = "晴朗"
    mgr = LetterManager()
    letter = mgr.evaluate_and_dispatch(ws, favor=60, current_weather="晴朗",
                                       now_ts=now, today_str="2026-08-19",
                                       arc="late_arc")
    print(f"[触发] {'是' if letter else '否'}")
    conv = ConversationStore()
    for m in letter.get("messages", []):
        conv.append(m["sender"], "蕾 姆" if m["sender"] == "rem" else "拉 姆", m["content"])
        print(f"[来信] {m['sender']}: {m['content'][:45]}")

    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = ws
    bot.engine.favor = 60
    bot.set_arc(StoryArc.LATE_ARC)

    reply = bot.chat("我回来了。让你们久等了。")
    print(f"\n[回应]\n{reply}")
    # 判据：后期语感（并肩/营地/战场/托付），非宅邸（红茶/花园/庭院白花）
    late_marks = ["并肩", "营地", "战场", "托付", "战友", "战线"]
    mansion_marks = ["红茶", "花园", "庭院", "白花", "厨房", "茶点", "宅邸"]
    late_hit = sum(1 for m in late_marks if m in reply)
    mansion_hit = sum(1 for m in mansion_marks if m in reply)
    print(f"\n后期语感命中 {late_hit} 项 | 宅邸语感命中 {mansion_hit} 项")
    print(f"结论: {'✅ 后期语感对齐' if late_hit >= mansion_hit else '❌ 仍偏宅邸'}")
