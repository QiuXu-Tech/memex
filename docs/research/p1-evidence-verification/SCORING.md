# P1 封存运行的 evaluator 评分合同

**评分器聚合显式判断，不自动生成标签或执行隐藏测试。** 当前仓库没有由此产生的真实 P1 人工评分。所有新增测试均为清楚标记的 fixture，零个人工评审、零个研究样本。

## Development 的新增程序路径：v2

本页其余部分描述已有 `score.py` 的 **human-v1 / fixture-v1 完整复合评分合同**，其中“两份真人审阅加裁决”是该版本的输入类型要求，不是所有开发运行必须先满足的条件。用户授权尽量采用可靠的自动核验后，现另有 [development-assurance v2](ANNOTATION_V2.md)：11 包程序预审、37 条 AI-assisted 义务草案，以及 `development_oracle.py` 的封存轨迹部分检查。原人工来源检查没有被改成信任 `ai_assisted` 字符串，也没有伪造任何人名或签署。

`development_oracle.py` 复用 `experiment.py` 的首次尝试账本与完整 output seal，重新调用 `python_workflow.summarize` 核验原始 observer 收据、nonce、测试 phase、代码快照及实际测试数。它可以报告当前公开测试是否通过、local review 是否引用有效的当前测试；**隐藏请求行为、证据语义和完整决策成功仍为 null**，不会生成可误送入 join 的 `quality.jsonl`。完整任务尚无记录时输出 NOT_MEASURED，不将未运行判成实测失败。

```bash
python -B scripts/paper1/development_oracle.py \
  --plan /absolute/frozen-development-plan \
  --state /absolute/original-experiment-state \
  --output /absolute/new-development-oracle-report
```

该入口只读已有封存数据，不执行任务或隐藏程序，不补建运行记录，不写原账本；拒绝 pilot、confirmatory 和 external 研究计划。直接由 `development_driver.py` 保留的原生开发输出尚未经过 `experiment.py` 的 seal 时，不得伪造一个 study/ledger 供此命令接受。可先保留原始开发收据，按未来明确的 evaluator 绑定合同另作审查。原 v1 文档已保存为 [历史副本](artifacts/remaining-completion-01/assisted-review-v2/history/SCORING.md)。

如果正式研究最终选择程序 oracle 或 AI 辅助标签，应在正式数据收集前明确更换标签版本，验证独立真值依据、未覆盖语义、等价证据与误差，再扩展完整评分合同；不得把 development 的部分检查当作已经验证的新正式终点。

后续已实际完成 [两来源行为 oracle 的独立隔离资格验证](artifacts/remaining-completion-01/oracle-qualification-01/README.md)：Flask 原版与 Requests 明确 URL 范围的 v2 各 5 个 pytest 用例能区分已知 base、fixed 和错误实现；空测试、缺源码与依赖目录同名包不能产生通过。Requests 原六项版本在 fixed 上的一项失败仍保留。此工作只运行独立参考源码，15 个 observer / 5 个 sandbox probe，不读取方法最终制品，不产生 `quality.jsonl`，也不改变本合同的 `decision_success`、人工数或任务验收状态；十个行为用例不是十个人工 gold 标签。

## 1. 流水线与边界

在选择 human-v1 路线时，先用现有 `annotation.py` 形成真实双审与裁决，再冻结义务和检查清单；方法执行由 `experiment.py` 封存；人类 evaluator 审查具体输出及行为收据；最后 `score.py` 聚合，供现有 `experiment.py join` 使用。完整费用仍由 join 计算。

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
