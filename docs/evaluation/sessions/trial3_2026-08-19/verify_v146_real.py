# -*- coding: utf-8 -*-
"""V14.6 真机验证：角色卡注入后的原著锚定效果（1-2 轮）。"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="v146_real_")
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
    # 好感 CLOSE：触发中好感情感表达档
    bot.engine.favor = 60

    probes = [
        "蕾姆，你觉得你是个什么样的人？",   # 应触发角色卡（自我认知/替代品弧线）
        "拉姆，你会怎么评价我？",           # 应触发拉姆毒舌+托付语义
    ]
    for text in probes:
        reply = bot.chat(text)
        print(f"=== {text} ===")
        print(reply)
        print()
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)
