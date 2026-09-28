"""每日（存档 / 摘要 / 问候 / 来信 / 立绘拖入）（SPEC-20260922-22 S2：自 gui.py 逐字搬出）。"""

from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import date, datetime

from shared.config import get_data_dir
from typing import Optional
from ui.app_data import GREETING_TEMPLATES, WEATHER_CLAUSES
from ui.assets import _copy_user_sprite
from ui.flags import _get_ambient_registry
from ui.logging_util import _log
from ui.text import event_compatible


class DailyMixin:
    """每日（存档 / 摘要 / 问候 / 来信 / 立绘拖入）。"""

    def _save_state(self) -> None:
        try:
            engine = self.engine
            data = self.store.load()
            data.update({
                # A3 收口（B2）：`mode` 不再落盘（本地模式已下线，字段无消费者）
                # V16.1（M2）：单源序列化（新键，含 locked/oni/turn_count 等全字段）
                "engine": engine.to_dict(),
                # 旧平铺键：双写一版（life_archive / 外部读取与回滚兼容，下版本删）
                "arc": engine.arc.value,
                "favor": engine.favor,
                "ram_favor": engine.ram_favor,
                "independence": engine.independence,
                "recovery": engine.recovery,
                "locked": engine.locked,
                "user_name": engine.user_name,
                "events": list(getattr(engine, 'events', [])),
                "world_state": self.world.save_dict() if hasattr(self, 'world') else {},
            })
            self.store.save(data)
            _log("状态保存成功", durable=True)
        except Exception as e:
            _log(f"保存状态失败: {e}", durable=True)

    # ── V11.6.5: session 摘要（规则生成，不调 LLM）──

    def _generate_session_summary(self) -> Optional[dict]:
        """规则生成 session 摘要（不调 LLM）。

        算法（收紧版）：
        - 优先：自上次 session_summaries.msg_end_id 之后的新消息
        - 若无上次摘要：最近 ≤50 条
        - 统计 user 消息数 = 轮次
        - last_user_excerpt ≤50 字
        """
        try:
            last_summary = self.conv_store.get_last_session_summary()
            after_id = last_summary["msg_end_id"] if last_summary else None

            messages = self.conv_store.get_messages_since(after_id, limit=50)
            if not messages:
                return None

            user_msgs = [m for m in messages if m["role"] == "user"]
            turn_count = len(user_msgs)
            if turn_count == 0:
                return None  # 无用户消息，不算有效 session

            # 最后一条用户消息截断 ≤50 字
            last_user_msg = user_msgs[-1]["content"]
            last_user_excerpt = last_user_msg[:50]
            if len(last_user_msg) > 50:
                last_user_excerpt += "…"

            # 规则摘要文本
            first_user = user_msgs[0]["content"][:20]
            if turn_count <= 2:
                summary_text = f"简短交流了{turn_count}轮"
            elif turn_count <= 5:
                summary_text = f"聊了{turn_count}轮，从「{first_user}」开始"
            else:
                summary_text = f"深入聊了{turn_count}轮，从「{first_user}」开始"

            return {
                "turn_count": turn_count,
                "summary_text": summary_text,
                "last_user_excerpt": last_user_excerpt,
                "msg_start_id": messages[0]["id"],
                "msg_end_id": messages[-1]["id"],
            }
        except Exception as e:
            _log(f"生成 session 摘要失败: {e}", durable=True)
            return None

    def _save_session_summary(self) -> None:
        """关闭时写入 session 摘要（closeEvent 末尾调用，失败不影响主流程）。"""
        try:
            summary = self._generate_session_summary()
            if not summary:
                _log("session 摘要：无有效内容，跳过")
                return
            self.conv_store.save_session_summary(
                started_at=self._session_start_time,
                ended_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                turn_count=summary["turn_count"],
                summary_text=summary["summary_text"],
                last_user_excerpt=summary["last_user_excerpt"],
                msg_start_id=summary["msg_start_id"],
                msg_end_id=summary["msg_end_id"],
            )
            _log(f"session 摘要已保存: turns={summary['turn_count']}")
        except Exception as e:
            _log(f"session 摘要保存失败: {e}", durable=True)

    def _show_daily_greeting(self, today_str: str) -> None:
        """V11.9.1：自然日首次问候 — 表驱动模板，View-Only。

        按当前 period 选骨架模板，天气走 WEATHER_CLAUSES 白名单注入。
        active_event 与天气冲突则跳过 event 并打日志。
        不依赖 mode（local/llm 均展示），不调用 LLM，不进 ConversationStore。
        展示后立即写入 last_greeting_date 并持久化。
        """
        try:
            period = self.world.period
            weather = self.world.weather
            event = self.world.active_event or ""

            # 天气从句：白名单查找，未知天气中性兜底
            weather_clause = WEATHER_CLAUSES.get(weather, "")

            # 事件从句：冲突检测（V11.9.2 统一入口）
            event_clause = ""
            if event:
                if event_compatible(period, weather, event):
                    event_clause = event + "。"
                else:
                    _log(f"日更问候: event与period/weather冲突, skip event. "
                         f"period={period} weather={weather} event={event}")

            template = GREETING_TEMPLATES.get(period, GREETING_TEMPLATES["上午"])
            text = template.format(weather_clause=weather_clause, event_clause=event_clause)
            # V11.12：日更问候与开场引言共用 vignette 幕间卡变体（同为宅邸幕间语义）
            self._append_parsed_message(
                "系统", f"━  ✦  ━\n{text}\n━  ✦  ━",
                "system", save=False, force_center=True, variant="vignette"
            )
            self.world.last_greeting_date = today_str
            # 立即持久化，防止崩溃丢失问候标记
            # V16.2：改走唯一保存入口——此前只 set("world_state") 导致存档里
            # 出现「world 是最新、engine/平铺键是上一轮」的部分保存
            self._save_state()
            _log(f"日更问候已展示: period={period} weather={weather} date={today_str}")
        except Exception as e:
            _log(f"日更问候展示失败: {e}\n{traceback.format_exc()}", durable=True)

    def _show_ambient_line(self) -> None:
        """V11.9.0：同日轻氛围一行 — period · weather · active_event，View-Only。

        V11.9.2：active_event 与 period/weather 语义冲突时省略 event 段并打日志。
        仅在同日有历史重开时展示（空库完整引言时不重复打）。
        save=False，不进 ConversationStore。
        V14.11 Step5：放行时在状态行下附「偶发一句」（registry slot=
        ambient_remark，事件触发 + 冷却 2h + 日 3 条上限，同一事件最多 1 句；
        纯展示不进好感/事件记忆通道）。
        """
        try:
            parts = [self.world.period, self.world.weather]
            event = self.world.active_event or ""
            if event:
                if event_compatible(self.world.period, self.world.weather, event):
                    parts.append(event)
                else:
                    _log(f"轻氛围: event与period/weather冲突, skip event. "
                         f"period={self.world.period} weather={self.world.weather} event={event}")
            text = " · ".join(parts)
            remark = self._pick_ambient_remark()
            extra = f"\n💬 {remark}" if remark else ""
            self._append_parsed_message("系统", f"🌧️ {text}{extra}", "system", save=False)
            _log(f"轻氛围已展示: {text} | 偶发一句: {'有' if remark else '无'}")
        except Exception as e:
            _log(f"轻氛围展示失败: {e}", durable=True)

    def _pick_ambient_remark(self) -> str:
        """V14.11 Step5：选取「偶发一句」。放行判定（WorldState）→ 注册表
        确定性选型（seed=日|事件id）→ 记录冷却。任何失败静默返回空串。"""
        try:
            if not self.world.ambient_remark_allowed():
                return ""
            from shared.template_registry import load_registry, pick as registry_pick
            registry = _get_ambient_registry()
            if not registry:
                return ""
            arc_value = getattr(getattr(self.bot, "engine", None), "arc", None)
            arc = getattr(arc_value, "value", "mansion_era")
            today = datetime.now().strftime("%Y-%m-%d")
            item = registry_pick(
                registry, arc=arc, slot="ambient_remark",
                period=self.world.period, weather=self.world.weather,
                seed=f"{today}|{self.world.active_event_id}")
            if not item:
                return ""
            self.world.record_ambient_remark()
            return item.get("text", "")
        except Exception as e:
            _log(f"偶发一句选取失败: {e}", durable=True)
            return ""

    def _show_resume_card(self) -> None:
        """启动时展示上次 session 摘要（续聊卡）。

        挂载于 _load_history() 之后、引言 QTimer 之前。
        - 无摘要 / 无对话记录 → 不显示
        - save=False，不写 DB
        - 有摘要时已压制欢迎语（_load_history 中处理），避免双卡叠放
        """
        try:
            summary = self.conv_store.get_last_session_summary()
            if not summary:
                return
            if self.conv_store.count() == 0:
                return  # 无对话记录不显示（fresh install 场景）

            ended = summary.get("ended_at", "")
            turns = summary.get("turn_count", 0)
            text_body = summary.get("summary_text", "")
            excerpt = summary.get("last_user_excerpt", "")

            # 格式化时间（只取 日期+时分）
            time_str = ended[:16] if len(ended) >= 16 else ended

            card_text = f"📋 上次对话 · {time_str}\n{text_body}（共{turns}轮）\n"
            if excerpt:
                card_text += f"最后你说：「{excerpt}」\n"
            card_text += "继续输入即可接着聊，或点击右上角宅邸日志查看完整回忆。"

            self._append_parsed_message("系统", card_text, "system", save=False)
            _log(f"续聊卡已展示: turns={turns} time={time_str}")
        except Exception as e:
            _log(f"续聊卡展示失败: {e}", durable=True)

    # ── V15.0-M2：纪念卡 ─────────────────────

    def _maybe_show_memorial_card(self) -> None:
        """纪念日/节日/相识周年 → 生成并展示一张纪念卡（相册落盘，每类每日一张）。

        生成链 L1（LLM，非 frozen/offscreen/有 key 时）→ L2 注册表确定性。
        事实计算与落账复用 _today_facts 同口径（ensure_genesis 幂等）。
        """
        from shared import memorial as memorial_mod
        from shared.anniversary import compute_facts
        from shared.life_ledger import ensure_genesis, record_day_facts
        genesis = ensure_genesis(self.conv_store)
        if genesis is None:
            return
        today = date.today()
        facts = compute_facts(genesis=genesis, today=today)
        if not facts:
            return
        record_day_facts(facts, today)
        kind = next((f.kind for f in facts if f.kind in memorial_mod.CARD_KINDS), None)
        if kind is None or memorial_mod.has_card(kind, today):
            return
        arc_value = getattr(getattr(self.bot, "engine", None), "arc", None)
        arc = getattr(arc_value, "value", "mansion_era")
        safe_path = (getattr(sys, "frozen", False)
                     or os.environ.get("QT_QPA_PLATFORM", "") == "offscreen"
                     or not os.getenv("DEEPSEEK_API_KEY"))
        llm_callable = None
        if not safe_path and hasattr(self.bot, "raw_completion"):
            llm_callable = lambda p: self.bot.raw_completion(  # noqa: E731
                "你是《Re:Zero》双子（蕾姆第三人称自称、拉姆毒舌而温柔）。"
                "写一张纪念卡的正文，30-60 字，只输出正文。",
                p)
        text = memorial_mod.generate(kind, facts=facts, arc=arc, today=today,
                                     llm_callable=llm_callable)
        if not text:
            return
        snapshot = {"arc": arc, "favor": getattr(self.engine, "favor", None),
                    "facts": [f.title for f in facts]}
        path = memorial_mod.save_card(kind, today, text, detail=snapshot)
        self._append_parsed_message(
            "系统", f"━━  ✦ 纪念日  ━━\n{text}\n━━  ✦  ━━",
            "system", save=False, force_center=True, variant="vignette")
        _log(f"纪念卡已生成: kind={kind} path={path}")

    # ── V14.3：主动来信 ────────────────────────

    def _maybe_dispatch_letter(self, today_str: str) -> Optional[dict]:
        """主动来信判定与渲染（启动序列调用；分离以便离屏测试）。

        last_period 回填（方案 C：字段优先，旧存档从 DB 推导）→ 冷却/桶/发件人
        判定 → 触发则落库（role=rem/ram 与正常回复一致）+ 渲染双泡。
        返回 letter 结果（None=未触发，回落既有问候逻辑）。
        """
        self.world.ensure_last_period(self.conv_store)
        letter = self.letter_manager.evaluate_and_dispatch(
            state=self.world,
            favor=self.engine.favor,
            current_weather=self.world.weather,
            now_ts=time.time(),
            today_str=today_str,
            arc=self.engine.arc.value,  # V14.4：篇章感知（帝国篇过滤宅邸深情模板）
        )
        if letter is not None:
            for m in letter["messages"]:
                role = m["sender"]  # "rem" / "ram"
                sender = "蕾 姆" if role == "rem" else "拉 姆"
                self._append_parsed_message(sender, m["content"], role, save=True)
            # V15.0-M1：来信记账（人生账本，每发件人每日一条）
            try:
                from shared.life_ledger import mirror_letter
                for sender_key in sorted({m["sender"] for m in letter["messages"]}):
                    mirror_letter(sender_key)
            except Exception:
                pass
            _log(f"主动来信触发: {len(letter['messages'])} 条"
                 f" (suppress_vignette={letter['suppress_vignette']})", durable=True)
            # A5（SPEC-20260922-14）：冷却写回**即时持久化**。
            # letter_manager 只在内存里改 state.last_letter_ts/date（其注释明写
            # 「调用方负责持久化 world」），此前调用方没做 → 启动即来信后进程被杀，
            # 冷却丢失 → 同日/8h 内可能重复来信。此处补一次落盘（与日更问候/纪念卡同路径）。
            self._save_state()
        return letter

    def _on_sprite_dropped(self, key: str, src: str) -> None:
        """V14.11：立绘拖入——复制到 data/sprites/{key}.{ext}（文件即持久化，
        重启经 _resolve_sprite 自动生效），刷新面板并给系统提示。"""
        try:
            dst = _copy_user_sprite(src, get_data_dir(), key)
            if not dst:
                self._append_parsed_message(
                    "系统", "立绘替换失败：仅支持 PNG/JPG/WEBP 图片。", "system", save=False)
                return
            panel = self.rem_panel if key == "rem" else self.ram_panel
            if panel is None:
                self._append_parsed_message(
                    "系统",
                    "立绘面板未启用（REZERO_SHOW_SIDE_PANELS=1 可开启侧边角色面板）。",
                    "system", save=False)
                return
            if not panel.set_sprite(dst):
                self._append_parsed_message(
                    "系统", "立绘替换失败：图片无法解码。", "system", save=False)
                return
            name = "蕾姆" if key == "rem" else "拉姆"
            self._append_parsed_message(
                "系统", f"已更新{name}的立绘（重启后依然生效）。", "system", save=False)
            _log(f"立绘替换: {key} -> {dst}")
        except Exception as e:
            _log(f"立绘替换异常: {e}", durable=True)
