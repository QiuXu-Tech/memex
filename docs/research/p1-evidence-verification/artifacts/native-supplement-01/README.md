# 第一次追加原生准备：执行结果与证据

更新：2026-11-29（Asia/Shanghai）。用户批准的四次具名追加尝试已全部执行完毕。**DeepSeek 原生工具链已发生十次成功响应，但四次准备均未形成有效的 task-bound 压缩检查点，A/B/C/D 方法单元仍为 0/16 已运行。论文尚无新增正式结果，未投稿。**

本目录保留失败、真实用量、部署和账本的实际记录。机器汇总见 [observations.json](observations.json)。不存在把中断重新登记为未使用、将未测量方法记为失败得分，或以程序测试通过填充论文结果的处理。

## 四次实际尝试

| 具名尝试 | 实际进展 | 终止边界 | 有效检查点 / 方法单元 |
|---|---|---|---|
| w-101 / r1 | 隔离探针、持久 thread/start、turn/start；provider 0 次 | 宿主报告 loopback 502。代理路径为固定源码与机器元数据支持的解释；未抓取该请求的网络包 | 0 / 0 |
| w-101 / r2 | 请求真实到达本地 relay，接收 39,739 B；provider 0 次 | 严格工具声明检查拒绝。默认 Goals 扩展的注册链由固定源码核实，未把未归档的 wire 工具名冒充实测 | 0 / 0 |
| w-102 / r1 | 5 次 DeepSeek completed；1 次 list_files、6 次 read_file | 第 6 次请求在上游派发前被累计参考输入上限拒绝；本次 5 次 generation_start 额度亦已消耗 | 0 / 0 |
| w-102 / r2 | 5 次 DeepSeek completed；1 次 list_files、6 次 read_file | 同一累计参考输入上限拒绝；5 次 generation_start 额度亦已消耗 | 0 / 0 |

后两次没有 write_file、run_current_tests 或 record_review，也未进入抽取和原生压缩。两次都保留为 `capture_incomplete`。它们是源材料上的开发运行，不能据此推断方法成功率为 0%、H1/H2 不成立，或任务已被正式纳入。

[第一失败记录](w-101-r1/result.json)、[第二失败记录](w-101-r2/result.json)、[Requests r1 原始宿主事件](w-102-r1/host-events.jsonl)、[Requests r2 原始宿主事件](w-102-r2/host-events.jsonl)。工具准入和修复的证据链见 [native-wire-routing-01](../native-wire-routing-01/README.md) 与 [persistent-extension-tools.json](../native-wire-routing-01/persistent-extension-tools.json)。

## 实际用量与现金

| 范围 | 上游完成响应 | Provider input | 其中缓存 input | Provider output | 独立 tokenizer 的请求 JSON 参考计数 |
|---|---:|---:|---:|---:|---:|
| w-102 / r1 | 5 | 50,875 | 39,424 | 486 | 54,139 |
| w-102 / r2 | 5 | 51,166 | 47,744 | 601 | 54,467 |
| 本轮合计 | **10** | **102,041** | **87,168** | **1,087** | **108,606** |

缓存 input 是 provider input 的子集，不能再相加。参考 tokenizer 计数不是账单 input，也不能与 provider input 相加。两次各自下一条完整请求会超过该 scope 的 65,536 参考输入上限，拒绝发生在 dispatch record 和上游调用前；上表只累计已派发的十次。每次完成回执及其真实 usage 均保留在各目录的 `dispatches/`，[r1 provider audit](w-102-r1/provider-audit.json)、[r2 provider audit](w-102-r2/provider-audit.json) 可逐条复核。此前的一次独立 DeepSeek 抽取诊断不计入本表。

原授权两次 native 保持已消耗；追加四次已消耗、剩余 0。原 16 个开发方法单元尚未消耗，但目前没有可供这些单元使用的新父检查点。现金总上限仍是 **CNY 100.00**：保留的预留上界 **15.80**，剩余可预留容量 **84.20**，实际费用 **null**。15.80 包括此前未核销的 3.00 和四次各 3.20 的预留，**不是已确认账单金额**；provider 响应已给出 token 用量，不自动核销未知费用。

## 授权、账本与导出

- [原授权](../authorized-batch1/authorization.json)、原 source plan 和 shared budget 保持原字节。
- [补充授权文件](../authorized-batch1/native-preparation-supplement1.json)与[显式激活收据](activation.json)保留。新增授权没有重置旧尝试。
- [canonical events](../authorized-batch1/ledger/events.jsonl)当前为 **50 条**；[HEAD](../authorized-batch1/ledger/HEAD.json)为 `9daabc2b62eff8efd17bd5783decc619f25094c2748fd4e838f2735150a25ed0`。
- 原七条事件的逐字节前缀 SHA-256 仍为 `d675c9c1f868d6169615c877bb6ffc0d88f73813eab0ccf830669ef97f6e47fa`。当前 events 文件 SHA-256 为 `9665b7579605fdf04a1cccc7a886ed8650b2afeebd3f13c862d65b23b8219b41`。
- 所有四个 controller scope 均已 `scope_finished`，所有四个 backend 均已关闭。十个真实 provider 记录均有完整 usage 和不可变 completion。

[原始记录包 native-run-evidence.zip](native-run-evidence.zip) 为 63,852 B，SHA-256 `05bff6a43ffea62679f2f0de5c7eb56104c84b9a18b66e223b6de1690ea732a3`。包内 38 份记录加一份 manifest：35 份保留原字节；2 份 transport 和 1 份 controller trace 仅替换已知私有路径前缀。所有原始私有记录仍保留。[export-manifest.json](export-manifest.json)同时记录原始和发布摘要，[export-verification.json](export-verification.json)记录独立重算。

`runtime-controller-review.jsonl` 是脱敏审阅副本。其行内原始链摘要没有重新签造，因此它不是可重放或可活动的 controller journal；原始 controller 在指定机器保持不变。canonical cash journal 与 HEAD 则是逐字节镜像，未经 JavaScript 数字重序列化。

## 完成的部署与验证

先后公开的三版运行修复均先验证，再由指定机器从明确 public commit 下载，并核对源 SHA。每次部署均保留旧静态代码，不复制或重建活动账本：[初次部署](deployment.json)、[wire 部署](deployment-v2.json)、[扩展工具部署](deployment-v3.json)。[实际零 turn feature 检查](effective-feature-check.json)确认新增工具入口为 false，没有使用模型或创建线程。

| 检查 | 真实结果 |
|---|---|
| 最新 Python 研究全量 | 569 项：560 通过、9 项旧环境 fixture 跳过、0 失败 |
| 本轮 Node 研究全量 | 123 通过、0 失败、0 跳过 |
| 本轮仓库主套件 | 197 通过、4 项因未构建 bundle 跳过 |
| canonical mirror 更新后相关子集 | 85 通过、0 失败、0 跳过；与全量有重叠，不额外累计 |
| AI 辅助标签与 oracle 材料独立审查 | 未发现发布阻断；不冒充真人科学评审或正式研究结果 |

日志和准确覆盖边界见 [validation-v2](validation-v2/summary.json)、[validation-v3](validation-v3/summary.json)、[validation-after-ledger](validation-after-ledger/summary.json)。最初一条 post-mirror 测试命令因模块命名与 Python 自带 test 包冲突而未加载目标测试；修正调用目录后 85 项通过，无生产或测试代码改动，错误调用日志也保留。

## 可由程序或 AI 完成的流程

已完成 [11 包程序预审与 37 条 AI-assisted 义务草案](../remaining-completion-01/assisted-review-v2/README.md)，以及[两套各 5 个用例的有限行为 oracle 资格验证](../remaining-completion-01/oracle-qualification-01/README.md)。资格验证包含 15 个实际 observer、5 个真实隔离探针，282 份发布记录已独立复算；原 Requests 六项草案的真实失败和事后修订保留。它们没有被改称人工 gold、方法最终制品成绩或验收任务。

B 的[真实 clean Git checkout](macos-rawrag-git-checkout.json)和[独立私有配置绑定](macos-rawrag-private-binding.json)已完成。当前[就绪记录](fixed-baseline-readiness.json)仍缺两个指定服务凭据，以及固定 rerank-v3.5 的账户可用性、计费和可核验人民币请求上界；没有用 DeepSeek 生成服务替换固定 embedding/reranker。

本轮授权已执行完毕。继续真实 native 准备需新的具名次数及经过检查的准备阶段预算设计；原 100 元总现金和 16 个方法单元不因此自动扩展。仅再加同配置次数、仅提高 reference input、或把参考用量重置到新 component，都不能视为已证明可行。后续研究和投稿边界统一见 [REMAINING_WORK.md](../../REMAINING_WORK.md)。
