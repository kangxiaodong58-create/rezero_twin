"""兼容 shim（SPEC-20260922-16 方案 B）：**仅外部/历史脚本兼容，新代码请用 `shared.state`。**

背景：v10.4 落地时选择沿用 memory.json 单持久化管线（不引入独立 `world_state.json`），
本模块是《代码实现》docx 原文的 API 兼容入口。方案 B 起本模块**自身不含任何状态逻辑**：

- `WorldState` = 核心 `shared.state.WorldState` 的**别名子类**（仅 docx 时代 4 个字段别名）；
- 4 个模块函数**全部转调核心**（`load_or_create` / `save_dict` / `mark_interaction`）。

迁移指引（重跑 `docs/evaluation/sessions/**` 历史探针时）：

    # 旧（仍可导入，但不推荐）
    from shared.world_state import WorldState, load_world_state, save_world_state
    # 新（核心类单源）
    from shared.state import WorldState
    from shared.memory_store import MemoryStore
    store = MemoryStore()
    ws = WorldState.load_or_create(store.load().get("world_state"))
    store.set("world_state", ws.save_dict())
"""

from __future__ import annotations

from datetime import datetime

from shared.state import WorldState as _CoreWorldState

__all__ = [
    "WorldState",
    "load_world_state",
    "save_world_state",
    "update_world_state_on_startup",
    "mark_interaction",
]


def _hour_of(current_time: str) -> int:
    try:
        return int((current_time or "")[11:13])
    except Exception:
        return datetime.now().hour


class WorldState(_CoreWorldState):
    """docx 时代字段别名（**纯别名、零逻辑**）。

    仅为「按 docx 编写的外部脚本不炸」而保留；新代码请直接用 `shared.state.WorldState`。
    """

    last_real_timestamp = property(
        lambda s: s.last_real_ts, lambda s, v: setattr(s, "last_real_ts", v))
    last_interaction_real = property(
        lambda s: s.last_interaction_ts, lambda s, v: setattr(s, "last_interaction_ts", v))
    days_away = property(
        lambda s: s.days_since_last, lambda s, v: setattr(s, "days_since_last", v))
    system_date = property(lambda s: (s.current_time or "")[:10])
    hour = property(lambda s: _hour_of(s.current_time))


def _store():
    """核心单持久化管线（memory.json）——与 GUI/CLI 完全同一路径。"""
    from shared.memory_store import MemoryStore

    return MemoryStore()


def load_world_state() -> WorldState:
    """从 memory.json 恢复世界状态（转调核心 `load_or_create`）。"""
    return WorldState.load_or_create(_store().load().get("world_state"))


def save_world_state(ws: WorldState) -> None:
    """写回 memory.json（转调核心 `save_dict` + `MemoryStore.set`）。"""
    _store().set("world_state", ws.save_dict())


def update_world_state_on_startup(
    ws: WorldState, weather_change_hours: float = 8.0
) -> WorldState:
    """启动更新（转调核心 `load_or_create`）。

    时段、离线天数与 ≥8h 天气推演都在核心 `load_or_create` 内部完成；
    `weather_change_hours` 参数保留**仅为 docx 签名兼容**，实际阈值由
    `WorldState.WEATHER_CHANGE_HOURS` 控制。
    """
    return WorldState.load_or_create(ws.save_dict())


def mark_interaction(ws: WorldState) -> None:
    """转调核心 `WorldState.mark_interaction()`。"""
    ws.mark_interaction()
