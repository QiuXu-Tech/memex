# 请求行为 oracle 的独立参考源码资格验证

**已实际执行并验证两个有限范围的行为 oracle：Flask 原五项草案，和 Requests 明确 URL 格式的五项 v2。** 本目录记录的是已知 base、官方 fixed 和故意错误输入上的程序资格验证。没有读取本轮 native / method 输出，没有把 oracle 提供给模型，没有生成方法评分或验收任务；真人审阅数仍为 0。

Requests 原六项草案在官方 fixed 上有 **1 项真实失败**。原草案、全部日志和该失败完整保留；原六项版本没有被判为全部合格。v2 的范围和修订时点单独记录，不能将 v2 的通过倒填到原版。

## 1. 实测结果

| Oracle 版本 | 固定 base | 官方 fixed | 故意错误实现 | 资格判断 |
|---|---:|---:|---:|---|
| Flask 原版，5 项 | 4 通过、1 失败 | 5 通过 | 2 通过、3 失败 | 可区分空名称 bug、修复和“一律拒绝名称”的错误实现。 |
| Requests 原版，6 项 | 2 通过、4 失败 | 5 通过、1 失败 | 3 通过、3 失败 | **原版不完全合格**；无 scheme 的普通认证字符串仍有未解决的输入格式假设。 |
| Requests v2，5 项 | 2 通过、3 失败 | 5 通过 | 2 通过、3 失败 | 对明确 HTTP/HTTPS URL 的认证保留、编码凭据和无认证路径成立；不是完整代理场景验收。 |

上述非空测试均有完整的 setup/call/teardown 观察、实际 pytest 退出码、执行前后源码快照和 workspace import 绑定。没有测试错误或跳过项。每个表格单元是一组已知参考源码的执行观察；这些重复和变体不是独立研究样本 N。[逐次第一轮结果](evidence/qualification.json)、[Requests v2 结果](evidence/revision-02/qualification.json)、[机器摘要](evidence/reference-summary.json)。

另对两套环境分别执行三个拒绝控制：

| 控制 | 实际观察 | 保留的判断 |
|---|---|---|
| 空 oracle 文件 | pytest 收集 0 项，退出 5 | `capture_incomplete`，不视为通过。 |
| 删除工作副本中的目标源码 | observer 退出 78，`ModuleNotFoundError`，pytest 未启动 | 缺失当前制品，不能给出测试通过。 |
| 缺源码，同时在**私有复制**的依赖目录加入同名包 | observer 退出 78，`project_import_outside_current_workspace`，pytest 未启动 | 拒绝从依赖目录冒充当前源码。原依赖目录没有修改或安装新包。 |

合计 **15 个 observer 子进程、5 个真实 OS sandbox probe**。其中 12 个 observer 属于原版完整控制矩阵，Requests v2 追加 3 个 base/fixed/错误实现观察；v2 使用新的 SandboxRunner 实例，先重新 probe。空集与错误来源控制没有因 v2 改动而重复计数。所有模型、provider、native、method 调用在**本资格验证范围内**均为 0，原账本没有被读取或改写。

## 2. 来源与环境绑定

| 来源 | 固定 base | 已知官方 fixed |
|---|---|---|
| Flask | `7ee9ceb71e868944a46e1ff00b506772a53a4f1d` | `7ed89d3f9d2207c9a607f5dcdce106c0278e1332` |
| Requests | `0192aac24123735b3eaf9b08df46429bb770c283` | `8fa9724398c4f44090997ff430a1dd3e935a9057` |

所有标识均由原任务包读取，而不是重新猜测来源。base 来自已校验的 canonical public 源码副本；fixed 通过指定的 Command Line Tools Git 获取上述固定提交，并用原 `taskpack.export_source` 的白名单、排除项和许可证要求导出。每个文件重算 SHA-256 与 Git blob，相关 fixed 文件还与旧复现收据逐字节摘要一致。[来源准备收据](evidence/source-preparation.json)

实际执行使用既有两套 **Python 3.10.16 与固定依赖**。原 venv、public、task plan 和 runtime settings 均未修改。代码通过现有 `public_workspace.SandboxRunner` 的 `sandbox-exec` 后端执行；每个实例先实际证明允许工作区读写、拒绝私有目录读写并拒绝真实 loopback 连接，随后才使用同一实例运行可信 `python_workflow_child.py`。没有不受限执行后备路径。

可信 observer 使用 `-I -S -B`，显式绑定项目根、依赖目录、Python 版本及依赖版本，禁止 site / `.pth` 和 pytest 插件自动加载。主要项目模块在运行前后均来自实际工作副本，且模块摘要匹配执行快照。Requests 的有限 dependency alias 依原 observer 规则单独绑定；错误来源的同名项目包明确被拒。

## 3. Requests 修订的理由和限制

原草案包含 `reviewer:fixture-password@proxy.example.invalid:3128`。官方 fixed 对这项仍返回空认证元组，导致真实断言失败；[原 stdout](evidence/runs/w-102/fixed/execution/capture/stdout.raw) 和 [JUnit](evidence/runs/w-102/fixed/execution/sandbox-output/pytest.junit.xml) 保留该结果。

读取被绑定的 urllib3 parser 源码后可见，它先识别 scheme，再决定是否补 `//`；普通 `reviewer:` 前缀会触发这类格式歧义。公开任务没有明确要求支持这一表示法，已知官方修复也不是这个扩展的合格参考。v2 因而明确使用 `http://` 或 `https://` 的认证 URL；编码认证例也改为显式 scheme。无认证 URL 的有 / 无 scheme 控制继续保留。

这是**看过参考实现结果后的开发修订**，不是事先注册的正式终点，也不是因为某个被评方法失败而删测试。原草案全部留存，歧义输入列入未覆盖范围。v2 仍不能证明 Python 3.8.12 与本环境等价，不能声称重现了真实 HTTP 407 交互，也不衡量完整的证据采用、授权或决策成功。[v2 文件](test_requests_request_contract_v2.py)、[修订计划](evidence/revision-02/revision-plan.json)

## 4. 完整性审计与保留的失败

第一次源码准备因 Mac 未部署旧的历史复现 JSON 而停止，目标代码执行为 0；随后只把仓库中已有收据复制到本次私有目录，并校验原哈希。第一次失败收据仍在 [source-preparation-failure.json](evidence/source-preparation-failure.json)，没有覆盖历史记录。

独立代码审查发现第一轮控制器没有在每次 invocation 前再次比较 source-preparation inventory 和最初 oracle SHA。运行结束后，新增只读审计用早先 pinned Git blob / 文件清单重建每次“参考源码 + 明示 mutation + oracle”的精确文件集合，再比对捕获的 before/after、原始 stream 摘要、observer nonce、导入来源和实际测试 phases。**15 条执行全部重算一致。** 这是一项后验完整性检查，不追认成先于原运行的冻结。Requests v2 在执行前另外检查来源 inventory 和固定 oracle 字节，并在每次运行前后复查。[审计结果](evidence/posthoc-integrity-audit.json)

导出后又在工作区独立检查了 **282 份记录的发布哈希、15 条 observer 汇总、5 份实际 probe 收据**。这次复算不执行项目源码或 pytest。[验证结果](verification.json)

## 5. 证据与重算入口

完整脱敏证据：[evidence.zip](evidence.zip)，484,495 B，SHA-256：

```text
81af1648cd1bce5251646a3bcebea66507bd7a1a774573e283a4c7f54fb9408a
```

其中包括捕获的工作区文件清单、依赖清单、实际 observer 与 process JSON、原始流的脱敏副本、JUnit、sandbox policy/probe、固定源码导出清单、当时使用的 helper 代码和全部控制脚本。原始私有记录仍保留；[export-manifest.json](evidence/export-manifest.json) 对每个文件同时给出原始和发布 SHA-256。名为 `stdout.raw` 的发布副本可能已替换已知私人路径；它不被声称为逐字节原始流。XML 在替换路径后重新序列化。没有认证信息被读取或导出。

从仓库根进行零源码执行复算：

```bash
python -B docs/research/p1-evidence-verification/artifacts/remaining-completion-01/oracle-qualification-01/verify_export.py \
  --archive docs/research/p1-evidence-verification/artifacts/remaining-completion-01/oracle-qualification-01/evidence.zip \
  --output /absolute/new-oracle-export-verification.json
```

`source_prepare*.py`、`run_qualification.py`、`run_requests_v2.py`、`audit_records.py` 和 `export_records.py` 保留本轮独立验证的实现；完整 bundle 中实际执行版本的原始哈希与脱敏副本另可核对。唯一的发布便携修改是将 `source_prepare.py` 的原私人 canonical 路径改为显式 `P1_ORACLE_CANONICAL_ROOT` 环境变量；这不是新源码执行，也没有修改已保存收据。源码准备依赖本次指定的已知 Git / canonical root 和复制的旧收据；重跑应使用新私有目录，明确指定原 settings，禁止修改原 public 或 venv。真实测试入口要求 `--run`，默认只打印零调用预检。它们不是 `experiment.py` 的 unit runner，也不制造 quota、permit、checkpoint、quality 或人类签署。

后续若要对方法最终制品评估，仍需另行绑定真实封存制品及其 evaluator 输出，保证模型事先无法读到 oracle，并保留完整义务与未覆盖语义。这里的参考程序通过不会自动把 source seed、synthetic archive 或 native checkpoint 升为已验收研究工作流。
