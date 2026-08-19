"""Trial #1 - GUI 首启测试（Hermes Step2-4 已提交后的稳定基线）。

盲测视角：全新用户第一次打开软件。
离屏启动（QT_QPA_PLATFORM=offscreen），隔离数据目录（不污染 data/）。
采集：窗口标题 / 首屏全部可见文本 / 控件清单 / 截图。
"""
import os
import sys
import time
import tempfile
import unittest.mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_gui_trial_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT_DIR = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial1_2026-08-19")
os.makedirs(OUT_DIR, exist_ok=True)
out_path = os.path.join(OUT_DIR, "gui_first_start.txt")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    import gui
    app = gui.QApplication(sys.argv)
    window = gui.TwinChatApp()
    window.resize(1360, 860)
    window.show()

    lines = []
    # 首启 1.2s：欢迎语/引导阶段
    t0 = time.time()
    while time.time() - t0 < 1.2:
        app.processEvents()
        time.sleep(0.05)
    lines.append("=== T+1.2s（首屏） ===")
    lines.append(f"窗口标题: {window.windowTitle()}")
    try:
        pix = window.grab()
        pix.save(os.path.join(OUT_DIR, "gui_first_1s.png"))
        lines.append("[截图已保存 gui_first_1s.png]")
    except Exception as e:
        lines.append(f"[截图失败: {e}]")

    # 首启 6s：引言/来信阶段（若有生成会在这段返回）
    t0 = time.time()
    while time.time() - t0 < 6.0:
        app.processEvents()
        time.sleep(0.1)
    lines.append("")
    lines.append("=== T+7s（引言后） ===")
    try:
        pix = window.grab()
        pix.save(os.path.join(OUT_DIR, "gui_after_7s.png"))
        lines.append("[截图已保存 gui_after_7s.png]")
    except Exception as e:
        lines.append(f"[截图失败: {e}]")

    # 采集全部可见文本（QLabel / QTextEdit / QPushButton / QLineEdit）
    from PySide6.QtWidgets import QLabel, QTextEdit, QPushButton, QLineEdit, QFrame
    lines.append("")
    lines.append("=== 首屏可见文本 ===")
    seen = set()
    for widget in window.findChildren(QFrame):
        for lbl in widget.findChildren(QLabel):
            t = lbl.text().strip()
            if t and t not in seen:
                seen.add(t)
                lines.append(f"[label] {t}")
    for box in window.findChildren(QTextEdit):
        t = box.toPlainText().strip()
        if t:
            lines.append(f"[textedit] {t[:200]}")
    for btn in window.findChildren(QPushButton):
        t = btn.text().strip()
        if t:
            lines.append(f"[button] {t}")
    for le in window.findChildren(QLineEdit):
        t = le.placeholderText().strip()
        if t:
            lines.append(f"[input-placeholder] {t}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[trial] saved {out_path}")
    print("\n".join(lines))
    print("[trial] done")
