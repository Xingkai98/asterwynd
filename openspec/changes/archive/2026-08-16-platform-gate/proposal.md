# Proposal: 平台闸门（platform-gate，P2）

关联跟踪 issue：[#138](https://github.com/Xingkai98/asterwynd/issues/138)（【feature】platform-gate：P2 平台闸门（benchmark-gate 进 required + conversation resolution + 配置脚本固化））。父 map：[#121](https://github.com/Xingkai98/asterwynd/issues/121)（开发流程可安装化，P2 平台闸门）。

## Change Type

- primary: process
- secondary: []

## 需求

1. **benchmark-gate 进 required status checks**：`master` 分支保护把 `benchmark-gate` 加入 required checks（strict 模式，与 `validate` 并列），CI 全绿才可合入。
2. **required_conversation_resolution 开启**：PR 未 resolve 的 conversations 不能合入。
3. **approve=1 暂缓**（用户决策 2026-08-15）：GitHub 平台硬限制「PR 作者不能 approve 自己的 PR」，单人仓无第二 reviewer，直接开启会锁死合入；文档记录触发条件（出现第二个有权限 reviewer 时开启，改 JSON + `--apply`）。
4. **平台配置固化**（用户决策 2026-08-15）：幂等脚本 `scripts/platform_gate.py`（`--apply` / `--verify`）+ 目标状态声明 `scripts/platform-gate.json`，配置即代码，可复现、可 review、防漂移。
5. **AGENTS.md 更新合入门禁描述**：PR 合入必须 required checks 全绿 + conversations 全部 resolve；approve=1 触发条件。

## 背景

- #121 P2 是「平台闸门」：把 CI 与 review 平台闸门按 #121 决策落地，合入必须满足 required checks + conversation resolution（approve=1 时机由用户定）。
- 当前 `master` branch protection 实况（`gh api repos/Xingkai98/asterwynd/branches/master/protection`，2026-08-15）：
  - `required_status_checks`: strict=true, contexts=["validate"]——`benchmark-gate` job 每个 PR 都跑但未进 required（可绕过）。
  - `required_pull_request_reviews`: required_approving_review_count=0（不需要 approve）。
  - `required_conversation_resolution`: enabled=false（对话可以不 resolve 就合入）。
  - `enforce_admins`: enabled=true（admin 也不 bypass）。
- P0（flow-policy-source，#131）与 P1（flow-event-projection，#136）已合入；P2 不依赖 P1 的代码，但依赖 P0/P1 合入后的仓库治理基线（checker/guard 已强制 OpenSpec 闭环）。
- 用户决策（2026-08-15）：approve=1 暂缓；配置用幂等脚本 + 文档固化。

## 非目标

- **不做 approve=1 的开启**（暂缓；只记录触发条件与开启路径）。
- **不做 P3 编排通知**（lark 卡片与降级链）。
- **不做 P4 声明化引擎**（statechart 等价 pin + 演示，验收线 #124 已定）。
- **不引入新依赖**：不引入 Terraform github provider / Pulumi 等配置即代码工具（调研结论见 RIR：对单人仓过重且有已知 drift bug）；脚本 stdlib + `gh` CLI。
- **不改 AgentLoop / ToolRegistry / workflow 治理脚本**（`workflow_guard.py`、`check_openspec_artifacts.py`、`workflow_state.py`、`event_log.py` 均不动）。
- **CI 不新增 verify job**（GITHUB_TOKEN 无 admin 权限读 protection API，见 RIR；verify 走本地/主 session）。
- **不做可安装产物**（#124：P0-P4 只做内部改造，`flow init` 可安装化留后续 effort）。

## 用户故事

- 用户合入 PR → GitHub 要求 `validate` + `benchmark-gate` 全部通过（不可绕过 benchmark 回归）。
- 用户在 PR 里评论后发现异议 → 未 resolve 前合入被 GitHub 拦截；resolve 后可合入。
- 用户/agent 想确认平台配置没被手动改漂移 → 跑 `python scripts/platform_gate.py --verify`，输出目标 vs 实况差异。
- 未来仓库加入第二个有权限 reviewer → 改 `platform-gate.json` 的 review 配置 + `python scripts/platform_gate.py --apply`，approve=1 生效。

## 行为定义

### 目标状态声明（scripts/platform-gate.json）

独立 JSON 声明 `master` 分支保护的目标状态，schema 对齐 `flow-policy.json` 的 `"schema": "1.0"` 风格。核心字段（对应 GitHub branch protection API）：

- `required_status_checks`: `strict: true`，`contexts: ["validate", "benchmark-gate"]`。
- `required_conversation_resolution`: `enabled: true`。
- `required_pull_request_reviews`: `required_approving_review_count: 0`（approve=1 暂缓），附带触发条件注释。
- `enforce_admins`: `enabled: true`（保持现状）。
- 其他字段（required_signatures / required_linear_history / allow_force_pushes / allow_deletions 等）不声明（保持当前 false 现状）。

### 幂等脚本（scripts/platform_gate.py）

- stdlib-only 单文件，调 `gh api`（复用 gh 认证；本地与 CI runner 均预装 gh）。
- `--apply`：**GET-modify-PUT**——GET 当前 protection → 用声明字段覆盖 → 剔除只读派生字段（`url`/`contexts_url`/`checks` 等）→ 按 PUT 请求形状变换（`enabled` 对象→布尔、`restrictions: null`、递归剥离 `_description`）→ PUT 完整 payload（含四必需字段）；幂等（目标状态已是当前状态时无副作用）；apply 前打印「目标 vs 当前实况」diff 供确认，预检失败 exit 2 不写。
- `--verify`：GET 当前 protection → 白名单归一化比对（只读声明字段，忽略只读派生字段；声明字段缺失/null 视为漂移）→ 输出逐字段 diff；有漂移 exit 1，一致 exit 0。
- `--config <path>`（可选）：指定目标状态 JSON 路径，默认 `scripts/platform-gate.json`；脚本唯一输出 JSON（`--json` 不作输入路径）。
- 错误处理：`gh` 不存在 / 认证失败 / API 错误 / 目标 JSON schema 非法 → 明确报错并 exit 2（fail-closed）。

### AGENTS.md 合入门禁描述

「常用命令」或文档地图相关段落补：PR 合入必须 required checks 全绿 + conversations 全部 resolve；approve=1 触发条件（出现第二个有权限 reviewer 时，改 `platform-gate.json` + `--apply`）；配置漂移检查命令 `python scripts/platform_gate.py --verify`。

### 平台配置落地时机

配置在 P2 实现 PR **合入后**由主 session 执行 `--apply` + `--verify`（合入前 apply 会把 P2 PR 自己锁在 conversation resolution 闸门下——PR 内未 resolve 的对话会阻止合入）。该步骤随 change 的 PR 收尾任务写明。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| GitHub 平台配置 | `master` branch protection：required checks 增加 benchmark-gate、conversation resolution 开启（合入后由 `--apply` 落地）。**实现期已用临时分支做非破坏性 PUT 实验验证**（`platform-gate-put-probe` off origin/master：PUT 脚本构造的完整 payload 成功，GET 确认四必需字段 + `restrictions: null` + enabled→布尔均正确，随后 DELETE 保护 + 删分支，零残留） |
| scripts/ | 新增 `platform_gate.py`（stdlib-only）+ `platform-gate.json`（目标状态声明） |
| Docs | AGENTS.md（合入门禁描述 + verify/apply 命令 + approve 触发条件）、change 自身文档（design/grill） |
| Specs | 新增 `openspec/specs/platform-gate/spec.md`（合入平台闸门 + 配置即代码 requirement） |
| 测试 | `tests/test_platform_gate.py` 单测（payload 构造、verify 比对、幂等、错误处理、schema、--repo 短路）+ 全量 pytest 回归 |
| 明确不受影响 | AgentLoop、工具系统、Web/TUI、benchmark 运行代码、workflow 治理脚本（guard/checker/workflow_state/event_log）、`flow-policy.json` 受保护策略表。实现期未发现新的额外影响面（脚本自包含，仅 scripts/ + tests/ + 文档/spec） |

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 本 change 走 grill（非平凡 process change，有 spec delta 与脚本交付），按判据命中「走 grill 的非平凡 change」→ full 必调研。调研对象为 GitHub 平台能力（branch protection API、required checks、conversation resolution、approve 限制）与「配置即代码」业界实践。
- research questions:
  1. GitHub branch protection REST API 的字段语义与幂等性？PUT 是声明式覆盖还是增量？
  2. 单人仓（PR 作者唯一操作者）能否开启 required approving reviews？自 review 限制是什么？
  3. 业界「branch protection as code」实践对比：Terraform github provider vs 裸 `gh api` 脚本 vs 自写幂等脚本，哪个适合单人小仓？
  4. GitHub Actions 的 GITHUB_TOKEN 能否读 protection API / 绕过 branch protection？CI 里做 verify 是否可行？
- findings:
  1. **Branch protection API**：`PUT /repos/{owner}/{repo}/branches/{branch}/protection` 为声明式覆盖接口，调用方需持有 repo admin 权限（或 ruleset 管理权限）。返回的 `checks` 数组与 `contexts` 并列（checks 含 app_id），`strict: true` 要求分支在合并前与上游同步（「Require branches to be up to date」）。字段以「enabled / 完整结构」表达，未显式传 null 的字段在 API 语义下保持现状——脚本因此只构造目标字段即可，不做全量重写。
  2. **自 review 限制**：GitHub 平台硬限制「PR author cannot approve their own PR」（错误 `Can not approve your own pull request (addPullRequestReview)`）。多仓库真实记录佐证：单人维护者开启 required approvals 会锁死发布/维护（[pyra MAINTAINING.md](https://github.com/treyorr/pyra/blob/main/MAINTAINING.md)）；自动化流程用与作者同身份的 token approve 必然失败（[Art-World-Hub #278](https://github.com/ilv78/Art-World-Hub/issues/278)、[metaphorex #1470](https://github.com/metaphorex/metaphorex/issues/1470)、[star-fleet #49](https://github.com/grid-xxx/star-fleet/issues/49)）。结论：单人仓 approve=1 应暂缓，等第二 reviewer（人或独立 bot 身份）出现再开——与用户决策一致。现有绕过方案（独立 bot 账号 + PAT、或 `exclude_contributor_approvals` 未来特性）均为额外身份基建，本 change 不做。
  3. **配置即代码工具对比**：
     - Terraform `github_branch_protection` / `github_repository_ruleset`：多仓库标准化强（[systemshardening 实践](https://www.systemshardening.com/articles/cicd/repo-policy-as-code/)），但 provider 有已知 drift bug：空 contexts 应用静默失败（[integrations/terraform-provider-github#1213](https://github.com/integrations/terraform-provider-github/issues/1213)）、无变更时 persistent drift（[#2243](https://github.com/integrations/terraform-provider-github/issues/2243)）、strict 回归（[#880](https://github.com/integrations/terraform-provider-github/issues/880#1)）、matrix check 名不匹配（[#2417](https://github.com/integrations/terraform-provider-github/issues/2417)）；且对本单人仓引入 Terraform 状态管理明显过重，违反「不引入新依赖」的约束。
     - 裸 `gh api` 脚本：简单可行（OneUptime 用 `gh api .../protection --input -` 发 JSON），但是一次性调用，无 drift 检测、无可复现校验（[OneUptime blog](https://raw.githubusercontent.com/OneUptime/blog/refs/heads/master/posts/2026-02-26-implement-code-review-workflow-config-changes/README.md)）。
     - **本 change 方案**：自写 stdlib-only 幂等脚本 + 独立目标 JSON + `--verify` 漂移检测，正好补上裸脚本缺的 drift 检测，又避开 Terraform 的重量依赖与已知 bug；JSON 目标状态可 diff、可 review，契合 #121 声明化方向（为 P4 铺垫）。
  4. **GITHUB_TOKEN 权限**：branch protection 的**读与写都需要 admin 权限**，而 Actions 的 `GITHUB_TOKEN` 默认无 admin 权限且**无法绕过 branch protection**（不能 push 受保护分支；即便加入 bypass actor 列表也无效，需 PAT/GitHub App token，见 [community discussion #21356](https://github.com/orgs/community/discussions/21356)）。`pull-requests: write` 允许 approve PR，但 approval 只算作 review，不构成绕过。结论：CI 内做 `--verify` 不可行（token 权限不足），verify 走本地/主 session（持有 admin PAT）；approve=1 若未来开启，CI bot 自动 approve 方案在技术上可行（`pull-requests: write`）但需要额外身份与权限设计，不在本 change 范围。
- design impact: 上述 4 点直接决定本 change 设计——脚本自写（不引入 Terraform）、目标状态独立 JSON（可 diff 可 review）、verify 本地执行（CI 不加 verify job）、approve=1 暂缓并在 JSON 中保留触发条件注释、`--apply` 使用 PUT 声明式覆盖且只构造目标字段。
- 本地参考仓库不可用：`.dev/reference-repos.txt` 不存在（已确认），无本地参考仓库可对比；业界实践调研以 GitHub 官方文档语义 + 上述公开 issue/文章为准。
