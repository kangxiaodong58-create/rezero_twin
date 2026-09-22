"""V16.1（M1+M2）状态持久化回归测试 —— 存档写读对称 + 原子写/损坏恢复。

架构审批（2026-09-22）强制项：
- **M2**：引擎状态单源序列化。locked / oni_stage / witch_scent / turn_count /
  consecutive_* 必须在重启后存活（V16.0 及以前：locked 写了不读，
  oni_stage/witch_scent/turn_count 根本不落盘 → 重启归零）。
- **M1**：memory.json 原子写 + 损坏三级降级（备份恢复 → 留证告警 → 默认值），
  绝不静默回落默认值。
- **M5**：原一次性探针（A/B 假设）固化为回归测试，不再「跑完即删」。
- A3：上下文摘要真源收敛（此前 engine.context_emotions 只读不写 →
  「近期情绪倾向」恒为「平稳」）。

全部本地，零 API 调用。
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.memory_store import MemoryStore  # noqa: E402
from shared.state import HardStateEngine, OniStage, StoryArc  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return MemoryStore(root_dir=str(tmp_path))


def test_memory_store_resolves_data_dir_late(monkeypatch, tmp_path) -> None:
    """存档目录必须「调用时」解析。

    V16.1 根因修复：此前 memory_store 在 import 期 `from .config import get_data_dir`，
    测试对 `shared.config.get_data_dir` 打补丁无效 → smoke_test 的
    test_world_state_docx_compat 直接写真实 data/memory.json（隐藏的隔离漏洞）。
    """
    from shared import config
    monkeypatch.setattr(config, "get_data_dir", lambda: str(tmp_path))
    assert MemoryStore().path == str(tmp_path / "memory.json")


# ── M2：引擎状态单源序列化 ────────────────────────────────────────

def test_engine_roundtrip_all_persisted_fields() -> None:
    """全部存档字段：to_dict → from_dict 逐项等价。"""
    e = HardStateEngine()
    e._safe_add_favor(85)          # favor 100 + 忠诚锁定
    e.update("解放鬼角")            # oni EMERGING / aftermath 1 / turn_count 1
    e.update("我好累")             # 连续负面 +1 + 情感轨迹「负面」
    e.witch_scent = 3
    e.is_reunion = True
    e.breaker_triggered = True
    e.user_name = "小东"
    e.profile.context.add_topic("明天要交的作业")

    e2 = HardStateEngine.from_dict(e.to_dict())
    for attr in ("arc", "favor", "locked", "independence", "recovery", "ram_favor",
                 "oni_stage", "oni_aftermath", "witch_scent", "user_name",
                 "consecutive_negative", "consecutive_procrastinate",
                 "is_reunion", "breaker_triggered", "turn_count", "events"):
        assert getattr(e2, attr) == getattr(e, attr), f"{attr} 往返不等价"
    assert e2.profile.context.emotional_trajectory == e.profile.context.emotional_trajectory
    assert e2.profile.context.open_topics == e.profile.context.open_topics


def test_locked_oni_turn_count_survive_restart() -> None:
    """M2 主验收：重启后 locked / 鬼化 / 轮次必须存活（旧版归零）。"""
    e = HardStateEngine()
    e._safe_add_favor(85)
    e.update("解放鬼角")              # 鬼化 EMERGING / aftermath 1
    e.witch_scent = 3
    e.consecutive_negative = 1        # 直接置位：本用例只验证「存档携带」，不验证衰减
    saved = e.to_dict()

    fresh = HardStateEngine()          # 模拟一次全新进程
    fresh.apply_dict(saved)
    assert fresh.locked is True, "忠诚锁定必须跨重启保留"
    assert fresh.turn_count == e.turn_count == 1, "轮次计数必须跨重启保留"
    assert fresh.oni_stage is OniStage.EMERGING, "鬼化阶段必须跨重启保留"
    assert fresh.witch_scent == e.witch_scent == 3
    assert fresh.consecutive_negative == e.consecutive_negative == 1


def test_legacy_flat_format_still_restores() -> None:
    """旧平铺格式（V16.0 及以前）仍可恢复；缺字段回落默认不炸。"""
    legacy = {
        "mode": "llm", "arc": "empire_era", "favor": 42, "ram_favor": 30,
        "independence": 0.5, "recovery": 0.3, "locked": True, "user_name": "小东",
        "events": [{"type": "name_first", "desc": "命名", "date": "2026-01-01"}],
        "chat_history": [], "world_state": {},
    }
    e = HardStateEngine(arc=StoryArc.EMPIRE_ERA)
    e.apply_dict(legacy)
    assert e.arc is StoryArc.EMPIRE_ERA
    assert (e.favor, e.ram_favor, e.locked, e.user_name) == (42, 30, True, "小东")
    assert e.independence == 0.5 and e.recovery == 0.3
    assert len(e.events) == 1
    assert e.oni_stage is OniStage.NONE and e.turn_count == 0, "缺字段应回落默认"


def test_arc_restore_keeps_saved_recovery_independence() -> None:
    """篇章恢复不得被构造期副作用（empire → 归零）覆盖存档值。"""
    e = HardStateEngine(arc=StoryArc.EMPIRE_ERA)
    e.recovery, e.independence = 0.4, 0.9
    e2 = HardStateEngine.from_dict(e.to_dict(), arc=StoryArc.MANSION_ERA)
    assert e2.arc is StoryArc.EMPIRE_ERA
    assert (e2.recovery, e2.independence) == (0.4, 0.9)


def test_to_dict_json_serializable() -> None:
    """存档必须可直接 json.dump（无枚举对象泄漏）。"""
    e = HardStateEngine()
    e.update("解放鬼角")
    json.dumps(e.to_dict(), ensure_ascii=False)


def test_apply_dict_tolerates_garbage() -> None:
    """坏字段类型不得抛异常（存档被手改/降级仍能启动）。"""
    e = HardStateEngine()
    e.apply_dict({"favor": "不是数字", "oni_stage": "不存在", "events": "不是列表",
                  "profile": 42, "arc": "unknown_arc"})
    assert e.favor == 15 and e.oni_stage is OniStage.NONE and e.events == []
    e.apply_dict(None)          # 空档
    e.apply_dict({})


# ── A3：上下文摘要真源收敛 ────────────────────────────────────────

def test_context_summary_reflects_real_emotions() -> None:
    """A3 回归：摘要首段此前恒为「平稳」（死字段），现须反映真实情感轨迹。"""
    e = HardStateEngine()
    assert not hasattr(e, "context_emotions"), "死字段应已删除"
    t = e.update("我好累")
    head = t.context_summary.split("|")[0]
    assert "负面" in head, f"情绪倾向应反映真实轨迹，实际: {head}"
    snap = e.snapshot()
    assert "负面" in snap.context_summary.split("|")[0]
    assert e.snapshot().context_summary == t.context_summary


# ── M1：原子写与损坏恢复 ──────────────────────────────────────────

def test_memory_store_atomic_write_and_backup(store) -> None:
    store.save({"favor": 42})
    assert not os.path.exists(store.path + ".tmp"), ".tmp 应已被 os.replace 消费"
    assert store.load()["favor"] == 42
    assert store.load()["schema_version"] == 2
    store.save({"favor": 43})
    assert os.path.isfile(store.backup_path), "第二次保存应留下上一代备份"
    with open(store.backup_path, encoding="utf-8") as f:
        assert json.load(f)["favor"] == 42


def test_memory_store_recovers_from_backup(store) -> None:
    """主档损坏 → 从 .bak 恢复并写回；绝不静默回默认值。"""
    store.save({"favor": 42})
    store.save({"favor": 43})               # .bak = 42
    with open(store.path, "w", encoding="utf-8") as f:
        f.write('{"favor": 43, "events": [')  # 模拟写盘中断留下的残档

    data = store.load()
    assert data["favor"] == 42, "损坏主档应从备份恢复（不是默认值 15）"
    ok, repaired = MemoryStore._read_json(store.path)
    assert ok and repaired["favor"] == 42, "恢复后应原子写回修复主档"
    assert not glob.glob(store.path + ".corrupt-*"), "可恢复时不应留 .corrupt 证据"


def test_memory_store_both_corrupt_keeps_evidence(store, caplog) -> None:
    """主档与备份皆坏 → 保留坏档证据 + 告警，才回落默认值。"""
    store.save({"favor": 42})
    for path in (store.path, store.backup_path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("{ 坏档 ")
    with caplog.at_level(logging.WARNING, logger="rezero.memory_store"):
        data = store.load()
    assert data["favor"] == 15, "双坏才回落默认值"
    assert glob.glob(store.path + ".corrupt-*"), "坏档证据必须保留"
    assert not os.path.exists(store.path), "坏档应被改名移走"
    assert any("损坏" in r.getMessage() for r in caplog.records), "必须告警"


def test_memory_store_interrupted_write_keeps_previous(store) -> None:
    """半截 .tmp（写盘中断）不得影响主档。"""
    store.save({"favor": 42})
    with open(store.path + ".tmp", "w", encoding="utf-8") as f:
        f.write('{"favor": 99')
    assert store.load()["favor"] == 42


# ── GUI 集成：存档 ↔ 恢复端到端 ───────────────────────────────────

@pytest.fixture
def gui_env(monkeypatch, tmp_path):
    """离屏窗口 + 全隔离存储（临时 memory.json / conv.db / life.db 由 conftest 兜底）。"""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used")
    import gui
    from shared.conversation_store import ConversationStore
    from PySide6.QtWidgets import QApplication

    gui.QMessageBox.warning = lambda *a, **k: None
    monkeypatch.setattr(gui, "MemoryStore", lambda: MemoryStore(root_dir=str(tmp_path)))
    monkeypatch.setattr(gui, "ConversationStore",
                        lambda: ConversationStore(db_path=str(tmp_path / "conv.db")))
    QApplication.instance() or QApplication([])
    return gui, tmp_path


def test_gui_save_restore_roundtrip(gui_env) -> None:
    """V16.1 端到端：_save_state 双写（新 engine 键 + 旧平铺键）→ 重建窗口恢复。"""
    gui, tmp_path = gui_env
    win = gui.TwinChatApp()
    engine = win.engine
    engine._safe_add_favor(85)
    engine.update("解放鬼角")
    win._save_state()

    raw = json.loads((tmp_path / "data" / "memory.json").read_text(encoding="utf-8"))
    assert isinstance(raw.get("engine"), dict), "应写入新格式 engine 键"
    assert raw["engine"]["locked"] is True
    assert raw["engine"]["oni_stage"] == "EMERGING"
    assert raw["locked"] is True and raw["favor"] == 100, "旧平铺键应保持双写"

    win2 = gui.TwinChatApp()          # 模拟重启
    e2 = win2.engine
    assert e2.locked is True and e2.favor == 100, "锁定态与好感必须恢复"
    assert e2.oni_stage.name == "EMERGING", "鬼化阶段必须恢复"
    assert e2.turn_count == engine.turn_count
    win.close()
    win2.close()
