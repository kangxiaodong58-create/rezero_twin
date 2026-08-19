# -*- coding: utf-8 -*-
"""SCENE_GUIDES 扩充真机验证（LLM 模式，2-3 轮）。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="scene_real_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState, load_world_state
    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = load_world_state()
    bot.engine.favor = 85  # DEAR，guardian_vow 门槛可过

    for text in ["如果有一天我离开了呢？", "我会保护你们的，不会让你们受伤。"]:
        scene, _ = bot._detect_scene(text, bot.engine.snapshot(), bot.world)
        print(f"=== 检测场景: {scene} ===")
        print(f"输入: {text}")
        reply = bot.chat(text)
        print(f"回复: {reply[:200]}")
        print()
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)
