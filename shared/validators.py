"""LLM 回复后验校验器（v10.5.x）。

为 ReZeroLLMBridge 提供轻量级输出校验，拦截：
- OOC / 出戏词汇
- 角色台词中出现第一人称「我」
- 格式崩溃（缺少【蕾姆】/【拉姆】）
- 暴露具体好感 / 独立度数值
- API 异常回包形态

只做判定与轻度清洗，不改写语义；校验失败由调用方决定重试或 fallback。
"""

from __future__ import annotations

import re
from typing import NamedTuple, Optional


class ValidationResult(NamedTuple):
    """校验结果。

    Attributes:
        ok: 是否通过校验。
        reason: 失败原因（通过时为 None）。
        cleaned: 轻度清洗后的文本（失败时也可能返回，供日志使用）。
    """

    ok: bool
    reason: Optional[str] = None
    cleaned: Optional[str] = None


class ResponseValidator:
    """校验 LLM 生成的双子回复是否符合角色扮演约束。

    清洗规则保守，校验规则宁可漏拦也不误杀正常文学表达。
    """

    # 出戏 / OOC 词汇表（精确子串匹配）
    # V11.8.1a：移除「您说」（误杀「听您说的」「您说得对」等正常台词）
    FORBIDDEN_WORDS = [
        "用户",
        "玩家",
        "系统",
        "AI",
        "大模型",
        "提示词",
        "角色扮演",
        "作为AI",
        "请问有什么",
        "主人您好",
    ]

    # 上下文敏感词：角色可能合法地在「否认」中提及（如「不是AI」）
    _CONTEXT_SENSITIVE = frozenset({"AI", "系统"})

    # 否定词：出现在敏感词前方 4 字符内时视为「否认」语境
    # 仅保留 2 字否定词（3 字词在 window=4 下可能被截断）
    _NEGATION_WORDS = ("不是", "并非", "不算", "没有")

    # 常见 LLM 开头杂质，仅做清洗，不因此判失败
    PREFIXES_TO_STRIP = [
        "好的",
        "以下是",
        "回复：",
        "回答：",
        "正文：",
        "【系统】",
        "【回复】",
        "```markdown",
        "```",
    ]

    def __init__(self, max_length: int = 1200) -> None:
        self.max_length = max_length

    def _clean(self, text: str) -> str:
        """轻度清洗：去除常见前缀杂质与首尾空白。"""
        cleaned = text.strip()
        for prefix in self.PREFIXES_TO_STRIP:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].lstrip(" ：:：\n")
        cleaned = cleaned.rstrip("`\n ")
        return cleaned

    def _has_ooc(self, text: str) -> Optional[str]:
        """检查是否包含 OOC 词，返回命中的词或 None。

        V11.8.1a：对「AI」「系统」启用否定例外——当该词的所有出现
        均被否定词修饰时（如「蕾姆不是什么AI助手」），视为角色否认，不判 OOC。
        """
        for word in self.FORBIDDEN_WORDS:
            if word not in text:
                continue
            # 上下文敏感词：检查是否所有出现均在否定语境中
            if word in self._CONTEXT_SENSITIVE and self._is_all_negated(text, word):
                continue
            return word
        return None

    def _is_all_negated(self, text: str, word: str, window: int = 4) -> bool:
        """判断 word 在 text 中的所有出现是否均被否定词修饰。

        返回 True 表示全部出现均在否定语境（应放行）；
        返回 False 表示至少有一处非否定出现（应拦截）。
        """
        idx = 0
        found = False
        while True:
            pos = text.find(word, idx)
            if pos == -1:
                return found
            found = True
            before = text[max(0, pos - window):pos]
            if not any(neg in before for neg in self._NEGATION_WORDS):
                return False
            idx = pos + len(word)

    def _has_first_person(self, text: str) -> bool:
        """检查角色台词引号内是否出现独立的第一人称「我」。

        当前 LLM 输出格式为：
            【蕾姆】: "..."
            【拉姆】: "..."
        仅检查引号内内容，并排除「我们」「自己」「自我」等常见描写词。

        V14.4（Trial #2-A 暴露）：第三人称硬约束只属于蕾姆（prompt 仅蕾姆段要求
        「严格使用第三人称自称」）——拉姆是傲娇人设，用「我」/「我可」完全符合
        原著（「姐姐我可没那么容易相信」）。原实现对两角色统一禁「我」，
        导致拉姆正常台词被误杀 → 用户看到「角色拒绝回答」的兜底文案。
        修复：仅对【蕾姆】行检查第一人称；【拉姆】行放行。
        """
        quotes = re.findall(r'【蕾姆】\s*:\s*"([^"]*)"', text)

        for q in quotes:
            # 先遮蔽常见非违规组合，再检查残留的「我」
            masked = re.sub(r"我们|自己|自我|我省略号|我……|我\\.\\.\\.", "〇", q)
            if "我" in masked:
                return True
        return False

    def _has_numeric_favor(self, text: str) -> bool:
        """保守检查是否暴露具体好感或独立度数值。"""
        patterns = [
            r"\d{1,3}\s*/\s*100",
            r"好感[是为]?[：:\s]*\d{1,3}",
            r"独立度[是为]?[：:\s]*\d+\.\d{1,2}",
        ]
        for p in patterns:
            if re.search(p, text):
                return True
        return False

    def _has_format(self, text: str) -> bool:
        """检查是否包含至少一个角色标签。"""
        return "【蕾姆】" in text or "【拉姆】" in text

    def _is_error_echo(self, text: str) -> bool:
        """API 异常回包常见形态：整段被中文括号包裹。"""
        return text.startswith("（") and text.endswith("）")

    def validate(self, text: str) -> ValidationResult:
        """清洗并校验 LLM 回复。

        Args:
            text: 原始 LLM 回复文本。

        Returns:
            ValidationResult: (是否通过, 失败原因, 清洗后文本)
        """
        if not text or not isinstance(text, str):
            return ValidationResult(ok=False, reason="Empty output", cleaned=None)

        cleaned = self._clean(text)

        if len(cleaned) > self.max_length:
            return ValidationResult(
                ok=False,
                reason=f"Too long ({len(cleaned)} chars)",
                cleaned=cleaned,
            )

        if self._is_error_echo(cleaned):
            return ValidationResult(
                ok=False, reason="Wrapped error echo", cleaned=cleaned
            )

        ooc = self._has_ooc(cleaned)
        if ooc:
            return ValidationResult(
                ok=False, reason=f"OOC word: {ooc}", cleaned=cleaned
            )

        if self._has_first_person(cleaned):
            return ValidationResult(
                ok=False,
                reason="First person '我' in character line",
                cleaned=cleaned,
            )

        if self._has_numeric_favor(cleaned):
            return ValidationResult(
                ok=False,
                reason="Exposed numeric favor/independence",
                cleaned=cleaned,
            )

        if not self._has_format(cleaned):
            return ValidationResult(
                ok=False,
                reason="Missing 【蕾姆】/【拉姆】 tags",
                cleaned=cleaned,
            )

        return ValidationResult(ok=True, cleaned=cleaned)
