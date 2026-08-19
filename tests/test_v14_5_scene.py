"""V14.5：场景一致性测试（无框架，直接运行，零 API 费用）。

覆盖（调研 C + B 前半 + D）：
- 天气×事件兼容：大雨/小雨时不选「晒太阳/晾晒/午后阳光」类事件
- 时段过滤：夜晚/深夜不选白昼事件；清晨/上午可选晨间事件
- 雨天/夜晚专属事件可被选中（池扩充生效）
- 防御回落：极端输入不崩
- 角色视角：to_prompt_text 注入「蕾姆/拉姆对此事的倾向」
- 旧存档兼容：无 active_event_id 不崩

用法：python tests/test_v14_5_scene.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.state import EVENT_POOL, WorldState


def _event_ids() -> dict:
    return {ev["id"]: ev for ev in EVENT_POOL}


def _sample(period: str, weather: str, n: int = 300) -> set:
    """确定性种子采样：返回 (日期, 时段, 天气) 组合下可能被选中的事件 id 集合。"""
    picked = set()
    for seed in range(n):
        ev = WorldState._pick_active_event("2026-08-19", period, weather, seed)
        picked.add(ev["id"])
    return picked


def test_weather_compat() -> None:
    """大雨/小雨天：绝不选中「晒太阳/晾晒/午后阳光」类冲突事件。"""
    ids = _event_ids()
    for weather in ("大雨", "小雨"):
        picked = _sample("午后", weather)
        for conflict in ("cat_visitor", "sunny_noon", "laundry_day"):
            assert conflict not in picked, f"{weather} 天不应选中 {conflict}（{ids[conflict]['desc']}）"
    # 雨天专属事件应出现
    rain_events = {ev["id"] for ev in EVENT_POOL if "雨" in ev["desc"]}
    picked = _sample("午后", "大雨")
    assert picked & rain_events, f"大雨天应有机会选中雨天事件: {picked}"


def test_period_compat() -> None:
    """夜晚/深夜：不选白昼事件；清晨/上午：不选深夜事件。"""
    for period in ("夜晚", "深夜"):
        picked = _sample(period, "晴朗")
        for conflict in ("garden_bloom", "sunny_noon", "laundry_day", "cleaning_morning"):
            assert conflict not in picked, f"{period} 不应选中 {conflict}"
    picked_day = _sample("上午", "晴朗")
    for conflict in ("night_wind", "night_candle_01", "night_star_01"):
        assert conflict not in picked_day, f"上午不应选中 {conflict}"
    # 深夜事件应可被选中
    picked_night = _sample("深夜", "晴朗")
    assert {"night_candle_01", "night_star_01"} & picked_night, \
        f"深夜应有机会选中深夜事件: {picked_night}"


def test_all_events_reachable() -> None:
    """13 条事件在合理天气×时段组合下全部可达（无死事件）。"""
    reachable = set()
    for period in ("清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜"):
        for weather in ("晴朗", "多云", "小雨", "大雨", "阴沉"):
            reachable |= _sample(period, weather, n=60)
    missing = {ev["id"] for ev in EVENT_POOL} - reachable
    assert not missing, f"死事件（任何组合不可达）: {missing}"


def test_defensive_fallback() -> None:
    """极端输入（不存在的天气/时段）不崩且返回合法事件。"""
    ev = WorldState._pick_active_event("2026-08-19", "暴风时段", "暴雪", 42)
    assert ev["id"] in {e["id"] for e in EVENT_POOL}, "防御回落应返回合法事件"
    assert ev["desc"]


def test_character_views_injected() -> None:
    """角色视角：active_event_id 设置后 to_prompt_text 注入蕾姆/拉姆倾向。"""
    ws = WorldState(current_time="2026-08-19 14:00", period="午后",
                    weather="晴朗", days_since_last=0)
    ws.active_event = "一只野猫从庭院围墙跳了进来，正晒着太阳"
    ws.active_event_id = "cat_visitor"
    text = ws.to_prompt_text()
    assert "蕾姆对此事的倾向" in text and "拉姆对此事的倾向" in text, text
    assert "野猫" in text
    # 无 id（旧存档/新事件无视角）→ 不注入也不崩
    ws2 = WorldState(current_time="2026-08-19 14:00", period="午后",
                     weather="晴朗", days_since_last=0)
    ws2.active_event = "未知事件描述"
    text2 = ws2.to_prompt_text()
    assert "对此事的倾向" not in text2, "无 id 不应注入视角"
    assert "未知事件描述" in text2


def main() -> int:
    tests = [
        ("天气兼容（大雨/小雨零冲突事件）", test_weather_compat),
        ("时段兼容（夜昼互斥）", test_period_compat),
        ("13 条事件全部可达（无死事件）", test_all_events_reachable),
        ("防御回落（极端输入不崩）", test_defensive_fallback),
        ("角色视角注入", test_character_views_injected),
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
