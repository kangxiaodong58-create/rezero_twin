```
SPEC-ID：SPEC-20260922-16
级别：L2（跨模块：main / vignette / world_state / smoke_test；含模块退役）
状态：⏳ 待批准
```

# B4 收口：第二 WorldState（docx 兼容层）统一到核心类

## 目标

把 CLI（`main.py`）与 `shared/vignette.py:prepare_session_opening` 从 `shared/world_state.py`（**核心 `shared.state.WorldState` 的子类兼容层**，108 行）迁到**核心类单源**，随后退役该兼容层——消除「两个 WorldState 在产线并存」。

## 复核修正（只读侦察，2026-09-23）

- 原台账写「第二 WorldState 仍在生产路径」→ **部分修正**：
  - `shared/world_state.py:29 class WorldState(_CoreWorldState)` 是**子类**（字段别名 property + 4 个模块函数），不是独立类；
  - `main.py:20/109/113` 在产线（CLI 入口，forensic 设计文档指定为崩溃取证入口之一）；
  - `shared/vignette.py:869 prepare_session_opening`（`:878-881` 用兼容层）**当前全仓无 .py 调用者**（仅历史探针与文档提及）→ 属「疑似死入口」；
  - `world_state.json` **全仓不存在**（`find` 为空）→ 无文件级依赖，原「先确认无人依赖 world_state.json」的前置条件已满足；
  - 兼容层调用方全集：`main.py`、`shared/vignette.py`、`tests/smoke_test.py`（两个兼容层用例）、`docs/evaluation/sessions/**` 历史探针（**不在 CI 路径**，pytest 只收 `tests/`）。

## 非目标

改 CLI 的交互/命令语义；合并 GUI 与 CLI 的会话循环；动 `memory.json` 的 `world_state` 键结构（**结构不变**，仍是 `WorldState.save_dict()` 产物）；删历史探针脚本（只记录影响）。

## 方案（建议路线：统一 + 退役）

1. `main.py`：改 `from shared.state import WorldState` + `WorldState.load_or_create(store.load().get("world_state"))` 与 `store.set("world_state", ws.save_dict())`（经 `MemoryStore`，与 GUI 同一持久化管线）；`mark_interaction` 用核心方法（`shared/state.py:595`）。
2. `shared/vignette.py`：`prepare_session_opening` 改用核心类；**因无调用者**，同批在 docstring 标注「未接线入口（无调用者）」并保留（不删，避免误删外部用法）。
3. `shared/world_state.py`：**删除**（兼容层退役）。
4. `tests/smoke_test.py`：两个 docx 兼容层用例（`:377 test_world_state_docx_compat` 等）改为**核心类等价断言**（保留原覆盖意图：字段别名 → 属性、save/load 往返、启动推演）。

## 文件

| 动作 | 文件 |
|---|---|
| 修改 | @main.py · @shared/vignette.py · @tests/smoke_test.py |
| 删除 | @shared/world_state.py |

## 接口/数据是否变化

外部脚本若 `import shared.world_state` 将失效（已知影响面：`docs/evaluation/sessions/**` 历史探针 12 处，均为归档产物、不在 CI）；`memory.json` 结构不变；CLI 行为不变。

## 测试方式

1. 机械判据：`grep -rn "shared.world_state" --include=*.py .`（排除 `docs/`）= **0**。
2. CLI 可用性：`python main.py --help` 退出码 0；`python -c "import main"` 无错。
3. 世界状态往返：新用例（核心类 save→load 后字段等价，含 `last_letter_ts/last_letter_date/active_event/days_since_last`）。
4. 回归：全量 295 + 隔离校验 + 冒烟 31/31。

## 回滚方式

`git revert` 该提交（含恢复被删模块）；兼容层为纯别名实现，恢复无数据影响。

## 风险

- **误删外部依赖**：如你有仓库外的脚本用 `shared/world_state`，请在批准时说明 → 改走「方案 B：保留零逻辑 shim（4 个函数转调核心类）」。默认按方案 A 执行。
- CLI 侧持久化路径改动 → 由「世界状态往返」用例 + 冒烟兜底。

## 等待批准：是（口令 `批准 SPEC-20260922-16`）
