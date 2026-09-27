# Design: Bash 命令护栏的单一解析管线与能力范围声明

> **本版是 grill 后的修订版（v2）**。首版 design 经 4 个独立零记忆 subagent 以不同视角（绕过面 / 成本 / 可行性 / 证据审计）追问，发现 9 项阻塞问题，其中一项是**首版自身会引入的安全回归**。修订内容与证据见 `reviews/grill-design.md`；下文凡经 grill 更正的结论均标注「[grill]」。

## Context

### 现状

`agent/tools/command_guard.py`（577 行）在 `fix-issue-247` 之后由**三条并行通道**组成，每条都从原始命令文本或自己的分词结果出发做语义判定：

```
check(cmd):
  1. 全文 denylist 正则        → DEFAULT_DENYLIST(59, 含 1 条重复) + _EXTRA_DENYLIST(18)
  2. _has_pipe_to_shell(cmd)   → 又一次 re.split 全文本
  3. _has_protected_redirect   → tokenize_command 后按 token 找 > / >>
  4. _check_argv               → _check_command_text(raw) 重新按 \r\n 切分 + 逐段 tokenize
                               → _strip_wrappers / _shell_dash_c_payloads / _check_rm ...
```

同一份「这条命令有几个段、每段 argv 是什么」被回答了三次，且三次在 `$(...)`、heredoc、brace 展开、进程替换上**互相矛盾**。

### 已实测的缺陷（grill 独立复现确认）

| 类型 | 命令 | 当前判定 | 机制 |
|---|---|---|---|
| **误报** | `cat <<'EOF'` + `cp x .env` + `EOF` | deny (`mv_cp_dest`) | 分词器把 `<<` 拆成 `<` `<`，heredoc 正文成了「命令段」 |
| **漏报** | `cp x ~/.{ssh}/f` | allow | brace 展开 → 段切成 `~/.` `ssh` `/f`，目标参数消失 |
| **漏报** | `cp x ~/.ss\h/id_rsa` / `~/.s[h]h/f` / `~/.ss*/f` | allow | 反斜杠/字符类/glob（known-debt 乙类） |
| **漏报** | `nice cp x .env` / `flock /tmp/l cp x .env` | allow | launcher 前缀（known-debt 甲类） |

**grill 追加实测的漏报（首版 design 未覆盖）**：

| 命令 | 判定 | 说明 |
|---|---|---|
| `eval 'cp x .env'` | allow | 引号把载荷合成一个 token，`_strip_wrappers` 剥掉 `eval` 后命令名变成 `cp x .env` ≠ `cp` |
| `cp -t .env x` / `mv --target-directory=.env x` | allow | `_check_mv_cp` 只读 `args[-1]`，目标经选项传递 |
| `dd of=.env` / `dd of=~/.ssh/authorized_keys` | allow | **没有 `dd` evaluator**（`dd if=` 被拦只是 denylist 字面巧合） |
| `echo SECRET=1 > .env` / `cat payload > ~/.ssh/authorized_keys` | allow | 重定向通道只比 `_DENY_PATHS`，**不含敏感点目录** |
| `doas cp x .env` / `unshare -m cp x .env` / `script -q /dev/null cp x .env` 等 | allow | launcher 族远不止首版列的 9 个 |

### 关键的架构事实（grill 发现，首版遗漏）

1. **默认执行后端没有任何文件系统/网络边界**。`ProcessBackend`（`agent/tools/sandbox/process_backend.py:68`）是宿主机 `create_subprocess_shell` + 可选 cgroup v2 内存/CPU 限制；`grep -rnE "landlock|bwrap|seccomp|unshare|CLONE_NEWNS" agent/ --include=*.py` **零命中**。只有 opt-in 的 `DockerBackend` 有 `--network none` + 只挂载 workspace（`docker_backend.py:101-113`），但它也没有 `--read-only` / `--cap-drop` / `--user`。
   → **首版 design 的「Backend guarantees」列被一行 grep 证伪**。默认配置下护栏是**唯一**的防线，这一事实必须如实写进能力范围声明，而不是用「边界在执行后端」把它糊过去。
2. **`workspace_policy.assert_command_allowed` 在护栏之前运行，且会硬拒一批形态**。`agent/tools/builtin/bash.py:68` 先调它，命中即 `permission_denied`、护栏根本不执行。`DEFAULT_DENYLIST` 因此被 `workspace_policy` 全文 `re.search` 与 `command_guard` 各跑一遍（两条不同的语义）。
3. **攻击集高度依赖全文 denylist 通道**。实测：把 `_denylist` 清空后，54 条攻击用例的 deny 数从 **54 → 20**（**34 条**只靠全文正则拦下）。这条通道不可能「降级为 evaluator」而不丢覆盖。
4. **工具无法触达审批层**。`BashTool` 无任何 approval 引用（`inspect.getsource` 实测），`Tool` 基类也无；`AgentLoop` 只在 `loop.py:842`、`decision.requires_approval` 分支调用 `request_approval`，而 `decide_tool` 只吃 `Tool` 对象、看不到 `cmd`。→ 首版「`ask` 复用既有审批路径、只新增一个调用点」**是错的**。

## Goals / Non-Goals

### Goals

1. **单一解析管线**：`source → parse → command IR → policy evaluators → decision`。所有判定器消费同一 IR；**judgement 所需的语义（命令名、argv、写目标、重定向目标、动态词、解析错误）在 IR 里一次定义**。
2. **可证伪的能力范围声明**：按输入形态 × **执行后端**给出 `Guard guarantees` / `Backend guarantees` / `Unsupported`，措辞可证伪、每行有真实存在的测试证据。
3. **未知与失败策略显式化**：不许静默放行。
4. **已知残余逐项收口**（甲类/乙类 + grill 新发现的 5 类）。
5. **不降低既有拦截能力**：攻击集拦截数不得下降——这是一条**硬验收线**，且实测表明它约束很强（见 D10）。

### Non-Goals

- 不证明任意 Bash 程序的最终效果（不做符号执行、不追踪 fs 状态）。
- 不手写 bash parser（kimi-code 16,900+ 行是这条路线成本的实证）。
- **本 change 不新增 OS 级沙箱**（那是执行后端的事）。但**必须如实声明默认后端没有边界**，不得用「后端兜住」掩盖。
- 不在本 change 内重写 `workspace_policy` 的 denylist 层（但要在 D6 说清两层关系）。

## Decisions

### D1：解析器选 `tree-sitter-bash`（数据支持）

**决策**：用 `tree-sitter-bash`（PyPI wheel，`tree_sitter_bash.language()`）替换自维护 tokenizer 作为 IR 的生产者。已随本 change `uv add tree-sitter-bash`（`pyproject.toml:45`，`uv.lock` 已锁定）。

**实测数据**（151 条语料，脚本 `research/gen_corpus.py` + `research/compare_parsers.py`，逐条结果 `research/parser-comparison-rows.json`；4 位 grill 审阅员各自独立复跑，数字一致）：

| 维度 | 当前 tokenizer | tree-sitter-bash | bashlex |
|---|---|---|---|
| `has_error`（151 条） | 从不报错，**静默误切** | **0/151** | 不适用 |
| 抛异常 | 从不 | **0/151** | **5/151**（`NotImplementedError`×3、`ParsingError`×2） |
| 结构分歧 | — | **23/151 条** `tok_n != ts_n` | — |
| 延迟（代表样本，300 次） | 0.016 ms | 0.040 ms | 0.813 ms |
| 一次性导入 | 0 | ~62 ms | ~290 ms |
| 新增依赖 | 0 | **1 个 wheel，226.5 KiB，cp310-abi3** | 67 KiB |
| 平台覆盖 | — | manylinux×4 / musllinux / macos×2 / win×2 / sdist，**目标平台全覆盖，无需编译器** | 纯 Python |
| 维护 / 许可 | 自维护 | 活跃 / MIT | **3.5 年未更新（0.18, 2023-01）/ GPL-3.0** |

**关键论据**：`tree-sitter` 已是本项目依赖（`pyproject.toml` 已有 + 6 个语法包），加 bash 是**补完已有承诺**。延迟不构成选型理由（三者都远低于一次 Bash 调用）。`bashlex` 因「抛异常 + 空串 `AttributeError` + 未维护 + GPL-3.0」排除。

**实现约束**（grill 复现，两处均已修正措辞）：

1. **枚举命令节点必须用 `QueryCursor`**：递归 Python 遍历在 `$(( 1+…+1 ))` 约 **1000 项（≈2,008 字符）** 时 `RecursionError`（默认 limit 1000）；`QueryCursor.captures()` 不递归、恒正常。→ 这也是 opencode 的写法（`descendantsOfType("command")`）。
   > [grill 更正] 首版写「~1,300 字符」，实测触发点约 **2,000 字符**（1,808 字符仍 OK）。
2. **`has_error` 与 `is_missing` 都要查**：`rm -rf !(keep)` 实测 `has_error=True`、**无 ERROR 节点**，唯一异常信号是零宽 `is_missing` 的 `;`（位置 `[8:8]`）。
   > [grill 更正] 首版写「`has_error` 不够、只产生 MISSING」，措辞与实测相反——`has_error` **已经**是 True。仍须查 `is_missing` 的理由是**区分**「可安全降级的畸形」与「完全不可信」，且此时 `(command)` 捕获退化为 `['rm -rf !', 'keep']`（argv 是垃圾），evaluator 绝不能信。
3. **解析器从不抛异常**：空串 / 纯空白 / 未闭合引号 / NUL 字节 / `$((` / 超深嵌套全部返回带 `has_error` 的 tree。

**不复制 opencode**：opencode 的 `parse()` 只查 `if (!tree)`，**全文 grep `hasError` 零命中**——畸形输入静默少解析出命令。对 deny 型护栏正是要修的 bug 类。

### D2：IR 的字段集由「所有 evaluator 需要什么」反推

**决策**：单一 IR（`BashAnalysis` / `CommandSegment`），**任一 evaluator 不得绕过 IR 重新解析原文**：

| 字段 | 消费方 | 为什么必须在 IR 里 |
|---|---|---|
| `segments[]`（命令段） | 全部 | 替代三次重复回答 |
| `argv[]`（命令名 + 参数） | `rm`/`mv`/`cp`/`chmod`/`curl`/`wget`/**`dd`**/`tee` | 目标必须准确 |
| **`write_targets[]`** | 写类 evaluator | **[grill 新增]** 目标**不一定**是 `argv[-1]`：`cp -t .env x`、`mv --target-directory=.env x`、`dd of=.env`。由 per-command spec 从 argv 解析出「写目标」，位置规则不再是「最后一个参数」 |
| `redirects[]`（fd、操作符、目标） | 重定向 evaluator | 替代独立 token 扫描 |
| `env_assignments[]` | wrapper 处理 | `FOO=bar cmd` |
| `dynamic_words`（bool + 位置） | 失败策略 | 动态词是「不可分析」的信号 |
| `parse_errors`（bool + 位置 + `is_missing`） | 失败策略 | fail-closed 触发条件 |
| `unsupported_nodes[]` | 失败策略 | zcode 口径 |
| **`heredoc[]`（delim、body 节点、绑定到哪个 fd / 哪个命令）** | 失败策略 | **[grill 新增]** 见 D4 |
| `source_span` | 报错 / trace | 定位 |

**IR 构造规则**：容器节点（`list` / `pipeline` / `redirected_statement`）透明展开；`command` 节点产出一个 segment；`variable_assignment` / `file_redirect` / `heredoc_redirect` 从 argv 剔除但记入各自字段。

### D3：决策模型从二态扩展为三态 `allow / deny / ask`

**决策**：`CommandVerdict` 增加 `ASK`，路由到审批层。

**理由**：业界三态是共识——codex `Decision::{Allow, Prompt, Forbidden}`（`execpolicy/src/decision.rs:9-16`）、Gemini CLI `allow/deny/ask_user`、OpenHands `SecurityRisk` + `ConfirmationPolicy`、opencode 审批提示。只有 allow/deny 会把「不确定」错误地压成「放行」（当前漏报的根源）。

**改造面**（[grill 更正] 首版严重低估——「只新增一个调用点」是错的）：实测 `BashTool` 与 `Tool` 基类**都没有** approval 引用，`AgentLoop` 只在工具**执行前**、按 `ToolPermission` 元数据决定是否审批，看不到 `cmd`。因此至少需要：

1. `BashTool` 增一条**执行中**请求审批的通路（构造期注入回调，先例见 `bash.py:57-58` 的 `run_in_background_cb` 注入，但那条只在 `background_manager is not None` 时可用，需一条无条件路径）。
2. 一个能由 `CommandVerdict` + `cmd` 构造审批请求的路径（`build_approval_request` 现在强制要 `PermissionDecision`，`approval.py:123-149`）。
3. **3 处内部早返回改为 ASK 透传**（`command_guard.py:381/439/451` —— 它们今天在「非 DENY」时落到 `return ALLOW`，正是「不确定静默压成放行」的现成实现）+ 2 处递归传播点。
4. **可观测性**：`loop.py:917-952` 的 `approval_required`/`approval_granted` 事件来自执行前那一层，执行中的第二次审批**不会**进 trace —— 需新增事件（加法）。

**各运行时下的 `ask` 行为必须分别陈述**（首版只提 CLI/FailClosed）：

| 运行时 | handler | `ask` 实际行为 |
|---|---|---|
| 交互 CLI | `CliApprovalHandler(interactive=True)` | 弹 `Approve? [y/N]` |
| 非交互 CLI / TTY 不可用 | 同上 → `UNAVAILABLE`（`approval.py:101-106`） | **拒绝** |
| Web | `web/session.py:158` | 弹卡片（同 session 已有 pending 时二次请求降为 `UNAVAILABLE`，`session.py:159-164`） |
| benchmark | `benchmarks/agent_runner.py` **不传 handler** | 恒 `FailClosed` → **拒绝** |

### D4：未知与失败策略 —— fail-closed，且**命令替换无论位置都递归判定**

**决策**：

| 触发条件 | 处置 | 依据 |
|---|---|---|
| `parse_errors`（`has_error` 或 `is_missing`） | **ask**（且**禁用 argv**，见 D1 约束 2） | kimi `unanalyzable → ask` |
| `unsupported_nodes` | **ask** | zcode `isBashCommandPermissionSafe` |
| 嵌套 shell 超深度上界 | **ask**（停止解包，不无界递归） | codex 超界后不再逐段判定 |
| 解析预算耗尽 | **ask** | kimi `ParseBudget`（50ms / 50k 节点） |
| 后端不可用 | **deny** | 深寻 `SANDBOX_UNAVAILABLE` |
| **命令替换 / 进程替换 / 反引号**（`$(...)`、`` `...` ``、`<( )`） | **无论出现在哪个位置都递归判定其内部命令；内部命中 deny 则整体 deny** | **[grill 修正]** 首版写「非目标位置 ⇒ allow」，会把 `echo $(rm -rf /tmp/x)` 放行——参数位的命令替换**照样执行代码** |
| 变量 / glob / brace 展开，**出现在写目标位置**（含 `-t` / `--target-directory` / `of=` 携带的目标） | **归一化后命中敏感名/受保护路径 ⇒ deny；否则 ask** | 见 D8；[grill 修正] 首版在 D4 说 ask、D8 说 deny，自相矛盾 |
| 同上，**出现在非目标位置** | **allow**（记入 IR） | 避免 `echo "$PATH"` 全去审批 |
| **heredoc / herestring 正文** | **默认是数据（allow）**；若绑定到**解释器**（`sh`/`bash`/`zsh`/`ksh`/`dash`/`python*`/`node`/`perl`/`ruby`/`php`/`awk` 及其 `-s` / `-` 变体）的 stdin，则**正文按命令递归判定** | **[grill 修正 — 本项是本 change 最重要的一处]** 见下 |

**heredoc 规则的必要性（grill 拦下的安全回归）**：`bash <<EOF` + `cp x .env` + `EOF` 今天被 deny（**靠的是分词器误报的巧合**）。首版 D2 规则「heredoc 正文不产生 segment」会让 tree-sitter 只产出 `bash` 一个命令 → 未知命令 → **allow**。即「修一个误报」直接换来「一个真漏报」，且泄露面更大（正文可含任意代码）。`attacks.json` 里只有 `python3 - <<PY` 一条，所以「拦截数不下降」也抓不到。

修正后的规则需 IR 记录 heredoc 的**绑定关系**（D2 的 `heredoc[]` 字段），由 evaluator 判断消费方是不是解释器。

### D5：能力范围声明（本 change 的核心交付物）

**措辞必须可证伪**：每条 guarantee 对应**真实存在**的测试；不保证的形态明确写「不分析」。

> [grill 更正] 首版矩阵的「测试证据」列 12/16 行引用了**不存在的测试名**（如 `test_chain_each_segment_checked`、`test_launcher_family`），其中 6 行未标「（新增）」，读起来像既存证据——**把待办伪装成证据**。本版只列**当前真实存在**的测试；待补的行标 `(新增)` 并在 tasks 中跟踪。

**责任表（按执行后端分列）**

| 层 | 承诺 | 明确不承诺 |
|---|---|---|
| **命令护栏** | 对**已正确解析**的命令结构：识别受保护路径写入、敏感点目录写入（含重定向与 `dd of=` 目标）、递归强制删除越界、管道到 shell、解释器内联求值、文件外传；对无法分析的形态给出显式 `ask`/`deny` | 不模拟执行、不追 fs 状态、不防语法层以下的混淆（如 base64 编码 payload）、**不构成 OS boundary** |
| **`ProcessBackend`（默认）** | 进程启动、超时、可选 cgroup v2 内存/CPU 限制 | **无文件系统隔离、无网络隔离、无提权限制**（实测 `grep -rnE "landlock\|bwrap\|seccomp\|unshare" agent/` 零命中）。默认配置下**不存在**文件/网络边界 |
| **`DockerBackend`（opt-in）** | `--network none`（无网络）、只挂载 workspace 到 `/workspace`（`docker_backend.py:101-113`）、`--rm` | 容器内 rootfs 可写（无 `--read-only`）、以 root 运行（无 `--user`）、未 drop capabilities（无 `--cap-drop`）——**partial**，需如实标注 |
| **审批层** | 把 `ask` 呈现给人类并按答复放行/拒绝；无 UI 时拒绝 | 不判断命令语义；不保证人类看清了命令（UI 截断是已知攻击面） |

**输入形态矩阵**（「测试证据」列只写**当前存在**的用例；括号内为 `tests/agent/tools/test_command_guard.py` 的真实测试名）

| 输入形态 | Guard | Backend（默认 process） | 测试证据 |
|---|---|---|---|
| simple argv | allow（未知命令默认放行） | 无隔离 | `test_basic_command`, `test_unknown_command_allowed`, `test_pytest_allowed` |
| 命令链 `&& \|\| ; \| &` | 每段独立判定 | 无隔离 | `TestChainedCommandSegments`（类） |
| 换行分隔 | 每行独立判定 | 无隔离 | `test_normalizes_workspace_path` 所属类 |
| 分组 `( )` `{ }` | 组内命令照样判定 | 无隔离 | `TestShellKeywordAndGrouping`（类，含 `test_inline_eval_denied`） |
| shell 关键字 | 剥离后判定真实命令 | 无隔离 | `TestShellKeywordAndGrouping` |
| wrapper `env`/`command`/`nohup` | 剥离后判定真实命令 | 无隔离 | `TestWrapperForms`（类） |
| launcher 前缀 | **兜底策略**（D8），非穷举 | 无隔离 | `(新增)` `test_launcher_fallback_ask` |
| `bash -c` / `sh -lc` | 解包 payload 递归判定 | 无隔离 | `TestShellDashCPayload`（类） |
| **heredoc 绑定解释器** | **正文按命令判定** | 无隔离 | `(新增)` `test_heredoc_into_interpreter_denied` |
| heredoc 绑定非解释器 | 正文是数据 ⇒ allow | 无隔离 | `(新增)` `test_heredoc_body_is_data` |
| 命令替换 `$(...)` / 反引号 | **无条件递归判定** | 无隔离 | `TestCommandSubstitution`（类，含 `test_echo_substitution_rm_denied`） |
| 进程替换 `<( )` `>( )` | 同上 | 无隔离 | `(新增)` `test_process_substitution` |
| 重定向 `>` `>>` `2>` | 目标判定，**含敏感点目录**；`/dev/null` 族豁免 | 无隔离 | `TestRedirect`（类）, `test_redirect_to_etc_denied`, `test_redirect_to_devnull_allowed` |
| 变量/glob/brace 在写目标位 | 归一化后命中 ⇒ deny，否则 ask | 无隔离 | `(新增)` `test_dynamic_write_target_policy` |
| 绝对路径 / 符号链接 | 按分量边界 + 规范化 | 无隔离 | `TestPathContainment`（类） |
| `rm`/`cp`/`mv`/`chmod`/`curl`/`wget` | argv 语义检查（含 `-t`/`--target-directory`） | 无隔离 | `TestCommandGuardDeny`（类） |
| **`dd`** | `of=` 目标判定 | 无隔离 | `(新增)` `test_dd_of_target` |
| **`tee`** | 目标判定 | 无隔离 | `(新增)` `test_tee_target` |
| 网络 | 只识别 `nc` / `/dev/tcp` 字面模式 | **无隔离（默认）**／Docker 下 `--network none` | `TestExtraDenylist`（类） |
| 子进程与资源耗尽 | 只识别 fork bomb 字面模式 | cgroup v2 内存/CPU（可选） | `test_cgroup`（`tests/agent/tools/`） |
| 解释器内联求值（`node -e` / `python -c`） | 字面模式 + 待补的选项感知 | 无隔离 | `test_node_e_denied` + `(新增)` 长选项变体 |

**明确不声称能防**（写进 spec，防止声明被写乐观）：
- CVE-2025-54794（路径前缀匹配）：靠 D7 的规范化处理，**不是**解析器的功劳。
- CVE-2025-55284（allowlist 过宽）：**策略问题，本层不声称**。
- CVE-2025-59536（信任对话框前执行）：**决策时序问题，本层不声称**。
- 编码/加密后的 payload、绕过 `argv` 表达的对抗输入。

### D6：三方职责边界 —— 并如实说明默认配置下没有边界

**决策**：guard 产出决策，审批层消费 `ask`，执行后端是**可选的**边界。spec delta 明确：护栏 **不**因判定 `allow` 而绕过后端；`allow` 只表示「护栏没有理由阻止」，**不**表示「安全」。

**必须写清的两层关系**（[grill 新增] 首版遗漏）：

- `bash.py:68` 的 `workspace_policy.assert_command_allowed` 在护栏**之前**运行，命中即硬拒，护栏不执行。`DEFAULT_DENYLIST` 被两层各跑一遍（语义不同）。本 change **不合并**这两层，但要在 spec 中写明顺序与各自的覆盖面，并**不得**把「被 workspace_policy 拒掉」记成「护栏的功劳」。
- 因此 D4 里「`$(...)` ⇒ 递归判定」对某些形态**不可达**（它们已被 `workspace_policy` 硬拒）。spec 要如实描述，不能让读者以为护栏覆盖了它。

**并且必须承认**：默认 `ProcessBackend` 不提供文件/网络边界。能力范围声明不得用「后端兜住」掩盖——这是 D5 用 grep 实测更正的核心。

### D7：路径判定继续按分量边界 + 规范化，解析器不替代它

保留 `_normalize_path` / `_within` / `_is_device_exempt` 的既有语义（#247 建立），作为消费 IR argv 的 evaluator 逻辑。**依据**：CVE-2025-54794 与 Gemini CLI 的 `startsWith` bug 属同一类，换任何解析器都防不住，只能靠 canonicalization + 分量边界。这条要写进能力范围声明。

### D8：已知残余收口

**甲类**（launcher + 写命令）—— [grill 更正]**不再用穷举表**：

首版列的 9 个 launcher 是开集里的 9 个点。实测 `doas` / `unshare -m` / `nsenter` / `script -q` / `ionice` / `watch` / `strace` / `setpriv` / `chrt` / `systemd-run` / `runuser` / `setarch` / `perf` / `ltrace` 全部 allow。且 wrapper × launcher 交叠（`nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env`）也漏——剥离循环没有交替到不动点。

改用的策略（三选一，**需用户拍板**，见 Open Questions）：
- (a) 穷举补表 —— **已证伪**，任何单条缺失即证伪整个属性；
- (b) **未知前导 token ⇒ ask**（属性可证、噪音大）；
- (c) **已知安全前导白名单 + 其余 ask**。

无论选哪个，**剥离循环必须 wrapper/launcher 交替到不动点**（这条是确定的，不依赖 (a)(b)(c)）。

**乙类**（混淆形态）—— 判定：**修**。目标先归一化（去反斜杠转义、展开字符类与 brace），再用 `fnmatch` 反向匹配敏感名。**反例不可破**：`.env.example` / `.gitignore` / `.github/` 必须保持放行。

**grill 新发现的三类**（首版未列）—— 判定：

| 类别 | 命令 | 处置 |
|---|---|---|
| 重定向写敏感点目录 | `echo X > .env`、`cat payload > ~/.ssh/authorized_keys` | **修**：重定向 evaluator 复用 `_dest_is_sensitive`。`authorized_keys` 覆写是持久化后门，且默认后端无文件系统边界 |
| 目标经选项传递 | `cp -t .env x`、`mv --target-directory=.env x` | **修**：D2 的 `write_targets[]` |
| `dd` / `tee` 无 evaluator | `dd of=.env`、`tee ~/.ssh/authorized_keys` | **修**：补目标判定 |

**`eval` 引号载荷** —— 判定：**修**。`eval 'cp x .env'` allow 而 `eval cp x .env` deny，说明字符串载荷没有被再解析。做法：把「字符串型载荷」统一到同一机制（`-c` 的 payload、`eval` 的 argv[1]、`env -S` 的 value）。若实现成本过高，则从声明中**删除 `eval`** 并写明「不分析」——但**不得**声明覆盖而不实现。

### D9：全文 denylist 通道**不能**降级为 evaluator——它承载 34/54 条攻击用例

**决策**（[grill 新增，首版的方向性错误]）：保留一条**字面模式通道**，但明确它的身份与边界。

实测：清空 `_denylist` 后攻击集 deny 数 **54 → 20**。这 34 条（`priv-esc-001..008`、`code-exec-001/002/003/007/008/009/010/012`、`exfil-002`、`resource-001..003`、`bypass-002..009`）**只**被全文正则拦下。它们多数是「按 IR 无法表达的整句模式」（`shutdown`、`mkfs.`、`killall`、fork bomb、`$IFS`、`\\[a-z]\s`）。

因此本 change 的真实目标不是「消灭全文正则」，而是：
- 把**能从 IR 表达**的语义（路径、目标、重定向）**移到 evaluator**；
- 把**不能表达**的整句模式**保留为一条显式的字面通道**，在 spec 里写明它是「深度防御的字面层」而非「解析层」，且**不重复实现**已由 evaluator 覆盖的语义（消除双实现等价性负担的是这部分）。

**验收口径随之修正**：不再是「全文正则消失」，而是「**同一语义不再有两个实现**」——可用「手工维护的等价性对数 == 0」度量（见 D10）。

### D10：度量与迁移（[grill 新增]）

**度量修正**：首版的「模块级常量数下降」是**不诚实**的弱代理（实测：常量数 15 → 估计 13–18，持平；且可把常量搬进 dict 无成本刷低）。改用三条可机械验证的指标：

1. **「从原文重推 argv 的入口数 == 1」**：断言只有 `bash_ir.py` 加载 tree-sitter，任何 evaluator 不再调 `re.split` / `tokenize_command` / 自己的 offset 切分。
2. **「手工维护的等价性对数 == 0」**：同一语义（如「敏感目标」）只在一处定义，其余引用它。
3. **代码量三栏对照**：`bash_ir.py` 新增 LOC / `command_guard.py` 删除 LOC / net。**如实报告**：预估 net 为 **577 → 600–800 行**（重写不是删除），不粉饰。

**迁移与回归对冲**（首版缺失）：重写一个经 9 轮审阅才稳定的安全护栏核心，**必须**有新旧对拍窗口：

- 对 `benchmarks/attacks/attacks.json` 全量 + 现有 81 个 guard 单测的命令串做**旧 vs 新 verdict 对拍**，断言 **旧 DENY ⊆ 新 DENY ∪ 新 ASK**（沿用 `workspace_policy` 修订版对拍思路）。
- 提供**回退开关**（环境变量）在重构期内可切回旧实现，直到对拍全绿。
- 对拍报告作为本 change 的验收证据之一。

**攻击集断言的配套修改**：`tests/benchmark/test_attack_suite.py:46` 现在断言 `is CommandVerdict.DENY`；三态引入后需定义 **ASK 是否计入「被拦截」**（见 Open Questions）。`tests/agent/tools/test_command_guard.py` 中 `assert verdict in (ALLOW, DENY)` 形态的断言会因新枚举值变红，需同步。

### D11：本 change 明确不做

- 不实现 OS 级沙箱（但如实声明默认后端无边界）。
- 不合并 `workspace_policy` 与 `command_guard` 两层（只写清关系）。
- 不做「护栏判定 allow 则 bypass sandbox」（codex 的 `bypass_sandbox` 机制本 change 不引入）。
- 不为 launcher 表做穷举（改用兜底策略）。

## Pre-Implementation Review

本 change 属 design 类（primary: refactor）。**首轮 grill 已完成**（4 个独立零记忆 subagent，视角：绕过面 / 成本 / 可行性 / 证据审计），产出 `reviews/grill-design.md`，发现 9 项阻塞问题并已在 v2 design 中修订。**实现前仍需用户确认 Open Questions**。

**已由 grill 关闭的争议**（见 `## Confirmed Decisions`）：D1 选型的数据基础、D1 两条实现约束、D3 三态必要性与真实改造面、D7 路径判定独立性、D9 全文通道的不可替代性。

**grill 后新增的、需用户拍板的问题**见 `reviews/grill-design.md` 的 `## Open Questions`。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| **本次重构静默降低拦截能力** | 攻击集 34 条依赖全文通道，改错即回归 | D9（保留字面通道）+ D10（新旧对拍 + 回退开关 + `旧 DENY ⊆ 新 DENY ∪ 新 ASK` 硬断言） |
| **`ask` 在无 UI 环境等于 deny** | benchmark / CI / 非 TTY CLI 下，含动态词语命令**全部失败**，pass rate 可能归零 | D3 的运行时矩阵必须如实写；具体分配由用户拍板（Open Question） |
| **默认后端无边界这一事实被披露后削弱叙事** | 「护栏 + 后端 = 双层防御」在默认配置下不成立 | 这正是能力范围声明要说的真话；不得美化（D5/D6） |
| 重写核心安全模块的回归风险 | 9 轮审阅才稳定的语义可能被改坏 | D10 的双跑对拍 + 回退开关 |
| `ask` 交互噪音 / 审批疲劳 | 攻击者可用一次「y」换持续放行；长前缀命令可把敏感目标推出截断区 | D4 尽量把能静态判定的做成 deny；审批 UI 的截断问题记为已知限制 |
| IR 构造本身是新 bug 面 | grill 的 140 行原型第一次就把 redirect 提取写错（`file_redirect` 有两种父节点） | 字段级契约测试（不只「同语义 ⇒ 同 IR」，还要 per-field 断言） |
| launcher 兜底策略的噪音 | 选 (b)/(c) 会把非 launcher 的未知前导拉去审批 | 由用户拍板；白名单可迭代 |
| `has_error` 输入下 argv 退化为垃圾 | `rm -rf !(keep)` 捕获成 `['rm -rf !', 'keep']` | D4：`parse_errors` 命中即 **禁用 argv** 并 ask |

## Testing Strategy

**测试先行**，分层：

1. **IR 契约层**：同语义不同写法 ⇒ 同 IR（`rm -rf /` 族）；**且 per-field 断言**（redirect / env_assign / dynamic / heredoc 绑定 / write_targets 各自单独断言，不只比整树）。
2. **解析器层**：`has_error` 与 `is_missing` 双信号；永不抛异常（空串/空白/未闭合引号/NUL/超深嵌套）；预算与深度上界返回确定处置；**枚举命令节点不得递归**（~2,000 字符 `$(( ))` 不抛 `RecursionError`）。
3. **evaluator 层**：既有 81 个 guard 测试按「语义等价输入族」重组；`write_targets` 覆盖 `-t` / `--target-directory` / `of=`。
4. **策略层（fail-closed）**：各失败形态的处置 + **反例**（不得静默放行）；命令替换**任意位置**都递归判定。
5. **攻击集回归**：`benchmarks/attacks/attacks.json` **只增不减**，新增 heredoc→解释器、launcher 兜底、混淆形态、重定向敏感点目录、`dd`/`tee` 目标、CVE-inspired；**拦截数不下降**（含 ASK 的计数口径定义）。
6. **对拍/迁移**：D10 的旧 vs 新 verdict 对拍，`旧 DENY ⊆ 新 DENY ∪ 新 ASK`。
7. **能力范围声明一致性**：声明的每一行「测试证据」必须能被 `pytest --collect-only` 解析到（可在 `tasks.md` 6.1 加一条校验）。
8. **CI**：全量 pytest、OpenSpec strict validate、artifact checker、benchmark smoke。

## 技术选型对比实验（方法与数据）

**语料**：151 条 = `attacks.json` 全部真实攻击用例 + `test_command_guard.py` 中真实出现的命令串 + issue #254 点名的对抗类（launcher / 混淆 / 命令替换 / 进程替换 / heredoc / 分组与关键字 / wrapper / 动态词）+ 15 条良性复杂命令。

**方法**：对每条跑 (a) `tokenize_command` + `_check_command_text`、(b) `tree_sitter_bash` + `Query("(command) @c")` + `QueryCursor`、(c) `bashlex.parse`；代表样本测延迟（300 次均值）。

**脚本与产物**（可复现，[grill 修正] 首版只存了 JSON、没存脚本）：`research/gen_corpus.py`（生成语料）、`research/compare_parsers.py`（跑对比）、`research/parser-comparison-rows.json`（逐条结果）。

**结果**：

```
tree-sitter has_error: 0/151        bashlex raised: 5/151
latency: tokenizer 0.016 ms | tree-sitter 0.040 ms | bashlex 0.813 ms
结构分歧（tok_n != ts_n）: 23/151，集中在 substitution(6)/grouping(6)/heredoc(4)/dynamic(3)
```

**结构对比代表片段**（`|` 分隔 tree-sitter 恢复的命令，`;` 分隔当前分词器的「段」）：

| 命令 | 当前分词器 | tree-sitter-bash |
|---|---|---|
| `cat <<'EOF'` + `cp x .env` + `EOF` | `cat<<EOF ; cp x .env ; EOF` | `cat`（正文是数据 → 但见 D4 的绑定规则） |
| `cp x ~/.{ssh}/f` | `cp x ~/. ; ssh ; /f` | `cp x ~/.{ssh}/f` |
| `diff <(a) <(b)` | `diff < ; a ; < ; b` | `diff <(a) <(b)` \| `a` \| `b` |
| `echo ${PATH}` | `echo $ ; PATH` | `echo ${PATH}` |
| `x=$(rm -rf /)` | `x=$ ; rm -rf /` | `rm -rf /` |
| `cmd 2>&1 \| tee /etc/passwd` | `cmd 2 > ; 1 ; tee /etc/passwd` | `cmd \| tee /etc/passwd` |

**结论**：当前分词器不只是「漏掉」`$()`/heredoc/进程替换，而是**静默误切**——同时制造假阳性（heredoc）与假阴性（brace）。延迟不构成选型理由，错误模型与自维护代码量才是。`bashlex` 因「抛异常 + 空串 `AttributeError` + 3.5 年未维护 + GPL-3.0」排除。
