# 验证记录与复现说明

日期：2026-11-08。固定基线：`5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182`。本次实测结果与历史论文/仓库实验明确分开。

## 1. 环境和隔离

macOS / arm64，Node **v25.9.0**，Python **3.14.3**。从 GitHub 固定提交的源码 ZIP 解包到独立临时目录，保留原始归档作为校验源。运行测试时使用独立 HOME、TMPDIR、DSH_HOME/MEMEX_ROOT（按需要设置），不继承提供商凭据；通过 macOS sandbox 拒绝测试进程网络。没有操作用户实际记忆库、客户端配置或工作项目。

本次是 AI 辅助工程审查，未由独立人工审计员背书。源归档不含 `.git`，这与正常 git clone 的测试条件不同，已单独记录阻断。

## 2. 原有验证结果

| 类别 | 结果 | 解释 |
|---|---|---|
| Bundle build / check | 两者 exit 0 | 源码与生成 bundle 校验通过，不等于适配器正式安装通过 |
| 离线主套件 | **196/196** | 使用测试 loader 与部分宿主 stub |
| SQLite 一致性 | **38/38** | 包含已有进程/注入故障场景，不是断电测试 |
| 完整性/隔离 | **50/50** | 既有断言全部通过，未包含全部本次新增反例 |
| synthetic recall | 80 probes，hit@1/@3/@5=1，MRR=1；p50 1.95ms，p95 2.38ms | 该合成集与机器的结果，不可宣称真实任务准确率 100% |
| scale smoke | 1,000 records × 声明的 1,000 tokens；完成 | 不是 100M 或生产负载复测；记录声明 token 不等于独立真实 tokenizer 测量 |
| 全部原有命令 | **87 次调用：86 exit 0，1 环境阻断** | 包括重复/重叠检查，不是 87 个独立测试套件 |
| Runtime JavaScript 语法 | **33 文件无语法错误** | 不证明功能正确 |
| Python AST 语法 | **279 文件无语法错误** | 未执行所有历史研究脚本 |

逐条命令、退出状态与时长见 [baseline-commands.json](baseline-commands.json)。

唯一非零项 `test/prospective-task-state-canary.py` 调用 `git rev-parse HEAD`，受到本机 Git/Xcode 许可证状态与归档不带 `.git` 的条件阻断。没有接受用户机器许可证、修改系统，也没有伪造 Git 输出让其变绿。它属于 **ENVIRONMENT_BLOCKED**，不能据此认定 Memex 产品代码失败；在正常 Git 检出与可用 Git 环境应另行重跑。

原始测试没有网络模型费用。没有把本次的本机微基准与不同机器、不同版本的历史结果拼成趋势图。

## 3. 公开的新增诊断

本目录提供 **18 个诊断观测：14 个 Core/CLI/备份探针 + 4 个 Fake DSH/真实 Store 探针**，共同支持 16 个问题编号。一个问题可能对应多个观测，不能把 18 当作独立漏洞数。敏感安全复现不在公开脚本内。

所有公开脚本已经按上传版本重新执行，均 exit 0、无 probeError。**这里 exit 0 表示诊断过程执行完成，不表示产品不变量通过。** 例如 F02 的输出正是预算超限；后续修复 PR 应将冻结期望转换为正式断言，并在修复前见红、修复后见绿。

| 诊断 | 本次观察 | 问题 |
|---|---|---|
| clean_adapter_startup | 三入口均 exit 1，缺少 memex-core | F01 |
| pinned_hard_budget | 预算100，返回估算1534，exceeded | F02 |
| canonical_block_order | 0,1,10,11,2,…,9 | F03 |
| mixed_ordering_units | 新局部 sequence 排到旧 timestamp 之前 | F03 |
| forced_nonresident_record | 旧必选记录未包含，候选40 | F04 |
| forced_canonical_record_mapping | canonical page 包含，但 forcedIds 空 | F04 |
| kv_reference_contract | 实际内容被 block ID 字符串覆盖 | F05 |
| grep_open_coordinates | 正文第2行被报告为20，按20打开为空 | F06 |
| concurrent_sticky_enable | L2开启覆盖了另一个连接开启的L3 | F07 |
| canonical_default_id_collision | 两个记录的事件数为[0,1]而非[1,1] | F08 |
| fts_migration_interruption | 故障后 records=1、FTS rows=0 | F09 |
| zero_term_reindex_on_reopen | 连续打开均再次读正文 | F10 |
| async_refinement_overwrites_new_status | superseded 被旧结果写回 active | F11 |
| failed_digest_attempt_accounting | 实际attempts=2、记录calls=0 | F12 |
| http_unicode_pagination | 出现U+FFFD且无准确续读位置 | F13 |
| backup_manifest_validation | 空清单、无数据库却 verify OK | F14 |
| restore_failure_preserves_existing_target | 注入复制错误后旧目标标识已消失 | F15 |
| bm25_score_direction | 两个负BM25值都被公式变为1 | F16 |

完整数值见 [evidence.json](evidence.json)，问题影响与局限见 [AUDIT.md](AUDIT.md)。特别注意：KV 探针针对参考字符串宿主，不是 GPU tensor 推理；确定性交错不是大规模并发压测；UI 响应乱序是源码风险分析，未运行真实浏览器。

## 4. 在独立工作副本复现

要求具备满足基线要求的 Node（本次实测 v25.9.0）。在固定基线的独立源码副本中运行，不要指向真实记忆 root。把此 PR 的审查目录放在副本的 `docs/reviews/2026-11-08` 下；不要为了复现把原有库或客户端配置复制进去。

```bash
# 当前目录应是独立的 Memex 基线副本；不要在生产进程使用的目录运行。
AUDIT_TMP="$(mktemp -d)"
mkdir -p "$AUDIT_TMP/home" "$AUDIT_TMP/tmp"

# Core 诊断无需测试 loader；其中安装探针刻意不加载测试解析器。
env -i PATH="$PATH" HOME="$AUDIT_TMP/home" TMPDIR="$AUDIT_TMP/tmp" \
  node docs/reviews/2026-11-08/reproduce-core.mjs \
  "$PWD" "$AUDIT_TMP/core-results.json"

# 集成诊断使用假 DSH 宿主，因此明确启用仓库自己的测试 loader。
env -i PATH="$PATH" HOME="$AUDIT_TMP/home" TMPDIR="$AUDIT_TMP/tmp" \
  node --import ./test/register.mjs \
  docs/reviews/2026-11-08/reproduce-integration.mjs \
  "$PWD" "$AUDIT_TMP/integration-results.json"
```

上述是可移植 shell 示例；本次 macOS 运行还使用了 `sandbox-exec` 禁网。其他平台应在自己的受控离线环境运行，不把设置空环境变量误当网络沙箱。探针只创建和清理自身 `mkdtemp` 下的合成文件，结果 JSON 保存在传入的输出路径；请不要指定覆盖已有重要文件的输出位置。公开脚本不是通用数据恢复工具。

原有核心检查：

```bash
node scripts/build-bundle.mjs
node scripts/check-bundle.mjs
node --import ./test/register.mjs ./test/run.mjs
node --import ./test/register.mjs --test ./test/sqlite-consistency.mjs
node --import ./test/register.mjs --test ./test/integrity-regression.mjs
node --import ./test/register.mjs scripts/recall-eval.mjs --suite synthetic --threshold 0.9
node --import ./test/register.mjs scripts/scale-bench.mjs --records 1000 --tokens 1000
```

注意，build 会生成 bundle 文件；只在独立副本运行。精确原始命令清单在 JSON 中。重点源码及入口哈希见 [source-sha256.json](source-sha256.json)，防止把另一版本的结果误归到本次基线。

## 5. 历史研究的独立重算

只对仓库内公开逐行结果进行算术复核，没有重新调用历史 solver/judge。

输入：`docs/assets/benchmarks/production-task-state-20261102/results.json` 与 `rescue-results.json`。按 task ID 对接：优先保留原始有效 review，缺失时使用明确登记的 post-hoc replacement；只计 completePair。

重算得到28对：control高4、持平20、Memex高4；均分均为0.8928571428571429/2。与仓库敏感性分析一致。这个重算确认的是汇总算术，不验证 judge 判断、历史源码正确性或成本发票。

主队列13对原始有效评分与15对事后替换仍必须分开解释；不能因补齐28对就声称原计划评审无缺失。四任务后续队列用不同 commit，不并入同一个效应估计。只有6/28对输入有逐流最终对账，不能把该子集直接外推为全队列节省。

## 6. 明确未验证

没有真实 DSH GUI 或所有支持客户端的实机运行；没有 Windows/Linux 复测、GPU/vLLM 推理、网络供应商故障实测、断电耐久性测试、新的前瞻生产 A/B 或独立人工评审。静态安全/资源风险未等同于利用成功。

审查发现足够多可修复的问题，但不能保证缺陷穷尽。原有安全修复和作用域约束的存在也不能自动被新反例否定，应按对应入口与不变量逐项判断。

## 7. 交付完整性检查

上传前检查：全部 JSON 可解析；两个公开脚本语法正确且重新执行无 probeError；16个问题都有源码锚点、修复与验收；内部相对文档链接存在；报告不含真实机器绝对路径、凭据、会话正文或私密安全探针。新增文件限定在本审查目录，原运行时代码不变。

GitHub 新 PR 的 Actions 状态应以该 PR 的实际运行结果为准。本机既有套件通过不等于上传后 CI 已通过；如交付时 CI 尚未结束，应直接报告状态而不是推断成功。
