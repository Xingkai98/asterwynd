# Design: 护栏写白名单（guard-write-allowlist）

## Context

`bash-command-guard-redesign`（issue #254）把「什么算敏感点文件名」从三处独立定义收敛成共享谓词 `is_sensitive_dot_name`（`agent/workspace_policy.py:45-109`，设计 D12），并给命令护栏建了单一解析管线。收敛之后暴露出来的第一个政策缺口就是 issue [#272](https://github.com/Xingkai98/asterwynd/issues/272)：**没有任何配置通道能授权 agent 写一个被 deny 的 `.env`**。用户当时拍板「白名单机制不塞进 #254、留作后续独立 change」，本 change 就是那个承接。

本 change 同时是归档 change `2026-10-13-witnessloop-adoption` 的**阶段 B 载体**（那个 change 的 `tasks.md` B.1–B.8 全部标了 `(post-merge)`，等一个真实小需求）。所以它的设计里有两条腿：**一是一条安全功能的实现设计**，**二是一次流程验证的观测设计**。两条都必须写在 design 里，且第二条的落点要明确（否则报告无处安放）。

### 实现要点复核（本分支在 `fd6d581` 上独立实测，不照抄 issue 行号）

用 `WorkspacePolicy` + `CommandGuard` 直跑探针得到下表（workspace 为临时目录）：

| 动作 | `WorkspacePolicy`（文件工具层） | `CommandGuard`（Bash 层） |
|---|---|---|
| `Write .env` | DENY（`is_denied` 的段级敏感名判定） | — |
| `Read .env` | DENY | — |
| `cp .env.example .env` | ALLOW | DENY（`last_reason=mv_cp_dest`） |
| `echo API_KEY=x >> .env` | ALLOW | DENY（`protected_redirect`） |
| `tee .env` / `dd of=.env` | ALLOW | DENY（`tee_target` / `dd_target`） |
| `cat .env` / `grep API_KEY .env` | ALLOW | ALLOW |
| `.env.example` 读写 | ALLOW | ALLOW |
| `.env.local` / `.env.production` | DENY | DENY |

六条结论。第 1–4 条在立项稿就有（其中第 1 条的证据在整合独立 grill 时被订正为「四处」）；**第 5、6 条是整合独立 grill 时新增的**（`f09fa77` 的复核节原为 4 条），计五条与 issue 的说法有出入或 issue 未覆盖。

1. **生产构造点：三处「入口可配置」+ 一处「dry-run 沙箱」= 四处**。可配置的三处是 `agent/main.py:251-254`、`web/session.py:1728-1731`、`benchmarks/agent_runner.py:349-352`；第四处是 `agent/tools/builtin/subagents.py:2005`——在 `dry_run_workflow`（同文件 `:1979`）里 `SubAgentManager(workspace_policy=WorkspacePolicy(workspace_root=sandbox))`，**不是** `policy or WorkspacePolicy()` 兜底，而是一个真实构造点（临时 dry-run 沙箱，无配置可传 ⇒ 不需要接线，但**不能**把它算作「兜底」而漏出清单）。`agent/tools/factory.py:316,422`、`agent/tools/builtin/*.py` 里那些 `policy or WorkspacePolicy()` 才是兜底。**与 issue 的差异**：issue 写的 `web/session.py:1566` 在当前树上已漂移到 `:1728`。⇒ 引用行号必须每次现测，清单口径必须能被复核。
2. **`WorkspacePolicy.__init__` 确实已接受 `denied_patterns`**（`agent/workspace_policy.py:239`）——issue 这条对。**但「把 allowlist 接上 `denied_patterns`」是错的**：`denied_patterns` 只喂 `is_denied` 里那一路 **glob 判定**（`:331-337`），而 `.env` 命中的是**段级敏感名判定**（`:326-330` 的 `is_sensitive_dot_name`）。实测：`WorkspacePolicy(root, denied_patterns=())` 下 `.env` 仍 `is_denied=True`。⇒ allow 必须是**独立于 `denied_patterns` 的一个新判定面**，不能靠覆写 glob 表实现。
3. **issue 说「护栏用另一张表，必须同源喂给两层」——对，且比 issue 描述的更封闭**：`CommandGuard` 在**生产路径上只有一个构造点** `agent/tools/builtin/bash.py:87`（`self._guard = CommandGuard(workspace=self.policy.workspace_root)`），它**只拿得到 `workspace_root`**，拿不到 policy 本身、更拿不到任何配置。⇒ 「同源」需要**新增传参面**（`BashTool` → `CommandGuard`），不是「配置里补一个字段」就自动同源。
4. **issue 未覆盖的一条：读侧的不对称。** 文件工具层的读被拒（`Read`/`Grep`/`ListFiles` 走 `assert_read_allowed`，`agent/workspace_policy.py:350-354`），但 **Bash 层的读今天本来就是通的**——`cat .env` / `grep API_KEY .env` / `source .env` 两层全 ALLOW（实测）。只有 `mv`/`cp` 的**源位置**被查（`_check_target` 的 `mv`/`cp` 分支，`agent/tools/command_guard.py:872-878`），`python -c 'open(".env").read()'` 被 `DEFAULT_DENYLIST` 的 `python3?\s+-c\b` 拦下（那是另一条理由）。⇒ 任何「只放行写 ⟹ 凭据读不到」的说法都必须限定在**文件工具层**，否则是失真陈述。
5. **issue 未覆盖的第二条：两层今天就不同向，且 Bash 层更宽。** 本分支实测 13 条被拒路径，**8 条**（`deploy.pem` / `srv.key` / `id_rsa` / `node_modules/x.js` / `benchmarks/runs/r.json` / `.venv/y.py` / `__pycache__/z.pyc` / `.ruff_cache/x`）在文件工具层是 DENY、Bash 层 `cp x <path>` 是 ALLOW（`last_reason=None`）：`CommandGuard` 只按**段级敏感点名**（`_dest_is_sensitive`）+ 固定 `_DENY_PATHS` 判目标，根本不读 `DEFAULT_DENIED_PATTERNS` 那张 glob 表。⇒ 「两层结论恒同向」是**变更前就不成立**的断言，任何要求它的规格/测试一写即红（见 blocker 3 的处置）。
6. **issue 未覆盖的第三条：嵌套 `.env` 的 Bash 写被 denylist 整句正则前置拦下。** `_EXTRA_DENYLIST` 里那条 `r"\b(mv|cp)\s+\S+\s+\S*/\.(?:git|ssh|env|aws|gnupg|kube|docker|netrc|npmrc|pypirc)(?![\w.-])"`（`agent/tools/command_guard.py:609`）由 `check()` 的**第 1 步**在任何 IR 判定之前对整句执行（扫描循环 `:737-740`，`last_reason="denylist"`）。实测：`cp x config/.env`、`mv x config/.env`、`cp x ./config/.env`、`cp x 'config/.env'`、`cp x /tmp/../config/.env` **全 DENY 且 reason 为 `denylist`** ⇒ 与 allow 挂钩点（`_check_target` / `_has_protected_redirect`）**结构上不相交**。裸 `.env` 不受影响（走 `mv_cp_dest`，可挂钩）。这条直接决定本 change 能兑现什么（见 Decision 9）。

## Goals / Non-Goals

**Goals:**

- 新增 `tools.allowed_write_paths` 配置，语义是「deny 默认 + **精确**可写覆盖」；默认空列表 ⇒ 不配置时行为零变化。
- allow 的**判定同源**喂到 `WorkspacePolicy`（文件工具层）与 `CommandGuard`（Bash 层）两个判定器——同源指**共享谓词函数**，且**只在写路径求值**，读路径与 tree-sitter 索引面不受影响。
- 把四条硬约束写进规格：不越 workspace 边界、不接受「匹配一切」的模式、不放宽结构性目录 deny 与命令 denylist、**不使任一层比引入本能力前更宽**。
- 用**否定用例**（未列入的 `.env` 仍拒）钉死「allow 没被实现成后门」。
- **诚实划定兑现面**：不承诺「配了就两层通吃」——嵌套路径的 Bash `cp`/`mv` 明确不在范围内（Decision 9），并把这条写进规格与用户可见的示例。
- 把 12 条政策取舍（每条带具体例子）停轮抛给用户，收到答复前不写实现代码。
- 作为 `witnessloop-adoption` 的阶段 B 载体，产出：asterwynd 形态审阅证据 + witnessloop 形态 manifest + 分叉清单 + 按成因分类的红清单 + 「值不值得真打开」的判断依据。

**Non-Goals:**

- 不允许模型自己配白名单（#254 已拍板否决）；不引入「模型提议 → 落规则」的通道。
- 不放宽 `DEFAULT_DENYLIST` / `_EXTRA_DENYLIST` / `_match_allowlist` 的任何语义。
- 不为 allow 支持 glob、目录前缀或 `~` 展开（**U2 已裁定**；若日后需要目录级，那是本 change 之外的扩展）。
- 不改 `assert_within_workspace` 的边界（allow 只在 workspace 内生效）。
- **不为嵌套路径的 Bash `cp`/`mv` 动 `_EXTRA_DENYLIST` 的扫描顺序**（**U7 已裁定**不动；理由见 Decision 9）——若日后要扩，那是范围变更，需重开设计。
- **不修两层「绝对同向」的既存差异**（R10：8/13 条被拒路径今天两层就不同向，Bash 更宽）——本 change 只保证「不使任一层更宽」与「allow 命中处变化同向」。
- 不合并 Bash 读侧缺口（`cat .env` 通着）——见 **U6**（已裁定记为债务另立）。
- 不修 witnessloop 侧的已知不兼容（`:来源` 谓词，上游 issue #20），不为变绿放宽任何判据。
- 不改 `.github/workflows/ci.yml`、不动 branch protection、不改 `AGENTS.md` 的流程段。

## Decisions

### Decision 1: allow 是**独立判定面**，不靠覆写 `denied_patterns` 实现

**选择**：`WorkspacePolicy` 新增独立的 `allowed_write_paths` 参数与谓词（函数名与调用点见 Decision 2），**不改** `denied_patterns` 的语义与默认值。

**理由**：见「实现要点复核」第 2 条——`.env` 命中的是 `is_denied` 里的**段级敏感名判定**，`denied_patterns` 那条路根本管不到它。若把 allow 实现成「从 `denied_patterns` 里删掉命中项」，对 `.env` 完全无效。

**否决的备选**：把 allow 实现成「`denied_patterns` 的减法」——对 `.env` 无效（实测），且会把「用户配的 allow」与「内置 deny 表」耦合成一个可被写坏的单一列表。

### Decision 2: 两层同源 = 共享**谓词函数**，不共享**调用点**；allow 只在写路径求值

**选择**：
- `allowed_write_paths` 的**唯一数据源**是 `WorkspacePolicy` 的实例属性（**快照于构造期**，运行中改它不会影响已构造的 `CommandGuard`——见 R13）。
- `CommandGuard.__init__` 新增参数接收**同一个元组**（不是重新解析一份配置）。
- `BashTool.__init__`（`agent/tools/builtin/bash.py:87`）构造 `CommandGuard` 时把 `self.policy.allowed_write_paths` 传进去。
- 判定逻辑抽成**一个共享的纯函数**（如 `workspace_policy.write_allowlist_covers(resolved_rel_path, allowlist)`）。**共享的是这个函数，不是它的调用点**：该函数只在**写路径**被调用——`WorkspacePolicy.assert_write_allowed`（`agent/workspace_policy.py:356-360`）与 `CommandGuard` 的**写目标判定面**。

**「写目标判定面」的唯一定义（本 change 全文与规格同此口径，禁止再用「三面」之类的缩写）**：`CommandGuard` 中**消费写目标路径**的六个判定方法——`_check_target`（`:930-938`，**仅其在写目标位置上的调用**）、`_has_protected_redirect`（`:976-993`）、`_check_dynamic_target`（`:940-960`）、`_check_mv_cp`（`:1106-1122`）、`_check_tee`（`:1156-1167`）、`_check_dd`（`:1139-1154`）。**明确排除三项**：① `check()` 第 1 步的**整句 denylist 正则扫描**（`:737-741`，pre-IR，见 Decision 9 与「Bash 层豁免覆盖面差异」）；② `mv`/`cp` 的**源位置**判定（`_check_ir_segment` `:875` 与 `_check_argv_segment` `:1060` 都用 `_check_target` 判 `source`——那是**读侧**，与 U8 / U5 的「只放行写」冲突，allow SHALL NOT 影响它）；③ `_check_rm`（`:1077-1103`）——它只判 `-r`+`-f` 的**逃逸**面，与 allow 无关。`tasks.md` 3.2 的收敛清单与本节同口径。
- **`WorkspacePolicy.is_denied`（`:316-338`）保持原语义，SHALL NOT 感知 allowlist。**

**这条是本 change 最容易写错、且写错后果最重的地方**：`is_denied` 是 `assert_read_allowed`（`:350-354`）与 `assert_write_allowed`（`:356-360`）的**同一个实现**（两处都在 `:352` / `:358` 直接调它），`agent/code_intelligence/repo_map.py:173` 还**直接**调它做 tree-sitter 跳过判定。⇒ 把 allow 写进 `is_denied` 会**同时**打开三处：① `Read` / `Grep` / `ListFiles` / `Find` / `ReadDoc` / `InspectGitDiff` / LSP 的读（全部走 `assert_read_allowed`）；② **RepoMap / SymbolSearch 会把被豁免的 `.env` 收进符号索引**（`repo_map.py:173` → `_should_ignore`）；③ `assert_write_allowed` 本身。其中 ② 尤其隐蔽——它不报错，只是默默把凭据文件的内容送进索引与上下文。Grill 的首轮审阅正是靠这条把本设计的原稿判为自相矛盾（原稿 Decision 2 要求 `is_denied` 调共享谓词，而 Decision 5 与规格又要求读不放行）。

**理由**：`#254` 的 D12 教训是「同一语义有两个实现 ⇒ 必然漂移」（`.env.local` 曾被文件工具拒、被 Bash 护栏放行）。allow 若两层各写一遍匹配，会重演同一个 bug 的反向版本——而哪边生效取决于用户用哪个工具。**但「同源」不等于「同一个调用点」**：把 allow 塞进读路径会引入一个本 change 从未承诺的读侧扩权（违反 Decision 5 与规格）。

**落点被数据钉死**：`CommandGuard` 生产路径上只有 `agent/tools/builtin/bash.py:87` 一个构造点（实测），传参面就是 `BashTool.__init__` 一行 + `CommandGuard.__init__` 一个参数；`agent/tools/factory.py:335,457` 的两处 `BashTool(policy=policy, ...)` 不需要改（它们已经传了 policy）。

**明确不受 allow 影响的面（逐条列出，供评审对照）**：`is_denied` 本身、`assert_read_allowed`、`repo_map.py:81,96,173`、`agent/tools/builtin/{read,grep,list_files,find,read_doc,inspect_git_diff,lsp}.py` 的读路径，以及 **Bash 层的读侧**——`mv`/`cp` 的**源位置**判定（`_check_ir_segment` `:875`、`_check_argv_segment` `:1060` 都借 `_check_target` 判 `source`）与 `WorkspacePolicy._env_source_is_credential`（`agent/workspace_policy.py:119-127`，Bash 命令层的 `cp .env /tmp/x` 就靠它拒）。**这条是「只放行写」在 Bash 层的第二条腿**：若把 allow 挂进 `_check_target` 而不区分源/目标位置，被豁免的 `.env` 会立刻变成可外泄的读源。

**否决的备选**：(a) allow 写进 `is_denied`——读写一起开 + tree-sitter 索引面泄漏（见上），且直接违反规格的「豁免不影响读判定」Requirement；(b) 新增 `is_write_denied` 而在其中复用 `is_denied` 的结果——等价于 (a)，因为判定结果仍然共享；(c) 两层各写一份匹配——D12 的漂移重演。

### Decision 3: 粒度 = **精确 workspace 相对路径**；glob 元字符在解析期 fail fast

**选择**：`allowed_write_paths` 的每一项是 workspace 相对路径的**字面值**（如 `.env` / `config/.env`）。含 glob 元字符（`*` `?` `[` `]`）、`..` 段、或以 `/` 结尾（目录形式）的条目 SHALL 在配置解析期被判非法（`ConfigError`，fail fast）。绝对路径同样判非法。

**理由**：
- **业界同名解法**：codex 明确「glob 只能用于 deny，不能用于授权」（`codex/codex-rs/sandboxing/src/policy_transforms.rs:30-35`），授权走精确路径 + 符号链接保留式规范化（同文件 `:39-41`）。
- **直接消灭 issue 的 `**/*` 硬约束**：一个「匹配一切」的模式会把 `.git/config` 一起打开（issue 实测）。把 glob 从授权面整体移走，比给 `**/*` 加黑名单特判更彻底——后者还要处理 `./**/*`、`.//**/*`、`x/../**/*` 等等价拼写。fail fast 让这类拼写**根本进不了运行时**。
- **防御性收益**：`is_denied` 的现有实现对每个候选做 `fnmatch`（`agent/workspace_policy.py:331-337`），allow 若也走 glob，就等于在这条已经出过越界 bug（本仓 #247、CVE-2025-54794 的同类）的路径上再加一层 `fnmatch` 语义。

**代价（如实写）**：用户想给一个目录下 10 个 env 文件授权时，必须写 10 条。这是**接受**的代价——本 change 的存在理由是「精确豁免」，不是「目录级授信」。若日后确实需要，`dir/**` 语法可以作为独立扩展（届时它需要单独解决「`**` 的段边界」问题，正是 #247 那一类）。

**否决的备选**：(a) 允许任意 glob + 只特判 `**/*`——等价拼写漏不完，且 `fnmatch` 的段边界语义与 `is_denied` 的段级判定不一致；(b) 目录前缀（`config/` 授 `config/` 下一切）——`config/` 会把 `config/.env.production` 一起打开，与 U3 的裁定（变体不跟随）自相矛盾。

### Decision 4: 配置住 `asterwynd.yaml` 的 `tools.allowed_write_paths`，与 `tools.command_denylist` 同构

**选择**：`ToolsConfig` 新增 `allowed_write_paths: tuple[str, ...] = ()`（`agent/config.py:151-161` 旁），`_parse_tools_config` 走既有 `_parse_string_list` 并在其后加语义校验（glob/绝对路径/`..`/尾 `/` ⇒ `ConfigError`）（`:875-897`）；`asterwynd.example.yaml` 在 `command_denylist: []`（`:35`）旁补一行示例。三个生产构造点把 `config.tools.allowed_write_paths` 传给 `WorkspacePolicy`。

**理由**：业界静态白名单住在配置文件里是主流（opencode 的 `permissions` 有序数组 `opencode/packages/core/src/config.ts:60-62`；codex 的额外权限来自运行参数/用户配置构成的 `AdditionalPermissionProfile`，`codex/codex-rs/sandboxing/src/policy_transforms.rs:18-77`）。本仓**已经有**这条通道（`tools.command_denylist` / `tools.ignore_patterns`），复用它 = 零新增机制、零新增发现逻辑、零新增环境变量面。是否额外支持用户级 scope 见 U4（已裁定：不做）。

### Decision 5: 只放行**写**，读保持拒绝（文件工具层）；并如实写明 Bash 读侧本来就是通的

**选择**：allow 只接进 `assert_write_allowed`（`agent/workspace_policy.py:356-360`）与 Bash 层的**写目标**判定；`assert_read_allowed`（`:350-354`）、`is_denied`（`:316-338`）与 `agent/code_intelligence/repo_map.py:173` 的索引跳过判定 SHALL NOT 被 allow 影响（与 Decision 2 是同一条约束的两个视角）。

**理由**：
- 用户要的是「让 agent 能**配置** env」，不是「让 agent 能**看** env」。读放行会把明文凭据带进上下文、trace 与 `messages.jsonl`。
- 与业界 read/write 不对称的做法一致：codex 的 glob 权限**只能用于 deny-read**（`policy_transforms.rs:30-35`），即读侧才是允许用宽模式去**收紧**的那一侧。

**必须写明的边界（不得失真）**：
- `Edit` 工具**不依赖** `assert_read_allowed`——它在 `assert_write_allowed` 之后自己 `read_text()`（`agent/tools/builtin/edit.py:55,67`）。所以 `Edit .env` 在「只放行写」下**可用**。
- `Write` 工具**拒绝覆盖已存在的文件**（`agent/tools/builtin/write.py:52-56` 的「file already exists… Use Edit」）⇒ 受 allow 覆盖的路径的典型用法是「`Write` 建、`Edit` 改」。
- **agent 读不回自己写的内容**（`Read .env` 仍拒）⇒ `Edit` 的 `old_string` 只能靠 agent 自己记住写过的内容，或整文件 `Write`（但那会被「已存在」挡）。这是「只放行写」的**真实可用性代价**，见 U5 的可用性边界。
- **Bash 层读侧不通**（`cat .env` 全放行，实测）**不由本 change 负责**，见 U6；任何「凭据读不到」的结论都不得写成无限定语。

### Decision 9: 诚实划定 allow 的**兑现面**——嵌套路径的 Bash `cp`/`mv` 不在范围内

**选择**：本 change 明确**不**承诺「配了 `allowed_write_paths` 就等于该路径的两层都可写」，而是把兑现面写死如下（并同步到规格与 proposal 的示例）：

| 路径形态 | 文件工具（`Write`/`Edit`） | Bash `echo >>` / `tee` / `dd of=` / `install` | Bash `cp` / `mv` |
|---|---|---|---|
| **裸名**（`.env`） | ✅ 可兑现 | ✅ 可兑现 | ✅ 可兑现（走 `_check_target` → `mv_cp_dest`，可挂钩） |
| **嵌套**（`config/.env`） | ✅ 可兑现 | ✅ 可兑现（`protected_redirect` / `tee_target` / `dd_target` / `install_target`，均可挂钩） | ❌ **不可兑现**（被 `_EXTRA_DENYLIST` 整句正则在 IR 之前拦下，`last_reason=denylist`，`agent/tools/command_guard.py:609` / 扫描循环 `:737-740`） |

**理由**：`check()` 的**第 1 步**是「对整句跑 denylist 正则」并**立即返回 `DENY`**（`:737-741`），它排在所有 IR 判定之前。那条正则要求「第二个参数里含 `/<敏感点名>`」，所以**只**拦嵌套形态：`cp x .env` 不匹配它（走 `mv_cp_dest`），`cp x config/.env` 匹配它。实测五个拼写变体（`./config/.env`、`'config/.env'`、`/tmp/../config/.env`）**全部**命中同一条 regex。

**为什么不让正则扫描给 allow 让路**：把 allow 判定提到第 1 步之前，等于让一条**整句正则**的命中可以被配置覆盖——而那条正则正是 `#254` 重建的单一解析管线的**第一道**、也是承载最多攻击用例的通道（`#254` 的 RIR findings 5 实测：清空 denylist 后攻击集拦截数 54 → 20）。为一个嵌套路径的 `cp` 便利去动它，收益与风险不对称，且违反 proposal 的 Non-Goal。

**代价（如实写）**：proposal 原先举的 `['.env', 'config/.env']` 里，`config/.env` 的 Bash **`cp`/`mv`** 写不生效——而 `Write` / `Edit` / `echo >>` / `tee` / `dd of=` / `install` 都生效。⇒ 示例必须改成实际可兑现的形态，且用户配嵌套路径时**必须知道**这条边界（否则会得到「文件工具能写、`cp` 报 denied、且报错文案是笼统的 `Command denied by sandbox command guard`」的困惑）。

**这条是否要扩范围，U7 已裁定为「不扩」**；被否决的备选是「把嵌套路径的 `cp`/`mv` 也纳入 allow」（需要改 denylist 扫描顺序，与 Non-Goal 冲突，属范围扩张）。

### Decision 6: 阶段 B 的观测报告落在**本 change 根目录**，不放 `reviews/`

**选择**：阶段 B 的观测报告落 `openspec/changes/guard-write-allowlist/stage-b-observation.md`——即 change 目录**根部**，**不在 `reviews/` 下**。

**理由（三条，按硬到软）**：
1. **witnessloop 的孤儿规则**：一旦 `reviews/` 下存在**任意一份** witnessloop 形态 manifest，`reviews/**/*.md` 里**每一份**未被某份 manifest 的 `report_path` 绑定的报告都判「孤儿报告」（witnessloop `src/witnessloop/contract.py:185-206`）。阶段 B **必须**建 witnessloop 形态 manifest（B.2 的硬要求）⇒ 孤儿规则**一定会被激活**。
2. **观测报告没有合法的 stage 可绑**：witnessloop 的 stage 词表是固定的三个（`grill` / `grill-adversarial` / `building`，`src/witnessloop/constants.py:65-76`，policy 可覆写名字但不是新增语义）。一份「流程观测报告」不属于任何 stage。硬塞成第二份 `stage=building` 的 manifest 会踩另一个坑：`stage_manifest_findings_in_change` 按路径字典序取 `matching[0]`，同 stage 多份时**只有第一份被当证据、其余静默忽略**（`witnessloop-adoption` 的 Decision 2 实测过这个错绑形态）。
3. **报告仍必须随 change 进 PR、随归档留痕**：放 change 根目录 ⇒ 在 diff 里、在归档目录里、可从 `tasks.md` 的 B 节直接链到，只是**不参与 `reviews/` 的证据一致性**。

**与「报告不放已归档 change」的关系**：B.1–B.8 的 tasks **住在已归档的 `witnessloop-adoption` 里**，本 change **不能**只把报告写在那儿（归档目录是 `event_explained` 受保护路径，每次写入都要解释事件；且那份 change 的实现 PR 已经合入，报告写在归档里等于给历史 change 补新证据，语义漂移）。⇒ 落点是**执行阶段 B 的这个 change 自己**，并在 `tasks.md` 里写一条「回链」任务：把报告路径写进 `witnessloop-adoption` 归档目录**之外**的跟踪入口（issue #305 的 comment），而不是往归档里加文件。

**否决的备选**：(a) `reviews/stage-b-observation.md` —— 触发孤儿；(b) 强制给观测报告建 stage=building manifest —— 同 stage 双份、`matching[0]` 错绑风险；(c) 只写进 `witnessloop-adoption` 归档 —— 受保护写入 + 语义漂移；(d) 写进 `docs/` —— 会把一次**阶段验证**的过程材料沉淀成项目文档，与「阶段 A 报告随 change 走」的先例不一致。

### Decision 7: 阶段 B 的证据形态与 `reviews/` 的一致状态

**选择**：
- **asterwynd 形态**：`/review-loop guard-write-allowlist` 产出 `reviews/building-review.md` + `reviews/building-review-manifest.json`（本仓生成器，`phase` 形态）。
- **witnessloop 形态**：额外跑 `uv run witnessloop manifest build --change guard-write-allowlist --stage <stage> --report reviews/<报告>.md`，产出 `reviews/<stage>.manifest.json`，**`reviews/` 下每一份 `.md` 都要有一份**（三份：`grill-design.md` / `grill-adversarial.md` / `building-review.md`）。
- **中间轮产物必须清理**：第 2 轮 `/review-loop` 会产出 `building-review-r1.md` 之类；它们在收尾前**要么删掉、要么改名成规范名**，否则成孤儿。
- **顺序硬约束**：manifest 必须在**所有内容提交之后**产出（`witnessloop-adoption` 的 Z.7：`_check_git_span` 只豁免 `.witnessloop/**`、`<changes_root>/*/reviews/**`、`<changes_root>/*/workflow-events.jsonl`、`archive/**`，而本 change 会改 `agent/**` / `docs/**` / `openspec/specs/**` ⇒ 先建的 manifest 到 PR 时必然 stale）。归档 move 仍必须是**独立纯 rename 提交**。

**理由**：阶段 B 的出口判据（`witnessloop-adoption` B 节）就是「两套 manifest 并存的真实成本」与「`witnessloop check` 真的核到证据」。而孤儿规则是这条路上唯一的**静默陷阱**——只落一部分比一份都不落更红（该 change 实测：2 → 14 → 16 条红）。本 change 的处理是**全绑 + 清中间轮**，正好把 N.6（归档里非规范报告的孤儿化）的迁移成本**在真需求上量一次**。

### Decision 8: 已知不兼容的归因口径（阶段 B 报告必须先分类再下结论）

**选择**：阶段 B 报告的 findings 必须**按成因分三类**，且不得混算：

| 成因 | 典型项 | 处置 |
|---|---|---|
| **格式选择导致的红** | 本 change 的 `grill-design.md` 里 `## Confirmed Decisions` 各块若用加粗 `来源` 写（不论独占行 `- **来源**:` 还是同行内联），`_SOURCE_RE`（`src/witnessloop/evidence.py:33`）不命中 ⇒ 每条决策各报一条「缺 `来源:`」；若按 grill 实际采用的 `- **决策**: …；来源: <run id>` 同行裸写法，则命中、不报。**本 change 自己的报告已实测为后者** | 记为**可选择的红**；由 Q11 裁定报告格式后再定归属 |
| **已知工具不兼容** | 上游 witnessloop issue #20 记录的谓词形态不兼容类问题（尚未关闭） | 记为**结构性红**，附「不属于阶段 B 的配置错误」的显式说明 |
| **配置问题** | policy 字段写错、glob 放宽错、执行点命令错 | 记为**可修红**，当次修掉 |

**前提订正（grill 实测证伪了本设计的原断言）**：原稿写「建了 witnessloop 形态 grill manifest 后 grill 正文判据**全红**」，并声称本仓 62 份归档记录通篇加粗。**实测不成立**：用 witnessloop 自己的 `grill_evidence_findings` 跑全部 **63** 份归档 `grill-design.md`（`openspec/changes/archive/*/reviews/grill-design.md`）得到 **39 份零 finding（判绿）**、**9 份**只报「缺 `来源:`」、**15 份**报其它项；其中**使用加粗 `来源` 写法的共 3 份**（独占行形式 `- **来源**:` **2 份** = `2026-08-03-grill-confirmation-gate` 与 `2026-10-13-witnessloop-adoption`；同行内联形式 **1 份** = `2026-09-29-workflow-recursion-limit-default`），**这 3 份全部被判 src-only（红）**。⇒ 「全红」是采用加粗写法的那三份的**局部事实**，不是本仓通例。落到本 change：这份 `reviews/grill-design.md` 的 `## Confirmed Decisions` 用的是同行裸 `来源:`，**7 条 source 判据全部命中**；它当前实测的 **13 条** finding 全部是「缺 `## User Confirmation` 小节」+「Q1–Q12 未经用户确认」这一类（Q 编号已与 `design.md` 对齐为同一套 12 条，见下节编号口径）——那是 tasks 0.3 收到答复后就消的状态，**不是** `来源:` 类红。

**理由**：若报告不分类，读者会把任一种红读成「接入没配好」，从而误判「值不值得真打开」——这正是 Decision 8 存在的目的。而把「我们可以通过写法避免的红」误归到「上游工具不兼容」，会让阶段 C 的「值不值得真打开」判断建立在假前提上。

## User Rulings（原 Open Questions，2026-10-14 用户逐条裁定，无遗留）

> **本 change 的 `## Open Questions` 已全部确认**：Q1–Q12 十二条（Q1–Q6 立项期提出、Q7–Q12 独立 grill 补充），**全部按本节的推荐值裁定**（2026-10-14 停轮拍板），逐条答复记录在 `reviews/grill-design.md` 的 `## User Confirmation`。无保留项、无新增停轮项。以下直接写**生效口径**，不列备选分支（未选分支的理由各压成一句「否决的备选」）。**编号与 `reviews/grill-design.md` 的 `## Open Questions` / `## User Confirmation` 完全一致**（机械门只读该文件）。

### U1（原 Q1）: allow 覆盖**文件级** deny，不覆盖结构性目录 deny 与 workspace 边界

**裁定**：`allowed_write_paths` 只重开文件级 deny（`.env` 族等敏感点文件名、`*.pem` / `*.key` / `*.pyc` 等无 `/` 的文件模式）；结构性目录 deny 不可覆盖（判定规则见 U12）；`assert_within_workspace` 的边界检查**先于**任何 allow 判定，不可被豁免。

**落地效果**：`tools.allowed_write_paths: ['deploy.pem', 'config/.env']` ⇒ `Write deploy.pem` 放行、`Write other.pem` 仍拒；`Write .git/config` 仍拒（`.git` 是 `SENSITIVE_DOTDIRS` 段）。

**否决的备选**：(a) 只覆盖 `.env` 族——用户拿不到 `.pem` 的豁免，而两者同属「用户自己的凭据文件」；(c) 全放开含 `.git/**`——`.git/hooks/*` 是代码执行点，等价于给 agent 一个 commit 钩子的写入权，且不解决任何真实需求。

### U2（原 Q2）: 粒度 = **精确 workspace 相对路径**；glob 元字符解析期 fail fast

**裁定**：条目是 workspace 相对路径的**字面值**（精确匹配）。含 glob 元字符（`*` `?` `[` `]`）、绝对路径、含 `..` 段、以 `/` 结尾的条目一律在**配置解析期 `ConfigError`**，不得宽容接受。

**落地效果**：`['.env', '.env.testing', 'config/.env', 'config/.env.testing']` 四条都生效；写 `['config/']` 或 `['**/*']` 直接在 `asterwynd.yaml` 加载期报错，进不了运行时。

**否决的备选**：(a) 任意 glob + 只特判 `**/*`——等价拼写（`./**/*`、`x/../**/*`）漏不完，且 `fnmatch` 的段边界语义与 `is_denied` 的段级判定不一致；(b) 目录前缀——`config/` 会把 `config/.env.production` 一起打开，与 U3 自相矛盾。**代价（接受）**：目录级授权不支持，10 个文件要写 10 条。

### U3（原 Q3）: `.env` 变体**不跟随**

**裁定**：`allowed_write_paths: ['.env']` 只放行 `.env` 本身；`.env.local` / `.env.production` 仍拒绝。要开哪个就再写一条。

**落地效果**：`Write .env` ⇒ ALLOW；`Write .env.production` ⇒ 仍 DENY（`Write denied by workspace policy`）；`cp .env.example .env.local` ⇒ Shell 层 `mv_cp_dest` 拒。业界同形：kimi-code 的 `ENV_PREFIX = '.env.'` 除 `ENV_EXEMPTIONS` 三个模板外一律判敏感（`kimi-code/packages/agent-core-v2/src/tool/path-access.ts:28-29,58-59`）；`#254` 刚把凭据变体收进 deny（`is_env_sensitive_name`，`agent/workspace_policy.py:91-102`）。

**否决的备选**：家族豁免——一个 `.env` 打开 `.env.production`（生产凭据位），与刚收紧的 deny 粒度反向。

### U4（原 Q4）: 配置**只做项目级** `asterwynd.yaml` 的 `tools.allowed_write_paths`

**裁定**：`ToolsConfig` 新增 `allowed_write_paths: tuple[str, ...] = ()`（`agent/config.py:152-161` 旁），`_parse_tools_config`（`:875-897`）走 `_parse_string_list` 后追加 U2 的语义校验；三个入口层构造点传入。**不加用户级 scope、不加环境变量通道。**

**落地效果**：仓库根写 `['.env']` ⇒ 该仓库任意子目录启动 CLI 都生效（配置发现向上找到 repo root 停）；换工作区则不生效。白名单随仓库进 git，改动过 review。

**否决的备选**：用户级（`~/.asterwynd/…`）——同一份仓库代码在本机与 CI runner 上门禁不同，而 CI 才是真锚；环境变量通道——等于白名单不进代码评审，与 #254 已拍板的「扩权必须可见」相悖。

### U5（原 Q5）: **只放行写**，读保持拒绝

**裁定**：allow 只接进 `assert_write_allowed`（`agent/workspace_policy.py:356-360`）与命令护栏的**写目标判定面**；`assert_read_allowed`（`:350-354`）、`is_denied`（`:316-338`）、`agent/code_intelligence/repo_map.py:173` 的索引跳过判定 SHALL NOT 被 allow 影响。

**必须写明的可用性边界（接受）**：`Edit` 不依赖 `assert_read_allowed`——它在 `assert_write_allowed` 之后自己 `read_text()`（`agent/tools/builtin/edit.py:55,67`），所以 `Edit .env` 可用；`Write` 拒绝覆盖已存在的文件（`agent/tools/builtin/write.py:52-56`）；**agent 读不回自己写的内容**（`Read .env` 仍拒）⇒ `Edit` 的 `old_string` 只能凭记忆，猜错即 `Error: old_string not found`。典型用法是「`Write` 建、`Edit` 改」，或先 `rm`（`rm .env` 由 `_check_target` 判 `rm_target`，可挂钩）再整文件 `Write`。

**否决的备选**：读写一起放——`Read .env` 会把 `API_KEY=sk-live-…` 明文带进上下文、trace 与 `messages.jsonl`。

### U6（原 Q6）: **不堵** Bash 读侧，记为债务另立

**裁定**：本 change 不新增读侧判定能力。如实写明「只放行写」的保护面**只在文件工具层**。

**背景（实测，非推理）**：Bash 层读 `.env` 今天本来就是通的——`cat .env` / `grep API_KEY .env` / `head -5 .env` / `source .env` / `. .env` 在两层全 ALLOW；只有 `mv`/`cp` 的**源位置**被查（`agent/tools/command_guard.py:872-878`），`python -c 'open(".env").read()'` 被 `DEFAULT_DENYLIST` 的 `python3?\s+-c` 拦下（另一条理由）。⇒ 任何「只放行写 ⟹ 凭据读不到」的说法都必须限定在文件工具层。

**落地**：记入 `docs/known-debt.md`（受保护路径，配 `protected_artifact_explained` 事件）；见 tasks 7.1。

**否决的备选**：顺手堵——要给 `cat` / `head` / `tail` / `less` / `grep` / `source` / `.` / `awk` 等一批命令新增读目标语义，`#254` 的护栏刻意只对写命令做目标判定；扩读侧立刻带来误报面（`git log -- .env`、`grep -rn "cat .env" docs/`），而误报在无 UI 环境下等于硬拒。

### U7（原 Q7）: **不动** `_EXTRA_DENYLIST`，接受嵌套路径的 Bash `cp`/`mv` 不在范围内

**裁定**：命令护栏第 1 步的整句 denylist 正则扫描保持现有语义、不可被配置覆盖；**接受**下列兑现面，并把 change 文档与配置示例改成**可兑现**形态（见 Decision 9 的表）：

| 路径形态 | 文件工具（`Write`/`Edit`） | Bash `echo >>` / `tee` / `dd of=` / `install` | Bash `cp` / `mv` |
|---|---|---|---|
| **裸名**（`.env`） | ✅ | ✅ | ✅（`mv_cp_dest`，可挂钩） |
| **嵌套**（`config/.env`） | ✅ | ✅（`protected_redirect` / `tee_target` / `dd_target` / `install_target`，均可挂钩） | ❌（`last_reason=denylist`，pre-IR、不可挂钩） |

**落地效果**：`tools.allowed_write_paths: ['.env', '.env.testing']`（两个裸名，全兑现）。配嵌套路径时用户必须知道「`Write` / `Edit` / `echo >>` / `tee` / `dd of=` / `install` 生效，`cp` / `mv` 仍拒，且报错文案是笼统的 `Command denied by sandbox command guard`」。

**否决的备选**：把 allow 判定提到 denylist 扫描之前——那条整句正则是 `#254` 重建的单一解析管线的**第一道**、也是承载攻击用例最多的通道（`#254` 的 RIR findings 5 实测：清空 denylist 后攻击集拦截数 **54 → 20**）。

### U8（原 Q8）: allow **只在写路径求值**；共享谓词函数、不共享调用点

**裁定**：共享的是**谓词函数**（如 `workspace_policy.write_allowlist_covers(resolved_rel_path, allowlist)`），它的调用点只有 `assert_write_allowed` 与命令护栏的**写目标判定面**（口径见 Decision 2）。`is_denied` 保持原语义、SHALL NOT 感知 allowlist。

**落地效果**：`allowed_write_paths: ['.env']` ⇒ `Write .env` ALLOW、`Read .env` 仍 DENY、RepoMap 仍跳过 `.env`（不收进符号索引）。实测：`is_denied` 是 `assert_read_allowed`（`:352`）与 `assert_write_allowed`（`:358`）的**同一实现**，`repo_map.py:173` 还直接调它。

**否决的备选**：(a) 写进 `is_denied`——会同时打开 `Read` / `Grep` / `ListFiles` / `Find` / `ReadDoc` / `InspectGitDiff` / LSP 的读**与 RepoMap / SymbolSearch 的索引面**（后者不报错，只是默默把凭据文件送进索引），并直接违反 U5；新增 `is_write_denied` 而复用 `is_denied` 的结果等价于 (a)。

### U9（原 Q9）: 作用域 = **任一 workspace 根**的相对路径

**裁定**：allow 条目按 `relative_path()` 的现有语义比较——主 workspace 与**附加根**（`/workspace add` / Web hub「+ 添加」）下的同名相对路径**都**被覆盖。

**落地效果**：主根 `/repo`、附加根 `/srv/other`（`web/session.py:1516` 的 `register_workspace`；CLI 侧 `agent/commands/registry.py:507` 的 `policy.add_root(arg, create=True)`），配 `allowed_write_paths: ['.env']` ⇒ `Write /srv/other/.env` ⇒ ALLOW（`relative_path` 对附加根返回根相对路径，`agent/workspace_policy.py:307-314`）。

**须如实记录的边界**：Bash 层 `cp x /srv/other/.env` 实测 `last_reason=denylist`——附加根必然是绝对路径、含 `/`，先命中 `command_guard.py:609` 的**不可挂钩**整句正则，与 U7 的嵌套路径缺口**同源**。

**否决的备选**：只覆盖主 workspace 根——需要额外解释「为什么同一个相对路径在不同根下结论不同」，而「用户加根」本身已经是一次显式授权。

### U10（原 Q10）: **规格随裁定改，design 与规格同向**

**裁定**：用户裁定后**先重写 change 的 spec delta**（tasks 1.1/1.2），再让 `design.md` 的 Decisions 与规格对齐（tasks 1.4 已按此改写），不允许出现「实现按 design、测试对照旧规格」的中间态。

**落地效果**：本 change 的十二条裁定全部等于 spec delta 已写的推荐值 ⇒ 规格**无需因裁定改写**，只需按 U9 补一条附加根作用域的 Scenario（已补）。若日后有裁定与规格冲突，顺序仍是「规格先、design 后」。

**否决的备选**：design 先改、规格后跟——中间态会出现实现与验收判据错配。

### U11（原 Q11）: `reviews/grill-design.md` 保持**同行裸 `来源:`** 写法

**裁定**：本 change 的 grill 记录保持 `- **决策**: …；理由: …；来源: <run id>`（裸 `来源:` 与决策同 bullet），不用加粗写法；Decision 8 的归因表保留「**格式选择导致的红**」这一类，与上游 issue #20 那类结构性不兼容分开。

**落地效果（实测）**：`_SOURCE_RE = re.compile(r"来源\s*[:：]")`（`src/witnessloop/evidence.py:33`）配 `re.search(block)` ⇒ 本 change 的 7 条 Confirmed Decisions **source 判据全命中**，witnessloop 侧的 finding 只剩「未确认」类（本次裁定后归零）。

**否决的备选**：改用加粗写法——本仓 63 份归档里使用加粗 `来源` 的 3 份（独占行 2 + 同行内联 1）**全部**被判 src-only 红，属自造红。

### U12（原 Q12）: 结构性 deny 用**两源推导**

**裁定**：**结构性 deny** ＝ `含 '/' 的 deny 条目` **∪** `路径中任一**路径段**命中 `SENSITIVE_DOTDIRS``；其余 deny 条目为**文件级、可豁免**。规则写进规格且必须**可机械复算**（对 32 条表逐条断言分类 + 对 `SENSITIVE_DOTDIRS` 逐条断言）。

**落地效果**：`allowed_write_paths: ['.ruff_cache/CACHEDIR.TAG', '.git/config']` ⇒ 两者都仍 DENY（前者被 `含 '/' 的 .ruff_cache/**` 覆盖，后者被段级 `.git` 覆盖）；同配置下 `Write .ruff_cache/x.pyc` 也仍拒（`*.pyc`）。

**必须如实写的残余**：在「精确路径 + `Write`/`Edit` 自带的目录检查」下，本裁定与备选的实际后果差别**很小**——`allowed_write_paths: ['.venv']` 即便归为「文件级」，也只能放行一个**恰好叫 `.venv` 的文件**（`Write .venv` 会被 `write.py` 的 `is_dir()` 拒），`.venv/x.py` 仍拒（`.venv/**` 结构性）。⇒ 这一问的取舍主要是**可预测性与可测试性**，不是安全强度。

**否决的备选**：(i) 封闭列举规格里手写的 6 条——会随 `DEFAULT_DENIED_PATTERNS` 增删**静默失配**，且实测漏了 `.pytest_cache/**`、`.mypy_cache/**`、`venv/**`、裸 `node_modules`、裸 `.git`；「含 `/` 即目录级」的单源推导实测**误分类 11 条**（8 条裸目录名被划成文件级、3 条 `**/id_rsa` 私钥模式被划成目录级）。

## Pre-Implementation Review

- Questions resolved（本 change 内已定）：
  - 「接线成本极小、照抄 `command_denylist` 约 6 行」——**部分成立**：配置字段与解析确实是同构照抄（Decision 4），但**判定面是新增的**（Decision 1，不能靠覆写 `denied_patterns`），且 Bash 层还多一个传参面（Decision 2，`agent/tools/builtin/bash.py:87` 只拿得到 `workspace_root`）。⇒ 工作量从「6 行」修正为「两个判定器 + 一个传参面 + 三层测试」。
  - 阶段 B 观测报告落点 —— **已定**（Decision 6：change 根目录，避开 `reviews/` 的孤儿规则）。这是本 change 必须自己拍的，不能留给阶段 B 现场决定。
  - 阶段 B 的 `reviews/` 一致状态 —— **已定**（Decision 7：全绑 + 清中间轮）。
  - 已知不兼容的归因口径 —— **已定**（Decision 8：先分类再下结论）。
- Questions resolved（**由代码给出带证据的答案，移出停轮队列**）：
  - 「生产构造点几处、在哪」——**代码判定**：三处，`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349`（全仓 grep + 排除 `policy or WorkspacePolicy()` 兜底与 factory 默认参数）。issue 写的 `web/session.py:1566` 已漂移。
  - 「`denied_patterns` 能不能直接当 allow 的载体」——**代码判定**：不能（探针实测 `denied_patterns=()` 下 `.env` 仍 `is_denied=True`）。
  - 「Bash 层读 `.env` 是否已被拦」——**代码判定**：没有，`cat .env` / `grep API_KEY .env` / `source .env` 两层全 ALLOW（探针实测）。这条把 U6 从「要不要顺手堵」变成「要不要**新增**一个读侧能力」。
- Options considered:
  - **A. 只接文件工具层**（不动 `CommandGuard`）：**否决**——`echo API_KEY=x >> .env` / `tee .env` / `dd of=.env` 仍被拦，功能半残，且用户无法预期「为什么 Write 能写 Bash 不能写」。
  - **B. 只接 Bash 层**（不动 `WorkspacePolicy`）：**否决**——`Write` / `Edit` 仍拒，主用法（agent 生成配置文件）走不通。
  - **C. 两层各实现一份 allow 匹配**：**否决**——重演 D12 的漂移，且这次是「宽松方 vs 严格方」不一致，更难发现。
  - **D. 复用 `denied_patterns` 做减法**：**否决**（Decision 1，实测无效）。
  - **E. 引入 glob / 目录前缀授权**：**否决**（Decision 3，与业界做法相反，且直接撞上 issue 的 `**/*` 实测坑）。
  - **F. 本 change（Decision 1–5 + 9）**：新增独立判定面 + 共享谓词（不共享调用点）+ 精确路径 + 只写 + 配置同构 + 诚实划定兑现面。
- Rejected alternatives：A–E 的理由如上。另否决「在本 change 内顺手收口 Bash 读侧」（U6 的否决备选，会把范围扩到读判定与一批读命令的误报面）、「把 allow 写进 `is_denied`」（U8 的否决备选 (a)，会同时打开读侧与 tree-sitter 索引面）、「为嵌套路径动 `_EXTRA_DENYLIST` 扫描顺序」（U7 的否决备选 (b)，见 Decision 9）。
- **独立 grill 已完成的核对（`reviews/grill-design.md`，run `grill-guard-write-allowlist-20261014`，被审 revision `f09fa77`）**：
  - **已确认（7 条 Confirmed Decisions）**：allow 必须是独立判定面（`denied_patterns=()` 下 `.env` 仍拒，实测）；`CommandGuard` 生产路径唯一构造点 `bash.py:87`；两套 manifest 并存**不冲突**（`reviews/*.manifest.json` 的 `*.manifest.json` 要求字面 `.manifest.json` 后缀，本仓 `building-review-manifest.json` 匹配不上——隔离模拟实测孤儿清单为 **0**）；观测报告落 change 根目录**正确且必要**（孤儿判定在 `validate_review_manifests` 内、对 `reviews/**/*.md` 逐份要求绑定）；`.env` 变体不跟随、模板保持放行；「Bash 读 `.env` 今天本来就通」属实；`rm .env` 由 `_check_target` 判（`reason=rm_target`）⇒ U5 的「先删再 `Write`」笨办法**可行**（`_check_rm` 只判逃逸面，不在收敛清单里是对的）。
  - **已按 grill 修订（本节的 9 条「必须修改项」全部落实）**：① Decision 2 重写为「共享谓词函数、不共享调用点」，`is_denied` 保持原语义，并逐条列出不受影响的面（含 `repo_map.py` 的索引跳过）；② 新增 **Decision 9** 诚实划定兑现面（嵌套路径的 Bash `cp`/`mv` 不在范围内），并同步改 proposal 的示例与 Non-Goal；③ 规格的「两层结论同向」改为**可满足的增量表述**；④ Decision 8 的「全红」前提按实测改为**条件式**并加第三类归因；⑤ tasks 的 witnessloop 调用方式改为在 witnessloop 源码树里跑；⑥ tasks 的 0.5/1.4 先后口径写死为「规格随裁定改」；⑦ 构造点清单从三处改为**四处**并写明 dry-run 沙箱与兜底的区别；⑧ 结构性 deny 的判定机制立 **Q12** 并由推导规则给出可测试定义；⑨ 反复核对了全部 `文件:行号` 锚点（本文件与 proposal 的引用均在 `f09fa77 + 本次修订` 的前树上现测）。
  - **用户已裁定（12 条，2026-10-14 停轮拍板、全部按推荐值）**：Q1–Q6 为立项原提，Q7–Q12 为 grill 补充，**每条都配了本 change 真实场景的具体例子**；生效口径见 `## User Rulings`（U1–U12），逐条答复见 `reviews/grill-design.md` 的 `## User Confirmation`。其中 Q7 与 Q8（grill 判定的阻塞项）已一并裁定。
- Final confirmations：
  - **停轮确认已完成**（AGENTS.md 的 grill-confirmation-gate 已满足）：`reviews/grill-design.md` 的十二条 Open Question 已由用户于 **2026-10-14** 逐条答复并记入该文件的 `## User Confirmation`（实测 `_unconfirmed_open_questions` 返回空）；生效口径落在本文件的 `## User Rulings`。⇒ **可以进入实现**。
  - 设计阶段审阅闭环（`reviews/grill-adversarial.md`）同样在实现前必须收敛（grill-flow-hardening / issue #298）——它审的是**本次修订后的** design。
- Remaining risks：见下节 R1–R14。

## Risks / Trade-offs

- **[R1] 「同源」被实现成「同名两份」**：两层都叫 `allowed_write_paths` 但各写一份匹配逻辑 ⇒ 文件工具放行而 Bash 拦（或反向），且哪边生效取决于用哪个工具。**Mitigation**：Decision 2 把判定抽成共享**纯函数**并由测试锁定——新增一条跨层回归测试，但**测的是增量而非绝对值**：对同一组路径断言 `assert_write_allowed` 与 `CommandGuard` 写目标判定的**变化方向同向**（allow 命中 ⇒ 两处都从拒变放行；未命中 ⇒ 两处都与今天逐条一致）。**SHALL NOT** 断言「两层对所有路径恒同向」——实测今天已有 8/13 条被拒路径两层不同向（Bash 更宽），见 R10。
- **[R10] 两层「绝对同向」是变更前就不成立的断言**（grill 实测，原稿的规格与 2.6 测试按它写会一写即红）：`CommandGuard` 的目标判定（`_dest_is_sensitive` + 固定 `_DENY_PATHS`）**不读** `DEFAULT_DENIED_PATTERNS` 那张 glob 表 ⇒ `deploy.pem` / `srv.key` / `id_rsa` / `node_modules/x.js` / `benchmarks/runs/r.json` / `.venv/y.py` / `__pycache__/z.pyc` / `.ruff_cache/x` 在文件层 DENY、Bash 层 `cp x <path>` ALLOW 且 `last_reason=None`。**Mitigation**：规格改写为「allow SHALL NOT 使任一层比引入本能力前更宽」+「allow 命中的路径两层变化同向」；任务 2.6 按此写；这条既存差异**不修**（不在本 change 范围），但**必须在阶段 B 的分叉清单里出现**。
- **[R11] allow 的兑现面被过度承诺**：proposal 原先举的 `['.env', 'config/.env']` 会让用户以为嵌套路径两层通吃，实际 Bash 的 `cp`/`mv` 仍拒（`_EXTRA_DENYLIST` 整句正则前置，实测五变体全灭）。**Mitigation**：Decision 9 写死兑现面表；proposal 示例改成可兑现形态；规格新增一条「Bash 覆盖面差异 SHALL 被记录」的 Requirement；该取舍已由 U7 裁定（不动 denylist）。
- **[R12] 附加根（`/workspace add`）下的同名路径语义**（**U9 已裁定：任一 workspace 根**）：`relative_path()` 对附加根返回根相对路径，而 `is_denied` 对主根之外只做 basename 判定 ⇒ 两种口径给出相反结论，且 Bash 层恒不看 workspace 根。**Mitigation**：Q9 停轮裁定作用域口径；裁定前不写对应实现与测试；无论选哪支，阶段 B 报告都要记这条三层（文件主根 / 文件附加根 / Bash）的差异。
- **[R13] `allowed_write_paths` 是构造期快照**（grill R5）：`CommandGuard` 在 `BashTool.__init__`（`agent/tools/builtin/bash.py:87`）一次性构造，运行中改 policy 属性不会影响它。**Mitigation**：Decision 2 明写「快照于构造期」这个边界；本 change 不引入运行中改配置的路径；若日后有（Web 会话改配置 / 测试），需要显式重建工具集。
- **[R14] 阶段 B 的 `uv run witnessloop` 会静默跑到 PATH 上那份**（grill R4，实测 `uv run which witnessloop` ⇒ `/home/happy/.local/bin/witnessloop`、`uv run python -c "import witnessloop"` ⇒ `ModuleNotFoundError`）：按 `tasks.md` 原文字面执行，阶段 B 会拿到 0.1.0 的判定，把「放行/绿」误读成证据完备。**Mitigation**：tasks 6.2 改为 `cd <witnessloop 源码树> && uv run witnessloop …`（与 `docs/development-guide.md` 的既有口径一致）；并注意 `plugin/hooks/guard.sh` 内硬编码裸命令，这条缓解**覆盖不到它**。
- **[R2] 否定用例被漏掉 ⇒ allow 变成后门**：最常见的实现滑手是「命中 allow 就 return allow」写在 workspace 边界检查**之前**，那样 allow 条目一旦写成绝对路径就能写 workspace 外。**Mitigation**：① Decision 3 在解析期拒绝绝对路径与 `..`；② 否定用例三条（未列入的 `.env`、`.env.local` 变体、`../` 逃逸）写成硬性任务；③ 规格里把「`assert_within_workspace` 先于任何 allow 判定」写成 Requirement。
- **[R3] 配置错写的暴露延迟**：与本仓 `--policy` 同类的坑——配置解析若对非法值宽容，错误只会在运行时以「莫名还是被拒」的形式暴露。**Mitigation**：Decision 3/4 的语义校验在**解析期 fail fast**（`ConfigError`），并在 `asterwynd.example.yaml` 给出正例。
- **[R4] 「只放行写」的可用性被低估**：agent 写不了 `.env` 又想改，只能整文件 `Write`（被「已存在」挡）或 `Edit`（要 `old_string`，但它读不到内容）。**Mitigation**：Q5 的例子把这个链路完整走一遍给用户看，由用户拍板；不接受「用户以为能改其实改不动」的默认。
- **[R5] 权限面扩大的既有语义问题**：`.env` 写入本身可能是**代码执行向量**（`source .env` 在 shell 里执行内容；某些工具链会读 env）。本 change 只是把「用户显式授权的文件」从不可写变为可写，判定者仍是人；但**必须写明这不是安全边界**（护栏不是边界，`ProcessBackend` 才是）。**Mitigation**：写进规格与 Impact Analysis 的「行为变更」段，不让它被读成「安全能力」。
- **[R6] 阶段 B 激活 witnessloop 孤儿规则 ⇒ `reviews/` 从 2 条红变 14/16 条**（`witnessloop-adoption` 实测）。**Mitigation**：Decision 7 的「全绑 + 清中间轮」，并在报告里如实记这条成本（它正是 N.6 的迁移成本样本）。
- **[R7] 阶段 B 的 grill 正文判据是否判红取决于报告格式**（**原「结构性判红」已按 grill 实测证伪**）：`_SOURCE_RE` 只要求块内有裸 `来源` + 冒号，加粗写法（`来源` 后接 `**`）**不命中**；63 份归档里 **39 份判绿**，含加粗 `来源` 的 **3 份**（口径见 Decision 8：其中独占行形式 `- **来源**:` 2 份、同行内联形式 1 份；三种写法**都**判 src-only 红）。本 change 自己的报告用同行裸写法 ⇒ source 判据全命中，当前 **13 条** finding 全是「未确认」类（tasks 0.3 后即消）。**Mitigation**：Decision 8 的三分类归因表（新增「格式选择导致的红」一类）；Q11 裁定报告格式；本 change **不放宽判据、不改既有归档格式**（U7 已拍板）。
- **[R8] 本 change 自己会成为 witnessloop 的「已知红」**：本 change 的 diff 触达 `agent/**` / `web/**` ⇒ `code_hits` 非空 ⇒ `building` 与 `grill-adversarial` 两条 stage 判定**会真的触发**（这既是阶段 B 想要的，也意味着本 change 的红数比 `witnessloop-adoption` 多）。**Mitigation**：阶段 B 报告如实列出并分类；不放宽判据。
- **[R9] 阶段 B 的报告纪律**：观测报告若在**最后一刻**才写，会与 manifest 的 stale 顺序约束打架。**Mitigation**：报告作为**内容提交**（非证据路径之外的内容），manifest 在其后重建（Decision 7）。

## Testing Strategy

测试分层按本仓既有约定（`docs/testing-guide.md`），**测试先行**：

1. **单元：`WorkspacePolicy` 的 allow 判定**（`tests/agent/test_workspace_policy.py`）
   - 正例：`allowed_write_paths=('.env',)` ⇒ `.env` 的 `assert_write_allowed` 通过；`config/.env` 同理。
   - **否定例（硬要求）**：① 同一 policy 下 `.env.local` / `.env.production` / `.env.example` 的行为与 allow 前**一致**（前两者仍拒、模板仍放行）；② 未列入的 `.env`（`allowed_write_paths=('.env',)` 下的 `other/.env`）仍拒；③ `../outside/.env` 仍因**边界**被拒（allow 不得先于边界生效）；④ 结构性目录 deny（`.git/config`）即便被显式列入仍拒（按 U1 + U12 的裁定写）。
   - 默认值：`allowed_write_paths=()` 时全部断言与今天逐条一致（回归线）。
2. **单元：`CommandGuard` 的同源生效**（`tests/agent/tools/test_command_guard.py`）
   - 正例（**按 Decision 9 的兑现面表写**）：带 allowlist 的 guard 下**裸名** `.env` 的 `cp x .env` / `echo X >> .env` / `tee .env` / `dd of=.env` 由 DENY 变 ALLOW；**嵌套** `config/.env` 的 `echo K >> config/.env` / `tee` / `dd of=` / `install` 由 DENY 变 ALLOW。
   - **否定例（含 Decision 9 的边界）**：不带 allowlist 时上述命令仍 DENY（与今天的断言逐条一致）；带上 `config/.env` 豁免后 **`cp x config/.env` / `mv x config/.env` 仍 DENY 且 `last_reason=="denylist"`**（这是**故意**的边界，不是缺陷——把它写成断言，避免日后有人「顺手修好」而改动 denylist 语义）；带 allowlist 时 `cp x .env.local` 仍 DENY；`cp x /etc/passwd` 仍 DENY（结构性 deny 不被 allow 影响）。
3. **跨层一致性（R1/R10 的锁定，**测增量不测绝对值**）**：对同一组路径断言**变化方向同向**——allow 命中的路径在 `assert_write_allowed` 与 `CommandGuard` 写目标判定上**都**从拒变放行；未列入的路径两处都与今天逐条一致。**SHALL NOT** 断言「两层对任意路径恒同向」（实测 8/13 条被拒路径今天两层就不同向）。
4. **配置层**（`tests/agent/test_config.py`）
   - `tools.allowed_write_paths` 缺失 ⇒ `()`（默认空，deny 默认不变）。
   - 正例解析：YAML 里 `['.env', 'config/.env']` ⇒ 元组。
   - **fail fast**：含 `*` / 绝对路径 / `..` / 尾 `/` 的条目 ⇒ `ConfigError`（逐条一条用例）。
   - **结构性 deny 的分类规则（U12 的裁定：两源推导）**：对 `DEFAULT_DENIED_PATTERNS` 的每条断言分类结果（含 `/` ⇒ 目录级不可豁免；无 `/` ⇒ 文件级可豁免），使规则可机械复算。
5. **Bash 攻击集不回归**：`benchmarks/attacks/attacks.json` 的 `deny` 用例在**配置了 allowlist** 的 guard 下仍全部被拦（allow 只放宽被明确列入的路径，攻击集里的 `/etc/`、`~/.ssh/` 等不受影响）。
6. **benchmark smoke**：本 change 触及 `agent/workspace_policy.py` 与 `agent/tools/`（命中 checker 的 benchmark smoke 触发面）⇒ 跑一条 benchmark smoke 确认工具策略接线未破。
7. **不做的事**：不为 U6（Bash 读侧）、U9 的 Bash 层附加根差异、Decision 9 的嵌套 `cp`/`mv`（U7 已裁定）写实现——它们不在本 change 范围。**但 Decision 9 的边界必须写一条断言**（「仍 DENY」是规格行为，不是遗漏）。

**阶段 B 的「测试」**（本 change 的流程验证腿）：见 `tasks.md` 的 B 节。它不是 Python 测试，而是「在并存期跑通完整链路并如实记录分叉」。

## Impact Analysis

- **新增**：`openspec/changes/guard-write-allowlist/stage-b-observation.md`（阶段 B 观测报告，change 根目录，见 Decision 6）；witnessloop 形态 manifest `reviews/grill.manifest.json` / `reviews/grill-adversarial.manifest.json` / `reviews/building.manifest.json`（阶段 B 产出，见 Decision 7）。
- **修改（生产）**：`agent/workspace_policy.py`（新增 `allowed_write_paths` 参数 + 共享**纯函数**；`is_denied` 保持原语义）、`agent/tools/command_guard.py`（消费同一份 allowlist + 共享谓词）、`agent/tools/builtin/bash.py`（传参面，`:87`）、`agent/config.py`（`ToolsConfig` 字段 `:151-161` + `_parse_tools_config` `:875-897` + fail fast）、`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349`、`asterwynd.example.yaml:35`。
- **受影响但属正确的同源行为（grill 指出的漏列）**：`agent/browser/policy.py:121` 也调 `assert_write_allowed` ⇒ **浏览器产物落盘会一并继承 `allowed_write_paths` 豁免**。这是正确的同源效果，但必须列出来，否则读者会以为改动面止于上面那 8 个文件。
- **明确不受影响（Decision 2 的对照清单）**：`WorkspacePolicy.is_denied`（`:316-338`）的语义、`assert_read_allowed`（`:350-354`）、`agent/code_intelligence/repo_map.py:81,96,173`（tree-sitter / RepoMap 的跳过判定）、`agent/tools/builtin/{read,grep,list_files,find,read_doc,inspect_git_diff,lsp}.py` 的读路径。
- **修改（测试）**：`tests/agent/test_workspace_policy.py`、`tests/agent/tools/test_command_guard.py`、`tests/agent/test_config.py`。
- **修改（文档）**：`docs/development-guide.md`（配置项说明 + 阶段 B 的跑法）；`docs/openspec-change-backlog.md`（登记/清理，受保护路径配 `backlog_updated` 事件）；`openspec/specs/workspace-safety/spec.md` 与 `openspec/specs/configuration/spec.md`（同步 delta，配 `current_spec_synced` 事件）。
- **文档影响面扫描（AGENTS.md 要求，grill R3 指出原稿漏列）**：收尾阶段 7.1 必须扫 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与本变更相关的段落。已知命中一处**会变半真**：`docs/interview-script/walkthrough/W06-security.md:34` 现写「敏感文件 deny（`DEFAULT_DENIED_PATTERNS`）：.git/**、.env*、*.pem、id_rsa、__pycache__ 等，**读写都拒**」——本 change 落地后「写」侧多了一条显式豁免通道。**另有四处在变更前就存在的历史口径问题**（不在本 change 范围，按 AGENTS.md 记债务）：① 同文件 **`:11`**（`└─ 命令拒绝列表：DEFAULT_DENYLIST（58 个危险模式）`）与 **`:35`** **两处**都写 `DEFAULT_DENYLIST` 为「58 个模式」（实测 **59**）；② `docs/interview-bullets/walkthrough.md:2483` 写「**35 条**」并列了 `.env` / `.env.*` / `**/.env` 等模式（实测 `DEFAULT_DENIED_PATTERNS` 现为 **32** 条，且 `.env` 族早已改由段级谓词判、不在该表里；同文件 `:2497` 的「合计 35 条 glob pattern（9 大类）」同源）；③ 同文件 `:2481` 引 `agent/workspace_policy.py:9-45`（现为 `9-43`）；④ 同文件 `:2499` 引 `is_denied()` 为 `:222-239`（现为 `:316-338`）。7.1 要对这五处（含 ① 的两处）各给「改 / 不改 / 记债」的结论。
- **明确不改**：`AGENTS.md` 流程段、`.github/workflows/ci.yml`、`.witnessloop/**`、`scripts/**`、branch protection、`agent/approval.py`、`CommandVerdict` 的三态语义、`DEFAULT_DENYLIST` / `_EXTRA_DENYLIST` / `_match_allowlist`（Q7 裁定前）。
- **回退**：删掉配置项即回到今天的行为（默认空列表 ⇒ 零行为变化）；代码侧回退是一次普通 revert，无数据迁移、无持久化状态。
