# Building Review: workflow-dry-run

**Verdict**: PASS

审阅范围：`cc317a9`（HEAD）对 base `08a0abe5` 的实现。零记忆独立审阅，全部结论由本 reviewer 自己跑命令/读代码得出，未采信实现者自述。

核心不变量 **`agent/subagent/scheduler.py` 零改动**已独立确认（见 Independent Verification）。本批 `tasks.md` 第 2/3/5 节的 `[x]` 逐条有真实实现；第 4 节（端到端验收）与 6.3–6.8（归档/发 PR/关 issue）按任务书不计入本批判定。

发现 1 个中等问题（I-1，`script_applied` 对不产生 run 的节点误标）与 2 个低危问题（I-2、I-3）。均**不阻塞整体**，且 I-1 不在本批 `[x]` 任务的验收范围内（tasks 2.14/3.4c 只要求"数组按调用次序消费"与"`input_source` 可见"，均满足）。故判 PASS，并把 I-1 作为实现 PR 内顺手可修的改进项列出。

---

## Tasks Verification

> 方法：逐条打开 `agent/tools/builtin/subagents.py` 的实现体读取，不只看函数名/注释；行号为 HEAD 实际行号。

### 第 2 节（测试）

| 任务 | 声称 | 证据（file:line） |
|---|---|---|
| 2.1 T-1 隔离·落盘 | [x] | `tests/agent/subagent/test_workflow_dry_run.py:222` `test_simulation_writes_nothing_to_the_callers_workspace`（sentinel + 前后快照对比）；实现侧 `subagents.py:1736-1743` 用 `tempfile.TemporaryDirectory` 造一次性 `workspace_root` |
| 2.2 T-2 隔离·注册表 | [x] | 测试 `:235`；实现侧 `subagents.py:1734-1738` 构造独立 `SubAgentManager`，从不交给调用方 manager |
| 2.2a T-2a 一次性目录无 W2 产物 | [x] | 测试 `:243`（monkeypatch `subagents_module.tempfile.TemporaryDirectory` 抓 sandbox 路径，断言无 `events.jsonl`/`root.txt`/`*.attribution`）；`assert hasattr(scheduler, "_store")` 在实现 `subagents.py:1739` |
| 2.3 T-3 隔离·零 token | [x] | 测试 `:273` + 变异验证 `:294`；实现 `subagents.py:1381` `llm = _DryRunLLM(...)` 传给一次性 manager |
| 2.4 T-4 隔离·sink | [x] | 测试 `:284`；一次性 manager 的 `graph_sink` 默认 `None`（`manager.py:526`） |
| 2.5 T-5 received foreach + 下游 | [x] | 测试 `:346` / `:367`；实现 `subagents.py:1496-1520` 按 `(node_id, item_index)` 落 `received` |
| 2.5a T-5a foreach 不坍缩 | [x] | 测试 `:346` 断言 3 项各可见且 `{item}` 已被替换；变异等价物由本 reviewer 独立复现（见 Independent Verification M1） |
| 2.5b T-5b 自动插入层可见 | [x] | 测试 `:378`（`WIDE_FOREACH_SPEC` 20 项）；实现 `subagents.py:1533` `for node in plan.nodes` + `:1539` `auto_inserted` |
| 2.6 T-6 input_seen(S1) | [x] | 测试 `:397`；实现 `subagents.py:1554` `entry["input_seen"] = _clip_text(state.raw, limit)` |
| 2.7 T-7 input_seen(S2) | [x] | 测试 `:408`（含"断言现状而非批准现状"的 docstring） |
| 2.7a T-7a input_source | [x] | 测试 `:427`；实现 `subagents.py:1608-1630` `_route_input_sources` → `_resolve_source` |
| 2.8 T-8 script 注入 | [x] | 测试 `:496`，图形态确为 `a→mid→gate`（符合 grill I3 的订正要求） |
| 2.8a T-8a 失败节点带 reason | [x] | 测试 `:528`；实现 `subagents.py:1627-1633` `_terminal_reason`（合成兜底，不留空） |
| 2.9 T-9 回边不带文本 | [x] | 测试 `:557` |
| 2.9a T-9a 聚合产出不被替身污染 | [x] | 测试 `:583` + 变异验证 `:618`；实现 `subagents.py:1744` `scheduler._aggregator = WorkflowAggregator(summarizer=TruncationSummarizer())` |
| 2.9b T-9b 无不可归因调用 | [x] | 测试 `:658`；实现 `subagents.py:1507-1508,1575` 计数 `unattributed` |
| 2.10 T-10 有界性 | [x] | 测试 `:673`；实现 `subagents.py:1478-1486` `_clip_text` + `_DRY_RUN_CLIP_SUFFIX` |
| 2.11 T-11 边界声明 / 无 workflow_id | [x] | 测试 `:697`；实现 `subagents.py:1655` `simulated: True`，报告 dict 不含 `workflow_id`（已独立 grep 确认） |
| 2.11a T-11a 答不了清单 | [x] | 测试 `:712`；实现 `subagents.py:1690-1705` `_dry_run_notes()` 四条 notes |
| 2.12 T-12 schema parity | [x] | 测试 `:726`；实现 `subagents.py:1795` `_workflow_spec_schema()` 直接复用 |
| 2.13 T-13 工具面 | [x] | 测试 `:749`；`DryRunWorkflow` 不在 `SPAWN_TOOL_NAMES`（见 spec 覆盖节） |
| 2.14 Q1 数组按调用次序 | [x] | 测试 `:773` / `:799`；实现 `subagents.py:1405-1412` `_output_for` 的 `sequence[index] if index < len(sequence) else sequence[-1]` |

### 第 3 节（实现）

| 任务 | 证据 |
|---|---|
| 3.1 `_DryRunLLM` | [x] `subagents.py:1390-1412`：回显 + 按 `current_node_id()` 注入、只返回 `LLMResponse(content=...)` 无 tool call |
| 3.2 `_DryRunWorkflowStore` + 替换 `scheduler._store` | [x] `subagents.py:1420-1442`（no-op store）+ `:1740` 替换点 |
| 3.3 模拟驱动函数 | [x] `subagents.py:1710-1755` `dry_run_workflow()` |
| 3.4 报告构造（含 plan.nodes / `(node_id,item_index)`） | [x] `subagents.py:1452-1600` `_build_dry_run_report`；**未复用也未改 `NodeState.to_dict()`**（见冗余度节） |
| 3.4a script 两形态 + 不用 oneOf | [x] `subagents.py:1445-1469` `_normalize_script`；schema `:1795-1812` |
| 3.4b 切断 collect summarizer | [x] `subagents.py:1744` |
| 3.4c `input_source` + 聚合产出标投影 | [x] `subagents.py:1554-1562`（`input_sources`）+ `:1635-1638` `_produced_kind` |
| 3.5 `DryRunWorkflowTool` | [x] `subagents.py:1827-1915`：`read_only = True`、`permission = SUBAGENT_CONTROL_PERMISSION` |
| 3.6 loop.py 一行注册 | [x] `agent/loop.py:410-413`（在 `DeclareWorkflowTool` 后，未进 `SPAWN_TOOL_NAMES`） |
| 3.7 调用计数 | [x] `subagents.py:1833` `self._calls = 0`（工具实例上）+ `:1845-1861` 软提醒/硬上限 |
| 3.8 报告 `slots` 字段 | [x] `subagents.py:1577-1587`（独立顶层字段，仅在 `slot_reads` 命中时展开） |
| 3.9 `DeclareWorkflow` 描述加指针 | [x] `subagents.py:801-802`（一句话） |
| 3.10/3.11 停轮回写 | [x] 未发生（`scheduler.py` 零改动、RIR 无需修正）；属"条件未触发即合规" |
| 3.12 文档 | [x] `docs/openspec-change-backlog.md` 入队条目 + `workflow-events.jsonl` 的 `backlog_updated` 事件 |

### 第 5 节（验证）

5.1–5.8 均 [x]，本 reviewer 独立复现了其中 5.1 / 5.2 / 5.3 / 5.4 / 5.6（数字见 Test Results）。5.9 的未勾理由（`current_spec_synced` 属归档阶段）与任务书一致，不计缺陷。

---

## Spec Scenario Coverage

`specs/multi-agent-collaboration/spec.md` 的 3 条 ADDED + 1 条 MODIFIED Requirement，逐 Scenario 映射：

### ADDED：工作流可零成本模拟执行以暴露数据投递语义

| Scenario（行号） | 实现 | 测试 |
|---|---|---|
| 模拟不产生任何副作用（:32） | 一次性 manager/root/store（`subagents.py:1734-1743`） | `test_workflow_dry_run.py:222` / `:235` / `:273` / `:284` |
| 失败节点带可解释原因（:40） | `_terminal_reason`（`:1627`）+ `evaluated` 门（`:1553`） | `:528`（含 `used_default is None` 断言） |
| 聚合节点的产出不被替身污染（:47） | `:1744` TruncationSummarizer | `:583` + 变异 `:618` |
| 判定输入可归属到来源节点（:54） | `_route_input_sources`/`_resolve_source`（`:1608`/`:1470`） | `:427` |
| 报告如实暴露 route 的判定输入（:61） | `entry["input_seen"] = state.raw`（`:1554`） | `:397` |
| 报告暴露系统自动插入的汇合层（:68） | `for node in plan.nodes` + `auto_inserted`（`:1533`/`:1539`） | `:378` |
| 报告区分 foreach 各展开项（:76） | 按 `(node_id,item_index)` 落 received（`:1496-1513`） | `:346` |
| 报告暴露重派发节点的 received（:83） | 同一个 list 追加（每轮一条） | `:557` |
| 有界性（:90） | `_clip_text` + 可见标记（`:1478`/`:1497`） | `:673` |

### ADDED：模拟结果 SHALL 声明其可信边界

| Scenario | 实现 | 测试 |
|---|---|---|
| 结果体携带模拟标记且无可消费标识符（:105） | `simulated: True`（`:1655`）；无 `workflow_id` | `:697` |
| 声明模拟无法预测的维度（:112） | `_dry_run_notes()` 的 ANSWERABLE/NOT ANSWERABLE（`:1690`） | `:712` |
| 描述含断言式的无副作用声明（:119） | `_DRY_RUN_DESCRIPTION`（`:1762`） | `:712`（`"no model calls" in desc`） |

### ADDED：工作流模拟可通过脚本指定节点产出以推演分支

| Scenario | 实现 | 测试 |
|---|---|---|
| 数组脚本按调用次序消费（:135） | `_output_for` 序号索引 + 末元素沿用（`:1405`） | `:773`（含"用尽沿用末元素"断言） |
| 脚本注入改变 route 走向（:143） | `_DryRunLLM` 按 `current_node_id()` 查表 | `:496`（blind→default / 注入→rework 两侧均断言） |
| 未注入的节点产出被标注为占位（:151） | `_DRY_RUN_STAND_IN`（`:1393`） | `:518` |

### MODIFIED：DeclareWorkflow 描述暴露循环契约

| Scenario | 实现 | 测试 |
|---|---|---|
| 声明入口引导到零成本预演（:166） | 描述新增一句（`subagents.py:801-802`） | `:760`（`"DryRunWorkflow" in declare` + 既有条款仍在） |

**覆盖结论**：无未覆盖 Scenario。三条"变异验证"测试（`test_isolation_assertions_are_discriminating` / `test_zero_token_assertion_is_discriminating` / `test_pollution_guard_is_discriminating`）均**不是恒真断言**——本 reviewer 亲手把每条对应的生产代码改坏，均观察到变红（见下节）。

---

## Independent Verification

### 1. 核心不变量：`scheduler.py` 未被改动

```
$ git diff 08a0abe5...HEAD -- agent/subagent/scheduler.py
（无输出）

$ git diff 08a0abe5...HEAD --name-only
agent/loop.py
agent/tools/builtin/subagents.py
docs/openspec-change-backlog.md
openspec/changes/workflow-dry-run/...（文档与 research）
tests/agent/subagent/test_workflow_dry_run.py
```

`scheduler.py` 不在改动清单中，确认零改动。D4 承诺兑现。

### 2. 变异复现（自己动手，改坏 → 跑 → 确认变红 → 还原）

每次变异前 `cp` 原文件到 `/tmp`，变异后 `cp` 还原，并 `diff <(git show HEAD:...) 文件` 确认与 HEAD 逐字一致。

| 变异 | 改坏方式 | 结果 |
|---|---|---|
| **M1**（对应 2.5a/3.4 的 `(node_id,item_index)` 寻址） | `received_by_node[node_id] = [...]` 单键覆盖（原为 `setdefault(...).append(...)`） | **4 failed**：`test_received_shows_each_foreach_item_with_its_own_task`、`test_back_edge_delivers_no_new_text`、`test_script_array_is_consumed_in_call_order`、`test_script_array_covers_each_foreach_item` |
| **M2**（对应 2.5b/3.4 的 `plan.nodes`） | `plan = spec`（把节点枚举换回 `spec.nodes`） | **1 failed**：`test_report_lists_auto_inserted_merge_layers` |
| **M3**（对应 2.9a/3.4b 的 summarizer 切断） | 删掉 `scheduler._aggregator = WorkflowAggregator(summarizer=TruncationSummarizer())` | **2 failed**：`test_collect_aggregate_output_is_a_bounded_projection`（聚合产出变为 `'[None produced: auto (simulated stand-in)] ## L1 Summary 1'`，即替身回复顶掉了拼接）、`test_pollution_guard_is_discriminating` |
| **M4**（对应 2.7a/3.4c 的 `input_source`） | `_resolve_source` 直接 `return upstream.node.id, None`（不追踪槽归属） | **3 failed**：`test_route_input_is_attributable_to_a_source_node`、`test_route_input_sources_concatenate_to_input_seen`、`test_slots_are_returned_only_when_a_route_reads_them` |

M3 的细节值得记录：**首次尝试的 M3 变异是无效的**（我只在下方加了一行读取、没有删除切断语句），当时 36 条全绿——这恰好说明"变异本身需要被验证"。重做（真正删除切断语句）后主用例确实变红，证明这条断言有效。这个教训也适用于实现者：`test_pollution_guard_is_discriminating` 的 monkeypatch 只作用于 `TruncationSummarizer`，若哪天 `WorkflowAggregator` 不再走 summarizer 路径，该测试**未必**能失败——这是设计上的局限而非缺陷（主用例 `:583` 在 M3 下同样变红，构成双保险）。

### 3. 关键机制读码交叉验证

| 声称 | 核验 |
|---|---|
| `_plan.nodes` 含自动插入层 | ✅ 独立跑 20 项 foreach：报告节点为 `['fan','agg','__auto_agg__agg_0_0','__auto_agg__agg_0_1']`，即 `spec.nodes`（2 个）→ `plan.nodes`（4 个） |
| 真实 workspace 零落盘 | ✅ 独立构造真实 workspace 跑宽图：目录内容 `[]` |
| 真实 manager 注册表零污染 | ✅ 同次跑：`_workflows == []`、`_workflow_stores == []` |
| 报告不泄露一次性路径/ref | ✅ grep 报告全文：`/tmp`、`dryrun-`、`artifact://`、`result_ref`、`wf_` 全部 absent |
| `_node_output` 三段语义（S1/S2） | ✅ 读 `scheduler.py:2468-2478`，与 design D2 的机制订正逐字一致 |
| `_resolve_source` 是"调真方法 + 按值验证" | ✅ `subagents.py:1470-1487` 先 `scheduler._node_output(...)` 再按三个分支用 `==` 确认；**未**复制取值逻辑 |
| 报告不碰 `NodeState.to_dict()` | ✅ grep：实现文件内零 `to_dict()` 调用；报告字段独立构造 |
| `script_applied` 的误标 | ⚠️ 见 Issues I-1 |

### 4. 边界与滥用

- **调用上限有效**：`DryRunWorkflowTool.execute`（`subagents.py:1845-1861`）在 `self._calls > 40` 时**在任何解析/模拟之前**直接返回 `dry_run_limit_reached`，测试 `:837` 覆盖（含"越界响应不含 `simulated`"）。
- **`script` 非法形态**：`_normalize_script` 返回原因字符串，调用方转 `invalid_input`（`subagents.py:1871-1873`），测试 `:812`。
- **`invalid_spec` 不冒充模拟结果**：`:1867-1868` 提前返回，测试 `:828`。
- **`_FakeManager` 只用于 schema 校验路径**：测试 `:822` 的桩只有 `config`，`_spec_bounds` 对它是 `getattr` 链（`manager.config` → `.subagents.workflow`），不会 AttributeError 崩。

---

## Issues

**I-1（中）`script_applied` 对不产生 run 的节点误标为 `True`，与报告自身 notes 相互矛盾**

- 位置：`agent/tools/builtin/subagents.py:1547-1548`
- 现象：`entry["script_applied"] = True` 只判断 `node.id in scripted_nodes`，**不看该节点是否真的消费了 script**。独立复现（对 route 与 aggregate 节点注入）：

  ```
  echo | kind=route     | script_applied=True  | produced_kind=script | produced="default -> ['end']"
  end  | kind=aggregate | script_applied=True  | produced_kind=bounded_projection
  ```

  同一份报告的 `notes` 里却写着"`script` … has no effect on route nodes or on `collect` aggregates"。模型据 `script_applied: true` 会以为注入生效了（而 D3/R5 明说的目的是"防止对不产生 run 的节点注入却以为生效"）。
- 另注：给 `route` 节点注入时，报告里也**没有** `input_sources` 之外的纠错提示。
- **为何不阻塞**：本批 `[x]` 任务（2.14 / 3.4 / 3.4c）未把该字段列入验收；且 `script_applied` / `produced_kind` **两个字段没有任何测试断言**（已 grep 确认），它们是超出 spec 契约的额外信息面。
- **建议**：改为按实际生效判定，例如 `entry["script_applied"] = node.kind == "subagent" and node.id in scripted_nodes`，或在 `script` 命中不产生 run 的节点时往 `warnings` 推一条可解释提示（与 `_terminal_reason` 的"绝不留空"同口径）。补一条回归测试。

**I-2（低）`script` 的 `anyOf` 是嵌套的，与本仓 self-imposed 的"不用 anyOf"纪律存在张力，且无测试守卫**

- 位置：`agent/tools/builtin/subagents.py:1795-1812`（`script.additionalProperties.anyOf`）
- 现象：文件自身的注释（`:516-518`）与 `#246` RIR 都记为"Anthropic `input_schema` 拒绝顶层 `oneOf`/`anyOf`"，实现把 `anyOf` 放到**嵌套**位置。`test_script_schema_avoids_top_level_one_of`（`:734`）只断言 `"oneOf" not in json.dumps(schema)`、`"anyOf" not in schema`（顶层 key），**没有**断言这两条不变量在嵌套层也成立——即该测试对嵌套写法是"放行"的。
- 这是有意的设计选择（嵌套 union 在 Anthropic 上通常可接受，且运行期 `_normalize_script` 承担判别），但**"无要求"与"未验证的假设"是两回事**：静态校验器如果哪天收紧，只有真实 API 报错才会发现。
- **建议**：在 tasks / design 里明确记录"嵌套 `anyOf` 是可接受的，顶层不可"，或在 PR 描述里补一条真实 API 调用证据。当前先记 debt 亦可。

**I-3（低）`unattributed_llm_calls > 0` 的失败模式未被断言钉死为"只应由聚合漂移触发"**

- 位置：`agent/tools/builtin/subagents.py:1570-1575`
- 现象：实现把"归不到已知节点"的条目一律并进 `unattributed`。真正想要的不变量是"没有第二条未切断的 LLM 通道"。我尝试构造 plan 收缩（`_expand_plan` → `_prune_states`）导致 `_states` 缺项的场景（20 项 foreach 回边带 `script` 触发 `max_items=0` 重展开），**未能复现**（`unattributed` 恒为 0，report 节点完整）——所以这是**假设性**风险，不是已确认缺陷。
- **建议**：若要更强的保证，可把 `unattributed` 拆成"无节点身份的调用"与"身份已失效的调用"两个计数，前者用于断言（对应 F4a），后者用于诊断。

**无阻塞性问题。** 本 reviewer 未发现安全漏洞、核心功能缺失或测试大面积失败。

---

## Test Results

所有命令在 worktree `/home/happy/my-agent/.claude/worktrees/workflow-dry-run` 执行，`export PATH=/home/happy/.local/bin:$PATH`，`.venv` 已 `uv sync --extra dev`。

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_dry_run.py -q` | `36 passed in 4.12s` |
| `uv run pytest -q --ignore=tests/web_tests` | `2 failed, 3397 passed, 2 skipped, 1 warning in 173.74s` |
| `uv run pytest --collect-only -q`（全量，含 web_tests） | `3834 tests collected` |
| `uv run python scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed` |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 29 passed, 0 failed (29 items)` |
| `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/dryrun-smoke` | `Tasks: 72 \| passed: 5 \| warnings: 0 \| unsupported: 38 \| failed: 29`（与既有 smoke 基线形态一致，无新爆点） |

**2 failed 为任务书声明的环境噪声**（非本 change 缺陷）：
`tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` 与 `::test_malformed_git_file_falls_back_to_scan`，根因是本机 `/tmp/.git` 是真实目录，`_find_scope_root` 走到 `/tmp`。

**实现者声称的数字已独立复现**：`3834 collected = 3823 passed + 2 failed + 9 skipped`，与实现者给出的 `3823 passed, 2 failed, 9 skipped` 逐项吻合（本 reviewer 跑 web_tests 之外的子集得 `3397 passed`，加回 web_tests 的 426 条即 3823）。数字属实，未见美化。

**实现者"假失败误判"一事已如实处理**：其 worktree `.venv` 一度缺 dev extra 导致 `uv run pytest` 回退系统 python（缺 `tree_sitter_bash`）产生约 236 个假失败。当前 `.venv` 状态正确（`uv run python -c "import tree_sitter_bash"` 通过，`sys.executable` 指向 worktree 的 `.venv/bin/python3`），失败面已收敛到上述 2 条环境噪声。**判断：已如实处理，无隐瞒。**

---

## Notes

1. **关于 `bash_ir.py` 吞 `ImportError`**：已独立确认。`agent/tools/bash_ir.py:241-277` 的 `analyze()` 有三处 `except Exception: return BashAnalysis(..., has_errors=True)`，其中 `_parser().parse()` 一处的 `_parser`（`:64-66`）会 `import tree_sitter_bash`——该导入失败时异常被吞成 `has_errors=True`。独立复现（模拟 `tree_sitter_bash` 缺失）：`analyze('rm -rf /')` 返回 `has_errors = True`、`segments = [Segment(argv=(), dynamic=False)]`、`redirects = []`。消费端 `agent/tools/command_guard.py:788-790` 走**fail-closed**（`has_errors → ASK` 交审批层，不 ALLOW），所以**后果是"守门退化为审批"而非"守门放行"**，安全上可接受。
   - **是否值得另开 issue**：值得，但**低优先**。真实风险面是：依赖缺失（部署/打包缺 extra）时安全护栏静默降级为 ASK，运维侧不会看到任何告警（`analyze` 是 `Never raises` 设计，把"依赖坏了"与"输入不可解析"混成一个 `has_errors=True`）。建议 issue 的方向是**可观测性**（依赖缺失时 log/态区分），不是行为修正。
   - **本 change 未修它对**：`bash_ir.py` 在本 change 的 diff 之外，修改它会引入与 dry-run 无关的回归面，不属本 change 范围。实现者的处理（发现、如实记录、不顺手改）是正确的。

2. **`docs/architecture.md` 的工具清单段落无事实变化**：`docs/architecture.md:57` 的"workflow 资产工具"一行只列了资产四件套（`SaveWorkflowAsset`/`ListWorkflowAssets`/`GetWorkflowAsset`/`RunWorkflowAsset`），`DeclareWorkflow`/`StartWorkflow`/`RunWorkflow` 等 DSL 入口本就不在该表里——`DryRunWorkflow` 同样不进，所以该段落**无需更新**（tasks 3.12 的"如无事实变化则在 review 记录中说明"，本报告即该说明）。`README.md`/`README_EN.md`/`CONTEXT.md` 全仓 grep `DeclareWorkflow`/`DryRunWorkflow` 零命中，亦无事实变化。

3. **`workflow-events.jsonl` 只有 `backlog_updated` 一项**：与 tasks 5.9 的说明一致（`current_spec_synced` 属归档阶段，由主 session 在 spec 同步时落）。本 change 尚未归档、spec delta 仍在 change 目录下，故当前状态正确。

4. **受保护路径未被本批改动**：本 diff 触及的受保护面仅 `docs/openspec-change-backlog.md`（有 `backlog_updated` 事件）与 `openspec/changes/workflow-dry-run/**`（change 自身目录）。`openspec/specs/**` 与 `openspec/changes/archive/**` 未动。

5. **CI 完整性**：`.github/workflows/ci.yml`、`scripts/**`、`pyproject.toml`、`benchmarks/baseline.json` 在本 diff 中**零改动**，无弱化既有门禁的痕迹。`benchmark-gate` 的 baseline 不含工具面指纹，新增工具不改变 benchmark 判定口径。

---

## Round 2（commit 805e25b）

**Round 2 Verdict**: PASS

审阅范围：`805e25b`（HEAD）相对 Round 1 审过的 `cc317a9` 的**修复批**（I-1 / I-2 / M3 变异升级），外加对修复是否引入新问题的复核。base = `08a0abe5`，核心不变量 `agent/subagent/scheduler.py` 零改动已独立确认。
**零记忆独立审阅**：本轮的每一条结论都由本人自己写探针脚本 / 亲手做变异得出，Round 1 报告的结论未被采信（其「PASS + I-1 不阻塞」的定性也与本轮不同——I-1 是实打实修好了，不是「顺手可修」）。
修复触及的 3 个文件：`agent/tools/builtin/subagents.py`（+38 行，实现）、`tests/agent/subagent/test_workflow_dry_run.py`（+159 行，回归测试）、`openspec/changes/workflow-dry-run/tasks.md`（+7 行，3b 节）。

### 修复核验

#### I-1（中）`script_applied` 对不产生 run 的节点误标 —— **已真修好**

修复方式（`subagents.py:1531`）：新增 `called_nodes = {node_id for node_id, _, _, _ in llm.calls if node_id is not None}`，判定改为 `script_applied = node.id in scripted_nodes and node.id in called_nodes`；`produced_kind` 同步改用该判定（`:1548`）；并对 `scripted_nodes - called_nodes` 逐条推 `warnings`（`:1587-1598`），按「图中无此 id / 该 kind 不跑模型 / 从未跑」三分支给可行动原因。

**独立探针（自写 `/tmp/probe_i1.py`，未复用仓库测试）**，实测矩阵：

| 注入目标 | kind / strategy | HEAD 实测 | 期望 | 结论 |
|---|---|---|---|---|
| `mid`（真跑过） | subagent | `script_applied=True`，`produced_kind='script'`，`produced='GAPS'` | 生效 | ✅ |
| `gate` | route | **无** `script_applied`，`produced_kind='stand_in'` | 不生效 | ✅ |
| `nonexistent` | 图中不存在 | warning：`there is no node with that id in the execution plan` | 可行动原因 | ✅ |
| `root` | aggregate/collect | **无** `script_applied`，`produced_kind='bounded_projection'` | 不生效 | ✅ |
| `sum` | aggregate/**llm** | `script_applied=True`，`produced='SYNTHESISED'` | **生效** | ✅ |
| `fan` / `critic` | foreach / subagent | 均 `script_applied=True` | 生效 | ✅ |
| `rework`（分支未选中） | subagent | **无** `script_applied`，warning：`it never ran (status=skipped)` | 可行动原因 | ✅ |
| 不传 `script` | — | `warnings=[]`，无任何 `script_applied` | 无噪声 | ✅ |

原先的「报告自身 notes 与 `script_applied` 自相矛盾」问题**已消除**：`notes` 第 6 条的措辞（`script … has no effect on route nodes or on collect aggregates`）现与实际字段完全一致。修复没有采取 Round 1 建议的「按 kind 硬编码」（那会漏掉 `llm` 聚合与自动插入层），而是用「是否真的发过调用」这一**行为判据**——更正确，且自动覆盖自动插入的 `__auto_agg__*`（llm 策略）层（实测：对其注入 `AUTO0` 生效）。

**变异验证（本人亲手）**：
- 变异 A：`script_applied = node.id in scripted_nodes`（改回旧判据）→ `test_script_for_a_node_that_runs_no_model_is_reported_as_ineffective` **1 failed**；还原后 39 passed。✅
- 变异 B：`_node_runs_a_model` 的 route 分支改为 `if False`（让 route 也被当成「跑模型」）→ 同一测试 **1 failed**。✅ 即「runs no model」这条可行动原因确被钉住。

#### I-2（低）`anyOf` 纪律未钉死 —— **已真修好**

`test_script_schema_avoids_top_level_one_of` 改为断言 `not ({"oneOf","anyOf","allOf"} & set(schema))`（顶层三禁）；新增 `test_script_schema_uses_no_anyof_outside_the_one_union`，用递归 `_anyof_paths()` 断言路径集合**逐字等于** `["properties.script.additionalProperties.anyOf"]`。

**变异验证（本人亲手）**：给 `properties.max_report_chars` 临时加一个 `anyOf`（即"第二个 anyOf"）→ `test_script_schema_uses_no_anyof_outside_the_one_union` **1 failed**；还原后 39 passed。✅ 测试确实会红，不是恒真断言。该写法（路径全等而非"计数=1"）比单纯计数更强：位置一旦漂移也会红。

#### M3 变异升级 —— **升级是忠实的**

`test_pollution_guard_is_discriminating` 重写为：monkeypatch `subagents_module._DryRunLLM` 为子类（在 `current_node_id() is None` 的压缩调用上把内容换成 `[SUMMARY-PLACEHOLDER]`）**并**把 `subagents_module.WorkflowAggregator` 换成强制 `LLMSummarizer(holder["llm"])` 的工厂——即精确复刻「实现没有切断聚合路径时」的真实世界（那时 `scheduler._build_summarizer()` 返回的正是 `LLMSummarizer` 包着**这个假 LLM**）。Round 1 的代理变异（替换 `TruncationSummarizer`）确实无法区分「切断生效」与「没走到」，这一版可以。

**变异验证（本人亲手，两个方向）**：
- 方向一（改坏实现）：删除 `scheduler._aggregator = WorkflowAggregator(summarizer=TruncationSummarizer())` 这一行 → **主用例** `test_collect_aggregate_output_is_a_bounded_projection` **1 failed**（同时 `test_pollution_guard_is_discriminating` 也红）。✅ 这正是任务书要求的忠实性：不切断聚合路径，主用例必红。
- 方向二（改坏测试）：把测试里的污染分支改为 `if False:` → `test_pollution_guard_is_discriminating` **1 failed**。✅ 该测试不是空转。

**「忘记切断」在真实现路径下可复现**（不只是构造）：删掉那一行后，`root` 的产出变成 `'[None produced: auto (simulated stand-in)] ## L1 Summary 1'`——替身回复顶掉了拼接，正是 F4/F4a 要防的谎。且新增的 `assert report["unattributed_llm_calls"] >= 1` 同时钉住 F4a 的第二症状（压缩调用归不到节点）。✅

### 独立复现的变异

| # | 变异对象 | 改坏方式 | 结果 |
|---|---|---|---|
| 1 | 实现 | `script_applied` 改回 `node.id in scripted_nodes` | **1 failed**（`test_script_for_a_node_that_runs_no_model_…`） |
| 2 | 实现 | `_node_runs_a_model` route 分支 → `if False` | **1 failed**（同上） |
| 3 | 实现 | 给 `max_report_chars` 加第二个 `anyOf` | **1 failed**（`test_script_schema_uses_no_anyof_outside_the_one_union`） |
| 4 | 实现 | 删 `scheduler._aggregator = WorkflowAggregator(…)` | **1 failed**（主用例 + M3 测试） |
| 5 | 测试 | M3 测试的污染分支 → `if False` | **1 failed**（`test_pollution_guard_is_discriminating`） |
| 6 | 实现 | **`_node_runs_a_model` 的 aggregate 分支 → `return False`** | **0 failed（存活！）** → 见 N-1 |

每次变异后均以 `diff <(git show HEAD:<path>) <path>` 确认还原到与 HEAD 逐字一致（两次比对均无输出）。变异 1–5 全部按预期变红，说明 Round 1 的 3 条修复都带了**真正有判别力**的回归测试。

### 新问题

**N-1（低）`_node_runs_a_model` 的「aggregate/llm 会跑模型」这一支未被测试钉住（变异存活）**

- 位置：`agent/tools/builtin/subagents.py:1662-1666`（`if node.kind == "aggregate": return node.strategy == "llm"`）。
- 现象：把该分支改成 `return False`（即"所有 aggregate 都不跑模型"）后，**39 条测试全绿（变异存活）**。构造的判别场景是「`llm` 聚合因上游撞 `max_runs` 而**从未运行**，调用方仍给它注入了 `script`」：

  ```
  变异体（错）：`script` for node 'synth' had no effect: that node kind runs no model,
                so it produces no output of its own (route nodes just pick a branch;
                a `collect` aggregate just merges text)
  HEAD  （对）：`script` for node 'synth' had no effect: it never ran (status=cancelled)
  ```
  即变异体把「它没跑」错报成「这类节点永远不跑」，而后者是一句关于拓扑的**假陈述**——正是 I-1 这一整条修复要消灭的那类谎。另一侧分支 `test_script_for_an_llm_aggregate_does_apply` 只覆盖「llm 聚合**跑到了**」的情形，覆盖不到这一半。
- **为何不阻塞**：HEAD 的实现是**正确**的（我逐条实测：llm 聚合跑到 → `script_applied=True`；未跑到 → 报 `it never ran (status=…)`）。这是**测试覆盖缺口**，不是实现缺陷；且 `warnings` 文案目前无 spec 契约。Round 1 的 I-1 定级为「中」，本轮复发形态属其**低危投影**。
- **建议**（可选，一行即可强化）：在 `test_script_for_a_node_that_runs_no_model_is_reported_as_ineffective` 里补一段「`llm` 聚合因闸门未跑 → warning 必须出现 `never ran` 且**不得**出现 `runs no model`」，即可让变异 6 变红。

**N-2（低，且为改动前既有问题，非本修复引入）`warnings` 数组不受 `max_report_chars` 约束**

- 现象：`max_report_chars` 只截断 `produced` / `received` / `input_seen` / `slots` 等**文本字段**，`warnings` 的条目数与其内部文本**不截断**，且节点 id 由调用方 spec 决定。实测：
  - 一次传 2000 个不存在的 script 键 → 报告 **202,628 字符**（`max_report_chars=800`），warnings 2000 条；
  - 单个超长键 → 报告 51,829 字符，**单条 warning 50,087 字符**；
  - **完全不传 `script`**（走修复前就存在的 `node X ended as Y: <reason>` 路径）、节点 id 长 30,000 → 报告 **123,243 字符**，单条 warning 60,149 字符。
- **归因**：我把三条路径都归到 **`cc317a9`（Round 1 前的实现）** 上跑的——第 3 条在**完全不涉及新代码**的情况下即可复现 123KB 报告。所以这是**既有**的有界性缺口，`805e25b` 只是新添了一条同类路径（无效注入的警告），**不是本修复引入的新问题**。D5 的「所有文本截断」在 spec 里限定的是「报告中的每个文本字段」，`warnings` 作为诊断通道未被覆盖，spec 与实现口径一致。
- **建议**（可选）：若关心上下文膨胀，可给 `warnings` 加「条目数上限 + 单条截断」；或明确记 debt。不阻塞。

**无中等以上新问题。** 未发现回归、未发现与 spec delta 冲突、未发现安全面变化（修复只动报告构造与一个判定谓词，不碰隔离手段）。

### 复核 8 个维度（本批 = tasks 第 2/3/5 节 + 第 3b 节）

| 维度 | 结论 |
|---|---|
| 任务逐项验证 | 第 3b.1–3b.4 逐条有真实实现与测试落点：3b.1 → `subagents.py:1531/1540/1587` + 2 条新测试；3b.2 → 新测试 `test_script_schema_uses_no_anyof_outside_the_one_union`；3b.3 → M3 测试重写；3b.4 → 如实「不改实现 + 记入报告」，与「构造未复现」的事实相符。第 2/3/5 节同 Round 1，本轮抽查多组（见上）仍成立。 |
| 正确性 | 新判据 `node.id in called_nodes` 的行为判据优于 Round 1 建议的 kind 硬编码：自动覆盖 `__auto_agg__*` 自动插入层（实测生效）。warnings 三分支分类正确（我对 8 种注入形态实测，无一条误分类）。 |
| Spec 对齐 | spec delta 的「`script` 对不产生 run 的节点不生效，工具 SHALL 说明 / 报告 SHALL 说明」现由字段 + warnings **双重**满足；`test_script_for_an_llm_aggregate_does_apply` 守住「`llm` 聚合不是不产生 run 的节点」这一 spec 边界，未越界把 `llm` 聚合也说成不生效。 |
| 冗余度 | 修复未新增冗余抽象：`called_nodes` 直接复用已有 `llm.calls`（该结构本就是 `unattributed` 计数的来源），`_node_runs_a_model` 是单点谓词。无重复取值逻辑。 |
| 测试覆盖 | 净增 3 条（36→39）。**缺口**：N-1 所述 `_node_runs_a_model` 的 aggregate/llm 支；其余新分支均有判别力测试（变异 1–5 全红）。 |
| 安全性 | 修复不触碰隔离手段（一次性 manager / `workspace_root` / `_store` 替换 / 假 LLM），不引入新 IO 面。`script` 键仅用于字符串插值进 warnings，无注入面（键经过 `sorted()` 与 f-string，不 eval）。 |
| 可维护性 | 新增 2 处注释解释了「为什么用行为判据而非 kind」与「为什么静默无效果是陷阱」，与 D3/R5 的动机对齐；`_node_runs_a_model` 带 docstring 与 kind 分派表。 |
| CI 完整性 | 修复批零改动 `.github/**`、`scripts/**`、`pyproject.toml`、`benchmarks/baseline.json`（已独立 grep 确认），无弱化门禁痕迹。 |

**核心不变量**：`git diff 08a0abe5...HEAD -- agent/subagent/scheduler.py` **无输出**，D4 承诺在本批仍兑现（修复只动 `subagents.py` 的报告构造层）。

### 范围说明：artifact checker 当前离线红灯（**不在本批判定内**）

`uv run python scripts/check_openspec_artifacts.py` 现报 `review manifest missing: …/building-review-manifest.json`（exit 1）。我做了归因实验确认**这不是修复批造成的**：

- 在 HEAD 的干净树（`git archive HEAD` 解包到 `/tmp`，`reviews/` 下只有 `grill-design.md`）上跑 checker → `OpenSpec artifact checks passed`（exit 0）；
- 仅额外拷入 Round 1 的 `building-review.md` → 立刻复现 `review manifest missing`（exit 1）。

机理：checker 的 `_check_review_manifests` 对 `reviews/*-review.md` 逐个调 `verify_review_manifest`，manifest 不在即报错；Round 1 报告落盘后该门才被激活。tasks 6.1/6.2（manifest 在 tasks 最终化后生成）按任务书属**未勾/不在本批**，故：

- **不构成 Round 2 缺陷**；
- 但**提示下一阶段**：`/review-loop` 收尾与 6.2 之前，checker 会持续红灯——需在 tasks 最终化后生成 `building-review-manifest.json` 才会转绿（这符合仓库既有纪律，不是本次改动引入的债）。

同理，本 worktree 工作区未提交的 `docs/openspec-change-backlog.md` 与 `workflow-events.jsonl` 两处改动（`805e25b` 只提交了 3 个文件）属实现者的收尾动作，不属本批审阅对象，仅记录。

### Test Results

全部命令在本 worktree 执行，`export PATH=/home/happy/.local/bin:$PATH`，`.venv` 已就绪。

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_dry_run.py -q` | `39 passed in 4.27s`（Round 1 基线 36 → 净增 3 条） |
| `uv run pytest tests/agent/subagent/ tests/agent/tools/ -q` | `1622 passed in 56.15s` |
| `uv run pytest -q --ignore=tests/web_tests` | `2 failed, 3400 passed, 2 skipped in 174.31s`（Round 1 为 3397 passed；2 failed 为任务书声明的 `/tmp/.git` 环境噪声） |
| `uv run pytest tests/agent/subagent/test_workflow_tools.py -q` | `17 passed in 1.36s`（工具面回归） |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 29 passed, 0 failed (29 items)`（含 `change/workflow-dry-run`） |
| `uv run python scripts/check_openspec_artifacts.py` | **exit 1** — `review manifest missing`（归因见上节：由 Round 1 报告落盘激活，非本批引入） |
| `git diff 08a0abe5...HEAD -- agent/subagent/scheduler.py` | 无输出（零改动，独立确认） |
| 变异 ×6（上表） | 5 红 1 存活（存活项 = N-1） |

`tests/web_tests/` 按任务书要求未运行（与本 change 无关，本机会挂起）。

### 结论

**Round 2 Verdict: PASS。**

I-1 / I-2 / M3 三条修复经**独立探针 + 亲手变异**逐条验证，全部真修好，且都带了有判别力的回归测试（变异 1–5 全部按预期变红）。M3 的变异升级是**忠实**的：删掉实现里的聚合切断语句后，主用例 `test_collect_aggregate_output_is_a_bounded_projection` 确实变红，不再是 Round 1 那种「代理变异未必变红」的形态。修复未引入新问题——新判据是行为判据而非 kind 硬编码，自动覆盖了自动插入的 llm 汇合层；`scheduler.py` 零改动这一核心不变量在本批仍成立。

本轮新增 2 条低危项：N-1（`_node_runs_a_model` 的 llm 聚合支无测试，变异存活，但 HEAD 实现正确）与 N-2（`warnings` 不受 `max_report_chars` 约束——实证为 **Round 1 之前既有**的缺口，非本修复引入）。两者均不达「中等以上」，不阻塞整体，建议在 PR 内顺手补 N-1 的一条断言。

---

## Round 3（commit 83ec63b）

**Round 3 Verdict**: PASS

审阅范围：`83ec63b`（HEAD）相对 Round 2 审过的 `805e25b` 的**修复批**（N-1 变异存活 / N-2 warnings 无界），base = `08a0abe5`。**零记忆独立审阅**：本节的每一条结论都由本人自写探针脚本（`/tmp/r3/*.py`，不复用仓库测试的任何 helper）与亲手变异得出；Round 1 / Round 2 报告的结论**未被采信**，仅用于定位改动面。修复批只动 3 个文件：`agent/tools/builtin/subagents.py`（+18 行）、`tests/agent/subagent/test_workflow_dry_run.py`（+88 行）、`tasks.md`（+2 行，3b.5/3b.6）。

### 本轮核验

#### N-1（`_node_runs_a_model` 的 aggregate/llm 支）—— **已真修复，变异被杀死**

实现侧无改动（`subagents.py:1677-1684` 的分支逻辑与 Round 2 相同），修复方式是**补测试**。我自己构造探针（`/tmp/r3/probe_n1.py` / `probe_n1b.py`），三条行为路径逐一实测：

| 场景 | HEAD 实测 | 期望 |
|---|---|---|
| `llm` 聚合**从未跑到**（route 未选中）+ 注入 `script` | `status=skipped`；**无** `script_applied`；warning = `` `script` for node 'sum' had no effect: it never ran (status=skipped) `` | 「没跑到」✅ |
| `llm` 聚合**跑到**（控制组，`script={"a":"GO","sum":"SYNTHESISED"}`） | `sum.status=completed`、`script_applied=True`、`produced='SYNTHESISED'` | 生效 ✅ |
| `collect` 聚合 + 注入 `script` | **无** `script_applied`；warning = `…that node kind runs no model…` | 不生效、且原因正确 ✅ |

即两条分支的**文案判据已经被分开**：「没跑到」与「这类节点不跑模型」是两句不同陈述，前者不再被后者冒名。Round 2 记录的 N-1 病灶（变异体把「它没跑」错报成关于拓扑的假陈述）在 HEAD 上不可复现。

#### N-2（`warnings` 无界）—— **已真修复，条数上界与单条截断都生效**

`subagents.py:1315-1318` 新增 `_WARNINGS_MAX = 40` / `_WARNINGS_CHARS_PER_ITEM = 200`；`:1625` 单条 `_clip_text`；`:1631-1633` 条数上界 `max(1, min(40, limit * 200 // 200))` 并把差额落进 `warnings_omitted`（`:1666` 进报告）。

**独立实测**（`/tmp/r3/probe_round3.py` / `probe_warnsize.py`，`max_runs=1` 的 60 节点长链——正是 N-2 里把报告撑爆的那类图）：

| 输入 | `max_report_chars` | warnings 条数 | `warnings_omitted` | 单条最大 | warnings 块 JSON 体积 |
|---|---|---|---|---|---|
| 60 节点长链 | 200 | 40 | 20 | 132 | 2,623 |
| 60 节点长链 | 800 | 40 | 20 | 132 | 2,623 |
| 60 节点长链 | 5000 | 40 | 20 | 132 | 2,623 |
| 40 节点、每 id 30,000 字符 | 800 | 40 | 0 | **815** | 32,077 |

结论：条数上界**饱和在 40**（与 `_WARNINGS_MAX` 一致，不再随 `limit` 或图规模增长），单条截断把 30,000 字符的 id 压到 815 字符（含 `…[+n chars]` 标记与引号）。**不静默**：被丢掉的条数落进 `warnings_omitted`，且我确认报告里图级提示（`the graph did not run to completion…`）因 `warnings.insert(0, …)`（`:1617`）而**永远位于保留区内**——截断优先丢的是尾部细节，最要紧的那条不会被裁掉。

### 独立复现的变异

每次变异前 `cp` 原文件到 `/tmp/r3/subagents.py.head`，变异后 `cp` 还原，并以 `diff <(git show HEAD:agent/tools/builtin/subagents.py) agent/tools/builtin/subagents.py` 确认还原到与 HEAD 逐字一致（每轮之后均无输出）。

| # | 变异对象 | 改坏方式 | 结果 |
|---|---|---|---|
| 1 | 实现 | `_node_runs_a_model` 的 aggregate 分支 → `return False` | **1 failed** — `test_a_scripted_llm_aggregate_that_never_ran_is_not_called_model_less`（报错文本正是「runs no model」冒充「never ran」） |
| 2 | 实现 | `_node_runs_a_model` **整函数短路**成 `return False` | **1 failed** — 同一条测试（两种变异形态都被杀死） |
| 3 | 实现 | 删掉条数裁剪（`warnings = warnings[:warnings_limit]` 与其换算） | **1 failed** — `test_the_warning_list_is_bounded_too`（实测 60 条未被裁） |
| 4 | 实现 | 删掉**单条**截断（`warnings = [_clip_text(w, limit) …]`） | **0 failed（存活！）** → 见 N-3 |

变异 1–3 证明 N-1 与 N-2 的**条数**这一半都带着有判别力的回归测试；变异 4 暴露了**单条**截断这一半没被任何测试守护（探针实测：去掉后单条暴涨到 30,060 字符、warnings 块 1,172,623 字符、整份报告 4.7 MB，而 41 条测试全绿）。

### 新问题

**N-3（低）`warnings` 的「单条截断」这一半无测试守护（变异存活）——实现正确但没被钉住**

- 位置：`agent/tools/builtin/subagents.py:1625`；对应测试 `tests/agent/subagent/test_workflow_dry_run.py:739`。
- 现象：`test_the_warning_list_is_bounded_too` 的全部断言都只覆盖**条数**维度（`len(warnings) == bound` / `warnings_omitted` / 块体积上界 `bound * (limit + 40)`）。删掉单条 `_clip_text` 后，条数上界仍成立、`warnings_omitted` 仍正确、块体积断言因 `bound=40` 且每条 30,060 字符而**本应**变红——但该测试用的图（`_many_failed_nodes_spec`）节点 id 只有 2 字符，单条 warning 天然远小于上限，所以那条体积断言也过不去触发条件。结果：**变异 4 全绿**。
- **实现本身是对的**（我实测单条 30,000 字符 id 被压到 815 字符），这是**测试覆盖缺口**，不是行为缺陷。且本轮之前的既有实现里单条本就是无界的（Round 2 已把这条路径认定为「Round 1 之前既有缺口」），所以 N-3 是「修复只被部分钉住」，不是「修复没生效」。
- **建议**（一行即可）：在 `_many_failed_nodes_spec` 里把节点 id 拉长（如 `f"n{i}" + "x" * 500`），或在既有断言旁补一条「单条 warning ≤ limit + 32」的显式断言——当前 `all(len(w) <= limit + 32 …)` 那一条已经写了，只是喂进去的数据触发不到它。把长 id 图加进去即可让变异 4（与变异 3）同时变红。不阻塞。

**另记一条观察（不计缺陷，说明归因）**：极端情况下（40 个 id 各 30,000 字符）整份报告仍有 3.5 MB。归因**不是** warnings 块（已压到 32 KB），而是 `nodes[].id` ——调用方 spec 自带的标识符，`_parse_node`（`agent/subagent/workflow.py:483-486`）只校验「非空字符串」、**不校验长度**，`max_nodes` 管的是节点**个数**不是**长度**。报告体积因此与调用方输入同阶（实测放大 1.16x，输入 spec 自身 243 KB）。Round 2 已把节点条目明确划出 N-2 范围（「随图规模线性增长是预期的，受 `max_nodes` 结构闸管辖」），本轮复核同意该定性：报告没有放大出输入之外的新规模，且 `max_report_chars` 从未承诺约束**整份报告**的体积。另记此条只为把 3.5 MB 这个数字归到正确的因上，避免下一轮误判为 N-2 未修好。

**无中等以上新问题**：未发现回归、未发现与 spec delta 冲突、未发现安全面变化。修复只动报告构造层的两个常量与两处收尾语句，不触碰任何隔离手段（一次性 manager / `workspace_root` / `_store` 替换 / 假 LLM）。

### 回归检查（本轮新增问题面）

| 检查项 | 结论 |
|---|---|
| 新字段 `warnings_omitted` 是否破坏消费方 | 全仓 grep：除实现与本次测试外**零消费者**；spec delta 未点名 `warnings`，新增字段是纯增量。✅ |
| 字段语义是否与 spec 冲突 | spec 的 `有界性` Scenario 要求「报告中的每个文本字段 SHALL 被截断到配置上界」+「SHALL NOT 静默丢弃」。`warnings` 从「无界」改为「有界且显式报告省略数」，是**朝 spec 收敛**，不是偏离。✅ |
| 与原 N-2 归因是否一致 | Round 2 说 N-2 是「Round 1 之前既有」。我复核：修复前该路径确实无界，修复把它纳入了界——归类为「既有缺口的修复」，与 Round 2 表述一致。✅ |
| 3b.5/3b.6 任务文本与实现是否相符 | tasks 3b.5 声称「新增回归测试 + 变异必红」——已由变异 1/2 证实；3b.6 声称「每条单个截断 + 条数硬上界 + 显式 `warnings_omitted`」——三者实现均存在，但见 N-3（只有后两者被测试钉住）。✅（3b.6 的「变异验证：去掉条数裁剪必红」这一句**属实**，已由变异 3 证实。） |
| 是否有实现者自述与事实不符 | 提交信息称「去掉条数裁剪 → 必红」属实；未发现夸大的完成度声明。✅ |

### Test Results

全部命令在本 worktree（`/home/happy/my-agent/.claude/worktrees/workflow-dry-run`）执行，`export PATH=/home/happy/.local/bin:$PATH`。

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_dry_run.py -q` | `41 passed in 4.28s`（Round 2 基线 39 → 净增 2 条） |
| `uv run pytest tests/agent/subagent/ tests/agent/tools/ -q` | `1624 passed in 42.57s` |
| `uv run pytest tests/agent/subagent/test_workflow_tools.py -q`（5.7 工具面回归） | `17 passed in 1.28s` |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 29 passed, 0 failed (29 items)`（含 `change/workflow-dry-run`） |
| `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/r3-smoke`（5.6） | `Tasks: 72 \| passed: 5 \| warnings: 0 \| unsupported: 38 \| failed: 29`（与既有 smoke 基线形态一致） |
| `git diff 08a0abe5...HEAD -- agent/subagent/scheduler.py` | **无输出**（核心不变量仍成立，独立确认） |
| `git diff 08a0abe5...HEAD --name-only \| grep -E "^\.github/\|^scripts/\|pyproject\|benchmarks/baseline"` | 无输出（CI 完整性：门禁未被弱化） |
| `uv run python scripts/check_openspec_artifacts.py` | **exit 1** — `review manifest missing`（任务书已声明为预期：manifest 由主 session 在本轮 PASS 后按 tasks 6.2 生成） |
| 变异 ×4（上表） | 3 红 1 存活（存活项 = N-3） |

`tests/web_tests/` 按任务书要求未运行。任务书声明的环境噪声（`tests/agent/memory/test_persistent.py` 的 2 条 `TestFindScopeRoot`）未出现在本轮运行的测试面内。

**本批 `tasks.md` 第 2/3/5 节 + 第 3b 节的 `[x]` 逐条核对**：第 3b.5 / 3b.6 为本轮新增，均已核实有真实实现与测试落点（3b.6 的实现完整、测试只覆盖一半，见 N-3）；第 2/3/5 节的 `[x]` 经抽查（2.5b / 2.7a / 2.9a / 2.10 / 2.12 / 2.13 / 3.4b / 3.4c / 3.6 / 5.1 / 5.3 / 5.6 / 5.7 / 5.8）在本批仍成立。第 4 节（端到端验收）与 6.3–6.8（归档 / 发 PR / 关 issue）按任务书**不计入本批判定**，其 `[ ]` 不算缺陷。

### 结论

**Round 3 Verdict: PASS。**

N-1 与 N-2 两条修复经**自写探针 + 亲手变异**独立验证，**均真修复**：N-1 的「没跑到 vs 这类节点不跑」两句陈述已在字段与 warnings 文案上分开，两种变异形态（分支短路与整函数短路）都被新增测试杀死；N-2 的条数上界饱和在 40、单条截断把 30,000 字符压到 815 字符、`warnings_omitted` 显式报告省略数，且图级提示因插入位置在头部而永不被裁掉——三条都实测成立，去掉条数裁剪必红（与实现者自述一致）。

本轮新增 1 条低危项 **N-3**：N-2 修复中的「单条截断」这一半**没有测试守护**（删掉它 41 条全绿），但**实现本身正确且经我实测确实生效**——属测试覆盖缺口而非行为缺陷，不达「中等以上」，不阻塞。另把极端情况下的 3.5 MB 报告体积归因到 `nodes[].id`（调用方输入自带、`_parse_node` 不校验长度），**不计缺陷**，仅作归因说明以免下一轮误判。

核心不变量 `agent/subagent/scheduler.py` 零改动在本批仍成立；CI 配置、`scripts/**`、`benchmarks/baseline.json` 零改动；未发现回归、与 spec 冲突或安全面变化。**建议（非阻塞）**：合入前顺手把 3b.6 的测试图改成带长 id 的节点，一条改动即可让单条截断也受守护。
