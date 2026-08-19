"""V14.6：原著锚定测试（无框架，直接运行，零 API 费用）。

覆盖（V14.6-Character-Anchoring-01 文案包落地）：
- PromptBuilder 注入角色卡（蕾姆/拉姆核心 + 行为限制）
- 世界观词汇表注入（正确使用 + 使用限制）
- 注入结构（PERSONA → LORE 位于状态节之后）
- Validator E-5 软检查：A-E 级词命中 → 不阻断 + 返回警告
- 硬检查回归：FORBIDDEN_WORDS 仍拦截

用法：python tests/test_v14_6_anchor.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.prompts import PromptBuilder
from shared.state import StoryArc, TwinState
from shared.validators import ResponseValidator, ValidationResult


def _state(**kw) -> TwinState:
    defaults = dict(arc=StoryArc.MANSION_ERA, user_name="小东", favor=40,
                    ram_favor=20, independence=0.5, recovery=1.0,
                    context_summary="", events=[])
    defaults.update(kw)
    return TwinState(**defaults)


def test_persona_injected() -> None:
    """角色卡注入：蕾姆/拉姆核心设定与行为限制出现在 system prompt。"""
    prompt = PromptBuilder.build(_state())
    checks = [
        "蕾姆角色锚定", "拉姆角色锚定",
        "蕾姆不是任何人的替代品", "蕾姆就是蕾姆",
        "希望被认可为", "保护重要之人",
        "拉姆最大的情感核心是保护", "托付",
        "将用户称为", "不得表现为占有欲",
    ]
    for c in checks:
        assert c in prompt, f"prompt 缺少: {c}"
    # 行为限制原文
    assert "过度卖萌" in prompt and "病娇占有欲" in prompt


def test_lore_injected() -> None:
    """世界观词汇表注入：正确使用 + 使用限制。"""
    prompt = PromptBuilder.build(_state())
    for c in ("Re:0 世界观词汇规范", "巴鲁斯", "贝蒂", "圣域", "龙历石",
              "禁止展开圣域完整剧情", "禁止展开魔女因果"):
        assert c in prompt, f"prompt 缺少: {c}"
    # 名字动态（硬性状态节）
    assert "对用户称呼：小东" in prompt
    prompt2 = PromptBuilder.build(_state(user_name="客人大人"))
    assert "对用户称呼：客人大人" in prompt2


def test_injection_order() -> None:
    """注入结构：角色卡在世界状态节之前（CORE → PERSONA → LORE → SCENE）。"""
    from shared.state import WorldState
    prompt = PromptBuilder.build(_state(), world=WorldState(
        current_time="2026-08-19 14:00", period="午后", weather="晴朗"))
    assert prompt.index("蕾姆角色锚定") < prompt.index("当前世界状态"), \
        "角色卡应在世界状态节之前"
    assert prompt.index("Re:0 世界观词汇规范") < prompt.index("当前世界状态"), \
        "词汇表应在世界状态节之前"


def test_ooc_soft_check() -> None:
    """E-5 软检查：A-E 级词命中 → ok=True 不阻断 + ooc_warnings 返回。"""
    v = ResponseValidator()
    # A 级
    r = v.validate("【蕾姆】: \"今天的茶很好喝，yyds！\"")
    assert r.ok and r.ooc_warnings and "A级" in r.ooc_warnings[0], r
    # C 级
    r2 = v.validate("【蕾姆】: \"蕾姆永远属于你。\"")
    assert r2.ok and r2.ooc_warnings and "C级" in r2.ooc_warnings[0], r2
    # E 级
    r3 = v.validate("【拉姆】: \"用手机APP可不行。\"")
    assert r3.ok and r3.ooc_warnings and "E级" in r3.ooc_warnings[0], r3
    # D 级
    r4 = v.validate("【蕾姆】: \"路飞是谁？\"")
    assert r4.ok and r4.ooc_warnings and "D级" in r4.ooc_warnings[0], r4


def test_ooc_soft_clean_text() -> None:
    """软检查不误伤：正常台词无警告；多个命中全部收集。"""
    v = ResponseValidator()
    r = v.validate("【蕾姆】: \"蕾姆认为您说得对。\"")
    assert r.ok and r.ooc_warnings is None, r
    r2 = v.validate("【蕾姆】: \"哈哈哈，666，太秀了。\"")
    assert r2.ok and len(r2.ooc_warnings) == 3, r2.ooc_warnings


def test_hard_check_regression() -> None:
    """硬检查回归：FORBIDDEN_WORDS 仍拦截（软检查不改变既有行为）。"""
    v = ResponseValidator()
    r = v.validate("【蕾姆】: \"用户您好，欢迎使用。\"")
    assert not r.ok and "OOC" in (r.reason or ""), r
    # 软检查字段在失败结果中保持 None
    assert r.ooc_warnings is None


def main() -> int:
    tests = [
        ("角色卡注入", test_persona_injected),
        ("世界观词汇注入 + 名字动态", test_lore_injected),
        ("注入结构顺序", test_injection_order),
        ("E-5 软检查（不阻断+警告）", test_ooc_soft_check),
        ("软检查不误伤/多命中收集", test_ooc_soft_clean_text),
        ("硬检查回归", test_hard_check_regression),
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
