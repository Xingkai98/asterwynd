# Grill: grill-enforcement 设计追问

## Reviewer

- run id: grill-subagent-independent-design-review
- 时间: 2026-08-02

## Confirmed Decisions

本节的"确认"指：设计方向成立、机制可行，可以保留；但多数条目附带必须落实的实现前提（见每条的"前提"）。

### Decision 1: 独立零记忆 subagent 执行 grill，产出结构化证据

- **决策**：grill 由独立零记忆 subagent 执行，产出结构化决策记录到 change 目录；主 agent 不自证。
- **理由**：与 #90 审阅闭环对称，是"有独立执行者"这一要素的关键。当前 `_check_design_review_task` 的字面检查确属纸糊的墙——本 change 的 tasks.md 能通过检查仅仅因为标题含 "batch-grill"（`scripts/check_openspec_artifacts.py:338-344`，`_has_design_review_task` 对 `"batch-grill" in lowered` 匹配 tasks.md 第 1 行标题）。
- **涉及文件/行号**：`scripts/check_openspec_artifacts.py:338-344`、`tasks.md:1`、`.claude/commands/review-loop.md:52-68`（对称模板）。
- **前提**：/grill 命令文件 `.claude/commands/grill.md` 与 `.claude/settings.json` 均被 .gitignore 忽略（实测 `git check-ignore` 命中、`git ls-files` 为空），是本地安装件而非提交件；评审需明确这一点，不能在 PR 里把命令文件当提交产物。

### Decision 2: 门禁放在 PreToolUse hook 层（workflow_guard），而非 CI

- **决策**：写代码前门禁用 `scripts/workflow_guard.py`（PreToolUse hook），缺失证据 exit 2；CI 门禁只在 PR 时跑，拦不住开发过程。
- **理由**：正确。`docs/known-issues.md` 记录的三个 Batch A session 是开发中跳过 grill，CI 无法拦截。
- **涉及文件/行号**：`.claude/settings.json`（hook 配置，未提交）、`scripts/workflow_guard.py:166-217`。
- **前提**：hook 只在装有本地 settings.json 的机器生效；提交侧的机械强制仍是 CI 的 artifact checker。设计应显式说明"门禁是本地开发时钩子 + CI 提交时检查"双层，避免误以为 CI 也跑 hook。

### Decision 3: 替换字面检查为结构化证据验证

- **决策**：`_check_design_review_task` 从"tasks.md 含 batch-grill 字样"升级为"验证 `reviews/grill-design.md` 存在且含结构化决策记录"。
- **理由**：方向正确，字面检查确实拦不住（见 Decision 1 的实测例子）。
- **涉及文件/行号**：`scripts/check_openspec_artifacts.py:404-415`。
- **前提**：必须同步处理触发时机与存量 change 迁移（见 Open Questions 3 与"必须修改项 C"），否则 8 个 active 非 docs change 会集体红 CI（实测 `add-minimal-tui-runtime-view`/`context-engineering-deepening`/`observability-deepening`/`sandbox-hardening`/`update-design-review-method` 等 8 个均无 `reviews/grill-design.md`）。

### Decision 4: 非目标边界（不保证 grill 质量、不防恶意伪造、不重做主干流程）

- **决策**：独立执行只保证"有独立 agent 挑战设计"，不保证质量；不拦截恶意伪造证据；不重做 OpenSpec 主干。
- **理由**：与审阅闭环同一边界，合理。
- **涉及文件/行号**：`design.md:16-20`。
- **前提**：既然接受"不防恶意"，checker 的结构化验证应定位为"提高伪造成本 + 拦偶然跳过"，不要给它超出能力的期待；但至少应把证据绑定到 design.md 版本（见 Open Question 1），否则"grill 过"无法对应"grill 的是这份 design"。

## 必须修改项（设计缺陷，不改会死锁或误伤）

### A. workflow_guard 缺少"写操作 → change"的映射机制（最严重）

- **问题**：Design Decision 2/3 说"workflow_guard 在写操作时检查 change 的 reviews/grill-design.md"，但代码写入发生在 change 目录之外（`agent/*.py`、`tests/*.py`），hook 收到的 `file_path` 不包含 change_id。旧状态机的 `_discover_active_change` 已在 #90 删除（`scripts/workflow_guard.py:209-212` 注释明确"state-machine ceremony disabled"），设计没有给出新的映射机制。
- **实测影响**：主仓库 `openspec/changes/` 下有 9 个 active change 并存（`add-minimal-tui-runtime-view`、`context-engineering-deepening`、`grill-enforcement` 等）；当前 cwd 在分支 `grill-enforcement/2026-08-02`。若只按"目录下有 active change"判定，任何一个 change 没 grill 证据都会拦下所有代码写；若按文件路径映射，代码文件无法映射到 change。
- **必须决定**：用分支名推导（`git branch --show-current` 形如 `<change-id>/<YYYY-MM-DD>`，worktree 目录名也编码了分支）作为主机制，单 active change 目录作为兜底，两者都不成立时不启用门禁。Paseo 管理的 worktree 目录名随机（实测 `.paseo/worktrees/.../pink-badger`），但分支名仍含 change-id，所以"分支名优先、目录名不可靠"。设计需写明该机制，否则实现者无从下手。

### B. 证据写入死锁：grill-design.md 的创建会被门禁自己拦截（鸡生蛋）

- **问题**：门禁触发条件含"有 spec delta（或 tasks 有实现项）"。一旦 change 具备该条件，任何写操作都被拦（缺 grill-design.md）。但 grill 证据必须由独立 subagent 写入 `reviews/grill-design.md`——subagent 继承 PreToolUse hook，它自己的 Write 也会被拦 → 死锁。同理，proposal/design/tasks/specs 的写入发生在 grill 之前，若不做豁免，propose 流程写完 spec delta 后再写 design.md 就会被拦。
- **必须决定**：门禁必须豁免 change 自身文档类写操作：`openspec/changes/<id>/{proposal,design,tasks}.md`、`<id>/specs/**`、`<id>/reviews/**`。豁免路径清单要精确，否则要么死锁（没豁免 reviews）、要么误放行代码（豁免过宽）。建议：豁免白名单按路径前缀精确匹配 change 目录内文档与 reviews，代码目录（`agent/`、`tests/`、`scripts/` 等）不豁免。

### C. checker 触发时机未定义 + 存量 change 迁移缺失

- **问题**：现 `_check_design_review_task` 对所有非 docs + 有 tasks.md 的 change 无条件触发（`scripts/check_openspec_artifacts.py:404-408`）。改成"要求 grill-design.md 存在"后，实测 8 个 active 非 docs change 全部缺该文件，CI 立即全红。设计说"替换字面检查"但没定义新检查的触发时机（何时才要求证据）。
- **必须决定**：新检查触发条件应与门禁一致（非 docs + 有 spec delta 或 tasks 有实现项），并且对"已实现但尚未有证据的存量 change"给出迁移策略：要么要求存量 change 补 grill，要么对 `_tasks_all_complete()` 之前的部分实现 change 暂不要求（与 building-review 门禁的"tasks 全勾选才触发"对齐，`scripts/check_openspec_artifacts.py:557-561`）。至少应把触发收窄到"有实现内容"，避免 proposal 阶段就报缺。

### D. spec delta 为空，削弱触发与演示

- **问题**：本 change `specs/change-documentation/` 目录存在但无 `spec.md`（实测 `find` 为空）。`_changed_capabilities`（`scripts/check_openspec_artifacts.py:355-365`）glob `*/spec.md` → 空，因此该 change 当前不因 spec delta 而"合格"，只能靠"tasks 有实现项"触发门禁。proposal/design 声称要更新 `openspec/specs/change-documentation/spec.md`（当前规格），但没有对应的 change spec delta。
- **必须决定**：补写 `specs/change-documentation/spec.md` delta（描述新的设计追问 requirement），否则：门禁的 spec-delta 触发分支在此 change 上无演示；`_check_current_spec_sync_task` 也不会触发（无 capabilities），规格同步无验证。

### E. "至少 N 条决策"未定义，证据格式不可机械解析

- **问题**：`design.md:50` 与 `tasks.md:18` 写"至少 N 条决策"，N 未定；证据条目格式（列表项还是 `**Decision N:**` 标题）未定义，checker 无法可靠解析；"空节算不算"未定义。
- **必须决定**：定义机器可解析格式，例如 `## Confirmed Decisions` 下每条为 `- **决策**: …；理由: …；来源: <subagent run id>` 的单行列表项；checker 复用 `_is_placeholder_body`（`scripts/check_openspec_artifacts.py:122-129`）判空，N 建议取 3；`## Open Questions` 允许为空（= 无未决项），`## Confirmed Decisions` 不得为空。

### F. 本 change 自身任务顺序：5.1 必须早于 2.x 生效

- **问题**：tasks.md 把 5.1（本 change 先 grill）排在 2.x（门禁实现）之后。workflow_guard 的 grill 检查一旦写入并运行，本 change（非 docs + tasks 有实现项）即"合格"，下一次代码写操作就会被拦——除非 `reviews/grill-design.md` 已存在。顺序不对会造成自我拦截。
- **必须决定**：把 5.1 提到实现类任务（2.x/3.x）之前，或显式注明"门禁代码合入前必须先有本 change 的 grill 证据"。本 grill session 正在产出该证据，即时死锁可避免，但任务顺序要修正以固化为规则。

### G. 与 update-design-review-method 的叠加冲突

- **问题**：active change `update-design-review-method` 也在改 `_has_design_review_task`（让字面检查同时接受 batch-grill 与 grill-with-docs），且 tasks 未全部完成、未归档（`tasks.md:3.3` 仍 `[ ]`）。本 change 要把同一函数从字面检查改为结构化验证——两 change 在同一函数上相向而行，存在合入顺序/冲突风险。
- **必须决定**：明确两 change 的合入顺序与冲突消解（建议后者合入后再改本 change，或本 change 直接以"结构化验证优先、字面检查兜底"兼容中间态）。

## Open Questions

1. **设计变更后的重 grill 策略**：grill 证据是否应绑定 design.md 的 hash/版本？design.md 在 grill 后被修改，是否需要重 grill？当前设计对"证据对应哪版 design"无约束，checker 无法检测证据过期。（涉及 `design.md:24-54`）
2. **多批次 change 的 grill 粒度**：审阅闭环是 batch-aware（`review-loop.md:60,154`），grill 是否也要按批次？一个 change 分多批实现、每批改 design，是每批 grill 一次还是只 grill 最终 design？
3. **grill manifest 是否必要**：review 有 `*-review-manifest.json` 绑定 reviewer/shas/hashes（`agent/workflow/review_manifest.py:9-19`），grill 只靠 md 里的 run id 自报。要不要对称建 `grill-manifest.json`，把 grill-design.md 与 design.md hash 绑定？还是维持轻量（run id 即够）？
4. **主仓库多 change 场景的失效边界**：若开发者在 master 分支（无 change-id）直接写代码，分支推导失效、门禁不触发——接受这个缺口，还是要求每次开发必须切 `<change-id>/<date>` 分支？（这决定了门禁实际覆盖率）
5. **存量 8 个 active 非 docs change 的迁移**：补 grill？还是"tasks 全勾选才要求"对齐 building-review？还是上线前手工批过？需要明确后再改 checker，否则 CI 全红。

## 风险

- **[死锁/误拦]** 豁免清单若不含 `reviews/**`，grill 证据永远写不进去；若豁免过宽（如豁免整个 change 目录），代码写在 change 目录内时门禁失效。设计必须给出精确白名单（`design.md:34-38`）。
- **[门禁形同虚设]** 若分支推导只在 `.claude/worktrees/<change-id>/` 生效、Paseo 随机目录或主仓库 master 分支失效，三个 Batch A 的"一股脑开发"场景可能再次漏网。门禁强度 = 分支纪律强度，需在 AGENTS.md 写明。
- **[CI 集体误报]** `_check_design_review_task` 改成证据检查后，8 个 active 非 docs change 无证据即红（实测），若不同步迁移策略，合入本 change 会让主仓库 CI 立即失败。
- **[Bash 写操作漏网]** `_is_write_bash`（`scripts/workflow_guard.py:130-156`）是启发式匹配，未知命令按安全放行（保守放行策略）；经 Bash 的非常规写文件方式可能绕过门禁。这是 hook 层固有局限，可接受，但应在文档注明门禁不是硬边界。
- **[spec delta 缺失导致规格脱节]** 若本 change 不补 `specs/change-documentation/spec.md`，新 requirement 只落在 AGENTS.md 文字与 checker 逻辑上，正式规格未同步（`tasks.md:4.2` 只提到改当前规格，没建 delta）。
- **[合入竞态]** `update-design-review-method` 未归档且与本 change 改同一函数，若并行合入可能出现冲突或互相覆盖（`scripts/check_openspec_artifacts.py:338-344`）。
- **[证据过期]** 无 design hash 绑定时，checker 认可的是"存在一份看似结构的证据"，无法发现"design 已改但证据未更新"——与"不防恶意"边界一致，但会给人"已 grill 过"的虚假安全感。
