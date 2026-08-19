# -*- coding: utf-8 -*-
"""验证 O-1 场景约束刷新（多 seed 稳定性）。"""
import sys
sys.path.insert(0, r"C:\Users\11985\.qclaw\workspace\rezero_twin")

from shared.world_state import WorldState
from shared.state import EVENT_POOL
from shared import vignette as _v

CONFLICT = "宅邸走廊"

tea = next(ev for ev in EVENT_POOL if ev["id"] == "tea_ready")
for s in [1, 42, 99, 1234, 99999]:
    ws = WorldState.now()
    ws.weather_seed = s
    ws.active_event = tea["desc"]
    ws.active_event_id = "tea_ready"
    ws.refresh_active_event(scene="LIBRARY")
    loc = _v._derive_location(ws.active_event)
    ok = loc != CONFLICT
    print(f"seed={s:>6}: id={ws.active_event_id} loc={loc} 冲突消除={ok}")
    assert ok, f"seed={s} 仍选中走廊事件"
print("\n场景约束刷新验证通过 ✅")
