# V14.8 场景互动池扩池落地报告（2026-08-19）

> 文案组交付 V14.8 Part1（帝国 3 场景）+ Part2（后期 3 场景）72 句全量落地
> 结论：**scene_dialogue 加 arc 维度完成；篇章均衡性修复（帝国/后期场景不再注入宅邸文案）**
> 测试：135/135 × 3 连跑全绿（含 O-1 flaky 修复）

---

## 一、落地内容

### 1. scene_dialogue.json 结构升级 1.0 → 2.0（arc 维度）
```
{
  "schema_version": "2.0",
  "mansion_era": { KITCHEN/ROOM/DINING/LIBRARY/HALLWAY/LAUNDRY/GARDEN },  # 原样保留
  "empire_era":  { CAMP/INN/WILDERNESS },    # 新：营地/旅店/荒野（失忆疏离语感）
  "late_arc":    { CAMPFIRE/BARRACKS/BATTLEFIELD }  # 新：营火/军营/战场（战友托付语感）
}
```
- 共 67 组视角（mansion 20 + empire 23 + late 24）
- 文案组内容原样落位（未删改），OOC 红线自查（帝国无宅邸元素/后期无早期「可疑客人」腔）

### 2. SceneManager 改造
- `_scenes(arc)`：arc 维度读取（未知 arc / 旧结构回落 mansion）
- `get_scene_opening/get_scene_interaction` 加 arc 参数（默认 mansion，旧调用兼容）
- `_PERIOD_SLOTS` 加 6 新场景时段映射；互动去重 key 含 arc（跨篇章不串用）

### 3. 场景切换扩展
- `SCENE_KEYWORDS` 加 6 场景关键词（营地/营帐/帐篷→CAMP，旅店/客栈/酒馆→INN，荒野/荒原/旷野→WILDERNESS，营火/篝火/火堆→CAMPFIRE，军营/军帐→BARRACKS，战场/前线→BATTLEFIELD）
- `SCENE_CN`（prompts.py）+ `_derive_location`（vignette.py）补 6 场景
- bridge 场景切换传 arc；prompts 场景注入按 arc 取库

### 4. O-1 缺陷修复（flaky 暴露的产品 bug）
- **发现**：`refresh_active_event` 用相同 weather_seed 重选——可能选中同一冲突事件（seed=42 切书库仍选走廊事件），O-1「消除冲突」目标未达成（3 跑 1 败 flaky 暴露）
- **修复**：`refresh_active_event(scene=None)` 带场景约束——用 `_derive_location` 校验事件地点，冲突则换 seed 重试（最多 5 次）；所有 seed 下稳定收敛到书库事件
- **验证**：5 个 seed 全部冲突消除；135/135 × 3 连跑全绿

---

## 二、篇章均衡性改善

| 资产 | 前 | 后 |
|---|---|---|
| 场景互动池 | 7 宅邸（无 arc） | 13 场景 × 3 arc（67 组视角） |
| 帝国篇场景 | 无（切场景注入宅邸文案） | CAMP/INN/WILDERNESS ✅ |
| 后期篇场景 | 无 | CAMPFIRE/BARRACKS/BATTLEFIELD ✅ |
| 语感差异 | 单一女仆腔 | 宅邸日常 / 帝国疏离试探 / 后期并肩托付 |

**架构效果**（文案组描述达成）：`arc → scene → character_state → dialogue_style`——同一「用户陪伴」在不同篇章完全不同（宅邸「完成女仆职责」/ 帝国「想确认为何信任您」/ 后期「蕾姆会站在您身边」）。

---

## 三、测试

- 新增 `tests/test_v148_arc_scenes.py`（5 用例）：arc opening / interaction 语感区分 / 未知 arc 回落 / 新场景关键词 / JSON 结构
- O-1 测试固定 seed + 场景约束刷新
- 全量 **135/135 × 3 连跑全绿**

## 四、成本

零 API（纯内容 + 逻辑落地，无 LLM 真机调用）
