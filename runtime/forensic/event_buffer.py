"""事件环形缓冲：崩溃前最后 N 个事件的黑匣子（Forensic Kernel M1）。

设计约束（FORENSIC_DEBUGGING_PROTOCOL v1.2 §0 / §2）：
- seq 是唯一排序依据；时间戳只作物理时间参考（可能同毫秒/跳变）
- 双时钟：monotonic（算间隔）+ wall clock（参考）
- (startup_id, seq) 跨进程分段：进程重启后 seq 重新从 0 开始，靠 startup_id 区分
- 只记录状态标识（generation + 枚举值），不记录状态对象（防 Heisenberg 效应）
- 所有锁用超时获取，所有操作静默失败——取证器绝不允许成为新的崩溃源

本模块为纯 Python，禁止 import PySide6。
"""

from __future__ import annotations

import itertools
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

MAX_EVENTS = 200          # 环形容量上限（200 事件 × ~500B ≈ 100KB，可接受）
TIME_WINDOW_SECONDS = 60.0  # 时间窗：dump 时只保留最近 60 秒
_LOCK_TIMEOUT = 0.05      # 锁获取超时：崩溃 handler 中绝不能死锁


def _make_startup_id() -> str:
    """启动标识：时间戳 + PID（跨进程分段依据）。"""
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}"


class EventRingBuffer:
    """线程安全环形事件缓冲。所有方法静默失败，绝不抛异常。"""

    def __init__(self, max_events: int = MAX_EVENTS, startup_id: Optional[str] = None) -> None:
        self._events: Deque[Dict[str, Any]] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._seq = itertools.count(1)
        self.startup_id = startup_id or _make_startup_id()

    def append(
        self,
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
        """写入一条事件。失败静默返回 False，不影响业务。"""
        try:
            entry = {
                "seq": next(self._seq),
                "startup_id": self.startup_id,
                "ts_mono": time.monotonic(),
                "ts_wall": time.time(),
                "generation": generation,
                "event": str(event),
                "component": str(component),
                "session_id": session_id,
                "state_before": state_before,
                "state_after": state_after,
                "payload_summary": payload_summary,
                "thread": threading.current_thread().name,
                "exception": exception,
            }
            if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
                return False
            try:
                self._events.append(entry)
            finally:
                self._lock.release()
            return True
        except Exception:
            return False

    def snapshot(self, time_window: Optional[float] = None) -> List[Dict[str, Any]]:
        """返回事件快照（时间窗过滤后）。崩溃 handler 中调用，锁超时返回空。"""
        try:
            if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
                return []
            try:
                items = list(self._events)
            finally:
                self._lock.release()
        except Exception:
            return []
        if time_window is None:
            return items
        try:
            cutoff = time.monotonic() - time_window
            return [e for e in items if e["ts_mono"] >= cutoff]
        except Exception:
            return items

    def __len__(self) -> int:
        try:
            if not self._lock.acquire(timeout=_LOCK_TIMEOUT):
                return 0
            try:
                return len(self._events)
            finally:
                self._lock.release()
        except Exception:
            return 0
