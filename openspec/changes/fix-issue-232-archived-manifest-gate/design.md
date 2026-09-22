# Design — fix-issue-232-archived-manifest-gate

## Context

见 `proposal.md`。核心事实：

- `verify_review_manifest`（`agent/workflow/review_manifest.py:135-175`）当前无条件校验 `tasks_hash`（`:169-170`）。
- 该函数的**生产调用方有三处**：`scripts/check_openspec_artifacts.py:1050`（active 与 `--check-archived` 归档分支共用）、`:1425-1435` 的 `--check-archived` 分支、`scripts/check_phase_done.py:276`（恒以 `archived=False` 调用，A′ 不影响其行为）。三处都依赖「返回 `list[str]` 错误列表」这一签名契约，故 A′ 不得改签名。
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

**Grill 收紧的刻画（已确认）**：这 15 条漂移**不是纯勾选翻转**，而是 **checkbox 行内的实质性文本编辑**——例如 `- [x] …（1813 passed，7 skipped）` → `（1814 passed，7 skipped）`、追加「归档后复跑通过」「PR #142 双 check 均 SUCCESS」等证据、以及 `fix-issue-110` 整条新增任务行。「零条非 checkbox 行」成立**仅因这些编辑恰好发生在以 `- [ ]` 开头的行内**，它不等于「无实质内容变更」。因此 D2 的降级放弃的是「归档语境下检测 `tasks.md` 任何 post-PASS 编辑（含行内描述级篡改）」的能力——该残余风险必须在 spec 降级理由段与 `docs/known-debt.md` 明写（用户 Q5 确认）。

> grill 已确认（Run 2026-09-22-001）：接受「非篡改」这一定性——独立复算 15/15 命中历史版本、非 checkbox 差异行合计 0；同时接受上述残余风险并显式登记。

### D2: A′——归档语境跳过 `tasks_hash`，其余校验保留

`verify_review_manifest` 的 `tasks_hash` 比较前置 `not archived`。归档语境仍校验：manifest 存在性、`schema` / `change_id` / `phase` / `verdict` / 必填字段、`spec_hash`、`report_hash`、`git span`。

理由与取舍（诚实记录）：

- **为什么不能"只忽略勾选状态"**：实测过三种归一化——① 剥离全部 checkbox 行后比对：全仓 43/43 通过，但剥离后只剩 8–18 行**标题/说明**（任务描述本身就在 checkbox 行里），hash 几乎不再能发现"任务列表被篡改" → 这是**假绿**，等于把检查废掉；② checkbox 行归一为 `[TASK]`：仍有 2 条红（那 2 条连描述也改了）；③ 原样：15 红。**勾选标记与任务描述同一行，无法只忽略前者。**
- **因此选择显式降级**：归档语境不假装校验 tasks，而是明确不校验，并在输出中可见（不得静默）。
- **为什么降级是可接受的**：tasks.md 在归档语境下是**贯穿到归档的活文档**（收尾清单本身就在里面）；用它的字节哈希做不可变证据是概念错配。承载"审阅了什么"的实质证据是 `report_hash`（审阅报告原文）与 `spec_hash`（当时已冻结的规格 delta）——两者 15 条全过，且仍被校验。

**降级的可见形式（grill 确认，用户 Q1 拍板）**：note **绝对不得混入 `verify_review_manifest` 的 `list[str]` 返回值**——grill 实跑证明 note 进返回值会被 `_check_review_manifests:1050` 的 `errors.extend` 收走，main 打成 `ERROR:` → **checker exit 1**，A′ 的「可见」立刻退化为「误伤」，15 条红一条不少地继续红（只是文案变了）。落点选在**调用方**：`scripts/check_openspec_artifacts.py` 的 `--check-archived` 分支按归档 change 计数并输出**一行汇总**到 stderr（不逐 change、不进返回值、不改签名）。spec Scenario 措辞相应放宽为「SHALL 在归档校验输出中可见地说明 `tasks_hash` 已跳过（可为汇总行）」。

> 已由 grill 确认 + 用户拍板，无需再议。

### D3: C′——「manifest 最后生成」纪律

manifest SHALL 在该 change 的 tasks.md **最终化之后**生成（含归档 move 之后的最终 head），使 active 语境与将来的归档校验都拿到稳定 hash。

- 该纪律写进 spec（新增 Scenario）+ `docs/development-guide.md`（收尾检查清单）。
- 与既有「审阅 PASS 后不应再改代码」不冲突：收尾勾选**不是改代码**，它是流程推进；纪律只要求「若收尾会改 tasks.md，则 manifest 在其后生成或重绑」。
- 已在做的正确范例：`#199` / `#232` 均在归档 move 后生成 manifest。

**强度（grill 确认，用户 Q2 拍板）**：保留**文档纪律（`docs/development-guide.md` 收尾清单）+ spec 新增 Scenario + D4 的 CI 门**三者叠加，**不新增收尾脚本强制**。active 语境 `tasks_hash` 已被 CI 强制、D4 又让归档语境有非静默降级，二者叠加已闭环；再加脚本层只重复并增加归档摩擦。CI 门兜得住「active 语境 tasks_hash 已强校验」，兜不住的是「manifest 生成后、归档前又改了 tasks.md 而该 PR 的 CI 因故没跑到」——这是残留缺口，由文档纪律承担。

> 已由 grill 确认 + 用户拍板，无需再议。

### D4: CI 增 `--check-archived` 步骤

`.github/workflows/ci.yml` 的 `validate` job 增加一步运行 `check_openspec_artifacts.py --check-archived`（与既有 `--base-ref` 步骤并列）。

- D2 放宽后全仓应 exit 0（立项时已实测 15 红 → 放宽后 0 红，由实现阶段回归锁定）。
- 不加 `--require-base`（该模式与 base-ref 语义绑定，归档步骤不涉及 diff）。

**归属与参数（grill 确认，用户 Q3 拍板）**：放**同一个 `validate` job 的新 step**（复用已装好的 uv/依赖与 `fetch-depth: 0`；独立 job 要重装 env，纯浪费）。参数钉死为 `--check-archived --skip-protected-paths --skip-backlog`：裸跑会用默认 `--base-ref master`，而 CI 检出通常没有本地 `master` 分支 → 打出 `WARNING: could not resolve base ref 'master'`、并重跑一遍 active + backlog 检查；该 WARNING **本地看不到（本工作区 `master` 可解析）、只在 CI 现形**，故必须提前钉参数。`fetch-depth: 0` 够用（`_verify_git_span` 本就是 best-effort，找不到 commit 对象即跳过）。不阻塞无关 PR：A′ 后实测全仓 exit 0（约 9s）。

> 已由 grill 确认 + 用户拍板，无需再议。

### D5: spec 措辞与实现对齐（改措辞，不修实现；grill 确认后修正原案）

spec `dev-workflow-state-machine/spec.md:158` 写「checker SHALL 验证 `head_sha` 匹配当前 `HEAD`」，但实现 `_verify_git_span`（`review_manifest.py:209-232`）实际**只查 `base_sha`/`head_sha` 是否为存在的 commit + `diff_hash` 匹配**，**不校验 `head_sha == HEAD`**。

**grill 实测证明该断言在结构上不可满足**：44 份归档 manifest 中 **0 份** `head_sha == HEAD`（37 份是 HEAD 祖先、7 份不可达），且「生成 manifest」这个动作本身就移动 HEAD（实例：`2026-09-14-subagent-concurrency-queue` 的 manifest 记 `head_sha=ea22b65c`，而写入它的 commit 是 `357cec0`；`fix-issue-110` 记 `8e732b4b` vs `6cd4451`）——除非把 manifest amend 进同一 commit，否则永不成立。

因此本 change 重写该 Requirement 正文时**顺手改措辞**（用户 Q4 拍板，推翻原「逐字保留」案）：delta 的「manifest 字段和 hash 校验」Scenario 删去「`head_sha` 匹配当前 `HEAD`」，保留与实现一致的「`base_sha`/`head_sha` 均为 commit，且 `diff_hash` 匹配 `git diff --binary <base_sha> <head_sha>` 的 sha256」。**反向修实现不可行**（会让 43/43 历史 manifest 转红，见上实测）。原始意图（本想校验 `head_sha == HEAD`，但该断言不可满足）记入 `docs/known-debt.md`，不让意图丢失。

> 已由 grill 确认 + 用户拍板，无需再议。

### D6: spec delta 完整性

按 #199/#232 教训：`openspec archive` 整段替换 Requirement，delta 必须含**变更后的完整正文**。本 change 的 delta 保留「Review evidence manifest」Requirement 的全部既有 Scenario（2 条，**逐字相同**，grill 已实测比对）+ 新增 **2 条** Scenario（「归档 change 的 manifest 校验不因 tasks_hash 漂移而失败」+「active change 的 tasks_hash 漂移仍判失败」），退役项 0。

> 原文误写「新增 1 条」；grill 逐条数出正式 spec 该 Requirement 恰 2 条 Scenario、delta 4 条，**新增数为 2**。归档前需按 2 核对。

## Pre-Implementation Review

非平凡 change（有 spec delta + 非 docs），进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 降级被误读为「归档 manifest 不用管」 | D2 要求降级**可见**（输出说明）+ spec 写明理由；`spec_hash`/`report_hash`/字段/存在性仍强校验 |
| 降级 note 落错位置反而使 A′ 失效 | grill 实测：note 进 `list[str]` → 调用方当 error → exit 1；故落点钉死为调用方汇总一行 stderr（Q1） |
| 假绿：归一化后看似通过实则废检 | D1 实测否定了三种归一化（剥离后只剩标题行）；另有 revision-bound 替代实测 32 过/10 红 → 选显式降级而非伪装校验 |
| 残余风险：归档语境不再检测 tasks.md 任何编辑（含行内描述级篡改） | 已接受并显式登记（Q5）：spec 降级理由段 + `docs/known-debt.md` 写明；`spec_hash`/`report_hash` 承担实质证据 |
| 既有测试 `test_verify_review_manifest_archived_path` 被 A′ 打红 | grill 已实测该测试 FAILED；tasks.md 增列改写该测试（归档 tasks 漂移不报错 + 归档 spec/report 漂移仍报错），**不得删断言** |
| 开启 CI 步骤后阻塞无关 PR | 立项时已实测放宽后全仓 0 红；实现阶段回归锁定；若仍有红则说明 D2 未覆盖，属实现缺陷 |
| CI 第二 step 的 base-ref WARNING 只在 CI 现形 | 参数钉死 `--skip-protected-paths --skip-backlog`（Q3），本地 master 可解析故本地看不到该 WARNING |
| 纪律 D3 只写在文档、缺乏强制 | CI 门（D4）兜底：active 语境 tasks_hash 仍强校验，manifest 绑晚会导致 active 校验失败 |
| delta 静默删既有 Scenario | D6 完整正文 + 归档前核对 Scenario 数（应为既有 2 + 新增 2） |
| `--check-archived` 覆盖面隐含上界 | 实测 90 个归档目录中 4 个 `2026-06-21-*` 老世代因 `parse_change_type` 返回 None 被 `continue` 整段跳过；当前这 4 个均无 `reviews/`，不构成盲区；本 change 仅记录、不处理 |

## Testing Strategy

- `tests/agent/workflow/test_review_manifest.py`（既有文件）新增：
  - 归档态 `tasks_hash` 漂移 → 无错（且 `archived=True` 返回值仍为纯错误列表，**不含 note**）。
  - **同输入 active 态 → `tasks hash mismatch`**（判别性对照，锁住 A′ 只放宽归档）。
  - 归档态 `spec_hash` / `report_hash` 漂移 / 缺 manifest → 仍报错。
- **改写既有测试** `tests/test_openspec_artifact_checker.py::test_verify_review_manifest_archived_path`（:1663-1706）：其 :1700-1706 现断言「归档态 tasks 漂移 → `tasks hash mismatch`」，A′ 下必红（grill 已实测 FAILED）。改为「归档态 tasks 漂移不报错 + 归档态 spec/report 漂移仍报错」，由它承担判别性对照——**不得删断言**。
- 端到端：`check_openspec_artifacts.py --check-archived` 全仓 exit 0，且 stderr 恰含一行归档跳过汇总。
- CI 走查：`validate` job 含 `--check-archived`（断言 step 存在且带 skip 参数）。
- 变异验证：去掉 `not archived` 前置 → 归档用例红；把降级扩到 active → 对照用例红；还原后变绿。
- 全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
