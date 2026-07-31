# Re:Zero 双子系统

基于两份文档代码文本整合实现的拉姆 & 蕾姆对话系统。

## 项目结构

```
rezero_twin/
├── main.py              # 统一入口脚本
├── README.md            # 项目说明
├── assets/              # 静态资源 / 配置文件占位
├── shared/              # 共享状态与 Prompt 组件
│   ├── state.py         # 枚举、硬状态引擎、TwinState 快照
│   ├── prompts.py       # PromptBuilder / ResponseLibrary / RamAI 模板
│   └── __init__.py
├── local/               # 本地模板模式（不依赖 LLM）
│   ├── rem_ai.py        # 本地蕾姆 AI
│   ├── twin_system.py   # 本地双子总控
│   └── __init__.py
└── llm/                 # LLM 桥接模式（依赖 OpenAI 兼容 API）
    ├── bridge.py        # ReZeroLLMBridge
    └── __init__.py
```

## 运行方式

### 本地模板模式（默认，无需 API Key）

```powershell
python rezero_twin/main.py
# 或
python rezero_twin/main.py --mode local
```

### LLM 桥接模式（需要 DEEPSEEK_API_KEY 环境变量）

```powershell
$env:DEEPSEEK_API_KEY = "sk-xxx"
python rezero_twin/main.py --mode llm
```

## 交互指令

| 指令 | 说明 |
|------|------|
| `status` | 查看当前硬状态 |
| `empire` | 切换至帝国篇（失忆） |
| `mansion` | 切换回宅邸篇 |
| `late` | 切换至后期篇章 |
| `recover 0.6` | 设置记忆恢复进度 |
| `recover 1.0` | 完全恢复记忆 |
| `quit` | 退出 |

## 已实现功能

- [x] 拉姆 / 蕾姆好感与阶段系统
- [x] 鬼化阶段与余韵
- [x] 帝国篇 / 宅邸篇 / 后期篇章切换
- [x] 记忆恢复进度控制
- [x] 高风险越界风控
- [x] 名字自动提取
- [x] 连续负面 / 拖延检测与轻推
- [x] 本地模板回复 + LLM 桥接双模式
- [x] 统一入口与项目文件夹归类
