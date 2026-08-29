"""人生账本（V15.0「年轮」M1）：Relationship Assets 的持久层。

设计依据：docs/design/V15_0_年轮_关系资产版本构思_2026-08-29.md §3.1/§3.5。

定位（与既有存储的边界）：
- engine.events（30 条环形+钉住）= 工作记忆（RAM），喂 prompt 用；
- conversations.db = 对话流水（原始证据）；
- **life.db = 人生账本（墓志铭）**——append-only、永不淘汰、幂等去重，
  记录的是「这段关系真的发生过」的事实，不为检索而生，为证明而生。

原则：
1. 事实由规则层记账（零 API、确定性）；LLM 只朗读事实，永不产生事实。
2. 幂等：dedup_key 唯一约束，回填/重跑/镜像重复调用不产生重复记录。
3. 静默：镜像函数任何失败都不得影响主流程（与 forensic 同纪律）。

schema：
    life_events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,          -- 'YYYY-MM-DD HH:MM:SS'（本地时）
      kind TEXT NOT NULL,        -- genesis|first_name|loyalty_lock|reunion|breaker|
                                 -- arc_shift|milestone|scene_first|letter|first_letter|
                                 -- days_milestone|festival|memorial|custom
      title TEXT NOT NULL,       -- 一句话事实（如「第一次收到蕾姆的来信」）
      detail TEXT NOT NULL DEFAULT '',  -- JSON 快照：arc/favor/period/weather/scene 等
      dedup_key TEXT NOT NULL UNIQUE,   -- 幂等键
      created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
    )
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import get_data_dir


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class LifeLedger:
    """人生账本（SQLite，append-only）。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        if db_path is None:
            db_path = os.path.join(get_data_dir(), "life.db")
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS life_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    dedup_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_life_ts ON life_events(ts)")
            conn.commit()

    # ── 写入（append-only + 幂等）────────────────────────────────

    def append(self, *, ts: Optional[str] = None, kind: str, title: str,
               detail: Any = "", dedup_key: str) -> bool:
        """追加一条人生事实。dedup_key 已存在时不写入并返回 False（幂等）。

        detail 可传 dict/list（自动序列化为 JSON 快照）或字符串。
        返回 True = 新增；False = 重复（幂等跳过）。
        """
        if not kind or not title or not dedup_key:
            return False
        detail_str = detail if isinstance(detail, str) else json.dumps(
            detail, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO life_events (ts, kind, title, detail, dedup_key) "
                "VALUES (?, ?, ?, ?, ?)",
                (ts or _now_str(), kind, title, detail_str, dedup_key),
            )
            conn.commit()
            added = cur.rowcount > 0
        if added:
            # V15.0-M4：人生事实落账进取证黑匣子（未初始化 no-op，静默）
            try:
                from runtime.forensic import record
                record("LEDGER_APPEND", component="life_ledger",
                       payload_summary=f"{kind}|{dedup_key}")
            except Exception:
                pass
        return added

    def has(self, dedup_key: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM life_events WHERE dedup_key = ?", (dedup_key,)
            ).fetchone()
            return row is not None

    # ── 读取 ─────────────────────────────────────────────────────

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM life_events").fetchone()[0])

    def all_events(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM life_events ORDER BY ts ASC, id ASC").fetchall()
            return [dict(r) for r in rows]

    def latest(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM life_events ORDER BY ts DESC, id DESC LIMIT ?",
                (int(limit),)).fetchall()
            return [dict(r) for r in rows]


# ── 默认账本单例（env 可覆盖路径；测试隔离用 REZERO_LIFE_DB）────────

_default_ledger: Optional[LifeLedger] = None


def get_default_ledger() -> LifeLedger:
    global _default_ledger
    if _default_ledger is None:
        path = os.environ.get("REZERO_LIFE_DB") or os.path.join(
            get_data_dir(), "life.db")
        _default_ledger = LifeLedger(path)
    return _default_ledger


def reset_default() -> None:
    """测试用：丢弃单例（下次 get 重新按 env 解析路径）。"""
    global _default_ledger
    _default_ledger = None


# ── 语义化镜像（规则层记账入口；全部静默失败）────────────────────

def _mirror(kind: str, title: str, *, dedup_key: str,
            detail: Any = None, ts: Optional[str] = None) -> bool:
    try:
        return get_default_ledger().append(
            ts=ts, kind=kind, title=title, detail=detail, dedup_key=dedup_key)
    except Exception:
        return False


def _snap(engine: Any) -> Dict[str, Any]:
    """记账快照：时刻发生时她是谁（arc/favor），供未来回看与纪念卡用。"""
    arc = getattr(getattr(engine, "arc", None), "value", "")
    return {"arc": arc, "favor": getattr(engine, "favor", None)}


def mirror_first_name(name: str, *, engine: Any) -> bool:
    return _mirror("first_name", f"第一次告知名字「{name}」",
                   dedup_key="first_name", detail=_snap(engine))


def mirror_loyalty_lock(*, engine: Any) -> bool:
    return _mirror("loyalty_lock", "好感抵达 95，忠诚锁定达成",
                   dedup_key="loyalty_lock", detail=_snap(engine))


def mirror_reunion(*, engine: Any) -> bool:
    return _mirror("reunion", "记忆恢复，重逢", dedup_key="reunion",
                   detail=_snap(engine))


def mirror_breaker(*, engine: Any) -> bool:
    return _mirror("breaker", "破局者时刻", dedup_key="breaker",
                   detail=_snap(engine))


def mirror_arc_shift(prev_arc: str, new_arc: str, *, turn_count: int,
                     engine: Any) -> bool:
    return _mirror("arc_shift", f"篇章切换：{prev_arc} → {new_arc}",
                   dedup_key=f"arc_shift|{int(turn_count)}|{new_arc}",
                   detail=_snap(engine))


def mirror_scene_first(scene_id: str, arc: str) -> bool:
    """场景首访（每场景一生一次；dedup 幂等保证）。"""
    return _mirror("scene_first", f"第一次一起来到「{scene_id}」",
                   dedup_key=f"scene_first|{scene_id}", detail={"arc": arc})


def mirror_milestone(name: str, *, engine: Any) -> bool:
    """名场面语感注入记账（每名场面每日一条——冷却节奏天然限频）。"""
    return _mirror("milestone", f"名场面时刻：{name}",
                   dedup_key=f"milestone|{name}|{_today()}", detail=_snap(engine))


def mirror_letter(sender: str) -> bool:
    """收到主动来信记账（每发件人每日一条）。"""
    who = "蕾姆" if sender == "rem" else "拉姆"
    return _mirror("letter", f"收到{who}的来信",
                   dedup_key=f"letter|{sender}|{_today()}")


# ── 历史回填（一次性、幂等）──────────────────────────────────────

# engine.events 类型 → 账本 kind / 镜像 dedup / 标题
_EVENT_KIND_MAP = {
    "name_first": ("first_name", "first_name", "第一次告知名字"),
    "locked": ("loyalty_lock", "loyalty_lock", "忠诚锁定达成"),
    "reunion": ("reunion", "reunion", "记忆恢复，重逢"),
    "breaker": ("breaker", "breaker", "破局者时刻"),
}


def backfill_from(*, conversation_store: Any, memory_events: Optional[List[dict]] = None,
                  first_letter_ts: float = 0.0,
                  ledger: Optional[LifeLedger] = None) -> Dict[str, Any]:
    """一次性历史回填（幂等，可重复执行）。返回 {added, skipped, details}。

    来源与规则：
    - genesis：最早一条消息的 created_at（最早可得证据；无消息则今天）；
    - 引擎重要时刻：memory.events 中 name_first/locked/reunion/breaker，
      ts = 第 seq 条 user 消息时刻（对不上则回退最早消息时刻）；
    - first_letter：world.last_letter_ts > 0 时回填首封来信。
    """
    ledger = ledger or get_default_ledger()
    added = 0
    checked = 0
    user_times = []
    oldest = ""
    try:
        user_times = conversation_store.user_message_times()
        oldest = conversation_store.oldest_message_time()
    except Exception:
        pass

    genesis_ts = oldest or _now_str()
    checked += 1
    if ledger.append(ts=genesis_ts, kind="genesis", title="相识之日",
                     dedup_key="genesis"):
        added += 1

    for ev in (memory_events or []):
        etype = ev.get("type", "")
        if etype not in _EVENT_KIND_MAP:
            continue
        kind, dedup, base_title = _EVENT_KIND_MAP[etype]
        checked += 1
        seq = int(ev.get("seq", 0) or 0)
        ts = user_times[seq - 1] if 0 < seq <= len(user_times) else genesis_ts
        summary = (ev.get("summary") or base_title)[:80]
        if ledger.append(ts=ts, kind=kind, title=summary, dedup_key=dedup):
            added += 1

    if first_letter_ts and first_letter_ts > 0:
        checked += 1
        ts = datetime.fromtimestamp(first_letter_ts).strftime("%Y-%m-%d %H:%M:%S")
        if ledger.append(ts=ts, kind="first_letter", title="第一封主动来信",
                         dedup_key="first_letter"):
            added += 1

    return {"added": added, "checked": checked, "total": ledger.count()}


# ── 相识日与当日事实入账（V15.0-M2，纪念日引擎配套）────────────────

def genesis_date(ledger: Optional[LifeLedger] = None):
    """账本中的相识日（kind=genesis）；无则 None。返回 datetime.date。"""
    try:
        led = ledger or get_default_ledger()
        for ev in led.all_events():
            if ev["kind"] == "genesis":
                from datetime import date
                return date.fromisoformat(ev["ts"][:10])
    except Exception:
        return None
    return None


def ensure_genesis(conversation_store: Any = None,
                   ledger: Optional[LifeLedger] = None):
    """确保 genesis 已落账（幂等），返回相识日；无任何证据时取今天。

    证据链：conversations 最早消息 > 今天（与 backfill_from 同口径）。
    """
    led = ledger or get_default_ledger()
    existing = genesis_date(led)
    if existing is not None:
        return existing
    oldest = ""
    try:
        if conversation_store is not None:
            oldest = conversation_store.oldest_message_time()
    except Exception:
        pass
    try:
        led.append(ts=oldest or _now_str(), kind="genesis", title="相识之日",
                   dedup_key="genesis")
    except Exception:
        return None
    return genesis_date(led)


def record_day_facts(facts: Any, today: Any,
                     ledger: Optional[LifeLedger] = None) -> None:
    """把纪念日引擎的当日事实落账（days_milestone/festival；幂等、静默）。

    facts = anniversary.compute_facts() 的返回（鸭子类型：kind/title/key）。
    节日每年一条 → 时间线自然积累"一起度过的节日"序列。
    """
    led = ledger or get_default_ledger()
    today_str = today.isoformat() if hasattr(today, "isoformat") else str(today)
    for f in facts or []:
        try:
            kind = getattr(f, "kind", "")
            if kind == "days_milestone":
                led.append(kind="days_milestone", title=f.title,
                           dedup_key=f"days_milestone|{f.key}", ts=today_str)
            elif kind == "festival":
                led.append(kind="festival", title=f.title,
                           dedup_key=f"festival|{f.key}|{today_str}", ts=today_str)
            elif kind == "genesis_annual":
                led.append(kind="days_milestone", title=f.title,
                           dedup_key=f"genesis_annual|{f.key}|{today_str}",
                           ts=today_str)
        except Exception:
            continue
