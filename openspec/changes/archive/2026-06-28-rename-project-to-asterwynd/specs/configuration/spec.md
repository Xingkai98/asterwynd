## MODIFIED Requirements

### Requirement: 支持结构化 YAML 配置

系统 SHALL 支持从 `asterwynd.yaml` 读取结构化非敏感配置。缺失配置文件时，系统 SHALL 使用环境变量和代码默认值继续启动；发现非法配置文件时，系统 SHALL fail fast 并返回可读错误。

#### Scenario: 未提供 YAML 配置

- **GIVEN** 当前工作区没有可发现的 `asterwynd.yaml`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用代码默认值和支持的环境变量
- **AND** SHALL NOT 因配置文件缺失而启动失败

#### Scenario: 环境变量使用正式前缀

- **GIVEN** 用户设置 `ASTERWYND_MODE` 或 `ASTERWYND_BENCHMARK_PARALLEL`
- **WHEN** 系统加载配置
- **THEN** 系统 SHALL 使用 `ASTERWYND_*` 环境变量覆盖对应 YAML 配置
- **AND** 系统 SHALL NOT 接受旧 `MYAGENT_*` 前缀作为兼容入口

### Requirement: 配置文件发现受工作区边界约束

系统 SHALL 支持通过 `--config <path>` 显式指定配置文件；未显式指定时，系统 SHALL 从当前工作目录开始向上查找 `asterwynd.yaml`，并在 git repo 根目录停止。

#### Scenario: 子目录启动

- **GIVEN** 用户从仓库子目录启动 CLI
- **AND** 仓库根目录存在 `asterwynd.yaml`
- **WHEN** 系统发现配置文件
- **THEN** 系统 SHALL 读取仓库根目录的配置文件
- **AND** 系统 SHALL NOT 继续查找旧 `myagent.yaml`
