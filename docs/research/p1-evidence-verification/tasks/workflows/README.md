# 未验收的 P1 开发材料

本目录是 **controller/evaluator 研究材料集**，不能整份提供给方法或盲审人。

当前已物化 2 个固定 base 的真实来源种子，以及 8 个合成开发家族的 9 个分支，共 11 个物理包、22 份空白双审 packet。真实来源程序资格已记录；P1 工作流验收、人工审阅、裁决、原生压缩和方法执行在本目录中均为 **0**。D01 的两个反事实分支不增加独立 N。

主要入口：

- [TASKPACKS.md](../../TASKPACKS.md)：public 导出、来源资格、预算、CLI、缺口与失败处理。
- [ANNOTATION.md](../../ANNOTATION.md)：真实独立双审、第三方裁决和结构检查边界。
- [catalog.json](catalog.json)：11 个包的目录与状态。
- [source-draft-plan.json](source-draft-plan.json)：两来源包的 16 个未执行计划单元。
- [draft-plan.json](draft-plan.json)：八个开发主分支加两来源包的 80 个未执行计划单元。
- [shared-budget.json](shared-budget.json)：所有包共同的未冻结开发预算；reader/tokenizer 尚未确定。
- [acceptance/w-101.json](acceptance/w-101.json)：单包可检查的验收阻断示例。
- [checks/README.md](checks/README.md)：红→绿、完整性和可重建检查收据。
- [materialize.py](materialize.py)：只读固定 Git base、生成新目录的离线重建脚本。

每个包只有 `public/` 可以在校验后单独导出。`controller/`、`evaluator/`、manifest、来源映射、隐藏检查草案与完整研究目录不属于模型输入。盲审人只收到其自己的 `reviewers/review-…/` 包；两个 reviewer 标签与所有实际身份字段均为空。

来源源码的许可证随各 public 工作区保留：Flask 为 BSD-3-Clause，Requests 保留 Apache-2.0 `LICENSE` 与 `NOTICE`。完整 issue 文本及官方 solution/test patch 未复制进 public。源码摘录保持固定 base 字节；Flask 的一个 `.env` 测试夹具显式排除并记录。许可与上游定位见 [acquisition](../acquisition/README.md)，实际程序复现与隔离限制见 [reproduction](../reproduction/README.md)。
