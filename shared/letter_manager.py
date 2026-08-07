"""V14.3：双子主动来信管理器（纯模板，零 API 费用）。

职责：
- 加载 content/letters.json 模板池（frozen 兼容）
- 冷却校验（首次启动排除 / 8h 最小间隔 / 每日 1 次）
- 离线桶判定（SAME_PERIOD 静默 / CROSS_PERIOD 轻度 / HALF_DAY / DAYS_1_3 / DAYS_3_7 / LONG_ABSENCE）
- 发件人权重采样（按蕾姆好感 favor 三档：<30 / <70 / >=70）
- 白名单占位符安全插值（replace 实现，模板笔误不抛 KeyError）
- twins 复合来信按【蕾姆】/【拉姆】前缀拆分（UI 天然双泡）
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional


def _templates_path() -> str:
    """content/letters.json 绝对路径，兼容 frozen（_MEIPASS）。"""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "content", "letters.json")


class LetterManager:
    """主动来信控制器（纯逻辑，不依赖 Qt/LLM，可单测）。"""

    # 安全插值白名单（防模板注入；replace 实现，未知占位符原样保留）
    PLACEHOLDER_KEYS = {"last_period", "current_period", "days_absent", "hours_absent", "weather"}

    MIN_COOLDOWN_HOURS = 8.0   # 最小触发间隔
    DAILY_CAP = 1              # 每自然日最多触发次数

    def __init__(self, templates_path: Optional[str] = None):
        self.templates: List[Dict[str, Any]] = self._load_templates(
            templates_path or _templates_path())

    def _load_templates(self, path: str) -> List[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    # ── 冷却校验 ─────────────────────────────

    def check_cooldown(self, state, now_ts: float, today_str: str) -> bool:
        """三条红线：首次启动/零交互不触发；每日 1 次；最小间隔 8h。"""
        if state.last_interaction_ts <= 0.0:
            return False  # 首次启动 / 空库：走既有开场引言
        if state.last_letter_date == today_str:
            return False  # 每日上限
        if now_ts - state.last_letter_ts < self.MIN_COOLDOWN_HOURS * 3600:
            return False  # 最小间隔
        return True

    # ── 离线桶判定 ───────────────────────────

    @staticmethod
    def calculate_offline_bucket(hours_since: float, last_period: str, current_period: str) -> Optional[str]:
        if hours_since < 12.0:
            if last_period == current_period:
                return None  # 同时段短离线：静默
            return "CROSS_PERIOD"
        if hours_since < 24.0:
            return "HALF_DAY"
        if hours_since < 72.0:
            return "DAYS_1_3"
        if hours_since < 168.0:
            return "DAYS_3_7"
        return "LONG_ABSENCE"

    # ── 发件人权重（affinity = engine.favor，蕾姆好感）──

    @staticmethod
    def select_sender(favor: float) -> str:
        if favor < 30.0:
            weights = {"ram": 65, "rem": 25, "twins": 10}
        elif favor < 70.0:
            weights = {"ram": 40, "rem": 45, "twins": 15}
        else:
            weights = {"ram": 20, "rem": 55, "twins": 25}
        senders = list(weights.keys())
        probs = list(weights.values())
        return random.choices(senders, weights=probs, k=1)[0]

    # ── 安全插值 ─────────────────────────────

    def interpolate_text(self, text: str, context: dict) -> str:
        """白名单 replace 插值：未知占位符原样保留（模板笔误不崩溃）。"""
        out = text
        for key in self.PLACEHOLDER_KEYS:
            if key in context:
                out = out.replace("{" + key + "}", str(context[key]))
        return out

    # ── twins 拆分 ───────────────────────────

    @staticmethod
    def split_twins_message(interpolated_text: str) -> List[Dict[str, str]]:
        """按【蕾姆】/【拉姆】前缀拆分复合来信为独立消息（UI 双泡、落库成对）。"""
        parsed: List[Dict[str, str]] = []
        for line in interpolated_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("【拉姆】"):
                parsed.append({"sender": "ram", "content": line.replace("【拉姆】", "", 1).strip()})
            elif line.startswith("【蕾姆】"):
                parsed.append({"sender": "rem", "content": line.replace("【蕾姆】", "", 1).strip()})
            else:
                parsed.append({"sender": "rem", "content": line})
        return parsed

    # ── 触发主管道 ───────────────────────────

    def evaluate_and_dispatch(
        self,
        state,
        favor: float,
        current_weather: str,
        now_ts: float,
        today_str: str,
    ) -> Optional[Dict[str, Any]]:
        """来信触发核心入口；返回 None=不触发，否则 {messages, suppress_vignette}。

        state: WorldState（含 last_interaction_ts / last_period / period /
               last_letter_ts / last_letter_date；调用方负责 ensure_last_period）
        """
        if not self.check_cooldown(state, now_ts, today_str):
            return None

        hours_since = (now_ts - state.last_interaction_ts) / 3600.0
        bucket = self.calculate_offline_bucket(hours_since, state.last_period, state.period)
        if bucket is None:
            return None

        target_sender = self.select_sender(favor)

        # 匹配模板：bucket + sender + 好感区间 + 时段条件
        candidates = []
        for t in self.templates:
            if t.get("bucket") != bucket or t.get("sender") != target_sender:
                continue
            cond = t.get("conditions") or {}
            lo = float(cond.get("min_favor", 0))
            hi = float(cond.get("max_favor", 100))
            if not (lo <= favor <= hi):
                continue
            last_p = cond.get("last_periods") or ["all"]
            if "all" not in last_p and state.last_period not in last_p:
                continue
            cur_p = cond.get("current_periods") or ["all"]
            if "all" not in cur_p and state.period not in cur_p:
                continue
            candidates.append(t)

        if not candidates:
            return None

        selected = random.choice(candidates)

        ctx = {
            "last_period": state.last_period,
            "current_period": state.period,
            "days_absent": int(hours_since // 24),
            "hours_absent": int(hours_since),
            "weather": current_weather,
        }
        interpolated = self.interpolate_text(selected.get("text", ""), ctx)

        if selected.get("sender") == "twins":
            messages = self.split_twins_message(interpolated)
        else:
            messages = [{"sender": selected.get("sender", "rem"), "content": interpolated}]

        # 更新冷却状态（调用方负责持久化 world）
        state.last_letter_ts = now_ts
        state.last_letter_date = today_str

        return {
            "messages": messages,
            "suppress_vignette": bool(selected.get("suppress_vignette", True)),
        }
