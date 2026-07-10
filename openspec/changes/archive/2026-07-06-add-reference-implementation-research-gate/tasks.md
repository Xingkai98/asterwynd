## 1. 规格

- [x] 1.1 更新 `change-documentation` spec delta，定义参考实现调研决策记录和机械门禁。
- [x] 1.2 明确本 change 的范围、非目标和验收标准。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认默认启用、显式关闭、本地参考仓库不可用、CI 可复现性、历史迁移和 checker 检查边界。
- [x] 1.4 维护 `## Impact Analysis`，列出影响、不影响和现有 active changes 迁移范围。
- [x] 1.5 维护 `## Reference Implementation Research`，记录调研状态、问题、发现和设计影响。
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。
- [x] 1.7 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。

## 2. 测试

- [x] 2.1 新增 artifact checker 测试，覆盖非 docs change 缺少参考实现调研记录。
- [x] 2.2 新增 artifact checker 测试，覆盖 enabled 状态缺少必填字段。
- [x] 2.3 新增 artifact checker 测试，覆盖 disabled 状态缺少 reason。
- [x] 2.4 新增 artifact checker 测试，覆盖 docs-only change 豁免和 section 放在 `design.md` 的场景。

## 3. 实现

- [x] 3.1 更新 `scripts/check_openspec_artifacts.py`，检查 `## Reference Implementation Research`。
- [x] 3.2 更新 `openspec/templates/tasks.md`，让后续 change 默认包含参考实现调研任务。
- [x] 3.3 更新 `openspec/config.yaml` 的 artifact rules。
- [x] 3.4 更新 `AGENTS.md` 和 `docs/requirements-process.md`，明确硬门禁和动态实施方式。
- [x] 3.5 更新 `openspec/specs/change-documentation/spec.md`。
- [x] 3.6 对现有 active changes 做最小结构迁移。

## 4. 验证

- [x] 4.1 运行 `uv run pytest tests/test_openspec_artifact_checker.py -q`。
- [x] 4.2 运行 `uv run pytest -q`。
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行 `uv run python scripts/check_openspec_artifacts.py`。

## 5. PR 收尾

- [x] 5.1 将 `change-documentation` delta 合并到 `openspec/specs/change-documentation/spec.md`。
- [x] 5.2 PR 发起前，将本 change 归档到 `openspec/changes/archive/2026-07-06-add-reference-implementation-research-gate/`。
- [x] 5.3 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次。
- [x] 5.4 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.5 运行 OpenSpec strict validate 和项目 artifact checker。
