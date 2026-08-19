"""案件交接层（Forensic Kernel M2）：Handoff Protocol 实现。

对应 FORENSIC_DEBUGGING_PROTOCOL v1.2 §2：
- scan_incidents：检测未处理案件（cron 巡检 / 启动扫描共用）
- claim_incident：认领（防双 Agent 争抢，claim token = claimant + 时间）
- resolve_incident / mark_ignored：结案 / 忽略

状态机：PENDING → CLAIMED → INVESTIGATING → RESOLVED / IGNORED
dump.json 的 status 字段是唯一状态真相（崩溃时写入 PENDING）。
本模块只做文件读写，纯 Python，禁止 import PySide6。
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

ACTIVE_STATUSES = ("PENDING", "CLAIMED", "INVESTIGATING")


def _dump_path(incidents_dir: str, incident_id: str) -> Optional[str]:
    """案件 dump.json 路径；目录不存在/非案件目录返回 None。

    兼容 rename 失败降级：dump 可能留在 pending/（校验 incident_id 匹配）。
    """
    if not incident_id.startswith("INC-"):
        return None
    path = os.path.join(incidents_dir, incident_id, "dump.json")
    if os.path.isfile(path):
        return path
    pending = os.path.join(incidents_dir, "pending", "dump.json")
    if os.path.isfile(pending):
        try:
            with open(pending, "r", encoding="utf-8") as f:
                if json.load(f).get("incident_id") == incident_id:
                    return pending
        except Exception:
            pass
    return None


def _read_dump(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_dump(path: str, payload: Dict[str, Any]) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        return True
    except Exception:
        return False


def list_incidents(incidents_dir: str) -> List[Dict[str, Any]]:
    """列出 incidents 目录下所有案件摘要（按 crash 时间倒序）。"""
    out: List[Dict[str, Any]] = []
    try:
        names = [n for n in os.listdir(incidents_dir) if n.startswith("INC-")]
        # rename 失败降级：pending/ 里的 dump 也是证据，纳入扫描
        if os.path.isdir(os.path.join(incidents_dir, "pending")):
            names.append("pending")
    except Exception:
        return out
    for name in names:
        path = _dump_path(incidents_dir, name)
        if not path:
            continue
        payload = _read_dump(path)
        if not payload:
            continue
        crash = payload.get("crash", {})
        out.append({
            "incident_id": payload.get("incident_id", name),
            "status": payload.get("status", "UNKNOWN"),
            "type": crash.get("type", "?"),
            "value": (crash.get("value") or "")[:120],
            "thread": crash.get("thread", "?"),
            "at_wall": crash.get("at_wall"),
            "events": len(payload.get("events", [])),
            "claimed_by": payload.get("claimed_by"),
            "claim_time": payload.get("claim_time"),
        })
    out.sort(key=lambda d: d["at_wall"] or 0, reverse=True)
    return out


def scan_incidents(incidents_dir: str) -> List[Dict[str, Any]]:
    """返回所有未处理案件（status ∈ PENDING/CLAIMED/INVESTIGATING）。"""
    return [d for d in list_incidents(incidents_dir) if d["status"] in ACTIVE_STATUSES]


def set_incident_status(
    incidents_dir: str,
    incident_id: str,
    status: str,
    *,
    claimant: Optional[str] = None,
) -> bool:
    """更新案件状态（写回 dump.json）。claim 时写入 claim token。"""
    path = _dump_path(incidents_dir, incident_id)
    if not path:
        return False
    payload = _read_dump(path)
    if not payload:
        return False
    payload["status"] = status
    if status == "CLAIMED" and claimant:
        payload["claimed_by"] = claimant
        payload["claim_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    return _write_dump(path, payload)


def claim_incident(incidents_dir: str, incident_id: str, claimant: str) -> bool:
    """认领案件。已是 CLAIMED/INVESTIGATING 的重复认领返回 False（防双 Agent）。"""
    path = _dump_path(incidents_dir, incident_id)
    if not path:
        return False
    payload = _read_dump(path)
    if not payload:
        return False
    if payload.get("status") in ("CLAIMED", "INVESTIGATING"):
        return False
    return set_incident_status(incidents_dir, incident_id, "CLAIMED", claimant=claimant)


def resolve_incident(incidents_dir: str, incident_id: str) -> bool:
    return set_incident_status(incidents_dir, incident_id, "RESOLVED")


def mark_ignored(incidents_dir: str, incident_id: str) -> bool:
    return set_incident_status(incidents_dir, incident_id, "IGNORED")
