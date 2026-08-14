# Proposal: 方案设计前业界调研门禁（industry-research-gate）

关联跟踪 issue：[#133](https://github.com/Xingkai98/asterwynd/issues/133)（【feature】industry-research-gate：方案设计前业界调研门禁（分流判据））。父 map：[#121](https://github.com/Xingkai98/asterwynd/issues/121)（cross-cutting 规则：方案设计前业界调研门禁）。

## Change Type

- primary: process
- secondary: []

## 需求

1. **规则升级**：AGENTS.md「参考实现调研」节升级为「业界调研门禁」——方案设计（proposal/design）前必须充分调研业界最新实践或框架，含分流判据表；调研渠道从「本地参考仓库对比」扩展为「业界实践/框架调研 + 本地参考仓库对比」两层。
2. **分流三档**：
   - **必调研**（完整 `## Reference Implementation Research`：status/reason/questions/findings/design impact）：架构级改造、引入新框架/新依赖/新协议、对标业界产品、走 grill 的非平凡 change；
   - **浅调研**（proposal 内 findings 一段 + 结论）：常规功能增强、成熟模式局部应用；
   - **可豁免**（须写 reason）：docs-only、bugfix（无新增能力面 + 回归测试）、上游决策锁定（方案引用已关闭决策 issue/架构评审结论，无待定设计项）。
3. **豁免质量门槛**：结构性豁免（docs-only / bugfix / 上游决策锁定）判据清单可机械验证；判断性豁免须引用客观依据（如「与已有模块 X 等价改造」「方案已在 issue #Y 完整讨论并记录」）；占位文本（待确认/待补充等，复用 #123 词表）不计入确认。
4. **checker 机械校验**（复用 #123 阶段感知）：RIR 节引入 `research_tier: full|light|exempt` 必填字段；proposal 阶段只查结构（字段存在且合法）；tasks 全勾时按 tier 校验——full/light 的 findings/design impact 不得命中「自认未完成」词表（沿用 #123），exempt 的 reason 须命中结构性豁免关键词或引用证据（`#<issue>` / 评审文档路径），否则 exit 2。
5. **细节落 `docs/development-guide.md`**：三档判据举例、豁免 reason 写法示范（好/坏例子）、常见误用。

## 背景

- 现状：`openspec/specs/change-documentation/spec.md:190-231` 已有 `Requirement: Reference implementation research gate`——非 docs change 必须维护 RIR 节，checker 做结构检查（status/reason/questions/findings/design impact 非空，不判质量）；#123 内容门槛（tasks 全勾时「自认未完成」短语 exit 2）已随 P0（flow-policy-source）合入 `dev-workflow-state-machine` spec。但调研对象局限**本地参考仓库**（`.dev/reference-repos.txt`），「业界最新实践/框架」调研未成文，无分流判据，豁免仅靠 reason 非空——agent 一句「方案明确」即可豁免，门禁可被绕开。
- 用户 2026-08-14 提出通用规则并确认分流模型（#121 cross-cutting 规则节）：方案设计前充分调研业界最新实践或框架，按改动性质分流，不允许一句「方案明确」豁免。
- flow-policy-source（P0）已按该规则归「上游决策锁定」豁免（归档版 proposal 的 RIR reason 已记录口径，见 `openspec/changes/archive/2026-08-14-flow-policy-source/proposal.md`）。
- 本 change 由用户指示立项（2026-08-14），作为 #121 cross-cutting 规则的落点 change。

## 非目标

- **不做调研质量语义判定**（findings 是否"充分"归 building-review 维度，避免误伤无 URL 优质 findings）——与 #123 口径一致。
- **不要求外网可达**、不强制本地参考仓库存在（不可用时在 RIR 记录不可用事实即可，沿用现有规则）。
- **不改参考仓库机制**（`.dev/reference-repos.txt`、codegraph 调研方式不变）。
- **不新增独立规则文档**（规则在 AGENTS.md，细节在 development-guide，不另开 docs/ 文件）。
- **不改 proposal/design/tasks 既有结构**（只在 RIR 节加 `research_tier` 字段）。
- **不把分流判据做成"checker 自动分类 change 类型"**（自动判断是否架构级/是否 bugfix 不可靠，由 proposal 作者声明 tier + 机械校验 reason 证据，语义归 review）。

## 用户故事

- 新 change 引入新框架/新依赖（架构级）→ proposal 的 RIR 节写 `research_tier: full`，附业界对比 findings 与 design impact；checker 在 tasks 全勾时确认 findings 非「自认未完成」占位。
- 常规功能增强（如给已有工具加参数）→ `research_tier: light`，findings 一段 + 结论即可，不必写完整 research questions。
- 纯 bugfix（无新增能力面，带回归测试）→ `research_tier: exempt` + reason「纯 bugfix，无设计决策，不引入新能力面」。
- agent 想把架构级改造标成 exempt 偷懒 → tasks 全勾时 checker 校验 reason：不命中结构性豁免关键词、无 issue/评审引用 → exit 2，错误信息指明字段与命中情况。
- 方案已被已关闭决策票锁定的 change（如 P1-P4 立项）→ `research_tier: exempt` + reason 引用决策 issue（如 #128/#129），与 flow-policy-source 归档口径一致。

## 行为定义

### RIR 节字段扩展（`openspec/changes/<id>/proposal.md` 与 `design.md` 的 `## Reference Implementation Research`）

- 新增必填字段 `research_tier: full|light|exempt`（放在 status 之前）。
- `exempt` 时：`status` 必须为 `disabled`；`reason` 必须命中结构性豁免关键词（`docs-only` / `bugfix` / `上游决策锁定` / `无设计决策` 等，见 checker 清单）**或**引用证据（`#<数字>` issue 引用、评审文档路径）。
- `full`/`light` 时：`status` 可为 `enabled`（调研完成）或 `disabled`（proposal 阶段在途，reason 说明未完成原因）；tasks 全勾时不得为 `disabled`。

### checker 扩展（`scripts/check_openspec_artifacts.py`，阶段感知复用 #123）

- **proposal 阶段**（结构门槛）：`research_tier` 存在且为合法枚举值；其余照旧（section/status/reason/findings/design impact 非空）。
- **tasks 全勾时**（内容门槛）：
  - `full`/`light`：findings 与 design impact 不得命中「自认未完成」词表（沿用 #123：`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`，`暂无`/`未完成` 不列入）；`status` 不得为 `disabled`。
  - `exempt`：`status` 必须 `disabled`；`reason` 必须命中结构性豁免关键词清单或引用证据模式，否则 exit 2 并指明字段。
- 错误信息统一格式：指明 change id、字段、命中短语/缺失证据。

### AGENTS.md 升级

「参考实现调研」节改为「业界调研门禁」：规则条文（方案设计前充分调研业界最新实践或框架 + 三档分流判据表 + 豁免质量门槛）+ 链接 `docs/development-guide.md`；保留本地参考仓库渠道说明（参考仓库路径写入 `.dev/reference-repos.txt`，不提交）。

### docs/development-guide.md

新增「业界调研门禁」小节：三档判据举例、豁免 reason 写法示范（好/坏例子）、常见误用（占位文本、无证据空话）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程治理（checker） | `check_openspec_artifacts.py`：RIR 结构门槛扩展 `research_tier` 字段校验；tasks 全勾时 exempt reason 证据校验 + full/light status 约束；现有 #123 内容门槛保留复用 |
| Docs | `AGENTS.md`（参考实现调研节升级为业界调研门禁）、`docs/development-guide.md`（新增小节）、change 自身 OpenSpec 文档、存量 active change 的 proposal RIR 节补齐 `research_tier`（add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method，后者 reason 强化命中「无设计决策」） |
| Specs | `openspec/specs/change-documentation/spec.md`（RIR gate requirement 扩展 + 新增分流 requirement） |
| Tests | checker 单元测试新增：tier 解析/豁免证据/阶段感知/回归 |
| CI | checker 行为变严（合规 change 不受影响），无新 check 条目 |
| 明确不受影响 | AgentLoop、工具系统、CLI/Web/benchmark、`workflow_guard.py`（guard 不涉及）、hook 部署机制、参考仓库机制 |

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 本 change 归「上游决策锁定」豁免——决策集来自 #121 cross-cutting 规则（2026-08-14 用户提出并确认分流模型）与本仓库既有实现（change-documentation spec 的 RIR gate + #123 内容门槛 + flow-policy-source 归档版豁免口径），无外部同类「coding-agent 仓库的调研门禁分流规则」可比；业界调研实践已在 #121 架构评审完成（重型 workflow 引擎评审否决、编排工具调研 #126、Herdr/Orca 桌面端调研），本 change 不引入新能力面。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，已确认）。
- research questions: 无（决策已由 #121 锁定）
- findings: 无新增
- design impact: 无
