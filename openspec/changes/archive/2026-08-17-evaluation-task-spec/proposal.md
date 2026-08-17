# Proposal: 评测任务集组成与任务 schema 扩展（evaluation-task-spec，C1）

关联跟踪 issue：[#154](https://github.com/Xingkai98/asterwynd/issues/154)（【feature】evaluation-task-spec：评测任务集组成与任务 schema 扩展）。父 map：[#144](https://github.com/Xingkai98/asterwynd/issues/144)（Wayfinder: Agent 评测升级）。

## Change Type

- primary: feature
- secondary: process

## Why

Wayfinder 地图 #144 已完成全部决策（G1 分层/G2 任务集/G3 指标/G4 落地形态/T1 协议/T2 叙事，9/9 票关闭）。现有 benchmark 基建完整（runner/VerifierAdapter/statistics/结果页，`benchmark-evaluation-depth` 已合入），但任务集是评测体系最薄的一层：

- **26 个本地任务全为历史重建型**（base_commit 为特性引入前提交），其中 4 个陈旧（002-sandbox-executor/004-benchmark-cli 目标文件被重构推翻、005-bash-workspace/021-lsp-diagnostics 部分陈旧）、2 个 gold.patch 为空（018-warning-passes/020-close-clients）、1 个弱评估（022-collaborative-context-audit，grep 关键词打分）。
- **10 个 swebench fixture 全为 `<15 min fix`**（Verified 最易档），requests 占 6/10，无中/难实例，无法支撑"评测升级"的难度梯度。
- **context-planning 能力层 0 任务**（R3 盘点），面试最想展示的"规划"能力没有任务样本。
- **spec 与业界方法论存在张力**：`任务支持显式能力分层` Requirement 要求任务级能力标签，但业界主流（Terminal-Bench/GAIA）是「场景 × 难度」双元结构、能力层放套件级覆盖矩阵（OpenHands Index 式）；`Pass@k 稳定性指标` 语义与 τ-bench pass^k（可靠性）混淆。

本 change 把任务集从"历史重建回归基线"升级为"场景×难度分层 + 三来源组合"，并把评测升级的完整规格（含 M1–M11 指标/方法 Requirement）落进 `benchmark` spec，作为 C2–C4 的需求来源。

## What Changes

- **任务 schema 扩展**：`TaskSpec` 新增 `scenario` 字段（`bug-fix`/`feature-dev`/`refactor`/`debug`/`integration` 5 枚举），`difficulty` 归一化为 3 档枚举（`easy`/`medium`/`hard`，swebench `<15 min fix` 映射到 easy）。能力层从任务级正交标签改为**套件级能力覆盖矩阵**（7 能力列：`tool-usage`/`context-planning`/`multi-step-solving`/`error-recovery`/`safety-boundary`/`long-term-memory`/`long-context`），随任务集 manifest 声明。
- **存量 26 去留重打标**（G2 Q2）：4 陈旧 → 002-sandbox-executor/004-benchmark-cli 重写为 B 轨当前 HEAD 任务、005-bash-workspace/021-lsp-diagnostics 按新架构改写；2 gold.patch 空 → 补参考实现；1 弱评估 → 补结构校验；其余 19–20 保留 A 轨并重打 `scenario`/`difficulty` 标签。
- **B 轨新增 12–16 条**（当前 HEAD 真实缺陷/增强，面试核心）：context-planning 0→3–5 条（最高优先）、long-term-memory +1、long-context +1–2 真实大仓库任务、safety-boundary 靠重写补齐、每场景至少 1–2 条、含 2–3 条 hard。
- **SWE-bench Verified 精选子集 50 条接入**：保留现有 10 fixture，从轻量+中等池（requests/flask/pytest + sympy/seaborn/pylint，115 条）逐条过滤 KNOWN_BAD 补齐；不含 django/sphinx 重实例；验证路径分级 L1 本地轻量 + L2 Docker harness（`SwebenchAdapter`）+ L3 金补丁自检；结果页带污染披露（OpenAI 2026-02 弃用 Verified：138 审计实例 59.4% 有实质缺陷）。
- **spec delta**（`openspec/specs/benchmark/spec.md`）：修订 `任务支持显式能力分层` Requirement（能力层移到套件级覆盖矩阵）；`Pass@k 稳定性指标` 改名 `pass^k` 并补 pass@1/pass@k/pass^k 三分定义；新增任务 schema（scenario/difficulty）、任务集组成（三来源）、Verified 子集接入、反作弊泄漏披露，以及 G3 M1–M11 指标/方法对应 Requirement（指标三分/采样显式化/成本-延迟联合/失败归因/报告元组/污染披露/反作弊披露/配对比较/f2p-p2p 保留/小 N 声明/过程效率——实现归 C2 `evaluation-metrics`）。
- **反作弊披露**：A 轨历史重建任务在完整 git 历史中运行（agent 可见后续提交），本期接受开放性并在结果页/面试材料披露，不冒充公平评测；shallow/mirror 克隆截断留作后续加固项。

## Capabilities

### New Capabilities

无。全部为既有 `benchmark` 能力域的增量扩展，不引入新 capability。

### Modified Capabilities

- `benchmark`: 任务 schema 扩展（`scenario`/`difficulty` 枚举）、任务集组成（三来源 ~90）、Verified 50 子集接入、能力分层口径修订（任务级→套件级覆盖矩阵）、pass^k 改名与三分定义、M1–M11 指标/方法 Requirement 落定；全部以 ADDED/REVISED 方式并入 `benchmark` spec，既有 `status`/`reason`/`task_family`/`category` 语义保持不变（向后兼容）。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 非平凡 change（走 grill），任务集组成与分层必须对照业界主流（SWE-bench Verified、Terminal-Bench、GAIA、OpenHands Index、τ-bench）确认口径，避免自造一套不可对外引用的任务组织方式。
- research questions:
  1. 业界 coding-agent benchmark 如何组织任务？（主组织轴/难度轴/能力层位置）
  2. SWE-bench Verified 的已知坏实例（KNOWN_BAD）如何过滤？验证路径如何分级绕过内存墙？
  3. 业界如何做任务集的"能力覆盖"表达（OpenHands Index / VersaBench 覆盖矩阵）？
  4. 指标语义三分（pass@1/pass@k/pass^k）的业界出处与有效性条件？
- findings: 本地 `.dev/reference-repos.txt` 不存在，本地参考仓库不可用，已在 findings 记录该事实。作为替代依据，map 已完成的调研结论直接引用（调研明细见对应 ticket resolution comment，均为永久 GitHub 记录）：R1（[#145](https://github.com/Xingkai98/asterwynd/issues/145)，SWE-bench 协议/τ-bench pass^k/cost@pass 等 2025-2026 业界共识）、R2（[#146](https://github.com/Xingkai98/asterwynd/issues/146)，Verified 子集可行性/L1/L2/L3 路径/内存墙/KNOWN_BAD）、R3（[#147](https://github.com/Xingkai98/asterwynd/issues/147)，26+10 资产盘点/陈旧任务/gold.patch 空）、G1（[#148](https://github.com/Xingkai98/asterwynd/issues/148)，主组织轴=场景/难度第二轴/能力层套件级覆盖矩阵，业界无任务级场景×能力二维矩阵先例）。核心结论：任务组织用「场景 × 难度」双标签（Terminal-Bench 式）；能力层放套件级覆盖矩阵（OpenHands Index 式）；指标三分与 pass^k 为 τ-bench 事实标准；Verified 子集接入成本最低、内存墙用 L1/L2 分级处置。
- design impact: 任务 schema 扩展（scenario/difficulty）、任务集三来源配比、能力层套件级覆盖矩阵、Verified 子集接入路径（L1/L2/L3）为设计阶段输入；M1–M11 Requirement 文本落进 C1 spec delta、实现归 C2。

## Impact Analysis

- **能力域**: `benchmark`（任务 schema 与任务集组成扩展）。
- **代码**: `benchmarks/`（`task_schema.py` 增加 `scenario` 字段 + `difficulty` 归一化校验、`benchmarks/tasks/` 下 26 个本地任务重打标 + B 轨新增 + Verified 50 fixture 生成、`adapters.py` 或辅助脚本支持 Verified 子集接入与 L1 本地验证路径、任务集 manifest 声明套件级能力覆盖矩阵）。
- **测试**: 新增 `tests/benchmark/` 任务 schema 校验（scenario 枚举/difficulty 归一化）、任务集 manifest 覆盖矩阵完整性、Verified 子集 fixture 元数据校验；所有新增/改写任务需有测试（B 轨任务走测试先行，A 轨重打标不改逻辑不需新测试但跑存量回归）；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
- **文档**: `openspec/specs/benchmark/spec.md` 同步（ADDED/REVISED requirements）、`docs/openspec-change-backlog.md` 更新、`docs/benchmark-plan.md` 任务数口径修正（34→26 + 三来源目标）、README 如涉及任务数同步（含 README_EN）。
- **基准**: 不改变既有任务 schema 的必需字段与既有 `benchmark` 规格行为；`scenario` 缺省时回退默认、`difficulty` 现有值归一化映射，全部向后兼容。
- **流程（process）**: 引入任务集组成约定——三来源配比、scenario×difficulty 双标签口径、套件级能力覆盖矩阵表达、Verified 子集过滤规则；后续评测任务新增需遵循此约定。
