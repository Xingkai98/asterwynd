# 项目模拟面试 Q&A 记录

> **场景**: 角色反转模拟面试 — 用户是面试官，Claude 是候选人
> **项目**: Asterwynd — Coding Agent 系统
> **日期**: 2026-07-20
> **分支**: worktree-lively-painting-phoenix
> **格式**: 每个问题含 A（详细参考版）+ B（面试讲稿版）
> **缺陷跟踪**: 面试中发现的缺陷记录于文末「面试中发现的缺陷」章节

---

## Q1: 简单介绍一下你做的这个 coding agent 项目

### A — 详细参考版

Asterwynd 是一个面向大厂 Agent 开发岗位的 Coding Agent 系统。主线是让 Agent 能够在真实代码仓库中理解需求、调用工具、修改代码、验证结果，形成完整的开发闭环。

核心架构围绕几条能力线展开：

1. **AgentLoop（Agent 运行时）**: 中枢——接收用户任务后，循环调用 LLM、解析 tool-call、执行工具、把结果送回 LLM，直到任务完成或达到迭代上限。支持多种执行模式（inline、subagent、远程）。

2. **上下文注入管线**: 每次 LLM 调用前，系统自动注入多层上下文——系统提示词、项目文档（AGENTS.md、CONTEXT.md）、记忆、当前会话历史。管线是插件化的，不同场景挂不同的注入源。

3. **工具系统**: Agent 可调用的工具通过注册表管理——文件读写、搜索（grep/glob）、bash 执行、git 操作等。工具调用遵循协议约束，保证消息链合法性。

4. **验证与可观测性**: 通过 benchmark 任务集评测 Agent 能力，覆盖 CLI、Web、工具协议等层级。每个关键操作都有日志追踪。

5. **OpenSpec 工作流**: 需求驱动的开发流程——从 explore → propose → apply → sync → archive，每个阶段有 gate 机制和机械验证。

**技术栈**: Python 为主，uv 管理依赖，支持多种 LLM provider（通过 adapter 模式），提供 CLI 和 Web 两种交互方式。

### B — 面试讲稿

> "Asterwynd 是一个面向大厂 Agent 开发岗的 Coding Agent 系统——核心目标就是让 AI 能在真实代码仓库里理解需求、调用工具、写代码、跑验证，走通完整的开发闭环。
>
> 架构上分几条主线：最核心的是 AgentLoop 运行时——它负责接收任务，然后在一个循环里调 LLM、解析工具调用、执行工具、把结果塞回给 LLM，直到任务完成或者达到迭代上限。每次调 LLM 之前，有一个上下文注入管线，会把系统提示词、项目的 ASTER.md 指令文件、持久记忆索引、已激活的 Skill 上下文这些东西按优先级拼进去，优先级高的 critical 层永远不会被截断。
>
> 工具系统是插件化的，通过注册表管理，包括文件读写、搜索、Git 操作、Bash 执行这些。所有工具调用有协议约束，保证消息链不会出现 tool-result 伪装成 assistant 回复这种问题。
>
> 验证这层靠 benchmark——我们有一套 benchmark 任务集，每个任务对应一个真实的代码修改场景，Agent 跑完后由 runner 判定结果，区分"成功"和"达到迭代上限但没完成"等不同终态。
>
> 另外整个开发流程走 OpenSpec 工作流：需求先 explore 探索、再 propose 提案、设计确认后 apply 实现、然后 sync 同步正式 spec、最后 archive 归档——每个关键节点有 gate 机制，必须通过机械验证才能继续。"

---

## Q1.1: Agent Loop 迭代上限多少轮，长程任务够用吗？

### A — 详细参考版

**默认迭代上限**: 20 轮（`agent/loop.py:77`），可通过 CLI `--max-iterations` 覆盖（`agent/main.py:282`）。

```python
# agent/loop.py:77,98
max_iterations: int = 20,
self.max_iterations = max_iterations  # 构造函数可覆盖

# agent/loop.py:527
for iteration in range(start_iteration, self.max_iterations):
```

**长程任务够不够？** 20 轮是偏保守的默认值：

1. **可以调大**: CLI 和 Runner 都支持 `--max-iterations` 参数，benchmark 跑复杂任务时可以设到 50-100。`AsterwyndRunner` 同样支持传入覆盖（`benchmarks/agent_runner.py:262`）。

2. **有记忆压缩缓解**: 每轮迭代结束都会调用 `self.memory.compact_if_needed()`（`agent/loop.py:805`），当上下文接近窗口上限时自动触发压缩，把历史消息摘要化。所以即使迭代多，也不会因为上下文溢出而中断——但这只能解决窗口问题，不解决"Agent 能不能在有限步数内完成任务"的问题。

3. **实际瓶颈**: 长程任务的真正瓶颈往往不是迭代上限，而是上下文压缩后信息丢失导致 Agent 迷路、工具调用结果太大、LLM 推理质量下降。20 轮是一个"尽早暴露问题"的合理默认值，需要时上调，而不是无脑设一个超大值让 Agent 在里面打转。

4. **benchmark 体现**: 当 Agent 在 20 轮内没完成任务，`stop_reason` 返回 `max_iterations`，benchmark 判定为 `passed_with_warnings` 而非假成功——不会伪造最终回复（AGENTS.md 明确禁止）。

### B — 面试讲稿

> "默认是 20 轮，可以通过 CLI 参数 `--max-iterations` 调大。20 这个值的考虑是偏保守的——它更像一个'尽早暴露问题'的设计，而不是'给够步数等 Agent 慢慢磨'。
>
> 长程任务有两个层面的问题。第一是上下文窗口——Agent 每轮调用都在积累消息历史，所以我们在每轮结束后做记忆压缩：当 token 数达到上限的 90% 时触发，用 LLM 把中间段的历史总结成四段结构化摘要——已完成、关键决策、进行中、阻塞与待办——然后把摘要以 user 消息形式注入，保留最近 10 轮的完整上下文。这样窗口不会炸。
>
> 第二是任务本身的收敛性——如果 Agent 在 20 轮内找不到方向，调大到 100 也不太可能突然找到。真正的瓶颈往往是压缩后信息丢失、工具输出过大导致关键细节被截断、或者 LLM 本身的推理退化。所以我们的策略是默认 20，需要时上调，但更关注怎么让每一步的上下文质量更高。"

---

## Q1.2: 上下文都注入了哪些东西，超阈值之后怎么压缩？

### A — 详细参考版

#### 注入管线

每次 LLM 调用前，`ContextBuilder` 按优先级从 P0 到 P5 渲染各层 ContextSource，拼接到消息列表中。注入预算 = `min(20K, context_window × 20%)`，默认 20K tokens（`agent/loop.py:1039-1041`）。

| 优先级 | 层 | 预算 | 关键? | 内容 |
|--------|-----|------|--------|------|
| **P0** | SystemPrompt | 1.5K | 是 | 身份声明、NEVER/ALWAYS 红线圈、工具使用约定；可拼接 `--system` 用户参数 |
| **P1** | AsterMd | 3K | 是 | 从 Git 根到 CWD 逐层收集 `ASTER.md` + `ASTER.local.md`，越靠近工作目录优先级越高 |
| **P2** | MemoryIndex | 2K | 否 | 持久记忆索引（MEMORY.md 摘要），引导 agent 用 RecallMemory 查详情 |
| **P4** | SkillIndex + SkillActive | 各 2.5K | 否 | 可用 skill 列表 + 当前激活 skill 的完整 prompt |
| **P5** | PlanMode + PlanningState + Todo | 合计约 5K | 否 | plan 模式指令、规划状态、执行进度（仅 build/read_only 模式） |

P3 跳号——设计预留但未实现。P0 + P1 是 critical，永不被截断（约占 4.5K）。

#### 两层压缩机制

**第一层 — ContextBuilder 截断**：针对静态注入内容。超预算时从最低优先级的尾部开始按 token 截断，critical 层（P0/P1）永不被截。

**第二层 — MemoryManager 对话压缩**：

触发条件：总 token 数达到 `max_tokens × 90%`（默认 100K → 90K 触发），两次压缩间至少间隔 5 轮迭代。

压缩策略（`agent/memory/manager.py:118-160`）：
```
messages
  ├── system 消息  → 完整保留
  ├── 中间段 (middle) → LLM 摘要，注入为 user 消息
  └── 尾部 recent_window (默认10条) → 完整保留 + 工具链保护
```

工具链保护（`manager.py:197-215`）：保留尾部消息时，如果其中有 tool 消息，向前追溯找到对应的 assistant tool-call，确保 tool-call ↔ tool-result 对不被拆散。

摘要生成两种策略（`agent/context/summarizer.py`）：

1. **LLMSummarizer**：四段结构化摘要（已完成/关键决策/进行中/阻塞与待办），预算目标为中间段 token 的 30%。以 user 角色注入——让 agent 当作"前情提要"而非约束。
2. **TruncationSummarizer**（无 LLM 降级）：工具输出截断至 500 字符，user/assistant 截断至 200 字符，旧轮次直接丢弃。

### B — 面试讲稿

> "上下文注入分六层优先级。P0 是系统提示词——定义身份、约束红线、工具约定。P1 是项目指令，从 Git 根目录往下逐层收集 ASTER.md 文件，越靠近工作目录优先级越高。这两个是 critical 层，永远不会被截断。P2 是持久记忆的索引摘要，让 Agent 知道有哪些记忆可以调用 RecallMemory 查看。P3 设计上预留了但还没实现。P4 是 Skill 系统——可用 skill 列表和当前激活 skill 的完整 prompt。P5 是计划状态、Todo 进度这些。总注入预算控制在整个上下文窗口的 20%，最多 20K token。
>
> 超出之后有两层处理。注入层本身如果超预算，从最低优先级尾部截断，critical 层不动。
>
> 对话历史的压缩是另一层——由 MemoryManager 管理。触发点是总 token 到上限的 90%，默认 100K 窗口就是 90K 触发。压缩逻辑是：保留所有 system 消息、保留最近 10 轮完整对话并保证工具调用和结果的配对不拆散、中间段丢给 LLM 生成四段结构化摘要——已完成、关键决策、进行中、阻塞与待办——然后以 user 消息形式注入。这样可以保证 Agent 始终知道'之前发生了什么'，但又不会因为长对话撑爆窗口。两次压缩之间至少隔 5 轮，防止频繁压缩造成抖动。"

---

## Q1.3: Memory Index 和 Skill Index、Skill Active 怎么实现的？

### A — 详细参考版

#### Memory Index (P2)

**存储模型**：`PersistentMemory`（`agent/memory/persistent.py`）兼容 Claude Code 格式：

```
~/.asterwynd/projects/<repo-sha256[:16]>/memory/
  ├── MEMORY.md          ← 索引文件（注入上下文的就是这个）
  ├── user_xxx.md        ← 具体记忆文件（含 YAML frontmatter）
  ├── feedback_xxx.md
  └── ...
```

每个记忆文件含 YAML frontmatter（`name`、`description`、`metadata.type`）+ Markdown body。

**注入**：`MemoryIndexSource.render()` 调用 `load_index()` 直接读 MEMORY.md 原文，截断保护 200 行 / 25KB。超出附加 warning 引导 agent 用 RecallMemory。

**读写工具**：
- `SaveMemory`：agent 调用，写入 `{name}.md` + 更新 MEMORY.md 索引行
- `RecallMemory`：解析 MEMORY.md 中 `[name](file.md)` 链接，按需读取 `.md` 全文，按 type 过滤

**设计要点**：MEMORY.md 是索引不是记忆本身——agent 看到索引后按需 RecallMemory，避免所有记忆全塞进上下文。

#### Skill Index + Skill Active (P4)

**加载**：`SkillLoader`（`agent/skills/loader.py`）扫描配置的 root 目录下所有 `*/SKILL.md`，解析 YAML frontmatter 生成 `Skill` dataclass：name、description、prompt（body）、tools 白名单、always 标志、triggers 匹配词等。

**SkillIndex 渲染**（`runtime.py:152-161`）：只列 `user_invocable=True` 的 skill，格式为 `- skill_name: description. Invoke: /skill_name <arg>`。

**SkillActive 渲染**（`runtime.py:163-168`）：遍历 `_active_skill_names` 集合，输出每个激活 skill 的完整 prompt。

**激活时机**（`runtime.py:68-83`）：
1. 清空上一轮激活列表
2. 处理队列化激活
3. 自动匹配——`always=True` 直接激活；否则用 `_matches_user_input()` 检查 skill 的 name/description/triggers 是否出现在用户输入中

也可中途通过工具调用 `queue_activation()` 或 `activate_skill()` 手动激活。

### B — 面试讲稿

> "Memory Index 的存储模型是文件系统——在 `~/.asterwynd/projects/` 下按仓库 hash 建目录，每个记忆是一个独立 markdown 文件，包含 YAML frontmatter 标记类型和名称。MEMORY.md 本身是索引文件，每行一个条目链接到具体的 md 文件。注入上下文时只加载索引摘要，不让 Agent 把全部记忆灌进去。Agent 看到索引后，如果需要某个记忆的详细内容，调用 RecallMemory 工具，系统再按文件名链接去读对应的完整文件。写记忆则是 SaveMemory 工具，会同时更新文件内容和索引行。
>
> Skill 这边是通过 SkillLoader 扫描配置的 skill 根目录，找到所有 `SKILL.md` 文件，解析 frontmatter 生成 Skill 对象。name 是目录名，prompt 是 body 部分，另外还有 tools 白名单、always 标志、triggers 触发词这些字段。
>
> SkillIndex 只渲染 user_invocable 的 skill，给 Agent 一个可用清单。SkillActive 则输出当前已激活 skill 的完整 prompt——这才是真正指导 Agent 行为的指令。激活逻辑在每次 AgentLoop 开始时执行：先清空、再处理队列中的激活请求、然后自动匹配——标记了 always 的 skill 无条件激活，其他的通过关键词匹配用户输入来触发。两个 source 共用 P4 的 5K 预算，超出时限截 Active 保留 Index。"

---



---

## Q1.4: 怎么确保模型在适当时候调用 SaveMemory 存全局记忆

[...B 版已输出，此处省略重复内容，详见对话记录...]

---

## Q1.5: 工具系统的权限怎么管理

### A — 详细参考版

三层架构：能力标记 → 模式策略 → 审批处理。

**第一层 — 工具声明权限**：每个 Tool 子类声明 `permission`（ToolPermission 含 capability + risk_level）。8 种 capability（workspace_read/write、command_execute、network_read、external_side_effect、agent_state、subagent_control、browser_control），3 级风险（LOW/MEDIUM/HIGH）。未显式声明时按 read_only/dangerous 属性推断。

**第二层 — ModePolicy 决策**：`decide_tool()` 五步逐级过滤：
1. allowed_modes 检查
2. mode deny list 检查
3. profile denied_tools 检查
4. capability 子集检验
5. 风险等级 vs profile 阈值 → ALLOW / REQUIRE_APPROVAL / DENY

**第三层 — ApprovalHandler**：REQUIRE_APPROVAL 时构建脱敏审批请求，默认 FailClosed（不可用），CLI 模式交互式 y/N。

**四种模式配置**：build（全能力，MEDIUM自批，HIGH审批）、read_only（只读白名单）、plan（规划白名单）、bypass（全拒）。

**参数脱敏**：`redact_value()` 对 key/token/secret/password 等敏感 key 名和 Bearer/sk- 等值模式正则替换为 `[redacted]`。

**并行执行影响**：需审批的工具不会编入并行组，单独串行等待。

### B — 面试讲稿

> "工具权限是分层管理的，从下到上一共三层。最底层每个工具声明自己的权限——capability 能力标签加 risk_level 风险等级。Read 是 workspace_read + low，Bash 是 command_execute + high，Edit 是 workspace_write + medium。能力标签有 8 种。
>
> 中间层是 ModePolicy——Agent 四种运行模式各绑定一个 PermissionProfile，定义了允许哪些 capability、自动批准到哪个风险等级、需要审批到哪个等级。决策五步走：allowed_modes → mode deny list → profile deny list → capability 子集检验 → 风险阈值比较。最终返回三种结果：自动放行、需要审批、直接拒绝。
>
> 审批层对需要审批的调用做参数脱敏——把 token、api_key 这些值替换成 [redacted]——然后交给 ApprovalHandler。默认是 FailClosed，CLI 下交互式 y/N。审批不通过工具就不执行。
>
> 还有一个细节：需要审批的工具不会进并行组，被单独串行等待，避免审批失败波及其他并行调用。"

---

## Q1.5.1: 为什么执行时 WorkspacePolicy 还要做一次校验

### A — 详细参考版

两层职责不同：

- **审批层**回答"能用吗"——判断工具类型和能力，不检查参数内容
- **WorkspacePolicy** 回答"安全吗"——对具体内容做程序化硬拦截

审批层不可替代 WorkspacePolicy 的原因：

1. **`build_legacy_auto_high_risk` 模式下 Bash 自动批准**——HIGH ≤ auto_approve_max_risk=HIGH，直接跳过审批，无人查看命令内容
2. **人工审批可能漏判**——长命令中藏危险操作、疲劳审批习惯性按 y
3. **审批只管工具级别**——不知道也不应该知道哪些命令模式是危险的

WorkspacePolicy 的 denylist（`rm -rf /`、`shutdown`、fork bomb、`curl | bash` 等 60+ 条正则）是正则硬匹配，不依赖人。两层之间：权限管边界，Policy 做最后安全网。

### B — 面试讲稿

> "因为两层管的事不一样。审批层判断的是'这个工具你能用吗'——它是按工具类型和能力来决策的，不看参数内容。WorkspacePolicy 判断的是'这个具体命令安全吗'——用正则硬匹配危险模式。
>
> 关键场景是 build_legacy_auto_high_risk 这个权限配置——HIGH 风险的工具也自动批准，Bash 直接跳过审批流程。如果 LLM 返回了 `rm -rf /`，没有 WorkspacePolicy 这道网就直接执行了。即使在交互式 CLI 下，人也可能疲劳审批或者没注意到长命令里藏了危险操作。
>
> 简单说就是防御纵深——审批是第一道门禁，决定你能不能进；WorkspacePolicy 是第二道保险丝，你进去了也不能碰红线。"

---

## 面试中发现的缺陷

模拟面试过程中发现的设计/实现缺陷，记录于此，后续修复。

### BUG-001: 全局记忆保存时机规则未内置于系统提示词

- **发现于**: Q1.4 — 追问"怎么确保模型会在适当的时候调用这个工具去存全局记忆"
- **严重程度**: 中
- **问题**: P0 系统提示词（`_render_system_prompt()`）和 SaveMemory 工具描述中均未包含"何时该存记忆"的行为规则。当前这些规则只存在于项目 AGENTS.md 的"保存时机"章节中，依赖 Claude Code 的 CLAUDE.md → @AGENTS.md 引用链路注入。在新文件夹启动 Asterwynd 时，没有 ASTER.md 就没有这些规则，Agent 拥有 SaveMemory/RecallMemory 工具但缺乏使用判断依据。
- **涉及文件**:
  - `agent/context/sources.py` — `_render_system_prompt()` 无记忆相关指令
  - `agent/tools/builtin/memory.py` — `SaveMemoryTool` description 无触发场景说明
- **建议修复方向**: 将记忆保存时机规则（何时存/不存什么）内嵌到 P0 系统提示词或 SaveMemory 工具描述中，作为框架级基础能力，不依赖外部指令文件。

### BUG-002: `max_memory_mb` 参数声明但未实际生效

- **发现于**: Q1.7 — "工具执行有沙箱机制吗"
- **严重程度**: 低
- **问题**: `SandboxExecutor.__init__` 接受 `max_memory_mb: int = 512` 参数（`agent/tools/sandbox.py:115`），但 `run()` 方法中从未调用 `resource.setrlimit` 或任何内存限制机制。看起来是为未来容器沙箱预留的接口，但当前对 subprocess 完全不生效。
- **涉及文件**: `agent/tools/sandbox.py` — `SandboxExecutor`
- **建议修复方向**: 在 `run()` 中通过 `preexec_fn` 设置 `resource.RLIMIT_AS`，或在注释中明确标记为"预留未实现"。

---

## 待讨论

模拟面试中发现的潜在改进点，方案尚不明确，需要进一步讨论。

### DISCUSS-001: 工具权限静态声明 vs 参数感知

- **发现于**: Q1.5 — 追问"静态权限有什么场景会不够用"
- **问题**: 每个工具的 `ToolPermission`（capability + risk_level）是类级别的静态常量。同一工具不同参数的实际风险差异很大，但权限判定无法区分。例如 Bash 工具执行 `git status`（实际风险 ≈ LOW）和 `rm -rf /dir/`（实际风险 = HIGH）都走相同的 HIGH 风险审批路径。当前靠 WorkspacePolicy 的命令/文件黑名单兜底，但这层在权限决策之后才触发。
- **为什么先不记 bug**: 参数感知权限会让模型从静态声明变成运行时推理，复杂度显著上升。是否有更轻量的方案（如 Bash 工具内部做命令分类、或在工具注册时按参数模式注册多个变体）需要讨论后再定。
- **待讨论点**:
  - 是否有比"参数感知权限"更轻量的方案？
  - 能否让 WorkspacePolicy 参与 `decide_tool()` 的判定而不是事后拦截？
  - 静态权限在多大程度上是"够用的"？

### DISCUSS-002: 沙箱加固方向——轻量改进 vs OS 级隔离

- **发现于**: Q1.7 — "工具执行沙箱机制" + 跨项目调研
- **背景**: 调研了 18 个参考仓库的沙箱实现。Asterwynd 当前 `SandboxExecutor` 本质是 subprocess 包装，无任何 OS 级隔离。OS 级沙箱（bwrap/seccomp）工程量大，但有三项轻量改进可快速落地。
- **轻量改进候选**:
  1. **命令安全扫描器**（对标 Goose 30 条正则 + Continue shlex 令牌化）：在 `SandboxExecutor.run()` 执行前加一层 `shlex.split()` + 正则扫描，将命令分为 safe/unknown/dangerous/blocked 四级，联动审批系统。WorkspacePolicy 已有 60+ 正则但只做二元判断，可重构为分级扫描。
  2. **`max_memory_mb` 实际生效**：`preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_AS, (...))`，一行代码。
  3. **`allowed_dirs` 实际生效**：命令执行前校验 cwd 是否在允许目录列表中。
- **长期方向**: bwrap + seccomp（对标 Codex/Claude Code），但需 Rust/C 实现，不属于短期目标。
- **待讨论点**:
  - 安全扫描器应该作为 SandboxExecutor 的内置层，还是独立的 PreExecutionHook？
  - Goose 的 30 条正则是否足够？需要补充哪些模式？
  - 三级风险（safe/dangerous/blocked）如何映射到现有的 PermissionDecision（ALLOW/REQUIRE_APPROVAL/DENY）？

---

## Q1.6: 运行时崩溃后能从执行位置恢复吗

### A — 详细参考版

可以。保存机制在 `run()` 的 `finally` 块（`agent/loop.py:456-463`），保证正常退出和异常崩溃都会写盘。

**快照内容**（`SessionSnapshot`）：完整 messages 列表、mode、todos、active_skills、iteration、run_id、user_system_prompt、runtime_fingerprint（cwd/model/provider/version）。

**存储格式**：`.asterwynd/sessions/<session_id>/` 下两个 JSON 文件（snapshot.json + messages.json），原子写入（先写 .tmp 再 os.replace）。

**恢复路径**：`--resume <session_id>` 或 Web `?resume=`。加载时校验 schema version（大版本不兼容拒绝）和 runtime fingerprint（cwd/model/provider 变了会 warn 但不阻止）。恢复后保留当前 system 消息，替换 conversation 为快照历史，追加 `[Session resumed. Continuing from where we left off.]` 标记，恢复 mode/todos/skills，**iteration 重置为 0**。

**局限**：只在 run 结束时保存，非逐轮增量。SIGKILL/断电/OOM 时 finally 不执行，整个 run 丢失。

### B — 面试讲稿

> "可以恢复。核心是在 AgentLoop 的 run 方法里用 finally 块——正常结束或异常崩溃都会把当前完整消息历史、运行模式、todos、已激活 skill、迭代数序列化到磁盘。路径是 `.asterwynd/sessions/<session_id>/`，两个 JSON 文件，用原子写入防止写一半崩溃。
>
> 恢复用 `--resume <session_id>`，加载时校验 schema 版本和运行时指纹——工作目录或模型换了会警告但不阻止。关键点是恢复后迭代计数器归零，崩溃前消耗的配额重新获得。
>
> 局限是只在 run 结束保存，不是逐轮增量。kill -9 或断电的话 finally 不执行，整个 run 进度丢失。这是 IO 开销和安全性之间的取舍。"

---

## Q1.7: 工具执行有沙箱机制吗，有没有用 Docker

### A — 详细参考版

没有。`SandboxExecutor`（`agent/tools/sandbox.py`）基于 `asyncio.create_subprocess_shell`，不是真正的安全沙箱。

三道防线：超时+输出限制（30s / 1MB）、进程组清理（`os.setsid` + `os.killpg`）、WorkspacePolicy 黑白名单。没有 Docker/容器、没有 chroot/namespace/cgroup、没有网络隔离。

Bash 工具暴露 `timeout` 参数给 LLM 自定义超时，`run_in_background` 支持后台长时间任务——AgentLoop 每轮迭代检查完成状态并注入结果。`max_memory_mb=512` 声明但未实现。

`BackgroundProcessHandle` ABC 注释预留了容器替换接口。

### B — 面试讲稿

> "没有用 Docker。当前所谓的沙箱本质就是 subprocess。安全靠三层叠加：超时和输出限制防止资源耗尽、进程组管理防止子进程泄露、WorkspacePolicy 命令黑名单做硬拦截。但没有真正的容器隔离——没有 namespace、cgroup、网络隔离。
>
> 超时方面，Bash 工具暴露了 timeout 参数给 LLM，模型可以根据任务类型自己设定，比如 npm install 调 300 秒。真正长任务走 run_in_background 后台模式，AgentLoop 每轮迭代自动检查并注入完成结果。
>
> 代码里有个抽象类预留了容器适配器接口，注释写了未来换容器时改适配器即可。还有个 max_memory_mb 参数声明了 512MB 但完全没实现。"

---
