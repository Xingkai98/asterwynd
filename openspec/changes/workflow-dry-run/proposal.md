# Proposal: DryRunWorkflow — 零 token 模拟执行 workflow，让模型直接看到数据投递语义

关联跟踪 issue：[#273](https://github.com/Xingkai98/asterwynd/issues/273)。同族先例（同一个工具面）：`workflow-tool-discoverability`（issue #248，已归档 2026-09-29）、`workflow-builtin-templates`（issue #246，已归档 2026-09-29）、`workflow-recursion-limit-default`（issue #262，已归档 2026-09-29）。

## Change Type

- primary: feature
- secondary:
  - subagent
  - tool-surface

## Why

### 问题：声明期 schema 解不了运行期语义

#248 把 `DeclareWorkflow` 的 `spec` 从裸 object 升级成派生 schema，让「域」（合法值集合）在动笔前可见。验收实测的结论是分裂的：

- **域不可见类**错误（自造 `channel` 值、自造字段名）从 **4/5 降到 1/4**；
- **主指标 S0（探针 workflow 数）没降到 0**——改后 3 次 rollout 是 **6/7/4**（基线 9），严格门槛 **0/3 达标**。

把改后残留的 **17 条探针逐条读一遍**，它们问的是同一类东西：

| 探针在问什么 | 举例 |
|---|---|
| foreach 的 item 是否注入、模板占位符怎么写 | 「`$item` 会进 subagent 的 prompt 吗」 |
| route 读的是**中间节点自身输出**还是上游输入 | 「`a→mid→gate`，gate 匹配的是 `mid` 的还是 `a` 的文本」 |
| route 重新求值时看 LATEST 还是累积旧输出 | 「第二轮循环，route 看到的是新的还是旧的」 |
| 回边是否携带上游文本 | 「`gate→producer` 这条回边，producer 第二轮收到新的输入了吗」 |
| bus channel 是否真发布到总线 | 「`channel:"bus"` 的边下游能看到吗」 |

**全是「拓扑 + 数据流」问题，没有一条是「真实 LLM 会说什么」。** 但模型没有便宜的地方问它们，于是**手写一次性 workflow 去实测**——它在 #248 基线里明确自述：*"let me run a cheap probe to validate loop-dispatch semantics before committing to the full topology"*。**它裸手做了我们本该内置的事。**

### 命题

> #248 之后，模型**仍然需要一个便宜的、非破坏性的地方**去问「这张图的线怎么接、文本怎么流」。
> 每次都要起一张真图、烧真 token、撞真超限——代价 398,590 token（498% 预算）。

`DryRunWorkflow` 就是那个地方：**对着它真正想用的那张图，零 token 跑一遍，看数据往哪流。**

## What Changes

新增一个只读工具 `DryRunWorkflow`（`agent/tools/builtin/subagents.py`），对一张 spec 做**模拟执行**并返回**数据流报告**：

1. **模拟执行**：用一次性 manager + 假 LLM 真正跑一遍调度器（同一套 `_drive`/门控/reducer/route 匹配），**零真实 LLM 调用、零落盘、零注册表污染**（机制见 design D4，已实测）。
2. **返回数据流**（字段名即「那 17 条探针在问的东西」）：
   - `received`：**每个节点实际收到的 prompt 文本**（foreach item 注入、上游 bounded 投递都在这里现形）；
   - `produced`：每个节点的产出（默认是「回显式占位」，可用 `script` 覆盖）；
   - `route.input_seen` / `matched` / `walked_to` / `used_default`：route 到底读了谁的文本、命中哪个 case、没命中时走没走 default；
   - `edges`：每条边的 `channel` 与 `control`（route 出边是控制边）——回答「回边带不带数据」；
   - `nodes`：节点终态（`completed` / `skipped` / `blocked`）——回答「这条分支会不会跑到」。
3. **可选 `script`（what-if 注入）**：调用方可以给某个节点指定「假装它输出这个」，于是能问「**如果 critic 说 `GAPS`，图往哪走？**」——把工具从「happy-path 草图」升级成「任意 what-if 推演」。
4. **报告是有界的**：所有文本按 `max_report_chars` 截断，避免大图把父上下文打爆（与既有 `parent_envelope` bounded 纪律同口径）。
5. **如实声明边界**：返回体与工具描述都写明这是**模拟**——它回答**拓扑与数据流**，**不回答**「真实模型会不会真的输出 `APPROVED`」。

**不变**：调度器全部运行语义、`WorkflowSpec` 的数据结构、既有工具（`DeclareWorkflow`/`StartWorkflow`/`RunWorkflow`/资产四件套）的行为与返回体、`parent_envelope` 投影、资产 schema。**不修改 `scheduler.py` 的执行路径**（模拟复用既有 `run()`，隔离靠**喂给它的 manager/LLM/store**——见 design D4）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：
  - **ADDED** 新 Requirement「工作流可零成本模拟执行以暴露数据投递语义」——系统 SHALL 提供只读的 `DryRunWorkflow`，对给定 spec 做**不调用真实 LLM、不产生持久副作用**的模拟执行，SHALL 返回每个节点的 `received`/`produced`、route 的判定输入与命中、每条边的 `channel`/`control` 与节点终态，SHALL 允许调用方 `script` 指定节点输出以推演分支，SHALL 对有界性（截断）与模拟边界（不代表真实模型输出）作出显式声明。
  - **MODIFIED** 既有 Requirement「DeclareWorkflow 描述暴露循环契约」——描述中 SHALL 增加指向 `DryRunWorkflow` 的**可发现性引导**（把「不确定语义时先 dry run」写进声明入口，而不是等模型自己想起来有这个工具）。**注**：`DeclareWorkflow` 的描述实测 **3993 字符**（守卫上界 6000，`research/` 的实测输出），**尚有约 2000 字符余量**——所以加一句引导语是可行的；但主引导仍建议放 `DryRunWorkflow` 自身的 description（见 design D10 / Open Question Q4）。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

沿用 #248 的验收 harness——**同一提示词、同一模型（`deepseek-v4-flash`）、同 `--mode bypass`，N=3**。主指标不变：

| # | 指标 | 主/辅 |
|---|---|---|
| **S0** | **探针 workflow 数**（「只为验证语义、不含业务目标」的一次性声明） | **主指标** |
| S1 | `invalid_spec` 次数及 reason | 辅 |
| S2 | 首次声明成功率 | 辅 |
| S4 | `graph_recursion_exceeded` / `blocked` 节点数 | 辅 |
| S5 | 迭代数、token 消耗 | 辅 |
| S6 | 达成目标拓扑 | 端到端有效性 |
| **S7** | **`DryRunWorkflow` 调用次数**（本 change 新增） | **对照** |
| **S8** | **`DryRunWorkflow` 是否被用来替代探针**（读 transcript 判断 dry run 的 `goal` 是否就是探针想问的那个语义） | **对照** |

**通过门槛**：**无探针 workflow（S0 = 0）且原任务完成（S6 成立）**。

**负面检查（必须做）**：dry run 是否变成**新的无限试探循环**——S7 调用次数是否有上界行为（design D7 给界；验收要看它有没有被撞到）。

**跑之前必须清空全局资产库**（`~/.asterwynd/projects/<hash>/workflow-assets/`），**且每次 rollout 之间 quarantine 记忆**（`MemoryIndexSource` 是 always-loaded，上一次 `SaveMemory` 会注入下一次起始上下文——#248 实测踩过，会让 S0 假达标）。

**证据归属**：rollout 证据由实现方产出并落盘（`reviews/acceptance-evidence.md` + 原始 transcript），`/review-loop` 的独立 reviewer 核验可信度（数字真实性、harness 是否被改动、结论是否 cherry-pick）。**reviewer 不自己跑 rollout**。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据「引入新工具（新能力面）」与「走 grill 的非平凡 change」。本 change 新增一个**模型可见的工具**，其契约、可信边界表述与「零成本模拟」形态都是**需要业界依据的形态决策**，不是成熟模式的局部应用。**不判 `light`/`exempt` 的理由**：`exempt` 仅适用 docs-only / 无新增能力面的 bugfix / 上游决策锁定，本 change 三者皆不满足；「新增工具」本身就是新增能力面。
- research questions:
  - **RQ1**：业界 agent 框架有没有「对编排图做干跑 / 模拟 / 只校验不执行」的机制？形态是什么？（须区分静态 lint ≠ 数据流模拟；真跑一次 ≠ 零成本模拟）
  - **RQ2**：有没有框架允许**指定某节点的预期输出**然后看它往哪流（what-if 注入）？接口长什么样？
  - **RQ3**：对模拟/干跑结果，业界怎么表达**可信边界**？有没有把「这是模拟，不代表真实模型会这么说」写进工具描述或返回体的先例？
  - **RQ4**：agent 框架里「零 token 预演」的典型做法是假 LLM/mock provider、只跑控制流、还是别的？实现位置在哪？
  - **RQ5**：这类工具会不会被滥用来无限试探？业界有没有对「模拟调用次数」设界的先例？
- findings:
  1. **RQ1 结论：本地 6 个参考仓库里，没有「对编排图做零成本数据流模拟」的现成机制。** 最接近的是两类，与 `DryRunWorkflow` 有明确区别：**(a) 静态预检**——`deepseek-harness` 的 workflow 引擎把「校验」与「执行」显式分开（`deepseek-harness/packages/workflow/workflow-ptc/src/index.ts:126`：`start() validates the script up front (meta + a host-side body parse)`），但**校验只做 meta 形状 + body 能否 parse，不回放数据流**（`:62` 注释 `// Parse only — the script object is discarded, nothing executes.`）；**(b) 测试期假 LLM**——能跑控制流，但**属测试基建，不是模型可调用的工具**。权重最高的 `pi` 与 `deepseek-harness` 均无同款。
  2. **RQ1 补充：各仓库的 `dry-run` 全是「副作用预演」，语义不同但命名可借鉴。** `codex` 的 imagegen dry-run 最接近「零调用」——`codex/codex-rs/skills/src/assets/samples/imagegen/references/cli.md:27`：`Dry-run (no API call; no network required; does not require the openai package)`；`opencode/packages/web/src/content/docs/cli.mdx:629`：`Show what would be removed without removing`；`zcode` 的 `dryRun` 用于插件 marketplace 的 install/configure。**共同语义 = 「不产生副作用地预演」，与 `DryRunWorkflow` 的命名意图一致。**
  3. **RQ4 结论：「假 provider 回显输入」是业界成熟标配，本 change 的实现形态与之一致。** `deepseek-harness/packages/subagent/subagent-dsh-sdk/tests/fixtures/loader/mock-delegating-llm.ts` 的 `MockDelegatingAdapter.stream()` **直接把上一轮 tool result 文本回显拼进回复、不发起真实调用**——与 design D3 的「假 LLM 回显 prompt」几乎同构。同类还有 `pi` 的 `fauxProvider`（`pi/packages/ai/src/providers/faux.ts`）、`codex` 的 wiremock 回放（`codex-rs/app-server/tests/common/mock_model_server.rs:13`）、`kimi-code` 的 scripted-provider seam、`opencode` 的真 HTTP 假 LLM。**结论：本 change 是「把测试基建产品化为 agent 工具」，不是自创造轮子。**
  4. **RQ2 结论：本地没有「按节点指定输出 + 返回流向」的同款接口，最接近的是 `pi` 的顺序响应队列。** `pi/packages/ai/src/providers/faux.ts:140` 的 `setResponses(responses: FauxResponseStep[])`，README（`pi/packages/ai/README.md:1469`）说明 `Responses are consumed from a queue in request start order`——**按调用顺序排队，不是按节点 id 指定**，且没有「看它流向哪个后继节点」的返回体。`deepseek` 的 record/replay 快照（`vitest.snapshot.config.ts:26`）回放的是整条 request/transcript，**不是图节点**。**⇒ design D3 的 `script`（按节点 id 注入）是无先例的设计，必须自证其必要性与边界。**
  5. **RQ3 结论：没有「面向模型的模拟工具」的描述先例，但 dry-run 免责措辞有直接样板。** `codex` 的 `Dry-run (no API call; no network required; ...)` 与 `deepseek` 大量测试注释 `No model call is involved` 是间接依据；Temporal 侧有「模拟不得触达生产副作用」的原文（**二手**，来自 WebSearch 摘要）。**⇒ design D6 的边界声明应套用「no API call」这类**断言式措辞**，而不是散文式的「请注意这只是模拟」。**
  6. **RQ5 结论：有教科书式先例——把上限写成「防失控」并在越界错误里说明，而非静默截断。** `deepseek-harness/packages/workflow/workflow-ptc/src/index.ts:37`：`Total agent() calls one run may start — the runaway-loop backstop (default 1000)`；越界文案（`runtime.ts:170`）：`this run reached its total agent cap (...) — a runaway-loop backstop; raise the applicable maxTotalAgents limit if the scale is intentional`。**⇒ design D7 的调用上限应仿此形态：设界 + 可读原因 + 给出正当提高路径。**（注：未见对「模拟调用次数」单独设界的先例——业界把界设在真实调用上；本 change 设在 `DryRunWorkflow` 调用上，是同构迁移。）
  7. **本地参考仓库可用性**：`/home/shared/agent-study/reference-repos/` 下 6 个仓库（`codex`/`deepseek-harness`/`kimi-code`/`opencode`/`pi`/`zcode`）**全部可用**，与 `.dev/reference-repos.txt` 列出的 6 条一致，findings 全部以源码 `file:line` 为证。**WebSearch 可用**（LangGraph dry-run / Temporal replay 两轮检索成功）；**WebFetch 未使用**，故 RQ3 的 Temporal 原文与 RQ4(b) 的 LangGraph 确定性 stand-in node **属二手证据**，已在 findings 中标注。`.dev/reference-repos.txt` 在本 worktree 不存在（不提交，属正常），已改用实测目录。
- design impact: 见 design **D3**（`script` 无先例 ⇒ 必须论证必要性并把「不传 script 时的默认行为」定义清楚）、**D6**（边界声明改为断言式措辞）、**D7**（仿 deepseek 的 runaway-loop backstop 设调用上限）、**D8**（新增：把「测试基建产品化为模型工具」的无先例风险单列一节）。**调研对设计的主要影响**：RQ3 + RQ5 各驱动一条硬性设计决策（边界表述、调用设界）；RQ1/RQ2 的「未找到先例」把本 change 定位为**创新点**，据此要求在 design 中显式处理「模型把模拟当真实执行」这一无模板可抄的风险。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（Workflow DSL 的工具面）。
- **代码**:
  - `agent/tools/builtin/subagents.py` — 新增 `DryRunWorkflowTool`（`@tool_parameters` + `read_only = True`，权限沿用 `SUBAGENT_CONTROL_PERMISSION`）；新增模拟驱动函数与报告构造；新增 `_DryRunLLM`（假 LLM）；新增 NullStore。**不改任何既有工具的行为**。
  - `agent/loop.py` — 在既有工具注册块（`:398-425`）加一行注册。**不改注册顺序语义、不改 mode 门禁**（`read_only`，与 `DeclareWorkflow` 同档，`max_depth` 撤工具时**不**撤它——它不 spawn）。
  - `agent/subagent/manager.py` — **预期不改**。若 D4 发现需要 `graph_sink` 之外的隔离点，先回写 Impact Analysis。
  - `agent/subagent/scheduler.py` — **预期不改**（模拟复用 `run()`）。**这是本 change 最重要的不变量**：若实现过程中发现必须改 `scheduler.py` 才能隔离，SHALL 先停轮回写本 Impact Analysis 与 design，因为「不改调度器」是 D4 的核心承诺。
- **测试**:
  - **必须新增**：`tests/agent/subagent/test_workflow_dry_run.py`
    - 隔离性：dry run 后**真实 workspace 零新增文件**、**真实 manager 的 `_workflows`/`_workflow_stores` 为空**、`graph_sink` 未被调用；
    - 数据流正确性：`received` 里能读出 foreach item 注入、route 的 `input_seen` 等于**上游节点自身输出**（拿实测钉死的语义当断言——注意 D-发现：上游是 aggregate 时会回退到槽值，须分别断言两种形态）；
    - `script` 注入：给 critic 脚本 `GAPS`，断言 `gate.walked_to` 走回边、且回边重跑节点的 `received`（验证「回边不带文本」这一反直觉语义）；
    - 有界性：超长产出被截断到 `max_report_chars`；
    - 边界声明：返回体含「这是模拟」的显式措辞；
    - 零 token：断言模拟期间**真实 `manager.llm` 的 `chat` 调用数为 0**（变异验证：把假 LLM 换回真 LLM，测试必须变红）。
  - **必须新增**：工具面 parity/描述断言（沿用 `test_workflow_tool_discoverability.py` 范式）——`DryRunWorkflow` 的 `spec` 参数用**同一份** `_workflow_spec_schema()` 派生（与 `DeclareWorkflow`/`RunWorkflow` 一致，纳入既有 schema↔常量 parity 与清单守卫）。
  - **必须回归**：`_SPAWN_TOOL_NAMES` 不含 `DryRunWorkflow`（它不 spawn），既有工具数量/名字断言（`test_workflow_tools.py`）需同步新增而非修改。
- **文档**:
  - `openspec/specs/multi-agent-collaboration/spec.md`（current spec 同步，受保护路径）——ADDED 1 + MODIFIED 1。
  - `docs/openspec-change-backlog.md`（本 change 入队；受保护路径）。
  - `README.md` / `README_EN.md` / `docs/architecture.md`：关键词扫描（`DryRunWorkflow` / `DeclareWorkflow`）确认工具清单段落是否有事实变化。
  - `docs/interview-script/`：本 change 是「可发现性从静态 schema 走向运行期模拟」的完整案例，**建议**候选（建议性，不设门禁）。
- **流程（process）**: 触及受保护路径，需 `current_spec_synced` / `backlog_updated` 结构化事件 + grill 证据 + building review；实现须在独立 worktree、`workflow-dry-run/2026-09-30` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**。
- **与既有 change 的边界（避免重叠）**：
  - **与 `workflow-tool-discoverability`（#248）**：该 change 解决**声明期域可见性**（schema 枚举），本 change 解决**运行期语义可发现性**。两者是**互补而非重叠**——#248 的验收实测已证明后者 schema 吃不掉（改后探针 100% 属运行期语义）。
  - **与 #269（运行期语义可发现性）**：**本 change 可能覆盖它的大部分**。若 dry run 能让模型自己看到语义，则 #269 的「写进描述」与「运行后可观测」两个方向可能都不必做。**用户已拍板（2026-09-30）：本 change 先做，#269 做完再评估。**
  - **与 #268（只读 `ValidateWorkflow`）**：**本 change 可能让它重新定位**。静态校验的价值在 #248 后已被 schema 吃掉大半；剩下的运行期问题恰是 dry run 的地盘。**用户已拍板：做完本 change 再评估 #268。**
  - **与 #208（route 走 default 时看不到判定依据）**：dry run 的 `route_decisions`（`input_seen`/`matched`/`used_default`）**天然覆盖**「为什么走 default」。但 #208 是**运行后**的用户侧可观测性，本 change 是**声明前**的模型侧可预演性——两者仍可独立推进。
  - **与 `benchmark-workflow-replay`（C5，已归档）**：C5 是**记录/重放**（replay 需要真实 record 过的 run），本 change 是**零记录模拟**（不需要任何历史 run）。基础设施可复用（假 LLM 形态、`StaticLLM` 范式），但路径不同——**本 change 不依赖 C5 的落盘记录**。
- **代价权衡（如实记录）**: 新增工具会**增加每次 API 调用的 input token**（工具描述 + schema 每轮都发）。但收益形态是「**消除一整类无效动作**」——一次探针循环的代价是 398,590 token，而 dry run 是 0 token、亚秒级（实测大图 0.06–0.7s）。**不设 token 降幅门槛**（#248 教训：收益不是线性省 token）。
- **可回滚性**: 全部改动集中在新增工具 + 一行注册；回滚 = revert 该 commit，无数据迁移、无资产指纹变化（`spec_hash` 由 `WorkflowSpec.to_dict()` 计算，与工具无关）。

## Non-Goals（摘要）

- **不改调度语义**。模拟复用既有 `run()`；若需改 `scheduler.py` 才能隔离，先回写 Impact Analysis（见上）。
- **不替代真实运行**。dry run 不产生可用的 workflow 结果、不落盘、不能被 `GetWorkflow` 查询——它是「看一眼」，不是「跑一遍」。
- **不引入 `ValidateWorkflow`**（#268 的范畴）。
- **不做表达式求值**。`matches_route` 的「不做表达式求值」是安全姿态，模拟沿用同一匹配语义。
- **不把 dry run 注册进 workflow 注册表**，也就不进 `ListWorkflowAssets`/`GetWorkflow` 的任何可见面。
