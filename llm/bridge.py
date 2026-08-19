"""LLM 桥接模式：硬状态机 + 大模型生成台词。

需要安装 openai：
    pip install openai
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from shared.config import load_env

load_env()

from shared.state import StoryArc, WorldState, StructuredProfile
from shared.prompts import PromptBuilder
from shared.state import HardStateEngine
from shared.conversation_store import ConversationStore
from shared.validators import ResponseValidator


_DEFAULT_KEY = "your-api-key-here"
_VERSION = "10.0.1"  # 懒加载修复版本


def _get_openai():
    """懒加载 openai，避免模块级导入阻断切换模式。"""
    try:
        from openai import OpenAI as _OpenAI
        return _OpenAI
    except ImportError as _e:
        raise ImportError(
            "请先安装 openai 库：pip install openai\n"
            "如果已安装，请检查 Python 环境是否正确。"
        ) from _e


class ReZeroLLMBridge:
    """通过状态机约束 + System Prompt 驱动 LLM 生成双子回复。"""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        model_name: str = "deepseek-chat",
        arc: StoryArc = StoryArc.MANSION_ERA,
        max_history: int = 8,
        conversation_store: Optional[ConversationStore] = None,
        world: Optional[WorldState] = None,  # V14.7：持久化世界状态注入（场景切换）
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY") or _DEFAULT_KEY
        if not key or key == _DEFAULT_KEY:
            raise ValueError("未提供 DEEPSEEK_API_KEY。请在 .env 文件中设置或传入环境变量。")
        OpenAI = _get_openai()
        # V13.0：LLM 请求超时（秒），env REZERO_LLM_TIMEOUT 可覆盖，默认 45
        self.timeout_sec = float(os.getenv("REZERO_LLM_TIMEOUT", "45"))
        self.client = OpenAI(
            api_key=key,
            base_url=base_url,
            timeout=self.timeout_sec,
        )
        self.model_name = model_name
        self.engine = HardStateEngine(arc=arc)
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.world: Optional[WorldState] = world  # 可由 GUI 注入持久化世界状态（V14.7）
        self.conversation_store = conversation_store
        self.validator = ResponseValidator()
        self._first_round_atmosphere: Optional[str] = None  # v10.8.1：首轮氛围（View-Only）
        self._active_scene_id: Optional[str] = None  # V11.10.0：本轮情感场景 ID
        # V13.0：兜底/校验结果回传 GUI + 取消通道（布尔/字符串，GIL 原子，跨线程安全）
        self._last_chat_fallback = False       # chat() 本轮是否为兜底（View-Only）
        self._last_stream_ok: Optional[bool] = None  # 流式校验结果（None=未开始）
        self._stream_fallback_text: str = ""   # 流式校验失败回避文案（View-Only）
        self._active_stream = None             # 当前流式请求（取消用）
        self._stream_cancelled = False         # 取消标志（生成器内检查）
        self._restore_history_from_store()

    def set_opening_atmosphere(self, text: str) -> None:
        """注入开场引言氛围，仅首轮 _build_messages 生效，chat 成功后自动清空。

        铁律：氛围文本绝不进入 history / ConversationStore（View-Only Data）。
        """
        if not text or not isinstance(text, str):
            return
        self._first_round_atmosphere = text[:300] + "…" if len(text) > 300 else text

    def _restore_history_from_store(self, limit: Optional[int] = None) -> None:
        """从 ConversationStore 恢复最近 N 轮对话到 bridge.history。

        映射规则：
        - 'user' / 'assistant' → 直接映射为同 role
        - 'rem' / 'ram' → 合并为一条 assistant 消息，前缀补回【蕾姆】/【拉姆】
        - 'system' / 其它 → 跳过，避免污染 LLM 上下文

        取数时多取若干行以抵消 system 消息和 rem/ram 拆分带来的膨胀，
        映射完成后再截取最后 limit 条。

        恢复失败时不抛异常，仅记录警告并保留空 history，确保 Bridge 能正常启动。
        """
        if self.conversation_store is None:
            return

        try:
            limit = self.max_history if limit is None else limit
            if limit <= 0:
                self.history = []
                return

            # 多取一些行，确保在存在 system 和 rem/ram 拆分时仍能凑够 limit 条有效消息
            fetch_limit = max(limit * 4, 20)
            rows = self.conversation_store.get_recent(limit=fetch_limit)

            restored: List[Dict[str, str]] = []
            assistant_buffer: List[str] = []

            def _flush_assistant() -> None:
                nonlocal assistant_buffer
                if assistant_buffer:
                    restored.append({"role": "assistant", "content": "\n".join(assistant_buffer)})
                    assistant_buffer = []

            for row in rows:
                role = row.get("role", "")
                content = (row.get("content") or "").strip()
                if not content:
                    continue
                if row.get("status", "normal") != "normal":
                    # V14.0：failed/recalled/deleted 均不进 LLM 上下文
                    # （GUI 展示路径与搜索的过滤差异见 ConversationStore.get_recent 注释）
                    continue
                if role == "user":
                    _flush_assistant()
                    restored.append({"role": "user", "content": content})
                elif role == "assistant":
                    _flush_assistant()
                    restored.append({"role": "assistant", "content": content})
                elif role == "rem":
                    assistant_buffer.append(f"【蕾姆】{content}")
                elif role == "ram":
                    assistant_buffer.append(f"【拉姆】{content}")
                # system 及其它角色跳过
            _flush_assistant()

            self.history = restored[-limit:]
        except Exception as e:
            logging.warning("从 ConversationStore 恢复 LLM 历史失败: %s", e)
            self.history = []

    def _build_messages(self, user_input: str, reply_to: Optional[Dict[str, Any]] = None):
        state = self.engine.update(user_input)
        world = self.world or WorldState.now()
        profile = StructuredProfile.from_engine(self.engine)
        # V14.7：空间场景切换识别（「去厨房」「回房间」→ 更新 world.scene + 开场）
        scene_opening = None
        try:
            from shared.scene_manager import SceneManager
            new_scene = SceneManager.parse_scene_change(user_input)
            if new_scene and world.scene != new_scene:
                world.scene = new_scene
                scene_opening = SceneManager.get_scene_opening(
                    new_scene, world.period, world.weather,
                    arc=getattr(state, "arc", None).value if getattr(state, "arc", None) else None)
                logging.info("V14.7 场景切换 → %s", new_scene)
                # V14.7 优化 O-1：场景切换联动事件——若当前事件地点与新场景冲突
                # （如切到书库但事件是「走廊红茶」），刷新事件保持场景一致性
                try:
                    if world.active_event:
                        from shared import vignette as _v
                        loc = _v._derive_location(world.active_event)
                        # 事件地点含场景关键词且与新场景中文名不同 → 冲突刷新
                        scene_cn = PromptBuilder.SCENE_CN.get(new_scene, new_scene)
                        if loc != "罗兹瓦尔宅邸" and scene_cn and scene_cn not in loc:
                            world.refresh_active_event(scene=new_scene)  # V14.8：带场景约束刷新
                            logging.info("O-1 场景联动：事件刷新 %s → %s",
                                         loc, world.active_event[:20])
                except Exception:
                    pass  # 联动失败不影响场景切换
        except Exception:
            scene_opening = None  # 场景系统故障不阻断对话
        # V11.10.0：情感场景检测（在 Prompt 构建前）
        scene_id, ram_witness = self._detect_scene(user_input, state, world)
        self._active_scene_id = scene_id
        system_prompt = PromptBuilder.build(state, world=world, profile=profile,
                                            scene_id=scene_id, ram_witness=ram_witness,
                                            user_input=user_input,
                                            scene_opening=scene_opening)  # V14.4/14.7
        # v10.8.1：首轮氛围注入（View-Only，不进 history，不写 ConversationStore）
        if not self.history and self._first_round_atmosphere:
            system_prompt += (
                "\n\n### 开场氛围（仅本轮参考，请自然融入回复的情境感，"
                "不要复述或引用这段文字）\n"
                + self._first_round_atmosphere
                + "\n"
            )
        # V14.2：引用注入（仅本轮 Prompt，不进 history / 不落库 / 不写 events）
        if reply_to:
            preview = (reply_to.get("preview") or "").strip()
            if preview:
                system_prompt += (
                    "\n\n### 用户引用了你之前的话（仅本轮参考，请针对这段被引用的内容回应，"
                    "不要复述引用标记）\n「"
                    + preview
                    + "」\n"
                )
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        messages.extend(self.history[-self.max_history:])
        messages.append({"role": "user", "content": user_input})
        return messages, state

    # ── V11.10.0：情感场景检测 ──

    SCENE_KEYWORDS = {
        "hug_accept": ["抱", "拥抱", "抱住", "抱抱"],
        "headpat_comfort": ["摸头", "抚头", "摸摸头", "摸摸"],
        "identity_affirm": ["你是蕾姆", "不是影子", "你就是蕾姆"],
        # V14.4（LLM 优先内容路线 P0）：场景库扩充 4→12
        "farewell_weight": ["离开", "告别", "分别", "走了", "再见", "如果有一天我"],
        "reunion_tenderness": ["我回来了", "我回宅邸了", "回来了"],
        "battle_weary": ["好累", "太累了", "战斗", "虚脱", "撑不住", "筋疲力尽"],
        "midnight_confession": ["睡不着", "月色真美", "月色很美", "深夜", "说说话"],
        "wish_offer": ["想一直", "希望", "如果", "就好了", "愿望"],
        "apology_accept": ["对不起", "抱歉", "我错了", "请原谅"],
        "guardian_vow": ["会保护", "会珍惜", "不会让", "守护你们", "保护你们"],
        "daily_glow": ["真好喝", "真好吃", "今天很开心", "普通的幸福", "岁月静好"],
    }
    SCENE_FAVOR_MIN = {
        "hug_accept": 3,       # FavorLevel.DEAR
        "headpat_comfort": 2,  # FavorLevel.CLOSE
        "identity_affirm": 2,  # FavorLevel.CLOSE
        "breaker_promise": 3,  # FavorLevel.DEAR
        # V14.4：新场景好感门槛（farewell/battle/daily 低门槛，亲密类高门槛）
        "farewell_weight": 1,      # FAMILIAR（离别是基础情感）
        "reunion_tenderness": 1,   # FAMILIAR
        "battle_weary": 1,         # FAMILIAR
        "midnight_confession": 2,  # CLOSE
        "wish_offer": 2,           # CLOSE
        "apology_accept": 1,       # FAMILIAR
        "guardian_vow": 3,         # DEAR（守护誓言是高重量场景）
        "daily_glow": 1,           # FAMILIAR（日常闪光低门槛，调剂场景）
    }
    SCENE_COOLDOWN_HOURS = 24

    def _detect_scene(self, user_input: str, state, world) -> tuple:
        """检测本轮情感场景，返回 (scene_id | None, ram_witness: bool)。

        优先级（互斥）：breaker > identity > hug > headpat > 高重量(guardian/farewell) > 亲密(confession/wish) > 轻场景。
        V14.4：场景库扩充 4→12，新增场景按重量降序接入；低门槛调剂场景（daily_glow）最后兜底。
        复用 engine._is_negated 检测「不是替代品」式肯定句。
        """
        text = user_input
        favor_level = int(state.favor_level)
        ram_witness = state.ram_stage.value in ("观察中", "还算守规矩", "勉强认可", "真正承认")

        # breaker_promise：「替代品」被否定 或 「蕾姆就是蕾姆」
        is_breaker = (
            ("替代品" in text and self.engine._is_negated(text, "替代品"))
            or "蕾姆就是蕾姆" in text
        )
        if is_breaker and favor_level >= self.SCENE_FAVOR_MIN["breaker_promise"]:
            if not self._is_cooled_down("breaker_promise", world):
                return "breaker_promise", ram_witness

        # identity_affirm
        if any(k in text for k in self.SCENE_KEYWORDS["identity_affirm"]):
            if favor_level >= self.SCENE_FAVOR_MIN["identity_affirm"]:
                if not self._is_cooled_down("identity_affirm", world):
                    return "identity_affirm", ram_witness

        # hug_accept
        if any(k in text for k in self.SCENE_KEYWORDS["hug_accept"]):
            if favor_level >= self.SCENE_FAVOR_MIN["hug_accept"]:
                if not self._is_cooled_down("hug_accept", world):
                    return "hug_accept", ram_witness

        # headpat_comfort
        if any(k in text for k in self.SCENE_KEYWORDS["headpat_comfort"]):
            if favor_level >= self.SCENE_FAVOR_MIN["headpat_comfort"]:
                if not self._is_cooled_down("headpat_comfort", world):
                    return "headpat_comfort", ram_witness

        # V14.4：新场景（按重量降序）
        for scene_id in ("guardian_vow", "farewell_weight", "midnight_confession",
                         "wish_offer", "battle_weary", "reunion_tenderness",
                         "apology_accept", "daily_glow"):
            if any(k in text for k in self.SCENE_KEYWORDS[scene_id]):
                if favor_level >= self.SCENE_FAVOR_MIN[scene_id]:
                    if not self._is_cooled_down(scene_id, world):
                        return scene_id, ram_witness

        return None, False

    def _is_cooled_down(self, scene_id: str, world) -> bool:
        """检查场景是否在冷却期内（24h）。"""
        from datetime import datetime, timedelta
        last = (world.scene_cooldowns or {}).get(scene_id, "")
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
            return datetime.now() - last_dt < timedelta(hours=self.SCENE_COOLDOWN_HOURS)
        except Exception:
            return False

    def _write_scene_cooldown(self, world) -> None:
        """成功生成后写入场景冷却时间戳。"""
        if self._active_scene_id and world is not None:
            from datetime import datetime
            if not hasattr(world, 'scene_cooldowns') or world.scene_cooldowns is None:
                world.scene_cooldowns = {}
            world.scene_cooldowns[self._active_scene_id] = datetime.now().isoformat(timespec="seconds")

    def _fallback_reply(self) -> str:
        """校验彻底失败时的安全兜底回复。

        V13.0：文案改为「角色内回避」，禁止失忆感（T1-05 验收缺陷）。
        """
        return (
            '【蕾姆】: "……这个话题，蕾姆想先放一放。您愿意说点别的吗？"\n'
            '【拉姆】: "哼。刚才那段，拉姆建议换个说法再试。"'
        )

    def _generate_validated(
        self,
        user_input: str,
        messages: List[Dict[str, Any]],
        temperature: float,
        max_tokens: int,
    ) -> Tuple[str, bool]:
        """调用 LLM 并校验回复；失败时重试 1 次，仍失败返回安全 fallback。

        V13.0：返回 (reply, is_fallback)。is_fallback=True 表示兜底文本，
        调用方不得写入 history（View-Only 数据）。
        """
        for attempt in range(2):
            current_temp = temperature if attempt == 0 else max(0.1, temperature - 0.25)
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=current_temp,
                max_tokens=max_tokens,
            )
            reply = response.choices[0].message.content.strip()
            result = self.validator.validate(reply)
            # V14.6 E-5：软检查（WARNING 不阻断，仅记录提示）
            if result.ok and result.ooc_warnings:
                logging.warning(
                    "V14.6 原著一致性软检查命中 %d 项: %s",
                    len(result.ooc_warnings),
                    ", ".join(result.ooc_warnings[:5]),
                )
            if result.ok:
                return result.cleaned or reply, False
            logging.warning(
                "LLM 回复校验失败 (attempt %d): %s | raw: %s",
                attempt + 1,
                result.reason,
                reply[:200],
            )
        return self._fallback_reply(), True

    def chat(
        self,
        user_input: str,
        *,
        temperature: float = 0.65,
        max_tokens: int = 600,
        reply_to: Optional[Dict[str, Any]] = None,  # V14.2：引用回复（仅本轮 Prompt 注入）
    ) -> str:
        messages, _state = self._build_messages(user_input, reply_to=reply_to)
        try:
            reply, is_fallback = self._generate_validated(
                user_input, messages, temperature, max_tokens
            )
        except Exception as e:
            logging.warning("chat API 调用失败: %s", e)
            # V11.10.0：错误返回角色格式，不写【系统】（避免被解析器误分类）
            self._active_scene_id = None
            self._last_chat_fallback = True
            return '【蕾姆】: "……蕾姆好像没听清。请再说一次好吗？"'
        if is_fallback:
            # V13.0：校验失败兜底 = View-Only——不写 history、不清首轮氛围、
            # 不写场景冷却（mark_interaction 保留：用户确实产生了互动）。
            logging.warning("chat 校验失败重试耗尽，返回 View-Only 兜底（不写 history）")
            self._last_chat_fallback = True
            self._active_scene_id = None
            return reply
        self._last_chat_fallback = False
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": reply})
        self._first_round_atmosphere = None  # v10.8.1：首轮氛围一次性消费
        # V11.10.0：成功生成后写入场景冷却
        if self.world is not None:
            self._write_scene_cooldown(self.world)
            self.world.mark_interaction()
        else:
            self._write_scene_cooldown(None)
        return reply

    def chat_stream(self, user_input: str, *, temperature: float = 0.65, max_tokens: int = 600,
                    reply_to: Optional[Dict[str, Any]] = None):  # V14.2：引用回复（仅本轮 Prompt 注入）
        """流式聊天：返回 (generator, state_snapshot)。

        V13.0：
        - 完整生成结束后后验校验；校验失败不写 history，结果经 _last_stream_ok
          回传 GUI（由 GUI 展示 View-Only 回避文案）。
        - 取消通道：cancel_stream() 置 _stream_cancelled 并关闭底层流，
          生成器在下一个检查点静默提前结束，不校验、不写 history。
        """
        messages, state = self._build_messages(user_input, reply_to=reply_to)
        # V13.0：每次调用重置流式状态（防陈旧回传）
        self._last_stream_ok = None
        self._stream_fallback_text = ""
        self._stream_cancelled = False
        self._active_stream = None
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            self._active_stream = stream

            def _generator():
                full = ""
                try:
                    for chunk in stream:
                        if self._stream_cancelled:
                            # V13.0：用户取消——静默结束，不校验、不写 history
                            return
                        delta = chunk.choices[0].delta.content
                        if delta:
                            full += delta
                            yield delta

                    if self._stream_cancelled:
                        return

                    # 流式完整输出结束后校验；失败仅记录日志，不污染 history
                    result = self.validator.validate(full)
                    # V14.6 E-5：软检查（WARNING 不阻断，仅记录提示）
                    if result.ok and result.ooc_warnings:
                        logging.warning(
                            "V14.6 原著一致性软检查命中 %d 项: %s",
                            len(result.ooc_warnings),
                            ", ".join(result.ooc_warnings[:5]),
                        )
                    if result.ok:
                        self._last_stream_ok = True
                        final = result.cleaned or full
                        self.history.append({"role": "user", "content": user_input})
                        self.history.append({"role": "assistant", "content": final})
                        self._first_round_atmosphere = None  # v10.8.1：首轮氛围一次性消费
                        # V11.10.0：成功生成后写入场景冷却
                        if self.world is not None:
                            self._write_scene_cooldown(self.world)
                            self.world.mark_interaction()
                    else:
                        # V13.0：校验失败回传 GUI，由 GUI 展示 View-Only 回避文案
                        self._last_stream_ok = False
                        self._stream_fallback_text = self._fallback_reply()
                        logging.warning(
                            "流式 LLM 回复校验失败，跳过写入 history: %s | input: %s | full: %s",
                            result.reason,
                            user_input[:50],
                            full[:200],
                        )
                        self._active_scene_id = None
                except Exception:
                    # V13.1（真机抽测暴露）：cancel_stream() 关闭底层 socket 后，
                    # 进行中的迭代会抛 httpx.ReadError（WinError 10038）——取消引发的
                    # 读中断应静默结束（V13.0「取消=安静」契约）；真实异常继续上抛。
                    if self._stream_cancelled:
                        return
                    raise
                finally:
                    # V13.0：无论取消/异常/正常结束，关闭底层流并释放引用
                    try:
                        stream.close()
                    except Exception:
                        pass
                    self._active_stream = None

            return _generator(), state
        except Exception as e:
            logging.warning("chat_stream API 调用失败: %s", e)
            self._active_scene_id = None
            self._last_stream_ok = False
            self._stream_fallback_text = ""

            def _err():
                # V11.10.0：错误返回角色格式，不写【系统】（避免被解析器误分类）
                yield '【蕾姆】: "……蕾姆好像没听清。请再说一次好吗？"'
            return _err(), state

    def cancel_stream(self) -> None:
        """V13.0：中断当前流式请求（主线程可调用，线程安全）。

        置取消标志 + 关闭底层 httpx 流；工作线程的生成器会在下一个
        检查点静默提前结束（不校验、不写 history）。
        """
        self._stream_cancelled = True
        if self._active_stream is not None:
            try:
                self._active_stream.close()
            except Exception:
                pass

    def status(self) -> str:
        state = self.engine.snapshot()
        d = state.to_prompt_dict()
        lines = [f"{k}: {v}" for k, v in d.items()]
        return "===== 当前硬状态 =====\n" + "\n".join(lines)

    def set_arc(self, arc: StoryArc) -> None:
        self.engine.set_arc(arc)

    def recover(self, progress: float = 1.0) -> None:
        self.engine.recover(progress)

    def raw_completion(self, system_prompt: str, user_prompt: str = "", *, temperature: float = 0.8, max_tokens: int = 200) -> str:
        """原始 API 调用（不经角色 system prompt）。用于开场引言等独立生成。"""
        messages: List[Dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"（{e}）"
