# 需求流程

本文档规定 MyAgent 后续功能开发的需求管理流程。目标是避免功能杂糅、走一步看一步，以及偏离 offer 导向目标。

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
- 文档影响：需要更新哪些文档和面试材料？

## 开发流程

1. 提出想法。
2. 讨论目标、边界和面试价值。
3. 写需求文档。
4. 写详细设计文档。
5. 人工评审并通过需求和详细设计。
6. 实现测试。
7. 实现功能。
8. 运行验证。
9. 更新文档和能力证明链。

## 参考实现调研

在方案详细讨论阶段，如果用户明确提出“参考其他实现”“看看别的仓库怎么做”或类似要求，应将参考实现调研纳入需求讨论，而不是直接进入实现。

执行规则：

- 先读取本地配置 `.dev/reference-repos.txt`，按行获取当前工作区可用的参考仓库路径；该文件不提交，路径只代表当前工作区。
- 优先用 codegraph 理解参考仓库中的调用链、类型关系和模块边界，再用 `rg`、文件阅读和测试补充验证。
- 调研重点应围绕当前 change 的设计问题，例如权限边界、状态归属、入口参数、错误处理、测试策略，而不是泛泛浏览代码。
- 如果调研影响设计决策，应把结论写入当前 `openspec/changes/<change-id>/design.md`、`proposal.md`、`diagnosis.md` 或讨论纪要；不要把本地路径或 `.codegraph/` 产物写成项目依赖。
- 如果 `.dev/reference-repos.txt` 不存在或为空，应说明无法使用本地参考仓库，并继续用公开文档、当前代码和用户补充信息讨论方案。

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

## 约束与校验

当前使用三层约束：

- OpenSpec schema：`spec-driven` schema 已包含 `proposal`、`specs`、`design`、`tasks` 四类 artifact，可通过 `openspec status --change <id>` 查看缺失项。
- 项目本地脚本：检查 active changes 是否满足项目文档规则，例如 `Change Type` 合法、各类型要求按并集满足、非平凡 change 有 `design.md`、问题定位类 change 有 `diagnosis.md`，并且必填章节不是空壳。
- 人工评审：脚本不判断设计是否合理；开发前必须人工审核 `design.md` 并确认通过。

在开始实现前，应至少运行：

```bash
openspec status --change <change-id>
openspec validate <change-id> --strict
# 项目本地文档规则脚本，加入后也必须运行
uv run python scripts/check_openspec_artifacts.py
```

`scripts/check_openspec_artifacts.py` 只做机械检查：`Change Type` 合法、文件存在、必填章节存在、章节下有正文、没有模板占位符。设计是否正确、取舍是否合理、是否足以指导开发，必须由人工评审确认。

设计评审通过前，不进入实现阶段。

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
- 不允许未经过人工评审通过的 `design.md` 进入开发。
- 不允许为了覆盖 AI 方向而偏离 Agent 开发主线。
