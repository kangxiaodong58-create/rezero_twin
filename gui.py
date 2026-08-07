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

import ctypes
import html
import os
import sys

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
from datetime import datetime
from typing import Optional

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env, get_data_dir
load_env()

# 历史浮层开关（V10.10.2）：环境变量 REZERO_DISABLE_HISTORY=1 可禁用浮层做二分排查
_HISTORY_DISABLED = os.environ.get("REZERO_DISABLE_HISTORY", "") == "1"

# 开场引言开关（V10.10.3）：环境变量 REZERO_DISABLE_VIGNETTE=1 可禁用引言做二分排查
_VIGNETTE_DISABLED = os.environ.get("REZERO_DISABLE_VIGNETTE", "") == "1"

# UI 动效开关（V12.0）：环境变量 REZERO_DISABLE_UI_MOTION=1 可整体关闭动效（验收对比/回滚）
ENABLE_UI_MOTION = os.environ.get("REZERO_DISABLE_UI_MOTION", "") != "1"

from PySide6.QtCore import (
    Qt, QTimer, Signal, QObject, QThread, QSize,
    QPropertyAnimation, QSequentialAnimationGroup, QAbstractAnimation, QEasingCurve,
)
from PySide6.QtGui import QFont, QFontMetrics, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QLabel, QFrame, QScrollArea,
    QMessageBox, QSizePolicy, QSplitter, QProgressBar, QGraphicsOpacityEffect,
    QMenu,
)

from local import ReZeroTwinSystem
from shared.state import StoryArc, OniStage, FAVOR_LEVEL_CN
from shared.memory_store import MemoryStore
from shared.conversation_store import ConversationStore

# 日志与持久化统一走 get_data_dir()：
# frozen 时指向 EXE 同级 data/，源码时指向项目根 data/。
# 切勿用 _PROJECT_ROOT（frozen 下是 _MEIPASS 临时目录，退出即丢）。
_LOG_PATH = os.path.join(get_data_dir(), "gui.log")


def _log(msg: str) -> None:
    try:
        os.makedirs(os.path.dirname(_LOG_PATH), exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        pass


_log(f"=== PySide6 GUI 启动 (python={sys.executable}) ===")


# ═══════════════════════════════════════════════
#  Design Tokens（V10.9.0 暗色视觉基线）
# ═══════════════════════════════════════════════
COLORS = {
    # ── 背景层级 ──
    "bg_base":       "#121319",   # 全局底色
    "bg_surface":    "#1a1b23",   # 面板/输入区表面
    "bg_surface_2":  "#1e1f29",   # 气泡/卡片表面（略亮，区分层级）
    "bg_header":     "#0f1015",   # 顶栏/底栏（更深，收束视觉）

    # ── 边框（低对比细边） ──
    "border_subtle": "rgba(255,255,255,0.08)",
    "border_focus":  "rgba(255,255,255,0.15)",

    # ── 文本层级 ──
    "text_primary":   "#E2E8F0",  # 主文本（对话内容、角色名）
    "text_secondary": "#94A3B8",  # 次要文本（状态、好感数值、提示语）
    "text_muted":     "#64748B",  # 系统标签、占位符

    # ── 角色主题色 ──
    "rem_accent":    "#56CCF2",   # 蕾姆冰蓝
    "rem_bubble":    "rgba(86,204,242,0.10)",
    "rem_left":      "rgba(86,204,242,0.45)",
    "ram_accent":    "#FF7EB3",   # 拉姆蔷薇粉
    "ram_bubble":    "rgba(255,126,179,0.10)",
    "ram_left":      "rgba(255,126,179,0.45)",

    # ── 用户 ──
    "user_bubble":   "rgba(99,102,241,0.16)",
    "user_border":   "rgba(99,102,241,0.30)",

    # ── 功能色 ──
    "accent":        "#c9a96e",   # 金色点缀（发送按钮、章节标签）
    "accent_hover":  "#d4b87a",
    "accent_press":  "#b8964f",

    # ── 系统标签 ──
    "system_label_bg":  "rgba(255,255,255,0.04)",
    "system_label_fg":  "#64748B",

    # ── STATE（V10.15b：状态色，消除 disabled/高亮/遮罩硬编码）──
    "btn_disabled_bg":  "#4a4a4a",               # 按钮 disabled 背景
    "btn_disabled_fg":  "#888",                  # 按钮 disabled 文字
    "locate_highlight": "rgba(255,215,0,0.15)",   # 定位高亮金色半透明
    "search_hit":       "#FFEB3B",                # V14.1：搜索命中词黄底
    "overlay_mask":     "rgba(0,0,0,0.65)",       # 历史浮层遮罩
}

RADIUS = {
    "xs":     4,    # 历史详情区（V10.15b 新增）
    "sm2":    6,    # 历史项外框（V10.15b 新增，介于 xs 与 small 之间）
    "large":  16,   # 气泡、立绘框
    "medium": 12,   # 面板、输入框
    "small":   8,   # 按钮
    "pill":   20,   # 头像、标签
}

SPACING = {
    "xs":  4,
    "sm":  8,
    "md":  12,
    "lg":  16,
    "xl":  24,
}

# ═══════════════════════════════════════════════
#  Font Tokens（V10.15a：字体族 + 语义刻度，消除 30+ 处字面量）
# ═══════════════════════════════════════════════
FONT_FAMILY = {
    "ui":    "Microsoft YaHei",   # 正文/UI
    "emoji": "Segoe UI Emoji",    # 表情/立绘占位
}

FONT_SIZE = {
    "caption":   8,   # 时间戳、最弱辅助
    "small":     9,   # 角色名、按钮文字、状态栏
    "body":     10,   # 历史正文、面板数值、搜索框、系统标签(长)
    "body_lg":  11,   # 气泡正文、输入框、发送按钮
    "title":    12,   # 浮层标题
    "title_lg": 14,   # 顶栏标题、面板角色名
    "emoji_sm": 20,   # 头像 emoji（AvatarLabel）
    "emoji_md": 28,   # 情绪 emoji（历史面板）
    "emoji_lg": 36,   # 情绪 emoji（CharacterPanel 主焦点）
    "display":  48,   # 立绘占位 emoji
}

# ═══════════════════════════════════════════════
#  角色色统一映射（V10.15a：消除三处分散定义）
# ═══════════════════════════════════════════════
ROLE_COLORS = {
    "rem":    COLORS['rem_accent'],   # 蕾姆冰蓝
    "ram":    COLORS['ram_accent'],   # 拉姆蔷薇粉
    "user":   COLORS['text_primary'], # 用户（统一为 primary）
    "system": COLORS['text_muted'],   # 系统弱化
}

# BubbleWidget 专用：角色 → 气泡底色/前景/边框 CSS
ROLE_BUBBLE_STYLES = {
    "rem": {
        "bg": COLORS['rem_bubble'],
        "fg": COLORS['text_primary'],
        "border": f"border-left: 3px solid {COLORS['rem_left']};",
        "hl_border": "border-left: 5px solid rgba(86,204,242,0.70);",
        "hl_bg": "rgba(86,204,242,0.15)",
        # V11.10.1：streaming 弱变体 — 底色降至 0.04，边线细 2px+弱 0.15，文字暗一档
        "stream_bg": "rgba(86,204,242,0.04)",
        "stream_border": "border-left: 2px solid rgba(86,204,242,0.15);",
        "stream_fg": COLORS['text_secondary'],
    },
    "ram": {
        "bg": COLORS['ram_bubble'],
        "fg": COLORS['text_primary'],
        "border": f"border-left: 3px solid {COLORS['ram_left']};",
        "hl_border": "border-left: 5px solid rgba(255,126,179,0.70);",
        "hl_bg": "rgba(255,126,179,0.15)",
        "stream_bg": "rgba(255,126,179,0.04)",
        "stream_border": "border-left: 2px solid rgba(255,126,179,0.15);",
        "stream_fg": COLORS['text_secondary'],
    },
    "user": {
        "bg": COLORS['user_bubble'],
        "fg": COLORS['text_primary'],
        "border": f"border: 1px solid {COLORS['user_border']};",
    },
}
# system 兜底（实际不走 BubbleWidget，仅防御）
ROLE_BUBBLE_FALLBACK = {
    "bg": COLORS['bg_surface_2'],
    "fg": COLORS['text_secondary'],
    "border": f"border: 1px solid {COLORS['border_subtle']};",
}

# ═══════════════════════════════════════════════
#  Surface Tint（V10.15b：表面叠加色，消除散落 rgba(255,255,255,0.0x)）
# ═══════════════════════════════════════════════
SURFACE_TINT = {
    "detail": "rgba(255,255,255,0.03)",  # 历史详情区底色（弱叠加）
    "hover":  "rgba(255,255,255,0.03)",  # 折叠态 hover 底色（弱叠加）
    "active": "rgba(255,255,255,0.04)",  # 展开态外框底色（中叠加）
    "input":  "rgba(255,255,255,0.06)",  # 搜索框底色 / 按钮强 hover
}


def _rgba_to_qcolor(rgba_str: str):
    """解析 'rgba(r,g,b,a)' 字符串为 QColor（供 QPainter 使用）。"""
    s = rgba_str.strip()[5:-1]  # 去掉 "rgba(" 和 ")"
    r, g, b, a = s.split(",")
    from PySide6.QtGui import QColor
    return QColor(int(r), int(g), int(b), int(float(a) * 255))


def highlight_plain_text(text: str, keyword: str) -> str:
    """V14.1：HTML escape 后把命中词包装为黄底 span（多命中全部标黄）。

    防注入：先 html.escape 全文，再在转义后的文本上精确匹配转义后的关键词
    （命中词的转义形态与原文一致，直接切片包裹）。空 keyword 或未命中时
    返回 escape 后的文本（QLabel PlainText 渲染与原文一致）。
    """
    escaped = html.escape(text)
    if not keyword:
        return escaped
    kw = html.escape(keyword)
    if kw not in escaped:
        return escaped
    hit_style = f"background-color: {COLORS['search_hit']}; color: #1a1a1a;"
    parts: list = []
    pos = 0
    while True:
        idx = escaped.find(kw, pos)
        if idx < 0:
            parts.append(escaped[pos:])
            break
        parts.append(escaped[pos:idx])
        parts.append(f'<span style="{hit_style}">{escaped[idx:idx + len(kw)]}</span>')
        pos = idx + len(kw)
    return "".join(parts)

# ═══════════════════════════════════════════════
#  DIM 尺寸 token（V10.15c：布局尺寸唯一真源，消除魔法数）
# ═══════════════════════════════════════════════
DIM = {
    # ── 结构高度 ──
    "header_h":         54,   # 顶栏高度
    "footer_h":         28,   # 底部状态栏高度
    "input_frame_h":   130,   # 输入区域总高度
    "input_box_h":      55,   # 输入框高度
    "avatar_frame_h":  240,   # 角色面板立绘区域高度

    # ── 结构宽度 ──
    "panel_w":          180,  # 角色面板宽度
    "history_card_w":   720,  # 历史浮层卡片宽度
    "search_box_w":     160,  # 顶栏搜索框宽度

    # ── 元素尺寸 ──
    "avatar_size":       42,  # 头像直径
    "bubble_max_w":     600,  # 气泡/系统标签最大宽度
    "send_btn_w":        72,  # 发送按钮宽度
    "send_btn_h":        55,  # 发送按钮高度（与 input_box_h 同值，语义独立）

    # ── 方形图标按钮（28×28）──
    "icon_btn":          28,  # 关闭/搜索按钮等方形图标按钮

    # ── 顶栏控件高度（与 icon_btn 同值，语义独立）──
    "search_box_h":      28,  # 顶栏搜索框高度
    "history_btn_h":     28,  # 顶栏历史按钮高度

    # ── 次级按钮 ──
    "quick_btn_h":       26,  # 快捷按钮高度
    "locate_btn":        22,  # 历史条目定位按钮直径

    # ── 历史浮层子区域 ──
    "history_header_h":  48,  # 历史浮层标题栏/搜索区高度
}

# ═══════════════════════════════════════════════
#  显示层中文映射（V10.9.1）
#  V11.7：FAVOR_LEVEL_CN 已迁移至 shared.state（唯一真源）
#  ONI_STAGE_CN / ARC_CN 仅 GUI 使用，保留本地
# ═══════════════════════════════════════════════
ONI_STAGE_CN = {
    "NONE": "无",
    "EMERGING": "显现",
    "FULL": "完全解放",
    "BRINK": "失控边缘",
}

ARC_CN = {
    "mansion_era": "宅邸篇",
    "empire_era": "帝国篇（失忆）",
    "late_arc": "后期篇",
}

# ── V11.9.1：日更问候模板表驱动 ──────────────────────
# 骨架不含天气/其它时段词，天气由 WEATHER_CLAUSES 白名单注入。
GREETING_TEMPLATES = {
    "清晨": "早安。蕾姆已经备好了早餐。{weather_clause}{event_clause}",
    "上午": "上午好。宅邸的走廊已经亮起来了。{weather_clause}{event_clause}",
    "午后": "午安。刚泡好的红茶还冒着热气。{weather_clause}{event_clause}",
    "下午": "下午好。宅邸很安静。{weather_clause}{event_clause}",
    "傍晚": "傍晚了。天色渐暗，蕾姆点了灯。{weather_clause}{event_clause}",
    "夜晚": "晚上好。夜风有些凉。{weather_clause}{event_clause}",
    "深夜": "这么晚了还没休息吗。{weather_clause}{event_clause}",
}

# 天气从句白名单：覆盖 WorldState.WEATHERS 全部 5 种，未知天气中性兜底。
WEATHER_CLAUSES = {
    "晴朗": "窗外天气晴朗。",
    "多云": "云层遮住了部分天空。",
    "小雨": "窗外飘着小雨。",
    "大雨": "雨下得很大，宅邸的屋檐传来急促的滴水声。",
    "阴沉": "天空阴沉沉的。",
}

# 天气 ↔ active_event 语义冲突关键词：命中则跳过 event 拼接并打日志。
WEATHER_EVENT_CONFLICT = {
    "大雨": ["花园", "盛开", "晒", "阳光", "晾晒", "白布", "温暖"],
    "阴沉": ["阳光", "晒", "晴朗", "盛开", "晾晒", "白布", "温暖"],
    "小雨": ["晒", "阳光", "晾晒"],
}

# 时段关键词：event 含这些词且与当前 period 不一致 → 语义冲突。
# "入夜" 视为 "夜晚"/"深夜" 的别名，不与这两个时段冲突。
PERIOD_KEYWORDS = ["清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜", "入夜"]


def event_compatible(period: str, weather: str, event: str) -> bool:
    """V11.9.2：检查 active_event 是否与当前 period/weather 语义相容。

    统一冲突检测，供 _show_daily_greeting / _show_ambient_line / _update_status_bar 共用。
    返回 True 表示可拼接；False 表示应跳过 event 段。
    """
    if not event:
        return False

    # 天气冲突：event 含当前天气的冲突关键词
    conflict_kws = WEATHER_EVENT_CONFLICT.get(weather, [])
    if any(kw in event for kw in conflict_kws):
        return False

    # 时段冲突：event 含其它时段词
    for kw in PERIOD_KEYWORDS:
        if kw in event:
            # "入夜" 是 "夜晚"/"深夜" 的别名
            if kw == "入夜" and period in ("夜晚", "深夜"):
                continue
            # 时段词与当前 period 一致则不冲突
            if kw == period:
                continue
            return False

    return True


def match_speaker_tag(line: str) -> tuple:
    """V11.11：行首说话人标签匹配（parse_twin_segments 与 _streaming_segments 共用）。

    Returns: (tag_type, content)
    - tag_type: "rem" | "ram" | "system" | "unknown" | None
    - content: 标签后提取的文本（strip 引号）；无标签时返回原 line
    """
    if line.startswith("【蕾姆】") or line.startswith("【蕾姆】:"):
        content = line.split(":", 1)[1].strip().strip('"') if ":" in line else line[4:].strip()
        return "rem", content
    elif line.startswith("【拉姆】") or line.startswith("【拉姆】:"):
        content = line.split(":", 1)[1].strip().strip('"') if ":" in line else line[4:].strip()
        return "ram", content
    elif line.startswith("【系统】") or line.startswith("【系统】:"):
        content = line.split(":", 1)[1].strip().strip('"') if ":" in line else line[4:].strip()
        return "system", content
    elif line.startswith("【"):
        return "unknown", ""
    else:
        return None, line


def _streaming_segments(buffer: str) -> list:
    """V11.11：流式分段，与 parse_twin_segments 语义一致，处理不完整末行。

    末行规则：
    - 以【开头且未出现】→ 标签不完整，跳过该行（等后续 token 补全）
    - 其他 → 正常处理（标签可能完整，或无标签）

    返回的段是 parse_twin_segments(buffer) 的子集（最多缺少末行）。
    流式过程中可能暂时为空，不做兜底（与 parse_twin_segments 的兜底不同）。
    """
    segments = []
    current_speaker = None
    current_buffer = []

    def _flush():
        nonlocal current_speaker, current_buffer
        if current_buffer:
            text = "\n".join(current_buffer).strip()
            if text:
                segments.append((current_speaker or "rem", text))
            current_buffer = []

    lines = buffer.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        is_last = (i == len(lines) - 1)
        # 末行标签不完整：跳过，等后续 token 补全
        if is_last and line.startswith("【") and "】" not in line:
            break

        tag_type, content = match_speaker_tag(line)
        if tag_type in ("rem", "ram"):
            _flush()
            current_speaker = tag_type
            if content:
                current_buffer.append(content)
        elif tag_type == "system":
            # LLM 来源的【系统】不落 system，提取内容按无前缀行处理
            if content:
                if current_speaker is None:
                    current_speaker = "rem"
                current_buffer.append(content)
        elif tag_type == "unknown":
            # 未知【XX】标签，跳过
            continue
        else:  # None
            # 无前缀行：继承当前 speaker（默认 rem）
            if current_speaker is None:
                current_speaker = "rem"
            current_buffer.append(content)

    _flush()
    return segments


def parse_twin_segments(reply: str) -> list:
    """V11.10.0：解析双子回复为段列表 [(speaker, text), ...]。

    缓冲+flush 模型，speaker 继承，禁止 LLM 台词降级 system。
    V11.11：标签匹配抽至 match_speaker_tag，与 _streaming_segments 共用，行为不变。
    """
    segments = []
    current_speaker = None
    current_buffer = []

    def _flush():
        nonlocal current_speaker, current_buffer
        if current_buffer:
            text = "\n".join(current_buffer).strip()
            if text:
                segments.append((current_speaker or "rem", text))
            current_buffer = []

    for line in reply.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        tag_type, content = match_speaker_tag(line)
        if tag_type in ("rem", "ram"):
            _flush()
            current_speaker = tag_type
            if content:
                current_buffer.append(content)
        elif tag_type == "system":
            # LLM 来源的【系统】不落 system，提取内容按无前缀行处理
            if content:
                if current_speaker is None:
                    current_speaker = "rem"
                current_buffer.append(content)
        elif tag_type == "unknown":
            # 未知【XX】标签，跳过
            continue
        else:  # None
            # 无前缀行：继承当前 speaker（默认 rem）
            if current_speaker is None:
                current_speaker = "rem"
            current_buffer.append(content)

    _flush()

    if not segments:
        segments.append(("rem", reply.strip() or "……"))

    return segments


class LLMWorker(QObject):
    """后台线程：调用 LLM 生成回复（不冻结 UI）。"""
    finished = Signal(str)           # 完整回复文本
    stream_token = Signal(str)       # 流式 token
    error = Signal(str)

    def __init__(self, bot, user_input: str, stream: bool = True, reply_to: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.bot = bot
        self.user_input = user_input
        self.stream = stream
        self.reply_to = reply_to  # V14.2：引用回复（透传 bridge）

    def cancel(self) -> None:
        """V13.0：主线程调用——中断底层 LLM 流，使 run() 尽快返回。"""
        try:
            cancel_fn = getattr(self.bot, "cancel_stream", None)
            if cancel_fn is not None:
                cancel_fn()
        except Exception as e:
            _log(f"LLMWorker.cancel 异常: {e}")

    def run(self) -> None:
        try:
            if self.stream and hasattr(self.bot, 'chat_stream'):
                gen, _state = self.bot.chat_stream(self.user_input, reply_to=self.reply_to)  # V14.2：引用透传
                full = ""
                for token in gen:
                    full += token
                    self.stream_token.emit(token)
                self.finished.emit(full)
            else:
                reply = self.bot.chat(self.user_input, reply_to=self.reply_to)  # V14.2：引用透传
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
    
    SIZE = DIM['avatar_size']  # V10.15c：走 token

    def __init__(self, emoji: str = "", parent=None):
        super().__init__(parent)
        self._emoji = emoji
        self._pixmap_path: Optional[str] = None
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['emoji_sm']))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {COLORS['bg_surface_2']};
                border-radius: {self.SIZE // 2}px;
                border: 1px solid {COLORS['border_subtle']};
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
                f"color: {ROLE_COLORS.get(role, COLORS['text_muted'])};"
                f" background: transparent; border: none; padding: 0 16px;"
            )
            layout.addWidget(tag)

        # V11.10.1：streaming 顶部「生成中…」弱标签（text_muted 灰）
        if variant == "streaming":
            tag = QLabel("生成中…")
            tag.setObjectName("bubble_tag")
            tag.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['caption']))
            tag.setStyleSheet(
                f"color: {COLORS['text_muted']};"
                f" background: transparent; border: none; padding: 0 16px;"
            )
            layout.addWidget(tag)

        label = QLabel(text)
        label.setObjectName("bubble_text")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg']))
        label.setContentsMargins(0, 0, 0, 0)  # V10.14：去除双重 padding，统一由 QSS 控制
        label.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {fg};
                {border_css}
                border-radius: {RADIUS['large']}px;
                padding: 12px 16px;
            }}
        """)
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
        label.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                {border_css}
                border-radius: {radius}px;
                padding: {pad_v}px {pad_h}px;
            }}
        """)

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
        name_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))  # V10.14：去 Bold，弱化角色名层级
        # V10.15a：角色色统一走 ROLE_COLORS 字典
        name_label.setStyleSheet(f"color: {ROLE_COLORS.get(role, COLORS['text_muted'])};")
        self._name_label = name_label  # V14.0：failed 时追加「（未送达）」标记

        # 气泡
        bubble = BubbleWidget(text, role=role, variant=variant)
        bubble.setMaximumWidth(DIM['bubble_max_w'])
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


# ═══════════════════════════════════════════════
#  角色侧边面板
# ═══════════════════════════════════════════════

class CharacterPanel(QFrame):
    """角色状态面板（V11.0：沉浸化信息分层）。

    布局：立绘 → 名字 → 放大表情 → 好感数字+简条 → 阶段引号弱化 → 条件标记。
    鬼化/残香不进面板术语，仅通过表情传达。
    """

    def __init__(self, name: str, emoji: str, color: str, sprite_path: str = "", parent=None):
        super().__init__(parent)
        self._color = color
        self._speaking = False  # V12.0：说话态描边状态（幂等）
        self.setObjectName("character_panel")
        self.setFixedWidth(DIM['panel_w'])
        self.setStyleSheet(f"""
            QFrame#character_panel {{
                background-color: {COLORS['bg_surface']};
                border-left: 1px solid {COLORS['border_subtle']};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(8)

        # ── 立绘区域（不动）──
        self.avatar_frame = QFrame()
        self.avatar_frame.setFixedHeight(DIM['avatar_frame_h'])
        self.avatar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_surface_2']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: {RADIUS['large']}px;
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
                self.avatar_image.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['display']))
                self.avatar_image.setAlignment(Qt.AlignCenter)
        else:
            self.avatar_image.setText(emoji)
            self.avatar_image.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['display']))
            self.avatar_image.setAlignment(Qt.AlignCenter)
            placeholder = QLabel("立绘区域\n拖入 PNG 图片")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
            avatar_inner.addWidget(placeholder)

        avatar_inner.addWidget(self.avatar_image)
        layout.addWidget(self.avatar_frame)

        # ── ① 主信息：角色名 ──
        name_label = QLabel(name)
        name_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title_lg'], QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(f"color: {color};")
        layout.addWidget(name_label)

        # ── ② 主信息：放大表情（视觉焦点）──
        self.emotion_label = QLabel("😊")
        self.emotion_label.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['emoji_lg']))
        self.emotion_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.emotion_label)

        # ── ③ 主信息：好感数字 + 简条 ──
        self.favor_label = QLabel("好感 --/100")
        self.favor_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self.favor_label.setAlignment(Qt.AlignCenter)
        self.favor_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        layout.addWidget(self.favor_label)

        self.favor_bar = QProgressBar()
        self.favor_bar.setRange(0, 100)
        self.favor_bar.setTextVisible(False)
        self.favor_bar.setFixedHeight(4)
        self.favor_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: {COLORS['bg_surface_2']};
                border: none;
                border-radius: {RADIUS['xs']}px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: {RADIUS['xs']}px;
            }}
        """)
        layout.addWidget(self.favor_bar)

        # ── ④ 次信息：阶段引号弱化 ──
        self.stage_label = QLabel("「--」")
        self.stage_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self.stage_label.setAlignment(Qt.AlignCenter)
        self.stage_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        layout.addWidget(self.stage_label)

        # ── ⑤ 条件标记：互斥（记忆模糊 > 锁定 > 独立）──
        self.mark_label = QLabel("")
        self.mark_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small'], QFont.Bold))
        self.mark_label.setAlignment(Qt.AlignCenter)
        self.mark_label.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(self.mark_label)

        layout.addStretch()

    def update_state(self, favor: int, stage: str, emotion: str,
                     locked: bool = False, independence: float = 0.0,
                     recovery: float = 1.0) -> None:
        """更新面板状态。

        鬼化/残香仅通过 emotion 传达，不在此处显示术语。
        条件标记互斥优先级：记忆模糊 > 锁定 > 独立。
        """
        self.favor_label.setText(f"好感 {favor}/100")
        self.favor_bar.setValue(favor)
        self.stage_label.setText(f"「{stage}」")
        self.emotion_label.setText(emotion)

        # 互斥标记
        if recovery < 0.5:
            self.mark_label.setText("⚠ 记忆模糊")
            self.mark_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        elif locked:
            self.mark_label.setText("🔒 忠诚锁定")
            self.mark_label.setStyleSheet(f"color: {COLORS['accent']};")
        elif independence >= 0.6:
            self.mark_label.setText("✨ 独立人格")
            self.mark_label.setStyleSheet(f"color: {COLORS['accent']};")
        else:
            self.mark_label.setText("")

    def set_speaking(self, speaking: bool) -> None:
        """V12.0：说话态描边（幂等，状态未变不刷 QSS）。

        空闲 = border_subtle 1px；说话 = 角色色 2px。
        仅改 avatar_frame 边框，背景/圆角保持原样；任何异常只记日志。
        """
        if speaking == self._speaking:
            return
        self._speaking = speaking
        try:
            border = f"2px solid {self._color}" if speaking else f"1px solid {COLORS['border_subtle']}"
            self.avatar_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLORS['bg_surface_2']};
                    border: {border};
                    border-radius: {RADIUS['large']}px;
                }}
            """)
        except Exception as e:
            _log(f"set_speaking 异常: {e}")


# ═══════════════════════════════════════════════
#  樱花飘落动画
# ═══════════════════════════════════════════════

class SakuraOverlay(QWidget):
    """透明樱花飘落粒子动画。绘制在聊天区域上层，不拦截鼠标事件。"""

    PETAL_COUNT = 35
    COLORS_PINK = [
        (255, 183, 197, 99),    # 淡粉（V10.9.0：alpha 降低适配暗色背景）
        (255, 154, 162, 88),    # 樱粉
        (255, 204, 188, 77),    # 浅桃
        (255, 175, 188, 93),    # 中粉
        (252, 157, 172, 82),    # 深粉
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
#  历史浮层（V10.10）
# ═══════════════════════════════════════════════

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
        # V14.1：搜索命中词黄高亮（同一 highlight_plain_text，仅构造期渲染）
        content_display = highlight_plain_text(content, keyword)

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
        self._role_label.setStyleSheet(f"color: {sender_color};")
        header_row.addWidget(self._role_label)

        header_row.addStretch()

        self._time_label = QLabel(time_str)
        self._time_label.setFont(self.FONT_TIME)
        self._time_label.setStyleSheet(f"color: {COLORS['text_muted']};")
        header_row.addWidget(self._time_label)

        # 📍 定位按钮（保留 V10.12 功能）
        self._locate_btn = QPushButton("📍")
        self._locate_btn.setFixedSize(DIM['locate_btn'], DIM['locate_btn'])
        self._locate_btn.setCursor(Qt.PointingHandCursor)
        self._locate_btn.setToolTip("回到现场")
        self._locate_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 12px;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {COLORS['accent']};
            }}
        """)
        self._locate_btn.clicked.connect(lambda: self.locate_clicked.emit(msg_id))
        header_row.addWidget(self._locate_btn)

        self._layout.addLayout(header_row)

        # ── 第二行：正文摘要（最多约 2 行，可换行）──
        preview = content[:self.PREVIEW_WORDS] + ("…" if len(content) > self.PREVIEW_WORDS else "")
        self._preview_label = QLabel(highlight_plain_text(preview, keyword) if keyword else preview)
        self._preview_label.setFont(self.FONT_CONTENT)
        self._preview_label.setStyleSheet(f"color: {content_color};")
        self._preview_label.setWordWrap(True)
        self._layout.addWidget(self._preview_label)

        # ── 展开态全文（初始隐藏，独立区域 + 左边线着色）──
        self._detail_label = QLabel(content_display if keyword else content)
        self._detail_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self._detail_label.setWordWrap(True)
        self._detail_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._detail_label.setStyleSheet(f"""
            QLabel {{
                color: {COLORS['text_secondary']};
                background-color: {SURFACE_TINT['detail']};
                border-left: 2px solid {sender_color};
                border-radius: {RADIUS['xs']}px;
                padding: 8px 10px;
                margin-top: 4px;
            }}
        """)
        self._detail_label.hide()
        self._layout.addWidget(self._detail_label)

        self._update_style()

    def _update_style(self) -> None:
        if self._expanded:
            self.setStyleSheet(f"""
                QFrame#history_item {{
                    background-color: {SURFACE_TINT['active']};
                    border-left: 2px solid {self._sender_color};
                    border-radius: {RADIUS['sm2']}px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame#history_item {{
                    background-color: transparent;
                    border-left: 2px solid {self._sender_color};
                    border-radius: {RADIUS['sm2']}px;
                }}
                QFrame#history_item:hover {{
                    background-color: {SURFACE_TINT['hover']};
                }}
            """)

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
    locate_requested = Signal(int)  # V10.12：定位请求透传 message_id 给主窗口

    def __init__(self, conv_store, parent=None):
        super().__init__(parent)
        self._conv_store = conv_store
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
        self._card.setStyleSheet(f"""
            QFrame#history_card {{
                background-color: {COLORS['bg_surface_2']};
                border: 1px solid {COLORS['border_focus']};
                border-radius: {RADIUS['large']}px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── 卡片标题栏 ──
        header_frame = QFrame()
        header_frame.setFixedHeight(DIM['history_header_h'])
        header_frame.setStyleSheet(
            f"border-bottom: 1px solid {COLORS['border_subtle']};"
        )
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(20, 0, 16, 0)

        title = QLabel("📖 宅邸日志")
        title.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title'], QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_primary']};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(DIM['icon_btn'], DIM['icon_btn'])
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_muted']};
                border: none;
                font-size: 14px;
            }}
            QPushButton:hover {{
                color: {COLORS['text_primary']};
            }}
        """)
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
        self._search_box.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE_TINT['input']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: {RADIUS['medium']}px;
                padding: 4px 10px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['border_focus']};
            }}
        """)
        self._search_box.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self._search_box)
        card_layout.addWidget(search_frame)

        # ── 历史列表滚动区 ──
        self._list_scroll = QScrollArea()
        self._list_scroll.setWidgetResizable(True)
        self._list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list_scroll.setFrameShape(QFrame.NoFrame)
        self._list_scroll.setStyleSheet("background-color: transparent;")

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
            empty.setStyleSheet(f"color: {COLORS['text_muted']}; padding: 40px;")
            self._list_layout.insertWidget(0, empty)
            return

        # records 来自 get_recent 已是正序，倒序插入实现最新在上
        for record in reversed(records):
            item_widget = HistoryItemWidget(record, keyword=keyword)  # V14.1：keyword 透传高亮
            item_widget.locate_clicked.connect(self.locate_requested)  # V10.12
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
        try:
            results = self._conv_store.search(keyword, limit=50)
        except Exception:
            results = []
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
        label.setStyleSheet(f"color: {COLORS['text_muted']}; padding: 40px;")
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
        self.mem = self.store.load()
        self.conv_store = ConversationStore()
        _log(f"记忆加载: mode={self.mem.get('mode')} arc={self.mem.get('arc')} data={self.store.path}")

        # 迁移旧 JSON chat_history → SQLite（仅首次）
        old_history = self.mem.get("chat_history", [])
        if old_history:
            migrated = self.conv_store.migrate_from_json(old_history)
            if migrated:
                _log(f"SQLite 迁移: {migrated} 条旧消息")
                self.store.set("chat_history", [])  # 清空 JSON 中的旧历史

        self.mode = self.mem.get("mode", "llm")
        self._streaming_bubbles: list[ChatMessageWidget] = []  # V11.11：多临时泡列表
        self._streaming_buffer: str = ""
        self._streaming_active: bool = False
        self._current_speaker: Optional[str] = None  # V12.0：当前说话人（"rem"/"ram"/None）
        self._breath_group: Optional[QSequentialAnimationGroup] = None  # V12.0：状态栏呼吸组
        _log(f"UI 动效: {'启用' if ENABLE_UI_MOTION else '禁用（REZERO_DISABLE_UI_MOTION=1）'}")
        self._llm_thread: Optional[QThread] = None
        self._llm_worker: Optional[LLMWorker] = None
        self._history_overlay: Optional[HistoryOverlay] = None  # V10.10
        self._session_start_time: str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # V11.6.5
        self._pending_user_widget: Optional[ChatMessageWidget] = None  # V14.0：本轮发送的用户句（取消→failed）
        self._quote: Optional[dict] = None  # V14.2：待发送的引用 {id, sender, preview}

        # 世界状态（持久化）
        from shared.state import WorldState
        saved_world = self.mem.get("world_state")
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
        today_str = datetime.now().strftime("%Y-%m-%d")
        last_greeting = self.world.last_greeting_date
        day_changed = (last_greeting != today_str)
        msg_count = self.conv_store.count()

        if _VIGNETTE_DISABLED:
            _log("开场引言已通过 REZERO_DISABLE_VIGNETTE 禁用")
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
        if msg_count > 0 and not day_changed:
            self._show_ambient_line()
        elif msg_count > 0 and day_changed:
            # 换日时问候正文已带天气，不额外打轻氛围避免刷屏
            _log("换日：日更问候已含天气，跳过轻氛围避免刷屏")

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
                    conversation_store=self.conv_store,
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
        header.setFixedHeight(DIM['header_h'])
        header.setStyleSheet(f"background-color: {COLORS['bg_header']};")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 0, 18, 0)

        title = QLabel("❄  Re:Zero 双子系统  —  Rem × Ram")
        title.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title_lg'], QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['text_primary']};")
        header_layout.addWidget(title)
        header_layout.addStretch()

        # 历史搜索
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索对话…")
        self.search_box.setFixedWidth(DIM['search_box_w'])
        self.search_box.setFixedHeight(DIM['search_box_h'])
        self.search_box.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE_TINT['input']};
                color: {COLORS['text_primary']};
                border: 1px solid {COLORS['border_subtle']};
                border-radius: {RADIUS['small']}px;
                padding: 2px 8px;
            }}
            QLineEdit:focus {{
                border-color: {COLORS['border_focus']};
            }}
        """)
        self.search_box.returnPressed.connect(self._do_search)
        # V14.1：清空搜索框 → 清除全部黄高亮
        self.search_box.textChanged.connect(self._on_top_search_changed)
        header_layout.addWidget(self.search_box)

        # 搜索按钮
        search_btn = QPushButton("🔍")
        search_btn.setFixedSize(DIM['icon_btn'], DIM['icon_btn'])
        search_btn.setCursor(Qt.PointingHandCursor)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_secondary']};
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
        arc_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        arc_label.setStyleSheet(f"color: {COLORS['accent']};")
        self._arc_label = arc_label
        header_layout.addWidget(arc_label)

        # V10.10：历史浮层入口
        history_btn = QPushButton("📖 回忆")
        history_btn.setFixedHeight(DIM['history_btn_h'])
        history_btn.setCursor(Qt.PointingHandCursor)
        history_btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        history_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLORS['text_secondary']};
                border: none;
                padding: 0 6px;
            }}
            QPushButton:hover {{
                color: {COLORS['accent']};
            }}
        """)
        history_btn.clicked.connect(self._open_history)
        header_layout.addWidget(history_btn)

        main_layout.addWidget(header)

        # ── 主体三栏布局 ──
        body = QHBoxLayout()
        body.setSpacing(0)

        # 左侧：蕾姆面板
        self.rem_panel = CharacterPanel("蕾 姆", "🩵", COLORS["rem_accent"], sprite_path=_asset_path("rem_sprite.jpg"))
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
        input_frame.setStyleSheet(f"background-color: {COLORS['bg_surface']}; border-top: 1px solid {COLORS['border_subtle']};")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(6)

        # V14.2：引用条（默认隐藏；发起引用后显示「↪ 回复 …」，可 × 取消）
        self._quote_bar = QFrame()
        self._quote_bar.setObjectName("quote_bar")
        self._quote_bar.setStyleSheet(
            "background-color: rgba(201,169,110,0.08);"
            " border-left: 3px solid rgba(201,169,110,0.8); border-radius: 4px;"
        )
        quote_layout = QHBoxLayout(self._quote_bar)
        quote_layout.setContentsMargins(10, 3, 6, 3)
        quote_layout.setSpacing(6)
        self._quote_label = QLabel("")
        self._quote_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self._quote_label.setStyleSheet(f"color: {COLORS['text_secondary']}; background: transparent;")
        quote_layout.addWidget(self._quote_label, 1)
        self._quote_close = QPushButton("×")
        self._quote_close.setFixedSize(20, 20)
        self._quote_close.setCursor(Qt.PointingHandCursor)
        self._quote_close.setToolTip("取消引用")
        self._quote_close.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {COLORS['text_muted']};
                border: none; font-size: 14px; border-radius: 10px;
            }}
            QPushButton:hover {{ color: {COLORS['accent']}; background-color: rgba(255,255,255,0.06); }}
        """)
        self._quote_close.clicked.connect(self._clear_quote)
        quote_layout.addWidget(self._quote_close)
        self._quote_bar.hide()
        input_layout.addWidget(self._quote_bar)

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
            btn.setFixedHeight(DIM['quick_btn_h'])
            btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['bg_surface_2']};
                    color: {COLORS['text_secondary']};
                    border: 1px solid {COLORS['border_subtle']};
                    border-radius: {RADIUS['small']}px;
                    padding: 2px 10px;
                }}
                QPushButton:hover {{
                    background-color: {SURFACE_TINT['input']};
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
        self.input_box.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg']))
        self.input_box.setFixedHeight(DIM['input_box_h'])
        self.input_box.installEventFilter(self)
        input_row.addWidget(self.input_box, 1)

        self.send_btn = QPushButton("发 送")
        self.send_btn.setFixedSize(DIM['send_btn_w'], DIM['send_btn_h'])
        self.send_btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg'], QFont.Bold))
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        input_layout.addLayout(input_row)
        chat_section.addWidget(input_frame)

        body.addLayout(chat_section, 1)

        # 右侧：拉姆面板
        self.ram_panel = CharacterPanel("拉 姆", "💗", COLORS["ram_accent"], sprite_path=_asset_path("ram_sprite.jpg"))
        body.addWidget(self.ram_panel)

        main_layout.addLayout(body, 1)

        # ── 底部状态栏 ──
        footer = QFrame()
        footer.setFixedHeight(DIM['footer_h'])
        footer.setStyleSheet(f"background-color: {COLORS['bg_header']}; border-top: 1px solid {COLORS['border_subtle']};")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 0, 14, 0)

        self.footer_label = QLabel("就绪")
        self.footer_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self.footer_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        footer_layout.addWidget(self.footer_label)
        footer_layout.addStretch()

        mode_label = QLabel("LLM 桥接")
        mode_label.setTextFormat(Qt.RichText)  # V10.14：启用 RichText 主次分层
        mode_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        mode_label.setStyleSheet(f"color: {COLORS['text_secondary']};")
        self._mode_label = mode_label
        footer_layout.addWidget(mode_label)

        main_layout.addWidget(footer)

    def _apply_theme(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {COLORS['bg_base']};
            }}
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QTextEdit {{
                border: 1px solid {COLORS['border_subtle']};
                border-radius: {RADIUS['medium']}px;
                padding: 8px 10px;
                background-color: {COLORS['bg_surface']};
                color: {COLORS['text_primary']};
            }}
            QTextEdit:focus {{
                border-color: {COLORS['border_focus']};
            }}
            QPushButton {{
                background-color: {COLORS['accent']};
                color: white;
                border: none;
                border-radius: {RADIUS['small']}px;
            }}
            QPushButton:hover {{
                background-color: {COLORS['accent_hover']};
            }}
            QPushButton:pressed {{
                background-color: {COLORS['accent_press']};
            }}
            QPushButton:disabled {{
                background-color: {COLORS['btn_disabled_bg']};
                color: {COLORS['btn_disabled_fg']};
            }}
        """)

    # ── 命令处理 ────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        if cmd == "/status":
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
        self._teardown_llm_thread()  # V13.0：流式中切模式先收尾（防旧 worker 回调/错对象读）
        self._streaming_active = False
        self._set_breathing(True)
        self.send_btn.setText("发送")
        self.send_btn.setEnabled(True)
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
                    conversation_store=self.conv_store,
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
            self._update_status_bar()  # V10.14：统一走 RichText 刷新，不再手动 setText
            self._update_panels()
        except Exception as e:
            _log(f"_switch_mode 失败: {e}\n{traceback.format_exc()}")
            self._append_parsed_message("系统", f"切换失败：{e}", "system")

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
            if self.mode != "llm" or not hasattr(self.bot, 'world'):
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
                    _log(f"引言回调异常: {e}\n{traceback.format_exc()}")

            # ── V10.10.4: frozen 安全路径 ──
            # frozen EXE 下 QThread + LLM 调用触发原生崩溃（0xC0000409），
            # 改为主线程直接走 L2/L3 模板生成，不创建线程不调 LLM。
            if getattr(sys, "frozen", False):
                _log("frozen 安全引言路径")
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
                        _log(f"引言 Worker 异常: {e}\n{traceback.format_exc()}")
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
            _log(f"引言生成启动失败: {e}\n{traceback.format_exc()}")
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
        results = self.conv_store.search(query, limit=10)
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
            preview = text[:60] + ("…" if len(text) > 60 else "")
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
                _log(f"高亮异常 #{getattr(w, 'message_id', '?')}: {e}")

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

    def _append_parsed_message(self, sender: str, text: str, role: str, save: bool = True, transient: bool = False, message_id: Optional[int] = None, force_center: bool = False, highlight: bool = False, variant: str = "system", animate: bool = True) -> Optional[QWidget]:
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
            self._play_entrance_animation(msg)

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

        if self.mode == "llm" and hasattr(self.bot, 'chat_stream'):
            self._send_llm_stream(text, reply_to=reply_to)
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
            # V11.10.0：错误不走解析器，直接 system 消息
            self._append_parsed_message("系统", f"出错了：{e}", "system")
            self._finish_reply()
            _log(f"异常: {e}")
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
                _log(f"worker.cancel 异常: {e}")
        if self._llm_thread is not None:
            if self._llm_thread.isRunning():
                self._llm_thread.requestInterruption()
                self._llm_thread.quit()
                if not self._llm_thread.wait(2000):
                    _log("线程收尾超时（2s），最后手段 terminate")
                    self._llm_thread.terminate()
                    self._llm_thread.wait(1000)
        self._llm_worker = None
        self._llm_thread = None
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""

    def _cancel_streaming(self) -> None:
        """V13.0：用户取消当前流式回复。V14.0：本轮用户句标记未送达（failed）。"""
        _log("用户取消流式回复")
        self._teardown_llm_thread()
        self._streaming_active = False
        pending = getattr(self, "_pending_user_widget", None)
        if pending is not None and pending.message_id:
            try:
                self.conv_store.update_status(pending.message_id, "failed")
                pending.set_failed()
                _log(f"取消：用户句 #{pending.message_id} 标记 failed")
            except Exception as e:
                _log(f"失败态标记异常: {e}")
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
            _log("流式校验失败：丢弃未校验全文，展示 View-Only 回避文案")
            self._clear_streaming_bubbles()
            self._streaming_buffer = ""
            fallback_text = (
                getattr(self.bot, "_stream_fallback_text", "")
                or '【蕾姆】: "……这个话题，蕾姆想先放一放。您愿意说点别的吗？"'
            )
            self._parse_twin_reply(fallback_text, highlight=False, save=False)
            self._finish_reply()
            _log("流式校验失败：已展示回避文案")
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
        _log(f"流式错误: {err}")

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
            w = self._append_parsed_message(sender, text, role, save=False, message_id=msg_id, animate=False)  # V12.0：历史批量回放跳过入场动画
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

        self.rem_panel.update_state(
            favor=state.favor,
            stage=FAVOR_LEVEL_CN.get(state.favor_level.name, state.favor_level.name),
            emotion=rem_emotion,
            locked=state.locked,
            independence=state.independence,
            recovery=state.recovery,
        )

        # ── 拉姆表情（8 档：姐姐危险感知 + 自身阶段）──
        if state.witch_scent >= 3:
            ram_emotion = "😠"       # P1 姐姐的怒意
        elif state.oni_stage >= OniStage.FULL:
            ram_emotion = "😤"       # P2 姐姐的警惕
        else:
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
            # 活跃事件可见化：有事件且与 period/weather 相容才追加（V11.9.2）
            ram_part = state.ram_stage.value
            ev = w.active_event or ""
            if ev and event_compatible(w.period, w.weather, ev):
                event_short = ev[:16] + '…' if len(ev) > 16 else ev
                ram_part += f"  ·  {event_short}"
            # V10.14：RichText 主次分层（金色模式 / 次亮主信息 / 弱化次信息）
            mode_text = "LLM" if self.mode == "llm" else "本地"
            sep = f'<span style="color:{COLORS["text_muted"]};">  ·  </span>'
            self._mode_label.setText(
                f'<span style="color:{COLORS["accent"]};">{mode_text}</span>'
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

        ENABLE_UI_MOTION=False 时不创建任何动画对象（完全静态）。
        """
        if not ENABLE_UI_MOTION:
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
            _log(f"呼吸动画创建异常: {e}")
            self._breath_group = None

    def _set_breathing(self, active: bool) -> None:
        """V12.0：呼吸暂停/恢复。思考中 pause（opacity 停在当前值），完成后 resume。"""
        if not ENABLE_UI_MOTION:
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
            _log(f"呼吸暂停/恢复异常: {e}")

    def _set_speaking_panels(self, speaker: Optional[str]) -> None:
        """V12.0：点亮/复位侧栏说话描边。speaker=None 全部复位。

        状态跟踪（_current_speaker）不受开关影响；仅 QSS 刷新受 ENABLE_UI_MOTION 控制。
        """
        self._current_speaker = speaker
        if not ENABLE_UI_MOTION:
            return
        try:
            self.rem_panel.set_speaking(speaker == "rem")
            self.ram_panel.set_speaking(speaker == "ram")
        except Exception as e:
            _log(f"_set_speaking_panels 异常: {e}")

    def _play_entrance_animation(self, widget: QWidget) -> None:
        """V12.0：正式消息泡轻入场 — opacity 0→1，200ms，OutCubic。

        动画结束即卸载 effect（防离屏渲染残留）；widget 可能已被删除，
        清理回调与创建路径均 try/except，异常只记日志不拖垮事件循环。
        """
        if not ENABLE_UI_MOTION:
            return
        try:
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            anim = QPropertyAnimation(effect, b"opacity", widget)
            anim.setDuration(200)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(
                lambda w=widget, e=effect: self._cleanup_entrance_effect(w, e)
            )
            anim.start(QAbstractAnimation.DeleteWhenStopped)
        except Exception as e:
            _log(f"入场动画异常: {e}")

    def _cleanup_entrance_effect(self, widget, effect) -> None:
        """卸载入场动画的 opacity effect（widget 可能已被删除，全部 try/except）。"""
        try:
            widget.setGraphicsEffect(None)
        except Exception:
            pass
        try:
            effect.deleteLater()
        except Exception:
            pass

    # ── V14.2：引用回复 ────────────────────────

    def _on_quote_request(self, message_id: int) -> None:
        """右键「引用」：校验消息仍为 normal，展示引用条。"""
        try:
            record = self.conv_store.get_by_id(message_id)
        except Exception as e:
            _log(f"引用查询异常: {e}")
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
            _log(f"撤回查询异常: {e}")
            return
        if not record or record.get("role") != "user" or record.get("status") != "normal":
            return
        # 3 分钟窗口（DB created_at 为权威时间戳，格式 YYYY-MM-DD HH:MM:SS）
        created = record.get("created_at", "")
        try:
            dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            _log(f"撤回：created_at 解析失败 {created!r}")
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
                _log(f"history 剪枝失败: {e}")

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

    def _close_history(self) -> None:
        """关闭历史浮层。"""
        if self._history_overlay:
            self._history_overlay.hide()
            self.clear_all_highlights()  # V14.1：关闭回忆浮层 → 清除黄高亮
            self.input_box.setFocus()
            _log("历史浮层已关闭")

    # ── V10.12：历史条目定位 ───────────────────

    def _locate_message(self, message_id: int) -> None:
        """根据 message_id 定位主聊天中的消息 widget。

        成功：关闭浮层 → 滚动到目标 → 短暂高亮 2 秒
        失败：关闭浮层 → transient 提示（不污染主聊天流）
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

        # 3. 成功：滚动 + 高亮
        if target is not None:
            self.scroll.ensureWidgetVisible(target)
            self._highlight_widget(target)
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
            _log(f"定位降级查询异常: {e}")

        tip = "📍 该消息不在当前可见范围（可能已随对话滚动移出）。"
        if summary:
            tip += f"内容摘要：{summary}"
        self._append_parsed_message("系统", tip, "system", save=False, transient=True)

    def _highlight_widget(self, widget) -> None:
        """短暂高亮目标 widget（金色半透明背景，2 秒后恢复）。

        不动 BubbleWidget 内部样式，仅设置 ChatMessageWidget 外层背景。
        """
        try:
            widget.setStyleSheet(
                f"background-color: {COLORS['locate_highlight']}; border-radius: {RADIUS['small']}px;"
            )
            QTimer.singleShot(2000, lambda: widget.setStyleSheet(""))
        except Exception as e:
            _log(f"高亮异常: {e}")

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
            _log(f"生成 session 摘要失败: {e}")
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
            _log(f"session 摘要保存失败: {e}")

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
            self.store.set("world_state", self.world.save_dict())
            _log(f"日更问候已展示: period={period} weather={weather} date={today_str}")
        except Exception as e:
            _log(f"日更问候展示失败: {e}\n{traceback.format_exc()}")

    def _show_ambient_line(self) -> None:
        """V11.9.0：同日轻氛围一行 — period · weather · active_event，View-Only。

        V11.9.2：active_event 与 period/weather 语义冲突时省略 event 段并打日志。
        仅在同日有历史重开时展示（空库完整引言时不重复打）。
        save=False，不进 ConversationStore。
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
            self._append_parsed_message("系统", f"🌧️ {text}", "system", save=False)
            _log(f"轻氛围已展示: {text}")
        except Exception as e:
            _log(f"轻氛围展示失败: {e}")

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
            _log(f"续聊卡展示失败: {e}")

    def closeEvent(self, event) -> None:
        self._teardown_llm_thread()  # V13.0：先收尾线程，再存状态（防 worker 写一半）
        self._save_state()
        self._save_session_summary()  # V11.6.5: 写入 session 摘要
        event.accept()


def _install_crash_handler() -> None:
    """安装崩溃捕获：excepthook 捕获未处理异常写入日志。"""
    crash_path = os.path.join(get_data_dir(), "crash.log")
    try:
        def _excepthook(exc_type, exc_value, exc_tb):
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            _log(f"未捕获异常: {exc_value}\n{msg}")
            try:
                with open(crash_path, "a", encoding="utf-8") as f:
                    f.write(f"\n[{datetime.now().isoformat()}] 未捕获异常:\n{msg}")
            except Exception:
                pass
        sys.excepthook = _excepthook
    except Exception as e:
        _log(f"崩溃处理器安装失败: {e}")


def main() -> None:
    _install_crash_handler()
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
                _log(f"AppUserModelID 设置失败（非致命）: {e}")

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
            _log("[警告] 图标文件不存在，QIcon 将为空，任务栏/窗口图标会异常")

        # frozen 时补充：用 EXE 自身内嵌图标作为兜底（Windows 可从 PE 资源提取）
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            try:
                exe_icon = QIcon(sys.executable)
                if not exe_icon.isNull():
                    app_icon = exe_icon
                    _log(f"frozen 兜底: 使用 EXE 内嵌图标 ({sys.executable})")
                else:
                    _log("frozen 兜底: EXE 内嵌图标为空，保持 ICO 文件图标")
            except Exception as e:
                _log(f"frozen 兜底失败（非致命）: {e}")

        app.setWindowIcon(app_icon)
        app.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        app.aboutToQuit.connect(lambda: _log("aboutToQuit 信号触发"))
        window = TwinChatApp()
        window.show()
        # show 后二次 setWindowIcon：强制任务栏刷新图标关联
        window.setWindowIcon(app_icon)
        _log("show 后二次 setWindowIcon 已执行")
        _log("窗口 show 完成")
        _log("即将进入 app.exec() 事件循环")
        ret = app.exec()
        _log(f"app.exec() 返回 {ret}")
        sys.exit(ret)
    except Exception as e:
        _log(f"main 异常: {e}\n{traceback.format_exc()}")
        raise


if __name__ == "__main__":
    main()
