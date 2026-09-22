# Proposal: 归档 change 的 manifest 校验门（fix-issue-232-archived-manifest-gate）

关联跟踪 issue：[#232](https://github.com/Xingkai98/asterwynd/issues/232)（【debt】归档 change 的 review manifest 存在写入与校验双盲区）。本 change 做**盲区 B（校验侧）**；盲区 A（写入侧）已由 `fix-issue-232-archive-write`（PR #234）收口。

## Change Type

- primary: process
- secondary: []

## Why

盲区 A 收口后，受保护写通道已能对已归档 change 写 manifest（`review-manifest --change <裸 id>` 落在 `archive/<date>-<id>/reviews/`）。但校验侧仍有一个洞：`.github/workflows/ci.yml:62` 的 checker **不带 `--check-archived`**，归档 change 一旦归档就脱离 manifest 校验；而 AGENTS.md 要求「归档收尾与实现同一个 PR」，于是 **change 恰在变得可合入的那一刻退出校验范围**。

直接开启 `--check-archived` 当前会红：**15 条既有归档 change 报 `tasks hash mismatch`**。本 change 立项时已把 15 条逐条查清（见 `design.md` D1 的实测表）：

- **根因是流程顺序，不是篡改**：`building-review-manifest.json` 在**审阅 PASS 时**生成（此时 tasks 未全勾），而收尾阶段（spec sync / 归档 / backlog 移除）还会再勾几项。
- **15 条的差异行全部落在 checkbox 行上**（勾选翻转 `[ ]`→`[x]`、同行描述随之更新、一条纯新增 checkbox 行），**零条非 checkbox 行**；`spec_hash` / `report_hash` / `git diff` 全部通过。
- 新近 change（`#199` / `#232` / `#213`）**全部通过**——因为它们在收尾改动之后**重绑了 manifest**。

即：`tasks_hash` 的语义与「tasks.md 是贯穿到归档的活文档」相冲突。本 change 明确该语义并开启校验门。

## 需求

1. `verify_review_manifest` 的 `tasks_hash` 校验**只在 active 语境生效**；归档语境（`archived=True`）不再以 `tasks_hash` 判失败，但 `spec_hash` / `report_hash` / manifest 字段 / manifest 存在性仍 SHALL 校验。归档态该降级 SHALL 在输出中**可见**（不得静默），并写进 spec 说明理由。
2. 立「manifest 最后生成」纪律（C′）：manifest SHALL 在该 change 的 tasks.md 最终化之后生成（含归档 move 之后的最终 head），使 active 语境的 `tasks_hash` 保持有意义；该纪律写进 spec 与开发指南。
3. CI 增加归档校验步骤：`.github/workflows/ci.yml` 的 `validate` job SHALL 运行 `check_openspec_artifacts.py --check-archived`，使归档 change 不脱离校验。
4. 不改写 15 条既有归档 manifest（不做 B′）：不用重算 hash 覆盖历史证据文件。降级 + 纪律已足以让门禁诚实且不复发。
5. 补回归测试：归档态 `tasks_hash` 漂移不报错、但 active 态仍报错；归档态 `spec_hash`/`report_hash` 漂移仍报错；`--check-archived` 在放宽后全仓 exit 0。

## 背景

门禁的价值在于「归档不脱离校验」。盲区 A 修好了写入通道，盲区 B 才有意义——否则 manifest 写得进去、却没人验。本 change 把这条链路补完：写得到 + 验得着。

## 非目标

- 不改写 15 条历史归档 manifest（B′ 已否决：改写归档证据文件的代价大于保住的那点检查强度）。
- 不改 `change_dir_for` 的归档解析、不改写通道（盲区 A 已完成）。
- 不改 `diff_hash` / `head_sha` 校验逻辑（见 `design.md` D5：现状 `_verify_git_span` 只查 commit 存在 + diff_hash 匹配，**不校验 `head_sha == HEAD`**，与 spec 措辞有出入——记 debt，本 change 不动）。
- 不引入新的 manifest 字段或 schema 版本。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 校验语义 | `agent/workflow/review_manifest.py` 的 `verify_review_manifest`：`tasks_hash` 校验在 `archived=True` 时跳过（其余 hash 不变） |
| CI 门禁 | `.github/workflows/ci.yml` 的 `validate` job 增 `--check-archived` 步骤 |
| 开发流程纪律 | 「manifest 在 tasks 最终化后生成」写入 spec + `docs/development-guide.md` |
| 受保护 artifact 证据 | 15 条既有归档 change 的 `tasks hash mismatch` 由红转绿（**不改写其文件**，靠语义放宽） |
| Guard / flow-policy | 不改 |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md`（MODIFIED「Review evidence manifest」的 hash 校验段落 + 新增归档 Scenario） |
| Tests | `tests/agent/workflow/test_review_manifest.py` 增归档/active 对照用例；`--check-archived` 全仓回归 |
| Docs | `docs/development-guide.md`（收尾纪律）、`docs/known-debt.md`（按本 change 收口盲区 B 的范围更新 #232 说明 + 记 head_sha 校验口径债） |
| Migration / compatibility | active change 行为不变；15 条归档由红转绿；无 schema 变更 |
| 明确不受影响 | AgentLoop、ToolRegistry、Web UI、benchmark、MCP、记忆系统、盲区 A 的写通道 |

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 属 process 门禁调整（无新增能力面：放宽已有校验的一维语义 + 开启已有 `--check-archived` CLI 步骤 + 立一条纪律）。上游决策已锁定：issue #232 已记录双盲区与实测证据；同根的 `fix-issue-232-archive-write`（PR #234）已确立归档语境口径；`--check-archived` 是仓库既有能力（`scripts/check_openspec_artifacts.py:1406` 已实现），本 change 只是把它接进 CI。15 条漂移的性质已实测穷举定性（见 `design.md` D1）。无待定设计项。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在），改用上述仓库内证据作为依据。

## 测试计划

- `tests/agent/workflow/test_review_manifest.py`：归档态 `tasks_hash` 漂移 → 不报错；**同输入 active 态 → 报 `tasks hash mismatch`**（判别性对照）；归档态 `spec_hash` / `report_hash` 漂移 → 仍报错；归档态缺 manifest → 仍报错。
- 端到端：`check_openspec_artifacts.py --check-archived` 全仓 exit 0（放宽前 15 红）。
- CI 走查：`validate` job 含 `--check-archived` 步骤（可用 grep 断言或 workflow 语法检查）。
- 全量 `uv run pytest -q` + OpenSpec strict validate。
