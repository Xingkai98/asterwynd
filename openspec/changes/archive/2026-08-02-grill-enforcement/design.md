# Design: 流程强制 — batch-grill-me 独立执行 + 写代码前门禁

## Context

当前「必须 batch-grill-me」只是 AGENTS.md 的文字规则。三个 Batch A session 被发现跳过 grill 直接开发，说明文字规则无约束力。对比 subagent 审阅闭环（#90 实现）能拦住"没审阅就提 PR"，是因为它有独立执行者 + 结构化证据 + 机械门禁三要素。本 change 把这三要素对称复刻到 grill 上。

## Goals / Non-Goals

**Goals:**

- grill 由独立零记忆 subagent 执行（非主 agent 自证）。
- 写代码前门禁：无 grill 证据则阻止写操作。
- artifact checker 验证结构化 grill 证据（替换字面检查）。
- `/grill` 命令封装独立 subagent grill 闭环。

**Non-Goals:**

- 不保证 grill 质量（独立执行只保证"有独立 agent 挑战设计"）。
- 不拦截恶意 agent 伪造证据（与审阅相同边界）。
- 不重做 OpenSpec 主干流程。

## Decisions

### Decision 1: grill 证据存 change 目录 grill.md 或 reviews/grill-*.md

**方案**：grill 决策记录存 `openspec/changes/<id>/reviews/grill-design.md`（与 review 证据同目录，随 change 进 PR）。内容含已确认决策列表、未决项、每项的确认来源（独立 subagent run id）。

**备选**：写进 design.md 的 Pre-Implementation Review 节。被拒：design.md 是主 agent 写的，容易与 grill 证据混淆；独立存文件更清晰。

**理由**：与 review 证据（`reviews/building-review.md`）对称，checker 统一从 `reviews/` 目录读。

### Decision 2: 写代码前门禁用 workflow_guard

**方案**：`workflow_guard.py` 在写操作时检查 change 的 `reviews/grill-design.md` 存在。缺失 → `exit 2` 阻止写操作。

**备选**：CI 门禁。被拒：CI 在 PR 时才跑，拦不住"开发过程中直接写代码"。写代码前门禁必须在 PreToolUse hook 层。

**理由**：workflow_guard 已是 PreToolUse hook（Claude Code settings.json），能在 agent 写第一行代码前拦截。

### Decision 3: 门禁触发条件 = 非 docs + 有 spec delta + tasks 有实现项

**方案**：grill 门禁只对"要写代码"的 change 生效。判定：非 docs primary + 有 spec delta（或 tasks 有非文档实现项）。

**备选**：所有 change 都要求 grill。被拒：docs change / 纯占位不需 grill。

**理由**：与 review 门禁的触发条件对齐，避免误伤。

### Decision 4: checker 验证结构化 grill 证据

**方案**：`_check_design_review_task` 改为验证 `reviews/grill-design.md` 存在且含结构化标记（`## Confirmed Decisions` 节 + 至少 N 条决策记录）。不再只检查 tasks.md 字样。

**备选**：保留字面检查。被拒：纸糊的墙（agent 加一行字即过）。

**理由**：结构化决策记录难伪造，且是"真 grill 过"的合理代理。

**前提**：必须处理触发时机与存量 change 迁移（Decision 7），否则 8 个 active 非 docs change 集体红 CI。

### Decision 5: 写操作 → change 的映射机制（grill 门禁的前提）

**方案**：workflow_guard 判断"当前写操作属于哪个 change"用两级机制：
1. **主机制**：`git branch --show-current` 解析分支名，若形如 `<change-id>/<YYYY-MM-DD>` 则 change_id = 前缀。
2. **兜底**：`openspec/changes/` 下仅 1 个 active change 时用它。
3. **都不成立**：门禁不触发（放行）。

**备选**：按 file_path 映射。被拒：代码写在 change 目录外，hook 的 file_path 不含 change_id。

**理由**：分支名编码了 change-id（AGENTS.md 分支规则），是最可靠的映射源。Paseo worktree 目录名随机但分支名仍含 change-id。

### Decision 6: 文档写操作豁免（防死锁）

**方案**：门禁豁免 change 自身文档类写操作：
- `openspec/changes/<id>/{proposal,design,tasks}.md`
- `<id>/specs/**`
- `<id>/reviews/**`（grill 证据写入处）

代码目录（`agent/`、`tests/`、`scripts/` 等）**不豁免**。

**备选**：豁免整个 change 目录。被拒：若代码写在 change 目录内门禁失效。

**理由**：proposal/design/specs 写在 grill 之前，reviews/ 是 grill 证据写入处——不豁免会死锁（鸡生蛋）。

### Decision 7: checker 触发时机 + 存量迁移

**方案**：新 grill 检查触发条件 = 非 docs + 有 spec delta **且 tasks 全部勾选**（与 building-review 门禁对齐）。存量 active change（无 grill-design.md）只要 tasks 未全勾选就不触发，避免 CI 全红；全勾选后要求补 grill 证据。

**备选**：所有非 docs change 都要求。被拒：8 个存量 active change 无证据，CI 立即红。

**理由**：tasks 全勾选是"实现完成"信号，与 #90 的 review 门禁触发一致；存量 change 未完成不误伤。

### Decision 8: 证据格式机器可解析

**方案**：`reviews/grill-design.md` 格式：
```
## Confirmed Decisions
- **决策**: <内容>；理由: <理由>；来源: <subagent run id>
- ...（至少 3 条）
## Open Questions
- <未决项>（可为空）
```
checker 复用 `_is_placeholder_body` 判空，`## Confirmed Decisions` 不得为空且至少 3 条决策。

### Decision 9: 本 change 任务顺序

tasks 5.1（本 change 先 grill）提前到实现任务之前——门禁代码合入前必须先有本 change 的 grill 证据，否则自我拦截。

### Decision 10: 与 update-design-review-method 的冲突消解

`update-design-review-method` 也在改 `_has_design_review_task`（字面检查）。本 change 改为结构化验证，两者相向而行。消解：本 change 实现为"结构化验证优先，字面检查兜底"——`reviews/grill-design.md` 存在且结构完整 → 通过；否则回退到字面检查（tasks.md 含 batch-grill）。这样两个 change 可独立合入，不互相破坏。

## Pre-Implementation Review

经独立 subagent grill（`reviews/grill-design.md`，run id: grill-subagent-independent-design-review）已定稿以下决策：

- **已确认**：独立 subagent 执行 grill、门禁放 PreToolUse hook、替换字面检查、非目标边界。
- **必须修改已落实**：写操作→change 映射（Decision 5）、文档写豁免防死锁（Decision 6）、存量迁移触发收窄（Decision 7）、证据格式机器可解析（Decision 8）、本 change 任务顺序（Decision 9）、与 update-design-review-method 冲突消解（Decision 10）。
- **Open questions**（见下节，待实现前明确）。

## Open Questions（grill 遗留）

1. **重 grill 策略**：grill 证据是否绑定 design.md hash？design 改了要不要重 grill？→ 建议：轻量方案，grill-design.md 记录 design.md 的修订时间或 hash，checker 检测到 design 更新且无对应 re-grill 时 warn（非阻塞）。
2. **多批次 change 的 grill 粒度**：与 review 的 batch-aware 对称，多批次 change 每批进入实现前 grill 该批涉及的 design 变更。
3. **grill manifest 是否必要**：与 review manifest 对称可做，但 grill 证据轻量（run id 即够），首版不做 manifest，后续按需。
4. **主仓库 master 分支门禁失效**：接受——门禁强度 = 分支纪律强度，AGENTS.md 写明"每次开发必须切 `<change-id>/<date>` 分支"。
5. **存量 8 个 active change 迁移**：Decision 7 已解决（tasks 全勾选才触发），不单独迁移。

## Reference Implementation Research

- status: disabled
- reason: 设计复刻 #90 已实现的 subagent 审阅闭环，无需外部参考。

## Risks / Trade-offs

- **[死锁/误拦] → 豁免清单精确（Decision 6），reviews/** 必含、代码目录必不含。**
- **[门禁形同虚设] → 分支推导主机制 + AGENTS.md 写死分支纪律；Bash 非常规写法是 hook 固有局限，文档注明非硬边界。**
- **[CI 集体误报] → 触发收窄到 tasks 全勾选（Decision 7），存量不误伤。**
- **[合入竞态] → 结构化验证优先 + 字面兜底（Decision 10）。**
- **[证据过期] → 记录 design 版本（Open Question 1），warn 不阻塞。**

## Testing Strategy

- 单元测试：workflow_guard grill 检查（有/无证据、分支映射、豁免清单）、checker 结构化验证。
- 回归：全量 pytest + openspec validate + artifact checker。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `AGENTS.md` | 流程文档更新 + 分支纪律 |
| `.claude/commands/grill.md` | 新增独立 grill 命令 |
| `scripts/workflow_guard.py` | 写操作门禁新增 grill 检查 + change 映射 |
| `scripts/check_openspec_artifacts.py` | design review task 检查逻辑 |
| 测试 | workflow_guard / artifact checker 测试 |
