# -*- coding: utf-8 -*-
"""V14.8 ② 真机验证：后期篇离线触发来信（GUI 启动链路模拟）。"""
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

tmp = tempfile.mkdtemp(prefix="late_letter_real_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from shared.world_state import WorldState
    from shared.state import StoryArc
    from shared.letter_manager import LetterManager

    # 构造后期篇 + 离线 3 天的世界状态
    ws = WorldState.now()
    ws.last_interaction_ts = time.time() - 3 * 86400  # 3 天前
    ws.last_period = "上午"
    ws.period = "午后"
    ws.weather = "晴朗"

    mgr = LetterManager()
    # 模拟 GUI 启动链路：arc 透传（late_arc）
    letter = mgr.evaluate_and_dispatch(ws, favor=60, current_weather="晴朗", now_ts=time.time(), today_str="2026-08-19", arc="late_arc")
    print(f"触发: {'是' if letter else '否'}")
    if letter:
        for m in letter.get("messages", []):
            print(f"  [{m['sender']}] {m['content'][:60]}")
        print(f"suppress_vignette: {letter.get('suppress_vignette')}")
    else:
        print("（未触发——可能冷却或条件不满足）")

    # 冷却验证：立即再触发应被拦
    letter2 = mgr.evaluate_and_dispatch(ws, favor=60, current_weather="晴朗", now_ts=time.time(), today_str="2026-08-19", arc="late_arc")
    print(f"冷却后再次触发: {'是（异常）' if letter2 else '否（冷却生效 ✅）'}")
