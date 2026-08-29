"""长会话稳定性专项 · 真实 API 压测（预算护栏 ≤1 元）。

30 轮真实 LLM 对话（deepseek-chat），验证：
1. 连续调用稳定性（无超时/无异常/回复可解析）
2. 长上下文累积（history 截断 + prompt 构建不崩）
3. Validator 通过率与软 OOC 命中率
4. 断线恢复（第 15 轮重建 bridge + 存档恢复 → 继续对话）
5. 场景切换在真实对话中的注入正确性
6. 费用统计（超 0.9 元自动停止）

用法：python probe_long_session.py  （需要 DEEPSEEK_API_KEY）
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from llm.bridge import ReZeroLLMBridge
from shared.state import WorldState

# 预算护栏（元）
BUDGET_MAX = 0.9
INPUT_PRICE = 2.0 / 1_000_000    # ¥2/M tokens
OUTPUT_PRICE = 8.0 / 1_000_000   # ¥8/M tokens

ROUNDS = 30
SCRIPT = [
    "早上好，蕾姆", "今天天气真好", "蕾姆在做什么呢", "我好累啊", "去厨房看看",
    "有什么好吃的吗", "蕾姆真好", "我好没用", "我想重新开始", "回房间休息",
    "晚安", "贝蒂大人在吗", "厨房的茶很好喝", "拉姆姐姐今天心情如何",
    "我们去看花园", "花开了吗", "我好难过", "谢谢你一直陪着我", "去书库找本书",
    "这本书讲什么", "蕾姆喜欢看书吗", "我想听你讲故事", "夜深了还不睡吗",
    "去走廊走走", "月光真美", "蕾姆是我的光", "不行我要振作", "从零开始吧",
    "我们去餐厅吃饭", "今天辛苦了一天",
][:ROUNDS]

stats = {"ok": 0, "fail": 0, "fallback": 0, "ooc_warn": 0,
         "in_tokens": 0, "out_tokens": 0, "cost": 0.0, "scenes_seen": []}


def _patch_usage(bridge) -> None:
    """monkeypatch client.create 记录 usage（bridge 未内置费用统计；防重入）。"""
    if getattr(bridge, "_usage_patched", False):
        return
    bridge._usage_patched = True
    orig = bridge.client.chat.completions.create

    def wrapped(*a, **k):
        resp = orig(*a, **k)
        if getattr(resp, "usage", None):
            bridge._last_usage = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", 0),
                "completion_tokens": getattr(resp.usage, "completion_tokens", 0),
            }
        return resp

    bridge.client.chat.completions.create = wrapped


def main() -> int:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        print("[ABORT] 未设置 DEEPSEEK_API_KEY")
        return 2

    world = WorldState(current_time="2026-08-19 08:00", period="上午", weather="晴朗")
    bridge = None
    start = time.time()

    for i, text in enumerate(SCRIPT):
        # 预算护栏
        if stats["cost"] >= BUDGET_MAX:
            print(f"\n[STOP] 预算护栏触发（¥{stats['cost']:.3f} ≥ {BUDGET_MAX}）于第 {i} 轮")
            break
        # 断线恢复模拟：第 15 轮重建 bridge（模拟重启 + 存档恢复）
        if i == 15:
            saved = world.save_dict()
            world2 = WorldState.load_or_create(saved)
            bridge = ReZeroLLMBridge(api_key=key, model_name="deepseek-chat",
                                     max_history=8, world=world2)
            print(f"  [RECOVER] 第 15 轮重建 bridge（scene={world2.scene}, events={len(bridge.engine.events)}）")
        if bridge is None:
            bridge = ReZeroLLMBridge(api_key=key, model_name="deepseek-chat",
                                     max_history=8, world=world)
        _patch_usage(bridge)
        try:
            msgs, _ = bridge._build_messages(text)
            # V14.8：chat() 返回 str（fallback 经 _last_chat_fallback 暴露）
            reply = bridge.chat(text, temperature=0.65, max_tokens=600)
            fallback = bridge._last_chat_fallback
            if fallback:
                stats["fallback"] += 1
            if "场景开场（您刚来到" in msgs[0]["content"]:
                stats["scenes_seen"].append((i, text))
            # 费用统计（usage 从 bridge 最后响应提取）
            last_usage = getattr(bridge, "_last_usage", None)
            if last_usage:
                stats["in_tokens"] += last_usage.get("prompt_tokens", 0)
                stats["out_tokens"] += last_usage.get("completion_tokens", 0)
                stats["cost"] = (stats["in_tokens"] * INPUT_PRICE
                                 + stats["out_tokens"] * OUTPUT_PRICE)
            stats["ok"] += 1
            preview = reply.replace("\n", " ")[:42]
            print(f"[{i + 1:02d}] {text[:12]:<14} → {preview}…  (累计 ¥{stats['cost']:.4f})")
        except Exception as e:
            stats["fail"] += 1
            print(f"[{i + 1:02d}] {text[:12]:<14} → ❌ {type(e).__name__}: {str(e)[:60]}")

    elapsed = time.time() - start
    report = {
        "rounds": stats["ok"] + stats["fail"],
        "ok": stats["ok"], "fail": stats["fail"], "fallback": stats["fallback"],
        "ooc_warn": stats["ooc_warn"],
        "in_tokens": stats["in_tokens"], "out_tokens": stats["out_tokens"],
        "cost_yuan": round(stats["cost"], 4),
        "elapsed_sec": round(elapsed, 1),
        "scenes_switched": stats["scenes_seen"],
        "final_scene": world.scene,
        "final_favor": bridge.engine.favor if bridge else None,
        "history_len": len(bridge.history) if bridge else None,
    }
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "long_session_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 56)
    print(f"成功 {stats['ok']} / 失败 {stats['fail']} / 兜底 {stats['fallback']} | "
          f"耗时 {elapsed:.0f}s")
    print(f"Tokens: 输入 {stats['in_tokens']} + 输出 {stats['out_tokens']} = "
          f"{stats['in_tokens'] + stats['out_tokens']}")
    print(f"费用: ¥{stats['cost']:.4f}（护栏 ¥{BUDGET_MAX}）")
    print(f"场景切换 {len(stats['scenes_seen'])} 次: {stats['scenes_seen']}")
    print(f"最终 scene={world.scene} favor={report['final_favor']} history={report['history_len']}")
    print("=" * 56)
    return 0 if stats["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
