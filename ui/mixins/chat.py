"""聊天流（消息渲染 / 流式 / 发送 / 历史装载）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Qt
from PySide6.QtWidgets import QWidget

from design_tokens import SPACING
from runtime.forensic import record
from typing import Optional
from ui.logging_util import _log
from ui.text import _streaming_segments, parse_twin_segments
from ui.widgets_message import ChatMessageWidget, SystemLabelWidget
from ui.worker import LLMWorker


class ChatMixin:
    """聊天流（消息渲染 / 流式 / 发送 / 历史装载）。"""

    # ── V12.1 回合间距（Conversation Turn Rhythm）────────────────

    def _turn_top_margin(self, role: str) -> int:
        """V12.1：按「最近正式消息」的 role 计算本条 top margin（O(1) 回看）。

        跳过 streaming 临时泡（objectName=="__streaming_temp__"，最多回看 8 个），
        使正式泡顶替临时泡时间距一致（删临时泡零跳变）。
        判定顺序：首条→sm / 涉 system→sm / 同 speaker→xs / 涉 user→lg / 其余→md。
        全部 try/except，异常兜底 sm。
        """
        try:
            i = self.chat_layout.count() - 1  # SPEC-26 D6：stretch 已置首 ⇒ 末尾即最后一条
            steps = 0
            while i >= 0 and steps < 8:
                item = self.chat_layout.itemAt(i)
                w = item.widget() if item is not None else None
                if w is None:
                    break
                if w.objectName() == "__streaming_temp__":
                    i -= 1
                    steps += 1
                    continue
                prev_role = getattr(w, "role", "system")
                if prev_role == "system" or role == "system":
                    return SPACING['sm']
                if role == prev_role:
                    return SPACING['xs']
                if role == "user" or prev_role == "user":
                    return SPACING['lg']
                return SPACING['md']
            return SPACING['sm']  # 无正式上一条 / 回看越界
        except Exception:
            return SPACING['sm']

    def _apply_turn_rhythm(self, msg, role: str) -> None:
        """V12.1：按上一条 role 设置本条外层 margins（只动 top，不碰 Bubble 内部）。

        ChatMessageWidget 基线 (12,5,12,5)；SystemLabelWidget 基线 (16,4,16,4)；
        与各自构造处硬编码保持一致。
        """
        try:
            top = self._turn_top_margin(role)
            if isinstance(msg, ChatMessageWidget):
                msg.layout().setContentsMargins(12, top, 12, 5)
            else:
                msg.layout().setContentsMargins(16, top, 16, 4)
        except Exception:
            pass

    def _append_parsed_message(self, sender: str, text: str, role: str, save: bool = True, transient: bool = False, message_id: Optional[int] = None, force_center: bool = False, highlight: bool = False, variant: str = "system", animate: bool = True,
                    motion_delay_ms: int = 0) -> Optional[QWidget]:
        """添加消息 widget。超出上限时移除最早的。

        V10.9.0：system 角色走 SystemLabelWidget 轻标签，其余走 ChatMessageWidget。
        V10.9.2：transient=True 时系统标签自动消失 + 可点击关闭。
        V10.12：message_id 参数透传给 ChatMessageWidget（历史回放带 id）；
                save=True 时捕获 conv_store.append 返回值回填 widget.message_id。
        V11.9.1：force_center 透传给 SystemLabelWidget（日更问候多行居中）。
        V11.10.0：highlight 透传给 ChatMessageWidget（高光变体）。
        V11.12：variant 透传给 SystemLabelWidget（vignette 幕间卡）；
                返回值改为创建的 widget（供占位引用删除等场景，既有调用方不受影响）。
        V12.0：animate 参数 — 正式角色泡（rem/ram/user）200ms opacity 轻入场；
               system 标签恒无入场；历史批量回放传 animate=False 跳过动画。
        """
        if role == "system":
            msg = SystemLabelWidget(text, transient=transient, force_center=force_center,
                                    variant=variant, message_id=message_id)
        else:
            msg = ChatMessageWidget(sender, text, role=role, message_id=message_id,
                                    variant="highlight" if highlight else "normal")
        # V14.0：右键菜单信号接线（仅带 DB id 的消息；瞬态标签无 id 不接线）
        if hasattr(msg, "recall_requested"):
            msg.recall_requested.connect(self._on_recall_request)
        if hasattr(msg, "delete_requested"):
            msg.delete_requested.connect(self._on_delete_request)
        if hasattr(msg, "quote_requested"):
            msg.quote_requested.connect(self._on_quote_request)
        # V12.1：回合间距 — 插入前计算（此时 layout 最后一条才是真正的上一条）
        self._apply_turn_rhythm(msg, role)

        insert_index = self.chat_layout.count()   # SPEC-26 D6：stretch 在首部 ⇒ 追加到末尾
        self.chat_layout.insertWidget(insert_index, msg)

        # V12.0：正式角色泡轻入场（system 标签无入场；历史回放由调用方传 animate=False）
        if animate and role != "system":
            self._play_entrance_animation(msg, delay_ms=motion_delay_ms)

        # 限制可见 widget 数量，防止内存泄漏
        visible = self.chat_layout.count() - 1  # 减去首部 stretch（SPEC-26 D6）
        while visible > self.MAX_VISIBLE_WIDGETS:
            item = self.chat_layout.itemAt(1)   # SPEC-26 D6：跳过首部 stretch
            if item and item.widget():
                w = item.widget()
                self.chat_layout.removeWidget(w)
                w.setParent(None)
                w.deleteLater()
                visible -= 1
            else:
                break

        if save:
            new_id = self.conv_store.append(role, sender, text)
            if hasattr(msg, "message_id"):
                msg.message_id = new_id  # V10.12：回填 DB id 供定位
        QTimer.singleShot(50, self._scroll_to_bottom)
        return msg

    def _insert_streaming_bubble(self, role: str) -> ChatMessageWidget:
        """插入一个空流式气泡，后续逐 token 填充。

        V11.10.1：使用 variant="streaming" 弱变体，视觉明显弱于正式泡。
        V11.11：临时泡全部 save=False，不写 ConversationStore。
        """
        sender = "蕾 姆" if role == "rem" else ("拉 姆" if role == "ram" else role)
        msg = ChatMessageWidget(sender, "", role=role, variant="streaming")
        msg.setObjectName("__streaming_temp__")  # V12.1：临时泡标记（回合间距跳过用）
        self._apply_turn_rhythm(msg, role)  # V12.1：插入前计算（上一条 = 布局当前最后一条）
        insert_index = self.chat_layout.count()   # SPEC-26 D6
        self.chat_layout.insertWidget(insert_index, msg)
        QTimer.singleShot(30, self._scroll_to_bottom)
        return msg

    def _clear_streaming_bubbles(self) -> None:
        """V11.11：统一清理所有流式临时泡（finished/error/重入共用）。"""
        for bubble in self._streaming_bubbles:
            try:
                bubble.setParent(None)
                bubble.deleteLater()
            except Exception:
                pass
        self._streaming_bubbles = []
        self._set_speaking_panels(None)  # V12.0：说话态复位（finished/error/重入共用）

    def _scroll_to_bottom(self) -> None:
        vsb = self.scroll.verticalScrollBar()
        vsb.setValue(vsb.maximum())

    # ── 发送消息 ────────────────────────────

    def _send_message(self) -> None:
        # V13.0.1：取消优先——流式中即使输入框为空，点发送键也应取消
        # （原「先取 text → 空输入 return」会挡住取消入口：发完消息输入框已清空）
        if self._streaming_active:
            self._cancel_streaming()
            return
        text = self.input_box.toPlainText().strip()
        if not text:
            return
        _log(f"发送: {text[:40]}")

        self.input_box.clear()
        # V14.0：记录本轮用户句 widget（取消时标记 failed）
        self._pending_user_widget = self._append_parsed_message("你", text, "user")

        # 命令检测（V16.2.1：全部指令收敛到唯一路由 _handle_command）
        if text.startswith("/"):
            self._handle_command(text)
            return

        # 有效对话：刷新世界状态的最后互动时间戳（v10.4）
        if hasattr(self, 'world'):
            self.world.mark_interaction()

        self.footer_label.setText("双子思考中…")
        self.send_btn.setText("取消")  # V13.0：流式中发送键变取消
        self.send_btn.setEnabled(True)
        self._streaming_active = True
        self._set_breathing(False)  # V12.0：思考中暂停状态栏呼吸

        # V14.2：引用——发送时校验被引用消息状态（期间可能被删/撤）
        reply_to = None
        if self._quote is not None:
            try:
                qrec = self.conv_store.get_by_id(self._quote["id"])
            except Exception:
                qrec = None
            if qrec is None or qrec.get("status") != "normal":
                self._append_parsed_message(
                    "系统", "原消息已撤回，引用已取消。", "system", save=False, transient=True)
            else:
                reply_to = {"id": self._quote["id"], "preview": self._quote["preview"]}
            self._clear_quote()  # 引用一次性消费（无论成功与否）

        if hasattr(self.bot, 'chat_stream'):
            self._send_llm_stream(text, reply_to=reply_to)
        else:
            QTimer.singleShot(50, lambda: self._send_sync(text))

    def _send_sync(self, text: str) -> None:
        """同步发送（LLM 同步模式；本地模板模式已下线——A3 收口）。"""
        try:
            reply = self.bot.chat(text)
            _log(f"回复: {reply[:60]}")
        except Exception as e:
            # V11.10.0：错误不走解析器，直接 system 消息
            self._append_parsed_message("系统", f"出错了：{e}", "system")
            self._finish_reply()
            _log(f"异常: {e}", durable=True)
            return

        # V11.10.0：检查场景高光标记
        highlight = hasattr(self.bot, '_active_scene_id') and bool(self.bot._active_scene_id)
        # V13.0：兜底 View-Only（不写 ConversationStore）
        is_fallback = getattr(self.bot, "_last_chat_fallback", False)
        self._parse_twin_reply(reply, highlight=highlight, save=not is_fallback)
        if hasattr(self.bot, '_active_scene_id'):
            self.bot._active_scene_id = None
        self._finish_reply()

    def _cancel_streaming(self) -> None:
        """V13.0：用户取消当前流式回复。V14.0：本轮用户句标记未送达（failed）。"""
        _log("用户取消流式回复", durable=True)
        record("UI_EVENT", component="gui", payload_summary="stream_cancelled")  # Forensic M4
        self._teardown_llm_thread()
        self._streaming_active = False
        pending = getattr(self, "_pending_user_widget", None)
        if pending is not None and pending.message_id:
            try:
                self.conv_store.update_status(pending.message_id, "failed")
                pending.set_failed()
                _log(f"取消：用户句 #{pending.message_id} 标记 failed")
            except Exception as e:
                _log(f"失败态标记异常: {e}", durable=True)
        self._pending_user_widget = None
        self._set_breathing(True)  # 恢复状态栏呼吸
        self._set_speaking_panels(None)
        self._update_panels()
        self._update_status_bar()
        self.footer_label.setText("已取消")
        self.send_btn.setText("发送")
        self.send_btn.setEnabled(True)
        self.input_box.setFocus()

    def _send_llm_stream(self, text: str, reply_to: Optional[dict] = None) -> None:
        """LLM 流式发送（异步线程，安全的线程管理）。reply_to: V14.2 引用。"""
        # V13.0：统一走 _teardown_llm_thread 清理旧线程（原 quit/wait/terminate 手写块）
        self._teardown_llm_thread()

        self._streaming_buffer = ""
        # V11.11：重入时清理所有旧临时泡，防止孤儿残留
        self._clear_streaming_bubbles()

        self._llm_thread = QThread()
        self._llm_worker = LLMWorker(self.bot, text, stream=True, reply_to=reply_to)
        self._llm_worker.moveToThread(self._llm_thread)
        self._llm_thread.started.connect(self._llm_worker.run)
        self._llm_worker.stream_token.connect(self._on_stream_token, Qt.QueuedConnection)
        self._llm_worker.finished.connect(self._on_stream_finished, Qt.QueuedConnection)
        self._llm_worker.error.connect(self._on_stream_error, Qt.QueuedConnection)
        self._llm_thread.finished.connect(self._llm_thread.deleteLater)
        self._llm_thread.start()

    def _on_stream_token(self, token: str) -> None:
        self._streaming_buffer += token
        # V11.11：流式分段，按说话人切泡
        segments = _streaming_segments(self._streaming_buffer)
        if not segments:
            return
        # V12.0：当前说话人 = 最后一段 speaker，变化时才点亮对应侧（幂等）
        current = segments[-1][0]
        if current != self._current_speaker:
            self._set_speaking_panels(current)
        # 段数多于当前泡数 → 新增泡
        while len(self._streaming_bubbles) < len(segments):
            speaker, _ = segments[len(self._streaming_bubbles)]
            bubble = self._insert_streaming_bubble(speaker)
            self._streaming_bubbles.append(bubble)
        # 更新各泡文本（纯文本，不含标签）
        for i, (speaker, text) in enumerate(segments):
            if i < len(self._streaming_bubbles):
                self._streaming_bubbles[i].update_text(text)
        QTimer.singleShot(10, self._scroll_to_bottom)

    def _on_stream_finished(self, _final: str = "") -> None:
        # V13.0：校验失败回传——丢弃未通过校验的全文，展示 View-Only 回避文案
        stream_ok = getattr(self.bot, "_last_stream_ok", None)
        if stream_ok is False:
            _log("流式校验失败：丢弃未校验全文，展示 View-Only 回避文案", durable=True)
            self._clear_streaming_bubbles()
            self._streaming_buffer = ""
            fallback_text = (
                getattr(self.bot, "_stream_fallback_text", "")
                or '【蕾姆】: "……这个话题，蕾姆想先放一放。您愿意说点别的吗？"'
            )
            self._parse_twin_reply(fallback_text, highlight=False, save=False)
            self._finish_reply()
            _log("流式校验失败：已展示回避文案", durable=True)
            return
        buffered = self._streaming_buffer or _final
        # V11.10.1：先解析插入正式泡，再删临时泡（减少空白帧跳变）
        if buffered.strip():
            # V11.10.0：检查场景高光标记
            highlight = hasattr(self.bot, '_active_scene_id') and bool(self.bot._active_scene_id)
            self._parse_twin_reply(buffered, highlight=highlight)
            if hasattr(self.bot, '_active_scene_id'):
                self.bot._active_scene_id = None
        # V11.11：移除所有临时预览泡（正式泡已在上方插入）
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""
        self._finish_reply()
        _log("流式完成")

    def _on_stream_error(self, err: str) -> None:
        self._streaming_active = False
        # V11.11：清理所有临时泡，防止孤儿残留
        self._clear_streaming_bubbles()
        self._streaming_buffer = ""
        self._append_parsed_message("系统", f"出错了：{err}", "system")
        self._finish_reply()
        _log(f"流式错误: {err}", durable=True)

    def _parse_twin_reply(self, reply: str, highlight: bool = False, save: bool = True) -> None:
        """V11.10.0：解析双子回复，缓冲+flush 模型，speaker 继承。

        - 【蕾姆】/【拉姆】→ 切换 speaker，开启新气泡段
        - 无前缀行 → 并入当前 speaker 段（默认 rem）
        - 【系统】→ 提取内容后按无前缀行处理（继承或默认 rem）
        - 禁止 LLM 台词降级 system
        - highlight=True 时标记最后一个 rem 段为高光变体
        - V13.0：save 参数——View-Only 兜底文案传 save=False，不写 ConversationStore
        """
        segments = parse_twin_segments(reply)

        # 找最后一个 rem 段索引（用于 highlight）
        last_rem_idx = -1
        for i in range(len(segments) - 1, -1, -1):
            if segments[i][0] == "rem":
                last_rem_idx = i
                break

        for i, (speaker, text) in enumerate(segments):
            if speaker == "rem":
                self._append_parsed_message("蕾 姆", text, "rem",
                                            highlight=(highlight and i == last_rem_idx),
                                            save=save)
            else:
                self._append_parsed_message("拉 姆", text, "ram", save=save)

    def _finish_reply(self) -> None:
        self._streaming_active = False
        self._pending_user_widget = None  # V14.0：成功完成——本轮用户句不标记 failed
        self._set_speaking_panels(None)  # V12.0：兜底复位说话态（幂等，未亮时不做事）
        self._set_breathing(True)  # V12.0：完成后恢复状态栏呼吸
        self._save_state()
        self._update_panels()
        self._update_status_bar()
        self.footer_label.setText("就绪")
        self.send_btn.setText("发送")  # V13.0：恢复发送态
        self.send_btn.setEnabled(True)
        self.input_box.setFocus()

    # ── 历史加载 ────────────────────────────

    def _load_history(self) -> None:
        recent = self.conv_store.get_recent(limit=30)
        _log(f"_load_history: {len(recent)} 条")
        shown = 0
        for item in recent:
            role = item["role"]
            text = item["content"]
            sender = item["sender"]
            msg_id = item.get("id")  # V10.12：透传 DB id 供定位
            if not text:
                continue
            # V16-M_B：历史回放级联——前 8 条 30ms 错落入場，其后同时出现（宪法 §一.3）
            import motion as _motion_mod
            delays = _motion_mod.stagger_delays(len(recent))
            w = self._append_parsed_message(sender, text, role, save=False, message_id=msg_id,
                                            animate=True, motion_delay_ms=delays[min(shown, len(delays) - 1)])
            # V14.0：软状态渲染——recalled 占位 / failed 未送达标记（deleted 已被 get_recent 过滤）
            status = item.get("status", "normal")
            if status == "recalled" and w is not None:
                w.set_recalled()
            elif status == "failed" and w is not None:
                w.set_failed()
            shown += 1
        _log(f"历史显示: {shown} 条")
        self.clear_all_highlights()  # V14.1：历史重载后清除可能残留的黄高亮
        if shown == 0:
            # V11.6.5: 有上次摘要时不显示欢迎语（续聊卡接管，避免双卡叠放）
            last_summary = None
            try:
                last_summary = self.conv_store.get_last_session_summary()
            except Exception:
                pass
            if not last_summary:
                self._append_parsed_message(
                    "系统",
                    "❄ 欢迎来到 Re:Zero 双子系统。\n"
                    "左侧是蕾姆面板，右侧是拉姆面板。\n"
                    "输入消息开始对话，或使用底部快捷按钮。",
                    "system", save=False,
                )
