"""消息控件（头像 / 气泡 / 系统标签 / 聊天消息行）——SPEC-22 S1b 自 gui.py 逐字归位。"""

from __future__ import annotations

import html
import os
from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout, QMenu,
    QSizePolicy, QGraphicsOpacityEffect,
)
from design_tokens import (
    COLORS, DIM, FONT_FAMILY, FONT_SIZE, RADIUS,
    ROLE_BUBBLE_FALLBACK, ROLE_BUBBLE_STYLES, ROLE_COLORS, SPACING, TYPE,
)
from ui import theme
from ui.assets import _asset_path, _svg_pixmap
from ui.app_data import WORLD_FEEDBACK


class AvatarLabel(QLabel):
    """圆形主题头像。优先使用项目资产，避免随系统字体变化的 emoji。"""
    
    SIZE = DIM['avatar_size']  # V10.15c：走 token

    def __init__(self, role: str = "user", parent=None):
        super().__init__(parent)
        self._role = role
        self._pixmap_path: Optional[str] = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['emoji_sm']))
        # V16-M_E：角色色描边环——高清头像 + 角色识别锚点（rem 冰蓝 / ram 蔷薇粉）
        ring = ROLE_COLORS.get(role, COLORS['text_muted'])
        self.setStyleSheet(theme.avatar_label_base(self.SIZE // 2, ring))
        self._emoji_fallback = {"rem": "🩵", "ram": "💗", "user": "🙂", "system": "❄"}.get(role, "·")
        avatar_files = {
            # SPEC-20260922-25 B3：脸部紧裁图优先（256²，头肩完整、脸占比更大）
            "rem": ["rem_face.png", "rem_avatar.png", "rem_avatar.svg"],
            "ram": ["ram_face.png", "ram_avatar.png", "ram_avatar.svg"],
            "user": ["user_avatar.svg"], "system": ["system_avatar.svg"],
        }
        for fname in avatar_files.get(role, ["user_avatar.svg"]):
            path = _asset_path(fname)
            if os.path.isfile(path):
                self.set_image(path)
                break
        else:
            self.setText(self._emoji_fallback)

    def set_image(self, path: str) -> None:
        """加载头像：SVG 走 QSvgRenderer 显式渲染（EXE 稳健），位图走 QPixmap。

        渲染失败回退角色 emoji（避免空白圆）。
        """
        self._pixmap_path = path
        if path.lower().endswith(".svg"):
            pm = _svg_pixmap(path, self.SIZE)
            if not pm.isNull():
                self.setPixmap(pm)
                self.setText("")
                return
            self.setText(self._emoji_fallback)
            return
        pixmap = QPixmap(path).scaled(
            self.SIZE, self.SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(pixmap)
        self.setText("")


class BubbleWidget(QFrame):
    """聊天气泡（V10.9.0 暗色差异化）。V11.10.0 加 highlight 变体，V11.10.1 加 streaming 弱变体。"""

    def __init__(self, text: str, role: str, variant: str = "normal", parent=None):
        super().__init__(parent)
        self.setObjectName("bubble")

        # V10.15a：角色色统一走 ROLE_BUBBLE_STYLES 字典
        style = ROLE_BUBBLE_STYLES.get(role, ROLE_BUBBLE_FALLBACK)

        # V11.10.0：highlight 变体 — 角色色不变，左边线加粗 + 底色增强
        # V11.10.1：streaming 变体 — 底色极淡 + 边线细弱 + 文字暗一档 + 「生成中…」标签
        if variant == "highlight":
            bg = style.get("hl_bg", style["bg"])
            border_css = style.get("hl_border", style["border"])
            fg = style["fg"]
        elif variant == "streaming":
            bg = style.get("stream_bg", style["bg"])
            border_css = style.get("stream_border", style["border"])
            fg = style.get("stream_fg", style["fg"])
        else:
            bg = style["bg"]
            border_css = style["border"]
            fg = style["fg"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 高光顶部弱标签（角色色浅字，非系统金灰）
        if variant == "highlight":
            tag = QLabel("约定")
            tag.setObjectName("bubble_tag")
            tag.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['caption']))
            tag.setStyleSheet(
                theme.bubble_tag_role(role)
            )
            layout.addWidget(tag)

        # V11.10.1：streaming 顶部「生成中…」弱标签（text_muted 灰）
        if variant == "streaming":
            tag = QLabel(WORLD_FEEDBACK.get(role, "双子正在准备回应…"))
            tag.setObjectName("bubble_tag")
            tag.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['caption']))
            tag.setStyleSheet(
                theme.bubble_tag_muted()
            )
            layout.addWidget(tag)

        label = QLabel(text)
        label.setObjectName("bubble_text")
        label.setWordWrap(True)
        # V14.5：显式 RichText——让 QSS line-height:150% 生效（QLabel 默认 AutoText
        # 纯文本渲染不应用 line-height）；文本需 HTML 转义防注入（highlight_plain_text 已转义）
        label.setTextFormat(Qt.RichText)
        if "<" not in text:  # 纯文本（无高亮 span）→ 转义后渲染
            escaped = html.escape(text)
            # V14.8 体验侧：多段回复（同角色多句）段间空行——用 <p> 段落 margin
            if "\n" in escaped:
                paras = [p for p in escaped.split("\n") if p.strip()]
                if len(paras) > 1:
                    body = "".join(f'<p style="margin:0 0 6px 0;">{p}</p>' for p in paras)
                    label.setText(f'<div style="line-height:{TYPE["lh_body_pct"]}%;">{body}</div>')
                else:
                    label.setText(escaped)
            else:
                label.setText(escaped)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg']))
        label.setContentsMargins(0, 0, 0, 0)  # V10.14：去除双重 padding，统一由 QSS 控制
        label.setStyleSheet(theme.bubble_body(bg, fg, border_css))
        layout.addWidget(label)

    def set_text(self, text: str) -> None:
        """更新气泡文本（流式追加用）。"""
        label = self.findChild(QLabel, "bubble_text")
        if label:
            label.setText(text)


class SystemLabelWidget(QWidget):
    """系统消息：居中轻标签，无气泡，弱化显示（V10.9.0）。

    普通系统提示 9pt；较长文本（如引言）自动换行，字号 10pt。
    V10.9.2：transient 模式支持自动消失 + 点击关闭。
    V11.12：variant="vignette" 幕间卡变体 — 金色 accent 派生淡底 + 细金边，
    视觉强于 system 灰条、弱于 streaming 草稿泡与正式角色泡。
    V14.0：带 DB id 的系统消息可右键删除（瞬态标签无 id 无菜单）。
    V14.2：带 DB id 的系统消息可引用。
    """
    delete_requested = Signal(int)  # V14.0：删除请求
    quote_requested = Signal(int)   # V14.2：引用请求

    def __init__(self, text: str, transient: bool = False, auto_dismiss_ms: int = 15000, force_center: bool = False, variant: str = "system", message_id: Optional[int] = None, parent=None):
        super().__init__(parent)
        self._transient = transient
        self._dismissed = False
        self.message_id = message_id  # V14.0：DB 记录 id（瞬态标签为 None，无右键菜单）

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING['lg'], SPACING['xs'], SPACING['lg'], SPACING['xs'])
        layout.setSpacing(0)

        is_multiline = '\n' in text
        # 较长或多行文本用 10pt，短提示用 9pt
        font_size = 10 if len(text) > 40 or is_multiline else 9

        label = QLabel(text)
        label.setWordWrap(True)
        # force_center 时强制居中（日更问候多行）；默认多行左对齐、单行居中
        if force_center:
            label.setAlignment(Qt.AlignCenter)
        else:
            label.setAlignment(Qt.AlignLeft if is_multiline else Qt.AlignCenter)
        label.setFont(QFont(FONT_FAMILY['ui'], font_size))  # V10.15a：字体族走 token，字号保留动态逻辑
        label.setMaximumWidth(DIM['bubble_max_w'])

        # transient 模式：鼠标穿透 label 到父 widget，手型光标
        if transient:
            label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.setCursor(Qt.PointingHandCursor)
        else:
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        # 多行用中等圆角，单行用 pill
        radius = RADIUS['medium'] if is_multiline else RADIUS['pill']
        # V11.12：vignette 幕间卡 — 中性金色（非角色色，避免与双子台词混淆），
        # 色值由 accent #c9a96e 派生，内联写法与 stream_bg 既有先例一致。
        if variant == "vignette":
            fg = COLORS['text_secondary']
            bg = "rgba(201,169,110,0.06)"
            border_css = "border: 1px solid rgba(201,169,110,0.18);"
            radius = RADIUS['medium']
            pad_v, pad_h = 10, 20
        else:
            fg = COLORS['system_label_fg']
            bg = COLORS['system_label_bg']
            border_css = ""
            pad_v, pad_h = 6, SPACING['lg']
        label.setStyleSheet(theme.system_label(fg, bg, border_css, radius, pad_v, pad_h))

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        # transient 自动消失定时器
        if transient:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self._dismiss)
            self._timer.start(auto_dismiss_ms)

    def _dismiss(self) -> None:
        """从布局中移除自身并销毁（防重入）。"""
        if self._dismissed:
            return
        self._dismissed = True
        parent_layout = self.parent().layout() if self.parent() else None
        if parent_layout:
            parent_layout.removeWidget(self)
        self.setParent(None)
        self.deleteLater()

    def mousePressEvent(self, event) -> None:
        """transient 模式下点击关闭。"""
        if self._transient:
            self._dismiss()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """V14.0：带 DB id 的系统消息右键删除；V14.2：可引用（瞬态无 id 无菜单）。"""
        if self.message_id is None:
            return
        menu = QMenu(self)
        menu.addAction("引用", lambda: self.quote_requested.emit(self.message_id))
        menu.addAction("删除", lambda: self.delete_requested.emit(self.message_id))
        menu.exec(event.globalPos())

    def set_text(self, text: str) -> None:
        """更新标签文本（流式追加兼容）。"""
        label = self.findChild(QLabel)
        if label:
            label.setText(text)


class ChatMessageWidget(QWidget):
    """一条聊天消息：头像 + 发送者名 + 气泡。

    V10.12：新增 message_id 属性，用于历史浮层点击定位。
    V14.0：右键菜单（撤回/删除）+ 软状态（recalled 占位 / failed 未送达）。
    """
    recall_requested = Signal(int)  # V14.0：撤回请求（仅 user 且 normal）
    delete_requested = Signal(int)  # V14.0：删除请求（任意有 DB id 的消息）
    quote_requested = Signal(int)   # V14.2：引用请求（任意 normal 且有 DB id 的消息）

    def __init__(self, sender: str, text: str, role: str, message_id: Optional[int] = None, variant: str = "normal", parent=None):
        """
        role: "rem" | "ram" | "user" | "system"
        message_id: 对应 ConversationStore 中的记录 id，None 表示不参与定位
        variant: "normal" | "highlight"（V11.10.0）
        """
        super().__init__(parent)
        self.role = role
        self.sender = sender
        self.message_id = message_id  # V10.12：DB 记录 id，供定位查找
        self._status = "normal"  # V14.0：normal|recalled|failed（deleted 的消息直接移除 widget）

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(8)

        # 头像：由主题 SVG 提供，避免系统 emoji 的跨设备差异。
        avatar = AvatarLabel(role)

        # 名字标签
        name_label = QLabel(sender)
        name_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))  # V10.14：去 Bold，弱化角色名层级
        # V10.15a：角色色统一走 ROLE_COLORS 字典
        name_label.setStyleSheet(theme.color_only(ROLE_COLORS.get(role, COLORS['text_muted'])))
        self._name_label = name_label  # V14.0：failed 时追加「（未送达）」标记

        # 气泡
        bubble = BubbleWidget(text, role=role, variant=variant)
        bubble.setMaximumWidth(DIM['bubble_max_w'])
        bubble.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._bubble = bubble

        # V16-M_E：名字行真正显示（原 left_col 为死代码——名字标签从未加入布局，
        # 聊天里只有头像+气泡）。现按概念稿：头像在侧，角色名小字在上、气泡在下。
        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        name_col.addWidget(name_label)
        name_col.addWidget(bubble)
        name_col.addStretch()

        inner = QHBoxLayout()
        inner.setSpacing(8)

        if role == "user":
            name_label.setAlignment(Qt.AlignRight)
            inner.addStretch()
            inner.addLayout(name_col)
            inner.addWidget(avatar, 0, Qt.AlignTop)
        else:
            inner.addWidget(avatar, 0, Qt.AlignTop)
            inner.addLayout(name_col)
            inner.addStretch()

        layout.addLayout(inner)

    def update_text(self, text: str) -> None:
        """流式更新气泡文本。"""
        self._bubble.set_text(text)

    # ── V14.0：软状态与右键菜单 ──

    def set_recalled(self) -> None:
        """撤回占位：保留时间线位置，内容替换为「（已撤回）」轻样式。"""
        self._status = "recalled"
        self._bubble.set_text("（已撤回）")
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.45)
        self.setGraphicsEffect(eff)

    def set_failed(self) -> None:
        """未送达标记：用户句保留原文，名字后缀「（未送达）」+ 弱化。"""
        self._status = "failed"
        if self._name_label is not None:
            self._name_label.setText(f"{self.sender}（未送达）")
        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.55)
        self.setGraphicsEffect(eff)

    def contextMenuEvent(self, event) -> None:
        """右键菜单：引用（normal 且 DB id）/ 撤回（仅 user 且 normal）/ 删除。"""
        if self.message_id is None:
            return  # 无 DB id（瞬态/未落库）不出菜单
        menu = QMenu(self)
        if self._status == "normal":
            menu.addAction("引用", lambda: self.quote_requested.emit(self.message_id))
            if self.role == "user":
                menu.addAction("撤回", lambda: self.recall_requested.emit(self.message_id))
        menu.addAction("删除", lambda: self.delete_requested.emit(self.message_id))
        menu.exec(event.globalPos())


