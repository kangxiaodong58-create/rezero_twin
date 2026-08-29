"""V16 表现层 M_A 测试：DESIGN_SYSTEM_V2 token 组 + 截图基线工具。

覆盖：
- V2 四组 token 存在且零 Qt 依赖；玻璃五档分序；MOTION 黄金带
- ELEVATION 已被浮层消费（memory_book 卡片含内发光顶边）
- 气泡行高走 TYPE token（155%，宪法 §二）
- 截图基线：采集/自对比零差异/篡改检出
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

import design_tokens  # noqa: E402


def test_v2_token_groups():
    m, t, e, s = (design_tokens.MOTION, design_tokens.TYPE,
                  design_tokens.ELEVATION, design_tokens.SURFACE)
    assert 100 <= m["fast"] <= 200 and m["base"] == 220 and m["slow"] <= 400, \
        "时长必须落在黄金带"
    assert m["enter_curve"] == "OutCubic" and m["spring_curve"] == "OutBack"
    assert t["lh_body_pct"] == 155 and t["lh_title_pct"] == 120
    assert e["glow_top"].startswith("rgba(255,255,255,0.0")
    tiers = [s[f"glass_{k}"] for k in (15, 35, 45, 55, 60)]
    assert all(tier.startswith("rgba(18,19,25,") for tier in tiers), "玻璃档同源同色相"


def test_elevation_consumed_by_memory_book(tmp_path):
    from PySide6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])
    import memory_book
    overlay = memory_book.MemoryBookOverlay(parent=None, conv_store=None)
    assert design_tokens.ELEVATION["glow_top"] in overlay._card.styleSheet(), \
        "浮层卡片应消费内发光顶边 token"


def test_bubble_line_height_uses_type_token(tmp_path):
    from PySide6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])
    import gui
    bubble = gui.BubbleWidget("第一行\n第二行", "rem")
    label = bubble.findChild(gui.QLabel)
    assert label is not None
    html = label.text()
    assert f'line-height:{design_tokens.TYPE["lh_body_pct"]}%' in html, \
        "多行气泡行高应来自 TYPE token"


def test_screenshot_capture_and_compare(tmp_path):
    import tools.screenshot_baseline as sb

    base = str(tmp_path / "base")
    saved = sb.capture(base)
    assert len(saved) == 5
    for _name, path in saved:
        assert os.path.isfile(path) and os.path.getsize(path) > 500
    assert sb.compare(base) == 0, "同 token 同渲染应零差异"

    # 篡改检出：往基线图上糊一块黑
    from PySide6.QtGui import QImage, QPainter, QColor
    target = saved[0][1]
    img = QImage(target)
    painter = QPainter(img)
    painter.fillRect(0, 0, img.width() // 3, img.height() // 3, QColor(0, 0, 0))
    painter.end()
    img.save(target)
    assert sb.compare(base) >= 1, "篡改必须被截图对比检出"
