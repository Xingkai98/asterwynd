# Known Debt

Pre-existing TODO/FIXME/HACK residues — exact source-line matches.
Files are compared against stripped source lines during gate checks.

- "收尾过程中发现任何未收敛的 open question 或 TODO，先回写到 change 文档。"

## 节点因由的两条小瑕疵（workflow-terminal-honesty Round 3 观察项）

`workflow-terminal-honesty`（2026-09-19 合入）的审阅闭环 Round 3 在 `_waiting_reason` / `_blocked_reason`（`agent/subagent/scheduler.py`）上留了两条**低危、非阻塞**观察项，均不影响正确性，记录以免遗忘：

1. **数量上限是冗余保护**：`_WAITING_LIST_LIMIT`（限列出几个上游 id）在「整句 160 字符 clamp 生效」时不可观测——clamp 已先截掉尾部。两条保护**各自充分**（删任一条输出仍在预算内），故数量上限是第二道。不是缺口，但若有人想清理冗余，需知道删掉它测试不会变红。
2. **取消态防护在优先级上先于闸门分支**（`if self._cancelled:` 置于 `reason` 判据之前）：理论上「既被取消又撞闸门」的图会先报取消、遮蔽闸门真因。**实测不可达**（节点因由的唯一写入路径只在 teardown 的 `_resolve_pending_nodes` 里被调用，而 `cancel()` 不走该路径；`state.reason = state.reason or ...` 的 `or` 也保证已写的闸门因由不被覆盖）。若日后要收口，可在防护前先判 `reason` 键——当前无证据支持该改动必要。

## guard Bash 静态分析无法解析 shell 变量拼接（flow-policy-source P0）

`scripts/workflow_guard.py` 的 Bash 受保护路径扫描是静态文本分析：对写意图命令做「命令文本 contains + 提取重定向/写目标 token 归一化」匹配。shell 变量拼接（`echo > doc$V/known-debt.md`、`$V` 在运行时展开为 `s`）的最终目标路径无法静态解析，该形态可绕过检测。属工具面纪律边界（同 add-worktree-tool「Bash 绕过工具直接 git worktree add 无法阻止」），P0 不引入过度误拦（拦截含 `$` 的重定向会误伤合法 `$OUTPUT_DIR/notes.txt`）。后续如需更强静态分析可引入 shell AST 解析（独立 effort）。

## Workflow guard 未启用（Q7）

`scripts/workflow_guard.py`（PreToolUse 受保护文件门禁）已实现但未安装启用（settings.json 未挂钩子）。启用前必须先为 `/opsx:archive`（写 `openspec/changes/archive/`、`workflow-events.jsonl`、`-review-manifest.json`）与 `/review-loop`（写 `reviews/*-review-manifest.json`）增加 sanctioned 流程白名单，否则这两个合法流程会被自身写保护拦截形成死锁。是否启用是项目治理选择，当前决定不启用、保持 checker 机械门禁兜底。

## NGram embedding 词面近似局限（Q9）

`NGramEmbedding`（`agent/embedding/provider.py`）是 char-trigram 词面近似，无语义/同义泛化——释义改写、同义词召回会漏检（"语义检索/语义去重"措辞实际是"相似度召回"）。0.5 去重召回阈值在记忆路径现已对齐 dim=2048 标定操作点，但换更强 embedding（sentence-transformers / ollama）后必须重标定 `dedup_recall_threshold`。SearchMemory 工具描述已改为"按文本相似度召回"以如实反映能力。

## 已归档 change 的 review manifest 漂移（Q6）

PASS 后 closeout 提交若修改 tasks.md/spec（如补充审阅修复节、实测数据），已生成的 review manifest 的 `tasks_hash`/`spec_hash` 会与归档后 artifact 失配（潜伏态，active-only checker 不报）。`--check-archived` 模式可捕获并修复：重建 manifest 绑定当前 artifact。历史已归档 change（2026-08-02 的 context-engineering-deepening / grill-enforcement / long-term-memory-deepening / sandbox-hardening / workflow-slim）已重建 manifest 消除漂移；`/opsx:archive` 应归档前对 manifest 做最终校验。

## 写时去重可逆性缺口（R2-4 → issue #99）✅ 已解决

`apply_judgment()` update 直接覆盖旧 body 无 pre-image、supplement 误判污染无 undo、conflict_with 只增不减无解除 API，memory 目录无 VCS 兜底（误判覆盖即永久丢失）。design Risk 表"判断结果可人工复核、change log 可回溯"当前仅到 action 级审计。**已由 issue #99 `long-term-memory-reversibility`（2026-08-03 合入）解决**：git commit-before-write + resolve_conflict + MemoryGitBackend（ADR-0002）。本条目保留作历史记录。

## 记忆并发写丢更新（#99 遗留）

`PersistentMemory` 的 read-modify-write 无文件锁（#75 已知债），多 subagent 并发写同一记忆目录时可能丢更新；git 可逆性解决误判恢复、**不解决并发丢更新**（ADR-0002）。`.git/index.lock` 冲突时按 commit 失败处理（abort 写保护）。后续若需多 agent 并发写记忆，应引入 per-entry 文件锁或 merge 策略。

## closeTab 后 activeTabId / 全局代理可能指向已关闭的 tab（fix-issue-191 Round 2 观察项）

`closeTab`（`web/static/chat.js`）先 `tabs.delete(tabId)`，再在「关闭的是活跃 tab」分支里
经 `switchTab(next)` 修正 `activeTabId`。但两条路径会在修正之前/之外留下指向已删除 tab 的引用：

- `socket.onclose` / `socket.onerror` 无条件调 `bindActiveTab(tab)`（`chat.js` 的 connectTab
  回调）。若该连接所属的 tab 已被关闭，这个回调会把全局代理重新指向一个已从 `tabs` 移除的
  对象 —— 此后 `getActiveTab()` 返回它，而它已不在 `tabs` 里。
- 关 tab 与「挂起的异步回调」同 turn 交错时，`activeTabId` 会短暂指向已删除的键，
  直到 `switchTab(next)` 把它改正。

**实测（fix-issue-191 R2，`/tmp/verify_close191.py` 与审阅者探针）**：稳定态下（关闭后
等待 300ms）`activePaneTabId` 与渲染出的 `.session-tab` 一致，用户可见行为无异常；
上述残留只在「关闭后的瞬时窗口 / 断连回调」里可观察到，且**在本 change 之前就存在**
（在 base `eb50f8a` 上同样复现），不属于 fix-issue-191 引入的缺陷，也未被本次新增的
归属守卫放大成功能问题（守卫只做 `getActiveTab() !== tab` 比较，指向死对象时结果为
「不等于」→ 提前返回，行为与预期一致）。

**处置**：不在 fix-issue-191 内修（超出该 bugfix 边界）。若后续要收敛，方向是
`closeTab` 在 `tabs.delete` 后立即把 `activeTabId` 置为 `next`（或 `null`），并让
`socket.onclose` / `onerror` 在 `tabs.has(tab.id)` 为假时直接返回、不重绑全局代理。

## 四阶段状态机退役的能力面净损失（retire-4phase-state-machine 收口，issue #235）

`retire-4phase-state-machine`（2026-09-22 合入）退役了整套四阶段状态机实现
（`check_phase_done.py`、`doc_artifact_protocol*.py`、`dispatcher.py`、`role_registry.py`、
`manager.py`、`handoff_note.py`、`flow/` 引擎与声明，及 `discover`/`current`/`validate`/`spawn`
与 gate 家族子命令）。被删实现承载**两项在新机制中没有等价替代**的完成度门禁——这是**能力面
净损失，不是替代**，须显式记录而非静默消失：

1. **「100% 要求全勾」变薄**：原 `doc_artifact_protocol_openspec.py:123-125` 的
   `ContentRequirement(..., "checkboxes_all_checked")` 要求 tasks.md **全部** checkbox 为 `[x]`。
   删除后，完成度检查只剩 `check_openspec_artifacts.py:1027` 的 `requires_building_review`，
   而它由 `_tasks_all_complete`（`:982`）驱动——**「全勾才查」的触发器**：tasks 未全勾
   → 整个分支不进入 → **无任何检查**。
2. **TODO 残留扫描消失**：原 `check_phase_done.py:210` 的 `_find_todo_residuals` / `:183` 的
   `_load_known_debt` 会对**改动过的 `.py` 源码行**扫 `TODO`/`TBD`/`FIXME`/`HACK` 并与本文件比对。
   退役后只剩 `check_openspec_artifacts.py:92` 的 `SELF_ADMITTED_INCOMPLETE_PHRASES`
   （只扫 `Reference Implementation Research` 字段的自认未完成短语）——**只查一个 section 的散文，
   不查源码行**，覆盖是结构性下降。

**触发条件（具体场景）**：本 change 合入后，若某后续 change 在 `agent/foo.py` 留下
`# TODO: 处理边界` 且 tasks.md 已全勾，则——退役前 `flow approve --phase building` 会调用
`check_phase_done` 报「发现 1 处 TODO/TBD/FIXME/HACK 残留」并拒绝批准；退役后 CLI 无此通道，
PR 照常合入。同理，若某 change 只勾了部分 tasks 就提交 PR，退役前的 100% 全勾要求会拒绝，
退役后 `requires_building_review` 因不满足前置而不触发，**等于绕开**。

**口径定性**：退役前是「旧机制兜底 + 新机制更薄」，退役后是「**只剩薄的那层**」——本退役**放大**了
issue [#235](https://github.com/Xingkai98/asterwynd/issues/235) 的缺口（主 session 已在 #235 加评论
交叉引用本退役）。

**处置（grill D9 裁定，用户 2026-09-22 确认）：显式接受消失，不顺带移植 checker。** 反对移植的理由：
`_find_todo_residuals` 依赖 `git diff --name-only origin/master`（`check_phase_done.py:200`），而
checker 走 `--base-ref`（CI 传 `${{ github.event.pull_request.base.sha }}`，`.github/workflows/ci.yml`），
直接搬运会在 CI 上退化为「与 master 比」的**语义漂移**；正确移植需重新设计 diff 基线，属**新增能力面**
而非退役配套。收口入口见 issue [#235](https://github.com/Xingkai98/asterwynd/issues/235)。

## awaiting 态无 CLI 进入/解除通道（retire-4phase-state-machine 残留面）

`retire-4phase-state-machine` 删除了 `flow block` / `flow confirm`（及 `flow approve`）后，
`blocked_entered` 与 `blocked_resolved` 两个事件**不再有任何 CLI 写入者**（原写入者
`workflow_state.py` 的 `cmd_flow_block` / `cmd_flow_confirm` 与 `manager.py` 的 `block`/`unblock`
均已删除）。但 guard 的 awaiting 执法**保留且不弱化**——`scripts/workflow_guard.py` 的
`_awaiting_block_reason` 仍会对 `is_awaiting_state` 为真的 change 拦截所有写操作（exit 2），
且不可经 Bash 绕过。

**触发条件**：若某 change 的事件日志投影为 `blocked.awaiting_*`（进入方式只剩手写
`workflow-events.jsonl`），合入后将**无法用 CLI 解除**——`flow confirm` 已不存在。唯一出路是手写
`workflow-events.jsonl` 追加 `blocked_resolved`（该文件受保护，需配解释事件）。

**实测现状**：本 change 合入时全仓 awaiting change 数为 **0**，故不会立刻自锁。这是**保留执法、
放弃通道**的有意取舍（执法不弱化是红线，进入通道无生产调用方故随之删除），不是待修缺口。
若未来重新需要 awaiting 流程，应按新能力重新设计进入/解除通道，而非恢复已退役的 gate 家族。

## 受保护路径解释门禁是「防误改」而非「防伪造」（fix-issue-229 实测复核，issue #229）

`scripts/check_openspec_artifacts.py` 的 `check_protected_path_explanations` 判定「受保护路径被改动时，
是否存在覆盖它的结构化解释事件」。它**只校验事件日志里有匹配的 `event_type` + `artifact_path` + 必填字段**，
不校验发起该事件的 change 是否真实立项。

**黑盒复现（fix-issue-229 在 master 上隔离 worktree 实测）**：

| 伪造形态 | checker 结果 |
|----------|--------------|
| 裸目录（只有 `workflow-events.jsonl`，无 `proposal.md`） | **exit 1**（`missing required file: proposal.md`） |
| 完整伪造 change（`proposal.md` 含各必填节 + `diagnosis.md` + 一条自述 `protected_artifact_explained`） | **exit 0，整体放行** |

即：伪造者手写一行 JSON 即可为任意受保护路径改动「背书」，无需跑任何 CLI。

**该缺口是既有属性**，不是 fix-issue-199 引入：修复前用「先跑 `flow status --change <fake>` 让 CLI
自愈写出 `handoff.json`」同样可过闸（旧前置只看 `handoff.json` 存在）。

**处置：机械加固不可行，不引入新机制——本条定位为「已知边界」而非「待修缺口」。** 三条设想路径均已实测排除：

1. **`approved_by` 绑定真实身份**——`_validate_protected_artifact_event`（`check_openspec_artifacts.py:1153`）
   只查**字段存在性**，值是完全自由字符串，bot 无法区分真人；
2. **靠 PR 审批背书**——仓库 `required_approving_review_count = 0`（无第二 reviewer 可依赖；平台门本身见 #231）；
3. **收紧锚点（要求 `tasks.md`／backlog 登记）**——解释门禁只看事件日志，不读其它文件，
   任何「伪造者能顺手补上」的文件当不了门槛。

故该门禁的定位是**防误改**（防漏配事件、防手滑），**不是防伪造**；真正的信任边界在仓库外——
**谁拥有 push 权限**。tracker 见 issue [#229](https://github.com/Xingkai98/asterwynd/issues/229)（按本结论关闭）。

## 受保护写通道的 change id 前置未专门拒绝 `..`（fix-issue-229 复核，issue #231）

`_require_change_target`（`workflow_state.py`）的 id 合法性前置只拒绝**绝对路径**与含 `/` `\` 的 id
（#199 加），`..` 不在其列。`fix-issue-231` 记录：`Path("..").is_absolute()` 为假且不含分隔符，
`CHANGES_ROOT / ".."` 会解析到 `openspec/`。

**复核结论（fix-issue-229 实测）**：`--change ..` 现在**已被拦下**（实测 `artifact-event --change ..`
→ exit 1），但拦住它的是**锚点兜底**（`..` 解析到 `openspec/`，该目录无 `proposal.md` 且无 `handoff.json`），
而非专门的路径校验规则。故「没有专门拒绝 `..`」这一点在实现层面仍成立，但**当前不可利用**
（依赖 `openspec/` 下不存在锚点文件；#199 的 R3 审阅已实测同一结论）。属**低危已知边界**，
不单独加固；tracker 见 issue [#231](https://github.com/Xingkai98/asterwynd/issues/231)。

## 归档 change 的 review manifest 写入/校验双盲区（fix-issue-199 收尾实测，issue #232）

**A. 写入盲区**（**已由 fix-issue-232-archive-write 收口**，2026-09-21）：`scripts/workflow_state.py`
的 `_require_change_target` 原用 `CHANGES_ROOT / change_id` 定位目标、**只看 active 目录**，不回退
`archive/`。故 `fix-issue-199` 修好的 CLI 只覆盖「归档前」写 manifest；归档后再需要生成只能绕底层
`write_review_manifest(..., archived=True)`。实测：对已归档 change 调 `review-manifest` 报
「change ... 不存在」。

收口内容（PR 见 change `2026-09-21-fix-issue-232-archive-write`）：目标解析改为 active 优先 →
归档回退，**委托 `review_manifest.change_dir_for(archived=True)`**（不是复用
`_flow_resolve_change_dir`——后者回退拼裸 id，对仓库全部带 `YYYY-MM-DD-` 前缀的归档目录是**死代码**）；
`cmd_review_manifest` 据解析结果传 `archived=`；归档目标跳过投影刷新（避免在已提交的归档目录写出
`handoff.json` / `workflow-state.json`）并做只读 `verify_projection` 告警；归档目标要求解析结果目录名
为裸 `<id>` 或 `<date>-<id>`、`--change` 拒绝带日期前缀的 id（否则写入的 `change_id` 会触发 CI
`change_id mismatch`）。

**A-遗留 1（`flow status` 归档查询，仍开放）**：`_flow_resolve_change_dir` 对归档 id 仍返回 `None`
（`flow status --change <归档 id>` 实测 exit 1「不存在」）。它与写通道无关、属既存缺陷，本 change
按非目标未修，仍留在 issue [#232](https://github.com/Xingkai98/asterwynd/issues/232) 跟踪。

**A-遗留 2（`change_dir_for` 前缀正则缺 `$`，仍开放）**：`agent/workflow/review_manifest.py:47` 的
`re.match(rf"\d{{4}}-\d{{2}}-\d{{2}}-{escaped}", name)` 无 `$` 锚点，归档下并存 `alpha` 与
`alpha-beta` 时查询 `alpha` 会命中 **`alpha-beta`**（另一个 change）的目录，且结果依赖 `iterdir()`
顺序。当前仓库 89 个归档 id 实测无前缀碰撞（潜在而非现实故障）。本 change 已在调用侧加事后断言
fail-closed（解析目录名必须为裸 `<id>` 或 `<date>-<id>`），**未改 `change_dir_for` 本身**（它被 checker
`--check-archived` 共用，改动面超出该 bugfix）。收紧正则属独立决策，跟踪见
issue [#232](https://github.com/Xingkai98/asterwynd/issues/232)。

**B. 校验盲区**（**已由 fix-issue-232-archived-manifest-gate 收口**，2026-09-22）：`.github/workflows/ci.yml`
原来跑的是 `check_openspec_artifacts.py --base-ref ... --require-base`，**不带 `--check-archived`**；
默认模式把 `archive/` 显式排除在扫描外，归档 change 只在 `--check-archived` 下才走
`_check_review_manifests(..., archived=True)`（`:1425-1435`）。AGENTS.md 要求「归档收尾与实现同一 PR」，
于是**归档动作本身把 change 移出了 CI 校验范围**——恰在变得可合入的那一刻脱离 manifest 校验。实测对照：
缺 manifest 时默认模式 `checks passed`（漏检），`--check-archived` 报 `review manifest missing`（能抓）。

注：`_check_review_manifests` 对已存在的 `*-review.md` 逐个 verify，**能**报出 missing manifest；
漏检的真因是默认模式根本不进 archive 目录，而非「glob 枚举不到」。

收口内容（PR 见 change `2026-09-22-fix-issue-232-archived-manifest-gate`）：直接把 `--check-archived`
接进 CI 会红——**实测恰好 15 条既有归档 change 报 `tasks hash mismatch`**。根因是流程顺序而非篡改：
manifest 在**审阅 PASS 时**生成（tasks 未全勾），收尾阶段（spec sync / 归档 / backlog 移除）还会再勾项或补行，
15 条的差异行**全部落在 checkbox 行上**（勾选翻转、同行描述更新、一条纯新增；`spec_hash`/`report_hash`/git diff
全过）。因此本 change：

1. `verify_review_manifest` 的 `tasks_hash` 校验加 `not archived` 前置——**归档语境不以此判失败，active 语境仍强校验**；
   其余校验（manifest 存在性 / 字段 / `spec_hash` / `report_hash` / git span）**全部保留**。
2. 该降级**不静默**：`--check-archived` 在 stderr 输出一行汇总（`tasks_hash 已按归档语境跳过（N 个 change）`），
   note **不混入** `verify_review_manifest` 的返回列表（否则会被当 error → exit 1，降级失效）。
3. `.github/workflows/ci.yml` 的 `validate` job 增 `--check-archived --skip-protected-paths --skip-backlog` 步骤；
   加 `--skip-*` 是为避免默认 `--base-ref master` 在 CI 上解析失败打出无意义 WARNING 与重复检查（该 WARNING
   只在 CI 现形，本地 `master` 可解析看不到）。
4. 立「manifest 在该 change 的 `tasks.md` 最终化之后生成」纪律，写入 spec 与 `docs/development-guide.md`。

**B-残余风险（已接受，勿误读为「归档 manifest 不用管」）**：归档语境**不再检测 `tasks.md` 的任何编辑，含
checkbox 行内的描述级编辑**（如把 `1813 passed` 改成 `1814`、或把某条任务描述改成与事实不符的表述）。
承载「审阅了什么」的实质证据是 `report_hash`（审阅报告原文）与 `spec_hash`（当时已冻结的规格 delta），
二者仍被强校验。三个「保住 tasks 检查力」的替代方案已实测排除：①「忽略勾选」归一化 → 剥离 checkbox 行后
只剩 8–18 行标题（任务描述本身就在 checkbox 行里），等于废检、属假绿；② checkbox 归一为 `[TASK]` → 仍 2 条红；
③ 绑定 `head_sha` 处的 `git show` blob → 32 过/10 红（manifest 用工作区而非提交时刻的 tasks.md 计算哈希）。

### head_sha 校验口径债（A′ 收尾时对齐措辞，issue #232）

spec `dev-workflow-state-machine/spec.md` 的「manifest 字段和 hash 校验」Scenario 原写「checker SHALL 验证
`head_sha` 匹配当前 `HEAD`」，但实现 `_verify_git_span`（`agent/workflow/review_manifest.py:209-232`）**从不做此校验**
——它只查 `base_sha`/`head_sha` 是否为存在的 commit + `diff_hash` 匹配。该断言语义上**不可满足**：实测 44 份归档
manifest 中 **0 份** `head_sha == HEAD`（37 份是 HEAD 祖先、7 份不可达），且「生成 manifest」这个动作本身就移动
HEAD（例：`2026-09-14-subagent-concurrency-queue` 的 manifest 记 `head_sha=ea22b65c`，而写入它的 commit 是
`357cec0`）——除非把 manifest amend 进同一 commit，否则永不成立。反向「修实现使其校验」会让 43/43 历史 manifest
转红，不可行。

**处置**：已在 fix-issue-232-archived-manifest-gate 中把该 Scenario **改措辞与实现对齐**（删去「匹配当前 `HEAD`」，
保留「`base_sha`/`head_sha` 均为 commit + `diff_hash` 匹配」），原始意图记录于此，不再声称未做的检查。
跟踪见 issue [#232](https://github.com/Xingkai98/asterwynd/issues/232)。

**B-覆盖面隐含上界（记录，不处理）**：`--check-archived` 是**漂移检测**而非「归档必须有审阅」的补票门，两处上界
（审阅 R1 指出，均非本 change 引入、修复方向超出本 change 边界）：

1. **无 `Change Type` 的归档目录整段跳过**：`scripts/check_openspec_artifacts.py:1428-1433` 对
   `parse_change_type` 返回 `None` 的目录 `continue`。实测 90 个归档目录中 4 个（均 `2026-06-21-*` 老世代）被跳过；
   当前这 4 个都没有 `reviews/`。
2. **压根没有 `reviews/` 的归档 change 不被要求补 manifest**：`_check_review_manifests` 在
   `review_dir` 不存在时直接 `return []`，且 `requires_building_review` 对 `archived=True` 恒为 False（设计意图：
   「归档 change 要么早于本门禁、要么已满足」，不为历史 change 追溯索取审阅）。实测 42 个非 docs 归档 change
   完全无 `*-review.md` 却通过 `--check-archived`；**只覆盖已有 `*-review.md` 的 change 的漂移**。
   `openspec/changes/archive/**` 的写入仍受 `change_archived` 事件约束，但事件不蕴含 manifest 存在。

即 AGENTS.md 新增段落的「归档 change 也在校验范围内」应读作：**已有审阅报告的归档 change 不再脱离校验**，
而非「每个归档 change 都必须有 manifest」。若要把后者也变成门禁，属独立 change（需为历史 change 补审阅或豁免）。

### 完成度门禁的残余面（issue #235）

归档点完成度门（`_check_new_archived_completion_gates`）把审阅证据类门禁的触发点从「tasks 全勾」改挂「归档点」，
已知两处残余面，均为**流程违规**而非静默绕过：

1. **实现 PR 完全不归档** → 门不触发。这违反 AGENTS.md「OpenSpec 收尾」硬规则（实现 PR 必须含归档收尾），
   但该 change 仍以 active 形态可见，不会被静默吞掉。要机械兜住需另立「active change 存在时长 / 未归档检测」门，
   超出本 change 边界。
2. **归档到无日期前缀目录** → 已由本 change **直接报错**兜住（不再只是记债）：`--diff-filter=AR` diff 中出现
   `openspec/changes/archive/` 下但不匹配 `<YYYY-MM-DD>-<id>/` 的路径会进 `errors`。此条记债仅为说明
   「为何该守卫是必需的」——缺了它，这类目录既不匹配归档正则、又被 `iter_change_dirs` 排除在 active 之外，
   会落成「谁都不管」的静默面。当前语料触发面为零（93/93 归档目录都带日期前缀）。

另外，**本门不追溯既有归档**：只有本 PR 新建的归档目录（`AR` diff ∩ base 树不存在）才被求值。对 89 个可解析
历史归档实跑四道门，69 个会失败（48 个连 `reviews/` 目录都没有）——这正是必须叠加「base 树不存在」条件的原因，
否则任何「往旧归档补文件」的 PR（`#234`/`#236`/`#238` 的形态）都会触发对陈旧 change 的误判。

**既存机制弱点（本 change 未引入、也未修复）：受保护路径的解释事件是全仓搜索命中的。**
`_protected_artifact_explanation_errors`（`scripts/check_openspec_artifacts.py`）用
`changes_root.rglob("workflow-events.jsonl")` 遍历**整个仓库**的事件日志，而 `_change_id_for_event_log` 的
expected id 取自事件日志**自身所在目录**——两者都不校验「该事件是否属于当前正在改这个文件的那个 change」。
后果：一个 change 修改 `docs/known-debt.md` 却**没写自己的** `protected_artifact_explained` 事件时，只要**任意**历史
change 的日志里有一条指向同一路径的陈旧事件，门禁就会放行（实测：只留本 change 的事件 → 报
`changed without workflow event explanation`；再叠加一条陈旧归档事件 → GREEN）。**即 CI 绿不等于承诺的证据存在。**
本 change 已为自己的 `docs/known-debt.md` 修改写了事件，并以测试
`test_own_change_explains_protected_artifact_with_its_own_event` 钉死这一点；但把该门收窄为「只认本 change 的事件」
属独立改动面，超出本 change 边界。
