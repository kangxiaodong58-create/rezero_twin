"""案件目录模板 + Agent 侧编排（Forensic Kernel M4）。

对应 FORENSIC_DEBUGGING_PROTOCOL（docs/forensic/FORENSIC_DEBUGGING_PROTOCOL.md）§4：
案件工作目录 `.debug/CASE-<INC-id>/case.md` 由模板生成，是调查 Agent 的工作台；
`incidents/<INC-id>/dump.json` 始终是证据真相（本模块不改写事件数据，只改状态）。

工作流：
    open_case(...)   # claim（防双 Agent）→ 建案件目录 → 状态 INVESTIGATING → CASE_OPEN
    ...调查（读 dump.json / 复现 / 假设）...
    close_case(...)  # resolve → case.md 追加结案节 → CASE_CLOSED

状态机（dump.json status 字段为唯一真相）：
    PENDING → CLAIMED → INVESTIGATING → RESOLVED / IGNORED

约束：纯 Python，禁止 import PySide6；全部文件操作静默失败，绝不抛异常。
"""

from __future__ import annotations

import os
import time
from typing import Optional

from . import recorder
from .manifest import claim_incident, resolve_incident, set_incident_status

_CASE_TEMPLATE = """# 取证案件 {incident_id}

- **状态**: 调查中（INVESTIGATING）
- **开案时间**: {opened_at}
- **认领人**: {claimant}
- **证据目录**: `{incidents_dir}/{incident_id}/dump.json`
- **事件数**: {event_count}
- **崩溃类型**: {crash_type}
- **崩溃摘要**: {crash_value}

---

## 一、现场摘要（SCENE_FROZEN）

> 由开案脚本预填。调查人可补充，但不得改写 dump.json 原始数据。

{scene_notes}

## 二、时间线（seq 排序）

> 工具：`python -c "import json;d=json.load(open(r'{incidents_dir}/{incident_id}/dump.json',encoding='utf-8'));[print(e['seq'],e['event'],e.get('component'),e.get('payload_summary','')) for e in d['events']]"`

（待调查人填写关键事件序列）

## 三、假设与验证

（待调查人填写：H1 / 验证方式 / 结论）

> 第二、三节由调查人填写；「四、结案」一节由 close_case 自动追加，请勿手写。
"""


def _cases_dir(incidents_dir: str, cases_dir: Optional[str]) -> str:
    """默认案件目录：与 incidents 同级的 .debug/（设计 §9 布局）。"""
    if cases_dir:
        return cases_dir
    parent = os.path.dirname(os.path.abspath(incidents_dir.rstrip("/\\")))
    return os.path.join(parent, ".debug")


def _read_crash_brief(incidents_dir: str, incident_id: str) -> dict:
    """读 dump.json 的崩溃与事件概要（只读，失败给占位值）。"""
    import json

    brief = {"events": "?", "type": "?", "value": "?", "notes": "（dump.json 读取失败，手工检查）"}
    path = os.path.join(incidents_dir, incident_id, "dump.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        crash = payload.get("crash", {}) or {}
        brief["events"] = len(payload.get("events", []))
        brief["type"] = crash.get("type", "?")
        brief["value"] = (crash.get("value") or "")[:160]
        brief["notes"] = (
            f"- startup_id: `{payload.get('startup_id', '?')}`\n"
            f"- 崩溃线程: {crash.get('thread', '?')}\n"
            f"- 崩溃时间: {crash.get('at_wall', '?')}\n"
            f"- 事件窗口: 最后 {brief['events']} 条（含崩溃 marker）"
        )
    except Exception:
        pass
    return brief


def open_case(
    incidents_dir: str,
    incident_id: str,
    *,
    claimant: str,
    cases_dir: Optional[str] = None,
) -> Optional[str]:
    """开案：认领案件 → 生成案件目录与 case.md → 状态置 INVESTIGATING。

    返回 case.md 路径；认领失败（已被其他 Agent 认领）/ 案件不存在
    / 文件创建失败时返回 None（防双 Agent 争抢由 manifest.claim 保证）。
    """
    if not claim_incident(incidents_dir, incident_id, claimant):
        return None
    cdir = _cases_dir(incidents_dir, cases_dir)
    case_dir = os.path.join(cdir, f"CASE-{incident_id}")
    case_md = os.path.join(case_dir, "case.md")
    try:
        os.makedirs(case_dir, exist_ok=True)
        brief = _read_crash_brief(incidents_dir, incident_id)
        with open(case_md, "w", encoding="utf-8") as f:
            f.write(_CASE_TEMPLATE.format(
                incident_id=incident_id,
                opened_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                claimant=claimant,
                incidents_dir=os.path.abspath(incidents_dir),
                event_count=brief["events"],
                crash_type=brief["type"],
                crash_value=brief["value"],
                scene_notes=brief["notes"],
            ))
    except Exception:
        return None
    set_incident_status(incidents_dir, incident_id, "INVESTIGATING")
    recorder.record("CASE_OPEN", component="forensic",
                    session_id=incident_id, payload_summary=f"claimant={claimant}")
    return case_md


def close_case(
    incidents_dir: str,
    incident_id: str,
    resolution: str,
    *,
    root_cause: str = "",
    fix: str = "",
    cases_dir: Optional[str] = None,
) -> bool:
    """结案：RESOLVED → case.md 追加结案节 → CASE_CLOSED 事件。

    root_cause / fix 建议填写（协议 §4 结案必填字段）；resolution 为
    一句话结论。案件未开（无 case.md）时仅做 resolve 并返回 False。
    """
    ok = resolve_incident(incidents_dir, incident_id)
    case_md = os.path.join(
        _cases_dir(incidents_dir, cases_dir), f"CASE-{incident_id}", "case.md")
    wrote = False
    if os.path.isfile(case_md):
        try:
            with open(case_md, "a", encoding="utf-8") as f:
                f.write(
                    f"\n## 四、结案（{time.strftime('%Y-%m-%d %H:%M:%S')}）\n\n"
                    f"- **结论**: {resolution}\n"
                    f"- **根因**: {root_cause or '（未填写）'}\n"
                    f"- **修复**: {fix or '（未填写）'}\n"
                    f"- **状态**: RESOLVED → CASE_CLOSED\n")
            wrote = True
        except Exception:
            pass
    if ok:
        recorder.record("CASE_CLOSED", component="forensic",
                        session_id=incident_id,
                        payload_summary=f"root_cause={root_cause[:60]}")
    return ok and wrote
