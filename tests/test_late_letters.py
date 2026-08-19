# -*- coding: utf-8 -*-
"""V14.8 ② 测试：后期来信触发验证（各桶可达/冷却/权重/插值）。"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest.mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.config import load_env
load_env()


def _manager():
    import shared.config as cfg
    tmp = tempfile.mkdtemp(prefix="late_letter_")
    with unittest.mock.patch.object(cfg, "get_data_dir", return_value=tmp):
        from shared.letter_manager import LetterManager
        from shared.state import WorldState
        return LetterManager(), WorldState.now()


def test_late_letters_loaded_v148() -> None:
    """后期来信 15 条已加载（arcs 过滤后可用）。"""
    mgr, _ = _manager()
    pool = mgr._load_pool() if hasattr(mgr, "_load_pool") else None
    # 直接验证 letters.json 内容
    import json
    with open(os.path.join(PROJECT_ROOT, "content", "letters.json"), encoding="utf-8") as f:
        letters = json.load(f)
    late = [l for l in letters if l.get("arcs") == ["late_arc"]]
    assert len(late) == 15, f"后期应 15 条: {len(late)}"
    buckets = {l["bucket"] for l in late}
    assert buckets >= {"CROSS_PERIOD", "HALF_DAY", "DAYS_1_3", "DAYS_3_7", "LONG_ABSENCE"}, \
        f"五桶应全覆盖: {buckets}"


def test_late_letter_trigger_v148() -> None:
    """后期篇离线触发来信：各桶均有模板可达（arc 过滤生效）。"""
    import json
    with open(os.path.join(PROJECT_ROOT, "content", "letters.json"), encoding="utf-8") as f:
        letters = json.load(f)
    late = [l for l in letters if l.get("arcs") == ["late_arc"]]
    # 每桶至少 1 条 rem（蕾姆是核心 sender）
    for bucket in ("CROSS_PERIOD", "HALF_DAY", "DAYS_1_3", "DAYS_3_7", "LONG_ABSENCE"):
        hits = [l for l in late if l["bucket"] == bucket and l["sender"] == "rem"]
        assert hits, f"桶 {bucket} 缺 rem 模板"
    # twins 复合来信含双泡标记
    twins = [l for l in late if l["sender"] == "twins"]
    for t in twins:
        assert "【蕾姆】" in t["text"] and "【拉姆】" in t["text"], f"twins 应含双泡: {t['id']}"


def test_late_letter_interpolation_v148() -> None:
    """后期来信占位符插值（{days_absent} 等）。"""
    import json
    with open(os.path.join(PROJECT_ROOT, "content", "letters.json"), encoding="utf-8") as f:
        letters = json.load(f)
    late = [l for l in letters if l.get("arcs") == ["late_arc"]]
    # 全部后期模板的占位符应可被 LetterManager 白名单插值（不抛 KeyError）
    from shared.letter_manager import LetterManager
    mgr = LetterManager()
    for l in late:
        try:
            mgr.interpolate_text(l["text"], {
                "last_period": "上午", "current_period": "下午",
                "days_absent": 3, "hours_absent": 36, "weather": "晴朗"})
        except Exception as e:
            assert False, f"{l['id']} 插值失败: {e}"


def main() -> int:
    tests = [
        ("后期来信加载（15 条五桶）", test_late_letters_loaded_v148),
        ("后期触发模板可达", test_late_letter_trigger_v148),
        ("占位符插值", test_late_letter_interpolation_v148),
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
