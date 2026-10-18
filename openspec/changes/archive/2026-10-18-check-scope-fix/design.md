# Design: 收窄「闭环出口」检查到本 PR 新归档（默认 base 解析修复）

## Context

`scripts/check_openspec_artifacts.py` 的归档点门（issue #235）用两条过滤挑出「本 PR 新归档」：

1. `git diff --name-only --diff-filter=AR <base> --`；
2. 该归档子目录在 `<base>:openspec/changes/archive` 树中不存在。

两条过滤本身正确，`retire-manifest-check` 的 design 也明确写「verdict 检查只在新归档目录
执行，历史归档不追溯」。但 `--base-ref` 的 argparse 缺省值是字符串 `master`。本地 worktree
的 `master` 分支可以长期落后 `origin/master`（本工作区实测落后 103 个提交），此时：

- 本 PR 实际 base 是 `origin/master = b0469cb`；
- 裸跑 diff 的是 `master = 3c7196b`；
- 8 个归档目录出现在 AR diff 中（`master` 的 archive 树里都不存在），其中 5 个
  （`2026-10-13-web-agent-group-chat`、`2026-10-13-witnessloop-adoption`、
  `2026-10-14-guard-write-allowlist`、`2026-10-17-review-loop-no-round-cap`、
  `2026-10-17-stage-c-required-switch`）缺 `## 闭环出口` → 被当成「本 PR 新归档」→
  完成面要求 PASS → 5 条历史报告误红。

此外，分支落后于 `origin/master` 且未 merge 时，两点 diff 会把上游已合入的受保护路径改动
反向列为本分支改动，产生「本分支没碰受保护路径却被要求解释」的误红。修法必须让裸跑的 base
代表**本 PR**（merge-base 三点语义），而不是碰巧存在的本地分支或上游最新提交。

## Goals / Non-Goals

**Goals**

- 干净 HEAD 裸跑 artifact checker 为 0 错；新建归档缺 `## 闭环出口` 仍必须红。
- 分支落后时，上游受保护路径改动不被反向列为本分支改动。
- 保留 `--base-ref` 的显式两点语义，CI 与既有调用方零改动。

**Non-Goals**

- 不放宽归档点门的任何过滤条件或出口判据。
- 不改 `--check-archived` / `--change` / `--skip-*` 语义。
- 不追溯修历史归档报告。
- 不处理 TUI proposal 退役（另立 PR）。

## Decisions

### Decision 1：默认 base 解析用 `origin/master` 与 `HEAD` 的 merge-base

**选择**：`--base-ref` 的 argparse 默认值改为 `None`。新增 helper：

```text
_resolve_base_ref(repo_root, explicit):
    if explicit is not None and explicit.strip(): return explicit  # 空/纯空白视为未提供
    for candidate in ("origin/master", "master"):
        if git rev-parse --verify --quiet candidate (cwd=repo_root) fails: continue
        mb = git merge-base HEAD candidate (cwd=repo_root)
        base = mb if mb succeeds else candidate    # shallow 等场景退回两点 diff
        print("INFO: using implicit base ref '<candidate>' -> <base>", file=sys.stderr)
        return base
    return "master"   # 交给下游的 fail-closed / warning 逻辑
```

`main()` 解析一次，把结果同时传给 `_check_new_archived_completion_gates` 与
`_changed_paths_since_base`。只在至少一个 diff 消费者启用时解析，避免
`--check-archived --skip-protected-paths` 的 CI 调用打出无意义 INFO。`--require-base`
语义不变。

**理由**：

- 本仓的 PR 都从 `origin/master` 分支；`origin/master` 是「本 PR base」的本地可用代理。
- 三点语义让分支落后时 diff 只含本分支自共同祖先以来的提交，历史归档回到 base 树里，
  上游受保护路径改动也不会被反向列出。
- CI 显式传 `github.event.pull_request.base.sha`，不经过默认解析，零影响。
- 显式 `--base-ref master` 仍可复现旧行为。

**被拒备选**：

| 备选 | 拒绝原因 |
|------|---------|
| 只在 `_new_archive_dirs_since_base` 里排除「日期早于某阈值」的归档 | 魔数阈值会误杀真正的新归档；历史性不能由日期推断 |
| 无参数时直接跳过归档点门 | 会让裸跑不再检查新建归档，违反 issue #319 的验收要求，且是放宽判据 |
| 直接返回 `origin/master` 做两点 diff | 分支落后时反向 diff 会把上游受保护路径改动列为本分支改动，产生新的误红 |
| 用 `git merge-base HEAD master` 作为默认 base | 本地 `master` 陈旧时 merge-base 仍在旧点，历史归档照样被误判 |
| 要求用户必须显式传 `--base-ref`，否则报错 | 破坏「裸跑可用」的本地体验；标准命令已经存在，不需要把裸跑变成错误 |

决策备选记录于 `docs/adr/ADR-0007-default-base-resolution-for-archive-gate.md`。

### Decision 2：保持归档点门的两条过滤与出口判据逐行不变

**选择**：只改 base 的**来源**，不改「怎么判定新归档」与「出口怎么判」。

- `_new_archive_dirs_since_base` 的 `--diff-filter=AR`、`ARCHIVE_PATH_RE`、base 树不存在
  过滤保持不变；
- `_review_exit_verdict` / `_review_exit_errors` / `_check_archived_completion_gate`
  保持不变；
- 新建归档缺 `## 闭环出口` 仍由完成面报错。

**理由**：issue #319 明确「不放宽任何其它判据」。缺陷在 base 选错，不是门本身太宽或太窄。

### Decision 3：TDD 七条测试；helper / 回归 / 接线 / 空 base 先红，其余为守卫

**选择**：在 `tests/test_openspec_artifact_checker.py` 新增：

1. `test_resolve_base_ref_prefers_origin_master_and_honors_explicit`（单元）：helper 不
   存在时先红；显式值（含空字符串）原样返回；无显式值时返回
   `git merge-base HEAD origin/master`；无 `origin/master` 时返回与 `master` 的
   merge-base；都不可解析时回退 `master`。
2. `test_bare_check_does_not_trace_historical_archives`（回归本体，修复前红）：
   `git branch -M master` 钉初始分支 → 提交 A → `git checkout -b pr-branch` → 提交 B
   （历史归档，缺出口）→ `git update-ref refs/remotes/origin/master <B>`；前置断言
   `master != origin/master`、`rev-list --count master..origin/master >= 1`、
   `_new_archive_dirs_since_base(repo,"master")` 含归档、`origin/master` 为空、
   `HEAD == origin/master`；裸跑（skip protected/backlog）→ exit 0。
3. `test_bare_check_still_flags_new_archive_missing_exit`（防退化守卫）：同仓库在
   `origin/master` 之后新建非 docs + 有 spec delta、缺出口的归档；裸跑仍报「闭环出口」；
   断言错误含目录名与「闭环出口」。检查结果修复前后都红，测试本身修复前即绿。
4. `test_explicit_base_ref_still_wins`（显式优先级守卫）：显式 `--base-ref master` 时
   历史归档仍被当成新归档；显式 `origin/master` 时 exit 0。
5. `test_resolve_base_ref_is_used_for_protected_path_diff`（修复前红）：monkeypatch
   `_changed_paths_since_base` 捕获 `base_ref`，断言无显式参数时收到 merge-base sha、
   显式 `master` 时收到 `master`。
6. `test_behind_branch_does_not_false_red_protected_paths`（三点语义守卫）：HEAD 停在
   共同祖先 A，`origin/master` 前进到 Y 并修改受保护路径；裸跑（只 skip backlog）→
   exit 0。两点实现下红，修复前即绿。
7. `test_empty_base_ref_does_not_skip_checks`（空值红线，修复前红）：新归档缺出口时传
   `--base-ref ""` → 仍 exit 1 且报「闭环出口」；空/纯空白不得变成「跳过两个 diff
   检查」的快捷方式。

main 级测试 2–4 和 7 显式传 `--skip-protected-paths --skip-backlog`（tmp 仓库没有为本 PR
受保护路径准备解释事件）；测试 5 只 monkeypatch 受保护路径函数；测试 6 需要真实 diff。

**口径**：1、2、5、7 修复前红；3、4、6 是守卫（6 在两点实现下红）。不得为守卫编造先红证据。

### Decision 4：规格只 MODIFIED 一条 Requirement

**选择**：`specs/dev-workflow-state-machine/spec.md` delta MODIFIED
`### Requirement: 开发流程精简为 OpenSpec 主干 + 强制审阅闭环`，补充默认 base 解析段与
两个 Scenario（裸跑不追溯历史归档 / 显式 base 不被默认解析覆盖）。

**理由**：这是同一 Requirement 的语义补强，不新增能力域。

### Decision 5：收尾次序与证据

**选择**：内容提交 → 写出 `change_archived` 事件 → 移除 backlog 条目 → 归档 move（独立
提交）→ 本地复验（裸跑 + 显式 base）→ 结算 `tasks.md` → 用归档目录名重建三份 witnessloop
manifest → `check` 复验 → PR → `--merge`。注意：tasks 结算（含 4.7/4.8）之前的首次裸跑
可能因未勾任务而红，这是预期；最终以结算后的复验为准。`docs/known-debt.md` 的 `protected_artifact_explained`
事件与 `current_spec_synced` 事件在内容提交阶段写入。
witnessloop 用 `/home/happy/wl170/bin/witnessloop`（v1.7.0，支持归档目录名）；其源码克隆
当前停留在不支持归档态的 v1，仅作为开发参考，不作为最终复验命令。

## Pre-Implementation Review

**独立 grill（零记忆）**：`reviews/grill-design.md`，run
`1dcf6023-d516-4995-9c83-7332375687da`，6 条 Confirmed Decisions、0 个 Open Question。
必须修改项 M1（缺 `change_archived` 任务）、M2（测试 `-k` 漏选）、M3（known-debt 事件）、
M4（变异证据）与 S1–S3 已全部整合。

**设计阶段对抗闭环**：`reviews/grill-adversarial.md`，run
`ef2d1462-81ef-4636-a8b0-ac70ad817680`。第 1 轮开批 A1（current spec 未同步）、
A2（空 `--base-ref` 静默跳过检查）2 条 medium，全部修复；第 1 轮修复验证 A1/A2 PASS，
当前未收敛 medium+ = 0，出口 **PASS**。停轮检查：`## Open Questions` 为「无」，
`## User Confirmation` 写明「无待用户拍板项」→ 无需停轮，可进入实现。

## Risks / Trade-offs

- **`origin/master` 自身陈旧**：未 fetch 时仍可能误判，属 fail-loud；文档补充
  「裸跑前 fetch」；显式 `--base-ref` 仍是逃生口。
- **`origin` 指向 fork/镜像**：diff 可能变大并误红；显式参数可覆盖。
- **没有 `origin/master` 的仓库**：回退与 `master` 的 merge-base，再回退 `master`，与今日
  行为一致；不会更差。
- **测试必须显式创建 refs**：现有 `_init_git_repo` 不创建 `origin/master`；测试必须
  `git branch -M master`、`git update-ref refs/remotes/origin/master <sha>`，并断言五项
  前置状态，否则「无 master 可解析 → 只打 WARNING、exit 0」会让回归假绿。
- **默认 base 改变影响受保护路径 diff**：本地 `master` 领先 `origin/master` 时 diff 只会
  更大（更严格）；分支落后时三点语义消除反向噪音。

## Testing Strategy

- **单元/回归**（TDD）：helper 单元、默认 base 不追溯、新建归档仍红、显式优先、受保护
  路径接线、落后分支不误红、空 `--base-ref` 不跳过检查。
- **既有测试**：`uv run pytest -q tests/test_openspec_artifact_checker.py tests/test_retire_manifest_check.py`。
- **端到端验收**：
  - 干净 HEAD 裸跑 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → EXIT=0；
  - `--base-ref origin/master --require-base` → EXIT=0；
  - `--check-archived` → EXIT=0；
  - 新建归档缺出口的守卫用例 → 红；
  - OpenSpec strict validate → 删除前 30 / 本 change 活跃时 30（28 specs + 2 changes）→
    归档前 29（28 + 1）；以实跑输出为准；
  - 全量 `uv run pytest -q` 与基线同类同因。
- **witnessloop**：`/home/happy/wl170/bin/witnessloop check --root <repo> --base origin/master --head HEAD`。
