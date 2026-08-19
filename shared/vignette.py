"""Opening Vignette 开场氛围引言生成器（v10.4）。

多级弹力兜底网络：
- L0 缓存层：会话内存缓存 + 持久化 LRU 缓存（data/vignette_cache.json），
  按「时段 | 天气 | 离开天数桶 | 蕾姆好感等级 | 拉姆阶段」状态桶命中，
  相同状态重启毫秒级返回，零 API 成本。
- L1 LLM 主生成：带自修正的重试（≤3 次，温度 0.78 → 0.65 衰减），
  输出经清洗与校验（字数 80~180、违禁词、禁止直接对用户发问）。
- L2 动态母板填充：时段/天气/双子动作槽位的文学性模板，降级不生硬。
- L3 静态兜底：保证 100% 可用性。

上下文隔离铁律：引言是 UI 渲染专属数据（View-Only Data），
绝不写入 LLM 对话历史（messages），防止模型产生人称混淆。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime as _dt  # V14.4 Step2：归来感/短开场确定性 seed
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared.template_registry import load_registry, pick as registry_pick  # V14.4 Step2
from shared.letter_manager import LetterManager  # V14.4 Step2：归来感复用来信五桶口径

# V14.4 Step2：篇章模板注册表（懒加载单例；frozen 兼容经 ContentLoader._get_content_dir）
_REGISTRY: Optional[Dict[str, Any]] = None


def _get_registry() -> Dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_registry(os.path.join(
            ContentLoader()._get_content_dir(), "templates", "registry.json"))
    return _REGISTRY

from shared.config import get_data_dir
from shared.state import WorldState, FAVOR_LEVEL_CN

# LLMCallable 协议：与 llm.bridge.ReZeroLLMBridge.raw_completion 签名一致
LLMCallable = Callable[..., str]

# ── 校验参数 ──────────────────────────────────
MAX_LLM_ATTEMPTS = 3
BASE_TEMPERATURE = 0.78
RETRY_TEMPERATURE = 0.65
MIN_LEN = 80
MAX_LEN = 180

FORBIDDEN_WORDS = [
    "用户", "玩家", "系统", "AI", "大模型", "提示词",
    "您说", "主人您好", "请问有什么", "作为AI", "角色扮演",
]

CACHE_MAX_ENTRIES = 40

# L3 静态兜底
STATIC_FALLBACK = (
    "宅邸静静地立在流淌的时间里。蕾姆与拉姆各自做着手头的事，"
    "没有人先开口，一切都安静得刚刚好。"
)


def _get_cache_path() -> str:
    return os.path.join(get_data_dir(), "vignette_cache.json")


# ═══════════════════════════════════════════════
#  L2：动态模板文学母板
# ═══════════════════════════════════════════════

PERIOD_DESC = {
    "清晨": ["晨光刚刚越过窗沿", "天空还带着一点青白", "宅邸在清晨显得格外安静"],
    "上午": ["上午的光线已经明亮起来", "阳光洒在地板上", "宅邸进入了忙碌却有序的时辰"],
    "午后": ["午后的空气有些懒洋洋的", "阳光偏了角度", "时间在午后显得格外缓慢"],
    "下午": ["下午的光渐渐柔和", "影子开始拉长", "宅邸的节奏稍微放缓"],
    "傍晚": ["暮色正在从窗外漫进来", "天边只剩下最后一丝亮光", "傍晚的宅邸有种安静的过渡感"],
    "夜晚": ["夜色已经完全笼罩了宅邸", "窗外只剩深色的轮廓", "夜晚让一切声音都变得更清晰"],
    "深夜": ["夜已深了", "宅邸里几乎只剩下细微的声响", "深夜的空气带着凉意"],
}

WEATHER_DESC = {
    "晴朗": ["空气清透", "光线格外干净", "没有云层打扰"],
    "多云": ["云层把光线过滤得柔和许多", "天空显得有些沉", "空气里有种说不清的平静"],
    "小雨": ["细雨连绵", "屋檐不时落下水珠", "空气里带着潮湿的气味"],
    "大雨": ["雨声密集而持续", "窗外的世界被雨水模糊", "空气完全被水汽浸透"],
    "阴沉": ["天色压得很低", "光线暗淡", "空气里有种说不出的滞涩"],
}

EXTRA_ATMOSPHERE = [
    "空气中还残留着淡淡的红茶香。",
    "远处隐约能听到风穿过庭院的声音。",
    "时间仿佛被放慢了些许。",
    "一切都安静得刚刚好。",
    "没有人先开口，沉默却并不令人难受。",
]


# ═══════════════════════════════════════════════
#  V11.5：双子状态驱动动作文案库
#  动作本体不以「在」开头，模板统一「正在{动作本体}」
# ═══════════════════════════════════════════════

# ── Rem 动作文案 ──
REM_DANGER = [
    "紧绷着身体站在角落，目光警觉地扫过四周",
    "握紧了拳头，鬼族的气息若隐若现",
]
REM_WITCH_SNIFF = [
    "微微皱眉，似乎闻到了什么不安的气息",
    "不自觉地握紧了裙角，神情凝重",
]
REM_FRAGILE = [
    "神情恍惚，动作有些迟疑，像在努力回忆什么",
    "迷茫地望着窗外，手指无意识地攥着围裙",
]
REM_LOCKED = [
    "守在门扉的阴影里，像是一直在等谁回来",
    "轻轻握着门把手，目光柔和而坚定",
]
REM_DEFAULT = [
    "整理着房间里的摆设",
    "擦拭着茶具，动作细致而安静",
    "叠着桌布，神情平和",
]
REM_DEFAULT_NIGHT = [
    "借着烛光缝补衣物",
    "轻手轻脚地收拾着餐桌",
]

# ── Ram 动作文案 ──
RAM_HORN_PAIN = [
    "偶尔抬手按住额头，眉头微蹙",
    "不动声色地揉着太阳穴，神情有些不适",
]
RAM_SISTER_PROTECT = [
    "挡在蕾姆身前，神情严肃",
    "警惕地注视着蕾姆的方向，随时准备上前",
]
RAM_SUSPECT = [
    "冷眼打量着这边，嘴角微微下沉",
    "抱臂靠在墙边，目光审视",
]
RAM_OBSERVE = [
    "不动声色地观察着这边的动静",
    "翻着书页，余光却始终没有离开",
]
RAM_ACKNOWLEDGE = [
    "安心地翻着书，偶尔抬头看一眼",
    "靠在窗边，神情舒展了许多",
]
RAM_DEFAULT = [
    "靠在一旁休息",
    "整理着书架上的旧书",
]

# ── 双子联动文案（日常双人同屏时启用）──
# 动作本体不以「在」开头，避免与模板「正在{动作本体}」拼出「正在在」
DUO_DEFAULT = [
    ("整理着茶具", "递着杯碟配合"),              # 日常茶歇
    ("擦拭着餐桌", "收拾着旁边的椅子"),            # 共同劳作
]
DUO_NIGHT = [
    ("借着烛光缝补衣物", "整理着灯芯"),
]


# ═══════════════════════════════════════════════
#  V11.6：ContentLoader + M1 内容池细分
# ═══════════════════════════════════════════════

class ContentLoader:
    """内容资产加载器（懒加载 + 单例 + 三层回退）。

    JSON → 内置常量 → STATIC_FALLBACK
    单文件/条目失败隔离，错误日志输出到 console。
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _init(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._actions: Dict[str, List[dict]] = {}
        self._openings: Dict[str, List[dict]] = {}
        self._load_all()

    def _get_content_dir(self) -> str:
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS  # type: ignore
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "content")

    def _load_all(self) -> None:
        content_dir = self._get_content_dir()
        actions_dir = os.path.join(content_dir, "actions")
        for fname in ("rem.json", "ram.json", "twin.json"):
            self._load_json(os.path.join(actions_dir, fname), self._actions)
        openings_dir = os.path.join(content_dir, "openings")
        for fname in ("mansion.json",):
            self._load_json(os.path.join(openings_dir, fname), self._openings)

    def _load_json(self, path: str, target: Dict[str, list]) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                cat = entry.get("category")
                if not cat:
                    continue
                target.setdefault(cat, []).append(entry)
        except Exception as e:
            print(f"[ContentLoader] 加载失败 {path}: {e}")

    def get(self, category: str, role: Optional[str] = None) -> list:
        """获取动作文案池。可选按 role 过滤。"""
        self._init()
        pool = self._actions.get(category, [])
        if role:
            pool = [e for e in pool if e.get("role") == role]
        return pool

    def get_pairs(self, category: str) -> List[Tuple[str, str]]:
        """获取 Twin 联动文案对。返回 [(rem_text, ram_text), ...]。"""
        self._init()
        pool = self._actions.get(category, [])
        result: List[Tuple[str, str]] = []
        for e in pool:
            if e.get("role") == "Twin" and e.get("text") and e.get("text_pair"):
                result.append((e["text"], e["text_pair"]))
        return result

    def get_openings(self, category: str) -> list:
        """获取开场段文案池。"""
        self._init()
        return self._openings.get(category, [])


def _pick_rem_mansion_action(period: str, weather: str, days_since_last: int) -> str:
    """从 M1 内容池选择 Rem 日常动作，无命中回退内置常量。"""
    loader = ContentLoader()
    if days_since_last > 0:
        pool = loader.get("mansion_return", role="Rem")
        if pool:
            return random.choice(pool)["text"]
    if weather in ("小雨", "大雨", "阴沉"):
        pool = loader.get("mansion_rain", role="Rem")
        if pool:
            return random.choice(pool)["text"]
    if period in ("清晨", "上午"):
        pool = loader.get("mansion_morning", role="Rem")
        if pool:
            return random.choice(pool)["text"]
    if period in ("午后", "下午"):
        pool = loader.get("mansion_afternoon", role="Rem")
        if pool:
            return random.choice(pool)["text"]
    if period == "傍晚":
        pool = loader.get("mansion_evening", role="Rem")
        if pool:
            return random.choice(pool)["text"]
    pool = loader.get("mansion_tea", role="Rem")
    if pool:
        return random.choice(pool)["text"]
    return random.choice(REM_DEFAULT)


def _pick_ram_mansion_action(period: str, days_since_last: int) -> str:
    """从 M1 内容池选择 Ram 日常动作，无命中回退内置常量。

    注：雨天已在高优先级角痛桶处理，此处不接 mansion_rain。
    """
    loader = ContentLoader()
    if days_since_last > 0:
        pool = loader.get("mansion_return", role="Ram")
        if pool:
            return random.choice(pool)["text"]
    if period in ("清晨", "上午"):
        pool = loader.get("mansion_morning", role="Ram")
        if pool:
            return random.choice(pool)["text"]
    if period in ("午后", "下午"):
        pool = loader.get("mansion_afternoon", role="Ram")
        if pool:
            return random.choice(pool)["text"]
    if period == "傍晚":
        pool = loader.get("mansion_evening", role="Ram")
        if pool:
            return random.choice(pool)["text"]
    pool = loader.get("mansion_tea", role="Ram")
    if pool:
        return random.choice(pool)["text"]
    return random.choice(RAM_DEFAULT)


def _pick_short_opening(period: str, weather: str, days_since_last: int,
                        arc: str = "mansion_era", recovery: Optional[float] = None) -> Optional[str]:
    """尝试从内容池匹配短开场段。~30% 概率使用，无命中返回 None。

    V14.4 Step2：注册表 slot=vignette 优先（确定性 hash，同日同时段稳定）；
    Step3：按 arc×recovery 选型（帝国低 recovery 命中疏离档/恢复期记忆碎片，
    pick 内置 arc 级回落）；无命中回落旧 openings 硬匹配（防御兜底）。
    """
    if random.random() > 0.3:
        return None
    reg = _get_registry()
    seed = f"{_dt.now().strftime('%Y-%m-%d')}_{period}"
    hit = registry_pick(reg, arc=arc, slot="vignette",
                        period=period, weather=weather,
                        recovery=recovery, seed=seed)
    if hit and hit.get("text"):
        return hit["text"]
    loader = ContentLoader()
    openings = loader.get_openings("opening_mansion")
    if not openings:
        return None
    candidates = []
    for op in openings:
        op_id = op.get("id", "")
        op_text = op.get("text", "")
        if not op_text:
            continue
        if days_since_last > 0 and "return" in op_id:
            candidates.append(op_text)
        elif weather in ("小雨", "大雨") and "rain" in op_id:
            candidates.append(op_text)
        elif period in ("夜晚", "深夜") and "night" in op_id:
            candidates.append(op_text)
        elif period in ("清晨", "上午") and "sun_01" in op_id and weather not in ("小雨", "大雨", "阴沉"):
            candidates.append(op_text)
        elif period in ("午后", "下午") and "sun_02" in op_id and weather not in ("小雨", "大雨", "阴沉"):
            candidates.append(op_text)
        elif period in ("清晨", "上午") and "fog" in op_id:
            candidates.append(op_text)
    if candidates:
        return random.choice(candidates)
    return None


def _pick_rem_action(
    locked: bool = False,
    recovery: float = 1.0,
    oni_warning: bool = False,
    witch_scent: int = 0,
    period: str = "上午",
    weather: str = "晴朗",
    days_since_last: int = 0,
) -> str:
    """Rem 动作优先级选择（命中即停，返回动作本体，不带「在」前缀）。

    V11.6：高优先级状态仍走 V11.5 真实字段桶；
    仅 default 分支再按 period/weather/days_since_last 细分读 M1 池。
    """
    if oni_warning or witch_scent >= 3:
        return random.choice(REM_DANGER)
    if witch_scent >= 2:
        return random.choice(REM_WITCH_SNIFF)
    if recovery < 0.3:
        return random.choice(REM_FRAGILE)
    if locked:
        return random.choice(REM_LOCKED)
    if period in ("夜晚", "深夜"):
        return random.choice(REM_DEFAULT_NIGHT)
    # V11.6：default 分支 → M1 内容池细分（JSON → 内置常量回退）
    return _pick_rem_mansion_action(period, weather, days_since_last)


def _pick_ram_action(
    ram_stage: str = "观察中",
    oni_warning: bool = False,
    witch_scent: int = 0,
    weather: str = "晴朗",
    period: str = "上午",
    days_since_last: int = 0,
) -> str:
    """Ram 动作优先级选择（命中即停，返回动作本体，不带「在」前缀）。

    V11.6：雨天先角痛桶（V11.5 真实字段），高等级状态仍走 V11.5；
    仅 default 分支再按 period/days_since_last 细分读 M1 池。
    """
    if weather in ("小雨", "大雨", "阴沉"):
        return random.choice(RAM_HORN_PAIN)
    if oni_warning or witch_scent >= 3:
        return random.choice(RAM_SISTER_PROTECT)
    if ram_stage == "可疑":
        return random.choice(RAM_SUSPECT)
    if ram_stage == "观察中":
        return random.choice(RAM_OBSERVE)
    if ram_stage == "真正承认":
        return random.choice(RAM_ACKNOWLEDGE)
    # V11.6：default 分支 → M1 内容池细分（JSON → 内置常量回退）
    return _pick_ram_mansion_action(period, days_since_last)


def _try_duo_link(
    locked: bool, recovery: float, oni_warning: bool, witch_scent: int,
    ram_stage: str, weather: str, period: str, days_since_last: int = 0,
) -> Optional[Tuple[str, str]]:
    """尝试双子联动动作。仅当双方都落在日常优先级时启用，返回 (rem, ram) 或 None。

    V11.6：优先从 M1 Twin 内容池读取 (rem_text, ram_text) 对；
    无命中回退内置 DUO 常量。
    """
    # 高等级单人状态优先，不启用联动
    if oni_warning or witch_scent >= 2:
        return None
    if recovery < 0.3 or locked:
        return None
    if ram_stage in ("可疑",) or weather in ("小雨", "大雨", "阴沉"):
        return None
    # V11.6：M1 Twin 内容池选择（JSON → 内置常量回退）
    loader = ContentLoader()
    cat = None
    if days_since_last > 0:
        cat = "mansion_return"
    elif period in ("清晨", "上午"):
        cat = "mansion_morning"
    elif period in ("午后", "下午"):
        cat = "mansion_afternoon"
    elif period == "傍晚":
        cat = "mansion_evening"
    else:
        cat = "mansion_tea"
    pairs = loader.get_pairs(cat)
    if pairs:
        return random.choice(pairs)
    # 回退内置常量
    if period in ("夜晚", "深夜"):
        return random.choice(DUO_NIGHT)
    return random.choice(DUO_DEFAULT)


# ── V11.0：离线归来感文案（按天数分桶）──

def _pick_return_awareness(days: int) -> str:
    """按离线天数分桶返回归来感文案，0 天返回空串。"""
    if days <= 0:
        return ""
    if days == 1:
        return random.choice([
            "你离开不过一日，宅邸的节奏几乎没有变化。",
        ])
    if days == 2:
        return random.choice([
            "你离开了两天，蕾姆似乎一直在留意门口的动静。",
        ])
    if days <= 7:
        return random.choice([
            "几天不见，宅邸里似乎有些细微的变化。",
            "你离开了有些日子了，蕾姆见到你时眼中闪过一丝安心。",
        ])
    return random.choice([
        "你离开了很久。蕾姆站在门口，像是一直在等。",
        "久别重逢，宅邸的空气都似乎轻快了一些。",
    ])


def _pick_return_flavor(ws: WorldState, arc: str = "mansion_era",
                        recovery: Optional[float] = None) -> str:
    """V14.4 Step2：归来感走注册表 slot=return_flavor（复用来信五桶口径）。

    hours_since 由 last_interaction_ts 精确计算 → LetterManager 五桶映射
    （CROSS_PERIOD/HALF_DAY/DAYS_1_3/DAYS_3_7/LONG_ABSENCE）；
    Step3：按 arc×recovery 选型（帝国低 recovery 命中疏离档 return_flavor，
    恢复期无对应档位时 pick 回落宅邸——设计语义）；
    无匹配回落旧 _pick_return_awareness 粗桶（防御兜底）。
    0 天离线返回空串（不插入）。
    """
    if ws.days_since_last <= 0:
        return ""
    if ws.last_interaction_ts > 0:
        # 用 time.time()（全精度浮点）——datetime.now().timestamp() 微秒截断
        # 会在整 72h 边界产生 71.99999x 误差导致误落 DAYS_1_3（实测踩坑）
        hours_since = (time.time() - ws.last_interaction_ts) / 3600.0
    else:
        hours_since = ws.days_since_last * 24.0
    bucket = LetterManager.calculate_offline_bucket(hours_since, ws.last_period, ws.period)
    if bucket is None:  # <12h 同时段：旧语义下 days>=1 也走兜底
        return _pick_return_awareness(ws.days_since_last)
    reg = _get_registry()
    seed = f"{_dt.now().strftime('%Y-%m-%d')}_{ws.period}"
    hit = registry_pick(reg, arc=arc, slot="return_flavor",
                        offline_bucket=bucket, period=ws.period,
                        recovery=recovery, seed=seed)
    if hit and hit.get("text"):
        return hit["text"]
    return _pick_return_awareness(ws.days_since_last)


def _derive_location(active_event: str) -> str:
    """从 active_event 描述推导地点短描述（V11.8）。

    纯函数、无副作用。关键词启发式查表，无匹配回落「罗兹瓦尔宅邸」。
    覆盖 EVENT_POOL 全部 8 条事件的地点词。
    """
    if not active_event:
        return "罗兹瓦尔宅邸"
    if "走廊" in active_event:
        return "宅邸走廊"
    if "花园" in active_event:
        return "宅邸花园"
    if "书库" in active_event or "书房" in active_event:
        return "宅邸书库"
    if "庭院" in active_event:
        return "宅邸庭院"
    if "后院" in active_event:
        return "宅邸后院"
    if "门厅" in active_event:
        return "宅邸门厅"
    if "屋顶" in active_event:
        return "宅邸屋顶下"
    if "夜空" in active_event or "星星" in active_event:
        return "宅邸庭院"
    if "厨房" in active_event:
        return "宅邸厨房"
    if "二楼" in active_event:
        return "宅邸二楼走廊"
    if "壁炉" in active_event:
        return "宅邸大厅"
    if "大扫除" in active_event:
        return "宅邸大厅"
    if "窗" in active_event:
        return "宅邸窗边"
    if "宅邸" in active_event:  # V14.7：泛宅邸事件（巡查/灯火/初雪/茶会）
        return "罗兹瓦尔宅邸"
    if "地板" in active_event:
        return "宅邸向阳处"
    return "罗兹瓦尔宅邸"


def fill_dynamic_template(
    ws: WorldState,
    locked: bool = False,
    recovery: float = 1.0,
    oni_warning: bool = False,
    witch_scent: int = 0,
    ram_stage: str = "观察中",
    arc: str = "mansion_era",  # V14.4 Step3：篇章透传（帝国低 recovery → 疏离档）
) -> str:
    """L2 动态槽位填充模板（V11.5：状态化动作 + 去「正在在」铁律）。

    动作本体不以「在」开头，模板统一「正在{动作本体}」格式。
    保留 V11.0 的归来感与 active_event 融入。
    V11.6：~30% 概率优先使用短开场段（JSON 内容池），无命中回退模板。
    V14.4 Step3：短开场/归来感按 arc 选型。
    """
    # V11.6：尝试短开场段（~30% 概率，JSON → None 回退模板）
    short_op = _pick_short_opening(ws.period, ws.weather, ws.days_since_last,
                                   arc=arc, recovery=recovery)
    if short_op:
        return short_op

    period_desc = random.choice(PERIOD_DESC.get(ws.period, ["时间悄然流过"]))
    weather_desc = random.choice(WEATHER_DESC.get(ws.weather, ["天气如常"]))
    extra = random.choice(EXTRA_ATMOSPHERE)

    # V11.0：离线归来感（0 天返回空串，不插入）；V14.4 Step2/3：注册表五桶口径 + arc×recovery
    return_desc = _pick_return_flavor(ws, arc=arc, recovery=recovery)

    # V11.0：活跃事件氛围（EVENT_POOL 文案已文学化，直接作为独立短句）
    event_part = f"{ws.active_event}。" if ws.active_event and ws.active_event.strip() else ""

    # V11.5：双子联动判定——双方都在日常态时启用联动动作
    duo = _try_duo_link(
        locked, recovery, oni_warning, witch_scent,
        ram_stage, ws.weather, ws.period, ws.days_since_last,
    )
    if duo is not None:
        rem_action, ram_action = duo
    else:
        rem_action = _pick_rem_action(
            locked=locked, recovery=recovery,
            oni_warning=oni_warning, witch_scent=witch_scent,
            period=ws.period, weather=ws.weather,
            days_since_last=ws.days_since_last,
        )
        ram_action = _pick_ram_action(
            ram_stage=ram_stage, oni_warning=oni_warning,
            witch_scent=witch_scent, weather=ws.weather,
            period=ws.period, days_since_last=ws.days_since_last,
        )

    # V11.8：回写选中动作到 WorldState，供下次 L1 prompt 展示真实动作
    try:
        ws.character_actions["rem"] = rem_action
        ws.character_actions["ram"] = ram_action
    except Exception:
        pass  # 回写失败不影响引言生成

    # V11.5：模板统一「正在{动作本体}」，彻底消灭「正在在」
    templates = [
        f"{period_desc}，{weather_desc}。{event_part}蕾姆正在{rem_action}，动作很轻。拉姆正在{ram_action}。{return_desc}{extra}",
        f"{period_desc}。{weather_desc}。{event_part}蕾姆正在{rem_action}，拉姆正在{ram_action}，两人之间维持着熟悉的安静。{return_desc}{extra}",
        f"{weather_desc}的{ws.period}，宅邸显得格外沉静。{event_part}蕾姆正在{rem_action}。拉姆正在{ram_action}。{return_desc}{extra}",
    ]
    return random.choice(templates)


# ═══════════════════════════════════════════════
#  校验与过滤清洗
# ═══════════════════════════════════════════════

def sanitize_and_validate_vignette(text: str) -> Tuple[bool, str]:
    """清洗 LLM 输出并校验。返回 (是否通过, 清洗后文本或失败原因)。"""
    if not text or not isinstance(text, str):
        return False, "Empty output"

    cleaned = text.strip()

    # 移除常见前缀杂质
    prefixes_to_strip = [
        "好的", "以下是", "引言：", "开场：", "【开场引言】",
        "【开场】", "正文：", "```markdown", "```",
    ]
    for prefix in prefixes_to_strip:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip(" ：:：\n")
    cleaned = cleaned.rstrip("`\n ")

    # raw_completion 异常回包形如「（错误信息）」，整段括号包裹一律视为失败
    if cleaned.startswith("（") and cleaned.endswith("）"):
        return False, "Wrapped error echo"

    # 字数校验
    if len(cleaned) < MIN_LEN:
        return False, f"Too short ({len(cleaned)} chars)"
    if len(cleaned) > MAX_LEN:
        return False, f"Too long ({len(cleaned)} chars)"

    # 违禁词校验
    for word in FORBIDDEN_WORDS:
        if word in cleaned:
            return False, f"Forbidden word found: '{word}'"

    # 人称倾斜校验（防止模型直接对用户发问）
    if "您" in cleaned and ("吗？" in cleaned or "呢？" in cleaned or "吧？" in cleaned):
        return False, "Contains direct interactive dialogue"

    return True, cleaned


# ═══════════════════════════════════════════════
#  L0：本地持久化缓存
# ═══════════════════════════════════════════════

def build_cache_key(ws: WorldState, rem_level: str, ram_stage: str,
                    arc: str = "mansion_era", recovery: float = 1.0) -> str:
    """按状态桶生成缓存 key（离开天数分桶：0 / 1-2 / 3+）。

    V14.4：缓存 key 补 arc 与 recovery 桶（§3.3 跨篇章缓存污染修复——
    宅邸篇缓存不再被帝国篇命中；recovery 桶 a/r/m 三档）。
    """
    days = ws.days_since_last
    days_bucket = "0" if days == 0 else ("1-2" if days <= 2 else "3+")
    recovery_bucket = "a" if recovery >= 0.85 else ("r" if recovery >= 0.35 else "m")
    raw = f"{arc}|{recovery_bucket}|{ws.period}|{ws.weather}|{days_bucket}|{rem_level}|{ram_stage}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def load_cache() -> Dict[str, str]:
    path = _get_cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache: Dict[str, str]) -> None:
    path = _get_cache_path()
    try:
        # LRU 简单淘汰：保留最近 CACHE_MAX_ENTRIES 条
        if len(cache) > CACHE_MAX_ENTRIES:
            keys = list(cache.keys())[-CACHE_MAX_ENTRIES:]
            cache = {k: cache[k] for k in keys}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Vignette] 缓存保存失败: {e}")


# ═══════════════════════════════════════════════
#  核心生成器
# ═══════════════════════════════════════════════

class VignetteGenerator:
    """开场引言多级生成器。

    llm_callable：兼容 (system_prompt, user_prompt, temperature=..., max_tokens=...)
    签名的调用对象（通常传 ReZeroLLMBridge.raw_completion）；为 None 时直接走 L2。
    """

    def __init__(self, llm_callable: Optional[LLMCallable] = None) -> None:
        self.llm_callable = llm_callable
        self._session_cache: Optional[str] = None
        self._persistent_cache: Dict[str, str] = load_cache()

    def _build_prompt(self, ws: WorldState, rem_level: str,
                      independence: float, ram_stage: str) -> Tuple[str, str]:
        event_desc = ws.active_event or "无特殊事件"
        rem_action = ws.character_actions.get("rem", "做着日常事务")
        ram_action = ws.character_actions.get("ram", "在一旁休息")
        system_date = (ws.current_time or "")[:10] or "未知日期"
        hour_text = (ws.current_time or "")[11:16] or ""

        system_text = (
            "你正在为《Re:从零开始的异世界生活》双子女仆系统撰写一段「开场氛围引言」。"
            "风格类似轻小说章节开头的环境与人物描写。使用第三人称，不对用户说话。"
        )
        user_text = f"""【硬性状态（绝对不可修改）】
- 系统日期：{system_date} {hour_text}
- 当前时段：{ws.period}
- 天气：{ws.weather}
- 地点：{_derive_location(ws.active_event)}
- 距离用户上次到访：{ws.days_since_last} 天
- 蕾姆当前动作：{rem_action}
- 拉姆当前动作：{ram_action}
- 最近事件：{event_desc}
- 蕾姆关系阶段：{FAVOR_LEVEL_CN.get(rem_level, rem_level)}，人格独立度：{independence:.2f}
- 拉姆评价阶段：{ram_stage}

【写作要求】
1. 使用第三人称，带有轻微文学性的笔调，营造沉浸感。
2. 自然描写当前的时间光影、天气感受，以及蕾姆与拉姆正在做的事情。
3. 可轻微体现两人对环境的感受，但不要过度解读，不要直接对用户说话。
4. 不要总结、不要解释系统、不要出现「用户」「玩家」等词。
5. 字数严格控制在 90～140 字之间。
6. 语气符合原著氛围：可以安静、可以有淡淡温情，也可以有一点寂寥。
请直接输出引言正文，不要加任何前缀或标题。"""
        return system_text, user_text

    def _call_llm(self, system_text: str, user_text: str, temperature: float) -> Optional[str]:
        if self.llm_callable is None:
            return None
        try:
            return self.llm_callable(
                system_text, user_text,
                temperature=temperature, max_tokens=280,
            )
        except Exception as e:
            print(f"[Vignette] LLM 请求异常: {e}")
            return None

    def generate(
        self,
        ws: WorldState,
        rem_favor_level: str = "CLOSE",
        independence: float = 0.5,
        ram_stage: str = "观察中",
        force_refresh: bool = False,
        locked: bool = False,
        recovery: float = 1.0,
        oni_warning: bool = False,
        witch_scent: int = 0,
        arc: str = "mansion_era",  # V14.4：篇章（缓存 key 分桶；默认宅邸零感知）
    ) -> str:
        """按 L0 → L1 → L2 → L3 顺序生成开场引言。

        V11.5：新增 locked/recovery/oni_warning/witch_scent 参数，
        透传至 L2 fill_dynamic_template 用于状态化动作选择。
        L1 _build_prompt 不使用这些参数（仍用 ws.character_actions 原始值）。
        """
        # L0：会话级内存缓存
        if self._session_cache and not force_refresh:
            return self._session_cache

        # L0：持久化文件缓存
        cache_key = build_cache_key(ws, rem_favor_level, ram_stage,
                                    arc=arc, recovery=recovery)
        if not force_refresh and cache_key in self._persistent_cache:
            result = self._persistent_cache[cache_key]
            self._session_cache = result
            return result

        # L1：LLM 主路径（带重试与校验）
        if self.llm_callable is not None:
            system_text, user_text = self._build_prompt(
                ws, rem_favor_level, independence, ram_stage)
            for attempt in range(MAX_LLM_ATTEMPTS):
                temperature = BASE_TEMPERATURE if attempt == 0 else RETRY_TEMPERATURE
                raw_text = self._call_llm(system_text, user_text, temperature)
                if raw_text is None:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                ok, result_or_reason = sanitize_and_validate_vignette(raw_text)
                if ok:
                    cleaned = result_or_reason
                    self._persistent_cache[cache_key] = cleaned
                    save_cache(self._persistent_cache)
                    self._session_cache = cleaned
                    return cleaned
                print(f"[Vignette] 第 {attempt + 1} 次校验未通过: {result_or_reason}")
                time.sleep(0.4)
            print("[Vignette] LLM 路径尝试耗尽，降级至动态模板填充 (L2)")

        # L2：动态模板（V11.5：透传状态参数用于动作选择）
        try:
            vignette = fill_dynamic_template(
                ws,
                locked=locked,
                recovery=recovery,
                oni_warning=oni_warning,
                witch_scent=witch_scent,
                ram_stage=ram_stage,
                arc=arc,  # V14.4 Step3：篇章透传（帝国 → 疏离/记忆碎片档）
            )
            if vignette:
                self._session_cache = vignette
                return vignette
        except Exception as e:
            print(f"[Vignette] 动态模板异常: {e}")

        # L3：静态兜底
        self._session_cache = STATIC_FALLBACK
        return STATIC_FALLBACK


def generate_opening_vignette(
    ws: WorldState,
    rem_favor_level: str = "CLOSE",
    independence: float = 0.5,
    ram_stage: str = "观察中",
    llm_callable: Optional[LLMCallable] = None,
    force_refresh: bool = False,
) -> str:
    """一次性便捷入口：新建生成器并生成开场引言。"""
    return VignetteGenerator(llm_callable=llm_callable).generate(
        ws,
        rem_favor_level=rem_favor_level,
        independence=independence,
        ram_stage=ram_stage,
        force_refresh=force_refresh,
    )


def prepare_session_opening(
    llm_callable: Optional[LLMCallable] = None,
    rem_favor_level: str = "CLOSE",
    independence: float = 0.5,
    ram_stage: str = "观察中",
) -> Tuple[WorldState, str]:
    """应用启动标准单一入口（docx 兼容签名）。

    加载/更新世界状态并生成开场引言；返回 (world_state, vignette)。
    底层沿用 memory.json 单持久化管线，与现有 GUI 完全兼容。
    """
    from shared.world_state import load_world_state, update_world_state_on_startup

    ws = load_world_state()
    ws = update_world_state_on_startup(ws)
    vignette = generate_opening_vignette(
        ws,
        rem_favor_level=rem_favor_level,
        independence=independence,
        ram_stage=ram_stage,
        llm_callable=llm_callable,
    )
    return ws, vignette
