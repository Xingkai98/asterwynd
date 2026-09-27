## MODIFIED Requirements

### Requirement: 命令护栏（单一解析管线 + 能力范围声明）

命令护栏 SHALL 采用单一解析管线处理 shell 命令：`source → parse/tokenize → command IR → policy evaluators → decision`。护栏 SHALL 只解析一次并产出结构化中间表示（IR），SHALL 由所有判定器消费同一 IR；SHALL NOT 存在多个各自从原始命令文本或独立分词结果出发的语义解析入口。IR SHALL 至少携带：命令段与各行内命令的 argv、重定向（文件描述符、操作符、目标）、环境变量赋值、动态词标记、解析错误标记、不支持的语法节点、源码位置。

护栏 SHALL 拒绝危险命令模式（rm 递归+强制目标越界、重定向到受保护路径、管道到 shell、任意代码执行解释器、敏感文件外传），SHALL 默认放行未知命令（护栏不是边界）。

护栏的判定结果 SHALL 是三态：`allow` / `deny` / `ask`。`ask` SHALL 被路由到审批层（`agent/approval.py` 的 `ApprovalHandler`），SHALL NOT 被护栏自行解释为放行。`allow` SHALL NOT 表示「安全」，SHALL 只表示「护栏没有理由阻止」；护栏 SHALL NOT 因为判定 `allow` 而绕过执行后端（`ProcessBackend` / `DockerBackend` / OS sandbox）。

受保护路径与工作区边界的判定 SHALL 按**路径段**比较（`path == prefix` 或 `path` 以 `prefix + "/"` 开头），SHALL NOT 使用裸字符串前缀比较——裸前缀会把 `/various.txt` 当作 `/var` 下的路径、把 `/tmp/ws-evil` 当作工作区 `/tmp/ws` 内的路径。判定前 SHALL 先对路径做规范化（解析 `..` 与 `.` 段），使 `rm -rf /tmp/ws/../etc`（工作区为 `/tmp/ws`）SHALL NOT 因字面前缀匹配而被判为工作区内。该判定 SHALL 独立于解析器实现：解析器只确定「参数是哪个」，路径规范化与分量边界比较 SHALL 在执行路径上完成。

**重定向目标**与 **mv/cp 目标**的判定 SHALL 豁免设备文件 `/dev/null`、`/dev/stdout`、`/dev/stderr`——它们是黑洞设备与进程标准流的别名，不属于「受保护的系统目录内容」语义。该豁免 SHALL NOT 扩展到 rm/chmod/curl-wget 的目标判定（`rm -rf /dev/null` SHALL 保持拒绝）；其余 `/dev/*` 目标 SHALL 保持拒绝。

mv/cp 目标命中敏感点目录（`.git`/`.ssh`/`.env`/`.aws`/`.gnupg`/`.kube`/`.docker`/`.netrc`/`.npmrc`/`.pypirc`）SHALL 被拒绝。目标参数 SHALL 从 IR 的 argv 读取，SHALL NOT 因解析器对 brace 展开、反斜杠转义、glob 或字符类的处理而丢失或被切碎——`cp x ~/.{ssh}/f` SHALL NOT 因目标被切成多段而放行。判定 SHALL 覆盖**互补**通道并如实描述各自覆盖面：**argv 通道**在 `mv`/`cp` 居命令段首时按路径段比较，覆盖裸形态（`.env`）与嵌套形态（`src/.git/hooks/x`），并 SHALL NOT 误判 `.gitignore`、`.env.example`、`.github/` 这类普通文件/目录；**混淆归一化通道**对目标做归一化（去反斜杠转义、展开字符类与 brace、以 `fnmatch` 反向匹配判定敏感名能否被该模式匹配）后判定，SHALL NOT 因此误报字面名（`.env.example` SHALL 保持放行）。

rm 递归+强制的目标 SHALL NOT 等于工作区根（`rm -rf <workspace_root>` SHALL 拒绝），且 SHALL NOT 位于工作区之外。

argv 语义检查 SHALL 覆盖**命令行的每一段**，SHALL NOT 只检查首段——命令分隔符（`&&`/`||`/`;`/`|`/`&`/换行）与分组符号（`(`/`)`/`{`/`}`）之后、以及 shell 关键字（`then`/`do`/`else`/`fi`/`done`/`time`/`exec`/`eval` 等）之后的命令 SHALL 同样受检。`<shell> -c <string>` 形态（含 `-lc`/`-ic` 等短选项簇、`env`/`command`/`nohup` 前缀及其选项、重复 `-c`）SHALL 对每个 payload 递归执行同样的校验；递归 SHALL 有深度上界，超出上界时 SHALL 停止解包而 SHALL NOT 无界递归（护栏不是边界，真实边界在执行后端）。shell 关键字与 wrapper 前缀的剥离 SHALL 发生在 IR 构造阶段，SHALL NOT 在多个判定器上分别实现。`<shell> -c SCRIPT $0 $1` 的位置参数 SHALL NOT 掩盖 SCRIPT 本身；`env -S <string>` / `env --split-string <string>` 的值 SHALL 被当作待执行的命令检查。

**launcher 前缀**（`nice`/`flock`/`chroot`/`setsid`/`xargs`/`busybox`/`stdbuf`/`taskset`/`timeout` 等）SHALL 按其自身的参数模式剥离（区分「消费下一 token 的选项」「自身吞掉的位置参数」「其后为真实命令」），剥离后 SHALL 对真实命令执行同样的 checks；`nice cp x .env`、`flock /tmp/l cp x .env`、`nice tee ~/.ssh/authorized_keys` SHALL 被拒绝。

heredoc 的**正文是数据**、SHALL NOT 被当作命令判定：`cat <<'EOF'\ncp x .env\nEOF` SHALL NOT 因正文含危险字样而被拒绝；重定向到受保护路径的目标 SHALL 仍被判定（`cat <<EOF > /etc/passwd` SHALL 拒绝）。

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

#### Scenario: 目标参数不得被解析层销毁

- **GIVEN** `cp x ~/.{ssh}/f`（brace 展开）、`cp x ~/.ss\h/id_rsa`（反斜杠转义）、`cp x ~/.s[h]h/f`（字符类）、`cp x ~/.ss*/f`（glob）
- **WHEN** 命令护栏校验
- **THEN** 这些命令 SHALL 被拒绝或要求审批（目标归一化后命中敏感名，SHALL NOT 因目标被切碎而放行）
- **AND** 同时 `cp x .env.example`、`cp x .gitignore`、`cp x .github/w.yml` SHALL 保持放行（归一化不得引入误报）

#### Scenario: launcher 前缀不得掩盖真实命令

- **GIVEN** `nice cp x .env`、`flock /tmp/l cp x .env`、`chroot /tmp cp x .env`、`setsid cp x .env`、`stdbuf -o0 cp x .env`、`taskset -c 0 cp x .env`、`nice tee ~/.ssh/authorized_keys`
- **WHEN** 命令护栏校验
- **THEN** SHALL 拒绝或要求审批（launcher 按其参数模式剥离后，真实命令 SHALL 受检）

#### Scenario: heredoc 正文是数据不是命令

- **GIVEN** `cat <<'EOF'\ncp x .env\nEOF` 或 `cat <<EOF\nnice tee ~/.ssh/authorized_keys\nEOF`
- **WHEN** 命令护栏校验
- **THEN** SHALL 放行（heredoc 正文是 stdin 数据，不构成命令）
- **AND** `cat <<EOF > /etc/passwd\nx\nEOF` SHALL 保持拒绝（重定向目标是受保护路径）

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

#### Scenario: 解析结果的三态决策

- **GIVEN** 一条护栏无法给出确定结论的命令（解析错误 / 目标位置的动态词 / 不支持的语法节点 / 超出嵌套深度或解析预算）
- **WHEN** 命令护栏校验
- **THEN** SHALL 返回 `ask` 并路由到审批层，SHALL NOT 静默放行（default-allow 只适用于**成功解析且未命中任何规则**的命令）
- **AND** 无 UI / 非交互环境下 SHALL 由审批层 `FailClosedApprovalHandler` 拒绝

#### Scenario: 护栏不因自身放行而绕过执行后端

- **GIVEN** 护栏判定 `allow` 但执行后端不可用
- **WHEN** Bash 工具执行
- **THEN** SHALL NOT 以无保护方式执行（后端不可用是显式失败，不是护栏放行的理由）

### Requirement: 命令护栏的能力范围声明与责任边界

命令护栏 SHALL 维护一份**可证伪的能力范围声明**，按输入形态给出三层职责：`Guard guarantees`（护栏负责且承诺拦住的形态）、`Backend guarantees`（明确交给执行后端的形态）、`Unsupported`（明确不分析的形态及其处置）。声明 SHALL 避免「安全」「完全正确」这类不可证伪措辞，每一项承诺 SHALL 对应至少一条可执行的回归用例。

声明 SHALL 覆盖以下输入形态：`simple argv`、`&&`/`||`/`;`/`|`/`&`、换行、分组与 shell 关键字、`env`/`command`/`nohup`、launcher 前缀、`bash -c`/`sh -c`、`eval`、命令替换、进程替换、heredoc、重定向、变量/glob/brace 展开、绝对路径/符号链接、`rm`/`cp`/`mv`/`chmod`/`curl`/`wget`/`dd`、网络、子进程、资源耗尽。

责任分界 SHALL 明确：护栏只做命令结构的判定与路由，SHALL NOT 承诺拦截混淆到语法层的对抗输入（如编码后的 payload）；路径包含判定 SHALL NOT 被表述为「只要用了正确的解析器就成立」；执行后端 SHALL 是唯一做边界承诺的层。

#### Scenario: 声明覆盖度可机械检查

- **GIVEN** 能力范围声明的输入形态矩阵
- **WHEN** artifact checker 或测试套件检查
- **THEN** 矩阵中 SHALL NOT 存在「测试证据」列为空的形态（每个承诺有可执行用例）

#### Scenario: 明确不承诺的项被显式标注

- **GIVEN** 已知本层无法防御的攻击类别（如仅靠命令文本无法识别的编码 payload、解析器无法解决的路径规范化缺陷）
- **WHEN** 阅读能力范围声明
- **THEN** SHALL 能找到对应条目并明确写为「本层不声称能防」或其等价表述

### Requirement: 恶意命令攻击回归集

沙箱 SHALL 维护数据驱动攻击集（`benchmarks/attacks/attacks.json`），包含 50+ 恶意命令（file-destroy/priv-esc/code-exec/exfil/resource/bypass/sensitive-read 分类），SHALL 断言所有 guard-deny case 被拦截。攻击集 SHALL 只增不减：护栏重构 SHALL NOT 降低被拦截的攻击用例数，SHALL 新增 launcher 族、混淆形态（反斜杠/glob/字符类/brace 展开）与 CVE-inspired 用例。

#### Scenario: 攻击集拦截

- **GIVEN** 攻击集 cases
- **WHEN** 每个 guard-deny case 被命令护栏校验
- **THEN** 全部 SHALL 被拒绝

#### Scenario: 重构不得降低拦截数

- **GIVEN** 重构前被拦截的攻击集用例集合
- **WHEN** 重构后的命令护栏校验同一攻击集
- **THEN** 被拦截用例数 SHALL NOT 少于重构前，且新增用例 SHALL 被覆盖
