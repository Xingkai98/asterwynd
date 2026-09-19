# Tasks: workflow 终态与因由如实表达（workflow-terminal-honesty）

> **开发前必做**：`batch-grill-me` 设计追问（独立零记忆 subagent，AGENTS.md #95 机械强制）。
> grill 产出后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复；答复记录进
> `reviews/grill-design.md` 的 `## User Confirmation`。收到答复前**不得写实现代码**。

## 0. 立项（主 session 完成）

- [x] 0.1 业界调研（Airflow `all_tasks_deadlocked`→FAILED / Prefect 子任务失败→FAILED / Argo `Omitted` 不使 workflow 失败）并写进 `design.md`/`proposal.md` 的 `## Reference Implementation Research`
- [x] 0.2 三个 bug（#217 / #218 / #220）确定性复现，证据写进 issue
- [x] 0.3 proposal / design / tasks / spec delta
- [x] 0.4 backlog 登记 + `workflow-events.jsonl` 结构化事件
- [x] 0.5 `openspec validate --strict` + artifact checker 通过
- [ ] 0.6 **grill**（独立 subagent）→ 停轮收集用户答复 → 回填 `## User Confirmation`

## 0.7 立项修正（grill 答复与必修项落地，主 session）

- [x] 0.7.1 回填 `reviews/grill-design.md` 的 `## User Confirmation`（Q1–Q5 五条用户答复）
- [x] 0.7.2 修正 spec delta 的 MODIFIED 标题（逐字匹配目标 spec 既有 Requirement 名）；`回边重跑不得清空本次派发的发起者` 改 `## ADDED`
- [x] 0.7.3 修正 `diagnosis.md` 的 #220 复现 spec（`default` 必须是 `body`），加说明
- [x] 0.7.4 修正 D5 表述（真实三副本：`_SNAPSHOT_TERMINAL_STATUSES` / `workflow.js` 数组 / `workflow_graph.js` 的 `isGraphTerminal()`；无 scheduler 侧 `TERMINAL_STATUSES`）
- [x] 0.7.5 design 记录：D2 口径澄清（节点数 ≠ 快照 `completed`）、D4 改方案 D、D3 加后端+前端同改、D6 补配色门槛
- [x] 0.7.6 `proposal.md` 更新范围（Q4 扩大前端面）与 Impact Analysis

## 1. 复现与回归测试（TDD：先写测试，确认红）

- [ ] 1.1 **#217**：零节点完成的图（回边 `required=true` 死锁）→ 断言图级 status **不是** `completed`
- [ ] 1.2 **#218 形态 A**：`max_routes` 撞线 → 断言被牵连节点 `reason` **含**闸门信息（`max_routes` / 上限值），**不含**无信息量的兜底文案
- [ ] 1.3 **#218 形态 B**：无图级闸门的死锁 → 断言节点 `reason` 说明「入边互等」，而非「workflow ended before...」
- [ ] 1.4 **#220**：回边为数据边（**`default` 指向回边分支 `body`**，见 `diagnosis.md`）→ 断言 `_reset_subtree(body)` **不**清空 `cycle_gate`（`targets`/`status`/`summary` 保持）
- [ ] 1.5 **方案 D 组合回归**：同一张回边图 → 断言被派发节点 `status != "skipped"` 且 `reason` **不含** `route did not select this branch`（与 1.4 一起断言；只断 1.4 会让「仅豁免」的中间态漏过）

## 2. 实现：图级终态四档（D1/D2）

- [ ] 2.1 `_terminal_converged_status()` 扩为四档（`completed_with_failures` / `completed` / `failed` / `stalled`），判据按 D1 的优先级表
- [ ] 2.2 `completed_count` 口径 = `status == "completed"` 的节点数（**不含** `skipped`）
- [ ] 2.3 确认调用点仍在 `if self._budget_stop / else` 的 else 分支内（预算优先，不覆盖 `budget_exceeded`/`cancelled`/`graph_recursion_exceeded`）
- [ ] 2.4 四档边界矩阵测试：`completed>0, failed=0`→`completed`；`completed>0, failed>0`→`completed_with_failures`；`completed=0, failed>0`→`failed`；`completed=0, failed=0`→`stalled`

## 3. 实现：节点因由分档（D3）

- [ ] 3.1 `_resolve_pending_status()` 按真实成因分三档（图级闸门穿透 / 入边互等 / 其它兜底）
- [ ] 3.2 图级闸门穿透：注入 `diagnostics.reason` + `diagnostics.message`（按 `_SUMMARY_LIMIT` 截断）
- [ ] 3.3 入边互等：列出未就绪的上游 id，文案说明「永远未就绪」
- [ ] 3.4 确认 `state.reason` 本体语义不变（它是 `_envelope` 字段；截断只在投影层）

## 4. 实现：方案 D（D4 = 发起者豁免 + 选中判据修正）

- [ ] 4.1 `_reset_subtree` 增加 `origin` 参数，递归时跳过 `origin`
- [ ] 4.2 **3 处**调用点全部透传 origin（`_on_node_finished` `:1509` / 自身递归 `:1535` / `_execute_route` 派发循环 `:1626`）——**只改 `_on_node_finished` 那处不会有任何效果**，`:1626` 是生效关键
- [ ] 4.3 **`_is_skipped` 增加条件 2**：控制源 `completed` 时 `node_id in source.targets` → return False（只读既有字段，不引入新记账）
- [ ] 4.4 **不做**「先 reset 再 `activations += 1`」的顺序调整（实测无效，且在 4.1+4.3 之上会反向破坏 #220 修复）
- [ ] 4.5 **G11 回归红线**：确认仍然清 `reason`/`error`/`summary`/`finished_at`/`status`/`activations`/`verdict`/`targets`（只加豁免，不减清理项）
- [ ] 4.6 跑 G11 既有回归（陈旧因由 / 负耗时），全绿

## 5. 实现：契约同步与用户可见性（D5/D6/Q4/Q5）

- [ ] 5.1 `_SNAPSHOT_TERMINAL_STATUSES`（`scheduler.py:111`）加 `stalled`
- [ ] 5.2 前端 `web/static/workflow.js` 的 `TERMINAL_STATUSES` 数组加 `stalled`
- [ ] 5.3 前端 `web/static/workflow_graph.js` 的 `isGraphTerminal()` 加 `stalled`
- [ ] 5.4 **三副本等价断言**（断言三个集合相等，而非各自「包含 stalled」）——防未来再次漂移；副本 3 走正则源文本抽取（既有范式 `test_workflow_graph_ux_js.py:444-455`），**不新增导出**
- [ ] 5.5 前端 `stalled` 配色（深琥珀/暗橙，到每个既有图级档 RGB 距离 ≥ 100）+ tab 徽标文案「停滞（无节点完成）」+ 图例说明
- [ ] 5.6 前端测试：`stalled` 的配色/文案与 `completed`/`budget_exceeded` 都可分辨 + 配色距离门槛断言
- [ ] 5.7 **Q4 前端因由优先级**：`explainNode()` 对 `blocked` 让具体因由（含闸门信息 / 「入边互等」）优先于泛化文案（`GRAPH_STOP_REASONS` / 上游穿透）
- [ ] 5.8 **Q4 前端验收测试**：`max_routes` 快照 → 用户可见文案含 `max_routes`；`stalled` 死锁快照 → 含「入边互等」而非「被上游 X 挡住」
- [ ] 5.9 **Q5 消费方清单核对**：确认 `stalled` 被所有图级 status 消费方按「非成功」处理（`web/session.py:_is_terminal_snapshot` / 前端 tab 淘汰 / `GetWorkflow` / benchmark），并在 spec 正文写明语义

## 6. 验证与收尾

- [ ] 6.1 变异验证：每个新测试都能被「改坏实现」杀死（至少覆盖四档判据、因由三档、origin 豁免、**`_is_skipped` 条件 2**、三副本同步、**前端 `explainNode()` 优先级**）
- [ ] 6.2 `tests/agent/subagent/` + `tests/web_tests/` 全量回归
- [ ] 6.3 全量 `uv run pytest -q`
- [ ] 6.4 **同步 current spec**：把 spec delta（MODIFIED 四条 Requirement：图级终态区分有失败 / 节点异常态语义表达 / 未选中分支状态 skipped / —— + ADDED 一条：回边重跑不得清空本次派发的发起者）合入 `openspec/specs/web-ui/spec.md`，并写受保护路径的结构化解释事件到 `workflow-events.jsonl`
- [ ] 6.5 `/review-loop` 独立审阅闭环（AGENTS.md #90 机械强制，PASS 或 3 轮封顶）
- [ ] 6.6 归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-terminal-honesty/` + backlog 移除
- [ ] 6.7 `openspec validate --all --strict` + `check_openspec_artifacts.py` 通过
- [ ] 6.8 建 PR（含归档收尾）；合入后 comment + close #217 / #218 / #220
- [ ] 6.9 文档影响检查：扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及图级状态词的段落

## 7. 另立（不在本 change 范围）

- [ ] 7.1 #219：`DeclareWorkflow` 循环契约提示 + 声明期校验（另立 change）
