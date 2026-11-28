# 下一批 native 准备：先完成整条调用链的预算设计

**当前应停在离线设计。下一批需要新的具名 native allowance，并同时审查 generation、累计 reference tokens 与后续 extraction／compaction 的预算分配；仅增加相同配置的尝试次数，没有解决本次已经观测到的停止原因。** 原 CNY 100 总现金上限和尚未使用的 16 个 method 单元继续有效，不应把它们作为新增额度重复审批。本文不是授权、运行配置、费用核销或科学结果。

## 1. 已发生的事实

依据 [observations.json](artifacts/native-supplement-01/observations.json)，四次追加 native allowance 已全部消耗，四个 preparation 均为 `capture_incomplete`，没有 sealed checkpoint。A/C/D 未派发，B 仍为 `not_dispatched_dependency_blocked`，全部 `not_scored`；accepted tasks 与 formal results 均为 0。前两次均没有 provider 派发，后两次已有真实 provider 完成记录，不能混为同一种失败；前两次的实测边界与源码解释分别保留在[执行记录](artifacts/native-supplement-01/README.md)。

| 保留观测 | w-102-r1 | w-102-r2 |
| --- | ---: | ---: |
| 完成的 HTTP 请求／`generation_start` | 5／5 | 5／5 |
| 实际 provider input tokens | 50,875 | 51,166 |
| 实际 provider output tokens | 486 | 601 |
| 累计公共 reference input tokens | 54,139 | 54,467 |
| 当前 65,536 reference 上限的余量 | 11,397 | 11,069 |
| 公共工具 | 1 次 list、6 次 read | 1 次 list、6 次 read |

两次第 6 个 wire 请求均在实际 provider 派发前被 `scope_reference_input_budget_exhausted` 拒绝；它不是第 6 次已收费或已完成的 API 调用。两次都没有 `write_file`、`run_current_tests`、`record_review`、extraction、compaction 或 checkpoint。已完成请求的 usage 完整，不代表完整准备链已完成。第 6 个请求只保留字节数、SHA 和拒绝码，没有可据此复算的完整请求正文，不能给出它的精确 reference token 数。[r1 拒绝回执](artifacts/native-supplement-01/w-102-r1/local-rejection.json)、[r2 拒绝回执](artifacts/native-supplement-01/w-102-r2/local-rejection.json)。

原台账当前是 50 个事件，原 native 2/2、追加 native 4/4，method 0/16；保守现金承诺为 CNY 15.80，剩余容量 CNY 84.20，`actual_added_cash_total` 仍为 `null`。余量是准入容量，不是实付余额或允许新增 native 的依据。[汇总及原始证据索引](artifacts/native-supplement-01/observations.json)

## 2. 固定准备链需要分别计数

[prepare_block](../../../scripts/paper1/paired_runtime.py) 的顺序固定为 `capture_parent → prime_D → compact_parent → seal checkpoint`；同一个 native scope 的用量不会因切换组件、host 进程或 lease 而清零。[NativeBackend](../../../scripts/paper1/native_backend.py) 实际执行：

| 阶段 | 必须得到的真实产物 | 预算含义 |
| --- | --- | --- |
| capture_parent | 原请求的真实持久父线程、完成的 prelude、当前 workspace 与完整可观察 archive | 一次 `turn/start` 可包含多轮 HTTP／工具调用；每个 prelude provider 请求都计一次 `generation_start` |
| prime_D | 独立抽取线程的真实 extraction、同一 archive epoch 的 prime receipts／cache | 抽取请求继续计 native generation；实际 archive opens 另计公共操作；不能用预造抽取或 receipt 替代 |
| compact_parent | 对原父线程 `thread/resume` 后真实 `thread/compact/start`，并读取校验原生状态 | compaction 请求计 `compaction_start`，仍消耗同 scope 的 HTTP、reference 和实际 usage 预算 |

设 prelude、extraction、compaction 的实际 HTTP 数分别为 `P、E、C`，prelude 公共工具数为 `T`，prime 实际 archive opens 为 `S`。当前必要约束包括：

- `P + E ≤ 5`（native generation），`C ≤ 2`（native compaction）。
- `P + E + C ≤ 8`（profile HTTP 上限）；全部这些请求的 reference token **求和**不得超过 65,536。
- provider 实际 input 累计阈值 65,536、output 累计上限 8,192 独立检查；参考计数不是 provider 计费 token，也不是单次上下文容量。
- 当前控制器还把每个 provider 请求记作一次 native `public_tool_call`，因此 `P + E + C + T + S ≤ 20`；测试执行另受原 6 次限制。不能只核对模型次数而漏掉这层准入。

按 extraction 和 compaction 各预留一次 provider 请求的最简路径，generation 上限 5 只容许 prelude 使用至多 4 次；本次两次 prelude 都已消耗 5 次，尚未结束。即使第 6 个请求不再被 reference 拒绝，generation 限额仍会阻止继续。以上是必要的算术条件，不是“4 次 prelude 足以完成任务”的证据。[授权与计数](../../../scripts/paper1/batch_limits.py)、[逐请求准入](../../../scripts/paper1/runtime_controller.py)、[固定 profile](../../../scripts/paper1/deepseek-reader-profile.json)、[reference 准入顺序](../../../scripts/paper1/deepseek_native_relay.py)

## 3. 现有证据支持的推断及其限度

r1 六次 read 实际返回 `50、120、441、200、200、200` bytes，共 1,211 bytes；其五次请求的 reference 数依次为 `8,850、9,921、10,876、11,986、12,506`。完整请求历史会随工具往返再次发送，因此多次小页读取会占用请求槽，并反复计入已有上下文。这里有实测的效率问题，但没有证明小页是唯一原因。[r1 host events](artifacts/native-supplement-01/w-102-r1/host-events.jsonl)、[r1 relay audit](artifacts/native-supplement-01/w-102-r1/relay-state.json)

r2 的 read 返回 `120、50、391、400、400、4,000` bytes，最后一页已经达到现有单次上限，仍在同一位置受阻。因此不能承诺“改成大页就能完成”。现有工具描述已经注明 UTF-8 byte page；未来可候选增加任务无关的简明提示：`offset/limit` 是字节，按文件大小选择有用的一页，使用返回的 `next_offset`，避免把 200 当作行数。它必须遵守每次 4,000 bytes、总字节和调用上限，不能增加工具权限，也不能给出任务答案、隐藏评测内容或改动任务测试。[r2 host events](artifacts/native-supplement-01/w-102-r2/host-events.jsonl)、[现有 read_file 合同](../../../scripts/paper1/public_workspace.py)

六次 read 是这两次运行的观测量，并非 native prelude 的独立六次 source-open 上限；prime helper 自身的 `maxSourceOpens=6` 也不能与 prelude 计数混用。

## 4. 下一批应先交付的离线材料

1. **按阶段列预算候选。** 给出 prelude 的 generation／reference 分配，明确保留 extraction、prime 和 compaction 所需请求、公共操作、输出及时间。可比较“保留现有总额、减少 prelude 往返”和“调整 native 准备额度”两类候选；后一类必须明确新的具名 allowance 及所改的每次尝试限制。当前数据不足以证明任何精确新额度足以完成，不在此填一个看似可执行的数字。
2. **对完整请求形状做离线预算证明。** 使用固定 tokenizer 与 pinned host 的完整历史／工具合同，分别检查 prelude、真实抽取输入和 native compaction 的请求上界；保留所有历史、功能调用及输出，不用删历史或手拼摘要降低计数。测试应覆盖阶段预留、reference/generation 各自先耗尽、20 次公共操作的组合边界、缺 usage 后停发和 first-attempt 不可重放。合成响应只能证明控制器可达与计量正确，不能证明模型会完成真实任务。当前没有成功的 extraction／compaction wire 样本，必须把这部分的不确定性保留在报告中。
3. **重算并绑定现金证明。** 若只调整 reference／请求分配而保持实际 usage envelope，仍须验证串行 completion 握手与全部准入边界；若提高实际 input/output 阈值，当前每 scope CNY 3.20 的证明不能原样套用。候选需按新的实际用量上界、最终未知请求、当日价格依据和原账本重新计算保守预留，始终留在原 CNY 100 总额内；不将任何参考计数或估算核销成实际支出。
4. **先发布可审查设计，再形成独立授权与版本。** 下一份具名 native allowance 应绑定新的尝试身份、明确预算、profile／源码／价格证据，并保留全部旧失败 scope 和台账前缀。它只补足 native 准备权限；现有 16 个 method 单元不增加、不重批。成功 seal 后，仍通过同一父 checkpoint、同一 helper epoch 和独立 prime cache 进入原有 A/C/D；B 的固定凭据与 v3.5 账户价格／可用性证据仍另行保留阻断，不换模型、不猜报价。

本文仅完成设计诊断：未改 runner、限额、模型、五个公共工具、public task、测试、profile、授权或账本；未生成 active grant、attempt 或 reservation。本文分析所用 observations 文件 SHA-256 为 `95ba8d536338ef3aebc056031fc2afcb1007e90323102141154e9994c9b2e7c3`。
