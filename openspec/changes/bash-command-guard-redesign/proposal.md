# Proposal: Bash 命令护栏的能力范围审视与单一解析管线重构

关联跟踪 issue：[#254](https://github.com/Xingkai98/asterwynd/issues/254)，标题以 `【feature】` 开头。

## Change Type

- primary: refactor
- secondary:
  - workspace-safety
  - tool-system

## Why

`fix-issue-247`（PR #253，已合入）把命令护栏的路径段边界与命令分段解析修对了、没引入回归，代价是把 `agent/tools/command_guard.py` **从 300 行变成 577 行**，并形成了**三套各自独立做语义判定的机制**：

| 机制 | 位置 | 职责 |
|---|---|---|
| 全文 denylist 正则 | `check()` 第 1 步（`_EXTRA_DENYLIST` 18 条 + `DEFAULT_DENYLIST` 59 条） | 常规绕过变体、敏感点目录、`/dev/` |
| 重定向扫描 | `_has_protected_redirect` | `>` / `>>` 目标判定 |
| 段级 argv 判定 | `_check_argv` → `_check_rm` / `_check_mv_cp` / `_check_chmod` / `_check_curl_wget` / `_check_timeout` | 按命令段识别命令并做语义检查 |

**同一个语义判断存在两个实现**（全文正则 vs 段级函数），必须**手工保持等价**。`fix-issue-247` 的 9 轮审阅里因两者不一致翻车过三次：R7-1（`/dev/` 半边未补）、R8-1（spec 声称两通道都覆盖裸名但代码没有）、R6-1（launcher 子族判断错误）。新增一种 shell 语法形态要同时改 3–4 个常量，改漏一个**不会有任何测试报警**（R9-1 正是如此发生）。

根因不是「正则写得不够多」，而是**模块缺少一个统一的、可被所有判定器消费的中间表示（IR）**。当前实现的每个判定器都从**原始命令文本**或**自己的分词结果**出发，于是「命令是什么、有几个、每个的 argv 是什么」这个最基本的问题被回答了三次，而三次的答案在 `$(...)`、heredoc、brace 展开等形态上**互相矛盾**。

### 本 change 自立项前已实测的两个具体缺陷（不是推测）

用当前 `CommandGuard` 与 `tree-sitter-bash` 对同一组输入直接对比（实验脚本与全部 151 条结果见 `research/`，方法见 design.md「技术选型对比实验」）：

**缺陷一：分词器制造「幻影命令」，导致误报（false positive）。**

```
$ CommandGuard(workspace="/tmp/ws").check("cat <<'EOF'\ncp x .env\nEOF")
deny  mv_cp_dest
```

heredoc 的**正文是数据**、不是命令，但当前分词器把 `<<` 拆成两个 `<` token，正文 `cp x .env` 因此变成一个「命令段」并被判 deny。也就是说：**读取一份含 `cp x .env` 字样的文本文件也会被拦**。这是护栏自己制造的假阳性，与「`grep -rn "cp x .env" docs/` 应放行」的既有 spec 意图同源。

**缺陷二：分词器销毁真实参数，导致漏报（false negative）。**

```
$ ...check("cp x ~/.{ssh}/f")        → allow（brace 展开让目标被切成 `~/. ; ssh ; /f`，目标参数整个消失）
$ ...check("cp x ~/.ss\\h/id_rsa")   → allow（反斜杠转义）
$ ...check("nice cp x .env")         → allow（launcher 前缀，known-debt 甲类）
$ ...check("flock /tmp/l cp x .env") → allow（同上）
```

其中 brace 展开那条是**当前实现独有的新漏报**：dest 被切成三段后 `_check_mv_cp` 看到的目标不再是 `.env` 族，判定直接失效。

**共同点**：两个缺陷都不是「denylist 少一条正则」，而是**解析层给不出正确的命令结构**。在这个地基上继续加正则，只会让三套机制的等价性负担继续变重。

## What Changes

### 1. 引入单一解析管线，三套机制合并为一条

```
source → parse/tokenize → command IR → policy evaluators → decision
```

- **一次解析**产出结构化 IR（命令段、argv、重定向、env 赋值、动态词标记、解析错误标记、源码位置）。
- **所有判定器消费同一个 IR**：全文 denylist 降级为「对 IR 中的 argv/重定向目标做字面模式匹配」的**一层 evaluator**，不再是独立入口；重定向扫描与 argv 扫描合并为对 IR 的字段读取。
- 可度量目标：`command_guard.py` 的**模块级常量数量下降**（当前 15 个 `_CONST` + 77 条 denylist）；新增一种 shell 语法形态的改动面收敛到**一处**（解析器/IR），且有测试报警。

### 2. 给出可证伪的能力范围声明

用「按输入形态 × 决策」的矩阵取代「guardrail, not boundary」这类**不可证伪**的自述。每一行给出 `Guard guarantees` / `Backend guarantees` / `Unsupported·ask`，并写明**测试证据**。声明必须能被证伪：每条 guarantee 对应一条可执行的回归用例，未覆盖的形态明确写「不分析」。

### 3. 未知与失败策略显式化（fail-closed，不允许静默放行）

解析错误、动态词、不支持的节点、超出预算、后端不可用各自有明确处置，**由用户确认后**在 design.md 定稿。当前实现对这些形态的处置是「猜」（分词器永远返回结果、从不报错），这正是缺陷一/二的来源。

### 4. 已知残余逐项收口

`docs/known-debt.md`「命令护栏的残余覆盖缺口」一节记录的**甲类**（launcher + 纯命令 + 裸点名、launcher + 非 `cp`/`mv` 写命令）与**乙类**（混淆形态 50/50）逐项给出「修」或「不修 + 理由」。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `workspace-safety`：命令护栏从「全文正则 + 重定向扫描 + 段级 argv 三条并行通道，各自解析」演进为「单一解析管线 + 多 evaluator 消费同一 IR」；新增**能力范围声明**（按输入形态的 Guard/Backend/Unsupported 矩阵）、**未知与失败策略**（unanalyzable → 显式处置，不静默放行），并把三方职责边界（guard / 审批 / 执行后端）写成可验收条款。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 架构级改造（三套判定机制合并为单一解析管线）+ 引入新依赖（bash 语法解析器）+ 对标业界产品（codex / opencode / kimi-code / zcode / Gemini CLI / OpenHands）+ 走 grill 的非平凡 change，四条 `full` 判据全部命中。调研须回答「护栏的能力边界画在哪」，这直接决定重构后的形态。
- research questions:
  1. 主流 coding agent 把「命令安全」拆成哪几层？护栏、审批、执行后端、OS 沙箱各自承诺什么、明确不承诺什么？
  2. 命令解析应该产出什么中间表示，才能让「全文扫描 / 重定向扫描 / argv 检查」不再各自实现一份语义？
  3. 遇到解析失败、动态词（`$VAR`/glob/命令替换）、不支持的语法节点时，业界是放行、拒绝还是要求审批？默认值是什么？
  4. 护栏与真实边界如何分工？后端不可用 / 只实现部分强制（partial enforcement）时怎么办？stderr 文本能否作为安全事实？
  5. 「AST 解析器」与「轻量 tokenizer」在本项目（Python、每次 Bash 调用都跑）的真实成本差是多少？解析覆盖、误报漏报、代码量、延迟、错误恢复、新增语法的改动面各是多少？
  6. 业界因「命令校验可绕过」而真实发生过的漏洞有哪些类别？这些类别分别能被什么手段防住？
- findings: 6 个本地参考仓库实读（codex / deepseek-harness / kimi-code / zcode / opencode / pi，路径与本仓库的读法见 design.md）+ 6 组公开材料（Gemini CLI / Cline / OpenHands / SWE-agent / Aider / 产品观察）+ 隔离技术与失败史核验 + 151 条语料的解析器对比实验。要点：
  1. **业界共识是「护栏不是边界」，且这条共识被写进产品文档而不只是注释**。pi 明确「无内置文件/进程/网络限制，更强隔离交给 Docker/外部」；opencode 同样把隔离完全交给外部（Daytona 插件）。「agent 内只做 policy + 审批，边界交给外部执行环境」是**被明确选择的主流模式**，不是妥协。
  2. **护栏的决策模型是三态，不是布尔**。codex 的 `Decision::{Allow, Prompt, Forbidden}`（`execpolicy/src/decision.rs`）、Gemini CLI 的 `allow/deny/ask_user`、OpenHands 的 `SecurityRisk` + `ConfirmationPolicy`、opencode 的审批提示都是「询问人类」作为一等结果。一个只有 allow/deny 的护栏是**偏离业界模式的**。
  3. **沙箱绕过的条件被精确定义，且默认不放行**。codex 只有在**每一个解析出的命令段都命中显式 allow 规则**时才允许 `bypass_sandbox`（`core/src/exec_policy.rs:352-372`，且 heuristics 命中的「看起来安全」不算数）；深寻（deepseek-harness）**根本没有命令护栏**，把一切交给 per-call 的 file-effect policy，并把 `enforcement: 'full' | 'partial'` 作为**结构化事实**返回，`SANDBOX_UNAVAILABLE` 一律 fail-closed。
  4. **解析失败在业界是保守信号，不是放行理由**。codex 解析不出 `bash -lc` 时退化为「整条 argv 作为一个不透明命令」，从此**永远不满足逐段 allow**；kimi-code 对「解析失败 / ERROR 节点 / 动态字面量 / 超嵌套」一律返回 `unanalyzable` 并要求审批；zcode 的 `isBashCommandPermissionSafe = !hasParseErrors && !hasUnsupportedSyntax && !hasDynamicWords` 直接把「不认识」等同于「不允许」。**opencode 是这条上的反例**：它只检查 `if (!tree)`，从不看 `rootNode.hasError`，畸形输入会静默地少解析出几个命令——本 change 明确不复制这一做法。
  5. **AST 路线在小语料上是「零成本」，在手写路线上是「数千行」**。kimi-code 为「agent 侧命令权限分析」手写了一个 tree-sitter-bash 兼容解析器：**5,000 行源码 + 2,387 行测试 + 9,034 行 fixture ≈ 16,600 行**，且仍登记 **30 处与官方语法的已知偏差**、自带 50ms/50k 节点的 DoS 预算与三层递归深度上限，**并且仍把官方 tree-sitter-bash 作为差分测试的 oracle 一起发布**。对照组：zcode 用现成 `unbash` 只写 **276 行**消费代码；opencode 用 `web-tree-sitter` + wasm 把解析嵌进 **645 行**。
  6. **本项目的解析器选型有实测数据，且结论与直觉相反地便宜**。`tree-sitter` **已经是本项目的依赖**（`pyproject.toml` 已钉 `tree-sitter>=0.25.2` + 6 个语法包），`agent/code_intelligence/tree_sitter_symbols.py` 已有 393 行的加载/查询层。加 bash 只是**多一个 226 KiB 的 wheel**。151 条实测语料（含真实攻击集 50+ 条、真实 guard 回归用例、launcher/混淆/heredoc/命令替换/分组/动态词等对抗类）：**tree-sitter-bash 0/151 报错**，`bashlex` **5/151 抛异常**（`NotImplementedError`×3、`ParsingError`×2）；延迟 tokenizer 0.019ms / tree-sitter 0.050ms / bashlex 0.948ms，**三者都远低于一次 Bash 调用的实际耗时**，所以**延迟不构成选型理由，正确性与「自己要维护多少代码」才是**。`bashlex` 另有两项否决性事实：**3.5 年未更新**（0.18，2023-01）、**GPL-3.0**（本仓库 MIT，不适合引入核心路径），且对空串/纯空白输入会抛 `AttributeError`（其自身 walker 的空指针缺陷）。
  7. **路径包含判定必须按「分量边界」而不是字符串前缀，这是业界反复踩的同一类 bug**。CVE-2025-54794 就是 Claude Code 用 prefix matching 做路径限制导致越界——**与本仓库 #247 修的是同一个 bug**。Gemini CLI 同类 bug（`startsWith(docsRoot)` 让 `../docs-private/secret.md` 通过）修复用的是 `path.relative` 的 `isSubpath`。**一个正确的命令解析器不能替代路径规范化**：AST 只解决「参数是哪个」，不解决「这个参数指向哪里」。
  8. **CVE 语料说明「哪一类缺陷靠解析能修、哪一类不能」**。4 个 Claude Code 公告中，只有 CVE-2025-54795（`echo` 解析错误绕过审批）是 AST 能防的「文本模式 ≠ shell 语义」类；CVE-2025-54794 是路径规范化、CVE-2025-55284 是 allowlist 语义过宽（只读 ≠ 安全）、CVE-2025-59536 是决策时序（信任对话框之前就执行）——后三者**换任何解析器都防不住**，只能靠「路径规范化 / 收紧 allowlist / 修正决策顺序」。
  9. **「stderr 不能作为安全事实」这条业界只做到了半条**。深寻明确记录「runner 诊断是 in-band 的，stderr + exit code 无法证明是哪个进程写的，受限子进程可以模仿它的 runner 造成错误的归因；但这不能绕过 confinement，out-of-band 通道留作后续」；codex 的 `is_likely_sandbox_denied` 则是**在 stderr 与 stdout 上做 7 个关键词的子串匹配**。两者的共同底线是：**stderr 文本可以用来给一个已经失败的运行归因，绝不能用它来授予权限**。本 change 采纳这条底线。
- design impact: 见 design.md 的 D1–D9。调研对本 change 的关键影响为——**D1**（解析器选 tree-sitter-bash；数据在 research/）、**D2**（IR 字段集直接来自「所有 evaluator 需要什么」）、**D3**（决策模型引入三态 `allow/deny/ask`，对齐业界共识）、**D4**（unanalyzable 一律 fail-closed，不复制 opencode 的静默少解析）、**D5**（能力范围声明用可证伪措辞 + 每行带测试证据）、**D6**（三方责任表：guard 只做建议与路由，后端是唯一边界）、**D7**（路径判定按分量边界 + 规范化，解析器不替代它）、**D8**（已知残余的收口/不收口逐项决策）、**D9**（测试矩阵按「语义等价输入族」组织，所有 evaluator 消费同一 IR）。

## Impact Analysis

| 影响面 | 说明 |
|--------|------|
| `agent/tools/command_guard.py` | 主体重写：`tokenize_command` / `_split_command_segments` / `_check_command_text` / `_strip_wrappers` / `_shell_dash_c_payloads` 等 ad-hoc 解析函数由单一解析管线取代；`_EXTRA_DENYLIST` 与段级检查合并为消费 IR 的 evaluator；`CommandVerdict` 扩展为三态。 |
| `agent/tools/builtin/bash.py` | `check()` 的返回值由二态变三态：新增 `ask` 分支路由到既有审批层（`agent/approval.py` 的 `ApprovalHandler`，`agent/loop.py:842` 已接线）；`last_reason` 语义与 `sandbox` 事件载荷保持兼容。 |
| `agent/approval.py` / `agent/loop.py` | 仅在需要新增「命令护栏触发的审批」路径时改动；若沿用既有 `request_approval` 协议则改动面很小。**本 change 不新增审批协议**，只新增一个调用点。 |
| `pyproject.toml` | 新增 `tree-sitter-bash` 依赖（`tree-sitter` 已在依赖中）。 |
| `openspec/specs/workspace-safety/spec.md` | 命令护栏 Requirement 由「三通道、各自解析」改写为「单一解析管线 + 能力范围声明 + 未知策略」；既有 Scenario 的**断言不得放松**（攻击集拦截数不得下降）。 |
| `docs/known-debt.md` | 「命令护栏的残余覆盖缺口」节逐项标注收口结论（修 / 不修 + 理由）；受保护路径，需结构化解释事件。 |
| `benchmarks/attacks/attacks.json` | 攻击集**只增不减**：新增被本次重构补上的类别（launcher 族、混淆形态、brace 展开），并保持既有 50+ 条全部被拦截。 |
| 测试 | `tests/agent/tools/test_command_guard.py`（874 行）按「语义等价输入族」重组；新增解析器 IR 契约测试、CVE-inspired 用例、解析失败/动态词/预算耗尽的策略测试。 |
| 用户可见行为 | **行为变更**：`cat <<'EOF'…EOF` 这类「heredoc 正文含危险字样」从 deny 变为 allow（修掉当前误报）；`nice cp x .env` / `flock /tmp/l cp x .env` / `cp x ~/.{ssh}/f` 等从 allow 变为 deny 或 ask（补齐漏报）。两项均由用户确认后定稿（grill Open Questions）。 |
| 兼容性 | 不触及 AgentLoop 主循环协议、tool-call 消息链与 trace 事件 schema；`CommandVerdict` 新增枚举值对现有 `is DENY` 调用点向后兼容。 |

## 明确不做（Non-Goals）

- **不证明任意 Bash 程序的最终效果**：护栏分析命令结构，不模拟执行、不做符号执行、不追踪文件系统状态。
- **不把 denylist 当 OS boundary**：护栏是建议层，真实边界是执行后端（`ProcessBackend` / `DockerBackend` / OS sandbox）。
- **不为无限嵌套提供无限递归**：所有递归（子命令、命令替换、嵌套 shell）都有显式预算与深度上界，超界必须给出确定处置。
- **不在后端不可用时静默放行**：后端不可用是显式失败，不是「护栏放行」的理由。
- **不引入第二个 bash 解析器实现**：不手写 parser（kimi-code 的 16,600 行是这条路线的成本实证）。
