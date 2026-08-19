"""Forensic Kernel M1：运行时取证黑匣子。

用法（main.py / gui.py 入口处）：
    from runtime.forensic import init_forensic, shutdown_forensic, record
    writer = init_forensic(incidents_dir=...)   # 安装崩溃捕获 + 启动缓冲
    record("MESSAGE_RECEIVED", component="bridge", generation=1)
    shutdown_forensic()                          # 正常退出时清理

未初始化时 record() / transition() 均为安全 no-op。
本包为纯 Python，禁止 import PySide6（headless 可跑）。
"""

from __future__ import annotations

import os
from typing import Optional

from . import recorder
from .crash_dump import IncidentWriter, install_crash_handler, uninstall_crash_handler
from .event_buffer import EventRingBuffer
from .recorder import get_buffer, record, set_buffer, transition

__all__ = [
    "EventRingBuffer",
    "IncidentWriter",
    "init_forensic",
    "shutdown_forensic",
    "record",
    "transition",
    "get_buffer",
]

_active_writer: Optional[IncidentWriter] = None


def init_forensic(
    incidents_dir: Optional[str] = None,
    *,
    buffer: Optional[EventRingBuffer] = None,
) -> Optional[IncidentWriter]:
    """初始化取证子系统。

    - 默认 incidents 目录：REZERO_INCIDENTS_DIR 环境变量 > cwd/incidents
    - 返回 IncidentWriter（取证可用）或 None（静默降级，如目录不可写）
    """
    global _active_writer
    if incidents_dir is None:
        incidents_dir = os.environ.get("REZERO_INCIDENTS_DIR") or os.path.join(
            os.getcwd(), "incidents"
        )
    buf = buffer or EventRingBuffer()
    set_buffer(buf)
    if get_buffer() is not buf:
        return None
    w = install_crash_handler(incidents_dir)
    if w is not None:
        _active_writer = w
    return w


def shutdown_forensic() -> None:
    """正常退出清理：关闭句柄、移除未使用的 pending 占位、恢复 excepthook。"""
    global _active_writer
    uninstall_crash_handler()
    _active_writer = None
    set_buffer(None)
