# -*- coding: utf-8 -*-
"""Trial #1 回归验证（S-01/S-02/A-01 修复后）。

验收指标（用户 Step 2）：
- 盲测 13 轮：连续两次完全相同回复 = 0
- 连续 20 轮：重复率 < 10%（不同轮次相同句占比）
- 核心剧情（从零开始）100% 触发
- 关系成长：20 轮升温序列 favor 正常推进（> 修复前停滞值）
"""
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_trial_reg_")
print(f"[trial] isolated data dir: {tmp_dir}")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from local import ReZeroTwinSystem
    from shared.state import Intent, HardStateEngine, StoryArc

    # ── 1. 盲测 13 轮：连续重复检查 ──
    sys0 = ReZeroTwinSystem()
    blind = ["你好", "你是谁？", "你叫什么名字？", "蕾姆？你是蕾姆吗？",
             "那你是拉姆？", "你喜欢我吗？", "我们在哪里？", "今天天气怎么样？",
             "asdfghjkl", "滚开", "我刚才说我是谁了吗？", "我叫小明", "我叫什么名字？"]
    prev = None
    consec_dup = 0
    lines = []
    for t in blind:
        r = sys0.interact(t)
        rem = [l for l in r.split("\n") if "蕾姆" in l]
        line = rem[0] if rem else r
        lines.append(line)
        if line == prev:
            consec_dup += 1
        prev = line
    print(f"[1] 盲测 13 轮：连续重复 {consec_dup} 次（目标 0）")
    print(f"    不同句数 {len(set(lines))}/{len(lines)}")

    # ── 2. 核心剧情触发 ──
    eng = HardStateEngine(arc=StoryArc.MANSION_ERA)
    zero_ok = all(
        eng._classify_intent(t) == Intent.FROM_ZERO
        for t in ["从零开始吧", "从零开始……如果可以的话，我想和你一起。", "我想重新认识你"]
    )
    print(f"[2] 核心剧情（从零开始）触发: {'100% ✅' if zero_ok else '❌ 失败'}")

    # ── 3. 连续 20 轮：全局重复率 + 好感成长 ──
    sys1 = ReZeroTwinSystem()
    warm = [
        "你好", "早餐看起来很丰盛，辛苦你们了。", "今天有点累，但看到你们就安心很多。",
        "我叫小东，请多指教。", "今天天气怎么样？", "蕾姆，谢谢你一直这么认真地照顾我。",
        "能遇见你们，是我在这个世界最幸运的事之一。", "蕾姆，你不是任何人的替代品。你就是你。",
        "从零开始……如果可以的话，我想和你一起。", "拉姆，我会好好珍惜蕾姆的。这是我对你的承诺。",
        "今天宅邸有什么新鲜事吗？", "蕾姆今天心情怎么样？", "我有点担心明天的安排。",
        "你们平时都在做什么？", "蕾姆泡的茶最好喝了。", "拉姆的头发保养得真好。",
        "如果能一直这样下去就好了。", "蕾姆，你会一直陪着我吗？", "我好像越来越离不开你们了。",
        "谢谢你们，真的。",
    ]
    seen = []
    for t in warm:
        r = sys1.interact(t)
        rem = [l for l in r.split("\n") if "蕾姆" in l]
        seen.append(rem[0] if rem else r)
    total = len(seen)
    uniq = len(set(seen))
    dup_rate = (total - uniq) / total * 100
    favor_end = sys1.rem.engine.favor
    print(f"[3] 连续 20 轮：重复率 {dup_rate:.1f}%（目标 <10%，{total} 轮 {uniq} 句不同）")
    print(f"    好感成长: {favor_end}（修复前 27 停滞，目标 >40）")
    print(f"    拉姆好感: {sys1.ram._get_favor()}")
