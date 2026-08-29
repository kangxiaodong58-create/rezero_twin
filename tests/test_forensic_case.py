"""Forensic Kernel M4 测试：案件目录模板 + CASE_OPEN→CASE_CLOSED 编排。

验证点（FORENSIC_DEBUGGING_PROTOCOL v1.2 §2/§4；M4 验收 = 真实案件走通全流程）：
- open_case：认领 + .debug/CASE-<id>/case.md 生成（预填现场摘要）+ 状态 INVESTIGATING
- 防双 Agent：第二次 open_case 被拒（返回 None）
- close_case：RESOLVED + case.md 结案节；案件退出扫描
- 未知案件 / 未开案结案的静默行为
"""

from __future__ import annotations

import json
import sys

import pytest

from runtime.forensic import init_forensic, record, shutdown_forensic
from runtime.forensic.case import close_case, open_case
from runtime.forensic.manifest import scan_incidents


@pytest.fixture
def pending_incident(tmp_path):
    """安装取证 → 记事件（含状态跃迁）→ 模拟崩溃 → 一个 PENDING 案件。"""
    incidents = tmp_path / "incidents"
    init_forensic(str(incidents))
    record("MESSAGE_RECEIVED", component="bridge", generation=1)
    record("STATE_TRANSITION", component="engine.arc",
           state_before="mansion_era", state_after="empire_era")
    sys.excepthook(RuntimeError, RuntimeError("crash-m4"), None)
    yield str(incidents)
    shutdown_forensic()


def _first_pending(incidents: str) -> str:
    return scan_incidents(incidents)[0]["incident_id"]


def test_open_case_creates_workdir_and_investigating(pending_incident, tmp_path):
    inc_id = _first_pending(pending_incident)
    case_md = open_case(pending_incident, inc_id, claimant="agent-a",
                        cases_dir=str(tmp_path / "cases"))
    assert case_md is not None
    with open(case_md, "r", encoding="utf-8") as f:
        text = f.read()
    assert inc_id in text, "case.md 应含案件 ID"
    assert "agent-a" in text, "case.md 应含认领人"
    assert "崩溃类型" in text, "case.md 应预填现场摘要"
    # dump.json 状态推进到 INVESTIGATING（唯一状态真相）
    dump = json.loads(
        (tmp_path / "incidents" / inc_id / "dump.json").read_text(encoding="utf-8"))
    assert dump["status"] == "INVESTIGATING"


def test_open_case_default_dir_is_debug(pending_incident, tmp_path):
    """cases_dir 缺省 → 与 incidents 同级 .debug/CASE-<id>/。"""
    inc_id = _first_pending(pending_incident)
    case_md = open_case(pending_incident, inc_id, claimant="agent-a")
    assert case_md is not None
    assert str(tmp_path / ".debug" / f"CASE-{inc_id}" / "case.md") == case_md


def test_double_agent_claim_rejected(pending_incident):
    inc_id = _first_pending(pending_incident)
    assert open_case(pending_incident, inc_id, claimant="agent-a") is not None
    assert open_case(pending_incident, inc_id, claimant="agent-b") is None, \
        "已认领案件不得被第二个 Agent 开案"


def test_close_case_resolves_and_appends(pending_incident, tmp_path):
    inc_id = _first_pending(pending_incident)
    case_md = open_case(pending_incident, inc_id, claimant="agent-a",
                        cases_dir=str(tmp_path / "cases"))
    assert close_case(pending_incident, inc_id, "超时注入压测误报，非产品缺陷",
                      root_cause="mock 注入超时", fix="无需修复",
                      cases_dir=str(tmp_path / "cases")) is True
    assert scan_incidents(pending_incident) == [], "结案后不应再出现在扫描"
    with open(case_md, "r", encoding="utf-8") as f:
        text = f.read()
    assert "CASE_CLOSED" in text and "超时注入压测误报" in text, "case.md 应含结案节"


def test_close_case_without_open_graceful(pending_incident):
    """未开案（无 case.md）：仅做 resolve，返回 False（无工作台可写）。"""
    inc_id = _first_pending(pending_incident)
    assert close_case(pending_incident, inc_id, "跳过调查直接结案") is False
    assert scan_incidents(pending_incident) == []


def test_unknown_incident_silent(tmp_path):
    assert open_case(str(tmp_path), "INC-99999999-000000-001", claimant="x") is None
    assert close_case(str(tmp_path), "INC-99999999-000000-001", "x") is False
