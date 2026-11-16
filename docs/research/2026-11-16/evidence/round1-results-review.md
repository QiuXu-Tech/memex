# R1 基准结果独立复核

结论：**在预注册的合成本地基准范围内，R1 达成排序目标，小窗口回退护栏通过；未发现需要阻止 R2 的问题。** 这不是生产收益或真实任务效果证明。实现与语义审查详见 `round1-review.md`。

## 原始证据核对

- `round1-benchmark.json` SHA-256 `a2bfaa3511d311af30e4503229d0bf7a9602626250cb726d6d6fd226e77a9e87`；20 个进程均正常退出，其 stdout 与结构化记录一致。7 场景 × 10 配对，逐一核对 fixture 和输出哈希以及两侧合计 420 个测量样本的输出哈希。哈希相等是这些样本的证据，不等于所有输入语义皆正确。
- baseline 和 candidate 各 17 个 core 文件，运行前后哈希一致，并分别与冻结目录及 Git 提交 `c3fa508e`、`6c460d7f` 逐文件一致；登记的协议、脚本、fixture 三文件与候选提交匹配。未重跑计时。
- 从每个 worker 的三次 wall 时间重算中位数，逐对计算 baseline/candidate，再取十对中位数；与结果文件的 `pairedMedianSpeedup` 和 `pairedMedianDeltaMs` 均一致。

| 合成场景 | 配对速度比中位数 | 配对时间差中位数（候选减基线，ms） |
|---|---:|---:|
| order-singletons | 61.049× | -125.169 |
| order-streams | 5.075× | -5.191 |
| materialize-wide | 4.032× | -196.354 |
| materialize-tight | 1.360× | -7.386 |
| materialize-small | 1.558× | -0.104 |
| materialize-custom | 1.061× | -0.367 |
| materialize-tools | 1.203× | -5.434 |

singleton 排序的配对时间相对变化中位数为 -98.36%，满足预注册至少降低 25% 的 R1 目标。small 场景配对时间差中位数 -0.104 ms，满足最多增加 0.2 ms 的护栏。wide 的 4.032× 是当前合成场景观察值；最终累计 ≥2× 仍需最终版本重新评估。各场景均应保留，不能只引用最优项。

## 统计与限制

- 五个固定合成 seed，每个 seed 两对进程，每进程每场景预热一次、计时三次；运行时 Node v25.9.0，macOS arm64。独立语义测试运行时 Node v24.22.1，二者不是同一次运行。样本数有限，重复调用并非独立真实任务；分层 bootstrap 区间仅作描述，pooled p95 也不是生产尾延迟保证。
- `round1-benchmark.log` 将 `speedupGeomean` 与 `speedup95CI` 相邻打印，但脚本中的区间是对 **配对中位速度比** 的 bootstrap，而非几何均值的区间。汇报须以 JSON 的 `pairedMedianSpeedup` 为主要指标，并明确区间对应指标，避免误读日志。
- CPU 和 RSS 可从原始 JSON 查看；RSS 为整个 worker 峰值，不能归属于单场景。没有模型调用、真实客户端、生产负载、账单或任务质量证据。原始盲评、事后补评和历史回放均未因此改变。
