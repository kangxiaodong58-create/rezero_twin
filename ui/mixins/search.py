"""搜索（顶栏搜索 / 命中高亮）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from shared.search_service import format_preview
from ui.logging_util import _log
from ui.text import highlight_plain_text
from ui.widgets_message import ChatMessageWidget


class SearchMixin:
    """搜索（顶栏搜索 / 命中高亮）。"""

    # ── 历史搜索 ────────────────────────────

    def _on_top_search_changed(self, text: str) -> None:
        """V14.1：顶栏搜索框清空 → 清除全部黄高亮。"""
        if not text.strip():
            self.clear_all_highlights()

    def _do_search(self) -> None:
        query = self.search_box.text().strip()
        if not query:
            return
        # SPEC-20260922-19（B7）：检索统一走 SearchService（原为直连 conv_store.search，
        # 与历史浮层各写一套）；limit=10 为顶栏有意取值（每条结果渲染成系统条，防刷屏）。
        results = self.search_service.search(query, limit=10)
        self.clear_all_highlights()  # V14.1：新搜索先清旧高亮
        if not results:
            self._append_parsed_message("系统", f"未找到包含「{query}」的对话。", "system", save=False, transient=True)
            return
        # V10.9.2：搜索全部瞬时化——不存 DB、自动消失、可点击关闭
        self._append_parsed_message(
            "系统", f"🔍 搜索「{query}」找到 {len(results)} 条", "system", save=False, transient=True
        )
        # V14.1：命中词黄高亮 + 定位第一条结果（滚动 + 金色 2s）
        self.highlight_hits(query)
        self._locate_message(results[0]["id"])
        for r in results:
            sender = r["sender"]
            text = r["content"]
            created = r.get("created_at", "")
            # 时间截取 MM-DD HH:MM（去掉年份和秒）
            time_str = created[5:16] if len(created) >= 16 else created
            # SPEC-20260922-19：摘要格式抽为纯函数（format_preview 默认 60，值等价迁移）
            preview = format_preview(text)
            self._append_parsed_message(
                "系统", f"{time_str} · {sender} → {preview}", "system", save=False, transient=True
            )

    # ── V14.1：搜索命中词黄高亮 ────────────────────

    def highlight_hits(self, keyword: str) -> None:
        """遍历可见消息 widget，把命中词标为黄底（DB/status/content 零改动）。

        仅处理 ChatMessageWidget 且 message_id 且 _status=='normal'
        （recalled 占位无原文、deleted 已移除、failed 不命中搜索）。
        """
        if not keyword:
            return
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if not isinstance(w, ChatMessageWidget):
                continue
            if not getattr(w, "message_id", None) or getattr(w, "_status", "normal") != "normal":
                continue
            try:
                record = self.conv_store.get_by_id(w.message_id)
                if not record:
                    continue
                content = record.get("content", "")
                if not content:
                    continue
                label = w._bubble.findChild(QLabel, "bubble_text")
                if label is None:
                    continue
                label.setText(highlight_plain_text(content, keyword))
                w._search_hit_text = content  # 原文留存，供 clear 恢复
            except Exception as e:
                _log(f"高亮异常 #{getattr(w, 'message_id', '?')}: {e}", durable=True)

    def clear_all_highlights(self) -> None:
        """清除全部黄高亮（恢复原文）。幂等；无高亮时无副作用。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if not isinstance(w, ChatMessageWidget):
                continue
            orig = getattr(w, "_search_hit_text", None)
            if orig is None:
                continue
            label = w._bubble.findChild(QLabel, "bubble_text")
            if label is not None:
                label.setText(orig)
            if hasattr(w, "_search_hit_text"):
                del w._search_hit_text
