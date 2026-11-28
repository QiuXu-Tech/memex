# P1 剩余工作执行记录

更新：2026-11-28（Asia/Shanghai）。用户要求：**“把剩下的全部做完”**。

本轮完成第一篇论文尚可独立推进的运行实现、分析工具、环境准备与交付核验。论文仍是 **When to Reopen the Source: Evidence Verification after Native Agent Compaction** 的方法与实验协议工作稿。当前已验收研究任务、正式方法结果和已完成真人评审均为 **0**；没有新增模型调用，没有提交论文。

## 已完成的工作

| 工作 | 本轮完成内容 | 证据入口 |
|---|---|---|
| 配对运行 | 原计划的显式路径迁移收据；父状态及完整检查点封存；同父分叉；每臂独立公共副本；失败用量保留 | [PAIRED_RUNTIME.md](PAIRED_RUNTIME.md) |
| 接入原实验调度 | 同一存活 backend/helper 按冻结顺序逐单元运行，沿用原首次尝试、用量收集、结果封存和 join；实现摘要和检查点绑定发生变化即拒绝 | [PAIRED_DISPATCH.md](PAIRED_DISPATCH.md) |
| 原生宿主与共同 reader | Codex 0.153.0 的实际 RPC；DeepSeek 固定 profile 与官方 tokenizer；实际 thread/read、resume、fork lineage 检查；受限公共工具与真实版本观察 | [NATIVE_BACKEND.md](NATIVE_BACKEND.md)、[NATIVE_DRIVER.md](NATIVE_DRIVER.md) |
| C/D 证据流程 | 一个存活 archive epoch；实际候选抽取与原文打开；D 使用不可变 prime cache，C 的新收据不会流入后续 D；每次原文打开先准入 | [PAIRED_EVIDENCE_HELPER.md](PAIRED_EVIDENCE_HELPER.md) |
| B 强基线接口 | 固定官方 Raw-RAG、embedding 与 reranker；每次 HTTP/重试先持久化准入；绑定原请求、归档与检查点；保留真实用量及有效失败前缀 | [BASELINE_RUNTIME.md](BASELINE_RUNTIME.md) |
| 现金控制 | 同一 canonical ledger；固定 relay 注册；不可变逐请求完成证据；串行累计用量上界；未知、过期、超额、迟到即停止，未知现金不核销 | [NATIVE_RELAY.md](NATIVE_RELAY.md) |
| 评分、报告和设计分析 | 封存输出与冻结标签绑定；直接调用现有统计器；真实无结果时效果、区间和正式 N 均保留 null | [SCORING.md](SCORING.md)、[REPORTING.md](REPORTING.md)、[DESIGN_ANALYSIS.md](DESIGN_ANALYSIS.md) |
| 真实任务环境 | 指定 Mac 安装 Python 3.10.16；两套固定依赖分别 17/17、15/15 匹配；各自真实隔离探针通过，历史失败回执保留 | [macos-python-setup-03.json](artifacts/checks/public-workspace/macos-python-setup-03.json) |
| 主进程依赖 | 指定 Mac 准备独立 Python 3.12.13 环境、37 个 wheel 包、两套 tokenizer/缓存和私有配置；实际 SDK 构造与编码检查未触发网络或凭据读取 | [macos-dependency-setup.json](artifacts/remaining-completion-01/macos-dependency-setup.json) |
| 目标机部署与预检 | 已发布实现部署到原 canonical runtime；核对 771 个静态文件、两份 public digest 和原授权/账本；实际默认预检正常完成，dispatch 因原配额及缺少 B 配置/已核验 scope 而阻断 | [部署回执](artifacts/remaining-completion-01/macos-runtime-deployment.json)、[实际预检](artifacts/remaining-completion-01/macos-native-preflight.json) |
| 文档和投稿包核对 | 修正页数、来源资格、旧运行状态及成本语义；保留 26 页正文稿、27 页 TMLR 格式稿和源码包的原始字节 | [COMPLETION.md](COMPLETION.md)、[SUBMISSION.md](SUBMISSION.md) |
| 集成审查与回归 | 原生状态继承、失败用量、source-open 身份、现金完成握手均有独立 AI 审查和回归；不冒充真人科学评审 | [NATIVE_INTEGRATION_REVIEW.md](NATIVE_INTEGRATION_REVIEW.md)、[本轮验证](artifacts/remaining-completion-01/README.md) |

当前已实际生成[零结果报告](artifacts/remaining-completion-01/reporting/report/report.md)和[设计分析](artifacts/remaining-completion-01/reporting/design-analysis/design-analysis.md)。它们记录 **NOT MEASURED**，不把未执行的单元当作失败结果，也不把工程夹具加入论文样本。16 个已批准开发单元仍保留，尚未执行。

## 验证范围与修正

- Node 研究套件 **123 项通过，0 失败、0 跳过**。
- Python 研究套件共发现 **496 项：487 项通过、9 项跳过、0 失败**。9 项使用旧本地 Python 3.10 fixture 环境，本检查机没有该旧目录；它们明确跳过，没有声称通过。指定 Mac 的固定环境与隔离探针另行真实验证。
- 仓库主套件 **197 项通过**，另外 **4 项因 bundle 未构建跳过**；不与研究套件合并计数。
- 全量首次回归暴露两类旧测试假设：复制账本后仍假定已有预留为零，以及把冻结计划内旧绝对路径当作当前 checkout。测试已改为校验准确增量、使用明确的临时 fixture，并新增历史计划不得被静默迁移的检查。原计划、授权与历史账本未修改。新 driver 的价格 fixture 也已补齐严格价格证据字段。初次失败日志与后续通过日志均保留。
- 已运行的默认 driver 仅作只读预检：模型、网络、任务源码执行、子进程和账本写入均为 0；结果为 `dispatch_ready=false`。它不把缺少配置的本地检查机误报成指定 Mac 的真实服务状态。
- 随后已在指定 Mac 使用真实私有配置完成默认预检，reader/tokenizer、路径迁移、授权和两任务依赖检查通过。缺原生额度、embedding/reranker 环境及已核验 scope 的四项阻断均原样保留。部署封装脚本首次误把已使用次数当作剩余次数；错误说明留存，仅重做只读检查保存报告，未重做部署、任务或模型调用。

## 原有授权和账本保持有效

原授权文件仍为[第 1 批 authorization.json](artifacts/authorized-batch1/authorization.json)，记录用户此前的“全部批准”：2 次原生尝试、16 个开发方法单元、总新增现金 CNY 100。两次原生尝试已在此前使用；本轮“把剩下的全部做完”没有被解释为重置次数、增加现金或接受新的付费服务。

| 项目 | 当前记录 |
|---|---:|
| Canonical journal | 7 条事件；本轮未追加 |
| 原生尝试 | 2 已使用，0 剩余 |
| 开发方法单元 | 0 已执行，16 剩余 |
| 真实 DeepSeek 抽取诊断 | 此前 1 次；不是原生任务或论文样本 |
| 总新增现金上限 | CNY 100.00 |
| 账本保留的未核销上界 | CNY 3.00 |
| 剩余预留容量 | CNY 97.00 |
| 实际新增费用总额 | null；3.00 是预留而非实付 |

原 4 条事件的字节前缀及当前 7 条事件均已核对。原授权、source plan、shared budget、固定 Raw-RAG 配置及 PDF/ZIP 字节保持不变。详细摘要和验证日志见[本轮证据目录](artifacts/remaining-completion-01/README.md)。

## 尚需真实外部条件的步骤

| 条件 | 为什么当前无法代填或执行 | 条件到位后的具体动作 |
|---|---|---|
| 新增原生准备次数 | 原批准上限 2 次已经用完；当前两份真实任务没有可使用的 task-bound native checkpoint | 对 2 个任务 × 2 个 replicate 创建 4 个实际父会话/压缩检查点，再执行原有 16 个开发单元 |
| B 的 Git、既有账户配置与价格依据 | 指定进程此前检查到 `VECTORIZE_API_KEY`、`RERANK_API_KEY` 未配置；固定 `rerank-v3.5` 的当前账户计费与可用性未核实；Mac 的 Git 与一次瓶装安装均停在 Xcode 许可前提 | 由用户处理本机许可或提供已可用 Git，取得并核对固定 clean checkout；通过私有配置提供既有凭据，核对实际模型和人民币上界后准入。已下载源码和构造 SDK 不冒充真实 B 运行 |
| 独立标签与作者事实 | 22 份真人双审材料仍为空；作者顺序、机构、真实贡献、责任与利益冲突未知 | 两名独立真人完成标签与裁决，作者提供真实事实，再验收任务和更新声明 |
| 真实先导与正式研究 | 尚无可用于估计效应/成本的完整配对数据，正式 N 未决定 | 完成有计量的先导；据此冻结方法、预算、样本量与分析；再执行确认研究和外部验证 |
| 最终投稿 | 当前稿件保留 PENDING，科学和作者条件尚未满足 | 完成结果稿、作者审阅与最终提交资格核对后，再进行具体的投稿批准与提交 |

## 下一批新增执行批准项（草案，未生效）

这里只集中列出超出原授权的具体动作；已批准的公开研究分支、16 个开发方法单元和 CNY 100 总现金上限不重复请求。

**提议仅增加 4 次原生准备尝试**，对应 `w-101/w-102 × replicate 1/2`。每次沿用原 600 秒、最多 5 次 generation start、2 次 compaction、6 次测试执行、20 次公共工具调用上限；同一真实尝试失败也计数，不自动补发。四个任务父状态完成后，续跑原有 A/B/C/D 共 16 个开发单元，每单元最多 300 秒。本草案没有启用新增次数，也没有改写原 authorization。

可审查的**条件预算**如下，保持总现金上限 CNY 100：

| 组成 | 条件上界 CNY |
|---|---:|
| 既有未核销预留 | 3.00 |
| 4 个原生 scope × 3.20 | 12.80 |
| 16 个 reader scope × 3.20 | 51.20 |
| 4 个 B 单元 × 最多 16 次检索请求 × 0.50 | 32.00 |
| 合计 | **99.00** |

3.20 是当前固定 profile、串行 completion 握手与调用当日官方峰值价格核验共同成立时的 scope 预留上界，不是预计实付。**B 的 0.50/请求是待核实的准入上限，绝非已确认报价**；只有实际账户、计费单位和汇率证据能够证明每个检索请求不超过它时，这张预算才可执行。否则继续阻断，不能把猜测价格写入配置，也不能突破 100 元。价格跨日或变更时必须重新核验，失败和未知费用继续占用预留。

这批开发执行不会自动授权正式研究、购置新服务、充值、合并 main、发送编辑邮件、提交预印本或论文；也不会使空白真人材料或工程测试变成研究结果。
