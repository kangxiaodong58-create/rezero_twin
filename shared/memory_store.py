"""本地长期记忆存储。

将用户昵称、好感度、拉姆阶段、鬼化、记忆恢复进度、聊天历史等
保存到项目目录的 data/memory.json 中，程序重启后可恢复。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .config import get_data_dir


class MemoryStore:
    def __init__(self, root_dir: Optional[str] = None) -> None:
        if root_dir is not None:
            # 显式指定：保持原有语义（root_dir 下建 data/）
            self.root = root_dir
            self.data_dir = os.path.join(self.root, "data")
        else:
            # 默认：统一解析（frozen → EXE 同级 data/；源码 → 项目根 data/）
            self.data_dir = get_data_dir()
            self.root = os.path.dirname(self.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "memory.json")

    def load(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        defaults = {
            "user_name": None,
            "favor": 15,
            "ram_favor": 8,
            "independence": 0.25,
            "recovery": 1.0,
            "arc": "mansion_era",
            "chat_history": [],
            "mode": "llm",
            "events": [],
        }
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            pass
        for key, value in defaults.items():
            data.setdefault(key, value)
        return data

    def save(self, data: Dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def append_chat(self, role: str, content: str) -> None:
        data = self.load()
        history: List[Dict[str, str]] = data.get("chat_history", [])
        history.append({"role": role, "content": content})
        # 只保留最近 200 条
        if len(history) > 200:
            history = history[-200:]
        data["chat_history"] = history
        self.save(data)
