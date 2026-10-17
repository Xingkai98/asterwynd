# Tasks: 下掉与 witnessloop 重复的本仓 review manifest 校验（retire-manifest-check）

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → **用归档目录名**重建 witnessloop 三份 manifest → 机械复核。
> closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）执行设计追问，产出 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与 `## User Confirmation` 小节无条件存在）。
- [x] 0.2 逐项确认：删除面（`_check_review_manifests` + 两个调用点）、保留面（building-review 存在性 + `## 闭环出口` PASS）、历史不追溯边界、第二刀边界。
- [x] 0.3 跑设计阶段对抗闭环 → `reviews/grill-adversarial.md`；按批次模型开批 / 全修 / 只验证 / 收口，直到 PASS（无轮数上限，停止条件 = 收敛；无法收敛 ⇒ BLOCKED + 成因）。
- [x] 0.4 停轮检查：`grill-design.md` 没有需要用户拍板的 Open Question，且设计环出口为 PASS（或 BLOCKED + 成因 + 用户明确裁决继续）。任一不满足 ⇒ 停下报告。
- [x] 0.5 把 grill 与对抗闭环结论回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 先写红测试（TDD）

- [x] 1.1 新增 parser 单测：标题带中文括号后缀命中；fenced code 内标题 / token 忽略；`**PASS**（...）` 通过；`PASS（此前 CHANGES_REQUESTED 已收口）` 通过；`PASSED` 报错；模板占位行 `PASS | BLOCKED（…） | BLOCKED（…）` 报错；`不是 PASS` / `未定` 报错；多小节报错。
- [x] 1.2 改写旧用例：`review manifest missing` 改为「无 manifest 不再报错」；保留 building-review 存在性门用例；新增 partial active change：`未定` 报告不报错、`BLOCKED` 报告仍报错（宽触发）；新增 active docs change 的 `BLOCKED` 报告用例（宽触发不绑回完成面条件）。
- [x] 1.3 新增 `--check-archived` 退役用例：带漂移 `spec_hash` / `tasks_hash` / 缺失 manifest 的归档 change 不再报错；历史归档（无 `## 闭环出口`）仍 exit 0；归档事件日志不可投影仍报错。
- [x] 1.4 新增归档点门用例：新建归档的 building-review 出口非 PASS / 缺失 ⇒ 报错；PASS ⇒ 通过；docs / 无 spec delta 的归档上 `BLOCKED` 仍报错、`未定` 不报错（宽触发 + 完成面）。
- [x] 1.5 新增文档守卫测试：扫描 `AGENTS.md` / `README.md` / `README_EN.md` / `docs/development-guide.md` / `docs/requirements-process.md` / `docs/interview-script/questions/{Q12-ci-testing,Q14-dev-process}.md`，断言不再出现 `building-review-manifest.json`、`write_review_manifest`、「review report 必须有 manifest」等旧要求，且 `witnessloop manifest build` / `## 闭环出口` 在场；排除 `docs/known-debt.md` 的历史记录与 `openspec/changes/archive/**`。
- [x] 1.6 运行指定测试确认**红**，记录原始输出。

## 2. 实现（checker）

- [x] 2.1 `scripts/check_openspec_artifacts.py`：删除 `_check_review_manifests` 与其 `verify_review_manifest` 调用；删除 `--check-archived` 的 manifest 校验、`tasks_hash` 汇总，以及只被旧函数使用的死代码 `_change_id_from_dir_name` / `_repo_root_for_change_dir`。
- [x] 2.2 新增 `_check_building_review` / `_review_exit_verdict` / `_review_exit_errors`，按四条规则解析：① 标题前缀匹配 `闭环出口`（容忍中文括号）；② 忽略 fenced code；③ 只认首个非空行，首个 token 后须有终止符（拒绝 `PASSED`），其后不得出现 `|` 分隔的其它终结 token（拒绝官方模板占位行），`PASS（...）` 合法；④ 多个同名小节报错。
- [x] 2.3 active `check_change` 用新函数替代旧调用：**宽触发**（报告存在且 terminal 非 PASS ⇒ 红，与类型/勾选无关）+ **完成面**（非 docs + spec delta + tasks 全勾 ⇒ 必须 PASS）。
- [x] 2.4 `_check_archived_completion_gate` 复用宽触发 + 完成面检查（完成面条件为非 docs + spec delta）；`--check-archived` 只保留 `_check_archived_projectable`，并保留既有 `change_type is None ⇒ continue` 语义。
- [x] 2.5 同步 help 文案、注释、docstring 与既有 CI 测试文案；确认 RIR / Impact / benchmark / backlog / 受保护路径 / grill 证据 / 归档点其它门逐行未动。
- [x] 2.6 `.github/workflows/ci.yml`：只改归档校验步骤的名称 / 注释，命令与 flag 不变。
- [x] 2.7 **全文件**同步本地入口 `/home/happy/my-agent/.claude/commands/review-loop.md`（描述、步骤 6/7、输出、护栏）：改为 `witnessloop manifest build` + `## 闭环出口`，不再产 ast manifest；改完 grep 确认无 `write_review_manifest` / `building-review-manifest` 字样。

## 3. 规则文档

- [x] 3.1 `AGENTS.md`：受保护 artifact 证据、强制审阅闭环、manifest 校验第二步、归档 manifest 段、阶段 C 降级清单。
- [x] 3.2 `README.md` 与 `README_EN.md` 同一句同步（审阅证据绑定 witnessloop manifest）。
- [x] 3.3 `docs/development-guide.md`：Review manifest 纪律改为 witnessloop 证据纪律 + `## 闭环出口` 格式；降级清单去掉 review manifest。
- [x] 3.4 `docs/requirements-process.md`：实现后闭环产物、受保护证据、checker 检查清单。
- [x] 3.5 `docs/interview-script/questions/Q12-ci-testing.md` 与 `Q14-dev-process.md`：manifest 与 checker 描述。
- [x] 3.6 `docs/known-debt.md`：新增退役记录（`diff_hash` 强校验、`--check-archived` 历史 drift 检测、非 building PASS 门、完成面之外的未终结报告、第二刀清单），并**标注既有四处变假段落**：`:25`（`/review-loop` 写 ast manifest）、`:31-33`（`--check-archived` 可检测/修复漂移）、`:158-206`（#232 A/B 机制）、`:232-241`（覆盖面隐含上界）。
- [x] 3.7 全仓 grep 复核：规范面不再要求产出 ast manifest（历史归档 / known-debt 历史记录除外）。
- [x] 3.8 新增 `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md`：记录「保留两套并派生 (d) / 下掉重复校验 / 统一 schema」的三个备选与选择理由（AGENTS ADR 规则：>= 2 个备选方案）。

## 4. 规格

- [x] 4.1 `specs/dev-workflow-gate/spec.md` delta：MODIFIED「review manifest 两套并存」→「单套承载」；MODIFIED 阶段 C Requirement 的「并存两套」Scenario。
- [x] 4.2 `specs/dev-workflow-state-machine/spec.md` delta：REMOVED「Review evidence manifest」；ADDED「Review evidence 与终结 verdict」；MODIFIED「审阅闭环的轮次模型」的机械门禁段。
- [x] 4.3 `specs/platform-gate/spec.md` delta：MODIFIED 降级理由清单，移除已不成立的 review manifest 例子。
- [x] 4.4 把三份 delta 施加进当前规格（同步对应 current spec 到 `openspec/specs/<capability>/spec.md`），记录 Requirement 计数前后变化，并写 `current_spec_synced` 事件。验收：`grep -c '两套并存' openspec/specs/dev-workflow-gate/spec.md` 必须为 0（delta 的 RENAMED 段除外）。
- [x] 4.5 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过。
- [x] 4.6 修 current spec 的悬空交叉引用：`openspec/specs/dev-workflow-gate/spec.md:45` 的「review manifest 两套并存」指向改名后的 Requirement；同步 Purpose 中的承载清单，并在 `current_spec_synced` 事件中说明非 Requirement 散文编辑。

## 5. 验证

- [ ] 5.1 `uv run pytest -q`（记录通过数与既有环境失败）。
- [x] 5.2 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 0 errors。
- [x] 5.3 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` → 仍 exit 0，且 stderr 不再出现 tasks_hash 汇总。
- [x] 5.4 变异验证：临时让 `_review_exit_verdict` 接受 BLOCKED，指定测试变红；恢复后转绿。

## 6. 实现后独立审阅闭环

- [ ] 6.1 跑 `/review-loop retire-manifest-check`，产出 `reviews/building-review.md`（含 `## 闭环出口`），收敛到 PASS。
- [ ] 6.2 按批次模型完成全部 medium+ 修复并补回归测试；low/nit 登记。

## 7. witnessloop 证据与出口判据

- [ ] 7.1 所有内容提交之后，用 `witnessloop manifest build` 产 `grill` / `grill-adversarial` / `building` 三份 manifest，`report_path` 覆盖 `reviews/` 下每一份 `.md`。
- [ ] 7.2 `witnessloop check --root . --base origin/master --head HEAD` → `check：通过 ✓`。
- [ ] 7.3 归档 move 之后用归档目录名重建三份 manifest，再跑一次 `witnessloop check`。
- [ ] (post-merge) 7.4 PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` 照跑。

## 8. 收尾（归档前完成）

- [ ] 8.1 `docs/openspec-change-backlog.md` 先登记本 change，再在证据产出之前移除；配 `backlog_updated` 事件。
- [ ] 8.2 `workflow-events.jsonl` 事件齐全：`change_created` / `backlog_updated`（登记）/ `current_spec_synced` × 3 / `protected_artifact_explained`（known-debt）/ `backlog_updated`（移除）/ `change_archived`。
- [ ] 8.3 结算 `tasks.md`：已完成项全部勾选；closeout 未完成项标 `(post-merge)`。
- [ ] 8.4 归档 move 前 `git add` 并确认 `reviews/` 报告已跟踪；手工 `git mv` 到 `openspec/changes/archive/2026-10-17-retire-manifest-check/`（独立提交）。
- [ ] 8.5 归档后核对：目录含三份报告与三份 witnessloop manifest，不含 ast manifest。

## 9. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 9.1 PR 用 `--merge` 合入，不用 squash。
- [ ] (post-merge) 9.2 在 issue #316 追加完成 comment（并提一句 #305 保持 OPEN）。
- [ ] (post-merge) 9.3 合入后确认：active change 目录不存在、backlog 干净、本地 `master` 已快进。

## 验收清单（对应 spec）

- [ ] V1 checker 不再要求 / 校验 asterwynd 形态 manifest；`agent/workflow/review_manifest.py` 未被修改。
- [ ] V2 building-review 的 `## 闭环出口` 必须为唯一 PASS；BLOCKED / 缺失 / 不唯一被拒。
- [ ] V3 `--check-archived` 不再做 manifest 漂移检测，仍做事件日志可投影校验。
- [ ] V4 RIR / Impact / benchmark / backlog / 受保护路径 / 归档点其它门行为不变（测试与 diff 证据）。
- [ ] V5 规范面与文档只要求 witnessloop 形态；本地 review-loop 入口已同步。
- [ ] V6 三份 witnessloop manifest + `gate / check` 绿。
- [ ] (post-merge) V7 PR 已 `--merge` 合入，issue 已留 comment。
