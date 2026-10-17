# Tasks: 删除 legacy asterwynd 形态 review manifest 生成模块与写通道（retire-manifest-module）

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → **用归档目录名**重建 witnessloop 三份 manifest → 机械复核。
> closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）执行设计追问，产出 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与 `## User Confirmation` 小节无条件存在）。
- [x] 0.2 逐项确认：删除面（模块 / CLI / 保护规则 / 忽略规则 / 测试）、保留面（artifact-event 归档解析、历史冻结、`## 闭环出口`）、内联解析的语义选择、文档与规格影响。
- [x] 0.3 跑设计阶段对抗闭环 → `reviews/grill-adversarial.md`；按批次模型开批 / 全修 / 只验证 / 收口，直到 PASS（无轮数上限，停止条件 = 收敛；无法收敛 ⇒ BLOCKED + 成因）。
- [x] 0.4 停轮检查：`grill-design.md` 没有需要用户拍板的 Open Question，且设计环出口为 PASS（或 BLOCKED + 成因 + 用户明确裁决继续）。任一不满足 ⇒ 停下报告。
- [x] 0.5 把 grill 与对抗闭环结论回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 先写红测试（TDD）

- [x] 1.1 `tests/test_workflow_state_cli.py`：把 `review-manifest` 加入 `REMOVED_SUBCOMMANDS`，断言未知子命令、非零退出；**单独**构造一个合法 target（proposal.md + reviews/building-review.md + tasks.md + specs/）并传完整参数，证明「恢复子命令会写 manifest」的探针在删除后消失（避免现有 `_seed_gen2_change` 无锚点导致平凡通过）；删除正向 `test_review_manifest_command_writes_manifest`。
- [x] 1.2 新增模块退役守卫：`agent/workflow/review_manifest.py` 不存在，且 `import agent.workflow.review_manifest` 失败；用 import 语句正则（`^\s*(from|import)\s+agent\.workflow\.review_manifest\b`）扫描全仓 `.py`（排除 `openspec/changes/archive/**`、`.venv/`、`.dev/`、`.git/` 与本守卫文件），不再存在 import；不要用裸子串扫描，避免命中退役说明自身。
- [x] 1.3 `tests/test_flow_policy.py`：断言 `-review-manifest.json` 不在策略表与 guard 默认表；`_is_privileged_cli` 对 `review-manifest` 返回 False、对 `artifact-event` 仍返回 True。
- [x] 1.4 `tests/agent/workflow/test_resume_audit.py`：新增「历史 `*-review-manifest.json` 改动被审计发现」的回归（当前实现因忽略项会恒绿）。
- [x] 1.5 `tests/test_workflow_archive_write_channel.py` / `tests/test_workflow_protected_write_channel.py`：删除 manifest 正向用例与 import；把仍需要判别的断言改到 `artifact-event` 上；保留归档、投影、非法 id 覆盖。兄弟前缀用例**断言 stderr 含「不存在」且不含「不匹配」**（区分旧 `re.match` + 调用侧断言路径）；新增同 id 多日期目录（`2026-01-01-alpha/` 与 `2026-02-02-alpha/`）用例：exit 1、明确多匹配错误、两个目录都未被写入。新增 guard 回归：Write/Edit `openspec/changes/archive/<date>-<id>/reviews/building-review-manifest.json` 仍命中归档前缀规则（exit 2）。
- [x] 1.6 `tests/test_retire_manifest_check.py`：文档守卫扩展为「规范文档不再指示**调用/导入形态**」（marker 用调用形态 `workflow_state.py review-manifest`——含裸调用与带参数调用——与 `agent.workflow.review_manifest`；同句含「已删除 / 已退役 / 不存在」时放行；不要把文件路径当裸 marker）。同时给守卫函数加**阳性/阴性对照**单测：含 `workflow_state.py review-manifest --change x` 的文本必须报错，含「`workflow_state.py review-manifest` 已删除」的文本必须放行；保留历史文件不被 checker 消费的用例。
- [x] 1.7 运行指定测试确认**红**，记录原始输出：1.1–1.5 与文档守卫在删除前应红（文档守卫的当前红点 = `AGENTS.md:115` 的「`workflow_state.py review-manifest` 作为 legacy 通道保留」，清理后转绿）。

## 2. 实现（删除）

- [x] 2.1 删除 `agent/workflow/review_manifest.py`。
- [x] 2.2 `scripts/workflow_state.py`：删除 `review-manifest` parser、`cmd_review_manifest`、`_resolve_review_base_sha`、模块 import 与因此未使用的 `subprocess` import；把归档目录解析内联为私有 helper（以 `CHANGES_ROOT / "archive"` 为根、`fullmatch` 精确匹配、按名排序；同 id 多日期目录 ⇒ 明确错误 fail-closed），保留 `artifact-event` 的 active 优先 → 归档回退行为；删除已不可达的 `_archive_dir_matches_change_id` 与调用侧断言；同步 `_is_archived_change_dir` / `_require_change_target` docstring。
- [x] 2.3 `scripts/flow-policy.json` 与 `scripts/workflow_guard.py`：删除 `-review-manifest.json` 保护规则、docstring 提及与 privileged CLI 豁免中的 `review-manifest`；**不改** `flow-policy.json` 的顶层 `_description`（不在 agent 合法写通道内），`manifest_verified` 无规则使用只记入 known-debt。删除策略规则走合法通道 `policy-set --delete --path=-review-manifest.json`（leading dash 必须用 `=` 形式），guard 内嵌默认表作为代码同步修改。
- [x] 2.4 `agent/workflow/resume_audit.py`：删除 `-review-manifest.json` 忽略项。
- [x] 2.5 `agent/workflow/__init__.py`：包说明移除 `review_manifest`。
- [x] 2.6 跑 1.1–1.6 的测试确认转绿；做一次变异验证（临时恢复任一删除面 → 对应用例变红）。

## 3. 规则文档

- [x] 3.1 `AGENTS.md`：受保护 artifact 证据、强制审阅闭环、flow 命令组段落改为「模块 / CLI / 保护规则已删除，历史文件冻结」；同步 `README.md:264` 与 `README_EN.md:264` 的目录树（双语必须同改，用词如「事件日志 + 受保护写通道」）。
- [x] 3.2 `docs/development-guide.md:294-300,324`：Review evidence 纪律说明模块与 CLI 已删除；`:324` 的「历史 manifest 的处置留给第二刀」改为已完成的冻结口径；保留 witnessloop 三份 manifest 命令。
- [x] 3.3 `docs/requirements-process.md`：checker / 证据说明改为「唯一活通道是 witnessloop 形态」。
- [x] 3.4 `docs/interview-script/questions/Q14-dev-process.md`：guard 与 legacy 模块描述改为已删除。
- [x] 3.5 `docs/known-debt.md`：更新 `:25`（legacy 写通道保留到第二刀）、`:168-177`（委托 `change_dir_for` / `cmd_review_manifest` 的收口描述）、`:186-192`（A-遗留 2 随内联解析关闭）、`:229`（已删模块的行号锚点）、`:516-537`（退役段第 5 项改为 legacy 已删除）与 `--check-archived` 历史冻结口径；写明 `manifest_verified` 当前无规则使用。
- [x] 3.6 `docs/adr/ADR-0004-retire-duplicate-review-manifest-check.md`：勾掉「第二刀启动」Revisit Condition 并指向 ADR-0005；新增 `docs/adr/ADR-0005-retire-legacy-review-manifest-module.md`。
- [x] 3.7 全仓 grep 复核：`grep -rnE "review[-_ ]manifest"` 仅剩历史归档、`review_manifest_glob`（witnessloop 配置）与本 change 自身的退役说明；`workflow_state.py review-manifest` 不再出现在任何可执行指示中；测试 docstring（`test_workflow_state_cli.py:3`、`test_workflow_archive_write_channel.py:4,181-182`、`test_workflow_guard.py:127`、`test_flow_policy.py:142`）逐处改准。

## 4. 规格

- [x] 4.1 `specs/dev-workflow-gate/spec.md` delta：MODIFIED「review manifest 单套承载：本仓形态退役」与阶段 A Scenario 的生成器表述。
- [x] 4.2 `specs/dev-workflow-state-machine/spec.md` delta：MODIFIED 受保护写通道 Requirement（含相关 Scenario）、Workflow 总开关、guard 写通道豁免 / 受保护路径规则。
- [x] 4.3 `specs/change-documentation/spec.md` delta：MODIFIED 受保护 artifact 写通道清单。
- [x] 4.4 把三份 delta 施加进当前规格（同步对应 current spec 到 `openspec/specs/<capability>/spec.md`），记录 Requirement 计数前后变化，并写 `current_spec_synced` 事件。
- [x] 4.5 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过（30/30）。

## 5. 验证

- [x] 5.1 删除前基线：`uv run pytest -q` = **3 failed / 4532 passed / 9 skipped**（2 条 `TestFindScopeRoot` 本机 `/tmp` 是 git 仓库的环境失败 + 1 条 `test_sandbox_backends.py::test_contract[docker]` Docker 契约超时）。
- [ ] 5.2 删除后全量：`uv run pytest -q`，不得引入**新的**失败；与 5.1 逐条对账并记录。
- [x] 5.3 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` → **exit 0（checks passed）**。
- [x] 5.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed / 0 failed**。
- [x] 5.5 `grep -rnE "review[-_ ]manifest"`（排除 `openspec/changes/archive/**`）只余 `review_manifest_glob`、本 change 退役说明与历史测试夹具；把结果贴进 PR。
- [x] 5.6 `workflow_state.py review-manifest` 实测未知子命令、非零退出、无副作用；`artifact-event` 对归档 change 实测仍可写入。

## 6. 实现后独立审阅闭环

- [x] 6.1 跑 `/review-loop retire-manifest-module`，产出 `reviews/building-review.md`（含 `## 闭环出口`），收敛到 PASS。
- [x] 6.2 按批次模型完成全部 medium+ 修复并补回归测试；low/nit 登记。

### 审阅结论（building R0）

- 独立零记忆审阅者（`building-2026-10-17-r1`）初次开批 **medium+ = 0** ⇒ **PASS（零轮）**；独立复核全量 pytest 为 2 failed / 4523 passed / 9 skipped（仅剩已知 2 条 `/tmp` 环境失败）。
- low/nit L1–L9 登记；处置：L1/L2/L3/L4/L5/L8/L9 已随本 change 顺手修复；L6（第一刀遗留的 `--check-archived` 口径）已补进本 change 的 MODIFIED Requirement 并同步 current spec；L7 为簿记项（5.5 在 backlog 移除后勾选）。

## 7. witnessloop 证据与出口判据

- [x] 7.1 所有内容提交之后，用 `witnessloop manifest build` 产 `grill` / `grill-adversarial` / `building` 三份 manifest，`report_path` 覆盖 `reviews/` 下每一份 `.md`（归档目录名；base origin/master）。
- [x] 7.2 `witnessloop check --root . --base origin/master --head HEAD` → 通过。
- [x] 7.3 归档 move 之后用归档目录名重建三份 manifest，再跑一次 `witnessloop check`。
- [ ] (post-merge) 7.4 PR 的 `gate / check` 判绿；`validate` / `benchmark-gate` / `windows-platform` 照跑。

## 8. 收尾（归档前完成）

- [x] 8.1 `docs/openspec-change-backlog.md` 先登记本 change，再在证据产出之前移除；同时把第十七批 `:116` 的「第二刀已立项」改为「第二刀已完成并归档」；配 `backlog_updated` 事件。
- [x] 8.2 `workflow-events.jsonl` 事件齐全：`change_created` / `backlog_updated`（登记）/ `current_spec_synced` × 3 / `protected_artifact_explained`（known-debt）/ `backlog_updated`（移除）/ `change_archived`，`approved_by` 均为 `human`。
- [x] 8.3 结算 `tasks.md`：已完成项全部勾选；closeout 未完成项标 `(post-merge)`。
- [x] 8.4 归档 move 前 `git add` 并确认 `reviews/` 报告已跟踪；手工 `git mv` 到 `openspec/changes/archive/2026-10-17-retire-manifest-module/`（独立提交，纯 rename）。
- [x] 8.5 归档后核对：目录含三份报告与三份 witnessloop manifest，不含 ast manifest；80 份历史 manifest 未变。

## 9. 合入之后（结构上无法在本 PR 内完成）

- [ ] (post-merge) 9.1 PR 用 `--merge` 合入，不用 squash。
- [ ] (post-merge) 9.2 在 issue #316 追加完成 comment（并提一句 #305 保持 OPEN）。
- [ ] (post-merge) 9.3 合入后确认：active change 目录不存在、backlog 干净、本地 `master` 已快进。

## 验收清单（对应 spec）

- [x] V1 模块文件不存在；`workflow_state.py review-manifest` 为未知子命令、无副作用。
- [x] V2 `artifact-event` 的 active / 归档 / gen-1 / 非法 id / 兄弟前缀碰撞**fail-closed 结论不变**（兄弟前缀错误文案由「不匹配」变为「不存在」，多日期目录新增明确错误）。
- [x] V3 策略表与 guard 默认表无 `-review-manifest.json`；`manifest_verified` 不再被任何规则使用。
- [x] V4 resume audit 能发现历史 manifest 改动。
- [x] V5 80 份历史 manifest 保持原样；checker 仍忽略其漂移。
- [x] V6 规格与规范文档只描述一套 manifest；`## 闭环出口` 判据未动。
- [x] V7 全量 pytest 无新增失败；artifact checker exit 0；openspec strict validate 30/30。
- [ ] (post-merge) V8 PR 已 `--merge` 合入，issue 已留 comment。
