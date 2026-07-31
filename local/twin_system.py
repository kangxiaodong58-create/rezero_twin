"""本地双子总控系统（模板模式）。"""

from __future__ import annotations

from shared.state import FavorLevel, HardStateEngine, Intent, OniStage, RamStage, StoryArc
from shared.prompts import RamAI
from .rem_ai import RemAI


class ReZeroTwinSystem:
    """拉姆 + 蕾姆本地模板协同系统。"""

    def __init__(self, arc: StoryArc = StoryArc.MANSION_ERA) -> None:
        self.rem = RemAI(arc=arc)
        self.ram = RamAI()
        self.twin_enabled = True

    def set_arc(self, arc: StoryArc) -> None:
        self.rem.set_arc(arc)

    def recover(self, progress: float = 1.0) -> str:
        return self.rem.recover(progress)

    def interact(self, user_input: str) -> str:
        rem_reply, intent, oni_stage = self.rem.generate(user_input)

        if intent != Intent.BOUNDARY_TEST:
            self.ram.on_rem_treated_well(1)
        else:
            self.ram.on_rem_hurt(3)

        if not self.twin_enabled:
            return rem_reply

        favor = self.rem._get_favor_level()
        recovery = self.rem._recovery
        independence = self.rem._independence
        is_reunion = self.rem._is_reunion
        user_mentioned_ram = intent == Intent.MENTION_RAM
        user_name = self.rem.profile.get("name")

        ram_leads = self.ram.should_lead(
            intent=intent,
            oni_stage=oni_stage,
            user_mentioned_ram=user_mentioned_ram,
        )
        if ram_leads:
            ram_line = self.ram.generate_active_line(
                intent=intent,
                user_name=user_name,
                recovery=recovery,
                oni_stage=oni_stage,
            )
            return f"{ram_line}\n{rem_reply}"

        if (
            oni_stage != OniStage.NONE
            or intent in (Intent.DANGER, Intent.BOUNDARY_TEST, Intent.FROM_ZERO)
            or user_mentioned_ram
            or is_reunion
            or favor >= FavorLevel.CLOSE
            or independence >= 0.6
        ):
            ram_line = self.ram.generate_echo(
                rem_favor=favor,
                user_name=user_name,
                recovery=recovery,
                oni_stage=oni_stage,
                is_reunion=is_reunion,
                independence=independence,
            )
            return f"{rem_reply}\n{ram_line}"

        return rem_reply

    def status(self) -> str:
        f = self.rem._get_favor_level()
        return f"""
===== Re:Zero 双子系统（本地模板模式）=====
篇章: {self.rem._arc.value}
记忆恢复: {self.rem._recovery:.2f}
蕾姆好感: {self.rem._favor}/100 ({f.name}) {'[忠诚锁定]' if self.rem._locked else ''}
蕾姆人格独立度: {self.rem._independence:.2f}
拉姆 {self.ram.favor()}/100 | 阶段：{self.ram.stage().value}
鬼化: {self.rem._oni_stage.name} | 余韵: {self.rem._oni_aftermath}
破局者彩蛋: {'已触发' if self.rem._breaker_triggered else '未触发'}
上下文: {self.rem.engine.profile.context.brief()}
用户画像: {self.rem.engine.profile.get_summary()}
""".strip()
