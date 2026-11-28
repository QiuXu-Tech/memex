# P1 本轮交付与研究状态

更新：2026-11-29（Asia/Shanghai）。论文：**When to Reopen the Source: Evidence Verification after Native Agent Compaction**。

**本轮授权执行已完成，四次具名补充 native 准备均未成立，不能自动补尝试或改预算。** 配对运行、原生后端、强基线接线、计量、评分和报告工具已实现；固定环境、Git checkout 及独立私有运行绑定已核验。实际补充执行完成 10 次 DeepSeek 请求，但没有有效 task-bound native checkpoint，16 个方法单元均未派发。所有原始失败和次数消耗保留，不能把真实模型响应或工程修复当作准备成功。论文当前是方法与实验协议工作稿，正式实验结果为 0，真实作者贡献与责任事实尚待补齐，不能标记为“可投稿”或“已投稿”。最终次数、方法单元、用量和现金记录统一见 [REMAINING_WORK.md](REMAINING_WORK.md)与[机器汇总](artifacts/native-supplement-01/observations.json)。

后续配置更新：用户已选择 DeepSeek 作为生成服务，并已完成一次真实候选抽取诊断；HTTP 200，1 次生成、0 次自动重试，434 输入与 210 输出 tokens，取得一条通过现有校验的候选 claim。见[真实诊断记录](artifacts/deepseek-live-01/README.md)与 [DEEPSEEK.md](DEEPSEEK.md)。这项接入验证不增加论文样本，不替换 B 臂固定的 embedding/reranker；原授权及历史事件保留，现金台账只追加本次诊断事件，正式研究状态仍未就绪。

## 先阅读这些文件

| 用途 | 文件 |
|---|---|
| 英文研究工作稿 | [manuscript.pdf](manuscript.pdf)：26 页；可编辑 [Markdown](manuscript.md) 与 [LaTeX](manuscript.tex) |
| 官方 TMLR 格式稿 | [main.pdf](submission/tmlr-review/main.pdf)：27 页，首页明确 NOT READY / NOT SUBMITTED |
| 可重建源码包 | [review-source.zip](submission/review-source.zip)：22 个成员；独立解包重建的页面文字、尺寸和像素一致 |
| 研究协议与执行证据 | [PROTOCOL.md](PROTOCOL.md)、[EXECUTION.md](EXECUTION.md)、[REVIEW.md](REVIEW.md) |
| 来源资格与任务材料 | [来源汇总](tasks/reproduction-expansion/summary.json)、[TASKPACKS.md](TASKPACKS.md)、[ANNOTATION.md](ANNOTATION.md) |
| 本轮运行与科学工具接口 | [NATIVE_DRIVER.md](NATIVE_DRIVER.md)、[PAIRED_RUNTIME.md](PAIRED_RUNTIME.md)、[PAIRED_DISPATCH.md](PAIRED_DISPATCH.md)、[BASELINE_RUNTIME.md](BASELINE_RUNTIME.md)、[SCORING.md](SCORING.md)、[REPORTING.md](REPORTING.md)、[DESIGN_ANALYSIS.md](DESIGN_ANALYSIS.md) |
| 当前真实零结果的复算产物 | [零结果说明与来源绑定](artifacts/remaining-completion-01/reporting/README.md)：NOT MEASURED，未选择正式 N |
| 最终完成记录与外部前提 | [REMAINING_WORK.md](REMAINING_WORK.md)：四次补充授权执行已结束、真实失败与用量、预算设计问题及具体服务前提 |
| 完整运行与导出记录 | [补充执行证据索引](artifacts/native-supplement-01/README.md)：四次尝试、十次 provider 完成、实际用量、原账本镜像与原始/脱敏副本边界 |
| 可靠可代劳的材料预审 | [ANNOTATION_V2.md](ANNOTATION_V2.md)：11 包程序预审、37 条 AI-assisted 义务草案；不冒充 gold 或真人双审 |
| 有限行为 oracle 的实测资格 | [参考源码资格验证](artifacts/remaining-completion-01/oracle-qualification-01/README.md)：Flask 与 Requests v2 各 5 项 pytest；15 个 observer、5 个隔离 probe、282 份发布记录复核，不计方法结果 |
| 投稿条件与贡献记录 | [SUBMISSION.md](SUBMISSION.md)、[SUBMISSION_PACKAGE.md](SUBMISSION_PACKAGE.md)、[CONTRIBUTIONS.md](CONTRIBUTIONS.md) |

## 已实际完成的工作

### 1. 工程与审查

自动候选抽取、真实 Memex L2 原文、类型核验、当前文件状态绑定、受限执行 broker、首次运行保留、评分绑定及成本未知值处理均已有可检查实现。DeepSeek 接入前的完整研究套件 **366 项通过：70 项 Node、296 项 Python，0 失败、0 跳过**。见[本批日志](artifacts/checks/authorized-batch1/paper1-suite.txt)；历史 phase3 的 265 项记录保留。后续 DeepSeek 诊断集成的 **112 项 Node、72 项相关 Python 测试通过**，范围及初始路径相关失败详见[诊断验证记录](artifacts/checks/deepseek-diagnostic/validation.json)；后一次未重跑完整 Python 研究套件。

原生与来源阶段的独立 AI 审查发现并修复三项问题：公共 JSONL 嵌套字段可能携带评估标签；审批处理器的允许范围过宽；来源资格检查记录了测试文件一致性，却没有把它作为通过前提。修复后的定向套件分别为 26、12、18 项通过。审查不冒充独立人工评审。

剩余工作首个集成检查点的完整研究回归为 **Node 123 项通过；Python 487 项通过、9 项因检查机缺少旧固定环境而跳过，0 失败**，主仓库另有 197 项通过、4 项因 bundle 未构建跳过，历史记录见[本轮证据](artifacts/remaining-completion-01/README.md)。补充执行 v2 的全量验证随后增至 **Python 566 项：557 通过、9 跳过、0 失败；Node 123 通过；主仓库 197 通过、4 跳过**。额外工具修复后的 [v3 Python 全量](artifacts/native-supplement-01/validation-v3/summary.json)为 **569 项：560 通过、9 跳过、0 失败**，该阶段未另称重跑 Node 或主仓库套件。不同检查点分别保留，不重复相加；最终部署版本及日志入口见 [REMAINING_WORK.md](REMAINING_WORK.md)。这些工程验证不增加论文样本。

最终 canonical journal 的 50 条原字节镜像到位后，授权、诊断、补充额度与两个 driver 的[85 项相关回归](artifacts/native-supplement-01/validation-after-ledger/summary.json)全部通过，0 失败、0 跳过；它们与全量重叠。首次命令因 Python `test` 包命名冲突未加载目标测试，修正调用目录后通过，无生产或测试代码变更；错误调用日志保留。

审批处理器已按 Codex 0.153.0 的真实协议实现两条一次性请求路径。本批已真实观察到 `run_current_tests` 和 `record_decision` 的单次批准与后续工具执行，来源记录为 `prior_chat_authorization`，不声称新的真人点击、设备验证或持久授权。原来的审批阻断记录保持不变。

本轮又补充 task-bound 配对运行、受限公共工作区、共同 DeepSeek reader/profile、逐请求 relay、固定 Raw-RAG 受控接口，以及绑定原现金台账的 runtime controller。真实四臂比较仍未完成。控制器将 provider 请求绑定到最近一次准入操作，强制计数 native generation/compaction，限制请求与剩余时间；现金采用显式逐请求上界，或固定 relay 的串行累计用量证明及 completion 握手。后者仍预留完整 scope 上界、未知时停止且不核销实际费用。细则见 [DEEPSEEK.md](DEEPSEEK.md)。新增授权只增加四个具名准备尝试，现金 CNY 100 与方法 16 单元均未增加。

离线完整评分工具只聚合相应版本的已冻结标签、行为检查与封存证据；报告直接调用现有分析器，成本沿用 `experiment.py join` 重算值。另有 v2 的 development 部分组件检查，但语义、隐藏行为和复合终点仍为未测量，不能生成伪造的完整质量分数。设计分析在无真实先导时保留 null，不拟合功效或自动选 N。已有空研究清单已实际生成[报告](artifacts/remaining-completion-01/reporting/report/report.md)与[设计分析](artifacts/remaining-completion-01/reporting/design-analysis/design-analysis.md)，均为 **NOT MEASURED**。0 个已验收研究任务不撤销单独的 16 单元开发计划，工具测试也不增加人类评审或论文 N。

### 1a. 此前第 1 批批准后的真实原生运行

第 1 次尝试启动 1 个生成 turn，在响应流多次重连后于 125.473 秒超时。第 2 次启动 5 个生成 turn、完成其中 4 个，实际完成 2 次原生压缩与 2 次候选抽取；一次真实测试通过，压缩后的稳定状态模拟决定为 release。未变化的收据被复用，改变字节后旧的通过收据被重新打开并以版本不匹配拒绝。

最后一个 changed-state 决定在总时限 480 秒到达时尚未完成；没有观察到新失败测试或 hold 决定，完整集成 checks 保持 null。这些部分观察不能改写为一次成功试验。两次额度均已使用；实际事件、许可消费、失败和用量见[本批记录](artifacts/authorized-batch1/README.md)。计量不完整，完整成本和实际账单仍为未知。

### 1b. 已完成的四次补充执行与真实失败记录

用户明确同意追加 `w-101/w-102 × replicate 1/2` 四个原生准备尝试，并要求可靠可代劳的工作尽量由 AI 完成。[补充授权与激活收据](NATIVE_SUPPLEMENT.md)在同一 canonical journal 追加记录，原两次消耗及原七条历史字节前缀保留。

`w-101` replicate 1 在实际宿主 turn 启动后收到 localhost 502；provider 记录为 0，未获得有效检查点。固定源码和实际 feature 检查支持代理路由原因，后续只增加了进程内精确 loopback 例外。replicate 2 随后实际抵达本地 relay，确认该路由修复生效；其 39,739 B 请求因额外工具声明被严格白名单拒绝，provider 记录仍为 0，凭据未读取，结果仍为 `capture_incomplete`。两次失败均消耗具名次数，没有回填成功或自动返还。额外工具入口随后根据固定源码关闭，未放宽 relay 白名单。

`w-102` replicate 1/2 各实际完成 **5 次 DeepSeek 请求、7 次公共工具调用（1 次 list、6 次 read）**，没有写文件、运行测试或记录 review，也没有得到有效检查点。每次第 6 个请求都由本地 relay 在 provider 派发前以 `scope_reference_input_budget_exhausted` 拒绝；累计 reference-input 上限为 65,536，native generation_start 的 5 次额度也已用尽。仅增加输入上限并不能继续这些已结束的尝试。[replicate 1 记录](artifacts/native-supplement-01/w-102-r1/)、[replicate 2 记录](artifacts/native-supplement-01/w-102-r2/)

本补充实际合计 provider input **102,041**，其中缓存输入 **87,168**，output **1,087**；独立预算口径 reference input **108,606**。缓存是输入子集，reference 也不额外加入 provider token 合计。四个 backend 均已关闭，四次准备都是 incomplete，A/C/D 均未派发，B 未调用或预留，所有方法 `not_scored`。原两次与补充四次均已消耗，方法仍为 0/16；canonical journal 50 条、现金保留上界 **CNY 15.80**，剩余现金容量 **84.20**，实际费用 **null**。[最终汇总](artifacts/native-supplement-01/observations.json)

本轮完成的是授权执行和可复核的失败观察，原生准备与比较研究尚未完成。下一步先按[离线设计诊断](NATIVE_NEXT_STEP.md)修订读取分页、请求策略和完整准备所需的生成/输入预算设计；不按同一配置反复重跑、不改原冻结预算，也不自动补发新次数。原 16 个未用方法单元不替代有效父检查点或 native 许可。

### 2. 原生只读联调与真实观测

在已有真实测试收据构成的一个开发场景中，实际完成 **5 次模型生成、1 次原生压缩、同一压缩后父线程的 3 次分叉继续回答**。A/C/D 均建议暂缓，并引用较新的失败收据。[完整记录](artifacts/readonly-native/README.md)保留了提示、实际抽取、L2 核验、原始事件、失败预检和执行版本。

| 比较项 | C：每次重开原文 | D：复用未变化的已核验收据 |
|---|---:|---:|
| 支持测试 claim 的本次原文打开数 | 2 | 0 |
| 加入上下文的完整证据包 | 3,447 bytes | 3,447 bytes |
| 本次原生输入 | 15,350 tokens | 15,350 tokens |
| 回答 | hold；正确失败收据 | hold；正确失败收据 |

D 的前置核验实际打开过 2 次原文，仍有目录读取和证据重新传递。另一个无法支持的 claim 保持 unknown。该场景没有得到质量优越性或成本节省证据，也没有执行 Raw-RAG B。原文访问减少不能换算成 token 或费用下降。

五次生成的用量核对为 71,077 输入、937 输出，合计 72,014 tokens。缓存输入与推理输出分别是子集，没有重复相加。压缩通知的计费语义无法闭合，费用保持未知。

### 3. 真实来源扩展

16 个候选、8 个项目均已检查；**12 个满足当前来源与环境资格条件，4 个保留限制**。本轮补做剩余 14 个候选，保留 29 次编号尝试与 34 次顶层测试阶段调用。旧失败和后续诊断分开记录。

| 仍有限制的候选 | 已查明的边界 |
|---|---|
| Requests #5414 | 目标缺陷已修复；完整模块仍有网络条件相关失败 |
| Pylint #4970 | 所选 Python 3.9、仅 wheel 环境缺少兼容的历史 wrapt wheel，未进入测试 |
| SymPy #19637 | 官方列出的转变满足，但模块仍有两个历史 AST 兼容异常 |
| Sphinx #9367 | 42 个实际用例全部通过，但 15 个历史官方 P2P 标签身份未闭合 |

这里的通过不等于官方 Docker 全环境重现，更不等于验收了 P1 工作流。来源扩展的 139 个文件和工作流集合的 782 个文件，共 **921 个条目全部通过哈希核对**。29 份原始扩展收据未改写。私有原始重建包已另行保存，公开记录只保留其哈希与范围，不把官方评估答案提供给模型。

本批又对两份清洁 public base 各做一次 controller-only 固定测试采集：Flask 原公开测试 **59 通过**；Requests 原公开测试 **201 通过、11 跳过**。源码和依赖的前后摘要一致。没有官方未来测试补丁、模型/API 请求或方法单元运行，因此与前述来源资格检查分别计数。新采集器已保存真实 pytest 阶段、双流、模块 origin 与退出状态，见[采集摘要](artifacts/authorized-batch1/python-workflows/summary.json)。

### 4. 可分发的任务与标注材料

已制作 **11 个待验收材料包**：2 个真实来源种子、8 个合成家族中的 9 个分支；另有 **22 份自包含空白双审材料**。后续 [v2](ANNOTATION_V2.md) 已完成全部 11 包的程序预审和 37 条明确标识的 AI-assisted 义务草案，旧真人模板及裁决记录保持原样。固定双真人加逐包第三人裁决是旧 human-v1 路线的合同，**不是开发运行的普遍前置条件**。同一家族的反事实分支不能分别增加独立样本量。

固定 base 的公开文件不含 Git 历史、未来修复补丁或隐藏评估字段。材料清单、来源摘要、输入预算、双审及裁决结构都可验证；空白审阅会被判为未完成。程序预审、AI 草案和真正的人类记录分别计数，均不能单凭结构检查证明语义覆盖、身份或独立性。当前实际人工评审、人工裁决、研究任务验收与正式方法结果均为 **0**。v2 evaluator 草案没有在方法最终制品上执行；正式标签路线仍须验证、版本化和冻结。

两份有限行为 oracle 已实际完成隔离参考源码资格验证：Flask 原五项和 Requests 明确 HTTP/HTTPS URL 格式的 v2 五项，在各自官方 fixed 上均 5 通过，在 base 与故意错误实现上检出对应失败。Requests 原六项版在官方 fixed 上 **5 通过、1 失败**；歧义输入、原版失败和看过参考结果后的 v2 修订均保留。此范围共 15 个 observer 进程、5 个真实隔离 probe，282 份发布记录的哈希与执行汇总已独立复算。没有读取或测试本轮方法最终制品，不能据此给方法评分、宣称完整语义覆盖或追认正式预注册。见[资格结果与边界](artifacts/remaining-completion-01/oracle-qualification-01/README.md)。

### 5. 文稿与投稿材料

当前 PDF 版本已同步较早原生与来源阶段的实测结果及限制；后续 DeepSeek 诊断、补充授权、v2 材料预审和新的失败仅保存在工程与状态记录，**本次没有改写 manuscript、PDF 或 ZIP**。正文保留 16 条参考记录和 **56 个 PENDING**。官方样式固定到明确上游版本，格式转换、字体与页边界检查、逐页视觉检查、源码 ZIP 和独立解包重建均已完成。附有未发送的投稿信草稿、补充材料清单及真实 AI 使用说明。

格式完成不会替代科学证据。官方模板自带的 “Under review” 字样不代表实际投稿；首页和元数据已明确未提交状态。人类思想来源、作者顺序、机构、贡献、利益冲突等均未凭空填写。

## 剩余关卡及其实际前提

| 关卡 | 当前不能声称完成的原因 | 条件具备后的工作 |
|---|---|---|
| 原生可变工具完整链路 | 原两次及四次补充均已消耗；本轮无有效父检查点，两个 Requests 准备同时受累计输入和 5 次生成边界限制 | 先离线修订分页、读取策略与完整准备预算设计，验证可执行性；不直接同配置重跑、不更改原计划或自动增加次数 |
| 强基线实际调用 | Git checkout、独立私有配置与启动 Git 优先级已准备；`VECTORIZE_API_KEY`、`RERANK_API_KEY` 与固定 `rerank-v3.5` 账户计费/可用性证据尚缺 | 私有凭据及已核验计费依据接入后仍须通过原 B 准入，并有真实可用 parent；不需要用户再处理 Git 许可或 PATH。见[绑定收据](artifacts/native-supplement-01/macos-rawrag-private-binding.json) |
| 全方法任务验收与执行 | 共享 reader、配对调度、工作区和现金控制已有实现，16 个方法单元均未派发，真实四臂比较未发生 | 准备设计与合法运行依据闭合后，仍须按真实相关状态变化、最终行为、等输入与完整计量验收；未用 method 额度不能当作 native 重试许可 |
| 独立标签与测量验证 | v2 程序预审、AI 草案及两套有限 oracle 的参考源码资格已完成；方法最终制品行为与完整语义仍未测量 | 独立绑定封存方法制品后执行评价；正式使用前补齐覆盖、误差与语义依据并冻结所选路线，对未能可靠形式化的争议安排所需复核，不要求先填满 22 张真人表 |
| 正式实验冻结 | 缺少配对 pilot 和完整成本数据；新报告/设计工具的当前输出为未测量 | 冻结方法、预算、价格与分析方案，用实际 pilot 设计样本量，再跑确认及外部验证 |
| 投稿资格与提交 | 缺少完整研究结果与真实作者身份、贡献、利益关系、责任和最终同意记录 | AI 可继续整理文稿及制品；作者提供本人事实并实际复核关键主张，依据届时政策核实资格后批准确切版本与提交 |

本轮具名补充授权已执行完毕，失败记录不重放、不返还；本文件没有提出或激活新批准。当前余项首先是准备阶段的预算与读取策略设计，其次是具体服务材料、科学测量和不可虚构的作者事实与最终责任。可靠的离线核验和文稿工作可继续；本轮没有合并 main、提交预印本或向期刊/会议送稿。
