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

## workflow_state.py 四个 legacy 子命令对当代 change 失效（fix-issue-199 实测，issue #227）

`fix-issue-199`（2026-09-21）解除 `artifact-event` / `review-manifest` 两条受保护写通道的
`handoff.json` 硬前置时，实测出同源漏网共**四处**（issue #199 原文与立项文档只点到三处）：

- `cmd_current`（`scripts/workflow_state.py`）：读 handoff 状态打印 `state`，对当代 change 恒报
  「没有 handoff.json」。当代等价物是 `flow status`（打印投影 state）。
- `cmd_spawn`：wayfinding 时代子 change 派生命令，要求父 change 处于 `wayfinding.<gate>`；
  停用四阶段状态机后无 wayfinding phase 推进，实际不可用。它还有两条既有测试
  （`tests/test_workflow_state_cli.py` 的 spawn 用例）直接依赖 `handoff.json`。
- `cmd_validate`：校验 `handoff.json` 结构，对当代 change 恒报「没有 handoff.json」。
- **`discover`（实测补出的第四处，最易误导）**：`_cmd_discover_text` / `_cmd_discover_json` 在
  `_load_handoff` 返回 None 时直接 `continue`，**对当代 change 完全静默**。实测两个 gen-2 change
  （各有 `proposal.md` + `change_created` 事件日志）下文本模式零行输出，`--format json` 报
  `"active_count": 2` 但 `"active_changes": []`。它是 CLI usage 里的**默认命令**。
  另有 AGENTS.md「不再需要 discover/advance/approve」与 spec 仍描述 discover 的口径漂移。
- **文档口径漂移**：`docs/requirements-process.md` 的「开发流程」节仍把 change 生命周期描述为
  「四个活跃阶段（phase），由 `agent/workflow/` 状态机驱动，`handoff.json` 是由事件 replay 生成的
  projection」。该段写于 2026-07-31，早于四阶段状态机停用（AGENTS.md 已声明「旧的四阶段状态机仪式
  （phase/sub_state 推进、handoff.json、gate 停止）已停用」），属**既有**漂移、非 fix-issue-199 引入；
  fix-issue-199 只解除写通道前置，未使该段更不准确，故不在该 bugfix 内改写流程文档，随本条一并跟踪。

**处置**：不在 fix-issue-199 内修（超出该 bugfix 的验收面，且删 `spawn` 会连带删既有测试、
`discover` 有完整实现面 `path/next_action/gate_check`，属独立 API 变更）。跟踪见
issue [#227](https://github.com/Xingkai98/asterwynd/issues/227)。

## 当代 change 与 handoff.json 的三层残留耦合（fix-issue-199 实测，issue #228）

`handoff.json` 是已停用的四阶段状态机遗物，当代 change 不产生它，但代码库仍有三层耦合，
拆除需同步改三处，只改一层会立刻引发新 FAIL：

1. **自愈仍产出退役 artifact**：`_refresh_workflow_state`（`scripts/workflow_state.py`）在写
   `workflow-state.json` 的同时**同步映射写 `handoff.json`**；`flow status` 的 stale 自愈
   （`_flow_status_projection`）与写事件后的 `_flow_refresh_after_event` 都会走到它。
   后果之一是**顺序依赖掩蔽**：冷状态（新 worktree / 新 clone）下 `artifact-event` 报错 exit 1，
   但只要先跑一次 `flow status`，自愈写出 `handoff.json`，同一命令立刻变可用——
   这正是 issue #199 长期不易复现的原因。
2. **phase 协议层仍把 `handoff.json` 当必填**：`agent/workflow/doc_artifact_protocol_openspec.py`
   的 `FileRequirement(..., "handoff.json")` 与 `scripts/check_phase_done.py` 的
   `_check_handoff_at_gate`。实测在 gen-2 change 上删掉 `handoff.json` 后，`flow approve --phase planning`
   的 FAIL 从 4 条变 6 条（新增「Missing required file: .../handoff.json」与「handoff.json 不存在」）。
   即真正的耦合在协议层必填文件表，不在自愈。
3. **该文件未被 gitignore**：`handoff.json` / `workflow-state.json` 在 active change 下既不被 git
   跟踪也不在 `.gitignore`，自愈产物以未跟踪文件形式出现在 `git status`，收尾 `git add -A` 有被
   误提交的风险。（口径限定：归档目录里 `archive/2026-08-15-flow-event-projection/workflow-state.json`
   确实被跟踪，属历史遗留。）

**处置**：fix-issue-199 只解除写通道前置，按证据维持 `_refresh_workflow_state` 不变（改它会让
协议层 FAIL 增多，改动面大于收益）。跟踪见 issue [#228](https://github.com/Xingkai98/asterwynd/issues/228)。

## 受保护路径解释门禁可被伪造 change 目录糊过（fix-issue-199 实测，issue #229）

实测（`fix-issue-199` 立项期）：在仓库里构造一个假的 change 目录
（`openspec/changes/<fake>/proposal.md` + 一条 `protected_artifact_explained` 事件），
`scripts/check_openspec_artifacts.py` 的 `check_protected_path_explanations` 返回 **PASS**——
门禁只校验「存在结构化解释事件」，不校验目标 change 是否真实立项。

该缺口是**既有属性**，不是 fix-issue-199 引入或放大的：修复前同样可行——先跑
`flow status --change <fake>` 让 CLI 自愈写出 `handoff.json`（首条为非状态事件也能投影成功），
旧前置随即放行。本次锚点放宽（`proposal.md` 或 `handoff.json`）不使其变差。

**处置**：不在 fix-issue-199 内修（属门禁加固的独立 effort）。跟踪见
issue [#229](https://github.com/Xingkai98/asterwynd/issues/229)。

## 受保护写通道的 change id 前置未拒绝 `..`（fix-issue-199 R3 审阅观察项，issue #231）

`fix-issue-199` 在 `scripts/workflow_state.py` 的 `_require_change_target` 加了 id 合法性前置
（拒绝绝对路径与含 `/` `\` 的 id，封住「绝对路径可把事件写到仓库外」与 gen-1 路径型目标的裸
traceback 回归），但 `--change ..` 未覆盖：`Path("..").is_absolute()` 为假且不含 `/`，
`CHANGES_ROOT / ".."` 会解析到 `openspec/`。

**实测不可利用且非本次引入**：本仓库 `openspec/proposal.md` 与 `openspec/handoff.json` 均不存在，
`..` 在锚点检查处即 exit 1；base 提交对同一输入同样不受锚点约束（既有属性）；spec delta 把拒绝面
限定为「绝对路径或含 `/`」，实现与规格一致。

**处置**：不在 fix-issue-199 内修（R3 审阅判 PASS 并归为 Low/不阻塞；改代码会超出审阅 3 轮封顶而
未被复审）。跟踪见 issue [#231](https://github.com/Xingkai98/asterwynd/issues/231)。

## 归档 change 的 review manifest 写入/校验双盲区（fix-issue-199 收尾实测，issue #232）

**A. 写入盲区**：`scripts/workflow_state.py` 的 `_require_change_target` 用 `CHANGES_ROOT / change_id`
定位目标、**只看 active 目录**，不回退 `archive/`（对照 `_flow_resolve_change_dir` 有归档回退）。
故 `fix-issue-199` 修好的 CLI 只覆盖「归档前」写 manifest；归档后再需要生成只能绕底层
`write_review_manifest(..., archived=True)`。实测：对已归档 change 调 `review-manifest` 报
「change ... 不存在」。

**B. 校验盲区**：`.github/workflows/ci.yml` 跑的是 `check_openspec_artifacts.py --base-ref ... --require-base`，
**不带 `--check-archived`**；默认模式把 `archive/` 显式排除在扫描外，归档 change 只在
`--check-archived` 下才走 `_check_review_manifests(..., archived=True)`（`:1425-1435`）。
AGENTS.md 要求「归档收尾与实现同一 PR」，于是**归档动作本身把 change 移出了 CI 校验范围**——
恰在变得可合入的那一刻脱离 manifest 校验。实测对照：缺 manifest 时默认模式 `checks passed`（漏检），
`--check-archived` 报 `review manifest missing`（能抓）。

注：`_check_review_manifests` 对已存在的 `*-review.md` 逐个 verify，**能**报出 missing manifest；
漏检的真因是默认模式根本不进 archive 目录，而非「glob 枚举不到」。

**处置**：不在 fix-issue-199 内修（改 CI / checker 属独立门禁加固，超出该 bugfix 边界）。
本 change 已用底层函数按 `archived=True` 生成并验证 manifest。跟踪见
issue [#232](https://github.com/Xingkai98/asterwynd/issues/232)。
