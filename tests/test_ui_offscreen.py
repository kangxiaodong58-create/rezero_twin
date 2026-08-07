"""Re:Zero 双子系统 UI 离屏测试（无框架，直接运行）。

用法：
    python tests/test_ui_offscreen.py

覆盖 GUI 布局/行为断言（不显示窗口、不调用 LLM、不产生 API 费用）：
1. V12.1 回合间距五档（首条 / 同角色 / 换角色 / 阵营 / system 中性）
2. V12.1 streaming 时序（临时泡标记、正式泡跳过临时泡、顶替零跳变）
3. 上限裁剪（80 条）与 spacing 基线

说明：
- 内部强制 QT_QPA_PLATFORM=offscreen，任何环境直接运行即可
- 构造 TwinChatApp 会读取真实 data/（只读）；不写入 ConversationStore
- 与 tests/smoke_test.py（引擎纯逻辑）互补，互不依赖
"""

from __future__ import annotations

import os
import sys
from PySide6.QtWidgets import QLabel  # V14.1：搜索高亮测试取 bubble label

# ── 必须在 import PySide6 之前设置 ──
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

# 项目根目录加入搜索路径
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import traceback  # noqa: E402

import gui  # noqa: E402

# 离屏下防止 LLM 模式创建失败时的弹窗阻塞
gui.QMessageBox.warning = lambda *a, **k: None  # type: ignore[assignment]

from PySide6.QtWidgets import QApplication  # noqa: E402

SPACING = gui.SPACING


def _make_window() -> gui.TwinChatApp:
    """构造主窗口并清空历史（保留 stretch），使间距断言从空布局开始。"""
    app = QApplication.instance() or QApplication([])
    win = gui.TwinChatApp()
    win.show()
    while win.chat_layout.count() > 0:
        item = win.chat_layout.takeAt(0)
        if item.widget() is not None:
            item.widget().deleteLater()
    win.chat_layout.addStretch()
    return win


def _top_of(w) -> int:
    return w.layout().contentsMargins().top()


def test_turn_rhythm_five_levels_v121() -> None:
    """V12.1：五档间距 — 首条/阵营/同角色/换人/阵营/system 中性。"""
    win = _make_window()
    w_user = win._append_parsed_message("你", "你好", "user", save=False)
    assert _top_of(w_user) == SPACING['sm'], f"首条应 sm({SPACING['sm']})，实际 {_top_of(w_user)}"
    w_rem1 = win._append_parsed_message("蕾 姆", "欢迎回来", "rem", save=False)
    assert _top_of(w_rem1) == SPACING['lg'], f"user→rem 应 lg({SPACING['lg']})，实际 {_top_of(w_rem1)}"
    w_rem2 = win._append_parsed_message("蕾 姆", "今天也要加油", "rem", save=False)
    assert _top_of(w_rem2) == SPACING['xs'], f"rem→rem 应 xs({SPACING['xs']})，实际 {_top_of(w_rem2)}"
    w_ram = win._append_parsed_message("拉 姆", "哼", "ram", save=False)
    assert _top_of(w_ram) == SPACING['md'], f"rem→ram 应 md({SPACING['md']})，实际 {_top_of(w_ram)}"
    w_user2 = win._append_parsed_message("你", "辛苦了", "user", save=False)
    assert _top_of(w_user2) == SPACING['lg'], f"ram→user 应 lg({SPACING['lg']})，实际 {_top_of(w_user2)}"
    w_sys = win._append_parsed_message("系统", "场景转换", "system", save=False)
    assert _top_of(w_sys) == SPACING['sm'], f"user→system 应 sm({SPACING['sm']})，实际 {_top_of(w_sys)}"
    w_rem3 = win._append_parsed_message("蕾 姆", "继续", "rem", save=False)
    assert _top_of(w_rem3) == SPACING['sm'], f"system→rem 应 sm({SPACING['sm']})，实际 {_top_of(w_rem3)}"


def test_turn_rhythm_streaming_v121() -> None:
    """V12.1：streaming 时序 — 临时泡标记/跳过判定/顶替零跳变。"""
    win = _make_window()
    win._append_parsed_message("你", "再来一轮", "user", save=False)
    temp = win._insert_streaming_bubble("rem")
    assert temp.objectName() == "__streaming_temp__", f"临时泡标记错误：{temp.objectName()}"
    assert _top_of(temp) == SPACING['lg'], f"user→临时rem 应 lg({SPACING['lg']})，实际 {_top_of(temp)}"
    w_final = win._append_parsed_message("蕾 姆", "正式定稿", "rem", save=False)
    assert _top_of(w_final) == SPACING['lg'], f"正式泡应跳过临时泡→lg({SPACING['lg']})，实际 {_top_of(w_final)}"
    assert _top_of(w_final) == _top_of(temp), "正式泡与临时泡 top 应一致（顶替零跳变）"
    temp.setParent(None)
    temp.deleteLater()
    assert _top_of(w_final) == SPACING['lg'], "删临时泡后正式泡 top 不应变"
    t2 = win._insert_streaming_bubble("rem")
    assert _top_of(t2) == SPACING['xs'], f"正式rem→临时rem 应 xs({SPACING['xs']})，实际 {_top_of(t2)}"
    t3 = win._insert_streaming_bubble("ram")
    assert _top_of(t3) == SPACING['md'], f"临时rem→临时ram 应 md({SPACING['md']})，实际 {_top_of(t3)}"


def test_turn_rhythm_cap_and_spacing_v121() -> None:
    """V12.1：上限裁剪（≤80）后判定仍正确 + spacing 基线 xs。"""
    win = _make_window()
    for i in range(85):
        win._append_parsed_message("蕾 姆", f"批量 {i}", "rem", save=False)
    visible = win.chat_layout.count() - 1  # 去掉 stretch
    assert visible <= 80, f"裁剪后应 ≤80，实际 {visible}"
    w_after = win._append_parsed_message("拉 姆", "裁剪后", "ram", save=False)
    assert _top_of(w_after) == SPACING['md'], f"裁剪后 rem→ram 应 md({SPACING['md']})，实际 {_top_of(w_after)}"
    assert win.chat_layout.spacing() == SPACING['xs'], (
        f"chat_layout spacing 应为 xs({SPACING['xs']})，实际 {win.chat_layout.spacing()}"
    )


def test_cancel_with_empty_input_v1301() -> None:
    """V13.0.1：流式中空输入框点发送键必须触发取消（缺陷回归）。

    原缺陷：_send_message 先取文本、空输入即 return，挡住取消分支；
    发完消息后输入框已清空 → 点「取消」无反应。
    """
    win = _make_window()
    win._streaming_active = True
    win.send_btn.setText("取消")
    win.send_btn.setEnabled(True)
    win.input_box.clear()  # 发完消息后的典型状态
    win._send_message()
    assert win._streaming_active is False, "空输入点发送键应触发取消"
    assert win.send_btn.text() == "发送" and win.send_btn.isEnabled(), "取消后按钮应恢复「发送」"
    assert win.footer_label.text() == "已取消", "footer 应显示「已取消」"
    assert len(win._streaming_bubbles) == 0 and win._streaming_buffer == "", "临时泡/buffer 应清空"
    # 非流式空输入仍应安静 return（无副作用回归）
    win._streaming_active = False
    count_before = win.chat_layout.count()
    win._send_message()
    assert win.chat_layout.count() == count_before, "非流式空输入不应有副作用"


def test_recall_delete_failed_v140() -> None:
    """V14.0：撤回占位 / 撤回超时拒绝 / 删除移除 widget / 取消→failed。

    使用临时 DB 替换 win.conv_store，不写入正式 data/conversations.db。
    """
    import datetime as _dt
    import tempfile
    from PySide6.QtWidgets import QMessageBox as QMB

    win = _make_window()
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    win.conv_store = gui.ConversationStore(db_path=db_path)
    gui.QMessageBox.question = staticmethod(lambda *a, **k: QMB.StandardButton.Yes)

    # 1) 撤回：用户消息 → widget 占位 + DB recalled
    w = win._append_parsed_message("你", "要撤回的话", "user")
    assert w.message_id is not None, "save=True 应回填 message_id"
    win._on_recall_request(w.message_id)
    assert w._status == "recalled", "撤回后 widget 应为占位"
    assert win.conv_store.get_by_id(w.message_id)["status"] == "recalled", "DB 应为 recalled"

    # 2) 撤回超时（created_at 改 4 分钟前）→ 拒绝
    w2 = win._append_parsed_message("你", "超过三分钟的话", "user")
    old_ts = (_dt.datetime.now() - _dt.timedelta(minutes=4)).strftime("%Y-%m-%d %H:%M:%S")
    with win.conv_store._connect() as conn:
        conn.execute("UPDATE messages SET created_at=? WHERE id=?", (old_ts, w2.message_id))
        conn.commit()
    win._on_recall_request(w2.message_id)
    assert win.conv_store.get_by_id(w2.message_id)["status"] == "normal", "超时不应撤回"
    assert w2._status == "normal", "超时 widget 不应变占位"

    # 3) 删除：widget 从布局移除 + DB deleted
    w3 = win._append_parsed_message("蕾 姆", "要被删的话", "rem")
    win._on_delete_request(w3.message_id)
    assert win.conv_store.get_by_id(w3.message_id)["status"] == "deleted", "DB 应为 deleted"
    removed = True
    for i in range(win.chat_layout.count()):
        if win.chat_layout.itemAt(i).widget() is w3:
            removed = False
            break
    assert removed, "删除后 widget 应从主聊天移除"

    # 4) 取消 → 本轮用户句 failed（widget + DB）
    w4 = win._append_parsed_message("你", "然后取消的话", "user")
    win._pending_user_widget = w4
    win._cancel_streaming()
    assert win.conv_store.get_by_id(w4.message_id)["status"] == "failed", "取消后 DB 应为 failed"
    assert w4._status == "failed", "取消后 widget 应标记未送达"


def test_search_highlight_v141() -> None:
    """V14.1：命中词黄高亮——escape 防注入 / 多命中 / 空关键词 / clear 恢复。"""
    import tempfile

    # ── 纯函数层（highlight_plain_text）──
    h = gui.highlight_plain_text
    # 中文精确命中
    r = h("今天去野外散步", "野外")
    assert "<span" in r and "野外" in r, f"命中词应包 span: {r}"
    assert r.count("<span") == 1
    # 多命中全部标黄
    r2 = h("野外和野外", "野外")
    assert r2.count("<span") == 2, f"多命中应全部标黄: {r2}"
    # escape 防注入：HTML 标签原样转义，关键词仍可命中
    r3 = h("讲 <b>野外</b> 的事", "野外")
    assert "<b>" not in r3 and "&lt;b&gt;" in r3, f"HTML 应被转义: {r3}"
    assert r3.count("<span") == 1 and "&lt;/b&gt;" in r3
    # 空 keyword / 未命中 → 原样（escape 后）
    assert h("普通文本", "") == "普通文本"
    assert h("普通文本", "不存在") == "普通文本"

    # ── widget 级：高亮 → clear 往返 ──
    win = _make_window()
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    win.conv_store = gui.ConversationStore(db_path=db_path)
    w = win._append_parsed_message("蕾 姆", "今天去野外散步，野外很美", "rem")
    win.highlight_hits("野外")
    label = w._bubble.findChild(QLabel, "bubble_text")
    assert label is not None and "<span" in label.text(), f"高亮后 label 应含 span: {label.text()}"
    win.clear_all_highlights()
    assert "<span" not in label.text() and "野外" in label.text(), f"clear 应恢复原文: {label.text()}"
    assert not hasattr(w, "_search_hit_text"), "clear 后应删除原文留存"
    # recalled widget 不参与高亮（占位无原文）
    w2 = win._append_parsed_message("你", "要被撤回的高亮句", "user")
    w2.set_recalled()
    win.highlight_hits("高亮")
    label2 = w2._bubble.findChild(QLabel, "bubble_text")
    assert label2 is not None and "<span" not in label2.text(), "recalled 占位不应参与高亮"


def test_quote_reply_v142() -> None:
    """V14.2：引用条显示 / 已撤提示 / 取消 / 发送消费（临时 DB）。"""
    import tempfile

    win = _make_window()
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    win.conv_store = gui.ConversationStore(db_path=db_path)

    # 1) 引用 normal 消息 → 引用条显示 + _quote 设置
    w = win._append_parsed_message("蕾 姆", "这是可以被引用的内容", "rem")
    win._on_quote_request(w.message_id)
    assert win._quote is not None and win._quote["id"] == w.message_id, "引用应设置"
    assert win._quote_bar.isVisible(), "引用条应显示"
    assert "↪ 回复" in win._quote_label.text() and "被引用" in win._quote_label.text()

    # 2) 引用已撤消息 → 提示 + 不设置引用
    w2 = win._append_parsed_message("你", "将被撤回的内容", "user")
    win._on_recall_request(w2.message_id)  # 先撤回（question 已 patch Yes）
    before = win._quote
    win._on_quote_request(w2.message_id)
    assert win._quote is before, "已撤消息不应覆盖当前引用"

    # 3) × 取消 → 引用条隐藏 + 状态清空
    win._clear_quote()
    assert win._quote is None and not win._quote_bar.isVisible(), "取消后应清空并隐藏"

    # 4) 发送消费：quote → reply_to 透传 + 一次性清除
    w3 = win._append_parsed_message("蕾 姆", "第二句可引用的", "rem")
    win._on_quote_request(w3.message_id)
    captured = {}

    def fake_send(text, reply_to=None):
        captured["reply_to"] = reply_to

    win._send_llm_stream = fake_send
    win.input_box.setPlainText("回应这句")
    win._send_message()
    assert captured["reply_to"] == {"id": w3.message_id, "preview": "第二句可引用的"}, \
        f"应透传引用: {captured['reply_to']}"
    assert win._quote is None, "发送后引用应一次性清除"
    assert not win._quote_bar.isVisible(), "发送后引用条应隐藏"


def test_letter_dispatch_v143() -> None:
    """V14.3：GUI 接线——离线 3 天触发来信（渲染 + 落库 + 冷却状态）；同日再触发被拦。"""
    import tempfile
    import time as _time
    from datetime import datetime as _dt

    win = _make_window()  # REZERO_DISABLE_VIGNETTE=1 环境下构造（来信判定跳过，安全）
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(db_path)
    win.conv_store = gui.ConversationStore(db_path=db_path)

    # 模拟离线 3 天：改 world 内存状态（不落盘，零污染）
    win.world.last_interaction_ts = _time.time() - 3 * 86400
    win.world.last_period = "上午"
    win.world.last_letter_ts = 0.0
    win.world.last_letter_date = ""

    orig_flag = gui._VIGNETTE_DISABLED
    gui._VIGNETTE_DISABLED = False
    try:
        today = _dt.now().strftime("%Y-%m-%d")
        letter = win._maybe_dispatch_letter(today)
        assert letter is not None, "离线 3 天应触发来信"
        assert letter["messages"], "来信消息非空"
        # DB 落库（role=rem/ram，status normal）
        recent = win.conv_store.get_recent(limit=10)
        letter_roles = {r["role"] for r in recent if r["role"] in ("rem", "ram")}
        assert letter_roles, f"来信应落库: {recent}"
        # 冷却状态更新
        assert win.world.last_letter_date == today, "冷却日期应更新"
        # 同日再触发 → 被每日上限拦截
        letter2 = win._maybe_dispatch_letter(today)
        assert letter2 is None, "同日二次触发应被冷却拦截"
    finally:
        gui._VIGNETTE_DISABLED = orig_flag


def main() -> int:
    tests = [
        ("回合间距五档 V12.1", test_turn_rhythm_five_levels_v121),
        ("回合间距 streaming 时序 V12.1", test_turn_rhythm_streaming_v121),
        ("回合间距裁剪+基线 V12.1", test_turn_rhythm_cap_and_spacing_v121),
        ("空输入取消回归 V13.0.1", test_cancel_with_empty_input_v1301),
        ("撤回/删除/失败态 V14.0", test_recall_delete_failed_v140),
        ("搜索命中词黄高亮 V14.1", test_search_highlight_v141),
        ("引用回复 V14.2", test_quote_reply_v142),
        ("主动来信 GUI 接线 V14.3", test_letter_dispatch_v143),
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception:
            failed += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
