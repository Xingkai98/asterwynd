# Building Review: fix-issue-232-archive-write

## Verdict

PASS

## Reviewer

- run id: `89e2eb23-7af9-4cd2-b9ac-c0655f115e53`（独立零记忆 subagent，未参与开发）
- 时间: 2026-09-22
- 审阅基线: base `b54a50a3b132afbade150e175e9f40fdf8b8f24d` → head `4e22abc708548b40f49c7790d47769c3f9a0e78d`
- 复核方式（全部实跑，非只读代码）:
  1. `uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py -q` → 40 passed。
  2. `uv run pytest -q` 全量 → 3035 passed / 2 failed，2 条失败在 `tests/agent/memory/test_persistent.py::TestFindScopeRoot`（断言 `_find_scope_root('/tmp') is None` 失败，与本次 diff 零交集，`git diff --stat | grep memory` = 0），属既有环境性失败。
  3. **独立冷状态复现**：自建 4 个 `/tmp` 临时仓库（`openspec/changes/archive/<date>-<id>/` + `proposal.md` + `change_created` 首事件），实跑 `artifact-event` / `review-manifest`，核对 exit code、落点、污染、active 幽灵目录、前缀碰撞、日期前缀 id、陈旧投影告警。**未在真实仓库 `openspec/changes/archive/` 下执行任何写命令**。
  4. **独立变异验证**（改写 `scripts/workflow_state.py` → 跑测试 → 从 `/tmp/ws_backup.py` 还原，最终 `git status --porcelain` 为空）：去 archive 回退 7 红；去 `archived=` 透传 3 红；去「归档跳过刷新」3 红；去 Q2 一致性断言 1 红。
  5. **只读承诺佐证**：读 `agent/workflow/event_log.py:481-508`（`verify_projection`）、`:347-359`（`verify_handoff_projection`）、`project_workflow_state` 源码，确认三者只读（无 `write_text` / `mkdir` / `open(...,"w")`）。
  6. **文档事实核验**：实跑 `_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`；`change_dir_for('.', ..., archived=True)` → `openspec/changes/archive/2026-09-21-fix-issue-199-handoff-prereq`；`ls openspec/changes/archive | grep -v '^[0-9]{4}-[0-9]{2}-[0-9]{2}-'` → 空（89/89 全带日期前缀）；对全部 89 个归档目录 read-only 跑 `verify_projection` → 0 告警；`ls openspec/changes/archive/*/workflow-state.json` → 1 个（`2026-08-15-flow-event-projection`，与 D4 的 1/89 一致）。

## Tasks Verification

`tasks.md` 当前 **30 条未勾选 / 1 条已勾选**（`- [x]` 仅「变异验证」一项），故严格意义上只有 1 条 `[x]` 需要验证；为便于收尾，下面把「未勾选但已实现」的条目也逐条核对了实现落点。

- [x] **变异验证（4 组全部实测变红，还原后全绿）** — 已验证，且由我独立复现：4 组变异分别得到 7/3/3/1 条红，与 tasks 描述（8/3/3/1）量级一致；还原后 `git status --porcelain` 干净。证据: `scripts/workflow_state.py`（变异点 `:911` archive 回退、`:1101` `archived=` 透传、`:941-943` 归档跳过刷新、`:914` 一致性断言）。
- [ ] `_require_change_target` active 优先 + archive 回退（委托 `change_dir_for(archived=True)`，`repo_root` = `CHANGES_ROOT.parent.parent`） — 实现已存在: `scripts/workflow_state.py:905-922`；实跑证据：归档 change `artifact-event` exit 0 且事件落归档目录。
- [ ] 解析结果位于 archive 之下时标记归档目标 — 实现方式与 tasks 措辞（“用路径前缀判定”）不同：实现在 `:906,:922` 用「active 目录不存在 → `is_archived=True`」。在 active 优先解析下两者等价（`change_dir_for(archived=True)` 的返回值恒在 `CHANGES_ROOT/archive/` 之下），见 Issues 的 O1（观察，不阻塞）。
- [ ] 解析结果目录名必须裸 `<id>` 或 `<date>-<id>`，否则 fail-closed exit 1；`--change` 带日期前缀 id 显式拒绝 — 已验证: `:854-867`（`re.fullmatch` + `re.escape`）、`:899-903`（日期前缀拒绝）、`:914-920`（fail-closed）。实跑：查询 `alpha` 而 archive 只存在 `2026-09-22-alpha-beta` → exit 1「目录名与 change id 不匹配（拒绝写入以避免污染其它 change）」，兄弟目录事件日志仍为 1 行。
- [ ] `cmd_review_manifest` 对归档目标传 `archived=True` — 已验证: `:1101`；实跑 manifest 落 `archive/<date>-<id>/reviews/building-review-manifest.json`，`verify_review_manifest(..., archived=True)` 实测为 `[]`。
- [ ] 归档目标跳过 `_flow_refresh_after_event` — 已验证: `_after_protected_write` `:932-953`，`:941-943` 分流；实跑归档目录写入后仅有 `proposal.md` + `workflow-events.jsonl`（+ 用例预置文件），无 `handoff.json` / `workflow-state.json`。
- [ ] 归档目标只读 `verify_projection`，不一致 stderr 告警、exit 0、绝不落盘 — 已验证: `:946-952`；实跑预置陈旧 `workflow-state.json` → stderr 有告警、exit 0、投影文件 sha256 不变；`/tmp` 归档目录亦无新增文件。
- [ ] 保留 #199 全部行为 — 已验证: diff 未改 `:869-903` 的既有校验分支（仅新增日期前缀拒绝 + 回退），`cmd_artifact_event` / `cmd_review_manifest` 的 active 路径仍走 `_flow_refresh_after_event`；`tests/test_workflow_protected_write_channel.py` 11 条全绿（tasks 写「10 条」，实为 11 条，属文档小漂移）。实跑并存场景（active 与 archive 同名）：写入落 active 且刷新投影，archive 未被触碰。
- [ ] 测试条目（tasks 17-25、31） — 覆盖已存在: `tests/test_workflow_archive_write_channel.py` 11 条，与 tasks 逐条对应（落点/污染/幽灵目录/路径型 id/日期前缀 id/前缀碰撞/只读告警/非法目录）。缺口见 O2（3 条）。
- [ ] 文档条目（tasks 35-40） — 部分已存在: `diagnosis.md` 6 章、spec delta、backlog 登记均在；`docs/known-debt.md` 更新（task 38）与 spec 同步（task 37）尚未落，见 O3。

## Issues

未发现中等及以上问题。以下 4 条为低severity 观察/建议，均不阻塞合入。

- **O1**（Low，文档-实现措辞不一致）: design.md:53（D3）与 tasks.md:6 写「判定用**路径前缀**判断，不用目录名猜」，实现实际用「active 目录不存在 → `is_archived=True`」（`scripts/workflow_state.py:906,922`）。设计自己在 design.md:53 论证了两者等价（我独立验证：active 优先下 `change_dir_for(archived=True)` 的返回值恒在 archive 下；并存时实测走 active 且结果与路径前缀判据一致），故**行为无差异**，仅代码注释未说明该判据选择。证据: `scripts/workflow_state.py:905-922`；实测并存用例（active + archive 同名）落 active、`is_archived=False`。
- **O2**（Low，测试覆盖缺口，3 条）: ① 归档目录为**裸 `<id>`**（无日期前缀）的情形无用例——`_archive_dir_matches_change_id` `:865` 的 `name == change_id` 分支未被任何测试执行（`change_dir_for` 也有该分支，`review_manifest.py:45`）；② 归档的**老世代** change（只有 `handoff.json`，无 `proposal.md`）无用例，而 spec 既有 Scenario「老世代 change 的受保护写通道保持可用」覆盖该形态（我用真实归档目录 `archive/2026-07-14-add-workflow-automation`、`archive/2026-07-08-multi-agent-dev-workflow` 拷到 `/tmp` 实跑：均 exit 0、无告警、`handoff.json` 未被改写、无投影新增）；③ tasks.md:21「归档 + 不存在 id → exit 1」无对应用例（实跑 `--change nope-nope` → exit 1「不存在」；active 语境由 `test_workflow_protected_write_channel.py:229,237` 覆盖）。三条均非判别性缺陷，建议后续补。
- **O3**（Low，待收尾项 + 悬空前向引用）: `scripts/workflow_state.py:856-858` 的注释写「修复该正则属独立决策，记在 `docs/known-debt.md`」，但本 diff **未改** `docs/known-debt.md`（`grep -n "change_dir_for" docs/known-debt.md` 无命中），且其 `## 归档 change 的 review manifest 写入/校验双盲区` 一节仍写着「写入盲区…`_require_change_target` 只看 active 目录」——本 change 合入后该表述即失真。tasks.md:37-38 已列入待办，收尾时必须完成，否则注释成为悬空引用、known-debt 与代码事实相反。
- **O4**（Low，安全，**先于本 change 存在**）: `--change ..` 可被当作合法单段 id（`:889` 的校验只拦绝对路径与 `/`、`\`，`:899` 的日期前缀正则也不命中 `..`）。实测：若仓库内恰好存在 `openspec/proposal.md`（我构造该前置），`artifact-event --change ..` 会 exit 0 并把 `workflow-events.jsonl` / `workflow-state.json` / `handoff.json` 写到 `openspec/` 目录（即 changes 根之上）。**该缺口在 base `b54a50a` 上同样存在**（`git show b54a50a:scripts/workflow_state.py` 第 869 行即同一校验），非本 change 引入；且最远只能上一级（`/` 被拒），**无法写到仓库外**，spec「受保护写通道拒绝非法目标」的「SHALL NOT 写入仓库外路径」未被违反。建议另案收紧（拒绝 `.` / `..`），本 change 不需要处理。
- **O5**（Info，front matter 与文档漂移）: ① `docs/openspec-change-backlog.md:115-116` 新增条目仍保留两处本 change 自己**已判定失实**的表述（「不传 `archived=` 会写进 active 幽灵目录」——实为先抛 `FileNotFoundError`；「复用既有 `_flow_resolve_change_dir` 口径」——实为委托 `change_dir_for`），与 `proposal.md` / `design.md` / `diagnosis.md` 及 `workflow-events.jsonl` seq 2 的更正相矛盾；该条目按 tasks.md:40 在收尾时会整条删除，故不会进入 master，但若在收尾前提交 PR 会短暂自相矛盾。② design.md:67 称 delta 有 12 条 Scenario / 新增 1 条，实测 delta 该 Requirement 为 **13** 条 Scenario、新增 **2** 条（`受保护写通道支持已归档 change`、`受保护写通道拒绝归档语境下的非法 change id`），既有 11 条 **零丢失**（逐 Scenario 集合比对）；tasks.md:36 同样写「新增 1 条」。

## Spec Alignment（逐条 SHALL 对照 spec delta）

| spec delta SHALL | 实现 | 实跑证据 |
|---|---|---|
| 目标解析 active 优先，否则回退 `archive/<date>-<id>/` | `scripts/workflow_state.py:905-922` | 归档写入 exit 0；active 优先（并存用例落 active） |
| 回退 SHALL NOT 依赖 `flow status` 解析 | 委托 `change_dir_for`（`:910`），未用 `_flow_resolve_change_dir` | `_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`（确认既有回退是死代码） |
| 解析结果 SHALL 与查询 id 一致，否则 exit 1 | `:854-867` + `:914-920` | `alpha` vs `2026-09-22-alpha-beta` → exit 1，未写任何文件 |
| `--change` SHALL 只接受裸 id | `:899-903` | `--change 2026-09-21-arch-one` → exit 1，事件日志保持 1 行 |
| 写入落归档目录、SHALL NOT 新建 active 目录 | `:910,1101` | `/tmp` 复现：事件/ manifest 均落 archive，`openspec/changes/<id>/` 不存在 |
| 归档 SHALL NOT 产出投影文件 / SHALL NOT 刷新投影 | `_after_protected_write` `:932-953` | 写入后归档目录无 `handoff.json` / `workflow-state.json` |
| 不一致 SHALL 告警但 SHALL NOT 落盘、SHALL NOT 失败 | `:946-952` | 陈旧投影 → stderr 告警 + exit 0 + sha256 不变；`verify_projection` 源码只读 |
| 对 active 目标写入后 SHALL 重新生成投影 | `:941-942` | 并存/active 场景写入后生成 `workflow-state.json` + `handoff.json`；#199 测试全绿 |

## Test Results

```
$ uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py -q
........................................                                 [100%]
40 passed in 47.08s

$ uv run pytest -q
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
2 failed, 3035 passed, 9 skipped, 76 warnings in 310.66s (0:05:10)
# 2 条失败与本 change 零交集：断言 _find_scope_root('/tmp') is None 失败（环境性），diff 未触碰 tests/agent/memory/**
```

独立冷状态复现（摘录，`T` 为 `/tmp` 临时仓库）：

```
===== A: artifact-event on archived change =====
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)   exit=0
archive/2026-09-21-arch-one/{proposal.md,workflow-events.jsonl}            # 无 handoff/workflow-state
active 路径 openspec/changes/arch-one -> No such file or directory

===== B: review-manifest on archived change =====
已写入 review manifest: .../archive/2026-09-21-arch-one/reviews/building-review-manifest.json  exit=0

===== C: 前缀碰撞（只有 2026-09-22-alpha-beta，查询 alpha）=====
错误：change 'alpha' 解析到归档目录 '2026-09-22-alpha-beta'，目录名与 change id 不匹配（拒绝写入以避免污染其它 change）  exit=1
alpha-beta 事件日志行数 = 1（未被写入）

===== D: 陈旧已提交投影 =====
警告：归档投影与事件日志不一致（只读校验，未落盘）：workflow-state.json projection does not match workflow-events.jsonl
exit=0；投影 sha256 前后一致；归档目录无新增文件

===== E/F: 日期前缀 id / 不存在 id =====
错误：change id '2026-09-21-arch-one' 非法（请用不含日期前缀的裸 change id）  exit=1
错误：change 'nope-nope' 不存在  exit=1
```

独立变异验证（每次改后还原，最终 `git status --porcelain` 为空）：

```
mutation 1 去 archive 回退            -> 7 failed, 4 passed
mutation 2 去 archived= 透传          -> 3 failed, 8 passed
mutation 3 去掉「归档跳过刷新」        -> 3 failed, 8 passed
mutation 4 去 Q2 一致性断言            -> 1 failed, 10 passed
```

## 结论

核心修复行为、归档目标契约、只读承诺与 #199 零回归均经独立实跑与变异验证确认，测试有真实判别力（4 组变异全部变红），未发现中等及以上缺陷，判 **PASS**。

两点需在**收尾前**处理（均已在 tasks.md 排期，非代码缺陷）：
1. tasks.md:37-38 的 `docs/known-debt.md` 更新（本 change 合入后其现状描述失真，且 `scripts/workflow_state.py:856-858` 的注释会变成悬空引用）与 spec 同步；
2. tasks.md 勾选 + 生成 review manifest（tasks.md:44-45）——注意 artifact checker 只在 tasks 全勾选时才强制 building-review + manifest，若收尾时漏勾 `[x]`，该门禁会**静默失效**。
