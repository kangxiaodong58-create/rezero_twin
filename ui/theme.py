"""QSS 构造器（SPEC-20260922-18 / B6·A14 收口）。

- 只消费 `design_tokens`（**禁止裸色值/裸尺寸**——本批为值等价迁移，视觉零变化）；
- **零 Qt 依赖**（纯字符串构造 + f-string），可直接单测；
- 单一真源：`gui.py` / `status_dashboard.py` 的全部内联 QSS 都出自本模块；
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
        f"\n            QLineEdit {{\n                background-color: {SURFACE_TINT['input']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['medium']}px;\n                padding: 4px 10px;\n            }}\n            QLineEdit:focus {{\n                border-color: {COLORS['border_focus']};\n            }}\n        "
    )

def empty_hint() -> str:
    return (
        f"color: {COLORS['text_muted']}; padding: 40px;"
    )

def header_shell() -> str:
    return (
        f"background-color: {COLORS['shell_header']}; border: 1px solid {COLORS['border_subtle']}; border-radius: 18px;"
    )

def twin_mode_chip() -> str:
    return (
        f"background: {COLORS['chip_bg']}; color: {COLORS['twin_mode_fg']}; border: 1px solid {COLORS['chip_border']}; border-radius: 13px; padding: 8px 14px; font-weight: bold;"
    )

def ambient_label() -> str:
    return (
        f"color: {COLORS['text_secondary']}; padding-right: 6px;"
    )

def search_box() -> str:
    return (
        f"\n            QLineEdit {{\n                background-color: {SURFACE_TINT['input']};\n                color: {COLORS['text_primary']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['small']}px;\n                padding: 2px 8px;\n            }}\n            QLineEdit:focus {{\n                border-color: {COLORS['border_focus']};\n            }}\n        "
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
        f"QScrollArea {{ background: {SURFACE_TINT['chat_surface']}; border: 2px solid {SURFACE_TINT['chat_border']}; border-radius: 22px; }}"
    )

def input_frame() -> str:
    return (
        f"background: {SURFACE_TINT['chat_surface_strong']}; border: 1px solid {COLORS['chat_border_pink']}; border-radius: 18px;"
    )

def quote_bar() -> str:
    return (
        f"background-color: {COLORS['accent_veil']}; border-left: 3px solid {COLORS['accent_border']}; border-radius: 4px;"
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
        f"QTextEdit {{ background: {SURFACE_TINT['input_light']}; color: {COLORS['input_fg_dark']}; border: none; border-radius: 12px; padding: 7px 10px; }} QTextEdit:focus {{ border: 1px solid {COLORS['input_border_pink']}; }}"
    )

def send_btn_base() -> str:
    return (
        "QPushButton { border-radius: 12px; }"
            "QPushButton:pressed { padding-top: 1px; }"
    )

def dock() -> str:
    return (
        f"background: {COLORS['shell_dock']}; border: 1px solid {COLORS['dock_border']}; border-radius: 17px;"
    )

def footer() -> str:
    return (
        f"background: {COLORS['shell_footer']}; border-radius: 10px;"
    )

def app_shell(backdrop_url) -> str:
    return (
        f"\n            QWidget#app_shell {{\n                border-image: url({backdrop_url}) 0 0 0 0 stretch stretch;\n            }}\n            QMainWindow {{\n                background-color: {COLORS['bg_base']};\n            }}\n            QScrollArea {{\n                border: none;\n                background-color: transparent;\n            }}\n            QTextEdit {{\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['medium']}px;\n                padding: 8px 10px;\n                background-color: {COLORS['input']};\n                color: {COLORS['text_primary']};\n            }}\n            QTextEdit:focus {{\n                border-color: {COLORS['border_focus']};\n            }}\n            QPushButton {{\n                background-color: {COLORS['accent']};\n                color: white;\n                border: none;\n                border-radius: {RADIUS['small']}px;\n            }}\n            QPushButton:hover {{\n                background-color: {COLORS['accent_hover']};\n            }}\n            QPushButton:pressed {{\n                background-color: {COLORS['accent_press']};\n            }}\n            QPushButton:disabled {{\n                background-color: {COLORS['btn_disabled_bg']};\n                color: {COLORS['btn_disabled_fg']};\n            }}\n        "
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

def input_box_highlight() -> str:
    return (
        f"QTextEdit {{ border: 2px solid {COLORS['accent']}; border-radius: 10px; background-color: {COLORS['input']}; padding: 6px 10px; }}"
    )

def input_box_normal() -> str:
    return (
        f"QTextEdit {{ border: 1px solid {COLORS['border_subtle']}; border-radius: 10px; background-color: {COLORS['input']}; padding: 6px 10px; }}"
    )

def locate_highlight() -> str:
    return (
        f"background-color: {COLORS['locate_highlight']}; border-radius: {RADIUS['small']}px;"
    )

def card_avatar(accent) -> str:
    return (
        f"border-radius: 23px; border: 2px solid {accent};"
    )

def card_frame(role, border) -> str:
    return (
        f"\n            QFrame#dash_card_{role} {{\n                background-color: {COLORS['bg_surface']};\n                border: 1px solid {border};\n                border-top: 1px solid {ELEVATION['glow_top']};\n                border-radius: {RADIUS['medium']}px;\n            }}\n        "
    )

def dashboard_frame() -> str:
    return (
        f"\n            QFrame#character_dashboard {{\n                background-color: {SURFACE_TINT['detail']};\n                border: 1px solid {COLORS['border_subtle']};\n                border-radius: {RADIUS['large']}px;\n            }}\n        "
    )

__all__ = [
    "history_card",
    "ambient_label",
    "avatar_frame_border",
    "input_box_normal",
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
    "card_avatar",
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
    "input_box_highlight",
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
