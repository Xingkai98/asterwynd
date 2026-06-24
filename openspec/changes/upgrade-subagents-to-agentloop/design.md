## Context

当前 `SubAgentManager` 只是后台调用一次 `llm.chat`，不能执行工具循环，也不能产出与主 agent 一致的 trace、mode 和运行时事件。它适合轻量问答，但不能承担并行调查代码、读取文件、运行受限工具或持续编排多个子问题的 coding-agent 子任务。

本 change 不再把 subagent 视为“一次性后台 helper”，而是把它升级为 **完整的子 session runtime**：

- 子 agent 是一个不直接和用户交互的受限子 session。
- 子 session 可以存在多个，并发运行。
- 一个子 session 可以承载多次 run。
- 父 agent 通过显式运行时接口管理子 session，而不是把子结果直接塞回父 messages。

## Goals / Non-Goals

**Goals:**

- 子 agent SHALL 建模为受限子 session，而不是一次性 LLM 委托。
- 子 session SHALL 拥有独立 transcript、mode、run 历史、trace 和工具集合。
- 系统 SHALL 支持同时存在多个子 session，并允许跨 session 并发运行。
- 父 agent SHALL 通过显式运行时接口创建、运行、查询、等待、取消和检查子 session。
- 子 session 的结果、摘要、usage 和 trace 关联 SHALL 结构化暴露，而不破坏父 AgentLoop 的 tool-call 消息链。
- 本设计 SHALL 同时兼容 CLI、Web，并为未来 TUI 预留 inspect/focus 能力。

**Non-Goals:**

- 不实现跨进程 worker。
- 不实现分布式任务队列。
- 不在本 change 中实现用户直接切入子 session 聊天。
- 不默认支持 `fork parent transcript`。
- 不实现 OpenClaw 那种 announce retry、orphan recovery、thread binding 和多通道路由恢复机制。
- 不让子 agent 绕过父 agent 的 mode 和工具权限。

## 参考实现对照

### Hermes：清晰的 isolated 委托边界

Hermes 的 `delegate_task` 把子 agent 视为带独立上下文的委托执行单元：

- 子 agent 默认全新上下文，只吃 `goal/context`。
- 父 agent 只拿最终摘要，不拿中间 tool 流。
- 支持并发批量委托和父取消传播。

可借鉴点：

- `isolated` 默认值。
- 父只消费摘要和结果，而不是吞整份子 transcript。
- 独立预算、独立工具权限。

不直接照搬的点：

- Hermes 更像“强委托工具”，而不是完整子 session runtime。
- 它没有把“子 session 可多次 run”作为一等模型。

### Nanobot：真实 child runtime 骨架

Nanobot 的 `SubagentManager` 已经不是一次性 `llm.chat`，而是真正跑 child loop：

- `spawn -> _run_subagent -> AgentLoop.run` 形成完整 child runtime 链。
- 子 agent 单独构造 tool registry。
- 有显式 `SubagentStatus`、usage、tool event 和 announce 逻辑。

可借鉴点：

- 子 agent 必须复用真实 AgentLoop，而不是维护第二套轻量循环。
- 子运行时要有显式状态对象，而不是只留字符串结果。
- 工具、workspace、trace 和取消都要在 child runtime 内部闭环。

不直接照搬的点：

- Nanobot 目前更像“带状态的后台子任务运行器”。
- 它没有完整展开为“持久子 session + 多次 run”的运行时模型。

### OpenClaw：最接近的 session/runtime 分层

OpenClaw 的 sub-agent 最接近本 change 想达成的结构：

- 子 agent 运行在自己的 session。
- `sessions_spawn` 和 `sessions_yield` 明确区分了 spawn 与等待/回传。
- 有独立 inspect 入口，如 `/subagents list`、`info`、`log`。
- 支持 `isolated / fork` 等上下文模式。

可借鉴点：

- 子 agent 作为 session identity，而不是一次性 helper。
- 父子交互通过显式运行时接口完成。
- transcript、状态、结果和 inspect 是独立能力，而不是消息链 hack。

不直接照搬的点：

- OpenClaw 的 announce、retry、registry、thread binding、恢复机制太重。
- 本 change 先不实现 push-based completion handoff，也不实现复杂路由恢复。

### Claude Code：fork worker 路线，不作为主参考

Claude Code 的 `forkedAgent` / `forkSubagent` 更强调：

- 继承父上下文。
- 利用 prompt cache。
- 权限和上下文尽量与父保持一致。

这条路线适合“fork worker”，但不适合作为本 change 的默认模型，因为：

- 它会模糊父子 transcript 边界。
- 它会抬高 token 成本和运行时耦合度。
- 它不适合本项目当前要优先强调的 runtime clarity。

### 两层模型：目标委托型与运行时管理型并存

参考实现里并不只有一种 subagent 交互方式，而是常见地分成两层：

- **目标委托型**：父 agent 给子 agent 一个目标和较长 briefing，让它自主完成任务后回报结果。Claude Code 的 `Explore` / `Plan` / `verification`，以及 Hermes 的 `delegate_task` 都偏这一路线。
- **运行时管理型**：父 agent 把子 agent 视为 session/runtime object，显式执行创建、运行、查询、等待、取消和 inspect。OpenClaw 最典型，Claude Code 的 resume/continue 能力也带有这一层。

本 change 当前优先建设的是**底层运行时管理型**，而不是立即把 `Explore` 这类高层角色化 agent 一起做完。

## 设计结论

本 change 采用以下折中：

- 借鉴 OpenClaw 的 **子 session identity + 显式运行时接口**。
- 借鉴 Nanobot 的 **真实 child AgentLoop 骨架**。
- 借鉴 Hermes 的 **isolated 默认上下文**。
- 明确不走 Claude Code 那种 **默认 fork 全量父 transcript** 路线。

如果一句话概括，本设计是：

> 不是一次性 delegate，也不是重型 announce/session orchestration，而是一个受限的 child-session runtime：先把 session identity、child AgentLoop、多次 run 和显式 inspect 接口建清楚。

## Decisions

### Decision 1: 子 agent 建模为完整子 session

子 agent SHALL 被建模为不直接和用户交互的子 session，而不是一次性子任务对象。

每个子 session SHALL 至少拥有：

- `subagent_id`
- 独立 transcript
- 当前 session mode
- run 历史
- 当前运行状态
- trace / usage / artifact 关联

理由：

- “子 agent = 子 session，子 run = 子 session 中的一次运行”比“一次性 helper”更符合长期演进方向。
- 这样 CLI、Web、未来 TUI 都能围绕同一个运行时对象工作。

### Decision 2: 子 session 支持多次 run，并允许多个子 session 并发存在

本 change SHALL 支持：

- 同时存在多个子 session。
- 在同一个子 session 中发起多次 run。

同时，系统 SHALL 施加保守边界：

- 多个子 session 可以并发运行；同一子 session 内的子 run 必须串行。
- 父取消或显式取消操作 SHALL 只影响目标子 run。

理由：

- 并发多个子 agent 是 subagent 机制的核心价值之一。
- 多次 run 是“完整子 session runtime”与“单次后台任务”之间的关键分水岭。

### Decision 3: 默认只支持 isolated 子上下文

子 session 默认 SHALL 使用 `isolated` 上下文。

本 change SHALL NOT 默认支持 `fork parent transcript`。

这里的“fork”专指：复制父 session 的 message transcript 作为子 session 启动前缀，而不是复制整个父运行时实例。

理由：

- `isolated` 边界最清楚，最适合当前阶段控制复杂度。
- 父 agent 必须显式传入 `task/context`，可避免把噪音 transcript 一并带入 child runtime。
- 等未来 session 持久化和 inspect 能力成熟后，再扩展 `fork` 更稳妥。

### Decision 4: 父子交互走显式运行时接口，不走自动注入

父 session SHALL 通过显式运行时接口管理子 session，例如：

- 创建子 agent
- 启动子 run
- 查询子 agent
- 列出子 agents
- 查询子 run 结果
- 等待子 run
- 取消子 run
- 设置子 agent mode
- 查看子 transcript 摘要
- 查看子 run 最近消息

本 change SHALL NOT：

- 自动把子结果注入父当前 messages。
- 自动把子 transcript 合并进父 transcript。
- 通过伪造 tool result 的方式把子 session 嵌进父 tool-call 链。

`ParentChannel` 在本设计中仍可保留，但 SHALL 被视为内部 runtime channel，而不是“直接向父 messages 追加 tool result”的公共语义。

理由：

- 显式运行时接口更稳，不破坏父 AgentLoop 的协议约束。
- 这种模型更容易统一到 CLI、Web 和未来 TUI。

### Decision 5: 子 session 维护完整 transcript，父默认只读结构化摘录

子 session SHALL 维护自己的完整 transcript。

父 session 默认可读取：

- 当前状态
- 最近一次 run 的结构化结果
- 摘要
- artifact 引用
- usage
- `run_id`

父 session SHALL NOT 默认读取整份子 transcript。

若父确实需要查看 transcript，本 change SHALL 通过单独的 inspect 操作提供**有边界的读取**，例如：

- transcript 摘要
- 某次 run 最近 `N` 条消息
- 可选是否包含 tool result

理由：

- 控制 token 成本。
- 保持父子边界。
- 为未来安全、产品展示和更细粒度权限控制预留空间。

### Decision 6: 子 session 具有 session 级 mode，mode 变更只影响后续 run

子 session SHALL 拥有自己的 session 级 mode。

规则如下：

- 创建子 session 时确定初始 mode。
- 后续多次 run 默认复用当前子 session mode。
- 父 agent 可以显式修改子 session mode。
- mode 变更 SHALL 只影响后续 run，不影响当前已在运行的子 run。
- 子 session mode SHALL NOT 高于父 session mode。

理由：

- 这与主 session 当前的 mode 语义保持一致。
- 多次 run 的子 session 只有拥有 session 级 mode 才有稳定语义。

### Decision 7: 结果模型使用 `subagent_id + run_id`，不额外引入 `trace_id`

本 change 中：

- `subagent_id` 标识子 session。
- `run_id` 标识某次具体子运行。
- trace SHALL 通过 `run_id` 关联。
- 若需要跨 UI / 日志定位，可附带 `session_id`。

本 change SHALL NOT 额外引入新的 `trace_id` 概念。

子 run 结果建议至少包含：

- `status`
- `summary`
- `reason`
- `artifacts`
- `usage`
- `run_id`

其中：

- 判断状态读 `status`
- 看细节读 `reason`

理由：

- 本仓库现有运行时已经区分 `session_id` 和 `run_id`。
- 引入独立 `trace_id` 只会增加一层无必要映射。

### Decision 8: 子 session 不直接对用户开放交互

即使子 session 是完整 session runtime，本 change 仍 SHALL 限定：

- 子 session 不直接接受用户输入。
- 用户不直接切入子 session 与其对话。
- 子 session 只能由父 agent 通过专用运行时接口驱动。

理由：

- 先把子 session runtime 做完整，比同时引入“用户直接切换子会话”更可控。
- 这能保留清晰的 orchestrator/worker 分层。

### Decision 9: 本 change 先做底层子 session runtime，不做高层角色化子 agent

本 change SHALL 优先实现底层运行时能力：

- 子 session identity
- 多次 run
- 显式运行时接口
- transcript / 状态 / 结果 inspect

本 change SHALL NOT 同时把 `Explore` / `Plan` / `verification` 这类高层角色化子 agent 一并做完。

未来若要增加高层角色化子 agent，它们 SHOULD 建立在本次完成的子 session runtime 之上，而不是另起一套独立委托机制。

理由：

- 运行时地基与角色化 agent 是两层问题，混做会显著拉高范围和耦合度。
- 先把底层 runtime 做稳，更符合当前项目“面试可解释的 Agent runtime”主线。

### Decision 10: 区分 LLM 可见工具面与 CLI/Web 内部接口

子 session runtime 的能力 SHALL 区分两层暴露：

- **父 agent 可直接调用的 LLM 工具**
  - `CreateSubagent`
  - `RunSubagent`
  - `ListSubagents`
  - `GetSubagentRun`
  - `CancelSubagentRun`
  - `InspectSubagentTranscript`
- **CLI / Web 内部接口**
  - `GetSubagent`
  - 更细的 session 元数据读取

其中，`GetSubagent` 本 change 中 SHALL 先不直接暴露给 LLM。

理由：

- 父 agent 编排真正需要的是“创建、运行、拿结果、取消、受限 inspect”这一闭环，不一定需要完整 session 元数据对象。
- CLI / Web 对状态展示和调试有更细粒度需求，应保留内部接口，但不必一开始就把所有运行时对象直接暴露给模型。

### Decision 11: `CreateSubagent` 与 `RunSubagent` 严格分层

本 change 中：

- `CreateSubagent` SHALL 只负责创建空的子 session。
- `CreateSubagent` MAY 接收初始元数据，如 `name`、`description`、初始 `mode`。
- `CreateSubagent` SHALL NOT 自动启动子 run。
- `RunSubagent` SHALL 只负责在已有 `subagent_id` 上发起一次新的子 run。
- `RunSubagent` SHALL 显式接收本次 run 的 `task`，并 MAY 接收 `wait`、`timeout` 等 run 级参数。

理由：

- 这与“子 agent = 子 session，子 run = 子 session 中的一次运行”的建模保持一致。
- 如果把创建 session 和启动 run 混在一起，多次 run 的语义会变弱，也会把工具接口做脏。
- CLI / Web 也更容易围绕这组稳定分层复用。

### Decision 12: 等待能力作为参数语义内建在运行时工具中

本 change SHALL NOT 额外引入独立的 `WaitSubagentRun` 工具。

等待语义 SHALL 作为参数能力内建在：

- `RunSubagent(wait=true, timeout_s=...)`
- `GetSubagentRun(wait=true, timeout_s=...)`

规则如下：

- 当 `wait=false` 时，工具立即返回 `subagent_id`、`run_id` 和当前状态。
- 当 `wait=true` 时，工具等待该次 run 进入终态或达到超时，然后返回终态结果或超时状态。

理由：

- 这能减少工具数量，同时保留清晰的运行时语义。
- 对父 agent 的编排足够自然，不需要额外学习一把专门的等待工具。
- CLI / Web 若需要更复杂的等待或订阅逻辑，仍可通过内部接口自行实现。

### Decision 13: session、run result、transcript inspect 使用三类返回结构

本 change SHALL 不尝试用一个通用 schema 覆盖所有子 session 工具，而是按职责划分三类返回结构。

#### `CreateSubagent`

`CreateSubagent` 返回最小子 session 标识信息，例如：

- `subagent_id`
- `name`
- `mode`
- `status`
- `created_at`

#### `RunSubagent` 与 `GetSubagentRun`

`RunSubagent` 与 `GetSubagentRun` SHALL 返回同构的子 run 结果 envelope，例如：

- `subagent_id`
- `run_id`
- `status`
- `summary`
- `reason`
- `usage`
- `artifacts`

规则如下：

- 当 `wait=false` 时，`status` 通常为 `running`，其余字段 MAY 为空或部分为空。
- 当 `wait=true` 或查询到终态 run 时，工具 SHALL 返回终态结构化结果。

其中：

- 判断状态读 `status`
- 看细节读 `reason`

#### `InspectSubagentTranscript`

`InspectSubagentTranscript` SHALL 使用单独的受限 inspect 结构，例如：

- `subagent_id`
- `run_id`（可选）
- `scope`（如 `summary` 或 `recent_messages`）
- `summary` 或 `messages`
- `truncated`
- `included_tool_results`

理由：

- session 创建、run 结果、transcript inspect 是三类不同职责，硬塞进一个 schema 会让调用方和模型都变得模糊。
- `RunSubagent` 与 `GetSubagentRun` 返回同构结构，能显著降低模型记忆成本。

### Decision 14: 单子 session 内 run 串行，跨子 session 允许并发

本 change SHALL 允许多个子 session 并发存在和并发运行。

但对于同一个 `subagent_id`：

- 任一时刻 SHALL 最多只有一个 active run。
- 若该子 session 已存在运行中的子 run，则新的 `RunSubagent` 调用 SHALL 被拒绝，或要求先等待/取消当前 run。

理由：

- 子 session 的 transcript、mode 和状态是 session 级共享状态。
- 若同一子 session 同时存在多个 active run，会立刻引入消息交错、trace 归属和 mode 语义混乱。
- 第一版 runtime 保持“跨 session 并发、单 session 串行”能覆盖主要价值，同时控制复杂度。

## Risks / Trade-offs

- [Risk] 作用域膨胀。  
  Mitigation: 明确本 change 只做 in-process child-session runtime，不做跨进程、路由恢复和用户直连子 session。

- [Risk] 多个子 session 并发导致 token、trace 和状态管理复杂度上升。  
  Mitigation: 引入显式状态模型、同 session run 串行化、取消语义和结构化 inspect 接口。

- [Risk] 父 agent 过度依赖子 transcript，导致边界失效。  
  Mitigation: 默认只暴露结构化结果与摘要，transcript inspect 做成单独且有边界的操作。

- [Risk] 子 session 的多次 run 语义与 mode/permission 继承产生歧义。  
  Mitigation: 把 mode 绑定在子 session 上，并规定 mode 变更只影响后续 run，且不得高于父 session。

- [Risk] 高层角色化子 agent 与底层 runtime 一起开发，导致需求和接口同时漂移。  
  Mitigation: 本 change 先只做底层 runtime；高层 `Explore` / `Plan` 类 agent 后续单独立项。

- [Risk] 一开始把完整 session 元数据对象直接暴露给 LLM，导致编排工具面过宽。  
  Mitigation: 先只暴露最小闭环工具，把 `GetSubagent` 这类更细元数据读取保留给 CLI / Web 内部接口。

- [Risk] 创建子 session 与启动子 run 语义混叠，导致后续多次 run 接口难以稳定。  
  Mitigation: 明确 `CreateSubagent` 只建 session，`RunSubagent` 专门发起 run。

- [Risk] 为等待语义新增独立工具，导致工具面过碎且模型选择成本上升。  
  Mitigation: 将等待收敛为 `RunSubagent` / `GetSubagentRun` 的参数能力。

- [Risk] 为所有子 session 工具复用同一个返回 schema，导致字段语义混乱。  
  Mitigation: 将返回结构明确分为 session 标识、run result、transcript inspect 三类。

- [Risk] 同一子 session 内并发多个 run，导致 transcript、trace 和 mode 语义交错。  
  Mitigation: 明确同一 `subagent_id` 任一时刻最多一个 active run，真正并发通过多个子 session 实现。

## Testing Strategy

- SubAgentManager / 子 session 管理测试覆盖：
  - 创建子 session
  - 并发多个子 session
  - 在同一子 session 中发起多次 run
  - 查询状态、等待结果、取消 run

- AgentLoop 集成测试覆盖：
  - 子 run 执行只读工具循环
  - 子 run 产出独立 trace、usage 和 artifact 引用
  - 父 run 通过显式接口管理子 session，不破坏父 tool-call 链

- transcript / inspect 测试覆盖：
  - 默认只返回结构化摘录
  - transcript inspect 只返回受限范围内容

- mode / permission 测试覆盖：
  - 子 session mode 继承和限制
  - mode 变更只影响后续 run
  - 子 mode 不得高于父 mode

- scope 测试覆盖：
  - 本 change 不引入高层角色化子 agent
  - 底层 runtime 工具接口可单独驱动子 session 全生命周期

- tool surface 测试覆盖：
  - 父 agent 仅看到最小闭环的 6 把工具
  - CLI / Web 可读取额外 session 元数据

- session/run 分层测试覆盖：
  - `CreateSubagent` 不自动启动 run
  - `RunSubagent` 必须基于现有 `subagent_id`

- wait 语义测试覆盖：
  - `RunSubagent(wait=false)` 立即返回运行中状态
  - `RunSubagent(wait=true)` 在完成或超时后返回正确结果
  - `GetSubagentRun(wait=true)` 不破坏父 tool-call 链

- 返回结构测试覆盖：
  - `CreateSubagent` 只返回 session 标识信息
  - `RunSubagent` 与 `GetSubagentRun` 返回同构 run result
  - `InspectSubagentTranscript` 返回受限 inspect 结构

- 并发边界测试覆盖：
  - 多个子 session 可同时运行
  - 同一子 session 在 active run 未结束时拒绝再次 `RunSubagent`

- Web / CLI 测试覆盖：
  - Web 能看到子 session 状态与最近 run 摘要
  - CLI 能列出和检查子 session
  - 未来 TUI 所需的 focus/inspect 字段在事件和数据模型中已保留

## 面试表述

这套设计在面试中建议这样表述：

> 我们没有把 subagent 做成一次性 `llm.chat` helper，也没有直接上重型分布式任务系统，而是先做了一个 in-process、受限、可多次运行的 child-session runtime。  
>  
> 参考实现上，我们借了 OpenClaw 的 session identity 和 inspect 思路，借了 Nanobot 的真实 child AgentLoop 骨架，借了 Hermes 的 isolated 默认边界，也认同 Claude Code / Hermes 在高层会用 `Explore` 这类目标委托 agent；但这次我们先不把高层角色化 agent 和底层 runtime 混在一起实现。  
>  
> 这样做的结果是：父子运行时边界、权限边界、trace 归属和 UI 展示模型都比较清楚，而且 CLI、Web、未来 TUI 能围绕同一套子 session runtime 演进。
