"""V14.11 体验补全测试：名场面冷却（O-5）/ 偶发一句（Step 5）/ history 裁剪 / 立绘自定义。

覆盖（研判第四批验收口径）：
- O-5：名场面语感注入 24h 冷却——命中 → 注入 → consume → 冷却内抑制 →
  冷却期内 consume 不续期 → 到期恢复 → 随存档持久化
- Step 5：ambient_remark 门控（无事件不放行 / 同事件仅 1 句 / 冷却 2h /
  每日 3 条上限）+ registry 三 arc 文案契约 + 确定性选型 + 厨房小池加厚
- history：bridge._trim_history 运行中有界（与重启恢复口径一致）
- 立绘：_copy_user_sprite / _resolve_sprite 优先级 / CharacterPanel.set_sprite（离屏）
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

# ── 必须在 import PySide6 / gui 之前设置 ──
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("REZERO_DISABLE_VIGNETTE", "1")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest  # noqa: E402

from shared.scene_manager import SceneManager  # noqa: E402
from shared.state import HardStateEngine, WorldState  # noqa: E402
from shared.template_registry import load_registry, pick as registry_pick  # noqa: E402

REGISTRY_PATH = os.path.join(PROJECT_ROOT, "content", "templates", "registry.json")
SCENE_JSON = os.path.join(PROJECT_ROOT, "content", "scene_dialogue.json")


# ── O-5：名场面冷却 ───────────────────────────────────────────────

def _loyal_engine() -> HardStateEngine:
    eng = HardStateEngine()
    eng.favor = 96  # ≥95 → loyalty_lock 名场面
    return eng


def test_milestone_gated_flow():
    world = WorldState()
    eng = _loyal_engine()
    ms = SceneManager.get_milestone_for_prompt(eng, world)
    assert ms is not None and ms["name"], "首次命中应注入名场面语感"
    SceneManager.consume_milestone(world, eng)
    assert world.milestone_cooldowns.get(ms["name"]), "consume 应记录冷却起点"
    assert SceneManager.get_milestone_for_prompt(eng, world) is None, \
        "24h 冷却内应被抑制（O-5 防疲劳）"


def test_milestone_cooldown_expiry_and_no_extend():
    world = WorldState()
    eng = _loyal_engine()
    SceneManager.consume_milestone(world, eng)
    name = next(iter(world.milestone_cooldowns))
    world.milestone_cooldowns[name] = (
        datetime.now() - timedelta(hours=25)).isoformat(timespec="seconds")
    assert SceneManager.get_milestone_for_prompt(eng, world) is not None, "到期应恢复注入"
    # 冷却中被抑制的名场面不得被 consume 续期
    world.milestone_cooldowns[name] = datetime.now().isoformat(timespec="seconds")
    ts1 = world.milestone_cooldowns[name]
    SceneManager.consume_milestone(world, eng)
    assert world.milestone_cooldowns[name] == ts1, "冷却期内 consume 不应刷新时间戳"


def test_milestone_persistence_roundtrip():
    world = WorldState()
    eng = _loyal_engine()
    SceneManager.consume_milestone(world, eng)
    ws2 = WorldState.load_or_create(world.save_dict())
    assert SceneManager.get_milestone_for_prompt(eng, ws2) is None, \
        "冷却状态应随存档持久化（重启不重置）"


# ── Step 5：偶发一句 ──────────────────────────────────────────────

def test_ambient_gating_rules():
    world = WorldState()
    assert not world.ambient_remark_allowed(), "无活跃事件不放行"
    world.active_event_id = "afternoon_tea"
    assert world.ambient_remark_allowed(now_ts=1000.0), "新事件放行"
    world.record_ambient_remark(now_ts=1000.0)
    assert not world.ambient_remark_allowed(now_ts=2000.0), "同事件 TTL 内仅 1 句"
    world.active_event_id = "night_patrol"
    assert not world.ambient_remark_allowed(now_ts=1000.0 + 3600.0), "冷却 2h 内不放行"
    assert world.ambient_remark_allowed(now_ts=1000.0 + 2 * 3600.0 + 1.0), "冷却 2h 后放行"
    world.record_ambient_remark(now_ts=1000.0 + 2 * 3600.0 + 1.0)
    world.active_event_id = "flower_garden"
    world.record_ambient_remark(now_ts=1000.0 + 3 * 3600.0)
    world.active_event_id = "morning_light"
    world.record_ambient_remark(now_ts=1000.0 + 4 * 3600.0)
    world.active_event_id = "night_patrol"
    assert not world.ambient_remark_allowed(now_ts=1000.0 + 5 * 3600.0), "每日 3 条上限"
    tomorrow = 1000.0 + 24 * 3600.0
    assert world.ambient_remark_allowed(now_ts=tomorrow), "跨日后计数重置放行"


def test_ambient_registry_contract():
    reg = load_registry(REGISTRY_PATH)
    for arc in ("mansion_era", "empire_era", "late_arc"):
        item = registry_pick(reg, arc=arc, slot="ambient_remark",
                             period="午后", weather="晴朗", seed="2026-08-29|ev1")
        assert item is not None, f"{arc} 应有 ambient_remark 条目"
        assert item.get("text"), "文案非空"
    a = registry_pick(reg, arc="mansion_era", slot="ambient_remark",
                      period="午后", weather="晴朗", seed="s1")
    b = registry_pick(reg, arc="mansion_era", slot="ambient_remark",
                      period="午后", weather="晴朗", seed="s1")
    assert a["id"] == b["id"], "同 seed 选型稳定"


def test_ambient_state_persistence_roundtrip():
    world = WorldState()
    world.active_event_id = "afternoon_tea"
    world.record_ambient_remark(now_ts=1000.0)
    ws2 = WorldState.load_or_create(world.save_dict())
    assert ws2.ambient_state.get("last_event_id") == "afternoon_tea"
    assert not ws2.ambient_remark_allowed(now_ts=2000.0), "事件去重随存档持久化"


def test_kitchen_pool_thickened():
    """研判 P2：厨房小池加厚——三个时段 interaction 各 ≥3。"""
    d = json.load(open(SCENE_JSON, encoding="utf-8"))
    kitchen = d["mansion_era"]["KITCHEN"]
    for slot in ("MORNING", "AFTERNOON", "NIGHT"):
        n = len([k for k in kitchen[slot] if k.startswith("interaction")])
        assert n >= 3, f"KITCHEN.{slot} interactions {n} < 3"


# ── history 裁剪 ──────────────────────────────────────────────────

def test_bridge_trim_history():
    from llm.bridge import ReZeroLLMBridge
    bridge = ReZeroLLMBridge(api_key="sk-test", conversation_store=None)
    bridge.max_history = 8
    for i in range(20):
        bridge.history.append({"role": "user", "content": str(i)})
        bridge.history.append({"role": "assistant", "content": "reply"})
        bridge._trim_history()
        assert len(bridge.history) <= 8
    assert bridge.history[-1]["content"] == "reply", "裁剪保留最新内容"


# ── 立绘自定义 ────────────────────────────────────────────────────

def test_copy_and_resolve_user_sprite(tmp_path):
    import gui
    src = os.path.join(PROJECT_ROOT, "assets", "app_icon.png")
    assert gui._copy_user_sprite(src, str(tmp_path), "rem").endswith("rem.png")
    # 覆盖旧扩展名：换 jpg 后旧 png 被清理
    from PySide6.QtGui import QImage
    jpg = tmp_path / "in.jpg"
    assert QImage(src).save(str(jpg), "JPG"), "测试前置：生成 jpg 失败"
    dst = gui._copy_user_sprite(str(jpg), str(tmp_path), "rem")
    assert dst.endswith("rem.jpg")
    assert not os.path.exists(os.path.join(tmp_path, "sprites", "rem.png")), "旧扩展名应清理"
    # 非法扩展名拒绝
    bad = tmp_path / "x.gif"
    bad.write_bytes(b"GIF89a")
    assert gui._copy_user_sprite(str(bad), str(tmp_path), "rem") == ""
    # 解析优先级：用户自定义 > assets > 空占位
    assert gui._resolve_sprite(str(tmp_path), "rem", "asset_fallback") == \
        os.path.join(str(tmp_path), "sprites", "rem.jpg")
    empty_dir = tmp_path / "none"
    empty_dir.mkdir()
    assert gui._resolve_sprite(str(empty_dir), "rem", "asset_fallback") == "asset_fallback"


def test_character_panel_set_sprite_offscreen(tmp_path):
    import gui
    from PySide6.QtWidgets import QApplication
    _ = QApplication.instance() or QApplication([])
    panel = gui.CharacterPanel("测试", "🩵", "#ffffff", sprite_path="", character_key="rem")
    assert panel._placeholder_label is not None, "无图应显示占位"
    ok = panel.set_sprite(os.path.join(PROJECT_ROOT, "assets", "app_icon.png"))
    assert ok, "有效图片应加载成功"
    assert panel._placeholder_label.isHidden(), "加载后占位应隐藏"
    assert not panel.set_sprite(str(tmp_path / "missing.png")), "缺失路径返回 False"
