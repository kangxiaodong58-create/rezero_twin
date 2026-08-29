"""关系资产导入 CLI（V15.0 年轮 M4）。

用法（建议先关闭程序）：
    python tools/import_life.py --zip ReZeroTwin-Life-xxx.zip [--data-dir 数据目录] [--dry-run]

流程：全量校验 → 备份现状（ReZeroTwin-Backup-*.zip）→ 恢复 → 提示重启。
任何校验/备份失败即整体拒绝（退出码 1），绝不半导。
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.life_archive import import_life  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导入关系资产包（覆盖前自动备份）")
    parser.add_argument("--zip", required=True, help="关系资产包路径")
    parser.add_argument("--data-dir", help="数据目录（默认：get_data_dir() 解析）")
    parser.add_argument("--dry-run", action="store_true", help="只校验与预览，不写入")
    args = parser.parse_args()

    try:
        report = import_life(args.zip, data_dir=args.data_dir, dry_run=args.dry_run)
    except Exception as e:
        print(f"❌ 导入被拒绝: {e}")
        return 1

    mode = "预览（dry-run）" if report["dry_run"] else "导入"
    print(f"✅ {mode}完成，共 {len(report['restored'])} 个文件：")
    for rel in report["restored"]:
        print(f"   · {rel}")
    print(f"   清单计数: {report['counts']}")
    if report["backup"]:
        print(f"   旧数据已备份: {report['backup']}")
    if not report["dry_run"]:
        print("   请重启 ReZeroTwin 以加载恢复后的关系资产。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
