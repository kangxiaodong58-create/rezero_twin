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
    PRAISE_KEYWORDS = ["谢谢", "辛苦了", "真棒", "厉害", "喜欢你", "感谢"]

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
            return self.user_name
        m = re.search(r"(?:我叫|称呼我|我的名字是)\s*([^\s,，。！?]{1,8})", text)
        if m:
            return m.group(1).strip()
        return None

    def _classify_intent(self, text: str) -> Intent:
        lowered = text.lower()
        if "从零开始" in text and any(k in text for k in ["吧", "吧！", "吧。", "啊"]):
            return Intent.FROM_ZERO
        if any(k in text for k in ["拉姆", "姐姐", "姐姐大人"]):
            return Intent.MENTION_RAM
        if any(k in text for k in ["黑化", "侮辱", "低俗", "下跪", "舔狗", "恶搞"]):
            return Intent.BOUNDARY_TEST
        if any(k in text for k in ["敌人", "危险", "袭击", "快跑", "魔兽"]):
            return Intent.DANGER
        if any(k in text for k in ["狮子王", "王国", "无名之星", "星的光芒"]):
            return Intent.WORLD_LATE
        if any(k in text for k in ["放弃", "做不到", "一无所有", "不配", "废物", "替代品"]):
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
        intent = self._classify_intent(text)
        self.profile.session.last_intent = intent

        # 高风险越界
        if any(k in text for k in self.HIGH_RISK_KEYWORDS):
            self._safe_add_favor(-12)
            self.witch_scent = min(5, self.witch_scent + 2)
            self.ram_favor = max(0, self.ram_favor - 6)
            self.profile.context.last_drop_reason = "高风险越界"

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
            self.independence = min(1.0, self.independence + 0.03)
            self.ram_favor = min(100, self.ram_favor + 1)

        # 替代品 / 姐姐比较 -> 独立度下降
        if "替代品" in text or "不如姐姐" in text:
            self.independence = max(0.0, self.independence - 0.04)
            self.profile.context.add_emotion("自卑")

        # 名字提取
        extracted_name = self._extract_name(text)
        if extracted_name and self.user_name is None:
            self.user_name = extracted_name
            self.profile.name = extracted_name
            self._safe_add_favor(4)
            self.profile.record_pattern("告知名字")

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
        )

    def set_arc(self, arc: StoryArc) -> None:
        self.arc = arc
        if arc == StoryArc.EMPIRE_ERA:
            self.recovery = 0.0
            self.independence = 0.0
            self.is_reunion = False
        else:
            self.recovery = 1.0
            self.independence = max(self.independence, 0.25)

    def recover(self, progress: float = 1.0) -> None:
        old = self.recovery
        self.recovery = max(0.0, min(1.0, progress))
        if old < 0.5 <= self.recovery:
            self.is_reunion = True
            self._safe_add_favor(8)
            self.independence = min(1.0, self.independence + 0.12)

    def mark_breaker_triggered(self) -> None:
        self.breaker_triggered = True
