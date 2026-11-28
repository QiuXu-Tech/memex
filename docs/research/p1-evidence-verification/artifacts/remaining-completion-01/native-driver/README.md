# 本地默认原生 driver 预检

执行 `python -B scripts/paper1/native_driver.py`，退出 0；[preflight.json](preflight.json) 为该命令的实际结构化输出，[verification.json](verification.json) 保留命令、driver 摘要及受保护文件执行前后的 SHA-256 核对。

**预检结果为 blocked，`dispatch_ready=false`、`scientific_ready=false`。** 当前命令的模型/网络调用、来源执行、子进程启动和账本写入均为 0；没有提供 settings 或 scope-specs，也没有读取凭据内容。它检查的是当前本地进程，不是对先前 Mac 执行设备的重新探测。

历史事实仍完整保留：原 canonical ledger 为 **7 个事件、2 次已消耗 native 尝试、1 次真实生成诊断、0 次方法单元派发**。CNY 3.00 诊断预留仍占用原 CNY 100 上限，实际现金未知。预检的零调用不能解释成旧 native 尝试或 DeepSeek 诊断没有发生；旧批准与账本字节均未变化。

预检确认原授权/来源计划与 public relocation、reader 配置；没有设置本地运行路径时，设备、tokenizer、价格依据等保持未提供或未检查，不能把它解释为已有 Mac 凭据被删除、服务鉴权失败或 B 已可用。

接口与两个现金上界模式见 [NATIVE_DRIVER.md](../../../NATIVE_DRIVER.md)，真实科学结果仍见[零结果报告](../reporting/README.md)。本产物没有冻结正式研究、选择 N、执行模型或创建第三次 native 许可。
