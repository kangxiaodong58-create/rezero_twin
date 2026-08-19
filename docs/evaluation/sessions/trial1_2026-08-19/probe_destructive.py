# -*- coding: utf-8 -*-
"""Trial #1 - Phase 3 破坏测试（CLI local，隔离存档，零 API）。

主动攻击清单：
1. 异常输入：空串/纯空格/超长/emoji/乱码/HTML 注入
2. 边界操作：连发重复消息、快速切换 arc、recover 越界
3. 状态压力：好感刷到顶（锁定时攻击是否被豁免）、连续负面
4. 数据完整性：interact 后 status() 是否一致、engine 状态无 NaN
"""
import sys
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

import shared.config as cfg

tmp_dir = tempfile.mkdtemp(prefix="rezero_trial_dest_")
print(f"[trial] isolated data dir: {tmp_dir}")

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp_dir):
    from local import ReZeroTwinSystem
    from shared.state import StoryArc

    sys0 = ReZeroTwinSystem()
    failures = []

    def check(label, cond, detail=""):
        status = "PASS" if cond else "FAIL"
        if not cond:
            failures.append(label)
        print(f"[{status}] {label} {detail}")

    # ── 1. 异常输入 ──
    cases = [
        ("空串", ""),
        ("纯空格", "   "),
        ("超长(2000字)", "啊" * 2000),
        ("emoji", "😀🎉🔥"),
        ("乱码", "qwertyuiopasdfghjklzxcvbnm"),
        ("HTML注入", "<script>alert(1)</script>"),
        ("SQL注入", "' OR 1=1 --"),
        ("系统命令", "import os; os.system('dir')"),
    ]
    for name, text in cases:
        try:
            r = sys0.interact(text)
            ok = r is not None and len(r) > 0
            check(f"异常输入[{name}]", ok, f"-> {r[:30]}")
        except Exception as e:
            check(f"异常输入[{name}]", False, f"异常 {type(e).__name__}: {e}")

    # ── 2. 边界操作 ──
    try:
        sys0.set_arc(StoryArc.EMPIRE_ERA)
        r = sys0.interact("你是谁？")
        check("arc切换帝国", "疏离" in r or "蕾姆" in r or "不记得" in r, f"-> {r[:40]}")
    except Exception as e:
        check("arc切换帝国", False, f"异常 {e}")
    try:
        sys0.set_arc(StoryArc.LATE_ARC)
        sys0.interact("你好")
        check("arc切换后期", True)
    except Exception as e:
        check("arc切换后期", False, f"异常 {e}")
    try:
        sys0.set_arc(StoryArc.MANSION_ERA)
        r = sys0.recover(1.5)   # 越界 >1.0
        check("recover越界1.5", "想起来" in r or "蕾姆" in r, f"-> {r[:30]}")
        r2 = sys0.recover(-0.5)  # 越界 <0
        check("recover越界-0.5", r2 is not None and len(r2) > 0)
    except Exception as e:
        check("recover越界", False, f"异常 {e}")

    # ── 3. 状态压力：锁定后攻击是否豁免 ──
    sys1 = ReZeroTwinSystem()
    for _ in range(30):
        sys1.interact("蕾姆真棒，你是独一无二的。谢谢你。")
    favor_before = sys1.rem.engine.favor
    locked_before = sys1.rem.engine.locked
    for _ in range(5):
        sys1.interact("滚开")
    favor_after = sys1.rem.engine.favor
    check("锁定后攻击豁免",
          favor_after >= max(90, favor_before - 8) or not locked_before,
          f"锁定={locked_before} favor {favor_before}->{favor_after}")

    # ── 4. 数据完整性 ──
    eng = sys1.rem.engine
    import math
    check("无NaN状态", all(not math.isnan(v) for v in [eng.favor, eng.independence, eng.recovery, eng.ram_favor]))
    check("状态范围", 0 <= eng.favor <= 100 and 0 <= eng.independence <= 1)
    s = sys1.status()
    check("status()可用", s is not None and len(s) > 10, f"-> {s[:40]}")

    print()
    if failures:
        print(f"破坏测试: {len(failures)} 项失败 -> {failures}")
    else:
        print("破坏测试: 全部通过 ✅")
