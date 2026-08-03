# Grill: grill-confirmation-gate 设计追问

## Reviewer

- run id: grill-subagent-grill-confirmation-gate-design-review
- 时间: 2026-08-02

本追问是 #96 grill-confirmation-gate 的独立设计评审（零记忆，不继承开发上下文）。审阅对象为 `design.md`，并以实际代码（`scripts/check_openspec_artifacts.py`、`scripts/workflow_guard.py`、`tests/test_openspec_artifact_checker.py`、`tests/test_workflow_guard.py`、归档的 #95 grill-design.md）逐一验证设计主张。

## Confirmed Decisions

本节的"确认"指：设计方向成立、机制可行，可以保留；但每条附带必须落实的实现前提（见每条的"前提"），未落实前不得按字面理解。

### Decision 1: `## User Confirmation` 与 `## Confirmed Decisions` 同文件同模式

- **决策**：在 `reviews/grill-design.md` 新增 `## User Confirmation` 节，每条确认记录为 `- **Q<n>**: 用户答复：<正文>；确认时间: <date>` 单行列表项；`**Q<n>:**` 对应 `## Open Questions` 节第 n 个问题。备选（独立 `user-confirmation.md`）被合理拒绝：避免新增文件类型、避免跨文件解析。
- **理由**：与 #95 决策记录同文件，checker 可复用 `_extract_h2_sections`（`check_openspec_artifacts.py:131-139`）统一解析；序号让「哪个问题被确认」可机械对应。该方向成立。
- **来源**: grill-subagent-grill-confirmation-gate-design-review
- **前提**：`_is_placeholder_body`（`check_openspec_artifacts.py:122-129`）是为「整节正文」设计的，`PLACEHOLDER_ONLY` 只含 `{"todo","tbd","n/a","na","待补充","无"}`。对确认记录里 `用户答复：` 的**字段值**做占位判定时，`待确认`/`未确认`/`pending` 都不在其中 → 会被误计为真实确认（见 Open Question 1）。必须为该字段定义专用「未确认 token 集」，或把判定收紧为「`用户答复：` 后到 `；确认时间` 之间的值 ∈ 未确认集 → 该行不计数」。这是 Decision 1 成立的前提，不能直接复用现有 PLACEHOLDER_ONLY。

### Decision 2: checker 在 tasks 全勾选时强制 M≥N（归档门禁）

- **决策**：`_check_design_review_task` 在 `grill-design.md` 存在时，解析 Open Questions 非占位条目数 N 与 User Confirmation 记录数 M；仅当 N>0 且 `_tasks_all_complete(change_dir)`（`check_openspec_artifacts.py:569-587`）为真时要求 M≥N，否则报「存在未确认的 Open Question，不允许归档」。开发中允许挂未决项（M≥N 不强制的分支）。
- **理由**：归档 = 全部拍板；开发中允许边澄清边推进。作为「归档前不得留未确认项」的机械背板，方向正确。
- **来源**: grill-subagent-grill-confirmation-gate-design-review
- **前提**：
  - **必须重构早返回**。当前 `_check_design_review_task` 在 `if len(decisions) >= 3: return []`（`check_openspec_artifacts.py:416-417`）直接返回。若实现者只是把 M≥N 逻辑「追加」到该函数，新校验**永远不会执行**。Decision 2 必须写明：先做 User Confirmation 校验、再走 decisions≥3 判断（或把两者合并为一个 error list）。
  - **可绕过性要诚实标注**。M≥N 只拦「记录里明示了未确认问题」的偶然跳过。agent 在归档前删掉 Open Questions 条目、或写一条 `用户答复：已确认` 的假记录即可通过——设计已声明「不防恶意伪造」，但 Decision 2/3 的「归档门禁/第一道强制」措辞会让读者高估机械强度。真正的「停轮拍板」只由行为层（AGENTS.md + skill 契约）保证，checker/workflow_guard 的机械层只提高伪造成本（见 Open Question 5 与 Must-fix C）。

### Decision 3: workflow_guard 增强为「证据存在但不完整仍拦截代码写」

- **决策**：`_grill_evidence_missing(change_id)` 增强——`grill-design.md` 存在但 Open Questions 非空且 M<N → 视为「证据不完整」，仍返回 True 拦截代码写。这是「grill 之后必须停轮确认」的第一道机械强制。
- **理由**：开发期门禁是唯一能在「写完代码暴露」之前拦下的层；归档 checker 兜不住开发期。方向正确。
- **来源**: grill-subagent-grill-confirmation-gate-design-review
- **前提**：
  - **必须重构判定顺序**。当前 `_grill_evidence_missing` 是 `if evidence.exists(): return False`（`workflow_guard.py:212-213`）在最前、非 docs / spec-delta 判定在其后。增强后必须先把「该 change 是否需要 grill（非 docs + 有 spec delta）」（`workflow_guard.py:214-226`）前置，再评估证据完整性；否则 docs-only 或 proposal 阶段 change 会因一份「存在但不完整」的 grill-design.md 被误拦。Decision 3 未说明此重构。
  - **覆盖范围比字面窄**。grill gate 在 `main()` 里是 `if file_path and not _is_change_doc_write(file_path)`（`workflow_guard.py:295`）——只对 Write/Edit 的 `file_path` 生效，Bash 命令无 `file_path`，**Bash 写操作（`cat > file`、`tee`、heredoc、`python -c open(...)`）完全绕过**（`workflow_guard.py:131-157` 只判定 is_write，不进入 grill gate）。「第一道机械强制」的实际覆盖率不含 Bash 写路径（见 Open Question 2）。
  - **依赖 `_current_change_id()` 的分支映射**。当前 7 个 active change 并存，`_current_change_id` 的 single-active fallback（`workflow_guard.py:193-200`）永不触发；只有分支名 `<change-id>/<date>` 命中（`workflow_guard.py:180-190`）时门禁才生效（实测本 worktree 分支 `grill-confirmation-gate/2026-08-02` 命中，映射成立）。分支纪律不成立（如 master 直接写、非规范分支名）则门禁静默不触发（见 Open Question 3）。

### Decision 4: 两处共享同一提取规则，无存量迁移

- **决策**：Open Questions 条目数 / 确认记录数提取逻辑在 checker 定义，workflow_guard 复刻同规则（hook 需自包含，不互相 import）；`iter_change_dirs` 排除 archive、active 无 grill-design.md，故无迁移负担。
- **理由**：提取规则统一避免两门禁判定不一致；存档迁移负担实测为零。
- **来源**: grill-subagent-grill-confirmation-gate-design-review
- **前提**：
  - 存量主张**已实测验证成立**：`iter_change_dirs` 过滤 `archive`（`check_openspec_artifacts.py:820-827`）；7 个 active change 均无 `reviews/grill-design.md`；且没有任何 active change 的 tasks 全勾选（`observability-deepening` 22/11、`sandbox-hardening` 18/9、`update-design-review-method` 9/4，其余 0 勾选）。因此新校验（M≥N 只在 grill-design.md 存在 + tasks 全勾选时触发）不会让任何现存 active change 红 CI，也不会触及已归档的 #74/#95。
  - **两处复刻有漂移风险**。checker 与 workflow_guard 各自实现同一提取逻辑，无一致性机制。建议加一个 parity 测试（同一 fixture 喂两个实现，断言计数一致），或抽共享模块——`workflow_guard.py` 的「自包含」理由是 hook 需单文件，但可把提取规则放进 checker 后让 workflow_guard import 一个无 argparse 依赖的纯函数模块，权衡后至少要有测试兜底（见 Open Question 5/7）。

## 必须修改项（设计缺陷，不改会死锁、误伤或名不副实）

### A. `_check_design_review_task` 的早返回会吞掉新校验

- **问题**：`check_openspec_artifacts.py:416-417` 在 decisions≥3 时 `return []`。Decision 2 的 M≥N 校验若按「追加」实现将永不执行。
- **必须改**：重构为不早返回——先收集 User Confirmation 校验错误，再判 decisions 阈值，合并返回。Design Decision 2 应写明该重构，tasks 1.3 应覆盖「decisions≥3 且有未确认 Open Question → 仍报错」的测试。

### B. `_grill_evidence_missing` 的判定顺序重构

- **问题**：`workflow_guard.py:212-213` 的 `evidence.exists() → return False` 在「是否需 grill」判定之前。增强后若保持该顺序，docs-only / proposal 阶段 change 会被「存在但不完整」的证据误拦。
- **必须改**：先判定「非 docs + 有 spec delta」（需 grill），再判证据完整性；docs-only 或 proposal 阶段不因证据不完整而拦。

### C. 机械层强度措辞需与「不防伪造」边界对齐

- **问题**：proposal 验收标准 1「新 change 开发中未确认 → workflow_guard 拦代码写」、design Decision 3「第一道机械强制」在「agent 删除 Open Questions / 写假 User Confirmation / 经 Bash 写代码」三类绕过下均不成立。
- **必须改**：在 design.md 的 Risks 显式写明——机械层只拦「记录里诚实标注未确认」的偶然跳过，不拦「删除或伪造记录」的故意绕过；真正的停轮由行为层保证。当前 design.md 只写「不防恶意伪造」一句，没有列全三类绕过路径（尤其 Bash 写路径与删除 Open Questions 的 trivial bypass）。

## Open Questions

1. **`用户答复：` 字段的占位判定会误接受「待确认/未确认/pending」**：`_is_placeholder_body` 的 token 集不含这些值，`- **Q1**: 用户答复：待确认；确认时间: ...` 无论按整行还是按字段值判定都不算占位 → 会计入 M，让「写假确认」比预期更容易。需要专门的未确认 token 集（如 `待确认/未确认/pending/tbd/待定`），或要求确认记录必含用户原文引用。设计只写了「复用 `_is_placeholder_body`」，没有定义该字段的未确认语义。
2. **workflow_guard grill gate 不覆盖 Bash 写操作**：`main()` 的 grill gate 只在 `file_path` 非空时触发（`workflow_guard.py:295`），Bash 命令无 `file_path`，`cat >`/`tee`/heredoc 绕过。这是 #95 继承下来的洞，但本 change 把 Decision 3 定位为「grill 后必须停轮」的第一道强制——要么把 Bash 写命令纳入 grill gate（需把 change_id 判定下放到 Bash 分支），要么在 Risks 明示「第一道」仅覆盖 Write/Edit。请拍板。
3. **`_current_change_id()` 在 7 active change 下只依赖分支纪律**：single-active fallback 永不触发，非规范分支名或 master 直写时门禁静默失效。是否接受这个覆盖率缺口，并把「开发必须切 `<change-id>/<date>` 分支」固化进 AGENTS.md？这决定 proposal 验收标准 1 是否可测。
4. **workflow_guard 依赖本地 PreToolUse hook 安装**：实测当前 worktree 无 `.claude/settings.json`，`~/.claude/settings.json` 的 `hooks` 为空——hook 未安装时 Decision 3 完全失效。设计应像 #95 grill Decision 2 的前提那样写明「hook 是本地安装件，CI 侧机械强制靠 checker」。
5. **M≥N 条数匹配 vs `**Q<n>:**` 序号一一对应**：Open Questions 有 5 条而确认记录是 Q1,Q2,Q3,Q3,Q3（M=5）时检查通过，但 Q4/Q5 未确认。设计已声明「不强求严格解析」——请明确这是有意取舍并写入文档，否则「每个 Open Question 都被确认」的说法名不副实；以及 Open Questions 条目被 agent 事后删除（N 变小）是否也算 accepted bypass。
6. **与 active change `update-design-review-method` 的合入冲突未评估**：该 change 仍 active（tasks 9/4 未归档），也在改 `_has_design_review_task`；本 change 改 `_check_design_review_task`（同一函数族）。#95 grill 的 G 项已flag 过，本 design.md 未提。需要明确合入顺序或冲突消解。
7. **确认记录未绑定 design.md hash / 用户动作**（继承 #95 Open Question 1/3）：design.md 在 grill+确认后被修改，确认是否仍有效？是否要对称的 `grill-manifest.json`？本 change 维持轻量（run id 即够）可接受，但应显式声明「证据过期」是 accepted risk，与 #95 一致。

## User Confirmation

- **Q1**: 用户答复：序号集匹配 + 排除未确认 token（`用户答复：` 后跟 `待确认/TODO/待主 agent 提交` 等未拍板标记不计入确认记录，用专用 `_UNCONFIRMED_TOKENS` 集排除）；确认时间: 2026-08-02
- **Q2**: 用户答复：接受并文档化（Bash 写操作绕过 hook 是固有局限，靠归档 checker 兜底，design Decision 3 明示三个边界）；确认时间: 2026-08-02
- **Q3**: 用户答复：接受（依赖分支名 `<change-id>/<date>` 纪律，固化进 AGENTS.md 分支命名规则）；确认时间: 2026-08-02
- **Q4**: 用户答复：接受并文档化（hook 是本地安装件，未安装则门禁不跑，CI 侧机械强制靠 checker）；确认时间: 2026-08-02
- **Q5**: 用户答复：序号集匹配替代 M≥N 条数（防 Q1,Q2,Q3,Q3,Q3 假通过）；Open Questions 被删除视为 accepted bypass（不防伪造边界）；确认时间: 2026-08-02
- **Q6**: 用户答复：兼容中间态（本 change 以"结构化验证优先、字面 marker 兜底"实现，与 update-design-review-method 无论谁先合入都能共存）；确认时间: 2026-08-02
- **Q7**: 用户答复：本轮不加 hash 绑定，标注遗留（继承 #95 不防伪造边界，证据随 change 进 PR 可审计）；确认时间: 2026-08-02
