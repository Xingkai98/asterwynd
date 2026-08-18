# 评测运行协议（自洽数字蓝本）

> 上游决策：G2（任务集组成）、G3（指标与方法）、G4（落地形态）；跟踪 issue：本协议由 [evaluation-protocol-reporting（#159）](https://github.com/Xingkai98/asterwynd/issues/159) 转正。
> 用途：按本协议执行评测，产出「面试可引用、逻辑自洽」的真实数字。**本文件只定协议；是否实际跑数、预算大小由使用者按需决定。**

## 1. 目标数字形态（面试要什么）

按本协议产出的数字全部附报告元组 + bootstrap CI + 固定 seed 可复现：

| 数字 | 来源 | 面试用法 |
|---|---|---|
| 本地场景任务 pass@1（按能力层覆盖矩阵汇总） | B 轨 + A 轨（本地） | 展示 agent 能力面（tool-usage/context-planning/…） |
| SWE-bench Verified 精选子集 pass@1 / pass@k / pass^k / cost@pass | Verified 精选子集 | 对外对标数字（**带污染披露**，不当金标准） |
| 对照：同任务同 harness 换 agent 的 per-task delta + 差异 CI + win-rate | 对照运行 | 「同一 harness 下我们的 agent vs 参照」头条叙事 |
| 成本-精度对照（本地主力 vs API 前沿） | 双模型跑 | 「成本差一个数量级」叙事（Claw-SWE-Bench 实证：GPT-5.5 78%@$1399 vs DeepSeek-V4-Flash 70.3%@$8.2，~170×） |

## 2. 任务集口径

| 轨 | 数量 | 角色 | 验证路径 |
|---|---|---|---|
| **A 轨·历史重建**（存量去留后） | 20–24 | 回归基线 | 本地（`git worktree add --detach <base_commit>`） |
| **B 轨·当前演进**（新增） | 12–16 | **面试核心** | 本地，确定性 VerifierAdapter |
| **SWE-bench Verified 子集** | 50 | 对外对标 | L1 本地轻量 + L2 Docker（内存墙混合路径） |
| **合计** | **82–90**（G2 记为 85–95，实际边界 82–90） | | |

- 具体任务清单由 C1 `evaluation-task-spec` 交付；本协议只定边界与优先级。
- Verified 子集：从轻量+中等池 115 条（requests/flask/pytest/sympy/seaborn/pylint）逐条过滤 **KNOWN_BAD**（最少排除 28 条）后选 50，**不含 django/sphinx 重实例**。
- A 轨自评泄漏：detached worktree 复用完整对象库，agent 可 `git log --all` 见答案提交——结果页**必须披露**该泄漏（回归基线定位），shallow/mirror 截断为后续可选加固。
- **Verified 40 fixture 前置**：SWE-bench Verified 精选子集 40 条新 fixture 需在数据可达环境执行 `build_subset` 生成（跟踪 [#156](https://github.com/Xingkai98/asterwynd/issues/156)）；本环境数据不可达期间不阻塞本地任务与协议/渲染/对照交付。

## 3. 模型与采样

| 角色 | 默认 | 说明 |
|---|---|---|
| **本地主力**（主数字） | `--provider anthropic --model deepseek-v4-flash`（DeepSeek Anthropic 兼容端点） | 本地实测可用（~1.8s/调用），成本近零，可控复现；面试可讲「70% 量级精度 @ 个位数美元」 |
| **API 前沿对照** | `--model claude-*`（如 sonnet-5 / opus-5，可配置） | 讲「同 harness 下成本-精度对照」；成本受预算约束 |

- 模型参数由 CLI 覆盖，**不写死**：`--provider` / `--model` / `--model-version`（报告元组字段）。
- 采样约定：`--repeat 5`（N≥3 才有 pass^k 意义）、固定 seed 集合 `--seeds 0 1 2 3 4`、`--temperature 0.2`（pass@1 口径）；0.8 探索档标为后续（注入多样性才让 pass^k 有区分度）。
- 每轮记录 `(temperature, seed, model version)`；可复现性声明限定 **(model version, provider, harness) 内**。
- **无效轮次不进分母**：`unsupported` / `approval-unavailable` / `docker-unavailable` 不计入 pass@1 与 pass^k 的分母，也不当失败。

## 4. 成本预算（可配置、可取消）

**用户决策（2026-08-17）**：预算**可配置**，也**可以取消**；cap 按**单轮（per-round）**口径，任一轮累计成本超过 cap 即停止剩余轮次。

- **缺省不设上限**，保持既有行为；`$50` 为协议文档建议值（来自 API 对照的预算约束：本地任务成本近零、大头是可被 cap 截断的 API 前沿对照；按 R2 的 $0.5–5/实例粗算 250 次 instance-run 约 $125–1,250，全量跑会超出）。
- 接口：`--budget-cap <USD>` 设置单轮上限；`--budget-cap 0`（或 `--no-cap`）**取消上限**；`0`/未传/`--no-cap` 三者等价取消，负数拒绝。
- **超限行为**：停止剩余轮次；当前轮已启动的并发任务自然完成（不 cancel，避免半截 trace）；当前轮结果标 `truncated`（`run.json` 的 `truncated: true`）。已发生成本照常计入 cost@pass 分母（口径不变，只注明截断）。compare 配对剔除 truncated 轮，pass^k 分母不含 truncated 轮。
- **成本口径**：cache-aware 四档定价（fresh input / cache read / cache write / output）+ run 级 `cache_read_tokens`/`cache_write_tokens`；`$/resolved-task` = 层内全部 run 总成本（含失败 run）/ resolved 数；**声明「仅 LLM token 计费、不含沙箱/CI/计算」**；本地 self-hosted 模型不计费（或标注估算口径）。定价表附版本与日期。
- 预算策略（cap 值与是否启用）**随报告披露**，跨 agent 比较时预算必须对齐（对标 vexp $3/task cap）。

## 5. 对照口径

- 原则：**同任务、同 harness、仅换一个变量**；声明 (model, harness, task_family) 元组，数字**仅在同一 harness 内可比**。
- 两种对照口径**分开写**，不要混读：
  1. **换 agent 对照**（默认）：Asterwynd 主 agent vs 参照 agent（如 `--agent claude`，现有 runner；或开源 agent，可配置），同一任务集、同一 VerifierAdapter 判分、同 `--repeat N` + 同 seed 集合。命令：`uv run python benchmarks/compare.py <run-dir> [run-dir ...]`，输出 per-task delta + 差异 CI（paired bootstrap / McNemar）+ win-rate。
  2. **换 model 对照**（成本-精度叙事）：同 agent、同任务、同 harness、同 repeat/seed，跑本地主力 vs API 前沿，输出 cost@pass 对照。

## 6. artifact 布局 + 报告元组

```
benchmarks/runs/<run-id>/
├── run.json            # 报告元组（model/harness/task_set_hash/grader/成本口径/采样/truncated）
├── tasks/
│   ├── <task_id>/result.json   # TaskResult（status/reason/fault_owner/partial/tokens/temperature/seed）
│   └── <task_id>/trace.json    # 逐步 trace（tool_call/tool_result/edit + timestamp）
├── summary.md          # 单轮任务汇总
└── （repeat>1 时）
benchmarks/runs/evaluation-report.md      # 聚合结果页（披露段齐全，见第 7 节）
benchmarks/reports/comparison.md / .html # 对照报告（per-task delta/差异 CI/win-rate）
```

- **run.json 元组**：`model{name,version,provider}`、`harness{adapter_version,prompt_version,max_turns,timeout_seconds,network}`、`task_set_hash`、`swebench 实例/包版本`、`成本口径{定价表版本,cache hit rate}`、采样（temperature/seed）、`started_at/ended_at`、计数（passed/warnings/unsupported/failed）、`truncated`。
- 定价表版本/日期见 `agent/cost_tracker.py::PRICING_TABLE_VERSION`。

## 7. 结果页披露段（渲染义务）

聚合结果页（`evaluation-report.md` / HTML）除 Pass@k/均值/CI/延迟/成本外，必须渲染以下披露段：

1. **报告元组**：model/harness/task_set_hash/grader/成本口径。
2. **SWE-bench 污染注记**：保留条件域（经审计的 138 个高失败率实例中 59.4% 有实质缺陷；OpenAI 2026-02 弃用 SWE-bench 评测；子集 KNOWN_BAD 过滤/版本钉住）。
3. **反作弊泄漏披露**：A 轨回归基线定位（来源/时间范围/training cutoff 未知），声明非公平评测。
4. **reason × fault_owner 交叉表**（失败归因闭环的渲染面）。
5. **$/resolved-task + cache hit rate + 定价表版本**。
6. **f2p/p2p 部分成功档**（严格 resolved 口径 = F2P+P2P 全通过；部分成功字段保留展示）。
7. **采样参数**（temperature/seed/model version）。
8. **小样本声明**（N=3–5 附声明；per-task CI 不加权，仅 layer/aggregate 层展示 CI 权重）。
9. **过程效率**（time-to-first-successful-edit / exploration fraction）。
10. **能力覆盖矩阵**（C1 manifest 套件级展示，独立 Requirement）。

## 8. 预检与环境

```bash
uv run asterwynd benchmark benchmarks/tasks --preflight
```

检查 Docker daemon 可用性 + 可用内存；退出码：

| 退出码 | 含义 |
|---|---|
| 0 | 可跑全量 |
| 1 | 可用内存 <8GiB，提示走 L1 本地轻量路径（不强制失败） |
| 2 | Docker daemon 不可用（有 docker 任务时需降级） |

## 9. 自洽性检查（self_check 五门禁）

数字要「逻辑自洽」，每次产数后运行 `uv run python scripts/self_check.py <run_dir>`，任一门禁不过则该轮数字**不得入面试材料**：

1. **同模型同 harness 复现**：报告元组存在且一致（同一配置跨轮 model/harness 元组一致）。
2. **seed 复现**：采样参数（temperature/seed/model_version）记录完整。
3. **失败归因闭环**：fault_owner 标注覆盖 + reason × fault_owner 交叉表存在（注：当前无校准证据 κ artifact，归因覆盖率口径见脚本实现；人审/强 judge 校准为后续项）。
4. **披露段齐全**：污染注记 + 严格 resolved + f2p/p2p 保留 + A 轨泄漏 + 小 N 声明。
5. **报告元组完整**：model/harness/task_set_hash/grader/成本口径字段齐全。

每门禁缺失时输出具体项并以非零退出码表达；`--skip <n>` 可跳过指定门禁（可重复）。

## 10. 复现步骤（照做）

```bash
# 0. 准备（一次性）
uv sync --extra dev

# 1. 环境 preflight
uv run asterwynd benchmark benchmarks/tasks --preflight   # 退出码 0/1/2

# 2. 本地场景任务（A 轨 + B 轨，面试核心主数字）
uv run asterwynd benchmark benchmarks/tasks \
  --repeat 5 --seeds 0 1 2 3 4 --temperature 0.2 \
  --budget-cap 50                    # 单轮建议上限；--budget-cap 0 或 --no-cap 取消

# 3. Verified 精选子集（L1 本地轻量 + L2 Docker 混合；fixture 见第 2 节前置）
uv run asterwynd benchmark benchmarks/tasks/verified-subset \
  --repeat 5 --seeds 0 1 2 3 4 --temperature 0.2 --budget-cap 50

# 4. 对照运行（同任务同 harness，仅换参照 agent）
uv run asterwynd benchmark benchmarks/tasks --agent claude \
  --repeat 5 --seeds 0 1 2 3 4 --budget-cap 50

# 5. 生成对照报告
uv run python benchmarks/compare.py benchmarks/runs/<runA-id> benchmarks/runs/<runB-id>

# 6. 自洽性检查
uv run python scripts/self_check.py benchmarks/runs/<run-id>

# 7. 汇总面试数字 + 披露段（evaluation-report.md / comparison.md 供引用）
```

## 11. 本期不跑 / 后续

- 完整 SWE-bench Verified 全量 500（资源升级后，预算按 $0.5–5/实例粗算 $250–2,500）。
- Terminal-Bench 2.x（内存 ≥8GiB + 拉镜像验证后，10–20 条试点）。
- τ³-bench（本期不纳入，G2 定）。
- 后续项：long-horizon 分层 → human audit（先于 agent-as-judge）→ agent-as-judge → flaky 校准 → 趋势/常态化 → 预算-成功曲线。
