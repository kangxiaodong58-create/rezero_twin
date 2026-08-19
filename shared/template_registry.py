"""V14.4 Step 1：篇章模板注册表选择器（纯逻辑零依赖，可单测——与 letter_manager 同风格）。

registry.json 条目 schema：
{
  "id": "唯一 id",
  "arc": "mansion_era | empire_era | late_arc（与 StoryArc.value 一致）",
  "slot": "vignette | proactive | return_flavor | status_flavor | twin_idle | ambient_remark",
  "text": "文案（含 {占位符} 由调用方插值）",
  "offline_bucket": 可选 "CROSS_PERIOD|HALF_DAY|DAYS_1_3|DAYS_3_7|LONG_ABSENCE",
  "recovery_range": 可选 [lo, hi]（帝国失忆恢复度档位，篇章语义不可放松）,
  "periods": 可选 ["all"] 或 ["清晨", ...],
  "weathers": 可选 ["all"] 或 ["晴朗", ...],
  "favor_range": 可选 [lo, hi]
}

选择器优先级（报告 §4.3）：arc（必须，缺则兜底 mansion_era）→ slot →
offline_bucket/recovery_range → period → weather（加味）→ 确定性 hash（同日同时段稳定）。
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List, Optional, Tuple


def load_registry(path: str) -> Dict[str, Any]:
    """加载 registry.json 并校验；失败降级为空注册表（调用方拿到 None 不崩）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or "items" not in data:
            return {"schema_version": "0", "items": [], "skipped": len(data) if isinstance(data, list) else 1}
        items = []
        skipped = 0
        for it in data["items"]:
            if isinstance(it, dict) and it.get("id") and it.get("arc") and it.get("slot"):
                items.append(it)
            else:
                skipped += 1
        return {
            "schema_version": data.get("schema_version", ""),
            "items": items,
            "skipped": skipped,
        }
    except Exception:
        return {"schema_version": "0", "items": [], "skipped": 0}


def _match(item: Dict[str, Any], *, offline_bucket=None, recovery=None,
           period=None, weather=None, favor=None, drop: Optional[str] = None) -> bool:
    """硬条件匹配；drop=要放松的键（逐级放松用，保留其余条件）。"""
    checks = []
    if offline_bucket and item.get("offline_bucket") and drop != "offline_bucket":
        checks.append(item["offline_bucket"] == offline_bucket)
    if recovery is not None and item.get("recovery_range") and drop != "recovery_range":
        lo, hi = item["recovery_range"]
        checks.append(lo <= recovery <= hi)
    if period and item.get("periods") and "all" not in item["periods"] and drop != "periods":
        checks.append(period in item["periods"])
    if weather and item.get("weathers") and "all" not in item["weathers"] and drop != "weathers":
        checks.append(weather in item["weathers"])
    if favor is not None and item.get("favor_range") and drop != "favor_range":
        lo, hi = item["favor_range"]
        checks.append(lo <= favor <= hi)
    return all(checks)


def pick(registry: Dict[str, Any], *, arc: str, slot: str,
         offline_bucket: Optional[str] = None, recovery: Optional[float] = None,
         period: Optional[str] = None, weather: Optional[str] = None,
         favor: Optional[float] = None, seed: str = "", rng=None) -> Optional[Dict[str, Any]]:
    """同一把钥匙（arc, slot, bucket, period, weather, favor）在同一天内选型稳定。

    - arc 分桶（必须）：arc 无条目 → 兜底 mansion_era → 再无 → None
    - 硬条件交集 → 空池则逐级放松（weathers → periods → favor_range →
      offline_bucket；recovery_range 是篇章语义，不放松）
    - 条件全过滤仍空且 arc != mansion_era → **arc 级回落 mansion_era**
      （帝国满恢复 = 宅邸人格；保证启动永远有引言）
    - seed 非空 → 确定性 hash（md5(f"{seed}|{id}") 排序取首）；否则 rng/random.choice
    - 无匹配返回 None（不抛）
    """
    result = _pick_arc(registry, arc=arc, slot=slot, offline_bucket=offline_bucket,
                       recovery=recovery, period=period, weather=weather,
                       favor=favor, seed=seed, rng=rng)
    if result is None and arc != "mansion_era":
        result = _pick_arc(registry, arc="mansion_era", slot=slot,
                           offline_bucket=offline_bucket, recovery=recovery,
                           period=period, weather=weather, favor=favor,
                           seed=seed, rng=rng)
    return result


def _pick_arc(registry: Dict[str, Any], *, arc: str, slot: str,
              offline_bucket=None, recovery=None, period=None, weather=None,
              favor=None, seed: str = "", rng=None) -> Optional[Dict[str, Any]]:
    items = registry.get("items", [])
    bucket_items = [it for it in items if it.get("arc") == arc and it.get("slot") == slot]
    if not bucket_items:
        return None

    pool = [it for it in bucket_items
            if _match(it, offline_bucket=offline_bucket, recovery=recovery,
                      period=period, weather=weather, favor=favor)]
    if not pool:
        # 逐级放松（保留 arc+slot；recovery_range 不放松）
        for key in ("weathers", "periods", "favor_range", "offline_bucket"):
            pool = [it for it in bucket_items
                    if _match(it, offline_bucket=offline_bucket, recovery=recovery,
                              period=period, weather=weather, favor=favor, drop=key)]
            if pool:
                break

    if not pool:
        return None

    if seed:
        pool = sorted(pool, key=lambda it: hashlib.md5(
            f"{seed}|{it['id']}".encode("utf-8")).hexdigest())
        return pool[0]
    if rng is not None:
        return rng.choice(pool)
    return random.choice(pool)
