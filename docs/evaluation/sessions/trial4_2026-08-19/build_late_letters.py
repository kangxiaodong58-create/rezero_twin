# -*- coding: utf-8 -*-
"""V14.8 ② 落地：letters.json 追加后期来信 15 条（文案组交付，原样）。"""
import json
import os

BASE = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
path = os.path.join(BASE, "content", "letters.json")

with open(path, "r", encoding="utf-8") as f:
    letters = json.load(f)

late_letters = [
    {"id": "late_rem_cross_01", "sender": "rem", "bucket": "CROSS_PERIOD", "conditions": {},
     "text": "刚从战场回来吗？蕾姆看到您还在，就放心了。下一阵号角响起时，请继续与蕾姆并肩。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_ram_cross_01", "sender": "ram", "bucket": "CROSS_PERIOD", "conditions": {},
     "text": "还没倒下就好。拉姆可不认为已经证明自己的人，会被这种战事轻易击垮。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_twins_cross_01", "sender": "twins", "bucket": "CROSS_PERIOD", "conditions": {},
     "text": "【蕾姆】战斗间隙也请记得喘口气，蕾姆会守住这里。\n【拉姆】别逞强，下一场还需要你站得住。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_half_day_01", "sender": "rem", "bucket": "HALF_DAY", "conditions": {},
     "text": "才离开了{hours_absent}小时，营地却安静了许多。您回来时，蕾姆会和您一起整理战线。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_ram_half_day_01", "sender": "ram", "bucket": "HALF_DAY", "conditions": {},
     "text": "只是离开半天而已，拉姆可没在等你。只是……你的那份位置，拉姆还留着。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_half_day_02", "sender": "rem", "bucket": "HALF_DAY", "conditions": {},
     "text": "{last_period}时您还在这里。到了{current_period}，蕾姆仍然记得与您并肩走过的路。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_days_01", "sender": "rem", "bucket": "DAYS_1_3", "conditions": {},
     "text": "已经{days_absent}天了。蕾姆相信您有必须去做的事，所以请放心前行，蕾姆会守住约定。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_ram_days_01", "sender": "ram", "bucket": "DAYS_1_3", "conditions": {},
     "text": "{days_absent}天不见，也算不上什么。既然你已经证明过自己，拉姆自然相信你会回来。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_twins_days_01", "sender": "twins", "bucket": "DAYS_1_3", "conditions": {},
     "text": "【蕾姆】这几天没有您的消息，蕾姆确实有些挂念。\n【拉姆】但比起担心，拉姆更相信那个能一路走到现在的你。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_days_3_7_01", "sender": "rem", "bucket": "DAYS_3_7", "conditions": {},
     "text": "已经{days_absent}天了。无论您现在身在何处，蕾姆都会把这份托付记在心里，等您归来。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_ram_days_3_7_01", "sender": "ram", "bucket": "DAYS_3_7", "conditions": {},
     "text": "这么久还没回来……看来你遇上的麻烦不小。别让拉姆等太久，活着回来就是你该尽的责任。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_days_3_7_02", "sender": "rem", "bucket": "DAYS_3_7", "conditions": {},
     "text": "这几日天气一直在变，战场也一样。可无论局势如何变化，蕾姆都会站在您身边。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_rem_long_01", "sender": "rem", "bucket": "LONG_ABSENCE", "conditions": {},
     "text": "已经{days_absent}天了。蕾姆等得很久，却从未想过放弃这份托付。您回来时，蕾姆仍会在这里。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_ram_long_01", "sender": "ram", "bucket": "LONG_ABSENCE", "conditions": {},
     "text": "消失这么久还知道回来，看来你确实没那么容易倒下。很好，拉姆认可这样的战友。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
    {"id": "late_twins_long_01", "sender": "twins", "bucket": "LONG_ABSENCE", "conditions": {},
     "text": "【蕾姆】不管过了多久，蕾姆都会记得与您并肩的约定。\n【拉姆】所以回来吧。你的位置，拉姆和蕾姆都没有忘。",
     "suppress_vignette": False, "arcs": ["late_arc"]},
]

# 检查 id 冲突（防重复）
existing_ids = {l["id"] for l in letters}
new_ids = [l["id"] for l in late_letters]
dup = [i for i in new_ids if i in existing_ids]
assert not dup, f"id 冲突: {dup}"

letters.extend(late_letters)
with open(path, "w", encoding="utf-8") as f:
    json.dump(letters, f, ensure_ascii=False, indent=2)

from collections import Counter
print("总数:", len(letters))
print("arcs:", dict(Counter(tuple(l.get("arcs", [])) for l in letters)))
late = [l for l in letters if l.get("arcs") == ["late_arc"]]
print("后期条数:", len(late))
print("后期桶分布:", dict(Counter(l["bucket"] for l in late)))
print("后期 sender:", dict(Counter(l["sender"] for l in late)))
