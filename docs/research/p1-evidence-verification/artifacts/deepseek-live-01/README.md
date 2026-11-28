# DeepSeek 真实接入诊断 01

观测时间：2026-11-28 18:05:49（Asia/Shanghai；UTC 为 10:05:49）。

**结论：一次真实 `deepseek-flash` 候选抽取请求成功返回，并通过已有 JSON、类型及原文依据检查。** 输入是公开、固定的合成例子；本记录验证有限接入路径，不计入论文方法单元、正式样本或原生压缩试验。

## 实际观测

| 项目 | 结果 |
|---|---|
| 生成请求 / 自动重试 | 1 / 0 |
| HTTP 状态 | 200 |
| 请求 / 返回模型名 | `deepseek-flash` / `deepseek-flash` |
| 本次前置只读检查 | 1 次；账户资料不公开 |
| 输入 / 缓存输入 / 输出 tokens | 434 / 0 / 210；缓存输入是输入子集 |
| 总 tokens | 644 |
| 有效候选 claim | 1 条 `operation_authorization` |
| 输出上限 | 1,024 tokens |
| 标准化高峰费用估计 | CNY 0.00254800 |
| 实际新增扣款 | 未知，保留 `null` |
| 仍持有的现金预留 | CNY 3.00 |
| 原生压缩 / 研究样本 | 均为 false |

实际运行使用已公开提交 `396c7e12bfe007371caa7131c743837d1b157ee3` 中的诊断与 transport 源码及配置。部署前核对安装文件摘要；运行环境为 Node v25.9.0、Python 3.14.3。只有指定设备副本可执行真实请求，发布和测试 checkout 不作为并行调度器；实现不提供跨设备分布式互斥。

调用记录的 1,388 ms 包含准入及台账处理，不含前置账户检查，不能解释为纯服务推理延迟或速度基准。

## 固定输入与实际候选

输入来自仓库中的 [deepseek-diagnostic-config.json](../../../../../scripts/paper1/deepseek-diagnostic-config.json)。draft 为：

> The maintainer approved publishing release c1 in project demo.

上下文明示这是合成 API 兼容性诊断，不执行发布或任何其他操作。结果将 maintainer 对 project demo / release c1 的发布批准提取为待核验候选；原文引用完整匹配 draft，并明确草稿可能错误、撤销、过时或缺少支持，角色尚无具体身份，当前上下文不允许执行发布。

该候选在语义上对应输入中的授权主张，但本次没有真实来源绑定、当前授权证据或人工标签。因此不能从格式与引用检查推出真实授权成立，也不能据此估计准确率、召回率或完整义务覆盖率。

实际 `unresolved` 还额外写出缺少 `test_result` 证据，而这个输入没有要求测试。这一多余提示如实保留在结果中。单条合成例子既不足以测量该问题的频率，也不提供方法效果估计。

## 请求与台账核对

[请求审计](request-audit.json)根据公开代码和固定输入重建请求及准入 intent，核对请求、输入、诊断配置与实际 transport 配置摘要。它同时复核 claim 类型、原文引用、一次生成、零重试及供应商用量一致性。审计没有再次调用服务。

原 [canonical journal](../authorized-batch1/ledger/events.jsonl) 的 4 条历史事件保持字节一致；这次追加 3 条：

1. `reserved`：在同一批次 CNY 100 总额度内预留 CNY 3.00。
2. `operation_reserved`：绑定本次唯一 dispatch、请求及配置，记录一次 `provider_request`。
3. `finished`：本次诊断完成，实际扣款未知，保留现金预留。

[台账审计](ledger-audit.json)已重算全部 7 条事件的哈希链，核对历史字节前缀、请求/价格绑定与唯一操作。[状态快照](ledger-status.json)直接由 Python 台账 CLI 生成，保留纳秒整数精度。

| 批次额度 | 当前状态 |
|---|---|
| native 尝试 | 2 次已用，剩余 0 |
| 方法单元 | 0 个已用，剩余 16 |
| 独立诊断 | 1 次 |
| 新增现金上限 | CNY 100.00 |
| 当前占用预留 | CNY 3.00 |
| 账面剩余预留容量 | CNY 97.00 |
| 实际新增现金总额 | 未知；包括历史原生尝试的未核销项 |

剩余预留容量不是供应商账户余额，也不证明历史尝试免费。原授权摘要保持不变。

通用 transport 记录仍带有 `canonical_cash_ledger_integrated: false`：该组件自身不认证调用方是否真正接上 canonical ledger。这次接入证明来自外层诊断 controller 的预留与完成记录，以及真实台账中的绑定事件；没有为美化结果改写通用组件字段。

## 费用口径

核查日的 [DeepSeek 官方中文价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)列出每百万 tokens 的高峰费率：未缓存输入 CNY 2.00、缓存输入 CNY 0.04、输出 CNY 8.00。按本次用量作统一高峰口径计算：

`434 × 2 / 1,000,000 + 210 × 8 / 1,000,000 = CNY 0.00254800`。

这是标准化估计；服务方的非高峰规则、余额扣减与结算回执没有在这里核销，实际费用仍为未知。CNY 3.00 是发送前按完整文档上下文上限向上预留的保守现金上界，不是这次的用量估计或实际花费。不能用估计值释放未知费用的预留。

## 公开范围与复核限制

| 文件 | 内容 |
|---|---|
| [result-public.json](result-public.json) | 选择性脱敏的实际结果、解析后候选、用量及 controller 记录 |
| [request-audit.json](request-audit.json) | 请求、配置、候选及用量复核结果 |
| [ledger-audit.json](ledger-audit.json) | 历史前缀、追加事件、配额及现金绑定复核结果 |
| [ledger-status.json](ledger-status.json) | 运行结束后的完整批次状态快照 |

公开结果移除了账户可用性与余额，供应商 completion ID 只保留 SHA-256；不含 API Key 或私有设备路径。公开包保留解析后的输出与其原文本摘要，没有提供逐字节原始 provider 文本，因此不声称外部读者可从本包独立重现原始文本解析。已保留的 controller 事件和本地审计也不是服务方签名的账单或模型权重认证。

## 对论文进度的影响

这次补齐了 DeepSeek 真实生成与候选校验的接入证据。它不解除原生压缩 checkpoint、同一 reader/tokenizer、B 臂固定检索服务、完整费用采集、真人标签与裁决、正式配对实验等剩余条件。16 个方法单元仍未运行，文稿及正式结果未因这次诊断改写，论文仍为 **NOT READY / NOT SUBMITTED**。

完整接入合同见 [DEEPSEEK.md](../../DEEPSEEK.md)，论文状态见 [COMPLETION.md](../../COMPLETION.md)。
