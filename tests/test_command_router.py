"""V16.2.1 命令路由回归测试（结构守卫 + offscreen 行为）。

**背景**：`TwinChatApp` 曾同时存在两份 `_handle_command` —— 文件后部那份
（V16-M_D 导航栏精简版，只认 `/status` `/toggle`）在类体里**覆盖**了前面的完整路由，
于是 `/mansion /empire /late` 全部落进「未知指令」，V10.9.2 的富状态面板变成死代码。
这类「后定义静默覆盖」不报错、不告警、测试也照样绿——所以本文件用两条防线锁住：

1. **结构守卫**：扫描全项目 AST，同类内同名方法只允许一份（`@x.setter/@x.deleter`
   这类 property 访问器除外）；
2. **行为回归**：offscreen 主窗口真发指令，断言「状态已切换 + 不出现未知指令」，
   并覆盖真实入口 `_send_message()`（用户实际走的路径）。

全程不调用任何 API，全部本地。
"""

from __future__ import annotations

import ast
import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

SKIP_DIRS = {"venv", ".git", "dist", "build", "Temp", "__pycache__"}
# 唯一路由必须仍然认得的指令（含别名）；少一个即视为回归
ALL_COMMANDS = {"/status", "/mansion", "/empire", "/late",
                "/recover", "/toggle", "/llm", "/local"}


# ── 结构守卫 ─────────────────────────────────────────────

def _first_party_files():
    for path in sorted(PROJECT_ROOT.rglob("*.py")):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def _is_property_accessor(fn: ast.FunctionDef) -> bool:
    """`@x.setter` / `@x.deleter` / `@x.getter` —— 与 property 同名，属合法写法。"""
    for dec in fn.decorator_list:
        if isinstance(dec, ast.Attribute) and dec.attr in ("setter", "deleter", "getter"):
            return True
    return False


def _parse(path: pathlib.Path) -> ast.Module:
    """读源码并解析（`utf-8-sig` 吞掉部分历史文件开头自带的 BOM）。"""
    return ast.parse(path.read_text(encoding="utf-8-sig"))


def test_no_duplicate_method_definitions():
    """同类内重复方法定义 = 后者静默覆盖前者（前一份是死代码，且行为不可见地改变）。"""
    offenders = []
    for path in _first_party_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            seen: dict = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and not _is_property_accessor(item):
                    if item.name in seen:
                        offenders.append(
                            f"{path.relative_to(PROJECT_ROOT)}::{node.name}.{item.name} "
                            f"@{seen[item.name]} 与 @{item.lineno}")
                    seen[item.name] = item.lineno
    assert not offenders, (
        "同类内重复方法定义（后定义覆盖前定义，前一份变死代码）：\n  " + "\n  ".join(offenders)
    )


def _router_node() -> ast.FunctionDef:
    tree = _parse(PROJECT_ROOT / "gui.py")
    router = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_handle_command":
            assert router is None, "gui.py 里又出现了第二份 _handle_command"
            router = node
    assert router is not None, "gui.py 里找不到 _handle_command"
    return router


def test_command_router_covers_all_commands():
    """路由内出现的指令字面量必须仍覆盖全部指令（防静默删分支）。"""
    router = _router_node()
    literals = {
        c.value for c in ast.walk(router)
        if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith("/")
    }
    missing = ALL_COMMANDS - literals
    assert not missing, f"命令路由缺少字面量：{sorted(missing)}（现有：{sorted(literals)}）"
    has_unknown_branch = any(
        isinstance(c, ast.Constant) and isinstance(c.value, str) and "未知指令" in c.value
        for c in ast.walk(router)
    )
    assert has_unknown_branch, "未知指令兜底分支被删除"


# ── offscreen 行为回归 ────────────────────────────────────

@pytest.fixture(scope="module")
def qtapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def win(qtapp, tmp_path, monkeypatch):
    """隔离主窗口：临时存储 / 临时会话库 / 临时账本 / 临时日志（绝不碰真实 data/）。"""
    import gui
    from shared import life_ledger
    from shared.conversation_store import ConversationStore
    from shared.memory_store import MemoryStore

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used")
    monkeypatch.setenv("REZERO_LIFE_DB", str(tmp_path / "life.db"))
    life_ledger.reset_default()
    monkeypatch.setattr(gui, "MemoryStore", lambda: MemoryStore(root_dir=str(tmp_path)))
    monkeypatch.setattr(gui, "ConversationStore",
                        lambda: ConversationStore(db_path=str(tmp_path / "conv.db")))
    monkeypatch.setattr(gui.QMessageBox, "warning", lambda *a, **k: None)

    window = gui.TwinChatApp()
    try:
        yield window
    finally:
        window.close()
        life_ledger.reset_default()


def _bubbles(window) -> list:
    """聊天区全部 QLabel 文本（气泡 + 系统条 + 瞬时面板）。"""
    return [lbl.text() for lbl in window.chat_container.findChildren(QLabel)]


def test_arc_commands_switch_arc_without_unknown_message(win):
    from shared.state import StoryArc

    for cmd, expected, label, hint in (
        ("/empire", StoryArc.EMPIRE_ERA, "Arc II · 帝国篇", "帝国篇"),
        ("/mansion", StoryArc.MANSION_ERA, "Arc I · 罗兹瓦尔宅邸", "宅邸篇"),
        ("/late", StoryArc.LATE_ARC, "Arc III · 后期篇章", "后期篇章"),
    ):
        win._handle_command(cmd)
        assert win.engine.snapshot().arc is expected, f"{cmd} 未切换篇章"
        assert win._arc_label.text() == label, f"{cmd} 篇章标签未更新"
        texts = _bubbles(win)
        assert any(hint in t for t in texts), f"{cmd} 缺切换提示：{texts}"
        assert not any("未知指令" in t for t in texts), f"{cmd} 仍报未知指令：{texts}"
        # 大写/带空格也应可用（路由内统一小写化）
        win._handle_command("  /EMPIRE  ")
        assert win.engine.snapshot().arc is StoryArc.EMPIRE_ERA


def test_send_message_routes_slash_command(win):
    """真实入口路径：输入框敲指令 → _send_message → 唯一路由。"""
    from shared.state import StoryArc

    win.input_box.setPlainText("/empire")
    win._send_message()
    assert win.engine.snapshot().arc is StoryArc.EMPIRE_ERA, "输入框指令未生效"
    texts = _bubbles(win)
    assert not any("未知指令" in t for t in texts), texts


def test_recover_command_defaults_and_value(win):
    win._handle_command("/recover 0.5")
    assert win.engine.snapshot().recovery == pytest.approx(0.5)
    win._handle_command("/recover")           # 缺参数 → 默认 1.0
    assert win.engine.snapshot().recovery == pytest.approx(1.0)


def test_status_panel_is_rich_not_plain(win):
    """V10.9.2 富状态面板（曾被第二份路由覆盖成死代码）：含「残香」字段。"""
    win._handle_command("/status")
    texts = _bubbles(win)
    assert any("残香" in t for t in texts), f"/status 未走富面板：{texts}"
    assert any("篇章：" in t for t in texts), texts


def test_unknown_command_keeps_bounded_message(win):
    win._handle_command("/nope")
    texts = _bubbles(win)
    assert any("未知指令: /nope" in t for t in texts), texts
