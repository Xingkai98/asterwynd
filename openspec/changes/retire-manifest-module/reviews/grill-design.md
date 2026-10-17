# Grill: retire-manifest-module

## Reviewer
- run id: grill-2026-10-17-retire-manifest-module
- 时间: 2026-10-17

## Confirmed Decisions

- **决策**: 直接删除 `agent/workflow/review_manifest.py`，不为 `artifact-event` 保留薄壳，把归档目录解析内联到 `scripts/workflow_state.py`；理由: 全仓生产 side 的唯一消费者就是 `scripts/workflow_state.py:41,384`，测试侧 import 随本 change 删除，保留薄壳只会留下一个没有生产者的「活 import 路径」并延续双通道幻觉；来源: `scripts/workflow_state.py:41,139-155,380-395,484-519,699-706`；`grep -rn "from agent.workflow.review_manifest" --include=*.py` 除 `scripts/workflow_state.py:41` 与 4 个测试文件外无命中；`tests/` 下的 5 处 import 全在本次删除/改写清单内
- **决策**: 内联 helper 用 `re.fullmatch(r"\d{4}-\d{2}-\d{2}-<escaped id>", name)`，不再沿用无 `$` 锚点的 `re.match`；理由: 旧写法把 `alpha` 命中 `2026-09-22-alpha-beta` 是已知缺陷，调用侧断言（`_archive_dir_matches_change_id`，`workflow_state.py:329-341`）本来就用 `fullmatch`；内联后两端口径一致，合法输入行为不变，兄弟前缀从「解析到错误目录后由断言拒绝」变为「直接判不存在」；来源: `agent/workflow/review_manifest.py:45-48`；`scripts/workflow_state.py:329-341,380-395`；`tests/test_workflow_archive_write_channel.py:267-286`（兄弟前缀回归，只留唯一候选目录，避免 `iterdir()` 顺序假绿）
- **决策**: 删除 `review-manifest` 子命令而不保留 deprecation 占位；调用必须以 argparse 未知子命令非零退出且无副作用；理由: 仓库已有 `TestRemovedSubcommands` 的「未知、非零、无副作用」惯例，保留占位会让 CLI surface 与文档继续承认该通道；来源: `tests/test_workflow_state_cli.py:27-36,258-320`；`scripts/workflow_state.py:699-706`；实测 `python3 scripts/workflow_state.py review-manifest --change test-change` 当前 exit 2（缺必填参数），删除后应为 `invalid choice`
- **决策**: 删除 `flow-policy.json` 的 `-review-manifest.json` 规则、guard 内嵌默认表同名规则与 privileged CLI 豁免，同时保留 `manifest_verified` governance 词汇；理由: 生产端删除后 active change 不再出现该文件，历史 80 份全在 `openspec/changes/archive/**` 下、仍被 `event_explained` 前缀规则覆盖；`manifest_verified` 是 spec 已钉住的政策枚举（`dev-workflow-state-machine` `:312`），删它属 schema 变更，超出本次纯删除范围；来源: `scripts/flow-policy.json:3,55-59`；`scripts/workflow_guard.py:16,69,73-85,254-275`；`openspec/specs/dev-workflow-state-machine/spec.md:312`；`openspec/changes/retire-manifest-module/specs/dev-workflow-state-machine/spec.md:159`（保留的豁免集已无该子命令）
- **决策**: 从 `_is_resume_audit_ignored` 移除 `-review-manifest.json`，让历史 manifest 修改按普通文件进入 resume audit；理由: 该忽略项只为跳过 workflow 自己写的 manifest，写通道删除后它只会让历史证据文件改动继续隐形；现有测试文件对这条忽略规则零覆盖，新增回归在删除前必红；来源: `agent/workflow/resume_audit.py:331-341`；`tests/agent/workflow/test_resume_audit.py`（当前无 review-manifest 断言，实测 grep 零命中）；`agent/workflow/resume_audit.py:180-197`（`_changed_paths` 过滤）
- **决策**: 80 份历史 `*-review-manifest.json` 冻结，不迁移/不重算/不删除，checker 继续忽略其漂移；理由: 第一刀已确认无法干净迁移且 checker 已不消费；实测 80 份全部位于 `openspec/changes/archive/**`，archive 外零份；保留 `test_check_archived_ignores_retired_manifest_drift` 即可证明；来源: `find openspec/changes/archive -name '*-review-manifest.json' | wc -l` = 80；`tests/test_retire_manifest_check.py:290-309`；`openspec/changes/retire-manifest-module/specs/dev-workflow-gate/spec.md:17-22`
- **决策**: 三份 spec delta 的 Requirement / Scenario 集合与 current spec 精确对齐（只改正文，不静默删场景）；理由: 用脚本按 `### Requirement:` / `#### Scenario:` 抽取比对，6 个 MODIFIED Requirement 的场景集合与 current spec 完全一致（gate 5+2、state-machine 12+4+3+4、change-documentation 3），不存在「delta 顺手丢掉 Scenario」的规范收窄；来源: `openspec/changes/retire-manifest-module/specs/{dev-workflow-gate,dev-workflow-state-machine,change-documentation}/spec.md` 与 `openspec/specs/{dev-workflow-gate,dev-workflow-state-machine,change-documentation}/spec.md` 的抽取比对（本报告执行）

## Code-Resolved Questions

- **除 `scripts/workflow_state.py` 外还有运行时代码 import `agent.workflow.review_manifest` 吗？** 没有。`grep -rn "from agent.workflow.review_manifest"` 只命中 `scripts/workflow_state.py:41` 与 `tests/test_workflow_state_cli.py:19`、`tests/test_workflow_protected_write_channel.py:27`、`tests/test_workflow_archive_write_channel.py:25`、`tests/test_openspec_artifact_checker.py:1788`、`tests/agent/workflow/test_review_manifest.py:6`；这些测试全部在 tasks 1.1/1.5 与 Impact Analysis 的删除面内。`scripts/check_openspec_artifacts.py:1205` 只是注释。
- **`artifact-event` 的归档解析确实是唯一需要保留的能力吗？** 是。模块内 `review_report_path` / `review_manifest_path` / `build_review_manifest` / `write_review_manifest` / `verify_review_manifest` 的唯一调用方是 `cmd_review_manifest` 与测试；`change_dir_for` 在删除 CLI 后只剩 `workflow_state.py:384` 的归档回退。内联 12 行解析即可，不需要新模块。
- **删除保护规则后历史 manifest 还受保护吗？** 受保护。guard 的路径匹配是「归一化后 contains」：`openspec/changes/archive/` 前缀规则命中任何归档内路径（包括绝对路径字符串）；`scripts/flow-policy.json:37-44` 的 `change_archived` 规则同时供 checker 使用。风险是这条「历史文件仍受保护」目前没有直接的 guard 回归测试，见风险清单。
- **80 份历史文件是否全在 archive 下？** 是：`find openspec/changes/archive -name '*-review-manifest.json' | wc -l` = 80；archive 外 `find` 零命中。
- **有在途 change、CI、witnessloop 配置依赖 `review-manifest` 吗？** 没有。active change 只有 `add-minimal-tui-runtime-view` 与 `retire-manifest-module`，前者零命中；`.github/workflows/ci.yml` / `witnessloop.yml` 零命中；`.witnessloop/policy.json:24` 只含 `review_manifest_glob: reviews/*.manifest.json`（witnessloop 默认 glob，匹配不到 `*-review-manifest.json`）。
- **本地 `/review-loop` 命令仍调用该 CLI 吗？** 不调用。`/home/happy/my-agent/.claude/commands/review-loop.md` 对 `workflow_state.py review-manifest` / `review_manifest` 零命中，proposal 的「只复核表述」成立。
- **`policy-set` 能删除以 `-` 开头的 path 吗？** 直接用 `--path -review-manifest.json` 不行：argparse 报 `argument --path: expected one argument`（实测 exit 2）；必须写 `--path=-review-manifest.json`（实测解析成功）。tasks 2.3 未写这个形式，见风险清单。
- **删除 `_resolve_review_base_sha` 后还有遗留吗？** `subprocess` 只在该函数内使用（`scripts/workflow_state.py:23,145`），删除后 import 变成未使用；`_is_archived_change_dir` 的 docstring（`:323`）与归档回退注释（`:382`）仍引用 `change_dir_for`，Impact Analysis 只列了 `:327-343` / `:359-384`，漏了 `:320-326` 与 import 清理。
- **规格 delta 会通过 strict validate 的 Requirement 首行 SHALL 判据吗？** 会。6 个 MODIFIED Requirement 的正文首行均含 `SHALL`，且 Requirement 名称都能在当前 spec 中精确命中（本报告脚本比对）。
- **移除 resume audit 忽略项会不会误伤正常流程？** 不会。历史 manifest 只在 archive 下且已冻结；正常开发期间不会修改它们。唯一行为变化是「禁用期间人工改历史 manifest」现在会进入 `changed_paths`，这是 Decision 5 的有意暴露。
- **`workflow_guard.py:91` 的 manifest 用例在规则删除后是否还有别的规则兜住？** 没有：该用例路径是 `.handoff/test-change/building-review-manifest.json`，删除 `-review-manifest.json` 规则后不再命中任何规则，必须改用其它受保护路径；Impact Analysis 已列出这一点（`tests/test_workflow_guard.py:91`）。
- **`manifest_verified` 还有任何规则使用吗？** 删除后没有。当前唯一使用点是 `scripts/flow-policy.json:55-59` 与 `scripts/workflow_guard.py:81`；保留枚举本身不影响 guard/checker（checker 只加载 `event_explained`，guard 接受但无规则使用）。
- **baseline 测试现状如何？** 实测 `uv run pytest -q tests/test_workflow_archive_write_channel.py tests/agent/workflow/test_resume_audit.py tests/test_workflow_state_cli.py` = 28 passed，说明删除前的归档写通道/CLI/审计基线干净，测试信号不会被既有失败污染。

## Open Questions

- 无

## 风险

- **[medium] 文档守卫与文档措辞会自相矛盾。** tasks 1.6 要求把守卫扩展到「不再指示 `review_manifest.py`」，而 tasks 3.1-3.4 又要求文档写成「模块与 CLI 已删除」。若守卫用裸 marker `review_manifest.py` 扫描 `NORMATIVE_DOCS`（`tests/test_retire_manifest_check.py:334-356`），任何按 3.2 写出的「`agent/workflow/review_manifest.py` 已删除」都会把守卫自己判红。修法：marker 钉成**调用/导入形态**（如 `workflow_state.py review-manifest` 带后续参数、`agent.workflow.review_manifest`），并允许「已删除」叙述；不要把文件路径当 marker。
- **[medium] 逆向守卫（全仓不再 import）存在自匹配假绿/假红。** tasks 1.2 的「全仓 Python 源码不再 import 该模块」若用子串扫描，会命中守卫测试自身保存的 marker 字符串，也可能把退役说明误判为引用。修法：用 import 语句正则（`^\s*(from|import)\s+agent\.workflow\.review_manifest\b`）或 AST，显式排除本守卫文件。
- **[medium] CLI 负向回归的「无副作用」断言当前会平凡通过。** `TestRemovedSubcommands` 的种子 `_seed_gen2_change` 只建目录 + `change_created` 事件、**没有 `proposal.md`/`handoff.json`**（`tests/test_workflow_state_cli.py:82-86`），所以即使子命令仍在，删除前也会因「不是合法 change」提前失败；把 `review-manifest` 加进 `REMOVED_SUBCOMMANDS` 后，`test_removed_subcommands_have_no_side_effects` 无法证明任何事。实测最小参数形态当前也是 `required` 错误而非 `invalid choice`。修法：为 review-manifest 单独构造合法 target（proposal + `reviews/building-review.md` + tasks/specs）并传完整参数，或至少断言「恢复子命令后会写文件」的变异探针。
- **[medium] 删除受保护规则后，缺少「历史 manifest 仍被 guard 拦截」的回归。** Decision 4 的安全前提是 archive 前缀规则兜底，但 `tests/test_workflow_guard.py` 只有 known-debt/known-issues/specs/archive 的泛化描述（`tests/test_workflow_guard.py:170-191`），没有对归档内 `*-review-manifest.json` 的直接 Write/Edit 探针。修法：新增 `Write`/`Edit` 指向 `openspec/changes/archive/<date>-<id>/reviews/building-review-manifest.json`，断言 exit 2。
- **[medium] `known-debt.md` 的更新面比 Impact Analysis 写的大。** Impact 只列 `:186-192,516-537`；但 `docs/known-debt.md:25` 的 Q7 仍写「legacy `*-review-manifest.json` 写通道保留到第二刀」，`:168-177` 仍把收口描述为「委托 `change_dir_for` / `cmd_review_manifest`」，`:229` 的行号锚点指向将被删除的 `agent/workflow/review_manifest.py:209-232`。不改这些会留下与「已删除」矛盾的事实口径。修法：tasks 3.5 显式加上 `:25` 与 `:168-177,:229`（历史段落可加「模块已于第二刀删除」注记）。
- **[medium] 验证 grep 漏掉连字符形态。** tasks 3.7/5.5 的 `grep -rn "review_manifest"` 匹配不到 `review-manifest`；而多处待清理文本只用连字符形态（如 `docs/known-debt.md:25`、`tests/test_workflow_state_cli.py:3`、`tests/test_workflow_archive_write_channel.py:4`、`tests/test_flow_policy.py:142`）。修法：改用 `grep -rnE "review[-_]manifest"`，并把结果贴进 PR。
- **[medium] `policy-set` 删除 leading-dash 路径的调用方式未写清。** 按 tasks 2.3 的字面执行 `policy-set --delete --path -review-manifest.json` 会 argparse exit 2（实测）；且 `scripts/flow-policy.json` 的 `cli_written` governance 把 `policy-*` 规定为 agent 合法写通道。修法：任务里钉死 `--path=-review-manifest.json`，并同步 guard 内嵌默认表（代码文件，不走 policy-set）。
- **[low] 内联 helper 的 base 推导未在 design 钉死。** `_require_change_target` 刻意用 `CHANGES_ROOT.parent.parent`（CWD 相对）而不是 `_PROJECT_ROOT`（`scripts/workflow_state.py:380-384`）；若 helper 改用项目绝对路径，tmp_path 内的子进程测试会全红而非静默。建议在 Decision 2 明确 helper 以 `CHANGES_ROOT / "archive"` 为根，或保留原 `repo_root` 参数。
- **[low] `fullmatch` 只关闭「更长前缀」碰撞，没有处理同一 id 的两个日期目录。** 若 archive 下同时有 `2026-01-01-alpha` 与 `2026-02-02-alpha`，`iterdir()` 仍是顺序依赖。建议在 helper 里收集全部 fullmatch，多于一个时 fail-closed（或至少有确定性排序）；这不是新缺陷，但既然在改这段解析，值得一次收口。
- **[low] `dev-workflow-gate` delta 的 Phase A 场景仍写 `agent/workflow/**` SHALL 未被修改。** 本 change 会删除 `agent/workflow/review_manifest.py` 并修改 `agent/workflow/{__init__,resume_audit}.py`；虽然场景的 WHEN 明确限定「阶段 A 的变更集被评审」，当前句式仍容易被读成对现状的约束。建议改成「阶段 A 变更集评审时」的时态表述，避免与已删除模块并存。
- **[low] 细节行号/计数：** proposal 写模块 265 行，实测 `wc -l` = 264；Impact 的 `_archive_dir_matches_change_id` 行段漏了 `:320-326`，且 `subprocess` import 会变成未使用。这些不阻塞实现，但应在实现时按现查行号更新。
- **[low] `tests/test_workflow_guard.py:127` 与 `tests/test_workflow_state_cli.py:3` 的 docstring** 仍把 manifest 描述为当前产物/活路径；连字符 grep 若按上条修好，会在清理时一并暴露。

## User Confirmation

本 change 无 Open Question，无需用户确认。
