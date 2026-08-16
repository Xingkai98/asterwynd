# Grill: platform-gate 设计追问

## Reviewer

- run id: `reviewer-platform-gate-20260815-1`
- 时间: 2026-08-15
- 性质: 独立零记忆设计评审（不继承任何开发上下文，仅基于 proposal/design/tasks/spec delta/当前 spec/flow-policy.json/ci.yml/实况 API 证据）

## Confirmed Decisions

- **决策**：配置落地顺序红线（PR 合入后才 `--apply`）正确，能防合入自锁。理由：当前实况 `required_conversation_resolution.enabled=false`、required checks 仅 `["validate"]`（本环境 `gh api repos/Xingkai98/asterwynd/branches/master/protection` 实测 2026-08-15，与 proposal Context 一致）；若合入前 apply 把 conversation resolution 置 true，platform-gate PR 自身的 grill/审阅对话会成为合入阻塞。design D3 / tasks 5.6 的「顺序红线」成立，无需改动。来源: `reviewer-platform-gate-20260815-1`
- **决策**：D6「CI 不新增 verify job，verify 本地/主 session 执行」与调研结论一致，成立。理由：branch protection 的读需 admin 权限，Actions `GITHUB_TOKEN` 无 admin 且无法绕过（RIR 引用 community #21356）；本环境能直读实况正是因为持 admin PAT，CI 内不可复现。CI verify 不可行，verify 本地化是唯一可行路径。来源: `reviewer-platform-gate-20260815-1`
- **决策**：D5 approve=1 暂缓建模正确。理由：GitHub 硬限制「PR 作者不能 approve 自己的 PR」在单人仓成立（RIR 的 pyra / Art-World-Hub #278 / metaphorx #1470 / star-fleet #49 实证 + 用户 2026-08-15 决策）；当前实况 `required_approving_review_count=0` 与目标一致（无漂移）。用 `_description` 注释 + AGENTS.md 记录触发条件，未来开启路径（改 JSON + `--apply`）完整。来源: `reviewer-platform-gate-20260815-1`
- **决策**：D1「platform-gate.json 不入受保护路径清单」成立。理由：`scripts/flow-policy.json` 的受保护路径是 guard/checker 的执法来源；platform-gate.json 只是 GitHub 平台配置目标状态，单独改文件不产生平台变化（apply 是独立、需 admin 权限、主 session 执行的步骤），真正的控制点在 apply。入受保护清单反而会与「配置走 git PR 流程 review」的 spec 要求矛盾。来源: `reviewer-platform-gate-20260815-1`
- **决策**：D4 verify 方向正确。理由：只比较声明字段（白名单：`strict` / `contexts` 集合 / `required_approving_review_count` / conversation `enabled` / enforce_admins `enabled`）、忽略只读派生字段（`url` / `contexts_url` / `checks`）、contexts 按集合比对。实测 GET 返回 `required_status_checks.checks=[{context:"validate", app_id:15368}]` 确为派生数组，忽略正确；`contexts=["validate"]` 需与目标 `["validate","benchmark-gate"]` 集合比对。来源: `reviewer-platform-gate-20260815-1`
- **决策**：D7/D8 文档与 spec 影响覆盖完整。理由：AGENTS.md 更新范围（合入门禁描述 + `--verify` 命令 + approve 触发条件）覆盖 proposal 需求第 5 条；spec delta 新增「合入平台闸门」+「平台配置即代码」两个 requirement 与当前 spec「预留能力域」占位写法衔接一致；backlog 已登记（`docs/openspec-change-backlog.md` 条目 + `workflow-events.jsonl` seq2 `backlog_updated` 事件）。来源: `reviewer-platform-gate-20260815-1`

## Open Questions

- **Q1 (BLOCKING)**：D3 的核心假设「PUT 只构造目标字段不传 null，未传字段保持现状」不成立或未验证。GitHub `PUT /repos/{owner}/{repo}/branches/{branch}/protection` 是整体替换接口：org 仓证据显示 `enforce_admins`、`required_pull_request_reviews`、`required_status_checks`、`restrictions` 四字段缺一即 422 `"weren't supplied"`（[community #114292](https://github.com/orgs/community/discussions/114292)、[cli/cli #7338](https://github.com/cli/cli/issues/7338)），传 `null` 会重置该保护（#114292 实测：只设 `lock_branch:true`、其余四字段传 null → 清空已有 checks+reviews）。本仓为个人仓（实测 GET 响应中 `restrictions` 完全缺席），个人仓 PUT 是否也强制四字段、未声明的可选布尔（`required_signatures`/`required_linear_history`/`allow_force_pushes`/`allow_deletions`/`lock_branch` 等）在省略时是否被重置，均未验证。当前实况下这些字段全为 false，误伤为零，但设计理由与 API 行为矛盾，且未来若经 UI 开启 `required_signatures` 等，下一次 apply 会静默关闭它而 verify 不报警（verify 只查声明字段）。
  - **推荐答案**：apply 改为 **GET-modify-PUT**：GET 当前 protection → 合并声明字段 → 剔除只读派生字段（`url`/`contexts_url`/`checks`/`*_url`/`dismissal_restrictions`/`bypass_pull_request_allowances`）→ 按 PUT 请求形状变换（见 Q2）→ PUT 完整 payload。该方案在「API 保留未传字段」与「API 重置未传字段」两种语义下都正确，且天然满足四字段必需约束。实现前必须在真实仓用**临时分支**做一次非破坏性 PUT 实验验证（建临时分支 → PUT → GET → DELETE 该分支保护 → 删分支）。
  - **为什么必须现在定**：这是 apply 的核心数据通路，payload 构造与单测（tasks 2.1/3.2）完全依赖它；按当前设计实现大概率 422 或静默误关保护。
- **Q2 (BLOCKING)**：platform-gate.json 声明形状 vs PUT 请求形状未定。proposal 行为定义写 `required_conversation_resolution: {enabled: true}`、`enforce_admins: {enabled: true}`（对象形态 = GET 响应形状，实测 GET 确为 `{enabled, url}` 对象），但 PUT 请求体这两个字段是**布尔**（`enforce_admins: true`、`required_conversation_resolution: true`）。若把 JSON 原样作为 PUT body 透传，GitHub 会 422（对象无法满足布尔 schema）。另外 D5 的 `_description` 注释嵌在 `required_pull_request_reviews` 对象内，apply 构造 payload 时必须**递归剥离**任意深度的 `_description`，否则会发给 API 导致 422；tasks 2.4 只测「不影响解析」，没测「不进 PUT body」。
  - **推荐答案**：platform-gate.json 存「归一化目标状态」形状（`enabled` 对象形态，人可读、与 verify 比对同构，`_description` 注释保留）；apply 做**显式双向变换**——`enabled`→布尔、`required_status_checks` 用 `{strict, contexts}`（不含 `checks`）、`required_pull_request_reviews` 用 `{required_approving_review_count}`、`restrictions: null`、递归剥离 `_description`；verify 把 GET 响应归一化到同一形状比对。D3/D4 必须写清这个变换，并加「嵌套 `_description` 不进 PUT body」的单测。
  - **为什么必须现在定**：决定 JSON schema（tasks 3.1）、脚本变换逻辑（3.2）与 schema 单测（2.4），是 apply 能成功落地的硬前提。
- **Q3**：`--json` 参数语义冲突。proposal 行为定义「`--json <path>`：指定目标状态 JSON 路径，默认 `scripts/platform-gate.json`」；design D2 写「输出 JSON 格式（`--json` 语义与 P1 `flow status` 对齐：唯一 JSON 输出，不搞双格式）」——同一 flag 两个含义，实现无法同时满足。
  - **推荐答案**：按 design D2 方向——脚本**唯一输出 JSON**（与 P1 惯例一致），`--json` 不再作输入路径；输入路径改用 `--config <path>`（默认 `scripts/platform-gate.json`），同步修正 proposal 与 tasks 3.2 的措辞。
  - **为什么必须现在定**：CLI 接口契约是测试（2.1-2.4）与 AGENTS.md 命令文档的基础，二义性会导致实现时二选一后文档/测试对不上。
- **Q4**：verify 归一化白名单的边界与 null/缺失处理未定义。D4 用「忽略 url/contexts_url/checks」黑名单式列举，未明确「只比较声明字段」的白名单原则；若 GitHub 侧经 UI 禁用 reviews（GET 返回 `required_pull_request_reviews: null` 或对象 count=0），脚本访问 `required_approving_review_count` 会 AttributeError 或误判。
  - **推荐答案**：verify 用**白名单**——只从 GET 提取声明字段，其余一律不读；声明字段在 GET 中缺失或为 null 时视为**漂移（exit 1）**而非崩溃，并有单测覆盖 null GET 场景（当前实况是对象 count=0，与目标 count=0 相等）。
  - **为什么必须现在定**：verify 是防漂移的唯一机械手段，null/缺失处理不当会导致崩溃（误报 exit 2）或漏报。
- **Q5**：合入后 apply 失败的恢复路径缺失。5.6 同时含「PR 合入时关闭 issue #138」与「apply 必须在合入后执行」；若 apply 因认证/API 错误失败，change 已归档、issue 已关、spec 声称「配置已落地」，而实际平台配置未变（漂移）。design 只写了正常路径。
  - **推荐答案**：5.6 改为「合入后主 session 依次执行 `--apply` → `--verify`；verify 通过后才关闭 #138，关闭 comment 记录 apply+verify 结果；若 apply/verify 失败，暂不关 issue 并开 follow-up（或保持 open 记录失败原因与重试命令）。apply 幂等，可安全重试」。
  - **为什么必须现在定**：决定主 session 的操作序列与失败处理，避免「归档完成但配置未落地」的悬空完成态。
- **Q6**：approve=1 未来开启的二次自锁风险缓解不足。触发条件「出现第二个有权限 reviewer」未定义验证手段——第二 reviewer 的 approve 是否真实有效（身份、权限、是否被判无效 approval）未验证；若开启后 bot/human 失效，全部 PR 锁死（count=1 且作者不能 approve 自己的 PR）。
  - **推荐答案**：触发条件注释与 AGENTS.md 补两条：(a) 开启前用**测试 PR** 让第二 reviewer 实际 approve 一次验证有效性；(b) 锁死应急回滚路径 = 改 JSON `count=0` + `--apply`（幂等，随时可回）。「有权限 reviewer」明确为「能 approve 且非 PR 作者的身份（read 以上权限即可 approve）」。
  - **为什么必须现在定**：这是「开了就锁死」的唯一防线，应写进设计而非留给未来。
- **Q7**：apply 前预检的语义安全网不足。D3 说「apply 前 verify 预检（目标 JSON schema 合法性 + gh 可用）」，只防格式/环境错误，不防「JSON 被误改导致的目标状态退化」（如误删 enforce_admins、从 contexts 删掉 validate）。
  - **推荐答案**：apply 前跑 verify 并**打印「目标 vs 当前实况」逐字段 diff** 供执行者确认后再 PUT（配合 Q1 的 GET-modify-PUT，diff 就是「将把什么改成什么」）；至少输出 diff + 回滚提示。
  - **为什么必须现在定**：apply 是 admin 特权写平台，误写面要最小化。
- **Q8**：测试对 git remote 解析与 gh 调用的隔离边界。脚本从 `git remote get-url origin` 解析 owner/repo（D2）；单测运行在真实 git 仓（origin 指向 Xingkai98/asterwynd），若不 mock 该 subprocess，verify/apply 单测可能意外命中真实仓（危险）或依赖环境。
  - **推荐答案**：所有单测强制 `--repo` 覆盖 + mock subprocess.run（gh 与 git 都 mock）；加一条「git remote 缺失/非 GitHub 格式 → exit 2」的测试。
  - **为什么必须现在定**：避免测试误打真实仓，是 tasks 2.1-2.4 的隔离边界。
- **Q9**：进 required 前缺少 benchmark-gate 预检。design 假定 benchmark-gate 稳定（P1 验证过），但未要求 platform-gate PR 自身证明 benchmark-gate 为绿。若该 PR 的 benchmark-gate 恰为红/被跳过，合入后 apply 把它设为 required 会立即锁死全仓。
  - **推荐答案**：platform-gate PR 合入前核对该 PR 的 benchmark-gate check 存在且绿色（它已随 PR 自动跑，零额外成本），在 5.x 加一条核对任务。
  - **为什么必须现在定**：这是「进 required 后 lockout」风险的最前置、零成本缓解。
- **Q10（可选增强）**：CI 无法做平台 drift verify（决策 2 成立），但 `--check-json`（本地校验 platform-gate.json schema，不依赖 gh/admin）可进 validate job，让配置文件本身每次 PR 都被机械校验。
  - **推荐答案**：接受增强——脚本加 `--check-json` 模式，CI validate job 加一步 `python scripts/platform_gate.py --check-json`；若不做，至少记入 backlog。
  - **为什么必须现在定**：决定脚本 CLI 是否加第三个子命令与 CI 改动面（接受则 tasks 需补任务）。

## User Confirmation

- **Q1**: 用户答复：按推荐——apply 改 GET-modify-PUT（读当前→合并声明字段→剔只读派生→PUT 完整 payload）+ 临时分支实测验证；确认时间: 2026-08-16
- **Q2**: 用户答复：按推荐——JSON 存归一化形状（`{enabled:true}`）+ apply 显式双向变换（对象→布尔）+ 递归剥离任意深度 `_description`（不进 PUT body）；确认时间: 2026-08-16
- **Q3**: 用户答复：按推荐——输入路径改 `--config <path>`，脚本唯一输出 JSON（`--json` 不作输入路径）；确认时间: 2026-08-16
- **Q4**: 用户答复：按推荐——verify 白名单比对（只读声明字段），声明字段 null/缺失 = 漂移 exit 1（不崩溃）；确认时间: 2026-08-16
- **Q5**: 用户答复：按推荐——合入后主 session 依次 `--apply` → `--verify`，verify 通过才关闭 issue #138，失败保持 open 记原因；确认时间: 2026-08-16
- **Q6**: 用户答复：approve=1 保持暂缓（用户明确「先不搞评分，绝不出现合入不了的情况」）——触发条件文档化（第二个有权限 reviewer）、开启前测试 PR 验证 reviewer 有效、锁死应急回滚 `count=0`+apply；确认时间: 2026-08-16
- **Q7**: 用户答复：按推荐——apply 前打印「目标 vs 当前实况」逐字段 diff 供执行者确认后再 PUT；确认时间: 2026-08-16
- **Q8**: 用户答复：按推荐——单测强制 `--repo` 覆盖 + mock subprocess.run（gh/git），防误打真实仓；确认时间: 2026-08-16
- **Q9**: 用户答复：按推荐——platform-gate PR 合入前核对 `benchmark-gate` check 存在且绿色（写进 tasks 5.x）；确认时间: 2026-08-16
- **Q10**: 用户答复：按推荐但经代码层自洽性审查（run a0e2031bc9dc83c5b）建议**拒绝并记 backlog**——CI 的 pytest 单测（tasks 2.4）已直接校验 checked-in 的 `scripts/platform-gate.json` schema（每个 PR 随 `uv run pytest -q` 跑），`--check-json` 是对同一静态文件的重复机械校验，边际收益≈0；确认时间: 2026-08-16

## 风险

- **R1（高，BLOCKING）**：PUT 覆盖语义误判 → apply 直接 422（缺 `restrictions` 等必需字段）或静默重置未声明保护（省略字段被 API 重置为默认 false）。design D3 的「未传字段保持现状」与 GitHub 整体替换语义矛盾（见 Q1）。
- **R2（高，BLOCKING）**：JSON 声明形状（对象 `enabled`）与 PUT 请求形状（布尔）不匹配，直接透传必 422（见 Q2）。
- **R3（中）**：合入后 apply 失败 → change 已归档 + issue 已关 + spec 声称已落地，但平台配置未变（见 Q5）。
- **R4（中）**：approve=1 未来开启后第二 reviewer 失效 → 全仓锁死（见 Q6）。
- **R5（中）**：verify 对 GET 的 null/缺失字段处理不当 → 崩溃（误报）或漏报漂移（见 Q4）。
- **R6（低，任务缺口）**：tasks 5.1（归档到 `openspec/changes/archive/`，受保护路径需 `change_archived` 事件）与 5.2（移除 backlog，需 `backlog_updated` 事件）未显式列出 workflow-events.jsonl 解释事件；`flow-policy.json` 明确 `openspec/changes/archive/` prefix → event_explained/`change_archived`、`docs/openspec-change-backlog.md` exact → event_explained/`backlog_updated`。P1 tasks 也未列（靠 5.5 checker 兜底），但建议本 change 显式补入，避免 5.5 报错返工。
- **R7（低，任务缺口）**：tasks 未列 review-loop 任务；checker 对「非 docs + 有 spec delta + tasks 全勾选」的 change 强制 building-review.md + manifest PASS，建议 5.x 补「运行 /review-loop」。
- **R8（低）**：个人仓 vs org 仓/rulesets 语义差异——本方案基于 branch protection REST API；若未来迁入 org 或启用 rulesets（GitHub 正推动 org 迁 ruleset），字段集与模型不同，脚本需重评。RIR 未覆盖该迁移路径。
- **R9（低，口径一致性）**：task 1.7（规格阶段同步 current spec）与 design D8「只描述已实现行为（P2 合入 + 配置落地后成立）」存在张力；本仓 P1 惯例是规格阶段用 SHALL 目标语言同步。建议明确 current spec 用 SHALL（规范性目标）语言，且配 `current_spec_synced` 事件（flow-policy `openspec/specs/` prefix），避免「声称已实现但实际未落地」的表述。
