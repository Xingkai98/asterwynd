## Context

当前配置来源以 `.env` 和环境变量为主：

- `.env` 保存 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY`、provider、model 和 base URL。
- `MYAGENT_DEBUG`、`MYAGENT_LOG_LEVEL`、`MYAGENT_BENCHMARK_PARALLEL`、`MYAGENT_COMMAND_DENYLIST`、`MYAGENT_IGNORE_PATTERNS` 等散落在 CLI、Web、WorkspacePolicy 和工具实现中。
- agent mode policy 需要为未来 `deny_by_mode`、network policy、approval policy 和 MCP 工具权限预留结构化配置入口。

## Goals / Non-Goals

**Goals:**

- 新增 `myagent.yaml` 作为结构化非敏感配置文件。
- 保留 `.env` 作为 secrets 和环境覆盖入口。
- 定义配置优先级：CLI 参数 > 环境变量 > YAML > 默认值。
- 提供 typed config loader，供 CLI、Web、benchmark、WorkspacePolicy 和 ModePolicy 复用。
- 支持 mode tool deny override 等结构化配置字段。

**Non-Goals:**

- 不把 API key 写入 YAML。
- 不删除 `.env` 支持。
- 不一次性重构所有配置调用点；允许按模块逐步迁移，但必须保证统一 loader 是新配置入口。
- 不改变 agent mode policy、WorkspacePolicy 或 Bash allowlist 的默认安全语义。

## Decisions

### Decision 1: `.env` 与 `myagent.yaml` 分工

`.env` 保留 secrets、provider endpoint 和临时环境覆盖项；`myagent.yaml` 保存结构化、可提交示例化但通常本地化的非敏感配置。

理由：secrets 不应进入 YAML；结构化列表、map 和按 mode 配置不适合环境变量。

### Decision 2: 配置优先级固定

配置解析使用以下优先级：

1. CLI 显式参数
2. 环境变量
3. `myagent.yaml`
4. 代码默认值

理由：保留现有 CLI 和环境变量覆盖习惯，同时让 YAML 成为稳定默认配置来源。

### Decision 3: deny override 由配置系统承载

agent mode 的工具 deny override 不在 `introduce-agent-mode-policy` 中开放用户配置；该 change 可先在代码中预留空的 `deny_by_mode` 结构。真正从文件读取 deny override 由本 change 的 `myagent.yaml` 配置系统交付。

理由：mode policy change 应聚焦运行模式语义；配置文件格式、加载优先级和迁移策略应独立设计和测试。

### Decision 4: YAML 示例可提交，个人配置不提交

仓库 MAY 提供 `myagent.example.yaml` 说明字段结构；个人的 `myagent.yaml` 默认不提交，除非后续明确要维护项目级共享配置。

理由：不同开发者的模型、工具策略和本地路径不同；示例文件能帮助理解格式，个人配置不应污染仓库。

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
```

## Testing Strategy

- 配置 loader 单元测试覆盖缺省值、YAML 读取、环境变量覆盖和 CLI 参数覆盖。
- mode policy 测试覆盖 `deny_tools` 能阻止 schema 暴露和执行。
- WorkspacePolicy / ListFiles / Find 测试覆盖 YAML ignore patterns 和 command denylist。
- CLI/Web/benchmark 测试覆盖统一配置对象传入构造路径。
