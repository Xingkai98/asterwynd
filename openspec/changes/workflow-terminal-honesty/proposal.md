# Proposal: workflow 终态与因由如实表达（workflow-terminal-honesty）

## Change Type

- primary: feature
- secondary:
  - bugfix

> 为何是 `feature` 而非 `bugfix`：新增图级终态档 `stalled` 是**对外契约变更**（状态词表扩容），
> 需要设计决策与独立 grill；三个 bug 是它的**触发证据与验收面**，故同时声明 `bugfix`
> 并维护 `diagnosis.md`。

## Why

用户在 session `0a94250da7bf` 实测时发现：**图不但会骗人，还会指错排查方向**。

三条实测证据（均为确定性复现，非竞态）：

1. **图级 status 谎报**（issue #217）：一张**一个节点都没跑**的图（三节点全 `blocked`、`runs=0`）在 UI 上显示「**已完成**」。
2. **节点因由是假话**（issue #218）：`max_routes` 撞线时，节点因由写 `workflow ended before the node became ready`（读起来像被动受牵连、无解），真因（自己撞了路由上限）只在图级 `diagnostics` 里。
3. **回边重跑会清空发起者状态**（issue #220）：回边为数据边时，`_reset_subtree` 沿回边递归走回 route 自身，把 route 刚写的 `status`/`targets`/`summary` 清空 → 成功的 route 报 `blocked`、选中的控制边显示 `inactive`、详情面板「命中出口」显示 `—`。

三者共同指向一个命题：**图的终态与因由必须如实反映「实际发生了什么」**。用户原话是「尽可能对整个 workflow 的流程有更多的掌控感，能看到每个节点运行过程中的情况，如果报错了，为什么报错」——当图说「完成了」而实际什么都没跑、或说「工作流提前结束了」而实际是自己撞了上限时，这条掌控感是负的（**答错比答不出更糟**）。

## What Changes

**A. 图级终态档位修正（#217）**

`completed` 的判据补前置条件：**至少一个节点 `completed`**。零节点成功的收敛不再报 `completed`。

业界先例（见 `## Reference Implementation Research`）：
- Airflow：无 runnable task 且存在未完成任务 → DAG run 标 **FAILED**，原因 `all_tasks_deadlocked`
- Prefect：任一 task/subflow 失败 → flow run 标 **FAILED**

两家的共同口径是「**没有任何成功 = 失败**」，而不是「没有失败 = 成功」。

**新增图级档 `stalled`**（停滞）：图收敛时**零节点 `completed`、零节点 `failed`、且存在 `blocked` 节点** → `stalled`。
- 与 `failed` 分开：`failed` 表示「有节点执行失败」，`stalled` 表示「图根本没跑起来」（死锁 / 全部被挡），二者对用户的行动指引不同
- 与 `completed_with_failures` 对称：后者是「跑了但有失败」，`stalled` 是「压根没跑」

**B. 节点因由如实（#218）**

兜底因由 `workflow ended before the node became ready` 不再吞掉真实原因。两种触发形态都要给准：

- **有图级闸门**（`max_routes` / `recursion_limit` / `max_nodes` / `max_runs`）：穿透 `diagnostics.reason` 到被牵连节点，例如 `图级闸门 max_routes 触发（route 'cycle_gate' 超过上限 2），本节点未派发`
- **无图级闸门**（入边互相等待的死锁）：说明是「入边互相等待，永远不就绪」而非「工作流提前结束」

**C. 回边重跑不清空发起者（#220）**

`_reset_subtree` 的递归不得沿回边走回**本次派发的发起者**。发起者是刚刚完成、正在写结果的那个节点；清空它会让「成功」被改写成「未派发」。

## Non-Goals

- **不修空转环本身**：用户那张图（`body` 为 `collect` 聚合、唯一入参来自不产数据的 route）在语义上**就该**撞 `max_routes`——环里没有任何东西在变化。本 change 只让系统**说清楚**这件事，不改它的行为。
- **不做循环契约的模型面提示**（#219）：`DeclareWorkflow` 描述补 `max_routes` 默认值 / 回边方向 / 环内产出要求、以及声明期校验，属于**工具面**改动，另立 change。
- **不改 `max_routes` 的语义**（节点级、跨轮累加、不重置）：那是循环契约的一部分，随 #219 一并讨论。
- **不引入节点级重试 / 运行内事件流 / 搜索定位**：见 #201–#205。

## Impact Analysis

**代码影响**

| 文件 | 改动 | 风险 |
|---|---|---|
| `agent/subagent/scheduler.py` | ① `_terminal_converged_status()` 补 `completed > 0` 前置 + `stalled` 档<br>② `_resolve_pending_status()` 的兜底因由穿透图级 diagnostics<br>③ `_reset_subtree()` 增加「发起者豁免」 | **高**（收敛判据 + 状态机 + G11 回归面） |
| `web/static/workflow_graph.js` | 图级 `stalled` 的配色/文案；前端 `TERMINAL_STATUSES` 副本同步 | 中 |
| `openspec/specs/web-ui/spec.md` | 图级终态 Requirement（MODIFIED）、节点因由 Requirement | — |

**契约影响（对外，须谨慎）**

- **图级 status 词表新增 `stalled`**：`GetWorkflow`、benchmark、前端 tab 徽标、tab 淘汰池（`TERMINAL_STATUSES` **两个副本**）都要同步。
  - **漏同步的后果**：该图被当成 running → 永不淘汰 → 每次 ws 重连都补发（`_SNAPSHOT_TERMINAL_STATUSES` 同类坑）。
- **`completed` 的含义收窄**：「零节点成功」的图不再报 `completed`。既有断言该语义的测试需评估。
- `_reset_subtree` 语义变更：G11（清陈旧 `reason`/`error`/`summary`/`finished_at`）的回归必须保持。

**测试影响**

- 三个 bug 各需**确定性回归测试**（本 change 的复现脚本已可作基础）
- 收敛判据的边界：`completed>0` + 有 failed → `completed_with_failures`；`completed>0` + 无 failed → `completed`；`completed==0` + failed>0 → `failed`；`completed==0` + failed==0 + blocked>0 → `stalled`
- 既有 `tests/agent/subagent/` 全量回归

**文档影响**

- `openspec/specs/web-ui/spec.md`（图级终态 + 节点因由）
- `docs/openspec-change-backlog.md`（本 change 登记 + 完成后移除）
- 关键词扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及图级状态词的段落

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 走 grill 的非平凡 change；新增**对外状态词**（图级终态档）属契约级改动，且涉及「工作流终态语义」这一业界有明确先例的领域，必须对标。

- research questions:
  1. 业界工作流引擎在「零任务成功且全部被挡/死锁」时报什么终态？
  2. 它们是否区分「有任务失败」与「根本没跑起来」？
  3. 节点级因由如何表达「因图级闸门而未执行」？

- findings:
  - **Airflow**（`airflow/models/dagrun.py` 的 `DagRun.update_state()`）：当**存在未完成任务**且**没有任何 runnable task** 时，DAG run 标为 **FAILED**，reason `all_tasks_deadlocked`；日志 `"Deadlock; marking run %s failed"`。其 task 终态集合含 `SUCCESS` / `FAILED` / `SKIPPED` / `UPSTREAM_FAILED`——**`UPSTREAM_FAILED` 是独立档**，与 `FAILED` 区分（前者是「被上游连累」，后者是「自己失败」）。AIRFLOW-1420/1473 专门修过「上游失败/跳过导致的 deadlock 误报」。
  - **Prefect**：flow run 的终态由内部决定——任一 task/subflow **failed** → flow run **FAILED**；任一 **cancelled** → **CANCELLED**；返回 `None`/无值时按子任务结果推导。口径是「**子任务没成功 = 流程没成功**」。
  - **Argo Workflows**：node phase 含 `Succeeded` / `Skipped` / `Failed` / `Error` / **`Omitted`**（依赖被跳过而未执行）；但 workflow 级 phase 只看 **entrypoint node** 的成败（`WorkflowSucceeded` / `WorkflowFailed` / `WorkflowError`）。`Omitted` 不使 workflow 失败——与本项目的 `skipped` 口径一致。Argo PR #15841 修过一个同类缺口：`Skipped`/`Omitted` 的节点**不产出 output**，下游引用时解析失败导致**无限 requeue**——即「未执行节点的产出语义」在业界也是踩过坑的地方。
  - **Temporal** 未提供对应先例：其「blocked/awaiting」是非终态的 Running 条件（靠 Event History 诊断），终态由异常/取消/终止决定，无「零节点执行」这一档。**不采纳**其「保持 Running」口径——本项目是有限 DAG、收敛由调度器判定，没有「等外部信号」这一说，保持 Running 只会让用户永远等下去。

- design impact:
  - **档位设计采纳 Airflow + Prefect 的「无成功即失败」方向**，但**不直接复用 `failed`**：本项目的 `failed` 已被「节点执行失败」占用（且 `completed_with_failures` 依赖它），混用会让「有节点失败」与「图没跑起来」不可分辨。故新增独立档 `stalled`，与既有 `completed_with_failures` 形成对称（跑了但有失败 / 压根没跑）。
  - **节点级因由的分档参考 Airflow 的 `UPSTREAM_FAILED`**：本项目已有同构设计（`skipped` vs `blocked` 的「未选中」/「被连累」区分，见 `openspec/specs/web-ui/spec.md` 的 `workflow 未选中分支状态（skipped）` Requirement）。本 change 沿用同一思路：**因由必须指向真实成因**，不用一句兜底文案覆盖多种成因。
  - **`TERMINAL_STATUSES` 双副本的风险**在 Argo 的 `Omitted` 相关 issue 里有同构教训（新档未同步到消费方 → 行为不一致），本 change 的 Impact Analysis 已把「两个副本同步」列为硬要求。
  - 本地参考仓库不可用（工作区无 `.dev/reference-repos.txt`），故本条 findings 全部来自业界调研（官方文档/源码/issue），未做本地参考仓库对比。
