# Grill: workflow-tool-discoverability 设计追问

独立零记忆评审者产出。本文件只记录**挑战**结果，不代表用户确认；`## Open Questions` 全部需用户逐条答复后才可写实现代码。

## Reviewer

- run id: d061a077-b0c0-46ae-bfc1-571412c3c280
- 时间: 2026-09-29
- 复核方式: 在 worktree 内直接读源码 + `uv run python` 现场复现（`parse_workflow_spec` 直调）+ AST 扫描测试面 + `git log` 核对引用时点。**未采信 proposal/design 的任何自称事实**。

## Confirmed Decisions

- **决策**: D1「schema 管域、描述管形」的分工线成立，且是正确的一刀。；理由: 我独立复现了「形对、域错」的实证——`parse_workflow_spec` 对顶层结构（`goal`/`nodes`/`edges`/`entry`/`terminal`）接受度高，而对 `channel`/`strategy` 这类封闭域处处设卡（`workflow.py:664-670` 的 channel 白名单、`:568-573` 的 strategy 白名单）。且「域进 schema」确实零结构风险：`agent/tools/base.py:53-61` 把 `parameters` 原样放进 `function.parameters`，`agent/anthropic_llm.py:746-753` 的 `_convert_tool` 只做改名（`parameters` → `input_schema`），不校验、不裁剪，嵌套 `properties`/`items`/`enum` 全程无阻。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280
- **决策**: D2「枚举从源码常量派生、不手写」的**方向**成立，且 parity 测试必须断言**顺序**（元素元组相等，不是集合相等）。；理由: 常量确实存在且是唯一真相源（`workflow.py:30/31/32/34/35` 的 `NODE_KINDS`/`JOIN_SEMANTICS`/`AGGREGATE_STRATEGIES`/`REDUCERS`/`CHANNELS`）。更关键的是，我实测到 `mode` 的域**已经有第二份手写副本**活在同一个被改文件里（见 Design Corrections #2），这正是 D2 断言的漂移形态、且不是假设而是现状。顺序敏感这一点必须保留：若实现者写成 `set(schema_enum) == set(CONST)`，一个「常量顺序变了但 schema 没跟」的漂移会静默通过——而顺序恰恰是 `enum` 在模型侧的提示强度来源。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280
- **决策**: D3「删掉描述里的 `control`」是**纠错而非改进**，且改动面可控、可机械断言。；理由: 逐字复核 `agent/tools/builtin/subagents.py`，字符串 `control` 全文**恰好 4 处**，全部在 `DeclareWorkflow` 的描述体内：`:518`（术语）、`:530`/`:531`/`:536`（非法示例），与 design 的表完全一致。我另外运行期验证了**其他工具描述零命中**（`RunWorkflow`/`CreateSubagent`/`RunSubagent`/`SaveWorkflowAsset`/`ListWorkflowAssets` 全部 `False`），所以 T2 的「零命中」断言可以精确限定在 `DeclareWorkflowTool.description`，不会误伤。同时 `control` 确实是系统里的真实取值——`scheduler.py:2855` 的 `"kind": "control" if ... is_control_edge(edge) else "data"`，design 的「两个正交概念挤同一个词」判断为真。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280
- **决策**: D7（修误导性错误文案）针对的是真实缺陷，且「只改文案、不改接受/拒绝行为」是可实现的。；理由: 我现场跑了 `parse_workflow_spec({"nodes":[{"id":"g","kind":"route","strategy":"concat"}],...})`，返回 `aggregate node 'g' strategy must be one of ['llm', 'collect']`——节点是 `route`，报的却是 `aggregate`。根因确认在 `workflow.py:559-573`：`_parse_join`/`_parse_strategy` 的文案硬编码 `aggregate`，而 `_parse_node`（`:469` 起）对**所有** kind 无条件调用它们，不看 `node.kind`。文案与判据分离，所以改文案不动语义是可行的。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280
- **决策**: 「事实 7 类 A（静默丢弃）」是比 design 描述的**更大**的面，D5 的字段表是必要缓解。；理由: 我不止复现了 design 举的那一个例子，而是把 16 种「字段 × 错误 kind」组合全跑了一遍：**13 种静默 `declared` 成功**（`subagent`+strategy/join/deadline_s/cases/max_routes/items/source、`aggregate`+cases/max_routes/items、`foreach`+cases/strategy/join、`route`+items），`to_dict()` 里这些字段整条消失、零提示。只有 3 种会进解析器报错。也就是说「写错但不报错」是**默认情形**而非边角，D5 把字段归属讲清的价值比 design 论证的更高。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280
- **决策**: T1 配「变异验证」的要求正确且必要。；理由: parity 断言若写成「enum 非空」或「schema 里存在该键」就是恒真断言；design 明确要求「临时改常量 → 测试必须红」并被 tasks 2.1a 承接，这是防恒真的唯一机械手段（#246 R3 / #196 的复发点）。；来源: d061a077-b0c0-46ae-bfc1-571412c3c280

## Design Corrections

### C1 — `workflow.py` 的 `文件:行号` 引用**系统性漂移**，实现者不可直接采信

`agent/subagent/workflow.py` 的常量段（`:28-35`）引用准确，但**第 35 行之后的行号全部漂了**（推断为 `#262` 在 `DEFAULT_*` 附近插入注释/改 docstring 后未回写 design）。实测对照：

| design 引用 | 引用所指 | 实际位置 | 偏差 |
|---|---|---|---|
| `workflow.py:503-506`（mode 内联元组） | `_parse_node` 里的 mode 校验 | **`:497`** | −6 |
| `workflow.py:243-245`（`is_control_edge`） | 该方法 | **`:256`** | +13 |
| `workflow.py:546-570`（`_parse_node`） | 该函数 | **`:469`** 起 | +77 |
| `workflow.py:571-577`（`_parse_strategy`） | 该函数 | **`:567-573`** | −4 |
| `workflow.py:566-570`（`_parse_join`） | 该函数 | **`:559-565`** | −7 |
| `workflow.py:598-599`（`_parse_max_routes` 文案） | 该函数 | **`:586`** | −12 |
| `workflow.py:88-107`（`$ref` 解析） | `ROUTE_REF_PREFIX`/`parse_route_ref` | **`:99`** 起 | +11 |
| `workflow.py:437-439`（`_validate_cycle_can_start`） | 该函数 | **`:968`** | +531 |

`agent/tools/builtin/subagents.py` 的引用（`:504-541` 描述、`:544-552` parameters、`:518/530/531/536` 的 control）**全部准确**——漂移只发生在 `workflow.py`。tasks 3.1 直接照抄 `:503-506` 就会改错行。

### C2 — D2 的「唯一一处在源码侧新增常量」不实：`mode` 的域**今日已有多份手写副本**

`agent/tools/builtin/subagents.py:51`（就是本 change 在改的同一个文件，同一批工具）：

```python
"mode": {"type": "string", "enum": ["build", "read_only", "plan"]},   # CreateSubagent
```

`agent/run_config.py:19-22` 是第二份（`AgentMode` 枚举，含 `BYPASS`），`:31` 是第三份（字符串别名表，含 `read-only`/`bypass`）。也就是说：**在 D2 成立的那一刻，本 change 会新造一个 `NODE_MODES`，却把同一个文件里 30 行之上的手写孪生体留在原地**——这恰好是 D2 用来论证自己的那类漂移（「源码加一个 kind，schema 里漏一个」）。D2 的论证因此**自我削弱**：它不仅没消除重复，还新增了第三个定义点。

### C3 — D8 与 D3 直接矛盾

D8 约束「不改描述里的既有正确内容……**既有循环契约一节逐字保留**，只做插入与纠错」，而 D3 要改的 `:518`（`"- A route's OUTGOING edges are control edges: they never gate."`）**就在循环契约一节内部**。D8 需要改写成「保留该节的**语义与既有断言串**（`defaults to 1` / `per route node` / `reset` / `gate->producer` / `body->gate`），允许并且要求改写其中出现非法 token 的措辞」。

### C4 — D6 (b) 的代价被**高估**：「warnings 通道」在同文件已有同构先例

design 说 (b)「需要设计一个**新的返回字段通道**（目前 `declared` 返回体没有 warnings 概念）」。但同一文件的 `RunWorkflowAssetTool` 返回体里已经有形态完全相同的诊断数组：`agent/tools/builtin/subagents.py:1372-1373`

```python
payload["declared_mode_nodes"] = declared_nodes
payload["mode_diagnostics"] = diagnostics
```

即「在成功返回体里追加一个结构化诊断数组，逐节点给 declared/applied」——(b) 要做的是**同一个动作的第二次实例化**，不是从零设计。(b) 的真实代价应重估为「一个小 helper + 一行 payload 注入」。因此 (a)/(b)/(c) 的比较基线需要按修正后的代价重排（(b) 的成本进一步下降，而 (a) 的 15 处测试 + 生产模板改动不变）。

### C5 — D10 的理由 2 推理不成立（结论可保留，论据必须换）

design 写：ValidateWorkflow「会给探针循环发通行证……**直接违背本 change 的验收主指标（探针数 = 0）**」。这个推理有概念滑移：proposal 的 S0 定义是「**`goal` 以 `probe:` 开头、或只为验证语义的 `DeclareWorkflow` 声明**」——**统计对象是 workflow 声明**。`ValidateWorkflow` 不声明 workflow、不注册、不进 S0。一个零成本校验工具若被使用，作用方向更可能是**降低**无效声明数（模型校验通过后一次声明成功），而不是推高 S0。design 把「试错被合法化」直接等同于「S0 上升」，中间少了一步论证。

「不引入」的**结论**仍可站住，但正确论据是另外两条：RIR RQ5（无参考实现提供只读校验工具）与**范围纪律**（新增工具 = 新增能力面，需要自己的调研档位与 grill 轮次，不是本 change 该塞进来的东西）。design 现有的理由 2 应删除或改写。

### C6 — R1 的 token 估算只算了 schema，**漏算描述本体的增长**

- schema 部分：我按「全量 + 每个字段一句 `description`」手写了一份等价 schema 实测 **1508 字符 ≈ 400 token**，加上逐字段说明约 **600-700 token**——design 的「+400~700 token/轮」区间**有依据、成立**。
- 描述部分：D8（分节）+ D4（cases 一节含正反例）+ D5（per-kind 字段表）+ D3（正交关系一段）+ D9（枚举改指向）全部是**增量文字**，而现状描述只有 **2063 字符**（我运行期取 `DeclareWorkflowTool.description` 实测；design 写的 2504 是**源码字符数**含缩进与引号，两者不是同一口径，design 内部两处混用——`:5` 用 2504，需统一）。T5 的上界是 6000 字符 = 现状的 2.9 倍，即描述侧最坏再增 ≈ +3900 字符 ≈ +1000 token。

**合起来真实上界 ≈ +1400~1700 token/调用**，而非 R1 写的 400-700。design 的结论「相对基线 398,590 token 可忽略」**仍然成立**（按 54 迭代算，最坏 +9 万 token，仍远低于一次探针循环），但数字要如实改为两段。

### C7 — 「route 的 `task` 被忽略」在**声明/回读侧不成立**，只在执行侧成立

design 事实 6 与附录 A.2 写「route（接受但忽略）」。我实测 `parse_workflow_spec` 后 `to_dict()` 的节点输出是：

```python
{'id': 'r', 'kind': 'route', 'task': 'my prompt', 'outputs': ['result'], 'cases': [], 'default': 'r', 'max_routes': 1}
```

`task` **被完整保留**并进入 spec 指纹与快照投影——只有 `_execute_route`（`scheduler.py:1866-1909`）不读它。这个区别对 Q1 有实质影响：(a)/(b) 的文案必须说「route 的 `task` **不会被执行**」，而不能说「route 没有 `task` 字段」——后者与 `to_dict()`/`spec_hash` 的行为直接冲突，会诱发新一轮「看起来权威但错的域」。

### C8 — 若 Q1 选 (b)，**`RunWorkflow(spec=...)` 这条入口拿不到 warning**

(b) 的落点在设计里默认是 `DeclareWorkflowTool.execute` 的 `declared` 返回体（`subagents.py:571-585`）。但 `RunWorkflow(spec=...)` 走的是**另一条路径**：它自己调 `parse_spec_for_manager`（`subagents.py:993`）后直接 `_drive_scheduler` 返回 **run envelope**（`:1005`），**从不经过** `DeclareWorkflowTool.execute`。结果是：同一份「route 带 `task`」的 spec，用 `DeclareWorkflow` 声明会收到 warning，用 `RunWorkflow(spec=...)` 一步跑完则**什么都没有**——静默陷阱在这条入口上原样保留。

spec delta 的 Scenario「两条声明入口的 spec schema 一致」只约束了 **schema**，不约束返回体；tasks 3.13 也只写了「`declared` 返回体新增 `warnings` 数组」。所以这是 design 与 tasks 都没覆盖的**半边**。选 (b) 时必须明确两件事：(1) warning 的生成点应放在 `parse_spec_for_manager` 之后、**两条路径共用的位置**（或抽成 helper 两条路径各调一次）；(2) `RunWorkflow` 侧的 warning 应挂在 run envelope 上（那里天然有 `mode_diagnostics` 一类的诊断位，见 C4）。若只做 `DeclareWorkflow` 侧，(b) 的收益会打对折。

## Risks

- **R-A｜T2 的 `control` 零命中断言有两处自伤面。** 现有描述断言的写法是 `text = _declare_description().lower()`（`tests/agent/subagent/test_workflow_cycle_contract.py:552-556`）。若 T2 沿用 `.lower()`，那么任何中文段落里的英文 token（如 "no control edge"）仍会被抓到——这是**想要**的；但反过来，若实现者用中文「控制边」表述就完全绕过断言，等于测试形式化。建议 T2 明确写死：断言对 **`DeclareWorkflowTool.description`（原样、不 lower）** 做 `"control" not in desc`，并**额外**断言 `"control" not in desc.lower()`，两条都要。
- **R-B｜派生 helper 必须参数化 `required`，否则要么破测要么入口不一致。** `RunWorkflow.parameters["required"] == []` 被 `tests/agent/subagent/test_run_workflow_template.py:187-190`（`test_schema_drops_required_spec`）钉住；`DeclareWorkflow.parameters["required"] == ["spec"]`。spec delta 的 Scenario「两条声明入口的 spec schema 一致」指的是**嵌套结构与 enum 一致**，不是 `required` 一致。若 helper 把两者一并写死就必破一处。
- **R-C｜嵌套 schema 内部要不要写 `required`，design 完全未决。** 节点的 `task` 对 `subagent`/`foreach` 必填、对 `aggregate` 可选、对 `route` 无意义；`foreach` 的 `items`/`source` 是二选一。这些**无法**在不引入 `oneOf` 的前提下表达（D1 已论证），所以正确形态是**嵌套层不写 `required`**（或不写节点级 `required`）。design 没有把这个「不做」写下来，实现者很可能顺手加上 `"required": ["id","kind","task"]`，凭空造出一批 schema 层拒绝。这是 design 的隐藏未决细节。
- **R-D｜`cases` 的 schema 形态未定义。** D2 列了 6 个 enum（不含 `when`，这一点**正确**——`when` 是「字面标签或 `$ref:`」的开放域，`workflow.py:99-107`）。但 design 从没写 `cases` 在 schema 里长什么样（`{"type":"array","items":{"type":"object","properties":{"when":{"type":"string"},"to":{"type":"string"}}}}`）。不写清楚，实现者有相当概率给 `when` 硬塞一个 enum，把 `$ref:` 形态堵死。
- **R-E｜Q2 的前置任务（tasks 0.4「在基线 transcript 上做归因统计」）当前**执行不了**。我把常见落盘位置全查了一遍：`/home/happy/.asterwynd/sessions/` 不存在；`/home/happy/my-agent/.asterwynd/sessions/` 下 65 个 session 里 `grep "probe:"` **零命中**、也无 `fanout-review-loop`；`/home/shared/code/temp/.asterwynd/sessions/edd3b6ded5eb/messages.json` 是**另一个** session（54 条消息，`DeclareWorkflow` 11 次，`"probe:"` 0 次），不是本次 19 次声明的那个；`/tmp/.asterwynd/` 只有 `workflows/`（68 张，内容是 `ZZZZ...` 测试桩，mtime **09-21～09-27**，**全部早于基线**）与 `subagents/`，**无 `sessions/`**；`/tmp/tmp*/` 下的 `.asterwynd/sessions/` 全是 `aaaa11111111` 测试夹具（msgs=1）；`/home/happy/.asterwynd/ledger.jsonl` 是 57459 个测试 session 的记账噪声，`grep "probe:"` 0 命中。

  基线里唯一幸存的是 `~/.asterwynd/projects/e9671acd244849c5/workflow-assets/`。注意这个 project hash 就是 **`/tmp`**（我算过 `_compute_project_hash(Path('/tmp')) == e9671acd244849c5`），即基线是以 `cwd=/tmp` 跑的。该目录的 `events.jsonl` 给了**完整时间线**：`probe-asset`(02:11:29Z) → `a1`(02:13:09Z) → `my-dsl`(04:41:36Z) → `my-recipe`(04:42:30Z) → `r`(04:42:51Z) → **`fanout-review-loop`(10:09:59Z, `spec_hash=7f3ca786dfc2eb0b`)**。我把这 5 个"垃圾"资产逐个打开核对：`probe-asset`/`a1`/`my-recipe`/`r` **全部 `source: "pattern"`、无 DSL spec**（四者 `spec_hash` 都是 `23571776a101688c`，是模板身份），`my-dsl` 是一个 2 节点的平凡 DSL（`a → root`）——**它们都不是模型的探针 workflow**，而正是 proposal 说的**改前就存在的污染**。**结论：20 个探针声明没有留下任何可恢复的产物**（探针从未被 `SaveWorkflowAsset`，故不进资产库；transcript 与 per-workflow 记录均已不在盘上）。因此 proposal/design 的基线数字（19/20/4/15/54/398,590）**无法从盘上复算，只能采信文档**。这同时波及 T6 的「改前/改后对照」——见 Q2、Q5。
- **R-F｜验收主指标 S0 的机械口径有洞。** proposal 的 S0 定义含一个**主观**分支（「或『只为验证语义、不含业务目标』的声明」），并非它自称的「机械可提取」。模型把探针命名为 `test-topology`/`sandbox` 即可规避 `probe:` 前缀；另外「声明了但从未 StartWorkflow」的图也完全不计入。可补一个**纯机械**的辅指标：**声明数 − 启动数**（proposal 自己的数字就是 19 − 14 = **5** 张声明后未启动；这个数不需要读 transcript 语义就能提）。
- **R-G｜D6 选 (a) 会把「改工具面」扩大成「改生产模板 + 改 15 处测试」。** AST 扫描确认 15 处 / 5 文件（`test_scheduler.py:418,451,491,638,674`、`test_workflow_cycle_contract.py:65,152,190,289,347,380,383`、`test_recursion_limit_default.py:199`、`test_truncation_diagnostics.py:100`、`test_workflow_spec.py:152`）与 proposal 一致，且 `patterns.py:205`（peer-review 的 `gate` 节点）确实自带 `"task": "route on the reviewer verdict"`。注意 `patterns.py:205` 的 `task` 去掉后 peer-review 的 `spec_hash` 会变，而**验收资产 `fanout-review-loop.json` 是 DSL 源、不走模板**，所以若在同一 PR 里重跑验收，模板 hash 变化会与资产对照混淆——T4 的 hash 显式断言必须与 T6 的验收证据分开落盘。

## Open Questions

> 以下为**最终版**清单（含并入/改写/新增）。每条必须由用户逐条答复并记录到 `## User Confirmation` 后才可写实现代码。
>
> **相对 design 的变更概览**：Q1 保留并补强；Q2 保留并补强（新增 transcript 不可得的事实）；**Q3 建议撤出阻塞集**（理由见 Q3 条目）；Q4 保留但**换论据**；**新增 Q5（验收 baseline 是否重跑）**；**新增 Q6（CreateSubagent 的 mode enum 是否一并派生）**。

### Q1 — route 节点的 `task`：四选项选哪个？

**例子**（沿用 design，已复核为真实场景）：模型想写「评审不过就重做」的环，给 route 节点写了判定 prompt：

```json
{"id": "gate", "kind": "route",
 "task": "阅读上游仲裁结论。若出现 `GAPS:` 且其值不是 none，则选择回到 intake……",
 "cases": [{"when": "GAPS", "to": "intake"}],
 "default": "report", "max_routes": 3}
```

今天的行为（我实测）：`parse_workflow_spec` **接受**，`to_dict()` 里 `task` **完整保留**（C7）；运行时 `_execute_route`（`scheduler.py:1866-1909`）不读它 → `gate` 的 `runs` 恒为 0、`subagent_id` 为 null。模型只能从 `runs: 0` 反推「我这段 prompt 白写了」。

- **(a) 声明期拒绝**：上面这段直接 `invalid_spec`，reason 说明「route 是纯控制节点，`task` 不会被执行；判定逻辑写在 `cases[].when`」。代价：**15 处 / 5 文件**测试 + **生产模板** `patterns.py:205`，且 peer-review 的 `spec_hash` 变化。
- **(b) 声明期 warnings**：`declared` 返回体多一个数组，如 `{"status":"declared","workflow_id":"wf_...","warnings":["node 'gate' (route) declares `task` which is never executed: route nodes only match `cases[].when`"]}`。这次调用仍然成功。**我复核了「零测试改动」这一声称：成立**——搜遍 `tests/agent/subagent/`，没有任何对 `declared` 返回体做**键集合相等**断言的测试（只有 `out["status"] == "declared"`、`out["nodes"] == [...]` 这类子集断言）。而且 RIR RQ4 的「接受但显式告知」是业界主流。
- **(c) 只写描述**：描述里加一句「route 是纯控制节点，`task` 不会被执行」。仍留静默陷阱。
- **(d)（我方新增）结构化标记而非自由文本**：声明期接受，但在 `spec.to_dict()` 与 workflow 快照里给该节点打 `"task_ignored": true`（机器可读），描述同时说明。前端（`web/static/workflow_graph.js`）与 `GetWorkflow` 都能显示，模型读 envelope 也能看到。代价介于 (b)/(c) 之间；缺点是模型要主动去读快照才看得到，**及时性弱于 (b)**。

**改写后的代价对照**：RIR RQ4 结论（沉默忽略是最差档）排除了 (c)；(b) 的成本经 C4 修正后明显低于 design 描述（同文件已有 `mode_diagnostics` 先例，(b) 是它的第二次实例化）；(a) 成本不变但语义最干净。

**我的推荐**: **(b)**。它在「消除静默」与「不破既有写法/生产模板」之间取得最优，且成本被 C4 修正后可忽略。若用户更看重「语义上不可能再静默」，选 (a)——但需接受模板 hash 变化与 15 处测试改动。不推荐 (c)。

### Q2 — schema 升级幅度：全量 per-kind 域，还是只加三个最痛的 enum？

**例子**：模型要写 `{"id":"merge","kind":"aggregate","outputs":["draft"],"join":"all_required","strategy":"collect"}`。

- **全量**：`kind`/`channel`/`reducer`/`strategy`/`join`/`mode` 全带 `enum`。我手写了一份等价 schema 实测 **≈1508 字符 ≈ 400 token**，加逐字段说明约 **600-700 token**/调用——design 的估算区间**成立**。
- **最小**：只给实测踩过的三个（`channel`/`strategy`/`join`）加 `enum`，其余留描述。

**新事实（影响本问）**：design 给的决策依据是「先在基线 transcript 上做归因统计再定幅度」（tasks 0.4），但我把常见落盘位置查遍后确认——**基线 transcript 已不在盘上**（详见 Risks R-E）。所以「先归因再定」这条路**当前走不通**，除非重跑基线（见 Q5）。

**我的推荐**: **全量**，且理由是 D2 自己的论据：一个**不完整却看起来权威**的 schema 比没有 schema 更糟（D2 原文）。最小方案会留下 `kind`/`mode`/`reducer` 三个「schema 里没有、描述里说了」的字段——模型无从判断「没有是因为不合法，还是因为作者忘了」。既然 schema 一旦引入就成为权威，就该一次给全。成本已由 C6 核定为可忽略。

### Q3 — 描述要覆盖 `foreach`/`aggregate` 低频字段到什么粒度？**（建议撤出阻塞集）**

**例子**：`foreach` 的 `source` 跨层解析（只沿数据边向上、多入边歧义拒绝、环检测复用 Tarjan SCC，`workflow.py:788` 的 `_validate_foreach_source_cycles`）、`source_field` 只应用一次。基线里模型**一次都没碰过 `foreach`**（它用的是 4 个 subagent 节点）。

**为什么我认为它不该是 Open Question**: design 在 Q3 里**自己给出了判据**——「基线的失败分布里 `foreach` 命中数为 0」以及明确的倾向「只给字段表 + 一句『`source` 跨层解析有歧义拒绝规则，细节见错误信息』」。这是**可由 design 自身判据决定**的实现细节，不是需要用户拍板的价值取舍。把它留在阻塞集只会增加用户的确认负担（而 AGENTS.md 要求每条 OQ 都必须配例子、逐条确认）。建议：**按 design 已有倾向定稿（只给字段表 + 一句指向错误信息），从 Open Questions 移除，写进 D5。**

### Q4 — 是否引入只读的 `ValidateWorkflow` 工具？

**例子**：模型不确定自己写的图合不合法。今天的唯一选项是 `DeclareWorkflow`，而它会注册一个 workflow（`subagents.py:570` 的 `manager.register_workflow(scheduler)`），「只想 check 一下」会留下一条 registry 记录（per-manager、in-memory、会话结束即释放，未启动的图零成本）。

**我改写的论据（见 C5）**: design 原理由「它会合法化试错 → 推高探针数」在 S0 的口径下**不成立**（S0 数的是 workflow 声明，不是校验调用）。**真正支持「本 change 不引入」的两条**是：(1) RIR RQ5——六个参考仓库无一提供独立的只读校验工具，校验一律内联在提交动作里；(2) **范围纪律**——新增一个工具就是新增一个能力面，需要自己的调研档位、自己的 spec delta 与自己的 grill 轮次，而本 change 的主题是「让已有的工具面可发现」。

- **不引入（本 change）**：模型必须一次写对，或在失败中学习。
- **引入**：`ValidateWorkflow(spec)` → `{"valid": true}` / `{"valid": false, "reason": "..."}`，零副作用。

**我的推荐**: **本 change 不引入**，但**另开一个 issue** 承载它（连同「模型先用 ValidateWorkflow 探路」这个假设的实测验证）。理由是范围纪律，不是 design 原文的「会推高探针数」。

### Q5（新增）— 验收 baseline 是否重跑？

**例子**：proposal 的验收要求「改后跑同一条提示词 3 次，与基线对照」。基线的关键数字是 19 次声明 / 20 个探针 / 4 次 `invalid_spec` / 15 次 `graph_recursion_exceeded` / 54 迭代 / 398,590 token。但我把盘翻遍后确认：**基线 transcript 与 20 个探针的声明记录都不在了**（详情见 R-E），幸存的只有最终产物 `fanout-review-loop.json`（`spec_hash=7f3ca786dfc2eb0b`，含 `entry: ["w1","w2","w3","w4","rework"]` 的完整 10 节点图）和文档里记下的数字。

- **A. 不重跑，直接引用文档数字当基线**：零成本。代价：那些数字**无法被独立复核**，而 `/review-loop` 的 reviewer 按 proposal 要求正是要核「数字真实性」——reviewer 会撞上「无法验证」。
- **B. 重跑基线 3 次**：与改后组同模型同提示词，数字可信、reviewer 可核。代价：真实 LLM，若模型仍迷路，单次可烧掉数十万 token（基线就是 398,590），3 次上界可观。
- **C. 折中**：重跑 **1 次**基线（而非 3 次）用于校准量级，改后跑 3 次；在证据里如实标注基线样本量 N=1 与其局限。

**我的推荐**: **C**。基线的作用是确认「改前确有大量无效动作」这一量级事实，而不是做统计检验；N=1 足以支撑量级，同时把成本控制在一个已知上界内。若用户接受 B 的成本也可，但 A 会让 T6 的独立核验失效。

### Q6（新增）— `CreateSubagent` 的 `mode` enum 是否一并改为派生？

**例子**：本 change 要新建 `NODE_MODES = ("build","read_only","plan")` 供 workflow 校验与 schema 共用。做完之后，同一个文件 `agent/tools/builtin/subagents.py` 的第 **51** 行仍然手写着 `"enum": ["build","read_only","plan"]`（`CreateSubagentTool`）。两份字面量内容此刻相同，但**没有任何东西保证它们继续相同**——将来 workflow 若支持第四个 mode（或 `read_only` 改名），schemas 会静默分叉。

- **一并派生**：`CreateSubagentTool` 也改成引用 `NODE_MODES`。成本 ≈ 1 行 import + 1 行替换；但会把本 change 的 diff 触及一个与 workflow DSL 无关的工具。
- **不派生**：维持现状，把手写孪生体留给未来。

**我的推荐**: **一并派生**。D2 的纪律是「手写枚举需要理由，派生是默认」，而此刻**没有任何理由**让第 51 行保持手写；本 change 正好动这个文件，是消除它的最低成本时点。若用户认为这超出「workflow 工具面」的边界，则应至少在 `docs/known-debt.md` 记一条债务（受保护路径，需 `workflow-events.jsonl` 事件）。

## User Confirmation

> 主 session 于 2026-09-29 停轮把本清单逐条（配具体例子）交用户拍板，以下为用户答复实质内容，由主 session 亲笔记录（非 agent 代笔）。

- **Q1**: 用户答复：**按推荐选 (b) 声明期 warnings**；**并追加一项要求**——warnings 的文案必须**让模型注意到并知道怎么改**，不能只说「task 被忽略」，要说清判定逻辑该写在哪里（`cases[].when`），使模型能当场修正而非只知道自己错了。确认时间: 2026-09-29
- **Q2**: 用户答复：**全量派生**（`kind`/`channel`/`reducer`/`strategy`/`join`/`mode` 全部带 `enum`，从源码常量派生）。确认时间: 2026-09-29
- **Q3**: 用户答复：**按 design 倾向定稿，不占用户拍板**（只给字段表 + 一句「`source` 跨层解析有歧义拒绝规则，细节见错误信息」）；该项从阻塞集移除，落进 D5。确认时间: 2026-09-29
- **Q4**: 用户答复：**本 change 不引入 `ValidateWorkflow`，另开 issue 承载**（连同「模型会用它探路」这一假设的实测验证）。确认时间: 2026-09-29
- **Q5**: 用户答复：**重跑 1 次基线**（而非 3 次，也不引用无法复核的文档数字），改后跑 3 次；证据中如实标注基线样本量 N=1 及其局限。确认时间: 2026-09-29
- **Q6**: 用户答复：**一并派生**（`CreateSubagentTool` 的 `mode` enum 改为引用新建的 `NODE_MODES`）。确认时间: 2026-09-29

> **附：用户对 Q1 追加要求的落地约束**（实现期必须满足）：(b) 的 warning 文案 SHALL 是可行动的——须同时给出「哪里错了」与「改到哪里去」。建议文案形态：
> `"node 'gate' (route) declares `task`, which route nodes never execute; route decisions come from `cases[].when` — move your decision text there."`
