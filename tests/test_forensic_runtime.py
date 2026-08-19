"""Forensic Kernel M1 测试：环形缓冲 + 崩溃 dump + 静默降级。

验证点（对应 FORENSIC_DEBUGGING_PROTOCOL v1.2 §0/§2）：
- seq 递增且为唯一排序依据；(startup_id, seq) 跨进程分段
- 双时钟存在（monotonic + wall）
- 环形覆盖（200 上限）
- 未初始化时 record 安全 no-op
- 崩溃 → INC 目录落盘（events/crash/environment/git 快照）
- threading.excepthook 捕获工作线程异常
- 取证器失败静默（不影响原始崩溃行为）
- 正常退出清理 pending 占位
"""

from __future__ import annotations

import json
import os
import sys
import threading

import pytest

from runtime.forensic import EventRingBuffer, init_forensic, record, shutdown_forensic
from runtime.forensic import recorder
from runtime.forensic.crash_dump import IncidentWriter


@pytest.fixture
def forensic(tmp_path):
    """安装取证子系统，测试后彻底卸载（恢复原始 excepthook）。"""
    incidents = tmp_path / "incidents"
    init_forensic(str(incidents))
    yield incidents
    shutdown_forensic()


# ── 1. 环形缓冲基础 ──────────────────────────────────────────────

def test_buffer_seq_and_clocks(forensic):
    buf = recorder.get_buffer()
    assert buf is not None
    assert buf.append("EVT_A", component="t")
    assert buf.append("EVT_B", component="t")
    snap = buf.snapshot()
    assert [e["event"] for e in snap] == ["EVT_A", "EVT_B"]
    assert snap[0]["seq"] == 1 and snap[1]["seq"] == 2
    # 双时钟：monotonic 与 wall 都存在且为数值
    assert isinstance(snap[0]["ts_mono"], float)
    assert isinstance(snap[0]["ts_wall"], float)
    # startup_id 跨进程分段标识存在
    assert snap[0]["startup_id"] == buf.startup_id


def test_buffer_ring_capacity(forensic):
    buf = recorder.get_buffer()
    for i in range(250):
        buf.append(f"EVT_{i}", component="t")
    snap = buf.snapshot()
    assert len(snap) == 200  # 环形上限
    assert snap[0]["event"] == "EVT_50"  # 最旧的 50 条被覆盖
    assert snap[-1]["event"] == "EVT_249"
    # seq 仍然严格递增（覆盖后不重置）
    seqs = [e["seq"] for e in snap]
    assert seqs == sorted(seqs) and len(set(seqs)) == 200


def test_generation_field(forensic):
    assert record("X", component="t", generation=37, state_before="IDLE", state_after="RUN")
    ev = recorder.get_buffer().snapshot()[-1]
    assert ev["generation"] == 37
    assert ev["state_before"] == "IDLE" and ev["state_after"] == "RUN"


def test_record_noop_when_uninitialized():
    recorder.set_buffer(None)
    assert record("X", component="t") is False  # 未初始化：静默 no-op，不抛


def test_concurrent_append_safe(forensic):
    buf = recorder.get_buffer()
    errors = []

    def writer():
        try:
            for i in range(200):
                buf.append(f"EVT", component="thr", generation=i)
        except Exception as e:  # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    snap = buf.snapshot()
    assert len(snap) == 200
    seqs = [e["seq"] for e in snap]
    assert seqs == sorted(seqs)  # 并发写入后 seq 仍严格有序（锁保护）


# ── 2. 崩溃 dump 链路 ────────────────────────────────────────────

def _simulate_main_thread_crash():
    sys.excepthook(ValueError, ValueError("boom-test"), None)


def test_crash_dump_creates_incident(forensic):
    record("MESSAGE_RECEIVED", component="bridge", generation=1)
    record("API_REQUEST", component="bridge", generation=1)
    _simulate_main_thread_crash()

    incs = [d for d in os.listdir(forensic) if d.startswith("INC-")]
    assert len(incs) == 1
    inc_dir = forensic / incs[0]
    dump = json.loads((inc_dir / "dump.json").read_text(encoding="utf-8"))

    assert dump["incident_id"] == incs[0]
    assert dump["status"] == "PENDING"
    assert dump["crash"]["type"] == "ValueError"
    assert "boom-test" in dump["crash"]["value"]
    assert [e["event"] for e in dump["events"]] == ["MESSAGE_RECEIVED", "API_REQUEST"]
    assert dump["startup_id"]
    # 环境快照（git 摘要启动时已拍）
    assert "git" in dump["environment"]
    assert "commit" in dump["environment"]["git"]
    # pending 占位已被 rename 走
    assert not (forensic / "pending").exists()


def test_crash_dump_worker_thread(forensic):
    """threading.excepthook 捕获工作线程异常并落盘。"""
    def boom():
        raise RuntimeError("worker-boom")

    t = threading.Thread(target=boom, name="llm-worker")
    t.start()
    t.join()  # 异常进 threading.excepthook，线程正常结束

    incs = [d for d in os.listdir(forensic) if d.startswith("INC-")]
    assert len(incs) == 1
    dump = json.loads((forensic / incs[0] / "dump.json").read_text(encoding="utf-8"))
    assert dump["crash"]["type"] == "RuntimeError"
    assert dump["crash"]["thread"] == "llm-worker"
    assert "worker-boom" in dump["crash"]["value"]


def test_dump_keeps_original_excepthook(forensic, capsys):
    """取证后仍调用原 excepthook（打印 traceback），原始崩溃行为不变。"""
    _simulate_main_thread_crash()
    err = capsys.readouterr().err
    assert "boom-test" in err  # 原始 stderr 输出仍在


def test_shutdown_cleans_pending(tmp_path):
    """正常退出：不留 pending 占位、恢复 excepthook。"""
    incidents = tmp_path / "incidents"
    original = sys.excepthook
    init_forensic(str(incidents))
    assert sys.excepthook is not original
    shutdown_forensic()
    assert sys.excepthook is original
    assert not (incidents / "pending").exists()
    assert record("X", component="t") is False  # 卸载后 no-op


# ── 3. 静默失败 ─────────────────────────────────────────────────

def test_writer_failure_is_silent(tmp_path):
    """取证器故障绝不抛异常、不影响调用方。"""
    writer = IncidentWriter(str(tmp_path / "incidents"))
    if writer.prepared:
        # 破坏状态：关闭句柄后再次 dump（内部全 try/except）
        writer.close()
        writer._prepared = True  # 人为制造不一致状态
        writer._fh = None
        assert writer.dump_crash(ValueError, ValueError("x"), None, "t") is None
    else:
        assert writer.dump_crash(ValueError, ValueError("x"), None, "t") is None
