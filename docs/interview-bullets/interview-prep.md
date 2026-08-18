# Bullet 面试讲稿合集（1-7）

> 七条简历 bullet 的面试讲稿合集。每条含主讲述稿（~400-450 字）+ 系列追问与回答，讲法与代码走读互补。
> 简历原文见 [resume-bullets.md](./resume-bullets.md)。代码走读见 [walkthrough.md](./walkthrough.md)。

- **Bullet 1** · AgentLoop 核心循环
- **Bullet 2** · 动态工具编排
- **Bullet 3** · 多 Agent 编排模式
- **Bullet 4** · ContextBuilder 上下文系统
- **Bullet 5** · 长期记忆系统
- **Bullet 6** · 3 层纵深防御安全体系
- **Bullet 7** · 全链路可观测体系与 Benchmark 评测闭环


---

## Bullet 1 面试讲稿：AgentLoop 核心循环

> 实现可扩展 AgentLoop 核心循环（message-driven + 快照断点续传），以 7 切面 Hook 协议解耦迭代/LLM 调用/工具执行/错误处理/完成阶段，同构适配 OpenAI / Anthropic 双 Provider，集成 38 个内置工具

---

### 主讲述稿（~400 字）

Asterwynd 的 AgentLoop 是整个框架的运行时心脏，我在 `agent/loop.py` 里实现了一个 ~600 行的核心循环类。它的设计哲学是"message-driven"——所有状态存在一个 messages 数组里流转，没有外部状态机。每轮迭代做三件事：拼接上下文、调 LLM、执行工具调用，然后结果回填 messages，下一轮继续。这带来了一个直接好处：快照断点续传几乎是免费的——你只需要把 messages 序列化下来，恢复时重建数组就行。

我用 Hook 协议把横切关注点解耦出去——定义了 7 个切面：run 开始、每轮迭代前、LLM 调用后、工具执行前后、错误、完成。内置了日志、trace、重试、token 预算四个 Hook。HookManager 遍历独立执行，互不影响。

LLM Provider 这块我设计了一个统一的 LLM Protocol，只要求实现一个 `chat` 方法。OpenAILLM 和 AnthropicLLM 各自实现，关键差异是 Anthropic 路径支持手动打 `cache_control` 断点做 prompt caching，OpenAI 走服务端自动缓存。AnthropicLLM 还有三层降级——cache_control 被拒就去掉重试，vision 被拒就去掉图像重试。

38 个内置工具覆盖文件读写、Web 获取、LSP 代码理解、长期记忆、计划任务等类别，另外还有 10 个子 agent 工具和 MCP 工具可按需动态注册。

---

### 追问 1：为什么选 message-driven 而不是状态机？

**回答（~250 字）：**

状态机的核心问题是状态散落各处——tool_call 执行到哪一步、当前 mode 是什么、对话进行到第几轮——这些信息分布在多个变量里，序列化和恢复都很痛苦。message-driven 把所有状态收敛到 messages 数组——每条消息就是一步历史记录，数组本身就是完整的执行轨迹。

这个选择带来了三个直接收益。第一，断点续传成本极低——`SessionSnapshot` 只需要存 messages + mode + todos + skills，恢复时重建数组即可。我用 SHA-256 做内容去重，tmp+rename 原子写入，`finally` 块保底落盘。第二，调试友好——messages 数组就是完整 transcript，不需要额外重建上下文。第三，与 LLM API 天然对齐——LLM 的输入就是 messages 数组，不需要做状态→消息的转换层。

代价是 messages 会持续膨胀——这就需要 AutoCompact 上下文压缩来配合，以及 Prefix Cache 来降低重复 token 成本。这也是为什么 AgentLoop 不是孤立模块，它和 ContextBuilder、MemoryManager 深度耦合。

---

### 追问 2：Hook 协议为什么是 7 个切面？有考虑过更多吗？

**回答（~250 字）：**

7 个切面是沿着 AgentLoop 的单次迭代生命周期切出来的，原则是"每个外部可观测的状态转换点就是一个切面"。run 开始 → 迭代前 → LLM 调用后 → 工具执行前 → 工具执行后 → 错误 → 完成，这 7 个点完整覆盖了从启动到终止的全部状态转换。比这更多就会侵入核心循环的业务逻辑——比如"LLM 调用前"我不设切面，因为调用前的准备工作（上下文拼接、工具选择、cache plan）本身就是核心逻辑，不应该被 Hook 拦截。

业界对比：LangChain 的 Callback 体系有 ~20 个事件，但很多是 LLM 内部的 token 级事件（on_llm_new_token），对 Agent 框架来说粒度过细。AOP 切面的核心原则是"拦截点应该是架构边界，不是业务细节"。7 个切面刚好覆盖架构边界。

如果业务需要更多切面——比如流式 token 回调——可以通过 Hook 内部自行订阅 LLM 的 streaming 接口来实现，不需要在 Hook 协议层面暴露。

---

### 追问 3：快照断点续传能精确恢复 in-flight 工具调用吗？

**回答（~250 字）：**

不能。续传是 transcript 级，不是 call-stack 级——这是有意为之的设计决策。代码注释明确写了"resume is transcript-level, not stack-level"。

快照保存的是 messages 数组和执行元数据（mode、todos、skills），不保存 Python 调用栈。如果中断时恰好在工具执行中——assistant 的 tool_call 消息已经写入 messages 但 tool_result 还没写回——续传后对话历史里会有一个不完整的工具链。代码不会自动重新执行那个工具。模型看到不完整状态后会自然地重新发起调用。

为什么不做 stack-level？两个原因。第一，工具执行可能有副作用（Bash 命令、文件写入），盲目重放可能造成二次伤害。第二，Python 调用栈序列化本身就很脆弱——协程栈、闭包、网络连接都不可序列化。transcript-level 恢复虽然丢掉了"当前正在执行什么"的精确信息，但换来了实现简洁性和副作用的天然安全性。

---

### 追问 4：38 个工具怎么管理注册和生命周期？

**回答（~200 字）：**

工具注册通过 `ToolRegistry` 集中管理，每个工具继承 `Tool` 基类，定义 name、description、parameters（JSON Schema）、parallelizable 标志和 execute 方法。注册时自动做去重检测——对 description 做 embedding 后 cosine 比较，超过 0.7 阈值的标记 `duplicate_of`。

工具分三层：内置工具 38 个（`KNOWN_BUILTIN_TOOL_NAMES`），子 agent 工具 10 个（按需注册），MCP 工具（通过 MCP 协议动态发现和注入）。每轮迭代前通过 ToolSelector 做 BM25+embedding 两阶段检索，选出 Top-K 工具 schema 注入 LLM。稳定工具层 7 个永远常驻。

工具生命周期跟 AgentLoop 绑定——loop 创建时初始化 registry，loop 销毁时 registry 随之释放。不做跨 session 的工具缓存，因为不同 session 可能有不同的 MCP 连接和模式配置。

---

### 追问 5：双 Provider 适配中遇到的最棘手问题是什么？

**回答（~200 字）：**

最棘手的是 Anthropic 的 cache_control 兼容性。标准的 Anthropic API 支持 `cache_control: {"type": "ephemeral"}` 断点，但很多兼容端点（比如 DeepSeek 的 anthropic 兼容模式）不认识这个字段，直接返回 400。我的解决方案是三层降级——400 + cache_control → 自动去掉所有 cache_control 重试；400 + vision → 自动去掉图像 content block 重试；其他 400 → 直接报错。

另一个问题是 OpenAI 和 Anthropic 的 tool call 格式不同。OpenAI 用 `tool_calls` 数组，每个元素有 `id`、`function.name`、`function.arguments`。Anthropic 用 `content` 数组里的 `tool_use` block。我在 `LLMResponse` 里做了统一抽象，AgentLoop 只看到标准化的 `ToolCall` 对象。

流式处理也有差异——OpenAI 的 streaming tool calls 需要手动拼接 JSON fragments，Anthropic 的 SSE 格式也不一样。这些差异全部封装在各自 LLM 类内部。

---

## Bullet 2 面试讲稿：动态工具编排

> 实现动态工具编排：BM25 粗筛 + 向量精排两阶段按对话上下文 Top-K 注入工具 schema，核心工具稳定层常驻且不占 Top-K 预算、配合 cache_control 断点保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级

---

### 主讲述稿（~400 字）

这个功能要解决一个很实际的问题：38 个工具全量注入给 LLM 成本太高——每个工具的 JSON Schema 占几百 token，38 个就是好几千，而且大部分工具当前任务根本用不到。我的方案是每次迭代只选最相关的几个注入。

代码在 `agent/tools/governance/` 目录。核心是 `ToolSelector` 类——每次 LLM 调用前，用"用户最新消息 + 最近 3 个工具调用名"拼成 query，然后走两阶段检索。

第一个设计决策是"稳定层"——Read、Edit、Write、Bash、Glob、Grep、InspectGitDiff 这 7 个工具在任何 coding 任务中都会用到，我让它们永远排在工具列表最前面且位置固定。因为 schema 字节级不变，可以在上面打 `cache_control` 断点，Anthropic API 就不会重复计算这部分的 KV cache。

剩下 ~30 个变层工具走两阶段筛选。BM25 粗筛做关键词匹配，取 top 50。向量精排用 embedding 做 cosine 相似度重排，取 top 5。最终注入 LLM 的是 7 稳定 + 5 变层 = 12 个 tool schema。

还有两个辅助机制。语义去重在每个新工具注册时跟已有工具做 cosine 比较，超过阈值标记 `duplicate_of`，软标记不影响功能。质量评分用 50 次滑动窗口——成功率 + 耗时因子 + 审批率的加权——低于 0.4 就从变层候选剔除，但稳定层不受影响、全量 schema 仍可见。这就是"软降级"。

---

### 追问 1：为什么选 BM25 + embedding 两阶段而不是直接用 embedding？

**回答（~250 字）：**

两阶段是成本和质量之间的权衡。直接用 embedding cos 精排对所有 30 个工具做全量比较，每次 LLM 调用前都要做 30 次 cosine 计算。BM25 粗筛几乎零成本——标准的倒排索引加 TF-IDF 变体，纯 CPU 毫秒级——先把候选池从 30 个收到 50 个（未来工具数 100+ 时会更有意义），然后 embedding 只在 50 个候选中做精排。

BM25 的优势是关键词匹配很准——如果用户说"帮我读文件"，BM25 会对 Read 和 Grep 打高分，因为它直接匹配 description 中的"读取"和"文件"。但 BM25 完全不懂语义——"检查代码"和"review code"对它来说是无关的。Embedding（即使是最简单的 n-gram 哈希向量）能捕捉到字面上的字符共现——Read 和 Grep 的 description 里有很多共同的英文词。

未来工具数增加到 100+ 时，BM25 真正的筛选价值会体现出来——把全量搜缩小到 50 候选，减少 50% 的 embedding 计算量。

---

### 追问 2：当前用的 NGramEmbedding 效果如何？为什么不直接用 sentence-transformers？

**回答（~200 字）：**

NGramEmbedding 是字符 n-gram 的 MD5 哈希拼成的 256 维向量，零外部依赖、确定性（同输入永远同输出）、不需要 GPU、不需要下载模型。对于工具 description 这种几十字的英文短文本，效果其实不差——因为工具名本身就是很强的语义信号，"Read"和"Grep"的 description 里都有"file""search""pattern"这些词，n-gram 向量能捕捉到这种字面共现。

但它的局限也很明显——同义词完全感知不到。"Read"和"View"功能相似，但字面上没有重叠，n-gram cosine 会很低。

不用 sentence-transformers 的核心原因是**零依赖优先**。Asterwynd 的定位是 pip install 即可用，不强制用户装 PyTorch。代码已经预留了 `EmbeddingProvider` Protocol 的插拔缝——只要实现 `embed` 和 `cosine` 两个方法就能替换。如果业务场景对语义精度要求高，一行配置就能切到 all-MiniLM-L6-v2。

---

### 追问 3：Prefix Cache 断点怎么打？如果变层工具变了不会破坏缓存吗？

**回答（~250 字）：**

断点打在**最后一个稳定工具**上，这是精心设计的位置。Anthropic 的 prompt caching 机制是：从 prompt 开头到 `cache_control` 断点之间的所有内容被缓存，断点之后的内容每次重新计算。

我的稳定层是 7 个工具，按注册顺序固定排列，schema 字节级不变。变层的 5 个工具排在后面，每次可能不同。断点打在最后一个稳定工具的位置，意味着 system 消息 + 稳定工具全部被缓存，只有变层的 5 个工具每次重新计算。

95% 以上的迭代中变层工具不会改变——如果用户一直在做文件操作，稳定层就够了，变层可能一直是空的或相同工具。这时整个 tools 数组都被缓存了。只有当用户切换任务类型时变层才变化——比如从读文件变成搜网页。

这里还有个细节：`cacheable` 属性不仅打给稳定工具，还打给 ContextBuilder 的 P0/P1 上下文源。`_compute_cache_plan` 扫描所有 system block 找最后一个 `cache=True` 的位置。默认（Selector OFF）时断点只打 system block，Selector ON 时考虑 tool 层。

---

### 追问 4：质量评分公式的三个权重（0.5/0.3/0.2）是怎么定的？

**回答（~200 字）：**

坦白说，当前公式是一个启发式的起点，不是经过实验验证的最优解。0.5 给成功率是最自然的——工具调用成功与否是最直接的质量信号。0.3 给耗时因子和 0.2 给审批率是直觉分配。

走读代码后我发现了两个问题（已提 issue #120）。第一，耗时因子 `1.0 - avg_duration/30000` 把"快=好"当成普适逻辑，但 git clone 就是比 ls 慢，不代表质量差，业界没人这样用。第二，审批率是安全策略偏好，不是工具质量信号——应该独立存在。

后续改进方向：去掉 duration 和 approval，引入 Tool Selection Accuracy（模型选了不该选工具的比例）和 Invalid Tool Rate（幻觉出不存在的工具），把错误类型分类（超时 vs 参数错误 vs 权限错误）也纳入评分。质量评分应该只问一个核心问题——"这个工具被正确选中的概率有多高"。

---

### 追问 5：如果 selector 功能默认关闭，简历写的这些有什么意义？

**回答（~150 字）：**

代码完整实现了，测试覆盖到位，通过配置开关控制——这是成熟的工程实践，不是 vaporware。就像 nginx 的 gzip 压缩默认关闭不代表没实现。

而且设计上关闭时有合理的降级行为——走 `get_all_schemas()` 全量注入，cache_control 断点打在最后一个 cacheable system block 上。用户不需要证明"我需要动态工具选择"才能用一个功能完整的 agent。随着 MCP 工具接入量增加，这个开关的价值会越来越明显。

---

## Bullet 3 面试讲稿：多 Agent 编排模式

> 内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token/时间双维度预算硬 kill 与快照恢复

---

### 主讲述稿（~400 字）

多 Agent 编排是我在 Asterwynd 里实现的协作层，让一个主 agent 能 spawn 多个子 agent 协同完成任务。代码在 `agent/subagent/` 目录，四个核心模块。

关键是 4 种编排模式，在 `patterns.py` 里通过 `PATTERNS` 注册表管理。Orchestrator-Worker 最直接——fan-out 到 N 个并行 worker，所有 worker 执行相同任务，最后 aggregate 结果。Peer-Review 是 producer-reviewer 对——producer 产出方案，reviewer 评审，最多 3 轮迭代，reviewer 回复 "APPROVED" 才通过。Hierarchical 是 N 个 manager 各自带团队，manager 可以继续 spawn worker，形成树状工作组，深度上限 3 层。Bidding 是 N 个 proposer 独立出方案，一个 selector 选最佳——它的 proposal 传递故意不走消息总线，因为总线的 drop-oldest 策略可能丢关键竞标。

消息总线是子 agent 间的通信层——每个编排 run 创建一个 MessageBus 实例，子 agent 通过 PublishBusMessage/ReadBus 两个工具交换语义摘要。总线有三层 token 预算控制——容量上限 100 条、发布端 LLM 摘要压缩到 400 token、消费端从最新消息往前截断。

预算硬 kill 是我比较满意的一个设计——token 超限在 LLM 调用后立即被 hook 检测并抛异常终止，时间超限用独立协程 asyncio.sleep 后 cancel 跑趟 task，处理的是工具卡死的场景。两条路径都先写 checkpoint 再杀。

---

### 追问 1：4 种编排模式是怎么选出来的？为什么是这 4 种不是别的？

**回答（~250 字）：**

这 4 种模式覆盖了多 Agent 协作的几个核心拓扑结构，每个对应一类真实需求。

Orchestrator-Worker 是最基础的并行化——"把这件事做 N 遍取最佳"，对应代码生成里的并行采样或数据处理的 map-reduce。它的假设是 worker 之间不需要通信，任务天然可并行。

Peer-Review 对应质量控制——"你写我审，通过为止"。核心价值是用一个 reviewer 来校准 producer，对代码 review、方案评审特别有效。最多 3 轮是为了平衡质量和成本。

Hierarchical 对应大规模分解——"一个人管不过来，分给多个组长各自带团队"。适合需要多维度并行探索的场景，比如同时调研多个技术方案。

Bidding 对应方案竞选——"N 个人出方案，一个人拍板"。与 Orchestrator-Worker 不同，proposer 各自出不同方案而非相同答案，selector 做选择。适合架构设计这种没有标准答案的任务。

这 4 种模式不是随意选的——每个对应一类拓扑（fan-out、feedback loop、tree、competition），覆盖了多 Agent 协作的主要范式。

---

### 追问 2：消息总线的"三层 token 预算"具体怎么工作的？

**回答（~250 字）：**

三层预算是自底向上递进的，从量限制到质量压缩。

第一层是容量限制——bounded queue 最多 100 条消息，溢出用 drop-oldest 策略。这个设计牺牲了完整性保预算，所以 bidding 模式故意不走 bus——它的竞标信息必须全量保留。

第二层是发布端摘要压缩——每个 agent 调用 PublishBusMessage 时，如果内容超过 400 token，自动调 LLM 做摘要再入队。不可用 LLM 时退化到字符截断。这意味着总线上流动的是"结论"而非"过程"——子 agent 的完整思考过程在 transcript 里，总线上只放关键发现。

第三层是消费端 token 窗口——agent 调用 ReadBus 时从最新消息往前累加，直到达到 token 上限（默认 2000）。单条超预算也保留最新一条——不让消费者错过最重要的信息。返回时 oldest-first 排列，保持时间顺序可读。

三层加在一起，把"N 个 agent 的原始对话"压缩到"几千 token 的结构化摘要"，不过度消耗主 agent 的 context window。

---

### 追问 3：Token 超限和时间超限两条 kill 路径有什么区别？为什么需要两套机制？

**回答（~200 字）：**

两套机制处理的是完全不同的超标场景。

Token 超限是在 LLM 调用边界被检测到的——每次 LLM 返回后 BudgetHook 累加 input+output tokens，超过限制立即抛 BudgetExceededError。这需要在能执行代码的 hook 层触发，因为只有那里能读到 usage 信息。

时间超限的场景是工具卡死——比如 Bash 命令 hang 住了，hook 永远等不到触发。这时候需要一个外部 watcher——独立的 asyncio 协程 sleep 到 timeout 时间后，检查 run 是否还在活跃，如果是就 cancel 跑趟 task。

关键设计是两个路径的执行顺序——先标记 `_budget_kill_reason`，再写 checkpoint，最后才 cancel 或抛异常。这样被取消后的 handler 能区分"这是预算杀"还是"用户手动取消"，终止状态分别标记为 `budget_exceeded` 和 `cancelled`。

两套机制也可以同时配置——token 预算防止烧钱，时间预算防止卡死。

---

### 追问 4：子 agent 的快照和主 agent 的快照是同一套机制吗？

**回答（~150 字）：**

底层存储复用同一个 SessionStore——相同的 schema_version 兼容、SHA-256 去重、tmp+rename 原子写入——但存储路径和恢复逻辑是独立的。子 agent 快照存在 `<workspace>/.asterwynd/subagents/<run_id>/`，key 是完整 run_id 而非短 subagent_id。

区别在于快照内容——子 agent 快照额外携带 objective、blockers、next_steps、bus_summary 这些编排字段。恢复也是 transcript 级——快照把对话历史重建后，从 iteration 0 重新循环，不恢复 Python 调用栈。

子 agent 有自己的 ResumeSubagent 工具，主 agent 可以通过它主动恢复任何有 checkpoint 的已中断 run。

---

## Bullet 4 面试讲稿：ContextBuilder 上下文系统

> 实现 ContextBuilder 统一编排 8 个上下文源，稳定前缀分层注入、字节级不变命中 LLM Prefix Cache，搭配 AutoCompact L1/L2 层级压缩与 tool-call pending 标记防止工具链断裂

---

### 主讲述稿（~400 字）

上下文工程是 Agent 框架里最容易被低估的子系统。ContextBuilder 要解决的核心问题是：每次 LLM 调用前，怎么把系统提示词、项目规则、记忆、待办事项、技能信息、计划状态这些信息高效地注入到 system 消息里，既不能超预算，又要保证缓存命中。

代码在 `agent/context/builder.py`。我定义了 8 个 ContextSource，从 P0 到 P5 分层。SystemPrompt 和 AsterMd（项目规则）最高优先级，同时是 static 的——同 cwd、mode、user_system_prompt 下输出字节级不变，可以跨迭代缓存。加上 MemoryIndex（记忆索引），这三个是 cacheable 层，永不参与预算截断，成为稳定前缀。

注入预算默认 20000 token，如果 8 个源超预算，从最低优先级 tail-first 截断——先裁计划状态，再裁技能信息，再裁待办。cacheable 层不受影响。

AutoCompact 是上下文压缩系统，代码在 `agent/memory/manager.py`。对话超过阈值（100K 窗口下是 85K）时触发 L1 增量压缩——保留最近 10 条消息，中间部分送 LLM 做四段式摘要（已完成 / 待办 / 疑难点 / 进行中）。当 L1 累计超过 6000 token 且至少 2 个 chunk 时，触发 L2 高阶压缩，把 L1 摘要再压缩一次。

tool-call pending 标记是我特别在意的设计。压缩时如果有些工具调用还没完成，摘要会让模型"忘记"这些调用。我的三层保障：窗口扩展保证工具链不被切断，pending 标记显式标注未完成的调用，summarizer 的 prompt 要求逐字保留这些标记。

---

### 追问 1：为什么要分 P0-P5 而不是简单按类型分？预算截断为什么是 tail-first？

**回答（~250 字）：**

P0-P5 的分层是为了同时满足三个约束。第一，有些内容是生存必需的——没了 system prompt 和项目规则，agent 不知道该干什么。所以 P0/P1 是 critical+cacheable，永不截断。第二，有些内容是"越多越好但可以部分牺牲"——记忆索引和待办事项有助于决策但不致命。第三，有些内容是"锦上添花"——技能列表和计划状态缺失也能工作。

Tail-first 截断是从低优先级尾部开始裁，而不是均匀缩减所有源——因为低优先级信息即使不全也比压缩到不可读要强。例如把每个 skill 描述截成 10% 长度会导致描述完全失真实用，不如整体裁掉 P5 的计划状态。

这个设计受操作系统内存管理的启发——不是把每个进程都砍一刀，而是 swap out 低优先级进程。ContextBuilder 做的就是上下文的"页面置换"。

另外 P3 的位置是空着的——这是有意的，留给未来可能加入的中优先级上下文源。分层设计预留了扩展点。

---

### 追问 2：Prefix Cache 的"字节级不变"怎么保证？什么情况下会打破？

**回答（~250 字）：**

"字节级不变"由三层保障。第一层是 static 属性——P0 和 P1 的渲染输出由 `(name, cwd, mode, user_system_prompt)` 决定。只要这四个值不变，`_static_cache_key` 命中缓存，返回的就是字节级相同的内容。第二层是 cacheable 层不参与预算截断——不管 context 多满，P0/P1/MemoryIndex 永远不会被截断，所以它们在 messages 中的位置和内容始终确定。第三层是工具 schema 稳定——当 Selector OFF 时，全量 38 个工具 schema 按固定顺序排列，字节级不变。

以下场景会打破缓存：用户切换 mode（build → plan），cwd 在 subagent spawn 到新 workspace 时变化，user_system_prompt 被用户修改，或者 Selector ON 时变层工具变了位置。这些场景通常发生在会话开始或重大转折点，不在高频迭代中。

设计上的关键是让"打破缓存"的触发条件可预测——同一个 session 的大部分迭代命中缓存，成本集中在少数转折迭代上。

---

### 追问 3：L1 和 L2 压缩的全流程是怎样的？为什么需要两层？

**回答（~250 字）：**

压缩在每次迭代末触发，两个条件必须同时满足：总 token 超过阈值（默认 85K），且距上次压缩至少 5 轮（防抖动）。

L1 流程是：分离 system 消息、取最近 10 条 + 工具链保护的 recent window、确定需要压缩的 middle segment、给 middle segment 打上 pending 标记和分页进度、送 LLM 做四段式摘要。摘要以 user 角色（不是 system）注入，让模型把它当作"对话历史摘要"而非"系统约束"来处理。

L2 触发条件是至少 2 个 L1 chunk 且累计超过 6000 token。输入是已有 L2 基础 + 所有 L1 chunk，预算是 L1 累积的 30%。关键设计是每次 L2 都带上上次的 L2 基础——顶层结论永不丢失。

为什么需要两层？单层压缩的问题是历史被"扁平化"——第 100 轮的摘要和第 1 轮的摘要在 L1 里是平权的。L2 做的是对 L1 摘要的"摘要"，把多段 L1 提炼成更高层次的结论。类比就是 L1 是"每章小结"，L2 是"全书摘要"。

---

### 追问 4：tool-call pending 标记在压缩中怎么保证不丢失？

**回答（~200 字）：**

三层保障链。第一层：`_recent_with_tool_chains` 扩展 recent window——如果最近 10 条里有 3 个 tool result，但对应的 assistant tool_call 消息在第 12 位，window 自动前扩展到包含它们。保证工具链消息对不被切断。

第二层：`_annotate_pending_calls` 在压缩前全量扫描 middle + recent，收集所有已有结果的 tool_call_id，然后对 middle segment 中的 assistant 消息逐条检查——tool_call 没有对应 result 就打上 `[call#1: toolu_abc123 pending]`。其中 #1 是 1-based 位置编号，toolu_abc123 是工具调用 ID。

第三层：summarizer 的 system prompt 和 user prompt 明确要求逐字保留 pending 标记。L2 压缩的 prompt 同样要求。这意味着即使经过两级压缩，未完成的工具调用信息不会丢失。

---

### 追问 5：ContextBuilder 和其他 Agent 框架的上下文管理有什么不同？

**回答（~200 字）：**

两个核心差异。第一是"分层的 cacheable 前缀"——大多数框架要么不做 prefix cache 优化，要么全量缓存（一旦任何东西变化就全部失效）。我的做法是区分 cacheable 和 non-cacheable 层，只在 cacheable 前缀的末尾打断点。这意味着变层的待办事项或技能列表变化时，缓存仍然 90%+ 命中。这个设计直接来自对 Anthropic API 行为的深入理解。

第二是 pending 标记机制——大多数框架的压缩策略是"保留最近 N 条消息"，但不检查工具链完整性。这会导致压缩后出现 broken tool chains，LLM 下次调用时困惑于"我之前调用的工具怎么没结果"。我的三层保障专门解决这个痛点。

LangChain 的 ConversationSummaryBufferMemory 做的是纯摘要 + 最近 N 条，没有缓存分层。LlamaIndex 的 ChatMemoryBuffer 有 token 限制但没有分层压缩。Asterwynd 是把这三件事——分层缓存、分层压缩、工具链保护——整合在了一起。

---

## Bullet 5 面试讲稿：长期记忆系统

> 构建长期记忆系统，LLM 写时四分支去重（supplement/update/conflict + new 兜底），importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆

---

### 主讲述稿（~400 字）

长期记忆系统解决的是跨 session 知识积累的问题。每次 agent 运行完，用户偏好、项目约定、踩过的坑都应该保留下来，下次运行时自动注入上下文。

每条记忆是一个独立的 Markdown 文件，YAML frontmatter 存元数据（importance 1-5、创建时间、最后访问时间、类型标签），正文存实际内容。有一个 MEMORY.md 索引文件做人类可读的目录。5 个工具暴露给 LLM——SaveMemory、RecallMemory、SearchMemory、ResolveMemoryConflict、MemoryGitBackend。

写路径的核心是四分支去重。每次写入前，先向量召回 top 5 相似记忆，然后调 LLM 判决新内容和已有记忆的关系——完全新的就新建文件（new），对已有记忆补充细节就追加到原文尾部（supplement），新内容取代旧内容就整体替换（update），内容矛盾两边都保留并双向标记 conflict_with（conflict）。所有异常路径都 fallback 到 new——宁可重复存，不丢信息。

读路径的核心是 importance × recency 联合衰减。公式是 `importance × 0.5^(days/30)`——30 天半衰期，importance 高的记忆即使不访问也能存活更久。每次 recall/search 命中就刷新 last_accessed_at。超过 30 天未访问且衰减分数低于 1.5 的自动归档到 archive/ 子目录。可手动恢复。

最特别的是 git 可逆机制——memory 目录是一个独立的 git 仓库，懒初始化。每次破坏性写（supplement/update/conflict）前先 git commit 当前状态，commit 失败就中止写入。Revert 是两阶段 commit——先 commit 当前状态做 undo 凭证，再 checkout 旧内容并重建索引。

---

### 追问 1：为什么选文件+Git 而不是数据库？对比过什么方案？

**回答（~250 字）：**

三个核心原因。第一是"人类可读性"——Markdown 文件 + MEMORY.md 索引可以直接用任何编辑器打开查看和修改，不需要专门的查询工具。这在调试记忆系统本身时特别有价值——你可以直接看每一条记忆的内容，不需要写 SQL。

第二是"git 是现成的版本控制"——如果自己实现版本管理，需要做 diff、log、restore，还要处理并发写入和原子性。而 git 已经完美解决了这些问题，加上 Git Worktree 感知的作用域复用——同一个仓库的多个 worktree 共享一份 memory 存储——更是直接拿到了项目隔离和跨 session 持久化。

ADR-0002 里对比了三个替代方案：mem0 V3 的 ADD-only + 读时 ranker（需要多信号排序引擎，Asterwynd 当前只有 NGramEmbedding，弱 ranker 下矛盾记忆会无序浮出）、侧车 revisions 目录（"自己发明的残缺版 git"——缺 diff/log/restore）、单文件 .bak（误判链覆盖中间版本）。最终选择文件+Git 是工程上最务实的方案。

---

### 追问 2：四分支去重里 LLM 判错了怎么办？有纠正机制吗？

**回答（~200 字）：**

多层兜底。第一层是向量召回阈值——相似度低于 0.5 的候选直接短路为 new，不经过 LLM，零成本零误判。第二层是 LLM 不可用时的 fallback——直接 new，不阻塞写入。第三层是 LLM 输出校验——JSON 解析失败、未知 action、target 文件名非法（如 `../etc/passwd`）全部 fallback 到 new。第四层是 target 校验——supplement/update 的目标如果不存在或已归档，退化为 new。

纠正机制有两层。第一层是 git revert——通过 MemoryGitBackend 工具随时回退到任意历史版本，两阶段 commit 保留完整审计链。第二层是 ResolveMemoryConflict 工具——当 conflict 标记存在时，LLM 可以主动调用此工具选择保留一方并归档败者。

核心设计哲学是"宁可多存不丢"——fallback 全部偏向 new 而非拒写。误存可以事后清理，漏存就永久丢失了。

---

### 追问 3：衰减公式里的 30 天半衰期和 1.5 阈值是怎么定的？

**回答（~150 字）：**

30 天半衰期是直觉选值——大部分项目的开发周期以周为单位，30 天意味着一个月不碰的记忆权重降一半，两个月降到 1/4，这是一个温和但持续的衰减曲线。1.5 阈值是基于默认 importance=3——3×0.5=1.5，意味着默认重要度的记忆刚好在 30 天时触碰归档边界。importance=5 的记忆在 60 天后 score=1.25 才会被归档。

这些参数都可配置——构造 PersistentMemory 时可以覆盖 archive_after_days、recency_halflife_days、decay_threshold。也支持关闭衰减（decay_threshold=None），变成纯时间归档。

---

### 追问 4：git commit-before-write 怎么保证不丢数据？

**回答（~200 字）：**

核心设计是"commit 失败 = 写入中止"。`_git_commit` 方法里每个 git 操作都检查返回值——git 不可用抛 RuntimeError、git init 失败抛 RuntimeError、git add 失败抛 RuntimeError、git commit 失败抛 RuntimeError。所有异常在调用方（save/apply_judgment）被捕获，写入操作不会执行。

特殊处理是 nothing-to-commit——当 repo 是全新的（第一次写入前没有任何内容需要快照），git diff --cached --quiet 返回 0，直接安全通过不抛异常。这是合理的——第一次写入确实没有"旧内容"需要保护。

两阶段 revert 是另一个保障——revert 前先 commit 当前状态，所以被覆盖的"当前版本"也有一个快照。这意味着 revert 本身是可 revert 的——你可以回退到回退之前的状态。changelog 保留完整审计，不受 revert 影响。

---

### 追问 5：如果不用 LLM 做去重判决，有什么替代方案？

**回答（~150 字）：**

最直接的替代是纯向量去重——cosine 相似度超过阈值就判定为"相同"，直接 update。但这有个致命问题：无法区分 supplement（补充细节）和 conflict（内容矛盾）。两个描述同一件事的记忆可能 high cosine 但一个是"用 Redis 做缓存"另一个是"用 Memcached 做缓存"——语义相似但内容矛盾。

这就是为什么选了 LLM 判决——它不仅能识别"相似"，还能判断关系的性质（补充/取代/矛盾）。代价是每次写入多一次 LLM 调用，但写操作本身是低频的。mem0 V3 的 ADD-only 方案反过来——不在写时判断，在读时用多信号排序让最佳记忆浮出来。但 Asterwynd 的读路径只有 NGramEmbedding，弱 ranker 下矛盾记忆会无序浮出，所以 ADD-only 不适合当前架构。

---

## Bullet 6 面试讲稿：3 层纵深防御安全体系

> 实现 3 层纵深防御安全体系：工作区路径边界 + 敏感文件 deny 与 mode 权限 fail-closed → CommandGuard 语义级命令检查覆盖绕过变体 → 进程沙箱 + cgroup v2 资源限制 / Docker 容器隔离双后端，配合细粒度工具权限、受控只读浏览器（URL 白名单 + 只读工具集）和人工审批链路

---

### 主讲述稿（~450 字）

安全体系是我在 Asterwynd 里花了很多心思设计的部分——因为一个能执行 Bash 命令和文件读写的 AI agent，安全问题不是可选的，是生存问题。我设计了三层纵深防御，每层承担不同的职责。

第一层是工作区策略和权限模型。WorkspacePolicy 限制 agent 只能读写 workspace 内的文件，35 条 glob 模式拒绝敏感文件（.git、.env、私钥、SSH 密钥等）。权限模型定义了 8 种 Capability（如 WORKSPACE_READ、COMMAND_EXECUTE、BROWSER_CONTROL）、3 级风险（LOW/MEDIUM/HIGH）、4 种 Mode（BUILD/READ_ONLY/PLAN/BYPASS）。核心设计是 fail-closed——如果 mode 没有配置对应的权限 profile，默认返回一个空能力集的 fail_closed profile，拒绝一切操作。配置缺失不应等于全通。

第二层是 CommandGuard，专门解决"正则黑名单可以被绕过"的问题。除了 59 个危险命令正则模式外，我加了 18 个扩展模式覆盖绕过变体（如 rm -fr vs rm -rf 的 flag 重排、$IFS 变量空格绕过、反斜杠逃逸命令名），还对 7 个高危命令做了 argv 语义级检查——timeout 5 rm -rf / 这种包装攻击会被递归检查被包装的命令。但我必须诚实地说，CommandGuard 文档自身定性为"guardrail, not boundary"——正则命令检查在根本上是可以绕过的（Claude Code 2025 年的 CVE 已经证明了这一点）。真正的硬边界在第三层。

第三层是进程级隔离。双后端设计——ProcessBackend 用独立进程组 + cgroup v2（memory.max、swap.max=0 禁用 swap、cpu.max 配额），DockerBackend 用容器级隔离（--network none 无网络、-v 仅挂载 workspace、--rm 自动清理）。统一 ExecutionBackend Protocol 切换。cgroup 不可用时降级为无限制但打 degraded 事件，Docker 不可用时直接抛 RuntimeError 而不是静默退回 ProcessBackend——静默降级会丢失用户期望的容器隔离。

旁路防线包括细粒度工具权限（每个工具绑定 Capability 和 RiskLevel，按 mode 的权限 profile 决策）、受控只读浏览器（7 个只读工具 + URL 白名单 + 默认关闭）、人工审批链路（fail-closed 默认 N，非交互环境 UNAVAILABLE 等价拒绝，参数自动脱敏）。

---

### 追问 1：三层防线是不是太多了？去掉一层会怎样？

**回答（~250 字）：**

三层防线遵循"纵深防御"原则——没有单层是完美的，但组合起来让攻击面大幅缩小。每层去掉后的后果不同。

去掉第一层（权限+fail-closed）——CommandGuard 拦截了危险命令，Bash 工具仍然需要经过 deny 检查，但 Read/Write 等文件工具失去了 capability 保护。一个 READ_ONLY mode 的 agent 仍然可以写文件，因为 READ_ONLY 的限制来自第一层的 capability 检查而非第二层的命令检查。

去掉第二层（CommandGuard）——第一层还有命令黑名单，但黑名单是正则匹配且只有 42 个 + 扩展 18 个模式。rm -fr / 这种 flag 重排、timeout 5 rm -rf / 这种包装攻击会直接通过黑名单，因为没有 argv 语义检查来做递归分析。第三层 sandbox 能限制破坏范围但无法阻止 workspace 内的破坏。

去掉第三层（sandbox）——Docker 隔离的缺失意味着 agent 进程有完整的宿主机文件系统和网络访问。即使有两层软防护，Bash 命令的任何逃逸都会导致宿主机沦陷。这就是为什么第三层被定义为"the real boundary"。

面试官可能会追问"会不会过度设计"——我的回答是：这是 AI coding agent，能执行任意命令。安全不是功能需求，是生存条件。

---

### 追问 2：fail-closed 具体怎么实现的？和 fail-open 的区别在哪里？

**回答（~200 字）：**

fail-closed 在三个层面体现。权限维度——ModePolicy 的 permission_profile 属性在找不到 mode 对应配置时，返回一个 `allowed_capabilities=frozenset()` 的空 profile，任何需要 Capability 的工具都会被 DENY。这就是"配置缺失则拒绝一切"。

审批维度——FailClosedApprovalHandler 永远返回 UNAVAILABLE，在 AgentLoop 的审批接线中 UNAVAILABLE 等价于拒绝（pre_denied_error_type="approval_unavailable"）。CLI 交互式审批的默认答案是 N——用户按一个回车不做选择等价于拒绝。

沙箱维度——DockerBackend 不可用时，build_sandbox_from_config 直接抛 RuntimeError，不会静默退回 ProcessBackend。ProcessBackend 的 cgroup 不可用时降级为无限制运行但打 degraded 事件——这里是 degrade but alert，不是 silent fail-open。

和 fail-open 的核心区别：fail-open 在异常路径上"宁可放行不错杀"，fail-closed 是"宁可错杀不放行"。对一个能执行任意命令的 AI agent 来说，后者是唯一合理的默认。

---

### 追问 3：CommandGuard 是 guardrail 不是 boundary，为什么还要做？

**回答（~200 字）：**

因为深度防御的第一原则就是"不要让单层承担全部责任"。

CommandGuard 要做的是拦截 95% 的常见攻击变体，让剩下的 5% 由 sandbox 兜底。如果在第一层就全放过，sandbox 的压力会大得多——比如 rm -rf / 和 fork bomb 这些明显有害的命令，不应该让 cgroup/Docker 来拦，应该在语义层面就直接拒绝。而且 sandbox 拦截意味着进程已经启动了，性能开销和副作用已经产生了。

另一个价值是可观测性——CommandGuard 的 deny 事件通过 SandboxEventSink 写入 trace，比 sandbox kill 事件更容易分析。运维层面可以回答"上周有多少次命令被拦截"这类问题，sandbox kill 很难区分"恶意攻击"和"普通超时"。

说白了——正则命令检查确实不是安全边界，但它是一个极低成本、极高收益的预过滤器。好比机场安检的金属探测门不是绝对安全（陶瓷刀能过），但不能因为它不完美就不装。

---

### 追问 4：受控浏览器是怎么做安全的？和浏览器沙箱有区别吗？

**回答（~200 字）：**

首先要澄清术语——这不叫"浏览器沙箱"。沙箱意味着进程级隔离——cgroup 或 Docker。Asterwynd 的浏览器是 Playwright 驱动的真实 Chromium，运行在宿主机上，没有容器包装。它的安全依赖的是策略护栏而非执行隔离。

URL 白名单是第一道防线：空白名单 = 拒绝所有 URL，http 只能被显式白名单放行（强制 HTTPS），域名匹配支持精确和通配符两种模式。BrowserSession 的每次 navigate 操作都被 BrowserPolicy.assert_url_allowed 拦截。

只读工具集是第二道防线：7 个浏览器工具全部是 read-only——导航、获取内容、截图、滚动、标签管理。没有表单填写、文件上传、数据提交。当然这里有个现实的局限——只读是"工具层面"的。如果一个页面有 JavaScript 能访问 Playwright 的 API，理论上仍可能突破。但 URL 白名单大幅缩小了这个攻击面——agent 只能访问你明确允许的域名。

浏览器默认关闭（config.enabled=False），需要用户显式开启并配置白名单。惰性启动意味着只在首次浏览器工具调用时才启动 Chromium，不做无谓初始化。

---

### 追问 5：如果有 MCP 工具接入，怎么保证它的安全？

**回答（~150 字）：**

MCP 工具是外部注入的，不在 Asterwynd 的编译时安全控制范围内，这是一个真实的风险面。当前有三层保护：MCP 工具在注册时被分配 ToolOrigin.MCP，权限级别默认是 HIGH——所有 MCP 工具都需要审批才能执行，在 BUILD mode 下也不例外。MCP 工具权限走相同的 ModePolicy 决策链——如果 mode 的 profile 不允许 EXTERNAL_SIDE_EFFECT capability，MCP 工具直接 DENY。命令型 MCP 工具如果在执行侧调了 Bash，仍然受 CommandGuard 和 sandbox 约束。

但 MCP 工具的安全确实是当前最薄弱的环节——一个恶意的 MCP 服务端可以伪造 description 让模型频繁调用它、可以做数据外泄。这也是为什么 MCP 工具默认标记为 HIGH 风险 + EXTERNAL_SIDE_EFFECT capability——它的安全假设是"不可信"。

---

## Bullet 7 面试讲稿：全链路可观测体系与 Benchmark

> 建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；72 个 coding 任务（34 本地 = 22 A 轨回归基线 + 12 B 轨当前演进 + 38 SWE-bench Verified 子集）在 git worktree / Docker 隔离执行，pass@1/pass^k/成本（cache-aware）与 fault_owner 归因统计，场景×难度分层覆盖矩阵，支持跨 Agent 配对比较与 CI 回归门禁

---

### 主讲述稿（~450 字）

可观测体系和 Benchmark 评测闭环是我认为做 Agent 框架必须有的东西——没有数据，所有优化都是拍脑袋。

可观测侧有三个组件。TraceRecorder 是全链轨迹记录器，定义了 18 种事件类型——run 开始、LLM 调用、工具调用和结果、沙箱事件、审批请求和响应、文件编辑、内存压缩等。每个事件携带时间戳和结构化 data，最终序列化为 JSON 写入文件。我特别关注了 benchmark 场景——runner 为每个 task 创建独立 TraceRecorder 实例，注入 task_id，基准测试结果可以逐 task 追溯。

CostLedger 是成本归因系统，bill 方法返回三层聚合——by_session 按会话、by_phase 按运行阶段（building/review/planning/bypass）、by_tool 按工具。定价表是 cache-aware 四档（fresh input / cache read / cache write / output），按前缀匹配计算成本，覆盖 17 个主流模型。Ledger 通过 JSONL 持久化，支持增量 flush。三层归因的价值在于——你可以回答"review 阶段的成本占比是多少"、"哪个工具消耗了最多的 token"。

ErrorClassifier 是错误自动打标，5 大类：PERMISSION_DENIED、NETWORK_TIMEOUT、MODEL_ERROR、PARAMETER_ERROR、UNKNOWN。三级优先级分类——结构化 error_type 最优先（17 条映射），finish_reason 次之，文本正则 fallback 兜底。我用的是确定性规则而非 LLM 分类，保证打标的稳定性和零成本。

Benchmark 评测侧，72 个 coding 任务——34 个本地任务分双轨（22 个 A 轨历史重建回归基线 + 12 个 B 轨当前演进），38 个 SWE-bench Verified 子集覆盖 requests/flask/pytest/sympy/seaborn/pylint 外部仓库。本地任务通过 git worktree 隔离执行，task 文件隐藏防止作弊；SWE-bench 通过 SwebenchAdapter 调用官方 Docker 验证器。指标分三层：pass@1 是用户实际获得的有效轮通过率，pass@k 是能力上限，pass^k 是全部有效轮成功的可靠性；成本用 cache-aware 定价算 $/resolved-task，失败轮次用 reason × fault_owner 交叉表归因。任务按 scenario × difficulty 双标签分层，套件级能力覆盖矩阵机械校验；跨 Agent 对比用配对统计（per-task delta + 差异 CI + win-rate）。CI 回归门禁检查 success_rate 绝对下降不超过 5pp 和 p95 延迟回归不超过 5%。

---

### 追问 1：为什么不直接用 Langfuse / OpenTelemetry 而是自己实现？

**回答（~250 字）：**

三个原因。第一是零外部依赖——Asterwynd 的定位是 pip install 即可用，不要求用户部署一个 Langfuse 服务器或配置 OpenTelemetry collector。对于一个单机开发工具来说，依赖外部可观测平台是过重的。

第二是结构化深于通用框架——我的事件类型不是泛化的"LLM call + metadata"，而是精确到"并行工具执行开始""压缩前后 token 变化""审批被拒"。这些事件的 schema 和 AgentLoop 的内部状态紧密耦合。可以类比——Langfuse 给你的是"HTTP request trace"，我给你的是"函数级 execution trace"。

第三是 benchmark 集成——TraceRecorder 的 task_id 注入、runner 的 diff snapshot、测试执行记录，这些都是 benchmark 评测闭环的一部分，不是独立的可观测。把 trace 和 benchmark 产出放在同一个 task 目录下（trace.json 和 result.json），后续分析不需要跨系统关联。

如果未来需要对接企业级可观测平台，TraceRecorder 的 to_dict 输出可以直接适配 OpenTelemetry span exporter。

---

### 追问 2：CostLedger 的价格表硬编码了，模型更新或降价了怎么办？

**回答（~150 字）：**

承认——当前 MODEL_PRICES 是硬编码常量，模型更新需要改源码。这是有意为之的简单设计——17 个模型的四档定价表维护成本极低，而且定价不是实时变化的数据。价格变动一年几次，动态加载（配置缺失、格式错误、恶意注入）的复杂度超过收益。

评测升级后定价表变成 cache-aware 四档（fresh / cache read / cache write / output），并带 `PRICING_TABLE_VERSION` 版本号写进报告元组——即便价格调整，报告仍能追溯到用的是哪一版定价口径。这比"过期定价"更致命的是"不知道用的是哪版定价"。

更重要的设计是 CostLedger 和 TraceRecorder 解耦——即便定价表过期，token 消耗数据仍然准确，只是换算成美元的部分需要手动修正。token 数据是永久正确的。

---

### 追问 3：34 个本地任务怎么设计出来的？A 轨和 B 轨怎么分工？

**回答（~250 字）：**

34 个本地任务分双轨。**A 轨是历史重建回归基线（22 个）**——从本仓库 2026-06 前合入特性的 git 历史重建，任务是"回到过去改同一个 bug / 加同一个功能"，验证命令是确定性的 pytest。它的定位是回归基线而非公平评测：agent 在完整 git 历史里运行，base_commit 之后的提交可见，有答案泄漏面，所以结果页必须披露"A 轨非公平评测"。

**B 轨是当前演进（12 个）**——基于当前 HEAD 的真实缺陷和增强构造，是面试核心。覆盖面包括沙箱执行器、benchmark CLI、LSP diagnostics、ListRunningBenchmarks 只读工具装配链、statechart 新态、结果页 track 分组、SwebenchAdapter model name 转义回归、memory project scope 隔离、记忆注入归属下沉等。B 轨任务刻意不给文件路径，只给行为症状，agent 需要自己通读管线定位；验证是确定性 test_command + test.patch 新增回归断言，base 红/gold 绿可复现。

关键设计是每个任务有可自动验证的正确性标准，且 task 文件在 agent 执行前被移动到 .hidden 目录——防止 agent 读取测试文件"作弊"。worktree 隔离保证任务间的文件变更不互相污染。

---

### 追问 4：Gate 的门禁指标为什么是 5pp success_rate 和 5% p95？不是更严？

**回答（~200 字）：**

5pp 和 5% 是 CI 门禁的"防退步底线"，不是"质量目标"。门禁要做的是拦截显著的回归——改一行代码导致 10% 的任务失败，那就肯定有问题。但如果严格要求 success_rate 不下降，会导致两个问题：第一是假阳性——模型 API 本身有非确定性，同一任务同一配置跑两次结果可能略有不同，严格不下降会导致 CI 频繁误报；第二是抑制改进——有些重构可能稍微降低某个边缘 case 的通过率但整体架构改善很多，5pp 的门槛允许合理权衡。

p95 延迟还有特殊处理——当 baseline p95 < 1s 时，用绝对 floor 1s 代替相对 fraction。因为 sub-second 任务的相对波动（0.3s→0.4s 就是 33%）没有实际意义，可能是随机噪声。abs_p95_floor 解决了这个"sub-second baseline 不适用相对比较"的计量问题。

---

### 追问 5：Benchmark 结果怎么跟其他 Agent 对比？

**回答（~200 字）：**

对比的核心原则是**同任务、同 harness、仅换一个变量**——换 agent 对照（Asterwynd vs 参照 agent）和换 model 对照（本地主力 vs API 前沿）分开写，数字仅在同一 harness 内可比。

compare.py 是独立 CLI，输入是多个 run 目录，输出 Markdown 和 HTML 对比报告。当输入恰好两个 run 时，追加**配对比较段**：per-task delta（同一任务上 A 的 pass@1 减 B 的 pass@1）、差异 95% CI（paired bootstrap——重采样时同一任务索引同时读两侧，保持配对性，否则方差会高估）、win-rate（A 胜/B 胜/平的任务数）、McNemar 检验（在 pass^k 布尔上做 exact-binomial 显著性）。SWE-bench 任务使用官方验证器（swebench.harness.run_evaluation）确保判定标准一致。

目前的局限是仅支持文件级 run 目录对比，没有 Web dashboard。这适合 CI 集成和本地对比，不适合对外公开展示——这也是后续可以做的一个方向。

---

### 追问 6：pass@1、pass@k、pass^k 有什么区别？为什么成本要用 cache-aware 定价？

**回答（~200 字）：**

三个指标回答三个不同的问题。**pass@1** 是用户实际获得的——把有效轮次里通过的比例直接算出来，它是"开箱即用的体验"。**pass@k** 是能力上限——同一个任务跑 k 次至少一次通过的组合概率（Chen et al. 2021），回答"如果允许重试，这个 agent 能不能解决"。**pass^k** 是可靠性——要求一个任务的全部有效轮都通过才算成功，回答"能不能稳定复现"，这是 CI 门禁和工程交付最关心的。

成本为什么用 cache-aware 定价？因为 Agent 系统的真实账单里 cache hit 占比很高——稳定前缀（system + 工具 schema）每轮重复发送，命中 cache 的价格只有 fresh input 的 10%。如果只用两档定价，同一任务不同前缀命中率的成本会被系统性低估或高估，$/resolved-task 就不可比。四档定价（fresh / cache read / cache write / output）+ `PRICING_TABLE_VERSION` 版本戳，让成本数字可追溯、可复现。
