## MODIFIED Requirements

### Requirement: 命令护栏（轻量分词 + argv 语义校验）

命令护栏 SHALL 通过轻量分词与 argv 语义校验验证 shell 命令，SHALL 拒绝危险命令模式（rm 递归+强制目标越界、重定向到受保护路径、管道到 shell、任意代码执行解释器、敏感文件外传），SHALL 扩展 denylist 覆盖绕过变体，SHALL 默认放行未知命令（护栏不是边界）。

受保护路径与工作区边界的判定 SHALL 按**路径段**比较（`path == prefix` 或 `path` 以 `prefix + "/"` 开头），SHALL NOT 使用裸字符串前缀比较——裸前缀会把 `/various.txt` 当作 `/var` 下的路径、把 `/tmp/ws-evil` 当作工作区 `/tmp/ws` 内的路径。判定前 SHALL 先对路径做规范化（解析 `..` 与 `.` 段），使 `rm -rf /tmp/ws/../etc`（工作区为 `/tmp/ws`）SHALL NOT 因字面前缀匹配而被判为工作区内。

**重定向目标**与 **mv/cp 目标**的判定 SHALL 豁免设备文件 `/dev/null`、`/dev/stdout`、`/dev/stderr`——它们是黑洞设备与进程标准流的别名，不属于「受保护的系统目录内容」语义。该豁免 SHALL NOT 扩展到 rm/chmod/curl-wget 的目标判定（`rm -rf /dev/null` SHALL 保持拒绝）；其余 `/dev/*` 目标 SHALL 保持拒绝。

mv/cp 目标命中敏感点目录（`.git`/`.ssh`/`.env`/`.aws`/`.gnupg`/`.kube`/`.docker`/`.netrc`/`.npmrc`/`.pypirc`）SHALL 被拒绝，判定 SHALL 按**路径段**比较（`.gitignore`、`.env.example`、`.github/` 是普通文件/目录，SHALL NOT 被误判），且 SHALL 同时覆盖裸形态（`.env`）与嵌套形态（`src/.git/hooks/x`）。

rm 递归+强制的目标 SHALL NOT 等于工作区根（`rm -rf <workspace_root>` SHALL 拒绝），且 SHALL NOT 位于工作区之外。

argv 语义检查 SHALL 覆盖**命令行的每一段**，SHALL NOT 只检查首段——命令分隔符（`&&`/`||`/`;`/`|`/`&`/换行）与分组符号（`(`/`)`/`{`/`}`）之后、以及 shell 关键字（`then`/`do`/`else`/`fi`/`done`/`time`/`exec`/`eval` 等）之后的命令 SHALL 同样受检。`<shell> -c <string>` 形态（含 `-lc`/`-ic` 等短选项簇、`env`/`command`/`nohup` 前缀及其选项、重复 `-c`）SHALL 对每个 payload 递归执行同样的校验；递归 SHALL 有深度上界，超出上界时 SHALL 停止解包而 SHALL NOT 无界递归（护栏不是边界，真实边界在执行后端）。shell 关键字（`then`/`do`/`else`/`fi`/`done`/`time`/`exec`/`eval` 等）前缀的剥离 SHALL 发生在 argv 与 payload 两条通道的**共用入口**，SHALL NOT 只在其中一条上生效。`<shell> -c SCRIPT $0 $1` 的位置参数 SHALL NOT 掩盖 SCRIPT 本身；`env -S <string>` / `env --split-string <string>` 的值 SHALL 被当作待执行的命令检查。

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

#### Scenario: 重定向到受保护路径拒绝

- **GIVEN** `echo x > /etc/passwd`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝

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

- **GIVEN** 未知命令 `my-custom-tool --flag`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（default-allow；后端负责隔离）
