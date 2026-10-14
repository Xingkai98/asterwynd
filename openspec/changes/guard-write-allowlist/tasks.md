# Tasks: 护栏写白名单（guard-write-allowlist）

> **状态：立项文档；未开始实现。** 第 0 节是前置门——`design.md` 与 `reviews/grill-design.md` 的 `## Open Questions`（**同一套 Q1–Q12，共十二条**）**必须停轮抛给用户并逐条收到答复**，答复记入 `reviews/grill-design.md` 的 `## User Confirmation` 之前，不得写实现代码或测试代码（AGENTS.md 的 grill-confirmation-gate）。
>
> **测试先行**含义：第 2 节（测试）先于第 3 节（实现）。本 change 的安全属性集中在**否定用例**上（未列入的 `.env` 仍拒），否定用例必须与正例同时先写。
>
> **本 change 有两条腿**：第 1–5 节是**功能实现**；第 6 节是 `witnessloop-adoption`（已归档 `2026-10-13`）**阶段 B** 的流程验证——用本 change 自己当那个「真实小需求」。第 7 节是收尾。

## 0. 设计追问与用户确认（前置门，不完成不开工）

- [ ] 0.1 用 `grilling` skill（或等价独立零记忆设计追问）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条）。
- [ ] 0.2 把 `design.md` 的 `## Open Questions` **十二条**（立项原提 Q1–Q6：allow 覆盖面 / 粒度 / `.env` 变体是否跟随 / 配置级别 / 读写是否区分 / Bash 读侧是否一并收口；独立 grill 补充 Q7–Q12：嵌套路径的 Bash `cp`/`mv` 是否扩范围 / allow 判定面接在哪 / 附加根下同名路径是否覆盖 / 裁定与规格 delta 的先后顺序 / grill 报告的 `来源:` 写法 / 结构性 deny 的判定规则）**逐条停下抛给用户**，每条附本 change 真实场景的具体例子（参数、输入输出、前后对比）与推荐值，等待明确答复。**得到答复前不写实现代码。** 其中 **Q7 与 Q8 是 grill 判定的阻塞项**。
- [ ] 0.3 把十二条答复逐条记进 `reviews/grill-design.md` 的 `## User Confirmation`（格式 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`），自查 `_unconfirmed_open_questions` 返回空。**编号纪律**：`n` 必须用 **`reviews/grill-design.md` 的编号**——机械门（`scripts/check_openspec_artifacts.py` 的 `_unconfirmed_open_questions` 与 `scripts/workflow_guard.py` 的 grill 证据判定）**只读该文件**，两份文件的 Q 集合与编号必须一致（两份现均列 Q1–Q12）。若这里写成别的编号，门会「张冠李戴判绿」（确认的是一条、门以为确认了另一条）。**注意**：该文件当前的 **13 条** witnessloop finding 全部是「缺 `## User Confirmation` 小节」+「Q1–Q12 未经确认」，本步完成后即消（见 `design.md` Decision 8 的订正前提）。
- [ ] 0.4 按 `grill-flow-hardening`（issue #298）跑**设计阶段审阅闭环**（独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审，直到 PASS 或轮数封顶），产出 `reviews/grill-adversarial.md`。**能由代码判定的问题用代码给出带证据（`文件:行号`）的答案并移出停轮队列**（本 change 已移出六条：生产构造点四处 / `denied_patterns` 不能当 allow 载体 / Bash 读侧今天通着 / 嵌套 `.env` 的 Bash `cp`/`mv` 被 denylist 前置拦下 / 两层今天就有 8/13 条不同向 / grill 正文判据不是结构性地全红——见 `design.md` 的 Context 与 Pre-Implementation Review）。
- [ ] 0.5 把十二条答复落到 `design.md`（重写为 `## User Rulings` 一节，与 `## Decisions` 并列），并据此定稿：allow 覆盖面与结构性 deny 的推导规则、粒度校验规则、附加根作用域口径、配置解析的 fail-fast 条件。

## 1. 规格

- [ ] 1.1 修改 `workspace-safety` 规格：新增五条 Requirement（显式可写豁免 / 可写豁免的粒度与配置合法性 / 可写豁免不放宽结构性 deny 与命令 denylist / **可写豁免不使任何一层比引入前更宽** / **Bash 层豁免覆盖面差异必须被记录**），并把「工作区策略支持配置扩展」改为覆盖三个配置项（delta 已在 `specs/workspace-safety/spec.md`）。
- [ ] 1.2 修改 `configuration` 规格：新增「工具策略支持 allowed_write_paths 配置」（delta 已在 `specs/configuration/spec.md`）。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/workspace-safety/spec.md` 与 `openspec/specs/configuration/spec.md`，并按 `scripts/flow-policy.json` 追加 `current_spec_synced` 解释事件（受保护路径）。
- [ ] 1.4 **裁定后改的先后顺序（Q10 的口径，已写死）**：**规格随裁定改** —— 先按 0.5 重写本 change 的 spec delta（1.1/1.2 是它们的落地），再让 `design.md` 的 `## Decisions` 与规格**同向**（不得只改设计不改规格，也不得让规格停留在推荐值而设计与裁定对齐）。规格 delta 现文中带「推荐值」性质的条款（结构性 deny 的判定、附加根作用域、读写区分）在裁定与之不同时**必须逐条重写**，并同步反向修订实现任务与测试任务的断言。

## 2. 测试（先行，先写后实现）

- [ ] 2.1 `tests/agent/test_workspace_policy.py`：**正例**——`allowed_write_paths=('.env',)` 下 `.env` 与 `config/.env` 的 `assert_write_allowed` 放行。
- [ ] 2.2 `tests/agent/test_workspace_policy.py`：**否定用例**（本 change 的核心验收面）——① 同 policy 下 `src/.env` / `.env.local` / `.env.production` 仍拒；② `../outside/.env` 因 workspace **边界**被拒（allow 不得先于边界生效）；③ `.env.example` 等模板行为不变；④ 按 Q1 裁定，结构性 deny 即便被显式列入仍拒（`.git/config` 走目录类敏感名段；`.ruff_cache/CACHEDIR.TAG` 走含 `/` 的条目）。
- [ ] 2.3 `tests/agent/test_workspace_policy.py`：**默认值回归**——`allowed_write_paths=()` 时逐条断言与引入本能力前一致（配置为空 ⇒ 行为零变化）。
- [ ] 2.4 `tests/agent/tools/test_command_guard.py`：**Bash 层同源生效**——带 allowlist 时**裸名** `.env` 的 `cp x .env` / `echo API_KEY=x >> .env` / `tee .env` / `dd of=.env` 由 DENY 变 ALLOW；不带 allowlist 时这些断言逐条保持今天的结论。
- [ ] 2.5 `tests/agent/tools/test_command_guard.py`：**Bash 层否定用例**——带 allowlist 时 `cp x .env.local`、`cp x /etc/passwd`、`cp x .git/config` 仍 DENY。
- [ ] 2.5b `tests/agent/tools/test_command_guard.py` + `tests/agent/test_workspace_policy.py`：**Bash 读侧不被 Allow 打开**——`allowed_write_paths=('.env',)` 下 `cp .env /tmp/out` 与 `mv .env /tmp/out`（**源位置**）仍 DENY（护栏侧 `cp_source` / 策略侧 `_env_source_is_credential`），且 `assert_read_allowed('.env')` 仍拒。这是「只放行写」在 Bash 层的第二条腿（`design.md` Decision 2 的不受影响清单），漏了它被豁免的 `.env` 会变成可外泄的读源。
- [ ] 2.6 **Decision 9 的边界断言（必须写成断言，不是缺陷）**——带 `allowed_write_paths=('config/.env',)` 时：`cp x config/.env` 与 `mv x config/.env` **仍 DENY 且 `last_reason == "denylist"`**；同时 `echo K >> config/.env` / `tee config/.env` / `dd of=config/.env` / `install x config/.env` **变 ALLOW**。在测试里写明「这是规格行为（见『Bash 层豁免覆盖面差异必须被记录』Requirement），不得被『顺手修好』而改动 denylist 语义」。
- [ ] 2.7 **跨层一致性测试（锁定 R1/R10，测**增量**不测绝对值）**：同一份 allowlist + 同一组路径，断言**变化方向同向**（allow 命中 ⇒ 文件工具与命令护栏都从拒变放行；未命中 ⇒ 两处都与今天逐条一致）。**SHALL NOT** 断言「两层对任意路径恒同向」——实测今天已有 8/13 条被拒路径两层不同向（`deploy.pem` / `id_rsa` / `node_modules/x.js` 等，Bash 层更宽）。
- [ ] 2.8 `tests/agent/test_config.py`：解析正例、缺省为空、fail fast 逐条用例（glob 元字符 / 绝对路径 / `..` 段 / 尾 `/`），以及**结构性 deny 分类规则的可复算断言**（对 `DEFAULT_DENIED_PATTERNS` 逐条断言「含 `/` ⇒ 结构性」、对 `SENSITIVE_DOTDIRS` 逐条断言段级判定）。
- [ ] 2.9 确认 `benchmarks/attacks/attacks.json` 的 `deny` 用例在**配置了 allowlist** 的 guard 下仍全部被拦（allow 只放宽被明确列入的路径）。

## 3. 实现

- [ ] 3.1 `agent/workspace_policy.py`：新增独立的 `allowed_write_paths` 参数与**共享判定谓词**（Decision 1：不靠覆写 `denied_patterns` 实现——实测那样对 `.env` 无效），谓词同时供 `is_denied` 与命令护栏调用。
- [ ] 3.2 `agent/tools/command_guard.py`：`CommandGuard.__init__` 接收同一份 allowlist，把**写目标判定面**（口径见 `design.md` Decision 2 的唯一定义）的六个方法——`_check_target`（**仅写目标位置的调用**）/ `_has_protected_redirect` / `_check_dynamic_target` / `_check_mv_cp` / `_check_tee` / `_check_dd`——的路径判定收敛到 3.1 的共享谓词（Decision 2：禁止两层各写一份匹配）。**必须核对三条排除项**：① 不碰 `check()` 第 1 步的整句 denylist 正则扫描；② `mv`/`cp` 的**源位置**判定（读侧）SHALL NOT 被 allow 影响——否则 `cp .env /tmp/x` 会在 `.env` 被豁免后变成可读出口；③ 不碰 `_check_rm`。
- [ ] 3.3 `agent/tools/builtin/bash.py:87`：`BashTool.__init__` 构造 `CommandGuard` 时传入 `self.policy.allowed_write_paths`（现状只传 `workspace_root`）。
- [ ] 3.4 `agent/config.py`：`ToolsConfig` 新增 `allowed_write_paths: tuple[str, ...] = ()`（`:151-161` 旁），`_parse_tools_config`（`:875-897`）走 `_parse_string_list` 并追加 Decision 3 的语义校验（fail fast）。
- [ ] 3.5 三个生产构造点接线：`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349` 把 `config.tools.allowed_write_paths` 传给 `WorkspacePolicy`。
- [ ] 3.6 `asterwynd.example.yaml:35`：在 `command_denylist` 旁补 `allowed_write_paths` 示例与一行注释（说明「deny 默认 + 精确覆盖」与不接受 glob）。
- [ ] 3.7 按 Q5 与 Q8 的裁定实现读写区分：共享谓词**只**在写路径被调用——`assert_write_allowed`（`:356-360`）与命令护栏的写目标判定；`assert_read_allowed`（`:350-354`）、`is_denied`（`:316-338`）与 `agent/code_intelligence/repo_map.py:81,96,173` **不受影响**（Decision 2 的对照清单，逐条核对）。
- [ ] 3.8 核对 `agent/browser/policy.py:121` 的 `assert_write_allowed` 调用点：浏览器产物落盘会继承豁免，确认这是预期行为并写进 PR 描述（不是遗漏）。
- [ ] 3.9 `agent/tools/builtin/subagents.py:2005`（`dry_run_workflow` 的临时沙箱）**不接线**：它无配置可传，且 `WorkspacePolicy(workspace_root=sandbox)` 不接受 allowlist 是正确的（沙箱里不该有用户的豁免）。核对它未被误当作「兜底」而漏出清单。

## 4. 验证

- [ ] 4.1 `uv run pytest -q`（新增用例 + 全量回归）。
- [ ] 4.2 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.3 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.4 **benchmark smoke**：本 change 触及 `agent/workspace_policy.py` 与 `agent/tools/`（命中 checker 的 benchmark smoke 触发面），跑一条 benchmark smoke 确认工具策略接线未破。
- [ ] 4.5 手工确认默认态：不配置 `asterwynd.yaml` 时 `.env` 的读写拒绝行为与 `fd6d581` 上逐条一致。

## 5. 实现后独立审阅闭环

- [ ] 5.1 跑 `/review-loop guard-write-allowlist`，产出 `reviews/building-review.md` + `reviews/building-review-manifest.json`（**asterwynd 形态**）。CHANGES_REQUESTED 则修复并加回归测试，再审，直到 PASS 或 3 轮封顶。
- [ ] 5.2 **收敛后清理中间轮产物**（如 `building-review-r1.md` / `building-review-r2.md`），或把最终版落到规范名——它们不在任何 manifest 的 `report_path` 上，第 6 节一旦建了 witnessloop 形态 manifest 就会成孤儿报告（`witnessloop-adoption` 的 N.6）。

## 6. 阶段 B：用真实小需求跑一遍（`witnessloop-adoption` 的 B.1–B.8）

> **本节是已归档 change `2026-10-13-witnessloop-adoption` 阶段 B 的落地**。那个 change 的 B.1–B.8 全部标了 `(post-merge)`、住在归档目录里；本 change **就是**它们等的那个「真实小需求」。观测报告落 `openspec/changes/guard-write-allowlist/stage-b-observation.md`（change 根目录，**不在 `reviews/` 下**——理由见 `design.md` Decision 6）。
>
> **B 的出口判据**（沿用归档 change）：产出验收报告，含 findings 清单、与本地 checker 的**分叉清单**、已知红清单、体验摩擦清单、**按成因分类的红清单**（配置问题 vs 工具不兼容），以及「值不值得真打开」的判断依据。

- [ ] 6.1 **（对应 B.1）选定真实小需求**：即本 change 自己。记录选择理由：它**触达 `require_change_for`**（改 `agent/**` / `web/**` ⇒ `code_hits` 非空 ⇒ `building` 与 `grill-adversarial` 两条 stage 判定**真的会触发**，与 `witnessloop-adoption` 自己 `code_hits` 为空形成对照）、**产生 spec delta 与受保护写入**（两份 spec 同步 + backlog 事件）、规模在 5 个文件以内。
- [ ] 6.2 **（对应 B.2）在新流程上跑完整链路**：本地 `guard` 拦（Write/Edit 路径）→ 写码 → 本仓 `/review-loop` 产 asterwynd 形态审阅证据 → **额外**产 witnessloop 形态 manifest → `witnessloop check` 核证据 → `gate / check` 在 CI 里**真的跑起来**（含测试执行点）。**命令写法（已按实测订正）**：必须 `cd /home/happy/witnessloop && uv run witnessloop manifest build --root /home/happy/ax-wt/guard-write-allowlist --change guard-write-allowlist --stage <stage> --report reviews/<报告>.md`（`check` 同理），**SHALL NOT** 在本 worktree 里裸跑 `uv run witnessloop`——实测本 worktree 的 `uv run which witnessloop` 解析到 `/home/happy/.local/bin/witnessloop`（PATH 上那份 uv-tool 安装），且 `uv run python -c "import witnessloop"` 报 `ModuleNotFoundError`（本仓 `pyproject.toml` 无此依赖），即**裸跑等于用 PATH 上那份、测不到 witnessloop 源码树**；口径与 `docs/development-guide.md` 的「witnessloop 影子接入」节一致。**硬约束**：`reviews/` 下**每一份** `.md` 都要有一份 manifest（`grill-design.md` / `grill-adversarial.md` / `building-review.md` 三份），否则孤儿规则被激活；`manifest build` 必须在**所有内容提交之后**跑（stale 约束）；**执行者＝人在本地跑**（`gate.yml` 只做 `check`、不产证据）。**注意 `plugin/hooks/guard.sh` 内硬编码裸命令**，上述 `uv run` 口径**覆盖不到它**——本地 `guard` 的前置核验见 6.5。
- [ ] 6.3 **（对应 B.3）如实记录已知红**：K1 `add-minimal-tui-runtime-view` 的报错原文；K2 本 change 自己触发的 `building` / `grill-adversarial` 两 stage 判定的实际结论。**不放宽判据、不给它们开豁免。** 同时如实记录**本 change 的 `reviews/grill-design.md` 的实测 finding 构成**（当前 **13 条** = 1 条「缺 `## User Confirmation` 小节」+ **Q1–Q12** 各 1 条「未经确认」，在 0.3 完成后即消），把它与 K1/K2 **分开列**。
- [ ] 6.4 **（对应 B.4）列出分叉清单**：同一段 diff 下，本地 checker 判绿而 witnessloop 判红（及反向）的项，逐条给 `文件:行号` 级依据。**必须逐条独立复核**，不得照抄归档 change 的既有结论（那些是在另一个 change 上实测的）。
- [ ] 6.5 **（对应 B.5）评估本地守卫的行为变化**：先做前置核验（`command -v witnessloop` + `witnessloop --help` 是否含 `guard` 子命令——PATH 上若是旧版 CLI，`guard.sh` 的「1 → 拦、其余 → 放行」映射会让它**静默空转**，不做这步就会把「放行」误读成「证据完备」）；再实测一次「用 Bash 写受管路径」是否确实绕过 witnessloop `guard`。**必须在主 checkout 与 building worktree 各测一次**（`.claude/` 被 gitignore，worktree 下没有本仓守卫的 hook）。
- [ ] 6.6 **（对应 B.6）写「值不值得真打开」的判断依据**：findings 的可读性与可行动性、误报率、与本地 checker 的重复劳动量、对 in-flight change 的影响面、**两套 manifest 并存的额外劳动量**（如实记：本 change 为此多跑了 3 次 `manifest build` + 清理中间轮 + 守 stale 顺序）。
- [ ] 6.7 **（对应 B.7）记录测试执行点的已知边界**：`uv run --extra dev pytest -q` 覆盖到什么、覆盖不到什么（浏览器用例、编码 warn-as-error 门、`openspec validate`、artifact checker 四条**不在**执行点内），以及它们在本仓 `validate` job 里**仍然照跑**的事实。
- [ ] 6.8 **（对应 B.8）把 grill 正文那组红与「配置错误」分开归因**：按 `design.md` Decision 8 的**三分类**表格分类（**格式选择导致的红** / 已知工具不兼容 / 配置问题）。**前提已按实测订正**：原稿写的「建了 witnessloop 形态 grill manifest 后 grill 正文判据**会全红**」**不成立**——把 witnessloop 自己的 `grill_evidence_findings` 跑在全部 **63** 份归档 `grill-design.md` 上实测得 **39 份判绿**、**9 份**只缺 `来源:`、**15 份**其它；使用**加粗 `来源` 写法**的共 **3 份**（独占行 2 + 同行内联 1），且**这 3 份都被判 src-only**。本 change 自己的报告用同行裸 `来源:` ⇒ **source 判据全命中**，它当前的红是「未确认」类（0.3 后即消）。⇒ 这条红是**可选择的**（取决于报告怎么写，Q11 裁定），**不是**结构性不兼容；报告里 SHALL 把它与上游 issue #20 那类真正的工具不兼容分开。**另注意**：本 change 的 diff 触达 `agent/**` ⇒ 与 `witnessloop-adoption` 不同，`building` / `grill-adversarial` 两条判定**也会真的触发**（不因 `code_hits` 为空而跳过）。
- [ ] 6.9 把 `stage-b-observation.md` 的路径**回链到跟踪入口**：在 issue #305 追加 comment 指向本 change 的报告路径。**不得**往已归档的 `witnessloop-adoption` 目录里加文件（归档是 `event_explained` 受保护路径，且给历史 change 补新证据会造成语义漂移——`design.md` Decision 6）。

## 7. 收尾（本 change 的归档前必须完成）

- [ ] 7.1 **检查文档影响面（按 AGENTS.md 的关键词扫描要求，范围是 `docs/` + `README.md` + `AGENTS.md` + `CONTEXT.md`）**：`docs/development-guide.md`（配置项说明 + 阶段 B 的跑法）、`docs/openspec-change-backlog.md`（本 change 的登记与清理）、`docs/known-debt.md`（若 Q6 裁定记为债务，则补一条并配 `protected_artifact_explained` 事件）、`AGENTS.md`（本 change **不改流程段**，但要确认没有因本 change 产生的事实性出入）。**已知五处命中，逐条给「改 / 不改 / 记债」结论**：① `docs/interview-script/walkthrough/W06-security.md:34`「敏感文件 deny …**读写都拒**」在本 change 落地后**变半真**（写侧多了一条显式豁免通道）⇒ 应改；② 同文件 **`:11`**（`└─ 命令拒绝列表：DEFAULT_DENYLIST（58 个危险模式）`）与 **`:35`**（正文同款「58 个模式」）**两处**，实测 `DEFAULT_DENYLIST` 为 **59**；③ `docs/interview-bullets/walkthrough.md:2483` 的「**35 条**」及所列 `.env` / `.env.*` / `**/.env` 模式实测已不存在（`DEFAULT_DENIED_PATTERNS` 现为 **32** 条，`.env` 族改由段级谓词判；同文件 `:2497` 同源）；④ 同文件 **`:2481`** 引 `agent/workspace_policy.py:9-45`（现为 **`9-43`**）；⑤ 同文件 **`:2499`** 引 `is_denied()` 为 `:222-239`（现为 **`:316-338`**）——②③④⑤ 是**变更前就存在**的历史口径问题，按 AGENTS.md **记债务**即可，但必须在本任务里被显式列出并给出结论。
- [ ] 7.2 确认 witnessloop 形态 manifest 在**所有内容提交之后**重建（stale 约束），且 `reviews/` 处于「每份 `.md` 都被绑定」的一致状态。
- [ ] 7.3 **归档 move 必须是独立的纯 rename 提交**（`git mv` 单独成一个 commit，不与任何内容改动并用——`witnessloop-adoption` 实测：并用会被 git 记作 `A`/`D` 而非 `R100`，`is_archive_move` 为假 ⇒ 3 条红）；归档到 `openspec/changes/archive/2026-10-14-guard-write-allowlist/`（日期前缀以实际归档日为准）。
- [ ] 7.4 从 `docs/openspec-change-backlog.md` 移除本 change，并追加 `backlog_updated` 与 `change_archived` 解释事件（受保护路径）。
- [ ] 7.5 跑 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`，把原始输出要点写进 PR 描述。
- [ ] (post-merge) 7.6 PR 合入后：确认 active change 目录不存在、backlog 干净、本地 `master` 已快进到 `origin/master`；在 issue #272 补完成说明 comment 并关闭 issue。
