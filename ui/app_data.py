"""静态数据表（呼称/问候/导航/羁绊阶段/天气从句/世界反馈）。"""

from __future__ import annotations



ARC_CN = {
    "mansion_era": "宅邸篇",
    "empire_era": "帝国篇（失忆）",
    "late_arc": "后期篇",
}


# 骨架不含天气/其它时段词，天气由 WEATHER_CLAUSES 白名单注入。
GREETING_TEMPLATES = {
    "清晨": "早安。蕾姆已经备好了早餐。{weather_clause}{event_clause}",
    "上午": "上午好。宅邸的走廊已经亮起来了。{weather_clause}{event_clause}",
    "午后": "午安。刚泡好的红茶还冒着热气。{weather_clause}{event_clause}",
    "下午": "下午好。宅邸很安静。{weather_clause}{event_clause}",
    "傍晚": "傍晚了。天色渐暗，蕾姆点了灯。{weather_clause}{event_clause}",
    "夜晚": "晚上好。夜风有些凉。{weather_clause}{event_clause}",
    "深夜": "这么晚了还没休息吗。{weather_clause}{event_clause}",
}


# 左导航与底部图标坞**同表驱动**（禁止两处各写一份入口列表——V16 前两处各 7/6 项，
# 其中「日程/任务/插件」三条同指 /status、「设置」绑空转命令、「主页」与「对话」同动作）。
# 结构断言（tests/test_command_router.py）：id/label/handler 唯一、图标资产存在、不得出现空转命令。
NAV_ENTRIES = (
    {"id": "chat",    "label": "对话", "icon": "icon_chat.svg",     "handler": "_nav_focus_input"},
    {"id": "memory",  "label": "记忆", "icon": "icon_memory.svg",   "handler": "_open_memory_book"},
    {"id": "status",  "label": "状态", "icon": "icon_calendar.svg", "handler": "_nav_open_status"},
    {"id": "history", "label": "历史", "icon": "icon_info.svg",     "handler": "_open_history"},
)


# ═══════════════════════════════════════════════
#  显示层中文映射（V10.9.1）
#  V11.7：FAVOR_LEVEL_CN 已迁移至 shared.state（唯一真源）
#  ONI_STAGE_CN / ARC_CN 仅 GUI 使用，保留本地
# ═══════════════════════════════════════════════
ONI_STAGE_CN = {
    "NONE": "无",
    "EMERGING": "显现",
    "FULL": "完全解放",
    "BRINK": "失控边缘",
}


# 天气从句白名单：覆盖 WorldState.WEATHERS 全部 5 种，未知天气中性兜底。
WEATHER_CLAUSES = {
    "晴朗": "窗外天气晴朗。",
    "多云": "云层遮住了部分天空。",
    "小雨": "窗外飘着小雨。",
    "大雨": "雨下得很大，宅邸的屋檐传来急促的滴水声。",
    "阴沉": "天空阴沉沉的。",
}


# UI 动效开关（V12.0）：环境变量 REZERO_DISABLE_UI_MOTION=1 可整体关闭动效（验收对比/回滚）
# V16-M_F：状态反馈的世界内表达（DESIGN 解析 §2.5）——
# 不用"生成中/AI 思考中"等系统术语，让反馈留在宅邸世界观里。
WORLD_FEEDBACK = {
    "rem": "蕾姆正在斟酌话语…",
    "ram": "拉姆正在挑选用词…",
    "user": "双子正在准备回应…",
}


