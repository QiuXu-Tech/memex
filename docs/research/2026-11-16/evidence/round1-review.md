# R1 独立定向复核

2026-11-16。基线 foundation `c3fa508e53043e40eb1022d3606f0d467219a6e2`。本次只读实现与测试；作者实现、本人未实施该代码。R1 的审查证据不等于性能达标或生产验收。后续分支的文档清理提交不改变本报告绑定的 core 基线，仍需以 benchmark 的快照哈希确认实测版本。

## 结论

**未发现必须修复的 R1 正确性问题，可以与独立冻结快照上的正式性能结果一起判定该轮。** 不应在结果出来前宣称速度达标。独立审查没有穷举所有 JS 对象/系统运行时，也没有验证模型或真实生产任务。

## 实现核对

- `context-events.js` 在已有的 session 分组及组内排序后，对可验证的普通对象有限数值键启用已排序队列维护。推进的队首经 lower_bound 放在相等头之前，符合原先 stable sort 对上一轮队首的优先关系；singleton 流使用一次稳定 sort。其余值保留原 repeated-sort 路径。整体保持流内 sequence/block/id 次序，跨流只能在当前头之间按时间及原比较器选取，不把所有页面全局按时间排序。
- hasStableOrderKeys 对 page Proxy、非普通原型、排序字段访问器、缺失 id/sequence、非有限或非数值键回退。session 分组仍用原始 Map 与独立 Symbol 行为；检查字段描述符在分组之后、组内排序之前。测试覆盖代理与 getter 的访问 trace 及异常、同键稳定顺序、Unicode 等价 ID、时钟逆行、missing/null/空 session。该实现假定 Node 标准内建方法未被恶意替换，且没有把 fallback 宣称为全面的任意运行环境保证。
- `test/reference` 两份引用的字节在测试中通过移除头部并还原相对导入与 foundation 指纹比较。测试比较排序返回对象身份、完整 materializer 结果及自定义 counter 调用文本/顺序和错误。本人独立运行 Node 24.22.1 差分套件 **20/20 通过**，覆盖作者所列 500 个排序及 500 个材化随机案例。本人另用种子 135792468 运行 2,000 个短排序 differential，加入重复 ID、Unicode 等价键、±1e308、±Number.MIN_VALUE、±0 和混合 session，逐位置比较对象身份，全部通过。该随机抽查不是对所有对象与 locale 的证明。
- 独立读取作者日志中 audit **43/43** 的结果；本人没有重跑该套件。当前作者回执中的 R1 core、未变 materializer、测试及两份参考文件哈希均与读取时文件一致。工作树仍在并行工作，正式 benchmark 必须绑定独立快照而非这个可变目录。

## Benchmark 开跑条件

benchmark follow-up 四项必修已落实，新 preregistration 的协议、脚本和 fixture 当前哈希与登记一致；baseline 17 个 core 文件此前已逐一核对为 c3fa508e。R1 冻结快照 `round1-core` 的 17 个 core 文件与 `round1-version.json` 指向的提交 `6c460d7f9e23f60237edd870fe36b64b47a02684` 逐一比对一致，其中 context-events 哈希与本次审查文件一致；该提交相对 c3 的 core 唯一变化也是 context-events。计时方仍须保留运行前后源 hash、输入 hash、每 worker 原始记录和任何 mismatch/timeout。多 seed 的 paired median、每个 workload 回退、custom counter 与预算/工具依赖的语义硬门应同时满足。

本轮没有运行 benchmark；两千随机用例的测试时长不代表性能。允许局部微基准未达目标，保留负结果，必要时撤回候选。用户可感知的模型 token、费用、任务正确率以及真实客户端仍未由本轮建立。
