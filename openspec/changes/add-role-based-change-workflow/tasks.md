## 1. 规格

- [ ] 1.1 更新 `change-documentation` spec delta，定义角色化 change workflow、handoff、implementation review 和 revision loop。
- [ ] 1.2 开发前使用 `grill-with-docs` 或等价设计追问确认角色边界、artifact 位置、checker 范围和单 agent 快速路径。
- [ ] 1.3 维护 `## Impact Analysis`，确认本 change 只影响流程文档和 artifact checker，不改变 runtime 行为。

## 2. 测试

- [ ] 2.1 如新增 checker 规则，先写缺少 handoff / review 结构的失败测试。
- [ ] 2.2 如检查 blocking findings，覆盖未关闭和已接受 deviation 两种路径。
- [ ] 2.3 覆盖 docs-only change 不被多角色流程误伤。

## 3. 实现

- [ ] 3.1 更新 `AGENTS.md`，说明自然语言开发可按角色拆分，也可由同一 agent 完成。
- [ ] 3.2 更新 `docs/requirements-process.md`，补充 Designer / Implementer / Reviewer / Closer 阶段和 revision loop。
- [ ] 3.3 更新 `openspec/templates/tasks.md`，加入 handoff、implementation review 和 revision 任务模板。
- [ ] 3.4 按确认后的范围更新 `scripts/check_openspec_artifacts.py` 和测试。
- [ ] 3.5 更新 `openspec/config.yaml` 的 artifact rules 摘要。

## 4. 验证

- [ ] 4.1 运行相关 artifact checker 测试。
- [ ] 4.2 运行全量测试。
- [ ] 4.3 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.4 运行 `uv run python scripts/check_openspec_artifacts.py`。

## 5. PR 收尾

- [ ] 5.1 将 `change-documentation` delta 合并到 `openspec/specs/change-documentation/spec.md`，确认 current spec 只描述已经实现的流程能力。
- [ ] 5.2 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-add-role-based-change-workflow/`。
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [ ] 5.4 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
