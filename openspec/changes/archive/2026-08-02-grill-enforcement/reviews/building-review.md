# Building Review: grill-enforcement (issue #95, Round 3)

## Verdict

**CHANGES_REQUESTED**

第三轮独立复审（零记忆，不继承任何开发上下文）。审阅对象：`grill-enforcement/2026-08-02` 分支，最近提交 `78d091d`「修复 #95 二轮审阅：grill 决策只认规范列表项格式」。

二轮残留的 **LOW-3 功能性缺陷已完整修复并经 Python 实测确认**：`_extract_grill_decisions` 现在只把规范的 `- **决策**：/：` 列表项计入证据阈值，`### Decision N:` 标题不再计入，决策计数虚高问题消除。但本轮发现 **1 个需修复项（MEDIUM）**：该修复（本身是 bug fix）未按 AGENTS.md「每个 bug fix 必须新增回归测试」与 review-loop「每个修复都加测试」补充回归测试——现有测试对本次修复的核心行为（标题不计入 + 全角冒号匹配）完全无感，回退修复后全部现有测试仍会通过。修复成本极低（一个用例），故判 CHANGES_REQUESTED。

## Round 2 Finding 修复验证

### LOW-3: `_extract_grill_decisions` 只认规范列表项格式 — 已修复 ✓

修复落在 `scripts/check_openspec_artifacts.py:445-462`（`_extract_grill_decisions`）：

- **只认列表项**：`:460-461` 仅匹配 `stripped.startswith("- **决策**：") or stripped.startswith("- **决策**:")`（全角/半角冒号），其余行不计入。去重块已删除——由于标题不再计入，heading+list 重复计数的场景自然消失，去重逻辑不再需要，属正确简化。
- **标题不再计入**：`### Decision N:` / `### 决策` 标题（`:462` 已无该分支）不再进入 `decisions` 列表。commit message 声明与代码一致。
- **docstring 与行为一致**：`:447-452` 明确"Only the canonical list-item format counts… heading form is tolerated for display but does not satisfy the evidence threshold"。

Python 实测（`_extract_grill_decisions`）：

| 输入 | 结果 | 期望 |
|------|------|------|
| 本 change 的 `reviews/grill-design.md`（4 个 `### Decision N:` + 4 条 `- **决策**：` 全角） | **4** | ≥3 ✓ |
| 仅 3 个 `### Decision N:` 标题、无列表项 | **0** | <3 ✓ |
| 1 标题 + 2 条列表项（半角+全角混用） | **2** | 只计列表项 ✓ |
| 空 `## Confirmed Decisions` 节 | **0** | <3 ✓ |

**主仓库不误伤**：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 对全部 active change 无 grill 门禁误报；grill-enforcement 自身唯一报错为 `review manifest missing: .../building-review-manifest.json`——这是审阅闭环中间态（manifest 需 /review-loop 以 PASS 收尾后生成），非缺陷。`_extract_grill_decisions` 全仓库仅 1 处调用（`scripts/check_openspec_artifacts.py:415`），无其他消费方受影响。

**格式一致性确认**：
- `.claude/commands/grill.md:51` 产出模板为 `- **决策**: <内容>；理由: <理由>；来源: <subagent run id>`——与 checker 的列表项格式逐字对齐。
- delta spec `openspec/changes/grill-enforcement/specs/change-documentation/spec.md` 与当前规格 `openspec/specs/change-documentation/spec.md` 均写明 `each `- **决策**: ...；理由: ...；来源: <run id>`, at least 3`——修复与规格一致。

## New Issues（如有）

### NEW-1（MEDIUM）: Round 2 修复缺回归测试，修复行为零保护

`78d091d` 只改了 `scripts/check_openspec_artifacts.py`（1 文件，7 增 18 删），未新增/修改任何测试。本次修复的核心行为因此完全没有测试保护：

- **现有测试全部用半角冒号 `- **决策**:`**（`tests/test_openspec_artifact_checker.py:630-632,653,674-676`），无任何用例覆盖**全角 `- **决策**：`**（真实 grill-design.md 用的就是全角）——若未来回退全角分支，真实证据会从 4 条掉到 0，而测试套件照常全绿。
- **无任何用例覆盖「标题不计入」**：三个 grill 证据测试（`:617-682`）均只有列表项、无 `### Decision N:` 标题；回退到旧的「标题也计入」逻辑后，这些测试结果不变（无标题可计），全部照常通过。即现有测试对本次修复要修的 bug（2 条真实决策算 4 条）100% 无感。
- **违反仓库硬规则**：AGENTS.md「每个 bug fix 必须新增回归测试」为最高优先级规则；review-loop 自身亦要求「回归测试必须: 每个修复都加测试」（`.claude/commands/review-loop.md:152`）并把「是否有回归测试」列为审阅维度（`:24`）。

**建议修复（单一、低成本）**：在 `tests/test_openspec_artifact_checker.py` 新增 1 个用例，覆盖本次修复的两种行为：
1. 仅 `### Decision N:` 标题（无列表项）→ `_check_design_review_task` 报 `Confirmed Decisions 不足 3 条`；
2. 全角冒号 `- **决策**：` 3 条 → 通过（或直接对 `_extract_grill_decisions` 断言两种格式的计数）。

建议断言形态（可直接并入现有 grill 测试区）：

```python
def test_grill_headings_do_not_count_toward_threshold(tmp_path):
    """issue #95：### Decision N: 标题不计入 ≥3 阈值（只认 - **决策**：列表项）。"""
    change = tmp_path / "openspec" / "changes" / "change-ui"
    write_change(change, proposal_for("feature"), design=VALID_DESIGN)
    write_tasks(change, "## 4. Verification\n\n- [ ] Run tests.\n")
    reviews = change / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "grill-design.md").write_text(
        "## Confirmed Decisions\n"
        "### Decision 1: 方向A\n"
        "### Decision 2: 方向B\n"
        "### Decision 3: 方向C\n",
        encoding="utf-8",
    )
    errors = check_change(change)
    assert any("Confirmed Decisions" in e for e in errors), errors
```

（另可加一条全角冒号通过用例，或对 `_extract_grill_decisions` 直接断言 `- **决策**：` 全角 3 条 == 3。）

## Test Results

- 定向：`python3 -m pytest tests/test_openspec_artifact_checker.py tests/test_workflow_guard.py -q` → **51 passed**。
- 主仓库 checker：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 唯一报错 `grill-enforcement: review manifest missing`（审阅闭环中间态，非缺陷）；8 个存量 active change 无 grill 门禁误报。
- Python 实测 `_extract_grill_decisions`：真实证据 4 条（≥3 通过）、标题-only 0、混用只计列表项、空节 0（详见上表）。

## 结论

二轮 LOW-3 的功能性缺陷已修复到位并经实测确认：`_extract_grill_decisions` 只认规范列表项格式，标题不再稀释 ≥3 阈值，与 grill.md 模板、delta spec、当前规格三方一致；无新引入的误报或死锁问题。唯一需修复项是 **NEW-1（MEDIUM）**：本次修复未按仓库硬规则补充回归测试，其核心行为（标题不计入 + 全角冒号匹配）无任何测试保护，回退即静默削弱门禁且 CI 全绿。修复成本为 1 个测试用例，故判定 **CHANGES_REQUESTED**；补测试并复跑定向测试 + 主仓库 checker 后即可收敛为 PASS。
