# Building Review: evaluation-task-spec

## Reviewer
- run id: independent-building-review-evaluation-task-spec-2026-08-17
- 时间: 2026-08-17
- 基线: base=4dc6289 head=f71f1bff50b329191d8d31b6124f53755118b4fe
- 审阅方式: 独立零记忆审阅；代码事实均经本 reviewer 实际读代码 + 在 base_commit 建临时 worktree 红绿复现 + 全量测试验证。

## Verdict

**CHANGES_REQUESTED**

核心实现（schema 扩展、任务集覆盖矩阵、B 轨 5 任务、018/020 补 gold.patch、022 结构校验、Verified 子集基建、spec delta 同步）全部真实存在且经红绿/全量验证通过；唯一需修复的中等问题为**文档任务数口径 off-by-one（26 vs 实际 27；36 vs 实际 37）**，该口径正是本 change tasks 8.3 声称已修正的对象，且 `benchmarks/tasks/README.md` 头部「26」与其自身 A22+B5=27 分解自相矛盾。修复成本极低（4 处文档数字），不阻塞整体。

## Tasks Verification

> `[x]` 逐条验证；`[~]`（5.1 部分完成）与 `[ ]`（9.x 收尾任务）按标注评估，不算缺陷。

### 1. 规格与设计定稿
- task 1.1 proposal 完整: ✅ `openspec/changes/evaluation-task-spec/proposal.md` 含 Change Type（feature+process）、Impact Analysis、RIR（research_tier=full，findings 记录本地 `.dev/reference-repos.txt` 不存在 + 引用 R1/R2/R3/G1 ticket 作为替代依据）。
- task 1.2 grill 独立 subagent 审视: ✅ `reviews/grill-design.md` 存在，核验 D1–D8 与开放问题 OQ-B1/OQ-V1，Confirmed Decisions 5 条（≥3 达标）。
- task 1.3 停轮用户确认: ✅ `grill-design.md` `## User Confirmation` 含 OQ-B1/OQ-V1/OQ-1~OQ-4 共 6 条用户答复（2026-08-17「按推荐」），每条配场景说明。
- task 1.4 spec delta 与 proposal 一致: ✅ delta 3 REVISED + 12 ADDED 与 proposal Modified Capabilities 描述一致，向后兼容扩展（既有字段语义不变）。

### 2. 任务 schema 扩展
- task 2.1 scenario 字段 + 缺省兼容: ✅ `benchmarks/task_schema.py:8` SCENARIOS、`:27` `scenario: str | None = None`、`:83-86` validate 枚举校验；`from_dict` 用 `.get()` 缺省（:60），未填不报错。测试 `tests/benchmark/test_task_schema.py:168`（缺省 None 兼容）。
- task 2.2 difficulty 3 档归一化 + validate + swebench 映射: ✅ `task_schema.py:9` DIFFICULTIES、`:87-88` validate；10 个 swebench fixture `difficulty` 已从 `<15 min fix` 迁移为 `easy`（OQ-3 方案 A，如 `benchmarks/tasks/swebench-psf__requests-1142/task.json`），gate-smoke `trivial`→`easy`。
- task 2.3 schema 扩展单测: ✅ `tests/benchmark/test_task_schema.py` 覆盖场景枚举接受/拒绝（:157-165）、difficulty 归一化拒绝 `<15 min fix`/`trivial`（:181-185）、缺省兼容（:199-209）、旧任务 JSON 向后兼容（:204）。
- task 2.4 manifest track + 套件级覆盖矩阵: ✅ `benchmarks/tasks/manifest.json`（version/capabilities 7 列/coverage 27 任务）+ `benchmarks/task_set.py` `Manifest`/`validate_coverage`；`track` 单一事实源在 task.json（OQ-1），manifest 只声明覆盖矩阵。

### 3. 存量 26 去留 / 重打标
- task 3.1 4 陈旧任务重写/改写为 B 轨: ✅ 002/004/005/021 均 `track: "B"`、`base_commit=4dc6289`（master HEAD），gold.patch/test.patch 在 base 干净应用，**红绿全部复现**（见 Test Results）。
- task 3.2 2 空 gold.patch 补参考实现: ✅ 018 从合入 commit `3ffa0cb`、020 从 `dfd1e11` 提取；在各自 base（594fa47/dfbd831）建 worktree 验证 gold/test patch 干净应用 + **红绿复现**。
- task 3.3 022 弱评估补结构校验: ✅ `tests/benchmark/test_collab_audit_structure.py`（test.patch 新增）断言三章节顺序/实质内容/真实字段；引用的 `LLMSummarizer`/`TruncationSummarizer`（`agent/context/summarizer.py`）与 `max_tokens`/`compaction_gap`/`compact_trigger_tokens`（`agent/memory/manager.py`）在 base 7c6fc3e 真实存在，可满足。
- task 3.4 其余 22 重打标: ✅ 27 个本地任务 task.json 全部含 `scenario`+`difficulty`；难度分布 26 存量 = easy 9/medium 13/hard 4（+b01 hard=5），与 design 口径一致（重打标未改难度）。
- task 3.5 存量 smoke 不回归: ✅ 本 reviewer 实测 `asterwynd benchmark gate-smoke-001 --agent fake` → `Tasks: 1 | passed: 1`；gate-smoke-001/002 元数据迁移后正常。

### 4. B 轨任务（context-planning 优先）
- task 4.1 B 轨清单 5 条收敛: ✅ 4 重写（002 沙箱命令审计字段/004 CLI --list-tasks/005 mv-cp 工作区边界/021 LSP language 覆盖）+ 1 新增（asterwynd-b01 结果页按 task_family 分组）；tasks.md 4.1 如实披露「较目标 12–16 收敛」及原因。
- task 4.2 每任务测试先行 + 红绿: ✅ 全部 5 条在 base 建 worktree 验证 base+test 红、+gold 绿（详见 Test Results）。
- task 4.3 覆盖矩阵机械校验: ✅ 实测 `Manifest.validate_coverage` → missing_capabilities=[]、missing_scenarios=[]、unknown_task_ids=[]、is_complete=True（7 能力列 + 5 场景列全 ≥1，verified 排除）。
- task 4.4 B 轨 smoke: ✅ 本 reviewer 实测 `asterwynd benchmark asterwynd-b01 --agent fake` → 任务被发现/执行、无崩溃（`failed: 1` 为 fake 不实现 gold 的预期结果）。

### 5. Verified 50 子集接入
- task 5.1 `[~]` 部分完成（生成阻塞）: ✅ 按标注评估。`benchmarks/swebench_subset.py` 已交付 build_subset（配比 requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8 + KNOWN_BAD/重 repo/空 test_patch 过滤）+ validate_fixture + gold_check + CLI；40 条新 fixture 未生成（huggingface 不可达）已如实披露。KNOW_BAD_ENTRIES 为空（数据环境注入），披露充分。
- task 5.2 fixture 元数据校验: ✅ `validate_fixture` 全字段校验；`tests/benchmark/test_swebench_subset.py:93` 实测现有 10 fixture 全部通过。
- task 5.3 L1 本地轻量路径: ✅ `task_schema.py:91-104` swebench+local 允许免 instance 元数据；`test_task_schema.py:212` 覆盖。
- task 5.4 L3 gold_check 脚本: ✅ 实测 `python benchmarks/swebench_subset.py --gold-check benchmarks/tasks/asterwynd-018-warning-passes` → exit 0（嵌套 worktree 创建/应用 gold/test.patch/跑 test_command 全链路可用）。
- task 5.5 污染披露: ✅ delta spec「SWE-bench 污染披露」Requirement + manifest 第 5 行注记（KNOWN_BAD 过滤/现有 10 fixture 偏置/版本钉住），结果页渲染归 C2/C3。

### 6. 反作弊披露
- task 6.1 A 轨泄漏披露: ✅ `manifest.json` `anti_cheat_disclosure`（source/time_range/training_cutoff/positioning「回归基线、非公平评测」+ track_a_note 完整 git 历史泄漏面）。
- task 6.2 shallow/mirror 加固留后续: ✅ design.md D7 记触发条件（结果页被外部引用/面试解读为能力上限/需与外部基准直接比较），本期不实现。

### 7. spec delta 落定（含 C2 需求文本）
- task 7.1 能力分层口径修订: ✅ delta + 正式 spec 同步（`任务支持显式能力分层`：scenario×difficulty 双标签 + 套件级覆盖矩阵，SHALL NOT 任务级正交）。
- task 7.2 pass^k 改名 + 三分定义: ✅ 正式 spec:244-259 含 pass@1/pass@k/pass^k 三分 + n/k 有效性条件。
- task 7.3 新增任务 schema/三来源/Verified/反作弊 Requirement: ✅ 正式 spec 含全部。
- task 7.4 M1–M11 Requirement + 9 个「实现归 C2」注记: ✅ 正式 spec 9 处「实现归 C2 evaluation-metrics」（grep 计数 9）。
- task 7.5 delta 同步正式 spec: ✅ 15/15 Requirement 名称在 `openspec/specs/benchmark/spec.md` 全部命中；`workflow-events.jsonl` seq=2 `current_spec_synced`（approved_by: human）。

### 8. 同步与验证
- task 8.1 Impact Analysis 无残留: ✅ proposal 无 unknown/TBD/待确认。
- task 8.2 RIR 最终结论: ✅ proposal/design findings 一致，无新调研结论变化。
- task 8.3 文档任务数口径: ⚠️ 已更新但**口径 off-by-one**（26 vs 实际 27；36 vs 实际 37），见 Issue I1。
- task 8.4 全量测试: ✅ 本 reviewer 复跑 `uv run pytest -q` → 2007 passed / 5 failed（全部 `tests/agent/mcp/test_mcp_manager.py`，在 base 4dc6289 复跑同样 5 失败，确认为环境性）/ 7 skipped。
- task 8.5 OpenSpec validate + artifact checker: ✅ 复跑 `npx @fission-ai/openspec@1.4.1 validate --all --strict` → 30 passed；`python scripts/check_openspec_artifacts.py` → passed。
- task 8.6 benchmark smoke: ✅ 复跑 gate-smoke（passed:1）+ b01（failed:1，正常），A/B 轨全链路不回归。

### 9. 审阅与 PR 收尾
- task 9.1-9.5 `[ ]`（未勾选，收尾任务）: ✅ 按标注评估。本 building-review 即为 9.1 审阅闭环的一部分；归档/backlog 清理/PR 发起为后续步骤。

## Issues

- **I1** [严重度: 中] 文档任务数口径 off-by-one：README/README_EN/benchmark-plan/tasks-README 均写「26 个本地任务 / 36 个编码任务」，实际为 **27 个本地任务（A22+B5）+ 10 swebench = 37**；`benchmarks/tasks/README.md` 头部「26 local coding-agent tasks」与其自身分解「A 轨（22）+ B 轨（5）」（=27）自相矛盾。根因：新增 `asterwynd-b01` 后未把存量「26」更新为 27（b01 为新增任务）。证据: `git ls-tree 4dc6289:benchmarks/tasks/` asterwynd-* = 26；HEAD = 27；track 计数 A=22/B=5；`README.md:36`/`README.md:178`/`README_EN.md:36`/`docs/benchmark-plan.md:22`/`benchmarks/tasks/README.md:3`。本 change tasks 8.3 明确声称修正任务数口径，但产出仍错误（grill R1 同类数据口径风险复发）。修复建议: 四处文档统一改「27 个本地任务 / 37 个编码任务（含 gate-smoke 则 39）」，并同步 README_EN。
- **I2** [严重度: 低] b01 的 `long-context` 能力标注与用户确认的 long-context 形态不符：OQ-B1 用户确认 long-context 采用「强制大读取 + 小改动（题面不给文件路径、只给行为症状）」；b01 issue.md 直接给出目标文件 `benchmarks/report.py`，更接近中等 multi-step 集成任务。`manifest.json` 将 b01 标注为 `["long-context", "multi-step-solving"]`，long-context 列仅靠 b01 支撑。证据: `benchmarks/tasks/asterwynd-b01-report-family-summary/issue.md:3`；`grill-design.md` OQ-B1 确认。影响: 覆盖矩阵机械校验通过，但 long-context 列覆盖力度存疑。修复建议: 接受为已知口径（面试场景解释为「多文件集成 + 统计口径理解」），或在后续 B 轨扩展中补真实 long-context 任务。
- **I3** [严重度: 低] 004 gold.patch 的 typer help 文案与实际行为不一致：help 写「只列出任务集组成（总数 + 按 track 分组）」，实现仅列出任务总数与 task id（无 track 分组）。证据: `benchmarks/tasks/asterwynd-004-benchmark-cli/gold.patch`（agent/main.py `_echo_task_set`）。影响: 仅任务 fixture 内帮助文案瑕疵，不影响评测判定（测试断言的是总数与 id）。修复建议: help 改为「只列出任务集（总数 + 任务 id），不运行 benchmark」。
- **I4** [严重度: 低] `swebench_subset.py` 的 `gold_check` 接受 `python` 参数但未使用（固定用默认解释器）；`build_subset` 对 `instance_id` 缺失的实例不跳过（`ex.get("instance_id") in known_bad` 对 None 安全但不报错）。证据: `benchmarks/swebench_subset.py:146-149`（python 参数未透传）、`:84-86`。影响: 低，不影响当前交付（fixture 未实际生成）。修复建议: 后续生成 40 fixture 时补校验。

## Test Results

- **B 轨 5 任务红绿复现**（在 base 4dc6289 建临时 worktree，应用 task fixture）：
  - 002：base+test 红（2 failed，AttributeError）→ +gold 绿（10 passed，含全任务）
  - 004：base+test 红（2 failed）→ +gold 绿
  - 005：base+test 红（2 行为测试 failed，2 基线行为 passed）→ +gold 绿
  - 021：base+test 红（1 failed）→ +gold 绿
  - b01：base+test 红（1 failed）→ +gold 绿
- **018/020 补 gold.patch 红绿复现**（在各自 base 594fa47/dfbd831 建 worktree）：018 红（`metadata.passed==1` 与断言不符）→ 绿（1 passed）；020 红（`llm.closed is False`）→ 绿（1 passed）。
- **gold_check L3 脚本**: `python benchmarks/swebench_subset.py --gold-check benchmarks/tasks/asterwynd-018-warning-passes` → exit 0。
- **全量测试**: `uv run pytest -q` → 2007 passed, 5 failed, 7 skipped in 126.72s；5 个失败全在 `tests/agent/mcp/test_mcp_manager.py`，在 base 4dc6289 复跑同样失败（FileNotFoundError，MCP server 二进制环境缺失），**确认环境性、非本 change 引入**。
- **OpenSpec**: `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → 30 passed, 0 failed。
- **Artifact checker**: `PYTHONPATH=. python scripts/check_openspec_artifacts.py` → OpenSpec artifact checks passed。
- **Benchmark smoke**: gate-smoke-001 fake runner → `Tasks: 1 | passed: 1`；asterwynd-b01 fake runner → `Tasks: 1 | failed: 1`（发现/执行正常）。

## 关键结论

- 任务 schema 扩展（scenario 5 枚举/difficulty 3 档/track）向后兼容实现正确，枚举校验 + 缺省兼容 + 旧 JSON 兼容单测齐全。
- 覆盖矩阵机械校验完整（每能力列/每场景列 ≥1、无幽灵 id、verified 排除），真实目录校验通过。
- B 轨 5 任务 + 018/020 补 gold + 022 结构校验全部红绿可复现，fixture 质量达标。
- Verified 子集基建（build_subset/validate_fixture/gold_check/CLI）交付，40 fixture 未生成已如实披露（5.1 `[~]`）。
- spec delta 15 条 Requirement 全部同步正式 spec，C2 注记齐全，workflow-events 已记录。
- 唯一中等问题为文档任务数口径 off-by-one（I1），修复成本极低；修复后即可 PASS。

---

## Round 2
- reviewer run id: a655915c4671bedbc
- 时间: 2026-08-17
- 复审范围: `git diff 4dc6289...HEAD`（含 R1 修复提交 0bdf257），change 文档（tasks/design/specs），全量测试，OpenSpec validate + artifact checker。R1 之后唯一新增提交为 0bdf257（R1 修复），本次复审重点核实 4 项修复落实与修复引入的新问题。

### Verdict

**PASS**

R1 的 4 项修复（I1 文档任务数、I2 b01 long-context 轻量形态记录、I3 004 gold.patch help 文案、I4 swebench_subset 健壮性）全部落实，修复提交 0bdf257 未引入新问题。全量测试 2008 passed / 5 failed（5 个失败全为 `tests/agent/mcp/test_mcp_manager.py` 环境性，master 基线同失败）/ 7 skipped；OpenSpec strict validate 30 passed。新增发现仅 1 条低严重度（R2-N1，README.md:428 陈旧任务数「34」，为存量债务且与刚修正的 README_EN 不一致，非本 change 引入），不阻塞 PASS。剩余收尾事项（审阅 manifest 生成、归档、backlog 清理）为 review-loop 闭合步骤，见 R2-N2。

### Round 1 修复验证

- **I1**: ✅ 实测任务目录计数 `asterwynd-*`=27（A=22/B=5）、`swebench-*`=10，总 37；四份文档当前值全部为 27/37：`README.md:36`（27 个本地）、`README.md:178`（37 个编码任务）、`README_EN.md:36`（27 local）、`README_EN.md:178`（37 coding）、`README_EN.md:374`（27 local）、`README_EN.md:429`（27 tasks）、`docs/benchmark-plan.md:22/76`（27）、`benchmarks/tasks/README.md:3`（27 local）；`rg "26 个|36 个|26 local|36 coding"` 对四文件无命中。修复提交 0bdf257 将 README 3 处 26/36→27/37、README_EN 4 处同步（含 Task Set 段落 26→27）。gate-smoke 为 smoke 目录不计入 27。遗留：README.md:428 仍写「34 个任务从项目 git 历史中提取」（见 R2-N1）。
- **I2**: ✅ `tasks.md:29`（4.1）明确记录「b01 的 long-context 为**轻量形态**（issue 给出 report.py 路径，但需通读 report/models/statistics 三模块；与 OQ-B1 确认的「强制大读取+不给路径」理想形态有偏差，审阅 I2 记录，接受为覆盖矩阵达标的最小实现）」；`tasks.md:67` 审阅修复记录节同步。
- **I3**: ✅ `benchmarks/tasks/asterwynd-004-benchmark-cli/gold.patch` help 文案改为「只列出任务集组成（总数 + 任务 id），不运行 benchmark」（与 `_echo_task_set` 实际行为一致）。红绿复现（临时 worktree）：base+test 红 2 failed（`--list-tasks` 断言），+gold 绿 11 passed。gold/test patch 在 base_commit 4dc6289 干净应用。
- **I4**: ✅ `benchmarks/swebench_subset.py`：`gold_check` 签名移除未用 `python` 参数（`rg "gold_check"` 全仓无调用方传 python=）；`build_subset` 对 `not ex.get("instance_id")` 先跳过并 `skipped_missing_instance_id += 1`（:88-90）；`SubsetPlan.summary` 计入该计数。回归测试 `tests/benchmark/test_swebench_subset.py::test_build_subset_skips_missing_instance_id` 新增并通过（32 个 benchmark 单测全绿）。

### 新发现 Issues

- **R2-N1** [严重度: 低] `README.md:428`「34 个任务从项目 git 历史中提取」为存量陈旧值（base 4dc6289 已为 34，本 change 及 R1 修复均未触碰），但 R1 修复恰好更新了同一段落的英文翻译 `README_EN.md:429`（26→27 tasks），现 README.md（源文档）与 README_EN.md（同步翻译）对 Task Set 段落的任务数不一致（34 vs 27），违反 AGENTS.md「README 与 README_EN 保持事实口径一致」维护规则。证据: `git show 4dc6289:README.md | sed -n '428p'`（34）、`README_EN.md:429`（27）。影响: 仅文档口径，不影响代码/评测/spec。建议: 一行修复 README.md:428 为「27 个任务」并保持 README_EN 一致，或在 known-debt 记录为历史口径债务（AGENTS.md 允许「历史口径问题另记债务或单独处理」）。
- **R2-N2** [严重度: 信息] artifact checker 当前报「review manifest missing: openspec/changes/evaluation-task-spec/reviews/building-review-manifest.json」。根因: building-review.md 已存在（R1 产出）但 PASS manifest 未生成；`verify_review_manifest` 对存在的 `*-review.md` 强制绑定 manifest。此为 review-loop 中间态（`requires_building_review` 因 tasks 9.x 未勾选而不触发，纯由 building-review.md 存在触发），审阅 PASS 后由 review-loop 闭合生成 manifest 即可恢复绿色，非本 change 缺陷。

### Test Results

- `uv run pytest -q` → **2008 passed, 5 failed, 7 skipped in 122s**；5 个失败全在 `tests/agent/mcp/test_mcp_manager.py`（MCP server 二进制环境缺失），master 基线同失败，确认为环境性、非本 change 引入；较 R1（2007 passed）多出的 1 个通过为新增回归测试 `test_build_subset_skips_missing_instance_id`。
- `uv run pytest tests/benchmark/test_task_schema.py tests/benchmark/test_task_set.py tests/benchmark/test_swebench_subset.py -q` → **32 passed**。
- 004 红绿复现（临时 worktree）: base+test → 2 failed；+gold → 11 passed；gold/test.patch 在 base_commit 干净 apply。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。
- `PYTHONPATH=. python scripts/check_openspec_artifacts.py` → **FAIL**（仅因 building-review-manifest.json 缺失，R2-N2；PASS manifest 生成后闭合）。
