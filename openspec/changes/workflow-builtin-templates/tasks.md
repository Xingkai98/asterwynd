# Tasks: 内置模板归一（RunPattern 融合进 Workflow DSL 入口）

> 实现前须完成 grill（`reviews/grill-design.md`）与停轮确认。测试先行（TDD）：每条实现任务先落回归/新测试再落代码。

## 0. 实现前设计追问（batch-grill-me）

- [ ] 0.1 用独立零记忆 subagent 执行 `batch-grill-me`（等价设计追问），逐项审视 design.md 的 D1–D6，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条决策 + `## Open Questions` + `## User Confirmation`）
- [ ] 0.2 停轮把 `## Open Questions` 逐条配具体例子交用户确认，答复记录进 `grill-design.md` 的 `## User Confirmation`；收到答复前不写实现代码

## 1. 共享配方编译路径（D3 / D4）

- [ ] 1.1 在 `agent/subagent/patterns.py` 落共享 helper `_compile_recipe(pattern, task, params) -> WorkflowSpec`（实现期定名）：内部即 `compile_pattern`，统一「未知模板名 → 结构化拒绝」的措辞；被统一入口与资产路径共用
- [ ] 1.2 在 `agent/subagent/patterns.py` 落 `params` 键集校验（封闭集合：`workers`/`teams`/`proposers`/`max_rounds`/`worker_max_tokens`/`worker_max_time_s`），未知键结构化拒绝（消灭「以为传了」的假象）
- [ ] 1.3 单测：helper 对 `{"workers": 3}` 的产出与 `compile_pattern("orchestrator-worker", task=…, params={"workers": 3})` 的 `spec_hash` 相等；未知名/未知键各一条结构化拒绝

## 2. 统一 Workflow 入口的 template 输入（D1）

- [ ] 2.1 测试先行：`RunWorkflow` 的四条非法组合各一条（同时给 spec+template / 都不给 / template 缺 task / 未知模板名）+ spec 路径带 params 或 task 拒绝
- [ ] 2.2 扩展 `RunWorkflowTool`（`agent/tools/builtin/subagents.py`）的 `tool_parameters`：新增 `template`/`task`/`params`，描述里写明「exactly one of spec/template」与「`wait=false` 返回启动回执而非结果」
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
- [ ] 4.4 template 分支与 spec 分支统一返回 `scheduler.parent_envelope()`（`wait=true`）；`wait=false` 保持既有回执形状
- [ ] 4.5 确认 `agent/subagent/scheduler.py` 的 `_envelope`/`parent_envelope` **逐字不动**；回归 `test_bounded_envelope.py` 的键集与界断言

## 5. 删除面与引用清理（D5）

- [ ] 5.1 删除 `RunPatternTool`（`agent/tools/builtin/subagents.py`）与 `agent/loop.py` 的注册
- [ ] 5.2 删除 `run_pattern` / `_legacy_result` / `_workers_from_node` / `_worker_entry` / `_AGGREGATE_NODE_IDS`（`agent/subagent/patterns.py`）；改写模块 docstring 中描述 `run_pattern` 返回形状的段落
- [ ] 5.3 `manager.py` 的 `SPAWN_TOOL_NAMES` 去掉 `"RunPattern"`
- [ ] 5.4 订正 `agent/subagent/bus.py` 的 `snapshot_payload()` docstring 中「模型面调用点是 RunPattern」的措辞（界本身不落笔）
- [ ] 5.5 改写受影响测试：`test_patterns.py` / `test_pattern_templates.py` 5.2 段 / `test_bus_bounded_exports.py` 出口 2 / `test_bounded_envelope.py` / `test_guardrails.py` / `test_concurrency_queue.py`
- [ ] 5.5a **#245 回归测试迁移**（实测确认这三个文件用 `RunPatternTool` 产出 pattern 图）：`test_workflow_asset_tools.py:121`、`test_workflow_asset_context.py:165` 改用 `RunWorkflow(template=…)` 产出 pattern 图；`test_workflow_asset_context.py:195` 的 `test_run_pattern_result_keyset_is_locked`（键集锁）随 `run_pattern` 退役删除，其「加字段必须是有意识的」语义改挂到统一入口返回体的键集锁上
- [ ] 5.6 **出口 4 语义迁移**：把 `test_workflow_node_transcript.py` 的「worker 条目 bounded + `result_ref` 补偿」断言改挂到新出口（`GetWorkflow(detail='nodes')` 的 `result_ref` 或 `root_result_ref`），**不删断言语义**（issue #213 回归保护）
- [ ] 5.7 深度闸测试：深度到限子 agent 工具集不含 `RunWorkflow` 与 `RunPattern`
- [ ] 5.8 删净检查：`rg 'run_pattern|RunPattern|_legacy_result'` 在 `agent/` `tests/` `benchmarks/` `web/` 零命中

## 6. 文档与收尾

- [ ] 6.1 `docs/openspec-change-backlog.md`：新增本 change 条目 + 并行批次（与 #261 flaky 修复并行，仅此文件可能冲突）
- [ ] 6.2 更新 `docs/agent-internals.md:1029` 的工具清单树（去 `RunPatternTool`、补 `RunWorkflow` 的 `template` 入参）；`docs/architecture.md` 工具清单段落同样处理
- [ ] 6.3 检查 `README.md` 与同步 `README_EN.md`（如工具清单被列出）
- [ ] 6.4 处理 `docs/` 下 `RunPattern` 命中文件（逐个显式决定：更新 or 记债务，不静默留错）：`docs/interview-script/run-pattern-web-demo.md`（整份文件，8 处）、`docs/interview-bullets/walkthrough.md`（14 处，含「10 个 spawn 工具」口径）、`docs/interview-script/walkthrough/W03-multi-agent.md`（2 处）、`docs/interview-script/questions/Q08-multi-agent.md`（1 处）、`docs/interview-bullets/interview-prep.md`（1 处）；工具数 10→9 的叙述一并订正
- [ ] 6.5 受保护 artifact（`openspec/specs/**`）修改落 `workflow-events.jsonl` 结构化解释事件
- [ ] 6.6 把 spec delta 同步到 current spec（`openspec/specs/<capability>/spec.md`：multi-agent-collaboration / subagents / agent-runtime / web-ui）并归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-builtin-templates/`，从 backlog 移除
- [ ] 6.7 跑 `/review-loop`（独立审阅闭环）至 PASS 或 3 轮封顶，产出 `reviews/building-review.md` + manifest
- [ ] 6.8 全量 `uv run pytest -q` + benchmark smoke（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`，确认 `template` 臂不受影响）+ `openspec validate --all --strict` + `check_openspec_artifacts.py`
- [ ] 6.9 发起 PR 并合入
- [ ] 6.10 (post-merge) 给 issue #246 加完成说明 comment 并关闭
