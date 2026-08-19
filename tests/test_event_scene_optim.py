# -*- coding: utf-8 -*-
"""V14.7 优化 G-1 + O-1：事件高亮注入 + 场景联动刷新测试。"""
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


def _bridge_with_world():
    import shared.config as cfg
    tmp = tempfile.mkdtemp(prefix="g1o1_test_")
    with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
        from llm import ReZeroLLMBridge
        from shared.conversation_store import ConversationStore
        from shared.world_state import WorldState
        conv = ConversationStore()
        bot = ReZeroLLMBridge(
            api_key="sk-test", base_url="http://127.0.0.1:1",
            model_name="deepseek-chat", conversation_store=conv)
        bot.world = WorldState.now()
        return bot


def test_event_highlight_injected_g1() -> None:
    """G-1：事件高亮小节注入（含双子倾向 + 优先回应指令）。"""
    from shared.prompts import PromptBuilder
    from shared.state import EVENT_POOL, TwinState, StoryArc, FavorLevel, OniStage, RamStage
    cat = next(ev for ev in EVENT_POOL if ev["id"] == "cat_visitor")
    st = TwinState(arc=StoryArc.MANSION_ERA, favor=55, favor_level=FavorLevel.CLOSE,
                   locked=False, independence=0.5, recovery=1.0, ram_favor=30,
                   ram_stage=RamStage.OBSERVING, oni_stage=OniStage.NONE, witch_scent=0,
                   context_summary="", user_name="小东", events=[], wants_push=False)
    ws = __import__("shared.state", fromlist=["WorldState"]).WorldState.now()
    ws.active_event = cat["desc"]
    ws.active_event_id = "cat_visitor"
    p = PromptBuilder.build(st, world=ws)
    assert "今日宅邸事件" in p, "事件高亮节应注入"
    assert "蕾姆对此的倾向" in p and cat["rem_view"] in p, "应含蕾姆倾向"
    assert "优先自然回应" in p, "应含优先回应指令"


def test_scene_event_refresh_o1() -> None:
    """O-1：切场景时冲突事件被刷新（走廊事件 → 书库场景 → 书库事件）。"""
    from shared.state import EVENT_POOL
    bot = _bridge_with_world()
    bot.world.weather_seed = 42  # 固定种子消除 flaky（刷新结果确定性）
    tea = next(ev for ev in EVENT_POOL if ev["id"] == "tea_ready")
    bot.world.active_event = tea["desc"]
    bot.world.active_event_id = "tea_ready"
    # 手动调 _build_messages（零 API）
    bot._build_messages("去书库")
    assert bot.world.scene == "LIBRARY", f"场景应切到书库: {bot.world.scene}"
    # 事件应刷新（seed=42 确定性下不再是走廊红茶）
    assert bot.world.active_event_id != "tea_ready", f"走廊事件应被刷新: {bot.world.active_event_id}"
    from shared import vignette as _v
    loc = _v._derive_location(bot.world.active_event)
    assert loc != "宅邸走廊", f"刷新后不应仍是走廊事件: {loc}"


def test_scene_no_refresh_when_match() -> None:
    """O-1 反向：场景与事件地点一致时不刷新（稳定性）。"""
    from shared.state import EVENT_POOL
    bot = _bridge_with_world()
    bot.world.weather_seed = 42  # 固定种子
    lib = next(ev for ev in EVENT_POOL if ev["id"] == "library_dust")
    bot.world.active_event = lib["desc"]
    bot.world.active_event_id = "library_dust"
    bot._build_messages("去书库")
    assert bot.world.active_event_id == "library_dust", "地点一致不应刷新"


def main() -> int:
    tests = [
        ("G-1 事件高亮注入", test_event_highlight_injected_g1),
        ("O-1 场景联动刷新冲突事件", test_scene_event_refresh_o1),
        ("O-1 地点一致不刷新", test_scene_no_refresh_when_match),
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
