## Why

Asterwynd 当前已经具备 AgentLoop、工具系统、WorkspacePolicy、Memory、SubAgent、Trace、CLI/Web、Benchmark、RepoMap、LSP 等基础能力，但后续投入顺序仍容易被单个功能点牵引。

为了服务“面向大厂 Agent 相关开发岗位”的项目定位，需要建立一份可维护的 Coding Agent 对标矩阵：以当前主流 coding agent 的能力面为参照，逐项判断 Asterwynd 是否已有能力、是否有等价替代、是否存在缺口，以及缺口应如何转化为 OpenSpec change、测试和 benchmark 证据。

本 change 先建立对标方法、矩阵 artifact 和差距转化规则，不在一个 change 内实现所有缺口。

## Change Type

- primary: research
- secondary: [process]

## What Changes

- 确认参考对象分层：
  - Codex CLI 作为主对标对象，用于定义本地 coding agent 的核心能力面。
  - Claude Code 作为产品能力上限参照，不作为实现主参照。
  - Aider 作为 repo map、代码上下文和编辑工作流参照。
  - OpenCode 作为 TUI、多 provider、AGENTS.md 初始化和多入口体验参照。
- 新增长期维护的对标矩阵 artifact，记录每个能力项的参考来源、Asterwynd 状态、证据、缺口等级和后续 change。
- 规定对标矩阵不能替代 OpenSpec change：任何运行时能力缺口都必须拆成独立 change，再进入实现。
- 将对标矩阵接入能力证明链：重要能力必须能链接到规格、代码、测试、benchmark 或运行证据。

## Capabilities

### Modified Capabilities

- `change-documentation`: 增加 reference-agent parity artifact 的职责边界和维护规则。
- `benchmark`: 增加对标能力项与测试/benchmark 证据之间的映射要求。

## Impact

- 影响文档：
  - 新增 `docs/reference-agent-parity.md` 或等价长期文档。
  - 后续可能更新 `docs/project-positioning.md`、`docs/coding-agent-roadmap.md` 和面试材料中的能力证明链。
- 影响 OpenSpec：
  - 新增对标矩阵的 process/spec delta。
  - 后续根据矩阵缺口拆分独立 OpenSpec changes。
- 影响测试和 benchmark：
  - 本 change 本身不修改运行时代码。
  - 后续每个 runtime 缺口 change 必须明确测试和 benchmark evidence。
