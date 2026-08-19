# -*- coding: utf-8 -*-
"""Trial #5-B：后期来信真机——离线触发来信 + LLM 回应来信内容。

验证：后期篇离线触发后期来信 → 来信进入对话上下文 → 用户回应 → 双子接住
（来信落库为正常消息，LLM 上下文恢复可引用）
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

tmp = tempfile.mkdtemp(prefix="t5b_")
print(f"[t5b] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial5_2026-08-19")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState
    from shared.state import StoryArc
    from shared.letter_manager import LetterManager

    now = time.time()
    # ── 1. 触发后期来信（离线 5 天）──
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
    if not letter:
        print("未触发，结束")
        sys.exit(0)
    msgs = letter.get("messages", [])

    # ── 2. 来信写入 conversation store（模拟 GUI 落库）──
    conv = ConversationStore()
    letter_texts = []
    for m in msgs:
        conv.append(m["sender"], "蕾 姆" if m["sender"] == "rem" else "拉 姆", m["content"])
        letter_texts.append(m["content"])
        print(f"[来信] {m['sender']}: {m['content'][:50]}")

    # ── 3. 用户回应 → LLM 应接住来信内容 ──
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = ws
    bot.engine.favor = 60
    bot.set_arc(StoryArc.LATE_ARC)

    reply = bot.chat("我回来了。看到你们的信了，让你们担心了。")
    print(f"\n[用户回应] -> LLM 回复:\n{reply}")
    with open(os.path.join(OUT, "t5b_results.txt"), "w", encoding="utf-8") as f:
        f.write(f"来信:\n" + "\n".join(letter_texts) + f"\n\n用户回应后:\n{reply}")
    print(f"\n[t5b] saved {OUT}/t5b_results.txt")
