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

# V14.11 Step5：偶发一句注册表（懒加载单例）——SPEC-28：**定义已归位 ui/flags.py**（re-export 见下方归位块）

# SPEC-20260922-22 S1a：路径引导不能再借 `_PROJECT_ROOT`（已归位 ui/assets.py，
# 而 import ui.* 又需要 sys.path 就绪——先有鸡还是先有蛋）⇒ 引导就地自算（与 ui/assets 同式，值恒等）。
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env, get_data_dir
load_env()


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

from shared.state import StoryArc, OniStage, FAVOR_LEVEL_CN, is_valid_user_name
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
from ui.flags import _VIGNETTE_DISABLED, _HISTORY_DISABLED, _ui_motion_enabled, _side_panels_enabled, _get_ambient_registry, name_hint_once, _AMBIENT_REGISTRY  # noqa: F401
from ui.app_data import ARC_CN, GREETING_TEMPLATES, NAV_ENTRIES, ONI_STAGE_CN, WEATHER_CLAUSES, WORLD_FEEDBACK  # noqa: F401
from ui.widgets_message import AvatarLabel, BubbleWidget, SystemLabelWidget, ChatMessageWidget  # noqa: F401
from ui.history import HistoryItemWidget, HistoryOverlay, LOCATE_FLASH_MS  # noqa: F401
from ui.panels import CharacterPanel  # noqa: F401
from ui.overlays import SakuraOverlay  # noqa: F401
from ui.worker import LLMWorker  # noqa: F401
from ui.mixins.search import SearchMixin
from ui.mixins.message_ops import MessageOpsMixin
from ui.mixins.history import HistoryMixin
from ui.mixins.chat import ChatMixin
from ui.mixins.panels import PanelsMixin
from ui.mixins.daily import DailyMixin
from ui.mixins.commands import CommandsMixin
from ui.mixins.shell_setup import ShellSetupMixin

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

class TwinChatApp(SearchMixin, MessageOpsMixin, HistoryMixin, ChatMixin, PanelsMixin, DailyMixin, CommandsMixin, ShellSetupMixin, QMainWindow):

    # ── 消息处理 ────────────────────────────

    MAX_VISIBLE_WIDGETS = 80  # 最多保留 80 条消息 widget


    def _ambient_fits(self, text: str) -> bool:
        """顶栏氛围行宽度判定（SPEC-20260922-24 真机反馈修订）。

        标签尚未布局（宽度 ≤ 24px，启动首帧）时按「放得下」处理，避免误降级。
        """
        try:
            w = self._ambient_label.width()
            if w <= 24:
                return True
            return QFontMetrics(self._ambient_label.font()).horizontalAdvance(text) <= max(0, w - 8)
        except Exception:
            return True


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
