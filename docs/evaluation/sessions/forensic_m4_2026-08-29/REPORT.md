# Forensic Kernel M4 验收报告——首个真实案件 CASE_OPEN→CASE_CLOSED

**日期**: 2026-08-29
**验收口径**（设计 §8）: 首个真实案件走通 CASE_OPEN→CASE_CLOSED —— **✅ 达成**
**首案编号**: `INC-20260829-125701-018`（案件副本归档: `CASE_INC-20260829-125701-018.md`）
**复现方式**: `python docs/evaluation/sessions/forensic_m4_2026-08-29/walkthrough_m4.py`（固定 seed=7，可重复）

---

## 一、走查结果（五步全通）

| 步骤 | 结果 | 证据 |
|---|---|---|
| 1. 崩溃注入压测 | 24 轮、timeout_rate=0.3 → **18/24 崩溃（75%）**，18 个 INC 自动落盘 `incidents/` | 走查[1]；线程异常经 threading.excepthook 自动取证 |
| 2. 扫描 | `scan_incidents` 发现 18 个 PENDING | [2] |
| 3. 开案 | `open_case` → 认领 + `.debug/CASE-<id>/case.md` 生成（预填现场摘要）+ 状态 INVESTIGATING | [3] |
| 4. 读现场 | 93 事件（startup_id=20260829-125659-23324），时间线呈完整崩溃链 `MESSAGE_RECEIVED → API_REQUEST → STREAM_START → STREAM_ERROR` | [4]；**STATE_TRANSITION 1 条：`engine.favor STRANGER → FAMILIAR`（seq=17）——state_trace 端到端进证据链** |
| 5. 结案 | `close_case` → RESOLVED + case.md 结案节（结论/根因/修复）+ CASE_CLOSED 事件；首案退出 ACTIVE 扫描 | [5] |

## 二、本批次交付物（第二批：Forensic 收口）

1. **GUI/EXE 入口接入取证（研判 R1 修复）**：`gui.main()` 在 `_install_crash_handler()` 之后
   `init_forensic(<data_dir>/incidents)`（crash hook 包装并透传原 hook，crash.log 不受影响）；
   `closeEvent` 记 `WINDOW_CLOSE` + `shutdown_forensic()`；`_cancel_streaming` 记 `UI_EVENT`。
   EXE 用户侧崩溃从此有黑匣子。
2. **spec 显式 hiddenimports**：`runtime.forensic` 全子模块列入 `ReZeroTwin.spec`
   （此前全靠 bridge 顶层 import 被动跟随，改懒加载即从 EXE 消失——D2 修复）。
3. **stale callback 拦截（设计偏差修复）**：设计 §4.1「记录后拒绝执行」落地——
   起点 stale → `STALE_CALLBACK_DETECTED` 拒绝执行；chunk 检查点 stale → `STALE_CALLBACK_OBSERVED`
   中止流；写 history 前兜底校验。此前「只观测不拦截」会让旧会话流继续涌向 GUI 并落入新会话 history
   （数据完整性风险，现消除）。
4. **状态轨迹（state_trace）**：`shared/state.py` 新增 `_trace_transition` 静默助手，
   接入低频跃迁：篇章（set_arc）/ 好感等级 / 拉姆阶段 / 鬼化 / 忠诚锁定（`_detect_events` 跃迁点）。
   高频数值变化刻意不入 200 容量缓冲。
5. **M4 案件编排**：`runtime/forensic/case.py`（`open_case` / `close_case`，案件目录
   `.debug/CASE-<id>/case.md` 模板生成，防双 Agent 由 manifest.claim 保证）+
   `docs/forensic/FORENSIC_DEBUGGING_PROTOCOL.md` v1.2 仓库落地版（设计引用的外部协议文档至此入库）。
6. **测试 +7**：`tests/test_forensic_case.py`（开案/防双 Agent/结案/缺省目录/未开案结案/未知案件 6 项）+
   `test_llm_failures.py::test_stale_stream_intercepted_not_written`。全量 **174 passed**（此前 167）。

## 三、判定与遗留

- **判定**: 演练案件（mock 注入超时的预期崩溃），非产品缺陷——根因/结论已写入 case.md 结案节。
- **同跑次其余 17 个 INC** 保持 PENDING（演练产物，无需逐案调查）；如需清场可
  `mark_ignored` 或直接删除 `incidents/`（已 gitignore）。
- **已知预期噪音**: 压测阶段线程异常 traceback 会打印到 stderr（headless runner 设计如此：
  worker 内绝不捕获，捕获=线程没死=取证不触发）。
- **设计文档同步**: `forensic_subsystem_design.md` 已回写 v1.1 实现修订记录（见该文档 §11）。

## 四、下一步（移交第三批）

- 审判循环 Phase 2 回归门禁：`tools/persona_fingerprint.py`、`tools/trial_gate.py`、baselines 入库。
- 可选：Hermes cron 巡检新 INC 自动开案（协议 §7 二期，接口已就绪）。
