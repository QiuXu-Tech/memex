# P1 真实工作流来源候选采集

**状态：16 个真实来源候选，8 个项目；尚无在本目录验收或冻结的 P1 工作流。** 采集时间为 2026-11-28 UTC。全部候选来自官方 SWE-bench Verified 的真实 GitHub issue/PR；本目录不报告智能体执行、双人标注、H1/H2 或论文结果。相邻 [reproduction/](../reproduction/README.md) 已完成其中 2 项 base→fix 真实程序复现，其程序测试也不能充当方法臂结果。

## 1. 已取得什么

- 官方数据集：[`SWE-bench/SWE-bench_Verified`](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3)，固定 revision `78f471bf655a3137b2e8a75af1501690ec009ec3`。下载并解析了原始 500 行 Parquet，不使用搜索摘要重建条目。
- 原始 Parquet 为 6,304,616 字节，SHA-256 `030cfd7f2a704c4c0226e7f104c725a3b41230b1d3517f9c915ad7ea5be3fa25`。原始行的标量元数据、完整行摘要和被省略字段的摘要见 [evaluator/dataset-row-metadata.jsonl](evaluator/dataset-row-metadata.jsonl)。整份含 gold 的数据集不在这里再分发。
- 16 个 issue、16 个已合并 PR、16 个固定 base/fix 提交、所有 PR 变更文件均经 GitHub 原始 API 核对；元数据投影见 [evaluator/github-metadata.jsonl](evaluator/github-metadata.jsonl)。完整 API payload 的 canonical JSON 哈希保留，正文、账户资料及补丁正文省略。
- 16 个官方 OCI 镜像标签都已从公开 registry 解析到不可变 digest，原始 index JSON 保存在 `raw/oci-*.json`。这只证明 manifest 可读取；此次采集没有下载镜像 layer、启动容器或认证镜像内容与源码相符。
- 每个候选 base 对应的许可文件已读取并按原字节保存。来源、摘要、时间和已修正的 404 定位保存在 [license-evidence.json](license-evidence.json) 与 [sources.json](sources.json)。Sphinx、SymPy 等许可文件还列出子组件许可，不能只保留顶层简称。

[官方数据集说明](https://www.swebench.com/SWE-bench/guides/datasets/)与[Verified 说明](https://www.swebench.com/verified.html)提供来源背景。官方 Verified 的人工审阅不能替代 P1 的状态、义务与隐藏行为双人标注。这里没有把 Multilingual 的相似任务补进来凑独立数量。

## 2. 可见性与发布边界

**整个 `acquisition/` 是 controller/evaluator 材料，不是 agent-public 输入。** 候选 manifest 中的修复提交、变更路径、评估命令、标签计数以及所有 gold 摘要均不得挂载给被测智能体。公开可读不表示实验中可提供。

未保留 `patch`、`test_patch`、`eval_script`、`FAIL_TO_PASS`、`PASS_TO_PASS` 的值，只保留对应官方定位、字段摘要、文件路径及数量。原 issue/problem statement、hints 和 PR body 的全文也不再分发。后续 public 输入应从已审核的自然请求和当时可见源码白名单重新构造；不能把此 manifest 删几个字段后直接交给模型。当前 `public_input_sha256` 与 `p1_gold_sha256` 均为 null，因为这两种 P1 包尚未建立。

固定 HF dataset card 的 `cardData` 未声明 license，sibling 列表没有 LICENSE。SWE-bench 工具仓库在固定 commit 的 MIT 许可已保存，但不能据此把上游 issue 文本、所有代码和第三方依赖统称 MIT。本次公开材料限定为来源定位、事实元数据、摘要与原许可通知；源代码、补丁或 issue 正文的进一步再分发需按对应材料验收。Pylint 保存的是 GPL v2 文本，现有证据不充分区分 `only` 与 `or-later`，故 SPDX 字段保留 `NOASSERTION`，不擅自改成宽松许可。

## 3. 候选清单

这是运行前按来源可行性作的便利抽样，偏向小范围生产代码/测试改动和不同模块。未用任何方法臂输出或模型解题率选样。原始修复难度和补丁长度只能辅助排期，不能作为 P1 成功的证据。Flask 在该固定 Verified 数据集中只有 1 个条目，因此 pytest 取 3 个不同模块的 issue，其余项目各取 2 个。

| 候选 ID | 真实 issue / PR | 主题 | 安装版本标签 | base / fix 提交 |
|---|---|---|---|---|
| `psf__requests-5414` | [#5367](https://github.com/psf/requests/issues/5367) / [PR #5414](https://github.com/psf/requests/pull/5414) | URL host validation | `2.26` | [39d0fdd909](https://github.com/psf/requests/commit/39d0fdd9096f7dceccbc8f82e1eda7dd64717a8e) / [d09659997c](https://github.com/psf/requests/commit/d09659997cd1e3eca49a07c59ece5557071c0ab9) |
| `psf__requests-6028` | [#6027](https://github.com/psf/requests/issues/6027) / [PR #6028](https://github.com/psf/requests/pull/6028) | Proxy URL authentication parsing | `2.27` | [0192aac241](https://github.com/psf/requests/commit/0192aac24123735b3eaf9b08df46429bb770c283) / [8fa9724398](https://github.com/psf/requests/commit/8fa9724398c4f44090997ff430a1dd3e935a9057) |
| `pallets__flask-5014` | [#5010](https://github.com/pallets/flask/issues/5010) / [PR #5014](https://github.com/pallets/flask/pull/5014) | Blueprint name validation | `2.3` | [7ee9ceb71e](https://github.com/pallets/flask/commit/7ee9ceb71e868944a46e1ff00b506772a53a4f1d) / [7ed89d3f9d](https://github.com/pallets/flask/commit/7ed89d3f9d2207c9a607f5dcdce106c0278e1332) |
| `pytest-dev__pytest-5262` | [#5257](https://github.com/pytest-dev/pytest/issues/5257) / [PR #5262](https://github.com/pytest-dev/pytest/pull/5262) | Captured stdout stream mode | `4.5` | [58e6a09db4](https://github.com/pytest-dev/pytest/commit/58e6a09db49f34886ff13f3b7520dd0bcd7063cd) / [c8f7e50c47](https://github.com/pytest-dev/pytest/commit/c8f7e50c47cc771142f2681aebf7dd9f86c83853) |
| `pytest-dev__pytest-7982` | [#7981](https://github.com/pytest-dev/pytest/issues/7981) / [PR #7982](https://github.com/pytest-dev/pytest/pull/7982) | Symlinked test collection | `6.2` | [a7e38c5c61](https://github.com/pytest-dev/pytest/commit/a7e38c5c61928033a2dc1915cbee8caa8544a4d0) / [a14a229d1b](https://github.com/pytest-dev/pytest/commit/a14a229d1bb9a7fe75799caa974b2cfb8f02f8b3) |
| `pytest-dev__pytest-7432` | [#7392](https://github.com/pytest-dev/pytest/issues/7392) / [PR #7432](https://github.com/pytest-dev/pytest/pull/7432) | Skip and xfail reporting | `5.4` | [e6e300e729](https://github.com/pytest-dev/pytest/commit/e6e300e729dd33956e5448d8be9a0b1540b4e53a) / [c3e2b11a62](https://github.com/pytest-dev/pytest/commit/c3e2b11a62234c283b4ed4a7bfe5edf7eb6f3d4d) |
| `pylint-dev__pylint-4970` | [#4901](https://github.com/pylint-dev/pylint/issues/4901) / [PR #4970](https://github.com/pylint-dev/pylint/pull/4970) | Similarity-check configuration | `2.10` | [40cc2ffd78](https://github.com/pylint-dev/pylint/commit/40cc2ffd7887959157aaf469e09585ec2be7f528) / [cf33d82635](https://github.com/pylint-dev/pylint/commit/cf33d82635569da924d82538f806a5242481f06f) |
| `pylint-dev__pylint-7080` | [#6964](https://github.com/pylint-dev/pylint/issues/6964) / [PR #7080](https://github.com/pylint-dev/pylint/pull/7080) | Recursive ignore-path configuration | `2.15` | [3c5eca2ded](https://github.com/pylint-dev/pylint/commit/3c5eca2ded3dd2b59ebaf23eb289453b5d2930f0) / [c74493bdb9](https://github.com/pylint-dev/pylint/commit/c74493bdb969c40b0b9bc503b239c572ee31641b) |
| `sphinx-doc__sphinx-9367` | [#9364](https://github.com/sphinx-doc/sphinx/issues/9364) / [PR #9367](https://github.com/sphinx-doc/sphinx/pull/9367) | Documentation AST rendering | `4.1` | [6918e69600](https://github.com/sphinx-doc/sphinx/commit/6918e69600810a4664e53653d6ff0290c3c4a788) / [bc616d3b1a](https://github.com/sphinx-doc/sphinx/commit/bc616d3b1a2c0c41ef6fb4e27181cf2b177f02fb) |
| `sphinx-doc__sphinx-8721` | [#8720](https://github.com/sphinx-doc/sphinx/issues/8720) / [PR #8721](https://github.com/sphinx-doc/sphinx/pull/8721) | Incremental HTML and EPUB builds | `3.5` | [82ef497a8c](https://github.com/sphinx-doc/sphinx/commit/82ef497a8c88f0f6e50d84520e7276bfbf65025d) / [86c75cea13](https://github.com/sphinx-doc/sphinx/commit/86c75cea13d87f1cbc7e9c30916bef0cf972eb5c) |
| `sympy__sympy-14711` | [#14710](https://github.com/sympy/sympy/issues/14710) / [PR #14711](https://github.com/sympy/sympy/pull/14711) | Vector arithmetic regression | `1.1` | [c6753448b5](https://github.com/sympy/sympy/commit/c6753448b5c34f95e250105d76709fe4d349ca1f) / [fb0d290816](https://github.com/sympy/sympy/commit/fb0d290816dcaefc1bc874dd7380e4ceba8af1d4) |
| `sympy__sympy-19637` | [#19608](https://github.com/sympy/sympy/issues/19608) / [PR #19637](https://github.com/sympy/sympy/pull/19637) | Symbolic parser regression | `1.7` | [63f8f465d4](https://github.com/sympy/sympy/commit/63f8f465d48559fecb4e4bf3c48b75bf15a3e0ef) / [ff1bc63fe9](https://github.com/sympy/sympy/commit/ff1bc63fe9c5b75fa0bd99e0f9342df80c7eca86) |
| `pydata__xarray-4629` | [#4627](https://github.com/pydata/xarray/issues/4627) / [PR #4629](https://github.com/pydata/xarray/pull/4629) | Merged metadata copy semantics | `0.12` | [a41edc7bf5](https://github.com/pydata/xarray/commit/a41edc7bf5302f2ea327943c0c48c532b12009bc) / [9396605d83](https://github.com/pydata/xarray/commit/9396605d8358a621c89478dbbd286b1b4cd72e64) |
| `pydata__xarray-6461` | [#6444](https://github.com/pydata/xarray/issues/6444) / [PR #6461](https://github.com/pydata/xarray/pull/6461) | Scalar where metadata handling | `2022.03` | [851dadeb03](https://github.com/pydata/xarray/commit/851dadeb0338403e5021c3fbe80cbc9127ee672d) / [0cd5285c56](https://github.com/pydata/xarray/commit/0cd5285c56c5375da9f4d27836ec41eea4d069f3) |
| `mwaskom__seaborn-3069` | [#2967](https://github.com/mwaskom/seaborn/issues/2967) / [PR #3069](https://github.com/mwaskom/seaborn/pull/3069) | Nominal plot scale state | `0.12` | [54cab15bda](https://github.com/mwaskom/seaborn/commit/54cab15bdacfaa05a88fbc5502a5b322d99f148e) / [a767d666d4](https://github.com/mwaskom/seaborn/commit/a767d666d45a6f105177e4720669b85c92ee2432) |
| `mwaskom__seaborn-3187` | [#3174](https://github.com/mwaskom/seaborn/issues/3174) / [PR #3187](https://github.com/mwaskom/seaborn/pull/3187) | Legend formatting across numeric ranges | `0.12` | [22cdfb0c93](https://github.com/mwaskom/seaborn/commit/22cdfb0c93f8ec78492d87edb810f10cb7f57a31) / [9bd166565b](https://github.com/mwaskom/seaborn/commit/9bd166565beea99ab2e43a0576c59efab196940b) |

完整字段见 [candidate-manifest.json](candidate-manifest.json)。`dataset_installation_version` 是官方环境选择标签，不是 P1 当前制品版本真值。16 个候选使用不同 upstream issue/PR，不通过重命名或改变量扩充数量；项目依赖仍按 8 个项目聚类。是否存在跨数据集/开发集污染还需人工核对，不能直接声称 16 个统计独立样本。

### 已发现的官方标签质量问题

`pytest-dev__pytest-5262` 的固定官方 `PASS_TO_PASS` 实际含有 `[100%]` 进度显示标签；[固定官方 parser 源码](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/log_parsers/python.py)也注明这一遗留问题。该候选已在 manifest 标记 `official_p2p_progress_artifact`，必须在进入先导前重建真实测试身份并人工审查，不能将该列表直接当 P1 gold。

Requests 的官方 parser 还会按空白截断参数化测试 ID，并将绝对路径参数压到 basename。原始 nodeid 与官方标签可能不逐字一致，多个实跑测试可能对应同一个规范化标签。后续复现保留 JUnit 的实际测试数与原始日志，不用官方标签条数充当执行次数或研究 N。

## 4. 优先执行的两项

1. **`pallets__flask-5014`：Blueprint 非空名称校验。** [issue #5010](https://github.com/pallets/flask/issues/5010)、[PR #5014](https://github.com/pallets/flask/pull/5014)。生产改动只涉及 `src/flask/blueprints.py`，官方测试 patch 涉及 `tests/test_blueprints.py`，PR 另含 changelog。base 为 `7ee9ceb71e868944a46e1ff00b506772a53a4f1d`，fix 为 `7ed89d3f9d2207c9a607f5dcdce106c0278e1332`；base 正好是 fix 第一父提交。官方预期标签是 1 个 F2P、59 个 P2P；相邻 reproduction 已独立核对，详细实跑结果以其日志为准。无需启动真实网站或外部服务。
2. **`psf__requests-6028`：代理 URL 的认证部分解析。** [issue #6027](https://github.com/psf/requests/issues/6027)、[PR #6028](https://github.com/psf/requests/pull/6028)。生产文件 `requests/utils.py`，测试文件 `tests/test_utils.py`。base 为 `0192aac24123735b3eaf9b08df46429bb770c283`，fix 为 `8fa9724398c4f44090997ff430a1dd3e935a9057`；两者也是相邻第一父关系。官方预期 2 个 F2P、185 个 P2P。目标是本地字符串解析，无需真实代理、认证凭据或外部请求。

这两项优先是环境与范围判断，不是经验速度排行。Requests #5414 虽也很小，但 dataset base 与最终 merge 第一父不同，因此不作为首批最简单的复现。

**重要重建约束：16 项中仅 5 项的 dataset base 等于 upstream fix 第一父。** `fix_commit` 是真实上游合并/压缩提交，用于来源追踪；SWE-bench 的生产 gold 是抽取后的 PR patch。对其余 11 项，直接把整个 base→merge diff 或完整 merge checkout 当作 benchmark 修复会混入中间改动。应使用固定 dataset `patch`/`test_patch` 并检查 `git apply --check`，另核对 PR 文件列表；保留上游提交与 benchmark patch 两种摘要。

## 5. 重建入口（本目录没有执行这些测试）

官方 [quickstart](https://www.swebench.com/SWE-bench/guides/quickstart/) 提供 `--predictions_path gold` 环境校验。这里核对的 harness commit 是 [`02e7a74ffd0b707aab73d203fe87bdc7c76afc8e`](https://github.com/SWE-bench/SWE-bench/tree/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e)；其 `swebench/harness/utils.py` 支持本地 JSON/JSONL dataset，`run_evaluation.py` 消费任务 image。每次运行前先固定 Python/依赖和容器可用性，不能直接依赖将来的 main 或 latest。

在隔离 evaluator 环境中，按固定 revision 取所需条目并保留原字段摘要；把 `image` 替换为 candidate manifest 已核对的 digest 引用，写入 **不挂载给 agent** 的 `/absolute/evaluator/selected.json`。随后可按官方入口验证 gold：

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name /absolute/evaluator/selected.json \
  --predictions_path gold \
  --instance_ids pallets__flask-5014 psf__requests-6028 \
  --max_workers 1 \
  --run_id p1-source-gold-validation
```

这只是 evaluator 环境测试，不调用语言模型。必须另在 base + 同一 test patch 上复现失败，避免只记录修复后的通过。官方 `eval_script` 内含 gold 测试 patch，不能交给 agent。无容器宿主可以另建固定 base 的独立 clone/venv，保留安装失败、依赖锁定、base/fix 日志及隔离限制，不能把这一环境自动说成官方容器等价。

## 6. 从候选到 P1 可用任务仍缺的验收

| 验收项 | 当前状态与所需动作 |
|---|---|
| 源与许可证 | URL/提交/许可原文/摘要已获得；issue 全文发布权限、第三方组件和最终发布范围需独立审核。 |
| 可运行性 | 镜像 manifest 已解析；其中 2 项已在相邻 reproduction 完成本地 base→fix，未启动官方容器。其余 14 项未运行，失败不得删除。 |
| 工作流真实性 | 已取得真实修复来源；还没有真实 prelude、相关状态变更、压缩事件及压缩后的继续行动。 |
| 状态与授权 | test/version 相关性是设计判断。所有未来的 grant/revoke/不可逆动作必须显式标模拟，并用本地 simulator 留 attempt 日志。 |
| Agent/evaluator 分离 | 当前只有 controller/evaluator 元数据；还需公私输入白名单、物理不可访问挂载与污染检查。 |
| 隐藏行为与真值 | 还需最终制品摘要绑定、后于最后写入的真实重测、覆盖完整状态生命周期、可回答/弃答分布及等价证据规则。 |
| 双人标注 | 标注者、独立标注、分歧裁决均为空；SWE-bench 原标注不能替代这一步。 |
| 独立性与划分 | 需登记旧开发题、当前开发使用、正式/外部集和共同源事件；使用某候选调试方法后，应整家族移到开发集并补采先导。 |
| 冻结运行设计 | A/B/C/D 与 TierMem 候选 T 的忠实性、资源、预算、失败账本、费率与项目聚类计划尚须按 P1 协议冻结。 |
| 科学外推 | 这是已有公开基准的便利候选样本，模型预训练污染未知；不能声称新近未见真实任务或代表全部仓库工作流。 |

若首批两项仅用于独立 evaluator 的环境资格检查且结果不用于调参，可保留候选资格；若拿它们调抽取/触发/预算，则按开发使用登记并补采，不能继续称完全独立先导。当前也没有因为找到 16 个来源就把协议里的 P01–P16 分配、冻结或报告为完成。

## 7. 文件和审计约定

- `candidate-manifest.json`：候选来源、固定提交、全 PR 与 benchmark 变更路径、重建入口、许可、独立性、P1 设计相关性和空验收字段。
- `sources.json`：原始来源 URL、检索时间、文件/响应摘要、留存方式，含失败定位。
- `raw/dataset-api.json`、`raw/oci-*.json`：原始公开 metadata 响应。
- `evaluator/*.jsonl`：经声明白名单投影的原始任务/API metadata；源行和被省略字段的摘要可用固定上游重新核对。
- `licenses/*.txt`、`license-evidence.json`：固定 base 许可原字节及映射；不把全部来源改许可。
- `validation-receipt.json`：本次静态一致性检查；它不是程序复现或研究结果。

字节哈希使用 SHA-256；canonical JSON 哈希采用 `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')`。字段为字符串时按 UTF-8 原值计算，不含 JSON 引号。所有候选 `frozen=false`、`eligible_for_pilot=false`；未知验收写 null，不填造假的成功或零成本。
