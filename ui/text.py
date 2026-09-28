"""纯文本 / 解析（事件相容、世界行、分段、命中高亮、颜色转换）。"""

from __future__ import annotations

import re
import html
from design_tokens import (  # noqa: E402
    COLORS, DIM, ELEVATION, FONT_FAMILY, FONT_SIZE, LAYOUT, MOTION,
    RADIUS, RAM_EMOTION_BY_STAGE, RAM_EMOTION_DEFAULT, RAM_EMOTION_ONI,
    RAM_EMOTION_WITCH, ROLE_BUBBLE_FALLBACK, ROLE_BUBBLE_STYLES,
    ROLE_COLORS, SPACING, SURFACE, SURFACE_TINT, TYPE,
)


# 时段关键词：event 含这些词且与当前 period 不一致 → 语义冲突。
# "入夜" 视为 "夜晚"/"深夜" 的别名，不与这两个时段冲突。
PERIOD_KEYWORDS = ["清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜", "入夜"]


# 天气 ↔ active_event 语义冲突关键词：命中则跳过 event 拼接并打日志。
WEATHER_EVENT_CONFLICT = {
    "大雨": ["花园", "盛开", "晒", "阳光", "晾晒", "白布", "温暖"],
    "阴沉": ["阳光", "晒", "晴朗", "盛开", "晾晒", "白布", "温暖"],
    "小雨": ["晒", "阳光", "晾晒"],
}


def highlight_plain_text(text: str, keyword: str, surface: str = "light") -> str:
    """V14.1：HTML escape 后把命中词包装为高亮 span（多命中全部高亮）。

    V16.5.4 / SPEC-20260922-20（高亮柔化）：按**显示表面**分档——
    - ``"light"``（默认）：聊天区浅底气泡 → 半透明暖黄底 + 下划线，不覆盖文字色（对比 9.28:1）；
    - ``"dark"``：历史浮层深底卡片 → 更弱暖黄底 + 提亮文字（``#FFE6B0``，对比 6.52:1）；
    - 未知 surface 值一律**回退 light**（不抛异常）。

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
    if surface == "dark":
        bg, fg = COLORS['search_hit_dark_bg'], COLORS['search_hit_dark_fg']
    else:  # light 与一切未知值
        bg, fg = COLORS['search_hit_light_bg'], COLORS['search_hit_light_fg']
    # 下划线是补充标识（背景对比不足时仍可辨命中 —— 可访问性兜底，见 SPEC-20 §目标）
    hit_style = f"background-color: {bg}; " + (f"color: {fg}; " if fg else "") + "text-decoration: underline;"
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


def _shorten_event(ev: str, limit: int) -> str:
    """SPEC-20260922-24：**子句感知**截断——硬切前先退到第一个子句，绝不产出「，…」。

    规则：总长 ≤ limit 原样返回；否则取第一个子句（按「，」「,」切）——
    子句 ≤ limit → 「子句…」；子句本身仍超长 → 硬切 limit + 「…」。
    """
    if not ev or len(ev) <= limit:
        return ev
    head = re.split(r"[，,]", ev, maxsplit=1)[0].strip()
    if head and len(head) <= limit:
        return head + "…"
    return ev[:limit] + "…"


def format_world_line(period: str, weather: str, event: str, *,
                      max_event: int = 16, prefix: str = "",
                      head: bool = True, suffix_sep: str = " · ") -> str:
    """A15（SPEC-20260922-12 B2）：世界行**唯一**格式化实现。

    此前 `_refresh_ambient` 与 `_update_status_bar` 各自内联「事件相容判定 + 截断」，
    两处截断长度还不一致（14 / 16 字）。本函数收口为单一实现，
    截断长度、分隔符、是否带 `period · weather` 行首全部参数化——
    **调用点现值原样保留 ⇒ 文案零变化**（是否统一长度属观感决策，留待真机批次）。

    head=False 时只返回事件后缀（供状态栏拼接用）。

    SPEC-20260922-24：截断改 ``_shorten_event``（子句感知，不吊「，」）；两调用点统一 16。
    """
    ev = event or ""
    head_txt = f"{prefix}{period} · {weather}" if head else ""
    if ev and event_compatible(period, weather, ev):
        # SPEC-20260922-24：子句感知截断（原硬切会把「，」吊在结尾）
        ev_short = _shorten_event(ev, max_event)
        return f"{head_txt}{suffix_sep}{ev_short}"
    return head_txt


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


def _rgba_to_qcolor(rgba_str: str):
    """解析 'rgba(r,g,b,a)' 字符串为 QColor（供 QPainter 使用）。"""
    s = rgba_str.strip()[5:-1]  # 去掉 "rgba(" 和 ")"
    r, g, b, a = s.split(",")
    from PySide6.QtGui import QColor
    return QColor(int(r), int(g), int(b), int(float(a) * 255))


