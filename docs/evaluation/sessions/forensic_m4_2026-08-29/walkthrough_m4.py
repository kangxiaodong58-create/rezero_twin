"""M4 验收走查：首个真实案件 CASE_OPEN → CASE_CLOSED（2026-08-29）。

复现方式（项目根运行）：
    python docs/evaluation/sessions/forensic_m4_2026-08-29/walkthrough_m4.py

流程（FORENSIC_DEBUGGING_PROTOCOL v1.2 §2，设计 §8 M4 验收）：
  1. headless 压测注入超时（DelayProfile.timeout_rate=0.3）→ 真实崩溃
     → threading.excepthook 自动取证 → INC 落盘 incidents/
  2. scan_incidents 发现 PENDING 案件
  3. open_case → .debug/CASE-<id>/case.md 生成 + 状态 INVESTIGATING
  4. 读 dump.json 时间线（seq 排序）→ 形成结论（含 STATE_TRANSITION 状态轨迹验证）
  5. close_case → RESOLVED + case.md 结案节 + CASE_CLOSED 事件
"""

from __future__ import annotations

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from runtime.forensic import init_forensic, shutdown_forensic          # noqa: E402
from runtime.forensic.case import close_case, open_case                # noqa: E402
from runtime.forensic.manifest import scan_incidents                   # noqa: E402
from runtime.forensic.headless_runner import DelayProfile, run_campaign  # noqa: E402

INC = os.path.join(PROJECT_ROOT, "incidents")


def main() -> int:
    # 1. 崩溃注入压测——真实异常路径产生 INC（非伪造 dump）
    result = run_campaign(n_cases=24, seed=7,
                          profile=DelayProfile(timeout_rate=0.3),
                          incidents_dir=INC)
    print(f"[1] 压测: {result.crashes}/{result.n_cases} 崩溃"
          f"（率 {result.crash_rate:.0%}），INC 落盘 {len(result.incidents)} 个")
    assert result.crashes > 0 and result.incidents, "未产生真实 INC"

    # 2. 扫描未处理案件
    init_forensic(INC)  # 重启取证：案件编排事件（CASE_OPEN/CLOSED）入黑匣子
    pending = scan_incidents(INC)
    print(f"[2] 扫描: {len(pending)} 个 PENDING/ACTIVE 案件")
    assert pending, "scan 未发现待处理案件"
    inc_id = pending[0]["incident_id"]

    # 3. 开案（认领 + 案件目录 + INVESTIGATING）
    case_md = open_case(INC, inc_id, claimant="hermes-m4-walkthrough")
    print(f"[3] 开案: {inc_id} → {case_md}")
    assert case_md, "open_case 失败"
    assert os.path.isfile(case_md), "case.md 未生成"

    # 4. 读现场：时间线摘要 + 状态轨迹（state_trace 端到端验证）
    with open(os.path.join(INC, inc_id, "dump.json"), "r", encoding="utf-8") as f:
        dump = json.load(f)
    events = dump.get("events", [])
    transitions = [e for e in events if e.get("event") == "STATE_TRANSITION"]
    print(f"[4] 现场: {inc_id} 共 {len(events)} 事件"
          f"（startup_id={dump.get('startup_id', '?')}），"
          f"STATE_TRANSITION {len(transitions)} 条")
    for e in transitions[:6]:
        print(f"     seq={e['seq']} {e.get('component')} "
              f"{e.get('state_before')} → {e.get('state_after')}")
    assert events, "dump 事件为空"

    # 5. 结案
    ok = close_case(
        INC, inc_id,
        resolution="mock 注入超时的预期崩溃——headless 复现通道演练产物，非产品缺陷（M4 验收首案）",
        root_cause="DelayProfile.timeout_rate=0.3 注入 → MockStream 中途 TimeoutError → worker 异常逃逸",
        fix="无需修复（演练案件，验收取证链路本身）")
    print(f"[5] 结案: {'OK' if ok else 'FAIL'}（case.md 已追加结案节，状态 RESOLVED）")
    assert ok, "close_case 失败"
    # 首案已退出 ACTIVE 扫描（其余演练案件保持 PENDING 属预期）
    assert all(d["incident_id"] != inc_id for d in scan_incidents(INC)), \
        "首案结案后不应再出现在 ACTIVE 扫描"

    print("\n═══ M4 验收 ✅ CASE_OPEN → CASE_CLOSED 全流程走通 ═══")
    print(f"首案编号: {inc_id}")
    shutdown_forensic()
    return 0


if __name__ == "__main__":
    sys.exit(main())
