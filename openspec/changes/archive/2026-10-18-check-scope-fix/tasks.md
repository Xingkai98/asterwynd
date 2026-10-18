# Tasks: 收窄「闭环出口」检查到本 PR 新归档（默认 base 解析修复）

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → 本地复验 → **结算 `tasks.md`（未勾且未标 `(post-merge)` 必须为 0）** → **用归档目录名**
> 重建 witnessloop 三份 manifest → 机械复核 → 发起 PR。PR 创建与合入不写回 `tasks.md`；
> closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling`（独立零记忆子代理）执行设计追问，产出 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与 `## User Confirmation` 无条件存在）。
- [x] 0.2 逐项确认：merge-base 语义、显式两点语义、gate 判据不放宽、七条测试、规格/文档影响、TUI 退役不在本 PR。
- [x] 0.3 设计阶段对抗闭环 → `reviews/grill-adversarial.md`，按批次模型收敛到 PASS。
- [x] 0.4 停轮检查：无 Open Question 或已确认；设计环出口 PASS。
- [x] 0.5 回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 测试（TDD）

- [x] 1.1 七条测试已就位：helper 单元、裸跑不追溯、新建归档仍红、显式 base 优先、受保护路径接线、落后分支不误红、空 `--base-ref` 不跳过检查。
- [x] 1.2 记录修复前红/绿：T1（helper）/T2（裸跑不追溯）/T5（受保护路径接线）/T7（空 base 不跳过）红，T3/T4/T6 绿；运行 `uv run pytest -q tests/test_openspec_artifact_checker.py -k "resolve_base_ref or empty_base_ref or historical_archives or new_archive_missing_exit or explicit_base_ref_still_wins or behind_branch"`。
- [x] 1.3 变异验证（实测）：① 把 `_resolve_base_ref` 改为恒返回 `"master"` → T1/T2/T4/T5 红（4 failed / 3 passed）；② 改为返回候选 ref 名（两点语义）→ T1/T5/T6 红（3 failed / 4 passed）；恢复后 173 passed。补丁位置：`scripts/check_openspec_artifacts.py:1540` 起（非显式分支首行）；命令同上。

## 2. 实现（checker）

- [x] 2.1 `--base-ref` 默认 `None`；`_resolve_base_ref` 实现 merge-base 优先、显式优先、fallback 与 stderr INFO。
- [x] 2.2 `main()` 解析一次并传给归档点门与受保护路径 diff；help/docstring 同步；归档点门与出口判据逐行未动。
- [x] 2.3 定向测试全绿（173 passed 口径）。

## 3. 规格与文档

- [x] 3.1 `specs/dev-workflow-state-machine/spec.md` delta（MODIFIED 归档点 Requirement）。
- [x] 3.2 把 delta 施加进 current spec（`openspec/specs/dev-workflow-state-machine/spec.md`），记录 Requirement 计数 12 → 12，写 `current_spec_synced` 事件；OpenSpec strict validate 通过。
- [x] 3.3 `AGENTS.md` / `docs/development-guide.md` / `docs/requirements-process.md` / `docs/known-debt.md` / CI 注释同步为 merge-base 口径；为 `docs/known-debt.md` 写本 change 的 `protected_artifact_explained` 事件。
- [x] 3.4 新增 `docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md`（≥2 备选）。
- [x] 3.5 全仓 grep 复核：无「裸跑会误红」的过期说明。

## 4. 验证（实测）

- [x] 4.1 干净 HEAD 裸跑 checker → EXIT=0。
- [x] 4.2 `--base-ref origin/master --require-base` → EXIT=0。
- [x] 4.3 `--check-archived` → EXIT=0。
- [x] 4.4 新建归档缺 `## 闭环出口` 的守卫用例实测为红。
- [x] 4.5 OpenSpec strict validate 通过（本 change 活跃时为 30；归档前 29；以实跑为准）。
- [x] 4.6 全量 `uv run pytest -q`：**2 failed / 4530 passed / 9 skipped**（550.80s）；2 条失败均为既有 `TestFindScopeRoot` 本机 `/tmp` 环境失败，与基线同因，无新增失败类型（基线 2 failed / 4523 passed；+7 = 新增测试）。
- [x] 4.7 归档后 `/home/happy/wl170/bin/witnessloop check --root <repo> --base origin/master --head HEAD` → `check：通过 ✓`（三份 manifest 落盘后复验；实测 1 个 change 目录、0 findings）。
- [x] 4.8 归档 move 前写 `change_archived` 事件（`artifact-path=openspec/changes/archive/2026-10-18-check-scope-fix`），归档后重跑裸跑与 `--base-ref origin/master --require-base` 均为 EXIT=0（实测）。

## 5. 实现后独立审阅闭环

- [x] 5.1 独立零记忆审阅，产出 `reviews/building-review.md`（含 `## 闭环出口`），收敛到 PASS。
- [x] 5.2 全部 medium+ 修复并补回归测试；low/nit 登记并写理由。

## 6. 收尾（合入后）

> 归档 move、本地复验、`tasks.md` 结算与三份 manifest 的次序见文件头；PR 创建与合入在
> manifest 之后执行，不写回 `tasks.md`。

- [ ] (post-merge) 6.1 用 `--merge` 合入 PR；合入后确认 active 目录不存在、backlog 干净、本地 `master` 已快进。
- [ ] (post-merge) 6.2 给 issue #319 添加本 PR 完成说明 comment（不关闭 issue；TUI 退役另立 PR）。
