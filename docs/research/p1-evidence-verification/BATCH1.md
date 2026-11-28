# P1 第 1 批：已批准范围与执行额度

日期：**2026-11-28，Asia/Shanghai**。用户对紧邻的《P1 统一审批单 · 第 1 批》回复 **“全部批准”**。

[authorization.json](artifacts/authorized-batch1/authorization.json) 记录这项会话授权，并固定到当时已有的两来源开发计划。它不是原生宿主的批准回执，不证明账户可用、任务验收、独立标注或科学结果。此前公开研究分支和草稿 PR 的授权继续有效。

当前[实际执行记录](artifacts/authorized-batch1/README.md)：两次原生尝试均已使用并以 timeout 结束，第二次已观察到真实单次审批、测试、两次压缩及部分后续行为。16 个方法单元仅完成准备，尚未执行；两份 Python 固定测试采集另行记录。权限与额度状态见 [ledger-status.json](artifacts/authorized-batch1/ledger-status.json)。

## 1. 本批明确上限

| 范围 | 已批准上限 |
|---|---|
| 新的完整原生开发尝试 | 2 次；每次最多 5 次可观察生成开始、2 次压缩、600 秒总时限 |
| 两来源开发运行单元 | Flask、Requests 两份来源材料 × A/B/C/D 四种方法 × 2 次重复，共 16 个；每单元最多 300 秒 |
| 新增按量现金支出 | **合计人民币 100.00 元**，包含诊断、失败请求及重试；不是每项分别 100 元 |
| 账户与输入 | 用户指定的现有服务账户；经过检查的公开研究输入 |
| 仍不在本批内 | 新订阅、GPU 租赁、自动充值、付费聘请标注人员、编辑通信、期刊/预印本提交、合并 main |

现有订阅额度仍可能被消耗。“新增现金支出为零”的依据不等于完整模型成本为零。服务配置、计费上界或真实宿主批准不具备时，相关执行保持阻断；不会以模拟响应替代真实调用。

两来源计划、共同预算文件及各公开输入摘要均被授权记录绑定。该记录维持 `phase=development`、`frozen=false`、`accepted_p1_tasks=0`。这是批准时的事实和本批范围，不是正式实验冻结。修改任务或预算文件后必须重新核对，不能悄悄沿用旧摘要。

## 2. 额度台账

实现：[batch_limits.py](../../../scripts/paper1/batch_limits.py)。

本批所有本地和远程控制器必须共用主控仓库中的唯一目录：

`docs/research/p1-evidence-verification/artifacts/authorized-batch1/ledger/`

远程进程由主控先预留额度后启动；不能在每个临时克隆中各新建一份台账。`BatchLedger` 拒绝在同一仓库中指定另一台账目录，但跨机器复制目录不是本工具能提供的分布式或操作系统隔离保证。

- `status` 为只读，空状态不创建目录或文件。
- `reserve` 默认 dry-run，只有显式 `run=True` / `--run` 才写入预留。
- 首次预留先使用文件锁，再持久化带前序哈希的事件和独立 HEAD。只有写入成功才允许控制器继续调度。
- 同一尝试 ID 或同一方法单元不能再次预留。失败、超时、审批阻断和进程崩溃均不退还已启动尝试名额。
- 原生生成、压缩、固定测试和公开工具调用可在实际动作前分别预留计数；已有开发 broker 的更严格限制继续有效。
- 每次动作前检查总时限及时间回退。真正运行的宿主/子进程仍须执行自己的超时和终止逻辑；台账不会自动杀死进程。
- 未知结算继续占用其现金上界，不作为零费用释放。之后只有有哈希依据的完整实际结算才能释放差额；尝试名额始终不返还。
- 实际费用若高于事先上界，先保留真实超支记录，再阻止后续调度。不能为了账面满足预算而丢弃该记录。
- 删除、空截断、有效前缀截断、部分尾行或 HEAD 不一致均停止调度，要求核对原始记录；不会自动清空并重启额度。

文件哈希只证明引用字节和完整性，不认证发票内容、真人身份或价格真实性。控制器负责确认计费依据涵盖**整次尝试及失败、重试、汇兑/收费附加项**。当前没有用假价格或假账单补齐该条件。

## 3. 调用方式

只读状态：

```bash
python3 -B scripts/paper1/batch_limits.py status
```

只读授权结构检查，供其他准备工具使用：

```python
import runpy
from pathlib import Path

api = runpy.run_path('scripts/paper1/batch_limits.py')
auth_path = Path('docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json')
authorization = api['validate_authorization'](api['read_json'](auth_path))
ledger = api['BatchLedger'](auth_path, repo_root=Path.cwd())
status = ledger.status()
```

实际调用的控制器按顺序执行：

1. 核实运行条件、授权范围、整个尝试的新增费用上界及其依据。
2. `reserve(kind='native'|'method', attempt_id=..., upper_bound_cny='金额字符串', billing_basis=..., unit=..., run=True)`。
3. 接入中央动作计数的控制器在动作前调用 `record_event(attempt_id, kind, operation_id)`。动作类别为 `generation_start`、`compaction_start`、`test_execution` 或 `public_tool_call`；方法材料还可记录 `source_open`。本批远程 native 控制器只在中央预留整次尝试，并在远端 `summary.json` 中于派发前持久化生成/压缩计数；最多 5 次生成和 2 次压缩由冻结的控制器执行。不得在运行后将观察值补写成中央事前预留。
4. 成功或失败都调用 `finish(attempt_id, status=..., actual_added_cost_cny=None)`；未知账单保持预留。
5. 后续完整结算用 `settle_cost(..., actual_added_cost_cny='金额字符串', cost_evidence=...)` 记录。

`billing_basis` 的结构为 `{kind, evidence:{ref,sha256}}`。`kind=included_subscription` 只用于有证据证明不产生新增现金支出的既有订阅范围，上界为 `0.00`；`kind=priced_upper_bound` 要求正数上界。`ref` 必须是仓库相对路径，所指依据文件的真实 SHA-256 必须匹配。`cost_evidence` 使用同一 `{ref,sha256}` 结构。这里没有提供假造的可执行计费依据。

方法单元 `unit` 使用 `w-101:A:1` 等明确身份。预留前重新核对原来源计划、共同预算文件和实际公开目录摘要。台账不提供模型输入目录隔离；实际执行器必须单独挂载经过验证的公开目录。

### 原生单次许可

主控在唯一中央台账预留后，为该 reservation 只签发一份固定路径 permit，绑定授权、运行源代码、模型、全新输出目录和期限。当前远端运行时限为 **480 秒**，permit 最迟在中央预留后 **600 秒**失效，余量用于传输和收尾。`native_permit.py` 检查这些绑定，并以原子独占文件记录一次性消费。它不读取中央 journal，不独立证明全局两次配额，也不证明真人在场；全局预算依赖主控不重复签发。

普通工具请求由 `PriorChatApprovals` 依据本次会话授权单次回应，日志明确 `prior_chat_authorization` 与 `identityAttested=false`。只允许真实未完成调用中的 `run_current_tests` 和 `record_decision`；不返回持久授权。未知表单、显式设备/本人验证或严格复核请求仍拒绝，详见 [APPROVALS.md](APPROVALS.md)。

## 4. 验证范围

专门套件 [test_paper1_batch_limits.py](../../../test/test_paper1_batch_limits.py) **23 项通过**，覆盖多进程竞争、已落盘预留后的真实子进程退出、未知费用保留、已知结算、超支保留、重复调度、计数/时限、计划/输入漂移、授权变更、符号链接和日志损坏。

这些测试只使用临时文件与本地受控子进程，没有供应商请求、模型生成、密钥创建、原生宿主批准或正式研究运行。台账本身不启动任何外部工作；实际批次进度以其当前状态和真实运行收据为准。
