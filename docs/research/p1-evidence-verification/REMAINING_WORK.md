# P1 剩余工作执行记录

更新：2026-11-29（Asia/Shanghai；UTC 日期仍为 2026-11-28）。用户要求：**“把剩下的全部做完”**，随后明确批准补充尝试，并要求可靠可代劳的工作尽量由 AI 完成。

**本轮授权执行已完成，四次补充原生准备均未成立，不能自动补发尝试或修改预算。** 配对运行、分析工具、固定环境和受控执行接口已实现；真实运行产生了 10 次完成的 DeepSeek 请求与保留的失败收据，但没有有效 task-bound native checkpoint，16 个方法单元均未派发。论文仍是 **When to Reopen the Source: Evidence Verification after Native Agent Compaction** 的方法与实验协议工作稿，尚未投稿。当前已验收研究任务、正式方法结果和已完成真人评审均为 **0**。程序与 AI 辅助预审已完成 11 个材料包和 37 条义务草案；两套有限行为 oracle 已完成各 5 个 pytest 用例的参考源码资格验证。这些开发产物不是 gold 标签或正式研究样本，也不是方法最终制品的测试结果。最终执行与计量见[机器汇总](artifacts/native-supplement-01/observations.json)及下表。

完整运行、用量、账本镜像、原始/脱敏导出边界与部署来源见[补充执行证据索引](artifacts/native-supplement-01/README.md)。

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
| 目标机部署与预检 | 首版部署核对 771 个静态文件和两份 public digest；旧预检的额度阻断作为历史保留。后续已显式激活四次补充尝试，受限 workspace 隔离探针和实际宿主启动已发生 | [首版部署](artifacts/remaining-completion-01/macos-runtime-deployment.json)、[补充部署](artifacts/native-supplement-01/deployment.json)、[激活收据](artifacts/native-supplement-01/activation.json) |
| 固定 B 源码与私有运行绑定 | Mac 上真实 Git detached checkout 的固定 commit、对象完整性、九个关键源码及 clean worktree 核验通过；独立私有配置已绑定它并设置经验证 Git 的启动优先级，原运行配置未改。无需用户处理 Xcode 许可或 PATH | [Git checkout 收据](artifacts/native-supplement-01/macos-rawrag-git-checkout.json)、[实际绑定收据](artifacts/native-supplement-01/macos-rawrag-private-binding.json)、[B 就绪重查](artifacts/native-supplement-01/fixed-baseline-readiness.json) |
| 开发材料与标签草案 | 11 包程序预审、37 条明确标识的 nonblind AI-assisted 义务草案；旧 22 份真人 review 与 11 份裁决模板仍为空，原记录保留 | [ANNOTATION_V2.md](ANNOTATION_V2.md)、[实际程序报告](artifacts/remaining-completion-01/assisted-review-v2/programmatic/report.md) |
| 有限行为 oracle 的参考资格 | Flask 原版、Requests 明确 URL 格式的 v2 各 5 个真实 pytest 用例；base、官方 fixed、错误实现及拒绝控制均有隔离观察。原 Requests 六项版在官方 fixed 上 5 通过、1 失败，原失败保留 | [资格验证](artifacts/remaining-completion-01/oracle-qualification-01/README.md)、[282 份发布记录的复算](artifacts/remaining-completion-01/oracle-qualification-01/verification.json) |
| 文档和投稿包核对 | 修正页数、来源资格、旧运行状态及成本语义；保留 26 页正文稿、27 页 TMLR 格式稿和源码包的原始字节 | [COMPLETION.md](COMPLETION.md)、[SUBMISSION.md](SUBMISSION.md) |
| 集成审查与回归 | 原生状态继承、失败用量、source-open 身份、现金完成握手均有独立 AI 审查和回归；不冒充真人科学评审 | [NATIVE_INTEGRATION_REVIEW.md](NATIVE_INTEGRATION_REVIEW.md)、[本轮验证](artifacts/remaining-completion-01/README.md) |

已有[零结果报告](artifacts/remaining-completion-01/reporting/report/report.md)和[设计分析](artifacts/remaining-completion-01/reporting/design-analysis/design-analysis.md)是补充执行前的真实快照，记录 **NOT MEASURED**。本轮实际运行另存为[补充观察](artifacts/native-supplement-01/observations.json)，没有方法臂结果可加入原报告；旧报告不改成看似当时已有结果的版本。未执行单元保持未测量，已启动的失败尝试单独保留，工程夹具不进入论文样本。

## 已完成的验证范围与修正

以下分别列出补充原生执行前的集成检查点、补充 v2 全量记录和最终 reader 修复后的 v3 Python 全量记录；不同代码版本与套件不混算。

- Node 研究套件 **123 项通过，0 失败、0 跳过**。
- Python 研究套件共发现 **496 项：487 项通过、9 项跳过、0 失败**。9 项使用旧本地 Python 3.10 fixture 环境，本检查机没有该旧目录；它们明确跳过，没有声称通过。指定 Mac 的固定环境与隔离探针另行真实验证。
- 仓库主套件 **197 项通过**，另外 **4 项因 bundle 未构建跳过**；不与研究套件合并计数。
- 后续补充 v2 的[实际全量验证](artifacts/native-supplement-01/validation-v2/summary.json)为 **Python 566 项：557 通过、9 跳过、0 失败；Node 123 通过；主仓库 197 通过、4 跳过**。这些是同一批代码的不同套件，不与较早 496 项检查点重复累计。
- 关闭额外宿主工具后的 [v3 Python 全量验证](artifacts/native-supplement-01/validation-v3/summary.json)为 **569 项：560 通过、9 跳过、0 失败**；此阶段未另称重跑 Node 或主仓库套件。reader 的 13 项定向测试另经独立复核通过。版本和套件分别陈述，不相加为研究样本。
- 最终 50-event canonical mirror 到位后的[相关 85 项回归](artifacts/native-supplement-01/validation-after-ledger/summary.json)全部通过，0 失败、0 跳过，与全量重叠，不额外累计。首次命令因模块名撞到 Python 自带 `test` 包而未加载目标测试，修正调用目录后通过；两个日志均保留，无生产或测试代码改动。
- 全量首次回归暴露两类旧测试假设：复制账本后仍假定已有预留为零，以及把冻结计划内旧绝对路径当作当前 checkout。测试已改为校验准确增量、使用明确的临时 fixture，并新增历史计划不得被静默迁移的检查。原计划、授权与历史账本未修改。新 driver 的价格 fixture 也已补齐严格价格证据字段。初次失败日志与后续通过日志均保留。
- 已运行的默认 driver 仅作只读预检：模型、网络、任务源码执行、子进程和账本写入均为 0；结果为 `dispatch_ready=false`。它不把缺少配置的本地检查机误报成指定 Mac 的真实服务状态。
- 指定 Mac 的早先默认预检中，reader/tokenizer、路径迁移、授权和两任务依赖检查通过；当时四项阻断的原始报告保留。后续显式补充授权解决了新增 native 次数，核验过的 Git checkout 解决了源码准备。B 的两项凭据及固定模型计费依据仍缺，不能把旧预检照抄成当前全部阻断。
- 首个补充 native 尝试暴露了 loopback 代理路由问题。固定 Codex 源码核对后，host 环境增加精确的 localhost/127.0.0.1 例外，未改变系统代理或 managed policy；同时修正固定版本的 metadata、reasoning-summary 和内置工具注册对接。源代码证据、真实失败、先红后绿测试及测试同步修正分别保留在[路由核对](artifacts/native-wire-routing-01/README.md)和[补充证据目录](artifacts/native-supplement-01/)。修复代码通过离线合同不等于后续原生运行已经成功。
- 第二次请求实际抵达 relay 后暴露额外工具声明。固定源码证实 persistent thread 的默认 Goals 扩展可注册额外工具；reader 现显式关闭 Goals 及已核实的其他工具入口，五个公共工具的严格白名单保持不变。[源码依据与修复记录](artifacts/native-wire-routing-01/persistent-extension-tools.json)属于静态原因证据；实际被拒请求没有归档工具名称，不能声称逐名观测到了 Goals 工具。

## 已完成的补充授权执行与最终记录

原[第 1 批 authorization.json](artifacts/authorized-batch1/authorization.json)的 2 次 native 已消耗，16 个开发方法单元和总新增现金 CNY 100 不变。用户随后明确批准：

> 确认追加
> 真人如无必要尽可能由你代劳

[不可变补充文件](artifacts/authorized-batch1/native-preparation-supplement1.json)已在同一 canonical journal **显式激活**，只增加 `w-101/w-102 × replicate 1/2` 四个具名原生准备尝试。原七条历史事件的字节前缀保留；这不是新账本，也没有把旧两次改为未使用。每次仍受原时间、generation、compaction、测试和公共工具边界约束，失败消耗其具名次数，不自动补发。[激活收据](artifacts/native-supplement-01/activation.json)、[补充合同](NATIVE_SUPPLEMENT.md)

<!-- SUPPLEMENT_RUN_STATUS_START -->
**最终状态：`authorized_supplement_exhausted`。** 四个具名 backend 均已关闭，四次准备全部为 `capture_incomplete`，有效 checkpoint 为 0；A/C/D 因准备未完成而未派发，B 因指定依赖未准入而未派发。所有方法均为 `not_scored`，原四臂分母保留。[机器汇总](artifacts/native-supplement-01/observations.json)

| 具名准备 | 完成的 provider 请求 | 公共工具调用 | 真实停止边界 |
|---|---:|---|---|
| `w-101` replicate 1 | 0 | 0 | 隔离探针、thread/start 与 turn 启动后收到 loopback 502；relay dispatch 和 provider audit record 均为 0 |
| `w-101` replicate 2 | 0 | 0 | 实际 39,739 B 请求到达 relay，以 `server_or_unknown_tools_forbidden` 拒绝；provider 记录为 0、凭据未读取 |
| `w-102` replicate 1 | 5 | 7：1 次 `list_files`、6 次 `read_file` | 第 6 个请求由本地 relay 在 provider 派发前以 `scope_reference_input_budget_exhausted` 拒绝；累计 reference-input 上限为 65,536，5 次 native generation_start 也已用尽 |
| `w-102` replicate 2 | 5 | 7：1 次 `list_files`、6 次 `read_file` | 同样在第 6 个请求的本地准入处触及累计 reference-input 上限；5 次 native generation_start 也已用尽 |

两个 `w-102` 准备都没有执行 `write_file`、`run_current_tests` 或 `record_review`，没有形成有效原生准备。已完成请求的 reference input 尚低于 65,536，但接纳第 6 请求会超过该累计上限，因此在派发前被拒绝，不计为完成调用。仅提高输入上限不能恢复已耗尽的生成次数，更不能恢复已消费的具名尝试。

| 用量范围 | provider input tokens | 其中 cached input | provider output | reference input（准入口径） |
|---|---:|---:|---:|---:|
| `w-102` replicate 1 | 50,875 | 39,424 | 486 | 54,139 |
| `w-102` replicate 2 | 51,166 | 47,744 | 601 | 54,467 |
| 本补充四次合计 | **102,041** | **87,168** | **1,087** | **108,606** |

缓存输入是 provider input 的子集，不能再次相加；reference input 是独立的预算核算口径，也不与 provider input 相加。两次 `w-101` provider 用量为 0，不掩盖其已消耗尝试和未核销现金。

| 项目 | 最终实际状态 |
|---|---|
| 原授权 native | 2 次已消耗，剩余 0，历史不变 |
| 补充 native | 4 次已消耗，剩余 0；不重放、不自动返还 |
| 方法单元 | 已预留/执行 0；原 16 单元未消费，但缺少可用父检查点，不能据此续跑 |
| B | 未调用、未预留首次尝试；Git checkout 和独立私有运行绑定均已完成，两个指定 key 与固定 `rerank-v3.5` 的账户计费/可用性证据仍缺 |
| 研究结果 | 已验收研究任务 0、正式方法结果 0、全部方法 `not_scored`；效果、区间和正式 N 均未测量 |
| Canonical journal | 50 条事件；HEAD 为 `9daabc2b62eff8efd17bd5783decc619f25094c2748fd4e838f2735150a25ed0` |
| 历史完整性 | 原七条事件字节前缀 SHA-256 `d675c9c1f868d6169615c877bb6ffc0d88f73813eab0ccf830669ef97f6e47fa` 保持不变；原 authorization、source plan、shared budget 原字节未改 |
| 现金 | 总上限 CNY 100；保留未核销上界 **CNY 15.80**（既有 3.00 + 四次各 3.20），剩余现金容量 **CNY 84.20**；实际费用总额 **null** |
| 费用含义 | 已知 token 用量不等于已核销账单；没有账单闭合时实际费用保持 null。剩余现金容量不产生新的 native 次数或复用失败 scope 的许可 |

首个失败的[宿主事件](artifacts/native-supplement-01/w-101-r1/host-events.jsonl)、[relay 状态](artifacts/native-supplement-01/w-101-r1/relay-state.json)及[结果记录](artifacts/native-supplement-01/w-101-r1/result.json)保留原样。后续修复不回填这次失败为成功，不重试其已消费 grant。

第二次失败的[本地拒绝收据](artifacts/native-supplement-01/w-101-r2/local-rejection.json)、[宿主事件](artifacts/native-supplement-01/w-101-r2/host-events.jsonl)、[provider audit](artifacts/native-supplement-01/w-101-r2/provider-audit.json)和[结果](artifacts/native-supplement-01/w-101-r2/result.json)也已保留。拒绝收据记录实际接收长度、摘要、固定错误码和 lease 身份，不含请求正文或凭据。两个 `w-102` 的[replicate 1 记录](artifacts/native-supplement-01/w-102-r1/)与[replicate 2 记录](artifacts/native-supplement-01/w-102-r2/)包含实际 host、provider audit、relay、operations、usage、完成请求和本地拒绝收据，状态归入[最终观察汇总](artifacts/native-supplement-01/observations.json)。canonical journal 镜像保留原字节；含路径的 controller trace 脱敏审阅副本不充当活动账本。
<!-- SUPPLEMENT_RUN_STATUS_END -->

本轮使用显式 A/C/D development 入口，保留 B 缺席与四臂分母。这个入口没有绕过真实父会话、原生压缩和同父分叉要求；由于四次均无可用父检查点，所有方法单元都保持未派发。授权次数耗尽后，运行已停止。完成了本轮执行与失败记录，不代表原生准备或科学比较完成。

## 真正尚需满足的条件

| 条件 | 当前事实 | 后续具体动作与责任 |
|---|---|---|
| 原生准备的预算与读取策略 | 四次补充额度已耗尽，无有效 checkpoint；两个 `w-102` 各在只读工具阶段完成 5 次生成，并在第 6 请求触及累计输入准入边界 | 先离线修订分页、读取请求与完整准备所需的生成/输入预算设计，明确哪些可在现有边界内完成、哪些会改变合同；用固定真实请求形状复算并检验。不直接按同一配置反复重跑，不修改原冻结计划，也不将新尝试写成已经获批 |
| 固定 B 的服务访问与计费证据 | `VECTORIZE_API_KEY`、`RERANK_API_KEY` 未配置；固定 `rerank-v3.5` 的账户可用性和计费单位/人民币上界未核实。Git checkout、私有配置绑定及启动 Git 优先级已准备 | 账户持有人私下提供现有凭据和适用账单/价格依据；将经核验计费证据接入原 B 准入。无需其改 PATH 或处理已解决的许可；不得用新模型价格或猜测 CNY 0.50/请求替代 |
| 真实工作流和方法执行 | 可调用实现与环境已有，但本轮没有产生可用父检查点，16 个方法单元未派发；完整四臂比较未发生 | 先闭合准备设计的可执行性和实际运行依据；后续若有合法新运行，仍须观察真实相关状态变化、压缩、续跑、最终制品与测试，不能把未消费 method 额度当作 native 重试许可 |
| 独立标签与科学测量 | v2 已完成 11 包预审、37 条 AI 草案及两套各 5 项的参考源码 oracle 资格验证；方法最终制品行为、完整语义和复合终点仍未测量。22 份旧真人表不是开发运行前提 | 将已验证 oracle 独立绑定到真实封存方法制品，保留原 Requests 草案失败和 v2 范围缩小的时点；正式使用前补齐覆盖、误差与语义依据并冻结版本。程序和 AI 继续完成可靠部分，仅对无法可靠形式化的争议安排所需实质复核 |
| 先导和正式研究 | 尚无支持正式效应、成本或样本量决定的完整研究数据 | 完成真实先导和适用成本记录，再冻结正式设计、样本量及分析；正式研究须有相应具体执行授权，不能把当前开发单元改名为确认样本 |
| 作者事实与最终投稿 | 作者身份、机构、真实智力贡献、COI/资助、相关投稿和最终同意尚无事实记录；论文主结果仍为 PENDING | 作者提供本人事实并实际审阅研究主张；AI 可继续整理引用、分析、文稿、匿名和格式。科学结果及作者责任闭合后才批准并提交确切最终版本 |

真正需要作者本人完成的是提供真实身份与贡献/利益关系、履行对内容的实际复核和责任、确认完整作者集合与账户资格，以及最终版本和投递的同意。账户私有凭据和适用计费证据也须来自真实账户持有人。不得把填写 22 张空表当作上述事实的替代，也不预设必须另找固定人数的外部真人审阅所有开发字段。本轮既有授权已执行完毕；本文件没有提出或激活新的批准。

## 已冻结的本轮结论

| 结论范围 | 已存依据及边界 |
|---|---|
| 授权执行 | 原两次与补充四次均保持已消耗，全部补充 backend 已关闭，没有自动补发或重放 |
| 实际运行 | 10 次 provider 请求完成、14 次公共工具调用，四个准备均 incomplete；没有有效检查点、方法制品或方法评分 |
| 可复核计量 | provider input 102,041，其中 cache 87,168，output 1,087；reference input 108,606；50 条 canonical 事件，现金保留 15.80、实付 null |
| 工程验证 | 最终 reader 的 v3 Python 全量 560 通过、9 跳过；v2 Node 123 通过和主仓库 197 通过、4 跳过分别保留，未混称同次运行 |
| 科学与投稿 | 有限 oracle 的参考资格已验证，正式研究任务与方法结果仍为 0；本轮 manuscript/PDF/ZIP 未改，尚未投稿 |

这些是本轮已结束执行的结论。[下一步离线预算设计诊断](NATIVE_NEXT_STEP.md)已列出 prelude、extraction、compaction 的共同计数及读取策略边界，尚未更改任何配置或创建新许可。后续首先处理这些设计问题，并继续可靠的离线核验、科学准备和文稿工作；不以现金余量、工程测试通过或缺少真人表为理由改变历史授权与研究状态。
