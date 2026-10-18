# Tasks: 原地废弃未实现的 `add-minimal-tui-runtime-view` proposal

> **结算次序（收尾）**：最终内容提交（含 `tasks.md` 结算与 backlog 移除）→ 归档 move 提交
> → 用归档目录名重建 `reviews/grill-design.md` 的 `stage=grill` manifest → **单独提交证据**。
> manifest 的 `head_sha` 必须指向最后一个非证据提交；`reviews/`、`workflow-events.jsonl`、
> `archive/**` 之外的内容不得落在 `head_sha` 之后。closeout 类任务（合入后动作）标
> `(post-merge)`。

## 0. 设计追问

- [x] 0.1 用 `grilling`（独立零记忆子代理）产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions、0 Open Questions、`## User Confirmation` 存在）。
- [x] 0.2 确认：目录字节不变、不伪造证据、backlog/ADR/规格同步、未来处置路径。

## 1. 记录

- [x] 1.1 新增 `docs/adr/ADR-0006-retire-minimal-tui-runtime-view-proposal.md`（决定、原因、删除/标记实测失败证据、sha 97b0370 + 取回命令、Revisit Conditions）。
- [x] 1.2 `docs/openspec-change-backlog.md` 移除 TUI 三处引用（第五批、第十七批「已知未收尾」、`### 3.` 小节），登记本 change。
- [x] 1.3 `docs/development-guide.md` 阶段 A 已知红条目改为「已处置：原地废弃 + ADR-0006」。

## 2. 规格

- [x] 2.1 `specs/dev-workflow-gate/spec.md` delta：MODIFIED「已知红如实记录且不放宽判据」+「原地废弃不伪造证据」Scenario。
- [x] 2.2 把 delta 施加进 current spec（`openspec/specs/dev-workflow-gate/spec.md`），写 `current_spec_synced` 事件；strict validate 通过。
- [ ] 2.3 归档 move 前写 `change_archived` 事件（`artifact-path=openspec/changes/archive/2026-10-18-retire-tui-proposal`）；归档后复跑裸 checker 确认受保护路径门通过。

## 3. 验证

- [x] 3.1 临时分支实测 marker：`WITHDRAWN` → witnessloop `check` 3 项 finding（缺 reviews / manifest / grill manifest）；结论写入 ADR 与 PR 描述，工作树不加标记。
- [x] 3.2 裸跑 checker → EXIT=0。
- [x] 3.3 `--base-ref origin/master --require-base` → EXIT=0。
- [x] 3.4 `--check-archived` → EXIT=0。
- [x] 3.5 OpenSpec strict validate → 30 passed（本 change 活跃时）/ 29（归档后）。
- [ ] 3.6 归档后 witnessloop `check` → 通过 ✓（grill manifest 落盘后复验；未完成前不得勾选）。
- [ ] 3.7 全仓 grep：TUI id 仅剩历史归档、ADR-0006、本 change 自身、backlog 退役条目与「已废弃」过去时说明（未完成前不得勾选）。

## 4. 收尾（合入后）

- [ ] (post-merge) 4.1 用 `--merge` 合入 PR；合入后确认 active TUI 目录仍在、backlog 干净、本地 `master` 已快进。
- [ ] (post-merge) 4.2 给 issue #319 添加完成说明 comment 并关闭。
