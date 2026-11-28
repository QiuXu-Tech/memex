# 真实宿主后端与共同 reader

状态：**开发实现；有离线合同验证，尚无本实现的真实四臂实验结果**。现有两次 native 授权已消费，新增代码不会产生第三次许可。本文不替代 [PROTOCOL.md](PROTOCOL.md)、原授权或正式预注册。

## 执行链

实现位于 [native_backend.py](../../../scripts/paper1/native_backend.py)。[paired_runtime.py](../../../scripts/paper1/paired_runtime.py) 负责阶段、首次尝试与检查点封存；[runtime_controller.py](../../../scripts/paper1/runtime_controller.py) 在原 canonical ledger 中完成额度预留、逐请求准入和未知费用保留。后端实际调用 Codex 0.153.0 的 app-server JSON-RPC。普通模型回复、Python 测试夹具及先前其他任务的 native 日志都不能创建本任务的压缩检查点。

| 阶段 | 实际调用与保留证据 |
|---|---|
| `capture_parent` | 先检查固定 Python 及依赖、验证 OS sandbox，再创建真实持久化 thread。原始任务作为实际 user message 输入；只提供五个公共动态工具。保存实际完成的用户/助手消息、工具请求与结果、当前工作区摘要。 |
| `prime_D` | 从可见 request、draft、公共配置构成抽取输入；独立辅助 thread 产生原始抽取输出，由已有 `extractClaims` 校验。真实 L2 打开原文并建立一次 prime cache。未知或未验证的 receipt 保留 null。 |
| `compact_parent` | 重新连接真实父 thread，调用 `thread/compact/start`，要求完成的 contextCompaction item 和对应成功 turn。再从实际 `thread/read` 获取保留历史并绑定摘要；原前置日志字节作为压缩日志的原样前缀。 |
| `verify_checkpoint` | 重新读取实际父历史，与已封存的观察比较；同时重算公共材料、工作区、原请求、归档和捕获文件摘要。既不靠模型复述，也不原样回传预期 binding。 |
| `fork_parent` | 对同一真实父 thread 调用 `thread/fork`，保存原始 RPC 请求及响应。每臂使用不同 thread ID 和独立复制的工作区。 |
| `build_packet` | A 不调用此阶段；B 调用固定官方 Raw-RAG；C 总是重新打开，D 使用同一 archive epoch 的原始 prime cache。每个单位从该 cache 独立复制，前一个单位的新 receipt 不污染后一个单位。 |
| `continue_reader` | 恢复真实子 thread，输入共同原请求及该臂证据包。保存实际生成、公共工具结果与供应商 usage；不在此处写成功标签或行为评分。 |

共同 [DeepSeek reader 配置](../../../scripts/paper1/deepseek-reader-profile.json) 是新增、可哈希的开发配置。它没有回写原 `shared-budget.json`，也没有把 `formal_study_frozen` 改为 true。原生前置阶段和每臂续跑分别受各自原授权 scope 约束。

## 进程与工具边界

每个宿主操作启动新的短寿命 Codex 进程。relay 每次激活都轮换本地随机能力 token；旧 token 无法给新 scope 排队请求。有未结束请求或未知用量时，相关 scope 保持阻断。真正的 DeepSeek credential 仅在私有 relay 中读取，Codex 子进程只获得随机本地 token；不会继承 OpenAI、Cohere、DeepSeek 服务密钥或控制器配置环境变量。

公共工具固定为 `read_file`、`write_file`、`list_files`、`run_current_tests`、`record_review`。shell、内置文件改写、其他 MCP、浏览器、网络工具和非绑定的动态请求均不准入。每次工具调用绑定真实 thread、turn 和唯一 call ID；测试使用当前工作区的独立只读快照，且必须在当前 SandboxRunner 实例的真实 canary 成功后执行。方法臂不能靠工具名或其他 scope 借用 native generation/compaction 次数。

被测试项目只获得任务工作区、固定运行时和受限输出目录。隔离证明是对实际运行环境的探针观察，不是对任意恶意 Python 程序的不可伪造执行证明；测试 receipt 的科学含义仍限于所选公开测试与记录的源版本，不能自动当成隐藏行为正确性或发表许可。独立行为评价由冻结后的评分流程完成。

## 检查点和缓存的寿命

运行中的 L2 helper 保存在私有 backend state 中，初次抽取及 prime 完成后复制不可变旁证到检查点。后续 C/D 的验证日志不会改写原检查点。抽取文件按真实文件字节复制，检查点中的 SHA-256 与 helper 中实际抽取文件相同。

当前实现要求 native 准备及其 C/D 单元由**同一个存活的 backend/helper 实例**处理。导入检查点不能恢复原进程的 archive epoch；不存在“读取缓存 JSON 就等于原 receipt 仍可复用”的分支。原生宿主进程可以通过真实 `thread/resume` 重连，L2 核验缓存的进程身份不因此重建。

开发 `run_paired_block` 是一个父准备加四个方法 scope 的组合调用，不能作为 `experiment.py` 每次只运行一个方法单元的 executable。新增 [PairedLauncher](PAIRED_DISPATCH.md) 已将存活 backend/helper 的 `run_unit` 接入原 dispatcher：绑定实际实现树和冻结单元，每次只执行一个方法，保留原首次尝试、usage、seal 与 join。A/C/D 三单元的实际 in-process fixture 已验证这一工程连接；没有通过跨进程重启或导入 JSON 重建缓存身份。真实宿主与完整实验的执行验证仍未完成。

## 用量、预算与失败

供应商返回的 input、cached input、output 是实际 delta；缓存输入是总输入的子集。官方 DeepSeek tokenizer 的离线计数只用于固定 canonical 请求 JSON 的参考计量，不能冒充服务端完整模板的精确账单 token 数。[实际 tokenizer 检查](artifacts/remaining-completion-01/tokenizer-check.json)记录了文件摘要、运行库版本和三个可复算文本。

源打开的实际调用和字节数在 L2 helper / 公共工作区中记录，并共享每臂的 32 次、96,000 字节、单次 4,000 字节上限。native 原授权没有独立 `source_open` 计数类别，仍计入 `public_tool_call`，额外保留实际源读计量；不会扩写原 ledger schema。超出单次边界的完整原文会保留 abstain，不能暗中放宽。打开字节未知时不能把它变成零。

每个宿主阶段无论成功失败都保留 `provider-operation-audit.json`；失败后已发生的请求不会消失。现金预留与标准化成本分开：实际现金未知时保留上界，原 CNY 100 不因新代码自动增加或重新计算。当前 backend 的模型/检索 usage 也不单独证明 setup、CPU、storage 等全部成本已经完整采集；完整性仍由冻结的 measurement audit 和现有 `experiment.py join` 判定，缺项保持 unknown。

## 已有验证与实际待验收项

已完成的零供应商调用检查包括：安装中 Codex 的实验协议 schema 导出；官方 tokenizer 的真实离线装载；实际 OS canary；Python 到 Node 的真实逐行 IPC、反向 source-open 准入和 Memex L2 打开；独立 C/D prime-cache 克隆；父历史、动态工具、权限、账本和错误边界的合同测试。其数据属于工程夹具和运行环境检查，不是论文实验样本。

仍待真实执行验证的是：DeepSeek Responses 与 Codex 实际请求的完整兼容性、本任务 native 前置/压缩/分叉、完整四臂结果和成本采集。缺失的 B 服务配置、已用尽的 native 次数以及真人评价不会由离线测试消除。下一步的具体输入和当前状态集中在 [REMAINING_WORK.md](REMAINING_WORK.md)。

## 一手接口依据

- DeepSeek Responses API：https://api-docs.deepseek.com/guides/responses_api/
- DeepSeek token 用量与官方 tokenizer：https://api-docs.deepseek.com/quick_start/token_usage/
- Codex 0.153.0 对应源码：https://github.com/openai/codex/tree/41e22fee981a63b3698df7ed36bad393cda24715/codex-rs/app-server
- [实际安装版本导出的协议清单](artifacts/remaining-completion-01/host-schema-check.json)，覆盖 ThreadStart/Resume/Fork/Read、TurnStart 和动态工具请求/响应；该清单本身不证明已执行模型 turn。
