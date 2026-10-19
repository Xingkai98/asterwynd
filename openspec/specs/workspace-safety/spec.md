# workspace-safety 规格

## Purpose

定义 WorkspacePolicy 提供的路径、敏感文件、命令执行和 git diff 安全边界。当前实现位于 `agent/workspace_policy.py`；Read、Write、Edit、Grep、ListFiles、Find、InspectGitDiff 和 Bash 均通过工具集合注入 workspace policy。
## Requirements
### Requirement: WorkspacePolicy 路径必须限制在 workspace 内

WorkspacePolicy SHALL 解析路径并阻止越过 workspace root 的读写访问。读权限和写权限校验 SHALL 都执行 workspace root 边界检查。

#### Scenario: 读路径逃逸

- **GIVEN** 工具请求读取 workspace 外路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

#### Scenario: 写路径逃逸

- **GIVEN** 工具请求写入 workspace 外路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝访问
- **AND** 返回权限错误

### Requirement: 敏感文件读写默认拒绝

WorkspacePolicy SHALL 在面向 agent tool 的读写校验中拒绝匹配 denied patterns 的路径，例如本地环境变量、私密配置、版本控制内部目录、虚拟环境、依赖目录和生成目录。

#### Scenario: 写入 `.env`

- **GIVEN** 工具请求写入被 denied pattern 命中的路径
- **WHEN** policy 校验写入权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 读取 `.env`

- **GIVEN** 工具请求读取被 denied pattern 命中的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: 普通 agent tool 不绕过 read policy

- **GIVEN** 普通 agent tool 请求读取 read policy 拒绝的路径
- **WHEN** policy 校验读取权限
- **THEN** 系统 SHALL 拒绝该操作
- **AND** SHALL NOT 为普通 agent tool 提供隐式绕过

### Requirement: 命令执行受 denylist 和 allowlist 控制

WorkspacePolicy SHALL 在 Bash 执行前检查命令。命令检查 SHALL 先应用 denylist，再应用 allowlist；命中 denylist 的命令 MUST 被拒绝，即使该命令同时匹配 allowlist。allowlist SHALL 只包含验证、只读查看和明确低风险的开发命令，不得用宽泛前缀放行任意脚本执行或敏感文件搬运。

#### Scenario: 命令命中 denylist

- **GIVEN** Bash 请求执行危险命令
- **WHEN** `assert_command_allowed` 发现命中 denylist
- **THEN** 系统 SHALL 抛出权限错误

#### Scenario: denylist 覆盖 allowlist

- **GIVEN** Bash 请求执行同时匹配 allowlist 前缀和 denylist 模式的命令
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

#### Scenario: 拒绝任意 Python 代码执行

- **GIVEN** Bash 请求执行 `python -c` 或 `python3 -c`
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

#### Scenario: 允许 Python pytest 验证命令

- **GIVEN** Bash 请求执行 `python -m pytest` 或 `python3 -m pytest`
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 允许该命令

#### Scenario: 拒绝敏感文件搬运

- **GIVEN** Bash 请求通过 `cp` 或 `mv` 读取系统敏感路径或移动 workspace denied pattern 文件
- **WHEN** `assert_command_allowed` 检查命令
- **THEN** 系统 SHALL 拒绝该命令

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

### Requirement: git diff 快照在 workspace root 执行

WorkspacePolicy SHALL 在 workspace root 下执行 git diff，并返回 diff 输出、diff stat 或无变更提示。

#### Scenario: 获取 diff stat

- **GIVEN** 调用方请求 stat 模式
- **WHEN** policy 执行 diff 快照
- **THEN** 系统 SHALL 运行 `git diff --stat`
- **AND** 返回标准输出或错误输出

### Requirement: WorkspacePolicy remains an execution boundary

工具 capability 和 mode profile SHALL 决定 tool 是否对 LLM 可见以及是否允许执行；WorkspacePolicy SHALL 继续作为路径、敏感文件、命令和 workspace 边界的执行前强制校验，不得被 capability metadata 绕过。

#### Scenario: capability 允许但 workspace policy 拒绝

- **GIVEN** 当前 mode profile 允许某个 workspace read tool
- **AND** 该 tool 请求读取 denied path
- **WHEN** WorkspacePolicy 校验该路径
- **THEN** 系统 SHALL 拒绝该操作

#### Scenario: capability 允许但命令 policy 拒绝

- **GIVEN** 当前 mode profile 允许某个命令执行工具
- **AND** 该 tool 请求执行命中 command denylist 的命令
- **WHEN** WorkspacePolicy 校验该命令
- **THEN** 系统 SHALL 拒绝该操作

### Requirement: MCP actions 必须声明权限边界

MCP-backed tools、prompt 读取和 resource 读取 SHALL 声明 capability / risk / origin 权限元数据，并受 agent mode policy 约束。未显式配置的 MCP action SHALL 默认为 `origin=mcp`、`capabilities=[external_side_effect]`、`risk_level=high`；MCP server 自身 annotation SHALL NOT 作为最终权限判定依据。

#### Scenario: MCP tool 被 mode 禁止

- **GIVEN** 当前 mode 不允许 MCP action 所需 capability
- **WHEN** MCP server 暴露该 tool
- **THEN** 系统 SHALL 不向 LLM 暴露该工具
- **AND** 直接执行该工具 SHALL 返回权限错误

#### Scenario: MCP prompt/resource 读取需要审批

- **GIVEN** 当前 mode 对某个 MCP prompt/resource 读取要求审批
- **WHEN** 用户通过 slash command 读取该 prompt/resource 且未批准
- **THEN** 系统 SHALL 返回 approval required 文本
- **AND** SHALL NOT 调用远端 MCP server

#### Scenario: 本地配置降低 MCP 读取权限

- **GIVEN** 本地配置将某个 MCP server 的 resource 读取声明为 `network_read` + `low`
- **WHEN** 当前 mode 允许该 capability 和 risk
- **THEN** 系统 SHALL 允许读取该 resource

### Requirement: browser artifacts 存储受 workspace policy 约束

Browser screenshots、HTML snapshots 和日志 artifacts SHALL 保存到 workspace policy 允许的目录（`<workspace_root>/.asterwynd/browser-artifacts/`），写入前 SHALL 通过 `WorkspacePolicy.assert_write_allowed()` 校验。

#### Scenario: browser artifact 路径被拒绝

- **GIVEN** browser tool 请求保存 artifact 到 denied path
- **WHEN** WorkspacePolicy 校验写入路径
- **THEN** 系统 SHALL 拒绝保存

### Requirement: ExecutionBackend 可插拔沙箱

沙箱 SHALL 将命令执行抽象为 `ExecutionBackend` 接口，提供可插拔后端：`ProcessBackend`（subprocess，默认）与 `DockerBackend`（`docker run --rm --network none` 容器隔离）。后端 SHALL 返回统一 `SandboxResult`，SHALL 可通过 config 选择。

#### Scenario: Docker 隔离执行

- **GIVEN** 通过 docker 后端执行命令
- **WHEN** 后端在容器内运行
- **THEN** 命令 SHALL 在 `--network none` 下运行
- **AND** 只挂载 workspace
- **AND** 运行后容器 SHALL 被移除

#### Scenario: 后端切换

- **GIVEN** config 选择 `backend: docker`
- **WHEN** 构建执行后端
- **THEN** 使用 `DockerBackend`
- **AND** `backend: process` 选择 `ProcessBackend`

#### Scenario: config 后端对前台 Bash 生效

- **GIVEN** `sandbox.backend: docker` 配置
- **WHEN** 构建 agent 工具注册表
- **THEN** Bash 工具的执行后端 SHALL 是配置的 `DockerBackend`（main/web/benchmark 入口一致，不仅限后台任务）

#### Scenario: 后端不可用 fail-fast

- **GIVEN** `sandbox.backend: docker` 配置但 Docker daemon 不可达
- **WHEN** 构建 agent core
- **THEN** 启动 SHALL 以明确错误失败（不静默回退到 process）

### Requirement: 命令护栏（单一解析管线 + 能力范围声明）

命令护栏 SHALL 采用单一解析管线处理 shell 命令：`source → parse → command IR → policy evaluators → decision`。护栏 SHALL 只解析一次并产出结构化中间表示（IR），SHALL 由所有判定器消费同一 IR；**同一语义 SHALL NOT 存在两个实现**（判定器 SHALL NOT 绕过 IR 重新解析原始命令文本或自行切分 token）。IR SHALL 至少携带：命令段与各行内命令的 argv、**写目标**、重定向（文件描述符、操作符、目标）、环境变量赋值、动态词标记、解析错误标记（含零宽 `is_missing`）、不支持的语法节点、**heredoc 绑定关系（分隔符、正文节点、绑定的文件描述符与消费方命令）**、源码位置。

**写目标** SHALL 由 IR 显式给出，SHALL NOT 假定为 argv 的最后一个元素——`cp -t <dir> <src>`、`mv --target-directory=<dir> <src>`、`dd of=<file>` 的目标经选项传递，SHALL 同样被判定。

护栏 SHALL 拒绝危险命令模式（rm 递归+强制目标越界、重定向到受保护路径或敏感点目录、管道到 shell、任意代码执行解释器、敏感文件外传），SHALL 默认放行**成功解析且未命中任何规则**的未知命令（护栏不是边界）。

护栏的判定结果 SHALL 是三态：`allow` / `deny` / `ask`。`ask` SHALL 被路由到审批层（`agent/approval.py` 的 `ApprovalHandler`），SHALL NOT 被护栏自行解释为放行。`ask` 在各运行时的实际行为 SHALL 被如实描述：交互 CLI 弹窗询问；非交互 / TTY 不可用时 SHALL 由 `CliApprovalHandler` 判 `UNAVAILABLE`（即拒绝）；Web 弹卡片；benchmark 运行器不注入 handler，恒 `FailClosedApprovalHandler`（即拒绝）。`allow` SHALL NOT 表示「安全」，SHALL 只表示「护栏没有理由阻止」；护栏 SHALL NOT 因为判定 `allow` 而绕过执行后端。

受保护路径与工作区边界的判定 SHALL 按**路径段**比较（`path == prefix` 或 `path` 以 `prefix + "/"` 开头），SHALL NOT 使用裸字符串前缀比较——裸前缀会把 `/various.txt` 当作 `/var` 下的路径、把 `/tmp/ws-evil` 当作工作区 `/tmp/ws` 内的路径。判定前 SHALL 先对路径做规范化（解析 `..` 与 `.` 段），使 `rm -rf /tmp/ws/../etc`（工作区为 `/tmp/ws`）SHALL NOT 因字面前缀匹配而被判为工作区内。**工作区边界判定** SHALL 对 POSIX 绝对路径（`/` 开头）进一步解析符号链接（realpath 语义，且 `..` SHALL 在符号链接解析之后折叠），使工作区经符号链接表示时，工作区与命令目标使用同一规范表示——`rm -rf <link>/build`（工作区为 `<link> → <real>`）SHALL 被判为工作区内；**相对路径** SHALL 保持词法规范化（护栏不掌握命令 cwd）。**受保护路径判定** SHALL 保持既有词法规范化，不受上述 realpath 语义影响。工作区边界判定中绝对路径无法规范化（如符号链接循环）时 SHALL fail-closed（判为不在工作区内），SHALL NOT 退回字面比较而放行；「目标尚不存在」SHALL NOT 被当作解析失败——解析 SHALL 在目标不存在时按非严格 realpath 解析（不存在的尾部按词法追加），仅在解析器报告循环等错误时 fail-closed。该判定 SHALL 独立于解析器实现：解析器只确定「参数是哪个」，路径规范化与分量边界比较 SHALL 在执行路径上完成；上述 realpath 语义 SHALL 同时用于工作区包含判定与写白名单的 workspace 相对路径计算。Windows 盘符绝对路径沿用既有判定口径，不进入该 POSIX 包含判定。

**重定向目标**与 **mv/cp 目标**的判定 SHALL 豁免设备文件 `/dev/null`、`/dev/stdout`、`/dev/stderr`——它们是黑洞设备与进程标准流的别名，不属于「受保护的系统目录内容」语义。该豁免 SHALL NOT 扩展到 rm/chmod/curl-wget 的目标判定（`rm -rf /dev/null` SHALL 保持拒绝）；其余 `/dev/*` 目标 SHALL 保持拒绝。**重定向目标 SHALL 与 mv/cp 目标使用同一套敏感点目录判定**——`echo X > .env`、`echo X >> .env`、`cat payload > ~/.ssh/authorized_keys` SHALL 被拒绝（它们当前只比受保护系统目录、不覆盖敏感点目录）。

mv/cp 目标命中敏感点目录（`.git`/`.ssh`/`.env`/`.aws`/`.gnupg`/`.kube`/`.docker`/`.netrc`/`.npmrc`/`.pypirc`）SHALL 被拒绝。目标参数 SHALL 从 IR 的写目标读取，SHALL NOT 因解析器对 brace 展开、反斜杠转义、glob 或字符类的处理而丢失或被切碎——`cp x ~/.{ssh}/f` SHALL NOT 因目标被切成多段而放行。判定 SHALL 覆盖**互补**通道并如实描述各自覆盖面：**argv 通道**在 `mv`/`cp` 居命令段首时按路径段比较，覆盖裸形态（`.env`）与嵌套形态（`src/.git/hooks/x`），并 SHALL NOT 误判 `.gitignore`、`.env.example`、`.github/` 这类普通文件/目录；**混淆归一化通道**对目标做归一化（去反斜杠转义、展开字符类与 brace、以 `fnmatch` 反向匹配判定敏感名能否被该模式匹配）后判定，SHALL NOT 因此误报字面名（`.env.example` SHALL 保持放行）。

**敏感 dot 名 SHALL 由一份共享谓词定义，SHALL NOT 存在多份互不相关的定义**（对齐 D9「同一语义 SHALL NOT 存在两个实现」）。当前「什么算敏感 dot 名」由三处各写各的——`workspace_policy` 的 `DEFAULT_DENIED_PATTERNS`（glob，读/写共用 `is_denied`）、同文件的两条**源位置锚定**正则、`command_guard` 的 `_SENSITIVE_DOTDIRS`/`_SENSITIVE_DOTFILES`（精确相等集合）——三者对同一文件的判定互相矛盾。该谓词 SHALL 为**代码谓词**，SHALL NOT 用 glob 表达（实测：Python `fnmatch` 不支持 bash extglob，`fnmatch('.env.local', ".env.!(example|…)")` 返回 False，写成 glob 会**静默放开两边**）。

**`.env` 系列 SHALL 按「凭据变体」与「模板」分流**：

- **凭据变体**（`.env` 本体及任何**非模板**的 `.env.<后缀...>`，含 `.env.local` / `.env.production` / `.env.development` / `.env.test` / `.env.staging` / `.env.secret` / `.env.keys`）SHALL 被拒绝——读、写、以及 `mv`/`cp`/`dd of=`/`tee`/重定向的目标位。当前实现**过窄**：`command_guard` 的敏感点集合是精确相等，`.env.local` 判定失效；且 `BashTool` 只经文本通道与护栏、不经 `assert_write_allowed`——故 `cp src.txt .env.local` 今天真的执行并写入。
- **模板**（`.env.example` / `.env.sample` / `.env.template` / `.env.dist` / `.env.defaults` / `.env.tpl`）SHALL 被豁免——读与写均放行。
- **判据 SHALL 为「`.env` 之后的每一个 `.` 分段都是模板词 ⇒ 模板；有任何一段不是 ⇒ 凭据」**。故 `.env.example.local` / `.env.local.example` / `.env.production.sample` / `.env.j2` / `.env.example.bak` SHALL 仍被判为凭据。
- 非 `.env` 前缀的名字（`.envrc` / `.environment` / `app.env` / `config.env` / `my.env` / `.env2` / `.env-file`）SHALL NOT 落入该判定，SHALL 保持放行。

rm 递归+强制的目标 SHALL NOT 等于工作区根（`rm -rf <workspace_root>` SHALL 拒绝），且 SHALL NOT 位于工作区之外。

argv 语义检查 SHALL 覆盖**命令行的每一段**，SHALL NOT 只检查首段——命令分隔符（`&&`/`||`/`;`/`|`/`&`/换行）与分组符号（`(`/`)`/`{`/`}`）之后、以及 shell 关键字（`then`/`do`/`else`/`fi`/`done`/`time`/`exec`/`eval` 等）之后的命令 SHALL 同样受检。`<shell> -c <string>` 形态（含 `-lc`/`-ic` 等短选项簇、`env`/`command`/`nohup` 前缀及其选项、重复 `-c`）SHALL 对每个 payload 递归执行同样的校验；递归 SHALL 有深度上界，超出上界时 SHALL 停止解包而 SHALL NOT 无界递归。shell 关键字与 wrapper 前缀的剥离 SHALL 发生在 IR 构造阶段，SHALL NOT 在多个判定器上分别实现。`<shell> -c SCRIPT $0 $1` 的位置参数 SHALL NOT 掩盖 SCRIPT 本身；`env -S <string>` / `env --split-string <string>` 的值 SHALL 被当作待执行的命令检查。

**字符串型命令载荷** SHALL 统一处理：`<shell> -c <string>` 的 payload、`eval <string>` 的参数、`env -S <string>` 的值 SHALL 走同一套「作为命令行递归判定」的机制。`eval 'cp x .env'`（引号载荷）SHALL NOT 因载荷被合成单个 token 而放行——当前实现中它放行而 `eval cp x .env` 被拒，二者语义相同、判定 SHALL 一致。

**launcher 前缀** SHALL 按「剥离到不动点」处理：wrapper（`env`/`command`/`nohup`）与 launcher（`nice`/`flock`/`chroot`/`setsid`/`timeout`/`stdbuf`/`taskset`/`xargs`/`busybox` 等）的剥离 SHALL 交替进行直到不动点，SHALL NOT 在遇到第一个未识别前缀时停止——`nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env` SHALL 被判定。剥离后 SHALL 对真实命令执行同样的 checks。

**未识别前缀的处置 SHALL 按「限定 ask」而非「一律 ask」**（[Q4] 用户拍板）：仅当该未识别前导 token **之后（滑窗内）跟着护栏真正会判的命令**（`rm`/`mv`/`cp`/`chmod`/`curl`/`wget`/`dd`/`tee`）时 SHALL 返回 `ask`；**纯粹的未识别程序 SHALL 保持 default-allow**（`my-custom-tool --flag` / `terraform plan` / `./scripts/run.sh` 仍放行）。依据：实测「未知即 ask」会把 **63%（37/59）** 今天 allow 的正常命令拉去审批，而 `ask` 在无 UI 环境等于 deny，等于把所有未识别程序硬拒；「限定 ask」在同一语料上噪音 **0/59**，30 条 launcher 攻击族抓取 29/30。白名单只用于**减噪**，安全属性由「未识别 ⇒ ask」承担——白名单被投毒（程序名叫 `git`）的后果只是从 ask 降为 allow，与今天 default-allow 持平，不构成回归。

**剥离到不动点 SHALL 同时作用于 `<shell> -c <string>` 的 payload 通道**，SHALL NOT 只在 argv 通道剥离：当前 `_shell_dash_c_payloads` 的 wrapper 剥离只认 `env`/`command`/`nohup`/shell 关键字，故 `doas sh -c 'cp x .env'`、`nice bash -c 'cp x .env'`、`nohup setsid sh -c 'cp x .env'`、`unshare -m bash -c 'cp x .env'` 今天全被放行。

heredoc 的正文 SHALL 按**绑定关系**分流，SHALL NOT 一刀切：当 heredoc / herestring 绑定到**解释器**（`sh`/`bash`/`zsh`/`ksh`/`dash`/`python`/`python3`/`node`/`perl`/`ruby`/`php`/`awk` 及其 `-s` / `-` 变体）的 stdin 时，其正文**就是待执行的代码**，SHALL 按命令行递归判定——`bash <<EOF` + 正文 + `EOF` SHALL 被拒绝。当 heredoc 绑定到**非解释器**命令时，正文是 stdin 数据，SHALL NOT 被当作命令判定——`cat <<'EOF'` + 正文含危险字样 + `EOF` SHALL 被放行。重定向到受保护路径的目标 SHALL 仍被判定（`cat <<EOF > /etc/passwd` SHALL 拒绝）。

**命令替换与进程替换**（`$(...)`、反引号、`<( )`、`>( )`）SHALL 无论出现在命令行的哪个位置都对其内部命令递归判定，SHALL NOT 因为「不在写目标位置」而放行——`echo $(rm -rf /tmp/x)`、`` echo `rm -rf /tmp/x` `` SHALL 被拒绝（参数位的命令替换照样执行代码）。

**写目标位置的动态词**（`$VAR` / glob / brace 展开出现在目标位置，含选项携带的目标）SHALL 归一化后判定：命中敏感名或受保护路径 ⇒ 拒绝；否则 ⇒ 要求审批（`ask`）。**非目标位置**的动态词（如 `echo "$VAR"`）SHALL 放行。

#### Scenario: rm 目标越界拒绝

- **GIVEN** `rm -rf /` 或 `rm -fr /` 或 `rm -rf $HOME`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（flag 归一化捕获重排/拆分）

#### Scenario: rm 目标前缀碰撞不得绕过工作区边界

- **GIVEN** 工作区为 `/tmp/ws`，命令为 `rm -rf /tmp/ws-evil`（或 `/tmp/wsX`、`/tmp/ws-evil/sub`）
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（`/tmp/ws-evil` 不在工作区 `/tmp/ws` 之下，前缀相同不构成包含关系）

#### Scenario: rm 的 `..` 穿越不得绕过工作区边界

- **GIVEN** 工作区为 `/tmp/ws`，命令为 `rm -rf /tmp/ws/../etc`（或 `/tmp/ws/../../etc`）
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（规范化后为 `/tmp/etc`，落在工作区之外）

#### Scenario: rm 工作区根本身拒绝

- **GIVEN** 工作区为 `/tmp/ws`，命令为 `rm -rf /tmp/ws`（或 `rm -rf /tmp/ws/`）
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（删除工作区根本身等同越界破坏）

#### Scenario: 符号链接工作区内 rm 放行

- **GIVEN** 工作区为 `<link> → <real>`（符号链接），命令为 `rm -rf <link>/build` 或 `rm -rf <real>/build`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（工作区与目标按 realpath 归一后使用同一规范表示；两种字面表示均在工作区内）

#### Scenario: 工作区内符号链接不得成为越界通道

- **GIVEN** 工作区内存在符号链接 `escape → <outside>`，命令为 `rm -rf <workspace>/escape` 或 `rm -rf <workspace>/escape/`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（目标的 realpath 落在工作区之外；这是保守过度判定——无尾斜杠时 `rm` 实际只删除链接本身，误报代价在 change design 的 Risks 登记）
- **AND** 前缀碰撞（`<workspace>-evil`）、`..` 穿越与删除工作区根本身 SHALL 继续保持拒绝

#### Scenario: 符号链接后的 `..` 按真实解析路径判定

- **GIVEN** 工作区内存在 `escape → <outside>`，命令为 `rm -rf <workspace>/escape/../victim`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（POSIX realpath 先跟随 `escape`、再折叠 `..`，目标为工作区外的 `<outside 的父>/victim`；SHALL NOT 先按词法把 `escape/..` 折叠回工作区内）

#### Scenario: 无法解析的绝对路径 fail-closed

- **GIVEN** 工作区为绝对路径 `<workspace>`，工作区内存在符号链接循环 `<workspace>/loop → <workspace>/loop`，命令目标为绝对路径 `<workspace>/loop/x`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（绝对路径解析报告循环等错误时判为不在工作区内；SHALL NOT 退回字面比较而放行，也 SHALL NOT 因目标不存在而误判为解析失败）

#### Scenario: 重定向到受保护路径拒绝

- **GIVEN** `echo x > /etc/passwd`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝

#### Scenario: 重定向到敏感点目录拒绝

- **GIVEN** `echo SECRET=1 > .env`、`echo X >> .env`、`cat payload > ~/.ssh/authorized_keys`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（重定向目标与 mv/cp 目标使用同一套敏感点目录判定）
- **AND** `cat payload > ~/.ssh/authorized_keys` 是持久化后门写入，默认执行后端不提供文件系统边界，SHALL NOT 依赖后端兜住

#### Scenario: 设备文件重定向放行

- **GIVEN** `ls -la 2>/dev/null` 或 `cmd > /dev/null 2>&1` 或 `python3 x.py > /dev/null` 或 `git log 2>/dev/null | head`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（`/dev/null` 是黑洞设备，不构成对受保护路径的写入）

#### Scenario: 前缀相似的普通路径不得被误判为受保护路径

- **GIVEN** `echo x > /various.txt` 或 `echo x > /rooted.log` 或 `echo x > /bootstrap.log` 或 `echo x > /etcetera.conf`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（这些路径与 `/var`、`/root`、`/boot`、`/etc` 无包含关系，仅前缀字符串相同）

#### Scenario: 敏感点目录按段判定

- **GIVEN** `cp x .gitignore` / `cp x .env.example` / `cp x .github/w.yml`（普通文件与目录）与 `cp x .env` / `cp x src/.git/hooks/pre-commit` / `cp x sub/.env/secrets`（敏感点目录，裸形态与嵌套形态）
- **WHEN** 命令护栏校验
- **THEN** 前者 SHALL 放行、后者 SHALL 拒绝

#### Scenario: `.env` 凭据变体不得被放行（本 change 新增范围）

- **GIVEN** `cp x .env.local`、`tee .env.production`、`dd of=.env.development`、`echo X >> .env.test`、`mv .env.staging /tmp/x`（凭据变体）
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝
- **AND** 这些命令**当前**均被放行（`_dest_is_sensitive` 按 basename 精确相等、字面通道否定前瞻显式排除 `.env.` 后续字符），且 `cp src.txt .env.local` 经 `BashTool` **真的执行并写入**——SHALL NOT 因「文件工具已拒绝」而假设护栏覆盖了它（实测 `BashTool.execute` 只经文本通道与护栏，不经 `assert_write_allowed`）

#### Scenario: `.env` 模板读写豁免

- **GIVEN** `cat .env.example`（读）、`cp x .env.example`（写）、`cp .env.example /tmp/backup.txt`（源为模板）
- **WHEN** 命令护栏与文件工具校验
- **THEN** SHALL 放行（模板按规范进 git、正文对任何有仓库读权限者可见；护栏拦不住「已提交的真值」，那是 secret scanning 的职责）
- **AND** 现状是 agent **读不到模板、只能猜该项目该配哪些环境变量**，属可发现性反模式

#### Scenario: 模板判据的边界不得被绕过

- **GIVEN** `.env.example`（模板）与 `.env.example.local` / `.env.local.example` / `.env.production.sample` / `.env.j2` / `.env.example.bak`（复合后缀，含非模板词）
- **WHEN** 敏感 dot 名谓词判定
- **THEN** 前者 SHALL 豁免（读写放行），后者 SHALL 全部判为凭据（deny）
- **AND** 判据是「`.env` 之后的每一个 `.` 分段都是模板词」，SHALL NOT 用「后缀出现在某个模板清单里」这类可被 `.env.example.local` 绕过的写法

#### Scenario: 非 `.env` 前缀的名字不受影响

- **GIVEN** `.envrc` / `.environment` / `app.env` / `config.env` / `my.env` / `.env2` / `.env-file` / `environment`
- **WHEN** 敏感 dot 名谓词判定
- **THEN** SHALL NOT 落入 `.env.<后缀>` 判定，SHALL 保持放行（收窄不得引入误报）

#### Scenario: 目标参数不得被解析层销毁

- **GIVEN** `cp x ~/.{ssh}/f`（brace 展开）、`cp x ~/.ss\h/id_rsa`（反斜杠转义）、`cp x ~/.s[h]h/f`（字符类）、`cp x ~/.ss*/f`（glob）
- **WHEN** 命令护栏校验
- **THEN** 这些命令 SHALL 被拒绝或要求审批（目标归一化后命中敏感名，SHALL NOT 因目标被切碎而放行）
- **AND** 同时 `cp x .env.example`、`cp x .gitignore`、`cp x .github/w.yml` SHALL 保持放行（归一化不得引入误报）

#### Scenario: 写目标经选项传递不得绕过

- **GIVEN** `cp -t .env x`、`mv --target-directory=.env x`、`dd of=.env`、`dd of=~/.ssh/authorized_keys`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝或要求审批（写目标由 IR 显式给出，SHALL NOT 假定为 argv 的最后一个元素）

#### Scenario: launcher 前缀不得掩盖真实命令

- **GIVEN** `nice cp x .env`、`flock /tmp/l cp x .env`、`doas cp x .env`、`unshare -m cp x .env`、`script -q /dev/null cp x .env`、`nice tee ~/.ssh/authorized_keys`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝或要求审批（launcher 剥离到不动点后，真实命令 SHALL 受检；未识别前缀后跟着受判命令时 SHALL 按未知形态处置）

#### Scenario: 未识别前缀的「限定 ask」不误伤普通程序

- **GIVEN** `my-custom-tool --flag`、`terraform plan`、`./scripts/run.sh`、`bun run dev`、`pytest -q`（未识别或未列入受判集合的程序）
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（default-allow；「限定 ask」只在未识别前缀**后跟受判命令**时触发）
- **AND** `nsenter -t 1 cp x .env` / `watch -n 1 cp x .env` / `setarch x86_64 cp x .env` / `flock /tmp/l cp x .env` SHALL 返回 `ask`（未识别前缀 + 后跟受判命令）

#### Scenario: wrapper 与 launcher 交叠剥离到不动点

- **GIVEN** `nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝或要求审批（剥离循环交替进行直到不动点，SHALL NOT 在第一个未识别前缀处停止）

#### Scenario: heredoc 正文按绑定关系分流

- **GIVEN** `cat <<'EOF'` + 正文含 `cp x .env` + `EOF`（绑定到非解释器）与 `bash <<EOF` + 正文含 `cp x .env` + `EOF`（绑定到解释器）
- **WHEN** 命令护栏校验
- **THEN** 前者 SHALL 放行（正文是 stdin 数据，不构成命令）
- **AND** 后者 SHALL 拒绝（正文是该解释器的待执行代码）
- **AND** `cat <<EOF > /etc/passwd` + 正文 + `EOF` SHALL 拒绝（重定向目标是受保护路径）

#### Scenario: 命令替换无论位置都递归受检

- **GIVEN** `echo $(rm -rf /tmp/x)`、`` echo `rm -rf /tmp/x` ``、`$(echo rm -rf /)`、`x=$(cp x .env)`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（命令替换出现在参数位照样执行代码，SHALL NOT 因「不在写目标位置」而放行）

#### Scenario: 字符串型载荷判定一致

- **GIVEN** `eval 'cp x .env'`（引号载荷）与 `eval cp x .env`（未加引号）
- **WHEN** 命令护栏校验
- **THEN** 两者判定 SHALL 一致（均为拒绝或要求审批），SHALL NOT 因载荷被引号合成单 token 而放行

#### Scenario: 链式与分组命令的每一段都被检查

- **GIVEN** `cd /tmp && cp evil ~/.ssh/authorized_keys` 或 `true; cp evil sub/.env/secrets` 或 `(cp evil a/.env)` 或 `if true; then cp x .env; fi`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（命令不在首段也 SHALL 受检）

#### Scenario: shell `-c` payload 递归受检且有界

- **GIVEN** `bash -c "cp evil a/.env"`、`bash -lc "…"`、`env -u FOO bash -c "…"`、`bash --norc -c "…"`、`bash -c a -c "cp evil a/.env"`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝（payload 被解包并当独立命令行检查；长选项 `--norc` SHALL NOT 被误认为 `-c`）
- **AND** 形如 `bash -c "bash -c …"` 的深层嵌套 SHALL 在有界深度内终止，SHALL NOT 无限递归

#### Scenario: 默认放行未知命令

- **GIVEN** 成功解析且未命中任何规则的未知命令 `my-custom-tool --flag`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（default-allow；后端负责隔离）
- **AND** **未识别命令前缀**（可能掩盖真实命令的 launcher 形态）SHALL NOT 适用本条，而 SHALL 按未知形态处置（`ask`）

#### Scenario: 解析结果的三态决策

- **GIVEN** 一条护栏无法给出确定结论的命令（解析错误 / 目标位置的动态词 / 不支持的语法节点 / 超出嵌套深度或解析预算）
- **WHEN** 命令护栏校验
- **THEN** SHALL 返回 `ask` 并路由到审批层，SHALL NOT 静默放行
- **AND** 解析错误（`has_error` 或 `is_missing`）命中时 IR 的 argv SHALL 被弃用（畸形输入下捕获退化为垃圾，不可作为判定依据）
- **AND** 无 UI / 非交互环境下 SHALL 由审批层拒绝

#### Scenario: 护栏不因自身放行而绕过执行后端

- **GIVEN** 护栏判定 `allow` 但执行后端不可用
- **WHEN** Bash 工具执行
- **THEN** SHALL NOT 以无保护方式执行（后端不可用是显式失败，不是护栏放行的理由）

### Requirement: 命令护栏的能力范围声明与责任边界

命令护栏 SHALL 维护一份**可证伪的能力范围声明**，按输入形态 × **执行后端**给出三层职责：`Guard guarantees`（护栏负责且承诺拦住的形态）、`Backend guarantees`（执行后端承诺的边界）、`Unsupported`（明确不分析的形态及其处置）。声明 SHALL 避免「安全」「完全正确」这类不可证伪措辞；每一项承诺 SHALL 对应**当前真实存在**的测试用例，SHALL NOT 引用尚未编写的测试名（待补项 SHALL 显式标注为新增）。

声明 SHALL 按执行后端分别陈述边界，SHALL NOT 用「后端兜住」掩盖默认配置下的空缺：**`ProcessBackend`（默认后端）SHALL 被如实描述为不提供文件系统隔离、不提供网络隔离、不提供提权限制**（只提供进程启动、超时与可选 cgroup v2 资源限制）；`DockerBackend`（opt-in）SHALL 被如实描述为 `--network none` + 仅挂载 workspace（partial：容器内可写、以 root 运行、未 drop capabilities）。声明 SHALL NOT 暗示「护栏 + 默认后端 = 双层防御」。

声明 SHALL 覆盖以下输入形态：`simple argv`、`&&`/`||`/`;`/`|`/`&`、换行、分组与 shell 关键字、`env`/`command`/`nohup`、launcher 前缀、`bash -c`/`sh -c`、`eval`、命令替换、进程替换、heredoc、herestring、重定向、变量/glob/brace 展开、绝对路径/符号链接、`rm`/`cp`/`mv`/`chmod`/`curl`/`wget`/`dd`/`tee`、网络、子进程、资源耗尽。

责任分界 SHALL 明确：护栏只做命令结构的判定与路由，SHALL NOT 承诺拦截混淆到语法层以下的对抗输入（如编码后的 payload）；路径包含判定 SHALL NOT 被表述为「只要用了正确的解析器就成立」。护栏与 `workspace_policy.assert_command_allowed` 的**先后顺序与各自覆盖面** SHALL 被如实描述（前者先运行、命中即硬拒、护栏不执行），SHALL NOT 把「被 workspace_policy 拒绝」记作护栏的覆盖。

#### Scenario: 声明覆盖度可机械检查

- **GIVEN** 能力范围声明的输入形态矩阵
- **WHEN** 测试套件检查
- **THEN** 矩阵中 SHALL NOT 存在「测试证据」列为空的形态，且所列测试名 SHALL 可被 `pytest --collect-only` 解析到

#### Scenario: 后端边界按实现如实声明

- **GIVEN** 能力范围声明的 `Backend guarantees` 列
- **WHEN** 与 `agent/tools/sandbox/` 的实现比对
- **THEN** 默认 `ProcessBackend` 的文件系统/网络/提权能力 SHALL 被标为「无隔离」，SHALL NOT 声称存在 Landlock/bwrap/seccomp 边界
- **AND** `DockerBackend` 的限制 SHALL 被标为 partial 并列出未覆盖项

#### Scenario: 明确不承诺的项被显式标注

- **GIVEN** 已知本层无法防御的攻击类别（如仅靠命令文本无法识别的编码 payload、解析器无法解决的路径规范化缺陷）
- **WHEN** 阅读能力范围声明
- **THEN** SHALL 能找到对应条目并明确写为「本层不声称能防」或其等价表述

### Requirement: 恶意命令攻击回归集

沙箱 SHALL 维护数据驱动攻击集（`benchmarks/attacks/attacks.json`），包含 50+ 恶意命令（file-destroy/priv-esc/code-exec/exfil/resource/bypass/sensitive-read 分类），SHALL 断言所有 guard-deny case 被拦截。攻击集 SHALL 只增不减：护栏重构 SHALL NOT 降低被拦截的攻击用例数，SHALL 新增 heredoc 绑定解释器、launcher 族、混淆形态（反斜杠/glob/字符类/brace 展开）、重定向到敏感点目录、`dd`/`tee` 目标与 CVE-inspired 用例。

护栏 SHALL 保留一条**字面模式通道**作为深度防御层，并 SHALL 在文档中如实标注其身份：实测若移除该通道，54 条攻击用例的拦截数将从 54 降至 20（34 条仅由字面模式拦下）。该通道 SHALL NOT 重复实现已由 IR evaluator 覆盖的语义——「同一语义两个实现」正是本次重构要消除的负担。

**攻击集的「被拦截」口径 SHALL 被明确定义并一致应用**（[Q5] 用户拍板）：

- **攻击集（`benchmarks/attacks/attacks.json`）SHALL 只允许 `deny`**——SHALL NOT 把 `ask` 混入攻击用例。把攻击用例放宽到允许 `ask`，会让一个在 CI（`FailClosed`）下失败的用例，在交互式开发里变成「人类可能点 y」，降低基线的语义强度。
- **会出 `ask` 的新增形态**（launcher「限定 ask」等）SHALL 进**独立的「应 ask」用例集**，断言结果为 `ask`。
- **无回归线的计数谓词 SHALL 为 `verdict is not ALLOW`**（`旧 DENY ⊆ 新 DENY ∪ 新 ASK` 使用的谓词）；该谓词比「`deny` 单独计数」更诚实（无 UI 环境下 `ask` 就是拦截），且与「攻击集只允 deny」的严格用例集不冲突。
- 实测：既有 **50 条 guard-deny 攻击用例过新管线 50/50 保持 `DENY`**（0 条翻 `ask`、0 条翻 `allow`），故既有断言无需修改。

#### Scenario: 攻击集拦截

- **GIVEN** 攻击集 cases
- **WHEN** 每个 guard-deny case 被命令护栏校验
- **THEN** 全部 SHALL 被拒绝

#### Scenario: 重构不得降低拦截数

- **GIVEN** 重构前被拦截的攻击集用例集合与现有 guard 单元测试的命令串集合
- **WHEN** 重构后的命令护栏校验同一批输入
- **THEN** **旧 `DENY` SHALL 是 新 `DENY ∪ 新 `ASK` 的子集**（对拍断言）
- **AND** 存在可切换回旧实现的回退开关，直到对拍全绿

#### Scenario: 攻击集只允 deny，「应 ask」另建用例集

- **GIVEN** 攻击集用例与新增的 launcher 形态（`nsenter -t 1 cp x .env` 等返回 `ask` 的形态）
- **WHEN** 测试套件校验
- **THEN** 攻击集用例 SHALL 全部为 `deny`（SHALL NOT 出现 `ask`）
- **AND** 返回 `ask` 的形态 SHALL 出现在独立的「应 ask」用例集并被断言为 `ask`
- **AND** 「被拦截」的计数谓词 SHALL 为 `verdict is not ALLOW`

#### Scenario: 字面通道的身份被如实标注

- **GIVEN** 能力范围声明与代码注释
- **WHEN** 检查字面模式通道
- **THEN** SHALL 标注其为深度防御的字面层而非解析层，且 SHALL NOT 与 evaluator 重复实现同一语义

#### Scenario: 同一语义不得有第二个实现

- **GIVEN** 「敏感 dot 名」这一语义（`workspace_policy` 的 glob、同文件的源位置正则、`command_guard` 的 frozenset）
- **WHEN** 检查代码
- **THEN** SHALL 只有一份定义，其余处 SHALL 引用它；SHALL NOT 存在「同一文件、两条通道、两种答案」（实测现成实例：`cp x .env.local` 在 Read/Write 下 DENY、在 Bash 护栏下 ALLOW）
- **AND** 该定义 SHALL 为代码谓词，SHALL NOT 为 glob 字符串（`fnmatch` 不支持 extglob，写成 glob 会静默放开两边）

### Requirement: cgroup v2 资源限制

沙箱 SHALL 在配置 `sandbox.memory_mb`/`sandbox.cpus` 时通过 cgroup v2 对本地 `ProcessBackend` 实施 CPU/内存限制，SHALL 为每次 `run` 创建唯一命名的临时子 cgroup，SHALL 检测 OOM kill 并在结果上标记 `oom_killed`，且 SHALL 在宿主无法创建 cgroup 时可观测地降级（结果 `degraded` 标志 + `degraded` 沙箱事件）——绝不静默忽略已请求的限制。

#### Scenario: 内存限制生效

- **GIVEN** 配置 `sandbox.memory_mb` 且 cgroup v2 可用
- **WHEN** 命令通过 ProcessBackend 运行
- **THEN** 命令 SHALL 在独立临时 cgroup 中运行并写入 `memory.max`
- **AND** OOM kill SHALL 标记结果并发出 `oom` 沙箱事件

#### Scenario: 无 cgroup 环境降级

- **GIVEN** 配置 `sandbox.memory_mb` 但宿主无法创建 cgroup
- **WHEN** 命令通过 ProcessBackend 运行
- **THEN** 结果 SHALL 标记 `degraded`
- **AND** 发出 `degraded` 沙箱事件（每后端实例至多一次）

### Requirement: 沙箱事件入 trace

沙箱 SHALL 通过 contextvar sink 向活跃的 `TraceRecorder` 发出结构化事件（`denied`/`kill`/`oom`/`degraded`），SHALL 附带调用方 `tool_call_id` 与截断的命令，且 SHALL 与 trace 事件 schema 向后兼容（新增 `sandbox` step type；`schema_version` 不变）。

该 sink SHALL 只对其所属执行上下文生效：一次 run 退出时对 sink 的恢复 SHALL NOT 写入任何**其它**执行上下文（否则会改写或清空另一个活跃 run 的事件归属，使 sandbox 事件静默丢失或串写进别的 run 的 trace）。

#### Scenario: 命令拒绝事件

- **GIVEN** 命令被 workspace policy 或命令护栏拒绝
- **WHEN** Bash 工具拒绝该命令
- **THEN** trace 中 SHALL 记录带拒绝原因的 `sandbox` `denied` 事件

#### Scenario: 超时 kill 事件

- **GIVEN** 命令超过超时（前台或后台）
- **WHEN** 后端或后台管理器杀死进程树
- **THEN** trace 中 SHALL 记录 `sandbox` `kill` 事件

#### Scenario: 被遗留 run 的迟后收尾不改变活跃 run 的事件归属

- **GIVEN** 一个 run 已启动并挂起在其私有执行上下文中，且其所属事件循环已关闭（该 run 的 task 保持 pending）
- **AND** 另一个 run 正在其自己的执行上下文中、以自己活跃的 sink 记录 sandbox 事件
- **WHEN** 那个被遗留的 task 在**后一个 run 的上下文里**被终结（例如被垃圾回收），从而展开其嵌套的 `finally`
- **THEN** 系统 SHALL NOT 因此改写后一个（活跃）run 的 sink
- **AND** 活跃 run 之后发出的 sandbox 事件 SHALL 仍写入它**自己**的 trace
- **AND** 该事件 SHALL NOT 静默丢失，也 SHALL NOT 写入任何别的 run 的 trace

### Requirement: 显式可写豁免（allowed_write_paths）

WorkspacePolicy SHALL 支持一份**显式可写豁免**（`allowed_write_paths`），语义是「deny 默认 + allow 精确覆盖」：默认值为空，未配置时路径拒绝行为 SHALL 与本能力引入前逐条一致。allow SHALL 只能把**已经在 workspace 内、且已被 deny 判定命中的路径**重新放行为可写；它 SHALL NOT 越过 workspace 边界，SHALL NOT 影响读判定。

allow 的判定 SHALL 是一个**共享谓词函数**，由**写路径**的判定器共同调用：`WorkspacePolicy.assert_write_allowed` 与命令护栏（`CommandGuard`）的写目标判定 SHALL 都调用它。共享的是**谓词函数**，SHALL NOT 是**调用点**——即 `is_denied` 与其读侧调用方 SHALL NOT 感知 allowlist。条目 SHALL 按「**任一 workspace 根**的相对路径」匹配（主 workspace 与附加根一视同仁，与 `relative_path()` 的现有语义一致）。

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

#### Scenario: 豁免按「任一 workspace 根」的相对路径匹配

- **GIVEN** 主 workspace 根为 `/repo`，且已通过 `/workspace add`（或 Web hub 的「+ 添加」）追加附加根 `/srv/other`
- **AND** 配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 工具请求 `Write /srv/other/.env`
- **THEN** 该路径 SHALL 被放行（allow 条目按 `relative_path()` 的现有语义与**任一 workspace 根**的相对路径比较）
- **AND** 该结论 SHALL NOT 依赖「条目只对主 workspace 根生效」的读法

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

`allowed_write_paths` 的每一项 SHALL 是 workspace 相对路径的**字面值**（精确匹配）。配置解析 SHALL 对以下条目 fail fast 并返回可读错误，SHALL NOT 宽容接受：含 glob 元字符（`*`、`?`、`[`、`]`）、绝对路径、含 `..` 路径段、以 `/` 结尾的目录形式，以及**无法与 `relative_path()` 的返回值相等的非规范拼写**（前导 `./`、重复斜杠、含 `.` 段、反斜杠分隔、落成空路径）——最后一类的理由是这类条目永远匹配不上，接受它等于给安全白名单制造**静默 no-op**；条目两端空白由配置解析的既有 `strip()` 处理，不属此类。

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

#### Scenario: 非规范拼写 fail fast（防静默 no-op）

- **GIVEN** 配置含 `./.env`、`a//b`、`a/./b` 或 `a\b` 这类非规范拼写
- **WHEN** 系统解析配置
- **THEN** 系统 SHALL 逐条 fail fast 并返回可读错误，提示改成规范写法
- **AND** 该条 SHALL NOT 依赖运行时静默失效（这类条目永远匹配不上 `relative_path()`）
- **AND** 条目两端空白 SHALL 仍被 `strip()` 接受（`' .env'` 解析为 `'.env'`）

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

本能力 SHALL 是**增量**的：对未被 allow 命中的路径，文件工具层与命令护栏层的判定 SHALL 与引入本能力前逐条一致；对被 allow 命中的路径，**在命令护栏的「写目标判定面」上**判定 SHALL 与文件工具层同向变化（都从拒变放行）。「写目标判定面」SHALL 指 `CommandGuard` 中**消费写目标路径**的判定：写目标位置的目标判定、重定向目标判定、动态目标判定、`mv`/`cp` 目标判定、`tee` 目标判定与 `dd of=` 目标判定。它 SHALL NOT 包含：① 在命令 IR 判定之前执行的**整句 denylist 正则扫描**；② `mv`/`cp` 的**源位置**判定（读侧，SHALL NOT 被 allow 影响）；③ `rm` 的**逃逸**判定；④ **命令护栏不感知附加根**——`CommandGuard` 只持有主 workspace（它没有 `additional_roots`），而文件工具层按「任一 workspace 根」的相对路径匹配（见「显式可写豁免」Requirement），因此附加根下的路径会出现「文件工具层放行、命令护栏仍拒」的形态。系统 SHALL NOT 承诺「两层对任意路径恒同向」——两层判定面在引入本能力前就存在差异（命令护栏的写目标判定不消费 `DEFAULT_DENIED_PATTERNS`），该差异不在本能力的职责范围内；①与④的刻意例外见「Bash 层豁免覆盖面差异必须被记录」。

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

#### Scenario: 附加根下的路径也不与文件层同向（根盲区）

- **GIVEN** 主 workspace 根 `/repo`，附加根 `/srv/other` 已通过 `/workspace add` 追加，配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** 对 `/srv/other/.env` 求值文件工具层的写判定，并分别求值命令护栏的重定向目标 / `tee` / `dd of=` / `install` 写目标判定
- **THEN** 文件工具层 SHALL 放行（豁免按任一 workspace 根的相对路径匹配）
- **AND** 命令护栏 SHALL 仍判 `deny`（重定向 ⇒ `protected_redirect`、`tee` ⇒ `tee_target`、`dd of=` ⇒ `dd_target`、`install` ⇒ `install_target`）
- **AND** 该形态 SHALL 被视为本 Requirement 排除项 ④ 的**显式例外**，SHALL NOT 被读作违反
- **NOTE** 它与「嵌套敏感路径命中整句正则」**不同源**：那里是 pre-IR 的整句 denylist 正则（`cp` / `mv` 的 `last_reason` 为 `denylist`），这里是护栏**看不到附加根**；两者 SHALL 分开归因

### Requirement: Bash 层豁免覆盖面差异必须被记录

命令护栏的**整句 denylist 正则扫描**（在命令 IR 判定之前执行）SHALL 保持其现有语义，本能力 SHALL NOT 使其可被配置覆盖。其后果——**嵌套路径**（如 `config/.env`）的 Bash `cp` / `mv` 写目标 SHALL NOT 因 allow 命中而放行（`last_reason` 为 `denylist`），而同一路径的 `Write` / `Edit` / 重定向（`>>`）/ `tee` / `dd of=` / `install` SHALL 放行——SHALL 在规格、change 文档与用户可见的配置示例中**如实记录**，SHALL NOT 被表述为「该路径的写已全部放开」。

另有一条**不同源**的覆盖面差异 SHALL 一并如实记录：**命令护栏不感知附加根**（`CommandGuard` 只持有主 workspace）。附加根下的路径（如 `/srv/other/.env`）在文件工具层可被豁免放行，但命令护栏的重定向 / `tee` / `dd of=` / `install` 写目标判定 SHALL 仍判 `deny`（`protected_redirect` / `tee_target` / `dd_target` / `install_target`，均属可挂钩面但路径比对不中），`cp` / `mv` 则**同时**叠加整句正则那层。两条差异 SHALL NOT 被混为一条归因。

#### Scenario: 嵌套路径的 cp/mv 不被豁免放行

- **GIVEN** 配置含 `tools.allowed_write_paths: ['config/.env']`
- **WHEN** Bash 请求执行 `cp x config/.env` 或 `mv x config/.env`
- **THEN** 命令护栏 SHALL 仍判 `deny`，`last_reason` SHALL 为 `denylist`
- **AND** 该结论 SHALL 作为**规格行为**被回归测试锁定（不是缺陷，不得被「顺手修好」）

#### Scenario: 嵌套路径的非 cp/mv 写可被豁免放行

- **GIVEN** 同一份配置 `tools.allowed_write_paths: ['config/.env']`
- **WHEN** 工具请求 `Write config/.env`，或 Bash 执行 `echo K >> config/.env` / `tee config/.env` / `dd of=config/.env`
- **THEN** 这些写 SHALL 被放行

#### Scenario: 附加根的写形态因根盲区仍拒（与整句正则不同源）

- **GIVEN** 主根 `/repo` + 附加根 `/srv/other`，配置含 `tools.allowed_write_paths: ['.env']`
- **WHEN** Bash 执行 `echo K >> /srv/other/.env` / `tee /srv/other/.env` / `dd of=/srv/other/.env` / `install x /srv/other/.env`
- **THEN** 命令护栏 SHALL 仍判 `deny`，`last_reason` 分别为 `protected_redirect` / `tee_target` / `dd_target` / `install_target`
- **AND** 该组拒绝的来源 SHALL 归因为**根盲区**（护栏只持有主 workspace），SHALL NOT 与「命中整句 denylist 正则」混为一谈
- **AND** 该结论 SHALL 作为规格行为被回归测试锁定
