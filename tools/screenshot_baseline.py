"""截图基线（V16 表现层 M_A）：把"质感"变成可对比的像素证据。

DESIGN_SYSTEM_V2.md §六。两种用法：
    python tools/screenshot_baseline.py                 # 采集基线 → baselines/screenshots/
    python tools/screenshot_baseline.py --compare       # 重采并与基线逐像素对比

设计：
- **组件级确定性截图**（固定文本的气泡/回忆之书/系统卡）——时钟无关，
  同 token 同渲染应当逐像素一致；`--compare` 对每张输出差异像素比率
  （单通道容差 8，抗 AA 噪声），超过阈值（默认 2%）退出码 1。
- 整窗截图含时段/天气等时钟内容，方差大，仅 --full 时附加采集（不参与 diff）。
- offscreen 渲染，零 API；QImage 对比，无 PIL 依赖。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QFont, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402

BASE_DIR = os.path.join(PROJECT_ROOT, "docs", "evaluation", "baselines", "screenshots")
DEFAULT_TOLERANCE = 0.02


def _ensure_app():
    app = QApplication.instance() or QApplication([])
    return app


def _demo_bubble(role: str, text: str):
    from gui import BubbleWidget
    return BubbleWidget(text, role)


def _demo_system_card():
    from gui import SystemLabelWidget
    return SystemLabelWidget(
        "━━  ✦  ━━\n今天的雨，很适合泡一杯热茶呢。\n━━  ✦  ━━",
        force_center=True, variant="vignette")


def _demo_memory_book(tmp_life, tmp_album):
    from datetime import date
    import memory_book
    from shared.life_ledger import LifeLedger
    ledger = LifeLedger(tmp_life)
    ledger.append(ts="2026-01-01 08:00:00", kind="genesis", title="相识之日",
                  dedup_key="genesis")
    ledger.append(ts="2026-08-01 09:00:00", kind="loyalty_lock", title="忠诚锁定达成",
                  dedup_key="loyalty_lock")
    ledger.append(ts="2026-09-20 10:00:00", kind="letter", title="收到蕾姆的来信",
                  dedup_key="letter1")
    return memory_book.MemoryBookOverlay(
        parent=None, conv_store=None, ledger=ledger, genesis=date(2026, 1, 1),
        album_dir=tmp_album, today=date(2026, 9, 23))


def build_surfaces(tmp_root: str):
    """确定性截图面（时钟无关）。返回 [(name, widget, size_hint)]。"""
    os.makedirs(tmp_root, exist_ok=True)
    surfaces = [
        ("bubble_rem", _demo_bubble("rem", '客人大人，欢迎回来。蕾姆刚煮好了红茶，请趁热喝。')),
        ("bubble_ram", _demo_bubble("ram", '哼，围裙可不是给你准备的，别站在路中间碍事。')),
        ("bubble_multiline", _demo_bubble(
            "rem", '（轻轻放下茶杯）\n今天过得还顺利吗？\n如果累了的话，蕾姆在这里陪着您。')),
        ("system_vignette", _demo_system_card()),
        ("memory_book", _demo_memory_book(
            os.path.join(tmp_root, "life.db"), os.path.join(tmp_root, "album"))),
    ]
    for name, w in surfaces:
        w.setStyleSheet(w.styleSheet())  # 触发样式解析
    return surfaces


def capture(out_dir: str = BASE_DIR) -> list:
    """采集全部确定性面 → out_dir/<name>.png；返回 [(name, path)]。"""
    _ensure_app()
    os.makedirs(out_dir, exist_ok=True)
    tmp_root = os.path.join(out_dir, "_tmp")
    saved = []
    for name, widget in build_surfaces(tmp_root):
        widget.resize(widget.sizeHint().width() or 640, widget.sizeHint().height() or 120)
        pix = widget.grab()
        path = os.path.join(out_dir, f"{name}.png")
        pix.save(path)
        saved.append((name, path))
    print(f"✅ 采集 {len(saved)} 张基线 → {out_dir}")
    for name, path in saved:
        print(f"   · {name}.png")
    return saved


def _diff_ratio(a_path: str, b_path: str, tol: int = 8) -> float:
    """差异像素比率（单通道差 > tol 计为差异）；尺寸不一致返回 1.0。"""
    a = QImage(a_path).convertToFormat(QImage.Format_ARGB32)
    b = QImage(b_path).convertToFormat(QImage.Format_ARGB32)
    if a.size() != b.size() or a.isNull() or b.isNull():
        return 1.0
    total = a.width() * a.height()
    diff = 0
    for y in range(a.height()):
        sa = bytes(a.constScanLine(y))
        sb = bytes(b.constScanLine(y))
        for x in range(0, len(sa), 4):
            if abs(sa[x] - sb[x]) > tol or abs(sa[x + 1] - sb[x + 1]) > tol \
                    or abs(sa[x + 2] - sb[x + 2]) > tol:
                diff += 1
    return diff / total if total else 0.0


def compare(baseline_dir: str, threshold: float = DEFAULT_TOLERANCE) -> int:
    """重采并对比基线。返回超阈值张数（0=通过）。"""
    _ensure_app()
    tmp_root = os.path.join(baseline_dir, "_cmp_tmp")
    os.makedirs(tmp_root, exist_ok=True)
    exceeded = 0
    for name, widget in build_surfaces(tmp_root):
        fresh = os.path.join(tmp_root, f"{name}.png")
        widget.grab().save(fresh)
        base = os.path.join(baseline_dir, f"{name}.png")
        if not os.path.isfile(base):
            print(f"  ⚠ {name}: 基线缺失（先采集）")
            exceeded += 1
            continue
        ratio = _diff_ratio(base, fresh)
        mark = "✅" if ratio <= threshold else "❌"
        print(f"  {mark} {name}: diff {ratio:.2%}")
        if ratio > threshold:
            exceeded += 1
    print(f"{'✅ 截图基线一致' if exceeded == 0 else f'❌ {exceeded} 张超阈值 {threshold:.0%}'}")
    return exceeded


def main() -> int:
    parser = argparse.ArgumentParser(description="截图基线（DESIGN_SYSTEM_V2 §六）")
    parser.add_argument("--compare", action="store_true", help="与基线逐像素对比")
    parser.add_argument("--threshold", type=float, default=DEFAULT_TOLERANCE)
    args = parser.parse_args()
    if args.compare:
        return 1 if compare(BASE_DIR, args.threshold) else 0
    capture(BASE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
