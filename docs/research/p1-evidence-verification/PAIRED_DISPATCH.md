# P1 配对运行与实验调度的连接

状态：**已实现同进程调度合同，并以明确的工程 fixture 验证；真实任务的全臂执行仍未完成，scientific readiness 为 false。** 本接口不会创建 native 额度、人工评分或新的现金账本。

[paired_dispatch.py](../../../scripts/paper1/paired_dispatch.py) 将同一个存活的 `NativeBackend` / L2 helper 接入原 [experiment.py](../../../scripts/paper1/experiment.py) 首次尝试路径。解决的问题是：若每个方法单元都重启 backend，C/D 就失去原 prime-cache 的 archive epoch；从 JSON 读回一组 receipt 不等于原缓存可继续复用。

## 1. 冻结实际实现的身份

`create_binding(new_path)` 创建一个只含严格实现绑定和失败退出行为的 executable 文件。绑定覆盖宿主 helper、`scripts/paper1` 下相关 Python/JavaScript/JSON、Memex core 的入口、实现目录及 package 描述的实际 SHA-256。路径必须位于这些实现目录之外，防止自身包含；已有文件不覆盖。

这个 executable 被普通 subprocess 启动时会明确拒绝执行单元。它不是一个表面上冻结、实际运行另一份代码的空 wrapper。`load_binding` 会重新枚举并核对实际实现树、固定 entrypoint、每个文件摘要及整个 executable 的精确内容；添加、删除或修改纳入绑定的实现均使旧绑定失效。文件绑定不替代外部 SDK、解释器、模型、账户、工具和数据的各自版本与运行检查。

把 `create_binding` 返回的 runner 路径写入正常 study spec，再用原 `freeze_study` 冻结；不要修改已有冻结计划的 runner 或摘要。创建 binding 只冻结实现身份，不创建 study、方法尝试、native 许可或研究任务验收。

## 2. 同一后端、每次一个冻结单元

```python
launcher = PairedLauncher(
    plan=frozen_plan,
    state=experiment_state,
    checkpoints={
        (task_id, replicate): task_bound_checkpoint_path,
    },
    backend=existing_live_backend,
    controller=original_canonical_controller,
    execution_mode="live",
)

# 默认仅查看待执行清单；不预留或派发新单元。
inspection = experiment.dispatch(frozen_plan, experiment_state, launcher=launcher)
```

checkpoint map 必须恰好覆盖冻结 schedule 中的所有 task×replicate。每份 checkpoint 绑定任务、项目、public path / 摘要、原请求、真实压缩父状态和 seal。live 模式要求实际 `NativeBackend`，C/D 还要求该 backend 中原证据 helper 正在存活。一个 fixture backend、另一个场景的 smoke、已退出 helper 或重新构造的 archive epoch 不会被接受为同一 live 状态。

每次调用严格核对冻结 runner、public、arm、replicate、run ID、output、cwd、传入 environment 合同及 timeout。随后检查原 `run-ledger.jsonl` 中已持久化的确切首次尝试，才调用 `paired_runtime.run_unit` **一次**。不能跳过原 dispatcher 直接伪造一个未预留的单元调用，也不能在同一 launcher 内复用 run ID。

初始化时锁定的实现/检查点绑定在之后每次调用重新验证；已开始的 study 不能改换 launcher 绑定后继续派发。公共输入再次核对，工作区由原 runtime 独立复制。调用方保留同一 backend/controller 直到所有相关单元结束，再关闭它们；本接口没有后台 daemon，也不提供丢失 live helper 后的假恢复。

实际执行仍需调用方显式传 `run=True`，且每个 scope/provider request 都必须通过原 canonical controller 的权限、次数、时间和现金准入。driver 的四臂 block 是独立入口，不能塞进此单元 ABI；见 [NATIVE_DRIVER.md](NATIVE_DRIVER.md)。当前已消耗的两次 native 额度不会因为增加这一接口而恢复。

## 3. 原失败分母、用量和封存继续生效

`experiment.dispatch(..., launcher=...)` 是新增的可选接口；不提供 launcher 时仍用原 subprocess runner。传入 launcher 时，外层继续负责：

- 冻结计划和 runner 身份检查，以及实际 public 字节检查。
- 在执行前持久化 `run_started`；中断或失败不会使该单元重新成为可择优运行的 pending 项。
- 全局/单元时限、返回状态、原 usage 收集、terminal seal 和后续 `sealed_score_rows` / join。
- 已启动 study 的 launcher 身份一致性，以及全部失败/缺失分母保留。

launcher 从入口开始计算 monotonic 时间，扣除实现树、checkpoint 和调用身份核对实际耗时，再向 `run_unit` 传剩余时限并保留清理余量。外层也检查总 elapsed。同步 Python callable 不具备任意代码的强制抢占能力；实际宿主、测试、helper 与 provider 子调用仍须执行 backend 的截止/取消合同。

callback 异常、超时或 `capture_incomplete` 会令用量捕获不完整。即使已有可解析的 JSONL 前缀，也不能据此宣称费用完整。返回码 0 只说明 launcher 交回了结构化状态，实际状态仍由 result/terminal 记录决定；这里不产生 `decision_success`。成本由原 `experiment.py join` 按封存计量与冻结费率重算，未知部分保持 null；独立真人评分另见 [SCORING.md](SCORING.md)。

`launcher_invocations` 记录调用次数。in-process 路径的 `external_processes_started=0` 专指未启动 **runner wrapper 子进程**；`external_process_counter_scope=runner_wrapper_only` 明确这一口径。backend 内部仍可能启动真实宿主/工具/helper 进程，不能把该 0 解释为全部运行无进程、无模型或免费。模型调用总数未在此聚合时保持 null。

## 4. 实际工程验证与剩余事实

[test_paper1_paired_dispatch.py](../../../test/test_paper1_paired_dispatch.py) 的主 fixture 实际经过 `freeze → dispatch(launcher) → run_unit → usage/terminal seal`：冻结 **A/C/D 三个开发单元**，使用同一个明确标为 `contract_fixture` 的 backend，得到 3 次 launcher 调用、3 次不同分叉和 3 份可供独立评分的 seal；再次 dispatch 不启动第 4 次调用。这里没有真实 provider、B dense/rerank 请求、自然 native 轨迹或真人标注，不计研究 N。

边界测试另覆盖零派发 dry run、实际实现修改、study/launcher 绑定改变、fixture 冒充 live、缺少首次尝试 reservation 以及异常后的不完整用量。这些工程断言与真实研究验收分开记录。复核入口：

```bash
PYTHONPATH=test:scripts/paper1 python -B -m unittest test_paper1_paired_dispatch -v
```

尚缺的事实包括本任务真实 checkpoint、足够且未消耗的原生额度、B 的固定服务配置和有效计费依据、全臂实际结果、完整计量以及独立人类标注。实现连接已经补齐；这些事实不能从 fixture 或 wrapper 成功推定。当前论文的 [零结果报告](artifacts/remaining-completion-01/reporting/README.md)仍为 **NOT MEASURED**。
