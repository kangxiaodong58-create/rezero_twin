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


def main() -> int:
    tests = [
        ("回合间距五档 V12.1", test_turn_rhythm_five_levels_v121),
        ("回合间距 streaming 时序 V12.1", test_turn_rhythm_streaming_v121),
        ("回合间距裁剪+基线 V12.1", test_turn_rhythm_cap_and_spacing_v121),
        ("空输入取消回归 V13.0.1", test_cancel_with_empty_input_v1301),
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
