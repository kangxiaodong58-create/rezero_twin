"""LLM 桥接模式：硬状态机 + 大模型生成台词。

需要安装 openai：
    pip install openai
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional

# 确保项目根目录在 import 路径中
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from shared.config import load_env

load_env()

try:
    from openai import OpenAI
except ImportError as _e:
    raise ImportError("请先安装 openai 库：pip install openai") from _e

from shared.state import StoryArc
from shared.prompts import PromptBuilder
from shared.state import HardStateEngine


_DEFAULT_KEY = "your-api-key-here"


class ReZeroLLMBridge:
    """通过状态机约束 + System Prompt 驱动 LLM 生成双子回复。"""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        model_name: str = "deepseek-chat",
        arc: StoryArc = StoryArc.MANSION_ERA,
        max_history: int = 8,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY") or _DEFAULT_KEY
        if not key or key == _DEFAULT_KEY:
            raise ValueError("未提供 DEEPSEEK_API_KEY。请在 .env 文件中设置或传入环境变量。")
        self.client = OpenAI(
            api_key=key,
            base_url=base_url,
        )
        self.model_name = model_name
        self.engine = HardStateEngine(arc=arc)
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history

    def chat(
        self,
        user_input: str,
        *,
        temperature: float = 0.65,
        max_tokens: int = 600,
    ) -> str:
        state = self.engine.update(user_input)
        system_prompt = PromptBuilder.build(state)

        messages: List[Dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt,
            }
        ]
        messages.extend(self.history[-self.max_history:])
        messages.append({"role": "user", "content": user_input})

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            reply = response.choices[0].message.content.strip()
        except Exception as e:
            return f"【系统】API 调用失败：{e}"

        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})
        return reply

    def status(self) -> str:
        state = self.engine.snapshot()
        d = state.to_prompt_dict()
        lines = [f"{k}: {v}" for k, v in d.items()]
        return "===== 当前硬状态 =====\n" + "\n".join(lines)

    def set_arc(self, arc: StoryArc) -> None:
        self.engine.set_arc(arc)

    def recover(self, progress: float = 1.0) -> None:
        self.engine.recover(progress)
