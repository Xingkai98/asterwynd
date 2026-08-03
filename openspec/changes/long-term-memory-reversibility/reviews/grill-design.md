# Grill: long-term-memory-reversibility 设计追问

> 独立零记忆 subagent 挑战 design.md 全部 4 条 Decision + proposal/diagnosis/spec delta，并对照已实现代码（`agent/memory/persistent.py`、`agent/memory/dedup.py`、`agent/tools/builtin/memory.py`、`agent/tools/factory.py`、`agent/config.py`）与 CI/门禁机制（`.github/workflows/ci.yml`、`scripts/workflow_guard.py`、`scripts/check_openspec_artifacts.py`）验证对齐。本记录为 reviews/** 豁免路径证据。

## Reviewer
- run id: subagent-grill-ltm-reversibility-20260803
- 时间: 2026-08-03
- 方法: 7 维度独立追问（需求对齐 / 实现细节 / 依赖 / 风险 / 测试策略 / 文档影响 / 触发与门禁），逐条对照代码与 CI 证据，产出 5 条 Confirmed + 10 条 Open Questions（含推荐答案）+ 风险清单。

## Confirmed Decisions
- **决策**: 采用 git 管理可逆写入（memory_dir 独立 git init + commit-before-write），不做 mem0 ADD-only、不做侧车 revisions 目录；理由: ADR-0002 已对比三方案（mem0 需重写 read 路径、当前无多信号 ranker；侧车是残缺版 git，diff/log/restore/备份都要自己造），用户已确认 git 方案；来源: subagent-grill-ltm-reversibility-20260803
- **决策**: resolve_conflict 作为独立 API + 工具，清除双方 conflict_with + changelog resolve 事件 + 可选归档败者；理由: conflict_with 标记只增不减且无消费点（persistent.py:513-525），git 只管内容恢复、不管标记累积，必须独立 API 承接（design.md:37-44、proposal.md:13）；来源: subagent-grill-ltm-reversibility-20260803
- **决策**: load_entries 顶层非递归 `glob("*.md")`（persistent.py:324）天然排除 `.git/`、`archive/` 子目录，git init 不污染加载；changelog.md 虽匹配 `*.md` 但无 frontmatter 被 `_parse_file` 跳过（persistent.py:339-349）；理由: 现状实现即安全，需以回归测试锁定（design.md Decision 4 / tasks 4.5）；来源: subagent-grill-ltm-reversibility-20260803
- **决策**: 破坏性写（save 覆盖 / supplement / update）前先 commit 旧状态，而非写后 commit；理由: 写后 commit 时旧 body 已被覆盖、无 pre-image 可恢复，写前 commit 是 git 方案下唯一能保留旧状态的时间点（design.md:35）；来源: subagent-grill-ltm-reversibility-20260803
- **决策**: commit message 与 changelog 对齐为 `<action> <name> → <reason>`，`git log -- <name>.md` 可查历史；理由: 与 R1-Q5 changelog 行格式一致（persistent.py:692-698），reason 由 LLM 三分支 judgment 的 `Judgment.reason` 提供（dedup.py:36-38/154）；来源: subagent-grill-ltm-reversibility-20260803

## Open Questions
- **Q1**: commit 失败策略——ADR 与 design 自相矛盾：ADR-0002:29 说"提交失败则中止写入（写保护）"，design.md:32 说"git 不可用时优雅降级：仍执行写入（GIT_ALLOW_FAIL=1）"，且 ADR-0002:54 自己又写"优雅降级为警告 + 仍写入"。到底 commit 失败（permission / git 损坏 / identity 缺失）时是 abort 写保护还是 degrade 仍写？→ 推荐: 采用**写保护（abort）**。理由: "降级仍写"= 旧内容唯一副本在无任何 pre-image 下被覆盖，正是本 change 要修的 bug；若 git 坏掉就静默无保护，比现状更糟（现状明确无兜底，降级是虚假兜底）。abort 时必须区分"nothing to commit"（fresh repo 无旧状态可快照，应安全继续）与"git 真坏了"（应 abort 或写 .bak 降级），否则首次写被永久阻塞（见 Q10）。
- **Q2**: git identity 在 CI / 无全局配置环境的处理——CI validate job（`.github/workflows/ci.yml` 1-85 行）未配置 user.name/email（只有 benchmark-gate job 90-93 行配了）；无 identity 时 `git commit` 必失败。若实现裸 `git add -A && git commit`，4.x 全部 git 历史断言测试在 CI validate 直接红，或（若 Q1 选 degrade）静默无 commit 使 4.1/4.2 断言失败。→ 推荐: 实现内联 `git -c user.name="Asterwynd Memory" -c user.email="memory@asterwynd.local" commit`（永不依赖全局/仓库配置），这是 commit-before-write 唯一真正的环境脆弱点，一行内联可消除。
- **Q3**: git init 时机——design.md:26 说 `PersistentMemory.__init__` 时 git init，但现有测试 test_persistent.py:209-212（`test_save_rejects_invalid_name`）断言 invalid name 时 `mem.memory_dir.exists()` 为 False（目录不得因构造产生）。若 __init__ 无条件 git init（git init 需建目录），该现有测试直接回归失败。→ 推荐: 懒初始化——仅首次破坏性写（save/apply_judgment 实际落盘）前 git init；__init__ 不做任何副作用。
- **Q4**: conflict 分支 commit 时序自相矛盾——design.md:30 先说"所有破坏性写路径在写入前先 commit"，同段末句又说"conflict 分支双方打标后 commit（一次覆盖双方）"。打标后 commit 是写后 commit，快照的是打标后的状态、不是 target 的旧状态，无法撤销打标；且 conflict 内部先 `save()` 写 incoming（persistent.py:514）再两次 `_write_entry` 打标（persistent.py:517-523），若只在外层打标后 commit，中间三次写全无快照。→ 推荐: 统一为"打标/写入前 commit 当前状态（快照 target 旧状态 + incoming 不存在），打标后不立即 commit，交给下一次破坏性写的 commit-before-write 兜底"；resolve_conflict（清标记）与 MemoryGitBackend.revert（覆盖文件）也必须纳入 commit-before-write 集（design 未列，否则被解除的 conflict 标记态与被 revert 覆盖的当前态从 git 历史永久消失）。
- **Q5**: resolve_conflict 败者参数缺失——spec delta"Conflict Resolution"场景 "the losing memory is moved to the archive directory / the winning memory keeps its content"，但 design.md:39-44 的 API 签名 `resolve_conflict(name_a, name_b, archive=False, reason)` 没有 winner/loser 参数，archive=True 时不知道该归档谁。→ 推荐: API 增加 `winner`（或 `loser`）必填/默认参数，或明确默认"loser=name_b"，并同步 spec 场景。
- **Q6**: spec SHALL 与降级路径冲突——spec delta "Reversible Writes" 要求 "SHALL snapshot the prior state before any destructive write"。若 Q1 选 degrade（git 不可用仍写），则该 SHALL 在 git 缺失/损坏环境被整体违背，且无任何机械可检测信号。→ 推荐: 三选一：(a) spec 加限定从句 "SHALL snapshot ... when git is available"；(b) 降级路径仍写 .bak/侧车 pre-image 保证旧内容留存，git 只作历史层；(c) 按 Q1 选 abort。至少 spec 与运行策略必须一致。
- **Q7**: MemoryGitBackend 工具形态与注册面——design.md:46-51 未定：(i) 一个工具带 action 参数（history/diff/revert）还是三个独立工具？(ii) 命名 `MemoryGitBackend`/`resolve_memory_conflict` 为 snake_case，与 #75 R1-Q8 定的库内 PascalCase 约定（SaveMemory/RecallMemory/SearchMemory，factory.py:91-93）不一致；(iii) revert 是写操作，工具 permission 级别未定（SaveMemory 用 AGENT_STATE_PERMISSION）；(iv) design Impact Analysis 漏了 `agent/tools/factory.py`——新工具必须注册进 factory.py:65-93 KNOWN_BUILTIN_TOOL_NAMES + 334-340/430-436 构造列表。→ 推荐: 单个 MemoryGitBackend 工具 + action 参数；命名改 PascalCase（ResolveMemoryConflict / MemoryGitBackend）；revert/resolve 走 AGENT_STATE_PERMISSION；Impact Analysis/tasks 补 factory.py。
- **Q8**: 并发写与 git race——#79 多 agent 协作已合入，ADR-0002:50 宣称"多 subagent 并发写记忆有 git 兜底"，但 git 无锁：两个并发写者各自 commit 同一旧状态、随后各自覆盖，git 无法检出丢失更新（persistent.py 的 read-modify-write 无 flock 是 #75 已知债）；`.git/index.lock` 冲突时其中一个 commit 失败，按 Q1 哪条策略走？→ 推荐: 在 design/ADR 显式记录"git 可逆性解决误判恢复、不解决并发丢更新"；index.lock 冲突按 Q1 策略（abort 则写失败、degrade 则无快照写），并在 known-debt 登记并发写债不因本 change 消解。
- **Q9**: `git add -A` 误收与 commit 噪声——`_touch()` 每次检索命中都整文件重写（persistent.py:684-690），未 commit；下次破坏性写的 `git add -A` 会把所有未 commit 的 touch 元数据变更、MEMORY.md 索引、changelog、archive/ 移动一起扫进同一 commit，使 commit diff 与 message（本次写的 reason）不一一对应；memory_dir 中若混入临时/大文件也会被提交。→ 推荐: 接受并文档化（memory_dir 是专用目录，误收面小），或限定 `git add -A -- <memory_dir>/` 并明确 .gitignore 不适用；至少写一条 commit 内容只含预期文件的断言测试。
- **Q10**: fresh repo 首次写与 diff 标注 off-by-one——(i) 全新 `git init` 后无 HEAD，首次破坏性写时 `git commit` 报 "nothing to commit"（不是失败是空状态），若按 Q1 abort 则首次写被永久阻塞，必须先 `git rev-parse --verify HEAD` 判定或识别 nothing-to-commit；(ii) commit N 的 message 描述写 N，但 commit N 的内容是写 N 前的状态，`git log -p -- <name>.md` 会把写 N-1 的 diff 标成写 N 的 message（revert 语义正确：checkout commit N = 撤销写 N，但 proposal.md:72/design.md:31 "git log 即可看到内容 diff + 原因" 的叙事 off-by-one）。→ 推荐: 实现区分"无旧状态可快照"与"git 损坏"；文档把审计叙事从"diff+reason 同行"改为"checkout commit N 撤销写 N"。
- **Q11**: 关闭时的受保护 artifact 事件——tasks 6.1/6.3 同步 `openspec/specs/long-term-memory/spec.md`、改 `docs/openspec-change-backlog.md`、归档到 `openspec/changes/archive/`，这三类路径受 workflow_guard.py:62-72 与 checker 保护，修改必须配 `workflow-events.jsonl` 结构化事件；design Impact Analysis 未提及。→ 推荐: tasks 6.x 增加"为受保护路径修改补 workflow-events 事件"子项；runtime 记忆 git 操作（subprocess 内联）不经过 Bash 工具，不会被 workflow_guard 拦截，无死锁。

## 风险
- **git init 副作用破坏现有测试**: `__init__` 无条件 git init 会使 test_persistent.py:209-212 回归失败（invalid name 后 memory_dir 必须不存在）——必须懒初始化，这是实现前必须锁定的契约。
- **CI validate 无 git identity**: `.github/workflows/ci.yml` validate job 未配 user.name/email，git commit 必失败；不内联 identity 则 4.x 测试全红（Q2）。
- **ADR 与 design 提交失败策略互相矛盾**: ADR-0002:29（abort 写保护）vs design.md:32（degrade 仍写）vs ADR-0002:54（degrade）三处口径不一，实现者无从下手，Q1 必须用户拍板。
- **`git log -p` 审计叙事 off-by-one**: commit N 内容=写 N 前状态、message=写 N reason，`git log -- <name>.md` 的 diff 标注与 reason 差一个 commit（revert 语义正确，叙事需修正）。
- **`~/.asterwynd` 若在 dotfiles git 仓库内**: 若某用户把 `~` 纳入 git 管理，`git init` 前必须校验 memory_dir 自身是仓库根（`git rev-parse --show-toplevel`），否则 commit 会写进父仓库。
- **resolve/revert/archive 未纳入快照集**: 这些破坏性写不 commit-before-write，被覆盖的标记态/当前态会从 git 历史消失（Q4）。
- **并发丢更新未被 git 兜底**: 多 subagent 并发写仍丢更新（#75 已知债），git 只保误判恢复，ADR-0002:50 叙事需降级为"有兜底"而非"解决并发"（Q8）。
- **memory `.git` 目录对工具可见**: load_entries（persistent.py:324 非递归 glob）安全，但任意文件扫描工具/sandbox 读 `~/.asterwynd` 时会看到 `.git`；系统提示的 "NEVER modify .git/" 只约束项目仓库，不影响本设计，但需在文档说明 memory `.git` 属用户主目录。
- **MemoryIndexSource 摘要不受影响**: sources.py:278-308 走 load_summary→load_entries，非递归 glob 已排除 .git/archive；changelog.md 被 glob 匹配但无 frontmatter 被 _parse_file 丢弃，无需改动。
- **close-out 受保护路径缺事件**: spec sync / backlog / archive 修改需 workflow-events 事件，设计未提，归档时会被 checker 拦截（Q11）。

## User Confirmation

> 用户停轮确认记录（grill-confirmation-gate）。2026-08-03 逐项拍板，全部采用推荐答案。

- **Q1**: 用户答复：commit 失败采用 **abort 写保护**——commit 失败则中止写入，宁可写失败不丢旧内容；区分"nothing to commit"（fresh repo 无旧状态，安全继续）与"git 真坏"（abort）；确认时间: 2026-08-03
- **Q2**: 用户答复：**内联 `-c user.name/-c user.email`**，永不依赖全局/仓库配置，消除 CI validate 无 identity 的脆弱点；确认时间: 2026-08-03
- **Q3**: 用户答复：**懒初始化**——仅首次破坏性写前 git init，`__init__` 不做副作用（保护 test_persistent.py:209-212 invalid name 后 memory_dir 不存在）；确认时间: 2026-08-03
- **Q4**: 用户答复：conflict 分支统一为"写入/打标前 commit 当前状态"；resolve_conflict 清标记前也 commit-before-write；resolve 后不立即 commit，交给下一次破坏性写兜底；确认时间: 2026-08-03
- **Q5**: 用户答复：resolve_conflict 增加 **loser 参数**（archive=True 时归档 loser），spec 场景同步；确认时间: 2026-08-03
- **Q6**: 用户答复：**保持严格 SHALL**——因 Q1 选 abort，git 不可用时写入被中止，SHALL 语义始终成立，spec 不加限定从句；确认时间: 2026-08-03
- **Q7**: 用户答复：MemoryGitBackend 用**单工具 + action 参数**；命名改 PascalCase（`ResolveMemoryConflict` / `MemoryGitBackend`）；revert/resolve 走 `AGENT_STATE_PERMISSION`；Impact Analysis 补 `agent/tools/factory.py` 注册面；确认时间: 2026-08-03
- **Q8**: 用户答复：**记录债务不解决**——git 可逆性解决误判恢复、不解决并发丢更新（#75 已知债），本次登记 known-debt，不引入锁；确认时间: 2026-08-03
- **Q9**: 用户答复：**接受全目录快照 + 内容断言测试**——`git add -A -- <memory_dir>/`，commit 是全目录快照（条目+索引+changelog+archive 都有历史）；revert 时**索引必须跟随回退**（重建该条索引行保持 description 一致），changelog 不跟随（保留审计）；确认时间: 2026-08-03
- **Q10**: 用户答复：首次写区分"无旧状态可快照"（nothing to commit，安全继续）与"git 真坏"（abort）；审计叙事从"diff+reason 同行"改为"checkout commit N 撤销写 N"；确认时间: 2026-08-03
- **Q11**: 用户答复：tasks 6.x 为 spec sync / backlog / archive 三处受保护路径补 **workflow-events 事件**；确认时间: 2026-08-03

## 维度覆盖说明
- 需求对齐: proposal 三项需求（可逆写入 / 冲突解除 / 内容级审计）design 均承接，但"内容级审计"的 `git log` 叙事 off-by-one、resolve 败者语义、revert/resolve 快照集缺失使承接不完整（Q4/Q5/Q10）。
- 实现细节: 每 Decision 有方案/理由但无备选；commit-before-write 确切实现（add/commit 子进程、identity、nothing-to-commit、首次写、错误分类）未定（Q1/Q2/Q10）。
- 依赖: 依赖系统 git，版本无要求（`git init/add/commit/checkout` 均远古即支持）；CI validate 无 identity 是主要依赖风险（Q2）。
- 风险: 见上；关键边界（fresh repo、git 损坏、并发 index.lock、dotfiles 嵌套仓库）均未覆盖。
- 测试策略: tasks 4.1-4.6 覆盖了功能路径但未覆盖 identity/首次写/并发/abort 分支；git 相关测试在 CI 无 identity 下必失败，需 fixture 或内联 `-c` 兜底（Q2）。
- 文档影响: 需同步 AGENTS.md/CONTEXT.md 的"memory 独立 git 仓库"说明、ADR-0002 与 design 的策略矛盾修正、spec SHALL 限定（Q6）；close-out 受保护路径需 workflow-events（Q11）。
- 触发与门禁: 本 change 改 PersistentMemory 写路径（in-process subprocess），不经过 Bash 工具，workflow_guard 不拦截 runtime 记忆 git 操作，无死锁；但实现者代码写操作会触发 grill 门禁（本记录满足），归档时 spec/backlog/archive 受保护路径需事件。
