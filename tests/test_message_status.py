"""V14.0：消息软状态（recalled/deleted/failed）测试（无框架，直接运行，零 API 费用）。

覆盖（验收用例）：
- 迁移：新库建表含 status 列；旧库（无 status）打开后自动 ALTER 幂等
- update_status 幂等 + get_by_id 返回 status
- get_recent：normal+failed+recalled 展示，deleted 隐藏
- search：仅 normal 命中（FTS + LIKE 双通道）
- get_messages_since：排除 deleted
- bridge._restore_history_from_store：仅 normal 进 LLM 上下文

用法：python tests/test_message_status.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.conversation_store import ConversationStore
from llm.bridge import ReZeroLLMBridge


def _tmp_db() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    return path


def test_migration_new_db() -> None:
    """新库：建表即含 status 列。"""
    store = ConversationStore(db_path=_tmp_db())
    with sqlite3.connect(store.db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
    assert "status" in cols, f"新库应含 status 列: {cols}"


def test_migration_old_db() -> None:
    """旧库（无 status）：打开后自动 ALTER 补列，旧行 status='normal'。"""
    path = _tmp_db()
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL, sender TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        conn.execute("INSERT INTO messages (role, sender, content) VALUES ('user','你','旧消息')")
        conn.commit()
    store = ConversationStore(db_path=path)
    with sqlite3.connect(path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
        status = conn.execute("SELECT status FROM messages WHERE content='旧消息'").fetchone()[0]
    assert "status" in cols, f"迁移后应含 status 列: {cols}"
    assert status == "normal", f"旧行默认 normal，实际 {status}"


def test_update_status_and_get_by_id() -> None:
    store = ConversationStore(db_path=_tmp_db())
    mid = store.append("user", "你", "测试消息")
    assert store.update_status(mid, "recalled") is True
    rec = store.get_by_id(mid)
    assert rec is not None and rec["status"] == "recalled", f"get_by_id 应返回 status: {rec}"
    assert store.update_status(mid, "bogus") is False, "非法 status 应拒绝"
    assert store.update_status(99999, "deleted") is False, "不存在 id 应返回 False"


def test_get_recent_filters_deleted() -> None:
    """get_recent：normal+failed+recalled 可见，deleted 隐藏。"""
    store = ConversationStore(db_path=_tmp_db())
    m_normal = store.append("user", "你", "正常消息")
    m_failed = store.append("user", "你", "未送达消息")
    m_recalled = store.append("user", "你", "被撤回消息")
    m_deleted = store.append("user", "你", "被删除消息")
    store.update_status(m_failed, "failed")
    store.update_status(m_recalled, "recalled")
    store.update_status(m_deleted, "deleted")
    recent = store.get_recent(limit=10)
    ids = [r["id"] for r in recent]
    assert m_normal in ids and m_failed in ids and m_recalled in ids, f"应含 normal/failed/recalled: {ids}"
    assert m_deleted not in ids, f"deleted 应隐藏: {ids}"


def test_search_only_normal() -> None:
    """search：仅 normal 命中（LIKE 中文子串通道验证）。"""
    store = ConversationStore(db_path=_tmp_db())
    m_normal = store.append("user", "你", "这只野猫今天又来晒太阳了")
    m_failed = store.append("user", "你", "未送达的野猫消息")
    m_recalled = store.append("user", "你", "被撤回的野猫消息")
    m_deleted = store.append("user", "你", "被删除的野猫消息")
    store.update_status(m_failed, "failed")
    store.update_status(m_recalled, "recalled")
    store.update_status(m_deleted, "deleted")
    hits = store.search("野猫", limit=10)
    ids = [r["id"] for r in hits]
    assert m_normal in ids, f"normal 应命中: {ids}"
    assert m_failed not in ids and m_recalled not in ids and m_deleted not in ids, \
        f"非 normal 不应命中正文: {ids}"


def test_get_messages_since_excludes_deleted() -> None:
    store = ConversationStore(db_path=_tmp_db())
    store.append("user", "你", "第一句")
    m2 = store.append("user", "你", "第二句")
    store.append("user", "你", "第三句")
    store.update_status(m2, "deleted")
    rows = store.get_messages_since(None, limit=10)
    ids = [r["id"] for r in rows]
    assert m2 not in ids, f"deleted 不应进摘要统计: {ids}"
    assert len(ids) == 2


def test_restore_skips_non_normal() -> None:
    """bridge 恢复：仅 normal 进 LLM 上下文。"""
    store = ConversationStore(db_path=_tmp_db())
    store.append("user", "你", "正常提问")
    f_id = store.append("user", "你", "未送达提问")
    store.append("assistant", "双子", '【蕾姆】: "正常回复"')
    r_id = store.append("assistant", "双子", '【蕾姆】: "被撤回回复"')
    store.update_status(f_id, "failed")
    store.update_status(r_id, "recalled")
    bot = ReZeroLLMBridge(api_key="sk-test-not-used", conversation_store=store)
    # 构造时已 restore；再手动恢复一次验证过滤
    bot._restore_history_from_store()
    contents = [m["content"] for m in bot.history]
    assert any("正常提问" in c for c in contents), f"normal 应进入 history: {contents}"
    assert any("正常回复" in c for c in contents), f"normal assistant 应进入: {contents}"
    assert not any("未送达提问" in c for c in contents), f"failed 不应进入: {contents}"
    assert not any("被撤回回复" in c for c in contents), f"recalled 不应进入: {contents}"


def test_recall_turn_links_same_turn() -> None:
    """V14.0.1：撤用户句连带同轮助手，不连锁后续轮。"""
    store = ConversationStore(db_path=_tmp_db())
    u1 = store.append("user", "你", "我的生日是3月15日")
    a1 = store.append("assistant", "双子", '【蕾姆】: "记住了，3月15日"')
    u2 = store.append("user", "你", "然后呢")
    a2 = store.append("assistant", "双子", '【蕾姆】: "继续聊聊"')
    ids = store.recall_turn(u1)
    assert sorted(ids) == sorted([u1, a1]), f"应连带同轮助手 a1: {ids}"
    assert store.get_by_id(u1)["status"] == "recalled"
    assert store.get_by_id(a1)["status"] == "recalled"
    assert store.get_by_id(u2)["status"] == "normal", "不应连锁后续用户句"
    assert store.get_by_id(a2)["status"] == "normal", "不应连锁后续助手句"


def test_recall_turn_history_clean() -> None:
    """V14.0.1：撤用户句后 history 不含用户原文与同轮助手原文（后续轮保留）。"""
    store = ConversationStore(db_path=_tmp_db())
    u1 = store.append("user", "你", "我的生日是3月15日")
    a1 = store.append("assistant", "双子", '【蕾姆】: "记住了，3月15日"')
    u2 = store.append("user", "你", "之后的正常对话")
    a2 = store.append("assistant", "双子", '【蕾姆】: "正常回复"')
    store.recall_turn(u1)
    bot = ReZeroLLMBridge(api_key="sk-test-not-used", conversation_store=store)
    contents = [m["content"] for m in bot.history]
    assert not any("3月15日" in c for c in contents), f"用户原文不应进上下文: {contents}"
    assert not any("记住了" in c for c in contents), f"同轮助手原文不应进: {contents}"
    assert any("正常对话" in c for c in contents), f"后续轮应保留: {contents}"


def main() -> int:
    tests = [
        ("迁移：新库含 status 列", test_migration_new_db),
        ("迁移：旧库 ALTER 幂等 + 旧行 normal", test_migration_old_db),
        ("update_status 幂等 + get_by_id 含 status", test_update_status_and_get_by_id),
        ("get_recent 过滤 deleted（展示 normal+failed+recalled）", test_get_recent_filters_deleted),
        ("search 仅 normal 命中", test_search_only_normal),
        ("get_messages_since 排除 deleted", test_get_messages_since_excludes_deleted),
        ("bridge restore 仅 normal 进上下文", test_restore_skips_non_normal),
        ("撤回连带同轮助手 V14.0.1", test_recall_turn_links_same_turn),
        ("撤后 history 不含原文 V14.0.1", test_recall_turn_history_clean),
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
