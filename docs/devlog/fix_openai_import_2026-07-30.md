# openai 导入问题修复记录

## 问题

用户反馈运行 `python main.py --mode llm` 或 `llm/bridge.py` 时报错：

```
ImportError: 请先安装 openai 库：pip install openai
```

但 `python -c "import openai"` 正常，`pip show openai` 也显示已安装。

## 根因分析

1. `openai` 实际安装在用户 site-packages：
   `<用户目录>\AppData\Roaming\Python\Python311\site-packages\openai`
2. 当前 `python` 指向 OpenClaw 自带解释器：`D:\Q-claw\QClaw\v0.2.35.624\resources\python\python.exe`
3. 该解释器的 `sys.path` 已包含用户 site-packages，所以常规命令下能导入。
4. 问题出现在 `llm/bridge.py` 的 `from openai import OpenAI` 处；之前 `try/except ImportError` 把 **任何** 导入失败都伪装成 openai 未安装，而真正的底层异常被 `from _e` 隐藏。

## 已做的修复

- 在 `llm/bridge.py` 开头加入项目根目录 `sys.path` 注入，避免 `shared` 导入失败被误判为 openai 错误。
- 将 `openai` 的导入错误单独捕获并 `raise ... from _e`，保留原始异常链。
- 移除了 `if OpenAI is None: raise ...` 的多余判断。

## 当前验证结果

在同一终端下执行：

```powershell
cd <项目根目录>
python main.py --mode llm
```

输出：
```
Re:Zero 双子系统已启动（LLM 桥接模式）
输入 status 查看硬状态 | empire / mansion / recover 0.7 切换状态 | quit 退出

小东：
```

程序已正常启动。

## 如果仍报错

请把完整的命令和完整 Traceback 复制给我。若底层是网络或 SSL 问题，会被 `openai` 抛出其他异常（而非 `ImportError`），需要单独排查。
