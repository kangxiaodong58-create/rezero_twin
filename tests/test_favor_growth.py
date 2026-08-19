"""V13.1：好感增长曲线回归测试（无框架，直接运行，零 API 费用）。

覆盖（验收用例）：
- 20 轮普通友善 → 蕾姆 favor 可观察增长（陪伴通道）
- 同等条件下拉姆涨幅不系统性超过蕾姆（本地模式无条件 +1 已删）
- 危险后仍可恢复上涨（风控保留且不冻死）
- 陪伴通道防刷（5涨3停）
- 存档读写一致

用法：python tests/test_favor_growth.py
"""
from __future__ import annotations

import os
import sys
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.state import HardStateEngine
from shared.memory_store import MemoryStore

# 已证零关键词命中的普通友善输入（诊断实验同款）
PLAIN = [
    "今天天气不错呢", "你们在忙什么呀", "宅邸里真安静", "我回来了",
    "今天的红茶很好喝", "花园的花开了", "我坐一会儿就走",
    "晚上要不要一起看月亮", "那就先这样吧",
]
PRAISE = [
    "谢谢你", "你们辛苦了", "蕾姆真棒", "谢谢你们一直陪着我",
    "你们真好", "有你们在真好",
]


def test_plain_favor_grows() -> None:
    """20 轮普通友善 → 蕾姆可观察增长（≥+5），拉姆不涨。"""
    eng = HardStateEngine()
    for i in range(20):
        eng.update(PLAIN[i % len(PLAIN)])
    growth = eng.favor - 15
    assert growth >= 5, f"20 轮友善应至少 +5，实际 {growth}"
    assert eng.ram_favor == 8, f"拉姆不应随普通友善增长，实际 {eng.ram_favor}"


def test_praise_rem_leads_ram() -> None:
    """10 轮夸奖 → 蕾姆涨幅 ≥ 拉姆涨幅。"""
    eng = HardStateEngine()
    for i in range(10):
        eng.update(PRAISE[i % len(PRAISE)])
    rem_growth = eng.favor - 15
    ram_growth = eng.ram_favor - 8
    assert rem_growth >= ram_growth, f"蕾姆涨幅应 ≥ 拉姆：rem={rem_growth} ram={ram_growth}"


def test_recover_after_danger() -> None:
    """高危扣分后，友善轮仍可恢复上涨（不冻死）。"""
    eng = HardStateEngine()
    eng.update("黑化吧")  # 高危 -12
    eng.update("我要侮辱拉姆")  # 高危 -12（再扣）
    eng.update("有魔兽袭击！快跑")  # DANGER（鬼化，不扣 favor）
    after_danger = eng.favor
    for i in range(10):
        eng.update(PLAIN[i % len(PLAIN)])
    assert eng.favor > after_danger, f"危险后应恢复上涨：{after_danger} → {eng.favor}"


def test_companion_cap() -> None:
    """陪伴通道 5涨3停：25 轮增长有限（≤18），防刷生效。"""
    eng = HardStateEngine()
    for i in range(25):
        eng.update(PLAIN[i % len(PLAIN)])
    growth = eng.favor - 15
    assert growth <= 18, f"25 轮应受防刷限制（≤18），实际 {growth}"
    assert growth >= 5, f"25 轮仍应有可观察增长，实际 {growth}"


def test_local_mode_ram_not_unconditional() -> None:
    """10 轮普通对话拉姆不再无条件 +1（V13.1 修复点，V14.4 改引擎直测）。"""
    eng = HardStateEngine()
    for i in range(10):
        eng.update(PLAIN[i % len(PLAIN)])
    assert eng.ram_favor == 8, f"普通对话拉姆不应无条件涨，实际 {eng.ram_favor}"
    # 蕾姆走陪伴通道应有增长
    assert eng.favor > 15, "普通对话蕾姆应有陪伴增长"


def test_memory_roundtrip() -> None:
    """存档读写一致（favor/ram_favor/events）。"""
    tmpdir = tempfile.mkdtemp()
    store = MemoryStore(root_dir=tmpdir)
    eng = HardStateEngine()
    eng.update("谢谢你")
    eng.update("黑化吧")
    data = store.load()
    data.update({"favor": eng.favor, "ram_favor": eng.ram_favor,
                 "events": eng.events, "user_name": eng.user_name})
    store.save(data)
    loaded = store.load()
    assert loaded["favor"] == eng.favor, "favor 存档不一致"
    assert loaded["ram_favor"] == eng.ram_favor, "ram_favor 存档不一致"
    assert loaded["events"] == eng.events, "events 存档不一致"


def main() -> int:
    tests = [
        ("20 轮友善 → 蕾姆 +5 可观察增长、拉姆不涨", test_plain_favor_grows),
        ("10 轮夸奖 → 蕾姆涨幅 ≥ 拉姆", test_praise_rem_leads_ram),
        ("危险后仍可恢复上涨", test_recover_after_danger),
        ("陪伴防刷 5涨3停（25 轮 ≤18）", test_companion_cap),
        ("本地模式拉姆不再无条件 +1（修复点回归）", test_local_mode_ram_not_unconditional),
        ("存档读写一致", test_memory_roundtrip),
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
