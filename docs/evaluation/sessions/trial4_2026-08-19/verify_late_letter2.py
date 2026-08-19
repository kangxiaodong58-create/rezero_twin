# -*- coding: utf-8 -*-
"""V14.8 ② 真机验证 v2：后期来信触发 + 冷却（独立状态）。"""
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

tmp = tempfile.mkdtemp(prefix="late_letter_real2_")
with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from shared.world_state import WorldState
    from shared.letter_manager import LetterManager

    now = time.time()
    mgr = LetterManager()

    # ── 场景 1：后期篇 + 离线 3 天 → 应触发（多次采样看可达桶）──
    triggered = 0
    shown = set()
    for seed in range(20):
        ws = WorldState.now()
        ws.last_interaction_ts = now - 3 * 86400
        ws.last_period = "上午"
        ws.period = "午后"
        ws.weather = "晴朗"
        # 用随机化触发（多采样）
        import random as _r
        _r.seed(seed)
        letter = mgr.evaluate_and_dispatch(ws, favor=60, current_weather="晴朗",
                                           now_ts=now + seed * 0.001,
                                           today_str="2026-08-19", arc="late_arc")
        if letter:
            triggered += 1
            for m in letter.get("messages", []):
                shown.add(m["content"][:25])
    print(f"[触发] 20 采样触发 {triggered} 次")
    print(f"[样本] {len(shown)} 种来信: {sorted(shown)[:5]}")

    # ── 场景 2：冷却验证（刚触发过 → 再触发被拦）──
    ws = WorldState.now()
    ws.last_interaction_ts = now - 3 * 86400
    ws.last_period = "上午"
    ws.period = "午后"
    ws.last_letter_ts = now - 3600  # 1 小时前刚来信（8h 冷却内）
    ws.last_letter_date = "2026-08-19"
    letter2 = mgr.evaluate_and_dispatch(ws, favor=60, current_weather="晴朗",
                                        now_ts=now, today_str="2026-08-19",
                                        arc="late_arc")
    print(f"[冷却] 1h 内再触发: {'是（异常）' if letter2 else '否（冷却生效 ✅）'}")

    # ── 场景 3：宅邸篇不触发后期来信（arc 隔离）──
    ws3 = WorldState.now()
    ws3.last_interaction_ts = now - 3 * 86400
    ws3.last_period = "上午"
    ws3.period = "午后"
    letter3 = mgr.evaluate_and_dispatch(ws3, favor=60, current_weather="晴朗",
                                        now_ts=now, today_str="2026-08-19",
                                        arc="mansion_era")
    late_hit = False
    if letter3:
        for m in letter3.get("messages", []):
            if "并肩" in m["content"] or "战友" in m["content"] or "托付" in m["content"]:
                late_hit = True
    print(f"[arc隔离] 宅邸篇收到后期来信: {'是（异常）' if late_hit else '否（隔离生效 ✅）'}")
