"""消息操作（引用 / 撤回 / 删除 / 桥接历史）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QMessageBox

from ui.logging_util import _log


class MessageOpsMixin:
    """消息操作（引用 / 撤回 / 删除 / 桥接历史）。"""

    # ── V14.2：引用回复 ────────────────────────

    def _on_quote_request(self, message_id: int) -> None:
        """右键「引用」：校验消息仍为 normal，展示引用条。"""
        try:
            record = self.conv_store.get_by_id(message_id)
        except Exception as e:
            _log(f"引用查询异常: {e}", durable=True)
            record = None
        if not record or record.get("status") != "normal":
            self._append_parsed_message(
                "系统", "原消息已撤回，无法引用。", "system", save=False, transient=True)
            return
        preview = (record.get("content") or "").strip()
        if len(preview) > 30:
            preview = preview[:30] + "…"
        self._quote = {"id": message_id, "sender": record.get("sender", ""), "preview": preview}
        self._quote_label.setText(f"↪ 回复 {record.get('sender', '')}：{preview}")
        self._quote_bar.show()

    def _clear_quote(self) -> None:
        """取消引用：清状态 + 隐藏引用条。"""
        self._quote = None
        if hasattr(self, "_quote_bar"):
            self._quote_bar.hide()

    # ── V14.0：撤回 / 删除 ────────────────────────

    def _on_recall_request(self, message_id: int) -> None:
        """撤回：仅 user 消息、created_at 起 3 分钟内、status=normal。"""
        try:
            record = self.conv_store.get_by_id(message_id)
        except Exception as e:
            _log(f"撤回查询异常: {e}", durable=True)
            return
        if not record or record.get("role") != "user" or record.get("status") != "normal":
            return
        # 3 分钟窗口（DB created_at 为权威时间戳，格式 YYYY-MM-DD HH:MM:SS）
        created = record.get("created_at", "")
        try:
            dt = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            _log(f"撤回：created_at 解析失败 {created!r}", durable=True)
            return
        if (datetime.now() - dt).total_seconds() > 180:
            self._append_parsed_message(
                "系统", "已超过 3 分钟，无法撤回。", "system", save=False, transient=True)
            return
        if QMessageBox.question(self, "撤回消息", "撤回这条消息？") == QMessageBox.Yes:
            # V14.0.1：连带同一次发送产生的助手回复（同轮占位），不连锁整段历史
            recalled_ids = self.conv_store.recall_turn(message_id)
            for mid in recalled_ids:
                self._mark_widget_recalled(mid)
            self._prune_bridge_history()
            _log(f"撤回: #{message_id}（连带同轮 {len(recalled_ids) - 1} 条助手）")

    def _on_delete_request(self, message_id: int) -> None:
        """删除：任意有 DB id 的消息（软删 status=deleted）。"""
        if QMessageBox.question(self, "删除消息", "删除这条消息？此操作不可恢复。") == QMessageBox.Yes:
            self.conv_store.update_status(message_id, "deleted")
            self._remove_widget_by_id(message_id)
            self._prune_bridge_history()
            _log(f"删除: #{message_id}")

    def _prune_bridge_history(self) -> None:
        """V14.0：删除/撤回后重建 bridge.history——已删/已撤内容不进后续 Prompt。"""
        restore = getattr(self.bot, "_restore_history_from_store", None)
        if restore is not None:
            try:
                restore()
            except Exception as e:
                _log(f"history 剪枝失败: {e}", durable=True)

    def _mark_widget_recalled(self, message_id: int) -> None:
        """按 DB id 找到聊天区 widget 并置为撤回占位。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and getattr(w, "message_id", None) == message_id:
                w.set_recalled()
                break

    def _remove_widget_by_id(self, message_id: int) -> None:
        """按 DB id 移除聊天区 widget（保留布局 stretch）。"""
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            w = item.widget() if item else None
            if w is not None and getattr(w, "message_id", None) == message_id:
                self.chat_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
                break
