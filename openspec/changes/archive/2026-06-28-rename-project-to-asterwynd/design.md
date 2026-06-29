## Context

项目旧名 `MyAgent` 缺少辨识度，也不适合长期作为公开仓库和面试叙事的名字。当前命名探索选择 `Asterwynd`：`Aster` 表示星辰与方向参照，`wynd` 表示风与行动路径，trace 则证明 agent 的实际航迹。

用户已经确认本 change 采用一次性全量迁移：活动代码、配置、CLI、Web、benchmark 和入口文档都改到 Asterwynd，不保留旧名兼容入口。唯一保留的代码边界是 `agent/` Python package 目录，因为它是内部模块边界，重命名包目录会扩大 import churn，且不会影响项目公开可发现性。

## Goals / Non-Goals

**Goals:**

- 将公开项目名、Python project name、CLI script、配置文件名、环境变量前缀、日志命名空间、benchmark runner 和活动 benchmark task 统一迁移到 Asterwynd。
- 在 README 中文/英文入口展示 Asterwynd wordmark、语言链接和 slogan。
- 在 CLI 交互模式展示纯文本 wordmark，并在窄终端使用 compact 文本。
- 在 Web UI header 展示 SVG wordmark，移动端保持可读降级。
- 集中维护品牌名、slogan 和 TUI banner 文本，避免入口层散落硬编码。
- 更新 current specs、OpenSpec change backlog 和相关项目文档，确保新事实可追溯。

**Non-Goals:**

- 不重命名 `agent/` Python package 目录。
- 不保留旧 `myagent` 命令、配置文件、环境变量或类型别名。
- 不迁移 archive、历史 benchmark reports、历史 discussion 原文、日志和本地虚拟环境中的旧名。
- 不实现新的 TUI runtime view、布局系统或终端交互控件。
- 不依赖远程图片、外部字体或运行时下载资源。

## Decisions

### Decision 1: 活动资产一次性迁移，不做兼容层

所有活动入口使用 Asterwynd：`pyproject.toml` project name、console script、`AsterwyndConfig`、`AsterwyndRunner`、`ASTERWYND_*` 环境变量、`asterwynd.yaml`、`--agent asterwynd` 和本地 `asterwynd-*` benchmark task。

理由：当前项目仍是个人主导使用，兼容层会让文档、测试和 benchmark 结果长期处于双命名状态，收益低于维护成本。

### Decision 2: `agent/` 包目录不重命名

内部 Python package 目录继续叫 `agent/`。公开名称迁移通过 project metadata、CLI script、配置、文档和类型名体现。

理由：`agent/` 描述的是领域模块，不是品牌名；重命名包目录会扩大 import churn，也会和当前模块职责相冲突。

### Decision 3: 历史记录不重写

`openspec/changes/archive/**`、`benchmarks/reports/**`、`docs/discussions/**`、`logs/**` 和本地虚拟环境不做旧名替换。

理由：这些内容代表历史状态或本地生成结果。重写会破坏审计语境，且不影响活动入口的一致性。

### Decision 4: TUI 使用纯文本源，Web/README 使用 SVG/PNG

CLI 交互模式和未来 TUI 使用打包在 `agent/assets/` 下的纯文本 wordmark；README 使用 `docs/assets/asterwynd-wordmark.svg`；Web UI 使用从 TUI render preview 提取的透明 PNG wordmark，只展示 `Asterwynd` 字样。

理由：终端原生渲染需要纯文本可降级；GitHub 和 Web 需要可缩放图形资产，SVG 更适合固定首屏命名。

### Decision 5: 单轮 CLI 默认不显示 banner

只有 CLI 交互模式默认显示 banner，并提供 `--no-banner` 关闭。单轮 CLI、benchmark 和非交互输出不显示品牌 masthead。

理由：单轮 CLI 常用于脚本、测试和 benchmark，banner 会污染可读/可解析输出。交互模式更接近 TUI splash 场景，适合展示项目名。

### Decision 6: wordmark 优先保证可读性

默认 TUI wordmark 采用清晰 block 版本，不使用会让 `Asterwynd` 结尾误读为 `Asterwyd` 的斜体版本。

理由：用户已经明确指出结尾 `n` 可读性问题。品牌视觉的第一要求是读对名称。

## Risks / Trade-offs

- [Risk] 不保留旧名兼容入口会让本地旧命令和旧配置立即失效。Mitigation: 当前项目主要由单人使用，README、开发指南、测试和示例配置同步更新到新入口。
- [Risk] `agent/` 包目录没有随品牌重命名，未来读者可能问为什么不是 `asterwynd/`。Mitigation: 在 proposal/design 中记录这是有意保留的内部领域模块名。
- [Risk] GitHub README SVG 在某些环境加载失败。Mitigation: 图片 alt 文本写 `Asterwynd`，README 正文第一段也直接写项目名。
- [Risk] Web header wordmark 过宽挤压状态栏。Mitigation: CSS 限制 wordmark 宽高，小屏降级为文本。
- [Risk] CLI banner 影响自动化输出。Mitigation: 只在交互模式默认显示，并提供 `--no-banner`。

## Testing Strategy

- CLI 测试覆盖交互模式显示 banner、`--no-banner` 关闭 banner、单轮模式不显示 banner，以及 benchmark runner 选择。
- 配置测试覆盖 `asterwynd.yaml` 发现、`ASTERWYND_*` 环境变量和 `AsterwyndConfig`。
- benchmark 测试覆盖 `AsterwyndRunner`、runner timeout 和 CLI benchmark。
- 品牌模块测试覆盖宽终端和窄终端 banner 选择。
- Web server/static 测试覆盖 app title、`/assets/asterwynd-web-wordmark.png` 静态资源可访问。
- OpenSpec 校验覆盖本 change 的 spec delta、tasks、current specs 和 backlog。
