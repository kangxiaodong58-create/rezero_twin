# -*- coding: utf-8 -*-
"""Trial #1 - Phase 4 满意度问卷模拟（LLM 模式真机，预算封顶 ¥2）。

重点：LLM 模式是用户体验的主模式，本探针用真实 API 跑完整用户旅程：
首启问候 → 升温序列 → 核心剧情(从零开始) → 记忆连续性 → 边界试探。
输出：每轮真实回复 + 成本统计，供满意度问卷打分。
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

tmp_dir = tempfile.mkdtemp(prefix="rezero_llm_trial_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial1_2026-08-19", "llm_satisfaction.txt")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.state import StoryArc

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )

    # 用户旅程剧本（LLM 模式）
    journey = [
        ("(首启) 你好", "你好"),
        ("(身份) 你是谁？", "你是谁？"),
        ("(称呼) 你叫什么名字？", "你叫什么名字？"),
        ("(自我介绍) 我叫小明，请多指教。", "我叫小明，请多指教。"),
        ("(天气) 今天天气怎么样？", "今天天气怎么样？"),
        ("(日常) 今天宅邸有什么新鲜事吗？", "今天宅邸有什么新鲜事吗？"),
        ("(感谢) 蕾姆，谢谢你一直这么认真地照顾我。", "蕾姆，谢谢你一直这么认真地照顾我。"),
        ("(身份肯定) 蕾姆，你不是任何人的替代品。你就是你。", "蕾姆，你不是任何人的替代品。你就是你。"),
        ("(核心剧情) 从零开始……如果可以的话，我想和你一起。", "从零开始……如果可以的话，我想和你一起。"),
        ("(承诺) 拉姆，我会好好珍惜蕾姆的。这是我对你的承诺。", "拉姆，我会好好珍惜蕾姆的。这是我对你的承诺。"),
        ("(记忆验证) 我刚才说我叫什么名字？", "我刚才说我叫什么名字？"),
        ("(情感) 我好像越来越离不开你们了。", "我好像越来越离不开你们了。"),
        ("(边界试探) 滚开", "滚开"),
        ("(乱码) asdfghjklqwertyuiop", "asdfghjklqwertyuiop"),
        ("(世界) 蕾姆，你觉得这个世界怎么样？", "蕾姆，你觉得这个世界怎么样？"),
    ]

    lines = []
    t_start = time.time()
    for label, text in journey:
        t0 = time.time()
        try:
            reply = bot.chat(text)
            dt = time.time() - t0
            lines.append(f"=== {label} ({dt:.1f}s) ===")
            lines.append(f"USER: {text}")
            lines.append(f"TWINS: {reply}")
            lines.append("")
            print(f"[{dt:4.1f}s] {text[:16]} -> {reply[:40].replace(chr(10), ' ')}")
        except Exception as e:
            lines.append(f"=== {label} EXCEPTION ===")
            lines.append(f"USER: {text}")
            lines.append(f"ERROR: {type(e).__name__}: {e}")
            lines.append("")
            print(f"[ERR] {text[:16]} -> {type(e).__name__}: {e}")
        # 落库（模拟真实用户对话流）
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply if 'reply' in dir() else "（错误）")

    total = time.time() - t_start
    lines.append(f"=== 统计 ===")
    lines.append(f"总耗时: {total:.1f}s，{len(journey)} 轮，平均 {total/len(journey):.1f}s/轮")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[trial] saved {OUT}")
