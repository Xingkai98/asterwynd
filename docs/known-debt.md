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
