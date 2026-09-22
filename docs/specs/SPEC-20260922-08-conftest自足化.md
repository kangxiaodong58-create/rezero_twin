```
SPEC-ID：SPEC-20260922-08
级别：L1（局部修复，不改接口；改测试基建一行）
状态：⏳ 待批准
```

# 测试套件自足化：conftest 注入 dummy API key（闭合 A19 → M7 本地闭环判据①③）

## 目标

让「**干净 checkout（无 `.env`、无 `data/`、无宿主 `PYTHONPATH`）只跑 `pytest tests/ -q` 就全绿**」成立——这是 M7 本地闭环判据①③的字面要求，也是新克隆者的复现性要求。

## 依据（实测，非推断）

`docs/devlog/M7本地闭环留证_2026-09-22.md` §2：

- 干净克隆（`a010c11`）裸环境：`pytest tests/ -q` → **`9 failed, 286 passed`**，9 例全部在 `tests/test_ui_offscreen.py`，`gui.py:1844`（`_create_bot`）抛 `ValueError: 未找到 DEEPSEEK_API_KEY`；
- 注入 `DEEPSEEK_API_KEY=test-key-not-used`（同 `ci.yml:25`）→ **`295 passed`** + 隔离校验通过；
- 既有做法：4 个测试文件已各自 `monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-used")`（`test_command_router.py:125` / `test_motion.py:110` / `test_state_persistence.py:204` / `test_status_dashboard.py:83`）——**模式已存在，只是没提升到全局**，且 `test_ui_offscreen.py` 未做。
- 台账：**A19 [P2]**（架构 Spec A′ 段）。

## 改法（一行 + 注释）

`tests/conftest.py` 顶部（在 import 项目模块**之前**）：

```python
# A19：套件自足——干净 checkout 无 .env 时，构造 TwinChatApp 的用例需要 key 存在。
# setdefault 不覆盖环境中已有的真实 key；测试全程零 API 调用，dummy 仅满足存在性检查。
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-not-used")
```

- 用 **`setdefault`**（不是赋值）：本地有真实 key 时行为不变；不阻断未来手工真实 API 验收（那些脚本在 `docs/evaluation/`，不走 pytest）。
- 位置与既有 `REZERO_GUI_LOG` / `REZERO_LIFE_DB` 自隔离同款；`tests/smoke_test.py` 的 A12 自隔离不受影响。

## 非目标

- 不改成强制覆盖（`os.environ[...] =`）；
- 不改 `gui.py` 的 key 检查逻辑（生产行为零变化）；
- 不动 `ci.yml`（其 env 注入保留为第二道保险）；
- 不处理 A13–A18 等其它债。

## 需要读取/修改的文件

- @tests/conftest.py
- @docs/specs/INDEX.md（状态与合入回填）
- @CHANGELOG.md（V16.3.7）
- @docs/devlog/M7本地闭环留证_2026-09-22.md（补「A19 已修 + 裸环境重新留证」段）

## 新增文件

- `docs/specs/SPEC-20260922-08-conftest自足化.md`（本文件）

## 接口/数据是否变化

无（仅测试基建）。

## 测试方式（机械判据）

1. **裸干净 checkout**（无 `.env`/无 `data/`/无宿主 PYTHONPATH，**不注入任何 key**）：`bash scripts/verify_isolation.sh env -u PYTHONPATH <venv>/python.exe -m pytest tests/ -q` → **295 passed** 且 `data/` 逐字节未变；
2. 带 `DEEPSEEK_API_KEY=test-key-not-used`（CI 等价）复跑 → 同样 `295 passed`；
3. `find data -type f | wc -l` = 0；`git status --porcelain` 仅列本 SPEC 允许的文件；
4. 本机真项目复跑 → `295 passed`（真实 `.env` 存在时 `setdefault` 不生效，确认行为不变）。

## 回滚方式

`git revert <本批次 squash>`（一行改动，零运行时影响）。

## 风险

**低**。唯一注意点：若将来有测试要**故意**验证「无 key 时报错」，需在该用例内显式 `monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)`。已 grep 确认当前**无**此类用例（`tests/` 内对 `DEEPSEEK_API_KEY` 的引用只有 4 处 setenv + 1 处历史注释）。

## 等待批准：是。请回复：**批准 L1 SPEC-20260922-08**
