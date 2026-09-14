# Building Review — workflow-result-aggregation (C3)

## Reviewer

- run id: review-workflow-result-aggregation-20260914-r1
- 时间: 2026-09-14
- 角色: 独立零记忆 building 审阅员（不继承实现上下文）
- base: `0dcbefb`（PR #182 合入点，C3 分支点）
- head: `7a60167`（C3 building 阶段 6）
- 分支: `workflow-result-aggregation/2026-09-14`
- diff: `git diff 0dcbefb...HEAD`，23 files / +3760 / −43（相对 0dcbefb；本地 `master` ref 停在
  `cb9902c` 是脏的，本报告一律以 `0dcbefb` 为基）

## Verdict

**CHANGES_REQUESTED**

核心交付（D1–D7 + 8 条 Confirmed Decisions + 9 条 User Confirmation）逐条落地且测试扎实：
result_ref 独立 subtree 落盘、分层汇聚自动兜底、三 hash 分离、三种结果表示、跨进程读取、
bus 降级、四档预算配置化——**grill 标的 3 个严重风险全部真修复且有回归测试**（下面逐条给证据）。
100-leaf Scenario 我自己复测确认不再撑爆。

但本 change **自己引入了一个 CI 红灯**（`tests/test_workflow_guard.py` 2 例失败，base 上 25 passed），
且在新代码里留了一处**路径逃逸读取**（文档明确声称已拒绝，实际未拒绝）。
这两条必须先修再复审，故不 PASS。

---

## 任务逐项验证（tasks.md 0.1–5.3、5.5）

| Task | 结论 | 证据 |
|------|------|------|
| 0.1 grill 追问 ≥3 决策 + Open Questions 停轮确认 | ✅ | `reviews/grill-design.md` 8 条 Confirmed Decisions + 9 条 Open Questions + 9 条 User Confirmation（内容实质，非占位）。但**格式触发了下面 Issue 1** |
| 1.1 workflow_store 落盘（独立文件 + 原子写 + 事件日志） | ✅ | `agent/subagent/workflow_store.py:36-193`；`_atomic_write` tmp+`os.replace`（`:183-193`）；独立 subtree `for_workspace`（`:43-45`） |
| 1.2 `to_result_dict` 增 summary_ref/transcript_ref/artifact_refs | ✅ | `agent/subagent/manager.py:118-142`；**成功路径新增写点** `_write_result_artifacts`（`:1089-1134`），grill 决策 2 要求的「正常完成也落盘」成立 |
| 2.1 显式 aggregate 树 + 自动兜底（>10 或总叶子 >10 插层） | ✅ | `agent/subagent/aggregation.py:126-141`（`plan_layer_insertions`，`ceil(n/10)` 分组）、`:267-356`（`ExecutionPlan.build`）；声明期 `_build_plan` + 展开期 `_expand_plan`（`scheduler.py:952-990`） |
| 2.2 四档 token 预算 300/800/1500/3000 可配置 | ✅ | `aggregation.py:57-62, 144-152`；`config.py:262-285`；实测 yaml `leaf:500 / max_fan_in:4` 生效 |
| 2.3 复用 Summarizer Protocol + `WorkflowAggregator` | ✅ | `aggregation.py:70-115`；复用点确为 `agent/context/summarizer.py` 的 `compress(tier_summaries, budget)`，非 `MemoryManager` 私有 L1/L2（grill 决策 8 口径正确） |
| 3.1 父 agent 永远 bounded envelope | ⚠️ | 字段齐（`scheduler.py:1448-1481`：workflow_id/status/total/completed/failed/pending/root_result_ref/latest_events…），但**不是真 bounded**，见 Issue 4 |
| 3.2 GetWorkflow 带 detail 参数 | ✅ | `agent/tools/builtin/subagents.py:622-681`，`summary`/`nodes`/`events` 三档，非法值返回 `invalid_detail` |
| 3.3 bus 降级为非权威 | ✅ | `bus.py:9-17` 文档 + 权威事件写 `events.jsonl`（`scheduler.py:428-432`）；`test_bus_degradation.py` 覆盖 |
| 4.1 阈值 + 预算入 `SubagentsConfig`，逐字段解析 | ✅ | `config.py:1456-1513` `_parse_aggregation` 逐字段 `mapping.get`；非递减校验 `:1494-1502`（拒绝严格递减实测生效） |
| 5.1 新增测试（落盘/兜底/envelope/预算/bus 降级） | ✅ | 9 个新测试文件、约 1900 行；`uv run pytest tests/agent/subagent/ -q` → **278 passed** |
| 5.2 100 leaf 不撑爆 + bus 丢消息 + 跨进程 result artifact 读取 | ✅ | 独立复现见下「特别核验点」；跨进程由 subprocess 真起新解释器（`test_workflow_store.py:175-193`） |
| 5.3 benchmark smoke | ✅ | 我自己跑：`asterwynd benchmark benchmarks/tasks --agent fake` → 72 tasks 执行完毕、无 crash |
| 5.5 全量 pytest + validate + checker | ⚠️ | validate 30 passed、checker passed；**全量 pytest 2 failed** → Issue 1 |
| 5.4 spec sync 留 closing | ✅（未勾选，符合预期） | tasks.md:33 仍为 `[ ]` |

### D1–D7 + User Confirmation 落地核验（重点）

- **D1 / 决策 1（独立 subtree）**：`WorkflowStore.for_workspace` = `<ws>/.asterwynd/workflows/<wf_id>/`，
  与 `.asterwynd/subagents/` 分离。回归 `test_snapshot_store_remove_does_not_delete_results`
  真的调 `snapshot_store.remove()`（内部 `shutil.rmtree`）后断言结果仍在。✅
- **决策 2（成功路径新增写点）**：`_complete_run` 末尾调 `_write_result_artifacts`；
  `test_successful_workflow_run_writes_result_artifacts` 断言 `store.load(run.result_ref) == 全文`。✅
- **决策 3（artifact_refs 明确填充时机）**：`_write_result_artifacts` 把 result/transcript/summary
  三个 ref 都塞进 `artifact_refs`；非 workflow run 保持 `[]`（`test_non_workflow_run_writes_no_refs`）。✅
- **决策 4 / Q2（envelope 不替换 `run()` 返回值）**：`_envelope` 保留 `nodes`/`completed`/`failed`，
  新字段是**增量**；C2 的 24 处断言全绿。✅
- **决策 5 / Q7（真正爆点在 task 文本）**：`_node_task_text`（`scheduler.py:1279-1302`）与
  `_aggregate_task_text`（`:1304-1325`）都改成消费 `_bounded_output`（按档裁剪 + 附 result_ref），
  不再拼全文。✅（独立实测见下）
- **决策 6（自动插层记账 max_nodes）**：`_check_declared_limits`（`:496-525`）+ `_expand_plan`
  记账（`:977-989`）双复检；`test_auto_inserted_nodes_are_charged_against_max_nodes` 用「声明通过、
  插层后超限」的缝隙验证。✅（但**再展开路径漏了幂等**，见 Issue 3）
- **决策 7 / Q8（配置逐字段解析）**：`_parse_aggregation` 显式逐字段；`test_aggregation_config.py` 覆盖。✅
- **决策 8 / D5（复用 summarizer 而非 MemoryManager）**：`WorkflowAggregator` 吃 `Summarizer` Protocol，
  无 LLM 退回 `TruncationSummarizer` 且**仍裁剪**（`aggregation.py:103-115`），不会变成绕过预算的旁路。✅
- **Q1（ReadWorkflowResult 分页 + GetWorkflow(detail) 不展开正文）**：✅（但 ref 解析有逃逸，见 Issue 2）
- **Q3（声明期 + 展开期都算 + 三 hash 分离 + 不原地改 spec）**：`declared_spec_hash` 在 `with_expansion`
  重建时通过 `declared_spec_hash=` 折回（`aggregation.py:257-263`）；`test_execution_plan_does_not_mutate_the_declared_spec` 锁定。✅
- **Q4（阈值 >10、ceil 分组、距 leaf 定档、auto=strategy llm）**：`MAX_FAN_IN=10`、`plan_layer_insertions`、
  `budget_for_distance`、`strategy="llm"`（`aggregation.py:389`）逐条对上。✅
- **Q5（scheduler 内部 ring buffer，最近 5 条终态迁移，字段 node_id+status+summary_preview ≤80）**：
  `_LATEST_EVENTS_LIMIT=5`、`_EVENT_PREVIEW_LIMIT=80`、`_record_event(terminal=True)`。✅
- **Q6（三种结果表示分离，run.summary 保留全文）**：实测 `to_result_dict` 的 `summary` 50k 字不动、
  `bounded_summary` 裁到 2040 字；`test_result_representations.py` 三条断言锁定。✅
- **Q9（删「恢复 workflow 状态」+ 补跨进程读取）**：tasks.md 5.2 已按此措辞；subprocess 测试真实。✅

---

## Issues（带 file:line）

### Issue 1 — [BLOCKER] 本 change 自己的 grill 证据格式使 workflow-guard 回归，CI 红灯

**现象**：`uv run pytest -q` → **2 failed**：
`tests/test_workflow_guard.py::test_guard_noops_when_workflow_disabled`（`:109-129`）、
`::test_guard_resume_audit_no_longer_blocks_writes`（`:158-176`），两例都断言普通 `Write` 应 `exit 0`，
实际 `exit 2`。

**根因**（独立定位，非环境问题）：`scripts/workflow_guard.py:363-401` 的 `_grill_evidence_missing()`
对「有 spec delta 的 active change」要求 grill 证据完整（Open Questions 全部有 User Confirmation），
解析用正则 `scripts/workflow_guard.py:470`：
```
r"用户答复\s*[:：]\s*(.*?)(?:[；;]\s*确认时间|\s*$)"
```
而本 change 的 `openspec/changes/workflow-result-aggregation/reviews/grill-design.md:105-112`
把括号注记插在了「用户答复」与冒号**之间**：`用户答复（codex 独立确认修正）：`。
该正则要求「用户答复」紧跟冒号，于是 9 条里只有 Q1（无括号）被识别：

```
open: ['Q1'..'Q9']   confirmed: ['Q1']   missing: ['Q2'..'Q9']
```

`_grill_evidence_missing()` 因此返回 True → guard `exit 2`。**在 base `0dcbefb` 上同一测试 25 passed**
（我在 `/tmp/basecheck2` 独立检出验证）；在 detached-HEAD 检出（模拟 CI）同样 25 passed——
即失败**只由本 change 的 grill 文件格式触发**，不是既有环境问题。

**影响面（比实现 agent 报告更大）**：`scripts/check_openspec_artifacts.py:830` 是**同一正则的复刻**
（两组代码注释互相声明「与 … 同步」）。因当前 tasks.md 的 5.4 仍未勾选，`_tasks_all_complete()` 为 False，
checker 暂时放行——**closing 阶段勾上 5.4 后 checker 立刻报错**。我模拟验证：
```
ERROR: workflow-result-aggregation: reviews/grill-design.md 存在未确认的 Open Question:
       Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9 ——每个 Open Question 必须有 ## User Confirmation 记录
```
即这是一个**延迟到 closing 才爆**的红灯。

**建议修法（二选一，任选，改完跑三门禁）**：
1. **改文件格式**（最小改动，已实测可行）：把注记移到 Q 序号后，即
   `- **Q2**（codex 独立确认修正）: 用户答复：…`。我在 `/tmp/fixsim` 上按此改 8 行，
   guard 解析随即变为 `missing: []`（两个正则都命中）。
2. **放宽两处正则**（更耐未来格式漂移）：让 `(?:[^：:]*)\s*[:：]` 同时允许「用户答复」后的括号注记。
   若选此路，必须在 `tests/test_workflow_guard.py` 补一条「注记插在用户答复后」的正例，
   否则下次同类格式漂移会再次静默降低门禁强度。

> 注：实现 agent 报告称这些失败是「既有环境问题（workflow-guard 缺 grill 证据 + Java tree-sitter +
> benchmark flaky）」。**前半句不成立**——guard 失败由本 change 的 artifact 直接导致，且代价是 CI 红。
> 全量 pytest 我只观察到 2 failed（非 4），未能复现 tree-sitter / benchmark 失败（本环境未装）。

### Issue 2 — [HIGH] `WorkflowStore` ref 解析接受 `..`，`ReadWorkflowResult` 可读出 subtree 之外

`agent/subagent/workflow_store.py:31-33` 的 `_ALLOWED_REF_CHARS` **包含 `.`**，
`parse_ref`（`:49-66`）只校验「两段 + 字符白名单」，因此 `..` 是合法 workflow_id/key。
`for_workspace(root, "..")` → root = `<ws>/.asterwynd/workflows/..` = `<ws>/.asterwynd`；
`path_for`（`:77-88`）的 containment 检查拿**已被 `..` 污染后的 base** 去比，自然通过。

`ReadWorkflowResultTool.execute`（`agent/tools/builtin/subagents.py:595-606`）直接吃模型给的 ref：
```python
workflow_id, _key = WorkflowStore.parse_ref(ref)      # :598
store = self.manager.workflow_store(workflow_id)      # :604  可传 ".."
page = store.read(ref, ...)                            # :605
```
独立复现（构造 `<ws>/.asterwynd/results/leak.txt`）：
```
ReadWorkflowResult(ref="artifact://workflow/../leak")
→ {"content": "LEAKED-OTHER-CONTENT", "missing": false}
```
读取范围限 `<ws>/.asterwynd/results/*.txt`（workflow_id/key 都禁 `/`，只能上跳一层），
故不是任意文件读；但它是**新代码 + 模型可控输入 + 明确违反该模块自己的安全声明**：
`workflow_store.py:52` 的 docstring 写「``..``、绝对路径、多余层级在解析层就被拒绝（不会拼出逃逸路径）」——
与事实不符。

**测试为何没抓到**：`test_parse_ref_rejects_foreign_and_traversing_refs`
（`tests/agent/subagent/test_workflow_store.py:103-114`）里那条 `artifact://workflow/../etc/passwd`
**是因为「三段」被 `len(parts) != 2` 拒绝的**，不是因为 `..` 被识别为逃逸——所以断言通过的理由是错的，
给出虚假信心。`artifact://workflow/../x`（两段）从未被覆盖。

**建议修法**：在 `parse_ref`（或 `ref()`/`path_for()`）显式拒绝 `.` / `..` 作为 workflow_id/key
（如 `if part in {".", ".."} or part.startswith("."):` 抛 ValueError，或校验解析后路径仍在
**未受污染的** workflows 根之下），并把回归测试改成断言 `artifact://workflow/../x` 与
`artifact://workflow/wf/..` 都被 `parse_ref` 拒绝。此处属安全边界，应单独加一条负例。

### Issue 3 — [MEDIUM] `_check_foreach_budget` 在再展开时重复记账（max_nodes / max_runs 双扣）

本 change 阶段 4 把 `_expand_plan` 改成了幂等（`scheduler.py:379-384`：`new_ids` 为空则直接返回，
不重复扣 `_expanded_nodes`），回归测试 `test_reexpanding_same_foreach_does_not_double_charge_max_nodes`
也点明「route 回边会导致同一 foreach 第二次展开」。**但 `_check_foreach_budget`
（`scheduler.py:994-1028`）没有同步改**，末尾仍无条件：
```python
self._expanded_nodes += count     # :1027
self._runs += count               # :1028
```
每次调用都加一遍。直接复现（同一 fan 节点调两次 `_expand_plan` + `_check_foreach_budget`）：
```
after_budget1=18  after_budget2=30   # 12 被双扣
_runs = 24        # 12 被双扣
```
后果：一条 route 回边把 foreach 重激活一次，max_nodes/max_runs 就多吃一份展开量，
可能提前抛 `graph_recursion_exceeded`（用户配置的 200/300 预算被无声缩水）。

**可达性**：我尝试用真实 route 回边（gate→fan）端到端触发，未能构造出命中回边的图
（route 走 default 分支），故标 **MEDIUM 潜伏**，不是已证实的线上路径。且该代码在 base 已存在——
**但本 change 既然已为 `_expand_plan` 修了同一类幂等问题，两处口径不一致会让「展开期复检」
（Q3/决策 6）的记账语义自相矛盾**，属应随本 change 一并收口的半修。

**建议修法**：把「节点 → 已记账展开量」记入 `self._charged_expansions: dict[str,int]`，
`_check_foreach_budget` 只对**增量**计费（`delta = count - charged.get(node.id, 0)`，≤0 直接返回），
与 `_expand_plan` 的 `with_expansion` 幂等语义对齐；补一条回归：同一 foreach 二次展开
`_expanded_nodes`/`_runs` 不变。

### Issue 4 — [MEDIUM] 父 agent envelope 并未真正 bounded（nodes 列表 + bus payload 无上界）

D3 的措辞是「父 agent **永远** bounded envelope」，spec delta Scenario 也写「系统 SHALL 返回 bounded
envelope」。`_envelope()`（`scheduler.py:1430-1484`）虽然把每个节点的 `summary` 裁到
`_SUMMARY_LIMIT=400`（`NodeState.to_dict`，`:142-168`），但：

1. `nodes` 是**全量节点列表**，长度 O(nodes)，不可裁剪（C2 断言依赖它）；
2. `payload["bus"] = self.bus.snapshot_payload()`（`:1483`）把 **bus 全量消息**塞进 envelope——
   而 D4 明说 bus 是**非权威**通道。`snapshot_payload()`（`bus.py:143-146`）返回
   `[m.to_dict() for m in self._messages]`，上界是 `max_messages`（默认 100）× 单条 summary 长度；
3. `foreach` 节点的 `subagent_ids`/`run_ids` 数组随展开项数线性增长。

独立实测（100 leaves + 100 条 1600 字 bus 消息，默认配置）：
```
StartWorkflowTool 返回  237,516 chars
GetWorkflowTool 返回    237,537 chars   （bus.messages = 100）
```
spec delta 的**具体 Scenario**（100 个 leaf 结果不注入父上下文）**是满足的**——`R`*20000 不出现在
envelope 里，节点 summary 全 ≤400。但 D3 的**设计承诺**（永远 bounded）在 bus 消息多时被打破，
且把一个非权威 blob 放进权威 envelope 与 D4 自相矛盾。

**建议修法**：父面向投影里**不含** bus 全量 payload（bus 非权威，要看走专门通道），
或至少对 `bus` 做条目数/总字符上界；对 `subagent_ids` 也做截断（带计数）。
补一条断言 `len(json.dumps(StartWorkflow(...)))` 有界的回归。

### Issue 5 — [LOW] `_expand_plan` 收缩时不清理失效的 auto 节点 NodeState

`_expand_plan`（`scheduler.py:952-990`）只往 `self._states` 加新节点，从不删除**已不在新 plan 里**的
auto 节点。当同一 foreach 以更小项数再展开（`inserted_nodes` 变少）时，旧的 `__auto_agg__*` 状态残留。
实测（25 项 → 5 项）：
```
after shrink: plan.nodes=3 但 states=6；stale auto states not in plan:
['__auto_agg__root_0_0','__auto_agg__root_0_1','__auto_agg__root_0_2']
unit total 仍为 31（含 3 个已不存在的节点）
```
它们会继续污染 `_unit_counts()`→ envelope 的 `total`/`pending` 计数（`scheduler.py:1397-1428`）。
与 Issue 3 同源（再展开路径未收口），可达性同样未证实，故 LOW。
建议在 `_expand_plan` 里对 `self._states` 中「id 在旧 `inserted_nodes`、但不在新 plan」的键做清理。

---

## 门禁复跑结果（全部我自己跑，不采信上一轮）

| 门禁 | 命令 | 结果 |
|------|------|------|
| C3 子集 | `uv run pytest tests/agent/subagent/ -q` | **278 passed**（10.46s）✅ 与实现 agent 报告一致 |
| 全量 pytest | `uv run pytest -q` | **2 failed, 2422 passed, 8 skipped**（233s）❌ 见 Issue 1 |
| OpenSpec strict | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **30 passed, 0 failed** ✅ |
| artifact checker | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | **passed**（当前 5.4 未勾选，故未触发 grill 完整性校验；勾上后会红，见 Issue 1） |
| benchmark smoke | `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo .` | 72 tasks 跑完，无 crash ✅ |
| base 对照 | `/tmp/basecheck2`(0dcbefb) + detached-HEAD 检出 各跑 `tests/test_workflow_guard.py` | **25 passed / 25 passed** → 证实 Issue 1 是本 change 引入 |

---

## 特别核验点（独立结论）

### 1. 「4 个被 deselect 的失败是既有环境问题」——**不成立**

我观察到的失败是 **2 例**（非 4），且**全部由本 change 的 grill 文件格式引入**（base 与 detached-HEAD
均 25 passed）。tree-sitter / benchmark flaky 在本环境未复现（Java tree-sitter 依赖未装，
benchmark smoke 可跑）。分类应为「本 change 引入的回归」，不是环境噪声。

### 2. 两个实现期缺陷修复——**核验通过，修复正确 + 有回归**

- **foreach 重复展开崩溃**：`with_expansion` 现在始终从 `declared_nodes`/`declared_edges` 重建
  （`aggregation.py:248-254`），不再把上次插入的 auto 节点当声明节点。独立复现：同一 fan
  在 20→100→100→5 项间反复展开，插层数分别为 2/10/10/0，幂等成立、无 ValueError。
  回归 `test_repeated_expansion_of_the_same_foreach_is_idempotent`（`test_aggregation_plan.py:270-311`）。
  ✅（唯一缺口：`_check_foreach_budget` 未同步，见 Issue 3）
- **单上游 collect 未压缩**：`_merge_contributions_bounded` 去掉了「上游数 <2 提前返回」，
  改为只按预算判断（`scheduler.py:1193-1232`）。回归
  `test_single_upstream_collect_aggregate_is_still_bounded`（`test_bus_degradation.py:149-202`）
  构造了「foreach 展开 20 项 → 单上游 collect」这一 Q3 隐蔽场景。✅

### 3. 「补了 envelope 泄漏点 `NodeState.to_dict` 的 slots 未裁剪」——**修复正确但不完整**

`NodeState.to_dict` 的 `slots` 现在按 `_SUMMARY_LIMIT` 裁剪（`scheduler.py:156-161`），
这条确实补对了（collect aggregate 的槽是 N 份 concat 的巨型串）。

但**仍有其它字段把巨型/无界串带进 envelope**（均已实测）：
- `bus` 全量 payload（Issue 4）——实测使 envelope 膨胀到 237 KB；
- `foreach` 的 `subagent_ids`/`run_ids` 数组（Issue 4）——随展开项数线性增长；
- `nodes` 全量列表本身 O(nodes)——实测 600 节点 envelope 219 KB（C2 兼容需求，不可直接删，
  但父面向投影应另设上界）。
`state.reason`（`scheduler.py:746,752` 取异常字符串）、`state.error`（:745，`f"{type}: {exc}"`）
未裁剪——当前异常串都很短，暂未观测到膨胀，但同属「无界字段」，建议一并加 `_SUMMARY_LIMIT`。

---

## 结论与下一步

核心实现质量高：D1–D7 与 9 条用户确认逐条落地，**grill 标的 3 个严重风险全部真修复**，
100-leaf/跨进程/三种表示等关键 Scenario 我自己复现均通过，测试覆盖真实行为（断言 `R`*20000
不在 envelope、在 subprocess 里读回 artifact、用真实 `rmtree` 验证隔离），非实现细节耦合。

但 **Issue 1 是必须修的 CI 红灯**（且会在 closing 勾 5.4 后二次触发 checker），
**Issue 2 是新代码里的安全边界违反**（模型可控路径逃逸 + 文档声明与事实不符 + 负例测试通过理由错误）。
这两条修完（含回归测试）后复审；Issue 3–5 建议一并收口（同属「再展开路径未收口」与
「envelope 非真 bounded」两类一致性问题）。

修复后请重跑三门禁，并注意本 change 的 grill-format 修复会使 guard 恢复正常——
届时 guard 会对本 worktree 的代码写操作重新放行，符合预期。
