# P1 投稿准备与暂定目标

**状态：NOT READY — 研究准备文件，不是可投递稿、投稿声明或已完成实验的证明。**

**暂定目标：Transactions on Machine Learning Research（TMLR），标准 PDF 路线。** 状态文档更新于 **2026-11-29（Asia/Shanghai）**。官方模板派生、源码 ZIP、页面 QA 与独立解包重建已完成；当前 canonical 为 26 页，官方 TMLR 格式稿为 27 页。本次仅更新状态叙述，未改写 manuscript、PDF 或 ZIP。科学证据、真实作者贡献与责任仍未闭合，实际投稿未执行。早先版面的检查时间与散列作为历史记录保留在 §4.1。

**本轮四次具名补充 native 授权已执行完毕，原生准备均未成立，不能自动补尝试或改预算。** 实际完成 10 次 DeepSeek 请求，但没有有效 task-bound checkpoint，16 个方法单元均未派发或评分。固定 Git checkout 及独立私有运行绑定已验证，11 包程序预审、37 条 AI-assisted 义务草案及两套有限 oracle 的参考源码资格已完成。22 份旧真人表不是 development 运行的前置条件；这些自动与辅助产物也不是正式 gold。B 仍缺指定服务凭据和固定模型计费依据，正式研究结果仍为 0。最终失败、次数、用量和现金见 [REMAINING_WORK.md](REMAINING_WORK.md)及[机器汇总](artifacts/native-supplement-01/observations.json)。

实际运行、部署、账本镜像和记录导出的完整入口为[补充执行证据索引](artifacts/native-supplement-01/README.md)；后续准备设计的必要约束见 [NATIVE_NEXT_STEP.md](NATIVE_NEXT_STEP.md)，该设计文档本身不改变授权或配置。

## 1. 目标判断

**TMLR 在题材上可以作为有条件的暂定目标，当前稿件尚不具备投递条件。** 研究对象是学习型智能体在原生压缩后怎样使用变化中的证据；若最终给出可复核的行为实验或有明确边界的理论结果，它可对应 TMLR 的方法、智能系统行为分析或复现研究范围。这是根据官方范围作出的匹配判断，不是编辑部的接收承诺。[S1][S2]

目前最大的缺口是结果与研究责任链。现有方法规范、工程回归、12/16 来源资格检查及一次只读原生联调不能支持“D 优于强检索”或“选择性核验降低总成本”；已完成的格式包也不替代这些证据。TMLR 的接受标准要求主张有可信证据，并向相关研究者传达可理解的发现；不要求一定刷新基准，但纯重复实现或缺乏可学习结论的课堂式复现并不自动合格。若完整实验给出负结果或适用边界，应相应收窄主张；不能把结果为空解释为负结果。[S3]

题材尚未显示明显错配，因此本轮保留一个目标，不扩展 venue 清单。**“还不能投稿”与“期刊不适合该题材”是两个判断。** 若真实作者后续确认存在归档会议论文重用、研究范围发生实质变化，或无法满足作者责任要求，应重新做目标判断，而非通过更换期刊绕开这些缺口。

## 2. 截至核验日的官方规则

下表区分官方规则与本项目的准备选择。网页可能更新；投稿日前须再次核对，尤其是表单、临时暂停和作者政策。

| 项目 | 本次核实的规则 / 对本稿的含义 | 来源 |
|---|---|---|
| 收稿节奏 | 全年滚动制，不按单次会议截稿倒排。滚动不保证任意时刻表单开放；本次未确认当前 invitation 状态或 2026 年末临时暂停安排。 | [S1][S4][S8] |
| 页数 | 没有固定页数上限，长度应由内容解释；主文超过 12 页可能采用更长审阅时间。12 页不是拒稿线或接受保证。 | [S4][S5] |
| 标准 PDF 格式 | PDF 路线使用官方 TMLR LaTeX 模板，不通过缩字、改边距或改样式压页。本稿采用这一方案。 | [S5][S6][S7] |
| 其他格式 | 官网另公布 BeyondPDF HTML 方案；不能把标准 PDF 指南概括成“期刊只收 PDF”。本次未核验该方案的完整流程。 | [S1] |
| 匿名 | 审稿稿件及补充材料匿名；全部真实作者仍需在 OpenReview 有有效档案及准确元数据。 | [S5] |
| 附录 / 代码 / 数据 | 附录可放参考文献后，审稿人可自行决定是否阅读。补充材料上限 100 MB，格式 PDF 或 ZIP，同样匿名；鼓励提交复现材料，并非一概强制公开所有数据。 | [S5] |
| 作者 | 实质智力贡献、参与写作/修改、承担责任是作者标准；提交时作者集合必须完整，提交后不得增删。LLM 不能列为作者。 | [S2] |
| 作者额度 | 每位作者均须有足够年度提交额度，包括 desk rejection 也会消耗额度；本团队额度未知。 | [S2] |
| COI / 报告 | OpenReview 档案需真实记录机构与个人冲突；相关政策覆盖近三年的机构/合作关系等。资助、竞争利益及适用的人体研究信息也需如实填报。 | [S2][S5] |
| LLM 辅助 | 允许辅助，但人类作者负责全文。FAQ 另要求首页脚注披露，并期待思想、主张、结果应源于人类，而非由 LLM 生成；不能把广泛 AI 辅助改写成“仅润色”。 | [S2][S4] |
| 预印本 | 允许已公开、署名的预印本；匿名稿不能链接到暴露本人身份的版本。预印本与匿名审稿包应分别处理。 | [S5][S7] |
| 双投 / 重用 | 不接收归档会议论文的扩展版；不得与已发表、已接收或同时送审的归档同行评议论文重用文字、图或结果。公开声明为非归档的 workshop/preprint 情形另按政策处理。 | [S2] |
| 许可 | 投稿论文从提交起适用 CC BY 4.0，作者保留版权；这不替代团队对第三方代码、数据、issue 文本与日志的权利核查。 | [S5] |
| 公开审稿 | 通过初筛进入审阅后稿件公开；撤稿/拒稿通常也保留记录。不要把正式投稿当成私有编辑草稿。 | [S2][S4] |
| 综述 | FAQ 明确自 **2026-09-01** 起不再受理 survey。不能以把未完成方法论文改名综述的方式解决实验缺口。 | [S4] |

**来源之间的边界。** Editorial Policies 仍能看到 survey certification 描述，而 FAQ 有明确日期的停止受理说明；本计划按后者处理新的综述投稿。作者指南写标准 PDF 规则，首页另列 BeyondPDF；本项目选择 PDF，不推断 HTML 的细则。主页检索到的是 2025–2026 跨年的旧暂停公告，不能据此推算 2026–2027 的日期。[S1][S2][S4]

## 3. 当前材料是什么，不能替代什么

本地依据为 [manuscript.md](manuscript.md)、[PROTOCOL.md](PROTOCOL.md)、[EXECUTION.md](EXECUTION.md)、[来源采集](tasks/acquisition/README.md)、[初始程序复现](tasks/reproduction/README.md)、[扩展资格汇总](tasks/reproduction-expansion/summary.json)、[任务材料](tasks/workflows/README.md)及[只读原生联调](artifacts/readonly-native/README.md)。格式与人类贡献材料分别见 [SUBMISSION_PACKAGE.md](SUBMISSION_PACKAGE.md) 和 [CONTRIBUTIONS.md](CONTRIBUTIONS.md)。工程状态仍以各自收据为准；本节只判断它们对论文主张的支持范围。

| 当前材料 | 可支持的说明 | 尚未支持的主张 |
|---|---|---|
| 历史 24 个合成任务 | 有明确便利输入和旧评分边界的开发观察 | 无特权条件下的独立方法效果 |
| 当前实现、分析器和宿主检查 | 特定接口、回归或调用链路的工程性质 | 跨任务成功率、算法增量或可部署可靠性 |
| 16 个来源候选、8 个项目 | 真实 issue/PR、固定来源与重建入口已采集 | 16 个已验收或冻结的 P1 先导工作流 |
| 12/16 来源通过资格检查 | 初始 Flask / Requests 两项加扩展十项；扩展尝试了其余 14 个候选，保留 29 次尝试、34 次顶层测试调用及四项有界限制 | 智能体压缩后决策效果、方法臂得分、12 个正式独立任务 |
| 11 个未验收任务包、22 份空白人工评审包 | 可检查的材料导出、来源绑定与未闭合验收项 | 已冻结 P1 工作流、已经发生的双人标注或裁决 |
| v2 的 11 包程序预审、37 条 AI-assisted 义务草案 | 可重算的材料事实、明确披露来源的开发标签草案、部分确定性组件检查 | 37 个 gold 标签、完整语义覆盖、方法最终制品上的目标行为结果或已验证的正式复合终点 |
| [有限 oracle 的参考源码资格验证](artifacts/remaining-completion-01/oracle-qualification-01/README.md) | Flask 原版与 Requests 明确 URL 格式的 v2 各 5 个真实 pytest 用例，在官方 fixed 上通过、在 base/错误实现上检出失败；15 个 observer、5 个隔离 probe 和 282 份发布记录可复算 | 方法臂得分、完整代理网络行为、证据采用与决策成功或正式预注册。Requests 原六项版的 1 项 fixed 失败保留，v2 为看过参考结果后的开发修订 |
| 固定归档证据上的只读原生联调 | 5 次 generation starts、1 次真实 native compaction、3 个相同压缩父会话的分叉；A/C/D 均建议 hold | 独立自然任务效果、可变工作区端到端闭环、强 Raw-RAG 比较或非劣效结论 |
| 同一 test-result 命题的 C/D 记录 | C 打开 2 条原文，D 复用后新打开 0 条；完整证据包相同，C/D 均为 15,350 input tokens | 模型 token 节省、完整成本下降或一般性性能优势 |
| 四次补充 native 的真实执行 | 两次 `w-101` 在 provider 前失败；两个 `w-102` 各完成 5 次 provider 请求及 7 次只读公共工具调用，随后触及累计输入上限，生成次数也已用尽；全部 backend 已关闭 | 有效 task-bound checkpoint、方法最终制品、任何 A/B/C/D 得分或原生准备成功；不能从未用方法额度或现金余量推导重试许可 |
| 官方格式 PDF、源码 ZIP 与 QA | 固定官方样式可编译；项目外解包重建的逐页文字、尺寸和渲染像素一致 | 科学研究复现完成、人类匿名审查完成或已经投稿 |
| 当前主结果表 | 预先陈述将测量什么 | 实测效应、置信区间、H1/H2、完整成本结论 |

上述候选尚无已验收冻结的研究工作流，22 份旧评审包均未填，已完成的人类独立评审数为 0。后续 [development-assurance v2](ANNOTATION_V2.md) 已替代开发阶段普遍等待固定双真人/第三人表单的流程依赖；human-v1 的记录要求本身未被放宽，AI 记录不能冒充它。正式使用程序或 AI 辅助标签前仍需验证独立真值依据、覆盖和误差，并冻结相应合同。只读联调没有运行强 Raw-RAG B，也没有执行可变工作区测试；其缓存、compaction 和成本边界仍保持原记录。`PENDING` 是未测量，不能换成 0、成功或“趋势”。论文主张应由实际研究证据决定。

**审批宿主的边界。** 原批准批次中，Codex 0.153.0 的实际 `run_current_tests` 和 `record_decision` 一次性审批与后续工具执行已有收据，来源为 `prior_chat_authorization`，不声称新的真人点击或持久授权。原两次 native 已消耗；第 2 次最后的 changed-state 决定超时，完整集成 checks 为 null。随后另行批准的四次 task-bound 准备也全部结束并消耗：两个 `w-101` 在 provider 前失败；两个 `w-102` 各完成 5 次生成和 7 次只读公共工具调用，无 write/test/review，第 6 请求由本地 relay 在 provider 派发前以 `scope_reference_input_budget_exhausted` 拒绝。65,536 的累计 reference-input 边界与 5 次 generation_start 边界同时限制后续进度；仅放宽输入不能续跑。没有有效 checkpoint、没有方法调用或评分。旧失败不回填成功，不能自动重放、返还或新增次数。具体边界见 [APPROVALS.md](APPROVALS.md)、[原批次记录](artifacts/authorized-batch1/README.md)、[NATIVE_SUPPLEMENT.md](NATIVE_SUPPLEMENT.md)及[最终观察](artifacts/native-supplement-01/observations.json)。

一次固定合成输入的 [DeepSeek 抽取诊断](artifacts/deepseek-live-01/README.md)已经完成，但未增加研究任务或方法运行。新增[评分](SCORING.md)、[报告](REPORTING.md)及[设计分析](DESIGN_ANALYSIS.md)工具有离线复核入口；当前[真实空结果报告](artifacts/remaining-completion-01/reporting/README.md)仍为 **NOT MEASURED**，不提供科学效果或正式 N。

## 4. 当前工作稿与已完成的官方格式包

### 4.1 本次检查到的版本

两种格式均已实际构建、渲染和检查，版本事实如下：

| 文件 | 当前版面 | PDF SHA-256 |
|---|---|---|
| [Canonical manuscript.pdf](manuscript.pdf) | **26 页 A4**；标题、摘要与主文第 1–21 页；参考文献第 22 页；附录第 23–26 页 | `0f9a5b0807f50939025a9b2e73c9e4ba4f4c6ec629ef4aa272e0e82efd1e2c95` |
| [官方 TMLR main.pdf](submission/tmlr-review/main.pdf) | **27 页 US Letter**；正文截至第 20 页；参考文献第 21–22 页；附录第 23–27 页 | `1cedfed3e276e8993ef46745c1af03626610c04ac5fa95a717b80e63f3084db8` |

官方稿使用 commit `7bf90efe3a0debbba703c05c43f3ff7e4d4a2992` 的默认 review 样式；官方文件原字节已核验，没有使用 `accepted` 或 `preprint`。首页显示 **NOT READY — NOT SUBMITTED**，解释模板固定 review 标签，并以脚注明确披露实质性 AI 辅助和未解决的人类来源条件。[S7]

[review-source.zip](submission/review-source.zip) 为文档源码包，含 22 个成员，压缩后 462,960 bytes，SHA-256 为 `c421382e189a0e0ab3333032998e26263e1d1644f5028223fa1d48b65764288b`。它已在项目目录之外解包并实际重编；27 页文字、尺寸和渲染像素全部相同，PDF 创建元数据导致字节散列不同。它没有被当作完整科学复现制品。

两份 PDF 均保留 16 条参考文献和 56 个 `PENDING`；没有未解析引用、缺字、行溢出或未解决的重编译请求。Canonical 与官方稿分别有 8 和 0 个非致命 underfull 警告。既有 QA 记录保留全页 110 dpi 渲染和逐页 AI 视觉检查；本次仅重新核对现有文件页数、分节与摘要，未重建 PDF。构建命令、样式来源、QA 及独立重建收据见 [BUILD.md](BUILD.md)、[SUBMISSION_PACKAGE.md](SUBMISSION_PACKAGE.md)、[canonical-qa-report.json](submission/canonical-qa-report.json)、[qa-report.json](submission/qa-report.json) 和 [zip-rebuild-report.json](submission/zip-rebuild-report.json)。机械匿名筛查或 AI 视觉检查通过不等于人类匿名审查完成。

**历史检查记录，非当前版本：** 2026-11-28 Asia/Shanghai（UTC+08:00）08:58 左右首次核对网页规则，09:00 检查的 canonical 为 24 页（主文截至 19 页、参考文献第 20 页、附录第 21–24 页）。该旧 PDF SHA-256 为 `b49157afe45dee02aa9d1a4a469f205466ecace8442febb2a798e39a3134aa2e`，旧 Markdown SHA-256 为 `e472ca2d2883d6c177c84398efbb694754d5d5e11991aa83e288d47855a99ca6`。这组时间和散列只标识早先检查点。

因此无需为一个不存在的“总计 12 页硬上限”删去必要证据。**本项目的编辑目标是主文约 10–12 页，参考文献与附录另计**，以便把读者注意力放到可验证发现；这是编辑选择，不是期刊规定，也不是在结果出来前锁死篇幅。

### 4.2 内容重组

| 当前部分 | 投递版处理 | 目的 |
|---|---|---|
| 首页状态说明与计划式摘要 | 工作稿继续保留；投递版另写由真实结果支持的一段摘要；保留已有实质 AI 使用披露，仅按真实后续记录更新 | 不把研究计划包装成完成研究 |
| §1–2 动机及相关工作 | 集中说明与强 Raw-RAG、TierMem / sufficiency 路由及 provenance/governance 的差异，保留一张关键比较表 | 避免把“选择性重开”本身声称为新意 |
| §3–4 问题与方法 | 主文保留可见性边界、类型语义、完整覆盖与 freshness 的区别、复用条件、算法和关键假设 | 必要推理不能藏到审稿人可不看的附录 |
| §5 旧开发和工程材料 | 主文用短段说明证据层次；旧 24 题、宿主日志、12/16 来源资格与未验收任务包详情放附录/制品 | 避免开发记录占据主结果位置 |
| §6 计划实验 | 完成后改写为实际执行的设计；明确冻结时间、偏离、任务家族与全部失败 | 计划不能充当执行证据 |
| §7 空结果表 | 用封存运行重新生成；没有执行的比较明确移除或标为未来工作，不填推测数字 | 每个结果都能追溯到分母和原始记录 |
| §8 条件式讨论、§9–11 | 围绕真实正/负结果写边界，整合重复限制；保留授权模拟、成本未知和外部效度限制 | 得出与数据匹配的结论 |
| 附录 A–D | 保留必要形式化/复现细节；采集流水账、源码检查记录移到版本化制品 | 附录支持主文，主文自身仍能被评审 |

一个可调整的主文分配是：动机/相关工作约 2 页；问题与方法约 3 页；设计约 2 页；结果与机制分析约 2–3 页；讨论、限制与复现约 1–2 页。结果的必要解释优先于这个排版预算。

当前官方派生稿已使用默认审稿选项，并完成逐页检查；canonical 的自定义页眉、边距和字体没有带入该稿。`accepted` 用于录用后，`preprint` 用于相应公开预印本。未来科学内容更新仍须重新生成并检查公式、表格、参考文献、匿名信息和 PDF metadata。[S6][S7]

## 5. 投递前必须闭合的 ready gates

这些是**本项目针对当前主张的验收要求**，不是声称 TMLR 规定了 16 个任务、22 份真人表、3% 界限或某个统计模型。开发运行不必等齐投稿关卡，但本轮原生准备次数已经耗尽；未用方法额度和剩余现金不产生新的原生许可。程序核验、AI 辅助起草与复算可继续进行；涉及本人事实和最终责任的 unknown 必须由实际作者如实提供。

| Gate | 当前状态 | 闭合时必须有的证据 / 负责人 |
|---|---|---|
| G1 真实作者与研究责任 | **UNKNOWN / BLOCKED**：真实作者、机构、作者顺序和可归属的人类智力贡献未确认 | 每名拟作者的真实身份、具体工作记录、全文审查和共同同意；核对思想、主张、结果的真实来源及实际人类研究贡献是否满足 human-sourced 期待；不能仅凭人工选择、复核、承担责任或签字推定满足，也不能用 AI 草拟的贡献声明替代。 |
| G2 通讯与投稿账户 | **UNKNOWN** | 明确实际负责沟通的人及邮箱、OpenReview 有效档案、每名作者额度。通讯联系人是项目组织要求；当前表单是否另有独立 corresponding-author 栏位尚未核实，不能填猜测信息。 |
| G3 无特权的真实工作流 | **BLOCKED**：16 个来源候选中 12 个通过资格检查；11 个任务包均未验收，冻结 P1 工作流为 0；四次补充 native 均无有效 checkpoint，次数已耗尽 | 先离线修订读取策略及完整准备的输入/生成预算设计，不直接同配置重跑或改原计划。未来实际开发与独立先导仍须有合法运行依据、真实 prelude、相关状态变化、native compaction、后续行动及完整失败台账；物理分离 public/controller/evaluator。 |
| G4 独立标签与测量合同 | **PARTIAL DETERMINISTIC VALIDATION COMPLETE / FORMAL VALIDATION PENDING**：11 包预审、37 条 AI-assisted 草案及两套有限 oracle 的参考源码资格已完成；方法最终制品行为、完整语义和复合终点仍未测量 | 将已验证的有限 oracle 独立绑定到封存方法制品，保留原版失败与开发修订；正式使用前补齐所选人类、程序或 AI 辅助标签路线的独立真值、接触史、覆盖、误差、分歧和版本冻结。若选 human-v1，继续遵守其双审/裁决合同；AI 草案或 SWE-bench 原标签不能直接改称完整 gold，开发执行无需先填完 22 张表。 |
| G5 公平、强且近邻的对照 | **BLOCKED FOR FULL COMPARISON**：B 的固定 Git checkout、独立私有绑定与启动 Git 优先级已准备；指定 embedding/rerank 凭据及固定 `rerank-v3.5` 计费/可用性证据尚缺。本轮 A/C/D 也因无父检查点而未派发 | 支持保留主张的实际比较仍须有合法可用 parent 与完整准入；验证 B 的 faithful `original_request` 配置和实际 dense/rerank，C/D 共用核心。保留 B 缺席与四臂分母，不以开发部分观察声称胜过强 B；无需用户再修 Git/PATH。新对照若纳入须明确实现并另行冻结设计。 |
| G6 完整效果与统计 | **BLOCKED**：当前结果为 PENDING | 冻结 manifest、任务级分母、replicate 聚合、项目依赖处理和区间方案；依据独立先导论证正式样本与 H2 界限；完成计划比较、失败保留及独立复算。负结果可闭合此 gate；不能要求先看到正结果再决定样本。 |
| G7 成本及主张边界 | **BLOCKED** | 若保留 H2，须冻结全流水费率/分摊并保留失败成本，按 H1→H2 层级解释。费率或费用缺失写 unknown，不补零；不能以搜索次数替代成本。若证据不足，删除优势主张并明确报告限制。 |
| G8 作者科学复核与责任 | **NOT RECORDED** | 程序和 AI 可完成引用查证、代码审查、复算与异常整理；责任作者须实际检查关键主张及其证据、理解适用范围并确认最终内容。对无法可靠形式化的关键争议安排具备相应能力的复核，记录范围、发现及处理；不预设另找固定人数的外部真人，也不能用一般签名代替实际核查。 |
| G9 COI、资助、伦理与来源许可 | **UNKNOWN / BLOCKED** | 每位作者真实 COI 与资助记录；确定标注/参与者安排是否需相应伦理审查并记录判断。逐项审核上游文本、代码、日志和身份信息；不得把“网上可读”视为全部可再分发。 |
| G10 重用、匿名与制品 | **UNKNOWN / BLOCKED** | 所有相关论文/预印本/归档投稿的重叠清单；匿名审稿包与公开仓库版本分开；完成可从记录重算的制品快照及合法发布范围。必要的第三方许可通知须保留，不能为匿名而删除。 |
| G11 格式与文档复现 | **COMPLETE（工作稿格式范围）** | 官方 pin、27 页默认 review 稿、首页实质性 AI 脚注、文档源码 ZIP、引用/占位检查、页面 QA 与项目外独立重建均有记录；不包含研究完成、人类匿名审查或实际投递。 |
| G12 最终作者批准与实际投递 | **NOT READY / NOT PERFORMED** | 完成其他研究与人类责任 gates，核对当天规则、真实账户与表单，完成科学补充材料和所有声明；最后由真实作者批准确切版本及投递。现有格式稿和 ZIP 不是已获批准的最终研究稿。 |

G1/G8 需要实际事实和责任记录。当前工作稿已说明 AI 参与文献检查、方法表述与英文写作；后续还有实现审查、来源采集、程序复现和明确披露的开发标签草案，应据实保留。官方政策允许 LLM 辅助并要求作者负责，FAQ 仍保留 human-sourced 的思想、主张和结果期待；本项目不能自行将其解释为已被豁免，也不能用事后签字或改写披露证明来源条件已满足。已查政策没有逐任务两位真人或 22 张表的固定要求；这是对政策范围的判断，不是期刊对本自动评价路线的预先认可。[S2][S3][S4]

人工标注的安排、公开 issue 中的人类信息以及未来数据使用都需要具体判断。伦理审查是否适用目前为 unknown；不得虚构“IRB approved”，也不自动把所有代码任务宣称为必须或无需 IRB。保留受限动作的本地模拟边界并解释适用风险。[S9]

## 6. 实际准备顺序

1. **先处理准备阶段的设计与证据缺口。** 四次补充执行已结束，不再重放已消费 scope。用真实请求和工具轨迹离线修订分页、读取与完整准备所需的输入/生成预算设计，保留原 [PROTOCOL.md](PROTOCOL.md)、计划、授权及失败记录，不把新次数或改预算写成已获批准。B 的私有绑定已完成，服务凭据与固定计费证据仍需闭合；后续真实比较还须有合法可用的 parent。正式样本不足时收窄问题及主张，不把开发测试混入正式 N。
2. **同步建立作者事实与来源记录。** AI 继续整理 author/contribution、AI assistance、COI/funding、related-work overlap 和许可材料；真实作者提供本人事实并实际履行 G1/G2/G8/G9 中的责任。无需让作者代做已经能可靠自动完成的逐文件机械检查，未知个人事实仍保持 unknown。
3. **锁定科学叙述。** 用同一封存记录重算所有表图，决定可支持的正、负或边界结论；全文主张与结果逐项相连，单独报告来源资格与工程检查。
4. **维护两种格式，补齐科学制品。** Canonical 与官方 TMLR 派生稿、文档源码包已完成；研究更新后从同一来源重新派生。完整科学补充包仍需冻结。公开仓库/预印本不必撤回，但审稿包须按匿名规则处理，不直接放暴露作者身份的版本链接。[S5]
5. **完成科学制品与投递前复核。** 文档的项目外独立重建已经通过；继续核查科学复算入口、完整材料、匿名性、链接、许可和实际表单字段，由作者实际确认最终审稿包。不向 OpenReview 创建“试投”。附录中才出现的关键论证移回主文。
6. **最后由真实作者核对。** 确认作者集合、责任、元数据、年度额度和当天规则，再批准确切 PDF/补充文件的摘要。此准备任务到此为止；没有发起投稿、联系编辑或发送邮件。

正式表单可从 [OpenReview TMLR](https://openreview.net/group?id=TMLR) 进入；本次公开页面只返回加载界面，未核验登录后所有栏位。不要据此宣称当前表单可投、账户有资格、额度充足或某栏目必填。[S8]

## 7. 投稿说明 / 披露骨架（不可投递）

**INTERNAL PLACEHOLDER — NOT FOR SUBMISSION.** 下面保留整理信息用的字段骨架；已有更完整的 [COVER_LETTER.md](submission/COVER_LETTER.md) 和 [CONTRIBUTIONS.md](CONTRIBUTIONS.md)，均未发送，也未虚构作者事实。这不表示 TMLR 必须提供 cover letter；实际栏目待最后核对。

```text
Title: [最终、与已完成研究匹配的标题]
Human authors / affiliations / OpenReview IDs: UNKNOWN — 尚待真实作者确认
Corresponding project contact: UNKNOWN — 姓名、邮箱、职责尚待确认
Verified intellectual contributions: [逐人记录实际工作；不得从 AI 草稿倒推]

Scientific question: [人类作者确认的范围与可证伪问题]
Completed evidence: BLOCKED — 当前无 P1 配对方法效应与确认性结果
Claims supported by those records: [只在实测与复核完成后填写]
Claims removed or limited: [按真实结果填写，不隐藏负结果]

Related prior / parallel archival submissions: UNKNOWN
Preprints / public artifacts and anonymous review package: [确切版本及处理]
Funding / competing interests / COI: UNKNOWN
Label/oracle version, validation and unresolved adjudication: NOT FROZEN FOR FORMAL STUDY
Human participant involvement / applicable ethics determination: [按实际采用的方法如实记录]
Data and code rights / reproducibility access: [实际完成的许可与访问方式]

AI assistance record: [工具、版本、日期、实际用途、范围、人工检查记录]
Human final approval of all content and author list: NOT RECORDED
Current format-draft PDF and document-source ZIP SHA-256: recorded in Section 4.1
Author-approved final study manuscript and scientific supplement: NOT FROZEN
```

官方格式稿首页现有 AI 脚注披露了文献与来源检查、方法和协议表述、英文起草、代码实现与审查、测试、来源采集和文档准备，并明确这些参与不限于语言润色、人类来源条件未解决。准确原文与逐项证据表在 [CONTRIBUTIONS.md](CONTRIBUTIONS.md)。哪些环节经谁独立核验仍须据实补齐。**在人工核验完成前，不能追加‘所有内容已由作者验证’；不能写成仅语法修订；不能把 AI 列为作者。** 匿名稿可以披露工具和用途而不暴露团队身份。[S2][S4]

## 8. 官方一手来源与检索日期

以下来源最初于 **2026-11-28（Asia/Shanghai）**实际读取或通过官方仓库只读接口核对。本次于 **2026-11-29（Asia/Shanghai）**重新打开 S2、S3、S4，核对 LLM 辅助、作者责任、human-sourced 期待及证据标准；其余条目仍对应原核验记录，不宣称已重新检查投稿表单。日期是核验日期，不假称政策有发布日期或固定版本号。提交前重新访问。

- **[S1] TMLR 首页（目标、rolling、BeyondPDF、公告）：** https://www.jmlr.org/tmlr/index.html
- **[S2] Editorial Policies（scope、双投/重用、作者、LLM、COI、额度）：** https://www.jmlr.org/tmlr/editorial-policies.html
- **[S3] Acceptance Criteria（主张/证据、受众兴趣、复现和 AI 内容）：** https://www.jmlr.org/tmlr/acceptance-criteria.html
- **[S4] FAQ（全年滚动、>12 页、LLM 首页脚注、2026-09-01 综述规则）：** https://www.jmlr.org/tmlr/faq.html
- **[S5] Author Guidelines（匿名、长度、PDF、补充、CC BY、预印本）：** https://www.jmlr.org/tmlr/author-guide.html 。许可与署名预印本链接限制位于页面末尾的版权/许可段；提交前再次通过网页抽取及直接 HTTPS 200 响应核对，原始 HTML SHA-256 为 `117ed02f6791f8167c861560a36d6efe3f12811a55ed416b84c4bf4c483055f1`。
- **[S6] Submission Instructions（标准模板及 OpenReview 流程）：** https://www.jmlr.org/tmlr/submissions.html
- **[S7] 官方模板仓库与本次核验的 main.tex：** https://github.com/JmlrOrg/tmlr-style-file ；https://github.com/JmlrOrg/tmlr-style-file/blob/7bf90efe3a0debbba703c05c43f3ff7e4d4a2992/main.tex
- **[S8] 官方投稿入口（动态表单未核验）：** https://openreview.net/group?id=TMLR
- **[S9] Ethics Guidelines（数据、隐私、同意、监督与风险讨论）：** https://www.jmlr.org/tmlr/ethics.html

本轮仅更新状态与投稿关卡叙述，使其与已完成的格式包、已激活授权、v2 预审及实际失败收据一致；未修改正文或 PDF，未填写未知作者事实，也未执行投稿、联系编辑或发送信件。剩余待作者本人提供的事项是身份/机构/贡献和利益关系等真实事实、对研究内容的实际复核与责任、账户资格及最终确切版本的投递同意；不是重复确认既有执行授权或补填 22 份虚构真人表。
