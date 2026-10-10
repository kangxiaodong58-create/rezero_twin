"""Character Dashboard（V16.0-M_F；SPEC-20260922-27 重构）：右侧「双子 · 陪伴状态」侧栏。

DESIGN 解析 §1.5：右栏不是"联系人"，而是 Character Dashboard——
立绘 / 名字 · 心情 / 一句描述 / 关系阶段 · 好感，全部属于 Persistent State。

SPEC-27 重构要点：
- 卡片四段层级：立绘 → 名称(+🔒) · 当前状态 → 一句描述 → 关系阶段 + 弱化好感条；
- 视觉减法：外壳去描边、卡片去顶光边、立绘去独立边框（三层框 → 一层）；
- 折叠：标题行折叠按钮 + 折叠为 44px 竖条；`resizeEvent` 由 shell_setup 驱动自动折叠
  （阈值实测：展开态聊天 <700px 即折叠；手动操作后自动让位）；
- 数据纪律：只展示快照派生的值，业务换算留在 `_update_panels`（不得凭空生成事实）。

设计纪律（沿用）：
- 本模块**只负责展示**：数据由 gui 从 snapshot/world 组装成 dict 注入（`set_data`）；
- 视觉消费 design_tokens；SVG 头像内联 QSvgRenderer 渲染（不依赖 gui，避免循环导入）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from design_tokens import COLORS, FONT_FAMILY, FONT_SIZE, LAYOUT, RADIUS
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
    """高清圆头像（.png 优先 → .svg 显式渲染 → 空图）。SPEC-25 B1：统一资产入口。"""
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
    """单角色卡：立绘 / 名称(+🔒) · 心情 / 一句描述 / 关系阶段 + 好感条（SPEC-27 R3）。"""

    def __init__(self, role: str, name: str, accent: str, parent=None):
        super().__init__(parent)
        self.role = role
        self._accent = accent
        self.setObjectName(f"dash_card_{role}")
        self._style(speaking=False)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        # ── ① 立绘（用户自定义 data/sprites 同样生效；SPEC-27 R4：不再单独描边）──
        self._sprite = QLabel()
        self._sprite.setObjectName(f"dash_sprite_{role}")
        self._sprite.setFixedHeight(LAYOUT.get("dash_sprite_h", 200))
        self._sprite.setAlignment(Qt.AlignCenter)
        self._sprite.setStyleSheet(theme.dash_sprite_frame(role))
        self._load_sprite()
        lay.addWidget(self._sprite)

        # ── ② 名称（+🔒）· 当前状态 ──
        head = QHBoxLayout()
        head.setSpacing(6)
        self._name_label = QLabel(name)
        self._name_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        self._name_label.setStyleSheet(theme.color_only(accent))
        head.addWidget(self._name_label)
        self._lock_icon = QLabel("🔒")           # SPEC-27 R3：锁定 = 名字后缀小图标
        self._lock_icon.setToolTip("忠诚已锁定")
        self._lock_icon.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        self._lock_icon.hide()
        head.addWidget(self._lock_icon)
        head.addStretch()
        self._mood_label = QLabel("😊 平静")
        self._mood_label.setFont(QFont(_UI_FONT, FONT_SIZE["body_lg"]))
        self._mood_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        head.addWidget(self._mood_label)
        lay.addLayout(head)

        # ── ③ 一句描述（来源：world.character_actions）──
        self._desc_label = QLabel("—")
        self._desc_label.setWordWrap(True)
        self._desc_label.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        self._desc_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        lay.addWidget(self._desc_label)

        # ── ④ 关系阶段 + 弱化好感条 ──
        self._favor_row, self._favor_bar, self._favor_label = self._favor_row_widget()  # SPEC-26 D4

    # ── 构造辅助 ────────────────────────────

    def _load_sprite(self) -> None:
        """立绘卡片图；取不到时回退圆头像（B1 修好的资产入口），仍失败留空框。"""
        w = int(LAYOUT.get("dash_w", 288)) - 48       # 侧栏宽 − 侧栏边距 24 − 卡片边距 24
        h = int(LAYOUT.get("dash_sprite_h", 200))
        pm = sprite_card_pixmap(_config.get_data_dir(), self.role, w, h,
                                RADIUS["medium"], COLORS["bg_surface"])
        if pm.isNull():
            pm = _avatar_pixmap(self.role, h)
        if not pm.isNull():
            self._sprite.setPixmap(pm)

    def _favor_row_widget(self):
        """SPEC-26 D4 / SPEC-27 R3④：关系阶段 + 好感细条 + 小字数值（不做 KPI 强调）。"""
        row = QFrame()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        self._stage_label = QLabel("—")
        self._stage_label.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        self._stage_label.setStyleSheet(theme.color_only(COLORS['text_muted']))
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(theme.dash_favor_bar(self._accent))
        val = QLabel("0")
        val.setFont(QFont(_UI_FONT, FONT_SIZE["small"]))
        val.setStyleSheet(theme.color_only(COLORS['text_muted']))
        rl.addWidget(self._stage_label)
        rl.addStretch()
        rl.addWidget(bar, 2)
        rl.addWidget(val)
        self.layout().addWidget(row)
        return row, bar, val

    # ── 状态注入 ────────────────────────────

    def _style(self, speaking: bool) -> None:
        border = self._accent if speaking else COLORS["border_subtle"]
        self.setStyleSheet(theme.card_frame(self.role, border))

    def set_data(self, *, mood: str, doing: str, stage: str,
                 favor: int, locked_icon: bool = False) -> None:
        """注入展示数据（业务换算由调用方完成）。

        SPEC-27 R3：`locked` 形参改为 `locked_icon`（名字后缀 🔒，不再占一整行）。
        """
        self._mood_label.setText(mood)
        self._desc_label.setText(doing or "—")
        self._stage_label.setText(stage or "—")
        self._favor_bar.setValue(max(0, min(100, int(favor))))   # SPEC-26 D4
        self._favor_label.setText(str(int(favor)))
        self._lock_icon.setVisible(bool(locked_icon))

    def set_speaking(self, speaking: bool) -> None:
        """说话高亮（V12.0 描边语义在 Dashboard 上的映射）。"""
        self._style(speaking=bool(speaking))


class CharacterDashboard(QFrame):
    """右栏「双子 · 陪伴状态」：标题 + 折叠操作 + 拉姆卡 + 蕾姆卡（SPEC-27 R1/R2）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("character_dashboard")
        self.setFixedWidth(LAYOUT.get("dash_w", 288))
        self.setStyleSheet(theme.dashboard_frame())
        self._collapsed = False
        self._user_choice = False      # SPEC-27：手动操作后自动折叠让位

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 展开体 ──
        self._expanded = QWidget()
        lay = QVBoxLayout(self._expanded)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)
        self._title_label = QLabel("双子 · 陪伴状态")
        self._title_label.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
        self._title_label.setStyleSheet(theme.dash_title_label())
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        self._fold_btn = QPushButton("◀")
        self._fold_btn.setToolTip("收起侧栏")
        self._fold_btn.setFixedSize(22, 22)
        self._fold_btn.setCursor(Qt.PointingHandCursor)
        self._fold_btn.setStyleSheet(theme.dash_collapse_btn())
        self._fold_btn.clicked.connect(self._on_fold_clicked)
        title_row.addWidget(self._fold_btn)
        lay.addLayout(title_row)

        self.ram_card = CharacterCard("ram", "拉 姆", COLORS["ram_accent"])
        self.rem_card = CharacterCard("rem", "蕾 姆", COLORS["rem_accent"])
        lay.addWidget(self.ram_card)   # SPEC-25 A：拉姆在上
        lay.addWidget(self.rem_card)
        lay.addStretch()
        root.addWidget(self._expanded)

        # ── 折叠条（SPEC-27 R1 / §7.5）──
        self._folded_strip = QWidget()
        self._folded_strip.setObjectName("dash_folded_strip")
        self._folded_strip.setStyleSheet(theme.dash_folded_strip())
        fl = QVBoxLayout(self._folded_strip)
        fl.setContentsMargins(4, 10, 4, 10)
        fl.setSpacing(10)
        self._unfold_btn = QPushButton("▶")
        self._unfold_btn.setToolTip("展开侧栏")
        self._unfold_btn.setFixedSize(22, 22)
        self._unfold_btn.setCursor(Qt.PointingHandCursor)
        self._unfold_btn.setStyleSheet(theme.dash_collapse_btn())
        self._unfold_btn.clicked.connect(self._on_fold_clicked)
        fl.addWidget(self._unfold_btn, 0, Qt.AlignHCenter)
        for _role, ch, accent in (("ram", "拉", COLORS["ram_accent"]),
                                  ("rem", "蕾", COLORS["rem_accent"])):
            lab = QLabel(ch)
            lab.setAlignment(Qt.AlignCenter)
            lab.setFont(QFont(_UI_FONT, FONT_SIZE["body"], QFont.Bold))
            lab.setStyleSheet(theme.dash_folded_name(accent))
            fl.addWidget(lab)
        fl.addStretch()
        self._folded_strip.hide()
        root.addWidget(self._folded_strip)

    # ── 折叠控制（SPEC-27 R1）────────────────

    def _on_fold_clicked(self) -> None:
        self._user_choice = True
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, *, auto: bool = False) -> None:
        """切换折叠态。`auto=True`（来自窗口宽度）在用户手动选择后让位。"""
        if auto and self._user_choice:
            return
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._expanded.setVisible(not collapsed)
        self._folded_strip.setVisible(collapsed)
        self.setFixedWidth(int(LAYOUT.get("dash_folded_w", 44)) if collapsed
                           else int(LAYOUT.get("dash_w", 288)))

    def is_collapsed(self) -> bool:
        return self._collapsed

    # ── 数据注入 ────────────────────────────

    def set_data(self, rem: Dict[str, Any], ram: Dict[str, Any]) -> None:
        self.rem_card.set_data(**rem)
        self.ram_card.set_data(**ram)

    def set_speaking(self, speaker: Optional[str]) -> None:
        self.rem_card.set_speaking(speaker == "rem")
        self.ram_card.set_speaking(speaker == "ram")
