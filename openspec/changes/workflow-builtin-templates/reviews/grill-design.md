# Grill: workflow-builtin-templates 设计追问

## Reviewer

- **run id**: `grill-workflow-builtin-templates-20260929-r1`（reviewer 自署）；paseo agent id `b707f27b-3922-423a-bd15-6d99783ce9f4`（零记忆独立评审者，与主 session 无共享上下文）
- **时间**: 2026-09-29
- **审视对象**: `openspec/changes/workflow-builtin-templates/design.md` 的 D1–D6 与 Testing Strategy，对照 proposal.md、tasks.md、spec deltas 与真实实现代码
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-builtin-templates-2026-09-29`, 分支 `workflow-builtin-templates/2026-09-29`, HEAD `09e5fe8`（基线 master `ee06df7`）
- **评审方法（零记忆独立复核，非转述）**:
  - 实读：`agent/subagent/patterns.py`（全量 472 行）、`agent/subagent/scheduler.py`（重点 `_launch_run` 2163-2225、`NodeState` 225-291、`_bounded_node` 383-405、`_envelope` 3005-3086、`parent_envelope` 3088-3110、`run()` 789-830、`__init__` 481-524）、`agent/tools/builtin/subagents.py`（重点 `RunPatternTool` 415-451、`RunWorkflowTool` 834-884、`_asset_from_scheduler` 905-938、`GetWorkflowTool` 722-803、`RunWorkflowAssetTool` 1135-1242、`_invalid_spec` 493-506）、`agent/subagent/context.py`（全量）、`agent/tools/base.py`（schema 契约）、`agent/tools/registry.py:100-157`、`agent/anthropic_llm.py:750-753`、`agent/subagent/manager.py:424-434,1490-1505`、`benchmarks/agent_runner.py:505-529`、`agent/loop.py:54-68,380-410`、四个 spec delta 与 `openspec/specs/{multi-agent-collaboration,subagents,agent-runtime,web-ui}/spec.md`、七个受影响测试文件
  - 探针（全在 `/tmp`，直接驱动真实调度器/工具）：`/tmp/probe_d2.py`（legacy vs envelope 形状与计数对照）、`/tmp/probe_bus.py`（bus contextvar 在 `RunWorkflow` 路径是否可见）、`/tmp/probe_refs.py` `/tmp/probe_refs2.py` `/tmp/probe_itemrefs.py`（`_node_refs` 与 `item_runs` 的 ref 可得性）、`/tmp/probe_root.py`（`root_result_ref` 内容究竟是谁）、`/tmp/probe_fail.py`（worker 失败时两出口的明细差）、`/tmp/probe_params.py` `/tmp/probe_hash.py`（params 键的按模板消费语义）、`/tmp/probe_roundtrip.py`（`compile_pattern` → `parse_workflow_spec` 的 `spec_hash` 稳定性）、`/tmp/probe_workers_ref.py`（legacy 每 worker 的 `result_ref`）
  - 测试命令：`uv run pytest tests/web_tests/test_workflow_node_transcript.py -q` → **76 passed**；`uv run pytest tests/agent/subagent/test_workflow_asset_tools.py tests/agent/subagent/test_workflow_asset_context.py -q` → **30 passed**；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed**（含本 change）
  - 注：评审期间作者另落了两枚 commit（`5b167d9` 补文档影响面、`09e5fe8` 补 5.5a 测试迁移清单）；本报告结论基于 HEAD `09e5fe8`

## Confirmed Decisions

- **决策**: D2 的 `bus` 论证成立，但「删 `run_pattern` 会丢 bus contextvar 安装点」这一常见顾虑被证伪——`RunWorkflow` 路径的 bus 早已可用。
  理由: `run_pattern` 确实在 `patterns.py:449` 做 `set_bus(bus)`，但 scheduler 本身在**每次派发**时也会安装：`scheduler.py:2190` 的 `_launch_run` 做 `token_bus = set_bus(self.bus)`（`:2221` finally reset），而 `WorkflowScheduler.__init__` 接受 `bus=MessageBus()`（`scheduler.py:481-491`），`RunWorkflowTool` 就在 `subagents.py:869` 传入。探针用 monkeypatch 包住 `run_subagent` 采样 `current_bus()`，在纯 `RunWorkflow`（不经 `run_pattern`）路径下得到 `[True, True]`，即图内每个 worker 派发点 bus 均可见。
  来源: `agent/subagent/scheduler.py:2190,2221`；`agent/tools/builtin/subagents.py:869`；`/tmp/probe_bus.py` 输出 `bus visible inside worker dispatch: [True, True]`

- **决策**: D2「信息损失」比 design 描述的更严重——foreach 类模板（orchestrator-worker / hierarchical / bidding）的 per-worker 全文在统一出口下**不可达**，design 给出的补偿路径 `GetWorkflow(detail='nodes')` / `root_result_ref` 均不携带 per-worker ref。
  理由: 三个事实叠加。(a) 今天 legacy 出口的每个 worker 条目确实带 `result_ref`（`_worker_entry` 在截断时注入，`patterns.py:365-372`；探针实测 orchestrator-worker workers=3 得到三条 `artifact://workflow/<wf>/<run_id>`，只因原文未超 9000 字阈值才无 ref，一旦超限即带）。(b) 统一出口的 `_bounded_node` 丢弃 `subagent_ids`（`scheduler.py:389-397`，`_PARENT_NODE_FIELDS` 不含它）。(c) design 指定的补偿通道 `GetWorkflow(detail='nodes')` 加的 ref 来自 `_node_refs()`（`subagents.py:792-803`），而它只读 `state.subagent_id`/`state.run_id`——对 `kind: "foreach"` 节点这两个字段恒为 `None`（身份在 `state.item_runs` 里，`_ItemRunSlot`，`scheduler.py:199-213,1890`）。探针实测 `_node_refs(s)` 对 orchestrator-worker/hierarchical **返回 `{}`**，对 bidding 只返回 selector 一条，对 peer-review 返回 producer/reviewer 两条。per-worker 的 `result_ref` 只存在于 `state.item_runs[i]` → `manager.find_run(...).result_ref`，而**没有任何工具读 `item_runs` 的 ref**（`web/session.py:1004,1207,1213` 读 `item_runs` 只取 `subagent_id`/`run_id`/`failure_count` 做 transcript 路由，不吐 `result_ref`；全仓 `item_runs` 消费点无一是模型面工具）。
  来源: `agent/subagent/patterns.py:365-372`；`agent/subagent/scheduler.py:384,389-397,199-213,1890`；`agent/tools/builtin/subagents.py:792-803`；`/tmp/probe_refs2.py` 输出 `orchestrator-worker detail=nodes refs: {'workers': None, 'aggregate': None}`；`/tmp/probe_itemrefs.py`（item_runs 里每条 run 有 `result_ref`，但 `_node_refs` 取不到）

- **决策**: D4 的 `asset_source` 迁移判断正确——写入点确实唯一在 `run_pattern`，删它不迁移会让 #245 的 pattern 资产静默退化为 DSL 资产。
  理由: `self.asset_source: dict = {"kind": "dsl"}`（`scheduler.py:503`）；全仓唯一的 pattern 写入是 `patterns.py:457-462`（`{"kind":"pattern","pattern","params","task"}`）；消费者是 `_asset_from_scheduler`（`subagents.py:914`，`source.get("kind")=="pattern"` → 存 `recipe`，否则存 `spec` 正文，`:922-938`）。全仓 `grep asset_source` 另无写入点。
  来源: `agent/subagent/scheduler.py:503`；`agent/subagent/patterns.py:457-462`；`agent/tools/builtin/subagents.py:914,922-938`

- **决策**: D3 的「未知键拒绝」（task 1.2）与真实模板语义不匹配——今天 `compile_pattern` 对未知键**静默忽略**，且六个「封闭键」是**全局并集**，跨模板传合法但无关的键同样被静默忽略。
  理由: `_template_*` 只读各自的键（orchestrator-worker 读 `params.get("workers")`、hierarchical 读 `teams`、bidding 读 `proposers`、peer-review 读 `max_rounds`，`_worker_budget` 读 `worker_max_tokens`/`worker_max_time_s`，`patterns.py:65-77,80-231`）。探针：`compile_pattern("orchestrator-worker", params={"bogus":1})` **不抛异常**且 `spec_hash` 与空参完全相同；`compile_pattern("peer-review", params={"workers":7})` 的 `spec_hash` 也与空参完全相同（`658b47f0aa7d5495`）。即 task 1.2 的「全局封闭键集」能拦下 `bogus`，但拦不下 `peer-review + workers:7` 这类「键在集合内、但对该模板无意义」的组合——正是 D1 规则 #5 想消灭的「以为 params 生效了」假象在 template 路径复现。
  来源: `agent/subagent/patterns.py:65-77,80-231`；`/tmp/probe_params.py`、`/tmp/probe_hash.py` 输出（`orchestrator-worker teams:5 == f5753e7ff3855502`、`peer-review workers:7 == 658b47f0aa7d5495`）

- **决策**: D1 的「exactly one of `{spec, template}`」在 schema 层**不可表达**，只能是运行期判别；且必须把 `"required": ["spec"]` 摘掉。
  理由: `tool_parameters` 把参数字典原样存进 `Tool.parameters`，`get_schema()` 原样返回（`agent/tools/base.py:18-56`），Anthropic 侧 `_convert_tool` 直接把它当 `input_schema`（`agent/anthropic_llm.py:750-753`）——RIR 已引证 Anthropic API 拒绝顶层 `oneOf`/`anyOf`，故 schema 无法表达互斥，模型实际看到的是「两个可选字段 + 无 required 判别子」。当前 `RunWorkflow` 的 schema 是 `"required": ["spec"]`（`subagents.py:855`），加 `template` 后必须移除它，否则 `RunWorkflow(template=…)` 在 schema 层就被判缺参。这与 proposal RIR「判别子必须显式且在 required 语义上无歧义」的自我要求存在张力——实现上只能靠描述文本 + 运行期拒绝。
  来源: `agent/tools/base.py:18-56,58-66`；`agent/anthropic_llm.py:750-753`；`agent/tools/builtin/subagents.py:844-856`

- **决策**: D5 的删除面清单基本准确但**不完整**——`_worker_entry` 还有一个 design 未点名的直接调用者（测试），且 `_AGGREGATE_NODE_IDS`/`_workers_from_node` 确实只服务 `_legacy_result`（可安全删）。
  理由: 全仓 grep 确认 `_AGGREGATE_NODE_IDS`（`:247`）、`_workers_from_node`（`:314`）、`_worker_entry`（`:333`）、`_legacy_result`（`:376`）在 `agent/` 下的调用点只在 `patterns.py` 内部（`_legacy_result` 是唯一的外部消费者）。但 `_worker_entry` 另被 `tests/web_tests/test_workflow_node_transcript.py:942-946` **直接 import 调用**（`test_worker_entry_without_workflow_identity_does_not_lie`），design 的 D5 注记与 tasks 5.6 只提到「出口 4 经 `run_pattern`」那条（`:894-932`），漏了这条直调测试——它必须一并处理（删或改），否则删 `_worker_entry` 会直接 ImportError。另外 `_worker_entry` 内 `from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT, _clip` 是函数内 import，删除时不影响模块头。
  来源: `agent/subagent/patterns.py:247,314,333,376`；`tests/web_tests/test_workflow_node_transcript.py:894-946`（`grep -rn '_worker_entry'` 结果）

- **决策**: D2 的 `completed`/`failed` 语义切换（节点口径 → run 口径）经实测为真，且 design 对两种口径的量化描述方向正确。
  理由: peer-review（producer 跑 2 轮 + reviewer 2 轮 + gate + aggregate）legacy `completed=2`（producer/reviewer 两条终态**节点**），统一出口 `completed=4`（4 个 **run**）；bidding legacy `completed=3`（3 个 proposer 节点，selector 被排除在 `workers[]` 外），统一出口 `completed=4`（含 selector 的 run）。同 `spec_hash`（`6ae2bf4e059a9283`）证明两路径产同一张图。
  来源: `/tmp/probe_d2.py` 输出（`peer-review legacy completed 2 / envelope completed(runs) 4`、`bidding legacy completed 3 / envelope 4`、`spec_hash match: True`）

- **决策**: D6 的 `wait=false` 回执确实是与终态结果**不同形状**的第二个出口，但它与「入参相关形状」违例的边界比 design 写的更细——回执的键集是 `{status, workflow_id, spec_hash, nodes}`，与 `parent_envelope()` 的 40+ 键**完全不同**。
  理由: `subagents.py:871-881` 的 `wait=false` 分支返回硬编码四键 dict，而 `wait=true` 返回 `parent_envelope()`。二者键集不相交。design 用「显式判别子」论证可接受（`design.md:132-137`），但该论证只在「判别子显式」意义上成立；从「形状随入参变化」的**字面**标准看，`wait` 就是一个使形状翻转的入参，与 D2 想消灭的形态同构。design 承认这点并归因为「正交的第二形状」，理由自洽，但需用户认可「`wait` 显式声明」足以豁免。
  来源: `agent/tools/builtin/subagents.py:864-884`；`/tmp/probe_d2.py` 的 parent keys 列表（41 键）

- **决策**: spec delta 覆盖不全——`multi-agent-collaboration` 下另有两条 Requirement 硬引用 `RunPattern`，本 change 的 delta 未 MODIFY，归档后 `openspec/specs/` 会留下与实现矛盾的存量条款。
  理由: `openspec/specs/multi-agent-collaboration/spec.md` 的「资产保存是显式的，且 spec 不穿过模型输出」Requirement 的 Scenario（`:540`）GIVEN 写「模型刚通过 `RunPattern` 跑完一张图并拿到 `workflow_id`」；「资产的两类载体与参数化复用」Requirement 正文（`:560`）写「从内置编排模式（`RunPattern`）产出的图 SHALL 保存为配方」，其 Scenario「pattern 资产保留参数化」（`:564`）GIVEN 写「资产由 `RunPattern(pattern="orchestrator-worker", params={\"workers\": 3})` 保存」。本 change 的 `specs/multi-agent-collaboration/spec.md` 只 MODIFY 了「Orchestration Pattern Library」与「内置编排模式降级为 DSL 模板」两条，**未触及**上述两条。tasks 5.8 的删净检查 `rg 'run_pattern|RunPattern|_legacy_result'` 只扫 `agent/ tests/ benchmarks/ web/`，**不含 `openspec/specs/`**，因此该漏项不会被任务的机械检查抓住。
  来源: `openspec/specs/multi-agent-collaboration/spec.md:533-570`；`openspec/changes/workflow-builtin-templates/specs/multi-agent-collaboration/spec.md`（仅 4 条 delta）；`tasks.md:47`（5.8 的扫描范围）

- **决策**: `compile_pattern` → `parse_workflow_spec` 的 round-trip 是 `spec_hash` 稳定的，task 1.3 与 Testing Strategy 的「逐字一致」断言可成立。
  理由: 探针 `parse_workflow_spec(compile_pattern(...).to_dict())` 的 hash 与原 hash 相等（`3eb32d1c59ce7c26`），且带 `_spec_bounds` 的三闸默认值也相等（说明 bounds 不影响 hash，`to_dict()` 只吐 `{edges, entry, goal, nodes, schema_version, terminal}`）。所以 `RunWorkflow(template=...)` 内部走 `parse_spec_for_manager` 后 `spec_hash` 不变，Testing Strategy 的 `spec_hash 相等` 断言可落地。
  来源: `/tmp/probe_roundtrip.py` 输出；`agent/subagent/workflow.py`（`spec_hash` 定义，`agent/tools/builtin/subagents.py:475-477` 的 `parse_spec_for_manager`）

## Open Questions

> 每条配本 change 真实场景的具体例子，供用户快速拍板。**未答复前不得写实现代码**（grill-confirmation-gate）。

- **Q1**: per-worker 明细在统一出口下变成**不可达**（不只是「多一跳」），是接受这个损失、还是必须补一条 compensation 通道？
  **具体场景**：`RunWorkflow(template="orchestrator-worker", task="审查 3 个模块", params={"workers": 3})`，worker-2 失败、worker-1/3 成功。**今天**父 agent 拿到的 `workers[]` 里三条各自带 `subagent_id`、`status`、截断后的 `summary`、以及**被截断时的 `result_ref`**（探针实测：`fa89f8dc completed ... ref: artifact://workflow/wf_50d9f4ec/7f9ce30f17fd`），能直接 `ReadWorkflowResult(ref)` 读任意一个 worker 的全文。**合并后**父 agent 拿到的 `nodes[]` 只有一条 `{id:"workers", kind:"foreach", status:"completed", runs:3, items:3, summary:"worker1 output…", reason:"1/3 foreach items did not complete"}`；`GetWorkflow(detail='nodes')` 的 ref 来自 `_node_refs()`，对 foreach 节点**实测返回 `None`**（`{'workers': None, 'aggregate': None}`）——因为 foreach 的身份在 `state.item_runs` 而非 `state.subagent_id/run_id`；`root_result_ref` 只落「终态节点的最后一条 summary」（实测内容只有 aggregate 自己的输出，不含 W1/W2/W3 各自正文）。**结果**：父 agent 能看到「3 个 worker 名字里有 1 个没完成」，但**拿不到任何一个 worker 的完整产出**，`ReadWorkflowResult` 无 ref 可传。
  **推荐**：**必须补**——最小改法是在 `_node_refs()`（或 `GetWorkflow(detail='nodes')`）对 `kind=="foreach"` 节点读 `state.item_runs`，吐一个 `item_refs: [{index, subagent_id, run_id, result_ref}]`（这是纯读投影，`item_runs` 已是权威身份源，`web/session.py` 同款用法已存在）。否则 task 5.6 打算「改挂到 `GetWorkflow(detail='nodes')` 的 `result_ref`」这套断言**写不出来**——现在的 `_node_refs` 对四个模板里三个的 foreach 节点根本给不出 ref，实现阶段一定会在这里卡住或静默降级成「只断言 root_result_ref」，把 issue #213 的回归保护缩水。

- **Q2**: 父 agent 看到的 `completed`/`failed` 从「终态**节点**数」翻成「**run** 数」，是否接受？
  **具体场景**：`RunWorkflow(template="peer-review", task="写方案", params={"max_rounds":3})`，producer 改两稿才获批。**今天** `RunPattern` 返回 `completed=2`（producer + reviewer，各算一条 worker，即使 producer 跑了 2 轮）。**合并后**同一个 `spec_hash` 的图，父 agent 拿到 `completed=4`（producer×2 + reviewer×2 四次 run 全计）。用户若按「2 个子 agent 完成了」读这个数会误判成本/规模；`failed` 同理会把「同一节点失败重试」重复计数。
  **推荐**：**接受 run 口径 + 在工具描述里写明「completed/failed 数的是 run，不是 subagent」**（design 的缓解方向正确）。理由：run 口径是新出口的既有事实、改动它要动 `_envelope`（C2 的 24 处断言依赖），代价远超收益；且 `nodes[]` 已给出每节点的 `runs` 字段，需要节点口径时的正确形态是 `GetWorkflow` 的新 detail，而非改 envelope。若用户坚持要节点口径，请一并回答「放 `GetWorkflow` 的哪个 detail 模式」。

- **Q3**: `params` 的键校验口径是「全局封闭键集」（拦 `bogus`，放行 `peer-review + workers:7`）还是「按模板封闭」（连跨模板无关键也拒）？
  **具体场景**：模型调 `RunWorkflow(template="peer-review", task="写方案", params={"workers": 7})`（把 orchestrator-worker 的键记混了）。**今天** `compile_pattern` 静默忽略 `workers`，编译出的图与不传 params **逐字节相同**（实测 `spec_hash` 都是 `658b47f0aa7d5495`）——父 agent 以为起了 7 个并发点，实际 peer-review 只有 producer/reviewer 两个节点、并发度 2。task 1.2 的全局封闭键集拦不下这个组合（`workers` 在集合内），于是 D1 规则 #5 要消灭的「以为 params 生效了」假象在 template 路径原样复现；而 D1 规则 #5 恰恰在 spec 路径上把同款情况判为 `invalid_input`。
  **推荐**：**按模板封闭**——为每个模板定义其接受的键子集（orchestrator-worker: `workers`/`worker_max_*`；hierarchical: `teams`/`worker_max_*`；bidding: `proposers`/`worker_max_*`；peer-review: `max_rounds`/`worker_max_*`），不属于该模板的键结构化拒绝并在 `reason` 里列出该模板的可用键。理由：与 D1 规则 #5 的动机完全一致（「避免以为 params 生效了」），实现成本极低（一张 `dict[pattern, frozenset]`），且这是**行为变更**——`RunWorkflowAsset` 的 pattern 分支会把 recipe 默认 params 与调用方 params 合并（`subagents.py:1198-1199`），历史上允许「多传了无关键」，收紧后若某资产 recipe 存着跨模板键会被拒。用户需确认：**是否接受这个收紧，以及 `RunWorkflowAsset` 的合并路径要不要同步享受同一校验**。

- **Q4**: `wait=false` 的启动回执（`{status, workflow_id, spec_hash, nodes}`，`subagents.py:871-881`）与终态 `parent_envelope()`（41 键）形状完全不同，是否确认为可接受的「正交第二形状」？
  **具体场景**：模型先 `RunWorkflow(template="bidding", task="选方案", wait=false)` 拿到 `{"status":"running","workflow_id":"wf_ab12","spec_hash":"a931cf97…","nodes":[]}`，再 `GetWorkflow("wf_ab12")` 轮询。**问题**：这个回执**没有** `nodes_total`/`root_result_ref`/`completed` 等任何终态字段，模型若把回执当结果解析（例如取 `nodes` 找产出），会拿到空数组且**看不出自己错了**（`status:"running"` 是唯一线索）。D2 的整个立论是「形状不随入参变化」，`wait` 是一个能让形状翻转的入参，二者在字面上冲突。
  **推荐**：**确认接受 + 在工具描述里硬写「`wait=false` 返回的是启动回执，不是结果；结果只在终态返回里，或经 `GetWorkflow` 轮询取」**（design `:137` 已倾向此方案）。理由：回执的判别子 `status:"running"` 显式且与终态 status 集合不相交（design `:136` 列的 7 个终态），且 `wait` 是调用方显式声明而非服务端推断——符合 RIR 的「显式、诚实的判别子」门槛。若要更稳，可在回执里加一个布尔 `started: true` 或把 `nodes: []` 换成 `nodes: null` 以强化「这不是节点投影」的信号。

## Review Notes

- **（中）`docs/` 文档影响面已在评审期间被作者补全**（commit `5b167d9`）：proposal 的「文档」段现在逐个列出 `docs/` 下 7 个 `RunPattern` 命中文件与「10 个 spawn 工具 → 9」的口径变更，tasks 6.2/6.4 已更新。本 reviewer 独立 grep 复核，命中文件清单与处数一致（`docs/agent-internals.md:1029`、`docs/interview-bullets/walkthrough.md` 14 处、`docs/interview-script/run-pattern-web-demo.md` 整份 8 处、`W03-multi-agent.md` 2 处、`Q08-multi-agent.md:54`、`interview-prep.md:225`）。此项无需再追。

- **（中）#245 回归测试迁移清单已在评审期间补入**（commit `09e5fe8`，tasks 新增 5.5a）：点名 `test_workflow_asset_tools.py:121`、`test_workflow_asset_context.py:165`（用 `RunPatternTool` 产出 pattern 图）与 `test_workflow_asset_context.py:195`（`test_run_pattern_result_keyset_is_locked` 键集锁）。本 reviewer 复核：这两文件确以模块级 `import RunPatternTool`（`test_workflow_asset_tools.py:28`、`test_workflow_asset_context.py:23`）并在上述行调用，**删除 `RunPatternTool` 会让这两个文件在收集期就 ImportError**，5.5a 正确且必要。补一条 5.5a 未提的：`_worker_entry` 被 `test_workflow_node_transcript.py:942` 直调（见 Confirmed Decisions），也须一并处理。

- **（中）`benchmarks/agent_runner.py:518` 的注释引用 `RunPatternTool`**（「与 `RunPatternTool` 同路」），tasks 5.8 的删净检查把 `benchmarks/` 列入扫描范围，故会被抓住；但该文件本身**逻辑不受影响**（C5 template 臂直调 `compile_pattern`，`agent_runner.py:505-529`，design 事实 #6 正确）。

- **（低）`agent/subagent/bus.py:3` 与 `agent/subagent/context.py:11` 的模块 docstring 也写「bus is created by `RunPattern`」**，tasks 5.4 只点了 `bus.py` 的 `snapshot_payload()` docstring（`:208-215`）。三处措辞需一并订正，5.8 的 grep 会兜住。

- **（低）`scheduler.py:499-502` 的 `asset_source` 注释自述矛盾**：注释写「`RunWorkflow` 路径**从不**设置 `scheduler.spec`」，但 `run()` 在 `scheduler.py:795` 会执行 `self._spec = spec`，而 `SaveWorkflowAsset` 依赖 `scheduler.spec` 非空才能落资产（`subagents.py:989-993`）——即 `RunWorkflow(spec=…, wait=true)` 跑完后是**可以**存 DSL 资产的。该注释是 D1 时代的叙述残留，实现时若照它删/改代码会引入误判，建议顺手订正（不属本 change 的强制项）。

- **（低）`critical_path_s` 口径在合并后会变**：legacy 把它覆盖成 `run_pattern` 的**外挂钟**（`patterns.py:470`，含编译 + bus 装配），统一出口给的是调度器内部窗口（`finished_at - started_at`，`scheduler.py:3048`）。数值偏小，direction 一致；design 未显式披露，实现时若要保 parity 需注意（不建议保，方向正确）。

- **（低）`spec_hash` 命名切换**：legacy 的 `workflow_spec_hash`（`patterns.py:402`）在统一出口叫 `spec_hash`（`scheduler.py:3025`）。delta 已显式声明改挂（`specs/multi-agent-collaboration/spec.md:19`），但父 agent 若缓存了旧键名会 KeyError——这是破坏性变更的一部分，与删工具名同批发布，可接受。

- **未解疑点（无工具可验，留给实现）**：`RunWorkflowAsset` 的 pattern 分支合并 params（`subagents.py:1198-1199`）后在 Q3 若采用「按模板封闭」，需明确是**合并后校验**还是**分别校验**——合并后校验更宽松（recipe 与 caller 各出一半也能凑齐合法键），分别校验更严但可能拒绝历史上合法的资产。design 的 Non-Goals 明确「资产工具对外行为不变」，故 Q3 的收紧若要落在 `RunWorkflowAsset` 上，会与该 Non-Goal 冲突，需一并拍板。

## User Confirmation

> 本节为两轮 grill 的 Open Questions 的用户答复汇总；两轮 `## Confirmed Decisions` / `## Open Questions` / `## Review Notes` 原文逐字保留。答复时间均为 2026-09-29。

- **Q1**: 用户答复：**补 per-worker 通道**。落 `GetWorkflow(detail='nodes')`，形状 `item_refs: [{index, subagent_id, run_id, result_ref?}]` + `items_total` / `item_refs_omitted`；**跳过未派发的空槽**；**只有成功项有 `result_ref`**（失败/取消/预算超限恒为 `None`）。spec delta 措辞须与 legacy `_worker_entry` 同口径，**不得暗示失败项可读全文**。；确认时间: 2026-09-29
- **Q2**: 用户答复：**接受 run 口径，不改名**。`completed`/`failed` 数的是 run 不是 subagent；改名要连 `_envelope` 一起动（约 20 处断言），性价比不抵，故不改名。**必须在工具描述里写明**「completed/failed 数的是 run，不是 subagent」。主 session 补充：实测 `parent_envelope()` 是 `_envelope()` 的派生（`scheduler.py:3100` 起手 `self._envelope(status=…)` 再 pop + bounded），「只改父投影」结构上不可行，故主 session 撤回其改名提议、接受 reviewer 结论。；确认时间: 2026-09-29
- **Q3**: 用户答复：**按模板封闭键校验 + 同步收紧资产路径**。校验落 `compile_pattern`（唯一 choke point）；同步修订本 change 自设的 Non-Goal 措辞（**不违反 #245**——#245 无此承诺且显式把模板归一划给 #246）。；确认时间: 2026-09-29
- **Q4**: 用户答复：**接受 `wait=false` 回执为「正交第二形状」**；工具描述硬写「回执非结果」（`status:"running"` 与终态集合不相交，`wait` 是显式入参）。；确认时间: 2026-09-29
- **Q5**: 用户答复：**做值级校验**。非法值（非整数 / null / 不可转数）→ `invalid_input` 结构化拒绝，列出可用键与取值约束；**clamp 保留**（`workers=0/-5 → 下界`是既有语义，不动）。；确认时间: 2026-09-29
- **Q6（主 session 取证时新增约束）**: 用户答复：`params` 计数键**无上界**（实测 `workers=100000` 造 10 万 spec items），要求明确它在 Q3/Q5 校验设计里的归位（拒绝还是钳到某个上界？），并与既有三闸（`max_items`/`max_nodes`/`max_runs`）的关系写清楚，**不得造出第二套互不知情的上界**。本 session 实测结论与归位决定见 design.md 的 Open Question 6（✅ 已确认）：既有 `max_items`（默认 20）**已经是**该上界（`_resolve_items` 执行期 `items[:max_items]` 截断），故**不新增上界**，改为「计数键 > `max_items` → `invalid_input` 拒绝」，把今天的静默截断（`workers=50` 只跑 20）变为显式拒绝。；确认时间: 2026-09-29

## Round 2

### 第二轮 Reviewer

- **run id**: `grill-workflow-builtin-templates-20260929-r2`；paseo agent id：`3d9ab70a-0f68-40d3-b666-1adc34303409`（零记忆独立评审者，与主 session 及第一轮 reviewer 均无共享上下文）
- **时间**: 2026-09-29
- **审视对象**: 第一轮订正后的 design.md D1–D6（尤重 D2 的「⚠️ 实测订正」块与 D3 的「按模板封闭」块）与最终 spec delta / tasks
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-builtin-templates-2026-09-29`, 分支 `workflow-builtin-templates/2026-09-29`, HEAD `8e34f53`（基线 master `ee06df7`）
- **前提**: 第一轮的 11 条决策与 4 条 Open Questions 逐字保留于上文；本轮只追加
- **评审方法（零记忆独立复核，探针优先）**:
  - 实读：`agent/subagent/scheduler.py`（`_ItemRunSlot` 198-221、`NodeState` 224-291、`_bounded_node` 383-405、`_envelope` 3005-3086、`parent_envelope` 3088-3110、`_write_root_result` 3112-3140、`_execute_foreach` 1873-1941、`_run_foreach_item` 1943-1969、`_launch_run` 2163-2242、`run()` 789-857、`_check_budget_before_dispatch` 1037-1149+）、`agent/tools/builtin/subagents.py`（`RunPatternTool` 415-451、`GetWorkflowTool` 722-803、`_node_refs` 792-803、`RunWorkflowTool` 834-884、`_asset_from_scheduler` 905-938、`SaveWorkflowAsset` 941-1005、`RunWorkflowAsset` 1135-1242）、`agent/subagent/patterns.py`（全量 472 行）、`agent/subagent/manager.py`（`SubagentRunRecord` 189-250、`find_run` 596-604、`_complete_run`/`_write_result_artifacts` 1326-1393、`_mark_failed`/`_mark_cancelled`）、`agent/subagent/workflow_assets.py`、`web/session.py:1004,1207,1213`、`benchmarks/agent_runner.py:505-529`、四个 spec delta、`openspec/changes/archive/2026-09-28-workflow-asset-persistence/{design,proposal,specs}.md`
  - **探针（全在 `/tmp`，直接驱动真实调度器/工具/资产层；本轮重点，逐个实测）**：
    - `/tmp/probe_r2_d2.py`——模板 foreach 经真实 `WorkflowScheduler` 到终态，dump `item_runs`（全成功 / 一个失败 / 取消 / per-worker 预算超限四态）
    - `/tmp/probe_r2_d2b.py`——手写 DSL foreach，精确让 index=1 失败、派发后取消，dump 每 item 的 `find_run` 解析与 `result_ref`
    - `/tmp/probe_r2_d2c.py`——`_bounded_node` 对 50 项 foreach 节点的投影形状；`_acquire_slot` 拒绝路径
    - `/tmp/probe_r2_d2d.py`——容器级预算 drain（`max_total_runs=2` / 6 项）导致「未派发项」的空槽
    - `/tmp/probe_r2_d3.py`——`compile_pattern` 未知键静默忽略、非整数值 `int()` 抛错、`max(1, int())` clamp 与封闭键集的关系
    - `/tmp/probe_r2_q1q2.py` + `/tmp/probe_r2_q2b.py`——**真实 DSL foreach 图**（非模板）的 per-worker ref 可达性；`parent_envelope` vs `_legacy_result` 的 completed/failed 口径对照
    - `/tmp/probe_r2_q3.py`——`RunWorkflowAsset` 的 pattern 分支合并 params 是否放行跨模板键（真实资产层）
    - `/tmp/probe_r2_keys.py`——`parent_envelope()` 实测键集（43 键）
    - `/tmp/probe_r2_huge.py`——`params={"workers": N}` 无上界 clamp
  - 测试命令：`uv run pytest tests/agent/subagent/test_pattern_templates.py test_patterns.py test_bounded_envelope.py test_bus_bounded_exports.py test_workflow_asset_tools.py test_workflow_asset_context.py -q` → **78 passed**；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed**（含本 change）
  - 注：本轮对 HEAD `8e34f53`（含作者补入的两条 asset Requirement delta、tasks 5.5a/5.6a/5.8 收口）评估；第一轮的 delta 覆盖缺口已在该 commit 修复（见下文决策 12）

### 第二轮 Confirmed Decisions

- **决策**: D2 的补偿路径（`_node_refs()` 读 `state.item_runs` 吐 `item_refs`）**技术上可行**——`item_runs` 在所有「已派发 run」的终态下都带真实 `subagent_id`/`run_id` 且 `manager.find_run` 能解析；但设计漏了三个必须订正的细节（见下条）。**不推翻 R1 的 D2 结论，仅收紧其措辞。**
  理由: 探针 `/tmp/probe_r2_d2.py`（模板全成功态）与 `/tmp/probe_r2_d2b.py`（精确单 item 失败 / 派发后取消）实测——每个已派发项 `item[i] subagent_id=<hex> run_id=<hex> find_run=OK`；`item_runs` 由 `_execute_foreach` 在展开时初始化（`scheduler.py:1890`）、`_launch_run` 在派发那一刻写回 `reuse_state.subagent_id`/`run_id`（`scheduler.py:2199-2208,2225`），故与 run 身份一一对应。`web/session.py:_foreach_candidates`（`:1207,1213`）已是同款「`item_runs[i]` → `find_run`」读法，证明该投影是既有成熟用法而非新面。
  来源: 探针 `/tmp/probe_r2_d2.py`、`/tmp/probe_r2_d2b.py`；`agent/subagent/scheduler.py:1890,2199-2208,2225`；`web/session.py:1207,1213`

- **决策（HIGH，订正 D2/spec delta 的过度承诺）**: `item_refs` 只能恢复**成功项**的 `result_ref`；失败/取消/预算超限的 run **`result_ref` 恒为 `None``，因为只有成功路径 `_complete_run` → `_write_result_artifacts` 落盘并写 ref，`_mark_failed`/`_mark_cancelled`/`_mark_budget_exceeded` 都不写。** 本 change 的 spec delta（`specs/multi-agent-collaboration/spec.md:142`）写「对 `kind=="foreach"` 节点…暴露每个展开项的 `result_ref`，使 per-worker 全文在统一出口下**可达**」——这是对**失败项**的过度承诺，须改为「成功项可达 / 失败项只有 bounded `reason`（与既有 legacy `_worker_entry` 同口径）」。
  理由: 探针 `/tmp/probe_r2_d2b.py` 的 B2 用例——index=1 项失败：`item[1] run.status='failed' result_ref=None`，而 `item[0]`/`item[2]` 成功项 `result_ref='artifact://workflow/wf_5ef0b943/...'`；C2 取消用例：三项全 `status='cancelled' result_ref=None`；`/tmp/probe_r2_d2.py` 的 D 用例（`worker_max_tokens=5`）：三项全 `status='budget_exceeded' result_ref=None`。这与 legacy `_worker_entry` 的行为**一致**（`patterns.py:365-372` 只在 `truncated and ref` 时注入），所以不是净回归，但 spec delta 的「每个展开项…可达」字面承诺在失败态下不成立。
  来源: 探针 `/tmp/probe_r2_d2b.py`（B2/C2）、`/tmp/probe_r2_d2.py`（D）；`agent/subagent/manager.py:1213-1242,1326-1388`；`agent/subagent/patterns.py:365-372`

- **决策（HIGH，D2 补偿的新增约束）**: `item_runs` 的槽在「未派发」时是**空槽**（默认 `_ItemRunSlot()`，`subagent_id=None`/`run_id=None`），`item_refs` 投影必须跳过空槽；且 `params` 的计数键**无上界 clamp**，`item_refs` 的长度在原则上无界，补偿投影**必须自带界**（≤ `max_runs`）否则会把「bounded 读出口」重新撑成随规模线性的数组——正是投影纪律要消灭的形态。
  理由: 探针 `/tmp/probe_r2_d2d.py`（`max_total_runs=2` / 6 项 foreach）：`fan: status=blocked item_states=['pending']*6`，六个槽全 `subagent_id=None run_id=None find_run=MISS`（派发前被预算 drain 拦下，槽未填）。探针 `/tmp/probe_r2_huge.py`：`compile_pattern("orchestrator-worker", params={"workers": 100000})` → `foreach items=100000`（`_template_orchestrator_worker` 只做 `max(1, int(...))`，无上界）。单个 `item_ref` 约 131 字节，1000 项即 131 KB。故「每项一个 ref」在成功态虽被 `max_runs`（默认 300，成功项 ≤ 约 298）间接界定，但**设计文本没有任何界声明**；`test_get_workflow_detail_nodes_stays_bounded`（`tests/agent/subagent/test_bounded_envelope.py:176-191`）也只覆盖 100 个 **leaf** 节点、不含 foreach，无法兜住。
  来源: 探针 `/tmp/probe_r2_d2d.py`、`/tmp/probe_r2_huge.py`；`agent/subagent/patterns.py:80-81`（`max(1, int(params.get("workers", 3)))`）；`tests/agent/subagent/test_bounded_envelope.py:176-191`

- **决策**: challenge 1 提出的「更小改法」——把 per-item 投影直接塞进 `parent_envelope()` 的 `_bounded_node`——**应否决**：它同时违反本 change 的 Non-Goal（「不改 `parent_envelope()` / `_envelope()` 的内容……逐字不动」，`design.md:36`）与投影纪律（`_bounded_node` 明写「丢弃随图规模线性增长的数组」，`scheduler.py:389-405`，`subagent_ids` 即因此被丢）。**设计选 `GetWorkflow(detail='nodes')`（经 `_node_refs`）是对的**，那个出口本就允许逐节点 `result_ref`（`subagents.py:775-781`）。
  理由: 实测 `_bounded_node` 对 50 项 foreach 节点的产物键集为 `['id','items','kind','reason','runs','status','subagent_id','summary']`（探针 `/tmp/probe_r2_d2c.py` 的 H 用例）——`items` 只保留 **int 计数**（=50），正是「丢线性数组、留标量」的证据；把线性 `item_refs` 塞回这里就是反其道而行。反向验证：加 `item_refs` 到 `GetWorkflow` 出口**不破坏**任何既有精确键集测试——`test_workflow_graph_snapshot.py:376-387` 与 `test_workflow_graph_snapshot_additions.py:285-297` 用的是超集断言（`set(...) >= {...}`）且不覆盖 foreach 节点；`test_get_workflow_detail_nodes_lists_refs`（`test_workflow_read_tools.py:156-170`）只断 leaf 节点。
  来源: 探针 `/tmp/probe_r2_d2c.py`；`agent/subagent/scheduler.py:389-405`；`agent/tools/builtin/subagents.py:775-781`；`tests/agent/subagent/test_workflow_graph_snapshot.py:376-387`

- **决策（D3，新增 gap）**: 「封闭键集」校验应落在 **`compile_pattern` 这一唯一 choke point**（三个生产调用方共用），且**必须同时做值级类型校验**——今天 `params={"workers": "abc"}` 会在 `_template_*` 里抛**未捕获**的 `ValueError`（`int("abc")`），`{"workers": None}` / `{"teams": [1,2]}` 抛 `TypeError`，在 AgentLoop 里经 `execute_with_retry` 折成模型可见的裸 `[Error: invalid literal for int() with base 10: 'abc']`（不可重试 → 直接进上下文），既非结构化拒绝也非 `invalid_input`——与 D1 规则 #5「非法入参结构化拒绝」的口径冲突。设计只写了「未知键」这一维，漏了「值非法」维。
  理由: 探针 `/tmp/probe_r2_d3.py`——`orchestrator-worker {'workers': 'abc'} -> ValueError: invalid literal for int() with base 10: 'abc'`；`{'workers': None} -> TypeError`;`hierarchical {'teams': [1,2]} -> TypeError`。`agent/loop.py:1330-1345` + `agent/hooks/builtin/retry.py:42-61`：非 retryable 异常包成 `ToolResult(text=f"[Error: {msg}]")`。落点选择证据：三个生产调用方为 `run_pattern`（`patterns.py:447`，本 change 删）、`RunWorkflowAsset` pattern 分支（`subagents.py:1201`）、benchmark `_run_template_pattern`（`agent_runner.py:516`，**不传 params**），故在 `compile_pattern` 内校验不会破坏任何既有测试/调用方（既有测试全部只用模板自身的键）。
  来源: 探针 `/tmp/probe_r2_d3.py`；`agent/subagent/patterns.py:234-243,447`；`agent/tools/builtin/subagents.py:1201`；`benchmarks/agent_runner.py:516`；`agent/hooks/builtin/retry.py:42-61`

- **决策（D3/clamp 正交）**: 封闭键集校验与 `max(1, int(...))` clamp **正交**、不冲突——clamp 作用于**值的下界**（`workers:0 → 1`、`workers:-5 → 1`、`proposers:0 → 2`），键集校验作用于**键名归属**。设计无需为 clamp 改口径；但二者叠加仍拦不住「值非整数」（见上条）。
  理由: 探针 `/tmp/probe_r2_d3.py`——`orchestrator-worker {'workers': 0} -> foreach items=[1]`、`{'workers': -5} -> items=[1]`、`bidding {'proposers': 0} -> items=[2]`，均 clamp 而非拒绝；`agent/subagent/patterns.py:81,108,136,179`。
  来源: 探针 `/tmp/probe_r2_d3.py`；`agent/subagent/patterns.py:81,108,136,179`

- **决策（Q2 量化，修正 R1 的「24 处」）**: `completed`/`failed` 的命名变更 blast radius 精确为：**权威 `_envelope`（`scheduler.run()` 返回）约 18 处断言**（`test_scheduler.py`、`test_workflow_spawn_bucket.py`、`test_aggregation_runtime.py`、`test_workflow_budget.py`、`test_budget_compat.py`）+ **父投影 2 处**（`test_bounded_envelope.py:163`、`test_workflow_tools.py:95`）+ **随 `run_pattern` 退役的 legacy 17 处**（`test_patterns.py`/`test_pattern_templates.py`，已在本 change 删除面）。R1 引用的「C2 的 24 处」来自 `scheduler.py:3010` 注释与 `workflow-result-aggregation` 归档评审，量级正确但口径不精确。**关键**: 父投影的 `completed`/`failed` **无任何 web/模型面消费者**（`web/static/workflow.js` 只用 per-node `item_states`/`itemsFailed`，不读 envelope 计数；全仓无 `parent_envelope()["completed"]` 断言）。
  理由: `rg '\["completed"\]|\["failed"\]' tests/` 实测 37 处，分类后如上；`rg 'parent_envelope\(\)\[' tests/` 空；`web/static/workflow.js:785,842` 读的是节点级 `itemsFailed`，非 envelope 计数。**「投影内重命名」这条路径不成立**：`parent_envelope()` 就是 `_envelope()` 的输出再 `pop("bus")` + `_bounded_node`（`scheduler.py:3100-3109`），字段名无法只在一侧改而不制造「同一字段两名并存」的第二语义。
  来源: `rg` 全仓统计；`agent/subagent/scheduler.py:3010,3100-3109`；`web/static/workflow.js:785,842`；`agent/tools/builtin/subagents.py`（无枚举消费）

- **决策（Q1 边界，前提成立）**: 「per-worker 明细不可达」的前提**成立且可复现**——per-worker 的 `result_ref` **只在 `RunPattern` 路径可达**，删它就构成**能力回归**，故补 `item_refs` 是**恢复**（in scope）而非新能力。同时它也是**纯 DSL foreach 路径的净新增能力**（今天一样拿不到），但二者共用同一套 `foreach` 机制，补在 `GetWorkflow` 上同时覆盖两类用户，故留在本 change 正当。
  理由: 探针 `/tmp/probe_r2_q1q2.py` 用**真实 DSL foreach 图**（非模板，`fan` 节点 3 项、worker 输出 6000 字触发落盘）：manager 里 `item[0..2] run.result_ref='artifact://workflow/wf_e2e6337e/...'` **存在**，但 `GetWorkflow(detail='nodes')` 返回的 `fan` 节点键集为 `['id','items','kind','reason','runs','status','subagent_id','summary']`——**无 `result_ref`、无 `item_refs`**；`_node_refs`（`subagents.py:792-803`）只读 `state.subagent_id`/`state.run_id`，foreach 容器节点这两字段恒 `None`（`scheduler.py:1883-1884`），故对该节点返回空。
  来源: 探针 `/tmp/probe_r2_q1q2.py`；`agent/tools/builtin/subagents.py:792-803`；`agent/subagent/scheduler.py:1883-1884`

- **决策（Q2 语义翻转复现）**: peer-review 在「producer 改一稿才获批」下，legacy（节点口径）`completed=2`、统一出口（run 口径）`completed=4`，**同一 `spec_hash`（`6ae2bf4e059a9283`）**；`parent_envelope` 与 `_envelope` 的 `completed`/`failed` 逐字相等（同一数据源）。R1 的对照实测本轮独立复现，无偏差。
  理由: 探针 `/tmp/probe_r2_q2b.py`——`legacy completed=2 failed=0 len(workers)=2` vs `envelope completed=4` / `parent completed=4`；`node runs: {'producer': 2, 'reviewer': 2, 'gate': 0, 'aggregate': 0}`。设计 `design.md:86` 的量化描述方向正确。
  来源: 探针 `/tmp/probe_r2_q2b.py`；`agent/subagent/patterns.py:386`（节点口径）、`agent/subagent/scheduler.py:3011-3020`（run 口径）

- **决策（Q3 vs #245 Non-Goal，重大澄清）**: 「资产工具对外行为不变」这条 Non-Goal **是本 change（#246）自己的设计约束**（`design.md:37`、`proposal.md:128`），**不是 #245 的承诺**——#245 的 Non-Goals（归档 `design.md:40-49`）根本没有此项，且它**显式把内置模板归一划给 #246**（原文：「**不做内置模板归一。** 内置 4 个 pattern 走代码内注册表（`PATTERNS`，`patterns.py:303-308`），不进磁盘资产层——那是 #246 的范畴。」）。故把按模板封闭的键校验应用到 `RunWorkflowAsset` 的 pattern 分支**不违反 #245**，只触碰 #246 自设的 Non-Goal，而 #246 有权在同一 change 内修订它。**实测资产路径今天确实放行跨模板键**：caller `params={"workers": 7}` 打到 peer-review 资产 → `status: graph_recursion_exceeded`（正常执行，`workers` 被静默忽略）；recipe 自身存 `{"workers": 9}` → 同样接受。
  理由: `rg '对外行为|资产工具|不改资产' openspec/changes/archive/2026-09-28-workflow-asset-persistence/{proposal,design}.md` **零命中**；`design.md:43`（#245）原文划界；探针 `/tmp/probe_r2_q3.py` 两用例均「接受 + 静默忽略」。
  来源: `openspec/changes/archive/2026-09-28-workflow-asset-persistence/design.md:40-49`；`openspec/changes/workflow-builtin-templates/design.md:37,121`；探针 `/tmp/probe_r2_q3.py`

- **决策（第 6 项，覆盖已闭合）**: 第一轮查出的两条未覆盖 Requirement（`multi-agent-collaboration/spec.md:540,560`）**已由 commit `8e34f53` 补入 delta**（本 change 的 `specs/multi-agent-collaboration/spec.md` 现含 6 条 Requirement，含「资产保存是显式的…」「资产的两类载体与参数化复用」两条 MODIFIED）。本轮全量复核：`openspec/specs/` 下 `RunPattern|run_pattern|OrcPattern` 共 **17 处命中 / 4 个文件**（multi-agent-collaboration 8、agent-runtime 7、subagents 1、web-ui 1），**全部**落在 4 个 delta 的 MODIFIED Requirement 覆盖内；四个 delta 无引用「改后不存在」的符号（`compile_pattern`/`RunWorkflow`/`spec_hash`/`GetWorkflow` 均存活）。`openspec/project.md` 零命中。
  理由: `git diff --stat 09e5fe8 8e34f53` 显示 delta 新增 57 行（两条 asset Requirement + 场景）；`rg -n 'RunPattern|run_pattern|OrcPattern' openspec/specs/` 输出 17 行逐条比对 delta 标题；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → `29 passed, 0 failed`。
  来源: `git diff 09e5fe8 8e34f53 -- openspec/changes/workflow-builtin-templates/specs/`；`rg` 全量；OpenSpec validate 输出

- **决策（第 7 项，工具面/文档）**: 删除面引用清理**基本完整但有两处精度缺口**。(a) `web/` 零 `RunPattern` 命中，无需改 web 工具清单；(b) 模块级 `RunPatternTool` import 共 **5 个测试文件**（`test_workflow_asset_tools.py:28`、`test_bus_bounded_exports.py:34`、`test_concurrency_queue.py:34`、`test_workflow_asset_context.py:23`、`test_patterns.py:21`），tasks 5.5/5.5a 点名了其中 4 个的处理，但 `test_bus_bounded_exports.py:34` 的模块级 import 与 `:207` 的 `test_run_pattern_tool_export_is_bounded` **未被 5.5 显式点名**（5.5 只说「出口 2」= `run_pattern` 的 bus 导出，未覆盖该文件里第二个测试与它的 tool import）——若只改「出口 2」会在收集期 ImportError；(c) **`SaveWorkflowAsset` 的工具描述字符串**（`subagents.py:948-951`「RunPattern-sourced graphs…」、`:960`「workflow_id returned by RunPattern/…」）是**留存工具的模型面文案**，需**改写**（非删除），tasks 未显式点名（5.8 的 grep 会命中，但「删净」措辞掩盖了「改写」性质）。`_worker_entry` 直调测试（`test_workflow_node_transcript.py:942`）已由 5.6a 覆盖；其余 D5 符号（`_AGGREGATE_NODE_IDS`/`_workers_from_node`/`_legacy_result`）在 `agent/`/`tests/`/`web/`/`benchmarks/` 下**无存活代码引用**（仅 `test_workflow_node_transcript.py:902` 一句注释提到 `_legacy_result`）。
  理由: `rg -n 'RunPattern|run_pattern' web/` 空；`rg -n 'RunPatternTool' tests/` 列出 5 个模块级 import；`rg -n 'RunPattern' agent/tools/builtin/subagents.py` 出 `:18`(import)`/416/437/445`(删)`)` 与 `:948,960`(描述文案)；`rg -n '_AGGREGATE_NODE_IDS|_workers_from_node|_legacy_result' agent/ tests/ web/ benchmarks/ | grep -v patterns.py` 仅注释。
  来源: `rg` 全量（见上）；`agent/tools/builtin/subagents.py:948-951,960`

### 第二轮 Open Questions

> Q1–Q4 推荐**整体不变**（第一轮方向正确），但 Q1/Q3 各补两条必须落进 design/spec 的订正；新增 Q5（值级参数校验）。每条配本 change 真实场景例子。

- **Q1（推荐不变；补三条订正证据）**: per-worker 的 `result_ref` 通道**必须补**（`GetWorkflow(detail='nodes')` 读 `item_runs` 吐 `item_refs`）。
  **具体场景（补订正）**：`RunWorkflow(template="orchestrator-worker", task="审查 3 个模块", params={"workers": 3})`，worker-1 失败、worker-2/3 成功。补 `item_refs` 后父 agent 收到 `item_refs: [{index:0, result_ref:"artifact://…"}（成功）, {index:1, result_ref:null, reason:"simulated failure"}（失败，**无 ref**）, {index:2, result_ref:"artifact://…"}]`——实测失败项 `run.result_ref=None`（`_mark_failed` 不落盘），所以**只有成功项可 `ReadWorkflowResult`**，这与 legacy `_worker_entry` 完全一致（不是净回归）；但 spec delta `line 142` 的「每个展开项的 `result_ref`…**可达**」在失败态下**说不到**，须改写为「成功项的 `result_ref` 经只读投影可达；失败项给出 bounded `reason`」。另一订正：若容器因预算 drain（如 `max_total_runs=2`）在派发前被拦，实测 6 个槽全 `subagent_id=None`——`item_refs` 必须**跳过空槽**，且整条数组应带一个显式的界（成功项 ≤ `max_runs`）或 `item_refs_omitted` 计数，否则 `params={"workers":100000}`（实测无上界 clone 成 10 万 item）会把只读出口重新撑成线性大数组。
  **推荐**：补——落到 `GetWorkflow(detail='nodes')`（非 `parent_envelope`，后者受本次 Non-Goal 与投影纪律双重保护），投影形状定为 `item_refs: [{index, subagent_id, run_id, result_ref?}]`（`result_ref` 仅成功项出现），并对空槽/超界明确处置。

- **Q2（推荐不变）**: 接受 run 口径 + 工具描述写明「`completed`/`failed` 数的是 run，不是 subagent」。
  **具体场景（本轮量化）**：peer-review 改一稿才获批 → legacy `completed=2`、统一出口 `completed=4`（同 `spec_hash`）。改名方案的实测代价：**权威 `_envelope` 约 18 处断言** + 父投影 2 处断言会红；**无 web/模型消费者**受影响。而「只在父投影里改名」不可行——`parent_envelope()` 是 `_envelope()` 的 `pop("bus")`+`_bounded_node`，改名会制造同字段双语义。故 (a) 接受 + 文档 是**最便宜也最安全**；(b) 改名收益（可读性）不抵 18+2 处断言与双语义维护成本；(c) 并暴露两字段翻倍契约面。
  **推荐**：维持 (a)。

- **Q3（推荐不变 + 修正 Non-Goal 归属 + 补值级校验）**: 按模板封闭，校验落 `compile_pattern`；**同步收紧 `RunWorkflowAsset`**。
  **具体场景（补订正）**：① 归属订正——「资产工具对外行为不变」是 **#246 自己**的 Non-Goal（`design.md:37`），#245 **无此承诺**且把模板归一显式划给 #246，故收紧资产路径**不违反 #245**，只需在本 change 内修订自己的 Non-Goal 口径（写成「仅拒绝对该模板无效的键，不改变有效键的语义」）。② 资产路径实测：给 peer-review 资材传 `params={"workers":7}` 今天被**静默忽略**（正常起图）——这正是 D1#5 要消灭的「以为 params 生效了」假象，若只紧 `RunWorkflow` 而放过 `RunWorkflowAsset`，该假象在资产路径原样存留。③ 落点：`compile_pattern` 是唯一 choke point（`run_pattern` 待删、`RunWorkflowAsset:1201`、benchmark `agent_runner.py:516` 不传 params），在此校验零破坏既有测试。
  **推荐**：在 `compile_pattern` 内做「按模板封闭键集」校验，`RunWorkflowAsset` 自动享受；同步修订 #246 自己的 Non-Goal 措辞。

- **Q4（推荐不变）**: `wait=false` 回执作为显式判别子的「正交第二形状」可接受。
  **具体场景（本轮补证）**：`RunWorkflow(template="bidding", task="选方案", wait=false)` 返回 `{status:"running", workflow_id, spec_hash, nodes:[]}`——本轮实测 `parent_envelope()` 为 **43 键**，与该 4 键回执键集不相交；回执 `status:"running"` 与终态集合不相交（`design.md:136` 的 7 个终态）。`wait` 是调用方显式声明，非服务端推断，符合 RIR「显式判别子」门槛。
  **推荐**：确认接受 + 工具描述硬写「回执非结果」；若要更稳可加 `started: true`。

- **Q5（新增）**: `params` 的校验是否**只有键名维**，还是**同时校验值类型/范围**？
  **具体场景**：模型（或资产 recipe）给出 `RunWorkflow(template="orchestrator-worker", task="t", params={"workers": "abc"})`——今天实测抛 `ValueError: invalid literal for int() with base 10: 'abc'`，经 AgentLoop 的 retry 折成**裸 `[Error: invalid literal…]`** 进入上下文（既非 `invalid_input`、也无自足 `reason`、还不可重试）；`{"workers": null}` 抛 `TypeError`。而 `{"workers": -5}` 被静默 clamp 成 1（不报、不提示）。三个值域问题（非整数 / null / 越界）今天的表现各不相同，这恰是 D1 规则 #5 与 D3 想统一的「入参校验」面。
  **推荐**：**同时校验值**——在 `compile_pattern` 的封闭键集校验里，对计数键要求「正整数（或可安全 `int()`）」、对 `worker_max_*` 要求数值，非法值一律 `invalid_input` 结构化拒绝（列出该模板可用键与取值约束）；**clamp 保留**（`0/-5 → 下界`是既有语义，不宜改），只把「无法转成数」这一类从裸异常改为结构化拒绝。**是否接受此口径变更请用户拍板**。

### 第二轮 Review Notes

- **（HIGH，须回写 spec delta 才可进入实现）** `specs/multi-agent-collaboration/spec.md:142` 的「对 `kind=="foreach"` 节点…暴露每个展开项的 `result_ref`，使 per-worker 全文在统一出口下**可达**」是对**失败/取消/预算超限项**的过度承诺（实测这些 run `result_ref` 恒 `None`）。必须改写为「成功项的 `result_ref` 可达；失败项给 bounded `reason`」，否则实现期为满足字面契约会去给失败 run 造 ref（超出本 change 范围）。

- **（HIGH）** `item_refs` 需显式界。`params={"workers": N}` 无上界（`patterns.py:81`），成功项数受 `max_runs`（默认 300）间接限制，但设计文本未声明该界，且既有 bounded 回归测试不覆盖 foreach。建议 `item_refs` 投影附 `item_refs_omitted`/`items_total`，并复用 `_PARENT_FIELD_LIMIT` 之外的一个固定数组上限。

- **（中）** `SaveWorkflowAsset` 描述（`subagents.py:948-951,960`）与 `run-pattern-web-demo.md`（整份）是**需改写**的模型面/文档文案，非单纯删除；tasks 5.8 的「零命中」措辞会把「改写」误当「删净」，建议在任务里显式区分。

- **（中，tasks 精度）** `test_bus_bounded_exports.py` 有**两个** `RunPattern` 相关测试（`:187` 出口 2 经 `run_pattern`、`:207` 经 `RunPatternTool`）与**一个模块级 tool import**（`:34`）；tasks 5.5 只以「出口 2」一词概括，实现时须把该文件整体处理（含删 `:34` 的 import），否则收集期 ImportError。

- **（低）** `bus.py:3` / `context.py:11` 模块 docstring 与 `scheduler.py:499-502` 的 `asset_source` 注释（自述「`RunWorkflow` 路径**从不**设置 `scheduler.spec`」，与 `run()` 在 `scheduler.py:795` 的 `self._spec = spec` 矛盾）三处措辞订正，tasks 5.4/5.9 已覆盖；本轮确认 `asset_source` 的唯一 pattern 写入点确为 `patterns.py:457-462`（与 R1 一致）。

- **（低，未解疑点）** Q1 的 `item_refs` 若落 `GetWorkflow(detail='nodes')`，其 `nodes` 上限是 `_PARENT_NODES_LIMIT=200`，但 `item_refs` 是**嵌套**在每个 foreach 节点下、不受该 200 约束——是否需要第二个「节点内 item_refs 上限」由实现定；本报告只判定「需要一个界」，具体数值留给实现。

### 第二轮结论

**可以进入实现**，但**先须用户答复 Q1（补 `item_refs` 的三条订正：跳过空槽 / 不承诺失败项 ref / 自带界）与 Q3（是否把按模板封闭的键校验同步到 `RunWorkflowAsset`，即修订 #246 自设的 Non-Goal）与新增 Q5（值级参数校验口径）**；Q2/Q4 推荐维持第一轮不动。**在 Q1/Q3/Q5 得到明确答复前，grill-confirmation-gate 仍拦截代码写。**

## Round 3

### 第三轮 Reviewer

- **run id**: `grill-workflow-builtin-templates-20260929-r3`；paseo agent id：`ddfce1af-9ac4-4bbb-bb58-4cece5d4c909`（零记忆独立评审者，与主 session 及 r1/r2 reviewer 均无共享上下文）
- **时间**: 2026-09-29
- **审视对象**: Q1–Q6 拍板后的 design.md / tasks.md / 4 spec deltas 的**可落地性**——「按此设计写代码会不会卡住、写出来的东西是否可测、每个已拍板项是否有机械可验证的落点」
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-builtin-templates-2026-09-29`, 分支 `workflow-builtin-templates/2026-09-29`, HEAD `7155efe`（基线 master `ee06df7`）
- **评审方法（零记忆独立复核，探针优先；本轮以「能不能落地」为准绳）**:
  - 实读：`agent/subagent/scheduler.py`（`_ItemRunSlot` 198-221、`_bounded_node` 383-405、`_envelope` 3005-3086、`parent_envelope` 3088-3110、`_execute_foreach` 1873-1941、`_run_foreach_item` 1943-1969、`_resolve_items` 2595-2615、`run()` 789-857、`cancel()` 757-783）、`agent/tools/builtin/subagents.py`（全部 20 个工具的 `@tool_parameters`、`GetWorkflowTool` 723-803、`_node_refs` 792-803、`RunWorkflowTool` 834-884、`StartWorkflow` 610-662、`RunWorkflowAsset` 1136-1240、`SaveWorkflowAsset` 942-1005、`_asset_from_scheduler` 905-938、`_invalid_spec` 493-506）、`agent/subagent/patterns.py`（全量 472 行）、`agent/subagent/workflow.py`（`WorkflowNode.max_items` 159/197/520、`_parse_max_items` 586-596、`_resolve_limits` 433-447）、`agent/subagent/manager.py`（`SPAWN_TOOL_NAMES` 425-434）、`agent/loop.py:62,398`、`benchmarks/agent_runner.py:505-529`、四个 spec delta、`#245` 归档 design/proposal/tasks
  - **探针（全在 `/tmp`，直接驱动真实调度器/工具/资产层；逐个已运行）**：
    - `/tmp/r3_probe1_itemrefs.py`——foreach 五态（正常 / 部分失败 / 预算 drain / 取消 / max_items 截断）的 `item_runs` 与 proposed `item_refs`；含 T1 时序与 T2 回边
    - `/tmp/r3_probe1b.py`（子命令 c/d/e/f）——预算 drain / 取消 / 50 项截断 / route 回边重跑容器
    - `/tmp/r3_probe3_maxitems.py`——`workers=N` 的 compile 期 vs 运行期 items；`max_items` 默认值来源
    - `/tmp/r3_probe4_exits.py`——**全部模型可见出口**中携带 `completed`/`failed` 的清单与形状
    - `/tmp/r3_probe5_q6.py`——四个模板各自计数键落哪个节点、`max_rounds` 是否吃 `max_items`
    - `/tmp/r3_probe6_maxrounds.py`——`peer-review` 永不批准时 `max_rounds=100000` 实际停在哪
    - `/tmp/r3_probe7_validation.py`——`compile_pattern` 今天的异常类型契约 + 已存跨模板资产
    - `/tmp/r3_probe8_assetreceipt.py`——`RunWorkflowAsset` 的 wait 两分支形状
  - 测试命令：`uv run pytest tests/benchmark/ -q` → **475 passed, 1 skipped**；`uv run pytest tests/agent/subagent/test_pattern_templates.py test_patterns.py test_bounded_envelope.py test_bus_bounded_exports.py test_workflow_asset_tools.py test_workflow_asset_context.py test_workflow_read_tools.py test_workflow_graph_snapshot.py -q` → **114 passed**；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **29 passed, 0 failed**

### 第三轮 Confirmed Decisions

- **决策（挑战 1，可落地 ✅）：Q1 的 `item_refs` 形状在四种「已派发」终态下**完全可从 `state.item_runs` 获得**；T1 时序成立（`item_runs` 在 `run()` 返回后仍填充），空槽/成功/失败/取消四类都区分得开。**唯一需在实现里写清的是 T2：route 回边重跑容器时 `item_runs` 被 `_execute_foreach` **整体重置**，只剩最后一轮（`fan.runs=2` 但 `len(item_runs)=2` 而非 4）。这是**既有语义**（同 `state.items`/`item_states` 一起归零，`scheduler.py:1890-1896` 注释明说 M2 的记账必须归零），对 `item_refs` 是**正确的**（否则会吐同一 index 的陈旧 run），但设计文本需显式声明「`item_refs` 反映容器的**最后一轮**展开，不是历史所有轮」——否则实现者会照着 `fan.runs`（跨轮累计）去期待长度对不上而卡住。
  理由: 探针 `/tmp/r3_probe1b.py f`（`fan.runs(total across rounds)=2`、`len(item_runs)=2`、两条都带 `result_ref`）；`/tmp/r3_probe1_itemrefs.py` A（3 槽全 fill、全 `result_ref`）、B（index=1 `status='failed' result_ref=None reason='simulated failure of item 1'`，index=0/2 带 ref）、C（`max_total_runs=2`/6 项 → `status=blocked item_states=['pending']*6`，6 槽全空 → `item_refs=[] items_total=6 item_refs_omitted=6`）、D（取消后 3 槽全 fill、`status='cancelled' result_ref=None`）、E（50 项 → `items=20`，20 槽全 fill 全带 ref）。空槽跳过 → `items_total`/`item_refs_omitted` 可直接算（C 行实测 `items_total=6 emitted=0 omitted=6`）。
  来源: 探针 `/tmp/r3_probe1_itemrefs.py`、`/tmp/r3_probe1b.py`；`agent/subagent/scheduler.py:1890-1896`（`item_runs` 重初始化）、`:2199-2208,2225`（`_launch_run` 写槽）、`:1898-1902`（`state.items = len(items)`）

- **决策（挑战 1 附带，可落地 ⚠️ 有落地歧义）：未派发空槽的计数语义有两种合理读法，设计文本没有钉死，实现者会二分。** 空槽在「预算 drain 前被拦」时是「容器本轮未派发该项」（C 用例），设计说「跳过未派发的空槽」+「`items_total`/`item_refs_omitted`」——但 `items_total` 应等于 `len(state.item_runs)`（=6，含空槽）还是 `state.items`（=6）还是「已派发数」（=0）？`item_refs_omitted` 应等于 `items_total - len(item_refs)`（=6，把空槽计为 omitted）还是只计「因固定条数上限被砍」的项？**spec delta 的措辞（`...:144`「自带固定条数上限并显式报告被省略的项数」）把 omitted 绑在「条数上限」上，而 C 用例里 omitted 全来自空槽（非上限）**——这两个来源混在一个字段里会让断言写不下去。**这不是需用户拍板的设计抉择，而是实现前必须钉死的字段定义**（建议：`items_total = len(item_runs)`，`item_refs_omitted = items_total - len(item_refs)`，理由单一、可测）；列在下方 Review Notes 供实现择定。
  理由: 探针 C 用例 `items_total=6 item_refs_omitted=6` 的读数依赖「omitted 含空槽」；而 spec delta `:144` 的 omitted 语义只提「固定条数上限」。两处口径不一致 ⇒ 测试作者无法写出唯一断言的期望值。
  来源: `agent/tools/builtin/subagents.py:770-781`（现 `_node_refs` 无 omitted 概念）；`openspec/changes/workflow-builtin-templates/specs/multi-agent-collaboration/spec.md:144`；探针 `/tmp/r3_probe1b.py c`

- **决策（挑战 2，可落地 ✅）：`compile_pattern` 确实是**唯一** choke point——全仓 `rg` 后除自身定义与待删的 `run_pattern` 外，只有两个生产调用方（benchmark `_run_template_pattern`、`RunWorkflowAsset` pattern 分支），且**没有任何代码绕过它直调 `PATTERNS[...].compile()` 或 `OrcPattern.build()`**。benchmark `template` 臂**不传 params**（`compile_pattern(self.template_pattern, task=problem_statement)`，无 `params=`），故在 `compile_pattern` 内加键/值/上界校验对它**零影响**；实测 `uv run pytest tests/benchmark/ -q` → **475 passed, 1 skipped**（含 `test_workflow_modes.py` 的 `test_template_mode_runs_pattern_and_reports_orchestration`）。
  理由: `rg -n 'PATTERNS\[|\.compile\(\)|OrcPattern\(' agent/ benchmarks/ tests/ web/ scripts/` 仅命中 `patterns.py:243`（即 `compile_pattern` 自身）；`compile_pattern` 调用点全仓 4 处（`patterns.py:243` 定义、`:447` 待删的 `run_pattern`、`agent_runner.py:516`、`subagents.py:1201`）+ 测试 3 处；benchmark 全绿输出 `475 passed, 1 skipped in 32.03s`。
  来源: `benchmarks/agent_runner.py:516`；`agent/tools/builtin/subagents.py:1201`；`agent/subagent/patterns.py:241-243`；`rg` 输出；pytest 输出

- **决策（挑战 3，可落地 ⚠️ 但有 HIGH 级语义缺口）：Q6 的「计数键 > `max_items` → 拒绝」规则能正确消除 template 路径的静默截断，且读的是对的 `max_items`（模板节点一律吃默认 20，从不覆写）；**但该规则的适用面与 design 的措辞不匹配**——它只覆盖 `workers`/`teams`/`proposers`（落到 foreach 节点、被 `_resolve_items` 的 `items[:max_items]` 截断），**不覆盖 `max_rounds`**（落到 route 节点的 `max_routes`，根本不吃 `max_items`）。实测 `peer-review` 在永不批准时 `max_rounds=3/20/25/100000` **全部**停在 `graph_recursion_exceeded`、`steps=25`、`producer.runs=9`——即 `max_rounds=100000` 的真实效果是「静默只跑约 9 轮」，与 Q6 要消灭的 `workers=100000` 是**同一类假象，但逃出了该规则**。design 的 Q6 文本写「计数键（`workers`/`teams`/`proposers`）」时确实没列 `max_rounds`，故字面无矛盾；但 §Open Questions Q6 的论证「校验层拒绝计数键 > 既有 `max_items`」若被实现为「对所有 params 键套 `> max_items`」，会把 `max_rounds`（本就该 > 20 的合法值，peer-review 常见 3-10，但 25/50 也可能）误拒。**必须在实现里按模板分别取界**：`workers`/`teams`/`proposers` 对 `max_items`（20），`max_rounds` 对 `recursion_limit`（25），否则要么漏 `max_rounds` 的静默截断、要么误拒合法 `max_rounds`。
  理由: 探针 `/tmp/r3_probe3_maxitems.py`——`compile_pattern("orchestrator-worker", params={"workers":25})` → spec `len(items)=25` 但节点 `max_items=20`、运行期 `state.items=20 runs=20`（静默截断确认）；`workers=20→20`、`workers=5→5`。`/tmp/r3_probe5_q6.py`——`max_rounds=25` 落到 `gate` 节点 `max_routes=25`、`max_items=20`（不相干）；`peer-review` 无 foreach 节点。`/tmp/r3_probe6_maxrounds.py`——`max_rounds=3/20/25/100000` 全部 `status='graph_recursion_exceeded' steps=25 diag.recursion_limit=25 producer.runs=[9]`（`max_rounds≥25` 三者读数逐字相同 ⇒ 静默被 `recursion_limit=25` 截断）。模板节点 `max_items` 恒 20：`WorkflowNode.max_items` 默认 20（`workflow.py:159`）、`_parse_max_items` 只在 spec 显式给了才覆盖，四个 `_template_*` 的 `build()` 返回的 raw dict **不含 `max_items`**（探针 `/tmp/r3_probe3_maxitems.py` 的 `(c)` 行 `'max_items' in raw node: False`），故「reject > max_items」读的永远是默认 20、不可能读到非默认值（只有手写 DSL spec 才能把 `max_items` 提到 30+，那是 spec 路径、不经本校验）。
  来源: 探针 `/tmp/r3_probe3_maxitems.py`、`/tmp/r3_probe5_q6.py`、`/tmp/r3_probe6_maxrounds.py`；`agent/subagent/patterns.py:81,108,136,179`；`agent/subagent/scheduler.py:2613-2615`；`agent/subagent/workflow.py:159,520,586-596`；`openspec/changes/workflow-builtin-templates/design.md:215-217`；`openspec/changes/workflow-builtin-templates/tasks.md:18`

- **决策（挑战 4，可落地 ⚠️ 有遗漏面）：Q2 的「completed/failed 数的是 run」口径必须写进**两个**模型可见出口，而不是只有 `RunWorkflow` 一个。实测四个工具返回含 run 口径的 `completed`/`failed`：`RunWorkflow(wait=true)`/`StartWorkflow(wait=true)`/`GetWorkflow(任意 detail)` 返回 bounded `parent_envelope()`（含 `completed`/`failed`），**`RunWorkflowAsset(wait=true)` 返回的是权威 `_envelope()`（46 键、含 `bus`、无 `nodes_total`——非 bounded！）**。tasks 2.2a 只点名了 `RunWorkflow` 描述 + 「检查其余模型可见出口（GetWorkflow/DeclareWorkflow/SaveWorkflowAsset）」，**漏了 `RunWorkflowAsset` 与 `StartWorkflow`**——这两个都返回带 `completed`/`failed` 的结果体，`StartWorkflow` 与 `RunWorkflow` 同口径（都是 `parent_envelope()`），`RunWorkflowAsset` 虽非本 change 直接改的工具、但其 `completed`/`failed` 语义与新口径一致（同一 `_envelope` 源），模型若按旧节点口径读它同样会误判。**不存在任何一处仍写着旧的「节点口径」文档**（旧口径只活在 `_legacy_result` 与已归档 spec 里，均随本 change 退役）。
  理由: 探针 `/tmp/r3_probe4_exits.py`——`parent_envelope` 含 `completed/failed` 不含 `bus`；`_envelope` 含 `bus`；`GetWorkflow(detail='nodes')` 顶层含 `completed`、foreach 节点键集 `['id','items','kind','reason','runs','status','subagent_id','summary']`（无 `result_ref`/`item_refs`——Q1 尚未落）；`StartWorkflow(wait=true)` 含 `completed=2` 不含 `bus`；`RunWorkflowAsset(wait=true)` `has 'bus': True keys count: 46`（权威 envelope）。`list_pending` 无。`rg` 全仓确认旧节点口径的唯一载体是 `patterns.py:386`（待删）与 `openspec/specs/` 存量条（6.6a 覆盖）。
  来源: 探针 `/tmp/r3_probe4_exits.py`；`agent/tools/builtin/subagents.py:723-745,835-884,942-963`；`agent/subagent/scheduler.py:3011-3021,3088-3110`；`openspec/changes/workflow-builtin-templates/tasks.md:26`

- **决策（挑战 5，可落地 ⚠️ 有 GAP）：`RunPattern` 残留清扫**总体覆盖完整，但**至少 4 处命中不在任何 task 的「删/改」点名里**，且 tasks 5.8 的 grep 模式**不匹配 `OrcPattern`**（模式是 `run_pattern|RunPattern|_legacy_result|_worker_entry`，大小写与 `OrcPattern` 无交集）。逐命中分类见下方 Review Notes 的「RunPattern 残留清扫表」。最实质的 GAP 是 **`agent/subagent/patterns.py:247` `_AGGREGATE_NODE_IDS` 之外，`OrcPattern` 在 `agent/` 下有 6 处存活引用（基类+4 子类+`PATTERNS` 类型标注），它们是**保留面**（design 说保留），故不算删净 GAP**；但 `docs/interview-bullets/walkthrough.md` 的 8 处、`docs/interview-script/run-pattern-web-demo.md` 的 8 处、`docs/agent-internals.md:1029` 共 17 处 `RunPattern` 命中**中，**`walkthrough.md:1123` 的「10 个工具表」与 `:1166` 的「10 个 LLM 可见子 agent 工具」是口径变更（10→9），tasks 6.4 写了「工具数 10→9 的叙述一并订正」但**没有像 6.4 开头那样逐文件点名 walkthrough.md 的这两行**——6.4 的列举里 walkthrough.md 只写了「14 处」而实际 `rg -c` 是 **8 处**（口径不符，可能漏扫）。**`openspec/specs/` 的 17 处**由 6.6a 覆盖（已确认）、tasks 5.8 已把 `openspec/specs/` 纳入扫描范围。
  理由: 全仓 `rg` 输出见下方表格；`rg -c 'RunPattern' docs/interview-bullets/walkthrough.md` = **8**（tasks 6.4 写「14 处」——与实测不符）；`OrcPattern` 在 `agent/` 下 6 处均属 design §D5 的「保留」面；`test_bus_bounded_exports.py` 的 `:34` 模块级 import 由 5.5b 覆盖（R2 已抓）、`test_concurrency_queue.py:34,39,653` 由 5.5 覆盖。
  来源: `rg` 全仓输出；`openspec/changes/workflow-builtin-templates/tasks.md:52-60,67`；`agent/subagent/patterns.py:247-308`

- **决策（挑战 6，可落地 ⚠️ 有陈旧措辞）：Q3 收紧后，design.md 的 Non-Goal 已带 R2 订正（`:37`），但**仍保留了会误导实现的字面标题**「不改资产 schema 与 4 个资产工具的**对外行为**」——尽管其后紧跟「R2 订正：准确口径是不改 schema、不改变**有效键的语义**」。**"对外行为"四字与 Q3 的「收紧资产路径」在字面冲突**：实现者若只读标题会以为不能动资产路径的校验。对照 `#245` 归档文档确认：`#245` **无任何**「资产工具对外行为不变」的承诺（`rg '对外行为|资产工具|不改资产' #245 归档 proposal/design = 零命中`），且 **`#245` design.md:45 逐字把模板归一划给 #246**：「**不做内置模板归一。** 内置 4 个 pattern 走代码内注册表（`PATTERNS`，`patterns.py:303-308`），不进磁盘资产层——那是 #246 的范畴。」（`proposal.md:116` 同口径）。故 Q3 的收紧**不违反 #245**；只需把本 change 自己的 Non-Goal 标题从「不改…对外行为」改为「不改资产 schema、不改变**有效键的语义**（拒绝该模板无效的键不算违反）」，消除字面冲突。
  理由: `sed -n '32,40p' design.md` 显示 `:37` 标题仍是「不改资产 schema 与 4 个资产工具的对外行为」；`rg -n '不改资产|对外行为' design.md proposal.md` 命中 2 处（design `:37,132` + proposal `:128` 已带订正）；`#245` 归档 `design.md:45`、`proposal.md:116` 逐字引用 liness；`rg '对外行为' openspec/changes/archive/2026-09-28-workflow-asset-persistence/` **零命中**。
  来源: `openspec/changes/archive/2026-09-28-workflow-asset-persistence/design.md:45`、`proposal.md:116`；`openspec/changes/workflow-builtin-templates/design.md:37,132`；`openspec/changes/workflow-builtin-templates/proposal.md:128`

### 第三轮 Open Questions

**新增 1 条（Q7）——其余为标准 `Q1–Q6` 的落地注记，不需再拍板。**

- **Q7**: Q6 的「计数键 > `max_items` → 拒绝」是否**同样覆盖 `max_rounds`**？若不覆盖，`max_rounds=100000` 仍是**静默截断**（实测停在 `recursion_limit=25`），只是截断点从「20」换成「25」——与 Q6 要消灭的假象**同类**，且 `max_rounds` 与 `workers` 在 `params` 里是并列的「计数键」，用户对「计数键应显式拒绝超界」的意图很难说只针对其中三个。
  **具体场景**：模型调 `RunWorkflow(template="peer-review", task="把方案改到批准", params={"max_rounds": 100000})`——它以为「给足轮次直到批准」。**今天**：图实际跑 9 轮 producer（`producer.runs=9`）后以 `status='graph_recursion_exceeded'`、`steps=25` 结束（实测 `max_rounds=25/100000` 读数逐字相同：`completed(runs)=17 producer.runs=[9] steps=25 recursion_limit=25`），模型看到的只是「超了递归上限」，无法知道 `max_rounds=100000` 从未生效。**Q6 若只对 `workers`/`teams`/`proposers` 拒绝**：`max_rounds=25`（合法、常见）放行、`max_rounds=100000` 放行 → 静默截断存续；**若对全部计数键套 `> max_items=20`**：`max_rounds=25` 也会被误拒（而 25 恰是 `recursion_limit` 默认值、是 peer-review 的合理上限）。两条路都不好。
  **推荐**：**按模板分别取界并全部拒绝超界**——`workers`/`teams`/`proposers` 的界是 `max_items`（20），`max_rounds` 的界是 `recursion_limit`（25，正因为它落到 route 的 `max_routes` 而 route 受 `recursion_limit` 约束）；两个界都是**既有**闸（不造第二套上界，符合 Q6 精神）。`reason` 分别写明「该模板的并行位次上限来自 `max_items`」/「该模板的轮次上限来自 `recursion_limit`」。是否接受请用户拍板；若用户认为 `max_rounds` 的静默截断可接受，则须在 design/spec 显式声明「`max_rounds` 不在本校验范围内、超 `recursion_limit` 由既有闸处理（现状保留）」——不能默认留白。

### 第三轮 Review Notes

**RunPattern 残留清扫表**（全仓 `rg -n 'RunPattern|run_pattern|_legacy_result|_workers_from_node|_worker_entry|_AGGREGATE_NODE_IDS|OrcPattern'`，排除 `.git`/`.pyc`；分类 a=将删 b=须改写 c=change/archive 历史合法保留 d=tasks 未覆盖的 GAP）：

| 命中位置 | 现状 | 分类 | tasks 覆盖 |
|---|---|---|---|
| `agent/subagent/patterns.py:11`（docstring 描述 `run_pattern`） | 模块 docstring | **b 改写** | 5.2 ✅ |
| `agent/subagent/patterns.py:247` `_AGGREGATE_NODE_IDS` | 死代码 | **a 删** | 5.2 ✅ |
| `agent/subagent/patterns.py:314,324,329,333,376,379,384,410,429,456,467`（`_workers_from_node`/`_worker_entry`/`_legacy_result`/`run_pattern`） | 死代码 | **a 删** | 5.2 ✅ |
| `agent/subagent/patterns.py:255,283,288,293,298,303`（`OrcPattern`+4 子类+`PATTERNS`） | **保留面** | **保留** | ✔（D5 明列保留；5.8 grep 不匹配，见 Review Notes） |
| `agent/tools/builtin/subagents.py:18`（`import … run_pattern`） | import | **a 删** | 5.1/5.2 ✅ |
| `agent/tools/builtin/subagents.py:416,437,445`（`RunPatternTool`） | 工具本体 | **a 删** | 5.1 ✅ |
| `agent/tools/builtin/subagents.py:948,960`（`SaveWorkflowAsset` 描述「RunPattern-sourced」「returned by RunPattern/…」） | **模型面文案** | **b 改写** | 5.10 ✅ |
| `agent/loop.py:62,398`（import + 注册） | 注册 | **a 删** | 5.1 ✅ |
| `agent/subagent/manager.py:427`（`SPAWN_TOOL_NAMES`） | 枚举 | **a 删** | 5.3 ✅ |
| `agent/subagent/bus.py:3,208,211`（docstring 三处） | docstring | **b 改写** | 5.4/5.9 ✅ |
| `agent/subagent/context.py:11`（docstring） | docstring | **b 改写** | 5.9 ✅ |
| `agent/subagent/scheduler.py:499,502`（`asset_source` 注释 + `run_pattern` 措辞） | 注释 | **b 改写** | 5.9 ✅ |
| `benchmarks/agent_runner.py:518`（注释「与 `RunPatternTool` 同路」） | 注释 | **b 改写** | 5.9 ✅ |
| `docs/agent-internals.md:1029`（工具清单树） | 文档 | **b 改写** | 6.2 ✅ |
| `docs/interview-script/run-pattern-web-demo.md`（整份 8 处） | 文档 | **b 改写** | 6.4 ✅（处数对） |
| `docs/interview-bullets/walkthrough.md`（8 处） | 文档 | **b 改写** | 6.4 ⚠️（写「14 处」，实测 8；工具数 10→9 未给行号） |
| `docs/interview-script/walkthrough/W03-multi-agent.md:19,44`（2 处） | 文档 | **b 改写** | 6.4 ✅ |
| `docs/interview-script/questions/Q08-multi-agent.md:54`（1 处） | 文档 | **b 改写** | 6.4 ✅ |
| `docs/interview-bullets/interview-prep.md:225`（1 处） | 文档 | **b 改写** | 6.4 ✅ |
| `docs/openspec-change-backlog.md:104,122`（本 change 条目自身） | change 自述 | **c 合法** | 6.1/6.6 ✅ |
| `openspec/specs/` 17 处 / 4 文件 | 存量 spec | **b 改写（经 delta 同步）** | 6.6a ✅ |
| `tests/agent/subagent/test_pattern_templates.py`（`run_pattern` 全量） | 测试 | **a 删/改** | 5.5 ✅ |
| `tests/agent/subagent/test_patterns.py:17,21,58-…`（`run_pattern`/`RunPatternTool`） | 测试 | **a 删/改** | 5.5 ✅ |
| `tests/agent/subagent/test_workflow_asset_tools.py:28,121` | 测试（模块级 import） | **b 改写** | 5.5a ✅ |
| `tests/agent/subagent/test_workflow_asset_context.py:23,165,191-226` | 测试 | **b 改写** | 5.5a ✅ |
| `tests/agent/subagent/test_bus_bounded_exports.py:34,174,187,207` | 测试（模块级 import + 2 测试） | **a 删/改** | 5.5b ✅ |
| `tests/agent/subagent/test_concurrency_queue.py:34,39,522,653` | 测试 | **b 改写** | 5.5 ✅ |
| `tests/agent/subagent/test_guardrails.py:62,191` | 测试 | **b 改写** | 5.5/5.7 ✅ |
| `tests/web_tests/test_workflow_node_transcript.py:894-932`（出口 4 经 `run_pattern`） | 测试 | **b 改写** | 5.6 ✅ |
| `tests/web_tests/test_workflow_node_transcript.py:937-946`（直调 `_worker_entry`） | 测试（收集期 ImportError） | **b 改写** | 5.6a ✅ |
| `tests/agent/subagent/test_bounded_envelope.py:207-210`（`run_pattern` 读 bus） | 测试 | **b 改写** | 5.5 ✅ |
| `tests/agent/subagent/test_workflow_cycle_contract.py:23,325`（`compile_pattern`，**非** RunPattern） | 测试（保留面） | **保留** | ✔ |
| `openspec/changes/archive/**`（历史归档） | 历史 | **c 合法** | — |

**表结论**：唯一 d 类（GAP）已在 Confirmed Decision 5 说明——无「漏删死符号」，但有 3 处**精度**缺口：(i) tasks 6.4 的 `walkthrough.md` 处数（14≠8）与工具数行号未给；(ii) tasks 5.8 grep 不匹配 `OrcPattern`/`PATTERNS`（保留面，需在 5.8 声明豁免，否则误删）；(iii) `_workers_from_node`/`_AGGREGATE_NODE_IDS` 的**删除面**覆盖完整（5.2 列了），无遗漏。

- **（HIGH，须回写 spec delta 才可定实现）** `item_refs` 的 `items_total`/`item_refs_omitted` **字段定义未钉死**（见 Confirmed Decision 2）。spec delta `multi-agent-collaboration/spec.md:144` 把 `omitted` 绑在「固定条数上限」上，而预算 drain 用例（`/tmp/r3_probe1b.py c`，6 槽全空）的 `omitted=6` 全部来自空槽。建议在 delta 里写明：`items_total = len(state.item_runs)`（= 本轮展开项数），`item_refs_omitted = items_total - len(item_refs)`（涵盖空槽 + 超固定上限两类），并加一条「固定上限」的具体数值/来源（R2 已指出需要一个界，本轮确认该界仍**未给数值**）。否则 task 4.6 的测试无法写出唯一期望。

- **（HIGH）`max_rounds` 的静默截断未被任何 decided 项覆盖**（见 Q7）：`peer-review` 的 `max_rounds` 落到 `max_routes`、受 `recursion_limit=25` 约束，`max_rounds=100000` 实测静默停在 9 轮 producer。tasks 1.2b 只写了「计数键（`workers`/`teams`/`proposers`）」——字面正确但留下了这个同类假象。**这是本轮唯一的 HIGH 级可落地性缺口**：不是「写不出来」，而是「照 tasks 写完会留下一个与 Q6 动机同类的静默截断，且没有任何任务会发现它」。

- **（中）`RunWorkflowAsset(wait=true)` 返回**权威** `_envelope()`（46 键、含 `bus`、无 `nodes_total`）**，不是 `parent_envelope()`（探针 `/tmp/r3_probe4_exits.py` 实测 `has 'bus': True keys count: 46`）。这不是本 change 引入的（既有行为），但 Q2 的「completed/failed 数的是 run」口径若只写进 `RunWorkflow` 描述，模型从 `RunWorkflowAsset`/`StartWorkflow` 读到同一字段时没有对应说明。tasks 2.2a 的「检查其余模型可见出口」应显式列出 `StartWorkflow`（同 `parent_envelope()`）与 `RunWorkflowAsset`（返回 `_envelope()`）两个，而非举例式列举。另注：`agent-runtime` spec delta 的 `Scenario: 父 agent 的编排结果投影不含 bus` 只约束 `parent_envelope`，`RunWorkflowAsset` 的 `_envelope` 含 `bus` 与该 Requirement 不矛盾（它明写「当前为 `ReadBus` 与调度器权威 `_envelope()`」），但实现者需知道 `RunWorkflowAsset` 走的是后者、不在「不含 bus」的范围内。

- **（中）tasks 6.4 的文件处数与实测不符**：`docs/interview-bullets/walkthrough.md` 实测 `rg -c RunPattern` = **8**，tasks 6.4 写「14 处」；`docs/interview-script/run-pattern-web-demo.md` 实测 8 处（tasks 写「8 处」，对）。且 6.4 未逐行点名 `walkthrough.md:1123`（工具表「10 | RunPattern」行）、`:1166`（「10 个 LLM 可见子 agent 工具」）、`:567`（「10 个 LLM 可见子 agent 工具」树注释）三处**工具数 10→9** 的口径点——它们不是 `RunPattern` 字符串命中（`1123` 含 `RunPattern`，`567`/`1166` 是「10 个」），6.4 末句「工具数 10→9 的叙述一并订正」在语义上覆盖，但未给行号，实现时易漏。建议在 6.4 补行号。

- **（中）tasks 5.8 的删净 grep 不匹配 `OrcPattern`**：模式 `run_pattern|RunPattern|_legacy_result|_worker_entry` 与 `OrcPattern` 无交集。`OrcPattern` 是**保留面**（design §D5 明列保留 `OrcPattern` 及四个子类），故不是删净 GAP；但 5.8 若被当作「全仓零 `RunPattern`」的证明，它对 `OrcPattern`（6 处）与 `PATTERNS` 无覆盖——需在 5.8 明确「`OrcPattern`/`PATTERNS`/`_template_*` 属保留面，不在零命中范围」，避免实现者看到 `rg OrcPattern` 有命中而误删。

- **（低）已存跨模板资产在 Q3 收紧后会在**加载期**被拒**：既有 `WorkflowAsset(source="pattern", recipe={"pattern":"peer-review","params":{"workers":9}})` 今天可存可载可编译（`workers` 静默忽略），Q3 收紧后其 `RunWorkflowAsset` 加载路径会被 `compile_pattern` 拒绝（探针 `/tmp/r3_probe7_validation.py`）。tasks 1.2/1.2a/1.2b 无「已存资产迁移/兼容」项。这是**设计上可接受**的（该资产本就带无效果键），但应在 delta 或 tasks 显式记一句「历史 recipe 中的无效键在加载期被拒是预期行为」，否则会被当成回归。

- **（低）校验异常类型契约**：`compile_pattern` 今天对未知模板名抛 `KeyError`、对非法值抛裸 `ValueError`/`TypeError`（探针 `/tmp/r3_probe7_validation.py`）。新增校验要让两个调用方各自翻译成 `invalid_input`（`RunWorkflow`）与 `invalid_asset`（`RunWorkflowAsset`，其 catch 是 `except (KeyError, WorkflowValidationError)`）。`WorkflowValidationError` 是 `ValueError` 子类（探针实测 mro），故**若新校验统一抛 `WorkflowValidationError`**，`RunWorkflowAsset` 的既有 catch **自动兜住**（零改动）、`RunWorkflow` 侧需新增 `except WorkflowValidationError -> invalid_input`；这是最省的落法，建议在 tasks 1.1/1.2 写明「统一抛 `WorkflowValidationError`，两调用方各自翻译」，否则实现者可能另造异常类型导致资产路径漏兜。

- **（低）T2 时序注记**：`_execute_foreach` 在每次进入时把 `state.item_runs` 整体重置（`scheduler.py:1890-1896`）。对 `item_refs` 是正确语义（只反映最后一轮），但 task 4.6 的测试若用带回边的图（如 peer-review 不适用、但自定义 foreach+route 适用）会看到 `len(item_refs) == 最后一轮展开数` 而非 `fan.runs`（跨轮累计），需在测试里用正确期望值。design D2 未提这一条。

### 第三轮结论

**基本可落地，但有 1 条 HIGH 级缺口（Q7：`max_rounds` 的静默截断未归位）阻塞「Q6 已完整闭环」的判定**；其余 decided 项（Q1–Q5）均有可验证落点，探针实测 5 种终态、2 个 choke point 调用方、4 个模型可见出口、17 处文档残留、#245 归属引证全部通过。**建议：先把 Q7 抛给用户拍板（`max_rounds` 是否同样拒绝 > `recursion_limit`），并顺手钉死 `items_total`/`item_refs_omitted` 的字段定义（Review Notes 第 1 条）与 tasks 6.4/5.8 的行号-口径精度**，然后即可进入实现；不存在「写不出代码」的硬阻塞，只有「照 tasks 写完会留下一个未被任何任务发现的静默截断」这一处需先闭合。
