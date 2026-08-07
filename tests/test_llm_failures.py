"""V13.0：LLM 失败路径测试（零 API 费用，全部 mock）。

覆盖（验收用例 3）：
- 4 类异常形态（断网/空响应/None 内容/OOC）→ 角色格式兜底，不崩溃
- 兜底不污染 history（chat 校验失败 / API 异常 / stream 校验失败 / stream 异常）
- 流式校验结果回传（_last_stream_ok / _stream_fallback_text）
- cancel_stream() 中途取消 → 生成器提前结束、history 干净
- 回避文案防回归（不含「不太确定」失忆句）

用法：python tests/test_llm_failures.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from llm.bridge import ReZeroLLMBridge


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Delta:
    def __init__(self, content):
        self.content = content


class _StreamChoice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _StreamChunk:
    def __init__(self, content):
        self.choices = [_StreamChoice(content)]


class FakeChat:
    """模拟 openai client.chat.completions.create 的失败/成功形态。

    stream=True 时返回生成器（自带 close()，与 openai Stream 接口对齐）。
    """

    def __init__(self, mode: str):
        self.mode = mode

    def create(self, **kw):
        if kw.get("stream"):
            return self._stream()
        if self.mode == "boom":
            raise RuntimeError("模拟网络断开")
        if self.mode == "empty":
            class R:
                choices = []
            return R()
        if self.mode == "nullcontent":
            return _Resp(None)
        if self.mode == "ooc":
            return _Resp('【蕾姆】: "我是AI助手，用户您好"')
        if self.mode == "ok":
            return _Resp('【蕾姆】: "您好，小东大人。"')
        raise AssertionError(f"unknown mode: {self.mode}")

    def _stream(self):
        if self.mode == "boom":
            raise RuntimeError("模拟网络断开")
        if self.mode == "ooc":
            def g():
                yield _StreamChunk('【蕾姆】: "我是AI助手，用户您好"')
            return g()
        if self.mode == "ok":
            def g():
                yield _StreamChunk('【蕾姆】: "您好')
                yield _StreamChunk('，小东大人。"')
            return g()
        raise AssertionError(f"unknown stream mode: {self.mode}")


def _fake_client(mode):
    return type("FakeClient", (), {"chat": type("Chat", (), {"completions": FakeChat(mode)})()})()


def _new_bot():
    return ReZeroLLMBridge(api_key="sk-test-not-used", conversation_store=None)


def test_chat_boom_no_history() -> None:
    bot = _new_bot()
    bot.client = _fake_client("boom")
    reply = bot.chat("你好")
    assert "蕾姆" in reply and "系统" not in reply, f"异常回复非角色格式: {reply}"
    assert len(bot.history) == 0, f"API 异常不应写 history: {len(bot.history)}"
    assert bot._last_chat_fallback is True


def test_chat_empty_no_history() -> None:
    bot = _new_bot()
    bot.client = _fake_client("empty")
    reply = bot.chat("你好")
    assert "蕾姆" in reply
    assert len(bot.history) == 0


def test_chat_nullcontent_no_history() -> None:
    bot = _new_bot()
    bot.client = _fake_client("nullcontent")
    reply = bot.chat("你好")
    assert "蕾姆" in reply
    assert len(bot.history) == 0


def test_chat_validation_fallback_no_history() -> None:
    """T1-05 缺陷回归：校验失败兜底不得写入 history。"""
    bot = _new_bot()
    bot.client = _fake_client("ooc")
    reply = bot.chat("你好")
    assert "蕾姆" in reply and "拉姆" in reply
    assert len(bot.history) == 0, f"兜底不应写 history: {len(bot.history)}"
    assert bot._last_chat_fallback is True


def test_chat_ok_writes_history() -> None:
    """成功路径回归：正常写入 history。"""
    bot = _new_bot()
    bot.client = _fake_client("ok")
    reply = bot.chat("你好")
    assert "小东大人" in reply or "蕾姆" in reply
    assert len(bot.history) == 2, f"成功应写 2 条 history: {len(bot.history)}"
    assert bot._last_chat_fallback is False


def test_stream_boom_safe_and_clean() -> None:
    bot = _new_bot()
    bot.client = _fake_client("boom")
    gen, _state = bot.chat_stream("你好")
    tokens = list(gen)
    assert len(tokens) == 1, f"流式异常应产出 1 段错误文案: {len(tokens)}"
    assert "蕾姆" in tokens[0]
    assert len(bot.history) == 0


def test_stream_validation_fallback_reports_status() -> None:
    """流式校验失败：_last_stream_ok=False + 回避文案 + history 干净。"""
    bot = _new_bot()
    bot.client = _fake_client("ooc")
    gen, _state = bot.chat_stream("你好")
    list(gen)  # 消费完
    assert bot._last_stream_ok is False
    assert "放一放" in bot._stream_fallback_text, f"回避文案缺失: {bot._stream_fallback_text}"
    assert len(bot.history) == 0


def test_stream_ok_reports_status() -> None:
    bot = _new_bot()
    bot.client = _fake_client("ok")
    gen, _state = bot.chat_stream("你好")
    list(gen)
    assert bot._last_stream_ok is True
    assert len(bot.history) == 2


def test_cancel_stream_stops_generator() -> None:
    """取消：生成器提前结束且不写 history。"""
    bot = _new_bot()
    bot.client = _fake_client("ok")
    gen, _state = bot.chat_stream("你好")
    first = next(gen)  # 消费第一个 token
    assert first
    bot.cancel_stream()  # 模拟用户取消
    rest = list(gen)
    assert len(bot.history) == 0, f"取消后不应写 history: {len(bot.history)}"
    assert bot._stream_cancelled is True


def test_fallback_wording_no_amnesia() -> None:
    """V13.0：兜底文案去失忆感（T1-05）。"""
    bot = _new_bot()
    text = bot._fallback_reply()
    assert "放一放" in text, f"兜底应含回避语义: {text}"
    assert "不太确定" not in text and "没听清" not in text, f"兜底不得有失忆感: {text}"


def main() -> int:
    tests = [
        ("chat 断网异常 → 不写 history", test_chat_boom_no_history),
        ("chat 空响应 → 不写 history", test_chat_empty_no_history),
        ("chat None 内容 → 不写 history", test_chat_nullcontent_no_history),
        ("chat 校验失败兜底 → 不写 history（T1-05 回归）", test_chat_validation_fallback_no_history),
        ("chat 成功 → 写 history（正常路径回归）", test_chat_ok_writes_history),
        ("stream 断网 → 安全生成器 + history 干净", test_stream_boom_safe_and_clean),
        ("stream 校验失败 → 状态回传 + 回避文案", test_stream_validation_fallback_reports_status),
        ("stream 成功 → _last_stream_ok=True", test_stream_ok_reports_status),
        ("cancel_stream → 生成器提前结束 + 不写 history", test_cancel_stream_stops_generator),
        ("兜底文案去失忆感", test_fallback_wording_no_amnesia),
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
