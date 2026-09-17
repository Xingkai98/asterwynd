# Proposal: Workflow 流程图可视化体验增强（enhance-workflow-graph-ux）

关联跟踪 issue：[#197](https://github.com/Xingkai98/asterwynd/issues/197)。依赖 C7 `workflow-graph-visualization`（#189，已合入归档）：图已经能画出来，本 change 解决「画出来了但看不懂、看不了细节」。

## Change Type

- primary: feature
- secondary:
  - web-ui
  - observability

## Why

`workflow-graph-visualization`（#190）已合入，模型触发 workflow 时会自动弹出流程图（节点七档状态 + 边五档状态 + 桌面横向/手机纵向 DAG + pinch/pan）。但用户手机端跑「代码体检」等复杂任务的实测暴露了 4 类**展示体验缺口**——图有了，但**看不明白、看不了细节**：

1. **无图例**：节点代号 `S`/`F`/`R`/`A`、7 种节点状态色、5 档边状态与线型/箭头语义，图上**没有任何文字说明**。用户对着色块猜。
2. **异常态语义混淆**：`failed`（红，节点自身失败）/ `blocked`（黄，被上游或预算挡住没跑）/ `budget_exceeded`（橙，预算超限停下）三种「非成功态」挤在一张图里只有色块。实测「12 文件 foreach 体检」触发预算超限后，图上同时出现 3 红 2 黄 + 橙 chip，用户**把 blocked 误当 failed**，也看不懂 budget exceeded 是什么。
3. **节点详情缺失（最大痛点）**：点节点只有 hover `<title>` 的 200 字摘要，**非折叠组节点点击完全无效**。用户看不到单个节点的 task / 完整产出 / 对话 transcript——数据其实在后端（`SubAgentManager.inspect_transcript()` 能读每个 run 的 messages，前端没接）。
4. **多图 / foreach 可读性差**：
   - 多图 tab 只用 `truncate(goal, 24)` + 状态词，看不出「第几次 run / 什么时候起 / 为什么起 / 结果差异」。实测同一 session 里模型起了 3 次 workflow，用户**「为什么有三张图」分不清**。
   - foreach 并行容器只显示一个孤立节点，里面 N 个并行项**完全看不见**（`N items` 只在 ≥50 节点折叠时才显示）。
   - 统计行数字对不上：`11 edges` 但只画 6 条线（同一对节点多条边几何重合）。

这不是锦上添花：图是用户理解「模型到底在并行干什么、卡在哪、为什么停」的唯一窗口，看不懂等于观测能力没落地。

## What Changes

四块增强，**前端增强优先**；只有「图上看不到的语义」才做**加法式**后端补字段（不动物理契约）：

- **A. 图例（legend）**：新增常驻可折叠图例条（节点类型 4 类 + 节点状态 7 档 + 边状态 5 档 + 线型/箭头语义），桌面常驻、手机默认折叠为「图例 ▾」；元素级 hover/tap 提示升级为同一套词汇（`<title>` 带状态文字与因由）。
- **B. 异常态语义与因果**：
  - 异常节点在图上以「状态词 + 前缀符号」表达（`✕ failed` / `⊘ blocked` / `⛔ budget`），在既有**左侧色带（形状编码）**之上再加一层，不靠颜色单独承载语义。
  - **节点 `reason` 进快照**（bounded 截断）——这是「为什么是这个状态」的权威文本（blocked 的「workflow ended before the node became ready」、预算的「budget exceeded (tokens)」、foreach 的「3/12 foreach items did not complete」），今天**已有字段但没进快照**。
  - **因果链在前端纯函数层推导**：blocked 节点沿入边向上找第一个 failed/cancelled 源 → 「被上游 `<X>` 失败挡住」；budget_exceeded → 「预算超限（维度）」；failed → 自身 reason。
- **C. 节点详情面板**：点节点 → 打开详情（桌面右侧抽屉 / 手机底部抽屉，同 DOM 由 720 断点切换），显示 node id / kind / status / reason / task / runs / 起止与耗时 / summary / **完整 transcript（懒加载）**。数据来自**新增只读接口** `GET /api/sessions/{session_id}/workflows/{workflow_id}/nodes/{node_id}/transcript`，后端按 `workflow_id` + `node_id` 找 `SubagentSessionRecord`（字段已存在）后**复用 `inspect_transcript()`**，bounded、只读、不调 LLM。
- **D. 多图与 foreach 可读性**：
  - 多图 tab 显示 `#序号 + goal + 状态 + 时间/耗时`（需图级 `started_at`/`finished_at` 进快照，scheduler 已有这两个字段）。
  - foreach 容器**常显** `N items · 完成 M`（`N` 来自既有 `items`；`M` 需新增 bounded 计数 `items_completed`/`items_failed`）。
  - 统计行改为如实反映「实际绘制的边数」，并对同一对节点的**并行边做垂直偏移**，让 `11 edges` 与可见线条数一致。

- **E. 后端语义适配（用户裁决纳入：目标就是前端易用性，后端该适配就适配）**——实跑代码发现两个**上游遗留的真实语义缺口**，正好落在本 change 的核心命题（异常态语义）上：
  1. **新增第 8 档节点状态 `skipped`（未选中）**：route 未选中的分支今天被错标成 `blocked`（黄），与「被上游失败连累」混为一谈。实跑证据：正常完成走 `APPROVED` 时，`DEFAULT` 分支节点状态是 `blocked`。新增 `skipped` 档（复用既有 `activations` 控制激活信号判定，不引入新记账），前端以冷灰蓝 + 虚框 + `—` 与 `blocked` 明显区分。业界先例：Airflow `skipped`、Argo `Omitted`。
  2. **补 route 数据入边的 `passed` 记账**：route 读上游走 `_route_verdict`，不经过任何 `_mark_consumed` 调用点，因此 `a→gate` 这类边永远落到 `inactive`（灰）。在 `_route_verdict` 处**旁加** per-edge 记账（与 #190 决策 7 同构，`_mark_consumed` 本体不改）。

**约束**：`workflow_graph_snapshot()` 新字段**纯加法且 bounded**；`_envelope`/`parent_envelope` **结构**不变（唯一变化是节点 `status` 取值集合新增 `skipped`，消费方需容忍）；复用既有 720/380 断点与零依赖 vanilla JS + SVG 自绘，不引入前端框架；不做图历史回放、不做动画过渡、不做 Web 端编排画布（沿用 #190 的 Non-Goals）。

## Capabilities

### New Capabilities

无新能力域；在既有 `web-ui` + `observability` 能力域上深化。

### Modified Capabilities

- `web-ui`: workflow 视图从「能画出节点与边」演进为「可读的观测面板」——新增图例、异常态因果表达、节点详情面板（含 transcript 只读接口）、多图 tab 元信息、foreach 并行计数与边统计口径、第 8 档 `skipped` 状态的展示。
- `observability`: `workflow_graph_snapshot()` 观测面补齐三处**加法**字段（节点 `reason`、图级 `started_at`/`finished_at`、foreach `items_completed`/`items_failed`），既有字段语义不变。
- `multi-agent-collaboration`（或 `subagents`）：节点状态语义扩展——未选中的 route 分支记 `skipped` 而非 `blocked`；route 数据入边补消费记账。

## Impact Analysis

- **能力域**: `web-ui`（图例 + 详情面板 + tab/foreach/边统计可读性）、`observability`（快照加法字段）。
- **代码**:
  - `web/static/workflow_graph.js`（纯函数层：图例模型、因果推导、并行边偏移、边统计、tab 元信息格式化）；
  - `web/static/workflow.js`（渲染层：图例条、异常态符号、详情面板开合、tab 元信息、foreach 计数渲染）；
  - `web/static/index.html` + `web/static/style.css`（图例条与详情抽屉 DOM/样式，复用 720 断点）；
  - `web/server.py`（新增只读 transcript 路由）+ `web/session.py`（按 workflow_id/node_id 解析 subagent 并复用 `inspect_transcript`）；
  - `agent/subagent/scheduler.py`（快照**加法**字段：节点 `reason`、图级 `started_at`/`finished_at`、foreach `items_completed`/`items_failed`；`_envelope`/`parent_envelope` 一行不改）。
- **测试**: 前端纯函数 node+vm 单测（图例/因果/边统计/并行偏移/tab 元信息/详情状态机）；后端快照新增字段 + bounded + 白名单更新测试；transcript 路由测试（正常 / 无 subagent 节点 / 未知 node / 未知 session / bounded）；Playwright 浏览器 smoke 覆盖「点节点开详情」；回归「`_envelope`/`parent_envelope` 结构逐字节不变」。
- **文档**: `docs/openspec-change-backlog.md`（登记 change）；issue #197 跟踪；收尾同步 `openspec/specs/web-ui/spec.md`。
- **流程（process）**: 独立 change，走 OpenSpec 全套（propose → grill → 独立 worktree TDD → review-loop → archive）；分支 `<change-id>/2026-09-17`。
- **风险面**: 快照新增字段会触碰既有白名单契约测试（`SNAPSHOT_NODE_KEYS`）——必须同步更新且证明 `_envelope` 未漂移；transcript 接口暴露运行内容，需保持与 Chat 视图同一信任级并 bounded。
