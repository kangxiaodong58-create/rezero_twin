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
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
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

    def get_recent(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """分页读取最近消息（倒序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, role, sender, content, created_at "
                "FROM messages ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """FTS5 全文搜索。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT m.id, m.role, m.sender, m.content, m.created_at "
                "FROM messages m JOIN messages_fts f ON m.id = f.rowid "
                "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]

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
