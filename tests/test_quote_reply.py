"""V14.2：引用回复测试（bridge Prompt 注入，零 API 费用）。

覆盖（验收）：
- chat_stream / chat 带 reply_to → system prompt 注入「用户引用了…」+ 引用摘要
- 无 reply_to → 不注入（既有行为零回归）
- 引用不进 history（仅本轮 Prompt，ephemeral）
- 引用不落库（user 句 content 保持原文，无双份污染）

用法：python tests/test_quote_reply.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm.bridge import ReZeroLLMBridge


class _Chunk:
    """openai SSE chunk 形状（choices[0].delta.content）。"""

    def __init__(self, c: str):
        self.choices = [type("C", (), {"delta": type("D", (), {"content": c})()})()]


class _Resp:
    """非流式响应形状（choices[0].message.content + usage 缺省安全）。"""

    def __init__(self, content: str):
        self.choices = [type("C", (), {"message": type("M", (), {"content": content})()})()]


class CaptureChat:
    """捕获 create() 收到的 messages，同时返回合法回复（流式/非流式）。"""

    def __init__(self):
        self.captured: list = []

    def create(self, **kw):
        self.captured.append(kw.get("messages", []))
        if kw.get("stream"):
            def g():
                yield _Chunk('【蕾姆】: "好的，小东大人。这段被引用的话，')
                yield _Chunk('蕾姆明白了。"')
            return g()
        return _Resp('【蕾姆】: "好的，小东大人。蕾姆明白了。"')


def _make_bot(capture: CaptureChat) -> ReZeroLLMBridge:
    bot = ReZeroLLMBridge(api_key="sk-test-not-used", conversation_store=None)
    bot.client = type("F", (), {"chat": type("C", (), {"completions": capture})()})()
    return bot


def test_stream_inject_quote() -> None:
    """chat_stream 带 reply_to → system prompt 注入引用。"""
    cap = CaptureChat()
    bot = _make_bot(cap)
    gen, _ = bot.chat_stream("那是什么意思？", reply_to={"preview": "暗号是夜枭"})
    for _ in gen:
        pass
    sys_msg = cap.captured[0][0]["content"]
    assert "用户引用了" in sys_msg, f"应注入引用段: {sys_msg[:80]}…"
    assert "暗号是夜枭" in sys_msg, f"应包含引用原文: {sys_msg[:80]}…"


def test_chat_inject_quote() -> None:
    """chat 带 reply_to → 同样注入。"""
    cap = CaptureChat()
    bot = _make_bot(cap)
    bot.chat("那是什么意思？", reply_to={"preview": "生日是3月15日"})
    sys_msg = cap.captured[0][0]["content"]
    assert "用户引用了" in sys_msg and "生日是3月15日" in sys_msg


def test_no_quote_no_inject() -> None:
    """无 reply_to → 不注入（既有行为）。"""
    cap = CaptureChat()
    bot = _make_bot(cap)
    bot.chat("普通问题")
    sys_msg = cap.captured[0][0]["content"]
    assert "用户引用了" not in sys_msg


def test_quote_not_in_history() -> None:
    """引用不进 history：成功轮 history 仅 user 原文 + assistant 回复。"""
    cap = CaptureChat()
    bot = _make_bot(cap)
    bot.chat("那是什么意思？", reply_to={"preview": "暗号是夜枭"})
    assert len(bot.history) == 2, f"history 应恰为 2 条: {len(bot.history)}"
    assert bot.history[0]["content"] == "那是什么意思？", "用户句应保持原文（无引用标记）"
    assert "用户引用了" not in bot.history[0]["content"]
    assert "用户引用了" not in bot.history[1]["content"]


def main() -> int:
    tests = [
        ("流式注入引用（system prompt）", test_stream_inject_quote),
        ("非流式注入引用", test_chat_inject_quote),
        ("无引用不注入（回归）", test_no_quote_no_inject),
        ("引用不进 history（原文保持）", test_quote_not_in_history),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            import traceback
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
