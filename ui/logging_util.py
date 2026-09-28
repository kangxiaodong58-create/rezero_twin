"""应用日志（SPEC-20260922-22 S1a 自 gui.py 逐字归位）。"""

from __future__ import annotations

import os
import sys
import threading
from datetime import datetime
from datetime import date, datetime
from shared.config import load_env, get_data_dir


_LOG_FH = None


_LOG_FH_PATH = None


# ═══ A18（SPEC-20260922-13）：日志双档 ═══════════════════════════
# 常规档：**常开句柄 + flush**（不 fsync）——实测 729 µs/条 → ≈8 µs/条（94×）。
# 关键档 `durable=True`：flush + fsync，用于崩溃/异常/存档/生命周期/轮次中止等
#   必须留证的事件（精确 53 处，清单见 docs/devlog/步1-4前置材料_2026-09-27.md §1）。
# 线程安全：`VignetteWorker.run` 在 QThread 内调用 `_log`（gui.py:2509-2549 接线 +
#   :2516/2531/2534 调用点）⇒ 必须加锁；崩溃路径不阻塞（acquire timeout 0.5s）。
# 回退开关：`REZERO_LOG_DURABLE=1` → 全部走 fsync（取证/排障期一键回退，无需改码）。
_LOG_LOCK = threading.Lock()


_LOG_FSYNC_ALL = os.environ.get("REZERO_LOG_DURABLE", "") not in ("", "0", "false", "False")


# 日志与持久化统一走 get_data_dir()：
# frozen 时指向 EXE 同级 data/，源码时指向项目根 data/。
# 切勿用 _PROJECT_ROOT（frozen 下是 _MEIPASS 临时目录，退出即丢）。
# V16.1：支持 REZERO_GUI_LOG 覆盖——测试/CI 不得追加写真实 data/gui.log。
def _log_path() -> str:
    return os.environ.get("REZERO_GUI_LOG") or os.path.join(get_data_dir(), "gui.log")


def _log_open_locked():
    """（调用方须持锁）打开/重开日志句柄。"""
    global _LOG_FH, _LOG_FH_PATH
    path = _log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    _LOG_FH = open(path, "a", encoding="utf-8")
    _LOG_FH_PATH = path
    return _LOG_FH


def _log_close() -> None:
    """atexit（F13-3：模块导入期注册）：flush + close，置空句柄。"""
    global _LOG_FH, _LOG_FH_PATH
    with _LOG_LOCK:
        try:
            if _LOG_FH is not None:
                _LOG_FH.flush()
                _LOG_FH.close()
        except Exception:
            pass
        _LOG_FH = None
        _LOG_FH_PATH = None


def _log_write_locked(msg: str, durable: bool) -> None:
    global _LOG_FH
    try:
        f = _LOG_FH
        # 重开条件：未打开 / 已被 atexit 关闭（F13-3）/ 目标路径已变（REZERO_GUI_LOG 或 get_data_dir）
        if f is None or getattr(f, "closed", True) or _LOG_FH_PATH != _log_path():
            f = _log_open_locked()
        f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        f.flush()
        if durable or _LOG_FSYNC_ALL:
            os.fsync(f.fileno())
    except Exception:
        _LOG_FH = None    # 句柄异常（被清理/盘满）→ 丢弃本条并在下次重开


def _log(msg: str, durable: bool = False) -> None:
    """A18 双档日志：常规档缓冲写；`durable=True` 关键档强制 fsync。

    绝不抛异常（日志不得影响主流程）；崩溃路径 acquire 超时即放弃本条。
    """
    if not _LOG_LOCK.acquire(timeout=0.5):
        return
    try:
        _log_write_locked(msg, durable)
    finally:
        _LOG_LOCK.release()


