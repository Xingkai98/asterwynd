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
| workspace | `/tmp/wf-disc-baseline2`（基线）/ `/tmp/wf-disc-after-{1,2,3}`（改后） |
| 资产库 | 每次跑前 `rm -rf ~/.asterwynd/projects/*/workflow-assets/` |
| 源码 | 基线 = 干净 checkout `db79b05`（`/tmp/wf-disc-src-pristine`）；改后 = 本 worktree |

### 隔离修正（诚实记录）

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

transcript：`reviews/after-transcript-2026-09-29.log`（三次串行，同一脚本 `/tmp/wf-disc-harness/run-after.sh`）

| # | 指标 | 基线（N=1） | 改后 run 1 | 改后 run 2 | 改后 run 3 | 改后均值 |
|---|---|---|---|---|---|---|
| **S0** | **探针声明数** | **9** | **5** | **7** | **0** | **4.0** |
| S1 | `invalid_spec` | 5 | 2 | 2 | 0 | 1.3 |
| S2 | 声明成功率 | 13/18 | — | — | — | — |
| S3 | route 带 `task` 的声明 | 多处 | 仍有（run 2 见 `（路由节点不执行任务）`） | 仍有 | 仍有 | — |
| S4 | `graph_recursion_exceeded` | 10 | 23 | 13 | 6 | 14 |
| S5 | 迭代数 | 43 | 37 | 32 | 20 | 29.7 |
| S5 | token（in+out） | 553,116 | 686,649 | 846,717 | 175,183 | 569,516 |
| S6 | 达成目标拓扑 | ✅ | ✅ | ✅ | ✅ | 3/3 ✅ |

**每条 run 的最终产物**（S6）：run 1 `multi-aspect-review-conditional-redo`、run 2 同族 DSL 资产、
run 3 DSL 资产——三次都保存了包含「4 路 fan-out → 汇总 → 条件路由 → 回环重做 → 终态聚合」的
完整拓扑。

### 通过门槛判定（**如实：未严格达标**）

proposal 的门槛是「**无探针 workflow（S0 = 0）且原任务完成（S6 成立）**」。

- **严格口径**：**仅 run 3（1/3）达标**（S0=0 且 S6 成立）。run 1（S0=5）、run 2（S0=7）**未达标**。
- **趋势口径**：S0 从基线的 9 降到改后均值 4.0（≥50% 降幅），迭代数 43→30，且**探针的性质发生了
  质变**——见下。

### 关键质性发现：本 change 针对的**错误类**被消除，但探针未归零

按「错误/探针的**成因**」分类（这是判断 change 是否命中目标的核心，而非只看 S0 数字）：

| 成因类 | 基线 | 改后 |
|---|---|---|
| **域不可见**（自造 enum 值 / 自造字段名） | **4/5 次 `invalid_spec`**：`channel must be one of [...]`、`unknown edge field ['label']`、`unknown node field ['routes']`、`unknown node field ['task_note_unused']`；另有 `probe route cases schema (dict form)` 这类**专门探 schema** 的探针 | **0 次**。改后 2 次 `invalid_spec` **全部**是 `reducer` 未声明（一条**已在描述与 schema 里写明**的图构造规则，属「模型没照做」而非「模型看不到域」） |
| **运行期语义不可见**（foreach item 如何注入、route 读的是谁的文本、回边是否传数据） | 有（如 `probe whether a route back-edge delivers input to the loop start`） | **仍是探针的主体**（run 1：foreach item delivery ×3；run 2：route 读到谁的文本 ×4）。**这一类不在本 change 的范围内**——本 change 补的是**声明期的域**（枚举/字段），不是**运行期的数据投递语义**（后者更接近 issue #208 的「运行后可观测性」与更深层的 DSL 文档） |

**读法**：改后模型**不再探「这个字段有哪些合法值」**（schema 已可见），转而探**「这条边在运行时
到底把谁的文本交给了谁」**——后者是另一个问题域。S0 未归零，主要来自这第二类。

### 软判断（主 session 视角，回答 proposal 的「理解工具 vs 理解任务」）

- **改后模型在「理解工具」上的花费明显下降**：不再有「猜 enum/猜字段名」的失败轮次，run 3 甚至
  一次探针都没有、20 迭代直接写出正确拓扑。
- **token 没有下降（均值持平略升）**，**原因有二且都不否定本 change**：(1) R1 已如实记录——
  schema+描述每次调用 +≈1500 token（实测 spec schema 4107 字符 + 描述 2063→3993 字符），
  在 30-40 迭代的规模下就是 +5~10 万 token 的固定成本；(2) 剩余探针烧在**第二类**（运行期语义）
  上，与本 change 无关。**proposal 本就不设 token 降幅阈值**（收益形态是「消除一整类无效动作」）。
- **S4（`graph_recursion_exceeded`）改后反而偏高**（均值 14 vs 基线 10）：这不是本 change 引入的
  回归——改后模型写出的拓扑**更大更完整**（run 1 是 15 节点、多轮 barrier 收口），撞图级步数上限
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

```python
PROBE_RE = re.compile(r"^\s*(probe|test|verify|check|validation|minimal loop|loop validation|deterministic)", re.I)
def is_probe(goal):
    gl = goal.lower()
    return bool(PROBE_RE.match(goal)) or "probe" in gl or ("validation" in gl and len(goal) < 80)
```

判据：`goal` 以 probe/test/verify/check/validation 等**验证性**动词开头，或含 `probe`，或短句
且含 `validation`——即「不含业务目标、只为验证语义」。
