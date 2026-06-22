## Context

当前配置来源以 `.env` 和环境变量为主：

- `.env` 保存 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、provider、model 和 base URL。
- `MYAGENT_DEBUG`、`MYAGENT_LOG_LEVEL`、`MYAGENT_BENCHMARK_PARALLEL`、`MYAGENT_COMMAND_DENYLIST`、`MYAGENT_IGNORE_PATTERNS` 等散落在 CLI、Web、WorkspacePolicy 和工具实现中。
- agent mode policy 需要为未来 `deny_by_mode`、network policy、approval policy 和 MCP 工具权限预留结构化配置入口。

## Goals / Non-Goals

**Goals:**

- 新增 `myagent.yaml` 作为结构化非敏感配置文件。
- 保留 `.env` 作为 secrets 和环境覆盖入口。
- 定义配置优先级：CLI 显式参数 > 进程环境变量 > `.env` 加载值 > YAML > 默认值。
- 提供 typed config loader，供 CLI、Web、benchmark、WorkspacePolicy 和 ModePolicy 复用。
- 支持 mode tool deny override 等结构化配置字段。

**Non-Goals:**

- 不把 API key 写入 YAML。
- 不删除 `.env` 支持。
- 不一次性重构所有配置调用点；允许按模块逐步迁移，但必须保证统一 loader 是新配置入口。
- 不改变 agent mode policy、WorkspacePolicy 或 Bash allowlist 的默认安全语义。

## Decisions

### Decision 1: `.env` 与 `myagent.yaml` 分工

`.env` 保留 secrets、provider endpoint、provider/model 选择和临时环境覆盖项；`myagent.yaml` 保存结构化、可提交示例化但通常本地化的非敏感配置。

理由：secrets 不应进入 YAML；结构化列表、map 和按 mode 配置不适合环境变量。

字段归属：

| 字段 | 配置位置 | 说明 |
| --- | --- | --- |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | `.env` 或进程环境变量 | secret，不进入 YAML。 |
| `OPENAI_BASE_URL` / `ANTHROPIC_BASE_URL` | `.env` 或进程环境变量 | endpoint 可能包含本地代理、内网地址或环境差异。 |
| `MYAGENT_PROVIDER` | `.env` 或进程环境变量，CLI 可覆盖 | provider 选择属于个人或运行环境默认值。 |
| `MYAGENT_MODEL` | `.env` 或进程环境变量，CLI 可覆盖 | model 选择属于个人或实验默认值。 |
| `MYAGENT_DEBUG` | `.env` 或进程环境变量 | 运行时诊断开关，不进入项目结构化配置。 |
| `MYAGENT_LOG_LEVEL` | `.env` 或进程环境变量 | 运行时日志开关，不进入项目结构化配置。 |
| `agent.default_mode` | `myagent.yaml`，CLI 或环境变量可覆盖 | 非敏感、结构化的项目默认运行意图。 |
| `modes.<mode>.deny_tools` | `myagent.yaml` | 按 mode 的结构化工具策略。 |
| `tools.ignore_patterns` | `myagent.yaml` | 项目/工作区级 ignore 扩展列表。 |
| `tools.command_denylist` | `myagent.yaml` | 项目/工作区级命令 deny 扩展列表。 |
| `benchmark.parallel` | `myagent.yaml`，环境变量或 CLI 可覆盖 | benchmark 默认并发度。 |
| `benchmark.timeout_seconds` | `myagent.yaml`，环境变量或 CLI 可覆盖 | benchmark 默认超时。 |

### Decision 2: 配置优先级固定

配置解析使用以下优先级：

1. CLI 显式参数
2. 进程环境变量
3. `.env` 加载值
4. `myagent.yaml`
5. 代码默认值

实现时 CLI 选项需要区分“用户没有传参”和“用户显式传参”。例如 `--mode`
当前默认值为 `build`，如果继续把默认值当成显式参数，就会导致
`agent.default_mode` 永远无法生效；因此内部解析应使用 `None` 表示未显式传入。

理由：保留现有 CLI 和环境变量覆盖习惯，同时让 YAML 成为稳定默认配置来源。

### Decision 3: deny override 由配置系统承载

agent mode 的工具 deny override 不在 `introduce-agent-mode-policy` 中开放用户配置；该 change 可先在代码中预留空的 `deny_by_mode` 结构。真正从文件读取 deny override 由本 change 的 `myagent.yaml` 配置系统交付。

理由：mode policy change 应聚焦运行模式语义；配置文件格式、加载优先级和迁移策略应独立设计和测试。

### Decision 4: YAML 示例可提交，个人配置不提交

仓库 MAY 提供 `myagent.example.yaml` 说明字段结构；个人的 `myagent.yaml` 默认不提交，除非后续明确要维护项目级共享配置。

理由：不同开发者的模型、工具策略和本地路径不同；示例文件能帮助理解格式，个人配置不应污染仓库。

### Decision 5: 配置文件发现边界

配置文件发现使用以下顺序：

1. CLI `main`、`web`、`benchmark` 显式传入的 `--config <path>`。
2. 从当前工作目录开始向上查找第一个 `myagent.yaml`。
3. 向上查找到 git repo 根目录后停止。
4. 未找到时使用环境变量和代码默认值，不因文件缺失失败。

理由：CLI、Web 和 benchmark 可能从仓库子目录启动，只读取当前目录会漏掉工作区配置；但无限向上查找到用户 home 容易误读其他项目配置。以 git repo 根目录作为上界，符合“工作区配置”的语义。

配置发现只在入口层执行一次。Web 的 `create_app` / `SessionManager` 接收已解析配置或等价策略对象，不为每个 session 重新查找配置；benchmark 的 `BenchmarkRunner` / `MyAgentRunner` 接收已解析配置或等价策略对象，不在任务 worktree 中重新发现 `myagent.yaml`。这样可以避免 benchmark 误读被测仓库中的同名配置文件。

### Decision 6: 工具策略列表只走 YAML

`tools.ignore_patterns` 和 `tools.command_denylist` 只从 `myagent.yaml` 读取，不再继续支持 `MYAGENT_IGNORE_PATTERNS` 和 `MYAGENT_COMMAND_DENYLIST`。

这两个 YAML 字段的语义是追加项目级策略，而不是替换内置安全默认值：

- ignore 规则：内置 ignore 规则 + `tools.ignore_patterns`
- command deny 规则：内置 denylist + `tools.command_denylist`

理由：ignore pattern 和 command denylist 是结构化工作区策略，环境变量的逗号分隔格式不适合作为长期入口。项目仍处于早期，直接迁移到 YAML 比保留 deprecated env 兼容更清晰。

### Decision 7: `agent.default_mode` 作用于入口层

`agent.default_mode` 是所有创建 AgentLoop 或 agent runner 的入口层默认 mode：

- CLI 单轮和交互模式未显式传入 `--mode` 时使用 `agent.default_mode`。
- Web 未显式传入 `--mode` 时使用 `agent.default_mode`。
- Benchmark 未显式传入 `--mode` 时使用 `agent.default_mode`，并在 `run.json`、`result.json` 和 trace 中记录最终解析后的 mode。
- 未来 TUI 和 subagent 入口如果没有显式 mode，也应复用该默认值。

底层 `AgentRunConfig()` 不隐式读取 YAML，代码默认值仍为 `build`。测试或内部代码显式构造 `AgentRunConfig()` 时，不应因为当前目录存在配置文件而改变行为。

理由：`Agent Mode` 是一次 Agent 运行的顶层权限意图，应在入口层解析并显式传递，避免底层模型隐藏读取当前工作区配置。

### Decision 8: 非法配置 fail fast

缺失 `myagent.yaml` 时系统使用环境变量和代码默认值；但如果发现了 `myagent.yaml` 且内容非法，入口 SHALL 启动失败并显示可读错误，不静默退回默认值。

非法配置包括：

- YAML 语法错误。
- 顶层不是 mapping。
- mode 名称不合法。
- `deny_tools`、`ignore_patterns` 或 `command_denylist` 不是字符串列表。
- `benchmark.parallel` 或 `benchmark.timeout_seconds` 不是正整数。

理由：`myagent.yaml` 是用户明确放在工作区里的策略文件，静默忽略会造成安全误解，例如用户以为 denylist 生效但实际未生效。只有文件缺失才允许回退默认值。

### Decision 9: 使用 PyYAML 解析配置

新增 `PyYAML` 作为运行依赖，配置 loader 使用 `yaml.safe_load` 解析 `myagent.yaml`。

理由：需求明确使用 YAML 文件，用户会自然期待标准 YAML 子集；后续 MCP server、browser policy 和 approval policy 等配置会需要嵌套结构。使用成熟 YAML 解析库比手写简化 parser 更稳妥，`safe_load` 可以避免任意对象构造。

### Decision 10: `deny_tools` 使用工具公开名

`modes.<mode>.deny_tools` 使用工具 schema 和 tool call 中暴露的 `Tool.name`，例如 `Read`、`Write`、`Edit`、`Bash`、`InspectGitDiff`。匹配大小写敏感；配置了未知工具名时入口 SHALL fail fast。

理由：工具 schema 暴露给模型的是 `Tool.name`，tool call 执行也使用同一个名字。配置复用这套公开名可以减少映射歧义。未知工具名如果静默忽略，会造成用户以为 deny 生效但实际拼写错误的安全误解。

## Draft Schema

```yaml
agent:
  default_mode: build

modes:
  read_only:
    deny_tools: []
  plan:
    deny_tools: []
  build:
    deny_tools: []

tools:
  ignore_patterns: []
  command_denylist: []

benchmark:
  parallel: 1
  timeout_seconds: 600
```

## Risks / Trade-offs

- [风险] 引入 YAML 后配置来源变多。缓解：固定优先级为 CLI 参数 > 环境变量 > YAML > 默认值，并通过 typed config loader 汇总。
- [风险] secrets 被误写入 YAML。缓解：文档明确 `.env` 负责 secrets，YAML 只保存结构化非敏感配置。
- [风险] 移除 `MYAGENT_IGNORE_PATTERNS` 和 `MYAGENT_COMMAND_DENYLIST` 可能影响旧用法。缓解：该项目仍处早期，change 文档和示例 YAML 明确新入口；测试改为覆盖 YAML 工具策略。
- [风险] 个人配置污染仓库。缓解：个人 `myagent.yaml` 默认不提交，只提交示例文件或明确约定的项目级配置。
- [风险] 非法 YAML 阻止启动。缓解：错误信息指明配置文件路径和非法字段；缺失配置文件仍正常使用默认值。

## Testing Strategy

- 配置 loader 单元测试覆盖缺省值、YAML 读取、环境变量覆盖和 CLI 参数覆盖。
- mode policy 测试覆盖 `deny_tools` 能阻止 schema 暴露和执行，并覆盖未知工具名 fail fast。
- WorkspacePolicy / ListFiles / Find 测试覆盖 YAML ignore patterns 和 command denylist，并移除旧工具策略环境变量测试。
- CLI/Web/benchmark 测试覆盖统一配置对象传入构造路径。
