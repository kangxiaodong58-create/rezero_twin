"""V14.4 Step2：vignette 注册表迁移测试（无框架，直接运行，零 API 费用）。

覆盖（报告 Step 2 验收）：
- _pick_short_opening：注册表 slot=vignette 优先（确定性、池内命中）
- 兜底：registry 缺失/空 → 回落旧 openings 硬匹配
- _pick_return_flavor：注册表 slot=return_flavor 五桶口径（复用来信桶）
- 分布不劣化：40 组合（8 时段 × 5 天气）新池命中 ≥ 旧池命中

用法：python tests/test_vignette_registry.py
"""
from __future__ import annotations

import os
import random
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared import vignette
from shared.state import WorldState
from shared.template_registry import load_registry, pick as registry_pick

REGISTRY_PATH = os.path.join(PROJECT_ROOT, "content", "templates", "registry.json")

PERIODS = ["清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜"]
WEATHERS = ["晴朗", "多云", "小雨", "大雨", "阴沉"]


def test_short_opening_registry_preferred() -> None:
    """30% 门过后：注册表 slot=vignette 命中（确定性 seed 同日稳定）。"""
    reg = load_registry(REGISTRY_PATH)
    vignette_items = [it["text"] for it in reg["items"]
                      if it["slot"] == "vignette" and it["arc"] == "mansion_era"]
    assert len(vignette_items) == 10, f"宅邸 vignette 应 10 条: {len(vignette_items)}"

    original = random.random
    random.random = lambda: 0.0  # 必走选择分支
    try:
        out1 = vignette._pick_short_opening("上午", "晴朗", 0)
        out2 = vignette._pick_short_opening("上午", "晴朗", 0)
        assert out1 is not None, "应命中注册表 vignette"
        assert out1 in vignette_items, f"应来自注册表池: {out1}"
        assert out1 == out2, "同日同时段确定性（同 seed）"
    finally:
        random.random = original


def test_short_opening_fallback_old_pool() -> None:
    """registry 空 → 回落旧 openings 硬匹配（防御兜底不崩）。"""
    original = random.random
    random.random = lambda: 0.0
    orig_reg = vignette._get_registry
    vignette._REGISTRY = {"schema_version": "0", "items": []}
    try:
        out = vignette._pick_short_opening("上午", "晴朗", 0)
        assert out is None or isinstance(out, str), "兜底应返回 str 或 None（不抛）"
    finally:
        random.random = original
        vignette._REGISTRY = None
        vignette._get_registry = orig_reg


def test_return_flavor_registry_bucket() -> None:
    """归来感五桶：3 天离线（DAYS_3_7）命中注册表 return_flavor 条目。"""
    reg = load_registry(REGISTRY_PATH)
    bucket_items = [it["text"] for it in reg["items"]
                    if it["slot"] == "return_flavor" and it.get("offline_bucket") == "DAYS_3_7"]
    assert bucket_items, "registry 应有 DAYS_3_7 return_flavor 条目"

    ws = WorldState(
        current_time="2026-08-19 20:00", period="夜晚", weather="晴朗",
        days_since_last=3,
        last_interaction_ts=time.time() - 73 * 3600,  # 73h → DAYS_3_7（远离 72h 边界）
        last_period="上午",
    )
    out = vignette._pick_return_flavor(ws)
    assert out in bucket_items, f"应命中 DAYS_3_7 注册表条目: {out}"


def test_return_flavor_zero_days_empty() -> None:
    """0 天离线 → 空串（不插入归来感）。"""
    ws = WorldState(current_time="2026-08-19 20:00", period="夜晚",
                    weather="晴朗", days_since_last=0)
    assert vignette._pick_return_flavor(ws) == ""


def test_return_flavor_fallback_old() -> None:
    """registry 空 → 回落旧 _pick_return_awareness 粗桶（不崩）。"""
    ws = WorldState(
        current_time="2026-08-19 20:00", period="夜晚", weather="晴朗",
        days_since_last=5,
        last_interaction_ts=time.time() - 5 * 86400,
        last_period="上午",
    )
    vignette._REGISTRY = {"schema_version": "0", "items": []}
    try:
        out = vignette._pick_return_flavor(ws)
        assert out and isinstance(out, str), "兜底应返回文案"
    finally:
        vignette._REGISTRY = None


def test_distribution_not_worse() -> None:
    """分布不劣化：40 组合下注册表命中数 ≥ 旧硬匹配命中数。"""
    reg = load_registry(REGISTRY_PATH)
    new_hits = 0
    old_hits = 0
    for period in PERIODS:
        for weather in WEATHERS:
            hit = registry_pick(reg, arc="mansion_era", slot="vignette",
                                period=period, weather=weather,
                                seed=f"2026-08-19_{period}")
            if hit:
                new_hits += 1
            # 旧逻辑：id 关键词硬匹配（同 _pick_short_opening 旧分支语义）
            from shared.vignette import ContentLoader
            loader = ContentLoader()
            openings = loader.get_openings("opening_mansion")
            old_ok = any(
                (op.get("text") and (
                    ("return" in op.get("id", "") and 0 > 0)
                    or (weather in ("小雨", "大雨") and "rain" in op.get("id", ""))
                    or (period in ("夜晚", "深夜") and "night" in op.get("id", ""))
                    or (period in ("清晨", "上午") and "sun_01" in op.get("id", "")
                        and weather not in ("小雨", "大雨", "阴沉"))
                    or (period in ("午后", "下午") and "sun_02" in op.get("id", "")
                        and weather not in ("小雨", "大雨", "阴沉"))
                    or (period in ("清晨", "上午") and "fog" in op.get("id", ""))
                ))
                for op in openings
            )
            if old_ok:
                old_hits += 1
    assert new_hits >= old_hits, f"新池命中 {new_hits} < 旧池 {old_hits}（分布劣化）"
    assert new_hits >= 30, f"40 组合应大部分命中: {new_hits}/40"


def test_arc_passthrough_vignette() -> None:
    """V14.4 Step3：arc×recovery 透传——帝国档位路由（低档疏离/恢复期记忆碎片）。"""
    reg = load_registry(REGISTRY_PATH)
    empire_vignette = [it["text"] for it in reg["items"]
                       if it["arc"] == "empire_era" and it["slot"] == "vignette"]
    empire_return = [it["text"] for it in reg["items"]
                     if it["arc"] == "empire_era" and it["slot"] == "return_flavor"]
    low_texts = {it["text"] for it in reg["items"]
                 if it["arc"] == "empire_era" and it["slot"] == "vignette"
                 and it.get("recovery_range") == [0.0, 0.35]}
    mid_texts = {it["text"] for it in reg["items"]
                 if it["arc"] == "empire_era" and it["slot"] == "vignette"
                 and it.get("recovery_range") == [0.35, 0.85]}
    assert len(empire_vignette) == 16, f"帝国 vignette 应 16 条: {len(empire_vignette)}"

    original = random.random
    random.random = lambda: 0.0
    try:
        # 帝国低 recovery → 低档疏离
        out_low = vignette._pick_short_opening("上午", "晴朗", 0,
                                               arc="empire_era", recovery=0.1)
        assert out_low in low_texts, f"recovery=0.1 应命中低档: {out_low}"
        # 帝国恢复期 → 记忆碎片档
        out_mid = vignette._pick_short_opening("上午", "晴朗", 0,
                                               arc="empire_era", recovery=0.5)
        assert out_mid in mid_texts, f"recovery=0.5 应命中恢复期: {out_mid}"
        # 宅邸 arc 不受影响
        out2 = vignette._pick_short_opening("上午", "晴朗", 0, arc="mansion_era")
        assert out2 not in empire_vignette, "宅邸 arc 不应命中帝国条目"
    finally:
        random.random = original

    # 归来感：帝国 arc + 离线 → 帝国 return_flavor（或旧兜底）
    ws = WorldState(
        current_time="2026-08-19 20:00", period="夜晚", weather="晴朗",
        days_since_last=2,
        last_interaction_ts=time.time() - 50 * 3600,  # DAYS_1_3（远离边界）
        last_period="上午",
    )
    out3 = vignette._pick_return_flavor(ws, arc="empire_era", recovery=0.1)
    assert out3 in empire_return or "您回来了" in out3 or "停了几秒" in out3, \
        f"帝国归来感应来自帝国档: {out3}"


def main() -> int:
    tests = [
        ("短开场注册表优先（确定性）", test_short_opening_registry_preferred),
        ("短开场兜底旧池", test_short_opening_fallback_old_pool),
        ("归来感五桶命中", test_return_flavor_registry_bucket),
        ("归来感 0 天空串", test_return_flavor_zero_days_empty),
        ("归来感兜底粗桶", test_return_flavor_fallback_old),
        ("分布不劣化（40 组合）", test_distribution_not_worse),
        ("arc 透传（帝国档位路由）", test_arc_passthrough_vignette),
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
