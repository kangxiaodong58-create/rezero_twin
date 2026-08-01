# Changelog

All notable changes to the **Re:Zero Twin System** (Ram & Rem) are documented in this file.

本项目采用语义化版本记录，重点追踪「状态机深度」与「角色灵魂完整度」的演进。

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
