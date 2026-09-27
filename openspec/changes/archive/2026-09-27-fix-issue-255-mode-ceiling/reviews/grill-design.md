# Grill: fix-issue-255-mode-ceiling 设计追问

## Reviewer

- **run id**: grill-fix-issue-255-mode-ceiling-2026-09-27T17:50 (+08:00)，独立零记忆 grill reviewer subagent（主 session 之外）
- **时间**: 2026-09-27
- **审视对象**: `openspec/changes/fix-issue-255-mode-ceiling/design.md`（D1–D6、Pre-Implementation Review、Risks/Trade-offs、Testing Strategy、Open Questions），并交叉核对 `proposal.md` / `diagnosis.md` / `tasks.md` / 两份 spec delta / issue #255 正文 / 相关实现
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/fix-issue-255-mode-ceiling-2026-09-27`，分支 `fix-issue-255-mode-ceiling/2026-09-27`，HEAD `5752ca0`（= master `5752ca0`）
- **工作区状态**: `M docs/openspec-change-backlog.md`；`?? openspec/changes/fix-issue-255-mode-ceiling/`（未提交）。本次 grill **未修改**除本文件外的任何文件；全部探针脚本落在 `/tmp/probe255grill/`
- **评审方法**:
  - **读码**：`agent/subagent/context.py`、`agent/subagent/manager.py`（`__init__` 440-560 / `configure_runtime` 530-548 / `create_subagent` / `_enqueue_run` 855-890 / `_start_task` 940-980 / `_execute_run_in_context` 991-1010 / `_run_loop` 1186-1240 / `_build_subagent_loop` 1262-1320 / `_clamp_mode`+`_parent_mode` 1588-1603）、`agent/subagent/scheduler.py`（`run` 707+ / `_execute_subagent` 1710 / `_launch_run` 2088-2165 / `_run_foreach_item` 1876-1900）、`agent/loop.py`（`__init__` 120-200 / `set_mode` 209-235 / `run` 531-590）、`agent/tools/builtin/subagents.py`（全部 spawn 类工具）、`agent/subagent/patterns.py`、`agent/run_config.py`（`AgentRuntimeState` / `ModePolicy`）、`agent/tool_permissions.py`（capability/profile 表）、`agent/main.py:290-311`、`web/session.py:1575-1586`、`benchmarks/agent_runner.py:378-390, 505-570`
  - **实跑探针**（`/tmp/probe255grill/`，全部以运行时 monkeypatch 模拟 proposed 机制，不落仓库）：`harness.py`（机制模拟：新 ContextVar + `_parent_mode` 读上限 + 挂载 A/B）、`probe_paths.py`（四条路径）、`probe_B_nest.py`（可达嵌套缺口，defect / mount-A-off / mount-A-on 三档对照）、`probe_A_guard.py`（挂载 A 在正常/cancel/`coro.close()` 下的形态）、`probe_E_readonly_parent.py`（降级父能否 spawn）、`probe_F_scan.py`（横向扫描）、`probe_G_concurrency.py`（并发/入队/benchmark 回落）、`probe_H_falsify.py` / `probe_K_falsify2.py` / `probe_L_recommended_test.py` / `probe_N_reachable.py`（design 的测试策略对「defect / fixed / fixed-but-no-ceiling-wrap」三档实现的真假保护对照）、`probe_I_stale.py`（既有 session 重跑）、`probe_M_stale.py`（陈留上限泄漏）、`probe_O_teardown.py`（执行点 `finally reset` 的 teardown ValueError）
  - **实跑门禁**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`（29 passed / 0 failed）；`uv run python scripts/check_openspec_artifacts.py --base-ref 5752ca0`（passed）

### 关键实测输出（原始片段）

```text
# probe_K_falsify2：issue 真实场景（BUILD 会话依次跑两张图，第二张声明 build）
### implementation = defect
    K2 silent degradation (场景三)  -> {'g1-ro': 'read_only', 'g2-bw': 'read_only'}
### implementation = fixed
    K2 silent degradation (场景三)  -> {'g1-ro': 'read_only', 'g2-bw': 'build'}

# probe_B_nest：root=BYPASS, child 声明 build, grandchild 不声明 mode（真实 AgentLoop 路径）
  0. defect (today: shared provider)              : modes={'child': 'build', 'grand': 'build'}
  1. mount A OFF (mount B only, provider deleted) : modes={'child': 'build', 'grand': 'bypass'}
  2. mount A ON  (mount A + mount B)              : modes={'child': 'build', 'grand': 'build'}

# probe_E_readonly_parent：降级父能否 spawn 子 agent（默认配置）
  parent effective mode = read_only -> BLOCKED
      tool result: [Permission denied: tool CreateSubagent is not allowed in read_only mode:
                    capabilities subagent_control are not allowed by permission profile read_only_default]
  parent effective mode = plan      -> BLOCKED
  parent effective mode = build     -> SPAWNED
  parent effective mode = bypass    -> SPAWNED

# probe_A_guard：挂载 A「不 reset」的残留
(i)   after run() returns: caller ceiling = AgentMode.BUILD; sibling manager sees AgentMode.BUILD
(ii)  after cancel: caller-task ceiling = AgentMode.BUILD
(iii) no reset (design)     : no exception
(iii) with finally reset    : no exception

# probe_M_stale：同 task 内先跑 BUILD loop，再直接驱动 read_only 会话的 scheduler
step 1: BUILD loop ran; ceiling left in this task = AgentMode.BUILD
step 2: read_only-session node declaring build -> {'n': 'build'}
        D6 claims the fallback is the conservative static parent_mode
        (read_only); observed: build => STALE LEAK

# probe_L_recommended_test：read_only 会话里模型调 RunWorkflow
    run2 tool calls: [('RunWorkflow', '[Permission denied: tool RunWorkflow is not allowed in read_...')]

# probe_O_teardown：执行点 finally reset（独立复现 design 的论断）
  task cancel (copied ctx) reset=True  -> no exception
  coro.close() SAME ctx   reset=True  -> no exception
  coro.close() OTHER ctx  reset=True  -> ValueError: <Token ...> was created in a different Context
```

## Confirmed Decisions

- **决策**: 双挂载（挂载 A run 起点收紧 + 挂载 B 派发点收紧）**充分且有其一不可**——四条路径（workflow 节点/孙辈、直接 spawn 链、混合路径、跨图嵌套）在两挂载下全部正确；但在默认配置下，「降级父 spawn 孙辈」这一子情形**不可达**，因为降级（read_only/plan）的子 loop 工具集**根本不含任何 spawn 类工具**，所以 design 的 O1 例子（read_only 子 agent 再起 build 孙辈）在真实权限层就被挡在门外；挂载 A 真正可达的必要性来自另一条路径（见下条）。理由: probe_B_nest 三档对照证明只做派发点挂载会让 grandchild 从 `build` 变成 `bypass`（引入新 fail-open），挂载 A 把它修回 `build`；probe_E 证明 read_only/plan 父根本 spawn 不了。来源: `/tmp/probe255grill/probe_B_nest.py`、`/tmp/probe255grill/probe_E_readonly_parent.py`、`agent/tool_permissions.py:87-95`（`READ_ONLY_CAPABILITIES` 不含 `SUBAGENT_CONTROL`）、`agent/tool_permissions.py:171-176`（`read_only_default` profile）。

- **决策**: 全仓**不存在绕过挂载 A/B 的第三条 spawn 路径**——`rg 'AgentLoop\(|_build_subagent_loop|create_subagent\(' agent/ web/ benchmarks/` 枚举出的全部生产构造点（`agent/main.py:311`、`web/session.py:1584`、`benchmarks/agent_runner.py:382`、`agent/subagent/manager.py:1303`）都或经过 `AgentLoop.run`（挂载 A），或最终经 `_launch_run`（挂载 B）；`CreateSubagent`/`RunSubagent`/`ResumeSubagent`/`RunPattern`/`DeclareWorkflow`/`StartWorkflow`/`RunWorkflow` 七个工具**全部**只调 `manager.create_subagent` / `manager.run_subagent`，无第二入口。理由: spawn 工具表由 `_ensure_subagent_tools_registered` 单一注册，`create_subagent` 是全仓唯一创建 session 的函数（除测试）。来源: `agent/tools/builtin/subagents.py`（七个工具类）、`agent/loop.py:366-409`、`agent/subagent/manager.py:547`。

- **决策**: 挂载 A「不 reset」在当前代码形态下**不会**产生「兄弟/后续 run 读到陈旧上限」或「reset 抛 ValueError」，但会**在调用方 task 里留下一个陈旧上限**，直接推翻 D6「未 set 时回落保守静态 `parent_mode`」的断言。理由: probe_A_guard (i)/(ii) 显示 `run()` 返回后调用方 task 的 ceiling 仍是该 run 的 mode（不是 `None`）；probe_M_stale 显示在同一 task 内先跑一个 BUILD loop、再直接驱动一个 `parent_mode=read_only` 会话的 scheduler（benchmark / 直接驱动形态）时，节点拿到 `build` 而非 D6 承诺的 `read_only`，即**跨会话 fail-open**。来源: `/tmp/probe255grill/probe_A_guard.py`、`/tmp/probe255grill/probe_M_stale.py`、`benchmarks/agent_runner.py:309,517-520`。

- **决策**: 「执行点 `_execute_run_in_context` 不 reset」的论断**独立复现成立**——`reset` 的 `ValueError` 只在「跨 context teardown」下出现，同一 context 内 cancel 或 `close()` 都不抛。理由: probe_O_teardown 四档对照：`task cancel` 与 `coro.close() SAME ctx` 在 reset=True 下均无异常，只有 `coro.close() OTHER ctx`（token 在一个 context 创建、在另一个 context close）抛 `ValueError: ... was created in a different Context`。来源: `/tmp/probe255grill/probe_O_teardown.py`、`agent/subagent/manager.py:999-1002`（既有注释 `No tokens are reset`）。

- **决策**: design 的 Testing Strategy 第 3 项（并发）与其第 1 项（fail-open 对照）在**单元层是假保护**——按 design 表面写法（调度器直接 `run()` + 单进程默认配置）写的并发用例在 defect 与 fixed 两种实现下**都绿**；真正的并发失效只在我第一版探针人为让两个 `_launch_run` 在同一 task 内交错时才复现，而 `_launch_run` 与既有 4 个身份 contextvar 同形态、每节点经 `create_task` 各自成 task，默认路径下天然隔离。理由: probe_H_falsify/probe_J 显示按 design 写法构造的并发用例在 defect 下即已通过；probe_K/probe_N 显示真正能区分 defect/fixed 的是「同会话内跨图/跨 run 的构造序污染」而非「同图并发」。来源: `/tmp/probe255grill/probe_H_falsify.py`、`/tmp/probe255grill/probe_J_concurrent_falsify.py`、`agent/subagent/scheduler.py:1593,1833`（每节点 `create_task`）。

- **决策**: 两条 ADDED Requirement 的**正文首个非空行均含 `SHALL`**，且 spec delta 中**不存在**「不保证 / SHALL NOT 覆盖 / 不适用于」之类保留措辞；`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py --base-ref 5752ca0` **均通过**。理由: 逐条 Requirement 首行实读（`系统 SHALL 让 workflow 节点…`、`系统 SHALL 从当前执行上下文的上限推导…`）；`rg '不保证|SHALL NOT 覆盖|不覆盖|不适用于|仅保证'` 唯一命中是 Scenario 标题「并发节点互不覆盖上限」（正当措辞）；两条门禁实跑输出见下节。来源: `openspec/changes/fix-issue-255-mode-ceiling/specs/*/spec.md`、`/tmp/probe255grill/`（门禁命令输出）。

- **决策**: `_clamp_mode` 的静态回落下限在**所有**生产构造点都是保守的：`agent/main.py:294`、`web/session.py:1579`、`benchmarks/agent_runner.py:378` 三处均显式传 `parent_mode=<会话初始 mode>`；`SubAgentManager.__init__` 的默认值是 `AgentMode.BUILD`（非 `READ_ONLY`），但在生产路径上永不生效。理由: 全仓 `SubAgentManager(` 构造点实扫；probe_G 的 G4/G5 确认「manager 以 `parent_mode=read_only` 构造、无 ceiling、`scheduler.run()` 直驱」时节点被收窄为 `read_only`（保守），`SubAgentManager()` 裸构造的默认是 `BUILD`。来源: `agent/subagent/manager.py:440,453`、`agent/main.py:290-294`、`web/session.py:1575-1579`、`benchmarks/agent_runner.py:378`、`/tmp/probe255grill/probe_G_concurrency.py`。

- **决策**: 与 #245 的口径重叠**确实存在且需按 O4 收窄**——#245 的 `multi-agent-collaboration` delta 中「加载期闸值与能力面钳制」Requirement 的**最后一个 Scenario 组**（`节点 mode 只收窄不放宽` / `会话 mode 上限在启动时快照` / `节点自身的 mode 受上限约束` / `嵌套 spawn 逐层收紧` / `跨图嵌套同样继承有效 mode` / `并发节点互不覆盖上限`）与本 change delta 的 Requirement **逐条同义**；两 change 都 ADDED 同一 capability 的 mode 语义，合并进 `openspec/specs/multi-agent-collaboration/spec.md` 时会产出**重复 Requirement**。按 O4，机制与基准语义归 #255 ⇒ **该由 #245 删除/收窄这六个 Scenario 及 Requirement 正文中的 mode 段**，只保留「资产路径列出将以声明 mode 运行的节点 + diagnostics」；本 change 的 delta 不需改动。理由: 两份 delta 逐条对读；#245 正文已显式写「本 Requirement 的 mode 收窄语义依赖既有缺陷修复（见 issue #255）」，即其 mode 段本就是占位性转述。来源: `/home/happy/.paseo/worktrees/0frj3kg8/workflow-asset-persistence-2026-09-26/openspec/changes/workflow-asset-persistence/specs/multi-agent-collaboration/spec.md`（Requirement「加载期闸值与能力面钳制」末段与末尾六个 Scenario）。

- **决策**: 横向扫描确认「共享可变实例字段被并发构造覆写」的**同构缺陷不止 `parent_mode_provider` 一处**：`AgentLoop.__init__` 复用 `tool_registry.mode_policy.runtime_state`（`agent/loop.py:159-161`），因此**同一个 `ToolRegistry` 被两个 loop 复用**时，两个 loop 共享同一个 `AgentRuntimeState`，后构造的 loop 的 `run_config.mode` 被前者的 `runtime_state` 静默吞掉。理由: probe_F_scan F1/F2 实测——`loop1(run_config=read_only)` 与 `loop2(run_config=build)` 共用同一 registry 时，`loop2.runtime_state IS loop1.runtime_state` 为 `True`，`loop2.runtime_state.current_mode` 解析为 `READ_ONLY`（`loop2.run_config.mode` 却是 `build`）；这会让挂载 A 在 `loop2.run()` 时快照到**错误（更宽/更窄）**的上限。生产路径上每个 loop 各自 `build_default_tool_registry`（`agent/main.py:262`、`web/session.py:1559`、`agent/subagent/manager.py:1271`），故**当前无真实影响**，但它是与 #255 同一条根因（把作用域量挂在会被复用的共享对象上）的潜伏面。来源: `/tmp/probe255grill/probe_F_scan.py`、`agent/loop.py:159-161`、`agent/run_config.py:88-92`、`agent/tools/factory.py:192`。

## Open Questions

> **本轮无新增 Open Question。** O1–O5 已于 2026-09-27 全部确认，逐条见下（保留原例以便复查）。

- **O1【✅ 已确认（2026-09-27）：纳入】**：直接 spawn（非 workflow）的链式嵌套纳入本 change 范围，故必须实现挂载 A。
  **例子**：root = `bypass`（或 `build`，见下）的一次 run 里，模型链式 `CreateSubagent(child, mode=build)` → 子 agent 内再 `CreateSubagent(grand)`（不声明 mode）。若只做派发点挂载并删 provider，`grand` 读到 root 的上限（`bypass`）而不是 `child` 的有效 mode（`build`）⇒ fail-open；含挂载 A 则 `grand = build`。
  **⚠️ grill 复核补正（不改变 O1 结论，改变其「可复现例子」）**：design 原文举的例子（`read_only` 子 agent 再起 `build` 孙辈）在**默认权限配置下不可达**——`read_only`/`plan` 的子 loop 工具集里**没有** `CreateSubagent`（实测被 `[Permission denied: ... capabilities subagent_control are not allowed by permission profile read_only_default]` 拦下）。挂载 A 的必要性仍然成立，但要用**可达**例子说明：root = `bypass`，`child` 声明 `mode: build` ⇒ 只挂派发点时 `grand` 得 `bypass`（**新 fail-open**，实测），含挂载 A 得 `build`。**建议 tasks.md 4.4 路径 (b) 与 design D3 的示例按此更正**，否则回归测试会照着一个跑不通的场景写。

- **O2【✅ 已确认（2026-09-27）：run 起点口径】**：快照点取「run 起点」，不提为「workflow 启动点」。
  **例子**：root loop 一次 run 起点 mode=`build`；run 第 3 步用户切到 `read_only`；第 5 步模型调 `RunWorkflow`，节点声明 `mode: build`。run 起点口径 ⇒ 节点得 `build`；workflow 启动点口径 ⇒ `read_only`。

- **O3【✅ 已确认（2026-09-27）：回落静态 `parent_mode`（保守），绝不回落 `None`】**。
  **例子**：benchmark runner 直接 `WorkflowScheduler(manager).run(spec)`（不经任何 `AgentLoop.run`）且 manager 以 `parent_mode=read_only` 构造 ⇒ 节点得 `read_only`；若回落 `None` ⇒ 得 `build`（fail-open）。
  **⚠️ grill 复核发现的边界（见 `## 风险` R1）**：该保守性只在「调用方 task 内**从未**跑过任何 `AgentLoop.run`」时成立；一旦同 task 内先跑过别的会话的 loop，挂载 A 留下的陈旧上限会让回落读到那个值 —— 实测 `read_only` 会话拿到 `build`。

- **O4【✅ 已确认（2026-09-27）：#255 拥有机制与基准语义】**：#245 保留资产面的「列出将以声明 mode 运行的节点 + diagnostics」。
  **例子**：某节点声明 `mode: build`、会话只读；#255 delta 写「有效 mode = min(...)，不得放宽」，#245 delta 写「资产路径列出将以声明 mode 运行的节点 + 记 diagnostics」。
  **⚠️ grill 复核补正**：口径重叠不只是「概念重叠」，而是 #245 的 delta 里**已有六个逐条同义的 Scenario**（详见 `## Confirmed Decisions` 末条），必须在 #245 侧删除，否则两 change 先后合并会在 `openspec/specs/multi-agent-collaboration/spec.md` 留下重复 Requirement。

- **O5【✅ 已确认（2026-09-27）：挂载 B 带 `finally reset`】**，执行点 `_execute_run_in_context` 不带，挂载 A 不带。
  **例子**：`_launch_run` 是调度器 task 内被 await 的普通协程，与既有 4 个身份 contextvar 同形；实测带/不带 reset 都得到正确兄弟隔离，采用带 reset 以贴合既有惯例。

## User Confirmation

- **Q1**: 用户答复：纳入「直接 spawn 链式嵌套」路径，挂载 A（run 起点收紧）由可选升级为**必须**；理由：`CreateSubagent(mode=...)` 是常规调用，且删掉共享 provider 后该路径会从「碰巧对」变成「确定错」，不修就是改动引入的回归；确认时间: 2026-09-27
- **Q2**: 用户答复：快照点取 **run 起点**（`AgentLoop.run` 开头），不提为「workflow 启动点（`scheduler.run()`）」；一次 run 内先切 mode 再起 workflow，该 workflow 上限仍取该 run 起点的 mode；确认时间: 2026-09-27
- **Q3**: 用户答复：`current_mode_ceiling()` 未 set 时回落**静态 `parent_mode`**（会话初始 mode，保守），**绝不回落 `None`**（不收窄即 fail-open）；确认时间: 2026-09-27
- **Q4**: 用户答复：**#255 拥有机制与基准语义**；#245 保留资产面的「列出将以声明 mode 运行的节点 + diagnostics」，并按此收窄 / 对齐其 delta；确认时间: 2026-09-27
- **Q5**: 用户答复：挂载 B（派发点 `_launch_run`）采用 `set` + **`finally reset`**（与既有 4 个身份 contextvar 同形）；执行点 `_execute_run_in_context` 与挂载 A 均**不带** reset；确认时间: 2026-09-27

## 风险

- **【严重度：高】挂载 A 不 reset ⇒ D6「保守回落」在跨会话同 task 场景下失效（fail-open）。** 实测：同一 task 内先跑一个 `build` 会话的 `AgentLoop.run`，再直接驱动一个 `parent_mode=read_only` 会话的 `WorkflowScheduler(...).run(...)`（benchmark `template`/`dynamic-replay` 路径、或任何不经 loop 的直驱），节点声明 `build` ⇒ 实际授予 `build`（期望 `read_only`）。此时 `current_mode_ceiling()` 读到的是**上一个会话的上限**，既不是本会话上限也不是保守下界。**缓解建议**：(a) 把挂载 A 从「每次 run 开头无条件 set」改为「run 开头 set + 记录该 run 的快照值，run 结束后把上限**恢复为 `None`/或本会话的 `parent_mode`**」——但**不能**用 `reset(token)`（跨 context teardown 会抛 `ValueError`），应改用同值的 `set()`（不依赖 token）；(b) 或让 `_clamp_mode`/`current_mode_ceiling()` 把「contextvar 有值」与「该值属于当前执行单元」区分开（例如随上限一起 set 一个 owner 标识）；(c) 最低限度也必须新增一条回归覆盖此场景（design 现有 7 项均不覆盖）。**在 tasks.md 中作为独立验收项**：`scheduler.run()` 直驱路径 + 同 task 内有其它会话 loop 运行史时，回落必须仍保守。

- **【严重度：高】Testing Strategy 第 3 项（并发）与第 1 项对照存在假保护，不能证明修复有效。** 实测：按 design 表面写法（单进程默认配置 + `WorkflowScheduler.run`）构造的并发用例，在 **defect** 实现下同样返回 `{'A': 'build', 'B': 'read_only'}`（正确值），即该用例**不能**把修复与未修复区分开；而真正能区分的 K2/K1 型用例（**同会话内跨图/跨 run 的构造序污染**）实测在 defect/fixed 下分别是 `read_only`/`build`。**缓解建议**：把回归重心从「同图并发」改为「同会话顺序两图 + 中途切 mode」；并发项保留但必须**另配**一条「同 task 内人为交错两个 `_launch_run`」的用例（我第一版探针的形态），否则该行形同虚设。另：design 第 1 项的「对照」（build 会话 + build 节点 ⇒ build）在 defect 下也绿，只能挡住「无差别压低」，挡不住原缺陷 —— 这一点 design 自己也承认，但表格把它列为「防假保护」容易让人误以为整表可自证。

- **【严重度：高】回归测试形态必须驱动真实 `AgentLoop.run` 才能激活挂载 A；design 未把这条写成硬约束。** 实测：用 `H.set_mode_ceiling(...)` 手工包裹 `scheduler.run()` 的「单元式」测试（`probe_K` 的 `fixed_nowrap` 档）在 K1 场景下返回 `build`（未收窄），与 defect 无差别；只有走真实 `root.run([...])` 的端到端形态（`probe_N_reachable`）才返回 `read_only`。**缓解建议**：tasks.md 4.5 / 4.6 与 4.3 明确要求「经由 `AgentLoop.run` 驱动」，并写明「不得用 mock 手工 set 上限替代 run 起点」。另注意「read_only 会话内模型调 `RunWorkflow` 会被权限层直接拒绝」——写「run 中途切到 read_only」的用例时，切换必须发生在 `RunWorkflow` **之后**，否则测的是权限拒绝而不是 mode 钳制。

- **【严重度：中】既有 session 重跑不重新钳制 mode（design 未覆盖，且不在本 change 范围内）。** 实测：`CreateSubagent(child, mode=build)` 在建会话时把 mode 冻结，之后会话切到 `read_only`，模型对**同一** `subagent_id` 调 `RunSubagent` ⇒ 该子 run 仍拿到 `Bash`/`Edit`/`Write`/`CreateSubagent` 全套写权限。`_clamp_mode` 只在 `create_subagent` 调用，`run_subagent`/`resume_subagent` 路径不经过它。**缓解建议**：这属于「mode 在会话创建期冻结」的既有设计（与本 change 的 run 起点快照语义冲突），**不要在本 change 顺手改**（会扩大爆炸半径）；但必须（a）在 `## Non-Goals` 或 `## Risks` 中显式登记为**已知残留**，（b）在 #245 的资产面「列出将以声明 mode 运行的节点」里说明该列表对**已存在** session 的 mode 不作保证。若不加登记，审阅者会误以为 #255 已覆盖所有 fail-open 面。

- **【严重度：中】`.claude/` 被 gitignore ⇒ worktree 内 workflow_guard 不生效，本 change 的门禁只能靠 CI 兜底。** 本 grill 在独立 worktree 内运行，受保护路径（本文件落在 `reviews/` 下、非受保护路径，安全）与 tasks 门禁均无法本地拦截。**缓解建议**：合并前确认 CI 的 `validate` job 跑到了 `check_openspec_artifacts.py --base-ref <PR base>`，不要只依赖本地绿色。

- **【严重度：低】benchmark 任务 `asterwynd-009-subagent-manager` 的 `gold.patch` 内含 `parent_mode_provider` 的**新增**行。** `task.json` 的 `base_commit=89f1c116`（早于现状）且该任务未被现役 pytest 收集（`tests/benchmark/` 只读 `benchmarks/tasks/manifest.json` 与 `swebench-*`），故本 change **不会**使它失败。**缓解建议**：tasks.md 2.6 的验收写法「`rg 'parent_mode_provider'` 全仓零命中（除本 change 文档的历史引用）」应改为**排除 `benchmarks/tasks/**/*.patch` 与 `docs/openspec-change-backlog.md`**，否则该验收项自身会红。

- **【严重度：低】`AgentLoop` 复用 `tool_registry.mode_policy.runtime_state` 是与 #255 同根因的潜伏面（详见 Confirmed Decisions 末条）。** 当前生产路径每 loop 各自建 registry，无真实影响。**缓解建议**：**不在本 change 修**，登记到 `docs/known-debt.md`（或作为 #255 的 follow-up issue），并加一条注释说明「registry 与 loop 不得跨 mode 复用」。
