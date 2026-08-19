# -*- coding: utf-8 -*-
"""V14.8：场景互动池 arc 维度测试（文案组交付 Part1/Part2 落地验证）。"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.scene_manager import SceneManager


def test_arc_scene_opening_v148() -> None:
    """帝国/后期场景 opening 按 arc 读取。"""
    op = SceneManager.get_scene_opening("CAMP", "夜晚", arc="empire_era")
    assert op and "营火" in op["rem_view"], f"帝国 CAMP 夜 opening 缺失: {op}"
    op2 = SceneManager.get_scene_opening("BARRACKS", "清晨", arc="late_arc")
    assert op2 and "军营" in op2["rem_view"], f"后期 BARRACKS 晨 opening 缺失: {op2}"
    op3 = SceneManager.get_scene_opening("WILDERNESS", "上午", arc="empire_era")
    assert op3 and "荒野" in op3["rem_view"], f"帝国 WILDERNESS opening 缺失: {op3}"


def test_arc_scene_interaction_v148() -> None:
    """帝国/后期 interaction 按 arc 读取（语感区分：疏离 vs 战友）。"""
    i1 = SceneManager.get_scene_interaction("CAMP", "上午", arc="empire_era")
    assert i1 and i1["rem_view"], f"帝国语感应疏离试探: {i1}"
    # 帝国语感红线：不含宅邸元素（红茶/花园/女仆），含试探/确认语义
    assert "蕾姆" in i1["rem_view"] and "宅邸" not in i1["rem_view"], f"帝国语感不应含宅邸元素: {i1}"
    i2 = SceneManager.get_scene_interaction("BATTLEFIELD", "上午", arc="late_arc")
    assert i2 and "您" in i2["rem_view"], f"后期语感应并肩: {i2}"


def test_arc_fallback_mansion_v148() -> None:
    """未知 arc → 回落 mansion_era（防内容缺失崩溃）。"""
    op = SceneManager.get_scene_opening("KITCHEN", "上午", arc="unknown_arc")
    assert op and "早餐" in op["rem_view"], f"未知 arc 应回落 mansion: {op}"
    # 无 arc（旧调用）→ mansion
    op2 = SceneManager.get_scene_opening("KITCHEN", "上午")
    assert op2, "旧调用（无 arc）应仍工作"


def test_new_scene_keywords_v148() -> None:
    """帝国/后期场景切换关键词。"""
    assert SceneManager.parse_scene_change("去营地") == "CAMP"
    assert SceneManager.parse_scene_change("到旅店投宿") == "INN"
    assert SceneManager.parse_scene_change("去荒野") == "WILDERNESS"
    assert SceneManager.parse_scene_change("去营火边") == "CAMPFIRE"
    assert SceneManager.parse_scene_change("进军营") == "BARRACKS"
    assert SceneManager.parse_scene_change("去战场") == "BATTLEFIELD"
    # 闲聊不误触
    assert SceneManager.parse_scene_change("营地的故事很有意思") is None


def test_scene_dialogue_arc_structure_v148() -> None:
    """scene_dialogue.json 顶层 arc 分桶 + 6 新场景齐全。"""
    import json
    with open(os.path.join(PROJECT_ROOT, "content", "scene_dialogue.json"), encoding="utf-8") as f:
        d = json.load(f)
    assert d["schema_version"] == "2.0", f"应升 2.0: {d.get('schema_version')}"
    assert set(d.keys()) >= {"mansion_era", "empire_era", "late_arc"}
    assert set(d["empire_era"].keys()) == {"CAMP", "INN", "WILDERNESS"}
    assert set(d["late_arc"].keys()) == {"CAMPFIRE", "BARRACKS", "BATTLEFIELD"}
    # 全部场景具备 opening
    for arc in ("empire_era", "late_arc"):
        for scene, slots in d[arc].items():
            for slot, content in slots.items():
                assert content.get("opening"), f"{arc}/{scene}/{slot} 缺 opening"


def main() -> int:
    tests = [
        ("arc 场景 opening", test_arc_scene_opening_v148),
        ("arc 场景 interaction（语感区分）", test_arc_scene_interaction_v148),
        ("未知 arc 回落 mansion", test_arc_fallback_mansion_v148),
        ("新场景切换关键词", test_new_scene_keywords_v148),
        ("scene_dialogue arc 结构", test_scene_dialogue_arc_structure_v148),
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
