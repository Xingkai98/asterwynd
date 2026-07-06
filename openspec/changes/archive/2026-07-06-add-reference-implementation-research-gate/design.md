## Context

Asterwynd 的自然语言开发流程已经形成三层治理：

- `AGENTS.md` 负责最高优先级入口规则和自然语言到 OpenSpec 流程路由。
- `docs/requirements-process.md` 负责需求、设计、实现、验证和归档流程。
- `scripts/check_openspec_artifacts.py` 负责机械检查 active changes 的文档结构，并由 CI 运行。

现有“参考实现调研”规则已经写入 `AGENTS.md` 和 `docs/requirements-process.md`，但缺少可执行门禁。要让规则对后续 agent 生效，必须把调研决策写入每个 change 的稳定 artifact，并让 checker/CI 发现漏填、空壳和未说明的关闭。

## Goals / Non-Goals

Goals:

- 为非 docs change 增加 `## Reference Implementation Research` 记录要求。
- 默认启用参考实现调研；允许显式关闭，但必须说明理由。
- 让 artifact checker 和 CI 阻止漏填或空壳记录。
- 更新任务模板和流程文档，让后续 change 默认继承该门禁。
- 迁移现有 active changes，避免新规则破坏当前 backlog 基线。

Non-Goals:

- 不让 CI 读取 `.dev/reference-repos.txt`，也不要求 CI 环境存在本地参考仓库。
- 不判断调研结论是否充分、是否正确。
- 不引入新的 codegraph 集成或索引产物。
- 不把参考仓库路径、`.codegraph/` 或本地索引结果提交到项目。
- 不要求纯 docs change 补充调研记录。

## Decisions

### Decision 1: 调研记录使用单独 H2 section

非 docs change 使用 `## Reference Implementation Research`，放在 `proposal.md` 或 `design.md` 中。首选 proposal 记录初始决策，design 可补充更细结论。

理由：调研是否启用是需求/设计入口决策，不应藏在任务清单里；但允许设计阶段扩展结论，适配复杂 change。

### Decision 2: 状态字段只接受 enabled / disabled

记录格式使用列表项：

```markdown
## Reference Implementation Research

- status: enabled
- reason: ...
- research questions:
- findings:
- design impact:
```

关闭时：

```markdown
## Reference Implementation Research

- status: disabled
- reason: ...
```

理由：字段少、可读、可用简单解析机械检查；不引入 YAML frontmatter 或复杂 schema，避免和现有文档风格割裂。

### Decision 3: Checker 不读取本地参考仓库

artifact checker 只检查 change 文档中的调研决策记录，不检查 `.dev/reference-repos.txt` 是否存在，也不验证参考仓库路径。

理由：CI 没有本地参考仓库上下文，读取 `.dev/` 会让门禁不可复现。硬规则要约束“必须作出并记录决策”，具体调研质量由设计追问和人工审阅判断。

### Decision 4: 启用状态必须有三类非空记录

`status: enabled` 时，checker 要求 section 中包含非空的 `research questions`、`findings` 和 `design impact`。如果本地参考仓库不可用，`findings` 可以记录“本地 `.dev/reference-repos.txt` 不存在或为空，无法执行本地参考实现调研”，但不能留空。

理由：调研不是打勾动作，至少要留下问题、发现和设计影响，审阅者才能追溯设计是否受参考实现启发或明确未受影响。

### Decision 5: 现有 active changes 做最小迁移

现有 active changes 统一补充 `## Reference Implementation Research`。尚未进入开发的 change 可以记录为 enabled，并说明将在开发前基于 `.dev/reference-repos.txt` 执行；若已有设计事实不足，不伪造已经完成的调研结论。

理由：新 checker 应保持规则简单，不为历史 change 增加 allowlist；但迁移不能伪造已完成审议。

## Reference Implementation Research

- status: enabled
- reason: 本 change 定义参考实现调研门禁，必须对照其他 coding-agent 仓库的入口文档、命令、hooks 和 CI 做法。
- research questions:
  - 仓库级 agent 规则通常如何落地？
  - 规则如何从文字延伸到命令、hooks 或 CI？
  - Asterwynd 应检查“本地参考仓库是否可用”还是检查“change 是否记录了调研决策”？
- findings:
  - 本地 `.dev/reference-repos.txt` 存在，列出多个可参考的 coding-agent 仓库。
  - 当前环境没有 `codegraph` 可执行命令，因此本次降级使用 `find`、`rg` 和定点文件阅读。
  - Codex、opencode、OpenClaw 都使用 `AGENTS.md` 承载仓库级 agent 规则；OpenClaw 还大量使用分目录 `AGENTS.md` 表达局部 ownership 和验证要求。
  - Claude Code、OpenClaw 存在 commands/hooks 相关源码目录；Codex、opencode、OpenClaw 存在 CI workflow，说明流程规则最终需要进入可执行入口或自动验证。
- design impact:
  - 选择 checker/CI 门禁而不是只更新 AGENTS.md。
  - checker 不读取 `.dev/reference-repos.txt`，保证 CI 可复现。
  - 调研质量不由 checker 判断，避免把人工设计审阅误装成机械规则。

## Pre-Implementation Review

- Questions resolved:
  - 默认启用范围：非 docs change 必须显式记录参考实现调研；docs-only 小修豁免。
  - 关闭策略：允许关闭，但必须写 `status: disabled` 和非空 `reason`。
  - 本地参考仓库不可用：不阻塞 checker，但 findings 必须记录不可用事实和替代依据。
  - CI 行为：继续通过现有 artifact checker 运行，不新增独立 CI job。
  - 历史迁移：现有 active changes 补最小记录，不长期保留 allowlist。
- Options considered:
  - 只更新 AGENTS.md 和需求流程文档。
  - 新增独立 checker 命令读取 `.dev/reference-repos.txt`。
  - 在 proposal 中加固定 section，并由既有 artifact checker 检查。
  - 对历史 active changes 做 cutoff 例外。
- Rejected alternatives:
  - 只靠文字规则。原因：用户明确要求硬规范，不能只依赖 agent 自觉。
  - CI 读取 `.dev/reference-repos.txt`。原因：该文件是本地配置，不提交，CI 不应依赖它。
  - 历史 allowlist。原因：会让 checker 长期携带迁移例外，规则更难理解。
- Final confirmations:
  - 使用 `## Reference Implementation Research` 作为稳定 section 名称。
  - `enabled` 状态必须有 reason、research questions、findings、design impact。
  - `disabled` 状态必须有 reason。
  - checker 只做机械检查，不判断调研质量。
- Remaining risks:
  - agent 仍可能写低质量 findings；该风险由 `grill-with-docs` 和人工审阅承担。
  - codegraph 不可用时只能降级为文本阅读；文档应要求记录降级事实。

## Risks / Trade-offs

- [Risk] 新 section 增加 proposal/design 负担。Mitigation: 模板提供固定字段；docs-only change 豁免。
- [Risk] 机械检查可能诱导形式化填充。Mitigation: checker 只保证可追溯记录，设计质量仍由 review 负责。
- [Risk] 现有 active changes 被新规则打红。Mitigation: 本 change 同步做最小迁移。
- [Risk] 本地参考仓库路径各人不同。Mitigation: `.dev/reference-repos.txt` 仍不提交，change 文档只沉淀结论。

## Testing Strategy

- 更新 `tests/test_openspec_artifact_checker.py`，覆盖：
  - 非 docs change 缺少 `## Reference Implementation Research` 失败。
  - `status: enabled` 缺少 reason、research questions、findings 或 design impact 失败。
  - `status: disabled` 缺少 reason 失败。
  - docs-only change 不要求参考实现调研记录。
  - section 可以出现在 `proposal.md` 或 `design.md`。
- 运行 `uv run pytest tests/test_openspec_artifact_checker.py -q`。
- 运行 `uv run pytest -q`。
- 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- 运行 `uv run python scripts/check_openspec_artifacts.py`。
