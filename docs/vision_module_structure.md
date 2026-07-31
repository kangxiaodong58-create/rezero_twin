# 未来模块结构愿景（非当前结构）

> 本文是社区讨论中提出的远期目录结构设想，**不代表仓库当前布局**。
> 当前实际结构见 README.md 的「项目结构」一节。
> 按照项目演进原则（渐进式、不大规模重构），只有在收益明确时才会考虑朝此方向小步迁移。

```text
rezero-twin-system/
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── requirements.txt
├── .env.example
│
├── rezero/
│   ├── __init__.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── enums.py              # StoryArc, FavorLevel, RamStage, OniStage, Intent...
│   │   ├── state.py              # TwinState dataclass
│   │   └── hard_engine.py        # HardStateEngine (numerical & logic core)
│   │
│   ├── characters/
│   │   ├── __init__.py
│   │   ├── rem.py                # Rem-specific logic & independence
│   │   └── ram.py                # Ram stages, initiative, entrustment
│   │
│   ├── prompt/
│   │   ├── __init__.py
│   │   └── builder.py            # PromptBuilder
│   │
│   ├── llm/
│   │   ├── __init__.py
│   │   └── bridge.py             # ReZeroLLMBridge
│   │
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
│
├── docs/
│   ├── architecture.md           # Mermaid diagrams + design notes
│   └── design_insights.md        # Longer reflections
│
├── examples/
│   └── basic_chat.py
│
└── tests/
    ├── test_favor_lock.py
    ├── test_independence.py
    └── test_ram_stages.py
```

### Module Responsibility Summary

| Module              | Responsibility                                      | Should NOT contain          |
|---------------------|-----------------------------------------------------|-----------------------------|
| `core/hard_engine.py` | All numerical updates, locks, stage transitions    | Any natural language        |
| `core/state.py`     | Pure data snapshot (`TwinState`)                    | Business logic              |
| `characters/rem.py` | Independence logic, Rem-specific reactions          | Ram logic                   |
| `characters/ram.py` | Evaluation stages, initiative, entrustment lines    | Rem favor logic             |
| `prompt/builder.py` | Convert `TwinState` → high-quality system prompt    | State mutation              |
| `llm/bridge.py`     | API calls, history management, orchestration        | Hard rules                  |
