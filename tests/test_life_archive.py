"""V15.0「年轮」M4 测试：关系资产导出/导入。

验收口径（构思 §五 M4）：往返等价断言；损坏包拒绝；路径穿越拒绝；
覆盖前备份；dry-run 零写入。

安全设计回顾：
- 导入前全量校验（manifest schema / 路径安全 / 逐文件 sha256）→ 任一失败整体拒绝
- 覆盖前把目标现状打包备份（ReZeroTwin-Backup-*.zip），备份失败即中止
- curated 打包清单：memory.json / conversations.db* / life.db* / album/** / sprites/**
  （日志、vignette 缓存、incidents 明确排除）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from shared import life_ledger  # noqa: E402
from shared.conversation_store import ConversationStore  # noqa: E402
from shared.life_archive import (  # noqa: E402
    LifeArchiveError,
    export_life,
    import_life,
    validate_archive,
)
from shared.life_ledger import LifeLedger  # noqa: E402


def _seed_data(data_dir):
    """造一个有血有肉的数据目录：对话 + 账本 + memory + 相册 + 立绘 + 噪音。"""
    os.makedirs(data_dir, exist_ok=True)
    store = ConversationStore(os.path.join(data_dir, "conversations.db"))
    store.append("user", "你", "你好")
    store.append("rem", "蕾 姆", "蕾姆会陪着您。")
    store.append("user", "你", "我叫小东")
    ledger = LifeLedger(os.path.join(data_dir, "life.db"))
    ledger.append(ts="2026-01-01 08:00:00", kind="genesis", title="相识之日",
                  dedup_key="genesis")
    ledger.append(ts="2026-08-01 09:00:00", kind="loyalty_lock", title="忠诚锁定达成",
                  dedup_key="loyalty_lock")
    with open(os.path.join(data_dir, "memory.json"), "w", encoding="utf-8") as f:
        json.dump({"favor": 96, "user_name": "小东", "arc": "mansion_era"}, f)
    album = os.path.join(data_dir, "album")
    os.makedirs(album, exist_ok=True)
    with open(os.path.join(album, "2026-09-25_festival.md"), "w", encoding="utf-8") as f:
        f.write("# 纪念卡\n\n中秋快乐。")
    sprites = os.path.join(data_dir, "sprites")
    os.makedirs(sprites, exist_ok=True)
    with open(os.path.join(sprites, "rem.png"), "wb") as f:
        f.write(b"\x89PNG fake-bytes")
    # 噪音：必须被排除
    with open(os.path.join(data_dir, "gui.log"), "w", encoding="utf-8") as f:
        f.write("noise")


@pytest.fixture
def seeded_dir(tmp_path):
    d = tmp_path / "data"
    _seed_data(str(d))
    return str(d)


# ── 导出 ─────────────────────────────────────────────────────────

def test_export_creates_curated_zip(seeded_dir, tmp_path):
    out = str(tmp_path / "out")
    zip_path = export_life(dest_dir=out, data_dir=seeded_dir)
    assert os.path.isfile(zip_path) and zip_path.endswith(".zip")
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        assert names[0] == "manifest.json"
        assert "memory.json" in names and "conversations.db" in names
        assert "life.db" in names
        assert "album/2026-09-25_festival.md" in names
        assert "sprites/rem.png" in names
        assert not any(n.endswith(".log") for n in names), "日志必须排除"
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["schema"] == "rezero_life_v1"
        assert manifest["counts"]["messages"] == 3
        assert manifest["counts"]["life_events"] == 2
        assert len(manifest["files"]) == len(names) - 1


# ── 往返等价 ─────────────────────────────────────────────────────

def test_roundtrip_equivalence(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path / "out"), data_dir=seeded_dir)
    target = str(tmp_path / "restored")
    report = import_life(zip_path, data_dir=target)
    assert report["backup"] is None, "空目标无需备份"

    store = ConversationStore(os.path.join(target, "conversations.db"))
    assert store.count_user_messages() == 2, "对话轮数等价"
    ledger = LifeLedger(os.path.join(target, "life.db"))
    assert ledger.count() == 2, "人生事实等价"
    memory = json.load(open(os.path.join(target, "memory.json"), encoding="utf-8"))
    assert memory["user_name"] == "小东"
    assert os.path.isfile(os.path.join(target, "album", "2026-09-25_festival.md"))
    assert os.path.isfile(os.path.join(target, "sprites", "rem.png"))


# ── 损坏/恶意包拒绝（四连拒）────────────────────────────────────

def _rezip_without_manifest(src_zip, dst_zip):
    with zipfile.ZipFile(src_zip) as zin, \
            zipfile.ZipFile(dst_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            if n != "manifest.json":
                zout.writestr(n, zin.read(n))


def test_reject_missing_manifest(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    broken = str(tmp_path / "no_manifest.zip")
    _rezip_without_manifest(zip_path, broken)
    with pytest.raises(LifeArchiveError, match="manifest"):
        import_life(broken, data_dir=str(tmp_path / "t1"))


def test_reject_wrong_schema(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    forged = str(tmp_path / "wrong_schema.zip")
    with zipfile.ZipFile(zip_path) as zin, \
            zipfile.ZipFile(forged, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "manifest.json":
                m = json.loads(data)
                m["schema"] = "some_other_v9"
                data = json.dumps(m).encode("utf-8")
            zout.writestr(n, data)
    with pytest.raises(LifeArchiveError, match="schema"):
        import_life(forged, data_dir=str(tmp_path / "t2"))


def test_reject_path_traversal(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    evil = str(tmp_path / "evil.zip")
    with zipfile.ZipFile(zip_path) as zin, \
            zipfile.ZipFile(evil, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            zout.writestr(n, zin.read(n))
        zout.writestr("../evil.txt", "pwned")
    with pytest.raises(LifeArchiveError, match="不安全路径"):
        import_life(evil, data_dir=str(tmp_path / "t3"))


def test_reject_tampered_payload(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    forged = str(tmp_path / "tampered.zip")
    with zipfile.ZipFile(zip_path) as zin, \
            zipfile.ZipFile(forged, "w", zipfile.ZIP_DEFLATED) as zout:
        for n in zin.namelist():
            data = zin.read(n)
            if n == "memory.json":
                data = b'{"favor": 1}'  # 内容被改，sha256 不再匹配清单
            zout.writestr(n, data)
    with pytest.raises(LifeArchiveError, match="校验和"):
        import_life(forged, data_dir=str(tmp_path / "t4"))


# ── 备份与 dry-run ───────────────────────────────────────────────

def test_import_backups_existing_data(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    target = str(tmp_path / "t5")
    _seed_data(target)  # 目标已有旧数据（favor 应为旧值）
    old_memory = json.load(open(os.path.join(target, "memory.json"), encoding="utf-8"))
    report = import_life(zip_path, data_dir=target)
    assert report["backup"] and os.path.isfile(report["backup"])
    with zipfile.ZipFile(report["backup"]) as zf:
        assert "memory.json" in zf.namelist()
        restored_old = json.loads(zf.read("memory.json"))
    assert restored_old == old_memory, "备份必须能还原旧数据"


def test_dry_run_writes_nothing(seeded_dir, tmp_path):
    zip_path = export_life(dest_dir=str(tmp_path), data_dir=seeded_dir)
    target = str(tmp_path / "t6")
    os.makedirs(target)
    before = set(os.listdir(target))
    report = import_life(zip_path, data_dir=target, dry_run=True)
    assert report["dry_run"] is True and report["restored"]
    assert set(os.listdir(target)) == before, "dry-run 不得写任何文件"
    assert not any(f.startswith("ReZeroTwin-Backup") for f in
                   os.listdir(os.path.dirname(target) or ".")), "dry-run 不得产生备份"


def test_import_rejected_leaves_target_untouched(seeded_dir, tmp_path):
    """校验失败时目标目录零改动（绝不半导）。"""
    target = str(tmp_path / "t7")
    _seed_data(target)
    before = {p: os.path.getmtime(os.path.join(target, p))
              for p in os.listdir(target)}
    broken = str(tmp_path / "broken.zip")
    with zipfile.ZipFile(broken, "w") as zf:
        zf.writestr("memory.json", "{}")  # 无 manifest
    with pytest.raises(LifeArchiveError):
        import_life(broken, data_dir=target)
    after = {p: os.path.getmtime(os.path.join(target, p))
             for p in os.listdir(target)}
    assert before == after


# ── CLI 冒烟 ─────────────────────────────────────────────────────

def test_cli_export_and_import_roundtrip(seeded_dir, tmp_path):
    out = str(tmp_path / "cli_out")
    r1 = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(PROJECT_ROOT, "tools", "export_life.py"),
         "--out", out, "--data-dir", seeded_dir],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r1.returncode == 0, r1.stdout + r1.stderr
    zip_path = next(os.path.join(out, f) for f in os.listdir(out) if f.endswith(".zip"))

    target = str(tmp_path / "cli_target")
    r2 = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(PROJECT_ROOT, "tools", "import_life.py"),
         "--zip", zip_path, "--data-dir", target],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "重启" in r2.stdout

    r3 = subprocess.run(
        [sys.executable, "-X", "utf8", os.path.join(PROJECT_ROOT, "tools", "import_life.py"),
         "--zip", zip_path, "--data-dir", target, "--dry-run"],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r3.returncode == 0 and "预览" in r3.stdout
