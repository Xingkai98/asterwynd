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

change #199 归档收尾时**真实踩到**：manifest 必须绑定归档后的最终 head（含归档 move 自身），而 CLI 只认 active 目录——只能绕底层函数。

## Evidence

- `scripts/workflow_state.py:853-884` `_require_change_target` 用 `change_dir = CHANGES_ROOT / change_id` 定位，**只看 active 目录**，无 archive 回退。
- 对照：`_flow_resolve_change_dir`（`:794-803`）**有**回退——「active 目录优先；归档目录（`openspec/changes/archive/<date>-<id>`）只读可查」。两个解析入口口径不一致。
- 下游两处会因归档目标而**行为错误或产生污染**（本 change 立项时实测复现）：
  1. `cmd_review_manifest` 调 `write_review_manifest(repo_root, change_id, phase, ...)` **不传 `archived=`**，默认 `archived=False` → `change_dir_for` 返回 active 路径 → 即便前置放行也会**写到错误位置**（active 路径不存在则新建出幽灵目录）。
  2. 成功写入后调 `_flow_refresh_after_event(change_dir)`。实测：对归档的 #199 change 调用它，`_flow_is_gen1` 返回 **False**（该 change 首事件是 `backlog_updated`，既非 `initialized` 也非 `change_created`），于是走 gen-2 分支 `_refresh_workflow_state`，**在归档目录里写出 `handoff.json` + `workflow-state.json`**（实测复现，已清理）。这正是 #228 记录的「自愈产物污染」问题，但落在**已提交的归档目录**里，比 active 目录更严重。

## Root Cause

#199 只收口了「受保护写通道的前置条件」，**没有收口「目标解析」**：`_require_change_target` 是新写的函数，只按 active 目录实现，没复用 `_flow_resolve_change_dir` 的 archive 回退，也没把「目标已归档」这一事实传给下游（`write_review_manifest` 的 `archived=` 参数、投影刷新）。

## Recommended Direction

1. `_require_change_target` 增加 archive 回退（复用 `_flow_resolve_change_dir` 的口径，返回解析后的真实目录）。
2. **把「是否归档」显式传递给下游**：调用方据解析结果判断，`write_review_manifest(..., archived=True)`；否则会写错位置。
3. **归档目标不刷新投影**：`_flow_refresh_after_event` 对归档目录必须跳过——否则在已提交的归档目录里产生未跟踪产物（实测污染，见 Evidence 2）。归档 change 的投影按 `flow status` 的既有口径是「只读不落盘」。
4. 保留 #199 的全部既有行为：路径型 id 拒绝、非法目标拒绝、老世代兼容、写后刷新（仅 active）。

## Regression Tests

- 归档 change + 合法 manifest 参数 → `review-manifest` exit 0，且 manifest 落在 **archive** 路径（`archive/<date>-<id>/reviews/`），**不**在 active 路径新建目录。
- 归档 change → `artifact-event` exit 0，事件追加到 **archive** 的事件日志。
- **归档目标写入后，归档目录中不出现 `handoff.json` / `workflow-state.json`**（判别性：锁住 Evidence 2 的污染，移除「归档跳过刷新」后必红）。
- active change 行为不回归（#199 的 10 条测试保持全绿）。
- 路径型 id / 非法目标仍拒绝（含归档语境）。
