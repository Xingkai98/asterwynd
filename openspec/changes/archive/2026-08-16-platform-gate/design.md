# Design: 平台闸门（platform-gate，P2）

## Context

现状事实（file:line / 平台实况证据）：

- **GitHub 平台配置现状**（`gh api repos/Xingkai98/asterwynd/branches/master/protection`，2026-08-15 实况）：
  - `required_status_checks.strict: true`、`contexts: ["validate"]`——`benchmark-gate` 未进 required，可绕过。
  - `required_pull_request_reviews.required_approving_review_count: 0`。
  - `required_conversation_resolution.enabled: false`。
  - `enforce_admins.enabled: true`。
  - `restrictions` 字段完全缺席（个人仓语义，PUT 时需显式 `restrictions: null`）。
- **CI workflow**（`.github/workflows/ci.yml`）：`validate`（pytest + openspec validate + artifact checker）与 `benchmark-gate`（gate-smoke 基准回归）两个 job，`on.pull_request` 都跑；但只有 `validate` 被 protection 要求。
- **决策已锁定**：#121（P2 平台闸门）、#124（P0-P4 只做内部改造，不产物化）、用户 2026-08-15 决策（approve=1 暂缓；配置幂等脚本 + 文档固化）。
- **业界调研结论**（proposal RIR，full tier）：GitHub 自 review 硬限制 → 单人仓 approve=1 会锁死；Terraform provider 有 drift bug 且过重、裸 gh 脚本无 drift 检测 → 自写幂等脚本 + 独立 JSON + verify 最优；GITHUB_TOKEN 无 admin 权限读 protection → CI verify 不可行，verify 本地跑。
- **grill 关键发现**（`reviews/grill-design.md`，2026-08-15，独立零记忆 subagent）：`PUT .../branches/master/protection` 是**整体替换**接口（org 仓证据：四必需字段缺一即 422、传 null 重置保护），「只传目标字段保持现状」不成立 → D3 改为 GET-modify-PUT；JSON 声明形状（对象 `enabled`）与 PUT 请求形状（布尔）需显式双向变换；`_description` 注释必须递归剥离不进 PUT body；apply 失败需恢复路径（Q1/Q2/Q5 等）。

## Goals / Non-Goals

### Goals

- `master` 合入门禁完整落地：required checks 含 `validate` + `benchmark-gate`（strict）、`required_conversation_resolution` 开启、approve=1 暂缓但触发条件文档化。
- 平台配置「配置即代码」：目标状态声明 `scripts/platform-gate.json` + 幂等脚本 `scripts/platform_gate.py --apply/--verify`，可复现、可 review、防漂移。
- AGENTS.md 记录合入门禁与配置操作命令。
- 配置落地安全顺序：P2 实现 PR 合入后才 `--apply`，避免 PR 自己锁死自己；apply 失败有恢复路径。

### Non-Goals

- 开启 approve=1（暂缓；JSON 里保留触发条件注释与未来开启路径）。
- 引入 Terraform / Pulumi / 任何新依赖（调研否决，理由见 proposal RIR）。
- CI 新增平台 drift verify job（token 权限不足；verify 本地跑）。
- 改 workflow 治理脚本 / AgentLoop / benchmark 代码。
- P3 lark 通知 / P4 声明化引擎。

## Decisions

> 方向决策（approve=1 暂缓、幂等脚本 + 文档固化）已由用户于 2026-08-15 确认。D1-D5 已吸收独立 subagent grill 修正（`reviews/grill-design.md`，Q 标注对应 Open Questions 推荐答案，待用户逐项确认后定稿）。

### D1: 目标状态声明位置与形状——`scripts/platform-gate.json`

- 独立 JSON 声明 `master` 分支保护目标状态，`"schema": "1.0"` 风格对齐 `scripts/flow-policy.json`（单一策略源先例，P0）。
- **归一化目标形状**（Q2，grill BLOCKING）：JSON 存人可读的归一化形状，与 GET 响应同构——`required_conversation_resolution: {enabled: true}`、`enforce_admins: {enabled: true}`；`required_status_checks: {strict: true, contexts: [...]}`（不含派生的 `checks` 数组）；`required_pull_request_reviews: {required_approving_review_count: 0}`。`_description` 注释可出现在 JSON 任意深度。
- 只声明要强制的字段；不声明保持现状的字段（required_signatures / required_linear_history / allow_force_pushes / allow_deletions / lock_branch / block_creations 等均 false）。
- **不入受保护路径清单**（grill 决策 4）：它不是 guard/checker 的执法来源，控制点在 apply；入保护清单反而与「配置走 git PR 流程 review」的 spec 要求矛盾。
- apply 时做**显式双向变换**（PUT 形状）：`enabled` 对象 → 布尔、`required_status_checks` 用 `{strict, contexts}`、`required_pull_request_reviews` **保留 GET 中该对象的可写子字段**（`dismiss_stale_reviews`/`require_code_owner_reviews`/`require_last_push_approval`/`dismissal_restrictions`/`bypass_pull_request_allowances`，若 GET 存在），仅用目标覆盖 `required_approving_review_count`，剔除 `url`（代码层审查 P2：避免未来 UI 开启的 review 子字段被 apply 重置且 verify 白名单查不到）、`restrictions: null`、**递归剥离任意深度 `_description`**（不发进 PUT body）。

### D2: 脚本实现——stdlib-only 单文件 + `gh api`

- `scripts/platform_gate.py`：stdlib-only（argparse + json + subprocess），对齐 guard 的「stdlib-only 单文件」保留决策。
- 调 `gh api` CLI 访问 GitHub API，复用 gh 认证（本地与 CI runner 预装 gh；不引入 requests/pygithub）。
- 仓库 owner/repo 从 `git remote get-url origin` 解析（SSH/HTTPS 格式兼容），或 `--repo owner/repo` 覆盖；**提供 `--repo` 时完全不调用 `git remote get-url` subprocess**（代码层审查 P11，保证强制 `--repo` 的单测零 git 依赖）；单测强制 `--repo` + mock subprocess，避免误打真实仓（Q8）。
- CLI 参数（Q3）：`--config <path>` 指定目标 JSON 路径（默认 `scripts/platform-gate.json`）；脚本**唯一输出 JSON**（与 P1 `flow status` 惯例对齐），`--json` 不承担输入路径语义。
- 错误处理：`gh` 不存在 / 认证失败 / API 非零退出 / 目标 JSON schema 非法 → 明确报错并 exit 2（fail-closed），不执行部分写入。

### D3: apply 语义——GET-modify-PUT（Q1，grill BLOCKING 修正）

- **核心假设修正**：`PUT .../branches/master/protection` 是**整体替换**接口——org 仓证据显示 `enforce_admins`/`required_pull_request_reviews`/`required_status_checks`/`restrictions` 四字段缺一即 422（`"weren't supplied"`），省略字段可能被 API 重置为默认（[community #114292](https://github.com/orgs/community/discussions/114292)、[cli/cli #7338](https://github.com/cli/cli/issues/7338)）。原「只传目标字段、未传保持现状」假设不成立。
- apply = **GET-modify-PUT**：GET 当前 protection → 用声明字段覆盖（merge）→ 剔除只读派生字段 → 按 PUT 请求形状变换（D1）→ PUT 完整 payload（含四必需字段 + `restrictions: null`）。该方案在「保留未传字段」与「重置未传字段」两种 API 语义下都正确。
- **剔除规则**（代码层审查 P9）= 递归删除键名为 `url`、`contexts_url`、`checks` 或任何以 `_url` 结尾的键；`dismissal_restrictions`/`bypass_pull_request_allowances` 按 D1 口径保留（未声明的可写子字段保留自 GET，仅覆盖声明字段）。
- 幂等：GET 结果 merge 声明字段后 PUT，重复 apply 结果一致、无副作用（目标状态已是当前状态时无实际变更）。
- apply 前预检（Q7）：目标 JSON schema 合法性 + gh 可用 + **打印「目标 vs 当前实况」逐字段 diff** 供执行者确认后再 PUT（GET-modify-PUT 下 diff 即「将把什么改成什么」）；**预检复用 `--verify` 的归一化/diff 实现**（代码层审查 P11，避免两套逻辑漂移）；预检失败 exit 2 不写。
- **输出通道与交互性**（代码层审查 P3）：diff 与任何提示输出**一律走 stderr**；stdout 只输出最终 JSON（apply 输出结果对象、verify 输出 `{"ok": bool, "diff": {...}}` 结构）；**脚本不交互**（无 y/n 提示）——执行者看完 stderr diff 后决定是否重跑 `--apply`，保证非交互/自动化可复跑。
- **实现前临时分支实验**（Q1）：在真实仓用临时分支做一次非破坏性 PUT 实验（建临时分支 → PUT → GET 验证 → DELETE 该分支保护 → 删分支），确认个人仓 PUT 的必需字段集与省略布尔行为，再定稿 payload 变换。**已执行（2026-08-16，平台实况验证）**：对 `platform-gate-put-probe` 临时分支（off origin/master）PUT 脚本构造的 payload（`enforce_admins: true` + `required_pull_request_reviews`（GET 可写子字段 + count=0）+ `required_status_checks: {strict, contexts:[validate,benchmark-gate]}` + `required_conversation_resolution: true` + `restrictions: null`）→ **exit 0 成功**；GET 验证 strict=true、contexts=[validate, benchmark-gate]、conversation enabled=true、reviews count=0、enforce_admins=true；GET 响应不含 `restrictions` 键（个人仓语义：PUT 显式传 null 后响应省略该字段）。随后 DELETE 该分支保护（404 确认已删）+ 删除临时分支。结论：个人仓接受完整四必需字段 + `restrictions: null` + `enabled`→布尔变换，payload 形状定稿正确。

### D4: verify 语义（漂移检测）

- `--verify` GET 当前 protection → 归一化后与目标状态比对。
- **白名单比对**（Q4）：只从 GET 提取声明字段，其余一律不读；忽略只读派生字段（`url`/`contexts_url`/`checks` 等）。比较项：`strict`、`contexts`（按排序集合）、`required_approving_review_count`、conversation `enabled`、enforce_admins `enabled`。
- 声明字段在 GET 中缺失或为 null → 视为**漂移（exit 1）**而非崩溃（有单测覆盖 null GET 场景；当前实况 count=0 对象，与目标相等）。
- 输出：逐字段 diff（目标 vs 实况）**走 stderr**；stdout 输出 `{"ok": bool, "diff": {...}}` 结构（P3）；一致 exit 0，漂移 exit 1。
- verify 只读不写。

### D5: approve=1 暂缓建模

- `platform-gate.json` 中 `required_pull_request_reviews.required_approving_review_count: 0`，JSON 内注释（`_description`）写明触发条件：「出现第二个有权限 reviewer（能 approve 且非 PR 作者的身份）时开启：改本文件 count=1 + `--apply`；GitHub 硬限制 PR 作者不能 approve 自己的 PR，单人仓直接开启会锁死合入」。
- 未来开启前必须**用测试 PR 让第二 reviewer 实际 approve 一次**验证有效性（Q6）；锁死应急回滚路径 = 改 JSON `count=0` + `--apply`（幂等，随时可回）。
- AGENTS.md 同步记录该触发条件。

### D6: CI 不新增平台 drift verify job；verify 本地执行

- 调研结论：protection 读写需 admin 权限，GITHUB_TOKEN 无 admin 且不能绕过 branch protection → CI verify 不可行。
- 约定：配置落地（`--apply`）与漂移检查（`--verify`）由主 session（持 admin PAT）本地执行；AGENTS.md 记录命令。

### D7: AGENTS.md 合入门禁描述

- 「常用命令」/文档地图相关段落补：PR 合入必须 required checks 全绿 + conversations 全部 resolve；`python scripts/platform_gate.py --verify` 检查配置漂移；approve=1 触发条件。
- AGENTS.md 不在 flow-policy.json 受保护清单内（无 workflow-events 事件要求），但按文档影响检查规则仍只更新本 change 造成的事实变化。

### D8: spec delta——新增 `platform-gate` capability

- `openspec/specs/platform-gate/spec.md` 新增 requirement：合入平台闸门（required checks 含 validate + benchmark-gate strict、conversation resolution、approve 暂缓触发条件）与配置即代码（platform-gate.json + platform_gate.py --apply/--verify）。
- current spec 用 SHALL（规范性目标）语言描述（对齐 P1 惯例），配 `current_spec_synced` 事件（flow-policy `openspec/specs/` prefix → event_explained）。

### D9: 测试隔离（Q8）

- 所有单测强制 `--repo` 覆盖 + mock `subprocess.run`（gh 与 git 都 mock），避免 verify/apply 单测意外命中真实仓。
- 加「git remote 缺失 / 非 GitHub 格式 → exit 2」测试。

### D10: benchmark-gate 预检（Q9）

- platform-gate PR 合入前核对该 PR 的 `benchmark-gate` check 存在且绿色（它已随 PR 自动跑，零额外成本）；避免合入后 apply 把它设为 required 时全仓立即锁死。
- 在 tasks 5.x 加核对任务。

### D11: 合入后 apply 失败恢复（Q5）

- 合入后主 session 依次执行 `--apply` → `--verify`；verify 通过后才关闭 issue #138，关闭 comment 记录 apply+verify 结果。
- 若 apply/verify 失败，暂不关 issue 并保持 open 记录失败原因与重试命令（apply 幂等，可安全重试）。

## Pre-Implementation Review

独立 subagent design grilling 已完成第一轮（`reviews/grill-design.md`，2026-08-15，run `reviewer-platform-gate-20260815-1`）：6 条 Confirmed Decisions + 10 条 Open Questions（Q1/Q2 BLOCKING 已吸收进 D1/D3）+ 9 条风险。Open Questions Q1-Q10 已全部停轮获得用户确认（2026-08-16，答复记录于 `reviews/grill-design.md` 的 `## User Confirmation`，全部有实质答复）：Q1/Q2 BLOCKING 按推荐（GET-modify-PUT + 显式双向变换 + 递归剥离 `_description` + 临时分支实测）、Q3 `--config` 输入路径、Q4 verify 白名单 null/缺失=漂移、Q5 合入后 apply 顺序红线、Q6 approve=1 暂缓 + 测试 PR 验证 + 应急回滚、Q7 apply 前 diff 预检、Q8 单测强制 `--repo` + mock、Q9 benchmark-gate 核对、Q10 拒绝 `--check-json`（pytest 已直接校验 checked-in JSON，记 backlog）。所有决策已吸收进 D1-D11 并据此定稿。

## Risks / Trade-offs

- **合入自锁（高，已缓解）**：若 `--apply` 在 P2 PR 合入前执行，conversation resolution 开启会把 P2 PR 内未 resolve 的对话变成合入阻塞——缓解：配置落地严格排在合入之后（D11 + tasks 5.6 顺序红线，主 session 监督执行）。
- **PUT 覆盖误伤（高，Q1 已修正）**：PUT 是整体替换接口，原「只传目标字段」假设会 422 或静默重置未声明保护——缓解：GET-modify-PUT + 剔除只读派生字段 + 四必需字段 + `restrictions: null`（D3）+ 临时分支实验验证 + verify 复核。
- **JSON 形状与 PUT 形状不匹配（高，Q2 已修正）**：对象 `enabled` 透传必 422——缓解：显式双向变换 + `_description` 递归剥离（D1）+ 单测覆盖「嵌套 `_description` 不进 PUT body」。
- **apply 失败悬空完成（中，Q5 已缓解）**：apply 失败但 change 已归档、issue 已关 → verify 通过后才关 issue，失败保持 open 记原因（D11）。
- **approve=1 二次自锁（中，Q6 已缓解）**：第二 reviewer 失效 → 测试 PR 验证 + 应急回滚 `count=0` + `--apply`（D5）。
- **benchmark-gate 进 required 后 lockout（中，Q9 已缓解）**：gate 偶发失败 block 全仓 → 合入前核对 PR 的 benchmark-gate 绿（D10）+ admin 可手动调整 + verify 发现 baseline/check 名漂移。
- **verify 崩溃误报（低，Q4 已缓解）**：GET 字段 null/缺失 → 白名单 + 视为漂移 exit 1 而非崩溃（D4）。
- **个人仓 vs org/rulesets 语义差异（低）**：本方案基于 branch protection REST API；若未来迁 org 或启用 rulesets，字段集与模型不同，脚本需重评（R8）。
- **测试误打真实仓（低，Q8 已缓解）**：单测强制 `--repo` + mock subprocess（D9）。

## Testing Strategy

- **payload 构造单测**（D3/Q1）：`--apply` 从「GET 结果 + 声明字段 merge」构造的 PUT payload 符合 GitHub PUT 形状（`enabled`→布尔、四必需字段、`restrictions: null`、无只读派生字段）；幂等（两次 apply 构造同一 payload）；`_description` 递归剥离不进 body（D1/Q2）。
- **verify 比对单测**（D4/Q4）：mock GET 返回实况 → 白名单比对 → 一致 exit 0 / 漂移 exit 1；GET 字段 null/缺失视为漂移不崩溃；contexts 集合比对（顺序无关）；忽略 url/contexts_url/checks。
- **预检与恢复单测**（D3/Q7、D11/Q5）：apply 前打印目标 vs 实况 diff；schema 非法 / gh 缺失 / 认证失败 → exit 2 不写。
- **错误处理单测**（D2/Q3）：gh 不存在、认证失败、API 非零退出 → exit 2 fail-closed；`--config` 路径解析。
- **测试隔离单测**（D9/Q8）：强制 `--repo` + mock subprocess.run（gh/git）；git remote 缺失/非 GitHub 格式 → exit 2。
- **全量 pytest 回归**：不新增依赖，现有测试保持全绿（pre-existing tree-sitter 环境失败除外）。
- **平台实况验证（合入后，D11）**：主 session 本地 `--apply` → `--verify`，确认 required checks 含 validate+benchmark-gate、conversation resolution 开启，通过后才关 issue #138。
