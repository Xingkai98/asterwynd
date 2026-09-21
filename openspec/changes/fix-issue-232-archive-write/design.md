# Design — fix-issue-232-archive-write

## Context

见 `proposal.md` 与 `diagnosis.md`。核心事实：

- `_require_change_target`（`scripts/workflow_state.py:853`）只看 active 目录；对照 `_flow_resolve_change_dir`（`:794`）有 archive 回退——两个解析入口口径不一致。
- `cmd_review_manifest` 调 `write_review_manifest(...)` **不传 `archived=`**（默认 False）→ 即便前置放行也会写错位置。
- 成功后调 `_flow_refresh_after_event(change_dir)`；对归档目录实测**会写出 `handoff.json` + `workflow-state.json` 到归档目录**（立项复现并清理）。
- `review_manifest.change_dir_for(archived=True)` 已能按 `<date>-<id>` 扫描定位归档目录——能力存在，只是调用方没用。

## Goals / Non-Goals

**Goals**

- 归档 change 可经合法 CLI 写受保护 artifact（事件 + manifest），落在归档目录内。
- 归档目录**不被污染**（不产出投影文件、不在 active 路径新建幽灵目录）。
- active change 与 #199 行为零回归。

**Non-Goals**

- 不做盲区 B（CI `--check-archived`）——实测有 15 条既有 `tasks hash mismatch`，需先决策。
- 不改 `flow status` / `_flow_resolve_change_dir` 的归档只读语义。
- 不改 `.gitignore`（#228 范围）。

## Decisions

### D1: 复用 `_flow_resolve_change_dir` 的口径，而非新写回退逻辑

`_require_change_target` 的目标解析改为与 `_flow_resolve_change_dir` 同口径（active 优先 → archive 回退）。理由：两处解析同一概念（"这个 change 在哪"），分叉正是本 bug 的根因；复用现成函数（或抽出共用 helper）可避免再次漂移。

> 待 grill 确认：直接调用 `_flow_resolve_change_dir`（它不做 `proposal.md`/`handoff.json` 合法性判定），还是在其结果上再做合法性判定？本设计倾向「解析 + 判定分离」：`_flow_resolve_change_dir` 负责定位，`_require_change_target` 在其结果上做合法性判定（保持 #199 的锚点不变）。

### D2: 合法性锚点对归档目标维持 #199 口径

归档目录同样按「`proposal.md` 存在 **或** `handoff.json` 存在」判定。理由：归档 change 普遍有 `proposal.md`；老世代归档（如只有 handoff）也应可写。#199 的锚点无需为归档特例放宽。

> 待 grill 确认：是否需要额外要求「归档目录名符合 `<date>-<id>`」（防止 archive 下放非 change 目录）？

### D3: 把「已归档」显式传给 `write_review_manifest`

调用方据解析结果传 `archived=True`。理由：`change_dir_for` 按 `archived` 决定路径；不传则写 active 路径（不存在则 mkdir 出新幽灵目录——比报错更坏）。判定方式：解析结果是否位于 `CHANGES_ROOT/archive/` 之下（用路径判断，不用目录名猜）。

> 待 grill 确认：判定用「路径前缀是否在 archive 下」还是「active 目录是否不存在」？前者更直接（active 与 archive 同名并存的极端情形下不误判）。

### D4: 归档目标跳过投影刷新

`_flow_refresh_after_event` 对归档目录**不调用**。理由（实测）：对归档的 #199 change 调用它会走 gen-2 分支（该 change 首事件 `backlog_updated`，`_flow_is_gen1` 为 False），在归档目录写出 `handoff.json` + `workflow-state.json`——它们是**已提交**目录里的未跟踪产物，比 active 目录的同类污染更严重（会被 `git add -A` 吞进后续提交）。且 `flow status` 对归档的既有口径本就是「只读不落盘」。

> 待 grill 确认：跳过刷新是否会使归档 change 的 `verify_projection` 立即报 stale？——本 change 的立场是**不会**：归档 change 的投影校验走 `--check-archived` 的只读口径（`verify_review_manifest(archived=True)`），不要求磁盘投影新鲜；且新增的归档事件是 `NON_STATE_EVENT_TYPES`（不影响投影 state）。若 grill 认为需要，可在归档写入后仅做**只读**一致性校验（不落盘）。

### D5: spec delta 补全为完整 Requirement 正文

按 #199 教训：`openspec archive` 是整段替换 Requirement，delta 必须含变更后的**完整**正文（本 change 保留全部 11 条既有 Scenario + 新增 1 条归档 Scenario）。已逐条从正式 spec 复制并改写，退役项为 0。

### D6: 非目标锁定——盲区 B 不在本 change

CI 是否加 `--check-archived` 是独立决策（15 条既有 hash 漂移需先定「重绑 vs 容忍」）。本 change 只在 `proposal.md` / 本设计的 Non-Goals 中记明，不顺手改 `ci.yml`。

## Pre-Implementation Review

非平凡 change（有 spec delta + 非 docs），进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 归档目录被投影文件污染（立项已实测复现） | D4 跳过刷新 + 判别性回归测试（断言归档目录无 handoff/workflow-state） |
| manifest 写到 active 幽灵目录（比报错更坏） | D3 显式传 `archived=True` + 测试断言落点在 archive、active 路径未被新建 |
| 两个解析入口再次漂移 | D1 复用同一解析（不新写回退） |
| delta 静默删既有 Scenario | D5 完整正文 + 归档前核对 Scenario 数 |
| 归档写入是否该被允许的语义争议 | 证据：manifest 必须绑定归档后的最终 head（#199 真实踩到），归档写入是收尾固有需求；由 grill 复核该立场 |

## Testing Strategy

- CLI 层（新增 `tests/test_workflow_protected_write_channel.py` 归档用例，或独立文件）：
  - 归档 change + `artifact-event` → exit 0，事件落归档目录事件日志。
  - 归档 change + `review-manifest` → exit 0，manifest 落 `archive/<date>-<id>/reviews/`，`verify_review_manifest(archived=True)` 为空。
  - **污染判别**：写入后归档目录**无** `handoff.json` / `workflow-state.json`；active 路径未被新建。
  - 归档 + 路径型 id / 不存在 id → 仍拒绝。
- 回归：#199 的 `tests/test_workflow_protected_write_channel.py`（10 条）+ `tests/test_workflow_state_cli.py` 全绿。
- 变异验证：去 archive 回退 → 归档用例红；去「归档跳过刷新」→ 污染用例红；不传 `archived=` → 落点用例红。
- 全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
