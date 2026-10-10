"""面板 / 氛围 / 呼吸动效（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

import os
import sys
import traceback

from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QObject, QPropertyAnimation, QSequentialAnimationGroup, QThread, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from design_tokens import COLORS, RAM_EMOTION_BY_STAGE, RAM_EMOTION_DEFAULT, RAM_EMOTION_ONI, RAM_EMOTION_WITCH
from shared.state import FAVOR_LEVEL_CN, OniStage, WorldState, is_valid_user_name
from typing import Optional
from ui.flags import _ui_motion_enabled, name_hint_once
from ui.logging_util import _log
from ui.text import format_world_line


class PanelsMixin:
    """面板 / 氛围 / 呼吸动效。"""

    # ── 状态同步 ────────────────────────────

    def _update_panels(self) -> None:
        """更新左右角色面板（V11.0：表情扩档 + 状态分层）。"""
        try:
            state = self.engine.snapshot()
        except Exception:
            return

        # ── 蕾姆表情（11 档优先级，命中即停）──
        # 鬼化/残香仅通过表情传达，面板不显示术语
        if state.witch_scent >= 3:
            rem_emotion = "😰"       # P1 魔女侵蚀
        elif state.oni_stage == OniStage.BRINK:
            rem_emotion = "😡"       # P2 失控边缘
        elif state.oni_stage == OniStage.FULL:
            rem_emotion = "😠"       # P3 完全解放
        elif state.oni_stage == OniStage.EMERGING:
            rem_emotion = "😤"       # P4 鬼化显现
        elif state.recovery < 0.3:
            rem_emotion = "😵"       # P5 记忆严重模糊
        elif state.consecutive_negative >= 3:
            rem_emotion = "😟"       # P6 连连受挫
        elif state.locked:
            rem_emotion = "🥰"       # P7 忠诚锁定
        elif state.independence >= 0.6:
            rem_emotion = "😌"       # P8 独立人格
        elif state.favor >= 80:
            rem_emotion = "😍"       # P9 深爱满溢
        elif state.favor < 15:
            rem_emotion = "😐"       # P10 尚且陌生
        else:
            rem_emotion = "😊"       # P11 平静温和

        if self.rem_panel is not None:
            self.rem_panel.update_state(
                favor=state.favor,
                stage=FAVOR_LEVEL_CN.get(state.favor_level.name, state.favor_level.name),
                emotion=rem_emotion,
                locked=state.locked,
                independence=state.independence,
                recovery=state.recovery,
            )

        # ── 拉姆表情（8 档：姐姐危险感知 + 自身阶段）──
        # D3（B2）：档位→表情查表已出库 design_tokens（唯一真源，改表情只改那里）
        if state.witch_scent >= 3:
            ram_emotion = RAM_EMOTION_WITCH    # P1 姐姐的怒意
        elif state.oni_stage >= OniStage.FULL:
            ram_emotion = RAM_EMOTION_ONI      # P2 姐姐的警惕
        else:
            ram_emotion = RAM_EMOTION_BY_STAGE.get(
                state.ram_stage.value, RAM_EMOTION_DEFAULT)

        if self.ram_panel is not None:
            self.ram_panel.update_state(
                favor=state.ram_favor,
                stage=state.ram_stage.value,
                emotion=ram_emotion,
            )

        # V16-M_F：Character Dashboard 数据注入（Persistent State 映射）
        try:
            dashboard = getattr(self, "dashboard", None)
            if dashboard is not None:
                actions = getattr(self.world, "character_actions", {}) or {}
                rem_lock = bool(state.locked)
                dashboard.set_data(
                    rem={"mood": rem_emotion, "doing": actions.get("rem", "—"),
                         "stage": FAVOR_LEVEL_CN.get(state.favor_level.name,
                                                     state.favor_level.name),
                         "favor": state.favor, "locked_icon": rem_lock},   # SPEC-27 R3
                    ram={"mood": ram_emotion, "doing": actions.get("ram", "—"),
                         "stage": state.ram_stage.value,
                         "favor": state.ram_favor, "locked_icon": False},  # SPEC-27 R3
                )
        except Exception as e:
            _log(f"Dashboard 更新异常: {e}", durable=True)

    def _refresh_ambient(self) -> None:
        """V16-M_F：世界状态 → 顶部/左导航的映射（DESIGN 解析 §1.4/§1.3）。"""
        try:
            state = self.engine.snapshot()
            ev = self.world.active_event or ""
            # SPEC-20260922-24：max_event 14→16（与状态栏统一）+ 子句感知截断
            head_full = format_world_line(self.world.period, self.world.weather, ev,
                                          max_event=16, prefix="🌙 ")
            head_bare = format_world_line(self.world.period, self.world.weather, "",
                                          prefix="🌙 ")
            suffix = ""
            if is_valid_user_name(state.user_name):
                suffix = f"  ·  与{state.user_name}同行"
            elif state.user_name:
                # 脏称呼降级：**不回显脏值**（「与为客人大人哦同行」语病），每进程只提示一次纠正入口
                suffix = "  ·  与你同行"
                if name_hint_once():
                    self._append_parsed_message(
                        "系统", "称呼还没定下来——输入 /称呼 小东（或 /name 小东）告诉我你的名字",
                        "system", save=False, transient=True)
            # 真机反馈修订：顶栏宽度自适应——整行放不下时**事件先让位、只留称呼**
            ambient = head_full + suffix
            if suffix and not self._ambient_fits(ambient):
                ambient = head_bare + suffix
            self._ambient_label.setText(ambient)
            self._nav_weather.setText(f"{self.world.period}\n{self.world.weather}")
            try:
                from shared import life_ledger
                n = life_ledger.get_default_ledger().count()
                self._nav_sysstatus.setText(f"LLM · 人生账本 {n} 条")
            except Exception:
                self._nav_sysstatus.setText("LLM · 记忆同步正常")
        except Exception as e:
            _log(f"ambient 刷新异常: {e}", durable=True)

    def _update_status_bar(self) -> None:
        try:
            self._refresh_ambient()
            state = self.engine.snapshot()
            w = self.world if hasattr(self, 'world') else WorldState.now()
            # 活跃事件可见化：有事件且与 period/weather 相容才追加（V11.9.2）
            ram_part = state.ram_stage.value
            ev = w.active_event or ""
            # A15（B2）：同一实现，head=False 只取事件后缀（16 字 / 双空格分隔为本站现值）
            ram_part += format_world_line(w.period, w.weather, ev,
                                          max_event=16, head=False, suffix_sep="  ·  ")
            # V10.14：RichText 主次分层（金色模式 / 次亮主信息 / 弱化次信息）
            # V14.4（Phase C）：本地模式已移除，状态栏恒定 LLM
            mode_text = "LLM"
            mode_color = COLORS["accent"]
            sep = f'<span style="color:{COLORS["text_muted"]};">  ·  </span>'
            self._mode_label.setText(
                f'<span style="color:{mode_color};">{mode_text}</span>'
                f'{sep}'
                f'<span style="color:{COLORS["text_secondary"]};">{w.period} · {w.weather}  ·  好感 {state.favor}/100</span>'
                f'{sep}'
                f'<span style="color:{COLORS["text_muted"]};">{ram_part}</span>'
            )
        except Exception:
            pass

    # ── V12.0 视觉动效（头像说话态 / 气泡入场 / 状态栏呼吸）────────────

    def _setup_breathing(self) -> None:
        """V12.0：状态栏呼吸 — _mode_label opacity 0.85↔1.0，单程 2s，无限往复。

        _ui_motion_enabled()=False 时不创建任何动画对象（完全静态）。
        """
        if not _ui_motion_enabled():
            return
        try:
            self._breath_effect = QGraphicsOpacityEffect(self._mode_label)
            self._mode_label.setGraphicsEffect(self._breath_effect)
            self._breath_effect.setOpacity(1.0)
            fwd = QPropertyAnimation(self._breath_effect, b"opacity", self._mode_label)
            fwd.setDuration(2000)
            fwd.setStartValue(1.0)
            fwd.setEndValue(0.85)
            fwd.setEasingCurve(QEasingCurve.InOutSine)
            bwd = QPropertyAnimation(self._breath_effect, b"opacity", self._mode_label)
            bwd.setDuration(2000)
            bwd.setStartValue(0.85)
            bwd.setEndValue(1.0)
            bwd.setEasingCurve(QEasingCurve.InOutSine)
            self._breath_group = QSequentialAnimationGroup(self)
            self._breath_group.addAnimation(fwd)
            self._breath_group.addAnimation(bwd)
            self._breath_group.setLoopCount(-1)
            self._breath_group.start()
            _log("状态栏呼吸已启动")
        except Exception as e:
            _log(f"呼吸动画创建异常: {e}", durable=True)
            self._breath_group = None

    def _set_breathing(self, active: bool) -> None:
        """V12.0：呼吸暂停/恢复。思考中 pause（opacity 停在当前值），完成后 resume。"""
        if not _ui_motion_enabled():
            return
        group = getattr(self, "_breath_group", None)
        if group is None:
            return
        try:
            st = group.state()
            if active:
                if st == QAbstractAnimation.Stopped:
                    group.start()
                elif st == QAbstractAnimation.Paused:
                    group.resume()
            else:
                if st == QAbstractAnimation.Running:
                    group.pause()
        except Exception as e:
            _log(f"呼吸暂停/恢复异常: {e}", durable=True)

    def _set_speaking_panels(self, speaker: Optional[str]) -> None:
        """V12.0：点亮/复位侧栏说话描边。speaker=None 全部复位。

        状态跟踪（_current_speaker）不受开关影响；仅 QSS 刷新受动效门控制。
        """
        self._current_speaker = speaker
        if not _ui_motion_enabled():
            return
        try:
            if self.rem_panel is not None:
                self.rem_panel.set_speaking(speaker == "rem")
            if self.ram_panel is not None:
                self.ram_panel.set_speaking(speaker == "ram")
            dashboard = getattr(self, "dashboard", None)
            if dashboard is not None:
                dashboard.set_speaking(speaker)
        except Exception as e:
            _log(f"_set_speaking_panels 异常: {e}", durable=True)

    def _play_entrance_animation(self, widget: QWidget, delay_ms: int = 0) -> None:
        """正式消息泡轻入场（V16-M_B：收敛到 motion.fade_in——MOTION token
        220ms/OutCubic；delay_ms 供历史回放级联）。禁用态 = 立即呈现最终状态，
        零定时器零 effect 残留；effect 卸载由 motion 负责（防离屏渲染残留）。
        """
        try:
            import motion
            motion.fade_in(widget, delay_ms=delay_ms)
        except Exception as e:
            _log(f"入场动画异常: {e}", durable=True)

    # ── 开场引言 ────────────────────────────

    def _generate_vignette(self) -> None:
        """生成开场氛围段。

        v10.4 起走 shared.vignette 的 L0-L3 多级生成：
        L0 缓存 → L1 LLM(重试+校验) → L2 动态模板 → L3 静态兜底。
        引言为 View-Only 数据，绝不写入对话历史（save=False + 不进 messages）。
        V10.10.3：全路径 try-except + 探针日志。
        V10.10.4：frozen EXE 走安全路径（主线程 L2/L3 模板，不创建 QThread 不调 LLM）。
        V11.12：占位消息持有引用删除（替代脆弱的 count-2 位置删除）；
                引言卡使用 vignette 幕间卡变体（强于灰条、弱于角色泡）。
        """
        _log("引言生成触发")
        try:
            if not hasattr(self.bot, 'world'):
                self._append_parsed_message(
                    "系统", "欢迎回到罗兹瓦尔宅邸。输入消息开始对话。", "system", save=False
                )
                return

            placeholder = self._append_parsed_message("系统", "✨ 正在感知宅邸的氛围…", "system", save=False)

            def _on_done(clean: str):
                _log(f"引言回调 _on_done: {clean[:30]}...")
                try:
                    # V11.12：按引用移除占位消息（count-2 位置删除已废弃，
                    # 期间若有其他 widget 插入不会再误删）
                    if placeholder is not None:
                        try:
                            self.chat_layout.removeWidget(placeholder)
                            placeholder.setParent(None)
                            placeholder.deleteLater()
                        except RuntimeError:
                            pass  # 已被销毁（如 MAX_VISIBLE_WIDGETS 淘汰）
                    self._append_parsed_message(
                        "系统", f"━━  ✦  ━━\n{clean}\n━━  ✦  ━━",
                        "system", save=False, force_center=True, variant="vignette")
                    # v10.8.1：将引言氛围注入 Bridge，供首轮对话感知（View-Only，不进 history）
                    if hasattr(self.bot, 'set_opening_atmosphere'):
                        self.bot.set_opening_atmosphere(clean)
                    _log("引言回调完成")
                except Exception as e:
                    _log(f"引言回调异常: {e}\n{traceback.format_exc()}", durable=True)

            # ── V10.10.4 + V14.4: 安全引言路径 ──
            # frozen EXE 下 QThread + LLM 调用触发原生崩溃（0xC0000409）；
            # V14.4（Trial #1 B-01）：离屏环境（QT_QPA_PLATFORM=offscreen）或无
            # API key 同样存在崩溃风险（offscreen 下 QThread+LLM 崩溃），
            # 统一走主线程 L2/L3 模板生成，不创建线程不调 LLM。
            is_offscreen = os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"
            no_api_key = not os.getenv("DEEPSEEK_API_KEY")
            if getattr(sys, "frozen", False) or is_offscreen or no_api_key:
                _log("安全引言路径 (frozen/offscreen/无key)")
                from shared.vignette import VignetteGenerator
                engine = self.bot.engine
                gen = VignetteGenerator(llm_callable=None)  # None → 跳过 L1，直接 L2/L3
                text = gen.generate(
                    self.world,
                    rem_favor_level=engine._get_favor_level().name,
                    independence=engine.independence,
                    ram_stage=engine._get_ram_stage().value,
                    locked=engine.locked,
                    recovery=engine.recovery,
                    oni_warning=(engine.oni_stage != OniStage.NONE),
                    witch_scent=engine.witch_scent,
                    arc=engine.arc.value,  # V14.4：缓存 key 按篇章分桶
                )
                _log(f"模板引言生成完成: {text[:30]}...")
                _on_done(text)
                _log("模板引言已展示")
                return

            # ── 非 frozen：保留现有 LLM Worker 路径 ──
            # 用 raw_completion 绕过角色 system prompt
            class VignetteWorker(QObject):
                finished = Signal(str)
                error = Signal(str)
                def __init__(self, bot, world):
                    super().__init__()
                    self.bot = bot; self.world = world
                def run(self):
                    _log("引言 Worker.run() 开始")
                    try:
                        from shared.vignette import VignetteGenerator
                        engine = self.bot.engine
                        gen = VignetteGenerator(llm_callable=self.bot.raw_completion)
                        text = gen.generate(
                            self.world,
                            rem_favor_level=engine._get_favor_level().name,
                            independence=engine.independence,
                            ram_stage=engine._get_ram_stage().value,
                            locked=engine.locked,
                            recovery=engine.recovery,
                            oni_warning=(engine.oni_stage != OniStage.NONE),
                            witch_scent=engine.witch_scent,
                        )
                        _log(f"引言生成完成: {text[:30]}...")
                        self.finished.emit(text)
                    except Exception as e:
                        _log(f"引言 Worker 异常: {e}\n{traceback.format_exc()}", durable=True)
                        self.error.emit(str(e))

            _log("引言 Worker 创建")
            worker = VignetteWorker(self.bot, self.world)
            worker.finished.connect(_on_done)
            worker.error.connect(
                lambda e: _on_done(f"宅邸的轮廓在{self.world.period}的{self.world.weather}中若隐若现。")
            )
            thread = QThread()
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.finished.connect(thread.quit)
            worker.error.connect(thread.quit)
            thread.finished.connect(thread.deleteLater)
            thread.start()
            _log("引言子线程已启动")
        except Exception as e:
            _log(f"引言生成启动失败: {e}\n{traceback.format_exc()}", durable=True)
            # 降级为静态欢迎语
            try:
                self._append_parsed_message(
                    "系统", "欢迎来到罗兹瓦尔宅邸。", "system", save=False)
            except Exception:
                pass
