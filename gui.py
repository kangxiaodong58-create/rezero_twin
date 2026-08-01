"""Re:Zero 双子系统 —— PySide6(Qt) 图形界面聊天窗口。

布局：左蕾姆面板 + 中间对话 + 右拉姆面板（宅邸×VN 融合）
- 蕾姆气泡：蓝色系（#5b9bd5 / #d6e4f0）
- 拉姆气泡：粉色系（#e91e63 / #fce4ec）
- 用户气泡：白色
- 异步 LLM（QThread + Signal）
- 流式输出支持
- /status /empire /mansion /late /recover /llm /local 命令
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env
load_env()

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QThread
from PySide6.QtGui import QFont, QFontMetrics, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QScrollArea,
    QMessageBox, QSizePolicy, QSplitter,
)

from local import ReZeroTwinSystem
from shared.state import StoryArc
from shared.memory_store import MemoryStore
from shared.conversation_store import ConversationStore

_LOG_PATH = os.path.join(_PROJECT_ROOT, "data", "gui.log")


def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass


_log(f"=== PySide6 GUI 启动 (python={sys.executable}) ===")


# ═══════════════════════════════════════════════
#  颜色方案
# ═══════════════════════════════════════════════
COLORS = {
    "bg_primary": "#f0ebe3",       # 米白背景（仿和纸）
    "bg_secondary": "#ffffff",
    "bg_header": "#3a2f28",        # 深棕顶栏（罗兹瓦尔宅邸木色）
    "bg_sidebar": "#f5f0eb",
    "rem_primary": "#5b9bd5",      # 蕾姆蓝
    "rem_bubble": "#d6e4f0",       # 蕾姆气泡蓝
    "rem_dark": "#3a7cc3",
    "ram_primary": "#e982a5",      # 拉姆粉
    "ram_bubble": "#fce4ec",       # 拉姆气泡粉
    "ram_dark": "#d4687c",
    "user_bubble": "#ffffff",
    "text_primary": "#2c2416",
    "text_secondary": "#6b5e4f",
    "text_light": "#ffffff",
    "border": "#d4c5b2",
    "accent": "#c9a96e",           # 金色点缀
}


class LLMWorker(QObject):
    """后台线程：调用 LLM 生成回复（不冻结 UI）。"""
    finished = Signal(str)           # 完整回复文本
    stream_token = Signal(str)       # 流式 token
    error = Signal(str)

    def __init__(self, bot, user_input: str, stream: bool = True, parent=None):
        super().__init__(parent)
        self.bot = bot
        self.user_input = user_input
        self.stream = stream

    def run(self) -> None:
        try:
            if self.stream and hasattr(self.bot, 'chat_stream'):
                gen, _state = self.bot.chat_stream(self.user_input)
                full = ""
                for token in gen:
                    full += token
                    self.stream_token.emit(token)
                self.finished.emit(full)
            else:
                reply = self.bot.chat(self.user_input)
                self.finished.emit(reply)
        except Exception as e:
            self.error.emit(str(e))


def _asset_path(filename: str) -> str:
    """返回资产文件的绝对路径，兼容 frozen 与源码运行。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", _PROJECT_ROOT)
    else:
        base = _PROJECT_ROOT
    return os.path.join(base, "assets", filename)


# ═══════════════════════════════════════════════
#  聊天气泡组件
# ═══════════════════════════════════════════════

class AvatarLabel(QLabel):
    """圆形头像。支持 emoji 文字或 PNG 图片。"""
    
    SIZE = 42

    def __init__(self, emoji: str = "", parent=None):
        super().__init__(parent)
        self._emoji = emoji
        self._pixmap_path: Optional[str] = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont("Segoe UI Emoji", 20))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg_secondary']};
                border-radius: {self.SIZE // 2}px;
                border: 2px solid {COLORS['border']};
            }}
        """)
        self.setText(emoji)

    def set_image(self, path: str) -> None:
        """加载 PNG 立绘头像。"""
        self._pixmap_path = path
        pixmap = QPixmap(path).scaled(
            self.SIZE, self.SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.setPixmap(pixmap)
        self.setText("")


class BubbleWidget(QFrame):
    """聊天气泡。"""

    def __init__(self, text: str, role: str, parent=None):
        super().__init__(parent)
        self.setObjectName("bubble")

        # 配色
        if role == "rem":
            bg = COLORS["rem_bubble"]
            fg = COLORS["text_primary"]
            border_color = COLORS["rem_primary"]
        elif role == "ram":
            bg = COLORS["ram_bubble"]
            fg = COLORS["text_primary"]
            border_color = COLORS["ram_primary"]
        elif role == "user":
            bg = COLORS["user_bubble"]
            fg = COLORS["text_primary"]
            border_color = COLORS["accent"]
        else:
            bg = COLORS["bg_secondary"]
            fg = COLORS["text_secondary"]
            border_color = COLORS["border"]

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setFont(QFont("Microsoft YaHei", 11))
        label.setContentsMargins(14, 10, 14, 10)
        label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                border: 1px solid {border_color};
                border-radius: 12px;
                padding: 10px 14px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)

    def set_text(self, text: str) -> None:
        """更新气泡文本（流式追加用）。"""
        label = self.findChild(QLabel)
        if label:
            label.setText(text)


class ChatMessageWidget(QWidget):
    """一条聊天消息：头像 + 发送者名 + 气泡。"""

    def __init__(self, sender: str, text: str, role: str, parent=None):
        """
        role: "rem" | "ram" | "user" | "system"
        """
        super().__init__(parent)
        self.role = role
        self.sender = sender

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)
        layout.setSpacing(8)

        # 头像
        if role == "rem":
            emoji = "🩵"
        elif role == "ram":
            emoji = "💗"
        elif role == "user":
            emoji = "👤"
        else:
            emoji = "📢"

        avatar = AvatarLabel(emoji)

        # 名字标签
        name_label = QLabel(sender)
        name_label.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        if role == "rem":
            name_label.setStyleSheet(f"color: {COLORS['rem_dark']};")
        elif role == "ram":
            name_label.setStyleSheet(f"color: {COLORS['ram_dark']};")
        elif role == "user":
            name_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        else:
            name_label.setStyleSheet(f"color: {COLORS['text_secondary']};")

        # 气泡
        bubble = BubbleWidget(text, role=role)
        bubble.setMaximumWidth(600)
        bubble.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._bubble = bubble

        # 左侧列：头像 + 名字
        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        left_col.addWidget(name_label, alignment=Qt.AlignLeft)

        # 右侧列：气泡
        # 组装
        inner = QHBoxLayout()
        inner.setSpacing(8)

        if role == "user":
            inner.addStretch()
            inner.addWidget(bubble)
            inner.addWidget(avatar)
            name_label.setAlignment(Qt.AlignRight)
        else:
            inner.addWidget(avatar)
            inner.addWidget(bubble)
            inner.addStretch()

        layout.addLayout(inner)

    def update_text(self, text: str) -> None:
        """流式更新气泡文本。"""
        self._bubble.set_text(text)


# ═══════════════════════════════════════════════
#  角色侧边面板
# ═══════════════════════════════════════════════

class CharacterPanel(QFrame):
    """角色状态面板：立绘区域 + 好感条 + 状态标签。"""

    def __init__(self, name: str, emoji: str, color: str, sprite_path: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("character_panel")
        self.setFixedWidth(180)
        self.setStyleSheet(f"""
            QFrame#character_panel {{
                background-color: {COLORS['bg_sidebar']};
                border-left: 1px solid {COLORS['border']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(12)

        # 立绘区域
        self.avatar_frame = QFrame()
        self.avatar_frame.setFixedHeight(240)
        self.avatar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_secondary']};
                border: 2px solid {color if sprite_path else 'dashed ' + color};
                border-radius: 12px;
            }}
        """)
        avatar_inner = QVBoxLayout(self.avatar_frame)
        avatar_inner.setContentsMargins(4, 4, 4, 4)

        self.avatar_image = QLabel()
        self.avatar_image.setAlignment(Qt.AlignCenter)
        self.avatar_image.setScaledContents(False)

        if sprite_path and os.path.exists(sprite_path):
            pixmap = QPixmap(sprite_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(160, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.avatar_image.setPixmap(scaled)
            else:
                self.avatar_image.setText(emoji)
                self.avatar_image.setFont(QFont("Segoe UI Emoji", 48))
                self.avatar_image.setAlignment(Qt.AlignCenter)
        else:
            self.avatar_image.setText(emoji)
            self.avatar_image.setFont(QFont("Segoe UI Emoji", 48))
            self.avatar_image.setAlignment(Qt.AlignCenter)
            placeholder = QLabel("立绘区域\n拖入 PNG 图片")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 10px;")
            avatar_inner.addWidget(placeholder)

        avatar_inner.addWidget(self.avatar_image)
        layout.addWidget(self.avatar_frame)

        # 角色名
        name_label = QLabel(name)
        name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(f"color: {color};")
        layout.addWidget(name_label)

        # 好感度标签
        self.favor_label = QLabel("好感：--/100")
        self.favor_label.setFont(QFont("Microsoft YaHei", 10))
        self.favor_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.favor_label)

        # 阶段标签
        self.stage_label = QLabel("阶段：--")
        self.stage_label.setFont(QFont("Microsoft YaHei", 10))
        self.stage_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self.stage_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stage_label)

        # 情绪标签
        self.emotion_label = QLabel("😊")
        self.emotion_label.setFont(QFont("Segoe UI Emoji", 28))
        self.emotion_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.emotion_label)

        # 锁定标记
        self.locked_label = QLabel("")
        self.locked_label.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        self.locked_label.setAlignment(Qt.AlignCenter)
        self.locked_label.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(self.locked_label)

        layout.addStretch()

    def update_state(self, favor: int, stage: str, emotion: str, locked: bool = False, independence: float = 0.0) -> None:
        self.favor_label.setText(f"好感：{favor}/100")
        self.stage_label.setText(f"阶段：{stage}")
        self.emotion_label.setText(emotion)
        if locked:
            self.locked_label.setText("🔒 忠诚锁定")
        elif independence >= 0.6:
            self.locked_label.setText("✨ 独立人格")
        else:
            self.locked_label.setText("")


# ═══════════════════════════════════════════════
#  樱花飘落动画
# ═══════════════════════════════════════════════

class SakuraOverlay(QWidget):
    """透明樱花飘落粒子动画。绘制在聊天区域上层，不拦截鼠标事件。"""

    PETAL_COUNT = 35
    COLORS_PINK = [
        (255, 183, 197, 180),   # 淡粉
        (255, 154, 162, 160),   # 樱粉
        (255, 204, 188, 140),   # 浅桃
        (255, 175, 188, 170),   # 中粉
        (252, 157, 172, 150),   # 深粉
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._petals: list[dict] = []
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_petals)
        self._timer.start(33)  # ~30 fps

    def _init_petals(self) -> None:
        import random
        w = self.width() or 600
        h = self.height() or 400
        self._petals = []
        for _ in range(self.PETAL_COUNT):
            self._petals.append({
                "x": random.uniform(0, w),
                "y": random.uniform(-h, 0),
                "size": random.uniform(6, 14),
                "speed": random.uniform(0.4, 1.2),
                "drift": random.uniform(-0.3, 0.3),
                "rotation": random.uniform(0, 360),
                "rot_speed": random.uniform(-1.5, 1.5),
                "color_idx": random.randint(0, len(self.COLORS_PINK) - 1),
                "opacity": random.uniform(0.6, 1.0),
            })

    def _update_petals(self) -> None:
        if not self._petals:
            self._init_petals()
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return
        for p in self._petals:
            p["y"] += p["speed"]
            p["x"] += p["drift"]
            p["rotation"] += p["rot_speed"]
            # 漂出边界：循环回到顶部
            if p["y"] > h + 20:
                import random
                p["y"] = random.uniform(-40, -5)
                p["x"] = random.uniform(0, w)
        self.update()

    def paintEvent(self, event) -> None:
        from PySide6.QtGui import QPainter, QColor, QBrush, QPen
        from PySide6.QtCore import QPointF
        if not self._petals:
            self._init_petals()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        for p in self._petals:
            r, g, b, base_a = self.COLORS_PINK[p["color_idx"]]
            a = int(base_a * p["opacity"])
            color = QColor(r, g, b, a)
            painter.save()
            # 移动到花瓣位置并旋转
            cx, cy = p["x"], p["y"]
            painter.translate(QPointF(cx, cy))
            painter.rotate(p["rotation"])
            size = p["size"]
            # 画樱花花瓣（五瓣简化：椭圆 + 中心圆）
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            # 五个小椭圆组成花瓣
            for angle in range(0, 360, 72):
                painter.save()
                painter.rotate(angle)
                painter.drawEllipse(QPointF(size * 0.3, 0), size * 0.35, size * 0.15)
                painter.restore()
            # 中心
            center_color = QColor(255, 200, 180, a)
            painter.setBrush(QBrush(center_color))
            painter.drawEllipse(QPointF(0, 0), size * 0.18, size * 0.18)
            painter.restore()
        painter.end()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._init_petals()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._init_petals()


# ═══════════════════════════════════════════════
#  主窗口
# ═══════════════════════════════════════════════

class TwinChatApp(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        _log("TwinChatApp.__init__ 开始 (gui V10.0.1, lazy-import bridge)")
        self.setWindowTitle("❄ Re:Zero 双子系统 — Rem × Ram")
        self.setMinimumSize(1000, 650)
        self.resize(1100, 750)

        # 记忆存储（JSON — 硬状态）+ 对话流水（SQLite — 完整历史）
        self.store = MemoryStore(_PROJECT_ROOT)
        self.mem = self.store.load()
        self.conv_store = ConversationStore()
        _log(f"记忆加载: mode={self.mem.get('mode')} arc={self.mem.get('arc')}")

        # 迁移旧 JSON chat_history → SQLite（仅首次）
        old_history = self.mem.get("chat_history", [])
        if old_history:
            migrated = self.conv_store.migrate_from_json(old_history)
            if migrated:
                _log(f"SQLite 迁移: {migrated} 条旧消息")
                self.store.set("chat_history", [])  # 清空 JSON 中的旧历史

        self.mode = self.mem.get("mode", "llm")
        self._streaming_bubble: Optional[ChatMessageWidget] = None
        self._streaming_buffer: str = ""
        self._streaming_active: bool = False
        self._llm_thread: Optional[QThread] = None
        self._llm_worker: Optional[LLMWorker] = None

        # 世界状态（持久化）
        from shared.state import WorldState
        saved_world = self.mem.get("world_state")
        self.world = WorldState.load_or_create(saved_world)
        _log(f"世界加载: {self.world.period} {self.world.weather}")

        self._setup_ui()
        self._apply_theme()
        self._load_history()

        # 创建 bot
        self.bot = self._create_bot()
        # 注入持久化世界状态
        if hasattr(self.bot, 'world'):
            self.bot.world = self.world
        self._update_status_bar()
        self._update_panels()

        # 生成开场引言（LLM 模式且首次启动）
        if self.mode == "llm" and self.conv_store.count() == 0:
            QTimer.singleShot(300, self._generate_vignette)

        _log("TwinChatApp.__init__ 完成")

    # ── Bot 创建 ────────────────────────────

    def _create_bot(self):
        _log(f"_create_bot mode={self.mode}")
        if self.mode == "llm":
            try:
                from llm import ReZeroLLMBridge
                api_key = os.getenv("DEEPSEEK_API_KEY")
                bot = ReZeroLLMBridge(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    model_name="deepseek-chat",
                    arc=StoryArc(self.mem.get("arc", "mansion_era")),
                    max_history=8,
                )
                bot.engine.favor = self.mem.get("favor", 15)
                bot.engine.ram_favor = self.mem.get("ram_favor", 8)
                bot.engine.independence = self.mem.get("independence", 0.25)
                bot.engine.recovery = self.mem.get("recovery", 1.0)
                bot.engine.events = list(self.mem.get("events", []))
                bot.engine.user_name = self.mem.get("user_name")
                _log("LLM bot 创建成功")
                return bot
            except Exception as e:
                _log(f"LLM bot 创建失败: {e}")
                QMessageBox.warning(
                    self, "LLM 模式不可用",
                    f"{e}\n\n本次启动将使用本地模板模式。"
                )
                self.mode = "local"

        bot = ReZeroTwinSystem()
        bot.rem.engine.favor = self.mem.get("favor", 15)
        bot.rem.engine.ram_favor = self.mem.get("ram_favor", 8)
        bot.rem.engine.independence = self.mem.get("independence", 0.25)
        bot.rem.engine.recovery = self.mem.get("recovery", 1.0)
        bot.rem.engine.events = list(self.mem.get("events", []))
        bot.rem.engine.user_name = self.mem.get("user_name")
        try:
            bot.set_arc(StoryArc(self.mem.get("arc", "mansion_era")))
        except ValueError:
            bot.set_arc(StoryArc.MANSION_ERA)
        _log("本地 bot 创建成功")
        return bot

    @property
    def engine(self):
        return self.bot.engine if self.mode == "llm" else self.bot.rem.engine

    # ── UI 构建 ────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── 顶部标题栏 ──
        header = QFrame()
        header.setFixedHeight(54)
        header.setStyleSheet(f"background-color: {COLORS['bg_header']};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 18, 0)

        title = QLabel("❄  Re:Zero 双子系统  —  Rem × Ram")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_light']};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # 历史搜索
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索对话…")
        self.search_box.setFixedWidth(160)
        self.search_box.setFixedHeight(28)
        self.search_box.setFont(QFont("Microsoft YaHei", 10))
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba(255,255,255,0.15);
                color: {COLORS['text_light']};
                border: 1px solid rgba(255,255,255,0.25);
                border-radius: 6px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['accent']};
            }}
        """)
        self.search_box.returnPressed.connect(self._do_search)
        header_layout.addWidget(self.search_box)

        search_btn = QPushButton("🔍")
        search_btn.setFixedSize(28, 28)
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_light']};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {COLORS['accent']};
            }}
        """)
        search_btn.clicked.connect(self._do_search)
        header_layout.addWidget(search_btn)

        arc_label = QLabel("Arc I · 罗兹瓦尔宅邸")
        arc_label.setFont(QFont("Microsoft YaHei", 10))
        arc_label.setStyleSheet(f"color: {COLORS['accent']};")
        self._arc_label = arc_label
        header_layout.addWidget(arc_label)

        main_layout.addWidget(header)

        # ── 主体三栏布局 ──
        body = QHBoxLayout()
        body.setSpacing(0)

        # 左侧：蕾姆面板
        self.rem_panel = CharacterPanel("蕾 姆", "🩵", COLORS["rem_primary"], sprite_path=_asset_path("rem_sprite.jpg"))
        body.addWidget(self.rem_panel)

        # 中间：聊天区域
        chat_section = QVBoxLayout()
        chat_section.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignTop)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_container)
        chat_section.addWidget(self.scroll, 1)

        # 樱花飘落叠加层（覆盖聊天区域，不拦截鼠标）
        self.sakura = SakuraOverlay(self.scroll.viewport())
        self.sakura.setGeometry(self.scroll.viewport().rect())
        self.scroll.viewport().installEventFilter(self)

        # 输入区域
        input_frame = QFrame()
        input_frame.setFixedHeight(130)
        input_frame.setStyleSheet(f"background-color: {COLORS['bg_secondary']}; border-top: 1px solid {COLORS['border']};")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(6)

        # 快捷选项按钮行
        quick_row = QHBoxLayout()
        quick_row.setSpacing(6)
        for i, (label, cmd) in enumerate([
            ("📊 状态", "/status"),
            ("🏠 宅邸篇", "/mansion"),
            ("🗡️ 帝国篇", "/empire"),
            ("⏳ 后期", "/late"),
            ("🔄 切换模式", "/toggle"),
        ]):
            btn = QPushButton(label)
            btn.setFixedHeight(26)
            btn.setFont(QFont("Microsoft YaHei", 9))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_sidebar']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 6px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['rem_bubble']};
                    color: {COLORS['text_primary']};
                }}
            """)
            btn.clicked.connect(lambda checked, c=cmd: self._handle_command(c))
            quick_row.addWidget(btn)
        quick_row.addStretch()
        input_layout.addLayout(quick_row)

        # 输入行
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_box = QTextEdit()
        self.input_box.setPlaceholderText("和蕾姆、拉姆说点什么吧… (Enter 发送)")
        self.input_box.setFont(QFont("Microsoft YaHei", 11))
        self.input_box.setFixedHeight(55)
        self.input_box.installEventFilter(self)
        input_row.addWidget(self.input_box, 1)

        self.send_btn = QPushButton("发 送")
        self.send_btn.setFixedSize(72, 55)
        self.send_btn.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        input_layout.addLayout(input_row)
        chat_section.addWidget(input_frame)

        body.addLayout(chat_section, 1)

        # 右侧：拉姆面板
        self.ram_panel = CharacterPanel("拉 姆", "💗", COLORS["ram_primary"], sprite_path=_asset_path("ram_sprite.jpg"))
        body.addWidget(self.ram_panel)

        main_layout.addLayout(body, 1)

        # ── 底部状态栏 ──
        footer = QFrame()
        footer.setFixedHeight(28)
        footer.setStyleSheet(f"background-color: {COLORS['bg_header']};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 0, 14, 0)

        self.footer_label = QLabel("就绪")
        self.footer_label.setFont(QFont("Microsoft YaHei", 9))
        self.footer_label.setStyleSheet(f"color: {COLORS['text_light']};")
        footer_layout.addWidget(self.footer_label)
        footer_layout.addStretch()

        mode_label = QLabel("LLM 桥接")
        mode_label.setFont(QFont("Microsoft YaHei", 9))
        mode_label.setStyleSheet(f"color: {COLORS['accent']};")
        self._mode_label = mode_label
        footer_layout.addWidget(mode_label)

        main_layout.addWidget(footer)

    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg_primary']};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QTextEdit {{
                border: 1px solid {COLORS['border']};
                border-radius: 10px;
                padding: 8px 10px;
                background-color: {COLORS['bg_secondary']};
                color: {COLORS['text_primary']};
            }}
            QTextEdit:focus {{
                border-color: {COLORS['accent']};
            }}
            QPushButton {{
                background-color: {COLORS['accent']};
                color: white;
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: #b8944f;
            }}
            QPushButton:pressed {{
                background-color: #a07d3a;
            }}
            QPushButton:disabled {{
                background-color: #c0b8a8;
            }}
        """)

    # ── 命令处理 ────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        if cmd == "/status":
            if self.mode == "llm":
                status_text = self.bot.status()
            else:
                status_text = self.bot.status()
            self._append_parsed_message("系统", status_text, "system")
            self._update_panels()
        elif cmd == "/mansion":
            self.bot.set_arc(StoryArc.MANSION_ERA)
            self.store.set("arc", StoryArc.MANSION_ERA.value)
            self._append_parsed_message("系统", "→ 已切换至宅邸篇", "system")
            self._arc_label.setText("Arc I · 罗兹瓦尔宅邸")
            self._update_status_bar()
        elif cmd == "/empire":
            self.bot.set_arc(StoryArc.EMPIRE_ERA)
            self.store.set("arc", StoryArc.EMPIRE_ERA.value)
            self._append_parsed_message("系统", "→ 已切换至帝国篇（失忆）", "system")
            self._arc_label.setText("Arc II · 帝国篇")
            self._update_status_bar()
        elif cmd == "/late":
            self.bot.set_arc(StoryArc.LATE_ARC)
            self.store.set("arc", StoryArc.LATE_ARC.value)
            self._append_parsed_message("系统", "→ 已切换至后期篇章", "system")
            self._arc_label.setText("Arc III · 后期篇章")
            self._update_status_bar()
        elif cmd == "/toggle":
            self._switch_mode()
        self._update_panels()

    def _switch_mode(self) -> None:
        old = self.engine
        target = "local" if self.mode == "llm" else "llm"
        _log(f"_switch_mode: {self.mode} → {target}")
        try:
            if target == "llm":
                _log("_switch_mode: importing llm...")
                from llm import ReZeroLLMBridge
                _log("_switch_mode: llm imported OK")
                api_key = os.getenv("DEEPSEEK_API_KEY")
                if not api_key:
                    raise ValueError("未找到 DEEPSEEK_API_KEY，请确保 .env 文件在同目录下。")
                _log("_switch_mode: creating bridge...")
                new_bot = ReZeroLLMBridge(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    model_name="deepseek-chat",
                    arc=old.arc,
                    max_history=8,
                )
                new_engine = new_bot.engine
                _log("_switch_mode: bridge created OK")
            else:
                new_bot = ReZeroTwinSystem()
                new_bot.set_arc(old.arc)
                new_engine = new_bot.rem.engine

            new_engine.favor = old.favor
            new_engine.ram_favor = old.ram_favor
            new_engine.independence = old.independence
            new_engine.recovery = old.recovery
            new_engine.locked = old.locked
            new_engine.user_name = old.user_name
            new_engine.events = list(getattr(old, 'events', []))
            self.bot = new_bot
            self.mode = target
            self.store.set("mode", target)
            self._append_parsed_message(
                "系统",
                f"→ 已切换至{'LLM 桥接' if target == 'llm' else '本地模板'}模式（状态已迁移）",
                "system",
            )
            self._mode_label.setText("LLM 桥接" if target == "llm" else "本地模板")
            self._update_panels()
        except Exception as e:
            _log(f"_switch_mode 失败: {e}\n{traceback.format_exc()}")
            self._append_parsed_message("系统", f"切换失败：{e}", "system")

    # ── 开场引言 ────────────────────────────

    def _generate_vignette(self) -> None:
        """生成开场氛围段（异步，不阻塞 UI）。

        v10.4 起走 shared.vignette 的 L0-L3 多级生成：
        L0 缓存 → L1 LLM(重试+校验) → L2 动态模板 → L3 静态兜底。
        引言为 View-Only 数据，绝不写入对话历史（save=False + 不进 messages）。
        """
        if self.mode != "llm" or not hasattr(self.bot, 'world'):
            self._append_parsed_message(
                "系统", "欢迎回到罗兹瓦尔宅邸。输入消息开始对话。", "system", save=False
            )
            return

        self._append_parsed_message("系统", "✨ 正在感知宅邸的氛围…", "system", save=False)

        def _on_done(clean: str):
            # 移除旧的"正在感知"消息
            count = self.chat_layout.count()
            if count >= 2:
                item = self.chat_layout.itemAt(count - 2)
                if item and item.widget():
                    w = item.widget()
                    w.setParent(None)
                    w.deleteLater()
            self._append_parsed_message("系统", f"━━  ✦  ━━\n{clean}\n━━  ✦  ━━", "system", save=False)

        # 用 raw_completion 绕过角色 system prompt
        class VignetteWorker(QObject):
            finished = Signal(str)
            error = Signal(str)
            def __init__(self, bot, world):
                super().__init__()
                self.bot = bot; self.world = world
            def run(self):
                try:
                    from shared.vignette import VignetteGenerator
                    engine = self.bot.engine
                    gen = VignetteGenerator(llm_callable=self.bot.raw_completion)
                    text = gen.generate(
                        self.world,
                        rem_favor_level=engine._get_favor_level().name,
                        independence=engine.independence,
                        ram_stage=engine._get_ram_stage().value,
                    )
                    self.finished.emit(text)
                except Exception as e:
                    self.error.emit(str(e))

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

    # ── 历史搜索 ────────────────────────────

    def _do_search(self) -> None:
        query = self.search_box.text().strip()
        if not query:
            return
        results = self.conv_store.search(query, limit=10)
        if not results:
            self._append_parsed_message("系统", f"未找到包含「{query}」的对话。", "system")
            return
        self._append_parsed_message("系统", f"━━ 搜索「{query}」找到 {len(results)} 条 ━━", "system")
        for r in results:
            role = r["role"]
            sender = r["sender"]
            text = r["content"]
            # 截断过长内容
            preview = text[:80] + ("…" if len(text) > 80 else "")
            self._append_parsed_message(sender, preview, role)
        self._append_parsed_message("系统", "━━ 搜索结束 ━━", "system")

    # ── 消息处理 ────────────────────────────

    MAX_VISIBLE_WIDGETS = 80  # 最多保留 80 条消息 widget

    def _append_parsed_message(self, sender: str, text: str, role: str, save: bool = True) -> None:
        """添加消息 widget。超出上限时移除最早的。"""
        msg = ChatMessageWidget(sender, text, role=role)
        insert_index = self.chat_layout.count() - 1  # 在 stretch 之前插入
        self.chat_layout.insertWidget(insert_index, msg)

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
            self.conv_store.append(role, sender, text)
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _insert_streaming_bubble(self, role: str) -> ChatMessageWidget:
        """插入一个空流式气泡，后续逐 token 填充。"""
        sender = "蕾 姆" if role == "rem" else ("拉 姆" if role == "ram" else role)
        msg = ChatMessageWidget(sender, "", role=role)
        insert_index = self.chat_layout.count() - 1
        self.chat_layout.insertWidget(insert_index, msg)
        QTimer.singleShot(30, self._scroll_to_bottom)
        return msg

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    # ── 发送消息 ────────────────────────────

    def _send_message(self) -> None:
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        # 防止并发发送
        if self._streaming_active:
            self._append_parsed_message("系统", "双子正在回复中，请稍候…", "system")
            return
        _log(f"发送: {text[:40]}")

        self.input_box.clear()
        self._append_parsed_message("你", text, "user")

        # 命令检测
        lowered = text.lower()
        if lowered == "/status":
            self._handle_command("/status")
            return
        if lowered in ("/mansion", "/empire", "/late"):
            self._handle_command(lowered)
            return
        if lowered.startswith("/recover"):
            parts = text.split()
            try:
                p = float(parts[1])
            except (IndexError, ValueError):
                p = 1.0
            self.bot.recover(p)
            self.store.set("recovery", p)
            self._append_parsed_message("系统", f"→ 记忆恢复进度设为 {p}", "system")
            self._update_panels()
            return
        if lowered in ("/llm", "/local", "/toggle"):
            self._switch_mode()
            return

        # 有效对话：刷新世界状态的最后互动时间戳（v10.4）
        if hasattr(self, 'world'):
            self.world.mark_interaction()

        self.footer_label.setText("双子思考中…")
        self.send_btn.setEnabled(False)
        self._streaming_active = True

        if self.mode == "llm" and hasattr(self.bot, 'chat_stream'):
            self._send_llm_stream(text)
        else:
            QTimer.singleShot(50, lambda: self._send_sync(text))

    def _send_sync(self, text: str) -> None:
        """同步发送（本地模式 或 旧的 LLM 同步模式）。"""
        try:
            if self.mode == "llm":
                reply = self.bot.chat(text)
            else:
                reply = self.bot.interact(text)
            _log(f"回复: {reply[:60]}")
        except Exception as e:
            reply = f"【系统】出错了：{e}"
            _log(f"异常: {e}")

        self._parse_twin_reply(reply)
        self._finish_reply()

    def _send_llm_stream(self, text: str) -> None:
        """LLM 流式发送（异步线程，安全的线程管理）。"""
        # 清理旧线程
        if self._llm_thread and self._llm_thread.isRunning():
            _log("_send_llm_stream: 等待旧线程结束...")
            self._llm_thread.quit()
            if not self._llm_thread.wait(2000):
                _log("_send_llm_stream: 强制终止旧线程")
                self._llm_thread.terminate()
                self._llm_thread.wait(1000)
        # 断开旧信号
        if self._llm_worker:
            try:
                self._llm_worker.stream_token.disconnect()
                self._llm_worker.finished.disconnect()
                self._llm_worker.error.disconnect()
            except Exception:
                pass

        self._streaming_buffer = ""
        self._streaming_bubble = None

        self._llm_thread = QThread()
        self._llm_worker = LLMWorker(self.bot, text, stream=True)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.stream_token.connect(self._on_stream_token, Qt.QueuedConnection)
        self._llm_worker.finished.connect(self._on_stream_finished, Qt.QueuedConnection)
        self._llm_worker.error.connect(self._on_stream_error, Qt.QueuedConnection)
        self._llm_thread.finished.connect(self._llm_thread.deleteLater)
        self._llm_thread.start()

    def _on_stream_token(self, token: str) -> None:
        self._streaming_buffer += token
        if self._streaming_bubble is None and self._streaming_buffer.strip():
            # 流式进行中：建一个临时预览气泡
            self._streaming_bubble = self._insert_streaming_bubble("system")
            self._streaming_bubble.setObjectName("__streaming_temp__")
        if self._streaming_bubble:
            self._streaming_bubble.update_text(self._streaming_buffer)
            QTimer.singleShot(10, self._scroll_to_bottom)

    def _on_stream_finished(self, _final: str = "") -> None:
        buffered = self._streaming_buffer or _final
        # 移除临时预览气泡
        if self._streaming_bubble:
            try:
                self._streaming_bubble.setParent(None)
                self._streaming_bubble.deleteLater()
            except Exception:
                pass
        self._streaming_bubble = None
        self._streaming_buffer = ""
        # 解析完整回复，拆分成独立的蕾姆/拉姆气泡
        if buffered.strip():
            self._parse_twin_reply(buffered)
        self._finish_reply()
        _log("流式完成")

    def _on_stream_error(self, err: str) -> None:
        self._streaming_active = False
        self._append_parsed_message("系统", f"出错了：{err}", "system")
        self._streaming_buffer = ""
        self._streaming_bubble = None
        self._finish_reply()
        _log(f"流式错误: {err}")

    def _parse_twin_reply(self, reply: str) -> None:
        """解析双子回复，按【蕾姆】/【拉姆】分行，分色显示。"""
        lines = reply.strip().split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("【蕾姆】") or line.startswith("【蕾姆】:"):
                content = line.split(":", 1)[1].strip().strip('"') if ":" in line else line[4:].strip()
                self._append_parsed_message("蕾 姆", content, "rem")
            elif line.startswith("【拉姆】") or line.startswith("【拉姆】:"):
                content = line.split(":", 1)[1].strip().strip('"') if ":" in line else line[4:].strip()
                self._append_parsed_message("拉 姆", content, "ram")
            elif line.startswith("【系统】") or line.startswith("【系统】:"):
                content = line.split(":", 1)[1].strip() if ":" in line else line[4:].strip()
                self._append_parsed_message("系统", content, "system")
            else:
                if line and not line.startswith("【"):
                    self._append_parsed_message("系统", line, "system")

    def _finish_reply(self) -> None:
        self._streaming_active = False
        self._save_state()
        self._update_panels()
        self._update_status_bar()
        self.footer_label.setText("就绪")
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
            if not text:
                continue
            self._append_parsed_message(sender, text, role, save=False)
            shown += 1
        _log(f"历史显示: {shown} 条")
        if shown == 0:
            self._append_parsed_message(
                "系统",
                "❄ 欢迎来到 Re:Zero 双子系统。\n"
                "左侧是蕾姆面板，右侧是拉姆面板。\n"
                "输入消息开始对话，或使用底部快捷按钮。",
                "system", save=False,
            )

    # ── 状态同步 ────────────────────────────

    def _update_panels(self) -> None:
        """更新左右角色面板。"""
        try:
            state = self.engine.snapshot()
        except Exception:
            return

        # 蕾姆面板
        rem_emotion = "😊"
        if state.witch_scent >= 3:
            rem_emotion = "😰"
        elif state.oni_stage.value > 0:
            rem_emotion = "😠"
        elif state.consecutive_negative >= 2:
            rem_emotion = "😟"
        elif state.locked:
            rem_emotion = "🥰"
        elif state.independence >= 0.6:
            rem_emotion = "😌"

        self.rem_panel.update_state(
            favor=state.favor,
            stage=state.favor_level.name,
            emotion=rem_emotion,
            locked=state.locked,
            independence=state.independence,
        )

        # 拉姆面板
        ram_emotion_map = {
            "可疑": "😒",
            "观察中": "🤔",
            "还算守规矩": "😐",
            "勉强认可": "😏",
            "真正承认": "😌",
        }
        ram_emotion = ram_emotion_map.get(state.ram_stage.value, "😐")
        self.ram_panel.update_state(
            favor=state.ram_favor,
            stage=state.ram_stage.value,
            emotion=ram_emotion,
        )

    def _update_status_bar(self) -> None:
        try:
            state = self.engine.snapshot()
            w = self.world if hasattr(self, 'world') else WorldState.now()
            self._mode_label.setText(
                f"{'LLM' if self.mode == 'llm' else '本地'} | "
                f"{w.period} · {w.weather} | "
                f"好感 {state.favor}/100 | "
                f"{state.ram_stage.value}"
            )
        except Exception:
            pass

    def _save_state(self) -> None:
        try:
            engine = self.engine
            data = self.store.load()
            data.update({
                "mode": self.mode,
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
            _log("状态保存成功")
        except Exception as e:
            _log(f"保存状态失败: {e}")

    # ── 事件过滤 ────────────────────────────

    def eventFilter(self, source, event) -> bool:
        from PySide6.QtCore import QEvent
        # 输入框回车发送
        if source is self.input_box and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Return and not event.modifiers() & Qt.ShiftModifier:
                self._send_message()
                return True
        # 樱花层跟随 viewport 大小变化
        if source is self.scroll.viewport() and event.type() == QEvent.Resize:
            self.sakura.setGeometry(self.scroll.viewport().rect())
        return super().eventFilter(source, event)

    def closeEvent(self, event) -> None:
        self._save_state()
        event.accept()


def main() -> None:
    try:
        app = QApplication(sys.argv)
        app.setFont(QFont("Microsoft YaHei", 10))
        window = TwinChatApp()
        window.show()
        _log("窗口 show 完成")
        sys.exit(app.exec())
    except Exception as e:
        _log(f"main 异常: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
