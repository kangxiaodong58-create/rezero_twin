"""SPEC-20260922-25 B1 回归：Dashboard 资产入口必须取到真实图片（不得回退文字圈）。

根因（实锤）：S1c 把 status_dashboard.py 搬进 ui/ 后，`_ASSETS` 仍算成 `<ui>/assets`
（目录不存在）⇒ `_avatar_pixmap` 恒空 ⇒ 真机双卡一直显示「蕾/拉」字圈。
本文件把「解析到仓库根 assets/」与「卡片显示图片」钉成契约。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from ui.assets import _asset_path  # noqa: E402


@pytest.fixture
def qtapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_asset_path_points_to_repo_assets():
    """B1：资产入口解析到**仓库根** assets/（而不是不存在的 ui/assets）。"""
    for fname in ("rem_avatar.png", "ram_avatar.png", "rem_face.png", "ram_face.png",
                  "rem_sprite.jpg", "ram_sprite.jpg"):
        path = _asset_path(fname)
        assert os.path.isfile(path), f"{fname} 未解析到实际文件：{path}"
        assert os.path.basename(os.path.dirname(path)) == "assets"


def test_avatar_pixmap_non_null(qtapp):
    """B1：头像取图不再恒空。"""
    from ui.dashboard import _avatar_pixmap
    assert not _avatar_pixmap("rem", 46).isNull()
    assert not _avatar_pixmap("ram", 46).isNull()


def test_card_shows_sprite_not_text(qtapp):
    """A 项：卡片显示**立绘图片**，不再回退「蕾/拉」文字圈。"""
    from ui.dashboard import CharacterCard
    card = CharacterCard("rem", "蕾 姆", "#56CCF2")
    assert not card._sprite.pixmap().isNull(), "立绘区应当有图"
    assert card._sprite.text() == "", "不应回退文字"
    assert not hasattr(card, "_avatar"), "SPEC-25 A：头像圆已移除"


def test_dashboard_order_ram_first(qtapp):
    """A 项：拉姆在上、蕾姆在下（用户原话）。"""
    from ui.dashboard import CharacterDashboard
    dash = CharacterDashboard()
    lay = dash.layout()
    cards = [lay.itemAt(i).widget() for i in range(lay.count())]
    cards = [w for w in cards if hasattr(w, "role")]
    assert [w.role for w in cards] == ["ram", "rem"]


def test_sprite_card_pixmap_geometry_and_fade(qtapp):
    """立绘卡片图：尺寸正确 + 四角透明（圆角）+ 底行完全渐隐到卡片底色。"""
    from shared import config
    from ui.assets import sprite_card_pixmap

    fade_to = "#1B1E2E"
    pm = sprite_card_pixmap(config.get_data_dir(), "rem", 272, 200, 12, fade_to)
    assert not pm.isNull(), "立绘应能取到"
    assert (pm.width(), pm.height()) == (272, 200)
    img = pm.toImage()
    assert img.pixelColor(0, 0).alpha() == 0, "圆角外应透明"
    bottom = img.pixelColor(136, 199)
    assert bottom.alpha() == 255
    r, g, b = int(fade_to[1:3], 16), int(fade_to[3:5], 16), int(fade_to[5:7], 16)
    assert abs(bottom.red() - r) <= 2 and abs(bottom.green() - g) <= 2 and abs(bottom.blue() - b) <= 2, \
        f"底行应已渐隐到卡片底色：{bottom.name()} vs {fade_to}"
