"""SPEC-20260922-19（B7）：搜索单一入口 `SearchService` 的判据测试。

判据对照 SPEC §测试方式：
1. **等价判据**：同 query + 同 limit → 结果集与顺序逐条相同（两处 UI 上限各自取用时一致）；
2. 空 query / 纯空白 → []；store 抛异常 → []（兜底）；
3. FTS 特殊字符 query 不炸；
4. `format_preview` 边界（≤60 不加省略号 / >60 截断加「…」）；
5. **结构守卫**（F19-1 口径）：UI 层文件禁止直连 `conv_store.search(`——只扫 UI 层，
   排除 `tests/**` 与 `shared/search_service.py` 自身（否则测试替身会误报）。
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from shared.conversation_store import ConversationStore
from shared.search_service import DEFAULT_LIMIT, PREVIEW_WIDTH, SearchService, format_preview

ROOT = pathlib.Path(__file__).resolve().parents[1]

# 结构守卫扫描范围（审计 F19-1：只扫 UI 层文件清单，不做全项目扫描）
UI_LAYER_FILES = [
    "gui.py",
    "status_dashboard.py",
    "memory_book.py",
    "motion.py",
]
UI_LAYER_GLOBS = ["ui/**/*.py"]


def _make_store(tmp_path: pathlib.Path) -> ConversationStore:
    store = ConversationStore(db_path=str(tmp_path / "conv.db"))
    for i in range(6):
        store.append("rem" if i % 2 == 0 else "user", "蕾姆" if i % 2 == 0 else "你", f"第{i}条：今天去野外散步，野外很美")
    store.append("ram", "拉姆", "与野外无关的一条记录")
    return store


# ── 1. 等价判据 ────────────────────────────────


def test_limit_subset_equivalence_within_two_limits(tmp_path):
    """同 query 下 limit=10 的结果 = limit=50 结果的前 10 条（id 与顺序逐条相等）。"""
    svc = SearchService(_make_store(tmp_path))
    top = svc.search("野外", limit=10)   # 顶栏口径
    overlay = svc.search("野外", limit=50)  # 浮层口径
    assert top and overlay, "样例数据应能命中"
    assert [r["id"] for r in top] == [r["id"] for r in overlay[: len(top)]]
    assert [r["sender"] for r in top] == [r["sender"] for r in overlay[: len(top)]]


def test_service_passthrough_matches_store_direct(tmp_path):
    """服务与「直连 store」结果逐条相同（证明服务是纯收口，未擅自改排序/过滤）。"""
    store = _make_store(tmp_path)
    svc = SearchService(store)
    for limit in (10, 50):
        assert svc.search("野外", limit=limit) == store.search("野外", limit=limit)


# ── 2. 空值与兜底 ──────────────────────────────


@pytest.mark.parametrize("q", ["", "   ", "\n\t", None])
def test_blank_query_returns_empty_without_touching_store(q):
    class Boom:
        def search(self, *a, **k):  # pragma: no cover - 不应被调用
            raise AssertionError("空 query 不得触碰 store")

    assert SearchService(Boom()).search(q) == []


def test_store_exception_is_swallowed(tmp_path):
    class Boom:
        def search(self, *a, **k):
            raise sqlite_error()

    assert SearchService(Boom()).search("野外") == []


def sqlite_error():
    import sqlite3

    return sqlite3.OperationalError("database is locked")


def test_query_is_stripped_before_hitting_store():
    seen = {}

    class Spy:
        def search(self, query, limit=20):
            seen["query"] = query
            return []

    SearchService(Spy()).search("  野外  ")
    assert seen["query"] == "野外"


# ── 3. FTS 特殊字符 ────────────────────────────


@pytest.mark.parametrize("q", ['"', "*", "-", "(", "野外 AND", "野外'", "^野", "a:b"])
def test_fts_special_chars_do_not_raise(tmp_path, q):
    svc = SearchService(_make_store(tmp_path))
    out = svc.search(q)
    assert isinstance(out, list)  # 不抛异常即可（LIKE 兜底或空列表都接受）


# ── 4. format_preview 边界 ──────────────────────


def test_format_preview_boundaries():
    assert PREVIEW_WIDTH == 60  # 值等价：迁移前为硬编码 60
    short = "短" * 60
    assert format_preview(short) == short  # 恰好 60：不加省略号
    long = "长" * 61
    assert format_preview(long) == "长" * 60 + "…"
    assert format_preview("") == ""
    assert format_preview(None) == ""
    assert format_preview("甲" * 100, width=5) == "甲" * 5 + "…"


def test_default_limit_matches_overlay_budget():
    """默认 limit = 浮层口径 50（顶栏显式传 10）——两处口径写死在服务常量与调用点。"""
    assert DEFAULT_LIMIT == 50
    assert inspect.signature(SearchService.search).parameters["limit"].default == 50


# ── 5. 结构守卫（SPEC 判据 2 / 审计 F19-1 口径）────


def _attr_chain(node: ast.AST) -> list[str]:
    """把 `self.conv_store` 这类属性链展开为 ['self', 'conv_store']。"""
    chain: list[str] = []
    while isinstance(node, ast.Attribute):
        chain.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        chain.append(node.id)
    return list(reversed(chain))


def _ui_layer_paths() -> list[pathlib.Path]:
    paths = [ROOT / rel for rel in UI_LAYER_FILES]
    for pattern in UI_LAYER_GLOBS:
        paths.extend(sorted(ROOT.glob(pattern)))
    return [p for p in paths if p.is_file()]


def test_ui_layer_must_not_call_store_search_directly():
    """UI 层不得直连 `*.conv_store.search(...)`——必须走 SearchService（防两套逻辑复活）。

    扫描范围（F19-1）：仅 UI 层文件（上表 + `ui/**`）；**排除** `tests/**`（测试替身需直连）与
    `shared/search_service.py` 自身。失败信息精确到「文件:行号」。
    """
    violations: list[str] = []
    scanned: list[str] = []
    for path in _ui_layer_paths():
        scanned.append(path.relative_to(ROOT).as_posix())
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "search":
                continue
            chain = _attr_chain(func.value)
            if chain and chain[-1] in {"conv_store", "_conv_store"}:
                violations.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")

    assert scanned, "UI 层文件清单不应为空（守卫自身有效性）"
    assert not violations, (
        "UI 层禁止直连 ConversationStore.search，请经 SearchService：\n  " + "\n  ".join(violations)
    )
