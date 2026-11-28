# 两项真实仓库程序回归复现

**已完成固定 base → 预期失败 → 官方修复 → 通过。** 这是来源与本地环境资格检查，共 2 个仓库实例、4 次 pytest 调用。它没有运行语言模型、原生压缩、检索方法臂或 P1 隐藏行为，也没有产生双人 gold 标注、先导成功率、H1/H2 或 `C_std`。

## 1. 观察到的结果

| 实例 | base + 官方 test patch | 再加官方生产 patch | 退出码 | 官方标签核对 |
|---|---|---|---|---|
| `pallets__flask-5014` | 60 个实跑项：1 failed、59 passed、0 skipped、0 errors | 60 passed、0 failed | 1 → 0 | 1 个 F2P 和 59 个 P2P 均符合预期 |
| `psf__requests-6028` | 214 个实跑项：2 failed、201 passed、11 skipped、0 errors | 203 passed、11 skipped、0 failed | 1 → 0 | 2 个 F2P 和 185 个规范化 P2P 标签均符合预期；标签数不等于实际测试数 |

表中的实跑数从 JUnit 原始报告重算，失败没有从分母移除。Requests 的 11 个 skip 为 1 个 Python 2 `cStringIO` 条件和 10 个 Windows 专属条件，不记为通过。只运行表中相应测试文件，没有声称整个仓库测试全通过。

- Flask 原始 [base stdout](pallets__flask-5014/base.stdout.txt)、[base JUnit](pallets__flask-5014/base.junit.xml)、[fixed stdout](pallets__flask-5014/fixed.stdout.txt)、[fixed JUnit](pallets__flask-5014/fixed.junit.xml)。失败项为 `test_empty_name_not_allowed`：base 没有抛出所需 `ValueError`。
- Requests 原始 [base stdout](psf__requests-6028/base.stdout.txt)、[base JUnit](psf__requests-6028/base.junit.xml)、[fixed stdout](psf__requests-6028/fixed.stdout.txt)、[fixed JUnit](psf__requests-6028/fixed.junit.xml)。两项失败均是 `prepend_scheme_if_needed` 对含认证部分的 URL 的回归，使用源码中的示例字符串，没有真实凭据或代理请求。
- 机器可读汇总见 [summary.json](summary.json)；逐项来源、命令、哈希、依赖、限制和标签核验见 [Flask reproduction.json](pallets__flask-5014/reproduction.json) 与 [Requests reproduction.json](psf__requests-6028/reproduction.json)。

## 2. 固定来源与实际执行顺序

两项官方数据均来自 [SWE-bench Verified 固定 revision](https://huggingface.co/datasets/SWE-bench/SWE-bench_Verified/tree/78f471bf655a3137b2e8a75af1501690ec009ec3)。所用字段是该版本的 `patch` 与 `test_patch` 原 UTF-8 字节，哈希在逐项 `reproduction.json` 中。

| 实例 | 上游来源 | base commit | upstream fix commit |
|---|---|---|---|
| Flask | [issue #5010](https://github.com/pallets/flask/issues/5010)、[PR #5014](https://github.com/pallets/flask/pull/5014) | `7ee9ceb71e868944a46e1ff00b506772a53a4f1d` | `7ed89d3f9d2207c9a607f5dcdce106c0278e1332` |
| Requests | [issue #6027](https://github.com/psf/requests/issues/6027)、[PR #6028](https://github.com/psf/requests/pull/6028) | `0192aac24123735b3eaf9b08df46429bb770c283` | `8fa9724398c4f44090997ff430a1dd3e935a9057` |

每个实例先建独立 clone，detach 到固定 base，建独立 venv，安装明确版本依赖，再 `git apply --check` 并应用官方 test patch。接着运行目标测试文件，确认失败与官方 F2P 一致，然后 `git apply --check` 并应用官方生产 patch，用同一解释器、依赖和测试文件复跑。两个 phase 之间测试文件的 SHA-256 均未改变。

两个 base 恰好分别等于对应 upstream fix 的第一父提交。修复后的生产文件与测试文件，共 4 个文件，均重新计算 Git blob SHA-1 并与固定 fix commit 的官方 API 文件对象 SHA-1 对齐，同时保存实际文件 SHA-256。验证结果全部为 true；没有仅凭 patch 文件名或 pytest 返回码声称应用了真实修复。

Flask 生产文件为 `src/flask/blueprints.py`，测试为 `tests/test_blueprints.py`；Requests 生产文件为 `requests/utils.py`，测试为 `tests/test_utils.py`。原始 PR 的 changelog 不影响此处测试，未用完整 merge checkout 引入其他变化。

## 3. Python 与依赖

使用单独下载的 **CPython 3.10.16**，每项目独立 `venv310`。解释器二进制 SHA-256、`sys.version`、平台信息均在逐项记录内。原宿主的 3.12 venv 仅在准备阶段创建，未用于测试，也未把 Python 3.12 不兼容误算成程序回归。

Flask 的 pytest 7.2.2 与测试依赖版本参照固定源码的 `requirements/tests.txt`；核心运行依赖固定为 Werkzeug 2.2.3、Jinja2 3.1.2、MarkupSafe 2.1.2、itsdangerous 2.1.2、click 8.1.3。Requests 使用其开发依赖范围内的 pytest 6.2.5，并固定 urllib3 1.26.18、charset-normalizer 2.0.12、idna 3.3、certifi 2021.10.8、pytest-mock 2.0.0 等。完整直接安装清单见各自 `requirements-pinned.txt`，实际安装版本见 `dependencies-freeze.txt`。

这是一套明确记录的兼容本地环境，不是官方 Docker 镜像的逐位复制。此次没有拉取镜像 layer；[采集 manifest](../acquisition/candidate-manifest.json)另保留了官方镜像 digest。只有包版本锁定，没有声称完成全部 wheel 字节和操作系统镜像的供应链重建。

## 4. 隔离与保留的失败

测试实际在 bubblewrap 的 **文件系统、user、pid、ipc、uts 命名空间**中运行，只挂载本例源码、只读本例 venv、只读固定 Python runtime、本例日志、只读系统二进制/库以及私有 `/tmp`、`/proc`、`/dev`。其他项目、用户 home、`.env` 和 API 密钥不在挂载与环境白名单中。`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`，仅 Requests 显式启用本例需要的 `pytest_mock`。

完整 `--unshare-all` 曾因宿主禁止配置 `NETLINK_ROUTE` socket 失败。因此最终测试的**网络命名空间共享**，不能描述为网络隔离；没有使用提权、修改权限或绕过拒绝。测试环境没有代理变量，也未挂载宿主 `/etc` resolver。此处选择的测试是本地 API/字符串/文件工具回归，没有发起真实代理认证或外部动作。

全部探测见 [isolation-probe.json](isolation-probe.json)。保留了以下环境失败及修正，不用后续成功覆盖前次记录：

1. 最小环境未带公共网络路由配置时，首次 git clone 因无法解析 `github.com` 失败。`prepare-1.stderr.txt` 与初次命令保留。随后仅加允许的公共代理路由变量，未加载用户 `.env`、私有 Git 配置或用户凭据，clone 成功。
2. 初次极简 bwrap 未挂载动态链接器路径，`/bin/true` 启动失败；补齐只读 `/lib`、`/lib64` 后该问题解决。
3. 完整 network unshare 被宿主拒绝；改用明确可用的部分命名空间隔离，并保留网络共享限制。

安装与源码下载发生在独立 scratch 环境，使用最小环境加上述网络路由。所有安装 stdout/stderr、命令和返回码保存在项目子目录；测试时重新清空环境，不沿用下载环境。

## 5. 精确命令与可复查入口

每条实际命令以 JSON argv 保留，避免 shell 引号或转义造成歧义：

- `prepare-commands.json` 与 `prepare-retry1-commands.json`：首次失败、成功 clone、固定 checkout、初始 venv。
- `environment-commands.json`：CPython 3.10 venv、固定依赖安装、editable 安装、test patch 检查与应用。
- `base-command.json`：完整 bwrap 挂载和环境参数、测试 argv、开始时间、墙钟时间、退出码、phase 文件摘要。
- `apply-fix.json`：生产 patch 检查与应用。
- `fixed-command.json`：同样环境下的修复后测试命令与记录。

bwrap 内部的测试入口分别是：

```bash
python -m pytest -rA tests/test_blueprints.py --junitxml=/absolute/own-log/base.junit.xml
python -m pytest -rA -p pytest_mock tests/test_utils.py --junitxml=/absolute/own-log/base.junit.xml
```

修复后只改 JUnit 输出文件为 `fixed.junit.xml`。实际绝对路径和完整 bwrap 命令应以 JSON 记录为准；新机器重建时替换本例工作目录，保持所列挂载边界。

官方补丁不在研究目录再复制。原文可从固定 HF revision 的同名字段取得，校验记录中的 SHA-256 后使用：

```bash
git checkout --detach <recorded-base-commit>
git apply --check /absolute/evaluator/test_patch.diff
git apply /absolute/evaluator/test_patch.diff
# Run and retain base-command.json equivalent before applying the fix.
git apply --check /absolute/evaluator/patch.diff
git apply /absolute/evaluator/patch.diff
# Run and retain fixed-command.json equivalent with the same tests.
```

本地只给 evaluator 的原始两行记录与补丁保存在 `/workspace/scratch/d5292d3ebcac/p1-real-repros/`，不挂载给方法。此类 clone 有完整未来 Git 历史且已接触 gold 测试，**不得原样作为后续 agent-public 仓库**。正式任务应另从冻结白名单导出源码并屏蔽 solver 的 gold/未来历史可见性。

## 6. 官方标签与真实测试数的差异

首先做了未规范化的 nodeid 严格核对。Flask 完全对齐；Requests 出现 10 个官方 P2P 标签找不到逐字对应的 nodeid，原始 mismatch 完整保留在 `literal_nodeid_coverage_before_official_normalization`，没有删除这些标签或改判质量。

随后核对[固定官方 parser](https://github.com/SWE-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/log_parsers/python.py)：`parse_log_requests` 指向 `parse_log_pytest_options`，会按空白截断 nodeid 并将绝对路径参数改成 basename。本次从该固定源码提取未修改的函数 AST、其 helper 和官方 `TestStatus` enum，对封存日志执行相同解析规则；不是重写一套为通过而放宽的映射，也没有运行完整 harness。源码与 enum 文件的哈希保存在记录里。

按此官方规范，两个实例的 F2P、P2P 均覆盖且状态符合预期。但官方标签可能把多个参数化测试合并，所以继续以 JUnit 的 **60 / 214 个实际执行项**报告程序测试规模，不用 60 / 187 个官方标签代替。P1 的研究单位仍是任务，绝不能把这些测试项、标签、日志行或两次 phase 当成新增任务 N。

## 7. 许可、结论边界与下一步

固定来源代码许可已在[采集许可台账](../acquisition/license-evidence.json)核对：Flask 为 BSD-3-Clause，Requests 为 Apache-2.0。此处发布的是来源、摘要、依赖清单、调用记录与实际测试日志；未把源码、补丁或上游 issue 正文重新标为 Memex 许可。

两项目前适合进入 **P1 工作流构造与独立标注**。接下来仍需在真实工作过程中捕获原始工具证据、至少一次相关状态变化、原生压缩及压缩后行动，并建立 evaluator 的隐藏行为与等价证据规则。若某候选用来调抽取器、触发器或预算，就登记为开发家族并替换独立先导候选。此处没有运行这些方法开发或先导步骤。
