"""本地蕾姆回复生成器（基于模板词库）。"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Tuple

from shared.state import FavorLevel, HardStateEngine, Intent, OniStage, StoryArc, TwinState
from shared.prompts import ResponseLibrary


class RemAI:
    """本地模板蕾姆 AI，基于状态机选择回复模板。"""

    def __init__(self, arc: StoryArc = StoryArc.MANSION_ERA) -> None:
        self._arc = arc
        self._recovery = 1.0 if arc != StoryArc.EMPIRE_ERA else 0.0
        self._favor = 15
        self._locked = False
        self._independence = 0.25 if arc != StoryArc.EMPIRE_ERA else 0.0
        self._oni_stage = OniStage.NONE
        self._oni_aftermath = 0
        self._short_memory: deque = deque(maxlen=14)
        self.profile: Dict = {"name": None, "context": []}
        self._is_reunion = False
        self._breaker_triggered = False
        self._libs = ResponseLibrary()
        self.engine = HardStateEngine(arc=arc)
        self._last_intent: Optional[Intent] = None

    def _get_favor_level(self) -> FavorLevel:
        if self._favor >= 95:
            return FavorLevel.BELOVED
        if self._favor >= 80:
            return FavorLevel.DEAR
        if self._favor >= 50:
            return FavorLevel.CLOSE
        if self._favor >= 20:
            return FavorLevel.FAMILIAR
        return FavorLevel.STRANGER

    def _sync_from_engine(self, state: TwinState) -> None:
        self._favor = state.favor
        self._locked = state.locked
        self._independence = state.independence
        self._recovery = state.recovery
        self._oni_stage = state.oni_stage
        self._is_reunion = state.is_reunion
        self._breaker_triggered = state.breaker_triggered
        self.profile["name"] = state.user_name

    def _build_address(self, favor: FavorLevel) -> str:
        name = self.profile.get("name")
        if self._recovery < 0.35:
            return name if (name and favor >= FavorLevel.CLOSE) else "您"
        if not name:
            return "客人大人" if favor <= FavorLevel.STRANGER else ("昴君" if favor <= FavorLevel.CLOSE else "蕾姆的英雄")
        return name if favor >= FavorLevel.CLOSE else f"{name}大人"

    def generate(self, user_input: str) -> Tuple[str, Intent, OniStage]:
        state = self.engine.update(user_input)
        self._sync_from_engine(state)

        # 高风险越界已经在 engine 中处理，这里只需要读取状态生成文案
        intent = self.engine._classify_intent(user_input)
        self._last_intent = intent
        favor = self._get_favor_level()
        address = self._build_address(favor)

        # 破局者彩蛋
        if (
            not self._breaker_triggered
            and self._independence >= 0.75
            and favor >= FavorLevel.BELOVED
            and self._locked
            and intent in (Intent.NORMAL, Intent.FROM_ZERO)
        ):
            if hash(user_input + str(self._favor)) % 100 < 8:
                self.engine.mark_breaker_triggered()
                self._breaker_triggered = True
                reply = (
                    "【蕾姆】: "
                    '"以前的蕾姆，一直活在姐姐的影子里。是您……把蕾姆从那个封闭的世界里拉了出来。谢谢您，成为了蕾姆的破局者。"'
                )
                self._short_memory.append((user_input, reply))
                return reply, intent, OniStage.NONE

        # 鬼化
        if intent == Intent.DANGER or any(k in user_input for k in ["解放鬼角", "鬼化", "角解放", "变成鬼", "失控"]):
            key = {1: "oni_emerging", 2: "oni_full", 3: "oni_brink"}[self._oni_stage]
            raw = self._libs.get(self._arc, key, favor, fallback="鬼角……")
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, self._oni_stage

        # 鬼化余韵
        if self._oni_aftermath > 0:
            self._oni_aftermath -= 1
            if self._oni_aftermath == 0:
                self._oni_stage = OniStage.NONE
            raw = self._libs.get(self._arc, "aftermath", favor, fallback="角已经收回去了……")
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, self._oni_stage

        # 从零开始
        if intent == Intent.FROM_ZERO:
            raw = self._libs.get(self._arc, "from_zero", favor, fallback="从零开始吧。")
            if self._independence >= 0.6:
                raw = "从零开始吧。这一次，蕾姆不是作为替代品，而是作为蕾姆自己，站在您身边。"
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, OniStage.NONE

        # 轻推
        if state.wants_push:
            if state.consecutive_negative >= 3:
                raw = (
                    "蕾姆知道您现在很难迈出下一步。可一直躲下去，什么都不会改变。从零开始……"
                    "蕾姆握着您的手，一起迈出去，好吗？"
                )
            else:
                raw = self._libs.get(self._arc, "push", favor, fallback="从零开始吧。")
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, OniStage.NONE

        # 常规
        if intent == Intent.SELF_DOUBT or ("替代" in user_input and self._independence < 0.5):
            key = "inferiority" if self._independence < 0.55 else "from_zero"
        elif intent == Intent.VENT:
            key = "tired" if self.engine.profile.session.recent_mood == "tired" else "sad"
        else:
            key = "accompany"

        raw = self._libs.get(self._arc, key, favor, fallback="蕾姆会陪着您。")
        if self._independence >= 0.75 and key == "accompany" and favor >= FavorLevel.DEAR:
            raw = "蕾姆在这里。不是作为谁的替代，而是作为蕾姆自己。"
        reply = f'【蕾姆】: "{raw}"'
        self._short_memory.append((user_input, reply))
        return reply, intent, self._oni_stage

    def set_arc(self, arc: StoryArc) -> None:
        self._arc = arc
        self.engine.set_arc(arc)
        self._sync_from_engine(self.engine.update(""))

    def recover(self, progress: float = 1.0) -> str:
        self.engine.recover(progress)
        self._recovery = self.engine.recovery
        if self.engine.is_reunion:
            self._is_reunion = True
        if self._recovery >= 0.95:
            return '【蕾姆】: "全部想起来了。姐姐大人、宅邸、还有您。蕾姆的英雄。"'
        if self._recovery >= 0.6:
            return '【蕾姆】: "有更多画面回来了。您的脸……蕾姆以前一定很珍惜您。"'
        return '【蕾姆】: "好像有什么东西正在一点点回来……"'
