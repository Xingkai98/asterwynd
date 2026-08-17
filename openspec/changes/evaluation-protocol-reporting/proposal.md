# Proposal: 运行协议文档 + 结果页披露 + compare 增强（evaluation-protocol-reporting，C3）

关联跟踪 issue：[#159](https://github.com/Xingkai98/asterwynd/issues/159)（【feature】evaluation-protocol-reporting）。系列父级：[#144](https://github.com/Xingkai98/asterwynd/issues/144)｜ follow-up：[#156](https://github.com/Xingkai98/asterwynd/issues/156)。

## Change Type

- primary: feature
- secondary: process

## Why

C1（#154）与 C2（#157）已合入：任务 schema（scenario/difficulty/track）与指标层（pass^k/cache-aware 成本/fault_owner/配对比较）就绪。C2 的 spec 明确「结果页渲染义务（`$/resolved-task`/cache hit rate/定价表版本展示、reason × fault_owner 交叉表、报告元组、SWE-bench 污染注记、部分成功档、采样参数、小样本声明、过程效率展示）归 C3」。当前缺口（实测）：

- **无运行协议文档**：T1 `eval-run-protocol-2026-08-17.md` 只在 wayfinder-research worktree 的 `.gitignore` 调研区，仓库正式文档没有可执行的评测运行协议（任务集口径/模型/采样/预算/对照/artifact 布局/自洽门禁）。
- **结果页缺披露渲染**：`benchmarks/report.py` 有基础按层聚合/CI/延迟成本，但没渲染报告元组、SWE-bench 污染注记、反作弊泄漏披露、fault_owner 交叉表、$/resolved-task、部分成功档。
- **compare 报告缺增强**：`compare.py` 只输出点估计对比表，未接入 C2 的配对比较统计函数，run 元数据（模型/日期/成本）不完整。
- **CLI 缺预算/预检/自洽**：`--budget-cap`/`--no-cap`（用户已定可配置可取消）、`--preflight`（内存 <8GiB 走 L1 路径）、`self_check.py` 五门禁均不存在。

面试被追问「评测怎么跑、数字怎么披露、怎么保证自洽」时，缺协议文档 + 缺披露渲染会让升级后的指标层无法产出可引用的结果页。

## What Changes

- **运行协议文档**：T1 转正为 `docs/benchmark-run-protocol.md`（中文），含任务集 82–90 口径、模型/采样（repeat 5 + seed 0..4 + temp 0.2）、预算 `--budget-cap`（可配置可取消 `--budget-cap 0`）、对照口径（换 agent / 换 model 分开）、artifact 布局（run.json 元组 + trace.json + summary + protocol.json）、自洽五门禁、reproduction 步骤。
- **结果页披露渲染**（`benchmarks/report.py` + 结果页模板）：报告元组（model/harness/task_set_hash/grader/成本口径）、SWE-bench 污染注记（保留条件域，OpenAI 2026-02 弃用 + 138 实例 59.4% 缺陷）、反作弊泄漏披露（A 轨回归基线定位）、reason × fault_owner 交叉表、$/resolved-task + cache hit rate + 定价表版本、f2p/p2p 部分成功档、采样参数、小样本声明、过程效率展示。
- **compare 报告增强**（`benchmarks/compare.py`）：接入 C2 的 `paired_comparison` 渲染 per-task delta/差异 CI/win-rate；run 元数据补齐（模型/日期/成本口径）。
- **CLI**（`agent/main.py` benchmark）：`--budget-cap <USD>`/`--no-cap`（默认建议 $50，超限标 `incomplete`）；`--preflight`（Docker daemon + 内存检查，<8GiB 走 L1 本地路径）。
- **`scripts/self_check.py` 五门禁**：同模型同 harness 复现、seed 复现、失败归因闭环（fault_owner + 校准证据 + reason×owner 交叉表）、披露段齐全（污染注记 + 严格 resolved + f2p/p2p 保留 + A 轨泄漏 + 小 N 声明）、报告元组完整。
- **C3 前置**：Verified 40 fixture 生成（#156）在数据可达环境执行 `build_subset`；本环境不可达记录为范围外阻塞项，不阻塞本 change 其余交付。

## Capabilities

### New Capabilities

无。全部为既有 `benchmark` 能力域的协议/渲染扩展。

### Modified Capabilities

- `benchmark`: 结果页渲染义务（C2 spec 边界注记的 10 项）落地、运行协议文档、compare 配对渲染、预算/预检 CLI、self_check 五门禁；spec delta 以 MODIFIED 方式把「渲染归 C3」边界注记转为已实现。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 非平凡 change（走 grill），运行协议与披露口径需对照业界主流确认（SWE-bench 披露、预算曲线、self-check 门禁），避免自造不可引用的披露格式。
- research questions:
  1. 业界 benchmark 结果页/报告如何披露模型/harness/成本/污染（报告元组）？
  2. 预算受限评测（budget-limited）与自洽门禁（self-check）的业界做法？
  3. compare/配对比较报告如何渲染才可引用？
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录不可用）。替代依据为 map 调研结论：G3 决议（#150，4 独立审阅 agent 对照业界验证）M5 报告元组/M6 污染披露/M7 反作弊披露口径；R1（#145）SWE-bench 协议与披露；T1（#152）运行协议五门禁；T2（#153）面试叙事对披露的引用。披露格式与协议口径已在 C1/C2 spec 落为 Requirement 文本，本 change 按文本渲染与文档化。
- design impact: 渲染清单（10 项）与协议五门禁为设计输入；见 design.md D1–D8。

## Impact Analysis

- **能力域**: `benchmark`（结果页渲染 + 运行协议 + compare 增强 + CLI）。
- **代码**: `benchmarks/report.py`（披露渲染）、`benchmarks/compare.py`（配对渲染 + 元数据）、`agent/main.py`（`--budget-cap`/`--preflight`）、新增 `scripts/self_check.py`。
- **文档**: 新增 `docs/benchmark-run-protocol.md`（T1 转正）；`openspec/specs/benchmark/spec.md` 同步（MODIFIED 边界注记→已实现）；`docs/openspec-change-backlog.md` 更新。
- **测试**: 新增 `tests/benchmark/` 披露渲染（golden 片段）、compare 配对渲染、CLI `--budget-cap`/`--preflight`、self_check 五门禁各门禁单元测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
- **基准**: 不改变既有结果页/compare 输出结构（在既有基础上扩展）；`--budget-cap` 缺省不设上限保持既有行为；`--preflight` 新增不破坏既有参数。
- **流程（process）**: 运行协议与自洽门禁落地——后续评测按 `docs/benchmark-run-protocol.md` 执行、结果页按披露清单渲染、合入前跑 self_check。
