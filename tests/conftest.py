"""pytest 全局夹具：在 gui 模块加载前设置测试环境。

背景（2026-08-19 排查）：_VIGNETTE_DISABLED 在 gui 模块加载时求值；
pytest 按字母序收集时 smoke_test.py 先 import gui（此时 env 未设）
→ 禁用标志永久 False → 所有测试窗口触发「主动来信」（含写真实库风险）。
各直跑文件自己的 setdefault 无法影响已加载的 gui 模块——统一在此设置。
"""
import os
import tempfile

os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# V15.0-M1：人生账本测试隔离——引擎/bridge/gui 的记账镜像走临时库，
# 不污染真实 data/life.db（单例在首个镜像调用时才解析该路径）。
os.environ.setdefault(
    "REZERO_LIFE_DB",
    os.path.join(tempfile.mkdtemp(prefix="rz-life-test-"), "life.db"))
