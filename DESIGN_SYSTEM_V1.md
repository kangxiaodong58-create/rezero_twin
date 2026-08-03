# Re:Zero 双子系统 — Design System V1 草案

> 面向 PySide6 / QSS 桌面端角色扮演客户端。以 `gui.py` 代码为唯一事实来源。
> 本文档为规范草案，不包含代码改动方案；落地由开发 agent 按"第 6 章"约束执行。

---

## 1. 现状盘点

### 1.1 Token 现状

当前 token 集中在 `gui.py` 顶部三个常量字典（V10.9.0 基线）：

| Token 组 | 键数 | 评价 |
|----------|------|------|
| `COLORS` | 23 | 分类清晰（bg / border / text / 角色 / 用户 / 功能 / 系统），语义命名到位 |
| `RADIUS` | 4 | large=16 / medium=12 / small=8 / pill=20，覆盖主场景但留有缺口 |
| `SPACING` | 5 | xs=4 / sm=8 / md=12 / lg=16 / xl=24，刻度合理 |

**够用的部分**
- 暗色背景四级层级（base → surface → surface_2 → header）已建立，明度递进正确。
- 角色主题色三件套（accent / bubble / left）模式统一，rem 冰蓝、ram 蔷薇粉、user 靛蓝，辨识度高。
- 文本三级（primary / secondary / muted）与列表阅读层级约定一致。
- `border_subtle`(0.08) 与 `border_focus`(0.15) 的低对比细边策略符合"系统信息弱于对话"原则。

**不够用的部分（缺口）**
- **无 FONT token**：字体族 `"Microsoft YaHei"` 与 `"Segoe UI Emoji"` 散落 30+ 处；字号 8/9/10/11/12/14 全部以字面量传入 `QFont()`，无集中刻度。
- **无表面叠加 token**：`rgba(255,255,255,0.03/0.04/0.06)` 在 5+ 处重复书写（输入框底、hover 态、历史条目展开态、详情区），语义相同但数值零散。
- **无尺寸 token**：组件固定宽高（header 54、footer 28、input_frame 130、panel 180、avatar 42、card 720 等）全部硬编码，调整需全文搜索。
- **无层级 token**：overlay 遮罩 alpha `166`、樱花粒子层、浮层卡片的堆叠关系仅靠代码顺序隐含，无文档化约定。
- **无禁用态/高亮态 token**：`#4a4a4a` / `#888`（按钮 disabled）、`rgba(255,215,0,0.15)`（定位高亮）均为一次性硬编码，未进 `COLORS`。
- **RADIUS 缺口**：历史列表项用了 `6px`（外框）和 `4px`（详情内框），两者都不在 RADIUS 字典里，介于 small(8) 与无值之间。

### 1.2 组件现状

`gui.py` 共 8 个自定义 widget，成体系程度不一：

| 组件 | 行号 | 成熟度 | 说明 |
|------|------|--------|------|
| `BubbleWidget` | 248 | 中 | 角色色分发清晰；但 padding `12px 16px` 硬编码，未走 SPACING |
| `ChatMessageWidget` | 381 | 中 | 头像+名字+气泡组装完整；margins `12,5,12,5`、spacing `8` 硬编码 |
| `SystemLabelWidget` | 300 | 中高 | transient 自动消失 + 点击关闭做得好；字号 9/10 动态切换逻辑内联 |
| `CharacterPanel` | 462 | 中 | 立绘框 + 好感 + 阶段 + 情绪 + 锁定标记齐全；固定宽高全硬编码 |
| `HistoryItemWidget` | 674 | 高 | **最佳实践**：类级常量（`FONT_ROLE`/`FONT_TIME`/`FONT_CONTENT`/`MARGINS`/`SPACING`/`ROLE_COLORS`）集中管理，但该模式未推广到其他组件 |
| `HistoryOverlay` | 819 | 中高 | 非阻塞 overlay + 搜索 debounce + 空态/无结果态完整；遮罩 alpha 硬编码 |
| `AvatarLabel` | 217 | 低中 | SIZE=42 魔法数；emoji/图片双模式可用 |
| `SakuraOverlay` | 570 | 低 | 粒子颜色 5 色硬编码列表，30fps 定时器，无 token 接入 |

**体系性结论**：组件"能跑且风格统一"，但缺乏共享的常量基类或 mixin。`HistoryItemWidget` 的类级常量模式是正确方向，却孤立存在。角色色映射在 `HistoryItemWidget.ROLE_COLORS` 与 `BubbleWidget`/`ChatMessageWidget` 各自重复实现了一遍，存在三处定义。

### 1.3 硬编码与不一致清单

以下为代码中绕过 token 的具体位置（行号对应 `gui.py`）：

**颜色类**
- `#4a4a4a` / `#888` — 全局 QSS `QPushButton:disabled`（行 1403-1404），未进 COLORS
- `rgba(255,255,255,0.06)` — 顶栏搜索框(1192)、历史搜索框(905)、快捷按钮 hover(1311) 三处重复，无 token
- `rgba(255,255,255,0.03)` — 历史详情区底色(778)、历史项 hover(807) 两处
- `rgba(255,255,255,0.04)` — 历史项展开态(794)
- `rgba(255,215,0,0.15)` — 定位高亮 `_highlight_widget`(2058)，金色与 accent `#c9a96e` 不一致
- `QColor(0,0,0,166)` — overlay 遮罩(1041)，alpha 未 token 化
- 樱花 5 色 RGB 元组(574-580) — 与 ram 色系无关联，独立硬编码

**尺寸类（均无 DIMENSION token）**
- header `54`、footer `28`、input_frame `130`、input_box `55`、send_btn `72×55`
- panel `180`、avatar_frame `240`、avatar `42`、sprite `160×230`
- search_box `160×28`、history_card `720`、history_header `48`、quick_btn `26`
- bubble_max `600`、system_label_max `600`

**圆角类**
- `6px` — 历史项外框(797/804)
- `4px` — 历史详情内框(781)

**间距类（未走 SPACING）**
- BubbleWidget padding `12px 16px`(285)
- ChatMessageWidget margins `12,5,12,5`(398)、spacing `8`(399)
- CharacterPanel margins `10,16,10,16`(477)
- 多处 `setContentsMargins` 用裸数字

**字体类**
- `QFont("Microsoft YaHei", N)` 出现 20+ 次，N ∈ {8,9,10,11,12,14}
- `QFont("Segoe UI Emoji", N)` 出现 5 次，N ∈ {20,28,48}
- `QFont.Bold` 权重散落，V10.14 已对角色名去 Bold，但面板名(520)、标题(1179)、发送键(1333)仍 Bold

**结构性不一致**
- 角色色映射存在三份：`BubbleWidget`(if-elif 分发)、`ChatMessageWidget`(name_label 着色)、`HistoryItemWidget.ROLE_COLORS`(字典) — 数值相同但定义分散，改色需改三处。

---

## 2. 第一版 Design Tokens 建议

### 2.1 保留项（已验证可用，不动）

```
COLORS.bg_base        #121319       全局底色
COLORS.bg_surface     #1a1b23       面板/输入区表面
COLORS.bg_surface_2   #1e1f29       气泡/卡片表面
COLORS.bg_header      #0f1015       顶栏/底栏
COLORS.border_subtle  rgba(255,255,255,0.08)
COLORS.border_focus   rgba(255,255,255,0.15)
COLORS.text_primary   #E2E8F0
COLORS.text_secondary #94A3B8
COLORS.text_muted     #64748B
COLORS.rem_accent / rem_bubble / rem_left    蕾姆三件套
COLORS.ram_accent / ram_bubble / ram_left    拉姆三件套
COLORS.user_bubble / user_border             用户两件套
COLORS.accent / accent_hover / accent_press  金色功能色三态
COLORS.system_label_bg / system_label_fg     系统标签
RADIUS.large=16 / medium=12 / small=8 / pill=20
SPACING.xs=4 / sm=8 / md=12 / lg=16 / xl=24
```

以上为 V1 基线，禁止重命名或改值。

### 2.2 建议补强项

#### (A) FONT — 字体 token（最高优先）

```python
FONT_FAMILY = {
    "ui":    "Microsoft YaHei",   # 正文/UI
    "emoji": "Segoe UI Emoji",    # 表情/立绘占位
}

FONT_SIZE = {
    "caption":  8,   # 时间戳、最弱辅助
    "small":    9,   # 角色名、按钮文字、状态栏
    "body":    10,   # 历史正文、面板数值、系统标签(长)
    "body_lg": 11,   # 气泡正文、输入框
    "title":   12,   # 浮层标题
    "title_lg":14,   # 顶栏标题、面板角色名
    "display": 48,   # 立绘 emoji 占位
}
# emoji 专用尺寸（头像 20、情绪 28）并入 FONT_SIZE 或单列 FONT_SIZE_EMOJI
```

落地：所有 `QFont("Microsoft YaHei", N)` → `QFont(FONT_FAMILY["ui"], FONT_SIZE["..."])`。

#### (B) SURFACE_TINT — 表面叠加 token

将散落的 `rgba(255,255,255,0.0x)` 收敛为语义 token：

```python
SURFACE_TINT = {
    "input":   "rgba(255,255,255,0.06)",  # 输入框/搜索框底色
    "hover":   "rgba(255,255,255,0.06)",  # 按钮hover（与input同值，语义独立便于后续分化）
    "active":  "rgba(255,255,255,0.04)",  # 列表项展开态
    "detail":  "rgba(255,255,255,0.03)",  # 详情区/hover微底
}
```

> 注：hover 与 input 当前同值 0.06，但语义不同，分开命名以便后续独立调整。

#### (C) STATE — 状态色 token

```python
COLORS 补充：
"btn_disabled_bg":  "#3a3b44",   # 替换硬编码 #4a4a4a，向 bg_surface_2 靠拢
"btn_disabled_fg":  "#64748B",   # 复用 text_muted，替换 #888
"highlight_surface":"rgba(201,169,110,0.18)",  # 定位高亮，基于 accent #c9a96e 派生
"overlay_mask":     "rgba(0,0,0,0.65)",         # 替换 QColor(0,0,0,166)
```

#### (D) DIMENSION — 尺寸 token

```python
DIM = {
    # 结构高度
    "header_h":        54,
    "footer_h":        28,
    "input_frame_h":  130,
    "input_box_h":     55,
    "history_header_h":48,
    "avatar_frame_h": 240,
    # 宽度
    "panel_w":        180,
    "history_card_w": 720,
    "search_box_w":   160,
    "send_btn_w":      72,
    # 元素
    "avatar_size":     42,
    "bubble_max_w":    600,
    "sprite_w":        160,
    "sprite_h":        230,
    "icon_btn":        28,   # 搜索/关闭/历史等图标按钮
}
```

#### (E) RADIUS 补强

```python
RADIUS 补充：
"xs": 4,   # 详情区内框、极小元素
# 历史项外框 6px → 建议归并到 small(8) 或新增 "sm2"=6；V1 建议归并到 small 以减少刻度数
```

#### (F) LAYER — 层级约定（文档化，非 QSS 变量）

Qt 靠 widget 创建/堆叠顺序实现层级，无 CSS z-index。但需文档化约定：

```
LAYER 0  bg_base 背景
LAYER 1  面板/聊天内容/输入区（常规 widget）
LAYER 2  樱花粒子（WA_TransparentForMouseEvents，叠在聊天之上）
LAYER 3  历史浮层遮罩（全屏 paintEvent）
LAYER 4  历史浮层卡片（遮罩之上）
```

### 2.3 命名规范

| 规则 | 示例 |
|------|------|
| 颜色用 `<语义>_<层级/状态>` snake_case | `bg_surface_2`、`text_muted`、`btn_disabled_bg` |
| 角色色用 `<角色>_<用途>` | `rem_accent`、`rem_bubble`、`rem_left` |
| 圆角/间距用相对刻度名 | `large/medium/small/xs/pill`、`xs/sm/md/lg/xl` |
| 尺寸用 `<部位>_<维度>` | `header_h`、`panel_w`、`avatar_size` |
| 字号用语义刻度 | `caption/small/body/body_lg/title/title_lg/display` |
| 表面叠加用 `<状态>` | `SURFACE_TINT["hover"/"active"/"detail"/"input"]` |
| 禁止：red/blue 等颜色直命名 | ❌ `color_blue`；✅ `rem_accent` |
| 禁止：硬编码值出现在 QSS 字符串 | ❌ `padding: 12px`；✅ `padding: {SPACING['md']}px {SPACING['lg']}px` |

---

## 3. 组件规范草案

### 3.1 聊天气泡 BubbleWidget

- **用途**：承载单条对话文本，按角色区分视觉。
- **层级**：LAYER 1，主聊天区核心信息单元。
- **颜色规则**
  - rem：底 `rem_bubble`(0.10) + 左边线 3px `rem_left`(0.45)
  - ram：底 `ram_bubble`(0.10) + 左边线 3px `ram_left`(0.45)
  - user：底 `user_bubble`(0.16) + 全边 1px `user_border`(0.30)（无左边线，用全边区分）
  - 文本统一 `text_primary`
  - 兜底 system：`bg_surface_2` + `border_subtle` + `text_secondary`（实际 system 不走此组件）
- **间距/圆角**
  - 圆角 `RADIUS.large`(16)
  - 内 padding：`{SPACING.md}px {SPACING.lg}px`（12 16），替换硬编码
  - 外层 layout margins 0,0,0,0（已正确）
- **字号**：`FONT_FAMILY.ui` + `FONT_SIZE.body_lg`(11)
- **禁止事项**
  - 禁止给气泡加阴影/elevation（暗色主题靠左边线区分角色，不靠投影）
  - 禁止气泡宽度铺满，`bubble_max_w`(600) 限制 + stretch 占位
  - 禁止 system 角色走 BubbleWidget（走 SystemLabelWidget）
  - 禁止角色色逻辑分散；角色→颜色映射应集中到单一 `ROLE_COLORS` 字典（见 6.3）

### 3.2 历史浮层卡片 HistoryOverlay

- **用途**：非阻塞历史回忆浏览，主窗口级 overlay。
- **层级**：遮罩 LAYER 3，卡片 LAYER 4。附属层，不应抢主聊天风头。
- **颜色规则**
  - 卡片底 `bg_surface_2` + 边 `border_focus`(0.15)（比聊天区边框略亮，表明浮层）
  - 遮罩 `COLORS.overlay_mask`(0.65)
  - 标题 `text_primary`；关闭按钮默认 `text_muted`、hover `text_primary`
  - 搜索框底 `SURFACE_TINT.input` + `border_subtle`，focus `border_focus`
- **间距/圆角**
  - 卡片圆角 `RADIUS.large`(16)，宽 `DIM.history_card_w`(720)
  - 标题栏高 `DIM.history_header_h`(48)，底边 1px `border_subtle` 分隔
  - 搜索区高 48，margins `20,10,20,10`
  - 列表条目间距 2px（紧凑）
- **字号**：标题 `title`(12) Bold；搜索框 `body`(10)
- **行为**：`show()` 非 `exec()`；Esc / 点遮罩空白 / 关闭按钮 三路关闭；搜索 debounce 300ms
- **禁止事项**
  - 禁止用 `exec()` 阻塞（会冻住流式输出）
  - 禁止浮层卡片宽度超过 720（附属层不应比主区宽）
  - 禁止浮层内出现气泡组件（浮层只用 HistoryItemWidget 列表）
  - 禁止遮罩 alpha 高于 0.7（过黑会割裂主界面感知）

### 3.3 历史列表项 HistoryItemWidget

- **用途**：浮层内单条历史记录，折叠摘要 / 点击展开全文。
- **层级**：LAYER 4（浮层卡片内）。阅读层级：角色名 > 正文 > 时间。
- **颜色规则**
  - 角色名：`ROLE_COLORS` 映射（rem→rem_accent / ram→ram_accent / user→text_primary / system→text_muted）
  - 时间：`text_muted`
  - 摘要正文：system→`text_muted`，其余→`text_secondary`
  - 折叠态：transparent 底 + 左边线 2px 角色色 + hover `SURFACE_TINT.detail`(0.03)
  - 展开态：`SURFACE_TINT.active`(0.04) 底 + 左边线 2px 角色色
  - 详情区：`SURFACE_TINT.detail`(0.03) + 左边线 2px 角色色 + 圆角 `RADIUS.xs`(4)
- **间距/圆角**
  - 外框圆角 6px → V1 建议归并 `RADIUS.small`(8)
  - margins `(14, 8, 14, 8)`；内部 spacing 6
- **字号**：角色名 `small`(9) Bold；时间 `caption`(8)；正文 `body`(10)；详情 `small`(9)
- **禁止事项**
  - 禁止正文摘要超过 2 行（`PREVIEW_WORDS`=80 截断 + …）
  - 禁止时间戳显示年份（`created[5:16]` 只取 MM-DD HH:MM）
  - 禁止列表项高度固定（随内容自适应）
  - 禁止在列表项内嵌套气泡组件

### 3.4 系统标签 SystemLabelWidget

- **用途**：系统提示/引言，居中轻标签，无气泡，弱化显示。
- **层级**：LAYER 1，但视觉权重最低（系统信息弱于对话）。
- **颜色规则**
  - 底 `system_label_bg`(0.04) + 文 `system_label_fg`(#64748B=text_muted)
- **间距/圆角**
  - 单行：圆角 `RADIUS.pill`(20)，padding `6px {SPACING.lg}px`
  - 多行：圆角 `RADIUS.medium`(12)
  - 外层 margins `{SPACING.lg}, {SPACING.xs}, {SPACING.lg}, {SPACING.xs}`
  - 最大宽 600（`DIM.bubble_max_w` 复用）
- **字号**：短提示(≤40字/单行) `caption`(9)；长文本/多行 `body`(10)
- **transient 模式**：自动消失（默认 15s）+ 点击关闭 + 手型光标 + label 鼠标穿透
- **禁止事项**
  - 禁止系统标签用气泡背景（必须无气泡/弱底）
  - 禁止系统标签字号大于 `body`(10)
  - 禁止 transient 标签写入 DB（save=False）
  - 禁止系统标签文本可选（transient 模式下 label 穿透；非 transient 可选）

### 3.5 状态栏 StatusBar（footer）

- **用途**：底部信息条，RichText 主次分层。不是第二聊天区。
- **层级**：LAYER 1，结构最底层收束条。
- **颜色规则**（RichText span 分层）
  - 模式标记：`accent`（金色，最强）
  - 主信息（世界/好感）：`text_secondary`
  - 分隔符 `·`：`text_muted`
  - 次信息（拉姆阶段/事件）：`text_muted`
- **间距/圆角**
  - 高 `DIM.footer_h`(28)；margins `14,0,14,0`；底 `bg_header` + 顶 1px `border_subtle`
- **字号**：`small`(9)
- **禁止事项**
  - 禁止状态栏出现气泡/卡片
  - 禁止状态栏高度超过 28（信息条，非交互区）
  - 禁止状态栏文字超过一行（事件名截断 16 字 + …）
  - 禁止状态栏用 `text_primary`（会与聊天正文抢权重）

### 3.6 输入区 / 按钮

- **用途**：底部输入区（快捷命令行 + 多行输入 + 发送）。
- **层级**：LAYER 1，聊天区下方。
- **输入区**
  - 框高 `DIM.input_frame_h`(130)；底 `bg_surface` + 顶 1px `border_subtle`
  - 输入框 `QTextEdit`：`border_subtle` + `RADIUS.medium`(12) + focus `border_focus` + 底 `bg_surface` + 文 `text_primary`
  - 输入框高 `DIM.input_box_h`(55)；字号 `body_lg`(11)
- **快捷按钮**（/status /mansion 等）
  - 底 `bg_surface_2` + `border_subtle` + `RADIUS.small`(8) + 文 `text_secondary`
  - hover：底 `SURFACE_TINT.hover` + 文 `text_primary`
  - 高 26；字号 `small`(9)
- **发送按钮**
  - 主按钮：`accent` / hover `accent_hover` / press `accent_press` / disabled `btn_disabled_bg`+`btn_disabled_fg`
  - `RADIUS.small`(8)；尺寸 `DIM.send_btn_w`(72) × `DIM.input_box_h`(55)；字号 `body_lg`(11) Bold
- **图标按钮**（🔍 ✕ 📖 📍）
  - transparent 底 + 无边框 + 文 `text_secondary`/`text_muted`，hover 文 `accent`
- **禁止事项**
  - 禁止快捷按钮使用 `accent` 金色底（金色仅发送按钮 + 章节标签）
  - 禁止输入框高度随内容增长（固定 55，Shift+Enter 换行）
  - 禁止按钮圆角大于 `small`(8)
  - 禁止 disabled 态用 `#4a4a4a`/`#888` 硬编码（用 `btn_disabled_bg`/`btn_disabled_fg`）

---

## 4. 布局与信息层级规范

### 4.1 整体结构

```
┌─────────────────────────────────────────────┐
│ Header (54)  bg_header                       │ LAYER 1
├──────────┬──────────────────────┬───────────┤
│ Rem 面板  │   聊天滚动区          │ Ram 面板   │
│ (180)    │   + SakuraOverlay    │ (180)     │
│          │   (LAYER 2 粒子)      │           │
│          ├──────────────────────┤           │
│          │   输入区 (130)        │           │
├──────────┴──────────────────────┴───────────┤
│ Footer/StatusBar (28)  bg_header             │ LAYER 1
└─────────────────────────────────────────────┘
           最小 1000×650，默认 1100×750
```

- 三栏比例：面板固定 180 + 中间 stretch + 面板固定 180，body spacing 0。
- 全局 margins 0,0,0,0；间距靠组件内部 padding 控制。

### 4.2 主聊天区

- **信息层级**：对话气泡（primary）> 系统标签（muted，无气泡）。
- 消息间距 `SPACING.md`(12)（V10.14 已设定）；上下留白 `SPACING.sm`(8)。
- 气泡最大宽 600，超出靠 stretch 占位；user 右对齐 + 头像在右，角色左对齐 + 头像在左。
- 樱花粒子层叠在聊天之上，`WA_TransparentForMouseEvents` 不拦截交互。
- 最多保留 80 条 widget（`MAX_VISIBLE_WIDGETS`），超出移除最早。

### 4.3 左右角色面板

- **信息层级**：立绘（视觉锚点）> 角色名（accent 着色）> 好感/阶段（secondary）> 情绪 emoji > 锁定标记（accent）。
- 固定宽 180；立绘框高 240，圆角 `large`，底 `bg_surface_2`。
- 角色名 `title_lg`(14) Bold + 角色色；数值 `body`(10) + `text_secondary`。
- 边界：`border-left`(对外侧) 1px `border_subtle`，收束视觉。
- 面板是状态展示区，不含交互输入。

### 4.4 历史浮层

- **信息层级**：浮层是附属层，整体视觉权重低于主聊天。
- 遮罩全屏 `overlay_mask`(0.65)；卡片居中 720 宽，不铺满。
- 卡片内层级：标题栏 > 搜索框 > 列表（滚动）。
- 列表项内部层级：角色名（着色 Bold）> 正文摘要 > 时间（muted 右对齐）> 📍定位（muted，hover accent）。
- 浮层打开时不阻塞主聊天流式输出。

### 4.5 状态栏

- **信息层级**：模式（金色 accent）> 世界/好感（secondary）> 拉姆阶段/事件（muted）。
- 三段用 `·` 分隔符（muted）串联，单行。
- 固定高 28，不滚动，不交互。

---

## 5. 下一阶段建议

### P0 — 必须先规范的

1. **建立 FONT token 并全量替换**：字号/字体族散落 30+ 处，是当前最大一致性风险。先建 `FONT_FAMILY` + `FONT_SIZE`，再批量替换 `QFont()` 调用。
2. **收敛 SURFACE_TINT**：`rgba(255,255,255,0.03/0.04/0.06)` 五处重复，统一为 4 个语义 token，消除"同义不同值"。
3. **统一角色色映射**：将 `BubbleWidget` / `ChatMessageWidget` / `HistoryItemWidget` 三处角色色逻辑合并为单一 `ROLE_COLORS` 字典 + 统一取色函数。
4. **补齐 STATE token**：disabled 态 `#4a4a4a`/`#888`、高亮 `rgba(255,215,0,0.15)`、遮罩 `166` 三处硬编码进 token。
5. **RADIUS 补 `xs`=4**：消除历史详情区 4px 硬编码；历史项外框 6px 归并到 `small`(8)。

### P1 — 可增强体验的

1. **建立 DIMENSION token**：将 12+ 个固定宽高收口，便于后续统一调整密度（如紧凑模式）。
2. **推广 HistoryItemWidget 常量模式**：为 BubbleWidget / ChatMessageWidget / CharacterPanel 提取类级常量，降低样式与逻辑耦合。
3. **立绘占位态规范化**：当前"立绘区域\n拖入 PNG 图片"占位样式内联，应作为 CharacterPanel 的标准空态，纳入 token。
4. **樱花粒子色系与角色色关联**：当前 5 色独立硬编码，可派生自 `ram_accent` 色相，强化"拉姆/樱花"语义关联（但保持低 alpha 适配暗色）。
5. **输入区快捷按钮分组规范**：当前 5 个命令按钮平铺，可约定分组（状态类 / 篇章切换类 / 模式类）的视觉区分规则。

### P2 — 以后再做的

1. **明色主题 token 镜像**：当前纯暗色，未来若需明色，建 `COLORS_LIGHT` 镜像字典，保持 key 不变只换值。
2. **动画/过渡 token**：QSS 过渡支持有限，但可约定"出现/消失时长"（如 transient 15s、高亮 2s）为 token，统一节奏感。
3. **头像系统**：当前 emoji + PNG 双模式，未来可做圆形裁剪/边框状态色（如锁定态金色环）。
4. **无障碍/对比度审计**：系统化校验 text_muted(#64748B) on bg_surface(#1a1b23) 等组合的 WCAG 对比度。
5. **组件预览/文档站**：将本规范转为可交互的组件目录（非 WebView，可用 Qt 独立窗口生成预览）。

---

## 6. 给开发 agent 的落地约束

### 6.1 可以改什么

- 新增 token 字典（`FONT_FAMILY` / `FONT_SIZE` / `SURFACE_TINT` / `DIM` 等）到 `gui.py` 顶部 token 区。
- 将硬编码值替换为 token 引用（`12` → `SPACING['md']`、`QFont("Microsoft YaHei", 11)` → `QFont(FONT_FAMILY['ui'], FONT_SIZE['body_lg'])`）。
- 合并三处角色色定义为单一 `ROLE_COLORS` + 取色函数。
- 在组件内提取类级常量（参照 `HistoryItemWidget` 模式）。
- 调整 QSS 字符串以引用新 token。

### 6.2 不能改什么

- **不改 token 数值**：`COLORS` / `RADIUS` / `SPACING` 现有键的值禁止改动（V10.9-V10.14 已验证的视觉基线）。
- **不改业务逻辑**：状态机、Prompt、Validator、ConversationStore、LLM Bridge、世界状态——一律不碰。
- **不改组件行为契约**：`SystemLabelWidget` 的 transient 机制、`HistoryOverlay` 的非阻塞 `show()`、`ChatMessageWidget.message_id` 定位透传——行为保持不变。
- **不引入新框架**：禁止 React / GSAP / WebView / QML 作为主 UI；样式只走 QSS + `setStyleSheet`。
- **不做无边框窗口 / 头像系统 / 表情系统 / 背景主题大改**（本阶段明确不做）。
- **不改 `MAX_VISIBLE_WIDGETS`(80)、debounce(300ms)、transient(15s)、高亮(2s)** 等已验证参数（如需调整需单独评审）。
- **不改文件结构**：`gui.py` 仍是单文件主 UI（拆分文件不在本阶段范围）。

### 6.3 新增样式必须如何接入 token

1. **颜色**：任何新颜色必须先在 `COLORS` 注册 key，再在 QSS 中以 `COLORS['key']` 引用。禁止 QSS 字符串内出现裸 `#hex` 或 `rgba()`。
2. **字号/字体**：必须用 `FONT_FAMILY` + `FONT_SIZE`，禁止 `QFont("Microsoft YaHei", N)` 字面量。
3. **圆角/间距**：必须用 `RADIUS` / `SPACING`；若现有刻度不够，先在字典补 key（如 `RADIUS['xs']=4`），再引用。
4. **尺寸**：固定宽高必须进 `DIM` 字典；禁止 `setFixedHeight(130)` 裸数字。
5. **表面叠加**：hover/active/detail 底色必须用 `SURFACE_TINT`，禁止重复写 `rgba(255,255,255,0.0x)`。
6. **角色色**：新组件涉及角色着色，必须引用统一 `ROLE_COLORS` 字典，禁止重新 if-elif 分发。
7. **新增 token 的注释**：每个新 key 必须带 `# 用途` 注释，与现有 token 风格一致。
8. **自查**：改动后全文搜索 `#[0-9a-fA-F]{3,6}`、`rgba(255,255,255`、`QFont("` 三个模式，确认无新增裸值（仅 token 字典定义处允许）。

---

> 本草案基于 `gui.py`（V10.14 视觉基线）代码盘点。所有 token 值、组件尺寸、硬编码行号均以代码为准。
> 下一步：开发 agent 按 P0 顺序落地，每完成一项回填 token 注册并自查裸值。
