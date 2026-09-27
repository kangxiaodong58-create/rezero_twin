"""SPEC-20260922-19（B7）：两条搜索入口的单一实现（UI 无关，零 Qt 依赖）。

背景：顶栏搜索（``TwinChatApp._do_search``）与历史浮层搜索（``HistoryOverlay._do_search``）
各自写了一套「检索 + 空值/异常兜底」逻辑——数据层虽同为 ``ConversationStore.search()``
（FTS5 快路径 + LIKE CJK 兜底），UI 侧却存在重复与漂移风险。本模块把检索路径收口为单一实现。

口径（SPEC-19 §设计 3，写死不留发挥）：

- **limit 有意不同**：顶栏 ``10``（每条结果都渲染成聊天区系统条，防刷屏）、浮层 ``50``（列表浏览）。
  等价性判据因此定义为「同 query + 同 limit → 结果集与顺序逐条相同」。
- **无结果文案各用各的**（零观感批，不改用户可见文案）；服务只负责「有没有结果」的判定。
- **异常兜底统一在服务层**：浮层原有 ``try/except → []``；顶栏原**无**兜底（DB 异常会直接冒泡炸 UI）
  → 由本服务补上（仅影响错误路径，改变的是「炸」而非「显示什么」）。

迁移自：``gui.py`` 顶栏 ``_do_search``（原 ``:2421``，硬编码 ``limit=10`` 与 ``text[:60]``）
与 ``HistoryOverlay._do_search``（原 ``:1574``，``limit=50`` + 本地 try/except）。
"""

from __future__ import annotations

from typing import Any, Dict, List

DEFAULT_LIMIT = 50  # 浮层浏览用；顶栏显式传 10
PREVIEW_WIDTH = 60  # 顶栏结果行摘要宽度（迁移前为硬编码 60，值等价）


class SearchService:
    """对话检索的单一入口。

    构造入参为 ``ConversationStore``（或任何提供同名 ``search(query, limit=...)`` 的对象，
    便于测试替身注入）。本类不含任何 Qt 依赖，可脱离 GUI 单测。
    """

    def __init__(self, conv_store: Any) -> None:
        self._store = conv_store

    def search(self, query: str, limit: int = DEFAULT_LIMIT) -> List[Dict[str, Any]]:
        """按关键词检索对话记录。

        - 空串 / 纯空白：直接返回 ``[]``（不触碰 store）；
        - store 抛异常：吞掉并返回 ``[]``（兜底，见模块 docstring）；
        - 查询串在服务层统一 ``strip()``（含首尾空白的查询等价于去空白后检索）。
        """
        q = (query or "").strip()
        if not q:
            return []
        try:
            results = self._store.search(q, limit=limit)
        except Exception:
            return []
        return list(results or [])


def format_preview(content: str, width: int = PREVIEW_WIDTH) -> str:
    """顶栏搜索结果行的正文摘要：``content[:width] + '…'``（超长才加省略号）。

    迁移前该逻辑内联于 ``TwinChatApp._do_search``（硬编码 60），此处**值等价**抽为纯函数。
    注：历史浮层的摘要走的是另一套（``HistoryItemWidget.PREVIEW_WORDS = 80``，逐条渲染高亮），
    本批不动——见 SPEC-19 §设计 3。
    """
    text = content or ""
    return text[:width] + ("…" if len(text) > width else "")
