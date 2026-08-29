# Re:Zero Twin Forensic 子系统设计 v1.1

**Status:** M1~M4 全部落地（2026-08-29 验收）
**Date:** 2026-08-19 定稿 / 2026-08-29 实现修订
**关联协议:** `docs/forensic/FORENSIC_DEBUGGING_PROTOCOL.md` v1.2（仓库落地版，M4 起取代外部引用）
**目标:** 让概率性 Bug（如长对话崩溃、软 OOC）第一次"留下脚印"——崩溃前最后 N 个事件自动落盘，Agent 凭真实数据破案，而不是事后猜。

---

## 1. 为什么是这三件基础设施

协议是给"有取证能力的系统"用的。rezero_twin 当前最缺的不是更多 Prompt，而是：

| 设施 | 解决什么 | 对应协议层 |
|---|---|---|
| ① Event Ring Buffer | 崩溃前发生了什么（黑匣子） | §0 Incident Capture |
| ② Generation ID + State Trace | stale callback 的预防+暴露+记录 | §0 Incident Capture |
| ③ Headless Runner | 复现通道：崩溃率可测量、实验可做 | §0.5 Triage 复判 / §11 验证 |

三者共同点：**不是调试旁路，而是 Runtime 本身的可靠性基础设施**。

---

## 2. 模块布局

```
runtime/
└── forensic/
    ├── __init__.py
    ├── event_buffer.py      # 环形缓冲：seq + 双时钟 + startup_id + generation
    ├── recorder.py          # 事件注入 API（装饰器 / context manager）
    ├── crash_dump.py        # 崩溃处理：预分配文件 + marker + 静默失败
    ├── state_trace.py       # 状态机转换追踪（state_before/state_after）
    ├── session_trace.py     # 会话级 trace（session_id / generation 绑定）
    ├── forensic_manifest.py # INC 落盘清单 + 启动扫描（Handoff 入口）
    └── incidents/           # INC-{yyyyMMdd-HHmmss}-{seq}/
        └── INC-xxx/
            ├── dump.json    # 事件缓冲全量 + crash marker
            ├── manifest.json # 版本/startup_id/seq 范围/时间窗
            └── environment.json # 环境快照（协议 §1 SCENE_FROZEN 输入）
```

**关键约束：`runtime/` 模块不得 import PySide6。** 它是纯 Python 层，headless runner 和 GUI 共用。

---

## 3. Event Ring Buffer 规格

### 3.1 事件 schema（每条记录）

```yaml
seq: 10421                  # 进程内单调递增，唯一排序依据
startup_id: "20260819-1542" # 跨进程分段（进程重启后 seq 重新从 0 开始）
ts_mono: 1787130206.214     # monotonic clock：计算 A→B 间隔
ts_wall: 1787130206.214     # wall clock：参考，可能跳变
generation: 37              # 会话 generation id（stale 检测用）
event: MESSAGE_RECEIVED     # 事件名
component: conversation     # 组件标识
session_id: "s-7f3a"
state_before: IDLE          # 状态枚举值（不是状态对象）
state_after: REQUESTING
payload_summary: "len=128"  # 摘要，禁止大对象
callback_id: null
thread: "main"              # 线程/任务标识
exception: null             # 崩溃事件时附 traceback 摘要（截断）
```

### 3.2 容量与写入

- 双上限：`min(200 事件, 60 秒窗口)`，满则覆盖最旧（环形）
- 内存成本：200 × ~500B ≈ 100KB，可接受
- 写入必须：无锁或极短临界区（单生产者单消费者队列即可；多线程时用 `threading.Lock` 但临界区只做 append）
- **写入失败静默降级**：缓冲满/分配失败 → 丢弃新事件，绝不抛异常影响业务

### 3.3 Crash Handler 约束（协议 §2 硬性要求）

```
MUST NOT: 大内存分配 / 获取应用锁 / 网络 / 复杂逻辑 / 调 logger / 抛异常 / 递归处理失败
MUST ONLY: read buffer → append crash marker → flush 预打开文件 → exit
```

实现要点：
- **预分配**：启动时 `mmap` 或预打开 dump 文件并保持句柄；崩溃时直接写
- **预置 marker**：dump 文件头部预留 crash marker 槽位；崩溃时填时间戳 + `startup_id` + 最后 seq
- 取证失败静默；**绝不改变原始崩溃行为**

---

## 4. Generation ID + State Trace

### 4.1 机制

- `Session.generation`：会话每次重建（新对话/重置）递增
- 所有异步回调（API 流式回调、定时器、信号槽）在**起点捕获** generation，执行前校验：
  ```python
  if callback.generation != session.generation:
      record_event("STALE_CALLBACK_DETECTED", ...)  # 记录后拒绝执行
  ```
- **沿链传递**：回调 A 内部派生回调 B → B 继承 A 捕获的 generation 快照（防跨层 stale 漏检）

### 4.2 双用途

同一套机制同时实现：
- **预防**：stale callback 执行前被拦截
- **暴露**：被拦截时记录事件（`STALE_CALLBACK_DETECTED`），问题浮出水面
- **记录**：事件进缓冲，崩溃现场有据可查

### 4.3 State Trace 注入点

状态转换处统一走 `state_trace.transition(from, to, component, generation)`：
- 记录 `state_before / state_after`（枚举值）
- 非法转换（如 STREAMING→IDLE 后 callback 再写）会在时间线里现形

---

## 5. 接入点映射（对照现有代码）

| 现有代码 | 接入内容 |
|---|---|
| `main.py` `run_llm()` | 启动时：初始化 forensic、`startup_id`；会话循环：`MESSAGE_RECEIVED`、`REPLY_COMPLETED`；崩溃时：crash_dump 接管 |
| `gui.py` | UI 事件：`UI_EVENT`；窗口关闭/会话切换：generation++ |
| `llm/bridge.py` `ReZeroLLMBridge` | API 调用：`API_REQUEST` / `API_TIMEOUT` / `RETRY` / `STREAM_START` / `STREAM_END`；回调入口：generation 捕获+校验 |
| `shared/state.py` `HardStateEngine` | 状态转换：经 `state_trace.transition()`（StoryArc/FavorLevel/Intent 等） |
| `shared/conversation_store.py` / `memory_store.py` | `SESSION_LOAD` / `SESSION_SAVE` / `MEMORY_READ`（带 session_id） |
| `main.py` 启动流程 | Handoff 扫描：`forensic_manifest.scan()` 检测未处理 INC → 提示用户 |

---

## 6. Headless Runner（复现通道）

**现状红利：`main.py` 已是 CLI 驱动循环**（`input()` 驱动、不依赖 GUI）——headless 化的基础已存在。需要补的是：

```python
# runtime/forensic/headless_runner.py
def run_case(seed: int, convo_count: int, delay_profile: dict) -> dict:
    """模拟 N 轮对话（可注入 API delay / timeout），返回崩溃率与事件序列。"""
```

### 能力目标

```text
for i in range(100): run_case(...)      # 崩溃率统计（1/10 → 可测量）
seed=1..100                             # 固定随机种子，可重复
delay_profile: api_delay / timeout / callback_delay / input_interval  # 时序扰动实验
输出: crash_rate + 最后事件序列 + state transition 频率
```

### 前置条件（架构验收器）

- `llm/` 与 `shared/` 核心逻辑**纯 Python**（不 import PySide6）——这是 headless 的硬边界，也是 Forensic 子系统给架构的压力测试
- API 调用可注入 mock（`delay_profile`），不依赖真实网络

---

## 7. Handoff 集成

```text
崩溃 → INC dump 落盘（incidents/）
  ├── main.py 下次启动：scan() → "检测到上次未处理的异常案件 INC-xxx" → 用户可将现场喂给 Agent
  └── Hermes cron 巡检（可选，二期）：检测新 INC → 自动开案
```

### handoff.status（防双 Agent 争抢）
`PENDING → CLAIMED(claimant+time) → INVESTIGATING → RESOLVED → IGNORED`

---

## 8. 里程碑

| 里程碑 | 内容 | 验收 |
|---|---|---|
| M1 黑匣子 | `event_buffer.py` + `recorder.py` + `crash_dump.py` + 接入 main.py/llm/bridge.py | 模拟崩溃 → INC dump 完整落盘；buffer 写入零异常 |
| M2 交接 | `forensic_manifest.py` + 启动扫描 + handoff.status | 崩溃后重启提示 INC；状态机可 CLAIM |
| M3 复现通道 | `headless_runner.py` + generation guard + state_trace | 100 轮对话脚本可跑；崩溃率可统计；stale callback 被拦截并记录 |
| M4 协议对接 | 案件目录模板 + Agent 侧流程（skill） | 首个真实案件走通 CASE_OPEN→CASE_CLOSED |

---

## 9. 非目标（本期不做）

- ~~知识库/Pattern Mining~~：等真实案件 ≥5 再启动（协议 §17 Phase B）
- ~~案件状态机持久化（.debug/CASE-xxx/ 全目录）~~：M4 再做；M1-M3 只产出 INC 现场
- ~~GUI 内嵌案件浏览器~~：不做，Agent 是调查终端
- ~~网络请求级 tracing~~：事件缓冲先覆盖应用层

---

## 10. 风险与边界

| 风险 | 对策 |
|---|---|
| 取证器自身崩溃 | Crash Handler 极简约束 + 静默失败（协议 §2 硬性） |
| Heisenberg 效应 | 只记状态标识（generation+枚举），不记状态对象 |
| 多线程事件乱序 | seq 唯一排序；时间戳仅参考 |
| 观测改变时序 | 写入路径零业务逻辑，临界区极短 |
| GUI 耦合阻塞 headless | `runtime/` 禁止 import PySide6；解耦作为架构需求 |

---

## 11. 实现修订记录（v1.1，2026-08-29——M4 验收时回写）

| 设计原文 | 实现现状 | 说明 |
|---|---|---|
| §2 模块名 `forensic_manifest.py` / `state_trace.py` / `session_trace.py` | `manifest.py`；state_trace 以 `shared/state.py::_trace_transition` + `recorder.transition()` 实现；无独立 session_trace | 会话级信息由 `startup_id`/`session_id` 字段承载，无独立模块必要 |
| §2 三文件 dump.json / manifest.json / environment.json | 合并为单 `dump.json` | 减少崩溃时写盘次数（Crash Handler 硬性约束优先） |
| §4.1 stale「记录后拒绝执行」 | **V14.9 起已按设计落地拦截**（M1~M3 期间为只观测）：起点 stale → `STALE_CALLBACK_DETECTED` 拒执行；chunk 检查点 → `STALE_CALLBACK_OBSERVED` 中止流；写 history 前兜底校验 | 原观测实现存在旧会话流污染新会话 history 的数据完整性风险 |
| §4.3 / §5 State Trace 注入点 | 接入低频跃迁：篇章 / 好感等级 / 拉姆阶段 / 鬼化 / 锁定（state.py `_detect_events` 跃迁点 + `set_arc`）；**SESSION_SAVE 等高频事件刻意不接** | 200 容量环形缓冲会被高频事件挤占，违背黑匣子保留关键窗口的初衷 |
| §8 M4 验收 | ✅ 2026-08-29 首案 `INC-20260829-125701-018` 走通 CASE_OPEN→CASE_CLOSED | 证据：`docs/evaluation/sessions/forensic_m4_2026-08-29/` |
| §9 案件目录（M4） | `runtime/forensic/case.py`（open_case/close_case）+ `.debug/CASE-<id>/case.md` 模板 | 协议文档已仓库化：`docs/forensic/FORENSIC_DEBUGGING_PROTOCOL.md` |
| （新增）GUI/EXE 接入 | `gui.main()` init_forensic（data/incidents）+ closeEvent/shutdown + spec 显式 hiddenimports | M1~M3 曾只覆盖 CLI，分发 EXE（打包入口=gui.py）无取证——已修复 |
