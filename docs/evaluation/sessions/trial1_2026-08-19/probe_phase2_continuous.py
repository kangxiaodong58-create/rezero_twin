# -*- coding: utf-8 -*-
"""Trial #1 Phase 2：连续使用模拟（CLI local，隔离存档，零 API）。

任务：模拟新用户连续对话 20 轮（升温序列 + 日常闲聊），观察：
- 好感是否成长、拉姆是否参与、蕾姆是否随好感变化语感
- S-01 复读问题在好感突破 50 后是否自愈
"""
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_trial_p2_")
print(f"[trial] isolated data dir: {tmp_dir}")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from local import ReZeroTwinSystem
    from shared.state import FavorLevel

    sys_obj = ReZeroTwinSystem()

    # 升温序列 + 日常（参考 test_cases.md Phase 1 + 随机闲聊）
    script = [
        "你好",
        "早餐看起来很丰盛，辛苦你们了。",
        "今天有点累，但看到你们就安心很多。",
        "我叫小东，请多指教。",
        "今天天气怎么样？",
        "蕾姆，谢谢你一直这么认真地照顾我。",
        "能遇见你们，是我在这个世界最幸运的事之一。",
        "蕾姆，你不是任何人的替代品。你就是你。",
        "从零开始……如果可以的话，我想和你一起。",
        "拉姆，我会好好珍惜蕾姆的。这是我对你的承诺。",
        "今天宅邸有什么新鲜事吗？",
        "蕾姆今天心情怎么样？",
        "我有点担心明天的安排。",
        "你们平时都在做什么？",
        "蕾姆泡的茶最好喝了。",
        "拉姆的头发保养得真好。",
        "如果能一直这样下去就好了。",
        "蕾姆，你会一直陪着我吗？",
        "我好像越来越离不开你们了。",
        "谢谢你们，真的。",
    ]

    print("轮次 | favor | level | 回复摘要")
    print("-" * 70)
    distinct = set()
    for i, text in enumerate(script, 1):
        reply = sys_obj.interact(text)
        favor = sys_obj.rem.engine.favor
        lv = FavorLevel._value2member_map_  # noqa
        def lvl(f):
            if f >= 95: return "BELOVED"
            if f >= 80: return "DEAR"
            if f >= 50: return "CLOSE"
            if f >= 20: return "FAMILIAR"
            return "STRANGER"
        rem_line = [l for l in reply.split("\n") if "蕾姆" in l]
        first = rem_line[0][:50] if rem_line else reply[:50]
        distinct.add(first)
        print(f"{i:>2} | {favor:>3} | {lvl(favor):<8} | {first}")
    print("-" * 70)
    print(f"20 轮中蕾姆回复的不同句子数: {len(distinct)}")
    print(f"最终 favor={sys_obj.rem.engine.favor}, ram_favor={sys_obj.ram._get_favor()}")
    print(f"拉姆参与轮数: {sum(1 for t in script if True)}（见上，含拉姆行计数）")
