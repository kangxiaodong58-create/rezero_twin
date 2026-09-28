"""命令路由 / 导航按钮（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

import traceback

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QPushButton

from design_tokens import FONT_FAMILY, FONT_SIZE
from shared.state import FAVOR_LEVEL_CN, StoryArc
from ui import theme
from ui.app_data import ARC_CN, ONI_STAGE_CN
from ui.assets import _theme_icon
from ui.logging_util import _log


class CommandsMixin:
    """命令路由 / 导航按钮。"""

    # ── 导航（SPEC-20260922-17 / B5：单一真源 NAV_ENTRIES 驱动左导航 + 底部图标坞）──

    def _nav_button(self, entry: dict, *, active: bool = False, variant: str = "side") -> QPushButton:
        """由 NAV_ENTRIES 表项生成导航按钮（side = 左导航 / dock = 底部图标坞）。

        回调在**构建期**解析（`getattr(self, handler)`）——表里写错方法名会在启动时立刻炸，
        而不是等用户点了才发现（结构断言另有 AST 侧校验）。
        """
        btn = QPushButton(entry["label"])
        btn.setIcon(_theme_icon(entry["icon"]))
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(getattr(self, entry["handler"]))
        if variant == "dock":
            btn.setIconSize(QSize(24, 24))
            btn.setStyleSheet(theme.nav_btn_dock())
            return btn
        btn.setIconSize(QSize(21, 21))
        btn.setFixedHeight(43)
        btn.setFont(QFont(FONT_FAMILY['ui'], FONT_SIZE['body'], QFont.Bold if active else QFont.Normal))
        if active:
            btn.setStyleSheet(theme.nav_btn_dock_active())
        else:
            btn.setStyleSheet(theme.nav_btn_side())
        return btn

    def _nav_focus_input(self) -> None:
        """导航「对话」：聚焦输入框（原左导航/底坞两处 lambda 的唯一化落点）。"""
        self.input_box.setFocus()

    def _nav_open_status(self) -> None:
        """导航「状态」：走唯一命令路由（原「日程/任务/插件」三条同动作入口的合并落点）。"""
        self._handle_command("/status")

    # ── 命令处理 ────────────────────────────

    def _handle_command(self, cmd: str) -> None:
        """唯一命令路由（V16.2.1 合并）。

        支持：/status · /mansion · /empire · /late · /recover [0~1] · /称呼|/name <名字>（SPEC-20260922-24）

        ⚠ SPEC-20260922-17（步 5 / R4）：原 `/toggle` `/llm` `/local` 分支已随「设置」入口一并删除
        ——`mode` 特性 V16.4.0 已彻底移除，保留分支只会打印一条无意义提示（空转死链）。
        现敲这些指令会得到「未知指令」（诚实行为，CHANGELOG 已明示）。

        ⚠ 历史坑（V16.0-mf 引入 → V16.2.1 修复）：本类此前在文件后部**再定义了一份**
        同名 `_handle_command`（V16-M_D 导航栏精简版）。类体后定义覆盖前定义 →
        `/mansion /empire /late` 全部落进「未知指令」，且 V10.9.2 的状态面板变成死代码。
        结构回归守卫：`tests/test_command_router.py`（重复方法名 AST 扫描 + 命令覆盖断言）。
        """
        raw = (cmd or "").strip()
        low = raw.lower()
        try:
            if low == "/status":
                # V10.9.2：多行可读排版 + 瞬时消失 + 不存 DB
                state = self.engine.snapshot()
                arc_cn = ARC_CN.get(state.arc.value, state.arc.value)
                favor_cn = FAVOR_LEVEL_CN.get(state.favor_level.name, state.favor_level.name)
                oni_cn = ONI_STAGE_CN.get(state.oni_stage.name, state.oni_stage.name)
                status_text = (
                    f"📊 状态\n"
                    f"篇章：{arc_cn}\n"
                    f"蕾姆：{favor_cn}（{state.favor}）· 独立 {state.independence:.2f}\n"
                    f"拉姆：{state.ram_stage.value}（{state.ram_favor}）\n"
                    f"鬼化：{oni_cn} · 残香 {state.witch_scent}\n"
                    f"⌁ 点击关闭"
                )
                self._append_parsed_message("系统", status_text, "system", save=False, transient=True)
                self._update_panels()
            elif low == "/mansion":
                self._apply_arc(StoryArc.MANSION_ERA, "Arc I · 罗兹瓦尔宅邸", "→ 已切换至宅邸篇")
            elif low == "/empire":
                self._apply_arc(StoryArc.EMPIRE_ERA, "Arc II · 帝国篇", "→ 已切换至帝国篇（失忆）")
            elif low == "/late":
                self._apply_arc(StoryArc.LATE_ARC, "Arc III · 后期篇章", "→ 已切换至后期篇章")
            elif low.startswith("/recover"):
                parts = raw.split()
                try:
                    p = float(parts[1])
                except (IndexError, ValueError):
                    p = 1.0
                self.bot.recover(p)
                self._save_state()      # V16.2：改走唯一保存入口（engine + 平铺键一并落盘）
                self._append_parsed_message("系统", f"→ 记忆恢复进度设为 {p}", "system")
                self._update_panels()
            elif raw.startswith("/称呼") or raw.startswith("/name"):
                # SPEC-20260922-24：称呼纠正入口（空格可省；/name 为英文别名）
                _pref = "/称呼" if raw.startswith("/称呼") else "/name"
                arg = raw[len(_pref):].strip()
                if not arg:
                    self._append_parsed_message(
                        "系统", "用法：/称呼 小东（我怎么称呼你；/name 同）",
                        "system", save=False, transient=True)
                elif self.engine.set_user_name(arg):
                    self._save_state()              # 唯一保存入口
                    self._append_parsed_message(
                        "系统", f"好，以后就叫我「{arg}」。", "system", save=False, transient=True)
                    self._update_status_bar()       # 氛围行立即刷新
                else:
                    self._append_parsed_message(
                        "系统", "这个称呼我不敢用（1–8 字，别以「为/与/在」开头，别带「的/哦/呢」）。",
                        "system", save=False, transient=True)
            else:
                self._append_parsed_message(
                    "系统", f"未知指令: {raw}", "system", save=False)
        except Exception as e:
            _log(f"_handle_command 异常: {e}\n{traceback.format_exc()}", durable=True)

    def _apply_arc(self, arc, label: str, message: str) -> None:
        """切换篇章的唯一路径：改状态 → 落盘 → 提示 → 更新标签/状态栏/面板。"""
        self.bot.set_arc(arc)
        self._save_state()              # V16.2：改走唯一保存入口
        self._append_parsed_message("系统", message, "system")
        self._arc_label.setText(label)
        self._update_status_bar()
        self._update_panels()
