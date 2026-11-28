# 开发材料的检查记录

本目录只记录工程验证，所有数字均不属于论文效果结果或人工标注。

- `tdd-red-taskpack.*`、`tdd-red-annotation.*`：先写行为测试、模块尚未实现时的 import failure。它们是最初 red 阶段，不能声称所有测试逻辑当时已经执行。
- `tdd-red-boundaries.*`：随后实际执行的 3 个失败：嵌套 public JSON 答案字段未拦截；漏配显式 denylist 时未来 fix 身份未拦截；任务包摘要与 experiment freezer 摘要算法不一致。修复后对应测试转绿。
- `tdd-red-dotenv-fixture.*`：显式排除并记账固定 base 中 `.env` 测试夹具之前的失败。严格无 `.env` 边界保留。
- `first-materialization-rejected/receipt.json`：首次实际 Flask 材料化被该边界拒绝；记录原规格、拒绝原因和后续排除的限制。
- `tdd-red-source-qualification.*`：错误 base 可借用既有来源资格的回归。修复后必须与真实 base/fix 复现收据及其摘要绑定。
- `tdd-green-taskpack.*`、`tdd-green-annotation.*`：最终两个测试集的命令、退出码和完整输出。
- `collection-validation.json`：实际全部包校验、22 份空白模板、初始上下文与分页材料，以及固定 base 导出资格检查。
- `rebuild-check.json`：从相同固定来源重建到临时新目录，比较逐包 manifest/public 和盲审 packet 绑定的结果。运行路径不同的 draft-plan 不作逐字相等要求。

校验器始终保留 `accepted=false`、`frozen=false`；成功表示输入和记录的结构/摘要一致，并未检查真正发生了 P1 工作流或人类审阅。实际沙箱、通用 arm runner、原生 prelude 与 compaction、后续行为评分、独立人工评估仍需完成。
