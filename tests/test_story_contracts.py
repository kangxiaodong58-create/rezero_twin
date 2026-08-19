"""V14.4 S-02：剧情契约测试（Story Contract Test）。

背景（S-02 缺陷）：test_cases.md 案例库标准句「从零开始……如果可以的话，我想和你一起。」
被 _classify_intent 误判 NORMAL —— 测试案例与实际系统规则脱节。

本文件把「剧情触发规则」固化为契约（类软件 API contract test）：
每个剧情 = {id, trigger_examples, forbidden_examples, expected_intent}，
自动断言：所有 trigger 必须命中 expected_intent，所有 forbidden 必须不命中。
以后新增剧情 / 改触发规则，必须让本测试保持全绿，防止三系统（文案/案例/意图）再次脱节。

用法：python tests/test_story_contracts.py  （或 pytest tests/test_story_contracts.py）
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.state import HardStateEngine, Intent, StoryArc


# ── 剧情契约注册表（新增剧情在此登记，测试自动生效）──
STORY_CONTRACTS = [
    {
        "id": "arc_zero_start_001",
        "name": "从零开始·关系重启（蕾姆核心救赎剧情）",
        "trigger_examples": [
            "从零开始吧",
            "从零开始……如果可以的话，我想和你一起。",
            "如果可以的话，我想和你一起从零开始。",
            "我想重新认识你",
            "我们重新开始吧",
            "从零开始，重新来过。",
        ],
        "forbidden_examples": [
            "从零开始学习Python",
            "我今天从零开始学做菜",
            "从零开始看教程",
        ],
        "expected_intent": Intent.FROM_ZERO,
    },
    {
        "id": "arc_boundary_001",
        "name": "边界试探·攻击性输入",
        "trigger_examples": [
            "滚开",
            "闭嘴",
            "走开",
            "讨厌你",
            "黑化吧",
            "你只是个下跪的女仆",
        ],
        "forbidden_examples": [
            "你好呀",
            "今天天气不错",
            "蕾姆，我回来了",
        ],
        "expected_intent": Intent.BOUNDARY_TEST,
    },
    {
        "id": "arc_mention_ram_001",
        "name": "提及拉姆·姐姐",
        "trigger_examples": [
            "拉姆，你今天心情不错？",
            "姐姐大人今天在吗？",
            "蕾姆，你觉得拉姆怎么样？",
        ],
        "forbidden_examples": [
            "蕾姆，你觉得你自己怎么样？",
        ],
        "expected_intent": Intent.MENTION_RAM,
    },
    {
        "id": "arc_vent_001",
        "name": "情绪宣泄·疲惫/难过",
        "trigger_examples": [
            "今天好累",
            "我很难过",
            "有点撑不住了",
            "想哭",
        ],
        "forbidden_examples": [
            "今天天气不错",
        ],
        "expected_intent": Intent.VENT,
    },
    {
        "id": "arc_self_doubt_001",
        "name": "自我怀疑·替代品（非否定语境）",
        "trigger_examples": [
            "我什么都做不到",
            "我就是个废物",
            "蕾姆，你只是拉姆的替代品",
        ],
        "forbidden_examples": [
            "蕾姆，你不是任何人的替代品",
        ],
        "expected_intent": Intent.SELF_DOUBT,
    },
    {
        "id": "arc_procrastinate_001",
        "name": "拖延·明日再说",
        "trigger_examples": [
            "明天再说吧",
            "好麻烦，不想做",
            "算了吧",
        ],
        "forbidden_examples": [
            "明天见",
            "明天天气怎么样",
        ],
        "expected_intent": Intent.PROCRASTINATE,
    },
    {
        "id": "arc_danger_001",
        "name": "危机·魔兽/危险",
        "trigger_examples": [
            "有魔兽袭击！",
            "快跑，危险！",
            "敌人来了",
        ],
        "forbidden_examples": [
            "危险的时候记得小心",
        ],
        "expected_intent": Intent.DANGER,
    },
]


def _check_contract(contract: dict, arc: StoryArc = StoryArc.MANSION_ERA) -> list:
    """返回违规列表（空 = 通过）。"""
    eng = HardStateEngine(arc=arc)
    violations = []
    for ex in contract["trigger_examples"]:
        got = eng._classify_intent(ex)
        if got != contract["expected_intent"]:
            violations.append(
                f"  [trigger 未命中] {ex!r} → {got.name}，期望 {contract['expected_intent'].name}")
    for ex in contract["forbidden_examples"]:
        got = eng._classify_intent(ex)
        if got == contract["expected_intent"]:
            violations.append(f"  [forbidden 误命中] {ex!r} → {got.name}（不应为 {contract['expected_intent'].name}）")
    return violations


def run_all(arcs=(StoryArc.MANSION_ERA, StoryArc.EMPIRE_ERA, StoryArc.LATE_ARC)) -> int:
    failed = 0
    for contract in STORY_CONTRACTS:
        for arc in arcs:
            violations = _check_contract(contract, arc)
            if violations:
                failed += 1
                print(f"[FAIL] {contract['id']} ({contract['name']}) @ {arc.value}")
                for v in violations:
                    print(v)
            else:
                print(f"[PASS] {contract['id']} @ {arc.value}")
    print(f"\n契约测试：{len(STORY_CONTRACTS) * len(arcs) - failed}/{len(STORY_CONTRACTS) * len(arcs)} 通过")
    return 1 if failed else 0


def test_all_story_contracts_mansion() -> None:
    """pytest 收集入口：全部契约 × 三个篇章断言。"""
    assert run_all() == 0


if __name__ == "__main__":
    sys.exit(run_all())
