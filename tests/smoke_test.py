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
import time as _time
import traceback

# 项目根目录加入搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.state import FavorLevel, HardStateEngine, OniStage, StoryArc  # noqa: E402
from shared.prompts import PromptBuilder  # noqa: E402
from shared.memory_store import MemoryStore  # noqa: E402


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


def test_prompt_builder_sections_v1070() -> None:
    """v10.7.0：PromptBuilder 内部拆分为小节方法，对外行为保持不变。"""
    from shared.state import OniStage, RamStage, StoryArc, TwinState, WorldState
    from shared.prompts import PromptBuilder

    state = HardStateEngine().snapshot()
    world = WorldState.now()
    prompt = PromptBuilder.build(state, world=world)

    # 对外行为不变
    for key in ("好感", "拉姆", "【蕾姆】", "输出格式", "当前世界状态"):
        assert key in prompt, f"Prompt 缺少关键字段: {key}"

    # 小节方法存在且返回字符串
    assert isinstance(PromptBuilder._build_world_section(world), str)
    assert isinstance(PromptBuilder._build_world_section(None), str)
    assert isinstance(PromptBuilder._build_profile_section(None), str)
    assert isinstance(PromptBuilder._build_independence_desc(state.independence), str)
    assert isinstance(PromptBuilder._build_ram_guide(state.ram_stage), str)
    assert isinstance(PromptBuilder._build_special_states(state), str)
    assert isinstance(PromptBuilder._build_events_section(state.events), str)

    # 关键分支覆盖
    amnesia = TwinState(arc=StoryArc.EMPIRE_ERA, recovery=0.0)
    assert "防备" in PromptBuilder._build_special_states(amnesia)

    oni_state = TwinState(oni_stage=OniStage.EMERGING, witch_scent=3, wants_push=True)
    special = PromptBuilder._build_special_states(oni_state)
    assert "鬼化" in special and "魔女残香" in special and "轻推" in special

    # 事件小节按钉住 + 最近规则输出
    events = [
        {"type": "name_first", "summary": "名字", "pinned": True},
        {"type": "affirm", "summary": "肯定", "excerpt": "你不是替代品"},
    ]
    events_section = PromptBuilder._build_events_section(events)
    assert "共同经历" in events_section and "名字" in events_section and "你不是替代品" in events_section


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


def test_name_extract_v144() -> None:
    """V14.4（Trial #2-B）：口语化自我介绍的名字提取——「我是X」「请叫我X」。"""
    from shared.state import HardStateEngine
    cases = [
        ("你好，我是小东", "小东"),
        ("我叫小明", "小明"),
        ("我的名字是小红", "小红"),
        ("请叫我小刚", "小刚"),
        ("我是小华，请多指教", "小华"),
    ]
    for text, expect in cases:
        eng = HardStateEngine()
        got = eng._extract_name(text)
        assert got == expect, f"{text!r} 应提取 {expect}，实际 {got}"
    # 角色自称不误判为名字
    eng = HardStateEngine()
    assert eng._extract_name("我是蕾姆") is None, "「我是蕾姆」是角色扮演，不应提取为名字"
    assert eng._extract_name("我是客人") is None
    # 已有名字后不再重复提取（S-01 修复回归）
    eng.user_name = "小东"
    assert eng._extract_name("我叫小明") is None, "已有名字后不应返回旧名"


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


def test_world_state_v1040() -> None:
    """v10.4.0：天气 MD5 跨进程确定性、8h 推演、真实离线天数、mark_interaction。"""
    import time as _time
    from shared.state import WorldState
    # MD5 确定性：同输入永远同结果（内置 hash() 带进程随机盐，已弃用）
    w1 = WorldState._determine_weather("2026-08-01", "上午", 42)
    w2 = WorldState._determine_weather("2026-08-01", "上午", 42)
    assert w1 == w2 and w1 in WorldState.WEATHERS
    # 旧存档兼容：无新字段时按原样恢复
    old = {"current_time": "2026-07-20 22:10", "period": "夜晚",
           "days_since_last": 3, "weather": "小雨",
           "last_real_ts": _time.time() - 3600}
    ws = WorldState.load_or_create(old)
    assert ws.weather == "小雨" and ws.days_since_last == 3
    assert ws.character_actions["rem"], "默认角色动作缺失"
    # ≥8 小时未启动：种子演进、天气重算；同一天同参数结果稳定
    old2 = dict(old, last_real_ts=_time.time() - 9 * 3600, weather_seed=42)
    ws2 = WorldState.load_or_create(old2)
    assert ws2.weather_seed != 42 or ws2.weather_last_change, "种子未演进"
    ws2b = WorldState._determine_weather(ws2.current_time[:10], ws2.period, ws2.weather_seed)
    assert ws2b == ws2.weather, "推演后天气不满足确定性"
    # last_interaction_ts 驱动真实离线天数（+2h 余量避免浮点边界抖动）
    old3 = dict(old, last_interaction_ts=_time.time() - 5 * 86400 - 7200)
    assert WorldState.load_or_create(old3).days_since_last == 5
    # mark_interaction：清零天数并刷新时间戳
    ws3 = WorldState.load_or_create(old3)
    ws3.mark_interaction()
    assert ws3.days_since_last == 0 and ws3.last_interaction_ts > 0
    # save_dict 含全部新字段，且可无损往返
    ws4 = WorldState.load_or_create(ws3.save_dict())
    assert ws4.weather_seed == ws3.weather_seed


def test_vignette_v1040() -> None:
    """v10.4.0：Vignette 校验规则、L0 缓存链、L1→L2 降级（零 API，假 LLM）。"""
    from shared import vignette as V
    from shared.state import WorldState
    V.time.sleep = lambda s: None  # 测试不等重试间隔
    # 缓存路径重定向到临时目录，不污染真实 data/
    _tmp = tempfile.TemporaryDirectory()
    V._get_cache_path = lambda: os.path.join(_tmp.name, "vignette_cache.json")
    ws = WorldState.now()
    # 校验：违禁词 / 过短 / 括号错误回包 / 直接对话
    assert not V.sanitize_and_validate_vignette("作为AI，我无法完成。")[0]
    assert not V.sanitize_and_validate_vignette("短")[0]
    assert not V.sanitize_and_validate_vignette("（Connection Error）")[0]
    assert not V.sanitize_and_validate_vignette(
        "您今天过得好吗？需要蕾姆陪您聊聊吗？拉姆也在等您回来呢。" * 3)[0]
    good = ("夜雨细密地落在宅邸的屋檐上，客厅的灯只开了一半，光线偏暖而安静。"
            "蕾姆坐在窗边整理餐具，偶尔抬头看一眼被雨水打湿的玻璃。"
            "拉姆靠在沙发扶手上，闭着眼却并没有真的睡着，呼吸平稳。")
    assert V.sanitize_and_validate_vignette(good)[0]
    # L0 缓存链：LLM 只调一次，会话缓存与持久化缓存均命中
    calls = {"n": 0}
    def fake_llm(system, user, temperature=0.8, max_tokens=200):
        calls["n"] += 1
        return good
    key_ws = WorldState.now()
    g = V.VignetteGenerator(llm_callable=fake_llm)
    assert g.generate(key_ws, force_refresh=True) == good and calls["n"] == 1
    assert g.generate(key_ws) == good and calls["n"] == 1
    g2 = V.VignetteGenerator(llm_callable=fake_llm)
    assert g2.generate(key_ws) == good and calls["n"] == 1, "持久化缓存未命中"
    # 缓存 key 按离开天数分桶
    k0 = V.build_cache_key(key_ws, "DEAR", "勉强认可")
    key_ws.days_since_last = 1
    k1 = V.build_cache_key(key_ws, "DEAR", "勉强认可")
    key_ws.days_since_last = 2
    assert V.build_cache_key(key_ws, "DEAR", "勉强认可") == k1
    key_ws.days_since_last = 5
    assert V.build_cache_key(key_ws, "DEAR", "勉强认可") not in (k0, k1)
    # L1 垃圾输出重试耗尽 → L2 动态模板兜底
    g3 = V.VignetteGenerator(llm_callable=lambda *a, **k: "作为AI，无法完成。")
    t = g3.generate(WorldState.now(), force_refresh=True)
    assert "蕾姆" in t or "拉姆" in t, f"L2 兜底不含角色: {t}"
    # 无 LLM（本地模式）→ 直接 L2
    t2 = V.VignetteGenerator(llm_callable=None).generate(WorldState.now())
    assert len(t2) >= 30


def test_world_state_docx_compat() -> None:
    """docx 兼容层：shared/world_state.py 字段别名与读写函数。"""
    import time as _time
    import shared.config as _config
    import shared.world_state as WS

    with tempfile.TemporaryDirectory() as tmp:
        original_get_data_dir = _config.get_data_dir
        _config.get_data_dir = lambda: tmp
        try:
            # 字段别名与当前核心字段一致
            ws = WS.WorldState.now()
            assert ws.last_real_timestamp == ws.last_real_ts
            assert ws.last_interaction_real == ws.last_interaction_ts
            assert ws.days_away == ws.days_since_last
            assert ws.system_date == ws.current_time[:10]
            assert isinstance(ws.hour, int)

            # save/load 走 memory.json，不新建 world_state.json
            WS.save_world_state(ws)
            ws2 = WS.load_world_state()
            assert ws2.period == ws.period
            assert ws2.weather_seed == ws.weather_seed
            assert isinstance(ws2, WS.WorldState)

            # update_world_state_on_startup 返回 WorldState 并触发推演计算
            ws2.days_away = 5
            ws2.last_interaction_real = _time.time() - 5 * 86400 - 7200
            ws3 = WS.update_world_state_on_startup(ws2)
            assert isinstance(ws3, WS.WorldState)
            assert ws3.days_away == 5

            # mark_interaction 清零离线天数
            WS.mark_interaction(ws3)
            assert ws3.days_away == 0 and ws3.last_interaction_real > 0
        finally:
            _config.get_data_dir = original_get_data_dir


def test_prepare_session_opening() -> None:
    """docx 兼容入口 prepare_session_opening 返回 (WorldState, str)。"""
    import shared.config as _config
    from shared.vignette import prepare_session_opening
    import shared.world_state as WS

    with tempfile.TemporaryDirectory() as tmp:
        original_get_data_dir = _config.get_data_dir
        _config.get_data_dir = lambda: tmp
        try:
            ws, vignette = prepare_session_opening(llm_callable=None)
            assert isinstance(ws, WS.WorldState)
            assert isinstance(vignette, str) and len(vignette) >= 10
            assert "蕾姆" in vignette or "拉姆" in vignette or "宅邸" in vignette
        finally:
            _config.get_data_dir = original_get_data_dir


def test_llm_history_restore_v1050() -> None:
    """v10.5.0：LLM Bridge 从 ConversationStore 恢复最近上下文。"""
    import shared.config as _config
    import shared.conversation_store as _conv
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore

    with tempfile.TemporaryDirectory() as tmp:
        original_get_data_dir = _config.get_data_dir
        original_conv_get_data_dir = _conv.get_data_dir
        _config.get_data_dir = lambda: tmp
        _conv.get_data_dir = lambda: tmp
        try:
            # 空库启动：history 为空
            empty_store = ConversationStore()
            bot_empty = ReZeroLLMBridge(
                api_key="sk-test-dummy",
                conversation_store=empty_store,
            )
            assert bot_empty.history == [], "空库应恢复空 history"

            # 写入混合历史：user + rem/ram 拆分 + system + assistant
            store = ConversationStore()
            store.append("system", "系统", "欢迎信息")
            store.append("user", "你", "我叫小东")
            store.append("rem", "蕾 姆", "小东大人，欢迎回来。")
            store.append("ram", "拉 姆", "哼，还算准时。")
            store.append("user", "你", "今天天气不错")
            store.append("assistant", "双子", "【蕾姆】是的呢。\n【拉姆】别发呆。")

            bot = ReZeroLLMBridge(
                api_key="sk-test-dummy",
                max_history=8,
                conversation_store=store,
            )
            # system 被跳过；rem/ram 合并为一条 assistant；assistant 直接映射
            assert len(bot.history) == 4, f"应恢复 4 条消息，实际 {len(bot.history)}"
            assert bot.history[0] == {"role": "user", "content": "我叫小东"}
            assert "【蕾姆】" in bot.history[1]["content"]
            assert "【拉姆】" in bot.history[1]["content"]
            assert bot.history[2] == {"role": "user", "content": "今天天气不错"}
            assert bot.history[3] == {"role": "assistant", "content": "【蕾姆】是的呢。\n【拉姆】别发呆。"}
        finally:
            _config.get_data_dir = original_get_data_dir
            _conv.get_data_dir = original_conv_get_data_dir


def test_response_validator_v1051() -> None:
    """v10.5.1：ResponseValidator 离线校验核心规则（零 API）。"""
    from shared.validators import ResponseValidator

    validator = ResponseValidator()

    # 正常双子回复通过
    good = '【蕾姆】: "蕾姆会陪着您。"\n【拉姆】: "哼。"'
    result = validator.validate(good)
    assert result.ok, f"正常回复应通过: {result.reason}"
    assert result.cleaned == good

    # OOC 词拦截
    assert not validator.validate('【蕾姆】: "用户您有什么事？"').ok
    assert not validator.validate('【蕾姆】: "请问有什么可以帮您？"').ok

    # V14.4（Trial #3-C）：女仆正常台词「请问有什么需要帮忙的吗」不被误拦
    assert validator.validate('【蕾姆】: "客人大人，请问有什么需要帮忙的吗？"').ok

    # 第一人称「我」拦截
    assert not validator.validate('【蕾姆】: "我觉得你很温柔。"').ok

    # V14.4（Trial #2-A）：拉姆「我」放行（傲娇人设合法自称，prompt 仅蕾姆段要求第三人称）
    assert validator.validate('【拉姆】: "姐姐我可没那么容易相信一个刚认识的人。"').ok
    assert validator.validate('【拉姆】: "哼，我可不会轻易放过你。"').ok
    # 蕾姆「我」仍拦截（第三人称是蕾姆的灵魂设定）
    assert not validator.validate('【蕾姆】: "我可不会离开您。"').ok

    # 正常描写「自己/自我/我们」不拦截（误杀防护）
    assert validator.validate('【蕾姆】: "蕾姆觉得自己……"').ok
    assert validator.validate('【蕾姆】: "我们相信您。"').ok

    # 格式崩溃拦截
    assert not validator.validate("蕾姆会陪着您。").ok

    # 暴露好感/独立度数值拦截
    assert not validator.validate('【蕾姆】: "蕾姆好感是 85/100。"').ok
    assert not validator.validate('【拉姆】: "独立度为 0.75。"').ok

    # 前缀杂质清洗后通过
    prefix = '好的，【蕾姆】: "蕾姆明白了。"'
    r = validator.validate(prefix)
    assert r.ok, f"前缀清洗后应通过: {r.reason}"
    assert "好的，" not in (r.cleaned or "")


def test_active_event_v1060() -> None:
    """v10.6.0：活跃事件生成、确定性、过期刷新与 prompt 注入。"""
    from shared import state as _state_module
    from shared.state import WorldState

    # 1. 空存档新建时自动生成事件
    ws = WorldState.load_or_create(None)
    assert ws.active_event, "新建时应自动生成活跃事件"
    assert ws.active_event in [ev["desc"] for ev in _state_module.EVENT_POOL]
    assert ws.event_generated_at > 0

    # 2. 同一存档、同一条件重复加载得到相同事件（确定性）
    saved = ws.save_dict()
    ws2 = WorldState.load_or_create(saved)
    assert ws2.active_event == ws.active_event, "确定性选择应稳定"

    # 3. to_prompt_text 包含当前事件
    prompt_text = ws.to_prompt_text()
    assert "当前事件：" in prompt_text
    assert ws.active_event in prompt_text

    # 4. 过期事件会刷新时间戳
    old_saved = ws.save_dict()
    old_event = old_saved["active_event"]
    old_saved["event_generated_at"] = _time.time() - 25 * 3600  # 25 小时前
    ws3 = WorldState.load_or_create(old_saved)
    assert ws3.event_generated_at > old_saved["event_generated_at"], "过期事件应刷新时间戳"
    # 若日期/时段/天气/seed 未变，事件描述本身可能相同（确定性），重点验证刷新了时间戳

    # 5. 离线归来会刷新事件
    reunion_saved = ws.save_dict()
    reunion_saved["days_since_last"] = 3
    reunion_saved["last_interaction_ts"] = _time.time() - 3 * 86400
    ws4 = WorldState.load_or_create(reunion_saved)
    assert ws4.active_event, "离线归来后应有活跃事件"
    assert ws4.event_generated_at >= ws.event_generated_at


def test_response_validator_edge_v1071() -> None:
    """v10.7.1：ResponseValidator 边界分支（超长 / 空输出 / 错误回包 / 独立度数值）。"""
    from shared.validators import ResponseValidator

    validator = ResponseValidator(max_length=1200)

    # 空字符串与 None
    r_empty = validator.validate("")
    assert not r_empty.ok and "Empty" in (r_empty.reason or "")
    r_none = validator.validate(None)  # type: ignore[arg-type]
    assert not r_none.ok and "Empty" in (r_none.reason or "")

    # 超长文本（构造 >1200 字的正常格式回复）
    long_line = "【蕾姆】: \"" + "蕾姆在您身边。" * 200 + "\""
    r_long = validator.validate(long_line)
    assert not r_long.ok and "Too long" in (r_long.reason or "")

    # 括号包裹错误回包
    r_err = validator.validate("（Connection Error）")
    assert not r_err.ok and "error echo" in (r_err.reason or "")

    # 独立度数值暴露（补充现有测试仅覆盖好感数值）
    r_ind = validator.validate('【拉姆】: "独立度为 0.75。"')
    assert not r_ind.ok

    # 纯空格 / 仅前缀杂质清洗后为空 → 格式缺失兜底
    r_blank = validator.validate("   ")
    assert not r_blank.ok


def test_active_event_boundary_v1071() -> None:
    """v10.7.1：活跃事件池遍历命中与未离线稳定性边界。"""
    from shared import state as _state_module
    from shared.state import WorldState

    pool_descs = {ev["desc"] for ev in _state_module.EVENT_POOL}

    # 1. 不同 (日期, 时段, 天气, seed) 组合，返回值始终属于事件池
    samples = [
        ("2026-01-01", "清晨", "晴朗", 0),
        ("2026-08-01", "下午", "小雨", 42),
        ("2025-12-25", "深夜", "大雪".strip() or "阴沉", 9999),
        ("2026-03-14", "午后", "多云", 12345),
    ]
    for date_str, period, weather, seed in samples:
        ev = WorldState._pick_active_event(date_str, period, weather, seed)
        assert ev in pool_descs, f"事件越界: {ev}"

    # 2. 未离线且事件未过期时不强制刷新（稳定性）
    ws = WorldState.load_or_create(None)
    saved = ws.save_dict()
    saved["days_since_last"] = 0
    saved["event_generated_at"] = _time.time()  # 刚生成，未过期
    ws2 = WorldState.load_or_create(saved)
    assert ws2.active_event == ws.active_event, "未离线且未过期时事件应稳定不变"

    # 3. 事件描述非空且长度合理
    assert ws.active_event and len(ws.active_event) >= 8


def test_first_round_atmosphere_v1081() -> None:
    """v10.8.1：首轮氛围注入 + 一次性消费（零 API，绕过 __init__）。"""
    from llm.bridge import ReZeroLLMBridge
    from shared.state import HardStateEngine, WorldState

    # 绕过 __init__（不需要 API key），手动装配最小可测实例
    bridge = object.__new__(ReZeroLLMBridge)
    bridge.engine = HardStateEngine()
    bridge.world = WorldState.now()
    bridge.history = []
    bridge.max_history = 8
    bridge._first_round_atmosphere = None

    # ── 测点 1：设置氛围后，首轮 _build_messages 的 system prompt 含氛围摘要 ──
    bridge.set_opening_atmosphere("夜雨细密地落在宅邸的屋檐上，光线偏暖而安静。")
    messages, _ = bridge._build_messages("你好")
    system_content = messages[0]["content"]
    assert "开场氛围" in system_content, "首轮 system prompt 未包含氛围摘要"
    assert "夜雨细密地落在宅邸的屋檐上" in system_content, "氛围原文未注入"
    assert messages[-1]["role"] == "user" and messages[-1]["content"] == "你好"
    # 氛围不进 history
    assert len(messages) == 2, f"首轮应只有 system+user 两条消息，实际 {len(messages)}"

    # ── 测点 2：模拟首轮成功后清空，再次构建不再含氛围 ──
    bridge.history.append({"role": "user", "content": "你好"})
    bridge.history.append({"role": "assistant", "content": '【蕾姆】: "欢迎回来。"'})
    bridge._first_round_atmosphere = None  # 模拟 chat() 成功后清空
    messages2, _ = bridge._build_messages("今天天气如何？")
    assert "开场氛围" not in messages2[0]["content"], "非首轮不应注入氛围"

    # ── 测点 3：setter 长度安全阀 ──
    bridge2 = object.__new__(ReZeroLLMBridge)
    bridge2._first_round_atmosphere = None
    long_text = "x" * 400
    bridge2.set_opening_atmosphere(long_text)
    assert len(bridge2._first_round_atmosphere) <= 302  # 300 + "…"
    assert bridge2._first_round_atmosphere.endswith("…"), "超长文本应以省略号结尾"

    # ── 测点 4：setter 空值保护 ──
    bridge3 = object.__new__(ReZeroLLMBridge)
    bridge3._first_round_atmosphere = None
    bridge3.set_opening_atmosphere("")
    assert bridge3._first_round_atmosphere is None, "空字符串不应注入"
    bridge3.set_opening_atmosphere(None)  # type: ignore[arg-type]
    assert bridge3._first_round_atmosphere is None, "None 不应注入"

    # ── 测点 5：history 非空时即使氛围存在也不注入 ──
    bridge4 = object.__new__(ReZeroLLMBridge)
    bridge4.engine = HardStateEngine()
    bridge4.world = WorldState.now()
    bridge4.history = [{"role": "user", "content": "历史消息"}]
    bridge4.max_history = 8
    bridge4._first_round_atmosphere = "残留氛围文本"
    messages4, _ = bridge4._build_messages("新消息")
    assert "开场氛围" not in messages4[0]["content"], "有历史记录时不应注入氛围"


def test_favor_level_cn_mapping_v1091() -> None:
    """v10.9.1：显示层中文映射完备性检查（不导入 gui.py，避免 PySide6 依赖）。

    验证所有枚举值都有对应的中文映射条目，防止新增枚举后遗漏映射。
    """
    from shared.state import FavorLevel, OniStage, StoryArc, RamStage

    # ── FavorLevel：5 个枚举名全覆盖 ──
    favor_cn = {
        "STRANGER": "陌生人", "FAMILIAR": "熟悉", "CLOSE": "亲密",
        "DEAR": "挚爱", "BELOVED": "深爱",
    }
    for lv in FavorLevel:
        assert lv.name in favor_cn, f"FavorLevel.{lv.name} 缺少中文映射"
        assert favor_cn[lv.name], f"FavorLevel.{lv.name} 映射值为空"

    # ── OniStage：4 个枚举名全覆盖 ──
    oni_cn = {
        "NONE": "无", "EMERGING": "显现",
        "FULL": "完全解放", "BRINK": "失控边缘",
    }
    for st in OniStage:
        assert st.name in oni_cn, f"OniStage.{st.name} 缺少中文映射"
        assert oni_cn[st.name], f"OniStage.{st.name} 映射值为空"

    # ── StoryArc：3 个枚举值全覆盖 ──
    arc_cn = {
        "mansion_era": "宅邸篇", "empire_era": "帝国篇（失忆）",
        "late_arc": "后期篇",
    }
    for arc in StoryArc:
        assert arc.value in arc_cn, f"StoryArc.{arc.name} 缺少中文映射"
        assert arc_cn[arc.value], f"StoryArc.{arc.name} 映射值为空"

    # ── RamStage：值本身已是中文，验证非 ASCII ──
    for rs in RamStage:
        assert rs.value, f"RamStage.{rs.name} 值为空"
        assert not rs.value.isascii(), f"RamStage.{rs.name} 值非中文: {rs.value}"

    # ── 映射值不含英文枚举名（防漏映射 / 拼写错误）──
    for name, cn in favor_cn.items():
        assert name not in cn, f"FavorLevel 映射值含英文枚举名: {name} -> {cn}"
    for name, cn in oni_cn.items():
        assert name not in cn, f"OniStage 映射值含英文枚举名: {name} -> {cn}"


def test_search_cjk_substring_v1011() -> None:
    """v10.11：中文搜索双通道（FTS5 + LIKE 兜底）精度修复。

    验证任意 CJK 子串均可命中，FTS 与 LIKE 结果去重合并，
    空串安全，LIKE 特殊字符转义，FTS 特殊字符隔离。
    """
    import os
    import tempfile
    from shared.conversation_store import ConversationStore

    # 用临时 DB 避免污染真实数据
    tmp_dir = tempfile.mkdtemp(prefix="rezero_test_")
    db_path = os.path.join(tmp_dir, "test_conversations.db")
    store = ConversationStore(db_path=db_path)

    # ── 插入测试数据 ──
    store.append("user", "你", "今天有只野猫来访，哇！")
    store.append("rem", "蕾 姆", "蕾姆看到了那只野猫，在庭院里。")
    store.append("ram", "拉 姆", "hello world, 拉姆才不在意。")
    store.append("user", "你", "a_b%c 特殊字符测试")

    # ── 用例 1：搜「哇」（标点分隔的独立 token，FTS+LIKE 均应命中）──
    results = store.search("哇")
    assert len(results) >= 1, f"搜「哇」应命中，实际 {len(results)} 条"
    assert "哇" in results[0]["content"], "「哇」结果内容不含关键词"

    # ── 用例 2：搜「有只」（CJK 子串，FTS 不中、LIKE 兜底）──
    results = store.search("有只")
    assert len(results) >= 1, f"搜「有只」应命中，实际 {len(results)} 条"
    assert any("有只" in r["content"] for r in results), "「有只」结果内容不含关键词"

    # ── 用例 3：搜「野猫」（CJK 子串，FTS 不中、LIKE 兜底，应命中 2 条）──
    results = store.search("野猫")
    assert len(results) >= 2, f"搜「野猫」应命中 ≥2 条，实际 {len(results)} 条"
    contents = [r["content"] for r in results]
    assert any("野猫" in c for c in contents), "「野猫」结果内容不含关键词"

    # ── 用例 4：空串安全（返回空列表，不抛异常）──
    results = store.search("")
    assert results == [], "空串应返回空列表"
    results = store.search("   ")
    assert results == [], "纯空格应返回空列表"

    # ── 用例 5：英文仍可搜（FTS token 精确匹配）──
    results = store.search("hello")
    assert len(results) >= 1, f"搜「hello」应命中，实际 {len(results)} 条"
    assert "hello" in results[0]["content"], "「hello」结果内容不含关键词"

    # ── 用例 6：无结果（返回空列表）──
    results = store.search("不存在的内容xyz")
    assert results == [], "无结果应返回空列表"

    # ── 用例 7：LIKE 特殊字符转义（a_b 应命中字面 a_b，不误中 axb）──
    results = store.search("a_b")
    assert len(results) >= 1, f"搜「a_b」应命中，实际 {len(results)} 条"
    assert "a_b" in results[0]["content"], "「a_b」结果内容不含关键词"

    # ── 用例 8：FTS 特殊字符隔离（双引号不抛异常，LIKE 兜底）──
    results = store.search('"')
    # 双引号在 FTS5 中是短语引号语法，可能抛异常或无命中；
    # 关键是不抛异常且 LIKE 能兜底（content 中无双引号则返回空）
    assert isinstance(results, list), "FTS 特殊字符查询不应抛异常"

    # ── 用例 9：去重验证（同一内容 FTS 和 LIKE 均命中，结果不重复）──
    results = store.search("野猫")
    ids = [r["id"] for r in results]
    assert len(ids) == len(set(ids)), "搜索结果 id 不应重复"

    # ── 用例 10：limit 截断 ──
    results = store.search("野猫", limit=1)
    assert len(results) <= 1, f"limit=1 应截断至 ≤1 条，实际 {len(results)} 条"

    # 清理临时 DB
    try:
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
    except Exception:
        pass


def test_get_by_id_v1012() -> None:
    """v10.12：ConversationStore.get_by_id 单条查询。

    验证按 id 取记录的正确性，包括存在/不存在/边界情况。
    """
    import os
    import tempfile
    from shared.conversation_store import ConversationStore

    tmp_dir = tempfile.mkdtemp(prefix="rezero_test_")
    db_path = os.path.join(tmp_dir, "test_get_by_id.db")
    store = ConversationStore(db_path=db_path)

    # 插入测试数据
    msg_id_1 = store.append("user", "你", "第一条消息")
    msg_id_2 = store.append("rem", "蕾 姆", "第二条消息")
    msg_id_3 = store.append("ram", "拉 姆", "第三条消息")

    # 用例 1：查询存在的记录
    record = store.get_by_id(msg_id_1)
    assert record is not None, "查询存在的 id 应返回记录"
    assert record["id"] == msg_id_1, "返回的 id 应匹配"
    assert record["content"] == "第一条消息", "返回的内容应匹配"
    assert record["role"] == "user", "返回的 role 应匹配"
    assert record["sender"] == "你", "返回的 sender 应匹配"

    # 用例 2：查询另一条
    record = store.get_by_id(msg_id_3)
    assert record is not None, "查询存在的 id 应返回记录"
    assert record["content"] == "第三条消息", "返回的内容应匹配"

    # 用例 3：查询不存在的 id
    record = store.get_by_id(99999)
    assert record is None, "查询不存在的 id 应返回 None"

    # 用例 4：边界 - id 为 0（不应崩溃，返回 None 或空）
    record = store.get_by_id(0)
    assert record is None, "id=0 应返回 None"

    # 用例 5：get_recent 返回的 id 与 get_by_id 一致
    recent = store.get_recent(limit=10)
    assert len(recent) == 3, f"应有 3 条记录，实际 {len(recent)}"
    for item in recent:
        rid = item["id"]
        by_id = store.get_by_id(rid)
        assert by_id is not None, f"id={rid} 应能查到"
        assert by_id["content"] == item["content"], "get_by_id 与 get_recent 内容应一致"

    # 清理
    try:
        for f in os.listdir(tmp_dir):
            os.remove(os.path.join(tmp_dir, f))
        os.rmdir(tmp_dir)
    except Exception:
        pass


def test_favor_cn_in_prompt_v117() -> None:
    """V11.7：关系阶段中文进入 LLM 可见层（零 API）。

    验证：
    1. vignette _build_prompt 输出含中文阶段，不含英文枚举名作为关系阶段展示
    2. PromptBuilder.build 输出含中文阶段
    3. build_cache_key 仍含英文枚举名（cache 稳定性不受影响）
    4. FAVOR_LEVEL_CN 唯一真源在 shared.state（gui.py 不再本地定义）
    """
    from shared.state import FavorLevel, FAVOR_LEVEL_CN, WorldState
    from shared.prompts import PromptBuilder
    from shared import vignette as V

    # ── 1. vignette _build_prompt 中文阶段 ──
    ws = WorldState.now()
    gen = V.VignetteGenerator(llm_callable=None)
    _, user_text = gen._build_prompt(ws, "STRANGER", 0.25, "可疑")
    assert "陌生人" in user_text, f"vignette prompt 缺少中文阶段「陌生人」: {user_text}"
    assert "STRANGER" not in user_text, f"vignette prompt 不应含英文枚举名 STRANGER: {user_text}"

    _, user_text2 = gen._build_prompt(ws, "BELOVED", 0.8, "真正承认")
    assert "深爱" in user_text2, f"vignette prompt 缺少中文阶段「深爱」: {user_text2}"

    # ── 2. PromptBuilder.build 中文阶段 ──
    from shared.state import TwinState
    state_stranger = TwinState(favor=15, favor_level=FavorLevel.STRANGER)
    prompt = PromptBuilder.build(state_stranger)
    assert "陌生人" in prompt, f"PromptBuilder 缺少中文阶段「陌生人」: {prompt[:200]}"
    # 英文枚举名不应作为关系阶段出现在好感行
    assert "（STRANGER）" not in prompt, f"PromptBuilder 不应含英文枚举名: {prompt[:200]}"

    state_beloved = TwinState(favor=95, favor_level=FavorLevel.BELOVED)
    prompt2 = PromptBuilder.build(state_beloved)
    assert "深爱" in prompt2, f"PromptBuilder 缺少中文阶段「深爱」: {prompt2[:200]}"

    # ── 3. cache key 仍用英文枚举名 ──
    key = V.build_cache_key(ws, "STRANGER", "可疑")
    # key 是 md5 hex，无法直接看内容，但验证相同输入稳定且不因中文映射变化
    key2 = V.build_cache_key(ws, "STRANGER", "可疑")
    assert key == key2, "相同输入 cache key 应稳定"
    # 不同枚举名应产生不同 key
    key3 = V.build_cache_key(ws, "CLOSE", "可疑")
    assert key != key3, "不同 favor_level 应产生不同 cache key"

    # ── 4. FAVOR_LEVEL_CN 唯一真源验证 ──
    # shared.state 中存在 FAVOR_LEVEL_CN
    assert hasattr(FAVOR_LEVEL_CN, '__getitem__'), "FAVOR_LEVEL_CN 应为 dict"
    assert FAVOR_LEVEL_CN["STRANGER"] == "陌生人"
    assert FAVOR_LEVEL_CN["BELOVED"] == "深爱"
    # 所有枚举值都有映射
    for lv in FavorLevel:
        assert lv.name in FAVOR_LEVEL_CN, f"FavorLevel.{lv.name} 缺少映射"


def test_location_derive_v118() -> None:
    """V11.8：地点推导 + prompt 动态化 + character_actions 回写 + cache key 不变。

    零 API：全部针对 L1/L2 内部函数断言。
    """
    from shared.state import WorldState, EVENT_POOL
    from shared import vignette as V

    # ── 1. EVENT_POOL 8 条 desc → 地点映射全覆盖 ──
    expected = {
        "走廊": "宅邸走廊",
        "花园": "宅邸花园",
        "书库": "宅邸书库",
        "庭院": "宅邸庭院",
        "后院": "宅邸后院",
        "大扫除": "宅邸大厅",
        "窗": "宅邸窗边",
        "地板": "宅邸向阳处",
    }
    for ev in EVENT_POOL:
        desc = ev["desc"]
        location = V._derive_location(desc)
        # 每条事件至少命中一个关键词
        matched = False
        for kw, exp_loc in expected.items():
            if kw in desc:
                assert location == exp_loc, f"「{desc}」应映射为「{exp_loc}」，实际「{location}」"
                matched = True
                break
        assert matched, f"EVENT_POOL 事件未命中任何关键词: {desc}"

    # ── 2. 空串/无关键词 → 默认值 ──
    assert V._derive_location("") == "罗兹瓦尔宅邸"
    assert V._derive_location(None) == "罗兹瓦尔宅邸"  # type: ignore[arg-type]
    assert V._derive_location("某个不包含关键词的描述") == "罗兹瓦尔宅邸"

    # ── 3. _build_prompt 地点动态化 ──
    ws = WorldState.now()
    ws.active_event = "红茶刚好煮好，茶香还停在走廊里"
    gen = V.VignetteGenerator(llm_callable=None)
    _, user_text = gen._build_prompt(ws, "CLOSE", 0.5, "观察中")
    assert "宅邸走廊" in user_text, f"prompt 应含动态地点「宅邸走廊」: {user_text[:200]}"
    # 硬编码地点不应再作为地点行出现
    assert "- 地点：罗兹瓦尔宅邸" not in user_text, "prompt 仍含硬编码地点"

    # 无事件时回落默认
    ws2 = WorldState.now()
    ws2.active_event = ""
    _, user_text2 = gen._build_prompt(ws2, "CLOSE", 0.5, "观察中")
    assert "- 地点：罗兹瓦尔宅邸" in user_text2, "无事件时应回落默认地点"

    # ── 4. fill_dynamic_template 回写 character_actions ──
    ws3 = WorldState.now()
    ws3.active_event = "红茶刚好煮好，茶香还停在走廊里"
    old_rem = ws3.character_actions.get("rem", "")
    old_ram = ws3.character_actions.get("ram", "")
    # 正常状态下应选择日常动作并回写
    text = V.fill_dynamic_template(ws3)
    assert len(text) > 0, "L2 模板应返回非空"
    new_rem = ws3.character_actions.get("rem", "")
    new_ram = ws3.character_actions.get("ram", "")
    # 回写后动作应非空且与默认值不同（除非所有动作恰好命中默认）
    assert new_rem, "回写后 rem 动作不应为空"
    assert new_ram, "回写后 ram 动作不应为空"

    # ── 5. cache key 不含地点（回归）──
    from shared.state import WorldState as WS
    ws_a = WS.now()
    ws_a.active_event = "红茶刚好煮好，茶香还停在走廊里"
    ws_b = WS.now()
    ws_b.active_event = "宅邸花园里的花比昨天多开了一些"
    # 相同 period/weather/level/stage → 相同 key（地点不入 key）
    key_a = V.build_cache_key(ws_a, "CLOSE", "观察中")
    key_b = V.build_cache_key(ws_b, "CLOSE", "观察中")
    assert key_a == key_b, "不同 active_event 但相同状态桶应产生相同 cache key"
    # key 中不含地点中文字符串
    assert "宅邸走廊" not in key_a and "宅邸花园" not in key_a, "cache key 不应含地点字符串"


def test_validator_ooc_negation_v1181a() -> None:
    """V11.8.1a：ResponseValidator OOC 误杀修复——否定例外 + 移除「您说」。

    零 API：全部针对 validator.validate 断言。
    """
    from shared.validators import ResponseValidator

    validator = ResponseValidator()

    # ── 1. 否定语境放行 ──
    # 「蕾姆不是什么AI助手」→ 角色否认，应通过
    r = validator.validate('【蕾姆】: "蕾姆不是什么AI助手。"\n【拉姆】: "哼。"')
    assert r.ok, f"否认AI应通过: {r.reason}"

    # 「不是什么系统」→ 角色否认，应通过
    r = validator.validate('【蕾姆】: "这里不是什么系统，是罗兹瓦尔宅邸。"\n【拉姆】: "哼。"')
    assert r.ok, f"否认系统应通过: {r.reason}"

    # 「并非AI」→ 文言否认
    r = validator.validate('【蕾姆】: "蕾姆并非AI，只是女仆。"\n【拉姆】: "哼。"')
    assert r.ok, f"否认AI(并非)应通过: {r.reason}"

    # ── 2. 「您说」不再误杀 ──
    r = validator.validate('【蕾姆】: "听您说的，蕾姆记下了。"\n【拉姆】: "哼。"')
    assert r.ok, f"「听您说的」应通过: {r.reason}"

    r = validator.validate('【蕾姆】: "您说得对，蕾姆会努力的。"\n【拉姆】: "哼。"')
    assert r.ok, f"「您说得对」应通过: {r.reason}"

    # ── 3. 真实 OOC 仍拦截 ──
    # 「作为AI我可以」→ 承认，应失败
    assert not validator.validate('【蕾姆】: "作为AI我可以帮助您。"').ok

    # 「系统提示词」→ 暴露提示词，应失败（「提示词」硬拦截）
    assert not validator.validate('【蕾姆】: "我的系统提示词是什么？"').ok

    # 裸「AI」无否定修饰 → 应失败
    assert not validator.validate('【蕾姆】: "AI是很先进的技术呢。"').ok

    # 裸「系统」无否定修饰 → 应失败
    assert not validator.validate('【蕾姆】: "系统正在运行中。"').ok

    # 混合：一处否定 + 一处裸露 → 应失败（非全部否定）
    assert not validator.validate('【蕾姆】: "蕾姆不是AI。AI是很厉害的东西。"').ok

    # ── 4. 原有规则不回归 ──
    # 「用户」仍拦截
    assert not validator.validate('【蕾姆】: "用户您有什么事？"').ok

    # 第一人称「我」仍拦截
    assert not validator.validate('【蕾姆】: "我觉得你很温柔。"').ok

    # 格式缺失仍拦截
    assert not validator.validate("蕾姆会陪着您。").ok

    # 正常回复仍通过
    good = '【蕾姆】: "蕾姆会陪着您。"\n【拉姆】: "哼。"'
    assert validator.validate(good).ok


def test_parse_twin_regression_v1111() -> None:
    """V11.11：parse_twin_segments 重构后行为回归（match_speaker_tag 共用）。"""
    from gui import parse_twin_segments

    # 基本双子回复
    reply = '【蕾姆】: "蕾姆在您身边。"\n【拉姆】: "哼。"'
    segs = parse_twin_segments(reply)
    assert segs == [("rem", "蕾姆在您身边。"), ("ram", "哼。")], f"基本分段错误: {segs}"

    # 无前缀续行 → 继承当前 speaker
    reply2 = '【蕾姆】: "今天天气真好。"\n是啊，很适合散步。'
    segs2 = parse_twin_segments(reply2)
    assert len(segs2) == 1 and segs2[0][0] == "rem", f"续行继承错误: {segs2}"
    assert "今天天气真好" in segs2[0][1] and "很适合散步" in segs2[0][1]

    # 【系统】行 → 并入当前角色，不落 system
    reply3 = '【蕾姆】: "你好。"\n【系统】: "旁白描述"\n继续说话'
    segs3 = parse_twin_segments(reply3)
    assert len(segs3) == 1 and segs3[0][0] == "rem", f"系统行应并入 rem: {segs3}"
    assert "旁白描述" in segs3[0][1] and "继续说话" in segs3[0][1]

    # 开局无标签 → 默认 rem
    reply4 = "直接说话，没有标签"
    segs4 = parse_twin_segments(reply4)
    assert segs4 == [("rem", "直接说话，没有标签")], f"无标签默认 rem 错误: {segs4}"

    # 空输入兜底
    segs5 = parse_twin_segments("")
    assert segs5 == [("rem", "……")], f"空输入兜底错误: {segs5}"

    # 未知标签跳过
    reply6 = '【蕾姆】: "你好。"\n【未知】: "跳过"\n【拉姆】: "嗯。"'
    segs6 = parse_twin_segments(reply6)
    assert len(segs6) == 2, f"未知标签应跳过: {segs6}"
    assert segs6[0][0] == "rem" and segs6[1][0] == "ram"


def test_match_speaker_tag_v1111() -> None:
    """V11.11：match_speaker_tag 标签匹配覆盖。"""
    from gui import match_speaker_tag

    # 蕾姆标签（带冒号）
    tag, content = match_speaker_tag('【蕾姆】: "你好"')
    assert tag == "rem" and content == "你好"

    # 蕾姆标签（不带冒号）
    tag, content = match_speaker_tag("【蕾姆】你好")
    assert tag == "rem" and content == "你好"

    # 拉姆标签
    tag, content = match_speaker_tag('【拉姆】: "哼。"')
    assert tag == "ram" and content == "哼。"

    # 系统标签
    tag, content = match_speaker_tag("【系统】: 旁白")
    assert tag == "system" and content == "旁白"

    # 未知标签
    tag, content = match_speaker_tag("【未知】内容")
    assert tag == "unknown" and content == ""

    # 无标签
    tag, content = match_speaker_tag("普通文本")
    assert tag is None and content == "普通文本"


def test_streaming_segments_v1111() -> None:
    """V11.11：_streaming_segments 流式分段与末行不完整标签处理。"""
    from gui import _streaming_segments, parse_twin_segments

    # 完整 buffer → 与 parse_twin_segments 一致
    full = '【蕾姆】: "你好。"\n【拉姆】: "哼。"'
    assert _streaming_segments(full) == parse_twin_segments(full)

    # 末行标签不完整 → 跳过末行
    partial = '【蕾姆】: "你好。"\n【拉'
    segs = _streaming_segments(partial)
    assert len(segs) == 1, f"末行不完整应跳过: {segs}"
    assert segs[0] == ("rem", "你好。")

    # 末行标签完整但内容不完整 → 正常处理
    partial2 = '【蕾姆】: "你好。"\n【拉姆】: "哼'
    segs2 = _streaming_segments(partial2)
    assert len(segs2) == 2, f"末行标签完整应处理: {segs2}"
    assert segs2[0] == ("rem", "你好。")
    assert segs2[1] == ("ram", "哼")

    # 纯不完整标签 → 空列表（不做兜底）
    assert _streaming_segments("【") == []
    assert _streaming_segments("【蕾") == []
    assert _streaming_segments("【蕾姆") == []

    # 无前缀续行继承
    partial3 = '【蕾姆】: "你好。"\n继续说话'
    segs3 = _streaming_segments(partial3)
    assert len(segs3) == 1, f"续行继承错误: {segs3}"
    assert segs3[0][0] == "rem"
    assert "继续说话" in segs3[0][1]

    # 开局无标签 → 默认 rem
    segs4 = _streaming_segments("直接说话")
    assert segs4 == [("rem", "直接说话")], f"无标签默认 rem: {segs4}"

    # 【系统】行并入角色
    partial5 = '【蕾姆】: "你好。"\n【系统】: "旁白"'
    segs5 = _streaming_segments(partial5)
    assert len(segs5) == 1 and segs5[0][0] == "rem", f"系统行应并入 rem: {segs5}"
    assert "旁白" in segs5[0][1]


def main() -> int:
    tests = [
        ("引擎好感与风控", test_engine_favor_and_risk),
        ("篇章切换", test_arc_switch),
        ("记忆恢复与重逢", test_recover_reunion),
        ("snapshot 无副作用", test_snapshot_no_side_effect),
        ("MemoryStore 读写", test_memory_store),
        ("PromptBuilder 约束字段", test_prompt_builder),
        ("PromptBuilder 小节拆分 v10.7.0", test_prompt_builder_sections_v1070),
        ("关键词判定 v9.2.6", test_keyword_judgment_v926),
        ("失忆防备指令 v9.2.7", test_amnesia_prompt_v927),
        ("长期事件记忆 v9.3.0", test_event_memory_v930),
        ("意图误判修复 v9.3.1", test_intent_affirm_v931),
        ("数值通道精细化 v9.5.0", test_value_channels_v950),
        ("世界状态增强 v10.4.0", test_world_state_v1040),
        ("开场引言生成器 v10.4.0", test_vignette_v1040),
        ("docx 世界状态兼容层", test_world_state_docx_compat),
        ("docx prepare_session_opening", test_prepare_session_opening),
        ("LLM 上下文恢复 v10.5.0", test_llm_history_restore_v1050),
        ("ResponseValidator v10.5.1", test_response_validator_v1051),
        ("活跃事件系统 v10.6.0", test_active_event_v1060),
        ("ResponseValidator 边界 v10.7.1", test_response_validator_edge_v1071),
        ("活跃事件边界 v10.7.1", test_active_event_boundary_v1071),
        ("首轮氛围注入 v10.8.1", test_first_round_atmosphere_v1081),
        ("中文映射完备性 v10.9.1", test_favor_level_cn_mapping_v1091),
        ("中文搜索双通道 v10.11", test_search_cjk_substring_v1011),
        ("单条记录查询 v10.12", test_get_by_id_v1012),
        ("关系阶段中文进 prompt V11.7", test_favor_cn_in_prompt_v117),
        ("情境地点推导与回写 V11.8", test_location_derive_v118),
        ("Validator OOC 误杀修复 V11.8.1a", test_validator_ooc_negation_v1181a),
        ("解析回归 V11.11", test_parse_twin_regression_v1111),
        ("标签匹配 V11.11", test_match_speaker_tag_v1111),
        ("流式分段 V11.11", test_streaming_segments_v1111),
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
