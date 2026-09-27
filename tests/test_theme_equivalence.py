"""SPEC-20260922-18（步 6 / B6·A14）：QSS 全量 golden 快照等价。

**本批的主判据**（审计 2026-09-27 定调「本批最硬的判据」）：
线上全部 widget 的真实 `styleSheet()` 字符串，与迁移前捕获的 golden 快照
**逐字节等价** —— 「视觉零变化」因此不靠人眼，靠机器。

用法
----
::

    # ① 捕获（迁移前跑一次；产物入库 tests/data/qss_golden_v16_5_1.json）
    env -u PYTHONPATH venv/Scripts/python.exe tests/test_theme_equivalence.py --capture
    # ② 校验（迁移后；pytest 亦自动跑）
    env -u PYTHONPATH venv/Scripts/python.exe tests/test_theme_equivalence.py --check
    env -u PYTHONPATH venv/Scripts/python.exe -m pytest tests/test_theme_equivalence.py -q

环境纪律（审计 **F18-1**，阻塞项）
----------------------------------
QSS 字符串里含平台相关路径（`border-image: url(...)`）与字体族回退链 →
**捕获与比对必须同环境**；快照头部持久化平台/Python/PySide6 元数据，
比对时不一致 → **skip（不是 fail）**——跨平台比对无意义，CI（Linux runner）
上该用例 skip 属预期行为，非门禁失效。

归一化（审计 **F18-2**）
------------------------
行尾归一（`\\r\\n` → `\\n`）+ `rstrip()` 去尾空白 + **运行期容器路径归一化**（临时数据目录 / 临时根 → `<DATA>` / `<TMP>`；`border-image: url(...)` 会把 per-run 临时路径写进 QSS，不归一化快照跨 run 假阳性）；**空 QSS 不入快照**；
排序键 `(类名, objectName)`——注：同键多控件（匿名按钮极常见）按完整三元组
`(类名, objectName, qss)` 补全序，避免互相覆盖（本文件对 F18-2 的落地细化）。

隔离纪律（2026-09-27 探针事故后的硬纪律）
-----------------------------------------
直跑模式（`--capture` / `--check`）自行镜像 `tests/conftest.py` 的隔离
（`get_data_dir` 重定向 + `REZERO_LIFE_DB` / `REZERO_GUI_LOG` + dummy key），
并且**必须**经 `scripts/verify_isolation.sh` 包裹运行。
pytest 模式由 conftest 的 autouse 夹具 + 本文件的 `_build_window` 共同隔离。
"""

from __future__ import annotations

import os
import pathlib
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

GOLDEN_PATH = pathlib.Path(__file__).resolve().parent / "data" / "qss_golden_v16_5_1.json"

# 捕获脚本化的动作序列（全部 API-free、确定性）——覆盖懒创建组件
_OVERLAY_ACTIONS = ("history", "memory_book")


# ── 环境元数据（F18-1）──────────────────────────────────


def _env_meta() -> dict:
    import platform as _platform

    import PySide6

    return {
        "platform": _platform.platform(),
        "python": _platform.python_version(),
        "pyside6": PySide6.__version__,
    }


def _env_mismatch(golden_env: dict, current: dict) -> str:
    """返回不一致描述（一致则空串）。三条元数据必须全等。"""
    diffs = [
        f"{k}: 快照={golden_env.get(k)!r} 当前={current.get(k)!r}"
        for k in ("platform", "python", "pyside6")
        if golden_env.get(k) != current.get(k)
    ]
    return "；".join(diffs)


# ── 隔离（直跑模式镜像 conftest）────────────────────────


def _isolate_direct_run() -> pathlib.Path:
    """直跑模式的隔离：临时根 + 环境变量（pytest 模式走 conftest + monkeypatch）。"""
    import tempfile

    root = pathlib.Path(tempfile.mkdtemp(prefix="rz-theme-golden-"))
    os.environ.setdefault("REZERO_LIFE_DB", str(root / "life.db"))
    os.environ.setdefault("REZERO_GUI_LOG", str(root / "gui.log"))
    return root


def _patch_data_dir(data_dir: pathlib.Path) -> None:
    """把 `get_data_dir` 的所有 from-import 绑定重定向（对齐 conftest 的做法）。"""
    import shared.config as _config

    resolved = lambda: str(data_dir)  # noqa: E731
    _config.get_data_dir = resolved
    for _name, _mod in list(sys.modules.items()):
        if _mod is None or _mod is _config:
            continue
        try:
            if getattr(_mod, "get_data_dir", None) is not None:
                setattr(_mod, "get_data_dir", resolved)
        except Exception:  # 个别模块 __getattr__ 会抛错
            continue


# ── 窗口构造（与 tests/test_command_router.py 的 _build_window 同款隔离）──


def _build_window(tmp_root: pathlib.Path, monkeypatch=None):
    import gui
    from shared import life_ledger
    from shared.conversation_store import ConversationStore
    from shared.memory_store import MemoryStore

    def _set(name, value):
        if monkeypatch is not None:
            monkeypatch.setenv(name, str(value))
        else:
            os.environ[name] = str(value)

    _set("DEEPSEEK_API_KEY", "test-key-not-used")
    _set("REZERO_LIFE_DB", tmp_root / "life.db")
    life_ledger.reset_default()

    def _setattr(obj, name, value):
        if monkeypatch is not None:
            monkeypatch.setattr(obj, name, value)
        else:
            setattr(obj, name, value)

    _setattr(gui, "MemoryStore", lambda: MemoryStore(root_dir=str(tmp_root)))
    _setattr(gui, "ConversationStore",
             lambda: ConversationStore(db_path=str(tmp_root / "conv.db")))
    _setattr(gui.QMessageBox, "warning", lambda *a, **k: None)
    return gui, gui.TwinChatApp()


def _run_overlays(window) -> None:
    """脚本化动作：覆盖气泡 / 富状态面板 / 历史浮层 / 回忆之书（全部 API-free）。"""
    # 三条消息 → 气泡 + 头像 + 时间戳等 QSS
    for sender, text, role in (("蕾姆", "QSS 基线消息", "rem"),
                               ("拉姆", "QSS 基线消息", "ram"),
                               ("你", "QSS 基线消息", "user")):
        try:
            window._append_parsed_message(sender, text, role, save=False)
        except Exception:  # 签名漂移时静默跳过（不影响主体快照）
            pass
    # 说话态（头像呼吸/描边类 QSS）
    for fn in ("_set_speaking",):
        f = getattr(window, fn, None)
        if f is not None:
            for role in ("rem", "ram"):
                try:
                    f(role, True)
                except Exception:
                    pass
    window._handle_command("/status")      # 富状态面板
    window._open_history()                 # 历史浮层（懒创建）
    book = getattr(window, "_open_memory_book", None)
    if book is not None:
        book()                             # 回忆之书（懒创建）


# ── 采集（F18-2 归一化）────────────────────────────────


def _normalize(qss: str, reps) -> str:
    """归一化（F18-2）：行尾 + 尾空白 + **运行期容器路径**。

    路径归一化是必须的：数据目录是 per-run 临时目录（`border-image: url(...)`
    会把它写进 QSS），不归一化则快照跨 run 天然不等价（捕获/比对假阳性）。
    """
    qss = qss.replace("\r\n", "\n").rstrip()
    for real, token in reps:
        if real:
            qss = qss.replace(real, token)
    return qss


def _reps(tmp_root: pathlib.Path):
    """路径替换表（长路径优先，避免 `<DATA>` 被 `<TMP>` 抢先吃掉）。

    两种斜杠风格都要归一：QSS 里的 `border-image: url(...)` 用 **正斜杠**
    （Qt 风格），而 `str(Path)` 在 Windows 是反斜杠——只替一种会漏（实测坑）。
    """
    pairs = []
    for p, token in ((tmp_root / "data", "<DATA>"), (tmp_root, "<TMP>")):
        pairs.append((str(p), token))
        pairs.append((str(p).replace("\\", "/"), token))
    return sorted(pairs, key=lambda x: -len(x[0]))


def _collect(window, reps=()) -> list:
    from PySide6.QtWidgets import QWidget

    entries: list = []
    for w in [window, *window.findChildren(QWidget)]:
        try:
            raw = w.styleSheet() or ""
        except RuntimeError:               # 已销毁的 C++ 对象
            continue
        qss = _normalize(raw, reps)
        if not qss:                        # 空 QSS 不入快照
            continue
        entries.append([type(w).__name__, w.objectName() or "", qss])
    entries.sort(key=lambda e: (e[0], e[1], e[2]))
    return entries


def _capture(tmp_root: pathlib.Path, monkeypatch=None) -> list:
    _, window = _build_window(tmp_root, monkeypatch)
    try:
        _run_overlays(window)
        return _collect(window, _reps(tmp_root))
    finally:
        try:
            window.close()
        except Exception:
            pass
        from shared import life_ledger

        life_ledger.reset_default()


# ── 比对 ──────────────────────────────────────────────


def _first_diff(a: str, b: str) -> str:
    """首个不同字符的位置 + 左右各 40 字上下文（便于定位 QSS 差异）。"""
    n = min(len(a), len(b))
    i = next((k for k in range(n) if a[k] != b[k]), n)
    return (f"@{i}（长度 {len(a)} vs {len(b)}）\n"
            f"      快照 …{a[max(0, i-40):i+40]!r}\n"
            f"      当前 …{b[max(0, i-40):i+40]!r}")


def _diff(golden: list, current: list) -> list:
    """返回差异摘要（最多 8 条）：缺失 / 新增 / 变更。"""
    g_map: dict = {}
    for cls, name, qss in golden:
        g_map.setdefault((cls, name), []).append(qss)
    c_map: dict = {}
    for cls, name, qss in current:
        c_map.setdefault((cls, name), []).append(qss)

    out = []
    for key in sorted(set(g_map) | set(c_map)):
        g_qss, c_qss = g_map.get(key, []), c_map.get(key, [])
        if g_qss == c_qss:
            continue
        only_g = [q for q in g_qss if q not in c_qss]
        only_c = [q for q in c_qss if q not in g_qss]
        for q in only_g:
            near = [c for c in c_qss if c[:20] == q[:20]]
            out.append(f"缺失 {key}: {q[:90]!r}" + (f"  ↔ 首差位置 {_first_diff(q, near[0])}" if near else ""))
        for q in only_c:
            near = [g for g in g_qss if g[:20] == q[:20]]
            out.append(f"新增 {key}: {q[:90]!r}" + (f"  ↔ 首差位置 {_first_diff(near[0], q)}" if near else ""))
        if not only_g and not only_c and g_qss != c_qss:
            out.append(f"数量变化 {key}: 快照 {len(g_qss)} → 当前 {len(c_qss)}")
    return out[:8]


# ── pytest 用例 ───────────────────────────────────────


def test_qss_golden_equivalence(qapp, tmp_path, monkeypatch):
    """迁移后全部 widget 的 QSS 与 golden 逐字节等价（视觉零变化的机器判据）。"""
    import json

    import pytest

    if not GOLDEN_PATH.exists():
        pytest.skip(f"golden 快照不存在（先跑 --capture）：{GOLDEN_PATH}")
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    mismatch = _env_mismatch(golden.get("env", {}), _env_meta())
    if mismatch:
        pytest.skip(f"环境不一致 → 跳过（审计 F18-1）：{mismatch}")

    current = _capture(tmp_path, monkeypatch)
    diff = _diff(golden["entries"], current)
    assert not diff, (
        "QSS 与 golden 快照不等价（视觉零变化判据失败）：\n  "
        + "\n  ".join(diff)
        + f"\n（快照 {len(golden['entries'])} 条 / 当前 {len(current)} 条）"
    )


# ── 直跑 CLI ──────────────────────────────────────────


def _main(argv: list) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(description="QSS golden 快照：捕获 / 校验")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--capture", action="store_true", help="捕获并写入 golden")
    group.add_argument("--check", action="store_true", help="与 golden 比对")
    args = parser.parse_args(argv)

    root = _isolate_direct_run()
    _patch_data_dir(root / "data")
    (root / "data").mkdir(parents=True, exist_ok=True)
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])  # noqa: F841

    meta = _env_meta()
    if args.capture:
        entries = _capture(root)
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "env": meta,
            "note": "SPEC-20260922-18 QSS golden（迁移前捕获；归一化见 tests/test_theme_equivalence.py 头注释）",
            "entries": entries,
        }
        GOLDEN_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[capture] 已写入 {GOLDEN_PATH}")
        print(f"[capture] 条目 {len(entries)} 条 · 环境 {meta}")
        return 0

    if not GOLDEN_PATH.exists():
        print(f"[check] golden 不存在：{GOLDEN_PATH}")
        return 2
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    mismatch = _env_mismatch(golden.get("env", {}), meta)
    if mismatch:
        print(f"[check] SKIP（审计 F18-1 环境不一致）：{mismatch}")
        return 0
    current = _capture(root)
    diff = _diff(golden["entries"], current)
    if diff:
        print("[check] FAIL —— QSS 与 golden 不等价：")
        for line in diff:
            print("   ", line)
        print(f"  快照 {len(golden['entries'])} 条 / 当前 {len(current)} 条")
        return 1
    print(f"[check] PASS —— {len(current)} 条 QSS 与 golden 逐字节等价 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
