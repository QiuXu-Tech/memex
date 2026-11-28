# P1 可复算报告

**这是离线报告工具，不是新增研究结果。** `report.py` 直接调用现有 `analyze.py`，保留完整计划分母及其 ITT 审计；不调用模型、不调度方法臂、不补写真人评分、不重新编造费用。费用应由 `experiment.py join` 从已冻结计量合同产生。

## 1. 入口与输出

从仓库根执行；`--output` 必须尚不存在：

```bash
python -B scripts/paper1/report.py \
  --manifest /absolute/frozen-plan/manifest.json \
  --runs /absolute/joined/runs.jsonl \
  --data-kind research \
  --output /absolute/new-report
```

`--data-kind` 为 `research`、`fixture` 或默认的 `unverified`。这是输入来源声明，不认证材料确为真实研究。合成测试必须使用 `fixture`；其 Markdown 首页明确 `FIXTURE ONLY — NOT STUDY RESULTS`。输出不会自行把任何输入升级为可发表科学主张。

| 文件 | 用途 |
|---|---|
| `analysis.json` | 原分析器的完整输出，含 ITT 零值、计划/缺失分母、数据异常、区间设置和 H1/H2 条件判定。 |
| `summary.json` | 区分测量状态、各臂数量、可报告的任务平均、成本、延迟、评分组件和限制。 |
| `report.md` | 可读表格；未测量的单元格显示 `NOT MEASURED`。 |
| `arms.csv` | 便于复核的各臂平面表；未测量值为空，不补零。 |
| `provenance.json` | 输入原始字节摘要、实际实现摘要、Python/NumPy 版本；不是外部时间戳认证。 |

同一路径已有结果时返回退出码 2，不覆盖。不同版本应写到新目录。此工具不修改 `manuscript.md`、PDF 或旧运行记录。

## 2. 未测量、方法失败与 ITT

`missing`、`not_dispatched`、`running`、`capture_incomplete`、`evaluator_error` 和不可读质量记录是尚未闭合的质量测量。整个计划尚无测量时，报告不把分析器为 ITT 保留的零值称为实测 0% 成功率；相关论文格和配对估计保持 null。

一个臂的计划记录尚有此类缺项时，其表格成功率保持 null；涉及不完整臂的配对质量/成本表也保持 null。`analysis.json` 仍完整保留原有 ITT 数值，`itt_policy_task_mean` 明确用于审计，不能脱离不完整状态用于效果主张。无法定位的 JSONL 行保留在 `input_issues`，不会从计划分母删除。

已真实结束的预定义方法失败，例如 `host_timeout`、`provider_error` 或 `model_invalid_output`，仍是计划内 ITT 失败。它们不因结果不利被删除，也不被报告器改成未调度。损坏或未知成本只影响成本格，不会改变有效质量分数。重复或未计划运行仍由现有分析器拒绝。

## 3. 表格口径

任务成功率先平均该任务的全部计划重复，再平均任务；重复、声明和日志行不增加独立 N。完整标准化成本沿用相同任务汇总，任一计划成本未知则对应完整成本汇总未知。报告不将实际账单、部分组件估价或现金预留当作 `C_std`。

延迟统计读取实际记录的有限非负 `elapsed_seconds`，以 NumPy `linear` 分位数计算 p50/p95，同时报告观察数、缺失数和超时/预算停止数量。它描述**已观察尝试的时长，包括超时**，不是成功任务的完成时延分布；不把中止时长当作未观察到的最终完成时间，也不补齐缺失时长。

行为成功、错误高影响肯定和无谓弃答只有在提供绑定的评分制品时才报告：

```bash
python -B scripts/paper1/report.py \
  --manifest /absolute/frozen-plan/manifest.json \
  --runs /absolute/joined/runs.jsonl \
  --score-dir /absolute/scored \
  --data-kind research \
  --output /absolute/new-report-with-components
```

`--score-dir` 为 [SCORING.md](SCORING.md) 的输出目录。报告核对 `score-audit.json` 中的 manifest/组件文件摘要、数据类型、每条运行键、run ID 和质量结果；文件变化或串错运行即拒绝。各组件显示已评分运行数、计划数、缺失数和仅已评分部分的比例。这个比例不是完整任务级因果效应，不直接代替论文表 4a 的任务级终点。

论文表 6 的候选召回、源发现、完整生命周期、复用机会与交付等机制指标需要各自独立分母和事件合同，当前工具不从总失败或检索次数推断这些数字。它们明确保持 `not_measured_by_this_contract`。

## 4. 复核范围

新增测试使用合成输入，覆盖未运行、部分缺失、未知成本、超时、重复记录、不可解析记录及评分制品绑定。另有真实离线 fixture runner 的 `score → experiment.join → report` 测试；它只写本地 fixture 文件，绝不计入论文任务或人工评审。运行：

```bash
python -B -m unittest discover -s test -p 'test_paper1_report.py' -v
python -B -m unittest discover -s test -p 'test_paper1_score.py' -v
```

报告器不认证人类身份、义务语义、研究任务验收或真实预注册。`scientific_effect_claims_allowed=false` 表示本工具没有独立授予研究主张资格；真实结果仍应结合协议、原始材料和独立审查解释。
