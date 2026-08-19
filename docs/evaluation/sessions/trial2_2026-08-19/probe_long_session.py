# -*- coding: utf-8 -*-
"""Trial #2-A：30+ 轮长会话深度测试（LLM 真机，预算封顶 ¥2）。

重点（用户强调：LLM 模式是体验主模式）：
- 连续 30 轮：响应时延漂移、重复模式、情感弧线完整性
- 分两段（段1 升温 16 轮 → 段2 日常+波折 16 轮），观察关系成长与记忆连续性
- 括号密度随测（B-03 回归）
"""
import os
import re
import sys
import time
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_t2a_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial2_2026-08-19")
os.makedirs(OUT, exist_ok=True)
out_path = os.path.join(OUT, "long_session.txt")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )

    # 段1：升温序列 16 轮
    seg1 = [
        "你好", "你们是谁？", "我叫小东，请多指教。", "今天天气怎么样？",
        "宅邸平时都做些什么？", "你们喜欢什么茶？", "我有点累了。",
        "蕾姆泡的茶真好喝。", "拉姆今天心情不错？", "能遇见你们真好。",
        "蕾姆，谢谢你一直照顾我。", "蕾姆，你不是任何人的替代品。",
        "从零开始……我想和你一起。", "拉姆，我会好好珍惜蕾姆的。",
        "你们是我在这个世界的牵挂。", "我好像越来越依赖你们了。",
    ]
    # 段2：日常+波折 16 轮
    seg2 = [
        "今天有什么新鲜事？", "蕾姆你在做什么？", "我工作有点不顺心。",
        "拉姆，你觉得我这个人怎么样？", "蕾姆，如果有一天我离开了呢？",
        "开玩笑的，我不会走的。", "蕾姆今天好可爱。", "拉姆也别太累了。",
        "明天想带你们去镇上走走。", "蕾姆，你会一直陪着我吗？",
        "我好像开始习惯有你们了。", "今天月色真美。", "蕾姆，晚安前再说说话吧。",
        "你觉得命运是什么？", "不管发生什么，我们都会在一起吧。",
        "谢谢你，真的。遇见你们是我最幸运的事。",
    ]

    lines = []
    stats = {"parens": 0, "rows": 0}
    latencies = []
    t_start = time.time()

    def run_segment(name, seg):
        lines.append(f"\n########## {name} ##########")
        for i, text in enumerate(seg, 1):
            t0 = time.time()
            try:
                reply = bot.chat(text)
                dt = time.time() - t0
                latencies.append(dt)
                parens = len(re.findall(r"（[^）]{2,}）", reply))
                nrows = len([l for l in reply.split("\n") if l.strip()])
                stats["parens"] += parens
                stats["rows"] += nrows
                lines.append(f"\n--- 段{name} 轮{i} [{dt:.1f}s] ---")
                lines.append(f"USER: {text}")
                lines.append(reply)
                print(f"[{dt:4.1f}s] {text[:14]:16} -> {reply[:36].replace(chr(10),' ')}")
            except Exception as e:
                lines.append(f"\n--- 段{name} 轮{i} ERROR ---")
                lines.append(f"USER: {text}")
                lines.append(f"ERR: {type(e).__name__}: {e}")
                print(f"[ERR] {text[:14]} -> {type(e).__name__}: {e}")
            conv.append("user", "你", text)
            conv.append("assistant", "双子", reply if 'reply' in dir() else "(错误)")

    run_segment(1, seg1)
    run_segment(2, seg2)

    total = time.time() - t_start
    avg = sum(latencies) / len(latencies) if latencies else 0
    max_lat = max(latencies) if latencies else 0
    parens_total, rows_total = stats["parens"], stats["rows"]
    lines.append("\n########## 统计 ##########")
    lines.append(f"总轮数: {len(seg1)+len(seg2)} | 总耗时 {total:.1f}s | 平均 {avg:.2f}s/轮 | 最慢 {max_lat:.1f}s")
    lines.append(f"括号密度: {parens_total} 处 / {rows_total} 行 = {parens_total/max(1,rows_total):.2f} 处/行（B-03 目标 <0.3）")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[saved] {out_path}")
    print(f"统计: {len(seg1)+len(seg2)} 轮 | 平均 {avg:.2f}s | 括号密度 {parens_total/max(1,rows_total):.2f}")
