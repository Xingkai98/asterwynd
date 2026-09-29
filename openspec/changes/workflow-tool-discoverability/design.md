# Design: Workflow 工具面可发现性

## Context

`DeclareWorkflow` 是模型进入 workflow DSL 的唯一入口。它的工具描述是**一份手写散文**（2504 字符，`agent/tools/builtin/subagents.py:504-541`），它的 `spec` 参数是**裸的 `{"type": "object"}`**（`:544-552`）。DSL 的完整结构（哪些字段、每个字段的合法值、字段与节点种类的关系）**只存在于 Python 源码**：

```
agent/subagent/workflow.py:30  NODE_KINDS = ("subagent", "aggregate", "route", "foreach")
agent/subagent/workflow.py:31  JOIN_SEMANTICS = ("all_required", "best_effort")
agent/subagent/workflow.py:32  AGGREGATE_STRATEGIES = ("llm", "collect")
agent/subagent/workflow.py:34  REDUCERS = ("concat", "merge_dict", "first_non_empty", "last")
agent/subagent/workflow.py:35  CHANNELS = ("result_ref", "summary", "artifact", "bus")
agent/subagent/workflow.py:56  _NODE_FIELDS = {...20 个字段的并集...}
agent/subagent/workflow.py:80  _EDGE_FIELDS = {"from","to","channel","required","reducer"}
```

模型看不到这些，只能猜。实测（issue #248 原始提示词，`deepseek-v4-flash`，`--mode bypass`，最新 master）的代价是 **19 次声明 / 20 个探针 workflow / 4 次 `invalid_spec` / 15 次 `graph_recursion_exceeded` / 54 迭代 / 398,590 token（498% 预算）**。模型自述：*"let me run a cheap probe to validate loop-dispatch semantics before committing to the full topology"*。

**关键事实：模型最终完成了任务**（资产 `fanout-review-loop.json`，10 节点，`entry: ["w1","w2","w3","w4","rework"]`）。命题不是「做不到」，而是「必须先当黑箱逆向 20 次」。

### 已复核的机制事实（本 design 的地基，不再重复验证）

1. **`description` 与 `parameters` 每轮 API 调用都原样发给模型。** `Tool.get_schema()`（`agent/tools/base.py:53-61`）把 `parameters` 放进 `function.parameters`；`AnthropicLLM._convert_tool`（`agent/anthropic_llm.py:746-753`）把它**逐字**映射为 `input_schema`（只改名，不校验、不裁剪）。嵌套的 `properties`/`items`/`enum` 因此**完全支持**。→ 加 schema 是纯增量。
2. **失败是「域不可见」，不是「形不可见」。** 模型**从未**写错顶层结构（`goal`/`nodes`/`edges`/`entry`/`terminal`）；栽的是 `strategy`/`channel`——这两个字段的合法值描述里根本没有。
3. **`max_routes` 与 `recursion_limit` 是两条独立代码路径**（`scheduler.py:1672` vs `:995`）。15 次超限的 `reason` 是 `max_routes`。→ #262 调大 `recursion_limit` 救不了本 issue。
4. **四个内置模板无一覆盖「fan-out + 回边」**：`peer-review` 有 route + 回边但零 `foreach`（`patterns.py:195-230`），其余三个有 `foreach` 但零回边。→ 模板层吃不掉本 issue 的摩擦。
5. **`cases` 匹配是行首匹配 + first-match-wins**（`scheduler.py:323-338`）：`for line in verdict.upper().splitlines(): if line.lstrip().startswith(expected): return True`。模型写 `[{"when":"GAPS","to":"intake"},{"when":"GAPS: none","to":"report"}]`，以为是最长匹配；实际 `"GAPS: none"` 以 `"GAPS"` 开头 → 第一条永久命中 → 每轮回边 → `max_routes` 跨轮累计超限。
6. **route 的 `task` 被静默忽略**：`_execute_route`（`scheduler.py:1866-1909`）完全不读 `node.task`；`_NODE_FIELDS`（`workflow.py:56-78`）对**所有 kind 共用一套并集**，声明期接受、运行期丢弃、**无 warning**。
7. **字段用在不适用的 kind 上时，行为分两类**（本次实测，`parse_workflow_spec` 直接调用）：

   | 类 | 输入 | 结果 |
   |---|---|---|
   | **A 静默丢弃** | `{"id":"s","kind":"subagent","task":"t","join":"best_effort","deadline_s":5,"cases":[...],"max_routes":7,"items":[1,2],"max_items":3,"strategy":"collect"}` | **`declared` 成功**；`to_dict()` 只回 `{"id","kind","task","outputs"}` —— 6 个字段**全部消失**，零提示 |
   | **B 误导性拒绝** | `{"id":"g","kind":"route","strategy":"concat"}` | `WorkflowValidationError: aggregate node 'g' strategy must be one of ['llm','collect']` —— 节点是 **`route`**，错误信息却说是 **`aggregate`** |

   两类叠加的后果：模型要么**不知道自己写错了**（A），要么**被告知错的是另一个 kind**（B）——而 `strategy` 在 route 上到底算不算错，模型无从得知（真相是：算错，但不生效）。
8. **描述的关键字命中数**（本次实测统计）：`channel` 1 次（**且是错的用法**）、`result_ref`/`summary`/`artifact`/`bus` **各 0 次**、`case`/`cases` **各 0 次**、`join`（作字段名）**0 次**、`items`/`source` **各 0 次**、`control` **4 次**（`:518` 是术语，`:530,531,536` 是非法示例——见 D3）。

## Goals / Non-Goals

**Goals**

1. 让 DSL 的**域**（每个封闭字段的合法值集合）在**动笔前**对模型可见——进 schema 的 `enum`，**从源码常量派生**。
2. 让 DSL 的**形**（字段怎么组合成合法图：回边挂 route、环要能自启动、`cases` 的排序、per-kind 字段归属）在描述里**说得准、说得全**。
3. 消除描述里的**非法示例**（`control`）——这是「照抄了错的示例」这一类错误的**唯一正确修法**（删，不是加）。
4. 消除 route `task` 与 per-kind 字段错配的**静默性**（静默丢弃 + 误导性报错）。
5. 让「schema ≡ 源码常量」成为**机械可验**的性质（parity 测试），而非靠人记得同步。

**Non-Goals**

- **不改任何调度语义**：门控、reducer 合并、`max_routes`/`recursion_limit`/`max_nodes`/`max_runs` 计数、环可启动性校验、`_reset_subtree`、`parent_envelope` 投影——逐字不动。
- **不新增工具**（含 issue 方向 5 的 `ValidateWorkflow`）。理由见 D10 + RIR RQ5。
- **不重做 `cases` 为表达式求值**。`matches_route` 的「结构化标签匹配、不做表达式求值」是明确的安全姿态（`scheduler.py:325-337` docstring）；本 change 只**暴露它的语义**，不改它。
- **不用 `oneOf`/`anyOf`/`if-then` 表达 per-kind 域**。Anthropic API 拒绝顶层 `oneOf`/`anyOf`（#246 RIR 实测），且本仓 `parameters` 是逐字透传（事实 1）——判别子形态在这里是高风险低收益。per-kind 归属**退回描述**（D5）。
- **不改四个内置模板的编译产出**（唯一的例外：若 D6 选 (a)，peer-review 的 route 节点去掉 `task`）。
- **不改资产 schema**、不改 `RunWorkflow` 的入口形状（`spec`/`template` 二选一是 #246 定的，逐字保留）。
- **不承诺 token 下降**。收益形态是「消除一整类无效动作」，不是线性省 token（见 proposal 验收节）。

## Decisions

### D1 — 分工原则：**schema 管域，描述管形**

| | 内容 | 载体 | 判据 |
|---|---|---|---|
| **域** | 单个字段的**封闭合法值集合** | schema `enum` | 封闭、可枚举、与源码常量一一对应 |
| **形** | 字段**之间**怎么组合成合法图 | 描述散文 | 跨字段约束、有条件的、需要解释「为什么」 |

**为什么这条线画在这里**（不是「能进 schema 的都进」）：

- 域进 schema 是**零风险纯增量**：`"type":"string","enum":[...]` 不触发任何 provider 限制（RIR RQ3）；且模型**看得见就不用猜**（事实 2 证明这正是失败点）。
- 形进 schema 是**高风险**：它往往需要 `oneOf`（`join` 只属 aggregate、`cases` 只属 route），而 Anthropic 拒顶层 `oneOf`/`anyOf`（#246 RIR），本仓也无法在 `parameters` 里做后处理（事实 1：逐字透传）。**`pi` 的 subagent 工具是现成先例**——三模式参数在 schema 里全部可选并列，判别放运行期（`examples/extensions/subagent/index.ts:459-472,496-513`）。本 change 对「形」用同一策略：**描述说清 + 运行期校验**，不动 schema 结构。
- 更根本的理由：**形是模型的强项**。事实 2 显示模型一次就写对了顶层结构——因为那是形。它栽的全是域。把精力投在域上，是投在**实际失败点**上。

**替代方案与否决理由**：
- **全都塞进 schema（含 `oneOf` 判别子）** —— 否决。Anthropic 顶层 `oneOf`/`anyOf` 被拒是硬约束（#246 RIR 实测），而 per-kind 判别只能靠 `oneOf` 或等价形态；在 `parameters` 逐字透传的管线里没有折中空间。
- **全都留在描述（不加 schema）** —— 否决。这是**现状**。事实 8 显示描述已经写了 2504 字符却仍然 0 次提到 `CHANNELS` 的任何成员——散文不可枚举、不可机械校验、必然漂移。issue #248 的方向 3 与本 change 的核心判断一致。

### D2 — 枚举**从源码常量派生**，不手写

`DeclareWorkflow.spec.parameters.properties.<field>.enum` SHALL 由 `agent/subagent/workflow.py` 的常量**程序化展开**，而非在 `subagents.py` 里再写一份字面量。

```
NODE_KINDS            → kind
CHANNELS              → edges[].channel
REDUCERS              → edges[].reducer
AGGREGATE_STRATEGIES  → nodes[].strategy
JOIN_SEMANTICS        → nodes[].join
（新常量）NODE_MODES   → nodes[].mode        ← 当前内联在 _parse_node:503-506，须提为常量
```

**为什么必须派生**：#246 抓到过一处实证漂移——`patterns.py:238` 的注释把 superstep 换算比量纲写错（`≈3` 与 `≈1.9` 混用），**没人发现**，直到 RIR 复核。手写的第二份枚举会走同一条路：源码加一个 kind，schema 里漏一个，模型于是看见一个**不完整却看起来权威**的域——**这比不写更糟**。

**机械保障**：parity 测试（见 Testing Strategy T1）断言 schema 里每个 enum 与对应源码常量**逐字相等**。没有这条测试，「派生」就退化成「又一份手写」。这是本 change 最重要的单条测试。

**`mode` 的处理**：`mode` 的合法值当前是 `_parse_node` 里的内联元组（`workflow.py:503-506`：`("build","read_only","plan")`）。本 change SHALL 把它提为模块常量 `NODE_MODES`，供校验与 schema 共用——这是**唯一一处在源码侧新增常量**的改动，且不改变校验行为。

**替代方案与否决理由**：
- **手写枚举字面量 + parity 测试锁定** —— 部分可行但劣。它同样能防漂移（测试会红），但引入了一次无谓的重复：schema 的定义点与语义的定义点分离，读代码的人要先跳一层才知道「这个 enum 从哪来」。RIR RQ2 显示**没有任何参考实现手写字面量**（zod/typebox 一律从单一声明生成）。
- **把 schema 生成放进 `workflow.py`（校验模块产 schema）** —— 否决。`workflow.py` 的模块 docstring 明写它「只做结构与语义校验，不 import 运行时」（`:15-16`）；反过来让它承担工具面表述会把两种关注点耦合。正确方向是**工具层反向读取校验层的常量**（单向依赖：`subagents.py` → `workflow.py`，与现状一致）。

### D3 — 删掉描述里的 `control`，并把「门控」与「传输渠道」**正交**讲清

**实测的准确计数**（本次 grep `agent/tools/builtin/subagents.py`，字符串 `control` 共 4 处）：

| 行 | 原文片段 | 性质 |
|---|---|---|
| `:518` | `"- A route's OUTGOING edges are control edges: they never gate."` | **正确的术语用法**（描述概念本身） |
| `:530` | `"  edges: ... gate->join (control), ..."` | **非法示例**——`control` 出现在「channel 该在的位置」 |
| `:531` | `"gate->producer (control back-edge)"` | **非法示例**（同上） |
| `:536` | `"  edges: gate->body (control), ..."` | **非法示例**（同上） |

**改动**：把 **3 处非法示例**（`:530,531,536`）的 `control` 换成合法的 `summary`；**并把 `:518` 的「control edges」措辞也一并改写**（改为「route 的出边直接激活下游、不参与门控」一类不出现 `control` 字样的表述）——理由见下。

**为什么这是纠错而不是改进**：`control` **从来不是** `CHANNELS` 的成员（事实 8 + `workflow.py:35`）。模型第 2 次尝试**照抄了我们的示例**，被我们自己的校验拒绝。这是**我们写错、模型背锅**。

**这个错误从哪来的（本次新发现，值得记一笔）**：`control` **确实是系统里的一个真实取值**——但它是**另一层、另一个字段**的值：

```python
# agent/subagent/scheduler.py:2855  —— workflow 快照的「边种类」
"kind": "control" if plan is not None and plan.is_control_edge(edge) else "data",
```

即：**可观测层**用 `edge.kind ∈ {control, data}` 描述一条边是不是控制边（Web 流程图据此单列 route 控制边，见 backlog 第十三批条目）；而 **DSL 层**的 `edge.channel ∈ {result_ref, summary, artifact, bus}` 描述的是数据传输形式。**两个正交概念、两层词汇，被写进了同一个位置**。这解释了错误的来源，也说明 D3 的修法不只是「改个词」——**必须把这两层词汇的边界讲清**，否则下一个人还会再抄一次。

**为什么把 `:518` 也一起改**：`control` 这个词既然已经在描述里与「边」强绑定出现，就仍是一个**诱导源**（模型看到「edge」附近有 `control`，就可能把它填进 channel）。改法是描述概念时**不用这个 token**，让 T2 的「零命中」断言成为一条**真正可执行**的约束。代价是损失一点术语精确性——**有意接受**。

> **注**：可观测层的 `kind: "control"` **不需要改**（它是快照契约的一部分，Web 前端依赖它，且它不在模型可见的工具面里）。本 change 只保证**模型可见面**不再出现诱导性 token。

**并要讲清的正交关系**（描述新增一段）：一条边「是否门控下游」由**发起节点的 kind** 决定（route 出边 = 控制边，不 gate；其他节点出边 = 数据边，默认 gate），`WorkflowSpec.is_control_edge`（`workflow.py:243-245`）是唯一判据。`channel` 是**另一件正交的事**：它描述数据以什么**形式**传给下游（`result_ref`/`summary`/`artifact`/`bus`）。**改 `channel` 的取值不会改变门控行为**——描述里的 `control` 一词把这两件事混为一谈，正是模型反复试探的根源。

**替代方案**：保留 `control` 但解释「它只是代号，请写 summary」——否决。**示例里的非法值会继续被抄**（这一轮已有实证）；而且「写一个非法值但意思是合法值」在语义上是反模式。

### D4 — `cases` 语义进描述：**行首匹配 + first-match-wins + 具体在前**

**改动**：描述新增 `cases` 一节，覆盖三点，并附**具体在前的正例**：

1. **匹配是行首前缀匹配**（`startswith`），**不是子串包含**。依据 `scheduler.py:330`：`if stripped.startswith(expected)`。
2. **按声明顺序 first-match-wins**（`scheduler.py:1866-1877` 的 `for case in node.cases: ... break`）。
3. **因此：具体/更长的模式必须排在宽泛模式之前。**
4. 配正例：`[{"when":"GAPS: none","to":"report"}, {"when":"GAPS","to":"intake"}]`（**具体在前**），并配反例：`[{"when":"GAPS","to":"intake"}, {"when":"GAPS: none","to":"report"}]`（宽泛在前 → `"GAPS: none"` 这行以 `"GAPS"` 开头 → 第一条永久命中 → 死循环回边 → `max_routes` 超限）。

**为什么用正例+反例而不是只讲规则**：spec 既有 Requirement「DeclareWorkflow 描述暴露循环契约」已经钉了「描述 SHALL 附最小正确示例与反例，SHALL NOT 仅罗列规则」（`openspec/specs/multi-agent-collaboration/spec.md:415-420`）。本 change 沿用同一范式。

**并补 `when` 的两种形态**（当前描述 0 次提及）：字面标签（大小写无关）与 `$ref:<node_id>:<slot>`（`workflow.py:88-107`，取槽值首个非空行作期望标签，槽缺失静默走 default）。

### D5 — per-kind 字段适用性**进描述**（一个表），不进 schema

**改动**：描述新增一个紧凑的**字段 × kind 适用表**（本 design 附录 A 是权威源，描述是它的投影）。

**为什么这是必要的**：字段名在描述里命中 0 的有 `join`/`items`/`source`（事实 8）。模型不知道 `join` 存在，就必然从邻近的 `strategy`/`reducer` 借值（事实 2 的 `strategy: "concat"` 就是「从邻居借」——`concat` 是 `REDUCERS` 的值，描述刚枚举过）。

**为什么不做成 schema 判别子**：见 D1 的否决理由（`oneOf` 限制 + 逐字透传）。**描述表 + 运行期校验**是唯一可行形态，且与 `pi` 的运行期 `modeCount` 判别同构。

**同时修错误信息**（D7）。

### D6 — route 节点的 `task`：三方案待 grill，本 design **不预设结论**

**事实**：`_execute_route`（`scheduler.py:1866-1909`）不读 `node.task`；`_NODE_FIELDS` 对所有 kind 共用并集（`workflow.py:56-78`），所以声明期**接受** route 带 `task`，运行期**静默丢弃**。issue #248 有实证：模型给 `gate` 写了判定 prompt，得到 `runs: 0`，整个 `wf_f970f143` 白跑。

**三方案与取舍**：

| 方案 | 做法 | 收益 | 代价 | 需要改的测试 |
|---|---|---|---|---|
| **(a) 声明期拒绝** | route 节点带 `task` → `WorkflowValidationError` | 语义最干净：**不可能**再静默 | 破坏既有写法；且「字段无害、只是不生效」被当错误是否过严，有争议 | **15 处 / 5 文件**（AST 实测，见 T3）——含**生产代码** `patterns.py:205`（peer-review 模板的 route 也带 `task`） |
| **(b) 声明期返回 `warnings`** | 接受，但在 `declared` 返回体里加 `warnings: ["node 'gate' (route) declares task which has no effect"]` | 不改任何既有测试；消除了静默；模型得到可行动反馈 | 需要设计一个**新的返回字段通道**（目前 `declared` 返回体没有 warnings 概念，`subagents.py:565-580`）；模型是否**读** warnings 不可保证 | **零** |
| **(c) 仅描述说明** | 描述里写「route 是纯控制节点，忽略 `task`」 | 改动最小 | **仍留静默陷阱**——模型不读描述就还是会踩（而本轮实测恰恰是「描述里有 0 次提到」的问题） | 零 |

**本 design 的观察（供 grill，不是结论）**：

- (a) 的「代价」比 issue #248 正文写的更重——不只是测试，**生产模板 `patterns.py:205` 自己也这么写**，说明这是团队的既有直觉，不是模型的错。
- (b) 的「设计 warning 通道」比听起来轻：`_invalid_spec`/`_invalid_input` 已经是结构化返回的先例（`subagents.py:437-470`），加一个 `warnings` 数组不违背现有形态；且 **RIR RQ4 显示「接受但显式告知」正是业界主流**（`opencode`/`pi` 都把边界写在模型看得到的地方，无一静默）。
- (c) 与 RIR RQ4 的结论**冲突**：没有任何参考实现把「字段被接受但完全无效」当作可接受状态。

**本 change 不替用户拍板。** 见 Open Question **Q1**。

### D7 — 修 per-kind 字段错配的**误导性错误信息**

**事实（本次实测，事实 7 类 B）**：`{"kind":"route","strategy":"concat"}` → 报错 `aggregate node 'g' strategy must be one of ['llm','collect']`。节点是 `route`，报错却说是 `aggregate`。

**根因**：`_parse_node`（`workflow.py:546-570`）无条件调用 `_parse_strategy`/`_parse_join`/`_parse_max_routes`/`_parse_cases`/`_parse_items` 等，**不看 `node.kind`**；这些解析器的错误文案硬编码了它「认为」的 kind（`_parse_strategy`，`:571-577` 写 `aggregate node`；`_parse_join`，`:566-570` 写 `aggregate node`；`_parse_max_routes`，`:598-599` 写 `route node`）。

**改动**：这些解析器的错误文案改为按节点**实际** kind 命名，并明确指出该字段适用于哪个 kind。**不改任何校验的接受/拒绝行为**——只改文案。

**为什么这属于本 change**：它与 D5 是同一个问题的两面——D5 让模型**事前**知道字段归属，D7 让模型**事后**拿到不误导的反馈。二者缺一，都会把模型推回试探。

**替代方案**：把这些解析器改成只在 `node.kind` 匹配时才调用（即不做校验）——**否决**。那会让「字段错配且值非法」从「拒绝」变成「静默丢弃」，**加重**事实 7 类 A 的问题。

### D8 — 描述的**结构**：从「一段散文 + 两个示例」改成「分节」**

当前描述是一段 2504 字符的连续散文（顶层结构 → 循环契约 → 正例 → 反例 → 资产提示）。本 change 改成**分节**，每节聚焦一件事：

```
1. 顶层 spec 形状 + 各字段域（指向 schema）
2. 节点 kind 与 per-kind 字段适用表（D5）
3. 边的字段与 channel 语义（含「门控 vs 渠道正交」，D3）
4. cases 匹配语义（行首 + first-match-wins + 具体在前，D4）
5. 环的契约（既有内容，逐字保留）
6. 正例（修正后）/ 反例
7. 资产提示（既有）
```

**为什么**：模型的失败是**局部的**（域），但当前描述的**组织**让局部信息难以定位。分节让「我只想知道 `cases` 怎么写」有确定的落点。

**约束**：不改描述里的**既有正确内容**（循环契约一节经 #262/#246 多次 grill 与 spec 锁定，`spec.md:405-420`）——**只做插入与纠错**。

### D9 — 描述与 schema 的**内容分工**要有明确规则，避免两处漂移

描述引用枚举时**不再逐字重复**（如当前 `:511` 重写了 `concat/merge_dict/first_non_empty/last`），而是**指向**字段（「`reducer` 的合法值见 schema」），并在 schema 的字段级 `description` 里写一句话说明该字段**属于哪个 kind**。

**为什么**：事实 2 的 `strategy: "concat"` 的**直接诱因**就是描述里刚列出了 `REDUCERS` 的四个值、而 `strategy` 自己的值没说全。**枚举只在一个地方出现**（schema），描述负责「怎么用」，schema 负责「是什么」。

**替代方案**：描述与 schema 都写一遍（双保险）——否决。两份必然漂移（D2 的实证），且描述里的那份**会再次被跨字段误借**。

### D10 — 不引入 `ValidateWorkflow`（Non-Goal），列为 Open Question

issue #248 方向 5 提出：「当前唯一校验入口 `DeclareWorkflow` 会**注册** workflow，『只想 check 一下』会污染 registry」。

**本 design 的判断（供 grill）**：**不引入**。理由：

1. **RIR RQ5：没有任何参考实现提供独立的只读 validate 工具。** 校验一律内联在「提交」动作里（`pi` 的 `modeCount`、`deepseek-harness` 的 `z.object` 解析、`codex` 的 JSON Schema 校验）。
2. **它会**合法化**试错**——而本 change 的目标恰恰是让模型**不需要试**。给一个「查一下不花钱」的工具，等于给探针循环发通行证。这**直接违背**本 change 的验收主指标（探针数 = 0）。
3. registry 污染是**真实但轻微**的：`DeclareWorkflow` 只注册、不启动（`subagents.py:565-581`），未启动的图零成本；且 registry 是 per-manager in-memory，会话结束即释放。

**但**：若 grill 认为「模型先 declare 一次、被拒、再 declare」本身就是一种浪费的试错，那 validate 通道会有价值——**这是用户的判断，不是本 design 的**。见 Open Question **Q4**。

## Pre-Implementation Review

> 本 change 为**非平凡 change**（`primary: feature` ∈ `DESIGN_TYPES`），实现前须按 AGENTS.md 走 `batch-grill-me`（或等价独立 subagent 设计追问）审视本 design.md 的 D1–D10，逐项确认实现细节、依赖、风险、测试策略与文档影响，产出结构化决策记录到 `reviews/grill-design.md`，并经**停轮确认**（grill-confirmation-gate：每条 Open Question 配具体例子抛给用户，收到答复前不得写实现代码）。
>
> **本 design 刻意保留的未决项**：D6（route `task` 三方案 —— 用户未拍板）、D2（schema 升级的幅度是否过度）、D10（是否引入 `ValidateWorkflow`）、D9（描述与 schema 的分工粒度）。这四项列入 `## Open Questions` Q1–Q4，**grill 前不作结论**。
>
> **本 change 由 workflow_guard / artifact checker 机械门禁**：触及 `openspec/specs/**` 与 `docs/openspec-change-backlog.md`（受保护路径），实现阶段需 `current_spec_synced` / `backlog_updated` 结构化事件；归档点需 `reviews/grill-design.md`（≥3 决策 + 全部 OQ 已确认）+ `reviews/building-review.md`。

## Risks / Trade-offs

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | **schema 变大使每轮 input token 上升**（`parameters` 每轮都发，事实 1） | 每次调用 +≈400–700 token | 对照组是基线一次失败执行的 **398,590 token**——消除一次探针循环即回本。若 grill 认为过度，D2 可降级为「只加 `channel`/`strategy`/`join` 三个 enum」（D2 替代方案） |
| R2 | **描述变长稀释注意力** | 关键信息被淹没 | D8 分节 + D9「枚举只在 schema」——描述**净增文字有限**（删 4 处 `control` 后总量仍受控）。测试 T2 锁关键句存在 |
| R3 | **parity 测试写得太宽**（只断言「enum 非空」） | 派生退化，漂移无声 | T1 断言**逐字相等**（`tuple(schema_enum) == SOURCE_CONSTANT`），并配变异验证（改常量 → 测试必须红） |
| R4 | **D6 选 (a) 时改生产模板** `patterns.py:205` | peer-review 模板行为变化 | 该字段**本来就不生效**，去掉是纯粹的语义澄清，零运行时影响；T4 用 spec_hash 前后对照证明 |
| R5 | **D7 只改文案，模型可能仍不理解** | 误导消失但困惑留存 | D5 的字段表是**事前**解法，D7 是**事后**兜底；两者叠加才完整 |
| R6 | **验收主指标（探针数）依赖主观判定** | 「什么算 probe workflow」有边界模糊 | proposal 验收节给了**机械可提取**的定义（`goal` 以 `probe:` 开头 或「无业务目标、仅验证语义」）；S0 为主指标，S1–S6 为辅助交叉验证。**不设 token 阈值**——收益形态是消除整类无效动作 |
| R7 | **改后模型可能仍然写错**（工具面修好 ≠ 任务变简单） | 验收可能不通过 | 这正是验收节区分「理解工具 vs 理解任务」的原因：若 token 降但探针不降，说明方向错了；若探针降为 0 而任务仍难，说明本 change 成功 |

**已知的正面代价（有意接受）**：D9 让描述**不再重复枚举**，这会牺牲一点「描述自足性」（读者需要同时看 schema）。这是有意的取舍——**单一来源**比**自足**更重要，因为漂移是实证发生过的问题（#246 / D2）。

## Testing Strategy

**T1 — schema ↔ 常量 parity（最重要的单条测试）**
断言 `DeclareWorkflow.spec` 与 `RunWorkflow.spec` 的 `parameters` 中，每个 enum 与对应源码常量**逐字相等**：`kind`↔`NODE_KINDS`、`channel`↔`CHANNELS`、`reducer`↔`REDUCERS`、`strategy`↔`AGGREGATE_STRATEGIES`、`join`↔`JOIN_SEMANTICS`、`mode`↔`NODE_MODES`。**配变异验证**：临时改一个常量，测试必须红（防「恒真断言」——这是 #246 R3 与 #196 都踩过的坑）。

**T2 — 描述内容断言**
沿既有范式（`tests/agent/subagent/test_workflow_cycle_contract.py:545-575` 的 `assert "..." in text`）：
- `"control"` 在 `DeclareWorkflow` 描述中**零命中**（D3 的机械保障）；
- `cases` 语义句存在（含 `startswith`/行首/first-match 的措辞，D4）；
- per-kind 字段表存在（`join`/`items`/`source` 作为**字段名**出现，D5）；
- `$ref:` 出现（D4）；
- **既有循环契约的断言全部保持绿**（`"defaults to 1"` 等，`spec.md:405-420` 依赖它们）——本 change 只做插入与纠错，**不删既有契约文字**。

**T3 — route `task` 的处置（依赖 D6 拍板）**
- 若 (a)：新增「route 带 `task` → `WorkflowValidationError`」测试；同步改 **15 处 / 5 文件**（AST 实测清单见 Impact Analysis）+ 生产模板 `patterns.py:205`。
- 若 (b)：新增「route 带 `task` → `declared` 且返回体含 `warnings`」测试；**既有 15 处保持零改动**（这是选 (b) 的核心收益）。
- 若 (c)：仅新增描述断言（T2）。**须在 design/review 记录「静默陷阱保留」这一已知损失**。

**T4 — 无回归**
- 全量 `uv run pytest -q`。
- `patterns.py` 的四个模板 `spec_hash` 对照（若 D6 选 (a)，peer-review 的 hash 会变——**这是预期的**，须在测试里显式断言新值并写明原因，SHALL NOT 写成「hash 随便」）。
- 工具集断言（`test_workflow_tools.py`）：工具**数量与名字不变**。
- benchmark smoke（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`）——本 change 触及 `agent/tools/`（命中 `_requires_benchmark_smoke` 的代码模式）。
- `openspec validate --all --strict` + `check_openspec_artifacts.py`。

**T5 — 描述长度守卫（防 R2）**
断言描述长度在一个**宽松上界**内（如 ≤ 6000 字符），防「分节」演变成无节制扩张。**不设下界**。

**T6 — 端到端验收（不在 pytest 内）**
proposal 验收节的三次真实 LLM rollout，由实现方产出证据 + `/review-loop` 独立 reviewer 核验。

> **T6 的定位**：它不是 CI 的一部分（贵、flaky、需真实 LLM），但它是本 change **唯一的有效性证据**。T1–T5 只能证明「工具面变好了」，T6 才回答「模型是否因此少走弯路」。两者缺一不可，且**不可互相替代**。

## Open Questions（grill 前不作结论，每条配具体例子）

> 以下四项**本 design 刻意不拍板**。每条给出真实场景例子（用本 change 的 DSL，具体到参数/输入输出/前后对比），供 grill 停轮确认时逐条抛给用户。

### Q1 — route 节点的 `task`：三方案选哪个？

**场景例子**：模型想写一个「评审不通过就重做」的环，给 route 节点写了判定 prompt：

```json
{"id": "gate", "kind": "route",
 "task": "阅读上游仲裁结论。若出现 `GAPS:` 且其值不是 none，则选择回到 intake……",
 "cases": [{"when": "GAPS", "to": "intake"}],
 "default": "report", "max_routes": 3}
```

- **今天的行为**：`declared` 成功；运行时 `gate` 的 `runs` 恒为 0、`subagent_id: null`（`_execute_route` 不读 `task`）；模型只能从 `runs: 0` 反推「我这段 prompt 白写了」。整个 `wf_f970f143` 零收益。
- **(a) 拒绝**：上面这个 spec 直接 `invalid_spec`，reason 说明「route 是纯控制节点，`task` 不生效；判定逻辑请写在 `cases[].when` 里」。**代价**：`tests/agent/subagent/` 下 15 处（5 文件）+ 生产模板 `patterns.py:205` 都要改。
- **(b) warning**：`declared` 返回体多一个字段：`{"status":"declared","workflow_id":"wf_...","warnings":["node 'gate' (route) declares `task` which is ignored: route nodes are pure control nodes"]}`。**模型能当场看到**，这次调用仍然成功。
- **(c) 只写描述**：描述里加一句「route 是纯控制节点，`task` 不生效」。今天的情形就是不写这句的后果。

### Q2 — schema 升级的幅度：全量 per-kind 域，还是只加三个最痛的 enum？

**场景例子**：模型要写 `{"id":"merge","kind":"aggregate","outputs":["draft"],"join":"all_required","strategy":"collect"}`。

- **全量方案**：schema 里 `kind`/`channel`/`reducer`/`strategy`/`join`/`mode` **全部**带 `enum`（约 +5 个枚举 + 嵌套 properties，每次调用 +≈400–700 token）。
- **最小方案**：只给实测踩坑的三个加 `enum`（`channel` / `strategy` / `join`），其余留描述。代价更低，但 `reducer`/`kind`/`mode` 仍是「描述里说了、schema 里没有」。
- **判据**：本 change 的主指标是**探针数**。基线的 20 个探针里，有多少是 `reducer`/`kind`/`mode` 引起的？**目前无分解数据**——若 grill 认为需要，实现阶段可先在基线 transcript 上做一次归因统计再定幅度。

### Q3 — 描述的「形」要写到多细？是否要覆盖 `aggregate` 的 `deadline_s` / `foreach` 的 `source_field` 等低频字段？

**场景例子**：`foreach` 的 `source` 跨层解析规则是「只沿数据边向上、多入边歧义拒绝、环检测复用 Tarjan SCC」（`workflow.py` `_validate_foreach_source_cycles`），`source_field` 只应用一次。这些规则**复杂且有陷阱**，但实测中模型一次都没碰过 `foreach`（它用的是 4 个 subagent 节点，不是 `foreach`）。

- **写**：描述完整覆盖，代价是长度（R2 风险）。
- **不写**：只说明字段**存在**与**属于 foreach**（D5 的表），细节留给错误信息。
- **判据**：基线的失败分布里 `foreach` 命中数为 0。**本 design 倾向「只给字段表 + 一句『`source` 跨层解析有歧义拒绝规则，细节见错误信息』」**，但这是可调的。

### Q4 — 是否引入只读的 `ValidateWorkflow` 工具？

**场景例子**：模型不确定自己写的图合不合法，今天的唯一选项是 `DeclareWorkflow`——但它的副作用是**注册**一个 workflow（`manager.register_workflow`，`subagents.py:578`）。

- **不引入**（本 design 倾向）：模型必须一次写对，或在失败中学习。**风险**：若模型有「先试一下」的惯性，会继续用 `DeclareWorkflow` 当探针（今天的 20 个探针就是这样来的）。
- **引入**：`ValidateWorkflow(spec)` → `{"valid": true}` 或 `{"valid": false, "reason": "..."}`，零副作用。**风险**：把「试」变成零成本的默认动作，**可能推高**探针数（与验收主指标冲突）；且 RIR RQ5 显示无参考实现这么做。

## 附录 A：DSL 字段「域」权威清单（schema 与描述的派生输入）

> 本表从源码逐字抽取，是 D2/T1 的输入。**表本身不手写进 schema**——schema 由源码常量程序化展开；本表只用于设计与评审对照。

### A.1 顶层 spec 字段（`_SPEC_FIELDS`，`workflow.py:43-54`）

| 字段 | 类型 | 域 / 默认 | 来源 |
|---|---|---|---|
| `schema_version` | string | `"workflow.v1"`（唯一合法值） | `SCHEMA_VERSION`，`:28` |
| `goal` | string | 任意（默认 `""`） | `:346-348` |
| `nodes` | list | **非空** | `:350-353` |
| `edges` | list | 可为空（默认 `[]`） | `:366-368` |
| `entry` | list[str] | 节点 id；缺省 = 无入边节点（route 控制边不算入边） | `:400-412` |
| `terminal` | list[str] | 节点 id；缺省 = 无出边节点 | `:413-417` |
| `recursion_limit` | int ≥1 | 默认 **100**（配置 `subagents.workflow.recursion_limit`） | `:41` / `:441-448` |
| `max_nodes` | int ≥1 | 默认 **200** | `:42` |
| `max_runs` | int ≥1 | 默认 **300** | `:42` |

### A.2 节点字段（`_NODE_FIELDS`，`workflow.py:56-78`）

| 字段 | 适用 kind | 域 / 默认 |
|---|---|---|
| `id` | 全部 | 非空字符串，图内唯一 |
| `kind` | 全部 | **`subagent` / `aggregate` / `route` / `foreach`**（`NODE_KINDS`，`:30`） |
| `task` | subagent（**必填**）、foreach（**必填**）、aggregate（可选）、**route（接受但忽略 → Q1）** | 字符串 |
| `name` / `description` | 全部 | 字符串（元信息） |
| `mode` | 全部 | **`build` / `read_only` / `plan`**（`:503-506`，须提为 `NODE_MODES`） |
| `outputs` | 全部 | 非空 slot 名列表；默认 `["result"]` |
| `join` | **aggregate** | **`all_required`（默认）/ `best_effort`**（`JOIN_SEMANTICS`，`:31`）；`best_effort` **必须**显式给 `deadline_s` |
| `strategy` | **aggregate** | **`llm`（默认）/ `collect`**（`AGGREGATE_STRATEGIES`，`:32`） |
| `deadline_s` | aggregate（`best_effort` 时必填） | 正数 |
| `cases` | **route** | `{"when": str, "to": str}` 列表（**仅这两个键**，`:398-402`）；`when` = 字面标签 或 `$ref:<node_id>:<slot>` |
| `default` | **route** | 节点 id，可缺省 |
| `max_routes` | **route** | 正整数，默认 **1**；**节点级、跨轮累计、不重置** |
| `items` | **foreach** | 列表（`items` 与 `source` **二选一**） |
| `source` | **foreach** | 节点 id（配合 `source_field`，二者**同给同缺**） |
| `source_field` | **foreach** | 字符串 |
| `max_items` | **foreach** | **非负** int，默认 **20**，`0` = 不静态截断；`items` 上界 |
| `max_tokens` | 全部（run 预算） | 正整数，可缺省 |
| `max_time_s` | 全部（run 预算） | 正数，可缺省 |

**无 `deadline_s` 之外的时长字段**；**无 `retry`/`timeout`/`priority` 等字段**——不存在，写了会 `unknown node field(s)` 拒绝。

### A.3 边字段（`_EDGE_FIELDS`，`workflow.py:80`）

| 字段 | 域 / 默认 |
|---|---|
| `from` | 节点 id（必填） |
| `to` | 节点 id（必填） |
| `channel` | **`result_ref` / `summary`（默认）/ `artifact` / `bus`**（`CHANNELS`，`:35`）—— **`control` 不是合法值** |
| `required` | bool，默认 **`true`**（数据边门控）；route 出边是控制边，**`required` 对它无意义** |
| `reducer` | 缺省 `null` = 无 reducer。合法值：**`concat` / `merge_dict` / `first_non_empty` / `last`**（`REDUCERS`，`:34`）。**多入边写同一 output slot 时必须声明**，否则拒绝 |

### A.4 语义规则（不进 schema，进描述）

| 规则 | 依据 |
|---|---|
| 环上**必须**有 `route` 节点 | `_validate_cycles`，`workflow.py:660-681` |
| 环内**必须**有能自启动的节点（不等环内其他节点） | `_validate_cycle_can_start`，`:437-439` |
| route 出边 = 控制边（不 gate、不传数据、不参与 reducer） | `is_control_edge`，`:243-245` |
| 其他节点出边 = 数据边（默认 gate） | 同上 |
| `cases` 匹配 = **行首** `startswith` + **声明顺序 first-match** | `matches_route`，`scheduler.py:323-338` |
| 多入边写同 slot 必须声明 reducer | `_validate_reducers`，`:390` |
