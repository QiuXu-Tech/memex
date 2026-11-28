# P1：DeepSeek 接入与实验边界

更新：2026-11-28（Asia/Shanghai）。用户本轮明确选择：**“用deepseek的api”**。后续生成服务按此选择准备；此前未提交的 OpenAI 密钥创建流程停止。

**当前状态：DeepSeek 候选抽取组件已完成离线验证与一次真实生成诊断；实际返回通过 JSON、类型及原文依据检查。** 本次为固定合成输入上的接入验证，不是正式论文样本，不表示四臂实验已接通，也不增加原生尝试额度。原始批准记录、来源包、公共输入、原生证据和论文结果均保持原来的身份；现金台账已追加这一次诊断的真实事件。记录见 [deepseek-live-01](artifacts/deepseek-live-01/README.md)。

## 服务角色

| 角色 | DeepSeek 的接入方式 | 当前边界 |
|---|---|---|
| 候选 claim 抽取 | 使用独立 completion adapter，作为 `claims.mjs::extractClaims(input, complete)` 的回调 | 保留已有 JSON、原文 grounding 与 unknown 规则；直连 API 输出不能标记为 native auxiliary thread 产物 |
| 四臂共同 reader | 后续统一采用同一已冻结的 DeepSeek 配置，所有臂同时变更 | 当前真实来源 shared reader 未实现；普通聊天请求不能继承此前不透明的 native compacted parent |
| 原生压缩与分叉 | 需要真实 host 支持与完成收据 | DeepSeek 的 Responses 协议支持不证明本仓库 Codex 0.153.0 路径已接通；当前 host 仍显式指定 ChatGPT/OpenAI |
| B：官方 Raw-RAG 检索 | 保留固定上游版本及既定 embedding/reranker | 固定模型为 `text-embedding-3-small` 与 `rerank-v3.5`；不能将 DeepSeek 聊天、网页搜索或聊天排序包装成这两个模型 |

核查的 DeepSeek 官方 API 目录提供 Chat Completions、Responses、工具调用等生成接口；本次未找到可以直接供应上述固定 embedding/reranker 的 DeepSeek 官方端点。因此，新配置只处理生成角色。若以后替换检索模型或检索算法，须单列可复核的替代基线，不能沿用“忠实官方 Raw-RAG”标签。`rawrag-config.json` 不做改写。

## 当前配置选择

- 服务 origin：`https://api.deepseek.com`。
- 候选抽取 endpoint：`/chat/completions`。
- 模型请求名：`deepseek-flash`。2026-11-28 官方价目对应版本为 DeepSeek-V4.1-Flash-1017。
- 凭据变量：`DEEPSEEK_API_KEY`；配置文件只保存变量名，不保存密钥。
- 抽取使用显式非思考模式与 JSON object 输出；不启用服务端搜索、网页读取或其他额外工具。
- 设置请求、输出、响应字节和时间上限；不启用自动重试或重定向。

`deepseek-flash` 是服务方可更新的模型名。请求名、响应中的模型名、配置摘要和执行时间可记录；这不构成对服务端实际权重版本的独立认证。正式研究冻结还需要记录当时的服务说明、运行窗口与版本限制。

初次准备时，已检查的执行环境没有配置 `DEEPSEEK_API_KEY`。随后用户明确提供本机剪贴板中的密钥，凭据已直接保存至用户设备的 P1 专用私有文件，未经过聊天、Git 或模型输入。对官方 `/models` 的实际读取确认鉴权成功且包含 `deepseek-flash`。账户可用性只在本地检查；账户资料和余额状态不作为公开研究材料。

## 无付费调用的组件接口

新增 `scripts/paper1/deepseek.mjs` 和 `deepseek-config.json`。组件的 completion 结果为 `{text, usage, controllerMetadata}`；既有抽取器仍独立验证实际模型文本。controller metadata 由调用侧建立，不能从模型输出采信 provider、request identity 或费用声明。

`createDeepSeekCompletion(...)` 必须接收 controller 提供的 `authorizeDispatch(intent)`。该调用在网络发送前发生；缺失、拒绝或与本次请求摘要不匹配的入场记录必须阻断发送。回调自身只是可信 controller 的集成接口。下文新增的独立诊断入口将它接至同一批次现金台账；其他调用方仍须自行完成真实的 controller 集成，不能仅凭一个 receipt 对象声称预算已受控。

只读检查入口不发起请求、不执行来源、不预留尝试：

```bash
node --input-type=module -e "import { inspectDeepSeek } from './scripts/paper1/deepseek.mjs'; console.log(JSON.stringify(inspectDeepSeek(), null, 2))"
```

即使检测到密钥，通用组件预检仍报告 `live_dispatch_ready=false`。独立接入诊断只实现下述有限现金路径；任务原生 checkpoint、共享 reader/tokenizer、运行隔离和四臂统一预算集成仍未完成。

## 独立接入诊断

`scripts/paper1/deepseek-diagnostic.mjs` 使用固定、公开的合成小样例，经原有 `extractClaims()` 检查实际返回的 JSON、类型与原文依据。它不是 `w-101/w-102` 方法单元，不产生 native compaction 证据，也不增加论文样本量。

默认入口只读配置，不读取凭据、不访问服务、不修改台账：

```bash
node scripts/paper1/deepseek-diagnostic.mjs
```

在指定的唯一执行副本中，显式 `--run` 才允许做一次接入诊断：

```bash
node scripts/paper1/deepseek-diagnostic.mjs --run
```

执行入口优先读取进程变量 `DEEPSEEK_API_KEY`；未配置时，读取用户主目录下的 `.config/memex/p1/credentials/deepseek_api_key`。私有文件必须属于当前用户、权限为 `0600`，且路径不得经过符号链接。凭据不进入 Python 子进程参数、环境、stdout 或结果文件。运行时结果保留在本机，公开前只选择不含账户状态的验证摘要。

入口先请求官方 `/user/balance`。账户不可用、响应未知或检查失败时，停止于现金预留之前；当前人民币预算路径还要求可验证的 CNY 计费信息，其他币种须另行核对费率与换算，不能套用人民币价格。条件满足时，`BatchLedger.reserve_diagnostic()` 在原来的 canonical ledger 中预留现金，随后记录唯一且绑定本次 dispatch 的 `provider_request` 事件；两者持久化完成后才返回发送准入。诊断有独立计数，不消耗 native 或 method 名额，不产生新的现金总额度。

固定配置为单次生成、最多 1,024 输出 tokens、30 秒、零自动重试；请求和响应分别限制为 16,384 / 65,536 字节。预留 CNY 3.00 是预算上界，并非实际消费估计：按当天核对的高峰费率，对完整 1,048,576-token 上下文及 1,024 输出 tokens 保守计算，得到 CNY 2.105344，再向上预留至 3.00。此计算不把字节数当作 token 数。价格证据仅在核查的北京时间当日有效，过期后须重新核对并更新配置身份。

已确认的本次预留才可由启动器结束；未确认的写入或已有 ID 冲突须保留状态等待核对。失败、超时或实际费用未知时保留预留上界。返回的 token 用量可形成明确标注的费用估计，不能代替可归属的账单证据进行现金核销。

### 已完成的真实诊断

2026-11-28 18:05:49（Asia/Shanghai），指定设备执行副本完成一次 `deepseek-flash` 请求：HTTP 200，**1 次生成、0 次自动重试**，434 输入 tokens、210 输出 tokens，合计 644；缓存输入为 0。抽取器得到一条 `operation_authorization` 候选，引用与合成 draft 原文匹配，同时保留未验证、角色身份不完整和不得执行发布的限制。

输出还额外提示缺少 `test_result` 证据，但输入并未要求测试；这项定性问题在公开记录中保留。本次通过说明这个输入上的调用和校验链路可用，不提供抽取准确率、义务覆盖率、方法优势或完整研究可运行性的证据。

按当日高峰参考费率，标准化用量估计为 **CNY 0.00254800**，实际扣款仍为未知。原 canonical ledger 从 4 条增加到 7 条，依次追加现金预留、唯一 provider request 操作和完成事件；原 4 条事件的字节前缀完整保留。CNY 3.00 预留继续占用原 CNY 100 上限，账面剩余预留容量为 CNY 97.00；这不是账户余额或已核销预算。两次 native 名额仍已用完，16 个方法单元仍未使用。

公开的[脱敏结果](artifacts/deepseek-live-01/result-public.json)、[请求审计](artifacts/deepseek-live-01/request-audit.json)、[台账审计](artifacts/deepseek-live-01/ledger-audit.json)和[状态快照](artifacts/deepseek-live-01/ledger-status.json)保留了实际调用、配置与台账的绑定。账户状态、凭据和设备路径不在公开结果中；原始 provider 文本未作为公开复现材料提供。

## 用量、预算和历史记录

输入 tokens 与缓存输入分别记录，缓存命中是输入的子集。缓存命中与未命中计数若同时存在，必须与总输入一致。用量缺失保持未知；不能填零，不能据此声称完整成本。截断、工具输出、拒答、空 JSON 文本或无效响应均不能作为一次成功抽取。

官方中文价格在本次核查时列出 Flash 每百万 tokens 的高峰价格：缓存未命中输入 2 元、命中输入 0.04 元、输出 8 元；非峰价格减半。这些是日期明确的参考费率，**不是本项目已支付账单，也不是永久价格**。未来调度需在发送前重新核对费率、保守预留现金，并记录实际供应商回执；不能只凭 SDK 返回的 token 数宣布实际现金支出已核销。

原第 1 批的两次原生尝试已使用，16 个方法单元尚未使用，总新增现金上限继续为 CNY 100，包含配置诊断、失败和重试。切换服务方不退还已用尝试、不创建第三次原生许可、不把诊断伪装成方法单元。新增的是台账对独立诊断的支持；历史授权和已有事件字节保持不变。

原生结果使用原来的模型、宿主和记录解释。今后的 DeepSeek 结果须有新的配置身份；如果同时改变宿主，须作为单独的外部有效性研究，不能与历史结果混合后宣称是纯模型差异或方法提升。

## 验证与后续运行条件

组件测试只使用自有夹具和可计数的替身 transport，不调用公网服务、不读取真实凭据、不执行论文任务。它们验证接口、失败处理、用量与凭据保护，不能增加研究样本量。

第一轮 transport 准备于 2026-11-28 在 Node v24.22.3 上执行 `node --test test/paper1-*.mjs`：**97 项通过，0 失败、0 取消、0 跳过**，其中 DeepSeek 新增 27 项，原有 Node 回归 70 项。完整结果见 [node-tests.txt](artifacts/checks/deepseek-preparation/node-tests.txt)，当时组件、只读预检与受保护输入的校验记录见 [validation.json](artifacts/checks/deepseek-preparation/validation.json)。这些历史记录不被后续接入检查覆盖。

独立审查发现的同步准入回调越过截止时间后仍发送请求、同步解析超时仍返回成功、内层 JSON Unicode 转义反射凭据、声明响应过大时取消读取，以及响应其他层级的工具标记检查，均已修复并纳入离线回归。截止时间检查能拒绝过期后的发送与成功结果，但不能宣称抢占或中断任意同步 JavaScript。

第二轮诊断集成验证为 **112 项 Node 测试与 72 项相关 Python 测试通过**，新增诊断测试分别为 15 / 10 项。Python 选择了现金台账、独立诊断、原生许可与配对准备四组，未重跑整套研究套件。新 checkout 的配对准备测试最初因原计划绑定绝对路径而出现 8 个失败；在原冻结路径运行同一新台账代码后，19 项全部通过，未修改计划、授权或来源包。原失败与后续验证均保留在 [诊断验证记录](artifacts/checks/deepseek-diagnostic/validation.json) 中。

首次本机部署保留了当时已公开的四条台账事件及同一授权摘要；只有指定的设备执行副本用于真实诊断，其他 checkout 用于测试和发布。代码不声称提供跨设备、跨克隆的分布式互斥。真实生成之前的历史接入检查累计三次只读元数据请求，停止于现金预留之前；该阶段为零生成、零新增预留、原台账字节未变。随后上节所记诊断另有一次只读账户检查和一次实际生成。账户状态回执始终保留在设备私有运行目录，未发布。

独立生成诊断已通过当次账户检查、现金准入与实际返回校验；无需重复请求来证明同一接入结果。正式研究还需冻结并实施共同 tokenizer/token/工具上限、取得任务对应的真实压缩 checkpoint、接通四臂共同 reader 和完整费用采集，并单独解决 B 的固定检索服务。接入诊断不替代这些步骤。

## 核查依据

- [DeepSeek 官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)（2026-11-28 核查）。
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：JSON、生成限制、完成状态与用量字段。
- [DeepSeek 模型列表](https://api-docs.deepseek.com/api/list-models/)与[账户可用余额查询](https://api-docs.deepseek.com/api/get-user-balance/)：只读服务发现及账户可用性字段。
- [DeepSeek Responses 兼容性说明](https://api-docs.deepseek.com/guides/responses_api/)：客户端须发送完整历史；`previous_response_id`、服务端 conversation 与存储并不支持。
- [DeepSeek Codex 集成说明](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)：这是后续宿主兼容性验证的参考；本轮未运行安装脚本，也未覆盖用户全局配置。
- 仓库合同：`scripts/paper1/claims.mjs`、`rawrag-config.json`、`rawrag_adapter.py`、`paired_runner.py`、`batch_limits.py` 和 `scripts/codex-retention-host.py`。
