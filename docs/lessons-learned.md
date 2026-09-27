# 经验教训

本文档记录 Asterwynd 开发过程中已经踩过的坑。后续遇到相似问题时，应优先检查这里。

## uv run 隔离环境缺少依赖

`uv run` 使用项目声明的依赖创建隔离环境。系统环境中已经安装的包，不代表 `uv run` 环境可用。

曾经的问题：WebSocket 功能依赖 `websockets`，系统环境有包，但 `pyproject.toml` 未声明，导致 WebSocket 连接异常。

教训：新增 FastAPI / WebSocket / 浏览器测试相关能力时，必须同步检查 `pyproject.toml`。

## Mock 行为与真实 API 不一致

`httpx.Response.json()` 是同步方法，测试中如果用 `AsyncMock` 模拟并在代码里 `await response.json()`，测试可能通过但真实运行会失败。

教训：mock 第三方库方法前，先确认真实方法是否 async。同步方法用 `MagicMock`。

## Provider 专有字段透传

DeepSeek 思考模式可能返回 `reasoning_content`，后续请求需要原样传回。Message 序列化如果丢掉 provider 专有字段，可能导致 400。

教训：接入新 provider 时，检查响应里是否有需要回传的非标准字段。Message 和 LLMResponse 要保守保留未知字段。

### 补记（issue #256）：不止是「别丢」，还要分清「可展示」与「只能原样回传」

后续接入思维链时踩得更深一层：Anthropic 系的 thinking block 带一个 `signature`，
它**不可解析、不可改写、顺序不可重排**（官方明确 "should not be interpreted or parsed"），
必须原样回传，否则签名校验失败 → 400。把它当普通字符串处理（走文本清洗、
被摘要改写、被 compaction 丢弃）都会破坏它。

另一个反直觉点：**DeepSeek V4 默认开启 thinking**，客户端不传任何参数也会收到；
且在 **Anthropic 兼容端点上，丢弃 thinking 是否报 400 取决于 `tool_use` id 的格式**
（`call_00_ET_` 前缀被豁免）——即「能用」建立在未文档化的实现细节上。

教训升级为三条：
1. 结构化区分「可展示文本」与「opaque 回传载荷」，后者全链路逐字节不变、不进任何清洗函数。
2. 「最新 assistant 轮必须回传」是硬要求，「更早轮可省略」——压缩时据此取舍。
3. 不要在未文档化的启发式上建立正确性；显式回传，并用端到端测试固定真实端点行为。

## 0.0.0.0 是监听地址，不是浏览器访问地址

服务器 bind `0.0.0.0` 表示监听所有网卡，但浏览器不能直接访问这个地址。

教训：启动日志应该展示实际可访问 URL，例如 `127.0.0.1` 或 `localhost`。

## 默认模型名与 provider 不匹配

如果默认模型写死为 OpenAI 模型，但用户配置 DeepSeek 或其他 provider，就会出现误导或调用失败。

教训：无 `--model` 时应优先读取环境变量，启动时需要清楚展示 provider 和 model。

## 日志只输出 stderr 不留痕

`logging.basicConfig()` 默认输出到 stderr，进程退出后排查困难。

教训：服务器模式需要文件日志，最好每次启动生成独立日志文件。

## AgentLoop 最终回复未写入 messages

曾经的问题：`AgentLoop.run()` 正常返回前没有把最终 assistant 回复追加到 messages。下一轮对话时 agent 看不到自己上一条回复，只能看到 tool call 和 tool result，导致重复回答。

教训：AgentLoop 返回前必须写入最终 assistant 回复。CLI 层和 loop 内部只能有一处负责追加，避免重复。

## MemoryManager compact 使用了错误的数据源

曾经的问题：`MemoryManager.compact_if_needed()` 统计自己的 `self.messages`，但 AgentLoop 使用独立的 messages 列表，导致 token compaction 从不触发。

教训：插件如果管理内部状态，必须确认 AgentLoop 实际使用的数据源与插件操作的数据源一致。
