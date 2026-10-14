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

四条结论，其中三条与 issue 的说法有出入或 issue 未覆盖：

1. **生产构造点确实是三处**：`agent/main.py:251-254`、`web/session.py:1728-1731`、`benchmarks/agent_runner.py:349-352`（全仓 `grep -rn "WorkspacePolicy("` 复核，排除 `agent/tools/builtin/*.py` 里 `policy or WorkspacePolicy()` 的兜底与 `agent/tools/factory.py:316,422` 的默认参数）。**但与 issue 的差异**：issue 写的 `web/session.py:1566` 在当前树上已漂移到 `:1728`。⇒ 引用行号必须每次现测。
2. **`WorkspacePolicy.__init__` 确实已接受 `denied_patterns`**（`agent/workspace_policy.py:239`）——issue 这条对。**但「把 allowlist 接上 `denied_patterns`」是错的**：`denied_patterns` 只喂 `is_denied` 里那一路 **glob 判定**（`:331-337`），而 `.env` 命中的是**段级敏感名判定**（`:326-330` 的 `is_sensitive_dot_name`）。实测：`WorkspacePolicy(root, denied_patterns=())` 下 `.env` 仍 `is_denied=True`。⇒ allow 必须是**独立于 `denied_patterns` 的一个新判定面**，不能靠覆写 glob 表实现。
3. **issue 说「护栏用另一张表，必须同源喂给两层」——对，且比 issue 描述的更封闭**：`CommandGuard` 在**生产路径上只有一个构造点** `agent/tools/builtin/bash.py:87`（`self._guard = CommandGuard(workspace=self.policy.workspace_root)`），它**只拿得到 `workspace_root`**，拿不到 policy 本身、更拿不到任何配置。⇒ 「同源」需要**新增传参面**（`BashTool` → `CommandGuard`），不是「配置里补一个字段」就自动同源。
4. **issue 未覆盖的一条**：**读侧的不对称**。文件工具层的读被拒（`Read`/`Grep`/`ListFiles` 走 `assert_read_allowed`，`agent/workspace_policy.py:350-354`），但 **Bash 层的读今天本来就是通的**——`cat .env` / `grep API_KEY .env` / `source .env` 两层全 ALLOW（实测）。只有 `mv`/`cp` 的**源位置**被查（`_check_target` 的 `mv`/`cp` 分支，`agent/tools/command_guard.py:872-878`），`python -c 'open(".env").read()'` 被 `DEFAULT_DENYLIST` 的 `python3?\s+-c\b` 拦下（那是另一条理由）。⇒ 任何「只放行写 ⟹ 凭据读不到」的说法都必须限定在**文件工具层**，否则是失真陈述。

## Goals / Non-Goals

**Goals:**

- 新增 `tools.allowed_write_paths` 配置，语义是「deny 默认 + **精确**可写覆盖」；默认空列表 ⇒ 不配置时行为零变化。
- allow 的判定**同源**喂到 `WorkspacePolicy`（文件工具层）与 `CommandGuard`（Bash 层）两个判定器。
- 把三条硬约束写进规格：不越 workspace 边界、不接受「匹配一切」的模式、不放宽结构性目录 deny 与命令 denylist。
- 用**否定用例**（未列入的 `.env` 仍拒）钉死「allow 没被实现成后门」。
- 把 6 条政策取舍（每条带具体例子）停轮抛给用户，收到答复前不写实现代码。
- 作为 `witnessloop-adoption` 的阶段 B 载体，产出：asterwynd 形态审阅证据 + witnessloop 形态 manifest + 分叉清单 + 按成因分类的红清单 + 「值不值得真打开」的判断依据。

**Non-Goals:**

- 不允许模型自己配白名单（#254 已拍板否决）；不引入「模型提议 → 落规则」的通道。
- 不放宽 `DEFAULT_DENYLIST` / `_EXTRA_DENYLIST` / `_match_allowlist` 的任何语义。
- 不为 allow 支持 glob、目录前缀或 `~` 展开（若 Q2 裁定要目录级，那是本 change 之外的扩展）。
- 不改 `assert_within_workspace` 的边界（allow 只在 workspace 内生效）。
- 不合并 Bash 读侧缺口（`cat .env` 通着）——见 Q6，推荐记为债务另立。
- 不修 witnessloop 侧的已知不兼容（`:来源` 谓词，上游 issue #20），不为变绿放宽任何判据。
- 不改 `.github/workflows/ci.yml`、不动 branch protection、不改 `AGENTS.md` 的流程段。

## Decisions

### Decision 1: allow 是**独立判定面**，不靠覆写 `denied_patterns` 实现

**选择**：`WorkspacePolicy` 新增独立的 `allowed_write_paths` 参数与谓词（`is_write_allowed` 或等价物），**不改** `denied_patterns` 的语义与默认值。

**理由**：见「实现要点复核」第 2 条——`.env` 命中的是 `is_denied` 里的**段级敏感名判定**，`denied_patterns` 那条路根本管不到它。若把 allow 实现成「从 `denied_patterns` 里删掉命中项」，对 `.env` 完全无效。

**否决的备选**：把 allow 实现成「`denied_patterns` 的减法」——对 `.env` 无效（实测），且会把「用户配的 allow」与「内置 deny 表」耦合成一个可被写坏的单一列表。

### Decision 2: 两层同源：`WorkspacePolicy` 持有数据，`CommandGuard` 通过 `BashTool` 消费同一份 + 共享谓词

**选择**：
- `allowed_write_paths` 的**唯一数据源**是 `WorkspacePolicy` 的实例属性。
- `CommandGuard.__init__` 新增参数接收**同一个元组**（不是重新解析一份配置）。
- `BashTool.__init__`（`agent/tools/builtin/bash.py:87`）构造 `CommandGuard` 时把 `self.policy.allowed_write_paths` 传进去。
- 判定逻辑抽成**一个共享函数**（如 `workspace_policy.is_write_allowed(resolved_rel_path, allowlist)`），`WorkspacePolicy.is_denied` 与 `CommandGuard` 的 `_check_target` / `_has_protected_redirect` 都调它，**禁止两层各写一遍路径匹配**。

**理由**：`#254` 的 D12 教训就是「同一语义有两个实现 ⇒ 必然漂移」（`.env.local` 曾被文件工具拒、被 Bash 护栏放行）。本 change 的 allow 如果两层各写一遍，会**重演同一个 bug 的反向版本**：文件工具放行、Bash 拦住（或反过来），而哪一边生效取决于用户用哪个工具。issue #272 把这条列为「⚠️ 关键坑」，本 change 把它当作设计的第一个约束。

**落点被数据钉死**：因为 `CommandGuard` 生产路径上只有 `agent/tools/builtin/bash.py:87` 一个构造点（实测），传参面就是 `BashTool.__init__` 一行 + `CommandGuard.__init__` 一个参数；`agent/tools/factory.py:335,457` 的两处 `BashTool(policy=policy, ...)` 不需要改（它们已经传了 policy）。

### Decision 3: 粒度 = **精确 workspace 相对路径**；glob 元字符在解析期 fail fast

**选择**：`allowed_write_paths` 的每一项是 workspace 相对路径的**字面值**（如 `.env` / `config/.env`）。含 glob 元字符（`*` `?` `[` `]`）、`..` 段、或以 `/` 结尾（目录形式）的条目 SHALL 在配置解析期被判非法（`ConfigError`，fail fast）。绝对路径同样判非法。

**理由**：
- **业界同名解法**：codex 明确「glob 只能用于 deny，不能用于授权」（`codex/codex-rs/sandboxing/src/policy_transforms.rs:30-35`），授权走精确路径 + 符号链接保留式规范化（同文件 `:39-41`）。
- **直接消灭 issue 的 `**/*` 硬约束**：一个「匹配一切」的模式会把 `.git/config` 一起打开（issue 实测）。把 glob 从授权面整体移走，比给 `**/*` 加黑名单特判更彻底——后者还要处理 `./**/*`、`.//**/*`、`x/../**/*` 等等价拼写。fail fast 让这类拼写**根本进不了运行时**。
- **防御性收益**：`is_denied` 的现有实现对每个候选做 `fnmatch`（`agent/workspace_policy.py:331-337`），allow 若也走 glob，就等于在这条已经出过越界 bug（本仓 #247、CVE-2025-54794 的同类）的路径上再加一层 `fnmatch` 语义。

**代价（如实写）**：用户想给一个目录下 10 个 env 文件授权时，必须写 10 条。这是**接受**的代价——本 change 的存在理由是「精确豁免」，不是「目录级授信」。若日后确实需要，`dir/**` 语法可以作为独立扩展（届时它需要单独解决「`**` 的段边界」问题，正是 #247 那一类）。

**否决的备选**：(a) 允许任意 glob + 只特判 `**/*`——等价拼写漏不完，且 `fnmatch` 的段边界语义与 `is_denied` 的段级判定不一致；(b) 目录前缀（`config/` 授 `config/` 下一切）——`config/` 会把 `config/.env.production` 一起打开，与 Q3 的推荐值（变体不跟随）自相矛盾。

### Decision 4: 配置住 `asterwynd.yaml` 的 `tools.allowed_write_paths`，与 `tools.command_denylist` 同构

**选择**：`ToolsConfig` 新增 `allowed_write_paths: tuple[str, ...] = ()`（`agent/config.py:151-161` 旁），`_parse_tools_config` 走既有 `_parse_string_list` 并在其后加语义校验（glob/绝对路径/`..`/尾 `/` ⇒ `ConfigError`）（`:875-897`）；`asterwynd.example.yaml` 在 `command_denylist: []`（`:35`）旁补一行示例。三个生产构造点把 `config.tools.allowed_write_paths` 传给 `WorkspacePolicy`。

**理由**：业界静态白名单住在配置文件里是主流（opencode 的 `permissions` 有序数组 `opencode/packages/core/src/config.ts:60-62`；codex 的额外权限来自运行参数/用户配置构成的 `AdditionalPermissionProfile`，`codex/codex-rs/sandboxing/src/policy_transforms.rs:18-77`）。本仓**已经有**这条通道（`tools.command_denylist` / `tools.ignore_patterns`），复用它 = 零新增机制、零新增发现逻辑、零新增环境变量面。是否额外支持用户级 scope 见 Q4。

### Decision 5: 只放行**写**，读保持拒绝（文件工具层）；并如实写明 Bash 读侧本来就是通的

**选择**：allow 只接进 `assert_write_allowed`（`agent/workspace_policy.py:356-360`）与 Bash 层的**写目标**判定；`assert_read_allowed`（`:350-354`）SHALL NOT 被 allow 影响。

**理由**：
- 用户要的是「让 agent 能**配置** env」，不是「让 agent 能**看** env」。读放行会把明文凭据带进上下文、trace 与 `messages.jsonl`。
- 与业界 read/write 不对称的做法一致：codex 的 glob 权限**只能用于 deny-read**（`policy_transforms.rs:30-35`），即读侧才是允许用宽模式去**收紧**的那一侧。

**必须写明的边界（不得失真）**：
- `Edit` 工具**不依赖** `assert_read_allowed`——它在 `assert_write_allowed` 之后自己 `read_text()`（`agent/tools/builtin/edit.py:55,67`）。所以 `Edit .env` 在「只放行写」下**可用**。
- `Write` 工具**拒绝覆盖已存在的文件**（`agent/tools/builtin/write.py:52-56` 的「file already exists… Use Edit」）⇒ 受 allow 覆盖的路径的典型用法是「`Write` 建、`Edit` 改」。
- **agent 读不回自己写的内容**（`Read .env` 仍拒）⇒ `Edit` 的 `old_string` 只能靠 agent 自己记住写过的内容，或整文件 `Write`（但那会被「已存在」挡）。这是「只放行写」的**真实可用性代价**，必须在 Q5 的例子说清。
- **Bash 层读侧不通**（`cat .env` 全放行，实测）**不由本 change 负责**，见 Q6；任何「凭据读不到」的结论都不得写成无限定语。

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

**选择**：阶段 B 报告的 findings 必须**按成因分两类**，且不得混算：

| 成因 | 典型项 | 处置 |
|---|---|---|
| **已知工具不兼容** | witnessloop 的 `_SOURCE_RE` 不认 `- **来源**: x`（加粗写法）⇒ 建了 witnessloop 形态 grill manifest 后 grill 正文判据**全红**（本仓 62 份归档 grill 记录通篇加粗）。上游 issue #20 已立、已拍板「等上游修、本仓零改动」（U7/N.7） | 记为**结构性红**，附「不属于阶段 B 的配置错误」的显式说明 |
| **配置问题** | policy 字段写错、glob 放宽错、执行点命令错 | 记为**可修红**，当次修掉 |

**理由**：`witnessloop-adoption` 的 R11 已经实测证伪了「阶段 B 能拿到 grill 的绿」这个假设（补齐 manifest 也拿不到绿）。若报告不分类，读者会把结构性红读成「接入没配好」，从而误判「值不值得真打开」。

## Open Questions

> **停轮项：以下六条在用户逐条答复之前不得写实现代码或测试代码**（AGENTS.md 的 grill-confirmation-gate）。每条给出**本 change 真实场景的具体例子**（含参数、输入输出、前后对比），便于快速拍板。推荐值只是 agent 的建议，**不等于用户确认**。

- **Q1**: `allowed_write_paths` 能覆盖哪些 deny 来源？（推荐：**(b)** 覆盖文件级 deny，不覆盖结构性目录 deny 与 workspace 边界。）
  - 背景：`is_denied` 的拒绝来自三处不同来源——① 段级敏感名判定 `is_sensitive_dot_name`（`.env` 族、`id_rsa`、`.git` 段）；② `DEFAULT_DENIED_PATTERNS` 的 glob 表（`*.pem` / `*.key` / `node_modules/**` / `.venv/**` / `benchmarks/runs/**` …，`agent/workspace_policy.py:9-43`）；③ workspace 边界（`assert_within_workspace`）。
  - 具体例子：本仓部署脚本读 `config/.env`，同时 CI 用 `deploy.pem` 签名。用户写 `tools.allowed_write_paths: ['config/.env', 'deploy.pem', '.git/config']`：
    - **(a) 只覆盖 `.env` 族（敏感点文件名）**：`Write config/.env` ⇒ ALLOW；`Write deploy.pem` ⇒ **仍 DENY**（`*.pem` 走的是 glob 表）；`Write .git/config` ⇒ 仍 DENY。用户拿不到 `.pem` 的豁免。
    - **(b) 覆盖文件级 deny，不覆盖结构性目录 deny**：`Write config/.env` ⇒ ALLOW；`Write deploy.pem` ⇒ ALLOW；`Write .git/config` ⇒ **仍 DENY**（`.git/**` 属结构性目录）；`Write .venv/x.py` ⇒ 仍 DENY。
    - **(c) 覆盖全部（含 `.git/**`）**：`Write .git/config` ⇒ ALLOW。注意 `.git/hooks/*` 是**代码执行点**——一旦 `.git/**` 可授，等价于「给 agent 一个 commit 钩子的写入权」，而钩子会在维护者下次 commit 时执行。
  - 推荐 (b) 的理由：`.env` / `.pem` 是「用户自己的凭据文件」，`.git/**` / `.venv/**` / `node_modules/**` / `__pycache__/**` / `benchmarks/runs/**` 是「仓库与工具管理的目录」，开后者不解决任何真实需求，只扩大爆炸半径。**不覆盖 workspace 边界**三种取值下都成立、不可协商（那是本仓的核心不变量）。
- **Q2**: 粒度用**精确路径**、目录前缀，还是 glob？（推荐：**精确路径**，glob 元字符在解析期 fail fast。）
  - 具体例子：用户的项目有 `.env`、`.env.testing`、`config/.env`、`config/.env.testing` 四个文件要授权。
    - **精确路径**：写 `['.env', '.env.testing', 'config/.env', 'config/.env.testing']`，四条都生效；写 `['config/']` 会在 `asterwynd.yaml` 加载时直接 `ConfigError`（尾 `/` 是目录形式，非法）。**代价**：文件多时要列全。
    - **目录前缀**：写 `['config/']` ⇒ `config/.env`、`config/.env.testing` 都生效，但 `config/notes.md`、`config/.env.production` 也一起生效——与 Q3 的推荐值（变体不跟随）自相矛盾。
    - **glob**：写 `['config/*.env*']` ⇒ 灵活，但写 `['**/*']` 能开全仓（issue #272 实测会连 `.git/config` 一起打开）。要堵 `**/*` 就得堵等价拼写（`./**/*`、`.//**/*`、`x/../**/*`、`{a,b}/**`），漏一个就是洞。
  - 推荐精确路径的理由：codex 明确「glob 只能用于 deny、不能用于授权」，授权走精确路径 + 规范化（`codex/codex-rs/sandboxing/src/policy_transforms.rs:30-41`）；把 glob 整体移出授权面比给 `**/*` 加黑名单特判更彻底。**代价如实说**：目录级授权不支持，需要时逐文件列。
- **Q3**: 允许 `.env` 之后，`.env.local` / `.env.production` 是否跟着允许？（推荐：**不跟随**，严格精确匹配。）
  - 具体例子：`tools.allowed_write_paths: ['.env']`。
    - **不跟随**：`Write .env` ⇒ ALLOW；`Write .env.local` ⇒ **仍 DENY**（错误文案 `Write denied by workspace policy`）；`cp .env.example .env.local` ⇒ 被 Bash 层拦（`mv_cp_dest`）。要用 `.env.production` 就再写一条。
    - **跟随（家族豁免）**：`Write .env.production` ⇒ ALLOW。生产凭据位一并打开。
  - 推荐不跟随的理由：`#254` 刚把凭据变体收进 deny（`is_env_sensitive_name`：除模板词外 `.env.<suffix>` 全是凭据，`agent/workspace_policy.py:91-102`），业界同形（kimi-code 的 `ENV_PREFIX = '.env.'` 除 `ENV_EXEMPTIONS` 三个模板外一律判敏感，`kimi-code/packages/agent-core-v2/src/tool/path-access.ts:28-29,58-59`）⇒ 没有任何一家做「开 `.env` 级联开 `.env.production`」；豁免粒度与 deny 粒度对齐，用户「要开哪个写哪个」。
- **Q4**: 配置住在哪一级？（推荐：**只做项目级** `asterwynd.yaml` 的 `tools.allowed_write_paths`。）
  - 具体例子：团队 A 在仓库根 `asterwynd.yaml` 写 `tools.allowed_write_paths: ['.env']`。
    - **只项目级**：在该仓库**任意子目录**启动 CLI 都生效（配置发现向上找到 repo root 停，`openspec/specs/configuration/spec.md` 的「配置文件发现受工作区边界约束」）；换到另一个工作区启动 ⇒ 不生效（那个工作区没有这条配置）。
    - **再加用户级**（如 `~/.asterwynd/config.yaml`）：同一份仓库代码，在维护者本机 `.env` 可写、在 CI runner 上不可写——**同一个 PR 在两台机器上门禁不同**，而 CI 才是真锚。
    - **再加环境变量**（`ASTERWYND_ALLOWED_WRITE_PATHS`）：等价于「白名单不进代码评审」，与 #254 已拍板的「扩权必须可见」相悖。
  - 推荐项目级 + 不做用户级的理由：与既有 `tools.command_denylist` / `tools.ignore_patterns` 完全同构（零新增发现机制、零新增环境变量面），且白名单随仓库进 git ⇒ 每次改动都过 review。
- **Q5**: 只放行「写」而保留「读」的拒绝，还是读写一起放行？（推荐：**只放行写**；同时接受由此产生的可用性边界。）
  - 具体例子：`tools.allowed_write_paths: ['.env']`，agent 的任务是「给我加一个 `LOG_LEVEL=debug`，然后用 `pytest` 验证」。
    - **只放行写**：agent `Read .env` ⇒ **DENY**（`Read denied by workspace policy`）⇒ 它看不到现有内容。但 `Write .env`（文件不存在时）⇒ ALLOW；文件已存在时 `Write` 会回 `Error: file already exists: .env. Use Edit for modifications instead of overwriting existing files.`（`agent/tools/builtin/write.py:52-56`）；`Edit .env` ⇒ **ALLOW**（`EditTool` 在 `assert_write_allowed` 之后**自己** `read_text()`，不走 `assert_read_allowed`，`agent/tools/builtin/edit.py:55,67`），但 agent 必须**凭记忆**给出精确的 `old_string`，猜错就 `Error: old_string not found in .env`。⇒ 结果是「能写、能改，但改的时候像盲改」。
    - **读写都放**：agent `Read .env` ⇒ ALLOW，拿到 `API_KEY=sk-live-…` 明文 ⇒ 该值进入上下文、trace 与 `messages.jsonl`（本仓有 `messages` spill/ref 与 trace 持久化）；`Edit` 照旧可用，但风险从「盲改」变成「凭据落盘」。
  - 推荐只放行写的理由：用户要的是「让 agent 能**配置** env」而不是「让 agent 能**看** env」；读放行会把明文凭据带进持久化产物。**同时请判**：为缓解「盲改」，是否接受 README/配置注释里让用户「用 `Write` 整文件（先删旧文件）」这类笨办法，还是干脆在 Q5 选「读写都放」。**不接受**的是不把这条边界写清楚——用户以为能改、实际改不动。
- **Q6**: 要不要在本 change 内顺手把 **Bash 层的 `.env` 读侧**一并堵上？（推荐：**不堵**，记为债务另立。）
  - 背景（本分支实测，不是推理）：**今天的 Bash 层读 `.env` 是通的**——`cat .env`、`grep API_KEY .env`、`head -5 .env`、`source .env`、`. .env` 在 `WorkspacePolicy.assert_command_allowed` 与 `CommandGuard.check` **两层都是 ALLOW**；只有 `mv`/`cp` 的**源位置**被查（`agent/tools/command_guard.py:872-878`），`python -c 'open(".env").read()'` 是被 `DEFAULT_DENYLIST` 的 `python3?\s+-c\b` 拦下的（另一条理由）。⇒ 「Q5 选只放行写」**并不能**阻止 agent 通过 Bash 读到凭据；它只挡住 `Read` / `Grep` / `ListFiles` 这条工具路径。
  - 具体例子：同一 workspace，Q5 选「只放行写」。
    - **不堵（推荐）**：`Write .env` ALLOW；`Read .env` DENY；**`cat .env` ALLOW**。⇒ 「只放行写」的保护面必须如实表述为「文件工具层」，不得写成无限定语。
    - **顺手堵**：给 `CommandGuard` 新增读侧目标判定，`cat .env` / `grep API_KEY .env` / `head .env` 变 DENY。**代价**：读侧判定要新增一批「哪些命令的参数是读目标」的语义（`cat` / `head` / `tail` / `less` / `grep` / `source` / `.` / `awk`…），而 `#254` 的护栏**刻意只对本 change 关心的写命令做目标判定**；扩读侧会立刻带来误报面（`git log -- .env`、`grep -rn "cat .env" docs/` 这类**文本里提到路径**的命令），而误报在无 UI 环境下等于硬拒。
  - 推荐不堵的理由：① 它是**新增一个能力**（读侧判定），不是本 change 需求的必要部分，塞进来会让「写白名单」的 diff 无法独立评估（与 `witnessloop-adoption` Decision 6 对 `handoff.json` 的同款判断）；② 它会改变 `benchmarks/attacks/attacks.json` 之外的既有行为面，风险与收益不对称。处置：记入 `docs/known-debt.md`（受保护路径，配 `protected_artifact_explained` 事件）或另立 issue。

## Pre-Implementation Review

- Questions resolved（本 change 内已定）：
  - 「接线成本极小、照抄 `command_denylist` 约 6 行」——**部分成立**：配置字段与解析确实是同构照抄（Decision 4），但**判定面是新增的**（Decision 1，不能靠覆写 `denied_patterns`），且 Bash 层还多一个传参面（Decision 2，`agent/tools/builtin/bash.py:87` 只拿得到 `workspace_root`）。⇒ 工作量从「6 行」修正为「两个判定器 + 一个传参面 + 三层测试」。
  - 阶段 B 观测报告落点 —— **已定**（Decision 6：change 根目录，避开 `reviews/` 的孤儿规则）。这是本 change 必须自己拍的，不能留给阶段 B 现场决定。
  - 阶段 B 的 `reviews/` 一致状态 —— **已定**（Decision 7：全绑 + 清中间轮）。
  - 已知不兼容的归因口径 —— **已定**（Decision 8：先分类再下结论）。
- Questions resolved（**由代码给出带证据的答案，移出停轮队列**）：
  - 「生产构造点几处、在哪」——**代码判定**：三处，`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349`（全仓 grep + 排除 `policy or WorkspacePolicy()` 兜底与 factory 默认参数）。issue 写的 `web/session.py:1566` 已漂移。
  - 「`denied_patterns` 能不能直接当 allow 的载体」——**代码判定**：不能（探针实测 `denied_patterns=()` 下 `.env` 仍 `is_denied=True`）。
  - 「Bash 层读 `.env` 是否已被拦」——**代码判定**：没有，`cat .env` / `grep API_KEY .env` / `source .env` 两层全 ALLOW（探针实测）。这条把 Q6 从「要不要顺手堵」变成「要不要**新增**一个读侧能力」。
- Options considered:
  - **A. 只接文件工具层**（不动 `CommandGuard`）：**否决**——`echo API_KEY=x >> .env` / `tee .env` / `dd of=.env` 仍被拦，功能半残，且用户无法预期「为什么 Write 能写 Bash 不能写」。
  - **B. 只接 Bash 层**（不动 `WorkspacePolicy`）：**否决**——`Write` / `Edit` 仍拒，主用法（agent 生成配置文件）走不通。
  - **C. 两层各实现一份 allow 匹配**：**否决**——重演 D12 的漂移，且这次是「宽松方 vs 严格方」不一致，更难发现。
  - **D. 复用 `denied_patterns` 做减法**：**否决**（Decision 1，实测无效）。
  - **E. 引入 glob / 目录前缀授权**：**否决**（Decision 3，与业界做法相反，且直接撞上 issue 的 `**/*` 实测坑）。
  - **F. 本 change（Decision 1–5）**：新增独立判定面 + 两层同源 + 精确路径 + 只写 + 配置同构。
- Rejected alternatives：A–E 的理由如上。另否决「在本 change 内顺手收口 Bash 读侧」（Q6 的备选 (b)，会把范围扩到读判定与一批读命令的误报面）。
- Final confirmations：
  - **grilling 与停轮确认尚未进行**——本文件是立项文档；`## Open Questions` 六条**必须停下抛给用户**，收到答复并记入 `reviews/grill-design.md` 的 `## User Confirmation` 之前**不写实现代码或测试代码**（AGENTS.md 的 grill-confirmation-gate）。
  - 设计阶段审阅闭环（`reviews/grill-adversarial.md`）同样在实现前必须收敛（grill-flow-hardening / issue #298）。
- Remaining risks：见下节 R1–R9。

## Risks / Trade-offs

- **[R1] 「同源」被实现成「同名两份」**：两层都叫 `allowed_write_paths` 但各写一份匹配逻辑 ⇒ 文件工具放行而 Bash 拦（或反向），且哪边生效取决于用哪个工具。**Mitigation**：Decision 2 把判定抽成共享函数并由 `Design`/测试双重锁定——新增一条**跨层一致性回归测试**（同一路径在 `assert_write_allowed` 与 `CommandGuard.check` 上得到同向结论）。
- **[R2] 否定用例被漏掉 ⇒ allow 变成后门**：最常见的实现滑手是「命中 allow 就 return allow」写在 workspace 边界检查**之前**，那样 allow 条目一旦写成绝对路径就能写 workspace 外。**Mitigation**：① Decision 3 在解析期拒绝绝对路径与 `..`；② 否定用例三条（未列入的 `.env`、`.env.local` 变体、`../` 逃逸）写成硬性任务；③ 规格里把「`assert_within_workspace` 先于任何 allow 判定」写成 Requirement。
- **[R3] 配置错写的暴露延迟**：与本仓 `--policy` 同类的坑——配置解析若对非法值宽容，错误只会在运行时以「莫名还是被拒」的形式暴露。**Mitigation**：Decision 3/4 的语义校验在**解析期 fail fast**（`ConfigError`），并在 `asterwynd.example.yaml` 给出正例。
- **[R4] 「只放行写」的可用性被低估**：agent 写不了 `.env` 又想改，只能整文件 `Write`（被「已存在」挡）或 `Edit`（要 `old_string`，但它读不到内容）。**Mitigation**：Q5 的例子把这个链路完整走一遍给用户看，由用户拍板；不接受「用户以为能改其实改不动」的默认。
- **[R5] 权限面扩大的既有语义问题**：`.env` 写入本身可能是**代码执行向量**（`source .env` 在 shell 里执行内容；某些工具链会读 env）。本 change 只是把「用户显式授权的文件」从不可写变为可写，判定者仍是人；但**必须写明这不是安全边界**（护栏不是边界，`ProcessBackend` 才是）。**Mitigation**：写进规格与 Impact Analysis 的「行为变更」段，不让它被读成「安全能力」。
- **[R6] 阶段 B 激活 witnessloop 孤儿规则 ⇒ `reviews/` 从 2 条红变 14/16 条**（`witnessloop-adoption` 实测）。**Mitigation**：Decision 7 的「全绑 + 清中间轮」，并在报告里如实记这条成本（它正是 N.6 的迁移成本样本）。
- **[R7] 阶段 B 的 grill 正文判据结构性判红**（`:来源` 谓词不认加粗，上游 #20 未修）。**Mitigation**：Decision 8 的成因分类；本 change **不放宽判据、不为此改本仓 grill 记录格式**（U7 已拍板）。
- **[R8] 本 change 自己会成为 witnessloop 的「已知红」**：本 change 的 diff 触达 `agent/**` / `web/**` ⇒ `code_hits` 非空 ⇒ `building` 与 `grill-adversarial` 两条 stage 判定**会真的触发**（这既是阶段 B 想要的，也意味着本 change 的红数比 `witnessloop-adoption` 多）。**Mitigation**：阶段 B 报告如实列出并分类；不放宽判据。
- **[R9] 阶段 B 的报告纪律**：观测报告若在**最后一刻**才写，会与 manifest 的 stale 顺序约束打架。**Mitigation**：报告作为**内容提交**（非证据路径之外的内容），manifest 在其后重建（Decision 7）。

## Testing Strategy

测试分层按本仓既有约定（`docs/testing-guide.md`），**测试先行**：

1. **单元：`WorkspacePolicy` 的 allow 判定**（`tests/agent/test_workspace_policy.py`）
   - 正例：`allowed_write_paths=('.env',)` ⇒ `.env` 的 `assert_write_allowed` 通过；`config/.env` 同理。
   - **否定例（硬要求）**：① 同一 policy 下 `.env.local` / `.env.production` / `.env.example` 的行为与 allow 前**一致**（前两者仍拒、模板仍放行）；② 未列入的 `.env`（`allowed_write_paths=('.env',)` 下的 `other/.env`）仍拒；③ `../outside/.env` 仍因**边界**被拒（allow 不得先于边界生效）；④ 结构性目录 deny（`.git/config`）即便被显式列入仍拒（取决于 Q1 裁定，测试按裁定值写）。
   - 默认值：`allowed_write_paths=()` 时全部断言与今天逐条一致（回归线）。
2. **单元：`CommandGuard` 的同源生效**（`tests/agent/tools/test_command_guard.py`）
   - 正例：带 allowlist 的 guard 下 `cp x .env` / `echo X >> .env` / `tee .env` / `dd of=.env` 由 DENY 变 ALLOW。
   - **否定例**：不带 allowlist 时这些命令仍 DENY（与今天的断言逐条一致）；带 allowlist 时 `cp x .env.local` 仍 DENY；`cp x /etc/passwd` 仍 DENY（结构性 deny 不被 allow 影响）。
3. **跨层一致性（R1 的锁定）**：同一份 allowlist 下，对同一组路径断言 `assert_write_allowed` 与 `CommandGuard` 的写目标判定**结论同向**。
4. **配置层**（`tests/agent/test_config.py`）
   - `tools.allowed_write_paths` 缺失 ⇒ `()`（默认空，deny 默认不变）。
   - 正例解析：YAML 里 `['.env', 'config/.env']` ⇒ 元组。
   - **fail fast**：含 `*` / 绝对路径 / `..` / 尾 `/` 的条目 ⇒ `ConfigError`（逐条一条用例）。
5. **Bash 攻击集不回归**：`benchmarks/attacks/attacks.json` 的 `deny` 用例在**配置了 allowlist** 的 guard 下仍全部被拦（allow 只放宽被明确列入的路径，攻击集里的 `/etc/`、`~/.ssh/` 等不受影响）。
6. **benchmark smoke**：本 change 触及 `agent/workspace_policy.py` 与 `agent/tools/`（命中 checker 的 benchmark smoke 触发面）⇒ 跑一条 benchmark smoke 确认工具策略接线未破。
7. **不做的事**：不为 Q6（Bash 读侧）写测试——它不在本 change 范围。

**阶段 B 的「测试」**（本 change 的流程验证腿）：见 `tasks.md` 的 B 节。它不是 Python 测试，而是「在并存期跑通完整链路并如实记录分叉」。

## Impact Analysis

- **新增**：`openspec/changes/guard-write-allowlist/stage-b-observation.md`（阶段 B 观测报告，change 根目录，见 Decision 6）；witnessloop 形态 manifest `reviews/grill.manifest.json` / `reviews/grill-adversarial.manifest.json` / `reviews/building.manifest.json`（阶段 B 产出，见 Decision 7）。
- **修改（生产）**：`agent/workspace_policy.py`（新增 `allowed_write_paths` 参数 + 共享判定谓词）、`agent/tools/command_guard.py`（消费同一份 allowlist + 共享谓词）、`agent/tools/builtin/bash.py`（传参面，`:87`）、`agent/config.py`（`ToolsConfig` 字段 `:151-161` + `_parse_tools_config` `:875-897` + fail fast）、`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349`、`asterwynd.example.yaml:35`。
- **修改（测试）**：`tests/agent/test_workspace_policy.py`、`tests/agent/tools/test_command_guard.py`、`tests/agent/test_config.py`。
- **修改（文档）**：`docs/development-guide.md`（配置项说明 + 阶段 B 的跑法）；`docs/openspec-change-backlog.md`（登记/清理，受保护路径配 `backlog_updated` 事件）；`openspec/specs/workspace-safety/spec.md` 与 `openspec/specs/configuration/spec.md`（同步 delta，配 `current_spec_synced` 事件）。
- **明确不改**：`AGENTS.md` 流程段、`.github/workflows/ci.yml`、`.witnessloop/**`、`scripts/**`、branch protection、`agent/approval.py`、`CommandVerdict` 的三态语义。
- **回退**：删掉配置项即回到今天的行为（默认空列表 ⇒ 零行为变化）；代码侧回退是一次普通 revert，无数据迁移、无持久化状态。
