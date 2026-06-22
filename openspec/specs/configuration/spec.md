# configuration 规格

## Purpose

定义 MyAgent 的结构化配置文件、环境变量覆盖和入口层配置解析规则。当前实现位于 `agent/config.py`，入口层包括 CLI、Web 和 benchmark。

## Requirements

### Requirement: 支持结构化 YAML 配置

系统 SHALL 支持从 `myagent.yaml` 读取结构化非敏感配置。缺失配置文件时，系统 SHALL 使用环境变量和代码默认值继续启动；发现非法配置文件时，系统 SHALL fail fast 并返回可读错误。

#### Scenario: 未提供 YAML 配置

- **GIVEN** 当前工作区没有可发现的 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用代码默认值和支持的环境变量
- **AND** SHALL NOT 因配置文件缺失而启动失败

#### Scenario: 非法 YAML 配置

- **GIVEN** 系统发现或显式指定了非法 `myagent.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 返回可读配置错误
- **AND** SHALL NOT 静默退回默认值

### Requirement: 配置优先级明确

系统 SHALL 使用 `CLI 显式参数 > 进程环境变量 > .env 加载值 > myagent.yaml > 默认值` 的优先级解析配置。CLI 入口 SHALL 用 `None` 表示用户未显式传参，避免默认 CLI 参数覆盖 YAML。

#### Scenario: CLI 参数覆盖 YAML

- **GIVEN** `myagent.yaml` 设置了默认 mode
- **AND** 用户显式传入 `--mode`
- **WHEN** CLI 构造运行配置
- **THEN** CLI 参数 SHALL 覆盖 YAML 默认 mode

#### Scenario: 环境变量覆盖 YAML

- **GIVEN** `myagent.yaml` 和支持的环境变量同时设置同一配置项
- **WHEN** 系统解析最终配置
- **THEN** 环境变量值 SHALL 覆盖 YAML 值

### Requirement: 配置文件发现受工作区边界约束

系统 SHALL 支持通过 `--config <path>` 显式指定配置文件；未显式指定时，系统 SHALL 从当前工作目录开始向上查找 `myagent.yaml`，并在 git repo 根目录停止。

#### Scenario: 显式配置文件路径

- **GIVEN** 用户传入 `--config <path>`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 只读取该显式配置文件
- **AND** 如果文件不存在或非法，系统 SHALL fail fast

#### Scenario: 子目录启动

- **GIVEN** 用户从仓库子目录启动 CLI
- **AND** 仓库根目录存在 `myagent.yaml`
- **WHEN** 系统发现配置文件
- **THEN** 系统 SHALL 读取仓库根目录的配置文件

### Requirement: 配置只在入口层解析

系统 SHALL 在 CLI、Web 和 benchmark 入口层解析配置，并将结果显式传入下层对象。底层 `AgentRunConfig()` SHALL NOT 隐式读取 YAML。

#### Scenario: 内部默认 run config

- **GIVEN** 当前工作区存在 `myagent.yaml`
- **WHEN** 内部代码直接构造默认 `AgentRunConfig`
- **THEN** 默认 mode SHALL 仍为代码默认值 `build`

#### Scenario: benchmark worktree 不重新发现配置

- **GIVEN** benchmark runner 为任务创建临时 worktree
- **WHEN** runner 构造 AgentLoop 和工具策略
- **THEN** 系统 SHALL 使用入口层已解析配置
- **AND** SHALL NOT 在任务 worktree 中重新发现 `myagent.yaml`
