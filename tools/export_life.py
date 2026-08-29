"""关系资产导出 CLI（V15.0 年轮 M4）。

用法（项目根 / EXE 同级运行，建议先关闭程序）：
    python tools/export_life.py [--out 输出目录] [--data-dir 数据目录]

成功打印包路径与清单计数，退出码 0；失败打印原因，退出码 1。
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from shared.life_archive import export_life  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="导出关系资产包（ReZeroTwin-Life-*.zip）")
    parser.add_argument("--out", help="输出目录（默认：数据目录同级）")
    parser.add_argument("--data-dir", help="数据目录（默认：get_data_dir() 解析）")
    args = parser.parse_args()

    try:
        path = export_life(dest_dir=args.out, data_dir=args.data_dir)
    except Exception as e:
        print(f"导出失败: {e}")
        return 1
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"✅ 关系资产已导出: {path}（{size_mb:.2f} MB）")
    print("   这是「这段关系真的发生过」的全部证据——请妥善保管。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
