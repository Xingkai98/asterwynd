# Building Review: add-worktree-tool（Round 9，最终确认）

**Verdict**: PASS

**审阅基线**: base_sha=1e16ee14e8103b06786eb5407a50be36dd466f57（origin/master） head_sha=db8e57bc8d17af8d3b7d19049b433f4ea2850a2e
**审阅时间**: 2026-09-24

> 本审阅者为零记忆独立 reviewer，未参与本 change 的任何实现或修复。本轮为最终确认轮，只回答三个问题：
> 三个关键变异是否都被测试抓住、HEAD 在数据丢失场景下是否安全、本 PR 能否放行。
>
> **结论：三项全部满足，可放行。**
> - 变异 B（helper 契约 `return None` → `return set()`）：**被抓**（R7 时存活）。
> - 变异 C（调用侧非对称 fail-open）：**被抓**（R8 时存活，且 R8 已实测确认为真实数据丢失路径）。
> - 变异 D（原始 R5 无条件 `worktree remove`）：**被抓**（4 条失败）。
> - 独立复现数据丢失场景：HEAD 下**未执行任何 remove**，内容/提交/注册/policy root 全部存活；同一脚本对变异 B、C 均判 UNSAFE（有判别力）。
> - 本轮增量 `3c11605..db8e57b` **只有测试文件**，生产代码零改动。

## 变异验证（核心）

在一次性临时 worktree `/tmp/r9-mut`（`git worktree add --detach /tmp/r9-mut db8e57b`）中进行。
基线先跑一遍确认健康：`27 passed in 2.32s`（exit 0）。每次变异后立即 `git checkout -- agent/tools/builtin/worktree.py` 还原。
被测命令：`uv run pytest tests/agent/tools/test_worktree_tools.py -q`。

### 变异 B（helper 契约）——已抓住 ✅

- **改了什么**：`agent/tools/builtin/worktree.py::_registered_worktree_paths` 中，`worktree list` 失败分支
  `return None` → `return set()`。
- **真实结果**：`2 failed, 25 passed in 1.98s`（exit 1）。R7 时该变异存活（25 passed 全绿）。
- **失败测试名**：
  - `test_registered_worktree_paths_none_when_list_fails`（helper 契约定点断言，`assert ... is None` 失败）
  - `test_enter_worktree_cleanup_fail_closed_on_asymmetric_list_failure`
    （`AssertionError: before 快照不可读时不得执行任何 worktree remove`，实测 remove 被调用）
- **是否还原**：是（还原后 `git status --porcelain` 为空）。

### 变异 C（调用侧非对称 fail-open，R8 指出的数据丢失路径）——已抓住 ✅

- **改了什么**：调用侧
  `residue = None if before is None or after is None else after - before`
  → `residue = (after or set()) - (before or set())`。
- **真实结果**：`1 failed, 26 passed in 1.92s`（exit 1）。R8 时该变异存活。
- **失败测试名**：`test_enter_worktree_cleanup_fail_closed_on_asymmetric_list_failure`
  （`assert removed == []` 失败，实测执行了
  `['worktree', 'remove', '<tmp>/.asterwynd/worktrees/keepme']`）。
- **是否还原**：是。

### 变异 D（原始 R5 破坏性 bug）——已抓住 ✅

- **改了什么**：失败分支的残留判定改为无条件执行清理——`if residue is not None and str(wt_path) in residue:`
  → `if True:`，其内执行 `_run_git(repo, "worktree", "remove", str(wt_path))`。
- **真实结果**：`4 failed, 23 passed in 1.98s`（exit 1）。
- **失败测试名**：
  - `test_enter_worktree_existing_worktree_not_deleted`
  - `test_enter_worktree_dirty_existing_worktree_not_deleted`
  - `test_enter_worktree_cleanup_fail_closed_when_list_unreadable`
  - `test_enter_worktree_cleanup_fail_closed_on_asymmetric_list_failure`
- **是否还原**：是。还原后重跑基线确认 `27 passed in 2.22s`（exit 0）。

### 变异小结

| 变异 | 改动位置 | R 轮状态 | R9 实测 | 失败数 | exit |
|---|---|---|---|---|---|
| B | helper `return None` → `set()` | R7 存活 | **抓住** | 2 failed / 25 passed | 1 |
| C | 调用侧 `residue` 非对称 fail-open | R8 存活 | **抓住** | 1 failed / 26 passed | 1 |
| D | 无条件 `worktree remove`（原始 R5 bug） | — | **抓住** | 4 failed / 23 passed | 1 |

三个变异逐一还原，临时 worktree 结束后 `git status --porcelain` 为空、`git diff --stat` 为空（与被审检出 db8e57b 无差异）。

## 数据丢失场景的 HEAD 复现

独立脚本复现（**不依赖被测测试文件**），在 `/tmp/r9-mut` 的 HEAD 代码上运行：

1. 临时 git 仓库 `enter("keepme")` 创建 worktree；
2. worktree 内写入 `precious.txt` **并 `git commit`**（已提交，确保若真发生 `worktree remove` 会真的丢内容，
   而非被 git 的未跟踪文件保护挡住——这正是本轮补强测试所修的同一点）；
3. `exit(keep=True)` 保留 worktree，回到主工作区；
4. 再次 `enter("keepme")`，并通过替换 `_run_git` **只让 before 快照那一次 `worktree list` 失败**。
   实测调用序列：`#1 OK`（`_in_worktree`/`_main_workspace`）、`#2 INJECTED FAIL rc=128`（**before 快照**）、`#3 OK`（after 快照）。

**HEAD 结果（SAFE, exit 0）**：

```
OK  remove 未执行
OK  已提交文件仍在            （precious.txt 内容 == "valuable\n"）
OK  commit 仍指向原 sha
OK  worktree 仍注册          （str(wt_path) in `git worktree list`）
OK  policy root 未变
error_type: worktree_create_failed
text: Error: worktree 创建失败：<wt_path> 已被占用（分支或目录已存在），未改动它；...
```

即：before 快照不可读 → `residue is None` → 不清理，走「已被占用」分支，用户的 worktree 与内容完好。

**判别力对照（同一脚本）**：将同样的注入分别施加到变异 B 与变异 C，脚本均输出 `RESULT: UNSAFE`：
实测打印 `[REMOVE EXECUTED]: ('worktree', 'remove', '<wt_path>.asterwynd/worktrees/keepme')`，
随后 `remove 未执行` / `已提交文件仍在` / `commit 仍指向原 sha` / `worktree 仍注册` 四项 FAIL，
worktree 目录已从磁盘消失（后续 `git rev-parse` 因目录不存在而 `FileNotFoundError`）。
这证明该场景是**真实的数据丢失路径**，且 HEAD 的通过不是「场景无效」导致。

## 生产代码未改动确认

```
$ git diff 3c11605 db8e57b -- agent/ benchmarks/ scripts/
（空）
$ git diff --name-only 3c11605 db8e57b
tests/agent/tools/test_worktree_tools.py
$ git diff --stat 3c11605 db8e57b
 tests/agent/tools/test_worktree_tools.py | 57 ++++++++++++++++++++++++++++++++
 1 file changed, 57 insertions(+)
```

本轮增量**仅测试文件**（+57 行，无删除），生产代码（`agent/`、`benchmarks/`、`scripts/`）零改动。
`git status --porcelain` 在被审检出仅显示本报告文件本身为已修改（预期的审阅产出）。

## 验证命令实跑结果

环境：`export PATH=/home/happy/.local/bin:$PATH`，`cd /home/happy/my-agent/.claude/worktrees/add-worktree-tool+2026-08-07`。

| 命令 | 真实输出摘要 | exit |
|---|---|---|
| `uv run pytest tests/agent/tools/test_worktree_tools.py tests/agent/tools/test_worktree_benchmark_smoke.py -q` | `30 passed in 2.34s` | 0 |
| `uv run pytest tests/test_workflow_guard.py -q` | `26 passed in 10.27s` | 0 |
| `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 28 passed, 0 failed (28 items)` | 0 |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref 1e16ee14e8103b06786eb5407a50be36dd466f57 --require-base` | `OpenSpec artifact checks passed` | 0 |

## 结论

**Verdict: PASS —— 本 PR 可放行。**

理由（全部满足判定规则）：

1. **三个关键变异都被抓住**：B（helper 契约）2 failed、C（调用侧非对称 fail-open）1 failed、
   D（原始 R5 破坏性 bug）4 failed；且每一条由变异 B/C 触发的失败都直接落在对应的定点回归测试上，
   不再是「改坏 helper 反而全绿」的状态。
2. **HEAD 在数据丢失场景下安全**：独立复现（只注入 before 快照失败、内容已提交）下 HEAD 未执行任何
   `worktree remove`，文件、提交 sha、注册与 policy root 全部存活；同一脚本对变异 B/C 判 UNSAFE，
   证明该场景真实且测试有判别力。
3. **生产代码未被改坏**：`3c11605..db8e57b` 仅 `tests/agent/tools/test_worktree_tools.py`（+57/-0），
   `agent/`、`benchmarks/`、`scripts/` diff 为空。
4. **测试与门禁通过**：worktree 相关 30 passed、workflow_guard 26 passed、OpenSpec strict validate
   28 passed / 0 failed、artifact checker passed，四项 exit 均为 0。

已知无害项（按本轮口径不计为缺陷）：

- 本机 `/tmp` 是 git 仓库导致的 `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 2 条本地失败
  （base 同样失败，CI 不复现），与本 change 无关。
- `building-review-manifest.json` 尚未随本报告重生成，`--check-archived` 会 hash mismatch——预期中间态，
  由主 agent 在本报告定稿后重生成 manifest 收口。

本轮**不再提出**任何新问题：剩余测试强度加固与文档口径均属渐进目标，不是交付阻塞项。
