# -*- coding: utf-8 -*-
"""验收补测 B 组：事件系统专项（B1 天气×事件 / B2 时段×事件 / B3 角色倾向）。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="accept_b_")
print(f"[accept-B] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "accept_v1457_2026-08-19")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.state import WorldState, EVENT_POOL
    from shared import state as _state_mod

    # ── B1：雨天事件采样（纯逻辑，零 API）──
    rain_ids = set()
    for seed in range(300):
        ev = WorldState._pick_active_event("2026-08-19", "午后", "大雨", seed)
        rain_ids.add(ev["id"])
    conflict = rain_ids & {"cat_visitor", "laundry_day", "sunny_noon"}
    rain_specific = [ev for ev in EVENT_POOL if "雨" in ev["desc"]]
    print(f"[B1] 大雨 300 采样事件集合: {len(rain_ids)} 种")
    print(f"[B1] 冲突事件命中: {conflict if conflict else '零 ✅'}")
    print(f"[B1] 雨天专属事件可达: {[e['id'] for e in rain_specific if e['id'] in rain_ids]}")
    assert not conflict, f"大雨选中晴天事件: {conflict}"

    # ── B2：晴天上午事件（纯逻辑）──
    morning_ids = set()
    for seed in range(300):
        ev = WorldState._pick_active_event("2026-08-19", "上午", "晴朗", seed)
        morning_ids.add(ev["id"])
    print(f"[B2] 晴天上午 300 采样: {len(morning_ids)} 种")
    assert not (morning_ids & {"night_candle_01", "night_star_01"}), "上午选中夜晚事件"

    # ── B3：真机——设置 active_event 后问看法 ──
    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.world.active_event = "一只野猫从庭院围墙跳了进来，正晒着太阳"
    bot.world.active_event_id = "cat_visitor"
    bot.engine.favor = 40

    reply = bot.chat("蕾姆，你对今天那只野猫怎么看？")
    print(f"\n[B3] 回复:\n{reply}")
    with open(os.path.join(OUT, "b3_cat_reply.txt"), "w", encoding="utf-8") as f:
        f.write(f"事件: {bot.world.active_event}\n回复:\n{reply}")
    print("\n[accept-B] done")
