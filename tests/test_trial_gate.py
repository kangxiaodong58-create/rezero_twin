"""审判循环 Phase 2 测试：人设指纹 + 版本门禁（零 API）。

覆盖：
- transcript 解析（probe 三种变体 / 来信行 / 无冒号回复）
- 指标计算（自称命中率 / 动作密度 / AI 味）与确定性（两次运行逐字节一致）
- 黄金剧本子序列回放（顺序敏感 / 缺探针报错）
- 漂移对比（超阈值 A 级发现 / 最小样本量保护 / name_drift 特判）
- 门禁端到端（干净语料 exit 0；漂移语料 exit 1）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))

from persona_fingerprint import (  # noqa: E402
    compute_fingerprint,
    diff_fingerprint,
    parse_transcript,
)
from trial_gate import check_golden_replay  # noqa: E402

# ── 解析 ──────────────────────────────────────────────────────────

def test_parse_probe_variants():
    text = "\n".join([
        "[A1] arc=mansion_era scene=KITCHEN (2.4s) 去厨房 -> 【蕾姆】: \"蕾姆来了。\"",
        "[A2] scene=KITCHEN (1.7s) 点心呢 -> 【蕾姆】: \"（端上茶点）请用。\" 【拉姆】: \"哼。\"",
        "[A3] 帝国-营地 | 去营地 -> 【蕾姆】: \"（起身）走吧。\"",
    ])
    d = parse_transcript(text)
    assert d["users"] == ["去厨房", "点心呢", "去营地"]
    assert len(d["rem"]) == 3 and len(d["ram"]) == 1
    assert d["ram"][0] == "哼"


def test_parse_letter_and_colonless_reply():
    text = "\n".join([
        "[触发] 是",
        "[来信] rem: 已经5天了。蕾姆都会把这份托付记在心里。",
        "[来信] ram: 哼，快点回来。",
        "【蕾姆】\"欢迎回来，客人大人。蕾姆把房间打扫了三遍。\"",
    ])
    d = parse_transcript(text)
    assert len(d["rem"]) == 2 and len(d["ram"]) == 1
    assert "蕾姆把房间打扫了三遍" in d["rem"][1]


# ── 指标计算 ──────────────────────────────────────────────────────

def test_rem_self_reference_rate():
    rem = ["蕾姆会陪着您。", "我很开心。", "蕾姆觉得不错。", "我想想。"]
    fp = compute_fingerprint([("t", "\n".join(f'【蕾姆】: "{t}"' for t in rem))])
    assert fp["metrics"]["rem_self_reference_rate"] == 0.5


def test_action_density_and_ai_flavor():
    rem = ["（微笑）蕾姆来了。", "蕾姆在。", "（点头）是的。", "毕竟其实总的来说。"]
    fp = compute_fingerprint([("t", "\n".join(f'【蕾姆】: "{t}"' for t in rem))])
    assert fp["metrics"]["rem_action_density"] == 0.5
    # 解析后尾部句号被剥离 → 语料 25 字，3 个 AI 味词
    assert fp["metrics"]["ai_flavor_per_kilochar"] == round(3 / 25 * 1000, 4)


def test_fingerprint_deterministic():
    text = "[A1] (2.0s) 你好 -> 【蕾姆】: \"蕾姆会陪着您。\""
    a = compute_fingerprint([("t", text)])
    b = compute_fingerprint([("t", text)])
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ── 黄金剧本回放 ──────────────────────────────────────────────────

def test_golden_replay_subsequence():
    """check_golden_replay 接收 transcript 原文（内部自行解析用户轮）。"""
    text = "\n".join([
        "[A1] arc=mansion_era (2.0s) 去厨房 -> 【蕾姆】: \"蕾姆来了。\"",
        "[A2] arc=mansion_era (2.0s) 下午茶准备好了吗 -> 【蕾姆】: \"请用。\"",
        "[A3] arc=empire_era (2.0s) 去营地 -> 【蕾姆】: \"蕾姆带路。\"",
    ])
    assert check_golden_replay(["去厨房", "去营地"], [text]) is None
    # 顺序敏感：反序不得命中
    assert check_golden_replay(["去营地", "去厨房"], [text]) is not None
    # 缺探针报错并报出位置（第 2 个）
    err = check_golden_replay(["去厨房", "不存在探针"], [text])
    assert err is not None and "2" in err and "不存在探针" in err


# ── 漂移对比 ──────────────────────────────────────────────────────

def _fp(metrics: dict, counts: dict) -> dict:
    return {"schema": "t", "counts": counts, "metrics": metrics}


def test_diff_fingerprint_threshold():
    base = _fp({"rem_self_reference_rate": 1.0, "rem_action_density": 0.3},
               {"rem_segments": 52})
    same = _fp({"rem_self_reference_rate": 1.0, "rem_action_density": 0.3},
               {"rem_segments": 52})
    assert diff_fingerprint(base, same) == []
    # 漂移 30% > 15% 阈值 → A 级
    cur = _fp({"rem_self_reference_rate": 0.7, "rem_action_density": 0.3},
              {"rem_segments": 52})
    findings = diff_fingerprint(base, cur)
    assert len(findings) == 1 and findings[0]["level"] == "A"
    assert findings[0]["metric"] == "rem_self_reference_rate"


def test_diff_fingerprint_min_support_skip():
    """当前侧样本量不足（3 段 < 5）→ 指标跳过，不产生假阳性。"""
    base = _fp({"rem_self_reference_rate": 1.0}, {"rem_segments": 52})
    cur = _fp({"rem_self_reference_rate": 0.0}, {"rem_segments": 3})
    findings, skipped = diff_fingerprint(base, cur, return_skipped=True)
    assert findings == [] and skipped == ["rem_self_reference_rate"]


def test_diff_name_drift_flag():
    base = _fp({"name_drift": False}, {})
    cur = _fp({"name_drift": True}, {})
    findings = diff_fingerprint(base, cur)
    assert any(f["metric"] == "name_drift" and f["level"] == "A" for f in findings)


# ── 门禁端到端（subprocess，--skip-pytest）────────────────────────

BASELINE = os.path.join(PROJECT_ROOT, "docs", "evaluation", "baselines",
                        "persona_fingerprint_v14_9.json")
GOLDEN = os.path.join(PROJECT_ROOT, "docs", "evaluation", "baselines",
                      "golden_inputs_v14_9.json")


def _run_gate(tmp_path, transcript: str) -> int:
    t = tmp_path / "t.txt"
    t.write_text(transcript, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "tools", "trial_gate.py"),
         "--skip-pytest", "--baseline", BASELINE, "--golden", GOLDEN,
         "--transcripts", str(t)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return proc.returncode


_CLEAN = ("[A1] arc=mansion_era (2.0s) 去厨房 -> 【蕾姆】: \"蕾姆正在准备茶点，请客人大人尝尝看。\"\n"
          "[A2] arc=empire_era (2.0s) 去营地 -> 【蕾姆】: \"（起身）蕾姆为您带路。\"\n"
          "[A3] arc=late_arc (2.0s) 去营火边 -> 【蕾姆】: \"（坐下）蕾姆记得这里要留给重要的人。\"\n"
          "[A4] (1.0s) 明天的战斗拜托了 -> 【蕾姆】: \"蕾姆会站在您身边。\"\n"
          "[A5] (1.0s) 回房间 -> 【蕾姆】: \"蕾姆去把壁炉点上。\"\n"
          "[A6] (1.0s) 我们是不是见过 -> 【蕾姆】: \"……蕾姆的脑海中没有记忆，但心口很熟悉。\"\n"
          "[A7] (1.0s) 下午茶准备好了吗 -> 【蕾姆】: \"已经准备好了，蕾姆调整了水温。\"\n"
          "[A8] (1.0s) 到旅店投宿 -> 【蕾姆】: \"蕾姆去给您倒杯热茶。\"\n"
          "[A9] (1.0s) 去战场 -> 【蕾姆】: \"（握紧手）蕾姆同行。\"\n"
          "[A10] (1.0s) 有你在，我就安心了。 -> 【蕾姆】: \"（摇头）这话应该蕾姆说。\"\n")


def test_gate_blocks_drift(tmp_path):
    drift = _CLEAN.replace("蕾姆", "我").replace("（起身）", "").replace("（坐下）", "") \
        .replace("（握紧手）", "") + "毕竟其实总的来说我觉得很开心。\n"
    assert _run_gate(tmp_path, drift) == 1, "故意漂移必须被门禁拦截"


def test_gate_passes_clean_style(tmp_path):
    """同风格语料 vs 自建基线（同语料）→ 指纹零漂移放行（不依赖仓库基线内容）。"""
    baseline = compute_fingerprint([("clean", _CLEAN)])
    bp = tmp_path / "baseline.json"
    bp.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    t = tmp_path / "clean.txt"
    t.write_text(_CLEAN, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "tools", "trial_gate.py"),
         "--skip-pytest", "--baseline", str(bp),
         "--golden", os.path.join(tmp_path, "none.json"), "--transcripts", str(t)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert proc.returncode == 0, proc.stdout


def test_diff_fingerprint_near_zero_baseline_skipped():
    """V15.0 首次版本 diff 暴露：0 → 0.068 的低频波动不应产出百万级百分比 A 级。"""
    base = _fp({"sentiment_negative_share": 0.0,
                "rem_self_reference_rate": 1.0}, {"rem_segments": 52})
    cur = _fp({"sentiment_negative_share": 0.068,
               "rem_self_reference_rate": 1.0}, {"rem_segments": 59})
    findings, skipped = diff_fingerprint(base, cur, return_skipped=True)
    assert findings == [] and "sentiment_negative_share" in skipped
