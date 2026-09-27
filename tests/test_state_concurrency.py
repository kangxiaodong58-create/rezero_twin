"""SPEC-20260922-21（A10）：跨线程提交收口判据。

三项判据（对照 SPEC §测试方式）：
1. **撕裂读**：写线程成对写 `favor`/`ram_favor`，读线程反复 `snapshot()`，断言恒等
   ——修复前 20000 次迭代即稳定复现（先红留证见 `docs/devlog/A10并发收口_*.md`），修复后 0；
2. **陈旧整快照回写**（确定性，无线程）：轮内主线程改引擎 ⇒ commit 后必须保住；
3. **前置修正**：`apply_dict` 的 `user_name` 走「键存在性」语义（缺键保持 / 显式 None 置空）。
"""

from __future__ import annotations

import sys
import threading

from shared.state import HardStateEngine, StoryArc


# ── 1. 撕裂读（A10 主项）────────────────────────────


def test_no_torn_read_between_paired_fields() -> None:
    """成对字段在并发读写下必须恒等（加锁前可撕裂——先红后绿留证见 devlog）。"""
    engine = HardStateEngine()
    iterations = 20000  # 修复前 20000 次即稳定复现撕裂；修复后为 0
    tears: list = []
    done = threading.Event()

    def writer() -> None:
        for i in range(1, iterations + 1):
            engine.apply_dict({"favor": i, "ram_favor": i})

    def reader() -> None:
        while not done.is_set():
            s = engine.snapshot()
            if s.favor != s.ram_favor:
                tears.append((s.favor, s.ram_favor))
                if len(tears) >= 5:
                    return

    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)  # F21-4：压缩切换粒度以放大窗口（用后还原）
    try:
        writer_t = threading.Thread(target=writer)
        reader_t = threading.Thread(target=reader)
        writer_t.start()
        reader_t.start()
        writer_t.join(timeout=60)
        done.set()
        reader_t.join(timeout=10)
    finally:
        sys.setswitchinterval(old_interval)

    assert not writer_t.is_alive() and not reader_t.is_alive(), "探针线程未按时退出"
    assert not tears, f"观测到撕裂读（favor/ram_favor 不一致）：{tears[:5]}"


def test_snapshot_is_value_constructed_and_events_detached() -> None:
    """F21-1：`snapshot()` 返回新构造的 TwinState；`events` 亦为独立列表（不共享写入）。"""
    engine = HardStateEngine()
    s1 = engine.snapshot()
    engine.apply_dict({"favor": 99})
    assert s1.favor != 99, "旧快照不应随后续写入而变化（按值构造）"
    engine.events.append({"kind": "probe"})
    assert s1.events == [], "snapshot 的 events 应为独立列表"


# ── 2. 陈旧整快照回写（确定性）──────────────────────


def test_commit_preserves_concurrent_change_outside_turn() -> None:
    """轮内主线程改 `arc` ⇒ commit 后必须保住（修复前会被候选快照整体回写覆盖）。"""
    engine = HardStateEngine()
    before_turn_count = engine.turn_count
    txn = engine.begin_turn("今天我们聊聊吧")
    engine.set_arc(StoryArc.LATE_ARC)  # 轮内别处修改（模拟 set_arc / recover）
    txn.commit()
    assert engine.arc is StoryArc.LATE_ARC, "轮内别处修改被陈旧快照回写覆盖了"
    assert engine.turn_count == before_turn_count + 1, "本轮自身改动应正常落地"


def test_commit_delta_covers_turn_changes() -> None:
    """delta 必须覆盖本轮真实改动（否则等于没提交）。"""
    engine = HardStateEngine()
    base = engine.to_dict()
    txn = engine.begin_turn("解放鬼角")
    txn.commit()
    now = engine.to_dict()
    changed = {k for k in now if now[k] != base[k]}
    assert changed, "本轮应至少改动若干字段"
    assert now["turn_count"] == base["turn_count"] + 1


# ── 3. 前置修正：user_name 键语义 ───────────────────


def test_user_name_key_semantics() -> None:
    """缺键 → 保持当前值；显式 `None`/空串 → 置空（delta 写回安全，F21-2）。"""
    engine = HardStateEngine()
    engine.apply_dict({"user_name": "小东"})
    assert engine.user_name == "小东" and engine.profile.name == "小东"

    engine.apply_dict({"favor": 50})  # 缺键 ⇒ 保持
    assert engine.user_name == "小东" and engine.profile.name == "小东"

    engine.apply_dict({"user_name": None})  # 显式置空
    assert engine.user_name is None and engine.profile.name is None

    engine.apply_dict({"user_name": "再次设置"})
    engine.apply_dict({})  # 空字典早退
    assert engine.user_name == "再次设置"


def test_archive_roundtrip_unchanged() -> None:
    """存档往返不受本批影响：全量字典恢复语义与修复前一致。"""
    src = HardStateEngine()
    src.update("我叫小东")
    src.apply_dict({"user_name": "小东"})
    snapshot_before = src.to_dict()
    dst = HardStateEngine.from_dict(snapshot_before)
    assert dst.to_dict() == snapshot_before
