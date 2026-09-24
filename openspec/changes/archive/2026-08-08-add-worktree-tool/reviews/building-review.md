# Building Review: add-worktree-tool（Round 5）

**Verdict**: CHANGES_REQUESTED

**审阅基线**: base_sha=1e16ee14e8103b06786eb5407a50be36dd466f57（origin/master） head_sha=9ef7bfa1416fb6278a525c40f7a39f31c3a848c6
**审阅时间**: 2026-09-24

> 说明：本报告是 8 周前 PR #113 合并 master 后的**基线复验审阅**，非原 Round 4 的续写。
> 复审重点是三处复验修复（提交 `9ef7bfa`）是否真的落地、是否引入新问题。
> **关键结论：R1 修复（提交 `922bc45`）引入了一条数据丢失缺陷，见 Issue 1。**

## Tasks Verification

| 任务 | 声称产出 | 核验结果 | 证据 |
| --- | --- | --- | --- |
| 1.1 | tool-system spec delta | ✅ 存在 | `openspec/changes/archive/2026-08-08-add-worktree-tool/specs/tool-system/spec.md`（ADDED 1 Requirement + 7 Scenario） |
| 1.2 | 范围/非目标/验收标准 | ✅ 存在 | `proposal.md`「## 非目标」「## 验收」 |
| 1.3 | grill 设计追问 + 用户停轮确认 | ✅ 存在 | `reviews/grill-design.md`，`## User Confirmation` 8 条（Q1-Q8）全带实质答复与时间 `2026-08-07` |
| 1.4 | Impact Analysis | ✅ 存在 | `proposal.md`「## Impact Analysis」表（11 行，无 `unknown`/`TBD`/`待确认`） |
| 1.5 | Reference Implementation Research | ✅ 存在 | `proposal.md:82-92`：`research_tier: full` / `status: enabled` / reason / findings / design impact 齐全 |
| 1.6 | Pre-Implementation Review | ✅ 存在 | `design.md:85-92`（已确定/已否决/剩余风险） |
| 1.7 | **规格同步**（复验补做） | ✅ 存在且逐字节一致 | `openspec/specs/tool-system/spec.md:221-272`；与归档 delta 的 Requirement 块 `diff` 结果 **IDENTICAL**（各 52 行）；归档目录含 `specs/`；事件日志补 `seq 2 current_spec_synced`（见验证命令节） |
| 2.1 | Enter/Exit 单测 | ✅ 存在 | `tests/agent/tools/test_worktree_tools.py`（21 例） |
| 2.2 | tmp_path 真实 git 仓库全流程 | ✅ 存在 | 同上 `test_enter_worktree_creates_and_rebinds` / `test_file_tool_boundary_rebound_into_worktree`（`test_worktree_tools.py:375-389`） |
| 2.3 | 负向路径 + 失败回滚 | ✅ 存在 | `test_enter_worktree_not_a_git_repo`、`test_enter_worktree_nested_rejected`、`test_exit_worktree_dirty_rejected_state_unchanged`、`test_enter_worktree_rollback_on_post_add_failure` |
| 2.4 | AgentLoop 层测试 | ⚠️ 部分 | `test_registry_enter_exit_updates_policy_root:396-413` 是 **ToolRegistry 层**（register + `registry.execute`），不是 AgentLoop 层。核心断言（调用后 policy root 正确）已覆盖，口径偏窄 |
| 2.5 | benchmark smoke 沉淀 | ✅ 存在并实测闭环 | `benchmarks/tasks/asterwynd-008-worktree-tools/`（task.json/issue.md/gold.patch/test.patch）+ `tests/agent/tools/test_worktree_benchmark_smoke.py`；base 红 → gold 绿**本次实测复现** |
| 3.1-3.2 | Enter 创建+切换 / Exit keep+remove | ✅ 存在 | `agent/tools/builtin/worktree.py:135-285` |
| 3.3 | policy root 重绑定 + 权限元数据 + deny pattern | ✅ 存在 | `worktree.py:203-204`；`agent/workspace_policy.py:45-46`（`.asterwynd/worktrees/**`）；权限元数据由类属性提供，测试 `test_permission_metadata` 断言通过 |
| 3.4 | 注册进 ToolRegistry + schema | ✅ 存在 | `agent/tools/factory.py:40/111-112/334-335/447-448`；smoke 测试断言 `get_all_schemas()` 含两名 |
| 3.5 | 新影响面回写 | ✅ 存在 | `design.md:57`（D3 回写 R1 越权边界）、`design.md:92` 剩余风险已回写 |
| 3.6 | 调研结论修正回写 | ✅ 无需修正 | 调研结论（Claude Code 对标）未被实现推翻 |
| 3.7 | 更新必要文档 | ⚠️ 部分 | 本分支相对 origin/master **只改了 `docs/openspec-change-backlog.md`**（`git diff --name-status origin/master...HEAD -- docs/`）。`docs/architecture.md` 内置工具表（`:44-58`）**未**列 EnterWorktree/ExitWorktree；`docs/interview-script/` 无对应内容。任务文案带「如有新能力线」限定词，故判⚠️而非❌ |
| 4.1-4.6 | 验证 | ✅ 存在 | 见「验证命令实跑结果」节，均本地复现通过（4.2 的两条失败见下文说明） |
| 5.1 | 归档 | ✅ 存在 | `openspec/changes/archive/2026-08-08-add-worktree-tool/`；active 目录（`openspec/changes/add-worktree-tool/`）已不存在 |
| 5.2 | backlog 清理 | ✅ 存在 | `docs/openspec-change-backlog.md:78` 标「✅ 已合入并归档（2026-08-08）」；未实现队列条目已移除 |
| 5.3 | 无残留 TBD/unknown/待确认 | ✅ 存在 | `grep -n "TBD\|unknown\|待确认" proposal.md design.md` → 零命中 |
| 5.4 | 调研记录最终化 | ✅ 存在 | 同 1.5；`.dev/reference-repos.txt` 不可用仅记为事实，未写成项目依赖 |
| 5.5 | OpenSpec validate + artifact checker | ✅ 实跑通过 | 见验证命令节 |
| 5.6 | `(post-merge)` 标记 | ✅ 恰当 | issue #111 的 comment+关闭本质是合入后动作，标 `(post-merge)` 门禁认可（`scripts/check_openspec_artifacts.py:112-116`） |

## Issues

### 1. [高] `EnterWorktree` 失败兜底会**删除已存在的 worktree**（数据丢失）

- **位置**：`agent/tools/builtin/worktree.py:166-181`（关键行 `:169`）
- **问题**：`git worktree add -b <name> ...` 失败后**无条件**执行 `git worktree remove <wt_path>`，且该返回值被当作"清理成功"直接静默接受。但当失败原因是**分支已存在**（`exit 255`，最常见）时，`<wt_path>` 上很可能本来就有属于用户的、合法的 worktree——`remove` 成功返回 0，于是**用户的 worktree 连同其内容被删除**，而返回给 agent 的 text 只说"worktree 创建失败"，完全没有提示刚刚删掉了一个已有 worktree。
- **真实触发路径**（均为设计内的正常用法）：
  1. `EnterWorktree(name="fix-x")` → `ExitWorktree(keep=true)`（D3 明确：keep=true **保留** worktree 与分支）→ 再次 `EnterWorktree(name="fix-x")` 想接着干 → 分支已存在 → add 失败 → **删除上一轮保留的 worktree**。
  2. 上一次会话/用户手工留下的 `.asterwynd/worktrees/<name>`，同名重入同样被删。
- **实测证据**（临时 git 仓库，见「变异验证」节复现脚本）：
  ```
  预置 worktree keepme（clean，含已提交文件 newfile.py）
  → EnterWorktree(name="keepme")
  error_type: worktree_create_failed
  text: Error: worktree 创建失败: ... fatal: a branch named 'keepme' already exists
  wt exists AFTER: False   ← worktree 被删除
  file AFTER: False        ← 内容丢失
  worktrees AFTER: ['worktree /tmp/tmpiez0erlk']    ← 只剩主工作区
  ```
- **归因**：`base`（`454bebe`）没有这行 remove，失败时只返回错误、现场完好。该破坏性行为由 review-loop **R1 修复**（提交 `922bc45`）引入，并被 **R3 修复**（提交 `43ffd4a`）补上返回值检查（补的正是"清理失败"分支，反而把 clean 情形的静默删除固化成两条分支）。也就是说：**这是本轮要复验的 R1/R3 修复自身引入的新问题。**
- **影响面延伸**：`benchmarks/tasks/asterwynd-008-worktree-tools/gold.patch` 就是 R1 的 diff，**同样含这条破坏性 remove**（该缺陷已进入 benchmark 交付物，只是 smoke 测试不覆盖该路径）。
- **建议修法**：add 失败时不要无条件 remove。二选一：
  - 仅在能证明"这次 add 确实留下了注册"时才清理（例如失败后 `git worktree list --porcelain` 中该 path 存在，且此前不存在）；或
  - 直接回到 base 语义：add 失败只返回结构化错误、不做任何 remove（git 对 `-b` 冲突本就无残留注册，D2 里"非 branch 冲突可能残留"的场景应单独用"先探测 path 是否为空目录"来判定）。
  - 无论哪种，都必须补一条回归测试：**预置一个同名 worktree → 调 EnterWorktree → 断言 worktree 与文件仍在**。

### 2. [中] 失败文案与事实不符（dirty 保留场景误导 agent）

- **位置**：`agent/tools/builtin/worktree.py:169-177`
- **问题**：当已有 worktree **有未提交改动**时，`git worktree remove` 被 git 拒绝，代码走 `cleanup.returncode != 0` 分支，返回：
  `"Error: worktree 创建失败且清理未完成，worktree 可能残留: ...; 清理: fatal: '...' is not a working tree"`
  实测该 worktree 其实是**完好保留**的（`dirty file AFTER: True`）。文案 "清理未完成 / worktree 可能残留" 会让 agent 误判环境脏了、进而做出更多破坏性补救动作；而事实恰恰相反——现场是安全的，真正的问题是"名字被占用"。同理，Issue 1 的 clean 场景返回的"创建失败"也未告知 worktree 已被删除。
- **建议修法**：区分三类失败并给出准确文案——(a) 分支/名字已被占用（提示换名或 `ExitWorktree` 退出后再进）；(b) 本次 add 确实残留注册（提示残留路径）；(c) 已有 worktree 完好保留（明说未受影响）。

### 3. [低] `base_branch` 未做校验，存在参数注入/语义静默改变

- **位置**：`agent/tools/builtin/worktree.py:127-131`（schema）、`:164-165`（直接拼进 git argv）
- **问题**：`base_branch` 原样作为 `git worktree add -b <name> <path> <base_branch>` 的尾参，git 允许选项出现在任意位置，因此实测 `base_branch="--force"` **被接受**，结果是 base 被静默忽略、按 HEAD 创建（无报错），调用方以为拿到了指定基线；`base_branch="--detach"` 则直接失败。相比之下 `name` 已用 `check-ref-format` 做了前置校验（R1-4），base 同属"外部输入进 argv"却漏了。
- **建议修法**：对 `base_branch` 做与 `name` 同级的校验（`git check-ref-format` 或 `rev-parse --verify`），或改用 `--` 分隔符隔离位置参数。

### 4. [低] 测试缺口：没有"同名 worktree 已存在"的回归测试

- **位置**：`tests/agent/tools/test_worktree_tools.py:182-193`（`test_enter_worktree_branch_conflict`）
- **问题**：该用例只造了"分支已存在、但**没有**对应 worktree"（`git branch test-wt`，故 remove 报 `not a working tree`），恰好绕开了 Issue 1 的破坏路径，所以 24 例全绿也没能挡住这个缺陷。Issue 1、2 的修法都必须配回归测试。
- **建议修法**：补两个用例——干净同名 worktree（断言不删）、dirty 同名 worktree（断言不删 + 文案准确）。

### 5. [低] 任务勾选口径略宽

- **位置**：归档 `tasks.md` 2.4 / 3.7
- **问题**：2.4 声称的 "AgentLoop 层测试" 实际是 ToolRegistry 层；3.7 声称"更新必要文档（架构说明、工具文档、面试讲稿）"但本分支仅改了 backlog。两者都有"如/如有"限定词或已覆盖核心断言，不构成事实错误，但勾选依据弱于字面。
- **建议修法**：后续 change 把这类任务文案写成可机械核验的形式（如显式列出目标文件），或勾选时在任务行注明实际交付物。

### 6. [提示] 归档 manifest 已失效（本报告写入后）

- **位置**：`reviews/building-review-manifest.json`
- **问题**：该 manifest 绑定的是上一轮报告（`report_hash: sha256:017dab2a...`，`head_sha: 43ffd4a`），其 `verdict: PASS`。本报告一旦覆盖 `reviews/building-review.md`，`report_hash` 将不再匹配，`--check-archived` 归档 manifest 校验会失败。**这是预期状态，不要当作回退**：当前 HEAD 上存在 Issue 1 的数据丢失缺陷，本 change 不应以 PASS 合入。
- **建议修法**：修完 Issue 1（及 2/3/4）+ 复验通过后，再由 `/review-loop` 重新生成绑定新报告的 manifest。

## 验证命令实跑结果

```bash
export PATH=/home/happy/.local/bin:$PATH
cd /home/happy/my-agent/.claude/worktrees/add-worktree-tool+2026-08-07
```

1. `uv run pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q`
   → `24 passed in 1.99s`，exit 0

2. `uv run pytest tests/test_workflow_guard.py -q`
   → `26 passed in 11.39s`，exit 0

3. `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
   → `Totals: 28 passed, 0 failed (28 items)`，exit 0（含 `✓ spec/tool-system`）

4. `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`
   → `[archived manifest check] tasks_hash 已按归档语境跳过（49 个 change；其余 hash 与字段仍校验）` / `OpenSpec artifact checks passed`，exit 0

5. **`--base-ref` 命令的 base sha 有误（非仓库问题）**：任务书给的 `1e16ee148103b06786eb5407a50be36dd466f57` 长度 39 位，git 无法解析（`fatal: bad revision`，checker exit 1）。`origin/master` 的真实 sha 是 **`1e16ee14e8103b06786eb5407a50be36dd466f57`**（我实测 `git rev-parse origin/master`）。用正确 sha 重跑：
   `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref 1e16ee14e8103b06786eb5407a50be36dd466f57 --require-base`
   → `OpenSpec artifact checks passed`，exit 0

6. 全量 `uv run pytest -q`
   → `2 failed, 3050 passed, 9 skipped, 77 warnings in 350.49s (0:05:50)`，exit 1
   两条失败均为任务书声明的已知无害项，且**与本次 change 无关**：
   `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir`
   `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`
   失败原因是本机 `/tmp` 自身是 git 仓库（断言 `assert PosixPath('/tmp') is None`），非本次引入。

7. 归档一致性抽查：
   - `grep "Requirement: Worktree 隔离工具" openspec/specs/tool-system/spec.md` → `221:### Requirement: Worktree 隔离工具`（7 个 Scenario 齐全）
   - 主规格 Requirement 块 vs 归档 delta Requirement 块 `diff` → `IDENTICAL`（各 52 行）
   - 事件日志：`seq 1 backlog_updated` → `seq 2 current_spec_synced` → `seq 3 change_archived`（修复前为 `seq 1` → `seq 3` 跳号；`seq 3` 的 `artifact_path` 亦已由 `docs/openspec-change-backlog.md` 修正为归档目录）

## 变异验证

**A. 证明 `9ef7bfa` 的 `_isolate_changes_dir` 修复真实有效（不只是"看起来对"）**

在**一次性 detached worktree**（`git worktree add --detach /home/happy/mut-verify HEAD`，不改动被审检出）中做"改坏→变红→还原"：

| 步骤 | 操作 | 观察 |
| --- | --- | --- |
| A1 | detached HEAD（`git branch --show-current` 为空串），修复**保留** | `uv run pytest tests/test_workflow_guard.py -q` → `26 passed`，exit 0 |
| A2 | 注释掉 helper 内两行 `monkeypatch.setattr(mod, "CHANGES_DIR"/"REQUIRED_BASE", ...)` | `2 failed, 24 passed`，exit 1 —— 失败正是 `test_guard_noops_when_workflow_disabled` 与 `test_guard_resume_audit_no_longer_blocks_writes`；stderr 显示 `⛔ change 'add-minimal-tui-runtime-view' 尚未完成独立 subagent design grilling ... 请先运行 /grill`，`SystemExit(2)` |
| A3 | `git checkout -- tests/test_workflow_guard.py` 还原 | `diff -q` 与改动前文件逐字节一致 |

结论：修复**确实是**把 in-process 测试从"依赖检出状态"解耦的那一步；变异后立刻变红，且失败原因与 helper docstring 描述完全吻合（detached CI HEAD 下 branch 名规则失效 → 落到"唯一 active change"兜底 → grill 门禁拦截）。**有效，非假保护。**

**B. benchmark task 红→绿闭环（独立复现，未采信历史报告）**

在一次性 detached worktree 检出 `base_commit=454bebe`：

- `git apply --check test.patch` → rc=0（`git ls-tree 454bebe` 确认 smoke 文件在 base 树不存在，new-file patch 适用）
- base + `test.patch` → `1 failed, 2 passed`，失败断言 `exit_res.error_type == "not_in_worktree"` 实际为 `None`（`ToolResult(text='{"workspace": ...", "removed": true}', error_type=None)`）——base 上 ExitWorktree 确实会越权删除编排层 worktree，issue.md 描述与 base 状态一致
- base + `test.patch` + `gold.patch` → `3 passed`
- `gold.patch` 与 `git diff 454bebe 922bc45 -- agent/tools/builtin/worktree.py` → `IDENTICAL`（历史报告的溯源声明成立）
- `git apply --check --reverse test.patch` 于 HEAD → rc=0，主套件 smoke 文件与 `test.patch` 逐字节一致

**C. Issue 1 破坏性行为的独立复现**（临时 `tmp_path` git 仓库，`policy`/工具直接调用）

```
enter("keepme") → exit(keep=True)       # 设计内的"保留 worktree"正常用法
预置已提交文件 newfile.py 于该 worktree
enter("keepme") 再次调用
  → error_type: worktree_create_failed
  → text 只说 "创建失败"（未提删除）
  → wt exists AFTER: False / file AFTER: False / worktrees AFTER 只剩主工作区
对照：dirty 同名 worktree → 文件保留（git 拒绝 remove），但文案说"清理未完成"
对照：base(454bebe) 同一路径 → 不执行 remove，worktree 完好
```

**D. 还原确认**：两个临时 worktree（`/home/happy/mut-verify`、`/home/happy/bench-repro`）均已 `git worktree remove --force` 清除，`git worktree list` 无残留；被审检出 `git status --porcelain` **空**、`git diff --stat` **空**。评审过程中**未留下任何未还原的修改**（唯一写入是本报告文件）。

## Spec 对齐检查

三层一致性结论：**主规格 ≡ 归档 delta ≡ 实现行为，唯一偏差是 R1 新增的越权边界未进规格（低）**。

1. **主规格 vs 归档 delta**：`openspec/specs/tool-system/spec.md:221-272` 的 Requirement「Worktree 隔离工具」块与归档 `specs/tool-system/spec.md` 的对应块 `diff` 结果 **IDENTICAL**（各 52 行，ADDED 1 Requirement + 7 Scenario 逐条一致）。任务 1.7 声称的"补写主规格 + 回填 delta + 补事件"三项已**逐项实证**，非纸面声明。
2. **规格 vs 实现（逐 Scenario 回核）**：
   - 创建并进入 → `worktree.py:135-201`，返回 `{"worktree","branch"}` ✅
   - 非 git 仓库拒绝且工作目录不变 → `:146-150` + 测试 `test_enter_worktree_not_a_git_repo` ✅
   - 嵌套拒绝且当前 worktree 不变 → `:151-155` + `test_enter_worktree_nested_rejected` ✅
   - 退出保留 → `:265-285` + `test_exit_worktree_keep_true` ✅
   - 退出删除 → `:268-279` + `test_exit_worktree_keep_false_removes` ✅
   - 删除含未提交改动被拒且状态不变 → `:254-263` + `test_exit_worktree_dirty_rejected_state_unchanged` ✅
   - 不在 worktree 中返回错误 → `:237-242` + `test_exit_worktree_not_in_worktree` ✅
   未见"规格写了代码没做"或反之。
3. **规格未覆盖的实现行为**：R1 追加的 `_is_tool_created_worktree` 越权边界（`worktree.py:24-33`、`:246-250`）**没有**对应 Scenario——7 个 Scenario 里没有"非工具自建 worktree 内 ExitWorktree 被拒且状态不变"。该边界已有实现与测试（`test_exit_worktree_rejects_non_tool_created`、smoke `test_rejected_in_orchestration_worktree`），属**规格滞后于实现**。Round 4 报告已把它记为 [低] 并建议"同步时补该场景"，而本次 1.7 补做只做了"把 delta 原样复制进主规格"，**未补该场景**。建议随 Issue 1 的修复一并补一个 Scenario。

## 结论

**Verdict: CHANGES_REQUESTED。**

- 三处复验修复中，**规格同步（1.7）与 guard 测试隔离两项经实证确实落地**：主规格与归档 delta 逐字节一致、`specs/` 已回填、事件日志 seq 连续；guard 修复经"改坏→变红→还原"变异验证确认真实有效。benchmark task 的 base 红 / gold 绿闭环也独立复现成立。
- 但 **R1 修复引入了一条高危数据丢失缺陷**（Issue 1）：`EnterWorktree` 在"同名 worktree 已存在"时会把**已有的 worktree 及其内容删除**，且返回文案完全不提；最典型的触发路径正是设计内的正常用法（`keep=true` 保留 worktree 后重入）。这是本次审阅最重要的发现，必须修复并补回归测试（Issue 4）后才能放行。
- Issue 2（文案与事实相反）、Issue 3（`base_branch` 未校验）建议同批修掉；Issue 5、6 为口径与流程项，不阻断。
- 测试侧：24 例 worktree 用例、26 例 guard 用例全绿；全量 3050 passed，仅 2 条与本次无关的 `/tmp` 环境已知失败。**测试全绿不等于无缺陷**——现有用例恰好绕开了 Issue 1 的路径。
- 不判 BLOCKED：核心功能（创建/进入/退出/边界重绑定/越权拒绝）真实可用且测试充分，缺陷是失败分支上的破坏性副作用，属可定点修复的中等及以上问题。

## Open Questions

1. **Issue 1 的修法取向**：倾向"add 失败时完全不做 remove、回到 base 语义（git 对 `-b` 冲突无残留注册）"，还是"加前置探测、确实残留才清理"？前者更简单安全，但要确认 D2 里"非 branch 冲突可能残留注册"的场景是否真实存在（建议先构造一个来验证，否则可整段删掉）。
2. **`base_branch` 是否保留**：该参数在真实使用中价值有限（缺省即当前分支），却带来参数注入面。是否考虑直接下线，只保留 `name`？
3. **3.7 文档口径**：`docs/architecture.md` 内置工具表是否补 EnterWorktree/ExitWorktree 两行？任务带"如有新能力线"限定词，两种口径都说得通，请拍板后按同一口径回写 tasks.md。
4. **benchmark gold.patch 是否随修复重生成**：若 Issue 1 修复改动 `worktree.py`，`gold.patch`（= R1 diff）里的同一段破坏性 remove 需要同步，否则 benchmark 交付物会固化缺陷。
