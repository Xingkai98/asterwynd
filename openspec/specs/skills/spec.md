# skills 规格

## Purpose

定义 Markdown skill 的加载、运行时匹配、上下文注入、手动激活和用户可调用 slash command。当前实现位于 `agent/skills/loader.py`、`agent/skills/runtime.py`，并由 `AgentLoop`、CLI 和 Web 入口接入。

## Requirements

### Requirement: Runtime loads configured skills

Skill runtime SHALL 从配置声明的 skill roots 加载目录式 skill。合法 skill 文件格式为 `skills/<name>/SKILL.md`，文件包含 YAML frontmatter 和 Markdown prompt 正文；root 顶层的 `*.md` 文件不属于当前支持格式。

#### Scenario: Load skills from configured roots

- **GIVEN** 配置声明一个或多个 skill roots
- **WHEN** agent runtime 启动
- **THEN** 系统 SHALL 加载这些 roots 下有效的 `*/SKILL.md`
- **AND** SHALL 保留无效 skill 文件或无效 root 的诊断信息

#### Scenario: Missing skill root

- **GIVEN** 配置的某个 skill root 不存在
- **WHEN** skill runtime 加载 skills
- **THEN** 系统 SHALL 继续启动
- **AND** SHALL 记录该 root 的 warning 诊断

#### Scenario: Duplicate skill name

- **GIVEN** 多个 configured roots 中存在相同 skill name
- **WHEN** skill runtime 加载 skills
- **THEN** 先加载的 skill SHALL 生效
- **AND** 后续重复 skill SHALL 被跳过并记录诊断

### Requirement: Skill index is visible to the model

AgentLoop SHALL 在每次 LLM 调用前注入简短 skill index。index SHALL 只包含可调用 skill 的名称、描述和调用语法，不包含完整 `SKILL.md` prompt。

#### Scenario: Skill index rendered

- **GIVEN** 已加载用户可调用 skills
- **WHEN** AgentLoop 调用 LLM
- **THEN** model-visible messages SHALL 包含简短 skill index
- **AND** index SHALL NOT 包含完整 skill prompt 正文

### Requirement: Always and matched skills are injected for the current run

Skill runtime SHALL 在每次 run 开始时计算当前 active skills。`always: true` 的 skill 每次 run 都激活；普通 skill SHALL 基于 name、description 和 triggers 与当前用户输入做本地匹配。active skill prompt 只作为本次 LLM 调用的 system context 注入，不得永久写入 conversation memory。

#### Scenario: Always skill loaded

- **GIVEN** 某个已加载 skill 声明 `always: true`
- **WHEN** AgentLoop 开始一次 run
- **THEN** 该 skill prompt SHALL 出现在本次 run 的 model-visible context
- **AND** context SHALL 使用清晰的 skill 名称边界

#### Scenario: User input matches trigger

- **GIVEN** 某个非 always skill 声明 trigger phrase
- **WHEN** 当前用户输入包含该 trigger
- **THEN** 该 skill prompt SHALL 出现在本次 run 的 model-visible context
- **AND** 原始 conversation memory SHALL NOT 被追加该 prompt

#### Scenario: User input does not match any skill

- **GIVEN** 当前用户输入未命中任何非 always skill
- **WHEN** AgentLoop 开始一次 run
- **THEN** 系统 SHALL 只注入 skill index
- **AND** SHALL NOT 注入非 always skill prompt

### Requirement: LLM can activate skills with a runtime tool

AgentLoop SHALL 在 skill runtime 可用时注册只读 `ActivateSkill` tool，允许 LLM 在当前 run 内激活一个已加载 skill。该 tool 只改变 prompt context，不读取文件、不写文件、不执行命令，也不扩大权限。

#### Scenario: LLM activates known skill

- **GIVEN** LLM 调用 `ActivateSkill` 并传入已加载 skill name
- **WHEN** tool 执行成功
- **THEN** skill SHALL 在当前 run 中变为 active
- **AND** 下一次 LLM 调用 SHALL 包含该 skill 的完整 prompt
- **AND** runtime event SHALL 记录 `skill_activated`，source 为 `llm_tool`

#### Scenario: LLM activates unknown skill

- **GIVEN** LLM 调用 `ActivateSkill` 并传入未知 skill name
- **WHEN** tool 执行
- **THEN** tool SHALL 返回可读错误
- **AND** 不得注入任何未知 skill prompt

### Requirement: Skill reload refreshes runtime skills

Skill runtime SHALL 支持手动 reload configured skill roots，并让后续 run 使用刷新后的 skill set。

#### Scenario: Reload skills

- **GIVEN** 用户请求 reload skills
- **WHEN** runtime 重新加载 configured skill roots
- **THEN** 后续 run SHALL 使用刷新后的 skill set
- **AND** reload diagnostics SHALL 可被 CLI/Web command result 观察

### Requirement: 用户可调用 skill 出现在 slash command 中

Skill runtime SHALL 将 `user_invocable: true` 的 skill 注册到 central slash command registry。显式 `/skill-name args` SHALL 激活该 skill，并把 args 作为普通用户请求启动 Agent run；原始 slash command 不得作为普通用户消息进入 AgentLoop。

#### Scenario: Skill 出现在 slash command catalog

- **GIVEN** 已加载一个用户可调用 skill
- **WHEN** CLI 或 Web 请求 slash command catalog
- **THEN** catalog SHALL 包含该 skill 对应的 command
- **AND** command metadata SHALL 包含 source `skill` 和 kind `prompt`
- **AND** command SHALL 包含 description 和 argument hint

#### Scenario: Skill slash command 保留自然语言请求

- **GIVEN** 已加载一个名为 `review-skill` 的用户可调用 skill
- **WHEN** 用户发送 `/review-skill 帮我审一下这个 change`
- **THEN** command handler SHALL 将 `review-skill` 解析到该 skill
- **AND** SHALL 将 `帮我审一下这个 change` 作为 Agent run 的用户消息
- **AND** SHALL 在 run 开始前 queue 该 skill activation，source 为 `slash_command`
- **AND** SHALL NOT 将原始 slash command 作为普通用户消息发送给 AgentLoop
