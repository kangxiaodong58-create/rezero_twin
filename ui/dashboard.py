"""Character Dashboard（V16.0-M_F）：右侧双子状态双卡。

DESIGN 解析 §1.5：右栏不是"联系人"，而是 Character Dashboard——
立绘 / 名字 · 心情 / 当前行为 / 关系阶段 / 好感 / 忠诚，全部属于 Persistent State。
（SPEC-20260922-25 A：立绘区取代头像圆；资产入口统一走 ui.assets，修 B1 文字圈缺陷。）

设计纪律：
- 本模块**只负责展示**：数据由 gui 从 snapshot/world 组装成 dict 注入
  （`set_data`），业务计算（表情档位等）留在 gui/_update_panels——
  与 memory_book 同一拆分纪律（新 UI 独立模块、依赖注入可离屏单测）。
- 视觉消费 design_tokens；SVG 头像内联 QSvgRenderer 渲染（不依赖 gui，
  避免循环导入；EXE 内由 spec 收集的 QtSvg 保障）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from design_tokens import (
    COLORS, DIM, ELEVATION, FONT_FAMILY, FONT_SIZE, LAYOUT, RADIUS, SURFACE_TINT,
)
from shared import config as _config           # 晚绑定：调用时才解析数据目录
from ui import theme  # SPEC-20260922-18：QSS 单一真源（B6·A14 收口）
from ui.assets import _asset_path, sprite_card_pixmap

try:
    from PySide6.QtSvg import QSvgRenderer
    _SVG_OK = True
except Exception:  # pragma: no cover
    QSvgRenderer = None
    _SVG_OK = False

_UI_FONT = FONT_FAMILY["ui"].split(",")[0]


def _avatar_pixmap(role: str, size: int) -> QPixmap:
    """高清圆头像（.png 优先 → .svg 显式渲染 → 空图）。"""
    for fname in (f"{role}_avatar.png", f"{role}_avatar.svg"):
        path = _asset_path(fname)   # SPEC-20260922-25 B1：统一资产入口（原 _ASSETS 指向不存在的 <ui>/assets）
        if not os.path.isfile(path):
            continue
        if fname.endswith(".png"):
            pm = QPixmap(path)
            if not pm.isNull():
                return pm.scaled(size, size, Qt.KeepAspectRatio,
                                 Qt.SmoothTransformation)
            continue
        if _SVG_OK:
            try:
                renderer = QSvgRenderer(path)
                if renderer.isValid():
                    pm = QPixmap(size * 2, size * 2)
                    pm.fill(Qt.transparent)
                    painter = QPainter(pm)
                    renderer.render(painter)
                    painter.end()
                    return pm.scaled(size, size, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
            except Exception:
                pass
    return QPixmap()


class CharacterCard(QFrame):
    """单角色状态卡：立绘区 / 名字 · 心情 / 正在做 / 关系阶段 / 好感 / 忠诚。"""

    def __init__(self, role: str, name: str, accent: str, parent=None):
        super().__init__(parent)
        self.role = role
        self._accent = accent
        self.setObjectName(f"dash_card_{role}")
        self._style(speaking=False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # ── 立绘区（SPEC-20260922-25 A：取代头像圆；用户自定义 data/sprites 同样生效）──
        self._sprite = QLabel()
        self._sprite.setObjectName(f"dash_sprite_{role}")
        self._sprite.setFixedHeight(LAYOUT.get("dash_sprite_h", 200))
        self._sprite.setAlignment(Qt.AlignCenter)
        self._sprite.setStyleSheet(theme.dash_sprite_frame(role))
        self._load_sprite()
        lay.addWidget(self._sprite)

        # ── 名字 · 心情 ──
        head = QHBoxLayout()
        head.setSpacing(8)
        self._name_label = QLabel(name)
        self._name_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        self._name_label.setStyleSheet(theme.color_only(accent))
        head.addWidget(self._name_label)
        head.addStretch()

        self._mood_label = QLabel("😊 平静")
        self._mood_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"]))
        self._mood_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        head.addWidget(self._mood_label)
        lay.addLayout(head)

        # ── 明细行 ──
        self._doing_label = self._row("正在做", "—")
        self._stage_label = self._row("关系阶段", "—")
        self._favor_label = self._row("好感", "0 / 100")
        self._lock_row, self._lock_label = self._row_wrap("忠诚锁定", "—")

    def _load_sprite(self) -> None:
        """立绘卡片图；取不到时回退圆头像（B1 修好的资产入口），仍失败留空框。"""
        w = int(LAYOUT.get("dash_w", 320)) - 48       # 320 − dashboard 边距 24 − 卡片边距 24
        h = int(LAYOUT.get("dash_sprite_h", 200))
        pm = sprite_card_pixmap(_config.get_data_dir(), self.role, w, h,
                                RADIUS["medium"], COLORS["bg_surface"])
        if pm.isNull():
            pm = _avatar_pixmap(self.role, h)
        if not pm.isNull():
            self._sprite.setPixmap(pm)

    def _style(self, speaking: bool) -> None:
        border = self._accent if speaking else COLORS["border_subtle"]
        self.setStyleSheet(theme.card_frame(self.role, border))

    def _row_wrap(self, key: str, value: str):
        row = QFrame()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        k = QLabel(key)
        k.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        k.setStyleSheet(theme.color_only(COLORS['text_muted']))
        v = QLabel(value)
        v.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        v.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        rl.addWidget(k)
        rl.addStretch()
        rl.addWidget(v)
        self.layout().addWidget(row)
        return row, v

    def _row(self, key: str, value: str) -> QLabel:
        _wrap, v = self._row_wrap(key, value)
        return v

    def set_data(self, *, mood: str, doing: str, stage: str,
                 favor: int, locked: Optional[bool] = None) -> None:
        """注入展示数据（业务换算由调用方完成）。locked=None 表示该角色无此维度。"""
        self._mood_label.setText(mood)
        self._doing_label.setText(doing or "—")
        self._stage_label.setText(stage or "—")
        self._favor_label.setText(f"{int(favor)} / 100")
        if locked is None:
            self._lock_row.hide()
        else:
            self._lock_row.show()
            self._lock_label.setText("🔒 已锁定" if locked else "未锁定")

    def set_speaking(self, speaking: bool) -> None:
        """说话高亮（V12.0 描边语义在 Dashboard 上的映射）。"""
        self._style(speaking=bool(speaking))


class CharacterDashboard(QFrame):
    """右栏双子状态面板：标题 + 拉姆卡 + 蕾姆卡（SPEC-20260922-25 A：**拉姆在上**）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("character_dashboard")
        self.setFixedWidth(LAYOUT.get("dash_w", 320))
        self.setStyleSheet(theme.dashboard_frame())
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        title = QLabel("双子状态")
        title.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        title.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        lay.addWidget(title)

        self.ram_card = CharacterCard("ram", "拉 姆", COLORS["ram_accent"])
        self.rem_card = CharacterCard("rem", "蕾 姆", COLORS["rem_accent"])
        lay.addWidget(self.ram_card)   # SPEC-25 A：拉姆在上
        lay.addWidget(self.rem_card)
        lay.addStretch()

    def set_data(self, rem: Dict[str, Any], ram: Dict[str, Any]) -> None:
        self.rem_card.set_data(**rem)
        self.ram_card.set_data(**ram)

    def set_speaking(self, speaker: Optional[str]) -> None:
        self.rem_card.set_speaking(speaker == "rem")
        self.ram_card.set_speaking(speaker == "ram")
