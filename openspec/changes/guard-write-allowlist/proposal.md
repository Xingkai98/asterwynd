# Proposal: 护栏写白名单（被 deny 路径的显式可写豁免）

关联跟踪 issue：[#272](https://github.com/Xingkai98/asterwynd/issues/272)（【feature】护栏写白名单：允许配置 `.env` 等被 deny 路径的显式可写豁免（B1））。来源是 change `bash-command-guard-redesign`（issue [#254](https://github.com/Xingkai98/asterwynd/issues/254)）Q3 的补测结论。

## Change Type

- primary: feature
- secondary: []

## Why

今天没有任何配置通道能让用户「授权 agent 写某个 `.env`」。本分支在 `fd6d581` 上实测（探针脚本，见 `design.md` 的「实现要点复核」）：

| 动作 | 文件工具层（`WorkspacePolicy`） | Bash 层（`CommandGuard`） |
|---|---|---|
| `Write .env` / `Edit .env` | ❌ DENY | — |
| `Read .env` / `Grep .env` | ❌ DENY | — |
| `cp .env.example .env` | ❌ DENY（`mv_cp_dest`） | ❌ DENY |
| `echo API_KEY=x >> .env` | ✅ ALLOW | ❌ DENY（`protected_redirect`） |
| `touch .env` | ❌ DENY | ✅ ALLOW（空动作，非洞） |
| `cat .env` / `grep API_KEY .env` | ✅ ALLOW | ✅ ALLOW（**读侧今天本来就通**） |

⇒ 用户唯一的出路是手改 `agent/workspace_policy.py` 的 `DEFAULT_DENIED_PATTERNS`，那等于改源码。

需求是 issue 里的原话：`tools.allowed_write_paths: ['.env', '.env.testing']` 之类的**显式可写豁免**——「**deny 默认 + allow 精确覆盖**」。

> **示例为什么用两个裸名而不是 `['.env', 'config/.env']`**：本分支实测，**嵌套**路径（`config/.env`）的 Bash `cp`/`mv` 被 `_EXTRA_DENYLIST` 的整句正则在命令 IR 判定**之前**拦下（`last_reason=denylist`，`agent/tools/command_guard.py:609` / 扫描循环 `:737-740`），与 allow 的挂钩点结构上不相交 ⇒ 那个例子只能兑现一半。本 change 的**真实兑现面**见 `design.md` Decision 9 与规格的「Bash 层豁免覆盖面差异必须被记录」Requirement；是否扩范围见 `design.md` 的 **Q7**（停轮项）。

## 需求

1. **新增配置项 `tools.allowed_write_paths`，默认空列表。** 默认值 SHALL 为空 ⇒ 不配置时**现有行为逐字节不变**（deny 默认不变）。形态与既有的 `tools.command_denylist` / `tools.ignore_patterns` 同构（`agent/config.py:151-153` 的字段 + `:875-889` 的解析 + `asterwynd.example.yaml:35` 的示例）。
2. **allow 必须同时喂到两层判定器，不能只喂一层。** 本仓的路径判定有**两个互不相同的实现**：文件工具层是 `WorkspacePolicy.is_denied`（`agent/workspace_policy.py:316-338`），Bash 层是 `CommandGuard` 的 `_dest_is_sensitive` / `_has_protected_redirect` / `_check_target`（`agent/tools/command_guard.py:565-574`、`:976-993`、`:930-938`）。只接线前者，`echo API_KEY=x >> .env` 仍会被后者拦下（上表实测）——功能等于没做。**两层 SHALL 消费同一份数据与同一个判定谓词**（`#254` 的 D12 已经把「什么算敏感点文件名」收敛成共享谓词 `is_sensitive_dot_name`，本 change 沿用这条收敛路径）。
   **但「同源」的边界必须写准**：共享的是**谓词函数**，不是**调用点**。`is_denied` 是 `assert_read_allowed` 与 `assert_write_allowed` 的**同一实现**，`agent/code_intelligence/repo_map.py:173` 还直接调它做 tree-sitter 跳过 ⇒ 把 allow 写进 `is_denied` 会连**读侧与符号索引面**一起打开。⇒ allow **只在写路径求值**（见 `design.md` Decision 2 / Decision 5 与 Q8）。
3. **三条硬约束**（issue #272 已实测，本 change 独立复核后采纳）：
   - allow **只能重开被 deny 命中的路径**，SHALL NOT 扩展到 workspace 外（`assert_within_workspace` 的边界先于任何 allow 判定，不可被 allow 豁免）；
   - allow SHALL NOT 用「匹配一切」的模式（如 `**/*`）——issue 实测那会连 `.git/config` 一起打开；
   - allow 只放宽**路径类 deny**，SHALL NOT 放宽「结构性目录 deny」与命令 denylist。
4. **否定用例是验收的一部分**：未列入 `allowed_write_paths` 的 `.env` 文件 SHALL 仍然被拒绝。这是本 change 最容易被实现悄悄放松的一条，必须由回归测试钉死。
5. **本 change 同时是归档 change `2026-10-13-witnessloop-adoption` 的「阶段 B」载体**——用一个真实小需求在新流程上跑一遍（见 tasks 的 B 节），产出分叉清单与「值不值得真打开」的判断依据，并明确区分「配置问题」与「已知工具不兼容」。

## 非目标

- **不允许模型自己配白名单**。用户已在 #254 拍板否决：判定者（policy）与被判定者（agent）是同一主体时权限系统在定义上不存在；且护栏拿到的是命令文本不是用户意图，一次提示注入即永久扩权。本 change 的 allow 来源**只有 `asterwynd.yaml`**（人写的、仓外可 review 的文件），SHALL NOT 引入任何「模型提议 → 自动写配置」的通道。
- **不引入「持久化的 ask」**（模型提议 → 用户审批 → 落成规则）。那是 kimi-code `session-approval-history` 那条路的形态，可另行讨论，不在本 change。
- **不改命令 denylist 的语义**：`DEFAULT_DENYLIST`、`_EXTRA_DENYLIST`、`_match_allowlist` 一行不改。**这条有一个必须写明的后果**：命令护栏第 1 步的整句 denylist 正则（`agent/tools/command_guard.py:609`，在任何 IR 判定之前执行）会拦下**嵌套**路径的 `cp`/`mv` ⇒ 嵌套路径的 Bash `cp`/`mv` **不在豁免范围内**（`design.md` Decision 9）。是否为此扩范围见 Q7（停轮项）。
- **不改 read 侧行为**（是否放行读由 `design.md` 的 Q5 裁定；本 change 的推荐值是**不放行**）。
- **不合并 Bash 读侧缺口**（`cat .env` 今天两层全放行，实测）——见 `design.md` 的 Q6，推荐记为债务另立。
- **不为通过阶段 B 的 witnessloop 门禁而放宽任何判据**（继承 `witnessloop-adoption` Decision 7 的姿态）。
- **不改 `docs/openspec-change-backlog.md` 之外的流程文档**（`AGENTS.md` 的流程段不动）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `workspace-safety`：读写判定在「deny 默认」之上新增一层**显式可写豁免**（`allowed_write_paths`），并把它同时接入 `WorkspacePolicy` 与 `CommandGuard` 两个判定器；明确 allow 与 deny 的优先级、粒度、与 workspace 边界的关系，并钉死否定用例。
- `configuration`：`tools.allowed_write_paths` 成为 `asterwynd.yaml` 的受支持字段，非法值 SHALL fail fast。

## Impact Analysis

- **影响代码（生产）**：
  - `agent/workspace_policy.py`：`WorkspacePolicy.__init__` 新增 `allowed_write_paths` 参数与判定谓词（`__init__` 现状见 `:236-249`，已接受 `denied_patterns`；`is_denied` 现状见 `:316-338`）。
  - `agent/tools/command_guard.py`：`CommandGuard` 新增同一份 allowlist 的消费面，`_check_target` / `_has_protected_redirect` / `_check_dynamic_target` / `_check_mv_cp` / `_check_tee` / `_check_dd` 的路径判定收敛到共享谓词。
  - `agent/tools/builtin/bash.py`：`BashTool.__init__` 构造 `CommandGuard` 时把 policy 的 allowlist 一并传入（现状 `:87` 只传 `workspace_root`）。
  - `agent/config.py`：`ToolsConfig` 新增字段（`:151-161`）+ `_parse_tools_config` 解析与 fail fast（`:875-897`）。
  - `agent/main.py:251-254`、`web/session.py:1728-1731`、`benchmarks/agent_runner.py:349-352`：**三个入口可配置的**生产构造点把配置传给 `WorkspacePolicy`。**另有一处不可配置的真实构造点** `agent/tools/builtin/subagents.py:2005`（`dry_run_workflow` 的临时沙箱，`:1979`），它**不接线是正确的**（dry-run 沙箱不该带用户的豁免），但必须列出来——它不是 `policy or WorkspacePolicy()` 兜底。issue #272 写的 `web/session.py:1566` 在 `fd6d581` 上已漂移到 `:1728`。
  - **受影响但属正确行为**：`agent/browser/policy.py:121` 也调 `assert_write_allowed` ⇒ 浏览器产物落盘会继承豁免（同源效果，非遗漏）。
  - **明确不受影响**：`WorkspacePolicy.is_denied`（`:316-338`）的语义、`assert_read_allowed`（`:350-354`）、`agent/code_intelligence/repo_map.py:81,96,173` 的 tree-sitter/RepoMap 跳过判定、以及全部读工具的读路径。
  - `asterwynd.example.yaml`：在 `command_denylist` 旁补示例（`:35`）。
- **影响测试**：`tests/agent/test_workspace_policy.py`（新增 allow/deny 优先级与否定用例）、`tests/agent/tools/test_command_guard.py`（Bash 层同源生效 + 未列入仍拒）、`tests/agent/test_config.py`（解析、默认空、fail fast）。**回归测试是本 change 的硬要求**（AGENTS.md「每个 bug fix 必须新增回归测试」的同类要求：新能力面必须有正例与**否定**用例两层）。
- **影响文档**：`docs/openspec-change-backlog.md`（登记本 change，受保护路径，配 `backlog_updated` 解释事件）；`docs/development-guide.md`（配置项说明；若 Q6 裁定记为债务，同时进 `docs/known-debt.md`）。
- **行为变更（用户可见）**：配置了 `tools.allowed_write_paths` 后，被列入的路径从「被拒」变为「可写」——**但兑现面依赖路径形态与写方式**（细则见 `design.md` Decision 9 的表：裸名两层通吃；嵌套路径的文件工具写与非 `cp`/`mv` 的 Bash 写生效，`cp`/`mv` 不生效）。**未配置时零变化**。这不是安全边界（护栏不是边界，`ProcessBackend` 才是——见 `agent/tools/command_guard.py:1-23` 的自陈），而是「护栏的可配置豁免」。
- **不影响**：`CommandVerdict` 三态语义、`agent/approval.py`、AgentLoop 主循环、trace 事件 schema、`.github/workflows/ci.yml`、branch protection。
- **阶段 B 的额外影响面**（本 change 独有的义务）：本 change 的 PR 要在**并存期**跑通完整链路（本地 `guard` → 写码 → `/review-loop` 产 asterwynd 形态证据 → **额外** `uv run witnessloop manifest build` 产 witnessloop 形态 manifest → `witnessloop check` 核证据 → CI 的 `gate / check` 真的跑起来）。这会**激活 witnessloop 的孤儿规则**——`reviews/**/*.md` 的每一份都必须被某份 manifest 的 `report_path` 绑定（witnessloop `src/witnessloop/contract.py:185-206`）⇒ 中间轮产物（如 `building-review-r1.md`）必须清理，阶段 B 的观测报告必须落在 `reviews/` **之外**（见 `design.md` Decision 6）。
- **不新增外部依赖**。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 本 change 命中判据表两条 —— ①「**走 grill 的非平凡 change**」（它有 6 条待用户裁定的政策取舍：allow 覆盖面 / 粒度 / `.env` 变体是否跟随 / 配置级别 / 读写是否区分 / Bash 读侧是否一并收口，全部要停轮）；②「**对标业界产品**」（「deny 默认 + allow 显式覆盖」是主流 coding agent 权限模型的共同形态，每条取舍都有可对照的既有实现）。判据表的反例「给已有工具加一个可选参数（→ light）」**不成立**：本 change 不是给**一个**判定器加参数，而是把**同一份 allow 数据喂给两个互不相同的判定器**，而且它的效果是**放宽**一条既有安全约束——放宽型改动与收紧型改动的风险不对称，必须按 full 做。调研对象是本地参考仓库 `/home/shared/agent-study/reference-repos/` 下的 codex / kimi-code / opencode 三个有内置权限模型的仓（`pi` 无内置权限系统、`zcode` 为静态白名单，本 change 只在对口处引用）。**注意**：本 worktree 没有 `.dev/reference-repos.txt`（该文件 gitignore、属本地配置），实际路径由上列绝对路径给出——这不构成豁免，仅记录依据来源。
- research questions:
  1. 主流 coding agent 的路径权限模型里，**allow 与 deny 谁优先**？多条规则同时命中时怎么解？
  2. 用户可配的路径白名单**粒度**是什么？**glob 能不能用于授权（写）**，还是只用于拒绝？
  3. 敏感文件（`.env` 族）的**模板 vs 凭据**区分在业界怎么定？「开 `.env`」是否级联到 `.env.local` / `.env.production`？
  4. 「静态配置白名单」与「人类答复扩权」在业界的相对位置是什么？本 change 做哪一个？
  5. 读写是否区分（read/write 不对称）？
  6. 白名单配置住在哪一级（项目级 / 用户级 / 运行参数）？
- findings:
  1. **优先级：三家主流实现都保证「显式 allow 能覆盖默认保护」，同时「显式 deny 恒为最高优先级」。** codex 取**最严格者**：`Evaluation::from_matches` 是 `matched_rules.iter().map(RuleMatch::decision).max()`（`codex/codex-rs/execpolicy/src/policy.rs:366`），而 `Decision` 的 `Ord` 顺序是 `Allow < Prompt < Forbidden`（`codex/codex-rs/execpolicy/src/decision.rs:9-16`）。kimi-code 是**有序列表、首个命中者胜**（`AgentPermissionPolicyService.evaluate` 的 `for … if (result !== undefined) return`，`kimi-code/packages/agent-core-v2/src/agent/permissionPolicy/permissionPolicyService.ts:61-64`），而其策略顺序里 `UserConfiguredDeny`（`:41`）在 `UserConfiguredAllow`（`:48`）**之前**、`SensitiveFileAccessAsk`（`:49`）在它**之后** ⇒ ① deny 优先于 allow；② **显式 allow 优先于敏感文件保护**（allow 命中即短路，敏感文件判定根本不被求值）。opencode 是**最后一条匹配者胜**：`evaluate()` 用 `findLast`，且无匹配时默认 `ask` 而非 deny（`opencode/packages/core/src/permission.ts:76-83`），规则集是配置里的有序数组（`opencode/packages/schema/src/permission.ts:58-64`、`opencode/packages/core/src/config.ts:60-62`）。⇒ **「allow 覆盖默认 deny」是必需语义**——否则白名单是死配置（本仓今天正是死配置：`WorkspacePolicy.__init__` 已接受 `denied_patterns` 却只在 `agent/main.py:253` 传 `command_denylist`）；而**显式 deny 的最高优先级不可动摇**。
  2. **粒度：codex 明确「glob 只能用于 deny，不能用于授权」。** `normalize_additional_permissions` 对 glob 入口直接 fail-closed：`if matches!(&entry.path, FileSystemPath::GlobPattern { .. }) && entry.access != FileSystemAccessMode::Deny { return Err("glob file system permissions only support deny-read entries") }`（`codex/codex-rs/sandboxing/src/policy_transforms.rs:30-35`）。授权走**精确路径**并做**符号链接保留式规范化**（同文件 `:39-41` 的 `canonicalize_preserving_symlinks`）。⇒ 这正是 issue #272 实测到的 `**/*` 坑的**业界同名解法**：把 glob 从「授权」面整体移走，而不是加黑名单特判。
  3. **「deny 默认 + 显式 allow 覆盖」在 codex 有逐字同名的先例。** `WritableRoot.protected_metadata_names` 的文档注释写「Workspace metadata path names that must not be created or replaced under `root` **unless the policy grants an explicit write rule for that metadata path**」（`codex/codex-rs/protocol/src/protocol.rs:1050-1053`）；实现是 `protected_metadata_names_for_writable_root` —— 只有当 `metadata_paths.iter().all(|metadata_path| !policy.can_write_path_with_cwd(metadata_path, cwd))` 时才把该名字加进保护集（`codex/codex-rs/protocol/src/permissions.rs:1781-1807`）；对应测试的断言文案就是 `"explicit .codex rule should win over the default protected carveout"`（同文件 `:2092-2101`）。**粒度是精确路径**，且只按 writable root 的**首个路径分量**匹配（`path_contains_protected_metadata_name` 只看 `relative_path.components().next()`，`protocol.rs:1077-1087`）。
  4. **`.env` 族：模板豁免是共识，「变体跟随」没有任何一家做。** kimi-code 的 `isSensitiveFile`（`kimi-code/packages/agent-core-v2/src/tool/path-access.ts:51-81`）对 `.env` 判敏感（`:58` 的 `SENSITIVE_BASENAMES`）、对 `ENV_EXEMPTIONS = {'.env.example','.env.sample','.env.template'}` 显式豁免（`:29`），而对 `ENV_PREFIX = '.env.'` 的其余后缀**一律判敏感**（`:59`）⇒ `.env.local` / `.env.production` 都是凭据；另有 `SENSITIVE_DOT_VARIANT_SUFFIXES`（`.bak`/`.backup`/`.copy`/`.disabled`/`.key`/`.old`/`.orig`/`.pem`/`.save`/`.tmp`，`:33-44`）把「凭据文件的副本」一并收进敏感集。本仓的 `is_env_sensitive_name`（`agent/workspace_policy.py:91-102`）**形状一致**（模板词 `ENV_TEMPLATE_WORDS` 比 kimi 略宽：多 `dist`/`defaults`/`tpl`，`agent/workspace_policy.py:61`）⇒ 两家口径已经对齐，本 change 只需**不破坏**它。
  5. **「静态配置白名单」与「人类答复扩权」是同一张规则表的两个来源，本 change 只做前者。** kimi-code 的 `session-approval-history` 策略把人类答复落成规则（`kimi-code/packages/agent-core-v2/src/agent/permissionPolicy/policies/session-approval-history.ts`，写入条件见 `agent/permissionRules/permissionRulesOps.ts:53-64` 的 `result.decision === 'approved' && result.scope === 'session'`），opencode 的 `Reply = ["once","always","reject"]`（`opencode/packages/schema/src/permission.ts:40`）同理；而 `UserConfiguredAllow/Deny/Ask` 策略读的是**配置文件里的规则**（`.../policies/user-configured-rule.ts:14-18` 的 `USER_CONFIGURED_SCOPES = {turn-override, project, user}`）。⇒ 本 change 加的是**人预先写死在配置文件里的豁免**，与 #254 已拍板的「扩权必须落在人类答复上」不冲突——身份是配置作者，不是被判定者；「模型提议 → 自动落规则」那条路仍在 Non-Goal。
  6. **配置级别：静态白名单住在配置文件里是主流。** opencode 的 `permissions` 是配置文件中的有序规则数组（`opencode/packages/core/src/config.ts:60-62`，且含 `project`/`user` 两级 scope 概念）；codex 的额外文件系统权限来自运行参数/用户配置构成的 `AdditionalPermissionProfile`（`codex/codex-rs/sandboxing/src/policy_transforms.rs:18-77`）。⇒ 本仓沿用既有 `tools.*` 项目级配置通道（`tools.command_denylist` / `tools.ignore_patterns`）是**零新增机制**的选择。
  7. **本仓形态的独立复核（不照抄 issue），五处与 issue 说法不同或 issue 未覆盖：** 见 `design.md` 的「实现要点复核」节 —— ① 生产构造点是**三处入口可配置 + 一处 dry-run 沙箱 = 四处**（`agent/tools/builtin/subagents.py:2005` 会在「全仓 grep 只找到三处」的口径下被漏判，且 issue 写的 `web/session.py:1566` 已漂移到 `:1728`）；② `WorkspacePolicy.__init__` 已接受 `denied_patterns`（issue 说对了），但**它只覆盖 `DEFAULT_DENIED_PATTERNS` 那一路 glob 判定，不覆盖 `is_sensitive_dot_name` 的段级判定**（实测：`WorkspacePolicy(root, denied_patterns=())` 下 `.env` 仍 `is_denied=True`）——所以「接线」不是把 `denied_patterns` 传进去就完事；③ `CommandGuard` 在 `agent/tools/builtin/bash.py:87` 只从 `policy.workspace_root` 构造，**生产路径上完全拿不到任何配置**，所以「同源喂两层」必须新增 `BashTool` → `CommandGuard` 的传参面；④ **两层在变更前就不同向**——实测 13 条被拒路径里 **8 条**（`deploy.pem` / `id_rsa` / `node_modules/x.js` 等）文件层 DENY、Bash 层 `cp` ALLOW，因为护栏的写目标判定根本不读 `DEFAULT_DENIED_PATTERNS` 那张 glob 表 ⇒「两层恒同向」是假前提；⑤ **嵌套 `.env` 的 Bash `cp`/`mv` 被 denylist 整句正则前置拦下**（`cp x config/.env` ⇒ `deny/denylist`，五个拼写变体全灭）⇒ 免豁的 Bash 覆盖面**有真实缺口**，必须在文档里写明（`design.md` Decision 9）。
- design impact:
  - **allow 必须覆盖默认 deny**（否则本 change 是死配置）——这直接决定 `design.md` Q1 的推荐值，且**只覆盖文件级 deny**、不覆盖结构性目录 deny 与 workspace 边界（findings 1 的「显式 deny 最高优先级」+ findings 3 的 codex 先例）。
  - **粒度用精确 workspace 相对路径，glob 元字符在解析期 fail fast**（findings 2）——这同时消灭 issue 的 `**/*` 硬约束与「前缀匹配越界」整类 bug（对照本仓 #247 的路径分量边界教训）。
  - **`.env` 变体不跟随**（findings 4）——与 #254 刚把凭据变体收进 deny 的方向对齐，避免「开 `.env` 顺手打开 `.env.production`」。
  - **配置住 `asterwynd.yaml` 的 `tools.allowed_write_paths`**（findings 6），默认空列表，与 `tools.command_denylist` 同构。
  - **同源改造的落点被钉死**（findings 7）：`WorkspacePolicy` 是数据的唯一来源，`CommandGuard` 通过 `BashTool` 拿到同一份数据；判定逻辑走**共享谓词函数**，禁止把 allowlist 判定在两层各写一遍（`#254` 的 D12 教训：两侧漂移过）。**但共享谓词 ≠ 共享调用点**：allow 只在**写路径**求值，`is_denied` / `assert_read_allowed` / `repo_map.py:173` 的索引跳过判定都不感知 allowlist——否则会顺手打开读侧与 tree-sitter 索引面（`design.md` Decision 2 / Q8）。
  - **「两层同向」必须改成增量表述**（findings 7 的第 ④ 条，`design.md` R10）：护栏的写目标判定不读 `DEFAULT_DENIED_PATTERNS`，所以两层在**变更前**就有 8/13 条路径不同向（Bash 更宽）。规格与测试只能承诺「allow 不使任一层更宽」+「allow 命中处两层同向变化」，不能承诺绝对同向。
  - **「模型自配白名单」被显式排除**（findings 5）：本 change 只有配置文件这一个来源。

## 用户故事

- 作为本仓维护者，我的项目有一个必须由 agent 生成的 `.env`。我在 `asterwynd.yaml` 里写 `tools.allowed_write_paths: ['.env', '.env.testing']`，agent 的 `Write` / `Edit` 就能写这两个文件，而 `.env.local`、`.env.production`、`.git/config` **仍然被拒**。
- 作为本仓维护者，我不配置这一项时，agent 的行为与升级前**逐字节一致**——我不需要重新评审任何既有用例。
- 作为本仓维护者，我看到 agent 用 `echo API_KEY=x >> .env` / `tee .env` 这类 Bash 写法时**同样**被这条豁免放行（而不是只有 `Write` 工具生效）——两层判定同一份数据。
- 作为本仓维护者，我要配**嵌套**路径（`config/.env`）时，能事先知道它的兑现面是「`Write` / `Edit` / `echo >>` / `tee` / `dd of=` / `install` 生效，`cp` / `mv` 仍拒」——而不是自己撞上一条笼统的 `Command denied by sandbox command guard` 去猜原因（见 `design.md` Decision 9 与 Q7）。
- 作为流程 owner，我用**本 change 自己**作为 `witnessloop-adoption` 阶段 B 的「真实小需求」，拿到一份带 `文件:行号` 依据的分叉清单，判断「影子期该不该真打开」。
