"""资源 / 图标（项目根、精灵图、SVG 渲染、背景图）。"""

from __future__ import annotations

import os
import shutil
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QObject, QThread, QSize,
    QPropertyAnimation, QSequentialAnimationGroup, QAbstractAnimation, QEasingCurve,
)
from shared.config import load_env, get_data_dir
import sys


# V16 素材：SVG 显式渲染（EXE 内不赌 qsvg 图片插件）—— SPEC-22 S1a 自 gui.py 随 _svg_pixmap 归位
try:
    from PySide6.QtSvg import QSvgRenderer
    _SVG_OK = True
except Exception:  # pragma: no cover
    QSvgRenderer = None
    _SVG_OK = False


# 仓库根（SPEC-22 S1a 搬移修正：本文在 ui/ 子目录，故取**上一级**；
# 原 gui.py 里的同名值 = dirname(abspath(gui.py))，等价前提是这里的上一级）。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


_SPRITE_EXTS = ("png", "jpg", "jpeg", "webp")


def _asset_path(filename: str) -> str:
    """返回资产文件的绝对路径，兼容 frozen 与源码运行。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", _PROJECT_ROOT)
    else:
        base = _PROJECT_ROOT
    return os.path.join(base, "assets", filename)


def _svg_pixmap(filename: str, size: int, *, size_h: int = 0) -> QPixmap:
    """SVG → QPixmap（QSvgRenderer 显式渲染，不依赖 qsvg 图片插件——EXE 稳健）。

    2x 超采样抗锯齿；文件缺失/渲染失败返回空 QPixmap（调用端回退文字）。
    """
    if not _SVG_OK:
        return QPixmap()
    path = filename if os.path.isabs(filename) else _asset_path(filename)
    if not os.path.isfile(path):
        return QPixmap()
    try:
        renderer = QSvgRenderer(path)
        if not renderer.isValid():
            return QPixmap()
        w = size * 2
        h = (size_h or size) * 2
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        renderer.render(painter)
        painter.end()
        return pm
    except Exception:
        return QPixmap()


def _backdrop_image_url() -> str:
    """宅邸背景的 QSS 可用 URL。

    优先预渲染 PNG 缓存（data/backdrop_cache.png，随 SVG 更新再生）——
    QSS border-image 走图片插件，EXE 内插件缺失时 SVG 直引会静默空白；
    PNG 预渲染只依赖 QSvgRenderer（hiddenimports 显式收集），稳健。
    """
    svg = _asset_path("mansion_backdrop.svg")
    fallback = svg.replace(os.sep, "/")
    if not _SVG_OK or not os.path.isfile(svg):
        return fallback
    try:
        out = os.path.join(get_data_dir(), "backdrop_cache.png")
        if (not os.path.isfile(out)
                or os.path.getmtime(out) < os.path.getmtime(svg)):
            renderer = QSvgRenderer(svg)
            if not renderer.isValid():
                return fallback
            pm = QPixmap(1600, 1000)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            renderer.render(painter)
            painter.end()
            pm.save(out, "PNG")
        if os.path.isfile(out):
            return out.replace(os.sep, "/")
    except Exception:
        pass
    return fallback


def _theme_icon(filename: str) -> QIcon:
    """加载主题 SVG 图标（QSvgRenderer 显式渲染）；缺失时返回空图标，调用端仍保持文字可用。"""
    pm = _svg_pixmap(filename, 32)
    return QIcon(pm) if not pm.isNull() else QIcon()


def _user_sprite_path(data_dir: str, key: str) -> str:
    """用户自定义立绘路径：data/sprites/{key}.{ext}，存在即返回（文件即持久化）。"""
    sprite_dir = os.path.join(data_dir, "sprites")
    for ext in _SPRITE_EXTS:
        p = os.path.join(sprite_dir, f"{key}.{ext}")
        if os.path.isfile(p):
            return p
    return ""


def _copy_user_sprite(src: str, data_dir: str, key: str) -> str:
    """把拖入图片复制为 data/sprites/{key}.{ext}（清理旧扩展名），返回新路径。

    非图片扩展名返回空串；复制失败抛异常由调用方兜底。
    """
    import shutil
    ext = os.path.splitext(src)[1].lower().lstrip(".")
    if ext not in _SPRITE_EXTS:
        return ""
    sprite_dir = os.path.join(data_dir, "sprites")
    os.makedirs(sprite_dir, exist_ok=True)
    dst = os.path.join(sprite_dir, f"{key}.{ext}")
    for old_ext in _SPRITE_EXTS:
        old = os.path.join(sprite_dir, f"{key}.{old_ext}")
        if old != dst and os.path.isfile(old):
            try:
                os.remove(old)
            except Exception:
                pass
    shutil.copyfile(src, dst)
    return dst


def _resolve_sprite(data_dir: str, key: str, asset_path: str) -> str:
    """立绘解析优先级：用户自定义（data/sprites，持久化）> 内置 assets > 空（占位）。"""
    user = _user_sprite_path(data_dir, key)
    return user or asset_path

def sprite_card_pixmap(data_dir: str, key: str, width: int, height: int,
                       radius: int, fade_to: str) -> QPixmap:
    """SPEC-20260922-25 A：Dashboard 立绘卡片图。

    解析顺序与侧面板一致（用户自定义 data/sprites → 内置 assets，走 `_resolve_sprite`）；
    缩放填充 + 居中偏上裁切（保头）+ 圆角裁切 + 底部渐隐到卡片底色。失败返回空 QPixmap。
    """
    src = QPixmap(_resolve_sprite(data_dir, key, _asset_path(f"{key}_sprite.jpg")))
    if src.isNull():
        return QPixmap()
    scaled = src.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 3)   # 偏上取景：保住头部
    cropped = scaled.copy(x, y, width, height)

    out = QPixmap(width, height)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0.0, 0.0, float(width), float(height), float(radius), float(radius))
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, cropped)
    fade_h = max(1, int(height * 0.32))
    grad = QLinearGradient(0.0, float(height - fade_h), 0.0, float(height))
    top = QColor(fade_to)
    top.setAlpha(0)
    grad.setColorAt(0.0, top)
    grad.setColorAt(1.0, QColor(fade_to))
    painter.setPen(Qt.NoPen)
    painter.fillRect(0, height - fade_h, width, fade_h, grad)
    painter.end()
    return out
