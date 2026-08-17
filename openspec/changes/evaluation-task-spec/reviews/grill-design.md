# Grill: evaluation-task-spec 设计追问

## Reviewer

- run id: grill-evaluation-task-spec-2026-08-17
- 时间: 2026-08-17
- 审查对象: `openspec/changes/evaluation-task-spec/design.md`（D1–D8）
- 独立零记忆审查，未继承任何开发上下文；代码事实均经本 reviewer 在 `benchmarks/task_schema.py`、`benchmarks/adapters.py`、`benchmarks/statistics.py`、`benchmarks/tasks/`（37 目录）与既有 `openspec/specs/benchmark/spec.md` 逐一核验。

## 核验到的事实基线（与 design 交叉比对）

- `TaskSpec.from_dict` 无条件调用 `validate()`；`validate()` 目前只对 `execution_environment`、swebench 必填字段校验，**不校验 `difficulty` 值**（自由字符串）。→ 新增难度枚举校验将连锁影响所有既有任务加载。
- 本地任务 difficulty 实测分布为 **easy 9 / medium 13 / hard 4**（26 个本地任务），**与 design/proposal 引用的「9/12/5」不符**。
- `benchmarks/tasks/README.md` 仍写「23 coding-agent tasks」，已陈旧（实为 26 本地 + 10 swebench + gate-smoke 子任务）。
- 10 个 swebench fixture 的 `category` 均为 `bug_fix`（**下划线**），与新增 scenario 枚举 `bug-fix`（**连字符**）肉眼易混；`difficulty` 均为 `<15 min fix`。
- `gate-smoke` 的 `gate-smoke-001` 用 `difficulty: trivial`（不在 3 档枚举内）。
- **当前不存在 `manifest.json`**；runner 发现任务的逻辑是顶层 `*/task.json` 扫描（`runner.py:124-125`）。D2 的套件级覆盖矩阵与 `track` 是 net-new 基础设施，落点未定。
- `SwebenchAdapter` 目前只从 `report.json` 提取 `resolved` 布尔，`f2p_rate`/`p2p_rate`/`reward` 被丢弃（spec delta 的「SWE-bench 部分成功保留」为 C2 文本，未实现）。
- `external_repo` 指向 `https://gitee.com/mirrors/requests.git`——L1 本地验证依赖外部镜像可达性，存在风险。

## Confirmed Decisions（已确认，至少 3 条）

- **决策**: D1 任务 schema 双标签（`scenario` 5 枚举 + `difficulty` 3 档归一化、缺省 `scenario=None` 向后兼容）方向确认；理由: Terminal-Bench 式显式双标签最干净、缺省兼容保证既有 26 本地 + 10 fixture 不破，`validate()` 对已填值做枚举校验合理；来源: grill-evaluation-task-spec-2026-08-17
- **决策**: D2 能力层从任务级移到套件级覆盖矩阵方向确认；理由: 业界主流（OpenHands Index / VersaBench 聚合映射式）无任务级「场景×能力」二维先例，manifest 一层声明可机械校验，比任务级标注便宜可维护；`category` 保留为信息性主题标签正确（实测 26 本地 `category` 确为主题标签 tools/security/agent 等，从未真正打能力枚举）。覆盖矩阵的文件落点与 `track` 归属属未定细节，见 OQ-1；来源: grill-evaluation-task-spec-2026-08-17
- **决策**: D3 三来源配比（A 20–24 + B 12–16 + Verified 50 ≈ 82–90）确认；理由: G2 用户「按推荐」确认的组合，A 轨回归基线 + B 轨面试核心 + Verified 外部对标各有定位，`track: A|B|verified` 语义分立合理；来源: grill-evaluation-task-spec-2026-08-17
- **决策**: D7 反作弊泄漏本期披露、不做 shallow/mirror 加固确认；理由: 诚实边界 > 假装公平（G3 M7），披露成本近零、加固改动 runner 克隆语义面大，与 G4「加固留后续」一致；来源: grill-evaluation-task-spec-2026-08-17
- **决策**: D8 spec delta 承载完整评估规格（含 M1–M11 文本）、实现归 C2–C4 的编排确认；理由: 需求先行（AGENTS.md），G4 明确 M1–M11 Requirement 落 C1；tasks 的 `[spec]`/`[C2]` 标注区分「规格落定」与「指标实现」是必要的防误判手段。但 spec 落定与实现之间存在空窗期风险，见 OQ-4；来源: grill-evaluation-task-spec-2026-08-17

## D1–D8 逐项独立判断

| Decision | 判断 | 说明 |
|---|---|---|
| D1 scenario+difficulty 双标签 | ✅ 确认（附迁移约束） | 见 Confirmed；但 `validate()` 枚举收紧会连锁破坏 10 fixture（`<15 min fix`）与 gate-smoke（`trivial`），见 OQ-3 |
| D2 套件级覆盖矩阵 | ✅ 确认方向 / ⚠️ 落点需拍板 | 方向正确；manifest 位置、track 落点、统计口径未定，见 OQ-1/OQ-2 |
| D3 三来源配比 | ✅ 确认 | 见 Confirmed |
| D4 存量 26 去留/重打标 | ⚠️ 需修改/拍板 | 002/004→B 明确；005/021「按新架构改写」后 track 归属（A 或 B）未定，影响 A/B 计数，见 OQ-2；难度分布引用数据错误（9/13/4 非 9/12/5）需在 C1 内纠正 |
| D5 B 轨新增任务 | ⚠️ 需用户拍板 | 方向（context-planning 优先）确认；具体清单为 OQ-B1；另需拍板「合成任务 vs 真实缺陷」边界 |
| D6 Verified 50 + L1/L2/L3 | ⚠️ 需用户拍板 | 路径分级方向确认；实例选择、difficulty 映射、L1 判据为 OQ-V1；L3 自检与 L1 判定存在先后耦合 |
| D7 反作弊披露 | ✅ 确认 | 见 Confirmed |
| D8 spec delta 编排 | ✅ 确认（附空窗风险） | 见 Confirmed 与 OQ-4 |

## Open Questions

### OQ-B1: B 轨具体任务清单（id/问题描述/验证方式/gold patch 来源未定）

设计把 B 轨 12–16 条的任务清单整体开放。请用户拍板以下几点，每点给候选：

**① context-planning 3–5 条在本地仓库能构造什么具体任务？**（候选基于真实模块，issue.md 只给目标不给文件路径，迫使 agent 先 repo-map 再规划）

- 候选 CP-1（feature-dev / multi-step）：新增工具 `ListRunningBenchmarks`，注册进 `agent/tools/registry.py` 并经 `agent/tools/factory.py` 装配、在 `agent/loop.py` 的 AgentLoop 主循环可被调用，补 contract 测试。验证：`pytest tests/...` 断言工具已注册且经 `run()` 可调用。难点：agent 需自己发现「注册→工厂→主循环装配」链路。
- 候选 CP-2（refactor / 跨文件）：`flow/statechart.json` 新增 awaiting 态 `awaiting_grill_confirmation`，同步 `flow/engine.py` 转移表、`scripts/workflow_methods.json` 方法映射与 parity 测试。难点：需先理解 statechart↔engine↔parity 四者关系，是真实 repo 内存在的架构。
- 候选 CP-3（integration）：`benchmarks/report.py` 结果页新增按 `track`（A/B/verified）分组数量与占比（spec「任务集由三来源组成」Scenario）。需读 `report.py` + `run.json` schema + `statistics.py`。
- 候选 CP-4（debug）：构造 `SwebenchAdapter` 在 model name 含 `/` 时 `predictions.jsonl` 的 `model_name_or_path` 未转义、导致 report 路径找不到的 debug 任务，agent 需先读 harness 输出定位根因。

**② long-term-memory +1 与 long-context +1–2 的具体形态？**

- long-term-memory 候选：现有 `asterwynd-022-long-term-memory` 覆盖去重/冲突/衰减/检索；新增「scope 隔离」：SaveMemory 支持 `--project <hash>`，`agent/context/sources.py` 的 `MemoryIndexSource` 按当前 project 过滤注入。要求 agent 先写 A 项目记忆、切到 B 项目确认不可见、再切回 A 复用——正好是「会话中写记忆并后续复用」的形态。验证：pytest 断言跨 scope 不可见 + 注入按 project 过滤。
- long-context 候选：本仓库单 context、体量不算大，长上下文只能靠「强制大读取」构造——如「按 `docs/architecture.md` 模块划分审计 `agent/context/` 与 `agent/memory/` 职责，把混在 `sources.py` 的 memory 注入逻辑拆到 `agent/memory/`，保持现有测试全绿」，需要读整个注入管线 + memory 层。请拍板这类「任务设计得大」是否算 long-context 任务，还是必须等真实大仓库任务（无外部 repo 时成本高）。

**③ 每场景 ≥1–2 与 2–3 条 hard 的可行性？** bug-fix/feature-dev 最易凑（26 本地里大部分）；refactor 用 CP-2、debug 用 CP-4、integration 用 CP-3。hard 候选：CP-2（跨 4 处修改）+ 结果页 track 分组 + 002/004 重写（D4）。请确认此映射。

**④ 「从现有 26 本地任务改造」vs「必须新造」？** 设计称 B 轨为「当前 HEAD 真实缺陷/增强」，但 CP-1/2/3 是「基于现有模块构造的新功能」（gold patch = 参考实现），不是已发生缺陷。请拍板：B 轨允许合成任务（构造成本低、覆盖可控），还是必须来自真实 issue/PR（更可信但 12–16 条难以短期凑齐）。

### OQ-V1: Verified 50 具体实例选择（过滤口径 / difficulty 映射 / L1 判据）

**① 保留现有 10 fixture + 补齐 40 条的过滤口径？** KNOWN_BAD 列表来源需钉住（design 只引 R2，未给具体 URL/commit/版本）。轻量+中等池（requests/flask/pytest/sympy/seaborn/pylint）115 条 reviewer 无法本地核验，需用户/R2 给出实例清单。候选过滤规则：排除 KNOWN_BAD（≥28 条）→ 余 ~87；再排除 FAIL_TO_PASS 为空的实例、test_patch 依赖 py<3.12 或旧 numpy 的实例、swebench harness 已知 build 失败的实例、单实例验证 timeout>600s 的实例。40 条配比候选（平衡现有 requests 6/10 偏置）：requests +4（→10）、flask +6（→7）、pytest +8（→11）、sympy +8、seaborn +6、pylint +8 = 40，总计 50。

**② 实例 difficulty 映射？** Verified 官方是否带 per-instance 人工时间桶需确认；若无，需定映射依据（R2 人工标注或 FAIL_TO_PASS 测试数/补丁大小启发式）。候选规则：`<15 min`→easy、`15min-2h`→medium、`≥2h`→hard。若池中无 ≥2h 实例，则 Verified 子集全部 easy/medium、无 hard——可接受（hard 由 B 轨保证），但需在结果页/披露中写明「Verified 子集难度集中在 easy/medium」。注意 tasks.md 5.2 写「difficulty 映射 easy 等」语义含糊：是全部映射 easy，还是逐实例映射？需明确。

**③ L1「能在 Py3.12 现代 pytest 跑」的判据？** 候选判据清单（前后对比）：`python3.12 -m venv` 中 `pip install -e ".[test]"` 成功（无 py<3.12/old-numpy pin）+ FAIL_TO_PASS 测试在 base_commit 下红、打 gold.patch 后绿 + 单实例验证 <300s + 不依赖 Docker-only 环境。例如 requests-1142 的 `test_no_content_length` 可直接本地跑 → L1；某 sympy 实例若 `pip install` 需 numpy<2 则只能 L2。**关键耦合**：L1 资格判定本身需要一次试跑（= L3 自检），所以顺序应为「候选实例 → L3 金补丁试跑 → 顺带探明 L1 资格 → 按资格分配 L1/L2 验证路径」。design 未写明这一先后关系，tasks 5.3/5.4 并列，需确认流程顺序。

### OQ-1: `track` 字段落点（task.json 还是 manifest）

manifest 是 net-new 文件，runner 目前只扫 `*/task.json`。若 `track` 只在 manifest，新增任务需改 task.json + manifest 两处、结果页按 track 分组需 runner 读 manifest 关联；若 `track` 进 task.json，任务自描述、manifest 只声明覆盖矩阵。**具体场景**：新增 B 轨任务 `asterwynd-b-context-planning-001` 时，是 `task.json` 里写 `"track": "B"`，还是只在 `manifest.json` 登记？请拍板单一事实源，避免双写漂移。

### OQ-2: 覆盖矩阵统计口径 + 005/021 重写后的 track 归属 + 数据对账

**① 覆盖矩阵（5 场景列 + 7 能力列，每列 ≥1）统计哪些任务？** 若把 50 条 verified（全是 bug-fix 场景）计入，bug-fix 列被撑满、场景覆盖校验失去意义；建议矩阵只统计本地 A+B 任务，verified 单独披露。请拍板口径。

**② 005-bash-workspace / 021-lsp-diagnostics「按新架构改写」后 track？** 若 base_commit 仍为历史提交 → A 轨；若改为当前 HEAD 任务 → B 轨。数字对账：A=26−2（002/004→B）−(0 或 2)=22 或 24；B=12–16+(0 或 2)。design「本地场景任务约 35–40」对应 A+B=32–40。请拍板归属，落到 tasks 3.1。

**③ 数据对账修正**：design/proposal 引用 difficulty 分布 9/12/5，实测 9/13/4；`benchmarks/tasks/README.md` 写 23 任务已陈旧。C1 收尾（tasks 8.3）需按实测值修正 README/benchmark-plan 任务数与难度分布（含 README_EN 同步），避免新文档再次引入错误口径。

### OQ-3: difficulty 归一化对既有数据的迁移兼容

`from_dict` 无条件调 `validate()`，一旦 validate() 校验 difficulty∈{easy,medium,hard}，现有 10 fixture（`<15 min fix`）与 `gate-smoke-001`（`trivial`）**load 即 ValueError**，存量测试立即红。**具体前后对比**：现在 `load_task("benchmarks/tasks/swebench-psf__requests-1142")` 通过；改后不迁移则抛 `ValueError: difficulty must be one of easy/medium/hard`。请拍板：A) 同 PR 原子迁移 10 fixture 为 easy + gate-smoke 改 easy（推荐，真枚举）；B) validate() 对 difficulty 只 warn 不 error（弱校验，失去机械保证）；C) 保留原始桶字段 + 新增 `normalized_difficulty`（双字段，兼容最稳但 schema 冗余）。另：spec Scenario「任务未声明场景或难度 → 归入默认值」的「默认值」未定义——缺省 scenario 是 `None`（归「未标注」桶）还是具体枚举值？需定。

### OQ-4: spec-实现空窗与 C2 承接确认

C1 归档 + sync 后，`openspec/specs/benchmark/spec.md` 将含 `采样显式化`（`--repeat N` 3–5、seed 0..N-1、temperature 0.2）、`成本与延迟联合展示`（`$/resolved-task` + cache hit rate）、`失败归因与 fault_owner` 交叉表等 Requirement，但 C1 不实现（归 C2–C4）。**具体场景**：C1 合入后任何人 `uv run asterwynd benchmark --repeat 3` 看结果页，会发现没有 fault_owner 交叉表、没有 `$/resolved-task`——spec 声称能力与代码长期不一致（artifact checker 不校验 spec-vs-code，无人拦截）。请拍板：A) spec Requirement 文本加「实现归 C2 evaluation-metrics」状态注记（防误导）；B) C1 的 spec 同步延迟到 C2 合入后一并 sync；C) 接受「规格先行空窗」，但确认 C2–C4 已在 backlog 排期（当前 backlog 6 号条目只说 C1 先行解锁 C2–C4，未确认 C2 立项），否则空窗无限期。

## User Confirmation

（占位：grill-confirmation-gate 停轮后，主 session 转达的用户实质答复逐条记录于此；每条格式 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`。占位文本不计入确认。）

## 风险（design 自身 Risks 之外新发现）

- **R1 数据口径不实**：difficulty 分布引用 9/12/5 实测 9/13/4；`benchmarks/tasks/README.md`「23 任务」陈旧。不改则 C1 文档继续扩散错误口径。
- **R2 validate() 收紧连锁破坏**：`from_dict`→`validate()` 无条件，枚举校验一旦落地、10 fixture + gate-smoke 立刻 load 失败；tasks 2.2 与 5.2 必须同变更原子迁移，否则 CI 红。
- **R3 L1/L3 成本被低估**：L1 需本地 Py3.12 venv clone `external_repo`（gitee 镜像，可用性/速率风险）+ base_commit 检出 + 装依赖 + 打 test.patch 跑 FAIL_TO_PASS；50 条实例的 L3 自检要真跑一遍（Docker 镜像对旧 base_commit 可能 build 失败：pip 源/编译依赖）。design 只给 full-500 预算量级（$500–2,500），未单列 50 子集 + L3 的验证时间与成本。
- **R4 命名混淆**：10 fixture `category: bug_fix`（下划线）vs scenario 枚举 `bug-fix`（连字符），肉眼易混；重打标时需统一清理或明确 category→scenario 映射，否则 validate() 拒收或静默归错场景。
- **R5 覆盖矩阵维护漂移的诊断性**：manifest 为 net-new，新增任务忘登记时校验报「某能力列缺失」，错误信息必须可定位（报缺失列 + 提示可补任务），否则维护者无从下手。
- **R6 门禁/死锁自检（结论：无自死锁，但有两处注意）**：① 本 change 有 spec delta + tasks 全勾选，checker 强制 building-review.md + manifest——C1 走 `/review-loop` 可满足，无死锁；但 building-review 的「Spec 对齐」维度需区分 `[C2]` 文本不要求实现，审阅者若逐条对照 spec 断言实现会误报「未实现即验收」，需在 review prompt 里明确。② `[C2]` 标注仅是人读文本，checker 按 `[x]` 计数不识别——若 tasks 7.4 全勾，checker 认为实现完成，依赖审阅环节人工把关，无机械强制，接受为已知限制即可。
