# Tasks: DryRunWorkflow

> 实现前须完成 grill（`reviews/grill-design.md`）与**停轮确认**。测试先行（TDD）：每条实现任务先落回归/新测试再落代码。

## 0. 实现前设计追问（batch-grill-me）——**已解除阻塞**

> **状态：grill 与停轮确认均已完成**（2026-09-30）。grill verdict = CHANGES_REQUESTED，10 条 issue 已全部回写关闭；Q1–Q6 已全部拍板并回写 design/spec/tasks。**实现可开工。**

- [x] 0.1 用独立零记忆 subagent 执行 `batch-grill-me`（或等价设计追问），逐项审视 `design.md` 的 D1–D10，产出结构化决策记录到 `reviews/grill-design.md`（7 条 Confirmed Decisions + 4 条 Design-Level Open Questions；verdict CHANGES_REQUESTED → 10 条 issue 全部回写关闭）
- [x] 0.2 **停轮**把 Q1–Q6 逐条**配具体例子**（design 的 Open Questions 节已给出循环收敛/按项、`_store` 替换、截断上界、slots 与引导位置、防滥用设界、聚合产出语义与 input_source 六个场景）交用户确认；答复记录进 `grill-design.md` 的 `## User Confirmation`（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）
- [x] 0.3 按 Q1–Q6 答复回写 design（D3/D4/D4b/D5/D7/D10 + Non-Goals）与 spec delta、本任务清单（Q1 数组按调用次序、Q2 替换 `_store`、Q3 默认 800、Q4 两处都加引导+返回槽值、Q5 软提醒+硬上限、Q6 切断 summarizer+标 `input_source`）

## 1. 规格

- [x] 1.1 更新 `multi-agent-collaboration` 的 spec delta（ADDED 3 条 Requirement + MODIFIED 1 条——Q4 拍板加引导指针）
- [x] 1.2 明确本 change 的范围（proposal「What Changes」）、非目标（design「Goals / Non-Goals」）和**验收标准**（proposal「验收」节）
- [x] 1.3 开发前使用 `batch-grill-me` 或等价设计追问审视 `design.md`（见第 0 节；不得把 agent 自己的推荐答案当作用户确认）
- [x] 1.4 维护 `## Impact Analysis`（proposal）：列出影响、不影响和待确认影响面
- [x] 1.5 维护 `## Reference Implementation Research`（proposal）：`research_tier: full` + 完整五字段
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录待 grill 项与机械门禁要求

## 2. 测试（TDD：先落测试再落代码）

- [ ] 2.1 **T-1 隔离·落盘**：模拟后真实 `workspace_root` 零新增文件（F1/F6）。**变异验证**：把一次性 manager 换成真实 manager，测试必须变红（F9：W1 会往真实 workspace 写）
- [ ] 2.2 **T-2 隔离·注册表**：真实 manager 的 `_workflows`/`_workflow_stores` 为空（F3/F6）
- [ ] 2.2a **T-2a（Q2 已拍板选 B）**：一次性临时目录里无 `events.jsonl`/`root.txt`（G2：不选 B 时应为 8 个文件、选 B 后 6 个且不含这两个）；并加 `assert hasattr(scheduler, "_store")` 让私有属性被重构时在构造点就红
- [ ] 2.3 **T-3 隔离·零 token**：真实 `manager.llm.chat` 调用数 = 0。**变异验证（grill I9 订正）**：不能只「换回真 LLM」——真实 manager 从不被交给 scheduler，该断言**结构性恒真**。正确的变异是「**让模拟 manager 复用真实 manager 的 `llm` 对象**」，此时测试必须变红
- [ ] 2.4 **T-4 隔离·sink**：真实 manager 的 `graph_sink` 未被调用（F2）
- [ ] 2.5 **T-5 数据流·received**：foreach 展开项 prompt 含 item（占位符是 `{item}` **不是 `$item`**，`scheduler.py:369-380`）；下游节点 prompt 含上游 bounded 产出
- [ ] 2.5a **T-5a foreach 各项不坍缩（实测缺口 G1）**：foreach 展开 3 项时，报告的 `received` 里 3 项各自的输入**分别可见**。**变异验证**：改回 `received[node_id]` 单键写法，测试必须变红（`research/foreach_gap.py` 实证：单键会只剩最后一项）
- [ ] 2.5b **T-5b 自动插入层可见（实测缺口 G3）**：一张会触发自动汇合层插入的图（如 20 项 foreach），报告里 SHALL 含 `__auto_agg__*` 节点且标 `auto_inserted: true`。**变异验证**：把节点枚举从 `plan.nodes` 改回 `spec.nodes`，测试必须变红（`research/extra_calls.py` 实证：该图实际跑 4 个节点，`spec.nodes` 只有 2 个）
- [ ] 2.6 **T-6 数据流·input_seen（S1）**：`a→mid→gate` 时 `gate.input_seen == mid` 产出
- [ ] 2.7 **T-7 数据流·input_seen（S2）**：`aggregate→critic→gate` 时 `gate.input_seen` 是**聚合槽值**——把未钉住的语义固化为断言（断言的是「报告如实反映现状」，**不是**「现状是对的」）
- [ ] 2.7a **T-7a input_source（Q6）**：route 的判定输入来源节点 id 可见（S2 形态下应为那个聚合节点，不是直接上游的 subagent）
- [ ] 2.8 **T-8 `script` 注入（S4）**：不传 script → route 走 default；传 script 命中 case → route 走对应分支。**⚠️ 图形态必须是 `a(subagent)→mid(subagent)→gate`**（route 的直接上游是 subagent、且其上游无 `result` 槽）——**不能用 `agg→critic→gate`**：那种形态下 route 读的是聚合槽（S2），`script:{"critic":...}` **不会**改变走向（实测，`research/summarizer_pollution.py` 的姊妹场景）。**这条是 grill 发现的：初稿的 T-8 按 canonical 图的写法根本过不了。**
- [ ] 2.8a **T-8a 失败节点带 `reason`**：模拟中某节点非正常结束（如触达 `max_nodes` / run 被拒）时，报告的该节点带可解释原因，且不至于让调用方把「失败导致 route 走 default」误读为拓扑本身如此
- [ ] 2.9 **T-9 回边不带文本（S3）**：回边重跑时被重派发节点的 `received` 与首轮相同
- [ ] 2.9a **T-9a 聚合产出不被替身污染（F4/F4a）**：`collect` 聚合且上游超出预算时，报告的聚合产出是**有界投影**而非替身回复。**变异验证**：不切断 summarizer 路径，测试必须变红（`research/summarizer_pollution.py` 实证：`root.summary` 会变成 `[SUMMARY-PLACEHOLDER]`）
- [ ] 2.9b **T-9b 无不可归因调用（F4a）**：报告/`received` 里不出现 `None`/`?` 节点的条目
- [ ] 2.10 **T-10 有界性（D5）**：超长产出被截断到 `max_report_chars`
- [ ] 2.11 **T-11 边界声明（D6/D8）**：返回体含 `simulated: true` 与边界文案；**不含 `workflow_id`**
- [ ] 2.11a **T-11a 答不了清单（R10）**：返回体/描述 SHALL 声明「token/成本预算闸不可预测」与「结构闸可预测」的区分
- [ ] 2.12 **T-12 schema parity**：`DryRunWorkflow.spec` 的 schema 与 `DeclareWorkflow.spec` **逐字相等**
- [ ] 2.13 **T-13 工具面**：`DryRunWorkflow` **不在** `SPAWN_TOOL_NAMES`；depth 撤工具时不撤它
- [ ] 2.14 **Q1 已拍板「数组按调用次序」**：新增「同一节点多轮不同产出 → 循环收敛可见」测试 + 「数组用尽后沿用末元素」断言 + 「数组同时覆盖 foreach 各展开项」断言

## 3. 实现

- [ ] 3.1 `agent/tools/builtin/subagents.py`：新增 `_DryRunLLM`（假 LLM：回显 + 按 `current_node_id()` 支持 `script` 注入；只返回文本、不发起 tool call）
- [ ] 3.2 **Q2 已拍板选 B**：新增 `_NullWorkflowStore`（所有写方法 no-op，`ref()` 返回假 ref）——用于替换 `scheduler._store`。**注意 W1（`manager._write_result_artifacts`）不经它**，由一次性 `workspace_root` 兜住（G2/F9）
- [ ] 3.3 `agent/tools/builtin/subagents.py`：新增模拟驱动函数（**核心隔离手段 = 一次性 manager + 一次性 `workspace_root` + 假 LLM**；**Q2 已拍板额外替换 `scheduler._store`**）
- [ ] 3.4 `agent/tools/builtin/subagents.py`：新增报告构造（`received`/`produced`/`input_seen`/`matched`/`walked_to`/`used_default`/`edges[].control`/`nodes[].status`/`nodes[].auto_inserted`/`simulated: true`），文本按 `max_report_chars` 截断——**不复用也不改 `NodeState.to_dict()`**。**节点枚举基于 `scheduler._plan.nodes`**（含 auto 层）并标 `auto_inserted`（见 G3）；**`received` 按 `(node_id, item_index)` 寻址**（非 foreach 节点 `item_index=null`；foreach 的 received 是按项列表）——见 G1
- [ ] 3.4a **Q1 已拍板「数组按调用次序消费」**：实现 script 的 `str | [str]` 两形态（**假 LLM 内按节点自计数**即可拿到「第几次调用」，不依赖调度器）；schema 用「两种类型并列」写法，**不得用 `oneOf`**（`#246` RIR 实测 Anthropic 顶层 `oneOf` 受限）
- [ ] 3.4b **Q6 已拍板：切断 collect 聚合的 summarizer 路径（D4b）**：把 simulated aggregator 的 summarizer 置为 `TruncationSummarizer`（既有生产兜底）；不碰 `scheduler.py` 执行逻辑
- [ ] 3.4c **Q6 已拍板**：报告为 route 附 `input_source`（判定输入的来源节点 id）；聚合产出标为有界投影
- [ ] 3.5 `agent/tools/builtin/subagents.py`：新增 `DryRunWorkflowTool`（`@tool_parameters`，`spec` 复用 `_workflow_spec_schema()`；`description` ≤2000 字符 + 断言式无副作用声明；`read_only=True`、`permission=SUBAGENT_CONTROL_PERMISSION`）
- [ ] 3.6 `agent/loop.py`：在既有注册块加 `DryRunWorkflowTool(self.subagent_manager)`（**不加入 `SPAWN_TOOL_NAMES`**）
- [ ] 3.7 实现调用计数（**Q5 拍板：A+C 混合**——软提醒 ~10 + 硬上限 ~40 + `hint`；**计数点需选在能跨调用存活的位置**——`DryRunWorkflow` 不持有 session，需确认挂在 manager 还是工具构造处）
- [ ] 3.8 **Q4 已拍板「返回槽值」**：报告中加截断后的 `slots` 字段（独立顶层字段、单独截断、只在被 route 实际读到时展开）
- [ ] 3.9 **Q4 已拍板「两处都加引导」**：`DeclareWorkflow` 描述加一句极短指针（余量充足，无需压缩既有分节——保住 #248 建立的 `cases`/per-kind/门控语义）
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
