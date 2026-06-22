## Why

当前 MyAgent 主要通过 `.env` 和零散环境变量配置 provider、model、debug、benchmark 并发、工具 ignore pattern 和命令 denylist。`.env` 适合保存密钥和简单环境覆盖，但不适合表达结构化配置，例如按 agent mode 定义工具 deny override、工具策略列表、默认运行配置和未来 MCP / network / approval 策略。

随着 agent mode、MCP、network policy、benchmark 默认参数和工具策略增多，如果继续把所有配置塞进环境变量，配置来源会分散，类型不清晰，也难以在 CLI、Web 和 benchmark 间复用。

## Change Type

- primary: feature
- secondary: []

## What Changes

- 新增 `myagent.yaml` 作为结构化、非敏感项目配置文件。
- `.env` 继续用于 API key、base URL 等 secrets 和环境覆盖项，不被 YAML 取代。
- 新增配置加载顺序和优先级：CLI 参数 > 环境变量 > `myagent.yaml` > 默认值。
- 配置模型 SHALL 支持 agent 默认 mode、mode tool deny override、工具 ignore patterns、命令 denylist 等结构化字段。
- CLI、Web、benchmark 和工具策略 SHALL 逐步从统一配置对象读取非敏感配置。

## Capabilities

### New Capabilities

- `configuration`: 结构化配置文件、环境变量覆盖和配置优先级。

### Modified Capabilities

- `agent-modes`: mode policy 可从配置读取 deny override。
- `workspace-safety`: ignore pattern 和 command denylist 可迁移到结构化配置。
- `cli`: CLI 构造运行时配置时读取 YAML 配置。
- `web-ui`: Web session 构造运行时配置时复用 YAML 配置。
- `benchmark`: benchmark runner 可读取结构化默认配置。

## Impact

- 影响代码：
  - `agent/`
  - `agent/tools/`
  - `agent/workspace_policy.py`
  - `cli.py`
  - `web/`
  - `benchmarks/`
- 影响测试：
  - `tests/agent/`
  - `tests/test_cli.py`
  - `tests/web_tests/`
  - `tests/benchmark/`
- 不在本 change 中修改 agent mode policy 的核心语义；只提供配置系统和配置接入点。
