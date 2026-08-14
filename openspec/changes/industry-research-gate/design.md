# Design: 方案设计前业界调研门禁（industry-research-gate）

## Context

现状事实（file:line 证据）：

- `openspec/specs/change-documentation/spec.md:190-231`：`Requirement: Reference implementation research gate`——非 docs change 的 proposal/design 必须维护 `## Reference Implementation Research`；checker 做结构检查（status 存在、enabled 时 reason/questions/findings/design impact 非空、disabled 时 reason 非空）；**不判质量、不验证本地参考仓库**。
- `openspec/specs/dev-workflow-state-machine/spec.md:553-568`：`Requirement: 内容门槛阶段感知`（#123，随 P0 合入）——tasks 全勾时对 RIR 字段做「自认未完成」短语级匹配（`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`，删 `暂无`/`未完成`），命中 exit 2。
- `check_openspec_artifacts.py`：RIR 检查实现（proposal 阶段结构门槛 + tasks 全勾内容门槛，`_tasks_all_complete` 判定）。
- AGENTS.md「参考实现调研」节：调研对象为**工作区本地参考仓库**（`.dev/reference-repos.txt` + codegraph），触发面「当需要设计或对比某个 coding-agent 能力的实现方式时」。
- #121（2026-08-14）cross-cutting 规则：方案设计前充分调研业界最新实践或框架，按改动性质分流（用户提出并确认分流模型，记录于 #121 正文「Cross-cutting rule」节）。
- flow-policy-source 归档版 proposal 的 RIR reason 已按该规则写「上游决策锁定」豁免口径（`openspec/changes/archive/2026-08-14-flow-policy-source/proposal.md`）。

问题：业界调研未成文、无分流判据、豁免仅靠 reason 非空（「方案明确」即可绕过）、AGENTS.md 触发面过窄。

## Goals / Non-Goals

### Goals

- 方案设计前充分调研业界最新实践或框架成为可执行的通用规则，而非口头要求。
- 分流避免无差别强制（bugfix/方案锁定不背调研负担），且不允许一句话豁免。
- 分流与豁免可机械校验（checker），与 #123 阶段感知机制一致。
- AGENTS.md 与 spec 同步落地，不留双写漂移。

### Non-Goals

- 不做调研质量语义判定（findings 是否充分归 building-review）。
- 不要求外网可达 / 不强制参考仓库存在。
- 不改参考仓库机制与 guard（workflow_guard.py）。
- 不新增独立规则文档；不改 proposal/design/tasks 既有结构（仅 RIR 节加字段）。
- 不做"checker 自动分类 change 类型"（声明 + 证据校验，而非语义推断）。

## Decisions

### D1: 规则落点 —— AGENTS.md「参考实现调研」节升级，细节落 development-guide

- AGENTS.md「参考实现调研」节改名为「业界调研门禁」并升级为三档分流判据表 + 豁免质量门槛；保留本地参考仓库渠道说明（`Reference Implementation Research` 的 findings 可同时含业界调研与参考仓库对比结果）。
- 细节（判据举例、豁免写法示范、常见误用）放 `docs/development-guide.md` 新增小节，AGENTS.md 链接过去——AGENTS.md 是唯一维护入口，只放核心规则。
- 备选：AGENTS.md 另开独立节（否——与现有节重复，两处规则易漂移）；只改 docs 不机械（否——无强制力）。

### D2: 分流三档判据

| 档位 | 判据（命中任一） | 调研深度要求 |
|------|------|---------|
| `full` 必调研 | 架构级改造；引入新框架/新依赖/新协议；对标业界产品；走 grill 的非平凡 change | 完整 RIR（status/reason/questions/findings/design impact 全字段） |
| `light` 浅调研 | 常规功能增强；成熟模式的局部应用 | findings 一段 + 结论；research questions 可省略 |
| `exempt` 可豁免（须 reason） | docs-only；bugfix（无新增能力面 + 回归测试）；上游决策锁定（引用已关闭决策 issue/架构评审结论，无待定设计项） | reason 须引用客观依据，占位不计入 |

- `grill` 触发即 `full`：grill 是"有设计空间"的既有信号（非平凡 change 强制），与其联动避免重复判定。
- 判据表同时写入 AGENTS.md（规则）、development-guide（举例）、spec（Requirement）。

### D3: 豁免质量门槛

- **结构性豁免**（checker 可机械验证）：reason 命中关键词清单——`docs-only` / `bugfix` / `上游决策锁定` / `无设计决策` / `方案已由.*决策` 等，或引用证据（`#<数字>` issue 引用、评审文档路径如 `docs/`、`openspec/changes/archive/`、`reviews/`）。
- **判断性豁免**：reason 须含实质依据**且带引用**（如「与已有模块 X 等价改造（对照 `docs/…` 或 `#<issue>`）」）；「与已有模块 X 等价改造」无引用、仅「方案明确」「待确认」类占位 → 不通过（Q3 确认：不扩展证据路径清单，代码路径如 `agent/`、`scripts/` 不在清单内）。
- 占位词表复用 #123（`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`），保持 `暂无`/`未完成` 不列入（防误伤「暂无参考仓库可用」类合法表述，P0 决策口径）。
- 语义兜底：reason 是否"实质充分"不做硬判（避免误伤），归 building-review 维度；checker 只查"证据存在 + 非占位"。

### D4: `research_tier` 字段与 checker 校验（阶段感知）

- RIR 节新增必填字段 `research_tier: full|light|exempt`，位于 status 之前。
- **proposal 阶段**（结构门槛）：字段存在且合法枚举；其余照旧。
- **tasks 全勾时**（内容门槛）：
  - `full`/`light`：findings 与 design impact 不命中「自认未完成」词表（复用 #123 检查路径）；`status` 不得为 `disabled`（必调研档必须已调研）。
  - `exempt`：`status` 必须 `disabled`；`reason` 命中结构性豁免关键词**或**引用证据，否则 exit 2 指明字段。
- `status` 语义不变（enabled=已调研，disabled=未启用/在途）；tier 是"预期档位"，status 是"实际状态"，两者组合由阶段感知约束（proposal 允许 full/light+disabled 在途，完成时必须闭环）。
- 错误信息统一：change id + 字段 + 命中短语/缺失证据。

### D5: bugfix 判据的机械近似

- checker **不**自动判定"是不是 bugfix"（无新增能力面不可靠机械判），由 proposal 作者声明 `exempt` + reason 写 `bugfix` 类关键词；checker 只校验 reason 命中 + 非占位。
- 语义真实性（是否真无新增能力面）归 building-review 维度；误用（架构改造伪装 bugfix）由 review 发现，发现后记 `docs/known-debt.md` 模式跟踪。
- 这是有意为之的粗粒度：避免 checker 误伤合法 bugfix（如 P0 的 guard 修复），代价是语义部分依赖 review。

### D6: 与现有 gate / spec 的关系

- 保留 `Requirement: Reference implementation research gate` 的名称与结构，MODIFY 其检查要求（结构门槛加 tier 字段）；新增 `Requirement: Research tier triage`（三档判据 + 豁免质量门槛）。
- AGENTS.md 规则文本与 spec 在同一 change 内同步改（同一 PR），避免双写漂移；checker 以 spec 为权威。
- #123 内容门槛（dev-workflow-state-machine spec）不动，本 change 的 checker 逻辑在其路径上扩展。

### D7: 明确不做

- 调研质量语义硬判（无 URL 优质 findings 不误伤——#123 口径）。
- 外网可达性检查 / 参考仓库存在性检查。
- guard（workflow_guard.py）改动——调研门禁是 checker 侧检查，不涉及写拦截。
- 自动 tier 分类（语义推断不可靠）。

### D8: 本 change 自身的 RIR

- `status: disabled` + `research_tier: exempt`，reason 归「上游决策锁定」（决策来自 #121 cross-cutting 规则 + 已关闭决策票 + 本仓库既有实现），与 flow-policy-source 归档口径一致（proposal 已写）。

## Pre-Implementation Review

开发前需完成独立 subagent design grilling（`reviews/grill-design.md`，issue #95 机械强制），并停轮获得用户对 `## Open Questions` 的确认（grill-confirmation-gate，记录于 `## User Confirmation`）。本 change 的分流判据与落点已在 #121 cross-cutting 规则节与 2026-08-14 设计讨论中确认，此处 grilling 聚焦 checker 校验细节（tier 字段与 status 组合、豁免关键词清单、存量 change 兼容）的合并实现问题。

## Open Questions

- **Q1**：`research_tier` 的检查对象——RIR 节同时存在于 proposal 与 design 时，checker 以哪份为准？（proposal 优先，design 为设计细节补充？）
- **Q2**：存量 active change（add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method）补齐 `research_tier` 的时间点——本 change 合入时统一补齐（配事件），还是各自开发时补（避免本 change 触碰其他 change 文档）？
- **Q3**：exempt 结构性豁免关键词初始清单（`docs-only` / `bugfix` / `上游决策锁定` / `无设计决策` / `方案已由.*决策`）是否足够？「本地参考仓库不可用」**不应**单独构成 exempt（业界调研不依赖参考仓库），是否需在清单与文档中显式排除？
- **Q4**：full/light 在 tasks 全勾时 `status` 不得为 `disabled`——「proposal 阶段先 disabled、实现中调研」的 change 完成时必须改 enabled，是否接受该闭环要求（与「禁止占位文本」精神一致）？

## Risks / Trade-offs

- **机械误伤（中）**：tier 声明错误（如把必调研写成 exempt）→ 完成时 checker 报错。缓解：错误信息指明字段与缺失证据；proposal 阶段宽松（结构门槛），开发中可修正。
- **豁免滥用（中）**：reason 凑关键词绕过。缓解：结构性豁免关键词 + 引用证据双重要求 + 占位词表拦截；语义真实性归 building-review（D5 口径）；已确认这是有意粗粒度。
- **AGENTS.md / spec 双写漂移（低）**：同一 PR 内同步修改，checker 以 spec 为权威；AGENTS.md 文本一致性靠文档纪律（归档时检查）。
- **现有 change 兼容（低）**：存量非 docs change 的 RIR 节缺 `research_tier` → proposal 阶段结构门槛报错。缓解：立项扫描存量 active change（当前 `openspec/changes/` 仅 add-minimal-tui-runtime-view / add-worktree-tool / update-design-review-method 三个非 docs active change），合入时统一补齐字段；归档 change 不在检查范围（`--check-archived` 不扩展，沿用 #123 决策）。

## Testing Strategy

- checker 单元测试矩阵：
  - tier 解析：`full|light|exempt` 合法；缺失/非法值 → proposal 阶段报错。
  - exempt 校验：关键词命中通过；`#<issue>` 引用通过；评审文档路径引用通过；占位词命中 → exit 2；空 reason → exit 2。
  - full/light：tasks 全勾 + findings 含「尚未完成」→ exit 2（#123 回归）；status=disabled 在 tasks 全勾 → exit 2；proposal 阶段 full+disabled 不报错。
  - 阶段感知：tasks 未全勾时只查结构，不触发内容门槛。
- 全量 pytest + OpenSpec strict validate + artifact checker。
- 文档一致性检查（人工任务）：AGENTS.md 判据表与 development-guide 示例、spec Requirement 口径一致。

## 实施顺序

1. checker 扩展（tier 字段 + 阶段感知校验 + exempt 证据校验）与单元测试（TDD）。
2. AGENTS.md 节升级 + development-guide 小节。
3. spec delta 合入 + 存量 active change 补齐 tier 字段。
4. 验证（pytest / validate / artifact checker）+ 归档收尾。
