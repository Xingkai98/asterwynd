# Design: evaluation-task-spec（C1）

## Context

Asterwynd 现有 benchmark（`openspec/specs/benchmark/spec.md`）已经具备：任务目录读取、多 agent runner、每任务 artifact（result/trace/runner.log）、`status + reason` 统一语义、Docker-based SWE-bench harness、VerifierAdapter 抽象（`benchmarks/adapters.py`，`task_family` 为 key 走 registry）、统计（`benchmarks/statistics.py` bootstrap CI + pass@k）、结果页（`benchmarks/report.py`）。`benchmarks/task_schema.py` 的 `TaskSpec` 已有 `category`/`difficulty`/`task_family`/`execution_environment`/`instance_id`/`dataset_name`/`dataset_split` 字段。

Wayfinder map #144 的决策（G1/G2/G3/G4/T1/T2，9/9 票关闭）为本次变更提供了全部上层决策：

- **G1 分层**：任务级 `scenario` + `difficulty` 双标签（主组织轴=场景）；能力层放**套件级覆盖矩阵**（OpenHands 式），不做任务级二维正交（业界无先例）。
- **G2 任务集**：三来源 A 轨历史重建 20–24 + B 轨当前演进 12–16 + Verified 50 ≈ 85–95（T1 校正为 82–90）；存量去留规则；B 轨补缺目标；反作弊本期接受开放性 + 披露。
- **G3 指标**：M1–M11（指标三分/采样/成本/失败归因/报告元组/污染披露/反作弊披露/配对比较/f2p-p2p/小N/过程效率），spec Requirement 文本落 C1、实现归 C2。
- **G4 落地**：C1→C2→C3→C4 串行主链，C3/C4 在 C2 后并行；spec 增补 `openspec/specs/benchmark/spec.md`，不新建 domain。

当前任务集短板（R3 盘点）：26 本地全为历史重建型、4 陈旧、2 gold.patch 空、1 弱评估；10 swebench fixture 全 `<15 min fix` 且 requests 6/10；context-planning 0 任务。当前 spec 的 `任务支持显式能力分层` Requirement 要求任务级能力标签（与 G1 决策相悖）、`Pass@k 稳定性指标` 语义与 pass^k 混淆（与 G3 M1 相悖）。

## Goals / Non-Goals

**Goals:**

- 任务 schema 支持 `scenario`（5 枚举）× `difficulty`（3 档归一化）双标签，向后兼容既有任务。
- 任务集升级为三来源组合（A 轨回归基线 + B 轨面试核心 + Verified 50 外部对标）≈ 82–90 条。
- 存量 26 按 G2 规则去留/重打标；B 轨补齐 context-planning 等能力空白。
- Verified 50 子集接入，验证路径 L1/L2/L3 分级（绕内存墙），结果带污染披露。
- spec delta 落定评估升级完整规格（能力分层修订 + pass^k 改名 + M1–M11 Requirement），作为 C2–C4 需求来源。

**Non-Goals:**

- **不改指标实现**：pass^k 聚合、cost@pass cache-aware、fault_owner、配对比较等实现归 C2 `evaluation-metrics`；本 change 只落 Requirement 文本。
- **不做协议/报告**：运行协议文档、结果页披露（元组/污染/反作弊渲染）、compare 增强归 C3 `evaluation-protocol-reporting`。
- **不改面试叙事**：Q13/W07/FINAL/resume 改动归 C4 `evaluation-narrative`。
- **不实现反作弊加固**：shallow/mirror 克隆截断历史留作后续项（G2 Q5），本期只披露。
- **不引入 Terminal-Bench / τ³**（G2 Q6 本期不纳入）；不跑全量 Verified 500（预算 $500–2,500，资源升级后再跑）。
- **不推翻既有基建**：VerifierAdapter/statistics/report/harness 全部保留，在其上增补。

## Decisions

### Decision D1: 任务 schema 扩展 `scenario` 字段，`difficulty` 归一化为 3 档枚举

**方案**：`TaskSpec` 新增 `scenario: str | None`，取值 `bug-fix`/`feature-dev`/`refactor`/`debug`/`integration`（G1 5 场景枚举）；`difficulty` 现有自由字符串归一化为 `easy`/`medium`/`hard` 3 档（本地任务已用 easy/medium/hard，swebench `<15 min fix` 映射为 `easy`）。`validate()` 对填写的值做枚举校验；缺省 `scenario=None` 时兼容（`from_dict` 不强制），供评测汇总时归入默认场景或跳过。

**备选**：
- 任务级能力字段（沿用 spec 现要求）。被拒：G1 调研确认任务级「场景×能力」二维矩阵无业界先例、标注成本高、空单元多。
- `difficulty` 保留自由字符串。被拒：无法机械校验、按难度档聚合不稳（swebench `<15 min fix` 与 easy/medium/hard 无法直接比较）。

**理由**：Terminal-Bench 式显式双标签最干净；`scenario` 主组织轴 + `difficulty` 第二轴符合业界主流（G1 结论）；缺省兼容保证既有 36 任务不破。

### Decision D2: 能力层从任务级移到套件级覆盖矩阵

**方案**：修订 spec `任务支持显式能力分层` Requirement——任务 schema 不再要求任务级能力字段；能力层改为**套件级覆盖矩阵**：任务集 manifest（如 `benchmarks/tasks/manifest.json` 或任务集级声明）声明每个任务/任务组覆盖的 7 个能力列（`tool-usage`/`context-planning`/`multi-step-solving`/`error-recovery`/`safety-boundary`/`long-term-memory`/`long-context`），结果页按套件聚合展示能力覆盖度。既有 `category` 字段保留为信息性主题标签（tools/security/agent 等），不作为能力层载体。

**备选**：
- 继续任务级能力标签（现状）。被拒：G1 确认无业界先例，且 R3 显示 26 任务从未真正打上 benchmark-evaluation-depth 的能力枚举（category 仍是主题标签）。
- 能力层做成独立第三轴。被拒：与场景轴大量空单元，成本高。

**理由**：OpenHands Index / VersaBench 的聚合映射式是业界把能力层接进评测的主流做法（G1 结论 2）；覆盖矩阵在 manifest 一层声明、可机械校验每能力列至少 1 任务，比任务级标注便宜且可维护。

### Decision D3: 任务集三来源配比（≈82–90）

**方案**：A 轨历史重建 20–24（存量去留后，回归基线）+ B 轨当前演进 12–16（新增，面试核心）+ Verified 精选子集 50（外部对标）≈ 总 82–90。本地场景任务约 35–40。三来源语义分立在任务集 manifest 中标 `track: A|B|verified`。

**备选**：单来源扩量。被拒：A 轨回归基线 + B 轨面试亮点 + Verified 外部对标是 G2 用户确认的组合，三来源各有定位不可缺。

**理由**：G2 Q1 用户「按推荐」确认；A 轨定位回归基线（诚实披露反作弊局限）、B 轨展示当前能力、Verified 提供业界可比数字。

### Decision D4: 存量 26 去留与重打标

**方案**（G2 Q2）：
- **4 陈旧**：`002-sandbox-executor`、`004-benchmark-cli`（目标文件彻底消失）→ **重写为 B 轨当前 HEAD 任务**（002 改为沙箱后端的命令执行验证、004 改为 agent/main.py 的 benchmark CLI 入口）；`005-bash-workspace`、`021-lsp-diagnostics`（目标文件部分存在）→ **按新架构改写**（005 改为沙箱/命令守卫的工作区边界、021 改为 `agent/tools/lsp.py` 的诊断工具）。
- **2 gold.patch 空**（`018-warning-passes`、`020-close-clients`）→ **补参考实现**；若成本高（需逆向推导已合入行为），降级并入评测基建任务（作为非独立能力任务）。
- **1 弱评估**（`022-collaborative-context-audit`，grep 关键词打分）→ **补结构校验**（确定性断言审计报告的关键章节存在且格式正确），或改造成子 agent 编排评估用例。
- **其余 19–20** 保留 A 轨，重打 `scenario`/`difficulty` 标签（每任务按 issue.md 的实际改动类型归入 5 场景之一、按预期解决投入定难度）。

**理由**：陈旧任务目标文件已变，跑了也是过时架构的回归，价值低且误导；重写为 B 轨把成本变成当前能力证据。

### Decision D5: B 轨新增任务设计（12–16 条，context-planning 优先）

**方案**（G2 Q4）：新增 B 轨任务满足能力补缺目标：
- **context-planning 0→3–5 条**（最高优先）：设计为"给出目标 + 部分上下文，agent 需先构建/检索仓库地图再规划多步修改"的任务（如跨文件 feature 实现、需要先 repo-map 定位再改的任务），task schema 打 `scenario` + 覆盖矩阵 `context-planning` 列。
- **long-term-memory +1**（到 3）：需 agent 在会话中写入长期记忆并在后续步骤复用的任务。
- **long-context +1–2**：真实大仓库任务（利用本地已有大文件/模块）。
- **safety-boundary** 靠 002/005 重写补齐。
- 每场景（bug-fix/feature-dev/refactor/debug/integration）至少 1–2 条；含 2–3 条 hard。
- 具体任务清单（id/问题描述/验证方式/gold patch）为**开放问题 OQ-B1**，由 grill 追问 + 用户确认后落 tasks 实现。

**理由**：context-planning 当前 0 任务是面试最明显缺口（G2 Q4 用户确认最高优先）；每场景至少 1–2 条保证覆盖矩阵无空行。

### Decision D6: Verified 50 子集接入与 L1/L2/L3 验证路径

**方案**（G2 Q3 + R2 组合 A）：
- **构成**：保留现有 10 fixture（requests/flask/pytest 轻量实例）→ 从 Verified 轻量+中等 repo（requests/flask/pytest/sympy/seaborn/pylint 共 115 条）逐条过滤 KNOWN_BAD 补齐至 50；**不含 django/sphinx** 重实例（测试慢、权重失真）。
- **验证路径分级**（R2 组合 A）：L1 本地轻量（能在 Py3.12 现代 pytest 跑的实例用本地 test_command 验证，免 Docker）；L2 Docker harness（`SwebenchAdapter`，需 ≥8 GiB 内存 + `uv sync --extra dev`）；L3 金补丁自检（所选子集先跑 gold.patch 确认可复现，剔除 flaky/坏实例，对齐 SWE-rebench）。
- **L1/L3 顺序耦合（grill 追问）**：L1「能在 Py3.12 现代 pytest 跑」的资格判定本身需要一次试跑（即 L3 自检），流程顺序为「候选实例 → L3 金补丁试跑 → 顺带探明 L1 资格 → 按资格分配 L1/L2 验证路径」，tasks 5.3/5.4 按此顺序执行。
- **污染披露**：结果页/报告带注记「OpenAI 2026-02 弃用 Verified：审计 138 实例 59.4% 有实质缺陷」，不当金标准；子集风险注记（KNOWN_BAD 过滤、现有 10 fixture 偏置、数据集版本 + swebench 包版本钉住 4.1.x）。
- 子集 50 的具体实例选择（从 115 过滤后的清单）为**开放问题 OQ-V1**。

**理由**：R2 可行性结论 Verified 子集接入成本最低（adapter + 缓存 + 镜像就绪）；L1/L2/L3 分级处置内存墙使本期可跑；污染披露是 G3 M6 硬要求。

### Decision D7: 反作弊泄漏披露（不做加固）

**方案**：A 轨历史重建任务在 detached worktree 运行，复用完整 git 对象库，agent 理论上可 `git log --all` 看到 base_commit 之后的提交（答案含于后续提交）。本期**接受开放性并披露**：任务集 manifest/结果页标注 A 轨定位"回归基线、非公平评测"，披露任务集来源（本仓库 git 历史生成）、时间范围、训练 cutoff 未知性。B 轨（当前 HEAD）与 Verified 子集不受此影响。

**备选**：本期实现 shallow/mirror 克隆截断历史。被拒：G2 Q5 已定本期接受开放性，加固由 G4 后决定；改造 runner 克隆语义改动面大。

**理由**：诚实边界 > 假装公平（G3 M7 + T2 叙事第 7 加分点"反作弊诚实边界"）；披露成本近零，加固成本高。

### Decision D8: spec delta 承载完整评估规格，实现分 C2–C4

**方案**：C1 的 spec delta 落定评估升级**完整 Requirement 文本**：修订 `任务支持显式能力分层`（D2）、`Pass@k 稳定性指标` 改名 `pass^k` 并补 pass@1/pass@k/pass^k 三分定义（G3 M1）、新增任务 schema/任务集组成/Verified 子集/反作弊披露 Requirement（本 change 实现），以及 G3 M1–M11 的指标/方法 Requirement（**本 change 只落文本不实现，实现归 C2**）。C2 `evaluation-metrics` 为纯实现 change（statistics/models/adapters），其 proposal 引用本 change 落定的 Requirement。

**理由**：需求先行（AGENTS.md）：规格先于实现；G4 明确 M1–M11 Requirement 落 C1。C1 的 tasks 将区分"规格落定"与"任务集实现"两类任务，metrics 实现任务在 C1 中标记为"归 C2"。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 非平凡 change（走 grill），任务集组成与分层需对照业界主流确认口径。
- research questions: 同 proposal（4 项）。
- findings: 本地 `.dev/reference-repos.txt` 不存在，本地参考仓库不可用（已记录）。替代依据为 map 已完成的 R1/R2/R3/G1 调研（详见 proposal findings）。核心结论：① 任务组织主流为「场景/领域 + 难度」双元结构（Terminal-Bench 式必填枚举最干净；GAIA 难度一级轴；Verified 人工时间桶），任务级「场景×能力」正交矩阵无先例；② 能力层主流接法为套件级覆盖矩阵（OpenHands Index 5 域 / VersaBench 5 类）或"能力即场景"（METR/GAIA/Preparedness），本设计选覆盖矩阵（D2）；③ Verified 子集接入成本最低（R2），KNOWN_BAD 最少安全排除 28 条，轻量+中等池 115 条，内存墙用 L1/L2 分级处置；④ 指标三分（pass@1/pass@k/pass^k）中 pass^k 为 τ-bench 事实标准（G3 M1），spec 改名与其对齐。
- design impact: 本设计全部决策（D1–D8）来自 map 已确认决策；无新增调研依赖。

## Risks / Trade-offs

- **[B 轨具体任务清单未定] → 作为开放问题 OQ-B1 由 grill 追问、用户确认后落 tasks；实现阶段测试先行，避免无验证的"任务"。**
- **[Verified 50 具体实例选择未定] → 开放问题 OQ-V1；实现阶段 L3 金补丁自检剔除 flaky/坏实例，宁可子集略小于 50 也不混入坏实例。**
- **[4 陈旧任务重写成本高] → 2 gold.patch 空若逆向推导成本高，降级并入评测基建任务（D4 已给降级路径），不硬凑。**
- **[能力层覆盖矩阵维护漂移] → manifest 机械校验每能力列至少 1 任务，C1 tasks 加该校验测试。**
- **[difficulty 归一化口径主观] → 3 档锚定预期解决投入（R3 现有 easy/medium/hard 分布 9/13/4 保留，grill 实测校正 9/12/5），swebench `<15 min fix`→easy 映射在 manifest 记录。**
- **[spec delta 大（含 M1–M11 文本）] → tasks 明确区分"规格落定"（本 change 完成）与"指标实现"（归 C2），避免审阅误判未实现即已验收。**
- **[A 轨反作弊开放被面试追问] → 披露文案（结果页 + 面试叙事）明确"回归基线定位"，诚实边界是加分项非减分项（G3 M7）。**

## Pre-Implementation Review

独立零记忆 grill 已完成（run id `a98e752e1a6c61309`，2026-08-17，产出 `reviews/grill-design.md`）。

**已确认决策**（≥3 条）：D1 双标签方向、D2 能力层移到套件级覆盖矩阵、D3 三来源配比、D7 反作弊本期披露、D8 spec 先行编排，全部确认；D4 附 005/021 track 归属问题（OQ-2）、D5 附 B 轨清单边界（OQ-B1）、D6 附实例选择与 L1/L3 顺序（OQ-V1）。

**必须修改（已整合进本设计）**：
- 难度分布引用 9/12/5 实测为 **9/13/4**（grill 核验 + 本机复核），已在 Risks 节修正；`benchmarks/tasks/README.md`「23 任务」陈旧口径在 tasks 8.3 一并修正（含 README_EN）。
- D6 补 **L1/L3 顺序耦合**：L3 金补丁试跑先于 L1 资格判定，tasks 5.3/5.4 按序执行。
- `validate()` 收紧对既有 10 fixture（`<15 min fix`）与 gate-smoke（`trivial`）的连锁破坏 → 归 **OQ-3**（迁移策略待用户拍板，tasks 2.2/5.2 需同变更原子落地）。
- spec 落定与实现之间空窗期风险 → 归 **OQ-4**（C2 承接待用户确认）。

**Open Questions**（**已全部确认**，用户 2026-08-17「按推荐」答复，逐条记录见 `reviews/grill-design.md` `## User Confirmation`）：
- **OQ-B1** 已确认：B 轨允许基于当前仓库构造的合成任务；context-planning 按 CP-1~CP-4 形态落 3–5 条；long-context 采用「强制大读取 + 小改动」形态（验证走确定性测试）；hard 档 = CP-2 + track 分组 + 002/004 重写。
- **OQ-V1** 已确认：40 条配比 requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8；difficulty 逐实例映射 `<15min`→easy/`15min-2h`→medium/`≥2h`→hard；L1 判据 = Py3.12 依赖安装 + FAIL_TO_PASS 红绿 + <300s + 不依赖 Docker。
- **OQ-1** 已确认：`track` 写进 `task.json`（单一事实源），manifest 只声明能力覆盖矩阵。
- **OQ-2** 已确认：覆盖矩阵只统计本地 A+B；005/021 改写后归 B 轨（A≈22、B≈14–18）；口径按实测 9/13/4 修正。
- **OQ-3** 已确认：方案 A 同 PR 原子迁移 fixture→easy + gate-smoke→easy；缺省 scenario 归「未标注」桶。
- **OQ-4** 已确认：spec Requirement 加「实现归 C2」注记；C2 已在 backlog 第十一批排期，收尾提醒主 session 跟进。

## Testing Strategy

- 单元测试（`tests/benchmark/`）：`TaskSpec` schema 校验（scenario 枚举、difficulty 归一化、缺省兼容）；任务集 manifest 覆盖矩阵完整性（每能力列 ≥1 任务、每场景列 ≥1 任务）。
- 存量回归：重打标不改逻辑，26 本地任务现有测试与 benchmark smoke 不回归。
- B 轨/重写任务：测试先行（先写验证断言/gold patch，再实现任务）；每任务至少一条确定性验证命令。
- Verified 子集：fixture 元数据校验（instance_id/dataset 字段齐全、KNOWN_BAD 不含）、L3 金补丁自检脚本；L2 Docker 路径在内存达标环境跑 smoke。
- 涉及 benchmark 路径必须覆盖 benchmark 层级测试；每个 bug fix 新增回归测试。
