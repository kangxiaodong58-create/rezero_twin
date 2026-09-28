"""环境开关 / 氛围注册表（动效、侧栏、引子、历史、氛围事件表）。"""

from __future__ import annotations

import os


# 开场引言开关（V10.10.3）：环境变量 REZERO_DISABLE_VIGNETTE=1 可禁用引言做二分排查
_VIGNETTE_DISABLED = os.environ.get("REZERO_DISABLE_VIGNETTE", "") == "1"


# 历史浮层开关（V10.10.2）：环境变量 REZERO_DISABLE_HISTORY=1 可禁用浮层做二分排查
_HISTORY_DISABLED = os.environ.get("REZERO_DISABLE_HISTORY", "") == "1"


def _ui_motion_enabled() -> bool:
    """V16-M_B：动效统一门——收敛到 motion.enabled()（offscreen 恒禁用 /
    REZERO_DISABLE_UI_MOTION 旧开关兼容 / token 总开关）。"""
    try:
        import motion
        return motion.enabled()
    except Exception:
        return False


# 默认**不构造**隐藏面板：原实现构造 rem/ram 两个 CharacterPanel 后无条件 hide()，
# 却仍有 5 处 update_state/set_speaking/set_sprite 持续推送（台账 B3/D3「双写」债）。
# 排障/回滚：`REZERO_SHOW_SIDE_PANELS=1` 启动即恢复旧行为（面板构造 + 拖入换立绘可达）。
def _side_panels_enabled() -> bool:
    """侧边角色面板显式开关（默认关：面板构造后即被隐藏，纯死重）。"""
    return os.environ.get("REZERO_SHOW_SIDE_PANELS", "") not in ("", "0", "false", "False")


# 称呼提示开关（SPEC-20260922-24）：氛围行因脏名降级时只提示**一次**（每进程），
# 避免每次刷新刷屏；进程重启后允许再提示一次。
_name_hint_shown = False


def name_hint_once() -> bool:
    """一次性提示闸：仅首次调用返回 True（供「建议用 /称呼 设名」提示用）。"""
    global _name_hint_shown
    if _name_hint_shown:
        return False
    _name_hint_shown = True
    return True


def _get_ambient_registry() -> dict:
    global _AMBIENT_REGISTRY
    if _AMBIENT_REGISTRY is None:
        try:
            from shared.template_registry import load_registry
            from shared.vignette import ContentLoader
            _AMBIENT_REGISTRY = load_registry(os.path.join(
                ContentLoader()._get_content_dir(), "templates", "registry.json"))
        except Exception:
            _AMBIENT_REGISTRY = {"schema_version": "0", "items": [], "skipped": 0}
    return _AMBIENT_REGISTRY


