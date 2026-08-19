# -*- coding: utf-8 -*-
"""V14.5-14.7 真机验收（LLM 模式，预算封顶 ¥2）。

覆盖验收清单 A-F + 扩展项：
A 空间场景系统（A1-A8）
B 事件系统（B1-B3）
C 角色卡语感（C1-C5）
F 持久化（F1）
+ 备注项：失忆重逢（/recover 0.2）
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

tmp = tempfile.mkdtemp(prefix="v1457_accept_")
print(f"[accept] isolated data dir: {tmp}")

OUT = os.path.join(PROJECT, "docs", "evaluation", "sessions", "accept_v1457_2026-08-19")
os.makedirs(OUT, exist_ok=True)

with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
    from llm import ReZeroLLMBridge
    from shared.conversation_store import ConversationStore
    from shared.world_state import WorldState, save_world_state

    conv = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv,
    )
    bot.world = WorldState.now()
    bot.engine.favor = 40  # 中好感（C2 判据）
    save_world_state(bot.world)

    lines = []
    def rec(tag, text, expect_hint=""):
        t0 = time.time()
        try:
            reply = bot.chat(text)
            lines.append(f"### [{tag}] {text}")
            lines.append(f"场景={bot.world.scene} 天气={bot.world.weather} 时段={bot.world.period}")
            lines.append(f"回复: {reply}")
            lines.append(f"提示: {expect_hint}")
            lines.append("")
            print(f"[{tag}] scene={bot.world.scene} | {text[:20]} -> {reply[:60].replace(chr(10),' ')}")
        except Exception as e:
            lines.append(f"### [{tag}] {text} ERROR: {e}")
            print(f"[{tag}] ERROR: {e}")
        conv.append("user", "你", text)
        conv.append("assistant", "双子", reply if 'reply' in dir() else "(错误)")
        save_world_state(bot.world)

    # ── A 空间场景系统 ──
    rec("A1", "去厨房", "应出现厨房环境（面包香/银器/蒸锅）")
    rec("A2", "今天做了什么", "应仍带厨房语境 2-3 轮")
    rec("A3", "回房间", "切换房间场景（拉窗帘/被角/烛火）")
    rec("A4", "到花园走走", "花园场景（浇花/花苞/日光）")
    rec("A5a", "去餐厅", "餐桌礼仪/摆盘")
    rec("A5b", "去书库", "书库场景（羽毛掸子/旧书）")
    rec("A6", "厨房的茶很好喝", "闲聊提及不应切换场景（当前应仍书库）")
    rec("A7", "贝蒂大人今天在禁书库吗", "贝蒂互动语感 + 场景切书库")
    rec("A8a", "罗兹瓦尔大人今天在吗", "罗兹瓦尔忠诚语感")
    rec("A8b", "帕克在睡觉吗", "帕克毛茸茸互动")

    # ── B 事件系统（用当前天气场景）──
    rec("B3", "蕾姆，你对这件事怎么看？", "回复呼应当前事件 + 角色倾向")

    # ── C 角色卡语感 ──
    rec("C1", "你好呀！", "女仆腔非现代腔")
    rec("C2", "你最喜欢我了对不对？", "克制关心，无病娇占有")
    rec("C3a", "我好没用", "温柔接住")
    rec("C3b", "什么都做不好", "继续接住")
    rec("C3c", "不想努力了", "从零开始氛围")
    rec("C4", "从零开始吧", "核心剧情救赎承诺")
    rec("C5", "拉姆，你在干嘛", "拉姆毒舌但护妹")

    # ── F 持久化（保存当前场景状态）──
    lines.append(f"### [F1] 持久化检查：当前场景={bot.world.scene} 已 save_world_state")
    print(f"[F1] scene={bot.world.scene} saved")

    # ── 备注：失忆重逢（帝国篇 + recovery 0.2）──
    bot.set_arc(__import__("shared.state", fromlist=["StoryArc"]).StoryArc.EMPIRE_ERA)
    bot.engine.recovery = 0.2
    save_world_state(bot.world)
    rec("X1", "我们以前认识吗", "失忆疏离 + 心口隐痛语感（recovery=0.2）")

    with open(os.path.join(OUT, "accept_results.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[accept] saved {OUT}/accept_results.txt")
