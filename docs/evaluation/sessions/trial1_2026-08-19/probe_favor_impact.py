# -*- coding: utf-8 -*-
"""量化 S 级问题影响面：ResponseLibrary 好感档位降级。"""
import sys
sys.path.insert(0, r"C:\Users\11985\.qclaw\workspace\rezero_twin")

from shared.state import FavorLevel as FL, StoryArc
from shared.prompts import ResponseLibrary


def level_of(f: int) -> FL:
    if f >= 95:
        return FL.BELOVED
    if f >= 80:
        return FL.DEAR
    if f >= 50:
        return FL.CLOSE
    if f >= 20:
        return FL.FAMILIAR
    return FL.STRANGER


lib = ResponseLibrary()
print("=== 各好感档位下 accompany 桶实际返回（宅邸篇） ===")
for f in [0, 15, 30, 60, 85, 100]:
    lv = level_of(f)
    print(f"favor={f:>3} level={lv.name:<8} -> {lib.get(StoryArc.MANSION_ERA, 'accompany', lv)}")

print()
print("=== 全部 arc × intent 桶的档位覆盖（缺 STRANGER 即新用户全命中 fallback） ===")
for arc_name, arc in [("MANSION", StoryArc.MANSION_ERA),
                      ("EMPIRE", StoryArc.EMPIRE_ERA),
                      ("LATE", StoryArc.LATE_ARC)]:
    g = lib.libs[arc]
    missing = []
    for key, bucket in g.items():
        levels = [lv.name for lv in bucket]
        if "STRANGER" not in levels:
            missing.append(f"{key}(min={min(lv.value for lv in bucket)})")
    print(f"{arc_name}: {len(missing)}/{len(g)} 桶缺 STRANGER -> {missing}")
