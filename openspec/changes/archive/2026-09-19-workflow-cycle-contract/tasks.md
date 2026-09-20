# Tasks: 循环图的契约对模型可见（workflow-cycle-contract）

> **开发前必做**：`batch-grill-me` 设计追问（独立零记忆 subagent，AGENTS.md #95 机械强制）。
> grill 产出后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复；答复记录进
> `reviews/grill-design.md` 的 `## User Confirmation`。收到答复前**不得写实现代码**。
>
> **grill 已推翻初版判据**（`reviews/grill-design.md`）：初版 D1「环内无产出节点」被实测证伪（漏报 +
> 论据不成立），初版 D2「route 有同环内 required 数据入边」会**拒绝官方 `peer-review`** 并误伤 23 条
> 既有测试。用户裁决：**D1 改为不动点判据（环内无可派发节点）、D2 并入 D1 并把诊断价值保留在报错文案**。

## 0. 立项（主 session 完成）

- [x] 0.1 业界调研（Airflow/Argo 声明期拒绝环、Temporal/LangGraph 靠示例传达循环契约）写进 `## Reference Implementation Research`
- [x] 0.2 判据的静态可判定性论证 + 无误报论证（写进 design D1）
- [x] 0.3 proposal / design / tasks / spec delta
- [x] 0.4 backlog 登记 + `workflow-events.jsonl` 结构化事件
- [x] 0.5 `openspec validate --strict` + artifact checker 通过
- [x] 0.6 **grill**（独立 subagent）→ 停轮收集用户答复（重点：D3 拒绝 vs 警告）→ 回填 `## User Confirmation`
- [x] 0.7 按 grill 结论重写 design/proposal/spec delta（判据重写 + 行号修正 + 变异计划更换）

## 1. 复现与回归测试（TDD：先写测试，确认红）

- [x] 1.1 **复现 #219 形态**（`cycle_gate` route + `body` collect 聚合 + 环内 `required` 数据边）→ 当前能声明成功、跑到环内节点全 `blocked` 而图报 `completed`；新校验后**声明期被拒**
- [x] 1.2 反向：**环内有 subagent 但互等**（grill Q1 场景：`b`/`c` 互相 required 等待）→ 拒绝（「有产出节点」判据会漏掉它）
- [x] 1.3 正向：环有能自启动的 entry（`producer → reviewer → gate → producer`）→ 通过
- [x] 1.4 正向：环内是 `aggregate(strategy="llm")` 且能启动 → 通过
- [x] 1.5 正向：环内是 `foreach` 且能启动 → 通过
- [x] 1.6 正向：回边从 route 出发（控制边）→ 通过
- [x] 1.7 正向：回边 `required: false` 且环能启动 → 通过
- [x] 1.8 反向：环外节点以 `required` 数据边喂进环、环内无 entry → 拒绝
- [x] 1.9 回归红线：官方 4 pattern 全部仍能声明通过（`peer-review` 是本项目唯一能工作的多轮审阅循环）
- [x] 1.10 改造 `tests/agent/subagent/test_terminal_honesty.py`：绕过声明期校验、直接构造 `WorkflowSpec`（grill Q5 裁决）

## 2. 实现：声明期「环必须能启动」校验（D1）

- [x] 2.1 在 `workflow.py` 的校验段新增 `_validate_cycle_can_start`（最小不动点：required 数据源可派发 + entry/无控制入边/可派发控制源 route）
- [x] 2.2 新增 `WorkflowCycleError(WorkflowValidationError)`，供 `_invalid_spec` 给指向性 hint
- [x] 2.3 复用既有 `_strongly_connected_components`（迭代 Tarjan），**不改它**
- [x] 2.4 只对**环分量**判定（大小 > 1 或自环）；非环节点不在本校验范围
- [x] 2.5 与既有 `_validate_cycles` / `_validate_foreach_source_cycles` 的**执行顺序**确认（置于 `_validate_cycles` 之后，避免对无 route 的环重复报错；置于既有校验之后以不改既有报错优先级）

## 3. 实现：报错可操作（D5，**本 change 关键路径**）

- [x] 3.1 错误信息含三要素：**环成员节点 id**（有界列出）、**缺什么**（逐条「谁在等谁」）、**怎么改**（可照做的动作）
- [x] 3.2 被拒环内若有同环 `required` 数据入边 → 点名这些边并给「`required: false` / 回边改从 route 出发」建议
- [x] 3.3 `_invalid_spec` 对本类错误给**指向性 hint**（说明返回体无 `workflow_id`、按 reason 的 how-to-fix 改 spec 后重声明）
- [x] 3.4 测试断言错误信息含这些要素（不只断言「抛了异常」），并用「模型视角」核对能否据此改对

## 4. 实现：提示面补循环契约（D4）

- [x] 4.1 `DeclareWorkflow` 描述补循环小节：核心规则「环里必须有个节点先跑起来，且它不能反过来等环里的节点」
- [x] 4.2 描述覆盖：回边从 route 出发是控制边 / 非 route 回边须 `required: false`；`max_routes` 默认 1、逐节点配、跨轮累加不重置
- [x] 4.3 描述里给**最小正确示例**与**最小反例**（反例即被拒形态）
- [x] 4.4 测试断言描述含关键契约词

## 5. 运行期诊断（初版可选 C）——**本 change 不做**

- [x] 5.1 判断：D1 已在声明期拦下全部可静态判定的停滞环，且 `workflow-terminal-honesty` 已让 `blocked` 节点如实报「入边互相等待」→ 本条价值不足以独立成项。**记录为观察项，不实现**

## 6. 验证与收尾

- [x] 6.1 **回归红线**：官方 4 pattern（orchestrator-worker / peer-review / hierarchical / bidding）**全部仍能声明通过**
- [x] 6.2 变异验证：每条新校验都能被「改坏实现」杀死。**用有区分度的变异**（初版规划的 `data_incoming` → `incoming` 经 grill 实测是**恒等变换**，已废弃）：
  - 删掉 `required` 判断（`required: false` 的边也当门控边）→ 应被 1.7 抓住
  - 删掉「是 entry」分支 → 应被 1.9（`peer-review`）抓住
  - 判据退化成「环内有无 subagent」→ 应被 1.2 抓住
  - 去掉 `waiting on` / how-to-fix 段落 → 应被 3.4 抓住
- [x] 6.3 `tests/agent/subagent/` + 全量 `uv run pytest -q`
- [x] 6.3b 跑通 benchmark smoke（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke ...`），确认声明期校验未破坏 benchmark 路径
- [x] 6.4 **同步 current spec**：把 delta 合入 `openspec/specs/multi-agent-collaboration/spec.md`（受保护路径，需 `workflow-events.jsonl` 事件）
- [x] 6.5 `/review-loop` 独立审阅闭环（AGENTS.md #90 机械强制）：R1 = CHANGES_REQUESTED（7 条）→ 修复 + 回归测试 → R2 = **PASS**（3 轮封顶内收敛）。权威报告 `reviews/building-review.md` 覆盖两轮，另存 `reviews/building-review-r2.md`
- [x] 6.6 归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-cycle-contract/` + backlog 移除
- [x] 6.7 `openspec validate --all --strict` + `check_openspec_artifacts.py` 通过
- [x] 6.8 建 PR（含归档收尾）；合入后 comment + close #219
- [x] 6.9 文档影响检查：扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及 workflow DSL / 循环的段落

## 7. 首轮审阅（building-review）修复

首轮独立审阅 verdict = CHANGES_REQUESTED（blocker 1 / major 2 / minor 2 / low 2），全部已处理：

- [x] 7.1 **Issue 1（blocker）**：不动点补 `deadline_fired` 短路——环内 `best_effort` 聚合不得误拒（实跑该图在基线能声明且真循环）
- [x] 7.2 **Issue 2（major）**：新增 `_route_activators`，把 `cases[].to`/`default` 目标计入激活来源（调度器按 target id 激活、不要求声明边）
- [x] 7.3 **Issue 3（major）**：报错「waiting on」段排除 route 出边（控制边不门控，照其修改无效——与 Q3「报错必须能引导改正」冲突）
- [x] 7.4 **Issue 4（minor）**：`_bounded` 统一截断报错列表并注明 `(+N more)`（此前 60 节点环可到 8k+ 字符）
- [x] 7.5 **Issue 5（minor）**：勾选已完成的任务复选框，让 review 门禁真正咬合
- [x] 7.6 **Issue 6（low）**：补 6 条用例（best_effort 环 / route 无声明边 / 自环 / 多环并存 / 报错有界 / 不苛责控制边）+ 加严 2 条弱断言（改断言具体节点串）
- [x] 7.7 **Issue 7（low）**：backlog 同步（随 6.6 移除整条条目）
- [x] 7.8 变异验证新增 4 条（revert `deadline_fired` / revert route activator / 恢复控制边苛责 / 去掉截断），全部被杀死
- [x] 7.9 随机图 fuzz 交叉验证：三个种子共 ~155 张被拒图逐个实跑，零误报
