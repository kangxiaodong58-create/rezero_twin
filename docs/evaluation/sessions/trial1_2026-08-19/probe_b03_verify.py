# -*- coding: utf-8 -*-
"""B-03 修复验证：括号体密度对照（LLM 真机 5 轮）。"""
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

tmp_dir = tempfile.mkdtemp(prefix="rezero_b03_")
print(f"[trial] isolated data dir: {tmp_dir}")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )

    script = [
        "今天天气怎么样？",
        "蕾姆，谢谢你一直这么认真地照顾我。",
        "蕾姆，你不是任何人的替代品。你就是你。",
        "从零开始……如果可以的话，我想和你一起。",
        "我好像越来越离不开你们了。",
    ]

    total_paren = 0
    total_lines = 0
    for text in script:
        reply = bot.chat(text)
        # 统计括号描写数（【角色】: "（...）" 或行内括号）
        parens = len(re.findall(r"（[^）]{2,}）", reply))
        lines = [l for l in reply.split("\n") if l.strip()]
        total_paren += parens
        total_lines += len(lines)
        print(f"--- {text[:16]} ---")
        print(reply)
        print(f"[括号 {parens} 处 / {len(lines)} 行]")
        print()
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)

    density = total_paren / max(1, total_lines)
    print(f"=== 汇总：括号 {total_paren} 处 / {total_lines} 行 = {density:.2f} 处/行（修复目标 <0.3）===")
