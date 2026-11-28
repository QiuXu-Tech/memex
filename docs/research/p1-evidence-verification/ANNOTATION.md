# P1 标注方法与原独立双审流程

**方法更新：development-assurance v2 已实施，真人标注仍为 0。** 在用户要求尽量由 AI 完成可可靠代劳的工作后，现已完成 11 个原任务包的程序审阅、37 条明确标为 AI-assisted 的义务草案，并核对原 22 份 review 模板及 11 份裁决模板仍为空。实际结果见 [v2 审阅报告](artifacts/remaining-completion-01/assisted-review-v2/programmatic/report.md)，方法、可执行 oracle 与剩余边界见 [ANNOTATION_V2.md](ANNOTATION_V2.md)。这些成果不冒充独立真人，也没有把合成材料或未测方法输出改为研究结果。

**22 份真人表不是 development 运行的前置条件。** “每个物理包两位独立真人加第三位逐包裁决”是旧 v1 选择的一条标签验证路线，不是 TMLR 规定的标注人数。可确定的源码、版本、完整性、测试完成和证据绑定由程序核验；语义义务可先由 AI 明示起草。正式研究仍须在方法输出用于验证前确定标签路线、验证覆盖和误差、冻结版本与适用范围；不能把方法自己的候选或回答当作真值。

下文完整保留 **human-v1 路线** 的操作要求，仅适用于选择这条路线的记录。`annotation.py` 的真实人工声明与独立双审合同没有被放宽，AI 记录不得填入其中。旧页字节已保存在 [v1 历史副本](artifacts/remaining-completion-01/assisted-review-v2/history/ANNOTATION.md)。作者资格与最终责任是另一类事实，不能用自动标签或填写 22 张表替代；官方政策范围见 [v2 政策核对](ANNOTATION_V2.md#6-官方政策与作者责任)。

本流程用于在方法输出解封前独立确定任务义务、状态与行为检查。它不承担论文作者身份或研究贡献的认证。任务来源、真实/模拟成分和剩余工作见 [TASKPACKS.md](TASKPACKS.md)；完整研究要求见 [PROTOCOL.md](PROTOCOL.md)。

## 1. 三个操作角色

| 角色 | 可见材料 | 工作与限制 |
|---|---|---|
| 分配负责人 | controller mapping、来源资格及各 packet 的完整性摘要 | 指派两名具备能力且相互独立的真实评估者；只分发各自 packet；保存独立性/盲法执行证据。 |
| Reviewer 1 / Reviewer 2 | 各自的 `packet.json`、`material/`、空白模板与说明 | 独立读自然请求和可观察材料，提出义务、证据定位、可回答性及缺口；看不到对方标签、方法臂输出或 evaluator 草案。 |
| 第三位裁决者 | 两份已经封存的完整审阅、相同材料、裁决模板 | 对每处不同判断解释裁决；形成最终义务与剩余缺口；不能悄悄修改原始审阅。 |

当前目录中的 `review-…` 是自动生成的 **packet 编号**，不是人类身份。开发模板使用确定性的 assignment seed 方便复核；这不证明真实随机分配或评估者互不沟通。实际开始人工标注时，应创建新的分配记录，在方法输出尚未开放时独立分发，并由负责人验证参与者、完成时间、未看过隐藏答案/未来 fix 和未看过方法输出。

整个研究仓库包含 evaluator 材料，不能让 reviewer 浏览仓库根再宣称其盲法成立。应只交付一个经过校验的 packet；public 源码可能识别项目，盲法的目标是隐藏方法身份、输出及预设答案，而不是假称开源项目匿名或未见过。已经接触答案、同行审阅或方法输出的人必须如实记录，不能填 false 消除接触事实。

## 2. 已生成的模板结构

每个任务的目录为 `tasks/workflows/annotation/<task_id>/`：

```text
controller/mapping.json
controller/adjudication-template.json
reviewers/review-…/packet.json
reviewers/review-…/review-template.json
reviewers/review-…/INSTRUCTIONS.md
reviewers/review-…/material/
```

每个 packet 的 `material/` 是同一 public 树的普通文件复制，保留路径、文件权限、字节数和 SHA-256；不靠 symlink/hardlink 指回包含 evaluator 的包。`packet.json` 中 `method_arm=null`、`method_outputs=null`、`evaluator_answers_provided=false`。控制器映射和 evaluator 的 `proposed_obligations` 没有被复制给 reviewer。

来源包的 material 含 base 源码与自然请求，尚无真实 P1 native trajectory；合成包的 archive 明确自称 fixture。评估者应将材料不足作为真实发现。`insufficient_material` 或 `revise_design` 是正常结论，不能为了推进研究而把不存在的前置过程或行动写成已观察。

## 3. 审阅记录要表达什么

`review-template.json` 中需要真实评估者填写以下内容，现有值均为 null：

| 字段 | 含义与验证边界 |
|---|---|
| `reviewer_id`、`reviewed_at` | 负责人可核对的真实身份标识和带时区时间；不得用 LLM 或程序生成的人名冒充完成。 |
| `human_review_attestation` | 真实人工完成审阅的声明；程序只检查布尔值，不能认证其真实性。 |
| `independence_attestation` | 未借助另一份审阅形成此记录；负责人仍需验证独立过程。 |
| `method_outputs_seen` | 本阶段须为 false；若已经看过，应如实记录并另行处理盲法破坏。 |
| `decision` | `accept_design`、`revise_design` 或 `insufficient_material`；接受设计不等于接受完整 P1 任务。 |
| `material_completeness` | `complete_workflow` 或 `incomplete_workflow`；后者必须说明缺口。 |
| `critical_obligations` | 非空义务列表；不能只给“通过”二字或使用方法抽取出的候选作为完整分母。 |
| `gaps` | 未观察到、冲突、不可重建或需补足的材料。 |

每条义务含 `obligation_id`、`kind`、`description`、`expected_behavior`、`answerability` 和至少一条 `evidence`。类型包括 test、version、authorization、artifact、other；可回答性分别标明从现有材料可判、需新观察、冲突或未知。

每个证据引用必须给出 packet `material/` 内相对路径、该文件 SHA-256 和可用 span/locator。程序验证路径未越界、文件未变化、摘要一致和字段完整，**不会自动验证所引片段是否语义上支持结论**。版本是否真正当前、授权主体是否合法、适用生命周期是否完整，以及可接受证据集合是否遗漏，都仍需合格人工复核。

两份独立审阅应先封存，再交裁决者。不要把第二份审阅从第一份复制后换名字。大小写和空白规范化后相同的 reviewer ID 会被拒绝；不同字符串并不能证明是两个人，别名、串通或同一模型生成两份记录都需负责人识别。

## 4. 裁决绑定与分歧保留

所有双审记录都必须有第三位裁决者的显式记录，即使初步判断一致。`adjudication-template.json` 需要绑定原材料 SHA-256 和两份审阅的完整 canonical JSON SHA-256，并填写裁决人、时间、人工声明、理由、最终义务与剩余缺口。

如果两份审阅在 decision、材料完整性、义务或缺口上有差异，`resolution` 必须是 `resolved_disagreement`。当前比较按结构内容严格判断，措辞或列表顺序差异也可能触发裁决；这是保守的程序规则，不是自动语义一致性估计。完全相同的判断可以写 `confirmed_agreement`，但仍需裁决理由。

任何原始审阅在裁决后发生修改，旧的审阅摘要绑定都会失效，必须重新裁决。裁决人不能复用两位 reviewer 的规范化身份标识。`resolved_obligations` 的证据仍须引用相同 public material，不能在裁决时偷偷注入未来 fix 或方法成绩作为依据。

裁决输出可以是 revise/insufficient，工具不将其转成通过分数。即使填写 `accept_design`，程序返回 `research_task_accepted=false`、`frozen=false`；完整工作流验收及标签冻结是独立步骤，需要真实轨迹和行为检查支持。

## 5. 工具命令

从仓库根生成新的两个 packet；输出目录必须尚不存在：

```bash
python -B scripts/paper1/annotation.py prepare \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101 \
  --output /absolute/new/path/w-101-review-assignment \
  --assignment-seed actual-assignment-identifier-chosen-before-review
```

该命令只准备材料，输出 `completed_human_reviews=0`。不得从命令成功推断有人完成审阅。真实评估者返回自己的 review JSON 后，运行：

```bash
python -B scripts/paper1/annotation.py validate-review \
  --packet /absolute/path/assignment/reviewers/review-actual-packet-id \
  --review /absolute/path/returned-human-review.json
```

按 `controller/mapping.json` 中的两个 slot 顺序审查双审与裁决：

```bash
python -B scripts/paper1/annotation.py validate-pair \
  --bundle /absolute/path/assignment \
  --review /absolute/path/returned-review-slot-1.json \
  --review /absolute/path/returned-review-slot-2.json \
  --adjudication /absolute/path/returned-adjudication.json
```

空白模板、重复身份、材料被改动、引用越界、证据摘要不符、缺失裁决、错误审阅摘要、裁决者重复或未解决分歧都会返回退出码 2。把未填模板直接送入 `validate-review`，预期为 `review_incomplete`，这是正确的阻断结果。

结构检查成功返回 `structurally_complete=true` 和两条审阅记录的摘要；仍明确 `human_identity_verified=false`、`method_blinding_independently_verified=false`。CLI 没有“自动批准任务”或“自动生成人工标签”的开关。

## 6. 正式使用前的人工与研究验收

负责人需要保存真实身份与能力、独立分配、盲法过程、两份原始审阅、每处裁决和最终标签的不可变记录。最终义务应覆盖成功所需的所有关键行为，容许等价有效证据和新运行产生的有效证据；不能只承认指定旧 source ID，也不能让空候选绕过分母。

当前两来源包还需真实 native prelude、相关状态变化、原生 compaction、后续动作及隐藏行为检查；八个合成家族仍不能成为真实 pilot 来源。完成材料、审阅记录和代码结构校验，只是接下来可以认真验收的基础。

开发包的确定性模板与本测试中的 `human-1` 等合成身份都不能进入真实标注台账。正式收集开始后，任务版本或 public 字节一旦改变，应生成新材料摘要并重新审阅；不能沿用旧标签声称其适用于新任务。
