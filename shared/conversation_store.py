"""SQLite 对话流水存储（解耦 LLM 上下文）。

职责：
- 保存所有原始对话（user / rem / ram / system）
- 支持分页读取（GUI 翻历史）
- FTS5 全文搜索
- 与 MemoryStore（JSON 持久化硬状态）各自独立
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import get_data_dir


class ConversationStore:
    """SQLite 对话流水。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_dir = get_data_dir()
            db_path = os.path.join(db_dir, "conversations.db")
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,        -- 'user' | 'rem' | 'ram' | 'system'
                    sender TEXT NOT NULL,       -- '你' | '蕾 姆' | '拉 姆' | '系统'
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    status TEXT NOT NULL DEFAULT 'normal'  -- V14.0: normal|recalled|deleted|failed
                )
            """)
            # V14.0：旧库迁移——补 status 列（幂等，PRAGMA 检查后 ALTER）
            cols = [r[1] for r in conn.execute("PRAGMA table_info(messages)")]
            if "status" not in cols:
                conn.execute("ALTER TABLE messages ADD COLUMN status TEXT NOT NULL DEFAULT 'normal'")
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(content, content_rowid='id')
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content)
                    VALUES ('delete', old.id, old.content);
                END
            """)
            # V11.6.5: session 摘要表（规则生成，不调 LLM）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_summaries (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at        TEXT NOT NULL,
                    ended_at          TEXT NOT NULL,
                    turn_count        INTEGER NOT NULL DEFAULT 0,
                    summary_text      TEXT NOT NULL DEFAULT '',
                    last_user_excerpt TEXT NOT NULL DEFAULT '',
                    msg_start_id      INTEGER,
                    msg_end_id        INTEGER,
                    created_at        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.commit()

    def append(self, role: str, sender: str, content: str) -> int:
        """追加一条消息，返回 message_id。"""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO messages (role, sender, content) VALUES (?, ?, ?)",
                (role, sender, content),
            )
            conn.commit()
            return cur.lastrowid

    def oldest_message_time(self) -> str:
        """最早一条消息的 created_at（任何 status——历史即证据）。无消息返回 ""。"""
        with self._connect() as conn:
            row = conn.execute("SELECT MIN(created_at) FROM messages").fetchone()
            return (row[0] or "") if row else ""

    def user_message_times(self) -> List[str]:
        """全部 user 消息时刻（按 id 升序）——回填引擎事件 seq → 时刻映射用。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT created_at FROM messages WHERE role = 'user' ORDER BY id ASC"
            ).fetchall()
            return [r[0] for r in rows]

    def update_status(self, message_id: int, status: str) -> bool:
        """V14.0：软状态更新（normal/recalled/deleted/failed），返回是否命中。

        撤回/删除/失败态均为软状态：保留行与 id，仅改 status（FTS 行不动，
        命中与否由查询侧 status 过滤控制）。
        """
        if status not in ("normal", "recalled", "deleted", "failed"):
            return False
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE messages SET status = ? WHERE id = ?", (status, message_id)
            )
            conn.commit()
            return cur.rowcount > 0

    def recall_turn(self, message_id: int) -> List[int]:
        """V14.0.1：撤回用户句并连带「同一次发送产生的助手回复」标为 recalled。

        同轮 = message_id 之后、下一条 user 消息之前的 rem/ram/assistant 记录
        （system 消息不连带；后续轮次不连锁——只处理这一轮）。
        返回所有被标为 recalled 的 id（含用户句本身）。
        """
        with self._connect() as conn:
            next_user = conn.execute(
                "SELECT MIN(id) FROM messages WHERE id > ? AND role = 'user'",
                (message_id,),
            ).fetchone()[0]
            upper = next_user if next_user is not None else (1 << 31)
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM messages WHERE id > ? AND id < ? "
                "AND role IN ('rem','ram','assistant') AND status = 'normal'",
                (message_id, upper),
            ).fetchall()]
            ids.append(message_id)
            conn.executemany(
                "UPDATE messages SET status = 'recalled' WHERE id = ?",
                [(i,) for i in ids],
            )
            conn.commit()
            return ids

    def get_recent(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """分页读取最近消息（按 id 升序返回，最旧在前、最新在末尾）。

        内部 SQL 先 ORDER BY id DESC 取最近 limit 条，再 reversed 转为升序，
        便于 GUI 直接追加渲染。offset 基于 DESC 偏移（即跳过最新的 offset 条）。

        V14.0 三条查询的 status 过滤差异（务必保持一致）：
        - get_recent / get_messages_since（GUI 展示路径，主聊天+回忆浮层）：
          normal + failed + recalled，排除 deleted
        - search（全文/子串检索）：仅 normal（撤回/删除/未送达均不命中正文）
        - bridge._restore_history_from_store（LLM 上下文）：仅 normal
          （failed/recalled/deleted 均不进 Prompt）
        """
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, sender, content, created_at, status "
                "FROM messages WHERE status IN ('normal','failed','recalled') "
                "ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """混合搜索：FTS5 全文（快路径）+ LIKE 子串（CJK 兜底），id 去重合并。

        V10.11：修复中文检索精度。FTS5 的 unicode61 tokenizer 不对 CJK 逐字
        分词，连续中文是一个完整 token，导致搜「野猫」「有只」等子串无法命中
        （只有被标点分隔的字如「哇」才能独立命中）。新增 LIKE 子串兜底通道，
        保证任意 CJK 子串均可命中。

        - FTS5 处理英文/空格分词文本（token 精确匹配，rank 排序）
        - LIKE 处理 CJK 任意子串（unicode61 无法分词的短板）
        - 两路结果按 id 去重，FTS 优先，最终按 id DESC 统一排序
        - FTS 查询含特殊字符时 try-except 隔离，LIKE 仍正常兜底
        """
        query = (query or "").strip()
        if not query:
            return []

        # ── LIKE 特殊字符转义（% _ \ 是 LIKE 通配符/转义符）──
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like_pattern = f"%{escaped}%"

        with self._connect() as conn:
            # 通道 1：FTS5 快路径（try-except 隔离，FTS 语法异常不致命）
            # V14.0：仅 status='normal' 命中（撤回/删除/未送达正文不可搜）
            fts_rows: List[sqlite3.Row] = []
            try:
                fts_rows = conn.execute(
                    "SELECT m.id, m.role, m.sender, m.content, m.created_at, m.status "
                    "FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                    "WHERE messages_fts MATCH ? AND m.status = 'normal' ORDER BY rank LIMIT ?",
                    (query, limit),
                ).fetchall()
            except Exception:
                pass

            # 通道 2：LIKE 子串兜底（CJK 任意子串命中；同样仅 normal）
            like_rows = conn.execute(
                "SELECT id, role, sender, content, created_at, status "
                "FROM messages WHERE content LIKE ? ESCAPE '\\' AND status = 'normal' "
                "ORDER BY id DESC LIMIT ?",
                (like_pattern, limit),
            ).fetchall()

        # ── 合并去重：FTS 优先，LIKE 补充，按 id 去重 ──
        seen_ids: set = set()
        merged: List[Dict[str, Any]] = []
        for row in list(fts_rows) + list(like_rows):
            rid = row["id"]
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            merged.append(dict(row))

        # 最终按 id DESC 统一排序（最新优先），截断至 limit
        merged.sort(key=lambda r: r["id"], reverse=True)
        return merged[:limit]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

    def get_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """按 id 取单条消息记录（V10.12：定位降级摘要用；V14.0：撤回窗口判断用）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, role, sender, content, created_at, status "
                "FROM messages WHERE id = ?",
                (message_id,),
            ).fetchone()
        return dict(row) if row else None

    def migrate_from_json(self, chat_history: List[Dict[str, Any]]) -> int:
        """从旧 JSON chat_history 迁移到 SQLite（去重）。"""
        existing = self.count()
        if existing > 0:
            return 0
        migrated = 0
        for item in chat_history:
            role = item.get("role", "system")
            sender = item.get("sender", {"rem": "蕾 姆", "ram": "拉 姆", "user": "你"}.get(role, role))
            content = item.get("text", item.get("content", ""))
            if content:
                self.append(role, sender, content)
                migrated += 1
        return migrated

    # ── V11.6.5: session 摘要（规则生成，不调 LLM）──

    def save_session_summary(
        self,
        started_at: str,
        ended_at: str,
        turn_count: int,
        summary_text: str,
        last_user_excerpt: str,
        msg_start_id: Optional[int] = None,
        msg_end_id: Optional[int] = None,
    ) -> int:
        """保存一条 session 摘要，返回 summary id。"""
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO session_summaries "
                "(started_at, ended_at, turn_count, summary_text, "
                " last_user_excerpt, msg_start_id, msg_end_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (started_at, ended_at, turn_count, summary_text,
                 last_user_excerpt, msg_start_id, msg_end_id),
            )
            conn.commit()
            return cur.lastrowid

    def get_last_session_summary(self) -> Optional[Dict[str, Any]]:
        """取最近一条 session 摘要（无则 None）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, started_at, ended_at, turn_count, summary_text, "
                "       last_user_excerpt, msg_start_id, msg_end_id, created_at "
                "FROM session_summaries ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get_messages_since(
        self, after_msg_id: Optional[int], limit: int = 50
    ) -> List[Dict[str, Any]]:
        """取 after_msg_id 之后的消息（不含该 id），正序返回。

        若 after_msg_id 为 None，返回最近 limit 条（正序）。
        用于 session 摘要：优先取上次摘要 msg_end_id 之后的新消息。
        """
        with self._connect() as conn:
            if after_msg_id is not None:
                rows = conn.execute(
                    "SELECT id, role, sender, content, created_at, status "
                    "FROM messages WHERE id > ? AND status IN ('normal','failed','recalled') "
                    "ORDER BY id ASC LIMIT ?",
                    (after_msg_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, role, sender, content, created_at, status "
                    "FROM messages WHERE status IN ('normal','failed','recalled') "
                    "ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                rows = list(reversed(rows))
        return [dict(r) for r in rows]
