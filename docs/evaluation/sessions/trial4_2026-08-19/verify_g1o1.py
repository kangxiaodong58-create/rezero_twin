# -*- coding: utf-8 -*-
"""G-1+O-1 真机验证：事件高亮注入 + 场景联动刷新。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="g1o1_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import EVENT_POOL

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 55
    # 设置走廊事件，然后切书库 → O-1 应刷新事件
    tea = next(ev for ev in EVENT_POOL if ev["id"] == "tea_ready")
    bot.world.active_event = tea["desc"]
    bot.world.active_event_id = "tea_ready"
    print(f"[O-1] 切场景前事件: {bot.world.active_event[:30]}")

    r = bot.chat("去书库")
    print(f"[O-1] 切场景后事件: {bot.world.active_event[:30]}")
    print(f"[O-1] 场景: {bot.world.scene}")
    print(f"[G-1] 回复:\n{r[:200]}")
    conv.append("user", "你", "去书库")
    conv.append("assistant", "双子", r)

    # 再问事件（验证高亮注入后 LLM 呼应事件）
    r2 = bot.chat("今天宅邸有什么新鲜事？")
    print(f"\n[G-1] 事件询问回复:\n{r2[:250]}")
    conv.append("user", "你", "今天宅邸有什么新鲜事？")
    conv.append("assistant", "双子", r2)
