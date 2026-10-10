"""装配（__init__ / 主题 / 机器人 / 事件 / 生命周期 / UI 构建）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import QSequentialAnimationGroup, QSize, QThread, QTimer, Qt
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from design_tokens import COLORS, DIM, FONT_FAMILY, FONT_SIZE, LAYOUT, SPACING
from runtime.forensic import record, shutdown_forensic
from shared.config import get_data_dir
from shared.conversation_store import ConversationStore
from shared.letter_manager import LetterManager
from shared.memory_store import MemoryStore
from shared.search_service import SearchService
from shared.state import StoryArc
from typing import Optional
from ui import theme
from ui.app_data import NAV_ENTRIES
from ui.assets import _asset_path, _backdrop_image_url, _resolve_sprite, _theme_icon
from ui.flags import _VIGNETTE_DISABLED, _side_panels_enabled, _ui_motion_enabled
from ui.history import HistoryOverlay
from ui.logging_util import _log
from ui.overlays import SakuraOverlay
from ui.panels import CharacterPanel
from ui.widgets_message import ChatMessageWidget
from ui.worker import LLMWorker


class ShellSetupMixin:
    """装配（__init__ / 主题 / 机器人 / 事件 / 生命周期 / UI 构建）。"""

    def __init__(self) -> None:
        super().__init__()
        _log("TwinChatApp.__init__ 开始 (gui V10.4.0, frozen-safe data dir)")
        self.setWindowTitle("❄ Re:Zero 双子系统 — Rem × Ram")
        _win_icon = QIcon()
        _win_icon_path = _asset_path("app_icon.ico")
        if os.path.isfile(_win_icon_path):
            for _sz in (16, 32, 48, 256):
                _win_icon.addFile(_win_icon_path, QSize(_sz, _sz))
        self.setWindowIcon(_win_icon)
        self.setMinimumSize(1000, 650)
        self.resize(1100, 750)

        # 记忆存储（JSON — 硬状态）+ 对话流水（SQLite — 完整历史）
        # MemoryStore() 无参：统一走 get_data_dir()（frozen → EXE 同级 data/）
        # 禁止传 _PROJECT_ROOT：frozen 下指向 _MEIPASS，world_state 会丢
        self.store = MemoryStore()
        # A13（SPEC-20260922-12 B1）：加载期一次性读取 → **局部变量**。
        # 此前是**长期驻留的加载期快照属性**，任何后续代码读它都会静默拿到陈旧值。
        # 运行期需要存档数据时一律 `self.store.load()` 现读（见 `_create_bot`）。
        mem = self.store.load()
        self.conv_store = ConversationStore()
        # SPEC-20260922-19（B7）：搜索单一入口——顶栏与历史浮层共用同一实现
        self.search_service = SearchService(self.conv_store)
        _log(f"记忆加载: arc={mem.get('arc')} data={self.store.path}")

        # 迁移旧 JSON chat_history → SQLite（仅首次）
        old_history = mem.get("chat_history", [])
        if old_history:
            migrated = self.conv_store.migrate_from_json(old_history)
            if migrated:
                _log(f"SQLite 迁移: {migrated} 条旧消息")
                self.store.set("chat_history", [])  # 清空 JSON 中的旧历史

        # A3 收口（SPEC-20260922-12 B2）：`mode` 字段随「本地模板模式下线」一并删除
        # （V14.4 Phase C 起 LLM 已是唯一运行模式，字段早已无实际切换作用）。
        self._streaming_bubbles: list[ChatMessageWidget] = []  # V11.11：多临时泡列表
        self._streaming_buffer: str = ""
        self._streaming_active: bool = False
        self._current_speaker: Optional[str] = None  # V12.0：当前说话人（"rem"/"ram"/None）
        self._breath_group: Optional[QSequentialAnimationGroup] = None  # V12.0：状态栏呼吸组
        _log(f"UI 动效: {'启用' if _ui_motion_enabled() else '禁用'}")
        self._llm_thread: Optional[QThread] = None
        self._llm_worker: Optional[LLMWorker] = None
        self._history_overlay: Optional[HistoryOverlay] = None  # V10.10
        self._session_start_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # V11.6.5
        self._pending_user_widget: Optional[ChatMessageWidget] = None  # V14.0：本轮发送的用户句（取消→failed）
        self._quote: Optional[dict] = None  # V14.2：待发送的引用 {id, sender, preview}
        self.letter_manager = LetterManager()  # V14.3：主动来信控制器（纯模板，零 API 费用）

        # 世界状态（持久化）
        from shared.state import WorldState
        saved_world = mem.get("world_state")
        self.world = WorldState.load_or_create(saved_world)
        _log(f"世界加载: {self.world.period} {self.world.weather}")

        self._setup_ui()
        self._setup_breathing()  # V12.0：状态栏呼吸（_mode_label 已存在）
        self._apply_theme()
        self._load_history()
        self._show_resume_card()  # V11.6.5: 续聊卡（在历史加载后、引言前）

        # 创建 bot
        self.bot = self._create_bot()
        # 注入持久化世界状态
        if hasattr(self.bot, 'world'):
            self.bot.world = self.world
        self._update_status_bar()
        self._update_panels()

        # V11.9.0：开场问候 — 空库完整引言 / 日历日变化日更问候 / 同日轻氛围
        # V14.3：主动来信优先级最高（来信 > 日更问候 > 轻氛围 > 引言）
        today_str = datetime.now().strftime("%Y-%m-%d")
        last_greeting = self.world.last_greeting_date
        day_changed = (last_greeting != today_str)
        msg_count = self.conv_store.count()

        letter = None
        if not _VIGNETTE_DISABLED:
            letter = self._maybe_dispatch_letter(today_str)

        if _VIGNETTE_DISABLED:
            _log("开场引言已通过 REZERO_DISABLE_VIGNETTE 禁用")
        elif letter is not None:
            pass  # V14.3：来信已展示，跳过日更问候/引言/轻氛围（互斥）
        elif msg_count == 0:
            # 空库：保留完整引言路径（V10.4 L0-L3 多级生成）
            _log("空库 → 完整引言 QTimer 注册 (300ms)")
            QTimer.singleShot(300, self._generate_vignette)
        elif day_changed:
            # 非空库 + 日历日变化：日更短问候（不依赖 mode，View-Only）
            _log(f"day_changed=True today={today_str} last={last_greeting}")
            self._show_daily_greeting(today_str)
        else:
            # 同日重开：不打日更问候
            _log(f"already_greeted today={today_str} last={last_greeting}")

        # 轻氛围：同日有历史重开时展示一行（空库完整引言时不重复打）
        if letter is not None:
            pass  # V14.3：来信触发时跳过轻氛围（互斥）
        elif msg_count > 0 and not day_changed:
            self._show_ambient_line()
        elif msg_count > 0 and day_changed:
            # 换日时问候正文已带天气，不额外打轻氛围避免刷屏
            _log("换日：日更问候已含天气，跳过轻氛围避免刷屏")

        # V15.0-M2：纪念卡（纪念日/节日/周年；每类每日至多一张，失败静默）
        try:
            self._maybe_show_memorial_card()
        except Exception as e:
            _log(f"纪念卡流程异常: {e}", durable=True)

        _log("TwinChatApp.__init__ 完成", durable=True)

    @property
    def engine(self):
        return self.bot.engine

    def _apply_theme(self) -> None:
        self.setStyleSheet(theme.app_shell(_backdrop_image_url()))

    # ── Bot 创建 ────────────────────────────

    def _create_bot(self):
        # V14.4（Phase C）：本地模式移除——LLM 是唯一运行模式（退场研判）
        # A13（B1）：存档数据**现读**，不再用加载期快照（陈旧读防线）。
        saved = self.store.load()
        _log("_create_bot: LLM 为唯一运行模式", durable=True)
        try:
            from llm import ReZeroLLMBridge
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                raise ValueError("未找到 DEEPSEEK_API_KEY，请确保 .env 文件在程序同目录下。")
            bot = ReZeroLLMBridge(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                model_name="deepseek-chat",
                arc=StoryArc(saved.get("arc", "mansion_era")),
                max_history=8,
                conversation_store=self.conv_store,
                world=self.world,  # V14.7：注入持久化世界状态（场景切换跨会话保持）
            )
            # V16.1（M2）：存档恢复唯一入口——优先新格式 engine 键，回落旧平铺键。
            # 修 V16.0 及以前的写读不对称：locked 写了不读，oni_stage/witch_scent/
            # turn_count/consecutive_* 根本不落盘（重启归零）。
            saved_engine = saved.get("engine")
            bot.engine.apply_dict(saved_engine if isinstance(saved_engine, dict) else saved)
            _log("LLM bot 创建成功（引擎状态已恢复）", durable=True)
            return bot
        except Exception as e:
            _log(f"LLM bot 创建失败: {e}", durable=True)
            QMessageBox.warning(
                self, "LLM 模式不可用",
                f"{e}\n\nRe:Zero 双子系统需要 LLM API 才能运行。"
                "请确认 .env 中的 DEEPSEEK_API_KEY 正确且余额充足。"
            )
            raise

    # ── 事件过滤 ────────────────────────────

    def eventFilter(self, source, event) -> bool:
        from PySide6.QtCore import QEvent
        # 输入框回车发送
        if source is self.input_box and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self._send_message()
                return True
        # V14.4（Trial #1 B-02）：输入框聚焦高亮——小白首启区分输入框与搜索框
        if source is self.input_box and event.type() == QEvent.FocusIn:
            self.input_box.setStyleSheet(
                theme.input_box_highlight())
        if source is self.input_box and event.type() == QEvent.FocusOut:
            self.input_box.setStyleSheet(
                theme.input_box_normal())
        # 樱花层跟随 viewport 大小变化
        if source is self.scroll.viewport() and event.type() == QEvent.Resize:
            self.sakura.setGeometry(self.scroll.viewport().rect())
        return super().eventFilter(source, event)

    def resizeEvent(self, event) -> None:
        """窗口 resize 时同步浮层遮罩尺寸。"""
        super().resizeEvent(event)
        if self._history_overlay and self._history_overlay.isVisible():
            self._history_overlay.setGeometry(self.rect())
        # SPEC-20260922-24 修订：宽度变化后重算氛围行（整行 ↔ 只留称呼）
        try:
            if getattr(self, "_ambient_label", None) is not None:
                self._refresh_ambient()
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._teardown_llm_thread()  # V13.0：先收尾线程，再存状态（防 worker 写一半）
        self._save_state()
        self._save_session_summary()  # V11.6.5: 写入 session 摘要
        # Forensic M4：正常退出——关闭事件入黑匣子后清理取证（静默失败）
        try:
            record("WINDOW_CLOSE", component="gui")
            shutdown_forensic()
        except Exception:
            pass
        event.accept()

    # ── V13.0：线程收尾与取消 ──────────────────────────

    def _teardown_llm_thread(self) -> None:
        """统一收尾 LLM 工作线程（取消/关窗/切模式/重入共用）。

        顺序：断开信号 → worker.cancel（关底层流）→ requestInterruption →
        quit+wait(2s) → 超时才 terminate（最后手段）→ 置空引用 → 清临时泡。
        不碰 _streaming_active（由调用方管理）。
        """
        if self._llm_worker is not None:
            try:
                self._llm_worker.disconnect()
            except Exception:
                pass
            try:
                self._llm_worker.cancel()
            except Exception as e:
                _log(f"worker.cancel 异常: {e}", durable=True)
        if self._llm_thread is not None:
            if self._llm_thread.isRunning():
                self._llm_thread.requestInterruption()
                self._llm_thread.quit()
                if not self._llm_thread.wait(2000):
                    _log("线程收尾超时（2s），最后手段 terminate", durable=True)
                    self._llm_thread.terminate()
                    self._llm_thread.wait(1000)
        self._llm_worker = None
        self._llm_thread = None
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""

    # ── UI 构建 ────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("app_shell")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 8)
        main_layout.setSpacing(8)

        self._build_top_bar(main_layout)

        # ── 主体三栏布局 ──
        body = QHBoxLayout()
        body.setSpacing(12)
        self._build_side_nav(body)
        chat_section = self._build_chat_area(body)
        self._build_input_area(chat_section)
        body.addLayout(chat_section, LAYOUT['center_stretch'])
        self._build_dashboard(body)
        main_layout.addLayout(body, 1)
        self._build_dock(main_layout)
        self._build_footer(main_layout)

    def _build_top_bar(self, main_layout: QVBoxLayout) -> None:
        # ── 顶部标题栏 ──
        header = QFrame()
        header.setFixedHeight(LAYOUT["header_h"])
        header.setStyleSheet(theme.header_shell())
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 18, 0)

        title_mark = QLabel()
        title_mark.setPixmap(QPixmap(_asset_path("app_icon.png")).scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        header_layout.addWidget(title_mark)
        title = QLabel("Re:zero Twin\n双子系统")
        title.setFont(QFont("Georgia", 18, QFont.Bold))
        title.setStyleSheet(theme.color_only(COLORS['title_pink']))
        header_layout.addWidget(title)
        # A17 已收口（SPEC-20260922-17 步 5）：原两个角色 tab（蕾姆/拉姆）为**装饰性死 UI**
        # ——局部变量、无接线、看着可点却没反应（SPEC-12 B0 已加警示注释）→ 本批**删除**。
        # 双子身份由「双子模式」标识承担；真实篇章切换走命令路由 `/mansion` `/empire` `/late`。
        # 真机确认项：删 tab 后顶栏是否偏空 / 高度是否抖动（审计建议：可给「双子模式」加小图标补空间）。
        twin_mode = QLabel("双子模式")
        twin_mode.setAlignment(Qt.AlignCenter)
        twin_mode.setStyleSheet(theme.twin_mode_chip())
        header_layout.addWidget(twin_mode)
        header_layout.addStretch()

        # V16-M_F：世界状态 ambient（DESIGN 解析 §1.4——环境信息，不要求点击）
        self._ambient_label = QLabel("")
        self._ambient_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self._ambient_label.setStyleSheet(
            theme.ambient_label())
        header_layout.addWidget(self._ambient_label)

        # 历史搜索
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索对话…")
        self.search_box.setFixedWidth(DIM['search_box_w'])
        self.search_box.setFixedHeight(DIM['search_box_h'])
        self.search_box.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self.search_box.setStyleSheet(theme.search_box())
        self.search_box.returnPressed.connect(self._do_search)
        # V14.1：清空搜索框 → 清除全部黄高亮
        self.search_box.textChanged.connect(self._on_top_search_changed)
        header_layout.addWidget(self.search_box)

        # 搜索按钮
        search_btn = QPushButton()
        search_btn.setIcon(_theme_icon("icon_search.svg"))
        search_btn.setIconSize(QSize(17, 17))
        search_btn.setToolTip("搜索对话")
        search_btn.setFixedSize(DIM['icon_btn'], DIM['icon_btn'])
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.setStyleSheet(theme.search_btn())
        search_btn.clicked.connect(self._do_search)
        header_layout.addWidget(search_btn)

        arc_label = QLabel("Arc I · 罗兹瓦尔宅邸")
        arc_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        arc_label.setStyleSheet(theme.color_only(COLORS['accent']))
        self._arc_label = arc_label
        header_layout.addWidget(arc_label)

        # V10.10：历史浮层入口
        history_btn = QPushButton(" 回忆")
        history_btn.setIcon(_theme_icon("icon_memory.svg"))
        history_btn.setIconSize(QSize(16, 16))
        history_btn.setFixedHeight(DIM['history_btn_h'])
        history_btn.setCursor(Qt.PointingHandCursor)
        history_btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        history_btn.setStyleSheet(theme.history_btn())
        history_btn.clicked.connect(self._open_history)
        header_layout.addWidget(history_btn)

        # V15.0-M3：回忆之书入口（概念稿侧栏「回忆之书」位；浮层为独立模块）
        book_btn = QPushButton(" 回忆之书")
        book_btn.setIcon(_theme_icon("icon_book.svg"))
        book_btn.setIconSize(QSize(16, 16))
        book_btn.setFixedHeight(DIM['history_btn_h'])
        book_btn.setCursor(Qt.PointingHandCursor)
        book_btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        book_btn.setStyleSheet(theme.book_btn())
        book_btn.clicked.connect(self._open_memory_book)
        header_layout.addWidget(book_btn)

        main_layout.addWidget(header)

    def _build_side_nav(self, body: QHBoxLayout) -> None:
        # ── 参考图式左侧图标导航 ──
        nav = QFrame()
        nav.setObjectName("side_nav")
        nav.setFixedWidth(182)
        nav.setStyleSheet(theme.side_nav_shell())
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 15, 12, 15)
        nav_layout.setSpacing(7)

        # V16-M_F：天气状态块（DESIGN 解析 §1.3——Logo→天气→导航→系统状态）
        self._nav_weather = QLabel("")
        self._nav_weather.setAlignment(Qt.AlignCenter)
        self._nav_weather.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self._nav_weather.setStyleSheet(
            theme.nav_weather_chip())
        nav_layout.addWidget(self._nav_weather)
        nav_sep = QFrame()
        nav_sep.setFixedHeight(1)
        nav_sep.setStyleSheet(theme.nav_sep())
        nav_layout.addWidget(nav_sep)

        # 左导航：由 NAV_ENTRIES 单一真源生成（SPEC-20260922-17 / B5）——
        # 原 7 项硬编码（日程/任务/插件三条同指 /status、「关于」实开历史、「设置」绑空转命令）已合并去重。
        for _idx, _entry in enumerate(NAV_ENTRIES):
            nav_layout.addWidget(self._nav_button(_entry, active=(_idx == 0), variant="side"))
        nav_layout.addStretch()
        # V16-M_F：系统状态块
        self._nav_sysstatus = QLabel("LLM · 记忆同步中")
        self._nav_sysstatus.setAlignment(Qt.AlignCenter)
        self._nav_sysstatus.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['caption']))
        self._nav_sysstatus.setStyleSheet(
            theme.nav_section_hint())
        nav_layout.addWidget(self._nav_sysstatus)
        nav_twins = QLabel()
        nav_twins.setAlignment(Qt.AlignCenter)
        nav_twins.setPixmap(QPixmap(_asset_path("app_icon.png")).scaled(140, 140, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        nav_twins.setFixedHeight(108)
        nav_twins.setStyleSheet(theme.nav_twins_slot())
        nav_layout.addWidget(nav_twins)
        body.addWidget(nav)

        # 左侧：蕾姆面板
        # V14.11：立绘解析优先级 用户自定义（data/sprites）> 内置 assets；拖入信号接线
        # SPEC-20260922-17（步 5 / B3）：默认**不构造**侧边角色面板——原实现构造后无条件 hide()，
        # 却仍有 5 处 update_state/set_speaking/set_sprite 持续推送（台账 B3/D3「双写」债）。
        # `REZERO_SHOW_SIDE_PANELS=1` 可恢复旧行为（含拖入换立绘）。
        self.rem_panel = None
        if _side_panels_enabled():
            self.rem_panel = CharacterPanel(
                "蕾 姆", "🩵", COLORS["rem_accent"],
                sprite_path=_resolve_sprite(get_data_dir(), "rem", _asset_path("rem_sprite.jpg")),
                character_key="rem")
            self.rem_panel.sprite_dropped.connect(
                lambda p: self._on_sprite_dropped("rem", p))
            body.addWidget(self.rem_panel)
            self.rem_panel.hide()  # 左栏由主题导航替代（开关开启时保留拖入换立绘能力）。

    def _build_chat_area(self, body: QHBoxLayout) -> QVBoxLayout:
        # 中间：聊天区域
        chat_section = QVBoxLayout()
        chat_section.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(theme.chat_scroll_area())

        self.chat_container = QWidget()
        self.chat_container.setStyleSheet(theme.transparent_bg())
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.setSpacing(SPACING['xs'])  # V12.1：回合间距 — 基线降到 xs，关系由本条 top margin 表达
        self.chat_layout.setContentsMargins(0, SPACING['sm'], 0, SPACING['sm'])  # V10.14：上下留白
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_container)
        chat_section.addWidget(self.scroll, 1)

        # 樱花飘落叠加层（覆盖聊天区域，不拦截鼠标）
        self.sakura = SakuraOverlay(self.scroll.viewport())
        self.sakura.setGeometry(self.scroll.viewport().rect())
        self.scroll.viewport().installEventFilter(self)
        return chat_section


    def _build_input_area(self, chat_section: QVBoxLayout) -> None:
        # 输入区域
        input_frame = QFrame()
        input_frame.setFixedHeight(DIM['input_frame_h'])
        input_frame.setStyleSheet(theme.input_frame())
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(6)

        # V14.2：引用条（默认隐藏；发起引用后显示「↪ 回复 …」，可 × 取消）
        self._quote_bar = QFrame()
        self._quote_bar.setObjectName("quote_bar")
        self._quote_bar.setStyleSheet(
            theme.quote_bar()
        )
        quote_layout = QHBoxLayout(self._quote_bar)
        quote_layout.setContentsMargins(10, 3, 6, 3)
        quote_layout.setSpacing(6)
        self._quote_label = QLabel("")
        self._quote_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self._quote_label.setStyleSheet(theme.quote_label())
        quote_layout.addWidget(self._quote_label, 1)
        self._quote_close = QPushButton("×")
        self._quote_close.setFixedSize(20, 20)
        self._quote_close.setCursor(Qt.PointingHandCursor)
        self._quote_close.setToolTip("取消引用")
        self._quote_close.setStyleSheet(theme.quote_close_btn())
        self._quote_close.clicked.connect(self._clear_quote)
        quote_layout.addWidget(self._quote_close)
        self._quote_bar.hide()
        input_layout.addWidget(self._quote_bar)

        # 快捷选项按钮行
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        for i, (label, cmd) in enumerate([
            ("关系状态", "/status"),
            ("宅邸篇", "/mansion"),
            ("帝国篇", "/empire"),
            ("后期篇", "/late"),
        ]):
            btn = QPushButton(label)
            btn.setFixedHeight(DIM['quick_btn_h'])
            btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(theme.quick_action_btn())
            btn.clicked.connect(lambda checked, c=cmd: self._handle_command(c))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        input_layout.addLayout(quick_row)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("和蕾姆、拉姆说点什么吧… (Enter 发送)")
        self.input_box.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg']))
        self.input_box.setFixedHeight(DIM['input_box_h'])
        self.input_box.setStyleSheet(theme.input_box())
        self.input_box.installEventFilter(self)
        input_row.addWidget(self.input_box, 1)

        # V16-M_D：完整创建块恢复（此前布局改版误删——流式"取消"文本与
        # _send_message 信号都挂在 self.send_btn 上，必须保持同一实例）
        self.send_btn = QPushButton("发 送")
        self.send_btn.setStyleSheet(
            theme.send_btn_base())
        self.send_btn.setFixedSize(DIM['send_btn_w'], DIM['send_btn_h'])
        self.send_btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg'], QFont.Bold))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        input_layout.addLayout(input_row)
        chat_section.addWidget(input_frame)

    def _build_dashboard(self, body: QHBoxLayout) -> None:
        # 右侧：拉姆面板（同上：默认不构造；V16-M_F 起右栏由 Character Dashboard 承担）
        self.ram_panel = None
        if _side_panels_enabled():
            self.ram_panel = CharacterPanel(
                "拉 姆", "💗", COLORS["ram_accent"],
                sprite_path=_resolve_sprite(get_data_dir(), "ram", _asset_path("ram_sprite.jpg")),
                character_key="ram")
            self.ram_panel.sprite_dropped.connect(
                lambda p: self._on_sprite_dropped("ram", p))
            body.addWidget(self.ram_panel)
            self.ram_panel.hide()  # 右栏由 Character Dashboard 替代（V16-M_F）。

            # 右栏以双子画面取代单一立绘的留白，让状态面板更接近参考图。
            self.ram_panel.avatar_image.setPixmap(
                QPixmap(_asset_path("app_icon.png")).scaled(160, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        # V16-M_F：右侧 Character Dashboard（DESIGN 解析 §1.5——Persistent State 双卡）
        from ui.dashboard import CharacterDashboard  # SPEC-22 S1c：status_dashboard.py → ui/dashboard.py
        self.dashboard = CharacterDashboard()
        body.addWidget(self.dashboard, LAYOUT['right_stretch'])

    def _build_dock(self, main_layout: QVBoxLayout) -> None:
        # ── 底部图标坞 ──
        dock = QFrame()
        dock.setFixedHeight(58)
        dock.setStyleSheet(theme.dock())
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(20, 5, 20, 5)
        dock_layout.setSpacing(16)
        # 底部图标坞：**同表驱动**（SPEC-20260922-17 / B5；原「主页」与「对话」同动作、
        # 「日程/任务/插件」三条同指 /status → 已去重，现与左导航同为 NAV_ENTRIES 四项）。
        for _entry in NAV_ENTRIES:
            dock_layout.addWidget(self._nav_button(_entry, variant="dock"))
        dock_layout.addStretch()
        main_layout.addWidget(dock)

    def _build_footer(self, main_layout: QVBoxLayout) -> None:
        # ── 底部状态栏 ──
        footer = QFrame()
        footer.setFixedHeight(DIM['footer_h'])
        footer.setStyleSheet(theme.footer())
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 0, 14, 0)

        self.footer_label = QLabel("就绪")
        self.footer_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self.footer_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        footer_layout.addWidget(self.footer_label)
        footer_layout.addStretch()

        mode_label = QLabel("LLM 桥接")
        mode_label.setTextFormat(Qt.RichText)  # V10.14：启用 RichText 主次分层
        mode_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        mode_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        self._mode_label = mode_label
        footer_layout.addWidget(mode_label)

        main_layout.addWidget(footer)

