"""动效系统（V16 表现层 M_B）：MOTION token 的运行时消费层。

DESIGN_SYSTEM_V2.md §一（动效四律）与 §五（性能红线）的工程落点。
gui.py 的 ENABLE_UI_MOTION（V12.0 起）自此收敛到本模块统一判定。

红线（宪法 §一.5）：
- `QT_QPA_PLATFORM=offscreen` → 恒禁用（测试确定性）
- `REZERO_DISABLE_UI_MOTION=1` → 禁用（旧开关保持兼容）
- 流式 chunk 永远不动画（由调用侧保证：只对完成态消息调本模块）
- 所有入口在禁用态 = 立即呈现最终状态（零定时器、零 effect 残留）
"""

from __future__ import annotations

import os
from typing import List, Optional, Sequence

from design_tokens import MOTION


def enabled() -> bool:
    """动效总开关：token 开关 × 环境（offscreen 恒禁用）× 用户开关。"""
    if not MOTION.get("enabled", True):
        return False
    if os.environ.get("QT_QPA_PLATFORM", "") == "offscreen":
        return False
    if os.environ.get("REZERO_DISABLE_UI_MOTION", "") == "1":
        return False
    return True


def curve(name: str):
    from PySide6.QtCore import QEasingCurve
    mapping = {"enter": QEasingCurve.OutCubic, "spring": QEasingCurve.OutBack}
    return mapping.get(name, QEasingCurve.OutCubic)


def stagger_delays(count: int, *, step: Optional[int] = None,
                   cap: Optional[int] = None) -> List[int]:
    """级联延迟序列（纯函数）：前 cap 项 0/step/2*step…，其后全部停在 cap*step。

    宪法 §一.3：错落只属开头，列表不是瀑布也不是铁板。
    """
    step = MOTION["stagger_ms"] if step is None else step
    cap = MOTION["stagger_max"] if cap is None else cap
    if count <= 0 or step <= 0 or cap <= 0:
        return [0] * max(0, count)
    ceiling = (cap - 1) * step
    return [min(i, cap - 1) * step for i in range(count)]


def fade_in(widget, *, duration: Optional[int] = None, curve_name: Optional[str] = None,
            delay_ms: int = 0, dy: int = 0) -> None:
    """淡入（可选 8px 上浮）。禁用态 = 立即呈现最终状态。

    dy 仅用于几何稳定表面（浮层卡）；布局内 widget 传 0（resize 竞态防御，
    宪法红线：动画不得与布局引擎赛跑）。
    """
    if not enabled():
        return
    from PySide6.QtCore import QPoint, QPropertyAnimation, QTimer
    from PySide6.QtWidgets import QGraphicsOpacityEffect

    dur = MOTION["base"] if duration is None else duration
    name = MOTION["enter_curve"] if curve_name is None else curve_name

    def _run() -> None:
        try:
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            anim = QPropertyAnimation(effect, b"opacity", widget)
            anim.setDuration(dur)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(curve(name))
            anim.finished.connect(lambda: _safe_clear_effect(widget))
            anim.start(QPropertyAnimation.DeleteWhenStopped)
            if dy:
                origin = widget.pos()
                widget.move(origin.x(), origin.y() + dy)
                slide = QPropertyAnimation(widget, b"pos", widget)
                slide.setDuration(dur)
                slide.setStartValue(widget.pos())
                slide.setEndValue(origin)
                slide.setEasingCurve(curve(name))
                slide.start(QPropertyAnimation.DeleteWhenStopped)
        except Exception:
            _safe_clear_effect(widget)

    if delay_ms > 0:
        QTimer.singleShot(delay_ms, _run)
    else:
        _run()


def _safe_clear_effect(widget) -> None:
    """卸载 opacity effect（防离屏渲染残留；widget 可能已被删除）。"""
    try:
        widget.setGraphicsEffect(None)
    except Exception:
        pass


def fade_slide(card, *, dy: int = 12) -> None:
    """浮层卡片入场：fade + 上浮（slow 档）。几何固定表面专用。"""
    fade_in(card, duration=MOTION["slow"], curve_name="enter", dy=dy)


def stagger_reveal(list_widget, *, step: Optional[int] = None,
                   cap: Optional[int] = None) -> None:
    """列表行级联显形（QListWidget）：先全隐，前 cap 行步进显形，余量一次放开。"""
    if not enabled():
        return
    from PySide6.QtCore import QTimer
    n = list_widget.count()
    if n <= 0:
        return
    step = MOTION["stagger_ms"] if step is None else step
    cap = MOTION["stagger_max"] if cap is None else cap
    for i in range(n):
        list_widget.setRowHidden(i, True)
    shown = min(cap, n)
    for i in range(shown):
        QTimer.singleShot(i * step, lambda i=i: list_widget.setRowHidden(i, False))
    if n > shown:
        QTimer.singleShot(shown * step, lambda: [list_widget.setRowHidden(i, False)
                                                 for i in range(shown, n)])
