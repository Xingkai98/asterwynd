## Context

Asterwynd 已经具备较完整的开发治理文档：`AGENTS.md` 规定自然语言到 OpenSpec 流程的路由，`docs/requirements-process.md` 规定需求先行、设计追问、测试和归档收尾，`scripts/check_openspec_artifacts.py` 负责机械检查，`openspec/templates/tasks.md` 提供通用任务模板。

当前缺口是执行层级不够硬：这些要求主要靠 agent 或维护者主动执行。项目还没有 `.github/workflows/`，`master` 也没有 branch protection。与此同时，Impact 记录已经存在于很多 proposal 中，但格式较松，不能稳定支撑“开发过程中发现新影响面后必须回写”的规则。

新版 OpenSpec 初始化还生成了 `openspec/config.yaml`。该文件适合承载给 OpenSpec 命令读取的短版项目 context 和 artifact rules；但当前仓库已经把 `openspec/project.md` 作为人读项目说明和能力域地图使用，不能因为新版 config 出现就直接删除。

## Goals / Non-Goals

**Goals:**

- 为 PR/push 增加基础 CI workflow，自动运行测试和 OpenSpec 校验。
- 把 Impact Analysis 从一次性 proposal 段落升级为贯穿 change lifecycle 的维护对象。
- 在 `design.md` 中增加 pre-implementation review 结论记录，保留关键决策过程摘要而不是完整聊天流水。
- 将 `openspec/config.yaml` 纳入项目治理，补充机器可读的短版上下文和 artifact rules。
- 更新 artifact checker，使流程规则具备最低机械检查能力。
- 为后续 branch protection 留出清晰启用条件。

**Non-Goals:**

- 本 change 不直接配置 GitHub branch protection。
- 本 change 不把 benchmark smoke、real API、浏览器 smoke 或 Docker/SWE-bench smoke 设为所有 PR 的默认必跑项。
- 本 change 不要求记录完整聊天原文。
- 本 change 不删除 `openspec/project.md`，也不把完整项目说明迁移到 `openspec/config.yaml`。
- 本 change 不让 artifact checker 判断设计是否正确或 Impact Analysis 是否充分。

## Decisions

### Decision 1: 先加 CI workflow，再配置 branch protection

先新增 `.github/workflows/ci.yml` 并让它在 PR 上稳定运行，再把稳定 check 名称用于后续 branch protection。

理由：branch protection 依赖 required status check 名称。若先配置保护规则，再调整 workflow 名称或 job 名称，可能阻塞正常合入。

### Decision 2: CI 默认只跑基础、确定性门禁

首版 CI 默认运行：

- `uv sync --extra dev`
- `uv run pytest -q`
- `npx openspec validate --all --strict`
- `uv run python scripts/check_openspec_artifacts.py`

benchmark smoke、浏览器 smoke、real API 和 Docker/SWE-bench smoke 保持按影响面或手动触发，不作为所有 PR 的默认必跑项。

理由：基础门禁应稳定、可重复、成本可控。高成本或环境依赖强的验证仍由 change tasks 和人工/agent 收尾记录负责。

### Decision 3: Impact Analysis 使用固定 taxonomy，但允许逐项声明不影响

非平凡 change SHALL 维护 `## Impact Analysis`。建议 taxonomy：

- AgentLoop
- Tool system
- Workspace safety
- Agent modes / permissions
- CLI
- Web UI
- TUI
- Benchmark
- Trace / logs / artifacts
- Config / env
- Specs
- Tests
- Docs
- Migration / compatibility
- Explicitly not affected

每项不要求都有影响，但必须明确判断为影响、不影响或需要追问。proposal 阶段可以保留 `unknown / 待确认`；开发前设计追问后应清理或转成明确阻塞项；archive 前不得残留未解释的 `unknown / TBD / 待确认`。

理由：固定 taxonomy 可以降低漏看共享模块的风险；允许“不影响”能避免形式主义地编造影响。

### Decision 4: Pre-implementation review 只记录决策摘要

`design.md` 增加 `## Pre-Implementation Review`，记录：

- Questions resolved
- Options considered
- Rejected alternatives
- Final confirmations
- Remaining risks

不记录完整聊天流水。若讨论很长，可另放 `review.md` 或讨论纪要，但最终实现相关结论必须回写到 `design.md`。

理由：实现者需要读少量稳定结论，而不是翻完整对话。完整过程可以保留在外部聊天或讨论纪要中，但不能替代设计文档里的最终决策。

### Decision 5: Artifact checker 只检查结构和明显占位符

checker SHALL 检查非 docs change 是否包含 Impact Analysis 和 Pre-Implementation Review 的基础结构，并在 archive 前或普通检查中阻止明显占位符。它不判断分析是否完整，也不判断技术取舍是否正确。

理由：机械检查适合防漏项和空壳；设计质量仍由 `grill-with-docs` 或等价设计追问以及人工评审负责。

### Decision 6: `openspec/config.yaml` 承载短版机器上下文，`openspec/project.md` 继续做人读项目说明

本 change SHALL 保留 `openspec/config.yaml`，并在其中维护适合 OpenSpec 命令消费的短版项目 context 和 artifact rules。`openspec/project.md` 继续作为人读项目说明、能力域地图和详细文档约束的 source of truth，不在本 change 中删除。

理由：OpenSpec 新版提示 config 的 `context:` 更适合注入到命令执行中；但项目现有文档和 agent 规则已经引用 `openspec/project.md`，直接迁移或删除会扩大文档影响面，也容易丢失人读结构。

## Proposed Implementation

1. 新增 `.github/workflows/ci.yml`，使用 Ubuntu runner，安装 Python/uv/Node 依赖，运行基础门禁命令。
2. 更新 `AGENTS.md` 的最高优先级规则，加入 Impact Analysis 动态维护和 CI 门禁口径。
3. 更新 `docs/requirements-process.md`，说明 proposal、design、tasks、implementation、archive 各阶段如何维护 Impact Analysis。
4. 更新 `openspec/templates/tasks.md`，加入 Impact Analysis、pre-implementation review 和 CI 验证任务。
5. 更新 `openspec/config.yaml`，保留 `schema: spec-driven`，补充短版项目 context 和 artifact rules。
6. 更新 `openspec/specs/change-documentation/spec.md`，定义规范行为。
7. 增强 `scripts/check_openspec_artifacts.py` 和对应测试，检查新增结构。

## Risks / Trade-offs

- [Risk] CI 首次运行可能暴露依赖安装或环境差异。Mitigation: 首版只选择本地已验证的基础命令，并在 PR 中记录 CI 结果。
- [Risk] Impact Analysis taxonomy 过宽，导致模板噪音。Mitigation: 允许集中写 `Explicitly not affected`，避免每个无关项都长篇解释。
- [Risk] checker 规则过严会阻碍纯文档小修。Mitigation: `docs` primary change 不强制 design 和完整 Impact Analysis。
- [Risk] `openspec/config.yaml` 和 `openspec/project.md` 内容重复后漂移。Mitigation: config 只放短版机器上下文和规则摘要，详细说明仍链接或指向 `openspec/project.md`。
- [Risk] branch protection 延后可能短期仍允许直接 push。Mitigation: 本 change 完成后，单独执行保护规则配置，并把 CI check 名称作为依据。

## Testing Strategy

- 更新 `tests/test_openspec_artifact_checker.py`，覆盖缺失 Impact Analysis、缺失 Pre-Implementation Review、占位符残留和 docs-only 例外。
- 运行 `uv run pytest tests/test_openspec_artifact_checker.py -q`。
- 运行 `uv run pytest -q`。
- 运行 `npx openspec validate --all --strict`。
- 运行 `uv run python scripts/check_openspec_artifacts.py`。
- CI workflow 合入前在 PR 上至少成功运行一次基础门禁。
