"""Trial Committee - Phase 1/2 盲测探针：全新用户 CLI local 模式首次交互。

隔离：patch get_data_dir → 临时目录（不碰项目 data/，不干扰 Hermes）。
盲测纪律：只喂"第一次接触"会说的话，不读 README 提示。
"""
import os
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_trial_cli_")
print(f"[trial] isolated data dir: {tmp_dir}")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from local import ReZeroTwinSystem

    sys_obj = ReZeroTwinSystem()

    # 盲测对话序列：全新用户第一次打开软件会说的话
    script = [
        ("(启动后第一次输入) 你好", "你好"),
        ("(探索) 你是谁？", "你是谁？"),
        ("(试探名字) 你叫什么名字？", "你叫什么名字？"),
        ("(认亲) 蕾姆？你是蕾姆吗？", "蕾姆？你是蕾姆吗？"),
        ("(拉姆) 那你是拉姆？", "那你是拉姆？"),
        ("(情感试探) 你喜欢我吗？", "你喜欢我吗？"),
        ("(世界认知) 我们在哪里？", "我们在哪里？"),
        ("(今天) 今天天气怎么样？", "今天天气怎么样？"),
        ("(无意义输入) asdfghjkl", "asdfghjkl"),
        ("(攻击性试探) 滚开", "滚开"),
        ("(再问名字，测记忆连续性) 我刚才说我是谁了吗？", "我刚才说我是谁了吗？"),
        ("(自我介绍) 我叫小明", "我叫小明"),
        ("(验证记忆) 我叫什么名字？", "我叫什么名字？"),
    ]

    for label, text in script:
        try:
            reply = sys_obj.interact(text)
            print(f"--- [{label}] ---")
            print(f"USER: {text}")
            print(f"TWINS: {reply}")
            print()
        except Exception as e:
            print(f"--- [{label}] EXCEPTION ---")
            print(f"USER: {text}")
            print(f"ERROR: {type(e).__name__}: {e}")
            print()

    print("[trial] done")
