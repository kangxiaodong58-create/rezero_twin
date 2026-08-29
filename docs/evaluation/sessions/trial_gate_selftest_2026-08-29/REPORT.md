# 门禁自测报告——故意角色漂移被拦截（审判循环 Phase 2 验收）

**日期**: 2026-08-29
**验收口径**（设计 §5 Phase 2）: 「模拟一次『故意引入角色漂移』被门禁拦截」—— **✅ 达成**
**复现**: `python docs/evaluation/sessions/trial_gate_selftest_2026-08-29/selftest_gate.py`（确定性，退出码即结论）

---

## 一、交付物

| 组件 | 文件 | 说明 |
|---|---|---|
| 人设指纹 v1 | `tools/persona_fingerprint.py` | 8 项指标（自称命中率/动作密度/AI味/情感极性/主动句/毒舌率/自卑率/称呼漂移），读 transcript 输出确定性 JSON；解析器兼容 4 种真机 transcript 格式（probe 带/不带 arc+scene、`label \\| input` 变体、无冒号来信回应、`[来信]` 行） |
| 版本门禁 | `tools/trial_gate.py` | 三关卡：pytest 全绿 → 黄金剧本子序列回放 diff → 指纹漂移阈值（15%，A 级发现即拦截）；exit 0/1/2 |
| 指纹基线 | `docs/evaluation/baselines/persona_fingerprint_v14_9.json` | 由 3 套黄金剧本的真机 LLM transcript 构建（51 用户轮/52 蕾姆段/6 拉姆段/2174 字，零 mock）；含最小样本量保护说明 |
| 黄金剧本 | `docs/evaluation/baselines/golden_inputs_v14_9.json` | 3 套 51 探针：arc 漫游（11）+ V14.8 场景验收（8）+ 宅邸全场景漫游（32），全部来自已归档真机审判 |
| 单测 | `tests/test_trial_gate.py` | 11 项零 API（解析/指标/确定性/子序列/最小样本量/name_drift/门禁端到端双路径） |

**关键方法论修正（构建过程中发现）**：基线语料必须与黄金剧本同源——初版基线用了 9 份 transcript，门禁喂 3 份时出现 4 项假阳性漂移（如 ram_proactive 0.1→0.167，纯小样本波动）。修正为「基线=黄金剧本同语料」+ 漂移对比双侧最小样本量保护（rem/ram≥5 段、sentiment≥10 段、AI味≥500 字，不足自动跳过并提示）。

## 二、基线数值（V14.9，真机 LLM）

| 指标 | 数值 | 备注 |
|---|---|---|
| rem_self_reference_rate | **1.0** | 第三人称自称零违规 |
| rem_action_density | 0.2885 | ≤30% 目标内（B-03 约束生效） |
| ai_flavor_per_kilochar | 0.92 | 极低 |
| sentiment_positive/negative/neutral | 0.138 / 0.0 / 0.862 | 零负向（验收语料无攻击输入） |
| ram_proactive_ratio / ram_snark_rate | 0.167 / 0.333 | 拉姆段 6 条，样本量贴保护线下沿 |
| rem_inferiority_rate | 0.0 | 无自卑表达 |
| name_drift | false | 剧本无名字告知轮 |

## 三、自测结果（双路径）

**对照组（未漂移真机语料，3 份黄金剧本源文件）**：
- gate-1 跳过（--skip-pytest）；gate-2 剧本 diff 3 套/51 探针全部按序命中；gate-3 指纹零漂移
- **退出码 0（放行）** ✅

**实验组（故意漂移，51 探针保留+回复替换为 AI 化蕾姆）**：
- gate-2 仍通过（探针原样，隔离考核指纹关卡）
- gate-3 **5 项 A 级漂移被拦截**：

| 指标 | 基线 → 漂移 | 含义 |
|---|---|---|
| rem_self_reference_rate | 1.0 → 0.0（100%） | 第三人称铁律崩塌（改用「我」） |
| rem_action_density | 0.2885 → 0.0（100%） | 动作描写消失 |
| ai_flavor_per_kilochar | 0.92 → 65.91（7064%） | AI 味词爆发 |
| sentiment_positive_share | 0.138 → 1.0（625%） | 全句正向（情感扁平化） |
| sentiment_neutral_share | 0.862 → 0.0（100%） | 同上 |

- **退出码 1（拦截）** ✅

漂移语料存档：`drifted_transcript.txt`（脚本确定性生成）。

## 四、发布流程接入（Phase 3 前置）

```powershell
# 每次版本发布前（黄金剧本真机跑完后）：
python tools/trial_gate.py --transcripts <本轮 transcript...>
# 三关卡任一失败 → 拦截，A 级漂移按设计进 ISSUE_TRACKER 台账
```

- 完整含 pytest 门禁实测耗时约 25s（pytest ~11s + 剧本 diff/指纹 <1s）；真机剧本跑批费用约 ¥0.3~0.5（51 轮，预算 ¥2/次内）。
- V15.0 发布时以本轮真机 transcript 重算指纹与 V14.9 基线 diff，即完成设计 §5 Phase 3「版本发布流程加审判关卡」的首次全链路。
