"""Forensic Kernel M3 测试：Headless 复现通道。

验证点（forensic_subsystem_design.md M3 验收）：
- mock 回复模板通过 ResponseValidator（否则实验全在测校验失败）
- 基线战役（正常 profile）零崩溃，事件流完整
- 固定 seed 可重复（同一 seed 两次结果一致）
- 注入 timeout → 崩溃率可测量、INC 案件落盘（取证闭环）
- stale_every 触发 STALE_CALLBACK_OBSERVED（generation 级观测）
- 会话切换 generation 递增可见
"""

from __future__ import annotations

import os

import pytest

from runtime.forensic.headless_runner import (
    DelayProfile,
    _REPLY_POOL,
    make_bot,
    run_campaign,
)
from shared.validators import ResponseValidator

_N = 40  # 战役规模（保持测试快速）


def test_reply_pool_passes_validation():
    """mock 模板必须过校验器，否则实验体系失效。"""
    v = ResponseValidator()
    for tpl in _REPLY_POOL:
        r = v.validate(tpl)
        assert r.ok, f"模板未过校验: {tpl!r} → {r.reason}"


def test_baseline_campaign_no_crash():
    result = run_campaign(n_cases=_N, seed=7)
    assert result.crashes == 0
    assert result.crash_rate == 0.0
    # 事件流完整：每轮都有 MESSAGE_RECEIVED → STREAM_START → STREAM_END
    h = result.event_histogram
    assert h.get("MESSAGE_RECEIVED", 0) == _N
    assert h.get("STREAM_START", 0) == _N
    assert h.get("STREAM_END", 0) == _N
    assert h.get("API_REQUEST", 0) == _N
    # seq 严格递增（时间线排序依据）
    seqs = [e["seq"] for e in result.events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_seed_reproducible():
    r1 = run_campaign(n_cases=_N, seed=99)
    r2 = run_campaign(n_cases=_N, seed=99)
    assert r1.crashes == r2.crashes
    assert len(r1.events) == len(r2.events)
    # 同 seed：事件序列内容一致（事件名+generation 序列）
    sig1 = [(e["event"], e["generation"]) for e in r1.events]
    sig2 = [(e["event"], e["generation"]) for e in r2.events]
    assert sig1 == sig2


def test_timeout_injection_measurable_crash_rate(tmp_path):
    """注入流式中途超时 → 崩溃率 > 0 且 INC 案件落盘（取证闭环）。"""
    incidents = tmp_path / "incidents"
    profile = DelayProfile(timeout_rate=0.4)
    result = run_campaign(n_cases=_N, seed=3, profile=profile,
                          incidents_dir=str(incidents))
    assert result.crashes > 0
    assert 0 < result.crash_rate <= 1
    # 事件流里能看到超时与错误
    h = result.event_histogram
    assert h.get("STREAM_ERROR", 0) == result.crashes
    # 线程异常 → excepthook → INC 落盘
    incs = [d for d in os.listdir(incidents) if d.startswith("INC-")]
    assert len(incs) == result.crashes
    assert len(result.incidents) == result.crashes


def test_api_error_rate_counts_events_not_crashes():
    """create() 直接抛错被 bridge 捕获（_err 路径），不崩溃但事件可查。"""
    profile = DelayProfile(api_error_rate=0.5)
    result = run_campaign(n_cases=_N, seed=5, profile=profile)
    assert result.crashes == 0
    assert result.event_histogram.get("API_ERROR", 0) > 0


def test_stale_generation_observed():
    """流式中途重置会话 → 旧流继续产出 → STALE_CALLBACK_OBSERVED。"""
    result = run_campaign(n_cases=16, seed=11, stale_every=4, session_every=4)
    observed = [e for e in result.events if e["event"] == "STALE_CALLBACK_OBSERVED"]
    assert len(observed) >= 1
    ev = observed[0]
    # 捕获的旧 generation 与当前 generation 不同（stale 本质）
    assert "current_gen=" in (ev["payload_summary"] or "")
    assert ev["generation"] is not None


def test_session_switch_generation_increments():
    result = run_campaign(n_cases=16, seed=13, session_every=4)
    gens = result.generations
    assert gens == [1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4]
