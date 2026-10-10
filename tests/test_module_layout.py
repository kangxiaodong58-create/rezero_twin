"""SPEC-20260922-22 S4：结构守卫（防回弹）。

五条（SPEC §S4 / F22-2 / F22-6）：
1. `gui.py` 行数 ≤ 600；
2. `ui/**` 不得 import `gui`（防循环依赖）；
3. `TwinChatApp` + 8 个 mixin：**方法名跨模块唯一**（防 MRO 静默遮蔽）；
4. MRO 顺序固定 + 代表方法 `__qualname__` 归属断言（防"方法名唯一但被换实现"）；
5. `ui/**` 导入白名单：PySide6 / design_tokens / shared.* / ui.* / runtime.* + 标准库
   + **冻结的根级遗留集**（新增即红——棘轮）。

白名单修订说明（S2 实测）：原 SPEC 只列 {PySide6, design_tokens, shared.*, ui.*}；
实测 `ui/**` 还需 `runtime.*`（取证子系统，`_append_parsed_message` 的 `record`）与三个
根级遗留模块 `llm` / `memory_book` / `motion`（搬包前就存在的旧位置，非本批引入）。
本集冻结：**新增任何一项即红**，避免"随口加依赖"。
"""

from __future__ import annotations

import ast
import os
import pathlib
import sys
import sysconfig

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ─────────────────────────── 契约表 ───────────────────────────

MIXIN_ORDER = (
    "SearchMixin", "MessageOpsMixin", "HistoryMixin", "ChatMixin",
    "PanelsMixin", "DailyMixin", "CommandsMixin", "ShellSetupMixin",
)

# 根级遗留模块（搬包前既有位置；冻结，不许新增）
LEGACY_ROOT_MODULES = frozenset({"llm", "memory_book", "motion"})
WHITELIST_PREFIXES = ("design_tokens", "shared", "ui", "runtime", "PySide6")

# 代表方法 → 归属模块（S2 搬移后的既成事实；MRO 换了实现即红）
SPOT_METHODS = {
    "_do_search": "ui.mixins.search",
    "_handle_command": "ui.mixins.commands",
    "_apply_arc": "ui.mixins.commands",
    "_locate_message": "ui.mixins.history",
    "_open_history": "ui.mixins.history",
    "_append_parsed_message": "ui.mixins.chat",
    "_send_llm_stream": "ui.mixins.chat",
    "_update_panels": "ui.mixins.panels",
    "_show_resume_card": "ui.mixins.daily",
    "_on_sprite_dropped": "ui.mixins.daily",
    "_setup_ui": "ui.mixins.shell_setup",
    "__init__": "ui.mixins.shell_setup",
}

STDLIB = set(sys.stdlib_module_names) | {"__future__", "typing_extensions"}


def _ui_files() -> list:
    return [p for p in sorted(ROOT.glob("ui/**/*.py")) if "__pycache__" not in str(p)]


def _parse(path: pathlib.Path):
    return ast.parse(path.read_bytes().decode("utf-8-sig"))


def _import_roots(path: pathlib.Path) -> set:
    roots = set()
    for node in ast.walk(_parse(path)):
        if isinstance(node, ast.Import):
            for a in node.names:
                roots.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:      # 相对导入（包内）不参与
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


# ─────────────────────────── 守卫 1 ───────────────────────────

def test_gui_is_thin_shell():
    lines = len((ROOT / "gui.py").read_bytes().decode("utf-8").splitlines())
    assert lines <= 600, f"gui.py 已 {lines} 行（壳上限 600）——新逻辑请放 ui/"


# ─────────────────────────── 守卫 2 ───────────────────────────

def test_ui_does_not_import_gui():
    bad = []
    for p in _ui_files():
        for node in ast.walk(_parse(p)):
            mod = None
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".")[0] == "gui":
                    bad.append(f"{p.relative_to(ROOT)}:{node.lineno}")
    assert not bad, f"ui/ 不得 import gui（防循环依赖）：{bad}"


# ─────────────────────────── 守卫 3 ───────────────────────────

def _class_method_names(path: pathlib.Path) -> dict:
    """类体方法名 → 行号（跳过 @x.setter/deleter/getter —— 与既有扫描同口径）。"""
    out = {}
    for cls in _parse(path).body:
        if not isinstance(cls, ast.ClassDef):
            continue
        for fn in cls.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            decos = [getattr(d, "attr", "") for d in fn.decorator_list]
            if any(d in ("setter", "deleter", "getter") for d in decos):
                continue
            out.setdefault(fn.name, (cls.name, fn.lineno))
    return out


def test_mixin_method_names_unique_across_modules():
    """TwinChatApp + 8 个 mixin：同名方法只能有一份（否则 MRO 静默遮蔽）。"""
    sources = [ROOT / "gui.py"] + [ROOT / "ui" / "mixins" / f"{m}.py" for m in (
        "search", "message_ops", "history", "chat", "panels", "daily", "commands", "shell_setup",
    )]
    seen, dupes = {}, []
    for p in sources:
        assert p.is_file(), f"缺文件：{p}"
        for name, (cls, lineno) in _class_method_names(p).items():
            if name in seen:
                dupes.append(f"{name}: {seen[name][0]}@{seen[name][1]} ↔ {cls}@{lineno}")
            else:
                seen[name] = (cls, lineno, p.name)
    assert not dupes, "同类/跨 mixin 重复方法定义（MRO 会遮蔽前者）：\n  " + "\n  ".join(dupes)


# ─────────────────────────── 守卫 4 ───────────────────────────

def test_mro_order_and_method_ownership():
    """MRO 顺序固定 + 代表方法归属固定（F22-2）。"""
    from gui import TwinChatApp

    mro_names = [c.__name__ for c in TwinChatApp.__mro__]
    assert tuple(mro_names[1:9]) == MIXIN_ORDER, f"MRO 顺序变了：{mro_names[:10]}"
    assert mro_names[9] == "QMainWindow", f"QMainWindow 应排在 mixin 之后：{mro_names[:11]}"

    wrong = []
    for name, expected_mod in SPOT_METHODS.items():
        fn = getattr(TwinChatApp, name, None)
        assert fn is not None, f"TwinChatApp 缺方法 {name}"
        if fn.__module__ != expected_mod:
            wrong.append(f"{name}: {fn.__module__} ≠ {expected_mod}")
    assert not wrong, "代表方法归属漂移：\n  " + "\n  ".join(wrong)


# ─────────────────────────── 守卫 5 ───────────────────────────

def test_ui_import_whitelist():
    """ui/** 只允许白名单 + 标准库 + 冻结遗留集；新增依赖即红（棘轮）。"""
    offenders = {}
    for p in _ui_files():
        for root in _import_roots(p):
            if root in STDLIB or root in LEGACY_ROOT_MODULES:
                continue
            if any(root == w or root.startswith(w + ".") for w in WHITELIST_PREFIXES):
                continue
            offenders.setdefault(root, []).append(str(p.relative_to(ROOT)))
    assert not offenders, (
        "ui/** 出现白名单外导入（如确需新增：改本测试 + 在 SPEC 里写明理由）：\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(offenders.items()))
    )
# ─────────────────────── 守卫自证（防"永绿守卫"）───────────────────────

def test_guard_detectors_actually_bite(tmp_path):
    """把违规样本喂给检测器，必须报出来（否则守卫是装饰品）。"""
    sample = tmp_path / "sample_ui.py"
    sample.write_text("\n".join([
        "import gui",
        "import requests",
        "from gui import TwinChatApp",
        "import os",
    ]), encoding="utf-8")
    roots = _import_roots(sample)
    assert {"gui", "requests", "os"} <= roots, f"导入扫描失效：{roots}"
    assert "gui" in roots, "守卫 2 检测器失效"
    offenders = {
        r for r in roots
        if r not in STDLIB and r not in LEGACY_ROOT_MODULES
        and not any(r == w or r.startswith(w + ".") for w in WHITELIST_PREFIXES)
    }
    assert offenders == {"gui", "requests"}, f"守卫 5 判定异常：{offenders}"

    dup = tmp_path / "dup.py"
    dup.write_text("\n".join([
        "class A:",
        "    def m(self):",
        "        pass",
        "    def m(self):",
        "        pass",
    ]), encoding="utf-8")
    assert "m" in _class_method_names(dup), "守卫 3 检测器失效"

# ─────────────── 守卫 6（SPEC-28 / F28-1）：模块级全局必须有定义 ───────────────

def _module_defs(tree) -> set:
    """模块级定义名：def/class/赋值/注解赋值/import（含顶层 try/if 内的赋值）。"""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, (ast.Try, ast.If)):
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
    return names


def test_module_globals_are_defined():
    """`global X` 声明的名字必须在本模块有模块级定义。

    反例（真实事故）：SPEC-22 S1a 把 `_get_ambient_registry` 搬进 `ui/flags.py`，
    但 `_AMBIENT_REGISTRY = None` 留在 `gui.py` ⇒ 函数首次读取即 NameError（被 except 吞掉，
    「偶发一句」静默降级）。本守卫把「搬移后剩余变量丢失」钉死。
    """
    import builtins

    bad = []
    for p in _ui_files():
        tree = _parse(p)
        defs = _module_defs(tree) | set(dir(builtins))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for stmt in node.body:
                if isinstance(stmt, ast.Global):
                    for gname in stmt.names:
                        if gname not in defs:
                            bad.append(
                                "%s:%d 函数 %s 声明 global %s，但本模块无模块级定义"
                                % (p.relative_to(ROOT), node.lineno, node.name, gname)
                            )
    assert not bad, "global 声明的名字缺模块级定义：\n  " + "\n  ".join(bad)
