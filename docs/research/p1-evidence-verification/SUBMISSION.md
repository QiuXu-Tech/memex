# P1 投稿准备与暂定目标

**状态：NOT READY — 研究准备文件，不是可投递稿、投稿声明或已完成实验的证明。**

**暂定目标：Transactions on Machine Learning Research（TMLR），标准 PDF 路线。** 更新日期为 **2026-11-28**。官方模板派生、源码 ZIP、页面 QA 与独立解包重建已完成；当前 canonical 为 25 页，官方 TMLR 格式稿为 26 页。科学证据、人类来源与作者责任仍未闭合，实际投稿未执行。早先 24 页检查的时间与散列作为历史记录保留在 §4.1。

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
| 固定归档证据上的只读原生联调 | 5 次 generation starts、1 次真实 native compaction、3 个相同压缩父会话的分叉；A/C/D 均建议 hold | 独立自然任务效果、可变工作区端到端闭环、强 Raw-RAG 比较或非劣效结论 |
| 同一 test-result 命题的 C/D 记录 | C 打开 2 条原文，D 复用后新打开 0 条；完整证据包相同，C/D 均为 15,350 input tokens | 模型 token 节省、完整成本下降或一般性性能优势 |
| 官方格式 PDF、源码 ZIP 与 QA | 固定官方样式可编译；项目外解包重建的逐页文字、尺寸和渲染像素一致 | 科学研究复现完成、人类匿名审查完成或已经投稿 |
| 当前主结果表 | 预先陈述将测量什么 | 实测效应、置信区间、H1/H2、完整成本结论 |

上述候选尚无已验收冻结的 P1 工作流，22 份评审包均未填，已完成的人类独立评审数为 0。只读联调没有运行强 Raw-RAG B，也没有执行可变工作区测试；缓存输入子项不同，compaction 计量仍有缺口，actual spend 与完整标准化成本保持 null。`PENDING` 是未测量，不能换成 0、成功或“趋势”。论文是否最终主张优势，应由完成的研究记录决定，而不是投稿目标决定。

**审批宿主的边界。** 已批准批次中，Codex 0.153.0 的实际 `run_current_tests` 和 `record_decision` 一次性审批与后续工具执行已有收据，来源为 `prior_chat_authorization`，不声称新的真人点击或持久授权。两次 native 额度均已消耗；第 2 次最后的 changed-state 决定超时，完整集成 checks 为 null。先前阻断记录继续保留，局部通过也不证明完整可变工作流或跨宿主兼容性。[APPROVALS.md](APPROVALS.md) 与[本批原始记录](artifacts/authorized-batch1/README.md)保留具体边界。

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

这些是**本项目针对当前主张的验收要求**，不是声称 TMLR 规定了 16 个任务、3% 界限或某个统计模型。所有 unknown 都需要真实资料；此文件不要求现在重复确认公开授权。

| Gate | 当前状态 | 闭合时必须有的证据 / 负责人 |
|---|---|---|
| G1 真实作者与研究责任 | **UNKNOWN / BLOCKED**：真实作者、机构、作者顺序和可归属的人类智力贡献未确认 | 每名拟作者的真实身份、具体工作记录、全文审查和共同同意；核对思想、主张、结果的真实来源及实际人类研究贡献是否满足 human-sourced 期待；不能仅凭人工选择、复核、承担责任或签字推定满足，也不能用 AI 草拟的贡献声明替代。 |
| G2 通讯与投稿账户 | **UNKNOWN** | 明确实际负责沟通的人及邮箱、OpenReview 有效档案、每名作者额度。通讯联系人是项目组织要求；当前表单是否另有独立 corresponding-author 栏位尚未核实，不能填猜测信息。 |
| G3 无特权的真实工作流 | **BLOCKED**：16 个来源候选中 12 个通过资格检查；11 个任务包均未验收，冻结 P1 工作流为 0 | 完成开发与独立先导包；真实 prelude、相关状态变化、native compaction、后续实际行动及完整失败台账；物理分离 public/controller/evaluator。受控轨迹与自然工作部分逐项标明。 |
| G4 人工标注与裁决 | **BLOCKED**：22 份评审包为空，已完成人类独立评审为 0 | 至少两名具备能力的人独立标注关键状态、义务和证据等价规则，记录盲法、分歧与裁决。LLM 标签或 SWE-bench 原标签不替代该项；`[100%]` 进度伪标签等来源缺陷先修正并留账。 |
| G5 公平、强且近邻的对照 | **BLOCKED** | 冻结并实际运行 A/B/C/D；验证 B 的 faithful `original_request` 配置和实际 dense/rerank；C/D 共用核心；决定 TierMem 忠实复现或清楚命名的独立 sufficiency 对照，并重新冻结预算。 |
| G6 完整效果与统计 | **BLOCKED**：当前结果为 PENDING | 冻结 manifest、任务级分母、replicate 聚合、项目依赖处理和区间方案；依据独立先导论证正式样本与 H2 界限；完成计划比较、失败保留及独立复算。负结果可闭合此 gate；不能要求先看到正结果再决定样本。 |
| G7 成本及主张边界 | **BLOCKED** | 若保留 H2，须冻结全流水费率/分摊并保留失败成本，按 H1→H2 层级解释。费率或费用缺失写 unknown，不补零；不能以搜索次数替代成本。若证据不足，删除优势主张并明确报告限制。 |
| G8 人类独立复核 | **BLOCKED** | 真实研究者复核关键引用、方法正确性、所有主结果和异常；由能理解实现与统计的人检查代码/日志；说明审查人、范围、发现及处理。一般签名不能替代实际核查。 |
| G9 COI、资助、伦理与来源许可 | **UNKNOWN / BLOCKED** | 每位作者真实 COI 与资助记录；确定标注/参与者安排是否需相应伦理审查并记录判断。逐项审核上游文本、代码、日志和身份信息；不得把“网上可读”视为全部可再分发。 |
| G10 重用、匿名与制品 | **UNKNOWN / BLOCKED** | 所有相关论文/预印本/归档投稿的重叠清单；匿名审稿包与公开仓库版本分开；完成可从记录重算的制品快照及合法发布范围。必要的第三方许可通知须保留，不能为匿名而删除。 |
| G11 格式与文档复现 | **COMPLETE（工作稿格式范围）** | 官方 pin、27 页默认 review 稿、首页实质性 AI 脚注、文档源码 ZIP、引用/占位检查、页面 QA 与项目外独立重建均有记录；不包含研究完成、人类匿名审查或实际投递。 |
| G12 最终作者批准与实际投递 | **NOT READY / NOT PERFORMED** | 完成其他研究与人类责任 gates，核对当天规则、真实账户与表单，完成科学补充材料和所有声明；最后由真实作者批准确切版本及投递。现有格式稿和 ZIP 不是已获批准的最终研究稿。 |

其中 G1/G8 尤其不能通过美化措辞解决。当前工作稿已说明 AI 参与文献检查、方法表述与英文写作；本轮又有 AI 协助实现审查、来源采集和程序复现。应建立实际使用与人类复核记录。FAQ 的 human-sourced 期待是思想、主张、结果源于人类，而非由 LLM 生成；它不等同于事后由人类负责。当前真实研究贡献是否满足该要求仍须按来源事实核对，不能以签字或修改披露措辞替代。占位的人类贡献或尚未发生的审查也不能写成事实。[S2][S3][S4]

人工标注的安排、公开 issue 中的人类信息以及未来数据使用都需要具体判断。伦理审查是否适用目前为 unknown；不得虚构“IRB approved”，也不自动把所有代码任务宣称为必须或无需 IRB。保留受限动作的本地模拟边界并解释适用风险。[S9]

## 6. 实际准备顺序

1. **先完成研究证据。** 按 [PROTOCOL.md](PROTOCOL.md) 执行 G3–G7，冻结变更和偏离。正式样本不足时收窄问题及主张，而不是把开发测试混入正式 N。
2. **同步建立人类责任与来源记录。** 由真实作者处理 G1/G2/G8/G9；建立 author/contribution、AI assistance、COI/funding、related-work overlap 和许可台账。未知项保持 unknown。
3. **锁定科学叙述。** 用同一封存记录重算所有表图，决定可支持的正、负或边界结论；全文主张与结果逐项相连，单独报告来源资格与工程检查。
4. **维护两种格式，补齐科学制品。** Canonical 与官方 TMLR 派生稿、文档源码包已完成；研究更新后从同一来源重新派生。完整科学补充包仍需冻结。公开仓库/预印本不必撤回，但审稿包须按匿名规则处理，不直接放暴露作者身份的版本链接。[S5]
5. **完成科学制品与投递前复核。** 文档的项目外独立重建已经通过；后续还须核查科学复算入口、完整材料、人工匿名审查、链接、许可和实际表单字段，不向 OpenReview 创建“试投”。附录中才出现的关键论证移回主文。
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
Human annotation / adjudication / applicable ethics determination: UNKNOWN
Data and code rights / reproducibility access: [实际完成的许可与访问方式]

AI assistance record: [工具、版本、日期、实际用途、范围、人工检查记录]
Human final approval of all content and author list: NOT RECORDED
Current format-draft PDF and document-source ZIP SHA-256: recorded in Section 4.1
Author-approved final study manuscript and scientific supplement: NOT FROZEN
```

官方格式稿首页现有 AI 脚注披露了文献与来源检查、方法和协议表述、英文起草、代码实现与审查、测试、来源采集和文档准备，并明确这些参与不限于语言润色、人类来源条件未解决。准确原文与逐项证据表在 [CONTRIBUTIONS.md](CONTRIBUTIONS.md)。哪些环节经谁独立核验仍须据实补齐。**在人工核验完成前，不能追加‘所有内容已由作者验证’；不能写成仅语法修订；不能把 AI 列为作者。** 匿名稿可以披露工具和用途而不暴露团队身份。[S2][S4]

## 8. 官方一手来源与检索日期

以下来源均于 **2026-11-28（Asia/Shanghai）**实际读取或通过官方仓库只读接口核对。日期是本次核验日期；除页面明确给出的生效日期外，不假称政策有发布日期或固定版本号。提交前重新访问。

- **[S1] TMLR 首页（目标、rolling、BeyondPDF、公告）：** https://www.jmlr.org/tmlr/index.html
- **[S2] Editorial Policies（scope、双投/重用、作者、LLM、COI、额度）：** https://www.jmlr.org/tmlr/editorial-policies.html
- **[S3] Acceptance Criteria（主张/证据、受众兴趣、复现和 AI 内容）：** https://www.jmlr.org/tmlr/acceptance-criteria.html
- **[S4] FAQ（全年滚动、>12 页、LLM 首页脚注、2026-09-01 综述规则）：** https://www.jmlr.org/tmlr/faq.html
- **[S5] Author Guidelines（匿名、长度、PDF、补充、CC BY、预印本）：** https://www.jmlr.org/tmlr/author-guide.html 。许可与署名预印本链接限制位于页面末尾的版权/许可段；提交前再次通过网页抽取及直接 HTTPS 200 响应核对，原始 HTML SHA-256 为 `117ed02f6791f8167c861560a36d6efe3f12811a55ed416b84c4bf4c483055f1`。
- **[S6] Submission Instructions（标准模板及 OpenReview 流程）：** https://www.jmlr.org/tmlr/submissions.html
- **[S7] 官方模板仓库与本次核验的 main.tex：** https://github.com/JmlrOrg/tmlr-style-file ；https://github.com/JmlrOrg/tmlr-style-file/blob/7bf90efe3a0debbba703c05c43f3ff7e4d4a2992/main.tex
- **[S8] 官方投稿入口（动态表单未核验）：** https://openreview.net/group?id=TMLR
- **[S9] Ethics Guidelines（数据、隐私、同意、监督与风险讨论）：** https://www.jmlr.org/tmlr/ethics.html

早先版本只建立了投稿准备计划。本轮仅更新本文件，使其与已经完成的格式包及当前收据一致；未修改正文或 PDF，未填写未知作者事实，也未执行投稿、联系编辑或发送信件。
