# OpenSpec Change 实现队列

本文档记录当前 active OpenSpec changes 中尚未实现的需求，并按建议实现顺序排列。它不是规格本身；每个 change 的 source of truth 仍是 `openspec/changes/<change-id>/` 下的 proposal、design、specs 和 tasks。

维护规则：

- 新增 OpenSpec change 后，如果不是纯占位，应把它加入本队列。
- change 实现 PR 必须同时包含归档收尾：归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/` 并从本文档移除；如果因冲突、校验失败或其他明确阻塞暂时无法归档，才移到“已完成待归档”。
- change 状态变化时，必须同步更新“并行开发批次”和“未实现队列”两个章节，避免批次章节保留过期状态。
- 调整实现顺序时，应写清楚依赖原因，而不是只移动条目。
- 本文档只记录可提交的 change id 和稳定判断，不记录本地参考仓库路径。

## 并行开发批次

后续 change 不应全部串行，也不应全量并行。建议按以下批次推进；同一批次内可以并行开 PR，但如果两个 change 同时修改 AgentLoop、ToolRegistry、Web session 或 trace 语义，应在实现阶段错开合入，避免协议和事件模型互相覆盖。

### 第一批：已完成

- `add-repo-map-code-intelligence`：已合入并归档。
- `implement-structured-planning-state`：已合入并归档。
- `add-tool-result-display-controls`：已合入并归档。
- `harden-web-research-tools`：已合入并归档。
- `render-markdown-in-chat-surfaces`：已合入并归档。
- `add-tree-sitter-symbol-extraction`：已合入并归档。
- `add-plan-mode`：已合入并归档。
- `add-streaming-agent-output`：已合入并归档。
- `add-runtime-mode-switching`：已合入并归档。

### 第二批：benchmark 基础设施，已完成关键收敛

- `add-swebench-docker-harness`：已合入，后续 benchmark 相关 change 可以直接复用 Docker preflight、`status + reason` 和 SWE-bench harness 路径。

### 第三批：Coding Agent 基本操作面和入口回归

- 当前无未实现 change。

### 第四批：工具权限模型前置，已完成

当前无未实现 change。

### 第五批：MCP 与 TUI 基本扩展

- `add-lsp-code-intelligence`：已合入并归档。
- `add-mcp-tool-adapter`：已合入并归档。
- `add-minimal-tui-runtime-view`：建议在 skills、工具权限模型、planning state、streaming、runtime mode switching、工具结果 display policy 和已完成的 slash command framework 稳定后做，复用统一运行事件和 mode transition。

### 第六批：包结构和分发基础，已完成

- `improve-package-structure`：已合入（PR #49），未走完整 OpenSpec 流程，无需归档。

### 第七批：基础能力补全

基于与其他 coding agent（Claude Code、Codex、Cursor、Aider 等）的系统性对比，以下 6 个 change 覆盖了 Asterwynd 当前必备基础能力的核心缺口。第一批（1/3/4）可并行推进，第二批 2 等 1 合入后开始（共享 AgentLoop 改动面），第三批 5/6 可并行。

- `improve-agent-execution-foundation`：已合入并归档。
- `add-semantic-code-search`：已合入并归档。

### 第八批：高风险 browser 能力，已完成

- `add-browser-use-safety-foundation`：已合入并归档。

### 第九批：Wayfinder 面试深度深化（#73-79）

基于 wayfinder 地图 #72（面试深度路线）拆解的 6 个深化方向，已全部立项为 OpenSpec change（2026-08-01）。按批次推进；同一批次可并行开 PR，但共享 AgentLoop/ToolRegistry/trace 语义的 change 需错开合入。

- **Batch 1（并行，低冲突）**：`tool-governance-deepening`（✅ 已合入并归档，2026-08-02）‖ `sandbox-hardening`（✅ 已合入并归档，2026-08-02）。最独立、无硬依赖，各开独立 worktree。先立 `agent/embedding/` 公共模块（#77 提供，供 #75 复用）。
- **Batch 2（高冲突，拆分）**：`context-engineering-deepening`（✅ 已合入并归档，2026-08-02）。拆 3 子 change（增量 token 计数+四字段摘要+pending+L1/L2 / Prefix Cache 注入顺序 / 分页进度+深层 MD 按需加载）；已与 #77 约定「稳定层/可变层」注入契约并落实现。
- **Batch 3（并行）**：`observability-deepening`（✅ 已合入并归档，2026-08-03）‖ `long-term-memory-deepening`（✅ 已合入并归档，2026-08-02）。observability 依赖 PR #80 statistics（已合入）做回归门禁；#75 先 ADR 论证三层存储，低风险切片先行。
- **Batch 4（最后）**：`multi-agent-collaboration`（✅ 已合入并归档，2026-08-03）。依赖最重，先 grill 设计；复用 #67 `agent/workflow/` 持久化纪律而非阶段机器。

关键依赖：`#78 observability` 依赖 `#77 tool-governance` 质量事件 schema；`#75 long-term-memory` 依赖 `#77` embedding 模块；`#79` 依赖 `#74/#78`。

**#89 follow-up**：`structured-error-type-wiring`（✅ 已合入并归档，2026-08-03）。#78 的数据源接入下一步：工具错误在产生点打结构化 `error_type` 而非文本猜测（`ToolResult` 通道 + Bash/MCP/approval/LLM 打标）。
- **#99 follow-up**：`long-term-memory-reversibility`（✅ 已合入并归档，2026-08-03）。#75 长期记忆可逆性 follow-up：git commit-before-write + resolve_conflict + MemoryGitBackend（ADR-0002）。

### 第十批：Agent 侧 worktree 隔离工具

- `add-worktree-tool`（issue #111）：对标 Claude Code EnterWorktree/ExitWorktree，把 worktree 隔离做成 agent 工具面能力（agent 运行时自主创建/进入/退出）。与外部编排层现有 worktree 机制（workflow 状态机 building 强制、benchmark runner、`--keep-worktrees`）并行共存，不改动编排层。主要影响 tool-system 与 workspace-safety。

### 第十一批：评测升级系列（wayfinder map #144 决策落地）

基于 wayfinder 地图 #144（Agent 评测升级）已完成的全部决策（G1 分层/G2 任务集/G3 指标/G4 落地形态/T1 协议/T2 叙事）拆解的系列 change。**串行主链 C1→C2→C3→C4**：C1/C2 共享 `adapters.py`（子集接入 vs f2p/p2p 保留）、C2/C3 共享 `statistics/compare` 需顺序；**C3/C4 在 C2 合入后并行**（C4 叙事引用 C3 协议与数字）。每 change 独立 worktree、`<change-id>/<YYYY-MM-DD>` 分支、各自 grill/review/archive。

- `evaluation-task-spec`（issue #154）：**C1** 评测任务集组成与任务 schema 扩展（**已归档 2026-08-17**）。任务 schema 加 `scenario`×`difficulty` 双标签、能力层改套件级覆盖矩阵；任务集三来源（A 轨 20–24 存量重打标 + B 轨 12–16 新增 + Verified 50 子集）≈ 82–90；spec delta 落定评估升级完整规格（能力分层修订 + pass^k 改名 + M1–M11 Requirement，指标实现归 C2）。先行解锁 C2–C4。
- `evaluation-metrics`（issue #157）：**C2** 评测指标层实现（**已合入归档 2026-08-17**）。实现 C1 已落 spec 的 M1–M11 Requirement 指标层：pass^k 聚合、cost@pass cache-aware（四档定价 + cache tokens 数据模型）、fault_owner 正交 + 交叉表、配对比较统计（per-task delta/差异 CI/win-rate）、f2p/p2p 保留、小 N 声明、采样显式化 CLI（--seeds/--temperature/--model-version）；清理 spec「实现归 C2」注记。依赖 C1；关联 follow-up #156（C3 前置 Verified 40 fixture）。
- `evaluation-protocol-reporting`（issue #159）：**C3** 运行协议文档 + 结果页披露 + compare 增强（**已归档 2026-08-18**）。T1 协议转正 `docs/benchmark-run-protocol.md`；结果页渲染披露 9 项 + 能力覆盖矩阵（报告元组/污染注记/反作弊/fault_owner 交叉表/$/resolved-task/部分成功档/采样参数/小N/过程效率）；compare HTML 配对段 + 元数据；CLI `--budget-cap`/`--no-cap`/`--preflight`（per-round cap、truncated）；self_check 五门禁；spec 渲染边界注记→已实现。依赖 C2；关联 follow-up #156（C3 前置 Verified 40 fixture）。
- `evaluation-narrative`（issue #160）：**C4** 面试叙事（**已归档 2026-08-17**）。T2 改动清单 + grill 实测落 Q13/W07/FINAL/resume/walkthrough-README 五份面试文档：现状口径修正（23→27、450+→~1997、Claw 重锚为统一 harness 口径）+ 升级叙事段（升级目标 ~90/pass^k/cost@pass/fault_owner/预算，双要素标注「当前已落 37」，标 C1–C3 实现中）。依赖 C3，与 C3 并行。
- `evaluation-btrack-expansion`（issue #164）：**B 轨扩展（follow-up #156 后续项 2，已归档 2026-08-18）**。B 轨 5→12（新增 7 条：CP-1 工具装配链 / CP-2 statechart 新态 / CP-3 结果页 track 分组 / CP-4 SwebenchAdapter 合成回归 / LT-MEM-1 project scope 隔离 / LC-1 memory 注入归属拆分 / BF-1 绝对路径 shell 拦截修复），每任务 issue.md 不给路径 + 确定性 test_command + base 红/gold 绿红绿可复现；manifest coverage 登记 + `validate_coverage` per-track B 扩展；面试叙事数字校准 37→44（34 本地 = 22 A + 12 B）。任务集 37→44。依赖 C1（候选 OQ-B1）；与 `evaluation-verified-subset` 并行（manifest 只改 coverage 段）。

- `evaluation-verified-subset`（issue #163）：**follow-up #156 后续项 1** Verified fixture 生成管线（**已归档 2026-08-18**）。接通 `swebench_subset build-subset` 管线：hf-mirror 实测生成 28 条新 Verified fixture，总计 38 条（10 既有 + 28 新）——flask 池 1 条/seaborn 池 2 条全被既有占用，轻量池上限即 28；difficulty 归一化（真实列值映射，17 easy/16 medium/5 hard）、validate 全过、L3 抽样自检 3 PASS（gitee 系）/github 系未自检（github 本机不可达）、manifest verified 摘要登记 + disclosure 披露段；review-loop Round 2 PASS。依赖 C1；与 `evaluation-btrack-expansion` 并行（manifest 只改 verified 段，错开合入）。

### 第十二批：subagent 编排自由度系列（wayfinder map #170 决策落地）

基于 wayfinder 地图 #170（subagent 编排自由度）已完成的全部决策（R1 调研 / G1 架构方向 / G2 并发护栏 / G3 DSL / G4 汇聚 / G5 预算归因 / G6 benchmark / G7 落地形态）拆解的系列 change。**串行主链 C1→C2→C3→C4→C5**：C1 是地基（队列化并发 + 身份字段），C2（DSL 调度器）依赖 C1 的队列化与身份，C3（结果引用 + 分层汇聚）依赖 C2 的 DAG，C4（预算归因 + 动态 route）依赖 C2 的调度器 + C1 的身份，C5（benchmark replay）依赖 C2 的 spec 可哈希。每 change 独立 worktree、`<change-id>/<YYYY-MM-DD>` 分支、各自 grill/review/archive。

- `subagent-concurrency-queue`（issue #179）：**C1** 并发队列化 + 护栏改造 + 父子身份（**已合入归档 2026-09-14**）。并发护栏从 fail-fast 改为队列化（`max_active=5` + `max_queued_runs=20` + `queue_full`）；并发许可绑执行不绑等待（修父持槽等子自我饥饿）；深度到限撤 spawn 工具（复用 `expose_subagent_tools`）；per-orchestration 累计 spawn 计数（`max_spawns=200`）；run 状态机 `declared→queued→running→terminal`；`SubagentSessionRecord` 增 `parent_run_id`/`workflow_id`/`node_id`/`depth`；`RunSubagent`/`GetSubagentRun` 标 parallelizable。spec delta 已同步进 `openspec/specs/subagents/` + `openspec/specs/multi-agent-collaboration/`（并发护栏 requirement 旧口径「超限一律 reject」已改为「深度 reject / 瞬时并发排队」）。
- `workflow-dsl-scheduler`（issue #181）：**C2** Workflow DSL 调度器（**已合入归档 2026-09-14**）。Workflow DSL 分离式入口（`DeclareWorkflow`/`StartWorkflow`/`GetWorkflow`/`CancelWorkflow` + `RunWorkflow` 便捷语法）+ 4 节点（subagent/aggregate/route/foreach）+ 2 汇合语义（all_required/best_effort，失败不 fail-fast 只在 aggregate 层）+ reducer 声明 + 图级 recursion_limit=25 + DAG 调度器（依赖门控 + 复用 C1 队列作物理并发背闸）+ 4 pattern 降级为 DSL 模板（`run_pattern()` 保留兼容 adapter，新增 workflow_id/workflow_spec_hash/critical_path_s/peak_active/total_cost）。spec delta 已同步进 `openspec/specs/multi-agent-collaboration/`（ADDED 5 + MODIFIED Orchestration Pattern Library）与 `openspec/specs/subagents/`（MODIFIED 深度到限撤 spawn 工具 + 累计 spawn 计数上限）。**C1 遗留前置项已随本 change 落地**：D5 累计 spawn 计数桶由「root_run_id」（无载体）改用既有 `workflow_id`，一个 workflow run 的展开项共享一桶、嵌套 workflow 各自独立成桶。依赖 C1 的队列化 + 身份字段。
- `workflow-result-aggregation`（issue #183）：**C3** 结果聚合（**已合入归档 2026-09-14**）。result_ref 落盘 workflow store（独立 subtree，每 run 独立文件 + 原子写 + 事件日志，失败/取消分支复用 checkpoint 纪律）+ `SubagentRunRecord.to_result_dict` 增 `summary_ref`/`transcript_ref`/`artifact_refs`（成功路径显式触发落盘，artifact_refs 填充时机本 change 定义）+ 树状分层汇聚（模型显式 aggregate 树 + 调度器自动兜底：单 aggregate 直接上游 >10 或总叶子数 >10 时按 fan-in 分组逐层插层，部分显式树只补缺失层）+ 四档 token 预算（leaf 300 / shard 800 / domain 1500 / root 3000，非递减校验，入 `AggregationConfig`）+ 父 agent 永远 bounded envelope（分母 = 逻辑执行单元，blocked/cancelled/budget_exceeded 分列）+ `GetWorkflow` detail 参数 / `ReadWorkflowResult` 分页读 + `WorkflowAggregator` 复用 `Summarizer` 抽象 + 三种结果表示（artifact / scheduler internal / parent envelope）+ bus 降级为非权威（丢消息不影响完成与结果正确性）。spec delta 已同步进 `openspec/specs/multi-agent-collaboration/`（ADDED 4 条）。依赖 C2 的 DAG。
- `workflow-budget-attribution`（issue #185）：**C4**（**已合入归档 2026-09-14**）。workflow 级四维度总预算（max_total_tokens/max_total_cost_usd/max_total_runs/max_wall_time_s，任一维度 `0`=该维度不限、但 `max_total_runs=0` 不解除 C2 结构闸；超限停新 + 取消排队 + drain 在跑 + 根节点 `budget_exceeded`，超限出口不逃出 run、映射为 envelope）+ 成本归因四维账单（`CostLedger` 增 by_workflow/by_node/by_depth/by_edge，归因键随每次 LLM 调用透传；by_depth 口径 = workflow 图距 ≠ spawn_depth；不带归因键时保持既有 by_session/by_phase/by_tool 三维不变）+ 动态 route（`when` 支持 `$ref:<node>:<slot>` 引用上游结果槽，只读已声明/已落盘 slots、不执行模型生成代码，槽缺失走 default + diagnostics）/ 动态 foreach（跨层 source 递归解析：只沿数据边、多入边歧义拒绝、环检测复用 Tarjan SCC；`source_field` 只应用一次；`max_items=0` 展开到图级 run 预算耗尽、按剩余容量截断）。修复 C3 遗留：`_mark_budget_exceeded` 补填 usage，避免被预算杀的 run 在 by_node 里 cost 为 0。spec delta 已同步进 `openspec/specs/multi-agent-collaboration/`（ADDED 4 条 Requirement / 9 个 Scenario）。依赖 C2 调度器 + C1 身份 + C3 result_ref。
- `benchmark-workflow-replay`（issue #187）：**C5**（**已合入归档 2026-09-15**）。benchmark 三模式（`template` 固定 Pattern/DSL 回归 baseline / `dynamic-record` 模型自由生成 workflow + 旁路保存规范化记录（spec + spec_hash + scheduler_version + budget_config + seed/model/temperature）、不打断自由生成 / `dynamic-replay` 不重跑规划模型、离线重放已保存 `workflow_record.json`；CLI `--workflow-mode` + `--workflow-record <run-dir>` 透传 `AsterwyndRunner` 构造参数，`AgentRunner.run` 五参签名不动）+ 编排质量指标（冗余度 = 有用产出 / spawn 总数，消费口径 = `_collect_slots` 打标被消费的 run + terminal 进 root result；图级步数 = 调度器 steps；拒绝降级计数四类 queue_full + 深度撤工具 + spawn 拒绝 + 图级超限并入，`depth_capped_runs` 按构造次数计、`queue_cancelled_runs` 单列不并入）+ workflow 全字段报告（workflow_mode/workflow_spec_hash/scheduler_version/node_count/run_count/peak_active/queue_wait_s/critical_path_s/workflow_cost_usd，无 workflow 任务全为 null、报告不崩；渲染为**独立 section**，主表只加一列 `workflow_mode`）+ 比较口径扩展（完成率 + 总 token + $/resolved-task + wall time + 节点数 + 峰值并发 + 关键路径 + 失败原因；对照臂 `configs/workflow-arm-small-k.yaml`（3/60）vs `workflow-arm-large-n.yaml`（16/24））+ 端到端真实 LLM fan-out 验证（`benchmarks/tasks-e2e/workflow-fanout/`，不进主任务集）。实现要点：`workflow_record.json` 一任务一份、顶层 `workflows` 列表（grill Q1 写法 B）、只记真正 `run()` 过的图、`collection_status` 区分 `ok`/`no_workflow`/`failed`；`AsterwyndRunner` 注入 `CostLedger` 并透传 manager（此前 benchmark 路径没挂 ledger，`workflow_cost_usd` 会是假 0）；`TaskResult`/`AgentRunResult` 成对增字段、`runner.py` 三处重建点改 `dataclasses.replace` 增量写法；编排指标挂 scheduler envelope、spawn/拒绝计数在 `run()` finally 释放桶前快照、`_first_started_scheduler` 跳过 `declared` 态图避免顶掉真实图指标；`dynamic-replay` 不走 verifier、标 `replayed`、在 `_valid_results` 显式排除（不进 pass@k 分母）。spec delta 已同步进 `openspec/specs/benchmark/spec.md`（ADDED 5 条 Requirement / 14 个 Scenario）。依赖 C2 的 spec 可哈希 + C4 的预算归因数据。C5 为串行主链 C1→C2→C3→C4→C5 的终点，完成后 wayfinder #170 的「subagent 编排自由度」目的地全部落地。

## 未实现队列

### 4. `add-minimal-tui-runtime-view`

状态：未实现。

批次：第五批，runtime mode switching 和 slash command framework 已合入基础能力；等待 skills、工具权限模型、工具结果 display policy 等其余依赖稳定后开始。

建议顺序原因：

- TUI 应复用已有 AgentLoop 事件、planning state、streaming、工具结果 display policy、slash command registry、skill runtime、tool permission metadata 和 mode transition，而不是定义另一套运行协议。
- 放在这些基础能力之后，可以一次展示稳定的运行状态、工具调用、planning state、streaming 输出、mode 状态和工具权限信息。

主要交付：

- TUI 命令入口。
- AgentLoop 事件流消费。
- 对话、工具调用、planning state、最终回复、diff/test 摘要和 trace 路径展示。
- 非交互环境 graceful failure 或降级。

### 5. `add-worktree-tool`

状态：未实现。

关联 issue：[#111](https://github.com/Xingkai98/asterwynd/issues/111)（【feature】Agent 侧 worktree 隔离工具，对标 Claude Code EnterWorktree/ExitWorktree）。

批次：第十批，与队列中其他 change（TUI 等）无依赖。

建议顺序原因：

- 新工具面能力，主要影响 tool-system 与 workspace-safety。
- 涉及会话工作目录切换与 WorkspacePolicy root 重绑定，开发前需 `batch-grill-me` 收敛 design.md 中的开放问题（切换承载点、重绑定 API、目录约定、权限元数据、失败回滚、错误码枚举）。

主要交付：

- `EnterWorktree` / `ExitWorktree` 两个 builtin 工具注册进 ToolRegistry。
- 会话工作目录切换 + WorkspacePolicy root 重绑定，worktree 内文件工具路径边界生效。
- 结构化错误码、权限元数据、单测 + 集成测试 + benchmark smoke。
- 实现 PR 合入时给 issue #111 添加完成 comment 并关闭。

### 6. `workflow-budget-unbounded-default`

状态：未实现（已完成设计追问，待用户确认 Open Questions）。

关联 issue：[#196](https://github.com/Xingkai98/asterwynd/issues/196)（【feature】workflow 四维预算默认无上限，显式配置/CLI 才设上限）。

批次：第十五批（C4 `workflow-budget-attribution` 的 follow-up），与队列中其他 change 无依赖。

建议顺序原因：

- C4 的四维预算默认值（200k / 5.0 / 300 / 1800）对 token 消耗大的任务偏紧，12 文件 foreach 体检实测在约 18 万 token 处被 `budget_exceeded` 腰斩（issue #196）。参照 #192（AgentLoop 迭代默认无上限）先例，把「默认不设上限、显式配置才设限」搬到 workflow 预算层。
- 机制本身已在 C4 落地（`0 = 不限` 哨兵 + 真值判定），本 change 只改默认值与其配置落点，但会改 `openspec/specs/multi-agent-collaboration/spec.md` 里写死的默认值表述，属受保护路径，需走完整 OpenSpec change 流程。
- 开发前需 `batch-grill-me` 收敛 design.md 的开放问题（默认值表示法 `0` vs `None`、CLI 是否新增 `--workflow-budget-*` 入参、预算不限后 C2 结构闸是否仍兜底）。

主要交付：

- `WorkflowBudgetConfig` 四字段默认值改为 `0`（不限），`_parse_workflow_budget` 逐字段默认值与 `WorkflowBudget.__init__` 兜底同步。
- 回归测试：默认配置下累积量越过旧默认的图跑完不触发 `budget_exceeded`；显式配置上限/显式 0/显式 null 语义不变；C2 结构闸仍兜底。
- spec delta 同步进 `openspec/specs/multi-agent-collaboration/spec.md`；实现 PR 合入时给 issue #196 添加完成 comment 并关闭。

### 第十四批：Web 移动端断线重连恢复 pending 交互

- `web-reconnect-pending-interaction`（issue #195）：**已合入归档 2026-09-17**。移动端切后台/锁屏导致 WebSocket 断开后，重连同一会话时恢复仍 pending 的提问/审批卡片，用户可直接作答。实现要点：**pending 跨连接存活（D1/D2）**——`WebQuestionHandler`/`WebApprovalHandler` 的槽位从 `(id, future)` 扩为 `_PendingInteraction{id, future, payload}`，保留建立时的 `to_event_data()` 可重放载荷，新增**原子**访问器 `pending_*_payload()`（一次返回 `(id, payload)`，杜绝「读到 id、读不到载荷」的中间态），已 resolve 的立即从可补发集合排除（终态单向推进、已决请求不重放）；断连不再 `fail_pending("websocket disconnected")`。**放弃语义改为显式超时（D2/D6）**——审批 `WebConfig.approval_timeout_seconds` 缺省 **600s**、提问 `question_timeout_seconds` 缺省 300s，均为**总等待时长**（从 pending 建立时起算，断连与保持不影响计时，避免「断连重置计时」无限延长）；超时一律 **fail-closed** 判 `UNAVAILABLE`，绝不放行不可逆操作；`_parse_web_config` 补正整数校验且显式拒绝 YAML `true`（`isinstance(True, int)` 会让它静默退化成 1 秒超时）。**run 事件出口 session 化（D3/D7）**——新增 `ConnectionHandle{send, label, detach}` + `SessionEventChannel`（attach/detach/detach_all/broadcast/send_to），run 事件按 sender 集合广播，drain 循环**永不退出、永远消费 queue**（无界队列防内存堆积，无观察者时丢弃事件），单条连接 send 失败只摘该连接、SHALL NOT break / SHALL NOT cancel `agent_task`；断连检测点唯一（session 级接收任务 `await ws_receive()`，主循环在 `await run_session` 期间不读 socket）；`run_lock` 占用错误改为**定点发送**且带 `code: run_in_progress`（不广播到别的 tab）。**重连补发（D4）**——`bind_pending_interaction_channel` 把顺序钉死为 `session_resumed → session_history → 补发卡片 → workflow 快照`（`session_history` 会整体重绘消息区，补发必须在它之后）；服务端测试用**事件类型序列断言**锁住该不变量。**前端（D5）**——按 `approval_id`/`question_id` 幂等渲染；`renderHistory` 与 `/clear` 两条清空路径都清卡片注册表（否则留下僵尸条目、补发卡片被静默跳过）；`session_history` 重置 `currentAssistantMsg`（否则重连后的 `assistant_delta` 写进已脱离文档的僵尸节点）；提交改为**先判 `ws.readyState` 再改 UI**，未就绪给出可见反馈且卡片保持可提交；run 占用提示改用户可读中文。**终态单调（审阅闭环产出）**——服务端 `_deliver_interaction_receipt`：**被接受**的决定广播给所有连接（Q3 各路径一致），**被拒绝**的回执只回提交者（否则会把已收到终态的胜出方卡片改写成 `unavailable`，用户看到「自己批准过的卡片被判为不可用」而工具其实已执行）；前端 `APPROVAL_TERMINAL_STATUSES` + `card.accepted`/`card.settled` 守卫（`received` 是中间回执，`approved`/`denied`/`unavailable` 落定后不再改写）。**行为变更**：审批从「无超时」变为「缺省 600 秒」，已在 proposal Impact Analysis / README / README_EN / `docs/architecture.md` 显式标注。spec delta 5 个 ADDED + 1 个 MODIFIED Requirement 已同步进 `openspec/changes/archive/2026-09-17-web-reconnect-pending-interaction/` 与 `openspec/specs/web-ui/spec.md`。building 审阅闭环 **4 轮封顶内收敛、最终 verdict = PASS**（reviewer run `review-web-reconnect-pending-interaction-20260917-r4`，report 已绑定 review manifest），四轮共发现 19 个问题（3 中 16 低）全部修复并补回归：R1 修 reset 后连接永久静默、终态非单调、drain 测试变异存活等 10 项；R2 修二进制帧被当断连、`except RuntimeError` 作用域过宽、reset 漏重绑 workflow 图出口等 6 项；R3 修 R2 自身引入的 flaky 断言（等 12ms 瞬态文案）与讲稿行号；R4 用 `capfd` 闭环 RuntimeError 逃逸的覆盖缺口。每条修复均做变异验证（改坏实现 → 测试变红 → 还原），未留假保护。

### 第十三批：多 Agent 运行态可视化（wayfinder #170 的观测面 follow-up）

- `workflow-graph-visualization`（issue #189）：**已合入归档 2026-09-15**。多 Agent 运行态流程图可视化（模型触发 StartWorkflow/RunWorkflow 时自动显示图，节点七档状态高亮 + 边五档状态 + route 控制边单列；桌面横向 DAG / 手机纵向 DAG，pinch 缩放 + pan 平移，复用 720/380 断点）。实现要点：**数据面**——scheduler 新增独立 `workflow_graph_snapshot()`（`scheduler.py:2199-2249`），基于运行期 `ExecutionPlan`（含自动插层 + foreach 展开）输出完整 nodes + edges + 每节点/每边 status，**不动** `_envelope`/`parent_envelope` 父 Agent 数据契约（逐字节未变，回归 `test_snapshot_does_not_drift_envelope_contract`）；节点投影走显式挑字段（`_graph_node_projection`，不复用 `NodeState.to_dict()`，排除 `subagent_ids`/`slots`/`raw`/`error`/`verdict`，`summary` 截断 400），边界白名单断言严格（`SNAPSHOT_NODE_KEYS`/`SNAPSHOT_EDGE_KEYS`）。**状态语义**——节点七档 = `_SNAPSHOT_TERMINAL_STATUSES` + `started`/`pending`，与 scheduler 终态集合对齐；边五档 inactive/ready/active/passed/blocked（`_edge_status` 优先级链），`passed` 是 per-edge 记账、加在三个消费循环的 `_mark_consumed` **旁**（`_mark_consumed` 本体未改 → `_consumed_run_ids` 基数与 C5 有用产出口径逐位不变）；route 控制边 `kind: "control"` 单列、只高亮 `targets` 实际选中出口、容忍 `_reset_subtree` 清空 targets 的瞬时态；channel 用线型区分（summary/result_ref 实线、artifact 虚线、bus 点线）。**事件通道**——触发点在 `scheduler.run()` 的 `_record_event("workflow_started")` hook（**不是**工具层：工具只持有 `SubAgentManager` 拿不到 session sink；`DeclareWorkflow` 只注册不 `run()` 天然零事件），六处节点迁移点推快照（`_dispatch`/`_run_node` 终态/`run()` 启动收尾/`_mark_budget_stop`/`_mark_graph_recursion_exceeded`/`cancel()`）；出口是 session 级、跨 run 存活的 manager sink → `web/session.py` forwarder → WebSocket（`workflow_started`/`workflow_snapshot`），按 100ms 时间窗按 workflow 合并、终态立即发；重连经 `build_workflow_resume_payloads` 按 `started` property 过滤 declared、补发 running + 最近 5 张终态，`bind_workflow_graph_channel` **先补发再 rebind**；快照推送失败（ws 已断）不影响 workflow 执行状态或节点终态（三层隔离测试）。**前端**——`#workflow-tab`/`#workflow-view` 在 debug 门禁外，零依赖 SVG 自绘（`workflow_graph.js` 分层布局），`chat.js` 由 `workflow_started` 自动跳转；规模分级 <50 全展开 / 50–200 折叠 foreach（组状态聚合，点击展开）+ `__auto_agg__` 自动插层 / >200 不按 `nodes.length` 判断而只看 `status === 'graph_recursion_exceeded'` 且超限不画图（声明期被拒无 scheduler 无图）。**跨端**——>720 横向 / <720 纵向 DAG（`graphOrientation`），pointer events + viewBox transform 实现 pinch 缩放 + pan 平移，复用既有 720/380 断点 + safe-area，不加新断点；CI 加装 Playwright chromium 真跑浏览器 smoke（`test_workflow_graph_browser.py` 此前恒 skip）。spec delta 5 个 ADDED Requirement 已同步进 `openspec/specs/web-ui/spec.md:475-544`（相对 delta 有三处经 grill Q5/Q10/Q11 确认的口径补强：快照显式挑字段、session 级跨 run 事件出口 + 100ms 合并、推送失败不影响执行）。依赖 C2 的 ExecutionPlan 运行期图数据 + C5 的观测口径。building 审阅闭环 3 轮封顶内收敛、最终 verdict = **PASS**（reviewer run `review-workflow-graph-visualization-20260915-r3`，report 已绑定 review manifest），逐轮修掉 4 个缺陷：折叠组点击无法展开、折叠组聚合状态词表外、pan-after-pinch 手势 capture 未按指针记账、`cancel()` 把「只声明未启动」的图误标为已运行（C5 观测回归）。
