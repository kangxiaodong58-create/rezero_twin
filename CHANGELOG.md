# Changelog

All notable changes to the **Re:Zero Twin System** (Ram & Rem) are documented in this file.

本项目采用语义化版本记录，重点追踪「状态机深度」与「角色灵魂完整度」的演进。

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
