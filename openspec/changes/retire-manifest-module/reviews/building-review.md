# Building Review: retire-manifest-module

## Reviewer
- run id: building-2026-10-17-r1
- 时间: 2026-10-17
- 审阅范围: `git diff origin/master...HEAD`（base 5225207, head ffa4d02）

## 独立复核命令

- `uv run pytest -q tests/test_flow_policy.py tests/test_workflow_guard.py tests/test_workflow_state_cli.py tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py tests/agent/workflow/test_resume_audit.py tests/test_retire_manifest_check.py` → 136 passed
- `uv run pytest -q` → **2 failed / 4523 passed / 9 skipped**；两条失败均为基线 5.1 已记录的 `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 本机 `/tmp` 是 git 仓库的环境失败，无新增失败（基线 Docker 契约失败本轮未复现；用例数下降与删除 18 条 manifest 用例、新增 9 条回归相符）
- `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → `OpenSpec artifact checks passed`（exit 0）
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed / 0 failed**
- 三份 delta 的 6 个 MODIFIED Requirement 与 current spec 逐字节比对：全部 MATCH（无 Scenario 静默丢失）
- `find openspec/changes/archive -name '*-review-manifest.json' | wc -l` = 80；archive 外 0 份；本 diff 未改 `openspec/changes/archive/**`

## 任务逐项验证

| 任务 | 结果 | 证据 |
|---|---|---|
| 0.1 | ✓ | `reviews/grill-design.md:5-15` 7 条 Confirmed Decisions（≥3，同行 `来源:`）；`## Open Questions`/`## User Confirmation` 小节存在（`:27`、`:45`） |
| 0.2 | ✓ | `design.md:50-169` Decisions 1–8 覆盖删除面/保留面/内联语义/文档规格影响 |
| 0.3 | ✓ | `reviews/grill-adversarial.md` 第 1 轮 4 条 medium 全修、deferred 空，出口 `PASS` |
| 0.4 | ✓ | `grill-design.md:27-28` Open Questions「无」；设计环出口 PASS |
| 0.5 | ✓ | `design.md:215-232` `## Pre-Implementation Review` 回填 grill 与对抗结论 |
| 1.1 | ✓ | `tests/test_workflow_state_cli.py:34` 列入 `REMOVED_SUBCOMMANDS`；`:231-264` 用合法 target（proposal + review report + tasks + specs）断言 `invalid choice` 且不落 manifest；正向用例已删 |
| 1.2 | ✓ | `tests/test_retire_manifest_check.py:394-411` 断言模块文件不存在 + 全仓 import 正则扫描（排除 `.venv/.dev/.git/openspec` 与本测试文件） |
| 1.3 | ✓ | `tests/test_flow_policy.py:205-233` 断言策略表/guard 默认表无 `-review-manifest.json`，`_is_privileged_cli` 对 review-manifest=False、artifact-event=True |
| 1.4 | ✓ | `tests/agent/workflow/test_resume_audit.py:89-94`（`_status_path` 两形态）、`:97-122`（历史 manifest 改动进入 changed_paths） |
| 1.5 | ✓（一处低风险偏差见 L2） | `tests/test_workflow_archive_write_channel.py:216-238`（兄弟前缀断言「不存在」且不含「不匹配」）、`:240-255`（同 id 多日期 fail-closed、两个目录均未被写）；`tests/test_workflow_guard.py:101-121`（归档内 manifest Write 仍 exit 2）；manifest 正向用例与 import 已删，保留断言改到 artifact-event |
| 1.6 | ✓ | `tests/test_retire_manifest_check.py:349-392` 调用/导入形态 marker + 退役词同句放行 + 阳性/阴性对照；`:414-427` 规范文档扫描 |
| 1.7 | ✓（事后不可复验） | 删除后转绿可复验（上述测试全绿）；「删除前红」为过程声明，无落盘原始输出 |
| 2.1 | ✓ | `agent/workflow/review_manifest.py` 已删除（diff 删除 264 行） |
| 2.2 | ✓ | `scripts/workflow_state.py:307-323`（`_archived_change_dirs`：CHANGES_ROOT/archive、`fullmatch`、按名排序）、`:326-380`（active 优先 → 归档回退、多匹配 fail-closed 文案、裸 id 校验）；parser/`cmd_review_manifest`/`_resolve_review_base_sha`/`subprocess` import 已删；`_archive_dir_matches_change_id` 已删；docstring 同步 |
| 2.3 | ✓ | `scripts/flow-policy.json` 删除 `-review-manifest.json` 规则；`scripts/workflow_guard.py:77-86` 默认表同步、`:263-273` 豁免正则移除；`_description` 未改（`manifest_verified` 保留），无规则使用记录于 `docs/known-debt.md:538-543` |
| 2.4 | ✓ | `agent/workflow/resume_audit.py:342-345` 忽略项已删 |
| 2.5 | ✓ | `agent/workflow/__init__.py:9` 包说明移除 `review_manifest` |
| 2.6 | ✓ | 上述 136 条 targeted 测试全绿；变异验证为过程声明（不可事后复验），但删除面每条均有可判红的负向断言 |
| 3.1 | ✓ | `AGENTS.md:108,115,203`；`README.md:264` / `README_EN.md:264` 双语同步（「事件日志 + 受保护写通道」/「event log + protected write channel」） |
| 3.2 | ✓ | `docs/development-guide.md:294-301,324-328` 改为已删除/历史冻结口径 |
| 3.3 | ✓ | `docs/requirements-process.md:45,293` 唯一活通道为 witnessloop 形态 |
| 3.4 | ✓ | `docs/interview-script/questions/Q14-dev-process.md:38,49` 改为已删除 |
| 3.5 | ✓ | `docs/known-debt.md:25`（Q7）、`:166-172`（第二刀已完成）、`:191-196`（A-遗留 2 关闭）、`:232`（行号锚点标注历史）、`:538-543`（第 5 项 + `manifest_verified` 无规则使用） |
| 3.6 | ✓ | `docs/adr/ADR-0004-...md:43-44,69` 指向 ADR-0005；`docs/adr/ADR-0005-...md:1-71` 新增（备选/后果/Revisit） |
| 3.7 | ✓（L4 残留一处措辞） | 全仓 `review[-_ ]manifest` 复核仅剩历史归档、`review_manifest_glob`、测试夹具与本 change 退役说明；`workflow_state.py review-manifest` 无活调用指示 |
| 4.1 | ✓ | `specs/dev-workflow-gate/spec.md:5-58` MODIFIED 生产/写通道已删除 + 场景 |
| 4.2 | ✓ | `specs/dev-workflow-state-machine/spec.md:5-190` MODIFIED 4 个 Requirement（含全部相关 Scenario） |
| 4.3 | ✓ | `specs/change-documentation/spec.md:5-33` 写通道清单移除 review-manifest |
| 4.4 | ✓ | current spec 三份与 delta 逐字节 MATCH；`workflow-events.jsonl` seq 3–5 三条 `current_spec_synced`（计数 12→12 / 12→12 / 14→14） |
| 4.5 | ✓ | 独立复跑 strict validate：30 passed / 0 failed |
| 5.1 | ✓（基线声明，与复跑一致） | 本机复跑仅余同一组 2 条 `/tmp` 环境失败 |
| 5.3 | ✓ | 独立复跑 checker：`OpenSpec artifact checks passed`，exit 0 |
| 5.4 | ✓ | 独立复跑：30 passed / 0 failed |
| 5.6 | ✓ | `tests/test_workflow_state_cli.py:231-264` 负向无副作用；artifact-event 归档写入由 `tests/test_workflow_archive_write_channel.py:109` 覆盖 |
| V1 | ✓ | 模块文件不存在；`review-manifest` 为未知子命令（`invalid choice`，exit≠0，无 manifest 落盘） |
| V2 | ✓ | active/归档/gen-1/非法 id/兄弟前缀/多日期目录用例全部通过；兄弟前缀错误文案为「不存在」，多匹配新增明确「匹配多个目录」错误 |
| V3 | ✓ | 策略表与 guard 默认表 parity 测试通过；`manifest_verified` 保留但无规则使用 |
| V4 | ✓ | resume audit 历史 manifest 改动被发现（`:97-122`） |
| V5 | ✓ | 80 份历史 manifest 未改；checker 忽略其漂移（`tests/test_retire_manifest_check.py:291-310`） |
| V6 | ✓ | 三份 current spec 与 delta 一致，只描述一套 witnessloop 形态；`## 闭环出口` 判据代码未动（checker 仅 docstring 注释） |
| V7 | ✓ | 全量 pytest 无新增失败；checker exit 0；strict validate 30/30 |

### 未勾项说明

- 5.2 / 5.5 未勾（非 closeout）；5.2 的结论已被 V7 勾选并独立复跑证实，属任务簿记滞后（见 L7）。
- 6.x / 7.x / 8.x / 9.x 为审阅环、证据产出、归档与合入后动作，不在本轮范围；未勾不构成缺陷。

## 本轮判定

PASS

### 初次开批 · 批次

（空——未发现 blocker / high / medium）

### 初次开批 · 下一批（deferred）

（空）

### low/nit 登记表

| id | severity | 处置 | 理由 |
|---|---|---|---|
| L1 | low | 登记 | `tests/test_workflow_protected_write_channel.py:107` 的 `_seed_review_artifacts` 在 manifest 正向用例删除后已无调用方，属死测试辅助；不影响覆盖与行为，可后续清理 |
| L2 | low | 登记 | `tests/test_workflow_guard.py:101-121` 只覆盖 Write，task 1.5 写的是 Write/Edit；两者在 guard 里是同一分支（`tool_name in ("Write","Edit")`），且其它受保护路径已有 Edit 用例，判别力等价 |
| L3 | low | 登记 | `tests/test_retire_manifest_check.py:399-405` import 扫描排除整个 `openspec`，比 task 1.2 指定的 `openspec/changes/archive/**` 更宽；`openspec/**` 下当前无生产 `.py`，实际风险为零 |
| L4 | low | 登记（措辞） | `scripts/workflow_guard.py:611,624` 的拦截提示仍写「或 review manifest」；写通道删除后该措辞会误导读者，建议改为 witnessloop 形态 manifest |
| L5 | nit | 登记 | 三份 current spec 在施加 delta 时删掉了 Requirement 前空行（`openspec/specs/change-documentation/spec.md:423`、`openspec/specs/dev-workflow-gate/spec.md:128`、`openspec/specs/dev-workflow-state-machine/spec.md:364`），纯排版回归，strict validate 与 checker 均通过 |
| L6 | low | 登记（存量债务） | `openspec/specs/dev-workflow-state-machine/spec.md:283-287` 的「归档点门与 manifest 校验模式互斥」仍称 `--check-archived`「只做既有 manifest 的漂移检测」，与第一刀后事实不符；属第一刀遗留、不在本 change 的 MODIFIED Requirement 集合内，建议另立清理 |
| L7 | low | 登记（簿记） | `tasks.md:55,58,95`：5.2/5.5 未勾但 V7 已勾；V7 的三项结论已由本轮独立复跑证实，归档前应补齐 5.2/5.5 的勾选/结果记录，避免归档点完成度门被判红 |
| L8 | nit | 登记 | `tests/test_workflow_archive_write_channel.py:227` 的 `_seed_review_artifacts(sibling)` 在 manifest 调用删除后已与断言无关，可顺手删除 |
| L9 | nit | 登记 | `scripts/workflow_state.py:371` 的 `archived_dir = matches[0] if matches else CHANGES_ROOT / "archive" / change_id` 在 `matches` 为空时必然走「不存在」分支，else 回填多余；可简化为先判空 |

### 初次开批 · 收口确认

本轮未开非空批次（medium+ 为零）：初次开批确认批次为空。正确性、Spec 对齐、删除面/保留面配对、安全边界（归档解析 fail-closed、历史文件仍受归档前缀保护）、CI/checker/witnessloop 判据均未发现需修复项；low/nit 共 9 条仅登记。

## 闭环出口

PASS
