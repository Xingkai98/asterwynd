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

### A — 详细参考版

SaveMemory 的触发时机依赖于**外部指令文件**中的行为规则，而非框架内置机制。

**规则来源**：AGENTS.md 的"Agent 持久记忆"章节（`@AGENTS.md` → "保存时机"和"不保存的内容"）明确规定了四类记忆（user/feedback/project/reference）的保存场景：

- **user**: 了解到用户角色/偏好/知识背景时保存
- **feedback**: 用户纠正行为或确认非显然方案时保存
- **project**: 了解到项目约束/截止日期/合规要求等非代码信息时保存
- **reference**: 了解到外部资源位置时保存

同时明确排除：代码模式/架构（可从代码推导）、Git 历史（git log 是权威来源）、临时任务状态、已在 AGENTS.md 中记录的内容。

**注入链路**：AGENTS.md → CLAUDE.md（`@AGENTS.md`）→ `AsterMdSource`（P1）→ 上下文注入。这套规则只有在这条引用链路完整时才会被 Agent 看到。AsterMdSource 从 Git 根目录向 CWD 逐层收集 `ASTER.md` + `ASTER.local.md`（`agent/context/sources.py:252-271`），如果当前工作目录不在配置了 AGENTS.md 的仓库中，这些规则不会被注入。

**工具侧**：`SaveMemoryTool` 的 description（`agent/tools/builtin/memory.py:12-17`）描述了记忆的四种类型和它们的作用，但**不包含"何时该存"的触发场景**。Agent 需要从上下文注入的指令中理解保存时机。

**设计问题（BUG-001）**：P0 系统提示词（`agent/context/sources.py:67-97`）中完全没有提及记忆保存规则。在新文件夹启动 Asterwynd 且没有 ASTER.md 时，Agent 仍然拥有 SaveMemory/RecallMemory 工具，但缺乏使用判断依据——这依赖外部指令文件是否被正确加载。

**RecallMemory 检索**：Agent 看到 MEMORY.md 索引后会按需调用 RecallMemory 工具查看具体记忆内容。MEMORY.md 的 truncation 保护（200 行/25KB）确保不会一次加载所有记忆。

### B — 面试讲稿

> "坦率说，当前机制主要靠外部指令文件中的行为规则来驱动，框架本身没有内置'什么时候该存记忆'的判断逻辑。
>
> 规则写在 AGENTS.md 里——比如用户纠正你的方法时写入 feedback、了解到用户偏好时写入 user、了解到外部资源位置时写入 reference、了解到项目约束时写入 project。同时明确排除了不应保存的内容——能从当前代码推导的架构信息不要存、git log 能查到的历史不要存、临时任务状态不要存。
>
> 注入链路是这样的：AGENTS.md 被 CLAUDE.md 的 `@AGENTS.md` 引用，然后被 AsterMdSource 作为 P1 优先级注入上下文。P1 是 critical 层，永远不会被截断。SaveMemory 工具本身的 description 描述了四种记忆类型，但没有触发场景提示——Agent 需要从注入的指令中理解'什么时候该存'。
>
> 这里有一个已知缺陷：P0 系统提示词里完全没有记忆保存规则。如果在没有 ASTER.md 的新文件夹启动，Agent 有 SaveMemory 工具但不知道该什么时候用。理想情况下，记忆保存时机的核心规则应该内嵌到系统提示词或工具描述中，作为框架级基础能力，不依赖外部指令文件。
>
> 检索侧是两级设计——Agent 首先看到 MEMORY.md 索引，一个条目一行；需要详细信息时调用 RecallMemory，系统按文件名链接去读完整内容。这样避免了一次性把全部记忆灌进上下文。"

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

WorkspacePolicy 的 denylist（`rm -rf /`、`shutdown`、fork bomb、`curl | bash` 等 57 条正则）是正则硬匹配，不依赖人。两层之间：权限管边界，Policy 做最后安全网。

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

三道防线：超时+输出限制（30s / 1MB）、进程组清理（`run_background()` 中 `os.setsid` + `os.killpg`，普通 `run()` 无进程组隔离）、WorkspacePolicy 黑白名单。没有 Docker/容器、没有 chroot/namespace/cgroup、没有网络隔离。

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

## Q9: Plan-Execute 模式的设计——状态机、不变式与模式切换

## Version A -- 详细参考版

### 1. PlanItem 状态模型

Plan-Execute 模式的核心数据类型定义在 `agent/planning/manager.py`。

**PlanStatus 联合类型**（第 7 行）：

```python
PlanStatus = Literal["pending", "in_progress", "completed", "failed", "skipped"]
```

五个状态构成一个单向非循环的状态空间：
- `pending`：初始状态，尚未开始
- `in_progress`：正在执行（全局最多一个）
- `completed`：正常完成
- `failed`：执行失败
- `skipped`：被跳过（如用户决定不实现某一步）

`PLAN_STATUSES` 元组（第 8-14 行）是所有合法状态的枚举值，用于校验。

**PlanItem 数据类**（第 17-42 行）：

```python
@dataclass
class PlanItem:
    id: str           # 自动生成，格式 "item-{n}"
    content: str      # 步骤描述文本
    status: PlanStatus = "pending"
    note: str | None = None
```

它提供了 `to_dict()` / `from_dict()` 序列化方法。`from_dict()` 是防御性的——如果读到的 status 不在 `PLAN_STATUSES` 中，会默认回退为 `"pending"`（第 35-36 行），防止脏数据污染运行时。

**PlanningManager 类**（第 45-130 行）维护 `self._items: list[PlanItem]` 和自增 ID 计数器 `self._next_id`，对外暴露三个核心方法：`set_plan()`、`update_item()`、`snapshot()`。

### 2. "only one in_progress" 不变式

**位置**：`manager.py` 第 71-77 行

```python
if status == "in_progress":
    in_progress = [
        existing for existing in self._items
        if existing.status == "in_progress" and existing.id != item_id
    ]
    if in_progress:
        raise ValueError("only one in_progress plan item is allowed")
```

**设计意图**：Plan-Execute 模式的本质是串行推理——模型一次只应专注于一个步骤。如果有两个步骤同时 in_progress，说明状态的确定性被破坏了。这个不变式在 `update_item()` 的写入路径上强制检查，不是在读取时做 soft check。

**强制执行的点**：只有 `update_item()` 可以变更状态。`set_plan()` 重建全部 items 时不会触发此检查（因为它会先清空 `_items`，再创建全 `pending` 的新列表），所以不存在竞争条件。

**错误处理**：抛出 `ValueError` 而不是静默修改，调用方（`AgentLoop.update_plan_item()` 在 `loop.py:188-199`）会将这个异常自然地传播到工具调用链中，由 `_execute_single_tool()` 的 retry 逻辑（`loop.py:908-913`）捕获，最终以 `[Error: ...]` 前缀的字符串返回给 LLM，让模型感知到约束违规。

### 3. Snapshot 与恢复

**Snapshot 输出**（`manager.py` 第 83-88 行）：

```python
def snapshot(self) -> dict:
    items = [item.to_dict() for item in self._items]
    return {
        "items": items,
        "summary": self.summary(items),
    }
```

`summary()`（第 90-106 行）计算每个状态的计数、总步骤数以及当前 in_progress 的 item。这个 dict 结构是 PlanningManager 的所有可观察状态的完整投影。

**跨 session 恢复**：PlanningManager 本身是内存对象，没有 `load_snapshot()` 方法。跨 session 的持久化和恢复走的是两层机制：

- **Session 级持久化**：`agent/session.py` 的 `SessionSnapshot`（第 16-28 行）将 `mode: AgentMode` 和 `todos: list[PlanItem]` 写入磁盘。`SessionStore.save()`（`session.py:70-85`）在每次 AgentLoop.run() 结束时调用（`loop.py:460-461`），写入 `snapshot.json` 和 `messages.json`。
- **Session 恢复**：`AgentLoop._run()` 的 resume 路径（`loop.py:479-506`）读取 `resume_snapshot`，将 mode 恢复（第 483-484 行）、execution todos 恢复到 `_execution_todos`（第 485 行）。PlanningManager 本身不会被直接恢复——它的生命周期在单个 AgentLoop 实例内。但 plan document 状态（`_plan_document` / `_plan_document_final`，`loop.py:115-116`）会通过 plan tools 的重新注册来重建：当 mode 被恢复为 PLAN 时，`_ensure_plan_tools_registered()`（`loop.py:290-295`）重新注入 UpdatePlanTool 和 ExitPlanModeTool，允许模型继续之前的规划流程。

注意：PlanningManager 的 `_items`（计划步骤的状态机）和 AgentLoop 的 `_execution_todos`（构建模式下的 TodoWrite 列表）是**两套独立的数据结构**。前者用于 plan 模式的计划追踪，后者用于 build 模式的任务进度。但它们共享 PlanItem 类型（`loop.py:54` 的 `from agent.planning import PlanItem`），且 TodoWrite 的 create/update callbacks 直接使用 PlanItem 实例（`loop.py:318-339`）。

### 4. 模式切换行为

**AgentMode 枚举**（`agent/run_config.py` 第 18-22 行）：

```python
class AgentMode(str, Enum):
    BUILD = "build"
    READ_ONLY = "read_only"
    PLAN = "plan"
    BYPASS = "bypass"
```

**切换入口**：`AgentLoop.set_mode()`（`loop.py:147-175`）。

核心流程：
1. 调用 `self.runtime_state.set_mode()`（`run_config.py:56-74`），这是一个线程安全的状态转换（`self._lock` + 原子更新 `_current_mode`），返回 `{"old_mode": ..., "new_mode": ..., "source": ..., "reason": ...}`。
2. 如果新 mode 是 PLAN，调用 `_ensure_plan_tools_registered()` 注册 UpdatePlanTool 和 ExitPlanModeTool。
3. 通过 trace_recorder 和 on_event 发布 `mode_changed` 事件。

**Plan -> Build 切换时状态保留**：
- `PlanningManager._items` 保留在内存中（AgentLoop 实例存活），不会被清除。
- plan document（`_plan_document`）保留，`_plan_document_final` 标志保留。
- `PlanningStateSource` 在 build 模式下仍然会渲染（`sources.py:367-370`），因为它没有 mode gate —— `render_context()` 在 `_items` 为空时只返回空字符串。这意味着：如果从 plan 模式切到 build 模式时 PlanningManager 里还有 plan items，它们**仍然会被注入 context**，作为执行参考。
- execution todos（`_execution_todos`）是 build 模式专属的，只有 `TodoSource._renderer` 在非 plan 模式才渲染（`loop.py:1062-1064`）。

**Build -> Plan 切换时**：
- execution todos 不再注入 context（`TodoSource` 的 renderer 在非 build/read_only 模式返回空）。
- UpdatePlanTool 和 ExitPlanModeTool 被注册（`_ensure_plan_tools_registered` 的幂等注册）。
- `PlanModeSource` 开始注入 plan 模式指令（`sources.py:342-354`），明确告诉模型：不可编辑文件、不可运行 shell、仅做只读调研和讨论。

**模式切换的工具访问控制**：`ModePolicy.decide_tool()`（`run_config.py:101-175`）检查 `tool.allowed_modes`。
- UpdatePlanTool 和 ExitPlanModeTool 设置 `allowed_modes = ("plan",)`（`plan.py:49` 和继承），离开 plan 模式后自动不可见。
- Build 模式的写工具（Edit、Write、Bash）在 plan 模式不可见。

### 5. Plan Document 工作流

**两个工具**（`agent/tools/builtin/plan.py`）：

- **UpdatePlanTool**（第 45-78 行）：更新草稿。参数为 `title`、`plan_markdown`、`steps`。调用 `_save_plan`（实际绑定到 `AgentLoop.update_plan_document`），设置 `_plan_document.status = "draft"` 且 `_plan_document_final = False`。返回值是 `[Plan draft updated: {title} ({step_count} steps)]`。

- **ExitPlanModeTool**（第 90-101 行）：继承自 UpdatePlanTool，复用参数 schema 和 `_parse_args`。区别在于调用 `_save_plan`（绑定到 `AgentLoop.submit_plan_document`），设置 `_plan_document.status = "submitted"` 且 `_plan_document_final = True`。返回 `[Plan submitted: {title} ({step_count} steps)]`。

**工具注册**（`loop.py:290-295`）：

```python
def _ensure_plan_tools_registered(self) -> None:
    if self._plan_tools_registered:
        return
    self.tool_registry.register(UpdatePlanTool(self.update_plan_document))
    self.tool_registry.register(ExitPlanModeTool(self.submit_plan_document))
    self._plan_tools_registered = True
```

注意：callback 绑定有区别——UpdatePlanTool 绑定 `self.update_plan_document`，ExitPlanModeTool 绑定 `self.submit_plan_document`。两者都传递 `SavePlanCallback` 类型（`plan.py:10`）：`Callable[[str, str, list[str]], Awaitable[dict[str, Any]]]`。

**两种 plan document 写入路径**（`loop.py:201-261`）：

- `update_plan_document()`（第 201-230 行）：先 `set_plan(steps)` 重建 PlanItem 列表，生成 `{"title", "markdown", "steps", "planning_state", "status": "draft"}` 的 document dict，发布 `plan_document_updated` 事件。
- `submit_plan_document()`（第 232-261 行）：结构相同但 `status` 为 `"submitted"`，`_plan_document_final = True`，发布 `plan_document_submitted` 事件。两者都返回完整的 document dict。

**事件发布**（`loop.py:276-288`）：通过 `_publish_plan_document()` 同时写入 trace_recorder 和 on_event callback，实现了文档状态的可观测性。

### 6. Context 注入管线

**注入架构**：`ContextBuilder`（`agent/context/builder.py`）按优先级 0-5 排序所有 `ContextSource`，渲染后按 total_budget 从最低优先级尾部截断。P0 级标记 `critical=True` 永不被截断。

**P5 层 Plan 相关 Source**（`agent/context/sources.py`）：

- **PlanModeSource**（第 335-354 行）：priority=5, budget=2500, critical=False。仅在 `context.mode is AgentMode.PLAN` 时渲染。注入内容为 plan 模式的行为指令：只读调研、用 UpdatePlan 更新草稿、用户确认后调用 ExitPlanMode、不可编辑文件或运行命令。

- **PlanningStateSource**（第 357-370 行）：priority=5, budget=1500, critical=False。始终渲染（无 mode gate）。调用 `self._planning.render_context()` 输出格式化的计划状态文本：
  ```
  Current structured planning state:
  - [pending] 设计数据库 schema
  - [in_progress] 实现 API 路由
  - [completed] 初始化项目结构
  ```

- **TodoSource**（第 373-386 行）：priority=5, budget=1000, critical=False。通过回调函数渲染，回调是 `AgentLoop._todo_context()`（`loop.py:1061-1081`）。仅在 build 或 read_only 模式且 `_execution_todos` 非空时渲染最近 10 个按状态排序的 todo items。

**P5 层预算共享**：三个 source 共享 P5 的约 5K 预算（PlanModeSource 2.5K + PlanningStateSource 1.5K + TodoSource 1K = 5K）。当总注入超过 `_injection_budget`（`loop.py:1038-1041`，min(20K, 20% 上下文窗口)）时，ContextBuilder 从最低优先级的非 critical 层尾部截断。P5 是倒数第二低的优先级（仅 P6 更低），因此在高注入压力下最容易被截断。

**AgentLoop 中的注册顺序**（`loop.py:1043-1059`）：

```python
def _make_default_context_builder(self) -> ContextBuilder:
    builder = ContextBuilder(total_budget=self._injection_budget)
    builder.register(SystemPromptSource())        # P0
    builder.register(AsterMdSource())              # P1
    builder.register(MemoryIndexSource(...))       # P2
    builder.register(SkillIndexSource(...))        # P4
    builder.register(SkillActiveSource(...))       # P4
    builder.register(PlanModeSource())             # P5
    builder.register(PlanningStateSource(...))     # P5
    builder.register(TodoSource(...))              # P5
    return builder
```

同优先级（P5 三个 source）按注册顺序排列，ContextBuilder 不会在同优先级内重新排序。

**每轮迭代触发**：`_messages_with_run_context()`（`loop.py:1009-1031`）在每次 LLM 调用前执行，生成 `BuildContext`（包含 cwd、mode、context_window、total_budget、user_system_prompt），调用 `context_builder.build(ctx)`，将渲染结果作为 system 消息插入到最后一条 system 消息之后。


## Version B -- 面试讲稿版

> Plan-Execute 模式的设计核心是一个五状态 PlanItem 模型加上一系列约束保证状态的确定性和可恢复性。
>
> 首先说数据结构。PlanStatus 是一个 Literal 类型的联合——pending、in_progress、completed、failed、skipped，五个状态。PlanItem 是一个 dataclass，包含 id、content、status 和一个可选的 note。PlanningManager 作为聚合根，维护了一个 PlanItem 列表和自增 ID，对外暴露 set_plan、update_item 和 snapshot 三个核心方法。
>
> 关键的不变式是"全局最多一个 in_progress"。这个检查写在 update_item 方法里，当有人试图把某个 item 设成 in_progress 时，先遍历所有现有 items，看是否已有其他 item 处于 in_progress 状态。如果有，直接抛 ValueError。这个设计保证了一次只有一个步骤在执行，Plan-Execute 的串行推理不被破坏。
>
> Snapshot 机制做的是全量序列化。PlanningManager 的 snapshot 方法把 items 列表和 summary 统计一起转成 dict——summary 里包含每种状态的数量和当前 in_progress 的 item。这个 dict 是计划状态的可观察投影。跨 session 恢复不直接通过 PlanningManager，而是走 SessionSnapshot。AgentLoop 的 run 方法在结束时调用 session store 持久化——写入 snapshot.json 和 messages.json，把 mode、todos、消息链都存下来。resume 时读取 snapshot，恢复 mode、execution todos，并且如果 mode 是 plan 就重新注册 plan tools。
>
> 关于模式切换。四个模式——build、read_only、plan、bypass。切换入口是 AgentLoop.set_mode，它调用 AgentRuntimeState.set_mode，这是一个带线程锁的原子状态转换。从 plan 切到 build 时，PlanningManager 的 items 不会清空，PlanningStateSource 仍然会把计划注入 context——因为没有 mode gate——所以模型在 build 模式下仍然能看到之前的计划步骤作为参考。反过来，从 build 切到 plan 时，PlanModeSource 开始注入 plan 模式的行为指令，明确告诉模型只读调研、不编辑文件。
>
> Plan Document 工作流由两个工具驱动。UpdatePlanTool 用于中间草稿更新，设置 status 为 draft；ExitPlanModeTool 继承同一个参数 schema，但调用 submit_plan_document 设置 status 为 submitted 并标记 finalized。两个工具都通过 _ensure_plan_tools_registered 在进入 plan 模式时幂等注册，allowed_modes 限定为 plan。工具注册时把 AgentLoop 的 update_plan_document 或 submit_plan_document 作为 callback 注入，形成闭环。
>
> 最后是 Context 注入管线。ContextBuilder 按 P0 到 P6 的优先级排序，渲染后按注入预算从尾部截断。Plan 相关的是 P5 层三个 source：PlanModeSource 在 plan 模式时注入行为指令，PlanningStateSource 始终渲染 PlanningManager.render_context 的格式化输出，TodoSource 仅在 build/read_only 模式有活跃 todos 时渲染。P5 三个 source 共享约 5K 的预算，在高注入压力下是非关键层中最先被截断的。每轮 LLM 调用前通过 _messages_with_run_context 执行注入，保证模型始终感知最新的 plan 状态。


---
## Q10: 工具系统的架构设计 -- ABC 基类、装饰器、Schema 生成与工厂组装


## Version A -- 详细参考版

### 1. Tool ABC 基类设计 (`agent/tools/base.py` L37-82)

`Tool` 是一个抽象基类，继承自 `abc.ABC`，定义了所有工具的统一契约。核心接口由两部分组成：**属性声明**（元数据）和 **`execute()` 抽象方法**（行为）。

**属性声明 (L39-46):**

```python
class Tool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema
    read_only: bool = False
    dangerous: bool = False
    parallelizable: bool = False
    allowed_modes: tuple[str, ...] | None = None
    permission: ToolPermission | None = None
```

这些属性的含义：
- `name` / `description` / `parameters`：组成 LLM function-calling schema 的三要素，通常由 `@tool_parameters` 装饰器注入。
- `read_only`：标记工具是否只读（`base.py` L42）。用于 `get_permission()` 中的 fallback 权限推断。
- `dangerous`：标记工具是否有危险性（L43），如 `BashTool` 设为 `True`。在 `ToolRegistry.get_sandbox()` 中被读取以判断是否需要沙箱（`registry.py` L29-30）。
- `parallelizable`：标记工具是否可并行执行（L44），如 `ReadTool` 和 `GrepTool` 均设为 `True`。
- `allowed_modes`：显式限制工具只能在特定模式下可见。如果为 `None`，则交由 `ModePolicy` 全局策略决定。
- `permission`：显式指定权限对象。若为 `None`，则由 `get_permission()` 方法按 dangerous / read_only fallback 规则自动推断（L63-82）。

**`execute()` 抽象方法 (L48-51):**

```python
@abstractmethod
async def execute(self, **kwargs) -> str | list["ContentBlock"]:
    """执行工具，返回结果字符串或 content blocks 列表"""
    ...
```

所有子类必须实现异步 `execute()`。返回值支持两种类型：
- `str`：纯文本结果（大多数工具），如 `ReadTool` 返回文件内容，`GrepTool` 返回匹配行。
- `list[ContentBlock]`：富文本结果，如 `ReadTool._read_image()` 在读取图片时返回 `[TextBlock, ImageBlock]`（`read.py` L128-134），以支持多模态输出。

**`get_permission()` 智能推断 (L63-82):**

```python
def get_permission(self) -> ToolPermission:
    if self.permission is not None:
        return self.permission
    if self.dangerous:
        return ToolPermission(
            capabilities=frozenset({ToolCapability.COMMAND_EXECUTE}),
            risk_level=ToolRiskLevel.HIGH,
            origin=ToolOrigin.BUILTIN,
        )
    if self.read_only:
        return ToolPermission(
            capabilities=frozenset({ToolCapability.WORKSPACE_READ}),
            risk_level=ToolRiskLevel.LOW,
            origin=ToolOrigin.BUILTIN,
        )
    return ToolPermission(
        capabilities=frozenset({ToolCapability.WORKSPACE_WRITE}),
        risk_level=ToolRiskLevel.MEDIUM,
        origin=ToolOrigin.BUILTIN,
    )
```

这是 ABC 中唯一的非抽象方法，提供了三级 fallback 策略：
1. 如果子类显式设置了 `permission`（如 `ReadTool.permission = WORKSPACE_READ_PERMISSION`），直接返回。
2. 如果 `dangerous=True`，自动推断为 `COMMAND_EXECUTE` + `HIGH` 风险等级。
3. 如果 `read_only=True`，推断为 `WORKSPACE_READ` + `LOW` 风险等级。
4. 否则默认视为写入操作：`WORKSPACE_WRITE` + `MEDIUM` 风险等级。

**`ToolCall` 数据类 (L85-94):**

```python
@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    @classmethod
    def from_delta(cls, delta: "ToolCallDelta", arguments: dict) -> "ToolCall":
        return cls(id=delta.id, name=delta.name, arguments=arguments)
```

`ToolCall` 是对 LLM 返回的一次工具调用的结构化封装。`from_delta()` 类方法从流式增量 `ToolCallDelta` 和已完成的 `arguments` 构造完整调用对象，用于解耦流式解析与执行。


### 2. `@tool_parameters` 装饰器模式 (`agent/tools/base.py` L19-34)

```python
def tool_parameters(
    name: str,
    description: str,
    parameters: dict,
):
    """工具装饰器：附加元信息到 Tool 子类"""
    def decorator(cls):
        # Only set from decorator args if class doesn't already define them with truthy values
        if not getattr(cls, 'name', None):
            cls.name = name
        if not getattr(cls, 'description', None):
            cls.description = description
        if not getattr(cls, 'parameters', None):
            cls.parameters = parameters
        return cls
    return decorator
```

**设计核心：装饰器提供默认值，类属性可覆盖**

装饰器通过 `getattr(cls, attr, None)` 检查类是否已定义同名属性，只在类未定义（或值为 falsy）时才注入。这意味着三层优先级：
1. 类体中直接定义的属性（最高优先）
2. 装饰器参数（默认值）
3. ABC 基类的类型注解（无实际值，falsy）

**实际使用中**，当前所有内置工具均使用装饰器提供全部三个元数据，类体只设置行为标记：

- `ReadTool` (`read.py` L53-68)：装饰器设置 name/description/parameters；类体设置 `read_only=True, parallelizable=True, permission=WORKSPACE_READ_PERMISSION`
- `BashTool` (`bash.py` L22-41)：装饰器设置 name/description/parameters；类体设置 `dangerous=True, permission=COMMAND_EXECUTE_PERMISSION`
- `GrepTool` (`grep.py` L9-26)：装饰器设置 name/description/parameters；类体设置 `read_only=True, parallelizable=True, permission=WORKSPACE_READ_PERMISSION`
- `EditTool` (`edit.py` L10-33)：装饰器设置 name/description/parameters；类体设置 `read_only=False, permission=WORKSPACE_WRITE_PERMISSION`

**设计意图**：如果将来某个工具需要运行时根据构造参数动态生成 description 或 parameters，可以在 `__init__` 中设置类属性，装饰器的 `getattr` 检查会因类已定义而跳过，从而实现覆盖。当前代码中尚未使用此特性，但架构上已预留。


### 3. `Tool.get_schema()` -- LLM Schema 生成 (`agent/tools/base.py` L53-61)

```python
def get_schema(self) -> dict:
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        },
    }
```

这是将工具元数据组装为 **OpenAI function-calling 兼容格式** 的唯一入口。组装逻辑极其简洁：
- 外层 `"type": "function"` 是 OpenAI Chat Completions API `tools` 参数要求的格式。
- 内层 `"function"` 对象包含三个字段：`name`、`description`、`parameters`（JSON Schema）。
- 每个工具实例自行提供这些字段，因此 `get_schema()` 对任何 `Tool` 子类都是通用的，无需重写。

**在 ToolRegistry 中的调用链**：
1. `ToolRegistry.get_all_schemas()` (`registry.py` L22-27) 对每个通过 `ModePolicy.is_tool_allowed()` 过滤的工具调用 `tool.get_schema()`。
2. 返回的 schema 列表最终被送入 LLM 的 `tools` 参数。

**McpTool 的 Schema 适配**：`McpTool` (`mcp/tools.py` L10-23) 在 `__init__` 中直接设置 `self.name`、`self.description`、`self.parameters`，因此继承的 `get_schema()` 无需任何修改即可工作：
```python
class McpTool(Tool):
    def __init__(self, metadata: McpToolMetadata, manager: McpManager):
        self.name = metadata.callable_name
        self.description = metadata.description or (...)
        self.parameters = metadata.input_schema
        self.permission = metadata.permission
        ...
```


### 4. 工厂组装模式 (`agent/tools/factory.py`)

**`build_default_tool_registry()` (L77-101)** 是工具系统的主装配函数，接受依赖注入参数并产出配置完整的 `ToolRegistry` 实例。

**函数签名 (L77-88):**

```python
def build_default_tool_registry(
    *,
    policy: WorkspacePolicy | None = None,
    mode_policy: ModePolicy | None = None,
    ignore_patterns: tuple[str, ...] = (),
    code_intelligence_config: CodeIntelligenceConfig | None = None,
    web_search_config: WebSearchConfig | None = None,
    browser_config: BrowserConfig | None = None,
    mcp_manager: McpManager | None = None,
    tools: list[Tool] | None = None,
    persistent_memory: PersistentMemory | None = None,
) -> ToolRegistry:
```

所有参数使用 keyword-only 约束（`*` 之后的参数），防止误传位置参数。

**装配流程 (L89-101):**

```python
registry = ToolRegistry(mode_policy=mode_policy)
default_tools = tools or get_default_tools(
    policy=policy,
    ignore_patterns=ignore_patterns,
    code_intelligence_config=code_intelligence_config,
    web_search_config=web_search_config,
    browser_config=browser_config,
    persistent_memory=persistent_memory,
)
for tool in [*default_tools, *_build_mcp_tools(mcp_manager)]:
    registry.register(tool)
registry.mode_policy.validate_known_tools(_known_tool_names(registry))
return registry
```

三步装配：
1. 创建空的 `ToolRegistry`，注入 `mode_policy`。
2. 合并内置工具列表（来自 `get_default_tools()`）和 MCP 工具列表（来自 `_build_mcp_tools()`），逐一注册。
3. 校验：`validate_known_tools()` 确保 `mode_policy` 中引用的 `deny_tools` 白名单与实际注册的工具名一致，不存在未知工具名。

**`get_default_tools()` 功能域分组 (L162-206):**
按功能域组织的约 20 个核心工具（另有 Todo、BackgroundTask、Subagent 等通过外部注入注册）：

| 功能域 | 工具类 | 文件 |
|--------|--------|------|
| 文件 | `ReadTool`, `WriteTool`, `EditTool` | `builtin/read.py`, `builtin/write.py`, `builtin/edit.py` |
| 搜索 | `GrepTool` | `builtin/grep.py` |
| 命令/沙箱 | `BashTool` | `builtin/bash.py` |
| Git | `InspectGitDiffTool` | `builtin/inspect_git_diff.py` |
| 代码智能 | `RepoMapTool`, `SymbolSearchTool` | `builtin/code_intelligence.py` |
| LSP | `LspDefinitionTool`, `LspReferencesTool`, `LspHoverTool`, `LspDocumentSymbolsTool`, `LspWorkspaceSymbolsTool`, `LspDiagnosticsTool` | `builtin/lsp.py` |
| Web | `WebSearchTool`, `WebFetchTool` | `builtin/web_search.py`, `builtin/web_fetch.py` |
| 浏览器 | `BrowserNavigate`, `BrowserGetContent`, `BrowserScreenshot`, `BrowserScroll`, `BrowserListTabs`, `BrowserSwitchTab`, `BrowserCloseTab` | `builtin/browser_tools.py` |
| 记忆 | `SaveMemoryTool`, `RecallMemoryTool` | `builtin/memory.py` |
| 子代理 | `TaskOutput`, `TaskStop`, `TodoWrite`, `ActivateSkill` (在 `KNOWN_BUILTIN_TOOL_NAMES` 中声明但通过外部注入) | 见 L39-74 |

**MCP 工具适配 (`_build_mcp_tools()`, L104-107):**

```python
def _build_mcp_tools(mcp_manager: McpManager | None) -> list[Tool]:
    if mcp_manager is None:
        return []
    return [McpTool(metadata, mcp_manager) for metadata in mcp_manager.tools]
```

每个 MCP 服务器提供的工具元数据被包装为 `McpTool` 实例。`McpTool` 继承 `Tool` ABC，在 `execute()` 中委托给 `McpManager.call_tool()` (`mcp/tools.py` L22-23)。

**浏览器工具条件注册 (L199-204):**

```python
if browser_config is not None and browser_config.enabled:
    try:
        browser_tools = _build_browser_tools(browser_config, policy)
        tools.extend(browser_tools)
    except Exception as exc:
        logger.warning("Failed to initialize browser tools: %s", exc)
```

浏览器工具仅在 `BrowserConfig.enabled=True` 且 `playwright` 可用时才注册，否则静默跳过。

**`build_coding_tool_registry()` (L110-133)** 是一个精简变体，省略了 `WebSearchTool` 和 `WebFetchTool`，适用于不需要网络搜索能力的编码场景。


### 5. `ToolRegistry` 数据结构 (`agent/tools/registry.py`)

**核心数据结构 (L12-13):**

```python
class ToolRegistry:
    def __init__(self, mode_policy: ModePolicy | None = None):
        self._tools: dict[str, Tool] = {}
        self.mode_policy = mode_policy or ModePolicy()
```

`_tools` 以工具名称为键、`Tool` 实例为值的字典，保证 O(1) 按名查找。

**注册 (`register`, L16-17):**

```python
def register(self, tool: Tool) -> None:
    self._tools[tool.name] = tool
```

以 `tool.name` 为键，覆盖式注册。后注册的同名工具会覆盖先注册的，这允许工厂中 MCP 工具按需覆盖内置工具（当前未使用此特性，但字典结构天然支持）。

**Schema 获取 (`get_all_schemas`, L22-27):**

```python
def get_all_schemas(self) -> list[dict]:
    return [
        tool.get_schema()
        for tool in self._tools.values()
        if self.mode_policy.is_tool_allowed(tool)
    ]
```

通过列表推导式实现两阶段过滤：
1. 遍历所有注册工具。
2. 对每个工具调用 `mode_policy.is_tool_allowed(tool)`，该方法内部调用 `decide_tool()` 检查 `is_visible` 属性（`run_config.py` L98-99）。只有 `PermissionDecisionType` 不是 `DENY` 的工具才可见。
3. 通过过滤的工具调用 `get_schema()` 组装 LLM schema。

这意味着：`build` / `read_only` / `plan` 模式下，LLM 只会看到当前模式允许的工具列表，从源头防止 LLM 生成越权调用。

**执行 (`execute`, L32-46):**

```python
async def execute(self, tool_call: ToolCall, *, approval_granted: bool = False) -> str | list["ContentBlock"]:
    tool = self._tools[tool_call.name]
    decision = self.mode_policy.decide_tool(tool)
    if decision.type is PermissionDecisionType.DENY:
        mode = self.mode_policy.mode.value
        return (
            f"[Permission denied: tool {tool_call.name} is not allowed "
            f"in {mode} mode: {decision.reason}]"
        )
    if decision.type is PermissionDecisionType.REQUIRE_APPROVAL and not approval_granted:
        return (
            f"[Approval required: tool {tool_call.name} requires approval "
            f"in {self.mode_policy.mode.value} mode]"
        )
    return await tool.execute(**tool_call.arguments)
```

执行流程包含三层防护：
1. 按 `tool_call.name` 查找工具实例（O(1)）。
2. 通过 `mode_policy.decide_tool()` 获得权限决策：
   - `DENY`：返回带原因的错误字符串，不执行。
   - `REQUIRE_APPROVAL` 且未批准：返回要求批准的提示。
   - `ALLOW` 或已批准：通过。
3. 调用 `tool.execute(**tool_call.arguments)` 解包参数执行。

**沙箱检查 (`get_sandbox`, L29-30):**

```python
def get_sandbox(self, name: str) -> bool:
    return self._tools[name].dangerous
```

简化的沙箱判断：直接查询工具的 `dangerous` 属性。当前仅 `BashTool` 返回 `True`。

**单工具查询 (`get_tool`, L48-49):**

```python
def get_tool(self, name: str) -> Tool:
    return self._tools[name]
```

纯字典查找，用于需要直接访问工具实例的场景（如单元测试中获取工具引用）。


### 架构全景图

```
                    +--------------------------+
                    |   build_default_tool_    |
                    |   registry()             |
                    |   (factory.py L77)        |
                    +-----------+--------------+
                                |
                +---------------+---------------+
                |                               |
     +----------v----------+         +----------v----------+
     | get_default_tools() |         | _build_mcp_tools()  |
     | (L162)              |         | (L104)              |
     |                      |         |                      |
     | ReadTool              |         | McpTool(metadata,    |
     | WriteTool             |         |   mcp_manager)       |
     | EditTool              |         +---------------------+
     | BashTool              |
     | GrepTool              |
     | ... (~20 core tools)   |
     +----------+-----------+
                |
     +----------v-----------+
     | @tool_parameters(...) |  <-- class-level decorator
     | class ReadTool(Tool): |      attaches name/desc/params
     |   read_only = True    |      only if class not defined
     |   execute() -> str    |
     +----------+-----------+
                |
     +----------v-----------+
     | Tool ABC              |
     |   name/desc/params    |
     |   read_only/dangerous |
     |   parallelizable      |
     |   allowed_modes       |
     |   permission          |
     |   execute() abstract  |
     |   get_schema()        |
     |   get_permission()    |
     +----------+-----------+
                |
                v
     +---------------------+
     | ToolRegistry         |
     | _tools: dict[str,Tool]|
     | mode_policy           |
     | register()            |
     | get_all_schemas()     |  -->  filtered by ModePolicy
     | execute()             |  -->  DENY/APPROVAL/ALLOW
     | get_sandbox()         |
     +---------------------+
```


## Version B -- 面试讲稿版

> 我来介绍一下 Asterwynd 的工具系统架构，核心设计围绕四个层：Tool ABC 基类、@tool_parameters 装饰器、工厂装配和 ToolRegistry 注册中心。
>
> 首先看 Tool ABC，定义在 `agent/tools/base.py`。它是一个抽象类，声明了所有工具的统一契约。每个工具必须实现 `async execute()` 方法，返回字符串或 ContentBlock 列表——为什么支持列表呢？比如 ReadTool 读图片时，既要返回文本描述也要返回 base64 图片块，这是一种多模态输出需求。除了 execute，ABC 还声明了七个属性：name、description、parameters 这三个给 LLM 看；read_only、dangerous、parallelizable 三个行为标记；allowed_modes 控制工具在哪些模式下可见；permission 是显式权限对象。其中 `get_permission()` 是 ABC 中唯一的非抽象方法，它实现了一个三级 fallback：子类显式设置了 permission 就用子类的；否则如果 dangerous 是 true，自动推断为高危命令执行权限；如果 read_only 是 true，推断为低危只读权限；都不满足就给一个中危写入权限。这样大部分工具只需设置 boolean flag，不用手动构造复杂的 Permission 对象。
>
> 第二，`@tool_parameters` 装饰器。它的设计非常简洁：接收 name、description、parameters 三个参数，通过 `getattr` 检查类是否已经定义。如果类没定义就注入，定义了就跳过。这意味着装饰器提供默认值，类体可以覆盖——虽然当前所有内置工具都把元数据写死在装饰器参数里，但架构上预留了运行时动态覆盖的能力。
>
> 第三，`get_schema()` 方法。它把工具的 name、description、parameters 组装成 OpenAI function-calling 格式，最外层 type 是 function，里面包一个 function 对象。每个工具的 get_schema 返回结果完全一致，因为结构是通用的。
>
> 第四，工厂装配。`build_default_tool_registry()` 是主入口，所有参数都是 keyword-only 的，防止调用方传错位置。它先创建空的 ToolRegistry，然后调用 `get_default_tools()` 获取三十多个内置工具——按文件、搜索、编辑、LSP、Web、浏览器、记忆这些功能域分组——然后把 MCP 工具通过 `_build_mcp_tools()` 包装成 McpTool 实例追加到列表里，统一注册。注册完后还要跑 `validate_known_tools`，确保 ModePolicy 里配置的 deny_tools 白名单引用的都是真实存在的工具名，防止配置漂移。
>
> 第五，ToolRegistry 数据结构。核心就是一个 `_tools: dict[str, Tool]`，按工具名索引。它最关键的方法是 `get_all_schemas()`，遍历所有工具时先调用 `mode_policy.is_tool_allowed()` 做可见性过滤。这个方法会检查工具的 allowed_modes、deny_tools 配置、permission profile 的能力和风险阈值，只有真正允许的工具才会被组装成 schema 返回给 LLM。也就是说 LLM 在 plan 模式下压根看不到 Bash 工具，从源头杜绝越权调用。execute 方法也有三层防护：查工具实例、调用 decide_tool 做权限决策、根据 ALLOW/DENY/REQUIRE_APPROVAL 三种结果分别处理。如果 DENY 就直接返回错误信息，如果 REQUIRE_APPROVAL 且还没批准就提示需要审批，只有通过检查才真正执行。
>
> 总结一下，这个架构的精髓在于：ABC 定义契约、装饰器注入元数据、工厂做依赖组装、Registry 做运行时管控。整个系统用起来就是一行 `build_default_tool_registry(...)`，但内部的类型安全、权限过滤、模式感知和 schema 生成都是分层解耦的。


*Source files referenced:*
- `agent/tools/base.py` (L1-95) -- Tool ABC, tool_parameters decorator, get_schema(), ToolCall
- `agent/tools/registry.py` (L1-50) -- ToolRegistry
- `agent/tools/factory.py` (L1-284) -- build_default_tool_registry, get_default_tools, _build_mcp_tools
- `agent/mcp/tools.py` (L1-24) -- McpTool adapter
- `agent/tools/builtin/read.py` (L53-68) -- ReadTool example
- `agent/tools/builtin/bash.py` (L22-41) -- BashTool example
- `agent/tools/builtin/grep.py` (L9-26) -- GrepTool example
- `agent/tools/builtin/edit.py` (L10-33) -- EditTool example
- `agent/run_config.py` (L77-207) -- ModePolicy, decide_tool, is_tool_allowed
- `agent/tool_permissions.py` (L1-78) -- ToolPermission, ToolCapability, ToolRiskLevel


---
## Q11: Web UI 架构——WebSocket 实时交互、SSE 流翻译与 Approval Future 桥接

## Version A -- 详细参考版

### 1. FastAPI + WebSocket 双接口架构

入口函数 `create_app()` 位于 `web/server.py:25-390`，接收 `llm`、`mode`、`config`、`resume` 四个参数，返回一个 FastAPI 实例。架构分为两层：

**REST 端点 (6 个):**

| 路由 | 方法 | 位置 (行) | 功能 |
|---|---|---|---|
| `/` | GET | 48-53 | 返回 `static/index.html` 聊天页面 |
| `/debug` | GET | 55-62 | 返回调试页面（需 `ASTERWYND_DEBUG=1`） |
| `/api/debug-status` | GET | 64-66 | 返回 `{"enabled": bool}` |
| `/api/slash-commands` | GET | 68-73 | 返回已注册的 slash command 目录 |
| `/api/upload-image` | POST | 75-96 | 接收 base64 data URL，写入 `.asterwynd/uploads/` |
| `/api/uploads` | POST | 98-121 | 接收 multipart 图片上传 |

**WebSocket 端点 (1 个):** `/ws/{session_id}` 位于 `server.py:123-388`，是整个交互的核心。消息 dispatch 通过 `raw.get("type")` 路由到 7 种消息处理器：

| msg_type | 功能 | 所在行 |
|---|---|---|
| `chat` | 处理用户输入，先尝试 slash command，再走 AgentLoop | 145-223 |
| `image_upload_start/chunk/finish` | 分片接收 base64 图片 | 225-333 |
| `approval_response` | 转发用户审批决策到 `WebApprovalHandler` | 335-354 |
| `reset` | 销毁旧 session、创建新 session | 356-364 |
| `set_mode` | 切换 Agent 运行模式 | 366-382 |
| `ping` | 心跳 | 384-385 |

`create_app()` 在 36-38 行创建一个 `SessionManager` 实例，它是所有 `AgentSession` 的工厂。


### 2. WebApprovalHandler -- asyncio.Future 同步/异步桥接

这是整个 Web UI 架构中最精妙的设计。核心实现位于 `web/session.py:30-89`。

**问题背景:** AgentLoop 在主循环 `_run()` 中同步（async）等待审批——它调用 `await self.approval_handler.request_approval(...)` 后必须阻塞当前迭代，直到获得决策。但 Web 用户是在另一个异步上下文中、可能数秒甚至数分钟后才点击 "批准/拒绝" 按钮。

**解决方案: `asyncio.Future` 作为"暂停令牌"**

```python
class WebApprovalHandler:                          # session.py:30
    def __init__(self, session_id: str):
        self._pending: tuple[str, asyncio.Future[ApprovalResponse]] | None = None

    async def request_approval(self, request: ApprovalRequest) -> ApprovalResponse:
        # 一次只允许一个审批请求 (行 42-47)
        if self._pending is not None:
            return ApprovalResponse(..., status=UNAVAILABLE)
        future = asyncio.get_running_loop().create_future()  # 行 48
        self._pending = (request.approval_id, future)         # 行 49
        return await future  # ← 阻塞在这里，直到 future 被 set_result (行 51)

    def submit_response(self, approval_id: str, decision: str) -> bool:
        # 校验后 resolve future (行 62-76)
        future.set_result(ApprovalResponse(...))
```

**时序流程:**
1. AgentLoop 在 `agent/loop.py:692` 调用 `await self.approval_handler.request_approval(approval_request)`。
2. `WebApprovalHandler.request_approval()` 创建 `asyncio.Future`，存入 `_pending`，然后 `await future`。AgentLoop 迭代在此暂停。
3. AgentLoop 同时通过 `on_event("approval_request", ...)` (loop.py:690) 向前端推送审批请求——这会进入 `asyncio.Queue` 再送到 WebSocket。
4. 用户在浏览器点击批准/拒绝，前端发送 `{"type": "approval_response", "approval_id": "...", "decision": "..."}`。
5. WebSocket 端点在 `server.py:335-354` 接收消息，调用 `session.approval_handler.submit_response(approval_id, decision)`。
6. `submit_response()` 对 future 调用 `future.set_result(...)` (session.py:69-76)，解冻 `request_approval()` 的 `await`。
7. AgentLoop 继续执行，根据 `ApprovalResponse.approved` 决定是否执行工具。

**关键约束:** `_pending` 是单值——同一时间只允许一个审批请求。如果在已有 pending 时再次调用 `request_approval()`，直接返回 `UNAVAILABLE` 状态（行 43-47）。

**清理机制:** `fail_pending()` (session.py:78-89) 在 session reset、WebSocket disconnect、run 结束时被调用，以 `UNAVAILABLE` resolve 任何悬空的 future，防止 AgentLoop 永久挂起。


### 3. SSE 流翻译 -> WebSocket 推送

整个数据流是三层管道：

```
LLM API (SSE bytes) → stream_chat() (LLMStreamEvent) → AgentLoop._call_llm() (on_event回调) → asyncio.Queue → WebSocket
```

**第 1 层 — LLM Provider `stream_chat()`:** 以 OpenAI 为例 (`agent/openai_llm.py:128-205`)，`stream_chat()` 是 async generator，调用 `self._stream_events()`（底层 HTTP SSE 解析），将每个 delta 封装为 `LLMStreamEvent` (agent/llm.py:40-45) yield 出去：

```python
# openai_llm.py:194-198
yield LLMStreamEvent(
    type="assistant_delta",
    delta=text_delta,          # 增量文本
    content="".join(content_parts),  # 累计全文本
)
```

最终 yield `type="complete"` 事件，包含完整 `LLMResponse`。

**第 2 层 — AgentLoop `_call_llm()`:** (`agent/loop.py:826-870`)。当 `self._should_stream_llm()` 为 True，走流式分支：

```python
# loop.py:841-866
async for event in stream_chat(messages=messages, tools=tools):
    if event.type == "assistant_delta":
        await on_event("assistant_delta", {
            "delta": event.delta,
            "content": content,     # 累计文本
        })
    if event.type == "complete":
        await on_event("assistant_stream_complete", {
            "content": content,
            "stop_reason": ...,
        })
```

`on_event` 回调是由 Web 层传入的闭包。

**第 3 层 — SessionManager `run_session()`:** (`web/session.py:206-341`)。在 217-218 行定义了 `on_event` 回调：

```python
async def on_event(event_type: str, data: dict):
    await queue.put({"type": event_type, "data": data})
```

每个事件被放入 `asyncio.Queue`。主循环 (316-320 行) 逐条消费队列，通过 `ws_send(event)` 发送到 WebSocket：

```python
while True:
    event = await queue.get()
    if event is None:       # sentinel, agent 完成
        break
    await ws_send(event)    # 即 ws.send_json(event)
```

**为什么不直接把 `ws.send_json` 作为 `on_event`?** 因为需要双向通信——`run_session` 还要并行跑第二个 task `receive_approval_responses()` (276-313 行)，轮询 WebSocket 接收端检查 approval 响应。Queue 解耦了发送方向和接收方向。


### 4. AgentSession 模式 -- 每浏览器 Tab 一个 AgentLoop

**AgentSession** (`web/session.py:92-113`): 轻量数据对象，持有 4 样东西：

```python
class AgentSession:
    session_id: str                      # 12 位 hex (run_identity.py:6-7)
    agent: AgentLoop                     # 独立的 AgentLoop 实例
    approval_handler: WebApprovalHandler # 该 session 专属的审批处理器
    messages: list[Message]              # 消息历史（对话上下文）
    debug_turn: int = 0                  # 调试轮次计数器
```

**SessionManager** (`session.py:116-341`): 工厂 + 生命周期管理器。

- `_sessions: dict[str, AgentSession]` — 内存字典存储所有活跃 session
- `create_session()` (131-134): 同步版，如果 `config.mcp.servers` 非空则抛 `RuntimeError`——MCP 需要 async 初始化
- `create_session_async()` (136-138): 异步版，先 `await build_mcp_manager(config)` 再调 `_create_session()`
- `_create_session()` (140-191): 核心工厂方法，组装完整的 AgentLoop——创建 `WorkspacePolicy`、`ToolRegistry`、`SubAgentManager`、`SkillRuntime`、`HookManager`（含 `TracingHook`）、`MemoryManager`，然后构造 `AgentLoop` 并包装为 `AgentSession`
- `run_session()` (206-341): 并行运行两个 asyncio task——agent 执行 task + approval 接收 task，通过 Queue 汇聚到 WebSocket

**生命周期:**
1. 用户打开网页 → WebSocket 连接 → `create_session_async(llm)` 创建 `AgentSession`
2. 用户发消息 → `run_session()` 启动 AgentLoop，事件通过 Queue + WebSocket 推送前端
3. 用户点 reset → `remove_session()` + `fail_pending()` → 重新 `create_session_async()`
4. WebSocket 断开 → `WebSocketDisconnect` 异常捕获 (server.py:387)


### 5. DebugHook -- 扩展 Hook 协议，捕获完整迭代状态

**Hook 协议定义:** `agent/hooks/manager.py:14-22`，7 个 lifecycle hook：

```python
@runtime_checkable
class Hook(Protocol):
    async def on_run_started(self, run_config): ...
    async def before_iteration(self, iteration, messages): ...
    async def after_llm_call(self, response): ...
    async def before_tool_execute(self, tool_call): ...
    async def after_tool_execute(self, tool_call, result): ...
    async def on_error(self, error): ...
    async def on_completion(self, result): ...
```

**DebugHook** (`web/debug_hook.py:17-78`) 实现全部 7 个 hook，每个 hook 调用 `_send(phase, data)` 发出结构化事件：

| Hook 方法 | phase | 捕获数据 |
|---|---|---|
| `before_iteration` | `before_iteration` | messages (脱敏后)、message_count |
| `after_llm_call` | `after_llm_call` | content、stop_reason、tool_calls (参数经 `_redact_arguments` 脱敏) |
| `before_tool_execute` | `before_tool_execute` | tool_name、arguments |
| `after_tool_execute` | `after_tool_execute` | tool_name、arguments、result (extract_text 截断) |
| `on_error` | `on_error` | error_type、error_message |
| `on_completion` | `on_completion` | content、stop_reason、tool_calls_made、total_tokens |

**事件格式:** `{"type": "debug", "phase": "<phase>", "iteration": <int>, "data": {...}}`

**启用/挂载机制:**
- 环境变量 `ASTERWYND_DEBUG=1/true/enabled/yes/on` 启用 (debug_hook.py:13-14)
- 在 `run_session()` (session.py:221-231) 中，每次 run 动态创建新 `DebugHook` 实例并 append 到 `session.agent.hooks.hooks` 末尾
- run 结束后移除 (338-341 行)，避免跨 run 残留

**安全措施:**
- `_redact_arguments()` (80-85): 调用 `agent/approval.py` 的 `redact_value()` 脱敏敏感参数
- `_sanitize_message_dict()` (88-109): 将消息 dict 中的 `data:image/` URL 替换为 `[image data omitted]`


### 6. create_session vs create_session_async -- MCP 初始化的同步/异步分叉

与 CLI 的 `build_agent` / `build_agent_async` 完全对称 (agent/main.py:140-175)：

```python
# 同步版 (session.py:131-134)
def create_session(self, llm, tools=None) -> AgentSession:
    if self.config.mcp.servers:
        raise RuntimeError("create_session with MCP config requires create_session_async")
    return self._create_session(llm, tools=tools, mcp_manager=None)

# 异步版 (session.py:136-138)
async def create_session_async(self, llm, tools=None) -> AgentSession:
    mcp_manager = await build_mcp_manager(self.config)  # MCP 连接需要 asyncio
    return self._create_session(llm, tools=tools, mcp_manager=mcp_manager)
```

**设计动机:** MCP (Model Context Protocol) 客户端初始化是异步的——它需要建立与外部 MCP 服务器的连接。如果配置中没有 MCP server，同步版可以跳过这步直接构建。如果配置了 MCP 但错误调用了同步版，立即抛 `RuntimeError` 给出明确错误信息，而不是静默失败。

两者的核心构建逻辑收敛到同一个私有方法 `_create_session()` (session.py:140-191)，唯一的差异变量是 `mcp_manager` 参数（同步版传 `None`）。


### 架构全景总结

```
浏览器 WebSocket ──> /ws/{session_id}
                        │
              ┌─────────┴──────────┐
              │  WebSocket endpoint │ (server.py:123-388)
              │  - 消息路由         │
              │  - chat/approval/   │
              │    reset/set_mode   │
              └─────────┬──────────┘
                        │
         ┌──────────────┼──────────────┐
         │              │              │
    SessionManager  WebApprovalHandler DebugHook
    (session.py:116) (session.py:30)   (debug_hook.py:17)
         │              │              │
    AgentSession   asyncio.Future    Hook Protocol
    (session.py:92)  (桥接同步/异步)  (hooks/manager.py:14)
         │
    AgentLoop.run()
    (loop.py:428)
         │
    ┌────┴────┐
    │ LLM     │ stream_chat() → SSE → LLMStreamEvent
    │ Tools   │ execute()
    │ Hooks   │ before/after 钩子
    │ Memory  │ compact_if_needed()
    └─────────┘
         │
    on_event() → asyncio.Queue → ws.send_json() → 浏览器
```

## Version B -- 面试讲稿版

> Asterwynd 的 Web UI 架构核心是 **FastAPI + WebSocket 双通道**。REST 端点负责静态页面、slash command 目录和图片上传，WebSocket 则是实时交互的主干道——所有 agent 对话流、审批交互、模式切换都走 `/ws/{session_id}` 这一个 endpoint。
>
> 这里最值得讲的设计是 **WebApprovalHandler 的 asyncio.Future 桥接机制**。AgentLoop 在执行过程中碰到需要审批的工具调用时，会同步地 `await` 一个审批结果——它不能继续迭代，必须等用户决策。但 Web 用户是在浏览器的异步世界里，可能几秒甚至几分钟后才点"批准"。解决方案是：WebApprovalHandler 在 `request_approval` 里创建一个 `asyncio.Future`，存储为 `_pending`，然后 `await` 这个 future。AgentLoop 迭代就停在这里。同时，AgentLoop 通过 `on_event` 回调把审批请求推送到 WebSocket 前端。当用户在浏览器点批准，WebSocket 端点调用 `submit_response()`，它找到之前的 future 并 `set_result`，`request_approval` 的 `await` 立即解冻，AgentLoop 继续执行。这个设计只用一个 future 变量就解决了同步 AgentLoop 和异步 Web 之间的停顿/恢复问题。而且我们做了单审批约束——同一时间只允许一个 pending approval，避免状态混乱。
>
> 数据传输链路是三层管道。LLM Provider 的 `stream_chat` 方法是 async generator，把 HTTP SSE 的每个 chunk 封装成 `LLMStreamEvent` yield 出去。AgentLoop 的 `_call_llm` 消费这些事件，调用 `on_event` 回调把每个 `assistant_delta` 以及最终的 `llm_response`、`tool_call`、`tool_result` 等事件推送出去。Web 层的 `SessionManager.run_session` 把这个 `on_event` 实现为向 `asyncio.Queue` 放事件，主循环再逐条从 queue 取出发到 WebSocket。之所以不直接把 `ws.send_json` 当回调用，是因为 run_session 需要并行跑两个 asyncio task——一个跑 agent，一个轮询 WebSocket 接收端的 approval 响应。Queue 解耦了这两个方向。
>
> 每个浏览器标签页对应一个 AgentSession。AgentSession 是一个数据对象，持有独立的 AgentLoop 实例、专属的 WebApprovalHandler、消息历史和一个 debug 轮次计数器。SessionManager 管理内存 session 字典，提供 create_session 和 create_session_async 两个工厂方法——这个对称型和 CLI 的 build_agent / build_agent_async 一致：同步版在配置了 MCP server 时直接抛 RuntimeError，异步版先 `await build_mcp_manager` 初始化 MCP 连接。
>
> 调试能力通过 DebugHook 实现。它完整实现了 Hook 协议的 7 个生命周期方法：before_iteration 抓消息快照、after_llm_call 抓模型输出和工具调用（参数会做脱敏）、before/after_tool_execute 抓工具执行前后状态、on_error 抓异常、on_completion 抓最终结果。每个事件带 phase、iteration 和结构化 data，前端 Debug UI 可以回放整个迭代过程。DebugHook 在每次 run 时动态挂载、run 结束后立即移除，环境变量 `ASTERWYND_DEBUG=1` 控制开关。
>
> 总结一下，这个架构的核心思想是：用 asyncio.Future 做审批桥接、用 asyncio.Queue 做流翻译解耦、用 AgentSession 做会话隔离、用 Hook 协议做可插拔调试。


## 关键文件索引

| 文件 | 核心内容 |
|---|---|
| `web/server.py` | `create_app()` (L25-390), REST 端点 (L48-121), WebSocket `/ws/{session_id}` (L123-388) |
| `web/session.py` | `WebApprovalHandler` (L30-89), `AgentSession` (L92-113), `SessionManager` (L116-341), `run_session()` (L206-341) |
| `web/debug_hook.py` | `debug_enabled()` (L13-14), `DebugHook` (L17-78), `_redact_arguments()` (L80-85), `_sanitize_message_dict()` (L88-109) |
| `agent/loop.py` | `AgentLoop.__init__()` (L67-133), `run()` (L428-465), `_run()` (L467-824), `_call_llm()` (L826-870), approval flow (L667-737) |
| `agent/llm.py` | `LLM` Protocol (L20-28), `LLMStreamEvent` (L40-45), `BaseLLM` (L48-55) |
| `agent/openai_llm.py` | `stream_chat()` (L128-153), `_stream_chat_impl()` (L155-205) |
| `agent/approval.py` | `ApprovalHandler` Protocol (L82-84), `ApprovalRequest` (L35-68), `ApprovalResponse` (L71-79), `FailClosedApprovalHandler` (L87-93), `CliApprovalHandler` (L96-120), `build_approval_request()` (L123-149) |
| `agent/hooks/manager.py` | `Hook` Protocol (L14-22), `HookManager` (L24-56) |
| `agent/main.py` | `build_agent()` (L140-156), `build_agent_async()` (L159-175), `_build_agent_core()` (L191-258) |
| `agent/run_identity.py` | `new_session_id()` (L6-7), `new_run_id()` (L10-11) |


---
## Q12: 异步执行模式 -- SubAgent 派发、Background Task 管理与并行工具执行


## Version A -- 详细参考版

### 1. SubAgent 异步派发 (`agent/subagent/manager.py`)

SubAgentManager 管理子 Agent 的完整生命周期：创建 session、派发 run、等待结果、取消或查询状态。核心数据结构：

- `_sessions: dict[str, SubagentSessionRecord]` -- 按 subagent_id 索引的会话记录
- `_active_tasks: dict[str, asyncio.Task[None]]` -- 按 run_id 索引的活跃 asyncio Task 引用
- `_run_waiters: dict[str, asyncio.Event]` -- 按 run_id 索引的完成信号事件

#### 1.1 `run_subagent()` 的 wait=True/False 机制 (L162-194)

```python
async def run_subagent(self, *, subagent_id, task, wait=False, timeout_s=None):
    session = self._require_session(subagent_id)
    # 单 run 限制：同一 session 不允许并发 run
    if session.active_run_id is not None:
        raise RuntimeError(f"subagent {subagent_id} already has an active run")

    run = SubagentRunRecord(run_id=run_id, task=task, status="running", started_at=time.time())
    waiter = asyncio.Event()
    self._run_waiters[run_id] = waiter

    bg_task = asyncio.create_task(self._execute_run(session, run))  # 派发
    self._active_tasks[run_id] = bg_task
    bg_task.add_done_callback(lambda _: self._active_tasks.pop(run_id, None))

    if wait:
        await asyncio.wait_for(waiter.wait(), timeout=timeout_s)  # 阻塞当前协程
    return self._format_run_envelope(session.subagent_id, run)
```

关键行为：
- `wait=False`（默认）：立即返回 run envelope（含 run_id, status="running"），调用方可后续通过 `get_subagent_run(wait=True)` 或轮询获取结果
- `wait=True`：在 `waiter.wait()` 上阻塞，可设超时；超时不会取消任务（任务仍然在后台运行）
- `add_done_callback` 保证 Task 完成后自动从 `_active_tasks` 清除，防止内存泄漏

#### 1.2 `_execute_run()` 内部循环 (L271-296)

```python
async def _execute_run(self, session, run):
    trace = TraceRecorder(task_id=session.subagent_id)
    try:
        loop = self._build_subagent_loop(session.mode)  # 构建独立 AgentLoop
        result = await loop.run(session.messages, trace_recorder=trace, ...)
        self._complete_run(session, run, result, trace)
    except asyncio.CancelledError:
        self._mark_cancelled(session, run, trace)
        raise
    except Exception as exc:
        self._mark_failed(session, run, str(exc), trace)
    finally:
        waiter = self._run_waiters.pop(run.run_id, None)
        if waiter is not None:
            waiter.set()  # 无论成功/失败/取消，都通知等待者
```

关键设计：
- 每个 subagent run 构建**独立的 AgentLoop 实例**（`_build_subagent_loop`, L298-324），拥有自己的 ToolRegistry、HookManager、MemoryManager，模式受 `_clamp_mode()` 约束，不会超越父 Agent 权限
- `waiter.set()` 在 `finally` 块中执行，**保证一定触发**，即使任务被取消或异常终止
- `CancelledError` 被捕获后仍 `raise`，让 `cancel_subagent_run()` 中的 `await task` 能正常感知取消

#### 1.3 结果获取方式

| 方式 | 方法 | 说明 |
|------|------|------|
| 同步等待 | `run_subagent(wait=True)` | 在 waiter Event 上阻塞 |
| 异步轮询 | `get_subagent_run(run_id=...)` | 返回当前 run 状态，不阻塞 |
| 延迟等待 | `get_subagent_run(wait=True)` | 对 running 状态的 run 等待其完成 |
| 取消 | `cancel_subagent_run()` | `task.cancel()` + await task + mark_cancelled + waiter.set() |
| 查看消息 | `inspect_transcript(scope="summary"/"recent_messages")` | 读取 subagent 的消息历史和摘要 |

#### 1.4 SubAgent 与父 Agent 的隔离

`_build_subagent_loop()` (L298-324) 为每个 subagent 创建隔离的运行环境：
- **LLM 共享**：复用父 Agent 的 LLM 实例（`llm=self.llm`）
- **ToolRegistry 独立构建**：根据 mode 和 config 创建新的 tool set
- **模式钳制** (`_clamp_mode`, L401-411)：subagent 的 mode 不能超越父 agent（READ_ONLY < BUILD < BYPASS），防止权限提升
- **subagent_manager 传递**：`subagent_manager=self` -- 理论上 subagent 也能创建 sub-subagent（但受 `_clamp_mode` 限制）


### 2. BackgroundTaskManager 轮询 (`agent/background.py`)

BackgroundTaskManager 管理 OS 级别的后台进程（如长时间编译、测试套件），通过 Bash 工具的 `run_in_background=True` 参数启动。

#### 2.1 启动流程 (`start()`, L43-61)

```python
async def start(self, cmd, tool_call_id, cwd, timeout=None):
    task_id = self._new_task_id()  # "bg_0001", "bg_0002" ...
    handle = await self._sandbox.run_background(cmd, cwd=cwd)  # 子进程
    entry = _TaskEntry(handle=handle, tool_call_id=tool_call_id, command=cmd, ...)
    entry._monitor_task = asyncio.create_task(self._monitor(task_id, entry))
    self._tasks[task_id] = entry
    return task_id
```

Sandbox 层 (`agent/tools/sandbox.py` L172-184)：
```python
async def run_background(self, command, cwd=None):
    process = await asyncio.create_subprocess_shell(
        command, cwd=str(cwd), stdout=PIPE, stderr=STDOUT,
        preexec_fn=os.setsid,  # 创建新进程组，便于组杀
    )
    return _SubprocessHandle(process)
```

关键点：`preexec_fn=os.setsid` 创建新 session/进程组，后续 `terminate()` 和 `kill()` 通过 `os.killpg(pgid, signal)` 对整个进程组操作（`sandbox.py` L60-71），确保子孙进程一并被终止。

#### 2.2 并发输出 drain (`_monitor()` + `_drain_output()`, L113-164)

```python
async def _monitor(self, task_id, entry):
    drain_task = asyncio.create_task(self._drain_output(entry))  # 并发 drain

    try:
        if entry.timeout is not None:
            await asyncio.wait_for(entry.handle.wait(), timeout=entry.timeout)
        else:
            await entry.handle.wait()
    except asyncio.TimeoutError:
        entry.status = "timeout"
        await entry.handle.kill()
        await entry.handle.wait()
    ...

    # 进程结束后，等待 drain 完成
    if drain_task:
        await drain_task

    # 读取最终 exit code
    entry.exit_code = await entry.handle.poll()
    entry.status = "completed" if entry.exit_code == 0 else "failed"
```

`_drain_output()` (L153-164) 以 4096 字节为单位循环读取 stdout，累计最多 `MAX_OUTPUT_BYTES` (64KB)，超出部分丢弃并标记 `output_truncated=True`。

这是一个 `wait` + `drain` 的并发模型：进程运行时 drain 在后台持续读取 stdout 防止管道堵塞，进程退出后 drain 读完剩余数据再读取 exit code。

#### 2.3 轮询注入 (`check_completed()`) 与 AgentLoop 集成

`check_completed()` (L63-69) 在**每次 AgentLoop 迭代开始时**被调用（`agent/loop.py` L530-542）：

```python
# agent/loop.py L530-542
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
        messages.append(Message(role="user", content=observation))
```

`check_completed()` 遍历所有 task，将 `status != "running"` 且 `reported == False` 的 task 标记为 `reported=True` 并返回。返回的结果作为**用户消息**注入到对话中，LLM 在下一轮推理中即能感知到后台任务完成。

#### 2.4 两阶段终止 (`stop()`, L79-96)

```python
async def stop(self, task_id):
    await entry.handle.terminate()   # Phase 1: SIGTERM (进程组)
    try:
        await asyncio.wait_for(entry.handle.wait(), timeout=3.0)
    except asyncio.TimeoutError:
        await entry.handle.kill()    # Phase 2: SIGKILL (进程组)
        try:
            await asyncio.wait_for(entry.handle.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass                      # 放弃（标记为 killed）
    entry.status = "killed"
```

两阶段给予进程优雅退出的机会，3s+2s 的超时设计防止僵尸进程。

#### 2.5 ContextVar 传播：`current_tool_call_id`

```python
# agent/background.py L10
current_tool_call_id: ContextVar[str] = ContextVar("current_tool_call_id", default="")
```

传播链路：
1. `AgentLoop._execute_single_tool()` (L896): `current_tool_call_id.set(tool_call.id)`
2. `BashTool._execute_background()` (`agent/tools/builtin/bash.py` L81): `tc_id = current_tool_call_id.get()`
3. `AgentLoop._run_in_background()` (L400-406): 将 `tool_call_id` 传给 `background_manager.start()`
4. `BackgroundTaskManager._task_to_dict()` (L170-179): 在结果字典中携带 `tool_call_id`

这使得 LLM 在后续迭代中收到 `[Background task bg_0001 completed]` 消息时，能通过 `tool_call_id` 关联到最初发起该任务的那个 Bash 工具调用。

#### 2.6 cleanup 路径

`AgentLoop.run()` 的 `finally` 块 (L457-458) 调用 `self.background_manager.cleanup()`，对残留 running 进程执行同步 `force_kill_sync`（SIGTERM → 0.5s → SIGKILL），属于紧急清理路径，不依赖 event loop。


### 3. 并行工具执行 (`agent/loop.py` `_execute_tool_calls()`)

#### 3.1 分组逻辑 (L922-952)

```python
async def _execute_tool_calls(self, items):
    groups: list[list[dict]] = []
    current_group: list[dict] = []
    for item in items:
        tool = item.get("tool")
        decision = item.get("decision")
        pre_denied = item.get("pre_denied_result")
        requires_approval = decision is not None and decision.requires_approval
        is_parallel = (
            tool is not None
            and tool.parallelizable        # Tool 类属性，默认 False
            and not pre_denied             # 未因审批被拒绝
            and not requires_approval      # 不需要审批
        )
        if is_parallel:
            current_group.append(item)
        else:
            if current_group:
                groups.append(current_group)
                current_group = []
            groups.append([item])
    if current_group:
        groups.append(current_group)
```

分组规则：
- **连续的** `parallelizable` 工具聚合成一个并行组
- 非并行工具、审批拒绝、需要审批的工具各占一个单独的串行组
- 确认了并行安全性的只读/无副作用工具：Read、Grep、Glob/Find、CodeIntelligence（`codebase_search`/`grep_search`）、InspectGitDiff

#### 3.2 并行执行 (L956-997)

```python
for group in groups:
    if len(group) > 1:
        # 并行组
        group_results = await asyncio.gather(
            *[_run_one(item) for item in group],
            return_exceptions=True,
        )
        # Exception 解包：
        for i, r in enumerate(group_results):
            if isinstance(r, Exception):
                group_results[i] = {**group[i], "result": f"[Error: {r}]", "duration_ms": 0.0}
        results.extend(group_results)
    else:
        # 串行组
        item = group[0]
        if pre_denied := item.get("pre_denied_result"):
            results.append({**item, "result": pre_denied, "duration_ms": 0.0})
        else:
            result, duration_ms = await self._execute_single_tool(...)
            results.append({**item, "result": result, "duration_ms": duration_ms})
```

关键设计：
- `return_exceptions=True`：组内某个工具失败不会影响同组其他工具的执行
- 异常解包后统一转为 `"[Error: ...]"` 字符串，保持结果格式一致
- 结果集 `results` 按**原始顺序**组装（先并行组、后串行组，同组内按出现顺序），Phase 3 后处理（L743-803）按此顺序追加 `tool_result_message`，保证 LLM 看到一致的工具结果序列


### 4. 三维对比表

| 维度 | SubAgent 派发 | BackgroundTask 管理 | 并行工具执行 |
|------|-------------|-------------------|------------|
| **生命周期** | `create_subagent` → `run_subagent` (spawn Task) → `_execute_run` loop → `_complete_run` → `waiter.set()` | `Bash(run_in_background=True)` → `start` (spawn 子进程 + monitor Task) → `_monitor` wait/drain → `check_completed` → `reported=True` | LLM 返回 N 个 `tool_calls` → 按 `parallelizable` 分组 → `asyncio.gather` → 结果收集 |
| **结果投递** | 1) Event 阻塞等待 (waiter.wait) 2) 轮询 `get_subagent_run()` 3) `inspect_transcript` 查看消息历史 | `check_completed()` 在每轮迭代开始时轮询，结果以 `[Background task ... completed]` 格式注入为 user message | 同一次迭代内同步返回，`tool_result_message` 按原始顺序追加到消息列表 |
| **错误处理** | `CancelledError` → mark_cancelled; `Exception` → mark_failed; `waiter.set()` 始终在 finally 中执行 | `TimeoutError` → status=timeout + kill; 异常 → status=orphaned; 两阶段 kill (SIGTERM 3s → SIGKILL 2s) | `return_exceptions=True` 捕获 gather 中异常 → 转为 `"[Error: ...]"` 字符串；单个串行工具的异常由 `_retry.execute_with_retry` 兜底 |
| **LLM 可见性** | 通过工具接口间接可见：`GetSubagentRun` 返回状态/摘要，`InspectSubagentTranscript` 返回消息片段 | **自动注入**：下一轮迭代开始时，完成的后台任务作为 user role message 直接追加到对话 | **即时可见**：工具结果在当前迭代中追加为 `tool_result_message`，LLM 下一次 `_call_llm` 即看到 |
| **取消机制** | `cancel_subagent_run()` → `task.cancel()` + await + `waiter.set()` | `stop(task_id)` → `terminate()` → wait 3s → `kill()` → wait 2s；`cleanup()` 兜底 `force_kill_sync` | 无独立取消机制；同组内某一工具异常不影响其他工具（`return_exceptions=True`） |
| **隔离级别** | 完全隔离：独立 AgentLoop + 独立 ToolRegistry + 独立 MemoryManager | 进程级隔离：独立子进程 + 独立进程组 (setsid) | 无隔离：同一 event loop 内的并发协程 |
| **并发模型** | `asyncio.create_task` 派发独立协程，无并发限制（但同一 session 同一时间只能有一个 run） | `asyncio.create_task` 派发 monitor 协程，并发 drain (wait + drain_output)，无显式并发限制 | `asyncio.gather` 批量并发执行同组工具，受 event loop 并发能力限制 |
| **关键文件/行号** | `agent/subagent/manager.py` L92-417 | `agent/background.py` L1-179; `agent/tools/sandbox.py` L14-87 (BackgroundProcessHandle ABC + _SubprocessHandle) | `agent/loop.py` L890-997 (`_execute_single_tool` + `_execute_tool_calls`); `agent/tools/base.py` L44 (`parallelizable` flag) |


## Version B -- 面试讲稿版

> Asterwynd 的异步执行有三个层次，分别解决不同的并发需求。
>
> 第一层是 **SubAgent 异步派发**。当一个 Agent 需要把子任务委托给另一个 Agent 时，它通过 `SubAgentManager.run_subagent()` 派发一个独立的 AgentLoop。这个 API 支持 `wait=True/False` 两种模式：`wait=False` 时立即返回，后台通过 `asyncio.create_task` 启动 `_execute_run` 协程；`wait=True` 时在 `asyncio.Event` 上阻塞等待。无论哪种模式，`_execute_run` 的 finally 块一定会调用 `waiter.set()`，确保等待者不会永久挂起。SubAgent 拥有完全隔离的运行环境——独立的 ToolRegistry、MemoryManager、HookManager，但 LLM 实例是共享的，模式也受父 Agent 的 `_clamp_mode()` 钳制，无法越权。
>
> 第二层是 **BackgroundTaskManager**，它管理的是 OS 级别的后台进程，比如长时间的编译或测试。Agent 通过 Bash 工具的 `run_in_background=True` 参数启动，Sandbox 层用 `preexec_fn=os.setsid` 创建新进程组。启动后 `_monitor` 和 `_drain_output` 并发运行——monitor 等待进程退出，drain 持续读取 stdout 防止管道阻塞。输出限制在 64KB，超出截断。结果不立即返回，而是在**每轮迭代开始时**由 AgentLoop 调用 `check_completed()` 轮询，已完成的任务以 user message 形式注入对话，LLM 下一轮推理就能感知到。这里有个精巧的 ContextVar 设计：`current_tool_call_id` 在 `_execute_single_tool` 中被设置，Bash 工具读取它传给后台管理器，这样结果能关联到原始的工具调用。停止时采用两阶段终止：SIGTERM 等 3 秒，没死再 SIGKILL 等 2 秒。
>
> 第三层是**并行工具执行**。LLM 一次推理可能返回多个 tool call，AgentLoop 的 `_execute_tool_calls` 根据工具的 `parallelizable` 标志进行分组。连续的只读并行工具——比如同时读三个文件、做两次 Grep——会被聚合成一组，用 `asyncio.gather` 并发执行。任何需要审批的工具、被审批拒绝的工具、或者写操作工具，会被隔离在单独的串行组中。`return_exceptions=True` 保证组内某个工具失败不影响其他工具，异常统一转为 Error 字符串。结果按原始顺序追加为 tool_result_message，LLM 看到的工具输出序列和它发出的 tool call 顺序一致。
>
> 总结一下这三种模式的本质区别：SubAgent 是**协程级隔离**，BackgroundTask 是**进程级隔离**，并行工具执行是**无隔离的 intra-iteration 并发**。结果投递方式也不同：SubAgent 是主动查询或事件等待，BackgroundTask 是被动注入对话，并行工具是即时同步返回。这三种模式在 Asterwynd 中协同一工作，让 Agent 既能并行处理独立的读操作，又能异步启动长任务后继续推理，还能把复杂子问题委托给专门的 SubAgent 去解决。


---
## Q13: 错误处理与韧性设计 -- LLM 故障、工具异常与优雅降级

## Version A -- 详细参考版

### 1. 工具层重试：RetryHook 指数退避

`agent/hooks/builtin/retry.py` 实现了独立的 `RetryHook`，不依赖 HookManager 回调链，而是由 AgentLoop 在 `_execute_single_tool` 中直接显式调用 `_retry.execute_with_retry()`。

**可重试错误判定 (line 17-20)**

```python
RETRYABLE_PATTERN = re.compile(
    r"timeout|timed out|connection|rate limit|429|503|temporary",
    re.IGNORECASE,
)
```

`_is_retryable()` 使用正则匹配异常消息字符串，覆盖超时、连接故障、限流（429）、服务不可用（503）、临时错误五类场景。匹配不区分大小写。

**指数退避重试逻辑 (line 34-55)**

`execute_with_retry()` 接收 `max_retries=3` 和 `base_delay=1.0`：

- 最多执行 `max_retries + 1 = 4` 次尝试（含首次）。循环 `range(self.max_retries + 1)` 即 0..3。
- 每次失败后判断是否可重试：若 `_is_retryable(error_msg)` 为 False，**立即返回** `[Error: ...]` 格式不重试。
- 可重试且未达上限时：`delay = self.base_delay * (2 ** attempt)`，即 1s/2s/4s，第 4 次不重试直接返回。
- 所有重试耗尽后返回：`[Error after 4 attempts: <last_error>]`

**Bash 工具例外 (agent/loop.py:898-906)**

在 `AgentLoop._execute_single_tool()` 中，Bash 工具**完全绕过 RetryHook**：

```python
if tool_call.name == "Bash":
    try:
        result = await self.tool_registry.execute(tool_call, ...)
    except Exception as e:
        result = f"[Error: {e}]"
else:
    result = await self._retry.execute_with_retry(tool_call, execute_fn=...)
```

原因：Bash 命令可能产生不可逆副作用（如 `rm -rf`、`git push`），重试会导致重复执行，造成数据损坏。Bash 失败立即返回 `[Error: ...]`。

### 2. 工具执行错误约定：`[Error: ...]` 前缀

整个系统使用统一的错误前缀约定，让 LLM 能识别这是错误而非工具正常输出。

**错误来源汇总：**

| 错误来源 | 文件位置 | 格式 |
|---------|---------|------|
| RetryHook 不可重试 | `retry.py:46` | `[Error: <msg>]` |
| RetryHook 重试耗尽 | `retry.py:55` | `[Error after N attempts: <msg>]` |
| Bash 异常 | `loop.py:906` | `[Error: <msg>]` |
| JSON 解析失败 | `loop.py:614` | `[Error: <msg>]` |
| 未知工具 | `loop.py:662` | `[Error: unknown tool '<name>']` |
| 审批被拒 | `loop.py:717-727` | `[Approval denied: ...]` / `[Approval unavailable: ...]` |
| asyncio.gather 异常 | `loop.py:981` | `[Error: <exception>]` |
| MCP 工具异常 | `mcp/manager.py:195` | `[MCP tool error: <server>/<tool>: <exc>]` |
| MCP isError 结果 | `mcp/manager.py:304` | `[MCP tool error: <content>]` |

**追踪器错误判定 (loop.py:757-761)**：`trace_recorder.record_tool_result()` 通过检查结果是否以 `[Error` 或 `[Permission denied` 开头来决定 status 字段为 `"error"` 还是 `"ok"`。

### 3. MCP 服务器故障容忍

`agent/mcp/manager.py` 的 `connect_from_config()` (line 65-91) 实现分服务器错误处理：

**connect_from_config 流程：**

1. 遍历 `config.mcp.servers` 中的每个服务器配置
2. 若 `server_config.enabled == False`：记录状态为 `ready=False, error="disabled"`，跳过
3. 若启用：`asyncio.timeout(server_config.startup_timeout_seconds)` 包裹连接逻辑
4. 单个服务器连接失败被 `except Exception` 捕获：
   - 记录 `McpServerStatus(ready=False, error=<message>)`
   - 检查 `server_config.required`（`agent/config.py:116`，默认 `False`）
   - **required=True**：调用 `await self.aclose()` 清理已连接的服务器，然后 `raise RuntimeError(...)` 终止启动
   - **required=False**：仅记录错误，继续连接后续服务器

**工具列表获取容错 (line 241-252)**：`_list_or_empty()` 在 `list_tools/list_prompts/list_resources` 失败时静默返回空列表，保证服务器不会因部分能力不可用而导致注册中断。

**工具调用超时 (line 181-196)**：`call_tool()` 使用 `asyncio.wait_for(timeout=server_config.tool_timeout_seconds, default=30)` 包装 MCP 调用，超时或异常返回 `[MCP tool error: ...]` 错误字符串。

### 4. ContextBuilder 预算超支优雅降级

`agent/context/builder.py` 的 `_apply_budget()` (line 85-119) 实现了分层优先级的截断策略：

**截断算法：**

1. 已按优先级排序的 layers，从尾部（最低优先级）向前扫描
2. `_find_trimmable_index()` (line 122-128)：从末尾遍历，找到第一个 `critical=False` 的层
3. 若无非关键层可剪裁（只剩 P0/P1），停止截断，完整保留关键层
4. `_truncate_tail()` (line 131-142)：从文本**尾部**移除约 `excess_tokens * 4` 个字符（`_CHARS_PER_TOKEN_ESTIMATE = 4`）
5. 若截断后内容为空，该层被完全移除
6. 余下层之间用 `\n\n---\n\n` 连接

**优先级分层** (`agent/context/sources.py`)：

| 优先级 | 来源 | critical | 含义 |
|--------|------|----------|------|
| P0 | SystemPromptSource | True | 系统提示词，永不被截断 |
| P1 | AsterMdSource | True | AGENTS.md 项目指令，永不被截断 |
| P2 | MemoryIndexSource | False | 持久记忆索引，可剪裁 |
| P4 | SkillIndexSource / SkillActiveSource | False | 技能索引/活跃技能 |
| P5 | PlanModeSource / PlanningStateSource / TodoSource | False | 计划状态/待办 |

**单源渲染失败处理 (line 62-70)**：若某个 `ContextSource.render()` 抛出异常，记录 warning 并跳过该源，不影响其他源的组装完成。

### 5. SessionSnapshot 崩溃恢复

`agent/session.py` 的 `SessionStore` + `AgentLoop.run()` 的 `finally` 块协同实现：

**持久化触发 (loop.py:456-465)**

```python
finally:
    if self.background_manager is not None:
        self.background_manager.cleanup()
    if self.session_store is not None and session_id:
        try:
            self._save_session(messages, session_id, resolved_run_id, resume_snapshot)
        except Exception:
            logger.warning("Failed to save session", exc_info=True)
```

关键设计：session 保存本身包装在 try/except 中，保存失败只记录 warning，不会掩盖原始异常或中断 finally 清理流程。

**原子写入 (session.py:187-202)**：先写入 `.tmp` 临时文件，再 `os.replace()` 原子替换。崩溃不会产生损坏的半写文件。

**去重保存 (session.py:70-85)**：计算 snapshot + messages 的 SHA256 去重哈希，内容无变更时跳过写入。

**Schema 版本兼容 (session.py:108-116)**：加载时比较 `schema_version` 主版本号。主版本不匹配时发出 warning 并返回 None，拒绝恢复不兼容的会话。

**Runtime fingerprint 对比 (session.py:225-236)**：比较 cwd、model、provider、agent_version 四个维度；不匹配时发出 RuntimeWarning 但**不阻止恢复**，仅提示"当前运行时与保存时不同，行为可能不符合预期"。

**恢复行为 (loop.py:479-498)**：
- 恢复 mode、execution_todos、active_skills、user_system_prompt
- **iteration 重置为 0** (`start_iteration = 0`)：恢复后的计数重新开始
- 注入 `[Session resumed. Continuing from where we left off.]` 标记消息
- 保留 system 消息和对话历史，追加新用户输入

### 6. LLM 调用失败处理

**HTTP 层 (agent/llm.py:75-87)**：

`BaseLLM._get_client()` 创建 `httpx.AsyncClient`，timeout 配置为 connect=60s / read=60s(流式) or 180s(非流式)。大模型推理可能耗时较长，非流式请求给予 3 分钟读取超时。

**Provider 错误传播 (anthropic_llm.py + openai_llm.py)**：

两个 provider 在 HTTP 层面均使用 `response.raise_for_status()`，对于 >=400 状态码会抛出 `httpx.HTTPStatusError`。错误前会记录完整的 sanitized payload（图片 base64 替换为占位符）和 error body 到日志。

**视觉模型降级重试 (anthropic_llm.py:41-73, openai_llm.py:29-126)**：

当 `vision_mode(model) == "try_vision"` 且消息包含图片时：
1. 首先尝试携带图片发送请求
2. 若收到 400 错误（`_is_400_error`），判断为模型不支持图片
3. 自动重试，将 ImageBlock 降级为 `[image: <filename>]` 文本引用
4. 非 400 错误直接向上传播

**流式错误处理 (anthropic_llm.py:236-237)**：SSE 事件流中遇到 `event_type == "error"` 时 raise `RuntimeError`。

**Loop 层无额外重试 (loop.py:548)**：`_call_llm()` 调用不做 try/except 包装。如果 LLM 抛出异常，沿 `_call_llm -> _run -> run` 传播。`run()` 的 finally 块确保 (a) background_manager.cleanup() 和 (b) session 保存无论如何都会执行。

**max_tokens 截断处理 (loop.py:578-583)**：当 `stop_reason == "max_tokens"` 时，不视为错误终止，而是追加 assistant 消息 + `"Please continue from where you left off."` 提示并继续下一轮迭代。

**max_iterations 上限 (loop.py:811-824)**：当 `_iteration >= self.max_iterations`（默认 20），循环退出，返回 `StopReason.MAX_ITERATIONS`，取最后一条 assistant 消息内容作为最终输出。不会无限循环耗尽资源。


## Version B -- 面试讲稿版

> 问：Asterwynd 的"错误处理与韧性设计"，你是如何系统性地应对 LLM 故障、工具异常和资源异常的？
>
> 答：我们从六个层面构建了完整的韧性体系。
>
> 第一个是工具层的指数退避重试。我们有一个独立的 RetryHook，通过正则匹配超时、限流 429、503 等可重试错误来做退避。首次间隔 1 秒，翻倍到 2 秒、4 秒，最多做 3 次重试加首次执行共 4 次尝试。不可重试的错误直接返回 `[Error: ...]` 格式。关键在于 Bash 工具完全跳过 RetryHook，因为 Bash 可能有不可逆副作用，比如文件删除或 git push，重试会导致重复操作。
>
> 第二个是整个系统的 `[Error: ...]` 前缀约定。无论是工具执行失败、JSON 解析错误、未知工具、审批被拒，还是 MCP 工具超时，统一用这个前缀返回给 LLM。LLM 看到这个词缀就知道这是错误而不是正常结果，可以尝试自修复，比如换个参数重试或者用别的工具替代。
>
> 第三个是 MCP 服务器的故障容忍。每个 MCP 服务器配置有一个 required 标记，默认是 false。非关键服务器启动失败了只记录日志和状态，整个 agent 继续启动。但如果 required 设为 true，比如一个必需的数据库查询 MCP，启动失败会直接 raise RuntimeError 终止进程。工具发现阶段也是，list_tools 调用失败就返回空列表，不会中断注册流程。
>
> 第四个是上下文构建器的优雅降级。我们有 0 到 5 共六个优先级的上下文层，P0 是系统提示词，P1 是 AGENTS.md 项目指令，这两层标记为 critical 永不被截断。当注入预算超支时，从最低优先级的层尾部向前裁剪，比如先从 P5 的待办列表尾部裁，不够再裁 P4 的技能索引，依此类推。单个源渲染失败也只会打 warning 并跳过，不影响其它层。
>
> 第五个是会话快照的崩溃恢复。AgentLoop.run 方法用 finally 块保证无论是否崩溃都会保存会话。保存采用先写临时文件再原子替换的方式，不会产生半写损坏文件。加载时会做 schema 版本兼容检查，主版本不匹配就拒绝恢复。还会对比 runtime fingerprint 发现运行时环境变化，只发警告不阻止恢复。恢复时会把 iteration 计数重置为 0，注入一条恢复提示消息，保留对话历史和系统消息。
>
> 第六个是 LLM 调用的容错。HTTP 层面，非流式请求读写超时拉到 180 秒防止大模型推理慢导致超时。遇到 400 且是视觉模型探测模式时，自动把图片降级为文本引用重试一次。流式 SSE 遇到 error 事件直接 RuntimeError，非 400 错误向上传播。Loop 层不做额外重试，但做了两个保护：一是响应被 max_tokens 截断时自动追加续接提示进入下一轮，二是 20 轮迭代上限防止死循环，超限返回已生成内容而不是崩溃。


## Source File Index

| 组件 | 文件 | 关键行号 |
|------|------|---------|
| RetryHook | `agent/hooks/builtin/retry.py` | 17-55 |
| Bash 重试例外 | `agent/loop.py` | 898-906 |
| Error 前缀约定 | `agent/loop.py` | 608-665, 758-762, 890-920 |
| 并发异常处理 | `agent/loop.py` | 972-984 |
| MCP 故障容忍 | `agent/mcp/manager.py` | 65-91, 181-196, 241-252 |
| McpServerConfig.required | `agent/config.py` | 112-129 |
| ContextBuilder 截断 | `agent/context/builder.py` | 85-152 |
| ContextSource critical | `agent/context/sources.py` | 107-109, 263-265 |
| ContextSource priorities | `agent/context/sources.py` | 107, 263, 280, 306, 322, 338, 360, 376 |
| SessionStore save/load | `agent/session.py` | 70-123 |
| Schema 兼容检查 | `agent/session.py` | 204-210 |
| Fingerprint 对比 | `agent/session.py` | 225-236 |
| finally 块崩溃保存 | `agent/loop.py` | 456-465 |
| Session 恢复/iteration 重置 | `agent/loop.py` | 479-498 |
| BaseLLM 超时配置 | `agent/llm.py` | 75-87 |
| Anthropic 图片降级重试 | `agent/anthropic_llm.py` | 41-73 |
| OpenAI 图片降级重试 | `agent/openai_llm.py` | 29-73, 88-126 |
| SSE error 事件 | `agent/anthropic_llm.py` | 236-237 |
| max_tokens 截断续接 | `agent/loop.py` | 578-583 |
| max_iterations 上限 | `agent/loop.py` | 527, 811-824 |
| _stream_events 错误 | `agent/llm.py` | 89-105 |


---
