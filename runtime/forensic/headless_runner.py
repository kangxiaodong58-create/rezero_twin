"""Headless 复现通道（Forensic Kernel M3）。

能力（对应 forensic_subsystem_design.md M3 验收）：
- run_campaign(n_cases, seed, ...) → CampaignResult：崩溃率 + 事件序列 + INC 案件
- Mock LLM：不依赖网络；可注入 api_error_rate / timeout_rate（时序扰动实验）
- 固定随机种子：同一 seed 结果可重复
- 会话切换（session_every）：模拟长会话 + 新会话；stale_every：流式中途重置会话
  → 触发 STALE_CALLBACK_OBSERVED（generation 级 stale 观测）
- 每轮在独立线程运行（模拟 GUI QThread worker）：线程异常 → threading.excepthook
  → INC dump 自动落盘 → 崩溃率统计

约束：纯 Python，禁止 import PySide6。mock 回复模板必须通过 ResponseValidator
（含【蕾姆】/【拉姆】标签、无 OOC 词、无第一人称）。
"""

from __future__ import annotations

import os
import random
import tempfile
import threading
import time
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

# 每轮随机采样输入（词表组合，确定性由 seed 控制）
_USER_WORDS = [
    "今天", "蕾姆", "拉姆", "宅邸", "天气", "花园", "休息",
    "故事", "心情", "晚饭", "院子", "书库", "走廊", "早安",
]

# 校验器安全的回复模板（含角色标签、无 OOC 词、蕾姆行无第一人称）
_REPLY_POOL = [
    '【蕾姆】: "……明白了。"\n【拉姆】: "哼，随您吧。"',
    '【蕾姆】: "蕾姆会记住的。"\n【拉姆】: "姐姐也记下了。"',
    '【蕾姆】: "……蕾姆觉得您说得对。"\n【拉姆】: "偶尔也算说对了一次。"',
    '【蕾姆】: "是，蕾姆这就去准备。"\n【拉姆】: "动作快些。"',
    '【蕾姆】: "……很高兴听到您这么说。"\n【拉姆】: "看来心情不错呢。"',
]

_INPUT_WORD_COUNT = 3


@dataclass
class DelayProfile:
    """时序扰动配置（一次实验的一个变量维度）。"""

    api_error_rate: float = 0.0   # create() 直接抛错概率（非流式/流式通用）
    timeout_rate: float = 0.0     # 流式中途抛超时概率（消费生成器时崩溃）
    stream_delay: float = 0.0     # 每个 chunk 之间的延迟（秒）
    chunk_count: int = 3          # 每个流式回复的 chunk 数


@dataclass
class CampaignResult:
    n_cases: int
    crashes: int
    crash_rate: float
    events: List[Dict[str, Any]] = field(default_factory=list)
    event_histogram: Dict[str, int] = field(default_factory=dict)
    incidents: List[str] = field(default_factory=list)
    generations: List[int] = field(default_factory=list)


# ── Mock LLM（模拟 openai client 协议）────────────────────────────

class _MockStream:
    """流式响应：可注入中途超时（TimeoutError 在 __next__ 抛出）。

    bridge 生成器会捕获并 re-raise（非取消场景）→ 消费端崩溃 → 取证。
    """

    def __init__(self, chunks: List[Any], rng: random.Random, profile: DelayProfile) -> None:
        self._chunks = chunks
        self._rng = rng
        self._profile = profile
        self._consumed = 0

    def __iter__(self):
        return self

    def __next__(self) -> Any:
        if self._consumed >= len(self._chunks):
            raise StopIteration
        if self._profile.timeout_rate > 0 and self._rng.random() < self._profile.timeout_rate:
            raise TimeoutError("mock stream timeout injected")
        if self._profile.stream_delay > 0:
            time.sleep(self._profile.stream_delay)
        chunk = self._chunks[self._consumed]
        self._consumed += 1
        return chunk

    def close(self) -> None:  # bridge finally 调用
        pass


class _MockCompletions:
    def __init__(self, rng: random.Random, profile: DelayProfile) -> None:
        self._rng = rng
        self._profile = profile

    def create(self, model: str, messages: List[Dict], temperature: float,
               max_tokens: int, stream: bool = False) -> Any:
        if self._profile.api_error_rate > 0 and self._rng.random() < self._profile.api_error_rate:
            raise TimeoutError("mock api error injected")
        if stream:
            reply = self._rng.choice(_REPLY_POOL)
            chars = list(reply)
            size = max(1, len(chars) // self._profile.chunk_count)
            chunks = [
                SimpleNamespace(choices=[
                    SimpleNamespace(delta=SimpleNamespace(
                        content="".join(chars[i * size:(i + 1) * size])))
                ])
                for i in range(self._profile.chunk_count)
            ]
            return _MockStream(chunks, self._rng, self._profile)
        reply = self._rng.choice(_REPLY_POOL)
        return SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(content=reply))
        ])


class MockClient:
    """替换 bridge.client 的 mock：不依赖网络，行为由 DelayProfile 控制。

    模拟 openai 结构：client.chat.completions.create(...)
    """

    def __init__(self, profile: DelayProfile, seed: int) -> None:
        self.chat = SimpleNamespace(
            completions=_MockCompletions(random.Random(seed), profile)
        )


# ── 核心：轮次驱动 ────────────────────────────────────────────────

def _random_input(rng: random.Random) -> str:
    return " ".join(rng.sample(_USER_WORDS, _INPUT_WORD_COUNT))


def make_bot(profile: DelayProfile, seed: int) -> Any:
    """构造一个接入 mock LLM 的 ReZeroLLMBridge（无真实网络/存储）。"""
    from llm import ReZeroLLMBridge
    from shared.state import WorldState

    bot = ReZeroLLMBridge(api_key="mock-key", conversation_store=None)
    bot.client = MockClient(profile, seed)
    bot.world = WorldState()  # 类属性默认值，不触碰持久化存档
    return bot


def _run_one_turn(bot: Any, rng: random.Random, profile: DelayProfile,
                  stale_mid_stream: bool) -> None:
    """跑一轮流式对话并完整消费生成器。

    stale_mid_stream=True：消费到第 2 个 chunk 时重置会话（generation++），
    旧流继续产出 → chunk 检查点记录 STALE_CALLBACK_OBSERVED。
    """
    user_input = _random_input(rng)
    gen, _state = bot.chat_stream(user_input)
    for i, _chunk in enumerate(gen):
        if stale_mid_stream and i == 1:
            bot.reset_session()


def run_campaign(
    n_cases: int = 100,
    seed: int = 42,
    *,
    profile: Optional[DelayProfile] = None,
    session_every: int = 8,
    stale_every: int = 0,
    incidents_dir: Optional[str] = None,
) -> CampaignResult:
    """跑一轮实验战役，返回崩溃率与事件统计。

    - 每轮在独立线程运行（模拟 GUI QThread worker）：线程异常经
      threading.excepthook 自动取证（INC dump），不中断战役
    - incidents_dir=None → 临时目录（不污染项目）；传入项目 incidents/
      则案件落盘到真实取证目录
    """
    from runtime.forensic import init_forensic, record, shutdown_forensic
    from runtime.forensic.manifest import list_incidents

    profile = profile or DelayProfile()
    rng = random.Random(seed)
    if incidents_dir is None:
        incidents_dir = tempfile.mkdtemp(prefix="forensic-campaign-")
    init_forensic(incidents_dir)

    crashes = 0
    generations: List[int] = []
    bot = None

    # 计数 hook 链在 excepthook 上：worker 异常逃逸线程顶层 →
    # threading.excepthook（本 hook 计数 → init 的 hook 落 INC dump）。
    # worker 内绝不捕获：捕获 = 线程"没死" = 取证不触发。
    _orig_th_hook = threading.excepthook
    counter = {"crashes": 0}

    def _counting_hook(args: Any) -> None:
        counter["crashes"] += 1
        _orig_th_hook(args)

    threading.excepthook = _counting_hook
    try:
        for i in range(n_cases):
            if i % session_every == 0:
                if bot is None:
                    bot = make_bot(profile, seed + i)
                else:
                    bot.reset_session()  # 会话切换：generation 递增（stale 锚点）
            generations.append(bot._generation)
            stale = stale_every > 0 and (i % stale_every == 0)

            def _worker() -> None:
                _run_one_turn(bot, rng, profile, stale)  # 异常逃逸 → excepthook

            t = threading.Thread(target=_worker, name=f"llm-worker-{i}")
            t.start()
            t.join()
            crashes = counter["crashes"]
    finally:
        threading.excepthook = _orig_th_hook
        record("CAMPAIGN_END", component="headless",
               payload_summary=f"crashes={crashes}/{n_cases}")
        from runtime.forensic import get_buffer
        events = list(get_buffer().snapshot()) if get_buffer() else []
        shutdown_forensic()

    histogram: Dict[str, int] = {}
    for e in events:
        histogram[e["event"]] = histogram.get(e["event"], 0) + 1
    incidents = [d["incident_id"] for d in list_incidents(incidents_dir)]

    return CampaignResult(
        n_cases=n_cases,
        crashes=crashes,
        crash_rate=crashes / n_cases if n_cases else 0.0,
        events=events,
        event_histogram=histogram,
        incidents=incidents,
        generations=generations,
    )
