"""版本门禁（Trial Gate）——审判循环 Phase 2 的回归机制化。

对应 docs/design/用户体验测试委员会与AI审判循环_2026-08-19.md §5 Phase 2：
    pytest 全绿 + 剧本 diff + 指纹漂移阈值 → 输出「通过 / 拦截」

三道关卡：
  1. L0 回归    —— pytest tests/ 全绿（--skip-pytest 可跳过，如已在外层跑过）
  2. 剧本 diff  —— 黄金剧本输入序列必须按序出现在 transcript 的用户轮中
                   （任何问题报告引用「剧本ID+第N轮」的前提：剧本确实被跑了）
  3. 指纹漂移   —— persona_fingerprint 8 项指标 vs 基线，相对漂移 >15%
                   → A 级发现 → 拦截（设计 §4.1：漂移自动标记为 A 级问题）

用法（发布前门禁）：
    python tools/trial_gate.py --transcripts <transcript.txt...> \
        [--baseline docs/evaluation/baselines/persona_fingerprint_v14_9.json] \
        [--golden docs/evaluation/baselines/golden_inputs_v14_9.json] \
        [--threshold 0.15] [--skip-pytest]

退出码：0 = 通过；1 = 拦截（附原因清单）；2 = 运行错误（缺文件等）。
纯 Python，零 API；不 import PySide6。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from persona_fingerprint import (  # noqa: E402
    compute_fingerprint,
    diff_fingerprint,
    load_transcript_paths,
    parse_transcript,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_BASELINE = os.path.join(
    PROJECT_ROOT, "docs", "evaluation", "baselines",
    "persona_fingerprint_v14_9.json")
DEFAULT_GOLDEN = os.path.join(
    PROJECT_ROOT, "docs", "evaluation", "baselines",
    "golden_inputs_v14_9.json")


def check_pytest() -> Optional[str]:
    """跑 L0 全量；返回 None=通过，str=失败摘要。"""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no",
         "-p", "no:cacheprovider"],
        cwd=PROJECT_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(无输出)"]
    if proc.returncode != 0:
        return f"pytest 退出码 {proc.returncode}: {tail[0]}"
    return None


def check_golden_replay(golden_inputs: List[str], transcripts: List[str]) -> Optional[str]:
    """黄金剧本输入须按序出现于 transcript 用户轮（子序列匹配）。

    返回 None=通过，str=第一个未命中的探针描述。
    """
    users: List[str] = []
    for t in transcripts:
        users.extend(parse_transcript(t)["users"])
    idx = 0
    for probe in golden_inputs:
        found = False
        while idx < len(users):
            if probe in users[idx]:
                found = True
                break  # 停在本轮：下一探针允许同轮后文/后续轮命中
            idx += 1
        if not found:
            return f"黄金探针未命中（第 {golden_inputs.index(probe) + 1} 个）：「{probe}」"
        # 子序列：下一探针从当前轮继续（同轮多探针兼容）
    return None


def check_golden(golden, transcripts: List[str]) -> Optional[str]:
    """支持两种剧本文件形态：扁平输入数组，或 {scripts: [{id, inputs}]}。

    多剧本时每个剧本独立做子序列核对（同一份 transcript 集可含多轮剧本）。
    """
    if isinstance(golden, dict) and "scripts" in golden:
        for script in golden["scripts"]:
            err = check_golden_replay(script["inputs"], transcripts)
            if err:
                return f"剧本[{script.get('id', '?')}] {err}"
        return None
    inputs = golden["inputs"] if isinstance(golden, dict) else golden
    return check_golden_replay(inputs, transcripts)


def run_gate(transcript_paths: List[str],
             baseline_path: Optional[str],
             golden_path: Optional[str],
             threshold: float,
             skip_pytest: bool) -> int:
    failures: List[str] = []
    a_findings: List[Dict] = []

    # 关卡 1：pytest
    if skip_pytest:
        print("[gate-1] pytest: 跳过（--skip-pytest）")
    else:
        err = check_pytest()
        print(f"[gate-1] pytest: {'❌ ' + err if err else '✅ 全绿'}")
        if err:
            failures.append(f"L0 回归失败：{err}")

    transcripts = load_transcript_paths(transcript_paths)

    # 关卡 2：黄金剧本回放
    if golden_path and os.path.isfile(golden_path):
        with open(golden_path, "r", encoding="utf-8") as f:
            golden = json.load(f)
        if isinstance(golden, dict) and "scripts" in golden:
            n_probes = sum(len(s["inputs"]) for s in golden["scripts"])
            n_scripts = len(golden["scripts"])
        else:
            n_probes = len(golden["inputs"] if isinstance(golden, dict) else golden)
            n_scripts = 1
        err = check_golden(golden, [t for _p, t in transcripts])
        print(f"[gate-2] 剧本 diff（{n_scripts} 套/{n_probes} 探针）: "
              f"{'❌ ' + err if err else '✅ 全部按序命中'}")
        if err:
            failures.append(f"剧本 diff 失败：{err}")
    else:
        print("[gate-2] 剧本 diff: 跳过（未提供 --golden）")

    # 关卡 3：指纹漂移
    if baseline_path and os.path.isfile(baseline_path):
        with open(baseline_path, "r", encoding="utf-8") as f:
            baseline = json.load(f)
        current = compute_fingerprint(transcripts)
        result = diff_fingerprint(baseline, current, threshold, return_skipped=True)
        a_findings, skipped = result if isinstance(result, tuple) else (result, [])
        if skipped:
            print(f"    （样本量不足跳过 {len(skipped)} 项: {', '.join(skipped)}）")
        if a_findings:
            print(f"[gate-3] 指纹漂移（阈值 {threshold:.0%}）: "
                  f"❌ {len(a_findings)} 项 A 级漂移")
            for fd in a_findings:
                print(f"    - {fd['metric']}: 基线 {fd['baseline']} → "
                      f"当前 {fd['current']}（漂移 {fd['drift']:.0%}）")
            failures.append(
                f"人设指纹漂移 {len(a_findings)} 项超阈值（A 级，进台账）")
        else:
            print(f"[gate-3] 指纹漂移（阈值 {threshold:.0%}）: ✅ 无 A 级漂移")
        # 摘要（供人工复核）
        print("    指纹摘要: rem自指率={rem_self_reference_rate} "
              "动作密度={rem_action_density} AI味/千字={ai_flavor_per_kilochar} "
              "毒舌率={ram_snark_rate}".format(**current["metrics"]))
    else:
        print("[gate-3] 指纹漂移: 跳过（未提供 --baseline）")

    # 裁决
    print("─" * 56)
    if failures:
        print(f"⛔ 门禁拦截（{len(failures)} 项）")
        for f in failures:
            print(f"    · {f}")
        return 1
    print("✅ 门禁通过")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="版本门禁（审判循环 Phase 2）")
    parser.add_argument("--transcripts", nargs="+", required=True,
                        help="本轮审判 transcript 文件（>=1）")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                        help="指纹基线 JSON（缺省=V14.9 基线）")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN,
                        help="黄金剧本输入序列 JSON")
    parser.add_argument("--threshold", type=float, default=0.15,
                        help="漂移阈值（默认 0.15，设计 §4.1）")
    parser.add_argument("--skip-pytest", action="store_true",
                        help="跳过关卡 1（外层已跑过 pytest 时）")
    args = parser.parse_args(argv)

    missing = [p for p in args.transcripts if not os.path.isfile(p)]
    if missing:
        print(f"运行错误：transcript 不存在: {missing}")
        return 2
    return run_gate(args.transcripts, args.baseline, args.golden,
                    args.threshold, args.skip_pytest)


if __name__ == "__main__":
    sys.exit(main())
