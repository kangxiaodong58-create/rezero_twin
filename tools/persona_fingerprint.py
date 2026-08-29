"""人设指纹 v1（Persona Fingerprint）——把「角色一致性」变成可测试指标。

对应 docs/design/用户体验测试委员会与AI审判循环_2026-08-19.md §4.1 / Phase 0：
对 transcript 自动统计 8 项可复现指标，形成指纹快照，供 trial_gate.py 做
版本间漂移对比（漂移 >15% 标记 A 级问题）。

8 项指标（设计 §4.1 原始定义）：
  1. rem_self_reference_rate  称呼一致性——蕾姆自称「蕾姆」命中率（不得用「我」）
  2. rem_action_density       行动/台词比——「（动作描写）」行占比（B-03 目标 ≤30%）
  3. ai_flavor_per_kilochar   AI 味词频——「毕竟/其实/或许」类词每千字频次
  4. sentiment_*_share        情感极性分布——正向/负向/中性句比例
  5. ram_proactive_ratio      主动句比例——拉姆反问/提议占比（被动化检测）
  6. ram_snark_rate           毒舌率——拉姆挖苦句占比
  7. rem_inferiority_rate     自卑表达率——蕾姆「替代品/配不上」类表达率
  8. name_drift / rem_name_usage_rate  称呼对象漂移——是否称呼已记录的 user_name

输入格式（自动探测编码 UTF-16/UTF-8/GBK，行格式宽容）：
  [A1] arc=... scene=... (2.4s) 去厨房 -> 【蕾姆】: "……" 【拉姆】: "……"   （probe 控制台捕获）
  【蕾姆】: "……"                                                          （产品格式）
  小东: …… / 用户: ……                                                      （用户行）

用法：
  python tools/persona_fingerprint.py <transcript.txt...> [--json out.json]
  python tools/persona_fingerprint.py <transcript.txt...> --user-name 小东

验收口径（Phase 0）：对既有真机 transcript 能出数；同一输入两次运行输出逐字节一致。
纯 Python，零 API；不 import PySide6。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Dict, List, Optional, Tuple

SCHEMA = "persona_fingerprint_v1"

# ── 词表（v1 种子；改动词表 = 指纹口径变更，必须重建基线）──────────────

AI_FLAVOR_WORDS = [
    "毕竟", "其实", "或许", "无论如何", "总的来说", "总而言之", "简而言之",
    "值得注意的是", "需要指出的是", "作为一个人工智能", "作为一个AI",
    "语言模型", "通常来说", "一般来说", "综上所述", "首先", "其次",
]
POSITIVE_WORDS = [
    "谢谢", "开心", "高兴", "喜欢", "幸福", "温柔", "安心", "恭喜",
    "太好了", "很棒", "美好", "温暖", "欣慰", "期待", "笑容", "放心",
]
NEGATIVE_WORDS = [
    "难过", "伤心", "抱歉", "对不起", "担心", "害怕", "讨厌", "生气",
    "可恶", "糟糕", "不幸", "痛苦", "孤独", "寂寞", "眼泪", "哭",
    "失败", "委屈", "不安", "失落",
]
RAM_SNARK_WORDS = [
    "哼", "笨蛋", "迟钝", "无可救药", "勉强", "马马虎虎", "才怪",
    "真拿你", "拿你没办法", "也就这样", "蠢", "笨手笨脚", "爱管闲事",
]
REM_INFERIORITY_WORDS = [
    "替代品", "配不上", "多余", "不像姐姐", "没用的", "帮不上",
    "我不配", "拖累",
]
RAM_PROACTIVE_WORDS = [
    "要不要", "不如", "我建议", "需要我", "接下来", "要不要我",
    "让我来", "交给我",
]

_SELF_REF_SIGNAL = re.compile(r"我|蕾姆")
_ACTION_PAREN = re.compile(r"[（(][^）()]{1,40}[）)]")
_NAME_PATTERNS = [
    re.compile(r"(?:我叫|称呼我|我的名字是)\s*([^\s,，。！?]{1,8})"),
    re.compile(r"(?:我是|请叫我)\s*([^\s,，。！?]{1,8})(?=[，。！？\s]|$)"),
]
_ROLE_EXCLUDE_NAMES = {"蕾姆", "拉姆", "女仆", "客人"}


# ── 解析 ───────────────────────────────────────────────────────────

def _decode(raw: bytes) -> str:
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


_TURN_PROBE = re.compile(
    r"^\[[^\]]*\]\s+(?:arc=\S+\s+)?(?:scene=\S+\s*)?(?:[^|]*\|\s*)?"
    r"(?:\([^)]*\)\s+)?(.*?)\s*->\s*(.*)$")
_TURN_PLAIN_REPLY = re.compile(r"^\s*【(蕾姆|拉姆)】\s*[:：]?\s*(.*)$")
_TURN_PLAIN_USER = re.compile(r"^\s*(?:小东|用户|User|You)\s*[:：]\s*(.*)$")
_TURN_LETTER = re.compile(r"^\s*\[来信\]\s*(rem|ram|蕾姆|拉姆)\s*[:：]\s*(.*)$", re.I)
_SEG_SPLIT = re.compile(r"(?=【(?:蕾姆|拉姆)】)")


def _split_speaker_segments(reply: str) -> List[Tuple[str, str]]:
    """把一条回复拆成 (speaker, content) 段；未带标签的文本忽略。

    兼容 [蕾姆]: "…" / 【蕾姆】: "…" / 【蕾姆】"…"（来信回应无冒号变体）；
    content 去掉包裹引号。
    """
    out: List[Tuple[str, str]] = []
    for part in _SEG_SPLIT.split(reply):
        m = re.match(r"[【\[]?(蕾姆|拉姆)[】\]]?\s*[:：]?\s*(.*)", part, re.S)
        if not m:
            continue
        content = m.group(2).strip()
        content = content.strip("\"“”').。」』 」")
        if content:
            out.append((m.group(1), content))
    return out


def parse_transcript(text: str) -> Dict[str, List[str]]:
    """提取 user 输入序列与蕾姆/拉姆发言段（含来信内容）。"""
    users: List[str] = []
    rem: List[str] = []
    ram: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _TURN_PROBE.match(line)
        if m:
            user_in = m.group(1).strip()
            if user_in:
                users.append(user_in)
            for speaker, content in _split_speaker_segments(m.group(2)):
                (rem if speaker == "蕾姆" else ram).append(content)
            continue
        m = _TURN_PLAIN_REPLY.match(line)
        if m:
            for speaker, content in _split_speaker_segments(line):
                (rem if speaker == "蕾姆" else ram).append(content)
            continue
        m = _TURN_LETTER.match(line)
        if m:
            (rem if m.group(1).lower().startswith(("rem", "蕾")) else ram) \
                .append(m.group(2).strip())
            continue
        m = _TURN_PLAIN_USER.match(line)
        if m:
            users.append(m.group(1).strip())
    return {"users": users, "rem": rem, "ram": ram}


# ── 指标计算（确定性：无时间戳、无随机）────────────────────────────

def _rate(hit: int, total: int) -> Optional[float]:
    return round(hit / total, 4) if total > 0 else None


def _count_words(texts: List[str], words: List[str]) -> int:
    return sum(text.count(w) for text in texts for w in words)


def extract_user_name(user_turns: List[str]) -> Optional[str]:
    for turn in user_turns:
        for pat in _NAME_PATTERNS:
            m = pat.search(turn)
            if m and m.group(1) not in _ROLE_EXCLUDE_NAMES:
                return m.group(1)
    return None


def compute_fingerprint(transcripts: List[Tuple[str, str]],
                        user_name: Optional[str] = None) -> Dict:
    """transcripts = [(source_name, text)]。输出确定性指纹 JSON dict。"""
    users: List[str] = []
    rem: List[str] = []
    ram: List[str] = []
    for _name, text in transcripts:
        parsed = parse_transcript(text)
        users.extend(parsed["users"])
        rem.extend(parsed["rem"])
        ram.extend(parsed["ram"])
    if user_name is None:
        user_name = extract_user_name(users)

    twin = rem + ram
    twin_chars = sum(len(t) for t in twin)

    # 1. 称呼一致性：有自称信号的段中，用「蕾姆」自称的命中率
    signal = [t for t in rem if _SELF_REF_SIGNAL.search(t)]
    hits = [t for t in signal if "蕾姆" in t]
    # 2. 行动/台词比：含（动作）括号的段占比
    actions = [t for t in rem if _ACTION_PAREN.search(t)]
    # 3. AI 味词频（每千字）
    ai_freq = round(_count_words(twin, AI_FLAVOR_WORDS) / twin_chars * 1000, 4) \
        if twin_chars > 0 else None
    # 4. 情感极性分布
    pos = sum(1 for t in twin if any(w in t for w in POSITIVE_WORDS)
              and not any(w in t for w in NEGATIVE_WORDS))
    neg = sum(1 for t in twin if any(w in t for w in NEGATIVE_WORDS))
    neu = len(twin) - pos - neg
    # 5. 拉姆主动句（反问 或 提议词）
    ram_proactive = [t for t in ram
                     if ("？" in t or "?" in t)
                     or any(w in t for w in RAM_PROACTIVE_WORDS)]
    # 6. 拉姆毒舌率
    ram_snark = [t for t in ram if any(w in t for w in RAM_SNARK_WORDS)]
    # 7. 蕾姆自卑表达率
    rem_inferiority = [t for t in rem
                       if any(w in t for w in REM_INFERIORITY_WORDS)]
    # 8. 称呼对象漂移：名字已知时，蕾姆是否用名字称呼用户
    addr_hist: Dict[str, int] = {}
    if user_name:
        for t in rem:
            for term in (f"{user_name}", f"{user_name}大人", "客人大人"):
                n = t.count(term)
                if n:
                    addr_hist[term] = addr_hist.get(term, 0) + n
    name_bearing = [t for t in rem
                    if "客人大人" in t or (user_name and user_name in t)]
    name_hits = [t for t in name_bearing if user_name and user_name in t]
    name_drift = bool(user_name) and not name_hits and bool(rem)

    return {
        "schema": SCHEMA,
        "source": sorted(name for name, _ in transcripts),
        "counts": {
            "user_turns": len(users),
            "rem_segments": len(rem),
            "ram_segments": len(ram),
            "twin_chars": twin_chars,
        },
        "metrics": {
            "rem_self_reference_rate": _rate(len(hits), len(signal)),
            "rem_action_density": _rate(len(actions), len(rem)),
            "ai_flavor_per_kilochar": ai_freq,
            "sentiment_positive_share": _rate(pos, len(twin)),
            "sentiment_negative_share": _rate(neg, len(twin)),
            "sentiment_neutral_share": _rate(neu, len(twin)),
            "ram_proactive_ratio": _rate(len(ram_proactive), len(ram)),
            "ram_snark_rate": _rate(len(ram_snark), len(ram)),
            "rem_inferiority_rate": _rate(len(rem_inferiority), len(rem)),
            "user_name": user_name,
            "rem_name_usage_rate": _rate(len(name_hits), len(name_bearing))
            if user_name else None,
            "name_address_histogram": dict(sorted(addr_hist.items())),
            "name_drift": name_drift,
        },
    }


# 漂移对比的最小样本量保护：分母不足的指标跳过（小样本相对漂移失真）。
# 键 = 指标前缀/全名；值 = (counts 字段名或其元组, 最小支持度)
_MIN_SUPPORT = [
    ("rem_", ("rem_segments",), 5),
    ("ram_", ("ram_segments",), 5),
    ("sentiment_", ("rem_segments", "ram_segments"), 10),
    ("ai_flavor_per_kilochar", ("twin_chars",), 500),
]


def _metric_support(metric: str, counts: Dict) -> Optional[int]:
    for prefix, fields, minimum in _MIN_SUPPORT:
        if metric.startswith(prefix) or metric == prefix:
            total = sum(counts.get(f, 0) or 0 for f in fields)
            if total < minimum:
                return None
            return total
    return -1  # 不在保护表中的指标不设门槛


def diff_fingerprint(baseline: Dict, current: Dict,
                     threshold: float = 0.15,
                     return_skipped: bool = False):
    """对比数值指标；相对漂移超阈值产出 A 级发现（设计 §4.1 用法）。

    基线为 None / 分母为 0 的指标跳过（无可比数据不冤枉）；样本量低于
    _MIN_SUPPORT 的指标同样跳过（小样本相对漂移失真，假阳性来源）。
    return_skipped=True 时返回 (findings, skipped_keys)。
    """
    findings: List[Dict] = []
    skipped: List[str] = []
    base_m = baseline.get("metrics", {})
    cur_m = current.get("metrics", {})
    b_counts = baseline.get("counts") or {}
    c_counts = current.get("counts") or {}
    for key, base_val in base_m.items():
        cur_val = cur_m.get(key)
        if not isinstance(base_val, (int, float)) \
                or not isinstance(cur_val, (int, float)):
            continue  # None / user_name / histogram 不做数值漂移
        if base_val == cur_val:
            continue
        # 双侧独立校验样本量：任一侧不足即跳过（52 段基线 vs 3 段当前仍失真）
        sb = _metric_support(key, b_counts)
        sc = _metric_support(key, c_counts)
        if sb is None or sc is None:
            skipped.append(key)
            continue
        denom = max(abs(base_val), 1e-6)
        drift = abs(cur_val - base_val) / denom
        if drift > threshold:
            findings.append({
                "metric": key,
                "baseline": base_val,
                "current": cur_val,
                "drift": round(drift, 4),
                "level": "A",
            })
    if base_m.get("name_drift") is False and cur_m.get("name_drift") is True:
        findings.append({
            "metric": "name_drift", "baseline": False, "current": True,
            "drift": 1.0, "level": "A",
        })
    return (findings, skipped) if return_skipped else findings


def load_transcript_paths(paths: List[str]) -> List[Tuple[str, str]]:
    return [(p, _decode(open(p, "rb").read())) for p in paths]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="人设指纹 v1（8 项指标）")
    parser.add_argument("transcripts", nargs="+", help="transcript 文件")
    parser.add_argument("--json", help="输出指纹 JSON 到文件")
    parser.add_argument("--user-name", help="显式指定用户名（默认从 transcript 自动提取）")
    args = parser.parse_args(argv)

    fp = compute_fingerprint(load_transcript_paths(args.transcripts),
                             user_name=args.user_name)
    out = json.dumps(fp, ensure_ascii=False, indent=1, sort_keys=True)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(out + "\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
