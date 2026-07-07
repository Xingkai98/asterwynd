## Why

仓库已有 `agent/skills/loader.py` 和 `openspec/specs/skills/spec.md`，但当前能力主要停留在 Markdown skill 加载器层面：默认 AgentLoop/CLI 运行时没有配置 skill roots、没有把 always skill 注入 system prompt，也没有按用户输入匹配普通 skill 或提供可观察的 skill 状态。

如果不把 skills 接入真实运行时，后续 coding agent 的常用能力会缺一块：

- 项目级或用户级工作流无法沉淀为可复用 skill。
- agent 无法按任务自动加载相关 skill 指令。
- 用户无法在交互会话中查看当前可用 skill 或刷新 skill 目录。
- 后续 MCP、browser、review、TDD 等能力难以通过 skill 扩展形成轻量工作流。

本 change 目标是把已有 SkillLoader 升级为可配置、可观测、可在 CLI/AgentLoop 中生效的 runtime skill capability。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 配置新增 skill roots，支持 repo-local 和用户级目录；路径展开应支持 `~` 和环境变量。
- Skill 格式升级为目录式 `skills/<name>/SKILL.md`；本 change 迁移现有旧样例，不保留 root 下 `*.md` 旧格式兼容。
- Agent 构造时 SHALL 加载 configured skill roots，跳过无效 skill 文件并保留诊断。
- 每个 run SHALL 注入简短 skill index，只包含 name、description 和显式调用格式。
- always skills SHALL 注入完整 skill prompt。
- 普通 skills SHALL 基于用户输入本地匹配，并把匹配到的完整 skill prompt 注入当前 run 的上下文。
- LLM MAY 通过 `ActivateSkill` 工具在当前 run 中主动激活已加载 skill；激活后下一轮 LLM 调用 SHALL 携带完整 skill prompt。
- CLI slash command 框架接入后，新增：
  - `/skills`：列出已加载 skills、来源和 always/user-invocable 状态，并展示加载诊断。
  - `/skills reload`：重新加载 configured skill roots。
- user-invocable skills SHALL 注册进 slash command catalog，允许用户使用 `/skill-name 用户请求` 显式调用；命令后的自然语言参数 SHALL 作为用户消息启动 Agent run，并在 run 前激活对应 skill。
- 本 change 不负责创建 skill、安装外部 skill marketplace 或复杂语义检索；只做本地 skill runtime。

## Capabilities

### Modified Capabilities

- `skills`: 从 loader 能力升级为 runtime skill loading、matching 和 prompt injection。
- `configuration`: 增加 skill roots 配置。
- `cli`: 增加 `/skills` 和 `/skills reload` 命令，依赖 slash command framework。
- `web-ui`: Web command catalog 暴露 skill commands，WebSocket 支持 `/skill-name args` 启动 skill-triggered Agent run。

## Impact Analysis

- 影响代码：
  - `agent/skills/loader.py`
  - `agent/skills/runtime.py`
  - `agent/tools/builtin/activate_skill.py`
  - `agent/config.py`
  - `agent/loop.py`
  - `agent/commands/registry.py`
  - `cli.py`
  - `web/session.py`
  - `web/server.py`
- 影响测试：
  - `tests/agent/skills/test_loader.py`
  - 配置解析测试。
  - CLI `/skills` 命令测试。
  - CLI/Web skill slash command 测试，覆盖 `/xx-skill 帮我xxx` 参数传递和 prompt 组装。
  - Agent run/system prompt 注入测试。
  - `ActivateSkill` 工具测试，覆盖 LLM 主动激活、未知 skill 和重复激活。
- 影响文档：
  - `openspec/specs/skills/spec.md`
  - `openspec/specs/configuration/spec.md`
  - `openspec/specs/cli/spec.md`
  - `openspec/specs/web-ui/spec.md`
  - `docs/development-guide.md`
  - `docs/architecture.md`
  - `docs/testing-guide.md`
  - `README.md` / `README_EN.md`
- 依赖：
  - 依赖已归档的 slash command framework，以复用 command registry。
- 不影响：
  - MCP adapter。
  - browser/computer use。
  - 外部 skill marketplace 或 skill 创建流程。

## Reference Implementation Research

- status: enabled
- reason: Skills 是 coding agent 可扩展工作流的基础，应参考其他 agent 如何配置 skill roots、加载 Markdown skill、自动注入相关指令和提供可观察入口。
- research questions:
  - Skills 应在 Agent 构造时加载，还是每轮按需加载？
  - always skill 和 matched skill 应注入 system prompt、developer prompt 还是用户上下文附近？
  - `/skills` 这类命令应只做展示/刷新，还是参与 skill 匹配？
  - user-invocable skill 应该通过 `/skills run <name>` 调用，还是作为 `/skill-name <args>` 直接进入 command catalog？
  - slash command 后的自然语言参数应如何传给 skill prompt 或 workflow？
  - skill roots 是否需要区分 repo-local、user-global 和 external/shared？
- findings:
  - 当前环境没有可调用的 `codegraph` 命令，本次按流程降级使用 `rg` 和定点文件阅读。
  - Claude Code 提示中存在 skills 自动 surfaced/reminder 和 skill discovery 相关指令；Hermes 配置示例包含 external skill directories、local skills precedence 和 skill creation nudges；Nanobot 文档将 skills 作为核心上下文能力；OpenClaw 将 skills 作为扩展/插件生态的一部分。
  - 参考实现倾向于把 skills 作为 runtime context 能力，而不是单纯 CLI 命令；CLI 命令主要提供列表、刷新、安装或调试入口。
  - Claude Code 将 user-invocable skills 转换为 `type=prompt` command，`/<skill-name> args` 会把 args 交给 `getPromptForCommand`，再通过 `$ARGUMENTS`、`$0` 或具名参数替换进 skill prompt；skill 也可声明 fork context 来启动子 agent。
  - Claude Code 还会通过 `skill_discovery` surfaced attachment 和 session-specific guidance 告诉模型相关 skills 以及 `/<skill-name>` 的含义；完整 skill prompt 不作为所有 skill 的常驻系统提示。
  - Codex app-server 的显式 skill 调用使用 `$<skill-name> 用户任务` 文本，同时推荐提交结构化 `skill` input item，让后端直接注入 skill 指令，避免只靠模型识别。
  - Codex skills 采用 `skills/<skill-name>/SKILL.md` 目录式入口，并把 `user-invocable`、`argument-hint`、`allowed-tools` 和 `$ARGUMENTS` 作为推荐 metadata/prompt 模板能力。
  - Gemini CLI 文档说明会把 enabled skills 的 name/description 注入 system prompt，模型需要时调用 `activate_skill`，再把 `SKILL.md` 正文和目录结构加入上下文；其 discovery order 包含 built-in、extension、user、workspace skills，并按优先级处理同名 skill。
  - Goose recipes 使用参数化 prompt/workflow 模板，说明用户输入参数和 recipe/skill prompt 的组装应是运行时的显式职责。
  - 多个参考实现区分用户级/共享 skill 目录，说明 Asterwynd 需要配置 skill roots，而不应只写死单个 repo 目录。
- design impact:
  - 本 change 以 runtime skill roots、always injection、matched injection 和 `/skills` 可观测为最小闭环。
  - Skill 格式采用目录式 `skills/<name>/SKILL.md`，迁移现有 `skills/*.md` 样例，不保留旧格式兼容。
  - 每轮注入短 skill index，让模型知道可用 skills；完整 skill prompt 只在 always、本地匹配、显式 slash command 或 `ActivateSkill` 工具激活后注入。
  - 增加低风险 `ActivateSkill` runtime tool，使 LLM 在本地匹配未命中但判断需要 skill 时可以主动激活已加载 skill。
  - skill runtime 依赖 slash command framework，但不把 command registry 与 skill matching 强耦合；skill runtime 应作为 command source 注册 user-invocable skills。
  - `/skill-name 用户请求` 应显式解析到 skill，并把 `用户请求` 作为 args 参与 skill prompt 组装；不要把整条 slash command 原样交给 AgentLoop 让模型猜。
  - 首版使用现有 loader 的 Markdown 格式，不引入 marketplace、安装器或向量检索。
