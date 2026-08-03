# Design: grill 用户确认门禁

## Context

issue #95 的 grill 门禁保证「独立 subagent grill 跑过 + 决策记录存在」，但 `## Confirmed Decisions` 的「确认」语义是「设计方向成立」，不是「用户拍板」。issue #74 开发中，主 agent 的 12 项 grill 裁定标了「待用户确认」却没停轮确认就进了 building——AGENTS.md「不能把自己的推断当作用户确认」被踩线。本 change 把「用户确认」升级为机械强制的可审计证据。

## Goals / Non-Goals

**Goals:**

- grill 之后主 agent 必须停轮，把 Open Questions 逐项抛给用户，收到明确答复前不写代码。
- 用户答复记录进 `grill-design.md` 的 `## User Confirmation` 节。
- workflow_guard（写代码 gate）与 checker（归档 gate）都校验确认完整性。
- 停轮契约写进 AGENTS.md 与 grill skills。

**Non-Goals:**

- 不防恶意伪造（与 #95 边界一致）。
- 不重做主干流程。
- 不追溯迁移存量 change（archive 排除、active 无证据）。

## Decisions

### Decision 1: `## User Confirmation` 节格式（机械可解析）

**方案**：在 `reviews/grill-design.md` 新增 `## User Confirmation` 节，每条确认记录为单行列表项：

```markdown
## User Confirmation

- **Q1**: 用户答复：<用户实际答复文本>；确认时间: 2026-08-02
- **Q2**: 用户答复：<用户实际答复文本>；确认时间: 2026-08-02
```

其中 `**Q<n>**:` 对应 `## Open Questions` 节的第 n 个问题（1-based）。`用户答复：` 后必须是非占位正文（复用 `_is_placeholder_body` 判定）。

**备选**：单独 `user-confirmation.md` 文件。被拒：与 #95 决策记录分文件增加文件类型，且 Open Questions 关联要跨文件解析。

**理由**：与 #95 的 `## Confirmed Decisions` 同文件同模式，checker 用 `_extract_h2_sections` 统一解析；`**Q<n>**:` 序号让「哪个问题被确认」可机械对应。

### Decision 2: checker 校验时机 = tasks 全勾选（归档门禁）

**方案**：`_check_design_review_task` 在 `grill-design.md` 存在时：
1. Confirmed Decisions ≥3（现有）。
2. 解析 `## Open Questions` 节非占位条目数 N、`## User Confirmation` 节确认记录数 M。
3. 若 N>0 且 `_tasks_all_complete(change_dir)`：要求确认记录覆盖全部 Open Questions，否则报「存在未确认的 Open Question，不允许归档」。

**覆盖判定（grill Q5 裁定）**：不用 M≥N 条数匹配（Q1,Q2,Q3,Q3,Q3 可假通过），改用**序号集匹配**——确认记录的 `**Q<n>**:` 序号集合必须包含 Open Questions 节的全部序号。序号从 Open Questions 条目解析（`1.` / `- **Q1**:` / `- Q1` 三种形式），确认记录用 `**Q<n>**:` 前缀。

**备选**：任何状态都要求全确认。被拒：开发中允许带未决项澄清，归档前清零即可。

**理由**：归档 = 全部拍板。开发中 Open Questions 可以挂着（用户边开发边澄清），但归档时每个 Open Question 必须有确认记录。

### Decision 3: workflow_guard 写代码 gate 增强

**方案**：`_grill_evidence_missing(change_id)` 重构判定顺序 + 增强完整性判定：
1. **先判"是否要求 grill"**：docs-only（`primary: docs`）或无 spec delta → return False（不误拦）。
2. 再判证据：`grill-design.md` 缺失 → True。
3. 证据存在但 Open Questions 未全部确认（序号集未覆盖）→ 仍 True（证据不完整）。

**备选**：只查文件存在。被拒：#95 的门禁正是「grill 完未确认就写代码」的漏洞源头。

**理由**：这是「grill 之后必须停下来确认」的**第一道**机械强制——没确认就写不了代码，不等到归档才暴露。

**已知边界（grill Q2/Q3/Q4 裁定，文档化接受）**：
- grill gate 只在 Write/Edit 的 `file_path` 生效，**Bash 写操作绕过**（`_is_write_bash` 启发式）。这是 hook 层固有局限，checker 归档门禁兜底。
- `_current_change_id()` 依赖分支名 `<change-id>/<date>` 纪律；master 直写/非规范分支时门禁静默失效。AGENTS.md 已规定分支命名，接受此缺口。
- workflow_guard 依赖本地 hook 安装（`~/.claude/settings.json` / 项目 `.claude/settings.json`），未安装则门禁不跑；提交侧机械强制仍是 CI 的 artifact checker。

### Decision 4: 两处共享同一提取规则，无存量迁移

**方案**：Open Questions 序号 / 确认记录提取逻辑在 checker 定义，workflow_guard 复刻同规则（两文件独立，不互相 import——workflow_guard 是 hook，需自包含）。提取规则：
- Open Questions 条目：`## Open Questions` 节内，非空、非 `- 无`、非占位的列表项/编号项；解析序号（`1.` 数字 / `- **Q1**:` / `- Q1`）。
- 确认记录：`## User Confirmation` 节内，`- **Q<n>**:` 前缀且 `用户答复：` 后**非未确认 token** 的行（grill Q1 裁定）。
- **未确认 token 集（grill Q1 致命缺口）**：`用户答复：` 后跟 `待确认` / `待主 agent 提交` / `待用户确认` / `TODO` / `pending` 等未拍板标记不得计入确认记录。朴素占位判定（`_is_placeholder_body`）会把这些误收为已确认——grill subagent 的占位行 `用户答复：待主 agent 提交用户确认` 实测会假通过，必须用专用 `_UNCONFIRMED_TOKENS` 集合排除。

**理由**：`iter_change_dirs` 排除 archive（已确认 `scripts/check_openspec_artifacts.py:820-826`），归档 change 不受影响；当前 active changes 无 `grill-design.md`（已确认），无存量迁移负担。两处复刻有漂移风险，用 parity 测试（同一夹具在两函数上断言一致）兜底。

## Pre-Implementation Review

已完成独立 grill 设计追问（本 change 自身，run id `a7221d0f61c5b6c0a`，见 `reviews/grill-design.md`）。Grill 发现 3 个必须修改项（A 早返回吞校验 / B 判定顺序误拦 / C 绕过路径措辞），已整合进 Decisions 2-4。Open Questions 的裁定：

- **Q1 占位判定（致命）**：`用户答复：` 后跟 `待确认`/`待主 agent 提交` 等未拍板 token 不得计入确认记录——grill subagent 的占位行实测会假通过朴素判定。已用专用 `_UNCONFIRMED_TOKENS` 集合排除（Decision 4）。
- **Q2 Bash 绕过**：hook 层固有局限，归档 checker 兜底，文档化接受（Decision 3）。
- **Q3 分支纪律**：`_current_change_id` 依赖分支名，master 直写失效，接受（Decision 3）。
- **Q4 hook 安装**：本地配置，未安装则门禁不跑，CI checker 兜底（Decision 3）。
- **Q5 匹配粒度**：序号集匹配替代 M≥N 条数，防 Q1,Q2,Q3,Q3,Q3 假通过（Decision 2）。
- **Q6 合入冲突**：`update-design-review-method`（active，9/4）改 `_has_design_review_task`（fallback 路径），本 change 改 `_check_design_review_task`（结构化验证）。调用关系为 fallback 被调用，二者可共存；合入顺序建议 update-design-review-method 先合或本 change 以"结构化验证优先、字面兜底"兼容中间态。
- **Q7 hash 绑定**：继承 #95 边界（不防伪造），本轮不新增 design-hash 绑定，标注遗留。

**用户确认状态**：待用户对上述裁定拍板后填入 `reviews/grill-design.md` 的 `## User Confirmation` 节。
- Open Questions 与确认记录用 `**Q<n>**:` 序号对应；条数匹配即可（M≥N），不强求序号一一映射的严格解析。
- 存量无迁移：archive 排除 + active 无证据。

## Reference Implementation Research

- status: enabled
- reason: 设计追问的「用户拍板」强制与 plan mode 审批、PR approval 机制同构；参考 #95 manifest 绑定与 review-loop 的「证据随 change 进 PR」模式。
- research questions:
  - plan mode 的 ExitPlanMode 如何记录用户批准？
  - review-loop 的 review manifest 绑定机制能否对称用于 grill 确认？
- findings:
  - 本仓库 `agent/workflow/review_manifest.py` 把 review report 与 base/head sha、hash 绑定；grill 确认沿用「记录在 change 目录 + checker 机械校验」模式即可。
  - plan mode 的 ExitPlanMode 是 harness 权限门禁，与仓库级 checker/hook 强制两条路径并存，不互相依赖。
- design impact:
  - 确认记录落在 `reviews/grill-design.md` 的 `## User Confirmation` 节。
  - workflow_guard 与 checker 共享提取规则，两处实现保持一致。

## Risks / Trade-offs

- **[确认记录被伪造]** → 与 #95 边界一致：只提高伪造成本 + 拦偶然跳过，不保证真实。真正的「用户拍板」由停轮契约（行为层）保证，文件证据可审计。
- **[Open Questions 计数误判]** → 提取规则保守：`- 无` 与占位不计数；序号 `**Q<n>**:` 只要求前缀匹配，不强制连续。
- **[存量 change 误伤]** → archive 排除已确认；active 无 grill-design.md 已确认；无迁移负担。
- **[开发中未决项卡死]** → checker 只在 tasks 全勾选时强制 M≥N；开发中允许带未决项。

## Testing Strategy

- 单元（checker）：`_extract_open_questions`/`_extract_user_confirmations` 解析；`_check_design_review_task` 的通过/缺失/不完整/未确认全勾选场景。
- 单元（workflow_guard）：`_grill_evidence_missing` 对「存在但未确认」返回 True。
- 回归：既有 grill 测试不回归。
- 收尾：全量 pytest + openspec validate + artifact checker。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `scripts/check_openspec_artifacts.py` | User Confirmation 校验 + 两个 helper |
| `scripts/workflow_guard.py` | `_grill_evidence_missing` 增强 |
| `tests/test_openspec_artifact_checker.py` | 新增校验回归测试 |
| `AGENTS.md` | 停轮契约规则 |
| `~/.claude/skills/batch-grill-me/SKILL.md`、`grilling/SKILL.md` | User Confirmation 节产出 + 停轮 |
