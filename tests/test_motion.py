"""V16 表现层 M_B 测试：动效系统（motion.py）。

验收口径 = DESIGN_SYSTEM_V2 §一/§五：
- 运行时门：offscreen 恒禁用（测试确定性红线）、旧开关兼容
- 级联序列（纯函数）：步长 30ms、cap=8 后齐平
- 禁用态零残留：fade_in 不挂 effect、stagger_reveal 不藏行——立即呈现最终状态
- 启用态：effect 挂载 + 手动清理
- gui 接线：历史回放级联延迟透传（_play_entrance_animation(delay_ms)）
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

import motion  # noqa: E402


# ── 运行时门 ─────────────────────────────────────────────────────

def test_enabled_offscreen_always_false(monkeypatch):
    assert motion.enabled() is False, "offscreen 恒禁用（宪法红线）"
    monkeypatch.setenv("REZERO_DISABLE_UI_MOTION", "1")
    assert motion.enabled() is False


def test_enabled_respects_switches(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    monkeypatch.setenv("REZERO_DISABLE_UI_MOTION", "")
    assert motion.enabled() is True
    monkeypatch.setenv("REZERO_DISABLE_UI_MOTION", "1")
    assert motion.enabled() is False


# ── 级联纯函数 ───────────────────────────────────────────────────

def test_stagger_delays_shape():
    assert motion.stagger_delays(0) == []
    assert motion.stagger_delays(3) == [0, 30, 60]
    delays = motion.stagger_delays(12)
    assert len(delays) == 12
    assert delays[:8] == [i * 30 for i in range(8)]
    assert delays[8:] == [210] * 4, "第 9 项起同时出现（cap=8 齐平）"


def test_stagger_delays_custom():
    assert motion.stagger_delays(4, step=10, cap=2) == [0, 10, 10, 10]


# ── 禁用态零残留 ─────────────────────────────────────────────────

def test_fade_in_disabled_leaves_no_effect(qtapp):
    from PySide6.QtWidgets import QLabel
    w = QLabel("x")
    pos = (w.x(), w.y())
    motion.fade_in(w)
    assert w.graphicsEffect() is None, "禁用态不得挂任何 effect"
    motion.fade_slide(w)
    assert w.graphicsEffect() is None
    assert (w.x(), w.y()) == pos, "禁用态 fade_slide 不得移动 widget（立即呈现最终状态）"


def test_stagger_reveal_disabled_hides_nothing(qtapp):
    from PySide6.QtWidgets import QListWidget, QListWidgetItem
    lw = QListWidget()
    for i in range(5):
        QListWidgetItem(f"r{i}", lw)
    motion.stagger_reveal(lw)
    assert all(not lw.isRowHidden(i) for i in range(5)), \
        "禁用态不得隐藏任何行（立即呈现最终状态）"


def test_fade_in_enabled_attaches_and_cleans(monkeypatch, qtapp):
    from PySide6.QtWidgets import QLabel
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    w = QLabel("x")
    motion.fade_in(w)
    assert w.graphicsEffect() is not None, "启用态应挂 opacity effect"
    motion._safe_clear_effect(w)
    assert w.graphicsEffect() is None


def test_stagger_reveal_enabled_hides_then_reveals(monkeypatch, qtapp):
    from PySide6.QtWidgets import QListWidget, QListWidgetItem
    monkeypatch.setenv("QT_QPA_PLATFORM", "windows")
    lw = QListWidget()
    for i in range(3):
        QListWidgetItem(f"r{i}", lw)
    motion.stagger_reveal(lw)
    assert lw.isRowHidden(2), "cap 之外的行初始应隐藏（等一次性放开）"


# ── gui 接线 ─────────────────────────────────────────────────────

def test_append_message_accepts_motion_delay(qtapp, tmp_path, monkeypatch):
    """历史回放级联参数透传：offscreen 禁用态下 animate+delay 不破坏插入。"""
    import gui
    monkeypatch.setattr(gui, "_load_history", lambda self: None, raising=False)
    win = gui.TwinChatApp()
    win.show()
    w = win._append_parsed_message("蕾 姆", "测试消息", "rem",
                                   save=False, animate=True, motion_delay_ms=30)
    assert w is not None
    assert w.graphicsEffect() is None, "offscreen 下入场动画为 no-op"
    win.close()


@pytest.fixture
def qtapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
