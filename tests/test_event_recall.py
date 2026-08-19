# -*- coding: utf-8 -*-
"""V14.4（LLM 优先内容路线 P0）：事件记忆语义召回测试。

原实现：钉住 + 最近 3 条硬注入（README 遗留：聊 A 却注入 B 的往事）。
新实现：钉住保底 + 按「用户输入 × 事件关键词」重叠度动态召回。
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.prompts import PromptBuilder, _event_words, EVENT_TYPE_TOPICS


def _events():
    """构造一组事件：名字/鬼化/拉姆评价/替代品肯定。"""
    return [
        {"type": "name_first", "summary": "第3次对话：用户第一次告知名字「小东」",
         "excerpt": "我叫小东", "pinned": True},
        {"type": "oni", "summary": "第8次对话：蕾姆鬼化完全解放",
         "excerpt": "解放鬼角，我需要你的力量", "pinned": False},
        {"type": "ram_up", "summary": "第12次对话：拉姆评价进入「观察中」",
         "excerpt": "拉姆，你觉得我怎么样", "pinned": False},
        {"type": "affirm", "summary": "第15次对话：用户肯定蕾姆是独立的个体",
         "excerpt": "你不是任何人的替代品", "pinned": False},
    ]


def test_event_semantic_recall_v144() -> None:
    """问「鬼化」→ 应召回 oni 事件；问「拉姆」→ 应召回 ram_up 事件。"""
    evs = _events()

    # 用户聊鬼化：oni 事件必须被注入
    sec = PromptBuilder._build_events_section(evs, "还记得那次鬼化吗？")
    assert "鬼化完全解放" in sec, f"聊鬼化应召回 oni 事件: {sec}"

    # 用户聊拉姆：ram_up 事件必须被注入
    sec2 = PromptBuilder._build_events_section(evs, "拉姆最近对我态度好点了吗")
    assert "拉姆评价" in sec2, f"聊拉姆应召回 ram_up 事件: {sec2}"

    # 用户聊替代品：affirm 事件必须被注入
    sec3 = PromptBuilder._build_events_section(evs, "蕾姆，你还记得我说你不是替代品吗")
    assert "独立的个体" in sec3, f"聊替代品应召回 affirm 事件: {sec3}"


def test_event_recall_fallback_v144() -> None:
    """无关输入 → 回落最近事件（保底有上下文锚点）。"""
    evs = _events()
    sec = PromptBuilder._build_events_section(evs, "今天天气怎么样")
    # 钉住事件（名字）始终在
    assert "小东" in sec, f"钉住事件应始终注入: {sec}"


def test_event_words_v144() -> None:
    """分词辅助：去停用词、去标点、2-4 字词。"""
    words = _event_words("还记得那次鬼化吗")
    assert "鬼化" in words, f"应抽取「鬼化」: {words}"
    assert "的" not in words and "吗" not in words, f"停用词应剔除: {words}"
    assert "从零开始" in _event_words("从零开始吧"), "4字词应抽取"


def main() -> int:
    tests = [
        ("语义召回（鬼化/拉姆/替代品）", test_event_semantic_recall_v144),
        ("无关输入回落最近事件", test_event_recall_fallback_v144),
        ("分词辅助", test_event_words_v144),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            import traceback
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
