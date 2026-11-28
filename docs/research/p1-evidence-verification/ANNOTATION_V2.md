# P1 development-assurance v2

更新：2026-11-28。**已实际完成 11 个原任务包的程序审阅、37 条 AI-assisted 义务草案，以及两份有限行为 oracle 的隔离参考源码资格验证（各 5 个 pytest 用例）；真人审阅 0，研究工作流验收 0，方法复合结果未测量。** Requests 原六项草案的一项歧义失败单独保留。用户要求在可靠条件下尽量由 AI 代劳，因此取消了 development 阶段普遍等待“双真人加第三人裁决”的人为流程依赖。真实运行的次数、现金和服务准入仍由原 controller 管理；本方法不产生运行许可。

成果入口：[实际程序报告](artifacts/remaining-completion-01/assisted-review-v2/programmatic/report.md)、[逐包检查](artifacts/remaining-completion-01/assisted-review-v2/programmatic/reviews.json)、[37 条义务草案](artifacts/remaining-completion-01/assisted-review-v2/drafts.json)、[草案 schema](schemas/assisted-review.schema.json)、[可执行 oracle 清单](artifacts/remaining-completion-01/assisted-review-v2/oracle-plan.json)、[版本记录](artifacts/remaining-completion-01/assisted-review-v2/method.json)。

## 1. 修订的范围与来源

原 22 份 review packet 来自 **11 个物理包 × 2 份模板**，其中九包属于八个合成开发家族，另外两包是 Flask、Requests 的真实来源种子。这不等于 22 位已经参与的真人，也不是期刊规定的人数。原 v1 还要求每包一位不同的裁决者；即使同意也要第三人签署，这同样是先前选择的保守流程。

本轮逐字保留旧 [ANNOTATION](artifacts/remaining-completion-01/assisted-review-v2/history/ANNOTATION.md)、[SCORING](artifacts/remaining-completion-01/assisted-review-v2/history/SCORING.md)、[TASKPACKS](artifacts/remaining-completion-01/assisted-review-v2/history/TASKPACKS.md)，摘要记入 `method.json`。旧 public 树、来源包 manifest、22 张空表、11 张裁决模板、原 accepted/frozen 状态均不改。新产物采用 `p1-assisted-task-review-2` 和 `p1-development-assurance-2`，仅适用于 development 材料预审与诊断。

`annotation.py` 和 `score.py` 的 human-v1 输入仍要求真实来源声明，不能通过改字段将 AI 当真人。本轮新增程序路径不调用这些人工验证入口来制造人工记录，也不冻结正式 labels。未来正式研究可以选择有实证验证的程序标签、明确披露的 AI 辅助标签或人工路线；必须在正式方法结果用于判断之前确定并冻结相应合同。

## 2. 哪些工作可替代，哪些科学条件需要保留

| 原工作 | v2 的处理 | 保留的必要条件 |
|---|---|---|
| 文件、来源、哈希与引用核对 | 程序实际重算 | 原始证据可读，路径安全，版本和摘要一致。 |
| 原测试是否确实产生通过/失败记录 | 从旧 JUnit testcase 重新计数；新运行从 observer 重新推导 | 非空实际收集、完整测试 phases、代码/依赖/nonce 绑定；不能只找文本中的 passed 或 exit 0。 |
| 当前制品、revision、明确授权状态 | 对可形式化的输入直接计算 | 适用主体、对象、动作、时间和来源完整；冲突或缺信息保持未知。 |
| 从自然请求列出完整义务 | AI 先完成草案，逐项绑定公开原文 | 义务分母不来自被评方法的候选集合；说明 AI 来源、接触史和覆盖限制。 |
| 每任务固定两位真人 | development 不普遍要求 | 需要验证标签质量与独立真值依据；不能把同一个 AI 的两次输出称作独立真人。 |
| 所有任务均由第三人裁决 | 对确定性字段用规则合并；真正歧义保留 | 不隐藏冲突或删掉不利材料；非确定性争议需要有理由的审查，未必预先规定固定人数。 |
| 人类作者资格、真实贡献、责任与最终同意 | 仍是实际个人事实 | 自动审阅不能成为作者，不能代填机构、贡献、利益冲突或承诺。 |

独立性主要指真值依据不由被评方法的输出决定，也要诚实交代设计者与评估者的关联。不同 AI 实例不自动构成人类独立双审。本助手已看过原任务设计和来源复现信息，故草案明确是 **nonblind AI-assisted**；没有宣称未接触 evaluator 背景。新方法回答、候选提取结果和方法成绩不是草案生成器的输入。

## 3. 已实际完成的 11 包审阅

`scripts/paper1/taskpack_review.py` 复用原 taskpack 与 annotation 完整性检查，检查目录声明和 public 字节，重新核对 22 份 reviewer material 与两个 packet 的映射，并确认所有旧审阅/裁决字段仍为空。若发现非空记录，会要求单独核算，不能仍写人工 0。

两个真实来源包的导出文件逐个重算 SHA-256 与 Git blob ID；来源资格收据还绑定 candidate、base、原始收据摘要，并从存留的 base/fixed JUnit 重新计算 testcase。Flask 重算为 base 60 项、1 失败、59 通过，fixed 60 项通过。Requests 重算为 base 214 项、2 失败、201 通过、11 跳过，fixed 203 通过、11 跳过。这是**既有程序复现证据的复核**，没有新运行源码，也没有方法臂结果。[逐包审阅](artifacts/remaining-completion-01/assisted-review-v2/programmatic/reviews.json)

| 材料 | 程序可核对的事实 | 没有据此声称的事实 |
|---|---|---|
| D01 changed / unchanged | 当前 artifact 与旧记录摘要分别不同 / 相同 | 旧合成测试确曾运行，或复用在所有环境条件下有效。 |
| D02 | cancelled、not-run、零断言、无关 exit 0 仍是不同记录 | 没有把这些记录提升为目标测试通过。 |
| D03 / D08 | 当前 registry 文件的 revision 与 active_release 可读 | 方法已实际读取并采用当前版本。 |
| D04 | 显式 fixture grammar 下后续 revoke 覆盖仍在原 TTL 内的 grant | 真实世界的用户授权或真实 release 行动。 |
| D05 | assistant/tool 文字和错对象、错动作 grant 不匹配目标授权 | 自动认证一个现实中的 owner 身份。 |
| D06 | 同一最高 revision 存在不同值；wall clock 没用于覆盖冲突 | 已获得新的权威 readback。 |
| D07 | 完整 transport 文本超过 4,000 B，storage 缺完成信息 | 方法已翻完所有页，或合成断言是实际执行。 |
| D08 | 自然请求包含多项测试、版本与动作限制 | 抽取器输出少几个候选后可缩小义务分母。 |

所有 34 条 archive 仍为 `synthetic_fixture`；当前真实文件中的 registry/artifact 字节与描述它们的合成事件严格区分。程序仅执行已声明的 fixture grammar，不将不认识的 owner 语句解析成授权，也不把文字里的断言数当真实测试结果。

重算命令（输出目录必须是新目录）：

```bash
python -B scripts/paper1/taskpack_review.py \
  --catalog docs/research/p1-evidence-verification/tasks/workflows/catalog.json \
  --drafts docs/research/p1-evidence-verification/artifacts/remaining-completion-01/assisted-review-v2/drafts.json \
  --output /absolute/new-material-review
```

## 4. 可执行 oracle 与未测量边界

### 4.1 封存轨迹中的确定性组件

`scripts/paper1/development_oracle.py` 读取原 `experiment.py` 的冻结 development plan 和首次尝试账本，重算完整 output seal，再核验单一 fork 的 public-workspace hash-chain。它不从 checkpoint 复制的前置日志冒充本臂后续动作，也不接受未准入工具的成功结果。

对实际测试收据，它重新读取保存的 observer 配置、nonce、执行结果、原始 pytest observation、执行前后快照、依赖清单和 observer 字节，并调用现有 `python_workflow.summarize`。之后检查最终代码、已核验测试和 local review 的实际引用关系。测试后的编辑使旧制品证据失效；缺失、截断、零测试或不完整记录不会产出通过。该诊断保留所有已观察到的当前制品测试结果，若同一当前制品有失败，`current_public_tests_passed` 为 false；这是显式的开发组件定义，不是已注册的正式复合终点。

工具只能关闭可类型化的组件：`current_public_tests_passed`、`local_review_bound_to_current_tests`、`workspace_change_observed`。它不会凭一个 write 断言该变化与任务相关，也不会凭日志封存证明所有外部行动均被捕获。`requested_hidden_behavior_passed`、`evidence_semantic_correctness` 和 `decision_success` 一律保持 null，直到另有完整、已验证的测量合同。

```bash
python -B scripts/paper1/development_oracle.py \
  --plan /absolute/frozen-development-plan \
  --state /absolute/original-experiment-state \
  --output /absolute/new-typed-component-report
```

它不生成 `quality.jsonl`，拒绝正式研究 phase；未执行单元明确为 NOT_MEASURED。当前真实开发 driver 保留的直接 runtime 结果不能被伪造为 experiment seal。没有相应封存输入时，保留原收据与缺口即可，不为了运行这个工具而创建虚构运行。

### 4.2 两来源包的请求行为测试草案

两份 pytest 草案已进一步完成独立参考源码资格验证，但**没有在本轮方法最终制品上执行**。Flask 原版和 Requests 明确 URL 范围的 v2 各有 5 个实际收集的 pytest 用例，合计 10 个行为检查用例；这不是十个人工 gold 标签、十个独立任务或恰好十条 assert 语句。对方法评分仍须将 target import 绑定到封存后的方法制品，不得在执行前透露 oracle，也不能使用当前安装包的通过结果代替方法制品结果。

| 来源 | 可执行文件 | 检查内容与边界 |
|---|---|---|
| Flask | [test_flask_request_contract.py](artifacts/remaining-completion-01/assisted-review-v2/oracle-drafts/test_flask_request_contract.py) | 空 name 抛 ValueError；三个普通 name 的构造、注册与本地 test-client 路由；既有 dotted-name 拒绝。检查公开行为，不要求补丁逐字一致。 |
| Requests 原版 | [test_requests_request_contract.py](artifacts/remaining-completion-01/assisted-review-v2/oracle-drafts/test_requests_request_contract.py) | 六项草案在官方 fixed 上 5 通过、1 失败；无 scheme 的普通凭据字符串仍有格式歧义，因此原版不完全合格，原始失败保留。 |
| Requests v2 | [test_requests_request_contract_v2.py](artifacts/remaining-completion-01/oracle-qualification-01/test_requests_request_contract_v2.py) | 明确 HTTP/HTTPS URL 的虚构认证与 Proxy-Authorization 保留、编码字符、无认证路径；5 项在已知 fixed 上通过。没有网络请求，不声称重现真实 HTTP 407 或 Python 3.8.12 等价。 |

这些测试来自自然请求和公开接口分析，未复制官方 patch/test_patch，也不根据新方法答案写断言。初始材料报告的 `execution_status=not_executed` 保留为当时的历史快照；后续实际结果在独立的 [oracle-qualification-01](artifacts/remaining-completion-01/oracle-qualification-01/README.md) 版本中追加，不改写旧记录。

在已存在的两套 Python 3.10.16 固定依赖与实际 `SandboxRunner` 中，Flask 原版得到 base 4 通过/1 失败、fixed 5 通过、故意一律拒绝名称的实现 2 通过/3 失败；Requests v2 得到 base 2 通过/3 失败、fixed 5 通过、故意一律伪造凭据的实现 2 通过/3 失败。另有空测试、缺源码、私有复制依赖中的同名包三类控制：分别因零收集、缺失模块和错误 import 来源被拒。原 venv、public、taskplan、settings 均未修改。

本次共 15 个 observer 进程与 5 个真实隔离 probe；全部真实输入快照、Git blob、oracle hash、stream 与 observer 又经独立后验复算一致。第一轮逐 invocation 缺少 source/oracle pin 断言的问题明确记录为后验补核，v2 增加执行前后绑定。282 份脱敏记录和完整哈希在 [证据包](artifacts/remaining-completion-01/oracle-qualification-01/evidence.zip)，[零源码执行复核](artifacts/remaining-completion-01/oracle-qualification-01/verification.json) 重算 15 条汇总和 5 份 probe。Requests v2 在看过**参考源码**结果后缩小到明确 URL 格式；其原版一项失败、修订理由与未覆盖范围均保留，不能追认为正式预注册或给当前方法自动判成功。

## 5. 本轮 native 观察能否使两来源任务验收

**能继续发展为可验收的 development 工作流；不能预先保证四次 native 尝试使它们成为先导样本。** 来源、许可/固定 base、原始需求和开发环境已有可核查材料，程序预审已经完成，等待 22 张真人表不是继续采集的理由。

需要从本轮真实、任务绑定的收据确认：实际前置工作与相关状态变化；原生压缩与同父续跑；最终代码的目标行为和回归；证据引用与实际动作一致；失败、未知与全部尝试被保留。若仅完成一次修复和测试后重复输出相同 review，而没有后续决策确需早先证据的情境，仍可报告开发观察，但不满足当前 P1 工作流纳入条件。旧 source seed 已参与设计，不能未经污染审查称作新的确认样本。

确定性核对由程序完成，后续语义预审也可继续由 AI 明确署为 AI-assisted；涉及完整覆盖、真实作者责任或不可形式化的争议时，保留实际所需的复核范围，不事先要求每个字段都必须找两位真人。研究报告必须说明采用的方法、非独立性与验证限制，不能把方便的自动标签当作已证明的 ground truth。

## 6. 官方政策与作者责任

2026-11-28 核对的 TMLR [editorial policies](https://www.jmlr.org/tmlr/editorial-policies.html) 允许 LLM 作为一般辅助工具，要求人类作者对内容负责，并排除 LLM 作者；作者还须有实质知识贡献、参与写作或修改并承担责任。[FAQ](https://jmlr.org/tmlr/faq.html) 仍有人类来源的 ideas/claims/results 期待与首页披露说明。本轮没有宣称该 FAQ 已被撤销，也没有据此认定本项目作者资格已满足。

[Acceptance criteria](https://www.jmlr.org/tmlr/acceptance-criteria.html) 关注准确、有说服力的证据与清楚表述，也允许缩小证据不支持的主张。在这些已查官方页面中，没有发现逐任务两位真人或“22 份真人表”的固定要求。**这是对已查政策适用范围的判断，不是期刊对本方法、自动标签或稿件的预先认可。** 因而可以开展明确披露的程序和 AI 辅助开发工作，同时将最终作者事实与研究有效性如实保留。来源清单与该推论保存在 [policy-sources.json](artifacts/remaining-completion-01/assisted-review-v2/policy-sources.json)。

## 7. 验证与执行事实

```bash
PYTHONPATH=test:scripts/paper1 python -B -m unittest \
  test_paper1_taskpack_review test_paper1_development_oracle -v
```

26 项定向工程测试覆盖：禁止 AI 冒充真人；public/引用/span/目录绑定；不漏任务与义务；JUnit 重算、空测试/重复/实体拒绝；fixture 状态规则及乱序旧 grant 不恢复撤回权限；原空白审阅被填写后的单独核算；无结果 null；未知 observer、先测后改、未准入工具、缺失/篡改 seal、nonce 与代码快照变更。独立 AI 代码审查另发现“一个已核验通过加一个缺 observer”可能漏掉未知测试的组件分母，已用 red/green 回归修复：未知收据保留，相关组件为 null，不以已核验子集宣称通过。这 26 项单元测试用到的身份、观察、run 状态和成功/失败都是显式工程 fixture，本身不产生真实人工、native、provider 或源码执行；另行授权的真实参考源码资格验证如 §4.2 所述。
