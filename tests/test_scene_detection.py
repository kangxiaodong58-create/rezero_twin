# -*- coding: utf-8 -*-
"""V14.4（LLM 优先内容路线 P0）：SCENE_GUIDES 扩充 4→12 的场景检测测试。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest.mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import load_env
load_env()


def _make_bridge():
    import shared.config as cfg
    tmp = tempfile.mkdtemp(prefix="scene_test_")
    with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
        from llm import ReZeroLLMBridge
        from shared.conversation_store import ConversationStore
        from shared.state import HardStateEngine, StoryArc, TwinState, WorldState
        conv = ConversationStore()
        bot = ReZeroLLMBridge(
            api_key="sk-test", base_url="http://127.0.0.1:1",
            model_name="deepseek-chat", conversation_store=conv)
        # 好感提到 CLOSE(50)+ 让所有场景门槛可过
        bot.engine.favor = 60
        eng = bot.engine
        state = TwinState(
            arc=StoryArc.MANSION_ERA, favor=60, favor_level=eng._get_favor_level(),
            locked=False, independence=0.3, recovery=1.0, ram_favor=20,
            oni_stage=eng.oni_stage, witch_scent=0,
            user_name="小东", events=[], context_summary="", wants_push=False,
        )
        world = WorldState()  # scene_cooldowns 空 dict，冷却判定通过
        return bot, state, world


def test_scene_detection_v144() -> None:
    """新场景关键词 → scene_id 映射（favor 60 全门槛可过）。"""
    bot, state, world = _make_bridge()
    cases = [
        ("如果有一天我离开了呢？", "farewell_weight"),
        ("我回来了。", "reunion_tenderness"),
        ("今天战斗好累。", "battle_weary"),
        ("月色真美，睡不着。", "midnight_confession"),
        ("希望一直这样下去就好了。", "wish_offer"),
        ("对不起，是我错了。", "apology_accept"),
        ("今天很开心，蕾姆泡的茶真好喝。", "daily_glow"),
        ("你好", None),  # 无场景
    ]
    for text, expect in cases:
        scene, _ = bot._detect_scene(text, state, world)
        assert scene == expect, f"{text!r} 应检测为 {expect}，实际 {scene}"
    # guardian_vow 需 DEAR：favor 提到 85 再测
    from shared.state import FavorLevel, TwinState
    bot.engine.favor = 85
    state_high = TwinState(
        arc=state.arc, favor=85, favor_level=FavorLevel.DEAR,
        locked=False, independence=0.3, recovery=1.0, ram_favor=20,
        oni_stage=state.oni_stage, witch_scent=0,
        user_name="小东", events=[], context_summary="", wants_push=False,
    )
    scene, _ = bot._detect_scene("我会保护你们的，不会让你们受伤。", state_high, world)
    assert scene == "guardian_vow", f"高好感应触发 guardian_vow: {scene}"


def test_scene_favor_gate_v144() -> None:
    """好感门槛：guardian_vow 需 DEAR（favor<80 不触发）。"""
    bot, state, world = _make_bridge()
    # 降至 FAMILIAR
    from shared.state import FavorLevel, TwinState
    bot.engine.favor = 30
    state2 = TwinState(
        arc=state.arc, favor=30, favor_level=FavorLevel.FAMILIAR,
        locked=False, independence=0.3, recovery=1.0, ram_favor=20,
        oni_stage=state.oni_stage, witch_scent=0,
        user_name="小东", events=[], context_summary="", wants_push=False,
    )
    scene, _ = bot._detect_scene("我会保护你们的。", state2, world)
    assert scene is None, f"低好感不应触发 guardian_vow: {scene}"


def main() -> int:
    tests = [
        ("新场景关键词映射", test_scene_detection_v144),
        ("好感门槛", test_scene_favor_gate_v144),
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
