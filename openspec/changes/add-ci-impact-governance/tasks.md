## 1. 规格

- [x] 1.1 更新 `change-documentation` spec delta，定义 CI 门禁、Impact Analysis 动态维护和 pre-implementation review 记录要求。
- [x] 1.2 明确本 change 不直接配置 GitHub branch protection；保护规则等 CI check 名称稳定后单独执行。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认 CI 命令、Impact Analysis taxonomy、checker 检查范围、docs-only 例外、`openspec/config.yaml` 与 `openspec/project.md` 的职责边界，以及 branch protection 延后策略。

## 2. 测试

- [x] 2.1 新增 artifact checker 测试，覆盖缺失 Impact Analysis。
- [x] 2.2 新增 artifact checker 测试，覆盖缺失 Pre-Implementation Review。
- [x] 2.3 新增或调整流程文档和任务模板，明确 `unknown / TBD / 待确认` 首版不由普通 checker 禁止，但 archive 前必须清理或转成明确阻塞项。
- [x] 2.4 新增或调整测试，确认 `primary: docs` 的纯文档小修不被非平凡 change 规则误伤。

## 3. 实现

- [x] 3.1 新增 `.github/workflows/ci.yml`，运行 pytest、OpenSpec strict validate 和 artifact checker。
- [x] 3.2 更新 `scripts/check_openspec_artifacts.py`，检查非 docs change 的 Impact Analysis 和 Pre-Implementation Review 基础结构。
- [x] 3.3 更新 `AGENTS.md`，加入 Impact Analysis 动态维护和 CI 门禁的最高优先级规则。
- [x] 3.4 更新 `docs/requirements-process.md`，补充各阶段 Impact Analysis 维护流程。
- [x] 3.5 更新 `openspec/config.yaml`，补充 OpenSpec 命令可读取的短版项目 context 和 artifact rules，并保留 `openspec/project.md` 作为人读项目说明。
- [x] 3.6 更新 `openspec/templates/tasks.md`，让后续 change 默认带上 Impact Analysis、pre-implementation review 和 CI 验证任务。
- [x] 3.7 对现有 active changes 做最小结构迁移：`## Impact` 改为 `## Impact Analysis`，并补充不伪造结论的待审 `## Pre-Implementation Review`。

## 4. 验证

- [x] 4.1 运行 `uv run pytest tests/test_openspec_artifact_checker.py -q`。
- [x] 4.2 运行 `uv run pytest -q`。
- [x] 4.3 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.5 在 PR 上确认 GitHub Actions CI 至少成功运行一次。

## 5. PR 收尾

- [x] 5.1 将 `change-documentation` delta 合并到 `openspec/specs/change-documentation/spec.md`，确认 current spec 只描述已经实现的流程能力。
- [ ] 5.2 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-add-ci-impact-governance/`。
- [ ] 5.3 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次。
- [ ] 5.4 记录后续 branch protection 配置条件：CI workflow 名称、required check 名称和是否允许 admin bypass。
- [ ] 5.5 运行 `npx openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
