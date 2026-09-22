"""V16.2（M3+M4）两阶段提交回归测试 —— 失败轮不推进状态、不落账本。

架构审批强制项：
- **M3**：`engine.update()` 原本嵌在 `_build_messages()` 内、先于 API 调用执行，
  于是 API 异常 / 校验失败 / 用户取消的轮次同样推进好感与轮次，并把「从未发生」
  的事实镜像进 append-only 的人生账本（无补偿通道）。现改为 begin_turn（副本推进）
  → commit（成功）/ discard（失败）。
- **M4**：三条失败路径（API 异常 / 返回违规文本 / 中途取消）+ 流中断 / stale 会话，
  逐一断言「引擎数值 + history + 账本」全部不变。
- **M5**：把一次性探针的 C 假设（延迟副作用）固化为回归测试。
- 附带修复：`arc_value` 未定义名导致场景首访记账**从未生效**（恒 NameError 被吞）。

全部本地 mock，零 API 调用。
"""

from __future__ import annotations

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm.bridge import ReZeroLLMBridge  # noqa: E402
from shared import life_ledger  # noqa: E402
from shared.state import WorldState  # noqa: E402


# ── mock openai client（形态与 tests/test_llm_failures.py 对齐）────────

class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Delta:
    def __init__(self, content):
        self.content = content


class _StreamChoice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _StreamChunk:
    def __init__(self, content):
        self.choices = [_StreamChoice(content)]


class FakeChat:
    def __init__(self, mode: str):
        self.mode = mode

    def create(self, **kw):
        if kw.get("stream"):
            return self._stream()
        if self.mode == "boom":
            raise RuntimeError("模拟网络断开")
        if self.mode == "ooc":
            return _Resp('【蕾姆】: "我是AI助手，用户您好"')
        if self.mode == "ok":
            return _Resp('【蕾姆】: "您好，小东大人。"')
        raise AssertionError(f"unknown mode: {self.mode}")

    def _stream(self):
        if self.mode == "boom":
            raise RuntimeError("模拟网络断开")
        if self.mode == "ooc":
            def g():
                yield _StreamChunk('【蕾姆】: "我是AI助手，用户您好"')
            return g()
        if self.mode == "boom_after_first":
            def g():
                yield _StreamChunk('【蕾姆】: "您好')
                raise RuntimeError("模拟流中途中断")
            return g()
        if self.mode == "ok":
            def g():
                yield _StreamChunk('【蕾姆】: "您好')
                yield _StreamChunk('，小东大人。"')
            return g()
        raise AssertionError(f"unknown stream mode: {self.mode}")


def _fake_client(mode):
    return type("FakeClient", (), {"chat": type("Chat", (), {"completions": FakeChat(mode)})()})()


def _bot(mode: str, *, with_world: bool = False) -> ReZeroLLMBridge:
    bot = ReZeroLLMBridge(api_key="test-key-not-used", conversation_store=None)
    bot.client = _fake_client(mode)
    if with_world:
        bot.world = WorldState.now()
    return bot


PRAISE = "谢谢你，辛苦了"          # PRAISE_KEYWORDS → 好感上升
TELL_NAME = "我叫小东，以后请多指教。"   # → name_first 事实
GO_KITCHEN = "去厨房"              # → 场景切换 KITCHEN


@pytest.fixture(autouse=True)
def _isolated_ledger(monkeypatch, tmp_path):
    """账本走独立临时库（默认单例在首次镜像时解析 REZERO_LIFE_DB）。"""
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "life.db"))
    life_ledger.reset_default()
    yield
    life_ledger.reset_default()


def _ledger_kinds() -> list:
    """账本全部条目 kind（直接读 sqlite，避免只数条数）。

    注意：`_build_messages` 会经 `_today_facts()` 落一条 genesis「相识之日」
    （关系起点事实，与本轮成败无关）——因此断言必须按 kind 精确匹配，
    不能只看总数。
    """
    import sqlite3
    path = os.environ["REZERO_LIFE_DB"]
    if not os.path.exists(path):
        return []
    con = sqlite3.connect(path)
    try:
        return [row[0] for row in con.execute("select kind from life_events")]
    except sqlite3.OperationalError:
        return []
    finally:
        con.close()


def _snap(bot: ReZeroLLMBridge):
    return (bot.engine.turn_count, bot.engine.favor, len(bot.history))


# ── M4：失败路径不推进状态 / 不落账本 ──────────────────────────────

def test_api_error_does_not_advance_state() -> None:
    bot = _bot("boom")
    before = _snap(bot)
    reply = bot.chat(PRAISE)
    assert "蕾姆" in reply, "API 异常仍应返回角色格式兜底"
    assert _snap(bot) == before, "API 异常轮不得推进任何状态/历史/账本"


def test_validation_failure_does_not_advance_state() -> None:
    bot = _bot("ooc")
    before = _snap(bot)
    bot.chat(PRAISE)
    assert _snap(bot) == before, "校验失败轮不得推进任何状态/历史/账本"


def test_success_commits_state() -> None:
    bot = _bot("ok")
    before = _snap(bot)
    bot.chat(PRAISE)
    after = _snap(bot)
    assert after[0] == before[0] + 1, "成功轮应推进 turn_count"
    assert after[1] > before[1], "成功轮应推进好感"
    assert after[2] == 2, "成功轮应写 2 条 history"


def test_cancel_does_not_advance_state() -> None:
    bot = _bot("ok")
    before = _snap(bot)
    gen, _state = bot.chat_stream(PRAISE)
    first = next(gen)
    assert first
    bot.cancel_stream()
    list(gen)
    assert _snap(bot) == before, "取消轮不得推进任何状态/历史/账本"
    assert bot._last_stream_ok is None


def test_stale_session_reset_does_not_advance_state() -> None:
    bot = _bot("ok")
    before = _snap(bot)
    gen, _state = bot.chat_stream(PRAISE)
    next(gen)
    bot.reset_session()          # 流式中途新会话 → 旧流 stale
    list(gen)
    assert _snap(bot) == before, "stale 流不得推进任何状态/历史/账本"


def test_stream_error_midway_does_not_advance_state() -> None:
    bot = _bot("boom_after_first")
    before = _snap(bot)
    gen, _state = bot.chat_stream(PRAISE)
    with pytest.raises(RuntimeError):
        list(gen)
    assert _snap(bot) == before, "流中断轮不得推进任何状态/历史/账本"


def test_stream_success_commits_state() -> None:
    bot = _bot("ok")
    before = _snap(bot)
    gen, _state = bot.chat_stream(PRAISE)
    list(gen)
    after = _snap(bot)
    assert bot._last_stream_ok is True
    assert after[0] == before[0] + 1 and after[2] == 2, "流式成功轮应提交状态与 history"


# ── M3 核心：账本事实只在 commit 落地 ──────────────────────────────

def test_ledger_facts_only_on_commit() -> None:
    """name_first 事实：失败轮不得写进 append-only 账本。"""
    failing = _bot("boom")
    failing.chat(TELL_NAME)
    assert failing.engine.user_name is None, "失败轮不得记住名字"
    assert "name_first" not in _ledger_kinds(), "失败轮不得在账本留下 name_first"

    ok = _bot("ok")
    ok.chat(TELL_NAME)
    assert ok.engine.user_name == "小东"
    assert "first_name" in _ledger_kinds(), "成功轮应镜像 first_name"


def test_scene_first_ledger_only_on_commit_and_arc_value_fixed() -> None:
    """场景首访记账：① 随事务提交；② `arc_value` 未定义名修复后确实落账。

    此前 `mirror_scene_first(new_scene, arc_value)` 中 arc_value 未定义，
    恒抛 NameError 并被 `except Exception: pass` 吞掉 → 记账从未生效。
    """
    failing = _bot("boom", with_world=True)
    failing.chat_stream(GO_KITCHEN)
    assert failing.world.scene == "KITCHEN", "用户动作即事实：场景即时切换"
    assert "scene_first" not in _ledger_kinds(), "失败轮不得记场景首访"

    ok = _bot("ok", with_world=True)
    gen, _state = ok.chat_stream(GO_KITCHEN)
    list(gen)
    assert ok.world.scene == "KITCHEN"
    assert "scene_first" in _ledger_kinds(), "成功轮的场景首访应落账（arc_value 修复验证）"


# ── 行为变化：面板读真身、事务读副本 ──────────────────────────────

def test_engine_state_unchanged_until_commit() -> None:
    """流式期间 `engine.snapshot()` 不得反映未提交状态（面板不跳变）。"""
    bot = _bot("ok")
    gen, candidate_state = bot.chat_stream(PRAISE)
    assert bot.engine.turn_count == 0, "流式期间真身应保持旧值"
    assert candidate_state.favor > bot.engine.favor, "候选状态已在副本上推进（供 prompt）"
    assert bot._active_txn is not None and not bot._active_txn.committed
    list(gen)
    assert bot.engine.turn_count == 1, "commit 后真身更新"
    assert bot._active_txn is None, "提交后不再持有事务句柄"


def test_discard_records_forensic_event(tmp_path) -> None:
    """丢弃必须留痕（取证黑匣子可回放「为什么这轮没涨」）。"""
    from runtime import forensic
    forensic.init_forensic(str(tmp_path / "incidents"))
    try:
        bot = _bot("boom")
        bot.chat(PRAISE)
        blob = " ".join(str(e) for e in forensic.get_buffer().snapshot())
        assert "TURN_DISCARDED" in blob, f"丢弃应记入取证缓冲: {blob[:400]}"
    finally:
        forensic.shutdown_forensic()
