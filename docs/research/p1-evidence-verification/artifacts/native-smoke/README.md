# 原生宿主开发验证记录

这是 **一个受控合成开发工作流**，用于验证真实原生压缩、工具输出采集、fork 元数据边界及继续执行能力。不是独立真实任务 pilot，也不是 proposed method 与 Raw-RAG 的对照。它没有在线运行 P1 的 claim extractor 或 verifier。

宿主：macOS，Codex CLI 0.153.0，所请求和解析返回的模型均为 `gpt-5.6-sol`。运行的 UTC 时间保留在事件记录中，对应用户时区日期 **2026-11-28**。

## 实际发生的流程

1. 原始 `sum.mjs` 实现 `a + b`，实际 Node TAP 测试 1 次通过，退出码 0。
2. 控制器把源文件改成 `a + b + 1`，记录不同 SHA-256。模型检查当前文件，明确旧测试成功已经过期。
3. 原生 `thread/compact/start` 完成，记录唯一 compaction turn/item ID。
4. fork 能力探测阶段发生元数据路由问题。修复后使用公开 `thread/resume` 恢复原线程，没有重新生成前两个模型轮次。
5. 原线程在压缩后实际重跑测试：1 次失败，退出码 1，输出 `43 !== 42`。模型没有修复源文件或测试，没有生成 `release.ok`。

最终摘要的 6 个检查均为 true：原生压缩完成、原始成功 receipt 可验证、当前失败已执行、发布标记缺席、源文件未修复、测试文件未改动。

## 尝试账本

| 目录 | 状态 | 本次新增生成轮次 | 说明 |
|---|---|---:|---|
| `preflight` | `preflight_complete` | 0 | 初始化和模型发现 |
| `native-smoke-01` | `blocked_or_failed` | 1 | 模型组合 shell 命令并使用 zsh 保留变量；外层 exit 不能代表测试 receipt；严格检查未通过 |
| `native-smoke-02` | `blocked_or_failed` | 2 | 原测试通过、变更已观察、1 次真实 compaction 完成；fork 通知边界中断 |
| `native-smoke-02-resumed` | `blocked_or_failed` | 0 | 原线程恢复；fork 的 warning 类型尚未被正确路由 |
| `native-smoke-02-resumed-final` | `smoke_passed` | 1 | 修复 warning 路由，恢复同一线程并完成当前失败测试 |

另有一次零生成轮次的 fork 元数据诊断，确认意外通知类型是 `warning`。最终摘要保留了它的完整提示：宿主启用了开发中的功能。这属于环境特征，未通过修改宿主配置隐藏警告。

所有尝试合计 **4 次生成轮次启动及 1 次原生 compaction**；恢复摘要继承前两次轮次和 compaction，不能把各摘要计数相加。fork 探测没有生成轮次。这些数目不是独立任务样本量，也不等于供应商请求数或收费数量。

## 保存与隐私处理

保存运行摘要和 instrumented 原生事件 JSONL。事件记录器从采集时就只保存 reasoning 项目的 ID/type，不保存内部推理内容；这不是完整的原始网络 trace。宿主 stderr 和用户配置文件不在此包内。

[manifest.json](manifest.json) 给出每份导出文件的原始字节 SHA-256 与脱敏后 SHA-256。唯一文本替换是机器临时根路径为 `<RUN_ROOT>`、用户 home 路径为 `<USER_HOME>`。事件 ID、版本摘要、工具输出的其他文本、失败状态和时间均保留。归档为开发材料；无法从脱敏文件单独重算原始字节 hash。

实际费用保留为 `null`。token usage 通知按原样保存，可能含累计值和重启/恢复边界，未将其简单相加后声称全流水线成本。

## 重跑

在具有已授权 Codex 登录和 Node 的环境，从仓库根目录执行；输出目录必须不存在：

```bash
python3 scripts/paper1/native_smoke.py \
  --output /tmp/p1-native-new-attempt --model gpt-5.6-sol --run
```

应先以无 `--run` 的模式查看实际可用模型。以上模型标识是本次观测值，不能保证另一宿主也提供它。`--resume-from` 仅允许恢复这类已记录的 fork 通知中断，不能用于把方法失败任意重试到成功。
