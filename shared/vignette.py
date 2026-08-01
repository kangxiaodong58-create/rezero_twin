"""Opening Vignette 开场氛围引言生成器（v10.4）。

多级弹力兜底网络：
- L0 缓存层：会话内存缓存 + 持久化 LRU 缓存（data/vignette_cache.json），
  按「时段 | 天气 | 离开天数桶 | 蕾姆好感等级 | 拉姆阶段」状态桶命中，
  相同状态重启毫秒级返回，零 API 成本。
- L1 LLM 主生成：带自修正的重试（≤3 次，温度 0.78 → 0.65 衰减），
  输出经清洗与校验（字数 80~180、违禁词、禁止直接对用户发问）。
- L2 动态母板填充：时段/天气/双子动作槽位的文学性模板，降级不生硬。
- L3 静态兜底：保证 100% 可用性。

上下文隔离铁律：引言是 UI 渲染专属数据（View-Only Data），
绝不写入 LLM 对话历史（messages），防止模型产生人称混淆。
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from typing import Any, Callable, Dict, Optional, Tuple

from shared.config import get_data_dir
from shared.state import WorldState

# LLMCallable 协议：与 llm.bridge.ReZeroLLMBridge.raw_completion 签名一致
LLMCallable = Callable[..., str]

# ── 校验参数 ──────────────────────────────────
MAX_LLM_ATTEMPTS = 3
BASE_TEMPERATURE = 0.78
RETRY_TEMPERATURE = 0.65
MIN_LEN = 80
MAX_LEN = 180

FORBIDDEN_WORDS = [
    "用户", "玩家", "系统", "AI", "大模型", "提示词",
    "您说", "主人您好", "请问有什么", "作为AI", "角色扮演",
]

CACHE_MAX_ENTRIES = 40

# L3 静态兜底
STATIC_FALLBACK = (
    "宅邸静静地立在流淌的时间里。蕾姆与拉姆各自做着手头的事，"
    "没有人先开口，一切都安静得刚刚好。"
)


def _get_cache_path() -> str:
    return os.path.join(get_data_dir(), "vignette_cache.json")


# ═══════════════════════════════════════════════
#  L2：动态模板文学母板
# ═══════════════════════════════════════════════

PERIOD_DESC = {
    "清晨": ["晨光刚刚越过窗沿", "天空还带着一点青白", "宅邸在清晨显得格外安静"],
    "上午": ["上午的光线已经明亮起来", "阳光洒在地板上", "宅邸进入了忙碌却有序的时辰"],
    "午后": ["午后的空气有些懒洋洋的", "阳光偏了角度", "时间在午后显得格外缓慢"],
    "下午": ["下午的光渐渐柔和", "影子开始拉长", "宅邸的节奏稍微放缓"],
    "傍晚": ["暮色正在从窗外漫进来", "天边只剩下最后一丝亮光", "傍晚的宅邸有种安静的过渡感"],
    "夜晚": ["夜色已经完全笼罩了宅邸", "窗外只剩深色的轮廓", "夜晚让一切声音都变得更清晰"],
    "深夜": ["夜已深了", "宅邸里几乎只剩下细微的声响", "深夜的空气带着凉意"],
}

WEATHER_DESC = {
    "晴朗": ["空气清透", "光线格外干净", "没有云层打扰"],
    "多云": ["云层把光线过滤得柔和许多", "天空显得有些沉", "空气里有种说不清的平静"],
    "小雨": ["细雨连绵", "屋檐不时落下水珠", "空气里带着潮湿的气味"],
    "大雨": ["雨声密集而持续", "窗外的世界被雨水模糊", "空气完全被水汽浸透"],
    "阴沉": ["天色压得很低", "光线暗淡", "空气里有种说不出的滞涩"],
}

EXTRA_ATMOSPHERE = [
    "空气中还残留着淡淡的红茶香。",
    "远处隐约能听到风穿过庭院的声音。",
    "时间仿佛被放慢了些许。",
    "一切都安静得刚刚好。",
    "没有人先开口，沉默却并不令人难受。",
]


def fill_dynamic_template(ws: WorldState) -> str:
    """L2 动态槽位填充模板（非死板文本，按世界状态组装）。"""
    period_desc = random.choice(PERIOD_DESC.get(ws.period, ["时间悄然流过"]))
    weather_desc = random.choice(WEATHER_DESC.get(ws.weather, ["天气如常"]))
    rem_action = ws.character_actions.get("rem", "做着手头的事")
    ram_action = ws.character_actions.get("ram", "保持着一贯的姿态")
    extra = random.choice(EXTRA_ATMOSPHERE)

    templates = [
        f"{period_desc}，{weather_desc}。蕾姆{rem_action}，动作很轻。拉姆则{ram_action}。{extra}",
        f"{period_desc}。{weather_desc}。蕾姆正在{rem_action}，拉姆{ram_action}，两人之间维持着熟悉的安静。{extra}",
        f"{weather_desc}的{ws.period}，宅邸显得格外沉静。蕾姆{rem_action}。拉姆{ram_action}。{extra}",
    ]
    return random.choice(templates)


# ═══════════════════════════════════════════════
#  校验与过滤清洗
# ═══════════════════════════════════════════════

def sanitize_and_validate_vignette(text: str) -> Tuple[bool, str]:
    """清洗 LLM 输出并校验。返回 (是否通过, 清洗后文本或失败原因)。"""
    if not text or not isinstance(text, str):
        return False, "Empty output"

    cleaned = text.strip()

    # 移除常见前缀杂质
    prefixes_to_strip = [
        "好的", "以下是", "引言：", "开场：", "【开场引言】",
        "【开场】", "正文：", "```markdown", "```",
    ]
    for prefix in prefixes_to_strip:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].lstrip(" ：:：\n")
    cleaned = cleaned.rstrip("`\n ")

    # raw_completion 异常回包形如「（错误信息）」，整段括号包裹一律视为失败
    if cleaned.startswith("（") and cleaned.endswith("）"):
        return False, "Wrapped error echo"

    # 字数校验
    if len(cleaned) < MIN_LEN:
        return False, f"Too short ({len(cleaned)} chars)"
    if len(cleaned) > MAX_LEN:
        return False, f"Too long ({len(cleaned)} chars)"

    # 违禁词校验
    for word in FORBIDDEN_WORDS:
        if word in cleaned:
            return False, f"Forbidden word found: '{word}'"

    # 人称倾斜校验（防止模型直接对用户发问）
    if "您" in cleaned and ("吗？" in cleaned or "呢？" in cleaned or "吧？" in cleaned):
        return False, "Contains direct interactive dialogue"

    return True, cleaned


# ═══════════════════════════════════════════════
#  L0：本地持久化缓存
# ═══════════════════════════════════════════════

def build_cache_key(ws: WorldState, rem_level: str, ram_stage: str) -> str:
    """按状态桶生成缓存 key（离开天数分桶：0 / 1-2 / 3+）。"""
    days = ws.days_since_last
    days_bucket = "0" if days == 0 else ("1-2" if days <= 2 else "3+")
    raw = f"{ws.period}|{ws.weather}|{days_bucket}|{rem_level}|{ram_stage}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def load_cache() -> Dict[str, str]:
    path = _get_cache_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_cache(cache: Dict[str, str]) -> None:
    path = _get_cache_path()
    try:
        # LRU 简单淘汰：保留最近 CACHE_MAX_ENTRIES 条
        if len(cache) > CACHE_MAX_ENTRIES:
            keys = list(cache.keys())[-CACHE_MAX_ENTRIES:]
            cache = {k: cache[k] for k in keys}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[Vignette] 缓存保存失败: {e}")


# ═══════════════════════════════════════════════
#  核心生成器
# ═══════════════════════════════════════════════

class VignetteGenerator:
    """开场引言多级生成器。

    llm_callable：兼容 (system_prompt, user_prompt, temperature=..., max_tokens=...)
    签名的调用对象（通常传 ReZeroLLMBridge.raw_completion）；为 None 时直接走 L2。
    """

    def __init__(self, llm_callable: Optional[LLMCallable] = None) -> None:
        self.llm_callable = llm_callable
        self._session_cache: Optional[str] = None
        self._persistent_cache: Dict[str, str] = load_cache()

    def _build_prompt(self, ws: WorldState, rem_level: str,
                      independence: float, ram_stage: str) -> Tuple[str, str]:
        event_desc = ws.active_event or "无特殊事件"
        rem_action = ws.character_actions.get("rem", "做着日常事务")
        ram_action = ws.character_actions.get("ram", "在一旁休息")
        system_date = (ws.current_time or "")[:10] or "未知日期"
        hour_text = (ws.current_time or "")[11:16] or ""

        system_text = (
            "你正在为《Re:从零开始的异世界生活》双子女仆系统撰写一段「开场氛围引言」。"
            "风格类似轻小说章节开头的环境与人物描写。使用第三人称，不对用户说话。"
        )
        user_text = f"""【硬性状态（绝对不可修改）】
- 系统日期：{system_date} {hour_text}
- 当前时段：{ws.period}
- 天气：{ws.weather}
- 地点：罗兹瓦尔宅邸
- 距离用户上次到访：{ws.days_since_last} 天
- 蕾姆当前动作：{rem_action}
- 拉姆当前动作：{ram_action}
- 最近事件：{event_desc}
- 蕾姆关系阶段：{rem_level}，人格独立度：{independence:.2f}
- 拉姆评价阶段：{ram_stage}

【写作要求】
1. 使用第三人称，带有轻微文学性的笔调，营造沉浸感。
2. 自然描写当前的时间光影、天气感受，以及蕾姆与拉姆正在做的事情。
3. 可轻微体现两人对环境的感受，但不要过度解读，不要直接对用户说话。
4. 不要总结、不要解释系统、不要出现「用户」「玩家」等词。
5. 字数严格控制在 90～140 字之间。
6. 语气符合原著氛围：可以安静、可以有淡淡温情，也可以有一点寂寥。
请直接输出引言正文，不要加任何前缀或标题。"""
        return system_text, user_text

    def _call_llm(self, system_text: str, user_text: str, temperature: float) -> Optional[str]:
        if self.llm_callable is None:
            return None
        try:
            return self.llm_callable(
                system_text, user_text,
                temperature=temperature, max_tokens=280,
            )
        except Exception as e:
            print(f"[Vignette] LLM 请求异常: {e}")
            return None

    def generate(
        self,
        ws: WorldState,
        rem_favor_level: str = "CLOSE",
        independence: float = 0.5,
        ram_stage: str = "观察中",
        force_refresh: bool = False,
    ) -> str:
        """按 L0 → L1 → L2 → L3 顺序生成开场引言。"""
        # L0：会话级内存缓存
        if self._session_cache and not force_refresh:
            return self._session_cache

        # L0：持久化文件缓存
        cache_key = build_cache_key(ws, rem_favor_level, ram_stage)
        if not force_refresh and cache_key in self._persistent_cache:
            result = self._persistent_cache[cache_key]
            self._session_cache = result
            return result

        # L1：LLM 主路径（带重试与校验）
        if self.llm_callable is not None:
            system_text, user_text = self._build_prompt(
                ws, rem_favor_level, independence, ram_stage)
            for attempt in range(MAX_LLM_ATTEMPTS):
                temperature = BASE_TEMPERATURE if attempt == 0 else RETRY_TEMPERATURE
                raw_text = self._call_llm(system_text, user_text, temperature)
                if raw_text is None:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                ok, result_or_reason = sanitize_and_validate_vignette(raw_text)
                if ok:
                    cleaned = result_or_reason
                    self._persistent_cache[cache_key] = cleaned
                    save_cache(self._persistent_cache)
                    self._session_cache = cleaned
                    return cleaned
                print(f"[Vignette] 第 {attempt + 1} 次校验未通过: {result_or_reason}")
                time.sleep(0.4)
            print("[Vignette] LLM 路径尝试耗尽，降级至动态模板填充 (L2)")

        # L2：动态模板
        try:
            vignette = fill_dynamic_template(ws)
            if vignette:
                self._session_cache = vignette
                return vignette
        except Exception as e:
            print(f"[Vignette] 动态模板异常: {e}")

        # L3：静态兜底
        self._session_cache = STATIC_FALLBACK
        return STATIC_FALLBACK


def generate_opening_vignette(
    ws: WorldState,
    rem_favor_level: str = "CLOSE",
    independence: float = 0.5,
    ram_stage: str = "观察中",
    llm_callable: Optional[LLMCallable] = None,
    force_refresh: bool = False,
) -> str:
    """一次性便捷入口：新建生成器并生成开场引言。"""
    return VignetteGenerator(llm_callable=llm_callable).generate(
        ws,
        rem_favor_level=rem_favor_level,
        independence=independence,
        ram_stage=ram_stage,
        force_refresh=force_refresh,
    )
