"""pytest 全局夹具：在 gui 模块加载前设置测试环境。

背景（2026-08-19 排查）：_VIGNETTE_DISABLED 在 gui 模块加载时求值；
pytest 按字母序收集时 smoke_test.py 先 import gui（此时 env 未设）
→ 禁用标志永久 False → 所有测试窗口触发「主动来信」（含写真实库风险）。
各直跑文件自己的 setdefault 无法影响已加载的 gui 模块——统一在此设置。
"""
import os
import sys
import tempfile

import pytest

os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# V15.0-M1：人生账本测试隔离——引擎/bridge/gui 的记账镜像走临时库，
# 不污染真实 data/life.db（单例在首个镜像调用时才解析该路径）。
os.environ.setdefault(
    "REZERO_LIFE_DB",
    os.path.join(tempfile.mkdtemp(prefix="rz-life-test-"), "life.db"))
# V16.1：GUI 日志隔离——测试期 _log 曾追加写真实 data/gui.log。
os.environ.setdefault(
    "REZERO_GUI_LOG",
    os.path.join(tempfile.mkdtemp(prefix="rz-log-test-"), "gui.log"))
# A19（M7 本地闭环留证暴露）：套件自足——干净 checkout 无 .env 时，构造 TwinChatApp
# 的用例在 gui.py:1844（_create_bot）抛 ValueError: 未找到 DEEPSEEK_API_KEY（9 例）。
# setdefault 不覆盖环境中已有的真实 key；测试全程零 API 调用，dummy 仅过存在性检查。
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")


@pytest.fixture(scope="session")
def qapp():
    """全 session 唯一 QApplication，且**先于**任何 function 级夹具创建。

    SPEC-20260922-10：`tests/test_motion.py` 的启用态用例需要临时把
    `QT_QPA_PLATFORM` 从 `offscreen` 改成别的值（否则 `motion.enabled()` 恒为 False，
    见 `motion.py:25`）。若该环境变量在 QApplication **创建之前**就被改掉，Linux runner
    会尝试加载不存在的平台插件（`windows`）→ Qt 致命错误 → CI 整步失败。
    session 级夹具由 pytest 的 scope 规则保证先于 function 级 `monkeypatch` 建好，
    因此应用始终以 offscreen 起步；session 级引用同时避免应用被 GC 后重建。
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """V16.3.3（A11）：把 `get_data_dir()` 整体重定向到 per-test 临时目录。

    背景：SPEC-04 的 CI 首跑暴露——干净 checkout 下跑测试会创建真实
    `data/backdrop_cache.png`（gui.py:492）与 `data/conversations.db`
    （`ConversationStore` 默认库）；本机因这两个文件早已存在而长期看不出来。

    做法：`get_data_dir` 在多个模块是 **from-import 绑定**，逐个替换模块属性；
    替换 `shared.config` 一处同时覆盖晚绑定调用点（memory_store / life_ledger）。
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    resolved = lambda: str(data_dir)  # noqa: E731

    import shared.config as _config
    monkeypatch.setattr(_config, "get_data_dir", resolved)

    try:  # 收集期测试模块已 import gui；此处确保补丁一定落到 gui 的绑定上
        import gui as _gui
        monkeypatch.setattr(_gui, "get_data_dir", resolved)
    except ImportError:  # 无 Qt 环境下非 GUI 测试仍可运行
        pass

    # 已完成导入的模块里，凡持有 `get_data_dir` 名字的（from-import 绑定）全部替换。
    # 不逐个点名：漏一个就漏一类（A11 第一次修就栽在点名清单不全）。
    # 未来导入的模块会拿到上面已改过的 `shared.config.get_data_dir`，天然被覆盖。
    for _name, _mod in list(sys.modules.items()):
        try:
            if _mod is _config or _mod is None:
                continue
            if getattr(_mod, "get_data_dir", None) is not None:
                monkeypatch.setattr(_mod, "get_data_dir", resolved, raising=False)
        except Exception:  # 个别模块 __getattr__ 会抛错，跳过即可
            continue

    return str(data_dir)
