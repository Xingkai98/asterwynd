# Bullet 1 面试讲稿：AgentLoop 核心循环

> 实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 38 个内置工具

---

## 主讲述稿（~400 字）

Asterwynd 的 AgentLoop 是整个框架的运行时心脏，我在 `agent/loop.py` 里实现了一个 ~600 行的核心循环类。它的设计哲学是"message-driven"——所有状态存在一个 messages 数组里流转，没有外部状态机。每轮迭代做三件事：拼接上下文、调 LLM、执行工具调用，然后结果回填 messages，下一轮继续。这带来了一个直接好处：快照断点续传几乎是免费的——你只需要把 messages 序列化下来，恢复时重建数组就行。

我用 Hook 协议把横切关注点解耦出去——定义了 7 个切面：run 开始、每轮迭代前、LLM 调用后、工具执行前后、错误、完成。内置了日志、trace、重试、token 预算四个 Hook。HookManager 遍历独立执行，互不影响。

LLM Provider 这块我设计了一个统一的 LLM Protocol，只要求实现一个 `chat` 方法。OpenAILLM 和 AnthropicLLM 各自实现，关键差异是 Anthropic 路径支持手动打 `cache_control` 断点做 prompt caching，OpenAI 走服务端自动缓存。AnthropicLLM 还有三层降级——cache_control 被拒就去掉重试，vision 被拒就去掉图像重试。

38 个内置工具覆盖文件读写、Web 获取、LSP 代码理解、长期记忆、计划任务等类别，另外还有 10 个子 agent 工具和 MCP 工具可按需动态注册。

---

## 追问 1：为什么选 message-driven 而不是状态机？

**回答（~250 字）：**

状态机的核心问题是状态散落各处——tool_call 执行到哪一步、当前 mode 是什么、对话进行到第几轮——这些信息分布在多个变量里，序列化和恢复都很痛苦。message-driven 把所有状态收敛到 messages 数组——每条消息就是一步历史记录，数组本身就是完整的执行轨迹。

这个选择带来了三个直接收益。第一，断点续传成本极低——`SessionSnapshot` 只需要存 messages + mode + todos + skills，恢复时重建数组即可。我用 SHA-256 做内容去重，tmp+rename 原子写入，`finally` 块保底落盘。第二，调试友好——messages 数组就是完整 transcript，不需要额外重建上下文。第三，与 LLM API 天然对齐——LLM 的输入就是 messages 数组，不需要做状态→消息的转换层。

代价是 messages 会持续膨胀——这就需要 AutoCompact 上下文压缩来配合，以及 Prefix Cache 来降低重复 token 成本。这也是为什么 AgentLoop 不是孤立模块，它和 ContextBuilder、MemoryManager 深度耦合。

---

## 追问 2：Hook 协议为什么是 7 个切面？有考虑过更多吗？

**回答（~250 字）：**

7 个切面是沿着 AgentLoop 的单次迭代生命周期切出来的，原则是"每个外部可观测的状态转换点就是一个切面"。run 开始 → 迭代前 → LLM 调用后 → 工具执行前 → 工具执行后 → 错误 → 完成，这 7 个点完整覆盖了从启动到终止的全部状态转换。比这更多就会侵入核心循环的业务逻辑——比如"LLM 调用前"我不设切面，因为调用前的准备工作（上下文拼接、工具选择、cache plan）本身就是核心逻辑，不应该被 Hook 拦截。

业界对比：LangChain 的 Callback 体系有 ~20 个事件，但很多是 LLM 内部的 token 级事件（on_llm_new_token），对 Agent 框架来说粒度过细。AOP 切面的核心原则是"拦截点应该是架构边界，不是业务细节"。7 个切面刚好覆盖架构边界。

如果业务需要更多切面——比如流式 token 回调——可以通过 Hook 内部自行订阅 LLM 的 streaming 接口来实现，不需要在 Hook 协议层面暴露。

---

## 追问 3：快照断点续传能精确恢复 in-flight 工具调用吗？

**回答（~250 字）：**

不能。续传是 transcript 级，不是 call-stack 级——这是有意为之的设计决策。代码注释明确写了"resume is transcript-level, not stack-level"。

快照保存的是 messages 数组和执行元数据（mode、todos、skills），不保存 Python 调用栈。如果中断时恰好在工具执行中——assistant 的 tool_call 消息已经写入 messages 但 tool_result 还没写回——续传后对话历史里会有一个不完整的工具链。代码不会自动重新执行那个工具。模型看到不完整状态后会自然地重新发起调用。

为什么不做 stack-level？两个原因。第一，工具执行可能有副作用（Bash 命令、文件写入），盲目重放可能造成二次伤害。第二，Python 调用栈序列化本身就很脆弱——协程栈、闭包、网络连接都不可序列化。transcript-level 恢复虽然丢掉了"当前正在执行什么"的精确信息，但换来了实现简洁性和副作用的天然安全性。

---

## 追问 4：38 个工具怎么管理注册和生命周期？

**回答（~200 字）：**

工具注册通过 `ToolRegistry` 集中管理，每个工具继承 `Tool` 基类，定义 name、description、parameters（JSON Schema）、parallelizable 标志和 execute 方法。注册时自动做去重检测——对 description 做 embedding 后 cosine 比较，超过 0.7 阈值的标记 `duplicate_of`。

工具分三层：内置工具 38 个（`KNOWN_BUILTIN_TOOL_NAMES`），子 agent 工具 10 个（按需注册），MCP 工具（通过 MCP 协议动态发现和注入）。每轮迭代前通过 ToolSelector 做 BM25+embedding 两阶段检索，选出 Top-K 工具 schema 注入 LLM。稳定工具层 7 个永远常驻。

工具生命周期跟 AgentLoop 绑定——loop 创建时初始化 registry，loop 销毁时 registry 随之释放。不做跨 session 的工具缓存，因为不同 session 可能有不同的 MCP 连接和模式配置。

---

## 追问 5：双 Provider 适配中遇到的最棘手问题是什么？

**回答（~200 字）：**

最棘手的是 Anthropic 的 cache_control 兼容性。标准的 Anthropic API 支持 `cache_control: {"type": "ephemeral"}` 断点，但很多兼容端点（比如 DeepSeek 的 anthropic 兼容模式）不认识这个字段，直接返回 400。我的解决方案是三层降级——400 + cache_control → 自动去掉所有 cache_control 重试；400 + vision → 自动去掉图像 content block 重试；其他 400 → 直接报错。

另一个问题是 OpenAI 和 Anthropic 的 tool call 格式不同。OpenAI 用 `tool_calls` 数组，每个元素有 `id`、`function.name`、`function.arguments`。Anthropic 用 `content` 数组里的 `tool_use` block。我在 `LLMResponse` 里做了统一抽象，AgentLoop 只看到标准化的 `ToolCall` 对象。

流式处理也有差异——OpenAI 的 streaming tool calls 需要手动拼接 JSON fragments，Anthropic 的 SSE 格式也不一样。这些差异全部封装在各自 LLM 类内部。
