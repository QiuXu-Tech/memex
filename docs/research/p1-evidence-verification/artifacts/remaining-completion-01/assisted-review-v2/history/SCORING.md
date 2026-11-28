# P1 封存运行的 evaluator 评分合同

**评分器聚合显式判断，不自动生成标签或执行隐藏测试。** 当前仓库没有由此产生的真实 P1 人工评分。所有新增测试均为清楚标记的 fixture，零个人工评审、零个研究样本。

## 1. 流水线与边界

先用现有 `annotation.py` 形成真实双审与裁决，再冻结义务和检查清单；方法执行由 `experiment.py` 封存；人类 evaluator 审查具体输出及行为收据；最后 `score.py` 聚合，供现有 `experiment.py join` 使用。完整费用仍由 join 计算。

```bash
python -B scripts/paper1/score.py \
  --plan /absolute/frozen-plan \
  --state /absolute/execution-state \
  --labels /absolute/evaluator/frozen-labels.json \
  --assessments /absolute/evaluator/run-assessments.jsonl \
  --output /absolute/new-scored

python -B scripts/paper1/experiment.py join \
  --plan /absolute/frozen-plan \
  --state /absolute/execution-state \
  --quality /absolute/new-scored/quality.jsonl \
  --output /absolute/new-joined
```

输入仅供 controller/evaluator，不能提供给方法。`--output` 必须尚不存在且不得写进研究计划或执行状态目录。工具不改写原始评审、标签、日志、费用或已封存输出。

## 2. 冻结标签文件

[quality-components.schema.json](schemas/quality-components.schema.json) 同时描述标签文件与每行运行评估的结构；运行时还有跨文件与字节校验。

| 字段 | 要求 |
|---|---|
| `schema_version` | 1。 |
| `data_kind` | `research` 或 `fixture`。fixture 只可与 development 计划配合。 |
| `frozen` / `frozen_at` | true、带时区时间；必须在被绑定研究计划冻结之后、第一条运行 reservation 之前。 |
| `study_freeze_sha256` | `experiment.digest(freeze.json)` 的 canonical JSON 摘要。 |
| `tasks` | 完整计划中的每个 task/project 恰好一项。不能挑选有利任务。 |

每个任务包含 `task_id`、`project_id`、`public_sha256_by_replicate`、`annotation` 和非空 `obligations`。public 摘要必须等于 schedule 中所有相应重复的公开输入。当前 v1 为每个任务使用一组双审材料，要求该材料的 public 树与所有重复的 public 树完全相同；若重复具有不同轨迹，应扩展为逐重复材料绑定并独立审阅，不能用新 task ID 把重复变成独立 N。

`annotation` 包含声明来源 `origin`、材料 `bundle` 相对目录、两个原始 review 文件的 `{path, sha256}`，以及 adjudication 的 `{path, sha256}`。路径均相对标签文件所在目录，不允许越界、symlink 或哈希变化。评分器重新调用 `annotation.validate_pair`，检查真实使用的两份记录、不同身份标识、材料、裁决与双审摘要。还要求审阅和裁决先于标签冻结、材料完整、设计接受且没有未解决缺口。**这些是提交记录的结构条件；程序不能据此证明真人身份、实际独立性或任务确已验收。**

`research` 要求 origin 声明为 `human`；`fixture` 要求 `fixture`。显式 `ai`、`model` 或其他来源不能被当作人工标注。即使把 AI 记录改写为 `human` 字符串也不会产生真实人类工作；代码无法认证这种谎报，审计明确保留 `human_identity_verified=false`，不能拿工具通过作为人工认证。

每项义务使用以下结构：

```json
{
  "obligation_id": "与已绑定裁决一致的实际义务ID",
  "requires_evidence": true,
  "behavior_check_ids": ["事先定义的行为检查ID"]
}
```

义务 ID 集合必须恰好等于裁决中的全部 `resolved_obligations`，每个任务至少存在一项冻结行为检查。描述、可回答性与预期行为保留在原始裁决中。`requires_evidence=false` 必须是事先冻结的实质设计决定；它不能在看到输出后免除缺证。

## 3. 运行评估 JSONL

每行绑定 `(task_id, project_id, arm, replicate)`，并携带 `run_id`、`freeze_sha256`、`sealed_run_sha256`、`output_sha256` 和标签文件的**原始字节** `labels_sha256`。这些字段可从 `experiment.py score-inputs` 的封存输出获得；脚本仍会从现有日志重新计算完整 output seal，不只相信传入字段。

来源字段为 `data_kind`、`judgment_origin`、`reviewer_id`、`reviewed_at`、`human_review_attestation`。research 的判断来源必须声明 human 且人工声明为 true；fixture 必须声明 fixture 且该人工声明为 false。评估时间不得早于完成收据。身份字符串和时间戳不是外部身份或时间认证。

`obligations` 必须逐项覆盖冻结义务，不多不少，每项包含：

| 字段 | 可用值与含义 |
|---|---|
| `obligation_id` | 冻结 ID。 |
| `decision` | `satisfied` / `unsatisfied` / `unmeasured`。 |
| `evidence` | 需证据时为 `supported` / `unsupported` / `unmeasured`；冻结规则不需证据时必须为 `not_required`。 |
| `incorrect_high_impact_affirmative` | true / false / null；null 为未评分。 |
| `unnecessary_abstention` | true / false / null；null 为未评分。 |
| `evidence_refs` | 封存输出内文件的 `{path, sha256, locator}`。已测判断至少一项；不限制成预定旧 source ID。 |

`behavior_checks` 恰好覆盖全部冻结检查 ID，每项包含 `check_id`、`status`（`passed` / `failed` / `unmeasured`）和相同格式的 `evidence_refs`。通过或失败须引用实际封存 trace/receipt。评分器验证引用字节与范围，不从退出码、文本措辞或检查名称自动推断测试执行与结论。

隐藏检查在执行后才产生的独立 evaluator 文件，当前合同不能直接纳入 sealed-run output：需要另行定义并审查其与原执行的封存绑定。不要为绕过这一边界事后向原 output 目录加入文件；这会使旧 seal 失效。当前支持对既有封存轨迹和实际收据的显式 evaluator 判断。

## 4. 复合终点与未知值

只有全部判断已完成、每个义务 satisfied、要求的证据 supported、没有错误高影响肯定、没有无谓弃答，且全部行为检查 passed，才输出 `decision_success=true`。有已测失败且其余判断齐全则为 false。

缺少整行评估、存在 `unmeasured` 或 null 时，复合结果保持 null，并列出具体缺项。即使其他已测项已失败，工具也先保留未闭合状态以完整记录测量缺口。`experiment.py join` 随后将 completed 执行的 null 评分标为 `evaluator_error`；原 ITT 分母仍在，但不能把该状态叫作实测方法失败。

非 completed 执行由现有首次尝试/ITT 规则处理，评分器不允许附上一份“成功”评估覆盖它。重复记录、未计划或未封存运行、错误 seal、错标签摘要、义务/行为 ID 漏项、证据越界和摘要不符均返回退出码 2。

## 5. 输出与审计

| 文件 | 内容 |
|---|---|
| `quality.jsonl` | 每个已封存 completed 执行一行，可直接交给 `experiment.py join`；保留 null、首次尝试及来源类型。 |
| `quality-components.jsonl` | 同一运行的行为、错误肯定、弃答、义务/检查数和缺项。 |
| `score-audit.json` | 文件与研究绑定、逐运行结果、实现摘要和身份/语义/冻结时间认证的明确边界。 |

Fixture 输出的 `completed_human_reviews=0`。Research 输出该数为 null，并仅给出 `declared_human_review_records` 记录数量；工具没有能力认证“多少真人已经完成”。所有类型均有 `research_task_accepted=false`，因为评分合同不承担任务验收或研究发表资格认证。
