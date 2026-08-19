"""V14.7：宅邸场景系统测试（无框架，直接运行，零 API 费用）。

覆盖（V14.7-A1/E3/E4 资产落地）：
- 场景切换识别（移动动词前缀；闲聊提及不误触）
- 场景开场/互动选择（场景 × 时段 slot）
- E4 名场面状态联动（鬼化/失忆/忠诚/托付/从零开始 触发与优先级）
- E3 关键人物识别（贝蒂/罗兹瓦尔/爱蜜莉雅/帕克）
- prompts 注入（空间场景/人物/名场面三节）
- WorldState.scene 持久化

用法：python tests/test_v14_7_scene.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.prompts import PromptBuilder
from shared.scene_manager import SceneManager
from shared.state import OniStage, RamStage, StoryArc, TwinState, WorldState


def _state(**kw) -> TwinState:
    defaults = dict(arc=StoryArc.MANSION_ERA, user_name="小东", favor=40,
                    ram_favor=20, independence=0.5, recovery=1.0,
                    context_summary="", events=[])
    defaults.update(kw)
    return TwinState(**defaults)


def test_parse_scene_change() -> None:
    assert SceneManager.parse_scene_change("去厨房") == "KITCHEN"
    assert SceneManager.parse_scene_change("我想回房间休息") == "ROOM"
    assert SceneManager.parse_scene_change("我们到花园走走吧") == "GARDEN"
    assert SceneManager.parse_scene_change("去书库找本书") == "LIBRARY"
    assert SceneManager.parse_scene_change("厨房的茶很好喝") is None, "闲聊不应触发切换"
    assert SceneManager.parse_scene_change("罗兹瓦尔宅邸") is None
    # V14.7 修复（验收 O-3）：「在X」是位置陈述非移动意图，不应误触
    assert SceneManager.parse_scene_change("在厨房喝茶") is None, "「在厨房喝茶」不应切场景"
    assert SceneManager.parse_scene_change("在花园散步") is None
    assert SceneManager.parse_scene_change("刚才在厨房泡的茶") is None
    # 真实移动组合仍识别
    assert SceneManager.parse_scene_change("进厨房看看") == "KITCHEN"
    assert SceneManager.parse_scene_change("来到花园") == "GARDEN"


def test_scene_opening() -> None:
    op = SceneManager.get_scene_opening("KITCHEN", "上午", "晴朗")
    assert op and "早餐" in op["rem_view"], op
    assert op["ram_view"]
    op_night = SceneManager.get_scene_opening("ROOM", "深夜", "晴朗")
    assert op_night and "心事" in op_night["rem_view"], op_night
    assert SceneManager.get_scene_opening("未知场景", "上午", "晴朗") is None


def test_scene_interaction() -> None:
    inter = SceneManager.get_scene_interaction("KITCHEN", "上午")
    assert inter and inter["rem_view"] and inter["ram_view"], inter
    # ROOM 只有 opening 无 interaction → None（不注入）
    assert SceneManager.get_scene_interaction("ROOM", "上午") is None


def test_milestone_triggers() -> None:
    # 鬼化（优先级最高）
    ms = SceneManager.get_milestone(_state(oni_stage=OniStage.FULL))
    assert ms and ms["id"] == "oni_release", ms
    # 失忆重逢
    ms2 = SceneManager.get_milestone(_state(recovery=0.2))
    assert ms2 and ms2["id"] == "memory_fragment", ms2
    # 忠诚锁定
    ms3 = SceneManager.get_milestone(_state(favor=96))
    assert ms3 and ms3["id"] == "loyalty_lock", ms3
    # 拉姆托付
    ms4 = SceneManager.get_milestone(_state(ram_stage=RamStage.ACKNOWLEDGED))
    assert ms4 and ms4["id"] == "ram_entrust", ms4
    # 从零开始
    ms5 = SceneManager.get_milestone(_state(wants_push=True))
    assert ms5 and ms5["id"] == "zero_start", ms5
    # 正常状态 → None
    assert SceneManager.get_milestone(_state()) is None


def test_character_lines() -> None:
    ch = SceneManager.get_character_lines("贝蒂大人今天在禁书库吗？")
    assert ch and ch["person"] == "BEATRICE" and ch["rem_lines"], ch
    ch2 = SceneManager.get_character_lines("罗兹瓦尔大人怎么安排？")
    assert ch2 and ch2["person"] == "ROSWAAL" and ch2["ram_lines"], ch2
    ch3 = SceneManager.get_character_lines("帕克在睡觉")
    assert ch3 and ch3["person"] == "PACK", ch3
    assert SceneManager.get_character_lines("今天天气不错") is None


def test_prompt_injection() -> None:
    world = WorldState(current_time="2026-08-19 08:00", period="上午", weather="晴朗")
    world.scene = "KITCHEN"
    # 空间场景注入
    p = PromptBuilder.build(_state(), world=world)
    assert "当前场景：厨房" in p, "应注入场景互动引导"
    assert "蕾姆在此场景的倾向" in p
    # 场景开场注入（一次性）
    op = SceneManager.get_scene_opening("KITCHEN", "上午", "晴朗")
    p2 = PromptBuilder.build(_state(), world=world, scene_opening=op)
    assert "场景开场（您刚来到厨房）" in p2 and "早餐" in p2
    # 人物互动注入
    p3 = PromptBuilder.build(_state(), world=world, user_input="贝蒂大人还好吗")
    assert "关键人物互动引导（BEATRICE）" in p3
    # 名场面注入
    p4 = PromptBuilder.build(_state(favor=96), world=world)
    assert "名场面语感（忠诚锁定）" in p4


def test_scene_persistence() -> None:
    ws = WorldState(current_time="2026-08-19 08:00", period="上午", weather="晴朗")
    ws.scene = "GARDEN"
    saved = ws.save_dict()
    assert saved["scene"] == "GARDEN"
    ws2 = WorldState.load_or_create(saved)
    assert ws2.scene == "GARDEN", "scene 应持久化往返"


def main() -> int:
    tests = [
        ("场景切换识别", test_parse_scene_change),
        ("场景开场选择", test_scene_opening),
        ("场景互动选择", test_scene_interaction),
        ("E4 名场面触发", test_milestone_triggers),
        ("E3 关键人物识别", test_character_lines),
        ("prompts 三节注入", test_prompt_injection),
        ("scene 持久化", test_scene_persistence),
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
