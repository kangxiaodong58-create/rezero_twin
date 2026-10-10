# SPEC-26 基线差异留证（D1 深色玻璃面 + D5 文字对比）

| 基线 | 旧→新 差异 | 原因 |
|---|---|---|
| `locate_flash.png` | **83.63%** | D1：聊天面由近白 `rgba(255,250,255,0.86)` 改深色玻璃 `rgba(19,25,42,0.66)`（画布常量同步 `#DDDCE8 → #15182A`） |
| `system_vignette.png` | **5.23%** | D5：`text_muted #64748B → #8A9BBB`（系统卡文字提亮） |
| `history_item_search_hit.png` | **3.06%** | D5：同上（历史条目辅助文字） |
| `memory_book.png` | 0.72%（阈值内） | D5：同上（回忆之书辅助文字） |
| `bubble_rem/ram/multiline/search_hit` | 0.00% | 不受影响（纯气泡组件，无面板底色） |

全部为**预期内变化**（D1/D5 的直接后果），无意外回归。替换走工具自身 `capture()`（先 `resize(sizeHint)`，A20 教训）。
