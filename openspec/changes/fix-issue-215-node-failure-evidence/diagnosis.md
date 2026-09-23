# Diagnosis — fix-issue-215-node-failure-evidence

## Symptom

一个 subagent run **完成**（`status == "completed"`）但**中途有过工具失败**时，用户在 workflow 节点详情里
**看不到任何失败信号**：节点状态是绿的、`reason` 是空的、「对话」tab 里只能看到 `🔧 Bash` 这一行工具调用、
看不到它的失败输出。

用户原话（归档 change `enhance-workflow-graph-ux` 的总目标）：「如果报错了，为什么报错」——这正是没被回答的
那一半。

归档 change 的 M3.6（G9 `trace_digest`）标了 `[x]`，但全仓零实现：`openspec/specs/` 无对应 requirement，
active 代码无任何失败证据投影。唯一命中 `trace_digest` 的位置在归档 change 自己的文档里。

## Reproduction

**探针**（`/tmp/probe_215.py`，直接调真实投影入口 `build_node_transcript_payload`，不经 Web 层）：

构造一个已完成的 run，其 `run.trace.steps` 里放**两个**失败步骤——形状与生产者逐字一致
（`agent/loop.py:895-935` 产出 `tool_result` 的 `status="error"` + `error_type`；
`agent/trace_recorder.py:226` 产出 `llm_error`）：

```python
run.trace = {"steps": [
    {"step": 1, "type": "tool_call", "data": {"tool_name": "Bash",
        "arguments": {"command": "uv run pytest -q"}}},
    {"step": 2, "type": "tool_result", "data": {"tool_name": "Bash", "status": "error",
        "error_type": "tool_error", "observation": "3 failed, 12 passed in 4.21s"}},
    {"step": 3, "type": "llm_error", "data": {"error_type": "network_timeout",
        "message": "upstream timed out after 30s"}},
]}
payload = build_node_transcript_payload(manager, scheduler, "a")
```

**实测输出**（当前 master `1a7df92`）：

```
run.status      = 'completed'
run.reason      = None
trace steps     = 3 | failing steps = 2
payload keys    = ['content_limit', 'included_tool_results', 'kind', 'limit', 'messages',
                   'node_id', 'node_kind', 'reason_full', 'reason_length', 'reason_truncated',
                   'run_id', 'scope', 'status', 'subagent_id', 'truncated']
included_tool_results = False
messages        = 3
payload bytes   = 567
mentions '3 failed'?        = False
mentions 'network_timeout'? = False
has failure_evidence key?   = False
```

| 量 | 实测值 |
|---|---|
| run 状态 | `completed` |
| run.reason | `None` |
| trace 里的失败步数 | **2** |
| 载荷里能读到失败证据吗 | **不能**（无 `failure_evidence` 键） |
| 载荷里出现失败文本吗 | **不出现**（`3 failed` / `network_timeout` 均无命中） |

**结论**：数据在 `run.trace.steps` 里齐备，**没有任何出口把它投影出来**——这正是 M3.6 承诺而没做的事。

## Evidence

### 1. 数据齐备（不需要新采集）

`agent/trace_recorder.py` 已产出全部所需 step：

| step 类型 | 行号 | 关键字段 |
|---|---|---|
| `tool_result` | `:129` | `tool_name` / `status` / `duration_ms` / `observation` / `error_type` |
| `llm_error` | `:226` | `error_type` / `message` |

失败判据由生产者在 `agent/loop.py:895-935` 算出（`status = "error" if ... else "ok"`）。

### 2. 全仓唯一读取 `run.trace` 的地方不投影失败

```
$ grep -rn "\.trace\b" --include="*.py" agent/ web/
agent/subagent/manager.py:1334:        run.trace = trace.to_dict()   # _complete_run
agent/subagent/manager.py:1410:        run.trace = trace.to_dict()   # _mark_failed
agent/subagent/manager.py:1425:        run.trace = trace.to_dict()   # _mark_cancelled
agent/subagent/manager.py:1444:        run.trace = trace.to_dict() if trace is not None else None
agent/subagent/snapshot.py:77:     trace = run.trace or {}           # 唯一读取点
```

四个写入点 + **一个**读取点，而那个读取点只数 `llm_iteration` 步数（`snapshot.py:76-79`，
`_iteration_from_run`）——**与失败无关**。

### 3. Web 出口拿不到工具结果

`web/server.py:195-202` 的路由签名**没有** `include_tool_results`：

```python
async def node_transcript(
    session_id: str, workflow_id: str, node_id: str,
    limit: int = 50, offset: int = 0,
    subagent_id: str | None = None, run_id: str | None = None,
):
```

`build_node_transcript_payload` 的默认 `include_tool_results=False`（`web/session.py:875`）一路传到
`inspect_transcript`，后者在 `manager.py:1140-1141` 把所有 `role == "tool"` 消息过滤掉。前端
（`web/static/workflow_transcript.js:55-70`）也未传该参数——**前端从无机会请求工具结果**。

### 4. `run.reason` 覆盖不到「中途失败」

`reason` 只在**整个 run 失败**时才有文本（`_mark_failed` 的 `reason` 参数 / `_mark_budget_exceeded`
的 `f"budget exceeded ({dimension})"`）。而工具失败**不会**让 run 失败——`loop.py` 把工具错误包成 tool
消息继续跑（`:895-935` 只算 `status` 字段，不抛）。

### 5. 附带发现：`failed` 分支是死代码

`manager.py:1324`：

```python
run.status = "completed" if result.stop_reason is not StopReason.ERROR else "failed"
```

`StopReason.ERROR` 全仓**零赋值点**——只有 `agent/result.py:14` 的定义与 `tests/agent/test_result.py:18`
的值断言，`loop.py` 只产出 `END_TURN`（`:723`/`:740`）与 `MAX_ITERATIONS`（`:1011`）。所以 run 只能经
异常路径 `_mark_failed` 变 `failed`，**`completed` 覆盖了「跑完了且中途有工具失败」的全部情况**。

> 本发现记录在案，**不在本 change 范围**（修它属于 run 状态机语义，会改变 `completed`/`failed` 判据）。

## Root Cause

**投影层缺失，不是数据层缺失。** 归档 change 的 design.md:410 已经写明了做法（`trace_digest`），但实现阶段
没有落地，且审阅 R1 诚实标注「未逐行核实」后没有被强制回填——机制缺口，见 issue #215 的「为什么漏过」。

具体到代码：`run.trace.steps` → 用户面出口这条链路**没有任何一段存在**。

## Recommended Direction

在**节点 transcript 载荷**里加一条 bounded 的失败证据投影（`failure_evidence`），只做归档 design.md:410
坑 (b) 点名的那件事：**用显式状态枚举区分「没有 trace」与「trace 里没有失败」**。

- 数据源：该 run 的 `run.trace.steps` 中 `status != "ok"` 的 `tool_result` + 全部 `llm_error`。
- bounded：最近 N 条 + 单条 `observation` 截断（复用 `TRANSCRIPT_CONTENT_LIMIT` 口径）+ 总数 + 截断标志。
- 状态枚举（**三种 `trace is None` / 空 trace 成因各有取值**，实测确认）：
  - `present` — trace 有失败步骤
  - `clean` — trace 有步骤、无失败（**已检查，干净**）
  - `running` — run 未到终态，trace 按设计尚未写入
  - `empty_trace` — trace 存在但 `steps == []`（**排队取消**：`manager.py:1085` 新建空 `TraceRecorder`）
  - `no_trace` — 终态且 trace 为 `None`（**排队中撞时间预算**：`manager.py:1524` 传 `trace=None`）
  - `unavailable` — run 记录根本不存在（**queue_full** 把 run 弹出 `session.runs`，`manager.py:1033-1034`）
- 不做通用 `trace_digest`（含正常步骤），不做运行中实时可见性——归 #202。

## Regression Tests

（待 tasks.md 细化，方向如下）

1. `completed` + trace 含失败步骤 → `failure_evidence.state == "present"`，条目含工具名/步序/`status`/`error_type`。
2. trace 有步骤但无失败 → `state == "clean"`（**不是** `no_trace`）。
3. run 未终态 → `state == "running"`。
4. 终态 + `trace is None` → `state == "no_trace"`（**不是** `clean`）。
5. 终态 + `steps == []` → `state == "empty_trace"`（**不是** `no_trace`、**不是** `clean`）。
6. 失败条目多于 N → 只回最近 N 条 + 总数 + `truncated is True`。
7. 超长 `observation` → 不超过单条上限且 `observation_truncated is True`。
8. 大 trace 响应体积有界（投影只遍历不复制）。
9. 变异验证：把 `no_trace` 与 `empty_trace` 折叠、把 `clean` 当 `no_trace`、去掉截断 → 对应测试必须变红。
