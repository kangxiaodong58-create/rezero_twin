"""Forensic Kernel M2 测试：案件交接层（Handoff Protocol）。

验证点（FORENSIC_DEBUGGING_PROTOCOL v1.2 §2）：
- 崩溃落盘后 status=PENDING，scan 能发现
- claim 写入 claim token；重复认领被拒（防双 Agent 争抢）
- resolve / ignore 后不再出现在扫描结果
- 非案件目录 / 损坏 dump 静默处理
"""

from __future__ import annotations

import json
import sys

import pytest

from runtime.forensic import init_forensic, record, shutdown_forensic
from runtime.forensic.manifest import (
    claim_incident,
    list_incidents,
    mark_ignored,
    resolve_incident,
    scan_incidents,
)


@pytest.fixture
def incidents_with_crash(tmp_path):
    """安装取证 → 记事件 → 模拟崩溃 → 产生一个 PENDING 案件。"""
    incidents = tmp_path / "incidents"
    init_forensic(str(incidents))
    record("MESSAGE_RECEIVED", component="bridge", generation=1)
    record("API_TIMEOUT", component="bridge", generation=1, exception="timeout")
    sys.excepthook(RuntimeError, RuntimeError("crash-m2"), None)
    yield incidents
    shutdown_forensic()


def test_scan_finds_pending(incidents_with_crash):
    pending = scan_incidents(str(incidents_with_crash))
    assert len(pending) == 1
    p = pending[0]
    assert p["status"] == "PENDING"
    assert p["type"] == "RuntimeError"
    assert p["events"] == 2  # 崩溃时的事件缓冲已落盘


def test_claim_and_reject_double_claim(incidents_with_crash):
    inc_id = scan_incidents(str(incidents_with_crash))[0]["incident_id"]
    # 第一次认领成功
    assert claim_incident(str(incidents_with_crash), inc_id, claimant="hermes-cron") is True
    # 重复认领被拒（防双 Agent 争抢）
    assert claim_incident(str(incidents_with_crash), inc_id, claimant="user-session") is False
    dump = json.loads(
        (incidents_with_crash / inc_id / "dump.json").read_text(encoding="utf-8")
    )
    assert dump["status"] == "CLAIMED"
    assert dump["claimed_by"] == "hermes-cron"
    assert dump["claim_time"]


def test_resolve_removes_from_scan(incidents_with_crash):
    inc_id = scan_incidents(str(incidents_with_crash))[0]["incident_id"]
    assert resolve_incident(str(incidents_with_crash), inc_id) is True
    assert scan_incidents(str(incidents_with_crash)) == []


def test_ignore_removes_from_scan(incidents_with_crash):
    inc_id = scan_incidents(str(incidents_with_crash))[0]["incident_id"]
    assert mark_ignored(str(incidents_with_crash), inc_id) is True
    assert scan_incidents(str(incidents_with_crash)) == []
    # 但仍可见（审计）
    all_incs = list_incidents(str(incidents_with_crash))
    assert len(all_incs) == 1 and all_incs[0]["status"] == "IGNORED"


def test_unknown_incident_silent(tmp_path):
    assert claim_incident(str(tmp_path), "INC-99999999-000000-001", "x") is False
    assert resolve_incident(str(tmp_path), "not-an-incident") is False
    assert scan_incidents(str(tmp_path)) == []
