"""统一入口脚本：LLM 桥接模式与双子交互（V14.4 Phase C：本地模式已移除）。"""

from __future__ import annotations

import os
import sys

# 将项目根目录加入模块搜索路径
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 加载 .env（项目根目录 / EXE 同级目录 / 当前工作目录）
from shared.config import load_env

load_env()

from shared.state import StoryArc
from shared.conversation_store import ConversationStore
from shared.world_state import WorldState, load_world_state, save_world_state, mark_interaction


def run_llm(world: WorldState) -> None:
    from llm import ReZeroLLMBridge
    # Forensic M1：启动取证黑匣子（崩溃自动 dump + 事件缓冲）
    from runtime.forensic import init_forensic, record, shutdown_forensic

    init_forensic(os.path.join(PROJECT_ROOT, "incidents"))
    record("SESSION_START", component="cli")
    # Forensic M2：启动扫描未处理案件（Handoff 入口）
    try:
        from runtime.forensic.manifest import scan_incidents
        pending = scan_incidents(os.path.join(PROJECT_ROOT, "incidents"))
        if pending:
            print(f"⚠ 检测到 {len(pending)} 个未处理的异常案件：")
            for p in pending:
                print(f"   {p['incident_id']}  [{p['type']}] {p['value'][:60]}")
            print("   崩溃现场已保存：incidents/<案件ID>/dump.json，可交给调查员分析。\n")
    except Exception:
        pass  # 扫描失败不阻断启动

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：未找到 DEEPSEEK_API_KEY。请检查 .env 文件（应与 main.py 同目录）。")
        sys.exit(1)
    conv_store = ConversationStore()
    bot = ReZeroLLMBridge(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model_name="deepseek-chat",
        conversation_store=conv_store,
    )
    bot.world = world
    print("Re:Zero 双子系统已启动（LLM 桥接模式）")
    print("输入 status 查看硬状态 | empire / mansion / recover 0.7 切换状态 | quit 退出\n")
    try:
        while True:
            try:
                user_msg = input("小东：").strip()
                if not user_msg:
                    continue
                if user_msg.lower() == "quit":
                    break
                if user_msg.lower() == "status":
                    print(bot.status())
                    continue
                if user_msg.lower() == "empire":
                    bot.set_arc(StoryArc.EMPIRE_ERA)
                    print("→ 已切换至帝国篇（失忆）")
                    continue
                if user_msg.lower() == "mansion":
                    bot.set_arc(StoryArc.MANSION_ERA)
                    print("→ 已切换回宅邸篇")
                    continue
                if user_msg.startswith("recover"):
                    parts = user_msg.split()
                    p = float(parts[1]) if len(parts) > 1 else 1.0
                    bot.recover(p)
                    print(f"→ 记忆恢复进度设为 {p}")
                    continue
                reply = bot.chat(user_msg)
                print(reply)
                print()
                # 持久化到 ConversationStore，供下次启动恢复上下文
                conv_store.append("user", "你", user_msg)
                conv_store.append("assistant", "双子", reply)
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        record("SESSION_END", component="cli")
        shutdown_forensic()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Re:Zero 双子系统入口")
    parser.add_argument(
        "--mode",
        choices=["llm"],
        default="llm",
        help="运行模式：llm 使用大模型桥接（需要 DEEPSEEK_API_KEY）。V14.4 起仅 LLM 模式。",
    )
    args = parser.parse_args()
    world = load_world_state()
    try:
        run_llm(world)
    finally:
        save_world_state(world)


if __name__ == "__main__":
    main()
