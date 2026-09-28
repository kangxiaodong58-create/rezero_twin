"""全屏覆盖层（樱花飘落）——SPEC-22 S1b 自 gui.py 逐字归位。"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget


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


