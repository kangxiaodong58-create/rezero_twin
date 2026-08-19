"""崩溃现场捕获（Forensic Kernel M1）。

设计约束（FORENSIC_DEBUGGING_PROTOCOL v1.2 §0 / §2）：
- CRASH HANDLER MUST NOT：分配大内存 / 获取应用锁 / 网络 / 复杂逻辑 / 调 logger / 抛异常
- CRASH HANDLER MUST ONLY：read buffer → append marker → flush prepared file → exit
- 取证失败必须静默；绝不改变原始崩溃行为（包装后仍调用原 excepthook）

实现要点：
- 启动时（install_crash_handler）：预创建 incidents/pending/ 目录 + 预打开 dump 文件句柄
  + 环境快照（git 摘要等，崩溃时不可执行外部命令，提前拍好）
- 崩溃时（dump_crash）：只做 写 JSON → flush → rename pending→INC-{ts}，全 try/except
- 锁全部用超时/非阻塞获取：崩溃若发生在取证器持锁期间，宁可放弃取证也不死锁
- 正常退出（close）：清理未使用的 pending 占位，不留垃圾
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Dict, Optional, Tuple, Type

from .event_buffer import TIME_WINDOW_SECONDS
from .recorder import get_buffer

PENDING_DIR = "pending"
_INC_COUNTER = 0


def _git_summary() -> Dict[str, str]:
    """启动时 git 快照（崩溃时禁止执行外部命令，所以提前拍）。失败返回 unavailable。"""
    summary: Dict[str, str] = {}
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        summary["commit"] = r.stdout.strip() if r.returncode == 0 else "unavailable"
    except Exception:
        summary["commit"] = "unavailable"
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        summary["branch"] = r.stdout.strip() if r.returncode == 0 else "unavailable"
    except Exception:
        summary["branch"] = "unavailable"
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        summary["dirty_files"] = len(lines)
    except Exception:
        summary["dirty_files"] = -1
    return summary


class IncidentWriter:
    """预打开句柄 + 崩溃时极简写入 + rename 收尾。"""

    def __init__(self, incidents_dir: str) -> None:
        self.incidents_dir = incidents_dir
        self._fh: Optional[Any] = None
        self._pending_dir: Optional[str] = None
        self._startup_id: str = ""
        self._environment: Dict[str, Any] = {}
        self._dump_lock = threading.Lock()
        self._prepared = False
        self._last_error: Optional[str] = None  # 取证器自身诊断（静默记录）
        self._prepare()

    def _prepare(self) -> None:
        """启动时一次性准备（可失败，静默降级为无取证）。

        支持"重新武装"（dump 后再次调用）：环境快照只拍一次（git
        子进程是重活），后续复用；多崩溃场景（headless 战役）每次
        dump 后重新准备，保证连续取证。
        """
        try:
            os.makedirs(self.incidents_dir, exist_ok=True)
            self._pending_dir = os.path.join(self.incidents_dir, PENDING_DIR)
            os.makedirs(self._pending_dir, exist_ok=True)
            buf = get_buffer()
            self._startup_id = buf.startup_id if buf else "no-buffer"
            if not self._environment:  # git 快照只拍一次，复用
                self._environment = {
                    "python": sys.version.split()[0],
                    "platform": sys.platform,
                    "cwd": os.getcwd(),
                    "pid": os.getpid(),
                    "git": _git_summary(),
                    "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            dump_path = os.path.join(self._pending_dir, "dump.json")
            self._fh = open(dump_path, "w", encoding="utf-8")
            self._fh.write(json.dumps({"status": "RUNNING", "startup_id": self._startup_id}))
            self._fh.flush()
            self._prepared = True
        except Exception:
            self._prepared = False
            if self._fh is not None:
                try:
                    self._fh.close()
                except Exception:
                    pass
                self._fh = None

    @property
    def prepared(self) -> bool:
        return self._prepared

    def dump_crash(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_tb: Any,
        thread_name: str,
    ) -> Optional[str]:
        """崩溃时调用：写完整 dump → rename 为 INC-xxx。返回 incident_id 或 None。

        全 try/except 静默；锁非阻塞获取（防重入 / 防持锁崩溃死锁）。
        """
        if not self._prepared or self._fh is None or self._pending_dir is None:
            return None
        if not self._dump_lock.acquire(blocking=False):
            return None
        try:
            global _INC_COUNTER
            _INC_COUNTER += 1
            incident_id = (
                f"INC-{time.strftime('%Y%m%d-%H%M%S')}-{_INC_COUNTER:03d}"
            )
            tb_text = ""
            try:
                tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
                tb_text = tb_text[-8000:]  # 截断防超大 traceback
            except Exception:
                tb_text = f"{exc_type.__name__}: {exc_value}"
            payload = {
                "incident_id": incident_id,
                "startup_id": self._startup_id,
                "status": "PENDING",
                "crash": {
                    "type": exc_type.__name__,
                    "value": str(exc_value)[:2000],
                    "thread": thread_name,
                    "traceback": tb_text,
                    "at_wall": time.time(),
                    "at_mono": time.monotonic(),
                },
                "environment": self._environment,
                "events": get_buffer().snapshot(time_window=TIME_WINDOW_SECONDS)
                if get_buffer() else [],
            }
            # 极简写入序列：seek 重写预打开文件 → flush → rename
            self._fh.seek(0)
            self._fh.truncate()
            json.dump(payload, self._fh, ensure_ascii=False, indent=1)
            self._fh.flush()
            self._fh.close()
            self._fh = None
            # Windows 实战坑：写完立即 rename 会被 Defender 实时扫描锁定
            # （PermissionError WinError 5，间歇性）。退避重试；仍失败则
            # 保留 pending 目录（证据不丢），由 manifest 扫描兜底。
            target = os.path.join(self.incidents_dir, incident_id)
            renamed = False
            for delay in (0.05, 0.2, 0.8):
                try:
                    os.rename(self._pending_dir, target)
                    renamed = True
                    break
                except OSError:
                    time.sleep(delay)
            if renamed:
                self._pending_dir = None
                self._prepared = False
                self._prepare()  # 重新武装：支持同进程多崩溃（headless 战役）
                return incident_id
            # 降级：rename 失败，证据留在 pending/（manifest 可发现）。
            # 不重新武装：pending 里的证据不能被覆盖。
            self._prepared = False
            return incident_id
        except Exception as e:
            self._last_error = f"{type(e).__name__}: {e}"
            return None
        finally:
            try:
                self._dump_lock.release()
            except Exception:
                pass

    def close(self) -> None:
        """正常退出：关闭句柄、清理未使用的 pending 占位。静默。

        注意：pending 里若已有崩溃 dump（rename 失败降级保留的证据），
        不得删除——只清理启动时的 RUNNING 占位。
        """
        try:
            if self._fh is not None:
                self._fh.close()
                self._fh = None
            if self._pending_dir is not None and os.path.isdir(self._pending_dir):
                dump_path = os.path.join(self._pending_dir, "dump.json")
                keep = False
                try:
                    with open(dump_path, "r", encoding="utf-8") as f:
                        keep = json.load(f).get("status") != "RUNNING"
                except Exception:
                    keep = False
                if not keep:
                    for name in os.listdir(self._pending_dir):
                        try:
                            os.remove(os.path.join(self._pending_dir, name))
                        except Exception:
                            pass
                    try:
                        os.rmdir(self._pending_dir)
                    except Exception:
                        pass
        except Exception:
            pass


_writer: Optional[IncidentWriter] = None
_orig_excepthook: Any = None
_orig_threading_hook: Any = None


def install_crash_handler(incidents_dir: str) -> Optional[IncidentWriter]:
    """安装崩溃捕获：包装 sys.excepthook 与 threading.excepthook。

    包装后仍调用原 hook（打印 traceback 等原始行为不变），只在其前取证。
    可重复安装（重复调用会重新包装，writer 只建一次）。
    """
    global _writer, _orig_excepthook, _orig_threading_hook
    if _writer is not None:
        return _writer
    w = IncidentWriter(incidents_dir)
    if not w.prepared:
        return None
    _writer = w

    if _orig_excepthook is None:
        _orig_excepthook = sys.excepthook

        def _hook(etype: Type[BaseException], evalue: BaseException, etb: Any) -> None:
            w.dump_crash(etype, evalue, etb, threading.current_thread().name)
            _orig_excepthook(etype, evalue, etb)

        sys.excepthook = _hook

    if _orig_threading_hook is None:
        _orig_threading_hook = threading.excepthook

        def _thook(args: Any) -> None:
            try:
                w.dump_crash(
                    args.exc_type,
                    args.exc_value,
                    args.exc_traceback,
                    getattr(args.thread, "name", "?"),
                )
            except Exception:
                pass
            _orig_threading_hook(args)

        threading.excepthook = _thook

    return _writer


def uninstall_crash_handler() -> None:
    """恢复原始 excepthook（测试用）。"""
    global _writer, _orig_excepthook, _orig_threading_hook
    try:
        if _orig_excepthook is not None:
            sys.excepthook = _orig_excepthook
        if _orig_threading_hook is not None:
            threading.excepthook = _orig_threading_hook
    except Exception:
        pass
    if _writer is not None:
        _writer.close()
    _writer = None
    _orig_excepthook = None
    _orig_threading_hook = None
