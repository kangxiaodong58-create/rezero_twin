"""统一入口脚本：选择本地模板模式或 LLM 桥接模式与双子系统交互。"""

from __future__ import annotations

import argparse
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
from local import ReZeroTwinSystem as LocalTwinSystem


def run_local(world: WorldState) -> None:
    sys_obj = LocalTwinSystem()
    print("Re:Zero 双子系统已启动（本地模板模式）")
    print("指令：status | empire | mansion | late | recover 0.6 | recover 1.0 | quit\n")
    while True:
        try:
            msg = input("小东：").strip()
            if not msg:
                continue
            if msg == "quit":
                break
            if msg == "status":
                print(sys_obj.status())
                continue
            if msg == "empire":
                sys_obj.set_arc(StoryArc.EMPIRE_ERA)
                print("→ 帝国篇失忆")
                continue
            if msg == "mansion":
                sys_obj.set_arc(StoryArc.MANSION_ERA)
                print("→ 宅邸篇")
                continue
            if msg == "late":
                sys_obj.set_arc(StoryArc.LATE_ARC)
                print("→ 后期篇章")
                continue
            if msg.startswith("recover"):
                parts = msg.split()
                p = float(parts[1]) if len(parts) > 1 else 1.0
                print(sys_obj.recover(p))
                continue
            print(sys_obj.interact(msg))
            print()
            mark_interaction(world)
        except (KeyboardInterrupt, EOFError):
            break


def run_llm(world: WorldState) -> None:
    from llm import ReZeroLLMBridge

    api_key = os.getenv("DEEPSEEK_API_KEY", "your-api-key-here")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Re:Zero 双子系统入口")
    parser.add_argument(
        "--mode",
        choices=["local", "llm"],
        default="local",
        help="运行模式：local 使用本地模板回复，llm 使用大模型桥接（需要 DEEPSEEK_API_KEY）",
    )
    args = parser.parse_args()
    world = load_world_state()
    try:
        if args.mode == "llm":
            run_llm(world)
        else:
            run_local(world)
    finally:
        save_world_state(world)


if __name__ == "__main__":
    main()
