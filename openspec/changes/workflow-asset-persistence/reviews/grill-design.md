# Grill: workflow-asset-persistence 设计追问

## Reviewer

- **run id**: `grill-workflow-asset-persistence-20260926-r1`（reviewer 自署）；paseo agent id `b1d9c281-55c2-4fda-8201-0b12796051ef`（零记忆独立评审者，与主 session 无共享上下文）
- **时间**: 2026-09-26
- **审视对象**: `openspec/changes/workflow-asset-persistence/design.md` 的 D1–D7 与 Testing Strategy，对照 `proposal.md`、`tasks.md`、`specs/multi-agent-collaboration/spec.md`、`specs/subagents/spec.md`，以及真实实现代码
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-asset-persistence-2026-09-26`，分支 `workflow-asset-persistence/2026-09-26`，HEAD `369d99d731134c8c817e505ad198b70dee6afa57`（基线 master 369d99d）
- **工作区状态**: change 目录为 untracked；`docs/openspec-change-backlog.md` 有未提交改动。reviewer 未修改任何文件（本文件除外），未写任何实现或测试代码
- **评审方法（零记忆独立复核，非转述）**:
  - 读码核实：`agent/subagent/scheduler.py`（3054 行全文相关段）、`manager.py`、`workflow.py`、`patterns.py`、`workflow_store.py`、`agent/tools/builtin/subagents.py`、`agent/memory/persistent.py`、`agent/context/{builder,sources}.py`、`agent/loop.py`、`agent/tool_permissions.py`、`agent/run_config.py`
  - 用 `grep -c "pattern" agent/subagent/scheduler.py`（结果 = 1，且是无关注释）独立复核 D1 的「scheduler 上无 pattern 溯源字段」
  - 写了一次性探针脚本 13 个（全部放 `/tmp`，未落仓库），实跑验证：envelope 污染（`/tmp/probe1.py`）、mode 收窄全路径（`probe2.py`）、spec_hash 与钳制（`probe3.py`）、`parent_mode_provider` 归属（`probe4.py`）、资产往返丢声明（`probe5.py`）、同图混合 mode 的兄弟节点（`probe6.py`）、无 monkeypatch 复现（`probe7.py`）、`run_pattern` 返回键集与配方不可还原（`probe8.py`）、生产形态 root `AgentLoop`（`probe9.py`）、跨 run 粘滞（`probe10.py`）、fail-open 方向（`probe11.py`）、配方可由 `spec_hash` 校验（`probe12.py`）、钩子对 `spec_hash` 的稳定影响（`probe13.py`）
  - 机械检查：`awk`/`python3` 逐条验证 6 条 Requirement 正文**首个非空行**是否含 `SHALL`；实跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
  - 回归实跑：`uv run pytest -q` 针对 `test_snapshot_does_not_drift_envelope_contract`、`test_envelope_contract_does_not_drift`、`test_run_pattern_keeps_legacy_fields_and_adds_new_ones`、`test_spec_level_limits_override_defaults`、`test_create_subagent_clamps_mode_to_parent`，5 passed

## Confirmed Decisions

- **决策**: D1「附加字段写在 scheduler 上不会污染 `_envelope`/`parent_envelope`」成立，且既有回归锁不会因此变红。
  理由: `_envelope` 是**显式挑字段**的 dict 字面量（`agent/subagent/scheduler.py:2938-2989`），`parent_envelope` 从 `_envelope()` 出发做节点投影（`scheduler.py:3000-3022`），全文件无 `vars()`/`__dict__`/`dataclasses.asdict` 全量导出；`WorkflowScheduler` 无 `__slots__`，故附加属性可写。实跑探针在 `scheduler.asset_source` 赋值后断言：`asset_source in envelope` → False、`in parent` → False、`in json.dumps(parent)` → False（`/tmp/probe1.py`）。两个具名回归测试用的是**超集/成员断言**而非逐字节断言（`tests/agent/subagent/test_workflow_graph_snapshot.py:374-385` 用 `set(envelope["nodes"][0]) >= {...}`；`tests/agent/subagent/test_workflow_graph_snapshot_additions.py:283-292` 同），加属性在结构上不可能使其变红；实跑 5 passed。
  来源: probe1 + scheduler.py:2938-2989/3000-3022 + 两个测试文件的行号

- **决策**: 「资产加载天然继承 `_clamp_mode` 保护」这句话在**调用链意义上为真**——节点执行不存在绕过 `create_subagent` 的路径。
  理由: `manager.run_subagent` 的签名里**根本没有 mode 参数**（`agent/subagent/manager.py:724-734`），所以不存在「把 mode 直传给 run_subagent」的通路；scheduler 侧 `manager.create_subagent` 的**唯一**调用点是 `_launch_run`（`scheduler.py:2119`），而 `mode` 进入 `_launch_run` 的入口恰好三处，与主 session 的初步观察一致：`_execute_subagent`（`scheduler.py:1711-1715`）、`_execute_aggregate` 的 `strategy == "llm"` 分支（`:1733-1738`）、`_run_foreach_item`（`:1886-1890`）。`route` 节点**不起 run**（`_execute_route` 只算 targets，`scheduler.py:1760-1801`）；`aggregate` 的 `strategy="collect"` 分支**不起 run**（`_execute_aggregate` 在 llm 分支后直接走 `_merge_contributions_bounded` 并置 `status="completed"`，`:1749-1757`）；foreach 展开项**共用容器节点的 mode**（`_run_foreach_item(node, ...)` 收到的是容器 `node`，`scheduler.py:1865-1890`）。实跑探针：READ_ONLY 父模式下四种起 run 的节点（subagent / foreach 项 / aggregate-llm）`create_subagent` 的 effective mode 全部回落为 `read_only`（`/tmp/probe2.py`）。
  来源: probe2 + manager.py:724-734 + scheduler.py:1711/1733/1886/2119/1760-1801

- **决策**: 「闸值取 min 而非无条件取下限」在 `_resolve_limits` 的真实语义下可成立；给 `parse_workflow_spec` 增可选 `limit_ceiling` 不会破坏任何既有调用方。
  理由: `_resolve_limits` 是 `data.get(k, default)`——**只在缺键时**用配置默认值，声明值照单全收（`agent/subagent/workflow.py:433-448`），`_positive_int` 只要求 `int >= 1`、**无上界**（`workflow.py:451-455`）。实跑：声明 `max_runs: 5000` 被完整接受；`min(5000, 300) = 300`，`min(5000, 8000) = 5000`（`/tmp/probe3.py`）。全仓 `parse_workflow_spec(` 的**生产**调用点只有两个：`OrcPattern.compile`（`agent/subagent/patterns.py:279-280`，不传 kwargs）与 `parse_spec_for_manager`（`agent/tools/builtin/subagents.py:466-468`，传 `**_spec_bounds`）；新参数为 keyword-only 且带默认值时二者均不受影响。
  来源: probe3 + workflow.py:433-455 + patterns.py:280 + subagents.py:468

- **决策**: Q3（overrides 拒绝语义）、Q5（mode 收窄）、Q6（覆盖事件 + `previous_spec_hash`）三条已拍板决策在 spec delta 中**都有**对应的 Requirement/Scenario。
  理由: Q3 → `specs/multi-agent-collaboration/spec.md:80-85`「Scenario: 未声明的覆盖面被拒绝」（含 `override_not_declared` 与「SHALL NOT 静默忽略」），且拒绝语义同时写进 Requirement 正文 `:64`；Q5 → `:119-125`「Scenario: 节点 mode 只收窄不放宽」（含降级 + diagnostics + 返回体列节点 + SHALL NOT 放宽）；Q6 → `:138-143`「同名同 spec_hash 判为未变更」与 `:145-150`「同名不同内容判为覆盖并回传旧指纹」（含 `previous_spec_hash` 与事件日志）。Q2（只钳加载路径）由 `:112-117`「模型当轮声明的 spec 行为不变」覆盖。
  来源: 逐条 grep + 读 `specs/multi-agent-collaboration/spec.md`

- **决策**: spec delta 的 6 条 Requirement 全部满足「正文首个非空行含 `SHALL`」的 strict validate 硬约束，OpenSpec strict validate 实跑全绿。
  理由: 逐条以脚本取 `### Requirement:` 之后第一个非空行判定，6/6 `SHALL_OK`（`multi-agent-collaboration` 5 条分别落在正文行 7 / 40 / 64 / 96 / 129，`subagents` 1 条落在行 7）。实跑 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → `Totals: 29 passed, 0 failed (29 items)`，含 `✓ change/workflow-asset-persistence`。
  来源: python3 逐条 SHALL 扫描 + openspec 1.4.1 实跑输出

- **决策**: 资产里的节点 `mode` **永远无法授予 BYPASS**，枚举面本身就把上限锁死在 `{build, read_only, plan}`。
  理由: `_parse_node` 对 `mode` 只接受这三个字面量，越界直接 `WorkflowValidationError`（`agent/subagent/workflow.py:492-496`）；`AgentMode.BYPASS` 不在枚举内，因此任何资产都无法表达 bypass 能力面。这是 D3(2) 论证里未被写出、但实际存在的一层结构性保护。
  来源: workflow.py:492-496 + `agent/run_config.py:20-34`（AgentMode 枚举）

- **决策**: `SaveWorkflowAsset` 用 `AGENT_STATE_PERMISSION`（用户已拍）在只读会话下**不会静默写盘**，行为与 `SaveMemoryTool` 一致，不构成新的权限漏洞。
  理由: `READ_ONLY_CAPABILITIES` 含 `AGENT_STATE`（`agent/tool_permissions.py:97-101`），但 `AGENT_STATE_PERMISSION` 的 `risk_level = MEDIUM`（`:125-128`）高于 `read_only_default` 的 `auto_approve_max_risk = LOW`、等于其 `approval_required_max_risk = MEDIUM`，按 `ModePolicy.decide_tool` 落入 `REQUIRE_APPROVAL` 分支（`agent/run_config.py:130-146`）。这与既有 `SaveMemoryTool`（`agent/tools/builtin/memory.py:57`）完全同档同行为。
  来源: tool_permissions.py:97-101/125-128 + run_config.py:130-146 + memory.py:57

- **决策**: 「`run_pattern` 返回结构必须逐字不变」目前**没有被键集锁钉住**，本 change 必须补一条。
  理由: 既有测试 `test_run_pattern_keeps_legacy_fields_and_adds_new_ones`（`tests/agent/subagent/test_pattern_templates.py:175-197`）只逐个断言字段存在 + 一条 `"spec_hash" not in result`，**没有** `set(result) == {...}` 形式的键集断言；实跑确认 `run_pattern` 实际返回 13 个键（`bus/completed/critical_path_s/failed/pattern/peak_active/summary/task/total_cost/workers/workflow_id/workflow_spec_hash/workflow_status`，`/tmp/probe8.py`）。因此「不改返回结构」目前只是实现约束，没有机械护栏。
  来源: probe8 + test_pattern_templates.py:175-197

- **决策**: D1 的「配方不可还原」这一立论成立，且存在一条**比改 scheduler 更好的第三条路**（把配方写进 manager 侧按 `workflow_id` 索引的 dict）。
  理由: 实测 `run_pattern` 返回体里 **没有 `params` 键**，`scheduler` 上也没有任何 `asset_source` 属性；能拿到的只有 `scheduler.spec`（展开后 spec），配方与 params 确已丢失（`/tmp/probe8.py`）。第三条路可行：探针证明 `compile_pattern(pattern, task, params)` 对同一配方是**确定性的**，重编译得到的 `spec_hash` 与当次实际运行的 `spec_hash` **逐字相同**，而伪造的配方会得到不同 hash（`/tmp/probe12.py`）；因此无论配方记在 scheduler 还是 manager，都能用 `spec_hash` 交叉校验真实性。
  来源: probe8 + probe12 + patterns.py:234-243/429-461

- **决策**: `tests/agent/subagent/test_scheduler.py` / `test_workflow_budget.py` 一类「把 `recursion_limit`/`max_runs` 当参数」的测试，作为 Q2=A 的既有回归锁是**真实存在**的，但它锁的是「声明能覆盖配置」而非「声明无上界」，不足以证明模型声明路径逐字不变。
  理由: `test_spec_level_limits_override_defaults`（`tests/agent/subagent/test_workflow_spec.py:330-334`）断言声明 `recursion_limit=7, max_runs=11` 被采纳——这确实会被「两条路径都钳」的实现打破，是一条有效护栏；但它使用的值都**小于**配置默认（25 / 300），因此一个「对所有声明值无差别取 `min(declared, default)`」的错误实现也能通过。真正需要补的是一条**声明值高于配置值仍不被钳**的对照用例（今天没有）。
  来源: test_workflow_spec.py:330-334 + 实跑

## Open Questions

> 以下三条需要用户拍板（产品/范围决策），reviewer 无法单方定论。每条附本 change 真实场景的具体例子。不确认不进入实现（grill-confirmation-gate）。

- **Q7**: 资产的「`mode` 只收窄」以**谁的能力面**为基准？本 change 是修掉基准本身，还是只做 diagnostics 并记欠债？

  **我的实测发现（不是推测）**：`_clamp_mode` 比较的 `parent_mode` 来自 `manager.parent_mode_provider`（`agent/subagent/manager.py:1600-1603`），而这个 provider 是**整个 manager 共享的一个字段**，每次构造子 `AgentLoop` 时被**重写**（`agent/loop.py:153-155` → `manager.configure_runtime(parent_mode_provider=lambda: self.runtime_state.current_mode)`，`agent/subagent/manager.py:544-545`）。于是「当前会话允许的范围」实际上等于**最后构造的那个子 loop 的 mode**，而不是发起该 workflow 的那个会话的 mode。

  **具体例子（实测，`/tmp/probe9.py`、`probe10.py`）**：用户在 BUILD 模式下发一张图，节点声明 `ro(mode=read_only) → bw(mode=build)`（链式，ro 先跑）。实测结果：
  - `ro` 的会话 mode = `read_only` ✔（符合预期）
  - `bw` 的会话 mode = **`read_only`** ✘ —— 一个明确声明 build 的节点被前面那个 read_only 兄弟节点**污染降级**了；root loop 的 mode 自始至终是 BUILD。
  - 更严重：该 run 结束后 provider **粘滞在 READ_ONLY**，此后同一会话里一张**全 build** 的图（`/tmp/probe10.py` 第 2 次 run）也被整体降级为 read_only，而用户根本没改过模式。

  **反方向同样成立（fail-open，`/tmp/probe11.py`）**：先跑一张含 build 节点的图（provider 变成 BUILD），然后用户切到 READ_ONLY（`runtime_state.set_mode(READ_ONLY, source='user')`），再跑一张声明 `mode: build` 的图 —— 实测**授予了 BUILD**，即用户在只读状态下被授予了写权限。

  **为什么这条对本 change 特别要命**：内置 4 个 pattern 模板**不声明任何 `mode`**（`_template_orchestrator_worker` 等，`agent/subagent/patterns.py:80-231`），所以 pattern 路径绕过了这个 bug；但本 change 的 DSL 资产**恰恰以保留显式 `mode` 为卖点**（D3(2)、Q5 方案 B），是把这条路径放到台面上的那一类输入。而 D3 承诺的「返回体列出『将以声明 mode 运行的节点』」在今天的基准下会列出**错的基准**。

  **候选**：
  - **方案 A（本 change 修）**：让 mode 基准回到「发起该 workflow 的会话」。最小改法是把 workflow 的 mode 作为参数穿过 `_launch_run` → `create_subagent`（或在 `register_workflow` 时快照一次当前 provider 值挂在 scheduler 上，`_launch_run` 优先用它）。代价：触碰既有运行路径（与 D1 的「唯一一处改动」口径冲突），且需要一条回归锁同时覆盖「兄弟节点不互相污染」与「跨 run 不粘滞」。
  - **方案 B（本 change 不修，只留痕 + 降级口径）**：D3 的 mode 条只保留 diagnostics + 返回字段，并把「基准不精确」写进 `docs/known-debt.md` 与本节；同时**必须**在 spec 里把口径改成不依赖歧义基准的措辞（例如「不得**放宽**」定义为「不得授予高于发起会话的 mode」并显式说明该比较基准已知不精确）。风险：`RunWorkflowAsset` 的返回体列表会误导批准面。
  - **方案 C（本 change 只修 fail-open 方向）**：仅在 `_launch_run` 处对 `node.mode` 与**当次会话** mode 取 min（不依赖 provider），不修「兄弟污染」的过严方向。代价：一处改动兼顾安全方向，过严方向记欠债。

  **我倾向 A 或 C**：fail-open 方向（只读会话授予 build）是安全方向，不应带着它进资产层；而 D3 的整个立论就是「批准面 = 能力面」，基准错会让这条立论落空。

- **Q8**: 闸值钳制后，资产里存的 `spec_hash` 是**声明值**的 hash 还是**应用值**的 hash？`unchanged` 去重按哪个比？

  **具体例子（实测，`/tmp/probe5.py`、`probe13.py`）**：资产 `big-fanout` 文件里写着 `"max_runs": 5000, "max_nodes": 900`，配置 `subagents.workflow.max_runs = 300`。
  - 保存时 `WorkflowSpec.to_dict()` 会把 `max_runs`/`max_nodes` 原样写进 spec（`agent/subagent/workflow.py:279-294` 只在**等于模块默认**时才省略该键），`spec_hash` = `5bb392f41782ea7b`。
  - 加载时若按 D3 在 `_resolve_limits` 解析后取 `min`，得到 `max_runs=300 / max_nodes=200`。此时 `to_dict()` 认为它们**等于默认值**，于是**把这两个键整个丢掉**，`spec_hash` 变成 `d1130d802fff9a0b` —— 与存盘值**不等**。
  - 直接后果一：design 的 Testing Strategy §1「pattern 资产：… 断言 `spec_hash` 与直接编译结果一致」在配置值 ≠ 模块默认值时**必然变红**。实测三组：配置 300（= 默认）→ hash 稳定；配置 100 → hash 从 `f5753e7ff3855502` 变 `68d3abf2af851782`；配置 1000 → 变 `89f5215946743cd6`（`/tmp/probe13.py`）。
  - 直接后果二：D4 的 `unchanged` 判据（同名同 `spec_hash` 不写盘）会因此**误判为 `updated`**，把资产重写一遍，并顺带**永久丢掉**它曾经声明过 `max_runs: 5000` 这件事——下次配置调大到 8000 时，资产已经只记得 300。

  **候选**：
  - **方案 A**：`spec_hash` 一律按**声明值**计算（钳制只发生在执行期读取 `spec.max_runs` 处，或在 `WorkflowSpec` 上并存 `declared_limits` / 执行期用副本），资产原文与 hash 都不被钳制污染。
  - **方案 B**：`spec_hash` 按**应用值**计算，接受「保存后立刻加载再保存」会从 `unchanged` 变成 `updated`，并在文档里写明「钳制会改写资产的 hash」。
  - **方案 C**：钳制不回写 spec，改为在 scheduler 读 `spec.max_runs` 的三处入口做 min（`scheduler.py:753` 的桶校准等），`WorkflowSpec` 保持原文。

  **我倾向 A 或 C**：资产是**声明**的持久化载体，让「保存的字节」与「计算出的指纹」因运行时配置而漂移，会让 Q6 的 `previous_spec_hash` 也变得不可信；且方案 A/C 能让 §1 的 round-trip 测试恢复成一条干净的断言。

- **Q9**: Q4 注入面的**具体数字**（资产条数上限、description 截断长度）与**注入范围**（是否也对每个子 agent 注入）？

  **具体例子**：`ListWorkflowAssets` 默认页大小定 20；用户在同一个 repo 攒了 60 个资产，每个 description 平均 150 字符（中文约 1 字符 = 3 字节）。
  - 若照 memory 索引的 `MAX_INDEX_LINES=200` / `MAX_INDEX_BYTES=25_000`（`agent/memory/persistent.py:34-35`）照搬：200 行 × (名字 ≤ 64 + desc 150 + `- ` + ` — `) ≈ 44 KB ≈ 11K token —— 是既有两个注入源预算之和（`MemoryIndexSource.budget = 2000`、`SkillIndexSource.budget = 2500`，`agent/context/sources.py:283/314`）的**两倍多**，明显超配。
  - 若取 20 条 × (名字 ≤ 64 + desc ≤ 120) ≈ 3.9 KB ≈ 1K token，落在既有注入源的同一量级。
  - **另一层必须一并拍板**：注入点若做成 `ContextSource` 注册进 `AgentLoop._make_default_context_builder`（`agent/loop.py:1438-1454`，与 `MemoryIndexSource` / `SkillIndexSource` 并列），而**子 agent 的 loop 也走同一默认 builder**（`manager._build_subagent_loop` 不传 `context_builder`，`agent/subagent/manager.py:1308-1316`），那么这 20 行会进入**每一个子 agent 的系统提示**，且随并发度线性放大 token 消耗与注入暴露面。
  - **第三层**：`ContextBuilder` 对 `cacheable=True` 的源**永不裁剪**（`agent/context/builder.py:129-142` 的 `_find_trimmable_index` 跳过 critical + cacheable）。`MemoryIndexSource` 因会话内会被 `SaveMemory` 改写而刻意**不标 static/cacheable**（`sources.py:285-287`）。资产同理会被 `SaveWorkflowAsset` 改写，若误标 cacheable，则不仅内容陈旧，还会**永久占据**系统提示且无法被预算裁掉。

  **候选**：
  - **方案 A（我推荐）**：条数上限 **20**（与 `ListWorkflowAssets` 默认页大小同源）、description 单行截断 **120 字符**、名字长度上限 **64 字符**；源标 `cacheable=False`（每轮重渲染）；**仅对 root/session loop 注入**，子 agent loop 不注入。
  - **方案 B**：只对 root loop 注入但条数放宽到 50、desc 截到 200 字符（更接近 memory 口径，代价是多 ~2 倍 token）。
  - **方案 C**：所有 loop 都注入（含子 agent），条数与 desc 用方案 A 的值。收益是子 agent 也能发现资产，代价是 token 与暴露面按并发度放大。
  - 超出上限时的截断策略我建议固定为「按 `name` 升序取前 N，末尾追加一行 `[还有 M 个资产未列出，调用 ListWorkflowAssets 查看]`」——排序确定性可测，「还有 M 个」让模型知道该翻页而不是以为只有 20 个。

## User Confirmation

> 回填规则：`- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`。

**第一批（design.md 的原始 Open Questions + 两条实现期确认项）——已由用户拍板：**

- **Q1**: 用户答复：采纳方案 B——资产落在 `~/.asterwynd/projects/<hash>/workflow-assets/`，per-repo，同一仓库的所有 worktree 共享一套资产库；因此资产不在项目目录内，需在文档里说明。；确认时间: 2026-09-26
- **Q2**: 用户答复：采纳方案 A——闸值钳制只作用于资产加载路径（`RunWorkflowAsset`），模型当轮声明 spec 的路径行为逐字不变；「模型声明路径是否也该钳」记为独立 follow-up，不在本 change 范围内。；确认时间: 2026-09-26
- **Q3**: 用户答复：采纳方案 B——DSL 资产保存时显式声明覆盖面（如 `overrides: {"workers": ["items"]}`），调用时传入覆盖值，覆盖在 `parse_spec_for_manager` 之前应用；未声明的 `(node_id, field)` 组合一律拒绝。；确认时间: 2026-09-26
- **Q4**: 用户答复：采纳方案 B 的受限形态——只把「资产名列表 + 单行截断的 description」注入到一个标题明确、标注「数据而非指令」的小节；完整内容仍走显式工具（`ListWorkflowAssets`/`GetWorkflowAsset`）。；确认时间: 2026-09-26
- **Q5**: 用户答复：采纳方案 B——资产里的节点 `mode` 只能收窄不得放宽；返回体必须列出「将以声明 mode 运行的节点」。；确认时间: 2026-09-26
- **Q6**: 用户答复：采纳方案 A——同名覆盖不保留历史；返回体回传 `previous_spec_hash`，并把覆盖事件写进资产的事件日志。；确认时间: 2026-09-26
- **Q6-附（实现期确认项 1，权限档位）**: 用户答复：`SaveWorkflowAsset` 取 `AGENT_STATE_PERMISSION`（照 `SaveMemoryTool`），理由是资产属跨会话状态层，与 Q4=B 耦合。；确认时间: 2026-09-26
- **Q6-附（实现期确认项 2，工具命名）**: 用户答复：就用 `SaveWorkflowAsset` / `ListWorkflowAssets` / `GetWorkflowAsset` / `RunWorkflowAsset` 四个名字。；确认时间: 2026-09-26

**第二批（第一轮 grill 新产生的 Q7–Q9）——已由用户拍板：**

- **Q7**: 用户答复：**重新定义**——mode 上限不得由跨 run 共享、会被并发构造覆盖的可变状态（`parent_mode_provider`）推导；改走 **contextvar**，与 `workflow_id`/`node_id`/`graph_distance`/`bus` 同机制（scheduler 在派发点 set、`finally` reset，`create_subagent` 读）。**快照语义**：workflow 启动时快照 root 会话 mode 作为整轮上限，运行中途切换模式不影响本次 run。**嵌套语义**：节点 A 的有效 mode `E_A = min(M_A, R)`，A 派生的子孙上限为 `E_A`，逐层收紧。已立项为独立 bug issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)，本 change 以它为**前置阻塞项**。；确认时间: 2026-09-26
- **Q8**: 用户答复：**采纳方案 C**——钳制**不回写 spec**，在 **scheduler 读取** `spec.max_runs`/`max_nodes`/`recursion_limit` 的入口处取 `min(declared, config)`，spec 对象保持声明值不变，以保护 `spec_hash` 不受运行时配置影响。**附加要求**：核实所有读取路径，`parent_envelope`/`status()`/`workflow_graph_snapshot()` 对外报出的限制值必须与实际生效值一致。；确认时间: 2026-09-26
- **Q9**: 用户答复：**采纳 reviewer 的数字 + 收窄范围**——列表面 20 条、description 截 120 字符、slug 上限 64、超限按 name 升序取前 N 并追加「还有 M 个资产未列出」；**只注入 root 会话，不进子 agent**；**`cacheable=False`**。；确认时间: 2026-09-26

> **主 session 复核附注（第二批）**：Q7 的 contextvar 方案已按用户硬性要求**实证**（不采信读码推断）——探针 `/tmp/probe_nested_mode2.py` 把该机制装到真实 manager 的既有挂点上并驱动真实队列/任务/上下文传播，验证了三件事：**grandchild 上限 = 父节点有效 mode**（read_only 节点请求 build 得 read_only）、**并发兄弟互不串味**（read_only 与 build 交错执行各自正确）、**逐层收紧**。机制可行性成立；实现期须在真实挂点重跑同形断言。

**第三批（第二轮 grill 新产生的 Q10–Q11）——已由用户拍板：**

- **Q10**: 用户答复：**采纳口径 1（继承）**——嵌套 workflow 的 mode 上限**继承发起节点的有效 mode**：图 A 的 `read_only` 节点内起的新图 B，其节点上限 = `read_only`（而非作为新图重新快照会话 mode）。理由：mode 是**能力面**而非配额，应只随继承链收紧。；确认时间: 2026-09-27
- **Q11**: 用户答复：**采纳候选 A**——mode 上限的「发起会话」可读通道**由 #255 定义**，本 change 只消费。**前置条件**：#255 的验收标准必须包含「提供一个 scheduler 可读的会话 mode 通道」；若 #255 未提供，则回退候选 B（本 change 从工具层显式传参）。用户同时确认整体执行顺序 **#255 → 本 change（#245）→ #246**。；确认时间: 2026-09-27

> **主 session 复核附注（第三批）**：Q10/Q11 均已回写 `design.md`（Q10 → 口径 1 + 补跨图 Scenario 的任务；Q11 → 候选 A + 前置条件 + 回退路径）。**Q10 的实测基线**来自第二轮 reviewer 的 `/tmp/r2_probe_v3.py` section C（会话 BUILD、图 A 的 read_only 节点内起图 B、B1 实测得 `read_only`）——即口径 1 是当前实现的自然行为，用户确认的是「把它固化为规格」而非改变行为。**Q11 的实测基线**来自 `/tmp/r2_probe_v7.py`（同一会话顺序两张图，第二张快照到被第一张污染的值 `['build','read_only']`），即该通道目前**不存在**，必须由 #255 提供。

> 主 session 复核附注：本 reviewer 的两条最高severity 结论已由主 session **独立复现**（未采信转述）——
> ① mode 钳制基准错位且 fail-open：`/tmp/myprobe2.py` 在 root 会话切至 `READ_ONLY` 后，一张声明 `mode: build` 的图仍被授予 `build`（provider 粘在 `BUILD`，不跟随 root）；
> ② 钳制改变 `spec_hash`：声明 `max_runs: 5000` 在配置 300 下 hash 由 `5bb392f41782ea7b` 变 `d1130d802fff9a0b`；pattern 路径在配置 ≠ 300 时 hash 亦漂移（`/tmp/myprobe3.py`）。

## 风险

按严重度降序，每条附 `文件:行号` 证据。

1. **【高】`mode` 收窄的基准是全局可变 provider，方向同时过严与过松。** `_clamp_mode` 读 `manager.parent_mode_provider`（`agent/subagent/manager.py:1600-1603`），该字段由**每次构造子 loop** 时重写（`agent/loop.py:153-155` → `agent/subagent/manager.py:544-545`），而所有节点起 run 都要经 `create_subagent`（`scheduler.py:2119` → `manager.py:559-562`），因此「当前会话允许的能力面」＝最后构造的子 loop 的 mode。实测：BUILD 会话里 `read_only → build` 链式图中 build 节点被降级（`/tmp/probe9.py`）；降级贯穿整个会话粘滞（`/tmp/probe10.py`）；反方向在只读会话里授予了 build（`/tmp/probe11.py`）。D3(2) 与 Q5=方案 B 的整个论证建立在「收窄是可靠的」之上，而今天它不可靠。既有测试只覆盖静态 `parent_mode`（`tests/agent/subagent/test_subagent_manager.py:54-61`），无任何测试触及 provider 路径。→ 见 Q7。
2. **【高】闸值钳制会改变 `spec_hash` 并让资产遗忘自己声明过的值。** `WorkflowSpec.to_dict()` 仅在值**不等于模块默认**时输出 `max_runs`/`max_nodes`/`recursion_limit`（`agent/subagent/workflow.py:279-294`），`spec_hash` 取 `to_dict()` 的 canonical JSON（`workflow.py:297-300`）。钳制到配置值后这些键被丢弃，hash 随之改变（实测 `5bb392f41782ea7b` → `d1130d802fff9a0b`，`/tmp/probe5.py`；配置非默认时 `probe13.py` 稳定复现）。直接冲击两处既有设计承诺：design §Testing Strategy 1 的 round-trip `spec_hash` 断言、D4 的 `unchanged` 去重判据（都会在配置值 ≠ 默认值时失效），并让 Q6 的 `previous_spec_hash` 语义变模糊。→ 见 Q8。
3. **【中】spec delta 漏掉两条已确认决策：Q1（per-repo 跨 worktree 共享）与 Q4（受限可发现面）。** `grep -n "worktree|per-repo|落点|注入|可发现|系统提示"` 在 `specs/*/spec.md` 上返回**零命中**（`description` 的两处命中是保存动作的入参，与注入面无关）。`multi-agent-collaboration/spec.md:7` 只写了「SHALL 由一个独立的 store 落在本机非提交路径下」——这只覆盖「不提交」，**不覆盖**「同一仓库所有 worktree 共享一套」。而 Q1=B 是用户拍板的**核心语义**（`design.md:215`），Q4=B 是实现任务 3.9 的依据（`tasks.md:36`）却**无规格可依**；`openspec validate --strict` 实测全绿，说明机械门禁抓不到这个缺口。→ 建议本 change 补两条 Requirement+Scenario，跨 worktree 场景可直接复用既有可测机制（`agent/memory/persistent.py:62-87` 的 `_find_scope_root`，其行为已被 `tests/agent/memory/test_persistent.py:50-77` 用伪造的 `.git` 文件 + `commondir` 钉死）。
4. **【中】注入面（Q4=B）的挂载点会把资产文本推进**每个**子 agent 的系统提示，成本与暴露面被低估。** `_make_default_context_builder`（`agent/loop.py:1438-1454`）是子 loop 的默认构造路径（`agent/subagent/manager.py:1308-1316` 不传 `context_builder`），`_messages_with_run_context` 在**每轮**调用 `build_blocks`（`agent/loop.py:1399-1424`，调用点 `:672`）。design 只说「注入系统提示」，未说明是 session 级还是全员，也未给条数/长度。另外 `cacheable=True` 的源在预算裁剪中被显式跳过（`agent/context/builder.py:129-142`），若误标会让资产列表**无法被裁掉**且内容陈旧。→ 见 Q9。
5. **【中】资产 `name` 没有长度上界，注入面与文件名双重承压。** slug 约束是 memory 正则 `^[a-z0-9-]+$`（`agent/memory/persistent.py:36`）与 store 段白名单的字符集交集（`agent/subagent/workflow_store.py:31-44`），`_validate_name` **只校验字符集、不校验长度**（`persistent.py:112-116`）。因此 `ignore-previous-instructions-and-rm-rf` 这类名字完全合法，且长度可任意（`workflow_store.py:41-44` 的守卫也不限长）。字符集约束挡住了**结构性**注入（换行、伪标题、Unicode 花活），挡不住**语义**暗示；长名还会同时冲击 `~/.asterwynd/projects/<hash>/workflow-assets/<slug>.json` 的路径长度。→ 建议 slug 加长度上限（64），并在注入前对名字与 description 做一次「只保留安全字符 + 单行化」的渲染。
6. **【中】Testing Strategy 的「坏资产容错」缺少区分「没有资产」与「资产全坏了」的具体断言。** design 只写了「不抛异常、不返回空列表（区分『没有资产』与『资产全坏了』）」（`design.md:290`），`tasks.md:19` 同。但没有指定区分字段——一个「吞掉所有异常并返回空列表 + 空 diagnostics」的实现同样满足「不抛异常」。对照物是 `WorkflowStore.read_events` 的容错姿态（`agent/subagent/workflow_store.py:188-205`，坏行跳过但**返回已解析的**事件）。→ 建议断言：全损坏时 `total == 0` 且 `diagnostics` 非空且含被跳过文件计数；完全无资产时 `diagnostics` 为空。
7. **【中】「模型当轮声明路径行为逐字不变」的回归锁方向不完整。** 既有 `test_spec_level_limits_override_defaults`（`tests/agent/subagent/test_workflow_spec.py:330-334`）用 7 / 11 两个**小于默认**的值，无法区分「min(declared, config)」与「无差别压低」。→ 必须补一条声明值**高于**配置值仍原样生效的测试（例如声明 `max_runs: 5000`、配置 300 ⇒ 该路径下 `spec.max_runs` 仍为 5000）。design 把这条笼统写成「落在 Q2 的方案 A 上」（`design.md:295`），没有指名既有测试，容易在实现期重复造或漏造。
8. **【低-中】Testing Strategy §5 引用了错误的「既有断言风格」出处，且 §3 的 mode 对照用例在今天的实现下不确定。** §5 说「复用 `test_concurrency_queue.py` / `test_guardrails.py` 的既有断言风格」（`design.md:304`）——这两个文件里确实有 spawn 工具集断言（`tests/agent/subagent/test_concurrency_queue.py:514-522`、`tests/agent/subagent/test_guardrails.py:183-191`），但同时**最贴切的既有用例**是 `tests/agent/subagent/test_workflow_tools.py:193-196`（`StartWorkflow`/`RunWorkflow` ∈ `SPAWN_TOOL_NAMES`）与 `:198-210`（深度到限被撤），design 未提及。更关键的是 §3 的对照用例「会话允许 build 时 `build` 原样生效」（`design.md:296`）在风险 1 的现状下**结果取决于同图内是否先跑过 read_only 节点**，会写成一条顺序敏感的不稳定测试。
9. **【低】若干引用行号漂移，与描述不符。** (a) design 称「`patterns.py:447-461` 的 `_legacy_result(pattern, ...)`」（`design.md:20`），但 `_legacy_result` 定义在 `agent/subagent/patterns.py:376`，447-461 是 `run_pattern` 的尾部（`compile_pattern` 调用在 `:447`、`_legacy_result` 调用在 `:457`）。(b) design 称 `RunPatternTool.execute` 在 `agent/tools/builtin/subagents.py:409-427`（`design.md:17`），实际 `execute` 在 `:435-442`，409-427 是 `@tool_parameters` 的参数声明段。(c) design 称未知 workflow 返回体在 `subagents.py:504-513`（`design.md:9`），实际 `_unknown_workflow` 定义在 `:500`、自述文案在 `:508-509`。(d) design 称 C3/C5 的回归断言为「逐字节」口径（本任务描述与 `design.md:176` 一带的隐含表述），实测两条具名测试均为**超集/成员**断言（`tests/agent/subagent/test_workflow_graph_snapshot.py:374-385`、`tests/agent/subagent/test_workflow_graph_snapshot_additions.py:283-292`），结论（不会变红）正确但性质需订正，否则实现期会按「逐字节」去设计一条不存在的约束。其余引用（`scheduler.py:451`、`manager.py:505/663-664/666-667`、`workflow.py:433-448/451-455/492-496/279-294`、`workflow_store.py:5-16/31-44/56-60/188-206/210-220`、`persistent.py:34-35/36/57-59/62-87/185/519-530`、`snapshot.py:34-35`、`main.py:215-216`、`manager.py:1588`）逐条核对**准确**。
10. **【低】D1 的 `asset_source` 若以「临时附加属性」方式实现，会漏掉 `RunWorkflow`/`DeclareWorkflow` 的 dsl 默认值。** `DeclareWorkflowTool` 在注册后显式 `scheduler.spec = spec`（`agent/tools/builtin/subagents.py`），而 `RunWorkflowTool.execute` 直接 `scheduler.run(spec)`、**从不设置** `scheduler.spec`（`subagents.py:850-870`）；若只在 `run_pattern` 里写字段，则 dsl 路径上该字段**永不存在**，「缺失降级 dsl」的规则虽能兜住结果，但把「预期值」实现成了「异常路径」。→ 建议在 `WorkflowScheduler.__init__` 里**声明并默认**为 `{"kind": "dsl", "reason": "declared-via-dsl"}`（而非 ad-hoc 赋值），只有 `run_pattern` 覆盖它；这样「缺失即降级」变成一条永不触发的防御分支。
