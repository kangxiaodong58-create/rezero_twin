"""纪念卡（V15.0「年轮」M2）：把关系事实变成可回看的一张卡。

设计依据：docs/design/V15_0_年轮_关系资产版本构思_2026-08-29.md §3.3。

- 卡片 = 视觉资产里的"相册"：正文 + 日期/好感/篇章/天气快照，落盘
  `data/album/YYYY-MM-DD_{kind}.md`——文件存在即去重（每类每日至多一张）。
- 生成链：L1 可选 LLM（llm_callable，失败/未提供 → L2）→ L2 注册表
  `slot="memorial"` 确定性选型（seed=日期|kind，离线也有卡，vignette 同纪律）。
- 纯 Python，无 PySide6；任何失败静默（返回 None/False）。
"""

from __future__ import annotations

import os
from datetime import date as _date
from typing import Any, Callable, Dict, List, Optional

from . import config

# 触发优先级（同日多事实时取第一个命中的种类）
CARD_KINDS = ("days_milestone", "genesis_annual", "festival")
_KIND_LABELS = {"days_milestone": "相识纪念日", "genesis_annual": "相识周年",
                "festival": "节日"}

_ALBUM_DIRNAME = "album"


def album_dir(data_dir: Optional[str] = None) -> str:
    # 晚绑定（同 life_ledger：避免 from-import 锁死首个数据目录）
    return os.path.join(data_dir or config.get_data_dir(), _ALBUM_DIRNAME)


def card_path(kind: str, today: Any, data_dir: Optional[str] = None) -> str:
    day = today.isoformat() if hasattr(today, "isoformat") else str(today)
    return os.path.join(album_dir(data_dir), f"{day}_{kind}.md")


def has_card(kind: str, today: Any, data_dir: Optional[str] = None) -> bool:
    return os.path.isfile(card_path(kind, today, data_dir))


def _pick_card_text(kind: str, arc: str, seed: str) -> Optional[str]:
    """L2：注册表确定性选型（slot=memorial；arc 回落链由 pick 保证）。"""
    try:
        from shared.template_registry import load_registry, pick as registry_pick
        from shared.vignette import ContentLoader
        registry = load_registry(os.path.join(
            ContentLoader()._get_content_dir(), "templates", "registry.json"))
        return registry_pick(registry, arc=arc, slot="memorial", seed=seed)
    except Exception:
        return None


def generate(kind: str, *, facts: List[Any], arc: str = "mansion_era",
             today: Any = None, llm_callable: Optional[Callable[[str], str]] = None,
             registry_seed_extra: str = "") -> str:
    """生成纪念卡正文。L1（llm_callable(prompt)->text）失败 → L2 注册表。

    facts 用于构造插值上下文（days/festival/years/title）与 L1 提示词。
    返回正文；完全失败返回 ""。
    """
    ctx = _context(facts)
    seed = f"{(today.isoformat() if hasattr(today, 'isoformat') else today)}|{kind}|{registry_seed_extra}"
    if llm_callable is not None:
        try:
            prompt = (
                f"为一张纪念卡写正文（30-60 字，只输出正文）。\n"
                f"纪念类型：{_KIND_LABELS.get(kind, kind)}\n"
                f"事实：{ctx['titles']}。\n"
                "要求：贴合拉姆与蕾姆的口吻（可用一句），温柔而有分量，"
                "不要出现 AI、系统、用户等字眼。"
            )
            text = str(llm_callable(prompt)).strip()
            if text:
                return text[:300]
        except Exception:
            pass
    item = _pick_card_text(kind, arc, seed)
    if not item:
        return ""
    text = item.get("text", "")
    try:
        return text.format(**ctx)
    except Exception:
        return text


def _context(facts: List[Any]) -> Dict[str, str]:
    ctx = {"days": "", "festival": "", "years": "", "titles": ""}
    titles = [getattr(f, "title", "") for f in facts or []]
    ctx["titles"] = "；".join(t for t in titles if t)
    for f in facts or []:
        kind = getattr(f, "kind", "")
        if kind == "days_milestone":
            ctx["days"] = getattr(f, "key", "") or ctx["days"]
        elif kind == "festival":
            ctx["festival"] = getattr(f, "key", "") or ctx["festival"]
        elif kind == "genesis_annual":
            ctx["years"] = getattr(f, "key", "") or ctx["years"]
    return ctx


def save_card(kind: str, today: Any, text: str, *,
              detail: Any = "", data_dir: Optional[str] = None) -> Optional[str]:
    """落盘相册（幂等：已存在返回 None）并镜像账本 kind=memorial。"""
    import json
    path = card_path(kind, today, data_dir)
    if os.path.isfile(path) or not text:
        return None
    day = today.isoformat() if hasattr(today, "isoformat") else str(today)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        detail_str = detail if isinstance(detail, str) else json.dumps(
            detail, ensure_ascii=False)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 纪念卡 · {day}\n\n- **类型**: {_KIND_LABELS.get(kind, kind)}\n"
                    f"- **快照**: {detail_str}\n\n---\n\n{text}\n")
    except Exception:
        return None
    try:
        from . import life_ledger
        life_ledger.get_default_ledger().append(
            kind="memorial", title=f"纪念卡：{_KIND_LABELS.get(kind, kind)}",
            dedup_key=f"memorial|{kind}|{day}", detail={"path": path})
    except Exception:
        pass
    return path
