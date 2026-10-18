# Grill Adversarial: check-scope-fix

## Reviewer
- run id: `ef2d1462-81ef-4636-a8b0-ac70ad817680`
- 时间: 2026-10-18
- 审阅基线: HEAD=`b0469cb`（本轮修复仍在未提交工作树；钉住 blob：`scripts/check_openspec_artifacts.py`=`902df27`、`tests/test_openspec_artifact_checker.py`=`5ee084a`、current spec=`886f504`、delta spec=`813ab27`、`design.md`=`9745915`、`tasks.md`=`0042789`、ADR-0007=`3a62e2e`）；base: origin/master=`b0469cb`

## 本轮判定
- 第 1 轮：CHANGES_REQUESTED → 第 1 轮修复验证：**A1 PASS / A2 PASS**（无新增 medium+）

### 第 1 轮 · 批次
- A1 [medium] S1 只落在 delta，current spec 仍是旧措辞（「该解析失败时」）；delta/current 不一致。
- A2 [medium] 显式空字符串 `--base-ref ""` 被当作显式值原样透传，两个 diff 消费者只打 WARNING，checker 仍打印 `OpenSpec artifact checks passed`、EXIT=0；新归档缺 `## 闭环出口` 不会被求值。

### 第 1 轮 · 修复验证

**A1 — PASS**
- current spec `openspec/specs/dev-workflow-state-machine/spec.md:224` 已重同步为「非空显式提供……；空/纯空白显式值 SHALL 按未提供处理……；两个候选 ref 都不可解析时 SHALL 沿用既有 `--require-base` 的 fail-closed / warning 语义」。
- delta `openspec/changes/check-scope-fix/specs/dev-workflow-state-machine/spec.md:11` 与 current spec 的整块 MODIFIED Requirement 逐字一致：实测 `REQUIREMENT_BLOCK_EQUAL: True`，`len_cur=5727`、`len_delta=5727`（段落级 566/566 也一致）。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：`Totals: 30 passed, 0 failed`，EXIT=0。

**A2 — PASS**
- `scripts/check_openspec_artifacts.py:1540` 已改为 `if explicit is not None and explicit.strip():`；空/纯空白不再走显式分支，而是进入 `origin/master` → `master` 的 merge-base 解析。
- 单元测试 `tests/test_openspec_artifact_checker.py:2788-2789` 断言 `_resolve_base_ref(tmp_path, "") == expected` 且 `"   "` 同样返回 merge-base。
- 新增 `tests/test_openspec_artifact_checker.py:2846` `test_empty_base_ref_does_not_skip_checks`：在「新归档缺出口 + `--base-ref ""`」下断言 EXIT=1 且 stderr 含「闭环出口」；工作树版实跑通过，origin/master 版实跑失败（见下方 4 红 3 绿）。
- docstring（`scripts/check_openspec_artifacts.py:1528-1531`）、ADR-0007（`:35-36`）、design（`:49`、`:121-122`）与 spec（`:224`）均已同步；argparse help 仍写 `explicit values are used as-is`，未说明空/纯空白例外（low，见登记表 L3）。

**L1 — PASS**
- `design.md:138-145` Decision 5 已写入：内容提交 → **写出 `change_archived` 事件** → 移除 backlog 条目 → 归档 move（独立提交）→ 本地复验（裸跑 + 显式 base）→ 结算 `tasks.md` → 重建三份 witnessloop manifest → `check` 复验 → PR → `--merge`；并明确 `docs/known-debt.md` 的 `protected_artifact_explained` 与 `current_spec_synced` 事件在内容提交阶段写入。
- `workflow-events.jsonl` 现有 4 条事件，含 seq 3 `current_spec_synced`（`openspec/specs/dev-workflow-state-machine/spec.md`）与 seq 4 `protected_artifact_explained`（`docs/known-debt.md`），与本 change 的受保护路径改动对应。
- 残留 low：序列仍是「归档 move → 本地复验 → 结算 tasks」，首次裸跑会先看到 4.8 未勾；最终 `check` 复验是权威绿。见 L1。

**L2 — PASS（可复现），计数残留 low**
- `tasks.md:19`（1.2）：7 条测试、修复前红 T1/T2/T5/T7、`-k` 过滤器含 `empty_base_ref`；实测过滤器选中 7 条。
- `tasks.md:20`（1.3）：补丁位置 `scripts/check_openspec_artifacts.py:1538` 起、命令「同上」、失败集合已写；恢复后 173 passed 已实测。
- 变异实测（7 条测试）：
  - 变异①（`_resolve_base_ref` 恒返回 `"master"`）：**4 failed / 3 passed**；红 = T1（helper）、T2（裸跑不追溯）、T4（显式 base）、T5（受保护路径接线）；绿 = T3、T6、T7。
  - 变异②（隐式分支返回候选 ref / 两点语义）：**3 failed / 4 passed**；红 = T1、T5、T6（落后分支）；绿 = T2、T3、T4、T7。
- 与任务记录不一致：`tasks.md:20` 仍写 4 failed/2 passed 与 3 failed/3 passed（按 6 条测试的旧计数），且补丁位置写 1538、当前实际为 1540。失败**集合**与修复前 4 红 3 绿均正确，判别力不受影响。见 L2。

### origin/master 版 checker 下的新测试（/tmp 副本）
- 结果：**4 failed / 3 passed**。
- 红：`test_resolve_base_ref_prefers_origin_master_and_honors_explicit`（T1）、`test_bare_check_does_not_trace_historical_archives`（T2）、`test_empty_base_ref_does_not_skip_checks`（T7）、`test_resolve_base_ref_is_used_for_protected_path_diff`（T5）。
- 绿：`test_bare_check_still_flags_new_archive_missing_exit`（T3）、`test_explicit_base_ref_still_wins`（T4）、`test_behind_branch_does_not_false_red_protected_paths`（T6）。
- 工作树版同过滤器 7 passed；恢复副本后 7 passed；两测试文件 173 passed。

### 本轮实跑命令
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → EXIT=0（`INFO ... origin/master -> b0469cb`）
- `... --base-ref origin/master --require-base` → EXIT=0
- `... --check-archived` → EXIT=0
- `uv run pytest -q tests/test_openspec_artifact_checker.py tests/test_retire_manifest_check.py` → **173 passed**
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**

### 下一批（deferred）
- 无（修复验证未发现新 medium+）

### low/nit 登记

| id | severity | 问题 | 处置理由 |
|---|---|---|---|
| L1 | low | `design.md:138-145` 的收尾次序仍是「归档 move → 本地复验 → 结算 tasks.md」；首次裸跑会先看到 4.8 未勾，可能被误读为失败 | 最终 `check` 复验在 tasks 结算之后，属权威绿；建议明确「首次红是预期的」或把 4.8 的勾选放到首次裸跑前 |
| L2 | low | `tasks.md:20` 的变异计数仍按 6 条写（4/2、3/3），7 条实测为 4/3、3/4；补丁行号 1538 实际已是 1540 | 失败集合（T1/T2/T4/T5、T1/T5/T6）与修复前 4 红 3 绿均正确，判别力不受影响；只需更新计数与行号 |
| L3 | low | argparse help 仍写 `explicit values are used as-is`，未说明空/纯空白按未提供处理 | docstring/ADR/design/spec 已同步；help 是用户可见文案，建议补一句「empty/whitespace treated as omitted」 |
| L4 | low | shallow clone 下 `git merge-base` 失败静默退回候选 ref（两点语义），`--require-base` 不介入 | 设计明确接受的退化；CI 用显式 PR base sha |
| L5 | low | `origin` 指向 fork、stacked PR 或非 master 基线时，默认 base 可能不是本 PR base | 本仓 PR 约定从 `origin/master` 分支；显式参数是逃生口 |
| L6 | low | `origin/master` 未 fetch 而陈旧时，历史归档误红类问题会复现；「fail-loud」只有 INFO 行 | 设计/ADR 已列为接受风险并文档化「裸跑前 fetch」 |
| L7 | low | 受保护 artifact 事件按路径跨全部历史 change 日志匹配（弱门）；本 change 已补 seq 3/4 事件，但门本身仍可被历史事件满足 | 既有门禁弱点（grill R5），非本 change 引入 |
| L8 | low | backlog 条目采用 batch bullet 格式，`BACKLOG_CHANGE_PATTERN` 不识别；归档时漏删不会被 `check_backlog_consistency` 报出 | 既有格式/checker 错位；tasks 文件头已要求归档前移除 |
| L9 | nit | /tmp 验证时 repo 的 `_virtualenv` editable finder 会遮蔽临时 `scripts`（需复制 `scripts/__init__.py` 并用 module `__file__` 核实）；变异恢复不要只靠 `git diff`（racy stat 可能短暂报 clean） | 验证方法学提示，不影响本轮结论；最终恢复以 blob hash 与 173 passed 为准 |
| L10 | nit | `design.md` 的 `## Pre-Implementation Review` 仍是占位说明 | tasks 0.5 明确在 grill/adversarial 后回填；当前处于设计阶段，属预期 |

## 收口确认
- A1/A2 全部通过；本轮 medium+ 为空（0）；deferred 为空。
- L1/L2 已按要求补齐；low/nit 已登记，不阻塞。

## 闭环出口
PASS

本批 medium+ 数量：0
