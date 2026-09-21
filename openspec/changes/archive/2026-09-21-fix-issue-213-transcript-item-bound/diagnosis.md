# Diagnosis — fix-issue-213-transcript-item-bound

## Symptom

父 agent 调用 `InspectSubagentTranscript` 读取子 agent 的执行情况时，**单次工具调用可以把任意长度的
子 agent 输出灌进父 agent 的上下文**——而这个长度**不受父 agent 控制**（由子 agent 产生）。

issue #213 的实测口径：子 agent 输出 30,000 字纯文字 → 工具返回 **34,507 字符**。

同一份 `inspect_transcript` 结果，**HTTP 路由那条路是有界的**（截到 4000），模型面这条无界。

## Reproduction

**探针（`manager.inspect_transcript` 直接调用，不经工具层）**：

```python
session.messages = [Message(role="assistant", content="字" * 30000)]
payload = manager.inspect_transcript(subagent_id="x", scope="recent_messages", limit=5)
json.dumps(payload, ensure_ascii=False)
```

| 量 | 实测值 |
|---|---|
| 单条消息原文长度 | 30000 |
| 工具返回 JSON 长度 | **30190** |
| `content` 字段长度 | **30000**（与原文等长，无截断） |
| 是否有 `content_truncated` 标记 | **无** |

**`summary` scope 同样无界**（且它是工具的**默认** scope）：

| 量 | 实测值 |
|---|---|
| `summary` 长度 | 30000 |

**`GetSubagentRun`（出口 2）同样无界**：

```python
run = SubagentRunRecord(run_id="r1", task="t", status="completed", summary="字" * 30000)
run.to_result_dict()
```

| 量 | 实测值 |
|---|---|
| `summary` 长度 | **30000** ← 模型面看到的是这个 |
| `bounded_summary` 长度 | 2040 ← **已经算好了，但模型面没用** |
| JSON 总长 | 32363 |
| `result_ref` | **None** |
| `bounded_summary` 尾部 | `'\n…[truncated; full result in result_ref]'` ← 指向一个不存在的 ref |

## Evidence

**证据一：同一条 dict 里，一个字段截了、另一个没截。**

`agent/subagent/manager.py` 的消息投影（约 1088-1096）：

```python
{
    "role": msg.role,
    "content": extract_text(msg.content),      # ← 无截断
    "tool_call_id": msg.tool_call_id,
    **_project_tool_calls(msg),                # ← 这里按 TOOL_CALL_ARGUMENT_LIMIT 截断
}
```

`arguments` 与 `content` 同属「单条内容」，却享受两种待遇。同文件 `:62-63` 的注释把契约定死为
「『单条内容』在模型面与 HTTP 面是同一个概念，不该有两个数」——`content` 漏在同一句论证之外。

**证据二：`_project_tool_calls` 的 docstring 已声明「生产者无条件截断」，但只对 arguments 执行了。**

同文件 `:86-95` 明确写着截断**不能**下放给调用方，理由是调用方有两类（HTTP 路由自带预算、
模型面工具没有）。这段论证对 `arguments` 成立，对 `content` **同样成立**，只是当时没一起改。

**证据三：HTTP 面早已确立 bounded 口径，模型面没跟上。**

| 路径 | 条数上限 | 单条上限 |
|---|---|---|
| HTTP 路由（`web/session.py` 的 `_bounded_messages`） | 200 | `TRANSCRIPT_CONTENT_LIMIT = 4000` ✅ |
| 模型面工具（`InspectSubagentTranscript`） | 200 | **无** ❌ |

`web/session.py` 那条注释写着「截断必须在路由层做」——**这句话本身就是漏洞的自我承认**：
它假定所有消费者都会自己截，而模型面工具没有。

**证据四：`bounded_summary` 的截断标记是一句假话。**

`manager.py:52-59`：

```python
def _bounded_summary(text, max_tokens):
    ...
    return text[:budget_chars] + "\n…[truncated; full result in result_ref]"
```

但 `_write_result_artifacts` 在 `run.workflow_id` 为空时**早退**（`manager.py:1295-1297`），
`result_ref` 保持 `None`。实测确认：同一条 `to_result_dict()` 里 `bounded_summary` 说「全文在
result_ref」，而 `result_ref: None`——**全文根本没落盘**。

## Root Cause

**模型面出口直接暴露了本该 bounded 的字段。** 具体是三层叠加：

1. **生产者侧漏了一维**：`inspect_transcript` 对 `arguments` 截断、对 `content`/`summary` 不截断。
2. **出口侧没兜底**：`_format_run_envelope` 把 `to_result_dict()` 的**全文** `summary` 原样交给
   工具面（`bounded_summary` 就在同一个 dict 里，没人用）。
3. **契约只锁了数字、没锁行为**：既有一条断言锁死了
   `TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT`（「不该有两个数」），
   但只保证**数字相等**，没保证**行为相等**——`content` 在模型面根本没被截。

第 3 点是这次能长期潜伏的原因：测试给了「口径一致」的**假安心**。

## Recommended Direction

**A. `InspectSubagentTranscript` 两个 scope 都加单条内容上限**，与 HTTP 面同数（4000），
并回流布尔标志（`summary_truncated` / `content_truncated`）。`include_tool_results=True` 时
tool 角色消息的 content 由同一处覆盖——那是 30000 字最可能的真实来源。

**B. 模型面 run envelope 默认 bounded**：`_format_run_envelope` 默认返回 bounded summary
（复用**已有的** `bounded_summary`，不引入新常量），全文仍可通过 `summary_ref` / `result_ref`
按需读取。调度器的内部消费点显式要求全量——它拿 envelope 喂 `state.summary` 做下游聚合。

**C. `RunPattern` 的 worker summary 同口径 bounded。**

**D. 修 `_bounded_summary` 的假话**：截断标记只在**确有落盘 ref** 时提它。

**E. 常量治理**：`TOOL_CALL_ARGUMENT_LIMIT` 实际要约束三个字段，名字已误导 → 新增
`TRANSCRIPT_ITEM_LIMIT` 承载语义，旧名保留别名。

**F. HTTP 层截断标志取或**：生产者开始截 `content` 后，路由层若仍只比较本层长度，会在
「生产者截了、本层预算更宽」时报「没截断」= 谎报（与 #212 在 `arguments` 上修过的是同一 bug 的第二例）。

**为什么截断只能在出口、不能在记录层**：`run.summary` 是全文，经 `to_result_dict` →
`_format_run_envelope` → `scheduler` 的 `state.summary` → `_node_task_text` 传导到下游聚合。
在记录层截断会降低聚合质量，且两条既有测试（`test_result_representations.py`）直接钉死该不变量。

## Regression Tests

- `InspectSubagentTranscript` 的 `summary` scope：30000 字输入 → 有界且 `summary_truncated is True`
- `InspectSubagentTranscript` 的 `recent_messages` scope：30000 字的 assistant content **以及一条
  tool 消息** → 有界且 `content_truncated is True`
- `GetSubagentRun`：30000 字 → 返回的 `summary` 有界，且 `summary_ref` / `result_ref` 可取全文
- `RunPattern`：worker summary 有界
- HTTP 路由：`content_limit` 大于生产者上限时，`content_truncated` 仍为 `True`（取或）
- 假话：`result_ref is None` 时 `bounded_summary` **不含** result_ref 字样
- 常量：`TRANSCRIPT_ITEM_LIMIT` / `TOOL_CALL_ARGUMENT_LIMIT` / `TRANSCRIPT_CONTENT_LIMIT` 三处同值
- 变异：`_bounded_content` 改回 identity / 取或改成只看本层 / envelope 传回 full → 对应测试必须红

## 归档证据

- 实测脚本：`/tmp/probe213.py`（本文档 Reproduction 两节即其输出）
- 基线：`7c23059`（`master`），分支 `fix-issue-213-transcript-item-bound/2026-09-21`
