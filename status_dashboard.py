"""Character Dashboard（V16.0-M_F）：右侧双子状态双卡。

DESIGN 解析 §1.5：右栏不是"联系人"，而是 Character Dashboard——
头像 / 心情 / 当前行为 / 关系阶段 / 好感 / 忠诚，全部属于 Persistent State。

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
    COLORS, DIM, ELEVATION, FONT_FAMILY, FONT_SIZE, RADIUS, SURFACE_TINT,
)

try:
    from PySide6.QtSvg import QSvgRenderer
    _SVG_OK = True
except Exception:  # pragma: no cover
    QSvgRenderer = None
    _SVG_OK = False

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_UI_FONT = FONT_FAMILY["ui"].split(",")[0]


def _avatar_pixmap(role: str, size: int) -> QPixmap:
    """高清圆头像（.png 优先 → .svg 显式渲染 → 空图）。"""
    for fname in (f"{role}_avatar.png", f"{role}_avatar.svg"):
        path = os.path.join(_ASSETS, fname)
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
    """单角色状态卡：头像 | 心情 / 正在做 / 关系阶段 / 好感 / 忠诚。"""

    def __init__(self, role: str, name: str, accent: str, parent=None):
        super().__init__(parent)
        self.role = role
        self._accent = accent
        self.setObjectName(f"dash_card_{role}")
        self._style(speaking=False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # ── 头部：头像 + 名字 + 心情 ──
        head = QHBoxLayout()
        head.setSpacing(10)
        self._avatar = QLabel()
        self._avatar.setFixedSize(46, 46)
        self._avatar.setAlignment(Qt.AlignCenter)
        pm = _avatar_pixmap(role, 46)
        if not pm.isNull():
            self._avatar.setPixmap(pm)
        else:
            self._avatar.setText(name[:1])
        self._avatar.setStyleSheet(
            f"border-radius: 23px; border: 2px solid {accent};")
        head.addWidget(self._avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_label = QLabel(name)
        self._name_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        self._name_label.setStyleSheet(f"color: {accent};")
        info.addWidget(self._name_label)

        self._mood_label = QLabel("😊 平静")
        self._mood_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"]))
        self._mood_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        info.addWidget(self._mood_label)
        head.addLayout(info, 1)
        lay.addLayout(head)

        # ── 明细行 ──
        self._doing_label = self._row("正在做", "—")
        self._stage_label = self._row("关系阶段", "—")
        self._favor_label = self._row("好感", "0 / 100")
        self._lock_row, self._lock_label = self._row_wrap("忠诚锁定", "—")

    def _style(self, speaking: bool) -> None:
        border = self._accent if speaking else COLORS["border_subtle"]
        self.setStyleSheet(f"""
            QFrame#dash_card_{self.role} {{
                background-color: {COLORS['bg_surface']};
                border: 1px solid {border};
                border-top: 1px solid {ELEVATION['glow_top']};
                border-radius: {RADIUS['medium']}px;
            }}
        """)

    def _row_wrap(self, key: str, value: str):
        row = QFrame()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        k = QLabel(key)
        k.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        k.setStyleSheet(f"color: {COLORS['text_muted']};")
        v = QLabel(value)
        v.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        v.setStyleSheet(f"color: {COLORS['text_secondary']};")
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
    """右栏双子状态面板：标题 + 蕾姆卡 + 拉姆卡。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("character_dashboard")
        self.setFixedWidth(DIM.get("dash_w", 320))
        self.setStyleSheet(f"""
            QFrame#character_dashboard {{
                background-color: {SURFACE_TINT['detail']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: {RADIUS['large']}px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        title = QLabel("双子状态")
        title.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_secondary']};")
        lay.addWidget(title)

        self.rem_card = CharacterCard("rem", "蕾 姆", COLORS["rem_accent"])
        self.ram_card = CharacterCard("ram", "拉 姆", COLORS["ram_accent"])
        lay.addWidget(self.rem_card)
        lay.addWidget(self.ram_card)
        lay.addStretch()

    def set_data(self, rem: Dict[str, Any], ram: Dict[str, Any]) -> None:
        self.rem_card.set_data(**rem)
        self.ram_card.set_data(**ram)

    def set_speaking(self, speaker: Optional[str]) -> None:
        self.rem_card.set_speaking(speaker == "rem")
        self.ram_card.set_speaking(speaker == "ram")
