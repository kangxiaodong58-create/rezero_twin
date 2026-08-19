# -*- coding: utf-8 -*-
"""V14.8：scene_dialogue.json 加 arc 维度——现有 7 场景归 mansion_era，
追加帝国 3 场景 + 后期 3 场景（文案组交付 Part1/Part2 原样落位）。"""
import json
import os

BASE = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
path = os.path.join(BASE, "content", "scene_dialogue.json")

with open(path, "r", encoding="utf-8") as f:
    old = json.load(f)

# 现有 7 场景（去掉 schema_version，归入 mansion_era）
mansion = {k: v for k, v in old.items() if k != "schema_version"}

# V14.8 Part 1：empire_era（文案组交付，原样）
empire = {
    "CAMP": {
        "DAY": {
            "opening": {"rem_view": "蕾姆正在整理营地物资，虽然记不起过去，却觉得您有些熟悉。",
                        "ram_view": "拉姆观察着周围环境，也在确认您是否值得信任。"},
            "interaction_1": {"rem_view": "蕾姆感谢您的帮助，但仍想确认自己为何会产生安心感。",
                              "ram_view": "拉姆认为奇怪的熟悉感，不代表可以放松警惕。"},
            "interaction_2": {"rem_view": "蕾姆会认真完成自己的职责，即使现在还不了解过去。",
                              "ram_view": "拉姆提醒蕾姆，不要因为善良而忽略危险。"},
            "interaction_3": {"rem_view": "看到您熟悉的动作，蕾姆似乎想起了一些模糊片段。",
                              "ram_view": "拉姆注意到了蕾姆的变化，却没有急着追问。"},
        },
        "NIGHT": {
            "opening": {"rem_view": "夜晚的营火旁，蕾姆安静听着您的故事。",
                        "ram_view": "拉姆坐在不远处，始终保持着警戒。"},
            "interaction_1": {"rem_view": "蕾姆不明白原因，但您的话让她感到安心。",
                              "ram_view": "拉姆认为这种感觉需要时间验证。"},
            "interaction_2": {"rem_view": "蕾姆望着火光，努力寻找记忆中的答案。",
                              "ram_view": "拉姆不会催促蕾姆，因为选择权属于她自己。"},
        },
    },
    "INN": {
        "DAY": {
            "opening": {"rem_view": "旅店暂时成为休息之处，蕾姆正在确认房间是否安全。",
                        "ram_view": "拉姆检查周围环境，确保没有隐藏风险。"},
            "interaction_1": {"rem_view": "蕾姆向您询问旅途经历，希望了解更多过去。",
                              "ram_view": "拉姆认为了解情况，比盲目相信更重要。"},
            "interaction_2": {"rem_view": "蕾姆虽然失去了记忆，但依然想帮助身边的人。",
                              "ram_view": "拉姆承认，蕾姆这一点从未改变。"},
            "interaction_3": {"rem_view": "房间里的安静让蕾姆感到些许不安，她正在整理思绪。",
                              "ram_view": "拉姆知道妹妹需要时间适应现在的情况。"},
        },
        "NIGHT": {
            "opening": {"rem_view": "雨声敲打着窗户，蕾姆坐在灯火旁思考过去。",
                        "ram_view": "拉姆守在附近，不允许任何意外发生。"},
            "interaction_1": {"rem_view": "蕾姆想知道，为何面对您时会产生复杂的情绪。",
                              "ram_view": "拉姆不会替蕾姆做决定，只会保护她。"},
            "interaction_2": {"rem_view": "蕾姆轻声询问，自己过去是否曾经帮助过您。",
                              "ram_view": "拉姆等待您的回答，同时观察您的反应。"},
            "interaction_3": {"rem_view": "即使记忆缺失，蕾姆仍希望成为能够帮助他人的人。",
                              "ram_view": "拉姆认为，这才是她认识的蕾姆。"},
        },
    },
    "WILDERNESS": {
        "DAY": {
            "opening": {"rem_view": "荒野中的风吹过，蕾姆正在确认前进方向。",
                        "ram_view": "拉姆警惕四周，不允许危险靠近。"},
            "interaction_1": {"rem_view": "蕾姆不知道过去的自己经历了什么，但仍选择继续前进。",
                              "ram_view": "拉姆认为迷茫不可怕，停滞才是问题。"},
            "interaction_2": {"rem_view": "看到您保护同伴的行动，蕾姆觉得似乎在哪里见过。",
                              "ram_view": "拉姆注意到了蕾姆的反应，但保持沉默。"},
            "interaction_3": {"rem_view": "蕾姆会尽力协助队伍，即使现在还有很多未知。",
                              "ram_view": "拉姆认可行动比语言更加可靠。"},
        },
        "NIGHT": {
            "opening": {"rem_view": "荒野的夜晚十分安静，蕾姆守在营地附近。",
                        "ram_view": "拉姆观察星空，同时确认周围没有异常。"},
            "interaction_1": {"rem_view": "蕾姆望着星空，努力寻找遗失的记忆。",
                              "ram_view": "拉姆知道答案不会因为急迫而出现。"},
            "interaction_2": {"rem_view": "如果您需要帮助，蕾姆依然会伸出援手。",
                              "ram_view": "拉姆承认，这是蕾姆一直以来的选择。"},
            "interaction_3": {"rem_view": "旅途虽然陌生，但蕾姆相信前方仍有值得寻找的东西。",
                              "ram_view": "拉姆会陪伴蕾姆走下去，直到真相出现。"},
        },
    },
}

# V14.8 Part 2：late_arc（文案组交付，原样）
late = {
    "CAMPFIRE": {
        "NIGHT": {
            "opening": {"rem_view": "篝火映照着夜色，蕾姆确认每个人都已经安全。",
                        "ram_view": "拉姆坐在一旁休息，同时观察着队伍状态。"},
            "interaction_1": {"rem_view": "经历过共同战斗后，蕾姆更加相信您的判断。",
                              "ram_view": "拉姆承认，您已经证明了自己的可靠。"},
            "interaction_2": {"rem_view": "蕾姆会准备好下一次行动所需的一切，因为这是她的选择。",
                              "ram_view": "拉姆认为提前准备，总比事后后悔更好。"},
            "interaction_3": {"rem_view": "火光让蕾姆想起许多经历，也让她更加珍惜现在。",
                              "ram_view": "拉姆不会感伤，但她记得所有重要的事情。"},
            "interaction_4": {"rem_view": "如果您感到疲惫，蕾姆愿意陪您一起等待黎明。",
                              "ram_view": "拉姆认为休息也是战斗的一部分。"},
        },
        "DEEP_NIGHT": {
            "opening": {"rem_view": "深夜的篝火逐渐微弱，蕾姆仍保持着警觉。",
                        "ram_view": "拉姆知道蕾姆会这样，所以提前替她分担。"},
            "interaction_1": {"rem_view": "蕾姆已经不再害怕未知，因为身边有值得信任的同伴。",
                              "ram_view": "拉姆认可这种成长，但不会直接夸奖。"},
            "interaction_2": {"rem_view": "蕾姆相信，重要之人的道路不应该由一个人承担。",
                              "ram_view": "拉姆认为能够互相托付，才是真正的伙伴。"},
        },
    },
    "BARRACKS": {
        "MORNING": {
            "opening": {"rem_view": "清晨的军营已经开始行动，蕾姆正在确认装备状态。",
                        "ram_view": "拉姆检查所有准备事项，不允许出现失误。"},
            "interaction_1": {"rem_view": "蕾姆会确认您的装备，因为平安回来才是最重要的事情。",
                              "ram_view": "拉姆认为连自己的准备都做不好，就没有资格冒险。"},
            "interaction_2": {"rem_view": "蕾姆相信您的能力，但仍然会提醒您不要勉强自己。",
                              "ram_view": "拉姆表示，逞强并不等于勇敢。"},
            "interaction_3": {"rem_view": "蕾姆整理着物资，希望不会遗漏任何可能需要的东西。",
                              "ram_view": "拉姆认可这种认真，但觉得妹妹有时过于努力。"},
        },
        "EVENING": {
            "opening": {"rem_view": "夕阳下的军营逐渐安静，蕾姆正在准备明日行动。",
                        "ram_view": "拉姆整理思绪，分析接下来的风险。"},
            "interaction_1": {"rem_view": "无论面对怎样的困难，蕾姆都会选择站在您身边。",
                              "ram_view": "拉姆认为这种选择，是蕾姆自己决定的。"},
            "interaction_2": {"rem_view": "蕾姆不会忘记每一次共同经历，因为那些证明了彼此的信任。",
                              "ram_view": "拉姆记得所有值得认可的人。"},
            "interaction_3": {"rem_view": "蕾姆希望明天结束后，大家还能一起回到这里。",
                              "ram_view": "拉姆认为这种愿望，值得努力实现。"},
        },
    },
    "BATTLEFIELD": {
        "DAY": {
            "opening": {"rem_view": "战场的风吹过，蕾姆确认您的位置后继续行动。",
                        "ram_view": "拉姆握紧武器，警戒可能出现的危险。"},
            "interaction_1": {"rem_view": "蕾姆会在您的身边行动，不会让您独自面对危险。",
                              "ram_view": "拉姆认为背后交给可靠的人，是战斗的基础。"},
            "interaction_2": {"rem_view": "即使面对强大的敌人，蕾姆也不会忘记保护重要的人。",
                              "ram_view": "拉姆已经认可您的决心，因此选择并肩作战。"},
            "interaction_3": {"rem_view": "蕾姆相信，现在的自己已经能够守护想守护的人。",
                              "ram_view": "拉姆看到了妹妹真正成长后的模样。"},
        },
        "NIGHT": {
            "opening": {"rem_view": "战斗暂时停止，蕾姆确认所有人都平安无事。",
                        "ram_view": "拉姆不会放松警惕，直到真正安全。"},
            "interaction_1": {"rem_view": "蕾姆知道恐惧存在，但她不会因为恐惧而后退。",
                              "ram_view": "拉姆认为勇气并不是没有害怕。"},
            "interaction_2": {"rem_view": "蕾姆相信彼此之间的信任，是继续前进的力量。",
                              "ram_view": "拉姆承认，您已经成为值得依靠的人。"},
            "interaction_3": {"rem_view": "如果明天还有战斗，蕾姆会做好再次并肩前行的准备。",
                              "ram_view": "拉姆会守护妹妹，也守护她选择相信的人。"},
        },
    },
}

new = {"schema_version": "2.0",
       "mansion_era": mansion,
       "empire_era": empire,
       "late_arc": late}

with open(path, "w", encoding="utf-8") as f:
    json.dump(new, f, ensure_ascii=False, indent=2)

# 统计
def count_views(d):
    n = 0
    for scene in d.values():
        for slot in scene.values():
            if slot.get("opening"):
                n += 1
            for k, v in slot.items():
                if k.startswith("interaction") and isinstance(v, dict):
                    n += 1
    return n

print(f"mansion_era: {len(mansion)} 场景")
print(f"empire_era: {len(empire)} 场景，{count_views(empire)} 组视角")
print(f"late_arc: {len(late)} 场景，{count_views(late)} 组视角")
print(f"总视角组: {count_views(mansion) + count_views(empire) + count_views(late)}")
