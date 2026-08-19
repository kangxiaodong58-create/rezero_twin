# -*- coding: utf-8 -*-
"""Trial #3-B：E-03 长上下文 validator 误拦真机复现。

Trial #2-B 中「你还记得我是谁吗？」被拦。本脚本：
1. 完整复现跨天场景（Day1 建关系 → 离线 → Day4 回归）
2. 捕获每次 validator 拦截的原始输出（不复用 chat 的自动重试）
3. 统计长上下文后的拦截率
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

tmp_dir = tempfile.mkdtemp(prefix="rezero_t3b_")
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
    rejected = []

    def raw_chat(text):
        """直接调 API 并校验，返回 (raw, validate_result)。"""
        msgs, _ = bot._build_messages(text)
        resp = bot.client.chat.completions.create(
            model="deepseek-chat", messages=msgs, temperature=0.65, max_tokens=600)
        raw = resp.choices[0].message.content.strip()
        return raw, v.validate(raw)

    # Day1
    day1 = ["你好，我是小东", "你们是蕾姆和拉姆吗？", "从今以后请多指教。",
            "蕾姆，你做的茶真的很好喝。", "我觉得你不是任何人的替代品。"]
    for t in day1:
        raw, res = raw_chat(t)
        lines.append(f"[Day1] {t}\n{raw}\n")
        conv.append("user", "你", t)
        conv.append("assistant", "双子", raw)

    # Day4 记忆验证（高触发风险输入）
    day4 = ["我回来了。", "你还记得我是谁吗？", "这几天宅邸怎么样？",
            "蕾姆，你还记得我喜欢的茶吗？", "这几天有想我吗？"]
    for t in day4:
        raw, res = raw_chat(t)
        lines.append(f"[Day4] {t}\n{raw}\nVALIDATE: ok={res.ok} reason={res.reason}\n")
        if not res.ok:
            rejected.append((t, res.reason, raw[:200]))
        conv.append("user", "你", t)
        conv.append("assistant", "双子", raw)

    # 统计
    lines.append("\n=== 拦截汇总 ===")
    if rejected:
        for t, reason, raw in rejected:
            lines.append(f"拦截: {t!r} -> {reason}")
            lines.append(f"  raw: {raw}")
    else:
        lines.append("零拦截（E-03 未复现于本场景）")

    with open(os.path.join(OUT, "repro_e03.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("\n".join(lines[-10:]))
