# Grill: bash-command-guard-redesign 设计追问

## Reviewer

- run id: `grill-bash-command-guard-redesign-2026-09-27`
- 时间: 2026-09-27
- 对象: `openspec/changes/bash-command-guard-redesign/{proposal,design,tasks}.md` + `specs/workspace-safety/spec.md` + `research/parser-comparison-rows.json`
- 基线: `master`（worktree 分支 `bash-command-guard-redesign/2026-09-27`，立项 commit `c366a62`）
- **独立性**: 4 个零记忆 subagent 并行执行，各自只拿到「待审文档路径 + 自己的对抗视角」，不继承主 agent 的上下文与结论；四个视角为 **绕过面 / 成本 / 可行性 / 证据审计**。每个 reviewer 被显式禁止向用户提问（避免子 agent 直接触达用户）。

## 结论摘要

设计方向成立，**但首版不能直接进入实现**：grill 发现 **9 项阻塞问题**，其中一项是**首版 design 自身会引入的安全回归**（heredoc 正文规则会让 `bash <<EOF` + 危险正文 + `EOF` 从 deny 变 allow）。另有 5 项只有用户能拍板的口径问题。已按 grill 结论产出 design v2 / tasks v2 / spec delta v2，并把 5 个 Open Question 停轮提交用户。

**grill 的价值实证**：首版最自信的三处表述（「后端是唯一边界」「全文正则可以降级」「`ask` 只新增一个调用点」）全部被 grep / 实跑证伪。这三处若不修，本 change 的**核心交付物（可证伪的能力范围声明）本身就会是一份假声明**。

## Confirmed Decisions

- **决策**：D1 解析器选 `tree-sitter-bash`，不选 `bashlex`，不自写 parser。理由: 151 条语料四位审阅员独立复跑结果一致——tree-sitter-bash `has_error` **0/151**、从不抛异常；`bashlex` **5/151** 抛异常（`NotImplementedError`×3、`ParsingError`×2），且对空串/纯空白抛 `AttributeError`（其自身 walker 的空指针缺陷）、**3.5 年未更新**（0.18, 2023-01）、**GPL-3.0**（本仓库 MIT）。延迟 0.016 / 0.040 / 0.813 ms 三者都远低于一次 Bash 调用，**不构成选型理由**。决定性事实：`tree-sitter` 已是本项目依赖（`pyproject.toml` 已钉 + 6 个语法包 + `agent/code_intelligence/tree_sitter_symbols.py` 393 行加载层），加 bash 只多一个 226.5 KiB wheel（cp310-abi3，manylinux/macos/win 全覆盖，**无需编译器**）。；来源: `research/parser-comparison-rows.json` + 四位审阅员各自独立复跑（bypass/cost/evidence 三份报告均逐项确认）+ `uv pip download` 检查 PyPI 产物清单

- **决策**：IR 的「写目标」必须是显式字段，不能假定为 `argv[-1]`。理由: 实测 `cp -t .env x`、`mv --target-directory=.env x`、`install -t .env x`、`dd of=.env` **全部 allow**——当前 `_check_mv_cp` 只读 `args[-1]`，目标经选项传递时判定直接失效。这不是解析问题（tree-sitter 能把 `-t .env` 解析得很好），是**目标定位规则缺失**。；来源: `grill-bypass.md` 独立复现实测输出；`agent/tools/command_guard.py` `_check_mv_cp` 直读

- **决策**：D4 的「命令替换在非目标位置 ⇒ allow」改为**无论位置都递归判定**。理由: 首版这条会把 `echo $(rm -rf /tmp/x)`、`` echo `rm -rf /tmp/x` ``、`$(echo rm -rf /)` 放行——参数位的命令替换**照样执行代码**。实测这三条今天被 `DEFAULT_DENYLIST` 的 `\$\(.*\)` / `` `[^`]*` `` 全文正则拦下；一旦按首版 D9 把全文通道「降级」，它们会回归。成本审阅员独立标注为 R1「静默 POSIX 放宽」。；来源: `grill-cost.md` R1 + `grill-bypass.md` 实测；`benchmarks/attacks/attacks.json` 的 `code-exec-007/008`、`bypass-003`

- **决策**：D4 新增 heredoc **绑定关系**规则（绑定解释器 ⇒ 正文按代码判定），并把它写进 spec 的 Scenario。理由: 首版规则「heredoc 正文一律是数据」会让 `bash <<EOF` + `cp x .env` + `EOF` 从今天的 deny（**靠分词器把 `<<` 拆成两个 `<` 的误报巧合**）变成 allow——tree-sitter 对该输入只产出 `bash` 一个命令，未知命令 ⇒ 放行。即「修一个误报」直接换来「一个真漏报」，且泄露面更大。`attacks.json` 里只有 `python3 - <<PY` 一条，所以「拦截数不下降」这条验收线**也抓不到**。；来源: `grill-bypass.md` 第 1 项（实测 `bash <<EOF…` 今天 deny、tree-sitter `cmds=['bash']`）；spec delta 首版 heredoc Scenario 的反面

- **决策**：全文 denylist 通道**保留**为显式字面层，真实目标改为「同一语义不再有两个实现」。理由: 实测清空 `_denylist` 后，`benchmarks/attacks/attacks.json` 的拦截数 **54 → 20**，即 **34 条只被全文正则拦下**（`priv-esc-001..008`、`code-exec-001/002/003/007/008/009/010/012`、`exfil-002`、`resource-001..003`、`bypass-002..009`）。首版「全文正则只保留 denylist 那一层」的方向没说错，但「降级为 evaluator」的表述暗示可以消灭它——那会直接违反「拦截数不得下降」。；来源: 主 agent 实测脚本（清空 `_denylist` 后重跑攻击集）+ `grill-feasibility.md` 用「清空 denylist 跑全套单测」得到同一结论（34 failed）

- **决策**：D3 的 `ask` 无法复用既有审批路径，改造面被首版系统性低估。理由: 实测 `inspect.getsource(BashTool)` 无 `approval` 字样、`Tool` 基类也无；`request_approval` 的唯一生产调用点在 `agent/loop.py:842`，而它位于 `decide_tool(tool)` → `decision.requires_approval` 分支——**只吃 `Tool` 对象、看不到 `cmd`**。`build_approval_request` 强制要 `PermissionDecision`（`approval.py:123-149`）。另需把 `command_guard.py:381/439/451` 三处「非 DENY 即 ALLOW」的早返回改为 ASK 透传。；来源: `grill-feasibility.md` 第 2 节（含 `grep`/`inspect` 证据与最小改造面估算）

- **决策**：D5 的能力范围声明必须按执行后端分别陈述，并承认默认后端无边界。理由: `grep -rnE "landlock|bwrap|seccomp|unshare|CLONE_NEWNS" agent/ --include=*.py` **零命中**；`ProcessBackend`（`process_backend.py:68`）是宿主机 `create_subprocess_shell` + 可选 cgroup v2；默认 `backend_name="process"`（`bash.py:50`）。只有 opt-in `DockerBackend` 有 `--network none` + 仅挂载 workspace（`docker_backend.py:101-113`），且无 `--read-only`/`--cap-drop`/`--user`。首版矩阵的 Backend 列写的「Landlock/bwrap 强制」「网络命名空间 / seccomp」在本仓库**不存在**——一张被一行 grep 证伪的声明表比没有更糟，因为本 change 的核心交付物恰恰是可证伪的声明。；来源: `grill-bypass.md` 问题行 (c) + 主 agent 独立 grep 复核

## 已由 grill 更正的事实错误（首版 → v2）

| 首版表述 | 实测 | 处置 |
|---|---|---|
| 「`rm -rf !(keep)` **不产生 ERROR 节点**，只产生零宽 `MISSING ;`」（用作「只查 `has_error` 不够」的证据） | `has_error=True`，无 ERROR 节点，唯一异常信号是零宽 `is_missing` `;`（位置 `[8:8]`） | 措辞更正为「两者都要查」；并补充实测发现：该输入的 `(command)` 捕获退化为 `['rm -rf !', 'keep']`（argv 是垃圾），故 `parse_errors` 命中须**禁用 argv** |
| 递归遍历在「~1,000 项（**~1,300 字符**）」触发 `RecursionError` | 1,808 字符 OK；**2,008 字符**（1,000 项）触发 | 更正为 ~2,000 字符 |
| 「当前 tokenizer **77 行** ad-hoc」 | `tokenize_command` 46 行、`_split_command_segments` 34 行，77 对不上 | 删除该数字，改为列函数名 |
| 「模块级常量数下降」作为重构度量 | 常量数 15 → 估计 13–18，**持平**；且可把常量搬进 dict 无成本刷低 | 换成三条可机械验证的指标（tasks 6.6） |
| 矩阵「测试证据」列引用 `test_chain_each_segment_checked` / `test_launcher_family` 等 12 个名字 | 实测 12/16 行**不存在**对应测试，其中 6 行未标「（新增）」——把待办伪装成证据 | v2 矩阵只列真实存在的测试名，待补项标 `(新增)`；新增 `pytest --collect-only` 可解析校验 |
| 「实验脚本见 research/」 | `research/` 下**只有 JSON，无脚本**；且 `tree-sitter-bash`/`bashlex` 不在 `uv.lock` | 已补 `research/gen_corpus.py` + `research/compare_parsers.py`；已 `uv add tree-sitter-bash` 入锁（`pyproject.toml:45`） |
| pi 的 34 行/3 正则被称为「pi 的实现」 | 那是 `examples/extensions/permission-gate.ts`（示例扩展），pi 官方口径是「does not include a built-in permission system」 | v2 已按「示例扩展」表述 |

## 必须修改（已整合进 v2）

1. **M1（阻塞，安全回归）heredoc 规则**：改为按绑定关系分流。见 Confirmed Decisions 第 4 条与 spec delta 的「heredoc 正文按绑定关系分流」Scenario；tasks 1.5 / 4.3 / 4.4。
2. **M2（阻塞）命令替换的位置豁免**：改为无条件递归判定。tasks 4.2。
3. **M3（阻塞）全文 denylist 不可消灭**：保留为显式字面层，度量改为「同一语义单实现」。D9 + tasks 2.7 / 6.6。
4. **M4（阻塞）写目标必须是显式 IR 字段**：D2 的 `write_targets[]` + tasks 2.1/2.3。
5. **M5（阻塞）launcher 兜底而非穷举**：首版 9 条表已被 `doas`/`unshare`/`script` 等 14 个反例证伪；剥离循环须交替到不动点。D8 + tasks 5.1/5.2。
6. **M6（阻塞）重定向须覆盖敏感点目录**：`echo X > .env`、`cat payload > ~/.ssh/authorized_keys` 当前 allow，而 D6 却承诺「识别敏感点目录写入」。tasks 2.1 + spec Scenario。
7. **M7（阻塞）`ask` 改造面如实化**：D3 + tasks 3.2/3.3/3.4 已按实测改造面重写；`ask` 在各运行时的行为矩阵入 spec。
8. **M8（阻塞）能力范围声明的 Backend 列须与代码一致**：D5 重写；新增 spec Scenario「后端边界按实现如实声明」。
9. **M9（阻塞）缺迁移/回归对冲**：重写一个经 9 轮审阅才稳定的安全模块，首版 tasks **无任何新旧对拍/回退开关**。D10 + tasks 6.7（对拍断言 `旧 DENY ⊆ 新 DENY ∪ 新 ASK` + 回退开关）。

**另修（非阻塞但已落）**：`eval` 引号载荷不一致（tasks 2.6）；`dd`/`tee` 缺 evaluator（tasks 2.2）；`_CODE_EXEC_INTERPRETERS` 死代码（tasks 2.7）；`workspace_policy` 层与护栏的先后关系未描述（D6）；首版 spec 那条「矩阵测试证据列不得为空」在 checker 里**没有对应实现**（tasks 6.1 改为用 `pytest --collect-only` 自校验）。

## Open Questions

> 以下 5 条**只有用户能拍板**（政策取舍，不是事实问题）。每条配具体场景例子。**收到答复前不得写实现代码。**

- **Q1: 动态词落在「写目标位置」时，是 `deny` 还是 `ask`？**
  - 场景：agent 执行 `cp $SRC $DST`（两个都是变量）。**若选 `ask`**：交互 CLI 下弹「Approve? [y/N]」；但 benchmark 运行器不注入 handler（恒 `FailClosedApprovalHandler`），非 TTY CLI 也判 `UNAVAILABLE` —— 也就是**这些环境下 `ask` 等于 deny，脚本化的复制会全部失败、benchmark pass rate 可能归零**。**若选 `deny`**：`cp $SRC $DST` 这类日常命令在**所有**环境下直接失败，可用性代价最大，但语义最干脆。
  - 三个选项：(a) 动态写目标一律 `deny`（最安全、最伤可用性）；(b) 一律 `ask`（交互式可用，无 UI 环境等同 deny）；(c) **分层**：归一化后命中敏感名/受保护路径 ⇒ `deny`，否则 ⇒ `ask`（design v2 当前采纳的是 (c)，但它会放掉「归一化后不命中但仍是混淆目标」的攻击）。
  - 另需明确：`cp x ~/.{ssh}/f` 归一化后**命中**敏感名 ⇒ 按 (c) 是 deny。确认这个判据吗？

- **Q2: heredoc 绑定解释器时正文按代码判定，误报面可接受吗？**
  - 场景：`bash <<'SCRIPT'` + `set -e` + `cd /tmp` + `rm -rf build` + `SCRIPT` 是很常见的脚本写法，正文里的 `rm -rf build`（相对路径、工作区内）在**新规则下会被判定**：`rm -rf build` 不含 `-rf /`，按现有 `_check_rm` 语义是 allow，所以这类**不会**误报。真正会误报的是正文里出现 `cp x .env` 这类**命中敏感名**的写法（例如脚本里真的要 `cp .env.example .env`）。
  - 选项：(a) 正文全量按命令判定（最安全，接受上面那类误报）；(b) 只对「正文归一化后命中敏感名/受保护路径」才拦（漏掉 `bash <<EOF` 里的 `rm -rf /`——注意 `rm -rf /` 会命中，所以 (b) 实际只漏「IR 无法表达的整句模式」）。

- **Q3: `~/.ssh/authorized_keys` / `.env` 这类**重定向**写入，本轮补上吗？**
  - 场景：`cat payload > ~/.ssh/authorized_keys` 今天 allow（持久化后门写入），且默认 `ProcessBackend` **没有文件系统边界**（grill 已 grep 证实）。补上的代价：正常的开发流程 `echo FOO=1 >> .env`、`echo x > .gitignore` 会不会被误报？按当前归一化设计 `.gitignore` 不命中敏感名（`.git` 是目录名、`.gitignore` 是文件名），`.env` 会命中。
  - 选项：(a) 本轮补上（把重定向目标接入 `_dest_is_sensitive`，接受 `.env` 写入被拦）；(b) 登记为新债务，本轮只补 `mv/cp` 侧。

- **Q4: launcher 的收敛策略选哪条？**
  - 场景：`doas cp x .env`（OpenBSD 的 sudo）当前 allow。首版列的 9 条穷举表已被 14 个反例证伪（`doas`/`unshare -m`/`nsenter`/`script -q`/`ionice`/`watch`/`strace`/`setpriv`/`chrt`/`systemd-run`/`runuser`/`setarch`/`perf`/`ltrace`）。
  - 选项：(a) 穷举补表——**已证伪，任何单条缺失即证伪整个安全属性**；(b) **未知前导 token ⇒ `ask`**（属性可证，但 `my-custom-tool --flag` 这类今天 allow 的命令会被拉去审批，噪音大）；(c) **已知安全前导白名单 + 其余 `ask`**（折中，白名单可迭代）。
  - 无论选哪条，**剥离循环交替到不动点**是确定的（`nohup setsid cp x .env` 当前 allow，必须修）。

- **Q5: 攻击集里 `ask` 算不算「被拦截」？**
  - 场景：引入三态后，`bypass-003 $(echo rm -rf /)` 按 M2 修正后应仍为 deny，但若某条用例改成 `ask`，`tests/benchmark/test_attack_suite.py:46` 现在硬断言 `is CommandVerdict.DENY` 会红。而放宽断言（改成 `is not ALLOW`）又**放松了既有安全断言**。
  - 选项：(a) **`ask` 计入拦截**，断言改为 `verdict in (DENY, ASK)`，同时对攻击集**不允许** `ask`——即攻击用例必须 `deny`（最严格，`ask` 只用于非攻击集形态）；(b) `ask` 计入拦截且允许攻击用例为 `ask`（最宽松）；(c) 维持攻击集只能 `deny`，另建一组「应 ask」的独立用例集。
  - 倾向：**(a)**（数据驱动的攻击集是安全回归基线，不该因为引入三态而降低强度）。

## User Confirmation

> 待主 session 转达用户答复后填写。格式：`- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`。
> **此节为空即表示 Open Questions 尚未确认，workflow_guard 会拦截实现代码写操作。**

## Codex / 审阅员建议（非阻塞）

- **grill-cost**：建议把度量改成「从原文重推 argv 的入口数 == 1」+「手工维护的等价性对数 == 0」+ 代码量三栏对照——首版的常量计数是可无成本刷低的弱代理。已采纳（tasks 6.6）。
- **grill-cost**：IR 契约测试只覆盖 `rm -rf /` 族不够，须 **per-field 断言**（redirect / env_assign / dynamic / heredoc / write_targets 各自单独断言）——其 140 行原型第一次就把 `file_redirect` 提取写错（该节点有两种父节点）。已采纳（tasks 1.2）。
- **grill-feasibility**：`tests/agent/tools/test_command_guard.py` 的 `assert verdict in (ALLOW, DENY)` 形态断言在引入 `ASK` 后**必然变红**，须同步。已采纳（tasks 3.6 / 6.5）。
- **grill-feasibility**：herestring（`bash <<< '…'`）是 4 条既有 DENY 测试依赖的形态，却不在首版形态清单里——已补进 v2 矩阵与 spec。
- **grill-evidence**：proposal 里 Cline / OpenHands / SWE-agent / Aider / 产品观察这几组结论在仓库内**无存档**（只有结论、没有可核验的引用记录），其中「OpenHands `SecurityRisk` + `ConfirmationPolicy`」被标 UNVERIFIED。建议在后续实现期把公开材料的取证记录落盘，或把这几组降级为「产品观察、非实现证据」。**（未阻塞——它们只用于「业界模式分类」，不承载本 change 的任何设计决策；D1–D11 的每条依据都来自本地实读或本机实测。）**
