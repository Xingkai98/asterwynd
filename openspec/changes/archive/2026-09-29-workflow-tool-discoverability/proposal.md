# Proposal: Workflow 工具面可发现性（channel 枚举 / cases 语义 / route task 静默失效）

关联跟踪 issue：[#248](https://github.com/Xingkai98/asterwynd/issues/248)。同族先例（改同一个工具面）：`workflow-builtin-templates`（issue #246，已归档 2026-09-29）、`workflow-recursion-limit-default`（issue #262，已归档 2026-09-29）。相邻 issue（同属「route 决策不可解释」线，独立推进）：#208（运行**后**的用户侧可观测性）、#120（工具描述质量的**度量**）。

## Change Type

- primary: feature
- secondary:
  - subagent
  - tool-surface

## Why

`DeclareWorkflow` 是模型进入 workflow DSL 的唯一入口，但它的**参数 schema 是一个裸的 `{"type": "object"}`**（`agent/tools/builtin/subagents.py:546-549`）——DSL 的全部嵌套结构、全部合法枚举值只存在于 Python 源码常量里（`agent/subagent/workflow.py:30-80`）。模型看不到域，只能猜；猜错被拒；于是**写探针 workflow 去试**。

这不是推测。用 issue #248 的原始提示词在最新 master 上跑真实 agent（`deepseek-v4-flash`，`--mode bypass`）的实测：

| 指标 | 值 |
|---|---|
| `DeclareWorkflow` 调用 | 19 |
| `StartWorkflow` 调用 | 14 |
| `"probe:"` 开头的一次性探针 workflow | **20** |
| `invalid_spec` | 4 |
| `graph_recursion_exceeded` | 15 |
| 迭代数 | 54（手动 kill，仍在继续） |
| token 消耗 | 398,590 / 80,000 预算 = **498%** |

模型自述原话：**"let me run a cheap probe to validate loop-dispatch semantics before committing to the full topology"** —— 它把我们的 DSL 当成了需要实验才能理解的外部系统。

**关键更正（证据口径）**：模型**最终确实完成了任务**并保存了资产（`~/.asterwynd/projects/e9671acd244849c5/workflow-assets/fanout-review-loop.json`，10 节点图，`entry: ["w1","w2","w3","w4","rework"]` —— 把 loop body 也列进 entry，正是它探针得出的结论，反直觉但正确）。所以本 change 的命题**不是「模型做不到」**，而是：

> **模型做得到，但必须先当黑箱逆向工程 20 次。**

由此，验收标准也不是「能不能完成」，而是「**要花多少精力去理解工具**」（见下文「验收」节）。

### 三种错法 + 一种静默错（决定改法，不是加更多示例）

模型从来没写错顶层结构（`goal`/`nodes`/`edges`/`entry`/`terminal` 一次就对）——**因为那些字段的形态在描述里**。它栽的是 `strategy`/`channel`——**因为这两个字段的合法值压根不在描述里**。逐条读码 + 实测归类：

| # | 错法 | 具体证据 | 正确的补法 |
|---|---|---|---|
| 1 | **照抄了错的示例** | 描述 `:530-531` 的示例写 `gate->join (control)`、`gate->producer (control back-edge)`，而 `control` **不是** `CHANNELS` 的成员（`workflow.py:35`），声明期直接拒绝 | **删/改示例**，不是加示例 |
| 2 | **从邻居字段借值** | `strategy: "concat"` —— `concat` 是 `REDUCERS` 的取值，描述 `:511` 刚枚举过；`strategy` 自己的合法值（`llm`/`collect`）描述里只出现过 `"collect"` | **把该字段的合法值枚举进 schema** |
| 3 | **不知道字段存在** | `join` 作为**字段名**在描述里命中 **0 次**（只作为节点 id `join(aggregate, ...)` 出现在示例里） | **补字段清单（按 kind 分流）** |
| 4 | **静默错，不推高错误计数** | 模型自造 `channel` 值（`findings`/`round_summary`/`redo`），被拒后的"修法"是把 `channel` 字段**整个省掉** → 静默落到默认值 `summary`（`workflow.py:659`）。**这种错不报错** | 同 2：枚举进 schema，让它一开始就写对 |

### 机制事实（已复核，不需要再验）

- 工具 `description` 与 `parameters`（= Anthropic 的 `input_schema`）**每次 API 调用都原样发给模型**（`agent/tools/base.py:53-61` → `agent/anthropic_llm.py:295,746-753`；`agent/loop.py:732,1192`）。`parameters` 是**逐字透传**到 `input_schema` 的（`_convert_tool` 只改名、不校验），嵌套 JSON Schema（`properties`/`items`/`enum`）**完全支持**——加 schema 是纯增量，无管线改造。
- `max_routes`（`scheduler.py:1672`）与 `recursion_limit`（`scheduler.py:995`）是**两条独立代码路径**。#262 把 `recursion_limit` 25→100 **救不了**本 issue 场景：实测 15 次超限的 `reason` 是 `max_routes`。
- 四个内置模板（`orchestrator-worker`/`peer-review`/`hierarchical`/`bidding`）**无一覆盖**「fan-out + 回边」组合：`peer-review` 有 route + 回边但**零 fan-out**（`patterns.py:195-230`），其余三个有 fan-out 但零回边。故本 issue 的摩擦**模板层吃不掉**。
- 描述当前长度 2504 字符。关键字命中数：`channel` 1（且是错的用法）、`result_ref`/`summary`/`artifact`/`bus` **各 0**、`case`/`cases` **各 0**、`join`（字段名）**0**、`items`/`source` **各 0**、`control` **4**（全是错示例）。

## What Changes

工具面（`agent/tools/builtin/subagents.py` + `agent/subagent/workflow.py`）的行为与内容变更，**不改调度语义**：

1. **P0 纠错**：描述里字符串 `control` 共 4 处（`:518,530,531,536`）——其中 `:530,531,536` 是**非法示例**（`control` 出现在 channel 该在的位置），`:518` 是「control edges」术语。**全部改写为不出现 `control` token 的表述**，示例改用合法的 `summary`；并把「**route 出边不 gate，与 `channel` 取值无关**」讲清（gate 语义由「发起节点是 route」决定，`WorkflowSpec.is_control_edge`，`workflow.py:243-245`——与 channel 正交）。**新发现的错误来源**：`control` 确实是系统里的真实取值，但属**另一层另一个字段**——可观测层的 `edge.kind ∈ {control, data}`（`scheduler.py:2855`）。两层词汇写进了同一位置，故修法必须把边界讲清（见 design D3）。
2. **P0 补语义**：把 `cases` 的匹配规则写进描述——**行首匹配（`startswith`，非子串）+ 声明顺序 first-match-wins**（`scheduler.py:323-338`），并给出「具体模式须排在宽泛模式前」的正例（`"GAPS: none"` 必须排在 `"GAPS"` 之前）。
3. **P1 结构化 schema**：把 `spec` 从裸 `{"type":"object"}` 升级为**带嵌套 `properties` 与 `enum` 的 schema**，使 `kind` / `channel` / `reducer` / `strategy` / `join` / `mode` 的合法值**在动笔前就可见**。枚举**从源码常量派生**（`NODE_KINDS` / `CHANNELS` / `REDUCERS` / `AGGREGATE_STRATEGIES` / `JOIN_SEMANTICS` + `mode` 三元组），不手写。
4. **P1 补字段适用性**：按节点 `kind` 给出字段适用表（`join`/`strategy`/`deadline_s` 只属 `aggregate`；`cases`/`default`/`max_routes` 只属 `route`；`items`/`source`/`source_field`/`max_items` 只属 `foreach`），并说明 `when` 的两种形态（字面标签 / `$ref:<node>:<slot>`，`workflow.py:88-107`）。
5. **P1 消静默**：route 节点的 `task` 被静默忽略（`_execute_route`，`scheduler.py:1866-1909` 不读 `node.task`；`_NODE_FIELDS` 对所有 kind 共用并集，`workflow.py:56-78`）——按 (a) 声明期拒绝 / (b) 返回 `warnings` / (c) 仅描述说明 三选一处理，**本 proposal 不预设结论**，见 design D6 / Open Question Q1。
6. **P1 修错误信息**（新发现，见 design D7）：字段用在不适用的 kind 上时，若值恰好合法则**静默丢弃**；若值非法则**错误信息指错 kind**（实测 `{"kind":"route","strategy":"concat"}` → `aggregate node 'g' strategy must be one of ['llm','collect']`——报的是 `aggregate`，但节点是 `route`）。

**不变**：调度器全部运行语义（门控、reducer、`max_routes`/`recursion_limit` 计数、环可启动性校验）、四个内置模板的编译产出、`WorkflowSpec` 的数据结构、`parent_envelope` 投影、资产 schema。**不新增工具**（`ValidateWorkflow` 列为 Non-Goal，见 design D10 / Open Question Q4）。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `multi-agent-collaboration`：
  - **MODIFIED** 既有 Requirement「DeclareWorkflow 描述暴露循环契约」——把覆盖范围从「循环契约」扩到「**工具面可发现性契约**」：描述 SHALL 覆盖环的可启动性与回边方向（不变），**并** SHALL 覆盖 `cases` 匹配语义、`channel` 与门控的正交关系、按 kind 的字段适用性。
  - **ADDED** 新 Requirement「Workflow spec schema 的封闭取值从单一来源派生」——`DeclareWorkflow`/`RunWorkflow` 的 `spec` 参数 SHALL 以嵌套 schema 暴露 `kind`/`channel`/`reducer`/`strategy`/`join`/`mode` 的合法值，且这些枚举 SHALL 从 `agent/subagent/workflow.py` 的源码常量派生（SHALL NOT 手写第二份），SHALL 有测试机械锁定 schema 与常量的相等性。

## 验收（本 change 的验收口径，**只进 proposal、不进 spec**）

spec 该写的是 **DSL 语义规则**（什么图合法、字段怎么组合），不是「模型应该表现成什么样」。模型表现是**验收手段**，归属本 proposal。

### 这不是客观硬指标

用户明确拍板：这类 change 的验收标准是「**跑真实 LLM，看它能不能低成本理解并直接用对**」，由主 session 主观判断 + 监督，不存在「探针数 ≤ N」这种可以脱离语境成立的客观阈值。

### 硬前件（客观，N=3 次）

固定一条提示词（含 **fan-out + 汇总 + 条件判断 + 回边 + 聚合**），跑 3 次真实 LLM（与基线同模型、同 `--mode bypass`），每次从 session transcript + workflow envelope 机械提取：

| # | 指标 | 提取方式 | 主/辅 |
|---|---|---|---|
| **S0** | **探针 workflow 数**（`goal` 以 `probe:` 开头，或"只为验证语义、不含业务目标"的声明） | 扫 `DeclareWorkflow` 调用 | **主指标** |
| S1 | `invalid_spec` 次数及 reason | `DeclareWorkflow` 返回 `status` | 辅 |
| S2 | 首次声明成功率 = 首次即 `declared` 的调用数 / 总调用 | 同上 | 辅 |
| S3 | route 节点带 `task` 的声明数 | 扫 spec | 辅（对 D6） |
| S4 | `graph_recursion_exceeded` / `blocked` 节点数 | envelope | 辅（对 D4） |
| S5 | 迭代数、token 消耗 | session 记账 | 辅 |
| S6 | 达成目标拓扑（fan-out / fan-in / back-edge 各自存在） | 扫边集 | 端到端有效性 |

**通过门槛**：**无探针 workflow（S0 = 0）且原任务完成（S6 成立）**。

**跑之前必须清空全局资产库**（`~/.asterwynd/projects/<hash>/workflow-assets/`）。理由：`ListWorkflowAssets` 是声明流程的第一步（描述末尾就引导模型先调它），残留资产（尤其 `description="d"` 一类垃圾）会直接污染模型的判断。本次实测就被 5 个更早的测试残留（`a1`/`my-dsl`/`my-recipe`/`probe-asset`/`r`）干扰过。

### 改后应达到的状态（具体参照物）

现成的对照物是基线那一次跑出来的资产 `fanout-review-loop.json`（10 节点：4 worker fan-out → `merge` 聚合 → `critic` 评审 → `rework` 重做 → `recheck` 复审 → `gate` 路由 → `report` 终态；`entry: ["w1","w2","w3","w4","rework"]`）。改后跑**同一条提示词**，观察：

> 它**是否直接写出这张图**（或等价拓扑），还是**又得先探 20 次**。

具体到可观察的差别：
- **改前基线**：模型先探 20 次（探针 L 才得出「loop body 也要进 `entry`」），期间撞 4 次 `invalid_spec`、15 次 `graph_recursion_exceeded`。
- **改后目标**：模型读完工具面就能写出带 `entry: [..., "rework"]` 的图，且 `channel` 一次写对（不出现 `control`/`data`/`draft` 一类自造值），`cases` 按「具体在前」排列。

### 软判断（主 session 执行）

读 transcript 回答一个问题：**它在「理解工具」上花了多少，在「理解任务」上花了多少**——这两个必须分开。如果改后仍要长时间试探，要分清是工具面还是任务本身的难度；如果 token 下降但都降在任务侧，说明工具面已经到位。**不设 token 降幅阈值**：这个 change 的收益形态是「消除一整类无效动作」，不是「线性省 token」。

### 证据归属

rollout 证据由实现方产出并落盘（`reviews/` 下附基线表 + 改后表 + 原始 transcript 路径），`/review-loop` 的独立 reviewer 核验其可信度（数字真实性、harness 是否被改动、结论是否 cherry-pick）。**reviewer 不自己跑 rollout**——贵、flaky，且会撞 3 轮封顶。

## Reference Implementation Research

- status: enabled
- research_tier: full
- reason: 命中 `full` 判据「走 grill 的非平凡 change」与「引入新协议（对象级 JSON Schema 暴露契约）」。本 change 触及 `DeclareWorkflow` 的工具契约（spec 里已钉死的 Requirement）、影响所有走 DSL 声明的调用方，且「枚举从源码派生」是一条**跨工具的长期纪律**，其边界（派生 vs 手写+测试锁定、per-kind 域的 schema 表达强度）正是本 change 的核心设计决策，必须由调研支撑。**不判 `light`/`exempt` 的理由**：调研结论会**反向挑战** issue #248 的建议方向 3（「把 `spec` 升级为结构化 schema」）——Anthropic API 对顶层 `oneOf`/`anyOf` 有限制（#246 RIR 已实测），因此「结构化到什么程度」不是成熟模式的局部应用，而是需要写明依据与设计影响的形态决策。
- research questions:
  - **RQ1**：业界 agent 框架（Claude Code / OpenAI function calling / MCP / 本地参考仓库）如何暴露**深度嵌套参数**的合法取值？是进 schema 的 `enum`，还是写在 description 散文里？
  - **RQ2**：当 schema 的合法值集合在代码里已有单一来源（枚举常量）时，业界是「生成 schema」还是「手写字面量 + 测试锁一致性」？
  - **RQ3**：如何表达「字段的适用性依赖另一个字段的值」（本 case：`join` 只属 `aggregate`、`cases` 只属 `route`）？JSON Schema 的判别子（`oneOf`/`discriminator`/`if-then`）在实践中可行吗，还是应退回 description？
  - **RQ4**：对「工具被误用但**不报错**」（silent ignore）这类问题，业界做法是声明期拒绝、返回 warning，还是文档说明？
  - **RQ5**：有没有参考实现提供「只校验不执行」的独立工具（对应 issue 方向 5 的 `ValidateWorkflow`）？
- findings:
  1. **RQ1 结论：枚举一致进 schema 的 `enum`，且这是主流做法的默认项。** `deepseek-harness`（本地参考仓库，权重高）的 `docs/tool-catalog.zh.md` 是逐工具的 JSON Schema 快照，其中**每一个**枚举型参数都带 `"enum": [...]`——例如 `plugin_manager` 的 `action` 参数把 8 个合法操作全部列出（`"enum": ["list_plugins","list_bundles","set_plugin","set_bundle","install_bundle","remove_bundle","list_version_exemptions","set_version_exemption"]`），并配一句 `"description": "Management operation."`。对照本仓：`DeclareWorkflow` 的 `spec` 参数连一层 `properties` 都没有。这不是「业界还没解决」，而是**本仓落后于业界基线**。
  2. **RQ1 补充：模型可见 schema 的稳定性被显式当作设计目标。** `deepseek-harness` 的 tool-catalog 对 `web_search`/`web_fetch` 逐字写着「将提供方选择置于 `ctx.web` 之后，**使模型可见 schema 在更换后端时保持稳定**」。同一原则在本仓的表现应是：schema 从源码常量派生，常量改则 schema 改，中间不留手写副本。
  3. **RQ2 结论：没有参考实现手写第二份枚举字面量。** 各仓库一律从类型/校验库的单一声明生成 schema——`zcode`/`kimi-code` 用 zod（`z.enum(['off','starting','on','stopping'])`，`kap-server/src/protocol/rest-remote-control.ts:5`）、`codex` 用 zod/JSON Schema 二选一（`sdk/typescript/samples/structured_output_zod.ts:13` 的 `z.enum([...])` 与 `samples/structured_output.ts:15` 的 `{ type: "string", enum: [...] }` **是同一份声明的两种序列化**，不是两份手写源）、`pi` 甚至专门写了 helper 来规避供应商差异：
     ```ts
     // pi/packages/ai/src/utils/typebox-helpers.ts:20
     export function StringEnum<T extends readonly string[]>(values: T, options?) {
       return Type.Unsafe<T[number]>({ type: "string", enum: values as any, ... })
     }
     ```
     其 docstring 明写动机：*"Creates a string enum schema compatible with Google's API and other providers that don't support anyOf/const patterns."* **结论：从常量派生 schema 是业界唯一做法；手写字面量需要理由，而不是反过来。**
  4. **RQ3 结论：判别子式 schema 在真实 provider 上有硬约束，业界退回「更宽的 schema + 运行期判别 + 描述」。** `pi` 的 subagent 工具是**直接可照抄的先例**（`packages/coding-agent/examples/extensions/subagent/index.ts`）：三种模式（single / parallel / chain）的参数在 schema 层是**全部可选**的并列字段（`:459-472` 的 `Type.Object({agent?, task?, tasks?, chain?, ...})`，一个 `oneOf` 都没有），判别在运行期做：
     ```ts
     const modeCount = Number(hasChain) + Number(hasTasks) + Number(hasSingle);
     if (modeCount !== 1) { /* 结构化拒绝，列出可用值 */ }
     ```
     而 `channel`/`kind`/`reducer` 这类**封闭枚举**与「模式判别」性质不同：它们没有 `oneOf` 的需求，直接就是 `"type":"string","enum":[...]`，**不触发任何 provider 限制**。这印证了本 change 的分工原则：**域（封闭值集）进 schema 是安全的；形（字段间组合）进 schema 是危险的**，因为后者往往需要 `oneOf`/`if-then`。
  5. **RQ4 结论：沉默忽略是最差的一档，业界普遍「接受但显式告知」或「拒绝」。** `opencode` 的 `task` 工具用 `task.txt` 承载大段使用规则（含明确的能力边界与返回约定），把「不适用」写在模型每次都看得到的地方；`pi` 对非法组合**拒绝并列出可用集合**（`Available agents: ...`），而不是静默取默认。没有任何参考实现把「字段被接受但完全无效」当作可接受状态。**这支持把 route `task` 的静默失效当成必须消除的缺陷**，而不是文档补充项（详见 design D6 / Open Question Q1——本 change 仍不预设 (a)/(b)/(c) 哪个方案）。
  6. **RQ5 结论：没有参考实现提供独立的只读 validate 工具。** 校验一律内联在「提交」动作里（`pi` 的 `modeCount` 判别、`deepseek-harness` 的 `z.object` 解析、`codex` 的 JSON Schema 校验），无一为「我只想检查一下」单开工具。**旁证**：这类工具会把「试错」合法化——而本 change 的目标恰恰是让模型**不需要试**。该结论支撑 design D10 把 `ValidateWorkflow` 列为 Non-Goal（而非本 change 的交付面），并列入 Open Question Q4 交用户拍板。
  7. **本地参考仓库可用性**：`.dev/reference-repos.txt` 在本 worktree **不存在**（该文件不提交，属正常）。已改用 `/home/shared/agent-study/reference-repos/` 实测目录，其中 `pi` / `deepseek-harness` / `codex` / `kimi-code` / `opencode` / `zcode` 六个仓库均可用，本 RIR 的 findings 全部来自这六个仓库的实际源码/文档（已记录 file:line）。**业界侧（Anthropic tool use / OpenAI function calling strict mode / MCP）未查本地仓库**：本 change 的 schema 形态受 Anthropic（顶层 `oneOf`/`anyOf` 拒绝）与本仓自身管线（`parameters` 逐字透传 `input_schema`）共同约束，后者已由 #246 的 RIR 与本次代码复核钉死，故 RQ1–RQ5 均在本地参考仓库层闭环，未额外联网核对。
- design impact: 见 design **D1**（域进 schema / 形进描述的分工）、**D2**（枚举从源码常量派生，不手写）、**D5**（per-kind 字段适用性退回描述，不做判别子 schema）、**D10**（不引入 `ValidateWorkflow`）。**调研对设计的主要影响**：RQ3 直接否决了「用 `oneOf` 表达 per-kind 域」的候选形态，并把 issue #248 方向 3 的「结构化 schema」**限定为「枚举进 schema、组合进描述」**；RQ4 把 route `task` 的静默失效从「文档补充项」提升为「必须消除的缺陷」（方案仍交 grill）；RQ6 奠定了 D2 的派生纪律——**手写枚举需要理由，派生是默认**。

## Impact Analysis

- **能力域**: `multi-agent-collaboration`（Workflow DSL 的工具面与描述契约）。
- **代码**:
  - `agent/subagent/workflow.py` — 新增/复用供 schema 派生的常量出口（`NODE_KINDS`/`CHANNELS`/`REDUCERS`/`AGGREGATE_STRATEGIES`/`JOIN_SEMANTICS` 已存在，`:30-35`；`mode` 三元组当前内联在 `_parse_node`，`:503-506`，需提为常量）。**不改任何校验逻辑**。
  - `agent/tools/builtin/subagents.py` — `DeclareWorkflowTool` 的 `parameters`（`:544-552`）从裸 object 升级为嵌套 schema；`description`（`:504-541`）纠错 + 补语义；`RunWorkflowTool` 的 `spec` 分支（`:906-916`）同步（两条路径的 spec 语义必须一致）。
  - `agent/subagent/scheduler.py` — **仅当 D7 采纳**：`_parse_strategy` 等 kind 专属解析器的错误文案改为按节点**实际** kind 命名（`workflow.py:571-577,583-588` 等）。**不改调度语义**。
  - `agent/subagent/patterns.py` — **仅当 D6 选 (a)**：peer-review 模板的 route 节点（`:202-209`）去掉 `task`。
- **测试**:
  - **必须新增**：schema↔常量 parity 测试（`DeclareWorkflow`/`RunWorkflow` 的 `spec.parameters` 里每个 enum 与对应源码常量元组逐字相等）——这是 D2 的机械保障，**没有它「派生」就退化成「又一份手写」**。
  - **必须新增**：描述内容断言（沿用既有范式 `tests/agent/subagent/test_workflow_cycle_contract.py:545-575` 的 `assert "..." in text`）——`control` 零命中、`cases` 语义句存在、per-kind 字段表存在。
  - **可能需改**（**仅当** D6 选 (a)）：`tests/agent/subagent/` 下 **5 个文件 15 处** route 节点带 `task` 的写法——已用 AST 实测：`test_scheduler.py:418,451,491,638,674`、`test_workflow_cycle_contract.py:65,152,190,289,347,380,383`、`test_recursion_limit_default.py:199`、`test_truncation_diagnostics.py:100`、`test_workflow_spec.py:152`。选 (b)/(c) 则零测试改动。
  - **预期保持绿**：`test_workflow_tools.py`（工具集/返回体断言）、调度器全部行为测试（本 change 不动调度语义）。schema 变更可能影响 `test_workflow_tools.py` 中对 `parameters` 形态的断言——需逐一核对（当前无「`spec` 是裸 object」的正向断言，预期仅新增断言）。
- **文档**:
  - `openspec/specs/multi-agent-collaboration/spec.md`（current spec 同步，受保护路径）——MODIFIED 1 + ADDED 1。
  - `docs/openspec-change-backlog.md`（本 change 入队 第十六批；受保护路径）。
  - `README.md` / `README_EN.md` / `docs/architecture.md` / `docs/agent-internals.md` 的工具清单段落：经关键词扫描（`DeclareWorkflow` / `channel` / `cases`）确认是否有事实变化；工具**数量与名字不变**，预期仅「描述内容」层面无 README 影响。
  - `docs/interview-script/` 相关讲稿：本 change 是「工具面可发现性」的完整案例（问题→实测→根因→改法），**建议**作为新问题候选，但按 AGENTS.md 该约束为建议性、不设门禁，列为可选任务。
- **流程（process）**: 本 change 触及受保护路径 `openspec/specs/**` + `docs/openspec-change-backlog.md`，需 `current_spec_synced` / `backlog_updated` 结构化事件 + grill 证据 + building review；实现须在独立 worktree、`workflow-tool-discoverability/2026-09-29` 分支。**change type = feature → 实现前必须走 `batch-grill-me` + 停轮确认 Open Questions**。
- **与既有 change 的边界（避免重叠）**：
  - **与 `workflow-builtin-templates`（#246，已归档）**：该 change 把模型侧入口从两个收敛为一个（`RunWorkflow(spec|template)`），本 change **不改入口形状**，只改 `spec` 这一入参的**内容契约**。该 change 的 D7 已把「截断诊断增 `declared_max_rounds`/`rounds_actually_run`/`limit_source`」落地，本 change **不碰诊断通道**。
  - **与 `workflow-recursion-limit-default`（#262，已归档）**：该 change 只调 `recursion_limit` 默认值（25→100），本 change 明确**不依赖它**——实测本 issue 的超限 `reason` 是 `max_routes`（`scheduler.py:1672`），调 `recursion_limit` 不解决本场景。
  - **与 #208（route 走 default 时看不到判定依据）**：**相邻但不同层且不同时机**——#208 是**运行后**的用户侧可观测性（快照补 `verdict`/`raw`），本 change 是**声明前**的模型侧可发现性。两者独立推进；本 change 实施后 #208 的动机更纯粹（只剩「运行后解释」）。
  - **与 #120（工具质量评分公式）**：同源（描述写得好不好）但不重叠——#120 关注**度量**，本 change 关注**内容修正**。本 change 的 parity 测试是**质量断言**，不是评分公式。
  - **与 #245/#246 的「资产化」**：资产化降低「手写 spec」的**频率**，但不消除——自由声明路径仍在，且配方资产最终仍要模型读得懂 spec 方言。本 issue 的摩擦属于**根因层**。
- **代价权衡（如实记录）**: schema 变大会**增加每次 API 调用的 input token**（`parameters` 每轮都发）。粗估：新增 5 个 enum + 嵌套 properties 约 +1.5~2.5k 字符（≈400-700 token）/轮。而基线一次失败执行的浪费是 **398,590 token**。即：只要消除一次探针循环，投入即已回本；即便模型仍犯错，增量成本也远小于现状。**但这是加法不是减法**——若 grill 认为描述层补语义已足够、schema 升级属过度，本 change 的 P1 第 3 项可单独降级（见 design D2 的替代方案）。
- **可回滚性**: 全部改动集中在工具描述与 schema 常量出口；回滚 = revert 该 commit，无数据迁移、无资产指纹变化（`spec_hash` 由 `WorkflowSpec.to_dict()` 计算，与工具 schema 无关）。

## Non-Goals（摘要）

- 不改任何调度/门控/reducer/计数语义。
- 不新增工具（含 `ValidateWorkflow`，见 design D10 / OQ Q4）。
- 不重做 `cases` 为表达式求值（`matches_route` 的「不做表达式求值」是安全姿态，`scheduler.py:325-337` 明写）。
- 不用 `oneOf`/`if-then` 表达 per-kind 域（RIR RQ3：provider 限制 + 本仓 `parameters` 透传约束）。
- 不改四个内置模板的编译产出（除非 D6 选 (a) 时去掉 route 的 `task` 字段）。
