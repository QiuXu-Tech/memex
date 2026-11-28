# P1 原生运行入口与只读预检

`scripts/paper1/native_driver.py` 提供统一的开发执行入口。默认只读预检；显式 `--run` 才会尝试一次 task×replicate 的原生准备和 A/B/C/D 四个独立准入方法单元。它复用 [PAIRED_RUNTIME.md](PAIRED_RUNTIME.md) 的同一个 backend 与证据 helper 生命周期，不创建授权、不恢复已用额度，也不提供科学评分。

**当前原 canonical ledger 的 2 次 native 额度已经消耗，默认预检因此必须报告 `dispatch_ready=false`。** CNY 100 原上限、历史台账、16 个开发单元和公共输入均保持原身份。成功执行预检程序不表示允许发送模型请求或研究就绪。

本轮已实际运行默认本地预检：[输出与字节核对](artifacts/remaining-completion-01/native-driver/README.md)记录原台账 7 个事件、2 次 native、1 次诊断均保留，当前命令 0 次模型请求、0 次账本写入。未提供本地 settings 的结果不代表先前 Mac 执行设备的服务配置状态。

## 1. 默认入口：零调用、零写入

从仓库根执行：

```bash
python -B scripts/paper1/native_driver.py
```

该命令不启动子进程、不调用模型/网络、不运行来源测试、不执行 OS 隔离探针、不创建输出/后端目录，也不预留或写入账本。它读取并核对：

- 原授权、唯一 canonical ledger 的链与 HEAD、已用额度及未结算现金。
- 原 source plan、两份 public package 和仅改变本地路径的 relocation receipt；不改原绝对路径记录，不冻结新研究。
- 新共同 DeepSeek reader profile 和原 shared-budget 摘要。
- 可选显式 settings 中的设备文件、tokenizer 摘要及运行库、两份 Python 依赖元数据与 sandbox 配置。
- `VECTORIZE_API_KEY`、`RERANK_API_KEY` **变量名是否存在**；不取值、不显示值，空值也只算“名称存在”。真实非空/格式检查、服务鉴权和账单核对不在预检中完成。
- 显式 DeepSeek 私有文件的存在、所有者、0600 权限、链接数与大小；不读取其内容。已保存的设备凭据可继续使用，不需要重新创建或粘贴。

`WORKFLOW.inspect` 只读依赖 pin 和解释器文件，不执行 Python 版本命令。Codex/Node 也只检查可执行文件存在；版本、实际 OS 隔离和 transport 仍须在显式运行内验证。Raw-RAG 预检核对固定文件字节与当前 Python 依赖，未启动 Git、SDK 或 HTTP。参考 tokenizer 有缺失/摘要错误时直接保留阻断，不用字节估算、别的 tokenizer 或联网回退。

预检退出 0 表示检查报告已生成；请读取 `status`、`blockers` 与 `dispatch_ready`，不能把退出 0 当成实验成功。即使将来 `dispatch_ready=true`，其含义也仅为本地前提允许一次显式运行尝试；原控制器仍会在 scope 和每次实际 provider request 前重新准入。

## 2. 显式本地配置

```bash
python -B scripts/paper1/native_driver.py \
  --settings /absolute/private/runtime-settings.json \
  --scope-specs /absolute/private/checked-scope-specs.json \
  --state-root /absolute/private/new-backend-state \
  --output /absolute/private/new-paired-block \
  --task w-101 --replicate 1 --order A,B,C,D
```

所有路径均须由调用方明确给出。后端 state 和 output 必须为不同的全新目录，不得互相包含或覆盖公共输入、账本、配置及依赖目录。设置文件采用严格 JSON；重复或额外字段会被拒绝。下面仅展示字段形状，`/absolute/...` 是待替换路径，不是已存在的设备配置：

```json
{
  "codex": "/absolute/codex-0.153.0",
  "node": "/absolute/node",
  "tokenizer_path": "/absolute/deepseek-v4/tokenizer.json",
  "credential_file": "/absolute/private/deepseek_api_key",
  "rawrag_upstream": "/absolute/RAW-RAG",
  "tasks": {
    "w-101": {
      "python": "/absolute/flask-venv/bin/python",
      "sandbox": {
        "kind": "sandbox-exec",
        "executable": "/usr/bin/sandbox-exec",
        "python": "/absolute/pinned-python-runtime/bin/python3.10",
        "dependencies": "/absolute/flask-venv/lib/python3.10/site-packages",
        "runtime_roots": ["/absolute/pinned-python-runtime"]
      }
    },
    "w-102": {
      "python": "/absolute/requests-venv/bin/python",
      "sandbox": {
        "kind": "sandbox-exec",
        "executable": "/usr/bin/sandbox-exec",
        "python": "/absolute/pinned-python-runtime/bin/python3.10",
        "dependencies": "/absolute/requests-venv/lib/python3.10/site-packages",
        "runtime_roots": ["/absolute/pinned-python-runtime"]
      }
    }
  }
}
```

实际 sandbox 枚举为 `sandbox-exec`（macOS）或 `bwrap`（Linux），不是 `macos-seatbelt`。`runtime_roots` 需含实际解析后的 Python 运行目录，1–12 项；不可使用 `/`、用户主目录等宽泛挂载来绕过隔离。sandbox 的 Python 目标和 dependencies 必须匹配该任务的原 venv。预检不把配置有效解释为隔离探针已通过；backend 每个实际 runner 实例仍执行自己的探针。

可选 `--profile` 只接受现有 reader 合同允许的配置；不扩 token/HTTP 上限。预检输出 `required_scope_bindings` 中的 5 个精确 scope ID、kind、unit、public path 和 provider/config 摘要，供准备本地 `scope-specs`。不自动填写价格或生成 `checked` 证据。

每个 scope 的字段严格为：

| 字段 | 要求 |
|---|---|
| `kind`, `unit`, `public_path` | 与所选 task×replicate 的 native 或方法绑定完全一致。 |
| `max_http_dispatches` | 明确有限上界；native 至少覆盖 prelude/extraction/compaction，B 至少覆盖 embedding/rerank/reader。这些最低组件数不是充分运行预算或成本估计。 |
| `upper_bound_cny` | 全 scope 的现金上界，须满足下述已选择计量模式的完整上界。 |
| `billing_basis` | `kind=priced_upper_bound`，附原账本支持的 `{ref, sha256}` 证据。 |
| `providers` | 每项有 provider/model/endpoint/config 摘要、`checked_upper_bound_cny` 与 `checked_upper_bound_evidence:{ref,sha256}`；DeepSeek 每请求上界至少 CNY 3.00。固定 Responses 模式可另带严格的 `scope_usage_envelope`。 |

价格文件摘要只能认证文件字节，不能证明价格、币种和计量范围真实充分。调用方必须提供已核查依据；本工具不制造证据，不把未结算 token 估价释放为可用预算。除每 scope 的 canonical dry check 外，还检查该 block 全部 5 个 scope 的上界之和能否装入当前剩余容量。当前有两种明确区分的模式：

1. **原逐请求上界。** 不提供 `scope_usage_envelope` 时，scope 上界至少为 `max_http_dispatches × max(provider 每请求上界)`。若 5 个 scope 都声明 8 次、每请求 CNY 3，则最低 CNY 120，原预算下仍会被阻断。
2. **固定 DeepSeek 串行累计上界。** 仅当前完整 reader profile 摘要、`deepseek-flash` 和固定 Responses endpoint 可用。provider 的 `checked_upper_bound_cny` 必须恰为 `3.00`；可选字段严格如下，其中 relay 摘要必须来自当前实际源码：

```json
{
  "kind": "deepseek-native-serial-envelope-v1",
  "relay_source_sha256": "<actual deepseek_native_relay.py SHA-256>",
  "max_input_tokens": 65536,
  "max_output_tokens": 8192,
  "max_http_dispatches": 8,
  "scope_upper_bound_cny": "3.20"
}
```

第二种模式要求原控制器登记精确 relay/profile/私有审计目录，每次请求至多一条在途；只有持久化且绑定实际用量的 completion 握手完成后才允许下一条。已观察累计用量受 65,536 input / 8,192 output 上限约束；未知、超额、迟到或未完成握手使该 scope 持续阻断。按当前锁定的高峰参考价 input CNY 2/M、output CNY 8/M，已观察前缀上界为 CNY 0.196608，再覆盖最后一条可能未知或越限请求的 CNY 3.00，向上取分为 **CNY 3.20**。这是一份仍占用账本的保守 scope 预留证明，不是已支付金额或实际账单核销；价格来源与期限限制见 [DEEPSEEK.md](DEEPSEEK.md)。

B 的 embedding/rerank 没有套用 DeepSeek 串行证明；在该混合模式下，B scope 至少另加 `16 × max(非 DeepSeek 每请求 checked 上界)`，保留原 16 次总检索调用限制。真实非 DeepSeek 价格依据仍须提供。声明更高 DeepSeek 单请求上界时不能继续用固定 3.20 的 v1，须保留原逐请求模式或另行实现有效证明。driver 原样透传模式给 canonical controller，不自行重定价、自动降低请求上限或扩大原额度。

## 3. 明确运行及结果边界

只有在实际本地配置、价格依据、原额度等条件满足后，对上面的同一命令添加 `--run` 才会进入 `CanonicalPairedController(run=True)` 和 `NativeBackend`。当前耗尽的 native 额度仍会阻断，不能通过新目录、服务切换、导入旧摘要或重启进程取得第三次许可。

运行调用一次 `run_paired_block(..., execution_mode='live')`：一个 native 准备 scope，加四个独立 method scope，每个 A/B/C/D 只出现一次。backend、priming 证据 helper 及同一 archive epoch 保持存活到四臂结束，再统一关闭。没有 daemon、自动重试或恢复已尝试单元的入口。拒绝准入或未完成准备不能发布有效 checkpoint；任何不完整结果均保留为不完整。

`component_execution_completed` 只表示这些工程操作返回完成状态；`quality_scored=false`、`scientific_ready=false` 始终保留。provider/模型次数从已留存的准入、发送及计量制品核对；运行后的汇总次数未独立聚合时为 null，不把它们填成 0。错误、超时和未知费用仍受原 first-attempt 与费用合同约束。

**本 CLI 不是 `experiment.py` 的单个 unit runner。** 不能把它直接放进每个方法单元的 `--public/--arm/--run-id` ABI，否则会重复创建父状态或四臂。新增 [PairedLauncher](PAIRED_DISPATCH.md) 已实现该连接：在同一长寿命 controller/backend 内按冻结 unit 调用 `run_unit` 一次，并保留外层 dispatch 的首次尝试、usage、seal 与 join。重启后从文件导入一个 epoch，不能声称继承了原来的内存缓存。本入口仍只提供一次完整开发 block，真实全臂验证尚未完成。

测试使用真实只读状态或明确的本地 fixture；没有付费请求、来源执行或人工评审。定向命令为：

```bash
PYTHONPATH=test:scripts/paper1 python -B -m unittest test_paper1_native_driver -v
```
