# Building Review: workflow-slim (issue #90, Round 3)

## Verdict

**CHANGES_REQUESTED**

## Round 2 Findings 修复验证（含方案 A）

Round 2 的两个 finding 已闭环，方案 A（审阅证据路径迁移）的机制实现本身正确、验证通过：

1. **[HIGH] 强制审阅门禁对未实现 active change 误报** → 已修复。
   - 门禁收窄到 tasks 全勾选：`_tasks_all_complete()`（scripts/check_openspec_artifacts.py:522）+ `requires_building_review`（:557-561，非 docs + spec delta + tasks 全 `[x]`）。
   - 新增回归测试 `test_partial_change_does_not_require_building_review`（tests/test_openspec_artifact_checker.py:175），部分实现 change 不再被拦截。已验证通过。

2. **[LOW] workflow_guard 死代码 + 过时错误消息** → 已清理。
   - `_discover_active_change`/`_check_gate`/`_track_agent_call` 等状态机遗留已删除（f4a4272），grep 确认无残留。

### 方案 A（本轮重点）验证结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| review_report_path / review_manifest_path 指向新路径 | ✅ | agent/workflow/review_manifest.py:22-41 → `openspec/changes/<id>/reviews/` |
| build/verify_review_manifest 用新路径拼 change 目录 | ✅ | review_manifest.py:58,98,105,126-131 |
| check_openspec_artifacts 强制门禁读 change 目录 reviews/ | ✅ | scripts/check_openspec_artifacts.py:547 `review_dir = change_dir / "reviews"` |
| 强制条件保持（非 docs + spec delta + tasks 全勾选） | ✅ | :557-561 |
| check_phase_done `_check_review_report` 用新路径 | ✅ | scripts/check_phase_done.py:260-263 |
| 端到端 CI 场景：证据随 change 提交 → CI 通过 | ✅ | 手动验证，无 `building-review.md missing` |
| 端到端 CI 场景：证据只在 .handoff（未提交）→ 报缺审阅 | ✅ | 手动验证，报 `building-review.md missing` |
| 测试：5 个目标测试文件 | ✅ | 88 passed in 20.40s |
| .gitignore：reviews/ 可提交、.handoff/ 仍忽略 | ✅ | `.gitignore`；`git check-ignore` 实测 |
| 路径函数调用方（grep 全仓） | ✅ | 模块级 `review_report_path`/`review_manifest_path` 仅在 review_manifest.py 内部自用，无外部破坏 |
| 归档 change 场景 | ✅ | `iter_change_dirs` 排除 `archive`（check_openspec_artifacts.py:779）；phase-done 校验只跑 active change，归档后不再 verify review 路径，change_id 语义在 active 期正确 |
| review-loop 命令、AGENTS.md 路径文档同步 | ✅ | .claude/commands/review-loop.md:14,29,66,123,145；AGENTS.md 审阅闭环节 |

## New Issues

### 1. [Medium — PR 合入阻塞] `openspec/changes/workflow-slim/` 不存在，证据落入后形成"幽灵 change 目录"会触发项目 artifact 门禁

- **现状**：issue #90（workflow-slim）分支从未创建 OpenSpec change 目录（`git log --all -- openspec/changes/workflow-slim` 为空，active changes 列表无 workflow-slim）。方案 A 要求审阅证据提交到 `openspec/changes/<id>/reviews/`。按新路径把本轮证据写入 `openspec/changes/workflow-slim/reviews/building-review.md` 后，该目录会成为一个只含 reviews/ 的"幽灵 change"。
- **影响**：`scripts/check_openspec_artifacts.py` 的 `iter_change_dirs`（:773-780）会遍历所有非 archive 子目录，`check_change`（:695-699）对无 proposal.md 的目录直接报 `workflow-slim: missing required file: proposal.md` → CI 的 `uv run python scripts/check_openspec_artifacts.py` 失败，PR 无法合入。（已实测复现；`npx openspec validate --all --strict` 会忽略无 proposal.md 的目录，实测不受影响，但项目自身门禁已足够拦截。）
- **修复方向**：收尾时补全 workflow-slim 的 OpenSpec change 全量产物（proposal.md / design.md / tasks.md / specs delta），reviews/ 作为其子目录。这同时满足 AGENTS.md「OpenSpec 主干」对 #90 应有的流程要求。
- **证据**：`scripts/check_openspec_artifacts.py:695-699`（missing proposal.md 判定）；实测脚本输出 `["workflow-slim: missing required file: proposal.md"]`。

### 2. [Low] `scripts/workflow_state.py` 残留旧路径文案

- `_review_report_path`（scripts/workflow_state.py:274）与 `discover` 输出（:403）仍指向 `.handoff/<change-id>/`。属 #90 已停用状态机仪式的遗留文案，非方案 A 引入，但相对新路径已过时。建议改为 `openspec/changes/<id>/reviews/` 或显式标注命令已停用。

## Test Results

```
python3 -m pytest tests/agent/workflow/test_review_manifest.py \
  tests/test_openspec_artifact_checker.py tests/test_check_phase_done.py \
  tests/test_workflow_state_cli.py tests/test_workflow_guard.py -q
88 passed in 20.40s
```

端到端验证（手动）：
- 正向：`write_change(feature) + tasks 全 [x] + spec delta + write_review_evidence(tmp, "ci-change")` → `check_change` 无 `building-review.md missing`。
- 反向：证据只写 `tmp/.handoff/ci-change/building-review.md`（未提交）→ `check_change` 报 `building-review.md missing — 独立 subagent 审阅未运行`。

## 结论

方案 A 的路径迁移实现正确且验证充分：review_manifest.py / check_openspec_artifacts.py / check_phase_done.py 三处路径一致，强制门禁条件保持，端到端 CI 正反场景通过，88 个测试全绿，未破坏其他调用者，归档场景安全。

但方案 A 的价值前提是"证据随 change 进 PR"。workflow-slim 自身没有 OpenSpec change 目录，按新路径提交本轮证据会形成幽灵 change，触发项目 artifact 门禁（missing proposal.md），阻塞 PR 合入。该问题必须解决：在收尾时补全 workflow-slim 的 OpenSpec change 全量产物，使 reviews/ 成为合法 change 目录的子目录。另有 workflow_state.py 残留旧路径文案的低优清理项。

Verdict: **CHANGES_REQUESTED**（方案 A 代码无需改动；需补全 workflow-slim change 目录 + 清理 workflow_state.py 旧文案）。
