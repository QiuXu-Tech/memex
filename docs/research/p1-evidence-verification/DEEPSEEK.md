# P1：DeepSeek 接入与实验边界

更新：2026-11-28（Asia/Shanghai）。用户本轮明确选择：**“用deepseek的api”**。后续生成服务按此选择准备；此前未提交的 OpenAI 密钥创建流程停止。

**当前状态：DeepSeek 候选抽取组件已完成离线验证，尚未发生真实 DeepSeek 请求。** 这项选择不等于四臂实验已接通，也不增加原生尝试额度。原始批准记录、来源包、公共输入、原生证据和论文结果均保持原来的身份。

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

本轮凭据检查只观察进程环境和 P1 项目配置的存在情况，不输出值。在已检查的本地执行环境和 Mac P1 运行目录中，尚未发现 `DEEPSEEK_API_KEY`。这不是对整台机器、其他应用或用户账户的全盘检查，也不代表账户没有密钥。

## 无付费调用的组件接口

新增 `scripts/paper1/deepseek.mjs` 和 `deepseek-config.json`。组件的 completion 结果为 `{text, usage, controllerMetadata}`；既有抽取器仍独立验证实际模型文本。controller metadata 由调用侧建立，不能从模型输出采信 provider、request identity 或费用声明。

`createDeepSeekCompletion(...)` 必须接收 controller 提供的 `authorizeDispatch(intent)`。该调用在网络发送前发生；缺失、拒绝或与本次请求摘要不匹配的入场记录必须阻断发送。回调是可信 controller 的集成接口，**不是已经完成的中央现金预算实现，也不是防御 controller 自身篡改的安全边界**。当前没有可以直接启动付费调用的命令行入口。

只读检查入口不发起请求、不执行来源、不预留尝试：

```bash
node --input-type=module -e "import { inspectDeepSeek } from './scripts/paper1/deepseek.mjs'; console.log(JSON.stringify(inspectDeepSeek(), null, 2))"
```

即使检测到密钥，预检仍应报告 `live_dispatch_ready=false`。全局现金准入、任务原生 checkpoint、共享 reader/tokenizer 和运行隔离尚未接通；有密钥不能把这些状态改为完成。

## 用量、预算和历史记录

输入 tokens 与缓存输入分别记录，缓存命中是输入的子集。缓存命中与未命中计数若同时存在，必须与总输入一致。用量缺失保持未知；不能填零，不能据此声称完整成本。截断、工具输出、拒答、空 JSON 文本或无效响应均不能作为一次成功抽取。

官方中文价格在本次核查时列出 Flash 每百万 tokens 的高峰价格：缓存未命中输入 2 元、命中输入 0.04 元、输出 8 元；非峰价格减半。这些是日期明确的参考费率，**不是本项目已支付账单，也不是永久价格**。未来调度需在发送前重新核对费率、保守预留现金，并记录实际供应商回执；不能只凭 SDK 返回的 token 数宣布实际现金支出已核销。

原第 1 批的两次原生尝试已使用，16 个方法单元尚未使用，总新增现金上限继续为 CNY 100，包含配置诊断、失败和重试。切换服务方不退还已用尝试、不创建第三次原生许可、不把诊断伪装成方法单元。中央台账和历史授权文件不在本轮改写。

原生结果使用原来的模型、宿主和记录解释。今后的 DeepSeek 结果须有新的配置身份；如果同时改变宿主，须作为单独的外部有效性研究，不能与历史结果混合后宣称是纯模型差异或方法提升。

## 验证与后续运行条件

组件测试只使用自有夹具和可计数的替身 transport，不调用公网服务、不读取真实凭据、不执行论文任务。它们验证接口、失败处理、用量与凭据保护，不能增加研究样本量。

2026-11-28 在 Node v24.22.3 上执行 `node --test test/paper1-*.mjs`：**97 项通过，0 失败、0 取消、0 跳过**，其中 DeepSeek 新增 27 项，原有 Node 回归 70 项。完整结果见 [node-tests.txt](artifacts/checks/deepseek-preparation/node-tests.txt)，本次组件、只读预检与受保护输入的校验记录见 [validation.json](artifacts/checks/deepseek-preparation/validation.json)。没有重新执行与本次改动无关的 Python 研究套件。

独立审查发现的同步准入回调越过截止时间后仍发送请求、同步解析超时仍返回成功、内层 JSON Unicode 转义反射凭据、声明响应过大时取消读取，以及响应其他层级的工具标记检查，均已修复并纳入离线回归。截止时间检查能拒绝过期后的发送与成功结果，但不能宣称抢占或中断任意同步 JavaScript。

实际调用前仍需完成：定位可用凭据并安全接入、将发送前准入绑定中央现金台账、冻结并实施 tokenizer/token/工具上限、取得任务对应的真实压缩 checkpoint、接通四臂共同 reader，并单独解决 B 的固定检索服务。本文不声明已完成这些步骤。

## 核查依据

- [DeepSeek 官方模型与价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)（2026-11-28 核查）。
- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)：JSON、生成限制、完成状态与用量字段。
- [DeepSeek Responses 兼容性说明](https://api-docs.deepseek.com/guides/responses_api/)：客户端须发送完整历史；`previous_response_id`、服务端 conversation 与存储并不支持。
- [DeepSeek Codex 集成说明](https://api-docs.deepseek.com/quick_start/agent_integrations/codex/)：这是后续宿主兼容性验证的参考；本轮未运行安装脚本，也未覆盖用户全局配置。
- 仓库合同：`scripts/paper1/claims.mjs`、`rawrag-config.json`、`rawrag_adapter.py`、`paired_runner.py`、`batch_limits.py` 和 `scripts/codex-retention-host.py`。
