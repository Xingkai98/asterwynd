# Tasks — fix-issue-232-archive-write

## 实现

- [ ] `scripts/workflow_state.py`：`_require_change_target` 目标解析改为 active 优先 + archive 回退——**委托 `review_manifest.change_dir_for(archived=True)`**（D1；**不复用** `_flow_resolve_change_dir`，其回退对带日期前缀的归档目录是死代码；委托 `repo_root` 用 `CHANGES_ROOT.parent.parent`，不用 `_PROJECT_ROOT`）
- [ ] `scripts/workflow_state.py`：解析结果位于 `CHANGES_ROOT/archive/` 之下时标记为归档目标（D3，用路径前缀判定，不用目录名猜）
- [ ] `scripts/workflow_state.py`：解析结果目录名必须为裸 `<id>` 或 `<date>-<id>`，否则 fail-closed exit 1（D2/Q2——`change_dir_for` 的 `re.match` 缺 `$`，实测会命中 `alpha-beta`）；`--change` 带日期前缀 id 显式拒绝（D2/Q4）
- [ ] `scripts/workflow_state.py`：`cmd_review_manifest` 对归档目标传 `write_review_manifest(..., archived=True)`（D3）——不传会 `FileNotFoundError: review report missing: <active 路径>` exit 1（目录不新建，但报错误导）
- [ ] `scripts/workflow_state.py`：`cmd_artifact_event` / `cmd_review_manifest` 对归档目标**跳过** `_flow_refresh_after_event`（D4）——否则在归档目录写出 handoff.json / workflow-state.json
- [ ] `scripts/workflow_state.py`：归档目标写入后做**只读** `verify_projection`，不一致时 stderr 告警、exit 仍 0、绝不落盘（D4/Q3）
- [ ] 保留 #199 全部行为：路径型 id 拒绝、非法目标拒绝、老世代兼容、active 写入后刷新投影

## 测试

全部从**冷状态**构造（种子直接落盘事件，不用 `WorkflowManager.init()`；调用前断言状态符合预期）。归档用例在 tmp 仓库内构造 `openspec/changes/archive/<date>-<id>/`。新增独立文件 `tests/test_workflow_archive_write_channel.py`。

- [ ] 归档 change + `artifact-event` → exit 0，事件追加到**归档目录**的 `workflow-events.jsonl`
- [ ] 归档 change + `review-manifest` → exit 0，manifest 落 `archive/<date>-<id>/reviews/`，`verify_review_manifest(archived=True)` 为空
- [ ] **污染判别**：归档写入后，归档目录**无** `handoff.json` / `workflow-state.json`；`openspec/changes/<id>/`（active 路径）未被新建
- [ ] 归档 + 路径型 id（绝对/含 `/`）→ exit 1
- [ ] 归档 + 不存在 id → exit 1
- [ ] 归档 + 带日期前缀 id（`<date>-<id>`）→ exit 1，且不写任何文件（Q4）
- [ ] 前缀碰撞：归档下并存 `<date>-alpha/` 与 `<date>-alpha-beta/`，查询 `alpha` → 解析到 `alpha`（或 fail-closed exit 1），**绝不**写进 `alpha-beta`（Q2）
- [ ] 只读校验：归档目录投影一致 → 无告警；预置已提交 `workflow-state.json` 的归档目录追加事件 → stderr 有告警且 exit 0、无新落盘文件（Q3）
- [ ] active change 回归：#199 的 `tests/test_workflow_protected_write_channel.py`（10 条）全绿
- [x] 变异验证（4 组全部实测变红，还原后全绿）：
  - 去 archive 回退 → 8 条归档用例红
  - 去「归档跳过刷新」（改回无条件刷新）→ 3 条红（污染判别 + 2 条只读校验）
  - 去掉 `archived=` 透传 → 3 条红（落点/污染/ghost dir）
  - 去 Q2 解析一致性断言 → 前缀碰撞用例红（首次构造因依赖 `iterdir()` 顺序而假绿，已改为「只留唯一候选 `alpha-beta`」的确定性构造）
- [ ] 回归：`uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py -v`

## 文档

- [ ] `diagnosis.md`：bugfix 门禁 6 章（已产出）
- [ ] spec delta：`specs/dev-workflow-state-machine/spec.md`（MODIFIED「工作流事件日志与 handoff.json projection」——**补全为变更后完整正文**，保留全部 11 条既有 Scenario + 新增 1 条归档 Scenario；退役项 0）
- [ ] **当前规格同步**：delta 已合入 `openspec/specs/dev-workflow-state-machine/spec.md`（含 `current_spec_synced` 事件）
- [ ] `docs/known-debt.md`：按本 change 只收口盲区 A 的范围更新 #232 相关说明（盲区 B 仍开放）；并新增一条 `change_dir_for` 前缀正则缺 `$` 的债务（Q2），配 `protected_artifact_explained` 事件
- [ ] 关键词扫描 `docs/`、`AGENTS.md`、`docs/development-guide.md` 中与 artifact-event / review-manifest / 归档相关的段落
- [ ] `docs/openspec-change-backlog.md`：登记本 change（立项）+ 收尾移除（含 `backlog_updated` 事件 ×2）

## 审阅闭环

- [ ] 独立 subagent 审阅（`/review-loop`）→ 判 verdict → CHANGES_REQUESTED 则修复 + 回归，再审直到 PASS 或 3 轮封顶
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash（verify OK）

## 验证

- [ ] 全量 `uv run pytest -q` 通过（与本 change 无关的既有失败如实记录）
- [ ] OpenSpec strict validate 通过（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）
- [ ] OpenSpec artifact checker 通过（`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`）
- [ ] 端到端验收（issue #232 盲区 A 原文）：对一个**已归档** change 跑 `review-manifest`，manifest 成功落归档目录且 `verify_review_manifest(archived=True)` 为空，归档目录无投影污染
- [ ] 收尾：issue #232 **不关闭**（盲区 B 仍开放），添加 comment 说明盲区 A 已由本 PR 收口、列出盲区 B 的现状（15 条 hash 漂移 + CI 未带 `--check-archived`）
