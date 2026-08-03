"""世界状态持久化（docx 方案兼容入口）。

v10.4 落地时选择沿用 memory.json 单持久化管线，避免独立的 world_state.json
造成双文件同步问题。本模块作为《代码实现》docx 原文的 API 兼容层存在：

- 暴露 docx 中同名的 WorldState 类与函数（load_world_state / save_world_state /
  update_world_state_on_startup / mark_interaction）。
- 底层委托给已验证的 shared.state.WorldState，字段名做映射，保证旧存档、
  GUI、冒烟测试都不感知差异。
- 不破坏现有架构，也不引入新的持久化路径。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from shared.state import WorldState as _CoreWorldState

__all__ = [
    "WorldState",
    "load_world_state",
    "save_world_state",
    "update_world_state_on_startup",
    "mark_interaction",
]


class WorldState(_CoreWorldState):
    """docx 风格的 WorldState 兼容类。

    继承内部已实现的核心状态机，仅额外提供 docx 原文使用的字段别名，
    使按 docx 编写的调用代码可以直接使用。
    """

    @property
    def last_real_timestamp(self) -> float:
        return self.last_real_ts

    @last_real_timestamp.setter
    def last_real_timestamp(self, value: float) -> None:
        self.last_real_ts = value

    @property
    def last_interaction_real(self) -> float:
        return self.last_interaction_ts

    @last_interaction_real.setter
    def last_interaction_real(self, value: float) -> None:
        self.last_interaction_ts = value

    @property
    def days_away(self) -> int:
        return self.days_since_last

    @days_away.setter
    def days_away(self, value: int) -> None:
        self.days_since_last = value

    @property
    def system_date(self) -> str:
        return (self.current_time or "")[:10]

    @property
    def hour(self) -> int:
        try:
            return int((self.current_time or "")[11:13])
        except Exception:
            return datetime.now().hour


def load_world_state() -> WorldState:
    """从 memory.json 恢复世界状态（docx 兼容入口）。"""
    from shared.memory_store import MemoryStore

    store = MemoryStore()
    mem = store.load()
    saved = mem.get("world_state")
    return WorldState.load_or_create(saved)


def save_world_state(ws: WorldState) -> None:
    """保存世界状态到 memory.json（docx 兼容入口）。"""
    from shared.memory_store import MemoryStore

    store = MemoryStore()
    mem = store.load()
    mem["world_state"] = ws.save_dict()
    store.save(mem)


def update_world_state_on_startup(
    ws: WorldState, weather_change_hours: float = 8.0
) -> WorldState:
    """启动时更新时段、离线天数与自然天气演变（docx 兼容入口）。

    当前 WorldState.load_or_create 已在内部完成时段、离线天数与 ≥8h 天气推演，
    因此这里用当前存档值重新触发一次计算即可；weather_change_hours 参数保留以
    兼容 docx 签名，但实际阈值由核心 WorldState.WEATHER_CHANGE_HOURS 控制。
    """
    # 保留参数签名兼容性；重新 load_or_create 会基于当前时间重算。
    saved = ws.save_dict()
    return WorldState.load_or_create(saved)


def mark_interaction(ws: WorldState) -> None:
    """用户产生有效对话时调用：刷新最后互动时间戳并清零离线天数。"""
    ws.mark_interaction()
