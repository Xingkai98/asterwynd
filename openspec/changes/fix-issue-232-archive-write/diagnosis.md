# Diagnosis — fix-issue-232-archive-write

关联跟踪 issue：[#232](https://github.com/Xingkai98/asterwynd/issues/232)（【debt】归档 change 的 review manifest 存在写入与校验双盲区）。本 change 只做**盲区 A（写入侧）**；盲区 B（CI 校验侧）见「非目标」。

## Symptom

change 归档后，若再需要（重）生成 review manifest，`workflow_state.py review-manifest` 无法使用：

```text
$ uv run python scripts/workflow_state.py review-manifest \
    --change fix-issue-199-handoff-prereq --phase building \
    --reviewer-run-id <id> --verdict PASS
错误：change 'fix-issue-199-handoff-prereq' 不存在   # exit 1
```

即使该 change 就在 `openspec/changes/archive/2026-09-21-fix-issue-199-handoff-prereq/`。只能绕底层 `write_review_manifest(..., archived=True)`。

## Reproduction

1. 取任一已归档 change（如 `openspec/changes/archive/2026-09-21-fix-issue-199-handoff-prereq/`，它确实存在）。
2. 跑上述 CLI：报「不存在」exit 1。
3. 对照：同一 CLI 对 **active** change 正常。
4. 解析能力对照（同一 id）：`_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`（死代码分支）；`change_dir_for('.', 'fix-issue-199-handoff-prereq', archived=True)` → `openspec/changes/archive/2026-09-21-fix-issue-199-handoff-prereq`（正确）。
5. 不传 `archived=` 的实际失败模式：`write_review_manifest` 抛 `FileNotFoundError: review report missing: <active 路径>/reviews/building-review.md` → exit 1，且 `<active 路径>` **未被创建**（`mkdir` 在 build 之后）。
6. `--check-archived` 基线：exit 1，正好 **15** 条 `tasks hash mismatch`（与 proposal 非目标记载一致）。

change #199 归档收尾时**真实踩到**：manifest 必须绑定归档后的最终 head（含归档 move 自身），而 CLI 只认 active 目录——只能绕底层函数。

## Evidence

- `scripts/workflow_state.py:853-884` `_require_change_target` 用 `change_dir = CHANGES_ROOT / change_id` 定位，**只看 active 目录**，无 archive 回退。
- 归档解析能力**已存在但没被接上**：`agent/workflow/review_manifest.py:23` 的 `change_dir_for(archived=True)` 实测能正确解析 `archive/<date>-<id>/`（见 Reproduction 步骤 4）。受保护写通道的调用方没用它。
- **易误导点**：`scripts/workflow_state.py:795` 的 `_flow_resolve_change_dir` **看似**有 archive 回退，实际拼的是 `CHANGES_ROOT/"archive"/change_id`（**裸 id 目录**），而仓库 89 个归档目录**全部**带 `YYYY-MM-DD-` 前缀 → 该分支是**死代码**。实测 `_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`；`flow status --change fix-issue-199-handoff-prereq` → exit 1「不存在」。故它**不是**可复用的口径（design D1 据此改写为「委托 `change_dir_for`」）。
- 下游两处会因归档目标而**行为错误或产生污染**（本 change 立项时实测复现）：
  1. `cmd_review_manifest` 调 `write_review_manifest(repo_root, change_id, phase, ...)` **不传 `archived=`**，默认 `archived=False` → `change_dir_for` 返回 active 路径 → `build_review_manifest` 先抛 `FileNotFoundError: review report missing: openspec/changes/<id>/reviews/building-review.md` → CLI exit 1。因 `mkdir`（`review_manifest.py:130`）在 `build_review_manifest` **之后**，active 目录**不会**被新建。真实危害是**错误信息指向一个不存在的 active 路径、误导排查**，而非静默污染（实测否证了「幽灵目录」说法，见 Evidence）。
  2. 成功写入后调 `_flow_refresh_after_event(change_dir)`。实测：对归档的 #199 change 调用它，`_flow_is_gen1` 返回 **False**（该 change 首事件是 `backlog_updated`，既非 `initialized` 也非 `change_created`），于是走 gen-2 分支 `_refresh_workflow_state`，**在归档目录里写出 `handoff.json` + `workflow-state.json`**（实测复现，已清理）。这正是 #228 记录的「自愈产物污染」问题，但落在**已提交的归档目录**里，比 active 目录更严重。

## Root Cause

#199 只收口了「受保护写通道的前置条件」，**没有收口「目标解析」**：`_require_change_target` 是新写的函数，只按 active 目录实现，既没接上**已有且实测可用**的 `change_dir_for(archived=True)`，也没把「目标已归档」这一事实传给下游（`write_review_manifest` 的 `archived=` 参数、投影刷新）。附带一个易误导点：`_flow_resolve_change_dir` 那段 archive 回退拼裸 id、对全部带日期前缀的归档目录失效（死代码），照抄它会「改完仍红」。

## Recommended Direction

1. `_require_change_target` 增加 archive 回退：active 优先，否则**委托 `review_manifest.change_dir_for(..., archived=True)`**（不新写第二套扫描——事件落点与 manifest 落点必须由同一算法决定）。委托的 `repo_root` 必须由 `CHANGES_ROOT.parent.parent` 推导，**不能**用 `_PROJECT_ROOT`（后者是真实仓库绝对路径，会让 tmp 冷状态测试逃逸到真实仓库而恒红）。
2. **把「是否归档」显式传递给下游**：调用方据解析结果（`Path` 是否位于 `CHANGES_ROOT/"archive"` 之下）判断，`write_review_manifest(..., archived=True)`；否则 `build_review_manifest` 会抛 `FileNotFoundError: review report missing: <active 路径>`（exit 1、目录不新建，但报错指向不存在的 active 路径、误导排查）。
3. **归档目标不刷新投影**：`_flow_refresh_after_event` 对归档目录必须跳过——否则在已提交的归档目录里产生未跟踪产物（实测污染，见 Evidence 2）。归档 change 的投影按既有口径是「只读不落盘」。作为补偿，写入后做一次**只读** `verify_projection`，仅在不一致时 stderr 告警（exit 仍 0、绝不落盘）——因为若归档目录磁盘上已有已提交的 `workflow-state.json`（仓库实测 1/89：`2026-08-15-flow-event-projection`），跳过刷新会让投影**永久 stale**，而当前无人校验归档投影会把它彻底掩盖。
4. **收紧归档目标契约**：解析结果目录名必须 `== <id>` 或 `fullmatch <date>-<id>`，否则 fail-closed exit 1（`change_dir_for` 的前缀正则缺 `$`，实测 `alpha` 会匹配到 `2026-09-22-alpha-beta`——**另一个 change**，且依赖 `iterdir()` 顺序）；带日期前缀的 `--change` id 显式拒绝（会让写入的 `change_id` 触发 CI `change_id mismatch`）。
5. 保留 #199 的全部既有行为：路径型 id 拒绝、非法目标拒绝、老世代兼容、写后刷新（仅 active）。

## Regression Tests

- 归档 change + 合法 manifest 参数 → `review-manifest` exit 0，且 manifest 落在 **archive** 路径（`archive/<date>-<id>/reviews/`），**不**在 active 路径新建目录。
- 归档 change → `artifact-event` exit 0，事件追加到 **archive** 的事件日志。
- **归档目标写入后，归档目录中不出现 `handoff.json` / `workflow-state.json`**（判别性：锁住 Evidence 2 的污染，移除「归档跳过刷新」后必红）。
- 归档目标契约：带日期前缀的 `--change` id → exit 1；解析结果与查询 id 不一致 → exit 1（判别性：移除一致性断言后前缀碰撞用例变红）。
- 只读投影校验：一致 → 无告警；已有投影的归档目录追加事件后不一致 → stderr 有告警且 exit 仍 0。
- active change 行为不回归（#199 的 10 条测试保持全绿）。
- 路径型 id / 非法目标仍拒绝（含归档语境）。
