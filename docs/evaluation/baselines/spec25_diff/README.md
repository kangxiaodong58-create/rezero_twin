# SPEC-25 基线差异留证（locate_flash.png）

- 旧：`313x83`（头像 42px）
- 新：`335x100`（头像 64px + 脸部紧裁）
- 差异 100%：**尺寸不同**（行宽 +22 = 头像 +22；高度 +17 = 演示容器自适应宽度下气泡多折一行）。真机会话区 902px 宽，不存在这个折行。
- 预期内（SPEC §F25-4 已预判：唯一含 `ChatMessageWidget` 的基线）。其余 7 张 diff 0.00%。
- 文件：`locate_flash_new.png`、`locate_flash_side_by_side.png`
