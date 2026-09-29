# 验收证据：workflow-tool-discoverability（issue #248）

> 本 change 的**唯一有效性证据**（proposal 验收节）。改前/改后各跑同一条固定提示词、同模型
> （`deepseek-v4-flash`）、同 `--mode bypass`，机械提取 S0–S6。
>
> **证据归属**：rollout 由实现方产出并落盘（本文件 + 两个 transcript），`/review-loop` 的独立
> reviewer 核验其可信度（数字真实性、harness 是否被改动、结论是否 cherry-pick）。**reviewer
> 不自己跑 rollout**——贵、flaky。

## 固定提示词（一字不改，改前改后共用）

```
展示 workflow 能力，搞一个复杂的 workflow 跑起来：4 个并行 worker 各自分析一个方面，然后汇总，再根据汇总结论做条件判断，需要的话回到某一轮重做，最后聚合输出。
```

## Harness（可复核）

| 项 | 值 |
|---|---|
| 模型 | `deepseek-v4-flash` |
| provider / base_url | `anthropic` / `https://api.deepseek.com/anthropic` |
| mode | `bypass` |
| 上限 | `--max-iterations 80` + `timeout 2400`（TokenBudgetHook 只是监视器不是熔断器，必须外部兜住） |
| cwd | `/tmp`（**中立目录**，避免 agent 读到本 change 自己的 design/README） |
| workspace | `/tmp/wf-disc-baseline2`（基线）/ `/tmp/wf-disc-after-{1,2,3}`（改后）/ `/tmp/wf-disc-after-3b`（run 3 干净重跑） |
| 资产库 | 每次跑前 `rm -rf ~/.asterwynd/projects/*/workflow-assets/` |
| 源码 | 基线 = 干净 checkout `db79b05`（`/tmp/wf-disc-src-pristine`）；改后 = 本 worktree |

### 隔离修正（诚实记录）

- **污染 4（改后 run 3，已消除——本条改变了结论）**：三次改后 run 串行执行时，**run 2 末尾
  `SaveMemory` 写入的 workflow 语义记忆被注入 run 3 的起始上下文**（`MemoryIndexSource` 每 session
  注入 active 记忆摘要），使 run 3 的 S0=0 **不可信**。已在再次 quarantine 该 scope 全部 workflow
  记忆后**干净重跑 run 3**（= run 3b，S0=4）。详见下文「污染发现与修正」。**这是本文件最重要的一次
  自纠**——它把「1/3 达标」改写成「0/3 严格达标」。
- **污染 1（已消除）**：本机 `~/.asterwynd/projects/<hash>/memory/` 里存着**原始基线会话**写下的
  workflow 语义速查记忆（`asterwynd-workflow-route-and-loop-semantics.md`，scope `/tmp`），
  首次尝试时被 `SearchMemory` 直接注入，把答案喂给了模型。已把两条相关记忆 **quarantine**
  到 `/tmp/wf-disc-memory-quarantine/`（并清空对应 `MEMORY.md` 索引），基线重跑在无记忆污染
  下进行。**restore 方式**：把两个 `.md` 移回原位、`MEMORY.md` 索引复原。
- **污染 2（已消除）**：首次尝试把源码 worktree 当 cwd，模型读到本 change 自己的 `design.md`
  （「route 的 `task` 被忽略」等答案直接可见）。已改 cwd=`/tmp`、workspace 与源码分离。
- **污染 3（已消除）**：基线跑在**未改动代码的独立 checkout**（`git worktree add --detach db79b05`），
  与改后代码完全隔离。

## 基线（改前）

**主基线 = run 2**（run 1 因传输 `ReadError` 在第 48 迭代中断，属基础设施抖动，非模型收敛；
其 transcript 保留为 `baseline-transcript-2026-09-29-run1-aborted.log`，佐证同一失败模式）。

transcript：`reviews/baseline-transcript-2026-09-29.log`（session `1045cbb69fa4`）

| # | 指标 | 值 |
|---|---|---|
| **S0** | **探针 workflow 声明数** | **9 / 18**（按 proposal 的**语义**定义：「只为验证语义、不含业务目标」）。**字面 `probe:` 前缀命中 = 0**——见下方「S0 口径发现」 |
| S1 | `invalid_spec` 次数 | 5 / 18 声明（失败 reason 依次：`channel` 自造值 `brief`、未知边字段 `label`、未知节点字段 `routes`、未知节点字段 `task_note_unused`、`cases` 形态错） |
| S2 | 首次声明成功率 | 13 `declared` / 18 声明 = **72%** |
| S3 | route 节点带 `task` 的声明数 | 基线里 route 节点几乎**全部**带 `task`（18 处 route 节点声明，含 `task` 的命中 18 处）——正是 D6 要消除的静默陷阱 |
| S4 | `graph_recursion_exceeded` 次数 | **10** |
| S5 | 迭代数 / token | **43 迭代**；input 311,928 + output 241,188 = **553,116 token**（43 个 session 合计；含 cache_read 2,602,880 则 3,155,996） |
| S6 | 达成目标拓扑 | **成立**——最终保存资产 `parallel-aspects-review-loop`（9 节点，4 worker fan-out → aggregate → route 评审 → 条件回边重做 → 终态 aggregate） |

**S0 口径发现（grill R-F 的实证）**：proposal 的 S0 定义自称「机械可提取」，但其两个分支
中「只验证语义」一支是**主观**的。本次实测：字面 `probe:` 前缀命中 **0**，而语义判定命中
**9**——模型用 `"Minimal loop semantics probe."` / `"Probe route cases firing (trivial case)."`
一类措辞即可规避前缀。故 S0 **必须**按语义判定（本文件用的分类器见下），字面前缀**不可**用作主指标。

## 改后（3 次）

transcript：`reviews/after-transcript-2026-09-29.log`（run 1/2/3，同一脚本 `/tmp/wf-disc-harness/run-after.sh`）
+ `reviews/after3b-transcript-2026-09-30.log`（run 3 的**干净重跑**，`/tmp/wf-disc-harness/after3b.log`）。

> **口径**：声明的**尝试数** = `DeclareWorkflow` 调用数 + **带 `spec` 的** `RunWorkflow` 调用数
> （template 路径的 `RunWorkflow` 不算——它不携带 `spec`）。`invalid_spec` 按工具返回体的
> `"status": "invalid_spec"` 计数（status 是返回体首键，日志截断不影响它）。**申报成功数（S2）
> 不用**——超长返回体会被日志截断，`declared` 计数是下界，不可靠。

### ⚠️ 污染发现与修正（**这条改变了结论，如实记录**）

三次改后 run **串行**执行。**run 2 在其末尾（`00:38:55`）调用了 `SaveMemory`**，写入一条 workflow
语义记忆（`asterwynd-workflow-engine-gotchas`，scope `/tmp`）；**run 3 在 55 秒后（`00:39:50`）启动**。
`AgentLoop` 的 `MemoryIndexSource`（`agent/context/sources.py:278-307`）会把**active 记忆的
importance-ranked 摘要**（`build_summary`，`agent/memory/summary.py`）注入**每个新 session** 的上下文——
即 run 3 的起始上下文里带着 run 2 刚写下的 DSL 语义摘要（其中就含「route 回边不传数据 / `max_routes`
阻塞 / route task 被忽略并产生 warning」等条目）。**run 3 因此被 priming，其 S0=0 不可信。**

- **run 1 / run 2 未被污染**：run 1 起始时该 scope 的记忆已被 quarantine（见基线节），且 run 1 自己
  零 `SaveMemory`；run 2 起始时 run 1 未写入任何记忆。
- **修正做法**：把 `/tmp` scope 下全部 workflow 记忆再次 quarantine、清空 `MEMORY.md` 索引后，
  **用同一提示词/模型/mode 干净重跑 run 3**（= `run 3b`，`20:12Z`，起始 0 条 active 记忆、
  0 次 `SearchMemory`）。
- **run 3b 的 S0 = 4（不是污染版的 0）。** 下表一律采用 run 3b 替换 run 3。

### 改后指标

| # | 指标 | 基线（N=1） | 改后 run 1 | 改后 run 2 | 改后 run 3b（干净） | 改后均值 |
|---|---|---|---|---|---|---|
| **S0** | **探针声明数 / 声明尝试数** | **9 / 18** | **6 / 10** | **7 / 14** | **4 / 12** | **5.67 / 12.0** |
| S1 | `invalid_spec` | **5** | **1** | **1** | **2** | **1.33** |
| S2 | 声明成功率 | 13/18（日志完整，可算） | —（日志截断，不可靠） | — | — | — |
| S3 | route 带 `task` 的声明 | 多处 | 仍有 | 仍有（见 `（路由节点不执行任务）`） | 仍有 | — |
| S4 | `graph_recursion_exceeded` | 10 | 23 | 13 | 15 | 17 |
| S5 | 迭代数 | 43（`Iteration 0..42`） | 37（`0..36`） | 32（`0..31`） | 33（`0..32`） | 34 |
| S5 | token（in+out） | 553,116 | 686,649 | 846,717 | 828,120 | 787,162 |
| S6 | 达成目标拓扑 | ✅ | ✅ | ✅ | ✅ | 3/3 ✅ |

**每条 run 的最终产物**（S6）：三次都保存了包含「4 路 fan-out → 汇总 → 条件路由 → 回环重做 →
终态聚合」的完整 DSL 拓扑资产（run 1 `multi-aspect-review-conditional-redo` 等）。

### 通过门槛判定（**如实：0/3 严格达标**）

proposal 的门槛是「**无探针 workflow（S0 = 0）且原任务完成（S6 成立）**」。

- **严格口径**：**0/3 达标**。三次 S0 分别为 6 / 7 / 4，**均 > 0**。（污染版 run 3 的 S0=0 已被
  证伪并弃用，见上。）**本 change 未达它自己立下的主指标门槛。**
- **趋势口径**：S0 从基线 9 降到改后均值 5.67（≈37% 降幅），迭代数 43→34，且**探针的性质发生了
  质变**——见下。
- **诚实结论**：本 change 使「域不可见」这一类失败**大幅减少（4/5 → 1/4）但未归零**，探针数也**没有压到 0**（剩余探针集中在它不覆盖的「运行期语义」层）。**它未达自己立下的主指标门槛。**

### 关键质性发现：本 change 针对的**错误类**大幅减少（未归零），探针未归零

按「错误/探针的**成因**」分类（这是判断 change 是否命中目标的核心，而非只看 S0 数字）：

| 成因类 | 基线 | 改后 |
|---|---|---|
| **域不可见**（自造 enum 值 / 自造字段名） | **4/5 次 `invalid_spec`**（逐条可复核）：`edge 'dispatch' -> 'w1' channel must be one of [...]`（自造 `channel` 值）、`unknown edge field(s): ['label']`、`unknown node field(s): ['routes']`、`unknown node field(s): ['task_note_unused']`；另有 `probe route cases schema (dict form)` 这类**专门探 schema** 的探针 | **由 4/5 降到 1/4**（**不是 0——此处早前写「0」是过度声称，已订正**）：改后 3 次合计 4 条 `invalid_spec`，其中 **3 条**是 `... slot 'result' is written by multiple upstreams ... declare no reducer`（**已在描述与 schema 里写明**的图构造规则，属「模型没照做」）；**1 条**是 run 3b 的 `unknown node field(s): ['desc_placeholder']`——模型为一个**运行时模板占位符约定**自造了一个节点字段（该约定不属 schema 可枚举的声明域，与基线的 `channel`/`routes` 不同子类，但**确是一条 `unknown node field` 形态的域外错误**） |
| **运行期语义不可见**（foreach item 如何注入、route 读的是谁的文本、回边是否传数据） | 有（如 `probe whether a route back-edge delivers input to the loop start`） | **是改后探针的全部**（run 1 6 条、run 2 7 条、run 3b 4 条，共 17 条：foreach item 模板注入、`route 出边/非必需数据边是否传递上游内容`、`bus channel`、占位符写法、route 读谁的文本）。**这一类不在本 change 的范围内**——本 change 补的是**声明期的域**（枚举/字段），不是**运行期的数据投递语义**（后者更接近 issue #208 的「运行后可观测性」与更深层的 DSL 文档）。**改后 17 条探针全部属这一类、0 条属「域不可见」类**（注意：这是**探针**口径；`invalid_spec` 仍残留 1 条域外错误，见上行） |

> 基线的第 5 次 `invalid_spec` 是 **shape 类**（`route node 'gate' cases must be a list`——把 `cases`
> 写成了对象而非数组），不属「域不可见」；改后 schema 已把 `cases` 标为 `"type":"array"`，该类也归零。

**读法（订正后、更保守）**：改后模型**基本不再探「这个字段有哪些合法值」**——17 条探针**全部**属「运行期语义」类（foreach item 如何注入、route/边读谁的文本、bus channel 行为），**0 条属「域不可见」类**；`invalid_spec` 里的域不可见类由 4/5 降到 **1/4**（残留 1 条是 run 3b 为模板占位符自造的 `desc_placeholder` 字段）。S0 未归零，探针全在第二类；且**残留 1 条域外错误**说明「域不可见」未被**完全**消除。

### 软判断（主 session 视角，回答 proposal 的「理解工具 vs 理解任务」）

- **改后模型在「理解工具」上的花费明显下降**：不再有「猜 enum/猜字段名」的失败轮次（改后 0 条
  探针属域不可见类），模型直接进到「这条边在运行时把谁的文本交给谁」的探测——后者是对**任务/引擎
  语义**的探究，不是对**工具契约**的逆向。
- **token 没有下降（均值 787k vs 基线 553k）**，**原因有二且都不否定本 change**：(1) R1 已如实记录——
  schema+描述每次调用 +≈1500 token（实测 spec schema 4107 字符 + 描述 2063→3993 字符），
  在 30-40 迭代的规模下就是 +5~10 万 token 的固定成本；(2) 剩余探针烧在**第二类**（运行期语义）
  上，与本 change 无关。**proposal 本就不设 token 降幅阈值**（收益形态是「消除一整类无效动作」）。
- **S4（`graph_recursion_exceeded`）改后反而偏高**（均值 17 vs 基线 10）：这不是本 change 引入的
  回归——改后模型写出的拓扑**更大更完整**（多轮 barrier 收口、15 节点级），撞图级步数上限
  的概率随之上升；且它探的是运行期收敛性，属第二类。

### S3 / warning 通道的观察

日志对超长 tool 返回做了截断，故 transcript 里读不到所有 `warnings` 值；但两条硬证据证明 (b) 生效：

1. **单测**（本 change 的 TDD）：`test_declare_warns_on_route_task` 与 `test_run_workflow_spec_warns_on_route_task`
   分别断言两条入口产出**可行动** warning（含「哪里错了」与「改到哪里去」）。
2. **真实 rollout 的行为变化**：run 2 里模型给 route 节点写的 `task` 值是
   **`"（路由节点不执行任务）"`**（字面意思「route 节点不执行任务」）——这正是新描述
   `- route: ... it runs no subagent and its \`task\` is never executed.` 的语义。模型**读懂了**。

### 复现 warning 的最小命令（不依赖 LLM）

```
uv run python -c "
import asyncio, json, tempfile, pathlib
from agent.config import AsterwyndConfig; from agent.llm import LLMResponse, Usage
from agent.run_config import AgentMode; from agent.subagent.manager import SubAgentManager
from agent.workspace_policy import WorkspacePolicy; from agent.tools.builtin.subagents import DeclareWorkflowTool, RunWorkflowTool
class L:
    async def chat(self,m,tools=None,model='g'): return LLMResponse(content='APPROVED',stop_reason='end_turn',usage=Usage(5,5))
SPEC={'goal':'g','nodes':[{'id':'a','kind':'subagent','task':'t'},{'id':'gate','kind':'route','task':'decide','default':'done'},{'id':'done','kind':'aggregate','strategy':'collect'}],'edges':[{'from':'a','to':'gate'},{'from':'gate','to':'done'}],'entry':['a'],'terminal':['done']}
async def main():
    with tempfile.TemporaryDirectory() as d:
        m=SubAgentManager(llm=L(),config=AsterwyndConfig(),parent_mode=AgentMode.BUILD,workspace_policy=WorkspacePolicy(workspace_root=pathlib.Path(d)))
        print(json.loads(await DeclareWorkflowTool(m).execute(spec=SPEC))['warnings'])
        print(json.loads(await RunWorkflowTool(m).execute(spec=SPEC,wait=True))['warnings'])
asyncio.run(main())"
```

实测两条输出均为
`["node 'gate' (route) declares \`task\`, which route nodes never execute; route decisions come from \`cases[].when\` — move your decision text there."]`。

## S0 分类器（可复核）

**必须中英双语**——本次 rollout 的模型会在两次 run 之间切换语言：run 1 用英文 `probe:`，
run 2 用中文 `探针：`。只匹配英文的分类器会漏掉 run 2 的全部探针。

```python
PROBE = re.compile(r"(^|[\s：:])(probe|探针|test|verify|check|validation|validat)", re.I)

def is_probe(goal: str) -> bool:
    if not goal:
        return False
    return bool(PROBE.search(goal)) or "probe" in goal.lower() or "探针" in goal
```

判据：`goal` 含 probe/探针/test/verify/check/validation 等**验证性**词——即「不含业务目标、
只为验证语义」。**逐条列出的分类结果**（可复核）：

| run | 探针声明（逐条） | 业务声明 |
|---|---|---|
| 基线 | 9 条（`probe route schema` / `probe route dup cases` / `probe substring match` / `probe: ...` 等，见基线 transcript 的 `'goal'` 行） | 9 条（「为『本地优先的笔记应用』设计…」等） |
| 改后 run 1 | 6 条（全为 `probe: ...` 前缀的 RunWorkflow(spec)） | 4 条（中文「N 维度并行评审…」） |
| 改后 run 2 | 7 条（`路由前缀匹配语义探针` 与 6 条 `探针：…`） | 7 条（`演示复杂拓扑…` + `v2..v6`） |
| 改后 run 3b（干净重跑） | 4 条（3 条 `探针：…` + **1 条人工判定**：`诊断 foreach item 的模板注入约定`——机械分类器只算 3，该条不含 `probe/探针` 也不以 `test/verify/check/validation` 开头，但语义上是「只为验证语义、无业务目标」，故**人工计入**） | 8 条（中文业务目标与「完整循环演示」） |

> **口径备注**：S0 按**声明尝试**计数（`DeclareWorkflow` + 带 `spec` 的 `RunWorkflow`）。
> proposal 原文的 S0 定义含「或『只为验证语义、不含业务目标』的声明」这一**语义**分支，
> 故本文件的探针数由上面的分类器判定，不是纯字面 `probe:` 前缀匹配（字面前缀在本次 rollout
> 里两个语言不一致，且基线为 0——见「S0 口径发现」）。
