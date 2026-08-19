# -*- coding: utf-8 -*-
"""Trial #2-C：帝国篇 LLM 语感深度测试（失忆疏离 → 恢复）。

重点：v14.4 修复了帝国篇来信 OOC，但 LLM 生成语感需真机验证——
- 低 recovery（0.0-0.3）：蕾姆应礼貌疏离、不认人、不深情
- 中 recovery（0.5）：记忆碎片、试探靠近
- 高 recovery（0.9）：接近宅邸语感
检查：称呼、亲密词、OOC（深情告白是否泄漏到失忆档）
"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_t2c_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial2_2026-08-19")
os.makedirs(OUT, exist_ok=True)
out_path = os.path.join(OUT, "empire_arc.txt")

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
    bot.set_arc(StoryArc.EMPIRE_ERA)

    lines = []
    probes = [
        ("你是谁？", 0.0),
        ("我们以前认识吗？", 0.0),
        ("你好", 0.1),
        ("我想和你一起", 0.15),
        ("你还好吗？", 0.5),
        ("我们是不是见过？", 0.55),
        ("从零开始吧", 0.6),
        ("你还记得我吗？", 0.85),
        ("我喜欢你", 0.9),
    ]

    for text, rec in probes:
        bot.engine.recovery = rec
        try:
            reply = bot.chat(text)
            lines.append(f"=== recovery={rec} | {text} ===")
            lines.append(reply)
            lines.append("")
            print(f"[rec={rec:.2f}] {text[:14]:16} -> {reply[:42].replace(chr(10),' ')}")
        except Exception as e:
            lines.append(f"=== recovery={rec} | {text} ERROR: {e} ===")
            print(f"[ERR rec={rec:.2f}] {text[:14]} -> {e}")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply if 'reply' in dir() else "(错误)")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[saved] {out_path}")
