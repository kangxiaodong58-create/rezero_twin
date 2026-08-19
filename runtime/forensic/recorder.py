"""事件注入 API（Forensic Kernel M1）。

调用方（main / gui / llm.bridge）只 import record / transition；
未初始化时全部安全 no-op——对现有代码路径零影响。
"""

from __future__ import annotations

from typing import Optional

from .event_buffer import EventRingBuffer

_buffer: Optional[EventRingBuffer] = None


def set_buffer(buf: Optional[EventRingBuffer]) -> None:
    """由 init_forensic 调用。传入 None 恢复 no-op 状态。"""
    global _buffer
    _buffer = buf


def get_buffer() -> Optional[EventRingBuffer]:
    return _buffer


def record(
    event: str,
    *,
    component: str = "app",
    generation: Optional[int] = None,
    session_id: Optional[str] = None,
    state_before: Optional[str] = None,
    state_after: Optional[str] = None,
    payload_summary: Optional[str] = None,
    exception: Optional[str] = None,
) -> bool:
    """记录一条事件。未初始化 / 写入失败均静默返回 False。"""
    if _buffer is None:
        return False
    return _buffer.append(
        event,
        component=component,
        generation=generation,
        session_id=session_id,
        state_before=state_before,
        state_after=state_after,
        payload_summary=payload_summary,
        exception=exception,
    )


def transition(
    component: str,
    from_state: str,
    to_state: str,
    *,
    generation: Optional[int] = None,
    session_id: Optional[str] = None,
) -> bool:
    """记录一次状态转换（STATE_TRANSITION 事件）。"""
    return record(
        "STATE_TRANSITION",
        component=component,
        generation=generation,
        session_id=session_id,
        state_before=from_state,
        state_after=to_state,
    )
