"""QSS 构造器（SPEC-20260922-18 / B6·A14 收口）。

- 只消费 `design_tokens`（**禁止裸色值/裸尺寸**——本批为值等价迁移，视觉零变化）；
- **零 Qt 依赖**（纯字符串构造 + f-string），可直接单测；
- 单一真源：`gui.py` / `ui/dashboard.py`（原 `status_dashboard.py`，SPEC-22 S1c 归位）的全部内联 QSS 都出自本模块；
- 等价性判据见 `tests/test_theme_equivalence.py`（golden 快照逐字节比对）。
"""
from __future__ import annotations

from design_tokens import COLORS, ELEVATION, RADIUS, ROLE_COLORS, SURFACE_TINT


def color_only(color) -> str:
    return (
        f"color: {color};"
    )

def transparent_bg() -> str:
    return (
        "background: transparent;"
    )

def transparent_bg_color() -> str:
    return (
        "background-color: transparent;"
    )

def avatar_label_base(size, ring) -> str:
    return (
        f"\n            QLabel {{\n                background-color: {COLORS['bg_surface_2']};\n                border-radius: {size}px;\n                border: 2px solid {ring};\n            }}\n        "
    )

def bubble_tag_role(role) -> str:
    return (
        f"color: {ROLE_COLORS.get(role, COLORS['text_muted'])}; background: transparent; border: none; padding: 0 16px;"
    )

def bubble_tag_muted() -> str:
    return (
        f"color: {COLORS['text_muted']}; background: transparent; border: none; padding: 0 16px;"
    )

def bubble_body(bg, fg, border_css) -> str:
    return (
        f"\n            QLabel {{\n                background-color: {bg};\n                color: {fg};\n                {border_css}\n                border-radius: 14px;\n                padding: 10px 14px;\n                line-height: 150%;  /* V14.5：中文长文阅读行距优化 */\n            }}\n        "
    )

def system_label(fg, bg, border_css, radius, pad_v, pad_h) -> str:
    return (
        f"\n            QLabel {{\n                color: {fg};\n                background-color: {bg};\n                {border_css}\n                border-radius: {radius}px;\n                padding: {pad_v}px {pad_h}px;\n            }}\n        "
    )

def character_panel_frame() -> str:
    return (
        f"\n            QFrame#character_panel {{\n                background-color: {COLORS['bg_surface']};\n                border-left: 1px solid {COLORS['border_subtle']};\n            }}\n        "
    )

def character_avatar_frame() -> str:
    return (
        f"\n            QFrame {{\n                background-color: {COLORS['bg_surface_2']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['large']}px;\n            }}\n        "
    )

def character_placeholder() -> str:
    return (
        f"color: {COLORS['text_muted']}; font-size: 10px;"
    )

def emotion_pill(color) -> str:
    return (
        f"color: {color}; background-color: {COLORS['bg_surface_2']};border: 1px solid {color}; border-radius: {RADIUS['pill']}px; padding: 3px 8px;"
    )

def favor_bar(color) -> str:
    return (
        f"\n            QProgressBar {{\n                background-color: {COLORS['bg_surface_2']};\n                border: none;\n                border-radius: {RADIUS['xs']}px;\n            }}\n            QProgressBar::chunk {{\n                background-color: {color};\n                border-radius: {RADIUS['xs']}px;\n            }}\n        "
    )

def avatar_frame_border(border) -> str:
    return (
        f"\n                QFrame {{\n                    background-color: {COLORS['bg_surface_2']};\n                    border: {border};\n                    border-radius: {RADIUS['large']}px;\n                }}\n            "
    )

def history_locate_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent;\n                color: {COLORS['text_muted']};\n                border: none;\n                font-size: 12px;\n                padding: 0px;\n            }}\n            QPushButton:hover {{\n                color: {COLORS['accent']};\n            }}\n        "
    )

def history_detail(sender_color) -> str:
    return (
        f"\n            QLabel {{\n                color: {COLORS['text_secondary']};\n                background-color: {SURFACE_TINT['detail']};\n                border-left: 2px solid {sender_color};\n                border-radius: {RADIUS['xs']}px;\n                padding: 8px 10px;\n                margin-top: 4px;\n            }}\n        "
    )

def history_item_expanded(sender_color) -> str:
    return (
        f"\n                QFrame#history_item {{\n                    background-color: {SURFACE_TINT['active']};\n                    border-left: 2px solid {sender_color};\n                    border-radius: {RADIUS['sm2']}px;\n                }}\n            "
    )

def history_item_collapsed(sender_color) -> str:
    return (
        f"\n                QFrame#history_item {{\n                    background-color: transparent;\n                    border-left: 2px solid {sender_color};\n                    border-radius: {RADIUS['sm2']}px;\n                }}\n                QFrame#history_item:hover {{\n                    background-color: {SURFACE_TINT['hover']};\n                }}\n            "
    )

def history_card() -> str:
    return (
        f"\n            QFrame#history_card {{\n                background-color: {COLORS['bg_surface_2']};\n                border: 1px solid {ELEVATION['card_border']};\n                border-top: 1px solid {ELEVATION['glow_top']};\n                border-radius: {RADIUS['large']}px;\n            }}\n        "
    )

def history_header_sep() -> str:
    return (
        f"border-bottom: 1px solid {COLORS['border_subtle']};"
    )

def history_close_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent;\n                color: {COLORS['text_muted']};\n                border: none;\n                font-size: 14px;\n            }}\n            QPushButton:hover {{\n                color: {COLORS['text_primary']};\n            }}\n        "
    )

def history_search_box() -> str:
    return (
        f"\n            QLineEdit {{\n                background-color: {SURFACE_TINT['input']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['medium']}px;\n                padding: 4px 10px;\n            }}\n        "
    )

def empty_hint() -> str:
    return (
        f"color: {COLORS['text_muted']}; padding: 40px;"
    )

def header_shell() -> str:
    # SPEC-29 G1：必须带作用域选择器——裸声明会被 Qt 级联给**每个子控件**（历史上「长框里套一堆小框」的根因）
    return (
        f"QFrame#app_header {{ background-color: {COLORS['shell_header']}; border: 1px solid {COLORS['border_subtle']}; border-radius: 18px; }}"
    )

def twin_mode_chip() -> str:
    # SPEC-29 G2（审计 F29-5 写死口径）：纯文字 + text_secondary；无底色/无描边/无圆角；与氛围行同档、无分隔符
    return (
        f"color: {COLORS['text_secondary']}; background: transparent; border: none; padding: 0 6px;"
    )

def ambient_label() -> str:
    return (
        f"color: {COLORS['text_secondary']}; padding-right: 6px;"
    )

def search_box() -> str:
    return (
        f"\n            QLineEdit {{\n                background-color: {SURFACE_TINT['input']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['small']}px;\n                padding: 2px 8px;\n            }}\n        "
    )

def search_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent;\n                color: {COLORS['text_secondary']};\n                border: none;\n                font-size: 14px;\n            }}\n            QPushButton:hover {{\n                color: {COLORS['accent']};\n            }}\n        "
    )

def history_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent;\n                color: {COLORS['text_secondary']};\n                border: none;\n                padding: 0 6px;\n            }}\n            QPushButton:hover {{\n                color: {COLORS['accent']};\n            }}\n        "
    )

def book_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent;\n                color: {COLORS['text_secondary']};\n                border: none;\n                padding: 0 6px;\n            }}\n            QPushButton:hover {{\n                color: {COLORS['accent']};\n            }}\n        "
    )

def side_nav_shell() -> str:
    return (
        f"QFrame#side_nav {{ background: {COLORS['shell_nav']}; border: 1px solid {COLORS['border_subtle']}; border-radius: 18px; }}"
    )

def nav_weather_chip() -> str:
    return (
        f"background: {COLORS['chip_bg_soft']}; color: {COLORS['text_secondary']};border: 1px solid {COLORS['hairline_blue']}; border-radius: 12px;padding: 8px 6px;"
    )

def nav_sep() -> str:
    return (
        f"background: {COLORS['border_subtle']}; border: none;"
    )

def nav_section_hint() -> str:
    return (
        f"color: {COLORS['text_muted']}; padding: 2px 0 6px 0;"
    )

def nav_twins_slot() -> str:
    return (
        f"background: {COLORS['portrait_slot']}; border-radius: 14px;"
    )

def chat_scroll_area() -> str:
    return (
        f"QScrollArea {{ background: {SURFACE_TINT['chat_surface']}; border: 1px solid {SURFACE_TINT['chat_border']}; border-radius: 22px; }}"
    )

def input_frame() -> str:
    # SPEC-29 G1：同 header_shell——加作用域，防级联到输入区内部各控件
    return (
        f"QFrame#input_frame {{ background: {SURFACE_TINT['chat_surface_strong']}; border: 1px solid {COLORS['chat_border_pink']}; border-radius: 18px; }}"
    )

def quote_bar() -> str:
    # SPEC-29：作用域化（左彩条是引用条的设计语言，保留；只去掉「级联给内部 label」的副作用）
    return (
        f"QFrame#quote_bar {{ background-color: {COLORS['accent_veil']}; border-left: 3px solid {COLORS['accent_border']}; border-radius: 4px; }}"
    )

def quote_label() -> str:
    return (
        f"color: {COLORS['text_secondary']}; background: transparent;"
    )

def quote_close_btn() -> str:
    return (
        f"\n            QPushButton {{\n                background-color: transparent; color: {COLORS['text_muted']};\n                border: none; font-size: 14px; border-radius: 10px;\n            }}\n            QPushButton:hover {{ color: {COLORS['accent']}; background-color: {SURFACE_TINT['input']}; }}\n        "
    )

def quick_action_btn() -> str:
    return (
        f"\n                QPushButton {{\n                    background-color: {COLORS['bg_surface_2']};\n                    color: {COLORS['text_secondary']};\n                    border: 1px solid {COLORS['border_subtle']};\n                    border-radius: {RADIUS['small']}px;\n                    padding: 2px 10px;\n                }}\n                QPushButton:hover {{\n                    background-color: {SURFACE_TINT['input']};\n                    color: {COLORS['text_primary']};\n                }}\n            "
    )

def input_box() -> str:
    return (
        f"QTextEdit {{ background: {SURFACE_TINT['input_light']}; color: {COLORS['text_primary']}; border: none; border-radius: 12px; padding: 7px 10px; }}"
    )

def send_btn_base() -> str:
    """SPEC-32 F3：发送按钮改**暗沉玻璃**（原样式继承 `app_shell()` 的 `QPushButton{accent}` 金铜色，用户反馈太醒目）。

    必须**带 #send_btn 作用域**：id 选择器优先级高于 `app_shell()` 的类型选择器，
    否则 hover/pressed/disabled 仍会漏出 accent 系的亮色。
    """
    return (
        f"QPushButton#send_btn {{"
        f" background: {SURFACE_TINT['input_light']};"
        f" color: {COLORS['text_secondary']};"
        f" border: 1px solid {COLORS['border_subtle']};"
        f" border-radius: 12px; }}"
        f"QPushButton#send_btn:hover {{"
        f" background: {SURFACE_TINT['chat_surface_strong']};"
        f" color: {COLORS['text_primary']};"
        f" border: 1px solid rgba(179,211,239,0.30); }}"
        f"QPushButton#send_btn:pressed {{"
        f" background: rgba(12,17,30,0.92); padding-top: 1px; }}"
        f"QPushButton#send_btn:disabled {{"
        f" background: {COLORS['btn_disabled_bg']}; color: {COLORS['btn_disabled_fg']}; }}"
    )

def dock() -> str:
    # SPEC-29 G1
    return (
        f"QFrame#app_dock {{ background: {COLORS['shell_dock']}; border: 1px solid {COLORS['dock_border']}; border-radius: 17px; }}"
    )

def footer() -> str:
    # SPEC-29 G1
    return (
        f"QFrame#app_footer {{ background: {COLORS['shell_footer']}; border-radius: 10px; }}"
    )

def app_shell(backdrop_url) -> str:
    return (
        f"\n            QWidget#app_shell {{\n                border-image: url({backdrop_url}) 0 0 0 0 stretch stretch;\n            }}\n            QMainWindow {{\n                background-color: {COLORS['bg_base']};\n            }}\n            QScrollArea {{\n                border: none;\n                background-color: transparent;\n            }}\n            QTextEdit {{\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['medium']}px;\n                padding: 8px 10px;\n                background-color: {COLORS['input']};\n                color: {COLORS['text_primary']};\n            }}\n            QPushButton {{\n                background-color: {COLORS['accent']};\n                color: white;\n                border: none;\n                border-radius: {RADIUS['small']}px;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['accent_hover']};\n            }}\n            QPushButton:pressed {{\n                background-color: {COLORS['accent_press']};\n            }}\n            QPushButton:disabled {{\n                background-color: {COLORS['btn_disabled_bg']};\n                color: {COLORS['btn_disabled_fg']};\n            }}\n        "
    )

def nav_btn_dock() -> str:
    return (
        f"QPushButton {{ background: transparent; color: {COLORS['dock_fg']}; border: none; padding: 2px 9px; }} QPushButton:hover {{ background: {SURFACE_TINT['hover_dock']}; border-radius: 12px; }}"
    )

def nav_btn_dock_active() -> str:
    return (
        f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {COLORS['nav_grad_from']},stop:1 {COLORS['nav_grad_to']}); color: white; border: 1px solid {COLORS['nav_active_border']}; border-radius: 12px; text-align: left; padding-left: 14px; }} QPushButton:hover {{ background: {COLORS['nav_active_hover']}; }}"
    )

def nav_btn_side() -> str:
    return (
        f"QPushButton {{ background: transparent; color: {COLORS['nav_fg']}; border: none; border-radius: 12px; text-align: left; padding-left: 14px; }} QPushButton:hover {{ background: {SURFACE_TINT['hover_nav']}; color: white; }}"
    )

# SPEC-32 追加：`input_box_highlight()` / `input_box_normal()` 已删除——
# 它们只被 `eventFilter` 的聚焦换样式分支使用；该分支因「聚焦时边框闪光」被移除（用户真机反馈），
# 输入框外观统一由 `input_box()` 单一来源负责。

def locate_highlight(selector: str = "QLabel") -> str:
    """SPEC-32 F2：定位**不再做视觉突出**（用户真机反馈：闪光「异常发亮」）。

    历史到 SPEC-23：该函数返回一个亮琥珀底色（`rgba(255,205,96,0.55)`）追加到气泡 label 上，
    实现「定位闪光」。用户 2026-10-10 反馈不想要这种突出 ⇒ 返回空串；
    调用方（`ui/mixins/history.py::_locate_message`）已有空判 ⇒ 整条闪光链路自然成为 no-op，
    滚动定位与句级柔和高亮（SPEC-20）保持不变。
    如需恢复：把返回值改回 `f"{selector} {{ background-color: {COLORS['locate_highlight']}; }}"`。
    """
    return ""

def dash_title_label() -> str:
    """SPEC-27 R2：侧栏标题「双子 · 陪伴状态」。"""
    return f"color: {COLORS['text_secondary']}; background: transparent;"


def dash_collapse_btn() -> str:
    """SPEC-27 R2：折叠/展开小按钮（扁平、无边框、悬停微亮）。"""
    return (
        f"QPushButton {{ background: transparent; color: {COLORS['text_muted']};"
        f" border: none; padding: 2px 6px; }}"
        f"QPushButton:hover {{ color: {COLORS['text_primary']};"
        f" background: {SURFACE_TINT['hover']}; border-radius: {RADIUS['sm2']}px; }}"
    )


def dash_folded_strip() -> str:
    """SPEC-27 R1/§7.5：折叠条（复用 SPEC-26 体系：detail 底 + subtle 边 + radius.medium）。"""
    return (
        f"\n            QWidget#dash_folded_strip {{\n"
        f"                background-color: {SURFACE_TINT['detail']};\n"
        f"                border: 1px solid {COLORS['border_subtle']};\n"
        f"                border-radius: {RADIUS['medium']}px;\n"
        f"            }}\n        "
    )


def dash_folded_name(accent: str) -> str:
    """SPEC-27：折叠条里的角色名首字。"""
    return f"color: {accent}; background: transparent;"


def dash_favor_bar(accent: str) -> str:
    """SPEC-26 D4：好感细进度条（弱化呈现，不再当 KPI 显示）。"""
    return (
        f"\n            QProgressBar {{\n"
        f"                background-color: {SURFACE_TINT['input']};\n"
        f"                border: none;\n"
        f"                border-radius: 3px;\n"
        f"            }}\n"
        f"            QProgressBar::chunk {{\n"
        f"                background-color: {accent};\n"
        f"                border-radius: 3px;\n"
        f"            }}\n        "
    )


def dash_sprite_frame(role: str) -> str:
    """SPEC-27 R4：立绘直接嵌卡片，**不再单独描边**（底色 = 卡片底色，供底部渐隐衔接）。"""
    return (
        f"\n            QLabel#dash_sprite_{role} {{\n"
        f"                background-color: {COLORS['bg_surface']};\n"
        f"                border: none;\n"
        f"                border-radius: {RADIUS['medium']}px;\n"
        f"            }}\n        "
    )

def card_frame(role, border) -> str:
    """SPEC-27 R4/R6：卡片 = 唯一表面（去掉顶光边）；hover 轻微提亮。"""
    return (
        f"\n            QFrame#dash_card_{role} {{\n"
        f"                background-color: {COLORS['bg_surface']};\n"
        f"                border: 1px solid {border};\n"
        f"                border-radius: {RADIUS['medium']}px;\n"
        f"            }}\n"
        f"            QFrame#dash_card_{role}:hover {{\n"
        f"                background-color: {SURFACE_TINT['active']};\n"
        f"            }}\n        "
    )

def dashboard_frame() -> str:
    """SPEC-27 R4：外壳只留底色，去描边（减少嵌套边框第一层）。"""
    return (
        f"\n            QFrame#character_dashboard {{\n                background-color: {SURFACE_TINT['detail']};\n                border: none;\n                border-radius: {RADIUS['large']}px;\n            }}\n        "
    )

__all__ = [
    "history_card",
    "ambient_label",
    "avatar_frame_border",
    "history_close_btn",
    "bubble_tag_role",
    "character_placeholder",
    "nav_btn_side",
    "bubble_body",
    "history_header_sep",
    "emotion_pill",
    "history_detail",
    "system_label",
    "nav_twins_slot",
    "quick_action_btn",
    "history_search_box",
    "dash_sprite_frame",
    "dash_favor_bar",
    "dash_title_label",
    "dash_collapse_btn",
    "dash_folded_strip",
    "dash_folded_name",
    "history_locate_btn",
    "nav_btn_dock_active",
    "quote_bar",
    "quote_label",
    "bubble_tag_muted",
    "nav_section_hint",
    "nav_btn_dock",
    "avatar_label_base",
    "nav_sep",
    "card_frame",
    "quote_close_btn",
    "send_btn_base",
    "search_btn",
    "dock",
    "empty_hint",
    "nav_weather_chip",
    "side_nav_shell",
    "input_frame",
    "character_avatar_frame",
    "search_box",
    "input_box",
    "app_shell",
    "transparent_bg",
    "history_item_expanded",
    "history_item_collapsed",
    "twin_mode_chip",
    "color_only",
    "character_panel_frame",
    "history_btn",
    "chat_scroll_area",
    "favor_bar",
    "transparent_bg_color",
    "header_shell",
    "dashboard_frame",
    "footer",
    "book_btn",
    "locate_highlight",
]
