# R2 独立复核

结论：**在检查范围内未发现必须修复的正确性问题，可供组长与 R2 基准结果一起判断。** 本轮合成测试相对 foundation 的累计性能与小窗口护栏通过；它没有单独隔离 R2 的增量收益。没有验证生产验收。

## 实现与测试

- `selectedIds` 索引只用于原始页面 id 已筛为非空字符串的情况；因此 Set 的 NaN 等价差异不适用。工具依赖的嵌套 Map 对 NaN 的 session/tool 键显式不建索引，保持原 `===` 不匹配；零与负零保持相等，`undefined` toolCallId 仍走单页分支。recordId 的 NaN 不建索引，缺失/null 按原 `??` 回退 id。索引中的数组按 sorted 顺序填充，retrievedIds 原序及重复迭代保留。
- 静态检查对 Proxy、getter、函数、非普通原型、共享/循环引用和深层值回退；自定义 counter 直接回退，保留完整渲染及调用时序。实现假设标准 Node 内建对象/方法未被替换，不是所有可能运行环境的证明。
- 独立运行 Node 24.22.1 差分测试 27/27，包括 500 默认 counter 索引案例和已有随机排序、完整输出与 counter 轨迹；另以种子 246813579 运行 2,000 个独立随机完整输出或异常对照，覆盖 NaN、±0、Infinity、Symbol、重复 retrieved IDs、工具依赖，并核对 3 类 getter、Proxy、自定义 counter 轨迹，均通过。随机测试不可穷举。作者审计测试 43/43 仅读取回执，本人未重跑。
- frozen `round2-core` 17 个 core 文件逐一与提交 `b270c77e6fbf090058620660d8d01a3d848cab3c`、计时记录哈希相符；测试文件哈希与该提交及作者回执相符。

## 基准数据复核

`round2-benchmark.json` SHA-256 `c7d6a867e43012ed3d36459bf2479fec0ddf53c04e5bf95013b99694bcceb95c`。基线是 foundation `c3fa508e`，候选是 R1+R2 的冻结快照。两侧各 17 个 core 文件的前后哈希相同并匹配对应提交及冻结目录；三个预登记文件匹配提交。20 个 worker 均正常退出，stdout 与记录一致，70 个场景配对及 420 个样本输出哈希均核对一致；从原始三次计时重算的配对中位速度比及配对时间差与汇总一致。本人未重跑计时。

| 场景 | 配对速度比中位数 | 配对时间差中位数（候选减基线，ms） |
|---|---:|---:|
| order-singletons | 63.189× | -126.947 |
| order-streams | 5.031× | -5.174 |
| materialize-wide | 4.074× | -194.429 |
| materialize-tight | 1.310× | -6.531 |
| materialize-small | 1.545× | -0.101 |
| materialize-custom | 1.077× | -0.449 |
| materialize-tools | 1.293× | -7.237 |

small 的时间差中位数 -0.101 ms，满足允许增加 0.2 ms 的护栏。wide 的累计 4.074× 超过最终目标的数值，但最终版本仍须再测；与 R1 独立运行的数值差不能当作严格配对的 R2 增量。

性能运行是 macOS arm64、Node v25.9.0、五个合成 seed，每 seed 两对 worker、每 worker 三次热测；bootstrap 区间仅描述本批样本，汇总 p95 不是生产尾延迟。日志的几何均值旁边列出的区间实为配对中位数区间，应以 JSON 的 pairedMedianSpeedup 为主。结果不证明模型质量、真实任务、token 账单或生产收益。
