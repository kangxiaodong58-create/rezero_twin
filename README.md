: Zero Twin System

> 拉姆 & 蕾姆双子女仆状态机 + 大模型灵魂表达系统
> 从规则引擎到「硬约束 × 软表达」的完整演进实践

一个以《Re:从零开始的异世界生活》双子女仆为核心的角色扮演系统。  
项目经历了从纯规则状态机 → 深度心理状态机 → 状态机与 LLM 桥接的完整迭代，最终目标是：

**既保留原著逻辑、数值增长与风控的硬性约束，又赋予大模型极具灵活性与灵魂的自然语言表达能力。**

[English README](docs/README_en.md) ｜ [架构图](docs/architecture.md) ｜ [贡献指南](CONTRIBUTING.md) ｜ [开发日志](docs/devlog/) ｜ [测试评估](docs/evaluation/)

---

## 项目愿景

在角色 AI 领域，常见两种极端：

- 纯规则系统：稳定但死板，缺乏灵魂
- 纯 LLM 系统：灵活但容易崩人设、忘记设定、数值混乱

本项目探索第三条路：**用状态机守护边界与成长逻辑，用大模型释放语言与情感的表现力**。

---

## 核心设计原则

1. **数值与逻辑必须由状态机掌控**（好感、独立度、评价阶段、鬼化等）
2. **大模型只负责「如何说」，不负责「变成什么」**
3. **关系是有结构的**（而非单纯好感加减）
   - 蕾姆：情感救赎 ↔ 人格独立
   - 拉姆：观察 → 认可 → 托付
4. **高好感后应具备「忠诚锁定」**，符合原著后期情感质感
5. **双子必须有功能分工**，而非简单轮流说话

---

## 架构概览

```
用户输入
 ↓
HardStateEngine（硬约束层）
 ├─ 意图识别
 ├─ 好感 / 独立度 / 拉姆阶段安全更新
 ├─ 鬼化阶段机
 ├─ 上下文摘要 + 长期事件记忆（v9.3+）
 └─ 输出 TwinState 快照
 ↓
PromptBuilder（状态 → 自然语言指令）
 ↓
LLM（DeepSeek / OpenAI / 本地模型）
 ↓
符合当前状态的双子回复
```

Mermaid 版架构图见 [docs/architecture.md](docs/architecture.md)。

---

## 版本演进路线（经验沉淀）

| 版本 | 核心突破 | 解决的关键问题 | 可复用经验 |
|------|------------------------------|------------------------------|--------------------------------|
| V4 | 修复基础崩溃点 + 第三人称 | 逻辑漏洞、替换粗暴 | 枚举比较、占位符、执行顺序 |
| V5 | 帝国篇失忆 + 鬼化细节 | 篇章差异缺失 | 状态分支对话库 |
| V6 | 动态画像 + 意图 + 轻推 | 只会安慰不会推动 | 会话状态与行为模式 |
| V7 | 好感忠诚锁定 | 好感莫名回落 | 高价值关系的「抗衰减」设计 |
| V8 | 拉姆评价阶段 + 主动性 | 拉姆沦为接话机器 | 配角也需要独立成长曲线 |
| V9 | 托付语义 + 人格独立度 + 破局者 | 关系缺乏结构与叙事感 | 从「好感」升级到「关系阶段」 |
| V9.1 | 状态机 × LLM 桥接 | 规则死板 vs LLM 失控 | 硬软分离的可落地范式 |
| V9.1.1 | GUI + EXE 落地 | 终端门槛高 | 状态持久化 + 一键运行 |
| V9.2 | 安全修复 + 状态快照 + 线程化 + 持久化路径 | 密钥入包 / 状态空转 / GUI 假死 / EXE 失忆 | 打包产物的路径纪律（frozen/源码双模式） |
| V9.3 | 长期事件记忆 | LLM 编造共同经历 | 重要时刻由状态机认定，零 API 成本 |
| V9.4 | 本地模式真源收敛 | 双状态真源隐患、余韵死代码 | 镜像优于同步 |
| V9.5 | 数值通道精细化 | 负反馈单层、增速耦合 | 既有豁免层 + 小额扣分源 = 自然分层 |
| V10.0~V10.3 | PySide6 宅邸 UI + 世界状态 | Tkinter 视觉上限、存储耦合、天气重启跳变 | UI 线程安全纪律；世界状态注入 prompt |
| V10.4 | 天气确定性实质修复 + Vignette L0-L3 | hash() 进程随机盐、引言无缓存无校验 | 确定性算法必须跨进程稳定（MD5）；生成型功能配多级兜底网 |
| V10.5 | LLM 上下文恢复 + ResponseValidator 收口 | 重启后上下文丢失、LLM 偶发越界输出 | 对话历史由 ConversationStore 统一恢复；生成后校验应尽早介入 |
| V10.6 | 最小世界事件系统 | `active_event` 长期为空、世界氛围缺少变化 | 轻量确定性事件池 + TTL，不侵入硬状态 |
| V10.7.0 | PromptBuilder 最小拆分 | `build()` 单体方法过长 | 私有静态小节方法，签名与输出不变 |
| V10.7.1 | 活跃事件可见化 + 测试补强 | 事件仅进 Prompt，GUI 不可见；校验边界未覆盖 | 状态栏只读展示；红队边界用例补强 |

---

## 快速开始（LLM 版本）

### 安装依赖

```powershell
pip install -r requirements.txt
```

### 配置 API Key

在项目根目录创建 `.env` 文件：

```env
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> 使用打包版 EXE 时，把 `.env` 放在 `ReZeroTwin.exe` 同目录即可（v9.2.0 起密钥不再嵌入 EXE）。

### 终端启动

```powershell
python main.py
# 或指定模式
python main.py --mode llm
```

### GUI 启动

```powershell
python gui.py
```

### 常用指令

- `status`：查看当前全部硬状态
- `empire` / `mansion` / `late`：切换篇章
- `recover 0.6`：设置记忆恢复进度
- `/llm` / `/local`（GUI 内）：切换 LLM 桥接 / 本地模板模式，状态自动迁移
- `quit`：退出

### 冒烟测试

```powershell
python tests/smoke_test.py
```

23 项零 API 回归（引擎数值、事件记忆、持久化、prompt 约束、PromptBuilder 小节、本地对话、天气确定性、Vignette 校验、上下文恢复、ResponseValidator、活跃事件等）。

---

## 项目结构

```text
rezero_twin/
├── main.py               # CLI 入口（--mode local|llm）
├── gui.py                # PySide6 GUI（/llm /local 可切换）
├── requirements.txt
├── ReZeroTwin.spec       # PyInstaller 打包配置
├── shared/               # 共享核心
│   ├── state.py          # HardStateEngine 硬约束引擎 + TwinState + 事件记忆
│   ├── prompts.py        # PromptBuilder + 本地词库 + RamAI
│   ├── memory_store.py   # JSON 持久化
│   └── config.py         # .env 与数据目录解析（frozen/源码双模式）
├── llm/bridge.py         # LLM 桥接（DeepSeek 等）
├── local/                # 本地模板模式（RemAI + 双子总控）
├── tests/smoke_test.py   # 冒烟测试（23 项，零 API）
└── docs/
    ├── devlog/           # 开发日志（全部版本记录）
    ├── evaluation/       # 测试案例库与评估报告
    ├── architecture.md   # 架构图（Mermaid）
    ├── README_en.md      # English README
    └── vision_module_structure.md  # 未来结构愿景（非当前结构）
```

---

## 打包为可双击运行的 EXE

使用 PyInstaller：

```powershell
pyinstaller ReZeroTwin.spec --clean
```

打包完成后，`dist\ReZeroTwin.exe` 会生成。**v9.2.0 起 `.env` 不再打包进 EXE**：请把包含 `DEEPSEEK_API_KEY` 的 `.env` 复制到 `ReZeroTwin.exe` 同目录，再双击运行。缺少 `.env` 时程序会弹窗提示并回退到本地模板模式，不会闪退。窗口标题为 **"Re:Zero 双子系统"**，状态栏显示当前模式与状态。

**数据保存位置（v9.2.3 起）**：好感度、聊天记录、共同经历等持久化数据保存在 EXE 同级 `data\` 目录（源码运行时为项目根 `data\`），删除该目录即可重置记忆。若 EXE 所在目录不可写（如 Program Files），会自动改存 `%APPDATA%\ReZeroTwin\data\`。

**重启后上下文保留（v10.5.0+）**：LLM 模式下，最近 8 轮对话会自动从 `data\conversations.db` 恢复到 LLM 上下文，重启程序后双子仍能引用上一轮内容。本地模板模式不受影响。

> 注意：PyInstaller 输出末尾的 `Process exited with code 1` 不影响 EXE 正常生成，属于已知现象。

---

## 常见问题

### Q: 双击 EXE 后是本地模板模式，没有调用 Deepseek API
A: 删除旧的本地模式记忆文件：

```powershell
Remove-Item data\memory.json -ErrorAction SilentlyContinue
```

程序会重新生成 `mode: "llm"` 的默认记忆文件，再次启动即为 LLM 桥接模式。也可以在窗口里直接输入 `/llm` 切换。

### Q: 提示 `Insufficient Balance`
A: Deepseek 账号余额不足，需要充值。

### Q: 提示 `ModuleNotFoundError: No module named 'openai'`
A: 确保在当前 PowerShell 使用的 Python 环境中安装依赖：

```powershell
pip install -r requirements.txt
```

注意 Python 环境可能与系统 Python 不一致。

---

## 状态一览（V10.7+）

- 蕾姆好感 + 忠诚锁定（分级豁免：小额冒犯低关系生效、深爱豁免）
- 人格独立度（身份肯定驱动，影响自卑与主体性）
- 拉姆独立好感 + 五阶段评价（提及与表扬双通道）
- 鬼化三阶段 + 余韵
- 帝国篇记忆恢复进度
- 长期事件记忆（重要时刻注入 prompt，防编造共同经历）
- 结构化上下文摘要
- 轻推与拖延检测
- 破局者彩蛋（低频高重量）
- LLM 对话上下文恢复（v10.5.0+）：最近 8 轮从 SQLite 恢复到 LLM 上下文
- ResponseValidator 生成后校验（v10.5.1+）：拦截 OOC、第一人称、格式崩溃、好感暴露
- 世界状态活跃事件（v10.6.0+）：宅邸日常氛围事件注入开场与 Prompt
- PromptBuilder 模块化拆分（v10.7.0+）：`build()` 内部按小节拆分为私有静态方法，输出不变
- GUI 状态栏活跃事件可见化（v10.7.1+）：底部状态栏只读展示当前事件摘要

---

## 设计启示（给未来项目的借鉴）

1. **先把「关系结构」想清楚，再写代码**
   好感只是表面，真正重要的是角色之间如何相互定义。

2. **高价值状态需要抗衰减设计**
   一旦角色付出了深度信任，就不该因为日常摩擦轻易回退。

3. **配角也值得独立状态机**
   拉姆的评价阶段与主动性，显著提升了整体体验的层次感。

4. **状态机负责「真」，LLM 负责「美」**
   这是目前较可持续的角色 AI 架构方向。

5. **彩蛋与叙事节点可以很低频，但必须有重量**
   破局者台词触发率极低，却能形成强烈的情感记忆点。

---

## 未来可能方向

- [x] 流式输出支持（V10.0.0 起 `chat_stream()` 已实现）
- [ ] 更细粒度的 post-generation 校验（防止 LLM 偶尔越界）
- [ ] 多轮上下文摘要的向量化记忆
- [ ] 拉姆与蕾姆的独立短期目标
- [ ] 可视化状态面板（WebUI）
- [ ] 支持更多原著后期篇章锚点

---

## 已知遗留问题

以下问题已识别，但不在本阶段修复范围内：

- **PromptBuilder 小节方法为私有静态**：`build()` 已在 V10.7.0 拆分为 6 个 `_build_*` 私有静态方法，签名与输出不变；若后续需跨类复用或单测小节，可提升可见性或抽取独立类，当前保持最小拆分。
- **长期事件语义召回仍较弱**：事件按类型与摘要注入 prompt，缺乏基于语义的动态召回；大模型仍可能引用不相关经历。
- **GUI 体积与启动性能**：PySide6 + 全量 openai 依赖使 EXE 偏大，后续可考虑按需延迟加载或剥离非运行时依赖。
- **打包验证依赖完整 GUI 环境**：本环境未安装 PySide6 / PyInstaller，EXE 构建与 GUI 启动验证尚未执行。
- **流式输出校验滞后**：ResponseValidator 在完整回复生成后校验，流式失败时用户可能已看到部分内容，这是当前设计下的已知行为。
- **活跃事件中途不刷新**：事件仅在 `WorldState.load_or_create()` 时生成/过期，长会话中途不会切换，符合 V10.6 最小范围定义。

## 致谢与声明

本项目为个人学习与角色理解实践，所有角色与设定归属于《Re:从零开始的异世界生活》原作者与相关权利方。

仅用于技术探索与同人交流。

---

**维护者**：小东 & K 🦊  
**最后更新**：2026-08-01
