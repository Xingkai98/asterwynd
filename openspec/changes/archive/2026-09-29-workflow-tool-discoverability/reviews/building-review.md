# Building Review: workflow-tool-discoverability（issue #248）

独立零记忆审阅者产出。审阅对象 = OpenSpec change `workflow-tool-discoverability` 的 building 实现。

- 审阅 head: `75d5a1bbcde1b538ba0fe27c5cfe143bf1cc4c3e`
- base: `db79b051e479fd0e261144e683bac91ffba061ef`
- 审阅时间: 2026-09-30
- 复核方式: 读源码 + `uv run pytest` / `openspec validate` / `check_openspec_artifacts.py` / benchmark smoke 实跑 + 对 transcript 机械复算。**不采信任何自称事实**；rollout 不重跑（proposal 指定，贵且 flaky）。

> **工作树状态提示**：审阅期间工作树**领先**审阅 head（`git status` 显示 `acceptance-evidence.md` / `design.md` / `tasks.md` / `spec.md` / `backlog.md` / `test_workflow_tool_discoverability.py` 有未提交改动，属 closeout 提前推进 + evidence 自纠）。本报告的代码/测试结论以**审阅 head `75d5a1b` 的已提交内容**为准，并在相关处标注工作树增量。

---

## Verdict

**PASS（实现本身）／ 验收门槛未达标（交用户决策是否迭代）**（Round 3 更新）

- **Round 1 verdict（historical）**：`CHANGES_REQUESTED` —— 实现主体正确、schema 派生真实、D6(b)/D7 落地无误、测试与 spec 对齐良好，但有一处直接违背本 change 自己声明的 P0 不变式（模型可见面零 `control` token）的残留缺陷（Issue #1），以及 tasks 勾选（#2）与 manifest head 绑定（#3）两处流程项。
- **Round 2 verdict**：`PASS` —— Issue #1 已修复且断言补强到位、无夹带；#2/#3 经确认属**收尾流程项**，不阻塞对本 delta 的 verdict。
- **Round 3 verdict（current）**：**对「实现（代码）」维持 `PASS`；对「本 change 自己的验收门槛」判定为 `未达标`**——收尾期发现两处验收证据问题（run 3 被 run 2 的 `SaveMemory` 记忆 priming、`desc_placeholder` 属域外错误被漏归类），订正后门槛结论由「1/3 达标」降为 **0/3 严格达标**、域外错误由 `4/5` 降为 **`1/4`（未归零）`**。这两处**只影响验收结论，不影响实现代码的正确性/spec 对齐/测试覆盖**（后者在 R1/R2 已独立验证且未被本轮 delta 触碰）。**实现可以合入；但「本 change 是否达到它自己立的主指标门槛」的答案是否定的，须交用户决定是否迭代**（见文末「Round 3」）。

R1 审阅 head = `75d5a1b`；R2 审阅 head = `0114be4`；R3 审阅 head = `bf1760b`（归档后）。详见文末「Round 2」「Round 3」。

---

## 逐条任务验证

### 第 2 节：测试（全部落地，逐条有证据）

| 任务 | 结果 | 证据（`文件:行号`） |
|---|---|---|
| 2.1 T1 schema↔常量 parity | ✅ | `tests/agent/subagent/test_workflow_tool_discoverability.py:85` `test_schema_enum_matches_source_constant` — 对 `DeclareWorkflow`/`RunWorkflow` × 6 字段（`kind`/`mode`/`join`/`strategy`/`channel`/`reducer`）断言 `tuple(enum) == tuple(常量)`，**逐字且顺序敏感**，非 `set`（`:90`）。实跑 32 passed。 |
| 2.1a 变异验证 | ✅ | `test_workflow_tool_discoverability.py:103` `test_schema_enum_is_derived_live` — `monkeypatch.setattr` 改常量后重取 schema，断言 enum 跟随。我把该断言视为**恒常驻的变异验证**（强于一次性手工变异）。工作树另加 `test_tool_schema_matches_freshly_derived_schema`（未提交），闭死「手写与常量当前值相同的字面量」这一 T1+T1a 的联合缺口——方向正确。 |
| 2.2 T2 描述内容断言 | ✅ | `:143` `test_description_has_no_control_token`（原样 + `.lower()` 两条）；`:157` `test_description_covers_cases_semantics`（`startswith`/`prefix`、`first-match`、`GAPS: none`/`GAPS`、`$ref:`）；`:170` `test_description_has_per_kind_field_table`（`join`/`items`/`source`/`strategy`/`max_routes` + 三个 kind）。 |
| 2.2a T2 回归 | ✅ | `:182` `test_description_keeps_the_existing_cycle_contract`（`defaults to 1`/`per route node`/`reset`/`gate->producer`/`body->gate` 全绿）。 |
| 2.3 T3 route `task`（Q1=(b)） | ✅ | `:245` `test_declare_warns_on_route_task`（`DeclareWorkflow` 入口）；`:253` `test_run_workflow_spec_warns_on_route_task`（`RunWorkflow(spec=...)` 入口，C8 半边）；`:259` 负向 `test_no_warning_when_route_has_no_task`；`:232` `_assert_actionable_warning` 断言「哪里错了 + 改到哪里去」。 |
| 2.4 T4 负向按实际 kind 命名 | ✅ | `:272` `test_kind_mismatch_error_names_the_actual_kind` + `:295` 对照（属主 kind 文案不含噪音）。实跑复现见下「正确性」。 |
| 2.5 T5 描述长度守卫 | ✅ | `:197` `test_description_length_within_budget`（≤6000，无下界）。实测运行期 `len == 3993`。 |
| 2.6 集成：描述正例可逐字声明 | ✅ | `:313` `test_description_positive_example_declares`。 |

### 第 3 节：实现（逐条落地）

| 任务 | 结果 | 证据 |
|---|---|---|
| 3.1 `NODE_MODES` 提为模块常量 | ✅ | `agent/subagent/workflow.py:40`；`_parse_node` 改用它（`workflow.py:502` `mode not in NODE_MODES`），**校验行为不变**。 |
| 3.2 错误文案按**实际** kind 命名 | ✅ | `workflow.py:569` `_FIELD_OWNER_KIND`、`:582` `_kind_field_prefix`、`:600` `_parse_strategy` 等全部改签名收 `kind`；调用点传实际 kind（`workflow.py:518-533`）。 |
| 3.3 schema 派生 helper | ✅ | `agent/tools/builtin/subagents.py:516` `_workflow_spec_schema()`（**每次调用重读常量、不缓存**，`subagents.py:521-524` docstring 明写，这是 T1a 能生效的前提）；`:686` `_spec_schema_parameters(*, required)`（R-B 参数化 `required`）。 |
| 3.4 `DeclareWorkflowTool.parameters` 派生 | ✅ | `subagents.py:795` `parameters=_spec_schema_parameters(required=["spec"])`。实跑 `required == ['spec']`。 |
| 3.5 `RunWorkflow` 同步同一 schema | ✅ | `subagents.py:1157` `"spec": _workflow_spec_schema()`。实跑 `required == []`（R-B 满足，`test_run_workflow_template.py::test_schema_drops_required_spec` 未破）。 |
| 3.6 改写 4 处 `control` | ⚠️ **部分** | `DeclareWorkflow.description` 运行期 `control` 命中 **0**（实跑）；但 **schema 侧仍残留一处**——见 Issues #1。 |
| 3.7 门控 vs 渠道正交一段 | ✅ | `subagents.py:740` `"GATING vs CHANNEL (orthogonal — do not conflate them):"`。 |
| 3.8 `cases` 一节（含正反例 + `when` 两形态） | ✅ | `DeclareWorkflowTool.description` 内（含 `GAPS: none` 正例、`$ref:` 说明）。 |
| 3.9 per-kind 字段适用表 | ✅ | 描述「FIELDS BY NODE KIND」段；schema 每个字段级 `description` 亦标注归属 kind（D9 分工）。 |
| 3.10 描述分节化 | ✅ | 顶层形状 → per-kind 表 → edges → 门控/渠道 → `cases` → 环契约（保留） → 正/反例 → 资产提示。 |
| 3.11 描述枚举改指向 schema | ✅ | 描述写「see the schema for legal `channel`/`reducer` values」，不再逐字重复 `REDUCERS`。 |
| 3.12 Q1(a) 分支 | N/A | 用户选 (b)；`patterns.py` **零改动**（`git diff --name-only` 确认 0 命中），与 Impact Analysis 预期一致。 |
| 3.13 Q1(b) warnings（两条入口） | ✅ | 生成点抽为共用 helper `_route_task_warnings`（`subagents.py:700`），两条入口各调一次：`DeclareWorkflow` 的 `declared` 返回体 `:823`；`RunWorkflow` 的 run envelope `:1241`（含 `wait=False` 分支 `:1231`）。**C8 半边已覆盖**。 |
| 3.14 / 3.15 影响面/RIR 回写 | ✅（流程） | proposal 的 Impact Analysis 与 RIR 齐备。 |
| 3.16 文档 | ✅ | `docs/openspec-change-backlog.md` 入队条目在 diff 内；工作树另含 spec sync（未提交）。 |

### 第 5 节：验证

| 任务 | 结果 | 证据 |
|---|---|---|
| 5.1 相关测试 | ✅ | 见 Test Results。 |
| 5.2 全量 pytest | ✅（3 项环境性失败，已证 pre-existing） | 见 Test Results。 |
| 5.3 OpenSpec strict validate | ✅ | 29 passed / 0 failed。 |
| 5.4 artifact checker | ✅ | `OpenSpec artifact checks passed`。 |
| 5.5 baseline CI 本地可过 | ✅（扣除 3 项环境失败） | 同上。 |
| 5.6 benchmark smoke | ⚠️ | exit 0，但 34 failed / 38 unsupported（fake agent 预期，未比对 base 基线）——见 Issues #4。 |
| 5.7 `patterns.py` spec_hash 对照 | N/A | 选 (b)，模板零改动，无需断言。 |
| 5.8 工具数量与名字不变 | ✅ | 实跑名称列表与改动前一致（19 个工具名逐一列出，`DeclareWorkflow`/`RunWorkflow` 在列）。 |
| 5.9 受保护 artifact 结构化事件 | ⏳（closeout） | `workflow-events.jsonl` 现有 2 条 `backlog_updated`（立项期）；`current_spec_synced` 属 6.3 closeout，工作树已改 `openspec/specs/**` 但**尚未落事件**，归档前须补。 |

### 第 6 节：审阅闭环

- 6.1 = 本报告。6.2–6.8 为 closeout/post-merge，归档前处理（注意 6.2 manifest 须在 tasks.md 最终化后生成）。

---

## 正确性

1. **schema 派生是否正确**：✅。`_workflow_spec_schema()` 每次调用从 `workflow_dsl` 读常量（无缓存），实跑得到 6 个 enum 与源码常量逐字相等；`NODE_MODES` 为本次新提常量（`workflow.py:40`），`CreateSubagentTool` 的 `mode` enum 改引用它（`subagents.py:52-53`，Q6 落地）。node 级 `required` **未写**（实跑 `'required' in nodes.items == False`），R-C 满足。`cases[].when` **无 enum**（实跑 schema 为 `{"when": {"type":"string"}, "to": {"type":"string"}}`），R-D 满足——`$ref:` 形态未被堵死。
2. **route task warnings 两条入口**：✅。`DeclareWorkflow`（`subagents.py:823`）与 `RunWorkflow(spec=...)`（`subagents.py:1241`）共用 `_route_task_warnings`（`:700`）。`RunWorkflow` 的 **template 路径**显式返回 `[]`（`:1238-1240` 有注释说明：模板 route 的 `task` 非模型所写，提示不可行动），且**键恒存在**（返回体形状稳定，`test_workflow_asset_context.py` 键集锁已同步更新）。
3. **D7 按实际 kind 命名且未改接受/拒绝**：✅。实跑：
   - `route+strategy="concat"` → `REJECT: route node 'g' strategy (\`strategy\` only applies to aggregate nodes) must be one of ['llm','collect']`（原为 `aggregate node 'g' ...`，文案已按实际 kind）。
   - `aggregate+strategy="concat"` → 仍 `aggregate node 'g' strategy must be one of [...]`（属主 kind 无噪音）。
   - `subagent+cases={obj}` → `subagent node 'g' cases (\`cases\` only applies to route nodes) must be a list`（原硬编码 `route node`）。
   - **接受/拒绝集合未变**：field-owner 映射与 kind 无关地继续无条件调用解析器，只改了文案。

---

## Spec 对齐

delta（`specs/multi-agent-collaboration/spec.md`）逐条：

- **MODIFIED「DeclareWorkflow 描述暴露循环契约」**：4 条循环契约（`spec.md:9-12`）在描述中逐字保留（T2a 绿）；4 条可发现性条款（`cases` 语义 `:18`、`when` 两形态 `:19`、门控/渠道正交 `:20`、per-kind 适用性 `:21`）均有对应描述段与测试。Scenario「描述含 cases 匹配语义」✅、「描述不把门控与 channel 混为一谈」✅、「描述暴露按 kind 的字段适用性」✅。
- **ADDED「Workflow spec schema 的封闭取值从单一来源派生」**（`spec.md:55-81`）：嵌套 schema ✅（`subagents.py:516`）；6 个 enum 从常量派生 ✅；parity 测试 ✅；Scenario「schema 暴露枚举」✅、「枚举与源码常量一致性可机械校验」✅（`test_schema_enum_is_derived_live`）、「两条声明入口的 spec schema 一致」✅（`test_workflow_tool_discoverability.py:110` `test_declare_and_run_share_the_same_spec_schema`）。
- **一处未完全对齐**：Requirement 正文 `spec.md:23`「描述 SHALL NOT 出现**任何非法枚举值**……描述里出现的每个示例 SHALL 是可成功声明的」——`channel` 枚举本身合法、示例已改 `summary`，**此条本身满足**；但 D3 的**设计承诺**「模型可见面不再出现诱导性 token」未被 schema 侧兑现（见 Issues #1）。这是 **design 承诺** 而非 spec 条文的落差。

---

## 冗余度

- 6 个 workflow 域枚举**只在 `agent/subagent/workflow.py` 有一处真相源**（`workflow.py:28,30,31,32,34,35,40`），工具层经 `workflow_dsl.<CONST>` 引用（`subagents.py:529,538,553,561,570,588,611`），无手写第二份。✅
- `CreateSubagentTool.mode` 的手写孪生体已收口（`subagents.py:52-53`）。`agent/run_config.py` 的 `AgentMode`/别名表保留——design D2/C2 明确说明它服务 CLI agent mode（含 `BYPASS`），语义域不同，**有意分域**，不登记债务。判定合理。✅
- 描述不再重复枚举（D9），枚举仅存 schema。✅

---

## 测试覆盖

- T1/T1a/T2/T2a/T3/T4/T5/T6 **全部齐备**，另有负向（`:259`、`:295`）与集成（`:313`）。
- parity 断言为 **`tuple(enum) == tuple(constant)` 逐字 + 顺序敏感**，非 set（`:90`）。✅
- 变异验证可信：`test_schema_enum_is_derived_live` 常驻 CI，等价于「改常量→必红」。工作树补的 `test_tool_schema_matches_freshly_derived_schema` 进一步封死「烘焙值与现算值分叉」。✅
- 覆盖面小的隐忧：T3 的 run 路径测试（`:253`）走真实 `_drive_scheduler` + stub LLM，断言 `status ∈ {completed,failed,blocked}`，语义正确但存在轻微非确定性风险（见 Issues #5）。

---

## 安全性

- 无权限面变更：`DeclareWorkflowTool.read_only` 实跑仍为 `True`；工具权限常量未动。
- `warnings` 为**纯增量**字段，不改变任何工具的成功/失败判定，不构成注入面（文案由服务端模板拼接 `node.id`，非用户原始字符串直插）。
- 无静默失效面：D6(b) 的目标即「消除 route `task` 静默」，已由两条入口的 helper 覆盖；D7 消除误导性错误文案。
- **无新引入风险**：未新增工具、未改调度语义、`parameters` 逐字透传的既有约束被遵守（未引入 `oneOf`/`if-then`）。

---

## 可维护性

- 分工清晰：schema 管域（`subagents.py:516-685`），描述管形（`subagents.py:718+`）。字段级 `description` 标注归属 kind，与描述表互为投影。✅
- 漂移风险受控：enum 派生 + parity 测试 + 描述长度守卫（≤6000，现 3993）。✅
- **一处漂移源未封**：schema 字段级 `description` 是手写文本，其中的 `control` token 无测试覆盖（见 Issues #1）——「描述零命中」的机械保证只覆盖 `.description`，不覆盖 `parameters`。

---

## Test Results（实跑）

| 命令 | 关键输出 |
|---|---|
| `uv run pytest tests/agent/subagent/test_workflow_tool_discoverability.py -q` | **32 passed in 7.10s** |
| `uv run pytest -q`（全量） | **3510 passed, 3 failed, 9 skipped** in 478.89s |
| 3 项失败 | `test_tree_sitter_extracts_java_and_kotlin_symbols`（环境 tree-sitter 数据缺失）、`TestFindScopeRoot::test_returns_none_for_non_git_dir` 与 `test_malformed_git_file_falls_back_to_scan`（本机 `/tmp/.git` 存在，污染 scope-root 探测）。**在 base `db79b05` 的干净 checkout `/tmp/wf-disc-src-pristine` 上复现同样失败** → pre-existing / 环境性，与本 change 无关。 |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | **Totals: 29 passed, 0 failed**（含 `change/workflow-tool-discoverability`）。 |
| `uv run python scripts/check_openspec_artifacts.py` | **OpenSpec artifact checks passed**。 |
| `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-review` | exit 0；`Tasks: 72 / passed: 0 / warnings: 0 / unsupported: 38 / failed: 34`（fake agent 预期不真解题；**未比对 base 基线**，见 Issues #4）。 |
| 运行期核对 | `DeclareWorkflowTool.description` `control` 命中 **0**（原样与 `.lower()` 均 0）；描述长 **3993**；`parameters` JSON 长 4173；`DeclareWorkflow.parameters.required == ['spec']`、`RunWorkflow.parameters.required == []`。 |
| D7 行为核对 | 见「正确性」节 4 组实测。 |
| 工具名核对 | `DeclareWorkflow`/`RunWorkflow` 等 19 个工具名不变。 |

---

## Issues（按严重度分级）

### 【中高】#1 — 模型可见面仍有 `control` token：schema 字段描述未随 D3 一并清理

- **证据**：`agent/tools/builtin/subagents.py:634`，edge `required` 字段的 schema 描述里写着 `"outgoing edges, which are control edges."`。该 schema 经 `_spec_schema_parameters`（`:695`）成为 `DeclareWorkflow`/`RunWorkflow` 的 `parameters`，按 design 事实 1 **每次 API 调用原样发给模型**。
- **为何是缺陷**：D3 明文承诺「本 change 只保证**模型可见面**不再出现诱导性 token」，并据此把**同样是正确术语**的描述 `:518`（原 `- A route's OUTGOING edges are control edges: ...`）也一并改写成不出现该 token。`:634` 是同一层、同一用法，却被漏掉——**内部不自洽**。design R-A 的原始顾虑（「模型在 edge 附近看到 `control` 就可能填进 `channel`」）对 `:634` 同样成立。
- **测试为何没兜住**：T2 零命中断言（`tests/.../test_workflow_tool_discoverability.py:143`）只对 `DeclareWorkflowTool.description` 取值，**不覆盖 `parameters` 树**。因此「零命中」这条机械保证在其宣称的模型可见面上是**不完整**的。
- **修法（低成本）**：把 `:634` 改为不含该 token 的等价表述（如 `"Data-edge gating (default true). Meaningless on a route's outgoing edges, which never gate."`），并把 T2 的零命中断言扩到整个 `parameters` 树（或至少 edge/node 字段级 description）。**注意**：可观测层的 `scheduler.py` 快照 `kind: "control"` 不受影响（它不在模型可见面）。

### 【中】#2 — `tasks.md` 勾选未更新，归档点完成度门禁会红

- **证据**：`openspec/changes/workflow-tool-discoverability/tasks.md` 中第 2/3/4/5/6 节绝大多数任务仍为 `- [ ]`，而实现、测试、证据均已落地。
- **影响**：AGENTS.md 的完成度门禁在归档点检查未勾任务（除 `(post-merge)`）；未勾且无标记的行 SHALL 报错。收尾前须据实勾选（第 4 节端到端验收属「已执行」而非「已达标」，勾选时须与 evidence 的「未严格达标」结论一致，避免把「判定完成」误读为「门槛通过」；6.7/6.8 已标 `(post-merge)`，正确）。

### 【中】#3 — 审阅 head 与工作树不一致

- **证据**：`git rev-parse HEAD == 75d5a1b`，但 `git status` 显示 6 个文件有未提交改动（含 `openspec/specs/**` spec sync、backlog、design、tasks、acceptance-evidence、test 文件新增 1 条测试）。
- **影响**：本报告的代码核验对象是 `75d5a1b`；closeout 改动尚未进入任何 commit。6.2 的 review manifest 必须绑定**最终** head/任务 hash——请在 tasks.md 最终化与所有 closeout 改动落盘后再生成 manifest，避免 manifest 与审阅对象错位。

### 【低】#4 — benchmark smoke 34 failed / 38 unsupported，未比对 base

- **证据**：`uv run asterwynd benchmark ... --agent fake` → `passed: 0 / unsupported: 38 / failed: 34`，exit 0。
- **说明**：`--agent fake` 本就不真解题，大量 failed/unsupported 属预期；smoke 的价值在「管线不炸」（exit 0 满足）。但本报告**未**在 base 上跑同一 smoke 做对照，故「34 failed 是否与本 change 无关」未机械证实（低风险：本 change 不触 benchmark runner）。

### 【低】#5 — T3 run 路径测试的轻微非确定性

- **证据**：`tests/.../test_workflow_tool_discoverability.py:253` `test_run_workflow_spec_warns_on_route_task` 走真实 `_drive_scheduler` + stub LLM，断言 `status ∈ {completed,failed,blocked}`。
- **说明**：断言口径宽、设计上容忍多态，实跑稳定通过；仅提示这类集成断言比纯单元断言更易受调度时序影响。

### 【低·未验证项】memory quarantine 在改后轮次是否严格生效

- after transcript 中存在 `SearchMemory`/`RecallMemory` 调用（各 1 次）。evidence 声称已把污染记忆 quarantine 到 `/tmp/wf-disc-memory-quarantine/`，但**未在本次审阅中独立核验 quarantine 后的检索结果为空**。低风险（不影响「域不可见类归零」这一核心结论），但如实列为未验证项。

> **未验证项（低风险，因权限轮询成本而略过）**：base 上 benchmark smoke 对照；after 轮次的 memory 检索实际返回内容。

---

## 验收证据可信度核验（**本 change 特有 · 必查**）

**结论：修正后证据数字可信、无夸大、无残余 cherry-pick 掩盖；分类判定成立。** 明细如下。

### 1. 数字真实性（我独立复算，不采信文字）

口径：声明**尝试** = `DeclareWorkflow` 调用数 + **带 `spec` 的** `RunWorkflow` 调用数；`invalid_spec` 按工具返回体 `"status": "invalid_spec"` 计数（整行匹配，规避同一结果多行噪音）。

| 组 | 我的独立复算 | evidence 现版 | 一致 |
|---|---|---|---|
| 基线（`baseline-transcript-2026-09-29.log`，session `1045cbb69fa4`） | 尝试 **18**（Declare 18 + Run 0）/ `invalid_spec` **5** / 探针 **9** | 18 / 5 / 9 | ✅ |
| 改后 run1（session `919347fa361f`） | 尝试 **10**（Declare 4 + Run 6）/ `invalid_spec` **1** / 探针 **6** | 10 / 1 / 6 | ✅ |
| 改后 run2（session `55062659925c`） | 尝试 **14**（Declare 7 + Run 7）/ `invalid_spec` **1** / 探针 **7** | 14 / 1 / 7 | ✅ |
| 改后 run3（session `a57094603ad8`） | 尝试 **2**（Declare 2 + Run 0）/ `invalid_spec` **0** / 探针 **0** | 2 / 0 / 0 | ✅ |

- 早前 evidence 的 `S1 = 2/2/0` 与 `S0 run1=5` 二处**已被我更正期前发现、实现方已独立确认并修正**为 `1/1/0` 与 `6/7/0`；现版表格、门槛段、质性段三处口径已同步一致。
- **run1 探针 = 6 而非 5，成立**：第 6 条 goal 为双引号 `"probe: on route re-evaluation, does it see the aggregate's LATEST output or accumulated stale one?"`——只匹配单引号的旧正则会漏掉它。我以「单引号 or 双引号」两种引号各自扫描，确认该条存在且被判为探针。
- **run2 中文探针 = 7，成立**：逐条为 `路由前缀匹配语义探针` 与 6 条 `探针：…`。原纯英文分类器确实会给 0，中英双语分类器修正必要且正确。
- **S0 分类器**：现版为双语（含 `探针`），我按该正则独立跑，得基线 9 / 改后 6/7/0，与其一致。

### 2. 分类判定（基线 4/5「域不可见」是否成立）

我逐条抽取基线 5 次 `invalid_spec` 的 `reason`：`edge 'dispatch'->'w1' channel must be one of [...]`（自造 `channel` 值）、`unknown edge field(s): ['label']`、`unknown node field(s): ['routes']`、`unknown node field(s): ['task_note_unused']`、`route node 'gate' cases must be a list`。**前 4 条确为「域不可见」类**（自造枚举值 / 自造字段名），**第 5 条确为 shape 类**（`cases` 写成对象而非数组）。evidence 的「4/5 域不可见 + 第 5 条 shape」分类**成立**。
改后 2 次 `invalid_spec` 的 `reason` 均为 `node 'a'/'agg' slot 'result' is written by multiple upstreams [...] declare no reducer`——确属「规则已写明、模型没照做」，非「域不可见」。**改后域不可见类 = 0** 成立。

### 3. harness 是否被改动 / baseline 是否跑在未改代码上

- 提示词一字未改（evidence 顶部与两次 rollout 一致）；模型 `deepseek-v4-flash`、`--mode bypass`、`cwd=/tmp` 两组一致。
- baseline 头部 transcript 显示 `ListWorkflowAssets -> {"assets": [], "total": 0}`（资产库已清空，污染已消除）；workspace 为 `/tmp/wf-disc-baseline2`，与源码 worktree 分离。
- evidence 声称 baseline 跑在 `git worktree add --detach db79b05` 的干净 checkout（`/tmp/wf-disc-src-pristine`）——**该目录实际存在且 HEAD 确为 `db79b05`**（我实跑 `git rev-parse` 确认），与基线的「改前」定位一致。✅

### 4. 结论是否 cherry-pick

**未见掩盖。** evidence **主动披露**三类不利事实：(a) 严格门槛 **仅 1/3 达标**（run1/run2 探针未归零）；(b) token **未下降**（均值持平略升）；(c) `graph_recursion_exceeded` 改后**反而偏高**（均值 14 vs 10）。并给出**诚实定性**：S0 未归零主要来自「运行期语义」第二类探针（**不在本 change 范围**），而非本 change 针对的「声明期域」。将严格门槛的未达标 + 成因重构同时写出，属**如实呈现**而非掩盖。

**唯一需读者警惕的表述**：把 headline 从「S0=0」转移到「按成因分类」是一种**叙事软化**——严格门槛确实未过 2/3。但 evidence 已把严格数字原样保留在「通过门槛判定」节，未删改，故**不构成 cherry-pick**；判断 change 是否成功应以「域不可见类归零 + run3 零探针」为准（这有独立证据支撑）。

### 5. 隔离措施是否可信

quarantine 污染记忆、`cwd=/tmp`、独立 checkout 三项均有对应痕迹（baseline 起始资产库为空、`/tmp/wf-disc-src-pristine` 存在且 HEAD=db79b05）。**唯一未独立核验项**：after 轮次 `SearchMemory` 返回内容是否确为空（见 Issues 低风险项）。

---

## 需用户决策

无阻塞性决策项。Issues #1 为**建议必修**（低成本、直接关系本 change 的核心不变式）；#2/#3 为收尾流程项，可按 AGENTS.md 既定步骤处理。

---

## 附：审阅未覆盖

- 未重跑真实 LLM rollout（proposal 指定，reviewer 不跑）。
- 未在 base 上跑 benchmark smoke 对照（低风险，见 Issues #4）。
- 未独立验证 after 轮次 memory 检索返回内容（低风险，见「未验证项」）。

---

# Round 2（复审）

- 复审对象 head: `0114be47d89833eec69759f74d4ec457be451d9c`
- 上一轮 head: `75d5a1bbcde1b538ba0fe27c5cfe143bf1cc4c3e`
- delta: `git diff 75d5a1b 0114be4`（单 commit `0114be4`）
- 复审范围：聚焦 delta（不重跑全量 pytest，依实现方与 R1 的既有实跑）。

## Round 2 Verdict

**PASS** —— R1 的两条实现类 issue（#1 control token、T2 断言范围）均已修复且经独立复核；无夹带；#2/#3 确属收尾流程项，不阻塞本 delta。

## Delta 范围核对（是否恰好只动声明项 + 无夹带）

`git diff --name-only 75d5a1b 0114be4` 恰为 5 个文件，**全部与声明一致，无夹带**：

| 文件 | 声明改动 | 判定 |
|---|---|---|
| `agent/tools/builtin/subagents.py` | 1 行（edge `required` schema 描述） | ✅ 见下 |
| `tests/agent/subagent/test_workflow_tool_discoverability.py` | +31 行（2 条新测试） | ✅ 见下 |
| `openspec/changes/.../design.md` | T2 口径 + T10 OQ4 回写（issue #268） | ✅ 属声明范围 |
| `openspec/changes/.../reviews/acceptance-evidence.md` | R1 期间的自纠（S0/S1 口径修正） | ✅ 已在 R1 复核 |
| `openspec/changes/.../reviews/building-review.md` | R1 报告本身 | ✅ 属落盘 |

- `git diff 75d5a1b 0114be4` 中 **`spec.md` / `tasks.md` / `backlog.md` 均未出现**（那三者仍是工作树未提交的收尾改动，不在本 commit）。✅
- 本 commit **未触** `workflow.py`、`scheduler.py`、`patterns.py`、任何调度语义路径。✅

## Issue #1 复核（control token）

- **修复正确**：`agent/tools/builtin/subagents.py:634` 由 `"...which are control edges."` 改为 `"...which never gate."`。删掉了诱导 token，且新表述保留了「route 出边不 gate」的原意（与描述里同段语义一致，非机械删词）。
- **全文件零命中**：`grep -c "control" agent/tools/builtin/subagents.py == 0`（独立实跑）。剩余 19 处 case-insensitive 命中全为 `SUBAGENT_CONTROL_PERMISSION`（**Python 标识符**，不进入任何模型可见字符串）——非风险。✅
- **模型可见面全量扫描**：我额外全仓扫了 `agent/tools/` 下所有工具描述/schema，唯一残留的 `control` 出现在 `agent/tools/sandbox/{docker_backend,process_backend,cgroup}.py`——均为沙箱**实现代码**（非 `description`/`parameters` 文本），不进入模型可见面。**无其他工具 schema 残留诱导性 token**。✅

## Issue #1 断言补强复核（模型可见面覆盖度）

- **新断言**：`tests/.../test_workflow_tool_discoverability.py:155` `test_model_visible_surface_has_no_control_token`，参数化 `_TOOLS = [DeclareWorkflowTool, RunWorkflowTool]`（**两条入口都覆盖**），对 `tool.description` 与 `json.dumps(tool.parameters, ensure_ascii=False)` **两者**各断言 `"control" not in x` **且** `"control" not in x.lower()`（R-A 的「两处自伤面」口径保留）。
- **覆盖面判定**：`json.dumps(parameters)` 序列化的是**整棵 schema 树**（顶层 + `spec` + `nodes.items` + `edges.items` + `cases.items` 的每一层 `description`），故 R1 漏掉的 edge `required` 字段描述这类嵌套措辞**今后会被捕获**。这是对「模型每次调用可见的全部 surface」的正确覆盖——因为模型拿到的恰恰是 `description` + 逐字透传的 `parameters`（`agent/tools/base.py:53-61` → `anthropic_llm.py:746-753`），别无可注入的模型可见文本位。✅
- **变异验证可信**：实现方实测「注回 token → 2 failed, 34 passed → 还原 36 passed」。我独立复跑该文件得 **36 passed**，与「还原后」一致。✅
- **补充肯定**：同 commit 另含 `test_tool_schema_matches_freshly_derived_schema`（`:126`），把烘焙 `parameters` 与测试期现算的派生结果逐字比对——封死「手写字面量恰与常量同值」这一 T1+T1a 的联合缺口。方向正确，属加强而非引入风险。

## Issue #2 / #3 定性确认

- **#2（tasks 勾选）**：属**收尾流程项**。`tasks.md` 未勾是「记账滞后」，非实现缺陷；且工作树已在改动它（未提交），归档前最终化即可。**不阻塞**本 delta。
- **#3（manifest head 绑定）**：属**收尾流程项**。AGENTS.md 要求 manifest 在该 change 的 `tasks.md` 最终化（含归档 move）**之后**生成——即 manifest 本就应绑定一个**晚于** `0114be4` 的 head。故它与「本 delta 是否可信」无关。**不阻塞**本 delta。
- 两条均已在 R1 报告中建议按既定步骤处理，实现方确认照此执行，判定一致。

## Round 2 残留（非阻塞）

| 级别 | 项 | 说明 |
|---|---|---|
| 低 | benchmark smoke 未在 base 对照（R1 #4） | 未变；本 delta 不触 benchmark runner。 |
| 低 | after 轮次 memory 检索返回内容未独立核验（R1 未验证项） | 未变；本 delta 不触 memory 路径。 |
| 流程 | 8 个模型可见文案里的中文标点 `\`task\`` 等 | 非 token 类，D3 只约束 `control`，无影响。 |

**Round 2 结论：无阻塞项，`PASS`。** 收尾时按 AGENTS.md 完成 tasks 勾选、spec sync 落事件、manifest 在 tasks 最终化后生成即可。

---

# Round 3（收尾期验收证据订正复核）

- 复审 head: `bf1760bd0bece10edc5f4ed3cb3e8aa2697dcce2`（change 已归档到 `openspec/changes/archive/2026-09-29-workflow-tool-discoverability/`；本报告随归档移动）
- 触发：收尾期自查出「run 3 被 run 2 的 `SaveMemory` 记忆 priming」+「`desc_placeholder` 域外错误被漏归类」，两处均**改变门槛结论**。
- 复审范围：只核验收证据订正；不重跑 pytest/rollout（依 R1/R2 既有实跑 + 本轮 transcript 复算）。

## Round 3 Verdict

**对「实现（代码）」：维持 `PASS`。对「验收门槛」：`未达标`（0/3 严格口径），须交用户决策。**

判决理由：本轮两处订正**改变的是验收证据的可信度与结论，不是实现代码**。实现代码的正确性（schema 派生 / D6(b) 两条入口 / D7 文案不变行为）、spec 对齐、测试覆盖、T1–T6 齐备，在 R1/R2 已逐条独立验证；`bf1760b` 与 R2 审阅 head `0114be4` 之间**代码零改动**（归档 move + evidence/报告订正 + manifest）。因此「实现 PASS」不受影响。但本 change **自己立的主指标门槛（S0=0）确实未达**，且这一事实此前被两处证据问题部分掩盖——这是**必须交给用户**的决策点（是否迭代 / 放宽门槛口径 / 接受现状合入）。

## 订正 1 复核：run 3 的 memory priming（污染机制是否成立）

**结论：机制论证成立，我独立复核了每一环。**

1. **`SaveMemory` 确实在 run 2 末尾发生**：`after-transcript-2026-09-29.log:1063`，`00:38:55,508` 执行 `SaveMemory({'type':'project','name':'asterwynd-workflow-engine-gotchas', ...})`，`importance:4`；`:1064` `00:38:55,634` 返回 `saved`。该记忆的 `body` 逐条含「route 回边只传控制、不传数据」「`max_routes` 用尽 → blocked」等**正是 run 3 探针要回答的问题**。
2. **run 3 在 55 秒后启动**：`:1230` `Session ID: a57094603ad8`，`:1234` `00:39:51,855 [Iteration 0]`（首 iteration 即 2 条消息，含系统提示 = 新 session）。**时间差 ≈ 56 秒**，与 evidence 所述一致。
3. **注入通道存在且确实每 session 生效**：`agent/context/sources.py:278-307` 的 `MemoryIndexSource.render()` 读 `persistent_memory.load_summary()` 并把摘要拼进 `## Project Memory`，且该源 `static = False`（注释明写「每轮重渲染（非 static）」）→ **每个新 session 起始上下文都会带 active 记忆摘要**。故 run 3 的 S0=0 **不可信**这一判断成立。
4. **改后 run 1 / run 2 不受此路径污染**：run 1 起始该 scope 记忆已在基线节被 quarantine；run 2 起始时 run 1 未写记忆（run 1 transcript 中 `SaveMemory` 计数为 0）。✅
5. **干净重跑 run 3b**：`reviews/after3b-transcript-2026-09-30.log`（session `e1e3cf133945`，单 session，`SearchMemory=0` / `SaveMemory=0` 实跑计数）→ 起始无记忆注入痕迹，替代可信。

> **残余注意（非阻塞）**：run 3b 本身在**其执行期间**（00:46 前后，见 `after-transcript` 中原 run 3 的 `SaveMemory` 是另一条）——不影响 3b 起始上下文；3b 自己的 `SaveMemory=0` 已确认无自污染。

## 订正 2 复核：run 3b 的 S0 与 `desc_placeholder` 归类

**S0 = 4：我独立复算为 3，与 evidence 的 4 有 ±1 差。** 用 evidence 声明的**同一双语分类器**逐条跑 run 3b 的 `goal`，命中 3 条（`探针：route 出边/非必需数据边…`、`探针：上游内容在 task 里的占位符写法`、`探针：bus channel…`）；`诊断 foreach item 的模板注入约定` **未被分类器命中**（它不含 `probe`/`探针`，也不以 `test/verify/check/validation` 开头），但 evidence 把它计入探针（=第 4 条）。

- 该条**语义上确属探针**（「诊断…约定」= 只为验证语义、无业务目标），故 evidence 的「4」在**语义口径**下成立；但**用其声明的机械分类器算不出 4，只能算出 3**。这是一处**分类器与人工判定不一致**的口径瑕疵（与 R1 抓到的同类问题同源）。
- **对结论方向无影响**：无论 3 还是 4，均 > 0 ⇒ 门槛仍 `0/3 严格达标`。**故不改判**，但登记为低危口径项（见下）。

**`desc_placeholder` 归类：同意。** `after3b-transcript-2026-09-30.log` 中该次 `DeclareWorkflow` 返回 `unknown node field(s): ['desc_placeholder']` —— 属 `unknown node field` 形态，与基线的 `unknown node field(s): ['routes']` / `['task_note_unused']` **同类**（模型自造字段名以求「运行时模板占位符」能力）。归为**域外错误**成立。evidence 把「改后域不可见类 = 0」订正为 **`1/4`（未归零）**、并由「探针口径」单独声明，是**正确的收紧**。

**我独立抽取的全部 `invalid_spec` reason（可复核）**：

| 组 | 次数 | reason | 归类 |
|---|---|---|---|
| 基线 | 5 | `channel must be one of [...]`、`unknown edge field ['label']`、`unknown node field ['routes']`、`unknown node field ['task_note_unused']`、`route node 'gate' cases must be a list` | 域外 ×4 + shape ×1 |
| 改后 run1 | 1 | `slot 'result' is written by multiple upstreams [...] declare no reducer` | 规则未照做 |
| 改后 run2 | 1 | 同上（`agg`） | 规则未照做 |
| 改后 run3b | 2 | `unknown node field ['desc_placeholder']`、`slot 'result' ... no reducer` | **域外 ×1** + 规则未照做 ×1 |

⇒ 改后域外错误 = **1/4**（不是 0），evidence 订正后的表述与 transcript 逐字对得上。**未发现第三处被漏归类的 `invalid_spec`**。探针 17 条逐条看也确为「运行期语义」类（foreach 注入、route/边读谁的文本、bus channel、占位符写法），无「域不可见」类——探针口径的表述成立。

## 对实现本身的 PASS 是否维持（明确回答）

**维持 `PASS`。** 论据：

- 本轮两处订正**全部落在 `reviews/acceptance-evidence.md` 与 rollout transcript 层**，**不触任何实现代码**。`git diff 0114be4 bf1760b` 的实现侧为零（详见下方范围核对）。
- 实现正确性在 R1/R2 已独立验证且本轮无新反证：schema 派生真实（`_workflow_spec_schema` 读时取常量）、D6(b) 两条入口产可行动 warning、D7 只改文案未改接受/拒绝、T1–T6 齐备、spec delta 逐条对齐、`control` 模型可见面零命中。
- 「实现好不好」与「change 效果是否达标」是两个问题：前者 PASS，后者 **0/3 未达标**。二者不矛盾——一个正确实现了一个**方向对但收益不完全**的 change，正是本 change 的真实形态（域外错误 4/5→1/4、探针 9→5.67，改善真实但未归零）。

## 需用户决策（**阻塞项**）

> 这是本 change 真正的待决点，主 session 须停轮交用户。

**决策：本 change 是否达到可合入的验收标准？** 客观事实：

- 主指标门槛（S0=0）**未达标**：改后严格 **0/3**（S0 = 6/7/4），非此前误报的 1/3。
- 但 change 针对的错误类**确有实质改善**：`invalid_spec` 中的域外错误 `4/5 → 1/4`；探针数 9 → 5.67；剩余探针 **100% 属本 change 不覆盖的「运行期语义」层**（foreach 注入 / route 读谁的文本 / bus channel）。
- proposal 早已明写「这不是客观硬指标……由主 session 主观判断」且「不设 token 阈值」。

**可选处置**（供用户拍板）：
- **(A) 接受现状合入**：认定「消除一整类无效动作（域不可见类）」这一收益落地，剩余探针属另开 issue 的范畴（#208 / 运行期语义文档）。
- **(B) 迭代**：另开 change 补「运行期语义」可发现性（本 change Non-Goals 已明确排除，属范围扩张，需新立项）。
- **(C) 放宽/重定义门槛**：不推荐——proposal 的门槛是用户当初拍板的口径，事后放宽会让验收失去意义。

**我的建议**：**(A)**。实现正确、spec 对齐、域外错误显著下降且剩余探针与工具契约根因无关；把「运行期语义」作为独立 issue 跟进更符合范围纪律。但**这是用户的判断，不是 reviewer 的**。

## Round 3 残留（非阻塞）

| 级别 | 项 | 说明 |
|---|---|---|
| 中 | 验收门槛未达标交用户决策 | 见上「需用户决策」，**这是阻塞合入判断的项**。 |
| 低 | S0 分类器与人工判定不一致（run 3b 的 `诊断 foreach…` 条） | 机械分类器算 3、evidence 算 4；方向不变。建议 evidence 明确「含 1 条人工判定」，消除口径歧义。 |
| 低 | benchmark smoke 未在 base 对照（R1 #4） | 未变；本 delta 不触 benchmark runner。 |
| 低 | run 3b 起始 memory 状态未独立读盘核验 | evidence 声称「0 条 active 记忆」；我用 `SearchMemory=0/SaveMemory=0` 佐证，但未直读 `~/.asterwynd/projects/<hash>/memory/` 与 `MEMORY.md`。低风险。 |
