"""A18（SPEC-20260922-13）：`_log` 双档日志行为回归（零 API、零网络）。

覆盖：
1. 常规档**不** fsync（94× 提速的来源）；`durable=True` 恰好 fsync 一次；
2. `REZERO_LOG_DURABLE=1` 回退开关 → 全部走 fsync；
3. atexit 关闭后**自动重开**（F13-3）；
4. **线程安全**（F13-2：`VignetteWorker.run` 在 QThread 内调用 `_log`）——多线程并发写不丢行、不撕裂；
5. **清单契约**：`gui.py` 内 `durable=True` 精确等于 53 处（
   清单见 `docs/devlog/步1-4前置材料_2026-09-27.md` §1；增删关键档必须同步该清单）。
"""
import pathlib
import re
import sys
import threading

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import gui  # noqa: E402

DURABLE_SITE_COUNT = 53


@pytest.fixture()
def logfile(tmp_path, monkeypatch):
    """每个用例一条独立日志；隔离 REZERO_GUI_LOG 并把「全 fsync」关掉。"""
    path = tmp_path / "gui.log"
    monkeypatch.setenv("REZERO_GUI_LOG", str(path))
    monkeypatch.setattr(gui, "_LOG_FSYNC_ALL", False)
    gui._log_close()                 # 强制按新路径重开
    yield path
    gui._log_close()


def _spy_fsync(monkeypatch):
    calls = {"n": 0}
    monkeypatch.setattr(gui.os, "fsync", lambda fd: calls.__setitem__("n", calls["n"] + 1))
    return calls


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_regular_tier_does_not_fsync(logfile, monkeypatch):
    """常规档：只 flush，不 fsync（提速来源）；内容立即可读。"""
    calls = _spy_fsync(monkeypatch)
    gui._log("常规-1")
    gui._log("常规-2")
    assert calls["n"] == 0, "常规档不应触发 fsync"
    body = _read(logfile)
    assert "常规-1" in body and "常规-2" in body


def test_durable_tier_fsyncs_once(logfile, monkeypatch):
    """关键档：恰好一次 fsync。"""
    calls = _spy_fsync(monkeypatch)
    gui._log("关键-事件", durable=True)
    assert calls["n"] == 1, "durable=True 必须恰好 fsync 一次"
    assert "关键-事件" in _read(logfile)


def test_env_switch_forces_all_fsync(logfile, monkeypatch):
    """REZERO_LOG_DURABLE=1 回退：常规调用也走 fsync（排障/取证期）。"""
    calls = _spy_fsync(monkeypatch)
    monkeypatch.setattr(gui, "_LOG_FSYNC_ALL", True)
    gui._log("回退-全档")
    assert calls["n"] == 1


def test_reopens_after_close(logfile):
    """F13-3：atexit（或显式 close）之后调用仍能落盘——句柄自动重开。"""
    gui._log("关闭前")
    gui._log_close()
    assert gui._LOG_FH is None
    gui._log("关闭后")
    body = _read(logfile)
    assert "关闭前" in body and "关闭后" in body, "关闭后调用必须自动重开并落盘"


def test_switch_log_path_takes_effect(tmp_path, monkeypatch):
    """路径感知：REZERO_GUI_LOG 变更后写入新文件（不写错档）。"""
    p1, p2 = tmp_path / "a.log", tmp_path / "b.log"
    monkeypatch.setenv("REZERO_GUI_LOG", str(p1))
    monkeypatch.setattr(gui, "_LOG_FSYNC_ALL", False)
    gui._log_close()
    gui._log("写入-a")
    monkeypatch.setenv("REZERO_GUI_LOG", str(p2))
    gui._log("写入-b")
    assert "写入-a" in _read(p1) and "写入-b" in _read(p2)
    assert "写入-b" not in _read(p1)


def test_thread_safety_no_lost_or_torn_lines(logfile):
    """F13-2：多线程并发写——行数完整、格式完好（锁生效）。"""
    n_threads, per_thread = 8, 25
    def worker(tid: int) -> None:
        for i in range(per_thread):
            gui._log(f"并发 t{tid}-{i}", durable=True)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    lines = [ln for ln in _read(logfile).splitlines() if ln.strip()]
    assert len(lines) == n_threads * per_thread, f"应写满 {n_threads * per_thread} 行，实得 {len(lines)}"
    pat = re.compile(r"^\[[\dT:\-\.]+\] 并发 t\d+-\d+$")
    bad = [ln for ln in lines if not pat.match(ln)]
    assert not bad, f"存在撕裂行：{bad[:3]}"


def test_durable_site_count_matches_manifest():
    """清单契约：durable=True 精确 53 处（增删须同步 devlog §1 与 SPEC-13）。"""
    src = (PROJECT_ROOT / "gui.py").read_text(encoding="utf-8")
    # 只数真实关键字调用（`, durable=True)`），不数注释/文档字符串里的同名字样
    cnt = len(re.findall(r"durable\s*=\s*True\s*\)", src))
    assert cnt == DURABLE_SITE_COUNT, (
        f"关键档数量漂移：期望 {DURABLE_SITE_COUNT}，实得 {cnt}。"
        f"请同步 docs/devlog/步1-4前置材料_2026-09-27.md §1 清单与 SPEC-20260922-13。")
