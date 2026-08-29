"""Design Tokens（V15.0-M3 出库：唯一真源）。

V10.9.0 起的暗色视觉基线 token 自 gui.py 出库——本模块为**纯数据、零 Qt 依赖**，
供 gui.py 与一切新 UI 模块（回忆之书等）共同引用；gui.py 顶部转口导入保持
`gui.DIM` 等旧引用兼容。改 token 只改这里（DESIGN_SYSTEM_V1.md 的工程落点）。
"""

# ═══════════════════════════════════════════════
#  Design Tokens（V10.9.0 暗色视觉基线）
# ═══════════════════════════════════════════════
COLORS = {
    # ── 背景层级 ──
    "bg_base":       "#101626",               # 宅邸夜色底
    "bg_surface":    "rgba(19,25,42,0.91)",   # 玻璃面板，透出宅邸背景
    "bg_surface_2":  "rgba(34,39,61,0.84)",   # 气泡/卡片表面
    "bg_header":     "rgba(10,14,27,0.95)",   # 顶栏/底栏
    "input":         "rgba(18,27,45,0.94)",   # 专注输入表面

    # ── 边框（低对比细边） ──
    "border_subtle": "rgba(179,211,239,0.16)",
    "border_focus":  "rgba(135,220,248,0.68)",

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
    "accent":        "#b99a62",   # 宅邸金色点缀（发送按钮、章节标签）
    "accent_hover":  "#d6b877",
    "accent_press":  "#927542",

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
# V14.8 体验侧收尾：字体回退链（微软雅黑 → 中文回退 → 系统兜底）
# 跨平台：Windows 雅黑 / macOS 苹方 / Linux Noto CJK；QFont 用逗号分隔 family 列表
FONT_FAMILY = {
    "ui":    "Microsoft YaHei, PingFang SC, Noto Sans CJK SC, WenQuanYi Micro Hei, sans-serif",
    "emoji": "Segoe UI Emoji, Apple Color Emoji, Noto Color Emoji, sans-serif",
}

# V14.8 体验侧收尾：caption 8→9（可读性）、title 12→13（与正文 12 拉开层级）
FONT_SIZE = {
    "caption":   9,   # 时间戳、最弱辅助
    "small":     9,   # 角色名、按钮文字、状态栏
    "body":     10,   # 历史正文、面板数值、搜索框、系统标签(长)
    "body_lg":  12,   # V14.5：气泡正文、输入框、发送按钮（11→12 中文阅读优化）
    "title":    13,   # V14.8：浮层标题（12→13 与正文分层）
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
        "fg": "#34374d",  # 浅色聊天舞台上的正文
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
        "fg": "#34374d",
        "border": f"border-left: 3px solid {COLORS['ram_left']};",
        "hl_border": "border-left: 5px solid rgba(255,126,179,0.70);",
        "hl_bg": "rgba(255,126,179,0.15)",
        "stream_bg": "rgba(255,126,179,0.04)",
        "stream_border": "border-left: 2px solid rgba(255,126,179,0.15);",
        "stream_fg": COLORS['text_secondary'],
    },
    "user": {
        "bg": COLORS['user_bubble'],
        "fg": "#34374d",
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
#  V2 扩充组（V16 表现层：DESIGN_SYSTEM_V2.md 的 token 落点）
# ═══════════════════════════════════════════════

# 动效四律（宪法 §一）。enabled 由运行时判定覆写（offscreen 自动禁用）。
MOTION = {
    "enabled":       True,
    "fast":          150,   # ms：微反馈（hover/press）
    "base":          220,   # ms：消息入场（100–400ms 黄金带内）
    "slow":          320,   # ms：浮层
    "enter_curve":   "OutCubic",
    "spring_curve":  "OutBack",
    "stagger_ms":    30,    # 级联步长
    "stagger_max":   8,     # 至多前 8 项错落，其后同时出现
}

# 字排（宪法 §二）。存量字号不动（FONT_SIZE 即存量字阶）。
TYPE = {
    "lh_body_pct":   155,  # 正文行高百分比（气泡富文本 div 用；V10.9.2 为 150）
    "lh_title_pct":  120,
    "caps_spacing":  0.12,  # 英文全大写标签字距（em，QFont.setLetterSpacing 换算）
}

# 层级与光影（宪法 §三，widgets 代偿策略：内发光顶边 + 边框分档）
ELEVATION = {
    "glow_top":      "rgba(255,255,255,0.07)",   # 1px 受光高光（一切浮起表面）
    "card_border":   "rgba(255,255,255,0.10)",
}

# 玻璃五档（宪法 §四：Different layers, different opacity——禁止手写散落 rgba）
SURFACE = {
    "glass_15": "rgba(18,19,25,0.15)",   # 背景遮罩层
    "glass_35": "rgba(18,19,25,0.35)",   # 快捷件
    "glass_45": "rgba(18,19,25,0.45)",   # 侧栏
    "glass_55": "rgba(18,19,25,0.55)",   # 主卡
    "glass_60": "rgba(18,19,25,0.60)",   # 输入框
}
