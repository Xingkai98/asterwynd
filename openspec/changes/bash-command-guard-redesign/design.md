# Design: Bash 命令护栏的单一解析管线与能力范围声明

## Context

### 现状

`agent/tools/command_guard.py`（577 行）在 `fix-issue-247` 之后由**三条并行通道**组成，每条都从原始命令文本或自己的分词结果出发做语义判定：

```
check(cmd):
  1. 全文 denylist 正则        → DEFAULT_DENYLIST(59) + _EXTRA_DENYLIST(18)
  2. _has_pipe_to_shell(cmd)   → 又一次 re.split 全文本
  3. _has_protected_redirect   → tokenize_command 后按 token 找 > / >>
  4. _check_argv               → _check_command_text(raw) 重新按 \r\n 切分 + 逐段 tokenize
                               → _strip_wrappers / _shell_dash_c_payloads / _check_rm ...
```

同一份「这条命令有几个段、每段 argv 是什么」被回答了三次，且三次在 `$(...)`、heredoc、brace 展开、进程替换上**互相矛盾**。`CommandGuard` 的调用方 `agent/tools/builtin/bash.py` 只用二态（`is CommandVerdict.DENY`）；审批层（`agent/approval.py` 的 `ApprovalHandler`，`agent/loop.py:842` 已接线）与护栏**目前完全没有连接**。

### 已实测的两个缺陷（本 change 的动因，非推测）

实验方法见下节「技术选型对比实验」，全部 151 条结果存于 `research/parser-comparison-rows.json`。

**误报（heredoc 正文被当成命令）**：

```
CommandGuard(workspace="/tmp/ws").check("cat <<'EOF'\ncp x .env\nEOF")  →  deny  (reason=mv_cp_dest)
```

分词器把 `<<` 拆成 `<` `<`，正文 `cp x .env` 因此成为一个「命令段」。读一份含该字样的文本也会被拦。

**漏报（真实目标参数被销毁）**：

| 命令 | 当前判定 | 目标被销毁的方式 |
|---|---|---|
| `cp x ~/.{ssh}/f` | allow | brace 展开 → 段切成 `~/.` `ssh` `/f`，dest 参数消失 |
| `cp x ~/.ss\h/id_rsa` | allow | 反斜杠转义（known-debt 乙类） |
| `nice cp x .env` | allow | launcher 前缀（known-debt 甲类） |
| `flock /tmp/l cp x .env` | allow | launcher 位置参数（known-debt 甲类） |

`cp x ~/.{ssh}/f` 是**当前实现独有的新漏报**：brace 展开把 dest 切成三段后，`_check_mv_cp` 看到的目标不再是敏感名，判定直接失效。

### 结论

两个缺陷都不是「denylist 少一条正则」，而是**解析层给不出正确的命令结构**。在这个地基上继续加正则，只会继续加重三套机制的等价性负担。

## Goals / Non-Goals

### Goals

1. **单一解析管线**：`source → parse/tokenize → command IR → policy evaluators → decision`。所有判定器消费同一 IR，全文 denylist 不再是独立入口。
2. **可证伪的能力范围声明**：按输入形态给出 `Guard guarantees` / `Backend guarantees` / `Unsupported·ask`，**每条 guarantee 对应一条可执行回归用例**，不出现「安全」「完全正确」这类不可证伪措辞。
3. **未知与失败策略显式化**：解析错误 / 动态词 / 不支持节点 / 预算耗尽 / 后端不可用各自有确定处置，**不允许静默放行**。
4. **改动面收敛**：新增一种 shell 语法形态只改一处（解析器 + IR），且有测试报警。
5. **已知残余逐项收口**：`docs/known-debt.md` 的甲类/乙类逐项「修」或「不修 + 理由」。

### Non-Goals

- 不证明任意 Bash 程序的最终效果（不做符号执行、不追踪文件系统状态）。
- 不把 denylist 当 OS boundary；护栏是建议层。
- 不手写 bash parser（kimi-code 的 16,600 行是这条路线成本的实证）。
- 不新增审批协议——复用既有 `agent/approval.py`。
- 不在本 change 内实现新的 sandbox 后端。

## Decisions

### D1：解析器选 `tree-sitter-bash`（数据支持，非预设）

**决策**：采用 `tree-sitter-bash`（PyPI wheel，`tree_sitter_bash.language()`）替换自维护 tokenizer 作为 IR 的生产者。

**理由**（数据见下节实验，全部为本机实测）：

| 维度 | 当前 tokenizer | tree-sitter-bash | bashlex |
|---|---|---|---|
| 解析覆盖（151 条语料） | 结构丢失/误切（见 Context 实测） | **0/151 报错** | 5/151 抛异常 |
| 错误模型 | 从不报错，**静默误切** | `has_error` + `ERROR`/`MISSING` 节点，**从不抛异常** | 抛 4 类异常（含空串的 `AttributeError`） |
| heredoc / `$()` / 进程替换 | 全部误切 | 全部正确 | 部分，且 `$(( ))`/`time`/`case` 抛 `NotImplementedError` |
| 延迟 | 0.019 ms | 0.050 ms | 0.948 ms |
| 自己要维护的代码 | 77 行 ad-hoc + 持续增长 | **~60–80 行**（加载 + Query + IR 构造，复用既有 `tree_sitter_symbols.py` 的 393 行同款写法） | 0（依赖） |
| 依赖成本 | 0 | **1 个 226 KiB wheel**（`tree-sitter` 已在 `pyproject.toml` 依赖中） | 67 KiB |
| 维护状态 / 许可 | 自维护 | 活跃（2026-09 push）/ MIT | **3.5 年未更新 / GPL-3.0** |

**关键论据**：`tree-sitter` **已经是本项目的依赖**（`pyproject.toml` 已钉 `tree-sitter>=0.25.2` + 6 个语法包），已有 393 行的加载/查询层（`agent/code_intelligence/tree_sitter_symbols.py`，含 6 语言的 `_load_*_language()`）。加 bash **不是引入一个新的架构承诺，而是补完一个已经做出的承诺**。

**延迟不构成选型理由**：三者（0.019 / 0.050 / 0.948 ms）都远低于一次 Bash 调用的实际耗时（毫秒到秒级），**用错误模型与自维护代码量做决定**。

**两条实测实现约束**（写进 tasks，避免踩坑）：
1. **枚举命令节点必须用 `QueryCursor`，不能用递归 Python 遍历**：实测约 1,000 个算术项（~1,300 字符）的 `$(( … ))` 会让递归遍历 `RecursionError`（默认上限 1000），而 `QueryCursor.captures()` 不递归、正常返回。这也是 opencode 的写法（`node.descendantsOfType("command")`）。
2. **只查 `has_error` 不够**：`rm -rf !(keep)` 不产生 `ERROR` 节点，只产生一个零宽的 `MISSING ;`。需要同时看 `has_error` 与 `is_missing`。

**明确不复制 opencode 的做法**：opencode 的 `parse()` 只检查 `if (!tree)`，**从不看 `rootNode.hasError`**，畸形输入会静默地少解析出若干命令。对「ask 型」审批工具可辩护，对「deny 型」护栏正是要修的 bug 类。

### D2：IR 的字段集由「所有 evaluator 需要什么」反推

**决策**：单一 IR（`ParsedCommand` / `CommandSegment`）至少携带以下字段，**任一 evaluator 不得绕过 IR 重新解析原文**：

| 字段 | 消费方 | 为什么必须在 IR 里 |
|---|---|---|
| `segments[]`（命令段） | 全部 | 替代 `tokenize_command` + `_split_command_segments` + `_check_command_text` 三次回答 |
| `argv[]`（每段的命令名与参数） | `_check_rm` / `_check_mv_cp` / `_check_chmod` / `_check_curl_wget` | 目标参数必须**准确**（brace/转义不得销毁它） |
| `redirects[]`（fd、操作符、目标） | 重定向 evaluator | 替代 `_has_protected_redirect` 的独立 token 扫描 |
| `env_assignments[]` | wrapper 处理 | `FOO=bar cmd` 的赋值前缀 |
| `dynamic_words`（bool，及位置） | 失败策略 | 动态词是「不可分析」的**信号**，不是错误 |
| `parse_errors`（bool + 位置） | 失败策略 | fail-closed 的触发条件 |
| `unsupported_nodes[]` | 失败策略 | zcode 口径：不认识 ⇒ 不允许 |
| `source_span`（起止偏移） | 报错信息 / trace | 让 deny 原因可定位到命令里的具体位置 |

**IR 的构造规则**（对齐 zcode `bash-command-parser.ts` 的实测字段集，276 行）：容器节点（`list` / `pipeline` / `redirected_statement`）透明展开；`command` 节点产出一个 segment；`variable_assignment` / `file_redirect` / `heredoc_redirect` 从 argv 中剔除但记入各自字段；**heredoc 正文不产生 segment**（这是修掉误报一的关键）。

### D3：决策模型从二态扩展为三态 `allow / deny / ask`

**决策**：`CommandVerdict` 增加 `ASK`。护栏可以主动要求人类确认，而不只有「放行」与「拒绝」。

**理由**：业界共识是三态——codex `Decision::{Allow, Prompt, Forbidden}`（`execpolicy/src/decision.rs:9-16`）、Gemini CLI `allow/deny/ask_user`、OpenHands `SecurityRisk` + `ConfirmationPolicy`、opencode 的审批提示。只有 allow/deny 的护栏**偏离业界模式**，且会把「不确定」错误地压成「放行」（当前的漏报根源）。

**接线**：`agent/tools/builtin/bash.py` 的 `ask` 分支路由到**既有**审批层（`agent/approval.py::ApprovalHandler.request_approval`，`agent/loop.py:842` 已有调用点与 `FailClosedApprovalHandler`）。**本 change 不新增审批协议**。无 UI / 非交互环境下 `FailClosedApprovalHandler` 的既有语义（拒绝）即为默认，天然 fail-closed。

**兼容性**：现有调用点写的是 `is CommandVerdict.DENY`，新增枚举值不破坏它们；但需逐点复核「应当 ask 的地方是否被 `is DENY` 漏掉」。

### D4：未知与失败策略 —— 一律 fail-closed，不允许静默放行

**决策**（对齐 codex 的保守 fallback、kimi-code 的 `unanalyzable`、zcode 的 `isBashCommandPermissionSafe`，**明确不复制 opencode 的静默少解析**）：

| 触发条件 | 处置 | 依据 |
|---|---|---|
| `parse_errors`（`has_error` 或 `is_missing`） | **ask** | kimi `unanalyzable → ask`；zcode `!hasParseErrors` 作为安全前提 |
| 动态词出现在**命令名或目标位置**（`$VAR` / glob / `$(...)` / `<(...)` / brace 展开） | **ask** | zcode：`CommandExpansion`/`ProcessSubstitution`/`BraceExpansion`/未知一律 `true`（dynamic）；Gemini CLI 对 `$`/反引号判为「无法静态验证 ⇒ escape」 |
| 动态词出现在**非目标位置**（如 `echo "$VAR"`） | **allow**（记入 IR，不做判定） | 避免把 `echo "$PATH"` 这类日常命令全部拉去审批 |
| `unsupported_nodes`（超出现有 evaluator 覆盖的语法） | **ask** | zcode 的 `unsupportedNodeTypes` 直接进不安全集合 |
| 嵌套 shell（`bash -c` / 命令替换）超过深度上界 | **ask**（停止解包，不无界递归） | codex 超界后不再逐段判定；当前实现的 `_MAX_NESTED_COMMAND_DEPTH=4` 保留 |
| 解析预算耗尽（节点数 / 输入长度 / 时间） | **ask** | kimi `ParseBudget`：50ms / 50k 节点，超界 `aborted` |
| 后端不可用 | **deny**（不是「护栏放行」） | 深寻 `SANDBOX_UNAVAILABLE` fail-closed |

**注**：`ask` 与 `deny` 的最终分配是本 change 需要用户拍板的**核心开放问题**（见 grill 的 Open Questions）——「不确定就 ask」的代价是交互噪音，「不确定就 deny」的代价是可用性。「动态词出现在目标位置」这一条尤其需要用户确认。

### D5：能力范围声明（本 change 的核心交付物）

按输入形态逐行给出三方职责。**措辞必须可证伪**：每条 guarantee 对应一条可执行回归用例；不保证的形态明确写「不分析」而不是「尽力」。

#### 责任表：哪一层承诺什么

| 层 | 承诺 | 明确不承诺 |
|---|---|---|
| **命令护栏**（`command_guard.py`） | 对**已正确解析**的命令结构，识别受保护路径写入、敏感点目录写入、递归强制删除越界、管道到 shell、任意代码执行解释器、文件外传；对无法分析的形态给出显式 `ask`/`deny` | 不模拟执行、不追踪 fs 状态、不防混淆到语法层面的对抗输入（如 base64 编码后的 payload）、不构成 OS boundary |
| **审批层**（`agent/approval.py`） | 把 `ask` 呈现给人类并按答复放行/拒绝；无 UI 时 `FailClosedApprovalHandler` 拒绝 | 不判断命令语义（它不解析命令）；不保证人类看清了命令（业界已知的 UI 截断攻击面） |
| **执行后端**（`ProcessBackend` / `DockerBackend` / OS sandbox） | **唯一做边界承诺的层**：文件写入范围、网络、进程观察、提权 | 不做命令语义判断 |
| **OS/内核** | Landlock/bwrap/seccomp 等强制点 | 共享内核 ⇒ 内核漏洞不隔离；已有 fd 不受后设限制 |

#### 输入形态矩阵

| 输入形态 | Guard | Backend | 测试证据 |
|---|---|---|---|
| simple argv（`git status`） | allow（未知命令默认放行） | 后端隔离 | `test_basic_command` |
| 命令链 `&& \|\| ; \| &` | 每段独立判定 | — | `test_chain_each_segment_checked` |
| 换行分隔 | 每行独立判定 | — | `test_newline_split` |
| 分组 `( )` `{ }` | 组内命令照样判定 | — | `test_grouping` |
| shell 关键字 `then/do/fi/...` | 剥离后判定真实命令 | — | `test_shell_keyword` |
| wrapper `env/command/nohup` | 剥离后判定真实命令 | — | `test_wrapper_stripped` |
| **launcher**（`nice`/`flock`/`setsid`/`chroot`/`stdbuf`/`taskset`/`timeout`） | **per-launcher 参数表**（D8）：位置参数与选项混排后判定真实命令 | — | `test_launcher_family`（新增） |
| `bash -c` / `sh -lc` | 解包 payload 递归判定，有深度上界 | — | `test_shell_dash_c_payload` |
| 命令替换 `$(...)` / 反引号 | 递归判定**且**标记为动态 | — | `test_command_substitution` |
| 进程替换 `<( )` `>( )` | 同样处理；目标位置视为动态 | — | `test_process_substitution`（新增） |
| heredoc `<<` / `<<-` | **正文不产生命令段**（修误报一） | — | `test_heredoc_body_is_data`（新增） |
| 重定向 `>` `>>` `2>` `&>` | IR 读取重定向目标判定；`/dev/null` 族豁免 | — | `test_redirect_*` |
| 变量/glob/brace 展开 | 目标位置 ⇒ 动态 ⇒ ask；非目标位置 ⇒ allow | 后端兜住实际写入 | `test_dynamic_word_policy`（新增） |
| 绝对路径 / 符号链接 | 按分量边界判定 + 规范化（**不靠解析器**） | Landlock/bwrap 强制 | `test_path_segment_boundary` |
| `rm` / `cp` / `mv` / `chmod` / `curl` / `wget` / `dd` | argv 语义检查 | — | 既有回归集 |
| 网络 | 不分析（只识别 `nc` / `/dev/tcp` 字面模式） | 网络命名空间 / seccomp | — |
| 子进程与资源耗尽 | 不分析（识别 fork bomb 字面模式） | cgroup v2（已有） | `test_cgroup` |

### D6：三方职责边界写进 spec，护栏只做「建议 + 路由」

**决策**：spec delta 明确——guard 产出决策（allow/deny/ask），审批层消费 `ask`，**后端是唯一边界**。护栏**不**因为「我判定 allow」而绕过沙箱；`allow` 只表示「护栏没有理由阻止」，不表示「安全」。

**依据**：codex 只在**每一段都命中显式 allow 规则**时才 `bypass_sandbox`（`exec_policy.rs:352-372`，heuristics 不算数）；深寻 `bash-sandbox/README.md` 的不变式「Deny-only at the seam — this executor never grants permission」。本 change **不实现 bypass-sandbox**，只把职责写清。

### D7：路径判定继续按分量边界 + 规范化，解析器不替代它

**决策**：解析器只解决「参数是哪个」，**不解决「这个参数指向哪里」**。`_normalize_path` / `_within` / `_is_device_exempt` 的既有语义（#247 建立）保留，作为消费 IR argv 的 evaluator 逻辑。

**依据**：CVE-2025-54794 与 Gemini CLI 的 `startsWith` bug 属同一类——**换任何解析器都防不住**，只能靠 path canonicalization + 分量边界。这条要写进能力范围声明，避免读者误以为「上了 AST 就安全了」。

### D8：已知残余逐项收口

**甲类（master 与 #247 后同为漏洞）** —— 判定：**本轮修**。

| 命令 | 处置 | 手段 |
|---|---|---|
| `nice cp x .env` / `flock /tmp/l cp x .env` / `chroot /tmp cp x .env` / `setsid` / `xargs` / `busybox` / `stdbuf` / `taskset` + 写命令 | 修 | **per-launcher 参数表**（issue #254 建议方向）：每个 launcher 声明「哪些选项吃值、哪些位置参数是自己吃的」，剥完后判定真实命令 |
| `nice tee ~/.ssh/authorized_keys` | 修 | 同上；`tee` 的目标需要新 evaluator（当前只覆盖 `rm/cp/mv/chmod/curl/wget`），或纳入通用「写目标」判定 |

**乙类（#247 引入的收缩：混淆形态）** —— 判定：**修**。

同族变体（反斜杠 / `?` / `*` / 字符类 / brace 展开 5 种 × 10 个敏感名）实测 50/50 漏。修法：**先把敏感名与目标归一到「可比较的规范形态」再判**——去反斜杠转义、展开字符类与 brace、用 `fnmatch` 做「敏感名能否被该 glob 匹配」的反向匹配。难点是不可误报（`.env.example` 这类字面名）。**D1 的 IR 使这条变简单**：目标参数不再被分词器切碎，归一化只需作用在一个完整字符串上。

### D9：测试矩阵按「语义等价输入族」组织

**决策**：每种语义**一份 fixture**，所有 evaluator 消费同一 IR；attack set 只增不减。

**依据**：kimi-code 的 differential test 会与官方 tree-sitter-bash 逐树比较、known differences 单独登记、fuzz 覆盖 token soup / 字节变异 / 深层嵌套 / 永不抛异常 / 预算 abort；zcode 的所有命令特例消费同一 invocation/argv。**新增语法的改动面收敛到一处**这条目标，只有靠「IR 契约测试」才能机械验证——即断言「同一语义的不同写法产出相同 IR」。

## Pre-Implementation Review

本 change 属 design 类（primary: refactor），进入实现前须由**独立零记忆 subagent** 执行设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Reviewer` run id、`## Confirmed Decisions` ≥3 条且每条带 `来源:`、`## Open Questions`）。

追问重点（本 design 的**已知争议点**，须逐条挑战）：

1. **D1 的选型是否真的成立**？`tree-sitter-bash` 引入 C 扩展依赖（wheel 226 KiB），与「纯 Python 项目」的定位是否冲突？降级路径（wheel 装不上时）是什么？
2. **D3 的三态是否有必要**？本项目的审批层今天是否真的能承载 `ask`（`FailClosedApprovalHandler` 无 UI 时拒绝，但 CLI 之外呢）？引入三态会不会让 `bash.py` 的调用点变复杂？
3. **D4 的 `ask`/`deny` 分配是否正确**？「动态词出现在目标位置 ⇒ ask」是否会让日常命令（`cp $SRC $DST`）频繁触发审批？
4. **D5 的能力范围声明是否真的可证伪**？每行是否都有对应测试？有没有偷偷使用不可证伪的措辞？
5. **D8 的乙类收口是否值得**？归一化 + `fnmatch` 反向匹配会不会引入新的误报（`.env.example`）？
6. **「单一解析管线」的度量标准是否可机械验证**？模块级常量数量下降如何测量？「新增一种 shell 形态只改一处」如何用测试锁定？

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| 引入 C 扩展依赖（tree-sitter-bash wheel） | 某些平台无预编译 wheel 时安装失败 | 已有 6 个 tree-sitter 语法依赖，平台支持面已确定；本轮实验在本机（linux x86_64）实测安装成功（226 KiB，cp310-abi3 manylinux） |
| 三态 `ask` 带来交互噪音 | `cp $SRC $DST` 这类命令被频繁拉去审批，用户疲劳 | D4 已按「目标位置 vs 非目标位置」分流；最终分配由用户确认（Open Question） |
| 解析器与 evaluator 语义漂移 | 新语法被解析但 evaluator 不认，静默放行 | D4 的 `unsupported_nodes ⇒ ask` + D9 的 IR 契约测试 |
| 重构期漏报（安全回归） | 重构后某条攻击集用例不再被拦 | attack set 只增不减 + 「拦截数不得下降」作为验收硬指标 |
| `ask` 路径在非交互环境的行为 | 无 UI 时 `FailClosedApprovalHandler` 拒绝，可能让原本 allow 的命令被拒 | 需实测确认；这是 Open Question |
| 能力范围声明写得太乐观 | 读者误以为护栏是边界 | D5/D6：显式写出「明确不承诺」列 + D7 点明解析器不解决路径规范化 |

## Testing Strategy

分层策略，**测试先行**：

1. **解析器/IR 契约层**（新增）：
   - 同一语义的不同写法产出**相同 IR**（`rm -rf /` vs `rm -fr /` vs `rm -r -f /`）。
   - heredoc 正文不产生 segment；`$(...)` 与 `<(...)` 被正确归类为「嵌套内容 + 动态」。
   - `has_error` / `is_missing` 两条错误信号都被捕获。
   - 预算与深度上界：超界返回确定处置而非崩溃（对齐 kimi 的 `{ok:false, reason:'aborted'}`）。
   - **枚举命令节点不得递归**（防 `RecursionError`）：构造 ~1,300 字符的 `$(( … ))` 断言不抛异常。
2. **evaluator 层**：既有 `tests/agent/tools/test_command_guard.py`（874 行）按「语义等价输入族」重组，断言所有 evaluator 消费同一 IR。
3. **策略层（fail-closed）**：解析错误 / 动态词 / 不支持节点 / 预算耗尽 / 后端不可用各自的处置，**含反例**（不得静默放行）。
4. **攻击集回归**：`benchmarks/attacks/attacks.json` **只增不减**，新增 launcher 族、混淆形态、brace 展开、CVE-inspired 用例；断言**拦截数不下降**。
5. **CVE-inspired 用例**：4 个 Claude Code CVE 各一到多条（其中只有 CVE-2025-54795 是解析能防的，另三条用于**锁住「我们不声称能防」**）。
6. **文档层**：能力范围声明的每一行 guarantee 必须有对应测试用例（机械可查：声明表格的「测试证据」列指向真实测试名）。
7. **CI**：全量 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、项目 artifact checker、benchmark smoke。

## 技术选型对比实验（方法与本机实测数据）

**目的**：把「AST vs 轻量 tokenizer」当作需要数据支持的选择，而非预先定案。

**语料**：151 条，四类来源混合——
- `benchmarks/attacks/attacks.json` 全部真实攻击用例（file-destroy / priv-esc / code-exec / exfil / resource / bypass / sensitive-read）；
- `tests/agent/tools/test_command_guard.py` 中真实出现的命令串；
- issue #254 点名的对抗类：launcher 族、混淆形态（反斜杠/glob/字符类/brace）、命令替换、进程替换、heredoc、分组与 shell 关键字、shell wrapper、动态词；
- 15 条「良性但结构复杂」的命令（`docker compose up -d`、`rg 'def check' --type py`、`find … | head` 等），用于观察误报面。

**方法**：对每条命令分别跑 (a) 当前 `tokenize_command` + `_check_command_text`、(b) `tree_sitter_bash` + `Query("(command) @c")` + `QueryCursor`、(c) `bashlex.parse`；记录恢复出的命令段数、argv、错误信号；用 `git status --short && ls -la /tmp | grep -v node_modules || rm -rf build 2>/dev/null` 作代表样本测延迟（300 次取均值）。

**结果**（原始数据 `research/parser-comparison-rows.json`）：

```
OVERALL tree-sitter has_error:  {False: 151} of 151
OVERALL bashlex raised:        5 of 151
   raise kinds: NotImplementedError ×3, ParsingError ×2
latency  tokenizer 0.0186 ms | tree-sitter 0.0495 ms | bashlex 0.9481 ms
```

**结构对比的代表性片段**（`|` 分隔 tree-sitter 恢复的命令，`;` 分隔当前分词器的「段」）：

| 命令 | 当前分词器 | tree-sitter-bash |
|---|---|---|
| `cat <<'EOF'\ncp x .env\nEOF` | `cat<<EOF ; cp x .env ; EOF` ← 正文成了命令 | `cat`（正文是数据） |
| `cp x ~/.{ssh}/f` | `cp x ~/. ; ssh ; /f` ← 目标销毁 | `cp x ~/.{ssh}/f` |
| `diff <(a) <(b)` | `diff < ; a ; < ; b` ← 4 个幻影段 | `diff <(a) <(b)` \| `a` \| `b` |
| `echo ${PATH}` | `echo $ ; PATH` | `echo ${PATH}` |
| `x=$(rm -rf /)` | `x=$ ; rm -rf /` | `rm -rf /` |
| `cmd 2>&1 \| tee /etc/passwd` | `cmd 2 > ; 1 ; tee /etc/passwd` | `cmd \| tee /etc/passwd` |

**结论**：当前分词器不只是「漏掉」`$()`/heredoc/进程替换，而是**静默地误切**——这比漏掉更糟，因为误切同时制造假阳性（heredoc）和假阴性（brace）。延迟不构成选型理由（三者都远低于一次 Bash 调用），**错误模型与自维护代码量才是**。`bashlex` 因「抛异常 + 3.5 年未更新 + GPL-3.0」被排除。
