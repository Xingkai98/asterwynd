# Grill Adversarial: slim-gates

## Reviewer
- run id: grill-adversarial-slim-gates-20261018-r1
- 被审 revision: working tree（HEAD `528d02f` + 未提交的 `openspec/changes/slim-gates/` 与 `docs/openspec-change-backlog.md`）
- 依据：旧实现 `528d02f:scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`；witnessloop v1.7.0 源码（标签 `v1.7.0^{commit}` = `c9b2811`；本机 `/tmp/wl-v1.7.0` 与 tag 逐字节一致）；SPIKE `e9d23af`

## Round 1

### 批次（blocker/high/medium）

- **I-1（blocker）｜SPIKE 的文档 hunk 与最终形态相反，Decision 7 只排除 specs/backlog，cherry-pick 会把假事实落进受保护/核心文档**：SPIKE 是「全删」版本，它的 AGENTS/开发指南/known-debt/ADR/interview-script 都写着「checker 删除、platform gate 删除、六条规则不再有任何机械实现」。本 change 的最终形态是「checker 存在（重写）、platform gate 四项保留、补 Bash guard」，两者正相反；而 Decision 7 的冲突处理只排除 `docs/openspec-change-backlog.md` 与 `openspec/specs/**`，tasks 3.4 照抄该口径，tasks 3.6 的文件清单不含 `docs/known-debt.md` 与 `docs/adr/**`。证据：`git show e9d23af:AGENTS.md` 的 `:205`（`scripts/platform-gate.json 已删除`）与 `:209`（`branch protection 不再有仓内配置即代码`）；`e9d23af:docs/development-guide.md:336`（`check_openspec_artifacts.py`/`platform_gate.py` 已移除、项目特有检查「不再有任何机械实现」）；`e9d23af:docs/known-debt.md:3`（把 `platform_gate.py`/`check_openspec_artifacts.py` 列为「已删除的实现」）；`e9d23af:docs/adr/ADR-0004:3`、`ADR-0005:3`、`ADR-0007:3`（同样说 checker 已删除）；`e9d23af:docs/interview-script/questions/Q12-ci-testing.md:39`、`Q14-dev-process.md:46`（platform gate「曾提供」）；`design.md:149-155`（Decision 7 的排除清单）；`tasks.md:74-76`（3.4）；`tasks.md:79-87`（3.6 未列 known-debt / ADR）；`tasks.md:122`（known-debt 事件写成「若 SPIKE 的横幅被采用」）。复现：`git show e9d23af:AGENTS.md | sed -n '205p;209p'`、`git show e9d23af:docs/development-guide.md | sed -n '336p'`。后果：按现设计执行，PR 会同时（a）在受保护文件 `docs/known-debt.md` 里写假事实；（b）让 witnessloop 因该文件被改却没有 `protected_artifact_explained` 事件而判红（条件式任务 6.1 可能被跳过）；（c）留下「platform gate 已删」的文档与 Decision 6 正面矛盾。修法：cherry-pick 时显式排除这些文档 hunk（或在 3.4 后逐条改写）；把 `docs/known-debt.md`、`docs/adr/**` 写进 3.6 的逐文件清单；6.1 的 known-debt 事件改为无条件（只要最终 diff 触及该文件），并在 tasks 里写明「保留的 platform gate / 重写的 checker 仍是现行实现」。

- **I-2（high）｜grill-adversarial 证据在「不触达 require_change_for」的 change 上被静默放宽**：旧归档门对 `非 docs + DESIGN_TYPES + spec delta` 无条件要求 `reviews/grill-adversarial.md`（`528d02f:scripts/check_openspec_artifacts.py:1753-1762`）；新 checker 删掉该检查并声称「移交 witnessloop」（`design.md:214` Decision 11），但 witnessloop 的 `grill-adversarial` stage manifest 只在 `code_hits` 非空时才要求（`/tmp/wl-v1.7.0/src/witnessloop/checkcmd.py:193`，`_code_hits` 见 `:266-282`），而 `code_hits` 的口径是 `agent/**`、`scripts/**`、`web/**`（`.witnessloop/policy.json`）。反例：一个 `primary: process` 的 change 只改 `openspec/specs/**` + `docs/**`（例如纯规格对账），有 spec delta、无 `reviews/grill-adversarial.md`：旧 checker 在归档点判红，新 checker 判绿，witnessloop 也不要求该 stage（`code_hits` 为空）。这与 proposal 「不声称只删了六条规则之外无损失」的承诺不一致，且 Decision 11 的「移交 witnessloop」没有注明触发面差异。修法：把该损失如实登记并给出裁决（保留一条 checker 侧存在性判据、或改 policy 触发面、或经用户确认接受损失）；不能继续写成「已覆盖」。

- **I-3（high）｜MODIFIED `review manifest 单套承载：本仓形态退役` 静默删掉仍在生效的 Scenario（尤其 stale 顺序约束与 reviews/ 孤儿激活条件）**：现行规格在 `openspec/specs/dev-workflow-gate/spec.md:162-175` 有 `#### Scenario: reviews/ 必须处于一致状态（孤儿规则的激活条件）` 与 `#### Scenario: 证据的 stale 顺序约束`，后者明确「在所有内容提交之后产出证据；触碰 `docs/**` 与 `openspec/specs/**` 的收尾步骤排在证据产出之前」。delta 的同一 Requirement（`openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:80-97`）只保留「历史 manifest 冻结」与「building review 终结判据」两个 Scenario，把上述两条连同「本仓形态退役的边界」「glob 不放宽的理由可复核」「局部应用成熟模式而非另立协议」（现行 `:26-30`）一并删除。这些不只是历史描述：stale 顺序正是本 change 自己的 tasks 6.1–6.6 依赖的硬约束（witnessloop `contract._check_git_span` 的 `stray` 判定见 `/tmp/wl-v1.7.0/src/witnessloop/contract.py:738-760`，豁免集见 `policy.py:77-92`），删掉后规格不再承载该不变量。反例：后续 change 先 build manifest 再提交 `openspec/specs/**`/`docs/**`，规格层面没有任何条款可引用。修法：把两条 Scenario（至少 stale 顺序与孤儿激活条件）原样保留进 delta，或在 design/tasks 明确记录「有意删除 + 新载体」。

- **I-4（high）｜tasks 6.3/6.4/6.5 缺「先提交内容、后提交证据」的 commit 边界，`head_sha` 会绑到错误 revision**：`manifest build` 用 `head_sha = git rev-parse HEAD`（`/tmp/wl-v1.7.0/src/witnessloop/manifestcmd.py:155-157`），而 `check` 把 `head_sha..被检 head` 之间的非证据文件判 stale（`contract.py:738-760`）；`changes/*/tasks.md` 与 `docs/**` **不在** `stale_exempt_paths`（`policy.py:77-92`）。tasks 顶部顺序注只说「事件 → backlog 清理 → tasks 结算 → 归档 move → build → check」（`tasks.md:8-10`），6.4 又要求「独立 rename 提交」（`tasks.md:129-130`），6.5/6.6 没有「先把 6.1–6.3 与所有内容提交掉」「build 后把报告+manifest 单独提交」这两步。反例：作者按 6.4 只提交 rename（`git mv` 已 staged，6.1–6.3 的内容仍 unstaged）→ 6.5 build 的 `head_sha` 不含 tasks/backlog 改动 → 之后把内容随证据一起提交 → `check` 报「审阅的是旧 revision」（`tasks.md`/backlog 为 stray）。历史 change 已踩过同型坑（`openspec/changes/archive/2026-10-17-stage-c-required-switch/tasks.md:59` 明确写「`changes_root/*/tasks.md` 不在 stale_exempt_paths 内」）。修法：把顺序改成「提交所有内容（含 6.1–6.3）→ 归档 move 提交 → build → 提交证据（reports+manifests）→ 最终 check → PR」，并在 6.4/6.5 行内写明 commit 边界。

- **I-5（high）｜T8/6.5/6.6 的 witnessloop v1.7.0 锚点不可照抄执行，且设计里指定的本机路径不是 v1.7.0**：design 称「v1.7.0（`00192ab`）」，但 `00192ab` 是 annotated tag object，不是 commit（`git cat-file -p 00192ab` → `object c9b2811... type commit`，`git rev-parse 'v1.7.0^{commit}'` = `c9b2811`）；任务里写的源码路径 `/home/happy/witnessloop` 当前 HEAD 是 `ae99256`，`git -C /home/happy/witnessloop describe --tags --always HEAD` = `v1`，且 `## main...origin/main [behind 129]` —— 它是 v1.6.0 附近的旧树，与 v1.7.0 的 `checkcmd.py`/`contract.py`/`manifestcmd.py` 差异巨大（`git diff v1.7.0 HEAD --stat`：checkcmd 194 行、contract 479 行、manifestcmd 58 行）。按 `docs/development-guide.md:390-395` 的规范命令 `cd <witnessloop> && uv run witnessloop check` 执行会跑旧版，得到假绿/假红。可执行的现有锚点是 `/home/happy/wl170/bin/witnessloop`（实测 `constants.DEFAULT_GATE_REF` = `@v1.7.0`）。修法：在 Testing Strategy/T8 与 tasks 6.5/6.6 写死一条可复制命令（如 `/home/happy/wl170/bin/witnessloop manifest build ...` / `... check --root . --base origin/master --head HEAD`），或先 `git -C /home/happy/witnessloop checkout v1.7.0` 再 `uv run`；同时把「commit 00192ab」改为「tag object `00192ab` → commit `c9b2811`」。

- **I-6（medium）｜`multi-agent-collaboration` 改指 `agent/subagent/workflow_store.py`，但保留的括注描述该模块并不具备**：delta（`openspec/changes/slim-gates/specs/multi-agent-collaboration/spec.md:7`）写「reuse the `agent/subagent/workflow_store.py` persistence discipline (JSON serialization + schema_version + transition log style)」。实际的 `agent/subagent/workflow_store.py` 没有 `schema_version`，也没有 transition log；它是 artifact 原子写 + `events.jsonl` 追加（模块 docstring 与 `append_event`）。`schema_version` 在 `agent/subagent/workflow.py:28`（`SCHEMA_VERSION = "workflow.v1"`）。修法：把括注改为该模块实际承担的纪律，或把 schema_version 来源另指 `agent/subagent/workflow.py`，不要保留一个「指针 + 不存在的字段」组合。

- **I-7（medium）｜`change-documentation` delta 把有界批次模型指向 `dev-workflow-gate`，但后者没有该 Requirement**：delta（`openspec/changes/slim-gates/specs/change-documentation/spec.md:24-25`）写「defined by the project review rules in `AGENTS.md` and the `dev-workflow-gate` capability」。现行唯一的规格级定义在 `openspec/specs/dev-workflow-state-machine/spec.md:426`（本 change 要删除它），而 `dev-workflow-gate` 的 delta（`:5-210`）没有承载有界批次模型的 Requirement。修法：把该 Requirement 迁进 `dev-workflow-gate` delta，或删掉 `and the dev-workflow-gate capability` 只引用 AGENTS.md。

- **I-8（medium）｜删除 `dev-workflow-state-machine` 规格后仍留悬空能力域引用，tasks 3.6 未逐项覆盖**：`openspec/project.md:40` 仍写 `- dev-workflow-state-machine: 多阶段开发流程状态机，包含五阶段生命周期、handoff.json...`，而 tasks 3.6 对 project.md 的要求只有「清理旧脚本、旧 policy、flow status 引用」这一泛化措辞，没有一个任务明确要求删除/改写该能力域条目。后果：归档后 `openspec/project.md` 的能力域地图指向已删除的规格。修法：在 1.5 或 3.6 增加明确条目「从 `openspec/project.md` 能力域地图移除 `dev-workflow-state-machine`（或改写为历史说明）」。

- **I-9（medium）｜spec delta 要求「两 hook 并存至少做一次本地实测」，但任务清单没有任何实测/记录任务**：delta（`openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:98-113`）要求「hook 的合并/串行语义与拦截提示归属 SHALL 在安装文档中写明，并至少用一次本地实测确认」，而 tasks 2.4–2.7 只测 guard 本体，4.7 只手工验收 Bash guard，3.6 只写文档；没有一条任务产出该实测记录。修法：增加一个明确的验收任务（主 checkout + building worktree 至少各一次，记录两个 hook 都执行/并集阻断/提示归属），或按用户裁决把「至少一次」降级并同步改规格。

- **I-10（medium）｜把 `git checkout --` / `git restore` / `git apply` / `merge` / `rebase` / `cherry-pick` / `stash` 统称「VCS 簿记」并放行，理由不成立且低估绕过面**：design（`design.md:99-103`）与 delta（`specs/dev-workflow-gate/spec.md:156`）用「Write/Edit 无法删除或改名文件」为整组放行辩护；但该理由只覆盖 `git rm` / `git mv` 的删除/改名，`git checkout --`、`git restore`（非 `--staged`）、`git apply`、`git merge/rebase/cherry-pick/stash` 都会直接改写受管路径的文件内容。反例：`git restore agent/loop.py` 或 `git apply /tmp/patch` 可在没有任何 guard 反馈的情况下改写 `agent/**`。修法：把「删除/改名」与「内容写入」分开——只放行 `git rm`/`git mv`，或明确把后一组登记为「有意放行的内容写入绕过面」（而不是「簿记」），并写进开发指南的残余绕过面。

- **I-11（medium）｜受保护写入移交 witnessloop 时丢失 `change_id` 与 `schema` 校验，规格未登记该退步**：旧 checker 校验事件 `schema == "workflow-event/v1"` 且 `change_id` 与事件日志所属目录一致（`528d02f:scripts/check_openspec_artifacts.py:1328-1338`）；witnessloop 的 `Event` 只解析 `event_type/artifact_path/reason/approved_by`（`/tmp/wl-v1.7.0/src/witnessloop/events.py:37-46`），`covers` 只比 exact path + 类型 + 非空字段（`:106-121`），不读 `change_id`/`schema`。后果：任意 change（含历史归档）的事件都能覆盖本 PR 的受保护写入。Decision 11 与 `change-documentation` 的「机械门禁的信任边界」没有登记这一具体退步（只写了防误改/防伪造）。修法：在 Decision 11 与信任边界规格中如实记录「change_id/schema 绑定不再校验」，或保留一条 checker 侧的轻量校验（需与「六条规则」边界一起裁决）。

- **I-12（medium）｜benchmark smoke 判据在 delta 里被写成「条目级」，与旧实现的文件级子串语义不一致**：旧实现是 `"benchmark" in lowered and "smoke" in lowered`（整份 tasks 文本，`528d02f:scripts/check_openspec_artifacts.py:667-669`）；delta（`openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:123`）写「`tasks.md` SHALL 含同时出现 benchmark 与 smoke 的条目」。「条目」按行/按任务项读会比旧实现更严（且 design 声称「判据一致」）：反例 `- [ ] 4.1 benchmark-gate 跑通` 与 `- [ ] 4.2 smoke 记录` 分两行时旧实现通过、按「同一条目」读法会红。修法：改成「tasks.md 文本中同时出现 benchmark 与 smoke（不要求同一行）」，或明确记录这是有意收紧。

### low/nit 登记

- **L-1（low）｜grill L2 只回写了一半**：proposal `:138` 仍写「删除旧门禁测试约 7028 行」（净删是 6526，502 行 platform gate 测试被恢复），design `:201` 仍写「platform gate 三件套（脚本 / JSON / 测试 / 规格）」（四个产物却叫三件套）。理由：纯事实数字/措辞，不影响判据；归档前一并订正即可。
- **L-2（low）｜tasks 6.2 的判红理由不成立**：当前 backlog 里的 `slim-gates` 是「后续批次」散文 bullet（`docs/openspec-change-backlog.md:115`），不匹配 checker 的 `### <n>. \`id\`` 模式；移除它并不会影响 `check_backlog_consistency`。理由：任务本身仍应执行（生命周期要求），只是理由文案不准。
- **L-3（low）｜`tests/test_round_model_alignment.py` 有三处引用已删状态机规格**：ALLOWLIST `:29`、PER_FILE_REQUIRED `:69`、专用单测 `:141`；tasks 2.8 的「移除条目与对应单测」可能只覆盖前两处之一，漏掉 per-file 映射会让测试红。理由：实现时跑测试必然暴露，属机械修正。
- **L-4（low）｜Bash guard 测试未覆盖 delta 枚举的全部写操作**：delta `:151` 列了 `rmdir`/`unlink`/`truncate`/`ln`/`chmod`/`chown`/`perl -i`/`ruby -i`/`curl -o`/`wget -O`，tasks 2.4 的清单只覆盖其中 10 种；`eval` 也没进 2.4。理由：同一 tokenizer 分支，补参数化用例即可，不改变判据。
- **L-5（low）｜残余绕过面清单漏了常见的静态可写形态**：`cp -t dir src` / `mv -t dir src`（目标在 `-t` 后、不在最后一个参数）、`install` 的源/目的、以及「任何被执行的程序/脚本（`python x.py`、`make`、`uv run …`）都能写受管路径」未登记。理由：guard 明确是本地 checkpoint，非对抗；但清单应如实扩展到这些类别。
- **L-6（low）｜Decision 12 的 CLI 行为映射漏了两个旧边界**：空/空白 `--base-ref` 视同省略、`--change` 的归档后缀 decoy（旧测试 `test_empty_base_ref_does_not_skip_checks` / `test_change_dir_in_any_form_rejects_suffix_decoy`）。理由：影响小，补两条测试即可。
- **L-7（low）｜`tests/agent/tools/test_guard_three_state.py:516` 的示例命令无需改**：checker 路径在重写后仍存在（只是判据变瘦），SPIKE 把它换成 `scripts/self_check.py` 并非必要；Decision 10 的「指向旧 checker」理由不准确。理由：无害，保留/改回均可，但不应写成「必须修」。
- **L-8（low）｜AGENTS.md 的分支纪律句会变成假事实**：`AGENTS.md:18` 说「门禁依赖分支名推导 change-id」；新 guard 不推导 change id，tasks 3.6 未点名该句。理由：文档措辞，随 3.6 的 AGENTS 改写一并处理。
- **L-9（low）｜`docs/requirements-process.md:50` 的 workflow 总开关说明未点名**：它引用 `workflow_methods.json` 与 `workflow_state.py disable/enable`；tasks 3.6 列出该文件但只给了泛化清理要求。理由：同属文档清理面，不阻塞。

### deferred（验证期若发现新 medium+ 才写）
- **D-1（medium）｜I-2 修复引入新的规范冲突**：`dev-workflow-gate` delta 的归档完成度要求检查 `grill-design.md` 正文（≥3 决策、Open Question 确认）与 `grill-adversarial.md`（`openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:157,176-181`），但 `change-documentation` delta 仍写 checker 只做六条规则，且「does not check review manifests, protected-path events, or grill report bodies (witnessloop owns those)」（`openspec/changes/slim-gates/specs/change-documentation/spec.md:122-137`）。两份 delta 对同一 checker 的职责边界互相矛盾；下一批需统一（把 grill 证据显式写成归档完成度的一部分并改「六条」口径，或改回不检查正文）。属验证期新发现，不计入本轮修复判定。
- **D-2（medium）｜I-4 的终态勾选与「纯 rename 提交」冲突**：tasks 的结算体例说 6.4–6.6「在归档 commit 的 `tasks.md` 里按终态勾选」（`openspec/changes/slim-gates/tasks.md:127-129`），但 6.4 又要求该提交「不得夹带内容改动」（`tasks.md:145-146`）；若改在 6.5 的 evidence 提交里补勾，`tasks.md` 不在 stale 豁免集且会改变 `tasks_hash`。需明确把 6.4–6.6 的终态勾选放进 6.3 的「内容提交」并改写「归档 commit」措辞，或另给可执行顺序。属验证期新发现，不计入本轮修复判定。

### 验证

> 仅核对 Round 1 批次 I-1…I-12 与已登记 low/nit 的修复落点；验证期新发现的 medium+ 见 deferred，不计入本轮修复判定。

- **I-1 已修复**：Decision 7 改为只取代码 / 测试 / CI 的删除，`AGENTS.md`、`docs/**`（含 `docs/known-debt.md`、`docs/adr/**`、interview-script）、`openspec/specs/**`、`openspec/project.md`、`openspec/templates/tasks.md`、backlog 全部从 HEAD 恢复后手工重写（`design.md:154-171`）；tasks 3.4 列全恢复清单（`tasks.md:81-86`）；3.6 加入 `docs/known-debt.md` 与 interview-script（`tasks.md:89-99`）；6.1 的 known-debt 事件改为无条件（`tasks.md:137`）。
- **I-2 已修复**：Decision 2 明确 non-code change 的 witnessloop 触发面差异并在归档点保留两份 grill 证据（`design.md:56,65-70`）；Decision 11 增加归档点专属行（`design.md:233`）；tasks 2.2 加测试要求（`tasks.md:47-48`）；delta #4 与 Scenario 明确非 docs + DESIGN_TYPES + spec delta 的 grill-design / grill-adversarial 要求（`specs/dev-workflow-gate/spec.md:157,176-181`）。修复引入的规范冲突见 deferred D-1。
- **I-3 已修复**：delta 补回「本仓形态退役的边界」「glob 不放宽的理由可复核」「reviews/ 必须处于一致状态（孤儿规则的激活条件）」「证据的 stale 顺序约束」四个 Scenario（`specs/dev-workflow-gate/spec.md:92-123`），并在第一 Requirement 补回「局部应用成熟模式而非另立协议」（`:24-28`）。
- **I-4 已修复（commit 边界部分）**：tasks 顶部与 6.3 / 6.4 / 6.5 写明「内容提交 → 纯 rename → build → evidence 提交 → final check」（`tasks.md:8-12,142-151`）。新增的终态勾选措辞矛盾见 deferred D-2。
- **I-5 已修复**：T8 与 tasks 6.5 / 6.6 写死 `/home/happy/wl170/bin/witnessloop`，并注明 tag object `00192ab` → commit `c9b2811`、`/home/happy/witnessloop` 不是 v1.7.0（`design.md:325`、`tasks.md:149-153`）。
- **I-6 已修复**：multi-agent delta 改为 `workflow_store.py` 的原子 per-key 写 + 权威 `events.jsonl` 纪律，schema_version 指 `agent/subagent/workflow.py`（`specs/multi-agent-collaboration/spec.md:7`）。
- **I-7 已修复**：有界批次模型只引用 `AGENTS.md`，已删除 `dev-workflow-gate` capability 交叉引用（`specs/change-documentation/spec.md:24-25`）。
- **I-8 已修复**：tasks 1.5 要求从 `openspec/project.md` 能力域地图移除 / 改写 `dev-workflow-state-machine`（`tasks.md:38-39`）。
- **I-9 未修复**：新增的 tasks 4.8 只「分别调用」两个 guard，未实测「两个 hook 同时安装」、hook 的合并 / 串行语义与拦截提示归属；而 delta 明确要求这些实测记录（`specs/dev-workflow-gate/spec.md:133,137-146` vs `tasks.md:115-117`）。「分别调用」不能证明「两个 hook 同时启用」时哪个 hook 求值，也不能验证提示归属，`未知语义不靠推理` Scenario 仍未落地。
- **I-10 已修复**：design 与 delta 改为只放行 `git rm` / `git mv`；显式路径的 `git restore` / `git checkout --` / `git apply`（非只读形态）拦截；merge / rebase / cherry-pick / stash / am 登记为内容写入绕过面（`design.md:106-113,122-125`、`specs/dev-workflow-gate/spec.md:196-203,229-237`）。
- **I-11 已修复**：Decision 11 增加「事件 `schema` / `change_id` 一致性退役」行（`design.md:236`）；change-documentation delta 增加退步说明与 Scenario（`specs/change-documentation/spec.md:274,290-294`）。
- **I-12 已修复**：benchmark smoke 改为「`tasks.md` 文本中同时出现 benchmark 与 smoke（与旧实现一致，不要求同一行或同一条目）」（`specs/dev-workflow-gate/spec.md:156`）。
- **low/nit 复核（均已处理）**：L-1 proposal / design 的数字改为 6526、platform gate 称四项（`proposal.md:41,138`、`design.md:23`；`proposal.md:44` 的 7028 是 SPIKE 统计说明，正确）；L-2 tasks 6.2 已改为真实理由（`tasks.md:140-141`）；L-3 Decision 10 与 tasks 2.8 覆盖三处引用（`design.md:211-214`、`tasks.md:66-68`）；L-4 tasks 2.4 已枚举全部写操作与 `eval`（`tasks.md:52-57`）；L-5 残余绕过面已扩展（`design.md:122-125`）；L-6 Decision 12 已加空 base-ref / 后缀 decoy（`design.md:261-262`）；L-7 Decision 10 已改为「非必须」（`design.md:215-216`）；L-8 / L-9 tasks 3.6 已点名分支纪律句与 workflow 总开关（`tasks.md:92-94`）。
- **机械复核**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 30 passed / 0 failed；`uv run python scripts/check_openspec_artifacts.py --change slim-gates` → passed。

### 收口确认
- **非空**：I-9 未修复（tasks 4.8 未覆盖「同时启用 / 合并串行 / 提示归属」的实测，无法满足 delta 的双守卫 Requirement）。其余 11 条 batch 项已核对到修复落点；D-1 / D-2 为验证期新发现，只进下一批 deferred。

## 闭环出口
CHANGES_REQUESTED（I-9 未修复；D-1 / D-2 入下一批 deferred）

## Round 2

### 批次（blocker/high/medium）
- **I-9（medium，Round 1 遗留）**：两 hook 同时安装的实测与记录是否满足 delta 的「双守卫并存」Requirement。
- **D-1（medium，Round 1 deferred）**：`change-documentation` delta 与 `dev-workflow-gate` 归档点 grill 证据规则的职责边界是否不再矛盾。
- **D-2（medium，Round 1 deferred）**：section 6 的终态勾选点与「纯 rename」提交是否不再冲突。

### low/nit 登记
- 无新增。

### deferred（验证期若发现新 medium+ 才写）
- 无（本轮三项全部通过，验证期未发现新的 medium+）。

### 验证
- **I-9 已修复**：tasks 4.8 已改为「两 hook **同时安装**实测」：在临时 Claude Code settings 中同时挂 witnessloop plugin guard（`Write|Edit`）与 `scripts/bash_write_guard.py`（`Bash`），用同一组 Write / Edit / Bash payload 触发，并逐项记录（a）两个 hook 是否都执行、（b）串行 / 并行与并集阻断语义、（c）被拦时提示归属、（d）Write/Edit 只由 witnessloop 求值、Bash 只由本仓 guard 求值；若本机无法安装 plugin，须如实记录「未实测」并停下报告，且明确禁止用「分别调用」冒充同时启用（`openspec/changes/slim-gates/tasks.md:115-120`）。该记录落点写入 `docs/development-guide.md` 的本地守卫节，覆盖 delta 的 Requirement 与两个 Scenario（`openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:133,135-146`）。
- **D-1 已修复**：`change-documentation` delta 的 Mechanical artifact checks 已改为 checker 不重复 witnessloop 的 **active-stage** grill 检查，并明确归档点 grill 证据（grill design + adversarial reports）属于 `dev-workflow-gate` rule 4 的归档完成度，不是第七条规定；Scenario 同步为「不检查 active-stage grill report bodies + 归档点证据属于归档完成度规则」（`openspec/changes/slim-gates/specs/change-documentation/spec.md:126-143`）。与 `dev-workflow-gate` rule 4（`specs/dev-workflow-gate/spec.md:157,176-181`）职责边界一致，不再矛盾。
- **D-2 已修复**：section 6 的结算体例已改为 6.4–6.6 在 **6.3 的最终内容提交**里按终态勾选；6.4 的归档 move 提交必须是纯 rename（不再改 `tasks.md`）；6.5 的 evidence 提交只含 reports/manifests（`openspec/changes/slim-gates/tasks.md:130-134`）；6.3 的「随后提交所有内容改动」与 6.4 的「不得夹带内容改动」、6.5 的 evidence-only 现在自洽，且 `tasks_hash` 在 build 前已固定。
- **机械复核**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 30 passed / 0 failed；`uv run python scripts/check_openspec_artifacts.py --change slim-gates` → passed。

### 收口确认
- **空批**：I-9、D-1、D-2 三项全部验证通过；验证期未发现新的 medium+。

## 闭环出口
PASS
