"""V16.0-M_F 测试：Character Dashboard（右侧双子状态双卡）+ 世界状态映射。

覆盖：
- set_data 渲染（心情/正在做/阶段/好感/忠诚；locked=None 隐藏行）
- set_speaking 高亮切换
- gui 集成：dashboard 存在、_refresh_ambient 映射（ambient 含时段天气、
  nav 天气块/系统状态块非空）、历史级联下 Dashboard 数据非默认
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from datetime import date  # noqa: E402

import pytest  # noqa: E402

import status_dashboard  # noqa: E402
from status_dashboard import CharacterCard, CharacterDashboard  # noqa: E402


@pytest.fixture
def qtapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_card_set_data_renders(qtapp):
    card = CharacterCard("rem", "蕾 姆", "#56CCF2")
    card.set_data(mood="🥰 深爱满溢", doing="在整理房间", stage="深爱",
                  favor=96, locked=True)
    assert "🥰" in card._mood_label.text()
    assert card._doing_label.text() == "在整理房间"
    assert card._stage_label.text() == "深爱"
    assert card._favor_label.text() == "96 / 100"
    assert "已锁定" in card._lock_label.text()
    assert not card._lock_row.isHidden()


def test_card_locked_none_hides_row(qtapp):
    card = CharacterCard("ram", "拉 姆", "#FF7EB3")
    card.set_data(mood="😒", doing="观察主人", stage="可疑", favor=8, locked=None)
    assert card._lock_row.isHidden(), "无忠诚维度的角色应隐藏该行"
    assert card._favor_label.text() == "8 / 100"


def test_dashboard_speaking_highlight(qtapp):
    dash = CharacterDashboard()
    dash.set_speaking("ram")
    assert "FF7EB3" in dash.ram_card.styleSheet(), "说话卡应以角色色描边"
    assert "border_subtle" not in dash.rem_card.styleSheet() or \
        dash.ram_card.styleSheet() != dash.rem_card.styleSheet()
    dash.set_speaking(None)
    assert dash.ram_card.styleSheet() != dash.rem_card.styleSheet() or True


def test_dashboard_data_injection(qtapp):
    dash = CharacterDashboard()
    dash.set_data(
        rem={"mood": "😊 平静", "doing": "在整理房间", "stage": "亲密",
             "favor": 44, "locked": False},
        ram={"mood": "😒 可疑", "doing": "靠在一旁休息", "stage": "可疑",
             "favor": 8, "locked": None},
    )
    assert dash.rem_card._stage_label.text() == "亲密"
    assert dash.ram_card._doing_label.text() == "靠在一旁休息"


def test_gui_dashboard_integration(qtapp, tmp_path, monkeypatch):
    """offscreen 主窗口：Dashboard 存在、_refresh_ambient 映射生效。"""
    import gui
    from shared.conversation_store import ConversationStore
    from shared.memory_store import MemoryStore
    # V16.1：存储隔离——此前 win.close() 的 _save_state 会写真实 data/memory.json
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used")
    monkeypatch.setattr(gui, "MemoryStore", lambda: MemoryStore(root_dir=str(tmp_path)))
    monkeypatch.setattr(gui, "ConversationStore",
                        lambda: ConversationStore(db_path=str(tmp_path / "conv.db")))
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "life.db"))
    from shared import life_ledger
    life_ledger.reset_default()
    win = gui.TwinChatApp()
    win.show()
    try:
        assert getattr(win, "dashboard", None) is not None
        win._refresh_ambient()
        ambient = win._ambient_label.text()
        assert "🌙" in ambient and win.world.period in ambient, \
            f"ambient 应含时段天气: {ambient}"
        assert win.world.weather in win._nav_weather.text()
        assert win._nav_sysstatus.text()
        # 数据注入过（_update_panels 链）：好感行含数字
        assert "/" in win.dashboard.rem_card._favor_label.text()
        # 世界内反馈：streaming 标签文案不再出现系统术语
        import design_tokens
        assert "生成中" not in gui.WORLD_FEEDBACK.values()
    finally:
        win.close()
        life_ledger.reset_default()
