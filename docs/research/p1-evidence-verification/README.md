# P1：原生上下文压缩后的证据核验

更新：**2026-11-28，Asia/Shanghai**。研究分支：`research/p1-evidence-verification`。基于 Memex `49e772bbf60532682771874b7ec96958f4a179e3`。

用户已明确授权公开；[研究分支](https://github.com/QiuXu-Tech/memex/tree/research/p1-evidence-verification)和[草稿 PR #9](https://github.com/QiuXu-Tech/memex/pull/9)已建立。

## 当前交付

英文题目：**When to Reopen the Source: Evidence Verification after Native Agent Compaction**。

当前交付是一份可审阅的英文方法与实验协议工作稿，以及可运行、可检查失败的研究原型。**尚无新的正式对照实验结果，也尚未投稿。** 文稿的结果占位符不代表零分或实验失败。

| 内容 | 入口 | 状态 |
|---|---|---|
| 英文工作稿 | [PDF](manuscript.pdf)、[Markdown](manuscript.md)、[LaTeX](manuscript.tex)、[参考文献](references.bib) | 扩展方法与协议稿；16 条参考记录；56 个 `PENDING` 结果占位符；页数以 BUILD 为准 |
| 实验与统计协议 | [PROTOCOL.md](PROTOCOL.md) | 公开输入、独立任务、失败分母、H1/H2、成本口径与冻结条件 |
| 强基线 | [BASELINE.md](BASELINE.md) | 固定官方 Raw-RAG commit；实际供应商检索调用仍待凭据 |
| 执行与审查证据 | [EXECUTION.md](EXECUTION.md)、[REVIEW.md](REVIEW.md) | 记录完成事项、修复、失败和未解决边界 |
| 原生宿主开发验证 | [运行说明](artifacts/native-smoke/README.md)、[最终摘要](artifacts/native-smoke/native-smoke-02-resumed-final/summary.json) | 真实原生压缩与续跑完成；一个合成开发工作流 |
| 真实日志离线回放 | [回放说明](artifacts/replay/native-smoke-02/REPORT.md) | 原生工具事件接入研究核验器；不是在线方法臂的性能实验 |
| 实时状态与新原生接入 | [LIVE_STATE.md](LIVE_STATE.md)、[LIVE_HOST.md](LIVE_HOST.md) | 本地实际执行/L2/失鲜拒绝链路通过；原生写工具审批阻断；只读抽取同家族修订复测有记录 |
| 执行、成本与评分绑定 | [EXPERIMENT.md](EXPERIMENT.md) | 冻结、首次调度、完整组件封口、具体执行绑定、独立评分合并；37 项契约测试 |
| 真实来源与环境复现 | [候选采集](tasks/acquisition/README.md)、[真实复现](tasks/reproduction/README.md) | 16 来源候选/8 项目；2 项实际红→绿；0 个验收冻结的 P1 任务 |
| 投稿准备 | [SUBMISSION.md](SUBMISSION.md) | 暂定目标、官方要求、作者与结果门槛；尚未提交 |
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
- `live-state.mjs`、`live-broker.mjs`：每次决策重读指定文件/环境，绑定实际执行前后状态；真实 L2 接入、缓存失效、有界公开工具与新会话限制。
- `native_live.py`、`live_mcp.py`：当前工作区原生接入控制器和三工具公开界面；真实运行的阻断与独立抽取结果见 [记录](artifacts/live-native/README.md)。
- `experiment.py`：`freeze → dispatch → score-inputs → join`；完整费用未知时保留 null，评分必须绑定具体封存执行，首次失败不能被重跑覆盖。

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

最新完整套件实际为 **65 项 Node + 119 项 Python = 184 项通过**，零失败/跳过。原仓库测试另为 193 项实际通过、4 项跳过；不能把跳过计成执行通过。

原生宿主默认只进行能力发现：

```bash
python3 scripts/paper1/native_smoke.py --output /tmp/p1-host-preflight
```

在具有已授权 Codex 登录的机器上，显式 `--run --model <model/list返回的模型>` 才会产生模型轮次；每次输出目录必须是新目录。当前保存的 Mac 运行使用 `gpt-5.6-sol`、Codex 0.153.0。输出并不是 D/B/C 三臂实验。

## 尚未具备的实证条件

1. **忠实 Raw-RAG 的实际服务调用。** 官方 checkout 和适配器已准备；运行环境尚无 embedding 与 reranker 的供应商凭据。预检只报告是否存在，不展示密钥。当前未产生这两类模型请求或可报告的基线质量分数。
2. **端到端真实任务链路。** 当前 Node 目标的实时状态绑定和执行 broker 已实现；原生联调实际停在写工具审批，须由支持审批的客户端接通。一般自然语言生命周期归一化、其他运行时和抽取准确率仍待建立。单独抽取复测不能替代原生闭环。
3. **独立数据与标注。** 已有 16 个真实来源候选、8 个项目和 2 项程序复现；这些尚未转化为验收冻结的 P1 工作流。还需公开/隐藏输入隔离、相关状态变化与压缩后行为，以及独立双人义务标注。
4. **可比性及预算冻结。** 当前 Raw-RAG 的 5,000-token 展示适配和 verifier 的每 claim 默认预算不构成已冻结的跨臂总预算。近邻 TierMem/sufficiency 对照新增后，调用量、总成本与运行计划必须重新冻结。
5. **正式结果和投稿版本。** Pilot、功效设计、正式成对实验、外部验证及目标 venue 篇幅改写尚未执行。不能用旧合成试验或本次 smoke 填写结果表。

当前外部依赖包括原生写工具的真实批准通道、可用的 embedding/reranker 服务和人工研究标注/作者确认。密钥不应进入聊天、Git 或日志。接入后仍须完成真实任务和方法验收、共享预算冻结与成对 pilot，才进入正式实验。
