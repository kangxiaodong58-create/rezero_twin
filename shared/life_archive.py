"""关系资产导出/导入（V15.0「年轮」M4）："时间不能丢"的工程契约。

设计依据：docs/design/V15_0_年轮_关系资产版本构思_2026-08-29.md §3.5。

定位：任何未来的换栈、换模型、重装，迁移的单位是「关系资产包」而不是
数据库碎片。导出 = data/ 中**关系资产**的 curated 打包（含清单与校验和）；
导入 = 校验 → 备份现状 → 恢复，任何一步不干净即整体拒绝（绝不半导）。

打包范围（关系资产，curated）：
- memory.json（硬状态 + 世界状态——V10.4 起单管线）
- conversations.db（含 -wal/-shm）｜life.db（含 -wal/-shm）
- album/**（纪念卡）｜sprites/**（用户自定义立绘）
明确排除：gui.log/crash.log（噪音）、vignette_cache.json（可再生缓存）、
incidents/（取证现场，属调试证据非关系资产）。

安全纪律：
- 导入前全量校验：manifest schema / 条目路径安全（拒绝绝对路径、..、
  盘符、反斜杠）/ 逐文件 sha256 对账；
- 覆盖前先把目标现状打包备份（Backup-*.zip），备份失败即中止导入；
- 纯 Python，无 PySide6；tools/export_life.py、tools/import_life.py 为 CLI。
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from .config import get_data_dir

SCHEMA = "rezero_life_v1"
ARCHIVE_PREFIX = "ReZeroTwin-Life"
BACKUP_PREFIX = "ReZeroTwin-Backup"

INCLUDE_FILES = (
    "memory.json",
    "conversations.db", "conversations.db-wal", "conversations.db-shm",
    "life.db", "life.db-wal", "life.db-shm",
)
INCLUDE_DIRS = ("album", "sprites")


class LifeArchiveError(Exception):
    """导出/导入失败（原因在消息中；工具层转为退出码）。"""


# ── 内部工具 ─────────────────────────────────────────────────────

def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _payload_files(data_dir: str) -> List[str]:
    """curated 相对路径清单（仅实际存在的文件；目录递归）。"""
    rel: List[str] = []
    for name in INCLUDE_FILES:
        if os.path.isfile(os.path.join(data_dir, name)):
            rel.append(name.replace(os.sep, "/"))
    for d in INCLUDE_DIRS:
        base = os.path.join(data_dir, d)
        if os.path.isdir(base):
            for root, _dirs, files in os.walk(base):
                for f in sorted(files):
                    full = os.path.join(root, f)
                    rel.append(os.path.relpath(full, data_dir).replace(os.sep, "/"))
    return sorted(rel)


def _safe_entry(name: str) -> bool:
    """zip 条目路径安全：拒绝绝对路径 / .. / 盘符 / 反斜杠。"""
    if not name or name.startswith(("/", "\\")):
        return False
    if ":" in name or "\\" in name:
        return False
    parts = name.split("/")
    return all(p not in ("", ".", "..") for p in parts)


def _count_sqlite(db_path: str, table: str) -> int:
    """只读计数（库被锁/损坏时返回 -1——清单尽力而为，不阻断导出）。"""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return -1


def _record_forensic(event: str, summary: str) -> None:
    try:
        from runtime.forensic import record
        record(event, component="life_archive", payload_summary=summary[:120])
    except Exception:
        pass


# ── 导出 ─────────────────────────────────────────────────────────

def export_life(*, dest_dir: Optional[str] = None,
                data_dir: Optional[str] = None) -> str:
    """把关系资产打包为 ReZeroTwin-Life-YYYYMMDD-HHMMSS.zip，返回包路径。

    包内第一个条目是 manifest.json（schema/时间/计数/逐文件 sha256）。
    """
    data_dir = data_dir or get_data_dir()
    if not os.path.isdir(data_dir):
        raise LifeArchiveError(f"数据目录不存在: {data_dir}")
    dest_dir = dest_dir or os.path.dirname(data_dir) or "."
    os.makedirs(dest_dir, exist_ok=True)

    rel_files = _payload_files(data_dir)
    if "memory.json" not in rel_files and "conversations.db" not in rel_files:
        raise LifeArchiveError("数据目录中没有任何关系资产（memory.json/conversations.db 均缺失）")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = os.path.join(dest_dir, f"{ARCHIVE_PREFIX}-{stamp}.zip")

    manifest: Dict[str, Any] = {
        "schema": SCHEMA,
        "app": "ReZeroTwin",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "counts": {
            "messages": _count_sqlite(os.path.join(data_dir, "conversations.db"), "messages"),
            "life_events": _count_sqlite(os.path.join(data_dir, "life.db"), "life_events"),
            "files": len(rel_files),
        },
        "files": [],
    }
    for rel in rel_files:
        full = os.path.join(data_dir, rel)
        manifest["files"].append(
            {"path": rel, "size": os.path.getsize(full), "sha256": _sha256(full)})
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            info = zipfile.ZipInfo("manifest.json", date_time=time.localtime()[:6])
            zf.writestr(info, json.dumps(manifest, ensure_ascii=False, indent=1))
            for rel in rel_files:
                zf.write(os.path.join(data_dir, rel), arcname=rel)
    except Exception as e:
        try:
            os.remove(zip_path)
        except Exception:
            pass
        raise LifeArchiveError(f"打包失败: {e}") from e

    _record_forensic("LIFE_EXPORT", f"files={len(rel_files)} -> {os.path.basename(zip_path)}")
    return zip_path


# ── 校验 ─────────────────────────────────────────────────────────

def validate_archive(zip_path: str) -> Dict[str, Any]:
    """全量校验（schema/路径安全/逐文件 sha256）。返回 manifest；不合法抛错。"""
    if not os.path.isfile(zip_path):
        raise LifeArchiveError(f"包不存在: {zip_path}")
    try:
        zf = zipfile.ZipFile(zip_path)
    except Exception as e:
        raise LifeArchiveError(f"不是有效的 zip: {e}") from e
    with zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise LifeArchiveError("缺少 manifest.json（不是关系资产包）")
        try:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except Exception as e:
            raise LifeArchiveError(f"manifest 解析失败: {e}") from e
        if manifest.get("schema") != SCHEMA:
            raise LifeArchiveError(
                f"schema 不匹配: 期望 {SCHEMA}，实际 {manifest.get('schema')!r}")
        bad = [n for n in names if not _safe_entry(n)]
        if bad:
            raise LifeArchiveError(f"包含不安全路径: {bad[:3]}")
        listed = {f["path"]: f for f in manifest.get("files", [])}
        payload = [n for n in names if n != "manifest.json"]
        missing = [p for p in payload if p not in listed]
        if missing:
            raise LifeArchiveError(f"清单外文件: {missing[:3]}")
        for rel, meta in listed.items():
            if rel not in names:
                raise LifeArchiveError(f"清单文件缺失: {rel}")
            digest = hashlib.sha256(zf.read(rel)).hexdigest()
            if digest != meta.get("sha256"):
                raise LifeArchiveError(f"校验和不匹配（包被改动）: {rel}")
        return manifest


# ── 导入 ─────────────────────────────────────────────────────────

def import_life(zip_path: str, *, data_dir: Optional[str] = None,
                dry_run: bool = False) -> Dict[str, Any]:
    """校验 → 备份现状 → 恢复。dry_run=True 只出报告不写任何文件。

    返回 {restored, backup, counts, dry_run}。任何校验/备份失败抛
    LifeArchiveError——宁可拒绝，绝不半导。
    """
    data_dir = data_dir or get_data_dir()
    manifest = validate_archive(zip_path)
    rel_files = [f["path"] for f in manifest["files"]]

    # 备份目标现状（仅将被覆盖的 curated 文件）
    existing = [rel for rel in _payload_files(data_dir)
                if rel in set(rel_files)]
    backup_path = None
    if existing and not dry_run:
        parent = os.path.dirname(data_dir) or "."
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = os.path.join(parent, f"{BACKUP_PREFIX}-{stamp}.zip")
        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for rel in existing:
                    zf.write(os.path.join(data_dir, rel), arcname=rel)
        except Exception as e:
            raise LifeArchiveError(f"备份失败，已中止导入: {e}") from e

    if not dry_run:
        os.makedirs(data_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for rel in rel_files:
                target = os.path.join(data_dir, rel)
                os.makedirs(os.path.dirname(target) or data_dir, exist_ok=True)
                with zf.open(rel) as src, open(target, "wb") as dst:
                    dst.write(src.read())

    _record_forensic("LIFE_IMPORT",
                     f"dry_run={dry_run} files={len(rel_files)} backup={os.path.basename(backup_path) if backup_path else '-'}")
    return {
        "restored": rel_files,
        "backup": backup_path,
        "counts": manifest.get("counts", {}),
        "dry_run": dry_run,
    }
