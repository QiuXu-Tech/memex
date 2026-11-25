# 研究文档独立复核

复核对象 `repo/docs/research/2026-11-16/RESEARCH.md`，读取时 SHA-256 `2b922d3d97c8b661fc916660a538a1ca0c5b49fea9e5d1a9e185603392ea0d8c`。结论：**所核范围未发现须阻止本轮研究的实质性来源错误或路线冲突。** 没有复现外部论文、审计外部完整代码库，也没有验证外部系统的性能数字。

- [FlexA-Mem v1 摘要](https://arxiv.org/abs/2610.33274v1)及[锁定版本 README](https://raw.githubusercontent.com/WujiangXu/Flex-Amem/37ba0ce2b4d14f6746e819b6a2d728ad74c364f2/README.md)支持不可变原始历史、按预算生成 timeline 和原文/摘录、渲染无需新增 LLM 调用的概述。其任务表现不能移作 Memex 的效果。“最接近”的说法是架构选择判断，并非已量化的全面排名。
- [SimpleMem v3](https://arxiv.org/abs/2601.02553v3)和[A-MEM v11](https://arxiv.org/abs/2502.12110v11)摘要分别支持三阶段语义压缩/综合/意图检索及动态链接/记忆演化。SimpleMem [所引固定代码版本 README](https://raw.githubusercontent.com/aiming-lab/SimpleMem/db80b6a7c591e0ea730a058e9f5fc4eb06572299/README.md)含多模态等扩展，文档明确区分其与论文版本是合理的。
- [LLMLingua 固定文档](https://raw.githubusercontent.com/microsoft/LLMLingua/01b9e9481d7395e1e83a48df4a062b11f6304325/DOCUMENT.md)、[SQLite FTS5](https://www.sqlite.org/fts5.html)、[Python heapq](https://docs.python.org/3.14/library/heapq.html)及[tiktoken 教学实现](https://github.com/openai/tiktoken/blob/79dc2c0533685b893616c78160b5d9e40876e724/tiktoken/_educational.py)与表中受限表述一致。heapq.merge 要求各输入按合并键排序；文档并未把它直接用于存在时钟倒退的 Memex 数据。任意 counter 的非加性限制是接口层面的保守要求，而非声称所有 tokenizer 都具有同一种性质。
- [EvalMem v2](https://arxiv.org/abs/2609.22231v2)与[LongMemEval-V2 v1](https://arxiv.org/abs/2605.12493v1)均为记忆评价相关资料，文档明确它们只是未来参考、本轮未运行。没有将回放或后补评当成生产/前瞻性盲评。
- 文档提出的稳定队列头、请求内索引、默认计数长度三轮路线与冻结 `PROTOCOL.md` 对应；协议、计时脚本、fixture 当前 SHA-256 仍与 preregistration 一致。路线是待逐轮验证的计划，不构成 R2/R3 已通过的证据。独立的 R1 测量结论与日志呈现注意事项见 `round1-results-review.md`。

本审查针对来源所载概念和文档边界；没有验证各仓库完整历史或证明任何外部论文结论适用于 Memex。
