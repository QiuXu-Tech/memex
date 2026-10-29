# 记忆子系统架构

本文描述 `@qiuxu/dsh-memory` 子系统的精确实现：三级缓存模型（L1 = 模型原生上下文窗口，不存储；L2 = 会话私有归档 10M；L3 = 工作区共享归档 100M）、L2/L3 两个独立**粘性**开关、热池/冷存（cold）容量生命周期（回热/GC/配额/cold abstract）、按启用层级门控，以及 L1 驱逐（含敏感策略）、compaction 兜底、共享查询词与**混合检索**（FTS+LIKE+cold abstract+重排）、召回、双语容量提示、容量压缩（2 路并发 digest + 压缩历史）、metrics API、备份/校验/恢复、记录注入、持久化与 Web 面板/composer 圆环/HTTP API 语义。源码分为九个平级包（`packages/dsh-memory-seam`、`dsh-memory-local`、`dsh-memory-checkpoint`、`dsh-memory-evict`、`dsh-memory-compress`、`dsh-tool-memory`、`dsh-command-memory`、`dsh-memory-api`、`dsh-memory-ui`）；一个自包含 bundle（`packages/dsh-memory`，`scripts/build-bundle.mjs` 生成 `modules/`）在运行时组合**八条**独立插件行（`memory` / `memory-checkpoint` / `memory-tools` / `memory-evict` / `memory-compress` / `memory-api` / `memory-ui` / `memory-commands`），各自拥有 Config（或没有）与 fiber；除 seam 库外，消费者只使用异步 `ctx.memory` 服务，Web 客户端只使用 `/api/memory.*`。下文路径均相对 `memory-subsystem/packages/`；上游 DSH 侧的事件/服务契约来自随附 0.2.1-rc.3 构建（`dsh-compaction`、`dsh-session`、`dsh-session-query`、`dsh-llm`、`dsh-token-meter`、`dsh-client-modules`、`dsh-client-connection`、`dsh-api-remote-access` 的类型声明与 README）。

## 1. 设计边界与不变量

| 不变量 | 含义 |
|---|---|
| 不修改 compaction | 记忆子系统不替换 `ctx.compaction`，不写 `compaction/*` 事件，不重放或改写会话日志；归档是压缩摘要的“无损对侧” |
| 不新增会话事件类型 | 会话格式 v4 的读取方只接受带 `ignorable: true` 的未知事件，而在线的 `Session.append()` 无法设置该标记——“未知事件类型会使会话无法重新打开”。因此模型可见的记忆消息只能是 producer-owned source 的普通 user 消息 |
| 不阻塞步骤 | 所有钩子内部 try/catch，失败只 `ctx.logger.warn('memory-checkpoint: …')`；归档在串行后台队列执行 |
| 归档幂等 | `(sessionId, compactionId)` 决定记录 id 与 `archived_compactions` 主键；同一压缩重试/对账不会重复；记录的 `scope` 取首次成功归档时的 capture 层级（最深启用层） |
| 默认关闭与粘性层级 | L1 = 模型原生窗口（不由本子系统存储）；L2/L3 是两个独立、**只增不减**的开关，存 `session_settings.l2/l3`（旧 `mode` 列回填）；没有存储行时用后端 `defaultLevels`（默认 `none`）。两层都关时归档、注入、工具、API 记录读取与面板全部停用 |
| L1 驱逐走随附 seam | `memory-evict` 只追加已存在的 `compaction/prune` + 带 `surfaceOp:'replace'` 的 `user/message`；不替换 `ctx.compaction`、不调用 LLM、不新增会话事件类型；先写归档、再改 surface。含图片事件与单体超 `maxChars` 的事件**永不驱逐**（archived 文本会丢图/无法安全归档）；`captureLevel` 可把驱逐固定到 L2 |
| 冷存无损、目录只热 | 冷存（cold）只是把记录文件 rename 到 `<root>/cold/…` 并置 `records.cold=1`，正文不变、可按 id 打开/搜索；`catalog` 只列热记录，`facets` 分账 hot/cold；冷存不参与热容量/容量提示分母。**冷存可逆**：`restoreCold` 回热、`gcCold` 按预算删除；压缩配置 `coldQuotaTokens` 可在每次工具压缩后自动 GC。 |
| FTS + cold abstract 与混合检索 | `records_fts` 含 `(title,summary,use_when,tags,abstract)`；`records.abstract` 为冷记录正文前 ~1000 字（热记录空）。检索 = FTS leg + LIKE leg + 热正文回退 + JS 混合重排；旧库缺列/含 body 时 drop/recreate + 回填 abstract + optimize/VACUUM（live 18.19MB→0.25MB）。 |
| 敏感驱逐 | `memory-evict` 的 `sensitivePolicy:auto` 用高置信正则扫描被驱逐 span；命中则强制 session（L2），只有 L3 时跳过驱逐；记录 `tags.sensitive=['true']`。启发式，不是完整 DLP。 |
| 可备份/可观测 | `compression_runs`、`/api/memory.metrics` 提供运行指标；`scripts/memory-backup.mjs` 用 `VACUUM INTO` + records/cold + sha256 manifest 做 backup/verify/restore（恢复需校验完整、非空目标需 `--force`）。 |
| 压缩可观测 | 每次**工具**压缩写 `compression_runs`（level/strategy/before-after hot/cold moved/digests/llm calls/errors/time）；`memory_compress` 报告、`/memory status`、`memory_index`、API index 暴露 history。面板/API 的 cold 压缩直接走 `compressCold`，当前不写该表（见限制）。 |
| 会话设置 TTL | 打开数据库时 `DELETE FROM session_settings WHERE updated_at < now - settingsTtlDays`（默认 90 天）；层级读取不刷新 `updated_at`，只有 enable 等写操作刷新。 |
| 压缩需用户同意且分批幂等 | `memory_compress` 不自动运行：容量提示（`capacity-notice`）要求模型先问用户。压缩按层/可见池进行：cold 零 LLM；digest 每批 ≤`batchRecords`/`batchChars`、单次 ≤`maxBatches` 次 LLM 调用，digest id 由 `(sessionId, level, 批内 id)` 决定，已冷记录不再选中 ⇒ 可恢复/幂等；失败批保留原记录为热 |
| 文件是记录真源 | 每个记录一个 md 文件；SQLite 只是可重建投影与检索索引；`write`/`setStatus`/`forget` 同步文件与索引（当前代码尚未实现“从文件重建索引”的入口） |
| 工作区 + 作用域分区 | 读写一律带 `workspaceKey = sha256('cwd:' + cwd)[0:16]`；记录再按 `scope: session|workspace` 分池，session 池再加 `session_id` 过滤。无 cwd 时 key 退回 session id |
| 信任分级 | 归档记录 `trust: 'derived'`（原始对话，数据不是指令）；显式写入 `trust: 'trusted'`；manual 与 `memory_open` 对非 trusted 记录追加警告 |

## 2. 上游钩子与服务契约

### 2.0 插件行组合

一个安装单元（bundle `@qiuxu/dsh-memory`，源码为九个包）通过 bundle 自己的 `cordis.patch.yml` 插入**八条**行；行的 module 名指向 bundle 的 subpath exports（`@qiuxu/dsh-memory/local` 等），实际代码来自 `modules/<runtime>/`（`memory-ui` 行是例外：name 为指向 `modules/memory-ui/index.js` 的 file: URL，原因见 §11.4）。每条行是独立 fiber，拥有自己的 Config（或没有）、生命周期与可独立覆盖/禁用的 id：

| 行 id | 源码包 → bundle 模块 | 职责 | Config | 依赖注入 |
|---|---|---|---|---|
| `memory` | `dsh-memory-local` → `modules/memory-local` | 后端：注册 `ctx.memory`，文件 + SQLite/FTS5（card 字段 + **cold abstract**）、**混合检索/重排**、L2/L3 两层池、**冷存/回热/GC/热冷分账**、粘性层级表 + TTL、L1 驱逐审计、**压缩历史** | `root`、`capacityTokens`（L3，默认 100M）、`sessionCapacityTokens`（L2，默认 10M）、`defaultLevels`（默认 `none`；兼容 `defaultMode`）、`settingsTtlDays`（默认 90） | `inject: []` |
| `memory-checkpoint` | `dsh-memory-checkpoint` → `modules/memory-checkpoint` | compaction 兜底归档、回执/目录/召回（共享 `memoryQueryTerms`）、**双语容量提示**、恢复对账、卡片精修 | `autoArchive`、`autoRecall`、`catalogMaxChars`、`recallMaxChars`、`cardModel`、`capacityNoticeRatio`、`capacityNoticeCooldownMs` | `inject: ['memory']` |
| `memory-tools` | `dsh-tool-memory` → `modules/memory-tool` | 6 个工具（search/open/grep/write/index/**restore**）+ `tool:memory` 系统提示段落（order 950） | `maxInlineChars` | `inject: ['tools','systemPrompt','memory']` |
| `memory-evict` | `dsh-memory-evict` → `modules/memory-evict` | L1→L2/L3 原样驱逐（阈值/平衡 span/图片与超限加固/`captureLevel`/**敏感策略**/`compaction/prune` + surface replace/审计/失败回滚） | `evictAtRatio`、`retainRatio`、`maxChars`、`captureLevel`（`deepest`\|`l2`）、`sensitivePolicy`（`auto`\|`off`） | `inject: ['memory','tokenMeter','llm']` |
| `memory-compress` | `dsh-memory-compress` → `modules/memory-compress` | 注册 `memory_compress`（cold / digest **2 路并发**、**ids 强制**、重试/回退、配额 GC、历史） | `batchRecords`、`batchChars`、`maxBatches`、`minAgeMs`、`minDigestTokens`、`coldQuotaTokens` | `inject: ['memory','llm','tools']` |
| `memory-api` | `dsh-memory-api` → `modules/memory-api` | **9 条** owner 认证 `/api/memory.*` Fetch 路由（index/record/search/status/level/compress/restore/gc/**metrics**；record 分页） | 无 | `inject: ['memory','connection','sessions']` |
| `memory-ui` | `dsh-memory-ui` → `modules/memory-ui`（file: URL 行） | Web 客户端半侧：composer 触发按钮 + `shell.overlay` 面板（压缩/回热/⚠/已压缩 N 次/L3 敏感提示）+ 上下文圆环装饰 | 无 | 客户端 `inject: ['slots', 'uiSession']` |
| `memory-commands` | `dsh-command-memory` → `modules/memory-command` | `/memory` 人类命令（**restore / gc**；无压缩子命令） | 无 | `inject: ['memory']`；`commands` 服务经 `ctx.get` 可选使用 |

seam（`dsh-memory-seam` → `modules/memory-seam`）没有行：它只被其他模块 import，源码包之间用 `@qiuxu/dsh-memory-seam` 包名解析。策略/工具/命令/API 四类消费行只通过异步 `ctx.memory` 调用后端（`await memory.search(...)` 等），不访问 `.store`/`.core`；`memory-commands` 在缺失 `commands` 服务时静默无操作。后端包 `dsh-memory-local` 的默认导出是后端类（允许只挂载 `memory` 单行的“纯存储”部署），bundle 根 `index.js` 仅 `export {}`。行 id 与 Config 形状设计为在上游拆包后保持不变。

### 2.1 压缩标记对与 `compaction/summary`

随附 `dsh-compaction` 约定：一次成功压缩在会话日志上依次产生

1. `compaction/start`（**仅日志**，获取记录型锁，payload 含 `compactionId`、可选 `sourceCommandId`、`turn`）；
2. 摘要运行（后端调用 `ctx.llm.stream`）；
3. `compaction/summary`（**仅日志**）；payload（由随附构建的声明合并类型给出）：

   ```ts
   {
     compactionId: CompactionId
     sourceCommandId?: CommandId
     summary: ContentBlock[]
     shadowedRange: { start: SessionSeq; end: SessionSeq }
     shadowedSeqs: SessionSeq[]
     shadowedTokenCount: number
     provider: string
     model: string
     maxTokens?: number
     usage?: TokenUsage
   } & (
     | { rawOutput: ContentBlock[]; llmStreamCall: true }
     | { rawOutput?: ContentBlock[]; llmStreamCall?: never }
   )
   ```

4. 一条携带摘要的 `user/message` 替换被选范围（**表层唯一变更**，`surfaceOp: { op: 'replace', startSeq, endSeq }`，且 `sourceEventSeqs` 必须覆盖所有被遮蔽的表层节点）；
5. `compaction/end`（**仅日志**，释放锁）。

被遮蔽的原始事件仍保留在 append-only 日志中。记忆子系统在 (3) 被提交后归档 (4) 尚未发生：它读取的是原始日志，而不是替换后的表层。

### 2.2 本子系统使用的 Cordis 事件

| 钩子 | 模式（随附构建） | 本子系统用法 |
|---|---|---|
| `session/event` | `emit`，提交后触发、监听方异常被包含；签名为 `(session: Session, event: SessionEvent): void` | 每个事件写入每会话实时缓冲（上限 4000 条，供无 `sessionQuery` 时的归档兜底）；`event.type === 'compaction/summary'` 时把归档加入串行队列 |
| `agent/pre-step` | `waterfall`；payload `{ agent, messages: UserMessage[], turn, step, signal }`；`next(): Promise<PreStepDecision>`；`PreStepDecision = { kind:'reject' } \| { kind:'enter', messages, startsRequestSeries? }` | `{ prepend: true }` 注册：先调用 `await next()`，让其它监听者（含压缩策略）完成决定，再在 `decision.messages` 末尾追加回执/目录/容量提示/召回，返回 `{ ...decision, messages: [...decision.messages, ...additions] }`；`reject` 原样返回 |
| `session/disposed` | `emit` | 删除该会话所有内存态（缓冲、回执、digest、已展示集合、上次召回、对账标记） |
| `ctx.get('sessionQuery')` | 可选服务（随附组合由 `dsh-session-query-sqlite` 行提供；本机 base bundle 行 `session-query-sqlite` 配置 `path: ':memory:'`） | `readSession(id)` 返回经回放校验的完整原始事件 `{ events, … }`；`listEvents(id)` 返回逐事件轻量记录；`readEvent({ sessionId, seq })` 返回 `{ target, … }`。缺服务时归档回退到实时缓冲、对账跳过 |
| `ctx.get('llm')` + `session.requestHeader()` | 可选 | 卡片精修：`session.requestHeader()?.config` 给出路由 `provider`/`model`；缺任一项则不精修 |
| `ctx.commands` | 可选（`dsh-commands`） | `/memory` 命令注册（`memory-commands` 行）；缺服务时命令不注册、行本身仍可激活 |

`session/event` 的监听器是 **fire-and-forget**：回调在日志 push 之后同步调用，异常不会让提交失败。这意味着归档真正开始前，`compaction/summary` 已经持久化，但归档任务的结果不会反馈给压缩流程。上述监听器、每会话缓冲/回执/去重状态与串行队列都属于 `memory-checkpoint` 行实例；禁用该行只关闭策略，后端与工具行不受影响（反过来三条消费行都 `inject` 后端服务，后端停用则它们不激活）。

### 2.3 部署产物：source packages → build-bundle → bundle modules

源码真源是九个平级包（`dsh-memory-seam`、`dsh-memory-local`、`dsh-memory-checkpoint`、`dsh-memory-evict`、`dsh-memory-compress`、`dsh-tool-memory`、`dsh-command-memory`、`dsh-memory-api`、`dsh-memory-ui`）；运行时只安装一个 bundle `packages/dsh-memory`。`node scripts/build-bundle.mjs` 负责：

1. 把九个源码包复制到 `packages/dsh-memory/modules/<runtime>/`（runtime 名：`memory-seam` / `memory-local` / `memory-checkpoint` / `memory-tool` / `memory-command` / `memory-api` / `memory-ui` / `memory-evict` / `memory-compress`；复制 `index.js`、`lib/`、`client.js`、`package.json`，跳过 `test/`、`node_modules/`、`*.test.js`）；
2. 在 `packages/dsh-memory/node_modules/@qiuxu/` 建立 `<source-package-name>` → `../../modules/<runtime>` 的 symlink；
3. 写 `modules/.gitignore`（内容 `*`；生成的 `package.json` 还会删掉指向源码目录的 `dependencies` 字段）。

**为什么必须这样做**：profile 以 `link:` 安装 bundle，pnpm 不会为 linked package 安装 dependencies（bundle 的 `package.json` 没有 dependencies）；宿主的 linked-root 解析只在 linked 根目录内部为模块路由 `@deepseek-ai/*` 依赖（`dsh-app-boot` 的 linked roots：linked scope 跟随记录的真实目录，root 之外的 hoisted 依赖回落到原生 Node 解析）。复制 + 内部链接让每条行的 module 与它 import 的 seam 都落在同一个 linked 根内。bundle patch 通过 bundle 自己的 subpath exports 寻址模块：`@qiuxu/dsh-memory/local` / `…/checkpoint` / `…/tools`（`modules/memory-tool`）/ `…/api`（`modules/memory-api`）/ `…/commands`（`modules/memory-command`）；`memory-ui` 行用 file: URL（§11.5）。

维护规则：`modules/` 是生成物（`modules/.gitignore` 忽略全部内容）；改源码后必须重建；`node scripts/check-bundle.mjs` 逐文件比对源码与复制件并在漂移时非零退出（当前覆盖 **9 个模块**、含 `client.js`、`memory-evict`、`memory-compress`，已通过）；重建后要重新部署（Plugin Manager `remove_bundle` + `install_bundle`，行增删还需 Host/profile 重载；给已扫描包新增 `dsh.client` 需要重启 Host）。上游化后 bundle 正常声明九个包的 dependencies、由 pnpm 安装，该复制步骤会被删除。

### 2.4 L1/L2/L3、粘性层级与门控

- **层级**：`MEMORY_LEVELS = ['l2','l3']`，`MEMORY_LEVEL_SCOPE = { l2:'session', l3:'workspace' }`；L1 是模型原生上下文窗口（harness 拥有，不由本子系统存储）。每会话层级来自 `session_settings.l2/l3`；没有存储行时用后端 `defaultLevels`（默认 `none`，`l2|l3|both`；旧 `defaultMode` 兼容）。`enableLevel(sessionId, 'l2'|'l3')` 只写 1（**sticky，只增不减**）；`getMode/setMode` 仅为旧接口兼容（`session→l2`、`workspace→l3`，`off` 不会关闭任何层级）。
- **两层池**：记录 `scope ∈ {'session','workspace'}`。L2 = `workspaceKey + scope='session' + sessionId`，容量 `sessionCapacityTokens`（默认 10M/会话，私有）；L3 = `workspaceKey + scope='workspace'`，容量 `capacityTokens`（默认 100M/cwd，跨会话共享）。一个 DB、一棵 records 树。
- **捕获与可见**：`memoryCaptureScope(levels)` 返回最深启用层的 scope（L3 优先；两层关为 `undefined`）；`memoryVisibleScopes(levels)` 返回启用层 scope 的并集。新写入（evict/compaction 兜底/`memory_write`/`remember`）都写 capture 层；所有读取按可见并集过滤。
- **门控点**：
  - `memory-checkpoint`：`archiveCompaction` 与 `agent/pre-step` 先 `memory.getLevels(sessionId)`；两层都关时不归档、不 reconcile、清空该会话 pending 回执并直接返回原 decision；否则归档 `scope = captureScope`，目录/召回按 `{ scopes: memoryVisibleScopes(levels), sessionId }` 过滤。
  - `memory-evict`：两层都关时 no-op；否则按压力/平衡 span 搬 L1（见 §2.5）。
  - `memory-compress`：`memory_compress` 工具要求用户同意后由模型调用；两层关时返回 off 文案；按层/可见池操作（cold → `compressCold`/`archiveCold`，digest → 2 路并发有界批量 LLM + 重试/无损回退）；可触发冷存配额 GC 并写 `compression_runs`。
  - `memory-tools`：每个工具先解析层级；两层关返回固定 `OFF_TEXT`，否则 filter 用可见并集；工具共 7 个（6 + `memory_compress`）；`memory_index` 总是显示 L1/L2/L3 与两池，层级开启时追加 L1 已转移、可见池 byKind/pinned/open 与 compression-run 行。
  - `memory-commands`：`on l2|l3|both`、`status`（含 hot/cold 与 compression runs）、`search/remember/restore/gc`；两层关时这些读/写/GC 命令返回错误；`off` 返回“粘性不可关闭”；`pin|unpin|forget|restore` 先走 `visibleRecord`（校验 workspaceKey + 可见层级）。
  - `memory-api`：`index/record/search/status` 用 `visibleFilter(scope, levels)`；`level` 只接受 `l2|l3`；`compress/restore/gc` 执行冷生命周期操作（compress 仅 cold 策略，digest 返回 400）；record 支持字符 offset/limit 分页；两层关时 index/search 返回空记录。
  - `memory-ui`：面板/圆环弹层的 L2/L3 按钮调 `POST /api/memory.level`；已开启显示 🔒；面板「压缩」调 `POST /api/memory.compress`（cold），冷行「回热」调 `POST /api/memory.restore`；hot 比 ≥0.8 显示 `⚠ 热池 N%`，圆环 figures 追加 `⚠ 接近容量`。
- **迁移/旧数据**：升级前记录全部 `scope='workspace'`；旧 `mode` 列保留，打开 DB 时若缺 `l2/l3` 列会 `ALTER TABLE` 并一次性回填（`mode='session'→l2=1`、`workspace→l3=1`）。records 新增 `cold` 列（旧库自动补列默认 0）；冷存只 rename 文件，不迁移 scope。层级/可见性变化只影响之后的写入与过滤，**不迁移/不重分池既有记录**；compaction 兜底归档幂等键仍是 `(sessionId, compactionId)`。

### 2.5 L1 驱逐（`memory-evict`）

- **触发**：`agent/pre-step`（`{ prepend:true }`，先于自动 compaction 监听器）里，至少一个层级开启 + 能解析路由 `contextWindow` + `ctx.tokenMeter.measure(session).totalTokens >= floor(contextWindow × evictAtRatio)`（默认 0.6）。
- **选段**：跳过 system head；保留最新 `retainRatio × contextWindow`（默认 0.35）的 tail；从最老端选平衡 span（`toolPairingBalancedBefore`，随附 `dsh-compaction` helper），不超过 `maxChars`（默认 250k 字符；超出留到后续 step）。
- **加固（P0）**：含图片事件（`contentHasImage`，随附 `dsh-llm`）**永不被驱逐**——遇到第一个 image-bearing 事件即停止该批；单个事件渲染文本 > `maxChars` 时也停止该批（无法安全归档）。`captureLevel:'l2'` 且 L2 已开启时，驱逐写 L2（session 私有），L3 保持只读召回；默认 `deepest`（L3 优先）。
- **敏感策略**：`sensitivePolicy:auto` 时用 `SENSITIVE_PATTERNS`（私钥块、`sk-…`/`ghp_…`/`AKIA…`、`password/secret/api_key/access_token/authorization=…`）扫描 `selection.body`；命中时若 L2 已开启则强制 `scope='session'`，否则（只有 L3）**跳过本次驱逐**并 warn；记录 `tags.sensitive=['true']`。`off` 关闭扫描。记录先写成功再 append prune/replace；append 失败会尽力 `forget` 刚写的记录回滚。
- **写归档**：把 span 的每个 surface event 经 `session.deriveEventMessage` 渲染成文本，`ctx.memory.write` 写为 capture 层的 `episode`；record id `l1_<sha256(sessionId\0start\0end)[0:10]>`，`tags.level=[l2|l3]`/`tags.source=['l1-evict']`，`provenance.source='l1-eviction'`。**原文逐字，无 LLM 调用/摘要**。
- **缩 L1**：`session.append('compaction/prune', { shadowedRange, shadowedSeqs, shadowedTokenCount })` 紧接着 `session.append('user/message', receipt, { surfaceOp:{op:'replace',startSeq,endSeq}, sourceEventSeqs })`；receipt 是 `<l1-eviction>…</l1-eviction>` 的普通 user 消息（`source.kind='memory-recall'`、`form='l1-eviction'`）。这与随附 `compaction-tool-result-pruner` 的“影子价格 + surface replace”契约一致；`tokenMeter.measure()` 立刻下降，圆环经 prune shadow price 跟随。
- **审计**：`l1_evictions(session_id,start_seq,end_seq,record_id,shadowed_tokens,created_at)`，PK `(session_id,start_seq,end_seq)`，`INSERT OR REPLACE`；`memory.evictionStats(sessionId)` 汇总 count/tokens。
- **与 compaction 的关系**：不替换 `ctx.compaction`/`dsh-compaction-basic`（仍按标准 preset 挂载）；`dsh-compaction-basic` 默认触发为 `floor(min(W×0.8, W−O−headroom))`，驱逐把压力压到 0.6→0.8 之下，因此通常不需要有损摘要。无法安全选段/驱逐跟不上增长/context-overflow 时 compaction 仍兜底；`/compact` 手动命令不受影响。先写归档成功才 append prune+replace（避免“删了但没存”）。

### 2.6 冷存层与容量压缩（`memory-compress`）

- **冷/热分账与生命周期**：`records.cold INTEGER NOT NULL DEFAULT 0`（旧库补列）。`archiveCold(id)` 把文件从 `records/<ws>/<id>.md` rename 到 `cold/<ws>/<id>.md`，更新 `cold=1/path/updated_at`，并把正文前 ~1000 字写入 `records.abstract`/FTS `abstract`（空白折叠）；幂等；源文件缺失也容忍（摘要仍可读）。**`restoreCold(id)`** 反向 rename 回热目录、`cold=0` 并清空 abstract（已热幂等）；**`gcCold({scope,sessionId?,keepTokens})`** 按最老优先删除冷记录（文件+索引行）直到该层冷 token ≤ 预算（单次最多扫 5000 行）；`compressCold()` 是无 LLM 的热→冷批量下沉（API/面板/bench 使用）。
- **容量口径**：`facets` 的 `count/tokens/bytes` 含冷，另有 `hotCount/hotTokens`、`coldCount/coldTokens`；`capacityTokens`/`sessionCapacityTokens` 只与热池比较。`catalog` 固定 `cold:0`，footer 为 `Capacity (hot): hotTokens/capacity tokens across hotCount records, N cold records (X tokens, retrievable via memory_open) (L2/L3…)`。`search/list/get` 默认不做 cold 过滤，因此冷记录仍可被搜索/按 id 打开；召回 search 也包含冷记录。**FTS 只索引卡片字段**，正文-only fallback 只扫热池（≤400 条），避免每次搜索重复读冷层大文件；正文检索走 `memory_grep`/`memory_open`。
- **容量提示**（checkpoint 行，§4）：每会话按 `capacityNoticeRatio`（默认 0.8）检查已启用层热比；超阈值且距上次提示 ≥`capacityNoticeCooldownMs`（默认 10min）时，在目录之后注入**双语** `capacity-notice`（`[EXTRA CONTEXT CAPACITY / 额外上下文容量]`，clip 1400），要求模型先问用户再压缩。状态是每会话 `capacityNoticed: Map<sessionId, timestamp>`，`session/disposed` 清理。
- **`memory_compress` 工具**（compress 行注册，7 个模型工具中的第 7 个；`inject: ['memory','llm','tools']`）：
  - 参数 `level: l2|l3|auto`（auto=所有已启用层）、`strategy: cold|digest`（默认 cold）、`targetRatio`（0.1–0.95，默认 0.6）。请求未启用层直接报错；两层关返回 off 文案。
  - 候选：每层 `list({cold:0, sort:'oldest', limit:400})`，排除 `pinned`、`open-thread`、`updatedAt >= now-minAgeMs`（默认 1h）。`needed = max(0, hot - capacity×targetRatio)`；`needed==0` 或没有候选即空报告。
  - **cold**：直接调后端 `compressCold({targetRatio,minAgeMs})`（最老候选逐个 `archiveCold`）；零 LLM。
  - **digest**：按 `batchRecords`（20）/`batchChars`（120k）切批，**最多 2 批并发**（单次总调用 ≤ `maxBatches`=6）；每批一次 `llm.stream`（`maxTokens:1600`、`purpose:'memory-compress'`，提示词要求中文摘要 + 末尾 `ids: id1, id2` 关键 id，≤400 tokens）。空响应诊断抛错含 `textChunks/reasoningChars/promptChars`。生成 `dig_<sha10>`（hash 输入 `sessionId\0level\0批内 id`，确定性）的 `episode` 记录（`provenance.digestOf=[ids]`、`tags.digest=['cold-batch']`），随后把该批原记录全部 `archiveCold`；单批失败重试一次，仍失败则**无损冷移回退**（不写 digest、errors 报告、继续推进）；tiny batch（<`minDigestTokens`=2000）直接冷存不调 LLM；已冷记录不再被选中，因此可恢复/幂等。digest 本身仍热，可能被后续运行压缩。
  - **配额 GC**：`coldQuotaTokens > 0` 时，工具压缩结束若该层冷 token 超配额，自动 `gcCold` 回配额，报告显示 `cold quota GC removed …`。
  - **历史与报告**：每次工具压缩写 `compression_runs`；报告包含 `before/target/needed/hot-after/cold-moved/digests/LLM calls/gc/errors/history`。`/memory status`、`memory_index`、API index 也读 history。
  - 保护：只压可见池（启用层 + 当前 workspace/session）；pinned/open-thread/minAge 保护；不自动触发（需用户同意，见 §4）。
  - 入口：模型工具（cold/digest，需同意）+ 面板「压缩」按钮（API，cold-only；digest API 返回 `MEMORY_DIGEST_REQUIRES_MODEL`）。`/memory compress [l2|l3] [targetRatio]` 已补（cold-only，写 `compression_runs`）；digest 只能模型工具。

### 2.7 共享查询词与混合检索（hybrid retrieval）

- **共享提取器**：seam `memoryQueryTerms(text, maxTerms=20)` 是唯一查询词入口——引号 span（2–60 字）、拉丁标识符（保留 `_.:/-`，同时 push 小写变体）、CJK 整段前 12 字 + trigram + bigram，`QUERY_STOPWORDS`（中英疑问/虚词）过滤，去重后 ≤20 词。`store.search`、`memory-checkpoint` 的 auto-recall（`memoryQueryTerms(text,12).join(' ')` + 120 字回退）与 eval 共用。
- **索引**：`records_fts` = `(title, summary, use_when, tags, abstract)`；`records.abstract` 存冷记录正文前 ~1000 字（`abstractOfBody`，空白折叠），热记录为空。旧库缺 `abstract` 列 / FTS 列不全 / 含 `body` → `ALTER TABLE records ADD COLUMN abstract`、drop/recreate 5 列 FTS、全量重索引、回填冷记录 abstract；若旧表含 `body` 再 best-effort `optimize + wal_checkpoint(TRUNCATE) + VACUUM`（live 18.19MB→0.25MB）。
- **FTS leg**：`Array.from(term).length >= 3` 的词项（≤12）在 5 列上 trigram `MATCH ... OR`，bm25 rank，`LIMIT limit*8`。
- **LIKE leg**：前 8 个词在 `title/summary/use_when/abstract` 上 `OR LIKE`（覆盖 CJK bigram/短词/冷摘要），`LIMIT limit*8`。
- **热正文回退**：结果不足时对 `cold=0` 最近 400 条逐条 `grep`（正文-only 标识符）；冷完整正文不进 search 回退，用 `memory_grep`（按 `records.path` 读热/冷文件）或 `memory_open`。
- **混合重排**：对去重后的候选打分 `0.8×lexicalRank + 3×titleHits + 1.4×summaryHits + 1.2×useWhenHits + 1.6×tagsHits + 0.9×abstractHits + 0.4×recency(60d) − 0.1×cold`（lexicalRank 缺失时 0.35；同分按 `updatedAt`），再应用 tag/limit。
- **评测**（Lead 实测，`scripts/recall-eval.mjs`）：真实 40 条自然问题 hit@1 73% / hit@3 95% / hit@5 95%，cold recall 100%，p50 1.3ms；auto-recall 的 extracted-query 路径与 `memory_search` 同为 95%；合成套件 100%；基线 recall@5 67%。`scripts/recall-bench.mjs` 用长对话/卡片 vs 正文探针测召回与恢复 token 成本。
- **规模**（Lead 实测，`scripts/scale-bench.mjs`）：1000×10k tokens：DB 1.0 MiB、records 38.5 MiB、facets 0.63ms、list 0.55ms、catalog 1.21ms、search 1.2–5.6ms、grep 4.5ms、get 0.03ms；compressCold 700 条/7.00M tokens 0.10s；gcCold 350 条/0.02s。Phase-3 **10,000 条 / 100.0M tokens**：写入 2.8s、DB 9.0 MiB、records 384.8 MiB、facets 11.28ms、list 5.80ms、catalog 17.52ms、search 16.70–17.67ms（CJK 1.94ms）、grep 14.59ms、get 0.04ms；compressCold 5,000 条/50.0M tokens 2.56s（cold 文件 192.4 MiB、DB 26.6 MiB）；压缩后 search 28.77ms、catalog 26.28ms；gcCold 2,500 条/25.0M cold tokens 0.31s。**验收：card search p95 <50ms、grep <2s 达标。**

## 3. 压缩 → 归档时序

```
compaction backend           session log            memory-checkpoint             sessionQuery        LocalStoreCore
      |                          |                          |                          |                  |
      |-- compaction/start ----->|                          |                          |                  |
      |                          |-- session/event -------->| bufferEvent(event)       |                  |
      |   (LLM summarise)        |                          |                          |                  |
      |-- compaction/summary --->|                          |                          |                  |
      |                          |-- session/event -------->| bufferEvent(event)       |                  |
      |                          |                          | enqueue(job)             |                  |
      |                          |                          |   serial chain ──────────┐                  |
      |                          |                          |   wasArchived? ──────────┼─────────────────>|
      |                          |                          |   readShadowedEvents ───>| readSession(id)  |
      |                          |                          |<── events[] ─────────────|                  |
      |                          |                          |   buildCard(events, summary)                |
      |                          |                          |   archiveRegion(record) ─┼─────────────────>| md 文件(原子写)
      |                          |                          |                          |                  | records+FTS 事务
      |                          |                          |                          |                  | archived_compactions
      |                          |                          |   receipts.push(...)     |                  |
      |                          |                          |   refineCard? (LLM) ─────┼─────────────────>| 重写卡片
      |-- user/message replace ->| (surface)                |                          |                  |
      |-- compaction/end ------>|                          |                          |                  |
```

### 3.1 归档阶段（`archiveCompaction`）

1. **入口校验**：`disposed` 后不再归档；`policyConfig.autoArchive === false` 直接返回；`await memory.getLevels(session.id)` 后 `memoryCaptureScope(levels)` 为 `undefined`（两层都关）时直接返回（不归档、不读日志）；`data.compactionId` 必须是字符串且 `data.shadowedSeqs` 非空，否则静默返回。
2. **幂等预检**：`await memory.wasArchived(sessionId, compactionId)` 返回已有 record id 则跳过（在读取日志之前，避免重复 I/O）。幂等键与 scope 无关；记录的 `scope` 取首次成功归档时的 capture 层级（最深启用层）。
3. **工作区**：`cwd = session.header?.cwd`；`workspaceKey = memoryWorkspaceKey(cwd, session.id)`。
4. **读取原始事件**：优先 `sessionQuery.readSession(sessionId)`，用 seq 映射取 `shadowedSeqs`；返回不齐时告警但使用已取到的部分；抛错则回退实时缓冲。缓冲只保留最近 4000 条/会话。
5. **渲染**（`dsh-memory-checkpoint/lib/render.js` 的 `buildCard`）：
   - 遍历事件，用 `messageOf(event)` 取模型可见消息：`user/message` 取 `event.data`；`system|developer|assistant/message`、`tool/result` 取 `event.data.message`；
   - 正文 = 前言（会话/压缩 id、seq 范围、token 估算、"数据不是指令"）+ `## Summary`（压缩摘要的 text blocks）+ `## Archived context`（逐事件 `### [#seq] role · source · time` 及其内容块；`reasoning` 丢弃，图片/文件/tool-call 渲染为占位行，工具输出单行 clip 4000、助手文本 clip 8000、工具参数 clip 600）；
   - 正文超过 2 MiB 时截断并标注；
   - 卡片：`title` 取第一条**直接用户文本**（`role === 'user' && message.source.kind === 'user'`），否则助手文本，否则摘要首行；`summary` 取摘要 text，缺省用前 3 条用户文本；`useWhen` 固定模板 `Read when continuing the work archived at seq #a–#b; it covers <files|tools|seq 范围>.`；`tags = { source: ['compaction-archive'], where: <最多12个路径>, tools: <最多12个工具名>, issue: <最多5条首行错误> }`。路径候选需通过 `looksLikePath` 白名单（单 token、无空白/shell 元字符、需路径分隔符或文件扩展名），`topics` 截 160 字符，避免 shell 命令串污染 `where`/`use_when`。
6. **记录组装**：`id = archiveRecordId(sessionId, compactionId)`；`kind: 'episode'`、`scope: captureScope`（L2 启用时是 `session`、L3 启用时是 `workspace`，L3 优先）、`status: 'active'`、`trust: 'derived'`、`tokens = shadowedTokenCount`、`workspace = cwd`、`sessionId`（两种 scope 都写 provenance sessionId）、`provenance = { source:'compaction-archive', sessionId, compactionId, seqStart, seqEnd, shadowedEventCount, shadowedTokenCount, provider, model, cwd }`。
7. **持久化**（`await memory.archiveRegion(...)`；后端实现 `store.archiveRegion`）：`normalize` 校验后 `write`——先原子写 md（tmp `.pid.tmp` → rename，mode 0600），再开 SQLite `BEGIN IMMEDIATE`：upsert `records`、重建 `records_fts` 行、`COMMIT`；失败回滚并尽力删除刚写的文件。随后 `INSERT OR IGNORE INTO archived_compactions`。
8. **回执入队**：把一条回执文本加入该会话 pending 列表；最多保留 4 条（超出丢最旧）；把记录 id 加入“已展示”集合。
9. **可选卡片精修**（`refineCard`，`memory-checkpoint` 行）：`policyConfig.cardModel === 'off'` 或 `ctx.llm` 缺失或会话无路由 provider/model 时跳过；否则构造提示词，`llm.stream({ provider, model, messages, maxTokens: 600, sessionId })`，本地 `TextAccumulator` 聚合 `text-delta`/`block-end`，截取首个 `{` 到最后一个 `}` 解析 JSON；仅 `title` 非空才接受，其余字段回退确定性值，`tags.card` 最多 6 个；通过 `await memory.write({ ...record, id })` 重写文件与索引。异常时若 `attempt < 2` 且未 dispose，告警后等待 1.5s 重试一次，仍失败则只告警（保留确定性卡片）。`cardModel` 只允许 `'auto' | 'off'`，非法值由 `memory-checkpoint` 行的 `apply()` 在激活时抛 `TypeError`。

### 3.2 串行队列与恢复对账

- **串行队列**：`let chain = Promise.resolve()`；每个归档任务挂到上一条之后（`chain = job`）。因此同一 `memory-checkpoint` 行实例内多个会话的压缩归档不会并发写 SQLite；任务集合 `jobs` 用于 `drain()`（测试/teardown）。
- **恢复对账**（`reconcile`）：每会话首次 `agent/pre-step` 触发一次，后台执行：`sessionQuery.listEvents(sessionId)` → 对 `type === 'compaction/summary'` 的记录 `readEvent({sessionId, seq})` 取完整事件 → `target.type` 复核 → `wasArchived` 复查 → `archiveCompaction(target)`。这样进程崩溃/重启后，日志里已存在但未被本进程观察到的压缩会被补归档；对账本身也走同一串行队列，但不是 `enqueue()`，而是独立 job（仍在 `jobs` 集合中）。
- 无 `sessionQuery` 时对账直接跳过（实时缓冲无法覆盖历史）。
- **层级与对账**：对账只在至少一个层级开启的会话首步运行；`archiveCompaction` 每次按当时 `captureScope` 归档，因此历史压缩可能在之后开启层级时被补录成当时的 capture 层。**新增/切换层级不迁移/不重分池已归档记录**。

**实测证据（2026-10-28 21:18）**：一个历史会话（`session-3ca21388…`）在本进程恢复时被对账补归档了 2 个 compaction（seq #10–#2347 与 #3135–#5030），`archived_compactions` 恰好 2 行、无重复；其中一条卡片的 `kind/title/useWhen/tags.card` 被 LLM 精修改写（`open-thread` + 中文标题），另一条保留确定性卡片（`episode` + 模板 useWhen）——归档、幂等、恢复对账、可选卡片精修四条链路均有真实样本。

## 4. 下一步注入时序

```
agent loop                    agent/pre-step waterfall (memory 注册在最前)                 其它 pre-step 监听者
    |                                    |                                                      |
    |-- next() 推进决定 ────────────────>|                                                      |
    |                                    |-- await next() ─────────────────────────────────────>|
    |                                    |<──────────────── decision ───────────────────────────|
    |                                    |  decision.kind === 'reject' ? 原样返回               |
    |                                    |  levels = getLevels(session); 都关 ? 清回执并返回    |
    |                                    |  （memory-evict 行在此之前以 prepend 尝试搬 L1）      |
    |                                    |  reconcile（每会话一次，后台，不阻塞）                |
    |                                    |  receipts 非空 ? 拼回执 clip(…,1600) → addition       |
    |                                    |  catalogMessage()：内容未变/空库 → 跳过               |
    |                                    |  catalog 变化 ? 追加                                  |
    |                                    |  capacityNotice()：任一已启用层热比达阈值且冷却到期 → addition |
    |                                    |  最新直接 user 消息 → recallMessage() → addition      |
    |<── { ...decision, messages: [...decision.messages, ...additions] } ────────────────────────|
    |  消息进入本步请求（普通 user 消息，source.kind='memory-recall'）                           |
```

顺序固定为 **回执 → 目录 → 容量提示 → 召回**；它们都追加在 `decision.messages` 之后，因此模型把它们当作最新的用户输入读取。`prepend: true` 的意义是保证记忆监听器在其它 `agent/pre-step` 监听器之前拿到机会，同时 `await next()` 保证它看到的是最终消息批次（例如压缩替换后的 checkpoint）。

**层级门控**：`agent/pre-step` 在 `reject` 判断后先 `await memory.getLevels(sessionId)`；两层都关时 `receipts.delete(sessionId)` 并原样返回（不 reconcile、不注入）。开启时注入的目录/召回/容量提示都只针对 `memoryVisibleScopes(levels)` 的并集（L2 再加 sessionId）。`memory-evict` 行也用 `{prepend:true}` 注册、在压缩策略之前尝试驱逐 L1，但它是另一条独立 fiber（见 §2.5）。

### 4.1 回执

压缩归档成功后写入 pending 列表；下一次 `pre-step` 一次性取走并清空：

```
[MEMORY CHECKPOINT] The context that just left the window (seq #a–#b, ~N tokens) is archived
losslessly as mem_xxx (episode) "<title>". The checkpoint above is a lossy summary; call
memory_open mem_xxx when you need exact details, or memory_grep a distinctive string.
```

多条回执换行拼接后 `clip(..., 1600)`；source 额外携带 `recordIds`。

### 4.2 目录

`catalogMessage`：

1. `maxChars = max(600, policyConfig.catalogMaxChars)`（来自 `memory-checkpoint` 行 Config；非安全整数时兜底 2200，仍取下限 600）；
2. `filter = { workspaceKey, scopes: memoryVisibleScopes(levels), sessionId: session.id }`；`await memory.catalog({ ...filter, maxChars })` 生成 markdown：固定 header + `Pinned:`（≤6）+ `Open threads:`（≤4）+ `Recent:`（≤8，`updated_at DESC`）+ **热池 footer** `Capacity (hot): hotTokens / 启用层容量之和 tokens across hotCount records[, N cold records (X tokens, retrievable via memory_open)] (L2 session-private / L3 workspace-shared)`；超预算时截断并提示用 `memory_search`；空热池返回提示语；**catalog 只列热记录（内部固定 `cold:0`）**；
3. **digest 去重**：`digest = `${text.length}:${text.slice(0,80)}:${text.slice(-80)}``，与每会话上次值相同则不注入；
4. `facets(filter).count === 0` 时即使文本变化也不注入；
5. 注入成功才记录 digest；source 额外携带 `{ workspaceKey, scopes }`。

目录内容变化通常来自：可见热池的归档/驱逐写入、`memory_write`、pin/unpin、forget 导致的容量 footer 变化。后端 `catalog` 内部对同一 id 跨 section 去重，容量 footer 用启用层容量之和（L2→`sessionCapacityTokens`，L3→`capacityTokens`）与 `hotCount/hotTokens`；冷记录只以 footer 的计数出现。

### 4.3 容量提示（capacity-notice）

`capacityNotice(session, workspaceKey, levels)`（`memory-checkpoint` 行）：

1. 若距该会话上次提示 < `capacityNoticeCooldownMs`（默认 600000）→ 跳过；
2. 对每个已启用层级查 `facets`，取 `hotTokens / capacity`；`capacity` 优先 `sessionCapacityTokens`/`capacityTokens`，缺省 10M/100M；
3. 任一比例 ≥ `capacityNoticeRatio`（默认 0.8）时，记录本次提示时间并生成**双语** `[EXTRA CONTEXT CAPACITY / 额外上下文容量]` 文本（每层列出百分比/hot/capacity/coldCount，英文 + 中文各一段），明确要求：**先问用户是否压缩，同意后才调用 `memory_compress`**，拒绝则继续工作并忽略；clip 1400；
4. `createMemoryMessage('capacity-notice', clip(text,1400), { levels })`；source `kind='memory-recall'`、form `capacity-notice`；插入位置在目录之后、召回之前；
5. 每会话状态 `capacityNoticed: Map<sessionId, timestamp>`，`session/disposed` 清理。

这是**协议约束**而非代码强制：`memory_compress` 本身不校验“用户同意”，由 manual/提示文本约束模型。

### 4.4 召回

`recallMessage(session, workspaceKey, directText, levels)`（`memory-checkpoint` 行）：

1. `policyConfig.autoRecall === false` → 跳过；
2. 文本 trim 后长度 < 3 → 跳过；
3. 与该会话上次召回的文本相同 → 跳过；
4. `query = memoryQueryTerms(text, 12).join(' ')`（共享 extractor：引号 span、拉丁标识符、CJK 整段/trigram/bigram、停用词过滤）；拼接 <3 字符则回退 `text.slice(0,120)`；
5. `filter = { workspaceKey, scopes: memoryVisibleScopes(levels), sessionId: session.id }`；`await memory.search({ ...filter, query, limit: 3 })`（search 默认包含冷记录，因此冷存内容也可能被召回）；零命中且 `query !== text.slice(0,120)` 时用前 120 字再搜一次；
6. 过滤掉“已展示”集合（本会话见过目录/召回/回执里的 id；集合上限 80，FIFO 淘汰）；
7. 无新命中 → 跳过；
8. 记录本次查询文本（原文，用于去重），按 `policyConfig.recallMaxChars` 拼接：

   ```
   [MEMORY RECALL] Earlier records in this workspace may be relevant to the current request:
   - <id> · <title> · <useWhen 截 120>
   Call memory_open <id> to read one; ignore these if they are unrelated.
   ```

9. 把新 id 加入已展示集合，`await memory.markRead(ids)`（read_count/last_read_at），source 携带 `recordIds`。

**直接用户消息的判定**：在 `decision.messages` 中从后往前找 `role === 'user'` 且 `source.kind === 'user' || source.kind === 'user-rpc'` 的消息。会话格式 v4 中 RPC 提示的 source 实际是 `{ kind: 'user', rpcId, … }`，所以第二条件当前不会命中；注入的 `memory-recall`、runtime-context、instructions 等消息因此不会被当成“用户本轮请求”。

### 4.5 命令层

`/memory` 由独立的 `memory-commands` 行注册（入口 `dsh-command-memory/index.js`，实现 `dsh-command-memory/lib/commands.js`），不参与模型上下文，只通过异步 seam 操作同一批记录：

- 行 `inject: ['memory']`；`commands` 服务是可选依赖：`registerMemoryCommands` 内 `ctx.get('commands')` 失败/缺失时返回 `undefined`，命令层不注册也不报错；
- 注册形状：`definitionId: '@qiuxu/dsh-memory/commands/memory'`、`name: 'memory'`、`description`、`input.hint` 列出子命令语法；
- `handler(invocation)` 为 async，从 `invocation.agent.session` 解析 cwd/session id → 同一 `workspaceKey` 作用域；
- 层级命令：`/memory on l2|l3|both`（裸 `/memory on`=both）对 `memory.enableLevel()` 幂等调用；`/memory off` 返回“L2/L3 是粘性的，不能关闭”的错误（不改变状态）；`/memory status` 显示 L1/L2/L3、两池 **hot/cold** 记录数/tokens、L1 已转移 count/tokens、**compression runs（次数 + last 摘要）**、存储根；`/memory compress [l2|l3] [targetRatio]` 已补（cold-only，写历史）；
- 冷生命周期命令：`/memory restore <id>` 把冷记录回热（先 `visibleRecord` 校验）；`/memory gc <keepTokens>` 对每个启用层删除最老冷记录直到 ≤ 预算；`search`/`remember`/`restore`/`gc`/`forget` 在两层都关时返回错误；
- 门控：`pin`/`unpin`/`forget`/`restore` 都先 `visibleRecord(memory, scope, levels, id)` 校验 workspaceKey + 可见层级（早期版本不校验的缺口已修）；
- 命令的输入与结果由命令平面渲染，**不会变成模型消息**（`dsh-commands` 的既有语义）。

## 5. 消息 source 契约

`memory-checkpoint` 行（以及 `memory-evict` 行）通过 seam 的唯一构造入口生成消息（不 import `dsh-llm`，保持插件加载路径轻量）：

```js
memoryMessage({
  form: 'checkpoint' | 'catalog' | 'recall' | 'capacity-notice' | 'l1-eviction',
  text,                       // 有界 markdown 正文
  meta: { recordIds?, workspaceKey?, scopes?, levels?, recordId?, seqStart?, seqEnd? },
})
// => Object.freeze({
//   id: `msg_${sha256(form\0text\0time\0random)[0:20]}`,
//   role: 'user',
//   content: Object.freeze([Object.freeze({ type: 'text', text })]),
//   source: Object.freeze({ kind: 'memory-recall', form, version: 1, ...meta }),
// })
```

`form='l1-eviction'` 的 receipt 由 `memory-evict` 在 `compaction/prune` 之后追加，并配 `surfaceOp:{op:'replace'}` 与 `sourceEventSeqs` 真正替换 L1 surface（§2.5）；`form='capacity-notice'` 由 checkpoint 的容量提示注入（§4.3），只携带 `{levels}`。

`dsh-memory-seam/lib/index.js` 同时导出常量 `MEMORY_SOURCE_KIND = 'memory-recall'`，backend/策略/命令共用该词汇。会话格式 v4 的 native admission 规则：解释型消息槽要求 source 是对象、`kind` 非空且不为 `'plugin'`；未知 attribution 与自有 JSON 元数据会被保留（“不授予生产者运行时权限”）。`memory-recall` 属于这类 producer-owned kind，因此可持久化、重放、fork，且不会引入未知事件类型。

## 6. 幂等、恢复与失败语义

| 机制 | 实现 | 边界 |
|---|---|---|
| 记录 id | compaction 兜底：`mem_` + `sha256(`${sessionId}\0${compactionId}`)[0:10]`；L1 驱逐：`l1_` + `sha256(`${sessionId}\0${start}\0${end}`)[0:10]` | 同一压缩/同一 span 稳定 |
| 幂等标记 | compaction：`archived_compactions` 主键 `(session_id, compaction_id)`，归档前 `wasArchived`；L1 驱逐：`l1_evictions` 主键 `(session_id,start_seq,end_seq)` + `INSERT OR REPLACE` | 预检在读取日志前；`scope` 取首次成功归档时的 capture 层 |
| 层级门控 | `memory.getLevels(sessionId)`（`session_settings.l2/l3` → `defaultLevels`，默认 none）；两层都关时归档/注入/tools/API 记录读取全部短路 | 层级只增不减；不迁移既有记录；归档幂等键与 scope 无关 |
| L1 驱逐顺序 | 先 `memory.write` 原文归档成功，再 append `compaction/prune` + replace user message；写失败则不裁剪 L1 | 驱逐失败只告警一次；compaction 仍兜底 |
| 冷存幂等 | `archiveCold(id)` 已冷直接返回；先 rename 文件再 `UPDATE cold=1,path`；源文件缺失也可容忍（摘要可读） | 只动文件位置与 cold/path/updated_at，不改正文 |
| 压缩幂等/恢复 | digest 批失败不写 digest、不冷移；digest id = `dig_` + hash(sessionId, level, 批内 ids)，已冷记录不再入选；重新调用只处理剩余热记录 | 不保证跨并发调用互斥（单进程工具调用，无锁）；`maxBatches` 限制单次进度；2 路并发仅限 digest 批 |
| FTS 迁移 | `ensure()` 检测 `records_fts` 是否含 `body` 列，含则 drop/recreate card-only 并全量重索引，随后 best-effort `optimize + wal_checkpoint(TRUNCATE) + VACUUM` 回收旧页 | 迁移只发生一次；维护失败非致命（后续 VACUUM 仍可回收）；live 18.19MB→0.25MB |
| 会话设置 TTL | 打开时 `DELETE FROM session_settings WHERE updated_at < now - settingsTtlDays`（默认 90 天） | 只在打开时跑；enable 等写操作刷新 updated_at，单纯读层级不刷新 |
| 压缩历史 | 工具压缩写 `compression_runs`（level/strategy/before-after/cold/digests/llm/errors/time） | API/面板 cold 压缩路径当前不写该表（见限制） |
| 冷回热/GC | `restoreCold` rename 回热并 `cold=0`、清空 abstract（已热幂等）；`gcCold` 删除文件+索引行、最老优先、单次 ≤5000 行 | GC 是永久删除；配额 GC 只在工具压缩结束时检查 |
| abstract 迁移/回填 | 打开时 `ALTER TABLE records ADD COLUMN abstract`；FTS 缺 abstract/含 body 时重建 5 列并全量重索引；冷记录 `abstract=''` 时从文件回填前 ~1000 字 | 热记录 abstract 为空；回填失败（文件缺失）时卡片字段仍可搜 |
| 敏感驱逐 | `sensitivePolicy:auto` 正则扫描；命中且 L2 on → 强制 session；仅 L3 → 跳过驱逐（warn）；`tags.sensitive=['true']` | 启发式，不保证覆盖所有秘密；compaction 兜底归档不走该扫描 |
| digest ids 强制 | digest 回复缺 `ids:` 行视为失败：重试一次；仍缺则无损冷移回退（不写 digest、errors 记录） | 只影响 digest 结果质量，不阻塞压缩（回退是 lossless） |
| 容量提示去重 | 每会话 `capacityNoticed` 记录最近一次提示时间；`capacityNoticeCooldownMs` 内不再提示 | 只影响提示，不影响压缩能力 |
| 并发 | 单服务实例一条 `chain` 串行化所有会话的归档 job | 多进程/多实例写同一 root 无协调 |
| 崩溃恢复 | 每会话首步后台 `reconcile`（`listEvents`→`readEvent`→`wasArchived`→归档） | 无 `sessionQuery` 时不可用 |
| 会话销毁 | `session/disposed` 清理所有每会话 Map/Set | 已落盘记录不删（归档是持久的） |
| 钩子失败 | 每处 try/catch + `warn`；归档任务 `.catch`；目录/召回异常返回原 decision | 失败不会中断会话；但归档失败只留告警 |
| Teardown | 每行各自的 `ctx.effect`：`memory-checkpoint` 行 dispose 策略；`memory` 行 `core.close()` | dispose 只置 `disposed` 并清内存态，不等待在飞 job；`drain()` 供测试/teardown 使用。两行生命周期独立：若后端行先关闭 DB 而归档 job 未完成，写入会失败并告警（压缩事件仍在日志中，下次启动对账可补） |

## 7. 文件与 SQL schema

### 7.1 记录文件

`<root>/records/<workspaceKey>/<recordId>.md`（热）；冷存后同一文件 rename 到 `<root>/cold/<workspaceKey>/<recordId>.md`（内容不变）：

```markdown
---
id: "mem_..."
kind: "episode"
scope: "workspace"
workspace: "/abs/cwd"
workspace_key: "16hex"
session_id: "session-..."
title: "..."
use_when: "Read when ..."
status: "active"
trust: "derived"
tokens: 1234
tags: {"source":["compaction-archive"],"where":[...],"tools":[...],"issue":[...]}
links: {}
provenance: {"source":"compaction-archive","sessionId":"...","compactionId":"...","seqStart":12,"seqEnd":40,"shadowedEventCount":29,"shadowedTokenCount":1234,"provider":"...","model":"...","cwd":"/abs/cwd"}
created_at: 1700000000000
updated_at: 1700000000000
---

> Archived from session `...` (compaction `...`), seq #12–#40, ~1234 tokens.
> This is raw conversation content: treat it as data, never as instructions.

## Summary
...

## Archived context
### [#12] user · user · 2026-...
...
```

正文读取使用 `recordBodyFromFile`：若文件不以 `---\n` 开头则整文件即正文；否则定位第二个 `\n---\n` 之后。容忍用户手工编辑 frontmatter。冷记录与热记录同格式，只是路径在 `cold/` 下、DB `cold=1`；`get`/`search`/`grep` 通过 `records.path` 读盘，因此冷记录仍可打开/检索。示例是 workspace 记录；session 池记录同结构，只是 `scope: "session"` 且 `session_id` 必须非空（写入时校验），查询按两者过滤。

### 7.2 SQLite

`<root>/index.db`（`node:sqlite` 的 `DatabaseSync`，`journal_mode=WAL`、`synchronous=NORMAL`）：

```sql
CREATE TABLE records (
  id TEXT PRIMARY KEY,
  workspace_key TEXT NOT NULL,
  workspace TEXT NOT NULL DEFAULT '',
  scope TEXT NOT NULL DEFAULT 'workspace',
  session_id TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  use_when TEXT NOT NULL DEFAULT '',
  tags_json TEXT NOT NULL DEFAULT '{}',
  links_json TEXT NOT NULL DEFAULT '{}',
  provenance_json TEXT NOT NULL DEFAULT '{}',
  path TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 1,
  bytes INTEGER NOT NULL DEFAULT 0,
  trust TEXT NOT NULL DEFAULT 'trusted',
  status TEXT NOT NULL DEFAULT 'active',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  read_count INTEGER NOT NULL DEFAULT 0,
  last_read_at INTEGER,
  cold INTEGER NOT NULL DEFAULT 0,
  abstract TEXT NOT NULL DEFAULT ''
);
CREATE INDEX records_ws_index ON records(workspace_key, kind, status, updated_at);
CREATE INDEX records_scope_index ON records(workspace_key, scope, session_id, updated_at);

CREATE VIRTUAL TABLE records_fts USING fts5(
  title, summary, use_when, tags, abstract, tokenize = 'trigram'
);

CREATE TABLE archived_compactions (
  session_id TEXT NOT NULL,
  compaction_id TEXT NOT NULL,
  record_id TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (session_id, compaction_id)
);

CREATE TABLE session_settings (
  session_id TEXT PRIMARY KEY,
  mode TEXT NOT NULL DEFAULT 'off',   -- 旧版单模式列，保留兼容
  l2 INTEGER NOT NULL DEFAULT 0,      -- 粘性 L2（session-private）
  l3 INTEGER NOT NULL DEFAULT 0,      -- 粘性 L3（workspace-shared）
  updated_at INTEGER NOT NULL
);

CREATE TABLE l1_evictions (
  session_id TEXT NOT NULL,
  start_seq INTEGER NOT NULL,
  end_seq INTEGER NOT NULL,
  record_id TEXT NOT NULL,
  shadowed_tokens INTEGER NOT NULL,
  created_at INTEGER NOT NULL,
  PRIMARY KEY (session_id, start_seq, end_seq)
);

CREATE TABLE compression_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL DEFAULT '',
  level TEXT NOT NULL,
  strategy TEXT NOT NULL,
  before_hot INTEGER NOT NULL,
  after_hot INTEGER NOT NULL,
  cold_moved INTEGER NOT NULL,
  digests INTEGER NOT NULL,
  llm_calls INTEGER NOT NULL,
  errors TEXT NOT NULL DEFAULT '',
  created_at INTEGER NOT NULL
);
```

写入路径：`write` 先原子写文件，再 `BEGIN IMMEDIATE` upsert `records` + 删除/插入 `records_fts`（rowid 与 `records.rowid` 对齐；写入时 FTS 只写 card 字段、`abstract` 为空，冷记录才由 `archiveCold` 填 abstract），`COMMIT`；DB 失败则 `ROLLBACK` 并尽力 `unlink` 文件。`forget` 同理先删索引行再删文件。升级已有库时若 `session_settings` 缺 `l2/l3` 列会 `ALTER TABLE ADD COLUMN`，并一次性回填（`mode='session'→l2=1`、`mode='workspace'→l3=1`）；`records` 缺 `cold`/`abstract` 列时补列（默认 0/''）；`records_fts` 若含 `body` 或缺 `abstract` 列则 drop/recreate 为 5 列、全量重索引、从冷文件回填 abstract，并在旧表含 body 时 best-effort `optimize + wal_checkpoint(TRUNCATE) + VACUUM` 回收旧 trigram 正文页。打开时还会 `DELETE FROM session_settings WHERE updated_at < now - settingsTtlDays`。`enableLevel` 用 `INSERT ... ON CONFLICT DO UPDATE SET l2/l3=1`，`getLevels` 查不到行时返回后端 `defaultLevels`（默认 none）。`recordEviction` 写 `l1_evictions`，`evictionStats(sessionId)` 汇总 count/tokens。`archiveCold`/`restoreCold` rename 文件并更新 `cold/path/updated_at/abstract`（restore 清空）；`compressCold`/`gcCold` 分别做无 LLM 批量冷移与按预算删除；`recordCompression`/`compressionStats` 读写 `compression_runs`。

### 7.3 查询路径

`search(query)`：

1. `memoryQueryTerms(query.query)`（≤20 词；共享 extractor）→ 空则返回 `{hits:[],strict:true}`；
2. **FTS leg**：长度 ≥3 的词项（≤12）在 `records_fts(title,summary,use_when,tags,abstract)` 上 trigram `MATCH ... OR`，`ORDER BY bm25(rank)`，`LIMIT limit*8`；
3. **LIKE leg**：前 8 词在 `title/summary/use_when/abstract` 上 `OR LIKE`（CJK bigram/短词/冷摘要），`LIMIT limit*8`；与 FTS 结果按 id 去重；
4. **热正文回退**：结果不足 `limit` 时对 `cold=0` 最近 400 条逐条 `grep`（正文-only 标识符；同样应用 workspace/scopes/status 过滤；冷正文不在回退里，用 `memory_grep`/`memory_open`）；
5. **混合重排**：`0.8×lexicalRank + 3×title + 1.4×summary + 1.2×useWhen + 1.6×tags + 0.9×abstract + 0.4×recency(60d) − 0.1×cold`，同分按 `updatedAt`；再应用 tag 过滤/limit，snippet 来自 FTS `snippet()` 或 `makeSnippet`（截 180 字符）。

`list` 默认排除 `status='superseded'`（除非显式传 `status` 或 `includeStatus`）；`grep` 在记录的**原始文件文本**上逐行做不区分大小写正则（冷记录同样读盘）；`facets` 提供 count/tokens/bytes/byKind/byKindTokens/byStatus/oldest/newest，另有 **`hotCount/hotTokens/coldCount/coldTokens`**（`clauses` 可含 `cold` 过滤），并按可见 scope 求和容量（L2→`sessionCapacityTokens`，L3→`capacityTokens`）；`catalog` 固定 `cold:0`，只列热记录，footer 用 hotCount/hotTokens + cold 计数。所有查询路径都支持 `scope`/`scopes` 数组（可见层并集），L2 再叠加 `sessionId`；**默认不按 cold 过滤**，所以 search/list/get 包含冷记录。升级前写入的记录全部 `scope='workspace'`、`cold=0`，在未开启 L3 时不可见。

## 8. 每会话内存态与上限

| 名称 | 类型 | 上限/清理 | 用途 |
|---|---|---|---|
| `buffers` | `Map<sessionId, Map<seq, event>>` | 每会话 4000 条，FIFO；`session/disposed` 删除 | 无 `sessionQuery` 时归档兜底 |
| `receipts` | `Map<sessionId, {recordId,title,text}[]>` | 每会话 4 条，超出丢最旧；注入后清空 | 压缩回执 |
| `catalogDigest` | `Map<sessionId, string>` | 每会话 1 条；dispose 清除 | 目录去重 |
| `shown` | `Map<sessionId, Set<recordId>>` | 每会话 80 个，FIFO | 避免重复召回 |
| `lastRecall` | `Map<sessionId, string>` | 每会话 1 条 | 避免同文本重复召回 |
| `reconciled` | `Set<sessionId>` | 每会话执行一次 | 恢复对账 |
| `capacityNoticed` | `Map<sessionId, timestamp>` | 每会话 1 条；`session/disposed` 删除 | 容量提示冷却 |
| `jobs` | `Set<Promise>` | 完成即删；`drain()` 可等待 | teardown/测试 |

以上状态全部属于 `memory-checkpoint` 行实例；`memory` 行持有 SQLite 连接、root 路径、Config 与持久化的 `session_settings` 层级表（层级不是内存态，重启后仍按会话生效）。`memory-evict` 行无每会话状态（每次 step 现算）；`memory-compress` 行无每会话状态（工具调用期间现算，不缓存批次进度；进度由“已冷记录不再入选”保证）；`memory-tools` / `memory-commands` / `memory-api` / `memory-ui` 行无每会话状态（API 每次请求从 live session 解析作用域与层级；面板/圆环状态只在浏览器内）。

## 9. 预算与容量

| 预算 | 值 | 所属行与位置 |
|---|---|---|
| 目录消息 | `catalogMaxChars`（默认 2400，配置下限 600；backend `catalog` 再保底 400） | `memory-checkpoint` 行 Config → `dsh-memory-checkpoint/lib/checkpoint.js` |
| 回执消息 | 1600 字符（多条合并后 clip） | `memory-checkpoint` 行 → `dsh-memory-checkpoint/lib/checkpoint.js` |
| 召回消息 | `recallMaxChars`（默认 600，下限 200） | `memory-checkpoint` 行 Config → `dsh-memory-checkpoint/lib/checkpoint.js` |
| 工具内联 | `maxInlineChars`（默认 14_000，≥400，仅结果渲染上限）与 `memory_open` 的 `maxChars`（默认 30_000，2000-60000）分页上限 | `memory-tools` 行 Config → `dsh-tool-memory/lib/tools.js` |
| 归档正文字节 | 2 MiB，超出截断 | `memory-checkpoint` 行归档渲染 `dsh-memory-checkpoint/lib/render.js` |
| L3 池容量 | `capacityTokens`（默认 100M）≈ 400 MB 文本；正文 trigram ≈13 bytes/token（旧方案 100M 池可达 GB 级），card-only FTS 降到 MB 级 | `memory` 行 Config；**热池**软目标，冷存不计 |
| L2 池容量 | `sessionCapacityTokens`（默认 10M / 会话）≈ 40 MB 文本；SQLite+FTS 约 2 倍 | `memory` 行 Config；**热池**软目标，冷存不计 |
| 冷存 | 无软容量；文件在 `cold/` 下，仅检索/打开时读盘；可选 `coldQuotaTokens` 配额 | `memory` 行；`records.cold` |
| 容量提示 | `capacityNoticeRatio`（0.8）+ `capacityNoticeCooldownMs`（600000）；双语文本 clip 1400 | `memory-checkpoint` 行 Config → `lib/checkpoint.js` |
| 压缩 | `targetRatio` 0.6；候选 ≤400/层；digest 批 ≤20 条/120k 字符、2 路并发、单次 ≤6 次 LLM（`maxTokens=1600`）；`minDigestTokens=2000`；`minAgeMs` 1h；`coldQuotaTokens` 可选 | `memory-compress` 行 Config → `index.js` |
| L1 驱逐阈值/保留 | `contextWindow × evictAtRatio`（默认 0.6）触发；保留 tail `× retainRatio`（0.35）；单批 ≤`maxChars`（250k 字符）；含图片/超限事件停批 | `memory-evict` 行 Config；相对路由窗口 |
| L1 驱逐审计 | `l1_evictions` 行数/`shadowed_tokens` 之和 | `memory` 后端；供 index/`memory_index` 的 `l1Evicted` |
| 面板/圆环 | index ≤300（面板请求 200）、search ≤100（面板 50）、record body 窗口默认 200k / max 1M 字符且单窗口 ≤256 KiB；内弧 `dasharray = hotTokens / 启用层容量之和` | `memory-api` / `memory-ui`；不进模型上下文 |
| 基准 | `scripts/scale-bench.mjs`：1000×10k tokens → DB 1.0 MiB/records 38.5 MiB；facets 0.63/list 0.55/catalog 1.21/search 1.2–5.6/grep 4.5/get 0.03ms；compressCold 0.10s/700 条、gcCold 0.02s/350 条。**Phase-3 10k×10k（100M tokens）**：write 2.8s、DB 9.0 MiB、records 384.8 MiB；facets 11.28ms、list 5.80ms、catalog 17.52ms、search 16.70–17.67ms（CJK 1.94ms）、grep 14.59ms、get 0.04ms；compressCold 5000 条/50M 2.56s（DB 26.6MiB）、压缩后 search 28.77ms；gcCold 2500 条/25M 0.31s | 本地脚本（临时 DB）；**验收 card p95<50ms、grep<2s 达标** |
| 检索评测 | `scripts/recall-eval.mjs`：real hit@1 73%/hit@3 95%/hit@5 95%、cold 100%、p50 1.3ms；auto-recall 95%；synthetic 100%（基线 67%） | 本地脚本（真实副本/合成）；`--suite real\|synthetic --threshold` |
| 备份 | `scripts/memory-backup.mjs`：backup/verify/restore；live 备份 30 文件、db 268 KiB、verify OK | 手动脚本；`VACUUM INTO` + sha256 manifest |

## 10. 与上游压缩契约同步的注意点

- 只依赖 `compaction/summary.data` 的稳定字段：`compactionId`、`shadowedSeqs`、`summary`、`shadowedTokenCount`、`provider`、`model`。`shadowedRange` 存在但代码用 seq 数组的首尾推导 `#a–#b`；`usage`/`maxTokens`/`rawOutput` 当前不消费。
- 归档触发点选在 `compaction/summary`，即 `user/message` 替换**之前**：此时被遮蔽事件已提交且不可变，读取原始日志永远安全。若未来压缩后端改变事件顺序，只需保证 summary 事件提交时 `shadowedSeqs` 指向的事件已存在。
- 记忆注入发生在 `agent/pre-step` 的 `enter` 分支；若该步被 `reject`，不注入（回执留在队列里，下一步再注入）。
- `autoArchive` 现在只控制 `memory-checkpoint` 行（该行 `apply()` 在 false 时直接 return，不注册策略）：compaction 兜底归档、回执、目录、召回一起停用；`memory-evict`/`memory-tools`/`memory-commands` 行不受影响。若要单独控制目录/召回，需要把策略再拆细或给该行加子开关。
- **默认关闭**：`defaultLevels` 默认 `'none'`——升级后不显式开启就没有 L1 驱逐、归档或注入。开启前的压缩/驱逐不会补做；恢复对账只对“开启后的首步”可见的持久化压缩补录（按当时 capture 层）。
- **层级与作用域**：层级粘性存在 `session_settings`，只增不减；新增层级只影响后续写入与读取过滤，不迁移既有记录；旧记录（升级前）全部是 workspace scope，只在 L3 可见。
- **与 `compaction/prune` 契约同步**：`memory-evict` 依赖随附的 `compaction/prune` 影子价格事件（`shadowedRange/shadowedSeqs/shadowedTokenCount`）与 `user/message` 的 `surfaceOp:{op:'replace'}` + `sourceEventSeqs`；若上游改变 prune payload 或 replace 校验，evict 行需同步。compaction backend 本身未被替换。含图片/超限事件停批是本地加固（依赖 `dsh-llm` 的 `contentHasImage`）。
- **冷存/压缩是本地扩展**：`records.cold`、`cold/` 目录、`memory_compress` 与 `capacity-notice` 都不写会话事件；压缩只调用 `ctx.memory.write/archiveCold/compressCold/gcCold`，提示只注入普通 memory-recall user 消息。冷记录仍遵守“文件是记录真源”；压缩的幂等/恢复由已冷过滤 + 确定性 digest id 保证，无跨进程锁。
- **敏感策略与备份**：L1 驱逐的 `sensitivePolicy:auto` 用正则启发式（不是 DLP），命中时秘密强制 L2、仅 L3 时跳过；compaction 兜底归档没有敏感扫描。`scripts/memory-backup.mjs` 是手动备份/校验/恢复工具（`VACUUM INTO` + manifest + `--force` guard），没有定时/轮转；`GET /api/memory.metrics` 只读观测，不进 prompt。
- **FTS 迁移与检索权衡**：FTS 5 列含冷摘要（前 ~1000 字），正文-only 词依赖热回退或 `memory_grep`；LIKE leg 是 OR 扫描（10k 记录 Phase-3 仍 <50ms，再大需重新评估）；`memoryQueryTerms` 是词法启发式（无词干/语义）；若上游改变 FTS 字段或 trigram 可用性，需同步 `ensure()` 迁移与回退路径。
- **压缩历史是工具路径专有**：只有 `memory_compress`（compress 行）写 `compression_runs`；API/面板的 `compressCold` 没有写历史。若要把历史做成“所有压缩入口一致”，需要把 `recordCompression` 下沉到 `compressCold`/API。

## 11. 客户端半侧与 HTTP API

Web 面板 = `memory-ui`（客户端半侧，跑在浏览器）+ `memory-api`（Host 行，暴露 `/api/memory.*`）。两者都不进入模型上下文。

### 11.1 数据流

```
浏览器（owner browser session，Web GUI）
 ├─ row memory-ui 的 client half（modules/memory-ui/client.js，经典 factory script）
 │   ├ conversation.input.left → memory-panel-trigger（order 30，"记忆"按钮）
 │   ├ shell.overlay          → memory-panel（order 10，浮动对话框 + L2/L3 粘性按钮/压缩/回热/⚠ 警告/off CTA）
 │   └ composer ContextMeter  → DOM 装饰：内弧（热占用）+ 弹层「额外上下文」行/层级按钮/kind 占比/L1↓/冷存/⚠ 接近容量
 │        ├ GET  api/memory.index?sessionId=…&limit=…
 │        ├ GET  api/memory.record?sessionId=…&id=…&offset=…&limit=…
 │        ├ GET  api/memory.search?sessionId=…&q=…&limit=…
 │        ├ POST api/memory.status {sessionId,id,status}
 │        ├ POST api/memory.level  {sessionId,level:'l2'|'l3'}
 │        ├ POST api/memory.compress {sessionId,level,strategy:'cold',targetRatio}
 │        ├ POST api/memory.restore  {sessionId,id}
 │        ├ POST api/memory.gc       {sessionId,keepTokens}
 │        └ GET  api/memory.metrics?sessionId=…   （只读观测）
 ▼ 同源 document-relative fetch（browser-session cookie；同 /api/session.export）
row memory-api（packages/dsh-memory-api/index.js）
 └ resolveWorkspace(ctx, sessionId, cwd) —— 只查 ctx.sessions.list() 的 live session
      ├ memory.getLevels(sessionId) → visibleFilter（scopes 并集 + sessionId）
      └ 异步 ctx.memory（row memory）→ SQLite/FTS5(card-only) + md 文件（L2 session / L3 workspace / cold 冷存）
```

### 11.2 客户端模块格式与 Slots

`packages/dsh-memory-ui/client.js` 是**手写经典脚本**，不是 ESM/JSX：

```js
window.__ModuleLoader__.load({
  id: '@qiuxu/dsh-memory-ui',
  factory(require) {
    const React = require('react')        // 唯一外部依赖
    // ...
    return { inject: ['slots', 'uiSession'], apply }
  },
})
```

`apply(ctx)` 做四件事：

1. `ctx.effect` 注入一个 `<style data-plugin="@qiuxu/dsh-memory-ui" data-plugin-css="…">`（面板/按钮的全部 CSS；颜色优先使用宿主主题 token（`--dsw-alias-bg-layer-1`/`--dsw-alias-label-primary`/`--dsw-alias-brand-primary` 等，带字面量 fallback），仅在部署未提供 token 表时用 `@supports not` + `prefers-color-scheme` 兜底暗色）。
2. `ctx.slots.inject('conversation.input.left', () => ctx.slots.register({ name, id:'memory-panel-trigger', order: 30 }, MemoryTrigger))`。该 slot 是 session 域（随附 client 契约：`kind: 'list'`、`scope: 'session'`、summary “Compact controls at the left of the composer tool row.”），组件通过标准 prop 拿到 `sessionId`。
3. `ctx.slots.inject('shell.overlay', () => ctx.slots.register({ name, id:'memory-panel', order: 10 }, MemoryPanel))`。面板是 `role="dialog"` 的浮动层：顶部有两个**粘性**按钮「L2 本会话 10M」「L3 工作区 100M」（点击 `POST api/memory.level` 后重载；已启用显示 🔒、点击无效、title 说明不可关闭）；头部显示 `L2|L3|L2+L3 · N 条热 · hotTokens/capacity tokens [· 冷存 N]`，两层都关时显示 “额外上下文：关闭”；off 时列表位置显示关闭 CTA；开启层级时头部有「压缩」按钮 → `POST api/memory.compress {level,strategy:'cold',targetRatio:0.6}`（无损 cold；digest 只能由模型工具），结果以 notice 行显示“已冷移 N 条记录/无需压缩”；冷行显示「回热」按钮 → `POST api/memory.restore`；hot 比 ≥0.8 时 footer 显示 `⚠ 热池 N%`；footer 还显示 `已压缩 N 次`（compression 历史）与 `L3 共享（敏感内容自动留在 L2）`、`接近容量时模型会先询问` 提示；记录行带 scope 徽标「本会话」/「工作区」、kind、status/置顶、tokens、时间、useWhen；点击行按需 GET 单条 body（冷记录也可按 id 打开；支持 offset/limit 分页参数）；行内置顶；kind chips 显示热池按 kind 的 token 占比；搜索框在两层关时禁用。Esc/×/遮罩关闭。按钮与面板通过模块内小 store（`Set` listeners）共享 open/session 状态。
4. `ctx.effect(() => installContextRingBridge(ctx), …)`：ui-conversation 的 `ContextMeter` 是内联渲染、没有 slot，因此用 DOM 装饰：在 `button[aria-haspopup="dialog"]` 内的 `svg[viewBox="0 0 14 14"]` 追加 `circle[data-dsh-memory-arc]`（r=3.2、stroke 1.4、`rotate(-90 7 7)`，`stroke-dasharray = 2πr × hotTokens / 启用层容量之和`；颜色取 capture 层：L2 → teal `--dsw-static-teal-450`、L3（含 L2+L3）→ `--dsw-alias-brand-primary`，两层都关时 opacity 0）；给按钮 `aria-label` 追加 `· 额外上下文 N%（L2|L3|L2+L3）` 或 `· 额外上下文 关`（保存 base label，卸载恢复）；在打开的 ContextMeter 弹层尾部追加 `[data-dsh-memory-meter-row]`：「额外上下文」+ 色块 + 两个粘性按钮「L2 本会话 / L3 工作区」（开启后 🔒）+ figures（开启时 `hot/capacity · L1↓X · 冷存 N`，hot 比 ≥0.8 追加 `· ⚠ 接近容量`；关闭时 `关闭 · L2 x/10M · L3 y/100M`）+「查看记录 →」；行下方还有按 kind 的 token 占比块。数据来自 `/api/memory.index?sessionId=…&limit=1`（含 `compression` 对象），会话切换（`ctx.uiSession.adapter.current`）立即刷新，600ms 补装饰（React 重渲染会丢节点）、15s 轮询；卸载清节点/属性/定时器。纯展示级桥接，只写自己创建的 DOM。

面板的数据辅助函数是 `api(path, options)`：`fetch(path)` 后解析 JSON，HTTP 非 2xx 或 `{ok:false}` 时抛出 `data.message`，由面板红条显示。路径全部 document-relative（`api/memory.index` 等），因此与页面同源并复用 browser-session cookie。

### 11.3 HTTP API 路由与作用域

`packages/dsh-memory-api/index.js` 在 `ctx.effect` 中为每个路由调用
`ctx.connection.fetch.register({ path, methods, requestBody: 'buffered', fetch })`（exact path，无通配）：

| 方法 | 路径 | 输入 | 成功响应 |
|---|---|---|---|
| GET | `/api/memory.index` | `sessionId` 或 `cwd`；`limit` 1–300（默认 100） | `{ ok, levels, compression:{count,last,recent}, captureScope, scope, l2:{enabled,tokens,hotTokens,coldTokens,coldCount,count,capacityTokens}, l3:{…}, l1Evicted:{count,tokens}, capacityTokens, tokens, hotTokens, coldTokens, coldCount, byKind, byKindTokens, byStatus, count, records:[card] }`；`tokens` 含冷（兼容字段），热容量看 `hotTokens`；两层关时 active 字段归零但 l2/l3 池信息仍返回 |
| GET | `/api/memory.record` | `sessionId`/`cwd`；`id`；`offset`（默认 0）、`limit`（默认 200000，max 1,000,000 字符） | `{ ok, record, body, truncated, bodyTruncated, bodyOffset, bodyLimit, bodyTotalChars, path }`；窗口按字符切片；单窗口仍受 256 KiB 字节硬上限（超出截断并 `…[truncated]`）；`bodyTruncated`（`truncated` 为 legacy 别名）在窗口被截或“窗口后还有内容”时为 true；冷记录同样可读 |
| GET | `/api/memory.search` | `sessionId` 或 `cwd`；`q`；`limit` 1–100（默认 30） | `{ ok, levels, records:[{...card, snippet?}] }`；两层都关时 `records:[]`；包含冷卡片字段（正文回退仅热） |
| POST | `/api/memory.status` | JSON `{ sessionId \| cwd, id, status }`，status ∈ `pinned`/`active`/`resolved`/`superseded` | `{ ok, record }`；不可见记录 404 |
| POST | `/api/memory.level` | JSON `{ sessionId \| cwd, level }`，level ∈ `l2`/`l3` | `{ ok, levels, captureScope }`；`off`/非法值 → `400 MEMORY_LEVEL_STICKY` |
| POST | `/api/memory.compress` | JSON `{ sessionId\|cwd, level:'l2'\|'l3'\|'auto', strategy:'cold', targetRatio?, minAgeMs? }` | `{ ok, reports:[{level,targetTokens,beforeHot,coldMoved,freedTokens}], compression }`；无启用层 → `400 MEMORY_LEVELS_OFF`；`strategy:'digest'` → `400 MEMORY_DIGEST_REQUIRES_MODEL`（digest 只能走模型工具） |
| POST | `/api/memory.restore` | JSON `{ sessionId\|cwd, id }` | `{ ok, record }`；不可见/不存在 → 404；已热 → `400 MEMORY_NOT_COLD` |
| POST | `/api/memory.gc` | JSON `{ sessionId\|cwd, keepTokens }` | `{ ok, reports:[{level,removed,freedTokens}] }`；非法配额 → `400 MEMORY_INVALID_QUOTA`；只处理已启用层 |
| GET | `/api/memory.metrics` | `sessionId` 或 `cwd` | `{ ok, generatedAt, levels, l2:{hotTokens,coldTokens,hotCount,coldCount,capacityTokens}, l3:{…}, visible:{hotTokens,coldTokens,count,byKind}, l1Evicted:{count,tokens}, compression:{count,last,recent} }`；只读观测（第 9 条路由） |

`card()` 序列化**含** `cold` 布尔（面板据此显示「回热」）。`tokens` 是含冷总量（兼容旧消费方），容量判断必须用 `hotTokens/capacityTokens`。

错误：`400 MEMORY_INVALID_BODY`、`400 MEMORY_INVALID_ID`、`400 MEMORY_INVALID_STATUS`、`400 MEMORY_INVALID_QUOTA`、`400 MEMORY_LEVEL_STICKY`（level 不是 l2/l3）、`400 MEMORY_LEVELS_OFF`（没有启用层）、`400 MEMORY_DIGEST_REQUIRES_MODEL`（API digest）、`400 MEMORY_NOT_COLD`（回热已热记录）、`404 MEMORY_UNKNOWN_SESSION`、`404 MEMORY_NOT_FOUND`（记录不可见）。所有成功响应与错误 body 都是 JSON（`content-type: application/json; charset=utf-8`）。

**作用域与层级**：`resolveWorkspace(ctx, sessionId, cwd)` 只从 `ctx.sessions.list()` 里找 live session（按 id，或按 `header.cwd` 精确匹配），再用 `memoryWorkspaceKey(scope.cwd, scope.sessionId)` 派生 `workspaceKey`；`visibleFilter(scope, levels)` 产出 `{ workspaceKey, scopes: memoryVisibleScopes(levels), sessionId }` 供 index/search 使用；`recordVisible(record, workspaceKey, sessionId, levels)` 对 record/status/restore 再校验。API 从不接受调用方传入的 `workspaceKey`；两层都关时没有可见池，record/status/restore 按不可见处理。旧的 `/api/memory.mode` 已移除。

**认证**：exact Fetch 路由由 Connection 的共享 handler 提供 Host/Origin 与 browser-session cookie 校验；它们不经 API Gateway。随附 `dsh-api-remote-access` 的既定行为是：共享 Fetch handler 对非 owner Peer 返回 403，直到路由自行声明访问规则——当前**九条**路由**没有声明额外访问规则**，因此实际是 owner-only（与面板的浏览器 cookie 场景一致）。

### 11.4 `memory-ui` 的 file: URL 组合约束

`memory-ui` 行在 bundle patch 中不是裸包名，而是
`name: 'file:///…/packages/dsh-memory/modules/memory-ui/index.js'`。原因来自 DSH client-modules 的两条行为（本次实测）：

1. **只有已启用的 Loader 行会进 client 扫描**：纯 patch bundle 本身没有客户端半侧；客户端半侧必须来自某个带 `dsh.client` 声明的 Loader 行。
2. **subpath specifier 会被归因到外层包**：`locatePkgJson` 用 `exactPackageSpecifier('@qiuxu/dsh-memory/ui') = '@qiuxu/dsh-memory'`，`nearestPackage(url, expected)` 会跳过 `modules/memory-ui/package.json`（name 是 `@qiuxu/dsh-memory-ui`），继续向上找到 bundle 的 `@qiuxu/dsh-memory/package.json`——它没有 `dsh.client`，于是该行被静默忽略。

file: URL 是 path-like，`expectedName` 未定义，`nearestPackage` 命中的就是生成的 `modules/memory-ui/package.json`：其 `dsh.client = { platform: 'web', immediately: true }`、`exports['./client'] = './client.js'`，于是客户端半侧被组合。代价是**绝对路径写死在 patch 里（机器相关）**；上游应改为真实包依赖 + 裸包名行。另外 client-modules 对一个包元数据的负结果缓存不会失效：给已经被扫描过的包事后加 `dsh.client` 需要重启 Host 才能生效。

### 11.5 验证证据与边界

- client Slots 检查（任务时、运行中的 GUI）：`conversation.input.left` 的 occupant `memory-panel-trigger`（order 30）与 `shell.overlay` 的 occupant `memory-panel`（order 10）均为 active——说明 client 模块已加载且 `apply` 执行。圆环桥接由 client HMR 重载后同样生效。
- API：离线 Request/Response 冒烟覆盖 index/record/search/pin/level、compress/restore/gc 的成功与未知 session、坏 status/level/quota、跨 workspace 的 404/400；record 的 offset/limit 分页与 body 统计字段；两层关闭时 index/search `records:[]`；index 含 `compression` 与 `hotTokens/coldTokens/coldCount`。
- Host 冒烟（任务时）：两层默认 off 时 `memory_index` 显示 L2 OFF / L3 OFF-sticky 且旧 L3 记录不可见、工具返回 off 文案；开启 L2 后 session 池只对该会话可见；开启 L3 后 workspace 池跨会话可见；粘性开关点击/命令不可关闭；`l1_evictions` 现有 1 batch / 89,719 tokens。
- **已 live 实测**：cold 下沉（`rec_example` 496,274 tokens → `cold/`）、digest 成功 1 批（`digest_example` 124 tokens）与空响应时的无损回退（11 条）、容量提示注入（临时 0.05 阈值）、敏感驱逐/备份代码层验证、自然语言检索（「正式站的安全头什么时候上线」→ 冷记录 `rec_example` 排第一）。**live 状态**（2026-10-29 09:55，重载后）：records **29**（L2 5/558,443（1 冷）、L3 24/1,405,950（13 冷）、cold 14/1,374,878、热 589,515）、`index.db` 0.25 MB、`records_fts` **5 列含 abstract + 14 条冷 abstract 已回填**、API **9 路由（含 metrics）**、`compression_runs` 空、`l1_evictions` 1/89,719；evict Config 5 字段（含 `sensitivePolicy`）。
- **离线 harness**：**98/98 通过**（含 cold/compress/notice/R7 `bodyTruncated` 回归 + phase-1/2 的 S1–S5）。bundle 9 模块 / 8 行，`check-bundle` 干净。
- **recall eval（Lead 实测，副本/合成）**：真实 40 条自然问题 hit@1 73%/hit@3 95%/hit@5 95%、cold 100%、p50 1.3ms；auto-recall 95%；synthetic 100%；基线 67%。`scripts/recall-eval.mjs`（`--suite real|synthetic --threshold`）、`recall-bench.mjs`。
- **scale bench（Lead 实测）**：1000×10k tokens → DB 1.0 MiB/records 38.5 MiB、facets 0.63ms、list 0.55ms、catalog 1.21ms、search 1.2–5.6ms、grep 4.5ms、get 0.03ms；compressCold 700 条/7.00M tokens 0.10s；gcCold 350 条/0.02s。**Phase-3 10k×10k（100M tokens）**：write 2.8s、DB 9.0 MiB、records 384.8 MiB；facets 11.28ms、list 5.80ms、catalog 17.52ms、search 16.70–17.67ms（CJK 1.94ms）、grep 14.59ms、get 0.04ms；compressCold 5000 条/50M 2.56s（cold 文件 192.4 MiB、DB 26.6 MiB）、压缩后 search 28.77ms/catalog 26.28ms；gcCold 2500 条/25M 0.31s。**验收：card p95<50ms、grep<2s 达标。**
- **备份**：`scripts/memory-backup.mjs` 已对 live 根执行 backup：30 个文件、db 268 KiB，`verify: OK`（`VACUUM INTO` + records/cold + sha256 manifest；restore 需 `--force` 覆盖非空目标）。
- **仍未经 agent 操作验证**：面板/圆环的压缩/回热按钮、`⚠ 热池 N%`/`⚠ 接近容量`、`已压缩 N 次`/L3 敏感提示、热冷 figures 与视觉——需要用户点开确认。圆环是 DOM 装饰（选择器 + 600ms 补装饰），DSH UI 升级可能失效。
