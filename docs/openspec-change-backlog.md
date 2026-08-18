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

