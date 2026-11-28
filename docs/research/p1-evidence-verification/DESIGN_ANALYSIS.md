# P1 先导描述与资源设计分析

**当前新增的是离线工具，不是已完成先导或样本量论证。** 本工具调用现有 `analyze.py` 和 [报告合同](REPORTING.md)，从完整计划分母产生可复核描述；没有数据时诚实输出未测量。它不自动选择正式 N，不把 16 个来源候选当作 16 个先导任务。

## 1. 使用

```bash
python -B scripts/paper1/design_analysis.py \
  --manifest /absolute/pilot-plan/manifest.json \
  --runs /absolute/pilot-joined/runs.jsonl \
  --data-kind research \
  --output /absolute/new-design-analysis
```

可选 `--scenarios /absolute/assumptions.json` 加入**另行明确给出的假设资源网格**。输出目录必须尚不存在。输出为 `design-analysis.json`、`design-analysis.md` 和原分析器的 `analysis.json`，包含输入和实现摘要、Python/NumPy 版本、已有区间设置。

合成例子必须用 `--data-kind fixture`，首页显示 `FIXTURE ONLY — NOT PILOT EVIDENCE`。默认 unverified。`research` 仍只是输入声明，不证明标签、人类来源或任务验收。

## 2. 真实数据能提供的描述

| 内容 | 统计口径 |
|---|---|
| 采集与可行性 | 计划、收到、完整质量测量、缺失、失败状态及独立任务/项目数。 |
| 主要配对质量 | D−B、D−C 的任务平均差，任务差样本方差及项目均值样本方差。 |
| 配对 discordance | 任务均值的胜/平/负；另报相同 replicate 的四格结果，重复不扩大 N。 |
| 质量与成本依赖 | 全部配对任务成本完整且 N≥2 时才给出质量差/成本差的样本协方差。 |
| 资源 | 现有报告器的完整标准化成本、尝试时长、缺失计量数。 |

只要计划配对缺臂、存在未采集或未评分任务，主配对均值/方差/discordance 就保持 null；输出完整/计划数量和具体缺项，不悄悄挑选完成的有利子集。已测预定义方法失败仍按 ITT 为失败。单个任务不足以估计样本方差；项目均值方差也不等于 ICC、聚类区间覆盖保证或功效。

`real_pilot_estimates_available` 只对声明为 research、phase 为 pilot 且采集完整的数据开放。该字段不认证来源，也不表示样本量或模型假设已经充分。正式确认、development 或 fixture 不能被改称真实 pilot。

## 3. 假设资源网格

下面是**纯算术 fixture**，数字不是观测费率、预算授权或实际花费：

```json
{
  "schema_version": 1,
  "kind": "assumption_only",
  "scenarios": [
    {
      "name": "illustrative-fixture-only",
      "n_tasks": 16,
      "n_projects": 8,
      "replicates": 2,
      "arms": ["A", "B", "C", "D", "T"],
      "shared_prelude": true,
      "assumed_cost_per_continuation": 0.5,
      "assumed_cost_per_prelude": 2,
      "currency": "CNY",
      "assumption_source": "Synthetic arithmetic example; no measured prices or approved budget."
    }
  ]
}
```

该例只会算出 160 次 continuation、32 次共享 prelude 和 CNY 144 的假设总额。费用参数未知写 null，输出总额也保持 null。若 prelude 不共享，次数随各臂重复增加。增加 T 或重复次数会增加执行数，不增加独立任务 N。

这些情景不会读取云账户，不会申请预算、调度服务或冻结正式样本。`kind` 必须为 `assumption_only`；项目数不能超过任务数，计数须为正整数，成本须为有限非负数或 null，币种与假设来源须显式提供。

## 4. 尚未声称完成的设计工作

本工具明确输出 `formal_sample_size=null`、`sample_size_recommendation_made=false`、`power_simulation_performed=false`、`simulation_seed=null`、`monte_carlo_standard_error=null`。后两个 null 表示没有运行 Monte Carlo，不能写成 MC 误差为零。

H1 的 5/8/12 个百分点情景、H2 的 3% 界限及质量/成本联合拒绝概率，需要有依据的生成模型、项目和任务依赖假设、拟用区间程序、失败机制、模拟次数和 MC 精度目标。当前没有真实 P1 先导数据，所以没有拟合或执行这些功效模拟；假设资源表不替代它们。未来若新增模拟入口，须保存全部参数、种子、软件版本、Monte Carlo 标准误/区间，并区分纯假设情景与先导估计，不应自动选取有利 N。

正式 N、非劣界限的实质理由、停收规则和确认性分析仍须在正式结果解封前由真实研究设计完成。`min_tasks`、`min_projects` 和 bootstrap 次数只是现有分析器的明确操作设置，不是自动样本量依据。
