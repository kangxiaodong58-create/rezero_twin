"""角色侧栏面板——SPEC-22 S1b 自 gui.py 逐字归位。"""

from __future__ import annotations

import os
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QProgressBar
from design_tokens import COLORS, DIM, FONT_FAMILY, FONT_SIZE
from ui import theme
from ui.assets import _SPRITE_EXTS
from ui.logging_util import _log


class CharacterPanel(QFrame):
    """角色状态面板（V11.0：沉浸化信息分层）。

    布局：立绘 → 名字 → 放大表情 → 好感数字+简条 → 阶段引号弱化 → 条件标记。
    鬼化/残香不进面板术语，仅通过表情传达。
    V14.11：立绘区支持拖入 PNG/JPG/WEBP 替换（sprite_dropped 信号交由
    主窗口复制到 data/sprites/ 持久化），无图时保持 emoji 占位。
    """

    sprite_dropped = Signal(str)

    def __init__(self, name: str, emoji: str, color: str, sprite_path: str = "",
                 character_key: str = "", parent=None):
        super().__init__(parent)
        self._color = color
        self._speaking = False  # V12.0：说话态描边状态（幂等）
        self.character_key = character_key
        self._emoji = emoji
        self.setAcceptDrops(True)  # V14.11：立绘拖入
        self.setObjectName("character_panel")
        self.setFixedWidth(DIM['panel_w'])
        self.setStyleSheet(theme.character_panel_frame())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(8)

        # ── 立绘区域（不动）──
        self.avatar_frame = QFrame()
        self.avatar_frame.setFixedHeight(DIM['avatar_frame_h'])
        self.avatar_frame.setStyleSheet(theme.character_avatar_frame())
        avatar_inner = QVBoxLayout(self.avatar_frame)
        avatar_inner.setContentsMargins(4, 4, 4, 4)

        self.avatar_image = QLabel()
        self.avatar_image.setAlignment(Qt.AlignCenter)
        self.avatar_image.setScaledContents(False)
        self._placeholder_label: Optional[QLabel] = None

        if sprite_path and os.path.exists(sprite_path) and \
                not self._apply_pixmap(sprite_path):
            self._set_emoji_fallback()
        elif not sprite_path or not os.path.exists(sprite_path):
            self._set_emoji_fallback()
            self._placeholder_label = QLabel("立绘区域\n拖入 PNG 图片")
            self._placeholder_label.setAlignment(Qt.AlignCenter)
            self._placeholder_label.setStyleSheet(
                theme.character_placeholder())
            avatar_inner.addWidget(self._placeholder_label)

        avatar_inner.addWidget(self.avatar_image)
        layout.addWidget(self.avatar_frame)

        # ── ① 主信息：角色名 ──
        name_label = QLabel(name)
        name_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['title_lg'], QFont.Bold))
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setStyleSheet(theme.color_only(color))
        layout.addWidget(name_label)

        # ── ② 主信息：角色状态（用文本而非系统 emoji）──
        self.emotion_label = QLabel("心绪 · 平静")
        self.emotion_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small'], QFont.Bold))
        self.emotion_label.setAlignment(Qt.AlignCenter)
        self.emotion_label.setStyleSheet(
            theme.emotion_pill(color))
        layout.addWidget(self.emotion_label)

        # ── ③ 主信息：好感数字 + 简条 ──
        self.favor_label = QLabel("好感 --/100")
        self.favor_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body']))
        self.favor_label.setAlignment(Qt.AlignCenter)
        self.favor_label.setStyleSheet(theme.color_only(COLORS['text_secondary']))
        layout.addWidget(self.favor_label)

        self.favor_bar = QProgressBar()
        self.favor_bar.setRange(0, 100)
        self.favor_bar.setTextVisible(False)
        self.favor_bar.setFixedHeight(4)
        self.favor_bar.setStyleSheet(theme.favor_bar(color))
        layout.addWidget(self.favor_bar)

        # ── ④ 次信息：阶段引号弱化 ──
        self.stage_label = QLabel("「--」")
        self.stage_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small']))
        self.stage_label.setAlignment(Qt.AlignCenter)
        self.stage_label.setStyleSheet(theme.color_only(COLORS['text_muted']))
        layout.addWidget(self.stage_label)

        # ── ⑤ 条件标记：互斥（记忆模糊 > 锁定 > 独立）──
        self.mark_label = QLabel("")
        self.mark_label.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['small'], QFont.Bold))
        self.mark_label.setAlignment(Qt.AlignCenter)
        self.mark_label.setStyleSheet(theme.color_only(COLORS['accent']))
        layout.addWidget(self.mark_label)

        layout.addStretch()

    # ── V14.11：立绘替换与拖入 ──

    def _set_emoji_fallback(self) -> None:
        self.avatar_image.setText(self._emoji)
        self.avatar_image.setFont(QFont(FONT_FAMILY['emoji'], FONT_SIZE['display']))
        self.avatar_image.setAlignment(Qt.AlignCenter)

    def _apply_pixmap(self, path: str) -> bool:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return False
        scaled = pixmap.scaled(160, 230, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.avatar_image.setPixmap(scaled)
        if self._placeholder_label is not None:
            self._placeholder_label.hide()
        return True

    def set_sprite(self, path: str) -> bool:
        """替换立绘（拖入复制成功后调用）。路径无效或图片解码失败返回 False。"""
        if not path or not os.path.isfile(path):
            return False
        return self._apply_pixmap(path)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(_SPRITE_EXTS):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(_SPRITE_EXTS):
                self.sprite_dropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def update_state(self, favor: int, stage: str, emotion: str,
                     locked: bool = False, independence: float = 0.0,
                     recovery: float = 1.0) -> None:
        """更新面板状态。

        鬼化/残香仅通过 emotion 传达，不在此处显示术语。
        条件标记互斥优先级：记忆模糊 > 锁定 > 独立。
        """
        self.favor_label.setText(f"好感 {favor}/100")
        # V14.8 体验侧：距下一阶段提示（如「距亲密还差 5」）——提升成长期待感。
        # V14.8 排版修正：不拼进 favor_label 单行长串（视觉拥挤），改放 stage_label
        # 第二行弱化呈现（「「亲密」\n距亲密还差 5」）。
        stage_text = f"「{stage}」"
        try:
            from shared.state import HardStateEngine, FAVOR_LEVEL_CN, FavorLevel
            thresholds = HardStateEngine.FAVOR_THRESHOLDS
            next_lv, next_th = None, None
            for lv in FavorLevel:
                th = thresholds.get(lv)
                if th is not None and favor < th:
                    next_lv, next_th = lv, th
                    break
            if next_lv is not None and favor < 100:
                gap = next_th - favor
                cn = FAVOR_LEVEL_CN.get(next_lv.name, next_lv.name)
                stage_text = f"「{stage}」\n距{cn}还差 {gap}"
        except Exception:
            pass  # 提示失败不影响主显示
        self.favor_bar.setValue(favor)
        self.stage_label.setText(stage_text)
        mood_names = {
            "😰": "心绪 · 不安", "😡": "心绪 · 愠怒", "😠": "心绪 · 警觉",
            "😤": "心绪 · 坚定", "😵": "心绪 · 恍惚", "😟": "心绪 · 忧虑",
            "🥰": "心绪 · 依恋", "😌": "心绪 · 安然", "😍": "心绪 · 心动",
            "😐": "心绪 · 克制", "😊": "心绪 · 平静",
        }
        self.emotion_label.setText(mood_names.get(emotion, "心绪 · 平静"))

        # 互斥标记
        if recovery < 0.5:
            self.mark_label.setText("记忆模糊")
            self.mark_label.setStyleSheet(theme.color_only(COLORS['text_muted']))
        elif locked:
            self.mark_label.setText("忠诚锁定")
            self.mark_label.setStyleSheet(theme.color_only(COLORS['accent']))
        elif independence >= 0.6:
            self.mark_label.setText("独立人格")
            self.mark_label.setStyleSheet(theme.color_only(COLORS['accent']))
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
            self.avatar_frame.setStyleSheet(theme.avatar_frame_border(border))
        except Exception as e:
            _log(f"set_speaking 异常: {e}", durable=True)


