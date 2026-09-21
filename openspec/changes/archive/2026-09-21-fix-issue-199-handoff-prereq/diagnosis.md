# Diagnosis — fix-issue-199-handoff-prereq

关联跟踪 issue：[#199](https://github.com/Xingkai98/asterwynd/issues/199)（【debt】workflow_state.py 的 artifact-event / review-manifest 因强制要求 handoff.json 而实际不可用）。

## Symptom

`scripts/workflow_state.py` 的 `artifact-event` 与 `review-manifest` 两个子命令，对**任何当代 change**（无 `handoff.json`）都直接报错退出：

```text
$ uv run python scripts/workflow_state.py artifact-event \
    --change fix-issue-199-handoff-prereq \
    --event-type protected_artifact_explained \
    --artifact-path docs/known-debt.md \
    --reason "..." --approved-by human
错误：change 'fix-issue-199-handoff-prereq' 没有 handoff.json   # exit 1
```

`review-manifest` 同样报 `错误：change '<id>' 没有 handoff.json`（exit 1）。

后果：受保护路径的结构化解释事件（`current_spec_synced` / `backlog_updated` / `change_archived` / `protected_artifact_explained`）与 review manifest 的写入，只能绕过 CLI 直接调底层 Python 函数（`agent.workflow.event_log.append_protected_artifact_event`、`agent.workflow.review_manifest.write_review_manifest`），与 `workflow_guard.py`「只放行 `workflow_state.py` CLI 调用」的白名单形成事实死锁——guard 只允许走 CLI，CLI 却因前置条件不可用。

## Reproduction

1. 取任意当代 change 目录（如 `openspec/changes/add-worktree-tool/`，其 `workflow-events.jsonl` 首事件为 `backlog_updated`，**无** `handoff.json`）。
2. 执行：

```bash
uv run python scripts/workflow_state.py artifact-event \
  --change add-worktree-tool \
  --event-type backlog_updated \
  --artifact-path docs/openspec-change-backlog.md \
  --reason "复现" --approved-by human
uv run python scripts/workflow_state.py review-manifest \
  --change add-worktree-tool --phase building \
  --reviewer-run-id repro --verdict PASS
```

3. 两条均输出 `错误：change 'add-worktree-tool' 没有 handoff.json` 并返回 1。

实测：`find openspec/changes -maxdepth 2 -name handoff.json` 在 active 目录下命中 **0 个**（只有 5 个早期归档 change 目录残留 `handoff.json`）。即新 change 无一例外会命中该前置。

## Evidence

- `scripts/workflow_state.py:939`（`cmd_artifact_event`）：
  ```python
  if not (change_dir / "handoff.json").exists():
      print(f"错误：change '{args.change}' 没有 handoff.json", file=sys.stderr)
      return 1
  ```
- `scripts/workflow_state.py:968`（`cmd_review_manifest` 分支）：同一前置检查。
- 其余 `handoff.json` 引用（issue 点名的 `:542` / `:881` / `:999`）：
  - `:542`（`cmd_current`）与 `:999`（`cmd_validate`）走 `_load_handoff`，读的是 handoff 状态本身——停用状态机后无产出，是**同源遗留**，但不在受保护写路径上（见 Recommended Direction 对是否一并清理的判断）。
  - `:881`（`cmd_spawn`）是 wayfinding 时代的子 change 派生命令，同样依赖 `handoff.json` 状态，属遗留但非本 issue 的核心不可用面。
- `scripts/flow-policy.json`：`workflow-events.jsonl`（`cli_written`）与 `-review-manifest.json`（`manifest_verified`）为受保护路径，只准 CLI 通道写。
- `scripts/workflow_guard.py:246-269`：guard 白名单只豁免**独立**的 `workflow_state.py <subcommand>` 调用。
- **顺序依赖的掩蔽（立项期实测发现）**：冷状态（无 `handoff.json`）下 `artifact-event` 报错 exit 1；但只要先跑一次 `flow status --change <id>`，其**自愈重建**分支（`workflow_state.py:828` → `_refresh_workflow_state` `:859-873`）会**同时写** `workflow-state.json` 和映射用的 `handoff.json`，使 `artifact-event` 立刻变可用（实测 exit 0）。由于 `handoff.json` 不被任何 change 提交（`git ls-files` 在 active 与归档 change 下均无该文件），新建 worktree / clone 冷启动必然命中——这解释了该坑长期存在却不易复现。
- 对照事实：`_all_change_ids`（`workflow_state.py:194-211`）已在「代码层修正 6」中做过同源修正——从「只列有 handoff.json 的目录」改为「handoff.json **或** workflow-state.json **或** workflow-events.jsonl」，即代码库已在其它位置承认「当代 change 无 handoff.json」。本次是把这个已知事实补到 `artifact-event` / `review-manifest` 两处漏网的前置检查。

## Root Cause

停用四阶段状态机（AGENTS.md「旧的四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）已停用」）时，移除了 `handoff.json` 的生成，但 `cmd_artifact_event` / `cmd_review_manifest` 里这条由状态机时代引入的 `_require_handoff` 式前置校验没有随状态机一起清理。两条命令的**真实前置**（change 目录存在、是合法 change）与它们**实际检查的**（旧状态机的 handoff 产物）脱节。

## Recommended Direction

- 移除 `artifact-event` / `review-manifest` 对 `handoff.json` 的硬前置，改为**当代合法性判定**：change 目录存在 + `proposal.md` 存在（当前 `_flow_require_change` 已建立的「事件日志存在」口径可作为并列条件，具体锚点在 design.md 决策中定）。
- 复用现成的世代判定函数 `_flow_is_gen1(change_dir)`（`workflow_state.py:773`）：当代 change 事件日志首事件为 `change_created`（或异构派生），`_flow_is_gen1` 返回 False；`project_workflow_state`（`agent/workflow/event_log.py:370`）已能对两代 change 统一投影，故「gen-2 即合法」的判定与既有投影语义一致，不引入新机制。
- 兼容性：老世代归档 change（首事件 `initialized` + 有 `handoff.json`）行为不变。
- 补回归测试：无 `handoff.json` 的新 change 能正常走 `artifact-event` 与 `review-manifest`；有 `handoff.json` 的老世代仍可写。
- 其余 `handoff.json` 引用（`:542` / `:881` / `:999`）是否同批清理，作为本 change 的显式设计决策（design.md D 系列）处理，避免范围蔓延或半清理。

## Regression Tests

- 新增测试文件（如 `tests/test_workflow_state_cli.py` 内新增分支或独立文件）：
  - 无 `handoff.json` + 有 `proposal.md` + `change_created` 首事件 → `artifact-event` 成功写入事件日志（exit 0）。
  - 同条件 → `review-manifest` 成功写入 manifest（exit 0）。
  - 老世代 change（`initialized` + `handoff.json`）→ 两命令仍成功（兼容性不回归）。
  - 不存在的 change / 缺 `proposal.md` → 仍以明确错误 exit 1（不退化为「任意路径都能写」）。
- 覆盖层级：CLI 层（`tests/test_workflow_state_cli.py`）+ 端到端验收（新建一个无 `handoff.json` 的 change，两命令均成功且通过 `scripts/check_openspec_artifacts.py`）。
