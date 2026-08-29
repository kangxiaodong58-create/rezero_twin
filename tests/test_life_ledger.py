"""V15.0「年轮」M1 测试：人生账本 life_ledger。

验收口径（构思 §五 M1）：零 UI；回填幂等（跑两遍账本不变）；镜像静默；
与工作记忆严格分离（append-only + dedup）。

覆盖：
- 账本：append 幂等 / detail JSON 快照 / 排序与 count / 非法参数拒绝
- 镜像：引擎时刻（first_name/locked/reunion/breaker）/ 篇章切换 /
  场景首访去重 / 名场面每日本 / 来信每日 / 账本损坏静默
- 回填：genesis 取最早消息 / 引擎事件 seq→时刻映射 / 首封来信 / 双跑幂等
- 隔离：REZERO_LIFE_DB env 覆盖 + reset_default
"""

from __future__ import annotations

import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from shared import life_ledger  # noqa: E402
from shared.conversation_store import ConversationStore  # noqa: E402
from shared.life_ledger import (  # noqa: E402
    LifeLedger,
    backfill_from,
    mirror_arc_shift,
    mirror_letter,
    mirror_milestone,
    mirror_scene_first,
    reset_default,
)
from shared.state import HardStateEngine, StoryArc  # noqa: E402


@pytest.fixture
def ledger(tmp_path):
    return LifeLedger(str(tmp_path / "life.db"))


@pytest.fixture(autouse=True)
def _isolated_default(monkeypatch, tmp_path):
    """所有涉及默认单例的镜像走独立临时库，且逐用例重置单例。"""
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "default-life.db"))
    reset_default()
    yield
    reset_default()


# ── 账本基础 ──────────────────────────────────────────────────────

def test_append_idempotent_by_dedup(ledger):
    assert ledger.append(ts="2026-08-29 10:00:00", kind="genesis",
                         title="相识之日", dedup_key="genesis") is True
    assert ledger.append(ts="2026-08-29 11:00:00", kind="genesis",
                         title="重复不落账", dedup_key="genesis") is False
    assert ledger.count() == 1
    ev = ledger.all_events()[0]
    assert ev["ts"] == "2026-08-29 10:00:00", "重复调用不得改写首条事实"


def test_append_detail_json_snapshot(ledger):
    ledger.append(kind="loyalty_lock", title="锁定", dedup_key="k1",
                  detail={"arc": "mansion_era", "favor": 96})
    ev = ledger.all_events()[0]
    assert json.loads(ev["detail"])["favor"] == 96


def test_append_rejects_invalid(ledger):
    assert ledger.append(kind="", title="x", dedup_key="a") is False
    assert ledger.append(kind="x", title="", dedup_key="a") is False
    assert ledger.append(kind="x", title="y", dedup_key="") is False
    assert ledger.count() == 0


def test_latest_ordering_desc(ledger):
    for i, ts in enumerate(("2026-01-01 08:00:00", "2026-06-01 12:00:00",
                            "2026-03-01 09:00:00")):
        ledger.append(ts=ts, kind="custom", title=f"e{i}", dedup_key=f"k{i}")
    latest = ledger.latest(limit=2)
    assert [e["ts"] for e in latest] == ["2026-06-01 12:00:00", "2026-03-01 09:00:00"]


# ── 镜像函数 ──────────────────────────────────────────────────────

def test_mirror_scene_first_dedup():
    assert mirror_scene_first("KITCHEN", "mansion_era") is True
    assert mirror_scene_first("KITCHEN", "empire_era") is False, "同场景一生只记一次"
    assert mirror_scene_first("GARDEN", "mansion_era") is True


def test_mirror_milestone_daily_bucket():
    eng = HardStateEngine()
    assert mirror_milestone("loyalty_lock", engine=eng) is True
    assert mirror_milestone("loyalty_lock", engine=eng) is False, "同日同名场面只记一条"
    assert mirror_milestone("zero_start", engine=eng) is True


def test_mirror_letter_daily_bucket():
    assert mirror_letter("rem") is True
    assert mirror_letter("rem") is False
    assert mirror_letter("ram") is True


def test_mirror_arc_shift_per_turn():
    eng = HardStateEngine()
    assert mirror_arc_shift("mansion_era", "empire_era", turn_count=3, engine=eng)
    assert not mirror_arc_shift("mansion_era", "empire_era", turn_count=3, engine=eng)
    assert mirror_arc_shift("empire_era", "mansion_era", turn_count=4, engine=eng)


def test_mirror_silent_on_broken_db(monkeypatch, tmp_path):
    """账本不可写时镜像静默返回 False（绝不影响主流程）。"""
    blocker = tmp_path / "blocked"
    blocker.write_text("not a db")
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "sub" / "life.db"))
    (tmp_path / "sub").write_text("file blocks dir creation")
    reset_default()
    try:
        assert mirror_letter("rem") is False
    finally:
        reset_default()


# ── 引擎钩子（state.py 接线）────────────────────────────────────

def test_engine_locked_transition_mirrors_ledger():
    eng = HardStateEngine()
    eng._safe_add_favor(79)  # favor 15 → 94（<95，锁定未置位）
    eng.update("谢谢")  # 表扬 +2 → 96 ≥95：跃迁发生在本次 update 内，可被检测
    led = life_ledger.get_default_ledger()
    kinds = [e["kind"] for e in led.all_events()]
    assert "loyalty_lock" in kinds, "锁定跃迁应镜像人生账本"
    # 幂等：锁定后再次 update 不重复
    eng.update("谢谢你")
    assert sum(1 for e in led.all_events() if e["kind"] == "loyalty_lock") == 1


def test_engine_first_name_mirror():
    eng = HardStateEngine()
    eng.update("我叫小东")
    led = life_ledger.get_default_ledger()
    row = next(e for e in led.all_events() if e["kind"] == "first_name")
    assert "小东" in row["title"]


def test_engine_arc_switch_mirror():
    eng = HardStateEngine()
    eng.set_arc(StoryArc.EMPIRE_ERA)
    led = life_ledger.get_default_ledger()
    row = next(e for e in led.all_events() if e["kind"] == "arc_shift")
    assert "empire_era" in row["title"]


# ── 历史回填 ──────────────────────────────────────────────────────

def _store_with_history(tmp_path):
    store = ConversationStore(str(tmp_path / "conversations.db"))
    store.append("user", "你", "你好")              # 第 1 条 user
    store.append("rem", "蕾 姆", "蕾姆会陪着您。")
    store.append("user", "你", "我叫小东")           # 第 2 条 user
    store.append("rem", "蕾 姆", "小东大人，你好。")
    return store


def test_backfill_full_and_idempotent(tmp_path):
    store = _store_with_history(tmp_path)
    ledger = LifeLedger(str(tmp_path / "life.db"))
    events = [
        {"type": "locked", "summary": "第2次对话：好感抵达 95，忠诚锁定达成", "seq": 2},
        {"type": "favor_up", "summary": "第1次对话：好感提升", "seq": 1},  # 非人生事实，跳过
    ]
    r1 = backfill_from(conversation_store=store, memory_events=events,
                       first_letter_ts=time.time(), ledger=ledger)
    assert r1["added"] == 3, f"genesis+locked+first_letter（favor_up 不记），实际 {r1}"
    kinds = sorted(e["kind"] for e in ledger.all_events())
    assert kinds == ["first_letter", "genesis", "loyalty_lock"]
    locked = next(e for e in ledger.all_events() if e["kind"] == "loyalty_lock")
    user_times = store.user_message_times()
    assert locked["ts"] == user_times[1], "seq=2 → 第 2 条 user 消息时刻"
    genesis = next(e for e in ledger.all_events() if e["kind"] == "genesis")
    assert genesis["ts"] == store.oldest_message_time()

    r2 = backfill_from(conversation_store=store, memory_events=events,
                       first_letter_ts=time.time(), ledger=ledger)
    assert r2["added"] == 0 and ledger.count() == 3, "回填必须幂等（跑两遍账本不变）"


def test_backfill_empty_store(tmp_path):
    store = ConversationStore(str(tmp_path / "empty.db"))
    ledger = LifeLedger(str(tmp_path / "life.db"))
    r = backfill_from(conversation_store=store, memory_events=[], ledger=ledger)
    assert r["added"] == 1
    genesis = ledger.all_events()[0]
    assert genesis["kind"] == "genesis" and genesis["ts"], "空库 genesis 落今天"
