# -*- coding: utf-8 -*-
"""V14.6 E-5：软 OOC 检查验证 v2——WARNING 不阻断。"""
import sys
sys.path.insert(0, r"C:\Users\11985\.qclaw\workspace\rezero_twin")

from shared.validators import ResponseValidator

v = ResponseValidator()

# 1. 网络污染（A 级）
r = v.validate('【蕾姆】: "哈哈哈哈，这也太绝了吧。蕾姆觉得超棒。"')
print("A级: ok=", r.ok, " warnings=", r.ooc_warnings)
assert r.ok and r.ooc_warnings and any("网络污染" in w for w in r.ooc_warnings)

# 2. 人格污染（C 级）
r2 = v.validate('【蕾姆】: "蕾姆永远属于你，主人只能喜欢蕾姆。"')
print("C级: ok=", r2.ok, " warnings=", r2.ooc_warnings)
assert r2.ok and r2.ooc_warnings and any("人格污染" in w for w in r2.ooc_warnings)

# 3. 世界观冲突（E 级）——不含硬词「用户」
r3 = v.validate('【拉姆】: "哼，这台服务器又宕机了，手机APP也打不开。"')
print("E级: ok=", r3.ok, " warnings=", r3.ooc_warnings)
assert r3.ok and r3.ooc_warnings and any("世界观冲突" in w for w in r3.ooc_warnings)

# 4. 干净回复零警告
r4 = v.validate('【蕾姆】: "如果这是您的愿望，蕾姆会尽力完成。"')
print("clean: ok=", r4.ok, " warnings=", r4.ooc_warnings)
assert r4.ok and not r4.ooc_warnings

# 5. 硬拦截仍工作
r5 = v.validate('【蕾姆】: "用户您说笑了。"')
print("hard: ok=", r5.ok, " reason=", r5.reason)
assert not r5.ok

print("\n软 OOC 检查验证通过 ✅")
