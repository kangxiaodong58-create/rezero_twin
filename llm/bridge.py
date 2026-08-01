"""LLM 桥接模式：硬状态机 + 大模型生成台词。

需要安装 openai：
    pip install openai
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from shared.config import load_env

load_env()

from shared.state import StoryArc, WorldState, StructuredProfile
from shared.prompts import PromptBuilder
from shared.state import HardStateEngine


_DEFAULT_KEY = "your-api-key-here"
_VERSION = "10.0.1"  # 懒加载修复版本


def _get_openai():
    """懒加载 openai，避免模块级导入阻断切换模式。"""
    try:
        from openai import OpenAI as _OpenAI
        return _OpenAI
    except ImportError as _e:
        raise ImportError(
            "请先安装 openai 库：pip install openai\n"
            "如果已安装，请检查 Python 环境是否正确。"
        ) from _e


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
        OpenAI = _get_openai()
        self.client = OpenAI(
            api_key=key,
            base_url=base_url,
        )
        self.model_name = model_name
        self.engine = HardStateEngine(arc=arc)
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.world: Optional[WorldState] = None  # 可由 GUI 注入持久化世界状态

    def _build_messages(self, user_input: str) -> List[Dict[str, Any]]:
        state = self.engine.update(user_input)
        world = self.world or WorldState.now()
        profile = StructuredProfile.from_engine(self.engine)
        system_prompt = PromptBuilder.build(state, world=world, profile=profile)
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(self.history[-self.max_history:])
        messages.append({"role": "user", "content": user_input})
        return messages, state

    def chat(
        self,
        user_input: str,
        *,
        temperature: float = 0.65,
        max_tokens: int = 600,
    ) -> str:
        messages, _state = self._build_messages(user_input)
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

    def chat_stream(self, user_input: str, *, temperature: float = 0.65, max_tokens: int = 600):
        """流式聊天：返回 (generator, state_snapshot)。"""
        messages, state = self._build_messages(user_input)
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )

            def _generator():
                full = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        full += delta
                        yield delta
                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": full})

            return _generator(), state
        except Exception as e:
            def _err():
                yield f"【系统】API 调用失败：{e}"
            return _err(), state

    def status(self) -> str:
        state = self.engine.snapshot()
        d = state.to_prompt_dict()
        lines = [f"{k}: {v}" for k, v in d.items()]
        return "===== 当前硬状态 =====\n" + "\n".join(lines)

    def set_arc(self, arc: StoryArc) -> None:
        self.engine.set_arc(arc)

    def recover(self, progress: float = 1.0) -> None:
        self.engine.recover(progress)

    def raw_completion(self, system_prompt: str, user_prompt: str = "", *, temperature: float = 0.8, max_tokens: int = 200) -> str:
        """原始 API 调用（不经角色 system prompt）。用于开场引言等独立生成。"""
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"（{e}）"
