# P1 B 臂：受控真实检索接口

更新：2026-11-28。本文记录本轮工程接口，不新增论文样本或供应商检索结果。原始 `BASELINE.md`、离线构造报告、原授权、现金台账及冻结配置的历史身份保持不变。

## 已实现的路径

`scripts/paper1/rawrag_controller.py` 调用现有 `rawrag_adapter.py`，后者仍直接使用官方 `RAGAdapter.add/search`。固定上游为 `95639191e9547219b426710e50fe1a36235e26fc`；`rawrag-config.json` 未修改。256/32 分块、dense top 128、`text-embedding-3-small`、`rerank-v3.5`、本地最终 top 15、完整 turn expansion、重复 turn 保留和原始请求查询均沿用原合同。上游应用层三次尝试语义保留；SDK 自动重试为零。

新增接口：

```python
run_bound_retrieval(
    *, upstream, config, archive_path, request_path, output_path,
    checkpoint, attempt_id, authorize_dispatch, display
)
```

`display` 必须显式传入 `faithful` 或 `budget-matched`。后者继续采用既定的完整展开后 5,000 个参考 tokens 前缀及标记策略。两种模式都保存完整展开文本及实际交付文本的 SHA256。共同 reader 必须使用其自己的冻结 tokenizer 重新计量最终输入；此模块返回的参考计量不能替代该步骤。

## checkpoint 和输入身份

`checkpoint` 是严格的十字段 identity 对象：

| 字段 | 含义 |
|---|---|
| `task_id`, `replicate` | 本次任务与重复身份 |
| `public_sha256` | 公共任务输入身份 |
| `workspace_snapshot_sha256` | 任务工作区快照身份 |
| `native_parent_thread_id` | 共同原生父会话 |
| `native_capture_sha256` | 原生记录身份 |
| `native_compaction_item_id` | 实际压缩项身份 |
| `source_archive_sha256` | 原始归档文件 bytes 的 SHA256 |
| `shared_reader_config_sha256` | 共同 reader 配置身份 |
| `original_request_sha256` | 原始请求文件 bytes 的 SHA256 |

`checkpoint_sha256` 是这十字段的 canonical JSON SHA256，不是外层 sealed checkpoint 整包的摘要。外层 controller 必须验证真实宿主收据、公共目录和封印，再提取这十字段。本接口不创建父会话，不把普通聊天冒充原生压缩，不独立认证外层提供的宿主事实。

controller 在加载 runtime 前验证公共归档、原请求和任务身份；底层在真正消费文件时再次验证原始 bytes，防止初次检查后文件被替换。归档仍拒绝监督标签、私有元数据、重复 JSON 键、cutoff 之后事件及不完整快照。原始正文不改写、不去空格。公共语义字段仍是 ingestion 假设，不因此变成自然日志解析器。

## 每次 HTTP 请求的现金准入

`authorize_dispatch(intent)` 是同步、可从 rerank worker thread 调用的可信 callback。它必须在返回前完成唯一执行副本内的 canonical cash reservation 及本次操作的持久化记录。B 组件不创建另一份现金额度，不使用 DeepSeek 单请求诊断的独立计数。

intent 含 `attempt_id`、`checkpoint_sha256`、`config_sha256`、`provider`、`model`、`endpoint`、`component`、`dispatch_id`、精确请求正文摘要、正文 bytes、参考输入 tokens 及整个 intent 的摘要。`component` 为 `embedding` 或 `rerank`。同内容重试仍有不同的 `dispatch_id`，每次都重新经过准入。

回执沿用共同的七字段 ABI：

```json
{
  "schema_version": 1,
  "kind": "p1-dispatch-admission-receipt",
  "decision": "allow",
  "dispatch_id": "本次调用身份",
  "intent_sha256": "本次意图摘要",
  "request_sha256": "精确正文摘要",
  "admission_id": "持久化准入记录身份"
}
```

缺 callback、字段不匹配、拒绝回执、预算不足或准入返回时已超时均阻断发送。普通 `rawrag_adapter.py --run` CLI 没有提供可信 callback 的入口，因此即使凭据已配置也会在 credential preflight 前返回 `dispatch_controller_required`。离线 `--check` 和构造诊断继续可用。

这里的回执校验是 controller 集成合同；任意 Python 调用方返回一个对象不构成独立的现金账本认证。现金控制由共同 controller 承担，B 的日志同时保留意图、回执与发送观测。

共同 controller 保留原来逐请求保守上界模式。新版 DeepSeek reader 可采用注册 relay、不可变完成记录与串行累计用量证明下的每 scope 人民币 3.20 元上界；其条件和当日价格证明见 [NATIVE_RELAY.md](NATIVE_RELAY.md)。B 的 embedding/rerank 仍须另外覆盖原 16 次检索 dispatch 的保守费用，即再加 `16 × max(非 DeepSeek 单次已核验人民币上界)`。这不是把 B 的固定检索模型换成 DeepSeek，也不会把参考 tokens、请求次数或第三方价格猜测写作真实计费量。固定模型可用性、当前账户计费规则及汇率依据未核验时，B 继续阻断真实调用。3.20 元属于条件预留上界，不能据此核销实际现金。

## 供应商用量与实验账本

每条上游日志现在绑定到具体 HTTP attempt。返回的模型身份与固定 embedding 模型不符会阻止检索继续。embedding 与 rerank 响应都受 bytes 限制；embedding 响应在 SDK 解析前有界读取。所有失败、重试和未知用量保留，未知费用不填零。

`normalize_usage()` 产生现有 `experiment.py` 可读取的 `usage` 和 `component_end` 行：

| component | experiment meter | 实际来源 |
|---|---|---|
| `embedding` | `kind=quantity`, `unit=token` | `usage.prompt_tokens`，并要求 `total_tokens` 一致 |
| `rerank` | `kind=quantity`, `unit=search_unit` | `meta.billed_units.search_units` |

参考 tokenizer tokens、HTTP 次数和上游 log 行数都不能替代上述计费量。每次操作只形成一个量值记录；重复/缺失/未绑定日志使相应 component 为 `incomplete`。失败请求没有用量时，总标准化成本保持未知。返回用量不是实际账单；本组件始终不自行核销现金。

成功返回的 `packet` 仅携带交付正文、bytes、参考 token 计量和公共内容摘要。checkpoint、准入与计量审计单独保存在 controller 文件中。`trace_refs` 使用 `{path, sha256}`，路径相对于 B 输出目录；`usage_rows.source_ref` 采用相同基准。四臂汇总器应给它们添加一致的 B 目录前缀。

新增产物包括 `controller-binding.json`、`binding-receipt.json`、`usage.jsonl`、`usage-audit.json`、`controller-run.json`。原有 `ledger.json`、`retrieval.json`、`expanded-context.txt` 和 `context.txt` 继续保留。返回 `completeness.usage` 只涉及 B 的 embedding/rerank 计量；它不宣称完整实验的所有 pipeline 成本都已测得。

## 本轮验证与仍需外部提供的条件

隔离 Raw-RAG Python 环境执行 `python -B -m unittest discover -s test -p 'test_paper1_rawrag*.py' -v`：57 项通过、0 跳过。包括真实安装 SDK 及 HTTP client 的内存 transport 测试、无准入零发送、重试身份、超时、响应上限、错模型拒绝、checkpoint/input 修改拒绝、重复用量及缺失用量。另直接调用 `experiment.standardized_cost()` 验证 B 的 quantity meters 可以计价，缺失 rerank 用量时完整成本仍为未知。测试 fixture 均为合成控制器数据，不能算作检索或论文结果；没有外部供应商请求。

真实 B 调用仍需提供可访问固定模型的 `VECTORIZE_API_KEY`、`RERANK_API_KEY`，可核验的服务计费/币种及保守人民币预留依据，真实任务 checkpoint 和完整公共归档，以及已验证的共同现金 controller。凭据不应进入请求参数日志、Git、论文材料或模型上下文。本轮没有读取凭据，没有模型付费调用。

## 官方接口依据

- [OpenAI embeddings API](https://developers.openai.com/api/reference/resources/embeddings/methods/create)：固定 `/v1/embeddings` 请求和 `prompt_tokens` / `total_tokens` 响应计量。
- [Cohere Rerank v2 API](https://docs.cohere.com/v2/reference/rerank)：`query`、`documents`、`model`、`top_n` 请求合同。
- [Cohere Rerank 模型目录](https://docs.cohere.com/docs/rerank)：仍列出 `rerank-v3.5`。
- [Cohere 计费说明](https://docs.cohere.com/docs/how-does-cohere-pricing-work)与[返回示例](https://docs.cohere.com/v2/docs/rerank-overview)：search 计量及 `billed_units.search_units`。
- [DeepSeek 模型/API 目录](https://api-docs.deepseek.com/api/list-models/)：当前检索未发现提供上述两个固定模型的官方 DeepSeek 端点。DeepSeek 生成接口或网页搜索分数不能替代此 B 臂。
