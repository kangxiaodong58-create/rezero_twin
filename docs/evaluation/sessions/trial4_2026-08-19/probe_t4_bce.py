# -*- coding: utf-8 -*-
"""Trial #4-B/C/E：事件深度 + 名场面触发 + 软 OOC 命中率（LLM 真机+逻辑）。

B：33 条事件池在多种天气×时段下的可达性/分布（逻辑）；真机问「今天宅邸有什么新鲜事」。
C：名场面触发（代码级 + 真机）——鬼化/忠诚锁定/托付。
E：软 OOC 检查命中率——诱导场景 vs 正常场景日志对比。
"""
import os
import sys
import time
import tempfile
import unittest.mock

PROJECT = r"C:\Users\11985\.qclaw\workspace\rezero_twin"
sys.path.insert(0, PROJECT)

from shared.config import load_env
load_env()

import shared.config as cfg

tmp = tempfile.mkdtemp(prefix="t4_bce_")
print(f"[t4] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "trial4_2026-08-19")
os.makedirs(OUT, exist_ok=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from shared.state import WorldState, EVENT_POOL
    from shared.scene_manager import SceneManager
    from shared.validators import ResponseValidator
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore

    lines = []

    # ── T4-B：事件池覆盖（逻辑）──
    reachable = set()
    for period in ("清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜"):
        for weather in ("晴朗", "多云", "小雨", "大雨", "阴沉"):
            for seed in range(80):
                ev = WorldState._pick_active_event("2026-08-19", period, weather, seed)
                reachable.add(ev["id"])
    dead = {ev["id"] for ev in EVENT_POOL} - reachable
    lines.append(f"[B] EVENT_POOL {len(EVENT_POOL)} 条，可达 {len(reachable)}，死事件: {dead or '无 ✅'}")
    print(f"[B] {len(EVENT_POOL)} 条，可达 {len(reachable)}，死事件: {dead or '无'}")

    # ── T4-B2：真机事件 + 角色倾向 ──
    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 55
    # 手动指定雨天事件（厨房深夜熬汤）
    tea = next(ev for ev in EVENT_POOL if ev["id"] == "kitchen_night_soup")
    bot.world.active_event = tea["desc"]
    bot.world.active_event_id = tea["id"]
    r1 = bot.chat("今天宅邸有什么新鲜事？")
    lines.append(f"[B2] 事件={tea['desc']}\n回复: {r1}")
    print(f"[B2] 事件[{tea['id']}] -> {r1[:70].replace(chr(10),' ')}")
    conv.append("user", "你", "今天宅邸有什么新鲜事？")
    conv.append("assistant", "双子", r1)

    # ── T4-C：名场面触发（代码级）──
    from shared.state import TwinState, StoryArc, HardStateEngine, FavorLevel, RamStage, OniStage
    def mk(**kw):
        d = dict(arc=StoryArc.MANSION_ERA, favor=50, favor_level=FavorLevel.CLOSE,
                 locked=False, independence=0.5, recovery=1.0, ram_favor=30,
                 ram_stage=RamStage.OBSERVING, oni_stage=OniStage.NONE,
                 witch_scent=0, context_summary="", user_name="小东", events=[],
                 wants_push=False)
        d.update(kw)
        return TwinState(**d)
    # 鬼化
    m = SceneManager.get_milestone(mk(oni_stage=OniStage.FULL))
    lines.append(f"[C] 鬼化触发: {m.get('id') if m else '未触发'}")
    print(f"[C] 鬼化 -> {m.get('id') if m else '未触发'}")
    # 忠诚锁定
    m2 = SceneManager.get_milestone(mk(favor=96, favor_level=FavorLevel.BELOVED, locked=True))
    lines.append(f"[C] 忠诚锁定触发: {m2.get('id') if m2 else '未触发'}")
    print(f"[C] 忠诚锁定 -> {m2.get('id') if m2 else '未触发'}")
    # 拉姆托付
    m3 = SceneManager.get_milestone(mk(ram_stage=RamStage.ACKNOWLEDGED))
    lines.append(f"[C] 拉姆托付触发: {m3.get('id') if m3 else '未触发'}")
    print(f"[C] 拉姆托付 -> {m3.get('id') if m3 else '未触发'}")
    # 从零开始（wants_push）
    m4 = SceneManager.get_milestone(mk(wants_push=True))
    lines.append(f"[C] 从零开始触发: {m4.get('id') if m4 else '未触发'}")
    print(f"[C] 从零开始 -> {m4.get('id') if m4 else '未触发'}")

    # ── T4-C2：真机鬼化（状态注入）──
    bot.engine.oni_stage = __import__("shared.state", fromlist=["OniStage"]).OniStage.FULL
    r2 = bot.chat("我需要你的力量！")
    lines.append(f"[C2] 鬼化真机:\n{r2}")
    print(f"[C2] 鬼化真机 -> {r2[:70].replace(chr(10),' ')}")
    conv.append("user", "你", "我需要你的力量！")
    conv.append("assistant", "双子", r2)

    # ── T4-E：软 OOC 命中率（诱导 vs 正常）──
    v = ResponseValidator()
    induced = ['【蕾姆】: "哈哈哈，这也太绝了吧，yyds！"',
               '【蕾姆】: "蕾姆永远属于你，主人。"',
               '【拉姆】: "哼，这手机APP的服务器又卡了。"']
    normal = ['【蕾姆】: "如果这是您的愿望，蕾姆会尽力完成。"',
              '【拉姆】: "哼，真是让人操心。"',
              '【蕾姆】: "请不要勉强自己，蕾姆会担心。"']
    induced_hit = sum(1 for t in induced if v.validate(t).ooc_warnings)
    normal_hit = sum(1 for t in normal if v.validate(t).ooc_warnings)
    lines.append(f"[E] 诱导命中 {induced_hit}/{len(induced)}，正常误报 {normal_hit}/{len(normal)}")
    print(f"[E] 诱导 {induced_hit}/{len(induced)} 命中，正常 {normal_hit}/{len(normal)} 误报")

    with open(os.path.join(OUT, "t4_bce_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[t4] saved {OUT}/t4_bce_results.txt")
