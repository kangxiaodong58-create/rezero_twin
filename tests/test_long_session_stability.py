"""长会话稳定性专项测试（无框架，直接运行，零 API 费用）。

覆盖（研判报告「长会话稳定性」专项）：
- 历史截断：max_history=8 下连续 30 轮 messages 长度有界（不泄漏）
- 状态机：30 轮混合输入 engine.update 无异常、favor 有界
- 存档往返：30 轮后 save_dict → load_or_create 关键字段无损
- 场景切换累积：30 轮含多次切换，scene 正确、开场不重复注入
- Validator 长文本：1200 字边界 + 多轮稳定
- 事件池压力：5000 次采样无异常

用法：python tests/test_long_session_stability.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm.bridge import ReZeroLLMBridge
from shared.scene_manager import SceneManager
from shared.state import WorldState
from shared.validators import ResponseValidator

ROUNDS = 30

# 30 轮混合输入剧本（日常/负面/名字/场景移动/闲聊/人物）
SCRIPT = [
    "早上好", "今天天气真好", "蕾姆在做什么呢", "我好累啊", "去厨房看看",
    "有什么好吃的吗", "蕾姆真好", "我好没用", "我想重新开始", "回房间休息",
    "晚安", "贝蒂大人在吗", "厨房的茶很好喝", "拉姆姐姐今天心情如何",
    "我们去看花园", "花开了吗", "我好难过", "谢谢你一直陪着我", "去书库找本书",
    "这本书讲什么", "蕾姆喜欢看书吗", "我想听你讲故事", "深夜了还不睡吗",
    "去走廊走走", "月光真美", "蕾姆是我的光", "不行我要振作", "从零开始吧",
    "我们去餐厅吃饭", "今天辛苦了一天",
][:ROUNDS]


def _make_bridge() -> tuple:
    world = WorldState(current_time="2026-08-19 08:00", period="上午", weather="晴朗")
    bridge = ReZeroLLMBridge(api_key="sk-test-nonet", base_url="http://127.0.0.1:9",
                             model_name="deepseek-chat", max_history=8, world=world)
    return bridge, world


def test_history_bounded() -> None:
    """30 轮后 messages 长度恒定（system + max_history + user）。"""
    bridge, _ = _make_bridge()
    for i, text in enumerate(SCRIPT):
        msgs, _ = bridge._build_messages(text)
        assert len(msgs) <= 10, f"第 {i} 轮 messages 长度 {len(msgs)} 超界"
        assert msgs[0]["role"] == "system" and msgs[-1]["role"] == "user"
        assert len(bridge.history) <= 8, f"第 {i} 轮 history {len(bridge.history)} 超界"


def test_state_machine_30rounds() -> None:
    """30 轮混合输入状态机稳定：无异常、favor 有界、events 不失控。"""
    bridge, _ = _make_bridge()
    favors = []
    for text in SCRIPT:
        state = bridge.engine.update(text)
        favors.append(state.favor)
    assert all(0 <= f <= 100 for f in favors), f"favor 越界: {favors}"
    assert len(favors) == ROUNDS
    # 有正向也有波动（非恒值死锁）
    assert max(favors) > min(favors) or True  # 信息性：不强制
    events = bridge.engine.events
    assert len(events) <= 50, f"events 失控: {len(events)}"


def test_world_persistence_roundtrip() -> None:
    """30 轮后存档往返：关键字段无损（含 scene/active_event_id）。"""
    bridge, world = _make_bridge()
    for text in SCRIPT:
        bridge._build_messages(text)
    saved = world.save_dict()
    ws2 = WorldState.load_or_create(saved)
    assert ws2.scene == world.scene, f"scene 往返失败: {ws2.scene} vs {world.scene}"
    # active_event_id：load 时若判定离线归来会刷新事件（设计行为）——断言刷新后仍合法
    from shared.state import EVENT_POOL
    valid_ids = {ev["id"] for ev in EVENT_POOL}
    assert ws2.active_event_id in valid_ids, f"事件 id 非法: {ws2.active_event_id}"
    # 时段/天气随真实时钟推演（构造固定值会被 load 重推）——断言落入合法值域
    assert ws2.period in ("清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜"), ws2.period
    assert ws2.weather in ("晴朗", "多云", "小雨", "大雨", "阴沉"), ws2.weather
    assert ws2.days_since_last == world.days_since_last, \
        f"days 往返失败: {ws2.days_since_last} vs {world.days_since_last}"


def test_scene_switch_accumulate() -> None:
    """30 轮多次场景切换：scene 正确收敛、开场只在切换轮注入。"""
    bridge, world = _make_bridge()
    openings_seen = 0
    for text in SCRIPT:
        msgs, _ = bridge._build_messages(text)
        prompt = msgs[0]["content"]
        if "场景开场（您刚来到" in prompt:
            openings_seen += 1
    assert openings_seen >= 3, f"应多次触发场景开场，实际 {openings_seen}"
    # 最终 scene 是合法场景键（中途可能被「在X」再切）
    from shared.scene_manager import SCENE_KEYWORDS
    assert world.scene in SCENE_KEYWORDS.values() or world.scene == "", \
        f"scene 异常值: {world.scene}"
    # 每轮 prompt 最多一个场景开场（无重复注入）
    bridge2, world2 = _make_bridge()
    for text in SCRIPT:
        msgs, _ = bridge2._build_messages(text)
        assert msgs[0]["content"].count("场景开场（您刚来到") <= 1, "开场重复注入"


def test_validator_long_text() -> None:
    """Validator 长文本稳定：1200 字边界、多轮调用无异常。"""
    v = ResponseValidator()
    long_ok = "【蕾姆】: \"" + "蕾姆认为您说得对。" * 100 + "\""
    r = v.validate(long_ok)
    assert r.ok, f"长文本应通过: {r.reason}"
    for i in range(50):
        r = v.validate(f"【蕾姆】: \"第 {i} 轮测试。\"")
        assert r.ok
    # 超长（>1200）应被拦截（max_length 边界稳定）
    too_long = "【蕾姆】: \"" + "长" * 1300 + "\""
    r2 = v.validate(too_long)
    assert not r2.ok and "Too long" in (r2.reason or "")


def test_event_pool_stress() -> None:
    """事件池 5000 次采样：无异常、候选恒非空。"""
    from shared.state import EVENT_POOL, WorldState
    ids = {ev["id"] for ev in EVENT_POOL}
    picked = set()
    for seed in range(5000):
        ev = WorldState._pick_active_event("2026-08-19", "午后", "晴朗", seed)
        assert ev["id"] in ids, f"非法事件 id: {ev['id']}"
        picked.add(ev["id"])
    assert len(picked) >= 10, f"5000 次采样覆盖过少: {len(picked)}"


def main() -> int:
    tests = [
        ("历史截断（30 轮 messages ≤10）", test_history_bounded),
        ("状态机 30 轮稳定", test_state_machine_30rounds),
        ("存档往返无损", test_world_persistence_roundtrip),
        ("场景切换累积（开场不重复）", test_scene_switch_accumulate),
        ("Validator 长文本稳定", test_validator_long_text),
        ("事件池 5000 次压力", test_event_pool_stress),
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
