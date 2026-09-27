# Diagnosis: workflow 节点 mode 钳制基准错误（fix-issue-255-mode-ceiling）

## Symptom

`SubAgentManager._clamp_mode`（`agent/subagent/manager.py:1588`）的本意是「节点有效 mode 不得超过当前会话 mode」，但它的比较基准 `self.parent_mode_provider` 是一个**跨 run 共享、会被并发构造覆盖的可变实例字段**。三个外显症状（issue #255 记录，本 change 独立复现，见下节）：

1. **时序 fail-open**：BUILD 会话跑过工作流后切到 `read_only`，声明 `mode: build` 的节点/资产仍被授予 **BUILD**。
2. **并发结构性错误**：并行节点 `A(build)` / `B(read_only)` 互相覆盖，**构造顺序决定结果**。
3. **静默降级 + 跨图污染**：BUILD 会话（用户从未切模式）顺序跑两张图，图 1 的只读节点把图 2 的 `build` 节点降级为 `read_only`，无任何诊断。

安全影响是**方向性**的：只读会话可被授予写权限（fail-open），而不是「拒绝过度」。

## Reproduction

**三个症状的最小复现**（只读探针，脚本产出见「Evidence」；全部用真实 `AgentLoop` / `SubAgentManager` 构造路径，`_build_subagent_loop` 的等价物即 `AgentLoop(..., subagent_manager=mgr, run_config=AgentRunConfig(mode=...))`）：

```text
========================================================================
症状一：时序 fail-open（BUILD 跑过图 → 切 READ_ONLY → 授予 BUILD）
========================================================================
  步骤1 BUILD 会话        provider=AgentMode.BUILD
  步骤2 跑 build 节点后    provider=AgentMode.BUILD
  步骤3 用户切 READ_ONLY: root.current_mode=AgentMode.READ_ONLY provider=AgentMode.BUILD  <- 未跟随
  步骤4 声明 build 的节点 -> 授予 AgentMode.BUILD
  >>> FAIL-OPEN: True

========================================================================
症状二：并发结构性错误（构造序决定结果）
========================================================================
  构造序 ('A(build)', 'B(ro)') -> provider=AgentMode.READ_ONLY  A 请求 build 得 AgentMode.READ_ONLY
  构造序 ('B(ro)', 'A(build)') -> provider=AgentMode.BUILD  A 请求 build 得 AgentMode.BUILD

========================================================================
症状三：静默降级 + 跨图污染（用户从未切模式，全程 BUILD）
========================================================================
  图1（含只读节点）跑完后 provider=AgentMode.READ_ONLY
  图2 的 build 节点 -> 授予 AgentMode.READ_ONLY
  >>> 跨图污染静默降级: True
```

**端到端复现（真实调度器）**——挂载点对照探针。会话真实 mode 为 `read_only`，节点声明 `mode=build`，记录该节点**自身**拿到的有效 mode：

```text
会话已切 READ_ONLY，节点声明 mode=build —— 期望节点自身 = read_only
  挂载点=none      会话=read_only 节点自身授予=['build']  ✗ FAIL-OPEN
  挂载点=runctx    会话=read_only 节点自身授予=['build']  ✗ FAIL-OPEN
  挂载点=dispatch  会话=read_only 节点自身授予=['read_only']  ✓ 收窄
```

`runctx` = 把上限挂在 `_execute_run_in_context`（run 真正执行处）；`dispatch` = 挂在 `_launch_run`（调度器派发点）。**挂 `runctx` 修不了节点自身**——这独立复现了 issue #255「落点必须挂派发点」的结论。

**`finally reset` 的 teardown 崩溃复现**——在 run 执行上下文里 `set` 并配对 `finally reset`，当 task 被跨 context teardown（`coro.close()`）时：

```text
cancel+await  : 无异常
coro.close()  : ValueError: <Token ...> was created in a different Context
```

**为何节点自身修不了**：节点自身的 mode 在 `create_subagent` → `_clamp_mode` 里**定死**，而该调用发生在 `scheduler._launch_run` 的**派发阶段**（`scheduler.py:2119`）；`_execute_run_in_context`（`manager.py:991-1006`）是 run **真正执行**时才跑，**晚于**节点 mode 的冻结，只能管到孙辈。

## Evidence

### 证据 1：钳制的形状正确，输入错误

`_clamp_mode`（`manager.py:1588-1598`）按权限等级取小，形状无误：

```python
def _clamp_mode(self, requested: AgentMode) -> AgentMode:
    parent_mode = self._parent_mode()          # <-- 输入来源
    order = {READ_ONLY: 0, PLAN: 0, BUILD: 1, BYPASS: 2}
    if order[requested] > order[parent_mode]:
        return parent_mode
    return requested

def _parent_mode(self) -> AgentMode:           # manager.py:1600-1603
    if self.parent_mode_provider is not None:
        return self.parent_mode_provider()
    return self.parent_mode
```

### 证据 2：`parent_mode_provider` 是共享实例字段，唯一写入点在 `AgentLoop.__init__`

| 事实 | 位置 |
|---|---|
| 字段声明 | `manager.py:454` `self.parent_mode_provider = parent_mode_provider` |
| 唯一写入（覆写）点 | `manager.py:544-545`（在 `configure_runtime` 内） |
| 唯一调用 `configure_runtime` 的仓库位置 | `agent/loop.py:153-155`，`parent_mode_provider=lambda: self.runtime_state.current_mode` |
| 子 loop 复用同一 manager | `manager.py:1303` `subagent_manager=self`（`_build_subagent_loop`） |

仓库内 `parent_mode_provider` 的全部出现点（`rg`）：`manager.py` 4 处（形参 / 赋值 / `configure_runtime` 形参 / `configure_runtime` 赋值 / `_parent_mode` 读取）+ `agent/loop.py:155` 1 处。**子 agent loop 的每一构造都经 `AgentLoop.__init__` 覆写该字段**。

### 证据 3：子 loop 构造确实发生在并行节点执行路径上

`_build_subagent_loop`（`manager.py:1262`）在 `_run_loop`（`manager.py:1200`）里被调用，每个节点 run 一次；并行节点各自构造一个子 loop，**各自覆写同一 manager 字段**。构造顺序即覆盖顺序。

### 证据 4：测试盲区

```text
$ rg 'parent_mode_provider|_clamp_mode' tests/
(exit 1, 零命中)
```

既有 `tests/agent/subagent/test_subagent_manager.py:57-81` 的 `test_create_subagent_*` 走的是 `parent_mode=` **构造参数**（静态、不被覆写），因此完全绕过了出问题的路径。

### 证据 5：既有代码早已为身份字段采用正确方案，注释写明了理由

`agent/subagent/context.py` 模块 docstring 与 `_launch_run`（`scheduler.py:2108-2115`）注释：

> asyncio 的每个 Task 各持一份 context 副本，其它节点的 run 看不到这里的 set

`workflow_id` / `node_id` / `graph_distance` / `bus` 四项**已在同一派发点** set + `finally reset`。**仓库早已知道共享标量在并发节点下不成立，唯独 `mode` 还留在共享标量上。**

### 证据 6：端到端对照（挂载点）

见「Reproduction」第二段：`none` / `runctx` 两种挂法在「只读会话 + build 节点」下都 FAIL-OPEN，只有 `dispatch` 收窄正确。

### 证据 7：`reset` 在派发点安全、在执行点不安全

- 派发点 `_launch_run` 是调度器 task 内被 `await` 的**普通协程**，与既有 4 个 contextvar 同形态，`set` + `finally reset` 安全（探针实测：`reset=True` 与 `reset=False` 在该点都得到正确的兄弟隔离；采用 `reset=True` 与既有形态一致，且不依赖「每节点各自成 task」这一脆弱前提）。
- 执行点（`_execute_run_in_context`）的 `finally reset` 在跨 context teardown 时抛 `ValueError`（见「Reproduction」第三段）。既有代码因此在 `manager.py:999-1002` 明写 **No tokens are reset**，理由是该 task 拥有捕获上下文的私有副本。

## Root Cause

**单一根因**：`mode` 上限这一**并发作用域内必须逐执行单元区分的量**，被建模为 manager 上的**单一共享可变标量**（`parent_mode_provider`），而该标量的写入时机与并发节点的构造时机重叠。

- 它**不是**「`configure_runtime` 的调用点写错了」——写在一个共享对象上，无论写在哪里都逃不过并发覆盖。
- 它**不是**「没有 `finally reset`」——该字段根本没有 context 语义，reset 无从谈起。
- 它**不是**「子 loop 不该复用 manager」——复用 manager 是有意的（共享 session 注册表、预算、spawn 桶），问题只在于把一个**作用域量**也挂在了共享对象上。

**正确模型**：mode 上限是**执行上下文（asyncio Task context）**的量，应与 `workflow_id` / `node_id` / `graph_distance` / `bus` 一样用 `ContextVar` 承载——每个 Task 各持一份副本，并发兄弟天然隔离，嵌套经 `copy_context()` 逐层继承。

## Hypotheses

| # | 假设 | 判定 | 依据 |
|---|---|---|---|
| H1 | 覆盖来自子 loop 构造（而非 `set_mode` 未重调 provider） | **成立** | 证据 2/3：写入点唯一且在 `__init__`；探针症状二以构造顺序反转复现 |
| H2 | 落点在 `_execute_run_in_context` 即可修好 | **推翻** | 证据 6：挂 `runctx` 仍 FAIL-OPEN（节点自身 mode 早于其冻结） |
| H3 | 派发点 `set` 必须**不**带 `finally reset` | **部分推翻** | 证据 7：派发点带 reset 安全；真正不能 reset 的是执行点（跨 context teardown） |
| H4 | 只钳节点自身即可，无需管子孙 | **推翻** | 嵌套探针：仅派发点钳制会让孙辈回落到会话上限（见「Regression Tests」第 4 项） |
| H5 | 该缺陷是孤例，需横向扫描同类面 | **成立（范围为 1 处）** | `configure_runtime` 另两个参数在唯一调用点传 `None`（永不覆写），`llm` 覆写同一对象且幂等无害；`rg` 确认无第二处同构缺陷 |

## Recommended Direction

> 推荐方案与修复选项的完整论证。用户已确认的语义见 issue #255 与 #245 grill，本 change 不重新发明。

### Fix Options

- **方案 A（已定，contextvar + 派发点传播）**：mode 上限并入既有 `context.py` 的 contextvar 家族；会话 loop 在 run 起点快照会话 mode；调度器在派发点按 `min(节点声明, 当前上限)` 收紧并 `finally reset`；`_clamp_mode` 读上下文上限。**优点**：复用仓库已验证的机制，与并发正确性、嵌套继承、快照语义天然一致，无新增依赖。**代价**：触碰 `manager` / `loop` / `scheduler` / `context` 四处；删除 `parent_mode_provider`。
- **方案 B（显式参数穿过）**：把节点有效 mode 作为参数显式穿到 `create_subagent`，不改 contextvar。**缺点**：并发节点各自的 mode 需要调用方逐次传递、易漏；嵌套需手工逐层传递；与既有身份字段机制分叉。
- **方案 C（只修 fail-open 方向）**：仅在派发点对 `node.mode` 与当次会话 mode 取 min，不修「兄弟污染」。**缺点**：只掩一半；并发与跨图污染仍在；与 issue #255 要求的三症状全覆盖不符。
- **方案 D（在共享字段上补 reset / 显式重算）**：试图让共享字段「每次用前重算」。**缺点**：并发节点仍读同一标量，不可能同时正确（症状二），根因未消。

**推荐：方案 A。** 它对准根因而非症状，且是本仓库既有正确机制的直接沿用（证据 5）。

**推荐方案的具体语义（用户已确认，见 issue #255 与 #245 grill）**：

1. 节点 mode 在**声明 workflow 时**配置；
2. 运行时**不可改变**；
3. 节点有效 mode = `min(节点声明 mode, 当前会话上限)`；
4. 上限经 **contextvar** 传播（与身份字段同路）；
5. **快照语义**：上限在 run 起点快照，运行中途切换会话 mode **不影响**本次 run；
6. **嵌套继承**：节点 A 的有效 mode `E_A = min(M_A, R)`，A 的子孙上限为 `E_A`，逐层收紧；
7. 落点在**派发点** `_launch_run`（非执行点）；
8. 执行上下文的 set **不配对** `finally reset`（跨 context teardown 会抛 `ValueError`）；派发点的 set 沿用既有 4 个 contextvar 的 set/`finally reset` 形态。

**必须在验收中显式包含的通道**：#245 的 Q11 要求 #255 提供一个 **scheduler 可读的会话 mode 通道**（否则 #245 的整轮上限快照会静默读不到值、退化回 fail-open）。本 change 以 `current_mode_ceiling()` 只读访问器提供该通道，并写入 spec 与 tasks 的验收条件。

## Regression Tests

> 仓库规则：每个 bug fix 必须新增回归测试。issue #255 已列 5 项，本 change 追加第 6 项（跨图污染），并对**每一项**配「合法路径必须成功」的对照，防「无差别压低」的假修复。既有 `parent_mode=` 静态路径用例作为不改行为的回归基线保留。

1. **fail-open 方向**：只读会话 + 声明 `build` 的节点/资产 ⇒ 实际授予 **只读**（对照组：build 会话 + 声明 build ⇒ 授予 build，证明钳制不是无差别压低）。
2. **静默降级方向**：BUILD 会话中，先跑一个只读节点，再跑声明 `build` 的节点 ⇒ 后者**不被**降级（对照：只读节点自身仍为只读）。
3. **并发**：并行节点不同 mode 互不干扰，含**构造顺序反转**的时序不变性（`('A','B')` 与 `('B','A')` 结果一致）；两组对照证明各节点拿到各自正确的上限。
4. **嵌套**：grandchild spawn 的上限继承其父节点的**有效** mode（不是根会话 mode）；对照：根会话为写时，只读节点的子孙仍为只读。
5. **快照**：workflow 运行中途切换 root 会话 mode，本次 run 的上限**不变**；对照：该会话后续**新启动**的 run 按新 mode 取上限。
6. **跨图污染（本 change 追加）**：同一会话顺序跑两张图，前一张（含只读节点）**不影响**后一张的起点快照（对照：两张图各含 build 节点时都拿到 build）。
7. **通道验收（#245 契约）**：`current_mode_ceiling()` 在 scheduler 起点可读到正确的会话上限；未设置时回落静态 `parent_mode`（构造参数）而非无界。
