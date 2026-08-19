# Changelog

All notable changes to the **Re:Zero Twin System** (Ram & Rem) are documented in this file.

本项目采用语义化版本记录，重点追踪「状态机深度」与「角色灵魂完整度」的演进。

---

## [V14.4] - 2026-08-19 (来信 arc 感知——帝国篇 OOC 止血)

> 研判报告（docs/design/场景化内容密度与篇章模版池研判_2026-08-19.md）四个问题之首：letters.json 无 arc 字段，帝国篇 favor≥70 会命中宅邸深情模板（「没有您的日子蕾姆连呼吸都困难」），与 Prompt 注入的失忆疏离指令同屏冲突。本版 Step 0 止血：模板加 `arcs` 维度 + 帝国克制来信。

### Added
- **arc 匹配维度**：`LetterManager.evaluate_and_dispatch(..., arc="mansion_era")`——模板 `arcs` 字段过滤；**缺省 = ["mansion_era"]**（安全默认：内容默认宅邸专用，新 arc 内容必须显式声明；`"all"` 显式全 arc）；GUI 传 `engine.arc.value`
- **3 条帝国克制来信**（arcs:["empire_era"]，失忆疏离基调，与 Prompt 注入一致）：`empire_rem_cross_01`（CROSS_PERIOD）/ `empire_rem_days_01`（DAYS_1_3）/ `empire_ram_long_01`（LONG_ABSENCE）
- 测试 +4：帝国篇 favor 85 × 300 采样**零深情命中** / 帝国来信来自帝国模板 / 默认 arc 零回归 / 帝国无模板桶静默

### Changed
- `content/letters.json`：40 条既有模板显式标注 `"arcs": ["mansion_era"]`（共 43 条）

### 不变项
- 冷却三红线、离线五桶、发件人权重、twins 拆分、白名单插值——零改动
- 宅邸篇行为零变化（arcs 过滤对 mansion_era 全放行）

### 验收
1. pytest **87/87**（83 既有 + 4 新增；×3 连跑确认无 flaky）
2. 止血断言：帝国 arc 300 次采样永不出现「呼吸都困难/喜欢您/好想/缺了一块」
3. 后续：Step 1 注册表骨架（缓存 key 补 arc、引言粗桶对齐）待确认

---

## [V14.3] - 2026-08-07 (双子主动来信 / 问候系统)

> 离线归来时双子主动来信：按离线时长分桶（跨时段/半天/1-3天/3-7天/7天+），发件人按蕾姆好感动态加权（rem/ram/twins），纯模板插值（零 API 费用、本地/LLM 双模式一致），冷却 8h + 每日 1 次防打扰。来信优先于日更问候/轻氛围/引言（互斥）。

### Added
- **`shared/letter_manager.py`**（新）：LetterManager——模板池加载（frozen 兼容）、冷却校验（首次启动排除/8h 间隔/每日 1 次）、离线桶判定、发件人权重采样（favor <30/<70/≥70 三档）、白名单安全插值（replace 实现，模板笔误不崩）、twins 复合来信按【蕾姆】/【拉姆】拆分
- **`content/letters.json`**（新，40 条模板）：跨时段/半天/1-3天/3-7天/7天+ × rem/ram/twins × 好感低/中/高三档 + 天气变体；占位符 `{last_period}/{current_period}/{days_absent}/{hours_absent}/{weather}`
- **WorldState 三字段**：`last_period` / `last_letter_ts` / `last_letter_date`（持久化到 memory.json）；`mark_interaction()` 记录交互时段；`ensure_last_period(store)` **方案 C 回填**（字段优先，旧存档从 DB 最后消息 created_at 推导，空库回落当前时段）
- 测试：`tests/test_letter_manager.py` 12 用例（模板池/冷却红线/桶边界 8 断言/权重三档/插值白名单/twins 拆分/全链路触发/静默/回填）

### Changed
- 启动序列（`_load_history` 后）：`ensure_last_period` → 来信判定 → 触发则落库（role=rem/ram，与正常回复一致）+ 渲染 + 跳过日更问候/轻氛围/引言；未触发回落既有逻辑。优先级：**来信 > 日更问候 > 轻氛围 > 引言**

### 不变项
- 来信走 `_append_parsed_message(save=True)`：status=normal → 搜索/回忆/右键删除/LLM 上下文（restore）天然兼容
- 不写好感/事件记忆（纯展示+上下文消息）；HardStateEngine、V13/V14 全部契约零改动
- `content/` 已在 PyInstaller datas（ReZeroTwin.spec:14）——frozen 自动包含

### 验收
1. pytest **82/82**（70 既有 + 12 新增）
2. 真机待验：改系统时间/离线数小时后再开 → 双子来信；连续开两次 → 第二次不触发（冷却）；右键可删来信

---

## [V14.2] - 2026-08-07 (引用回复)

> 任意气泡可引用：右键「引用」→ 输入区引用条（可取消）→ 发送时当前轮 Prompt 注入「用户引用了…」增强针对性。引用为一次性 ephemeral——不进 history、不落库、不写 events，回忆/搜索零污染。

### Added
- **右键「引用」**：`ChatMessageWidget` / `SystemLabelWidget` 菜单项 + `quote_requested` 信号（仅 normal 且有 DB id；recalled 占位不可引用）
- **引用条**（输入区顶部，accent 左边线样式）：`↪ 回复 {sender}：{preview(≤30字)}` + × 取消
- **bridge 引用注入**：`chat` / `chat_stream` 加 `reply_to: Optional[Dict] = None`（默认 None 零感知）→ `_build_messages` 向 system prompt 追加「### 用户引用了你之前的话（仅本轮参考…）「{preview}」」（沿用首轮氛围先例）
- **双重状态校验**：发起引用时 + 发送时（`get_by_id` status）——已删/已撤 → transient「原消息已撤回，无法引用/引用已取消」
- 测试：`tests/test_quote_reply.py` 4 用例（流式/非流式注入、无引用不注入、引用不进 history）+ offscreen 1 用例（引用条显示/已撤提示/取消/发送一次性消费）

### Changed
- `LLMWorker` 加 `reply_to` 透传；`_send_message` / `_send_llm_stream` 链路携带
- 引用一次性消费：发送后（无论成功与否）清 `_quote` + 隐藏引用条

### 不变项
- 用户句 content 落库保持原文（引用标记只在 system prompt，ephemeral）→ 搜索/回忆无双份污染
- 事件记忆不因引用写入（engine 机制零改动）；本地模板模式忽略引用（不注入）
- V14.0/V14.1 全部语义（status 过滤差、删除/撤回/失败态、搜索高亮）零改动

### 验收
1. pytest **70/70**（65 既有 + 5 新增）
2. 真机待验：右键引用 → 引用条 → 发送 → 双子回复点题（如引用「蕾姆做的茶」再问细节）

---

## [V14.1] - 2026-08-07 (搜索命中词临时黄高亮)

> 搜索增强：命中词在正文内黄底高亮（主聊天 + 回忆浮层摘要同一工具函数），取消/清空搜索即全部清除。纯 UI 临时态——不写 DB、不改 status、不改 content。

### Added
- **`highlight_plain_text(text, keyword)`**（模块级纯函数）：`html.escape` 全文 → 转义后精确匹配关键词 → 黄底 span 包装（多命中全部标黄；空 keyword/未命中返回原样）；**先 escape 再高亮防注入**
- **`COLORS['search_hit'] = '#FFEB3B'`**（黄底 + 深色文字保证可读）
- `TwinChatApp.highlight_hits(keyword)`：遍历可见 widget（仅 normal 且有 DB id；recalled 占位/failed 不参与）→ label 设富文本；原文存 `_search_hit_text`
- `TwinChatApp.clear_all_highlights()`：恢复原文 + 清留存（幂等）
- **回忆浮层**：`HistoryItemWidget(record, keyword=...)`——预览摘要 + 展开全文复用同一函数（构造期渲染）
- 测试：`test_search_highlight_v141`（escape 防注入 / 多命中 / 空词 / clear 往返 / recalled 不参与）

### Changed
- 顶栏 `_do_search`：先清旧高亮 → 高亮命中词 → **定位第一条结果**（`_locate_message` 滚动 + 金色 2s，补此前"搜索不滚动"缺口）
- 顶栏搜索框 `textChanged`：清空 → clear
- `_load_history` 末尾 / `_close_history`：自动 clear（防残留）
- 黄高亮（label 内词级）与定位金色（widget 外层背景）不同层级，可叠加不互覆

### 不变项
- FTS/LIKE 检索逻辑与 `status='normal'` 过滤、HardStateEngine、bridge 契约、好感公式、删除/撤回/失败态语义——零改动
- 高亮是 UI 临时态：DB/status/content 零写入

### 验收
1. pytest **65/65**（64 既有 + 1 新增）
2. 离屏：纯函数 6 断言 + widget 级高亮→clear 往返 + recalled 不参与
3. 真机待验：搜「野外」→ 滚动定位 + 黄底高亮；清空搜索框/关浮层 → 高亮消失

---

## [V14.0.1] - 2026-08-07 (热修：撤回连带同轮助手回复)

> 真机契约抽测 T2 暴露：撤回用户句后，同轮残留助手句仍含该信息（模型可据此答出已撤内容）。修复：撤回时连带「同一次发送产生的助手回复」一并 recalled（占位），随后 `_restore_history_from_store` 剪枝——已撤轮完整退出 LLM 上下文。

### Added
- `ConversationStore.recall_turn(message_id)`：撤回用户句 + 同轮助手（`id > message_id` 且下一条 user 之前的 rem/ram/assistant 记录，system 不连带）；**不连锁后续轮次**
- 测试 2 例：连带范围（同轮助手 recalled、后续轮 normal）/ 撤后 history 不含用户原文与同轮助手原文（后续轮保留）

### Changed
- `_on_recall_request`：`update_status` → `recall_turn`，遍历 `_mark_widget_recalled` 置占位

### 不变项
- 3 分钟窗口、删除语义、failed 态、好感/其它功能零改动；V14.0 三条查询过滤差不变

### 验收
1. pytest **64/64**（62 既有 + 2 新增）
2. 契约补验（真机可选）：撤回含生日的轮次后追问——模型不再能由同轮残留答出

---

## [V14.0] - 2026-08-07 (消息删除 · 3 分钟撤回 · 取消后失败态)

> 对话时间线治理：删除（任意角色）、撤回（仅用户、created_at 起 3 分钟内）、取消流式后用户句标记「未送达」。全部软状态（status 字段），主聊天/回忆浮层/搜索/LLM 上下文四路径过滤差统一。

### Added
- **`messages.status` 软状态字段**（normal/recalled/deleted/failed）+ 旧库幂等迁移（PRAGMA 检查 + ALTER）；`ConversationStore.update_status(message_id, status)`
- **右键菜单**（项目首个 QMenu）：`ChatMessageWidget` 撤回（仅 user 且 normal）/删除；`SystemLabelWidget` 删除（瞬态标签无 id 无菜单）；均带 QMessageBox 确认防误触
- **撤回占位**：widget 保留时间线位置，文本换「（已撤回）」+ 45% 透明度轻样式；超时（>3 分钟）拒绝并 transient 提示
- **取消后失败态**：`_pending_user_widget` 机制——取消流式时本轮用户句 `status=failed` + 「（未送达）」弱化标记；可再右键删除
- **测试**：`tests/test_message_status.py` 7 用例（迁移/过滤/搜索/剪枝）+ offscreen 1 用例（撤回占位/超时/删除移除/取消 failed）

### Changed
- **三条查询的 status 过滤差**（代码注释已写明）：
  - `get_recent` / `get_messages_since`（GUI 展示：主聊天+回忆）：normal + failed + recalled，排除 deleted
  - `search`（FTS + LIKE 双通道）：仅 normal（撤回/删除/未送达正文不可搜）
  - `bridge._restore_history_from_store`（LLM 上下文）：仅 normal（failed/recalled/deleted 均不进 Prompt）
- `_load_history`：按 status 渲染（recalled 占位 / failed 标记）
- 删除/撤回后 `_prune_bridge_history()` → `_restore_history_from_store()` 重建——下一轮 Prompt 不引用已删/已撤正文

### 不变项
- HardStateEngine 好感公式、V13 超时/取消/history 契约、parse 分段、Vignette 零改动
- 删除/撤回为软状态：DB 保留行与 id（定位/摘要 msg_end_id 不炸）；FTS 行不动，命中由查询侧过滤
- 不做：引用、搜索高亮、主动问候、好感改动

### 验收
1. pytest **62/62**（54 既有回归 + 8 新增）
2. 离屏：撤回占位 + 超时拒绝 + 删除移除 + 取消 failed（临时 DB，未碰正式 data/）
3. 真机待验：右键菜单手感、3 分钟窗口体感、取消后「未送达」标记

---

## [V13.1] - 2026-08-07 (好感增长曲线最小修复：蕾姆日常陪伴通道 · 拉姆不再无条件涨)

> 用户反馈「蕾姆好感长期不涨、拉姆曾反超」。Step 1 诊断（离屏 7 项断言）坐实：**规则不对称**——蕾姆无日常增长通道（普通友善 Δ=0），拉姆在本地模式却无条件每轮 +1。本版只补「陪伴通道」+ 删一处无条件调用，不动公式/风控/解析/Vignette。

### Added
- **蕾姆陪伴通道**（`HardStateEngine.update()`）：非负面且无其它增减通道命中时 `favor +1`（覆盖普通友善 / QUICK / 提拉姆等日常轮）；**5涨3停**防刷（`_companion_gains`/`_companion_cooldown`，重启重置，非存档字段）
- **测试固化**：`tests/test_favor_growth.py` 6 用例（20 轮友善可观察增长 / 夸奖蕾姆 ≥ 拉姆 / 危险后恢复 / 防刷上限 / 本地模式拉姆不再无条件涨 / 存档一致）

### Changed
- `local/twin_system.py` `interact()`：删除无条件 `on_rem_treated_well(1)`——拉姆正向增长改由 `engine.update` 的 PRAISE / MENTION_RAM 通道驱动（与 LLM 模式行为对齐，修复「10 轮普通对话拉姆 8→18 反超蕾姆 15」）；边界试探 `on_rem_hurt(3)` 保留
- `llm/bridge.py` `chat_stream` 生成器：新增 `except` 分支——`cancel_stream()` 关闭底层 socket 后，进行中迭代抛出的 `httpx.ReadError`（WinError 10038）在 `_stream_cancelled` 时**静默吞掉**（V13.0「取消=安静」契约）；真实异常继续上抛。**真机 LLM 抽测 A3 暴露**：此前取消路径以异常结束（GUI 被 disconnect+worker except 兜底不崩，但单线程/测试场景会炸）

### 不变项
- 高光/风控 Δ 全部不变：夸奖 +2/+1、从零 +3/+1、温情 +1、高危 -12/-6、边界 -3、替代品 -1
- V13.0 超时/取消/history 契约、解析分段、Vignette、Validator 零改动
- 陪伴通道明确排除负面：VENT/SELF_DOUBT/PROCRASTINATE/BOUNDARY/DANGER 意图、高危词、替代品/不如姐姐、任何温情词命中（含「不太开心」否定式——V9.2.6 语义回归守护）、首次名字

### 验收
1. `tests/test_favor_growth.py` 6/6；冒烟 **34/34**；`test_llm_failures` 10/10；离屏 4/4
2. 回归守护：`test_keyword_judgment_v926`（「我今天不太开心」不加分）在陪伴通道下保持绿——修复过程中曾 33/34，经「温情词命中即排除」修正后恢复
3. 真机待验：20 轮日常对话后蕾姆面板数字应有肉眼可见增长；拉姆面板不再只靠聊天就涨

---

## [V13.0.1] - 2026-08-07 (热修：流式取消失效——空输入早退挡住取消入口)

> 真机缺陷：流式中点发送键（应为「取消」）无反应，内容继续生成。根因：`_send_message` 先取文本、空输入即 return，而发完消息后输入框已清空 → 取消分支永远到不了。

### Changed
- `_send_message()`：`_streaming_active` 取消判定**移到**空输入判定之前（取消优先）；非流式空输入行为不变（仍安静 return）

### 不变项
- bridge / HardStateEngine / 解析分段 / Vignette / V13.0 全部契约（超时、fallback 不写 history、cancel_stream）零改动
- 取消后三层忽略保证不变：teardown 先 disconnect（主防线）→ `_stream_cancelled` 生成器提前结束 → 引用置空

### 验收
1. `test_llm_failures.py` 10/10（含取消用例回归）；冒烟 34/34；离屏 **4/4**（空输入取消回归已固化进 `test_ui_offscreen.py`，非一次性脚本）
2. 真机：流式中输入框留空直接点「取消」→ 立即停字、临时泡消失、footer「已取消」、gui.log 出现「用户取消流式回复」；随后可立即再发

---

## [V13.0] - 2026-08-06 (稳定版 P0：LLM 超时 · 线程收尾与取消 · 兜底不污染 history)

> 产品级验收（真实 DeepSeek 实测，¥0.0661）坐实三缺陷后补的工程铠甲：LLM 超时兜底、流式可取消、校验失败不再「失忆」且不污染 LLM 上下文。AI 层（人格/记忆/世界观）零改动。

### Added
- **LLM 请求超时**：client 级 `timeout`（`REZERO_LLM_TIMEOUT` 环境变量，默认 45s），覆盖 chat / chat_stream / raw_completion 全部调用；超时走既有异常路径（角色文案 + 不写 history）
- **流式取消**：流式中发送键变「取消」；`LLMWorker.cancel()` → `bridge.cancel_stream()`（置标志 + 关闭底层 httpx 流）→ 生成器静默提前结束；`_teardown_llm_thread()` 统一收尾（断开信号 → 取消 → requestInterruption → quit+wait(2s) → terminate 仅作最后手段）
- **线程收尾接入三处**：closeEvent（先收尾再存状态）、`_switch_mode`（流式中切模式先收尾，修复旧 worker 错对象读）、`_send_llm_stream` 重入（原手写 quit/terminate 块替换为统一收尾）
- **流式校验结果回传**：bridge 新增 `_last_stream_ok` / `_stream_fallback_text`；GUI `_on_stream_finished` 校验失败时丢弃未校验全文、清临时泡、展示 View-Only 回避文案
- **测试固化**：`tests/test_llm_failures.py` 10 用例（4 类异常 mock + 兜底不污染 history + 取消 + 文案防回归，零 API 费用）

### Changed
- `_fallback_reply()` 文案：失忆感「刚才的话，蕾姆不太确定」→ 角色内回避「……这个话题，蕾姆想先放一放。您愿意说点别的吗？」（T1-05）
- `_generate_validated()` 返回 `(reply, is_fallback)` 二元组；`chat()` 兜底分支不写 history、不清首轮氛围、不写场景冷却（`mark_interaction` 保留）
- `_parse_twin_reply()` 新增 `save` 参数（默认 True）；兜底展示走 `save=False`，不落 ConversationStore
- `_send_message()` 流式中原「正在回复中」提示改为取消动作

### 不变项
- HardStateEngine 好感/独立度/鬼化/拉姆阶段数值公式零改动
- `parse_twin_segments` / `_streaming_segments` 分段规则零改动
- 场景冷却、WorldState 事件生成、Vignette L0–L3 架构零改动；frozen 安全引言路径不变
- API 异常路径（断网/超时）文案保留「没听清」（语义真实），仅校验失败兜底改回避

### 验收
1. `tests/test_llm_failures.py` 10/10（含 T1-05 回归：兜底不写 history）
2. 冒烟回归 34/34；UI 离屏 3/3
3. 离屏集成验证 11/11（teardown 幂等 / 取消状态恢复 / 校验失败分支清泡+回避文案 / 正常分支回归）
4. 真机：流式中点发送键立即取消；流式中关窗 ≤2s；切模式无僵尸回调

---

## [V12.1] - 2026-08-03 (对话回合视觉分组：同角色紧 · 换人松 · 阵营段落)

> 用最小布局参数做出「对话回合感」：同一 speaker 连续消息收紧、换人略松、角色↔用户有段落感。不改文案、不改解析、不动效主逻辑。

### Added
- **回合间距 helper**（`_turn_top_margin` / `_apply_turn_rhythm`）：`chat_layout` 基线 spacing 由 `md(12)` 下调至 `xs(4)`，回合关系由**本条外层 top margin** 表达（只动 widget 外层 margins，不碰 Bubble 内部）。判定顺序（O(1) 回看 `itemAt(count-2)`，最多跳过 8 个 streaming 临时泡）：

| 关系 | top margin | 总间距 |
|---|---|---|
| 首条 / 无上一条 | `sm`(8) | ≈17px |
| 涉 system / vignette（中性） | `sm`(8) | ≈17px |
| 同 speaker 连续（rem→rem / ram→ram / user→user） | `xs`(4) | ≈13px |
| 阵营切换（角色↔user） | `lg`(16) | ≈25px |
| 角色换人（rem↔ram） | `md`(12) | ≈21px |

- **streaming 时序无缝**：临时泡加 `objectName="__streaming_temp__"` 标记；临时泡插入即带正确间距；正式泡插入时**跳过临时泡**判定（顶替时 top margin 与临时泡一致 → 删临时泡零跳变）；多临时泡草稿之间按标准换气。
- **历史回放自动应用**：`_load_history` 走 `_append_parsed_message` 单点，30 条批量自动带回合节奏（与 V12.0 `animate=False` 正交：margins 是布局层、opacity 是渲染层）。

### Changed
- `_setup_ui`：`chat_layout.setSpacing(SPACING['md'] → SPACING['xs'])`
- `_append_parsed_message`：插入前调用 `_apply_turn_rhythm`（**插入后调用会误把刚插入的 widget 当作上一条**——该 bug 在离屏用例中被捕获并修复，临时泡因 objectName 跳过逻辑恰好免疫）
- `_insert_streaming_bubble`：objectName 标记 + 插入前计算间距

### 不变项
- HardStateEngine / Prompt / Validator / 场景冷却零改动
- `parse_twin_segments` / `_streaming_segments` 分段规则零改动
- HistoryOverlay 业务逻辑零改动；BubbleWidget 内部结构零改动
- V12.0 四件套（描边说话态 / 气泡入场 / 状态栏呼吸 / `REZERO_DISABLE_UI_MOTION` 开关）行为不变
- 回合间距是布局属性，**不受动效开关控制**（关动效后回合感仍在）

### 验收
1. 离屏用例 17/17：首条/同角色/换人/阵营/system 中性各档 top margin、临时泡标记、正式泡跳过临时泡判定、顶替零跳变、删临时泡后不变、多临时泡换气、上限裁剪（85 条→≤80）后判定仍正确
2. 冒烟回归 34/34 通过
3. 人工验收（真机）：连续蕾姆两段更紧、蕾姆→拉姆明显换气、用户↔角色有段落感、幕间卡不打断节奏、流式全程无间距跳变

---

## [V12.0] - 2026-08-03 (视觉第一波：头像说话态 · 气泡轻入场 · 状态栏呼吸)

> 本阶段从「话正确」转向「看起来活着」，但保持克制：只做三类可感知、可回滚的表现增强，不引入新 UI 框架、不重做布局与 Design Tokens。

### Added
- **侧栏说话态描边**（`CharacterPanel.set_speaking`）：流式时当前说话人一侧的 `avatar_frame` 立绘框描边由 `border_subtle` 1px 切换为角色色（rem 冰蓝 / ram 蔷薇）2px。**幂等**：speaker 未变化不重复刷 QSS（`_current_speaker` 比较），每轮流式最多 2–3 次样式重设，高频 token 无抖动。
- **正式消息泡轻入场**（`_append_parsed_message` 新增 `animate=True` 参数）：正式 rem/ram/user 泡插入时 `QGraphicsOpacityEffect` + `QPropertyAnimation` opacity 0→1，**200ms / OutCubic**，整条消息（头像+名字+气泡）一体淡入。动画结束即卸载 effect（防离屏渲染残留），effect/动画 parent 均为气泡自身（上限删除 `deleteLater` 连带销毁）。
- **状态栏呼吸**（`_mode_label`）：`QSequentialAnimationGroup` 双程往复，**opacity 0.85↔1.0，单程 2000ms（周期 4s），InOutSine**，无限循环。思考中（`_send_message` 有效对话发出）`pause()` 停在当前值，回复完成/出错（`_finish_reply`）`resume()`；不改变 RichText 信息结构与语义分层。
- **统一动效开关**：模块级 `ENABLE_UI_MOTION`，环境变量 `REZERO_DISABLE_UI_MOTION=1` 可整体关闭（对齐 `REZERO_DISABLE_VIGNETTE` 先例）。关闭时呼吸组不创建、入场动画短路、描边 QSS 不刷新（状态跟踪照常，开/关行为一致）。
- 所有动效路径 try/except + `_log`，异常只记日志，不拖垮事件循环（含 `_play_entrance_animation(None)` 异常注入验证）。

### Changed
- **历史批量回放跳过动画**：`_load_history` 传 `animate=False`（30 条批量零动画，冷启动不卡）。
- **说话态复位三路径**：`_clear_streaming_bubbles`（finished/error/重入共用）+ `_finish_reply`（兜底，幂等）统一复位双面板。

### 不变项
- HardStateEngine 好感/独立度/鬼化/拉姆阶段计算零改动
- `parse_twin_segments` / `_streaming_segments` / `_on_stream_token` 分段规则零改动（说话态仅读取 `segments[-1][0]`）
- 场景冷却与 Validator 主策略、Prompt、数值零改动
- 无新 UI 框架；无边框窗口与 Design Tokens 数值不动
- streaming 临时泡 / system 灰标签 / vignette 幕间卡均无入场动画
- 本地（同步）模式不点亮说话态（无「正在说话」过程），`_finish_reply` 兜底复位

### 验收
1. 离屏组件验证 17/17：呼吸组创建与 pause/resume、描边 True/False 切换与幂等、rem/ram 说话切换与 None 复位、正式泡有入场 effect、`animate=False` 与 system 无 effect、动画结束 effect 卸载、异常注入不崩溃
2. 开关关闭验证 5/5：`REZERO_DISABLE_UI_MOTION=1` 下呼吸组未创建、正式泡无 effect、描边 QSS 不刷、状态跟踪照常
3. 冒烟回归 34/34 通过
4. 人工验收（真机）：流式蕾姆→拉姆切换描边点亮；新消息泡 200ms 淡入；历史加载无动画；footer 呼吸不抢对话注意力；思考中呼吸暂停

---

## [V11.12] - 2026-08-03 (开场幕间卡：冷启动生命感视觉升级)

### Added
- **`SystemLabelWidget` 新增 `variant` 参数**：`"system"`（默认，样式不变）/ `"vignette"`（宅邸幕间卡）。vignette 变体采用 accent 金色派生（`rgba(201,169,110,0.06)` 淡底 + `1px solid rgba(201,169,110,0.18)` 细边 + `text_secondary` 字色 + 中圆角 + 加大 padding），视觉层级定为：正式角色泡 > streaming 草稿泡 > vignette 幕间卡 > system 灰标签。金色为中性色（非角色色），避免幕间叙述与双子台词混淆。
- **开场引言使用 vignette 幕间卡**：`_on_done` 落卡时 `variant="vignette" + force_center=True`，占位「✨ 正在感知宅邸的氛围…」保持 system 灰条，替换瞬间产生可见层级跃升。
- **日更问候共用 vignette 变体**：`_show_daily_greeting` 与引言同属「宅邸幕间」语义，统一视觉族；文案、触发、持久化逻辑不变。

### Changed
- **`_append_parsed_message` 返回创建的 widget**（原返回 `None`）：既有调用方均不接收返回值，向后兼容；供占位引用删除等场景使用。
- **引言占位删除改为持有引用**：`_generate_vignette` 捕获占位 widget 引用，`_on_done` 直接 `removeWidget + deleteLater`，废弃脆弱的 `chat_layout.itemAt(count-2)` 位置删除（期间若有其他 widget 插入会误删）。附带修复：非 frozen LLM 路径 error 回调同样走 `_on_done`，占位不再残留为孤儿灰条。

### 不变项
- `shared/vignette.py` 生成逻辑（L0-L3 多级兜底）零改动
- `llm/bridge.py` 首轮氛围注入链路（`set_opening_atmosphere` → 首轮 system_prompt → 一次性消费）零改动
- HardStateEngine 好感公式 / 场景冷却阈值 / Validator 主策略
- V11.11 流式分人切泡 / `_parse_twin_reply` 最终落库 / 临时泡清理逻辑
- frozen EXE 安全路径（主线程 L2/L3，不建 QThread 不调 LLM）结构不变
- View-Only 铁律：引言/问候仍 `save=False`，不进 ConversationStore、不进 LLM history
- 续聊卡 / 欢迎语 / 轻氛围 / /status / 搜索结果等保持 system 灰标签不变

### 验收
1. 空库冷启动：占位灰条 → 金色幕间卡替换，无残留占位、无误删其他 widget
2. 换日有历史：日更问候呈 vignette 卡，`last_greeting_date` 照常写入
3. 同日重开：轻氛围仍为灰条，不出现 vignette 卡，不刷屏
4. 发第一句：V11.11 流式分人切泡、临时泡清理、正式泡身份均不回归
5. 历史 DB 不被引言/问候污染（save=False）
6. 冒烟回归 34/34 通过；离屏组件测试验证 vignette 样式与 system 默认样式隔离

---

## [V11.11] - 2026-08-03 (TwinStreamParser：流式过程中按说话人切泡)

### Added
- **`match_speaker_tag` 公共标签匹配函数**：从 `parse_twin_segments` 中抽取行首说话人标签匹配逻辑为独立函数，返回 `(tag_type, content)`。`tag_type` 为 `"rem" | "ram" | "system" | "unknown" | None`，`parse_twin_segments` 与 `_streaming_segments` 共用，确保流式预览与最终落库语义完全一致。
- **`_streaming_segments` 流式分段函数**：与 `parse_twin_segments` 语义一致的流式版本。末行以 `【` 开头且未出现 `】` 时视为标签不完整，跳过该行等后续 token 补全。返回段是 `parse_twin_segments(buffer)` 的子集（最多缺少末行），流式过程中可能为空，不做兜底。
- **`_streaming_bubbles` 多临时泡列表**：替换单一 `_streaming_bubble` 为列表，支持同时存在多个 streaming 泡（按说话顺序排列）。`_on_stream_token` 按 `_streaming_segments` 结果增泡+更新末泡纯文本，识别到说话人切换时自动新建对应对话人的 streaming 泡。
- **`_clear_streaming_bubbles` 统一清理方法**：`finished` / `error` / `重入` 三条路径共用，遍历删除所有临时 streaming 泡并清空列表，防止孤儿残留。
- **冒烟测试**：新增 3 组测试——`test_parse_twin_regression_v1111`（解析回归：基本分段/续行继承/系统并入/无标签默认/空兜底/未知标签跳过）、`test_match_speaker_tag_v1111`（标签匹配覆盖）、`test_streaming_segments_v1111`（流式分段：完整一致/末行不完整跳过/纯不完整标签空列表/续行继承/系统并入），34/34 通过。

### Changed
- `parse_twin_segments` 重构为使用 `match_speaker_tag`，行为不变（缓冲+flush、speaker 继承、`【系统】` 并入角色、默认 rem、空兜底）。
- `_on_stream_token` 重写：累积 token 到 buffer 后调用 `_streaming_segments` 分段，按段数动态增泡，各泡只显示纯文本（不含标签）。
- `_on_stream_finished`：临时泡清理改用 `_clear_streaming_bubbles()`；正式落库仍走完整 buffer + `_parse_twin_reply`，保证 role/sender 一致性。
- `_on_stream_error`：临时泡清理改用 `_clear_streaming_bubbles()`。
- `_send_llm_stream`：重入保护改用 `_clear_streaming_bubbles()`。
- `_insert_streaming_bubble`：注释明确临时泡全部 `save=False`，不写 ConversationStore。

### 不变项
- 双 Agent 架构（不做并行生成）
- 好感公式 / 场景冷却语义 / Validator 主策略
- V11.10.0 解析铁律（角色台词不得进 system）
- `_parse_twin_reply` 最终落库逻辑（完整 buffer 解析 + 高光标记）
- 本地模式（非流式）行为不变

### 验收
1. 模型先输出蕾姆段再拉姆段时：先出现蕾姆 streaming 泡打字，再出现拉姆 streaming 泡打字
2. 结束后正式分色泡正确；历史 role/sender 正确；无 system 误标
3. 无前缀续行、`【系统】` 行行为与 V11.10 最终解析一致
4. 断网/连发：无临时泡残留
5. 场景高光仍落在最终最后一个 rem 段
6. V11.10 / V11.10.1 相关冒烟回归通过（34/34）

---

## [V11.10.1] - 2026-08-03 (流式预览弱草稿态 + 临时泡清理修复)

### Fixed
- **`_on_stream_error` 临时泡残留**：错误路径原仅 `_streaming_bubble = None`，不删 widget，API 超时/断网时临时泡孤儿残留在聊天区。补加 `setParent(None)` + `deleteLater()`，与 finished 路径同等清理。
- **`_send_llm_stream` 重入残留**：用户连续发送时旧临时泡未被清理。新开流式前先检查并强制删除旧 `_streaming_bubble`。
- **流式结束跳变**：`_on_stream_finished` 原先删临时泡再建正式泡，中间有空白帧。改为先 `_parse_twin_reply` 插入正式泡，再删临时泡，消除空白帧跳变。

### Added
- **streaming 弱变体**：`BubbleWidget` / `ROLE_BUBBLE_STYLES` 新增 `variant="streaming"`。rem/ram 各加 `stream_bg`（透明度 0.04，normal 的 1/2.5）、`stream_border`（2px + alpha 0.15，normal 为 3px + 0.45）、`stream_fg`（`text_secondary` 暗一档）。顶部「生成中…」弱标签（`text_muted` 灰，8pt）。仍保留角色色体系（冰蓝底/蓝头像），不灰成 system。
- **`_insert_streaming_bubble` 传 `variant="streaming"`**：临时泡创建时即用弱样式，用户一眼可辨「这不是定稿」。

### Changed
- `_on_stream_finished` 时序调整：先解析插入正式泡 → 再删临时泡（原为先删后建）。
- `_on_stream_error` 清理顺序：先清临时泡 → 再显示 system 错误消息（原为直接显示错误，不清理）。
- `_send_llm_stream` 重入保护：断开旧信号后、初始化新 buffer 前，先清理旧临时泡。

### 不变项
- V11.10.0 解析规则（`parse_twin_segments` 缓冲+flush）
- 场景检测 / 冷却 / `_active_scene_id` 时序
- 好感公式 / Validator 主策略
- 临时泡仍 `save=False`，不进 ConversationStore
- 本地模式（非流式）行为不变

### 验收
1. 流式中：底色极淡、边线细弱、文字暗色、「生成中…」标签，明显弱于正式泡
2. 结束后：正式泡先出现，临时泡紧接消失，无空白帧跳变
3. API 错误：临时泡被清理，显示 system 错误消息，无孤儿残留
4. 用户连发：旧临时泡被清理，无残留
5. 场景轮：高光仍打在最后一个 rem 段，临时泡本身无高光
6. V11.10.0 冒烟回归 48/48 + 旧冒烟 31/31 通过

---

## [V11.10.0] - 2026-08-03 (角色多气泡 + 高光一幕 + 情感场景包)

### Fixed
- **LLM 台词误分类为 system**：`_parse_twin_reply` 原将无前缀行直接标为 `system`，导致 LLM 生成的角色台词（如承诺段）被错误显示为系统消息。新增 `parse_twin_segments` 缓冲+flush 模型，无前缀行继承当前 speaker（默认 rem），`【系统】` 标签内容提取后并入角色段，禁止 LLM 台词降级 system。
- **bridge 错误返回 `【系统】` 前缀**：`chat()` / `chat_stream()` 异常时原返回 `【系统】API 调用失败：{e}`，经解析器后误显示为角色台词。改为返回角色格式 `【蕾姆】: "……蕾姆好像没听清。请再说一次好吗？"`，错误详情写入日志。
- **GUI 错误走解析器**：`_send_sync` / `_on_stream_error` 的异常路径原将错误文本传入解析器。改为直接调用 `_append_parsed_message("系统", ..., "system")` 走本地 system 标签，不经解析器。

### Added
- **多气泡解析**：`parse_twin_segments` 按 `【蕾姆】`/`【拉姆】` 标签拆分为独立段，每个新标签开启新气泡；无前缀续行拼入当前段。空输入兜底为 `[("rem", "……")]`。
- **高光变体**：`BubbleWidget` / `ChatMessageWidget` 新增 `variant="highlight"` 参数，角色色不变，左边线加粗（3px→5px）+ 底色增强 + 顶部「约定」弱标签。`ROLE_BUBBLE_STYLES` 各角色新增 `hl_border` / `hl_bg` 字段。高光默认打在本轮最后一个 rem 段。
- **情感场景检测**：`ReZeroLLMBridge` 新增 `_detect_scene` 方法，互斥优先级 `breaker > identity > hug > headpat`。好感门槛：breaker/identity≥DEAR(3)，hug/headpat≥CLOSE(2)。关键词 + `engine._is_negated` 检测否定句（如「不是替代品」）。
- **场景冷却**：`WorldState` 新增 `scene_cooldowns: Dict[str, str]` 字段，持久化到 `save_dict` / `load_or_create`。`_is_cooled_down` 检查 24h 冷却期，`_write_scene_cooldown` 在成功生成后写入时间戳。
- **Prompt 场景短节**：`PromptBuilder.build` 新增 `scene_id` / `ram_witness` 参数。`SCENE_GUIDES` 字典为四个场景注入引导文案；`ram_witness=True` 时附加拉姆见证提示。输出格式新增多段格式指导 + 禁止 `【系统】` 标签输出角色台词的约束。
- **冒烟测试**：新增 `smoke_v11_10_0.py`，覆盖解析四类用例（标准双子/续行/系统不降级/多段同角色）+ PromptBuilder 新签名 + WorldState 持久化 + 场景检测逻辑，48/48 通过。

### Changed
- `_parse_twin_reply` 改用 `parse_twin_segments` 拆段，循环渲染为独立 `ChatMessageWidget`；highlight 标记最后一个 rem 段。
- `_send_sync` / `_on_stream_finished` 读取 `bot._active_scene_id` 决定是否启用高光，消费后置 None。
- `chat()` / `chat_stream()` 成功生成后调用 `_write_scene_cooldown`；校验失败时清除 `_active_scene_id` 避免 GUI 误标高光。

### 不变项
- 好感公式 / HardStateEngine 数值逻辑
- 旧 DB system 记录不迁移
- `BubbleWidget` 核心结构（仅加 variant 分支，不重构）
- `ResponseValidator` 校验规则

---

## [V11.9.2] - 2026-08-03 (轻氛围/状态栏与 period·weather·event 语义对齐)

### Fixed
- **轻氛围 event 冲突**：`_show_ambient_line` 原直接拼接 `period · weather · active_event`，event 含写死时段/天气词时与当前 period/weather 语义矛盾（如：上午+阴沉却显示"午后的阳光特别好…"）。改为调用 `event_compatible` 检测，不相容则省略 event 段，日志记录 skip 原因。
- **状态栏 event 冲突**：`_update_status_bar` 右侧 ram_part 原无条件追加 event 摘要，同样存在冲突问题。改为调用 `event_compatible` 检测，不相容则静默省略（状态栏高频刷新不打日志避免刷屏）。
- **日更问候冲突检测统一**：`_show_daily_greeting` 原内联 `WEATHER_EVENT_CONFLICT` 关键词匹配（仅检测天气冲突），改为调用 `event_compatible` 统一入口，同时覆盖天气冲突和时段冲突。

### Added
- **`event_compatible(period, weather, event) -> bool`**：模块级共用函数，供日更问候/轻氛围/状态栏三处调用。检测两类冲突：
  - 天气冲突：event 含当前天气对应的冲突关键词（沿用 V11.9.1 `WEATHER_EVENT_CONFLICT`）
  - 时段冲突：event 含 7 时段词 + "入夜"别名，且与当前 period 不一致
- **`PERIOD_KEYWORDS`**：时段关键词常量表，含 `["清晨", "上午", "午后", "下午", "傍晚", "夜晚", "深夜", "入夜"]`。"入夜"视为"夜晚"/"深夜"的别名，不与这两个时段冲突。

### Changed
- **`_show_ambient_line`**：event 段拼接前调用 `event_compatible`，不相容则跳过并打日志。
- **`_update_status_bar`**：event 段拼接前调用 `event_compatible`，不相容则静默跳过。
- **`_show_daily_greeting`**：内联冲突检测替换为 `event_compatible` 调用，日志增加 `period=` 字段。

### 不变项
- `EVENT_POOL` / `_pick_active_event` / state.py（不改事件池和确定性选择逻辑）
- `last_greeting_date` 触发逻辑
- 轻氛围规则（`_show_ambient_line` 展示条件）
- 好感/Prompt/Validator/状态机数值
- save=False（轻氛围/日更问候不进 ConversationStore）

### 验收方法
1. 改 `data/memory.json` 中 `world_state.period` 为 `"上午"`、`weather` 为 `"阴沉"`，确保 `active_event` 含"午后的阳光" → 轻氛围显示 `上午 · 阴沉`（无 event），日志有 skip 记录
2. 状态栏右侧 ram_part 不含冲突 event 摘要
3. 改 `period` 为 `"午后"`、`weather` 为 `"晴朗"` + 同一 event → 轻氛围显示完整 `午后 · 晴朗 · 午后的阳光…`
4. 改 `period` 为 `"夜晚"` + `active_event` 含"入夜" → 相容，event 正常显示
5. 冒烟测试 31/31 通过

---

## [V11.9.1] - 2026-08-03 (日更问候语义对齐 + 居中装饰框)

### Fixed
- **问候文案与天气冲突**：原模板骨架内含写死天气/时段词（如"上午"模板出现"阳光已经照进走廊了"，阴沉天气下语义矛盾）。改为 `GREETING_TEMPLATES` 表驱动骨架，天气由 `WEATHER_CLAUSES` 白名单注入，骨架本身不含任何天气/时段词。
- **装饰线左对齐**：`━ ✦ ━` 上下装饰线在多行文本下默认左对齐。`SystemLabelWidget` 新增 `force_center` 参数，日更问候多行文本强制 `Qt.AlignCenter` 居中，其它系统消息默认行为不变。

### Added
- **`GREETING_TEMPLATES`**：7 时段骨架模板，仅含 `{weather_clause}` / `{event_clause}` 占位符，不含写死天气词。
- **`WEATHER_CLAUSES`**：覆盖 `WorldState.WEATHERS` 全部 5 种天气的自然语言从句；未知天气中性兜底（空串）。
- **`WEATHER_EVENT_CONFLICT`**：天气 ↔ active_event 语义冲突关键词表。大雨/阴沉/小雨 三种天气下，若 event 含冲突关键词（阳光/晒/花园/晾晒/白布/温暖等），跳过 event 拼接并打日志。
- **`SystemLabelWidget.force_center`**：构造参数，`True` 时强制多行文本居中对齐。
- **`_append_parsed_message.force_center`**：透传参数，默认 `False`，仅日更问候传 `True`。

### Changed
- **`_show_daily_greeting` 重写**：模板表驱动 + 天气白名单注入 + event 冲突检测。日志增加 `weather=` 字段。
- **event 拼接逻辑**：原 `event = active_event or "今日并无特别的事"`（空时硬编码兜底文案）→ 改为空 event 不拼接从句（骨架已自足）。

### 不变项
- `last_greeting_date` 触发逻辑（三分支：空库/换日/同日）
- 轻氛围规则（`_show_ambient_line`）
- 好感/Prompt/Validator/状态机数值
- 引言完整生成路径（空库 L0-L3）
- save=False（问候不进 ConversationStore）

### 验收方法
1. 改 `data/memory.json` 中 `world_state.weather` 为 `"阴沉"`，删除 `last_greeting_date` 值，重启 EXE → 问候不得出现"阳光"/"晒"
2. 改 `world_state.weather` 为 `"大雨"` + `active_event` 含"花园"/"晾晒" → 日志出现冲突跳过记录，正文不含 event
3. 改 `world_state.period` 为 `"上午"` → 问候不得出现"午后"/"深夜"
4. UI 上 `━ ✦ ━` 上下装饰线视觉居中框住正文
5. 同日二次启动不重复日更问候；轻氛围规则保持 V11.9.0 结论

---

## [V11.9.0] - 2026-08-03 (自然日首次问候 + 同日轻氛围)

### Added
- **日更问候**：自然日变化且今日尚未问候时，按当前 period 展示一次短文问候（2-4句女仆问候风格），写入 `last_greeting_date` 并立即持久化，同日不重复。问候正文带 weather + active_event，不额外打轻氛围避免刷屏。
- **同日轻氛围**：同日有历史重开时展示一行 `period · weather · active_event`（save=False，View-Only）。空库完整引言时不重复打。
- **`last_greeting_date` 字段**：`WorldState` 新增持久化字段（`"YYYY-MM-DD"`），`save_dict` + `load_or_create` 完整读写。

### Changed
- **引言触发逻辑重写为三分支**（`gui.py` `__init__`）：
  - 空库（`conv_store.count() == 0`）→ 完整引言路径（V10.4 L0-L3 多级生成，保留不变）
  - 日历日变化（`last_greeting_date != today`）→ 日更短问候（不依赖 mode，不调用 LLM）
  - 同日重开 → 无日更问候，有轻氛围
- **废除 `days_since_last > 0` 作为引言/问候触发条件**：改用本地日历日比较（`last_greeting_date != today_str`）。`days_since_last` 保留供其他系统使用，不修改其计算逻辑。

### 日志探针
- `day_changed=True today=YYYY-MM-DD last=YYYY-MM-DD`：日历日变化
- `already_greeted today=YYYY-MM-DD last=YYYY-MM-DD`：同日已问候
- `日更问候已展示: period=X date=YYYY-MM-DD`：问候展示完成
- `轻氛围已展示: X · Y · Z`：轻氛围展示
- `换日：日更问候已含天气，跳过轻氛围避免刷屏`：换日跳过轻氛围

### 不变项
- HardStateEngine 好感数值规则、Prompt 语义、Validator 不改。
- `days_since_last` 计算逻辑不改（供其他系统使用）。
- `_generate_vignette` 完整引言路径不改（空库仍走 V10.4 L0-L3）。
- 续聊卡逻辑不改（`_show_resume_card` 仍按 session 摘要 + count 触发）。
- build.ps1 dist/data 备份还原策略不改。
- View-Only：日更问候/轻氛围均 `save=False`，不进 ConversationStore。

---

## [V11.8.5] - 2026-08-02 (任务栏图标二次修复：addFile 多尺寸 + show 后刷新 + frozen 兜底)

### Fixed
- **任务栏图标仍未显示自定义图标（V11.8.4 后残留）**：V11.8.4 设置了 AUMID 且 `isfile=True`，但任务栏仍显示默认图标。根因推测为 Qt 单文件 ICO 加载时未向任务栏提供各尺寸位图，且 `show()` 前的 `setWindowIcon` 可能未被任务栏捕获。

### Changed
- **QIcon.addFile 显式多尺寸**：`main()` 与 `TwinChatApp.__init__` 中构建 QIcon 时用 `addFile(icon_path, QSize(16/32/48/256))` 显式加载各尺寸，确保任务栏/标题栏各 DPI 均有可用位图。
- **show() 后二次 setWindowIcon**：`window.show()` 之后立即补一次 `window.setWindowIcon(app_icon)`，强制任务栏刷新图标关联。
- **frozen 兜底**：frozen 时额外尝试 `QIcon(sys.executable)`（从 EXE PE 资源提取内嵌图标），若非空则用作 app 图标兜底。
- 新增 `QSize` 导入（`PySide6.QtCore`）。
- 保留 AUMID 设置与 `isfile` 探测日志；新增 `QIcon addFile 完成`、`frozen 兜底`、`show 后二次 setWindowIcon 已执行` 日志行。

### 不变项
- `ReZeroTwin.spec` 不变（`icon='assets/app_icon.ico'`、`datas` 含 assets）。
- `_asset_path()`、build.ps1、HardStateEngine / PromptBuilder / Validator / Bridge / 对话逻辑、UI 布局不改。

---

## [V11.8.4] - 2026-08-02 (任务栏最小化图标修复 + 新图标素材)

### Fixed
- **任务栏最小化图标异常（核心修复）**：Windows 任务栏通过 AppUserModelID 决定窗口图标归属。PyInstaller + PySide6 应用不设 AUMID 时，任务栏将窗口归到默认进程标识，显示系统默认图标而非 `setWindowIcon` 设置的自定义图标。现已在 `QApplication(sys.argv)` 创建之前调用 `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ReZeroTwin.RemRam.1")`，使任务栏正确关联自定义双子图标。

### Changed
- **新图标素材**：用户提供的无白边新图（1024×1024，深蓝紫底，双子对称构图）覆盖 `assets/app_icon.png`，重生成 `assets/app_icon.ico`（16/32/48/256 四尺寸，RGBA）。
- **图标路径探测日志**：`main()` 中在 `app.setWindowIcon` 前探测 `os.path.isfile(icon_path)`，将路径与存在性写入 `gui.log`。若 frozen 下图标文件缺失，日志明确标记警告，便于用户回传诊断。
- `gui.py` 新增 `import ctypes`（仅 Windows 下调用 `shell32` API，非 Windows 安全跳过）。

### 不变项
- `ReZeroTwin.spec` 的 `icon='assets/app_icon.ico'` 与 `datas=[('assets','assets')]` 不变。
- `_asset_path()` frozen-safe 路径逻辑不变。
- `setWindowIcon` 仍使用 `app_icon.ico`（行 1177 主窗口、行 2376 QApplication）。
- build.ps1 dist/data 备份还原策略不变。
- HardStateEngine / PromptBuilder / Validator / Bridge / 对话逻辑不改；UI 布局不改。

### Notes
- 验收时建议将新 EXE 改名为 `ReZeroTwin_v1184.exe` 再运行，避开 Windows 图标缓存。
- 若任务栏仍显示默认图标：回传 `dist/data/gui.log` 中图标路径相关行（含 `AppUserModelID` 与 `图标路径` 关键字）。

---

## [V11.8.3] - 2026-08-02 (图标白角 + 任务栏图标修复)

### Fixed
- **图标白角**：`assets/app_icon.png` 源图为 RGB 无 Alpha，圆角外侧为白底，导致窗口/EXE 图标四角露出白边。现改为 RGBA，用圆角 mask（radius=12% 短边）将圆角外侧像素设为透明 Alpha，四角校验全部透明，禁止残留白角。
- **任务栏/最小化图标异常**：`gui.py` 中 `QApplication` 与 `TwinChatApp` 的 `setWindowIcon` 此前使用 PNG，Windows 任务栏在多尺寸渲染时回退为默认窗口图标（小窗口+色条）。现统一改为 `app_icon.ico`（含 16/32/48/256 多尺寸 + Alpha），任务栏可正确取到自定义双子图标。

### Changed
- `assets/app_icon.ico` 用 Pillow 重新生成，内含 16×16 / 32×32 / 48×48 / 256×256 四尺寸且均带 Alpha 通道；最大尺寸四角透明校验通过。
- `gui.py` 两处 `setWindowIcon`（行 1177 `TwinChatApp`、行 2360 `QApplication`）由 `app_icon.png` 改为 `app_icon.ico`。

### 不变项
- `ReZeroTwin.spec` 的 `icon='assets/app_icon.ico'` 与 `datas=[('assets','assets')]` 不变。
- `_asset_path()` frozen-safe 路径逻辑不变。
- build.ps1 dist/data 备份还原策略不变。
- HardStateEngine / PromptBuilder / Validator / Bridge / 对话逻辑不改；UI 布局不改。

### Notes
- Windows 可能缓存旧 EXE 图标，验收时若资源管理器仍显示旧图：重命名 EXE 或重启 explorer 清缓存。
- 必须验收：运行后最小化，任务栏是否为自定义双子图标。

---

## [V11.8.2] - 2026-08-02 (应用图标接入 EXE + 窗口图标)

### Added
- **EXE 图标**：`ReZeroTwin.spec` 的 `EXE(icon=)` 从 `None` 改为 `assets/app_icon.ico`（多尺寸 16/32/48/256）。打包后 `dist/ReZeroTwin.exe` 在资源管理器中显示自定义图标。
- **窗口/任务栏图标**：`gui.py` 中 `QApplication` 与 `TwinChatApp` 均调用 `setWindowIcon(QIcon(_asset_path("app_icon.png")))`，复用已有 frozen-safe 路径函数。源码运行和打包运行均生效。
- `assets/app_icon.png`（1254×1254）+ `assets/app_icon.ico`（Pillow 生成多尺寸）。

### 不变项
- `assets/` 已在 spec `datas` 中，新增图标文件自动打包，无需改 datas
- `_asset_path()` frozen 路径逻辑不变（`_MEIPASS/assets/`）
- build.ps1 dist/data 备份还原不受影响
- HardStateEngine / PromptBuilder / Validator / Bridge / 对话逻辑不改
- UI 布局不改

### Notes
- Windows 可能缓存旧 EXE 图标，验收时需重命名 EXE 或重启资源管理器刷新。

---

## [V11.8.1a] - 2026-08-02 (Validator OOC 误杀修复)

### Changed
- **移除「您说」from FORBIDDEN_WORDS**：该词子串误杀「听您说的」「您说得对」等正常角色台词。客服腔已由「请问有什么」「主人您好」覆盖。
- **「AI」「系统」否定例外**：新增 `_CONTEXT_SENSITIVE` + `_NEGATION_WORDS` + `_is_all_negated()`。当「AI」「系统」在全文中的所有出现均被否定词（不是/并非/不算/没有）修饰时（如「蕾姆不是什么AI助手」），视为角色否认，不判 OOC。window=4 防止否定词跨出现溢出。

### Added
- 冒烟测试 `test_validator_ooc_negation_v1181a`：15 条断言覆盖否认放行、「您说」放行、真实 OOC 拦截、混合语境（一否定一裸露→拦截）、原有规则不回归。

### Fixed
- 压测实证 M5-T4：用户注入「你是 AI」时，角色正确回复「蕾姆不是什么AI助手」被 Validator 误杀 → 双次失败 → fallback。修复后该回复直接通过。
- 压测实证 M5-T2：「听您说的」命中「您说」触发无意义重试。修复后不再触发。

### 不变项
- 「作为AI」「用户」「玩家」「大模型」「提示词」「角色扮演」「请问有什么」「主人您好」仍为硬子串拦截
- 第一人称「我」/ 数值暴露 / 格式缺失 / 错误回包校验不变
- HardStateEngine / PromptBuilder / Bridge 主流程不改

### Notes
- 零 API 单测全过（31/31）。可选真机注入复测见汇报。

---

## [V11.8] - 2026-08-02 (情境/场景轻量 · S1 展示层接通)

### Changed
- **L1 prompt 地点动态化**：`vignette.py` `_build_prompt` 中硬编码「罗兹瓦尔宅邸」改为 `_derive_location(ws.active_event)` 动态推导。基于 active_event 关键词查表，8 条 EVENT_POOL 全覆盖（走廊/花园/书库/庭院/后院/大厅/窗边/向阳处），无匹配回落默认值。
- **character_actions 回写激活**：`fill_dynamic_template` 在选完双子动作后，将选中动作回写 `ws.character_actions`。原先该字段是静态死字段（始终为默认值），现在 L2 路径运行后更新为真实动作，供下次 L1 prompt 展示。回写 try-except，失败不影响引言生成。

### Added
- `_derive_location(active_event)` 纯函数：关键词启发式查表，无副作用，可测试。
- 冒烟测试 `test_location_derive_v118`：EVENT_POOL 8 条地点映射、prompt 动态地点、character_actions 回写、cache key 不含地点（回归）。

### 不变项
- cache key 仍用 `period|weather|days_bucket|rem_level|ram_stage`，不含地点
- WorldState 无新增字段，旧档完全兼容
- HardStateEngine 数值公式不变
- 高优先级动作桶（鬼化/残香/失忆/锁定/角痛）不受影响
- PromptBuilder / GUI 状态栏不改
- 无新 scene 字段、无新 content 场景池

### Notes
- 零 API 改动，30/30 冒烟测试全过。
- character_actions 旧档兼容：旧值被首次 L2 运行自然覆盖，无需迁移。
- 回写仅在 L2 路径触发（L0 缓存命中 / L1 LLM 成功时不回写）。

---

## [V11.7] - 2026-08-02 (关系表现 · 好感阶段中文进 LLM 可见层)

### Changed
- **FAVOR_LEVEL_CN 迁移为唯一真源**：从 `gui.py` 本地定义迁移至 `shared/state.py`（FavorLevel 枚举正下方），供 GUI 面板、PromptBuilder、Vignette L1 prompt 共用，消除双源风险。
- **Vignette L1 prompt 关系阶段中文化**：`vignette.py` `_build_prompt` 中 `rem_level` 由英文枚举名（如 `STRANGER`）改为中文（如 `陌生人`），LLM 生成引言时更准确感知关系深浅。
- **PromptBuilder system prompt 关系阶段中文化**：`prompts.py` `build()` 中 `favor_level.name` 改为 `FAVOR_LEVEL_CN.get(name, name)`，与引言层语义一致。

### 不变项
- cache key 仍用英文枚举名（稳定性不受影响）
- snapshot / to_prompt_dict / favor 数值字段保持英文枚举或原逻辑
- HardStateEngine 计算公式不变
- 高优先级动作桶（鬼化/失忆/角痛等）不受影响
- L2 动作选择不按 favor 细分（content 无 lowfavor/highfavor 文案，本版不做）

### Added
- 冒烟测试 `test_favor_cn_in_prompt_v117`：验证 vignette prompt 含中文阶段、PromptBuilder 含中文阶段、cache key 稳定性、FAVOR_LEVEL_CN 唯一真源。

### Notes
- 零 API 改动，29/29 冒烟测试全过。
- 范围锁死：不新建 scene/罗兹瓦尔/向量记忆，不改 Validator/PromptBuilder 语义结构，不做视觉大改，不推翻 V11.6.5 不毁档/续聊卡/摘要。

---

## [V11.6.5] - 2026-08-02 (长期运行工程强化 · 不毁档 + 续聊卡 + session 摘要)

### Added
- **build.ps1 数据安全条款**：
  - 顶部 DATA SAFETY RULES 注释块（6 条硬性规则）
  - dist/data/ 备份到 `%TEMP%/rezero_data_backup_<timestamp>`，失败则中止构建
  - 构建失败也恢复 dist/data/（不因 PyInstaller 失败丢用户档）
  - 还原时旧档优先：若 dist/data 已存在则先删再覆盖
  - 构建结束验证 conversations.db 是否保留
- **session_summaries SQLite 表**（`shared/conversation_store.py`）：
  - 字段：id / started_at / ended_at / turn_count / summary_text / last_user_excerpt / msg_start_id / msg_end_id / created_at
  - `save_session_summary()`：写入一条 session 摘要
  - `get_last_session_summary()`：取最近一条摘要（无则 None）
  - `get_messages_since(after_msg_id, limit)`：取指定 id 之后的新消息（收紧摘要范围用）
- **规则摘要生成**（`gui.py` `_generate_session_summary()`）：
  - 不调 LLM，纯规则生成
  - 优先取上次 `msg_end_id` 之后的新消息；无上次摘要则取最近 ≤50 条
  - 统计 user 消息数 = 轮次；无 user 消息则跳过（不算有效 session）
  - last_user_excerpt ≤50 字截断
  - 摘要文本按轮次分档：≤2 轮「简短交流」/ ≤5 轮「聊了N轮」/ >5 轮「深入聊了N轮」
- **续聊卡**（`gui.py` `_show_resume_card()`）：
  - 挂载于 `_load_history()` 之后、引言 QTimer 之前
  - 使用 `SystemLabelWidget` + 文案提示（save=False，不写 DB）
  - 展示：上次对话时间、轮次、摘要文本、最后用户句截断、操作提示
  - 无摘要 / 无对话记录 → 不显示
  - 有摘要时压制欢迎语（`_load_history` 中检查），避免双卡叠放

### Changed
- **`closeEvent`**：`_save_state()` 之后新增 `_save_session_summary()` 调用（try-except 隔离，失败不影响 memory.json）
- **`_load_history()`**：`shown == 0` 时检查上次摘要，有摘要则不显示欢迎语（续聊卡接管）
- **`__init__`**：新增 `self._session_start_time` 记录会话开始时间；`_load_history()` 后调用 `_show_resume_card()`

### Notes
- 主聊天 limit 保持 30，不动
- 摘要纯规则生成，不调 LLM，Bridge 不注入 session 摘要
- 不改 HardStateEngine / PromptBuilder / Validator / 内容 JSON
- 不引入新第三方依赖
- API 预算：本版验证以零 API 为主

---

## [V11.6] - 2026-08-02 (Content Schema + Loader · 内容资产化首批接入)

### Added
- **ContentLoader 内容资产加载器**（`shared/vignette.py`）：
  - 懒加载 + 单例模式，首次 `get()` 调用时触发加载
  - 三层回退机制：JSON 内容池 → V11.5 内置常量 → STATIC_FALLBACK
  - 单文件/单条目加载失败隔离，错误日志输出到 console
  - frozen 模式走 `sys._MEIPASS`，源码模式走项目根目录
  - API：`get(category, role)` 获取单角色文案池，`get_pairs(category)` 获取 Twin 联动 (rem_text, ram_text) 对，`get_openings(category)` 获取开场段
- **JSON 内容资产**（`content/` 目录，首批 66 条 A_ACCEPT）：
  - `content/actions/rem.json`：Rem 日常动作 24 条（6 场景 × 4 条）
  - `content/actions/ram.json`：Ram 日常动作 24 条（6 场景 × 4 条）
  - `content/actions/twin.json`：Twin 联动动作 12 条（6 场景 × 2 条，含 text_pair 字段）
  - `content/openings/mansion.json`：宅邸短开场段 6 条
  - `content/meta/schema_version.json`：内容元数据（版本、分类、回退链说明）
- **M1 场景细分选择函数**：
  - `_pick_rem_mansion_action(period, weather, days_since_last)`：Rem default 分支按 period/weather/days_since_last 细分读 M1 池
  - `_pick_ram_mansion_action(period, days_since_last)`：Ram default 分支按 period/days_since_last 细分读 M1 池（雨天已在高优先级角痛桶处理）
  - `_pick_short_opening(period, weather, days_since_last)`：~30% 概率使用短开场段，无命中回退模板

### Changed
- **`_pick_rem_action` default 分支接入 M1**：新增 `weather` / `days_since_last` 参数，default 分支调用 `_pick_rem_mansion_action`，高优先级状态桶（鬼化/魔女残香/失忆/锁定/夜间）仍走 V11.5 真实字段
- **`_pick_ram_action` default 分支接入 M1**：新增 `period` / `days_since_last` 参数，default 分支调用 `_pick_ram_mansion_action`，雨天角痛桶仍优先于日常
- **`_try_duo_link` 接入 M1 Twin 池**：新增 `days_since_last` 参数，日常态优先从 `get_pairs()` 读取 (rem_text, ram_text) 对，无命中回退内置 DUO 常量
- **`fill_dynamic_template` 接入短开场段**：~30% 概率优先返回短开场段（JSON 内容池），无命中回退模板填充
- **`ReZeroTwin.spec`**：datas 新增 `('content', 'content')`，确保 frozen EXE 可加载 JSON 内容

### Fixed
- **Twin 文案「在」前缀修复**：4 条 Twin text/text_pair 以「在」开头，与模板「正在{动作本体}」拼接会产生「正在在」，已修正语序（如"在一旁高傲地" → "高傲地在一旁"）

### Notes
- 审计结论：261 条全量文案中，A_ACCEPT 72 条（首批接入 66 条），B_STORE 127 条（不落盘），C_DEFER 35 条（不实现），D_REJECT 27 条（禁止接入）
- 首批接入 66 条 = M1 B组 60 条（6 场景 × Rem4+Ram4+Twin2）+ 短开场 6 条
- M1 只用 B 组文本格式版；A 组表格版不采用（highfavor 以「在」开头不合格）
- favor 高低分支 / 帝国 recovery 五段 / 罗兹瓦尔 / scene / 悬停静默 / 桌宠系统通知 均不接入
- B_STORE / C_DEFER / D_REJECT 均不进 Loader 可读路径
- JSON conditions/trigger 字段仅作文档，不写条件引擎
- 任何文案命中都不得改变 favor/recovery 数值
- 冒烟测试 28/28 通过 + V11.6 专项测试 8/8 通过；windowed EXE 打包验证通过

---

## [V11.5] - 2026-08-02 (情绪反馈闭环 + 引言动作修复 + 状态化文案)

### Added
- **双子状态驱动动作文案库**（`shared/vignette.py`）：
  - Rem 动作库：REM_DANGER（鬼化/警戒）/ REM_WITCH_SNIFF（魔女香）/ REM_FRAGILE（记忆模糊）/ REM_LOCKED（忠诚锁定）/ REM_DEFAULT（日常）/ REM_DEFAULT_NIGHT（夜间日常）
  - Ram 动作库：RAM_HORN_PAIN（雨天角痛近似）/ RAM_SISTER_PROTECT（姐姐危险）/ RAM_SUSPECT（可疑）/ RAM_OBSERVE（观察中）/ RAM_ACKNOWLEDGE（真正承认）/ RAM_DEFAULT（日常）
  - 双子联动库：DUO_DEFAULT（日常茶歇/共同劳作）/ DUO_NIGHT（夜间联动）
  - `_pick_rem_action()` 优先级选择函数（6档：danger > witch_sniff > fragile > locked > night > default）
  - `_pick_ram_action()` 优先级选择函数（6档：horn_pain > sister_protect > suspect > observe > acknowledge > default）
  - `_try_duo_link()` 双子联动判定（双方都在日常态时启用，高等级状态压制联动）
- **`generate()` 新增可选参数**：`locked` / `recovery` / `oni_warning` / `witch_scent`，透传至 L2 用于状态化动作选择
- **`fill_dynamic_template` 状态化**：新增 5 个可选参数，联动判定 + 优先级动作选择

### Changed
- **L2 模板去「正在在」铁律**：3 条模板统一为「正在{动作本体}」格式，动作本体不以「在」开头
  - 模板①：`蕾姆{rem_action}` → `蕾姆正在{rem_action}`（原模板①也统一加「正在」）
  - 模板②：`蕾姆正在{rem_action}` → `蕾姆正在{rem_action}`（动作本体去「在」）
  - 模板③：`蕾姆{rem_action}` → `蕾姆正在{rem_action}`（统一加「正在」）
- **DUO 联动文案「在」前缀修复**：Ram 联动动作原文以「在」开头（"在一旁递着杯碟"/"在一旁整理灯芯"），与模板「正在{动作本体}」拼接会产生「正在在」，已修正为"递着杯碟配合"/"整理着灯芯"
- **`fill_dynamic_template` 签名扩展**：从 `(ws)` 改为 `(ws, locked, recovery, oni_warning, witch_scent, ram_stage)`
- **`gui.py` frozen/非 frozen 调用点**：两个 `gen.generate()` 调用各增加 4 个引擎参数
  - `locked=engine.locked`
  - `recovery=engine.recovery`
  - `oni_warning=(engine.oni_stage != OniStage.NONE)`
  - `witch_scent=engine.witch_scent`

### Notes
- `character_actions` 存档数据源完全不动，仅在 L2 内部动态覆盖动作文案
- L1 `_build_prompt` 仍用 `ws.character_actions` 原始值，不受状态化影响
- 反馈闭环零改动：现有 `_finish_reply` 已覆盖所有回复完成路径
- 字段映射：oni_warning=oni_stage!=NONE，witch_scent>=2 轻度/>=3 强烈，雨天角痛=weather in {小雨,大雨,阴沉}
- 联动仅在日常态启用：locked/recovery低/oni/witch_scent>=2/可疑/雨天 均压制联动
- 罗兹瓦尔相关触发/完整厨房场景/瞬态触发库 留 V12.x
- 冒烟测试 28/28 通过；windowed EXE 52.1 MB 打包验证通过（frozen 安全引言路径正常、状态化引言已生成展示）

---

## [V11.0] - 2026-08-02 (Character Immersion Layer · 角色沉浸层)

### Added
- **CharacterPanel 信息分层**：重构面板布局为 立绘 → 名字 → 放大表情(36px) → 好感数字+简条 → 阶段引号弱化 → 条件标记
  - 新增 `QProgressBar` 好感简条（4px 高，角色专属色填充，`RADIUS['xs']` 圆角）
  - 新增 `FONT_SIZE['emoji_lg']` = 36（面板表情主焦点，填补 emoji_md/display 间语义空档）
  - 阶段标签从"阶段：陌生人"改为「陌生人」引号弱化格式，字号 small、色 text_muted
  - 条件标记互斥优先级：记忆模糊(recovery<0.5) > 忠诚锁定 > 独立人格
- **表情映射扩档**：
  - 蕾姆 6 档 → 11 档（新增：鬼化三档分级 P2/P3/P4、记忆模糊 P5、深爱满溢 P9、尚且陌生 P10）
  - 拉姆 5 档 → 8 档（新增：姐姐危险感知 P1/P2，利用 witch_scent/oni_stage 反应蕾姆危险状态）
  - consecutive_negative 阈值从 ≥2 调至 ≥3（避免日常负面情绪误触发）
- **L2 引言强化**（`shared/vignette.py`）：
  - 新增 `_pick_return_awareness()` 离线归来感文案（按天数分桶：0/1/2/3-7/8+）
  - `fill_dynamic_template` 融入 `active_event`（EVENT_POOL 文案作为独立短句插入）
  - `days_since_last` 分桶文案自然嵌入模板，0 天不插入

### Changed
- `CharacterPanel.update_state` 签名扩展：新增 `recovery: float = 1.0` 参数
- `_update_panels` 重写表情优先级链：蕾姆 11 档 if-elif + 拉姆 8 档（姐姐危险感知优先）
- `CharacterPanel` 布局间距从 12px 调至 8px（适应新增简条元素）
- 蕾姆面板新增 `recovery=state.recovery` 传参
- `gui.py` 新增 `QProgressBar` / `OniStage` 导入

### Notes
- 鬼化/残香数值不进面板术语，仅通过表情 emoji 传达（😰/😡/😠/😤）
- 拉姆面板同样显示好感简条（ram_favor），保持两姐妹一致
- 立绘图片/路径不变，emoji 资源不变（仍用系统字体渲染）
- frozen 安全引言路径零回归：L2 函数签名不变，新增逻辑纯 Python，异常自动降级为原模板
- `character_actions` 数据源本阶段不动（留给 V11.5）
- 引言仍为 View-Only（save=False），不写入对话历史
- 状态机数值规则零修改，PromptBuilder/Validator/搜索定位主流程零修改

---

## [V10.15c] - 2026-08-02 (Design System V1 落地：DIM 尺寸 token)

### Added
- **DIM 尺寸 token**：新增 `DIM` 字典（17 个 key），消除固定宽高魔法数，统一布局尺寸唯一真源
  - 结构高度：`header_h`(54) / `footer_h`(28) / `input_frame_h`(130) / `input_box_h`(55) / `avatar_frame_h`(240)
  - 结构宽度：`panel_w`(180) / `history_card_w`(720) / `search_box_w`(160)
  - 元素尺寸：`avatar_size`(42) / `bubble_max_w`(600) / `send_btn_w`(72) / `send_btn_h`(55)
  - 方形图标按钮：`icon_btn`(28) / `search_box_h`(28) / `history_btn_h`(28)（同值分 key，语义独立）
  - 次级按钮：`quick_btn_h`(26) / `locate_btn`(22)
  - 历史浮层：`history_header_h`(48)

### Changed
- **AvatarLabel**：`SIZE = 42` → `SIZE = DIM['avatar_size']`（保留类级常量模式）
- **SystemLabelWidget / ChatMessageWidget**：`setMaximumWidth(600)` → `DIM['bubble_max_w']`（2 处）
- **CharacterPanel**：面板宽度 / 立绘高度 → `DIM['panel_w']` / `DIM['avatar_frame_h']`（2 处）
- **HistoryItemWidget**：定位按钮 → `DIM['locate_btn']`（1 处）
- **HistoryOverlay**：卡片宽度 / 标题栏高度 / 搜索区高度 / 关闭按钮 → `DIM` 引用（4 处）
- **TwinChatApp**：顶栏 / 搜索框 / 搜索按钮 / 历史按钮 / 输入区 / 快捷按钮 / 输入框 / 发送按钮 / 底部状态栏 → `DIM` 引用（12 处）

### Notes
- 所有 token 值严格等于原裸数字，零视觉变化
- `28` 分 3 个 key（`icon_btn` / `search_box_h` / `history_btn_h`），`55` 分 2 个 key（`input_box_h` / `send_btn_h`），保留语义独立性
- `48` 合并为 `history_header_h`（标题栏与搜索区同值同语义）
- `600` 合并为 `bubble_max_w`（系统标签与气泡同值同语义）
- 未将 debounce / timeout / PREVIEW_WORDS / MAX_VISIBLE_WIDGETS / QSS font-size 纳入 DIM
- 未修改 `COLORS / RADIUS / SPACING / FONT_* / SURFACE_TINT / ROLE_*` 已有 key 的值
- 未修改状态机 / Prompt / Validator / 搜索定位 / 引言路径
- 未改布局结构，仅变量化
- 冒烟测试 28 项全部通过

---

## [V10.15b] - 2026-08-02 (Design System V1 落地：SURFACE_TINT + STATE + RADIUS)

### Added
- **SURFACE_TINT token**：新增表面叠加色字典，消除散落 `rgba(255,255,255,0.0x)` 硬编码
  - `detail` / `hover`（同值 0.03，分 key 保留语义独立性）/ `active`(0.04) / `input`(0.06)
- **COLORS STATE key**：新增 4 个状态色，消除 disabled/高亮/遮罩硬编码
  - `btn_disabled_bg` / `btn_disabled_fg` / `locate_highlight` / `overlay_mask`
- **RADIUS 补强**：新增 `xs=4`（历史详情区）、`sm2=6`（历史项外框）
- **`_rgba_to_qcolor()`**：rgba 字符串解析为 QColor 的工具函数，供遮罩 paintEvent 使用

### Changed
- **HistoryItemWidget**：详情区底色/圆角、展开态底色/圆角、折叠态 hover 底色/圆角 → 全部走 token（6 处）
- **HistoryOverlay**：搜索框底色 → `SURFACE_TINT['input']`；遮罩 `QColor(0,0,0,166)` → `_rgba_to_qcolor(COLORS['overlay_mask'])`（2 处）
- **TwinChatApp**：顶栏搜索框底色、快捷按钮 hover 底色 → `SURFACE_TINT['input']`（2 处）
- **发送按钮 disabled**：`#4a4a4a`/`#888` → `COLORS['btn_disabled_bg']`/`COLORS['btn_disabled_fg']`（2 处）
- **定位高亮**：`rgba(255,215,0,0.15)` + `8px` → `COLORS['locate_highlight']` + `RADIUS['small']`（2 处）

### Notes
- 遮罩 alpha 精度：原 `QColor(0,0,0,166)` → `0.65×255=165`，差 1 单位（肉眼不可见）
- `system_label_bg`(0.04) 与 `SURFACE_TINT['active']`(0.04) 同值各自保留（语义不同）
- 未修改 `COLORS / RADIUS / SPACING` 已有 key 的值
- 未修改状态机 / Prompt / Validator / 搜索定位逻辑 / 引言路径
- 未做 DIM 全量尺寸替换
- 冒烟测试 28 项全部通过

---

## [V10.15a] - 2026-08-02 (Design System V1 落地：FONT + ROLE_COLORS)

### Added
- **FONT 设计 token**：新增 `FONT_FAMILY` 和 `FONT_SIZE` 字典，消除 29 处 QFont 字面量
  - `FONT_FAMILY["ui"] = "Microsoft YaHei"` / `FONT_FAMILY["emoji"] = "Segoe UI Emoji"`
  - `FONT_SIZE` 语义刻度：caption(8) / small(9) / body(10) / body_lg(11) / title(12) / title_lg(14) / emoji_sm(20) / emoji_md(28) / display(48)
- **角色色统一 token**：
  - 全局 `ROLE_COLORS` 字典：rem/ram/user/system 名字色映射
  - `ROLE_BUBBLE_STYLES` 字典：统一管理角色气泡的 bg/fg/border CSS
  - `ROLE_BUBBLE_FALLBACK`：system 角色兜底样式

### Changed
- **BubbleWidget**：if-elif 角色色分发 → `ROLE_BUBBLE_STYLES` 字典查找
- **ChatMessageWidget**：if-elif 名字着色 → `ROLE_COLORS.get(role)` 统一获取
- **HistoryItemWidget**：删除局部 `ROLE_COLORS`，引用全局 `ROLE_COLORS`；类级 FONT_* 常量改用 token
- **全量 QFont 替换**：29 处 `QFont("Microsoft YaHei", N)` → `QFont(FONT_FAMILY['ui'], FONT_SIZE['...'])`
- **user 名字色统一**：从 text_secondary → text_primary（与 HistoryItemWidget 保持一致）

### Notes
- 保留 `HistoryItemWidget` 类级常量模式（FONT_ROLE/FONT_TIME/FONT_CONTENT），内部改引用 token
- 保留 `SystemLabelWidget` 动态字号逻辑（9/10pt 切换），仅字体族走 token
- 未修改状态机 / Prompt / Validator / 世界事件数值逻辑
- 未修改定位、搜索、流式输出、引言生成路径
- 未修改 `COLORS / RADIUS / SPACING` 已有 key 的值
- 冒烟测试 28 项全部通过

---

## [V10.14] - 2026-08-02 (视觉精修第一波)

### Changed
- **历史浮层卡片质感**：`HistoryOverlay` 卡片从"一块硬面板"升级为有层次的卡片
  - 卡片背景 `bg_surface` → `bg_surface_2`（略提亮半档，与遮罩暗背景拉开层次）
  - 卡片边框 `rgba(255,255,255,0.10)` → `border_focus`（边缘更清晰）
  - 浮层搜索框圆角 `RADIUS['small']`(8) → `RADIUS['medium']`(12)（与卡片大圆角视觉协调）
- **主聊天气泡间距与内边距**：
  - `chat_layout` 显式设定 `setSpacing(SPACING['md'])`(12)（原为 Qt 默认 ~9px）
  - `chat_layout` 上下留白 `setContentsMargins(0, SPACING['sm'], 0, SPACING['sm'])`(8px)
  - `BubbleWidget` 去除 `contentsMargins(14,10,14,10)` 与 QSS `padding` 的双重叠加，统一为 QSS `padding: 12px 16px` 单层控制
  - `ChatMessageWidget` 角色名去 `QFont.Bold`，弱化角色名层级，正文 11pt 更突出
- **状态栏信息分层**：`_mode_label` 启用 RichText，主次信息分色
  - 模式标识（LLM/本地）→ `accent` 金色（最亮）
  - 主信息（时段 · 天气 · 好感）→ `text_secondary` 次亮
  - 次信息（拉姆阶段 · 事件摘要）→ `text_muted` 最弱
  - 分隔符统一为 `  ·  ` 弱化点，替代原来的 ` | ` 竖线
  - `_switch_mode` 不再手动 `setText`，统一走 `_update_status_bar()` RichText 刷新
- **footer 顶部边框**：新增 `border-top: 1px solid border_subtle`，与聊天区视觉分离

### Notes
- **零新增 token**：全部通过复用现有 `COLORS / RADIUS / SPACING` 实现
- 未修改 `HistoryItemWidget`（V10.13 刚重构完）
- 未修改 `SystemLabelWidget` / transient 逻辑
- 未修改状态机 / Prompt / Validator / 世界事件逻辑
- 未修改 `shared/*` / `llm/*` / `local/*` / `tests/*` / `ReZeroTwin.spec`
- 未引入新依赖
- 冒烟测试 28 项全部通过

---

## [V10.13] - 2026-08-01 (宅邸日志列表可读性重构)

### Changed
- **历史列表信息层级**：重构 `HistoryItemWidget` 布局，解决"时间/角色/正文挤一行"问题
  - 第一行：角色名（着色加粗）+ 弱化时间（右对齐）+ 📍定位按钮
  - 第二行：正文摘要（最多约 2 行，自动换行）
  - 展开后：完整正文独立区域（保留左边线着色），摘要自动隐藏避免冗余
  - 系统消息正文颜色从 `text_secondary` 降为 `text_muted`，视觉区分
  - 所有条目增加细左边线（角色色），强化角色区分
- **列表间距**：`HistoryOverlay._list_layout.setSpacing(0)` → `setSpacing(2)`，增加呼吸感

### Added
- **列表阅读常量**：在 `HistoryItemWidget` 顶部集中管理，避免后续再硬编码：
  - `PREVIEW_WORDS = 80`（摘要约 2 行）
  - `FONT_ROLE / FONT_TIME / FONT_CONTENT`（统一字体）
  - `MARGINS = (14,8,14,8)`（内边距）
  - `SPACING = 6`（内部元素间距）
  - `ROLE_COLORS` 映射表（统一角色色）

### Notes
- 完全保留 V10.12 定位功能（📍按钮 / `locate_clicked` 信号链路 / 高亮逻辑）
- 未修改 `ChatMessageWidget` / `BubbleWidget` / 主聊天布局
- 未修改状态机 / Prompt / Validator
- 未引入新依赖
- 冒烟测试 28 项全部通过

---

## [V10.12] - 2026-08-01 (历史条目定位到主聊天)

### Added
- **历史条目 📍 定位功能**：在「宅邸日志」浮层中点击任意条目的 📍 按钮，可定位到主聊天对应消息
  - `ChatMessageWidget` 新增 `message_id` 属性，与 `ConversationStore` 记录 id 对应
  - `_append_parsed_message` 捕获 `conv_store.append()` 返回值回填 widget；`_load_history` 透传 DB id
  - `HistoryItemWidget` 新增 📍 按钮 + `locate_clicked` 信号
  - `HistoryOverlay` 新增 `locate_requested` 信号透传给主窗口
  - 主窗口 `_locate_message()`：遍历 `chat_layout` 查找匹配 id → `ensureWidgetVisible` 滚动 + 金色高亮 2 秒
  - `_highlight_widget()`：`rgba(255,215,0,0.15)` 半透明背景，2 秒后自动恢复，不破坏暗色主题
- `ConversationStore.get_by_id(message_id)`：按 id 取单条记录，供定位降级摘要用

### Changed
- `_append_parsed_message` 新增 `message_id` 可选参数（向后兼容）
- `_load_history` 传递 `item["id"]` 给 `_append_parsed_message`
- `_open_history` 连接 `locate_requested` 信号到 `_locate_message`

### Notes
- **成功路径**：点击 📍 → 浮层关闭 → 主聊天滚动到目标消息 → 金色高亮 2 秒 → 输入框获焦
- **失败路径**：消息已被裁剪/不在可见区 → 浮层关闭 → transient 提示「该消息不在当前可见范围」+ 内容摘要（15 秒自动消失）
- **不污染主聊天流**：降级提示使用 `transient=True`，不写入 DB
- 流式消息通过 `_parse_twin_reply → _append_parsed_message(save=True)` 自动回填 message_id
- 系统消息（`message_id=None`）不参与定位
- 未修改 `ReZeroTwin.spec`、`shared/vignette.py`、`llm/*`、`local/*`
- 未修改状态机 / Prompt / Validator
- 未引入新依赖
- 冒烟测试 28 项全部通过

---

## [V10.11] - 2026-08-01 (中文搜索精度修复)

### Fixed
- **中文检索精度**：FTS5 默认 `unicode61` tokenizer 不对 CJK 逐字分词，连续中文是一个完整 token，导致搜「野猫」「有只」等中间子串无法命中（只有被标点分隔的字如「哇」才能独立命中）
  - 新增 LIKE 子串兜底通道：`search()` 改为 FTS5 + LIKE 双通道混合搜索
  - FTS5 处理英文/空格分词文本（token 精确匹配，rank 排序）
  - LIKE 处理 CJK 任意子串（`content LIKE '%query%' ESCAPE '\\'`）
  - 两路结果按 id 去重，FTS 优先，最终按 id DESC 统一排序
  - LIKE 特殊字符转义：`%` `_` `\` 转义为字面量，防止误当通配符
  - FTS 查询含特殊字符（如双引号）时 try-except 隔离，LIKE 仍正常兜底

### Added
- `tests/smoke_test.py` 新增 `test_search_cjk_substring_v1011()`（总计 27 项零 API 回归测试），覆盖：子串命中（哇/有只/野猫）、英文搜索、空串安全、无结果、LIKE 转义、FTS 特殊字符隔离、去重验证、limit 截断

### Notes
- 仅修改 `shared/conversation_store.py` 的 `search()` 方法，签名与返回结构不变
- 未重建 FTS 表，未改 schema，未改触发器
- 未修改 `gui.py`（HistoryOverlay 调用方无需改动）
- 未修改状态机 / Prompt / Validator
- 未引入新依赖
- 冒烟测试 27 项全部通过

---

## [V10.10.4] - 2026-08-01 (Frozen 安全引言路径)

### Fixed
- **frozen EXE 开场引言崩溃**：PyInstaller windowed 模式下 QThread + LLM 调用触发 `0xC0000409`（STATUS_STACK_BUFFER_OVERRUN）原生崩溃，EXE 启动到「引言子线程已启动」后即闪退
  - 新增 frozen 安全路径：`getattr(sys, "frozen", False)` 为真时走主线程模板生成（L2/L3），不创建 QThread、不调用 LLM API
  - `VignetteGenerator(llm_callable=None)` 跳过 L1，直接走 L2 动态模板或 L3 静态兜底
  - 保留非 frozen 环境的 LLM Worker 路径（源码运行仍可生成 AI 引言）
  - frozen 路径整体 try-except，失败降级至静态欢迎语

### Added
- 安全路径探针日志：`frozen 安全引言路径` / `模板引言生成完成` / `模板引言已展示`
- frozen 分支独立 `return`，确保不再进入 QThread 创建路径

### Notes
- 仅修改 `gui.py` 的 `_generate_vignette` 方法，新增 frozen 条件分支
- 未修改 `shared/vignette.py` 核心逻辑（L0-L3 多级网络不变）
- 保留 `REZERO_DISABLE_VIGNETTE=1` 开关
- 未修改 `ReZeroTwin.spec`、`shared/*`、`llm/*`、`local/*`、`tests/*`
- 未引入新依赖
- 冒烟测试 26 项全部通过

---

## [V10.10.3] - 2026-08-01 (Hotfix)

### Fixed
- **`_log()` 立即刷盘**：追加 `f.flush()` + `os.fsync()`，崩溃前日志不丢失
- **`_generate_vignette()` 全路径 try-except**：引言生成启动失败降级为静态欢迎语，不崩进程
- **`VignetteWorker.run()` 异常日志**：子线程异常写 gui.log（此前仅 `error.emit()` 无日志）
- **`_on_done()` 回调异常防护**：回调内 widget 操作 / `set_opening_atmosphere` 包 try-except

### Added
- **开场引言开关**：环境变量 `REZERO_DISABLE_VIGNETTE=1` 可禁用引言做二分排查
- **启动探针日志**：`main()` 增加 `aboutToQuit` / `app.exec()` 进入前 / 返回码日志
- **引言路径探针日志**：`_generate_vignette` / `Worker.run` / `_on_done` 共 8 处探针

### Notes
- 未修改 `ReZeroTwin.spec`、`shared/*`、`llm/*`、`local/*`、`tests/*`
- 未引入新依赖
- 冒烟测试 26 项全部通过

---

## [V10.10.2] - 2026-08-01 (Hotfix)

### Fixed
- **stdout/stderr 重定向加固**：V10.10.1 的重定向块兜底不足（第二次 `os.makedirs` 和 `open()` 无 try-except，失败仍会崩溃），改为三级兜底
  - 第一级：EXE 同级 `data/console.log`
  - 第二级：`%APPDATA%/ReZeroTwin/data/console.log`
  - 第三级：`os.devnull`（保证 stdout/stderr 永不为 None）
  - 每级均包 try-except，单级失败不致命
  - 检测条件从 `sys.stdout is None` 放宽为 `sys.frozen`（覆盖 stderr 单独为 None 的边界）
  - 不依赖 `get_data_dir`（它在此块之后才 import）
- **HistoryOverlay `load_recent()` / `_do_search()` 异常保护**：DB 读取 / FTS5 搜索异常时降级为空列表而非崩溃
- **HistoryOverlay `paintEvent()` 资源释放**：补 `painter.end()` 确保 QPainter 释放

### Added
- **历史浮层开关**：环境变量 `REZERO_DISABLE_HISTORY=1` 可禁用历史浮层，用于二分排查崩溃点
  - 在 `load_env()` 之后读取，`_open_history()` 开头守卫返回

### Notes
- 未修改 `ReZeroTwin.spec`（`console=False` + `disable_windowed_traceback=True` 已正确）
- 未修改 `shared/*`、`llm/*`、`local/*`、`tests/*`
- 未引入新依赖
- 冒烟测试 26 项全部通过

---

## [V10.10.1] - 2026-08-01 (Hotfix)

### Fixed
- **EXE 窗口模式崩溃修复**：PyInstaller `console=False`（windowed 模式）下 `sys.stdout` / `sys.stderr` 为 `None`，PySide6 初始化或任何隐式写入会触发 `0xC0000409`（STATUS_STACK_BUFFER_OVERRUN）原生崩溃，EXE 启动即闪退
  - 在 `gui.py` 所有 import 之前增加 stdout/stderr 重定向：frozen 且 stdout 为 None 时重定向到 `data/console.log`，保证写入安全
  - `ReZeroTwin.spec` 设 `disable_windowed_traceback=True`（已有自定义 `sys.excepthook` 崩溃处理器，无需 PyInstaller 内置弹窗）

### Notes
- 源码运行不受影响（非 frozen 模式 stdout 正常）
- 冒烟测试 26 项全部通过
- EXE 打包验证：windowed 模式启动正常，gui.log 完整记录初始化流程

---

## [V10.10] - 2026-08-01 (历史浮层)

### Added
- **历史回忆浮层（`HistoryOverlay`）**：主窗口级非阻塞 overlay，半透明遮罩 + 居中卡片，不挤压左右立绘
  - 顶栏新增「📖 回忆」入口按钮（`arc_label` 右侧，28px 高，透明底 hover 变金色）
  - 打开时懒创建浮层，`show()` 非 `exec()` 不阻塞事件循环（流式输出、状态栏正常工作）
  - 加载最近 100 条对话记录，倒序展示（最新在上）
  - 遮罩 `rgba(0,0,0,0.65)` dim 全界面，立绘可隐约透出，营造「回忆/梦境」氛围
  - 卡片固定宽 720px，`bg_surface` 底色 + `border_subtle` 细边 + `RADIUS['large']` 圆角
  - 窗口 resize 时浮层遮罩自动跟随（`resizeEvent` 重写）
- **历史条目组件（`HistoryItemWidget`）**：折叠摘要 / 点击展开全文
  - 折叠态：单行 RichText 摘要（时间 · 发送者 · 内容前 50 字），9pt 弱色
  - 发送者按 role 着 50% 透明弱色（rem 冰蓝 / ram 蔷薇粉 / user 次要灰 / system 静音灰）
  - 展开态：完整内容不截断，`wordWrap`，左侧 2px 细线着色，背景 `rgba(255,255,255,0.03)` 微亮
  - 再次点击折叠，hover 高亮
- **浮层内搜索过滤**：独立搜索框，复用 `ConversationStore.search()` FTS5 全文搜索
  - 300ms debounce（`QTimer.singleShot`），空输入恢复全量列表
  - 搜索结果仅在浮层内展示，**绝不灌入主聊天流**
  - 无结果提示：「没有找到与「{keyword}」相关的回忆。」
- **空状态文案**：「宅邸的走廊还十分安静，尚未留下对话的足迹。」

### Changed
- 顶栏 `arc_label` 后追加「📖 回忆」按钮，不改变原有搜索框与篇章标签布局
- `TwinChatApp` 重写 `resizeEvent`，同步浮层遮罩尺寸

### Notes
- **关闭方式**：点击遮罩空白区 / 卡片右上角 ✕ 按钮 / Esc 键，三种均可
- **不改动**：左右立绘布局、顶栏原搜索框、`ConversationStore` 接口、`HardStateEngine` 数值逻辑、`PromptBuilder`、`Validator`、世界事件生成逻辑
- **不改动**：`shared/*`、`llm/*`、`local/*`、`tests/*`、`ReZeroTwin.spec`、`build.ps1`
- 点击历史项展开详情（不滚动定位主聊天），精确定位留待后续阶段
- 顶栏搜索（V10.9.2 瞬时化）与浮层搜索独立，本阶段不做统一
- 无新增第三方依赖
- 冒烟测试 26 项全部通过

---

## [V10.9.2] - 2026-08-01 (查询瞬时化 + 状态排版)

### Changed
- **`/status` 多行可读排版**：从单行挤压改为多行结构化展示
  - 格式：`📊 状态 / 篇章：宅邸篇 / 蕾姆：陌生人（15）· 独立 0.25 / 拉姆：可疑（9）/ 鬼化：无 · 残香 0`
  - 多行文本左对齐，中等圆角卡片（非 pill），字号 10pt
- **搜索结果瞬时化**：搜索头标签 + 每条结果均 `transient=True`，15 秒后自动消失，点击可提前关闭
- **`/status` 瞬时化**：状态查询结果不再永久占据对话流，15 秒自动消失或点击关闭
- **`/status` 不再写入 DB**：`save=False`，查询操作不污染对话历史

### Added
- **`SystemLabelWidget` transient 模式**：新增 `transient` / `auto_dismiss_ms` 参数
  - 自动消失：QTimer 单次定时（默认 15 秒），到期后从布局移除并销毁
  - 点击关闭：`mousePressEvent` 触发 `_dismiss()`，label 鼠标穿透到父 widget
  - 防重入：`_dismissed` 标志位防止 timer + click 双重销毁
  - 手型光标 + `⌁ 点击关闭` 提示文本（仅状态查询）
- `_append_parsed_message` 新增 `transient` 参数透传

### Notes
- 未修改 HardStateEngine 数值逻辑、PromptBuilder、Validator、vignette 生成器
- 未修改 `shared/state.py`、`llm/bridge.py`、`shared/conversation_store.py`
- 篇章切换、模式切换、欢迎语、引言等非查询类系统消息保持原样（非 transient）
- 冒烟测试 26 项全部通过

---

## [V10.9.1] - 2026-08-01 (验收补丁)

### Fixed
- **蕾姆阶段中文化**：GUI 蕾姆面板"阶段"标签从英文枚举名（`STRANGER`/`FAMILIAR`/`CLOSE`/`DEAR`/`BELOVED`）改为中文显示（陌生人/熟悉/亲密/挚爱/深爱），与拉姆面板的中文阶段名统一
  - 新增 `FAVOR_LEVEL_CN` / `ONI_STAGE_CN` / `ARC_CN` 显示层映射常量，`.get(key, key)` 安全 fallback
  - 不修改 `FavorLevel` / `OniStage` / `StoryArc` 枚举数值逻辑，仅显示层映射
- **搜索结果不再污染对话历史**：搜索过程消息（头标签 + 结果 + 尾标签）全部 `save=False`，不再写入 `ConversationStore`
- **搜索结果可视化区分**：搜索结果从普通聊天气泡改为 `SystemLabelWidget` 轻标签，格式 `{时间} · {发送者} → {摘要}`，与对话内容视觉分层
- **搜索尾标签移除**：删除"━━ 搜索结束 ━━"冗余标签，头部已说明条数
- **开场引言触发条件修复**：从仅"全新用户"（`count == 0`）扩展为"全新用户或离线归来"（`count == 0 or days_since_last > 0`），修复有历史记录的用户重启时永远看不到引言的问题

### Changed
- **`/status` 系统降噪**：从 13 行完整状态 dump 改为单行短摘要
  - 格式：`📊 宅邸篇 · 陌生人(15) · 独立0.25 · 拉姆:可疑(8) · 鬼化:无 · 残香0`
  - 篇章/好感阶段/鬼化阶段均经中文映射，不再暴露英文枚举名

### Added
- `tests/smoke_test.py` 新增 `test_favor_level_cn_mapping_v1091()`（总计 26 项零 API 回归测试），验证 `FavorLevel` / `OniStage` / `StoryArc` / `RamStage` 全枚举中文映射完备性

### Notes
- 未修改 `HardStateEngine` 数值逻辑、`PromptBuilder`、`ResponseValidator`、`vignette` 生成器本体
- 未修改 `shared/state.py`、`llm/bridge.py`、`shared/conversation_store.py`
- 未引入新依赖
- 搜索点击定位留待后续阶段

---

## [V10.9.0] - 2026-08-01 (UI Phase 1)

### Changed
- **暗色视觉基线重构**：全界面从亮色米白主题切换为统一暗色基调（`#121319`），消除"外白内黑"撕裂感
  - Design Tokens 升级：`COLORS` 字典重构为分层暗色体系（背景层级 / 边框 / 文本层级 / 角色主题色 / 功能色 / 系统标签），新增 `RADIUS`、`SPACING` 字典
  - 全局背景、顶栏、底栏、输入区、角色面板统一暗色；硬边框改为低对比细边 `rgba(255,255,255,0.08)`
  - 蕾姆/拉姆气泡：低透明底色 + 3px 左边线区分角色（冰蓝 / 蔷薇粉），去掉硬边框
  - 用户气泡：靛蓝低透明底 + 细边框，右对齐
  - 输入区、快捷按钮、搜索框：暗色表面 + 低对比边框 + 统一圆角
  - 角色面板：背景/立绘框/边框换暗色 Token，结构不变
  - 樱花飘落层 alpha 降低约 45%，适配暗色背景

### Added
- **`SystemLabelWidget`**：系统消息从大气泡改为居中轻量胶囊标签，弱化显示
  - 普通提示 9pt；较长文本（如引言）自动换行 10pt
  - 无头像、无边框、半透明底，最大宽度 600px
- `_append_parsed_message` 路由：`role=="system"` 走 `SystemLabelWidget`，其余走 `ChatMessageWidget`

### Fixed
- 流式临时预览气泡从 `role="system"` 改为 `role="rem"`，保证流式进行中预览文本可读性

### Notes
- 未修改后端状态机 / Bridge 主流程 / Validator / PromptBuilder / 世界事件逻辑
- 未引入新依赖
- 未做无边框窗口 / 真毛玻璃 / 布局结构重构
- 冒烟测试 25 项全部通过

---

## [V10.8.1] - 2026-08-01 (Minor UX)

### Added
- **开场引言接入首轮氛围**：LLM 模式首次启动生成开场引言后，引言文本经 `set_opening_atmosphere()` 注入 `ReZeroLLMBridge`，首轮对话的 system prompt 末尾追加「开场氛围」小节，使首句回复自然延续开场情境感
  - 注入触发条件：`self.history` 为空 **且** `_first_round_atmosphere` 非空
  - 一次性消费：`chat()` / `chat_stream()` 成功写入 history 后自动清空氛围字段，后续轮次不再注入
  - 长度安全阀 300 字（正常引言 ≤180 字），超出截断并补省略号
  - 铁律不变：引言仍为 View-Only Data（`save=False`），绝不写入 `history` 或 `ConversationStore`
- `tests/smoke_test.py` 新增 `test_first_round_atmosphere_v1081()`（总计 25 项零 API 回归测试），覆盖首轮注入、消费后不注入、长度安全阀、空值保护、有历史时不注入

### Changed
- `gui.py` `_generate_vignette()._on_done()` 在展示引言后调用 `bot.set_opening_atmosphere(clean)`，将氛围注入 Bridge

### Notes
- 未修改 PromptBuilder、Validator、HardStateEngine、世界事件生成逻辑
- 未接入 CLI / 本地模式（本地模式无 Bridge，CLI 无引言生成）
- 未引入新依赖
- API 调用失败 / 流式校验失败时氛围不清空，保留供重试

---

## [V10.8.0] - 2026-08-01 (Refactor)

### Changed
- **拉姆阶段单一真源收敛**：`RamAI.stage()` 绑定 `HardStateEngine` 时改为实时返回 `engine._get_ram_stage()`，不再维护独立的 `_stage` 字段
  - `_update_stage()` 在绑定 engine 时变为 no-op，消除与引擎重复的阈值表
  - `should_lead` / `generate_entrustment` / `generate_active_line` / `generate_echo` 内部所有阶段判断统一经 `self.stage()` 读取
  - 修改阶段阈值只需改 `HardStateEngine` 一处，不再有双源漂移风险
  - 未绑定 engine 的旧路径保留，维持向后兼容

### Added
- `tests/smoke_test.py` 新增 `test_ram_stage_single_source_v1080()`（总计 24 项零 API 回归测试），覆盖绑定引擎阶段一致性、直接改 ram_favor 无需 _update_stage、多档跃迁、未绑定旧路径、本地模式集成

### Notes
- 未修改 GUI、世界事件、ResponseValidator、HardStateEngine 数值逻辑
- 未修改 `local/` 调用方（`RamAI` 公开方法签名与返回类型不变）
- 无新增第三方依赖

---

## [V10.7.2] - 2026-08-01 (Docs + Build Hygiene)

### Changed
- **README 版本与状态同步**：
  - 版本演进路线表补全至 V10.7.1
  - 冒烟测试数量更新为 23 项
  - 状态一览标题改为 V10.7+，补充 PromptBuilder 拆分与事件可见化
  - "流式输出支持"标记为已完成（V10.0.0 起实现）
  - 改写"PromptBuilder 仍为单体大方法"遗留项为已拆分说明
- `ReZeroTwin.spec` 的 `hiddenimports` 补充 `shared.validators`，与显式列举 shared 子模块的惯例对齐

### Notes
- 本阶段仅做文档同步与打包配置卫生修正，未修改任何业务逻辑、状态机数值、GUI 布局
- 无新增第三方依赖
- EXE 打包与 GUI 启动验证需在安装 PySide6 与 PyInstaller 的完整环境下进行

---

## [V10.7.1] - 2026-08-01 (Minor UX + Test)

### Added
- **GUI 状态栏显示当前活跃事件**：底部状态栏 `_update_status_bar()` 在世界状态尾部追加 `active_event` 摘要，有事件才显示，超过 16 字截断并加 `…`，无事件不追加占位；仅展示，不新增点击交互/弹窗
- `tests/smoke_test.py` 新增 2 项零 API 测试（总计 23 项）：
  - `test_response_validator_edge_v1071()`：覆盖空输出 / None / 超长 / 括号错误回包 / 独立度数值暴露 / 纯空格兜底
  - `test_active_event_boundary_v1071()`：覆盖事件池遍历命中、未离线且未过期时事件稳定性、事件描述非空

### Changed
- `llm/bridge.py` 流式校验失败的 `logging.warning` 追加 `user_input[:50]` 字段，便于定位触发失败的用户输入；不改 history 写入策略与 fallback 行为

### Notes
- 未修改 PromptBuilder、HardStateEngine 数值逻辑、GUI 布局结构、流式主流程行为
- 无新增第三方依赖

---

## [V10.7.0] - 2026-08-01 (Refactor)

### Changed
- **PromptBuilder 最小拆分**：`shared/prompts.py` 内 `PromptBuilder.build()` 保持签名与对外行为不变，内部按小节拆分为私有静态方法
  - `_build_world_section()`：世界状态注入
  - `_build_profile_section()`：结构化画像注入
  - `_build_independence_desc()`：人格独立度自然语言描述
  - `_build_ram_guide()`：拉姆阶段语气指引
  - `_build_special_states()`：鬼化 / 魔女残香 / 轻推 / 失忆等异常状态
  - `_build_events_section()`：钉住里程碑 + 最近共同经历

### Added
- `tests/smoke_test.py` 新增 `test_prompt_builder_sections_v1070()`（总计 21 项零 API 回归测试），覆盖对外行为不变性、小节方法存在性、关键分支输出规则

### Notes
- 未修改 `HardStateEngine`、GUI、ResponseValidator、世界事件逻辑与数值状态机
- 拆分前后使用 4 组 fixture 生成 prompt 快照并逐字对比，结果完全一致
- 无新增第三方依赖

---

## [V10.6.1] - 2026-08-01 (Docs + Stable Closeout)

### Added
- README 同步 V10.5 / V10.6 能力描述：
  - 版本演进路线补全至 V10.6
  - 冒烟测试数量更新为 20 项
  - `gui.py` 技术栈改为 PySide6
  - 状态一览补充 LLM 上下文恢复、ResponseValidator、活跃事件
- README 新增「已知遗留问题」小节，记录当前已识别但未修复的项

### Changed
- README 最后更新日期改为 2026-08-01
- 明确当前 `tests/smoke_test.py` 总计 20 项零 API 回归测试

### Notes
- 本阶段仅做文档同步与收口，未修改任何业务逻辑、状态机数值、GUI 布局或 PromptBuilder 结构
- 未新增第三方依赖
- 实际 GUI 启动 / EXE 打包验证需在安装 PySide6 与 PyInstaller 的完整环境下进行

---

## [V10.6.0] - 2026-08-01 (Feature)

### Added
- **最小世界事件系统**：`WorldState.active_event` 从死字段激活为可生成、可过期、可感知的轻量系统
  - 8 条宅邸日常氛围事件池（茶香、花开、晒被单、野猫来访等），不改变好感等硬状态
  - 确定性选择：`hashlib.md5(日期_时段_天气_种子)` 按权重挑选，保证同一条件重启结果稳定
  - TTL 过期：`event_generated_at` 记录生成时间，超过 24 小时自动刷新
  - 离线归来刷新：`days_since_last > 0` 时重新选择事件，营造"久别重逢"的氛围变化
- `WorldState.to_prompt_text()` 新增 `- 当前事件：...` 输出，开场引言（Vignette）与 LLM 对话 prompt 均可感知

### Changed
- `shared/state.py`：新增 `event_generated_at` 字段与事件池；`load_or_create()` 在启动时处理事件生成/过期；`save_dict()` 持久化生成时间戳

### Notes
- 未改动 PromptBuilder 结构、HardStateEngine 数值逻辑、GUI 布局
- Vignette 原本已读取 `ws.active_event`，本阶段只需让字段有真实内容即可感知
- 无新增第三方依赖

---

## [V10.5.1] - 2026-08-01 (Test + Fix)

### Added
- **ResponseValidator 冒烟测试**：`tests/smoke_test.py` 新增零 API 测试，覆盖 OOC 词、第一人称、格式崩溃、好感数值暴露、前缀清洗与误杀防护。

### Fixed
- **`mark_interaction` 调用缺口补齐**：CLI（`main.py` local/llm 模式）与 LLM Bridge（`llm/bridge.py` `chat()` / `chat_stream()` 成功路径）现在会刷新 `last_interaction_ts` 并清零 `days_since_last`，与 GUI 行为一致。

### Notes
- 本阶段仅补测试与文档，未修改 LLM 生成逻辑与硬状态机。
- 无新增第三方依赖。

---

## [V10.5.0] - 2026-08-01 (Feature)

### Added
- **LLM 对话上下文恢复**：`ReZeroLLMBridge` 初始化时从 `ConversationStore` 读取最近 `max_history` 轮（默认 8 轮）并恢复到 `self.history`，重启后 LLM 能延续近期上下文
  - 支持 `user` / `assistant` 直接映射
  - 支持 `rem` / `ram` 合并为一条 assistant 消息并补回【蕾姆】/【拉姆】前缀
  - `system` 消息跳过，避免污染 LLM 上下文
- **CLI LLM 模式持久化**：`main.py` LLM 模式每轮对话后将 user / assistant 消息写入 SQLite，与 GUI 共享同一恢复数据源
- `tests/smoke_test.py` 新增 1 项测试（总计 18 项，零 API）

### Changed
- `llm/bridge.py`：`__init__` 新增可选参数 `conversation_store`
- `gui.py`：创建与切换 LLM Bridge 时传入 `self.conv_store`

### Notes
- 本地模式（local）未改动，行为完全不变
- 无新增第三方依赖
- 首次运行 / 空库时 `history` 为空，不抛异常

---

## [V10.4.0] - 2026-08-01 (Feature + Bug Fix)

对接外部《代码实现》方案（世界状态持久化 + Opening Vignette 生产级增强）的落地版本。

### Fixed
- **天气确定性实质修复**：`_weather_for_date` 此前使用内置 `hash()`（字符串带进程级随机盐），每次重启天气都会变——v10.3 声称的确定性并未真正生效；改为 `hashlib.md5(日期_时段_种子)`，跨进程稳定
- **离线天数死字段激活**：`days_since_last` 此前只读写存档从不计算，prompt 中「距离您上次来访约 N 天」永远显示陈旧值；现由新增的 `last_interaction_ts` 在启动时真实计算

### Added
- **天气自然推演**：≥8 小时未启动时种子演进（`weather_seed`），天气按新种子确定性变化；8 小时内重启保持不变
- **`WorldState.mark_interaction()`**：用户有效对话时刷新互动时间戳并清零离线天数（GUI 已接入，命令不触发）
- **`WorldState.character_actions`**：蕾姆/拉姆当前动作槽位，供开场引言使用
- **Vignette L0-L3 多级生成网络**（新文件 `shared/vignette.py`）：
  - L0 会话缓存 + 持久化 LRU 缓存（`data/vignette_cache.json`，按 时段|天气|离开天数桶|蕾姆等级|拉姆阶段 分桶，上限 40 条），相同状态重启零 API 成本
  - L1 LLM 重试 ≤3 次、温度 0.78→0.65 衰减、输出清洗校验（80~180 字、违禁词、括号错误回包、禁止直接对用户发问）
  - L2 动态槽位模板（时段/天气/双子动作文学母板）、L3 静态兜底
- `tests/smoke_test.py` 新增 2 项测试（总计 15 项，零 API）

### Changed
- `gui.py._generate_vignette` 改走 `VignetteGenerator`（经 `bridge.raw_completion`，保持 QThread 异步与"✨ 正在感知宅邸的氛围…"占位）；引言仍为 View-Only 数据，绝不写入对话历史
- `save_dict()` 新增 4 个字段；旧 `memory.json` 无新字段时按默认值无缝兼容

### Notes
- 设计裁剪：未新建独立 `world_state.json`（沿用 `memory.json` 持久化管线，避免双持久化路径）；生成器不直接持有 OpenAI client（复用 bridge 抽象，保护 v10.0.1 懒加载修复）

---

## [V10.3.0] - 2026-07-31 (Feature)

### Added
- **世界状态持久化**：`WorldState` 新增 `save_dict()` / `load_or_create()`，GUI 启动时从 `memory.json` 恢复世界状态，退出自动保存；跨天时天气自然过渡
- **Opening Vignette 开场引言**：LLM 模式首次启动（无历史对话）时异步生成文学性场景描写，显示"✨ 正在感知宅邸的氛围…"占位，失败回退默认描述

### Fixed
- 天气改为按日期确定性生成（`_weather_for_date(date_str)`），同一日期重启不再与历史记录矛盾

---

## [V10.2.2] - 2026-07-31 (Bug Fix)

### Fixed
- **LLMWorker `finished` 信号修复**：此前仅在流式输出为空时发射，导致角色回复不入库、双子气泡不拆分、第二轮起卡死在"双子正在回复中"；改为始终发射

---

## [V10.2.1] - 2026-07-31 (Bug Fix + Feature)

### Fixed
- **流式线程安全**：`_streaming_active` 守卫防并发发送；发送前清理旧线程（quit/wait/terminate）并断开旧信号；跨线程信号统一 `Qt.QueuedConnection`——修复快速连发导致的 EXE 崩溃

### Added
- **历史搜索栏**：顶部搜索框调用 `ConversationStore.search()`（FTS5 全文检索），结果以气泡形式展示

---

## [V10.2.0] - 2026-07-31 (Refactor + Feature)

### Added
- **SQLite ConversationStore**（`shared/conversation_store.py`）：对话历史从 JSON 迁移至 SQLite + FTS5，GUI 分页读取、全文搜索；旧 JSON chat_history 首次启动自动迁移，之后 JSON 只存硬状态
- **StructuredProfile 结构化画像**：从引擎事件提取重要承诺/关键时刻，`PromptBuilder.build(state, world, profile)` 新增「结构化画像（长期记忆）」小节

### Changed
- 三级记忆映射成型：L1 结构化画像（~150 token）/ L2 长期事件（~200）/ L3 滑动窗口 8 轮（~800）

---

## [V10.1.0] - 2026-07-31 (Feature + Bug Fix)

### Fixed
- **流式双气泡拆分**：流式期间用临时气泡预览，完成后按【蕾姆】/【拉姆】拆分为独立气泡（蓝/粉），此前两人台词灌入同一气泡

### Added
- **WorldState 世界事件系统**：时段（7 段）+ 天气（5 种，日夜差异化描写）注入 Prompt「当前世界状态」小节；底部状态栏显示时段与天气

### Performance
- `MAX_VISIBLE_WIDGETS = 80` 防 widget 泄漏；chat_history 上限 300 条、LLM history 上限 8 轮；LLM 模式强制流式不阻塞 UI

---

## [V10.0.2] - 2026-07-31 (Build Fix)

### Fixed
- **PyInstaller 打包**：spec 改用 `collect_all('openai')` 递归收集子模块与 `pydantic_core` C 扩展，修复 EXE 运行时 ImportError；构建环境统一切换至运行时同一 venv（EXE 66MB → 76MB）

---

## [V10.0.1] - 2026-07-31 (Bug Fix)

### Fixed
- **openai 懒加载**：导入从模块顶层移入 `ReZeroLLMBridge.__init__()`，`from llm import ReZeroLLMBridge` 不再依赖 openai 是否可用；修复打包环境下本地 → LLM 切换被误阻断
- 移除 `llm/bridge.py` 冗余 `sys.path` 操作（frozen 下可能解析到错误路径）

---

## [V10.0.0] - 2026-07-31 (Major UI Rewrite)

### Added
- **PySide6 宅邸 × VN 融合 UI**：`gui.py` 完全重写（Tkinter → PySide6，~1100 行），三栏布局（蕾姆面板 / 聊天区 / 拉姆面板）
- **角色立绘**：`assets/rem_sprite.jpg`、`assets/ram_sprite.jpg`，自动缩放，缺失时 emoji 占位
- **樱花飘落动画**：`SakuraOverlay` 透明叠加层，35 花瓣粒子，30fps
- **流式输出**：`ReZeroLLMBridge.chat_stream()`，逐 token 更新气泡，首 token 识别角色

### Fixed
- chat_history 双格式兼容、双子回复拆分解析、LLM 调用移入 QThread、补回全部快捷命令

### Notes
- EXE 体积约 56.8MB（Qt 库所致）；宅邸和纸色 + 深棕木色 + 双子蓝粉主题

---

## [V9.5.2] - 2026-07-31 (Docs, Open Source Ready)

### Added
- `LICENSE`：MIT 协议（附注：仅覆盖代码，角色权利归原作者）

### Security
- 开源前敏感信息清理：废弃 key 脱敏为占位符；开发日志中 16 处本机用户名路径替换为 `<项目根目录>`/`<用户目录>`；移除 AI 工具名痕迹。全历史扫描确认 `.env` 与 PAT 从未入库

---

## [V9.5.1] - 2026-07-31 (Docs)

### Removed
- 根目录冗余文件 `English Readme`（内容与 README 重复）

### Changed
- README 重构：移除内嵌的四段英文附录，新增「文档导航」「项目结构」（真实结构），版本路线更新至 V9.5，快速开始改用 `requirements.txt`
- 英文内容各归其位：`docs/README_en.md`（修正失效命令）、`docs/architecture.md`（Mermaid，GitHub 原生渲染）、`CONTRIBUTING.md`（仓库标准位置）、`docs/vision_module_structure.md`（标注为远期愿景，非当前结构）

---

## [V9.5.0] - 2026-07-31 (Feature)

### Added
- **小额冒犯扣分档**：边界试探意图（BOUNDARY_TEST）但未命中高危词 → 好感 -3；「替代品 / 不如姐姐」人格攻击在独立度 -0.04 外追加好感 -1。与既有豁免层自然分层：低中关系真实扣分，DEAR/锁定后被豁免（深爱不会因一句话离开，但独立度照扣）
- **拉姆成长通道**：MENTION_RAM 意图 → 拉姆好感 +1（攻击语境除外），与表扬可叠加至每回合 +2；LLM 模式拉姆阶段从此可达

### Changed
- **独立度增速解耦**：表扬对独立度的带动 0.03 → 0.01，「你就是你」肯定句 0.04 → 0.06——独立度主线回归身份肯定，避免「高独立低好感」错位；破局者彩蛋触发点后移，更符合其低频高重量定位
- `tests/smoke_test.py` 新增数值通道测试（总计 13 项）

---

## [V9.4.0] - 2026-07-31 (Refactor)

### Changed
- **本地模式状态真源收敛**：`RemAI` 的 `_favor/_locked/_independence/_recovery/_oni_stage/_is_reunion/_breaker_triggered/_arc` 全部改为 property 直通 `HardStateEngine`，删除手动同步（`_sync_from_engine`），双真源隐患消除；对外属性名不变，行为等价
- **RamAI 好感统一**：`RamAI(engine=...)` 绑定后好感读写落 `engine.ram_favor`（不绑定时保持旧行为）；本地模式拉姆好感从此可累积并随 GUI 持久化，不再重启归零

### Fixed
- **鬼化余韵死代码**：`RemAI._oni_aftermath` 从未被赋正数导致余韵分支永不触发；改为按「上一回合鬼化阶段」判定（EMERGING/FULL/BRINK 分别对应 1/2/3 回合余韵），计数由引擎统一管理

### Added
- GUI 新增 `/llm`、`/local` 切换指令：就地切换模式并迁移好感/独立度/记忆恢复/锁定/称呼/共同经历
- `tests/smoke_test.py` 新增真源收敛测试（总计 12 项）

---

## [V9.3.1] - 2026-07-31 (Bug Fix)

### Fixed
- 肯定句（「你不是替代品」）不再被意图分类误判为 SELF_DOUBT：「替代品」词从 SELF_DOUBT 词表拆出并加否定免疫，避免误累积连续负面计数导致错误触发轻推

---

## [V9.3.0] - 2026-07-31 (Feature)

### Added
- **长期事件记忆**：状态机自动认定重要时刻并沉淀为事件（首次告知名字 / 好感等级跃迁 / 忠诚锁定 / 拉姆阶段跃迁 / 重逢 / 鬼化 / 破局者 / 身份肯定 / 高风险冲突），零 API 成本
  - 容量 30 条；里程碑类事件（名字/锁定/重逢/破局者）钉住不淘汰
  - `PromptBuilder` 新增「共同经历」小节：钉住 + 最近事件至多 6 条注入 prompt，并明确「不要编造未列出的经历」
  - `memory.json` 新增 `events` 字段；GUI 双模式持久化
- `user_name` 纳入 GUI 持久化（此前重启丢失称呼；也是名字事件去重的前提）
- `tests/smoke_test.py` 新增事件记忆测试（总计 10 项）

### Compatibility
- 旧 `memory.json` 无 `events` 字段 → 默认空列表，无缝兼容
- 本地模式台词逻辑不变（事件照常记录，模板回复不读事件）

---

## [V9.2.7] - 2026-07-31 (Bug Fix)

### Fixed
- **失忆篇防备感不足**：`recovery < 0.4` 的 prompt 指令重写——失忆蕾姆改为「温和但明显的距离感与轻微防备」，不再主动亲昵；新增「高好感数值是沉睡的羁绊，不要直接表现」的数值-行为分离说明，解决高锁定状态下失忆台词过度亲密的矛盾

### Added
- `tests/smoke_test.py` 新增失忆防备指令测试（总计 9 项）

---

## [V9.2.6] - 2026-07-31 (Bug Fix)

### Fixed
- **肯定句误判**：「你不是任何人的替代品」此前触发独立度 -0.04（关键词无语义判断）；现增加否定语境检测，肯定句式使独立度 +0.04（攻击句式行为不变）
- **正面反馈词覆盖过窄**：`PRAISE_KEYWORDS` 扩充（辛苦你们/很棒/做得好/了不起/喜欢你们/爱你/心疼你 等），「辛苦你们了」等变体可正常 +2

### Added
- 温情小档 `WARM_KEYWORDS`（幸运/安心/开心/幸福/温柔/可爱/遇见你们/有你们）：非负面意图下 +1 好感，带否定免疫（「我不开心」不会误触发）
- `tests/smoke_test.py` 新增关键词判定测试（5 条断言），总计 8 项
- `docs/evaluation/`：测试案例库 v1.1 与首轮执行报告

---

## [V9.2.5] - 2026-07-31 (Docs)

### Changed
- 全部开发日志（16 篇）归档至 `docs/devlog/`，`README_old.md` 移至 `docs/`；根目录只保留 `README.md` 与 `CHANGELOG.md`
- 日志文件全部纳入版本管理（此前部分被 .gitignore 排除），作为项目历史完整保留

---

## [V9.2.4] - 2026-07-31 (Chore)

### Added
- `requirements.txt`：`openai` / `python-dotenv` / `pyinstaller` 一键安装
- `tests/smoke_test.py`：无框架冒烟测试（`python tests/smoke_test.py`），覆盖引擎好感与风控、篇章切换、记忆恢复重逢、snapshot 无副作用、MemoryStore 读写、PromptBuilder 约束字段、本地模式对话，共 7 项；不调用 LLM、不产生 API 费用，MemoryStore 用临时目录隔离

---

## [V9.2.3] - 2026-07-31 (Bug Fix)

### Fixed
- EXE（PyInstaller frozen）模式下好感度/聊天记录不再丢失：此前 `MemoryStore` 根目录指向临时解压目录（`sys._MEIPASS`），退出即被系统清理；现默认改存 EXE 同级 `data/` 目录，目录不可写时自动兜底到 `%APPDATA%\ReZeroTwin\data`

### Added
- `shared/config.py` 新增 `get_data_dir()`：统一解析持久化数据目录（frozen / 源码双模式，与 `load_env()` 同一惯例）

### Changed
- `MemoryStore` 默认存储根目录改由 `get_data_dir()` 解析；显式传入 `root_dir` 的行为不变
- 源码运行（`python gui.py`）数据路径不变，仍为项目根 `data/`

---

## [V9.2.2] - 2026-07-31 (Bug Fix)

### Fixed
- GUI 在 LLM 模式下不再假死：`bot.chat()` 网络调用移入后台线程，主线程通过队列 + `root.after` 轮询接收回复；等待期间禁用输入框与发送键，回复到达后自动恢复
- 回复解析与状态持久化逻辑提取为 `_handle_reply()`，local / llm 两种模式共用（行为不变）

---

## [V9.2.1] - 2026-07-31 (Bug Fix)

### Fixed
- 状态查询（`/status` 指令、GUI 状态栏刷新）不再推进状态机：此前显示层调用 `update("")` 会让状态机空转一轮，导致鬼化余韵衰减翻倍、连续负面/拖延计数被悄悄清零

### Added
- `HardStateEngine.snapshot()` 只读快照接口（pure read-only）：输出与 `update()` 相同字段的 `TwinState`，但零副作用，专供显示层使用

---

## [V9.2.0] - 2026-07-31 (Security Fix)

### Security
- `.env` 不再随 PyInstaller 打包进 EXE，杜绝 API Key 随 EXE 分发泄露的风险

### Added
- `shared/config.py`：统一 `.env` 查找逻辑（EXE 同级目录 → 项目根目录 → 当前工作目录）
- GUI 缺少 API Key 时弹窗提示并回退本地模板模式，不再无声退出

### Changed
- `ReZeroTwin.spec` 移除 `.env` 打包项；EXE 运行需在同级目录放置 `.env`
- `main.py` / `gui.py` / `llm/bridge.py` 的 dotenv 加载统一收口到 `shared/config.py`

---

## [V9.1.1] - 2026-07-31 (GUI + EXE Edition)

### Added
- **Tkinter GUI**：`gui.py` 提供聊天窗口，支持回车发送、Shift+回车换行、分角色颜色显示、底部状态栏
- **可双击运行的 EXE**：使用 PyInstaller 打包生成 `dist/ReZeroTwin.exe`
- **JSON 持久化记忆**：`shared/memory_store.py` 保存好感度、拉姆阶段、独立度、记忆恢复、当前篇章、最近聊天记录
- `.env` 自动打包进 EXE，双击即用

### Changed
- `gui.py` 默认启动模式从 `local` 改为 `llm`
- `MemoryStore` 默认值 `mode` 改为 `"llm"`，让程序默认使用 LLM 桥接模式

### Fixed
- 旧 `memory.json` 中 `mode: "local"` 导致 GUI 启动为本地模板模式的问题
- OpenClaw 自带 Python 环境 `sys.path` 不包含用户 site-packages 导致的 `ModuleNotFoundError: No module named 'openai'`
- 多 Python 环境下依赖安装到错误解释器的问题
- Deepseek 402 `Insufficient Balance` 后程序正确提示用户充值

### Notes
- 删除旧 `data/memory.json` 不会损坏 LLM 模式，程序会重新生成默认 `mode: "llm"` 的记忆文件
- PyInstaller 输出末尾的 `Process exited with code 1` 不影响 EXE 正常生成，属于已知现象

---

## [V9.1] - 2026-07-30 (LLM Bridge Edition)

### Added
- **HardStateEngine + LLM Bridge 架构**：实现「硬约束状态机 + 大模型自由表达」的完整分离
- 结构化 System Prompt 构建器，将好感锁定、人格独立度、拉姆评价阶段、托付语义、鬼化状态等转化为自然语言指令
- 支持 DeepSeek / OpenAI / 本地模型（LM Studio / Ollama）的统一接口
- `status` 命令可视化当前全部硬状态

### Changed
- 数值更新完全由状态机控制，LLM 不再拥有修改好感/独立度的权限
- Prompt 温度下调至 0.65，提升人设遵守稳定性

### Design Goal
保留原著逻辑与风控的硬性约束，同时赋予大模型极具灵活性的自然语言灵魂表达。

---

## [V9.0] - 2026-07-30

### Added
- **蕾姆人格独立度** (`identity_independence` 0.0~1.0)
  - 影响自卑台词出现频率与主体性表达
  - 随用户将其视为独立个体而缓慢提升
- **拉姆托付语义**
  - 高评价阶段（勉强认可 / 真正承认）优先使用「把蕾姆托付给你」的表达
- **功能分工机制**
  - 危险 / 自我否定 / 决策场景 → 拉姆更容易主导
  - 情感支持场景 → 蕾姆主导
- **破局者彩蛋**
  - 高独立度 + 忠诚锁定后极低概率触发叙事级台词
- 「从零开始」完整语境专属回应

### Changed
- 双子互动从简单接话升级为有角色功能分工的协作

---

## [V8.0] - 2026-07-30

### Added
- **拉姆评价阶段系统**（可疑 → 观察中 → 还算守规矩 → 勉强认可 → 真正承认）
- **主动性规则**
  - 强制触发：鬼化、高风险、被点名
  - 概率触发：自我否定、拖延、连续负面
- 拉姆可先于蕾姆开口，形成真正的双子互动节奏

### Changed
- 拉姆从「接话机器」升级为有独立判断与主动权的角色

---

## [V7.0] - 2026-07-30

### Added
- **好感忠诚锁定机制**
  - DEAR 以上普通负面几乎不扣分
  - BELOVED 后进入锁定，仅严重越界可小幅扣分，且不会跌破关键阈值
- 结构化上下文摘要（情绪轨迹 + 未完成话题 + 最近扣分原因）
- 拉姆独立好感与评价文本
- 拖延意图识别，并与轻推逻辑绑定

### Fixed
- 好感「莫名消失」问题（原著后期忠诚感落地）

---

## [V6.0] - 2026-07-30

### Added
- 动态用户画像（稳定特征 / 会话状态 / 行为模式）
- 轻量意图识别（倾诉、自我否定、拖延、快速回应、边界试探）
- 高好感「轻推」逻辑（连续负面时触发原著式「从零开始」压力）
- 帝国篇记忆恢复进度（0→1）与过渡期台词
- 拉姆帝国篇远程思念与重逢反应
- 鬼化三阶段（角初现 → 完全解放 → 失控边缘）

### Changed
- 短时记忆升级为可影响回复策略的上下文

---

## [V5.0] - 2026-07-30

### Added
- 帝国篇完整失忆状态对话库
- 鬼化余韵系统
- 短时记忆真正影响默认回复语气

### Changed
- 对话库按篇章与恢复状态动态切换

---

## [V4.0] - 2026-07-30

### Fixed
- FavorLevel 字符串比较导致的高好感分支失效（改为 IntEnum）
- `or True` 导致双子永远触发的问题
- 「您」暴力全量替换问题（改为占位符 `{address}`）
- 风控与记忆提取顺序（先风控，后提取，防污染）

### Added
- 严格第三人称自称
- 短时记忆框架
- 更完整的原著风控关键词

---

## [Initial] - 用户原始版本

基础状态机 + 关键词规则 + 简单双子联动。具备可运行骨架，但存在多处逻辑漏洞与原著还原不足。
