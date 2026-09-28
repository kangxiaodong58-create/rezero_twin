"""SPEC-20260922-24：氛围行修复——子句感知截断（``_shorten_event``）与 ``format_world_line`` 集成。

边界表（审计 F24-6 要求全覆盖）：短事件 / 恰等限长 / 两子句首短 / 两子句首长 /
无逗号超长 / 空串 / 逗号开头；外加**永不出现「，…」**的不变量断言。
零 API、零 GUI（纯函数）。
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ui.text import _shorten_event, format_world_line  # noqa: E402

# 实测脏事件原样（用户截图里被切到吊逗号的那条）
CASE_EVENT = "一只野猫从庭院围墙跳了进来，吓了蕾姆一跳"
FIRST_CLAUSE = "一只野猫从庭院围墙跳了进来"          # 13 字 ≤ 16
HARD_CUT_SOURCE = "一二三四五六七八九十一二三四五六七八九十"   # 首子句 20 字


class TestShortenEvent:
    def test_short_event_untouched(self):
        assert _shorten_event("夜里下过一场小雪", 16) == "夜里下过一场小雪"

    def test_len_equal_limit_untouched(self):
        s = "一二三四五六七八九十一二三四五六"           # 恰 16 字
        assert len(s) == 16
        assert _shorten_event(s, 16) == s

    def test_first_clause_short_keeps_clause(self):
        assert _shorten_event(CASE_EVENT, 16) == FIRST_CLAUSE + "…"

    def test_first_clause_too_long_hard_cuts(self):
        ev = HARD_CUT_SOURCE + "，尾"
        assert _shorten_event(ev, 16) == HARD_CUT_SOURCE[:16] + "…"

    def test_no_comma_hard_cuts(self):
        assert _shorten_event(HARD_CUT_SOURCE, 16) == HARD_CUT_SOURCE[:16] + "…"

    def test_empty(self):
        assert _shorten_event("", 16) == ""

    def test_leading_comma_falls_back_to_hard_cut(self):
        ev = "，" + HARD_CUT_SOURCE
        assert _shorten_event(ev, 16) == ev[:16] + "…"

    def test_never_dangling_comma(self):
        for ev in (CASE_EVENT, "，" + "字" * 30, FIRST_CLAUSE + "，" + "字" * 30):
            assert "，…" not in _shorten_event(ev, 16)


class TestFormatWorldLine:
    def test_ambient_uses_clause_aware_cut(self):
        line = format_world_line("上午", "多云", CASE_EVENT, max_event=16, prefix="🌙 ")
        assert line == f"🌙 上午 · 多云 · {FIRST_CLAUSE}…"

    def test_never_dangling_comma_integration(self):
        line = format_world_line("上午", "多云", CASE_EVENT, max_event=16, prefix="🌙 ")
        assert "，…" not in line

    def test_status_bar_suffix_head_false(self):
        out = format_world_line("上午", "多云", CASE_EVENT, max_event=16,
                                head=False, suffix_sep="  ·  ")
        assert out.startswith("  ·  ")
        assert "，…" not in out

    def test_default_limit_is_16(self):
        """默认 max_event 已由 14 统一为 16（门禁：改回 14 此用例即红）。"""
        ev = "一二三四五六七八九十一二三四五六"           # 恰 16 字
        assert format_world_line("上午", "多云", ev, prefix="") == "上午 · 多云 · " + ev


class TestNameHintOnce:
    def test_hint_is_per_process(self, monkeypatch):
        import ui.flags

        monkeypatch.setattr(ui.flags, "_name_hint_shown", False)
        assert ui.flags.name_hint_once() is True
        assert ui.flags.name_hint_once() is False
