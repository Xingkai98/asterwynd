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

## Q2: SubAgent 系统——父 Agent 如何生成和管理子 Agent？


## Version A -- 详细参考版

### 1. 架构总览

SubAgent 系统由三个核心模块组成：

| 模块 | 文件 | 职责 |
|------|------|------|
| `SubAgentManager` | `agent/subagent/manager.py` | 子 Agent 生命周期管理、运行调度、mode clamping |
| `ParentChannel` | `agent/subagent/protocol.py` | 子 Agent 向父 Agent 回传结果的单向消息通道 |
| 6 个 Subagent 工具 | `agent/tools/builtin/subagents.py` | 暴露给父 Agent 的 CRUD+控制工具 |

父 Agent 通过 6 个工具操作子 Agent；子 Agent 是独立的 `AgentLoop` 实例，**默认不注册 subagent 工具**，从而天然阻断递归。


### 2. 子 Agent 的生成与隔离

#### 2.1 创建（CreateSubagent）

**入口**: `CreateSubagentTool.execute()` (`agent/tools/builtin/subagents.py:30-36`)

```python
# agent/subagent/manager.py:128-149
def create_subagent(self, *, name, description="", mode=None) -> dict:
    requested_mode = self._parent_mode() if mode is None else (
        mode if isinstance(mode, AgentMode) else parse_agent_mode(mode)
    )
    effective_mode = self._clamp_mode(requested_mode)  # 关键：mode clamping
    subagent_id = uuid.uuid4().hex[:8]
    session = SubagentSessionRecord(
        subagent_id=subagent_id,
        name=name,
        description=description,
        mode=effective_mode,
        status="idle",
        messages=[system_message("你是一个受限的子 agent。按任务目标完成工作并汇报结果。")],
    )
    self._sessions[subagent_id] = session
    return session.to_summary_dict()
```

关注点：
- 如果父 Agent 不指定 mode，默认继承父 Agent 的当前 mode。
- mode 经过 `_clamp_mode` 处理，确保子 Agent 权限不高于父 Agent。
- 子 Agent 初始化一条中文 system message，明确其"受限子 agent"角色。
- 每个 session 通过 `subagent_id`（uuid4 hex 前 8 位）唯一标识。

#### 2.2 运行（RunSubagent）

**入口**: `RunSubagentTool.execute()` (`agent/tools/builtin/subagents.py:60-67`)

```python
# agent/subagent/manager.py:162-194
async def run_subagent(self, *, subagent_id, task, wait=False, timeout_s=None) -> dict:
    session = self._require_session(subagent_id)
    if session.active_run_id is not None:
        raise RuntimeError(f"subagent {subagent_id} already has an active run")

    run_id = new_run_id()
    run = SubagentRunRecord(run_id=run_id, task=task, status="running", started_at=time.time())
    session.runs.append(run)
    session.active_run_id = run_id
    session.status = "running"
    session.messages.append(Message(role="user", content=task))
    waiter = asyncio.Event()
    self._run_waiters[run_id] = waiter

    bg_task = asyncio.create_task(self._execute_run(session, run))
    self._active_tasks[run_id] = bg_task
    bg_task.add_done_callback(lambda _: self._active_tasks.pop(run_id, None))

    if wait:
        await asyncio.wait_for(waiter.wait(), timeout=timeout_s)
    return self._format_run_envelope(session.subagent_id, run)
```

关键设计：
- **互斥运行**: 每个 session 同时只能有一个活跃 run（`session.active_run_id is not None` 时抛异常）。
- **异步后台执行**: 通过 `asyncio.create_task` 创建后台任务，父 Agent 可以选择 `wait=True` 同步等待或 `wait=False` 异步派发后继续工作。
- **waiter 机制**: `asyncio.Event` 作为完成信号，`_execute_run` 的 `finally` 块中 `waiter.set()`。

#### 2.3 执行引擎（_execute_run + _build_subagent_loop）

```python
# agent/subagent/manager.py:271-324
async def _execute_run(self, session, run) -> None:
    if self.llm is None:
        raise RuntimeError("subagent manager LLM is not configured")
    trace = TraceRecorder(task_id=session.subagent_id)
    try:
        loop = self._build_subagent_loop(session.mode)
        result = await loop.run(
            session.messages,
            trace_recorder=trace,
            session_id=session.subagent_id,
            run_id=run.run_id,
        )
        self._complete_run(session, run, result, trace)
    except asyncio.CancelledError:
        self._mark_cancelled(session, run, trace)
        raise
    except Exception as exc:
        self._mark_failed(session, run, str(exc), trace)
    finally:
        waiter = self._run_waiters.pop(run.run_id, None)
        if waiter is not None:
            waiter.set()

def _build_subagent_loop(self, mode: AgentMode) -> AgentLoop:
    from agent.loop import AgentLoop
    config = self.config
    registry = build_default_tool_registry(
        policy=self.workspace_policy,
        mode_policy=ModePolicy(
            AgentRunConfig(mode=mode),
            deny_tools_by_mode=config.deny_tools_by_mode() if config else None,
            permission_profiles_by_mode=config.permission_profiles_by_mode() if config else None,
        ),
        ...
    )
    return AgentLoop(
        llm=self.llm,
        tool_registry=registry,
        hooks=HookManager([TracingHook()]),
        memory=MemoryManager(max_tokens=80_000),
        run_config=AgentRunConfig(mode=mode),
        subagent_manager=self,  # 传入同一个 manager 实例
        tool_result_display=config.tools.display if config else None,
    )
```

隔离细节：
- **独立的 AgentLoop**: 每个子 Agent run 创建一个全新的 `AgentLoop` 实例。
- **独立的 ToolRegistry**: `build_default_tool_registry` 构建新的工具注册表，受 clamped mode 的 `ModePolicy` 约束。
- **独立的 MemoryManager**: 80K token 的独立上下文窗口。
- **共享的 LLM 和 SubAgentManager**: 共享底层 LLM 实例，subagent_manager 传入 `self`（同一个 manager）。
- **独立的 session_id 和 run_id**: 与其他 AgentLoop run 隔离，用于追踪。


### 3. Mode Clamping（父子权限关系）

**核心实现**: `agent/subagent/manager.py:401-416`

```python
def _clamp_mode(self, requested: AgentMode) -> AgentMode:
    parent_mode = self._parent_mode()
    order = {
        AgentMode.READ_ONLY: 0,
        AgentMode.PLAN: 0,
        AgentMode.BUILD: 1,
        AgentMode.BYPASS: 2,
    }
    if order[requested] > order[parent_mode]:
        return parent_mode
    return requested

def _parent_mode(self) -> AgentMode:
    if self.parent_mode_provider is not None:
        return self.parent_mode_provider()
    return self.parent_mode
```

机制：
- 四种 mode 分为三个权限等级: READ_ONLY/PLAN (0) < BUILD (1) < BYPASS (2)
- 子 Agent 请求的 mode 若高于父 Agent 当前 mode，则被降级到父 Agent 级别
- `parent_mode_provider` 是一个回调函数（在 `AgentLoop.__init__` 中设置），动态返回 `runtime_state.current_mode`，这使得父 Agent 运行中 mode 切换也能即时生效

**初始化时设置回调** (`agent/loop.py:93-97`):
```python
self.subagent_manager = subagent_manager or SubAgentManager()
self.subagent_manager.configure_runtime(
    llm=llm,
    parent_mode_provider=lambda: self.runtime_state.current_mode,
)
```

**权限配置层**: 除了 mode clamping，`ModePolicy` 还通过 `PermissionProfile` 做工具级控制。`agent/tool_permissions.py` 中定义：
- `build_default`: 允许包括 `SUBAGENT_CONTROL` 在内的全部 capability
- `read_only_default`: 只允许 `WORKSPACE_READ`, `NETWORK_READ`, `AGENT_STATE`，不包含 `SUBAGENT_CONTROL`
- `plan_default`: 同 `read_only`，不包含 `SUBAGENT_CONTROL`

因此即使在 read_only/plan 模式下注册了 subagent 工具，也会被 `decide_tool()` 拒绝。


### 4. 父 Agent 观察子 Agent 进度

父 Agent 通过以下 6 个工具观察和控制子 Agent：

| 工具 | 文件位置 | 功能 |
|------|---------|------|
| `CreateSubagent` | `subagents.py:10-36` | 创建子 Agent session |
| `RunSubagent` | `subagents.py:39-67` | 启动一次 run，支持 `wait` 同步等待 |
| `ListSubagents` | `subagents.py:70-83` | 列出所有子 Agent session 及状态 |
| `GetSubagentRun` | `subagents.py:86-114` | 获取指定 run 的结果/状态，支持 `wait` |
| `CancelSubagentRun` | `subagents.py:117-141` | 取消活跃 run |
| `InspectSubagentTranscript` | `subagents.py:144-174` | 查看子 Agent 的 summary 或最近消息 |

**两种观察模式**:

1. **同步等待 (`wait=True`)**: 父 Agent 调用 `RunSubagent` 或 `GetSubagentRun` 时设置 `wait=True`，调用会阻塞直到子 Agent 完成或超时。
2. **异步轮询**: 父 Agent 先调用 `RunSubagent(wait=False)` 获取 run_id，后续通过 `GetSubagentRun` 或 `InspectSubagentTranscript` 观察进度。

**返回的数据结构** (`SubagentRunRecord.to_result_dict()`, `manager.py:51-65`):
```python
{
    "run_id": str,
    "status": "completed" | "running" | "failed" | "cancelled",
    "summary": str,
    "reason": str | None,
    "usage": {"total_tokens": int, "tool_calls": int},
    "artifacts": [{"path": str, "kind": str}],
}
```

**Transcript 探查** (`manager.py:234-269`): 支持两种 scope：
- `summary`: 返回最新 run 的 summary 文本
- `recent_messages`: 返回最近 N 条消息（默认 5 条），可选是否包含 tool 结果


### 5. ParentChannel 协议

**文件**: `agent/subagent/protocol.py`

```python
@dataclass
class SubAgentResult:
    subagent_id: str
    task: str
    result: str
    tool_call_id: str

class ParentChannel:
    def __init__(self, parent_id: str, subagent_id: str):
        self.parent_id = parent_id
        self.subagent_id = subagent_id
        self._queue: asyncio.Queue[SubAgentResult] = asyncio.Queue()

    def put_result(self, task: str, tool_call_id: str, result: str = "") -> None:
        self._queue.put_nowait(SubAgentResult(...))

    def get_result_nowait(self) -> SubAgentResult:
        return self._queue.get_nowait()

    async def get_result(self, timeout: Optional[float] = None) -> SubAgentResult:
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)
```

设计要点：
- 基于 `asyncio.Queue` 的单向消息通道（子->父）。
- `put_result` 是非阻塞的 `put_nowait`，子 Agent 不会因父 Agent 未读取而被阻塞。
- `get_result` 支持异步等待和超时，适合父 Agent 在需要时读取子结果。
- 当前设计中 `ParentChannel` 是数据结构层面的定义；实际的子 Agent 结果回传通过 `SubAgentManager` 的 `_complete_run` / `_format_run_envelope` 机制，由 `asyncio.Event` waiter 实现。

**实际使用的通信机制** (在 `SubAgentManager` 中):
- 父 Agent 通过工具调用的返回值（JSON 字符串）获取子 Agent 结果
- `_run_waiters` dict (`asyncio.Event`) 提供同步等待能力
- `_execute_run` 在 `finally` 块中 always 调用 `waiter.set()`，保证无论成功/失败/取消都能通知等待者


### 6. 递归防护机制

子 Agent 不能创建孙子 Agent，由 **三层防护** 保证：

#### 第一层：工具注册控制（默认不暴露）

```python
# agent/loop.py:76
expose_subagent_tools: bool = False,  # 默认不注册

# agent/loop.py:128-129
if expose_subagent_tools:
    self._ensure_subagent_tools_registered()
```

- `_build_subagent_loop` (`manager.py:298-324`) 创建子 Agent 的 `AgentLoop` 时，**不传** `expose_subagent_tools=True`。
- 因此子 Agent 的 `ToolRegistry` 中不包含 `CreateSubagent`、`RunSubagent` 等 6 个工具。
- 即使 LLM 尝试调用这些工具，也会因 `KeyError("unknown tool")` 被拒绝 (`loop.py:653-664`)。

只有在顶层入口（`agent/main.py:250`）、Web session (`web/session.py:180`) 和 benchmark runner (`benchmarks/agent_runner.py:322`) 中显式设置 `expose_subagent_tools=True`。

测试验证 (`tests/agent/test_loop.py:119-130`):
```python
async def test_agent_loop_does_not_expose_subagent_tools_by_default():
    loop = AgentLoop(llm=MockLLM(...), tool_registry=ToolRegistry(), hooks=HookManager())
    schema_names = {schema["function"]["name"] for schema in loop.tool_registry.get_all_schemas()}
    assert "CreateSubagent" not in schema_names
```

#### 第二层：Mode Clamping

即使未来有路径使子 Agent 获得 subagent 工具，`_clamp_mode` 确保子 Agent 的 mode 不高于父 Agent。如果父 Agent 本身是 read_only，子 Agent 不可能成为 build 模式去创建孙子 Agent。

#### 第三层：Permission Profile 能力控制

所有 6 个 subagent 工具都标记了 `permission = SUBAGENT_CONTROL_PERMISSION`（`subagents.py` 中每个工具类的 `permission` 属性），该 permission 的 capability 为 `SUBAGENT_CONTROL`。而 `read_only_default` 和 `plan_default` 的 `allowed_capabilities` 不包含 `SUBAGENT_CONTROL` (`tool_permissions.py:98-107`)，因此即使工具被注册，`ModePolicy.decide_tool()` 也会返回 `DENY`。


### 7. 生命周期状态机

```
create_subagent() --> status="idle"
    |
    v
run_subagent() --> status="running", active_run_id=<run_id>
    |
    +-- _complete_run() --> status="idle", run.status="completed"
    +-- _mark_failed()  --> status="idle", run.status="failed"
    +-- _mark_cancelled() --> status="idle", run.status="cancelled"
```

- **Session 层面**: `status` 在 `"idle"` 和 `"running"` 之间切换。一个 session 可以有多个历史 run（`session.runs` 列表）。
- **Run 层面**: 每个 `SubagentRunRecord` 有独立的 `status`（`"running"` / `"completed"` / `"failed"` / `"cancelled"`）。
- **互斥保证**: `run_subagent()` 在 `session.active_run_id is not None` 时抛出 `RuntimeError`，防止并发执行。


### 8. 数据模型

```python
# manager.py:25-65
@dataclass
class SubagentArtifact:
    path: str
    kind: str = "file"

@dataclass
class SubagentRunUsage:
    total_tokens: int = 0
    tool_calls: int = 0

@dataclass
class SubagentRunRecord:
    run_id: str
    task: str
    status: str          # running | completed | failed | cancelled
    summary: str = ""
    reason: str | None = None
    usage: SubagentRunUsage
    artifacts: list[SubagentArtifact]
    created_at: float
    started_at: float | None
    finished_at: float | None
    trace: dict | None   # TraceRecorder 序列化结果

@dataclass
class SubagentSessionRecord:
    subagent_id: str
    name: str
    description: str
    mode: AgentMode
    status: str          # idle | running
    created_at: float
    messages: list[Message]  # 该子 Agent 的完整对话历史
    runs: list[SubagentRunRecord]
    active_run_id: str | None
```


### 9. 初始化链路总结

```
agent/main.py:create_loop()
  --> SubAgentManager(llm, config, workspace_policy, parent_mode=run_config.mode)
  --> AgentLoop(..., subagent_manager=subagent_manager, expose_subagent_tools=True)
      --> subagent_manager.configure_runtime(llm=llm, parent_mode_provider=lambda: runtime_state.current_mode)
      --> _ensure_subagent_tools_registered()  # 父 Agent 注册 6 个 subagent 工具

子 Agent run 时：
  --> manager._execute_run()
      --> manager._build_subagent_loop(clamped_mode)
          --> AgentLoop(..., subagent_manager=self, expose_subagent_tools=DEFAULT_FALSE)
          --> 不注册 subagent 工具，递归阻断
```


## Version B -- 面试讲稿版

Asterwynd 的 SubAgent 系统解决的核心问题是：父 Agent 如何把复杂任务拆分给子 Agent 并行执行，同时保证安全和可控。

**子 Agent 的生成**通过 `SubAgentManager` 完成。父 Agent 调用 `CreateSubagent` 工具创建一个 session，指定 name、description 和 mode。创建时会做 mode clamping——子 Agent 的权限模式不能高于父 Agent。具体来说，READ_ONLY 和 PLAN 是级别 0，BUILD 是级别 1，BYPASS 是级别 2。如果父 Agent 是 read_only，子 Agent 请求 build，会被 clamp 回 read_only。

**运行机制**上，父 Agent 通过 `RunSubagent` 工具派发任务。每个子 Agent run 会创建一个新的 `AgentLoop` 实例，拥有独立的 ToolRegistry、MemoryManager 和消息历史。同一个 session 同一时间只能有一个活跃 run，防止并发冲突。父 Agent 可以选择 `wait=True` 同步等待结果，也可以异步派发后通过 `GetSubagentRun` 或 `InspectSubagentTranscript` 观察进度。

**递归防护**是整个设计的关键。子 Agent 的 AgentLoop 在构造时默认 `expose_subagent_tools=False`，这意味着子 Agent 的工具注册表中不包含 `CreateSubagent` 等 6 个 subagent 工具。即使 LLM 模型尝试调用这些工具，也会因为未知工具被拒绝。这从根源上杜绝了子 Agent 创建孙子 Agent 的可能性。此外还有两层兜底：mode clamping 确保权限不会升级，permission profile 中 `SUBAGENT_CONTROL` capability 只在 build 模式下可用。

**生命周期管理**围绕 session 和 run 两层状态。Session 在 idle 和 running 之间切换，每个 session 可以有多条历史 run 记录。Run 的状态包括 running、completed、failed、cancelled。`CancelSubagentRun` 工具通过 `asyncio.Task.cancel()` 取消正在执行的 run，并正确清理状态。无论 run 以何种方式结束，finally 块中都会 set 对应的 `asyncio.Event`，确保等待中的父 Agent 被唤醒。

**ParentChannel** 是基于 `asyncio.Queue` 的单向消息通道，支持非阻塞写入和带超时的异步读取，用于子 Agent 向父 Agent 回传结果。实际通信流程中，父 Agent 通过工具调用的 JSON 返回值获取子 Agent 的 run 结果，包括 status、summary、token 用量和 artifacts 列表。

总结来说，这套设计通过"工具注册控制 + mode clamping + permission profile"三层防护实现了安全的委托机制，让父 Agent 可以把任务分发给受限的子 Agent 并行执行，同时保证子 Agent 无法越权或无限递归。


---
## Q3: OpenSpec 工作流状态机——多阶段变更协议如何设计？


## Version A -- 详细参考版

### 1. 整体架构概述

Asterwynd 的 OpenSpec 工作流状态机由四层组件构成，采用状态机 + 持久化 + CLI 工具的组合设计：

| 层 | 文件 | 职责 |
|---|------|------|
| 数据模型 | `agent/workflow/models.py` | 定义 Phase、SubState、Transition、路由等所有数据结构 |
| 状态机引擎 | `agent/workflow/state_machine.py` | 实现状态转换验证、推进、Gate 检测、死锁处理 |
| 调度分发 | `agent/workflow/dispatcher.py` | 根据路由配置将各 Phase 分派给对应 executor |
| 路由配置 | `agent/workflow/routing.py` | 从 `openspec/config.yaml` 加载全局默认值，合并 per-change 覆盖 |
| 编排管理 | `agent/workflow/manager.py` | WorkflowManager 整合上述三层，提供统一 API |
| CLI 工具 | `scripts/workflow_state.py` | discover / advance / approve / validate 等命令行入口 |
| 机械验证 | `scripts/check_phase_done.py` | 只读阶段完成检查，Gate 前的自动化门禁 |

持久化载体是每个 change 目录下的 `handoff.json`，以 append-only transition 数组记录完整审计轨迹。


### 2. 七个 Phase 和各 Phase 的 sub_state 序列

定义位置：`agent/workflow/models.py` 第 8-82 行。

**七个 Phase**（第 8-9 行）：

```python
Phase = Literal["planning", "reviewing", "building", "code-review", "closing", "blocked", "done"]
PHASES: tuple[Phase, ...] = ("planning", "reviewing", "building", "code-review", "closing", "blocked", "done")
```

PHASE_ORDER 中 `blocked` 的 order 值为 -1（不属于主序列），`done` 为 5（终端）。

**五个主要 Phase 的 sub_state 序列**（第 49-79 行）：

**planning**（7 个 sub_state，第 49-52 行）：
```
exploring -> writing_proposal -> writing_design -> grilling_design -> writing_specs -> writing_tasks -> ready_for_review
```
特点：`grilling_design` 可以回退到 `writing_design`（设计追问-修改循环），也可以直接推进到 `writing_specs`。

**reviewing**（3 个 sub_state，第 54-56 行）：
```
reading_docs -> reviewing_design -> ready_for_review
```

**building**（6 个 sub_state，第 58-61 行）：
```
writing_tests -> test_failing -> implementing -> all_tests_passing -> smoke_validating -> ready_for_review
```
特点：内置 TDD 循环 -- `test_failing` 可回退到 `writing_tests`（测试写坏了）；`all_tests_passing` 可回退到 `implementing`（fix loop）；`smoke_validating` 失败也可回退到 `implementing`。这些循环在 `WITHIN_PHASE_ADJACENT`（state_machine.py 第 84-122 行）中定义为合法转换。

**code-review**（5 个 sub_state，第 63-66 行）：
```
reading_diff -> analyzing_tests -> reviewing_code -> requesting_changes -> ready_for_review
```
特点：`reviewing_code` 和 `requesting_changes` 构成双向循环（审查发现问题 -> 请求修改 -> 继续审查）。

**closing**（6 个 sub_state，第 68-71 行）：
```
syncing_specs -> archiving -> updating_backlog -> validating -> pr_ready -> ready_for_review
```

**blocked** 和 **done** 是终端 Phase，没有 sub_state（Phase -> SubState 映射中不包含它们，PHASE_SUB_STATES 第 73-79 行只包含五个主阶段）。


### 3. 阶段内转换 vs 跨阶段转换的验证规则

核心验证函数：`state_machine.py` 第 125-231 行的 `validate_transition(from_state, to_state, trigger)`。

**阶段内转换**（same phase，第 188-199 行）：

通过 `WITHIN_PHASE_ADJACENT` 字典（第 84-122 行）定义相邻关系。该字典记录了每个 phase 的每个 sub_state 可以到达的**下一个 sub_state 列表**。

例如 planning 阶段（第 85-93 行）：
```python
"writing_design": ["grilling_design", "writing_specs"],
"grilling_design": ["writing_design", "writing_specs"],  # loop back or advance
```

验证逻辑（第 189-199 行）：检查 `to_state.sub_state` 是否在 `from_state.sub_state` 的 `valid_next` 列表中，如果不在则抛出异常并提示合法目标。

**跨阶段前向转换**（cross-phase forward，第 216-231 行）：

必须从 `ready_for_review`（Gate）出发。合法目标由 `CROSS_PHASE_FORWARD` 字典定义（第 63-81 行）：

| 当前 Gate | 合法前向目标 |
|-----------|------------|
| `planning.ready_for_review` | `reviewing.reading_docs` 或 `building.writing_tests`（skip reviewing） |
| `reviewing.ready_for_review` | `building.writing_tests` |
| `building.ready_for_review` | `code-review.reading_diff` 或 `closing.syncing_specs`（skip code-review） |
| `code-review.ready_for_review` | `closing.syncing_specs` |
| `closing.ready_for_review` | `done` → None |

验证逻辑（第 217-231 行）：先检查 `from_state` 是否为 Gate（`_is_gate` 返回 True），然后匹配 `CROSS_PHASE_FORWARD` 中的 target tuple `(phase, sub_state)`。

**自环**（self-loop，第 156-169 行）：

`from_state == to_state` 的情况只允许 `handoff` trigger（用于记录交接时刻但不改变状态）。其他 trigger 的自环被禁止。

**任意阶段到 blocked**（第 138-143 行）：

任何非 done 阶段都可以直接进入 blocked，但已在 blocked 状态时不能再次进入。done 阶段不能进入 blocked。


### 4. Gate 机制（ready_for_review）作为人机决策点

**Gate 核心设计**：

Gate 子状态是 `"ready_for_review"`，定义为常量 `GATE_SUB_STATE`（models.py 第 81 行）。

`_is_gate(state)` 函数（state_machine.py 第 54-55 行）：
```python
def _is_gate(state: StateSnapshot) -> bool:
    return state.sub_state == GATE_SUB_STATE and state.phase not in ("blocked", "done")
```

每个主要 Phase 的最后一个 sub_state 都是 `ready_for_review`（参见 PHASE_SUB_STATES），这意味着每个 Phase 结束时都会触发 Gate。

**Gate 行为协议**（定义在 AGENTS.md 的 "Gate 停止规则" 中）：

1. **强制停止**：Agent 到达 Gate 后必须停止执行，不得修改代码、创建文件或推进状态。
2. **机械验证**：运行 `python3 scripts/check_phase_done.py --phase <current_phase> --change <change_id>` 进行自动化检查。
3. **结果呈现**：全部通过则列出通过项并等待人工审核；未通过则列出失败项说明需要修复。
4. **等人工指示**：用户必须明确说"批准"/"通过"/"继续"才能推进。
5. **记录批准**：通过 `python3 scripts/workflow_state.py approve --change <id> --phase <phase> --who human` 将批准记录写入 `.handoff/<change-id>/gate-approvals.json`（workflow_state.py 第 121-144 行）。

**Human 在 Gate 的三种决策**（Manager 提供对应方法）：

- **Approved**（manager.py 第 214-244 行 `human_approve`）：推进到下一个 Phase 的起始 sub_state。优先选择非 skip 路径（如 planning gate → reviewing，而非 skip 到 building）。
- **Skip**（manager.py 第 246-271 行 `human_skip`）：跳过一个 Phase。例如 planning gate 可以直接跳到 building（`forward[-1]` 取靠后的目标）。
- **Rollback**（manager.py 第 273-291 行 `human_rollback`）：回退到更早的 Phase。这是 Human 覆盖系统的核心能力。

**Gate 状态的持久化**：

当转换到达 Gate 时，`apply_transition`（state_machine.py 第 366-372 行）会自动更新 `handoff.json` 的 `last_gate` 字段为当前 Gate 的 phase 和 sub_state；离开 Gate 时清空 `last_gate` 为 None。


### 5. 死锁检测和恢复（blocked phase）

**blocked Phase 的设计**（models.py 第 8-9 行和第 29-37 行）：

`blocked` 是 Phase 枚举的正式成员，但在 `PHASE_ORDER` 中 order 为 -1（不在正常阶段序列中），且没有 sub_state 序列。

**进入 blocked**（state_machine.py 第 377-408 行 `enter_blocked`）：

- 任何非 done 阶段都可以进入 blocked（models.py 第 138-143 行的 `validate_transition` 中验证）
- 进入时记录 `Blocker` 对象（models.py 第 150-165 行），包含：
  - `blocked_from`: 进入 blocked 前的状态快照（用于恢复）
  - `reason`: 阻塞原因描述
  - `blocked_at`: 阻塞时间戳
  - `resolved_at`: 恢复时间戳（初始为 None）
- 使用 `trigger="auto"`, `actor_type="human"` 标记——意味着 block 操作被认为是人类级别的决策
- `blockers` 在 handoff.json 中是数组（`[]`），支持多个 blocker 共存——不是只有"当前 blocker"，而是完整的阻塞历史

**解除 blocked**（state_machine.py 第 411-440 行 `resolve_blocked`）：

- 当前状态必须是 `blocked`，否则报错
- 从 `blocked_from` 字段恢复原来的 phase 和 sub_state
- 设置 blocker 的 `resolved_at` 时间戳
- 创建一个从 `(blocked, None)` 到 `blocked_from` 的 transition

**死锁检测的实现层次**：

- **第一层（状态机层面）**：`blocked` 是唯一进入后只能由人工恢复的状态（`get_legal_targets` 第 241-242 行对 blocked 返回空列表，因为恢复目标由 `blocked_from` 决定而非状态机规则）。
- **第二层（会话启动协议）**：AGENTS.md 规定每次会话启动首先运行 `python3 scripts/workflow_state.py discover`，如果有 change 处于 blocked 状态会被列出，由人工决定下一步。
- **第三层（Manager API）**：`block(reason, actor_id)` 和 `unblock(blocker_index)` 提供编程接口（manager.py 第 293-308 行）。


### 6. 路由配置：inline / subagent / claude-code / codex 四种 executor

**Executor 类型定义**（models.py 第 18-19 行）：

```python
Executor = Literal["inline", "subagent", "claude-code", "codex"]
```

**三种 SessionMode**（models.py 第 21-22 行）：

```python
SessionMode = Literal["same", "new", "ask"]
```

- `same`：复用当前会话执行该 Phase
- `new`：为该 Phase 创建新会话
- `ask`：每次询问用户选择

**默认全局配置**（routing.py 第 30-55 行 `load_global_defaults`）：

从 `openspec/config.yaml` 的 `routing` 段加载。当前配置（`openspec/config.yaml` 第 28-43 行）：

```yaml
routing:
  planning:
    executor: inline
    session_mode: same
  reviewing:
    executor: codex
    session_mode: new
  building:
    executor: inline
    session_mode: same
  code-review:
    executor: codex
    session_mode: new
  closing:
    executor: inline
    session_mode: same
```

如果 config.yaml 不存在或解析失败，回退到硬编码的 `DEFAULT_ROUTING`（models.py 第 194-200 行）——planning/building/closing 用 inline/same，reviewing/code-review 用 subagent/new。

**合并策略**（routing.py 第 104-131 行 `merge_routing`）：

全局默认值被 per-change 的 handoff.json 中的 `routing` 字段覆盖。每个 Phase 独立覆盖：如果 handoff.json 中该 Phase 有 executor 或 session_mode 值，则替换对应字段。

**降级规则**（routing.py 第 92-101 行 `_apply_degradation`）：

非 inline executor + session_mode=same 是不合法组合（无法在同一个会话中执行外部工具），系统自动降级为 session_mode=new，并发出 warning。

**Dispatcher 如何使用路由**（dispatcher.py）：

`WorkflowDispatcher` 的 `_build_result`（第 150-175 行）根据 executor 类型生成不同结果：

- `inline`：返回 `inline_context`（change_dir、当前 state），调用方在同一会话中继续执行
- `subagent`：调用 `SubAgentManager` 创建子 agent，返回 subagent_id
- `claude-code` / `codex`：生成 CLI 命令字符串：`cat prompt.txt | {cli} exec - --cd <change_dir> --sandbox workspace-write`

如果 `subagent_manager` 未配置但 executor 为 subagent，退化为 inline 执行（dispatcher.py 第 201-204 行）。

路由配置附带可读标签（routing.py 第 161-181 行的中英文对照），用于在创建新 change 时向用户展示并确认。


### 7. handoff.json 的持久化和交接机制

**Schema**（`init_handoff_json` 在 state_machine.py 第 288-311 行定义）：

```json
{
  "schema_version": "1.0",
  "change_id": "<change-id>",
  "state": {"phase": "planning", "sub_state": "exploring"},
  "transitions": [],
  "current_agent": null,
  "last_gate": null,
  "blockers": [],
  "routing": { ... },
  "next_hints": {}
}
```

**原子写入**（state_machine.py 第 324-329 行 `save_handoff_json`）：

```python
def save_handoff_json(change_dir, data):
    path = Path(change_dir) / "handoff.json"
    tmp = str(path) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, str(path))  # 原子替换
```

先写入临时文件 `.tmp`，然后 `os.replace` 原子替换目标文件，防止写入过程中崩溃导致文件损坏。

**Transition 作为审计日志**：

每个 `Transition` 对象（models.py 第 96-128 行）记录：
- `from_state` / `to_state`: 状态快照
- `trigger`: auto / handoff / human_review / human_rollback
- `actor_type` / `actor_id`: 谁触发了转换
- `timestamp`: ISO 格式 UTC 时间戳
- 可选：`handoff_note`（交接笔记路径）、`decision`（approved/skip/rollback）、`reason`、`rollback_reason`、`skip_reason`

Transitions 数组永不删除，只追加。这构成了完整的可审计历史。

**Gate 状态追踪**：

`last_gate` 字段在到达 Gate 时自动写入当前 phase/sub_state，在离开 Gate 时清空为 null（state_machine.py 第 366-372 行 `apply_transition`）。

**交接机制（Handoff）**：

跨 Phase 推进时（AGENTS.md "跨阶段推进" 规定）：

1. 生成 Handoff note 写入 `.handoff/<change_id>/<from_phase>-to-<to_phase>.md`
2. Handoff note 中的关键决策必须包含 ADR 格式：决策标题、备选方案、拒绝原因、重访条件
3. 记录 Gate 批准到 `.handoff/<change_id>/gate-approvals.json`
4. `handoff.json` 推进到新 Phase 起始 sub_state

`compute_next_hints`（state_machine.py 第 450-465 行）为下一个 agent 计算推荐信息：`recommended_agent`（当前 Phase 对应角色）、`entry_point`（Handoff note 路径）、`priority_hints`（如果在 Gate 则列出下一阶段选项）。

Phase 到角色的映射（models.py 第 39-45 行 `PHASE_TO_ROLE`）：
- planning -> planner
- reviewing -> reviewer
- building -> builder
- code-review -> code-reviewer
- closing -> closer

每个角色的 system prompt 定义在 `agent/workflow/role_registry.py` 中（第 7-65 行），描述了该角色的工作流程、产出物、check_phase_done 调用要求。


### 8. human_rollback 能力

**定义**（models.py 第 13 行）：

```python
Trigger = Literal["auto", "handoff", "human_review", "human_rollback"]
```

`human_rollback` 是四种 trigger 之一。它在 `validate_transition` 中有三种特有行为：

**行为一：阶段内回退**（state_machine.py 第 172-186 行）

当 `trigger == "human_rollback"` 且 `from_state.phase == to_state.phase`：
- 验证 `from_state.sub_state` 和 `to_state.sub_state` 都在该 phase 的 sub_state 序列中
- `from_idx` 必须大于 `to_idx`（目标必须在当前之前）
- 可以跨多个子状态回退（例如从 `ready_for_review` 直接回退到 `exploring`），不需要逐级经过每个中间子状态

**行为二：跨阶段回退**（state_machine.py 第 202-214 行）

当 `trigger == "human_rollback"` 且 `from_state.phase != to_state.phase`：
- 目标 phase 的 order 必须小于当前 phase 的 order（更早）
- 但目标 phase 必须在主序列中（order != -1，即不能回退到 blocked）
- 不要求 from_state 是 Gate——可以从任何 sub_state 发起跨阶段回退
- to_state 的 sub_state 必须是有效值

**行为三：禁止项**
- 从 done 状态不能 rollback（done 是最终终态，在检查到 to_phase == "done" 时被拒绝，见第 148-154 行和第 152-153 行）
- 从 blocked 状态不能 rollback（进入 blocked 即意味流程堵塞，需要先 resolve_blocked 恢复）

**Manager 封装**（manager.py 第 273-291 行 `human_rollback`）：

```python
def human_rollback(self, target_phase, target_sub_state, actor_id, rollback_reason):
    if self.current_phase in ("blocked", "done"):
        raise StateMachineError("cannot rollback from blocked or done")
    return self.transition(
        to_phase=target_phase, to_sub_state=target_sub_state,
        trigger="human_rollback", actor_type="human", actor_id=actor_id,
        decision="rollback", rollback_reason=rollback_reason,
    )
```


### 9. 机械验证体系（check_phase_done.py）

每个 Phase 在 ready_for_review 之前，通过 `scripts/check_phase_done.py` 进行只读机械验证：

| Phase | 验证内容（check_phase_done.py 行号） |
|-------|-------------------------------------|
| planning (110-137) | 调用 artifact checker 检查 proposal/design/spec delta/tasks 结构；handoff.json 是否为 planning.ready_for_review |
| building (140-182) | pytest 全量通过（300s 超时）；Python 文件无 TODO/TBD/FIXME/HACK 残留；benchmark smoke 测试通过；handoff.json 是否为 building.ready_for_review |
| code-review (185-215) | 是否存在评审报告（review-report.md 或 .json）；报告不包含 CHANGES_REQUESTED；handoff.json 是否为 code-review.ready_for_review |
| closing (218-274) | openspec validate --strict 通过；change 已归档到 archive/；backlog 一致性检查；artifact checker 最终校验；handoff.json 为 closing.ready_for_review 或 done |

该脚本采用只读设计：`"""Read-only phase completion verification. Never modifies files."""`（第 2 行）。


### 10. 关键设计决策总结

1. **两个终端 phase（blocked 和 done）不参与正常阶段序列**，PHASE_ORDER 中 order 分别为 -1 和 5，而主序列是 0-4（planning 到 closing）。

2. **Gate 是单向串行的强制停止点**：前向跨阶段转换只能从 Gate 出发，这意味着 agent 不能跳过 ready_for_review 直接进入下一 Phase。

3. **Human 覆盖的两条路径**：`human_rollback` 可以绕过 Gate 限制进行回退（不要求 from_state 是 Gate），而 `human_review`（approve/skip）则严格遵守 Gate 起点规则。

4. **Skip 路径提供流程灵活性**：planning gate 可以 skip reviewing 直接进 building；building gate 可以 skip code-review 直接进 closing。Skip 通过 `forward[-1]` 选择靠后的目标实现。

5. **blocker 数组支持多次阻塞-恢复循环**：每次 `enter_blocked` 追加新 entry，`resolve_blocked` 通过 `blocker_index` 参数可以指定恢复哪一个。

6. **路由配置采用全局默认 + per-change 覆盖的二级合并策略**，确保每个 change 可以根据复杂度独立调整执行策略。

7. **副 agent 系统通过 role_registry 实现角色化提示词**：每个 RoleAgentType 有专属 system prompt，子 agent 以此理解自己的工作流程、产出物和验收标准。


## Version B -- 面试讲稿版

Asterwynd 的 OpenSpec 工作流状态机是一个五阶段多 agent 协作协议，核心解决一个问题：如何让多个不同职责的 agent 串行协作开发同一个 change，同时保证每个阶段有人类审查决策点。

整个状态机定义在 `agent/workflow/` 目录下，持久化载体是每个 change 目录下的 `handoff.json`。状态定义在 `models.py`，转换引擎在 `state_machine.py`，编排在 `manager.py`，CLI 工具在 `scripts/workflow_state.py`。

首先是七个 Phase。五个主阶段是 planning、reviewing、building、code-review、closing，外加两个特殊阶段 blocked 和 done。每个主阶段内部有一个线性的 sub_state 序列，但部分阶段内建了迭代循环。比如 building 阶段支持 TDD 循环——test_failing 可以回到 writing_tests，implementing 和 all_tests_passing 之间也有双向循环。planning 阶段的 grilling_design 支持设计追问和修改迭代。

阶段内转换通过 WITHIN_PHASE_ADJACENT 字典定义的邻接关系来验证，保证 sub_state 按序推进，只允许合法循环。跨阶段前向转换只能从 ready_for_review 这个 Gate 子状态出发，通过 CROSS_PHASE_FORWARD 映射表定义合法目标。这保证了每个阶段结束时必须经过人工 Gate。

Gate 机制是整个人机协作的核心。每个主阶段最后一个 sub_state 都是 ready_for_review。agent 到达 Gate 后必须强制停止，运行 check_phase_done.py 做机械验证——比如 building 阶段会跑 pytest 全量测试、扫描 TODO 残留、跑 benchmark smoke——然后等待人工审批。人工在 Gate 有三种选择：approve 推进到下一阶段、skip 跳过一个阶段、rollback 回退到更早阶段。

Deadlock 的检测和恢复通过 blocked phase 实现。当遇到无法自动解决的阻塞问题时，系统可以从任何非 done 状态进入 blocked。blocked 记录 blocker 对象，包含原始状态快照 blocked_from、阻塞原因和时间戳。恢复时从 blocked_from 恢复原来的位置。blockers 是数组，支持多次阻塞-恢复循环。另外在 AGENTS.md 的会话启动协议中，每次新会话先跑 discover 命令列出所有 change 状态，如果发现有 change 卡在 blocked 会特别标注。

路由配置支持四种 executor：inline 在当前会话执行、subagent 创建子 agent、claude-code 和 codex 分别调用外部 CLI。配置分为两层：openspec/config.yaml 的全局默认值和 handoff.json 的 per-change 覆盖，合并时 per-change 优先。当前默认配置把 planning、building、closing 设为 inline/same，reviewing 和 code-review 设为 codex/new，对应"写代码在本地，审代码用外部工具"的思路。

handoff.json 的持久化采用原子写入——先写 .tmp 再 os.replace，防止崩溃损坏文件。每次转换追加一条 transition 记录，包含 from/to 状态、trigger 类型、actor 信息和 UTC 时间戳，形成完整的审计轨迹。跨阶段交接时还会生成 handoff note，关键决策以 ADR 格式记录。

human_rollback 是该协议最重要的容错能力。它支持阶段内跨多步回退（比如从 ready_for_review 直接回到 exploring），也支持跨阶段回退到任意更早 phase。human_rollback 不要求从 Gate 出发——就是说即使开发做到一半发现方向错了，也可以随时回退。但 done 是最终终态，不支持 rollback。

整个状态机体系的设计哲学是：让 agent 可以自动推进日常的子状态流转，但在关键决策点（每个 Phase 结束）强制插入人类判断，同时通过 rollback 机制保证永远不会进入无法恢复的死路。机械验证脚本作为 Gate 前的自动化门禁，确保每个 Phase 的基本质量不依赖人类逐项检查。


---
## Q4: LLM Provider 适配器——如何支持多个 LLM 提供商？



### A — 详细参考版

### 一、整体架构：三层设计

Asterwynd 的 LLM provider 架构分为三层：

1. **LLM Protocol** (`agent/llm.py` 第 19-28 行) — 纯接口，定义 `async def chat(messages, tools, model) -> LLMResponse`，使用 `typing.Protocol` + `@runtime_checkable` 实现结构类型检查。
2. **BaseLLM 基类** (`agent/llm.py` 第 48-119 行) — 提供共享基础设施：httpx AsyncClient 管理、SSE 流式解析、多 provider 共享的业务逻辑和策略函数。
3. **具体实现类** — `AnthropicLLM` (`agent/anthropic_llm.py`) 和 `OpenAILLM` (`agent/openai_llm.py`)，各自持有认证头、端点 URL、消息格式转换和响应解析。

Provider 的选择通过 `agent/main.py` 中的 `build_llm(provider, model)` 函数（第 77-101 行）实现：根据 `--provider` CLI 参数（或 `ASTERWYND_PROVIDER` 环境变量）分发到对应类，`"anthropic"` 创建 `AnthropicLLM`，其余默认创建 `OpenAILLM`。

### 二、LLM Protocol vs BaseLLM 的设计差异

| 维度 | LLM Protocol | BaseLLM |
|------|-------------|---------|
| 文件位置 | `agent/llm.py:19-28` | `agent/llm.py:48-119` |
| 类型 | `typing.Protocol`（结构子类型，无需显式继承） | 普通类 |
| 职责 | 只定义调用契约：`chat()` 方法签名 | 提供共享基础设施 |
| 包含内容 | 仅 `chat()` 抽象方法 | 构造函数、HTTP 客户端懒初始化、SSE 解析器、资源释放 |
| 使用者 | `AgentLoop` 等消费者通过 Protocol 类型注解引用（不依赖具体类） | 具体 LLM 类继承它获得共享能力 |

**关键设计决策**：Protocol 与 BaseClass 分离，使 AgentLoop 等消费者通过 `LLM` Protocol 类型注解引用 provider（`agent/loop.py:832`），不依赖具体实现类。同时 BaseLLM 避免代码重复——`_get_client()` 使用 `asyncio.Lock` 实现线程安全的 HTTP 客户端懒初始化（`agent/llm.py:75-87`），并根据 `self.stream` 标志动态调整 read timeout（流式 60s / 非流式 180s）。

### 三、流式传输如何跨提供商工作

#### 3.1 SSE 解析（共享层）

`BaseLLM._stream_events()` (`agent/llm.py:89-106`) 是 SSE 解析的共享实现：

```python
async def _stream_events(self, url: str, json: dict):
    client = await self._get_client()
    async with client.stream("POST", url, json=json) as response:
        response.raise_for_status()
        event_type = None
        async for line in response.aiter_lines():
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                yield event_type, data
                event_type = None
```

按 SSE 协议逐行解析 `event:` 和 `data:` 前缀，忽略 JSON 解析失败行（第 103 行 `continue`）。两个提供商的流式方法都调用此方法，区别只在于对 `(event_type, data)` 元组的处理逻辑。

#### 3.2 Anthropic 流式实现 (`agent/anthropic_llm.py:247-294`)

Anthropic SSE 事件分为四类，按 **content block index** 累积：

- **`content_block_start`** (第 265-274 行)：初始化 block 字典 `{index: {type, id, name, text_parts, json_parts}}`
- **`content_block_delta`** (第 276-285 行)：根据 `delta.type` 区分 `text_delta`（追加到 text_parts）和 `input_json_delta`（追加到 json_parts）
- **`message_delta`** (第 287-289 行)：提取 `stop_reason` 并通过映射表转换（`"end_turn"`→`"end_turn"`, `"tool_use"`→`"tool_calls"`, `"stop_sequence"`→`"stop"`, `"max_tokens"`→`"max_tokens"`）
- **`error`** (第 291-292 行)：抛出 RuntimeError

流式累积完成后，调用 `_build_response()` (第 364-394 行) 将 blocks 字典转为统一的 `LLMResponse`：text block 拼接 text_parts，tool_use block 累积 json_parts 后 `json.loads` 构造 `ToolCallDelta`。

Anthropic 还提供独立的 `stream_chat()` 方法 (第 138-175 行)，在 `_stream_chat_impl` 中额外 yield `LLMStreamEvent(type="assistant_delta")` 实现增量文本推送。

#### 3.3 OpenAI 流式实现 (`agent/openai_llm.py:155-231`)

OpenAI SSE 格式不同：所有信息通过 `choices[0].delta` 传递，无 content_block 事件。关键处理：

- **文本增量** (第 191-198 行)：`delta.content` 追加到 `content_parts`，yield `LLMStreamEvent(type="assistant_delta")`
- **推理内容** (第 188-189 行)：累积 `delta.reasoning_content`（支持 DeepSeek-R1 等思维链模型）
- **工具调用增量** (第 200-209 行)：`delta.tool_calls` 按 `index` 分桶到 `tool_buffers` 字典，逐个累积 `id`、`function.name`、`function.arguments`

流式结束后 (第 211-231 行)，将 `tool_buffers` 转为 `ToolCallDelta` 列表，构造包含 `reasoning_content` 的 `LLMResponse`，yield `LLMStreamEvent(type="complete")`。

#### 3.4 代理层调用

`AgentLoop` (`agent/loop.py:828-878`) 通过 `_should_stream_llm()` 判断是否使用流式：检查 LLM 实例是否有 `stream_chat` 方法且 `self.stream` 为 True。如果有，调用 `stream_chat()` 并收集 `assistant_delta` 事件推送给 WebSocket/回调；最终 `complete` 事件返回完整 `LLMResponse`。

### 四、视觉支持策略

视觉支持的实现分布在 `agent/llm.py:122-167`，核心是两个函数：

**`supports_vision(model)`** (`agent/llm.py:133-135`)：
```python
VISION_MODEL_PREFIXES = ("gpt-4o", "gpt-4.1", "gpt-5", "claude-", "gemini-")
def supports_vision(model: str) -> bool:
    return model.startswith(VISION_MODEL_PREFIXES)
```
按模型前缀白名单判断。所有 `claude-` 前缀模型默认支持视觉，OpenAI 只有 4o/4.1/5 系列。

**`vision_mode(model)`** (`agent/llm.py:138-145`)：
- 已知视觉模型 → 返回 `"vision"`，直接发送图片
- 未知模型 → 返回 `"try_vision"`，先尝试发送图片，400 后降级重试

**try_vision 降级机制** 在两个 provider 中实现一致（模式相同）：

1. 检查 `mode == "try_vision" and has_images` 决定是否启用 `try_vision` 标志
2. 首次请求带着图片发送（`force_vision=True`）
3. 捕获异常后调用 `_is_400_error()` (`agent/llm.py:159-167`) 判断：`isinstance(exc, httpx.HTTPStatusError) and status_code == 400`
4. 如果是 400 且 `try_vision=True`：记录日志，重建 payload（`force_vision=False`），重试
5. 非视觉模式下，ImageBlock 被降级为文本引用 `"[image: ref]"`

Anthropic 的降级逻辑在 `_content_to_anthropic()` (第 405-420 行)：非视觉时 ImageBlock → `{"type": "text", "text": "[image: <file_path or 'pasted image'>]"}`。OpenAI 相同逻辑在 `_block_to_openai()` 和 `_build_openai_messages()` 中。

**OpenAI 特有**：`_build_openai_messages()` (`agent/openai_llm.py:250-288`) 额外处理图片注入——如果 tool 消息包含 ImageBlock，先将图片收集到 `image_buffer`，遇到非 tool 消息时 flush 为合成 user 消息。这是因为 OpenAI Chat Completions API 中只有 `role=user` 的消息可以带图片 content array。

### 五、AnthropicLLM 和 OpenAILLM 的具体实现差异

| 维度 | AnthropicLLM | OpenAILLM |
|------|-------------|-----------|
| **文件** | `agent/anthropic_llm.py` | `agent/openai_llm.py` |
| **默认 base_url** | `https://api.anthropic.com` | `https://api.openai.com/v1` |
| **默认模型** | `claude-sonnet-4-20250514` | `gpt-4` |
| **认证头** | `x-api-key` + `anthropic-version: 2023-06-01` (第 34-39 行) | `Authorization: Bearer` (第 27 行) |
| **端点** | `POST /v1/messages` | `POST /chat/completions` |
| **System 消息** | 独立 `system` 字段（字符串数组）(第 131-132 行) | `role: "system"` 消息 |
| **消息格式** | `content` 为 content block 数组，含 `type: "text"/"tool_use"/"tool_result"` | `content` 为字符串或 content array（仅 user），含 `type: "text"/"image_url"` |
| **Tool 定义** | `{name, description, input_schema}` | `{type: "function", function: {name, description, parameters}}` |
| **工具调用响应** | `tool_use` block 中的 `input` 为已解析的 dict | `tool_calls[i].function.arguments` 为 JSON 字符串 |
| **推理内容** | 不支持（API 层面） | 支持 `reasoning_content`（DeepSeek-R1 等）(第 103 行) |
| **Surrogate 处理** | 有 `_strip_surrogates()` (第 14-18 行)，剔除 U+D800-U+DFFF 字符防止 `json.dumps` 崩溃 | 无（OpenAI API 对此更宽容） |
| **Tool result 合并** | 连续 tool 消息合并为同一 user 消息中的多个 `tool_result` block（第 116-120 行，Anthropic API 要求） | 无此要求 |
| **流式差异** | 按 content_block index 累积，区分 `text_delta`/`input_json_delta` | 按 tool_calls index 分桶累积 |
| **日志** | `asterwynd.llm.anthropic` | `asterwynd.llm.openai` |
| **Max tokens** | 默认 16384 | 默认 16384（继承 BaseLLM） |

### 六、添加新提供商需要实现什么

以 Google Gemini 为例，新增 provider 需要实现以下内容：

#### 6.1 创建 LLM 实现类

需要继承 `BaseLLM` 并实现：

1. **`_get_headers()`** — 返回认证头（例如 Gemini API key）
2. **`chat(messages, tools, model)`** — 核心调用方法，包含：
   - 消息格式转换（`Message` → provider 原生格式）
   - Tool schema 转换（`Tool.get_schema()` 的 OpenAI 格式 → provider 格式）
   - HTTP 请求发送（使用 `self._get_client()`）
   - 响应解析 → 统一 `LLMResponse`
   - try_vision 降级重试逻辑
3. **可选 `stream_chat(messages, tools, model)`** — 流式输出 async generator，yield `LLMStreamEvent`
4. **消息转换方法**：
   - `_content_to_X(content, force_vision)` — `ContentBlock` → provider 格式（含图片降级）
   - `_system_content_to_X(content)` — system 消息处理
   - 处理 `tool_call_id`（如果 provider 的 tool result 格式不同）
5. **`_convert_tool(tool: dict)`** — 将 OpenAI function 格式转为 provider 格式

#### 6.2 注册 Provider

在 `agent/main.py` 的 `build_llm()` 函数（第 77-101 行）中添加新的 `if provider == "gemini"` 分支，读取对应环境变量（如 `GEMINI_API_KEY`、`GEMINI_BASE_URL`），创建 GeminiLLM 实例。

#### 6.3 导出

在 `agent/__init__.py` 中添加 import 和 `__all__` 条目。

#### 6.4 视觉模型前缀（如需要）

如果新 provider 的模型需要视觉支持，在 `agent/llm.py` 的 `VISION_MODEL_PREFIXES` 中添加对应前缀。

### 七、工具调用格式如何转换

#### 7.1 工具定义的内部表示

工具定义在 `agent/tools/base.py:53-61` 使用 OpenAI 函数调用格式作为内部标准：

```python
def get_schema(self) -> dict:
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,  # JSON Schema
        },
    }
```

所有工具通过 `Tool.get_schema()` 产出此格式，并直接被 OpenAILLM 用于 `payload["tools"]`（`agent/openai_llm.py:48`）。

#### 7.2 Anthropic 格式转换

`AnthropicLLM._convert_tool()` (`agent/anthropic_llm.py:396-403`) 将 OpenAI function 格式转为 Anthropic tool 格式：

```python
def _convert_tool(self, tool: dict) -> dict:
    func = tool.get("function", tool)
    return {
        "name": func["name"],
        "description": func.get("description", ""),
        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
    }
```

关键映射：
- `function.name` → `name`
- `function.description` → `description`
- `function.parameters` → `input_schema`（Anthropic 命名）

在 `_build_payload()` 中调用：`payload["tools"] = [self._convert_tool(tool) for tool in tools]`（`agent/anthropic_llm.py:134`）。

#### 7.3 工具调用响应的统一

两个 provider 的响应都统一为 `ToolCallDelta` 数据类（`agent/llm.py:12-15`）：

```python
@dataclass
class ToolCallDelta:
    id: str
    name: str
    arguments: str  # JSON string
```

**Anthropic 响应解析**：
- 非流式 (`agent/anthropic_llm.py:335-341`)：遍历 `data["content"]`，遇到 `type: "tool_use"` 的 block，取 `block["id"]`、`block["name"]`，将 `block["input"]` (dict) 重新 `json.dumps` 回字符串
- 流式 (`agent/anthropic_llm.py:374-381`)：累积 `json_parts`，`"".join()` 后 `json.loads` 验证 JSON 合法性，再 `json.dumps` 回去

Anthropic API 中的 `tool_use.input` 是已解析的 JSON 对象（dict），而内部表示需要 JSON 字符串，所以做了一次 `json.dumps(input_dict)` 的"再序列化"。

**OpenAI 响应解析**：
- 非流式 (`agent/openai_llm.py:105-113`)：直接读取 `tc["id"]`、`tc["function"]["name"]`、`tc["function"]["arguments"]`（已是 JSON 字符串）
- 流式 (`agent/openai_llm.py:200-209`)：按 index 分桶累积，`tool_delta.function.arguments` 是增量 JSON 片段，直接字符串拼接

OpenAI API 的工具调用参数本身就是 JSON 字符串，无需转换。

#### 7.4 Assistant 工具调用回传格式差异

在构建消息历史时，assistant 消息中的工具调用以不同格式回传给 API：

**Anthropic** (`agent/anthropic_llm.py:92-107`)：assistant 消息的 content 是 content block 数组，包含 `type: "text"` 和 `type: "tool_use"` 两种 block。文本必须在 tool_use 之前（第 94 行注释说明 DeepSeek Anthropic endpoint 的要求）。`tool_use` block 中 `input` 是 dict（解析后的 JSON 对象）。

**OpenAI** (`agent/openai_llm.py:237-248`)：assistant 消息通过 `_message_to_dict()` 序列化，`tool_calls` 以 `{id, type: "function", function: {name, arguments}}` 格式附加。`arguments` 保持 JSON 字符串格式。

#### 7.5 Tool Result 消息格式差异

两个 provider 对工具执行结果也有不同格式要求：

**Anthropic** (`agent/anthropic_llm.py:108-124`)：tool 消息转为 `type: "tool_result"` content block，包含 `tool_use_id` 和 `content`（文本或 content blocks）。关键约束是 Anthropic API 要求同一 assistant turn 的所有 tool_result 必须在同一个 user 消息中——代码通过检查前一条消息是否已含 tool_result 来决定合并还是新建（第 116-120 行）。

**OpenAI** (`agent/openai_llm.py:260-276`)：tool 消息使用 `role: "tool"` + `tool_call_id` 字段。OpenAI 的 tool 消息只能包含文本 content（纯字符串），图片会被提取到 image_buffer 延迟 flush 为合成 user 消息。



### B — 面试讲稿
>
> Asterwynd 的 LLM provider 架构采用三层设计。最底层是一个 Protocol 接口，只定义 `chat()` 方法签名，让 AgentLoop 等消费方通过结构类型引用，不依赖具体实现。中间层是 BaseLLM 基类，提供 httpx AsyncClient 的懒初始化、SSE 流式解析器和资源释放等共享能力。顶层是 AnthropicLLM 和 OpenAILLM 两个具体实现，各自处理认证头、端点、消息格式转换和响应解析。
>
> 流式传输这块，BaseLLM 提供了一个通用的 SSE 解析器，按 event 和 data 行解析。两个 provider 都调用它，但处理逻辑不同。Anthropic 的 SSE 事件有四类：content_block_start 初始化 block，content_block_delta 按 index 累积 text_delta 或 input_json_delta，message_delta 提取 stop_reason，最后 build_response 拼出统一结果。OpenAI 更简单，所有信息通过 choices[0].delta 传递，工具调用按 index 分桶累积。AgentLoop 那边通过检查实例是否有 stream_chat 方法且 stream 标志为 True 来决定走流式还是非流式。
>
> 视觉支持上，用模型前缀白名单判断 supports_vision，返回 "vision" 或 "try_vision"。try_vision 的机制是：先带图片发请求，遇到 400 错误就捕获，降级重试，把 ImageBlock 替换成文本引用 "[image: file_path]"。这个降级逻辑在两个 provider 中模式一致，都要在 chat 和 stream_chat 两个路径里实现。
>
> 两个具体实现的差异挺多。认证上，Anthropic 用 x-api-key 加 anthropic-version 头，OpenAI 用 Bearer token。消息格式上，Anthropic 的 system 是独立字段，assistant 回复里 tool_use 和 text 是 content block，tool result 要合并在同一个 user 消息里。OpenAI 则 system 就是普通 role 消息，tool 消息用 tool_call_id 字段。还有一个细节是 AnthropicLLM 需要 strip_surrogates 去掉 Unicode surrogate 字符，防止 json.dumps 崩溃。另外 OpenAILLM 支持 reasoning_content，适配 DeepSeek-R1 这些推理模型，Anthropic 目前没有。
>
> 工具调用格式上，内部标准是 OpenAI 的 function call 格式，`get_schema()` 返回 `{type: "function", function: {name, description, parameters}}`。AnthropicLLM 通过 `_convert_tool` 转成 Anthropic 的 `{name, description, input_schema}`。响应解析时也有差异：Anthropic 的 tool_use.input 是已解析的 dict，需要 json.dumps 回字符串；OpenAI 的 function.arguments 本身就是 JSON 字符串，直接拿来用。
>
> 如果要新增 provider，比如 Gemini，需要继承 BaseLLM，实现 `_get_headers`、`chat`（含消息转换、try_vision 降级）、可选的 `stream_chat`、以及 tool schema 转换；然后在 `build_llm()` 里加一个分支，读取对应的环境变量创建实例，最后在 `__init__.py` 导出。整体架构对新 provider 是开放的，工作量主要在消息格式适配上。
>

---
## Q5: MCP 集成——如何接入 Model Context Protocol？



### A — 详细参考版

### 1. 传输方式（stdio vs HTTP）

Asterwynd 支持两种 MCP 传输方式，由配置文件 `asterwynd.yaml` 中每个 server 的 `type` 字段决定：

| 传输方式 | type 值 | 底层实现 | 必需配置字段 |
|---------|---------|---------|------------|
| **stdio** | `"stdio"` | `mcp.client.stdio.stdio_client` + `StdioServerParameters` | `command` |
| **HTTP (Streamable)** | `"streamable_http"` | `mcp.client.streamable_http.streamable_http_client` | `url` |

**文件**: `agent/mcp/manager.py` 第 92-119 行 (`_connect_server`)

- **stdio 路径** (`manager.py:97-106`): 构造 `StdioServerParameters(command, args, env, cwd)`，通过 `self._exit_stack.enter_async_context(stdio_client(params))` 获取 `(read_stream, write_stream)`。支持可选的 `cwd` 和 `env` 配置。
- **HTTP 路径** (`manager.py:107-119`): 先创建 `httpx.AsyncClient`（带有自定义 headers 和超时），再通过 `streamable_http_client(url, http_client)` 获取 `(read_stream, write_stream, _)`。HTTP headers 支持两种来源：直接值 (`value`) 或环境变量 (`env`)，解析在 `manager.py:231-238` 的 `_resolve_headers()` 中。

### 2. MCP 配置结构

**文件**: `agent/config.py` 第 112-128 行 (`McpServerConfig`)

每个 MCP Server 的配置 dataclass 包含：

```python
@dataclass(frozen=True)
class McpServerConfig:
    name: str
    type: Literal["stdio", "streamable_http"]
    enabled: bool = True                 # 是否启用
    required: bool = False               # 启动失败是否致命
    command: str | None = None           # (stdio) 命令
    args: tuple[str, ...] = ()
    cwd: Path | None = None              # (stdio) 工作目录
    env: dict[str, str] = {}
    url: str | None = None               # (HTTP) 服务地址
    headers: dict[str, McpHeaderValueConfig] = {}
    startup_timeout_seconds: int = 10    # 启动超时
    tool_timeout_seconds: int = 30       # 单个工具调用超时
    default_permission: McpActionPermissionConfig | None = None  # 服务器级默认权限
    tools: dict[str, McpActionPermissionConfig] = {}     # 逐工具权限
    prompts: dict[str, McpActionPermissionConfig] = {}   # 逐 prompt 权限
    resources: dict[str, McpActionPermissionConfig] = {} # 逐资源权限
```

顶层配置在 `MCPConfig` (`config.py:132-134`):
```python
@dataclass(frozen=True)
class McpConfig:
    default_timeout_seconds: int = 30
    servers: dict[str, McpServerConfig] = {}
```

### 3. MCP 工具如何注册到 Agent 工具系统

注册链路共三步：

**Step 1: 启动时创建 McpManager**

**文件**: `agent/main.py:167`

```python
mcp_manager = await build_mcp_manager(config)
```

`build_mcp_manager` (`manager.py:225-228`) 实例化 `McpManager` 并调用 `connect_from_config(config)`。

**Step 2: connect_from_config 连接每个 Server**

**文件**: `agent/mcp/manager.py:65-90`

对 `config.mcp.servers` 中的每个 server：
- 如果 `enabled=False`，标记状态为 `ready=False, error="disabled"`，跳过。
- 否则，在 `asyncio.timeout(server_config.startup_timeout_seconds)` 超时保护下调用 `_connect_server()`。
- 连接失败时：如果 `required=True`，先 `aclose()` 清理所有已建立的连接，再 `raise RuntimeError` 终止启动（`manager.py:86-90`）；如果 `required=False`，记录错误状态但不中断。

**Step 3: _connect_server 发现并索引工具**

**文件**: `agent/mcp/manager.py:92-179`

连接成功后：
1. 创建 `ClientSession` 并 `session.initialize()`
2. 调用 `session.list_tools()`, `session.list_prompts()`, `session.list_resources()` 发现所有能力
3. 对每个 tool，使用命名函数生成 `callable_name`，通过 `ensure_unique_name()` 解决冲突，存入 `self._tools[callable_name] = McpToolMetadata(...)`
4. 对每个 prompt / resource 同理存入 `self._prompts` / `self._resources`

**Step 4: 工厂函数构建 McpTool 实例并注册到 ToolRegistry**

**文件**: `agent/tools/factory.py:104-107`

```python
def _build_mcp_tools(mcp_manager: McpManager | None) -> list[Tool]:
    if mcp_manager is None:
        return []
    return [McpTool(metadata, mcp_manager) for metadata in mcp_manager.tools]
```

在 `build_default_tool_registry()` (`factory.py:98`) 中，MCP 工具追加到内置工具列表后：

```python
for tool in [*default_tools, *_build_mcp_tools(mcp_manager)]:
    registry.register(tool)
```

`ToolRegistry.register()` (`registry.py:16-17`) 以 `tool.name` 为 key 存入字典。

### 4. 命名冲突解决机制（ensure_unique_name）

**文件**: `agent/mcp/naming.py`

**sanitize_mcp_name** (第 10-16 行):
- 将非字母数字下划线字符替换为 `_`
- 去除首尾下划线
- 若全为空则返回 `"unnamed"`
- 若以数字开头则前加 `_`（如 `"9tool"` -> `"_9tool"`）

**命名格式** (第 19-29 行):
- Tool: `mcp__{sanitized_server}__{sanitized_tool}`
- Prompt: `mcp__{sanitized_server}__prompt__{sanitized_prompt}`
- Resource: `mcp__{sanitized_server}__resource__{sha1(uri)[:8]}`（资源 URI 可能含特殊字符，用 SHA1 摘要代替）

**ensure_unique_name** (第 32-43 行):

```python
def ensure_unique_name(name: str, raw_identity: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    digest = hashlib.sha1(raw_identity.encode("utf-8")).hexdigest()[:8]
    candidate = f"{name}_{digest}"
    counter = 2
    while candidate in used:
        candidate = f"{name}_{digest}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate
```

策略：
1. 若 `name` 未被占用，直接返回。
2. 若冲突，追加 `_<sha1(raw_identity)[:8]>`（如 `mcp__github__search__a1b2c3d4`）
3. 仍冲突则追加计数器 `_<counter>`（如 `_a1b2c3d4_2`, `_a1b2c3d4_3`...）

`used_names` 集合在 `connect_from_config` (`manager.py:66`) 中初始化，包含所有已注册工具的 `callable_name`，每次 `ensure_unique_name` 成功后都会 `used.add(candidate)`。

### 5. 权限配置（per-tool、per-prompt、per-resource）

**文件**: `agent/config.py:99-108` (`McpActionPermissionConfig`), `agent/mcp/manager.py:255-268` (`_permission_for`), `agent/mcp/types.py:15-19` (`DEFAULT_MCP_PERMISSION`)

**权限粒度**:
- `default_permission`: 服务器级别默认，应用于该 server 下所有未单独配置的 tool/prompt/resource
- `tools`: `dict[str, McpActionPermissionConfig]` — 逐工具配置
- `prompts`: `dict[str, McpActionPermissionConfig]` — 逐 prompt 配置
- `resources`: `dict[str, McpActionPermissionConfig]` — 逐资源配置

**McpActionPermissionConfig** 字段:
- `capabilities: tuple[ToolCapability, ...]` — 能力标签（如 `WORKSPACE_READ`, `EXTERNAL_SIDE_EFFECT`）
- `risk_level: ToolRiskLevel` — 风险等级（`low` / `medium` / `high`）

**权限解析优先级** (`_permission_for`, `manager.py:255-268`):
1. 按 kind (`TOOL`/`PROMPT`/`RESOURCE`) 查对应细粒度配置字典
2. 若未命中，使用 `server_config.default_permission`
3. 若仍未设置，使用 `DEFAULT_MCP_PERMISSION`

**DEFAULT_MCP_PERMISSION** (`types.py:15-19`):
```python
DEFAULT_MCP_PERMISSION = ToolPermission(
    capabilities=frozenset({ToolCapability.EXTERNAL_SIDE_EFFECT}),
    risk_level=ToolRiskLevel.HIGH,
    origin=ToolOrigin.MCP,
)
```
所有 MCP 工具默认标记为 `EXTERNAL_SIDE_EFFECT`、`HIGH` 风险、`MCP` 来源。

**YAML 配置示例结构**:
```yaml
mcp:
  servers:
    github:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-github"]
      default_permission:
        capabilities: ["external_side_effect"]
        risk_level: "high"
      tools:
        search_repositories:
          capabilities: ["network_read"]
          risk_level: "low"
```

### 6. 服务器生命周期管理

**文件**: `agent/mcp/manager.py`

**启动流程**:
1. `build_mcp_manager(config)` 创建 `McpManager` 实例，调用 `connect_from_config(config)`（第 225-228 行）
2. `connect_from_config` 遍历所有 server 配置（第 65-90 行）
3. 每个 server 在 `asyncio.timeout(server_config.startup_timeout_seconds)` 内启动（第 77 行），默认 10 秒，可由 `mcp.default_timeout_seconds` 覆盖

**required vs optional**:
- `required=False`（默认）: 启动失败时记录 `McpServerStatus(ready=False, error=...)`, 其他 server 继续
- `required=True`: 启动失败时先调用 `self.aclose()` 清理所有已建立的连接，然后 `raise RuntimeError` 终止整个 Agent 启动（`manager.py:86-90`）

**AsyncExitStack 清理** (`manager.py:36`):
- `McpManager.__init__` 创建一个 `AsyncExitStack` 实例
- 所有异步资源通过 `self._exit_stack.enter_async_context()` 注册：`stdio_client`、`httpx.AsyncClient`、`streamable_http_client`、`ClientSession`
- `aclose()` (`manager.py:221-222`) 调用 `self._exit_stack.aclose()` 按 LIFO 顺序清理所有资源

**运行时调用保护**:
- 每次 tool call 有独立超时：`asyncio.wait_for(session.call_tool(...), timeout=server_config.tool_timeout_seconds)`（`manager.py:190-192`），默认 30 秒
- 同样保护适用于 `get_prompt` 和 `read_resource`

**状态追踪** (`types.py:59-66`):
```python
@dataclass(frozen=True)
class McpServerStatus:
    name: str
    ready: bool
    tools: int = 0
    prompts: int = 0
    resources: int = 0
    error: str | None = None
```
可通过 `McpManager.status()` 查询所有 server 的状态。

### 7. McpTool 如何将外部工具包装为本地 Tool

**注意**: 项目中不存在名为 `MCPToolAdapter` 的类。实际的适配器是 `McpTool`。

**文件**: `agent/mcp/tools.py:10-23`

```python
class McpTool(Tool):
    def __init__(self, metadata: McpToolMetadata, manager: McpManager):
        self.name = metadata.callable_name          # 已解决冲突的唯一名称
        self.description = metadata.description
        self.parameters = metadata.input_schema      # JSON Schema
        self.permission = metadata.permission        # ToolPermission
        self.server_name = metadata.server_name
        self.tool_name = metadata.tool_name          # 原始 MCP tool name
        self._manager = manager

    async def execute(self, **kwargs: Any) -> str:
        return await self._manager.call_tool(self.server_name, self.tool_name, kwargs)
```

**适配机制**:
1. `McpTool` 继承 `agent.tools.base.Tool` 抽象基类，满足 `ToolRegistry` 的类型约定
2. `metadata.input_schema` 直接作为 `self.parameters`（JSON Schema dict），工具注册时通过 `Tool.get_schema()` 暴露给 LLM
3. `metadata.permission` 作为 `self.permission`，参与 Agent 模式权限决策
4. `execute(**kwargs)` 将 LLM 结构化参数透传给 `manager.call_tool()`，后者内部调用 `session.call_tool(tool_name, arguments)`
5. 错误处理在 `manager.call_tool()` (`manager.py:194-195`) 中：异常被捕获并格式化为 `"[MCP tool error: server/tool: ErrorType: message]"` 字符串返回，不会导致 loop 中断
6. 工具执行结果通过 `_format_call_tool_result()` (`manager.py:286-305`) 格式化：提取 `content[].text` 或 `structuredContent`，标记 `isError` 的情况下追加 `[MCP tool error: ...]` 前缀



### B — 面试讲稿
>
> Asterwynd 的 MCP 集成是一套从配置、连接到工具注册、权限管控、运行期调用的完整链路。
>
> **传输方式**: 支持 stdio 和 HTTP 两种。配置文件中通过 `type` 字段区分，stdio 需要 `command` 字段指定可执行文件（可选 `args`、`env`、`cwd`），HTTP 需要 `url` 字段，并支持自定义 headers（可静态配置或从环境变量读取）。底层用 Python mcp 官方 SDK 的 `stdio_client` 和 `streamable_http_client` 建立双向字节流。
>
> **工具注册流程**: 启动时先创建 `McpManager`，遍历配置中每个 server。对启用的 server，在启动超时保护下连接、初始化 session、调用 `list_tools/list_prompts/list_resources` 发现能力，把每个 tool/prompt/resource 包装成 `McpToolMetadata`。然后在 `factory.py` 中，每份 metadata 被实例化为 `McpTool` 对象——它继承自 `Tool` 抽象基类——最后和内置工具一起注册到 `ToolRegistry` 的字典里。
>
> **命名冲突解决**: 工具名格式是 `mcp__{server}__{tool}`，其中非字母数字字符都被替换为下划线。如果两个不同 server 的工具产生相同 callable name，`ensure_unique_name` 函数会追加 SHA1 摘要（取前8位十六进制），如果还冲突则追加递增计数器。这样做保证了不同 server 同名工具不会互相覆盖。
>
> **权限配置**: 支持三级粒度——服务器级 `default_permission`、以及 per-tool、per-prompt、per-resource 的细粒度覆盖。每个权限配置里指定 `capabilities`（如 `external_side_effect`）和 `risk_level`（low/medium/high）。如果都没配，所有 MCP 工具默认标记为 `HIGH` 风险、`EXTERNAL_SIDE_EFFECT` 能力、`MCP` 来源。这些权限标签在 Agent 不同模式下参与决策——比如 `read_only` 模式下 HIGH 风险工具会被直接拒绝。
>
> **服务器生命周期**: 用 `AsyncExitStack` 管理所有异步资源，保证无论正常退出还是异常都能按 LIFO 顺序清理。每个 server 有独立的启动超时（默认10秒）和工具调用超时（默认30秒）。`required` 字段控制失败策略：`required=true` 的 server 启动失败会引发 `RuntimeError` 终止整个 Agent；`required=false` 的只记录错误状态不影响其他 server。
>
> **McpTool 适配层**: `McpTool` 继承 `Tool` 基类，把 `McpToolMetadata` 中的 `input_schema` 直接作为 `parameters` 暴露给 LLM，`permission` 参与权限决策；`execute` 方法把 LLM 传来的结构化参数透传回 `McpManager.call_tool()`，由 manager 通过对应 session 发出实际的 MCP 工具调用，异常和错误结果都被捕获格式化，不会导致 AgentLoop 崩溃。
>

---
## Q6: Benchmark 系统——如何衡量 Agent 性能？


## Version A -- 详细参考版

### 1. 整体架构

Benchmark 系统由四个核心模块组成：

| 模块 | 文件 | 职责 |
|------|------|------|
| `TaskSpec` / `LoadedTask` | `benchmarks/task_schema.py` | 任务定义与加载 |
| `AgentRunner` ABC + 实现 | `benchmarks/agent_runner.py` | Agent 适配器抽象 |
| `BenchmarkRunner` | `benchmarks/runner.py` | 编排：克隆/隔离/执行/判定/清理 |
| `TaskResult` / `RunMetadata` | `benchmarks/models.py` | 结果模型与汇总 |


### 2. TaskSpec 结构与任务类型

**`TaskSpec`**（`benchmarks/task_schema.py:8-27`）是 frozen dataclass，定义单个 benchmark 任务的元数据。

必填字段：
- `id` -- 任务唯一标识
- `repo` -- 目标仓库名（如 `"psf/requests"`）
- `base_commit` -- 任务的基准 commit（在此 commit 上执行 agent）
- `problem_statement_file` -- 相对于任务目录的 issue 描述文件路径
- `test_command` -- 验证命令（如 `python -m pytest tests/`）

可选关键字段：
- `gold_patch_file` / `test_patch_file` -- gold patch 和测试 patch（用于判定）
- `timeout_seconds` -- 默认 300s
- `task_family` -- 默认 `"local"`；SWE-bench 任务设为 `"swebench"`
- `execution_environment` -- `"local"`（默认）或 `"docker"`
- `external_repo` -- 外部仓库 URL（任务使用非本项目仓库时填写）
- `version` -- SWE-bench 版本键，用于查找 `MAP_REPO_VERSION_TO_SPECS`
- `instance_id` / `dataset_name` / `dataset_split` -- SWE-bench docker 任务必填（`task_schema.py:73-81`）

**两种任务类型**：

- **local 任务**（默认 `task_family="local"`, `execution_environment="local"`）：在 source_repo 的 git worktree 中执行，测试直接在本地跑。
- **docker/SWE-bench 任务**（`task_family="swebench"`）：必须在 docker 中执行（`task_schema.py:73-81` 强制校验），使用 `swebench.harness.run_evaluation` 在容器内验证。

**`LoadedTask`**（`task_schema.py:84-91`）将 `TaskSpec` 与解析后的文件路径和内容绑定：
- `task: TaskSpec`
- `task_dir: Path`
- `problem_statement: str` -- 已读取的纯文本 issue 描述
- `gold_patch_path` / `test_patch_path` -- 解析后的可选文件路径

**`load_task()`**（`task_schema.py:93-112`）：从目录中读取 `task.json`，校验路径不逃逸任务目录（`_resolve_task_file` 做 `relative_to` 校验），返回 `LoadedTask`。


### 3. AgentRunner 抽象与三种实现

**`AgentRunner` ABC**（`benchmarks/agent_runner.py:24-38`）：

```python
class AgentRunner(ABC):
    @abstractmethod
    async def run(
        self,
        task: TaskSpec,
        problem_statement: str,
        workspace: Path,
        output_dir: Path,
        trace: TraceRecorder,
    ) -> AgentRunResult:
        ...
```

三种实现：

#### 3.1 FakeAgentRunner（`agent_runner.py:41-104`）

测试桩。接收一个字符串替换（`edit_file` / `old_string` / `new_string`），在 workspace 中实际执行文件编辑，验证 Edit 工具逻辑。输出 `AgentRunResult`，report `status="completed"` 或 `status="error"`（文件不存在或 old_string 不匹配时）。

#### 3.2 ShellCommandRunner（`agent_runner.py:107-163`）

在 workspace 中执行任意 shell 命令。使用 `asyncio.to_thread` 包装 `subprocess.run`，支持 `timeout_seconds`。输出 status 由 returncode 决定，超时返回 `BenchmarkReason.TOOL_ERROR`。

#### 3.3 ClaudeCodeRunner（`agent_runner.py:166-243`）

通过 `claude -p` 子进程调用外部 Claude Code CLI（headless 模式）。构造 prompt 包含 problem_statement + test_command 验证提示。设置 `ANTHROPIC_BASE_URL` 指向 DeepSeek API（第 197 行）。输出仅收集 stdout/stderr transcript，无 per-turn trace。超时默认 600s。

#### 3.4 AsterwyndRunner（`agent_runner.py:256-378`）

**完整的 Asterwynd agent 执行器**。构造过程：

1. 创建 `WorkspacePolicy`（`agent_runner.py:292`）-- 约束工作区路径 + 命令黑名单
2. 构建 MCP manager + 工具注册表 + ModePolicy（`agent_runner.py:296-307`）
3. 使用 `CountingLLM`（`agent_runner.py:246-253`）包装 LLM 以追踪调用次数
4. 创建 `SubAgentManager` + `AgentLoop`（`agent_runner.py:310-326`）
5. 用 `CodingPromptBuilder.build_messages()` 构造初始消息
6. 以 `asyncio.wait_for` 包裹 `agent.run()`，配置 `timeout_seconds`（默认 1800s）

结果处理：
- 超时时记录 `BenchmarkReason.MODEL_FAILURE`，保留已收集的 iteration/tool_call 计数（`agent_runner.py:343-357`）
- 正常完成时统计成功 Edit 调用次数（排除 Permission denied / Error，`agent_runner.py:358-365`）
- 返回 `BenchmarkReason.MAX_ITERATIONS` 当 stop_reason 不是 end_turn 时（`agent_runner.py:372-378`）


### 4. git worktree 隔离

**`BenchmarkRunner._create_worktree()`**（`runner.py:445-455`）：

```python
def _create_worktree(self, loaded: LoadedTask, task_output: Path) -> Path:
    worktree = task_output / ".worktree"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(worktree), loaded.task.base_commit],
        cwd=self.source_repo,
        ...
    )
    return worktree
```

关键设计：
- `--detach`：在 detached HEAD 状态创建 worktree，不创建分支
- 基于 `base_commit` 而不是 HEAD，确保每次执行可复现
- worktree 建在 `runs_dir/<run_id>/tasks/<task_id>/.worktree`，每个任务完全独立

**清理**（`runner.py:876-884`）：`git worktree remove --force` + fallback `shutil.rmtree`。


### 5. 外部仓库克隆缓存策略

**`BenchmarkRunner._clone_external_repo()`**（`runner.py:457-484`）：

两条路径：
1. **有 clone_cache_dir**：先创建 bare clone cache（`_git_clone_with_retry(url, cache_dir, bare=True)`），然后用 `git clone --shared` 从缓存快速克隆（`runner.py:471-473`）。`--shared` 通过硬链接共享对象数据库，大幅加速多任务场景。
2. **无 clone_cache_dir**：直接普通 clone。

**`_prefill_clone_cache()`**（`runner.py:70-90`）：在所有并行任务启动前，串行预填充 bare clone cache，消除 TOCTOU 竞态（`runner.py:72-74` 注释）。

**`_git_clone_with_retry()`**（`runner.py:486-512`）：对 `git clone` 执行 3 次重试，延迟递增：60s、120s、240s（指数退避）。最多尝试 4 次（1 次原始 + 3 次重试）。

**依赖安装**（`runner.py:514-582`）：利用 SWE-bench 的 `MAP_REPO_VERSION_TO_SPECS` 获取 Python 版本和 pip 包配置，用 `uv venv` + `uv pip install` 安装依赖。对 `psf/requests` 任务额外安装 `pytest-httpbin` + `werkzeug<3.0`。


### 6. 测试结果判定

**本地任务流程**（`runner.py:346-419`）：

1. **test.patch 隔离**（`runner.py:650-715`）：
   - SWE-bench 模式：将 agent 的 source 修改保存为 patch，reset hard 到 HEAD，只重新 apply 源码修改，然后 apply 测试 patch
   - 这样测试文件始终是 gold test，agent 无法"作弊"修改测试

2. **本地 httpbin 服务**（`runner.py:355-375`）：对 `psf/requests` 任务启动本地 httpbin 避免依赖外部服务

3. **执行测试命令**（`runner.py:842-874`）：
   - 对 external_repo 任务自动将 `python -m pytest` 替换为 venv 中的 python 路径
   - `subprocess.run` 执行 shell 命令，捕获 stdout/stderr
   - 超时返回 exit_code = -1

4. **结果判定**（`runner.py:385-401`）：
   - `test_exit_code == 0` + agent 正常完成 -> `"passed"`
   - `test_exit_code == 0` + agent 异常（超时/非 end_turn） -> `"passed_with_warnings"`
   - `test_exit_code != 0` -> `"failed"`，reason 为 `TEST_TIMEOUT` 或 `TEST_FAILURE`

**Docker/SWE-bench 任务流程**（`runner.py:282-344`）：
- 先生成 `predictions.jsonl`，包含 `instance_id`、`model_name_or_path`、`model_patch`
- 调用 `swebench.harness.run_evaluation` 子进程
- 解析 `report.json` 中的 `resolved` 字段判定 pass/fail

**gold patch 对比**：当前实现通过 `test_command` 和 `test_patch_file` 验证，而非直接 diff gold_patch。`gold_patch_file` 在 `TaskSpec` 中存在但主要用于文档/参考。


### 7. 并行任务执行

**`BenchmarkRunner.run_all()`**（`runner.py:124-187`）：

```python
semaphore = asyncio.Semaphore(self.parallel)

async def run_one(task_dir: Path) -> TaskResult:
    async with semaphore:
        return await self.run_task(task_dir, run_dir=run_dir)

results_raw = await asyncio.gather(
    *(run_one(td) for td in task_dirs),
    return_exceptions=True,
)
```

- `asyncio.Semaphore(self.parallel)`：控制最大并发数
- 每个任务被 `return_exceptions=True` 包裹，单个崩溃不影响其他任务
- 异常任务被转为 `TaskResult(status="error", reason="setup_error")`

**执行前预填充缓存**（`runner.py:134-135`）：先串行执行 `_prefill_clone_cache()`，消除并行执行时多个任务同时 `git clone` 同一仓库的 TOCTOU 竞态。


### 8. 结果模型

**`AgentRunResult`**（`models.py:24-32`）：agent 运行产出的中间结果。包含 `status`、`iterations`、`tool_calls`、`edit_count`、`reason`、`output`。

**`TaskResult`**（`models.py:35-61`）：单个任务完整结果。额外包含 `test_exit_code`、`duration_seconds`、`test_runs`、`input_tokens`/`output_tokens`、`planning_summary`。通过 `write_json()` 序列化。

**`RunMetadata`**（`models.py:64-81`）：一次 run 的聚合统计。包含 `run_id`、`started_at`/`ended_at`、`task_count`、`passed`、`warnings`、`failed`、`unsupported`。写入 `run.json` 和 `summary.md`。

**`render_summary()`**（`models.py:85-98`）：生成 Markdown 表格，列出每个 task 的 status、duration、iterations、tool_calls、reason。

**`BenchmarkReason`**（`models.py:10-21`）：11 种失败原因枚举 -- `setup_error`、`tool_error`、`edit_validation`、`test_failure`、`test_timeout`、`max_iterations`、`no_change`、`out_of_scope_change`、`model_failure`、`docker_unavailable`、`docker_runtime_error`。


### 9. 关键设计决策总结

| 决策 | 理由 |
|------|------|
| Worktree 而非分支 | 不污染 git history，并发安全 |
| `--detach` | 无需额外分支管理，直接基于 base_commit |
| Bare clone cache + `--shared` | 节省磁盘 + 网络，多任务共享同一仓库对象 |
| 串行预填充缓存 | 消除 TOCTOU 竞态 |
| Clone 重试 + 指数退避 | 应对 GitHub 限流和网络波动 |
| test.patch 先隔离再 apply | SWE-bench 评估协议：agent 不能修改测试 |
| Semaphore 并发控制 | 避免资源耗尽（CPU、内存、网络） |
| `return_exceptions=True` | 单任务失败不影响整轮 run |
| CountingLLM wrapper | 精确统计 LLM 调用次数（包括 subagent 内部） |


## Version B -- 面试讲稿版

Benchmark 系统是我们衡量 Agent 性能的核心基础设施，它的设计目标有三个：可复现、隔离性强、支持多种 Agent 形态对比。

**任务定义层**用 `TaskSpec` 描述一个 benchmark 任务。每个任务包含目标仓库、基准 commit、issue 描述文件路径、测试命令、超时时间等。我们支持两种任务类型：local 任务直接在本地 worktree 中执行测试，SWE-bench 任务则通过官方的 harness 在 Docker 容器里验证。对于外部仓库（比如 psf/requests），任务还会指定 external_repo 和版本信息，运行时会自动 clone 并安装依赖。

**Agent 适配层**用 `AgentRunner` 抽象接口，统一了三种执行方式。`AsterwyndRunner` 是我们自己的完整实现——它构造 AgentLoop、加载工具注册表和 MCP manager、用 CountingLLM 包装来精确统计 LLM 调用次数，然后用 asyncio.wait_for 控制超时。`ClaudeCodeRunner` 则是通过 claude -p 子进程调用外部 Claude Code CLI，作为对比基线。还有 `ShellCommandRunner` 和 `FakeAgentRunner` 用于快速验证和测试桩。

**隔离机制**是 benchmark 可靠性的关键。每个任务在独立 git worktree 中执行——我们基于 base_commit 用 `git worktree add --detach` 创建，不同任务之间完全隔离，不会互相影响。对于外部仓库，我们设计了 bare clone 缓存策略：先在缓存目录创建一个 bare clone，然后每个任务通过 `git clone --shared` 快速复制，配合 3 次指数退避重试（间隔 1 分钟、2 分钟、4 分钟）来处理网络波动。所有缓存预填充在并行执行前串行完成，消除竞态条件。

**结果判定**分为两条路径。本地任务执行完 agent 后，先应用 test.patch（这里有一个巧妙的设计：我们会保存 agent 的源码修改为 patch，reset 工作区，只恢复源码修改，然后再 apply 测试 patch——这样可以防止 agent 修改测试文件作弊），然后运行 test_command，根据退出码判定 pass/fail。SWE-bench 任务则生成 predictions.jsonl，调用官方 run_evaluation，解析 report.json 中的 resolved 字段。无论是哪种方式，我们都会记录详细的 trace、final diff 和 test output。

**并行执行**通过 asyncio.Semaphore 控制并发数，所有任务用 asyncio.gather 提交，return_exceptions=True 保证单个任务失败不影响整轮 run。最终结果汇总为 RunMetadata，包含通过/失败/警告/不支持的统计，并生成 Markdown 摘要表格。

这套体系让我们可以量化评估 agent 在真实代码修改任务上的表现，也能直接对接 SWE-bench 社区评测标准。


---
## Q7: AgentLoop 核心架构——各子系统如何协同工作？



### A — 详细参考版

### 1. 整体架构概览

`AgentLoop`（`agent/loop.py`）是 Asterwynd 的**核心调度器**，它不是简单的"调 LLM、跑工具"循环，而是一个集成了 **10 个子系统**的编排引擎：

| 子系统 | 在 AgentLoop 中的注入方式 | 核心文件 |
|--------|--------------------------|---------|
| **LLM** | 构造函数 `llm` 参数，通过 `_call_llm()` 调用（支持 stream/非 stream） | `agent/loop.py:826-870` |
| **ToolRegistry** | `tool_registry` 参数，持有所有工具 schema 和执行逻辑 | `agent/loop.py:87` |
| **HookManager** | `hooks` 参数，7 个生命周期钩子串联整轮迭代 | `agent/hooks/manager.py` |
| **MemoryManager** | `memory` 参数，每轮迭代结束后触发 `compact_if_needed()` | `agent/loop.py:805` |
| **PersistentMemory** | `persistent_memory` 参数，注入 ContextBuilder 的 MemoryIndexSource | `agent/loop.py:1051` |
| **ContextBuilder** | `context_builder` 参数，每轮迭代前构建上下文注入 | `agent/loop.py:546` |
| **ApprovalHandler** | `approval_handler` 参数，对需要审批的工具在 Phase 1 发起审批 | `agent/loop.py:691-702` |
| **ModePolicy** | 内嵌在 `tool_registry.mode_policy` 中，通过 `decide_tool()` 决定是否需要审批 | `agent/loop.py:667` |
| **BackgroundTaskManager** | `background_manager` 参数，每轮迭代前 check_completed 注入结果 | `agent/loop.py:530-543` |
| **SubAgentManager** | `subagent_manager` 参数，可选暴露 6 个子 agent 工具 | `agent/loop.py:297-306` |
| **SkillRuntime** | `skill_runtime` 参数，控制 skill 激活/恢复 | `agent/loop.py:132-133` |
| **SessionStore** | `session_store` 参数，run() 结束后自动保存快照 | `agent/loop.py:459-463` |
| **TraceRecorder** | `trace_recorder` 参数，贯穿整轮运行记录每个步骤 | `agent/trace_recorder.py` |
| **RetryHook** | 内部 `_retry` 实例，对非 Bash 工具做指数退避重试 | `agent/loop.py:124` |
| **PlanningManager** | `_planning` 实例，管理 plan/execute 模式状态 | `agent/loop.py:92` |


### 2. 主循环详细流程图

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ run(messages, on_event, trace_recorder, session_id, run_id, resume_snapshot)  (L428) │
│   ├─ set_run_identity on trace_recorder                                              │
│   ├─ save/restore _active_on_event / _active_trace_recorder                          │
│   └─ _run(...)                                                                       │
│       └─ finally: cleanup background tasks, save session, restore event/trace        │
└──────────────────────────────────────────────────────────────────────────────────────┘
                │
                ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ _run(messages, ...)  (L467)                                                           │
│                                                                                      │
│  ┌─ resume 路径 (L479) ──────────────────────────────────────────────────────────┐   │
│  │ resume_snapshot is not None:                                                    │   │
│  │   1. 从 snapshot 恢复 mode (L483-484)                                          │   │
│  │   2. 恢复 execution_todos + _todo_next_id (L485-486)                           │   │
│  │   3. 恢复 active_skills (L487-488)                                             │   │
│  │   4. 恢复 user_system_prompt (L489-490)                                        │   │
│  │   5. 重建 messages: system + conversation + resume marker + new input (L491-497)│   │
│  │   6. start_iteration = 0 (L498)                                                │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─ start_iteration 路径 (L507) ─────────────────────────────────────────────────┐   │
│  │ resume_snapshot is None:                                                        │   │
│  │   1. skill_runtime.begin_run(last_user_content) (L509-510)                     │   │
│  │   2. await hooks.on_run_started(run_config) (L518)                             │   │
│  │   3. trace_recorder.record_run_started(mode) (L519-520)                        │   │
│  │   4. on_event("run_started", data) (L521-525)                                  │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
│  ┌─ 迭代主循环 for iteration in range(start_iteration, max_iterations): (L527) ───┐  │
│  │                                                                                 │  │
│  │  STEP 1: BACKGROUND TASK 结果注入 (L530-543)                                    │  │
│  │    background_manager.check_completed() → 已完成的后台任务                       │  │
│  │    将结果格式化为 user message 注入消息列表                                      │  │
│  │                                                                                 │  │
│  │  STEP 2: 上下文构建 (L544-546)                                                  │  │
│  │    tool_schemas = tool_registry.get_all_schemas()                               │  │
│  │    contextualized = await _messages_with_run_context(messages)                  │  │
│  │      → ContextBuilder.build() 将 8 个上下文源按优先级注入                       │  │
│  │                                                                                 │  │
│  │  STEP 3: HOOKS before_iteration (L547)                                          │  │
│  │    await hooks.before_iteration(iteration, contextualized)                      │  │
│  │                                                                                 │  │
│  │  STEP 4: LLM 调用 (L548-552)                                                    │  │
│  │    response, streamed = await _call_llm(messages, tools, on_event)              │  │
│  │    → 支持 stream_chat (逐个 delta 推送给前端) + 非 stream chat                   │  │
│  │                                                                                 │  │
│  │  STEP 5: HOOKS after_llm_call (L553)                                            │  │
│  │    await hooks.after_llm_call(response)                                         │  │
│  │                                                                                 │  │
│  │  STEP 6: TRACE iteration record (L554-562)                                      │  │
│  │    trace_recorder.record_iteration(iteration, assistant_preview, tool_calls)    │  │
│  │                                                                                 │  │
│  │  STEP 7: ON_EVENT "llm_response" (L564-575)                                     │  │
│  │    → 通知前端 LLM 响应内容                                                      │  │
│  │                                                                                 │  │
│  │  ★ STEP 8: 无 tool_calls 的处理 (L577-600)                                      │  │
│  │    • max_tokens 截断 → 追加 "continue" 消息并 continue (L579-584)              │  │
│  │    • end_turn → hooks.on_completion(), on_event("done"), return RunResult       │  │
│  │                                                                                 │  │
│  │  STEP 9: 追加 assistant 消息（只一次，在 for 外） (L603)                         │  │
│  │                                                                                 │  │
│  │  ═══════════════ PHASE 1: Pre-process (L606-737) ═══════════════════════════   │  │
│  │  对每个 tool_call delta:                                                        │  │
│  │    a. _parse_arguments → 解析 JSON (L609)                                       │  │
│  │    b. tool_registry.get_tool(name) → 查找工具 (L652)                            │  │
│  │       └─ 未找到 → pending 标记 pre_denied, 跳过 (L654-665)                      │  │
│  │    c. mode_policy.decide_tool(tool) → 检查是否需要审批 (L667)                   │  │
│  │    d. 需要审批 (L672-737):                                                      │  │
│  │       ├─ build_approval_request → 构建审批请求 (L673-681)                       │  │
│  │       ├─ 对 observed_tool_call 进行参数脱敏 (L682-686)                          │  │
│  │       ├─ trace_recorder.record_approval_request (L687-688)                      │  │
│  │       ├─ on_event("approval_request") → 通知前端 (L689-690)                     │  │
│  │       ├─ approval_handler.request_approval → 发起审批 (L691-701)                │  │
│  │       ├─ trace_recorder.record_approval_response (L711-712)                     │  │
│  │       ├─ on_event("approval_response") (L713-714)                               │  │
│  │       └─ 拒绝 → 生成 pre_denied_result (L715-727)                               │  │
│  │    e. pending.append(所有上下文) (L729-737)                                      │  │
│  │                                                                                 │  │
│  │  ═══════════════ PHASE 2: Execute with grouping (L740) ═══════════════════════ │  │
│  │  _execute_tool_calls(pending) → 并行分组执行                                    │  │
│  │    ├─ 连续 parallelizable 工具 → asyncio.gather 并发 (L957-984)                 │  │
│  │    ├─ 非 parallel / 需审批 / pre_denied → 串行执行 (L986-995)                   │  │
│  │    └─ _execute_single_tool 内部 (L890-920):                                     │  │
│  │        ├─ hooks.before_tool_execute(observed_tool_call) (L895)                  │  │
│  │        ├─ tool_registry.execute(tool_call, approval_granted=...) (L900-913)     │  │
│  │        │   └─ Bash 工具异常直接捕获; 非 Bash 经 RetryHook 指数退避重试          │  │
│  │        └─ hooks.after_tool_execute(observed_tool_call, result) (L919)           │  │
│  │                                                                                 │  │
│  │  ═══════════════ PHASE 3: Post-process results (L742-803) ═══════════════════  │  │
│  │  按原始顺序处理每个 executed entry:                                              │  │
│  │    a. trace_recorder.record_tool_call + record_tool_result (L751-769)           │  │
│  │       └─ Edit 工具额外 record_edit(path) (L770-772)                             │  │
│  │    b. on_event("tool_call") + on_event("tool_result") (L774-788)                │  │
│  │       └─ 附带工具结果摘要 (summarize_tool_result)                                │  │
│  │    c. skill_activated 检测 (L789-794)                                           │  │
│  │    d. TodoWrite → on_event("todo_updated") (L795-796)                           │  │
│  │    e. messages.append(tool_result_message) (L798)                                │  │
│  │    f. tool_calls_made.append(ToolCallMade) (L799-803)                            │  │
│  │                                                                                 │  │
│  │  STEP 10: MEMORY 压缩 (L805-809)                                                │  │
│  │    compacted = await memory.compact_if_needed(messages, iteration)              │  │
│  │    → 当 token 数达到 max_tokens 90% 触发压缩                                   │  │
│  │    → compact() 保留 system + recent(N+tool chains) + 摘要(summary)              │  │
│  │    → on_event("memory_compaction")                                              │  │
│  │                                                                                 │  │
│  │  → 下一轮迭代                                                                   │  │
│  └─────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                      │
│  ┌─ 达到 max_iterations (L811-824) ───────────────────────────────────────────────┐   │
│  │  返回 RunResult(content, StopReason.MAX_ITERATIONS, tool_calls_made)            │   │
│  │  → hooks.on_completion() → on_event("done")                                     │   │
│  └────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                      │
└──────────────────────────────────────────────────────────────────────────────────────┘
```


### 3. RunResult 的三种 StopReason (`agent/result.py:11-14`)

```python
class StopReason(Enum):
    END_TURN = "end_turn"          # LLM 自然返回不含 tool_call 的响应，正常结束
    MAX_ITERATIONS = "max_iterations"  # 达到 max_iterations 上限（默认 20）
    ERROR = "error"                # 异常错误（仅在 SubAgentManager._mark_failed 中使用）
```

**关键代码路径**：

- **END_TURN**: `_run()` L596-600 — LLM 响应没有 tool_calls 且不是 max_tokens 截断时返回。同时调用 `hooks.on_completion()` 和 `on_event("done")`。
- **MAX_ITERATIONS**: `_run()` L813-824 — 循环达到 `self.max_iterations`（默认 20）后返回。取最后一条 assistant content 作为最终结果。
- **ERROR**: 主 loop 的 `run()` 不会直接返回 ERROR；它仅在 `SubAgentManager._complete_run()` (subagent/manager.py:333) 中作为判断条件：`result.stop_reason is not StopReason.ERROR` 区分 "completed" 和 "failed"。


### 4. start_iteration 与 resume 路径对比

| 维度 | start_iteration 路径 (`_run` L507-525) | resume 路径 (`_run` L479-506) |
|------|--------------------------------------|-------------------------------|
| **触发条件** | `resume_snapshot is None` | `resume_snapshot is not None` |
| **messages 构建** | 使用调用者传入的原始 messages | 从 snapshot 恢复 conversation history + resume marker + new input |
| **mode 处理** | 使用当前 runtime_state 的 mode | 如果 snapshot.mode 与当前不同，调用 `set_mode(..., source="resume")` 切换 |
| **todos 恢复** | 不需要 | 从 snapshot.todos 恢复 + `_sync_todo_next_id()` |
| **skills 恢复** | 调用 `skill_runtime.begin_run()` | 调用 `skill_runtime.restore_skills()` |
| **system_prompt** | 使用当前值 | 从 `resume_snapshot.user_system_prompt` 恢复 |
| **生命周期钩子** | 调用 `hooks.on_run_started()` + `on_event("run_started")` + trace record | **不触发** run_started 事件 |
| **start_iteration** | 0 | 0（从头计数） |


### 5. Background Task 结果注入机制

Background task 在每轮**迭代开始**自动注入（`_run` L530-543）：

```python
# 每轮迭代开始
if self.background_manager is not None:
    completed = self.background_manager.check_completed()
    for task in completed:
        observation = (
            f"[Background task {task['task_id']} completed]\n"
            f"Command: {task['command']}\n"
            f"Status: {task['status']}\n"
            f"Exit code: {task['exit_code']}\n"
            f"Output:\n{task['stdout']}"
        )
        if task.get("output_truncated"):
            observation += "\n[output truncated]"
        messages.append(Message(role="user", content=observation))
```

关键设计：
- `check_completed()` 返回的是已完成且**未报告过**（`entry.reported == False`）的任务 (`background.py:63-69`)
- 每个已完成任务**只注入一次**，注入后标记 `entry.reported = True`
- 注入的 message 角色是 **user**，不是 tool，这使得 agent 把它当作新的事件通知来处理
- 输出 cap 为 64KB (`MAX_OUTPUT_BYTES = 64 * 1024`)，超出部分截断并标记 `output_truncated`

此外，agent 还可以**主动轮询**后台任务状态：
- `TaskOutputTool` → `_get_task_output()` (L371-386)，支持 `block=True` + timeout
- `TaskStopTool` → `_stop_task()` (L388-398)，终止后台任务


### 6. trace_recorder 贯穿流程

`TraceRecorder` (`agent/trace_recorder.py`) 是一个事件驱动的追踪记录器，贯穿整个 AgentLoop 生命周期：

| 生命周期节点 | TraceRecorder 调用 | 代码位置 |
|-------------|-------------------|---------|
| run 启动 | `set_run_identity(session_id, run_id)` | loop.py:439-442 |
| start 路径 | `record_run_started(mode)` | loop.py:519-520 |
| resume 路径 | `set_mode` 内 `record_mode_changed()` | loop.py:172 |
| 每轮迭代 | `record_iteration(iteration, assistant_preview, tool_calls)` | loop.py:555-562 |
| 审批请求 | `record_approval_request(data)` | loop.py:687-688 |
| 审批响应 | `record_approval_response(data)` | loop.py:711-712 |
| 工具调用 | `record_tool_call(name, arguments)` | loop.py:752-755 |
| 工具结果 | `record_tool_result(name, status, duration_ms, result)` | loop.py:764-769 |
| Edit 工具 | `record_edit(path, status, result)` | loop.py:770-772 |
| 并行执行 | `record_parallel_execution(group_names)` | loop.py:960-961 |
| Plan 更新 | `record_planning_state(snapshot)` | loop.py:272 |
| Plan 文档 | `record_plan_document(event_type, document)` | loop.py:286 |
| run 完成 | `record_completion(status, content)` | trace_recorder.py:165-171 |

TraceRecorder 内部使用 `steps: list[TraceStep]` 记录所有步骤，支持 `to_dict()`, `to_json()`, `write_to_file()` 三种导出格式。


### 7. 各子系统在单次迭代中的串联顺序

一次完整的迭代（从 L530 到 L809）串起来的子系统顺序：

```
BackgroundManager.check_completed()           → 注入已完成后台任务
  ↓
ToolRegistry.get_all_schemas()                → 获取所有工具 JSON schema
  ↓
ContextBuilder.build(BuildContext)            → 按优先级渲染 8 个上下文源:
  │   P0: SystemPromptSource (critical)
  │   P1: AsterMdSource (critical)
  │   P2: MemoryIndexSource (persistent_memory)
  │   P4: SkillIndexSource + SkillActiveSource (skill_runtime)
  │   P5: PlanModeSource + PlanningStateSource + TodoSource
  ↓
HookManager.before_iteration()                → 通知所有注册的 hooks
  ↓
LLM.stream_chat() / LLM.chat()               → 调用大模型（流式/非流式）
  ↓
HookManager.after_llm_call()                  → 通知所有 hooks LLM 返回
  ↓
TraceRecorder.record_iteration()              → 记录迭代轨迹
  ↓
on_event("llm_response")                      → 通知前端
  ↓
(无 tool_calls) → hooks.on_completion()       → 结束循环
  ↓
[PHASE 1] tool_registry.get_tool() +         → 工具查找 + 参数解析
  mode_policy.decide_tool()                   → 权限决策
  ↓
[PHASE 1] approval_handler.request_approval() → (如果需要) 发起审批
  ↓
[PHASE 2] _execute_tool_calls(pending):       → 并行分组执行
  ├─ hooks.before_tool_execute()
  ├─ tool_registry.execute(tool_call)
  │   └─ RetryHook.execute_with_retry()      → (非 Bash) 指数退避重试
  │   └─ 工具内部可能调用 mcp_manager.call_tool() → MCP 集成
  │   └─ Bash 工具可能启动 background task      → BackgroundTaskManager
  └─ hooks.after_tool_execute()
  ↓
[PHASE 3] TraceRecorder.record_tool_call/result() → 记录工具调用
  ↓
[PHASE 3] on_event("tool_call"/"tool_result")     → 通知前端
  ↓
[PHASE 3] 检测 skill_activated / todo_updated     → 状态事件
  ↓
[PHASE 3] messages.append(tool_result_message())   → 追加工具结果
  ↓
MemoryManager.compact_if_needed()                 → 必要时压缩消息历史
  ↓
→ 下一轮迭代
```


### 8. 关键设计要点

1. **Phase 1/2/3 分离 (L606-L803)**: 所有工具调用被先全部预处理（解析、校验、审批），再执行，最后按原始顺序产出结果。这保证了即使并行执行，结果插入消息列表的顺序仍然是 LLM 的输出顺序。

2. **并行分组算法 (L922-997)**: `_execute_tool_calls()` 中，连续的 `parallelizable=True` 且无需审批、非 pre_denied 的工具组成一组，通过 `asyncio.gather()` 并发执行。单个/非并行/需审批/被拒的工具单独一组串行执行。

3. **操作脱敏 (L682-686)**: 当工具需要审批时，`observed_tool_call` 的参数会被脱敏处理（通过 `approval_request.redacted_args`），使得推送到前端和 traces 中的参数不会包含敏感值。但实际执行使用原始 `tool_call`。

4. **max_tokens 截断处理 (L578-584)**: LLM 因 `stop_reason == "max_tokens"` 而没有 tool_calls 时，不是结束运行，而是追加"Please continue"消息并继续下一轮迭代。

5. **Memory 压缩保护 (memory/manager.py:197-215)**: 压缩时保留最近 N 条消息的完整 tool chain（assistant message + tool result），防止孤立的 tool result 留在消息列表中。

6. **Subagent 隔离 (subagent/manager.py:298-324)**: 每个 subagent 有自己的 AgentLoop 实例、独立的 ToolRegistry、独立的 MemoryManager（80K tokens）、独立的 TraceRecorder。Subagent 复用父 AgentLoop 的 LLM 实例但被限制在不超过父 mode 的权限级别 (`_clamp_mode()`) (subagent/manager.py:401-411)。

7. **MCP 集成**: MCP 服务器通过 `McpManager.connect_from_config()` 启动时注册到 `ToolRegistry`。工具命名遵循 `mcp__<server>__<tool>` 格式（在 `mcp/naming.py` 中定义）。AgentLoop 本身不直接感知 MCP 的存在，统一通过 `tool_registry.get_all_schemas()` 和 `tool_registry.execute()` 间接使用。

8. **Session 持久化**: `run()` 的 finally 块中自动调用 `_save_session()` (L459-463)，将所有状态（messages、todos、active_skills、mode、system_prompt、runtime_fingerprint）写入 `SessionStore`。后续 session 通过 `resume_snapshot` 参数恢复。



### B — 面试讲稿
>
> AgentLoop 是整个 Asterwynd 系统的心脏，它不只是简单的"调大模型、跑工具"，而是在一轮迭代里把十多个子系统精确地编织在一起。
>
> 每轮迭代可以概括为十个步骤。第一步，先检查后台任务管理器，如果有已完成的后台 Bash 任务，把结果以 user 消息形式注入消息列表，保证 agent 能看到进程完成通知。第二步，调用 ContextBuilder，按优先级从高到低注入 8 个上下文源：系统提示词、AGENTS.md、持久记忆索引、skill 索引和激活状态、plan mode 信息、planning 状态、以及当前 todo 列表。所有内容受 20K token 的注入预算约束，低优先级部分会从尾部截断。第三步，跑 hooks 的 before_iteration。第四步，调用 LLM，支持流式和非流式，流式模式下每个 delta 都实时推送给前端。第五步，after_llm_call。第六步，trace_recorder 记录本轮迭代的 assistant 预览和解析出的 tool_calls。
>
> 第七步是关键的分支判断。如果 LLM 没返回 tool_calls，有两种情况：如果是 max_tokens 截断，追加"请继续"的消息进入下一轮；如果是自然的 end_turn，触发 on_completion 钩子，返回 RunResult(stop_reason=END_TURN)。
>
> 如果有 tool_calls，进入三阶段处理。Phase 1 是预处理：依次对每个 tool_call 做 JSON 参数解析、工具注册表查找、mode_policy 权限决策。如果工具需要审批，调用 ApprovalHandler 发起审批请求，同时把原始参数脱敏后再推给前端。如果被拒绝或未知工具，标记为 pre_denied。Phase 2 是分组执行：连续的 parallelizable 且无需审批的工具通过 asyncio.gather 并发执行；非并行或需审批或已被拒的工具串行执行。实际执行时会经过 RetryHook 的指数退避重试，非 Bash 工具遇到 transient 错误会自动重试最多 3 次。Phase 3 是结果后处理：按原始顺序记录 trace、推送前端事件、检测 skill 激活和 todo 变更、追加 tool_result 消息。
>
> 第八步，MemoryManager 检查 token 数是否达到 90% 阈值，如果是且距离上次压缩超过 5 轮迭代，触发压缩。压缩策略是保留 system 消息、最近 N 条完整 tool chain，中间部分用 LLM 生成摘要后替换为一条 user 消息。
>
> 整个循环重复直到 LLM 主动结束、或者达到 max_iterations（默认 20 轮）。
>
> 另外有两个关键的外部路径。一个是 resume 路径：如果传入了 SessionSnapshot，AgentLoop 会恢复 mode、todos、active_skills、system_prompt，并把历史对话加上"session resumed"标记和新输入一起重建消息列表，但不触发 run_started 事件。另一个是 subagent：SubAgentManager 为每个 subagent 创建独立的 AgentLoop 实例，复用父 LLM 实例但权限收束到不超过父 mode，完成后返回 RunResult 汇总。
>
> trace_recorder 贯穿整个流程，从 run 启动开始记录每轮迭代、每个工具调用和结果、每次审批请求和响应、每次计划更新，最终可以导出为 JSON trace 文件用于调试和审计。RunResult 有三种 stop_reason：END_TURN 是正常结束，MAX_ITERATIONS 是达到轮次上限，ERROR 只在 subagent 异常时用。
>
> 这就是整个 AgentLoop 的工作方式——把 LLM 调用、上下文注入、权限审批、并行工具执行、记忆压缩、子 agent 调度，全部编织在一个精密的状态机里。
>

---
## Q8: Hook/Plugin 系统——Agent 生命周期钩子如何设计？



### A — 详细参考版

### 1. 7 个生命周期钩子点的定义和触发时机

Hook Protocol 定义在 `agent/hooks/manager.py:14-22`：

```python
@runtime_checkable
class Hook(Protocol):
    async def on_run_started(self, run_config: "AgentRunConfig") -> None: ...
    async def before_iteration(self, iteration: int, messages: list[Message]) -> None: ...
    async def after_llm_call(self, response: LLMResponse) -> None: ...
    async def before_tool_execute(self, tool_call: ToolCall) -> None: ...
    async def after_tool_execute(self, tool_call: ToolCall, result: str | list["ContentBlock"]) -> None: ...
    async def on_error(self, error: Exception) -> None: ...
    async def on_completion(self, result: "RunResult") -> None: ...
```

每个钩子点在 `agent/loop.py` 中的触发位置和时机如下：

| 钩子点 | loop.py 调用位置 | 触发时机 |
|--------|-----------------|---------|
| `on_run_started` | `_run()` L518 | Run 开始后、进入迭代循环前，仅在新启动（非 resume）时调用 |
| `before_iteration` | `_run()` L547 | 每轮迭代开始时，在 LLM 调用之前。传入 iteration 序号和当前消息列表（含上下文注入后的 contextualized messages） |
| `after_llm_call` | `_run()` L553 | 每次 LLM 调用返回后立刻触发，传入完整 LLMResponse（含 content、stop_reason、tool_calls） |
| `before_tool_execute` | `_execute_single_tool()` L895 | 每个工具执行前触发，传入 observed_tool_call（可能已脱敏的参数） |
| `after_tool_execute` | `_execute_single_tool()` L919 | 每个工具执行完成后触发，传入 tool_call 和执行 result |
| `on_error` | `_run()` L613（参数解析失败）、`_execute_single_tool()` L905（工具执行异常） | 发生错误时触发。注意 L613 是 JSON 参数解析错误，L905 是 Bash 工具执行异常 |
| `on_completion` | `_run()` L585（END_TURN）、L818（MAX_ITERATIONS） | Run 结束时触发，两处分别对应正常结束和达到最大迭代次数 |

关键细节：
- `before_iteration` 传入的是 `contextualized` 消息（L546-547），即经过 `_messages_with_run_context()` 注入了系统提示、ASTER.md、记忆索引等上下文后的消息列表。
- `before_tool_execute` 和 `after_tool_execute` 接收的是 `observed_tool_call`，当工具需要审批时，其 arguments 已被脱敏（L682-686）。
- `on_error` 只在参数解析失败（L613）和 Bash 工具执行异常（L905）时被显式调用；非 Bash 工具的错误通过 RetryHook 的 `execute_with_retry` 兜底处理，不额外触发 `on_error`（L908-918）。

### 2. Hook Protocol 设计——为什么用 Protocol 而非 ABC

**核心设计在 `agent/hooks/manager.py:14-22`：**

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Hook(Protocol):
    ...
```

选择 `typing.Protocol` 而非 `abc.ABC` 的原因：

**（1）结构子类型（Structural Subtyping）而非名义子类型**

Protocol 允许任何类只要实现了匹配的方法签名即可被视为 Hook，无需显式继承。这降低了耦合度，Hook 实现者不必了解继承层级，只需"按约定提供方法"即可。

**（2）减少样板代码**

ABC 要求每个具体实现必须继承基类，且抽象方法需要 `@abstractmethod` 装饰。使用 Protocol 后，内置 Hook 如 `RetryHook`、`TracingHook`、`TokenBudgetHook`、`LoggingHook` 均未显式继承 `Hook` 类——它们仅仅是提供了与 Protocol 签名匹配的方法。唯一的例外是 `ParentChannelHook`，它显式声明了 `class ParentChannelHook(Hook)`（`agent/subagent/parent_channel_hook.py:16`），这主要是为了文档意图的清晰性，而非功能必须。

**（3）允许部分实现**

Protocol 不强制实现所有方法。查看四个内置 Hook 的实现：

- `RetryHook`（`agent/hooks/builtin/retry.py:57-62`）：所有钩子方法都是 `pass` 的桩实现，实际功能通过 `execute_with_retry()` 暴露，由 AgentLoop 直接调用（`loop.py:908-913`）。
- `TracingHook`（`agent/hooks/builtin/tracing.py:58-61`）：只实现了 `before_tool_execute` 和 `after_tool_execute`，其余为 `pass`。
- `TokenBudgetHook`（`agent/hooks/builtin/token_budget.py:40-43`）：只实现了 `after_tool_execute`，其余为 `pass`。
- `LoggingHook`（`agent/hooks/builtin/logging.py:14-39`）：唯一实现了全部 7 个钩子方法的内置 Hook。

这种"只实现自己关心的钩子"的模式天然契合 Protocol 的设计哲学。

**（4）`runtime_checkable` 装饰器**

`@runtime_checkable` 使得 `isinstance(obj, Hook)` 在运行时可检查，而不是仅在静态类型检查时生效。这为未来的动态注册、插件发现提供了基础能力。

### 3. HookManager 如何链式调用多个 Hook

**核心实现在 `agent/hooks/manager.py:24-56`：**

```python
class HookManager:
    def __init__(self, hooks: list[Hook] | None = None):
        self.hooks: list[Hook] = hooks or []
```

HookManager 维护一个有序的 Hook 列表，对每个钩子点的方法，**按注册顺序依次调用**所有 Hook 的对应方法。

链式调用模式分为两类：

**（A）普通链式调用（6 个钩子点使用此模式）**

```python
async def before_iteration(self, iteration: int, messages: list[Message]) -> None:
    for hook in self.hooks:
        await hook.before_iteration(iteration, messages)
```

直接对每个 hook 调用同名方法。适用于 `before_iteration`、`after_llm_call`、`before_tool_execute`、`after_tool_execute`、`on_error`、`on_completion`。

**（B）防御式链式调用（`on_run_started` 使用此模式）**

```python
async def on_run_started(self, run_config: "AgentRunConfig") -> None:
    for hook in self.hooks:
        handler = getattr(hook, "on_run_started", None)
        if handler:
            await handler(run_config)
```

`on_run_started` 使用 `getattr` + 判空的方式而非直接调用，这是一种防御式设计。因为 Protocol 定义的所有方法都有 `...` 实现，HookManager 本身无法保证列表中的对象都实现了 `on_run_started`（尤其是工厂函数或外部注册的 Hook 可能只提供了部分方法）。这种方式比直接调用更健壮，避免 `AttributeError`。

**AgentLoop 中的集成（`agent/loop.py`）**：

AgentLoop 在构造函数中接收 HookManager（L89）：
```python
self.hooks = hooks or HookManager()
```

如果未传入，默认使用空的 HookManager。同时 AgentLoop 还在内部维护了一个专用的 `RetryHook` 实例（L124）：
```python
self._retry = RetryHook(max_retries=3, base_delay=1.0)
```

这个 `_retry` 不是通过 HookManager 链式调用的，而是在 `_execute_single_tool` 中直接调用 `self._retry.execute_with_retry()`（L908-913）。这是一种设计选择——RetryHook 的核心能力（重试逻辑）需要包装工具执行函数，不能简单地通过 before/after 钩子实现。

### 4. 内置 Hook 实现详解

#### 4.1 LoggingHook（`agent/hooks/builtin/logging.py`）

**唯一覆盖全部 7 个钩子点的内置 Hook**，使用 Python 标准 `logging` 模块，logger 名为 `asterwynd.hooks.logging`。

各钩子点行为：
- `on_run_started`（L18-19）：记录运行模式（`run_config.mode.value`）
- `before_iteration`（L21-22）：记录迭代序号和消息数量
- `after_llm_call`（L24-26）：仅当 `verbose=True` 时记录 LLM 响应内容和工具调用数量
- `before_tool_execute`（L28-29）：记录工具名和参数
- `after_tool_execute`（L31-33）：记录工具名和结果预览（截断至 200 字符）
- `on_error`（L35-36）：记录错误信息
- `on_completion`（L38-39）：记录停止原因和工具调用总数

构造函数接受 `verbose: bool = False` 参数控制 LLM 响应的详细日志级别。

#### 4.2 RetryHook（`agent/hooks/builtin/retry.py`）

**设计与其他 Hook 不同——它不依赖 HookManager 链式调用，而是通过 `execute_with_retry()` 方法被 AgentLoop 直接调用。**

核心机制：
- **可重试错误识别**（L17-25）：使用正则 `RETRYABLE_PATTERN`，匹配包含 `timeout`、`timed out`、`connection`、`rate limit`、`429`、`503`、`temporary` 的错误消息（大小写不敏感）。
- **指数退避策略**（L40-53）：`delay = self.base_delay * (2 ** attempt)`，即 1s、2s、4s、8s...（默认 `base_delay=1.0`）。
- **最大重试次数**：默认 `max_retries=3`，共执行 1 + 3 次（第一次 + 3 次重试）。
- **不可重试错误**：如果错误不匹配模式，直接返回 `[Error: ...]` 不重试。
- **耗尽重试**：所有重试都失败后，返回 `[Error after N attempts: ...]`。

在 AgentLoop 中的集成（`loop.py:908-913`）：
```python
result = await self._retry.execute_with_retry(
    tool_call,
    execute_fn=lambda tc: self.tool_registry.execute(tc, approval_granted=approval_granted),
)
```

注意：Bash 工具不走 RetryHook（L898-906），Bash 工具执行异常直接触发 `on_error` 钩子。

#### 4.3 TracingHook（`agent/hooks/builtin/tracing.py`）

**记录每个工具调用的性能追踪数据，用于可观测性。**

数据结构：`ToolCallTrace` dataclass（L15-20），包含 `tool_name`、`arguments`、`duration_ms`、`success`。

核心机制：
- `before_tool_execute`（L27-33）：创建 `ToolCallTrace` 对象，记录到 `self.calls` 列表和 `self._pending` 字典（以 `tool_call.id` 为 key，tuple of (trace, start_time) 为 value）。使用 `time.perf_counter()` 记录高精度起始时间。
- `after_tool_execute`（L35-43）：从 `_pending` 取出对应 entry，计算 duration_ms，判断 success（result 不以 `[Error` 开头）。
- `get_summary()`（L45-56）：返回聚合统计 `{"total_calls", "successful", "failed", "avg_duration_ms"}`。

TracingHook 使用 `_pending` 字典而非直接的 stack/try-finally 来匹配 before/after，因为工具执行可能并行（`asyncio.gather`），不同工具的 before 和 after 调用可能交错。

#### 4.4 TokenBudgetHook（`agent/hooks/builtin/token_budget.py`）

**监控工具输出 token 消耗，在超出预算阈值时发出警告。**

构造函数参数（L16-18）：
- `budget: int = 100_000`：总 token 预算
- `warn_threshold: float = 0.8`：告警阈值比例（80%）

核心机制：
- 只在 `after_tool_execute` 中工作（L24-31）
- Token 估算：`estimated = len(result) // 4`，基于粗略的 4 字符/token 近似
- 当累计 tokens 超过 `budget * warn_threshold` 时，记录 WARNING 日志
- `get_usage()`（L33-38）：返回 `{"total_tokens", "budget", "usage_ratio"}`

设计限制：
- 只估算工具结果的输出 token，不跟踪 LLM 调用的实际 input/output token（那是 LLM provider 层的职责）
- 使用 4 字符/token 的粗略估算而非精确的 tokenizer 计数

### 5. SubAgent 场景下的 ParentChannelHook

**位于 `agent/subagent/parent_channel_hook.py`，是唯一显式继承 `Hook` Protocol 的内置 Hook。**

```python
class ParentChannelHook(Hook):
    def __init__(self, subagent_id: str, channel: "ParentChannel", parent_messages: list["Message"]):
        self.subagent_id = subagent_id
        self.channel = channel
        self.parent_messages = parent_messages
```

构造函数接收三个参数：
- `subagent_id`：子 agent 的唯一标识
- `channel`：`ParentChannel` 类型的通信通道（定义在 `agent/subagent/protocol.py`）
- `parent_messages`：**对父 agent 消息列表的共享引用**（mutable list），这是关键设计——ParentChannelHook 直接修改父 agent 的消息列表

核心逻辑在 `after_tool_execute`（L27-39）：
```python
async def after_tool_execute(self, tool_call: "ToolCall", result: str) -> None:
    try:
        sub_result: "SubAgentResult" = await self.channel.get_result(timeout=0.01)
        self.parent_messages.append(
            Message(role="tool", content=sub_result.result,
                    tool_call_id=sub_result.tool_call_id)
        )
    except asyncio.TimeoutError:
        pass
```

工作流程：
1. 在父 agent 的每次工具执行完成后（`after_tool_execute`），尝试从 channel 获取子 agent 结果。
2. 使用 **极短的 0.01 秒 timeout**（非阻塞模式）——如果子 agent 还没完成，就跳过，下次工具执行后再试。
3. 如果子 agent 已完成，将子 agent 的结果构造为 `role="tool"` 的 Message 注入到父 agent 的 `parent_messages` 列表中。这样在父 agent 的下一轮迭代中，LLM 就能看到子 agent 的返回结果。
4. `tool_call_id` 使用 `sub_result.tool_call_id` 确保结果能与父 agent 的对应工具调用正确关联。

设计特点：
- **非阻塞注入**：不使用 long-running task 等待，而是利用父 agent 的每次工具执行点作为轮询机会
- **共享可变引用**：直接操作父 agent 的 messages 列表，无需额外的事件总线或通知机制
- **轮询而非推送**：依赖父 agent 继续执行工具来触发注入，如果父 agent 不再执行工具（如已进入 END_TURN），子 agent 结果可能无法及时注入



### B — 面试讲稿
>
> 面试官你好，我来介绍 Asterwynd 的 Agent 生命周期钩子系统设计。
>
> 整个系统围绕 7 个钩子点展开，覆盖了 Agent 一次完整运行的生命周期：`on_run_started` 在 run 开始时触发；`before_iteration` 在每轮迭代前触发，此时消息已经过上下文注入管线；`after_llm_call` 在 LLM 返回响应后触发；`before_tool_execute` 和 `after_tool_execute` 分别包裹每个工具执行；`on_error` 在异常时触发；`on_completion` 在 run 结束时触发，无论是正常结束还是达到最大迭代次数。
>
> 在架构上，我们选择了 Protocol 而非 ABC。核心考虑有三点：第一，结构子类型允许任何实现了正确方法签名的类自动满足 Hook 契约，无需显式继承，降低了耦合；第二，支持部分实现——比如 TracingHook 只关心工具执行前后，TokenBudgetHook 只关心工具输出 token 估算，它们不需要为不关心的钩子写空实现（虽然当前代码里还是写了 pass 桩，那是为了可读性）；第三，`runtime_checkable` 装饰器保留了运行时的 isinstance 检查能力。
>
> HookManager 的链式调用设计很简单：维护一个有序 Hook 列表，每个钩子点按注册顺序遍历调用。一个细节是 `on_run_started` 用了 `getattr` 加判空的防御式写法，其他六个钩子直接调用对应方法。
>
> 四个内置 Hook 各司其职。RetryHook 采用了不同的集成方式——它不是在钩子点里做重试，而是暴露 `execute_with_retry` 方法，由 AgentLoop 在 `_execute_single_tool` 中直接调用。重试策略是指数退避，默认最多 3 次重试，只对 timeout、rate limit、503 等可重试错误生效。TracingHook 记录每个工具调用的耗时和成功率，用 `perf_counter` 做高精度计时，通过 `_pending` 字典匹配 before 和 after。TokenBudgetHook 用简单的 4 字符/token 估算来监控输出 token，在超过 80% 预算阈值时告警。LoggingHook 是唯一覆盖全部 7 个钩子的内置实现，提供全链路日志。
>
> 最后是 SubAgent 场景。ParentChannelHook 是关键，它显式继承了 Hook Protocol，在父 agent 的每次 `after_tool_execute` 中非阻塞地轮询子 agent 结果。它持有一个对父 agent 消息列表的共享可变引用，子 agent 完成后直接以 tool role 的消息格式注入结果，这样父 agent 在下一轮 LLM 调用时就能看到。timeout 设成了极短的 0.01 秒，确保不阻塞父 agent 的正常执行流。
>

---
