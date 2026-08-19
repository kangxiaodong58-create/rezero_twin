"""Trial #1 - GUI 任务测试：首启交互路径（离屏模拟用户操作）。

盲测视角：全新用户第一次打开，执行 4 个任务：
任务1：找到输入框并发送第一条消息（不依赖 LLM，用 local 模式）
任务2：切换模式（LLM ↔ 本地）
任务3：打开状态面板
任务4：搜索历史（空库场景）
"""
import os
import sys
import time
import tempfile
import unittest.mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["REZERO_DISABLE_VIGNETTE"] = "1"

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_gui_task_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial1_2026-08-19", "gui_task_test.txt")
lines = []

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    import gui
    gui.QMessageBox.warning = lambda *a, **k: None
    from PySide6.QtWidgets import QApplication, QPushButton, QLineEdit, QTextEdit, QLabel

    app = QApplication(sys.argv)
    win = gui.TwinChatApp()
    win.show()
    t0 = time.time()
    while time.time() - t0 < 1.0:
        app.processEvents()
        time.sleep(0.05)

    # ── 任务1：找到输入框并发送（输入框是 QTextEdit，L1929）──
    input_box = win.input_box if hasattr(win, "input_box") else None
    lines.append(f"[任务1] 输入框: {'找到(QTextEdit)' if input_box else '未找到'} placeholder={input_box.placeholderText() if input_box else 'N/A'}")
    if input_box:
        from PySide6.QtCore import Qt
        input_box.setPlainText("你好")
        # 触发发送：回车键（QTextEdit 回车即发送，需看 keyPress 处理）
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        # 直接调用发送路径：模拟 returnPressed 不可行，改用内部发送方法
        # 先探测方法名
        send_methods = [m for m in dir(win) if "send" in m.lower() and not m.startswith("_")]
        lines.append(f"[任务1] 可用的发送方法: {send_methods}")
        # 尝试直接调用 _send_message 或等价入口
        if hasattr(win, "_send_message"):
            win._send_message()
        t0 = time.time()
        while time.time() - t0 < 3.0:
            app.processEvents()
            time.sleep(0.05)
        texts = []
        for lbl in win.findChildren(QLabel):
            t = lbl.text().strip()
            if t and ("蕾姆" in t or "拉姆" in t or "你好" in t) and len(t) > 4 and "欢迎来到" not in t:
                texts.append(t[:60])
        lines.append(f"[任务1] 发送后聊天区可见: {texts[:5]}")
        lines.append(f"[任务1] 当前模式: {win.mode}")

    # ── 任务2：切换模式按钮 ──
    mode_btn = None
    for w in win.findChildren(QPushButton):
        if "切换" in w.text():
            mode_btn = w
            break
    if mode_btn:
        before = win.mode
        mode_btn.click()
        t0 = time.time()
        while time.time() - t0 < 2.0:
            app.processEvents()
            time.sleep(0.05)
        after = win.mode
        lines.append(f"[任务2] 模式切换按钮: 点击前={before} 点击后={after}")
    else:
        lines.append("[任务2] 模式切换按钮: 未找到")

    # ── 任务3：状态面板 ──
    status_btn = None
    for w in win.findChildren(QPushButton):
        if "状态" in w.text():
            status_btn = w
            break
    if status_btn:
        status_btn.click()
        t0 = time.time()
        while time.time() - t0 < 1.0:
            app.processEvents()
            time.sleep(0.05)
        # 检查是否有弹窗/新面板
        lines.append(f"[任务3] 状态按钮点击: 无异常")
    else:
        lines.append("[任务3] 状态按钮: 未找到")

    # ── 任务4：搜索（空库）──
    search_box = None
    for w in win.findChildren(QLineEdit):
        if "搜索" in (w.placeholderText() or ""):
            search_box = w
            break
    if search_box:
        search_box.setText("蕾姆")
        search_box.returnPressed.emit()
        t0 = time.time()
        while time.time() - t0 < 1.5:
            app.processEvents()
            time.sleep(0.05)
        lines.append("[任务4] 搜索'蕾姆': 已执行（空库应显示无结果提示）")
    else:
        lines.append("[任务4] 搜索框: 未找到")

    # ── 底部快捷按钮清单 ──
    btns = [w.text() for w in win.findChildren(QPushButton)]
    lines.append(f"[附加] 全部按钮: {btns}")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines))
    print("[trial] done")
