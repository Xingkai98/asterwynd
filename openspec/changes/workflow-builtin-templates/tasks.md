# Tasks: 内置模板归一（RunPattern 融合进 Workflow DSL 入口）

> 实现前须完成 grill（`reviews/grill-design.md`）与停轮确认。测试先行（TDD）：每条实现任务先落回归/新测试再落代码。

## 0. 实现前设计追问（batch-grill-me）——已解除阻塞

> **阻塞已解除（2026-09-29）**：两轮独立 grill 完成，Q1–Q6 全部拍板并记录于 `reviews/grill-design.md` 的 `## User Confirmation` 与 `design.md` 的 `## Open Questions（全部 ✅ 已确认）`。grill-confirmation-gate 已满足，实现可开工。

- [x] 0.1 用独立零记忆 subagent 执行 `batch-grill-me`（等价设计追问），逐项审视 design.md 的 D1–D6，产出结构化决策记录到 `reviews/grill-design.md`（第一轮 11 决策 + 4 OQ；第二轮 12 决策 + 新增 Q5）
- [x] 0.2 停轮把 `## Open Questions`（Q1 per-worker ref 通道 / Q2 completed 口径 / Q3 params 按模板封闭 / Q4 wait=false 回执 / Q5 params 值级校验 / **Q6 workers 上界归位**）逐条配具体例子交用户确认，答复记录进 `grill-design.md` 的 `## User Confirmation`
- [x] 0.3 按 Q1 答复回写 design D2 与 tasks 4.6/5.6；按 Q3/Q5/Q6 答复回写 design D3、Non-Goals 与 spec delta

## 1. 共享配方编译路径（D3 / D4）

- [ ] 1.1 在 `agent/subagent/patterns.py` 落共享 helper `_compile_recipe(pattern, task, params) -> WorkflowSpec`（实现期定名）：内部即 `compile_pattern`，统一「未知模板名 → 结构化拒绝」的措辞；被统一入口与资产路径共用
- [ ] 1.2 在 `agent/subagent/patterns.py` 落 **per-template** `params` 校验（R2 订正：不是全局并集）——按模型各自的封闭键子集（orchestrator-worker: `workers`/`worker_max_*`；hierarchical: `teams`/`worker_max_*`；bidding: `proposers`/`worker_max_*`；peer-review: `max_rounds`/`worker_max_*`），不属该模板的键结构化拒绝并在 `reason` 列出该模板可用键
- [ ] 1.2a 落 **值级校验**（Q5）：计数键要求可安全 `int()` 且为正整数、`worker_max_*` 要求数值；非整数/null/不可转数 → `invalid_input` 结构化拒绝（今天抛未捕获 `ValueError`/`TypeError` → 模型见裸 `[Error: …]`）。**clamp 保留**（`0/-5 → 下界`是既有语义）
- [ ] 1.2b 落 **上界归位**（Q6）：计数键（`workers`/`teams`/`proposers`）**> 既有 `max_items`（默认 20）→ `invalid_input` 拒绝**，`reason` 写明该上限来自既有 `max_items` 闸。**不新增任何上界**——三闸（`max_items`/`max_nodes`/`max_runs`）仍是唯一权威边界；本校验只把今天的**静默截断**（实测 `workers=50` 只跑 20）变为显式拒绝。**`max_items` 本身不改**
- [ ] 1.3 单测：helper 对 `{"workers": 3}` 的产出与 `compile_pattern("orchestrator-worker", task=…, params={"workers": 3})` 的 `spec_hash` 相等；未知键 / 跨模板键（`peer-review + workers:7`）/ 非整数值（`workers:"abc"`）/ `null` / 超上界（`workers:50`）各一条结构化拒绝；`workers:0` 仍 clamp 为 1（不报错）
- [ ] 1.4 回归：确认 `workers`≤20 的既有调用方（测试实测最大用 3）与 benchmark `template` 臂（不传 params）不受新校验影响

## 2. 统一 Workflow 入口的 template 输入（D1）

- [ ] 2.1 测试先行：`RunWorkflow` 的四条非法组合各一条（同时给 spec+template / 都不给 / template 缺 task / 未知模板名）+ spec 路径带 params 或 task 拒绝
- [ ] 2.2 扩展 `RunWorkflowTool`（`agent/tools/builtin/subagents.py`）的 `tool_parameters`：新增 `template`/`task`/`params`，并**摘掉 `"required": ["spec"]`**（R2 实测：否则 `RunWorkflow(template=…)` 在模型侧被判缺参）
- [ ] 2.2a **工具描述文案（Q2/Q4 拍板要求）**：`RunWorkflow` 描述里写明 ①「exactly one of `spec`/`template`」；②「`completed`/`failed` 数的是 **run**，不是 subagent」；③「`wait=false` 返回**启动回执**（`status:"running"`）而非结果，结果经 `GetWorkflow` 轮询取」。**检查其余模型可见出口**（`GetWorkflow`/`DeclareWorkflow`/`SaveWorkflowAsset` 描述）是否也需要同款口径说明，避免遗漏
- [ ] 2.3 实现入参判别：exactly-one-of 校验 + 五条结构化拒绝（沿用 `_invalid_spec` 风格的 `invalid_input`）
- [ ] 2.4 template 分支调 1.1 的 helper 编译出 spec，与 spec 分支汇合到同一条 `parse_spec_for_manager` → scheduler 路径
- [ ] 2.5 单测：`RunWorkflow(template=…)` 编译出的 spec 与 `compile_pattern(…)` 逐字一致；`template` 与 `spec` 两路径返回体键集相等

## 3. 编码来源溯源迁移（D4，保 #245 能力不静默退化）

- [ ] 3.1 测试先行：`RunWorkflow(template=…)` 跑完后 `SaveWorkflowAsset` 存出的是 `source="pattern"` 的 recipe 资产；`RunWorkflow(spec=…)` 存出的是 `source="dsl"` 资产
- [ ] 3.2 把 `scheduler.asset_source` 的写入点从 `run_pattern` 迁到 `RunWorkflowTool` 的 template 分支（`{"kind": "pattern", "pattern": template, "params": params, "task": task}`）；spec 分支不写，保持默认 `{"kind": "dsl"}`
- [ ] 3.3 单测：用不同 `params` 跑同一模板资产，展开项数随参数变化（参数化保留的回归）

## 4. 出口收敛：单一 bounded 投影（D2 / D6）

- [ ] 4.1 测试先行：两条路径的返回体键集相等，且均不含 `pattern`/`workers`/`selected`/`selector`/`bus`
- [ ] 4.2 测试先行：投影 `nodes[]` 每节点文本 ≤ `_PARENT_FIELD_LIMIT`；`nodes_total`/`nodes_omitted` 正确；`bus` 不在投影内
- [ ] 4.3 测试先行：`wait=false` 回执 `status == "running"`，与终态 status 集合不相交
- [ ] 4.4 template 分支与 spec 分支统一返回 `scheduler.parent_envelope()`（`wait=true`）；`wait=false` 保持既有回执形状，工具描述硬写「回执非结果」
- [ ] 4.5 确认 `agent/subagent/scheduler.py` 的 `_envelope`/`parent_envelope` **逐字不动**；回归 `test_bounded_envelope.py` 的键集与界断言
- [ ] 4.6 **补 foreach per-worker ref 通道**（依赖 Q1 拍板）：`GetWorkflow(detail='nodes')` 对 `kind=="foreach"` 节点读 `state.item_runs` 吐 `item_refs: [{index, subagent_id, run_id, result_ref?}]`（**R2 三条硬约束**：①`result_ref` 仅成功项出现，失败/取消/超限项无 ref 只给 bounded `reason`；②跳过未派发空槽；③附 `items_total`/`item_refs_omitted` 固定界，禁止线性无界）

## 5. 删除面与引用清理（D5）

- [ ] 5.1 删除 `RunPatternTool`（`agent/tools/builtin/subagents.py`）与 `agent/loop.py` 的注册
- [ ] 5.2 删除 `run_pattern` / `_legacy_result` / `_workers_from_node` / `_worker_entry` / `_AGGREGATE_NODE_IDS`（`agent/subagent/patterns.py`）；改写模块 docstring 中描述 `run_pattern` 返回形状的段落
- [ ] 5.3 `manager.py` 的 `SPAWN_TOOL_NAMES` 去掉 `"RunPattern"`
- [ ] 5.4 订正 `agent/subagent/bus.py` 的 `snapshot_payload()` docstring 中「模型面调用点是 RunPattern」的措辞（界本身不落笔）
- [ ] 5.5 改写受影响测试：`test_patterns.py` / `test_pattern_templates.py` 5.2 段 / `test_bounded_envelope.py` / `test_guardrails.py` / `test_concurrency_queue.py`
- [ ] 5.5b **`test_bus_bounded_exports.py` 整体处理**（R2 精度订正）：该文件有**两个** `RunPattern` 相关测试（`:187` 出口 2 经 `run_pattern`、`:207` 经 `RunPatternTool`）+ **模块级 tool import**（`:34`）——必须整体处理（含删 `:34` 的 import），否则收集期 ImportError；出口 2 的 bounded 语义须迁移到仍存的 bus 出口（`ReadBus`）上钉住
- [ ] 5.5a **#245 回归测试迁移**（实测确认这三个文件用 `RunPatternTool` 产出 pattern 图）：`test_workflow_asset_tools.py:121`、`test_workflow_asset_context.py:165` 改用 `RunWorkflow(template=…)` 产出 pattern 图；`test_workflow_asset_context.py:195` 的 `test_run_pattern_result_keyset_is_locked`（键集锁）随 `run_pattern` 退役删除，其「加字段必须是有意识的」语义改挂到统一入口返回体的键集锁上
- [ ] 5.6 **出口 4 语义迁移**（**依赖 Open Question Q1 拍板**）：把 `test_workflow_node_transcript.py:894-932` 的「worker 条目 bounded + `result_ref` 补偿」断言改挂到新出口，**不删断言语义**（issue #213 回归保护）。**注意**：grill 实测 `GetWorkflow(detail='nodes')` 的 `_node_refs()` 对 foreach 节点返回空（身份在 `item_runs`），故若 Q1 = 不补通道，本任务必须显式缩水并记录损失，**禁止**静默降级成「只断言 `root_result_ref`」；若 Q1 = 补通道，则先落 `item_refs` 投影再迁移断言
- [ ] 5.6a 处理 `test_workflow_node_transcript.py:942-946`（`test_worker_entry_without_workflow_identity_does_not_lie`）**直接 import `_worker_entry`** 的测试——删 `_worker_entry` 会让该文件收集期 ImportError，须一并删除或改写
- [ ] 5.7 深度闸测试：深度到限子 agent 工具集不含 `RunWorkflow` 与 `RunPattern`
- [ ] 5.8 删净检查：`rg 'run_pattern|RunPattern|_legacy_result|_worker_entry'` 在 `agent/` `tests/` `benchmarks/` `web/` **以及 `openspec/specs/`** 零命中（`openspec/specs/` 必须纳入——grill 查出存量 spec 另有两条 Requirement 硬引用 `RunPattern`，见 6.6a）
- [ ] 5.9 订正 docstring/注释里的 `RunPattern` 措辞：`bus.py:3`、`context.py:11`（模块 docstring）、`benchmarks/agent_runner.py:518`（注释）、`scheduler.py:499-502`（`asset_source` 注释自述「`RunWorkflow` 路径从不设置 `scheduler.spec`」，与 `run()` 在 `:795` 的 `self._spec = spec` 矛盾，R2 顺手订正）
- [ ] 5.10 **改写（非删除）**留存工具的模型面文案：`SaveWorkflowAsset` 描述里的 `RunPattern` 引用（`subagents.py:948-951`「RunPattern-sourced graphs…」、`:960`「workflow_id returned by RunPattern/…」）改为统一入口口径——5.8 的 grep 会命中，但性质是**改写**不是删净

## 6. 文档与收尾

- [ ] 6.1 `docs/openspec-change-backlog.md`：新增本 change 条目 + 并行批次（与 #261 flaky 修复并行，仅此文件可能冲突）
- [ ] 6.2 更新 `docs/agent-internals.md:1029` 的工具清单树（去 `RunPatternTool`、补 `RunWorkflow` 的 `template` 入参）；`docs/architecture.md` 工具清单段落同样处理
- [ ] 6.3 检查 `README.md` 与同步 `README_EN.md`（如工具清单被列出）
- [ ] 6.4 处理 `docs/` 下 `RunPattern` 命中文件（逐个显式决定：更新 or 记债务，不静默留错）：`docs/interview-script/run-pattern-web-demo.md`（整份文件，8 处）、`docs/interview-bullets/walkthrough.md`（14 处，含「10 个 spawn 工具」口径）、`docs/interview-script/walkthrough/W03-multi-agent.md`（2 处）、`docs/interview-script/questions/Q08-multi-agent.md`（1 处）、`docs/interview-bullets/interview-prep.md`（1 处）；工具数 10→9 的叙述一并订正
- [ ] 6.5 受保护 artifact（`openspec/specs/**`）修改落 `workflow-events.jsonl` 结构化解释事件
- [ ] 6.6 把 spec delta 同步到 current spec（`openspec/specs/<capability>/spec.md`：multi-agent-collaboration / subagents / agent-runtime / web-ui）并归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-builtin-templates/`，从 backlog 移除
- [ ] 6.6a **补 MODIFY 两条被 grill 查出的存量 Requirement**：`openspec/specs/multi-agent-collaboration/spec.md` 的「资产保存是显式的，且 spec 不穿过模型输出」（`:534-543`，Scenario GIVEN 写 `RunPattern`）与「资产的两类载体与参数化复用」（`:558-567`，正文与 Scenario 写 `RunPattern(pattern=…)`）——delta 已含此两条（本 change `specs/multi-agent-collaboration/spec.md`），确认同步后存量文件零 `RunPattern`
- [ ] 6.7 跑 `/review-loop`（独立审阅闭环）至 PASS 或 3 轮封顶，产出 `reviews/building-review.md` + manifest
- [ ] 6.8 全量 `uv run pytest -q` + benchmark smoke（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`，确认 `template` 臂不受影响）+ `openspec validate --all --strict` + `check_openspec_artifacts.py`
- [ ] 6.9 发起 PR 并合入
- [ ] 6.10 (post-merge) 给 issue #246 加完成说明 comment 并关闭
