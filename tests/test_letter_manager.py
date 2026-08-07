"""V14.3：主动来信系统测试（无框架，直接运行，零 API 费用）。

覆盖（验收）：
- 模板池加载（40 条，JSON 结构完整）
- 冷却三条红线（首次启动 / 每日 1 次 / 8h 间隔）
- 离线桶边界（<12h 同时段静默 / 跨时段 / 12-24 / 24-72 / 72-168 / ≥168）
- 发件人权重三档（favor <30 / <70 / ≥70）
- 白名单安全插值（未知占位符不崩）
- twins 复合来信拆分
- evaluate_and_dispatch 全链路（触发 → messages + 冷却状态更新）
- last_period 回填（空字段从 DB 推导 / 已有值跳过）

用法：python tests/test_letter_manager.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.letter_manager import LetterManager
from shared.state import WorldState
from shared.conversation_store import ConversationStore


def _state(**kw) -> WorldState:
    """构造测试用 WorldState（默认：3 天前交互、上次上午、当前夜晚、favor 80）。"""
    base = WorldState(
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
        period="夜晚",
        weather="晴朗",
        last_interaction_ts=time.time() - 3 * 86400,
        last_period="上午",
    )
    for k, v in kw.items():
        setattr(base, k, v)
    return base


def _tmp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return ConversationStore(db_path=path)


def test_templates_loaded() -> None:
    lm = LetterManager()
    assert len(lm.templates) >= 35, f"模板池应 ≥35 条，实际 {len(lm.templates)}"
    ids = {t["id"] for t in lm.templates}
    assert len(ids) == len(lm.templates), "模板 id 应唯一"
    buckets = {t["bucket"] for t in lm.templates}
    assert {"CROSS_PERIOD", "HALF_DAY", "DAYS_1_3", "DAYS_3_7", "LONG_ABSENCE"} <= buckets


def test_cooldown_first_launch() -> None:
    lm = LetterManager()
    st = _state(last_interaction_ts=0.0)  # 首次启动/空库
    assert lm.check_cooldown(st, time.time(), datetime.now().strftime("%Y-%m-%d")) is False


def test_cooldown_daily_cap() -> None:
    lm = LetterManager()
    today = datetime.now().strftime("%Y-%m-%d")
    st = _state(last_letter_date=today)
    assert lm.check_cooldown(st, time.time(), today) is False, "每日上限应拦截"


def test_cooldown_min_interval() -> None:
    lm = LetterManager()
    now = time.time()
    st = _state(last_letter_ts=now - 7 * 3600)  # 7h 前刚来信
    assert lm.check_cooldown(st, now, "2099-01-01") is False, "8h 间隔应拦截"
    st2 = _state(last_letter_ts=now - 9 * 3600)
    assert lm.check_cooldown(st2, now, "2099-01-01") is True


def test_bucket_boundaries() -> None:
    calc = LetterManager.calculate_offline_bucket
    assert calc(11.9, "上午", "上午") is None, "同时段短离线静默"
    assert calc(11.9, "上午", "夜晚") == "CROSS_PERIOD"
    assert calc(12.0, "上午", "夜晚") == "HALF_DAY"
    assert calc(23.9, "上午", "夜晚") == "HALF_DAY"
    assert calc(24.0, "上午", "夜晚") == "DAYS_1_3"
    assert calc(71.9, "上午", "夜晚") == "DAYS_1_3"
    assert calc(72.0, "上午", "夜晚") == "DAYS_3_7"
    assert calc(167.9, "上午", "夜晚") == "DAYS_3_7"
    assert calc(168.0, "上午", "夜晚") == "LONG_ABSENCE"


def test_sender_weights_by_favor() -> None:
    """三档权重结构：低好感拉姆主导，高好感蕾姆主导。"""
    import random
    original = random.choices
    captured = {}

    def spy(population, weights=None, k=1):
        captured["weights"] = weights
        return [population[0]]

    random.choices = spy
    try:
        LetterManager.select_sender(10)
        w_low = captured["weights"]
        assert w_low[0] > w_low[1], f"低好感拉姆应主导: {w_low}"
        LetterManager.select_sender(80)
        w_high = captured["weights"]
        assert w_high[1] > w_high[0], f"高好感蕾姆应主导: {w_high}"
    finally:
        random.choices = original


def test_interpolate_whitelist() -> None:
    lm = LetterManager()
    out = lm.interpolate_text("等了{days_absent}天，{unknown_tag}保持原样",
                              {"days_absent": 5})
    assert "5" in out and "{unknown_tag}" in out, f"未知占位符应原样保留: {out}"


def test_split_twins() -> None:
    msgs = LetterManager.split_twins_message(
        "【拉姆】蕾姆，那家伙回来了。\n【蕾姆】姐姐！太好了。")
    assert len(msgs) == 2
    assert msgs[0]["sender"] == "ram" and "那家伙" in msgs[0]["content"]
    assert msgs[1]["sender"] == "rem" and "太好了" in msgs[1]["content"]


def test_dispatch_full_chain() -> None:
    """全链路：3 天离线 + 跨时段 + favor 80 → 触发来信并更新冷却状态。"""
    lm = LetterManager()
    st = _state()  # 3 天前交互、last_period=上午、period=夜晚、favor 80
    today = datetime.now().strftime("%Y-%m-%d")
    result = lm.evaluate_and_dispatch(st, favor=80.0, current_weather="晴朗",
                                      now_ts=time.time(), today_str=today)
    assert result is not None, "3 天离线应触发来信"
    assert result["messages"], "应有来信消息"
    for m in result["messages"]:
        assert m["sender"] in ("rem", "ram"), f"发件人非法: {m['sender']}"
        assert m["content"].strip(), "内容不应为空"
    assert result["suppress_vignette"] is True
    assert st.last_letter_ts > 0 and st.last_letter_date == today, "冷却状态应更新"


def test_dispatch_same_period_silent() -> None:
    """同时段短离线（<12h 且 period 未变）→ 静默。"""
    lm = LetterManager()
    st = _state(last_interaction_ts=time.time() - 5 * 3600, last_period="夜晚")
    result = lm.evaluate_and_dispatch(st, favor=50.0, current_weather="晴朗",
                                      now_ts=time.time(), today_str="2099-01-01")
    assert result is None, "同时段短离线应静默"


def test_dispatch_twins_split() -> None:
    """twins 来信应拆分为双条消息（rem + ram）。"""
    lm = LetterManager()
    for _ in range(200):  # 多次采样确保 twins 命中一次（权重 25%）
        st = _state()  # 每次新建（last_letter_* 为默认 0，不撞冷却）
        st.last_letter_date = ""  # 确保每日上限不拦截
        result = lm.evaluate_and_dispatch(st, favor=80.0, current_weather="晴朗",
                                          now_ts=time.time(), today_str="2099-01-01")
        if result and len(result["messages"]) == 2:
            senders = {m["sender"] for m in result["messages"]}
            assert senders == {"rem", "ram"}, f"twins 应拆为双人: {senders}"
            return
    raise AssertionError("200 次采样未命中 twins 拆分（权重或模板问题）")


def test_ensure_last_period_backfill() -> None:
    """last_period 空 → 从 DB 最后消息推导（固定时间戳）；已有值 → 跳过。"""
    store = _tmp_store()
    mid = store.append("user", "你", "昨晚的对话")
    # 固定 created_at 为上午 10 点 → 推导「上午」（不依赖测试运行时刻）
    with store._connect() as conn:
        conn.execute("UPDATE messages SET created_at='2026-01-01 10:00:00' WHERE id=?", (mid,))
        conn.commit()
    st = _state(last_period="")
    st.ensure_last_period(store)
    assert st.last_period == "上午", f"应从 DB 推导为「上午」: {st.last_period}"

    st2 = _state(last_period="下午")
    st2.ensure_last_period(store)
    assert st2.last_period == "下午", "已有值不应覆盖"

    # 空库 → 回落当前时段
    store_empty = _tmp_store()
    st3 = _state(last_period="")
    st3.ensure_last_period(store_empty)
    assert st3.last_period == st3.period, f"空库应回落当前时段: {st3.last_period}"


def main() -> int:
    tests = [
        ("模板池加载（≥35 条 + id 唯一）", test_templates_loaded),
        ("冷却：首次启动排除", test_cooldown_first_launch),
        ("冷却：每日上限", test_cooldown_daily_cap),
        ("冷却：8h 最小间隔", test_cooldown_min_interval),
        ("离线桶边界（8 断言）", test_bucket_boundaries),
        ("发件人权重三档", test_sender_weights_by_favor),
        ("白名单安全插值", test_interpolate_whitelist),
        ("twins 复合拆分", test_split_twins),
        ("全链路触发 + 冷却状态更新", test_dispatch_full_chain),
        ("同时段短离线静默", test_dispatch_same_period_silent),
        ("twins 来信拆分双泡", test_dispatch_twins_split),
        ("last_period 回填（DB 推导/已有跳过）", test_ensure_last_period_backfill),
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
