# workspace-safety 规格 delta

## ADDED Requirements

### Requirement: 显式可写豁免（allowed_write_paths）

WorkspacePolicy SHALL 支持一份**显式可写豁免**（`allowed_write_paths`），语义是「deny 默认 + allow 精确覆盖」：默认值为空，未配置时路径拒绝行为 SHALL 与本能力引入前逐条一致。allow SHALL 只能把**已经在 workspace 内、且已被 deny 判定命中的路径**重新放行为可写；它 SHALL NOT 越过 workspace 边界，SHALL NOT 影响读判定。

同一份 `allowed_write_paths` SHALL 同时作用于**文件工具层**（`WorkspacePolicy.assert_write_allowed`）与 **Bash 命令护栏层**（`CommandGuard` 的写目标判定）。两层 SHALL 消费同一份数据与**同一个判定谓词**，SHALL NOT 各自实现一份路径匹配——否则同一路径会因使用哪个工具而得到相反结论，这正是本能力引入前 `.env.local` 两层判定漂移（`bash-command-guard-redesign` 设计 D12）要避免的形态。

#### Scenario: 列入豁免的路径在文件工具层变为可写

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 工具请求 `Write .env` 或 `Edit .env`
- **THEN** `assert_write_allowed` SHALL 放行该路径

#### Scenario: 列入豁免的路径在 Bash 层同样可写

- **GIVEN** 同一份 `tools.allowed_write_paths: ['.env']` 已传入命令护栏
- **WHEN** Bash 请求执行 `cp x .env`、`echo API_KEY=x >> .env`、`tee .env` 或 `dd of=.env`
- **THEN** 命令护栏 SHALL 判 `allow`（SHALL NOT 以 `mv_cp_dest` / `protected_redirect` / `tee_target` / `dd_target` 拒）

#### Scenario: 未列入豁免的路径仍然拒绝（否定用例）

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 工具或 Bash 试图写 `src/.env`、`.env.local` 或 `.env.production`
- **THEN** 系统 SHALL 拒绝该操作，行为与未配置豁免时一致

#### Scenario: 豁免不越过 workspace 边界

- **GIVEN** 配置含一条指向 workspace 之外的路径
- **WHEN** 系统解析 `tools.allowed_write_paths`
- **THEN** 配置解析 SHALL fail fast 并返回可读错误
- **AND** 即便豁免条目以其他形式指向 workspace 之外，`assert_within_workspace` 的边界检查 SHALL 先于任何 allow 判定生效

#### Scenario: 豁免不影响读判定

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 工具请求 `Read .env`
- **THEN** `assert_read_allowed` SHALL 仍拒绝该操作

#### Scenario: 两层结论同向

- **GIVEN** 同一份 allowlist 与同一组 workspace 内路径
- **WHEN** 分别对文件工具层的 `assert_write_allowed` 与 Bash 层的写目标判定求值
- **THEN** 两者对每一个路径 SHALL 给出同向结论（同时放行或同时拒绝）

### Requirement: 可写豁免的粒度与配置合法性

`allowed_write_paths` 的每一项 SHALL 是 workspace 相对路径的**字面值**（精确匹配）。配置解析 SHALL 对以下条目 fail fast 并返回可读错误，SHALL NOT 宽容接受：含 glob 元字符（`*`、`?`、`[`、`]`）、绝对路径、含 `..` 路径段、以及以 `/` 结尾的目录形式。

#### Scenario: 精确路径生效

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env', 'config/.env']`
- **WHEN** 工具写 `config/.env`
- **THEN** 该路径 SHALL 被放行

#### Scenario: glob 条目 fail fast

- **GIVEN** 配置含 `tools.allowed_write_paths: ['**/*']`
- **WHEN** 系统解析配置
- **THEN** 系统 SHALL fail fast 并返回可读错误
- **AND** SHALL NOT 把该条解释成「匹配一切的可写授权」（一个匹配一切的模式会连 `.git/config` 一起打开）

#### Scenario: 其他非法条目 fail fast

- **GIVEN** 配置含绝对路径、含 `..` 段的路径或以 `/` 结尾的目录形式
- **WHEN** 系统解析配置
- **THEN** 系统 SHALL 逐条 fail fast 并返回可读错误

### Requirement: 可写豁免不放宽结构性 deny 与命令 denylist

`allowed_write_paths` SHALL 只重开**文件级** deny（`.env` 族等敏感点文件名、`*.pem` / `*.key` 等文件模式）。它 SHALL NOT 重开仓库与工具管理的**结构性目录** deny（`.git/**`、`.venv/**`、`node_modules/**`、`__pycache__/**`、`benchmarks/runs/**`、`.asterwynd/worktrees/**`）。命令 denylist（`DEFAULT_DENYLIST` / `_EXTRA_DENYLIST`）的语义 SHALL 不受本能力影响。

#### Scenario: 结构性目录 deny 不可被豁免

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.git/config']`
- **WHEN** 工具请求写 `.git/config`
- **THEN** 系统 SHALL 仍拒绝该操作（`.git/**` 是结构性目录 deny，不被文件级豁免覆盖）

#### Scenario: 命令 denylist 不受影响

- **GIVEN** 任意 `tools.allowed_write_paths` 配置
- **WHEN** Bash 请求执行命中命令 denylist 的命令
- **THEN** 系统 SHALL 仍拒绝该命令

## MODIFIED Requirements

### Requirement: 工作区策略支持配置扩展

WorkspacePolicy SHALL 保留内置 denied patterns 和 command denylist，并允许入口层通过统一配置追加项目级 command denylist 与项目级**显式可写豁免**（`tools.allowed_write_paths`）。ListFiles 和 Find SHALL 保留内置 ignore rules，并允许入口层通过统一配置追加项目级 ignore patterns。三个配置项 SHALL 由 CLI、Web 与 benchmark 三个入口层一致地传入，SHALL NOT 出现某个入口漏传而使豁免静默失效。

#### Scenario: YAML command denylist 扩展

- **GIVEN** 统一配置包含 `tools.command_denylist`
- **WHEN** Bash 工具校验命令
- **THEN** 系统 SHALL 同时应用内置 denylist 和配置扩展

#### Scenario: YAML ignore patterns 扩展

- **GIVEN** 统一配置包含 `tools.ignore_patterns`
- **WHEN** ListFiles 或 Find 枚举目录
- **THEN** 系统 SHALL 同时应用内置 ignore rules 和配置扩展

#### Scenario: YAML allowed_write_paths 扩展

- **GIVEN** 统一配置包含 `tools.allowed_write_paths`
- **WHEN** 任一入口层（CLI / Web / benchmark）构造工具策略
- **THEN** 系统 SHALL 把该列表传给同一个 WorkspacePolicy 实例
- **AND** 文件工具层与 Bash 命令护栏层 SHALL 都据此放行被列入的路径

#### Scenario: tree-sitter 不绕过 read policy

- **GIVEN** denied path 下存在已注册语言文件
- **WHEN** RepoMap 或 SymbolSearch 扫描 workspace
- **THEN** 系统 SHALL 跳过该文件
- **AND** SHALL NOT 通过 tree-sitter 读取或返回该文件中的符号

#### Scenario: 允许常规验证和只读查看命令

- **GIVEN** Bash 请求执行 `pytest`、`uv run pytest`、`git diff`、`rg`、`cat` 或 `ls` 等允许命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令
