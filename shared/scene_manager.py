"""V14.7：宅邸空间场景系统（场景切换 / 场景开场 / 场景互动 / 名场面 / 关键人物）。

数据源（V14.7 文案资产，frozen 兼容随 content/ 进 EXE）：
- content/scene_dialogue.json   宅邸场景对话库（A1：7 场景 × 时段 × 角色视角）
- content/character_dialogue.json 关键人物互动库（E3：贝蒂/罗兹瓦尔/爱蜜莉雅/帕克）
- content/milestone_lines.json  名场面状态联动语感库（E4：鬼化/失忆/从零开始/忠诚/托付）
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, Optional

# 场景中文关键词 → 场景键（A1 库 + V14.8 帝国/后期）
SCENE_KEYWORDS = {
    "厨房": "KITCHEN",
    "房间": "ROOM", "卧室": "ROOM",
    "餐厅": "DINING", "饭厅": "DINING",
    "书库": "LIBRARY", "书房": "LIBRARY",
    "走廊": "HALLWAY",
    "洗衣房": "LAUNDRY",
    "花园": "GARDEN", "庭院": "GARDEN",
    # V14.8：帝国篇（营地/旅店/荒野）
    "营地": "CAMP", "营帐": "CAMP", "帐篷": "CAMP",
    "旅店": "INN", "客栈": "INN", "酒馆": "INN",
    "荒野": "WILDERNESS", "荒原": "WILDERNESS", "旷野": "WILDERNESS",
    # V14.8：后期篇（营火/军营/战场）
    "营火": "CAMPFIRE", "篝火": "CAMPFIRE", "火堆": "CAMPFIRE",
    "军营": "BARRACKS", "军帐": "BARRACKS",
    "战场": "BATTLEFIELD", "战场边缘": "BATTLEFIELD", "前线": "BATTLEFIELD",
}

# 场景移动动词前缀（「去厨房」「回房间」「到花园」）
# V14.7 修复（验收 O-3）：移除「在」——「在厨房喝茶/在花园散步」是位置陈述
# 非移动意图（原实现误触发场景切换）；「去…在…」等真实移动组合仍保留
_MOVE_PREFIXES = ("去", "到", "回", "进", "来到", "走去")

# 时段映射（world.period → 场景库 slot 键）
_PERIOD_SLOTS: Dict[str, Dict[str, str]] = {
    "KITCHEN": {"清晨": "MORNING", "上午": "MORNING", "午后": "AFTERNOON",
                "下午": "AFTERNOON", "傍晚": "AFTERNOON", "夜晚": "NIGHT", "深夜": "NIGHT"},
    "ROOM": {"清晨": "MORNING", "上午": "MORNING", "午后": "MORNING",
             "下午": "MORNING", "傍晚": "MORNING", "夜晚": "NIGHT", "深夜": "DEEP_NIGHT"},
    "DINING": {"清晨": "BREAKFAST", "上午": "BREAKFAST", "午后": "DINNER",
               "下午": "DINNER", "傍晚": "DINNER", "夜晚": "DINNER", "深夜": "DINNER"},
    "LIBRARY": {"清晨": "AFTERNOON", "上午": "AFTERNOON", "午后": "AFTERNOON",
                "下午": "AFTERNOON", "傍晚": "AFTERNOON", "夜晚": "AFTERNOON", "深夜": "AFTERNOON"},
    "HALLWAY": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
                "傍晚": "DAY", "夜晚": "DAY", "深夜": "DAY"},
    "LAUNDRY": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
                "傍晚": "DAY", "夜晚": "DAY", "深夜": "DAY"},
    "GARDEN": {"清晨": "SUNNY", "上午": "SUNNY", "午后": "SUNNY", "下午": "SUNNY",
               "傍晚": "SUNNY", "夜晚": "SUNNY", "深夜": "SUNNY"},
    # V14.8：帝国/后期场景时段映射（文案组交付 V14.8 Part1/2）
    "CAMP": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
             "傍晚": "DAY", "夜晚": "NIGHT", "深夜": "NIGHT"},
    "INN": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
            "傍晚": "DAY", "夜晚": "NIGHT", "深夜": "NIGHT"},
    "WILDERNESS": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
                   "傍晚": "DAY", "夜晚": "NIGHT", "深夜": "NIGHT"},
    "CAMPFIRE": {"清晨": "NIGHT", "上午": "NIGHT", "午后": "NIGHT", "下午": "NIGHT",
                 "傍晚": "NIGHT", "夜晚": "NIGHT", "深夜": "DEEP_NIGHT"},
    "BARRACKS": {"清晨": "MORNING", "上午": "MORNING", "午后": "EVENING", "下午": "EVENING",
                 "傍晚": "EVENING", "夜晚": "EVENING", "深夜": "EVENING"},
    "BATTLEFIELD": {"清晨": "DAY", "上午": "DAY", "午后": "DAY", "下午": "DAY",
                    "傍晚": "DAY", "夜晚": "NIGHT", "深夜": "NIGHT"},
}

# 人物关键词 → E3 库键
CHARACTER_KEYWORDS = {
    "贝蒂": "BEATRICE", "碧翠丝": "BEATRICE",
    "罗兹瓦尔": "ROSWAAL", "罗兹瓦尔大人": "ROSWAAL",
    "爱蜜莉雅": "EMILIA", "艾米莉亚": "EMILIA",
    "帕克": "PACK", "猫": "PACK", "猫咪": "PACK", "灰猫": "PACK",
}


def _content_dir() -> str:
    """定位 content/ 目录（frozen 兼容：EXE 内 _MEIPASS/content）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, "content")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "content")


def _load(name: str) -> Dict[str, Any]:
    path = os.path.join(_content_dir(), name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class SceneManager:
    """宅邸空间场景系统（无状态查询 + 静态资产，线程安全）。"""

    _scene_db: Optional[Dict[str, Any]] = None
    _character_db: Optional[Dict[str, Any]] = None
    # V14.7 优化 O-4：场景互动轮转去重（{scene|slot: idx} + {scene|slot: 上次条目}）
    _interaction_rotor: Dict[str, int] = {}
    _last_interaction: Dict[str, Any] = {}
    _milestone_db: Optional[Dict[str, Any]] = None

    @classmethod
    def _scenes(cls, arc: Optional[str] = None) -> Dict[str, Any]:
        """场景库；V14.8 支持 arc 维度（mansion_era/empire_era/late_arc）。

        - 新结构（schema 2.0）：顶层按 arc 分桶，返回 {arc: {scene: {...}}}
        - 旧结构（schema 1.0）：顶层直接是场景，arc 参数忽略
        - 未知 arc / 无该 arc 数据 → 回落 mansion_era（防内容缺失崩溃）
        """
        if cls._scene_db is None:
            cls._scene_db = _load("scene_dialogue.json")
        data = cls._scene_db
        # 判断是否有 arc 维度：顶层键含 "era"/"arc" 或值为嵌套场景字典
        if any(k.endswith("_era") or k == "late_arc" for k in data.keys()):
            if arc and arc in data:
                return data[arc]
            return data.get("mansion_era", {})
        return data

    @classmethod
    def _characters(cls) -> Dict[str, Any]:
        if cls._character_db is None:
            cls._character_db = _load("character_dialogue.json")
        return cls._character_db

    @classmethod
    def _milestones(cls) -> Dict[str, Any]:
        if cls._milestone_db is None:
            cls._milestone_db = _load("milestone_lines.json")
        return cls._milestone_db

    # ── 场景切换识别 ──
    @classmethod
    def parse_scene_change(cls, user_input: str) -> Optional[str]:
        """从用户输入识别场景移动意图（「去厨房」「回房间」等）。

        返回场景键（如 "KITCHEN"），无移动意图返回 None。
        纯闲聊提到场景词（「厨房的茶很好喝」）不触发切换——要求移动动词前缀。
        """
        text = (user_input or "").strip()
        if not text:
            return None
        for kw, scene in SCENE_KEYWORDS.items():
            if kw not in text:
                continue
            idx = text.find(kw)
            prefix = text[max(0, idx - 2):idx]  # 场景词前最多 2 字
            if any(p in prefix for p in _MOVE_PREFIXES):
                return scene
        return None

    # ── 场景时段 slot ──
    @classmethod
    def _slot(cls, scene: str, period: str) -> Optional[str]:
        return _PERIOD_SLOTS.get(scene, {}).get(period)

    @classmethod
    def get_scene_opening(cls, scene: str, period: str, weather: str = "晴朗",
                          arc: Optional[str] = None) -> Optional[Dict[str, str]]:
        """场景开场（切换场景时注入一次）：{rem_view, ram_view} 或 None。

        V14.8：arc 参数按篇章取场景库（默认 mansion_era）。
        """
        scene_db = cls._scenes(arc).get(scene)
        if not scene_db:
            return None
        slot = cls._slot(scene, period)
        if not slot:
            return None
        entry = scene_db.get(slot, {}).get("opening")
        if not entry:
            return None
        return {"rem_view": entry.get("rem_view", ""), "ram_view": entry.get("ram_view", "")}

    @classmethod
    def get_scene_interaction(cls, scene: str, period: str,
                              arc: Optional[str] = None) -> Optional[Dict[str, str]]:
        """场景互动引导（每轮注入）：轮转选一条 interaction（V14.7 优化 O-4 去重）。

        原实现 random.choice——长会话同一场景下互动文案可能轮转重复；
        改用实例级轮转游标（避开上次命中的条目），减少重复观感。
        V14.8：arc 参数按篇章取场景库。
        """
        scene_db = cls._scenes(arc).get(scene)
        if not scene_db:
            return None
        slot = cls._slot(scene, period)
        if not slot:
            return None
        interactions = [v for k, v in scene_db.get(slot, {}).items()
                        if k.startswith("interaction")]
        if not interactions:
            return None
        # O-4 去重：轮转游标 + 避开上次（key 含 arc 防跨篇章串用）
        key = f"{arc or 'mansion'}|{scene}|{slot}"
        idx = cls._interaction_rotor.get(key, -1)
        candidates = [it for it in interactions if it != cls._last_interaction.get(key)]
        pool = candidates if candidates else interactions
        idx = (idx + 1) % len(pool)
        cls._interaction_rotor[key] = idx
        chosen = pool[idx]
        cls._last_interaction[key] = chosen
        return {"rem_view": chosen.get("rem_view", ""), "ram_view": chosen.get("ram_view", "")}

    # ── E4 名场面状态联动 ──
    # O-5（V14.11）：名场面语感注入的防疲劳冷却——同一名场面注入后 24h 内
    # 不再重复注入（状态持续命中时避免每轮同一语感；与场景冷却 24h 对齐）。
    MILESTONE_COOLDOWN_HOURS = 24.0

    @classmethod
    def get_milestone(cls, state: Any) -> Optional[Dict[str, Any]]:
        """按 TwinState 状态检测命中的名场面（返回 milestone dict 或 None）。

        触发优先级：鬼化 > 失忆重逢 > 忠诚锁定 > 拉姆托付 > 从零开始。
        无冷却判断（原始检测，冷却门控见 get_milestone_for_prompt）。
        """
        db = cls._milestones()
        if not db:
            return None
        if getattr(state, "oni_stage", None) is not None and getattr(state, "oni_stage", None).name != "NONE":
            return db.get("oni_release")
        recovery = float(getattr(state, "recovery", 1.0) or 1.0)
        if recovery <= 0.35:
            return db.get("memory_fragment")
        favor = float(getattr(state, "favor", 0) or 0)
        if favor >= 95:
            return db.get("loyalty_lock")
        ram_stage = getattr(state, "ram_stage", None)
        if ram_stage is not None and getattr(ram_stage, "name", "") == "ACKNOWLEDGED":
            return db.get("ram_entrust")
        if getattr(state, "wants_push", False):
            return db.get("zero_start")
        return None

    @classmethod
    def _milestone_on_cooldown(cls, world: Any, name: str) -> bool:
        cds = getattr(world, "milestone_cooldowns", None) or {}
        last = cds.get(name, "")
        if not last:
            return False
        try:
            from datetime import datetime
            elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            return elapsed < cls.MILESTONE_COOLDOWN_HOURS * 3600
        except Exception:
            return False

    @classmethod
    def get_milestone_for_prompt(cls, state: Any, world: Any) -> Optional[Dict[str, Any]]:
        """PromptBuilder 注入口：命中名场面且不在 24h 冷却内才返回（O-5）。"""
        ms = cls.get_milestone(state)
        if ms and world is not None and cls._milestone_on_cooldown(world, ms.get("name", "")):
            return None
        return ms

    @classmethod
    def consume_milestone(cls, world: Any, state: Any) -> None:
        """成功生成后由 bridge 调用：若本轮名场面可注入（未在冷却），记录冷却起点。

        冷却中被抑制的名场面不刷新冷却（标记前先复核，保持语义忠实）。
        """
        if world is None:
            return
        ms = cls.get_milestone(state)
        if not ms:
            return
        name = ms.get("name", "")
        if cls._milestone_on_cooldown(world, name):
            return
        try:
            from datetime import datetime
            if not hasattr(world, "milestone_cooldowns") or world.milestone_cooldowns is None:
                world.milestone_cooldowns = {}
            world.milestone_cooldowns[name] = datetime.now().isoformat(timespec="seconds")
        except Exception:
            pass

    # ── E3 关键人物互动 ──
    @classmethod
    def get_character_lines(cls, user_input: str) -> Optional[Dict[str, Any]]:
        """用户输入提到关键人物 → 返回 {person, rem_lines, ram_lines} 或 None。"""
        text = user_input or ""
        for kw, person in CHARACTER_KEYWORDS.items():
            if kw in text:
                entry = cls._characters().get(person)
                if entry:
                    return {"person": person,
                            "rem_lines": entry.get("rem", []),
                            "ram_lines": entry.get("ram", [])}
        return None
