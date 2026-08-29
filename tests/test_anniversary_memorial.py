"""V15.0「年轮」M2 测试：纪念日引擎 + 今日纪念注入 + 纪念卡/相册。

覆盖：
- 节日表：春节五年锚点（联网多源校准）/ 元宵=春节+14 推导（不存储）
  / 每年端午·七夕·中秋齐备
- compute_facts：第 1 天 / 第 100 天里程碑 / 周年 / 当日节日（第 N 个）/
  即将到来（3 天窗）/ 节日当天不再产出 upcoming / 未来 genesis 空事实
- record_day_facts：days_milestone/festival 落账幂等
- ensure_genesis：无账本建今天 / 有 store 取最早消息 / 幂等
- PromptBuilder._build_anniversary_section + bridge._build_messages 注入
- memorial：L2 确定性 + 插值 / save_card 相册幂等（同类同日一张）/
  账本 memorial 记录 / registry memorial 三 arc 契约
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from shared import life_ledger, memorial  # noqa: E402
from shared.anniversary import (  # noqa: E402
    build_festival_table,
    compute_facts,
    count_festival_between,
    festival_on,
    genesis_days,
)
from shared.conversation_store import ConversationStore  # noqa: E402
from shared.life_ledger import LifeLedger, ensure_genesis, record_day_facts  # noqa: E402
from shared.template_registry import load_registry, pick as registry_pick  # noqa: E402

REGISTRY_PATH = os.path.join(PROJECT_ROOT, "content", "templates", "registry.json")


@pytest.fixture(autouse=True)
def _isolated_default(monkeypatch, tmp_path):
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "life.db"))
    life_ledger.reset_default()
    yield
    life_ledger.reset_default()


# ── 节日表（日期经香港天文台对照表等多源校准）────────────────────

def test_spring_festival_anchors():
    """春节五年锚点（2026-02-17 / 2027-02-06 / 2028-01-26 / 2029-02-13 / 2030-02-03）。"""
    assert festival_on(date(2026, 2, 17)) == "春节"
    assert festival_on(date(2027, 2, 6)) == "春节"
    assert festival_on(date(2028, 1, 26)) == "春节"
    assert festival_on(date(2029, 2, 13)) == "春节"
    assert festival_on(date(2030, 2, 3)) == "春节"


def test_lantern_derived_not_stored():
    """元宵 = 春节 + 14 天，代码推导（消灭双源：搜索摘要曾给出错误元宵日期）。"""
    table = build_festival_table()
    assert table.get("2027-02-20") == "元宵节"  # 2027 春节 2-6 + 14
    assert table.get("2026-03-03") == "元宵节"  # 2026 春节 2-17 + 14


def test_lunar_festivals_complete_per_year():
    for year in range(2026, 2031):
        for name in ("端午节", "七夕节", "中秋节"):
            hits = [d for d, n in build_festival_table().items() if n == name
                    and d.startswith(str(year))]
            assert len(hits) == 1, f"{year} {name} 应恰有一条: {hits}"


# ── compute_facts ────────────────────────────────────────────────

def test_genesis_days_inclusive():
    assert genesis_days(date(2026, 1, 1), date(2026, 1, 1)) == 1
    assert genesis_days(date(2026, 1, 1), date(2026, 4, 10)) == 100


def test_facts_first_day_and_milestone():
    genesis = date(2026, 8, 29)
    facts = compute_facts(genesis=genesis, today=genesis)
    assert any(f.kind == "genesis_days" and "第 1 天" in f.title for f in facts)
    assert not any(f.kind == "days_milestone" for f in facts)

    facts = compute_facts(genesis=genesis, today=genesis + timedelta(days=99))
    milestone = [f for f in facts if f.kind == "days_milestone"]
    assert milestone and milestone[0].key == "100"
    assert any(f.kind == "genesis_days" for f in facts)


def test_facts_annual():
    facts = compute_facts(genesis=date(2024, 8, 29), today=date(2026, 8, 29))
    annual = [f for f in facts if f.kind == "genesis_annual"]
    assert annual and annual[0].key == "2"


def test_facts_festival_nth_and_upcoming():
    genesis = date(2026, 1, 1)
    # 当日中秋（2026-09-25）：第 1 个
    facts = compute_facts(genesis=genesis, today=date(2026, 9, 25))
    fest = [f for f in facts if f.kind == "festival"]
    assert fest and "第 1 个中秋节" in fest[0].title
    assert not any(f.kind == "festival_upcoming" for f in facts), "节日当天不产 upcoming"
    # 两天前：即将到来
    facts = compute_facts(genesis=genesis, today=date(2026, 9, 23))
    up = [f for f in facts if f.kind == "festival_upcoming"]
    assert up and up[0].key == "中秋节" and "2 天" in up[0].title
    # 次年中秋：第 2 个（跨年计数）
    facts = compute_facts(genesis=genesis, today=date(2027, 9, 15))
    fest = [f for f in facts if f.kind == "festival"]
    assert fest and "第 2 个中秋节" in fest[0].title


def test_count_festival_between():
    assert count_festival_between("春节", date(2026, 1, 1), date(2028, 3, 1)) == 3
    assert count_festival_between("中秋节", date(2026, 9, 26), date(2027, 9, 14)) == 0


def test_facts_future_genesis_empty():
    assert compute_facts(genesis=date(2030, 1, 1), today=date(2026, 8, 29)) == []


# ── 落账与 ensure_genesis ────────────────────────────────────────

def test_record_day_facts_idempotent(tmp_path):
    """genesis=2026-06-18、today=2026-09-25：恰为第 100 天 + 中秋，双事实同日。"""
    ledger = LifeLedger(str(tmp_path / "life.db"))
    facts = compute_facts(genesis=date(2026, 6, 18), today=date(2026, 9, 25))
    kinds = {f.kind for f in facts}
    assert {"days_milestone", "festival"} <= kinds, f"前置事实不足: {facts}"
    record_day_facts(facts, date(2026, 9, 25), ledger=ledger)
    record_day_facts(facts, date(2026, 9, 25), ledger=ledger)
    all_kinds = [e["kind"] for e in ledger.all_events()]
    assert all_kinds.count("festival") == 1 and all_kinds.count("days_milestone") == 1


def test_ensure_genesis_from_store_and_idempotent(tmp_path):
    store = ConversationStore(str(tmp_path / "conv.db"))
    store.append("user", "你", "你好")
    ledger = LifeLedger(str(tmp_path / "life.db"))
    g1 = ensure_genesis(store, ledger=ledger)
    g2 = ensure_genesis(store, ledger=ledger)
    assert g1 == g2 == date.fromisoformat(store.oldest_message_time()[:10])
    empty_ledger = LifeLedger(str(tmp_path / "empty.db"))
    g3 = ensure_genesis(None, ledger=empty_ledger)
    assert g3 == date.today(), "无证据 → 相识日=今天"


# ── Prompt 注入 ──────────────────────────────────────────────────

def test_anniversary_section_render():
    from shared.prompts import PromptBuilder
    facts = compute_facts(genesis=date(2026, 1, 1), today=date(2026, 9, 25))
    section = PromptBuilder._build_anniversary_section(facts)
    assert "今日纪念" in section and "中秋节" in section
    assert PromptBuilder._build_anniversary_section([]) == ""


def test_bridge_injects_facts_into_messages(monkeypatch):
    from datetime import datetime
    from llm.bridge import ReZeroLLMBridge
    bridge = ReZeroLLMBridge(api_key="sk-test", conversation_store=None)
    fact = type("F", (), {"kind": "festival", "title": "今天是中秋节",
                          "key": "中秋节"})()
    monkeypatch.setattr(ReZeroLLMBridge, "_anniv_cache",
                        {date.today().isoformat(): [fact]})
    msgs, _ = bridge._build_messages("你好")
    assert "今日纪念" in msgs[0]["content"] and "中秋节" in msgs[0]["content"]


# ── 纪念卡 ───────────────────────────────────────────────────────

def _facts_for(kind_day: date):
    return compute_facts(genesis=date(2026, 4, 21), today=kind_day)


def test_memorial_generate_l2_deterministic_and_interpolation(tmp_path):
    genesis = date(2026, 4, 21)
    milestone_day = genesis + timedelta(days=99)  # 第 100 天
    facts = compute_facts(genesis=genesis, today=milestone_day)
    a = memorial.generate("days_milestone", facts=facts, arc="mansion_era",
                          today=milestone_day)
    b = memorial.generate("days_milestone", facts=facts, arc="mansion_era",
                          today=milestone_day)
    assert a and a == b, "L2 同 seed 确定性"
    assert "100" in a, "文案插值应含天数"


def test_memorial_generate_l1_fallback(tmp_path):
    genesis = date(2026, 4, 21)
    day = genesis + timedelta(days=99)
    facts = _facts_for(day)
    text = memorial.generate("days_milestone", facts=facts, arc="mansion_era",
                             today=day,
                             llm_callable=lambda p: "（蕾姆轻声数着日子）一百天了呢。")
    assert "一百天" in text, "L1 成功时用 LLM 文本"


def test_memorial_generate_l1_exception_falls_back(tmp_path):
    genesis = date(2026, 4, 21)
    day = genesis + timedelta(days=99)
    def _boom(_p):
        raise RuntimeError("api down")
    text = memorial.generate("days_milestone", facts=_facts_for(day),
                             arc="mansion_era", today=day,
                             llm_callable=_boom)
    assert text and "100" in text, "L1 失败回落 L2 注册表"


def test_save_card_album_dedup_and_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "life.db"))
    life_ledger.reset_default()
    day = date(2026, 9, 25)
    p1 = memorial.save_card("festival", day, "中秋快乐。", detail={"arc": "mansion_era"},
                            data_dir=str(tmp_path))
    assert p1 and os.path.isfile(p1) and p1.endswith(f"{day}_festival.md")
    assert memorial.has_card("festival", day, data_dir=str(tmp_path))
    p2 = memorial.save_card("festival", day, "重复卡", data_dir=str(tmp_path))
    assert p2 is None, "同类同日只落一张"
    # 不同种类同日可并存
    p3 = memorial.save_card("days_milestone", day, "第 158 天。", data_dir=str(tmp_path))
    assert p3 is not None
    # 账本 memorial 记录（每类每日一条）
    led = life_ledger.get_default_ledger()
    assert sum(1 for e in led.all_events() if e["kind"] == "memorial") == 2
    body = open(p1, encoding="utf-8").read()
    assert "纪念卡" in body and "中秋快乐" in body


def test_registry_memorial_contract():
    reg = load_registry(REGISTRY_PATH)
    for arc in ("mansion_era", "empire_era", "late_arc"):
        for kind in memorial.CARD_KINDS:
            item = registry_pick(reg, arc=arc, slot="memorial",
                                 seed=f"2026-09-25|{kind}")
            assert item is not None, f"{arc}/{kind} 应有 memorial 条目"
            assert "{days}" in item["text"] or "{festival}" in item["text"] \
                or "{years}" in item["text"], "memorial 文案应含插值占位符"
