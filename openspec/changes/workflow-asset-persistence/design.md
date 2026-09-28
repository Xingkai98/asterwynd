# Design: Workflow 资产化：跑过的图沉淀为工作区可复用模板

## Context

C1–C5（队列化并发 → Workflow DSL 调度器 → 结果聚合 → 预算归因 → benchmark 可重放）已把「模型自由编排几十~上百个 subagent」做成产品能力，`workflow-graph-visualization` 补上了运行态可视化。缺的是**复用面**：跑过的图随会话消失，模型每次从零重写整张 spec。

现状的三条硬事实（已逐条读码核实，不是转述）：

1. **`workflow_id` 是随机串且注册表在内存里。** `WorkflowScheduler.__init__` 里 `self.workflow_id = workflow_id or f"wf_{uuid.uuid4().hex[:8]}"`（`agent/subagent/scheduler.py:451`）；`SubAgentManager._workflows` 是 per-manager 的 dict（`agent/subagent/manager.py:505`），未知 id 的返回体自述 "the registry is per-manager and in-memory"（`agent/tools/builtin/subagents.py:504-513`）。跨会话无法寻址。
2. **结果落盘是 per-run 的，不是资产。** `WorkflowStore.for_workspace()` 解析出 `<workspace_root>/.asterwynd/workflows/<workflow_id>/`（`agent/subagent/workflow_store.py:56-60`），该 subtree 存在的理由是「result artifact 与 checkpoint 必须分命名空间」（`workflow_store.py:5-16`）。它是执行产物，不是可复用模板。
3. **序列化 round-trip 已经可用。** `WorkflowSpec.to_dict()` + `parse_workflow_spec` 的往返被测试钉死（`tests/agent/subagent/test_pattern_templates.py:114-118`），C5 的 `workflow_record.json` 已经在做「从磁盘读 spec 再跑」。

**约束**：`.asterwynd/` 已在 `.gitignore:11`（本机、不共享、不提交）。任何「团队共享编排」的形态都意味着别人 clone 后跑的是别人存的 spec，而 spec 里的 `task` 文本可控——本 change 明确不做（见 Non-Goals）。

**关键代码事实（决定 D1，必须在此写明）**：资产有两类来源，它们的输入形态**不同**：

- `RunPattern` 路径的输入是 **配方**：`RunPatternTool.execute` 拿到 `pattern` / `task` / `params`（`agent/tools/builtin/subagents.py:409-427`），`compile_pattern` 把 `PATTERNS[pattern](task=task, params=params).compile()` 编成 spec（`agent/subagent/patterns.py:234-243, 279-280`）；编译后的 `foreach.items` 已是**具体列表**——`_items(workers, "worker")` 产出 `[{"name": "worker-0"}, ...]`（`patterns.py:61-62, 80-104`）。**所以 pattern 路径上「配方」是现成的、参数化天然保留。**
- `DeclareWorkflow` / `RunWorkflow` 路径的输入**已经是展开后的 spec**：工具只收一个 `spec` 对象（`subagents.py:566-572, 852-856`），没有任何地方保存「它是怎么被生成出来的」。**所以 DSL 路径上不存在可还原的配方**——「存配方还是存成品」在这条路径上不是二选一，而是只有一个可选项：存 spec 本身。

**由此暴露的一个实现前提（本 change 必须补，否则 D1 的第一类载体落不了地）**：**配方在今天不可寻址**。`run_pattern` 在 `scheduler.run(spec)` 之后只把 `pattern` 塞进**返回给模型的 result dict**（`patterns.py:447-461` 的 `_legacy_result(pattern, ...)`），而 `manager.register_workflow(scheduler)` 注册的是 **scheduler 对象**（`manager.py:663-664`），scheduler 上**没有任何 pattern 溯源字段**（对 `scheduler.py` 全文件 grep `pattern` 只命中无关的注释与 `origin` 参数）。也就是说：`SaveWorkflowAsset(workflow_id=…)` 若能拿到的只有 `scheduler.spec`（展开后的 spec），**配方与 params 都已丢失**，只能退化成 `source: "dsl"`。
另外 `RunWorkflow` 若被喂一份**手写的、恰好等于某 pattern 编译结果**的 spec，也同样无从判定来源——**靠 `spec_hash` 反查 4 个 pattern 是可行的探测但不可靠**（params 不可还原，且随默认值变动会漂移），不采用。

**对策（进 tasks 3.2/3.5）**：在 `WorkflowScheduler.__init__` **声明并默认** `asset_source = {"kind": "dsl"}`，由 `run_pattern` 在 `scheduler.run()` 前覆盖为 `{"kind": "pattern", "pattern": pattern, "params": params, "task": task}`。`SaveWorkflowAsset` 读该字段决定载体；字段缺失（老路径/未预期入口）**一律降级为 `source: "dsl"`**，不猜。**纯附加字段**——不改 `run_pattern` 的返回结构、不改 `_legacy_result`、不加新执行分支；该字段不在 `_envelope`/`parent_envelope` 的显式挑字段清单内，故不污染契约。
> **口径订正（2026-09-26，Q7 拍板后）**：本 change 改动既有运行路径的地方**不再是「一处」**。原口径（只有 pattern 溯源这一处）在 Q7 走 contextvar 方案后失效——mode 上限的 contextvar 安装点（`_execute_run_in_context`，与既有 `set_spawn_depth`/`set_current_run_id` 同处）虽属 **#255 的修复范围**而非本 change 直接落笔，但本 change **消费**其语义且**依赖**它作为前置。因此本 change 的准确口径是：**直接改动既有运行路径 1 处（pattern 溯源，纯附加字段）；依赖另一处既有运行路径的修复（#255 的 mode 上限 contextvar，本 change 不落笔但以它为前置阻塞项）**。
**已知代价**：一份 pattern 资产被 `GetWorkflowAsset` 取出、经 `RunWorkflow` 再跑一次后若再保存，会退化成 DSL 资产（溯源在往返中丢失）。这是可接受的行为，需在工具描述里写明。

## Goals / Non-Goals

**Goals**

1. 新增**跨会话可寻址**的 workflow 资产层：命名（slug）、落点、索引、版本纪律。
2. 把**刚跑过的图**一键沉淀为资产，且 spec **不穿过模型输出**（保存的输入是 `workflow_id`，正文由服务端取出）。
3. 按名**直接调用**资产并驱动调度器——这是「无需模型重新生成拓扑」的兑现点。
4. 两类载体都支持：pattern 资产存配方（参数化保留），DSL 资产存 spec + **显式声明的覆盖面**（零新方言）。
5. **加载路径 = 信任边界**：用当前配置重新钳制结构闸值；收窄（而不是照搬）节点 `mode`；对高版本资产明确拒绝。
6. **不重复造**：复用既有的写盘纪律、`spec_hash`、校验管线与模板编译器。

**Non-Goals**

- **不做可提交（团队共享）的资产路径。** 供应链风险（他人提交的 spec 在其仓库里被执行、`task` 文本可控）不在本 change 的消化范围内。若未来要做，必须同时引入签名/审批面，那是独立 change。
- **不改 `workflow_id` 的生成与 per-run 结果落点。** `wf_<uuid8>` 与 `.asterwynd/workflows/<id>/` 逐字不变。
- **不合并 benchmark 的 `workflow_record.json`。** 它是「record → replay」的回归对照，触发语义与生命周期都不同。
- **不做内置模板归一。** 内置 4 个 pattern 走代码内注册表（`PATTERNS`，`patterns.py:303-308`），不进磁盘资产层——那是 #246 的范畴。
- **不引入通用模板方言。** 不做占位符插值、表达式求值、item 名模板生成。覆盖面只允许对**既有 spec 字段**做直接赋值（见 D1）。
- **不做跨进程写锁。** 单进程 asyncio + `_atomic_write` 足够；不做 deepseek-harness 那样的 `SessionAlreadyOwnedError` 跨进程所有权（记入已知欠债）。
- **不做资产的 decay / importance / LLM dedup judge。** 没有可信信号（编排资产没有「被引用次数」这类本机可观测的使用计数），硬凑一个只会制造噪音。

## Decisions

### D1 — 资产的载体：两类，由来源路径决定，不是自由选择

资产是一个 tagged union，落成一个 JSON 文件：

```json
{
  "asset_schema_version": 1,
  "name": "repo-health-check",
  "description": "对指定目录做并行体检并汇聚",
  "when_to_use": "需要在一次 run 里并行扫描多个目录时",
  "source": "pattern",
  "goal": "体检这些目录",
  "recipe": { "pattern": "orchestrator-worker", "params": {"workers": 3}, "task": "体检这些目录" },
  "spec_hash": "…16 hex…",
  "node_count": 3,
  "created_at": "2026-09-26T10:00:00Z"
}
```

```json
{
  "asset_schema_version": 1,
  "name": "release-audit",
  "description": "五路并行审计 + 汇聚",
  "source": "dsl",
  "goal": "审计本次发布",
  "spec": { "…WorkflowSpec.to_dict()…" },
  "overrides": { "audits": ["items"] },
  "spec_hash": "…16 hex…",
  "node_count": 6,
  "created_at": "2026-09-26T10:00:00Z"
}
```

- `source == "pattern"`：加载时 `compile_pattern(recipe.pattern, task=…, params=merged)`（`patterns.py:234-243`）。**参数化天然保留**——`workers=3 → 5` 只需改 `params`，重新编译即得 5 个展开项。
- `source == "dsl"`：加载时对 `spec` 应用白名单内的覆盖，再走 `parse_spec_for_manager`（`subagents.py:456-463`）。
- `overrides`（仅 DSL 资产，可选）：`{node_id: [field, ...]}`。受允许的 `field` 是**既有 spec 字段**的一个封闭子集：`task` / `items` / `max_items` / `max_tokens` / `max_time_s`。未列出的 `(node_id, field)` 组合在调用时**拒绝**（`override_not_declared`）。
- **零新方言**：覆盖就是对既有字段的直接赋值，没有任何插值/表达式/item 名模板。覆盖**在 `parse_spec_for_manager` 之前**应用，因此 reducer 冲突、环的可启动性、闸值上限等既有校验**全部照跑**。

**为什么不做「配方化 DSL」（方案 C）**：给 `foreach` 加 `item_template: "worker-{i}"` + `count` 能省 token，但引入了占位符语义、转义规则、与既有 `items` 字段的共存规则——正是 issue #245 明确要避免的「发明新方言」。B（显式覆盖面）落地后若实测 `items` 覆盖太啰嗦，再补 C 是纯增量，不阻塞。

**替代方案与否决理由**：
- 只存成品 spec、不做任何参数化 —— 否决。`workers=3 → 5` 要手改 `items` 列表，等于把「重新生成拓扑」退化成「复述 + 手改」，核心价值打折（见 Open Question Q3 的场景）。
- 为 DSL 发明通用模板变量 —— 否决，见上。

### D2 — 落点与作用域：本机、按仓库共享（推荐），不使用可提交路径

- 候选落点 A：`<workspace_root>/.asterwynd/workflow-assets/`——与 `WorkflowStore`（`workflow_store.py:56-60`）、`SubagentSnapshotStore`（`agent/subagent/snapshot.py:34-35`）、sessions（`agent/main.py:215-216`）同域，**per-checkout**。
- 候选落点 B：`~/.asterwynd/projects/<hash>/workflow-assets/`——照 memory 的 scope 解析：`_find_scope_root` 把 worktree 的 `.git` **文件**经 `commondir` 解析回主 worktree 根（`agent/memory/persistent.py:66-87`），再取 `sha256(resolved)[:16]` 作桶名（`persistent.py:60-62, 180-185`），**per-repo，跨 worktree 共享**。
- **推荐 B**。理由：本仓库的开发流程（AGENTS.md）强制 worktree，per-checkout 会让资产库静默碎片化——在 worktree 里攒的资产回主仓库看不到，反之亦然。「跨会话复用」是资产的全部价值，作用域比 checkout 更细就兑现不了。
- 两者都是**本机、不共享、不提交**（`~/.asterwynd/` 与 `.asterwynd/` 都不在版本控制内），所以 D2 的选择不影响「不做共享路径」这条 Non-Goal。
- 落点在实现期由 `WorkflowAssetStore.for_workspace(workspace_root)` 这类构造器集中决定，调用方不感知（便于 Q1 拍板后单向切换）。
- 已知代价（写进 Risks）：资产不再落在项目目录内，「删掉项目目录」不会带走资产；反过来，用户若期望 `ls .asterwynd/` 能看到资产，需要文档说明。

### D3 — 加载路径是新的信任边界

**先划清风险类型。** AutoGen 对 `load_component()` 给出全大写警告「ONLY LOAD COMPONENTS FROM TRUSTED SOURCES」，理由是组件自带反序列化逻辑、「creating an object may include executing code」（见 proposal 的 RIR）。**这条不适用于本 change**：`agent/subagent/workflow.py` 的模块 docstring 明说它「不执行任何模型生成代码，不 import 运行时（manager/scheduler），只做结构与语义校验」（`workflow.py:15-16`）；`NODE_KINDS`/`JOIN_SEMANTICS`/`AGGREGATE_STRATEGIES`/`REDUCERS`/`CHANNELS` 全是受限枚举（`workflow.py:27-32`）；`$ref` 只做字符串槽引用 + 行首匹配，槽缺失静默走 default（`workflow.py:98-114`）。**加载一份恶意 spec 不存在 RCE 面。**

真正的风险有三类，逐条给对策：

**(1) 闸值绕过（结构资源）。** `_positive_int` 只要求 `>= 1`、**无上界**（`workflow.py:451-454`），且 `_resolve_limits` 对 spec 自声明的值照单全收——`data.get(k, default)` 只在**缺键**时才用配置默认值（`workflow.py:433-448`）。一份写着 `"recursion_limit": 999999, "max_nodes": 999999, "max_runs": 999999` 的资产，今天会被完整接受。

**对策（✅ Q8 已确认 = 方案 C，2026-09-26）**：**不回写 spec**。在 **scheduler 读取** `spec.max_runs` / `spec.max_nodes` / `spec.recursion_limit` 的入口处取 `min(declared, config)`，`WorkflowSpec` 对象本身**保持声明值不变**。
**为什么不改 `parse_workflow_spec`（原设计的 `limit_ceiling` 通道，已否决）**：`WorkflowSpec.to_dict()` 只在值**不等于模块默认**时才输出这三个键（`workflow.py:279-294`），而 `spec_hash` 取该 dict 的 canonical JSON（`workflow.py:297-300`）。把钳制过的值写回 spec 会让「等于默认值」的键被**丢弃**，hash 随之改变——实测：声明 `max_runs=5000, max_nodes=900` 的 hash 为 `5bb392f41782ea7b`，钳到 `(300, 200)` 后变成 `d1130d802fff9a0b`。连带三处失效：round-trip 断言在配置 ≠ 模块默认值时必红；D4 的 `unchanged` 去重把「未变」误判为「已更新」并重写资产；**「加载后重存」会让资产永久遗忘自己声明过的上限**（下次配置调大时它已经只记得 300）。方案 C 让钳制成为**纯执行期读值**，资产原文与指纹都不被运行时配置污染。
**实现约束（grill 第二轮订正：这是「新增字段」而非「订正既有假面」）**：实测（`/tmp/probe_exits.py` 与主 session 复核）`status()` / `parent_envelope()` / `workflow_graph_snapshot()` / `_envelope()` 四个出口今天**根本不报**这三个限制值——唯一报值处是 `DeclareWorkflowTool` 的返回体（`agent/tools/builtin/subagents.py:589-591`），而那是**模型当轮声明路径**（Q2=A 不钳，报声明值正确）。所以本条的准确表述是：**若为可观测性新增这三个字段的报值出口，则报的必须是实际生效值**；**不是**去订正一个已存在的漂移。**实现期禁止**照「断言既有键 == 生效值」去写测试——既有的键不存在，会写成一条永远为真（或永远报错）的假测试。
**返回体仍须显式报 `limits_clamped`**（`{max_runs: {declared: 5000, applied: 300}}`），不静默。
**读取落点必须穷举（grill 第二轮给出完整清单）**：scheduler 内对三个字段的读取共 **9 处**（跨 8 个方法），全是 `spec.<field>` 点属性读，无「预烘进结构体」或「跨 await 缓存」的反例，因此「在读取处取 min」可达：`scheduler.py:753`（`register_workflow_bucket(spec.max_runs * 2)`——**派生值，最易漏**）、`:825`（`_check_declared_limits` 的 `max_nodes`）、`:884`（主循环 `self._steps >= spec.recursion_limit`）、`:1551`（`_dispatch` 的 `max_runs`）、`:2005`（`_expand_plan` 的 `max_nodes`）、`:2058` / `:2070`（`_check_foreach_budget`）、`:2593` / `:2594`（`_remaining_expansion_capacity`）。**展开期那几处（`:2005`/`:2058`/`:2070`/`:2593`/`:2594`）最容易漏**——漏掉会让「资产声明 `max_items=0` 的动态 foreach」按声明值而非配置值决定展开上限，钳制对动态展开整条路径失效。跨模块范围核对：`web/` 与 `benchmarks/` 对这三个字段**零读取**。
**作用范围**（✅ Q2 已确认 = 方案 A）：只作用于**资产加载路径**，模型当轮声明路径行为逐字不变。

**(2) 能力授予（`mode` 字段）——依赖前置修复 issue #255。** `_parse_node` 接受 `mode ∈ {build, read_only, plan}`（`workflow.py:492-496`），该 mode 决定子 agent 拿到哪些工具。所以一份资产可以**持久化地**授予写权限。

**用户确认的语义模型（三条，Q7 已确认，2026-09-26）**：
1. 每个节点有一个 `mode`，在**声明 workflow 时**配置——现有代码已满足（`WorkflowNode.mode`，声明期解析校验）。
2. 运行时**不可改变**——现有代码已满足（`WorkflowNode` 是 `frozen=True`，scheduler 全文件无 `.mode =` 写入）。
3. 每个节点的**有效 mode 不得超过「当前会话」的 mode**——**意图正确，但现有实现读错了源**。

**现有实现的缺陷（已立项 issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)，本 change 的**前置阻塞项**）**：`_clamp_mode`（`manager.py:1588`）读 `manager.parent_mode_provider`——这是 manager 的**共享实例字段**（`manager.py:454`），唯一写入点是 `AgentLoop.__init__` → `configure_runtime`（`agent/loop.py:153`）。子 agent loop 复用同一 manager（`manager.py:1303`），**每构造一个子 loop 就无条件覆盖它**。后果三类（主 session 两轮探针实证，非代码推断）：①**时序 fail-open**——BUILD 会话跑过工作流后 provider 停在 BUILD，切到 READ_ONLY 再加载声明 `mode: build` 的资产仍被授予 BUILD（`/tmp/myprobe2.py`）；②**并发结构性错误**——并行节点互相覆盖，构造序决定结果；③**静默降级**——BUILD 会话先构造过 read_only 子 loop 后，请求 build 被降级。**测试盲区**：`rg 'parent_mode_provider|_clamp_mode' tests/` 零命中。
**注意**：内置 4 个 pattern 模板不声明任何 `mode`（`patterns.py:80-231`），所以 pattern 路径绕过了这个缺陷；而本 change 的 DSL 资产**恰恰以保留显式 `mode` 为卖点**，是把这条路径放到台面上的那类输入。

**修复方向（用户拍板，走 contextvar）**：mode 上限改走 **contextvar**，与 `workflow_id` / `node_id` / `graph_distance` / `bus` **同机制**（`agent/subagent/context.py`）：scheduler 在派发点 set、`finally` reset，`create_subagent` 读。
- **快照语义**：workflow **启动时**快照 root 会话 mode 作为整轮上限；**运行中途切换模式不影响本次 run**。
- **嵌套语义**：节点 A 的有效 mode `E_A = min(M_A, R)`；A 派生的**子孙上限为 `E_A`**，**逐层收紧**。
- **落地位置（grill 第二轮订正，主 session 独立复现）**：**必须挂在 scheduler 的派发点** `_launch_run`（`scheduler.py:2112-2141`，与既有 4 个身份 contextvar 并列），**不是** `_execute_run_in_context`。
  - **为什么不是 `_execute_run_in_context`**：节点**自身**的 mode 在 `create_subagent` → `_clamp_mode`（`manager.py:559-562` / `:1588`）里定死，而该调用点在 `scheduler._launch_run` 的**派发**阶段（`scheduler.py:2119`）；`_execute_run_in_context`（`manager.py:991-1006`）是 run **真正执行**时才跑，**晚于**节点 mode 的冻结。实测（`/tmp/mine_landing.py`，会话 `read_only` + 节点声明 `build`）：**只挂 RUNCTX ⇒ 仍授予 `build`（fail-open 未被修）**；只挂 DISPATCH ⇒ 收窄为 `read_only` ✓。即挂 RUNCTX 只能管到**孙辈**，管不到节点自身。
  - **为什么派发点是对的**：在 `_launch_run` 里 `set(有效 mode)` 会**先于** `create_subagent` 生效（钳住节点自身），并经 `_enqueue_run` 的 `copy_context()`（`manager.py:880-887`）被捕获 ⇒ 传给子孙；子孙的执行体 `_execute_run_in_context` 会 `set_spawn_depth(run.depth)`（`manager.py:1004`）后重建子 loop，逐层收紧自然成立。
  - **该处 set 不配对 reset**（grill 第二轮实证）：`finally reset` 在 task 被**跨 context teardown** 时实测抛 `ValueError: ... was created in a different Context`——这正是既有代码在 `_execute_run_in_context` 里显式写明「No tokens are reset」（`manager.py:999-1002`）的原因。**注意**：派发点 `_launch_run` 是调度器 task 内被 await 的**普通协程**、不是「可能被外部 close 的 task 体」，所以那里沿用既有 4 个 contextvar 的 set/finally-reset 形态是安全的；**但把同样的 set/finally-reset 照抄到 `_execute_run_in_context` 会把一条现在没有的 teardown 崩溃引入子 agent 取消路径**。
  - **队列时机不是问题**（grill 第二轮实证）：上限由 **enqueue 时刻**的 `copy_context()` 固定（`manager.py:880-887` + `_start_task` 的 `create_task(..., context=item.context)`，`:962-964`）；`max_active=1` 强制排队后两个 run 各自拿到正确上限、互不串味。结构上也自洽：`session.mode` 在 `create_subagent` 就已冻结，run 是「给定 mode 的执行」，所以「入队那刻 vs 执行那刻」在正确实现下不是两个不同的值。

**主 session 的实证结论（不采信读码推断，探针 `/tmp/probe_nested_mode2.py`）**：把该机制装到真实 manager 的既有挂点上、驱动真实的队列/任务/上下文传播后，**全部通过**：
```
=== 并发交错 read_only 与 build 两个 run ===
  session_mode=build      {'ceiling_visible_to_child': 'build',     'grandchild_requested': 'build', 'grandchild_granted': 'build'}
  session_mode=read_only  {'ceiling_visible_to_child': 'read_only', 'grandchild_requested': 'build', 'grandchild_granted': 'read_only'}
  期望：read_only 的孙=read_only、build 的孙=build（互不覆盖） -> PASS
=== grandchild 逐层收紧 ===
  A(read_only) 上下文中请求 build -> 授予 read_only  -> PASS
```
即：**contextvar 能穿透嵌套 spawn（grandchild 拿到的上限 = 父节点的有效 mode，而非 root 的）**，且并发兄弟**互不串味**。这是共享 provider 方案做不到的（对照：同一探针形态下 provider 方案实测 fail-open）。

**对策**：修复 #255 后，`mode` **只能收窄，不得放宽**由 contextvar 上限**结构性保证**；`RunWorkflowAsset` 的返回体**必须列出「本资产将以其声明 mode 运行的节点」**，让父 agent 在批准前可见（修好基准后这个列表才可信）。理由：用户按名批准一次资产调用时，看到的是一个名字；若名字背后藏着一次写授权，批准面与实际能力面就脱钩了。`WorkspacePolicy` 与工具面本身不变（这是本仓库既有的沙箱边界，资产不越过它）。
**已确认的结构性上限**：`mode` 枚举面本身锁死在 `{build, read_only, plan}`（`workflow.py:492-496`），**资产永远无法表达 `BYPASS`**——这是 D3(2) 论证里未被写出、但实际存在的一层保护。

**(3) 提示注入（自由文本）。** `description` / `when_to_use` / 节点 `task` 是自由文本，会经由 `ListWorkflowAssets` / `GetWorkflowAsset` 进入模型上下文。
**对策（✅ Q4 已确认 = 方案 B 的受限形态；✅ Q9 已确认 = 具体数字与范围）**：本机落点（只有本地写权限者能落资产，与仓库本身同一信任级）+ 列表面有界 + 工具返回体把资产文本标记为**数据**。
**可发现面的具体参数（Q9 已确认）**：列表面 **20 条**；`description` 截 **120 字符**；slug 上限 **64**；超限按 `name` 升序取前 N 并追加「还有 M 个资产未列出」。**范围：只注入 root 会话，不进子 agent**。**`cacheable=False`**。
`cacheable=False` 不是可选项：`ContextBuilder` 对 `cacheable=True` 的源**永不裁剪**（`agent/context/builder.py:129-142` 的 `_find_trimmable_index` 跳过 critical + cacheable），而资产会被 `SaveWorkflowAsset` 在会话内改写——照 `MemoryIndexSource` 的先例（`sources.py:285-287`）必须每轮重渲染，否则内容陈旧且**永久占据**系统提示。
**slug 只受字符集约束的缺口（grill 发现）**：`_validate_name` 只校验字符集不校验长度（`agent/memory/persistent.py:112-116`），故 `ignore-previous-instructions-and-rm-rf` 这类名字合法。字符集（`^[a-z0-9-]+$`，无空格/换行/标点）挡住了**结构性**注入，挡不住**语义**暗示；**64 字符上限（Q9 已确认）**同时缓解注入面与路径长度两处压力，注入前仍须对名字与 description 做「单行化 + 截断」渲染。

**另外两条纪律**（照上游先例）：
- **slug 双重约束**：必须同时满足 memory 的 `^[a-z0-9-]+$`（`persistent.py:37`）与 `WorkflowStore` 的段级白名单 `_ALLOWED_REF_CHARS` 且非 `.`/`..`（`workflow_store.py:31-44`）——交集即 `[a-z0-9-]+`。写入时照 Claude Code 的 symlink 门：目标路径任一环节为 symlink 即拒绝，不穿透写入。
- **文件损坏容错**：照 pi 的 `loadTemplatesFromDir`（`packages/coding-agent/src/core/prompt-templates.ts:159-198`，断链 symlink 跳过、单文件读失败降级为 diagnostic）与 `WorkflowStore.read_events`（`workflow_store.py:188-206`，半行/损坏行跳过）：**一份坏资产不能带走整批**。索引重建时坏文件进 diagnostics，`ListWorkflowAssets` 照常返回其余。

### D4 — 内化触发语义：显式保存，不做自动入库

**决策：显式。** `SaveWorkflowAsset(workflow_id="wf_1a2b3c4d", name="bug-sweep", description="…")`。

理由：
- 自动内化会把**失败的一次性实验**也入库。memory 靠 dedup judge + decay + archive 收敛（`agent/memory/dedup.py`、`persistent.py` 的 `ARCHIVE_AFTER_DAYS`/`DECAY_THRESHOLD`），资产**没有等价收敛机制**（见 Non-Goals），腐化会单调累积。
- **错误的代价量级不同**：memory 存错了污染的是上下文；资产存错了会被**真的执行**——花真 token、真的起子 agent。
- 上游一致：Claude Code 也是显式保存动作（`/workflows` 里选中一次 run、按 `s`、在对话框里选位置、按 Enter），不是「跑过就自动存」。

**但留存成本必须足够低**，否则模型会退回去手抄 spec：
- 保存的输入是 `workflow_id`，`spec` 由 `manager.get_workflow(workflow_id).spec` 取出（`manager.py:666-667`），**不穿过模型输出**——既不花 output token，也不会被模型抄错。
- 同会话约束：`workflow_id` 只在 manager 的内存注册表里（`subagents.py:504-513` 自述），跨会话不存在。所以「保存刚跑的那张图」必须在**同一会话内**发起。这是可接受的——正符合「跑完觉得好用就存」的自然节奏；显式保存后在同一次 run 里立刻就能 `RunWorkflowAsset` 复用，收益即时可见。

**同名优先级（照 pi 的教训，必须逐类型显式定死）**：调研发现 pi 同一个上游里 prompt 与 agent 两种资源的同名优先级**是相反的**（prompt 用户级胜、agent 项目级胜，见 RIR），说明这不是自然规律而是必须拍板的产品决策。本 change 定：

- **内置 pattern 名保留**：`orchestrator-worker` / `peer-review` / `hierarchical` / `bidding`（`patterns.py:303-308`）。`SaveWorkflowAsset` 用这些名字**直接拒绝**（`reserved_name`）并给出可用命名提示；内置 pattern 继续走 `RunPattern`，**一个命名空间一种语义**，不做「资产覆盖内置」。
- **资产之间同名 = 覆盖**，照 memory 的 exists→update 分支（`persistent.py:519-530`）：返回体显式给 `"action": "created" | "updated" | "unchanged"` + `previous_spec_hash`；`spec_hash` 相同则 **`unchanged` 不写盘**（现成的最省 dedup，不需要 LLM judge）。
- **不做双落点**（本 change 只有一个落点），因此不需要 Claude Code 那条「项目级胜个人级、离 cwd 最近者胜」的跨作用域规则。未来加共享路径时再补。

### D5 — 命名空间、索引与版本

- **两个命名空间永不互相解析**：运行时实例是 `wf_<uuid8>`（`scheduler.py:451`），设计时资产是 `<slug>`。`RunWorkflowAsset` 不接受 `wf_*`，`GetWorkflow` 不接受 slug。依据：LangGraph 的 `thread_id`（运行时 checkpoint 主键）与图定义（设计时）是分离的两层，且它**没有**图模板注册表——「模板目录」是应用层的事，两层混用会立刻产生歧义（见 RIR）。
- **索引**：`index.json`（机器读）+ `INDEX.md`（人读，照 memory 的 `MEMORY.md`，`persistent.py:184`）。列表面**必须有界**——memory 的 `MAX_INDEX_LINES=200` / `MAX_INDEX_BYTES=25_000`（`persistent.py:35-36`）是同类问题的现成解法。`ListWorkflowAssets` 返回 `{name, description(单行截断), source, params 摘要, node_count, spec_hash}` + `limit`/`offset`，返回体给 `total`/`truncated`，**绝不返回 spec 正文**（正文走 `GetWorkflowAsset`）。
- **版本**：`asset_schema_version: 1`。读取时缺该键 ⇒ 报错；**高于当前支持版本 ⇒ 明确报错**（`unsupported_asset_version`），不猜、不降级；低于 ⇒ 查迁移表，缺迁移器也报错。依据：zcode 的 `CURRENT_SCHEMA_VERSION` + `UnsupportedProviderConfigVersionError`（`packages/provider-node/src/provider-config-file-codec.ts:12, 32-56`）。这是**唯一的迁移机制**，本 change 尚无历史版本所以迁移表为空。
- **元数据字段表**照 deepseek-harness 的 `WorkflowMeta`：`name`（kebab-case，display + persistence key）/ `description`（required）/ `when_to_use`（optional annotation）（`docs/subsystems/workflow.md:51`）。关键纪律继承自同一处：「元数据是**纯数据**，校验失败要在任何执行之前 loud reject，**绝不为取得元数据而求值任何文本**」（`docs/subsystems/workflow.md:13`）。

### D6 — 不重复造：复用清单

| 复用 | 来源 | 说明 |
| --- | --- | --- |
| 原子写 | `WorkflowStore._atomic_write`（`workflow_store.py:210-220`） | tmp + `os.replace`，读者永不见半截文件 |
| 段级路径白名单 | `WorkflowStore._validate_segment`（`workflow_store.py:41-44`） | 拒绝 `.`/`..` 与越界字符 |
| 内容指纹 / dedup | `WorkflowSpec.spec_hash`（`workflow.py:296-300`） | 同名同 hash = `unchanged` |
| 校验管线 | `parse_spec_for_manager` + `_spec_bounds`（`subagents.py:456-463`） | 资产加载与模型声明走**同一条**管线，不产生第二套校验 |
| 模板编译 | `compile_pattern`（`patterns.py:234-243`） | pattern 资产实例化 |
| spec 序列化格式 | `WorkflowSpec.to_dict()`（`workflow.py:279-294`） | 与 C5 的 `workflow_record.json` 共享格式 |

**明确不复用**：
- `.asterwynd/workflows/` subtree —— 该 subtree 的分离理由（result artifact vs checkpoint）同样适用于资产，资产是**第三个**命名空间（`workflow_store.py:5-16`）。
- benchmark 的 `workflow_record.json` —— 用途不同（观测/回归对照 vs 复用）。
- memory 的 dedup judge / decay / git 回溯 —— 无可信使用信号，且落点不提交（git 后端无载体）。

### D7 — 工具面与深度闸

4 个新工具（拟定名）：

| 工具 | read_only | 深度闸 | 说明 |
| --- | --- | --- | --- |
| `SaveWorkflowAsset` | False | **不进** `SPAWN_TOOL_NAMES` | 写盘 + 更新索引；输入 `workflow_id` + `name`/`description`，spec 由服务端取出 |
| `ListWorkflowAssets` | True | 不进 | 有界列表面 |
| `GetWorkflowAsset` | True | 不进 | 读单个资产正文（spec 或配方） |
| `RunWorkflowAsset` | False | **必须进** `SPAWN_TOOL_NAMES` | 按名载入 + 驱动调度器 |

`SPAWN_TOOL_NAMES` 现状为 `CreateSubagent`/`RunSubagent`/`RunPattern`/`ResumeSubagent`/`StartWorkflow`/`RunWorkflow`（`manager.py:423-430`），语义是「一次性拉起一张图/一次 spawn」。`RunWorkflowAsset` 与 `StartWorkflow` 语义等价，**必须一并纳入**，否则深度到限的子 agent 可以绕过图级上限——这正是「深度到限撤 spawn 工具」requirement 存在的理由，而该 requirement 的工具枚举是**写死的**（`openspec/specs/subagents/spec.md` 的「深度到限撤 spawn 工具」逐字列出 `StartWorkflow`/`RunWorkflow`），因此需要 MODIFIED。
`SaveWorkflowAsset` **不进**闸：保存不消耗并发也不起图，把它撤掉只会让深度到限的子 agent 无法保存自己刚跑完的图，而它并没有因此获得任何额外能力。

权限档位：4 个工具统一用 `SUBAGENT_CONTROL_PERMISSION`（与 `agent/tools/builtin/subagents.py` 现有工具一致）。`SaveWorkflowAsset` 是否需要更高的 `AGENT_STATE_PERMISSION` 档（照 `SaveMemoryTool`，`agent/tools/builtin/memory.py:57`）留作实现期确认项——见 Open Questions 尾注。

工具描述必须写进的**行为引导**（这是「模型会不会用」的关键，但**不是**可发现面，见 Q4）：在 `DeclareWorkflow`/`RunWorkflow`/`RunPattern` 的描述里加一句「从零声明拓扑前，先 `ListWorkflowAssets` 看有没有可复用的资产」。这是低成本的引导，不占系统提示 token，也不把本地文本提升为系统指令。

## Pre-Implementation Review

> 本 change 为架构级改造（新增跨会话持久层 + 新的加载信任边界 + 新工具面），实现前必须按 AGENTS.md 走 `batch-grill-me`（或等价独立零记忆 subagent 设计追问）审视本 design.md 的 D1–D7 与 Open Questions，逐项确认实现细节、依赖、风险、测试策略与文档影响，产出结构化决策记录到 `reviews/grill-design.md`，并经**停轮确认**（grill-confirmation-gate）：每条 Open Question 必须由用户答复并记录进 `## User Confirmation`。
>
> 本节只记录**决策相关的已定项**，完整追问记录以 `reviews/grill-design.md` 为准。当前已定的关键取舍：资产分两类载体由来源路径决定（D1）；落点作用域 = per-repo（D2，✅ Q1 已确认）；加载路径按「结构闸取 min + mode 只收窄」处理，并**明确区分**于 AutoGen 的 RCE 类风险（D3）；显式保存 + 内置名保留 + 同名覆盖可见化（D4）；运行时与设计时命名空间分离 + 单一版本迁移机制（D5）。
>
> **独立 grill 已完成（2026-09-26，reviewer run `grill-workflow-asset-persistence-20260926-r1`，零记忆 subagent）**，产出 10 条 Confirmed Decisions + 3 条新 Open Questions（Q7–Q9）+ 10 条风险，记录在 `reviews/grill-design.md`。其中**两条高严重度结论已由主 session 独立复现**（不采信转述，探针 `/tmp/myprobe2.py` 与 `/tmp/myprobe3.py`）：
> 1. **`mode` 钳制的比较基准错位，且方向 fail-open**（对应新 Q7）。`_clamp_mode` 读的 `manager.parent_mode_provider`（`agent/subagent/manager.py:1600-1603`）是**整个 manager 共享**的字段，每次构造子 `AgentLoop` 都被重写（`agent/loop.py:153-155`）。实测：root 会话已切到 `READ_ONLY`，一张声明 `mode: build` 的图**仍被授予 `build`**。D3(2) 与 Q5=B 的整个论证建立在「收窄是可靠的」之上，而按今天的基准它不可靠。
> 2. **钳制会改变 `spec_hash`，进而污染 `unchanged` 去重与 `previous_spec_hash`**（对应新 Q8）。`WorkflowSpec.to_dict()` 只在值**不等于模块默认**时才输出三个 limit 键（`agent/subagent/workflow.py:279-294`），`spec_hash` 取该 dict 的 canonical JSON（`:297-300`）。实测：声明 `max_runs: 5000` 在配置 300 下 hash 由 `5bb392f41782ea7b` → `d1130d802fff9a0b`；且**加载后重存会让资产永久遗忘自己声明过 5000**。
>
> 第一轮的 Q7–Q9 现已全部答复（见下）；第一轮结论中有 **4 条被第二轮订正**，见下方「第二轮」块。
>
> **独立 grill 第二轮已完成（2026-09-27，reviewer run `grill-workflow-asset-persistence-20260927-r2`，零记忆 subagent）**，产出 8 条 Confirmed Decisions + 2 条新 Open Questions（Q10/Q11）+ 10 条风险，已并入 `reviews/grill-design.md` 的「第二轮」分节（第一轮记录原样保留，未被覆盖）。**四条订正已被主 session 独立复现（不采信转述）**：
> 1. **mode 上限落点写错了对象。** D3 原写「挂 `_execute_run_in_context` 同一处即可」——该处**晚于**节点自身 mode 的冻结（`create_subagent` 在派发点 `_launch_run` 内调用），只能管到孙辈。主 session 双向对照实测（`/tmp/mine_landing.py`）：只挂 RUNCTX ⇒「只读会话 + build 节点」**仍授予 build（FAIL-OPEN）**；只挂 DISPATCH ⇒ 收窄为 `read_only` ✓。**已改**为必须挂派发点。
> 2. **Q8 的「三出口报值」前提不成立。** 实测 `status()` / `parent_envelope()` / `workflow_graph_snapshot()` **零命中**这三个限制值（主 session 复核：`limit-value hits=(none)`）——这是**新增字段**，不是订正既有假面。**已改**，并加了「禁止照『断言既有键』写测试」的实现警告。
> 3. **`_execute_run_in_context` 里不得用 `finally reset`。** 跨 context teardown 实测抛 `ValueError`（既有注释 `manager.py:999-1002` 已写明）；派发点是普通协程，set/finally-reset 才安全。**已补进 D3。**
> 4. **Q9 的 token 估算只在 ASCII 下成立。** 中文实测 2699 token，是 `SkillIndexSource.budget=2500` 的 1.08 倍（design 原文称「同一量级」，对中文不成立）。数字仍可接受（真闸是 20K 注入总预算），**已订正口径说明**。
>
> 另：**横向扫描（挑战 5）确认全仓只有 `parent_mode_provider` 一处同构缺陷**（`configure_runtime` 另两个参数在该调用点传 `None`，永不被覆写；`llm` 覆写同一对象、幂等无害）——**不需另立 issue**，但 #255 的范围需扩大（并入「会话上限通道」，见 Q11）。
> **两条新 Open Question（Q10 嵌套图 B 的口径、Q11 会话 mode 通道归属）尚未答复**，相关实现任务已阻塞（见 `tasks.md` 3.16）。

## Risks / Trade-offs

- **风险：资产带来新的绕过面（闸值）** → 加载路径强制 `min(声明值, 当前配置)` 并显式报 `limits_clamped`（D3）。**残余**：模型当轮声明路径是否也钳留作 Q2（推荐只钳加载路径，避免把回归面从「资产加载」扩到「整个 DSL 声明面」）。
- **风险：资产携带 `mode: build` = 持久化的写权限授予，而用户批准的是「一个名字」** → `mode` 只收窄不放宽 + 返回体列出「将以声明 mode 运行的节点」（D3）。
- **风险：资产自由文本经可发现面进入系统提示 = 提示注入** → 本机落点（本地写权限与仓库同信任级）+ 列表面有界 + 若采纳自动可发现面则只提升受格式约束的最小面（Q4 推荐）。**残余**：本机就是信任边界，恶意本地文件不在威胁模型内——这一点必须在文档里写明，不留给读者推断。
- **风险：节点级 `max_tokens`/`max_time_s` 同样无上界**（`workflow.py:601-614`），本 change **不钳制**。理由：图级四维预算（C4）与 C2 结构闸已对总消耗封顶，补节点级上限会**同时改变模型声明路径的既有语义**（`workflow-budget-unbounded-default` 确立的「默认不限、显式才限」精神），风险收益不匹配。**残余**：单节点可声明一个高于图级预算的额度——但它在图级预算处仍会被停掉，不自愈的只是「改了配置也不回溯生效」，记入已知欠债。
- **风险：同名覆盖不可恢复**（Q6 = 方案 A，已确认） → 覆盖返回体回 `previous_spec_hash` 并写事件日志；用户至少能看出「被改过」。
- **风险【高·grill 发现，已决 → 前置 issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)】：`mode` 钳制的比较基准错位且 fail-open。** 已由用户拍板走 contextvar 修复（Q7，见 D3(2)），并**立项为独立 bug issue #255**；本 change 把 #255 作为**前置阻塞项**处理——资产的 mode 批准面依赖它，**#255 未修前不得实现 D3(2) 的「列出将以声明 mode 运行的节点」**。残余风险：若 #255 的修复未能按预期落地，本 change 的 mode 相关实现必须停在「只记 diagnostics、不承诺列表正确」的降级口径上。
- **风险【高·grill 发现，已决】：钳制会改变 `spec_hash`（若不改口径）。** 已由用户拍板方案 C（Q8）：钳制不回写 spec，改为在 scheduler 读取处取 min，资产原文与指纹不被运行时配置污染。**残余风险**：所有对外报出限制值的出口（`parent_envelope` / `status()` / `workflow_graph_snapshot()`）必须一致报「实际生效值」，任何一个漏改都会造成「对内钳、对外报声明值」的假面 → 已入 tasks 的实现与测试项，逐出口断言。
- **风险【中·grill 发现，已收窄】：Q4=B 的注入面会把资产文本推进每个子 agent 的系统提示。** 已由 Q9 收窄为**只注入 root 会话**，并明确 `cacheable=False`（`agent/context/builder.py:129-142` 对 cacheable 源永不裁剪，误标会让资产列表无法被裁掉）。**残余风险**：root 会话每轮仍带约 **2.7K token**（中文实测，非原估的 ~1K）的资产索引；`budget` 是 advisory，真闸是 `total_budget = min(20_000, 20% × context_window)`，仍在界内。
- **风险【高·grill 第二轮，未决 → Q11】：「启动时快照发起会话 mode」在 scheduler 侧没有可用通道。** `WorkflowScheduler.run()` 只持 `self.manager`，而唯一能读到会话 mode 的通道 `manager.parent_mode_provider` **正是 #255 的污染源**。实测（`/tmp/probe_v7.py`）：同一会话（BUILD）连续两张图，`scheduler.run()` 起点两次快照到 `['build', 'read_only']`——**第二张被第一张污染**，其 `build` 节点静默降级。工具层同样读不到（只持 `self.manager`）。→ 归属见 Q11；若 #255 不提供该通道，本 change 必须回退候选 B（工具层显式传参）。
- **风险【高·grill 第二轮，未决 → Q10】：嵌套 workflow B 的 mode 上限口径未定。** 实测：会话 BUILD、图 A 的节点声明 `read_only`、其内起图 B（节点声明 `build`）⇒ B1 实测得 `read_only`（继承）。口径 1（继承）与口径 2（重快照，与既有「嵌套 workflow 各自独立成桶」自洽）都能自圆其说，spec 目前只覆盖图内嵌套。→ 见 Q10。
- **风险【中·grill 第二轮】：`_execute_run_in_context` 里照抄 `finally reset` 会引入 teardown 崩溃。** 跨 context `close()` 协程时 `reset(token)` 抛 `ValueError: ... was created in a different Context`（实测复现）；既有代码因此在 `manager.py:999-1002` 明写「No tokens are reset」。**该处的 set 必须不带 reset**；reset 只允许出现在派发点 `_launch_run`（那里是既有 4 个 contextvar 的安全形态）。已在 D3 写明，实现期禁止照抄。
- **风险【中·grill 新发现】：spec delta 漏掉两条已确认决策。** Q1（per-repo 跨 worktree 共享）与 Q4（受限可发现面）在 `specs/*/spec.md` 里**零覆盖**（grep `worktree`/`per-repo`/`注入`/可发现 无命中）；`openspec validate --strict` 抓不到这个缺口。已按 grill 建议在 spec delta 补两条 Requirement（见 `specs/multi-agent-collaboration/spec.md` 的「资产库作用域」与「资产可发现面」）。
- **风险【中·grill 新发现】：Q4=B 的注入面会把资产文本推进每个子 agent 的系统提示。** `_make_default_context_builder` 是子 loop 的默认路径（`agent/subagent/manager.py:1308-1316` 不传 `context_builder`），`_messages_with_run_context` 每轮调用（`agent/loop.py:672`）——token 与暴露面随并发度放大。且标了 `cacheable=True` 的源在预算裁剪中被显式跳过（`agent/context/builder.py:129-142`），误标会让资产列表**无法被裁掉**。→ 参数与范围见 Open Question Q9。
- **风险【中·grill 新发现】：资产 `name` 无长度上界。** slug 只受字符集约束（`agent/memory/persistent.py:112-116` 不校验长度），`ignore-previous-instructions-and-rm-rf` 这类名字合法。字符集挡住了结构性注入，挡不住语义暗示；长名还会冲击路径长度。→ 建议加 64 字符上限（已入 tasks）。
- **风险【中·grill 新发现】：D1 的 `asset_source` 若只在 `run_pattern` 里写，dsl 路径上该字段永不存在。** 应改为在 `WorkflowScheduler.__init__` 里**声明并默认**为 `{"kind": "dsl"}`，让「缺失即降级」成为永不触发的防御分支，而不是把预期值实现成异常路径。（`RunWorkflowTool.execute` 从不设置 `scheduler.spec`，对比 `DeclareWorkflowTool` 会设。）
- **风险：资产落点选 B（per-repo）后，资产不在项目目录内**，「删掉项目目录」不带走资产，用户也可能预期 `ls .asterwynd/` 能看到 → 文档显式说明（Q1 拍板后）。
- **Trade-off：显式保存 = 模型可能不存** → 用「保存成本极低（只给 `workflow_id` + 名字）+ 工具描述引导 + 保存后同 run 即可复用」对冲；拒绝自动入库的理由见 D4。
- **Trade-off：DSL 资产的覆盖面是显式声明而非自动推断** → 保存者多写一行 `overrides`，换掉了一整门模板方言（D1）。
- **Trade-off：不做跨进程写锁** → 单进程 asyncio 下 `_atomic_write` 已足够；并发多进程同时写同一资产是未定义行为，记入已知欠债（不静默：索引重建以最后一次原子写为准）。

## Open Questions

> 每条必须配具体场景，停轮交用户拍板后才进入实现（grill-confirmation-gate）。
>
> **状态：Q1–Q11 与两条实现期确认项已全部由用户拍板（Q1–Q9 + 两条实现期确认项于 2026-09-26；Q10–Q11 于 2026-09-27）**，逐条见下方各 Q 的「✅ 已确认」块。**立项阶段无未决 Open Question。** 完整答复记录见 `reviews/grill-design.md` 的 `## User Confirmation`。下述「方案 A/B/C」与推荐理由保留原文，便于回看取舍过程；**已确认的结论以「✅ 已确认」块为准**。
>
> **执行顺序（用户确认）：#255 → 本 change（#245）→ #246。** 本 change 的 **mode 相关任务依赖 #255**（不是「待确认」，是「依赖外部 issue」），在 #255 合入前不得标完成。
>
> **Q7 已整体重写**：用户给出了比原 A/B/C 选项更准确的语义模型，并把它立项为独立 bug issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)；原 A/B/C 描述已被取代（保留在 `reviews/grill-design.md` 第一轮记录里）。

### Q1 — 资产落点的作用域：per-checkout 还是 per-repo？

**场景**：用户在主仓库 `/home/happy/my-agent` 跑了一次 `workers=3` 的 orchestrator-worker，存成资产 `bug-sweep`。三天后为了改这个 change 切到 worktree `/home/happy/.paseo/worktrees/0frj3kg8/workflow-asset-persistence-2026-09-26`，新会话里说「扫一遍 bug」。

- **方案 A（`<workspace_root>/.asterwynd/workflow-assets/`，与 `WorkflowStore` 同域，per-checkout）**：worktree 里 `ListWorkflowAssets` 返回**空**——`bug-sweep` 不见了；在 worktree 里新存的 `tui-audit`，回到主仓库也看不到。两个目录各攒一套，用户可以接受这个语义（资产跟随 checkout）。
- **方案 B（`~/.asterwynd/projects/<hash>/workflow-assets/`，hash 来自 git common dir 的父目录，照 memory，per-repo）**：worktree 里 `RunWorkflowAsset(name="bug-sweep")` 直接命中，跑出来仍是新的 `wf_<uuid8>`、新的 `.asterwynd/workflows/<新 id>/` 结果目录。同一仓库所有 worktree 共享一套资产。
- **推荐 B**。理由：AGENTS.md 强制 worktree 开发，per-checkout 会让资产库静默碎片化；资产的全部价值是跨会话复用，作用域比 checkout 更细就兑现不了。代价：资产不在项目目录内（`ls .asterwynd/` 看不到），需文档说明；「删掉 checkout」不带走资产。

> **✅ 已确认（2026-09-26）：采纳方案 B。** 用户答复：资产落 `~/.asterwynd/projects/<hash>/workflow-assets/`，per-repo，所有 worktree 共享。因此 D2 的推荐落点即最终落点，构造器 `WorkflowAssetStore.for_workspace(workspace_root)` 按 git common dir 解析出 repo 根再取 hash 桶；文档需说明「资产不在项目目录内」。

### Q2 — 闸值钳制只作用于加载路径，还是也作用于模型当轮声明的 spec？

**场景**：资产 `big-fanout` 文件里写着 `"max_runs": 5000`；当前配置 `subagents.workflow.max_runs` 是默认 300（`agent/config.py:323`）。

- **方案 A（只钳加载路径）**：`RunWorkflowAsset(name="big-fanout")` 实际 `max_runs=300`，返回体 diagnostics 报 `limits_clamped: {max_runs: {declared: 5000, applied: 300}}`。**但**模型当轮手写 `RunWorkflow(spec={"max_runs": 5000, ...})` 仍是 5000——两条路径口径不一致，模型可能因此更愿意手写 spec 而不是用资产。
- **方案 B（两条路径都钳）**：`RunWorkflow(spec={"max_runs": 5000})` 也被钳到 300。口径统一，**但改变了既有行为**：今天模型可以声明 5000 并用满（`workflow.py:433-448` 的 `data.get(k, default)` 只在缺键时取配置值）。回归面从「资产加载」扩到「整个 DSL 声明面」，且与 `workflow-budget-unbounded-default` 确立的「默认不限、显式才限」精神需要额外调和（该精神针对的是预算闸，`max_runs` 是结构闸，两者语义不同）。
- **推荐 A**。理由：本 change 的最小正确边界是**消掉自己新引入的绕过面**，不是顺带收紧既有面；B 会显著扩大回归面与评审成本，且其收益（口径统一）不足以覆盖风险。建议把「模型声明路径是否也该钳」记为独立 follow-up。

> **✅ 已确认（2026-09-26）：采纳方案 A。** 用户答复：只钳资产加载路径；模型当轮声明路径行为**逐字不变**；「模型声明路径是否也该钳」记为**独立 follow-up**（不在本 change 范围内，需在 `docs/known-debt.md` 或后续 change 留痕）。
> **遗留绕过面（grill 追问 3 标出，见 `reviews/grill-design.md`）**：`GetWorkflowAsset` 取回 spec 后由调用方自己 `RunWorkflow(spec=...)` 手动重放，会绕过本钳制。按 Q2=A 的边界，**本 change 不堵这条**——它等价于「模型手写 spec」，而 Q2=A 已明确不收紧该路径。该绕过面的取舍需在 grill 记录里显式留痕。

### Q3 — DSL 资产是否引入覆盖面（可参数化）？

**场景**：用户跑了一次 `foreach` 展开 6 项的代码体检图（spec 里 `items: [{"name":"worker-0"}, ..., {"name":"worker-5"}]`），存成资产 `repo-health-check`。现在想换成 12 个目录。

- **方案 A（冻结 spec，无覆盖面）**：`RunWorkflowAsset(name="repo-health-check")` 只能原样重跑 6 项。想跑 12 项必须 `GetWorkflowAsset` 取回完整 spec、把 `nodes[0].items` 手改成 12 项、再 `RunWorkflow(spec=...)`——**正是本 change 要消灭的「模型重新生成拓扑」**，只是从「从零生成」退化成「复述 + 手改」，output token 成本与抄错风险都还在。
- **方案 B（显式覆盖面，推荐）**：保存时声明 `overrides: {"workers": ["items"]}`；调用时 `RunWorkflowAsset(name="repo-health-check", overrides={"workers": {"items": [12 个 item]}})`。覆盖在 `parse_spec_for_manager` **之前**应用，reducer 校验、环的可启动性校验、闸值上限全部照跑；覆盖未声明的 `(node, field)` 直接拒绝。代价：调用方要写完整 `items` 列表（比写个数字啰嗦）。
- **方案 C（配方化 DSL：foreach 声明 `item_template: "worker-{i}"` + 调用时给 `count`）**：调用时只给 `count=12` 最省 token。代价：引入「item 名模板」这门微方言——占位符语义、转义规则、与既有 `items` 字段的共存与互斥规则都要定，正是 issue #245 说要避免的。
- **推荐 B**。零新语法、复用既有校验管线、覆盖面由保存者显式声明所以不会意外改到不该改的地方。C 更省但把方言成本提前付了；B 落地后若实测 `items` 覆盖太啰嗦，再补 C 是纯增量。

> **✅ 已确认（2026-09-26）：采纳方案 B。** 用户答复：保存时声明 `overrides: {"workers": ["items"]}`，调用时传覆盖值；覆盖在 `parse_spec_for_manager` **之前**应用。未声明的 `(node_id, field)` 组合拒绝（`override_not_declared`）。

### Q4 — 资产是否需要自动可发现面（进入系统提示）？

**场景**：用户上周存了 `bug-sweep`，今天新开会话说「帮我扫一遍这个仓库的 bug」。模型此刻看不到任何资产存在的线索。

- **方案 A（只靠显式 `ListWorkflowAssets`）**：在 `DeclareWorkflow`/`RunWorkflow`/`RunPattern` 的工具描述里加一句「从零声明前先列一下资产」。**零额外 token 开销、零注入面**，但**没有强制力**——模型很可能直接开始声明新图，「后续会话可直接调用」这个核心目标大概率落空。
- **方案 B（自动注入可发现面，照 `MEMORY.md` 的做法）**：把资产索引摘要（每行 `- name — description`）注入系统提示或工具描述。收益：模型天然知道有什么可用，目标真正兑现。代价三连：①每个会话每轮都占 token；②资产攒多了要截断（memory 的 `MAX_INDEX_LINES=200`/`MAX_INDEX_BYTES=25_000` 是现成解法）；③**资产 `description` 是自由文本，进入系统提示即等于把本地文件文本提升为系统级指令**——这是本 change 最实质的提示注入面。
- **推荐 B 的受限形态**：只把**资产名列表**（`description` 若有则强制单行截断到 N 字符）注入到一个**标题明确、标注为「数据而非指令」的小节**；完整 `description` 只在显式 `ListWorkflowAssets` 时返回。理由：没有可发现面，本 change 的核心价值基本落空；但把自由文本无约束地提升到系统提示是真实风险，所以只提升受格式约束的最小面。
- 这条决定「资产层能不能兑现它的核心价值」，是本 change 最重要的产品问题。

> **✅ 已确认（2026-09-26）：采纳方案 B 的受限形态。** 用户答复：只把**资产名列表 + 单行截断的 description** 注入到一个**标题明确、标注「数据而非指令」的小节**；完整内容仍走显式工具（`ListWorkflowAssets`/`GetWorkflowAsset`）。
>
> **✅ 已确认（2026-09-26）· Q9 具体数字与范围**：列表面 **20 条**；`description` 截 **120 字符**；slug 上限 **64**；超限按 `name` 升序取前 N 并追加「还有 M 个资产未列出」。**范围：只注入 root 会话，不进子 agent**（子 agent loop 走同一默认 builder，见 `manager.py:1308-1316`）。**`cacheable=False`**。
> 数字口径说明（**grill 第二轮订正**，原按 ASCII 估算有误）：memory 的 `MAX_INDEX_LINES=200`/`MAX_INDEX_BYTES=25_000`（`agent/memory/persistent.py:34-35`）不适用——200 行规模明显超配。**中文实测**（`/tmp/probe_tokens.py`）：20 行 × (name ≤64 + desc ≤120 字符) 在**英文**下 3.5 KB / **659 token**，**中文**下 7.8 KB / **2699 token**——是 `SkillIndexSource.budget=2500`（`agent/context/sources.py:315`）的 **1.08 倍**、`MemoryIndexSource.budget=2000`（`:286`）的 1.35 倍。**结论仍可接受**：`budget` 是 advisory（`ContextBuilder` 从不读它，grep `\.budget` 在 `agent/context/builder.py` 零命中），真正的闸是 `total_budget = min(20_000, 20% × context_window)`（`agent/loop.py:1430-1432`），2699 远在界内。但**不得**再宣称「落在既有注入源预算同一量级」——中文口径下不成立。
**注**：`MemoryIndexSource` 标 `cacheable=True`（`sources.py:286`），与本 change 的 `cacheable=False` **相反**——这正是本 change 不能照抄它的原因（资产索引会被 `SaveWorkflowAsset` 在会话内改写）。
**注入小节里只放名字与截断后的 description**——不得把 `when_to_use` 或节点 `task` 带进注入面。

### Q5 — 资产里的 `mode` 字段允许到什么程度？

**场景**：用户存了一张资产，其中 `producer` 节点声明 `mode: "build"`（子 agent 能写文件）。三天后新会话里 `RunWorkflowAsset(name="producer-fix")`——父 agent 看到的只是一个名字，用户按名字批准。

- **方案 A（原样恢复）**：资产里的 `build` 原样生效。语义最直白（存什么跑什么），但**用户批准的是一个名字，实际被授予的是一次写权限**——批准面与实际能力面不重合。
- **方案 B（只能收窄，推荐）**：加载时 `mode` 不得放宽——当前会话/manager 允许的范围低于资产声明时**降级并记 diagnostics**，返回体显式列出「本资产将以其声明 mode 运行的节点」。
- **方案 C（禁止资产携带 `mode`）**：节点 mode 一律由当前会话决定。最保守，但太粗——一张全 `read_only` 的只读体检图是合法且常见的资产，强行剥掉 mode 会让它失去表达力。
- **推荐 B**：保留表达力，同时保证「只能更保守」，并把实际能力面摆到批准面上。

> **✅ 已确认（2026-09-26）：采纳方案 B。** 用户答复：只能收窄不得放宽；返回体列出「将以声明 mode 运行的节点」。
> **grill 追问 2 的修正（见 `reviews/grill-design.md`）**：本仓库已有 `_clamp_mode`（`agent/subagent/manager.py:1588` 一带，`create_subagent` 路径），所以「收窄」这层保护可能**已经免费继承**——本 change 的净新增可能只剩 diagnostics + 返回字段，而不是新增一条钳制逻辑。**且必须核实「资产加载天然继承这层保护」是否真的成立**：节点执行是否**全部**经过 `create_subagent`？`aggregate` 的 `strategy="llm"` 分支、`route` 节点是否走同一路径？**该核实结论直接决定 D3 这一条的体量**，已列为 grill 的必答项。

### Q6 — 同名覆盖时是否保留资产历史？

**场景**：`bug-sweep` 存的是 `workers=3`，用户觉得 3 个不够，改成 `workers=6` 再存一次（同名覆盖）。两天后想回到 3 个的版本。

- **方案 A（不保留历史，推荐）**：覆盖返回体回 `"action":"updated"` + `previous_spec_hash`，并把覆盖事件写进资产的事件日志。旧 spec **没有**副本可恢复——`.asterwynd/workflows/<wf_id>/` 里只有那次 run 的结果，且 C5 的 `workflow_record.json` 只在 benchmark 路径写（采集逻辑在 `benchmarks/workflow_replay.py`，写盘由 `benchmarks/agent_runner.py:638-650` 的 `AsterwyndRunner` 触发，普通会话不写）。
- **方案 B（保留历史）**：同名保存时旧文件移到 `<slug>.history/<timestamp>-<spec_hash>.json`（照 memory 的 `memory_dir/archive/` 形态）。可恢复，但引入「哪个版本是当前」的第二套语义，且历史目录会无界增长。
- **推荐 A**：资产是「当前可用的编排」而不是「版本化配置」；memory 之所以能做历史是因为它挂了 git 后端，而 `.asterwynd/`（或 `~/.asterwynd/projects/<hash>/`）不提交，没有等价物。代价（误覆盖不可恢复）由「覆盖事件可见 + `previous_spec_hash` 回传」部分对冲。

> **✅ 已确认（2026-09-26）：采纳方案 A。** 用户答复：不保留历史，回传 `previous_spec_hash` + 写事件日志。

> **✅ 已确认（2026-09-26）· 实现期确认项 1（权限档位）**：用户答复：取 `AGENT_STATE_PERMISSION`（照 `SaveMemoryTool`，`agent/tools/builtin/memory.py:57`），理由是资产属**跨会话状态层**，与 Q4=B（资产名进入系统提示，写入后果更重）耦合。注意这**偏离**了 `agent/tools/builtin/subagents.py` 现有 subagent 工具统一使用的 `SUBAGENT_CONTROL_PERMISSION`——`SaveWorkflowAsset` 因此是本组 4 个工具里权限档最高的一个。其余 3 个（`ListWorkflowAssets`/`GetWorkflowAsset`/`RunWorkflowAsset`）档位按读取/控制语义各自对齐（只读的走低档、`RunWorkflowAsset` 走 `SUBAGENT_CONTROL_PERMISSION`）。
>
> **✅ 已确认（2026-09-26）· 实现期确认项 2（工具命名）**：用户答复：就用 `SaveWorkflowAsset` / `ListWorkflowAssets` / `GetWorkflowAsset` / `RunWorkflowAsset`。

### Q7 — `mode` 收窄的比较基准错位（独立 bug issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)）

**背景（grill 第二轮发现，主 session 两轮探针实证）**：`_clamp_mode` 读的 `manager.parent_mode_provider` 是 manager 的**共享实例字段**（`manager.py:454`），唯一写入点是 `AgentLoop.__init__`（`agent/loop.py:153`）；子 agent loop 复用同一 manager（`manager.py:1303`），**每构造一个子 loop 就无条件覆盖它**。所以「当前会话允许的能力面」实际等于**最后构造的那个子 loop 的 mode**。

**场景（实测）**：用户在 BUILD 模式下开会话并跑过一张图（构造过子 loop），随后把会话切到只读模式，再调用一个节点声明 `mode: build` 的资产。
- **今天的行为（探针 `/tmp/myprobe2.py`）**：授予 `build` —— **用户在只读状态下被授予写权限（fail-open）**。反向也成立：BUILD 会话里 `read_only → build` 链式图的 build 节点被前序 read_only 兄弟**静默降级**，且该降级在同一会话内**粘滞**。
- **期望的行为**：有效 mode `E = min(声明的 M, 当前会话上限 R)`；上例中应为 `read_only`。

**用户给出的正确语义模型（三条）**：①每个节点在**声明期**配置 mode（现有代码已满足）；②运行时**不可改变**（`WorkflowNode` 是 `frozen=True`，已满足）；③有效 mode **不得超过当前会话的 mode**（意图正确，但现有实现读错了源）。

> **✅ 已确认（2026-09-26）：采纳 contextvar 方案（取代原 A/B/C 选项）。** 用户答复：mode 上限改走 **contextvar**，与 `workflow_id`/`node_id`/`graph_distance`/`bus` 同机制（`agent/subagent/context.py`）——scheduler 在派发点 set、`finally` reset，`create_subagent` 读。**快照语义**：workflow **启动时**快照 root 会话 mode 作为整轮上限，运行中途切换模式**不影响**本次 run。**嵌套语义**：节点 A 的有效 mode `E_A = min(M_A, R)`，A 派生的子孙上限为 `E_A`，**逐层收紧**。
>
> **主 session 实证（满足「不要只读代码下结论」的硬性要求，探针 `/tmp/probe_nested_mode2.py`）**：把该机制装到真实 manager 的既有挂点上并驱动真实的队列/任务/上下文传播，**全部通过**——grandchild 拿到的上限 = 父节点的**有效** mode（不是 root 的），并发兄弟**互不串味**。落地挂点与既有先例对称：`_execute_run_in_context` 已用同样手法安装 `set_spawn_depth`/`set_current_run_id`（`manager.py:991-1006`），队列的 `copy_context()` 在 **enqueue** 时捕获（`manager.py:884`），run 在**启动**时安装自己的值，故延迟执行的 run 也拿到正确上限。
>
> **本 change 的处置**：把 #255 作为**前置阻塞项**——资产的 mode 批准面依赖它。**前置未修前不得实现 D3(2) 的「列出将以声明 mode 运行的节点」**（基准错了，列表就是错的）。修复本身在 #255 内落地；本 change 只消费修复后的语义。

### Q8 — 钳制后的 `spec_hash` 口径

**场景（实测）**：资产 `big-fanout` 声明 `max_runs: 5000, max_nodes: 900`，配置 `subagents.workflow.max_runs = 300`。
- **原设计（把钳制写回 spec）**：`to_dict()` 会把「等于模块默认」的 limit 键**丢掉**，hash 由 `5bb392f41782ea7b` 变 `d1130d802fff9a0b`（**必变**）。连带三处失效：round-trip 断言在配置非默认时必红；`unchanged` 去重把「未变」误判为「已更新」并重写；**「加载后重存」让资产永久遗忘原声明值**。
- **期望的行为**：钳制不改动资产原文与指纹。

> **✅ 已确认（2026-09-26）：采纳方案 C。** 用户答复：钳制**不回写 spec**——在 **scheduler 读取** `spec.max_runs`/`spec.max_nodes`/`spec.recursion_limit` 的入口处取 `min(declared, config)`，`WorkflowSpec` 对象本身保持声明值不变。理由：保护 `spec_hash` 不受运行时配置影响。
> **附加硬性要求**：必须核实「scheduler 读取处取 min」覆盖**所有**读取路径——`parent_envelope` / `status()` / `workflow_graph_snapshot()` **对外报出的限制值必须与实际生效值一致**，否则又是一个假面（对内钳、对外报声明值）。已入 tasks 的实现与测试项。

### Q9 — 可发现面的具体数字与范围

**场景**：`ListWorkflowAssets` 默认页定 20，用户在同一个 repo 攒了 60 个资产，每个 description 平均 150 字符。
- **照搬 memory 口径**：200 行 × (名字 ≤64 + desc 150) ≈ 44 KB ≈ 11K token —— 是既有两个注入源预算之和（`MemoryIndexSource.budget=2000` + `SkillIndexSource.budget=2500`，`agent/context/sources.py:283/314`）的**两倍多**，明显超配。
- **收窄口径**：20 条 × (名字 ≤64 + desc ≤120) ≈ 3.9 KB ≈ 1K token，落在既有注入源的同一量级。

> **✅ 已确认（2026-09-26）：采纳 reviewer 的数字 + 收窄范围。** 用户答复：列表面 **20 条**；`description` 截 **120 字符**；slug 上限 **64**；超限按 `name` 升序取前 N 并追加「还有 M 个资产未列出」。**范围：只注入 root 会话，不进子 agent**。**`cacheable=False`**（`agent/context/builder.py` 对 cacheable 源永不裁剪）。
> **实现判据（grill 第二轮补充）**：「只注入 root」用 `current_spawn_depth() == 0` 可行——实测构造期 `spawn_depth`：root = 0、子 loop = 1（`/tmp/probe_rootonly.py`）。但 `_make_default_context_builder`（`agent/loop.py:1438-1454`）为 root 与子 loop **共用**（`manager.py:1303-1315` 不传 `context_builder`），故判据必须写在**源内部**。**更稳的做法**：由 `SubAgentManager._build_subagent_loop` 构造子 loop 时显式传一个 `include_asset_index=False` 之类的参数，把「是不是 root」变成**构造期事实**而非环境推断。

### Q10 — 嵌套 workflow（图 A 的节点里起图 B）的 mode 上限口径

**场景（grill 第二轮实测，`/tmp/probe_v3.py`）**：会话处于 **BUILD**；图 A 的节点声明 `mode: read_only`（例如只读体检节点）；该节点的 run 内又 `RunWorkflow` 起了新图 B，B 的节点声明 `mode: build`。实测在「上限装到派发点 + 经 `copy_context()` 传播」的实现下，**B1 的实际 mode = `read_only`**（继承 A 的有效上限，而非会话的 BUILD）。

- **口径 1（继承，逐层收紧）**：B1 上限 = `E_A` = `read_only`。与 D3(2) 的「A 派生的子孙上限为 E_A」字面一致，也与 spec 的「嵌套 spawn 逐层收紧」Scenario 一致。安全方向保守；代价是「只读体检节点顺手起的一张本该能写的图被**静默降级**」，且父只看到 A 的摘要、看不到 B 的降级原因。
- **口径 2（重快照）**：B 是**新图**、有自己的 `workflow_id` 与 spawn 桶（既有 spec 明确「嵌套 workflow 各自独立成桶」，`openspec/specs/subagents/spec.md:83-88`），故 B 按「启动时快照**当前**会话 mode」处理 ⇒ `B1 = build`。与既有配额语义自洽（配额独立，能力面是否也该独立？）；代价是 A 的收窄意图在 B 处失效，收窄的传递性被打断。

**倾向口径 1**：mode 上限是**能力面**而非配额，能力面应只随继承链收紧、不随命名空间重置；且口径 1 是当前实现的自然行为（零额外代码）。**但 spec 目前只覆盖「同一张图内」的嵌套**（Scenario 写的是「其下一个节点再派生子 agent」），两条口径都能自圆其说 → **需用户拍板并写进 spec**，否则实现期会照字面写出不稳定行为。

> **✅ 已确认（2026-09-27）：采纳口径 1（继承）。** 用户答复：嵌套 workflow 的 mode 上限**继承发起节点的有效 mode**——图 A 的 `read_only` 节点内起的新图 B，其节点上限 = `read_only`。理由：mode 是**能力面**而非配额，应只随继承链收紧。
> **对 spec 的影响（实现期必须落）**：spec delta 现有「嵌套 spawn 逐层收紧」Scenario 只覆盖**图内**（「其下一个节点再派生子 agent」），必须补一条覆盖**跨图**（节点内 `RunWorkflow` 起新图 B）的 Scenario，否则口径 1 无规格可依。已入 tasks 3.16。
> **已知代价（写进 Risks 可见）**：只读体检节点顺手起的一张「本该能写」的图会被**静默降级**，且父 agent 只看到 A 的摘要、看不到 B 的降级原因——这是口径 1 的既定取舍，不是缺陷。

### Q11 — 「发起会话 mode」的可读通道归 #255 还是本 change？

**场景（grill 第二轮实测，`/tmp/probe_v7.py`）**：同一 manager、同一会话（真实 mode 全程 BUILD、用户从未切换），顺序跑两张图。图 1 含一个 `read_only` 节点；图 2 的节点声明 `build`。实测图 1 跑完后 `manager.parent_mode_provider()` 已变成 `read_only`；**图 2 在 `scheduler.run()` 起点快照到的值是 `['build', 'read_only']`——第二次被第一张图污染**，图 2 的 `build` 节点被静默降级。

**问题实质**：`WorkflowScheduler.run()` 手上只有 `self.manager`；scheduler 侧唯一能读到会话 mode 的通道就是 `manager.parent_mode_provider`——**正是 #255 的污染源**。工具层同样读不到（4 个 workflow 工具只持有 `self.manager`，`agent/tools/builtin/subagents.py:563-572`）；真实 mode 在 `AgentLoop.runtime_state.current_mode` 里。

- **候选 A（通道归 #255，倾向）**：在 #255 里一并定义「会话上限通道」（例如 manager 上一个只由 root loop 写入、子 loop 不碰的字段，或由 root loop 设置的 contextvar），本 change 只消费。优点：本 change 直接改动既有运行路径仍是 1 处（pattern 溯源），符合 Q2=A 的最小边界。**风险**：#255 的验收面被扩大（从「换机制」变成「换机制 + 新增通道」）；若 #255 只做了前者，本 change 的快照会**静默读不到值**并退化成「上限 = None → 不收窄 → fail-open」。**要求：#255 的 acceptance criteria 必须显式写上「提供一个 scheduler 可读的会话 mode 通道」。**
- **候选 B（通道归本 change）**：`RunWorkflowAsset` 工具本就由 root loop 注册、能拿到 `runtime_state.current_mode`，加载资产时把它作为**参数**传给 scheduler。优点：快照点显式、可测、不依赖 #255 的通道设计。代价：scheduler 多一个构造参数，且「资产路径」与「模型声明路径」的 mode 基准来源分叉。

**倾向候选 A，但以「#255 acceptance criteria 显式包含该通道」为前置条件**；否则降级为候选 B。

> **✅ 已确认（2026-09-27）：采纳候选 A。** 用户答复：mode 上限的「发起会话」可读通道**由 #255 定义**，本 change 只消费。
> **前置条件（硬性）**：**#255 的验收标准必须包含「提供一个 scheduler 可读的会话 mode 通道」**。若 #255 只换了机制（contextvar）而未提供该通道，本 change 的快照会**静默读不到值**并退化成「上限 = None → 不收窄 → fail-open」——此时**必须回退候选 B**（本 change 从工具层把会话 mode 作为参数显式传给 scheduler）。
> **执行顺序（用户同时确认）**：**#255 → 本 change（#245）→ #246**。因此本 change 的 **mode 相关任务在 #255 合入前不得标完成**（见 tasks 3.15/3.16）——这是**依赖外部 issue**，不是「待确认」。

## Testing Strategy

按 TDD：先写测试，再实现。分层如下。

**1. 单元 / round-trip**
- pattern 资产：`compile_pattern("orchestrator-worker", params={"workers": 3})` → 保存 → 加载 → 断言 `spec_hash` 与直接编译结果一致；改 `params={"workers": 5}` 加载后 `foreach` 展开项为 5（**这条直接验证 D1 的核心论点**：配方保留参数化）。
- DSL 资产：`WorkflowSpec.to_dict()` 往返 + 覆盖面应用后仍能过 `parse_spec_for_manager` 完整校验。
- `spec_hash` 相同 ⇒ `SaveWorkflowAsset` 返回 `unchanged` 且**不写盘**（断言文件 mtime 不变）。

**2. 负向 / 安全（每条都要有对照的「合法路径必须成功」）**
- `unsupported_asset_version`：手写一份 `asset_schema_version: 99` 的文件 ⇒ 明确拒绝并给出可读 reason（**不是**静默忽略）。
- `reserved_name`：`SaveWorkflowAsset(name="bidding")` ⇒ 拒绝且提示可用命名。
- slug 越界：`../escape` / `a/b` / `A-B`（大写）/ 空串 ⇒ 全部拒绝；写入路径上的 symlink ⇒ 拒绝穿透。
- 坏文件容错：目录里混入非法 JSON、缺 `name`、半截文件 ⇒ `ListWorkflowAssets` 照常返回其余资产 + diagnostics。**必须区分三种状态**：全损坏 ⇒ `total == 0` 且 diagnostics **非空**且含被跳过文件计数；完全无资产 ⇒ `total == 0` 且 diagnostics **为空**；有健康资产 ⇒ 正常返回且 diagnostics 为空。**没有这个区分，「吞掉所有异常并返回空列表」的实现同样能通过。**
- 覆盖未声明的 `(node, field)`：`overrides={"workers": {"task": "..."}}` 而 `overrides` 白名单只有 `["items"]` ⇒ 拒绝（`override_not_declared`）。
- 覆盖后破坏既有不变量：把 `items` 覆盖成空列表 / 把 `max_items` 覆盖成负数 ⇒ 由既有 `parse_workflow_spec` 拒绝，错误信息自足。

**3. 信任边界（本 change 的净新增面）**
- **闸值钳制（Q8 = 方案 C）**：资产声明 `max_runs: 5000`、配置为 300 ⇒ 实际生效 300，且返回体有 `limits_clamped`；配置为 8000 ⇒ 实际生效 5000（**min 而非无条件取下限**）。对照：**模型当轮声明路径行为逐字不变**（回归锁，落在 Q2 的方案 A 上；注意既有 `test_spec_level_limits_override_defaults` 用 7/11 两个**小于**默认的值，挡不住「无差别压低」，必须补声明值**高于**配置值仍原样生效的用例）。
- **钳制不污染 `spec_hash`（Q8 的核心验收）**：声明 `max_runs: 5000, max_nodes: 900` 的 spec 在配置 300/200 下**加载后**，`spec_hash` **仍为** `5bb392f41782ea7b`（不被钳制改写）；且「加载 → 重存」后资产文件的字节与 hash 均不变（`unchanged`，不被误判为 `updated`，也不遗忘原声明值）。
- **对外报值与实际生效值一致（Q8 的假面防线）**：`parent_envelope` / `status()` / `workflow_graph_snapshot()` 三处报出的 `max_runs`/`max_nodes`/`recursion_limit` **必须等于实际生效值**（钳制后的），**不得**报声明值。逐出口断言——任一出口漏改即「对内钳、对外报声明值」的假面。
- **`mode` 收窄（Q7，前置依赖 #255）**：资产声明 `mode: build` + 会话为只读 ⇒ 降级为 `read_only`，返回体列出「以声明 mode 运行的节点」。**四条回归（双向 + 并发 + 嵌套 + 快照），每条都配「合法路径必须成功」的对照**：
  1. **fail-open 方向**：BUILD 会话跑过图 → 切 READ_ONLY → 加载声明 `build` 的资产 ⇒ 必须 `read_only`。**对照**：会话保持 BUILD ⇒ `build` 原样生效（证明不是无差别降级）。
  2. **并发时序**：并行节点 A(`read_only`) / B(`build`) 同时跑，两者的子 spawn 上限**各自正确**、互不覆盖。**对照**：单节点图上 `build` 正常生效（证明并发修复没把正常路径也压死）。
  3. **嵌套 grandchild**：A(`read_only`) 的孙 spawn 请求 `build` ⇒ 上限 = A 的**有效** mode 而非 root 的。**对照**：B(`build`) 的孙请求 `build` ⇒ 得 `build`（证明收紧不是全局一刀切）。**主 session 已用探针 `/tmp/probe_nested_mode2.py` 验证该机制可行**（grandchild 穿透 + 并发兄弟隔离 + 交错执行全部 PASS）；实现期须在**真实**挂点上重跑同形断言。
  4. **快照语义**：workflow **启动时**快照 root mode；运行中途切换 root 模式**不影响**本次 run 的已定上限。**对照**：下一次 workflow 启动时按**新**的 root mode 快照（证明"不影响本次"不是"永远不更新"）。
  - **测试盲区提醒**：`rg 'parent_mode_provider|_clamp_mode' tests/` 今天**零命中**——这四条全是净新增覆盖。
- **闸值不与既有测试冲突**：现有把 `recursion_limit`/`max_runs` 当参数的测试（`tests/agent/subagent/test_scheduler.py`、`test_workflow_budget.py` 等）**在模型声明路径上必须全部保持绿**。

**4. 集成 / 跨会话可用性（核心价值验证）**
- 用 fake LLM 起一次 `RunPattern(pattern="orchestrator-worker", params={"workers": 3})` → `SaveWorkflowAsset(workflow_id=…)` → **构造一个新的 `SubAgentManager` / 新 store 实例**（模拟新会话）→ `ListWorkflowAssets` 能看到 → `RunWorkflowAsset(name=…)` 能跑通、起出新的 `wf_<uuid8>`、结果落在新的 `.asterwynd/workflows/<新 id>/`。
- 断言资产本体**未被执行污染**：跑完之后资产文件的字节内容不变（照 CrewAI 的 fork 语义）。

**5. 工具面 / 深度闸**
- `RunWorkflowAsset` ∈ `SPAWN_TOOL_NAMES`：深度到限的子 agent 的工具注册里**没有**它（复用 `test_concurrency_queue.py` / `test_guardrails.py` 的既有断言风格）。
- `SaveWorkflowAsset`/`ListWorkflowAssets`/`GetWorkflowAsset` **不在**该清单里：深度到限的子 agent 仍能保存/列出（对照断言，防「顺手把所有新工具都塞进闸」）。
- `ListWorkflowAssets` 有界：造 300 个资产 ⇒ 返回体不超过配置上限且带 `total`/`truncated`（照 memory 索引的 `MAX_INDEX_LINES` 口径）。
- 命名空间隔离：`RunWorkflowAsset(name="wf_1a2b3c4d")` ⇒ 拒绝；`GetWorkflow(workflow_id="bug-sweep")` ⇒ 仍报未知 workflow（既有 `_unknown_workflow` 路径不变）。

**6. 入口层 / benchmark smoke（AGENTS.md 要求）**
- 本 change 触及 coding-agent 核心路径（工具协议 + subagent manager），**必须**跑至少一个 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`，断言不回归。
- 若涉及 CLI 入口（资产不在 CLI 暴露则跳过），跑 `uv run asterwynd run "…"` 冒烟。
- **不涉及** Web / TUI / browser，故不跑对应 smoke（在 tasks 里显式记为「不适用 + 理由」，不留空白）。

**7. 全量门禁**
- `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py` 三者全绿。
