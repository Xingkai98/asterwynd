# Building Review: workflow-builtin-templates

## Reviewer

- **run id**: `review-workflow-builtin-templates-20260929-r1`；paseo agent id `6061c681-6a22-44fc-ae86-7539819db4a8`
- **时间**: 2026-09-29
- **base/head**: base `ee06df7`（merge-base 实测 `git merge-base HEAD master` = `ee06df7`）/ head `e23748a`
  - **注意（审阅期间 HEAD 前移）**：审阅开始时 head = `d5af96c`（本轮全部代码/测试实现）。审阅过程中实现者提交了 `e23748a`（仅 `tasks.md` 勾选 + `workflow-events.jsonl` + backlog 状态，不含代码）。本报告的代码结论对 `d5af96c` 的 diff 成立，`e23748a` 只影响任务勾选与收尾证据的核验（见 Issues HIGH-1）。
- **verdict**: **CHANGES_REQUESTED**

---

## Task Verification

逐条核验 `tasks.md` 的 `- [x]`。**代码实现面（任务 1–5）全部可核实为真**；**收尾面（5.8 / 6.5 / 6.6 / 6.6a / 6.8 / 6.9）有已勾选但未兑现的项**。

### 1. 共享配方编译路径（D3 / D4）—— 全部为真

- **1.1** `compile_recipe` 落于 `agent/subagent/patterns.py:359-382`；内部转调 `compile_pattern`；未知模板名抛 `WorkflowValidationError`（`patterns.py:375-378`）。证据：`/tmp/rev246/probe3_params.py` 末段 `compile_recipe("nope")` → `WorkflowValidationError: unknown template 'nope'; available: [...]`。
- **1.2 / 1.2a / 1.2b / 1.2c** `_TEMPLATE_PARAMS`（`patterns.py:246-266`）按模板封闭键集；`_coerce_count` / `_coerce_budget`（`patterns.py:277-306`）做值级校验（`bool` 显式排除）；`_FANOUT_CAP`（`patterns.py:269`）取 `WorkflowNode.max_items` 默认 20；`validate_template_params`（`patterns.py:308-339`）在模板 `build()` **之前**调用（`patterns.py:351`）。探针逐项见下「Probe Evidence 3」。
- **1.3** 单测齐备且带对照合法路径：`tests/agent/subagent/test_pattern_params.py`（跨模板键 `:30`、未知键 `:36`、reason 列可用键 `:41`、值类型 `:51-70`、clamp `:99-108`、上界 `:114-133`、**对照 `test_fanout_count_at_cap_is_accepted:123`**）。
- **1.4** `uv run pytest tests/benchmark/ -q` 实测 **475 passed, 1 skipped**，与 tasks 记录的 R3 基线逐数字一致（benchmark `template` 臂 `benchmarks/agent_runner.py:516` 仍直调 `compile_pattern` 不传 params）。
- **1.5** 新校验统一抛 `WorkflowValidationError`；`RunWorkflowAsset` 侧 catch 已收敛为 `except WorkflowValidationError`（`agent/tools/builtin/subagents.py:1333`）。实测资产路径非法 params → `invalid_asset`（probe5）。
- **1.6** 历史 recipe 兼容说明落在 spec delta「非法 params 在编译前被结构化拒绝」（`openspec/changes/workflow-builtin-templates/specs/multi-agent-collaboration/spec.md:136-142`）。
- **1.7 / 1.8** `_truncation_diagnostics`（`agent/subagent/scheduler.py:898-923`）经 `_mark_graph_recursion_exceeded` 并入 `_diagnostics`；实测经**模型面出口** `RunWorkflow` 返回 `declared_max_rounds=25` / `rounds_actually_run=8`（int）/ `limit_source='recursion_limit:25'`；纯 DSL 图三字段 `None`（probe4）。

### 2. 统一 Workflow 入口的 template 输入（D1）—— 全部为真，**但 2.2b 部分未兑现**（见 MED-1）

- **2.1 / 2.3 / 2.4 / 2.5** `RunWorkflowTool.execute` 判别 + 五条结构化拒绝（`subagents.py:948-999`）；template 分支走 `compile_recipe` 后与 spec 分支汇合到同一 `_drive_scheduler`（`subagents.py:635-648`）。单测 `tests/agent/subagent/test_run_workflow_template.py`（互斥 `:79`、都无 `:86`、缺 task `:92`、未知名 `:99`、spec 带 params `:107`、spec 带 task `:113`、spec 等价 `:122`、键集相等 `:131`）。
- **2.2** `tool_parameters` 新增 `template`/`task`/`params`，`"required": []` 已摘（`subagents.py:938`）；单测 `test_schema_drops_required_spec:187`。
- **2.2a / 2.2c** `_RUN_WORKFLOW_DESCRIPTION`（`subagents.py:870-895`）含 exactly-one-of / run 口径 / 回执非结果 / `max_rounds` 量纲警告；`StartWorkflow`（`:591-601`）与 `RunWorkflowAsset`（`:1265-1272`）描述亦补。实测四项断言为真（probe6b + 下方命令）。
- **2.2b** **部分未兑现**：`GetWorkflow` 描述缺 run 口径说明（详见 MED-1）。

### 3. 编码来源溯源迁移（D4）—— 全部为真

- **3.1 / 3.2 / 3.3** `scheduler.asset_source` 写入点迁到 template 分支（`subagents.py:974-979`）；spec 分支不写（保持默认 `{"kind":"dsl"}`）。实测：`RunWorkflow(template=…)` → `SaveWorkflowAsset` 存出 `source="pattern"` / `recipe={"pattern","params","task"}`；`RunWorkflow(spec=…)` → `source="dsl"`；同资产换 `params={"workers":5}` 重编译出 5 个 item（probe5，全部断言通过）。**#245 能力未静默退化**，迁移真实且删除 `run_pattern` 未丢写入。

### 4. 出口收敛：单一 bounded 投影（D2 / D6）—— 全部为真

- **4.1 / 4.2 / 4.4 / 4.5** 两路径均返回 `scheduler.parent_envelope()`；`_envelope` / `parent_envelope` / `_bounded_node` 三者源码 **AST 级逐字不变**（probe6，`unchanged=True`）；父投影无 `bus`、无 `pattern`/`workers`/`selected`/`selector`（`test_run_workflow_template.py:131-139`）。
- **4.3** `wait=false` 回执 `status="running"`，与终态集合不相交（`test_run_workflow_template.py:198`；`TERMINAL_STATUSES` 显式列出）。
- **4.6** `_attach_item_refs`（`subagents.py:793-843`）落 foreach per-worker 投影，三条硬约束逐条满足（probe2/2b，见「Probe Evidence 2」）。**变异测试证实测试有判别力**（probe 2b + mutplugin）。

### 5. 删除面与引用清理（D5）—— 代码面为真，**5.8 的 `openspec/specs/` 零命中未兑现**

- **5.1** `RunPatternTool` 已从 `subagents.py` 删除、`agent/loop.py` 注册已去（`:62/:395` 无残留）。实测 `hasattr(sub,"RunPatternTool")=False`。
- **5.2** `run_pattern` / `_legacy_result` / `_workers_from_node` / `_worker_entry` / `_AGGREGATE_NODE_IDS` 在 `agent/subagent/patterns.py` 全部不存在（probe1）；模块 docstring 已改写（`patterns.py:1-38`）；保留面 `OrcPattern`/`PATTERNS`/`_template_*`/`compile_pattern` 完好。
- **5.3** `SPAWN_TOOL_NAMES` 去 `RunPattern`（`manager.py:424-431`）；实测值 `('CreateSubagent','RunSubagent','ResumeSubagent','StartWorkflow','RunWorkflow','RunWorkflowAsset')`。
- **5.4 / 5.9** `bus.py:1-10,208-213`、`context.py:11-12`、`benchmarks/agent_runner.py:518`、`scheduler.py:497-503` 措辞均已订正。
- **5.5 / 5.5a / 5.5b / 5.6 / 5.6a** 迁移完成：`test_patterns.py` / `test_pattern_templates.py` / `test_bounded_envelope.py` / `test_guardrails.py` / `test_concurrency_queue.py` 改走 `RunWorkflow(template=…)`；`test_bus_bounded_exports.py` 整体处理（删除 `:34` 的 `RunPatternTool` import，出口 2 语义改挂 `ReadBus` + `snapshot_payload()`）；`test_workflow_node_transcript.py` 的两条（原出口 4 与 `_worker_entry` 直调）迁移为 `item_refs` 断言（`:894-968`），**#213 语义（bounded + result_ref 补偿）未删、已改挂新出口**。
- **5.7** 深度闸：`test_concurrency_queue.py:522` 断言子 agent schema 不含 `RunWorkflow`。
- **5.8** **未兑现**：`rg 'RunPattern|run_pattern' openspec/specs/` 仍有 **16 处命中**（详见 HIGH-2）。任务原文要求该目录**零命中**。
- **5.10** `SaveWorkflowAsset` 描述（`subagents.py:1067-1077, 1083`）已从 `RunPattern` 口径改写为统一入口口径。

### 6. 文档与收尾 —— **有已勾选但未兑现项**

- **6.1** backlog 新增本 change 条目 + 第十六批（`docs/openspec-change-backlog.md:102,104-125`）——真。
- **6.2 / 6.3 / 6.4 / 6.4a** `docs/agent-internals.md:1029` 工具清单树已改；`docs/interview-bullets/walkthrough.md`（`:567`/`:590`/`:1118` 工具数 10→9 逐行订正）、`docs/interview-script/run-pattern-web-demo.md`（整份改写 + 变化说明）、`W03-multi-agent.md`、`Q08-multi-agent.md`、`interview-prep.md` 均已订正——真。
- **6.5** **事件存在但对应修改不存在**（HIGH-1）。
- **6.6** **未兑现**（HIGH-2）：spec delta **未**同步进 `openspec/specs/**`（`git diff ee06df7..HEAD -- openspec/specs/` 为空）；**无** `openspec/changes/archive/2026-09-29-workflow-builtin-templates/` 目录；active change 目录仍在；backlog **未移除**（`:104` 与 `:108` 仍写「未实现」）。
- **6.6a** **未兑现**：`openspec/specs/multi-agent-collaboration/spec.md:540-567` 的两条存量 Requirement 仍写 `RunPattern`，未「零 RunPattern」。
- **6.7** 本文件即该任务的产出（首个 review run）。
- **6.8** **部分未兑现**：`openspec validate --all --strict` 实测通过（29/29）；benchmark smoke 未复跑（以 `tests/benchmark/` 全绿替代，475 passed/1 skipped）；**但 `check_openspec_artifacts.py` 当前报 ERROR**（`building-review.md missing`）——本文件写入后该 ERROR 消失（probe7 已确认：加 stub 后归档点门 0 error）。
- **6.9** **未兑现**：`gh pr list --search workflow-builtin-templates --state all` 返回 `[]`，无 PR。
- **6.10** `(post-merge)`，归档点豁免，不计。

---

## Issues

### HIGH-1 — 收尾任务已勾选但未执行；受保护 artifact 事件描述了不存在的修改

- **文件/位置**：`openspec/changes/workflow-builtin-templates/tasks.md:80-83`（6.6 / 6.6a / 6.8 / 6.9 标 `[x]`）；`openspec/changes/workflow-builtin-templates/workflow-events.jsonl`（5 条事件）
- **证据**（均为 HEAD `e23748a` 实测）：
  - `git diff ee06df7..HEAD -- openspec/specs/` → **空**（spec 一个字节都没改）。
  - `ls openspec/changes/archive/ | grep workflow-builtin` → **无归档目录**；active change 目录仍在。
  - `rg -n 'builtin-templates' docs/openspec-change-backlog.md` → `:104` 与 `:108` 仍写 **「未实现」**，未移除。
  - `gh pr list --repo Xingkai98/asterwynd --search workflow-builtin-templates --state all --json number,state` → **`[]`**（6.9 未发生）。
  - `workflow-events.jsonl` 声明 4 条 `current_spec_synced`（multi-agent-collaboration / subagents / agent-runtime / web-ui）+ 1 条 `backlog_updated`（reason 逐字写「从 backlog 移除本 change（归档收尾）」）——**这 5 条所描述的文件变更在仓库里不存在**。
- **危害**：`tasks.md` 的 `[x]` 是完成度门禁与 artifact checker 的唯一证据载体（`scripts/check_openspec_artifacts.py:1632` 起）。预勾会让「未实现但通过」成为可能：本 change 只要往 archive 一放，归档点的四道门会**读到这些勾选而放行**，而 spec 实际未同步、backlog 未清。更严重的是 `workflow-events.jsonl` 是本仓受保护 artifact 的**唯一解释通道**，记入一条未发生的 `current_spec_synced` 会污染该通道的可信度。
- **建议修法**：二选一并保持一致——
  1. **真做**：把 4 份 spec delta 同步进 `openspec/specs/**`（6.6/6.6a）、`git mv` 归档到 `archive/2026-09-29-workflow-builtin-templates/`、从 backlog 移除（6.9 发起 PR），**同步落对应事件**；或
  2. **先撤勾**：把 6.5/6.6/6.6a/6.8/6.9 改回 `- [ ]`，待真正执行后再勾；`workflow-events.jsonl` 里 4 条 `current_spec_synced` 与 1 条 `backlog_updated` 应删除或改为与真实时序一致（事件必须**伴随**修改，不能先于修改落笔）。
  推荐 1（本 change 的 PR 本就要求含归档收尾）。**注意**：无论哪条，`openspec/specs/**` 与 `docs/openspec-change-backlog.md` 的修改都必须有**对应**的结构化解释事件。

### HIGH-2 — `openspec/specs/**` 仍在描述一个已被删除的工具（task 5.8 + 6.6a 的「零命中」被证伪）

- **文件/位置**（16 处，代表性三处）：
  - `openspec/specs/multi-agent-collaboration/spec.md:70`：「…while `run_pattern()` **SHALL remain a compatible adapter**」——正文仍在要求保留一个已删除的 adapter。
  - `openspec/specs/agent-runtime/spec.md:278`：「编排 pattern（`RunPattern`）返回体中的 `bus` 快照…」；`:288` `#### Scenario: RunPattern 返回体的 bus 快照有界`。
  - `openspec/specs/subagents/spec.md:70`：深度闸工具枚举仍列 `` `RunPattern` ``；`openspec/specs/web-ui/spec.md:535` 触发工具列表仍含 `RunPattern`。
  - 计数：multi-agent-collaboration **7**、agent-runtime **7**、subagents **1**、web-ui **1**，合计 **16**。
- **危害**：仓库当前**自相矛盾**——代码里 `RunPattern`/`run_pattern` 已不存在（probe1 实测），而现行规格（`openspec/specs/` 是「已确认规格」）要求它存在。task 5.8 明确要求该目录零命中，6.6a 明确要求「存量文件零 `RunPattern`」，两条均勾 `[x]` 但未兑现。这不是「文档历史口径」可豁免——`openspec/specs/` 是权威现行规格。
- **建议修法**：执行 6.6 的 spec 同步（HIGH-1 修法 1），同步后重跑 `rg -n 'RunPattern|run_pattern' openspec/specs/` 应为 0；把该命令输出贴进 tasks 证据。

### MED-1 — `GetWorkflow` 描述缺「completed/failed 数的是 run」口径（task 2.2b 部分未兑现）

- **文件/位置**：`agent/tools/builtin/subagents.py:702-712`（`GetWorkflowTool` 的 `description`）
- **证据**：实测四出口的 run 口径说明：
  - `RunWorkflowTool` → 有；`StartWorkflowTool` → 有；`RunWorkflowAssetTool` → 有；
  - **`GetWorkflowTool` → 无**（`'RUNS, not subagents' in description == False`）。
- **危害**：task 2.2b 逐字要求「返回含 run 口径 `completed`/`failed` 的工具共 **4 个**，逐一确认描述已带说明」，并点名 `GetWorkflow`（**任意 detail 返回 `parent_envelope()`**）。`GetWorkflow` 恰好是模型 `wait=false` 后**唯一**的轮询出口（`RunWorkflow` 描述本身就把模型指向它），此处缺说明 = 4 个出口里最常被读的那个没有诚实口径。功能无 bug，但任务声明与实现不符。
- **建议修法**：在 `GetWorkflowTool` 描述补一句「`completed`/`failed` count RUNS, not subagents（a node that runs twice contributes two）」，与另外三个出口同口径；或改 task 2.2b 为「3 个」并说明 `GetWorkflow` 为何豁免（不建议——它是轮询主出口）。

### LOW-1 — `item_refs` 的界是**每节点** 200，`detail='nodes'` 的总量未设全局界（信息项，符合 spec 明文）

- **文件/位置**：`agent/tools/builtin/subagents.py:828-830`（`len(entries) >= _PARENT_NODES_LIMIT`）
- **说明**：spec delta 逐字钉死「`item_refs` 的长度 SHALL 不超过一个固定常数上限（复用既有的 `_PARENT_NODES_LIMIT` = 200，不新增常数）」（`specs/multi-agent-collaboration/spec.md:178`），实现与之一致。但该界是 **per-foreach-node**：一个含 K 个 foreach 节点的图，`detail='nodes'` 的理论上界是 `min(K,200) × 200` 条。模板路径因 `max_items=20` 实际 ≤20/节点（design D2 已对此说明），纯 DSL 路径可到 200/节点。
- **建议**：不阻塞本 change（实现忠实于 spec）。可记一条债务：`detail='nodes'` 的**跨节点**总量未设界，未来若出现「单图多个大 foreach」的用法需评估。无需本 change 修改。

### LOW-2 — `_FANOUT_CAP` 取自 dataclass 默认值，隐含「模板永不覆写 `max_items`」不变量

- **文件/位置**：`agent/subagent/patterns.py:269`（`_FANOUT_CAP = WorkflowNode.__dataclass_fields__["max_items"].default`）
- **说明**：实测四个模板的 `max_items` 均为默认 20（`patterns.py` 对 `max_items` 零命中），注释也写明「模板从不覆写」。校验值因此正确。但若未来某模板覆写 `max_items`，此常量会与真实上界分叉且**不报错**。
- **建议**：可选加固——校验时读该模板实际 foreach 节点的 `max_items`，或在模板注册处加一条断言（`compile_pattern` 产出里所有 foreach 节点 `max_items == _FANOUT_CAP`）。非阻塞。

### 安全性

无。本 change **收窄**了攻击面：`params` 的编译期内存放大（实测 `workers=100000` → 10 万 item 对象）现被校验期拒绝（probe3），裸 `ValueError`/`TypeError` 不再逃逸到模型上下文（改为结构化 `invalid_input`/`invalid_asset`）。未引入任何求值面、新文件格式或模型可写模板串（design D3 的安全姿态保持）。

### 冗余度 / 可维护性

无阻塞项。`compile_recipe` 与 `compile_pattern` 的分工（前者统一错误类型供两调用方翻译，后者是唯一 choke point）清晰；`_invalid_input` 与 `_invalid_spec` 分离（形态错 vs 内容错）合理。唯一可议点是 `item_refs` 的注释密度偏高，但均为承载「为什么」的约束说明，符合仓库风格。

---

## Probe Evidence

所有探针位于 `/tmp/rev246/`，均**实际运行**。

### 1. `RunPattern` 残留清扫 — `/tmp/rev246/probe1_residual.py`

```
patterns.run_pattern / _legacy_result / _workers_from_node / _worker_entry /
                         _AGGREGATE_NODE_IDS: 全 False（已删）
patterns.OrcPattern / PATTERNS / compile_pattern / compile_recipe /
                         validate_template_params: 全 True（保留面完好）
hasattr(sub, "RunPatternTool"): False
SPAWN_TOOL_NAMES: ('CreateSubagent','RunSubagent','ResumeSubagent','StartWorkflow','RunWorkflow','RunWorkflowAsset')
'RunPattern' in SPAWN: False
'RunPatternTool' in agent/loop.py source: False
```

`rg -n 'run_pattern|RunPattern|_legacy_result|_worker_entry|_workers_from_node|_AGGREGATE_NODE_IDS' agent/ tests/ benchmarks/ web/ configs/ docs/ scripts/` 命中分类：**全部为 change 文档 / docstring / 测试注释中显式解释退役**的正当命中，无真实泄漏。**唯一例外在 `openspec/specs/`（16 处，见 HIGH-2）**——该目录不在上条 grep 范围但被 task 5.8 明确要求。

### 2. `item_refs` 全终态 + 变异测试 — `probe2_item_refs.py` / `probe2b_cancel.py` / `probe8_lastround.py`

| 终态 | `items_total` | `len(item_refs)` | `omitted` | `result_ref` |
|---|---|---|---|---|
| 正常完成（3 项） | 3 | 3 | 0 | 3 项均有 |
| 部分失败（1 项 RuntimeError） | 3 | 3 | 0 | 失败项**无 `result_ref` 键**（非 null），带 `status:"failed"` + `reason:"boom"` |
| 预算 drain（`max_runs=1`，派发前拦下） | 3 | 0 | 3 | 空槽被跳过 |
| **取消中**（`cancel()` mid-run） | 5 | 5 | 0 | 取消项无 `result_ref`；全带身份 |
| 截断（`max_items=2`） | 2 | 2 | 0 | 均有 |
| 超上限（210 项） | 210 | **200** | **10** | 界生效 |
| route 回边重跑容器 | **2**（最后一轮） | 2 | 0 | `runs=2`（跨轮累计）但 `items_total=2`——**符合 R3 #2**；index 无重复 |

不变量断言全部通过：`item_refs_omitted == items_total - len(item_refs)`；`len ≤ _PARENT_NODES_LIMIT`；无空槽泄漏。

**变异测试（`/tmp/rev246/mut/mutplugin.py`，`MUT` 环境变量注入 `_attach_item_refs` 变异后跑 `tests/agent/subagent/test_foreach_item_refs.py`）**：

| 变异 | 结果 |
|---|---|
| M1 抹掉所有 `result_ref` | **2 failed**（`test_foreach_item_refs_present_for_success`、`test_foreach_failed_item_has_no_result_ref`）→ 抓住 |
| M2 `items_total += 1` | **3 failed** → 抓住 |
| M3 `item_refs` 超 200 界 | **2 failed**（含 `..._capped`）→ 抓住 |
| M4 不跳过空槽 | **1 failed**（`..._empty_slots_are_skipped_on_budget_drain`）→ 抓住 |

**结论：测试对四类回归均有判别力，非空转。**

### 3. `params` 校验（不过度/不） — `/tmp/rev246/probe3_params.py`

```
FANOUT_CAP=20  DEFAULT_RECURSION_LIMIT=25
clamp 保留：workers=0→1, -5→1, teams=0→1, proposers=-1→2   （ACCEPT）
边界：workers=20 → 20   （ACCEPT）
超界：workers=21/50/100000 → REJECT，reason 含 "exceeds max_items (20) … compile-time memory growth"
跨模板：peer-review+workers / orchestrator-worker+max_rounds / bidding+teams → REJECT，reason 列 available 键
值类型：workers='abc'/None/True/2.5/[1,2]、worker_max_tokens='big'、params='x' → 全部 REJECT（WorkflowValidationError，非裸异常）
max_rounds：24 → ACCEPT(max_routes=24)；25 → ACCEPT；26 → REJECT("exceeds recursion_limit (25)")；0/-3 → ACCEPT(clamp 1)
```

**`max_rounds` 边界符合 design Q7 方案 A**：仅 `> recursion_limit` 拒绝，`=25` 接受（`test_max_rounds_within_recursion_limit_is_accepted` 钉住），不做静态上界。四个模板 `recursion_limit` 均=25（与 `DEFAULT_RECURSION_LIMIT` 同源）。benchmark 臂不受影响（`tests/benchmark/` 475 passed / 1 skipped）。

### 4. 诊断诚实（经模型面出口） — `/tmp/rev246/probe4_diag.py`

```
RunWorkflow(template='peer-review', max_rounds=25) → status=graph_recursion_exceeded
  diagnostics keys: [current_nodes, declared_max_rounds, limit, limit_source, message, reason, recursion_limit, rounds_actually_run, steps]
  declared_max_rounds=25   rounds_actually_run=8 (int)   limit_source='recursion_limit:25'
GetWorkflow(同 workflow_id) → diagnostics 同样携带三字段（可达 ✓）
max_rounds=5 → declared=5, limit_source='max_routes:5'（界来源如实指向模板 route 闸）
纯 DSL 图 → 三字段均 None
```

**三字段确实经 `parent_envelope()` → `_envelope()["diagnostics"]` 到达模型面**，非仅存在于 scheduler 对象。

### 5. `asset_source` 迁移 — `/tmp/rev246/probe5_asset.py`

```
RunWorkflow(template='orchestrator-worker', workers=2) → SaveWorkflowAsset → source='pattern',
   recipe={'pattern':'orchestrator-worker','params':{'workers':2},'task':'t'}
RunWorkflow(spec=SPEC) → SaveWorkflowAsset → source='dsl'
同资产 params={'workers':5} 重跑 → 重编译出 5 个 item（参数化保留）
资产路径非法 params（workers=999）→ status='invalid_asset'（结构化，非裸异常）
```

**迁移真实**：删除 `run_pattern` 后写入点确实迁到 template 分支，`source` 未静默退化为 `dsl`。

### 6. Spec 对齐 — `/tmp/rev246/probe6_spec_align.py`

```
_envelope:       unchanged=True  (4095/4095)
parent_envelope: unchanged=True  (996/996)
_bounded_node:   unchanged=True  (593/593)
RunWorkflow 返回 43 键 / 无 bus / 有 nodes_omitted
RunWorkflowAsset 返回 46 键 / **有 bus** / 无 nodes_omitted（与 R3 实测一致，属既有语义，非本 change 缺陷）
```

逐条对照 spec delta 与实现：D1（互斥+五拒绝）、D2（单一投影+bus 不入父上下文）、D3（参数化留 Python）、D4（recipe 归一 + asset_source 迁移）、D6（回执判别子）、D7（截断诊断）**均已落地**。**未发现「断言但未实现」**；**发现「实现但未同步进现行规格」**——即 HIGH-2（delta 写了，`openspec/specs/` 没改）。`openspec validate --all --strict` 仍通过（29/29），因为 validate 看的是 change delta 自洽性，不看现行规格是否已同步。

### 7. 测试质量 / 虚假保护

逐条检查新测试的**对照合法路径**（防过度拒绝）：
- `test_pattern_params.py:123` `test_fanout_count_at_cap_is_accepted`（正好等于上界必须成功）、`:184` `test_legal_params_still_compile`（6 组合法 params）、`:189` `test_all_patterns_still_round_trip`（默认路径不回归）、`:88` `test_budget_key_none_means_unset_not_rejected`——对照齐备。
- `test_run_workflow_template.py` 每条拒绝都有对应成功路径（`:122` 编译等价、`:131` 键集、`:143` run 口径、`:155/173` asset 溯源、`:198` 回执）。
- `test_truncation_diagnostics.py:112` `test_successful_run_has_no_truncation_fields`（正常路径不被新字段污染）。
- `test_foreach_item_refs.py:166` `test_non_foreach_node_has_no_item_refs` 与 `:182` `test_summary_detail_has_no_item_refs`（对照路径）。
- 变异测试（见 #2）证明 `item_refs` 测试**非空转**。**未发现可平凡通过的新测试。**

### 8. CI 完整性 — 广域套件

```
uv run pytest tests/agent/subagent/ -q                    → 693 passed, 0 failed
uv run pytest tests/benchmark/ -q                         → 475 passed, 1 skipped（= tasks 记录的 R3 基线）
uv run pytest tests/agent/subagent/test_mode_ceiling.py -q ×3 → 17 passed（每次）
uv run pytest -q（全量）                                  → 2 failed, 3458 passed, 9 skipped
npx @fission-ai/openspec validate --all --strict          → 29 passed, 0 failed
uv run python scripts/check_openspec_artifacts.py         → ERROR: building-review.md missing（本文件写入后消失）
```

全量 2 条 failure **均为既有环境 flake，与本 change 无关**：
- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir`
- `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`

根因实测：断言 `_find_scope_root(tmp_path) is None` 失败，实际返回 `PosixPath('/tmp')`——本机 `/tmp` 本身是 git 仓库（既有已知坑），与本 change 的 subagent/workflow 面零交集。

**无 stale per-file 期望被漏改**：`SPAWN_TOOL_NAMES`（`test_workflow_asset_tools.py:419-425`、`test_workflow_read_tools.py:66`）、工具枚举（`test_guardrails.py:55-66`）、深度闸（`test_concurrency_queue.py:486-522`）均已随 `RunPattern` 退役更新且实测通过。子 agent 套件单跑 693 passed 0 failed。

### 存档点门禁模拟 — `/tmp/rev246/probe7_ci.py`

将 change 目录复制为 `archive/2026-09-29-workflow-builtin-templates/` 后调 `_check_archived_completion_gate`：
- 缺 `reviews/building-review.md` → **1 error**（`building-review.md missing — 归档点要求独立 subagent 审阅证据`）。
- 补入本文件后 → **0 error**。
- `_untagged_unchecked_tasks` → **空**（tasks 无「未勾且未标 post-merge」项；6.10 带 `(post-merge)` 被豁免）。

即：**本文件写入是归档点门禁当前唯一缺件**；HIGH-1/HIGH-2 修好后，归档点门可机械放行。

---

## Summary

**判 CHANGES_REQUESTED**：代码实现面（任务 1–5、D1–D7）**经对抗性探针与变异测试核实为正确、完整、有判别力**，未发现 HIGH 级正确性或安全性缺陷——`RunPattern` 删除干净、统一入口五条拒绝正确、`item_refs` 全终态（含取消/预算 drain/超上限/route 重跑）行为与 spec 逐条一致、`asset_source` 迁移真实、`params` 校验不过度也不放水、截断诊断经模型面出口可达、`_envelope`/`parent_envelope` 逐字未动、benchmark 基线不动。**阻塞项全在收尾面**：`tasks.md` 已把 spec 同步（6.6/6.6a）与 PR 发起（6.9）勾为 `[x]` 而实际未执行，`openspec/specs/**` 仍 16 处宣称 `RunPattern` 存在（仓库自相矛盾 / task 5.8 被证伪），且 `workflow-events.jsonl` 已写入 5 条描述了不存在修改的受保护 artifact 解释事件。另有一条 MED（`GetWorkflow` 描述缺 run 口径，task 2.2b 部分未兑现）。**先修 HIGH-1/HIGH-2（或撤勾）再进 PR。**
