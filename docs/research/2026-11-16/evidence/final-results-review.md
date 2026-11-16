# 公开 RESULTS 最终复核

结论：数值与统计口径核对通过；按本次明确的“公开文件无机器绝对路径”要求，有 **1 项发布前必修**。本报告绑定 RESULTS SHA-256 `d5396b4e849beac03aed0c3b4f6bb8ffbbe59fd7b9d5f1a693116be494c78ade`、更新后 final-validation SHA-256 `42bcc9642f0b3a509b4f7b98edbe791685ce94650062965654c0a73be0881aa1`。若文件继续修改，须核对最终版本。

## 必修

`RESULTS.md` 第 58 行复现命令的 `--out /tmp/memex-benchmark.json` 使用绝对路径。它是通用临时目录，并非发现的用户私密信息，但不符合本次“无机器绝对路径”的明确要求。请改为合适的相对输出路径，保证不覆盖既有证据；变更后重核文档哈希。

## 已核对

- 三轮 7 场景全部 21 个配对速度比中位数、最终 7 行 baseline/candidate 中位数、配对差、配对中位数 bootstrap 区间、CPU 几何平均和 pooled p95 均与公开原始 JSON 按表内精度一致。最终 wide 为 11.563×；small 为 -0.1598ms，阈值 0.200ms。区间和 p95 已限定为合成数据的描述性结果；三轮为各自相对 foundation，不是相邻轮次配对增量。
- worker 整体 peak RSS 与 1 分钟 load 的中位数及范围均从原始 records 重算一致，且文中没有把整体峰值归于单一 workload。
- 更新后的公开 final-validation.json 含命令、版本、实际数量和退出码；与保留的原始 receipt 比较，原记录字段未改，18 个本地日志的 SHA-256 均吻合。两种 Node 的 196、38、50、43、36 数量与日志相符；recall 为 synthetic、threshold 0.9，scale 为 1,000。公开 evidence 当前不包含这些最终验证日志本身，receipt 提供其哈希，完整日志保留本地；因此公开读者可见回执但无法仅凭公开文件独立重算日志摘要。
- 当前 repo 的 17 个 core 文件与 R3 测量快照及提交 `5fda3fbc764ffa914bb6c755a5adb6dcc77c94a6` 的已核对哈希一致。没有重跑基准或最终测试。
- 对整个公开 research 目录做了用户 home 路径及常见凭据格式的定向扫描，未发现匹配；此扫描不是对一切私密信息的穷尽证明。文中说明 AI 独立工程复核并非人类盲评，合成结果不证明真实任务、生产、账单或客户端验收。
