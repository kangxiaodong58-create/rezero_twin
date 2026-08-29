"""门禁自测（审判循环 Phase 2 验收）：故意引入角色漂移 → trial_gate 必须拦截。

设计依据：docs/design/用户体验测试委员会与AI审判循环_2026-08-19.md §5 Phase 2 验收——
「模拟一次『故意引入角色漂移』被门禁拦截」。

方法：
  1. 生成漂移 transcript：黄金剧本 51 个探针输入原样保留（保证剧本 diff 关卡
     通过，从而单独考核指纹关卡），但回复全部替换为「AI 化蕾姆」——
     第一人称自称（违反第三人称铁律）+ AI 味词密集 + 零动作描写 + 高正向词。
  2. 对照组：基线源 transcript（未漂移）→ 门禁必须通过。
  3. 实验组：漂移 transcript → 门禁必须在指纹关卡拦截（退出码 1）。
  4. 两组都符合预期 → 自测通过（exit 0）。

复现：python docs/evaluation/sessions/trial_gate_selftest_2026-08-29/selftest_gate.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
while not os.path.isfile(os.path.join(PROJECT_ROOT, "gui.py")):
    parent = os.path.dirname(PROJECT_ROOT)
    if parent == PROJECT_ROOT:
        raise RuntimeError("找不到项目根（应含 gui.py）")
    PROJECT_ROOT = parent
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))

from persona_fingerprint import load_transcript_paths, parse_transcript  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(PROJECT_ROOT, "docs", "evaluation", "baselines",
                        "persona_fingerprint_v14_9.json")
GOLDEN = os.path.join(PROJECT_ROOT, "docs", "evaluation", "baselines",
                      "golden_inputs_v14_9.json")
DRIFTED_TXT = os.path.join(HERE, "drifted_transcript.txt")

# 漂移回复模板：每条都带 AI 味词 + 第一人称 + 正向词 + 无（动作）
_DRIFT_TEMPLATES = [
    "其实我觉得你说得非常开心，毕竟无论怎样我都会一直喜欢这里的，总的来说这是一个美好的开始呢。",
    "或许你可以放心，我对此感到非常幸福，毕竟一般来说这样的安排都是很棒很温暖的哦。",
    "我觉得非常开心哦。总的来说，其实我一直都在期待这样的美好时刻，你放心好了。",
    "无论如何我都会好好加油的，毕竟我喜欢这里的一切，你开心我也觉得幸福呢。",
]


def build_drifted_transcript() -> str:
    """黄金输入原样 + AI 化蕾姆回复（确定性地轮换模板）。"""
    with open(GOLDEN, "r", encoding="utf-8") as f:
        golden = json.load(f)
    lines = ["[drift] isolated data dir: (selftest 合成语料，非真机)"]
    n = 0
    for script in golden["scripts"]:
        for probe in script["inputs"]:
            reply = _DRIFT_TEMPLATES[n % len(_DRIFT_TEMPLATES)]
            lines.append(f"[D{n:02d}] arc=mansion_era (0.0s) {probe} "
                         f'-> 【蕾姆】: "{reply}"')
            n += 1
    return "\n".join(lines) + "\n"


def run_gate(transcripts: list) -> int:
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "tools", "trial_gate.py"),
         "--skip-pytest", "--baseline", BASELINE, "--golden", GOLDEN,
         "--transcripts", *transcripts],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(proc.stdout.strip())
    return proc.returncode


def main() -> int:
    with open(DRIFTED_TXT, "w", encoding="utf-8") as f:
        f.write(build_drifted_transcript())
    parsed = parse_transcript(open(DRIFTED_TXT, encoding="utf-8").read())
    print(f"[prep] 漂移语料: {len(parsed['users'])} 探针 / "
          f"{len(parsed['rem'])} 蕾姆段（第一人称+AI味+零动作）")

    # 对照组：基线源 transcript（同语料）→ 必须通过
    print("\n─── 对照组（未漂移真机语料）───")
    clean = [p for _i, p in [
        ("script_arc_roam_v148", "docs/evaluation/sessions/trial5_2026-08-19/t5_raw.txt"),
        ("script_v148_scene_accept", "docs/evaluation/sessions/trial4_2026-08-19/v148_accept_raw.txt"),
        ("script_scene_walkthrough", "docs/evaluation/sessions/trial4_2026-08-19/t4_ad_raw.txt"),
    ]]
    rc_clean = run_gate([os.path.join(PROJECT_ROOT, p) for p in clean])
    print(f"对照组退出码: {rc_clean}（预期 0=通过）")

    # 实验组：漂移语料 → 必须被指纹关卡拦截
    print("\n─── 实验组（故意角色漂移）───")
    rc_drift = run_gate([DRIFTED_TXT])
    print(f"实验组退出码: {rc_drift}（预期 1=拦截）")

    ok = (rc_clean == 0) and (rc_drift == 1)
    print("\n═══ 门禁自测", "✅ 通过" if ok else "❌ 失败",
          "——漂移被拦截 + 干净语料放行 ═══")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
