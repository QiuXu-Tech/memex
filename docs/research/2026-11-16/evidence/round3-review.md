# R3 独立复核

结论：**检查范围内未发现必须修复的正确性缺陷。** 冻结候选的本地合成 wide 基准达到预注册累计 ≥2× 目标，小窗口回退护栏通过。此结论不等于真实生产验收。

## 实现与差分

- 默认计数的快速路径先对每个选中子集重新排序，逐页缓存 prefix/timeline 的 UTF-16 长度；计入 prefix、页间分隔符、最终页的完整 `trimEnd()`，对全体总长度只向上取整一次。各页 header 非空，故最终修剪只可能来自最后一页。空候选集合的预算探测返回 1，最终空窗口仍报告 0；独立检查了两种行为。
- 相同格式 helper 用于完整渲染与长度记录；页内容静态且无 Symbol 时才缓存。自定义 counter、动态对象、getter、Proxy、对象转换及 Symbol 场景保留完整渲染路径。语义保证限定于检查范围，并假设标准 Node 内建对象未被替换。
- 独立运行 Node 24.22.1 差分套件 36/36；另对冻结候选运行 `reviewer-r3-probe.mjs` 的 929 组基线对照，覆盖 25 类尾空白、emoji、字段 null/缺失/空值、truncated/source、预算切点 ±1、时钟倒退的子集重排，以及自定义 counter、getter/Proxy/coercion 轨迹。全部通过；随机/有限反例不能证明所有输入。作者 audit 43/43 为回执结果，本人未重跑。
- `round3-core` 17 个文件及差分测试文件与提交 `5fda3fbc764ffa914bb6c755a5adb6dcc77c94a6` 哈希一致。

## 正式基准

`round3-benchmark.json` SHA-256 `1ae75718a987b2a7d4da643d68f3dd1ed1d0d5b6aed1b01fda4c38d5471b190c`。baseline 为 foundation `c3fa508e`，candidate 为 R1＋R2＋R3 累计版本。基线和候选各 17 文件的计时前后哈希、冻结目录及提交一致；三个预登记文件匹配提交。20 个 worker 正常退出且 stdout 与记录一致；70 组场景配对的 fixture、输出及全部 420 个测量样本输出哈希相符。已用原始计时重算每场景配对速度比中位数及配对时间差中位数；本人没有重跑计时。

| 场景 | 配对速度比中位数 | 配对时间差中位数（候选减基线，ms） |
|---|---:|---:|
| order-singletons | 62.894× | -125.478 |
| order-streams | 5.089× | -5.129 |
| materialize-wide | 11.563× | -236.168 |
| materialize-tight | 2.275× | -15.512 |
| materialize-small | 2.223× | -0.160 |
| materialize-custom | 1.101× | -0.577 |
| materialize-tools | 2.492× | -19.047 |

wide 为 11.563×，达到预注册累计 ≥2× 目标；small 配对时间差为 -0.160 ms，满足最多增加 0.2 ms 的护栏。数字是这次累计对 foundation 的结果；R3 相对 R2 没有独立配对测量，不应将两次测量的比值当作 R3 增量因果效果。

测量环境 Node v25.9.0、macOS arm64；五个固定合成 seed、每 seed 两对 worker、每 worker 三次热测。置信区间仅对本批配对中位数作描述，pooled p95 不是生产尾延迟保证。日志中相邻的几何均值与中位数区间不能混为同一统计量；汇报以 JSON pairedMedianSpeedup 为主。没有真实客户端、模型调用、真实任务收益或账单证据。

公开 RESULTS 文档尚待另行通知后复核。
