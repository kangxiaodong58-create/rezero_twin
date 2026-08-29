"""回忆之书（V15.0「年轮」M3）：关系资产的可视化窗口。

设计依据：docs/design/V15_0_年轮_关系资产版本构思_2026-08-29.md §3.4。

结构：
- 纯函数层（零 Qt，可单测）：统计条计算 / 纪念日行 / 时间线行 / 相册清单
- MemoryBookOverlay：主窗口级非阻塞浮层（HistoryOverlay 同模式：遮罩+
  居中卡片，Esc/遮罩点击/✕ 关闭），三页签 时间线·纪念日·相册 + 顶部统计条
  「同行 N 天 · M 轮对话 · K 封来信 · J 个被记住的瞬间」

本模块是 gui.py God File 拆分后的**第一个独立 UI 模块**（M3 起点），
仅依赖 design_tokens（纯数据）与 shared（账本/纪念日/会话库）。
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QStackedWidget, QTextBrowser, QVBoxLayout, QWidget,
)

from design_tokens import (
    COLORS, DIM, ELEVATION, FONT_FAMILY, FONT_SIZE, RADIUS, SURFACE_TINT,
)

from shared.anniversary import (
    DAYS_MILESTONES, build_festival_table, genesis_days,
)
from shared.life_ledger import LifeLedger, ensure_genesis, genesis_date

# ── 纯函数层（零 Qt，可单测）──────────────────────────────────────

KIND_ICONS: Dict[str, str] = {
    "genesis": "🌱", "first_name": "📝", "loyalty_lock": "🔒", "reunion": "🌙",
    "breaker": "✨", "arc_shift": "🗺️", "milestone": "🎬", "scene_first": "🚪",
    "letter": "💌", "first_letter": "💌", "days_milestone": "🎂",
    "festival": "🏮", "memorial": "🖼️", "custom": "📌",
}

_MOMENT_KINDS = {"first_name", "loyalty_lock", "reunion", "breaker",
                 "milestone", "memorial", "days_milestone"}
_LETTER_KINDS = {"letter", "first_letter"}


def count_letters(events: List[Dict[str, Any]]) -> int:
    return sum(1 for e in events if e.get("kind") in _LETTER_KINDS)


def count_moments(events: List[Dict[str, Any]]) -> int:
    return sum(1 for e in events if e.get("kind") in _MOMENT_KINDS)


def compute_stats(*, genesis: Optional[date], today: date,
                  user_msg_count: int, events: List[Dict[str, Any]]) -> List[str]:
    """统计条四段：同行 N 天 · M 轮对话 · K 封来信 · J 个被记住的瞬间。"""
    days = genesis_days(genesis, today) if genesis else 1
    return [
        f"同行 {days} 天",
        f"{user_msg_count} 轮对话",
        f"{count_letters(events)} 封来信",
        f"{count_moments(events)} 个被记住的瞬间",
    ]


def upcoming_anniversaries(today: date, genesis: Optional[date],
                           max_rows: int = 8) -> List[Tuple[str, str]]:
    """纪念日行（按临近排序）：今天的节日 / 下一个天数里程碑 / 相识周年 / 下一个节日。"""
    rows: List[Tuple[date, str, str]] = []
    from shared.anniversary import festival_on
    today_fest = festival_on(today)
    if today_fest:
        rows.append((today, f"🏮 {today_fest}", "就是今天"))
    if genesis is not None and today >= genesis:
        days = genesis_days(genesis, today)
        nxt = next((m for m in DAYS_MILESTONES if m > days), None)
        if nxt:
            rows.append((today + timedelta(days=nxt - days),
                         f"🎂 相识第 {nxt} 天", f"还有 {nxt - days} 天"))
        try:
            annual_this = date(today.year, genesis.month, genesis.day)
        except ValueError:  # 2/29 genesis
            annual_this = None
        annual_day = annual_this if annual_this and annual_this > today \
            else date(today.year + 1, genesis.month, genesis.day) \
            if genesis.month != 2 or genesis.day != 29 else None
        if annual_day:
            years = annual_day.year - genesis.year
            rows.append((annual_day, f"💡 相识 {years} 周年",
                         f"{annual_day.isoformat()[5:]} · 还有 {(annual_day - today).days} 天"))
    next_fest = min(((d, n) for d, n in build_festival_table().items()
                     if d > today.isoformat()), default=None)
    if next_fest:
        fdate = date.fromisoformat(next_fest[0])
        rows.append((fdate, f"🏮 {next_fest[1]}",
                     f"{next_fest[0][5:]} · 还有 {(fdate - today).days} 天"))
    rows.sort(key=lambda r: r[0])
    return [(label, detail) for _d, label, detail in rows[:max_rows]]


def timeline_rows(events: List[Dict[str, Any]], limit: int = 300) -> List[Tuple[str, str, str]]:
    """时间线行（倒序）：[(icon, title, ts)]。"""
    rows = sorted(events, key=lambda e: (e.get("ts") or "", e.get("id") or 0),
                  reverse=True)[:limit]
    return [(KIND_ICONS.get(e.get("kind", ""), "📌"),
             e.get("title", ""), e.get("ts", "")) for e in rows]


def album_files(album_dir: str) -> List[str]:
    """相册文件名（*_*.md，按名称倒序=日期新→旧）。"""
    try:
        return sorted((f for f in os.listdir(album_dir) if f.endswith(".md")),
                      reverse=True)
    except Exception:
        return []


def album_card_title(filename: str) -> str:
    """'2026-09-25_festival.md' → '2026-09-25 · 节日'。"""
    from shared.memorial import _KIND_LABELS
    stem = filename[:-3] if filename.endswith(".md") else filename
    day, _, kind = stem.partition("_")
    return f"{day} · {_KIND_LABELS.get(kind, kind or '纪念')}"


# ── 浮层组件 ─────────────────────────────────────────────────────

class MemoryBookOverlay(QWidget):
    """回忆之书浮层：遮罩 + 居中卡片，三页签。show() 非 exec()，不阻塞。"""

    closed = Signal()

    def __init__(self, parent=None, *, conv_store: Any = None,
                 ledger: Optional[LifeLedger] = None, genesis: Optional[date] = None,
                 album_dir: Optional[str] = None, today: Optional[date] = None):
        super().__init__(parent)
        self._conv_store = conv_store
        self._ledger = ledger
        self._genesis = genesis
        self._album_dir = album_dir
        self._today = today or date.today()
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {COLORS['overlay_mask']};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()

        self._card = QFrame()
        self._card.setObjectName("memory_book_card")
        self._card.setFixedWidth(DIM['history_card_w'])
        self._card.setStyleSheet(f"""
            QFrame#memory_book_card {{
                background-color: {COLORS['bg_surface_2']};
                border: 1px solid {ELEVATION['card_border']};
                border-top: 1px solid {ELEVATION['glow_top']};
                border-radius: {RADIUS['large']}px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── 标题栏 ──
        header = QFrame()
        header.setFixedHeight(DIM['history_header_h'])
        header.setStyleSheet(f"border-bottom: 1px solid {COLORS['border_subtle']};")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 16, 0)
        title = QLabel("📚 回忆之书")
        title.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title'], QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_primary']};")
        h_layout.addWidget(title)
        h_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(DIM['icon_btn'], DIM['icon_btn'])
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 14px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        close_btn.clicked.connect(self.close)
        h_layout.addWidget(close_btn)
        card_layout.addWidget(header)

        # ── 统计条 ──
        self._stats_label = QLabel("")
        self._stats_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self._stats_label.setStyleSheet(
            f"color: {COLORS['text_secondary']};"
            f"background-color: {SURFACE_TINT['detail']};"
            f"padding: 10px 20px;")
        card_layout.addWidget(self._stats_label)

        # ── 页签 ──
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(20, 10, 20, 0)
        tab_row.setSpacing(8)
        self._tab_buttons: List[QPushButton] = []
        for i, name in enumerate(("🕐 时间线", "📅 纪念日", "🖼️ 相册")):
            btn = QPushButton(name)
            btn.setFixedHeight(DIM['quick_btn_h'] + 4)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
            btn.clicked.connect(lambda _=False, idx=i: self._switch_tab(idx))
            tab_row.addWidget(btn)
            self._tab_buttons.append(btn)
        tab_row.addStretch()
        card_layout.addLayout(tab_row)

        # ── 页面 ──
        self._stack = QStackedWidget()
        self._timeline_list = QListWidget()
        self._anniv_list = QListWidget()
        album_page = QFrame()
        album_layout = QHBoxLayout(album_page)
        album_layout.setContentsMargins(0, 0, 0, 0)
        self._album_list = QListWidget()
        self._album_view = QTextBrowser()
        self._album_list.currentItemChanged.connect(self._on_album_selected)
        album_layout.addWidget(self._album_list, 1)
        album_layout.addWidget(self._album_view, 2)
        self._stack.addWidget(self._timeline_list)
        self._stack.addWidget(self._anniv_list)
        self._stack.addWidget(album_page)
        card_layout.addWidget(self._stack, 1)

        row.addWidget(self._card)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

        self._reload()
        self._switch_tab(0)

    # ── 数据装载 ──

    def _reload(self) -> None:
        ledger = self._ledger
        if ledger is None:
            try:
                ledger = LifeLedger(os.environ.get("REZERO_LIFE_DB")
                                    or None) if os.environ.get("REZERO_LIFE_DB") \
                    else LifeLedger()
            except Exception:
                ledger = None
        events = ledger.all_events() if ledger is not None else []
        genesis = self._genesis
        if genesis is None:
            genesis = ensure_genesis(self._conv_store, ledger=ledger)
        user_count = 0
        if self._conv_store is not None:
            try:
                user_count = self._conv_store.count_user_messages()
            except Exception:
                user_count = 0

        stats = compute_stats(genesis=genesis, today=self._today,
                              user_msg_count=user_count, events=events)
        self._stats_label.setText("  ·  ".join(stats))

        self._timeline_list.clear()
        for icon, title, ts in timeline_rows(events):
            QListWidgetItem(f"{icon}  {title}   ·   {ts}", self._timeline_list)
        if not events:
            QListWidgetItem("（还没有被记住的瞬间——从今天的下一轮对话开始）",
                            self._timeline_list)

        self._anniv_list.clear()
        rows = upcoming_anniversaries(self._today, genesis)
        for label, detail in rows:
            QListWidgetItem(f"{label}   ·   {detail}", self._anniv_list)
        if not rows:
            QListWidgetItem("（节日表覆盖范围内暂无临近纪念日）", self._anniv_list)

        self._album_list.clear()
        self._album_files = album_files(self._album_dir) if self._album_dir else []
        for f in self._album_files:
            item = QListWidgetItem(album_card_title(f), self._album_list)
            item.setData(Qt.UserRole, f)
        if not self._album_files:
            QListWidgetItem("（相册还是空的——纪念日会自动生成卡片）",
                            self._album_list)

    def _on_album_selected(self, *_a) -> None:
        item = self._album_list.currentItem()
        filename = item.data(Qt.UserRole) if item else None
        if not filename or not self._album_dir:
            return
        path = os.path.join(self._album_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._album_view.setMarkdown(f.read())
        except Exception:
            self._album_view.setPlainText("（卡片读取失败）")

    def _switch_tab(self, idx: int) -> None:
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._tab_buttons):
            active = i == idx
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {SURFACE_TINT['active'] if active else 'transparent'};
                    color: {COLORS['text_primary'] if active else COLORS['text_muted']};
                    border: 1px solid {COLORS['border_subtle']};
                    border-radius: {RADIUS['small']}px; padding: 0 12px;
                }}
            """)

    # ── 关闭行为（Esc / 遮罩点击）──

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if not self._card.geometry().contains(event.position().toPoint()):
            self.close()
        else:
            super().mousePressEvent(event)
