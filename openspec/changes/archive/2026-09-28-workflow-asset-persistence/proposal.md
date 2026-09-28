# Proposal: Workflow 资产化：跑过的图沉淀为工作区可复用模板（workflow-asset-persistence）

关联跟踪 issue：[#245](https://github.com/Xingkai98/asterwynd/issues/245)。前置关系：本 change 是 #246（内置模板归一）的前置。依赖：无（前序 C1–C5 与 `workflow-graph-visualization` 均已合入归档）。

## Change Type

- primary: feature
- secondary:
  - subagent
  - workspace-safety

## Why

`workflow-dsl-scheduler`（已归档 2026-09-14）之后，模型已经可以自由声明 workflow DAG；`workflow-result-aggregation` / `workflow-budget-attribution` / `benchmark-workflow-replay` 又补齐了结果落盘、预算归因与 spec 可哈希。但**跑过的图是一次性的**：

- `workflow_id` 是随机串 `wf_<uuid8>`（`agent/subagent/scheduler.py:451`），per-run 结果落在 `.asterwynd/workflows/<workflow_id>/`（`agent/subagent/workflow_store.py:56-60`），**跨会话不可寻址、不可复用**。
- `SubAgentManager._workflows` 是 **per-manager 的内存注册表**——`GetWorkflow` 对未知 id 的返回体自己就写着 "the registry is per-manager and in-memory"（`agent/tools/builtin/subagents.py:504-513`）。新会话里那张图彻底不存在。
- 结果是：**模型每次都要重新生成整张 spec**。一张 6 节点的 orchestrator-worker 图，模型要重新输出完整 `nodes[]`/`edges[]`/`reduce` 声明，token 花在复述拓扑而不是解决问题上，而且每次重写都可能写坏（漏 reducer、写错环的可启动性——后者正是 `workflow-cycle-contract` 要治的病）。

已有地基不需要从零造：`WorkflowSpec.to_dict()` + `parse_workflow_spec` 的 round-trip 已被测试钉死（`tests/agent/subagent/test_pattern_templates.py:114-118`）；C5 的 `workflow_record.json` 已在用这套格式做「从磁盘读 spec 再跑」（`benchmarks/workflow_replay.py`、`benchmarks/runner.py:343-360`）；`agent/memory/persistent.py` 提供了跨会话资产的成熟形态（slug 命名 + 索引 + 写入纪律 + 版本可回溯）。

**为什么是现在**：C1–C5 把「模型能自由编排」做成了产品能力，但缺一个**复用面**——每次从零生成拓扑是这条链路上最后一块昂贵且易错的重复劳动。同时 #246（内置模板归一）要以本 change 的资产层为地基，先做本 change 可以让 #246 落在稳定的寻址与加载契约上。

## What Changes

- **新增可寻址的 workflow 资产层**：`~/.asterwynd/projects/<repo-hash>/workflow-assets/<slug>.json` + `index.json`（落点由 Q1 拍板为**仓库级**，跨 worktree 共享；`<repo-hash>` 经 git common dir 解析，与 memory 同作用域规则）。资产是**跨会话可寻址**的命名单元，取代「只有随机 `wf_<uuid8>`」的现状。
- **新增 4 个模型面工具**（拟定名，实现阶段可微调）：
  - `SaveWorkflowAsset`：把**刚跑过的图**存成命名资产（输入 `workflow_id` + `name`/`description`，spec 由服务端取出，**不穿过模型输出**）。
  - `ListWorkflowAssets`：有界列出可用资产（name/description/kind/参数面摘要）。
  - `GetWorkflowAsset`：读单个资产的正文（含 spec 或配方）。
  - `RunWorkflowAsset`：**按名调用**资产并驱动调度器——这是「无需模型重新生成拓扑」的落点。该工具语义上等价于一次性拉起整张图，必须进 `SPAWN_TOOL_NAMES` 深度闸。
- **资产两种载体**（关键设计点，见 design.md D1）：
  - **pattern 配方**（来自 `RunPattern`）：存 `{pattern, params, goal}`，参数化天然保留，加载时重新 `compile_pattern`。
  - **DSL spec**（来自 `DeclareWorkflow`/`RunWorkflow`）：输入**本来就是展开后的 spec**，不存在可还原的「配方」，存 spec 原文 + 可选**显式声明的覆盖面**。
- **加载路径的信任边界**（关键设计点，见 design.md D3）：从磁盘读回的是**跨会话、可能被其他工具或人改过**的输入。现状 `parse_workflow_spec` 的 `_positive_int` 只校验正整数、**无上界**（`agent/subagent/workflow.py:451-454`），且 `_resolve_limits` 对 spec 自声明的值**照单全收**（`data.get(k, default)`，只在缺键时才用配置默认值，`:441-448`）。加载时必须用**当前配置重新钳制** `recursion_limit`/`max_nodes`/`max_runs`；节点级 `max_tokens`/`max_time_s` 与节点 `mode` 是另外两条未钳制轴（见 Impact Analysis 与 design.md D3）。
- **资产版本与迁移纪律**：资产文件带 `asset_schema_version`；读取时高版本**明确拒绝**而非静默降级（照 `zcode` 的 `CURRENT_SCHEMA_VERSION` 纪律）。
- **内化触发语义定为显式保存**（关键设计点，见 design.md D4）：不做「跑过一次就自动入库」；同名覆盖 + 内置 pattern 名保留。

## Capabilities

### New Capabilities

无新能力域；在既有能力域上深化。

### Modified Capabilities

- `multi-agent-collaboration`: 在既有「声明式 Workflow DSL」之上新增「workflow 资产（保存 / 索引 / 按名复用）」的行为规格，并对「节点级预算与 mode 的加载期钳制」新增 requirement。
- `subagents`: 「深度到限撤 spawn 工具」requirement 的**工具枚举**需要扩展——新增的按名启动资产的工具与 `StartWorkflow`/`RunWorkflow` 语义等价（一次性拉起整张图），必须一并纳入深度闸的工具清单，否则深度到限的子 agent 可以绕过图级上限。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据——架构级改造（新增跨会话持久层 + 新的加载信任边界 + 新工具面），且走 grill 的非平凡 change。
- research questions:
  1. 业界 coding agent 怎么把「跑过的编排」沉淀为可复用资产？命名、落点、索引、同名优先级各是怎么定的？
  2. 序列化「蓝图/配方」与序列化「运行时状态」在信任模型上有什么区别？「从磁盘加载」的既定安全姿态是什么？
  3. 资产文件格式怎么做版本演进，才不会在升级后静默读出错误语义？
  4. 上游（编排 DSL 层）的「注册表 / 优先级 / 覆盖」机制有没有可直接借鉴的成熟形态？
- findings:

  **第一层：本地参考仓库定向检索**（`/home/shared/agent-study/reference-repos/`，全部可用，逐条附 `file:line`）

  - **`pi/`（权重最高）——「双落点 + 首见者胜」的资产发现模型。** `packages/coding-agent/src/config.ts:528-534` 定义 `getAgentDir()` = `~/.pi/agent`，`:567-568` 的 `getPromptsDir()` = `join(getAgentDir(), "prompts")`，`:572` 的 `getSessionsDir()` 同理——**用户级资产集中在 `~/.pi/agent/<kind>/`**，与 `<cwd>/.pi/<kind>/` 并列。`packages/coding-agent/src/core/prompt-templates.ts:235-236` 构造 `globalPromptsDir` 与 `projectPromptsDir`，`:268-271` 的加载顺序是**先 global 后 project**；而 `packages/coding-agent/src/core/resource-loader.ts:1057-1081` 的 `dedupePrompts()` 是「首次出现者保留、后续同名记 `collision` 诊断并附 `winnerPath`/`loserPath`」——**所以 prompt 类型的同名优先级是 user 胜 project**。但**同一仓库的 agent 类型恰好相反**：`packages/coding-agent/examples/extensions/subagent/agents.ts:137-143` 先 `set` userAgents 再 `set` projectAgents（Map 覆盖）⇒ **project 胜 user**。**这是本次调研最有用的一条**：同一个上游里两种资源的同名优先级是**相反的**，说明优先级不是「自然规律」而是**必须逐类型显式拍板并文档化**的产品决策。另外 `prompt-templates.ts:159-198` 的 `loadTemplatesFromDir()` 只收 `.md`、跳过断链 symlink、单文件读失败降级为 diagnostic 不炸整体——**「一个坏文件不能带走整批资产」**的容错姿态。`packages/agent/src/harness/session/jsonl/fork.ts:292` 记录 append-only 写入期间源文件不得被替换/编辑。
  - **`deepseek-harness/`（权重高）——「声明作为纯数据、执行前先校验」。** `docs/subsystems/workflow.md:13` 明确 workflow 的 `meta` 与 `args` **是 plain JSON DATA**：「the engine validates `meta` against its schema and rejects loud BEFORE anything runs — **no script text is ever evaluated to obtain it**」。`docs/subsystems/workflow.md:51` 的 `WorkflowMeta` 定义 `name`（kebab-case，display + **persistence key**）/`description`（required）/`whenToUse`/`phases`（optional annotation），并注明字段词表与 Claude Code 的 meta block 对齐。**这正是本 change 需要的姿态**：资产的元数据（name/description/whenToUse）是**数据**，不是被求值的代码；且「校验失败要 loud reject，发生在任何执行之前」。持久化侧：`docs/subsystems/session.md:5` 把 Session 建模为 **append-only log**、消息历史是**派生**而非另存、replay = 从同一批事件重新派生；`docs/subsystems/persistence.md:11` 要求**单写者所有权**（第二个 `open(id,'write')` 直接 `SessionAlreadyOwnedError`）——**「同一份持久资产同时被两个进程改」是被显式拒绝的**，这条对本 change 的资产写路径同样适用。
  - **`zcode/`——配置文件版本迁移纪律。** `packages/provider-node/src/provider-config-file-codec.ts:12` 定义 `CURRENT_SCHEMA_VERSION = 1`；`:32` 定义 `UnsupportedProviderConfigVersionError`；`:46-56` 的 `decodeProviderConfigFile()` 逻辑是：**缺 `schemaVersion` ⇒ 报错**、**高于当前支持版本 ⇒ 明确报错**、低于则逐级查 `migrations` 表，**缺迁移器也报错**（不静默）。这是本 change 资产文件 `asset_schema_version` 的直接模板：**升级后读到更高版本必须拒绝，不能猜**。
  - **`kimi-code/`——注册表 + 来源优先级 + 内置占位。** `packages/agent-core-v2/src/app/agentProfileCatalog/agentProfileRegistry.ts:8` 的 `AgentProfileRegistration` 带 **`priority: number`** 与 `sourceId`；`builtinAgentProfileLoader.ts:5` 用常量 `BUILTIN_AGENT_PROFILE_SOURCE_ID = 'builtin'` 把**内置来源与用户来源显式分列**；`agentProfileCatalog.ts:41-45` 的 profile 形状含 `whenToUse`、**`override?: boolean`**、`tools`/`disallowedTools`/`subagents`。可借鉴点：**「内置 vs 用户」是显式的来源维度，不是靠命名约定隐式区分**；以及 profile 里能声明**工具白/黑名单**——资产若能声明工具面，就等于一份持久化的能力授予（见 design.md D3 的 `mode` 收窄）。
  - **`codex/`（`codex-rs/` 定向 rg）——模板作为编译期常量。** `codex-rs/prompts/src/compact.rs:1-2`、`apply_patch.rs:3`、`review_exit.rs:6,8`、`goals.rs:7,15,22` 全部是 `include_str!("../templates/...")`：**模板在产品构建期就固化进二进制，运行期不从磁盘读**。这是一个与 Claude Code 相反的极端，价值在于它**划清了本 change 的边界**：只有「用户/模型在运行中产出的编排」才需要磁盘资产层；产品自带的模板应该走编译期常量或代码内注册表（这正是 #246 内置模板归一的范畴）。

  **第二层：业界实践（附真实 URL）**

  - **Claude Code 的命名 workflow 资产**（[code.claude.com/docs/en/workflows](https://code.claude.com/docs/en/workflows)，与本 change 最直接对应）。要点逐条：①**双落点**——保存对话框在 `.claude/workflows/`（项目级，「shared with everyone who clones the repo」）与 `~/.claude/workflows/`（个人级，「available in every project, visible only to you」）之间切换；②**保存前检查 symlink**——项目位置下 `.claude`、`.claude/workflows` 或目标文件任一为 symlink 即拒绝；个人位置只拒绝目标文件本身为 symlink（这样 dotfiles 工具管理的 `~/.claude` 仍可用），并注明 v2.1.216 之前会跟随链接、可能把文件写到选定位置之外；③**同名优先级明确且与作用域绑定**——「If a project workflow and a personal workflow share a name, the project one runs」，monorepo 里多个 `.claude/workflows/` 时**离当前工作目录最近的那个胜**；④**保存后以 `/<name>` 运行**，经 `/reload-skills` 重读目录；⑤**保存文件形态 = `meta` 块 + 脚本体**，`meta` 必须是**第一个语句、纯字面量对象**（含变量/函数调用/spread 就会从 autocomplete 掉名）；⑥**`args` 全局变量**作为参数化通道（调用时传入，脚本按结构化数据读）；⑦**信任姿态**——运行时只允许会话已获准读取的脚本文件，工作目录之外需先 `/add-dir` 或加 Read allow rule；插件分发的 workflow 按插件名做命名空间（`/acme-tools:release-audit`）。**与本 change 的关键差异**：Claude Code 存的是**可执行 JS 脚本**（因此必须有脚本读权限门 + symlink 门），本 change 存的是**受限可校验的数据 spec**，没有任何可执行字段——信任模型因此可以更轻，但**不能因此省掉闸值钳制**。
  - **AutoGen 的 `dump_component()` / `load_component()`**（[serialize-components](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/serialize-components.html)、[component-config](https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/framework/component-config.html)）。两者是「组件配置」体系的两半：`dump_component()` 把活对象变成 declarative spec，`load_component()` 反向重建。官方文档给出**全大写的安全警告「ONLY LOAD COMPONENTS FROM TRUSTED SOURCES」**，理由是每个组件自带反序列化逻辑，「In some cases, creating an object may include executing code (e.g., a serialized function)」。与 `save_state()`/`load_state()` 的分野在 component-config 页写得很清楚：**state 是「让这个对象成为它自己的全部数据」（含消息历史，反序列化应得回「exact same object」）；component config 是「对象的蓝图，可以被反复盖章出多个实例」**。**对本 change 的结论**：我们的 spec 更接近后者（蓝图，可反复实例化），但 AutoGen 的警告**不直接适用**——因为 AutoGen 的危险来自「组件自带反序列化逻辑」，而 `WorkflowSpec` 的字段全是受限枚举（`REDUCERS`、`NODE_KINDS`、`JOIN_SEMANTICS`，`agent/subagent/workflow.py:27-32`）与字符串标签，`parse_workflow_spec` 不 import 运行时、不求值任何表达式（`workflow.py:15-16` 的模块 docstring 明说这点）。**所以本 change 的信任风险不是「反序列化执行代码」，而是「持久化的资源与能力声明」**——闸值绕过、`mode: build` 的能力授予、以及 spec 文本本身携带的提示注入。这个区分必须写进 design 的信任边界论证，不能照抄 AutoGen 的结论。旁证：CSA 的研究记录（[AutoJack 研究简报](https://labs.cloudsecurityalliance.org/wp-content/uploads/2026/06/CSA_research_note_autojack-ai-agent-rce_20260621-csa-styled.pdf)）显示 agent 框架的 RCE 面普遍来自**框架逻辑层**而非模型输出本身，与「加载路径 = 信任边界」的判断一致。
  - **LangGraph**（[Checkpointers](https://docs.langchain.com/oss/javascript/langgraph/checkpointers)、[Checkpointing 概念](https://mintlify.wiki/langchain-ai/langgraph/concepts/checkpointing)）。checkpointer（`InMemorySaver` / `SqliteSaver` / `PostgresSaver`）在每个 super-step 边界存 `StateSnapshot`；`config={"configurable": {"thread_id": ...}}` 是 checkpoint 的**主键**，同 `thread_id` 续跑、省略即 `ValueError`、无历史 checkpoint 时续跑直接崩；`graph.getStateHistory()` 提供时间旅行、`updateState()` 产生新 checkpoint。**关键负面发现：LangGraph 没有「图模板注册表」**——search 结果里出现的 "registry" 是**线程注册表**（一 thread 一行，用于 `list_conversations` 与过滤），不是「图模板目录」；prebuilt 指的是 `create_react_agent` 这类**代码内自带**的构造器。**也就是说：LangGraph 恰好把本 change 要做的两件事都留给了应用层**——「跨会话可寻址的图模板目录」在它那里没有现成答案，只能自建。`thread_id` vs 「模板名」的区分很有启发：**运行时实例（thread/workflow_id）与设计时模板（图定义/资产名）必须是两个命名空间**，本 change 的现状恰恰把两者混成了一个随机串。
  - **CrewAI**（[Flows](https://docs.crewai.com/concepts/flows)）。两轴结构：**Crew**（agent+task 的自主协作单元）与 **Flow**（跨 crew 的编排单元，用 `@start()` / `@listen(method)` / `@router()` 声明分支与触发）。`@persist` 装饰器（类级 = 所有 flow 方法的状态都持久化；方法级 = 只持久化该方法）把状态存 SQLite（`SQLiteFlowPersistence` 为默认后端），状态自动获得 UUID，**该 id 跨状态更新与方法调用保持不变**；`kickoff(inputs={"id": <uuid>})` 是**续跑（resume）**——载入该 UUID 的最新快照并继续写在同一 UUID 下；`kickoff(restore_from_state_id=<uuid>)` 是**分叉（fork）**——从该快照 hydrate 一个新 run、分配**全新** `state.id`，源 flow 历史不受影响。**这条 resume/fork 二分对本 change 直接有用**：资产的复用天然是 fork 语义（每次调用都是新 `wf_<uuid8>`、新结果目录），而资产本体永不被执行污染。另外 `restore_from_state_id` 与 `from_checkpoint` **同时给会 `ValueError`**（「必须二选一」）——「恢复来源必须唯一确定」是本 change 加载路径应当继承的纪律。

- design impact:
  - **D1（资产载体分两路）**：由「`RunPattern` 的输入是配方、DSL 路径的输入已经是展开 spec」这一代码事实决定，不是自由选择；AutoGen 的「蓝图 vs 状态」二分提供了命名与语义骨架（资产 = 蓝图，per-run `wf_<uuid8>` = 状态）。
  - **D2（落点与作用域）**：Claude Code 的双落点 + 项目级优先 + 最近的胜，与 pi 的 `~/.pi/agent/<kind>/` 集中式落点，共同支撑「本机落点先行、共享路径另议」；同时暴露一个本仓库特有的语义分叉（memory 走 git common dir 所以跨 worktree 共享，`WorkflowStore` 直接用 `workspace_root` 所以 per-checkout），必须在设计里定死（见 Open Questions）。
  - **D3（加载期钳制与能力面收窄）**：AutoGen 的 trusted-sources 警告 + deepseek-harness 的「校验先于执行、loud reject」+ kimi 的 `tools`/`disallowedTools` profile 字段 + Claude Code 的 symlink 门，共同把加载路径定性为**信任边界**；但风险类型是「持久化资源/能力声明」而非「反序列化执行代码」（spec 无可执行字段，有 `workflow.py:27-32` 的受限枚举与 `:15-16` 的模块纪律为证）。节点 `mode` 与节点级 `max_tokens`/`max_time_s` 是主 session 分析未列出的两条未钳制轴。
  - **D4（显式保存 vs 自动内化）**：pi 的 `collision` 诊断（同名冲突可见）、Claude Code 的显式保存动作（`/workflows` 里按 `s`、选位置、按 Enter）、deepseek-harness 的 `persistence key` 概念，共同支持「显式保存 + 同名覆盖可见化 + 内置名保留」。
  - **D5（命名空间与版本）**：LangGraph 的 `thread_id`（运行时）vs 图定义（设计时）分离 ⇒ 资产名与 `wf_<uuid8>` 必须是两个命名空间；zcode 的 `CURRENT_SCHEMA_VERSION` + `UnsupportedProviderConfigVersionError` ⇒ 资产的 `asset_schema_version` 版本纪律；deepseek-harness 的 `WorkflowMeta`（name/description/whenToUse，纯数据）⇒ 资产元数据字段表。
  - **D6（不重复造）**：CrewAI 的 resume/fork 二分 ⇒ 资产复用一律 fork（永不污染资产本体）；codex 的编译期模板常量 ⇒ 产品自带模板不进磁盘资产层（边界划给 #246）。

## Impact Analysis

- **能力域**:
  - `multi-agent-collaboration`: 新增「workflow 资产（保存 / 索引 / 按名复用）」行为规格；新增「从磁盘加载 spec 的闸值与能力面钳制」规格。
  - `subagents`: 「深度到限撤 spawn 工具」的工具枚举扩展（加入按名启动资产的工具）。
- **代码**（实现期细化，下述为当前已核实的影响面）:
  - 新增 `agent/subagent/workflow_assets.py`（或同级模块）：资产 schema、slug 校验、读写纪律、索引、`asset_schema_version` 判定。
  - `agent/subagent/workflow.py`：**不落笔**。原计划的「`parse_workflow_spec` 增加闸值上限通道」已被 Q8 方案 C 否决（那会把钳制值写回 spec、改变 `spec_hash`）。
  - `agent/subagent/scheduler.py`：`_eff_limit(field)` 统一访问器 + `limit_ceiling` 构造参数 + `limits` 报值出口（Q8 方案 C）；`asset_source` 附加字段（pattern 溯源）。
  - `agent/subagent/manager.py`: `SPAWN_TOOL_NAMES` 加入 `RunWorkflowAsset`；子 loop 构造期传 `include_workflow_asset_index=False`（Q9）。
  - `agent/tools/builtin/subagents.py`：新增 4 个工具类 + `_spec_bounds()` 被资产加载路径复用。
  - `agent/loop.py`：工具注册 + `include_workflow_asset_index` 构造参数 + 注册 `WorkflowAssetIndexSource`（root）。
  - 新增 `agent/context/workflow_asset_source.py`：受限可发现面注入源（P2，`cacheable=False`）。
  - `agent/config.py`：**无改动**——资产层列表上限等常量落在 `agent/subagent/workflow_assets.py`，未新增配置面。
  - `agent/subagent/patterns.py` + `agent/subagent/scheduler.py`：**补 pattern 溯源**——今天 `run_pattern` 只在返回给模型的 result dict 里带 `pattern`（`patterns.py:447-461`），而 `manager` 注册的是 scheduler 对象（`manager.py:663-664`），scheduler 上没有任何来源字段。所以「存配方」这条载体在现状下**落不了地**（保存时只能拿到展开后的 spec、配方与 params 已丢失）。对策：在 `WorkflowScheduler` 上声明一个默认值为 `{"kind": "dsl"}` 的 `asset_source` 附加字段，由 `run_pattern` 覆盖为 pattern 溯源（见 design.md D1 的「实现前提」）。这是本 change **直接**改动既有运行路径的一处，且是**纯附加、不改返回结构**。**另有第二处既有运行路径的修复作为前置依赖**：workflow 节点 `mode` 钳制的比较基准错误（fail-open + 静默降级），已立项为独立 bug issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)，本 change 以它为**前置阻塞项**（资产的 mode 批准面依赖它），修复本身在 #255 内落地。
- **测试**: 新增资产 round-trip、slug/逃逸拒绝、`asset_schema_version` 高低版本分支、闸值钳制回落、`mode` 收窄、内置名占用拒绝、同名覆盖与 `spec_hash` 去重、索引有界、跨会话可寻址、坏资产不炸整体；回归「既有 `StartWorkflow`/`RunWorkflow`/`RunPattern` 行为逐字不变」。
- **文档**: `docs/openspec-change-backlog.md`（新增条目 + 并行批次）；`docs/architecture.md` 的 subagent/workflow 段落（如提及结果落点）；`README.md` + `README_EN.md`（如工具清单被列出）。**关键文档影响检查项**：确认 `.asterwynd/` 已在 `.gitignore:11`，资产目录**不应**需要新增 ignore 条目；若最终落点改到可提交路径，则本 change 的 Non-Goals 被违反，必须回写。
- **不影响**:
  - `workflow_id`（`wf_<uuid8>`）的生成与 per-run 结果落点（`WorkflowStore`）不变——资产是**第三个命名空间**，不复用 `.asterwynd/workflows/`（该 subtree 的分离理由见 `workflow_store.py:5-16`）。
  - benchmark 的 `workflow_record.json` 语义不变（它是观测/回归对照记录，不是资产）。
  - 内置 4 个 pattern 的编译结果不变（资产层只**引用** `compile_pattern`）。
  - 不做可提交（团队共享）的资产路径——见 Non-Goals（design.md）。
- **影响面结论**（原「待确认影响面」5 项，均已由用户拍板为结论；逐条见 design.md 的 ✅ 块与 `reviews/grill-design.md` 的 `## User Confirmation`）:
  1. 落点 = **per-repo**（`~/.asterwynd/projects/<hash>/workflow-assets/`，照 memory 的 git common dir 解析，跨 worktree 共享）——Q1=B。
  2. 闸值钳制**只作用于资产加载路径**，模型当轮声明 spec 的路径行为逐字不变；「模型声明路径是否也该钳」记为独立 follow-up——Q2=A。
  3. DSL 资产**引入显式声明的覆盖面**（`overrides: {node_id: [field]}`），覆盖在 `parse_spec_for_manager` 之前应用，未声明组合拒绝——Q3=B。
  4. 资产进入**受限可发现面**（只注入资产名 + 单行截断 description，20 条 / 120 字符 / slug 64，只注入 root 会话，`cacheable=False`）——Q4=B + Q9。
  5. 资产里的 `mode` **只收窄不放宽**，收窄机制由 [#255](https://github.com/Xingkai98/asterwynd/issues/255) 提供，本 change 只做资产面呈现（diagnostics + 「以声明 mode 运行」清单）——Q5=B + Q7。

## 与既有 change 的边界

- **#246（内置模板归一）**：内置模板走代码内注册表（对应 codex 的编译期常量姿态），不进磁盘资产层。本 change 只负责「运行中产出的编排如何沉淀与复用」，为 #246 提供寻址与加载契约。
- **`benchmark-workflow-replay`（已归档）**：它有 `workflow_record.json` 做「record → replay」的**回归对照**，本 change 有资产做**复用**。两者共享 `WorkflowSpec.to_dict()` 序列化格式，但**触发语义、落点、生命周期都不同**，本 change 不合并、不替换它。
- **`long-term-memory-deepening` 系列（已归档）**：memory 的 slug + 索引 + dedup judge 形态被**借鉴**，但资产不做 decay/importance（编排资产的「重要度」没有可信信号），也不做 git 可回溯（`.asterwynd/` 本身不提交，且 `WorkflowStore` 已有事件日志纪律）。
