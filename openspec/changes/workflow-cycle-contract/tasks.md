# Tasks: 循环图的契约对模型可见（workflow-cycle-contract）

> **开发前必做**：`batch-grill-me` 设计追问（独立零记忆 subagent，AGENTS.md #95 机械强制）。
> grill 产出后**停轮**把 `## Open Questions` 逐项抛给用户并等待明确答复；答复记录进
> `reviews/grill-design.md` 的 `## User Confirmation`。收到答复前**不得写实现代码**。

## 0. 立项（主 session 完成）

- [x] 0.1 业界调研（Airflow/Argo 声明期拒绝环、Temporal/LangGraph 靠示例传达循环契约）写进 `## Reference Implementation Research`
- [x] 0.2 两个判据的静态可判定性论证 + 无误报论证（写进 design D1/D2）
- [x] 0.3 proposal / design / tasks / spec delta
- [x] 0.4 backlog 登记 + `workflow-events.jsonl` 结构化事件
- [x] 0.5 `openspec validate --strict` + artifact checker 通过
- [ ] 0.6 **grill**（独立 subagent）→ 停轮收集用户答复（**重点：D3 拒绝 vs 警告**）→ 回填 `## User Confirmation`

## 1. 复现与回归测试（TDD：先写测试，确认红）

- [ ] 1.1 **复现 #219 的原始图**（`cycle_gate` route + `body` collect 聚合 + `required:false` 数据回边）→ 当前能声明成功、跑到撞 `max_routes`；新校验后**声明期被拒**
- [ ] 1.2 正向：环内有 `subagent` → 通过
- [ ] 1.3 正向：环内有 `aggregate(strategy="llm")` → 通过
- [ ] 1.4 正向：环内有 `foreach`（展开项为 subagent）→ 通过
- [ ] 1.5 反向：回边为 `required` 数据边（D2 死锁）→ 拒绝
- [ ] 1.6 正向：回边从 route 出发（控制边）→ 通过
- [ ] 1.7 正向：回边 `required: false` → 通过

## 2. 实现：两条声明期校验（D1/D2）

- [ ] 2.1 在 `workflow.py` 的校验段新增 `_validate_cycle_has_producing_node`（D1：SCC 内无产出节点 → 拒绝）
- [ ] 2.2 新增 `_validate_route_backedge_not_required`（D2：route 有同环内 `required` 数据入边 → 拒绝）
- [ ] 2.3 复用既有 `_strongly_connected_components`（迭代 Tarjan），**不改它**
- [ ] 2.4 产出节点定义：`subagent` 或 `aggregate(strategy="llm")`（**不含** `collect` / `route`；`foreach` 计入）
- [ ] 2.5 与既有 `_validate_cycles` / `_validate_foreach_source_cycles` 的**执行顺序**确认（先有 route 才谈产出，避免对无 route 的环重复报错）

## 3. 实现：报错文案可操作（D5）

- [ ] 3.1 两条校验的错误信息含：环成员节点 id、缺什么、**怎么改**（如「把回边改为 `required: false` 或从 route 出发」）
- [ ] 3.2 测试断言错误信息含这些要素（不只断言「抛了异常」）

## 4. 实现：提示面补循环契约（D4）

- [ ] 4.1 `DeclareWorkflow` 描述补循环小节（核心规则 + `max_routes` 默认值/位置/累加语义）
- [ ] 4.2 描述里给**最小正确示例**（subagent 在环内）与**最小反例**（全是 collect 聚合）
- [ ] 4.3 测试断言描述含关键契约词

## 5. 实现（可选 C）：运行期诊断补因果

- [ ] 5.1 `graph_recursion_exceeded` + `reason == "max_routes"` 时，`diagnostics` 补「为什么转不出去」
- [ ] 5.2 判断是否做：若 D1/D2 已在声明期拦住全部必然失败的环，本条价值降低 → **由 grill 决定**

## 6. 验证与收尾

- [ ] 6.1 **回归红线**：官方 4 pattern（orchestrator-worker / peer-review / hierarchical / bidding）**全部仍能声明通过**
- [ ] 6.2 变异验证：每条新校验都能被「改坏实现」杀死（含「把 `data_incoming` 换成 `incoming`」应当让 peer-review 误伤从而被抓住）
- [ ] 6.3 `tests/agent/subagent/` + 全量 `uv run pytest -q`
- [ ] 6.3b 跑通 benchmark smoke（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke ...`），确认声明期校验未破坏 benchmark 路径
- [ ] 6.4 **同步 current spec**：把 delta 合入 `openspec/specs/multi-agent-collaboration/spec.md`（受保护路径，需 `workflow-events.jsonl` 事件）
- [ ] 6.5 `/review-loop` 独立审阅闭环（AGENTS.md #90 机械强制，PASS 或 3 轮封顶）
- [ ] 6.6 归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-cycle-contract/` + backlog 移除
- [ ] 6.7 `openspec validate --all --strict` + `check_openspec_artifacts.py` 通过
- [ ] 6.8 建 PR（含归档收尾）；合入后 comment + close #219
- [ ] 6.9 文档影响检查：扫描 `docs/`、`AGENTS.md`、`CONTEXT.md` 中涉及 workflow DSL / 循环的段落
