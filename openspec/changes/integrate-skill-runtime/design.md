## Context

当前 `SkillLoader` 可以从目录读取 `*.md`、解析 frontmatter、返回 `Skill` 对象，并提供 always skill 的系统提示拼接和基于 description 的简单匹配。但它没有被 `build_agent`、AgentLoop 或 CLI 默认路径使用。配置文件也没有 skill roots。

这意味着当前 `skills` capability 的 current spec 已定义 loader 行为，但还没有覆盖“运行时如何加载、匹配、注入、观察和刷新”。

## Goals / Non-Goals

Goals:

- 增加 skill roots 配置。
- Agent/CLI 运行时加载 configured skills。
- always skills 注入系统提示。
- 普通 skills 根据当前用户输入匹配，并注入当前 run 上下文。
- 提供 `/skills` 和 `/skills reload` 作为 CLI 可观测/刷新入口。
- 保持无效 skill 不阻塞 agent 启动，并保留诊断。

Non-Goals:

- 不创建 skill authoring 工具。
- 不接入外部 skill marketplace。
- 不做 embedding/semantic search。
- 不实现 skill 权限隔离或工具 allowlist 细粒度 enforcement。
- 不让 skills 修改 tool registry；skills 首版只影响提示上下文。

## Decisions

### Decision 1: Skill roots 进入统一配置

新增配置字段，例如 `skills.roots`。默认可包含 repo-local `skills/`，用户可配置额外目录。路径展开支持 `~` 和环境变量。

理由：当前仓库已有 `skills/` 目录；用户级或团队共享 skill 目录应通过配置接入，而不是硬编码在代码里。

### Decision 2: Runtime 启动时加载，`/skills reload` 手动刷新

首版在 Agent/CLI 启动时加载 skill roots，并允许 `/skills reload` 手动刷新。不做每轮自动扫描文件系统。

理由：避免每轮文件系统扫描和不可控 prompt 变化；手动 reload 足够支持开发调试。

### Decision 3: Always skills 注入基础 system prompt

always skill 的 prompt SHALL 注入 Agent 系统提示，使每轮都可见。注入内容应带 skill 名称边界，便于 trace 和调试。

理由：always skill 表示全局行为约束或长期工作流，应稳定出现在运行上下文。

### Decision 4: Matched skills 注入当前 run 的临时上下文

普通 skill 基于当前用户输入匹配后，只注入当前 run，不永久追加到 memory。首版沿用现有 description 包含匹配；后续可单独增强匹配算法。

理由：用户一次任务相关的 skill 不应污染后续所有对话；匹配算法先保持简单可测。

### Decision 5: `/skills` 只做观察和 reload

`/skills` 输出当前已加载 skill、来源、always 标记和最近一次加载诊断。`/skills reload` 重新加载 configured roots。它不直接触发某个 skill，也不绕过匹配机制。

理由：保持 skill runtime 行为统一，避免用户命令和自动匹配产生两套注入路径。

## Pre-Implementation Review

- Questions resolved:
  - Skills runtime 单独建 change，不混入 slash command 框架。
  - `/skills` 依赖 slash command registry，因此实现顺序在 `add-slash-command-framework` 之后。
  - 首版只做本地 skill runtime，不做 marketplace、install 或 authoring。
  - Skills 首版只影响 prompt context，不修改 ToolRegistry 权限。
- Options considered:
  - 每轮动态扫描 skill roots。
  - 启动时加载并提供手动 reload。
  - 将 matched skill 永久写入 memory。
  - 将 matched skill 作为当前 run 临时上下文。
  - 一并实现 skill marketplace/install。
- Rejected alternatives:
  - 每轮扫描。原因：会引入不稳定 prompt 变化和性能开销。
  - 永久写入 memory。原因：任务相关 skill 会污染后续对话。
  - 同时实现 marketplace/install。原因：会扩大范围，基本能力补全阶段先做本地 runtime。
- Final confirmations:
  - 依赖 `add-slash-command-framework`。
  - 默认配置应能加载 repo-local `skills/`。
  - 实现前需要再次确认注入位置、trace 可观测字段、配置 schema 和测试矩阵。
- Remaining risks:
  - Prompt 注入位置如果放错，可能与系统提示、OpenSpec 规则或用户输入优先级冲突。
  - 简单 description 匹配可能召回差；首版接受，后续单独增强。

## Risks / Trade-offs

- [Risk] Skill prompt 注入过多导致上下文膨胀。Mitigation: 首版记录加载数量，必要时限制 matched skill 数量。
- [Risk] 无效 skill 静默跳过导致用户不知道。Mitigation: 保留加载诊断并在 `/skills` 展示。
- [Risk] Skills 影响行为但 trace 不可见。Mitigation: 记录 always/matched skill 名称到运行事件或 debug/trace。
- [Risk] 配置路径泄漏到可提交文档。Mitigation: 文档只描述字段，不提交本地路径。

## Testing Strategy

- SkillLoader / runtime 测试：
  - 多 root 加载、重复名称处理、无效 skill 诊断。
  - always skill prompt 注入。
  - matched skill 只注入当前 run。
- 配置测试：
  - `skills.roots` 解析、路径展开、默认值。
  - 非列表或非法项 fail fast。
- CLI 测试：
  - `/skills` 列出已加载 skills。
  - `/skills reload` 刷新目录并展示结果。
- Agent run 测试：
  - always skill 出现在 system context。
  - query 命中普通 skill 时注入该 skill。
  - 未命中时不注入普通 skill。
- 验证：
  - `uv run pytest tests/agent/skills -q`
  - 相关 CLI/config/AgentLoop 测试。
  - `uv run pytest -q`
  - OpenSpec strict validate 和 artifact checker。
