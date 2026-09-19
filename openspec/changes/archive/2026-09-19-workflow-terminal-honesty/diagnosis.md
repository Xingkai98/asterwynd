# Diagnosis: workflow 终态与因由的三个缺陷

本文件记录 `workflow-terminal-honesty` 的 bugfix 侧证据。三条均为**确定性复现**（非竞态）。

## Symptom

用户在 session `0a94250da7bf` 用真 LLM 跑了几张 workflow 图，发现**图会骗人且指错排查方向**：

1. **图级 status 谎报**（#217）：一张**一个节点都没跑**的图在 UI 上显示「已完成」
2. **节点因由是假话**（#218）：节点写 `workflow ended before the node became ready`，真因是它自己撞了 `max_routes`；且该文案在**无任何闸门**的死锁场景下也照样出现
3. **回边重跑清空发起者**（#220）：`route` 明明选中了下游，快照里 `targets=[]`、选中的出边显示 `inactive`、节点报 `blocked`

## Reproduction

三个最小 spec 均可确定性复现（`_LLM` 恒返回固定文本，无随机性）：

**#217（死锁）** — `route` 回边 `required` 默认 true：

```python
{"nodes": [{"id":"cycle_gate","kind":"route",
            "cases":[{"when":"CONTINUE","to":"body"}], "default":"end"},
           {"id":"body","kind":"aggregate","strategy":"collect"},
           {"id":"end","kind":"aggregate","strategy":"collect"}],
 "edges": [{"from":"cycle_gate","to":"body"},{"from":"cycle_gate","to":"end"},
           {"from":"body","to":"cycle_gate"}],        # ← 无 required:false
 "entry": ["cycle_gate"], "terminal": ["end"]}
```

**#220（空转环）** — 在 #217 的 spec 上回边加 `"required": false`，`cycle_gate` 加 `"max_routes": 3`，**并把 `cycle_gate` 的 `default` 从 `end` 改成 `body`**：

```python
{"nodes": [{"id":"cycle_gate","kind":"route","max_routes":3,
            "cases":[{"when":"CONTINUE","to":"body"}], "default":"body"},   # ← default 必须是 body
           {"id":"body","kind":"aggregate","strategy":"collect"},
           {"id":"end","kind":"aggregate","strategy":"collect"}],
 "edges": [{"from":"cycle_gate","to":"body"},{"from":"cycle_gate","to":"end"},
           {"from":"body","to":"cycle_gate","required":false}],
 "entry": ["cycle_gate"], "terminal": ["end"]}
```

> **`default` 必须指向回边分支（`body`），否则环转不起来。** 本文件早先的 Reproduction 段写「同上但回边加 required:false」（即沿用 #217 的 `default: "end"`）是**错的**——实测那份 spec 下 route 只派发 **1 次**、`_reset_subtree` **一次都没被调用**、`cycle_gate` 报 `completed`/`targets=['end']`，#220 **完全复现不出**。下面是 Evidence 块记录的实测行为（`default -> ['body']`），与 `default: "body"` 这一份一致。本段已按 Evidence 更正（grill Q3 用户确认，2026-09-19）。

**#218 形态 B** — 即 #217 的死锁场景（无图级闸门），观察节点 `reason`。

## Evidence

### #217：零节点完成 → 图级 `completed`

```
[死锁场景] 图级: completed     _reset_subtree: (未调用)
  cycle_gate   blocked    runs=0
  body         blocked    runs=0
  end          blocked    runs=0
  completed=0  failed=0  total=3
```

用户实测的真实图 `wf_e458b9eb` 同样表现（`status: "completed"`，三节点全 `blocked`）。

### #218 形态 A：真因在 `diagnostics`，节点只显示兜底文案

```
节点: cycle_gate  blocked  reason='workflow ended before the node became ready'
图级 diagnostics: {"reason": "max_routes",
                   "message": "GraphRecursionError: route node 'cycle_gate' exceeded max_routes 2",
                   "steps": 3, "limit": 2, "current_nodes": ["cycle_gate"]}
```

### #218 形态 B：无闸门时兜底文案照样出现（证明问题不止于「没穿透」）

```
[死锁场景] 图级: completed     diagnostics: (无)     _reset_subtree: (未调用)
  cycle_gate   blocked    reason='workflow ended before the node became ready'
  body         blocked    reason='workflow ended before the node became ready'
  end          blocked    reason='workflow ended before the node became ready'
```

**没有任何图级闸门，节点因由仍然是同一句兜底文案** → 兜底文案不区分成因是系统性问题。

### #220：`_reset_subtree` 走回发起者

```
执行#1  完成后 targets=['body']  (summary 记的是 "default -> ['body']")
执行#2  完成后 targets=[]        (summary 记的是 '')          ← 被擦
执行#3  完成后 targets=['body']  (summary 记的是 "default -> ['body']")

_reset_subtree 被调用的节点: ['cycle_gate', 'body', 'cycle_gate', 'cycle_gate']
                                              ↑ 第 3 个是它走回发起者自己

最终: cycle_gate  status=blocked  targets=[]
      cycle_gate → body = inactive     ← 应为 passed
      cycle_gate → end  = inactive
```

### 独立性实测（三 bug 互不依赖）

| 场景 | `_reset_subtree` | 图级 status | completed |
|---|---|---|---|
| 回边 `required=true`（死锁） | **从未调用** | `completed`（#217） | 0 |
| 回边 `required=false`（空转环） | 调用 `cycle_gate`（#220） | `graph_recursion_exceeded` | 1 |

#217 在 `_reset_subtree` 从未被调用的场景下依然复现；#218 形态 B 同理（`diagnostics` 为空）。
**三者可各自独立修复，无先后依赖。**

## Root Cause

| # | 根因 | 位置（修复前） |
|---|---|---|
| **#217** | `_terminal_converged_status()` 只排除「有 `failed`」，**不排除「零 `completed`」** | `agent/subagent/scheduler.py:1234` |
| **#218** | `_resolve_pending_status()` 用**单一兜底文案**覆盖多种成因，且不读图级 `diagnostics` | `agent/subagent/scheduler.py:1295` 附近 |
| **#220** | `_reset_subtree()` 沿 `data_outgoing` 递归时**不排除发起者**；回边为数据边时会走回 `route` 自身，清空其刚写的结果 | `agent/subagent/scheduler.py:1511` + `_execute_route` 派发循环 `:1626` |

> 上表行号是**修复前**（立项时）的定位，供追溯用；修复后的落点见 `design.md` 的 Impact Analysis。

**#217 的引入点**：`enhance-workflow-graph-ux` 的 G26/D9（commit `6e00876`）。G26 的立项理由是「有节点 `failed` 的图不得报 `completed`」，但**同一理由对「零 `completed`」成立得更强**——G26 修的是「有失败却说成功」，本次是「无成功却说成功」。

## Recommended Direction

见 `design.md` 的 D1–D4：

- **#217** → D1/D2：`completed` 判据补「至少一个节点 `completed`」前置；零 `completed` 且零 `failed` 落**新档 `stalled`**
- **#218** → D3：因由按真实成因分三档（图级闸门穿透 / 入边互等 / 其它兜底）
- **#220** → D4：`_reset_subtree` 增加「发起者豁免」

**为何 `#217` 新增独立档而不是复用 `failed`**：本项目的 `failed` 已被「节点执行失败」占用（`completed_with_failures` 依赖它）；混用会让「有节点失败」与「图没跑起来」不可分辨，而这两者的行动指引完全不同。业界 Airflow/Prefect 把「无成功」并入 FAILED 是因为其 `failed` 语义本就宽（含 `upstream_failed`）——本项目不适用该前提。

## Regression Tests

| 测试 | 断言 |
|---|---|
| 死锁图不得报 `completed` | 回边 `required=true` → 图级 status ≠ `completed`（且为 `stalled`） |
| 零完成 + 有失败 → `failed` | 四档矩阵第 3 格 |
| `max_routes` 撞线 → 因由含闸门信息 | 节点 `reason` 含 `max_routes` 与上限值 |
| 无闸门死锁 → 因由说明「入边互等」 | 节点 `reason` **不含** `workflow ended before` |
| 数据边回边不清空发起者 | `cycle_gate.status == "completed"`、`targets` 非空、选中出边 `passed` |
| **被选中且跑过的节点不得报 skipped**（方案 D 组合回归） | 同一张图：被派发节点 `status != "skipped"`，`reason` 不含 `route did not select this branch` |
| 三副本集合相等 | `_SNAPSHOT_TERMINAL_STATUSES` / `workflow.js` 数组 / `workflow_graph.js` 的 `isGraphTerminal()` |
| 前端因由可见（Q4） | `max_routes` 图的用户可见文案含 `max_routes`；`stalled` 图含「入边互等」 |
| `stalled` 配色门槛（D6） | 到每个既有图级档的 RGB 欧氏距离 ≥ 100 |
| **G11 回归**（必须保持绿） | 陈旧因由 / 负耗时 |

每个新测试都须经**变异验证**（改坏实现 → 测试变红）。

**#220 的复现 spec 以本文件 Evidence 块为准**（`default: "body"`）。

## Mutation Verification（tasks 6.1，2026-09-19）

每个新测试都用「改坏实现 → 期望目标测试变红 → 还原 → 基线确认绿」验证是真保护。
脚本：`/tmp/mut/mutate.py`（16 个变异，覆盖四档判据 / 因由三档 / origin 豁免三处调用点 /
`_is_skipped` 条件 2 / 三副本同步 / 前端 `explainNode` 优先级 / D6 配色门槛）。

| # | 变异（改坏实现） | 目标测试 | 结果 |
|---|---|---|---|
| M1 | 去掉 `completed_with_failures` 分支 | 四档第 1 格 | 杀死 |
| M2 | 零完成也返回 `completed`（原 bug 复现） | #217 两条 | 杀死 |
| M3 | 去掉 `failed` 分支（零完成+有失败） | **四档第 3 格（首轮存活，补测后杀死）** | 杀死 |
| M4 | `_blocked_reason` 恒返回兜底句 | #218 形态 A/B | 杀死 |
| M5 | 去掉「入边互等」分支 | #218 形态 B | 杀死 |
| M6 | `_reset_subtree` 去掉 origin 豁免 return | #220 两条 | 杀死 |
| M7 | `_execute_route` 调用点不透传 origin（**关键那处**） | #220 | 杀死 |
| M8 | 递归处不透传 origin | #220 | 杀死 |
| M9 | `_is_skipped` 去掉条件 2 | 方案 D 组合回归 | 杀死 |
| M10 | scheduler 副本去掉 `stalled` | 三副本等价 | 杀死 |
| M11 | `workflow.js` 副本去掉 `stalled` | 三副本等价 | 杀死 |
| M12 | `isGraphTerminal` 去掉 `stalled` | 三副本等价 | 杀死 |
| M13 | `explainNode` 去掉具体因由提权 | Q4 两条 | 杀死 |
| M14 | 兜底句被误当具体因由（反向） | Q4 反向护栏 | 杀死 |
| M15 | `stalled` 配色复用 `budget_exceeded` 的橙 | D6 配色门槛 | 杀死 |
| M16 | 「入边互等」列全部入边（含 completed） | #218 形态 B | 杀死 |

**首轮 M3 存活**（四档矩阵第 3 格 `completed==0 & failed>0 → failed` 无测试覆盖，是假保护）——
补 `test_zero_completed_with_failures_is_failed` 后杀死。这正是 tasks 6.1 要求逐格覆盖的原因。

**M7 的意义**：它把「只改 `_on_node_finished` 那处、漏掉 `_execute_route` 那处」这一最易犯的
实现错误钉成了红线（该错误实测零效果，见 Q1 复核）。
