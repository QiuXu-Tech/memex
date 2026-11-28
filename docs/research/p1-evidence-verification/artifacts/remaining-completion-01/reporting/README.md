# 当前零结果的离线报告

**NOT MEASURED — NOT READY — NOT SUBMITTED。** 本目录使用实际仓库状态生成报告；没有新增实验、模型请求、人工标注、费用核销或功效模拟。它不是一个测得成功率为 0% 的实验。

## 输入与分母

`manifest.json` 使用研究 schema 明确允许的空开发清单：`study_phase=development`、`frozen=false`、`runs=[]`；`runs.jsonl` 为 0 字节。这里的空清单表达当前 **0 个已验收/冻结研究任务、0 次正式方法运行、0 条研究结果**。输入声明为 `unverified`，不声称已完成独立的研究来源认证。

这不删除或取消既有的开发计划。现有 16 个已准备的双来源开发单元仍为 `prepared_not_dispatched`，80 单元材料结构草案仍未冻结；二者都不是已验收的研究清单。本报告没有把 16 个来源候选、12 个合格来源环境、11 个未验收材料包、22 份空白双审材料、宿主 smoke 或固定合成输入的 DeepSeek 诊断提升为研究任务。既有两次原生额度已消耗，另有一次真实生成诊断，这些事实与论文结果未测量并不矛盾。

[status.json](status.json) 保留上述状态及 8 个来源文件的 SHA-256。它读取已公开的最新台账快照，不写现金账本，也不把 CNY 97 的剩余预留容量解释成账户余额或可运行完整实验的成本证明。实际扣款与完整研究标准化成本均保持 null。

## 输出

| 入口 | 产物与当前结论 |
|---|---|
| [report/report.md](report/report.md) | D−B、D−C 的质量、成本和区间均为 `NOT MEASURED`；没有人为补造 A/B/C/D 运行行。 |
| [report/summary.json](report/summary.json) | 计划/收到研究记录均为 0，科学效果主张权限为 false。 |
| [report/analysis.json](report/analysis.json) | 直接保留现有分析器的空分母审计，H1/H2 不可确认。 |
| [design-analysis/design-analysis.md](design-analysis/design-analysis.md) | 配对均值、方差与先导估计均未测量；未选择正式 N，未运行功效模拟。 |
| [design-analysis/design-analysis.json](design-analysis/design-analysis.json) | `formal_sample_size=null`、`power_simulation_performed=false`；没有假设情景、MC 样本、种子或误差为零的说法。 |

没有调用评分工具，因为尚不存在已冻结的真人标签、裁决与封存执行记录。该缺口由事实决定，不能通过生成 AI 标签关闭。[SCORING.md](../../../SCORING.md) 记录后续真实材料的评分合同。

## 实际生成命令

从仓库根执行的命令如下。输出目录必须尚不存在；复算时将两个 `--output` 改为新的路径，既有产物不会被覆盖。

```bash
python -B scripts/paper1/report.py \
  --manifest docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/manifest.json \
  --runs docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/runs.jsonl \
  --data-kind unverified \
  --output docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/report

python -B scripts/paper1/design_analysis.py \
  --manifest docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/manifest.json \
  --runs docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/runs.jsonl \
  --data-kind unverified \
  --output docs/research/p1-evidence-verification/artifacts/remaining-completion-01/reporting/design-analysis
```

两条命令均退出 0，报告 `measurement_status=unmeasured`、`model_requests=0`。退出 0 只表示报告程序成功处理这些空输入；它不表示先导已运行、方法成功或论文科学就绪。输入与脚本摘要、Python/NumPy 版本分别保留在 [report/provenance.json](report/provenance.json) 和设计分析 JSON 中。

完整用法及统计限制见 [REPORTING.md](../../../REPORTING.md) 与 [DESIGN_ANALYSIS.md](../../../DESIGN_ANALYSIS.md)。
