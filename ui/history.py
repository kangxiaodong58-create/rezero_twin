"""历史浮层（条目 / 浮层）——SPEC-22 S1b 自 gui.py 逐字归位。"""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QHBoxLayout, QVBoxLayout,
    QLineEdit, QPushButton, QScrollArea,
)
from design_tokens import COLORS, DIM, FONT_FAMILY, FONT_SIZE, ROLE_COLORS
from shared.search_service import SearchService
from ui import theme
from ui.text import highlight_plain_text, _rgba_to_qcolor


# SPEC-20260922-23：定位闪光的净观察窗口（感知链 ≈0.4s：浮层关闭 + 滚动动画），2.0s 偏紧 ⇒ 2.4s
# SPEC-20260922-22 S2：自 gui.py 下沉（gui.py 保留 re-export：`gui.LOCATE_FLASH_MS` 契约不变）
LOCATE_FLASH_MS = 2400


class HistoryItemWidget(QFrame):
    """单条历史记录：折叠摘要 / 点击展开全文。

    阅读层级约定（V10.13）：
    1. 第一行：角色名（着色加粗）+ 时间（弱化右对齐）+ 📍按钮
    2. 第二行：正文摘要（最多约 2 行，可换行）
    3. 展开后：完整正文（独立区域，左边线着色）
    """

    clicked = Signal(object)  # 发送自身引用（展开/折叠）
    locate_clicked = Signal(int)  # 定位请求，发送 message_id

    # ── 列表阅读常量（V10.13：统一管理避免硬编码）──
    PREVIEW_WORDS = 80  # 摘要约 2 行
    FONT_ROLE = QFont(FONT_FAMILY['ui'], FONT_SIZE['small'], QFont.Bold)       # V10.15a：走 token
    FONT_TIME = QFont(FONT_FAMILY['ui'], FONT_SIZE['caption'])                 # V10.15a：走 token
    FONT_CONTENT = QFont(FONT_FAMILY['ui'], FONT_SIZE['body'])                 # V10.15a：走 token
    MARGINS = (14, 8, 14, 8)  # left, top, right, bottom
    SPACING = 6  # 内部元素间距
    # V10.15a：角色色引用全局 ROLE_COLORS，不再局部定义

    def __init__(self, record: dict, keyword: str = "", parent=None):
        super().__init__(parent)
        self._record = record
        self._expanded = False
        self.setObjectName("history_item")

        role = record.get("role", "system")
        sender = record.get("sender", "")
        content = record.get("content", "")
        created = record.get("created_at", "")
        time_str = created[5:16] if len(created) >= 16 else created
        msg_id = record.get("id", 0)
        # V14.1：搜索命中词高亮（同一 highlight_plain_text，仅构造期渲染）
        # SPEC-20260922-20：浮层卡片是深底 → 走 dark 档（半透明暖黄底 + 提亮文字）
        content_display = highlight_plain_text(content, keyword, surface="dark")

        sender_color = ROLE_COLORS.get(role, COLORS['text_muted'])  # V10.15a：引用全局 ROLE_COLORS
        content_color = COLORS['text_muted'] if role == "system" else COLORS['text_secondary']
        self._sender_color = sender_color

        # 主布局（V10.13：垂直布局容纳 header + 摘要 + 详情）
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(*self.MARGINS)
        self._layout.setSpacing(self.SPACING)

        # ── 第一行：角色名 + 时间 + 📍（水平布局）──
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self._role_label = QLabel(sender)
        self._role_label.setFont(self.FONT_ROLE)
        self._role_label.setStyleSheet(theme.color_only(sender_color))
        header_row.addWidget(self._role_label)

        header_row.addStretch()

        self._time_label = QLabel(time_str)
        self._time_label.setFont(self.FONT_TIME)
        self._time_label.setStyleSheet(theme.color_only(COLORS['text_muted']))
        header_row.addWidget(self._time_label)

        # 📍 定位按钮（保留 V10.12 功能）
        self._locate_btn = QPushButton("📍")
        self._locate_btn.setFixedSize(DIM['locate_btn'], DIM['locate_btn'])
        self._locate_btn.setCursor(Qt.PointingHandCursor)
        self._locate_btn.setToolTip("回到现场")
        self._locate_btn.setStyleSheet(theme.history_locate_btn())
        self._locate_btn.clicked.connect(lambda: self.locate_clicked.emit(msg_id))
        header_row.addWidget(self._locate_btn)

        self._layout.addLayout(header_row)

        # ── 第二行：正文摘要（最多约 2 行，可换行）──
        preview = content[:self.PREVIEW_WORDS] + ("…" if len(content) > self.PREVIEW_WORDS else "")
        self._preview_label = QLabel(highlight_plain_text(preview, keyword, surface="dark") if keyword else preview)
        self._preview_label.setFont(self.FONT_CONTENT)
        self._preview_label.setStyleSheet(theme.color_only(content_color))
        self._preview_label.setWordWrap(True)
        self._layout.addWidget(self._preview_label)

        # ── 展开态全文（初始隐藏，独立区域 + 左边线着色）──
        self._detail_label = QLabel(content_display if keyword else content)
        self._detail_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._detail_label.setStyleSheet(theme.history_detail(sender_color))
        self._detail_label.hide()
        self._layout.addWidget(self._detail_label)

        self._update_style()

    def _update_style(self) -> None:
        if self._expanded:
            self.setStyleSheet(theme.history_item_expanded(self._sender_color))
        else:
            self.setStyleSheet(theme.history_item_collapsed(self._sender_color))

    def mousePressEvent(self, event) -> None:
        self._expanded = not self._expanded
        self._detail_label.setVisible(self._expanded)
        self._preview_label.setVisible(not self._expanded)
        self._update_style()
        self.clicked.emit(self)


class HistoryOverlay(QWidget):
    """历史回忆浮层：主窗口级非阻塞 overlay。

    半透明遮罩 + 居中卡片，遮罩点击/Esc/关闭按钮均可关闭。
    show() 非 exec()，不阻塞流式输出。
    """

    closed = Signal()
    locate_requested = Signal(int, str)  # SPEC-23：定位请求透传 (message_id, keyword) 给主窗口

    def __init__(self, conv_store, parent=None):
        super().__init__(parent)
        self._conv_store = conv_store
        # SPEC-20260922-19（B7）：复用同一 SearchService 实现（构造签名不变，内部自建）
        self._search_service = SearchService(conv_store)
        self._search_timer: Optional[QTimer] = None
        self._keyword = ""

        # 让遮罩接收鼠标事件（卡片区域靠 geometry 判断）
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.addStretch()

        # 居中卡片容器
        card_wrapper = QHBoxLayout()
        card_wrapper.setContentsMargins(0, 0, 0, 0)
        card_wrapper.addStretch()

        self._card = QFrame()
        self._card.setObjectName("history_card")
        self._card.setFixedWidth(DIM['history_card_w'])
        self._card.setStyleSheet(theme.history_card())
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── 卡片标题栏 ──
        header_frame = QFrame()
        header_frame.setFixedHeight(DIM['history_header_h'])
        header_frame.setStyleSheet(
            theme.history_header_sep()
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 0, 16, 0)

        title = QLabel("📖 宅邸日志")
        title.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title'], QFont.Bold))
        title.setStyleSheet(theme.color_only(COLORS['text_primary']))
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(DIM['icon_btn'], DIM['icon_btn'])
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(theme.history_close_btn())
        close_btn.clicked.connect(self._do_close)
        header_layout.addWidget(close_btn)
        card_layout.addWidget(header_frame)

        # ── 搜索框 ──
        search_frame = QFrame()
        search_frame.setFixedHeight(DIM['history_header_h'])
        search_layout = QHBoxLayout(search_frame)
        search_layout.setContentsMargins(20, 10, 20, 10)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("搜索过往对话…")
        self._search_box.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self._search_box.setStyleSheet(theme.history_search_box())
        self._search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_box)
        card_layout.addWidget(search_frame)

        # ── 历史列表滚动区 ──
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.setFrameShape(QFrame.NoFrame)
        self._list_scroll.setStyleSheet(theme.transparent_bg_color())

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setAlignment(Qt.AlignTop)
        self._list_layout.setSpacing(2)  # V10.13：增加条目间距，提升可读性
        self._list_layout.addStretch()
        self._list_scroll.setWidget(self._list_container)
        card_layout.addWidget(self._list_scroll, 1)

        card_wrapper.addWidget(self._card)
        card_wrapper.addStretch()
        self._outer.addLayout(card_wrapper)
        self._outer.addStretch()

    # ── 公开方法 ──

    def refresh(self) -> None:
        """刷新列表（打开时 / 清空搜索时调用）。"""
        self._keyword = ""
        self._search_box.clear()
        self._load_data([])

    def _load_data(self, records: list, keyword: str = "") -> None:
        """清空列表并填充记录（倒序：最新在上）。keyword 非空时摘要高亮命中词。"""
        self._keyword = keyword or ""  # SPEC-23 F23-1：本次结果集的关键词（📍 relay 时携带）
        # 清空旧 widget
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()

        if not records:
            empty = QLabel("宅邸的走廊还十分安静，尚未留下对话的足迹。")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
            empty.setStyleSheet(theme.empty_hint())
            self._list_layout.insertWidget(0, empty)
            return

        # records 来自 get_recent 已是正序，倒序插入实现最新在上
        for record in reversed(records):
            item_widget = HistoryItemWidget(record, keyword=keyword)  # V14.1：keyword 透传高亮
            item_widget.locate_clicked.connect(lambda mid: self.locate_requested.emit(mid, self._keyword))  # SPEC-23：带关键词
            self._list_layout.insertWidget(self._list_layout.count() - 1, item_widget)

    def load_recent(self) -> None:
        """加载最近 100 条记录。"""
        try:
            records = self._conv_store.get_recent(limit=100)
        except Exception:
            records = []
        self._load_data(records)

    # ── 搜索 ──

    def _on_search_changed(self, text: str) -> None:
        keyword = text.strip()
        self._keyword = keyword
        # debounce 300ms
        if self._search_timer:
            self._search_timer.stop()
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(lambda: self._do_search(keyword))
        self._search_timer.start(300)

    def _do_search(self, keyword: str) -> None:
        if not keyword:
            self.load_recent()
            return
        # SPEC-20260922-19（B7）：检索统一走 SearchService（异常兜底亦在服务层，见其 docstring）
        results = self._search_service.search(keyword, limit=50)
        if not results:
            self._show_no_result(keyword)
            return
        self._load_data(results, keyword=keyword)  # V14.1：命中词黄高亮

    def _show_no_result(self, keyword: str) -> None:
        """清空列表并显示无结果提示。"""
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
        label = QLabel(f"没有找到与「{keyword}」相关的回忆。")
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        label.setStyleSheet(theme.empty_hint())
        self._list_layout.insertWidget(0, label)

    # ── 关闭逻辑 ──

    def _do_close(self) -> None:
        self.hide()
        self.closed.emit()

    def mousePressEvent(self, event) -> None:
        """点击遮罩空白区（卡片外）关闭。"""
        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
        if not self._card.geometry().contains(pos):
            self._do_close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self._do_close()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        """绘制半透明遮罩。"""
        from PySide6.QtGui import QPainter
        painter = QPainter(self)
        painter.fillRect(self.rect(), _rgba_to_qcolor(COLORS['overlay_mask']))
        painter.end()


