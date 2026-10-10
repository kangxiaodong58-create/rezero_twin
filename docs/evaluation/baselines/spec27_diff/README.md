# SPEC-27 基线差异留证（R5 强调色柔化）

| 基线 | 差异 | 原因 |
|---|---|---|
| `locate_flash.png` | 1.27% | rem 蓝 `#56CCF2→#7FB3D5`（气泡/名字/描边同色令牌） |
| `bubble_ram.png` / `bubble_rem.png` / `bubble_search_hit.png` | 1.17–1.22% | 同上（ram 粉 `#FF7EB3→#E8A0BF`） |
| `bubble_multiline.png` | 0.95% | 同上 |
| `history_item_search_hit.png` | 0.60% | 同上 |
| `system_vignette.png` / `memory_book.png` | 0.00% | 不受影响 |

全部**在阈值（2%）内**且原因单一（R5 色值柔化），无布局/结构回归。替换走工具自身 capture。
