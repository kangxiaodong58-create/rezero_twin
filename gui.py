"""Re:Zero 双子系统 —— PySide6(Qt) 图形界面聊天窗口。

布局（V16.5+，SPEC-20260922-17 步 5 后）：左侧主题导航 + 中间对话 + 右侧 Character Dashboard
- 蕾姆气泡：蓝色系（#5b9bd5 / #d6e4f0）
- 拉姆气泡：粉色系（#e91e63 / #fce4ec）
- 用户气泡：白色
- 异步 LLM（QThread + Signal）
- 流式输出支持
- /status /empire /mansion /late /recover 命令
- 导航入口单一真源：NAV_ENTRIES（同时驱动左导航与底部图标坞）
- 侧边角色面板默认不构造：REZERO_SHOW_SIDE_PANELS=1 可开启（含拖入换立绘）
"""

from __future__ import annotations

import atexit
import ctypes
import html
import os
import sys
import threading
import time

# ── PyInstaller windowed 模式 (console=False) 下 sys.stdout/stderr 为 None ──
# PySide6 初始化或任何 print/logging 写入 None 会触发 0xC0000409 原生崩溃。
# 三级兜底：EXE同级data/ → %APPDATA%/ReZeroTwin/data → os.devnull
# 保证 stdout/stderr 永不为 None，不依赖 get_data_dir（它在此块之后才可用）。
if getattr(sys, "frozen", False):
    _redir_done = False
    for _target_dir in (
        os.path.join(
            os.path.dirname(os.path.abspath(
                sys.argv[0] if sys.argv else sys.executable)), "data"),
        os.path.join(
            os.environ.get("APPDATA", os.path.expanduser("~")),
            "ReZeroTwin", "data"),
    ):
        try:
            os.makedirs(_target_dir, exist_ok=True)
            _fh = open(os.path.join(_target_dir, "console.log"), "a", encoding="utf-8")
            sys.stdout = _fh
            sys.stderr = _fh
            _redir_done = True
            break
        except OSError:
            continue
    if not _redir_done:
        sys.stdout = open(os.devnull, "w")
        sys.stderr = sys.stdout

import traceback
from datetime import date, datetime
from typing import Optional

# V14.11 Step5：偶发一句注册表（懒加载单例；加载失败 = 空 dict，选型返回 None）
_AMBIENT_REGISTRY: Optional[dict] = None

# SPEC-20260922-22 S1a：路径引导不能再借 `_PROJECT_ROOT`（已归位 ui/assets.py，
# 而 import ui.* 又需要 sys.path 就绪——先有鸡还是先有蛋）⇒ 引导就地自算（与 ui/assets 同式，值恒等）。
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env, get_data_dir
load_env()

# SPEC-20260922-23：定位闪光的净观察窗口（感知链 ≈0.4s：浮层关闭 + 滚动动画），2.0s 偏紧 ⇒ 2.4s
LOCATE_FLASH_MS = 2400

from PySide6.QtCore import (
    Qt, QTimer, Signal, QObject, QThread, QSize,
    QPropertyAnimation, QSequentialAnimationGroup, QAbstractAnimation, QEasingCurve,
)
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QScrollArea,
    QMessageBox, QSizePolicy, QSplitter, QProgressBar, QGraphicsOpacityEffect,
    QMenu,
)

from shared.state import StoryArc, OniStage, FAVOR_LEVEL_CN
from shared.memory_store import MemoryStore
from shared.conversation_store import ConversationStore
from shared.search_service import SearchService, format_preview  # SPEC-20260922-19：搜索单一入口（B7）
from shared.letter_manager import LetterManager  # V14.3：主动来信
# Forensic M4（R1 修复）：GUI/EXE 入口接入取证黑匣子——record 未初始化时为
# 安全 no-op，init_forensic 只在 main() 调用（测试构造 TwinChatApp 不触发）
from runtime.forensic import record, shutdown_forensic, init_forensic

# ── SPEC-20260922-22 S1a：叶子模块归位（re-export 保持 gui.X 可导入）──
from ui.logging_util import _LOG_FH, _LOG_FH_PATH, _LOG_LOCK, _LOG_FSYNC_ALL, _log_path, _log_open_locked, _log_close, _log_write_locked, _log  # noqa: F401
from ui.text import PERIOD_KEYWORDS, WEATHER_EVENT_CONFLICT, highlight_plain_text, event_compatible, format_world_line, match_speaker_tag, _streaming_segments, parse_twin_segments, _rgba_to_qcolor  # noqa: F401
from ui.assets import QSvgRenderer, _SVG_OK, _SPRITE_EXTS, _asset_path, _svg_pixmap, _backdrop_image_url, _theme_icon, _user_sprite_path, _copy_user_sprite, _resolve_sprite  # noqa: F401
from ui.flags import _VIGNETTE_DISABLED, _HISTORY_DISABLED, _ui_motion_enabled, _side_panels_enabled, _get_ambient_registry  # noqa: F401
from ui.app_data import ARC_CN, GREETING_TEMPLATES, NAV_ENTRIES, ONI_STAGE_CN, WEATHER_CLAUSES, WORLD_FEEDBACK  # noqa: F401
from ui.widgets_message import AvatarLabel, BubbleWidget, SystemLabelWidget, ChatMessageWidget  # noqa: F401
from ui.history import HistoryItemWidget, HistoryOverlay  # noqa: F401
from ui.panels import CharacterPanel  # noqa: F401
from ui.overlays import SakuraOverlay  # noqa: F401
from ui.worker import LLMWorker  # noqa: F401

_LOG_PATH = _log_path()

atexit.register(_log_close)   # F13-3：注册在模块导入期（最早时机）

_log(f"=== PySide6 GUI 启动 (python={sys.executable}) ===", durable=True)

# ═══════════════════════════════════════════════
#  Design Tokens（V15.0-M3 出库：design_tokens.py 唯一真源，此处仅转口）
# ═══════════════════════════════════════════════
from design_tokens import (  # noqa: E402
    COLORS, DIM, ELEVATION, FONT_FAMILY, FONT_SIZE, LAYOUT, MOTION,
    RADIUS, RAM_EMOTION_BY_STAGE, RAM_EMOTION_DEFAULT, RAM_EMOTION_ONI,
    RAM_EMOTION_WITCH, ROLE_BUBBLE_FALLBACK, ROLE_BUBBLE_STYLES,
    ROLE_COLORS, SPACING, SURFACE, SURFACE_TINT, TYPE,
)
from ui import theme  # noqa: E402  # SPEC-20260922-18：QSS 单一真源（B6·A14 收口）

# ── SPEC-20260922-22 S1a/S1b：原此处的模块函数与 9 个控件类已归位 ui/ ──
#   叶子：logging_util / text / assets / flags / app_data
#   控件：widgets_message / history / panels / overlays / worker
#   经上方 re-export 保持 gui.X 可导入（接口零变化）
# ═══════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════

class TwinChatApp(QMainWindow):
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

    # ── V15.0-M2：纪念卡 ─────────────────────

    def _maybe_show_memorial_card(self) -> None:
        """纪念日/节日/相识周年 → 生成并展示一张纪念卡（相册落盘，每类每日一张）。

        生成链 L1（LLM，非 frozen/offscreen/有 key 时）→ L2 注册表确定性。
        事实计算与落账复用 _today_facts 同口径（ensure_genesis 幂等）。
        """
        from shared import memorial as memorial_mod
        from shared.anniversary import compute_facts
        from shared.life_ledger import ensure_genesis, record_day_facts
        genesis = ensure_genesis(self.conv_store)
        if genesis is None:
            return
        today = date.today()
        facts = compute_facts(genesis=genesis, today=today)
        if not facts:
            return
        record_day_facts(facts, today)
        kind = next((f.kind for f in facts if f.kind in memorial_mod.CARD_KINDS), None)
        if kind is None or memorial_mod.has_card(kind, today):
            return
        arc_value = getattr(getattr(self.bot, "engine", None), "arc", None)
        arc = getattr(arc_value, "value", "mansion_era")
        safe_path = (getattr(sys, "frozen", False)
                     or os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"
                     or not os.getenv("DEEPSEEK_API_KEY"))
        llm_callable = None
        if not safe_path and hasattr(self.bot, "raw_completion"):
            llm_callable = lambda p: self.bot.raw_completion(  # noqa: E731
                "你是《Re:Zero》双子（蕾姆第三人称自称、拉姆毒舌而温柔）。"
                "写一张纪念卡的正文，30-60 字，只输出正文。",
                p)
        text = memorial_mod.generate(kind, facts=facts, arc=arc, today=today,
                                     llm_callable=llm_callable)
        if not text:
            return
        snapshot = {"arc": arc, "favor": getattr(self.engine, "favor", None),
                    "facts": [f.title for f in facts]}
        path = memorial_mod.save_card(kind, today, text, detail=snapshot)
        self._append_parsed_message(
            "系统", f"━━  ✦ 纪念日  ━━\n{text}\n━━  ✦  ━━",
            "system", save=False, force_center=True, variant="vignette")
        _log(f"纪念卡已生成: kind={kind} path={path}")

    # ── V14.3：主动来信 ────────────────────────

    def _maybe_dispatch_letter(self, today_str: str) -> Optional[dict]:
        """主动来信判定与渲染（启动序列调用；分离以便离屏测试）。

        last_period 回填（方案 C：字段优先，旧存档从 DB 推导）→ 冷却/桶/发件人
        判定 → 触发则落库（role=rem/ram 与正常回复一致）+ 渲染双泡。
        返回 letter 结果（None=未触发，回落既有问候逻辑）。
        """
        self.world.ensure_last_period(self.conv_store)
        letter = self.letter_manager.evaluate_and_dispatch(
            state=self.world,
            favor=self.engine.favor,
            current_weather=self.world.weather,
            now_ts=time.time(),
            today_str=today_str,
            arc=self.engine.arc.value,  # V14.4：篇章感知（帝国篇过滤宅邸深情模板）
        )
        if letter is not None:
            for m in letter["messages"]:
                role = m["sender"]  # "rem" / "ram"
                sender = "蕾 姆" if role == "rem" else "拉 姆"
                self._append_parsed_message(sender, m["content"], role, save=True)
            # V15.0-M1：来信记账（人生账本，每发件人每日一条）
            try:
                from shared.life_ledger import mirror_letter
                for sender_key in sorted({m["sender"] for m in letter["messages"]}):
                    mirror_letter(sender_key)
            except Exception:
                pass
            _log(f"主动来信触发: {len(letter['messages'])} 条"
                 f" (suppress_vignette={letter['suppress_vignette']})", durable=True)
            # A5（SPEC-20260922-14）：冷却写回**即时持久化**。
            # letter_manager 只在内存里改 state.last_letter_ts/date（其注释明写
            # 「调用方负责持久化 world」），此前调用方没做 → 启动即来信后进程被杀，
            # 冷却丢失 → 同日/8h 内可能重复来信。此处补一次落盘（与日更问候/纪念卡同路径）。
            self._save_state()
        return letter

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

    @property
    def engine(self):
        return self.bot.engine

    # ── UI 构建 ────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        central.setObjectName("app_shell")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 8)
        main_layout.setSpacing(8)

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

        # ── 主体三栏布局 ──
        body = QHBoxLayout()
        body.setSpacing(12)

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

        body.addLayout(chat_section, LAYOUT['center_stretch'])

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
        from status_dashboard import CharacterDashboard
        self.dashboard = CharacterDashboard()
        body.addWidget(self.dashboard, LAYOUT['right_stretch'])

        main_layout.addLayout(body, 1)

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

    def _apply_theme(self) -> None:
        self.setStyleSheet(theme.app_shell(_backdrop_image_url()))

    # ── 导航（SPEC-20260922-17 / B5：单一真源 NAV_ENTRIES 驱动左导航 + 底部图标坞）──

    def _nav_button(self, entry: dict, *, active: bool = False, variant: str = "side") -> QPushButton:
        """由 NAV_ENTRIES 表项生成导航按钮（side = 左导航 / dock = 底部图标坞）。

        回调在**构建期**解析（`getattr(self, handler)`）——表里写错方法名会在启动时立刻炸，
        而不是等用户点了才发现（结构断言另有 AST 侧校验）。
        """
        btn = QPushButton(entry["label"])
        btn.setIcon(_theme_icon(entry["icon"]))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(getattr(self, entry["handler"]))
        if variant == "dock":
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(theme.nav_btn_dock())
            return btn
        btn.setIconSize(QSize(21, 21))
        btn.setFixedHeight(43)
        btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body'], QFont.Bold if active else QFont.Normal))
        if active:
            btn.setStyleSheet(theme.nav_btn_dock_active())
        else:
            btn.setStyleSheet(theme.nav_btn_side())
        return btn

    def _nav_focus_input(self) -> None:
        """导航「对话」：聚焦输入框（原左导航/底坞两处 lambda 的唯一化落点）。"""
        self.input_box.setFocus()

    def _nav_open_status(self) -> None:
        """导航「状态」：走唯一命令路由（原「日程/任务/插件」三条同动作入口的合并落点）。"""
        self._handle_command("/status")

    # ── 命令处理 ────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """唯一命令路由（V16.2.1 合并）。

        支持：/status · /mansion · /empire · /late · /recover [0~1]

        ⚠ SPEC-20260922-17（步 5 / R4）：原 `/toggle` `/llm` `/local` 分支已随「设置」入口一并删除
        ——`mode` 特性 V16.4.0 已彻底移除，保留分支只会打印一条无意义提示（空转死链）。
        现敲这些指令会得到「未知指令」（诚实行为，CHANGELOG 已明示）。

        ⚠ 历史坑（V16.0-mf 引入 → V16.2.1 修复）：本类此前在文件后部**再定义了一份**
        同名 `_handle_command`（V16-M_D 导航栏精简版）。类体后定义覆盖前定义 →
        `/mansion /empire /late` 全部落进「未知指令」，且 V10.9.2 的状态面板变成死代码。
        结构回归守卫：`tests/test_command_router.py`（重复方法名 AST 扫描 + 命令覆盖断言）。
        """
        raw = (cmd or "").strip()
        low = raw.lower()
        try:
            if low == "/status":
                # V10.9.2：多行可读排版 + 瞬时消失 + 不存 DB
                state = self.engine.snapshot()
                arc_cn = ARC_CN.get(state.arc.value, state.arc.value)
                favor_cn = FAVOR_LEVEL_CN.get(state.favor_level.name, state.favor_level.name)
                oni_cn = ONI_STAGE_CN.get(state.oni_stage.name, state.oni_stage.name)
                status_text = (
                    f"📊 状态\n"
                    f"篇章：{arc_cn}\n"
                    f"蕾姆：{favor_cn}（{state.favor}）· 独立 {state.independence:.2f}\n"
                    f"拉姆：{state.ram_stage.value}（{state.ram_favor}）\n"
                    f"鬼化：{oni_cn} · 残香 {state.witch_scent}\n"
                    f"⌁ 点击关闭"
                )
                self._append_parsed_message("系统", status_text, "system", save=False, transient=True)
                self._update_panels()
            elif low == "/mansion":
                self._apply_arc(StoryArc.MANSION_ERA, "Arc I · 罗兹瓦尔宅邸", "→ 已切换至宅邸篇")
            elif low == "/empire":
                self._apply_arc(StoryArc.EMPIRE_ERA, "Arc II · 帝国篇", "→ 已切换至帝国篇（失忆）")
            elif low == "/late":
                self._apply_arc(StoryArc.LATE_ARC, "Arc III · 后期篇章", "→ 已切换至后期篇章")
            elif low.startswith("/recover"):
                parts = raw.split()
                try:
                    p = float(parts[1])
                except (IndexError, ValueError):
                    p = 1.0
                self.bot.recover(p)
                self._save_state()      # V16.2：改走唯一保存入口（engine + 平铺键一并落盘）
                self._append_parsed_message("系统", f"→ 记忆恢复进度设为 {p}", "system")
                self._update_panels()
            else:
                self._append_parsed_message(
                    "系统", f"未知指令: {raw}", "system", save=False)
        except Exception as e:
            _log(f"_handle_command 异常: {e}\n{traceback.format_exc()}", durable=True)

    def _apply_arc(self, arc, label: str, message: str) -> None:
        """切换篇章的唯一路径：改状态 → 落盘 → 提示 → 更新标签/状态栏/面板。"""
        self.bot.set_arc(arc)
        self._save_state()              # V16.2：改走唯一保存入口
        self._append_parsed_message("系统", message, "system")
        self._arc_label.setText(label)
        self._update_status_bar()
        self._update_panels()

    # ── 开场引言 ────────────────────────────

    def _generate_vignette(self) -> None:
        """生成开场氛围段。

        v10.4 起走 shared.vignette 的 L0-L3 多级生成：
        L0 缓存 → L1 LLM(重试+校验) → L2 动态模板 → L3 静态兜底。
        引言为 View-Only 数据，绝不写入对话历史（save=False + 不进 messages）。
        V10.10.3：全路径 try-except + 探针日志。
        V10.10.4：frozen EXE 走安全路径（主线程 L2/L3 模板，不创建 QThread 不调 LLM）。
        V11.12：占位消息持有引用删除（替代脆弱的 count-2 位置删除）；
                引言卡使用 vignette 幕间卡变体（强于灰条、弱于角色泡）。
        """
        _log("引言生成触发")
        try:
            if not hasattr(self.bot, 'world'):
                self._append_parsed_message(
                    "系统", "欢迎回到罗兹瓦尔宅邸。输入消息开始对话。", "system", save=False
                )
                return

            placeholder = self._append_parsed_message("系统", "✨ 正在感知宅邸的氛围…", "system", save=False)

            def _on_done(clean: str):
                _log(f"引言回调 _on_done: {clean[:30]}...")
                try:
                    # V11.12：按引用移除占位消息（count-2 位置删除已废弃，
                    # 期间若有其他 widget 插入不会再误删）
                    if placeholder is not None:
                        try:
                            self.chat_layout.removeWidget(placeholder)
                            placeholder.setParent(None)
                            placeholder.deleteLater()
                        except RuntimeError:
                            pass  # 已被销毁（如 MAX_VISIBLE_WIDGETS 淘汰）
                    self._append_parsed_message(
                        "系统", f"━━  ✦  ━━\n{clean}\n━━  ✦  ━━",
                        "system", save=False, force_center=True, variant="vignette")
                    # v10.8.1：将引言氛围注入 Bridge，供首轮对话感知（View-Only，不进 history）
                    if hasattr(self.bot, 'set_opening_atmosphere'):
                        self.bot.set_opening_atmosphere(clean)
                    _log("引言回调完成")
                except Exception as e:
                    _log(f"引言回调异常: {e}\n{traceback.format_exc()}", durable=True)

            # ── V10.10.4 + V14.4: 安全引言路径 ──
            # frozen EXE 下 QThread + LLM 调用触发原生崩溃（0xC0000409）；
            # V14.4（Trial #1 B-01）：离屏环境（QT_QPA_PLATFORM=offscreen）或无
            # API key 同样存在崩溃风险（offscreen 下 QThread+LLM 崩溃），
            # 统一走主线程 L2/L3 模板生成，不创建线程不调 LLM。
            is_offscreen = os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"
            no_api_key = not os.getenv("DEEPSEEK_API_KEY")
            if getattr(sys, "frozen", False) or is_offscreen or no_api_key:
                _log("安全引言路径 (frozen/offscreen/无key)")
                from shared.vignette import VignetteGenerator
                engine = self.bot.engine
                gen = VignetteGenerator(llm_callable=None)  # None → 跳过 L1，直接 L2/L3
                text = gen.generate(
                    self.world,
                    rem_favor_level=engine._get_favor_level().name,
                    independence=engine.independence,
                    ram_stage=engine._get_ram_stage().value,
                    locked=engine.locked,
                    recovery=engine.recovery,
                    oni_warning=(engine.oni_stage != OniStage.NONE),
                    witch_scent=engine.witch_scent,
                    arc=engine.arc.value,  # V14.4：缓存 key 按篇章分桶
                )
                _log(f"模板引言生成完成: {text[:30]}...")
                _on_done(text)
                _log("模板引言已展示")
                return

            # ── 非 frozen：保留现有 LLM Worker 路径 ──
            # 用 raw_completion 绕过角色 system prompt
            class VignetteWorker(QObject):
                finished = Signal(str)
                error = Signal(str)
                def __init__(self, bot, world):
                    super().__init__()
                    self.bot = bot; self.world = world
                def run(self):
                    _log("引言 Worker.run() 开始")
                    try:
                        from shared.vignette import VignetteGenerator
                        engine = self.bot.engine
                        gen = VignetteGenerator(llm_callable=self.bot.raw_completion)
                        text = gen.generate(
                            self.world,
                            rem_favor_level=engine._get_favor_level().name,
                            independence=engine.independence,
                            ram_stage=engine._get_ram_stage().value,
                            locked=engine.locked,
                            recovery=engine.recovery,
                            oni_warning=(engine.oni_stage != OniStage.NONE),
                            witch_scent=engine.witch_scent,
                        )
                        _log(f"引言生成完成: {text[:30]}...")
                        self.finished.emit(text)
                    except Exception as e:
                        _log(f"引言 Worker 异常: {e}\n{traceback.format_exc()}", durable=True)
                        self.error.emit(str(e))

            _log("引言 Worker 创建")
            worker = VignetteWorker(self.bot, self.world)
            worker.finished.connect(_on_done)
            worker.error.connect(
                lambda e: _on_done(f"宅邸的轮廓在{self.world.period}的{self.world.weather}中若隐若现。")
            )
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(thread.deleteLater)
            thread.start()
            _log("引言子线程已启动")
        except Exception as e:
            _log(f"引言生成启动失败: {e}\n{traceback.format_exc()}", durable=True)
            # 降级为静态欢迎语
            try:
                self._append_parsed_message(
                    "系统", "欢迎来到罗兹瓦尔宅邸。", "system", save=False)
            except Exception:
                pass

    # ── 历史搜索 ────────────────────────────

    def _on_top_search_changed(self, text: str) -> None:
        """V14.1：顶栏搜索框清空 → 清除全部黄高亮。"""
        if not text.strip():
            self.clear_all_highlights()

    def _do_search(self) -> None:
        query = self.search_box.text().strip()
        if not query:
            return
        # SPEC-20260922-19（B7）：检索统一走 SearchService（原为直连 conv_store.search，
        # 与历史浮层各写一套）；limit=10 为顶栏有意取值（每条结果渲染成系统条，防刷屏）。
        results = self.search_service.search(query, limit=10)
        self.clear_all_highlights()  # V14.1：新搜索先清旧高亮
        if not results:
            self._append_parsed_message("系统", f"未找到包含「{query}」的对话。", "system", save=False, transient=True)
            return
        # V10.9.2：搜索全部瞬时化——不存 DB、自动消失、可点击关闭
        self._append_parsed_message(
            "系统", f"🔍 搜索「{query}」找到 {len(results)} 条", "system", save=False, transient=True
        )
        # V14.1：命中词黄高亮 + 定位第一条结果（滚动 + 金色 2s）
        self.highlight_hits(query)
        self._locate_message(results[0]["id"])
        for r in results:
            sender = r["sender"]
            text = r["content"]
            created = r.get("created_at", "")
            # 时间截取 MM-DD HH:MM（去掉年份和秒）
            time_str = created[5:16] if len(created) >= 16 else created
            # SPEC-20260922-19：摘要格式抽为纯函数（format_preview 默认 60，值等价迁移）
            preview = format_preview(text)
            self._append_parsed_message(
                "系统", f"{time_str} · {sender} → {preview}", "system", save=False, transient=True
            )

    # ── V14.1：搜索命中词黄高亮 ────────────────────

    def highlight_hits(self, keyword: str) -> None:
        """遍历可见消息 widget，把命中词标为黄底（DB/status/content 零改动）。

        仅处理 ChatMessageWidget 且 message_id 且 _status=='normal'
        （recalled 占位无原文、deleted 已移除、failed 不命中搜索）。
        """
        if not keyword:
            return
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if not isinstance(w, ChatMessageWidget):
                continue
            if not getattr(w, "message_id", None) or getattr(w, "_status", "normal") != "normal":
                continue
            try:
                record = self.conv_store.get_by_id(w.message_id)
                if not record:
                    continue
                content = record.get("content", "")
                if not content:
                    continue
                label = w._bubble.findChild(QLabel, "bubble_text")
                if label is None:
                    continue
                label.setText(highlight_plain_text(content, keyword))
                w._search_hit_text = content  # 原文留存，供 clear 恢复
            except Exception as e:
                _log(f"高亮异常 #{getattr(w, 'message_id', '?')}: {e}", durable=True)

    def clear_all_highlights(self) -> None:
        """清除全部黄高亮（恢复原文）。幂等；无高亮时无副作用。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if not isinstance(w, ChatMessageWidget):
                continue
            orig = getattr(w, "_search_hit_text", None)
            if orig is None:
                continue
            label = w._bubble.findChild(QLabel, "bubble_text")
            if label is not None:
                label.setText(orig)
            if hasattr(w, "_search_hit_text"):
                del w._search_hit_text

    # ── 消息处理 ────────────────────────────

    MAX_VISIBLE_WIDGETS = 80  # 最多保留 80 条消息 widget

    # ── V12.1 回合间距（Conversation Turn Rhythm）────────────────

    def _turn_top_margin(self, role: str) -> int:
        """V12.1：按「最近正式消息」的 role 计算本条 top margin（O(1) 回看）。

        跳过 streaming 临时泡（objectName=="__streaming_temp__"，最多回看 8 个），
        使正式泡顶替临时泡时间距一致（删临时泡零跳变）。
        判定顺序：首条→sm / 涉 system→sm / 同 speaker→xs / 涉 user→lg / 其余→md。
        全部 try/except，异常兜底 sm。
        """
        try:
            i = self.chat_layout.count() - 2  # stretch 前最后一条
            steps = 0
            while i >= 0 and steps < 8:
                item = self.chat_layout.itemAt(i)
                w = item.widget() if item is not None else None
                if w is None:
                    break
                if w.objectName() == "__streaming_temp__":
                    i -= 1
                    steps += 1
                    continue
                prev_role = getattr(w, "role", "system")
                if prev_role == "system" or role == "system":
                    return SPACING['sm']
                if role == prev_role:
                    return SPACING['xs']
                if role == "user" or prev_role == "user":
                    return SPACING['lg']
                return SPACING['md']
            return SPACING['sm']  # 无正式上一条 / 回看越界
        except Exception:
            return SPACING['sm']

    def _apply_turn_rhythm(self, msg, role: str) -> None:
        """V12.1：按上一条 role 设置本条外层 margins（只动 top，不碰 Bubble 内部）。

        ChatMessageWidget 基线 (12,5,12,5)；SystemLabelWidget 基线 (16,4,16,4)；
        与各自构造处硬编码保持一致。
        """
        try:
            top = self._turn_top_margin(role)
            if isinstance(msg, ChatMessageWidget):
                msg.layout().setContentsMargins(12, top, 12, 5)
            else:
                msg.layout().setContentsMargins(16, top, 16, 4)
        except Exception:
            pass

    def _append_parsed_message(self, sender: str, text: str, role: str, save: bool = True, transient: bool = False, message_id: Optional[int] = None, force_center: bool = False, highlight: bool = False, variant: str = "system", animate: bool = True,
                    motion_delay_ms: int = 0) -> Optional[QWidget]:
        """添加消息 widget。超出上限时移除最早的。

        V10.9.0：system 角色走 SystemLabelWidget 轻标签，其余走 ChatMessageWidget。
        V10.9.2：transient=True 时系统标签自动消失 + 可点击关闭。
        V10.12：message_id 参数透传给 ChatMessageWidget（历史回放带 id）；
                save=True 时捕获 conv_store.append 返回值回填 widget.message_id。
        V11.9.1：force_center 透传给 SystemLabelWidget（日更问候多行居中）。
        V11.10.0：highlight 透传给 ChatMessageWidget（高光变体）。
        V11.12：variant 透传给 SystemLabelWidget（vignette 幕间卡）；
                返回值改为创建的 widget（供占位引用删除等场景，既有调用方不受影响）。
        V12.0：animate 参数 — 正式角色泡（rem/ram/user）200ms opacity 轻入场；
               system 标签恒无入场；历史批量回放传 animate=False 跳过动画。
        """
        if role == "system":
            msg = SystemLabelWidget(text, transient=transient, force_center=force_center,
                                    variant=variant, message_id=message_id)
        else:
            msg = ChatMessageWidget(sender, text, role=role, message_id=message_id,
                                    variant="highlight" if highlight else "normal")
        # V14.0：右键菜单信号接线（仅带 DB id 的消息；瞬态标签无 id 不接线）
        if hasattr(msg, "recall_requested"):
            msg.recall_requested.connect(self._on_recall_request)
        if hasattr(msg, "delete_requested"):
            msg.delete_requested.connect(self._on_delete_request)
        if hasattr(msg, "quote_requested"):
            msg.quote_requested.connect(self._on_quote_request)
        # V12.1：回合间距 — 插入前计算（此时 layout 最后一条才是真正的上一条）
        self._apply_turn_rhythm(msg, role)

        insert_index = self.chat_layout.count() - 1  # 在 stretch 之前插入
        self.chat_layout.insertWidget(insert_index, msg)

        # V12.0：正式角色泡轻入场（system 标签无入场；历史回放由调用方传 animate=False）
        if animate and role != "system":
            self._play_entrance_animation(msg, delay_ms=motion_delay_ms)

        # 限制可见 widget 数量，防止内存泄漏
        visible = self.chat_layout.count() - 1  # 减去末尾 stretch
        while visible > self.MAX_VISIBLE_WIDGETS:
            item = self.chat_layout.itemAt(0)
            if item and item.widget():
                w = item.widget()
                self.chat_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
                visible -= 1
            else:
                break

        if save:
            new_id = self.conv_store.append(role, sender, text)
            if hasattr(msg, "message_id"):
                msg.message_id = new_id  # V10.12：回填 DB id 供定位
        QTimer.singleShot(50, self._scroll_to_bottom)
        return msg

    def _insert_streaming_bubble(self, role: str) -> ChatMessageWidget:
        """插入一个空流式气泡，后续逐 token 填充。

        V11.10.1：使用 variant="streaming" 弱变体，视觉明显弱于正式泡。
        V11.11：临时泡全部 save=False，不写 ConversationStore。
        """
        sender = "蕾 姆" if role == "rem" else ("拉 姆" if role == "ram" else role)
        msg = ChatMessageWidget(sender, "", role=role, variant="streaming")
        msg.setObjectName("__streaming_temp__")  # V12.1：临时泡标记（回合间距跳过用）
        self._apply_turn_rhythm(msg, role)  # V12.1：插入前计算（上一条 = 布局当前最后一条）
        insert_index = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_index, msg)
        QTimer.singleShot(30, self._scroll_to_bottom)
        return msg

    def _clear_streaming_bubbles(self) -> None:
        """V11.11：统一清理所有流式临时泡（finished/error/重入共用）。"""
        for bubble in self._streaming_bubbles:
            try:
                bubble.setParent(None)
                bubble.deleteLater()
            except Exception:
                pass
        self._streaming_bubbles = []
        self._set_speaking_panels(None)  # V12.0：说话态复位（finished/error/重入共用）

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    # ── 发送消息 ────────────────────────────

    def _send_message(self) -> None:
        # V13.0.1：取消优先——流式中即使输入框为空，点发送键也应取消
        # （原「先取 text → 空输入 return」会挡住取消入口：发完消息输入框已清空）
        if self._streaming_active:
            self._cancel_streaming()
            return
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        _log(f"发送: {text[:40]}")

        self.input_box.clear()
        # V14.0：记录本轮用户句 widget（取消时标记 failed）
        self._pending_user_widget = self._append_parsed_message("你", text, "user")

        # 命令检测（V16.2.1：全部指令收敛到唯一路由 _handle_command）
        if text.startswith("/"):
            self._handle_command(text)
            return

        # 有效对话：刷新世界状态的最后互动时间戳（v10.4）
        if hasattr(self, 'world'):
            self.world.mark_interaction()

        self.footer_label.setText("双子思考中…")
        self.send_btn.setText("取消")  # V13.0：流式中发送键变取消
        self.send_btn.setEnabled(True)
        self._streaming_active = True
        self._set_breathing(False)  # V12.0：思考中暂停状态栏呼吸

        # V14.2：引用——发送时校验被引用消息状态（期间可能被删/撤）
        reply_to = None
        if self._quote is not None:
            try:
                qrec = self.conv_store.get_by_id(self._quote["id"])
            except Exception:
                qrec = None
            if qrec is None or qrec.get("status") != "normal":
                self._append_parsed_message(
                    "系统", "原消息已撤回，引用已取消。", "system", save=False, transient=True)
            else:
                reply_to = {"id": self._quote["id"], "preview": self._quote["preview"]}
            self._clear_quote()  # 引用一次性消费（无论成功与否）

        if hasattr(self.bot, 'chat_stream'):
            self._send_llm_stream(text, reply_to=reply_to)
        else:
            QTimer.singleShot(50, lambda: self._send_sync(text))

    def _send_sync(self, text: str) -> None:
        """同步发送（LLM 同步模式；本地模板模式已下线——A3 收口）。"""
        try:
            reply = self.bot.chat(text)
            _log(f"回复: {reply[:60]}")
        except Exception as e:
            # V11.10.0：错误不走解析器，直接 system 消息
            self._append_parsed_message("系统", f"出错了：{e}", "system")
            self._finish_reply()
            _log(f"异常: {e}", durable=True)
            return

        # V11.10.0：检查场景高光标记
        highlight = hasattr(self.bot, '_active_scene_id') and bool(self.bot._active_scene_id)
        # V13.0：兜底 View-Only（不写 ConversationStore）
        is_fallback = getattr(self.bot, "_last_chat_fallback", False)
        self._parse_twin_reply(reply, highlight=highlight, save=not is_fallback)
        if hasattr(self.bot, '_active_scene_id'):
            self.bot._active_scene_id = None
        self._finish_reply()

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

    def _cancel_streaming(self) -> None:
        """V13.0：用户取消当前流式回复。V14.0：本轮用户句标记未送达（failed）。"""
        _log("用户取消流式回复", durable=True)
        record("UI_EVENT", component="gui", payload_summary="stream_cancelled")  # Forensic M4
        self._teardown_llm_thread()
        self._streaming_active = False
        pending = getattr(self, "_pending_user_widget", None)
        if pending is not None and pending.message_id:
            try:
                self.conv_store.update_status(pending.message_id, "failed")
                pending.set_failed()
                _log(f"取消：用户句 #{pending.message_id} 标记 failed")
            except Exception as e:
                _log(f"失败态标记异常: {e}", durable=True)
        self._pending_user_widget = None
        self._set_breathing(True)  # 恢复状态栏呼吸
        self._set_speaking_panels(None)
        self._update_panels()
        self._update_status_bar()
        self.footer_label.setText("已取消")
        self.send_btn.setText("发送")
        self.send_btn.setEnabled(True)
        self.input_box.setFocus()

    def _send_llm_stream(self, text: str, reply_to: Optional[dict] = None) -> None:
        """LLM 流式发送（异步线程，安全的线程管理）。reply_to: V14.2 引用。"""
        # V13.0：统一走 _teardown_llm_thread 清理旧线程（原 quit/wait/terminate 手写块）
        self._teardown_llm_thread()

        self._streaming_buffer = ""
        # V11.11：重入时清理所有旧临时泡，防止孤儿残留
        self._clear_streaming_bubbles()

        self._llm_thread = QThread()
        self._llm_worker = LLMWorker(self.bot, text, stream=True, reply_to=reply_to)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.stream_token.connect(self._on_stream_token, Qt.QueuedConnection)
        self._llm_worker.finished.connect(self._on_stream_finished, Qt.QueuedConnection)
        self._llm_worker.error.connect(self._on_stream_error, Qt.QueuedConnection)
        self._llm_thread.finished.connect(self._llm_thread.deleteLater)
        self._llm_thread.start()

    def _on_stream_token(self, token: str) -> None:
        self._streaming_buffer += token
        # V11.11：流式分段，按说话人切泡
        segments = _streaming_segments(self._streaming_buffer)
        if not segments:
            return
        # V12.0：当前说话人 = 最后一段 speaker，变化时才点亮对应侧（幂等）
        current = segments[-1][0]
        if current != self._current_speaker:
            self._set_speaking_panels(current)
        # 段数多于当前泡数 → 新增泡
        while len(self._streaming_bubbles) < len(segments):
            speaker, _ = segments[len(self._streaming_bubbles)]
            bubble = self._insert_streaming_bubble(speaker)
            self._streaming_bubbles.append(bubble)
        # 更新各泡文本（纯文本，不含标签）
        for i, (speaker, text) in enumerate(segments):
            if i < len(self._streaming_bubbles):
                self._streaming_bubbles[i].update_text(text)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _on_stream_finished(self, _final: str = "") -> None:
        # V13.0：校验失败回传——丢弃未通过校验的全文，展示 View-Only 回避文案
        stream_ok = getattr(self.bot, "_last_stream_ok", None)
        if stream_ok is False:
            _log("流式校验失败：丢弃未校验全文，展示 View-Only 回避文案", durable=True)
            self._clear_streaming_bubbles()
            self._streaming_buffer = ""
            fallback_text = (
                getattr(self.bot, "_stream_fallback_text", "")
                or '【蕾姆】: "……这个话题，蕾姆想先放一放。您愿意说点别的吗？"'
            )
            self._parse_twin_reply(fallback_text, highlight=False, save=False)
            self._finish_reply()
            _log("流式校验失败：已展示回避文案", durable=True)
            return
        buffered = self._streaming_buffer or _final
        # V11.10.1：先解析插入正式泡，再删临时泡（减少空白帧跳变）
        if buffered.strip():
            # V11.10.0：检查场景高光标记
            highlight = hasattr(self.bot, '_active_scene_id') and bool(self.bot._active_scene_id)
            self._parse_twin_reply(buffered, highlight=highlight)
            if hasattr(self.bot, '_active_scene_id'):
                self.bot._active_scene_id = None
        # V11.11：移除所有临时预览泡（正式泡已在上方插入）
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""
        self._finish_reply()
        _log("流式完成")

    def _on_stream_error(self, err: str) -> None:
        self._streaming_active = False
        # V11.11：清理所有临时泡，防止孤儿残留
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""
        self._append_parsed_message("系统", f"出错了：{err}", "system")
        self._finish_reply()
        _log(f"流式错误: {err}", durable=True)

    def _parse_twin_reply(self, reply: str, highlight: bool = False, save: bool = True) -> None:
        """V11.10.0：解析双子回复，缓冲+flush 模型，speaker 继承。

        - 【蕾姆】/【拉姆】→ 切换 speaker，开启新气泡段
        - 无前缀行 → 并入当前 speaker 段（默认 rem）
        - 【系统】→ 提取内容后按无前缀行处理（继承或默认 rem）
        - 禁止 LLM 台词降级 system
        - highlight=True 时标记最后一个 rem 段为高光变体
        - V13.0：save 参数——View-Only 兜底文案传 save=False，不写 ConversationStore
        """
        segments = parse_twin_segments(reply)

        # 找最后一个 rem 段索引（用于 highlight）
        last_rem_idx = -1
        for i in range(len(segments) - 1, -1, -1):
            if segments[i][0] == "rem":
                last_rem_idx = i
                break

        for i, (speaker, text) in enumerate(segments):
            if speaker == "rem":
                self._append_parsed_message("蕾 姆", text, "rem",
                                            highlight=(highlight and i == last_rem_idx),
                                            save=save)
            else:
                self._append_parsed_message("拉 姆", text, "ram", save=save)

    def _finish_reply(self) -> None:
        self._streaming_active = False
        self._pending_user_widget = None  # V14.0：成功完成——本轮用户句不标记 failed
        self._set_speaking_panels(None)  # V12.0：兜底复位说话态（幂等，未亮时不做事）
        self._set_breathing(True)  # V12.0：完成后恢复状态栏呼吸
        self._save_state()
        self._update_panels()
        self._update_status_bar()
        self.footer_label.setText("就绪")
        self.send_btn.setText("发送")  # V13.0：恢复发送态
        self.send_btn.setEnabled(True)
        self.input_box.setFocus()

    # ── 历史加载 ────────────────────────────

    def _load_history(self) -> None:
        recent = self.conv_store.get_recent(limit=30)
        _log(f"_load_history: {len(recent)} 条")
        shown = 0
        for item in recent:
            role = item["role"]
            text = item["content"]
            sender = item["sender"]
            msg_id = item.get("id")  # V10.12：透传 DB id 供定位
            if not text:
                continue
            # V16-M_B：历史回放级联——前 8 条 30ms 错落入場，其后同时出现（宪法 §一.3）
            import motion as _motion_mod
            delays = _motion_mod.stagger_delays(len(recent))
            w = self._append_parsed_message(sender, text, role, save=False, message_id=msg_id,
                                            animate=True, motion_delay_ms=delays[min(shown, len(delays) - 1)])
            # V14.0：软状态渲染——recalled 占位 / failed 未送达标记（deleted 已被 get_recent 过滤）
            status = item.get("status", "normal")
            if status == "recalled" and w is not None:
                w.set_recalled()
            elif status == "failed" and w is not None:
                w.set_failed()
            shown += 1
        _log(f"历史显示: {shown} 条")
        self.clear_all_highlights()  # V14.1：历史重载后清除可能残留的黄高亮
        if shown == 0:
            # V11.6.5: 有上次摘要时不显示欢迎语（续聊卡接管，避免双卡叠放）
            last_summary = None
            try:
                last_summary = self.conv_store.get_last_session_summary()
            except Exception:
                pass
            if not last_summary:
                self._append_parsed_message(
                    "系统",
                    "❄ 欢迎来到 Re:Zero 双子系统。\n"
                    "左侧是蕾姆面板，右侧是拉姆面板。\n"
                    "输入消息开始对话，或使用底部快捷按钮。",
                    "system", save=False,
                )

    # ── 状态同步 ────────────────────────────

    def _update_panels(self) -> None:
        """更新左右角色面板（V11.0：表情扩档 + 状态分层）。"""
        try:
            state = self.engine.snapshot()
        except Exception:
            return

        # ── 蕾姆表情（11 档优先级，命中即停）──
        # 鬼化/残香仅通过表情传达，面板不显示术语
        if state.witch_scent >= 3:
            rem_emotion = "😰"       # P1 魔女侵蚀
        elif state.oni_stage == OniStage.BRINK:
            rem_emotion = "😡"       # P2 失控边缘
        elif state.oni_stage == OniStage.FULL:
            rem_emotion = "😠"       # P3 完全解放
        elif state.oni_stage == OniStage.EMERGING:
            rem_emotion = "😤"       # P4 鬼化显现
        elif state.recovery < 0.3:
            rem_emotion = "😵"       # P5 记忆严重模糊
        elif state.consecutive_negative >= 3:
            rem_emotion = "😟"       # P6 连连受挫
        elif state.locked:
            rem_emotion = "🥰"       # P7 忠诚锁定
        elif state.independence >= 0.6:
            rem_emotion = "😌"       # P8 独立人格
        elif state.favor >= 80:
            rem_emotion = "😍"       # P9 深爱满溢
        elif state.favor < 15:
            rem_emotion = "😐"       # P10 尚且陌生
        else:
            rem_emotion = "😊"       # P11 平静温和

        if self.rem_panel is not None:
            self.rem_panel.update_state(
                favor=state.favor,
                stage=FAVOR_LEVEL_CN.get(state.favor_level.name, state.favor_level.name),
                emotion=rem_emotion,
                locked=state.locked,
                independence=state.independence,
                recovery=state.recovery,
            )

        # ── 拉姆表情（8 档：姐姐危险感知 + 自身阶段）──
        # D3（B2）：档位→表情查表已出库 design_tokens（唯一真源，改表情只改那里）
        if state.witch_scent >= 3:
            ram_emotion = RAM_EMOTION_WITCH    # P1 姐姐的怒意
        elif state.oni_stage >= OniStage.FULL:
            ram_emotion = RAM_EMOTION_ONI      # P2 姐姐的警惕
        else:
            ram_emotion = RAM_EMOTION_BY_STAGE.get(
                state.ram_stage.value, RAM_EMOTION_DEFAULT)

        if self.ram_panel is not None:
            self.ram_panel.update_state(
                favor=state.ram_favor,
                stage=state.ram_stage.value,
                emotion=ram_emotion,
            )

        # V16-M_F：Character Dashboard 数据注入（Persistent State 映射）
        try:
            dashboard = getattr(self, "dashboard", None)
            if dashboard is not None:
                actions = getattr(self.world, "character_actions", {}) or {}
                rem_lock = bool(state.locked)
                dashboard.set_data(
                    rem={"mood": rem_emotion, "doing": actions.get("rem", "—"),
                         "stage": FAVOR_LEVEL_CN.get(state.favor_level.name,
                                                     state.favor_level.name),
                         "favor": state.favor, "locked": rem_lock},
                    ram={"mood": ram_emotion, "doing": actions.get("ram", "—"),
                         "stage": state.ram_stage.value,
                         "favor": state.ram_favor, "locked": None},
                )
        except Exception as e:
            _log(f"Dashboard 更新异常: {e}", durable=True)

    def _refresh_ambient(self) -> None:
        """V16-M_F：世界状态 → 顶部/左导航的映射（DESIGN 解析 §1.4/§1.3）。"""
        try:
            state = self.engine.snapshot()
            ev = self.world.active_event or ""
            # A15（B2）：世界行统一实现——max_event=14 与 " · " 分隔为本站现值（文案零变化）
            ambient = format_world_line(self.world.period, self.world.weather, ev,
                                        max_event=14, prefix="🌙 ")
            if state.user_name:
                ambient += f"  ·  与{state.user_name}同行"
            self._ambient_label.setText(ambient)
            self._nav_weather.setText(f"{self.world.period}\n{self.world.weather}")
            try:
                from shared import life_ledger
                n = life_ledger.get_default_ledger().count()
                self._nav_sysstatus.setText(f"LLM · 人生账本 {n} 条")
            except Exception:
                self._nav_sysstatus.setText("LLM · 记忆同步正常")
        except Exception as e:
            _log(f"ambient 刷新异常: {e}", durable=True)

    def _update_status_bar(self) -> None:
        try:
            self._refresh_ambient()
            state = self.engine.snapshot()
            w = self.world if hasattr(self, 'world') else WorldState.now()
            # 活跃事件可见化：有事件且与 period/weather 相容才追加（V11.9.2）
            ram_part = state.ram_stage.value
            ev = w.active_event or ""
            # A15（B2）：同一实现，head=False 只取事件后缀（16 字 / 双空格分隔为本站现值）
            ram_part += format_world_line(w.period, w.weather, ev,
                                          max_event=16, head=False, suffix_sep="  ·  ")
            # V10.14：RichText 主次分层（金色模式 / 次亮主信息 / 弱化次信息）
            # V14.4（Phase C）：本地模式已移除，状态栏恒定 LLM
            mode_text = "LLM"
            mode_color = COLORS["accent"]
            sep = f'<span style="color:{COLORS["text_muted"]};">  ·  </span>'
            self._mode_label.setText(
                f'<span style="color:{mode_color};">{mode_text}</span>'
                f'{sep}'
                f'<span style="color:{COLORS["text_secondary"]};">{w.period} · {w.weather}  ·  好感 {state.favor}/100</span>'
                f'{sep}'
                f'<span style="color:{COLORS["text_muted"]};">{ram_part}</span>'
            )
        except Exception:
            pass

    # ── V12.0 视觉动效（头像说话态 / 气泡入场 / 状态栏呼吸）────────────

    def _setup_breathing(self) -> None:
        """V12.0：状态栏呼吸 — _mode_label opacity 0.85↔1.0，单程 2s，无限往复。

        _ui_motion_enabled()=False 时不创建任何动画对象（完全静态）。
        """
        if not _ui_motion_enabled():
            return
        try:
            self._breath_effect = QGraphicsOpacityEffect(self._mode_label)
            self._mode_label.setGraphicsEffect(self._breath_effect)
            self._breath_effect.setOpacity(1.0)
            fwd = QPropertyAnimation(self._breath_effect, b"opacity", self._mode_label)
            fwd.setDuration(2000)
            fwd.setStartValue(1.0)
            fwd.setEndValue(0.85)
            fwd.setEasingCurve(QEasingCurve.InOutSine)
            bwd = QPropertyAnimation(self._breath_effect, b"opacity", self._mode_label)
            bwd.setDuration(2000)
            bwd.setStartValue(0.85)
            bwd.setEndValue(1.0)
            bwd.setEasingCurve(QEasingCurve.InOutSine)
            self._breath_group = QSequentialAnimationGroup(self)
            self._breath_group.addAnimation(fwd)
            self._breath_group.addAnimation(bwd)
            self._breath_group.setLoopCount(-1)
            self._breath_group.start()
            _log("状态栏呼吸已启动")
        except Exception as e:
            _log(f"呼吸动画创建异常: {e}", durable=True)
            self._breath_group = None

    def _set_breathing(self, active: bool) -> None:
        """V12.0：呼吸暂停/恢复。思考中 pause（opacity 停在当前值），完成后 resume。"""
        if not _ui_motion_enabled():
            return
        group = getattr(self, "_breath_group", None)
        if group is None:
            return
        try:
            st = group.state()
            if active:
                if st == QAbstractAnimation.Stopped:
                    group.start()
                elif st == QAbstractAnimation.Paused:
                    group.resume()
            else:
                if st == QAbstractAnimation.Running:
                    group.pause()
        except Exception as e:
            _log(f"呼吸暂停/恢复异常: {e}", durable=True)

    def _set_speaking_panels(self, speaker: Optional[str]) -> None:
        """V12.0：点亮/复位侧栏说话描边。speaker=None 全部复位。

        状态跟踪（_current_speaker）不受开关影响；仅 QSS 刷新受动效门控制。
        """
        self._current_speaker = speaker
        if not _ui_motion_enabled():
            return
        try:
            if self.rem_panel is not None:
                self.rem_panel.set_speaking(speaker == "rem")
            if self.ram_panel is not None:
                self.ram_panel.set_speaking(speaker == "ram")
            dashboard = getattr(self, "dashboard", None)
            if dashboard is not None:
                dashboard.set_speaking(speaker)
        except Exception as e:
            _log(f"_set_speaking_panels 异常: {e}", durable=True)

    def _play_entrance_animation(self, widget: QWidget, delay_ms: int = 0) -> None:
        """正式消息泡轻入场（V16-M_B：收敛到 motion.fade_in——MOTION token
        220ms/OutCubic；delay_ms 供历史回放级联）。禁用态 = 立即呈现最终状态，
        零定时器零 effect 残留；effect 卸载由 motion 负责（防离屏渲染残留）。
        """
        try:
            import motion
            motion.fade_in(widget, delay_ms=delay_ms)
        except Exception as e:
            _log(f"入场动画异常: {e}", durable=True)

    # ── V14.2：引用回复 ────────────────────────

    def _on_quote_request(self, message_id: int) -> None:
        """右键「引用」：校验消息仍为 normal，展示引用条。"""
        try:
            record = self.conv_store.get_by_id(message_id)
        except Exception as e:
            _log(f"引用查询异常: {e}", durable=True)
            record = None
        if not record or record.get("status") != "normal":
            self._append_parsed_message(
                "系统", "原消息已撤回，无法引用。", "system", save=False, transient=True)
            return
        preview = (record.get("content") or "").strip()
        if len(preview) > 30:
            preview = preview[:30] + "…"
        self._quote = {"id": message_id, "sender": record.get("sender", ""), "preview": preview}
        self._quote_label.setText(f"↪ 回复 {record.get('sender', '')}：{preview}")
        self._quote_bar.show()

    def _clear_quote(self) -> None:
        """取消引用：清状态 + 隐藏引用条。"""
        self._quote = None
        if hasattr(self, "_quote_bar"):
            self._quote_bar.hide()

    # ── V14.0：撤回 / 删除 ────────────────────────

    def _on_recall_request(self, message_id: int) -> None:
        """撤回：仅 user 消息、created_at 起 3 分钟内、status=normal。"""
        try:
            record = self.conv_store.get_by_id(message_id)
        except Exception as e:
            _log(f"撤回查询异常: {e}", durable=True)
            return
        if not record or record.get("role") != "user" or record.get("status") != "normal":
            return
        # 3 分钟窗口（DB created_at 为权威时间戳，格式 YYYY-MM-DD HH:MM:SS）
        created = record.get("created_at", "")
        try:
            dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            _log(f"撤回：created_at 解析失败 {created!r}", durable=True)
            return
        if (datetime.now() - dt).total_seconds() > 180:
            self._append_parsed_message(
                "系统", "已超过 3 分钟，无法撤回。", "system", save=False, transient=True)
            return
        if QMessageBox.question(self, "撤回消息", "撤回这条消息？") == QMessageBox.Yes:
            # V14.0.1：连带同一次发送产生的助手回复（同轮占位），不连锁整段历史
            recalled_ids = self.conv_store.recall_turn(message_id)
            for mid in recalled_ids:
                self._mark_widget_recalled(mid)
            self._prune_bridge_history()
            _log(f"撤回: #{message_id}（连带同轮 {len(recalled_ids) - 1} 条助手）")

    def _on_delete_request(self, message_id: int) -> None:
        """删除：任意有 DB id 的消息（软删 status=deleted）。"""
        if QMessageBox.question(self, "删除消息", "删除这条消息？此操作不可恢复。") == QMessageBox.Yes:
            self.conv_store.update_status(message_id, "deleted")
            self._remove_widget_by_id(message_id)
            self._prune_bridge_history()
            _log(f"删除: #{message_id}")

    def _prune_bridge_history(self) -> None:
        """V14.0：删除/撤回后重建 bridge.history——已删/已撤内容不进后续 Prompt。"""
        restore = getattr(self.bot, "_restore_history_from_store", None)
        if restore is not None:
            try:
                restore()
            except Exception as e:
                _log(f"history 剪枝失败: {e}", durable=True)

    def _mark_widget_recalled(self, message_id: int) -> None:
        """按 DB id 找到聊天区 widget 并置为撤回占位。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and getattr(w, "message_id", None) == message_id:
                w.set_recalled()
                break

    def _remove_widget_by_id(self, message_id: int) -> None:
        """按 DB id 移除聊天区 widget（保留布局 stretch）。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and getattr(w, "message_id", None) == message_id:
                self.chat_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
                break

    def _save_state(self) -> None:
        try:
            engine = self.engine
            data = self.store.load()
            data.update({
                # A3 收口（B2）：`mode` 不再落盘（本地模式已下线，字段无消费者）
                # V16.1（M2）：单源序列化（新键，含 locked/oni/turn_count 等全字段）
                "engine": engine.to_dict(),
                # 旧平铺键：双写一版（life_archive / 外部读取与回滚兼容，下版本删）
                "arc": engine.arc.value,
                "favor": engine.favor,
                "ram_favor": engine.ram_favor,
                "independence": engine.independence,
                "recovery": engine.recovery,
                "locked": engine.locked,
                "user_name": engine.user_name,
                "events": list(getattr(engine, 'events', [])),
                "world_state": self.world.save_dict() if hasattr(self, 'world') else {},
            })
            self.store.save(data)
            _log("状态保存成功", durable=True)
        except Exception as e:
            _log(f"保存状态失败: {e}", durable=True)

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

    # ── 历史浮层（V10.10） ───────────────────

    def _open_history(self) -> None:
        """懒创建并打开历史浮层。"""
        if _HISTORY_DISABLED:
            _log("历史浮层已通过 REZERO_DISABLE_HISTORY 禁用")
            return
        if self._history_overlay is None:
            self._history_overlay = HistoryOverlay(self.conv_store, parent=self)
            self._history_overlay.closed.connect(self._close_history)
            self._history_overlay.locate_requested.connect(self._locate_message)  # V10.12
        # 跟随窗口尺寸
        self._history_overlay.setGeometry(self.rect())
        # 刷新数据（每次打开都拉最新）
        self._history_overlay.load_recent()
        self._history_overlay.show()
        self._history_overlay.raise_()
        self._history_overlay.setFocus()
        _log("历史浮层已打开")

    # V16.2.1：此处的第二份 `_handle_command`（V16-M_D 导航栏精简版）已删除。
    # 它定义在类体后部 → 覆盖前面那份完整路由，导致 /mansion /empire /late
    # 全部落入「未知指令」。命令路由现只有 gui.py 上部那一份（唯一真源）。

    def _open_memory_book(self) -> None:
        """V15.0-M3：懒创建并打开回忆之书浮层（独立模块 memory_book.py）。"""
        try:
            import memory_book
            if getattr(self, "_memory_book_overlay", None) is None:
                self._memory_book_overlay = memory_book.MemoryBookOverlay(
                    parent=self, conv_store=self.conv_store)
            self._memory_book_overlay._reload()  # 每次打开拉最新（账本/相册轻量）
            self._memory_book_overlay.setGeometry(self.rect())
            self._memory_book_overlay.show()
            self._memory_book_overlay.raise_()
            self._memory_book_overlay.setFocus()
            _log("回忆之书已打开")
        except Exception as e:
            _log(f"回忆之书打开失败: {e}", durable=True)

    def _close_history(self) -> None:
        """关闭历史浮层。"""
        if self._history_overlay:
            self._history_overlay.hide()
            self.clear_all_highlights()  # V14.1：关闭回忆浮层 → 清除黄高亮
            self.input_box.setFocus()
            _log("历史浮层已关闭")

    # ── V10.12：历史条目定位 ───────────────────

    def _locate_message(self, message_id: int, keyword: str = "") -> None:
        """根据 message_id 定位主聊天中的消息 widget。

        成功：关闭浮层 → 滚动到目标 → 短暂高亮（底色 + 可选句级命中标记）→ 恢复
        失败：关闭浮层 → transient 提示（不污染主聊天流）
        keyword：当前搜索词（SPEC-20260922-23 F23-1，浮层 relay 携带；空则只闪光不标句）
        """
        # 1. 关闭浮层
        if self._history_overlay:
            self._history_overlay.hide()

        # message_id 无效（系统消息等）
        if not message_id:
            self._append_parsed_message(
                "系统", "📍 该消息不支持定位。", "system", save=False, transient=True
            )
            return

        # 2. 遍历 chat_layout 查找匹配 message_id 的 widget
        target = None
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            w = item.widget()
            if isinstance(w, ChatMessageWidget) and getattr(w, "message_id", None) == message_id:
                target = w
                break

        # 3. 成功：滚动 + 高亮（色彩定档见 design_tokens.locate_highlight）
        if target is not None:
            self._scroll_to_widget(target)
            self._highlight_widget(target, keyword=keyword)
            self.input_box.setFocus()
            return

        # 4. 失败：从 DB 取内容摘要，transient 提示
        summary = ""
        try:
            record = self.conv_store.get_by_id(message_id)
            if record:
                content = record.get("content", "")
                summary = (content[:60] + "…") if len(content) > 60 else content
        except Exception as e:
            _log(f"定位降级查询异常: {e}", durable=True)

        tip = "📍 该消息不在当前可见范围（可能已随对话滚动移出）。"
        if summary:
            tip += f"内容摘要：{summary}"
        self._append_parsed_message("系统", tip, "system", save=False, transient=True)

    def _scroll_to_widget(self, target) -> None:
        """滚动到目标消息：动效开=平滑滚动（220ms/OutCubic）；关=瞬跳（REZERO_DISABLE_UI_MOTION=1）。"""
        try:
            if not _ui_motion_enabled():
                self.scroll.ensureWidgetVisible(target)
                return
            bar = self.scroll.verticalScrollBar()
            current = bar.value()
            self.scroll.ensureWidgetVisible(target)   # 先借原生实现算出目标位置
            dest = bar.value()
            bar.setValue(current)                      # 回到原位，再动画滚过去
            anim = QPropertyAnimation(bar, b"value", self)
            anim.setDuration(220)
            anim.setStartValue(current)
            anim.setEndValue(dest)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start(QPropertyAnimation.DeleteWhenStopped)
        except Exception as e:  # 动画不可用则降级瞬跳——定位本身不能失败
            _log(f"滚动动画降级为瞬跳: {e}")
            self.scroll.ensureWidgetVisible(target)

    def _highlight_widget(self, widget, keyword: str = "") -> None:
        """短暂高亮目标消息**气泡本体**（暖黄底色 + 可选句级命中标记），LOCATE_FLASH_MS 后恢复。

        SPEC-23 修订（用户真机反馈：只标气泡，角色名/头像不动）：
        把闪光规则**追加**到气泡 label 自己的样式表末尾（同表同优先级 ⇒ 后写的赢），
        原样式存 `widget._locate_orig_style` 供恢复；拿不到气泡时退回容器级。
        """
        try:
            label = self._bubble_text_label(widget)
            target = label if label is not None else widget
            if not hasattr(widget, "_locate_orig_style"):
                widget._locate_orig_style = target.styleSheet()
            target.setStyleSheet(target.styleSheet() + "\n" + theme.locate_highlight())
            self._mark_locate_hit(widget, keyword)
            QTimer.singleShot(LOCATE_FLASH_MS, lambda: self._clear_locate_marks(widget))
        except Exception as e:
            _log(f"高亮异常: {e}", durable=True)

    @staticmethod
    def _bubble_text_label(widget):
        """取气泡文本 label（`QLabel#bubble_text`）——闪光与句级标记的共同落点。"""
        bubble = getattr(widget, "_bubble", None)
        if bubble is None:
            return None
        return bubble.findChild(QLabel, "bubble_text")

    def _mark_locate_hit(self, widget, keyword: str) -> None:
        """把命中词标进目标气泡（DB 原文 → highlight_plain_text 浅档）；无命中则不动。"""
        if not keyword:
            return
        try:
            record = self.conv_store.get_by_id(getattr(widget, "message_id", 0))
            content = (record or {}).get("content", "")
            if not content or keyword not in content:
                return
            label = self._bubble_text_label(widget)
            if label is None:
                return
            widget._locate_hit_text = content          # 原文留存，供 _clear_locate_marks 恢复
            label.setText(highlight_plain_text(content, keyword))
        except Exception as e:
            _log(f"句级定位标记异常: {e}")

    def _clear_locate_marks(self, widget) -> None:
        """恢复定位标记（气泡底色 + 句级标记）。幂等；widget 已销毁时静默返回。"""
        try:
            label = self._bubble_text_label(widget)
        except RuntimeError:
            return  # C++ 对象已销毁（消息在闪光窗口内被删除）
        try:
            orig_style = getattr(widget, "_locate_orig_style", None)
            if label is not None and orig_style is not None:
                label.setStyleSheet(orig_style)
            if hasattr(widget, "_locate_orig_style"):
                del widget._locate_orig_style
        except RuntimeError:
            return
        except Exception as e:
            _log(f"定位底色恢复异常: {e}")
        try:
            orig = getattr(widget, "_locate_hit_text", None)
            if orig is not None:
                if label is not None:
                    label.setText(orig)
                del widget._locate_hit_text
        except Exception as e:
            _log(f"句级标记恢复异常: {e}")

    def resizeEvent(self, event) -> None:
        """窗口 resize 时同步浮层遮罩尺寸。"""
        super().resizeEvent(event)
        if self._history_overlay and self._history_overlay.isVisible():
            self._history_overlay.setGeometry(self.rect())

    # ── V11.6.5: session 摘要（规则生成，不调 LLM）──

    def _generate_session_summary(self) -> Optional[dict]:
        """规则生成 session 摘要（不调 LLM）。

        算法（收紧版）：
        - 优先：自上次 session_summaries.msg_end_id 之后的新消息
        - 若无上次摘要：最近 ≤50 条
        - 统计 user 消息数 = 轮次
        - last_user_excerpt ≤50 字
        """
        try:
            last_summary = self.conv_store.get_last_session_summary()
            after_id = last_summary["msg_end_id"] if last_summary else None

            messages = self.conv_store.get_messages_since(after_id, limit=50)
            if not messages:
                return None

            user_msgs = [m for m in messages if m["role"] == "user"]
            turn_count = len(user_msgs)
            if turn_count == 0:
                return None  # 无用户消息，不算有效 session

            # 最后一条用户消息截断 ≤50 字
            last_user_msg = user_msgs[-1]["content"]
            last_user_excerpt = last_user_msg[:50]
            if len(last_user_msg) > 50:
                last_user_excerpt += "…"

            # 规则摘要文本
            first_user = user_msgs[0]["content"][:20]
            if turn_count <= 2:
                summary_text = f"简短交流了{turn_count}轮"
            elif turn_count <= 5:
                summary_text = f"聊了{turn_count}轮，从「{first_user}」开始"
            else:
                summary_text = f"深入聊了{turn_count}轮，从「{first_user}」开始"

            return {
                "turn_count": turn_count,
                "summary_text": summary_text,
                "last_user_excerpt": last_user_excerpt,
                "msg_start_id": messages[0]["id"],
                "msg_end_id": messages[-1]["id"],
            }
        except Exception as e:
            _log(f"生成 session 摘要失败: {e}", durable=True)
            return None

    def _save_session_summary(self) -> None:
        """关闭时写入 session 摘要（closeEvent 末尾调用，失败不影响主流程）。"""
        try:
            summary = self._generate_session_summary()
            if not summary:
                _log("session 摘要：无有效内容，跳过")
                return
            self.conv_store.save_session_summary(
                started_at=self._session_start_time,
                ended_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                turn_count=summary["turn_count"],
                summary_text=summary["summary_text"],
                last_user_excerpt=summary["last_user_excerpt"],
                msg_start_id=summary["msg_start_id"],
                msg_end_id=summary["msg_end_id"],
            )
            _log(f"session 摘要已保存: turns={summary['turn_count']}")
        except Exception as e:
            _log(f"session 摘要保存失败: {e}", durable=True)

    def _show_daily_greeting(self, today_str: str) -> None:
        """V11.9.1：自然日首次问候 — 表驱动模板，View-Only。

        按当前 period 选骨架模板，天气走 WEATHER_CLAUSES 白名单注入。
        active_event 与天气冲突则跳过 event 并打日志。
        不依赖 mode（local/llm 均展示），不调用 LLM，不进 ConversationStore。
        展示后立即写入 last_greeting_date 并持久化。
        """
        try:
            period = self.world.period
            weather = self.world.weather
            event = self.world.active_event or ""

            # 天气从句：白名单查找，未知天气中性兜底
            weather_clause = WEATHER_CLAUSES.get(weather, "")

            # 事件从句：冲突检测（V11.9.2 统一入口）
            event_clause = ""
            if event:
                if event_compatible(period, weather, event):
                    event_clause = event + "。"
                else:
                    _log(f"日更问候: event与period/weather冲突, skip event. "
                         f"period={period} weather={weather} event={event}")

            template = GREETING_TEMPLATES.get(period, GREETING_TEMPLATES["上午"])
            text = template.format(weather_clause=weather_clause, event_clause=event_clause)
            # V11.12：日更问候与开场引言共用 vignette 幕间卡变体（同为宅邸幕间语义）
            self._append_parsed_message(
                "系统", f"━  ✦  ━\n{text}\n━  ✦  ━",
                "system", save=False, force_center=True, variant="vignette"
            )
            self.world.last_greeting_date = today_str
            # 立即持久化，防止崩溃丢失问候标记
            # V16.2：改走唯一保存入口——此前只 set("world_state") 导致存档里
            # 出现「world 是最新、engine/平铺键是上一轮」的部分保存
            self._save_state()
            _log(f"日更问候已展示: period={period} weather={weather} date={today_str}")
        except Exception as e:
            _log(f"日更问候展示失败: {e}\n{traceback.format_exc()}", durable=True)

    def _show_ambient_line(self) -> None:
        """V11.9.0：同日轻氛围一行 — period · weather · active_event，View-Only。

        V11.9.2：active_event 与 period/weather 语义冲突时省略 event 段并打日志。
        仅在同日有历史重开时展示（空库完整引言时不重复打）。
        save=False，不进 ConversationStore。
        V14.11 Step5：放行时在状态行下附「偶发一句」（registry slot=
        ambient_remark，事件触发 + 冷却 2h + 日 3 条上限，同一事件最多 1 句；
        纯展示不进好感/事件记忆通道）。
        """
        try:
            parts = [self.world.period, self.world.weather]
            event = self.world.active_event or ""
            if event:
                if event_compatible(self.world.period, self.world.weather, event):
                    parts.append(event)
                else:
                    _log(f"轻氛围: event与period/weather冲突, skip event. "
                         f"period={self.world.period} weather={self.world.weather} event={event}")
            text = " · ".join(parts)
            remark = self._pick_ambient_remark()
            extra = f"\n💬 {remark}" if remark else ""
            self._append_parsed_message("系统", f"🌧️ {text}{extra}", "system", save=False)
            _log(f"轻氛围已展示: {text} | 偶发一句: {'有' if remark else '无'}")
        except Exception as e:
            _log(f"轻氛围展示失败: {e}", durable=True)

    def _pick_ambient_remark(self) -> str:
        """V14.11 Step5：选取「偶发一句」。放行判定（WorldState）→ 注册表
        确定性选型（seed=日|事件id）→ 记录冷却。任何失败静默返回空串。"""
        try:
            if not self.world.ambient_remark_allowed():
                return ""
            from shared.template_registry import load_registry, pick as registry_pick
            registry = _get_ambient_registry()
            if not registry:
                return ""
            arc_value = getattr(getattr(self.bot, "engine", None), "arc", None)
            arc = getattr(arc_value, "value", "mansion_era")
            today = datetime.now().strftime("%Y-%m-%d")
            item = registry_pick(
                registry, arc=arc, slot="ambient_remark",
                period=self.world.period, weather=self.world.weather,
                seed=f"{today}|{self.world.active_event_id}")
            if not item:
                return ""
            self.world.record_ambient_remark()
            return item.get("text", "")
        except Exception as e:
            _log(f"偶发一句选取失败: {e}", durable=True)
            return ""

    def _on_sprite_dropped(self, key: str, src: str) -> None:
        """V14.11：立绘拖入——复制到 data/sprites/{key}.{ext}（文件即持久化，
        重启经 _resolve_sprite 自动生效），刷新面板并给系统提示。"""
        try:
            dst = _copy_user_sprite(src, get_data_dir(), key)
            if not dst:
                self._append_parsed_message(
                    "系统", "立绘替换失败：仅支持 PNG/JPG/WEBP 图片。", "system", save=False)
                return
            panel = self.rem_panel if key == "rem" else self.ram_panel
            if panel is None:
                self._append_parsed_message(
                    "系统",
                    "立绘面板未启用（REZERO_SHOW_SIDE_PANELS=1 可开启侧边角色面板）。",
                    "system", save=False)
                return
            if not panel.set_sprite(dst):
                self._append_parsed_message(
                    "系统", "立绘替换失败：图片无法解码。", "system", save=False)
                return
            name = "蕾姆" if key == "rem" else "拉姆"
            self._append_parsed_message(
                "系统", f"已更新{name}的立绘（重启后依然生效）。", "system", save=False)
            _log(f"立绘替换: {key} -> {dst}")
        except Exception as e:
            _log(f"立绘替换异常: {e}", durable=True)

    def _show_resume_card(self) -> None:
        """启动时展示上次 session 摘要（续聊卡）。

        挂载于 _load_history() 之后、引言 QTimer 之前。
        - 无摘要 / 无对话记录 → 不显示
        - save=False，不写 DB
        - 有摘要时已压制欢迎语（_load_history 中处理），避免双卡叠放
        """
        try:
            summary = self.conv_store.get_last_session_summary()
            if not summary:
                return
            if self.conv_store.count() == 0:
                return  # 无对话记录不显示（fresh install 场景）

            ended = summary.get("ended_at", "")
            turns = summary.get("turn_count", 0)
            text_body = summary.get("summary_text", "")
            excerpt = summary.get("last_user_excerpt", "")

            # 格式化时间（只取 日期+时分）
            time_str = ended[:16] if len(ended) >= 16 else ended

            card_text = f"📋 上次对话 · {time_str}\n{text_body}（共{turns}轮）\n"
            if excerpt:
                card_text += f"最后你说：「{excerpt}」\n"
            card_text += "继续输入即可接着聊，或点击右上角宅邸日志查看完整回忆。"

            self._append_parsed_message("系统", card_text, "system", save=False)
            _log(f"续聊卡已展示: turns={turns} time={time_str}")
        except Exception as e:
            _log(f"续聊卡展示失败: {e}", durable=True)

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

def _install_crash_handler() -> None:
    """安装崩溃捕获：excepthook 捕获未处理异常写入日志。"""
    crash_path = os.path.join(get_data_dir(), "crash.log")
    try:
        def _excepthook(exc_type, exc_value, exc_tb):
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _log(f"未捕获异常: {exc_value}\n{msg}", durable=True)
            try:
                with open(crash_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] 未捕获异常:\n{msg}")
            except Exception:
                pass
        sys.excepthook = _excepthook
    except Exception as e:
        _log(f"崩溃处理器安装失败: {e}", durable=True)

def main() -> None:
    _install_crash_handler()
    # Forensic M4（R1 修复）：GUI/EXE 入口启动取证黑匣子。
    # 必须在 _install_crash_handler 之后安装——crash hook 会包装现有
    # excepthook 并在其后透传，gui 的 crash.log 写入不受影响。
    # 案件目录随数据目录走（EXE 下数据目录有 %APPDATA% 回退，根目录可能不可写）。
    try:
        init_forensic(os.path.join(get_data_dir(), "incidents"))
        record("SESSION_START", component="gui")
    except Exception:
        pass  # 取证初始化失败静默，绝不影响 GUI 启动
    try:
        # Windows 任务栏图标修复：在 QApplication 之前设置 AppUserModelID，
        # 否则任务栏将窗口归到默认进程标识，显示系统默认图标而非自定义图标。
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "ReZeroTwin.RemRam.1"
                )
                _log("AppUserModelID 已设置: ReZeroTwin.RemRam.1")
            except Exception as e:
                _log(f"AppUserModelID 设置失败（非致命）: {e}", durable=True)

        app = QApplication(sys.argv)

        # 构建多尺寸 QIcon：显式 addFile 各尺寸，确保任务栏/标题栏各 DPI 均有位图
        icon_path = _asset_path("app_icon.ico")
        icon_exists = os.path.isfile(icon_path)
        _log(f"图标路径: {icon_path} | isfile={icon_exists}")

        app_icon = QIcon()
        if icon_exists:
            for sz in (16, 32, 48, 256):
                app_icon.addFile(icon_path, QSize(sz, sz))
            _log(f"QIcon addFile 完成: 16/32/48/256 from {icon_path}")
        else:
            _log("[警告] 图标文件不存在，QIcon 将为空，任务栏/窗口图标会异常", durable=True)

        # frozen 时仅在主题 SVG 不可用时，用 EXE 内嵌图标作为兜底。
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            try:
                exe_icon = QIcon(sys.executable)
                if app_icon.isNull() and not exe_icon.isNull():
                    app_icon = exe_icon
                    _log(f"frozen 兜底: 使用 EXE 内嵌图标 ({sys.executable})")
                else:
                    _log("frozen 兜底: EXE 内嵌图标为空，保持 ICO 文件图标")
            except Exception as e:
                _log(f"frozen 兜底失败（非致命）: {e}", durable=True)

        app.setWindowIcon(app_icon)
        app.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        app.aboutToQuit.connect(lambda: _log("aboutToQuit 信号触发", durable=True))
        window = TwinChatApp()
        window.show()
        # show 后二次 setWindowIcon：强制任务栏刷新图标关联
        window.setWindowIcon(app_icon)
        _log("show 后二次 setWindowIcon 已执行")
        _log("窗口 show 完成")
        _log("即将进入 app.exec() 事件循环", durable=True)
        ret = app.exec()
        _log(f"app.exec() 返回 {ret}", durable=True)
        sys.exit(ret)
    except Exception as e:
        _log(f"main 异常: {e}\n{traceback.format_exc()}", durable=True)
        raise

if __name__ == "__main__":
    main()
