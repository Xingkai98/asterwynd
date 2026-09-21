# Proposal: 受保护写通道支持已归档 change（fix-issue-232-archive-write）

关联跟踪 issue：[#232](https://github.com/Xingkai98/asterwynd/issues/232)（【debt】归档 change 的 review manifest 存在写入与校验双盲区）。本 change 只做盲区 A（写入侧）。

## Change Type

- primary: bugfix
- secondary:
  - process

## Why

`workflow_state.py` 的 `artifact-event` / `review-manifest` 是写受保护路径的唯一合法 CLI 通道（#199 修复后对当代 change 已可用）。但两条命令的**目标解析只看 active 目录**（`_require_change_target`，`scripts/workflow_state.py:853`），无 archive 回退——change 一旦归档，这两条 CLI 就报「不存在」。

这不是理论问题：#199 归档收尾时**真实踩到**——manifest 必须绑定归档后的最终 head（含归档 move 自身），而 CLI 不可用，只能绕底层 `write_review_manifest(..., archived=True)`。对照 `_flow_resolve_change_dir`（`:794`）本就有 archive 回退，两个解析入口口径不一致。

更关键的是**下游两处会因归档目标而写错或产生污染**（立项实测复现，见 `diagnosis.md` Evidence）：

1. `cmd_review_manifest` 调 `write_review_manifest` **不传 `archived=`**，即便前置放行也会写到 active 路径（不存在的目录会被新建）。
2. 写入后调 `_flow_refresh_after_event(change_dir)`，对归档目录会**写出 `handoff.json` + `workflow-state.json` 到已提交的归档目录里**（实测复现并清理）——即 #228 记录的污染问题落在归档目录，比 active 目录更严重。

## 需求

1. `_require_change_target` 增加 archive 回退，口径与 `_flow_resolve_change_dir` 一致（active 优先，归档只读可查）。
2. 把「目标已归档」显式传给下游：`write_review_manifest(..., archived=True)`，使 manifest 落在 `archive/<date>-<id>/reviews/`。
3. **归档目标不刷新投影**——`_flow_refresh_after_event` 对归档目录跳过，避免在已提交的归档目录产生未跟踪产物。
4. 保留 #199 全部既有行为：路径型 id 拒绝、非法目标拒绝、老世代兼容、active 写入后刷新投影。

## 背景

门禁的机械证据（review manifest、受保护路径解释事件）在**归档收尾那一刻**才最终成形——而归档动作本身把 change 移出了 active 目录。若写通道不支持归档目标，收尾就只能绕底层函数，与 #199 修好的「单一路径」目标相悖。本 change 补齐这个收尾接缝。

## 非目标

- **不做盲区 B（CI 校验侧）**：`.github/workflows/ci.yml:62` 的 checker 不带 `--check-archived`，归档 change 脱离 manifest 校验。实测 `--check-archived` 当前有 **15 条 `tasks hash mismatch`**（43 个有 manifest 的归档 change 中），开启前必须先决定「重绑 15 个 vs 让 hash 容忍归档期勾选变化」——属独立决策，另案（仍记在 #232）。
- 不改 `_flow_resolve_change_dir` / `flow status` 的既有归档只读语义。
- 不改 `review_manifest.py` 的 `change_dir_for` / `write_review_manifest`（其 `archived=` 能力已存在，只是调用方没传）。
- 不改 .gitignore（#228 范围）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程 CLI | `scripts/workflow_state.py` 的 `_require_change_target` 增 archive 回退；`cmd_artifact_event` / `cmd_review_manifest` 据解析结果传 `archived=` 并决定是否刷新投影 |
| 受保护 artifact 证据 | 归档 change 的 manifest / 解释事件可经 CLI 写入，收尾接缝闭合 |
| 归档目录完整性 | 归档目标**不再**被投影刷新污染（新增判别性测试锁定） |
| Guard / 门禁 | 不改 `flow-policy.json` 与 `workflow_guard.py` |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md`（MODIFIED「工作流事件日志与 handoff.json projection」的写通道段落 + 「受保护写通道拒绝非法目标」Scenario 的归档语境 + 新增归档写通道 Scenario） |
| Tests | 新增归档写通道回归测试（含污染判别用例）；#199 的 10 条测试保持全绿 |
| Docs | `docs/known-debt.md` 若引用 #232 需按本 change 收口一半的范围更新说明 |
| Migration / compatibility | active change 行为不变；#199 行为不变 |
| 明确不受影响 | AgentLoop、ToolRegistry、Web UI、benchmark、MCP、记忆系统 |

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 bugfix（无新增能力面，是 #199 写通道收口的补全：把已有 archive 回退口径 `_flow_resolve_change_dir` 复用到目标解析，并修正下游两处未传 `archived=` / 未跳过刷新的缺陷）。上游决策已锁定：issue #232 已记录双盲区与实测证据，同根的 #199（PR #233）已确立「受保护写通道以 change 合法性为前置」的契约与实现范式（`_require_change_target`）；`review_manifest.py` 的 `archived=` 能力已存在。无待定设计项。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在），改用上述仓库内证据作为依据。

## 测试计划

- CLI 层：归档 change 的 `artifact-event` / `review-manifest` exit 0 且落在 archive 路径；归档目录不出现 `handoff.json` / `workflow-state.json`（污染判别）。
- active change 不回归（跑 #199 的 `tests/test_workflow_protected_write_channel.py` + `tests/test_workflow_state_cli.py`）。
- 非法目标（不存在 / 路径型 id）仍拒绝。
- 变异验证：去掉 archive 回退 → 归档用例红；去掉「归档跳过刷新」→ 污染用例红；不传 `archived=` → manifest 落错路径用例红。
- 全量 `uv run pytest -q` + OpenSpec strict validate。
