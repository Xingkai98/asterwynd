# Bullet 3 面试讲稿：多 Agent 编排模式

> 内置 4 种多 Agent 编排模式（orchestrator-worker / peer-review / hierarchical / bidding）+ 子 agent 消息总线、token/时间双维度预算硬 kill 与快照恢复

---

## 主讲述稿（~400 字）

多 Agent 编排是我在 Asterwynd 里实现的协作层，让一个主 agent 能 spawn 多个子 agent 协同完成任务。代码在 `agent/subagent/` 目录，四个核心模块。

关键是 4 种编排模式，在 `patterns.py` 里通过 `PATTERNS` 注册表管理。Orchestrator-Worker 最直接——fan-out 到 N 个并行 worker，所有 worker 执行相同任务，最后 aggregate 结果。Peer-Review 是 producer-reviewer 对——producer 产出方案，reviewer 评审，最多 3 轮迭代，reviewer 回复 "APPROVED" 才通过。Hierarchical 是 N 个 manager 各自带团队，manager 可以继续 spawn worker，形成树状工作组，深度上限 3 层。Bidding 是 N 个 proposer 独立出方案，一个 selector 选最佳——它的 proposal 传递故意不走消息总线，因为总线的 drop-oldest 策略可能丢关键竞标。

消息总线是子 agent 间的通信层——每个编排 run 创建一个 MessageBus 实例，子 agent 通过 PublishBusMessage/ReadBus 两个工具交换语义摘要。总线有三层 token 预算控制——容量上限 100 条、发布端 LLM 摘要压缩到 400 token、消费端从最新消息往前截断。

预算硬 kill 是我比较满意的一个设计——token 超限在 LLM 调用后立即被 hook 检测并抛异常终止，时间超限用独立协程 asyncio.sleep 后 cancel 跑趟 task，处理的是工具卡死的场景。两条路径都先写 checkpoint 再杀。

---

## 追问 1：4 种编排模式是怎么选出来的？为什么是这 4 种不是别的？

**回答（~250 字）：**

这 4 种模式覆盖了多 Agent 协作的几个核心拓扑结构，每个对应一类真实需求。

Orchestrator-Worker 是最基础的并行化——"把这件事做 N 遍取最佳"，对应代码生成里的并行采样或数据处理的 map-reduce。它的假设是 worker 之间不需要通信，任务天然可并行。

Peer-Review 对应质量控制——"你写我审，通过为止"。核心价值是用一个 reviewer 来校准 producer，对代码 review、方案评审特别有效。最多 3 轮是为了平衡质量和成本。

Hierarchical 对应大规模分解——"一个人管不过来，分给多个组长各自带团队"。适合需要多维度并行探索的场景，比如同时调研多个技术方案。

Bidding 对应方案竞选——"N 个人出方案，一个人拍板"。与 Orchestrator-Worker 不同，proposer 各自出不同方案而非相同答案，selector 做选择。适合架构设计这种没有标准答案的任务。

这 4 种模式不是随意选的——每个对应一类拓扑（fan-out、feedback loop、tree、competition），覆盖了多 Agent 协作的主要范式。

---

## 追问 2：消息总线的"三层 token 预算"具体怎么工作的？

**回答（~250 字）：**

三层预算是自底向上递进的，从量限制到质量压缩。

第一层是容量限制——bounded queue 最多 100 条消息，溢出用 drop-oldest 策略。这个设计牺牲了完整性保预算，所以 bidding 模式故意不走 bus——它的竞标信息必须全量保留。

第二层是发布端摘要压缩——每个 agent 调用 PublishBusMessage 时，如果内容超过 400 token，自动调 LLM 做摘要再入队。不可用 LLM 时退化到字符截断。这意味着总线上流动的是"结论"而非"过程"——子 agent 的完整思考过程在 transcript 里，总线上只放关键发现。

第三层是消费端 token 窗口——agent 调用 ReadBus 时从最新消息往前累加，直到达到 token 上限（默认 2000）。单条超预算也保留最新一条——不让消费者错过最重要的信息。返回时 oldest-first 排列，保持时间顺序可读。

三层加在一起，把"N 个 agent 的原始对话"压缩到"几千 token 的结构化摘要"，不过度消耗主 agent 的 context window。

---

## 追问 3：Token 超限和时间超限两条 kill 路径有什么区别？为什么需要两套机制？

**回答（~200 字）：**

两套机制处理的是完全不同的超标场景。

Token 超限是在 LLM 调用边界被检测到的——每次 LLM 返回后 BudgetHook 累加 input+output tokens，超过限制立即抛 BudgetExceededError。这需要在能执行代码的 hook 层触发，因为只有那里能读到 usage 信息。

时间超限的场景是工具卡死——比如 Bash 命令 hang 住了，hook 永远等不到触发。这时候需要一个外部 watcher——独立的 asyncio 协程 sleep 到 timeout 时间后，检查 run 是否还在活跃，如果是就 cancel 跑趟 task。

关键设计是两个路径的执行顺序——先标记 `_budget_kill_reason`，再写 checkpoint，最后才 cancel 或抛异常。这样被取消后的 handler 能区分"这是预算杀"还是"用户手动取消"，终止状态分别标记为 `budget_exceeded` 和 `cancelled`。

两套机制也可以同时配置——token 预算防止烧钱，时间预算防止卡死。

---

## 追问 4：子 agent 的快照和主 agent 的快照是同一套机制吗？

**回答（~150 字）：**

底层存储复用同一个 SessionStore——相同的 schema_version 兼容、SHA-256 去重、tmp+rename 原子写入——但存储路径和恢复逻辑是独立的。子 agent 快照存在 `<workspace>/.asterwynd/subagents/<run_id>/`，key 是完整 run_id 而非短 subagent_id。

区别在于快照内容——子 agent 快照额外携带 objective、blockers、next_steps、bus_summary 这些编排字段。恢复也是 transcript 级——快照把对话历史重建后，从 iteration 0 重新循环，不恢复 Python 调用栈。

子 agent 有自己的 ResumeSubagent 工具，主 agent 可以通过它主动恢复任何有 checkpoint 的已中断 run。
