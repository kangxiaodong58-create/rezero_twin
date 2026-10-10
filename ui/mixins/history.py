"""历史 / 回忆之书 / 定位（SPEC-23 方法随迁）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

from PySide6.QtCore import QTimer

from ui import theme
from ui.flags import _HISTORY_DISABLED
from ui.history import HistoryOverlay, LOCATE_FLASH_MS
from ui.logging_util import _log
from ui.widgets_message import ChatMessageWidget


class HistoryMixin:
    """历史 / 回忆之书 / 定位（SPEC-23 方法随迁）。"""

    # ── 历史浮层（V10.10） ───────────────────

    def _open_history(self) -> None:
        """懒创建并打开历史浮层。"""
        if _HISTORY_DISABLED:
            _log("历史浮层已通过 REZERO_DISABLE_HISTORY 禁用")
            return
        if self._history_overlay is None:
            self._history_overlay = HistoryOverlay(self.conv_store, parent=self)
            self._history_overlay.closed.connect(self._close_history)
            self._history_overlay.locate_requested.connect(self._locate_message)  # V10.12
        # 跟随窗口尺寸
        self._history_overlay.setGeometry(self.rect())
        # 刷新数据（每次打开都拉最新）
        self._history_overlay.load_recent()
        self._history_overlay.show()
        self._history_overlay.raise_()
        self._history_overlay.setFocus()
        _log("历史浮层已打开")

    # V16.2.1：此处的第二份 `_handle_command`（V16-M_D 导航栏精简版）已删除。
    # 它定义在类体后部 → 覆盖前面那份完整路由，导致 /mansion /empire /late
    # 全部落入「未知指令」。命令路由现只有 gui.py 上部那一份（唯一真源）。

    def _open_memory_book(self) -> None:
        """V15.0-M3：懒创建并打开回忆之书浮层（独立模块 memory_book.py）。"""
        try:
            import memory_book
            if getattr(self, "_memory_book_overlay", None) is None:
                self._memory_book_overlay = memory_book.MemoryBookOverlay(
                    parent=self, conv_store=self.conv_store)
            self._memory_book_overlay._reload()  # 每次打开拉最新（账本/相册轻量）
            self._memory_book_overlay.setGeometry(self.rect())
            self._memory_book_overlay.show()
            self._memory_book_overlay.raise_()
            self._memory_book_overlay.setFocus()
            _log("回忆之书已打开")
        except Exception as e:
            _log(f"回忆之书打开失败: {e}", durable=True)

    def _close_history(self) -> None:
        """关闭历史浮层。"""
        if self._history_overlay:
            self._history_overlay.hide()
            self.clear_all_highlights()  # V14.1：关闭回忆浮层 → 清除黄高亮
            self.input_box.setFocus()
            _log("历史浮层已关闭")

    # ── V10.12：历史条目定位 ───────────────────

    def _locate_message(self, message_id: int, keyword: str = "") -> None:
        """根据 message_id 定位主聊天中的消息 widget。

        成功：关闭浮层 → 滚动到目标 → 短暂高亮（底色 + 可选句级命中标记）→ 恢复
        失败：关闭浮层 → transient 提示（不污染主聊天流）
        keyword：当前搜索词（SPEC-20260922-23 F23-1，浮层 relay 携带；空则只闪光不标句）
        """
        # 1. 关闭浮层
        if self._history_overlay:
            self._history_overlay.hide()

        # message_id 无效（系统消息等）
        if not message_id:
            self._append_parsed_message(
                "系统", "📍 该消息不支持定位。", "system", save=False, transient=True
            )
            return

        # 2. 遍历 chat_layout 查找匹配 message_id 的 widget
        target = None
        for i in range(self.chat_layout.count()):
            item = self.chat_layout.itemAt(i)
            if not item or not item.widget():
                continue
            w = item.widget()
            if isinstance(w, ChatMessageWidget) and getattr(w, "message_id", None) == message_id:
                target = w
                break

        # 3. 成功：滚动 + 高亮（色彩定档见 design_tokens.locate_highlight）
        if target is not None:
            self._scroll_to_widget(target)
            self._highlight_widget(target, keyword=keyword)
            self.input_box.setFocus()
            return

        # 4. 失败：从 DB 取内容摘要，transient 提示
        summary = ""
        try:
            record = self.conv_store.get_by_id(message_id)
            if record:
                content = record.get("content", "")
                summary = (content[:60] + "…") if len(content) > 60 else content
        except Exception as e:
            _log(f"定位降级查询异常: {e}", durable=True)

        tip = "📍 该消息不在当前可见范围（可能已随对话滚动移出）。"
        if summary:
            tip += f"内容摘要：{summary}"
        self._append_parsed_message("系统", tip, "system", save=False, transient=True)

    def _highlight_widget(self, widget, keyword: str = "") -> None:
        """短暂高亮目标消息**气泡本体**（暖黄底色 + 可选句级命中标记），LOCATE_FLASH_MS 后恢复。

        SPEC-23 修订（用户真机反馈：只标气泡，角色名/头像不动）：
        把闪光规则**追加**到气泡 label 自己的样式表末尾（同表同优先级 ⇒ 后写的赢），
        原样式存 `widget._locate_orig_style` 供恢复；拿不到气泡时退回容器级。
        """
        try:
            label = self._bubble_text_label(widget)
            target = label if label is not None else widget
            _hl = theme.locate_highlight()   # SPEC-32 F2：返回空串（定位不做视觉突出）⇒ 整链 no-op
            if _hl:
                if not hasattr(widget, "_locate_orig_style"):
                    widget._locate_orig_style = target.styleSheet()
                target.setStyleSheet(target.styleSheet() + "\n" + _hl)
            self._mark_locate_hit(widget, keyword)
            QTimer.singleShot(LOCATE_FLASH_MS, lambda: self._clear_locate_marks(widget))
        except Exception as e:
            _log(f"高亮异常: {e}", durable=True)

    def _clear_locate_marks(self, widget) -> None:
        """恢复定位标记（气泡底色 + 句级标记）。幂等；widget 已销毁时静默返回。"""
        try:
            label = self._bubble_text_label(widget)
        except RuntimeError:
            return  # C++ 对象已销毁（消息在闪光窗口内被删除）
        try:
            orig_style = getattr(widget, "_locate_orig_style", None)
            if label is not None and orig_style is not None:
                label.setStyleSheet(orig_style)
            if hasattr(widget, "_locate_orig_style"):
                del widget._locate_orig_style
        except RuntimeError:
            return
        except Exception as e:
            _log(f"定位底色恢复异常: {e}")
        try:
            orig = getattr(widget, "_locate_hit_text", None)
            if orig is not None:
                if label is not None:
                    label.setText(orig)
                del widget._locate_hit_text
        except Exception as e:
            _log(f"句级标记恢复异常: {e}")
