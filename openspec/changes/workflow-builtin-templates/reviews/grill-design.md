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

- （待用户答复后由主 session 填入）
