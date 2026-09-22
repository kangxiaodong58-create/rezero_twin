#!/usr/bin/env bash
# SPEC-20260922-04（M7）：测试隔离校验 —— CI 与本地共用
#
# 用法：
#   bash scripts/verify_isolation.sh <被测命令...>
#   例（Windows/git-bash）：bash scripts/verify_isolation.sh env -u PYTHONPATH venv/Scripts/python.exe -m pytest tests/ -q
#   例（CI/Linux）        ：bash scripts/verify_isolation.sh python -m pytest tests/ -q
#
# 判据（本仓既定口径）：「不改变文件的命令」= 跑完后 data/ 目录逐字节不变（mtime + size）。
# 非空差异 → 说明测试/构造过程写入了真实用户数据，退出码 1。

set -u

snapshot() {
    # data/ 不存在（如干净 CI 环境）时输出为空——若被测命令把它建起来，diff 会立刻暴露
    if [ -d data ]; then
        find data -type f -exec stat -c '%n %Y %s' {} + 2>/dev/null | sort
    fi
}

BEFORE="$(snapshot)"

echo "▶ 执行：$*"
"$@"
CODE=$?

AFTER="$(snapshot)"

if [ "$BEFORE" != "$AFTER" ]; then
    echo "❌ 数据隔离校验失败：被测命令写入了真实 data/"
    echo "--- before ---"
    printf '%s\n' "$BEFORE"
    echo "--- after ---"
    printf '%s\n' "$AFTER"
    exit 1
fi
echo "✅ 数据隔离校验通过：data/ 逐字节未变（mtime+size）"

if [ "$CODE" -ne 0 ]; then
    echo "❌ 被测命令退出码：$CODE"
    exit "$CODE"
fi
exit 0
