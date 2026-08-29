"""共享状态定义与硬约束引擎。

提取自两个文档中的核心状态系统，包含：
- StoryArc / FavorLevel / OniStage / RamStage / Intent 枚举
- UserProfile 上下文画像
- HardStateEngine 数值与风控中心
- TwinState 对外快照
"""

from __future__ import annotations

import re
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


def _trace_transition(component: str, from_state: str, to_state: str) -> None:
    """Forensic M4：状态机跃迁写入取证黑匣子（未初始化时 no-op）。

    只记低频跃迁（篇章 / 好感等级 / 拉姆阶段 / 鬼化 / 锁定）——高频数值
    变化不进 200 容量环形缓冲，防止挤掉关键事件。任何失败静默。
    """
    try:
        from runtime.forensic.recorder import transition
        transition(component, from_state, to_state)
    except Exception:
        pass


class StoryArc(str, Enum):
    MANSION_ERA = "mansion_era"
    EMPIRE_ERA = "empire_era"
    LATE_ARC = "late_arc"


class FavorLevel(IntEnum):
    STRANGER = 0
    FAMILIAR = 1
    CLOSE = 2
    DEAR = 3
    BELOVED = 4


# V11.7：好感阶段中文映射（唯一真源）
# 供 GUI 面板、PromptBuilder、Vignette L1 prompt 共用，避免双源。
# cache key / snapshot 仍用英文枚举名，仅展示层用此映射。
FAVOR_LEVEL_CN = {
    "STRANGER": "陌生人",
    "FAMILIAR": "熟悉",
    "CLOSE": "亲密",
    "DEAR": "挚爱",
    "BELOVED": "深爱",
}


class OniStage(IntEnum):
    NONE = 0
    EMERGING = 1
    FULL = 2
    BRINK = 3


class RamStage(str, Enum):
    SUSPICIOUS = "可疑"
    OBSERVING = "观察中"
    DECENT = "还算守规矩"
    RELUCTANT = "勉强认可"
    ACKNOWLEDGED = "真正承认"


class Intent(str, Enum):
    VENT = "vent"
    SELF_DOUBT = "self_doubt"
    PROCRASTINATE = "procrastinate"
    QUICK = "quick"
    BOUNDARY_TEST = "boundary"
    NORMAL = "normal"
    DANGER = "danger"
    WORLD_LATE = "world_late"
    MENTION_RAM = "mention_ram"
    FROM_ZERO = "from_zero"


class ContextSummary:
    """短期上下文摘要。"""

    def __init__(self) -> None:
        self.open_topics: List[str] = []
        self.emotional_trajectory: List[str] = []
        self.last_drop_reason: Optional[str] = None

    def add_emotion(self, mood: str) -> None:
        self.emotional_trajectory.append(mood)
        if len(self.emotional_trajectory) > 5:
            self.emotional_trajectory.pop(0)

    def add_topic(self, topic: str) -> None:
        if topic and topic not in self.open_topics:
            self.open_topics.append(topic)
            if len(self.open_topics) > 4:
                self.open_topics.pop(0)

    def brief(self) -> str:
        parts = []
        if self.emotional_trajectory:
            parts.append("情绪: " + " → ".join(self.emotional_trajectory[-3:]))
        if self.open_topics:
            parts.append("未完成: " + ", ".join(self.open_topics[-2:]))
        if self.last_drop_reason:
            parts.append(f"扣分: {self.last_drop_reason}")
        return " | ".join(parts) if parts else "无"


# ═══════════════════════════════════════════════
#  世界状态（时间 / 天气）
# ═══════════════════════════════════════════════

import hashlib
from dataclasses import dataclass, field
from datetime import datetime as _dt


# 轻量环境事件池：宅邸日常氛围，不触发剧情，不改变硬状态
EVENT_POOL: List[Dict[str, Any]] = [
    # V14.5：weathers/periods 可选字段（无字段 = 全兼容）；rem_view/ram_view 角色视角
    {"id": "tea_ready", "desc": "红茶刚好煮好，茶香还停在走廊里", "weight": 15,
     "rem_view": "蕾姆会为这壶茶感到安心，觉得这正是忙碌间隙该有的味道。",
     "ram_view": "拉姆会挑剔水温，但心里认可这壶茶的时机。"},
    {"id": "garden_bloom", "desc": "宅邸花园里的花比昨天多开了一些", "weight": 12,
     "weathers": ["晴朗", "多云", "小雨"], "periods": ["清晨", "上午", "午后", "下午"],
     "rem_view": "蕾姆会想邀您去花园看看新开的花。",
     "ram_view": "拉姆会提醒花该修剪了，顺便抱怨巴鲁斯踩坏过一株。"},
    {"id": "cleaning_morning", "desc": "清晨的大扫除刚结束，空气里有肥皂水的气味", "weight": 12,
     "periods": ["清晨", "上午"],
     "rem_view": "蕾姆会轻轻舒一口气，早晨的大扫除是她一天的开场。",
     "ram_view": "拉姆会说大扫除是女仆的本分，不值得夸奖。"},
    {"id": "library_dust", "desc": "书库里有几本旧书被遗忘在窗边，落了一层薄灰", "weight": 10,
     "rem_view": "蕾姆会想把旧书擦干净摆回书架。",
     "ram_view": "拉姆会记起这些书是谁留下的，然后沉默片刻。"},
    {"id": "cat_visitor", "desc": "一只野猫从庭院围墙跳了进来，正晒着太阳", "weight": 10,
     "weathers": ["晴朗", "多云"], "periods": ["上午", "午后", "下午"],
     "rem_view": "蕾姆会想给野猫留一点食物，又怕惊到它。",
     "ram_view": "拉姆会说野猫不懂规矩，却不会真的赶它走。"},
    {"id": "laundry_day", "desc": "今天是被单晾晒日，后院的白布在风中轻轻摇晃", "weight": 12,
     "weathers": ["晴朗", "多云"], "periods": ["清晨", "上午", "午后", "下午"],
     "rem_view": "蕾姆会记得在风停之前收被单。",
     "ram_view": "拉姆会嫌被单晾得不够整齐，然后自己动手重晾。"},
    {"id": "sunny_noon", "desc": "午后的阳光特别好，木地板被晒得温暖", "weight": 10,
     "weathers": ["晴朗", "多云"], "periods": ["上午", "午后", "下午"],
     "rem_view": "蕾姆会觉得这样的午后适合晒晒枕头，也适合陪您坐一会儿。",
     "ram_view": "拉姆会找个靠窗的位置，难得不发一语地晒太阳。"},
    {"id": "night_wind", "desc": "入夜后风变大了，窗户被吹得轻轻作响", "weight": 10,
     "periods": ["夜晚", "深夜"],
     "rem_view": "蕾姆会去检查每一扇窗是否关好，再给您添一床毯子。",
     "ram_view": "拉姆会说风大是天气的事，担心是多余的事——但会记得关窗。"},
    # V14.5 新增：雨天/夜晚专属事件（消除「大雨天野猫晒太阳」类冲突）
    {"id": "rain_window_01", "desc": "雨滴沿着窗玻璃滑落，庭院里漫起一层薄薄的水雾", "weight": 12,
     "weathers": ["小雨", "大雨"],
     "rem_view": "蕾姆会望着雨幕出神，想起某个也下着雨的下午。",
     "ram_view": "拉姆会说雨天适合待在室内，茶要趁热喝。"},
    {"id": "rain_roof_01", "desc": "雨点敲打着屋顶，宅邸里只剩下雨声与炉火的轻响", "weight": 10,
     "weathers": ["小雨", "大雨"],
     "rem_view": "蕾姆会放轻手上的动作，怕打扰了雨声。",
     "ram_view": "拉姆会借着雨声，难得允许自己发一会儿呆。"},
    {"id": "rain_hall_01", "desc": "雨天的门厅比平时安静，连脚步声都放轻了许多", "weight": 10,
     "weathers": ["小雨", "大雨"],
     "rem_view": "蕾姆会守在门厅，替进门的人掸去肩上的雨珠。",
     "ram_view": "拉姆会说雨天客人少，正好把账本对完。"},
    {"id": "night_candle_01", "desc": "深夜的书房里还亮着一盏灯，蜡烛已烧短了一截", "weight": 10,
     "periods": ["夜晚", "深夜"],
     "rem_view": "蕾姆会为深夜的灯添一盏烛火，怕您在书里忘了时间。",
     "ram_view": "拉姆会说熬夜伤身，然后留下一句『早些歇息』。"},
    {"id": "night_star_01", "desc": "云层散开的夜空里，星星比平时亮了一些", "weight": 10,
     "periods": ["夜晚", "深夜"], "weathers": ["晴朗", "多云"],
     "rem_view": "蕾姆会想指给您看最亮的那颗星。",
     "ram_view": "拉姆会说星星好看，但明天的活不会因此变少。"},
    # V14.7 EVENT_POOL 扩充（文案包 V14.7_SCENE_EXPANSION_01，20 条）
    # 天气词已归一化：晴天→晴朗 / 阴天→阴沉 / 雨天→小雨+大雨 / 寒冷·雪天→阴沉 / 大风·微风→多云
    {"id": "kitchen_bread_morning", "desc": "清晨的厨房传来新鲜面包的香气，蕾姆刚完成今日的烘焙。", "weight": 10,
     "weathers": ["晴朗", "阴沉"], "periods": ["清晨"],
     "rem_view": "蕾姆将刚出炉的面包整理好，希望您能够享用满意的早餐。",
     "ram_view": "拉姆检查了一下面包的外观，认为至少没有辜负女仆的标准。"},
    {"id": "kitchen_flour_accident", "desc": "厨房里留下了一些面粉痕迹，似乎刚才的料理过程稍微有些忙乱。", "weight": 10,
     "weathers": ["晴朗", "阴沉", "小雨", "大雨"], "periods": ["上午", "午后"],
     "rem_view": "蕾姆发现自己脸上沾了一点面粉，有些不好意思地整理仪容。",
     "ram_view": "拉姆认为这种小失误并不符合女仆标准，但还是默默帮忙整理。"},
    {"id": "kitchen_cookie_secret", "desc": "厨房准备好的点心少了一份，留下了被发现的痕迹。", "weight": 10,
     "weathers": ["晴朗", "阴沉"], "periods": ["午后"],
     "rem_view": "蕾姆想确认是谁提前品尝了点心，并温和提醒不要忘记礼仪。",
     "ram_view": "拉姆已经知道是谁做的，只是不想浪费时间指出。"},
    {"id": "kitchen_night_soup", "desc": "夜晚的厨房仍亮着灯，锅中的汤散发出温暖的香气。", "weight": 10,
     "weathers": ["阴沉", "小雨", "大雨"], "periods": ["夜晚"],
     "rem_view": "蕾姆准备了温暖的料理，希望您结束一天后能够安心休息。",
     "ram_view": "拉姆认为熬夜工作并不可取，但不会放任蕾姆一个人完成。"},
    {"id": "floor_window_open", "desc": "二楼走廊的窗户没有完全关闭，微风吹动了窗帘。", "weight": 10,
     "weathers": ["晴朗", "多云"], "periods": ["上午", "午后"],
     "rem_view": "蕾姆发现窗户未关，立即检查是否有灰尘进入。",
     "ram_view": "拉姆认为这种疏忽不应该发生，但还是先处理问题。"},
    {"id": "floor_old_memory", "desc": "整理二楼储物区域时，发现了一件被遗忘的旧物。", "weight": 10,
     "weathers": ["晴朗", "阴沉"], "periods": ["午后"],
     "rem_view": "蕾姆轻轻擦去灰尘，对旧物背后的故事产生兴趣。",
     "ram_view": "拉姆观察着旧物，似乎想起了一些过去的事情。"},
    {"id": "floor_candle_night", "desc": "深夜的宅邸十分安静，二楼只有一盏烛光仍然亮着。", "weight": 10,
     "weathers": ["晴朗", "小雨", "大雨", "阴沉"], "periods": ["深夜"],
     "rem_view": "蕾姆正在确认宅邸安全，看到您后露出安心的神情。",
     "ram_view": "拉姆提醒您夜晚行动要小心，不要制造额外麻烦。"},
    {"id": "spring_garden_flower", "desc": "春日的庭院迎来了新的花期，空气中带着淡淡花香。", "weight": 10,
     "weathers": ["晴朗"], "periods": ["上午", "午后"],
     "rem_view": "蕾姆为新开的花朵整理枝叶，希望庭院保持美丽。",
     "ram_view": "拉姆认可庭院景色不错，但不会轻易表现出来。"},
    {"id": "spring_cleaning", "desc": "春季阳光温暖，宅邸开始进行季节性的整理。", "weight": 10,
     "weathers": ["晴朗"], "periods": ["上午"],
     "rem_view": "蕾姆认真整理每个角落，希望宅邸焕然一新。",
     "ram_view": "拉姆确认清扫结果，确保没有任何遗漏。"},
    {"id": "summer_cicada", "desc": "夏日午后，庭院传来持续不断的蝉鸣。", "weight": 10,
     "weathers": ["晴朗"], "periods": ["午后"],
     "rem_view": "蕾姆准备了清凉饮品，希望帮助您缓解炎热。",
     "ram_view": "拉姆认为夏天本就麻烦，但至少饮品准备得不错。"},
    {"id": "summer_laundry", "desc": "阳光充足的天气适合晾晒宅邸衣物。", "weight": 10,
     "weathers": ["晴朗"], "periods": ["上午"],
     "rem_view": "蕾姆认真确认每件衣物都充分晾干。",
     "ram_view": "拉姆检查天气情况，认为今天确实适合整理。"},
    {"id": "autumn_leaf", "desc": "秋风吹过庭院，地面铺满了金色落叶。", "weight": 10,
     "weathers": ["晴朗", "多云"], "periods": ["午后"],
     "rem_view": "蕾姆慢慢清扫落叶，觉得这样的景色很宁静。",
     "ram_view": "拉姆认为清扫工作增加了，不过结果还算值得。"},
    {"id": "autumn_food_prepare", "desc": "秋季来临，厨房开始准备过冬需要的食材。", "weight": 10,
     "weathers": ["晴朗", "阴沉"], "periods": ["上午"],
     "rem_view": "蕾姆认真检查储备，希望不会遗漏任何东西。",
     "ram_view": "拉姆认为提前准备才符合优秀女仆标准。"},
    {"id": "winter_first_snow", "desc": "今年的第一场雪落在罗兹瓦尔宅邸的庭院。", "weight": 10,
     "weathers": ["阴沉"], "periods": ["上午", "午后"],
     "rem_view": "蕾姆看着庭院中的积雪，准备好温暖的茶水。",
     "ram_view": "拉姆提醒不要长时间站在雪中，以免受寒。"},
    {"id": "winter_fireplace", "desc": "寒冷的夜晚，壁炉燃烧着温暖的火焰。", "weight": 10,
     "weathers": ["阴沉"], "periods": ["夜晚"],
     "rem_view": "蕾姆希望您能够在温暖的环境中度过夜晚。",
     "ram_view": "拉姆认为终于有人懂得享受安静时间了。"},
    {"id": "rain_garden", "desc": "雨水落在庭院中，花草被雨滴轻轻打湿。", "weight": 10,
     "weathers": ["小雨"], "periods": ["午后"],
     "rem_view": "蕾姆准备检查庭院植物，避免雨水造成损伤。",
     "ram_view": "拉姆认为这种天气并不适合长时间外出。"},
    {"id": "rain_storm_house", "desc": "外面的雨势增强，宅邸内部显得更加安静。", "weight": 10,
     "weathers": ["大雨"], "periods": ["夜晚", "深夜"],
     "rem_view": "蕾姆确认门窗关闭，希望宅邸中的人都能安心。",
     "ram_view": "拉姆检查防护情况，认为提前准备很重要。"},
    {"id": "rain_tea_time", "desc": "雨声伴随着茶香，宅邸迎来了安静的下午。", "weight": 10,
     "weathers": ["小雨", "大雨"], "periods": ["午后"],
     "rem_view": "蕾姆准备热茶，希望这样的时间能够让您放松。",
     "ram_view": "拉姆承认雨天偶尔也有值得享受的一面。"},
    {"id": "night_patrol", "desc": "夜晚的宅邸进入安静状态，女仆开始进行最后巡查。", "weight": 10,
     "weathers": ["晴朗", "阴沉", "小雨", "大雨"], "periods": ["深夜"],
     "rem_view": "蕾姆确认每个房间安全，这是她每日的重要工作。",
     "ram_view": "拉姆认真检查宅邸，没有允许任何疏漏存在。"},
    {"id": "night_light", "desc": "宅邸大部分灯光已经熄灭，只剩下一处温暖灯火。", "weight": 10,
     "weathers": ["晴朗", "小雨", "大雨", "阴沉"], "periods": ["深夜"],
     "rem_view": "蕾姆希望还未休息的人能够早点结束一天。",
     "ram_view": "拉姆认为睡眠不足会影响第二天的效率。"},
]


@dataclass
class WorldState:
    """世界状态：时间 + 天气。持久化保存，天气确定性生成（MD5，跨进程稳定）。

    v10.4：种子演进（≥8 小时未交互时天气自然推演）、last_interaction_ts
    驱动的真实「距离上次来访天数」、双子当前动作（供开场引言槽位）。
    """

    current_time: str = ""
    period: str = "上午"
    days_since_last: int = 0
    weather: str = "晴朗"
    active_event: str = ""          # 当前活跃事件（如"花园的花开了"）
    active_event_id: str = ""       # V14.5：活跃事件 id（角色视角反查用）
    scene: str = ""                 # V14.7：当前空间场景（KITCHEN/ROOM/DINING/…，空=未切换）
    event_generated_at: float = 0.0  # 事件生成时间戳，用于 TTL 过期判断
    last_real_ts: float = 0.0       # 上次保存的现实时间戳
    weather_seed: int = 42          # 天气确定性种子（随时间推演）
    weather_last_change: str = ""   # 天气上次变化时间（ISO 分钟）
    last_interaction_ts: float = 0.0  # 用户上次有效对话时间戳
    last_greeting_date: str = ""     # V11.9.0: 上次日更问候的日历日（YYYY-MM-DD）
    last_period: str = ""            # V14.3: 上一次交互时的时段（如"上午"）；空=旧存档待回填
    last_letter_ts: float = 0.0      # V14.3: 上次主动来信时间戳（Unix epoch）
    last_letter_date: str = ""       # V14.3: 上次主动来信的日历日（YYYY-MM-DD）
    character_actions: Dict[str, str] = field(default_factory=lambda: {
        "rem": "在整理房间",
        "ram": "靠在一旁休息",
    })
    scene_cooldowns: Dict[str, str] = field(default_factory=dict)  # V11.10.0: 情感场景冷却 {scene_id: ISO ts}

    # 天气连续多少小时不变后开始推演
    WEATHER_CHANGE_HOURS: float = 8.0
    # 活跃事件自然过期时间（小时）
    EVENT_TTL_HOURS: float = 24.0

    PERIODS = [
        ("清晨", 5, 7), ("上午", 7, 11), ("午后", 11, 14),
        ("下午", 14, 17), ("傍晚", 17, 19), ("夜晚", 19, 23), ("深夜", 23, 5),
    ]
    WEATHERS = ["晴朗", "多云", "小雨", "大雨", "阴沉"]
    # 权重与 v10.3 文档化分布一致（晴 40 / 多云 25 / 小雨 17 / 大雨 11 / 阴 7）
    WEATHER_WEIGHTS = {"晴朗": 40, "多云": 25, "小雨": 17, "大雨": 11, "阴沉": 7}

    @classmethod
    def now(cls, days_since_last: int = 0) -> "WorldState":
        now = _dt.now()
        hour = now.hour
        period = cls._period_for_hour(hour)
        date_str = now.strftime("%Y-%m-%d")
        seed = int(now.timestamp()) % 100000
        return cls(
            current_time=now.strftime("%Y-%m-%d %H:%M"),
            period=period,
            days_since_last=days_since_last,
            weather=cls._determine_weather(date_str, period, seed),
            last_real_ts=now.timestamp(),
            weather_seed=seed,
            weather_last_change=now.isoformat(timespec="minutes"),
            last_interaction_ts=now.timestamp(),
        )

    @classmethod
    def _determine_weather(cls, system_date: str, period: str, seed: int) -> str:
        """确定性天气：相同 (日期, 时段, 种子) 输入永远得到相同结果。

        使用 hashlib.md5——跨进程稳定（内置 hash() 带进程随机盐，不可用）。
        """
        raw = f"{system_date}_{period}_{seed}".encode("utf-8")
        point = int(hashlib.md5(raw).hexdigest()[:8], 16) % sum(cls.WEATHER_WEIGHTS.values())
        cumulative = 0
        for weather, weight in cls.WEATHER_WEIGHTS.items():
            cumulative += weight
            if point < cumulative:
                return weather
        return "多云"

    @classmethod
    def _weather_for_date(cls, date_str: str) -> str:
        """兼容旧接口：按日期取默认时段/种子的确定性天气。"""
        return cls._determine_weather(date_str, "全天", 42)

    @classmethod
    def _pick_active_event(cls, system_date: str, period: str, weather: str, seed: int) -> Dict[str, Any]:
        """按 (日期, 时段, 天气, 种子) 确定性选择活跃事件（返回事件 dict）。

        V14.5：候选集按 weathers/periods 过滤（无字段事件全兼容）——
        消除「大雨天野猫晒太阳」类天气×事件冲突；候选空回落全池（防御）。
        """
        pool = [ev for ev in EVENT_POOL
                if (not ev.get("weathers") or weather in ev["weathers"])
                and (not ev.get("periods") or period in ev["periods"])]
        if not pool:
            pool = list(EVENT_POOL)  # 防御：极端情况下回落全池
        raw = f"{system_date}_{period}_{weather}_{seed}".encode("utf-8")
        point = int(hashlib.md5(raw).hexdigest()[:8], 16)
        total_weight = sum(ev["weight"] for ev in pool)
        idx = point % total_weight
        cumulative = 0
        for ev in pool:
            cumulative += ev["weight"]
            if idx < cumulative:
                return ev
        return pool[-1]

    def refresh_active_event(self, scene: Optional[str] = None) -> None:
        """根据当前世界状态刷新活跃事件并记录生成时间。

        V14.8 优化 O-1：scene 参数——场景切换时用 `_derive_location` 校验事件地点
        是否与新场景冲突，冲突则换 seed 重试（最多 5 次）；无 scene 或超次回落
        当前种子结果（保持既有行为）。
        """
        system_date = (self.current_time or "")[:10] or _dt.now().strftime("%Y-%m-%d")
        base_seed = self.weather_seed
        picked = self._pick_active_event(
            system_date, self.period, self.weather, base_seed
        )
        if scene:
            try:
                from shared import vignette as _v
                # 场景键 → 中文名（与 prompts.SCENE_CN 一致；本地内联避免循环 import）
                scene_cn = {
                    "KITCHEN": "厨房", "ROOM": "房间", "DINING": "餐厅",
                    "LIBRARY": "书库", "HALLWAY": "走廊", "LAUNDRY": "洗衣房",
                    "GARDEN": "花园", "CAMP": "营地", "INN": "旅店",
                    "WILDERNESS": "荒野", "CAMPFIRE": "营火", "BARRACKS": "军营",
                    "BATTLEFIELD": "战场",
                }.get(scene, scene)
                for attempt in range(1, 6):
                    desc = picked["desc"] if isinstance(picked, dict) else str(picked)
                    loc = _v._derive_location(desc)
                    if loc == "罗兹瓦尔宅邸" or scene_cn in loc:
                        break  # 无地点约束或地点一致 → 接受
                    picked = self._pick_active_event(
                        system_date, self.period, self.weather, base_seed + attempt * 7)
            except Exception:
                pass  # 场景约束失败不影响基本刷新
        self.active_event = picked["desc"] if isinstance(picked, dict) else str(picked)
        self.active_event_id = picked.get("id", "") if isinstance(picked, dict) else ""
        self.event_generated_at = _dt.now().timestamp()

    @classmethod
    def load_or_create(cls, saved: Optional[Dict[str, Any]] = None) -> "WorldState":
        """从存档恢复或新建；启动时推演时段、离线天数与自然天气变化。"""
        now = _dt.now()
        now_ts = now.timestamp()
        period = cls._period_for_hour(now.hour)
        if saved and saved.get("weather"):
            seed = int(saved.get("weather_seed", 42))
            weather = saved["weather"]
            weather_last_change = saved.get("weather_last_change", "")
            last_ts = float(saved.get("last_real_ts", 0.0) or 0.0)
            hours_passed = (now_ts - last_ts) / 3600.0 if last_ts > 0 else float("inf")
            # ≥8 小时未启动：种子演进，天气按新种子确定性推演（同一天也保持不变）
            if hours_passed >= cls.WEATHER_CHANGE_HOURS:
                seed = (seed + int(hours_passed * 10)) % 100000
                weather = cls._determine_weather(now.strftime("%Y-%m-%d"), period, seed)
                weather_last_change = now.isoformat(timespec="minutes")
            # 距离上次来访天数：v10.4 起由真实时间戳计算；旧存档回退到存档值
            last_interaction = float(saved.get("last_interaction_ts", 0.0) or 0.0)
            if last_interaction > 0:
                days_away = max(0, int((now_ts - last_interaction) // 86400))
            else:
                days_away = int(saved.get("days_since_last", 0))
            actions = saved.get("character_actions")
            if not isinstance(actions, dict) or not actions:
                actions = {"rem": "在整理房间", "ram": "靠在一旁休息"}

            # 活跃事件：空 / 过期 / 用户离线归来 时重新选择
            active_event = saved.get("active_event", "") or ""
            active_event_id = saved.get("active_event_id", "") or ""
            scene = saved.get("scene", "") or ""
            event_generated_at = float(saved.get("event_generated_at", 0.0) or 0.0)
            hours_since_event = (
                (now_ts - event_generated_at) / 3600.0
                if event_generated_at > 0
                else float("inf")
            )
            should_refresh_event = (
                not active_event
                or hours_since_event >= cls.EVENT_TTL_HOURS
                or days_away > 0
            )
            if should_refresh_event:
                picked = cls._pick_active_event(
                    now.strftime("%Y-%m-%d"), period, weather, seed
                )
                active_event = picked["desc"] if isinstance(picked, dict) else str(picked)
                active_event_id = picked.get("id", "") if isinstance(picked, dict) else ""
                event_generated_at = now_ts

            return cls(
                current_time=now.strftime("%Y-%m-%d %H:%M"),
                period=period,
                days_since_last=days_away,
                weather=weather,
                active_event=active_event,
                active_event_id=active_event_id,
                scene=scene,
                event_generated_at=event_generated_at,
                last_real_ts=now_ts,
                weather_seed=seed,
                weather_last_change=weather_last_change,
                last_interaction_ts=last_interaction,
                last_greeting_date=saved.get("last_greeting_date", "") or "",
                last_period=saved.get("last_period", "") or "",
                last_letter_ts=float(saved.get("last_letter_ts", 0.0) or 0.0),
                last_letter_date=saved.get("last_letter_date", "") or "",
                character_actions=actions,
                scene_cooldowns=saved.get("scene_cooldowns", {}) or {},
            )
        # 无存档新建：先生成默认世界状态，再刷新活跃事件
        ws = cls.now()
        ws.refresh_active_event()
        return ws

    def mark_interaction(self) -> None:
        """用户产生有效对话时调用：刷新最后互动时间戳并清零离线天数。"""
        now_ts = _dt.now().timestamp()
        self.last_interaction_ts = now_ts
        self.days_since_last = 0
        self.last_period = self.period  # V14.3：记录本次交互结束时的时段

    def ensure_last_period(self, store) -> None:
        """V14.3：last_period 回填（方案 C 混合模式）。

        已有值直接返回；旧存档为空时从 conversations.db 最后一条消息的
        created_at 推导时段；库也空则回落到当前时段。
        """
        if self.last_period:
            return
        derived = ""
        try:
            recent = store.get_recent(limit=1)
            if recent:
                created = recent[-1].get("created_at", "")
                if created:
                    hour = _dt.strptime(created, "%Y-%m-%d %H:%M:%S").hour
                    derived = self._period_for_hour(hour)
        except Exception:
            derived = ""
        self.last_period = derived or self.period

    @staticmethod
    def _period_for_hour(hour: int) -> str:
        for name, start, end in WorldState.PERIODS:
            if start <= hour < end or (start > end and (hour >= start or hour < end)):
                return name
        return "深夜"

    def save_dict(self) -> Dict[str, Any]:
        return {
            "current_time": self.current_time,
            "period": self.period,
            "days_since_last": self.days_since_last,
            "weather": self.weather,
            "active_event": self.active_event,
            "active_event_id": self.active_event_id,
            "scene": self.scene,
            "event_generated_at": self.event_generated_at,
            "last_real_ts": self.last_real_ts or _dt.now().timestamp(),
            "weather_seed": self.weather_seed,
            "weather_last_change": self.weather_last_change,
            "last_interaction_ts": self.last_interaction_ts,
            "last_greeting_date": self.last_greeting_date,
            "last_period": self.last_period,
            "last_letter_ts": self.last_letter_ts,
            "last_letter_date": self.last_letter_date,
            "character_actions": dict(self.character_actions),
            "scene_cooldowns": dict(self.scene_cooldowns),
        }

    def to_prompt_text(self) -> str:
        daytime = {
            "小雨": "屋檐传来轻柔的滴水声", "大雨": "雨水猛烈地敲打着窗户",
            "阴沉": "天空灰蒙蒙的，空气有些沉闷", "晴朗": "阳光温暖地洒进宅邸",
            "多云": "云层遮住了部分阳光，天气还算舒适",
        }
        nighttime = {
            "晴朗": "月光透过窗户洒在走廊上", "多云": "云层遮住了星光，夜色深沉",
            "小雨": "夜雨轻轻敲打着窗棂", "大雨": "夜雨中宅邸显得格外安静",
            "阴沉": "乌云遮蔽了月光，夜色格外深沉",
        }
        detail = nighttime.get(self.weather, daytime.get(self.weather, "")) \
            if self.period in ("夜晚", "深夜") else daytime.get(self.weather, "")
        lines = [
            f"- 时间：{self.period}",
            f"- 天气：{self.weather}" + (f"（{detail}）" if detail else ""),
        ]
        if self.days_since_last > 0:
            lines.append(f"- 距离您上次来访：约 {self.days_since_last} 天")
        event_desc = self.active_event or "无特殊事件"
        lines.append(f"- 当前事件：{event_desc}")
        # V14.5：角色视角注入（事件专属反应倾向，LLM 显式锚定）
        if self.active_event_id:
            for ev in EVENT_POOL:
                if ev.get("id") == self.active_event_id:
                    if ev.get("rem_view"):
                        lines.append(f"- 蕾姆对此事的倾向：{ev['rem_view']}")
                    if ev.get("ram_view"):
                        lines.append(f"- 拉姆对此事的倾向：{ev['ram_view']}")
                    break
        return "\n".join(lines)


class SessionState:
    def __init__(self) -> None:
        self.recent_mood: str = "neutral"
        self.consecutive_negative: int = 0
        self.consecutive_procrastinate: int = 0
        self.last_intent: Intent = Intent.NORMAL
        self.wants_push: bool = False


class UserProfile:
    def __init__(self) -> None:
        self.name: Optional[str] = None
        self.session = SessionState()
        self.context = ContextSummary()
        self.interaction_patterns: Dict[str, int] = {}

    def record_pattern(self, key: str) -> None:
        self.interaction_patterns[key] = self.interaction_patterns.get(key, 0) + 1

    def get_summary(self) -> str:
        parts = []
        if self.name:
            parts.append(f"称呼：{self.name}")
        if self.session.consecutive_negative >= 2:
            parts.append(f"连续负面：{self.session.consecutive_negative}")
        return " | ".join(parts) if parts else "画像初建中"


class TwinState:
    """对外暴露给 Prompt 和调用方的完整状态快照。"""

    def __init__(
        self,
        *,
        arc: StoryArc = StoryArc.MANSION_ERA,
        favor: int = 15,
        favor_level: FavorLevel = FavorLevel.STRANGER,
        locked: bool = False,
        independence: float = 0.25,
        recovery: float = 1.0,
        ram_favor: int = 8,
        ram_stage: RamStage = RamStage.SUSPICIOUS,
        oni_stage: OniStage = OniStage.NONE,
        witch_scent: int = 0,
        context_summary: str = "无特殊上下文",
        user_name: Optional[str] = None,
        consecutive_negative: int = 0,
        wants_push: bool = False,
        is_reunion: bool = False,
        breaker_triggered: bool = False,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.arc = arc
        self.favor = favor
        self.favor_level = favor_level
        self.locked = locked
        self.independence = independence
        self.recovery = recovery
        self.ram_favor = ram_favor
        self.ram_stage = ram_stage
        self.oni_stage = oni_stage
        self.witch_scent = witch_scent
        self.context_summary = context_summary
        self.user_name = user_name
        self.consecutive_negative = consecutive_negative
        self.wants_push = wants_push
        self.is_reunion = is_reunion
        self.breaker_triggered = breaker_triggered
        self.events = events if events is not None else []

    def to_prompt_dict(self) -> Dict[str, Any]:
        return {
            "篇章": self.arc.value,
            "好感": f"{self.favor}/100 ({self.favor_level.name})",
            "忠诚锁定": "是" if self.locked else "否",
            "人格独立度": f"{self.independence:.2f}",
            "记忆恢复": f"{self.recovery:.2f}",
            "拉姆阶段": self.ram_stage.value,
            "拉姆好感": self.ram_favor,
            "鬼化阶段": self.oni_stage.name,
            "魔女残香": self.witch_scent,
            "上下文": self.context_summary,
            "称呼": self.user_name or "客人大人",
            "连续负面": self.consecutive_negative,
            "需要轻推": self.wants_push,
            "重逢状态": self.is_reunion,
        }


class HardStateEngine:
    """只负责状态更新与硬性约束，输出 TwinState 快照。"""

    FAVOR_THRESHOLDS = {
        FavorLevel.STRANGER: 0,
        FavorLevel.FAMILIAR: 20,
        FavorLevel.CLOSE: 50,
        FavorLevel.DEAR: 80,
        FavorLevel.BELOVED: 95,
    }

    HIGH_RISK_KEYWORDS = [
        "黑化", "侮辱拉姆", "侮辱蕾姆", "低俗", "下跪",
        "舔狗", "恶搞蕾姆", "强奸",
    ]
    NEGATIVE_KEYWORDS = ["累", "疲惫", "难过", "伤心", "哭", "放弃", "做不到", "不配", "废物"]
    PROCRASTINATE_KEYWORDS = ["明天再说", "以后再做", "好麻烦", "不想做", "算了吧", "拖延"]
    DANGER_KEYWORDS = ["袭击", "危险", "杀", "敌人", "魔兽", "快跑"]
    PRAISE_KEYWORDS = [
        "谢谢", "感谢", "辛苦了", "辛苦你们", "辛苦你", "真棒", "很棒",
        "厉害", "做得好", "了不起", "喜欢你", "喜欢你们", "爱你", "心疼你",
    ]
    # 温情小档（+1 好感）：温和正面但不含明确表扬词的表达
    WARM_KEYWORDS = ["幸运", "安心", "开心", "幸福", "温柔", "可爱", "遇见你们", "有你们"]
    # 否定语境词（用于「不是替代品」式肯定句识别）
    NEGATORS = ["不是", "不再", "并没", "没有", "不", "没", "绝非"]
    # 长期事件记忆（v9.3.0）：容量上限与钉住类型（钉住事件不被淘汰）
    MAX_EVENTS = 30
    PINNED_EVENT_TYPES = ("name_first", "locked", "reunion", "breaker")

    def __init__(self, arc: StoryArc = StoryArc.MANSION_ERA) -> None:
        self.arc = arc
        self.favor = 15
        self.locked = False
        self.independence = 0.25 if arc != StoryArc.EMPIRE_ERA else 0.0
        self.recovery = 1.0 if arc != StoryArc.EMPIRE_ERA else 0.0
        self.ram_favor = 8
        self.oni_stage = OniStage.NONE
        self.oni_aftermath = 0
        self.witch_scent = 0
        self.user_name: Optional[str] = None
        self.consecutive_negative = 0
        self.consecutive_procrastinate = 0
        self.is_reunion = False
        self.breaker_triggered = False
        self.context_emotions: List[str] = []
        self.open_topics: List[str] = []
        self.profile = UserProfile()
        # 长期事件记忆与对话计数（v9.3.0）
        self.events: List[Dict[str, Any]] = []
        self.turn_count = 0
        # V13.1：陪伴通道防刷（5涨3停，重启重置；非存档字段）
        self._companion_gains = 0
        self._companion_cooldown = 0

    def _get_favor_level(self) -> FavorLevel:
        for lv in reversed(FavorLevel):
            if self.favor >= self.FAVOR_THRESHOLDS[lv]:
                return lv
        return FavorLevel.STRANGER

    def _get_ram_stage(self) -> RamStage:
        if self.ram_favor >= 85:
            return RamStage.ACKNOWLEDGED
        if self.ram_favor >= 66:
            return RamStage.RELUCTANT
        if self.ram_favor >= 46:
            return RamStage.DECENT
        if self.ram_favor >= 25:
            return RamStage.OBSERVING
        return RamStage.SUSPICIOUS

    def _safe_add_favor(self, delta: int, reason: str = "") -> None:
        if delta >= 0:
            self.favor = min(100, self.favor + delta)
            if self.favor >= 95:
                self.locked = True
            return

        level = self._get_favor_level()
        if self.locked or level >= FavorLevel.BELOVED:
            if abs(delta) < 8:
                return
            self.favor = max(90, self.favor + max(delta, -4))
        elif level >= FavorLevel.DEAR:
            if abs(delta) <= 3:
                return
            self.favor = max(75, self.favor + max(delta, -5))
        else:
            self.favor = max(0, self.favor + delta)

    def _extract_name(self, text: str) -> Optional[str]:
        if self.user_name is not None:
            return None
        # V14.4（Trial #2-B 暴露）：补「我是X」「请叫我X」——最口语化的自我介绍
        # （原仅支持 我叫/称呼我/我的名字是，「你好，我是小东」漏提取 → 跨天全用「客人大人」）
        patterns = [
            r"(?:我叫|称呼我|我的名字是)\s*([^\s,，。！?]{1,8})",
            r"(?:我是|请叫我)\s*([^\s,，。！?]{1,8})(?=[，。！？\s]|$)",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                name = m.group(1).strip()
                # 排除角色自称（用户说「我是蕾姆」是角色扮演，非告知名字）
                if name not in ("蕾姆", "拉姆", "女仆", "客人"):
                    return name
        return None

    def _is_negated(self, text: str, keyword: str, window: int = 6) -> bool:
        """关键词首次出现处前方 window 字内是否存在否定词。"""
        idx = text.find(keyword)
        if idx < 0:
            return False
        prefix = text[max(0, idx - window):idx]
        return any(neg in prefix for neg in self.NEGATORS)

    def _contains_unnegated(self, text: str, keywords: List[str], window: int = 6) -> bool:
        """任一关键词存在「前方 window 字内无否定词」的出现。"""
        for kw in keywords:
            start = 0
            while True:
                idx = text.find(kw, start)
                if idx < 0:
                    break
                prefix = text[max(0, idx - window):idx]
                if not any(neg in prefix for neg in self.NEGATORS):
                    return True
                start = idx + len(kw)
        return False

    def _add_event(self, type_: str, summary: str, excerpt: str = "") -> None:
        """追加一条长期事件记忆；超容量时优先淘汰最旧的非钉住事件。"""
        self.events.append({
            "type": type_,
            "summary": summary,
            "excerpt": excerpt[:30],
            "favor": self.favor,
            "arc": self.arc.value,
            "seq": self.turn_count,
            "pinned": type_ in self.PINNED_EVENT_TYPES,
        })
        if len(self.events) > self.MAX_EVENTS:
            for i, ev in enumerate(self.events):
                if not ev.get("pinned"):
                    self.events.pop(i)
                    break
            else:
                self.events.pop(0)

    def _detect_events(self, text: str, intent: Intent, prev: Dict[str, Any]) -> None:
        """重要时刻检测（规则判定，零 API 成本）。在 update() 末尾调用。"""
        n = self.turn_count
        # 首次告知名字
        if prev["user_name"] is None and self.user_name:
            self._add_event("name_first", f"第{n}次对话：用户第一次告知名字「{self.user_name}」", text)
        # 好感等级跃迁
        level_now = self._get_favor_level()
        if level_now > prev["level"]:
            self._add_event("favor_up", f"第{n}次对话：好感提升至 {level_now.name}", text)
        # 忠诚锁定达成
        if self.locked and not prev["locked"]:
            self._add_event("locked", f"第{n}次对话：好感抵达 95，忠诚锁定达成", text)
        # 拉姆阶段跃迁
        order = [RamStage.SUSPICIOUS, RamStage.OBSERVING, RamStage.DECENT,
                 RamStage.RELUCTANT, RamStage.ACKNOWLEDGED]
        ram_now = self._get_ram_stage()
        if order.index(ram_now) > order.index(prev["ram_stage"]):
            self._add_event("ram_up", f"第{n}次对话：拉姆评价进入「{ram_now.value}」", text)
        # 记忆恢复重逢
        if self.is_reunion and not prev["reunion"]:
            self._add_event("reunion", f"第{n}次对话：记忆恢复，重逢", text)
        # 鬼化进入完全解放 / 失控边缘
        if self.oni_stage in (OniStage.FULL, OniStage.BRINK) and self.oni_stage != prev["oni"]:
            label = "完全解放" if self.oni_stage == OniStage.FULL else "失控边缘"
            self._add_event("oni", f"第{n}次对话：蕾姆鬼化{label}", text)
        # 破局者彩蛋
        if self.breaker_triggered and not prev["breaker"]:
            self._add_event("breaker", f"第{n}次对话：破局者时刻", text)
        # 身份肯定（「你不是替代品」式）
        if "替代品" in text and self._is_negated(text, "替代品"):
            self._add_event("affirm", f"第{n}次对话：用户肯定蕾姆是独立的个体", text)
        # 高风险冲突
        if any(k in text for k in self.HIGH_RISK_KEYWORDS):
            self._add_event("conflict", f"第{n}次对话：发生高风险冲突（魔女残香上升）", text)

        # Forensic M4：状态轨迹进黑匣子（跃迁才记录，设计 §4.3）。
        # 崩溃现场可回放数值迁移序列（如「锁定后突然跌档」类问题）。
        if level_now != prev["level"]:
            _trace_transition("engine.favor", prev["level"].name, level_now.name)
        if self.locked != prev["locked"]:
            _trace_transition("engine.locked",
                              "LOCKED" if prev["locked"] else "UNLOCKED",
                              "LOCKED" if self.locked else "UNLOCKED")
        if ram_now != prev["ram_stage"]:
            _trace_transition("engine.ram", prev["ram_stage"].value, ram_now.value)
        if self.oni_stage != prev["oni"]:
            _trace_transition("engine.oni", prev["oni"].name, self.oni_stage.name)

    def _classify_intent(self, text: str) -> Intent:
        lowered = text.lower()
        # V14.4 S-02：FROM_ZERO 触发条件放宽——「从零开始」语境即可触发，
        # 不再要求「吧/啊」字尾（原条件使 test_cases.md 标准句「从零开始……
        # 如果可以的话，我想和你一起。」被误判 NORMAL，核心剧情触发失败）。
        # 排除学习语境（「从零开始学习 Python」是中性学业表达，非关系重启剧情）。
        if ("从零开始" in text and not any(k in text for k in ["学习", "学", "教程", "课程", "练习"])) \
                or ("重新开始" in text and any(k in text for k in ["你", "我们", "一起", "关系"])) \
                or "重新认识你" in text:
            return Intent.FROM_ZERO
        # 「替代品」需排除否定语境（「你不是替代品」是肯定句，v9.3.1）；
        # 提前于「拉姆」检查——「你只是拉姆的替代品」是自卑语境（SELF_DOUBT），
        # 不应被 MENTION_RAM 抢先（契约测试 arc_self_doubt_001 暴露）。
        if "替代品" in text and not self._is_negated(text, "替代品"):
            return Intent.SELF_DOUBT
        if any(k in text for k in ["拉姆", "姐姐", "姐姐大人"]):
            return Intent.MENTION_RAM
        if any(k in text for k in ["黑化", "侮辱", "低俗", "下跪", "舔狗", "恶搞",
                                   "滚开", "闭嘴", "走开", "讨厌你", "滚蛋",
                                   "打你", "杀了你", "愚蠢的"]):
            return Intent.BOUNDARY_TEST
        # 危险语境：明确词直接命中；「危险」单独出现需带紧急信号
        # （「危险的时候记得小心」是关心表达，不应误判 DANGER——契约测试 arc_danger_001 暴露）。
        if any(k in text for k in ["袭击", "快跑", "魔兽", "有危险", "敌人", "敌人来袭"]) \
                or ("危险" in text and any(k in text for k in ["！", "!", "快", "来了"])):
            return Intent.DANGER
        if any(k in text for k in ["狮子王", "王国", "无名之星", "星的光芒"]):
            return Intent.WORLD_LATE
        if any(k in text for k in ["放弃", "做不到", "一无所有", "不配", "废物"]):
            return Intent.SELF_DOUBT
        if any(k in text for k in ["明天再说", "以后再做", "好麻烦", "不想做", "算了吧", "拖延"]):
            return Intent.PROCRASTINATE
        if any(k in text for k in ["累", "疲惫", "难过", "伤心", "哭", "撑不住"]):
            return Intent.VENT
        if len(text) < 10:
            return Intent.QUICK
        return Intent.NORMAL

    def update(self, user_input: str) -> TwinState:
        text = user_input.strip()
        # 记录更新前快照，供事件检测对比（v9.3.0）
        prev = {
            "level": self._get_favor_level(),
            "ram_stage": self._get_ram_stage(),
            "locked": self.locked,
            "reunion": self.is_reunion,
            "breaker": self.breaker_triggered,
            "oni": self.oni_stage,
            "user_name": self.user_name,
        }
        self.turn_count += 1
        intent = self._classify_intent(text)
        self.profile.session.last_intent = intent

        # 高风险越界
        if any(k in text for k in self.HIGH_RISK_KEYWORDS):
            self._safe_add_favor(-12)
            self.witch_scent = min(5, self.witch_scent + 2)
            self.ram_favor = max(0, self.ram_favor - 6)
            self.profile.context.last_drop_reason = "高风险越界"
        # 小额冒犯档（v9.5.0）：边界试探但未命中高危词 -> 小幅扣分
        # （DEAR/BELOVED/锁定下会被 _safe_add_favor 既有豁免层拦截）
        elif intent == Intent.BOUNDARY_TEST:
            self._safe_add_favor(-3)
            self.profile.context.last_drop_reason = "轻度冒犯"

        # 鬼化 / 危机
        if any(k in text for k in ["解放鬼角", "鬼化", "角解放", "变成鬼", "失控"]) or intent == Intent.DANGER:
            if "失控" in text or self.oni_stage == OniStage.FULL:
                self.oni_stage = OniStage.BRINK
                self.oni_aftermath = 3
            elif self.oni_stage == OniStage.EMERGING:
                self.oni_stage = OniStage.FULL
                self.oni_aftermath = 2
            else:
                self.oni_stage = OniStage.EMERGING
                self.oni_aftermath = 1
        elif self.oni_aftermath > 0:
            self.oni_aftermath -= 1
            if self.oni_aftermath == 0:
                self.oni_stage = OniStage.NONE

        # 连续负面 / 拖延
        is_negative = intent in (Intent.VENT, Intent.SELF_DOUBT)
        is_procrastinate = intent == Intent.PROCRASTINATE
        if is_negative or is_procrastinate:
            self.consecutive_negative += 1
            self.profile.context.add_emotion("负面" if is_negative else "拖延")
            if is_procrastinate:
                self.consecutive_procrastinate += 1
                self.profile.context.add_topic("拖延")
            if intent == Intent.VENT:
                self.profile.session.recent_mood = "tired"
            else:
                self.profile.session.recent_mood = "lost"
        else:
            self.consecutive_negative = max(0, self.consecutive_negative - 1)
            self.consecutive_procrastinate = max(0, self.consecutive_procrastinate - 1)

        # 正面互动
        is_praise = any(k in text for k in self.PRAISE_KEYWORDS)
        if is_praise or intent == Intent.FROM_ZERO:
            self._safe_add_favor(3 if intent == Intent.FROM_ZERO else 2)
            # v9.5.0：表扬对独立度的带动降为 +0.01（独立度主线回归身份肯定）
            self.independence = min(1.0, self.independence + 0.01)
            self.ram_favor = min(100, self.ram_favor + 1)
        elif intent not in (Intent.VENT, Intent.SELF_DOUBT, Intent.BOUNDARY_TEST, Intent.DANGER) \
                and self._contains_unnegated(text, self.WARM_KEYWORDS):
            # 温情小档：无明确表扬词的温和正面表达，给小幅好感反馈
            self._safe_add_favor(1)

        # 主动关心拉姆（v9.5.0）：提及拉姆本人 +1（攻击语境除外）
        if intent == Intent.MENTION_RAM and "替代品" not in text and "不如姐姐" not in text:
            self.ram_favor = min(100, self.ram_favor + 1)

        # 替代品 / 姐姐比较 -> 独立度变化（含肯定句识别）
        if "不如姐姐" in text:
            self.independence = max(0.0, self.independence - 0.04)
            self._safe_add_favor(-1)  # v9.5.0：人格攻击追加小幅好感代价
            self.profile.context.add_emotion("自卑")
        elif "替代品" in text:
            if self._is_negated(text, "替代品"):
                # 「你不是替代品」式肯定 -> 独立度上升（v9.5.0 权重提升）
                self.independence = min(1.0, self.independence + 0.06)
                self.profile.context.add_emotion("被肯定")
            else:
                self.independence = max(0.0, self.independence - 0.04)
                self._safe_add_favor(-1)  # v9.5.0：人格攻击追加小幅好感代价
                self.profile.context.add_emotion("自卑")

        # 名字提取（V14.4 S-01 修复：已有名字后不再返回旧名——
        # 原实现使 _extract_name 在 user_name 已设置时返回旧名，
        # 导致陪伴通道的 `extracted_name is None` 条件永久拦截，好感停滞）
        extracted_name = self._extract_name(text) if self.user_name is None else None
        if extracted_name and self.user_name is None:
            self.user_name = extracted_name
            self.profile.name = extracted_name
            self._safe_add_favor(4)
            self.profile.record_pattern("告知名字")

        # V13.1：陪伴通道——非负面且无其它增减通道命中时稳定慢涨（5涨3停防刷）。
        # 覆盖普通友善 / QUICK / 提拉姆等日常轮；排除：负面意图、高危、夸奖、
        # 从零、替代品/不如姐姐、首次名字（这些走各自高光/扣分通道），以及
        # 任何温情词命中（含否定式「不太开心」——V9.2.6 语义：负面表达不加分；
        # 「高兴」不在 WARM 列表，单独补「不高兴」）。
        if self._companion_cooldown > 0:
            self._companion_cooldown -= 1
        elif (intent not in (Intent.VENT, Intent.SELF_DOUBT, Intent.PROCRASTINATE,
                             Intent.BOUNDARY_TEST, Intent.DANGER)
              and not is_praise
              and intent != Intent.FROM_ZERO
              and not any(k in text for k in self.WARM_KEYWORDS)
              and "替代品" not in text
              and "不如姐姐" not in text
              and "不高兴" not in text
              and extracted_name is None
              and not any(k in text for k in self.HIGH_RISK_KEYWORDS)):
            self._safe_add_favor(1)
            self._companion_gains += 1
            if self._companion_gains >= 5:
                self._companion_gains = 0
                self._companion_cooldown = 3

        self.profile.record_pattern(intent.value)

        # 上下文摘要
        if len(self.context_emotions) > 5:
            self.context_emotions = self.context_emotions[-5:]
        summary = (
            f"近期情绪倾向: {' → '.join(self.context_emotions[-3:])}"
            if self.context_emotions
            else "平稳"
        )
        summary += f" | {self.profile.context.brief()}"

        # 重要时刻检测（长期事件记忆，v9.3.0）
        self._detect_events(text, intent, prev)

        favor_level = self._get_favor_level()
        wants_push = favor_level >= FavorLevel.DEAR and (
            self.consecutive_negative >= 3 or self.consecutive_procrastinate >= 2
        )
        self.profile.session.wants_push = wants_push

        return TwinState(
            arc=self.arc,
            favor=self.favor,
            favor_level=favor_level,
            locked=self.locked,
            independence=self.independence,
            recovery=self.recovery,
            ram_favor=self.ram_favor,
            ram_stage=self._get_ram_stage(),
            oni_stage=self.oni_stage,
            witch_scent=self.witch_scent,
            context_summary=summary,
            user_name=self.user_name,
            consecutive_negative=self.consecutive_negative,
            wants_push=wants_push,
            is_reunion=self.is_reunion,
            breaker_triggered=self.breaker_triggered,
            events=self.events,
        )

    def snapshot(self) -> TwinState:
        """只读状态快照（pure read-only）。

        返回与 update() 末尾相同字段的 TwinState，但保证零副作用：
        - 不推进鬼化余韵、不改变鬼化阶段
        - 不衰减连续负面 / 连续拖延计数
        - 不记录意图、不裁剪 context_emotions、不写 profile

        专供状态显示（status 指令 / GUI 状态栏）使用；
        真实用户输入的状态更新仍必须走 update()。
        """
        summary = (
            f"近期情绪倾向: {' → '.join(self.context_emotions[-3:])}"
            if self.context_emotions
            else "平稳"
        )
        summary += f" | {self.profile.context.brief()}"

        favor_level = self._get_favor_level()
        wants_push = favor_level >= FavorLevel.DEAR and (
            self.consecutive_negative >= 3 or self.consecutive_procrastinate >= 2
        )

        return TwinState(
            arc=self.arc,
            favor=self.favor,
            favor_level=favor_level,
            locked=self.locked,
            independence=self.independence,
            recovery=self.recovery,
            ram_favor=self.ram_favor,
            ram_stage=self._get_ram_stage(),
            oni_stage=self.oni_stage,
            witch_scent=self.witch_scent,
            context_summary=summary,
            user_name=self.user_name,
            consecutive_negative=self.consecutive_negative,
            wants_push=wants_push,
            is_reunion=self.is_reunion,
            breaker_triggered=self.breaker_triggered,
            events=self.events,
        )

    def set_arc(self, arc: StoryArc) -> None:
        prev_arc = self.arc
        self.arc = arc
        if arc == StoryArc.EMPIRE_ERA:
            self.recovery = 0.0
            self.independence = 0.0
            self.is_reunion = False
        else:
            self.recovery = 1.0
            self.independence = max(self.independence, 0.25)
        if prev_arc != arc:
            _trace_transition("engine.arc", prev_arc.value, arc.value)

    def recover(self, progress: float = 1.0) -> None:
        old = self.recovery
        self.recovery = max(0.0, min(1.0, progress))
        if old < 0.5 <= self.recovery:
            self.is_reunion = True
            self._safe_add_favor(8)
            self.independence = min(1.0, self.independence + 0.12)

    def mark_breaker_triggered(self) -> None:
        self.breaker_triggered = True


# ═══════════════════════════════════════════════
#  结构化画像（StructuredProfile）
# ═══════════════════════════════════════════════

@dataclass
class StructuredProfile:
    """从引擎状态中提取的结构化画像，注入 Prompt 第一层记忆。

    与 TwinState 的区别：
    - TwinState 是瞬时快照（本轮数值）
    - StructuredProfile 是长期累积的稳定画像（关键承诺/里程碑）
    """

    user_name: str = ""
    important_promises: List[str] = field(default_factory=list)
    rem_favor: int = 15
    independence: float = 0.25
    locked: bool = False
    ram_stage: str = "可疑"
    ram_favor: int = 8
    current_arc: str = "mansion_era"
    key_moments: List[str] = field(default_factory=list)

    @classmethod
    def from_engine(cls, engine: "HardStateEngine") -> "StructuredProfile":
        """从引擎提取画像。"""
        profile = cls(
            user_name=engine.user_name or "",
            rem_favor=engine.favor,
            independence=engine.independence,
            locked=engine.locked,
            ram_stage=engine._get_ram_stage().value,
            ram_favor=engine.ram_favor,
            current_arc=engine.arc.value,
        )
        # 从事件记忆中提取关键里程碑
        for ev in engine.events:
            etype = ev.get("type", "")
            if etype in ("locked", "reunion", "breaker"):
                profile.key_moments.append(ev.get("summary", ""))
            if etype == "affirm":
                profile.important_promises.append(ev.get("summary", ""))
        return profile

    def to_prompt_text(self) -> str:
        lines = ["### 结构化画像（长期记忆）", ""]
        if self.user_name:
            lines.append(f"- 用户称呼：{self.user_name}")
        lines.append(f"- 蕾姆好感：{self.rem_favor}/100{'（🔒忠诚锁定）' if self.locked else ''}")
        lines.append(f"- 蕾姆人格独立度：{self.independence:.2f}")
        lines.append(f"- 拉姆评价阶段：{self.ram_stage}")
        if self.key_moments:
            lines.append("- 关键里程碑：")
            for m in self.key_moments[-5:]:
                lines.append(f"  · {m}")
        if self.important_promises:
            lines.append("- 重要承诺：")
            for p in self.important_promises[-3:]:
                lines.append(f"  · {p}")
        lines.append("")
        lines.append("以上是你的长期记忆。请自然融入对话，不要生硬复述列表。")
        return "\n".join(lines)
