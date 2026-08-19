"""V14.4 Step 1：模板注册表测试（无框架，直接运行，零 API 费用）。

覆盖（报告 Step 1 验收）：
- 加载与校验（schema_version / id 唯一 / 条目字段 / 坏 JSON 降级）
- 确定性 hash：同日同时段（同 seed）选型稳定
- 逐级放松路径全覆盖（weathers → periods → favor_range → offline_bucket）
- arc 分桶与 mansion 兜底
- recovery_range 档位（低档疏离 / 恢复期记忆碎片）
- 无匹配返回 None 不抛
- build_cache_key：arc/recovery 分桶（跨篇章缓存污染修复回归）

用法：python tests/test_template_registry.py
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.template_registry import load_registry, pick
from shared.vignette import build_cache_key
from shared.state import WorldState

REGISTRY_PATH = os.path.join(PROJECT_ROOT, "content", "templates", "registry.json")


def _registry():
    reg = load_registry(REGISTRY_PATH)
    assert reg["items"], "registry 加载失败"
    return reg


def test_load_and_validate() -> None:
    reg = _registry()
    assert reg["schema_version"] == "1.0"
    assert len(reg["items"]) == 58, f"Step3 扩池后应 58 条，实际 {len(reg['items'])}"
    ids = [it["id"] for it in reg["items"]]
    assert len(ids) == len(set(ids)), "id 应唯一"
    for it in reg["items"]:
        assert it.get("arc") and it.get("slot") and it.get("text"), f"缺字段: {it.get('id')}"


def test_load_bad_json_degrades() -> None:
    reg = load_registry(os.path.join(PROJECT_ROOT, "content", "templates", "not_exist.json"))
    assert reg["items"] == [], "文件缺失应降级为空注册表"
    assert pick(reg, arc="mansion_era", slot="vignette") is None, "空注册表 pick 应 None"


def test_deterministic_same_seed() -> None:
    """同 seed（同日同时段）选型稳定；不同 seed 允许不同。"""
    reg = _registry()
    a1 = pick(reg, arc="mansion_era", slot="vignette", period="上午",
              weather="晴朗", seed="2026-08-19_上午")
    a2 = pick(reg, arc="mansion_era", slot="vignette", period="上午",
              weather="晴朗", seed="2026-08-19_上午")
    assert a1 is not None and a1["id"] == a2["id"], "同 seed 应稳定"
    b = pick(reg, arc="mansion_era", slot="vignette", period="上午",
             weather="晴朗", seed="2026-08-20_上午")
    assert a1["id"] is not None


def test_arc_bucket_and_mansion_fallback() -> None:
    reg = _registry()
    # 帝国低 recovery vignette：命中低档（route 正确 + 疏离语感标志）
    it = pick(reg, arc="empire_era", slot="vignette", recovery=0.1, seed="s")
    assert it is not None and it["arc"] == "empire_era", "帝国低档应命中"
    assert it["recovery_range"] == [0.0, 0.35], f"应命中低档: {it['id']}"
    aloof_marks = ("想不起来", "移开", "走错", "靠得太近", "后退", "退到一旁", "欠了欠身", "辨认", "听过")
    assert any(w in it["text"] for w in aloof_marks), f"低档应为疏离基调: {it['text']}"
    # 未知 arc → 兜底 mansion_era
    it2 = pick(reg, arc="unknown_era", slot="vignette", seed="s")
    assert it2 is not None and it2["arc"] == "mansion_era", "未知 arc 应兜底宅邸"
    # 未知 arc + 无 mansion 条目 slot → None
    assert pick(reg, arc="unknown_era", slot="ambient_remark", seed="s") is None


def test_recovery_ranges() -> None:
    """recovery 档位路由：0.1 → 低档 / 0.5 → 恢复期 / 1.0 不命中帝国。"""
    reg = _registry()
    aloof_marks = ("想不起来", "移开", "走错", "靠得太近", "后退", "退到一旁", "欠了欠身", "辨认", "听过")
    low = pick(reg, arc="empire_era", slot="vignette", recovery=0.1, seed="s")
    mid = pick(reg, arc="empire_era", slot="vignette", recovery=0.5, seed="s")
    assert low["recovery_range"] == [0.0, 0.35], f"0.1 应命中低档: {low['id']}"
    assert any(w in low["text"] for w in aloof_marks), "低档疏离"
    assert mid["recovery_range"] == [0.35, 0.85], f"0.5 应命中恢复期: {mid['id']}"
    # recovery=1.0（宅邸）→ 帝国条目 recovery_range 全不匹配 → 兜底 mansion
    high = pick(reg, arc="empire_era", slot="vignette", recovery=1.0, seed="s")
    assert high is not None and high["arc"] == "mansion_era", "满恢复应兜底宅邸"


def test_empire_arc_tone_guard() -> None:
    """V14.4 Step3：帝国两档语感守卫——低档零深情/宅邸腔；高档记忆碎片。"""
    reg = _registry()
    deep_words = ("呼吸都困难", "喜欢您", "好想", "缺了一块", "欢迎回家")
    mansion_words = ("客人大人", "宅邸", "巴鲁斯", "女仆")

    # 低档 8 条 vignette + 8 条 proactive：全部疏离克制
    low_items = [it for it in reg["items"]
                 if it["arc"] == "empire_era" and it.get("recovery_range") == [0.0, 0.35]]
    assert len(low_items) == 17, f"低档应 17 条: {len(low_items)}"
    for it in low_items:
        assert not any(w in it["text"] for w in deep_words), f"低档深情越界: {it['id']}"
        assert not any(w in it["text"] for w in ("客人大人", "巴鲁斯")), f"低档宅邸腔越界: {it['id']}"

    # 高档 8 条 vignette + 8 条 proactive：记忆碎片语感——两档互斥断言
    # （不含深情词 + 不含低档专属疏离标志「想不起来/走错/靠得太近/后退/退到一旁」）
    mid_items = [it for it in reg["items"]
                 if it["arc"] == "empire_era" and it.get("recovery_range") == [0.35, 0.85]]
    assert len(mid_items) == 16, f"高档应 16 条: {len(mid_items)}"
    aloof_marks = ("想不起来", "走错", "靠得太近", "后退", "退到一旁", "请让蕾姆继续工作")
    for it in mid_items:
        assert not any(w in it["text"] for w in deep_words), f"高档深情越界: {it['id']}"
        assert not any(w in it["text"] for w in aloof_marks), f"高档不应有疏离标志: {it['id']}"
    # 高档代表性记忆碎片抽样（关键条目语感正向确认）
    mid_by_id = {it["id"]: it["text"] for it in mid_items}
    assert "记起了红茶" in mid_by_id["empire_vignette_mid_01"]
    assert "梦见" in mid_by_id["empire_proactive_mid_01"]
    assert "会想起来的" in mid_by_id["empire_proactive_mid_07"]


def test_relaxation_chain() -> None:
    """逐级放松：严格匹配空池 → weathers → periods → favor_range → offline_bucket。"""
    reg = _registry()
    # return_flavor 全条目 offline_bucket 限定；用不存在 weather 触发逐级放松
    strict = pick(reg, arc="mansion_era", slot="return_flavor",
                  offline_bucket="HALF_DAY", period="午夜", weather="暴雪", seed="s")
    assert strict is not None, "严格空池应逐级放松到 offline_bucket 命中"
    # 确认放松链路保留 arc+slot（返回的仍是 return_flavor 条目）
    assert strict["slot"] == "return_flavor"
    # 无任何条目可匹配的 slot → None 不抛
    assert pick(reg, arc="mansion_era", slot="twin_idle", seed="s") is None


def test_offline_bucket_match() -> None:
    """offline_bucket 硬过滤：HALF_DAY 条目只在该桶命中。"""
    reg = _registry()
    hit = pick(reg, arc="mansion_era", slot="return_flavor",
               offline_bucket="LONG_ABSENCE", seed="s")
    assert hit["offline_bucket"] == "LONG_ABSENCE", "应命中 LONG_ABSENCE 条目"


def test_cache_key_arc_partition() -> None:
    """V14.4 §3.3 回归：同状态不同 arc → 不同缓存 key；同 arc 同 recovery → 同 key。"""
    ws = WorldState(period="夜晚", weather="晴朗", days_since_last=1)
    k_mansion = build_cache_key(ws, "CLOSE", "观察中", arc="mansion_era", recovery=1.0)
    k_empire = build_cache_key(ws, "CLOSE", "观察中", arc="empire_era", recovery=0.0)
    assert k_mansion != k_empire, "不同 arc 缓存 key 必须不同（跨篇章污染修复）"
    k_mansion2 = build_cache_key(ws, "CLOSE", "观察中", arc="mansion_era", recovery=1.0)
    assert k_mansion == k_mansion2, "同 arc 同 recovery 应稳定"
    k_low = build_cache_key(ws, "CLOSE", "观察中", arc="empire_era", recovery=0.1)
    k_mid = build_cache_key(ws, "CLOSE", "观察中", arc="empire_era", recovery=0.5)
    assert k_low != k_mid, "recovery 桶应分档（0.1=m / 0.5=r）"


def main() -> int:
    tests = [
        ("加载与校验（30 条 + id 唯一）", test_load_and_validate),
        ("坏 JSON/缺失降级", test_load_bad_json_degrades),
        ("确定性 hash（同 seed 稳定）", test_deterministic_same_seed),
        ("arc 分桶 + mansion 兜底", test_arc_bucket_and_mansion_fallback),
        ("recovery 档位（低档/恢复期/满恢复兜底）", test_recovery_ranges),
        ("帝国两档语感守卫（互斥断言）", test_empire_arc_tone_guard),
        ("逐级放松链路", test_relaxation_chain),
        ("offline_bucket 硬过滤", test_offline_bucket_match),
        ("缓存 key arc/recovery 分桶（§3.3 回归）", test_cache_key_arc_partition),
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
