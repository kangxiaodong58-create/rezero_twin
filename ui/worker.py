"""LLM 后台线程——SPEC-22 S1b 自 gui.py 逐字归位。"""

from __future__ import annotations

from typing import Optional
from PySide6.QtCore import QObject, Signal
from ui.logging_util import _log


class LLMWorker(QObject):
    """后台线程：调用 LLM 生成回复（不冻结 UI）。"""
    finished = Signal(str)           # 完整回复文本
    stream_token = Signal(str)       # 流式 token
    error = Signal(str)

    def __init__(self, bot, user_input: str, stream: bool = True, reply_to: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.bot = bot
        self.user_input = user_input
        self.stream = stream
        self.reply_to = reply_to  # V14.2：引用回复（透传 bridge）

    def cancel(self) -> None:
        """V13.0：主线程调用——中断底层 LLM 流，使 run() 尽快返回。"""
        try:
            cancel_fn = getattr(self.bot, "cancel_stream", None)
            if cancel_fn is not None:
                cancel_fn()
        except Exception as e:
            _log(f"LLMWorker.cancel 异常: {e}", durable=True)

    def run(self) -> None:
        try:
            if self.stream and hasattr(self.bot, 'chat_stream'):
                gen, _state = self.bot.chat_stream(self.user_input, reply_to=self.reply_to)  # V14.2：引用透传
                full = ""
                for token in gen:
                    full += token
                    self.stream_token.emit(token)
                self.finished.emit(full)
            else:
                reply = self.bot.chat(self.user_input, reply_to=self.reply_to)  # V14.2：引用透传
                self.finished.emit(reply)
        except Exception as e:
            self.error.emit(str(e))


