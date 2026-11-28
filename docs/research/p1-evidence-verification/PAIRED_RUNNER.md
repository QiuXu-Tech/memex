# P1 两来源批次：公开输入准备与运行前检查

**授权已记录；两份真实 Python 公开源码的固定测试采集已完成。四臂方法运行仍未接通。** 更新：2026-11-28（Asia/Shanghai）。本页对应 `scripts/paper1/paired_runner.py`、`python_workflow.py` 与 `python_workflow_child.py`。零调用预检、公共输入导出、真实固定测试观察器和执行器失败回执均有可运行实现。

## 已实现的工作

1. 把本批限定为 `w-101` / Flask 与 `w-102` / Requests、A/B/C/D、两次重复，共 16 个开发单元。按照完整的 `source-draft-plan.json` 与实际包重新计算比较，拒绝 80 单元计划、重复单元、其他来源、臂、路径或输入摘要。
2. 完整调用任务包验证，核对固定来源公开字节、权限和目录。初始 reader 输入只含任务描述符、原始请求和共同预算；整棵源码树不是免费上下文，controller/evaluator 不进入该输入。序列化包装的字节数也计入初始预算，超限直接拒绝。
3. 以新的输出目录导出两个 public 子树，保持与源树相同的两套摘要，并生成 16 个绑定明确、未调度的运行单元。所有臂在同一来源上得到同一公开输入与 300 秒上限。
4. 通过 `batch_limits.validate_authorization` 读取用户的统一批准记录，并额外核对 source plan、shared budget 文件字节 SHA 与 16 个单元的公开输入绑定。这个步骤不创建台账、预留尝试或产生任何计费请求。
5. 若误把该脚本配置成 `experiment.py` 的可执行 runner，脚本会按已有 ABI 写出 `host_error`、`source_workflow_backend_not_implemented` 和零后端调用的阻断记录。它不会返回 `completed`，也不会制造全零费用记录。外层可能已经预留的首次尝试应保留，不能改回未开始。
6. `python_workflow.py` 严格接收这两棵清洁 public 树；复制当前源码，执行固定公开测试模块，记录真实进程退出、信号、超时、完整输出及摘要、pytest 收集与逐测试阶段、实际项目模块来源、测试前后源码与依赖树摘要。采集只在显式 `execute --run` 时发生；预检和准备不执行源码。

## 三个状态分开报告

| 字段 | 本批实际含义 |
|---|---|
| `permissions_granted=true` | 提供的授权记录与这份具体计划匹配；不是宿主批准或人类身份认证。未传授权记录时为 null。 |
| `runtime_ready=false` | Python 固定测试观察器及两次源码采集已实现，但仍没有该任务的诊断/编辑前置轨迹、原生压缩 checkpoint、共享完整原始事件与完整四臂运行环境。 |
| `scientific_ready=false` | 任务验收、独立人工审阅、评分与正式研究冻结均未完成。 |

凭据检查只输出 `VECTORIZE_API_KEY` / `RERANK_API_KEY` 的存在布尔值，不读取 env 文件、不报告密钥、不联系服务。即使变量存在，也保留 `credential_access_verified=false`，B 的真实供应商访问与 checkpoint 绑定仍待验证。

## 可直接执行的预检

从仓库根运行；输出完整 JSON 报告，无模型、来源测试或供应商请求：

```bash
python -B scripts/paper1/paired_runner.py inspect \
  --plan docs/research/p1-evidence-verification/tasks/workflows/source-draft-plan.json \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101 \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-102 \
  --authorization docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json
```

不传 `--authorization` 仍可检查输入，但不会推断已有运行许可。现有授权继续有效，未配置密钥或缺少运行后端也不等于用户未批准。

## 导出仅含公开资料的任务根

将最后一项换成新的绝对目录。输出不得已存在，不得位于来源包内，也不得覆盖其祖先；路径的符号链接部分会被拒绝：

```bash
python -B scripts/paper1/paired_runner.py stage \
  --plan docs/research/p1-evidence-verification/tasks/workflows/source-draft-plan.json \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101 \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-102 \
  --authorization docs/research/p1-evidence-verification/artifacts/authorized-batch1/authorization.json \
  --output /absolute/new/p1-batch1-inputs
```

输出包含：

- `public/w-101/` 和 `public/w-102/`：各方法未来只应挂载其中对应的一棵；文件保持原始 public 字节与模式。
- `controller/preparation.json`：全批准备结果、权限记录摘要、公开树摘要和 16 个单元。
- `controller/units.json`：明确标记 `prepared_not_dispatched` 的单元清单。
- `controller/runtime-readiness.json`：逐来源、逐臂的阻断条件。
- `controller/backend-contract.json`：后端需要接通的实际操作与 checkpoint 身份字段。

**导出目录不是 OS 沙箱。** 不能把包含 controller 的输出根或整个研究仓库挂给模型；后续运行仍须实施宿主/操作系统的隔离和工具边界。本命令不会把路径隔开就声称隔离已经成立。

## 为什么当前不能启动 16 个真实方法单元

两个来源的 `public/task.json` 都是 `material_kind=real_source_seed`、`archive_path=null`。此前 base/fix 回归复现和本次清洁公开源码固定测试，都没有完成自然语言任务的诊断、修复、后续变化和压缩前置过程，不能用于补造压缩前状态。另一个 Node/TAP 合成工作流的宿主成功也不能替代这两个 Python 来源的当前状态。

具体还需接通：

- 在实际公开工作区捕获任务诊断、编辑和后续状态变化，把已实现的 Python 固定测试观察器接入这些真实动作。
- 将已有进程、测试计数、模块 origin 和前后版本捕获绑定到任务 checkpoint，形成所有方法共享的完整原始事件视图。当前 receipt 不冒充 native host 事件或 Memex archive。
- 实际压缩共同 native parent，保留原生完成收据，再为四臂从同一个未变化的 parent 分叉。
- B 调用固定官方 Raw-RAG 与原始请求；C/D 使用真实抽取结果，D 的预核验及复用均绑定同一 checkpoint。不能用关键词、假 embedding 或手工正确 claim 补位。
- 固定并实施共同 reader、tokenizer、工具及 token 上限；保留实际继续行动和完整计量，再接回 `experiment.py` 的首次尝试、成本与评分合同。

`backend-contract.json` 是这些具体接口的枚举，`implementation_registered=false`。提供一份写着 true 的配置，或填入一个已有 native thread ID，不能使未实现后端变成可执行。

## 真实 Python 源码采集与复现入口

本批在明确授权的 `controller-only` 开发模式下，各运行一次原始公开测试。结果位于 `artifacts/authorized-batch1/python-workflows/`：

| 公开来源 | 固定原始测试 | 实际收集 | 通过 | 跳过 | 失败/错误 | 真实 exit |
|---|---|---:|---:|---:|---:|---:|
| `w-101` / Flask | `tests/test_blueprints.py` | 59 | 59 | 0 | 0 | 0 |
| `w-102` / Requests | `tests/test_utils.py` | 212 | 201 | 11 | 0 | 0 |

这两个数量来自本次真实逐测试观察，未复用此前应用官方测试补丁的 60/214 结果。两次执行的公开工作区、实际执行副本、依赖树在前后均保持同一摘要。没有调用模型、供应商、安装器或上游服务；`method_attempts_reserved=0`、`accepted_p1_task_count=0`。原公开测试通过仍不证明空 blueprint 名称或代理认证的需求已被修复。

执行环境是现有 CPython 3.10.16；Flask 固定 pytest 7.2.2，Requests 固定 pytest 6.2.5 和显式 `pytest_mock` 2.0.0。完整依赖版本逐一核对既有 `requirements-pinned.txt`。旧环境含指向 evaluator 复现仓库的 editable 文件，因此启动参数为 **`-I -S -B`**：不处理 `.pth`/`.egg-link`，只显式加入依赖目录与本次公开副本，核对实际项目模块 origin 和对应内容 SHA。Requests 的已知依赖兼容别名单列，并绑定相应依赖对象/文件；不会把它们误称为项目源码。

开发模式清空继承环境、固定模块选择、禁自动插件，使用独立临时目录及明确的 `--rootdir`/`--confcutdir`。Python audit hook 拒绝连接、DNS 与发送；Requests 的 urllib3 导入时仅发生一次 `::1` 端口 0 的本地能力探测 bind，没有监听、连接或发送。**这是经过检查的 controller 开发运行，不是 OS 隔离证明，也不准入模型编辑后的任意源码或正式多方法实验。** 当前 controller-only 入口拒绝任何偏离两份原始 public 摘要的输入。

可复现的顺序如下；需要把三个环境路径换成现有目录，不能覆盖已存在的 session 或 export：

```bash
python -B scripts/paper1/python_workflow.py inspect \
  --public docs/research/p1-evidence-verification/tasks/workflows/packages/w-101/public \
  --python /absolute/existing/flask-venv/bin/python

python -B scripts/paper1/python_workflow.py prepare \
  --public docs/research/p1-evidence-verification/tasks/workflows/packages/w-101/public \
  --session /absolute/new/controller-session

python -B scripts/paper1/python_workflow.py execute \
  --session /absolute/new/controller-session \
  --python /absolute/existing/flask-venv/bin/python \
  --output /absolute/new/public-capture \
  --execution-mode controller-only --timeout 300 --run
```

Requests 只需选择 `w-102/public` 和对应已有依赖环境；固定测试与显式插件由代码选择，调用者不能注入任意命令。去掉 `--run` 是只读准入，不建立 attempt、输出或预算记录。实际尝试使用递增编号和新文件，失败会保留；退出 0、全 skip、collection error、输出超限或缺失阶段都不会被猜测为成功。

每份公开采集包含 `capture.json`、原始字节与公开字节分别校验的 stdout/stderr、结构 pytest 观察、合法 JUnit XML、前后文件清单。私有控制器保留完整原字节，公开副本透明替换主机路径与 hostname。本次检查发现 JUnit 参数中的路径替换需经过 XML 转义，已修复导出器，并保留 v1 副本、原 raw SHA 与 `export-repair.json`；**没有因此重新执行源码**。实际执行时的控制器/observer 原字节和摘要保存在 `python-workflows/provenance/`，与后续导出格式修复明确区分。

## 验证

```bash
python -B -m unittest discover -s test -p 'test_paper1_paired_runner.py' -v
python -B -m unittest discover -s test -p 'test_paper1_python_workflow.py' -v
```

paired runner 定向套件 19 项；Python capture 定向套件 19 项。后者使用自有微型 pytest 夹具验证真实退出与输出、超时/截断、collection/teardown 失败、xfail、导入污染、Requests 兼容别名、网络 guard、只读不启动、失败保留与 XML 转义。单元测试不执行两个上游来源；上表的两次来源执行单独记录。两类工程测试数量均不增加 P1 研究样本。
