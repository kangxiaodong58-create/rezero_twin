"""本地蕾姆回复生成器（基于模板词库）。

v9.4.0：状态字段全部镜像至 HardStateEngine（唯一真源），删除手动同步；
鬼化余韵死代码修复——余韵计数由引擎统一管理，
RemAI 按「上一回合是否处于鬼化」判定是否输出余韵台词。
"""

from __future__ import annotations

import hashlib
import random
from collections import deque
from typing import Dict, List, Optional, Tuple

from shared.state import FavorLevel, HardStateEngine, Intent, OniStage, StoryArc, TwinState
from shared.prompts import ResponseLibrary


class RemAI:
    """本地模板蕾姆 AI，基于状态机选择回复模板。

    V14.4 S-01 架构升级（用户提议的「关系阶段人格策略」层）：
      用户输入 → 意图识别 → 关系阶段判断 → 人格策略 → 回复生成
    关系阶段 = 好感档位（STRANGER/FAMILIAR/CLOSE/DEAR/BELOVED）；
    人格策略 = 按阶段选文案池 + 去重选择（连续轮次不重复同一句）。
    """

    def __init__(self, arc: StoryArc = StoryArc.MANSION_ERA) -> None:
        self._short_memory: deque = deque(maxlen=14)
        self.profile: Dict = {"name": None, "context": []}
        self._libs = ResponseLibrary()
        self.engine = HardStateEngine(arc=arc)
        self._last_intent: Optional[Intent] = None
        # 上一回合的鬼化阶段（余韵判定用，v9.4.0）
        self._prev_oni_stage = OniStage.NONE
        # V14.4 S-01：文案使用记录（句子 → 最近使用次序，池内 LRU 去重）
        self._pool_usage: Dict[str, int] = {}
        self._usage_clock = 0
        # V14.4 A-01：边界试探分级计数（首次温和/二次理解/三次严肃+关系下降）
        self._boundary_count = 0

    def _pick(self, pool: List[str], fallback: str, seed_text: str = "") -> str:
        """从文案池选择：池内 LRU（最久未用优先）+ 输入哈希定起始槽。

        V14.4 S-01：「输入≠输出变化」用输入特征哈希 + 池内最久未用句落地——
        不同输入优先选不同的、久未使用的句子，同一输入稳定映射到同一起始槽。
        池空回落 fallback。
        """
        if not pool:
            return fallback
        if len(pool) == 1:
            self._mark_used(pool[0])
            return pool[0]
        # 候选：优先「从未用过」或「最久未用」的句子
        def last_used(t: str) -> int:
            return self._pool_usage.get(t, -1)
        if seed_text:
            h = int(hashlib.md5(seed_text.strip().encode("utf-8")).hexdigest(), 16) % len(pool)
            # 从起始槽附近开始找最久未用句（保持输入相关性，同时分散）
            ordered = sorted(pool, key=lambda t: (last_used(t), abs(pool.index(t) - h) % len(pool)))
        else:
            ordered = sorted(pool, key=last_used)
        chosen = ordered[0]
        self._mark_used(chosen)
        return chosen

    def _mark_used(self, text: str) -> None:
        self._usage_clock += 1
        self._pool_usage[text] = self._usage_clock

    # ---- 状态镜像：唯一真源是 self.engine（v9.4.0）----
    @property
    def _arc(self) -> StoryArc:
        return self.engine.arc

    @property
    def _favor(self) -> int:
        return self.engine.favor

    @property
    def _locked(self) -> bool:
        return self.engine.locked

    @property
    def _independence(self) -> float:
        return self.engine.independence

    @property
    def _recovery(self) -> float:
        return self.engine.recovery

    @property
    def _oni_stage(self) -> OniStage:
        return self.engine.oni_stage

    @property
    def _oni_aftermath(self) -> int:
        return self.engine.oni_aftermath

    @property
    def _is_reunion(self) -> bool:
        return self.engine.is_reunion

    @property
    def _breaker_triggered(self) -> bool:
        return self.engine.breaker_triggered

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

    def _build_address(self, favor: FavorLevel) -> str:
        name = self.profile.get("name")
        if self._recovery < 0.35:
            return name if (name and favor >= FavorLevel.CLOSE) else "您"
        if not name:
            return "客人大人" if favor <= FavorLevel.STRANGER else ("昴君" if favor <= FavorLevel.CLOSE else "蕾姆的英雄")
        return name if favor >= FavorLevel.CLOSE else f"{name}大人"

    def generate(self, user_input: str) -> Tuple[str, Intent, OniStage]:
        prev_oni = self._prev_oni_stage
        state = self.engine.update(user_input)
        self._prev_oni_stage = state.oni_stage
        self.profile["name"] = state.user_name

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
                reply = (
                    "【蕾姆】: "
                    '"以前的蕾姆，一直活在姐姐的影子里。是您……把蕾姆从那个封闭的世界里拉了出来。谢谢您，成为了蕾姆的破局者。"'
                )
                self._short_memory.append((user_input, reply))
                return reply, intent, OniStage.NONE

        # 鬼化
        if intent == Intent.DANGER or any(k in user_input for k in ["解放鬼角", "鬼化", "角解放", "变成鬼", "失控"]):
            key = {1: "oni_emerging", 2: "oni_full", 3: "oni_brink"}[self._oni_stage]
            raw = self._pick(self._libs.get_pool(self._arc, key, favor), "鬼角……", user_input)
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, self._oni_stage

        # 鬼化余韵（v9.4.0 修复：上一回合处于鬼化则本回合进入余韵，计数由引擎管理）
        if prev_oni != OniStage.NONE:
            raw = self._pick(self._libs.get_pool(self._arc, "aftermath", favor), "角已经收回去了……", user_input)
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, self._oni_stage

        # 从零开始
        if intent == Intent.FROM_ZERO:
            raw = self._pick(self._libs.get_pool(self._arc, "from_zero", favor), "从零开始吧。", user_input)
            if self._independence >= 0.6:
                raw = "从零开始吧。这一次，蕾姆不是作为替代品，而是作为蕾姆自己，站在您身边。"
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, OniStage.NONE

        # V14.4 A-01：边界试探分级回应（用户提议：不是机械扣分，而是像角色一样有情绪梯度）
        if intent == Intent.BOUNDARY_TEST:
            self._boundary_count += 1
            n = self._boundary_count
            if n == 1:
                raw = "蕾姆……有点难过。是蕾姆做错了什么吗？还是您今天心情不好？"
            elif n == 2:
                raw = "如果您只是想测试蕾姆的反应，蕾姆理解。但希望您不要真的伤害彼此。"
            else:
                # 第三次起：严肃表态 + 关系下降（-6，比单次 -3 更重，体现「容忍有限度」）
                self.engine._safe_add_favor(-6)
                raw = "蕾姆可以忍耐一次两次，但不会无限容忍。如果您讨厌蕾姆，直说就好，不必用这种方式。"
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
                raw = self._pick(self._libs.get_pool(self._arc, "push", favor), "从零开始吧。", user_input)
            reply = f'【蕾姆】: "{raw}"'
            self._short_memory.append((user_input, reply))
            return reply, intent, OniStage.NONE

        # 常规
        if intent == Intent.SELF_DOUBT or ("替代" in user_input and self._independence < 0.5):
            key = "inferiority" if self._independence < 0.55 else "from_zero"
        elif intent == Intent.VENT:
            key = "tired" if self.engine.profile.session.recent_mood == "tired" else "sad"
        elif intent == Intent.QUICK:
            # V14.4 S-01：人格策略细分——问候/问身份/问天气独立成池，
            # 让「输入≠输出变化」（用户提议的关系阶段人格策略层落地）。
            if any(k in user_input for k in ["你好", "您好", "早安", "午安", "晚安", "哈喽", "嗨", "hello", "hi"]):
                key = "greet"
            elif any(k in user_input for k in ["你是谁", "你叫什么", "名字", "介绍一下", "自我"]):
                key = "introduce"
            elif any(k in user_input for k in ["天气", "下雨", "晴天", "冷", "热", "风"]):
                key = "weather"
            else:
                key = "accompany"
        else:
            key = "accompany"

        # V14.4 S-01：关系阶段人格策略——按好感档位取文案池 + 去重选择。
        # 独立度≥0.75 且 DEAR+ 的 accompany 高光句保持（既有语义）。
        if self._independence >= 0.75 and key == "accompany" and favor >= FavorLevel.DEAR:
            raw = "蕾姆在这里。不是作为谁的替代，而是作为蕾姆自己。"
        else:
            pool = self._libs.get_pool(self._arc, key, favor)
            raw = self._pick(pool, "蕾姆会陪着您。", user_input)
        reply = f'【蕾姆】: "{raw}"'
        self._short_memory.append((user_input, reply))
        return reply, intent, self._oni_stage

    def set_arc(self, arc: StoryArc) -> None:
        self.engine.set_arc(arc)

    def recover(self, progress: float = 1.0) -> str:
        self.engine.recover(progress)
        if self._recovery >= 0.95:
            return '【蕾姆】: "全部想起来了。姐姐大人、宅邸、还有您。蕾姆的英雄。"'
        if self._recovery >= 0.6:
            return '【蕾姆】: "有更多画面回来了。您的脸……蕾姆以前一定很珍惜您。"'
        return '【蕾姆】: "好像有什么东西正在一点点回来……"'
