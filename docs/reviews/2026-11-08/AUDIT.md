# Memex 全仓架构与缺陷盘点

基线：`5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182`；审查日期：2026-11-08；相关实测见 [VALIDATION.md](VALIDATION.md)。

## 1. 方法、范围与判定标准

审查覆盖仓库清点、14 个包的职责与边界、核心运行路径、集成入口、恢复/迁移、测试与 CI、关键实验生成/汇总逻辑。固定源码归档有 1,405 个文件：packages 52、scripts 524、training 16、test 30、docs 770，其余为根目录/配置文件。手工深入读取关键路径，执行运行时语法检查和现有测试，再用独立合成探针反证关键不变量；**不声称逐行审完所有历史实验脚本，更不声称找到了所有潜在缺陷**。

证据等级：**R** 为本次运行复现；**S** 为源码可定位的静态风险、尚未证明全部运行影响；**L** 为已明确的产品限制或验收缺口。优先级：P1 为发布前必须处理的数据/契约/核心接入问题；P2 为重要正确性、性能或使用体验问题；P3 为维护性改进。这里不是 CVSS，未发现可据本次证据认定的远程 P0。

## 2. 当前架构与应保留的设计

```text
DSH 事件/工具 ─┐
Claude Hooks ──┼─> Agent/宿主适配器 ─> 共用 record/visibility/evidence 语义
MCP / Codex ───┘                         │
                                 LocalStoreCore
                        SQLite 索引/事件 + Markdown 正文
                                  热层 ↔ 冷层
                                        │
                    search / open / context pager / materializer
                                        │
                     有界文本注入       │       可选 KV 宿主实验
```

L1 是模型当前窗口，不是 Memex 自己的存储；L2/L3 是可检索的外部上下文池。存储容量大不等于模型能同时注意到全部内容。SQLite 保存的不仅是可重建索引，还包含 canonical events 与归档完成状态，因此不能把 Markdown 视作唯一真源。

建议保留：Core 与宿主隔离、存储与注入分离、冷热分层、显式 source/version/validity、默认查询不返回 superseded/expired、已有故障注入测试。暂不引入微服务、分布式数据库、全局常驻 Agent 或大型自训练 Router；具体错误应通过小范围契约修复解决。

## 3. 16 个确认的工程问题

以下每项给出最小修复与可检验的完成条件。原有测试通过不能替代这些新增断言。

### F01 · P1 · R — 干净检出后的三个 Agent 入口无法直接启动

**证据：** [packages/memex-mcp/bin/server.mjs:L12-L26](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-mcp/bin/server.mjs#L12-L26)；[scripts/link-workspace.sh:L6-L10](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/scripts/link-workspace.sh#L6-L10)；[docs/integrations/mcp.md:L8-L13](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/docs/integrations/mcp.md#L8-L13)。

**观察与影响：** 在完成 bundle build 的干净源码归档中，不使用 test/register.mjs，分别运行 MCP、Claude、Codex 入口，三者均退出 1，报找不到 @qiuxu/memex-core。测试加载器替开发环境完成了包解析；bundle 内的链接不等于仓库根目录或各适配器的解析路径。

**最小修复：** 先补一个明确的本地安装/链接步骤，覆盖 core 与三个适配器，并让文档命令执行它；保留正式包名与导出契约。下一步才考虑可发布打包，不能把测试 loader 当正式启动依赖，也不要求为了本问题引入全部 DSH 依赖。

**验收：** 干净归档、空 HOME、没有 node_modules 时，按文档完成安装后，三个入口无 test loader 可启动；再做真正 stdio initialize/list/write/search/open 流程。所有生成配置中的命令必须在新进程可运行。

### F02 · P1 · R — 硬预算选项没有约束强制页，宿主仍可能注入超限窗口

**证据：** [packages/memex-core/lib/context-materializer.js:L145-L231](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-materializer.js#L145-L231)；[packages/memex-checkpoint/lib/checkpoint.js:L409-L424](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-checkpoint/lib/checkpoint.js#L409-L424)；[packages/memex/cordis.patch.yml:L28-L34](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex/cordis.patch.yml#L28-L34)。

**观察与影响：** budgetTokens=100、enforceTotalBudget=true，加入一个固定页后返回 1,534 个估算 tokens，超出 1,434；状态虽如实为 exceeded，但该标志未实现硬预算语义，DSH 注入路径也不据此拒绝。U40 只覆盖普通页；U42 测试的是未启用硬约束时允许超预算，不能替代这个交叉场景。

**最小修复：** 明确 hard/soft 两种预算契约：hard 模式必须先为标题、前缀、回执等预留预算；固定页装不下时按公开规则节选或返回明确遗漏，不能悄悄越界。注入边界再做总量校验；可用时用宿主真实 tokenizer，否则标记估算与保守余量。

**验收：** 覆盖固定页/必选页大于预算、零预算、多页元数据、CJK/emoji、非法数值与真实 tokenizer。hard 模式输出总 tokens 不超限；soft 模式必须明确报告 exceeded，宿主不得无条件消费。

### F03 · P1 · R — canonical block 次序与跨来源时间排序不可靠

**证据：** [packages/memex-core/lib/context-events.js:L92-L142](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-events.js#L92-L142)；[packages/memex-core/lib/store.js:L647-L663](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L647-L663)；[packages/memex-core/lib/context-materializer.js:L187-L212](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-materializer.js#L187-L212)；[packages/memex-core/lib/context-pager.js:L105-L133](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-pager.js#L105-L133)。

**观察与影响：** 同一事件含 12 个 block 时，读回顺序为 0,1,10,11,2,…,9：字符串 event_id 打破 block 顺序。另一个探针中，新事件的局部 sequence=1 被排在更早的普通记录 sequence=1000 前；源码把局部事件序号和 createdAt 毫秒混作同一排序坐标。

**最小修复：** 新增明确的 session/turn/event/block ordinal；存储与 materializer 共用排序元组。跨会话使用事件时间加确定性 tie-break，同会话保留 event+block 原始次序。关联 tool-call/result 保持拓扑约束；无法确定的跨来源顺序应标明不确定，而不是声称精确还原。

**验收：** 12/100 blocks、同毫秒、多会话从 sequence=1 重置、普通记录与 canonical 混排、tool-call/result、重启读回，顺序均符合冻结预期。迁移不丢失旧事件。

### F04 · P2 · R — 必选记录并未保证进入候选集，record/page ID 映射也会失效

**证据：** [packages/memex-core/lib/context-pager.js:L90-L153](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-pager.js#L90-L153)；[packages/memex-core/lib/context-materializer.js:L149-L156](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-materializer.js#L149-L156)。

**观察与影响：** 写入一个老记录及 45 个新记录，给予充足预算并在 alwaysIncludeIds 指定老记录，结果仍遗漏它：候选集只从固定大小的 pinned/open/recent/search 结果取。canonical 记录展开为 record:event 的 page ID 后，传入 record ID 对应的 forcedIds 又为空。

**最小修复：** 在现有可见域内显式读取必选 record ID，再展开到 page ID；返回 missing/not-visible/over-budget 原因。必选读入数量有上限，但不得绕过 workspace/session 或有效期策略；与 F02 共同定义“必须纳入”遇到硬预算时的失败语义。

**验收：** 超过 recentLimit 的旧必选记录仍可选择；canonical 记录整组或被明确选择的块可追踪；不可见 ID 不泄露内容；缺失/超限不能伪装成功。

### F05 · P2 · R — 参考 KV 宿主与通用适配函数契约不兼容

**证据：** [packages/memex-core/lib/context-kv.js:L53-L64](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-kv.js#L53-L64)；[packages/memex-core/lib/context-kv-host.js:L33-L49](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/context-kv-host.js#L33-L49)。

**观察与影响：** materializeWithHost 传给 registerPrefix 的是 block ID；PagedKvContextHost 却将参数当文本并重建相同 block。探针的 ACTUAL-CONTENT 被覆盖成 audit:block:0。Mock 接口与参考实现不一致，单独测试各自不会暴露此问题。这个结论针对字符串参考宿主，不等同于已证明真实 vLLM GPU KV 被损坏。

**最小修复：** 统一为显式 createBlock + registerPrefixIds，或者单独命名 putPrefixTexts，禁止同名不同语义。prefix 命中必须表示完整且连续的有效块，淘汰应整体失效或返回明确最长连续前缀；检查必要方法而非仅相信 capabilities 字符串。

**验收：** 用真实 PagedKvContextHost 跑通 materializeWithHost；检查内容与引用未变、容量不足、缺失块、空方法宿主及部分淘汰。GPU 路径另行验证，不借此单测宣布 GPU 正确。

### F06 · P2 · R — grep 返回的行号不能直接交给 open

**证据：** [packages/memex-core/lib/store.js:L1180-L1209](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L1180-L1209)；[packages/memex-core/lib/engine.js:L139-L178](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/engine.js#L139-L178)。

**观察与影响：** 正文第二行的目标被 grep 报为第 20 行，因为 grep 计算了文件 frontmatter；open 则以去掉 frontmatter 后的正文为坐标。按 grep 返回行号打开得到空正文。

**最小修复：** 统一工具坐标为正文 1-based 行号；或者返回显式 coordinateSpace 与可执行的 continuation 参数。保留原文件行号时必须另标，不允许由模型猜测 frontmatter 长度。

**验收：** grep→open 自动链路在普通、冷存、元数据长度变化、多行 Unicode 正文上均能读到同一匹配；分页边界不重复或跳行。

### F07 · P1 · R — 独立层级的并发启用存在丢失更新

**证据：** [packages/memex-core/lib/store.js:L1492-L1520](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L1492-L1520)。

**观察与影响：** 两个 Store 对同一 session 交错执行 enableLevel：A 读到旧值后，B 开启 L3，随后 A 写入开启 L2 的旧快照；最终为 L2=true/L3=false，而不是两个都开启。这违反粘性、只增不减的层级规则。复现以确定性交错模拟竞争，不是随机压力测试。

**最小修复：** 用单条原子 UPSERT，更新列使用 stored OR requested / MAX，而不是把两列整体覆盖；若以后支持关闭，使用独立且版本化的显式操作，不能混入此启用路径。

**验收：** 两连接交错启用、重复启用、跨进程并发均不会撤销已开启层级；adapter requestedLevels 仍保持更窄的读取限制。

### F08 · P1 · R — 未显式提供事件 ID 时会跨记录覆盖 canonical event

**证据：** [packages/memex-core/lib/store.js:L603-L640](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L603-L640)。

**观察与影响：** 为两个不同记录各追加 sequence=1、未传 ID 的事件，预期各有 1 条，实际读回数量 [0,1]。默认事件 ID 未绑定 record，而 event_id 为全局主键，UPSERT 把第一条转移到第二条。DSH 的显式 ID 路径不等于公共 Core API 安全。

**最小修复：** 默认 ID 纳入 workspace/session/record/event/block 的稳定命名空间；同 ID 更新必须验证 owner 与来源，不允许用 UPSERT 隐式转移归属。新记录与更新记录分开定义，迁移前检查现有冲突。

**验收：** 不同记录相同 sequence 均保留；相同事件重试幂等；跨归属相同 ID 拒绝且不修改任何旧事件。

### F09 · P1 · R — FTS 迁移中断可留下永久不完整索引

**证据：** [packages/memex-core/lib/store.js:L324-L402](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L324-L402)。

**观察与影响：** 模拟旧 FTS schema，在新表创建后中断进程（故障退出 91），重启后 records=1、records_fts=0；因为列已经是新结构，后续不再进入完整重建分支。LIKE 等回退可能掩盖遗漏，不能据此认为索引已恢复。

**最小修复：** 对 schema+回填采用事务或 staging FTS 表原子切换；记录明确 schema/index generation 与 BUILDING/READY，启动对账行数/抽样内容。失败必须重试重建，不把“列存在”当完成条件。

**验收：** 每个迁移阶段中断后恢复，检索与未中断对照一致；保留正文与 canonical event；升级前后都测大库与并发读写。

### F10 · P2 · R — 零 identifier 的正常记录在每次打开库时反复全文重建

**证据：** [packages/memex-core/lib/store.js:L388-L402](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L388-L402)。

**观察与影响：** 记录合法但没有 identifier token 时，record_terms 为空被当作“尚未索引”。探针连续两次打开同一库，两次都再次读取该正文。Claude hooks 每轮新进程启动时会放大这一重复成本。

**最小修复：** 单独记录 terms_index_version/terms_indexed，即使词项数量为零也表示构建完成；只对版本落后或正文 checksum 改变的记录增量更新。不要为避免扫描而悄悄丢失正文索引。

**验收：** 正常空 posting 的第二次打开不读全部正文；变更正文和迁移版本时恰好重建；用 1k/10k 记录测启动耗时、文件读取次数与 RSS。

### F11 · P1 · R — 异步卡片精修会覆盖较新的生命周期状态

**证据：** [packages/memex-checkpoint/lib/checkpoint.js:L222-L255](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-checkpoint/lib/checkpoint.js#L222-L255)。

**观察与影响：** Fake DSH + 真实 Store 中，模型精修等待期间将记录改为 superseded；模型返回后，refineCard 使用旧 record 展开重写，状态从 superseded 变回 active。问题是丢失更新，不是语言模型是否理解“被替代”。

**最小修复：** 给 enrichment 使用预期 recordVersion/checksum 的 CAS patch，仅允许更新 title/summary/useWhen 等指定字段；版本变化时跳过或重新读取并重评，不能把旧整行写回。删除之后的迟到任务不得重新创建同一记录。

**验收：** 精修期间发生 supersede、正文更新、冷移、删除、作用域变化，各自不被旧结果撤销；并发 patch 冲突有可观测状态。保留不调用模型的确定性归档路径。

### F12 · P2 · R — 摘要失败重试没有计入实际模型调用次数

**证据：** [packages/memex-compress/index.js:L238-L267](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-compress/index.js#L238-L267)。

**观察与影响：** 配置一个批次并让 synthetic provider 失败，实际触发 2 次 stream，compressionStats.last.llmCalls 却是 0：计数发生在成功返回之后。不能把失败调用的费用自动认作零，也不能把 maxBatches 当成总调用预算。

**最小修复：** 在 dispatch 前记录 attempt；分别统计 attempted/succeeded/failed/cancelled 与 usageKnown/chargeKnown。重试受独立 request/token/money budget 限制，未知费用保留 UNKNOWN，不猜测。

**验收：** 首轮失败、重试失败、超时、取消、部分 usage 都能与逐请求账本对齐；成功数和调用数不混用，摘要失败不删除原文。

### F13 · P2 · R — HTTP 字节截断破坏 Unicode，分页没有可靠续读位置

**证据：** [packages/memex-api/index.js:L36-L40](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-api/index.js#L36-L40)；[packages/memex-api/index.js:L199-L229](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-api/index.js#L199-L229)；[packages/memex-ui/client.js:L138-L141](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-ui/client.js#L138-L141)；[packages/memex-ui/client.js:L365-L379](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-ui/client.js#L365-L379)。

**观察与影响：** 100,000 个汉字的合成正文被读取后包含 U+FFFD；返回长度 87,395（含截断标识），声明 bodyLimit=200000，且没有可续读的 nextOffset。UI 只显示 data.body，没有继续加载；快速切换记录时也未以请求身份防止迟到响应覆盖当前正文。

**最小修复：** 先在 Unicode 边界切片，再按 UTF-8 字节预算收紧；返回 consumedChars/nextCharOffset，采用统一字符坐标。UI 添加继续读取与截断提示，并用请求序号/AbortController 丢弃过期响应，不引入新页面体系。

**验收：** 汉字、emoji、组合字符、超长单行、多页拼接无替换/丢失/重复；A/B 响应逆序时当前展开项仍显示正确正文。UI 竞态部分为静态发现，尚未运行真实浏览器复现。

### F14 · P1 · R — 空清单也能被备份校验器判为 OK

**证据：** [scripts/memory-backup.mjs:L94-L111](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/scripts/memory-backup.mjs#L94-L111)。

**观察与影响：** 只有 manifest.json、files=[]，没有 index.db 的目录，verify 仍退出 0 并打印 OK (0 files)。目前证明的是“列出的文件哈希一致”，并非备份完整或可恢复。

**最小修复：** 校验 manifest 版本、必需数据库项、完整文件清单、路径约束、数据库与记录的一致性；缺少必需项或未知 schema 必须失败。校验分 integrity（字节）与 restorability（数据库/引用），不要用一个 OK 夸大保障。

**验收：** 空清单、缺失 DB、损坏 DB、缺正文、错误 root/path、残留恢复日志、陌生格式都明确失败；正常备份必须经过临时恢复后能读回记录与事件。

### F15 · P1 · R — 强制恢复先删除旧目标，复制失败会丢失原状态

**证据：** [scripts/memory-backup.mjs:L114-L184](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/scripts/memory-backup.mjs#L114-L184)。

**观察与影响：** 在全新的合成恢复目标放入旧状态标识，然后注入 cpSync 失败。restore --force 退出 1，且旧标识已不存在；目标先 rm，再复制的顺序不具备失败回滚。没有触碰任何真实目录。

**最小修复：** 先恢复到目标同文件系统的私有 staging 目录，完成哈希、DB 完整性、路径重定位和引用检查，再在停写/锁定条件下交换目录；旧目录保留为可回滚副本直到验证成功。记录中断状态并提供明确恢复命令，禁止运行中的两个写实例并存。

**验收：** 复制、磁盘空间、校验、重定位、交换前后、进程中断等故障点，至少旧状态或完整新状态始终可恢复；不允许半目录被当作活动库。断电持久性需要另外验证，不能用进程中断测试替代。

### F16 · P2 · R — SQLite BM25 的负分被重排公式压成相同贡献

**证据：** [packages/memex-core/lib/store.js:L1074-L1105](https://github.com/QiuXu-Tech/memex/blob/5bf65f6ede777c00cf35ec2ba1e4b14dbc17f182/packages/memex-core/lib/store.js#L1074-L1105)。

**观察与影响：** SQLite 实测得到 -1.6923076923076922e-6 与 -1e-6 两个不同 BM25 值，但现行 1/(1+max(0,rank)) 对两者都得到 1。FTS 初选排序仍起作用；问题是混合重排中的 BM25 幅度信息被消掉，不能据此直接量化最终召回损失。

**最小修复：** 采用保持正确方向的归一化，或按名次做简单 fusion；权重由独立验证集确定。避免为了修负号顺便重写所有检索规则；先加入贡献可观测日志与 A/B。

**验收：** 不同有效 BM25 值的贡献有正确单调关系；精确标识符/CJK/冷记录测试不退化；冻结检索集上报告 MRR/nDCG 与尾延迟，而非只看两条样例。


## 4. 静态风险与架构债务（不能冒充已经发生的生产故障）

### A01 · P1/S — 模型增强与关键归档队列耦合

`memex-checkpoint/lib/checkpoint.js:222–255, 339–361, 385–405` 中卡片精修、全局串行归档链和查询扩展包含模型等待；`memex-compress/index.js:166–187` 的流也缺少这里可见的 deadline/AbortSignal。一个挂起增强可能造成队头阻塞；实际供应商无限挂起未测试。

**修复：** 持久归档提交不等待 enrichment；增强放进有界、可取消、按 session 隔离的队列。每项 deadline、总尝试预算和幂等键明确；超时退回确定性卡片，后台任务仅 patch 仍匹配版本的记录。**验收：** 一个永不结束的假 stream 不阻止其他会话归档、drain/关闭有界、队列长度/RSS 有上限。

### A02 · P1/S — 驱逐路径对未知内容类型的保真不足

`memex-evict/index.js:75–99, 195–222` 对不认识的非图片 block 可能只渲染类型名；驱逐主要写渲染文本，不能自动获得 compaction 的 canonical event 保真保证。已有“跳过图片/超大事件”保护应保留。

**修复：** 定义各宿主版本允许无损驱逐的类型表；未知、无法恢复的消息保持在 L1，或先写完整 canonical envelope 并验证再替换窗口。工具调用关联信息不能只剩显示文本。**验收：** text/tool-call/result/附件引用/未知 block 的逐类型 round-trip；无持久副本时绝不裁剪原上下文。这里不要求悄悄复制外部附件字节。

### A03 · P2/S — GPU KV 原型缺少生产缓存身份与完整性契约

`training/memex_kv_connector.py:129–142, 295–350, 479–555` 的 key 主要来自 token bytes、tenant 与多模态摘要；没有在该 key 中绑定完整模型 revision/tokenizer/RoPE/adapter/dtype/分片配置。manifest 校验只遍历已有条目，没有证明所有预期层齐全；写入/逐出与读入缺少明确发布和占用协议；prefix_tokens=0 与极短前缀的块映射也需要单独契约。GPU、多进程和多卡路径本次未运行，不能声称已复现模型错误输出。

**修复：** 先冻结兼容版本和完整 cache fingerprint，随后实现非空且覆盖全部预期层的清单、校验和、原子完成标记、占用租约及失败回退。对齐函数覆盖 0、1、block_size、block_size+1；明确 cuda device。先与上游 KV offload 能力对照，不继续把 debug connector 当产品后端。

### A04 · P2/S — 存储与检索的规模上限未被容量数字定义

`store.js` 的同步数据库/文件调用与若干 `.all()`、bounded body scans，以及 `memory-backup.mjs:55–82` 的写锁内全量复制，可能造成大库下事件循环和写入延迟。100M tokens 是逻辑容量，不是吞吐/延迟承诺。40-bit 短随机 record ID 与允许 UPSERT 的写入口也是长期增长下应收紧的身份契约，但本次未观察到随机碰撞。

**修复：** 先测文件读取次数、候选数、锁持有时间、event-loop lag，再做分页/增量索引/有界 worker；不先迁移到外部数据库。新建记录采用足够长 ID，更新必须显式且受可见域/版本约束。备份制定低停写方案及明确最大阻塞预算。**验收：** 1k/10k/100k 记录、多进程读写、备份并发压力，必须保持一致性而不是只追求平均速度。

### A05 · P2/L — 发布、协议、文档与 CI 尚未构成同一产品合同

CI 主要验证测试 loader 与假宿主；安装缺陷 F01 正好说明此盲区。声明 Node >=24 不等于覆盖所有 24.x；应声明实测最低 minor。只支持旧 MCP 协议版本本身不构成错误，规范允许协商旧版本；需要真正验证 initialize 顺序、兼容矩阵、错误处理和取消，而不是单看日期。不要给本地 stdio 服务无理由叠加 HTTP OAuth。

`SECURITY.md` 仍写支持 0.1.x；安装文档存在历史测试数；`architecture.md` 自称保留早期描述；README 中 `/memory compress` 与实际命令表需要逐条对照。研究 KV 文件声明 Apache-2.0、主项目 MIT，发布时应补第三方许可清单与必要上游文本，不能把所有文件笼统标作同一许可。本项不作法律合规认证。

**修复：** 一个生成式配置/命令快照、无测试 loader 安装 CI、实际宿主 canary、主分支必要检查与发布 checklist；维护者决定后再启用仓库规则，不由本次审查擅自更改。保留历史研究材料，新增研究采用统一 run manifest，不批量重写旧结果。

## 5. 必须正确归类的限制

| 项目 | 正确判断与处理 |
|---|---|
| Materializer 默认值 | 模块默认 off，但随附 bundle 显式 timeline-exact；要描述有效配置，不是简单判“文档与代码冲突”。 |
| `--all-tools` | 当前文档明确它控制 discovery，旧的直接工具调用仍兼容。不能宣称已证实“绕过原有授权”。若产品需要真正禁止维护操作，应另设执行 allow-list 并迁移兼容策略。 |
| Claude L2 绑定 | hooks 用客户端 session，MCP 默认另一个随机 session；PreCompact 私有副本不能自动被 MCP 打开，文档已说明。不要用全局固定 session 号换取表面可用而破坏隔离。 |
| 初次/空库使用 | 空库无需反复搜索；有记忆也不代表任务确实需要。把不调用 memory 纳入正常策略，而非强迫每轮使用。 |
| 证据 metadata | caller-asserted source/version 不等于源内容已验证；supersede 不是自动事实判断。引入新状态前先定义来源校验责任。 |
| 本地隐私 | 无遥测不等于内容永不出站；宿主可以把召回内容发给模型提供商。逻辑 scope 不等于 OS 沙箱。 |
| 持久化 | WAL+NORMAL 不能宣传断电后最近事务一定保留；现有故障测试主要是进程中断，外部文件也需 durability 设计。 |
| 完整上下文 | 文本 materialization 不等于模型原始 role/position/attention/KV 的完整恢复；API-only 路线必须以窗口内容与任务效果验收。 |

## 6. 研究证据审查

**已有机制证据应保留，但不得越级解释。** 10M 合成实验展示定点事实可被提供给模型；生成器 `scripts/long-context-10m.mjs:39–56` 还会用正确目标筛选命中、检索失败时退回目标记录。现有报告已披露 fallback 与缺少逐题证据。其 retrieval 指标不能等同于真实回答端到端表现；下一版须分为真实 top-k 策略与明确命名的 oracle-evidence 上限，任何 miss 不可自动获得真值正文。随机 seed 与递归磁盘统计也要修正。

最新 task-state 主队列 30 个登记任务、28 对完成，仅 13 对有原计划有效评审，15 对使用事后替代评审。本次从逐任务 scores 重算得到 **Memex 高 4、持平 20、baseline 高 4**，两组均分均为 **0.892857/2**。这支持“尚未证明优势”，不支持“已证明无价值”；更不应把不同 commit 的四任务补充队列当同一个预注册估计。

只有 6/28 对的最终输入得到了逐流消息对账；客户端列表价、账户时窗合计和逐请求实际扣费是三种不同口径。不能把没有 usage 或未结算的超时算作零费用。原研究主动披露了这些限制，问题是下一轮设计仍需要更强的计量和外部验收。

学习型 selector 在记录共享/模板问题上的 0.963 与记录隔离小集上的退化不能合并宣传。需要按 project/session/record 和时间切分，保留反例、无答案、过期事实和强干扰，先确认选择质量可泛化，再看最终完成率。

KV 比较的历史数据中 native hot prefix 第二次为 0.0187s，外置原型为 0.0583s，无缓存为 0.0924s；这些是特定模型/GPU/前缀的样本均值，不是当前复测。研究问题应改为“冷启动/重启/显存压力下，外置何时有净收益”，而不是证明外置缓存总是更快。

完整实验方案与投入顺序见 [RESEARCH_ROADMAP.md](RESEARCH_ROADMAP.md)。

## 7. 范围覆盖与剩余验证

| 模块/域 | 本次覆盖 | 未完成或应补的验证 |
|---|---|---|
| memex-core | store、事务、事件、pager、materializer、KV 接口、engine/manual/profile；核心复现 | 大库多进程/真实 tokenizer/断电与文件系统语义 |
| memex-local / seam | 后端转发、配置与 scope 能力声明 | 实际 DSH 版本组合 |
| memex-checkpoint | 归档、精修、回放、注入；真实 store 假宿主复现 | 真宿主消息持久/临时语义与挂起供应商行为 |
| memex-evict | 驱逐的类型/内容/回滚边界静态审查 | 宿主实际事件类型与未知 block round-trip |
| memex-compress | 冷移/digest/重试/计数；失败计数复现 | 真实模型摘要忠实度、取消与成本对账 |
| memex-tool / command | 可见域、工具参数与命令路径 | 每条帮助命令与真实客户端一致性 |
| memex-api / ui | record/status/restore/metrics 边界；Unicode 实测、UI 异步静态审查 | 浏览器并发/焦点/键盘可达性/实际宿主鉴权 |
| memex-mcp | 协议入口、工具 registry、分页、直接运行 | 多客户端协议合规、受限资源与取消；安全细节私密交付 |
| memex-claude / codex | init、hook、session、配置路径；直接运行失败 | 真实安装客户端、全局/项目/多窗口组合 |
| memex bundle | 构建/校验、有效默认配置 | 无 stub 的安装与发布产物 |
| training | 核心 KV connector、已有学习/质量实验结构 | GPU、跨模型、独立训练/验证集与硬件基准 |
| scripts / test / CI | 87 命令、备份/迁移/关键评测脚本、279 Python 语法检查 | 不是所有历史脚本的逐行审计或重跑 |
| docs / evidence | 关键结果、登记与复算、配置差异和限制 | 人工标签、完整发票、未公开原始运行证据 |

## 8. 外部核验资料

只采用上游文档解释协议/数据库语义，不以别的框架宣传材料证明 Memex 的效果。访问日期 2026-11-08。

- [SQLite FTS5 / BM25](https://sqlite.org/fts5.html#the_bm25_function)：解释排名数值方向，服务 F16。
- [SQLite PRAGMA synchronous](https://sqlite.org/pragma.html#pragma_synchronous)：区分进程恢复、事务一致性与断电 durability。
- [MCP Lifecycle（明确版本）](https://modelcontextprotocol.io/specification/2025-11-25/basic/lifecycle)：验证版本协商与生命周期，而非武断拒绝旧协议。
- [vLLM KV Offloading](https://docs.vllm.ai/en/latest/features/kv_offloading_usage/) 与 [Security](https://docs.vllm.ai/en/latest/usage/security/)：后续固定具体版本和配置重新对照；latest 文档是变化中的参考。
- [GitHub 私密安全公告](https://docs.github.com/en/rest/security-advisories/repository-advisories)：安全细节走 draft/private，不发布或申请 CVE。
