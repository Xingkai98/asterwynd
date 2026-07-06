## Why

当前项目已经有 OpenSpec lifecycle、artifact checker、全量测试、设计追问和收尾 checklist，但这些门槛主要依赖 agent 或维护者主动执行。自然语言开发可以被路由到正确流程，但缺少 CI 级自动门禁时，仍可能出现以下问题：

- PR 未运行全量测试、OpenSpec strict validate 或 artifact checker 就进入合并流程。
- `proposal.md` 的 `## Impact` 粒度不统一，后续实现中发现的新影响面不一定回写到 change 文档。
- 开发前设计追问记录了最终决策，但缺少统一位置记录关键问题、备选方案、否决原因和剩余风险。
- 新版 OpenSpec 初始化生成 `openspec/config.yaml`，但当前项目仍主要依赖 `openspec/project.md` 承载项目上下文，需要明确两者职责，避免 agent 或维护者误删稳定项目说明。
- `master` branch protection 需要稳定的 CI check 名称后再启用，否则容易把合入流程卡住。

本 change 目标是把已有规范升级为可执行的项目治理闭环：先引入 CI workflow 和 Impact Analysis 维护规则，再为后续 branch protection 提供稳定基础。

## Change Type

- primary: process
- secondary: []

## What Changes

- 新增 GitHub Actions CI workflow，默认在 `pull_request` 和 `push` 上运行项目基础门禁。
- CI workflow SHALL 至少运行全量 pytest、OpenSpec strict validate 和项目 OpenSpec artifact checker。
- 非平凡 change SHALL 维护结构化 `## Impact Analysis`，并在 proposal、design、tasks、implementation 和 archive 阶段持续更新。
- 非平凡 change 的 `design.md` SHALL 记录简短的 pre-implementation review 结论，包括已解决问题、备选方案、否决方案、最终确认和剩余风险。
- `openspec/config.yaml` SHALL 纳入项目治理：保留 `schema: spec-driven`，补充适合 OpenSpec 命令读取的短版项目 context / artifact rules，并明确 `openspec/project.md` 继续作为人读项目说明保留。
- `openspec/templates/tasks.md` SHALL 包含 Impact Analysis 动态维护、CI 验证和 pre-implementation review 记录任务。
- artifact checker SHALL 机械检查非 docs change 的 Impact Analysis 和 pre-implementation review 基础结构，但不判断设计质量。
- `master` branch protection 不在本 change 中直接配置；本 change 只记录后续启用条件：CI workflow 在 PR 上稳定通过，并确认 required check 名称。

## Capabilities

### Modified Capabilities

- `change-documentation`: OpenSpec change 文档流程增加 Impact Analysis、pre-implementation review 和 CI 门禁要求。

## Impact Analysis

- 影响代码：
  - `.github/workflows/ci.yml`
  - `scripts/check_openspec_artifacts.py`
- 影响测试：
  - `tests/test_openspec_artifact_checker.py`
  - GitHub Actions workflow 通过 PR/push 运行现有测试和校验命令。
- 影响文档：
  - `AGENTS.md`
  - `docs/requirements-process.md`
  - `openspec/config.yaml`
  - `openspec/project.md`
  - `openspec/templates/tasks.md`
  - `openspec/specs/change-documentation/spec.md`
  - `docs/openspec-change-backlog.md`
- 暂不影响：
  - GitHub branch protection 设置。
  - benchmark smoke 的默认 CI 运行策略。
  - real API、浏览器 smoke、Docker/SWE-bench smoke 的默认 PR 门禁。
