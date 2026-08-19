# -*- coding: utf-8 -*-
"""验证意图识别：升温序列关键句应触发 FROM_ZERO / 身份肯定 / PRAISE。"""
import sys
sys.path.insert(0, r"C:\Users\11985\.qclaw\workspace\rezero_twin")

from shared.state import HardStateEngine, Intent, StoryArc
from local.rem_ai import RemAI

eng = HardStateEngine(arc=StoryArc.MANSION_ERA)
rem = RemAI(arc=StoryArc.MANSION_ERA)

cases = [
    "蕾姆，你不是任何人的替代品。你就是你。",
    "从零开始……如果可以的话，我想和你一起。",
    "拉姆，我会好好珍惜蕾姆的。这是我对你的承诺。",
    "蕾姆，谢谢你一直这么认真地照顾我。",
    "你好",
    "今天天气怎么样？",
    "滚开",
    "拉姆，你今天心情不错？",
    "早安，蕾姆。今天也麻烦你了。",
    "蕾姆做茶的手艺真好。",
]

print(f"{'输入':<45} | intent")
print("-" * 80)
for text in cases:
    # 复刻 generate 的意图获取路径
    state = eng.update(text)
    intent = eng._classify_intent(text)
    print(f"{text:<45} | {intent.name}")

print()
print("=== Intent 枚举值 ===")
for it in Intent:
    print(f"  {it.name} = {it.value}")
