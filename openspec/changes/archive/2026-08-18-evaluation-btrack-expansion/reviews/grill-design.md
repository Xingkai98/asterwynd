# Grill: evaluation-btrack-expansion 设计追问

## Reviewer

- run id: grill-evaluation-btrack-expansion-2026-08-18
- 时间: 2026-08-18
- 审查对象: `openspec/changes/evaluation-btrack-expansion/design.md`（D1–D6）
- 独立零记忆审查声明: 本 reviewer 未继承任何开发上下文，不预设结论；全部「design 声称」均在本仓库 `benchmarks/`、`agent/`、`flow/`、`scripts/` 与文档中逐一实测核验后给出判断。

## 核验到的事实基线（design 声称 vs 代码库实测）

### 1. 任务数口径（遍历 `benchmarks/tasks/*/task.json` 实测）

| 来源 | 声称 | 实测 | 结论 |
|---|---|---|---|
| design D1 Non-Goal | 「不改 A 轨（26 条保持）」 | **A 轨 = 22 条**（001/002-runner/003×2/004-harden/006/007/008/009/010/011/012/013/014/015/017/018/019/020/022×2/readme-title） | **不符**。26 是 C1 前「26 本地全 A」的旧口径；C1 已把 002/004/005/021 重打标为 B 轨。 |
| design D4 | 「27 本地任务（26 A 轨 + 1 B 轨）」 | 27 本地 **= 22 A + 5 B** | 总数对、**拆分错**。D4 拟改写的「26 A 轨 + N B 轨」会继续沿用错误 A 数。 |
| proposal | 「27 本地 + 10 swebench = 37」 | 本地 27 + swebench 10 = 37 | **正确**（当前实测即此）。 |
| C1 用户确认 OQ-2 | 「A≈22、B≈14–18」 | 当前 A=22（相符）；B=5（14–18 是 B 轨扩展**之后**的预测值） | A 相符；B 是目标不是现状。 |

### 2. D4 引用文件与行号实测

| design 引用 | 实测 | 结论 |
|---|---|---|
| `docs/interview-script/FINAL-master-script.md` L117 | 存在。L117「评测任务 \| 37（27 本地 + 10 SWE-bench）」；**另有 L27「37 任务（27 本地 + 10 SWE-bench）」、L96「评测 37 任务…任务集从 37 扩到升级目标 ~90」、L118「~90（…当前已落 37）」** | 路径对；**校准范围漏了 L27/L96/L118**。 |
| `walkthrough/README.md` L27 | **顶层 `walkthrough/` 不存在**；正确路径是 `docs/interview-script/walkthrough/README.md` L27（`"37 任务（27 本地 + 10 SWE-bench）" \| 27 + 10 = 37`） | **路径错**。 |
| `resume-description.md` | **顶层不存在**；正确路径 `docs/resume-description.md`，L9/L87/L104 均写「27 个本地…（26 A 轨 + 1 B 轨）」 | **路径错 + 内容与 task.json（22 A + 5 B）不符**。 |
| （design 未列） | `README.md` L36/L178/L373、`README_EN.md` L36/L178 均引用任务数（「27 个本地…」「37 个编码任务」） | **design 漏了 README/README_EN**；tasks 6.2 有提，但 D4 正文只列 3 处。 |

### 3. CP-1~4 / LT-MEM-1 / LC-1 可行性逐条核验

- **CP-1**：`agent/tools/registry.py`（`ToolRegistry`）+ `agent/tools/factory.py`（`build_default_tool_registry`/`build_coding_tool_registry` 注册点）+ `agent/loop.py` 均存在；全库无 `ListRunningBenchmarks`，**net-new**。工具命名惯例是 `XxxTool`（`ListFilesTool`/`SaveMemoryTool`），design 写的 `ListRunningBenchmarks` 不是类名惯例。数据源 `benchmarks/reports/` 存在。**可行**；「benchmark 语境下 agent 工具是否自洽」是语义问题，gold.patch 需钉住工具契约（返回什么）。
- **CP-2**：`flow/statechart.json` 实测**无** `awaiting_grill_confirmation`，现有 `blocked.awaiting_proposal_confirmation/human_review/user_confirmation` 三个；`flow/engine.py` 的 `awaiting_sub_states()` 从 statechart 派生（无独立转移表要同步）。**但真实触面不止 4 处**：`agent/workflow/event_log.py` 的 `AWAITING_SUB_STATES` 常量（`flow block --awaiting` 在 `scripts/workflow_state.py:576` 校验 `args.awaiting not in AWAITING_SUB_STATES` 直接报错）、`scripts/workflow_state.py` 的 `_AWAITING_RECOVERY_DEFAULTS`（`flow confirm` 需要 recovery 目标）、`scripts/workflow_methods.json`、parity 测试 `tests/test_declarative_flow_engine.py`。**共 6 处**，design「跨 4 处」低估。`grill_completed` 已是 `MILESTONE_EVENT_TYPES` 之一。
- **CP-3**：`benchmarks/models.py` 的 `TaskResult` **只有 `task_family`/`category`，没有 `track`**；`benchmarks/runner.py` 有 5 处 `TaskResult(...)` 构造点（L218/308/377/446/530）只填 family/category；`benchmarks/report.py` 无任何 track 分组。**需要 models+runner+statistics+report 的管道改造**，比 design「结果页新增分组」的字面范围大，medium 难度合理但触面要写进 issue.md。`tests/benchmark/test_report.py` 存在（b01 同款 test_command 可行）。
- **CP-4**：**前提与代码不符**。`benchmarks/adapters.py:125` 已写 `model_name.replace("/", "__")`（git blame `2d23eabb` 2026-08-01，先于本 change）。design 声称「model name 含 / 时 predictions.jsonl 的 model_name_or_path **未转义**导致 report 路径找不到」在当前 HEAD **不成立**。swebench 包本地未安装（`ModuleNotFoundError`），harness 目录命名行为本地不可验证。base 红只能靠 Docker 跑 harness 或 mock harness——前者违反「确定性 test_command」轻量约定，后者测 mock 不测 adapter，判别力弱。**按现描述不可构造**（详见 OQ-2）。
- **LT-MEM-1**：`SaveMemoryTool`（`agent/tools/builtin/memory.py`）`execute(type,name,description,body,importance,...)` **无 project 参数**；`MemoryIndexSource.render`（`agent/context/sources.py:278`）调 `persistent_memory.load_summary()` **无 project 过滤**。**net-new、可行**；project 身份来源（工具参数 vs 会话级绑定）未钉（OQ-7）。
- **LC-1**：`agent/memory/` **不是空壳**——有 `manager.py`(22K)/`persistent.py`(38K)/`dedup.py`/`git_backend.py`/`model.py`/`summary.py`。`MemoryIndexSource` 是 context 注入源（把记忆摘要渲染进上下文），把它「拆到 `agent/memory/`」方向存疑（memory 层不该拥有 context-source 渲染）。base 红只能靠 test.patch 结构性断言（符号搬家类），与 C1「022 用 grep 关键词打分」教训同构（OQ-4）。

### 4. 覆盖矩阵缺口（manifest coverage + task.json scenario 实测）

- 能力列当前 B 轨缺口：**context-planning（B=0）**、**long-term-memory（B=0）**；long-context B=1（仅 b01）。design 声称「仅 010/022 无 B 轨」「2 条 A 轨」「仅 b01」——**全部属实**。
- 场景列当前 B 轨缺口：**refactor（B=0，A 仅 012）**、integration B=1（仅 b01）。
- 6 条候选补齐后：context-planning B=4（CP-1/2/3/4）、long-term-memory B=1、long-context B=2（LC-1+b01）、refactor B=2（CP-2/LC-1）、integration B=2（CP-3+b01）——**能力/场景缺口全部覆盖**。
- **但 B 轨总数 = 5 + 6 = 11 < 下限 12**。proposal「B 轨新增 7–11（5→12–16）」要求**至少 7 条新**，design 只有 6 条候选 → **不达下限**。且 design D1 自己的覆盖矩阵文字写「bug-fix 用既有 + 1 条新」，但候选清单里**没有 bug-fix 任务**——补上这条正好到 12（OQ-1）。

### 5. D6 红绿可复现评估（读 `task_schema.py`/`runner.py` 后）

验证机制：base_commit checkout → 应用 `test.patch`（判别测试）→ 跑 `test_command`（红）；再打 `gold.patch` → 绿。C1 b01 先例已确立。

| 候选 | base 红靠什么 | 评估 |
|---|---|---|
| CP-1 | test.patch 断言新工具注册+可 run() | **可构造** |
| CP-2 | test.patch 断言 `awaiting_grill_confirmation` 存在于 statechart 且 `flow block --awaiting` 接受 | **可构造**（须同步 Python 镜像常量，见 R5） |
| CP-3 | test.patch 断言 report 按 track 分组渲染 | **可构造**（触面 models+runner+report） |
| CP-4 | 现 HEAD 无此 bug | **不可构造**（前提错误，见 OQ-2） |
| LT-MEM-1 | test.patch 断言跨 project 不可见 + 注入按 project 过滤 | **可构造**（project 身份来源待钉，OQ-7） |
| LC-1 | test.patch 断言新模块存在/旧符号迁走 | **可构造但弱判别**（结构断言，见 OQ-4） |

### 6. D5 与 verified-subset 并行

`manifest.json` 现状只有 `anti_cheat_disclosure`/`capabilities`/`coverage` 三段，**没有 verified 条目段**；10 个 swebench 任务在独立 task.json 目录。design 说「verified-subset 改 verified 条目段」——该段当前不存在，属**推测**。本 change 只改 `coverage` 段，冲突面小的前提是 verified-subset 新增独立顶层段；若它把 verified 任务也登记进 `coverage`，冲突扩大。且 `benchmarks/runner.py` 根本不读 manifest（manifest 只被 `task_set.validate_coverage` 消费），改 coverage 不影响 runner 行为。

### 7. spec delta 一致性

- delta Requirement「context-planning、long-term-memory、long-context 等能力列 SHALL 有 B 轨任务覆盖」与 D1 候选一致；但只有 context-planning 有 Scenario，且 `validate_coverage`（`task_set.py:_LOCAL_TRACKS={None,"A","B"}`）**只校验 A+B 聚合 ≥1，不校验 per-track B**——当前 manifest **已过校验**，即使本 change 交付 0 条新任务门禁也绿。spec Scenario 1「context-planning 列 SHALL 有 B 轨任务登记」**无机械强制**。
- delta Scenario「每场景至少一个任务（A 轨或 B 轨）」当前已满足（bug-fix/feature-dev/refactor/debug/integration 均有 A 或 B 覆盖），无新增约束力。
- delta「任务数变化 SHALL 同步面试文档」与 D4 方向一致，但 D4 校准范围不全（见事实基线 2）。

### 8. grill 门禁自检

- **a) reviews/** 写豁免**成立**：`scripts/flow-policy.json` protected_paths 无 `reviews/`；`scripts/workflow_guard.py:_is_change_doc_write` 对 `reviews/` 前缀返回 True（豁免 grill gate）；checker 的 `_extract_grill_decisions` 只要求 `## Confirmed Decisions` ≥3 条 `- **决策**` 条目。
- **b) tasks 1.3「收到答复前不写实现代码」确有机械强制**：`workflow_guard._grill_evidence_missing` 对非 docs + 有 spec delta 的 change，若 `reviews/grill-design.md` 缺失或 Open Questions 未在 `## User Confirmation` 全部确认 → 代码写操作 exit 2。占位文本（`待确认`/`待拍板`/`pending`/`无` 等）不算确认（`_is_unconfirmed_answer`）。
- **c) 无自死锁**：awaiting 门禁（`_awaiting_block_reason`）只在该 change **自身** `workflow-events.jsonl` 投影为 `blocked.awaiting_*` 时拦截；CP-2 给 statechart 加新态**不会**自动把本 change 置入该态。本 change 停轮阶段用现有 `awaiting_user_confirmation`（此时 `awaiting_grill_confirmation` 还没进 `AWAITING_SUB_STATES`，`flow block --awaiting` 反而会拒绝它）。grill 证据写 `reviews/` 本身被豁免，不会卡自己。

## Confirmed Decisions

- **决策**: D2「B 轨任务 issue.md 不给目标文件路径、迫使 agent 先 repo-map 再规划」确认；理由: 与 C1 b01 同规范，context-planning 能力的测法就是「不给路径」，实测 b01 已是该形态且 test_command 确定性；来源: grill-evaluation-btrack-expansion-2026-08-18
- **决策**: D6「每任务 base 红 + gold 绿 硬性，红绿不成立则不提交」确认；理由: C1 教训（022 grep 打分、2 空 gold.patch）证明判别力是 B 轨任务的最低验收线；此原则适用于 CP-1/CP-2/CP-3/LT-MEM-1 且已核验可构造；来源: grill-evaluation-btrack-expansion-2026-08-18
- **决策**: D1 候选清单方向（CP-1/CP-2/CP-3/CP-4 + LT-MEM-1 + LC-1 补齐 context-planning/long-term-memory/long-context 的 B 轨空白）确认；理由: 6 条候选逐条核验模块存在、改动真实，补齐后 7 能力列 × 5 场景列的 B 轨缺口全部覆盖；来源: grill-evaluation-btrack-expansion-2026-08-18
- **决策**: D5「manifest 只改 coverage 段、与 verified-subset 错开合入」确认（附前提）；理由: 实测 runner 不读 manifest、coverage 段与 verified 条目段互不重叠；前提是 verified-subset 必须新增独立顶层段而不是写进 coverage；来源: grill-evaluation-btrack-expansion-2026-08-18
- **决策**: D3 覆盖矩阵机械校验方向确认（需扩展）；理由: `validate_coverage` 现有「A+B 聚合 ≥1」正确但不足以支撑 spec Scenario 1 的「B 轨登记」断言，需增加 per-track B 能力列校验（见 OQ-6）；来源: grill-evaluation-btrack-expansion-2026-08-18

## Open Questions

（每条配具体例子/场景；主 session 逐项转达用户确认后记录进 `## User Confirmation`）

- **Q1**: B 轨下限 12 vs 6 条候选 → B=11，是否补第 7 条 bug-fix 任务？具体场景：当前 B=5（002-sandbox-executor/004-benchmark-cli/005-bash-workspace/021-lsp-diagnostics/b01）。6 条候选（CP-1~4/LT-MEM-1/LC-1）全部落地后 B=11，仍低于 proposal「5→12–16」下限 12 与 C1 规格「B 轨 12–16」；且 design D1 覆盖矩阵文字自己写「bug-fix 用既有 + 1 条新」但清单里没有 bug-fix 候选——补一条 B 轨 bug-fix 正好到 12。请拍板：A) 补第 7 条（如 command_guard/sandbox 里挑一个可确定性验证的缺陷形态），B) 接受 B=11 收敛并在 #156 标注，C) 其它。
- **Q2**: CP-4 前提与代码不符，如何改？具体场景：模型名 `claude/claude-fable-5[1m]` → `SwebenchAdapter._prediction_model_name()` 返回 `asterwynd:claude/claude-fable-5[1m]`，`verify()` 在 `benchmarks/adapters.py:125` 已做 `model_name.replace("/", "__")` → 报告路径用 `asterwynd:claude__claude-fable-5[1m]`。design 声称「未转义导致路径找不到」与当前 HEAD 不符，且 swebench 包本地未安装、harness 目录命名不可本地验证。请拍板：A) 改成合成回归（base 人为去掉转义 + gold 加回 + 单测断言路径转义与 harness 目录命名一致），B) 换一个可真实验证（本地确定性 test_command）的 debug 任务，C) 砍掉 CP-4（B 轨再 −1）。
- **Q3**: D4 校准范围与 A 轨数字。具体场景：`docs/resume-description.md` L9/L87/L104 现写「27 个本地…（26 A 轨 + 1 B 轨）」；实测 task.json 是 22 A + 5 B。若按 D4 改成「26 A 轨 + N B 轨」则 A 数继续错（应为 22）。且 D4 只列了 FINAL L117/walkthrough L27/resume 三处，漏了 FINAL L27/L96/L118、`README.md` L36/L178/L373、`README_EN.md` L36/L178。请确认：以实测 22 A 为准；校准行清单按上面全套（FINAL 4 行 + walkthrough 1 行 + resume 3 行 + README 3 行 + README_EN 2 行）。
- **Q4**: LC-1 拆分方向与 base 红判别力。具体场景：test.patch 若写 `assert "MemoryIndexSource" not in source_text` 或 `from agent.memory import MemoryIndexSource`（base 红 → gold 绿），只验证「符号搬家」，与 C1 022「grep 关键词打分」教训同构。且 `agent/memory/` 已有 6 个实现文件（manager.py/persistent.py 等）不是空壳，`MemoryIndexSource` 是 context 注入源、拆进 memory 层方向存疑。请确认：拆分目标具体是什么（迁 MemoryIndexSource？还是把 sources.py 里其它 memory 调用下沉？）、base 红断言的具体内容（建议「行为保持断言 + 新模块路径可用」双断言，避免纯搬家）。
- **Q5**: CP-2 触面是 6 处不是 4 处。具体场景：只改 `flow/statechart.json` 后运行 `flow block --awaiting awaiting_grill_confirmation` 会怎样？`scripts/workflow_state.py:576` 校验 `args.awaiting not in AWAITING_SUB_STATES` → 直接报错退出，因为 `agent/workflow/event_log.py` 的 `AWAITING_SUB_STATES` 还没加该值；`flow confirm` 也需要 `scripts/workflow_state.py:_AWAITING_RECOVERY_DEFAULTS` 有 recovery 目标。请确认：issue.md 是否明示「blocked 子态需同步 Python 镜像常量（event_log.py + workflow_state.py）」及完整 6 处清单，避免 agent 只改 statechart 导致 parity/flow 卡住。
- **Q6**: `validate_coverage` 机械校验缺口。具体场景：当前 manifest 已过 `validate_coverage`（7 能力列 × 5 场景列在 A+B 聚合下全部 ≥1），即使本 change 交付 0 条新 B 轨任务、spec delta Scenario 1「context-planning 列 SHALL 有 B 轨任务登记」也无人拦截。请拍板：A) 扩展 `validate_coverage` 增加 per-track B 能力列要求（如 `required_track_coverage = {"context-planning": {"B"}, "long-term-memory": {"B"}, "long-context": {"B"}}`，只对声明的缺口列生效），B) 接受 task-list + review 人工把关（checker 不机械校验）。
- **Q7**: LT-MEM-1 的 project 身份来源。具体场景：实现 agent 写测试「写 A 项目记忆 → 切 B 项目 MemoryIndexSource 不可见 → 回 A 复用」，但 `PersistentMemory` 按 `workspace_root`（`PersistentMemory(Path.cwd())` 或 `policy.workspace_root`）定 project、`SaveMemoryTool.execute` 无 project 参数、`MemoryIndexSource.render` 调 `load_summary()` 无过滤。design 的 `--project <hash>` 到底是 SaveMemory 工具调用参数还是会话级绑定？若工具参数，测试里如何构造「两个 project」的 PersistentMemory 实例并断言隔离？请确认 project 身份来源与过滤实现位置。

## User Confirmation

主 session 转达用户答复（2026-08-18，Q1–Q7 全部按推荐执行）：

- **Q1**: 用户答复：按推荐 A——补第 7 条 B 轨 bug-fix 任务（B=12）；若实现时红绿做不出判别力，按 D6 收敛并在 #156 标注。确认时间: 2026-08-18
- **Q2**: 用户答复：按推荐 A——CP-4 改成合成回归：base 人为去掉转义 + gold 加回 + 单测断言「路径转义后与 harness 目录命名一致」；若判别力弱则换本地可确定性验证的其它 debug 任务。确认时间: 2026-08-18
- **Q3**: 用户答复：按推荐——全套清单校准（FINAL L11/L27/L96/L117/L118 + walkthrough/README L27 + resume L9/L87/L104 + README L36/L178/L373 + README_EN L36/L178），A 轨以实测 22 为准。确认时间: 2026-08-18
- **Q4**: 用户答复：按推荐——LC-1 拆分目标钉具体（sources.py 的 memory 注入逻辑下沉到 agent/memory/ 明确归属），base 红用「行为保持断言 + 新模块路径可用」双断言。确认时间: 2026-08-18
- **Q5**: 用户答复：按推荐——CP-2 触面 = statechart.json + event_log.py + workflow_state.py（校验+recovery）+ workflow_methods.json + parity 测试共 6 处，写进 issue.md。确认时间: 2026-08-18
- **Q6**: 用户答复：按推荐 A——扩展 validate_coverage 加 per-track B 能力列校验（`{"context-planning": {"B"}, "long-term-memory": {"B"}, "long-context": {"B"}}`，只对声明的缺口列生效）。确认时间: 2026-08-18
- **Q7**: 用户答复：按推荐——project 身份 = SaveMemoryTool 新增 `--project <hash>` 参数 + MemoryIndexSource 按当前 session project 过滤注入（双端闭合），测试构造两个 project 实例断言隔离。确认时间: 2026-08-18

## 风险

- **R1 CP-4 前提错误扩散**：design 声称的「未转义 bug」在当前 HEAD 不存在；若实现 agent 照 design 造任务，会得到一个「base 绿」（无 bug）或「base 红需 Docker」的任务，直接违反 D6 确定性 test_command 约定。
- **R2 LC-1 弱判别力**：refactor 不改行为，base 红只能靠结构性断言；若只断言符号位置，重演 C1 022「grep 打分」教训，且审阅（building-review「测试覆盖」维度）可能放行。
- **R3 机械校验缺口**：spec Scenario 1 的「B 轨登记」无 validate_coverage 强制，门禁不能阻止「0 新任务」交付通过，B 轨扩展可能空转。
- **R4 D4 数字穿帮**：resume 的「26 A 轨」与 task.json 不符是既有事实错误；D4 若按「26 A + N B」改写会延续错误，且漏 README/README_EN 多处 → 面试叙事前后不一致（C4 review-loop 对数字一致性是 PASS 项，审阅会拦）。
- **R5 CP-2 触面低估**：4→6 处；漏 event_log `AWAITING_SUB_STATES` / workflow_state `_AWAITING_RECOVERY_DEFAULTS` 时 parity 测试或 `flow block/confirm` 直接失败，任务红绿卡住。
- **R6 manifest 并行前提不确定**：verified 条目段当前不存在，若 verified-subset 把任务登记进 coverage 段则与本 change 冲突面扩大（D5 前提失效）。
- **R7 任务数口径漂移**：B=11 与 C1 规格「B 轨 12–16」不一致，合入后 spec-vs-code 长期不符（artifact checker 不校验 spec-vs-code，无人拦截）。

## Grill 结论

- **需修改**：D1（补第 7 条 bug-fix 候选或明确收敛 B=11；CP-4 前提重写为合成回归或替换）；D4（校准范围扩到 FINAL 4 行/walkthrough/resume/README/README_EN 全套，A 轨按实测 22 而非 26）；D3（扩展 validate_coverage 做 per-track B 能力列校验）；CP-2 触面描述 4 处→6 处（补 event_log/workflow_state 镜像常量）。
- **已确认**：D2（不给路径）、D5（只改 coverage 段，附 verified-subset 独立段前提）、D6（红绿硬性 + 红绿不成立则不提交）、D1 的能力补缺方向与 CP-1/CP-2/CP-3/LT-MEM-1 四个候选的可构造性；grill 门禁自检无死锁，reviews/** 写豁免成立，tasks 1.3 停轮确有机械强制。
- **Open Questions**：Q1（B 轨下限 12 vs 11）、Q2（CP-4 前提与红绿）、Q3（D4 校准范围与 22/26）、Q4（LC-1 拆分方向与 base 红判别力）、Q5（CP-2 六处触面）、Q6（validate_coverage per-track B 机械校验）、Q7（LT-MEM-1 project 身份来源）。全部停轮等用户确认后写入 `## User Confirmation`。
