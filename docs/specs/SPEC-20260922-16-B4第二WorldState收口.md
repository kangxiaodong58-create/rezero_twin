```
SPEC-ID：SPEC-20260922-16
级别：L2（跨模块：main / vignette / world_state / smoke_test）
状态：⏳ 待批准（**按 2026-09-27 审计 F16-1 改为方案 B：零逻辑 shim，不删除模块**）
```

# B4 收口：第二 WorldState 统一到核心类（方案 B —— 兼容层降级为零逻辑 shim）

## 目标

1. **内部统一**：CLI（`main.py`）与 `shared/vignette.py:prepare_session_opening` 改走**核心 `shared.state.WorldState`**，产线不再经过兼容层；
2. **兼容层降级**：`shared/world_state.py`（现 108 行：子类别名 + 4 个模块函数）重写为**零逻辑 shim**——保留**可导入性**与既有名字，函数体全部**转调核心类**，文件头写明「仅外部/历史脚本兼容，新代码请用 `shared.state.WorldState`」；
3. **不删除模块**（审计 F16-1 明确不批准删除：删除是假设性收益，shim 是确定性收益）；
4. **迁移指引落档**（审计 F16-3）。

## 复核修正（只读侦察，2026-09-23）

- `shared/world_state.py:29 class WorldState(_CoreWorldState)` 是**子类**（字段别名 property + 4 个模块函数），不是独立实现；
- `world_state.json` **全仓不存在**（`find` 为空）⇒ 无文件级依赖；
- `shared/vignette.py:869 prepare_session_opening` **全仓无 .py 调用者**（仅历史探针/文档提及）⇒ 保留并标注「未接线入口」；
- 兼容层调用方全集：`main.py`、`shared/vignette.py`、`tests/smoke_test.py`（两个兼容层用例）、`docs/evaluation/sessions/**` 归档探针（**不在 CI 路径**，pytest 只收 `tests/`）。

## 非目标

**删除 `shared/world_state.py`**（F16-1 否决）；改 CLI 交互/命令语义；合并 GUI 与 CLI 会话循环；动 `memory.json` 的 `world_state` 键结构（**结构不变**，仍是 `WorldState.save_dict()` 产物）；改归档探针（只落迁移指引）。

## 方案（方案 B：统一 + 零逻辑 shim）

1. `main.py`：`from shared.state import WorldState`；`ws = WorldState.load_or_create(store.load().get("world_state"))`；保存 `store.set("world_state", ws.save_dict())`（经 `MemoryStore`，与 GUI 同一持久化管线）；`mark_interaction` 用核心方法（`shared/state.py:595`）。
2. `shared/vignette.py`：`prepare_session_opening` 改用核心类；docstring 标注「未接线入口（当前无调用者）」并保留（避免误删外部用法）。
3. `shared/world_state.py`：**重写为零逻辑 shim**——保留 `WorldState` 名字导出（含 docx 时代的 4 个别名 property：纯别名、无逻辑，供外部脚本不炸）+ 4 个模块函数**转调核心类**；文件头写迁移指引。
4. `tests/smoke_test.py`：两个 docx 兼容层用例改为「**shim 转调等价**」断言（shim 可导入 + 别名 property 与核心字段等价 + save/load 往返仍走 `memory.json`）。

## 文件

| 动作 | 文件 |
|---|---|
| 修改 | @main.py · @shared/vignette.py · @tests/smoke_test.py |
| 重写（**不删除**） | @shared/world_state.py（108 行 → 约 25 行 shim） |
| 新增 | 无（迁移指引入 devlog + shim docstring） |

## 接口/数据是否变化

`shared.world_state` **保持可导入、名字不变**（外部脚本不炸）；`memory.json` 结构不变；CLI 行为不变；内部产线不再 import 兼容层。

## 测试方式

1. **机械判据**：`grep -rn "shared.world_state" --include=*.py` → 生产路径（`main.py` / `shared/*.py` / `llm/*.py` / `tests/*`）**仅剩 shim 自身**（`docs/` 归档探针不计）；
2. **shim 可导入性**：隔离环境下 `import shared.world_state as W; import shared.state as S; assert issubclass(W.WorldState, S.WorldState)` + `W.save_world_state(W.load_world_state())` 往返无异常；
3. **CLI**：`python main.py --help` 退出码 0；`python -c "import main"` 无错；
4. **世界状态往返**：新用例（save→load 后 `last_letter_ts/last_letter_date/active_event/days_since_last` 等价）；
5. **回归**：全量 295 + 隔离校验 + 冒烟 31/31。

## 回滚方式

`git revert` 该提交（四处文件，无数据迁移；shim 与原实现行为等价 ⇒ 回滚无状态影响）。

## 风险

- shim 与核心类**字段别名漂移** → 由 smoke「shim 转调等价」用例守卫（别名属性与核心字段逐条比对）；
- 外部脚本若使用除 4 个别名外的历史字段 → 超出本 SPEC 范围（不新增别名），如触发请提 RCR。

## 审计条件闭环（2026-09-27 审计报告）

| 条件 | 闭环方式 |
|---|---|
| F16-1 改方案 B | 本文件即方案 B（零逻辑 shim，不删模块）；「若要删模块」的三项前置（用户声明无外部依赖 + 迁移指引落档 + 全仓 grep 断言）**留待有证据时另立 SPEC** |
| F16-2 vignette 处理 | 保留 + docstring 标注「未接线入口」（审计认可） |
| F16-3 迁移指引 | 双落档：`docs/devlog/步1-4前置材料_2026-09-27.md` §7 + shim 文件头 docstring |

## 等待批准：是（口令 `批准 SPEC-20260922-16`；已按审计改方案 B）
