# -*- coding: utf-8 -*-
"""盘点：SCENE_GUIDES 与 registry slot 分布。"""
import json
import re
import sys

sys.path.insert(0, r"C:\Users\11985\.qclaw\workspace\rezero_twin")

# 1. SCENE_GUIDES keys
with open(r"C:\Users\11985\.qclaw\workspace\rezero_twin\shared\prompts.py", encoding="utf-8") as f:
    src = f.read()
m = re.search(r"SCENE_GUIDES\s*=\s*\{(.*?)\n\s*\}", src, re.S)
keys = re.findall(r'^\s{8}"([a-z_]+)":', m.group(1), re.M) if m else []
print("SCENE_GUIDES keys:", keys)

# 2. registry slot 分布
with open(r"C:\Users\11985\.qclaw\workspace\rezero_twin\content\templates\registry.json", encoding="utf-8") as f:
    d = json.load(f)
from collections import Counter
c = Counter((it["arc"], it["slot"]) for it in d["items"])
print("\nregistry 分布:")
for k in sorted(c):
    print(f"  {k[0]:14} {k[1]:18} {c[k]}")
print(f"  总计 {len(d['items'])} 条")
