"""本地长期记忆存储。

将用户昵称、好感度、拉姆阶段、鬼化、记忆恢复进度、聊天历史等
保存到 data/memory.json 中，程序重启后可恢复。

V16.1（M1 状态持久化止血，架构审批强制项）：
- **原子写**：先写 `.tmp` → flush+fsync → 备份旧档到 `.bak` → `os.replace` 落盘。
  写盘中断（掉电/崩溃）只可能留下 `.tmp`，主档与备份都不被破坏。
- **损坏恢复绝不静默**：主档不可解析 → 尝试 `.bak` 恢复并原子写回主档，记 WARNING；
  主档与备份皆损坏 → 坏档改名 `memory.json.corrupt-<时间戳>` 保留证据 + 告警，
  之后才回落默认值（此前是静默回落 = 用户关系进度无声清零）。
- **schema_version**：新档写 2；旧档无此键按 1 处理（不做破坏性迁移）。
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import config

SCHEMA_VERSION = 2

log = logging.getLogger("rezero.memory_store")


def _record(event: str, summary: str) -> None:
    """取证黑匣子埋点（未初始化时 no-op，任何失败静默）。"""
    try:
        from runtime.forensic import record
        record(event, component="memory_store", payload_summary=summary)
    except Exception:
        pass


class MemoryStore:
    def __init__(self, root_dir: Optional[str] = None) -> None:
        if root_dir is not None:
            # 显式指定：保持原有语义（root_dir 下建 data/）
            self.root = root_dir
            self.data_dir = os.path.join(self.root, "data")
        else:
            # 默认：统一解析（frozen → EXE 同级 data/；源码 → 项目根 data/）。
            # V16.1：必须「调用时」解析——此前 import 期绑定 get_data_dir，
            # 测试打补丁 shared.config.get_data_dir 无效 → 测试写真实 data/。
            self.data_dir = config.get_data_dir()
            self.root = os.path.dirname(self.data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self.path = os.path.join(self.data_dir, "memory.json")
        self.backup_path = self.path + ".bak"

    # ── 内部 ──────────────────────────────────────────────────────

    @staticmethod
    def _read_json(path: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """返回 (解析成功, 数据)。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return (False, None)
        if isinstance(data, dict):
            return (True, data)
        return (False, None)

    @staticmethod
    def _defaults() -> Dict[str, Any]:
        return {
            "user_name": None,
            "favor": 15,
            "ram_favor": 8,
            "independence": 0.25,
            "recovery": 1.0,
            "arc": "mansion_era",
            "chat_history": [],
            "events": [],
        }

    # ── 读 ────────────────────────────────────────────────────────

    def load(self) -> Dict[str, Any]:
        """读取存档；损坏时按「备份恢复 → 留证告警 → 默认值」三级降级。"""
        data: Dict[str, Any] = {}
        exists = os.path.isfile(self.path)
        ok, loaded = self._read_json(self.path) if exists else (False, None)

        if ok and loaded is not None:
            data = loaded
        elif exists:
            bak_ok, bak = self._read_json(self.backup_path)
            if bak_ok and bak is not None:
                msg = (f"memory.json 损坏，已从备份恢复"
                       f"（favor={bak.get('favor')}）: {self.path}")
                log.warning(msg)
                _record("SAVE_REPAIRED_FROM_BACKUP", msg[:200])
                data = bak
                try:
                    self.save(dict(data))  # 原子写回，主档修复
                except Exception as e:  # pragma: no cover - 写回失败不阻断启动
                    log.warning("备份恢复后写回主档失败: %s", e)
            else:
                corrupt = f"{self.path}.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                try:
                    os.replace(self.path, corrupt)
                except OSError:
                    corrupt = "(改名失败)"
                msg = (f"memory.json 与备份均损坏，已保留证据 {corrupt}，"
                       "本次以默认值启动（用户数据可能丢失）")
                log.warning(msg)
                _record("SAVE_CORRUPTED", msg[:200])
                data = {}

        for key, value in self._defaults().items():
            data.setdefault(key, value)
        return data

    # ── 写（原子 + 备份轮转）──────────────────────────────────────

    def save(self, data: Dict[str, Any]) -> None:
        payload = dict(data)
        payload.setdefault("schema_version", SCHEMA_VERSION)

        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

        # 备份上一份「成功落盘」的档（此时主档仍完好；最坏情况 .bak 与主档同代）
        if os.path.isfile(self.path):
            try:
                shutil.copy2(self.path, self.backup_path)
            except OSError as e:
                log.warning("存档备份失败（不影响本次写入）: %s", e)

        os.replace(tmp_path, self.path)

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def append_chat(self, role: str, content: str) -> None:
        data = self.load()
        history: List[Dict[str, str]] = data.get("chat_history", [])
        history.append({"role": role, "content": content})
        # 只保留最近 200 条
        if len(history) > 200:
            history = history[-200:]
        data["chat_history"] = history
        self.save(data)
