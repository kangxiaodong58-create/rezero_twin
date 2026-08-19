# -*- coding: utf-8 -*-
"""O-1 深度验证：bridge 真实调用链下事件是否刷新。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="o1_deep_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import EVENT_POOL
    from shared import vignette as _v
    from shared.prompts import PromptBuilder

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 55
    tea = next(ev for ev in EVENT_POOL if ev["id"] == "tea_ready")
    bot.world.active_event = tea["desc"]
    bot.world.active_event_id = "tea_ready"

    # 手动调 _build_messages（不真正调 API），观察事件是否被刷新
    msgs, _ = bot._build_messages("去书库")
    print("调用后 world.scene:", bot.world.scene)
    print("调用后 active_event:", bot.world.active_event[:35])
    print("调用后 active_event_id:", bot.world.active_event_id)

    # 检查条件逐项
    loc = _v._derive_location(bot.world.active_event)
    scene_cn = PromptBuilder.SCENE_CN.get(bot.world.scene, bot.world.scene)
    print("地点:", loc, "| 场景中文:", scene_cn)
    print("冲突判定:", loc != "罗兹瓦尔宅邸" and scene_cn and scene_cn not in loc)
