# workspace-safety 规格 delta

## ADDED Requirements

### Requirement: 显式可写豁免（allowed_write_paths）

WorkspacePolicy SHALL 支持一份**显式可写豁免**（`allowed_write_paths`），语义是「deny 默认 + allow 精确覆盖」：默认值为空，未配置时路径拒绝行为 SHALL 与本能力引入前逐条一致。allow SHALL 只能把**已经在 workspace 内、且已被 deny 判定命中的路径**重新放行为可写；它 SHALL NOT 越过 workspace 边界，SHALL NOT 影响读判定。

allow 的判定 SHALL 是一个**共享谓词函数**，由**写路径**的判定器共同调用：`WorkspacePolicy.assert_write_allowed` 与命令护栏（`CommandGuard`）的写目标判定 SHALL 都调用它。共享的是**谓词函数**，SHALL NOT 是**调用点**——即 `is_denied` 与其读侧调用方 SHALL NOT 感知 allowlist。

#### Scenario: 列入豁免的路径在文件工具层变为可写

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 工具请求 `Write .env` 或 `Edit .env`
- **THEN** `assert_write_allowed` SHALL 放行该路径

#### Scenario: 列入豁免的裸名路径在 Bash 层同样可写

- **GIVEN** 同一份 `tools.allowed_write_paths` 已传入命令护栏
- **WHEN** Bash 请求执行把**裸名**（非嵌套）敏感路径当写目标的命令（`cp x .env`、`echo API_KEY=x >> .env`、`tee .env`、`dd of=.env`）
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

#### Scenario: 豁免不影响 tree-sitter / RepoMap 的跳过判定

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** RepoMap 或 SymbolSearch 扫描 workspace
- **THEN** 被豁免的路径 SHALL 仍被跳过（`repo_map` 的跳过判定走 `is_denied`，SHALL NOT 感知 allowlist）
- **AND** SHALL NOT 通过 tree-sitter 读取或返回该文件中的符号

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

### Requirement: 可写豁免不放宽结构性目录 deny 与命令 denylist

`allowed_write_paths` SHALL 只重开**文件级** deny。**结构性 deny** SHALL 由两条**可机械复算**的来源推导，SHALL NOT 依赖封闭清单：① `DEFAULT_DENIED_PATTERNS` 中含 `/` 的条目；② 路径中任一**路径段**命中目录类敏感名集合（`SENSITIVE_DOTDIRS`：`.git` / `.ssh` / `.aws` / `.gnupg` / `.kube` / `.docker` / `.netrc` / `.npmrc` / `.pypirc`）。其余 deny 条目 SHALL 视为文件级、可被豁免。命令 denylist（`DEFAULT_DENYLIST` / `_EXTRA_DENYLIST`）的语义 SHALL 不受本能力影响。

#### Scenario: 含 `/` 的 deny 条目是结构性 deny

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.ruff_cache/CACHEDIR.TAG']`
- **WHEN** 工具请求写该路径
- **THEN** 系统 SHALL 仍拒绝该操作（`.ruff_cache/**` 含 `/`，属结构性 deny）
- **AND** 判定 SHALL 由推导得出，SHALL NOT 依赖一份会随 deny 表增删而静默失配的封闭清单

#### Scenario: 目录类敏感名段是结构性 deny

- **GIVEN** 配置含 `tools.allowed_write_paths: ['.git/config']`
- **WHEN** 工具请求写 `.git/config`
- **THEN** 系统 SHALL 仍拒绝该操作（`config` 不是敏感名，但路径段 `.git` 命中 `SENSITIVE_DOTDIRS`）
- **AND** 该结论 SHALL NOT 依赖 deny 表里那条裸 `.git` 条目（它在同一通道里与 `*.pem` 等文件模式混在一起）

#### Scenario: 不含 `/` 的 deny 条目可被豁免

- **GIVEN** 配置含 `tools.allowed_write_paths: ['deploy.pem']`
- **WHEN** 工具请求写 `deploy.pem`
- **THEN** 该路径 SHALL 被放行（`*.pem` 是文件级 deny）
- **AND** 同配置下 `Write other.pem` SHALL 仍被拒绝

#### Scenario: 命令 denylist 不受影响

- **GIVEN** 任意 `tools.allowed_write_paths` 配置
- **WHEN** Bash 请求执行命中命令 denylist 的命令
- **THEN** 系统 SHALL 仍拒绝该命令

### Requirement: 可写豁免不使任何一层比引入前更宽

本能力 SHALL 是**增量**的：对未被 allow 命中的路径，文件工具层与命令护栏层的判定 SHALL 与引入本能力前逐条一致；对被 allow 命中的路径，**在命令护栏的「写目标判定面」上**判定 SHALL 与文件工具层同向变化（都从拒变放行）。「写目标判定面」SHALL 指 `CommandGuard` 中**消费写目标路径**的判定：写目标位置的目标判定、重定向目标判定、动态目标判定、`mv`/`cp` 目标判定、`tee` 目标判定与 `dd of=` 目标判定。它 SHALL NOT 包含：① 在命令 IR 判定之前执行的**整句 denylist 正则扫描**；② `mv`/`cp` 的**源位置**判定（读侧，SHALL NOT 被 allow 影响）；③ `rm` 的**逃逸**判定。系统 SHALL NOT 承诺「两层对任意路径恒同向」——两层判定面在引入本能力前就存在差异（命令护栏的写目标判定不消费 `DEFAULT_DENIED_PATTERNS`），该差异不在本能力的职责范围内；①的刻意例外见「Bash 层豁免覆盖面差异必须被记录」。

#### Scenario: 未列入的路径逐条不变

- **GIVEN** 一份 allowlist
- **WHEN** 对任一**未**被其命中的路径求值
- **THEN** 文件工具层与命令护栏层的判定 SHALL 与引入本能力前的对应结论一致（SHALL NOT 出现「被 allow 顺带放宽」的路径）

#### Scenario: 被命中的可挂钩路径两层同向变化

- **GIVEN** 一份 allowlist 与一个被它命中的路径
- **AND** 该路径在命令护栏侧的拒绝来源**属于可挂钩写目标判定面**（不是整句 denylist 正则扫描）
- **WHEN** 分别对该路径求值文件工具层的写判定与命令护栏的写目标判定
- **THEN** 两处 SHALL 都从拒变为放行（SHALL NOT 出现只放宽一层的形态）

#### Scenario: 被命中但落在刻意例外上的路径不与文件层同向

- **GIVEN** 一份 allowlist 与一个被它命中的**嵌套敏感路径**（如 `config/.env`），且该路径的 `cp` / `mv` 写目标**命中整句 denylist 正则扫描**
- **WHEN** 对同一路径求值文件工具层的写判定与命令护栏的 `cp` / `mv` 写目标判定
- **THEN** 文件工具层 SHALL 放行，而命令护栏 SHALL 仍判 `deny`（`last_reason` 为 `denylist`）
- **AND** 该形态 SHALL 被视为「Bash 层豁免覆盖面差异必须被记录」的**显式例外**，SHALL NOT 被读作本 Requirement 的违反
- **NOTE** 例外只适用**命中整句正则**的敏感名：同一 `config/` 下的非敏感目标（如 `config/notes.txt`）今天就是 `allow`，不受本例外约束——本 Scenario SHALL NOT 被读成「嵌套路径一律不与文件层同向」

### Requirement: Bash 层豁免覆盖面差异必须被记录

命令护栏的**整句 denylist 正则扫描**（在命令 IR 判定之前执行）SHALL 保持其现有语义，本能力 SHALL NOT 使其可被配置覆盖。其后果——**嵌套路径**（如 `config/.env`）的 Bash `cp` / `mv` 写目标 SHALL NOT 因 allow 命中而放行（`last_reason` 为 `denylist`），而同一路径的 `Write` / `Edit` / 重定向（`>>`）/ `tee` / `dd of=` / `install` SHALL 放行——SHALL 在规格、change 文档与用户可见的配置示例中**如实记录**，SHALL NOT 被表述为「该路径的写已全部放开」。

#### Scenario: 嵌套路径的 cp/mv 不被豁免放行

- **GIVEN** 配置含 `tools.allowed_write_paths: ['config/.env']`
- **WHEN** Bash 请求执行 `cp x config/.env` 或 `mv x config/.env`
- **THEN** 命令护栏 SHALL 仍判 `deny`，`last_reason` SHALL 为 `denylist`
- **AND** 该结论 SHALL 作为**规格行为**被回归测试锁定（不是缺陷，不得被「顺手修好」）

#### Scenario: 嵌套路径的非 cp/mv 写可被豁免放行

- **GIVEN** 同一份配置 `tools.allowed_write_paths: ['config/.env']`
- **WHEN** 工具请求 `Write config/.env`，或 Bash 执行 `echo K >> config/.env` / `tee config/.env` / `dd of=config/.env`
- **THEN** 这些写 SHALL 被放行

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
- **AND** 文件工具层与 Bash 命令护栏层 SHALL 都据此放行被列入的路径（Bash 侧的覆盖面差异见「Bash 层豁免覆盖面差异必须被记录」）

#### Scenario: tree-sitter 不绕过 read policy

- **GIVEN** denied path 下存在已注册语言文件
- **WHEN** RepoMap 或 SymbolSearch 扫描 workspace
- **THEN** 系统 SHALL 跳过该文件
- **AND** SHALL NOT 通过 tree-sitter 读取或返回该文件中的符号

#### Scenario: 允许常规验证和只读查看命令

- **GIVEN** Bash 请求执行 `pytest`、`uv run pytest`、`git diff`、`rg`、`cat` 或 `ls` 等允许命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令
