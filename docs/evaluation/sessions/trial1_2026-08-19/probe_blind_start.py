"""Trial Committee - Phase 1 盲测探针 v2：全新用户首启 GUI（offscreen 截图）。

隔离策略：patch get_data_dir → 临时目录，不碰项目 data/。
盲测纪律：不读 README/文档，仅以"第一次接触"视角打开软件。
v2：去掉 findChildren 遍历（离屏下疑似崩溃源），只截图 + 收集可见 widget 文本。
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

tmp_dir = tempfile.mkdtemp(prefix="rezero_trial_")
print(f"[trial] isolated data dir: {tmp_dir}", flush=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    import gui
    app = gui.QApplication(sys.argv)
    window = gui.TwinChatApp()
    window.resize(1360, 860)
    window.show()

    t0 = time.time()
    while time.time() - t0 < 1.2:
        app.processEvents()
        time.sleep(0.05)
    pix1 = window.grab()
    print("[trial] first_1s grabbed", flush=True)

    t0 = time.time()
    while time.time() - t0 < 8.0:
        app.processEvents()
        time.sleep(0.1)
    pix2 = window.grab()
    print("[trial] after_8s grabbed", flush=True)

    out_dir = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial1_2026-08-19")
    os.makedirs(out_dir, exist_ok=True)
    pix1.save(os.path.join(out_dir, "blind_first_1s.png"))
    pix2.save(os.path.join(out_dir, "blind_after_8s.png"))
    print("[trial] screenshots saved", flush=True)

    title = window.windowTitle()
    print("[trial] title bytes:", title.encode("utf-8", "replace")[:120], flush=True)
    print("[trial] done", flush=True)
