"""Re:Zero 双子系统冒烟测试（无框架，直接运行）。

用法：
    python tests/smoke_test.py

覆盖核心回归（不调用 LLM、不产生 API 费用）：
1. 硬状态引擎：好感增减与风控关键词
2. 篇章切换（宅邸 / 帝国）
3. 记忆恢复与重逢逻辑
4. snapshot() 只读无副作用
5. MemoryStore 读写与默认值（临时目录隔离，不碰真实 data/）
6. PromptBuilder 输出包含关键约束字段
7. 本地模板模式一轮对话
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback

# 项目根目录加入搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.state import FavorLevel, HardStateEngine, OniStage, StoryArc  # noqa: E402
from shared.prompts import PromptBuilder  # noqa: E402
from shared.memory_store import MemoryStore  # noqa: E402
from local import ReZeroTwinSystem  # noqa: E402


def test_engine_favor_and_risk() -> None:
    """好感增加（表扬）与高风险扣分。"""
    engine = HardStateEngine()
    s = engine.update("谢谢你，辛苦了")
    assert s.favor == 17, f"表扬后好感应为 17，实际 {s.favor}"
    s = engine.update("黑化吧")
    assert s.favor == 5, f"高风险后好感应为 5，实际 {s.favor}"
    assert s.witch_scent == 2, f"魔女残香应为 2，实际 {s.witch_scent}"


def test_arc_switch() -> None:
    """篇章切换：帝国篇失忆，宅邸篇恢复。"""
    engine = HardStateEngine()
    engine.set_arc(StoryArc.EMPIRE_ERA)
    assert engine.recovery == 0.0 and engine.independence == 0.0
    engine.set_arc(StoryArc.MANSION_ERA)
    assert engine.recovery == 1.0 and engine.independence >= 0.25


def test_recover_reunion() -> None:
    """帝国篇恢复记忆触发重逢奖励。"""
    engine = HardStateEngine(arc=StoryArc.EMPIRE_ERA)
    engine.recover(0.7)
    assert engine.is_reunion, "恢复到 0.7 应触发重逢"
    assert engine.favor == 23, f"重逢应 +8 好感（15+8=23），实际 {engine.favor}"
    assert abs(engine.independence - 0.12) < 1e-9


def test_snapshot_no_side_effect() -> None:
    """snapshot() 不推进状态机。"""
    engine = HardStateEngine()
    engine.update("危险！有魔兽袭击！快跑！")
    stage, aftermath = engine.oni_stage, engine.oni_aftermath
    assert stage != OniStage.NONE
    for _ in range(3):
        engine.snapshot()
    assert engine.oni_stage == stage and engine.oni_aftermath == aftermath, \
        "snapshot() 产生了副作用"


def test_memory_store() -> None:
    """MemoryStore 默认值与读写（临时目录隔离）。"""
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(tmp)
        mem = store.load()
        assert mem["mode"] == "llm" and mem["favor"] == 15 and mem["chat_history"] == []
        store.set("favor", 42)
        store.append_chat("你", "测试消息")
        store2 = MemoryStore(tmp)  # 模拟重开
        assert store2.get("favor") == 42
        history = store2.get("chat_history", [])
        assert len(history) == 1 and history[0]["content"] == "测试消息"


def test_prompt_builder() -> None:
    """PromptBuilder 输出包含关键约束字段。"""
    state = HardStateEngine().snapshot()
    prompt = PromptBuilder.build(state)
    for key in ("好感", "拉姆", "【蕾姆】", "输出格式"):
        assert key in prompt, f"Prompt 缺少关键字段: {key}"
    assert state.favor_level == FavorLevel.STRANGER


def test_keyword_judgment_v926() -> None:
    """v9.2.6：肯定句识别与正面反馈词扩充。"""
    # 肯定句「你不是替代品」→ 独立度上升
    e = HardStateEngine()
    base = e.independence
    e.update("蕾姆，你不是任何人的替代品。你就是你。")
    assert e.independence > base, f"肯定句应提升独立度: {base} -> {e.independence}"
    # 攻击句「你只是替代品」→ 独立度下降（旧行为保持）
    e2 = HardStateEngine()
    base2 = e2.independence
    e2.update("你只是拉姆的替代品。")
    assert e2.independence < base2, f"攻击句应降低独立度: {base2} -> {e2.independence}"
    # 表扬变体「辛苦你们了」→ +2
    e3 = HardStateEngine()
    e3.update("早餐很丰盛，辛苦你们了。")
    assert e3.favor == 17, f"「辛苦你们了」应 +2，实际 {e3.favor}"
    # 否定温情词「不太开心」→ 不加分
    e4 = HardStateEngine()
    e4.update("我今天不太开心。")
    assert e4.favor == 15, f"否定句不应加分，实际 {e4.favor}"
    # 温情档「有你们……幸福」→ +1
    e5 = HardStateEngine()
    e5.update("有你们在身边，真的很幸福。")
    assert e5.favor == 16, f"温情档应 +1，实际 {e5.favor}"


def test_amnesia_prompt_v927() -> None:
    """v9.2.7：失忆篇 prompt 含防备/距离指令，正常篇章不含。"""
    from shared.state import TwinState
    amnesia = PromptBuilder.build(TwinState(recovery=0.0, arc=StoryArc.EMPIRE_ERA))
    assert "防备" in amnesia and "距离感" in amnesia, "失忆 prompt 缺少防备/距离指令"
    assert "沉睡的羁绊" in amnesia, "失忆 prompt 缺少数值-行为分离说明"
    normal = PromptBuilder.build(TwinState(recovery=1.0, arc=StoryArc.MANSION_ERA))
    assert "防备" not in normal, "正常篇章 prompt 不应含失忆防备指令"


def test_event_memory_v930() -> None:
    """v9.3.0：长期事件记忆——记录、钉住淘汰、prompt 注入、持久化。"""
    from shared.state import TwinState
    # 首次告知名字 → name_first 事件
    e = HardStateEngine()
    e.update("我叫小东，以后请多指教。")
    assert any(ev["type"] == "name_first" and "小东" in ev["summary"] for ev in e.events), \
        f"未记录名字事件: {e.events}"
    # 好感等级跃迁 → favor_up 事件
    e2 = HardStateEngine()
    e2.favor = 19
    e2.update("谢谢你")
    assert any(ev["type"] == "favor_up" for ev in e2.events), "未记录好感跃迁事件"
    # 肯定句 → affirm 事件
    e3 = HardStateEngine()
    e3.update("你不是任何人的替代品。")
    assert any(ev["type"] == "affirm" for ev in e3.events), "未记录肯定事件"
    # 容量与钉住：name_first 钉住，30 条上限
    e4 = HardStateEngine()
    e4.update("我叫小东。")
    for _ in range(35):
        e4.update("黑化吧")
    assert len(e4.events) <= 30, f"超出容量上限: {len(e4.events)}"
    assert any(ev["type"] == "name_first" for ev in e4.events), "钉住事件被误淘汰"
    # prompt 注入：有事件出现「共同经历」，无事件不出现
    p = PromptBuilder.build(TwinState(events=e.events))
    assert "共同经历" in p and "小东" in p, "prompt 未注入共同经历"
    p2 = PromptBuilder.build(TwinState())
    assert "共同经历" not in p2, "空事件不应出现共同经历小节"
    # 持久化：events + user_name 经 MemoryStore 跨重开保留
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(tmp)
        store.set("events", e.events)
        store.set("user_name", e.user_name)
        store2 = MemoryStore(tmp)
        evs = store2.get("events")
        assert evs and evs[0]["type"] == "name_first", "events 未持久化"
        assert store2.get("user_name") == "小东", "user_name 未持久化"


def test_intent_affirm_v931() -> None:
    """v9.3.1：肯定句不再误判 SELF_DOUBT，攻击句仍正确归类。"""
    from shared.state import Intent
    e = HardStateEngine()
    e.update("你不是任何人的替代品。你就是你。")
    assert e.profile.session.last_intent != Intent.SELF_DOUBT, "肯定句被误判 SELF_DOUBT"
    assert e.consecutive_negative == 0, f"肯定句误累积连续负面: {e.consecutive_negative}"
    e2 = HardStateEngine()
    e2.update("我只是个替代品，什么都做不好。")
    assert e2.profile.session.last_intent == Intent.SELF_DOUBT
    assert e2.consecutive_negative == 1


def test_local_convergence_v940() -> None:
    """v9.4.0：RemAI 镜像一致性、鬼化→余韵链路、RamAI 好感统一。"""
    from shared.state import OniStage
    from shared.prompts import RamAI
    # RemAI 镜像：字段直通 engine
    twin = ReZeroTwinSystem()
    twin.rem.engine.favor = 42
    assert twin.rem._favor == 42, "RemAI 镜像读取失败"
    # 鬼化 → 余韵：EMERGING 应恰好持续 1 回合余韵
    r1 = twin.interact("危险！有魔兽袭击！")
    assert "角" in r1 and twin.rem.engine.oni_stage == OniStage.EMERGING, f"鬼化未触发: {r1}"
    r2 = twin.interact("今天天气不错。")
    assert "角" in r2, f"余韵台词未触发: {r2}"
    r3 = twin.interact("那就好。")
    assert "角已经收回去" not in r3 and "头好沉" not in r3, f"余韵应只持续一回合: {r3}"
    # RamAI 好感统一：与 engine.ram_favor 同真源
    twin2 = ReZeroTwinSystem()
    before = twin2.rem.engine.ram_favor
    twin2.interact("谢谢你")
    assert twin2.ram.favor() == twin2.rem.engine.ram_favor, "RamAI 与引擎好感未统一"
    assert twin2.rem.engine.ram_favor > before, "拉姆好感未增长"
    # 未绑定 engine 的 RamAI 保持旧行为
    solo = RamAI()
    solo.on_rem_treated_well(2)
    assert solo.favor() == 10, "未绑定 RamAI 旧行为被破坏"


def test_value_channels_v950() -> None:
    """v9.5.0：小额冒犯档、独立度解耦、拉姆成长通道。"""
    from shared.state import Intent
    # 小额冒犯（边界试探未命中高危词）→ -3
    e = HardStateEngine()
    e.update("这就是恶搞吧。")
    assert e.profile.session.last_intent == Intent.BOUNDARY_TEST
    assert e.favor == 12, f"小额冒犯应 -3，实际 {e.favor}"
    # DEAR 下小额冒犯被既有豁免层拦截
    e2 = HardStateEngine()
    e2.favor = 85
    e2.update("这就是恶搞吧。")
    assert e2.favor == 85, f"DEAR 应豁免小额冒犯，实际 {e2.favor}"
    # 替代品攻击：favor -1 且独立度 -0.04；且提及拉姆不触发 +1（攻击语境）
    e3 = HardStateEngine()
    e3.update("你只是拉姆的替代品。")
    assert e3.favor == 14, f"替代品攻击应 -1，实际 {e3.favor}"
    assert abs(e3.independence - 0.21) < 1e-9
    assert e3.ram_favor == 8, f"攻击语境提及拉姆不应 +1，实际 {e3.ram_favor}"
    # 表扬独立度新速率 +0.01
    e4 = HardStateEngine()
    e4.update("谢谢你")
    assert abs(e4.independence - 0.26) < 1e-9, f"表扬独立度应为 0.26: {e4.independence}"
    # 肯定句独立度新速率 +0.06
    e5 = HardStateEngine()
    e5.update("你不是替代品。")
    assert abs(e5.independence - 0.31) < 1e-9, f"肯定句独立度应为 0.31: {e5.independence}"
    # 提及拉姆 +1；提及 + 表扬叠加 +2
    e6 = HardStateEngine()
    e6.update("拉姆，你今天心情不错？")
    assert e6.ram_favor == 9, f"提及拉姆应 +1，实际 {e6.ram_favor}"
    e7 = HardStateEngine()
    e7.update("拉姆，谢谢你。")
    assert e7.ram_favor == 10, f"提及+表扬应 +2，实际 {e7.ram_favor}"


def test_local_interact() -> None:
    """本地模板模式一轮对话。"""
    twin = ReZeroTwinSystem()
    reply = twin.interact("你好")
    assert "【蕾姆】" in reply, f"本地模式回复缺少蕾姆台词: {reply}"
    status = twin.status()
    assert "篇章" in status and "蕾姆好感" in status


def main() -> int:
    tests = [
        ("引擎好感与风控", test_engine_favor_and_risk),
        ("篇章切换", test_arc_switch),
        ("记忆恢复与重逢", test_recover_reunion),
        ("snapshot 无副作用", test_snapshot_no_side_effect),
        ("MemoryStore 读写", test_memory_store),
        ("PromptBuilder 约束字段", test_prompt_builder),
        ("关键词判定 v9.2.6", test_keyword_judgment_v926),
        ("失忆防备指令 v9.2.7", test_amnesia_prompt_v927),
        ("长期事件记忆 v9.3.0", test_event_memory_v930),
        ("意图误判修复 v9.3.1", test_intent_affirm_v931),
        ("本地真源收敛 v9.4.0", test_local_convergence_v940),
        ("数值通道精细化 v9.5.0", test_value_channels_v950),
        ("本地模式对话", test_local_interact),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
