# Tasks: DryRunWorkflow

> 实现前须完成 grill（`reviews/grill-design.md`）与**停轮确认**。测试先行（TDD）：每条实现任务先落回归/新测试再落代码。

## 0. 实现前设计追问（batch-grill-me）——**未解除阻塞**

> **状态（立项时点）**：design 的 D1–D10 已成型，但 **Q1–Q5 刻意未拍板**（design 的 `## Open Questions`）。**grill-confirmation-gate 未通过，实现不得开工。**

- [ ] 0.1 用独立零记忆 subagent 执行 `batch-grill-me`（或等价设计追问），逐项审视 `design.md` 的 D1–D10，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥3 条 + `## Open Questions`）
- [ ] 0.2 **停轮**把 Q1–Q5 逐条**配具体例子**（design 的 Open Questions 节已给出循环收敛、`_store` 替换、截断上界、slots 与引导位置、防滥用设界五个场景）交用户确认；答复记录进 `grill-design.md` 的 `## User Confirmation`（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）
- [ ] 0.3 按 Q1–Q5 答复回写 design（D3/D4/D5/D7/D10 + Non-Goals）与 spec delta、本任务清单

## 1. 规格

- [x] 1.1 更新 `multi-agent-collaboration` 的 spec delta（ADDED 3 条 Requirement）
- [x] 1.2 明确本 change 的范围（proposal「What Changes」）、非目标（design「Goals / Non-Goals」）和**验收标准**（proposal「验收」节）
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`（见第 0 节；不得把 agent 自己的推荐答案当作用户确认）
- [x] 1.4 维护 `## Impact Analysis`（proposal）：列出影响、不影响和待确认影响面
- [x] 1.5 维护 `## Reference Implementation Research`（proposal）：`research_tier: full` + 完整五字段
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录待 grill 项与机械门禁要求

## 2. 测试（TDD：先落测试再落代码）

- [ ] 2.1 **T-1 隔离·落盘**：模拟后真实 `workspace_root` 零新增文件（F1/F6）。**变异验证**：把一次性 manager 换成真实 manager，测试必须变红（F9：W1 会往真实 workspace 写）
- [ ] 2.2 **T-2 隔离·注册表**：真实 manager 的 `_workflows`/`_workflow_stores` 为空（F3/F6）
- [ ] 2.2a **T-2a（仅当 Q2 选 B）**：一次性临时目录里无 `events.jsonl`/`root.txt`（G2：不选 B 时应为 8 个文件、选 B 后 6 个且不含这两个）
- [ ] 2.3 **T-3 隔离·零 token**：真实 `manager.llm.chat` 调用数 = 0。**变异验证**：把假 LLM 换回真 LLM，测试必须变红→还原变绿
- [ ] 2.4 **T-4 隔离·sink**：真实 manager 的 `graph_sink` 未被调用（F2）
- [ ] 2.5 **T-5 数据流·received**：foreach 展开项 prompt 含 item（占位符是 `{item}` **不是 `$item`**，`scheduler.py:369-380`）；下游节点 prompt 含上游 bounded 产出
- [ ] 2.5a **T-5a foreach 各项不坍缩（实测缺口 G1）**：foreach 展开 3 项时，报告的 `received` 里 3 项各自的输入**分别可见**。**变异验证**：改回 `received[node_id]` 单键写法，测试必须变红（`research/foreach_gap.py` 实证：单键会只剩最后一项）
- [ ] 2.6 **T-6 数据流·input_seen（S1）**：`a→mid→gate` 时 `gate.input_seen == mid` 产出
- [ ] 2.7 **T-7 数据流·input_seen（S2）**：`aggregate→critic→gate` 时 `gate.input_seen` 是**聚合槽值**——把未钉住的语义固化为断言（断言的是「报告如实反映现状」，**不是**「现状是对的」）
- [ ] 2.8 **T-8 `script` 注入（S4）**：不传 script → route 走 default；传 `{"critic":"GAPS"}` → route 走回边
- [ ] 2.9 **T-9 回边不带文本（S3）**：回边重跑时被重派发节点的 `received` 与首轮相同
- [ ] 2.10 **T-10 有界性（D5）**：超长产出被截断到 `max_report_chars`
- [ ] 2.11 **T-11 边界声明（D6/D8）**：返回体含 `simulated: true` 与边界文案；**不含 `workflow_id`**
- [ ] 2.12 **T-12 schema parity**：`DryRunWorkflow.spec` 的 schema 与 `DeclareWorkflow.spec` **逐字相等**
- [ ] 2.13 **T-13 工具面**：`DryRunWorkflow` **不在** `SPAWN_TOOL_NAMES`；depth 撤工具时不撤它
- [ ] 2.14 若 Q1 选「支持按轮次」：新增「同一节点多轮不同产出 → 循环收敛可见」测试；若选「单值」：新增「单值下环一圈不转」的负向断言（把选定行为钉死）

## 3. 实现

- [ ] 3.1 `agent/tools/builtin/subagents.py`：新增 `_DryRunLLM`（假 LLM：回显 + 按 `current_node_id()` 支持 `script` 注入；只返回文本、不发起 tool call）
- [ ] 3.2 **仅当 Q2 选 B**：新增 `_NullWorkflowStore`（所有写方法 no-op，`ref()` 返回假 ref）——用于替换 `scheduler._store`。**注意 W1（`manager._write_result_artifacts`）不经它**，由一次性 `workspace_root` 兜住（G2/F9）
- [ ] 3.3 `agent/tools/builtin/subagents.py`：新增模拟驱动函数（**核心隔离手段 = 一次性 manager + 一次性 `workspace_root` + 假 LLM**；Q2 选 B 时额外替换 `scheduler._store`）
- [ ] 3.4 `agent/tools/builtin/subagents.py`：新增报告构造（`received`/`produced`/`input_seen`/`matched`/`walked_to`/`used_default`/`edges[].control`/`nodes[].status`/`simulated: true`），文本按 `max_report_chars` 截断——**不复用也不改 `NodeState.to_dict()`**。**`received` 按 `(node_id, item_index)` 寻址**（非 foreach 节点 `item_index=null`；foreach 的 received 是按项列表）——见 G1
- [ ] 3.4a 若 Q1 选 (b)/(c)：实现「数组按调用次序消费」的 script 语义（**须先验证「假 LLM 内如何拿到第几次调用」**——用调用序而非依赖调度器）
- [ ] 3.5 `agent/tools/builtin/subagents.py`：新增 `DryRunWorkflowTool`（`@tool_parameters`，`spec` 复用 `_workflow_spec_schema()`；`description` ≤2000 字符 + 断言式无副作用声明；`read_only=True`、`permission=SUBAGENT_CONTROL_PERMISSION`）
- [ ] 3.6 `agent/loop.py`：在既有注册块加 `DryRunWorkflowTool(self.subagent_manager)`（**不加入 `SPAWN_TOOL_NAMES`**）
- [ ] 3.7 **仅当 Q5 选 A/C**：实现调用计数（session 级计数点与 `hint` 文案；A 阻断、C 软提醒）
- [ ] 3.8 **仅当 Q4 选「返回 slots」**：报告中加截断后的 `slots` 字段（单独字段、单独截断）
- [ ] 3.9 **仅当 Q4 选「DeclareWorkflow 加指针」**：压缩既有分节腾出余量后加一句指针（**保住既有契约文字**，不得压掉 #248 建立的 `cases`/per-kind/门控语义）
- [ ] 3.10 如果实现中发现必须改 `scheduler.py`（破坏 D4 承诺），**先停轮**回写 Impact Analysis 与 design D4，再继续
- [ ] 3.11 如果实现中发现 RIR 结论需要修正，先回写 Reference Implementation Research 和本任务清单
- [ ] 3.12 更新必要文档（`docs/openspec-change-backlog.md` 入队 + 关键词扫描 `README.md`/`README_EN.md`/`docs/architecture.md` 的工具清单段落；如无事实变化则在 review 记录中说明）

## 4. 端到端验收（本 change 的唯一有效性证据）

- [ ] 4.1 **清空全局资产库** `~/.asterwynd/projects/<hash>/workflow-assets/`；**每次 rollout 之间 quarantine 记忆**（`MemoryIndexSource` 污染会让 S0 假达标，#248 踩过）
- [ ] 4.2 跑**基线**吗？——**不重跑**。基线沿用 #248 归档的 `reviews/` 记录（`baseline-transcript-2026-09-29.log`，S0=9），并**如实标注口径**：本 change 的基线是**改后 #248 的状态**（S0 = 6/7/4），不是 #248 基线（9）——因为本次是在 #248 之上继续。**两个对照都要写清**。
- [ ] 4.3 跑**改后** N=3：同提示词、同模型（`deepseek-v4-flash`）、同 `--mode bypass`，记录 S0–S8
- [ ] 4.4 落盘证据到 `reviews/acceptance-evidence.md`（改后表 + 与 #248 改后的对照 + 原始 transcript 路径）
- [ ] 4.5 主 session 软判断：读 transcript 回答「它在**理解工具** vs **理解任务**上花了多少」（两者必须分开）；重点看 **S8**——dry run 是否真的替代了探针
- [ ] 4.6 通过门槛判定：S0 是否降到 0 且 S6 成立；**负面检查 S7**（dry run 调用次数是否形成新循环）。不达标则如实记录归因，**交主 session 决定是否迭代**

## 5. 验证

- [ ] 5.1 运行相关单元/集成测试（`uv run pytest tests/agent/subagent/ tests/agent/tools/ -q`）
- [ ] 5.2 运行全量测试（`uv run pytest -q`）
- [ ] 5.3 运行 OpenSpec strict validate（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [ ] 5.4 运行项目 artifact checker（`uv run python scripts/check_openspec_artifacts.py`）
- [ ] 5.5 确认 baseline CI 命令可本地通过（`uv run pytest -q` + strict validate + artifact checker）
- [ ] 5.6 **benchmark smoke**（本 change 触及 `agent/tools/`）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`
- [ ] 5.7 确认工具**数量变化只增 `DryRunWorkflow`**，既有工具名字/行为不变（回归 `test_workflow_tools.py`）
- [ ] 5.8 确认 `patterns.py` 四个模板的 `spec_hash` **无变化**（本 change 不碰模板）
- [ ] 5.9 **受保护 artifact 结构化事件**：改 `openspec/specs/**` 落 `current_spec_synced`、改 `docs/openspec-change-backlog.md` 落 `backlog_updated`

## 6. 审阅闭环与 PR 收尾

- [ ] 6.1 跑 `/review-loop`（独立审阅闭环），直到 PASS 或 3 轮封顶；产出 `reviews/building-review.md`
- [ ] 6.2 review manifest 在本 change 的 `tasks.md` 最终化（含归档 move）之后生成
- [ ] 6.3 把 spec delta 同步到 current spec（`openspec/specs/multi-agent-collaboration/spec.md`）
- [ ] 6.3a 归档到 `openspec/changes/archive/2026-09-30-workflow-dry-run/`
- [ ] 6.4 从 `docs/openspec-change-backlog.md` 移除本 change 并同步批次
- [ ] 6.5 确认 Impact Analysis 不再残留未解释的 `unknown`/`TBD`/`待确认`
- [ ] 6.6 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响
- [ ] 6.7 (post-merge) 发起 PR 并合入（由主 session 确认后执行；worktree 不 push）
- [ ] 6.8 (post-merge) 给 issue #273 加完成说明 comment 并关闭；**按用户拍板重新评估 #268 / #269 是否还需要**（#273 可能覆盖它们的动机）
