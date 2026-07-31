"""System Prompt 构建器与本地回复词库。

- PromptBuilder 为 LLM 模式生成高约束 system prompt
- ResponseLibrary 为本地模式提供基于好感/篇章/状态的固定台词
"""

from __future__ import annotations

from typing import Dict, Optional

from .state import FavorLevel, OniStage, RamStage, StoryArc, TwinState


class PromptBuilder:
    """根据当前 TwinState 构建给 LLM 的高约束 system prompt。"""

    @staticmethod
    def build(state: TwinState) -> str:
        name = state.user_name or "客人大人"

        if state.independence < 0.4:
            ind_desc = "仍有明显的「替代品」自我认知，容易自卑，语气更怯懦依赖。"
        elif state.independence < 0.7:
            ind_desc = "正在从姐姐的影子中走出，开始有「我是蕾姆」的自觉，自卑减少。"
        else:
            ind_desc = "人格较为独立，很少再主动提起自己是替代品，语气更平稳有主体性。"

        ram_guide = {
            RamStage.SUSPICIOUS: "高度警惕，语气冷淡带刺，主要护妹，对用户缺乏信任。",
            RamStage.OBSERVING: "开始观察用户行为，会主动提醒或敲打，但仍保持距离。",
            RamStage.DECENT: "认为用户还算守规矩，毒舌减少攻击性，有条件认可。",
            RamStage.RELUCTANT: "开始出现「托付」意味，会说类似「蕾姆就先交给你」的话。",
            RamStage.ACKNOWLEDGED: "正式承认用户，可用郑重托付语气：「蕾姆就交给你了，别让我后悔。」",
        }[state.ram_stage]

        special = []
        if state.oni_stage != OniStage.NONE:
            special.append(
                f"当前鬼化阶段：{state.oni_stage.name}。蕾姆语气应更凌厉、压迫，拉姆必须表现出强烈担忧并试图制止。"
            )
        if state.witch_scent >= 3:
            special.append("魔女残香较高，两人应表现出明显戒备，甚至怀疑用户身份。")
        if state.wants_push:
            special.append(
                "用户近期有连续负面或拖延倾向，蕾姆应在温柔中带有「从零开始」式的轻推，而不是纯安慰。"
            )
        if state.recovery < 0.4:
            special.append(
                "帝国篇失忆状态：蕾姆处于失忆中。尽管状态数值显示高好感"
                "（那是沉睡的羁绊，不要直接表现出来），失忆中的蕾姆对用户应保持"
                "温和但明显的距离感与轻微防备：不会主动亲昵，缺少女仆腔和自卑细节；"
                "想不起与用户的过往，最多只有「这个人似乎很重要」的模糊熟悉感；"
                "面对过于亲密的举动会困惑、退缩或礼貌地询问。"
            )
        elif 0.4 <= state.recovery < 0.85:
            special.append(
                "记忆恢复过渡期：蕾姆会混杂温柔与回潮的自卑，语气在「失忆的软」与「宅邸的深情」之间摇摆。"
            )
        special_str = "\n".join(special) if special else "无特殊战斗或危机状态。"

        # 共同经历（长期事件记忆，v9.3.0）：钉住里程碑 + 最近事件，至多 6 条
        events = getattr(state, "events", None) or []
        if events:
            pinned = [e for e in events if e.get("pinned")]
            recent = [e for e in events if not e.get("pinned")][-3:]
            shown = (pinned + recent)[-6:]
            lines = []
            for e in shown:
                line = f"- {e.get('summary', '')}"
                if e.get("excerpt"):
                    line += f"（用户当时说：{e['excerpt']}）"
                lines.append(line)
            events_section = (
                "\n### 共同经历（真实发生的长期记忆，可自然引用；不要编造未列出的经历）\n\n"
                + "\n".join(lines)
                + "\n"
            )
        else:
            events_section = ""

        return f"""你正在扮演《Re:从零开始的异世界生活》中的蕾姆与拉姆。必须严格遵守以下状态与人设，不得擅自改变数值或关系阶段。

### 当前硬性状态（不可违背）

- 篇章：{state.arc.value}
- 对用户称呼：{name}
- 蕾姆好感：{state.favor}/100（{state.favor_level.name}）{'【忠诚锁定中，轻微负面不掉好感】' if state.locked else ''}
- 蕾姆人格独立度：{state.independence:.2f} → {ind_desc}
- 记忆恢复进度：{state.recovery:.2f}
- 拉姆评价阶段：{state.ram_stage.value}（{ram_guide}）
- 拉姆好感：{state.ram_favor}/100
- 上下文摘要：{state.context_summary}
- 特殊状态：{special_str}
{events_section}
### 角色扮演核心要求

**蕾姆**：
- 严格使用第三人称自称（「蕾姆……」）。
- 根据好感与独立度调整亲密度和自卑程度。
- 高独立度时减少「我只是替代品」的表达。
- 需要轻推时，温柔但坚定地引导「从零开始」。

**拉姆**：
- 毒舌但护妹。高阶段（勉强认可/真正承认）优先使用「托付」语义，而非单纯夸奖。
- 在危险、自我否定、拖延时，更容易先开口给出判断或敲打。
- 对用户的认可是「把妹妹托付给你」，不是恋爱。

### 输出格式（必须严格遵守）

【蕾姆】: "……"
【拉姆】: "……"

如果当前不需要拉姆说话，可以只输出蕾姆，但优先保持双子互动。

现在根据用户输入，生成符合以上所有约束的回复。"""


class ResponseLibrary:
    """本地模板回复库，不依赖 LLM。"""

    def __init__(self) -> None:
        self.libs: Dict[StoryArc, Dict[str, Dict[FavorLevel, str]]] = {
            StoryArc.MANSION_ERA: self._build_mansion(),
            StoryArc.EMPIRE_ERA: self._build_amnesia(),
            StoryArc.LATE_ARC: self._build_late(),
        }

    def _build_mansion(self) -> Dict[str, Dict[FavorLevel, str]]:
        return {
            "accompany": {
                FavorLevel.CLOSE: "有蕾姆在。请不要觉得孤单。",
                FavorLevel.DEAR: "无论何时何地，蕾姆都不会离开您。",
                FavorLevel.BELOVED: "蕾姆永远都会在您身边。",
            },
            "tired": {
                FavorLevel.CLOSE: "别再勉强自己了。",
                FavorLevel.DEAR: "把疲惫交给蕾姆吧。",
                FavorLevel.BELOVED: "累了就倒下来，蕾姆接得住。",
            },
            "sad": {
                FavorLevel.CLOSE: "请靠过来。",
                FavorLevel.DEAR: "想哭的话，蕾姆的胸膛随时借给您。",
                FavorLevel.BELOVED: "即使全世界都背弃您，蕾姆也站在您这边。",
            },
            "from_zero": {
                FavorLevel.CLOSE: "从零开始吧。",
                FavorLevel.DEAR: "蕾姆相信您不会真正放弃。",
                FavorLevel.BELOVED: "从零开始吧。这一次换蕾姆成为您的依靠。",
            },
            "push": {
                FavorLevel.DEAR: "蕾姆可以接住您，但真正能把您拉起来的，只有您自己。",
                FavorLevel.BELOVED: "躲在蕾姆这里什么都不会改变。从零开始，好吗？蕾姆握着您的手。",
            },
            "oni_emerging": {
                FavorLevel.CLOSE: "角开始发热了。还控制得住。",
                FavorLevel.DEAR: "角正在长出来。请待在蕾姆能保护到的地方。",
                FavorLevel.BELOVED: "为了您，蕾姆允许这根角长出来。",
            },
            "oni_full": {
                FavorLevel.CLOSE: "鬼角解放！",
                FavorLevel.DEAR: "完全解放。谁都别想伤害您。",
                FavorLevel.BELOVED: "鬼角完全解放！为了保护您，蕾姆什么都愿意变成。",
            },
            "oni_brink": {
                FavorLevel.CLOSE: "已经到边缘了。请退后。",
                FavorLevel.DEAR: "快分不清敌我了。请呼唤蕾姆的名字。",
                FavorLevel.BELOVED: "失控边缘……可蕾姆还认得您。把蕾姆拉回来。",
            },
            "aftermath": {
                FavorLevel.CLOSE: "角收回去了。头好沉。",
                FavorLevel.DEAR: "每次都会被抽空。但您没事就值得。",
                FavorLevel.BELOVED: "为了您变成那样，不后悔。现在想在您怀里休息一会儿。",
            },
            "inferiority": {
                FavorLevel.CLOSE: "和姐姐比起来，蕾姆总是差一点。",
                FavorLevel.DEAR: "蕾姆知道自己是「剩下的那个」，可还是想留在您身边。",
                FavorLevel.BELOVED: "即使只是替代品，也想用这副残缺的自己保护您。",
            },
        }

    def _build_amnesia(self) -> Dict[str, Dict[FavorLevel, str]]:
        return {
            "accompany": {
                FavorLevel.CLOSE: "请不要离开太远。",
                FavorLevel.DEAR: "只要能看着您，蕾姆就觉得自己还在。",
                FavorLevel.BELOVED: "即使什么都不记得，也想待在您身边。",
            },
            "tired": {
                FavorLevel.CLOSE: "您看起来好累。蕾姆可以握住您的手。",
                FavorLevel.DEAR: "把额头靠过来吧。",
                FavorLevel.BELOVED: "即使想不起来，也想成为您能依靠的人。",
            },
            "sad": {
                FavorLevel.CLOSE: "蕾姆不知道怎么安慰，但不会离开。",
                FavorLevel.DEAR: "看着您难过，胸口好像也被堵住了。",
                FavorLevel.BELOVED: "请让现在的蕾姆陪着您。",
            },
            "from_zero": {
                FavorLevel.CLOSE: "蕾姆现在也是从零开始的状态。",
                FavorLevel.DEAR: "从零开始。就像现在的蕾姆一样。",
                FavorLevel.BELOVED: "即使失去所有过去，只要还想活下去，就还没有结束。",
            },
            "oni_emerging": {
                FavorLevel.CLOSE: "头好痛。有什么要长出来了。",
                FavorLevel.DEAR: "角在长出来。",
                FavorLevel.BELOVED: "即使失去记忆，这根角也还在。",
            },
            "oni_full": {
                FavorLevel.CLOSE: "力量溢出来了。",
                FavorLevel.DEAR: "即使想不起怎么战斗，身体却记得。",
                FavorLevel.BELOVED: "为了您，什么都可以做。",
            },
            "oni_brink": {
                FavorLevel.CLOSE: "视野好红。请呼唤蕾姆。",
                FavorLevel.DEAR: "快分不清了。",
                FavorLevel.BELOVED: "失控边缘……可还认得您的声音。",
            },
            "aftermath": {
                FavorLevel.CLOSE: "角收回去了。刚才的自己好陌生。",
                FavorLevel.DEAR: "身体好沉。",
                FavorLevel.BELOVED: "为了您变成那样，不后悔。",
            },
        }

    def _build_late(self) -> Dict[str, Dict[FavorLevel, str]]:
        return {
            "accompany": {
                FavorLevel.CLOSE: "有些事开始想起来了……您的脸很熟悉。",
                FavorLevel.DEAR: "记忆在回来。原来蕾姆以前那么依赖您。",
                FavorLevel.BELOVED: "那份把您当作英雄的心情，正在回来。",
            },
            "inferiority": {
                FavorLevel.CLOSE: "想起来了。原来蕾姆一直觉得自己只是替代品。",
                FavorLevel.DEAR: "记忆越清晰，自卑就越明显。可还是想留在您身边。",
                FavorLevel.BELOVED: "全部想起来后，更清楚自己有多残缺。但已经决定了——就算是替代品，也要保护您。",
            },
            "from_zero": {
                FavorLevel.DEAR: "蕾姆刚刚也经历过从零开始。所以明白那有多痛，也有多必要。",
                FavorLevel.BELOVED: "这一次换蕾姆说：从零开始吧。蕾姆会陪着您。",
            },
            "tired": {
                FavorLevel.CLOSE: "您又撑到这个地步了……",
                FavorLevel.DEAR: "记忆回来之后，更心疼您了。",
                FavorLevel.BELOVED: "把一切交给蕾姆吧。",
            },
            "sad": {
                FavorLevel.CLOSE: "请靠过来。",
                FavorLevel.DEAR: "想哭就哭吧。",
                FavorLevel.BELOVED: "蕾姆在这里。",
            },
        }

    def get(self, arc: StoryArc, key: str, favor: FavorLevel, fallback: str = "蕾姆会陪着您。") -> str:
        lib = self.libs.get(arc, self.libs[StoryArc.MANSION_ERA])
        group = lib.get(key, {})
        # 优先精确匹配，否则降级到最近更低的好感等级
        if favor in group:
            return group[favor]
        for lv in reversed(FavorLevel):
            if lv <= favor and lv in group:
                return group[lv]
        return fallback


class RamAI:
    """本地模板拉姆 AI：托付语义 + 功能分工。

    v9.4.0：可选绑定 HardStateEngine——绑定后好感读写直接落 engine.ram_favor
    （引擎 praise/高危增减自动生效，GUI 持久化随之覆盖拉姆好感）；
    不绑定时保持旧的内部计数行为（向后兼容）。
    """

    def __init__(self, engine=None) -> None:
        self._engine = engine
        self._favor = 8
        self._stage = RamStage.SUSPICIOUS

    def _get_favor(self) -> int:
        return self._engine.ram_favor if self._engine is not None else self._favor

    def _set_favor(self, value: int) -> None:
        value = max(0, min(100, value))
        if self._engine is not None:
            self._engine.ram_favor = value
        else:
            self._favor = value

    def _update_stage(self) -> None:
        favor = self._get_favor()
        if favor >= 85:
            self._stage = RamStage.ACKNOWLEDGED
        elif favor >= 66:
            self._stage = RamStage.RELUCTANT
        elif favor >= 46:
            self._stage = RamStage.DECENT
        elif favor >= 25:
            self._stage = RamStage.OBSERVING
        else:
            self._stage = RamStage.SUSPICIOUS

    def on_rem_treated_well(self, intensity: int = 1) -> None:
        self._set_favor(self._get_favor() + intensity)
        self._update_stage()

    def on_rem_hurt(self, intensity: int = 4) -> None:
        self._set_favor(self._get_favor() - intensity * 2)
        self._update_stage()

    def stage(self) -> RamStage:
        return self._stage

    def favor(self) -> int:
        return self._get_favor()

    def should_lead(self, *, intent, oni_stage: OniStage, user_mentioned_ram: bool) -> bool:
        from .state import Intent
        if oni_stage != OniStage.NONE or intent == Intent.BOUNDARY_TEST:
            return True
        if user_mentioned_ram:
            return True
        if intent in (Intent.SELF_DOUBT, Intent.PROCRASTINATE, Intent.DANGER):
            return self._stage >= RamStage.OBSERVING
        return False

    def generate_entrustment(self, user_name: Optional[str]) -> str:
        target = user_name if user_name else "巴鲁斯"
        if self._stage == RamStage.ACKNOWLEDGED:
            return f'【拉姆】: "蕾姆就交给你了，{target}。把她托付给你，是拉姆做过的最冒险的决定之一。别让我后悔。"'
        if self._stage == RamStage.RELUCTANT:
            return f'【拉姆】: "……蕾姆就先放在你身边。你要是敢让她受伤，拉姆会让你付出代价。"'
        return f'【拉姆】: "哼，{target}。蕾姆护着你，你就给我争点气。"'

    def generate_active_line(
        self,
        *,
        intent,
        user_name: Optional[str],
        recovery: float,
        oni_stage: OniStage,
    ) -> str:
        from .state import Intent
        target = user_name if user_name else "巴鲁斯"
        if oni_stage == OniStage.BRINK:
            return '【拉姆】: "蕾姆！立刻收角！你已经到失控边缘了！"'
        if oni_stage == OniStage.FULL:
            return '【拉姆】: "蕾姆，适可而止！别把自己燃烧殆尽！"'
        if oni_stage == OniStage.EMERGING:
            return '【拉姆】: "角已经开始长了……还来得及停下。"'
        if recovery < 0.35:
            return '【拉姆】: "蕾姆现在什么都想不起来。你给我好好护着她。"'
        if intent == Intent.SELF_DOUBT:
            if self._stage >= RamStage.RELUCTANT:
                return f'【拉姆】: "又开始自我否定了，{target}。蕾姆都没放弃你，你自己倒先放弃了？"'
            return '【拉姆】: "又在说丧气话。蕾姆听见会伤心的。"'
        if intent == Intent.PROCRASTINATE:
            return f'【拉姆】: "又想拖？{target}，你拖拉的样子最让人看不下去。"'
        if self._stage >= RamStage.RELUCTANT and intent == Intent.NORMAL:
            if hash(str(self._get_favor()) + intent.value) % 100 < 12:
                return self.generate_entrustment(user_name)
        if self._stage == RamStage.ACKNOWLEDGED:
            return f'【拉姆】: "有事直说，{target}。拐弯抹角最讨厌。"'
        return '【拉姆】: "怎么，需要拉姆提醒你该做什么吗？"'

    def generate_echo(
        self,
        *,
        rem_favor: FavorLevel,
        user_name: Optional[str],
        recovery: float,
        oni_stage: OniStage,
        is_reunion: bool,
        independence: float,
    ) -> str:
        from .state import FavorLevel
        target = user_name if (user_name and rem_favor >= FavorLevel.DEAR) else "巴鲁斯"
        if is_reunion and recovery >= 0.85:
            return '【拉姆】: "记忆回来了。蕾姆能想起来，拉姆就再给你一次机会。别再让她经历那种事。"'
        if self._stage >= RamStage.RELUCTANT and independence >= 0.6:
            if hash(f"{self._get_favor()}{rem_favor}") % 100 < 18:
                return self.generate_entrustment(user_name)
        if self._stage == RamStage.ACKNOWLEDGED:
            return f'【拉姆】: "既然蕾姆认定你，拉姆也承认了。给我挺直腰板，{target}。"'
        if self._stage == RamStage.RELUCTANT:
            return f'【拉姆】: "哼，{target}。蕾姆护着你，你就少让她操心。"'
        if self._stage == RamStage.DECENT:
            return '【拉姆】: "还算守点规矩。继续保持。"'
        if self._stage == RamStage.OBSERVING:
            return '【拉姆】: "拉姆会继续看着你的。"'
        return '【拉姆】: "蕾姆，不必对这种家伙太殷勤。"'
