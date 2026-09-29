# Proposal: 内置模板归一：RunPattern 融合进 Workflow DSL 入口（workflow-builtin-templates）

关联跟踪 issue：[#246](https://github.com/Xingkai98/asterwynd/issues/246)。前置关系：前置 #245（workflow-asset-persistence，已合入 PR #260）提供「配方」载体；前置 #255（mode 钳制，已合入）提供 `mode_ceiling()` / `effective_mode()`。依赖：无阻塞项。

## Change Type

- primary: refactor
- secondary:
  - subagent
  - tool-surface

## Why

`RunPattern` 与 `RunWorkflow` 底下跑的是**同一个 `WorkflowScheduler`**，差别只有入口形状与出口投影。四个 pattern 早在 `workflow-dsl-scheduler`（D7，已归档 2026-09-14）就降级成了 DSL 模板（`compile_pattern` → `WorkflowSpec`），`run_pattern()` 只是兼容 adapter（`agent/subagent/patterns.py:429-471`）。所以这不是「迁移」，而是**双入口收敛**——两个入口各自维护一套入参校验、一套出口投影、一份工具描述，而底下是同一张图。

现状的四条硬事实（已逐条读码核实）：

1. **入参形状差一个数量级。** `RunPattern(pattern, task, params)` 两个必填字段（`agent/tools/builtin/subagents.py:415-436`），`params` 由 Python 消费后展开进 spec（`_items(workers, "worker")` 生成 N 个 item，`max_rounds` 填进 route 的 `max_routes`，`patterns.py:61-231`）。`RunWorkflow(spec)` 要求模型手写整张 DAG——peer-review 一份 4 节点 + 6 条边 + route cases + `max_routes` 的 spec 是几百 token，且要过 `parse_workflow_spec` 校验，写错就 `WorkflowValidationError` 重试一轮。
2. **出口形状是两套。** `RunPattern` 走 `_legacy_result()` 返回 `{pattern, task, completed, failed, workers[], summary, selected, selector, workflow_id, workflow_spec_hash, critical_path_s, peak_active, total_cost, workflow_status}`（`patterns.py:376-426`），并额外挂 `bus = bus.snapshot_payload()`（`patterns.py:468`）。`RunWorkflow` 走 `scheduler.parent_envelope()`——bounded 节点投影，且**显式 `payload.pop("bus", None)`**（`agent/subagent/scheduler.py:3088-3102`，依据 D4「bus 是非权威广播通道，不该进父上下文」；docstring 逐字写着这句）。同一个调度器，两个出口各自演化。
3. **`OrcPattern` 接口与 `run_pattern` adapter 已被 spec 钉死。** `openspec/specs/multi-agent-collaboration/spec.md:70` 明文要求「四个 pattern SHALL 编译成 Workflow DSL templates…`run_pattern()` SHALL remain a compatible adapter」；`:135` 又钉了一遍返回字段。删 `RunPattern` 必然 MODIFY 这两条。
4. **模板参数化没有 spec 内表达。** `WorkflowSpec` 没有模板/参数概念——`foreach.items` 是**具体元组**（`_items()` 的产物）。pattern 的 `params` 是 Python 侧消费的。

**为什么是现在**：C1–C5 把「模型能自由编排 + 跑过的图可沉淀」做成了产品能力（#245 刚合入，提供 `recipe` 载体与加载协议）。此时收敛双入口，收益最直接：模型侧从「手写几百 token 的拓扑」降到两个必填字段；出错面从模型搬到代码（模板已被 `test_every_pattern_compiles_to_a_valid_spec` 钉了 round-trip 校验）；子 agent 工具集少一个名字、少一份工具描述；C5 的 `template` 臂对 `dynamic-record` 臂的差异收敛成纯粹的「谁生成 spec」。

## What Changes

- **删除 `RunPattern` 工具**（`agent/tools/builtin/subagents.py:415-451`），把「跑内置模板」并入 `RunWorkflow`：`RunWorkflow` 新增 `template` 入参（内置模板名，enum = 四个 pattern），入参形状为 **exactly one of `{spec, template}`**。`template` 路径要求 `task`（必填），`params` 可选。
  - 输入判别采用**显式互斥 + 结构化拒绝**（照 `pi` 的 `packages/coding-agent/examples/extensions/subagent/index.ts:443-509`「单工具多模式、按出现的参数判别、非法组合拒绝」的成熟形态）：给了 `spec` 又给 `template`、两个都不给、`template` 给了但缺 `task`、`template` 名字不在 enum —— 一律结构化拒绝，不静默取其一。
- **返回形状统一为 `parent_envelope()` 一处**（关键设计点，见 design.md D2）：`RunWorkflow` 无论走 `spec` 还是 `template`，父 agent 拿到的都是同一份 bounded 投影。`bus` **不再**出现在父上下文（对齐既有 D4 与 `parent_envelope` 的 docstring；也对齐外部一致实践——见 RIR）。`workers[]` / `selected` / `selector` 这些 pattern 专属的扁平字段消失，内容经 `nodes[]` 有界摘要 + `root_result_ref` / `GetWorkflow(detail='nodes')` 的 `result_ref` 按需读回（C3 既定「父 agent 永远 bounded」纪律）。
- **删除只为兼容 adapter 存在的死代码**：`run_pattern`、`_legacy_result`、`_workers_from_node`、`_worker_entry`、`_AGGREGATE_NODE_IDS`（`patterns.py:246-252, 314-471`）。**保留** `compile_pattern` / `PATTERNS` / `OrcPattern` / `_template_*`——它们是模板本体的编译入口，被 `RunWorkflow` 的 template 路径、#245 的 pattern 资产路径、C5 benchmark 的 template 模式三处共用。
- **与 #245 归一（关键设计点，见 design.md D4）**：内置模板 = 随代码走的配方，用户资产 = 随 workspace 走的配方。两者共用**同一个** `compile_pattern` 编译入口与同一套参数处理；`recipe` 是二者共同的概念名（#245 的 `WorkflowAsset.recipe = {pattern, params, task}`，`agent/subagent/workflow_assets.py`）。本 change 落一个共享 helper，使「模板引用 → 编译 → 校验 → 调度」只有一条路径。
- **spec 契约 MODIFY**（见下方 Capabilities）：`multi-agent-collaboration` 的「Orchestration Pattern Library」与「内置编排模式降级为 DSL 模板」两条 Requirement 必须改写（去掉 `run_pattern()` adapter 条款，改钉统一入口）；`subagents` 的「深度到限撤 spawn 工具」工具枚举去掉 `RunPattern`；`agent-runtime` 的「编排结果中的 bus 快照有界」主体从已删的 `RunPattern` 改挂到仍存在的 bus 出口；`web-ui` 的 Workflow 视图触发列表去掉 `RunPattern`。
- **深度闸零额外工作**：`RunPattern` 与 `StartWorkflow`/`RunWorkflow` 都已在 `SPAWN_TOOL_NAMES`（`agent/subagent/manager.py:424-435`），合并后剥掉一个名字，语义不变（合并进来的 `template` 路径仍在 `RunWorkflow` 名下，照旧受闸）。

## Capabilities

### New Capabilities

无新能力域；在既有能力域上收敛入口与出口。

### Modified Capabilities

- `multi-agent-collaboration`:
  - **MODIFIED**「Orchestration Pattern Library」：去掉「`run_pattern()` SHALL remain a compatible adapter」，改为「四个 pattern SHALL 经统一 Workflow 入口的 `template` 输入编译并执行」。
  - **MODIFIED**「内置编排模式降级为 DSL 模板」：返回字段条款（`workflow_spec_hash` 等）改挂在统一 bounded envelope 上，不再描述 pattern 专属扁平结构。
  - **ADDED**「统一 Workflow 入口的模板输入」：`template` 与 `spec` 互斥、非法组合结构化拒绝、模板由代码内注册表编译、未知模板名拒绝。
  - **ADDED**「编排入口返回单一的 bounded 投影」：父 agent 得到的形状不随入参变化；`bus` 不进该投影；内容经 refs 按需读。
- `subagents`:
  - **MODIFIED**「深度到限撤 spawn 工具」：spawn 工具枚举去掉 `RunPattern`（该名字不再存在）；`RunWorkflow` 语义扩展为同时承载 spec 与 template 输入，仍在闸内。
- `agent-runtime`:
  - **MODIFIED**「编排结果中的 bus 快照有界」：约束主体从「`RunPattern` 返回体」改为「仍暴露 bus 的模型面出口」，并明确父 agent 的 workflow 结果投影不携带 `bus`。
- `web-ui`:
  - **MODIFIED**「workflow 运行态流程图视图」：触发工具列表去掉 `RunPattern`（保留 `StartWorkflow`/`RunWorkflow`）。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据——架构级改造（收敛模型面工具入口 + 改写既有 spec 契约 + 触碰父 agent 结果投影这一跨切面契约），且走 grill 的非平凡 change。**不为省事走 exempt**：本 change 直接改工具面与 spec 契约，须完整 RIR。
- research questions:
  1. 参考实现里，「命名模板/preset + 参数」与「模型手写动态 spec」是**同一个工具**还是**分开的工具**？若同一个，入参如何判别？
  2. 当一个工具接受多种入参形态时，它返回**一种稳定形状**还是**随入参变化的形状**？后者会坏在哪？
  3. 模板/配方编排 vs 动态编排，父 agent 各收到什么形状（扁平摘要 vs bounded 投影）？
  4. 有没有类似 Asterwynd `bus` 的「非权威广播/草稿通道」？它会不会作为结果状态交给父 agent？
  5. 模板参数化在这些系统里放在哪——**Python/配置拥有的配方展开**、模型手写的模板加占位符语言、还是 spec 本身？

- findings:

  **第一层：本地参考仓库**（`/home/shared/agent-study/reference-repos/`，六个仓库全部可用；逐条附 `file:line`。**CodeGraph 不可用**——外部仓库无 `.codegraph/` 索引，改用 ripgrep + 直接读源码）

  - **`deepseek-harness`（权重最高）——固定模板与动态脚本是**两个工具、两种各自的稳定 envelope**。** `packages/workflow/tool-workflow` 只接受 `meta`/`script`/`args`/`run_in_background`，**没有任何 template/preset 参数**；前台成功恒渲染 `{kind:'foreground', runId, agentsStarted, result}`，`maxResultChars`（默认 50000）只界模型面投影（`tool-workflow/README.md`「Calling the tool」/「Durable session records」；`packages/workflow/tool-workflow/src/types.ts`）。固定拓扑编排在**另一个包** `packages/workflow/tool-ralph`：deployment 拥有的固定脚本，调用 schema 只有 `{objective, maxRounds?}`，返回稳定 `{status, rounds, last report}`；其 README 明说 *"The loop is a deployment-owned fixed script: the model supplies data only and cannot alter the loop, provider route, schema, or handoff validation"*。**即：deepseek 把「固定模板」与「模型手写动态」拆成两个工具、两个各自稳定的 envelope，没有合一。**
  - **`deepseek-harness` — preset 是 session 组合概念，不是工具入参，模型够不着。** `packages/preset/agent-preset-registry`：preset 是声明式 YAML 条目列表（`src/definition.ts:5-11` 的 `PresetDefinition`，`definition.ts:18-38` 的 `entryListProblem` 做形态校验），按 session 选定并持久化（`src/session.ts:20-29`），README「Model Experience」写着 *"Preset selection — What the model sees: Nothing directly"*。**不存在「preset 或 spec」二选一的工具。**
  - **`deepseek-harness` — 唯一的「模板展开」在声明层且不求值。** `packages/preset/agent-preset-registry/src/composition-inventory.ts:60-74`：唯一的表达式形态是 `!!js` 的 `disabled` 谓词，由 **loader 在它自己的上下文里**求值；未挂载时拒绝并把该行报为 `'conditional'` 而非猜。**没有任何模型文本被求值，没有通用占位符语言。**
  - **`deepseek-harness` — 父 envelope / 通道纪律。** 父 agent 拿的是 bounded 投影而非子 transcript：`packages/subagent/subagent/src/projection-types.ts:9-19` 把父可见的 `SubagentCatalogEntry` 定为 `{id, createdAt, mode, label}`；`assistant-output.ts:1-11` 父选中的是「最后一条非空 assistant 消息」，与 run 内部无关；`tool-subagent/README.md`「Foreground result」：*"Success contains only the child's final text… Intermediate child steps stay out of the parent."*。**没有任何广播/草稿通道被暴露给父 agent。**
  - **`kimi-code` — 最接近「模板 + 参数 → 展开」的工具 `AgentSwarm`，且返回一种 envelope。** 入参（`packages/agent-core-v2/src/features/swarm/tools/agent-swarm/agent-swarm.ts:9-58`）：`description`/`subagent_type?`/`prompt_template?`/`items?`（≤128）/`resume_agent_ids?`/`fork?`/`model?`。展开：单一 token `{{item}}`（`PROMPT_TEMPLATE_PLACEHOLDER`，`:6`）被各 item 字面替换（`agentSwarmTool.ts:239-284`）。**在任何 subagent 启动之前**强制校验（`agent-swarm.md:7`）：items ≥2（除 resume）、有 items 则必须给 template 且 template 必须含 `{{item}}`、展开后的 prompt 必须两两不同。结果对**所有**入参形态是**一种形状**（`renderSwarmResults`，`agentSwarmTool.ts:296-329`）：`<agent_swarm_result><summary>…</summary><resume_hint>…</resume_hint><subagent agent_id item outcome>…</subagent></agent_swarm_result>`。**`AgentSwarm` 与单数 `Agent` 是两个工具**，不存在手写图 spec 模式。中间推理**刻意不进父历史**（`docs/en/customization/agents.md`）。
  - **`codex` — 每个形状一个独立工具；固定配方工具返回一个固定 envelope。** 工具集 `spawn_agent` / `spawn_agents_on_csv` / `report_agent_job_result` / `send_input` / `wait_agent` / `list_agents` / `close_agent` / `interrupt_agent`（`codex-rs/core/src/tools/handlers/multi_agents_spec.rs:47-317`）。`spawn_agents_on_csv` 是固定配方工具（`agent_jobs.rs:36-47`）：入参 `{csv_path, instruction, id_column?, output_csv_path?, output_schema?, max_concurrency?, max_workers?, max_runtime_seconds?}`；描述（`agent_jobs_spec.rs:65`）：*"The instruction string is a template where `{column}` placeholders are replaced with row values… This call blocks until all rows finish and automatically exports results."* 返回**一个固定 envelope**（`SpawnAgentsOnCsvResult`，`agent_jobs.rs:57-65`）：`{job_id, status, output_csv_path, total_items, completed_items, failed_items, job_error, failed_item_errors}`。参数化位置明确：**固定命名数据集（CSV）+ 封闭占位符集（`{column}` over 声明的列）+ output schema——从不是模型手写的 DSL。**
  - **`pi` — 唯一的「单工具多模式」先例。** `packages/coding-agent/examples/extensions/subagent/index.ts` 是**一个** `subagent` 工具、三种模式，按**出现的参数**判别（`:443-468`）：单发 `{agent, task}`、并行 `{tasks:[…]}`、链式 `{chain:[…]}`；模式经 `modeCount`（`:493-509`）推导，非法组合拒绝。**但三种模式全是配方**（命名 agent + prompt），**没有**「整张 spec」模式；结果是模式相关的（单发文本 vs 每任务结果数组），每任务 50 KB 封顶、*"full results remain in tool details"*（README「Output Display」/「Limitations」）。
  - **`opencode`** — `packages/opencode/src/tool/task.ts`：单个 `subagent_type` + `prompt`（从不是 spec/模板）。前后台两条路径**同一个**渲染形状（`renderOutput`，`:64-79`）：`<task id state><summary>…</summary><task_result>…</task_result></task>`；后台注入同样的形状（`:68-95`）；返回子 agent 最后一段文本（`:65`）。
  - **`zcode` — 无相关发现。** 唯一命中「presets」的 `packages/ui/src/app-shell/workflow-artifacts/presets/index.ts` 是 UI **artifact 渲染器**注册表（chart/table/metrics/board 视图模型），与编排工具入口无关。**记录「无相关实现」本身是发现**：该仓库不做编排模板 vs 动态 spec 的工具面。

  **第二层：业界实践（附真实 URL）**

  - **「预设/配方」与「动态编排」在场上是分开暴露的。** LangGraph 把 prebuilt（`create_react_agent`/`create_agent`）与自定义 `StateGraph` 作为**分开的入口**；指导口径是「先用 prebuilt，需要自定义控制流（分支/循环/并行/HITL/持久化）再降到 graph API」——一条**渐进抽象**规则，而非一个接受「preset 名或图」的工具（[LangChain custom workflow](https://docs.langchain.com/oss/javascript/langchain/multi-agent/custom-workflow)、[Thoughtworks Radar](https://www.thoughtworks.com/pt-br/radar/languages-and-frameworks/langgraph)）。
  - **「单工具按入参吐不同 schema」是记录在案的 MCP/function-calling 坑。** FastMCP issue #4280：判别联合的 tag 若不是 `required`，会让工具 schema 接受后端会拒绝的输入（`union_tag_not_found`）——**「感知到的工具行为」与「实际行为」分叉**（[PrefectHQ/fastmcp#4280](https://github.com/PrefectHQ/fastmcp/issues/4280)、[FastMCP json_schema 文档](https://gofastmcp.com/python-sdk/fastmcp-utilities-json_schema)）。Anthropic API 拒绝顶层 `oneOf`/`anyOf`/`allOf` 的 `input_schema`，强迫扁平对象（[gitlab-mcp#29](https://github.com/structured-world/gitlab-mcp/issues/29)）；被丢掉的 `allOf`/`anyOf` 分支会让参数不可满足（[rmcp-openapi#99](https://gitlab.com/lx-industries/rmcp-openapi/-/work_items/99)）。**标准的缓解是：每个变体一个显式扁平对象 + 一个 `required` 字段里的 `const` 判别 + `additionalProperties:false`**——即**入参相关形状只在有一个显式、诚实的判别子时可接受**。
  - **工具数/重叠的指导倾向「重叠真实存在时就合并」。** 超过约 15–18 个工具后准确率急降；「minimal means minimal overlap」，重叠/含糊的工具让 agent 选错（[arXiv 2605.24660](https://arxiv.org/html/2605.24660v2)、[How many tools should an MCP server expose](https://www.strayspark.studio/blog/how-many-tools-should-mcp-server-expose-token-budget)、[Consolidate agent tools](https://github.com/agentpatterns-ai/website/blob/main/tool-engineering/consolidate-agent-tools.md)）。
  - **广播/消息总线通道不是父 agent 的结果状态，且是更难的形态。** Anthropic 的多 agent 指导把 **Message Bus** 列为「hard to debug/trace events」的 cloud-scale 形态，并推荐 **Orchestrator-subagent** 作为默认起点（[Anthropic multi-agent coordination patterns](https://github.com/oakoss/agent-skills/blob/main/skills/agent-patterns/SKILL.md)、[Building Effective Agents 摘要](https://raw.githubusercontent.com/alirezadir/Agentic-AI-Systems/033b69f4b13c902b1fd80cfeba02093208db5df9/03_system_design/anthropic-build_effective_agents.md)）。bounded 投影设计普遍只返回子 agent 的最终产出、要么截断带检索句柄、要么溢出到按 id 读的侧通道（[gptme#3007](https://github.com/gptme/gptme/pull/3007)、[windmill#10416](https://www.cubic.dev/pr/windmill-labs/windmill/pull/10416)）。
  - **模板参数化是「代码/配置拥有、加载期校验」，从不是 eval。** Ema 的 agent catalog：`agent_type` 选执行路径，`agent_config.type_config` 带类型专属配置，输入按节点的 `input_schema` 校验（fail-fast 422），prompt 的 `Instructions.{{input.field}}` 占位符按 payload-rooted 契约解析（[Ema Agent Reference](https://builder.ema.ai/builder/v2/agent-reference)）。

- design impact:
  - **D1（统一入口的入参判别）**：没有任何参考实现在「preset vs spec」上做单工具双形状——最接近的类比全是**两个工具、各一个稳定 envelope**（deepseek `workflow`/`ralph`、LangGraph prebuilt/custom、kimi `Agent`/`AgentSwarm`、codex `spawn_agent`/`spawn_agents_on_csv`、opencode `task`）。本 change 的收敛**仍有据**——两个 Asterwynd 工具确实驱动同一个 `WorkflowScheduler`，且工具重叠指导倾向合并——**但证据要求：合并要用一个诚实的判别子 + 一种返回形状，而不是两种入参相关形状**。`pi` 的单工具多模式（显式按参数判别、非法组合拒绝）是入参判别的直接形态模板；MCP 文献给出判别子必须显式且 `required` 的硬约束。
  - **D2（返回形状与 `bus`）**：**证据一边倒地支持「单一 bounded 投影 + 从父上下文去掉 `bus`」**。这正是 Asterwynd 自己的 D4 教义（`parent_envelope` 的 docstring 与 `payload.pop("bus")`），与全部外部先例一致（deepseek/kimi/opencode/pi 均只给子 agent 最终产出、不含中间通道），且 Anthropic 把 message-bus 列为不适合做默认结果面的难调试形态。注意现状的不对称是真的：`_legacy_result` 注入 bus（`patterns.py:468`）而 `parent_envelope` pop 掉它（`scheduler.py:3102`）——**收敛按 pop 一侧解决**。`bus` 在 run **内部**仍可用（`PublishBusMessage`/`ReadBus` 工具，`subagents.py:250-364`），只是不再作为结果键。
  - **D3（模板参数化位置）**：**证据支持参数化留在 Python（配方层 / pattern 资产），不要往 spec 里塞模板/占位方言**。每个参考实现都把「模板 + 参数 → 展开」表达为**代码/配置拥有、占位符集封闭且预先校验的配方**：kimi `{{item}}`（单 token、必填、启动前强制两两不同）、codex `{column}` over 声明的 CSV 列 + `output_schema`、deepseek ralph = 固定脚本（参数在 deployment 配置里、不在调用 schema）、Ema `type_config` + `input_schema` 加载期校验。**没有一个把参数化放进动态 spec，也没有一个接受带通用展开/求值规则的模型手写模板。**
  - **D4（与 #245 归一）**：Asterwynd 已有正确的容器——`compile_pattern` 在 Python 里展开 `{workers|teams|proposers|max_rounds|worker_max_tokens}` 成具体 `WorkflowSpec`，资产层已把这条臂命名为 `recipe`（`source:"pattern"` → `recipe`）。所以「spec 格式没有模板概念」的答案是**不要加**：统一工具的模板形态就是 `template=<内置名>` + `params=<封闭类型对象>`，在**校验之前**编译成具体 spec，与今天一致。#245 的 `ALLOWED_OVERRIDE_FIELDS` 封闭子集与 `_apply_asset_overrides`（`subagents.py:1097-1128`）已经示范了这条门槛：**零新方言、对既有字段直接赋值、覆盖后重新校验**——模板机制必须达到同一门槛。
  - **反向证据（须写进 design 的权衡）**：kimi 与 codex **确实**让模型手写模板串，但两者占位符语法都是**单一固定 token**、展开是**字面替换**、且结果在**任何工作开始前**被校验（required token、两两不同、封闭列集）——它不是 DSL、没有 eval。若本 change 想要模型手写 prompt 模板，那是可接受的形态；但本 change 明示的安全姿态（DSL 受限可校验、不执行模型生成代码）指向**连这个都不做**：`template` 保持为**服务端配方的引用**，而非模型手写的字符串。

## Impact Analysis

- **能力域**:
  - `multi-agent-collaboration`: 「Orchestration Pattern Library」与「内置编排模式降级为 DSL 模板」两条 MODIFIED；新增「统一 Workflow 入口的模板输入」「编排入口返回单一 bounded 投影」两条 ADDED。
  - `subagents`: 「深度到限撤 spawn 工具」的**工具枚举** MODIFIED（去 `RunPattern`）。
  - `agent-runtime`: 「编排结果中的 bus 快照有界」的约束主体 MODIFIED（`RunPattern` 已不存在）。
  - `web-ui`: 「workflow 运行态流程图视图」的触发工具列表 MODIFIED（去 `RunPattern`）。
- **代码**（实现期细化；下述为已核实的影响面）:
  - `agent/subagent/patterns.py`：**删除** `run_pattern` / `_legacy_result` / `_workers_from_node` / `_worker_entry` / `_AGGREGATE_NODE_IDS`；**保留** `compile_pattern` / `PATTERNS` / `OrcPattern` / `_template_*` / `_items` / `_worker_budget` / `_AGGREGATE_INSTRUCTION`。模块 docstring 需改写（现 docstring 逐字描述 `run_pattern` 的返回形状，`patterns.py:11-16, 18-22`）。
  - `agent/tools/builtin/subagents.py`：**删除** `RunPatternTool`（`:415-451`）；`RunWorkflowTool`（`:834-884`）扩展 `template`/`task`/`params` 入参 + 互斥校验 + 模板编译分支；`_template_recipe()` 共享 helper（与 `RunWorkflowAssetTool` 的 pattern 分支共用，`:1196-1207`）。
  - `agent/loop.py`：工具注册列表去掉 `RunPatternTool`（`:62, 398`）。
  - `agent/subagent/manager.py`：`SPAWN_TOOL_NAMES`（`:424-435`）去掉 `"RunPattern"`。
  - `agent/subagent/bus.py`：`snapshot_payload()` **不落笔**（界照旧，仍是唯一加固点）；仅其 docstring 里「模型面调用点是 `RunPattern`」的措辞需订正（`:208-215`）。
  - `agent/tools/builtin/subagents.py` 的 `_asset_from_scheduler` / `SaveWorkflowAsset`（`:905-1005`）**不落笔**：它们读 `scheduler.asset_source`，而 `asset_source` 的写入点当前**只有** `run_pattern`（`patterns.py:457-462`）。`run_pattern` 删除后，`asset_source` 的写入点须迁到 `RunWorkflowTool` 的 template 分支（否则「保存刚跑过的 pattern 图为 recipe 资产」这条 #245 能力会静默退化成 DSL 资产——**这是本 change 最容易漏的连带影响**）。
  - **不改**：`agent/subagent/scheduler.py`（`parent_envelope` / `_envelope` 逐字不动）；`agent/subagent/workflow.py`；`benchmarks/agent_runner.py`（C5 的 `template` 模式直接调 `compile_pattern`，不经过任何工具，`:505-529`）；`agent/subagent/workflow_assets.py`（资产 schema 不动）。
- **测试**:
  - 删除/改写：`tests/agent/subagent/test_patterns.py`（断言 `RunPattern` 扁平返回，`:188`）、`tests/agent/subagent/test_pattern_templates.py` 的 5.2 段（`:171-300` `run_pattern` 兼容字段）、`tests/agent/subagent/test_bus_bounded_exports.py`（出口 2 = `run_pattern` 的 `result["bus"]`，`:173-216`）、`tests/agent/subagent/test_bounded_envelope.py`（`:208-213`）、`tests/web_tests/test_workflow_node_transcript.py`（出口 4 经 `run_pattern`，`:895-932`）、`tests/agent/subagent/test_guardrails.py`（`:62, 191`）、`tests/agent/subagent/test_concurrency_queue.py`（`:34, 39, 522, 653`）。
  - 新增：`RunWorkflow` 的 `spec`/`template` 互斥校验（四种非法组合各一条）；`template` 路径编译出的图与 `compile_pattern` 逐字一致（round-trip）；`template` 路径返回体 == `spec` 路径返回体形状（键集相等）；父投影不含 `bus`；`template` 路径的 `asset_source` 溯源（回归 #245 的 recipe 资产）；深度到限时 `RunWorkflow` 仍被撤。
  - 回归：全量 `uv run pytest -q` 绿 + `openspec validate --all --strict` + artifact checker。
- **文档**（已 grep 核实逐个文件；`RunPattern`/`run_pattern` 在 `docs/` 下命中 7 个文件）:
  - `docs/openspec-change-backlog.md`：本 change 条目 + 并行批次（与 #261 并行，仅本文件可能冲突）。
  - `docs/agent-internals.md`（1 处，`:1029` 工具清单树）：去 `RunPatternTool`、补 `RunWorkflow` 的 `template` 入参。属文档地图入口文档。
  - `docs/interview-script/run-pattern-web-demo.md`（**整份文件以 `RunPattern` 命名**，8 处）：这是实测多 Agent 编排的 web demo 指南，工具名与 `subagents.py` 行号引用均会失效——需整体改写为 `RunWorkflow(template=…)` 口径（或判为历史债务另记，但**必须显式决定**，不能静默留错）。
  - `docs/interview-script/walkthrough/W03-multi-agent.md`（2 处）、`docs/interview-script/questions/Q08-multi-agent.md`（1 处，bus 出口叙述）：多 agent 讲稿，按建议性维护约束检查更新。
  - `docs/interview-bullets/walkthrough.md`（14 处，工具清单 + 调用路径走读）、`docs/interview-bullets/interview-prep.md`（1 处，bus 两条出口叙述）：讲稿/要点，同上。
  - `docs/architecture.md`：如列举 subagent/workflow 工具清单，需去 `RunPattern`。
  - `README.md` + `README_EN.md`：如工具清单被列出，需同步。
  - **关键文档影响检查项**：`openspec/specs/multi-agent-collaboration/spec.md`、`openspec/specs/subagents/spec.md`、`openspec/specs/agent-runtime/spec.md`、`openspec/specs/web-ui/spec.md` 的改动属受保护 artifact，须在 `workflow-events.jsonl` 落结构化解释事件（实现阶段）。
  - **工具数量事实会变**：`docs/interview-bullets/interview-prep.md` 与 `walkthrough.md` 里的「10 个 spawn 工具 / 工具清单」叙述随 `RunPattern` 退役变为 9，需一并订正（这是本 change 收益之一的对外口径）。
- **不影响**:
  - benchmark 三模式（`template`/`dynamic-record`/`dynamic-replay`）与 `workflow_record.json` 语义不变——C5 template 臂直调 `compile_pattern`。
  - `StartWorkflow` / `DeclareWorkflow` / `GetWorkflow` / `CancelWorkflow` 行为逐字不变。
  - #245 的 4 个资产工具（Save/List/Get/RunWorkflowAsset）**schema 与有效输入的语义**不变（除 `RunWorkflowAsset` 与 `RunWorkflow` 共用编译 helper 的重构）。**R2/Q3 订正**：`RunWorkflowAsset` 的 pattern 分支**同步享受**按模板封闭的键校验（拒绝该模板无效的键）——这是本 change 自己的 Non-Goal 措辞收紧，**不违反 #245**（#245 无「资产工具对外行为不变」承诺，且显式把模板归一划给 #246）。
  - `workflow_id` 生成、per-run 结果落点、scheduler 的 `_envelope`/`parent_envelope` 内容不动。
  - 内置 4 个 pattern 的编译结果（模板本体）逐字不变。

## 与既有 change 的边界

- **#245（workflow-asset-persistence，已归档 2026-09-28）**：它负责「运行中产出的编排如何沉淀与复用」（磁盘资产 + 4 个资产工具），本 change 负责「内置模板与动态 spec 如何收敛成一个入口」。二者在 `recipe` 概念与 `compile_pattern` 编译入口上归一，但本 change **不**新增/删除资产工具，也**不**改资产 schema。（是否把 `RunWorkflowAsset` 也并入统一入口，见 design.md 的 Open Questions。）
- **`workflow-dsl-scheduler`（已归档 2026-09-14）**：它的 D7 把 pattern 降级为模板并**保留** `run_pattern()` 兼容 adapter，理由是当时「不牺牲自由、兼容既有测试」。本 change 正是撤销那条兼容条款——D7 的技术前提（pattern 已是模板）不变，变的只是「要不要继续维护第二套出口」。
- **`benchmark-workflow-replay`（C5，已归档）**：`template` 臂不经工具，本 change 不影响其对照口径；反而使 `template` 臂 vs `dynamic-record` 臂的差异收敛为纯粹的「谁生成 spec」。
