# Design: Bash 命令护栏的单一解析管线与能力范围声明

> **本版是 grill 后并用户拍板后的修订版（v3）**。首版 design 经 4 个独立零记忆 subagent 以不同视角（绕过面 / 成本 / 可行性 / 证据审计）追问，发现 9 项阻塞问题，其中一项是**首版自身会引入的安全回归**。修订内容与证据见 `reviews/grill-design.md`；下文凡经 grill 更正的结论均标注「[grill]」。
>
> **v3 变更**：grill 遗留的 5 条 Open Question 已由用户于 2026-09-30 拍板（`reviews/grill-design.md` 的 `## User Confirmation`），结论已回写进 D3 / D4 / D6 / D8 / D9 / D10 并新增 **D12**。Q3 经三轮补测（用户追问「调试配 API key 怎么写 `.env`」引出）新增了三条范围：**凭据变体 deny**、**模板读写豁免**、**敏感 dot 名三处定义收敛为共享谓词**。证据见 `reviews/grill-settled.md`。下文凡经用户拍板的结论均标注「[Q<n>]」。

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

**`ask` 的分配口径（[Q1] 用户拍板：分层）**：

对「无法确定」的形态，**不一律 deny 也不一律 ask**，而是**先归一化再分层**：

| 情形 | 处置 |
|---|---|
| 归一化（含乙类展开：去反斜杠、展开字符类与 brace）后**命中敏感名 / 受保护路径** | **deny** |
| 归一化后**未命中** | **ask** |

确认的判据示例：`cp x ~/.{ssh}/f` 展开后命中 `.ssh` ⇒ **deny**（不是 ask）。**归一化必须先于 deny/ask 分流**——否则 `~/.{ssh}/f` 会落到 `ask` 而非 `deny`。

**为什么分层而不是一律 deny**：`ask` 在**无 UI 运行时恒等于 deny**（下表），因此「命中敏感名 ⇒ deny」与「一律 deny」在 CI / benchmark 下**结果完全相同**；分层只在**有人的交互环境**放松成 `ask`，且只对**非敏感**目标放松。可用性代价被精确限定在「有人看着、目标不敏感」的角落，而 `cp $SRC $DST` 这类常见动态写目标不会在所有环境直接失败。

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
| benchmark（默认 `--mode build`） | 运行器不传 handler | **护栏根本执行不到**：见下 |
| benchmark（`--mode bypass`） | 同上 → `FailClosed` | **拒绝** |

> **[Q1 更正] benchmark 一行要限定模式**。实测：`Bash` 声明 `dangerous=True` + `COMMAND_EXECUTE_PERMISSION`（HIGH 风险，`bash.py:42-43`），`build_default` profile 的 `auto_approve_max_risk=MEDIUM`（`tool_permissions.py:148`），故 `decide_tool(Bash) = REQUIRE_APPROVAL`（`run_config.py:151`）；benchmark 不传 handler（`agent_runner.py:384`），`AgentLoop` 默认 `FailClosedApprovalHandler`（`loop.py:174`）。**默认配置下 Bash 在 loop 层就被拒绝、从不执行，护栏跑不到**。只有显式 `--mode bypass` 才让 Bash 无头执行，那里 `ask` = FailClosed = 拒绝。首版「benchmark 下 `ask` 会让含动态词的命令全部失败、pass rate 归零」的表述**只在 `bypass` 模式成立**。

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
| **heredoc / herestring 正文** | **默认是数据（allow）**；若绑定到**解释器**（`sh`/`bash`/`zsh`/`ksh`/`dash`/`python*`/`node`/`perl`/`ruby`/`php`/`awk` 及其 `-s` / `-` 变体）的 stdin，则**正文全量按命令递归判定** | **[grill 修正 — 本项是本 change 最重要的一处]** 见下 |

**heredoc 规则的必要性（grill 拦下的安全回归）**：`bash <<EOF` + `cp x .env` + `EOF` 今天被 deny（**靠的是分词器误报的巧合**）。首版 D2 规则「heredoc 正文不产生 segment」会让 tree-sitter 只产出 `bash` 一个命令 → 未知命令 → **allow**。即「修一个误报」直接换来「一个真漏报」，且泄露面更大（正文可含任意代码）。`attacks.json` 里只有 `python3 - <<PY` 一条，所以「拦截数不下降」也抓不到。

修正后的规则需 IR 记录 heredoc 的**绑定关系**（D2 的 `heredoc[]` 字段），由 evaluator 判断消费方是不是解释器。

> **[Q2 用户拍板：选 (a)「正文全量按命令判定」，接受误报]**。曾考虑的更窄规则 (b)「只对正文归一化后命中敏感名/受保护路径才拦」被实测否决：
> - **收益为零**：在 16 个真实风格的 heredoc 脚本（构建 / 部署 / CI / db-migrate / 测试）上，(a) 与 (b) 结果**逐条相同**——4 条 deny **全部来自 D9 保留的字面通道**，与 heredoc 规则无关。(a) 相对 (b) 的**额外误报实测为 0**。
> - **代价是 7 条已验证的漏报**：`rm -rf $HOME`、`dd of=$DEST`、`cp -t $T`、`mv --target-directory=$D`、`rm -rf $BUILD`、`tee $OUT`、`rm -rf $ROOT/../etc` 在 (b) 下全部降级为 allow 或从 DENY 降为 allow —— 它们的共同特征是**目标被动态化（变量 / 相对路径）**，归一化后不命中任何敏感名。
> - 注意：`bash <<EOF` + 正文 + `EOF` 的正文判定必须落到 **evaluator**（含 `_check_rm` 的 `$HOME` / `~` / `/` 特例），不能依赖字面通道兜底，否则字面通道一抖就漏。

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
| **`.env` 凭据变体**（`.env.local` 等） | 由共享谓词判 deny（D12） | 无隔离 | `(新增)` `test_env_credential_variants_denied` |
| **`.env` 模板**（`.env.example` 等） | 读写豁免（D12） | 无隔离 | `(新增)` `test_env_template_exempt` |
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

> **[Q3 新增] 「敏感 dot 名」有**三份互不相关的定义**，本 change 收敛为一份（见 D12）**。
> 实测当前三处定义各写各的、已经漂移：
>
> | 定义处 | 载体 | `cp x .env.local` 的判定 |
> |---|---|---|
> | `workspace_policy.py:9-47` | `DEFAULT_DENIED_PATTERNS`（glob，读写共用 `is_denied`） | **过宽**：连模板 `.env.example` 一起拒 |
> | `workspace_policy.py:121-122` | 两条正则（**源位置锚定**） | 拦 `cp .env.local x`（源），但拦不到目标位 |
> | `command_guard.py:41-46` | `_SENSITIVE_DOTDIRS` / `_SENSITIVE_DOTFILES`（**精确相等**） | **过窄**：集合不含 `.env.local` ⇒ 目标位放行 |
>
> 「同一文件、两条通道、两种答案」的现成实例：`cp x .env.local` 在 Read/Write 工具下 DENY、在 Bash 护栏下 **ALLOW**。这直接违反 D9 的「同一语义 SHALL NOT 存在两个实现」——**单点修补必留新漂移**，所以三处必须一起收敛。

### D7：路径判定继续按分量边界 + 规范化，解析器不替代它

保留 `_normalize_path` / `_within` / `_is_device_exempt` 的既有语义（#247 建立），作为消费 IR argv 的 evaluator 逻辑。**依据**：CVE-2025-54794 与 Gemini CLI 的 `startsWith` bug 属同一类，换任何解析器都防不住，只能靠 canonicalization + 分量边界。这条要写进能力范围声明。

### D8：已知残余收口

**甲类**（launcher + 写命令）—— [grill 更正]**不再用穷举表**：

首版列的 9 个 launcher 是开集里的 9 个点。实测 `doas` / `unshare -m` / `nsenter` / `script -q` / `ionice` / `watch` / `strace` / `setpriv` / `chrt` / `systemd-run` / `runuser` / `setarch` / `perf` / `ltrace` 全部 allow。且 wrapper × launcher 交叠（`nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env`）也漏——剥离循环没有交替到不动点。

**采用的策略（[Q4] 用户拍板：选 (c')「已知安全白名单 + 限定 ask」）**：

- **(a) 穷举补表 —— 已证伪**：任何单条缺失即证伪整个属性（实测 `doas` / `unshare -m` / `nsenter` / `script -q` / `ionice` / `watch` / `strace` / `setpriv` / `chrt` / `systemd-run` / `runuser` / `setarch` / `perf` / `ltrace` 全部 allow）。
- **(b) 未知前导 token ⇒ ask —— 被实测噪音否决**：在 59 条真实开发命令上，它会把 **37 条（63%）** 今天 allow 的正常命令拉去审批（`pytest -q`、`git status`、`ls -la`、`make build`、`docker build`、`uv run pytest`、`terraform plan` …）。而 `ask` 在无 UI 环境等于 deny ⇒ 等于把所有未识别程序硬拒。审批疲劳本身即安全损失。
- **(c') 已采纳 —— 未识别前缀 ⇒ 仅当其后（滑窗内）跟着护栏真正会判的命令时才 `ask`**。实测：在同样 59 条真实命令上噪音 **0/59**；30 条 launcher 攻击族抓取 **29/30**（唯一漏的 `doas sh -c '…'` 见下条）。白名单只用于**减噪**（把已知良性程序从 ask 降为 allow），安全属性由「未知 ⇒ ask」承担——即便白名单被投毒（程序名叫 `git`），后果也只是从 ask 降为 allow，与今天的 default-allow 行为持平，**不构成回归**。

> **白名单的内容是维护承诺、不是实测事实**：「噪音 0」依赖给定的 124 项白名单，换一份数字会变；安全属性（未知 ⇒ ask，fail-closed）与白名单内容无关。

**剥离循环必须 wrapper/launcher 交替到不动点**（这条不依赖策略选择，是硬要求）：`nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env` 今天全 allow，必须修。

> **[新增] 剥离到不动点必须同时作用于 `-c` payload 通道**。实测 payload 提取（`command_guard.py:165` 的 `_shell_dash_c_payloads` → `_strip_wrappers`）只认 `env`/`command`/`nohup`/shell 关键字，**不剥 launcher**：`doas sh -c 'cp x .env'`、`nice bash -c 'cp x .env'`、`nohup setsid sh -c 'cp x .env'`、`unshare -m bash -c 'cp x .env'` **今天全 allow**；把 payload 提取放到**剥离到不动点之后的 argv** 上即可恢复为 DENY。这条是 `doas sh -c '…'` 未被 (c') 命中的根因。

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

> **[Q3 新增] 「同一语义单实现」的第一个具体实例：敏感 dot 名（见 D12）**。当前「什么算敏感 dot 名」有**三份定义**（`workspace_policy` 的 glob / 同文件的源位置正则 / `command_guard` 的 frozenset），三者对 `.env.local` 的判定互相矛盾。按本条 D9 的目标，它们 SHALL 收敛为**一份共享谓词**。
>
> 同时，本条要求把「能从 IR 表达」的语义移到 evaluator——`workspace_policy.py:121-122` 的 `\b(mv|cp)\s+<源>` 两条正则**正是这类**：「cp 的目标是谁 / 源是谁」由 IR 的 `write_targets[]` 与 argv 表达，字面通道不该再判一遍。迁移后，源位置的误伤（`cp .env.example /tmp/backup.txt` 今天被拦）**自然消失**。

### D10：度量与迁移（[grill 新增]）

**度量修正**：首版的「模块级常量数下降」是**不诚实**的弱代理（实测：常量数 15 → 估计 13–18，持平；且可把常量搬进 dict 无成本刷低）。改用三条可机械验证的指标：

1. **「从原文重推 argv 的入口数 == 1」**：断言只有 `bash_ir.py` 加载 tree-sitter，任何 evaluator 不再调 `re.split` / `tokenize_command` / 自己的 offset 切分。
2. **「手工维护的等价性对数 == 0」**：同一语义（如「敏感目标」）只在一处定义，其余引用它。
3. **代码量三栏对照**：`bash_ir.py` 新增 LOC / `command_guard.py` 删除 LOC / net。**如实报告**：预估 net 为 **577 → 600–800 行**（重写不是删除），不粉饰。

**迁移与回归对冲**（首版缺失）：重写一个经 9 轮审阅才稳定的安全护栏核心，**必须**有新旧对拍窗口：

- 对 `benchmarks/attacks/attacks.json` 全量 + 现有 81 个 guard 单测的命令串做**旧 vs 新 verdict 对拍**，断言 **旧 DENY ⊆ 新 DENY ∪ 新 ASK**（沿用 `workspace_policy` 修订版对拍思路）。
- 提供**回退开关**（环境变量）在重构期内可切回旧实现，直到对拍全绿。
- 对拍报告作为本 change 的验收证据之一。

**攻击集断言的配套修改（[Q5] 用户拍板：攻击集只允 `deny` + 另建「应 ask」用例集）**：

实测：既有 **50 条 guard-deny 攻击用例过新管线全部保持 DENY**（`50/50`，0 条翻 ASK，0 条翻 ALLOW），**因此 `tests/benchmark/test_attack_suite.py:46` 的 `is CommandVerdict.DENY` 断言对既有 54 条无需任何修改**。首轮探针曾报 2 条翻转（`cat file | sh`、`base64 -d <<< '…' | bash`），经查是仿真器漏建 `_has_pipe_to_shell`，补上后恢复 DENY。

真正会出 `ask` 的是**本 change 新增的 launcher 用例**（`nsenter`/`script`/`watch`/`setpriv`/`setarch`/`flock`/`perf` 形态）。因此：

- **攻击集（`attacks.json`）继续只允许 `deny`**——不把 `ask` 混进攻击用例。把攻击用例放宽到允许 `ask` 会让一个在 CI（FailClosed）下失败的用例，在交互式开发里变成「人类可能点 y」，**降低基线的语义强度**。
- **另建一组标注 `expected: ask` 的独立用例集**（如 `test_launcher_ask_suite.py`），断言 `is ASK`。
- **「被拦截」的计数谓词定义为 `verdict is not ALLOW`**——这是无回归线（D10 的 `旧 DENY ⊆ 新 DENY ∪ 新 ASK`）使用的谓词，比「`deny` 单独计数」更诚实（无 UI 环境下 `ask` 就是拦截），同时不与「攻击集只允 deny」的严格用例集冲突。
- `tests/agent/tools/test_command_guard.py` 中 `assert verdict in (ALLOW, DENY)` 形态的断言会因新枚举值变红，需同步。

### D11：本 change 明确不做

- 不实现 OS 级沙箱（但如实声明默认后端无边界）。
- 不做「护栏判定 allow 则 bypass sandbox」（codex 的 `bypass_sandbox` 机制本 change 不引入）。
- 不为 launcher 表做穷举（改用 (c') 兜底策略）。
- **不引入配置层写白名单**（`tools.allowed_write_paths`）。可行性已实测（`WorkspacePolicy` 已接受 `denied_patterns`，全仓只有 3 个生产构造点传配置，照 `tools.command_denylist` 先例约 6 行），但**用户拍板另开独立 change**——它与本 change 的爆炸半径无关，且需要两层同源改造。
- **不引入「模型自配白名单」**。实测代码 + 5 家参考实现（codex `exec_policy.rs:376` / opencode `permission.ts:250` / kimi `permissionRulesOps.ts:60` / pi `README.md:42` / zcode `bash-command-permission-policy.ts:171`）：**扩权一律由人类答复触发，模型只能提议**。理由见 D12 末节（安全论证）。

### D12：敏感 dot 名的单一谓词（[Q3] 用户拍板新增）

**决策**：本 change 把「什么算敏感 dot 名」收敛为**一份共享谓词**，三处定义全部改为消费它；同时按用户拍板**扩大 deny 范围到凭据变体**、**豁免模板类**。

**（1）deny 范围扩到凭据变体（本 change 新增范围）**。当前 `command_guard.py:44-46` 的 `_SENSITIVE_DOTFILES` 是**精确相等**集合，不含 `.env.local`。实测因此产生的真洞（**不是理论风险，是今天可执行的**）：

```
cp src.txt .env.local        gate1(workspace_policy)=PASS  gate2(guard)=allow  write-gate=DENY  => EXECUTES
cp src.txt .env.production   gate1=PASS  gate2=allow  write-gate=DENY  => EXECUTES
tee .env.local               gate1=PASS  gate2=allow  write-gate=DENY  => EXECUTES
```

根因有二：`_dest_is_sensitive`（`command_guard.py:218-227`）**按 basename 精确相等**判定；且字面通道的否定前瞻 `(?![\w.-])`（`command_guard.py:263`）**显式排除**了 `.env` 后紧跟 `.` 的情形。两条通道同时漏掉所有 `.env.<后缀>`。而 `BashTool.execute`（`bash.py:68/73`）**只调 `assert_command_allowed` + `_guard.check`，从不调 `assert_write_allowed`**——所以「文件工具拒绝、Bash 通道执行」的组合是真实的凭据投毒路径。`.env.local` / `.env.production` 是 django / vite / Next.js 社区最常见的真实凭据文件。

**新增 deny 的变体**：`.env.local` / `.env.production` / `.env.development` / `.env.test` / `.env.staging` / `.env.secret` / `.env.keys`，以及任何**非模板**的 `.env.<后缀...>`。

**（2）模板读写豁免**。豁免后缀集合 `{example, sample, template, dist, defaults, tpl}`。

**判据（可证伪形式）**：**`.env` 之后的每一个 `.` 分段都是模板词 ⇒ 模板（豁免）；有任何一段不是 ⇒ 凭据（deny）**。

```
.env                  -> 凭据（裸名即本体）
.env.local            -> 凭据
.env.example          -> 模板（豁免）
.env.sample/.template/.dist/.defaults/.tpl -> 模板（豁免）
.env.example.local    -> 凭据（分段含凭据词）   ← 关键边界
.env.local.example    -> 凭据
.env.production.sample-> 凭据
.env.j2               -> 凭据（j2 不在模板词表）
.env.example.bak      -> 凭据
.envrc/.environment/app.env/config.env/my.env/.env2/.env-file -> 不在 `.env.*` 模式内，不受影响
```

边界实测 **0 错**（11 条 lookalike 全部不误伤、10 条凭据变体全部 deny、6 条模板全部豁免）。**模板的「写」也一并豁免**（`is_denied` 是读写共用的单一谓词）：新增一个必需变量时要更新模板，这是常规开发动作；如实声明即可。`.env` / `.env.local` 的写仍 DENY。

**为什么模板该放行读**：`.env.example` 按规范必须进 git、对任何有仓库读权限的人可见——护栏拦不住「已提交的真值」（那是 secret scanning 的职责）。而现状是 agent **连「这个项目该配哪些环境变量」都读不到**，只能猜，与 #248「照着示例写却被拒」同类。参考实现 opencode 把这件事**显式编码成三条有序 read 规则**（`packages/core/src/plugin/agent.ts:115-117`：`*.env`→ask、`*.env.*`→ask、`*.env.example`→allow，**最后命中者优先**），并有对应测试表（`packages/opencode/test/tool/read.test.ts:263-270`）。

**（3）共享谓词——这是 D9 的直接实例**。三处定义**必须一起收敛**，单点修补必留新漂移：

| 消费方 | 现状 | 改为 |
|---|---|---|
| `workspace_policy.DEFAULT_DENIED_PATTERNS`（读/写共用 `is_denied`） | glob 列表，过宽（含模板） | 消费共享谓词 |
| `workspace_policy.py:121-122` 的 `\b(mv\|cp)\s+<源>` 两条正则 | 源位置锚定，判「源」不判「目标」 | **迁移到 evaluator**（IR 的 `write_targets[]` 已表达），不再在字面通道重复实现 |
| `command_guard._SENSITIVE_DOTDIRS` / `_SENSITIVE_DOTFILES` | 精确相等集合，过窄 | 消费共享谓词 |

> **实现约束（实测，必须遵守）：不能用 glob 表达该谓词**。Python `fnmatch` **不支持 bash extglob**——实测 `fnmatch('.env.local', ".env.!(example|sample|template|dist|defaults|tpl)")` 返回 **False**（对 `.env.example` 也返回 False），即写成 extglob 会**把两边都放开**，是静默失效的写法。**必须是代码谓词**（分段判定），不得退化为 glob 字符串。

**为什么不选「模型自配白名单」**（用户提过的方向，被否决）：判定者（policy）与被判定者（agent）是同一主体时，权限系统**在定义上不存在**；且护栏拿到的是**命令文本**不是用户意图——提示注入写出的 `echo 'ssh-rsa …' >> ~/.ssh/authorized_keys` 与合法写 `.env` 在文本层同形，**一次提示注入即永久扩权**。五家参考实现一致：扩权由人类答复触发（见 D11）。用户想要的「不用每次手改配置」在 `ask` + 会话内记住的路径下几乎自动获得，无需新增模型可写通道。

## Pre-Implementation Review

本 change 属 design 类（primary: refactor）。

**grill 阶段已完成**：4 个独立零记忆 subagent（视角：绕过面 / 成本 / 可行性 / 证据审计）产出 `reviews/grill-design.md`，发现 9 项阻塞问题并已在 v2 design 中修订，另有 5 条 Open Question 停轮交用户。

**用户拍板已完成（2026-09-30）**：Q1–Q5 逐条答复由主 session 亲笔记录进 `reviews/grill-design.md` 的 `## User Confirmation`（含 Q3 的三条子决定）。**实现前的 grill gate 已放行**，`check_openspec_artifacts.py` 通过。

**拍板结论已回写本 design**（v3）：
- **Q1 → D3**：`ask` 分层口径（归一化命中敏感名 ⇒ deny，否则 ask），并更正 benchmark 运行时一行为「默认模式护栏跑不到，限 `--mode bypass`」。
- **Q2 → D4**：heredoc 绑定解释器时正文**全量按命令判定**（(a)）；(b) 的收益实测为零、代价是 7 条漏报。
- **Q3 → D6 / D9 / D12（新增）**：三条子决定——凭据变体 deny、模板读写豁免、三处定义收敛为共享谓词（含「不能用 glob」的实现约束）。
- **Q4 → D8**：(c') 已知白名单 + **限定 ask**（仅当未识别前缀后跟着护栏真正会判的命令）；剥离循环到不动点，且**必须同时作用于 `-c` payload 通道**。
- **Q5 → D10 / Testing Strategy**：攻击集只允 `deny` + 另建「应 ask」用例集；计数谓词 `verdict is not ALLOW`。

**Q3 经三轮补测**（用户追问「调试配 API key 怎么写 `.env`」引出），产出三条新增范围并已并入本 change；补测证据、被推翻的初版推荐、以及仍存的不确定性见 `reviews/grill-settled.md`。

**已由 grill 关闭的争议**（见 `reviews/grill-design.md` 的 `## Confirmed Decisions`）：D1 选型的数据基础、D1 两条实现约束、D3 三态必要性与真实改造面、D7 路径判定独立性、D9 全文通道的不可替代性。

**明确另开独立 change**（不属本 change）：配置层写白名单 `tools.allowed_write_paths`（见 D11）。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| **本次重构静默降低拦截能力** | 攻击集 34 条依赖全文通道，改错即回归 | D9（保留字面通道）+ D10（新旧对拍 + 回退开关 + `旧 DENY ⊆ 新 DENY ∪ 新 ASK` 硬断言） |
| **`ask` 在无 UI 环境等于 deny** | CI / 非 TTY CLI / benchmark `bypass` 模式下，含动态词语命令**全部失败** | D3 的运行时矩阵如实写；[Q1] 已限定为「非敏感目标才 ask」以把可用性代价压到最小；默认 benchmark 模式护栏跑不到（D3） |
| **默认后端无边界这一事实被披露后削弱叙事** | 「护栏 + 后端 = 双层防御」在默认配置下不成立 | 这正是能力范围声明要说的真话；不得美化（D5/D6） |
| 重写核心安全模块的回归风险 | 9 轮审阅才稳定的语义可能被改坏 | D10 的双跑对拍 + 回退开关 |
| `ask` 交互噪音 / 审批疲劳 | 攻击者可用一次「y」换持续放行；长前缀命令可把敏感目标推出截断区 | D4 尽量把能静态判定的做成 deny；审批 UI 的截断问题记为已知限制 |
| IR 构造本身是新 bug 面 | grill 的 140 行原型第一次就把 redirect 提取写错（`file_redirect` 有两种父节点） | 字段级契约测试（不只「同语义 ⇒ 同 IR」，还要 per-field 断言） |
| launcher 兜底策略的噪音 | 未知即 ask（(b)）会把 63% 的正常命令拉去审批 | [Q4] 已选 (c')：噪音 0/59，白名单可迭代；安全属性与白名单内容无关 |
| **敏感 dot 名三处定义漂移** | `.env.local` 在 Read/Write 下 DENY、在 Bash 护栏下 ALLOW（实测可用 `cp` 写入） | D12：三处收敛为一份共享谓词；D9 要求消除双实现 |
| **模板豁免被滥用为「放行真值」** | 有人把真值写进 `.env.example`，或造 `.env.example.local` 绕过 | D12：判据是「每一段都是模板词」⇒ `.env.example.local` 仍 deny；模板入 git 属既有问题，不是本层职责 |

## Testing Strategy

**测试先行**，分层：

1. **IR 契约层**：同语义不同写法 ⇒ 同 IR（`rm -rf /` 族）；**且 per-field 断言**（redirect / env_assign / dynamic / heredoc 绑定 / write_targets 各自单独断言，不只比整树）。
2. **解析器层**：`has_error` 与 `is_missing` 双信号；永不抛异常（空串/空白/未闭合引号/NUL/超深嵌套）；预算与深度上界返回确定处置；**枚举命令节点不得递归**（~2,000 字符 `$(( ))` 不抛 `RecursionError`）。
3. **evaluator 层**：既有 81 个 guard 测试按「语义等价输入族」重组；`write_targets` 覆盖 `-t` / `--target-directory` / `of=`。
4. **策略层（fail-closed）**：各失败形态的处置 + **反例**（不得静默放行）；命令替换**任意位置**都递归判定。
5. **攻击集回归**：`benchmarks/attacks/attacks.json` **只增不减**，新增 heredoc→解释器、launcher 兜底、混淆形态、重定向敏感点目录、凭据变体（`.env.local` 等）、`dd`/`tee` 目标、CVE-inspired；**拦截数不下降**（[Q5] 计数谓词 = `verdict is not ALLOW`）。
6. **「应 ask」用例集（[Q5] 新增）**：攻击集**只允 `deny`**；会出 `ask` 的新增形态（launcher 限定 ask）进独立用例集，断言 `is ASK`。
7. **共享谓词层（[Q3] 新增）**：敏感 dot 名的单一谓词须有 **per-field 契约测试**——判据是「`.env` 后每一段皆模板词」，**必须有对照组**（`.env.local` deny ↔ `.env.example` allow、`.env.example.local` deny ↔ `.env.example` allow、`.envrc`/`app.env`/`.env2` 不误伤）；并作**变异验证**：把谓词的模板词表改坏一个词，必须有测试变红（防止「三处又各写一遍」）。
8. **对拍/迁移**：D10 的旧 vs 新 verdict 对拍，`旧 DENY ⊆ 新 DENY ∪ 新 ASK`。
9. **能力范围声明一致性**：声明的每一行「测试证据」必须能被 `pytest --collect-only` 解析到（可在 `tasks.md` 6.1 加一条校验）。
10. **CI**：全量 pytest、OpenSpec strict validate、artifact checker、benchmark smoke。

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
