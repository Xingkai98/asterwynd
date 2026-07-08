# 需求流程

本文档规定 Asterwynd 后续功能开发的需求管理流程。目标是避免功能杂糅、走一步看一步，以及偏离 offer 导向目标。

## 基本原则

- 一个功能点对应一个需求文档。
- 需求没有聊清楚之前，不写实现代码。
- 每个需求必须能接入能力证明链。
- 每个需求必须明确测试策略。
- 功能完成后，文档、测试、benchmark 或运行证据要同步更新。

## 需求文档内容

每个需求至少包含：

- 背景：为什么需要这个能力？
- 面试价值：它对应什么岗位要求或面试问题？
- 用户故事：使用者如何触发和观察这个能力？
- 范围：本次做什么，不做什么？
- 行为定义：输入、输出、状态变化、错误处理。
- 设计约束：必须遵守的架构、协议和安全边界。
- 验收标准：什么算完成？
- 测试计划：单元测试、集成测试、CLI/Web/benchmark 覆盖。
- 影响分析：受影响能力域、代码模块、入口、artifact、配置、测试、文档，以及明确不影响的范围。
- 参考实现调研：是否启用、为什么、调研问题、主要发现，以及这些发现如何影响设计。
- 文档影响：需要更新哪些文档和面试材料？

## 开发流程

每个 change 的生命周期建模为五个阶段（phase），由 `agent/workflow/` 状态机驱动，状态文件为 `openspec/changes/<change-id>/handoff.json`：

| 阶段 | 角色 Agent | 核心产出 |
|------|-----------|---------|
| `planning` | Planner | proposal.md, design.md, spec delta, tasks.md |
| `reviewing` | Reviewer | 设计评审报告 |
| `building` | Builder | 测试代码和实现代码 |
| `code-review` | CodeReviewer | 代码审查报告 |
| `closing` | Closer | spec 同步、归档、backlog 更新 |

每个 phase 包含若干 sub_state，末端为 `ready_for_review`（human review gate）。人在 gate 点确认通过后进入下一 phase，也可以选择跳过或回退。

1. 提出想法。
2. 讨论目标、边界和面试价值。
3. 写需求文档（planning phase）。
4. 写详细设计文档（planning phase）。
5. 维护 `## Reference Implementation Research`，默认启用参考实现调研；如果关闭，记录明确原因。
6. 使用 `grill-with-docs` 对 `design.md` 做开发前设计追问，逐项确认实现细节、依赖、风险、测试策略和文档影响；如果当前环境没有该 skill，必须按同等标准充分追问并记录最终方案。
7. 人工评审并通过需求和详细设计（planning → reviewing gate）。
8. 实现测试（building phase）。
9. 实现功能（building phase）。
10. 代码审查（code-review phase）。
11. 运行验证（closing phase）。
12. 更新文档和能力证明链（closing phase）。
13. PR 发起前，执行 OpenSpec 收尾并纳入同一个实现 PR：将已完成 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`，从 [OpenSpec Change 实现队列](./openspec-change-backlog.md) 的未实现队列移除，并运行 OpenSpec 校验和项目 artifact checker。PR 合入后只确认 active change 目录不存在、backlog 干净且本地 `master` 已同步。

各阶段之间通过 handoff note（存储在 `.handoff/<change-id>/`）传递上下文。同一 agent 可贯穿多个 phase，不强制切换。路由配置（executor、session_mode）支持全局默认 + per-change 覆盖。

## 参考实现调研

在方案详细讨论阶段，非 docs OpenSpec change 默认应将参考实现调研纳入需求讨论，而不是直接进入实现。每个 change 可以显式关闭调研，但必须说明为什么不适用或收益不足。

执行规则：

- 先读取本地配置 `.dev/reference-repos.txt`，按行获取当前工作区可用的参考仓库路径；该文件不提交，路径只代表当前工作区。
- 优先用 codegraph 理解参考仓库中的调用链、类型关系和模块边界，再用 `rg`、文件阅读和测试补充验证。
- 调研重点应围绕当前 change 的设计问题，例如权限边界、状态归属、入口参数、错误处理、测试策略，而不是泛泛浏览代码。
- 如果调研影响设计决策，应把结论写入当前 `openspec/changes/<change-id>/design.md`、`proposal.md`、`diagnosis.md` 或讨论纪要；不要把本地路径或 `.codegraph/` 产物写成项目依赖。
- 如果 `.dev/reference-repos.txt` 不存在或为空，应说明无法使用本地参考仓库，并继续用公开文档、当前代码和用户补充信息讨论方案。

非 docs change 必须在 `proposal.md` 或 `design.md` 维护以下结构，并由项目 artifact checker 机械检查：

```markdown
## Reference Implementation Research

- status: enabled
- reason:
- research questions:
- findings:
- design impact:
```

关闭时使用：

```markdown
## Reference Implementation Research

- status: disabled
- reason:
```

`status: enabled` 时，`reason`、`research questions`、`findings` 和 `design impact` 都不能为空。`status: disabled` 时，`reason` 不能为空。checker 不判断调研质量，也不读取本地 `.dev/reference-repos.txt`；它只保证每个非 docs change 有明确、可追溯的调研决策记录。

## OpenSpec 约定

仓库已使用 OpenSpec 管理需求和能力规格：

- `openspec/specs/` 记录当前已确认的能力规格。
- `openspec/changes/<change-id>/` 记录单个需求对一个或多个能力域的 delta spec。
- `openspec/project.md` 记录项目级约定和能力域地图。

不要把需求散落在 README、roadmap 或聊天记录里。README 和 roadmap 可以引用 OpenSpec 结论，但不能替代需求规格。

## Change 文档结构

每个非平凡 OpenSpec change 应包含以下文档：

- `proposal.md`：说明为什么做、做什么、不做什么，以及影响哪些能力域。
- `specs/<capability>/spec.md`：定义系统对外可验证的行为要求。
- `design.md`：详细设计，说明实现方案、关键决策、接口、错误处理、测试策略和风险。
- `tasks.md`：按依赖顺序拆分可执行任务。

非平凡 change 必须维护 `## Impact Analysis`。首选放在 `proposal.md`；如果影响面需要在设计阶段展开，也可以在 `design.md` 补充更细版本。影响分析至少判断以下方面是否受影响：

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

proposal 阶段可以保留 `unknown`、`TBD` 或 `待确认`，但开发前设计追问必须将待确认项清理为明确结论或阻塞项；归档前不得残留未解释的占位词。

新建 `tasks.md` 时，应先复制或参考 `openspec/templates/tasks.md`，再按当前 change 裁剪和补充。模板中的通用验证项默认保留，只有在明确不适用时才删除，并在设计或任务中说明原因。

当 change 来自 bug、回归、线上式故障、工具不可用或调研驱动的问题定位时，还必须包含：

- `diagnosis.md`：记录症状、影响、复现、证据、假设、根因、修复选项、推荐方向和回归测试要求。

`proposal.md` 必须声明 change 类型：

```markdown
## Change Type

- primary: feature
- secondary: []
```

允许的类型：

- `feature`：新功能或行为扩展。
- `bugfix`：修 bug、回归、工具不可用或故障。
- `research`：调研驱动的方案判断或外部工具对比。
- `docs`：纯文档小修。
- `process`：流程、规范、项目管理规则变更。
- `refactor`：不改变外部行为的结构调整。

当一个 change 同时涉及多类工作时，`primary` 记录触发原因，`secondary` 记录辅助性质。项目文档规则按 `primary` 和 `secondary` 的并集校验：每个涉及的类型要求都必须满足。

示例：

```markdown
## Change Type

- primary: bugfix
- secondary: [research, feature]
```

该 change 同时需要问题定位、调研证据和详细设计。

职责边界：

- Spec 回答“系统必须保证什么”。
- Design 回答“准备怎么实现，以及为什么这样设计”。
- Diagnosis 回答“问题为什么发生，证据是什么”。
- Tasks 回答“开发时按什么顺序做”。

`docs/` 只保存稳定长期文档。单个 change 的详细设计和定位过程应留在对应的 `openspec/changes/<change-id>/` 下，并随 change 一起归档。

## 开发前设计追问

开始实现任何非平凡 change 前，必须先用 `grill-with-docs` 审视 `design.md`：围绕现有代码、项目词汇、规格 delta、入口行为、数据结构、配置、错误处理、权限边界、测试策略和验证命令逐项追问，直到每个关键实现细节都有明确最终方案。

执行规则：

- 用户要求“开始开发 / 实现 / 做某个 change”时，agent 的第一阶段必须是读取 change 文档、加载并声明使用 `grill-with-docs`，然后逐项提出设计问题；在这个阶段完成前不得写实现代码或测试代码。
- agent 可以基于代码和文档提出推荐答案，但不得把自己的推荐答案当作用户确认；只有用户明确确认，或已有代码/文档能无歧义回答，才算该问题 resolved。
- 如果问题能通过阅读代码或项目文档回答，先查代码和文档，不把可验证事实留给猜测。
- 如果发现术语、边界或设计决策不清楚，应先更新当前 change 的 `design.md`、`proposal.md`、spec delta、`tasks.md` 或稳定项目文档，再进入开发。
- 如果当前 agent 环境没有 `grill-with-docs` skill，也必须按同等标准执行设计追问：逐个设计分支确认方案、记录取舍和未选方案，并明确测试与验收方式。
- 设计追问完成后，`design.md` 必须包含 `## Pre-Implementation Review`，简要记录已解决问题、备选方案、否决方案、最终确认和剩余风险；不要把完整聊天流水粘贴进设计文档。
- 设计追问完成前，不进入测试实现或功能实现。

## Impact Analysis 动态维护

Impact Analysis 不是一次性段落，而是贯穿 change lifecycle 的维护对象：

- proposal 阶段：记录初始影响面，允许待确认项。
- design 阶段：结合代码和文档逐项确认影响面，将待确认项清理为明确结论或阻塞项。
- tasks 阶段：每个受影响入口必须对应测试、文档或验证任务；如果不需要动作，应记录原因。
- implementation 阶段：如果发现新影响面，先回写 Impact Analysis 和 `tasks.md`，再继续无关实现。
- archive 阶段：确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`，并完成对应验证。

项目 artifact checker 只机械检查 Impact Analysis 和 Pre-Implementation Review 的存在与非空，不判断分析是否充分，也不在普通模式下禁止 proposal 阶段的待确认占位词。

## Reference Implementation Research 动态维护

参考实现调研不是一次性搜索记录，而是设计阶段的输入：

- proposal 阶段：默认启用并记录初始问题；如果关闭，记录原因。
- design 阶段：结合本地参考仓库、codegraph 或降级的 `rg`/文件阅读，把发现转化为设计影响。
- tasks 阶段：如果调研发现需要新增验证、迁移或文档任务，应补进 `tasks.md`。
- implementation 阶段：如果实现中发现原调研结论不成立，先回写 findings 和 design impact，再继续相关实现。
- archive 阶段：确认调研记录不再是空壳；本地路径不应作为项目依赖写入稳定文档。

## 自然语言到 OpenSpec 流程

用户可以只用自然语言描述开发动作，不需要反复提醒 agent “按 OpenSpec lifecycle 走”。agent 应根据用户意图自动选择 OpenSpec Codex 命令或等价流程：

| 用户意图 | 流程 |
| --- | --- |
| 讨论想法、比较方案、澄清问题 | `/opsx:explore` 等价流程。只读取和讨论，不写实现代码。 |
| 创建需求、开始一个新 change | `/opsx:propose` 等价流程。创建或补齐 proposal、design、tasks、spec delta，并更新 backlog。 |
| 开始开发某个 change | 先执行 `grill-with-docs` 设计追问；确认后进入 `/opsx:apply` 等价流程，按 tasks 测试先行并实现。 |
| 同步 delta spec 到正式规格 | `/opsx:sync` 等价流程。读取 delta spec 和当前 spec 后智能合并。 |
| 提 PR、收尾、准备合入 | `/opsx:archive` 等价流程。实现 PR 内完成归档、backlog 清理、OpenSpec 校验和 artifact checker。 |
| 合入 PR | 合入后只确认本地 `master` 同步、active change 目录不存在、backlog 不引用已归档 change。 |

如果当前客户端不能直接执行 `/opsx:*` slash command，agent 也必须按表中等价步骤执行；不能因为用户没有显式写命令而跳过 OpenSpec 流程。

## Change PR 固定收尾 checklist

功能实现 PR 发起前，必须把 OpenSpec 收尾也纳入同一个 PR；PR merge、分支删除和 worktree 清理不等于需求流程结束。固定 checklist：

1. 确认受影响的当前规格已经写入 `openspec/specs/`。
2. 将 `openspec/changes/<change-id>/` 移动到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
3. 从 `docs/openspec-change-backlog.md` 的“未实现队列”移除该 change，并重新编号后续条目。
4. 同步更新 `docs/openspec-change-backlog.md` 的“并行开发批次”，避免批次章节保留过期状态。
5. 如果该 change 位于“已完成待归档”，也应从该列表移除。
6. 全量浏览 `docs/` 下的稳定文档标题和相关关键词，判断 README、架构、开发指南、测试指南、路线图、benchmark 或讨论纪要是否需要同步；只更新与本 change 直接相关的稳定口径。
7. 运行 `openspec validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
8. 在 PR 说明中记录归档路径、backlog 更新和验证结果。

`docs/openspec-change-backlog.md` 不是历史台账；已归档 change 的 source of truth 是 `openspec/changes/archive/`。只有遇到冲突、校验失败或其他明确阻塞，导致实现 PR 暂时不能完成归档时，才把 change 放入“已完成待归档”，并在阻塞解除后优先清空。

PR 合入后固定确认：

1. 快进本地 `master` 到 `origin/master`。
2. 确认 `openspec/changes/<change-id>/` 不存在。
3. 确认 `docs/openspec-change-backlog.md` 不再引用该已归档 change。

## 约束与校验

当前使用三层约束：

- OpenSpec schema：`spec-driven` schema 已包含 `proposal`、`specs`、`design`、`tasks` 四类 artifact，可通过 `openspec status --change <id>` 查看缺失项。
- 项目本地脚本：检查 active changes 是否满足项目文档规则，例如 `Change Type` 合法、各类型要求按并集满足、非平凡 change 有 `design.md`、问题定位类 change 有 `diagnosis.md`，必填章节不是空壳，核心路径 change 包含 benchmark smoke 验证项，并且 backlog 与 active/archive change 状态一致。
- 项目本地脚本还会检查需要 `design.md` 的 active change 是否在 `tasks.md` 中包含 `grill-with-docs` 或“等价设计追问”任务，避免新 change 漏掉开发前设计门槛。
- 项目本地脚本还会检查非 docs change 是否包含 `## Impact Analysis`，以及需要 `design.md` 的 change 是否包含 `## Pre-Implementation Review`。
- 项目本地脚本还会检查非 docs change 是否包含 `## Reference Implementation Research`，并按 `status: enabled` 或 `status: disabled` 检查必填字段。
- 人工评审：脚本不判断设计是否合理；开发前必须先完成 `grill-with-docs` 或等价设计追问，再人工审核 `design.md` 并确认通过。

在开始实现前，应至少运行：

```bash
openspec status --change <change-id>
openspec validate <change-id> --strict
# 项目本地文档规则脚本，加入后也必须运行
uv run python scripts/check_openspec_artifacts.py
```

`scripts/check_openspec_artifacts.py` 只做机械检查：`Change Type` 合法、文件存在、必填章节存在、章节下有正文、没有模板占位符、Impact Analysis、Reference Implementation Research 和 Pre-Implementation Review 基础结构存在、条件验证项存在、change delta spec 的 capability 能映射到 `openspec/specs/<capability>/spec.md`、非 docs change 的 `tasks.md` 包含 current spec 同步任务、backlog 不引用已归档或不存在的 change。设计是否正确、调研是否充分、取舍是否合理、是否足以指导开发，必须由人工评审确认。

开发前设计追问和设计评审都通过前，不进入实现阶段。

## 验证任务模板

每个非平凡 change 的 `tasks.md` 都应包含通用验证任务：

- 运行相关单元/集成测试。
- 运行全量测试。
- 运行 OpenSpec strict validate。
- 运行项目 OpenSpec artifact checker。
- 如 change 包含 spec delta，将对应 capability 的 delta 合并到 `openspec/specs/<capability>/spec.md`，并确认未实现能力没有被写成已实现。

还应按影响面保留条件验证任务：

- 涉及 AgentLoop、工具协议、coding tools、workspace safety、benchmark runner 或其他 coding-agent 核心路径时，至少跑通一个 benchmark smoke。
- 涉及 Web 时，运行 Web session/server 测试；必要时运行浏览器 smoke。
- 涉及 TUI、browser/computer use、外部服务或其他人工交互入口时，运行对应 smoke。

这些条件验证来自项目级测试规则，不能因为当前 change 的手写任务清单未列出就省略。若某项条件验证无法运行，应在 `tasks.md` 或最终交付说明里记录原因和替代验证。

## 需求状态

建议使用以下状态：

- `draft`: 正在讨论。
- `accepted`: 需求已确认，可以开发。
- `implementing`: 正在实现。
- `validated`: 已完成实现和验证。
- `superseded`: 被后续需求替代。

## 禁止事项

- 不允许“先写代码再补需求”。
- 不允许把多个不相关功能塞进一个需求。
- 不允许只写实现任务，不写验收标准。
- 不允许没有测试计划就开始开发。
- 不允许未经过 `grill-with-docs` 或等价设计追问的 `design.md` 进入开发。
- 不允许未经过人工评审通过的 `design.md` 进入开发。
- 不允许为了覆盖 AI 方向而偏离 Agent 开发主线。
