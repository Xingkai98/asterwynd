# Design — fix-issue-232-archived-manifest-gate

## Context

见 `proposal.md`。核心事实：

- `verify_review_manifest`（`agent/workflow/review_manifest.py:135-175`）当前无条件校验 `tasks_hash`（`:169-170`）。
- `--check-archived` 已实现（`scripts/check_openspec_artifacts.py:1406`），但 `.github/workflows/ci.yml:62` 未带 → 归档脱离校验。
- 全仓实测：43 个归档 change 有 `building-review.md`，其中 43 个都有 manifest（**无缺件**）；`--check-archived` 失败 15 条，**全部**是 `tasks hash mismatch`，无其它错误类型。
- spec `dev-workflow-state-machine/spec.md:157` 钉着「checker SHALL 验证 `report_hash`、`tasks_hash`、`spec_hash`」→ 本 change 必须走 spec delta。

## Goals / Non-Goals

**Goals**

- 开启归档校验门后全仓 green，且该绿**诚实**（不靠改写历史、不靠静默跳过）。
- `tasks_hash` 在它真正有意义的语境（active）保持强校验。
- 立一条纪律防复发。

**Non-Goals**

- 不重绑/改写 15 条归档 manifest（B′ 否决）。
- 不改写通道（盲区 A 已完成）、不改 `change_dir_for`。
- 不动 `diff_hash` / `head_sha` 校验逻辑（见 D5）。
- 不加 manifest 新字段或 schema 版本。

## Decisions

### D1: 15 条漂移的性质——实测穷举定性（本 change 的事实基础）

对每一条失败 change，穷举其 `tasks.md` 的全部历史版本找出与 manifest `tasks_hash` 相符的那一版，与当前归档版逐行 diff：

| 结论 | 实测 |
|------|------|
| 失败条数 | **15**，全部为 2026-08-03 ~ 2026-09-14 的 change |
| 错误类型 | **全部** `tasks hash mismatch`；`spec_hash` / `report_hash` / `git diff` 全过 |
| 差异性质 | **15/15 的差异行全部落在 checkbox 行**（勾选翻转、同行描述随之更新、一条纯新增 checkbox 行），**零条非 checkbox 行** |
| 对照 | 新近 change（`#199` / `#232` / `#213`）全部通过——它们在收尾改动后**重绑了 manifest** |

根因：manifest 在**审阅 PASS 时**生成（tasks 未全勾），收尾阶段（spec sync / 归档 / backlog 移除）会再勾几项 → `tasks_hash` 必然漂移。**这不是篡改，是流程顺序与哈希语义的固有冲突。**

> 待 grill 确认：是否接受「15 条全部良性」这一定性（可复现方式已写入 diagnosis 的既有证据链）。

### D2: A′——归档语境跳过 `tasks_hash`，其余校验保留

`verify_review_manifest` 的 `tasks_hash` 比较前置 `not archived`。归档语境仍校验：manifest 存在性、`schema` / `change_id` / `phase` / `verdict` / 必填字段、`spec_hash`、`report_hash`、`git span`。

理由与取舍（诚实记录）：

- **为什么不能"只忽略勾选状态"**：实测过三种归一化——① 剥离全部 checkbox 行后比对：全仓 43/43 通过，但剥离后只剩 8–18 行**标题/说明**（任务描述本身就在 checkbox 行里），hash 几乎不再能发现"任务列表被篡改" → 这是**假绿**，等于把检查废掉；② checkbox 行归一为 `[TASK]`：仍有 2 条红（那 2 条连描述也改了）；③ 原样：15 红。**勾选标记与任务描述同一行，无法只忽略前者。**
- **因此选择显式降级**：归档语境不假装校验 tasks，而是明确不校验，并在输出中可见（不得静默）。
- **为什么降级是可接受的**：tasks.md 在归档语境下是**贯穿到归档的活文档**（收尾清单本身就在里面）；用它的字节哈希做不可变证据是概念错配。承载"审阅了什么"的实质证据是 `report_hash`（审阅报告原文）与 `spec_hash`（当时已冻结的规格 delta）——两者 15 条全过，且仍被校验。

> 待 grill 确认：降级的**可见形式**——是仅在字段缺失时输出提示，还是每次归档校验都输出一行说明？（倾向：仅在归档校验路径输出一行说明性 note，不视为 error。）

### D3: C′——「manifest 最后生成」纪律

manifest SHALL 在该 change 的 tasks.md **最终化之后**生成（含归档 move 之后的最终 head），使 active 语境与将来的归档校验都拿到稳定 hash。

- 该纪律写进 spec（新增 Scenario）+ `docs/development-guide.md`（收尾检查清单）。
- 与既有「审阅 PASS 后不应再改代码」不冲突：收尾勾选**不是改代码**，它是流程推进；纪律只要求「若收尾会改 tasks.md，则 manifest 在其后生成或重绑」。
- 已在做的正确范例：`#199` / `#232` 均在归档 move 后生成 manifest。

> 待 grill 确认：纪律的措辞落点与强度（是否要求收尾脚本层面强制，还是文档纪律 + 本 change 的 CI 门兜底）。

### D4: CI 增 `--check-archived` 步骤

`.github/workflows/ci.yml` 的 `validate` job 增加一步运行 `check_openspec_artifacts.py --check-archived`（与既有 `--base-ref` 步骤并列）。

- D2 放宽后全仓应 exit 0（立项时已实测 15 红 → 放宽后 0 红，由实现阶段回归锁定）。
- 不加 `--require-base`（该模式与 base-ref 语义绑定，归档步骤不涉及 diff）。

> 待 grill 确认：放 `validate` job 还是独立 job；是否需要 `fetch-depth: 0`（校验含 git span，`validate` job 已是 `fetch-depth: 0`，沿用即可）。

### D5: 顺带记录的既有口径债（本 change 不修）

spec `dev-workflow-state-machine/spec.md:158` 写「checker SHALL 验证 `head_sha` 匹配当前 `HEAD`」，但实现 `_verify_git_span`（`review_manifest.py:209-232`）实际**只查 `base_sha`/`head_sha` 是否为存在的 commit + `diff_hash` 匹配**，**不校验 `head_sha == HEAD`**。本 change 重写该 Requirement 正文时**逐字保留**该句（不借机改动），把实现缺口记入 `docs/known-debt.md` 另案。

> 待 grill 确认：是否同意「不在本 change 修」——修它会让所有 head_sha 不等于当前 HEAD 的历史 manifest 转红（数量未测），风险面大于本 change 目标。

### D6: spec delta 完整性

按 #199/#232 教训：`openspec archive` 整段替换 Requirement，delta 必须含**变更后的完整正文**。本 change 的 delta 保留「Review evidence manifest」Requirement 的全部既有 Scenario（2 条）+ 新增 1 条归档 Scenario，退役项 0。

## Pre-Implementation Review

非平凡 change（有 spec delta + 非 docs），进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 降级被误读为「归档 manifest 不用管」 | D2 要求降级**可见**（输出说明）+ spec 写明理由；`spec_hash`/`report_hash`/字段/存在性仍强校验 |
| 假绿：归一化后看似通过实则废检 | D1 实测否定了三种归一化（剥离后只剩标题行）；因此选显式降级而非伪装校验 |
| 开启 CI 步骤后阻塞无关 PR | 立项时已实测放宽后全仓 0 红；实现阶段回归锁定；若仍有红则说明 D2 未覆盖，属实现缺陷 |
| 纪律 D3 只写在文档、缺乏强制 | CI 门（D4）兜底：active 语境 tasks_hash 仍强校验，manifest 绑晚会导致 active 校验失败 |
| delta 静默删既有 Scenario | D6 完整正文 + 归档前核对 Scenario 数 |

## Testing Strategy

- `tests/agent/workflow/test_review_manifest.py`（既有文件）新增：
  - 归档态 `tasks_hash` 漂移 → 无错（且输出含降级说明）。
  - **同输入 active 态 → `tasks hash mismatch`**（判别性对照，锁住 A′ 只放宽归档）。
  - 归档态 `spec_hash` / `report_hash` 漂移 / 缺 manifest → 仍报错。
- 端到端：`check_openspec_artifacts.py --check-archived` 全仓 exit 0。
- CI 走查：`validate` job 含 `--check-archived`。
- 变异验证：去掉 `not archived` 前置 → 归档用例红；把降级扩到 active → 对照用例红。
- 全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
