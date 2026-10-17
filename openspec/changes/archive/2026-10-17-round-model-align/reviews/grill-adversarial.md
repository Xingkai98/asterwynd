# Grill Adversarial: round-model-align

## Reviewer
- run id: grill-adversarial-round-model-align-2026-10-17
- 时间: 2026-10-17（UTC）
- 零记忆: 是
- 对象: 设计（proposal/design/tasks/spec delta）
- 依据: 本仓 `openspec/changes/round-model-align/`、`AGENTS.md`、`docs/requirements-process.md`、`scripts/check_openspec_artifacts.py`、`scripts/workflow_state.py`、`agent/workflow/review_manifest.py`、`.witnessloop/policy.json`、`.github/workflows/witnessloop.yml`；上游 `Xingkai98/witnessloop` `origin/main` = `98b97b7046e98508470345ce081f7189c6c4269c`（已 fetch 核验）。

## 本轮判定（verdict）
**PASS**（最终；第 1 轮开批时为 `CHANGES_REQUESTED`，4 条 medium+；`ba746ed` 修复后逐条验证全部已修好；第 1 轮后收口确认为 0 条 medium+）。`## 闭环出口` 见文末。

逐项证伪结论：轮定义、批次冻结、验证期禁提新问题、deferred 传递、severity 冻结、20 上限与收口确认、第 20 轮自身终止点、按 change/环计数、两环共用、frontier 豁免、三出口（`CHANGES_REQUESTED` 不是出口）**均与上游 `templates/review-loop.md` 及归档 `2026-10-17-convergence-based-stop` 的规范文本一致**；delta 形状（REMOVED + MODIFIED + ADDED）实测 `openspec validate --all --strict` 为 **30 passed / 0 failed**；Impact Analysis 的 `d0197b1` 行号逐点复核成立。R1 的 4 条修复已逐条验证；R2 重审未发现新的 medium+。

### 第 1 轮 · 批次

| id | severity | 锚点（文件:行） | 问题 |
|---|---|---|---|
| R1-1 | high | `openspec/changes/round-model-align/tasks.md:71`；`scripts/workflow_state.py:375-379`；`scripts/check_openspec_artifacts.py:1105-1108,1148-1152`；`agent/workflow/review_manifest.py:135-155` | 任务 7.5 要求「在归档目录上用**归档目录名**重建**两套** manifest（asterwynd 形态 + witnessloop 三份）」。witnessloop 三份可以：`manifest build --change <归档目录名>` 会解析 `archive/<name>`。asterwynd 形态不行：`workflow_state.py review-manifest` 的 `_require_change_target` 明确拒绝日期前缀 id（`:375-379`），而 `--check-archived` 在归档目录上用 `_change_id_from_dir_name` 剥掉日期前缀后要求 `manifest.change_id` 等于**裸 id**（`check_openspec_artifacts.py:1105-1108,1148-1152`；`review_manifest.py:135-155`）。照 7.5 字面执行，要么 CLI 直接 exit 1，要么写出一份 `change_id mismatch` 的假 manifest。修法：把 7.5 拆成两条——witnessloop 三份用归档目录名（`--change 2026-10-17-round-model-align`），asterwynd 形态用裸 `round-model-align`（`--change round-model-align` 会走归档回退）并把 manifest 写进归档目录。 |
| R1-2 | medium | `openspec/changes/round-model-align/design.md:237`；`openspec/changes/round-model-align/tasks.md:24-27` | Testing Strategy 第 1 条要求测试断言「两份当前规格与 delta 的 Requirement 标题/正文一致」。这个 delta 在本 PR 的 7.4 会被 move 到 `openspec/changes/archive/2026-10-17-round-model-align/`：硬编码 active 路径的测试在归档提交后直接 `FileNotFoundError`；改成 glob 归档路径则把一份**冻结的历史 delta** 与**活的当前规格**永久绑死，之后任何一次规格演进都会误红。这正是 G6 / 上游 R9 已经否掉的「合入后失真的 diff/结构断言」，且 `tasks.md` 的 1.1–1.4 并没有这条断言，design 与 tasks 不一致。修法：删掉 equality 断言，改为单向「当前规格含新 Requirement 要素、不含旧口径」；delta 合法性由 `openspec validate --all --strict`（本次实测 30 passed / 0 failed）承担。 |
| R1-3 | medium | `openspec/changes/round-model-align/tasks.md:18`；`openspec/changes/round-model-align/specs/dev-workflow-state-machine/spec.md:196-214`；`openspec/changes/round-model-align/specs/change-documentation/spec.md:17-40`；上游 `witnessloop@98b97b7:templates/grill.md:228-231` | 设计环的三出口定义了 `BLOCKED`，但没有把「设计环出口」变成写代码的前置条件：`tasks.md:18`（0.4）只检查 `design.md` 无待用户拍板的 Open Question，**无 Open Question ⇒ 进入实现**；若对抗环以 `BLOCKED` 终结，Open Questions 仍为空，0.4 会放行实现。上游 `templates/grill.md:228-231` 明确要求「对抗验证已到 `PASS`，或 `BLOCKED` + 成因 + **用户已明确裁决继续**；`BLOCKED` 本身不能作为写码许可」，本 change 的 delta 与 AGENTS 没有这条。对照之下：实现环 `BLOCKED` 的 manifest verdict 不是 PASS，`verify_review_manifest` 会拦；设计环 `BLOCKED` 目前没有任何机械或规则拦截——「两环共用」在这里并不同构。修法：在 `dev-workflow-state-machine` delta 的「两环共用」段与 `change-documentation` delta 补「设计环 `BLOCKED` SHALL NOT 作为写码许可；仅 `PASS` 或用户明确裁决继续可写」，并同步 `tasks.md` 0.4 与 `AGENTS.md:18`。 |
| R1-4 | medium | `openspec/changes/round-model-align/specs/dev-workflow-state-machine/spec.md:127-130`（开批段）与 `:146-148`（验证期 low/nit）；上游 `witnessloop@98b97b7:templates/review-loop.md:71` | **开批时**发现的 low/nit 没有明确去向。delta 的批次段只规定开批「只列 medium+」；low/nit 的登记只写在「验证期」段。术语表与报告 schema 虽提到 low/nit 可登记，但按字面执行的开批审阅者可以**不登记**——这样「累积 low/nit」规则在 `PASS` 报告里会出现缺项，且没有一条规则会被违反。上游开批步骤明确写「`low` / `nit` **另列登记表**，不进入阻塞批次」（`review-loop.md:71`）。修法：在批次段补一句「开批时发现的 low/nit SHALL 直接进入本轮 low/nit 登记表」，并在 `design.md` Decision 1/4 对齐。 |

### 第 1 轮 · 验证

| id | 结果 | 修复提交 | 回归测试 / 设计环对应物 |
|---|---|---|---|
| R1-1 | **已修好** | `ba746ed` | 可复现反例：按旧 7.5 用日期前缀 `2026-10-17-round-model-align` 调 asterwynd `review-manifest`，被 `scripts/workflow_state.py:375-379` 拒绝；修复后 7.5 明确 witnessloop 三份用归档目录名、asterwynd 形态用裸 `round-model-align`（归档回退），与 `check_openspec_artifacts.py:1105-1108,1148-1152` 的裸 id 比对一致。 |
| R1-2 | **已修好** | `ba746ed` | 可复现反例：delta 在 7.4 归档 move 后 active 路径不存在，硬编码该路径的 equality 测试会 `FileNotFoundError`；glob 归档路径则把冻结 delta 与活规格永久绑死。`design.md` Testing Strategy 已删除 equality，改为单向「新 Requirement 要素在场、旧口径不在场」；`openspec validate --all --strict` 本次实测 30 passed / 0 failed，delta 合法性由其承担。 |
| R1-3 | **已修好** | `ba746ed` | 可复现反例：旧 0.4 在「设计环 `BLOCKED` + `## Open Questions` 为空」时仍写「进入实现」。`tasks.md:18` 已改为必须满足「Open Question 为空 **且** 设计环出口为 `PASS`（或 `BLOCKED` + 成因 + 用户明确裁决继续）」，并写明 `BLOCKED` 本身 SHALL NOT 作为写码许可；两份 delta、`design.md` Decision 6 与 `proposal.md` 需求 7 同步。 |
| R1-4 | **已修好** | `ba746ed` | 可复现反例：旧批次段只写开批「只列 medium+」，开批发现的 low/nit 没有登记落点。`specs/dev-workflow-state-machine/spec.md` 批次段已改为「只把 medium+ 列入 `B_n`；开批时发现的 low/nit SHALL 直接进入本轮 low/nit 登记表」；`design.md` Decision 1 与 `proposal.md` 需求 3 对齐。 |

**第 1 轮验证结论：R1-1 ~ R1-4 全部已修好 ⇒ 第 1 轮结束。** 验证期未发现新的 medium+，无新增 deferred。

### 第 1 轮 · 下一批（deferred）

| id | severity | 锚点 | 问题 | 来源 | 延后理由 |
|---|---|---|---|---|---|
| 无 | — | — | 第 1 轮验证期未发现新的 medium+。 | — | — |

### low / nit 登记

| id | severity | 处置（已修 / 登记不修） | 理由 |
|---|---|---|---|
| R1-L1 | low | **已修（ba746ed）** | `tasks.md` 5.1 已改为「产出报告 + reviewer run；asterwynd 形态 manifest 只在 7.5 的最终 revision 上生成」，与 `docs/development-guide.md:294-298`、`AGENTS.md:114` 的时序一致。 |
| R1-L2 | low | **已修（ba746ed）** | dev-workflow delta 的「第 20 轮收口后仍有 medium+」Scenario 的 THEN 已改为「**超上限 `BLOCKED`**」。 |
| R1-L3 | low | **已修（ba746ed）** | `tasks.md` 5.2 已改为「收口后清理中间轮产物」。 |
| R1-L4 | low | **已修（ba746ed）** | `tasks.md` 7.2 已改为「确保事件齐全（`change_created` 已有 seq 1）」，不再暗示追加重复事件。 |
| R1-L5 | low | **已修（ba746ed）** | `tasks.md` 7.4 已注明「若同一提交含新增报告，则不是纯 rename，如实记录」，不再把纯 rename 当成硬前提。 |
| R1-L6 | low | 登记不修 | 本地入口逐项登记「已改 / 未改」的措辞仍有歧义；`design.md` 已写「必须单独同步」，且该入口被 gitignore、不进门禁。 |
| R1-L7 | low | 登记不修 | backlog 的「登记」动作仍没有独立的 `backlog_updated` 事件；收尾写一条 `backlog_updated`（移除）即可让 witnessloop `covers` 覆盖该路径，严格逐次解释可在实现时补。 |
| R1-L8 | low | 登记不修 | `docs/requirements-process.md:189` 的 verdict 列表可只写 `PASS` / `CHANGES_REQUESTED`；规范 delta 是权威口径，prose 摘要在实现时补 `BLOCKED` 即可。 |
| R2-L1 | low | 登记不修 | 新加的「设计环出口是写码前置条件」未纳入 `AGENTS.md` 的 per-file 映射（`design.md` Decision 8 / `tasks.md` 1.2）；规则已在 Decision 6、0.4 与两份 delta，per-file 映射刻意只钉核心要素；实现 AGENTS 改写时顺手带上。 |
| R2-L2 | low | 登记不修 | `design.md` Decision 6 的「与实现环的 manifest verdict 非 PASS 即拦截同构」容易被读成**机械**同构；Decision 7 明确本 change 不新增正文解析，实际是**流程**同构。建议改为「流程同构，非机械同构」。 |
| R2-L3 | low | 登记不修 | `design.md` Decision 3 未写「第 20 轮收口确认只发现 low/nit ⇒ 仍可 `PASS` 且用 `C-*`」；dev-workflow delta 已写，规范以 delta 为准。 |
| R2-L4 | low | 登记不修 | `tasks.md` 0.4 说检查 `design.md` 的 Open Questions；权威记录是 `grill-design.md`（write guard 读它）。两处当前都是「无」；建议把 0.4 的措辞改为 `grill-design.md`。 |
| R2-L5 | low | 登记不修 | `design.md` Decision 8 的 AGENTS 映射写「验证禁提新问题/deferred」，`tasks.md` 1.2 只写「deferred」；映射粒度轻微不一致，不影响可执行性。 |

### 第 1 轮后 · 收口确认

- 审阅时间: 2026-10-17（UTC）
- 范围: 完整重读 `proposal.md` / `design.md` / `tasks.md` / 两份 spec delta，并与上游 witnessloop `templates/review-loop.md`、`templates/grill.md` 及归档 `2026-10-17-convergence-based-stop` 对照；`openspec validate --all --strict` = 30 passed / 0 failed。
- 结论: **0 条 medium+ ⇒ `PASS`**。第 1 轮 deferred 0 条；R2 开批新发现 low/nit 为 R2-L1–R2-L5（已登记）；R1-L1–R1-L5 已在 `ba746ed` 修好，R1-L6–R1-L8 登记不修。

## 闭环出口
PASS（依据 `### 第 1 轮后 · 收口确认`：收口确认 0 条 medium+；累积 low/nit 见登记表）。
