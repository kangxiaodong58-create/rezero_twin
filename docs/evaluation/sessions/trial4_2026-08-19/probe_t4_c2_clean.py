# -*- coding: utf-8 -*-
"""Trial #4-C2 复测：纯净环境下鬼化名场面真机验证。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="t4_c2_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.state import OniStage
    from shared.world_state import WorldState

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 70
    bot.engine.oni_stage = OniStage.FULL  # 纯净状态（无历史干扰）

    reply = bot.chat("我需要你的力量！")
    print("=== 鬼化名场面（纯净环境）===")
    print(reply)
    conv.append("user", "你", "我需要你的力量！")
    conv.append("assistant", "双子", reply)
