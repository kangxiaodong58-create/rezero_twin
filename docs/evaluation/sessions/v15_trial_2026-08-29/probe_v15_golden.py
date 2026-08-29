# -*- coding: utf-8 -*-
"""V15.0 完整审判循环：黄金剧本 51 探针真机执行（角色委员会 L2）。

三套剧本（与 V14.9 基线同语料，trial_gate 首次版本 diff 的"当前侧"输入）：
  script_arc_roam_v148(11) / script_v148_scene_accept(8) / script_scene_walkthrough(32)

每套剧本独立隔离会话（临时数据目录 + 独立 bridge/store，favor=60 对齐 Trial#5）。
篇章按输入关键词映射（营地/旅店/荒野→帝国，营火/战场/军营/战斗→后期，
厨房/房间/宅邸/力量→宅邸），与基线 transcript 的 arc 语境对齐。

输出：
  v15_golden_raw.txt   逐轮一行 `[Sxx] arc=.. scene=.. (N.Ns) 输入 -> 回复`（fingerprint 可解析）
  v15_golden_meta.json 每轮时延/兜底标志 + 汇总（供审判报告引用）

成本预估：51 轮 × ~0.6s ≈ ¥0.2（¥2/次纪律内）。
复现：python docs/evaluation/sessions/v15_trial_2026-08-29/probe_v15_golden.py
"""
import json
import os
import sys
import tempfile
import time
import unittest.mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, PROJECT)

from shared.config import load_env  # noqa: E402
load_env()

import shared.config as cfg  # noqa: E402

OUT = HERE


def arc_for(text: str, current: str) -> str:
    if any(k in text for k in ("营地", "旅店", "荒野")):
        return "empire_era"
    if any(k in text for k in ("营火", "战场", "军营", "战斗")):
        return "late_arc"
    if any(k in text for k in ("厨房", "回房间", "宅邸", "力量")):
        return "mansion_era"
    return current


def main() -> int:
    from shared.state import StoryArc
    from shared.world_state import WorldState

    with open(os.path.join(PROJECT, "docs", "evaluation", "baselines",
                           "golden_inputs_v14_9.json"), encoding="utf-8") as f:
        golden = json.load(f)

    all_meta = {"scripts": [], "total_elapsed": 0.0}
    raw_lines = []
    seq = 0
    api_key = os.getenv("DEEPSEEK_API_KEY")
    assert api_key, "缺少 DEEPSEEK_API_KEY"

    for script in golden["scripts"]:
        sid = script["id"]
        tmp = tempfile.mkdtemp(prefix=f"v15_{sid}_")
        print(f"[{sid}] isolated: {tmp} | {len(script['inputs'])} 探针")
        arc = "mansion_era"
        turn_meta = []

        with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
            from llm import ReZeroLLMBridge
            from shared.conversation_store import ConversationStore

            conv = ConversationStore()
            bot = ReZeroLLMBridge(
                api_key=api_key,
                base_url="https://api.deepseek.com",
                model_name="deepseek-chat",
                conversation_store=conv,
                max_history=8,
            )
            bot.world = WorldState.now()
            bot.engine.favor = 60  # 对齐 Trial#5 语境

            for text in script["inputs"]:
                arc = arc_for(text, arc)
                bot.set_arc(StoryArc(arc))
                t0 = time.time()
                reply = bot.chat(text)
                dt = time.time() - t0
                all_meta["total_elapsed"] += dt
                seq += 1
                flat = "  ".join(reply.split())
                raw_lines.append(
                    f"[S{sid[:6].replace('_', '')}{seq:02d}] arc={arc} "
                    f"scene={bot.world.scene} ({dt:.1f}s) {text} -> {flat}")
                turn_meta.append({
                    "input": text, "arc": arc, "scene": bot.world.scene,
                    "sec": round(dt, 1),
                    "fallback": bool(bot._last_chat_fallback),
                })
                print(f"  [{seq:02d}] ({dt:.1f}s) {text[:18]} -> {flat[:46]}")
                conv.append("user", "你", text)
                conv.append("assistant", "双子", reply)

        all_meta["scripts"].append({"id": sid, "turns": turn_meta})

    raw_path = os.path.join(OUT, "v15_golden_raw.txt")
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write("\n".join(raw_lines) + "\n")
    fallbacks = sum(1 for s in all_meta["scripts"] for t in s["turns"] if t["fallback"])
    all_meta["summary"] = {
        "probes": seq,
        "fallbacks": fallbacks,
        "elapsed_sec": round(all_meta["total_elapsed"], 1),
        "est_cost_yuan": round(all_meta["total_elapsed"] * 0.0022, 2),
    }
    with open(os.path.join(OUT, "v15_golden_meta.json"), "w", encoding="utf-8") as f:
        json.dump(all_meta, f, ensure_ascii=False, indent=1)
    print(f"\n[done] {seq} 探针 | 兜底 {fallbacks} | "
          f"{all_meta['summary']['elapsed_sec']}s | 原始: {raw_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
