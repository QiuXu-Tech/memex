# P1 开发任务材料与 public 导出

**状态：材料已生成并通过完整性检查；P1 工作流验收数仍为 0。** 本批不调用模型，不执行原生压缩，不报告方法成功率。来源程序的 base→fix 复现、合成开发事件、完整 P1 工作流是三个不同的证据层次。

本页对应 [任务材料目录](tasks/workflows/README.md)、[机器可读目录](tasks/workflows/catalog.json) 和 [标注流程](ANNOTATION.md)。正式设计仍以 [PROTOCOL.md](PROTOCOL.md) 为准；这里补齐可检查的文件和操作入口，不替代协议或真实实验。

## 1. 本批实际交付

| 材料 | 实际数量 | 状态及可用范围 |
|---|---:|---|
| 固定 base 的真实来源包 | 2 | Flask 与 Requests；已有程序复现来源，重新导出干净 base，未建立原生 P1 工作流。 |
| 合成开发家族 | 8 | D01–D08 的公开工作区、原始事件样例、控制器计划和隐藏检查草案。 |
| 合成公开分支 | 9 | D01 有 changed 与 unchanged 两分支，其余各一个；D01 的两个分支属于同一家族。 |
| 物理任务包 | 11 | 2 个真实来源种子 + 9 个合成分支；不是 11 个已验收研究任务。 |
| 盲审模板包 | 22 | 每个物理包两份自包含材料，身份、标签、签署时间均未填。 |
| 已完成独立人工审阅 / 裁决 | 0 / 0 | 生成模板不增加人工审阅计数。 |
| 本批原生压缩 / 方法调用 / 行为评分 | 0 / 0 / 0 | 其他宿主 smoke 收据不能自动归属于这些任务。 |
| accepted P1 工作流 / frozen pilot 任务 | 0 / 0 | 各包的 acceptance 收据逐项列出缺口。 |

默认 [draft-plan.json](tasks/workflows/draft-plan.json) 选择八个开发家族的主分支和两个来源包：`10×4 arms×2 replicates=80` 个**计划单元**。这些单元只经过结构审查，没有执行。单独的 [source-draft-plan.json](tasks/workflows/source-draft-plan.json) 含两来源包的 16 个计划单元。重复种子、条件臂和 D01 反事实分支均不增加独立任务 N。

## 2. 两个真实来源包

| 内部 public handle | 来源，仅 controller/evaluator 持有完整映射 | 固定 base | public 文件与字节 |
|---|---|---|---:|
| `w-101` | [Flask issue 5010](https://github.com/pallets/flask/issues/5010)，来源候选 `pallets__flask-5014` | `7ee9ceb71e868944a46e1ff00b506772a53a4f1d` | 102 文件，546,845 B |
| `w-102` | [Requests issue 6027](https://github.com/psf/requests/issues/6027)，来源候选 `psf__requests-6028` | `0192aac24123735b3eaf9b08df46429bb770c283` | 44 文件，349,608 B |

数字包括 `task.json`、自然请求、共同预算和工作区文件，不包括 controller/evaluator。来源、许可证证据及官方数据定位见 [acquisition](tasks/acquisition/README.md)。真实程序复现的原始日志与限制见 [reproduction](tasks/reproduction/README.md)。两份新包只引用复现收据，并将收据 SHA-256、base/fix 身份和实际 F2P/P2P 复现资格绑定；没有把该复现改称 P1 分数。

公开请求根据问题行为独立改写，不复制许可未明确的 issue 全文。Flask 请求描述空 blueprint 名称；Requests 请求描述 Python 3.8.12 上的代理认证失败，并要求本地复现。请求不提供未来修复提交、官方 patch、官方测试 patch、F2P/P2P 标签或正确文件定位。模型可自行检查固定 base 中原本存在的代码和测试。

### 固定 base 导出的具体边界

打包器通过 `git ls-tree` 获取固定 commit 的文件清单，再按白名单用 `git cat-file blob` 读取原始字节。它不读取 clone 的当前工作树，不复制 `.git`，不包含后来应用的修复或官方回归测试。导出清单保存每个文件的 Git blob、SHA-256、字节数及白名单；来源许可证原文随包保留，Requests 的 `NOTICE` 也被保留。

Flask 白名单覆盖 `src/`、`tests/`、`requirements/` 和必要的项目元数据；Requests 覆盖 `requests/`、`tests/` 及必要元数据。它们是明确选择的 base 子树，**不是完整仓库镜像**。文档、历史 Git 对象和未列入白名单的目录不在 public 内。

首次实际打包被严格的 `.env` 防线拒绝：Flask 的 base 自带 `tests/test_apps/.env` 测试夹具。随后显式排除该文件，并在 `controller/source-export.json` 的 `excluded_files` 中保留其路径、Git blob 与原因；未读取用户环境文件。失败与修复记录位于 [checks/first-materialization-rejected](tasks/workflows/checks/first-materialization-rejected/receipt.json)。因此不能声称导出的整套 upstream CLI dotenv 测试与原树等价。P1 正式使用前须独立验证实际选择的测试范围及依赖；此前完成的程序复现也不能自动视为新 public 树的执行结果。

## 3. 八个开发家族的材料

| 家族 | 包 | 已物化的观察与工作区 | 隐藏检查仍是未审阅设计 |
|---|---|---|---|
| D01 | `d-201`、`d-201-unchanged` | 旧制品测试通过后发生相关编辑，以及未编辑的反事实分支；制品字节和摘要明确。 | 对实际最终制品重测或在充分核验后复用；两个分支不能作独立 N。 |
| D02 | `d-202` | completed/pass、cancelled、NOT RUN、零断言、无关命令退出 0。 | 对所要求的目标测试逐项判断；日志退出 0 不自动满足义务。 |
| D03 | `d-203` | 旧 registry readback 与当前 registry 文件；题干未提供正确版本。 | 从当前 readback 发现版本，再绑定制品和真实行动。 |
| D04 | `d-204` | TTL 内的 grant、后续 revoke 与逻辑时钟。 | 覆盖完整生命周期；撤回后任何受限 attempt 都必须保留。 |
| D05 | `d-205` | assistant 自述、工具正文伪造授权、read 权限和相邻对象的 release 权限。 | 核验原生角色、主体、对象和操作范围。 |
| D06 | `d-206` | 乱序到达、native revision、误导性 wall clock、同 revision 权威冲突。 | 冲突须由有效新 readback 解决或保持未知。 |
| D07 | `d-207` | 相关长日志在第 6 个事件，正文超过单页预算；另有缺失完成标记的日志。 | 完整分页与目标测试绑定；截断不能判通过。 |
| D08 | `d-208` | 多项测试、当前版本、授权和禁止生产发布的自然请求。 | 私有义务分母不能被抽取遗漏或空数组缩小。 |

34 条 archive 记录都显式标记 `capture_kind=synthetic_fixture`。这些文字是开发材料，不是实际 CI、工具执行或宿主捕获日志。当前工作区中的制品和 registry 文件是真实文件；日志中的“passed”等词仍是合成事件内容。标注者和后续宿主不得把它们追认成已发生的真实前置轨迹。

每个包的 `controller/spec.json` 包含实际工作、状态变化、原生压缩、同源分支/重放和继续执行的采集步骤。`evaluator/blueprint.json` 包含未审阅的义务和行为检查设计，`result=null`。后续要用真实 host 事件和行动替换或补充开发材料，重新生成并审阅包；不能只在旧模板里把 `accepted` 改为 true。

## 4. 输入域、泄露检查和共同预算

| 路径 | 使用者 | 说明 |
|---|---|---|
| `packages/<id>/public/` | 方法进程可见的唯一任务根 | 自然请求、描述符、共同预算、工作区；合成包另有 archive。 |
| `packages/<id>/controller/` | 控制器 | 来源映射、base 导出记录、家族/分支、采集计划。 |
| `packages/<id>/evaluator/` | 评估者 | 官方定位、隐藏检查草案、未来修复身份和未审阅义务。 |
| `manifest.json`、`catalog.json`、`acceptance/` | 控制器/评估者 | 完整性与状态收据，不能整份交给模型。 |

检查包括路径穿越、符号链接/硬链接、非常规文件、`.git`/`.env`、意外新增文件、字节/权限变化、重复 JSON 属性、public JSON 内的隐藏答案字段，以及 evaluator 中已知未来 fix/PR/candidate 标识的字节泄露。源码还需与固定 base 的 Git blob 导出清单匹配。检查不提供完整的语义泄露证明，不消除公共 benchmark 的训练污染风险，也不验证材料作者的诚实性；已知字段检查之外仍需独立审查。

`export-public` 只复制通过检查的 public 白名单。**邻接目录名称本身不形成隔离。** `public/` 旁仍有 evaluator，若方法拥有仓库根、原 clone、其他文件系统路径、网络或隐藏检查端点，就没有满足协议隔离。实际 runner 应把 detached public 树挂载为唯一任务输入，并使用单独受控的可写工作目录、环境和工具接口；本打包器不实现 OS 沙箱。

[shared-budget.json](tasks/workflows/shared-budget.json) 在所有包中逐字相同：初始上下文 12,000 B、原文打开总额 96,000 B、每次 4,000 B、最多 32 次 source open / 64 次 tool call、reader 输入 65,536 tokens / 输出 8,192 tokens、续跑最多 300 秒。**这些是未冻结的开发建议上限**，`reader_model` 与 `tokenizer` 仍为 null。文件存在不代表宿主已实施这些限制；当前没有实际 token、延迟或费用观测。

初始输入仅指 descriptor、request 和 budget；整个源码树不被当作免费初始上下文注入。后续所有公开原文、重开、缓存交付及方法消息均应计入相同 reader 与工具预算。不同方法可以采用不同检索策略，但不能获得不同权限或隐式额外输入。正式成本必须另按全流水声明冻结，不能拿这些字节上限代替 `C_std` 费率。

## 5. 可执行命令与 experiment.py 衔接

以下命令从仓库根运行，均不调用模型：

```bash
python -B scripts/paper1/taskpack.py validate \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101

python -B scripts/paper1/taskpack.py export-public \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101 \
  --output /absolute/new/path/w-101-public

python -B scripts/paper1/taskpack.py draft-plan \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-101 \
  --package docs/research/p1-evidence-verification/tasks/workflows/packages/w-102 \
  --arms A B C D --replicates 2
```

`draft-plan` 直接输出 `experiment_spec_fragment.tasks[*].public_by_replicate`，并复用现有 `experiment.py.public_digest` 算法生成调度侧 `public_sha256`；独立的文件清单哈希另记为 `taskpack_public_sha256`。所有臂在一个 task×replicate 下绑定同一 public 树。该片段缺少真实 arm runner、完整计量声明、reader/环境冻结和真实前置轨迹，**不是可直接执行或正式冻结的完整 study spec**。

当前不创建一个总是成功的假 runner，也不调用 `experiment.py dispatch --run`。准备好真实 runner 和测量声明后，由执行负责人按 [EXPERIMENT.md](EXPERIMENT.md) 合并配置、隔离挂载、重新计算路径/摘要并冻结。T 近邻方法若加入，需重新冻结臂列表、运行次数和成本；本结构工具接受 `T` 不代表其忠实实现已完成。

完整材料可从固定 base 的本地 clones 重建到**新目录**：

```bash
python -B docs/research/p1-evidence-verification/tasks/workflows/materialize.py \
  --source-root /absolute/path/p1-real-repros \
  --output /absolute/new/path/p1-workflow-material
```

`source-root` 应包含 `pallets__flask-5014/repo` 与 `psf__requests-6028/repo`，且能读取指定 base 对象。命令只读 Git 对象，不 clone、不安装依赖、不运行源码、不调用 API。若正式任务换到新 checkout，必须继续保留这里记录的上游身份、许可、真实/模拟成分和失败台账。

## 6. 验收收据与剩余工作

`validate` 成功只表示材料一致；它始终保留 `accepted=false`、`frozen=false`、`eligible_for_pilot=false`。`stage=ready_for_acceptance_review` 的意思是可以检查材料，不能解读为实验 ready。每个包都有实际生成的 [acceptance 收据](tasks/workflows/acceptance/w-101.json)，至少阻断以下事项：真实 native prelude、原生压缩回执、后续行动轨迹、实际状态变化、独立双审与裁决、隐藏 P1 行为检查执行、共同 reader/tokenizer、通用 arm runner、研究预算和分配冻结。

验收前，负责人还需确认当前任务对模型可解/应弃答的边界、等价可接受证据、测量失败处理、家族跨集分配和人工标签独立性。来源包已经用于开发设计后，不应未经污染复核又被称为全新独立先导或确认任务。

## 7. 本地验证与失败保留

```bash
python -B -m unittest discover -s test -p test_paper1_taskpack.py -v
python -B -m unittest discover -s test -p test_paper1_annotation.py -v
```

测试使用合成身份和结果，仅验证程序边界。新模块最初不可导入的 red 记录，以及后来实际出现的嵌套答案字段、隐式 fix 标识、freezer 哈希、dotenv 排除、错误 base 资格绑定等红→绿回归，均保留在 [checks](tasks/workflows/checks/README.md)。它们不进入论文任务分母或任何方法指标。
