## Why

`MyAgent` 作为项目名过于普通，GitHub 搜索辨识度低，也不能承载项目未来作为本地 coding-agent 系统的独特叙事。当前分支已经完成命名讨论、slogan 草案和 wordmark 预览，并选择 `Asterwynd` 作为正式项目名。本 change 将活动代码、配置、CLI、Web、benchmark 和文档入口一次性迁移到新名称，避免继续保留双命名状态。

## Change Type

- primary: feature
- secondary: []

## What Changes

- README 中文/英文入口使用居中 Asterwynd wordmark、语言链接和 slogan。
- CLI 交互模式显示纯文本 Asterwynd wordmark 和中英文 slogan；单轮 CLI 不输出 banner。
- Web UI header 显示 Asterwynd wordmark，并提供本地品牌资产静态路径。
- Python project name、CLI script、配置文件名、环境变量前缀、日志命名空间和 benchmark runner 名统一迁移到 Asterwynd。
- 活动 benchmark task 目录、task id、repo id 和 hidden patch 文本统一迁移到 `asterwynd-*` 命名。
- `agent/` Python package 目录保持不变，只调整其公开文案、类型名和配置类名。

## Capabilities

### Modified Capabilities

- `cli`: 交互模式启动 Asterwynd wordmark；`benchmark` 命令使用 `--agent asterwynd` 和 `AsterwyndRunner`。
- `web-ui`: Web header 展示 Asterwynd wordmark，并提供品牌资产静态访问路径。
- `configuration`: 默认配置文件改为 `asterwynd.yaml`，环境变量前缀改为 `ASTERWYND_`。
- `benchmark`: 内置 runner 和本地活动任务统一使用 Asterwynd 命名。

## Dependencies

- 依赖当前命名讨论结论：正式项目名为 `Asterwynd`，slogan 为 `Navigate by stars. Prove with traces.` / `以星为引，变更有证。`
- 不依赖 `add-minimal-tui-runtime-view`。本 change 只提供未来 TUI 可复用的纯文本 wordmark 资产，不实现完整 TUI。

## Impact

- 影响代码：
  - `pyproject.toml`
  - `cli.py`
  - `agent/config.py`
  - `agent/branding.py`
  - `agent/assets/`
  - `benchmarks/`
  - `web/`
- 影响文档和资产：
  - `README.md`
  - `README_EN.md`
  - `AGENTS.md`
  - `CONTEXT.md`
  - `docs/`
  - `openspec/`
  - `docs/assets/`
- 影响测试：
  - CLI 交互输出、配置、benchmark runner、Web server/static asset 和品牌模块测试。

## Non-Goals

- 不重命名 `agent/` Python package 目录。
- 不提供旧 `myagent` 命令、`myagent.yaml`、`MYAGENT_*` 环境变量或 `MyAgent*` 类型别名。
- 不迁移 archive、历史 benchmark reports、历史 discussion 原文、日志和本地虚拟环境中的旧名。
- 不实现完整 TUI runtime view。
- 不引入外部字体、远程图片或运行时网络依赖。
