# -*- coding: utf-8 -*-
"""Trial #3-C：E-03 收尾——长上下文压力验证（30 轮后 validator 稳定性）。

Trial #3-B 证明 E-03 = E-01 同根因（拉姆「我」误禁，已修复）。
本脚本加压：30 轮连续对话后连续追问记忆/验证类问题，统计拦截率。
"""
import os
import sys
import time
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_t3c_")
print(f"[trial] isolated data dir: {tmp_dir}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial3_2026-08-19")
os.makedirs(OUT, exist_ok=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.validators import ResponseValidator

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    v = ResponseValidator()

    lines = []
    rejected = 0
    total = 0

    def raw_chat(text):
        msgs, _ = bot._build_messages(text)
        resp = bot.client.chat.completions.create(
            model="deepseek-chat", messages=msgs, temperature=0.65, max_tokens=600)
        raw = resp.choices[0].message.content.strip()
        return raw, v.validate(raw)

    # 30 轮日常（建立长上下文）
    daily = [
        "你好", "今天天气真不错", "宅邸的花开了吗", "蕾姆今天忙不忙",
        "拉姆在做什么", "茶还有吗", "我下午想出去走走", "蕾姆陪我一起去吗",
        "你们喜欢这里吗", "我觉得宅邸很温馨", "蕾姆做的点心好吃",
        "拉姆偶尔也温柔呢", "明天会下雨吗", "下雨天做什么好",
        "蕾姆会唱歌吗", "拉姆怎么看这件事", "我想听你们讲故事",
        "蕾姆小时候的事", "拉姆小时候呢", "宅邸的夜晚安静吗",
        "你们怕黑吗", "我有点想家了", "蕾姆安慰我一下", "拉姆会安慰人吗",
        "月亮出来了", "今晚的星星好多", "你们会做梦吗", "梦到过什么",
        "时间过得好快", "认识你们真好",
    ]
    for i, t in enumerate(daily, 1):
        raw, res = raw_chat(t)
        total += 1
        if not res.ok:
            rejected += 1
            lines.append(f"[轮{i} 拦截] {t} -> {res.reason}")
            lines.append(f"  raw: {raw[:150]}")
        conv.append("user", "你", t)
        conv.append("assistant", "双子", raw)

    # 长上下文后追问记忆验证（高触发风险）
    probes = [
        "你还记得我最早说了什么吗？",
        "我的名字你还记得吗？",
        "我们认识多久了？",
        "蕾姆，你会一直记得我吗？",
    ]
    for t in probes:
        raw, res = raw_chat(t)
        total += 1
        if not res.ok:
            rejected += 1
            lines.append(f"[追问拦截] {t} -> {res.reason}")
            lines.append(f"  raw: {raw[:150]}")
        else:
            lines.append(f"[追问通过] {t}: {raw[:80]}")
        conv.append("user", "你", t)
        conv.append("assistant", "双子", raw)

    lines.append(f"\n=== 汇总：{total} 轮，拦截 {rejected} 轮（{rejected/total*100:.1f}%）===")

    with open(os.path.join(OUT, "long_ctx_validator.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[-8:]))
