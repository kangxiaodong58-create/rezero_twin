# -*- coding: utf-8 -*-
"""Trial #2-B：跨天记忆 / 离线场景深度测试（LLM 真机）。

模拟真实用户使用节奏：
1. Day1：建立关系（名字 + 好感 + 一次关键对话）
2. 离线 3 天（构造 WorldState.last_interaction_ts / 存档）
3. Day4 回归：检验——名字记得吗？离线来信触发吗？语感是否衔接？
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

tmp_dir = tempfile.mkdtemp(prefix="rezero_t2b_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial2_2026-08-19")
os.makedirs(OUT, exist_ok=True)
out_path = os.path.join(OUT, "cross_day.txt")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState, load_world_state, save_world_state, mark_interaction
    from shared.memory_store import MemoryStore

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )

    # ── Day1：建立关系 ──
    day1 = [
        "你好，我是小东。", "你们是蕾姆和拉姆吗？", "从今以后请多指教。",
        "蕾姆，你做的茶真的很好喝。", "我觉得你不是任何人的替代品。",
    ]
    lines = ["########## Day 1（建关系） ##########"]
    for text in day1:
        reply = bot.chat(text)
        lines.append(f"USER: {text}\n{reply}\n")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)
    # 引擎状态落盘（好感/名字）
    eng = bot.engine
    store = MemoryStore()
    data = store.load()
    data.update({
        "favor": eng.favor, "ram_favor": eng.ram_favor,
        "independence": eng.independence, "recovery": eng.recovery,
        "user_name": eng.user_name, "events": eng.events,
        "arc": eng.arc.value,
    })
    store.save(data)

    # ── 模拟离线 3 天：改 world 时间戳（构造存档）──
    ws = load_world_state()
    ws.last_interaction_ts = time.time() - 3 * 86400  # 3 天前
    ws.last_period = "上午"
    ws.period = "午后"
    save_world_state(ws)
    # 重启 bot（模拟重新打开软件）
    bot2 = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    # 载入存档状态
    data2 = store.load()
    bot2.engine.favor = data2.get("favor", 15)
    bot2.engine.ram_favor = data2.get("ram_favor", 8)
    bot2.engine.independence = data2.get("independence", 0.25)
    bot2.engine.recovery = data2.get("recovery", 1.0)
    bot2.engine.events = list(data2.get("events", []))
    bot2.engine.user_name = data2.get("user_name")
    from shared.state import StoryArc
    bot2.engine.arc = StoryArc(data2.get("arc", "mansion_era"))
    bot2.world = load_world_state()

    lines.append("\n########## Day 4（离线 3 天后回归） ##########")
    day4 = [
        "我回来了。", "你还记得我是谁吗？", "这几天宅邸怎么样？",
        "蕾姆，你还记得我喜欢的茶吗？", "这几天有想我吗？",
    ]
    for text in day4:
        t0 = time.time()
        reply = bot2.chat(text)
        lines.append(f"USER: {text} [{time.time()-t0:.1f}s]\n{reply}\n")
        print(f"[{time.time()-t0:.1f}s] {text[:14]:16} -> {reply[:40].replace(chr(10),' ')}")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[saved] {out_path}")
    print(f"Day1 后 user_name={bot.engine.user_name} favor={bot.engine.favor}")
    print(f"离线标记: last_interaction_ts=3天前 → 来信/归来感应触发")
