"""Re:Zero 双子系统 —— 图形界面聊天窗口。

双击运行或启动后弹出窗口，像 QQ/微信一样聊天。
自动保存聊天记录和好感度到 data/memory.json，重启后记忆恢复。
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import scrolledtext, font as tkfont

# 确保项目根目录在路径中
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from local import ReZeroTwinSystem
from shared.state import StoryArc
from shared.memory_store import MemoryStore

# 加载 .env（EXE 同级目录 → 项目根目录 → 当前工作目录）
from shared.config import load_env

load_env()


class TwinChatApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Re:Zero 双子系统")
        self.root.geometry("720x560")
        self.root.configure(bg="#fafafa")
        self.root.minsize(560, 400)

        # 记忆存储（frozen → EXE 同级 data/；源码 → 项目根 data/）
        self.store = MemoryStore()
        mem = self.store.load()

        # LLM 异步回复队列与等待标记
        self._reply_queue = queue.Queue()
        self._waiting_reply = False

        # 模式选择：local 或 llm
        self.mode = mem.get("mode", "llm")
        if self.mode == "llm":
            try:
                from llm import ReZeroLLMBridge

                api_key = os.getenv("DEEPSEEK_API_KEY")
                self.bot = ReZeroLLMBridge(
                    api_key=api_key,
                    base_url="https://api.deepseek.com",
                    model_name="deepseek-chat",
                    arc=StoryArc(mem.get("arc", "mansion_era")),
                    max_history=8,
                )
                self.bot.engine.favor = mem.get("favor", 15)
                self.bot.engine.ram_favor = mem.get("ram_favor", 8)
                self.bot.engine.independence = mem.get("independence", 0.25)
                self.bot.engine.recovery = mem.get("recovery", 1.0)
            except Exception as e:
                # 缺少 API Key / 依赖时提示并回退本地模板模式，避免无声闪退
                from tkinter import messagebox

                messagebox.showwarning(
                    "LLM 模式不可用",
                    f"{e}\n\n请将包含 DEEPSEEK_API_KEY 的 .env 放到程序同目录。\n"
                    "本次启动将使用本地模板模式。",
                )
                self.mode = "local"
        if self.mode != "llm":
            self.bot = ReZeroTwinSystem()
            self.bot.rem.engine.favor = mem.get("favor", 15)
            self.bot.rem.engine.ram_favor = mem.get("ram_favor", 8)
            self.bot.rem.engine.independence = mem.get("independence", 0.25)
            self.bot.rem.engine.recovery = mem.get("recovery", 1.0)
            try:
                self.bot.set_arc(StoryArc(mem.get("arc", "mansion_era")))
            except ValueError:
                self.bot.set_arc(StoryArc.MANSION_ERA)

        # 字体
        self.font_role = tkfont.Font(family="Microsoft YaHei", size=10, weight="bold")
        self.font_text = tkfont.Font(family="Microsoft YaHei", size=11)
        self.font_input = tkfont.Font(family="Microsoft YaHei", size=11)

        # 顶部标题
        header = tk.Frame(root, bg="#4a90e2", height=48)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)
        title = tk.Label(
            header,
            text="Re:Zero 双子系统",
            font=("Microsoft YaHei", 14, "bold"),
            bg="#4a90e2",
            fg="white",
        )
        title.pack(side=tk.LEFT, padx=15, pady=8)

        # 聊天记录区
        self.chat_area = scrolledtext.ScrolledText(
            root,
            wrap=tk.WORD,
            font=self.font_text,
            bg="#ffffff",
            fg="#333333",
            padx=12,
            pady=12,
            state="disabled",
            relief="flat",
            borderwidth=0,
        )
        self.chat_area.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # 标签样式
        self.chat_area.tag_config("role", font=self.font_role, spacing1=4, spacing3=2)
        self.chat_area.tag_config("user", foreground="#2c3e50", spacing3=6)
        self.chat_area.tag_config("rem", foreground="#e91e63", spacing3=6)
        self.chat_area.tag_config("ram", foreground="#9c27b0", spacing3=6)
        self.chat_area.tag_config("system", foreground="#7f8c8d", spacing3=6)

        # 输入区
        input_frame = tk.Frame(root, bg="#fafafa")
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 10))

        self.input_box = tk.Text(
            input_frame,
            height=3,
            font=self.font_input,
            wrap=tk.WORD,
            relief="solid",
            borderwidth=1,
            bg="white",
            fg="#333333",
            padx=8,
            pady=6,
        )
        self.input_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.input_box.focus_set()

        self.send_btn = tk.Button(
            input_frame,
            text="发送",
            command=self.on_send,
            font=("Microsoft YaHei", 11),
            bg="#4a90e2",
            fg="white",
            activebackground="#357abd",
            relief="flat",
            width=8,
        )
        self.send_btn.pack(side=tk.RIGHT, padx=(8, 0), fill=tk.Y)

        # 回车发送，Shift+回车换行
        self.input_box.bind("<Return>", self.on_enter)
        self.input_box.bind("<Shift-Return>", self.on_shift_enter)

        # 状态栏
        self.status_var = tk.StringVar(value="本地模板模式 | 宅邸篇")
        status_bar = tk.Label(
            root,
            textvariable=self.status_var,
            bd=1,
            relief=tk.SUNKEN,
            anchor=tk.W,
            font=("Microsoft YaHei", 9),
            bg="#f0f0f0",
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.load_history()
        self.update_status()

    def append_message(self, role: str, content: str, tag: str = "") -> None:
        self.chat_area.config(state="normal")
        self.chat_area.insert(tk.END, f"{role}\n", "role")
        self.chat_area.insert(tk.END, f"{content}\n\n", tag if tag else "normal")
        self.chat_area.config(state="disabled")
        self.chat_area.see(tk.END)

    def load_history(self) -> None:
        history = self.store.get("chat_history", [])
        for item in history[-50:]:
            role = item.get("role", "系统")
            content = item.get("content", "")
            if role == "你":
                self.append_message(role, content, "user")
            elif role in ("蕾姆", "拉姆"):
                self.append_message(role, content, "rem" if role == "蕾姆" else "ram")
            else:
                self.append_message(role, content, "system")
        if not history:
            self.append_message(
                "系统",
                "欢迎来到 Re:Zero 双子系统。\n输入消息开始和蕾姆、拉姆对话。\n输入 /status 查看状态，/empire /mansion /late 切换篇章，/quit 退出。",
                "system",
            )

    def on_enter(self, event: tk.Event) -> str:
        self.on_send()
        return "break"

    def on_shift_enter(self, event: tk.Event) -> None:
        # 允许默认换行行为
        pass

    def on_send(self) -> None:
        if self._waiting_reply:
            return
        text = self.input_box.get("1.0", tk.END).strip()
        if not text:
            return
        self.input_box.delete("1.0", tk.END)
        self.append_message("你", text, "user")
        self.store.append_chat("你", text)

        lowered = text.lower()
        if lowered in ("/quit", "quit", "退出"):
            self.root.destroy()
            return
        if lowered == "/status":
            reply = self.bot.status()
            self.append_message("系统", reply, "system")
            return
        if lowered == "/empire":
            self.bot.set_arc(StoryArc.EMPIRE_ERA)
            self.store.set("arc", StoryArc.EMPIRE_ERA.value)
            self.append_message("系统", "→ 已切换至帝国篇（失忆）", "system")
            self.update_status()
            return
        if lowered == "/mansion":
            self.bot.set_arc(StoryArc.MANSION_ERA)
            self.store.set("arc", StoryArc.MANSION_ERA.value)
            self.append_message("系统", "→ 已切换回宅邸篇", "system")
            self.update_status()
            return
        if lowered == "/late":
            self.bot.set_arc(StoryArc.LATE_ARC)
            self.store.set("arc", StoryArc.LATE_ARC.value)
            self.append_message("系统", "→ 已切换至后期篇章", "system")
            self.update_status()
            return
        if lowered.startswith("/recover"):
            parts = text.split()
            try:
                p = float(parts[1]) if len(parts) > 1 else 1.0
            except ValueError:
                p = 1.0
            self.bot.recover(p)
            self.store.set("recovery", p)
            self.append_message("系统", f"→ 记忆恢复进度设为 {p}", "system")
            self.update_status()
            return

        if self.mode == "llm":
            # LLM 网络调用放入后台线程，避免阻塞 Tkinter 主线程
            self._set_waiting(True)
            threading.Thread(
                target=self._fetch_llm_reply, args=(text,), daemon=True
            ).start()
            self.root.after(100, self._poll_reply)
            return

        try:
            raw_reply = self.bot.interact(text)
        except Exception as e:
            raw_reply = f"【系统】调用失败：{e}"
        self._handle_reply(raw_reply)

    def _fetch_llm_reply(self, text: str) -> None:
        """后台线程：调用 LLM 并把结果放入队列（线程内不触碰任何 Tkinter 控件）。"""
        try:
            reply = self.bot.chat(text)
        except Exception as e:
            reply = f"【系统】调用失败：{e}"
        self._reply_queue.put(reply)

    def _poll_reply(self) -> None:
        """主线程轮询回复队列，收到后交 _handle_reply 处理。"""
        try:
            reply = self._reply_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_reply)
            return
        self._set_waiting(False)
        self._handle_reply(reply)

    def _set_waiting(self, waiting: bool) -> None:
        """等待 LLM 回复期间禁用输入，防止并发发送。"""
        self._waiting_reply = waiting
        state = "disabled" if waiting else "normal"
        self.input_box.config(state=state)
        self.send_btn.config(state=state)
        if waiting:
            self.status_var.set("LLM 桥接模式 | 等待双子回复…")
        else:
            self.input_box.focus_set()

    def _handle_reply(self, raw_reply: str) -> None:
        """解析双子回复并持久化状态（local / llm 共用）。"""
        lines = raw_reply.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("【蕾姆】:"):
                content = line[len("【蕾姆】:"):].strip().strip('"')
                self.append_message("蕾姆", content, "rem")
                self.store.append_chat("蕾姆", content)
            elif line.startswith("【拉姆】:"):
                content = line[len("【拉姆】:"):].strip().strip('"')
                self.append_message("拉姆", content, "ram")
                self.store.append_chat("拉姆", content)
            else:
                if line:
                    self.append_message("系统", line, "system")
                    self.store.append_chat("系统", line)

        # 持久化当前状态
        if self.mode == "llm":
            engine = self.bot.engine
        else:
            engine = self.bot.rem.engine
        self.store.set("favor", engine.favor)
        self.store.set("ram_favor", engine.ram_favor)
        self.store.set("independence", engine.independence)
        self.store.set("recovery", engine.recovery)
        self.store.set("mode", self.mode)
        self.update_status()

    def update_status(self) -> None:
        if self.mode == "llm":
            state = self.bot.engine.snapshot()
        else:
            state = self.bot.rem.engine.snapshot()
        mode_text = "本地模板模式" if self.mode == "local" else "LLM 桥接模式"
        self.status_var.set(
            f"{mode_text} | 篇章：{state.arc.value} | "
            f"蕾姆好感：{state.favor}/100 | 拉姆：{state.ram_stage.value} | "
            f"独立度：{state.independence:.2f}"
        )


def main() -> None:
    root = tk.Tk()
    TwinChatApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
