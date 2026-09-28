# Tasks: workflow 节点 mode 钳制基准修正（fix-issue-255-mode-ceiling）

> 实现前置（硬性，AGENTS.md）：本 change 是非平凡 change，**写实现代码前**必须运行独立零记忆 agent 的 `batch-grill-me`，产出 `reviews/grill-design.md`，并在 `## Open Questions` 上**停轮**取得用户逐条答复（记录进 `## User Confirmation`）。**O1–O5 已于 2026-09-27 全部确认（见 `design.md` 的 `## Open Questions`）**，用户答复：O1=纳入（挂载 A 必须）、O2=run 起点口径、O3=回落静态 `parent_mode`（绝不回落 `None`）、O4=#255 拥有机制与基准语义、O5=带 `finally reset`。任务 1.2/1.3 已由确认过程完成，1.1 的 grill 记录由 `reviews/grill-design.md` 落盘。

## 1. 前置：设计追问与确认（阻塞实现）

- [x] 1.1 运行 `batch-grill-me`（零记忆 subagent），产出 `reviews/grill-design.md`（≥3 条决策），覆盖 D1–D6
- [x] 1.2 停轮把 O1–O5 逐条抛给用户（每条配 real 场景例子），取得明确答复并写入 `reviews/grill-design.md` 的 `## User Confirmation`
- [x] 1.3 按答复回写 `design.md`（挂载 A 升级为必须、快照点定为 run 起点、与 #245 的 delta 归属已定）
- [x] 1.4 核实与 #245 的接口：确认 `current_mode_ceiling()` 的签名与回落语义即为 #245 Q11 所需通道，并在本 change 文档记录该契约

## 2. 机制实现（contextvar 上限通道）

- [x] 2.1 在 `agent/subagent/context.py` 新增 mode 上限 `ContextVar` 与 `current_mode_ceiling()` / `set_mode_ceiling()` / `reset_mode_ceiling()` 访问器（与既有 `workflow_id` / `graph_distance` 同形）
- [x] 2.2 在 `SubAgentManager` 实现「上下文上限 → 静态 `parent_mode`」的保守回落链；确认回落不得为无界
- [x] 2.3 `_clamp_mode` / `_parent_mode` 改读该上限（保留静态 `parent_mode` 兜底）
- [x] 2.4 删除 `SubAgentManager.parent_mode_provider` 字段、`configure_runtime` 对应形参与赋值
- [x] 2.5 删除 `AgentLoop.__init__` 里写 `parent_mode_provider` 的 `lambda`（`agent/loop.py:153-155`）
- [x] 2.6 `rg 'parent_mode_provider'` 零命中——**验收范围须排除** `docs/openspec-change-backlog.md`（历史引用）与 `benchmarks/tasks/**/*.patch`（`asterwynd-009-subagent-manager` 的 gold patch 含该串，属早于现状的基线，grill 实测）

## 3. 上限挂载

- [x] 3.1 **【独立验收项；O1 已确认必做】挂载 A（run 起点收紧）**：在 `_run` 中 **resume 恢复 mode 之后**（`agent/loop.py:602-605` 之后）、把上限快照为当时 `runtime_state.current_mode` 并 `set_mode_ceiling(...)`；**run 起点先捕获 `prior = current_mode_ceiling()`，在 `finally` 用 `set(prior)` 恢复**（**不得**用 `reset(token)`——跨 context teardown 会抛 `ValueError`；也不得「什么都不做」，否则跨会话泄漏上限，见 4.10）。**验收判据**：直接 `CreateSubagent` 链式嵌套下，孙辈继承父辈的有效 mode（对应 4.4 路径 b）
- [x] 3.2 **挂载 B（派发点）**：`scheduler._launch_run` 在既有 4 个身份 contextvar 旁 `set_mode_ceiling(min(node.mode 或 cur, cur))`，并在 `finally` reset（O5 已确认带 reset）
- [x] 3.3 确认派发点的 set/reset 与既有身份 contextvar 同形；确认执行点（`_execute_run_in_context`）**未**照抄 `finally reset`
- [x] 3.4 **【独立验收项；O1 已确认必做】确认嵌套收紧**：节点子 run 的上下文上限 = 该节点的有效 mode（经挂载 A 收紧），使子孙逐层继承；覆盖「直接 spawn 链」与「workflow 节点内派生」两条路径

## 4. 回归测试（先测后码：每个方向先写失败用例，再实现）

> 每项必须有对照的「合法路径必须成功」用例，防「无差别压低」的假修复。每条修复后做变异验证（改坏实现 → 测试变红 → 还原）。

> **硬约束（grill 复核）**：4.1–4.4、4.6 **必须经真实 `AgentLoop.run` 驱动**（真实 root loop + 真实 `SubAgentManager` + 真实 `WorkflowScheduler`），**不得**用 mock / 手工 `set_mode_ceiling(...)` 包裹 `scheduler.run()` 替代——后者在 defect 与 fixed 下取值相同，是假保护。

- [x] 4.1 fail-open 方向：只读会话 + 声明 `build` 的节点 ⇒ 授予只读；**对照**：build 会话 + 声明 `build` ⇒ 授予 build
- [x] 4.2 静默降级方向：BUILD 会话中先跑只读节点再跑 `build` 节点 ⇒ 后者为 build；**对照**：该只读节点自身仍为只读
- [x] 4.3 并发：并行 `A(build)` / `B(read_only)` 各自正确；**对照**：构造序 `('A','B')` 与 `('B','A')` 结果一致（时序不变性）。**注意**：默认配置下此用例在 defect 与 fixed 下都绿（grill 实测），它是**护栏**而非防假保护；其对照须补「同 task 内人为交错两个 `_launch_run`」形态
- [x] 4.4 嵌套：grandchild 上限继承父节点的**有效** mode。**两条路径都必须覆盖，不得标为可选**（O1 已确认纳入范围）：(a) workflow 节点内派生子 agent；(b) 直接 `CreateSubagent` 链式派生——**用可达例子**：root 会话上限 = `bypass`（或 `build`），`child` 声明 `mode: build`，`grand` 不声明 mode ⇒ 只挂派发点时 `grand` 得 root 上限（新 fail-open），双挂载下得 `build`（grill 实测；**勿用**「read_only 子 agent 再起子 agent」——该路径在默认权限下被 `read_only_default` profile 拒掉，不可达）
- [x] 4.5 快照：run 中途切换 root mode，本次 run 上限不变；**对照**：该会话下一次 run 按新 mode 取上限
- [x] 4.6 跨图污染（本 change 追加）：同会话顺序两张图，图 1（含只读节点）不影响图 2 起点快照；**对照**：两图各含 build 节点时均得 build
- [x] 4.7 通道验收（#245 契约）：`current_mode_ceiling()` 在 scheduler 起点可读；未 set 时回落静态 `parent_mode`；**对照**：回落值不得为无界（bypass）
- [x] 4.8 运行收尾：子 run 取消路径下上限 set 不抛 `ValueError`（覆盖跨 context teardown）
- [x] 4.9 既有基线保持：`tests/agent/subagent/test_subagent_manager.py` 的 `test_create_subagent_*`（静态 `parent_mode=` 路径）行为不变
- [x] 4.10 **【grill 新增，高危】挂载 A 的 `set` 恢复**：同一 task 内先跑一个 `build` 会话的 `AgentLoop.run`，**再直驱**一个 `parent_mode=read_only` 的 `WorkflowScheduler.run()`（不经任何 loop），节点声明 `build` ⇒ 必须授予 `read_only`（证明 run 结束后 ceiling 已复原为 run 前值，D6 保守回落成立）
- [x] 4.11 **【grill 新增】已知残留的边界锁**：锁定「`RunSubagent` 重跑既有 session 不重新钳制 mode」的**现状行为**（文档化，非修复），避免将来被误当本 change 的回归

## 5. Spec 同步与文档影响

- [x] 5.1 同步 current spec：把本 change 的 delta 合理合并进当前规格 `openspec/specs/subagents/spec.md` 与 `openspec/specs/multi-agent-collaboration/spec.md`
- [x] 5.2 按 O4 拍板结果收窄 / 对齐 #245 的 delta：grill 复核确认 #245 的 `multi-agent-collaboration` delta（Requirement「加载期闸值与能力面钳制」末段）**已有六个逐条同义的 mode Scenario**（`节点 mode 只收窄不放宽` / `会话 mode 上限在启动时快照` / `节点自身的 mode 受上限约束` / `嵌套 spawn 逐层收紧` / `跨图嵌套同样继承有效 mode` / `并发节点互不覆盖上限`）⇒ **须由 #245 侧删除这六个 Scenario 及 Requirement 正文的 mode 段**，只保留「资产路径列出将以声明 mode 运行的节点 + diagnostics」；本 change 的 delta 不需改动。合并前核验 `openspec/specs/multi-agent-collaboration/spec.md` 无重复 Requirement
- [x] 5.3 文档影响检查：扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与 subagent mode / workflow mode 相关的段落，只更新本变更造成的事实变化
- [x] 5.4 如 design 相对已确认决策发生偏离，新增 ADR 到 `docs/adr/`
- [x] 5.5 **【grill 新增】登记已知残留与潜伏面到 `docs/known-debt.md`**：(a) `RunSubagent` 重跑既有 session 不重新钳制 mode；(b) `AgentLoop` 复用 `tool_registry.mode_policy.runtime_state` 的共享态潜伏面（当前生产不可达）。二者均**不在本 change 修**，须在 debt 文档留痕

## 6. 验证与收尾

- [x] 6.1 全量测试：`uv run pytest -q`
- [x] 6.2 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 6.3 Artifact checker：`uv run python scripts/check_openspec_artifacts.py --base-ref <PR base SHA>`
- [x] 6.4 benchmark smoke：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`（本 change 触及 AgentLoop 路径）
- [x] 6.5 维护本 change 的 `## Reference Implementation Research`：如调研结论变化，先回写 change 文档
- [x] 6.6 运行 `/review-loop fix-issue-255-mode-ceiling`，产出 `reviews/building-review.md`（PASS 或 3 轮封顶）
- [x] 6.7 生成 review manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）；**在 tasks.md 最终化之后再生成**
- [x] 6.8 归档：`openspec/changes/archive/YYYY-MM-DD-fix-issue-255-mode-ceiling/`，从 `docs/openspec-change-backlog.md` 移除
- [ ] 6.9 (post-merge) 关闭关联 issue #255 并加完成说明 comment
