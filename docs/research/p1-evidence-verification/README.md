# P1：原生上下文压缩后的证据核验

更新：**2026-11-28，Asia/Shanghai**。研究分支：`research/p1-evidence-verification`。基于 Memex `49e772bbf60532682771874b7ec96958f4a179e3`。

## 当前交付

英文题目：**When to Reopen the Source: Evidence Verification after Native Agent Compaction**。

当前交付是一份可审阅的英文方法与实验协议工作稿，以及可运行、可检查失败的研究原型。**尚无新的正式对照实验结果，也尚未投稿。** 文稿的结果占位符不代表零分或实验失败。

| 内容 | 入口 | 状态 |
|---|---|---|
| 英文工作稿 | [PDF](manuscript.pdf)、[Markdown](manuscript.md)、[LaTeX](manuscript.tex)、[参考文献](references.bib) | 21 页；16 条参考记录；56 个 `PENDING` 结果占位符 |
| 实验与统计协议 | [PROTOCOL.md](PROTOCOL.md) | 公开输入、独立任务、失败分母、H1/H2、成本口径与冻结条件 |
| 强基线 | [BASELINE.md](BASELINE.md) | 固定官方 Raw-RAG commit；实际供应商检索调用仍待凭据 |
| 执行与审查证据 | [EXECUTION.md](EXECUTION.md)、[REVIEW.md](REVIEW.md) | 记录完成事项、修复、失败和未解决边界 |
| 原生宿主开发验证 | [运行说明](artifacts/native-smoke/README.md)、[最终摘要](artifacts/native-smoke/native-smoke-02-resumed-final/summary.json) | 真实原生压缩与续跑完成；一个合成开发工作流 |
| 真实日志离线回放 | [回放说明](artifacts/replay/native-smoke-02/REPORT.md) | 原生工具事件接入研究核验器；不是在线方法臂的性能实验 |
| 排版与重建 | [BUILD.md](BUILD.md) | 可编辑源文件、构建命令与逐页 PDF 检查记录 |

## 论文要回答的问题

在原生上下文压缩后，面对代码版本改变、测试尚未执行、结果被后续事件取代等情况，显式核验能否比强原始历史检索提高后续决策质量？如果可以，按需核验能否在保持质量的条件下降低**全流水线**成本？

“摘要不足时回看原文”本身已有直接先例；TierMem 已有摘要到原始日志的选择性升级，Raw-RAG 已展示强原始历史检索的重要性。本文必须检验的是当前证据资格与执行语义的增量价值，不能仅凭新增架构命名宣称创新。相关原始文献及实现边界见工作稿第 2 节和附录 D。

## 已实现的研究组件

代码位于 [`scripts/paper1/`](../../../scripts/paper1/)。

- `claims.mjs`：对可观察请求、草稿、上下文和工具说明建立自动抽取输入边界；拒绝金标准、预置 claims、正确来源位置等字段。当前没有自然任务上的模型抽取准确率结果。
- `archive.mjs`：使用真实 Memex L2 保存和分页打开原始事件；动态来源定位；全 session catalog 水位和可信 head 内容承诺；重启使旧缓存失效。
- `verification.mjs`：测试结果、当前版本、历史操作授权三类核验；显式处理版本、实际执行、时间、生效、撤销、冲突、不完整视图、缓存来源篡改和异步竞态。历史授权检查不授予执行权限。
- `normalize-node.mjs`：受支持 Node/TAP 命令的窄解析器，检查完成事件、退出码、非零实际测试数和 host 提供的执行前后版本摘要。无法解析相关事件时不能把视图声明为完整。
- `rawrag_adapter.py`：调用固定官方 Raw-RAG 的 `add/search`，保留原始公开来源；官方完整展示与固定预算适配分别命名。默认预检不调用模型。
- `analyze.py`：以冻结计划左连接运行记录，保留缺失和失败分母；先在任务内聚合重复运行，再进行项目与任务分层 bootstrap；质量和成本损坏分别处理。
- `native_smoke.py`：有界的原生宿主预检与开发验证，保留实际命令结果、原生压缩事件及失败尝试。

这些组件是研究代码，历史 `scripts/evidence-check-gate.mjs` 及旧实验驱动保持原样。旧驱动和新协议不能混用后合并为同一研究结果。

## 本地验证

环境：Node 24+、Python 3.12+；统计测试需要 NumPy。先按仓库说明配置依赖并运行 workspace 链接：

```bash
python3 -m venv /tmp/p1-analysis-env
. /tmp/p1-analysis-env/bin/activate
python3 -m pip install -r scripts/paper1/requirements-analysis.txt
sh scripts/link-workspace.sh
npm run test:paper1
npm test
```

`test:paper1` 包含新的研究回归测试；原有 `npm test` 不会自动包含它们。测试数量和实际退出码以 [EXECUTION.md](EXECUTION.md) 及随附日志为准。单元测试、开发用例、模型轮次、claims 和压缩次数均不增加正式研究的独立任务数。

原生宿主默认只进行能力发现：

```bash
python3 scripts/paper1/native_smoke.py --output /tmp/p1-host-preflight
```

在具有已授权 Codex 登录的机器上，显式 `--run --model <model/list返回的模型>` 才会产生模型轮次；每次输出目录必须是新目录。当前保存的 Mac 运行使用 `gpt-5.6-sol`、Codex 0.153.0。输出并不是 D/B/C 三臂实验。

## 尚未具备的实证条件

1. **忠实 Raw-RAG 的实际服务调用。** 官方 checkout 和适配器已准备；运行环境尚无 embedding 与 reranker 的供应商凭据。预检只报告是否存在，不展示密钥。当前未产生这两类模型请求或可报告的基线质量分数。
2. **端到端真实任务链路。** 正式 host adapter 仍需在每次决定时读取并绑定 live workspace/object state；一般自然语言日志的生命周期归一化和抽取准确率仍待建立。当前 archive 接口依赖可信、完整的归一化状态快照。
3. **独立数据与标注。** 8 个开发任务槽位和 16 个新真实任务的 pilot 设计不等于已采集数据。需要不同项目或独立工作流、完整来源、人工审阅义务与成功条件。
4. **可比性及预算冻结。** 当前 Raw-RAG 的 5,000-token 展示适配和 verifier 的每 claim 默认预算不构成已冻结的跨臂总预算。近邻 TierMem/sufficiency 对照新增后，调用量、总成本与运行计划必须重新冻结。
5. **正式结果和投稿版本。** Pilot、功效设计、正式成对实验、外部验证及目标 venue 篇幅改写尚未执行。不能用旧合成试验或本次 smoke 填写结果表。

下一项外部依赖是提供可用的 embedding/reranker 服务配置；不应在聊天、Git 或日志里提交密钥。接入后仍须完成上述真实任务和方法链路，才进入成对 pilot，而不是直接启动大规模实验。
