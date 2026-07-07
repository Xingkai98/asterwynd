## Context

当前 `SkillLoader` 可以从目录读取 `*.md`、解析 frontmatter、返回 `Skill` 对象，并提供 always skill 的系统提示拼接和基于 description 的简单匹配。但它没有被 `build_agent`、AgentLoop 或 CLI 默认路径使用。配置文件也没有 skill roots。

这意味着当前 `skills` capability 的 current spec 已定义 loader 行为，但还没有覆盖“运行时如何加载、匹配、注入、观察和刷新”。

参考实现更常见的 skill 布局是目录式 `skills/<name>/SKILL.md`，可携带 `scripts/`、`references/` 和 `assets/` 等支持文件。当前仓库 `skills/code-review.md` 和 `skills/research.md` 只是早期样例，不是已接入 runtime 的内置能力。

## Goals / Non-Goals

Goals:

- 增加 skill roots 配置。
- Agent/CLI/Web 运行时加载 configured skills。
- 采用目录式 `skills/<name>/SKILL.md`，迁移现有样例。
- 每个 run 注入短 skill index。
- always skills 注入完整 skill prompt。
- 普通 skills 根据当前用户输入本地匹配，并注入当前 run 上下文。
- LLM 可通过低风险 `ActivateSkill` 工具在当前 run 主动激活 skill。
- 提供 `/skills` 和 `/skills reload` 作为 CLI/Web 可观测/刷新入口。
- 保持无效 skill 不阻塞 agent 启动，并保留诊断。

Non-Goals:

- 不创建 skill authoring 工具。
- 不接入外部 skill marketplace。
- 不做 embedding/semantic search。
- 不实现 skill 权限隔离或工具 allowlist 细粒度 enforcement。
- 不让 skills 修改 tool registry 权限；skills 首版只影响提示上下文。
- 不保留旧的 `skills/*.md` root-level 文件格式兼容；本 change 迁移现有样例。

## Decisions

### Decision 1: Skill roots 进入统一配置

新增配置字段 `skills.roots`。默认包含 repo-local `skills/`，用户可配置额外目录。路径展开支持 `~` 和环境变量。

同名 skill 采用“首个胜出，后续跳过并记录诊断”。默认 root 顺序是 repo-local `skills/` 在前，用户配置额外 roots 在后，避免用户全局 skill 悄悄覆盖项目约束。

理由：当前仓库已有 `skills/` 目录；用户级或团队共享 skill 目录应通过配置接入，而不是硬编码在代码里。

### Decision 2: Skill 格式采用目录式 `SKILL.md`

首版正式格式为 `skills/<name>/SKILL.md`。现有 root-level `skills/code-review.md` 和 `skills/research.md` 迁移为目录式，不保留旧格式兼容。frontmatter 支持 `name`、`description`、`tools`、`always`、`triggers`、`argument_hint` / `argument-hint` 和 `user_invocable` / `user-invocable`。

理由：目录式是 Claude Code、Codex、Gemini CLI 等参考实现中的主流形态，可以自然承载后续 `scripts/`、`references/`、`assets/`。旧格式未接入 runtime，继续兼容会增加实现分支。

### Decision 3: Runtime 启动时加载，`/skills reload` 手动刷新

首版在 Agent/CLI/Web session 启动时加载 skill roots，并允许 `/skills reload` 手动刷新。不做每轮自动扫描文件系统。

理由：避免每轮文件系统扫描和不可控 prompt 变化；手动 reload 足够支持开发调试。

### Decision 4: 每轮注入短 skill index

每个 run 都注入一个简短 skill index，只包含已加载 skill 的 name、description 和显式调用格式。skill index 让模型知道当前可用 skills，但不包含完整 `SKILL.md` 正文。

理由：Gemini CLI 等参考实现会把 enabled skills 的 name/description 放入 system prompt，避免模型完全不知道可用 skills。完整 skill prompt 常驻会浪费 token，因此只在激活后注入。

### Decision 5: Always skills 注入完整 prompt

always skill 的完整 prompt SHALL 注入每个 run 的 context，并带 skill 名称边界。当前仓库不新增默认 always skill；只保留机制。

理由：always skill 表示全局行为约束或长期工作流，应稳定出现在运行上下文。但 Asterwynd 当前已有 `AGENTS.md` 承载最高优先级规则，不应重复创建 always skill。

### Decision 6: Matched skills 注入当前 run 的临时上下文

普通 skill 基于当前用户输入本地匹配后，只注入当前 run，不永久追加到 memory。匹配读取 `name`、`description` 和 `triggers`。命中任一短语即激活；后续可单独增强匹配算法。

理由：用户一次任务相关的 skill 不应污染后续所有对话；匹配算法先保持简单可测。

### Decision 7: 增加 `ActivateSkill` runtime tool

当本地匹配没有命中或模型在过程中判断需要 skill 时，LLM MAY 调用 `ActivateSkill` 工具激活已加载 skill。该工具只修改当前 run 的 active skill 集合，不读写文件、不执行命令、不扩大工具权限。激活后，下一轮 LLM 调用会包含完整 skill prompt，同一 run 后续可以继续调用已有工具。

理由：参考实现中 Gemini CLI 有 `activate_skill`，Claude Code 有 `Skill` tool。只靠本地匹配会漏掉语义触发；提供受控工具可以让模型在看到 skill index 后主动加载完整 skill。

### Decision 8: `/skills` 只做观察和 reload

`/skills` 输出当前已加载 skill、来源、always 标记和最近一次加载诊断。`/skills reload` 重新加载 configured roots。它不直接触发某个 skill，也不绕过匹配机制。

理由：保持 skill runtime 行为统一，避免用户命令和自动匹配产生两套注入路径。

### Decision 9: User-invocable skill 注册为 slash command

`user_invocable` 未显式为 false 的 skill SHALL 注册为 slash command，`source=skill`、`kind=prompt`，并保留 `argument_hint`。用户输入 `/skill-name args` 时，CLI/Web command registry 拦截该输入，skill handler 组装 skill prompt 和 args，然后启动一次 Agent run；原始 slash command 不作为普通 user message 传给 LLM。

理由：用户明确调用 skill 时不应让模型猜；slash command registry 已经支持 `source`、`kind` 和 args 保留。

## Pre-Implementation Review

- Questions resolved:
  - Skills runtime 单独建 change，不混入 slash command 框架。
  - `/skills` 依赖已归档的 slash command registry。
  - 首版只做本地 skill runtime，不做 marketplace、install 或 authoring。
  - Skills 首版只影响 prompt context，不修改 ToolRegistry 权限。
  - Skill 格式采用目录式 `skills/<name>/SKILL.md`，迁移当前旧样例，不保留 root-level `*.md` 兼容。
  - 同名 skill 首个胜出，后续同名跳过并记录诊断；默认 repo-local root 优先。
  - 每个 run 注入短 skill index；完整 skill prompt 只在 always、本地匹配、显式 slash command 或 `ActivateSkill` 激活后注入。
  - 首版实现用户显式 slash skill、自然语言本地匹配和 LLM 主动 `ActivateSkill` 三条激活路径。
- Options considered:
  - 每轮动态扫描 skill roots。
  - 启动时加载并提供手动 reload。
  - 将 matched skill 永久写入 memory。
  - 将 matched skill 作为当前 run 临时上下文。
  - 保留旧 root-level `skills/*.md` 格式兼容。
  - 只做本地匹配，不提供 LLM 主动激活工具。
  - 每轮注入完整 skill prompt。
  - 一并实现 skill marketplace/install。
- Rejected alternatives:
  - 每轮扫描。原因：会引入不稳定 prompt 变化和性能开销。
  - 永久写入 memory。原因：任务相关 skill 会污染后续对话。
  - 保留旧格式兼容。原因：旧样例未接入 runtime，目录式更符合后续资源组织。
  - 每轮注入所有完整 skill prompt。原因：token 成本高，也不符合多数参考实现的按需加载策略。
  - 只做本地匹配。原因：语义召回有限，模型看到 skill index 后应有受控方式主动激活 skill。
  - 同时实现 marketplace/install。原因：会扩大范围，基本能力补全阶段先做本地 runtime。
- Final confirmations:
  - 依赖已归档的 slash command framework。
  - 默认配置加载 repo-local `skills/`。
  - `ActivateSkill` 所有 mode 可见，因为它只改变 prompt context，不扩大实际工具权限。
  - LLM 激活 skill 后，同一 run 的下一轮 LLM 调用会携带完整 skill prompt，并可继续调用已有工具。
- Remaining risks:
  - Prompt 注入位置如果放错，可能与系统提示、OpenSpec 规则或用户输入优先级冲突。
  - 简单本地匹配可能召回差；首版用 `ActivateSkill` 工具补充模型主动激活路径。
  - `ActivateSkill` 会让一次 run 多一次 LLM 循环；需要用 max iteration 和测试覆盖避免异常循环。

## Risks / Trade-offs

- [Risk] Skill prompt 注入过多导致上下文膨胀。Mitigation: 每轮只注入短 skill index；完整 prompt 仅按需激活。
- [Risk] 无效 skill 静默跳过导致用户不知道。Mitigation: 保留加载诊断并在 `/skills` 展示。
- [Risk] Skills 影响行为但 trace 不可见。Mitigation: 记录 loaded/matched/activated skill 名称到运行事件或 debug/trace。
- [Risk] 配置路径泄漏到可提交文档。Mitigation: 文档只描述字段，不提交本地路径。
- [Risk] `ActivateSkill` 被模型滥用导致多余轮次。Mitigation: 只允许已加载 skill，重复激活返回 already active，并依赖现有 max iteration。

## Testing Strategy

- SkillLoader / runtime 测试：
  - 多 root 加载、重复名称处理、无效 skill 诊断。
  - 目录式 `SKILL.md` 加载和旧 root-level `*.md` 不再加载。
  - triggers、argument_hint、user_invocable frontmatter 解析。
  - skill index 渲染。
  - always skill prompt 注入。
  - matched skill 只注入当前 run。
  - `ActivateSkill` 激活当前 run skill，未知 skill 和重复激活返回可读结果。
- 配置测试：
  - `skills.roots` 解析、路径展开、默认值。
  - 非列表或非法项 fail fast。
- CLI/Web 测试：
  - `/skills` 列出已加载 skills。
  - `/skills reload` 刷新目录并展示结果。
  - `/skill-name args` 启动 Agent run，原始 slash command 不进入普通 user message。
- Agent run 测试：
  - skill index 每轮可见但不包含完整 skill prompt。
  - always skill 出现在 run context。
  - query 命中普通 skill 时注入该 skill。
  - 未命中时不注入普通 skill prompt。
  - 未命中但 LLM 调用 `ActivateSkill` 后，下一轮注入该 skill prompt。
- 验证：
  - `uv run pytest tests/agent/skills -q`
  - 相关 CLI/config/AgentLoop/Web 测试。
  - `uv run pytest -q`
  - OpenSpec strict validate 和 artifact checker。
