"""统一的环境变量加载逻辑。

v9.2.0 起 .env 不再打包进 EXE，改为运行时按以下顺序查找：

1. PyInstaller onefile 原始 EXE 所在目录的 .env
2. PyInstaller onefile 临时解压目录的 .env（兼容把 .env 放一起打包的情况）
3. 源码运行：项目根目录的 .env
4. 当前工作目录的 .env
5. 用户主目录的 .env（最后兜底）

找到第一个存在的文件即加载；都找不到则静默跳过
（由调用方在读取 DEEPSEEK_API_KEY 时给出友好报错）。
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional


def _candidate_paths() -> List[str]:
    paths: List[str] = []

    # 1. PyInstaller onefile 模式下，原始 EXE 所在目录
    # sys.executable 在 onefile 中通常指向临时目录，但 sys.argv[0] 仍指向原 EXE 路径
    if getattr(sys, "frozen", False):
        exe_path = sys.argv[0] if len(sys.argv) > 0 else sys.executable
        paths.append(os.path.join(os.path.dirname(os.path.abspath(exe_path)), ".env"))
        # 临时解压目录（兼容旧版打包方式）
        paths.append(os.path.join(os.path.dirname(sys.executable), ".env"))
    else:
        # 源码运行：gui.py / main.py 所在目录
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        paths.append(os.path.join(project_root, ".env"))

    # 当前工作目录兜底
    paths.append(os.path.join(os.getcwd(), ".env"))
    # 用户主目录兜底
    paths.append(os.path.join(os.path.expanduser("~"), ".env"))

    return paths


def load_env(verbose: bool = False) -> Optional[str]:
    """加载第一个找到的 .env 文件，返回实际加载路径；未找到返回 None。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    for path in _candidate_paths():
        if os.path.isfile(path):
            load_dotenv(path)
            if verbose:
                print(f"[config] loaded .env: {path}")
            return path

    if verbose:
        print("[config] no .env found in candidates:")
        for path in _candidate_paths():
            print(f"  - {path}")
    return None
