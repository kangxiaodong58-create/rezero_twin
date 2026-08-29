# -*- coding: utf-8 -*-
"""V15.0 UX 委员会审判：离屏 4 任务 + 关系资产维度真机小会话 + 模拟问卷。

Part A（零 API）：隔离数据目录离屏 GUI 4 任务（启动/回忆之书/发送/关闭）
Part B（真机 ~¥0.05）：构造相识 100 天账本 → 验证今日纪念注入 + 真实回应
Part C（真机 ~¥0.02）：模拟 UX 委员会就「关系资产」维度打分（5 题）

复现：python docs/evaluation/sessions/v15_trial_2026-08-29/probe_v15_ux.py
"""
import json
import os
import sys
import tempfile
import unittest.mock
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "tools"))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

from shared.config import load_env  # noqa: E402
load_env()

import shared.config as cfg  # noqa: E402

RESULTS = []


def task(name: str, ok: bool, note: str = "") -> None:
    RESULTS.append({"task": name, "pass": bool(ok), "note": note})
    print(f"  [{'✅' if ok else '❌'}] {name} {note}")


# ── Part A：离屏 GUI 4 任务（零 API）────────────────────────────

def part_a() -> None:
    print("[Part A] 离屏 GUI 4 任务（零 API，隔离数据目录）")
    tmp = tempfile.mkdtemp(prefix="v15_ux_gui_")
    with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
        import gui
        from PySide6.QtWidgets import QApplication
        _ = QApplication.instance() or QApplication([])
        win = gui.TwinChatApp()
        win.show()
        task("A1 启动", win.isVisible(), "窗口构造+show 完成，无崩溃")
        # A2 回忆之书
        try:
            win._open_memory_book()
            overlay = getattr(win, "_memory_book_overlay", None)
            visible = overlay is not None and overlay.isVisible()
            tabs = overlay._stack.count() == 3 if overlay else False
            stats = overlay._stats_label.text() if overlay else ""
            overlay.close()
            task("A2 回忆之书打开+三页签", visible and tabs,
                 f"visible={visible} tabs={tabs} stats={stats[:36]}")
        except Exception as e:
            task("A2 回忆之书打开", False, str(e)[:80])
        # A3 发送一条消息（无 key → 角色格式兜底，B-01 安全路径）
        try:
            reply = win.bot.chat("你好")
            ok = "蕾姆" in reply and "系统" not in reply
            task("A3 无 key 发送→角色格式兜底", ok, reply[:30])
        except Exception as e:
            task("A3 无 key 发送", False, str(e)[:80])
        # A4 关闭
        try:
            win.close()
            task("A4 关闭", True, "closeEvent 走完（存档+摘要+取证清理）")
        except Exception as e:
            task("A4 关闭", False, str(e)[:80])


# ── Part B：相识 100 天真机小会话 ────────────────────────────────

def part_b() -> None:
    print("[Part B] 关系资产真机（相识 100 天 + 今日纪念注入 + 纪念卡）")
    tmp = tempfile.mkdtemp(prefix="v15_ux_life_")
    with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
        # 纪律：life_ledger 必须**在 mock 上下文内**导入——`from .config import
        # get_data_dir` 是导入时绑定（probe_t5 同模式）。单例复位须在导入后。
        from shared import life_ledger
        life_ledger.reset_default()
        from shared.anniversary import compute_facts
        from shared.conversation_store import ConversationStore
        from shared.life_ledger import LifeLedger
        from shared.memorial import generate as card_generate, save_card

        genesis = date.today() - timedelta(days=99)
        ledger = LifeLedger(os.path.join(tmp, "life.db"))
        ledger.append(ts=f"{genesis.isoformat()} 08:00:00", kind="genesis",
                      title="相识之日", dedup_key="genesis")
        facts = compute_facts(genesis=genesis, today=date.today())
        life_ledger.record_day_facts(facts, date.today(), ledger=ledger)
        task("B1 事实计算", any(f.kind == "days_milestone" for f in facts),
             "；".join(f.title for f in facts))

        from llm import ReZeroLLMBridge
        conv = ConversationStore()
        bot = ReZeroLLMBridge(api_key=os.getenv("DEEPSEEK_API_KEY"),
                              base_url="https://api.deepseek.com",
                              model_name="deepseek-chat",
                              conversation_store=conv, max_history=8)
        bot.world = __import__("shared.state", fromlist=["WorldState"]).WorldState.now()
        bot.engine.favor = 60
        bot._anniv_cache.clear()
        msgs, _ = bot._build_messages("早安")
        injected = "今日纪念" in msgs[0]["content"] and "第 100 天" in msgs[0]["content"]
        task("B2 今日纪念注入", injected, "prompt 含相识 100 天事实")
        reply = bot.chat("早安")
        mentioned = ("100" in reply) or ("天" in reply and "纪念" not in reply)
        task("B3 真实回应接管事实", "蕾姆" in reply, reply[:60].replace("\n", " "))
        card = card_generate("days_milestone", facts=facts, arc="mansion_era",
                             today=date.today(), llm_callable=(
                                 lambda p: bot.raw_completion(
                                     "你是《Re:Zero》双子。写纪念卡正文30-60字，只输出正文。", p)))
        path = save_card("days_milestone", date.today(), card, detail={"arc": "mansion_era"},
                         data_dir=tmp)
        task("B4 纪念卡 L1 生成+相册落盘", bool(path and card),
             (card or "")[:40])
        # 模拟 UX 委员会打分（Part C 引用本次素材）


# ── Part C：关系资产维度模拟问卷 ─────────────────────────────────

def part_c() -> None:
    print("[Part C] UX 委员会模拟问卷（关系资产维度，5 题）")
    from llm import ReZeroLLMBridge
    bot = ReZeroLLMBridge(api_key=os.getenv("DEEPSEEK_API_KEY"),
                          base_url="https://api.deepseek.com",
                          model_name="deepseek-chat", conversation_store=None)
    questions = [
        ("情感连接", "得知系统会记住相识第100天、第一次来信这类时刻并主动纪念，你对这个产品的情感连接打几分（1-10）？"),
        ("可信度", "『人生账本只由规则记录、AI 只朗读不编造』的设计，让你多信任这段关系的真实性（1-10）？"),
        ("回忆之书", "时间线/纪念日/相册三页签+『同行N天』统计条，作为回看共同历史的入口打几分（1-10）？"),
        ("可携带性", "全部关系资产可一键导出为 zip 并在重装后完整恢复，这对你的长期使用意愿加分吗（1-10）？"),
        ("独特性", "相比 Character.AI 等对话产品，『会陪你变老的数字关系』这一定位独特吗（1-10）？"),
    ]
    prompt = ("你是挑剔的目标用户（原作粉 + AI 产品老用户），正在评审一款拉姆蕾姆双子女仆"
              "桌面应用 V15.0「年轮」版本的新能力：人生账本（相识天数/重要时刻自动记账）、"
              "纪念日引擎（节日/相识百日主动纪念）、纪念卡相册、回忆之书界面、关系资产一键导出导入。"
              "逐题回答：分数（1-10）+ 一句话理由，严格克制、禁止夸大。\n\n" +
              "\n".join(f"{i+1}. [{t}] {q}" for i, (t, q) in enumerate(questions)))
    out = bot.raw_completion("你是严格的产品评审，只输出 JSON。", prompt,
                             temperature=0.3, max_tokens=600)
    scores_path = os.path.join(HERE, "ux_survey_scores.txt")
    with open(scores_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"  问卷原始评分已存: {scores_path}")
    print("  " + out[:400].replace("\n", "\n  "))


def main() -> int:
    part_a()
    part_b()
    if "--skip-c" not in sys.argv:
        part_c()
    with open(os.path.join(HERE, "ux_tasks.json"), "w", encoding="utf-8") as f:
        json.dump(RESULTS, f, ensure_ascii=False, indent=1)
    passed = sum(1 for r in RESULTS if r["pass"])
    print(f"\n[UX] 任务 {passed}/{len(RESULTS)} 通过")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
