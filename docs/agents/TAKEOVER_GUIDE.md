# 外部 Agent 接手指南：视觉评估与高清资产替换

> **对象**：短暂接手本项目的另一个 Agent（用虚拟桌面 + 视觉模型做前端观感深度评估、用生图模型替换 UI 图 / 立绘 / 头像）。
> **性质**：**强制规范**。本项目行《断流协议》受控协作——你不是自由代码生成器，是**受控编码协作代理**。
> **一句话**：先出 SPEC 等批准，再动手；只改批准过的文件；改完过四道门禁；观感类必须真机确认才合入。

---

## 0. 现状快照（接手点位）

| 项 | 值 |
|---|---|
| 分支 | 仅 `master`（干净）；工作区无未提交改动 |
| master HEAD | `c4d0786`（SPEC-33 已合入）+ `fe6468c`（台账回填） |
| 版本 | `CHANGELOG.md` 顶部 = **V16.6.7** |
| 门禁基线 | **386 passed** · 冒烟 **31/31** · 截图基线 **8 张 0.00%** · QSS golden **88 条** |
| 运行环境 | Windows 11 · `venv/Scripts/python.exe`（Python 3.10.11 · PySide6 6.11.1） |
| 真实显示 | **1707×1067 @150%**（逻辑宽约 1133）⇒ 右栏在逻辑宽 <1220 时自动折叠为 44px 竖条 |
| 已知开放小项 | **垂直自适应**：窗口过矮（≲900 逻辑高）时输入区/底坞会被挤出可视区 ⇒ 做视觉评估请用 **≥900 逻辑高**的窗口 |
| 远端 | GitHub `kangxiaodong58-create/rezero_twin`（本地领先，按"批量搬运"策略推送） |

---

## 1. 三条硬红线（最高优先级，违反即回滚重来）

1. **禁止直接修改 `main` / `master` / `develop`** —— 一切改动走 feature 分支；
2. **未收到「批准 SPEC-<ID>」之前**，禁止写代码、改文件、运行会改变文件的命令 —— 先出 SPEC 等批；
3. **只能修改 SPEC 中列出的文件** —— 需要改范围外文件，**立即停止**并输出「范围外变更请求（RCR）」。

> 用户已授权（2026-09-22）：**SPEC 一经批准即可实现到合并**，不必逐步再问。唯一必须停下的是上面第 3 条与"SPEC 与现状冲突"。

---

## 2. 分支纪律（"分支是草稿纸，不是收藏品"）

- 一个 SPEC 一个分支，命名 `feat|fix|refactor|audit|docs/SPEC-<ID>-简述`；
- 同时活跃分支 **≤2**（最好 1）；分支寿命 1 天内最好、3 天可接受、超过 1 周拆掉或放弃；
- 合并方式：`git merge --squash` + 单条提交（master 历史 = **一条 Spec 一条提交**）；
- 合并后**立刻删本地分支**，推送后同步删远端分支；
- **绝不 force push 到 master/develop**。

---

## 3. 改动分级与批准口令

| 级别 | 范围 | 口令 |
|---|---|---|
| L0 | 文案、样式、配置、注释 | 批准 L0 SPEC-<ID> |
| L1 | 局部 Bug 修复（不改接口） | 批准 L1 SPEC-<ID> |
| L2 | 新功能 / 跨模块 / 接口变化 | 批准 SPEC-<ID> |
| L3 | 架构、数据库、权限、支付、安全、依赖大版本 | 完整 SPEC + 回滚方案 + 手动确认 |

SPEC 模板与台账：`docs/specs/INDEX.md`；SPEC 全文放 `docs/specs/SPEC-<ID>-<简述>.md`（一个 Spec 一个文件）。
**免二次批准范围**：`docs/specs/**`、`CHANGELOG.md`、`docs/devlog/**`（常规产物）；其余文件一律要列进 SPEC。

---

## 4. 四条验证命令（前缀 `env -u PYTHONPATH` **不可省** —— 宿主 PYTHONPATH 会污染项目 venv）

| 用途 | 命令 | 当前基线 |
|---|---|---|
| 全量测试 | `env -u PYTHONPATH venv/Scripts/python.exe -m pytest tests/ -q` | **386 passed** |
| 冒烟回归 | `env -u PYTHONPATH venv/Scripts/python.exe tests/smoke_test.py` | **31/31** |
| 打包 EXE | `env -u PYTHONPATH powershell.exe -NoProfile -ExecutionPolicy Bypass -File build.ps1` | `dist/ReZeroTwin.exe`（57.3 MB） |
| 数据隔离校验 | `bash scripts/verify_isolation.sh <被测命令>` | **必须为空**（差集非空即失败） |

本仓**无** lint/typecheck 配置（报告里写「未运行及原因」）；CI 门禁在 `.github/workflows/ci.yml`。

---

## 5. 视觉/观感的验收闸门（**对你最关键的一条**）

1. **观感类改动（视觉、动效、间距、数值刷新时机）必须先打包 EXE、由用户真机确认，才能 merge 进 master。测试全绿 ≠ 可以合并。**
2. **截图基线三步法**（禁止直接覆盖）：
   1）采集到临时目录；2）逐像素 diff + 差异图**留证**到 `docs/evaluation/baselines/specNN_diff/`；3）用户确认后才替换基线。
   工具：`venv/Scripts/python.exe tools/screenshot_baseline.py`（默认采集）／`--compare`（对比）。
   ⚠️ 基线替换**必须走工具自身的 `capture()`**（它会先 `resize(sizeHint)`）——手动 `widget.grab()` 尺寸路径不同，历史上踩过（A20）。
3. **QSS golden**：`venv/Scripts/python.exe tests/test_theme_equivalence.py --check` 先看差异清单 → `--capture` 重采。
   ⚠️ golden 与截图基线都是**生成物**：**只能在最终合并态重采**，跨分支各自重采会在合并时打架。
4. **离屏抓图 ≠ 视觉真相**：
   - 离屏 `grab()` **不含父背景合成**（半透明气泡抓出来是"浅字叠白底"，会误判成"看不见"）；
   - `QT_QPA_PLATFORM=offscreen` 下**无 CJK 字形回退**（中文渲染成方框）——需要看字时显式 `QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")`；
   - 判视觉一律用**真机**；抓真机窗口用 `PrintWindow(hwnd, hdc, 2)`（PW_RENDERFULLCONTENT），避开遮挡。
5. 做可复现截图时设 `REZERO_DISABLE_VIGNETTE=1`（关暗角随机性）。

---

## 6. 数据安全（违反即事故）

- **绝不删除/覆盖** `.env`、`data/`、`dist/data/`；`data/` 整体未被 git 跟踪（`git ls-files data/` 为空）。
- 跑任何会写盘的脚本**必须隔离**：把 `REZERO_LIFE_DB` / `REZERO_GUI_LOG` 指向临时目录，并同步重定向 `shared.config.get_data_dir`（或直接用 `scripts/verify_isolation.sh` 包住）；**跑完用 `find data -type f` 验证零变化**。
- `build.ps1` 已内置备份/恢复/自检（SPEC-30）：失败时**备份目录会故意保留**（供手动恢复），**不要手删**。
- 任何凭据（API key/token/连接串）一律以 `[REDACTED]` 记录，不保留明文。

---

## 7. 资产替换专项（你的主要改动面）

### 7.1 资产清单与契约（改前必读）

| 文件 | 现状规格 | 消费方 | 约束 |
|---|---|---|---|
| `assets/rem_face.png` / `ram_face.png` | 256×256 | `AvatarLabel`（聊天气泡头像，直径 `DIM['avatar_size']` = 64） | **文件名被用例硬断言**（`test_avatar_size_and_face_crop_v1659`）——换名/换格式必须同批改用例 |
| `assets/user_avatar.svg` | 矢量 | 同上 | `AvatarLabel` 取图优先链：`<角色>_face.png` → `avatar.png` → `avatar.svg` |
| `assets/rem_sprite.jpg` / `ram_sprite.jpg` | 600×900 / 720×1280 | 右栏立绘卡（`ui/assets.py::sprite_card_pixmap`，`KeepAspectRatioByExpanding`） | **头部锚定取景**——换图后先确认发顶/头顶位置 |
| `assets/` 其它 UI 图 | — | 各处 | 顶栏与左导航里的 app 图标**已按用户要求删除**，不要加回来 |
| 背景图（backdrop） | — | `theme.app_shell(_backdrop_image_url())` + `data/backdrop_cache.png` | 改它影响**全局观感**，属观感类 ⇒ 必须真机；注意缓存文件在 `data/` 内，勿手改 |

### 7.2 高清替换的硬教训（实测，不是理论）

1. **裁切**：SPEC-25 实测 320²/416² 紧裁会切掉发顶或下巴 ⇒ 采用 **462² 温和裁切**（保留发顶+下巴）。换高分辨率图时**先出裁切预览**再定基准；
2. **尺寸 token 双点断言**：`DIM['avatar_size']` 与 `AvatarLabel.SIZE` 有用例互锁 ⇒ 改一处必改另一处；
3. **人设一致性**：角色形象须与原作/既有立绘同一人设（用户口径：**授权同人**，可创作）；蕾姆=蓝系、拉姆=粉系（`COLORS['rem_*']`/`['ram_*']`），角色色是**身份标识**，替换资产时不要打乱；
4. **格式**：优先 PNG（带透明）；JPG 仅用于不透明立绘；**换格式 = 接口面变化**，必须同步 tests（属于 L2）；
5. **体积**：单张建议 ≤ 1 MB（EXE 体积与首屏加载都受影响）；上限提升需在 SPEC 里写理由。

### 7.3 改资产的完整流程（照做）

1. **出 SPEC**：列出要换的资产、新规格（尺寸/格式/裁切方式/体积）、消费方清单、验收方式（旧 vs 新对照图 + 真机截图）、回滚方式；
2. **实现**（只动 SPEC 列出的文件）；
3. **跑四条命令** + 资产用例（`tests/test_dashboard_assets.py`、`tests/test_ui_offscreen.py` 的资产断言）；
4. **出对照图**（旧/新并排，100% 原尺寸）+ **真机截图**（PrintWindow）交给用户；
5. 用户真机 OK → `git merge --squash` 合入 + 删分支 + 回填 `docs/specs/INDEX.md`；
6. **收工四件套**（缺一不可）：`CHANGELOG.md` 条目 + `docs/devlog/<版本主题>_<日期>.md` 施工记录 + 打包 EXE + 冒烟回归。

---

## 8. 硬技术坑清单（本仓踩过，不遵守必翻车）

1. **行尾混排**：仓库混排 CRLF/LF（`gui.py`、`tests/` 多为 CRLF；`ui/history.py` 为 LF）。改文件要"按字节读 + 按原口径写回"，别让编辑器归一化（否则整文件 diff 假警报）。历史上 `gui.py` 还有 `\r\r\n` 残留会让 AST 行号错位。
2. **`build.ps1` 只许 ASCII 注入**：PowerShell 5.1 按 ANSI 读 BOM-less 文件，中文注释会吞掉后续字节（脚本直接语法错）。改完必须跑 `Parser::ParseFile` 语法门禁；文件非 ASCII 字节数应保持不变。
3. **给容器设样式表必须带 `#objectName` 作用域**：无选择器的"裸声明"会被 Qt 级联到**每一个子控件**——这正是历史上"顶栏长框里套一堆小框"的根因。守卫 `test_container_qss_is_scoped` 已钉死（白名单写在测试文件内）。
4. **QSS 继承是静默的**：控件自己没写的属性可能来自**祖先的类型选择器**（发送按钮变金黄就是这么来的）。修复用 **id 作用域**（`#send_btn`）并同时覆盖 `:hover/:pressed/:disabled`。
5. **"状态变色"有两条路径**：CSS `:focus` 伪状态 **和** 事件过滤器里的 `setStyleSheet`（`shell_setup.eventFilter` 曾这么做）。排障**两条都要查**。
6. **加描边先想布局**：`sizeHint` 会变 ⇒ 要么与既有描边**同宽替换**（SPEC-33 的零抖动做法），要么先跑尺寸探针再动手。
7. **视觉数值要入断言**：对比度（≥4.5:1）、定位底色 α 上限（≤0.20）等都已有用例锁死。你新增视觉参数时，请一并给出"上限/下限"断言，防回弹。
8. **Qt QSS 不支持 CSS 过渡/动画**：动效走 `QPropertyAnimation`，时长/曲线受 `design_tokens.MOTION` 黄金带约束（有用例）。
9. **快照类产物**（golden/基线）**必须在最终态重采**，并留证差异目录。
10. **视觉真相只在真机**：离屏图只作回归参考（见 §5.4）。

---

## 9. 必须"停下报告"的情形

- 需要改 SPEC 未列出的文件 → 出 RCR（模板见 `docs/specs/INDEX.md`）；
- SPEC 与现状冲突，需要改设计 → 停；
- 涉及 `data/` / `.env` / 权限 / 支付 / 架构 / 依赖大版本 → 停（L3）；
- 观感判据分歧（你认为更好、用户真机不认）→ **以用户真机为准**；
- 出现"数据被动过"的任何迹象 → 立即停 + 报告 + 用 `scripts/verify_isolation.sh` 取证。

---

## 10. 你可以直接抄的工作模板（视觉类 SPEC 骨架）

```
SPEC-ID：SPEC-<日期>-<序号>
级别：L2（资产替换）／L1（样式修复）／L0（仅观感参数）
目标：<一句话>
非目标：<明确不动什么>
需要读取/修改的文件：@assets/... @ui/... @tests/...
新增文件：<无 / 资产清单>
接口/数据是否变化：<是/否，换格式=是>
测试方式：四条命令 + 资产用例 + 基线三步法 + **真机确认（强制）**
回滚方式：<分支丢弃 / 单提交 revert / 资产回滚到上一版>
风险：<R1/R2 与缓解>
等待批准：是
```

---

## 11. 给你的一句总结

**本项目的"好看"由三样东西共同定义，缺一不可**：
① **机器判据**（测试/golden/基线/对比度断言）证明显式规则没被破坏；
② **真机确认** 判断观感是否真的更好；
③ **用户口径**（"不是不要 X，而是不要 X 太强"这类）决定档位。
你负责带入更强的视觉评估与更高清的资产，但**闸门顺序不能变**：出 SPEC → 批准 → 分支实现 → 四门禁 → 对照图 + 真机 → 合入 → 四件套。

---

## 12. 本机磁盘清理红线（用户 2026-10-14 明确要求，**最高优先级**）

> 用户原话：**「注意一些重要的、敏感的、历史会话记录、核心安全、游戏存档等的不要删除」**

### 12.1 永不删除（列清单比"凭常识判断"可靠）

| 类别 | 具体位置（本机） |
|---|---|
| **AI 会话/记忆/技能** | `C:\Users\11985\AppData\Local\hermes\` 下的 `sessions/`（历史会话）· `memories/` · `skills/` · `plugins/` · `cron/` · `attachments/` · `audio_cache/` · `.hermes_history` · `auth.json` · `.env` |
| **游戏存档** | `C:\Users\11985\Saved Games\` · `Documents\My Games\` · `AppData\Local\<游戏名>\` · `AppData\Roaming\<游戏名>\` · Steam `userdata\` · 各类模拟器存档目录 |
| **浏览器数据** | `AppData\Local\Google\Chrome\User Data\` · `Microsoft\Edge\User Data\` · 书签/密码/历史/登录态一律不碰 |
| **通讯软件数据** | `Documents\WeChat Files\` · `Documents\Tencent Files\` · QQ/微信/钉钉等的 `AppData` 数据目录 |
| **用户文件** | `Documents\` · `Desktop\` · `Downloads\` · `Pictures\` · `Videos\` 内的任何文件 |
| **本项目数据** | `.env`（真实 API key）· `data/` · `dist/data/`（会话/记忆/账本 DB）· `assets/` |
| **系统目录** | `C:\Windows\` · `Program Files` · `ProgramData`（**只报告，不清理**） |
| **回收站** | 清空回收站属"不可逆"操作 → **先问用户** |

### 12.2 允许清理（白名单，皆为"可再生成"的纯缓存）

- 包管理器缓存：`%LOCALAPPDATA%\npm-cache` · `%LOCALAPPDATA%\pip` · `%LOCALAPPDATA%\uv`（下次安装自动重建）；
- `%TEMP%`（`C:\Users\11985\AppData\Local\Temp`）中**修改时间 >7 天**的条目（锁定中/在用的自动跳过）；
- Hermes 自身缓存 `%LOCALAPPDATA%\hermes\cache`（该目录设计上 24 小时自动清理，属可弃）；
- 编译/构建产物（如项目 `build/`、旧 `dist/` 副本——但**先确认不是唯一存档**）。

### 12.3 执行纪律

1. **白名单之外一律先报告、等确认**，不得"顺手删"；
2. 每次清理前先**列清单 + 体量**，清完**再报实际释放量**；
3. 涉及任何"存档/会话/凭据"相邻目录时，**先只读核查、后动手**；
4. 清理不影响功能的验证方式：跑四条门禁命令（§4）+ 抽查受保护目录仍在（`sessions/`、`Saved Games/` 等）。
