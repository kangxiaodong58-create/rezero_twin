# FORENSIC_DEBUGGING_PROTOCOL v1.2（仓库落地版）

> 本文档将设计文档引用的外部协议（原 `agent_os/FORENSIC_DEBUGGING_PROTOCOL.md`，未入库）落地为仓库内可执行版本。
> 设计依据：`docs/design/forensic_subsystem_design.md` v1.0；实现：`runtime/forensic/`（M1~M4 全部落地，2026-08-29）。
> 调查终端是 Agent（或人），不是 GUI——本协议描述 Agent 面对的接口与纪律。

---

## §0 Incident Capture（现场自动捕获）

系统在运行时自动完成，Agent 无需干预：

- **黑匣子**：`EventRingBuffer` 环形缓冲，双上限 `min(200 事件, 60s 窗口)`，满则覆盖最旧。
- **崩溃取证**：未捕获异常（主线程 `sys.excepthook` / 子线程 `threading.excepthook`）触发
  `crash_dump.py`——read buffer → crash marker → flush 预打开句柄 → 保留原崩溃行为。
  产物：`incidents/INC-{yyyyMMdd-HHmmss}-{seq}/dump.json`（事件缓冲全量 + 环境快照 + 状态 PENDING）。
- **Crash Handler 硬性约束**（MUST）：不大内存分配 / 不拿应用锁 / 不网络 / 不 logger / 不抛异常；
  **绝不改变原始崩溃行为**；取证失败静默。
- **stale callback**：流式链起点捕获 generation；起点已 stale → `STALE_CALLBACK_DETECTED` 并拒绝执行；
  chunk 检查点 stale → `STALE_CALLBACK_OBSERVED` 并中止流；末尾写 history 前兜底校验（V14.9 起「记录后拦截」）。
- **状态轨迹**：HardStateEngine 低频跃迁（篇章/好感等级/拉姆阶段/鬼化/锁定）经 `transition()`
  进黑匣子（`STATE_TRANSITION` 事件）；高频数值变化刻意不入缓冲（防挤占 200 容量）。

## §1 证据真相与目录布局

```text
<root>/
├── incidents/                  # 崩溃现场（CLI/headless：项目根；GUI/EXE：data/incidents/）
│   └── INC-{ts}-{seq}/
│       └── dump.json           # 唯一证据真相：events[] + crash{} + status + 环境
└── .debug/                     # 案件工作目录（M4）
    └── CASE-{INC-id}/
        └── case.md             # 模板生成的调查工作台（预填现场摘要）
```

- `dump.json` 的 `status` 字段是案件状态唯一真相：`PENDING → CLAIMED → INVESTIGATING → RESOLVED / IGNORED`
- `incidents/`、`.debug/` 均不入库（gitignore）；结案时把关键摘录归档到 `docs/evaluation/sessions/`。

## §2 Agent 调查工作流（CASE_OPEN → CASE_CLOSED）

```python
from runtime.forensic.manifest import scan_incidents, list_incidents
from runtime.forensic.case import open_case, close_case

inc = "incidents"                     # 或 data/incidents（GUI EXE 场景）

# 1. 扫描未处理案件
pending = scan_incidents(inc)          # status ∈ PENDING/CLAIMED/INVESTIGATING

# 2. 开案（认领 + 建案件目录 + 置 INVESTIGATING）
case_md = open_case(inc, "INC-xxx", claimant="agent-name")
#   → 已被认领 / 案件不存在 / 建目录失败 → None（防双 Agent 争抢）

# 3. 调查：读 dump.json 时间线（按 seq 排序）、跑 headless 复现、形成假设
#   python -m runtime.forensic.headless_runner 亦可用作复现通道
#   dump.json 摘要字段：events / event_histogram / incidents / generations

# 4. 结案（RESOLVED + case.md 追加结案节 + CASE_CLOSED 事件）
close_case(inc, "INC-xxx",
           resolution="一句话结论",
           root_cause="根因", fix="修复 commit 或 PR")
```

替代误报案件：`mark_ignored(inc, "INC-xxx")`（退场但审计可见，不产生 case.md）。

## §3 调查纪律

1. **只读证据**：dump.json 只允许通过 manifest 改 `status/claimed_by/claim_time`，事件数据不得改写。
2. **先复现再修复**：能用 headless runner（固定 seed + DelayProfile 注入）复现的，先量出崩溃率再动手。
3. **结案必填**：resolution / root_cause / fix——无根因不得结案；无法定位根因的挂 IGNORED 并写明原因。
4. **留痕**：结案后把时间线、根因、修复摘录归档 `docs/evaluation/sessions/forensic_<日期>/`，并在 CHANGELOG 记账。
5. **M4 验收口径**（设计 §8）：首个真实案件走通 CASE_OPEN→CASE_CLOSED。
   首案已归档：`docs/evaluation/sessions/forensic_m4_2026-08-29/`。

## §4 API 速查

| 层 | API | 说明 |
|---|---|---|
| 运行时 | `init_forensic(dir)` / `shutdown_forensic()` | 入口初始化 / 正常退出清理（gui.main / main.run_llm 已接） |
| 运行时 | `record(event, component=..., generation=...)` | 事件入黑匣子（未初始化 no-op） |
| 运行时 | `transition(component, from, to)` | 状态跃迁（state.py 已接） |
| 交接 | `scan_incidents(dir)` / `list_incidents(dir)` | 未处理案件 / 全量清单 |
| 交接 | `claim_incident(dir, id, claimant)` | 认领（重复认领 False） |
| 交接 | `resolve_incident` / `mark_ignored` | 结案 / 忽略 |
| M4 | `case.open_case(dir, id, claimant=...)` | 开案：认领+目录+INVESTIGATING+CASE_OPEN |
| M4 | `case.close_case(dir, id, resolution, ...)` | 结案：RESOLVED+case.md 结案节+CASE_CLOSED |
| 复现 | `headless_runner.run_campaign(n, seed, profile=...)` | 崩溃率/事件直方图/INC 产出，同 seed 可复现 |
