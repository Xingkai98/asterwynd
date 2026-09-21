# Proposal: workflow_state.py 受保护写通道解除 handoff.json 前置（fix-issue-199）

关联跟踪 issue：[#199](https://github.com/Xingkai98/asterwynd/issues/199)（【debt】workflow_state.py 的 artifact-event / review-manifest 因强制要求 handoff.json 而实际不可用）。

## Change Type

- primary: bugfix
- secondary:
  - process

## Why

`scripts/workflow_state.py` 的 `artifact-event` 与 `review-manifest` 是 OpenSpec 流程写受保护路径事件与 review manifest 的**唯一合法 CLI 通道**（受保护路径规则见 `scripts/flow-policy.json`；`workflow-events.jsonl` 属 `cli_written`，`*-review-manifest.json` 属 `manifest_verified`）。

两条命令都**硬前置要求 `openspec/changes/<id>/handoff.json` 存在**（`scripts/workflow_state.py:939`、`:968`），而 `handoff.json` 是**已停用的四阶段状态机遗物**（AGENTS.md：「旧的四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）已停用」）。当前仓库 **0 个 active change** 拥有它（`find openspec/changes -maxdepth 2 -name handoff.json` 在 active 目录下命中 0 个；只有 5 个早期归档 change 残留）。

结果：对任何新 change，这两条 CLI 都直接报错退出；每个 change 的归档收尾事件与 review manifest 写入只能**绕过 CLI** 直接调底层函数，与 `workflow_guard.py` 的白名单（只放行 `workflow_state.py` 的 CLI 调用）形成事实死锁。

根因：停用四阶段状态机时移除了 `handoff.json` 生成，但漏掉了这两条 CLI 的前置校验。修复方向与验收见 `diagnosis.md`。

## 需求

1. `artifact-event` 与 `review-manifest` 不再要求 `handoff.json` 存在；当代 change（无 `handoff.json`）与老世代 change（有 `handoff.json`）都能正常写入。
2. 合法性判定改为**当代语义**：change 目录存在且是合法 change（判定锚点见 design.md 决策）；不存在的 change、缺 `proposal.md` 的目录仍以明确错误拒绝（不退化为「任意路径都能写受保护事件」）。
3. 不破坏老世代归档 change 的兼容性（首事件 `initialized` + 有 `handoff.json` 的路径行为不变）。
4. 核对并处置 `workflow_state.py` 其余 `handoff.json` 引用（`:542` `cmd_current` / `:881` `cmd_spawn` / `:999` `cmd_validate`），作为显式决策记录（清理或保留 + 理由），避免半清理。
5. 新增回归测试：无 `handoff.json` 的新 change 能走 `artifact-event` 与 `review-manifest`；老世代仍可写；非法目标仍被拒。

## 背景

这是债务修复（issue 标题即【debt】）。受保护路径门禁与 guard 白名单的存在，使「CLI 不可用 → 只能绕底层」这条退化路径同时削弱了门禁的证据链（结构化解释事件不再经由被 guard 认可的通道产生）。修复后，归档收尾与审阅 manifest 重新可以走单一路径，与「受保护 artifact 证据」和「OpenSpec 收尾」两条最高优先级规则对齐。

## 非目标

- 不恢复、不重建四阶段状态机，不重新引入 `handoff.json` 生成。
- 不重命名或迁移既有归档 change 目录里的 `handoff.json`（历史产物保持原样，只读兼容）。
- 不改动 `flow status` / `flow confirm` / `flow approve` / `flow block` / `flow advance` / `policy-*` 等既有子命令行为（除非其余 `handoff.json` 引用清理决策明确要求）。
- 不改动 `scripts/flow-policy.json` 的受保护路径规则表或 `workflow_guard.py` 白名单语义。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程 CLI | `scripts/workflow_state.py` 的 `cmd_artifact_event` / `cmd_review_manifest` 前置条件由「必须有 handoff.json」改为「change 目录 + 当代合法性判定」 |
| 受保护 artifact 证据 | 归档收尾事件（`current_spec_synced` / `backlog_updated` / `change_archived`）与 review manifest 重新可经 CLI 写入，证据链与 guard 白名单一致 |
| Guard / 门禁 | 不改 `flow-policy.json` 与 `workflow_guard.py`；仅使被白名单放行的 CLI 真正可用 |
| 状态机 legacy 引用 | `cmd_current` / `cmd_spawn` / `cmd_validate` 三处 `handoff.json` 引用的处置写入 design.md 决策（清理或保留 + 理由） |
| Specs | `openspec/specs/change-documentation/spec.md`（MODIFIED「Handoff state file artifact」）、`openspec/specs/dev-workflow-state-machine/spec.md`（MODIFIED 相关 Requirement，明确当代 change 无 `handoff.json` 时两 CLI 仍可用） |
| Tests | 新增 CLI 层回归测试（无 handoff.json 可写 / 老世代可写 / 非法目标拒绝） |
| Docs | 如涉及 `docs/known-debt.md`（本 issue 若在 debt 列表中登记则需移除条目，配 `protected_artifact_explained` 事件）；关键词扫描 dev-workflow 相关文档 |
| Migration / compatibility | 老世代归档 change 路径不变；无既有行为破坏 |
| 明确不受影响 | AgentLoop、ToolRegistry、Web UI、benchmark、MCP、记忆系统 |

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 bugfix（无新增能力面，仅移除已停用状态机的遗留前置 + 补回归测试，行为收敛到代码库**已有**的当代合法性口径）。上游决策已锁定：AGENTS.md「旧的四阶段状态机仪式（phase/sub_state 推进、handoff.json、gate 停止）已停用」已确立方向，issue #199 给出根因与建议方向（移除前置 / 改 gen-2 判定）。判定所复用的 `_flow_is_gen1` 与 `project_workflow_state` 均已在本仓库既有实现中（`openspec/changes/archive/` 下 flow-event-projection / declarative-flow-engine 系列已归档的决策），无待定设计项。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在），改用上述仓库内证据作为依据。

## 测试计划

- CLI 层（`tests/test_workflow_state_cli.py` 或新增）：无 `handoff.json` + 有 `proposal.md` + `change_created` 首事件 → `artifact-event` / `review-manifest` 成功（exit 0）；老世代 change 仍成功；不存在 change / 缺 `proposal.md` → exit 1。
- 端到端验收：新建一个无 `handoff.json` 的 change，两命令均成功且 `scripts/check_openspec_artifacts.py` 通过。
- 全量 pytest + OpenSpec strict validate。
