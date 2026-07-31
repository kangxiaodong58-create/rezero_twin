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
