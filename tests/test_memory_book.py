"""V15.0「年轮」M3 测试：回忆之书（统计/纪念日行/相册/浮层）+ token 出库兼容。

覆盖：
- design_tokens 出库：gui.DIM is design_tokens.DIM（拆分第一刀兼容契约）
- 纯函数：统计条 / 即将到来纪念日（里程碑+周年+节日，按临近排序）/
  时间线倒序 / 相册清单过滤与标题映射
- 离屏浮层：依赖注入构造（临时账本/会话库/相册目录），统计条文案、
  三页签列表行数、相册选中预览
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")
os.environ.setdefault("REZERO_LIFE_DB",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "_mb_tmp_life.db"))

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from datetime import date, timedelta  # noqa: E402

import pytest  # noqa: E402

import design_tokens  # noqa: E402
import memory_book  # noqa: E402
from shared.conversation_store import ConversationStore  # noqa: E402
from shared.life_ledger import LifeLedger  # noqa: E402


# ── token 出库兼容 ────────────────────────────────────────────────

def test_gui_tokens_are_design_tokens():
    import gui
    assert gui.DIM is design_tokens.DIM
    assert gui.COLORS is design_tokens.COLORS
    assert design_tokens.DIM["bubble_max_w"] == 600
    assert not hasattr(design_tokens, "QApplication"), "token 模块必须零 Qt 依赖"


# ── 纯函数 ────────────────────────────────────────────────────────

def _events():
    return [
        {"id": 3, "kind": "letter", "title": "收到蕾姆的来信", "ts": "2026-09-20 10:00:00"},
        {"id": 2, "kind": "loyalty_lock", "title": "忠诚锁定达成", "ts": "2026-08-01 09:00:00"},
        {"id": 1, "kind": "genesis", "title": "相识之日", "ts": "2026-01-01 08:00:00"},
    ]


def test_compute_stats():
    stats = memory_book.compute_stats(genesis=date(2026, 1, 1), today=date(2026, 9, 23),
                                      user_msg_count=42, events=_events())
    text = "  ·  ".join(stats)
    assert "同行 266 天" in text and "42 轮对话" in text
    assert "1 封来信" in text and "1 个被记住的瞬间" in text


def test_upcoming_anniversaries_order():
    genesis = date(2026, 1, 1)
    today = date(2026, 9, 23)
    rows = memory_book.upcoming_anniversaries(today, genesis)
    assert rows, "应有临近纪念日"
    assert "中秋节" in rows[0][0], "最近的应是 9-25 中秋（还差 2 天）"
    assert "还有 2 天" in rows[0][1]
    assert any("第 300 天" in label for label, _ in rows)
    assert any("周年" in label for label, _ in rows)
    # 相识当天（恰为元旦 2026-01-01）：节日行显示"就是今天"
    rows2 = memory_book.upcoming_anniversaries(date(2026, 1, 1), genesis)
    assert any("元旦" in label and "就是今天" in detail
               for label, detail in rows2)


def test_timeline_rows_desc_and_icons():
    rows = memory_book.timeline_rows(_events())
    assert rows[0][0] == "💌" and rows[-1][0] == "🌱"
    assert [r[2] for r in rows] == sorted([r[2] for r in rows], reverse=True)


def test_album_files_and_title(tmp_path):
    (tmp_path / "2026-09-25_festival.md").write_text("# 卡", encoding="utf-8")
    (tmp_path / "2026-07-29_days_milestone.md").write_text("# 卡", encoding="utf-8")
    (tmp_path / "junk.txt").write_text("x", encoding="utf-8")
    files = memory_book.album_files(str(tmp_path))
    assert files == ["2026-09-25_festival.md", "2026-07-29_days_milestone.md"]
    assert memory_book.album_card_title(files[0]) == "2026-09-25 · 节日"
    assert memory_book.album_card_title(files[1]) == "2026-07-29 · 相识纪念日"


# ── 离屏浮层 ──────────────────────────────────────────────────────

def test_memory_book_overlay_offscreen(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])

    ledger = LifeLedger(str(tmp_path / "life.db"))
    for ev in _events():
        ledger.append(ts=ev["ts"], kind=ev["kind"], title=ev["title"],
                      dedup_key=f"k{ev['id']}")
    store = ConversationStore(str(tmp_path / "conv.db"))
    for i in range(3):
        store.append("user", "你", f"消息{i}")
    album = tmp_path / "album"
    album.mkdir()
    (album / "2026-09-25_festival.md").write_text(
        "# 纪念卡 · 2026-09-25\n\n中秋快乐。", encoding="utf-8")

    today = date(2026, 9, 23)
    overlay = memory_book.MemoryBookOverlay(
        parent=None, conv_store=store, ledger=ledger,
        genesis=date(2026, 1, 1), album_dir=str(album), today=today)

    assert "同行 266 天" in overlay._stats_label.text()
    assert overlay._timeline_list.count() == 3
    assert "中秋节" in overlay._anniv_list.item(0).text()
    assert overlay._album_list.count() == 1
    # 相册选中 → 预览
    overlay._album_list.setCurrentRow(0)
    assert "中秋快乐" in overlay._album_view.toMarkdown() or \
        "中秋快乐" in overlay._album_view.toPlainText()

    # 今日无纪念卡文件时的空相册防御（另一实例）
    empty = memory_book.MemoryBookOverlay(
        parent=None, conv_store=None, ledger=LifeLedger(str(tmp_path / "l2.db")),
        genesis=today, album_dir=str(tmp_path / "none"), today=today)
    assert "还是空的" in empty._album_list.item(0).text()
    assert "还没有被记住的瞬间" in empty._timeline_list.item(0).text()
