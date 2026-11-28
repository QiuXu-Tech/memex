# 第 1 批授权执行记录

日期：2026-11-28（Asia/Shanghai）。本批依据用户对统一审批单的“全部批准”执行，范围见 [BATCH1.md](../../BATCH1.md) 与 [authorization.json](authorization.json)。公开研究分支授权继续有效。

## 已实际到达的阶段

本批已打通真实宿主的两种目标工具调用：`run_current_tests` 和 `record_decision`。宿主实际发出一次性 MCP elicitation，客户端依据已经记录的会话授权回应 `accept`，随后工具实际执行。审计来源为 `prior_chat_authorization`，`identityAttested=false`；没有新的真人点击声明或持久授权。

两次原生尝试均已结束并保留为超时。第二次完整走过真实测试、模型抽取、两次原生压缩、未变化证据复用、旧版本收据拒绝及第一次模拟决定；最后一次状态变化后的决定未完成。因此 **完整集成检查没有通过，正式方法比较仍未执行**。

| 项目 | native-01 | native-02 |
|---|---:|---:|
| 控制器开始的生成 turn | 1 | 5 |
| 完成的生成 turn | 0 | 4 |
| 完成的原生压缩 | 0 | 2 |
| 实际一次性审批响应 | 0 | 2 |
| 实际固定测试收据 | 0 | 1，passed |
| 实际模拟决定 | 0 | 1，release |
| 记录的运行时间 | 125.473 秒 | 480.037 秒 |
| 结束位置 | prelude 等待超时 | changed_decision 总时限到达 |

两个进程均退出为 1。native-01 保留响应流重连、请求超时和截止前出现的 reasoning item 类型记录；没有保存 reasoning 内容。native-02 将单次协议等待上限从 120 秒延长为 180 秒，整体控制器仍限 480 秒。重试理由单独记录在 [native-02-rationale.json](native-02-rationale.json)。本批原生尝试名额 **2/2 已使用**，没有新增第三次尝试。

## 第二次尝试的可核对观察

- 初始真实测试通过，生成唯一的当前版本测试收据；稳定状态的模拟 `release` 引用了该收据，未发生外部发布。
- 首次核验打开一次原文；稳定状态后续核验复用已核验收据，原文打开数为 0，但仍有视图读取和证据传递。
- 控制器改变了指定源文件字节；之后核验再次打开原收据一次，以 `version_mismatch` 拒绝将旧的通过结果用于当前版本。
- 两次实际模型抽取各产生一个被接受的 test claim；其他两个不受支持的 claim 保持 unknown，覆盖完整性仍未建立。
- 最后一个决定 turn 在约 471.35 秒开始，480 秒时限到达时未完成。没有观察到新失败测试收据，也没有观察到后续 `hold` 决定。原始 `checks` 与最终 `metrics` 保持 null；派生观察不替代这些未完成检查。

这些事实见 [observations.json](observations.json)、[native-02/summary.json](native-02/summary.json)、[宿主事件](native-02/main-host/events.jsonl)和[模拟决定](native-02/broker/decisions.jsonl)。同一方便构造的开发工作流不增加正式研究的独立任务数；本批没有质量优越性、token 节省或成本节省估计。

## 两份真实 Python 公开来源

新增 controller-only 开发采集器，针对固定公开 base 的原有测试执行真实 Python/pytest 进程，记录前后源码/依赖摘要、导入来源、退出码、标准输出/错误及逐测试阶段事件。

| 来源 | 原有公开测试 | collected | passed | skipped | 进程退出 |
|---|---|---:|---:|---:|---:|
| w-101，Flask | tests/test_blueprints.py | 59 | 59 | 0 | 0 |
| w-102，Requests | tests/test_utils.py | 212 | 201 | 11 | 0 |

原公开目录、执行副本和依赖树的前后摘要一致。没有安装/升级依赖，没有模型或供应商 API 请求，没有提供官方未来修复/回归测试补丁。这解释了它们与早期使用官方回归测试的来源资格计数不同。

详细事件和透明路径替换记录在 [python-workflows/](python-workflows/)。采集采用明确的 controller-only development 模式，`os_isolation=false`；它不是操作系统强隔离证明、原生代理完整工作流或已完成方法单元。原始测试失败、跳过和导出修订应分别保留，不用新结果覆盖旧记录。

## 16 个方法单元及外部服务

[paired-inputs/controller/preparation.json](paired-inputs/controller/preparation.json)已经绑定两个来源、A/B/C/D 四臂及两次重复的 16 个开发单元。公开输入单独准备；初始 reader 输入只包含任务描述、原请求和预算。没有将整个源码目录当作免费上下文输入。

当前 `permissions_granted=true`，`runtime_ready=false`、`scientific_ready=false`。Python 采集是实际准备进展，仍不能替代原生工作流的压缩前历史、共同父 checkpoint、完整 A/B/C/D 执行、共享 reader/tokenizer 和可比计量。两个来源仍为 real-source seed，正式接受任务数为 0；16 个方法单元实际运行数为 **0**。

最初 stage 的 controller 能力描述按历史原样保留。当前能力说明见 [paired-readiness-v2/runtime-readiness.json](paired-readiness-v2/runtime-readiness.json)，修订依据见 [revision.json](paired-readiness-v2/revision.json)。新版只更新已实现 Python 采集组件的描述，绑定相同公开输入、原计划、16 个单元和已有采集记录；没有重新复制源码、执行测试或消耗方法单元。两版 producer 的精确源码/hash 均可核对。

本地及授权 Mac 的指定进程变量未提供 embedding/reranker 凭据；未读取任意凭据仓库或打印密钥。[credential-presence.json](credential-presence.json)只表示检查范围内的存在性，不能证明用户没有服务账户。OpenAI 实际组织/项目尚未选择，Cohere 凭据及当前账户计费条件尚未配置；直接供应商请求数为 0。

## 预算与用量

唯一中央台账保留两次原生预留及两个 timeout 结束事件，见 [ledger-status.json](ledger-status.json) 和 [ledger/events.jsonl](ledger/events.jsonl)。没有为每个远端目录另建配额，也没有将运行后观察值补写成事前动作预留。

本批新增按量支出上限为人民币 100 元。两次 native 只允许既有 ChatGPT 订阅路径，禁止 API 回退、购买 credits 或自动充值，新增现金动作预留上界为 0 元。**完整经济成本与实际账单仍未知**，不能把订阅使用记为免费 token 或填入零成本。

native-01 没有可对齐的用量通知。native-02 的 11 条已对齐生成通知累计为 182,068 输入、2,218 输出、184,286 total tokens；缓存输入和 reasoning 输出是其中子集，不重复相加。通知条数不等于 generation turn 数，最后一个未完成 turn 的完整用量也不因此闭合；2 次 compaction 的计量语义仍未建立。见两目录中的 `usage-audit.json`。

## 证据与限制

- [approval-protocol/](approval-protocol/)保存安装版 schema、固定官方源码/许可证、通知时序和离线测试证据。
- [native-runtime-manifest.json](native-runtime-manifest.json)与 [native-runtime.tar.gz](native-runtime.tar.gz)固定实际运行的 31 个源文件；不覆盖安装的 Codex/Node 二进制或账户配置。
- 两份 permit 绑定各自唯一中央 reservation、模型、全新输出、运行源码和期限。一次性消费记录随各尝试导出；permit 自身不独立认证全局配额或真人身份。
- 各尝试 `export-manifest.json`保留原始与公开字节 SHA。公开文件替换临时根路径；二进制原始存储与完整原始运行文件另存所有者副本，不放进模型输入。
- 本批没有独立人工标签/裁决、任务验收、正式统计结果、期刊投稿、预印本发布或 main 合并。下一次原生运行需要新的明确批次额度；本批 16 个已授权开发单元的权限仍保留，待执行条件具备。
