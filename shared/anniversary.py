"""纪念日引擎（V15.0「年轮」M2）：把"时间"变成可注入、可纪念的事实。

设计依据：docs/design/V15_0_年轮_关系资产版本构思_2026-08-29.md §3.2。

原则：
- 纯计算、零 API、确定性——与账本（life_ledger）同一纪律：事实归规则层。
- 节日表为**静态对照表**（2026–2030），避免引入农历库依赖；日期经香港
  天文台公农历对照表等多源校准。**元宵节不存储**：恒等于春节+14 天
  （正月十五），代码推导消灭双源。
- 表外年份（2031+）无节日数据——compute_facts 只是不再产出节日事实，
  相识天数不受影响；表按年扩（新增一年 = 加一行）。

产出四类事实（AnniversaryFact）：
  genesis_days      相识第 N 天（每日）
  days_milestone    相识第 100/365/1000… 天（台账记录 + 纪念卡触发）
  genesis_annual    相识 N 周年
  festival          今天是某节日——"一起度过的第 N 个"（由相识日推算，不依赖历史记录）
  festival_upcoming 3 天内即将到来的节日
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

# ── 节日静态对照表（2026–2030；农历经多源校准）────────────────────

# 春节（正月初一）——表锚点
_SPRING: Dict[int, Tuple[int, int]] = {
    2026: (2, 17), 2027: (2, 6), 2028: (1, 26), 2029: (2, 13), 2030: (2, 3),
}
# 其他农历节日（端午=五月初五 / 七夕=七月初七 / 中秋=八月十五）
_LUNAR: Dict[int, Dict[str, Tuple[int, int]]] = {
    2026: {"端午节": (6, 19), "七夕节": (8, 19), "中秋节": (9, 25)},
    2027: {"端午节": (6, 9), "七夕节": (8, 8), "中秋节": (9, 15)},
    2028: {"端午节": (5, 28), "七夕节": (8, 26), "中秋节": (10, 3)},
    2029: {"端午节": (6, 16), "七夕节": (8, 16), "中秋节": (9, 22)},
    2030: {"端午节": (6, 5), "七夕节": (8, 5), "中秋节": (9, 12)},
}
# 公历节日（覆盖表内全部年份）
_SOLAR: Dict[Tuple[int, int], str] = {
    (1, 1): "元旦", (2, 14): "情人节", (12, 24): "平安夜", (12, 25): "圣诞节",
}

# 相识天数里程碑（触发行内祝福 + 台账 + 纪念卡）
DAYS_MILESTONES = (100, 200, 300, 365, 500, 730, 1000, 1500, 2000, 3000)

# 元宵节与春节的固定间隔（正月十五）
_LANTERN_OFFSET_DAYS = 14


@dataclass
class AnniversaryFact:
    """一条当日关系事实（title 为可直接注入/展示的一句话）。"""

    kind: str        # genesis_days | days_milestone | genesis_annual | festival | festival_upcoming
    title: str
    key: str = ""    # 附加键：天数 / 节日名 / 周年数


_FESTIVAL_TABLE: Optional[Dict[str, str]] = None


def build_festival_table() -> Dict[str, str]:
    """展开全部节日 → {"YYYY-MM-DD": 名称}（含推导的元宵节；排序稳定）。"""
    table: Dict[str, str] = {}
    for year, (month, day) in _SPRING.items():
        spring = date(year, month, day)
        table[spring.isoformat()] = "春节"
        lantern = spring + timedelta(days=_LANTERN_OFFSET_DAYS)
        table[lantern.isoformat()] = "元宵节"
    for year, mapping in _LUNAR.items():
        for name, (month, day) in mapping.items():
            table[f"{year:04d}-{month:02d}-{day:02d}"] = name
    for (month, day), name in _SOLAR.items():
        for year in _SPRING:
            table[f"{year:04d}-{month:02d}-{day:02d}"] = name
    return dict(sorted(table.items()))


def _festivals() -> Dict[str, str]:
    global _FESTIVAL_TABLE
    if _FESTIVAL_TABLE is None:
        _FESTIVAL_TABLE = build_festival_table()
    return _FESTIVAL_TABLE


def festival_on(day: date) -> str:
    return _festivals().get(day.isoformat(), "")


def festival_upcoming(day: date, look_ahead: int = 3) -> Optional[Tuple[str, int]]:
    """未来 look_ahead 天内最近的节日 → (名称, 还差几天)；无则 None。"""
    for offset in range(1, look_ahead + 1):
        name = festival_on(day + timedelta(days=offset))
        if name:
            return name, offset
    return None


def genesis_days(genesis: date, today: date) -> int:
    """相识天数（含首尾：相识当天 = 第 1 天）。"""
    return (today - genesis).days + 1


def count_festival_between(name: str, genesis: date, today: date) -> int:
    """[genesis, today] 内该节日的第几次（表外年份不计——诚实下界）。"""
    lo, hi = genesis.isoformat(), today.isoformat()
    return sum(1 for d, n in _festivals().items() if n == name and lo <= d <= hi)


def compute_facts(*, genesis: date, today: date) -> List[AnniversaryFact]:
    """计算当日全部关系事实（纯函数；today < genesis 返回空）。"""
    if today < genesis:
        return []
    facts: List[AnniversaryFact] = []
    days = genesis_days(genesis, today)
    facts.append(AnniversaryFact(
        "genesis_days", f"今天是你们相识的第 {days} 天"))
    if days in DAYS_MILESTONES:
        facts.append(AnniversaryFact(
            "days_milestone",
            f"今天是你们相识的第 {days} 天——一个值得记住的日子", key=str(days)))
    if days > 1 and genesis.month == today.month and genesis.day == today.day:
        years = today.year - genesis.year
        facts.append(AnniversaryFact(
            "genesis_annual", f"今天是你们相识 {years} 周年", key=str(years)))
    name = festival_on(today)
    if name:
        nth = count_festival_between(name, genesis, today)
        facts.append(AnniversaryFact(
            "festival",
            f"今天是{name}——这是你们一起度过的第 {nth} 个{name}", key=name))
    else:
        up = festival_upcoming(today, 3)
        if up:
            fname, left = up
            facts.append(AnniversaryFact(
                "festival_upcoming", f"还有 {left} 天就是{fname}了", key=fname))
    return facts
