# Tasks: 护栏写白名单（guard-write-allowlist）

> **状态：立项文档；未开始实现。** 第 0 节是前置门——`design.md` 的 `## Open Questions` 六条**必须停轮抛给用户并逐条收到答复**，答复记入 `reviews/grill-design.md` 的 `## User Confirmation` 之前，不得写实现代码或测试代码（AGENTS.md 的 grill-confirmation-gate）。
>
> **测试先行**含义：第 2 节（测试）先于第 3 节（实现）。本 change 的安全属性集中在**否定用例**上（未列入的 `.env` 仍拒），否定用例必须与正例同时先写。
>
> **本 change 有两条腿**：第 1–5 节是**功能实现**；第 6 节是 `witnessloop-adoption`（已归档 `2026-10-13`）**阶段 B** 的流程验证——用本 change 自己当那个「真实小需求」。第 7 节是收尾。

## 0. 设计追问与用户确认（前置门，不完成不开工）

- [ ] 0.1 用 `grilling` skill（或等价独立零记忆设计追问）对 `design.md` 做设计追问，产出结构化决策记录到 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条）。
- [ ] 0.2 把 `design.md` 的 `## Open Questions` **六条**（Q1 allow 覆盖面 / Q2 粒度 / Q3 `.env` 变体是否跟随 / Q4 配置级别 / Q5 读写是否区分 / Q6 Bash 读侧是否一并收口）**逐条停下抛给用户**，每条附本 change 真实场景的具体例子（参数、输入输出、前后对比）与推荐值，等待明确答复。**得到答复前不写实现代码。**
- [ ] 0.3 把六条答复逐条记进 `reviews/grill-design.md` 的 `## User Confirmation`（格式 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`），自查 `_unconfirmed_open_questions` 返回空。
- [ ] 0.4 按 `grill-flow-hardening`（issue #298）跑**设计阶段审阅闭环**（独立零记忆审阅者 → 对抗分析 → verdict → 修 → 再审，直到 PASS 或轮数封顶），产出 `reviews/grill-adversarial.md`。**能由代码判定的问题用代码给出带证据（`文件:行号`）的答案并移出停轮队列**（本 change 已移出三条：三处生产构造点 / `denied_patterns` 不能当 allow 载体 / Bash 读侧今天通着——见 `design.md` 的 Pre-Implementation Review）。
- [ ] 0.5 把六条答复落到 `design.md`（重写为 `## User Rulings` 一节，与 `## Decisions` 并列），并据此定稿：allow 覆盖面清单、粒度校验规则、是否需要结构性 deny 的硬编码清单、配置解析的 fail-fast 条件。

## 1. 规格

- [ ] 1.1 修改 `workspace-safety` 规格：新增「显式可写豁免」「可写豁免的粒度与配置合法性」「可写豁免不放宽结构性 deny 与命令 denylist」三条 Requirement，并把「工作区策略支持配置扩展」改为覆盖三个配置项（delta 已在 `specs/workspace-safety/spec.md`）。
- [ ] 1.2 修改 `configuration` 规格：新增「工具策略支持 allowed_write_paths 配置」（delta 已在 `specs/configuration/spec.md`）。
- [ ] 1.3 同步对应 current spec 到 `openspec/specs/workspace-safety/spec.md` 与 `openspec/specs/configuration/spec.md`，并按 `scripts/flow-policy.json` 追加 `current_spec_synced` 解释事件（受保护路径）。
- [ ] 1.4 按 0.5 的裁定回写 `design.md` 的 `## Decisions`，使 Decisions 与最终规格逐条对齐（不得只改规格不改设计）。

## 2. 测试（先行，先写后实现）

- [ ] 2.1 `tests/agent/test_workspace_policy.py`：**正例**——`allowed_write_paths=('.env',)` 下 `.env` 与 `config/.env` 的 `assert_write_allowed` 放行。
- [ ] 2.2 `tests/agent/test_workspace_policy.py`：**否定用例**（本 change 的核心验收面）——① 同 policy 下 `src/.env` / `.env.local` / `.env.production` 仍拒；② `../outside/.env` 因 workspace **边界**被拒（allow 不得先于边界生效）；③ `.env.example` 等模板行为不变；④ 按 Q1 裁定，结构性目录 deny（`.git/config`）即便被显式列入仍拒。
- [ ] 2.3 `tests/agent/test_workspace_policy.py`：**默认值回归**——`allowed_write_paths=()` 时逐条断言与引入本能力前一致（配置为空 ⇒ 行为零变化）。
- [ ] 2.4 `tests/agent/tools/test_command_guard.py`：**Bash 层同源生效**——带 allowlist 时 `cp x .env` / `echo API_KEY=x >> .env` / `tee .env` / `dd of=.env` 由 DENY 变 ALLOW；不带 allowlist 时这些断言逐条保持今天的结论。
- [ ] 2.5 `tests/agent/tools/test_command_guard.py`：**Bash 层否定用例**——带 allowlist 时 `cp x .env.local`、`cp x /etc/passwd`、`cp x .git/config` 仍 DENY。
- [ ] 2.6 **跨层一致性测试**（锁定风险 R1）：同一份 allowlist + 同一组路径，断言 `assert_write_allowed` 与 `CommandGuard` 的写目标判定**结论同向**。
- [ ] 2.7 `tests/agent/test_config.py`：解析正例、缺省为空、以及 fail fast 逐条用例（glob 元字符 / 绝对路径 / `..` 段 / 尾 `/`）。
- [ ] 2.8 确认 `benchmarks/attacks/attacks.json` 的 `deny` 用例在**配置了 allowlist** 的 guard 下仍全部被拦（allow 只放宽被明确列入的路径）。

## 3. 实现

- [ ] 3.1 `agent/workspace_policy.py`：新增独立的 `allowed_write_paths` 参数与**共享判定谓词**（Decision 1：不靠覆写 `denied_patterns` 实现——实测那样对 `.env` 无效），谓词同时供 `is_denied` 与命令护栏调用。
- [ ] 3.2 `agent/tools/command_guard.py`：`CommandGuard.__init__` 接收同一份 allowlist，把 `_check_target` / `_has_protected_redirect` / `_check_dynamic_target` / `_check_mv_cp` / `_check_tee` / `_check_dd` 的路径判定收敛到 3.1 的共享谓词（Decision 2：禁止两层各写一份匹配）。
- [ ] 3.3 `agent/tools/builtin/bash.py:87`：`BashTool.__init__` 构造 `CommandGuard` 时传入 `self.policy.allowed_write_paths`（现状只传 `workspace_root`）。
- [ ] 3.4 `agent/config.py`：`ToolsConfig` 新增 `allowed_write_paths: tuple[str, ...] = ()`（`:151-161` 旁），`_parse_tools_config`（`:875-897`）走 `_parse_string_list` 并追加 Decision 3 的语义校验（fail fast）。
- [ ] 3.5 三个生产构造点接线：`agent/main.py:251`、`web/session.py:1728`、`benchmarks/agent_runner.py:349` 把 `config.tools.allowed_write_paths` 传给 `WorkspacePolicy`。
- [ ] 3.6 `asterwynd.example.yaml:35`：在 `command_denylist` 旁补 `allowed_write_paths` 示例与一行注释（说明「deny 默认 + 精确覆盖」与不接受 glob）。
- [ ] 3.7 按 Q5 的裁定实现读写区分：只接 `assert_write_allowed`（`:356-360`），`assert_read_allowed`（`:350-354`）不受影响。

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
- [ ] 6.2 **（对应 B.2）在新流程上跑完整链路**：本地 `guard` 拦（Write/Edit 路径）→ 写码 → 本仓 `/review-loop` 产 asterwynd 形态审阅证据 → **额外**跑 `uv run witnessloop manifest build --change guard-write-allowlist --stage <stage> --report reviews/<报告>.md` 产出 **witnessloop 形态** manifest → `uv run witnessloop check --root .` 核证据 → `gate / check` 在 CI 里**真的跑起来**（含测试执行点）。**硬约束**：`reviews/` 下**每一份** `.md` 都要有一份 manifest（`grill-design.md` / `grill-adversarial.md` / `building-review.md` 三份），否则孤儿规则被激活；`manifest build` 必须在**所有内容提交之后**跑（stale 约束）；**执行者＝人在本地跑**（`gate.yml` 只做 `check`、不产证据）。**验证一律用 `uv run witnessloop`**（PATH 上那份是另一份 uv-tool 安装，测不到本仓/上游源码树）。
- [ ] 6.3 **（对应 B.3）如实记录已知红**：K1 `add-minimal-tui-runtime-view` 的报错原文；K2 本 change 自己触发的 `building` / `grill-adversarial` 两 stage 判定的实际结论。**不放宽判据、不给它们开豁免。**
- [ ] 6.4 **（对应 B.4）列出分叉清单**：同一段 diff 下，本地 checker 判绿而 witnessloop 判红（及反向）的项，逐条给 `文件:行号` 级依据。**必须逐条独立复核**，不得照抄归档 change 的既有结论（那些是在另一个 change 上实测的）。
- [ ] 6.5 **（对应 B.5）评估本地守卫的行为变化**：先做前置核验（`command -v witnessloop` + `witnessloop --help` 是否含 `guard` 子命令——PATH 上若是旧版 CLI，`guard.sh` 的「1 → 拦、其余 → 放行」映射会让它**静默空转**，不做这步就会把「放行」误读成「证据完备」）；再实测一次「用 Bash 写受管路径」是否确实绕过 witnessloop `guard`。**必须在主 checkout 与 building worktree 各测一次**（`.claude/` 被 gitignore，worktree 下没有本仓守卫的 hook）。
- [ ] 6.6 **（对应 B.6）写「值不值得真打开」的判断依据**：findings 的可读性与可行动性、误报率、与本地 checker 的重复劳动量、对 in-flight change 的影响面、**两套 manifest 并存的额外劳动量**（如实记：本 change 为此多跑了 3 次 `manifest build` + 清理中间轮 + 守 stale 顺序）。
- [ ] 6.7 **（对应 B.7）记录测试执行点的已知边界**：`uv run --extra dev pytest -q` 覆盖到什么、覆盖不到什么（浏览器用例、编码 warn-as-error 门、`openspec validate`、artifact checker 四条**不在**执行点内），以及它们在本仓 `validate` job 里**仍然照跑**的事实。
- [ ] 6.8 **（对应 B.8）把「`来源:` 谓词不兼容」这组红与「配置错误」分开归因**：按 `design.md` Decision 8 的两列表格分类。**已知事实**（上游 issue #20，已拍板 U7「等上游修、本仓零改动」）：一旦建了 witnessloop 形态的 grill manifest，grill 正文判据**会全红**——witnessloop 的 `_SOURCE_RE` 不认本仓通篇使用的 `- **来源**: x` 加粗写法。**注意**：本 change 的 diff 触达 `agent/**` ⇒ 与 `witnessloop-adoption` 不同，`building` / `grill-adversarial` 两条判定**也会真的触发**（不因 `code_hits` 为空而跳过）。
- [ ] 6.9 把 `stage-b-observation.md` 的路径**回链到跟踪入口**：在 issue #305 追加 comment 指向本 change 的报告路径。**不得**往已归档的 `witnessloop-adoption` 目录里加文件（归档是 `event_explained` 受保护路径，且给历史 change 补新证据会造成语义漂移——`design.md` Decision 6）。

## 7. 收尾（本 change 的归档前必须完成）

- [ ] 7.1 检查文档影响面：`docs/development-guide.md`（配置项说明 + 阶段 B 的跑法）、`docs/openspec-change-backlog.md`（本 change 的登记与清理）、`docs/known-debt.md`（若 Q6 裁定记为债务，则补一条并配 `protected_artifact_explained` 事件）、`AGENTS.md`（本 change **不改流程段**，但要确认没有因本 change 产生的事实性出入）。
- [ ] 7.2 确认 witnessloop 形态 manifest 在**所有内容提交之后**重建（stale 约束），且 `reviews/` 处于「每份 `.md` 都被绑定」的一致状态。
- [ ] 7.3 **归档 move 必须是独立的纯 rename 提交**（`git mv` 单独成一个 commit，不与任何内容改动并用——`witnessloop-adoption` 实测：并用会被 git 记作 `A`/`D` 而非 `R100`，`is_archive_move` 为假 ⇒ 3 条红）；归档到 `openspec/changes/archive/2026-10-14-guard-write-allowlist/`（日期前缀以实际归档日为准）。
- [ ] 7.4 从 `docs/openspec-change-backlog.md` 移除本 change，并追加 `backlog_updated` 与 `change_archived` 解释事件（受保护路径）。
- [ ] 7.5 跑 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`，把原始输出要点写进 PR 描述。
- [ ] (post-merge) 7.6 PR 合入后：确认 active change 目录不存在、backlog 干净、本地 `master` 已快进到 `origin/master`；在 issue #272 补完成说明 comment 并关闭 issue。
