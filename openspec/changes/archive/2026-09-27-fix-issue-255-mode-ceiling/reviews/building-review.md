# Building Review: fix-issue-255-mode-ceiling

PASS

- **reviewer**: 独立零记忆实现审阅 subagent（与主 session 无共享上下文），run `review-fix-issue-255-mode-ceiling-2026-09-27T19:20 (+08:00)`
- **工作区**: `/home/happy/.paseo/worktrees/0frj3kg8/fix-issue-255-mode-ceiling-2026-09-27`，分支 `fix-issue-255-mode-ceiling/2026-09-27`
- **base**: `5752ca0`；**head（审阅对象）**: `c3d482e`（`fix-issue-255：mode 钳制基准改走执行上下文上限`）
- **审阅方法**: 逐份读 change 文档（proposal / diagnosis / design / grill-design / tasks / 两份 spec delta）+ 读实现 diff + **自写独立探针**（不 import 作者的测试模块）+ **运行时 monkeypatch 变异验证**（不落仓库文件）
- **限定**：本次审阅只新建本文件，未修改任何其它文件；未 commit / push / 切分支。全部探针脚本落在 `/tmp/probe255review/`。

> **环境事实（影响「可复现性」判断，非缺陷）**：审阅开始时**同一 worktree 内仍有另一 paseo agent 在运行**（`463a3597`「#255 mode 钳制基准修复立项」），且 `docs/agent-internals.md` 有一处**未提交**修改（内容为本次语义的文档补充）。为不与其冲突，所有变异验证均走 `PYTHONPATH` 插件在运行时替换符号，未改动任何仓库文件。因此本次审阅对象严格锚定 `c3d482e` 的提交内容。

---

## Verdict 依据（一句话）

修复方向正确、实现与已确认的 O1–O5 一致、**独立探针 18/18 全绿**、变异验证能把修复与缺陷区分开、三道门禁（pytest / openspec strict / artifact checker）均通过。发现的 6 条问题全部是**观察项**（1 条中、5 条低），无一阻塞 PASS。

---

## 逐条任务验证

| 任务组 | 结论 | 证据 |
|---|---|---|
| **1.1–1.4 前置（grill / 停轮确认 / 回写 / #245 契约）** | 已验证 | `reviews/grill-design.md` 存在，9 条 Confirmed Decisions、O1–O5 均有 `## User Confirmation` 实质答复（无占位文本）；`design.md:247-268` 已按答复回写（挂载 A 升级为必须、快照点 run 起点）。 |
| **2.1 contextvar 与访问器** | 已验证 | `agent/subagent/context.py:52`（`_mode_ceiling`）、`:127-142`（`current_mode_ceiling` / `set_mode_ceiling` / `reset_mode_ceiling`），与 `_graph_distance` 等既有四项同形。 |
| **2.2 保守回落链** | 已验证 | `agent/subagent/manager.py:1601-1613`：contextvar → `self.parent_mode`，**无 `None` 分支**。探针 P5a 实测 `parent_mode=read_only` 直驱 ⇒ 节点得 `read_only`。 |
| **2.3 `_clamp_mode` / `_parent_mode` 改读上限** | 已验证 | `manager.py:1589-1599`（形状未改）、`:1601-1613`。 |
| **2.4 删除 `parent_mode_provider`** | 已验证 | `rg 'parent_mode_provider'` 全仓命中仅剩：`benchmarks/tasks/asterwynd-009-subagent-manager/gold.patch`（历史基线）、`docs/openspec-change-backlog.md:104`（历史引用）、本 change 文档自身。**`agent/`、`tests/`、`web/`、`benchmarks/*.py` 零命中** —— 与 tasks 2.6 的排除口径一致。 |
| **2.5 删除 `AgentLoop.__init__` 的 lambda** | 已验证 | `agent/loop.py:154` 现为 `configure_runtime(llm=llm)`；`manager.py:534-546` 的 `configure_runtime` 已无 `parent_mode_provider` 形参。`rg 'configure_runtime'` 生产调用点仅 `loop.py:154` 一处。 |
| **3.1 挂载 A（set + `set(prior)` 恢复）** | 已验证 | `loop.py:553-554`（捕获 prior + set）、`:582`（`finally` 用 `set_mode_ceiling(previous_ceiling)` 恢复，**非 reset**）。探针 P6a/b/c 覆盖成功 / 异常 / 取消三条路径，均回到 `None` 且不抛 `ValueError`。 |
| **3.2 挂载 B（`set` + `finally reset`）** | 已验证（形态）/ **不可测（outcome-idempotent）** | `scheduler.py:2125`（`set_mode_ceiling(manager.effective_mode(node.mode))`）、`:2148`（`finally` reset），与既有 4 个身份 contextvar 同处同形。**但其行为无法被任何用例区分**，见 Issue #2。 |
| **3.3 执行点不 reset** | 已验证 | `manager.py:992-1003`（`_execute_run_in_context`）内**零** `reset_*` 调用（`rg 'reset_' agent/subagent/manager.py` 无命中）；docstring `:1000` 保留了「No tokens are reset」的既有理由。 |
| **3.4 嵌套收紧（两条路径）** | 已验证 | 路径 (b)：探针 P3b 实测 `grand` 继承 `child` 的有效 mode `build`（root 为 `bypass`）。路径 (a)：`scheduler._launch_run` 在 `create_subagent` **之前** set（`scheduler.py:2125` 早于 `:2131` 的 `create_subagent`），节点自身即被钳制，探针 P4 实测。 |
| **4.1–4.11 回归测试** | 已验证（含真假保护判定） | 实跑 `17 passed`；变异验证见下节。**4.3 的自认是诚实的**：该用例在 defect 实现下也确实为绿（我实测复核），作者已在 docstring 与 change 文档中明确标注为「护栏而非防假保护」。 |
| **5.1–5.5 spec 同步与文档影响** | 已验证，1 条未提交（见 Issue #6） | delta 已合并进 `openspec/specs/subagents/spec.md`、`openspec/specs/multi-agent-collaboration/spec.md`；`docs/known-debt.md` 两项残留登记到位；`workflow-events.jsonl` 有 3 条结构化事件（2 条 `current_spec_synced` + 1 条 `protected_artifact_explained`），满足受保护 artifact 的解释事件要求。 |
| **6.1–6.5 验证与收尾** | 已验证 | 见「实跑输出」。 |
| **6.6–6.9 审阅 / manifest / 归档 / 关 issue** | 未验证（结构上属本审阅之后） | 6.6 即本文件；6.7/6.8 待 `tasks.md` 最终化后执行；6.9 已正确标注 `(post-merge)`。 |

---

## Issues

### 必须修（阻塞 PASS）

**无。**

### 观察项

#### Issue #1（中）挂载 A 在「既有 session 重跑」路径上会把上限**放宽**一级，且该放宽会传播给新派生的孙辈

- **位置**：`agent/loop.py:553-554`（挂载 A 直接取 `self.runtime_state.current_mode`，未与 `previous_ceiling` 取 min）
- **期望**：本 change 的目标是「子孙上限逐层收紧」。子 session 重跑时，其 loop 的 `runtime_state.current_mode` 是**创建期冻结**的 mode，可能比当前会话上限更宽。
- **实际**（探针 `/tmp/probe255review/probe_widen.py`，实测输出）：
  ```text
  冻结的 session mode          = build      （创建时 ambient ceiling = bypass）
  重跑期间 ambient ceiling     = read_only
  重跑期间派生的孙辈被授予     = build      ← 越过当前会话上限（fail-open）
  ```
  **同一探针在 defect 实现下给出完全相同结果** ⇒ **不是本 change 引入的回归**，而是既有残留（`design.md` Non-Goals 已登记「既有 session 重跑不重新钳制 mode」，`docs/known-debt.md` 亦已留痕）。
- **为什么仍要报告**：登记口径是「该 session 自身保留冻结 mode」，而实测的**外显面更大**——上限经由挂载 A 写进执行上下文后，该 session 运行期内**新派生的任意子孙**都继承这个更宽的值，而不是只影响它自己。
- **建议**（非阻塞，可留作 follow-up）：在 `loop.py:554` 把挂载 A 写成**只收窄**形态：
  ```python
  snapshot = self.runtime_state.current_mode
  if previous_ceiling is not None and <权限序>(previous_ceiling) < <权限序>(snapshot):
      snapshot = previous_ceiling
  set_mode_ceiling(snapshot)
  ```
  或在 `_clamp_mode` 之外补一处「既有 session 重跑按当前上限重钳」的收口（后者属 `known-debt.md` 已登记的 follow-up，不在本 change 爆炸半径内）。

#### Issue #2（低→中，判定项）挂载 B 在当前形态下**不可测**（outcome-idempotent）

- **位置**：`agent/subagent/scheduler.py:2125` / `:2148`
- **独立验证**：我把挂载 B 的 set/reset 整体替换为 no-op（变体 `noB`），**作者 17 条测试与我的 18 条独立探针全部保持全绿**（见下节）。作者在 `design.md:124-127` 也自认「无回归覆盖」。
- **为什么确实不可测（我独立推导 = 作者的论证）**：设会话上限 `R`、节点声明 `m`。挂载 B 把上限压到 `min(m, R)`，而紧随其后的 `create_subagent(mode=m)` 内 `_clamp_mode(m)` 本来就是 `min(m, R)`，再取一次 min 得同值 ⇒ **节点自身**不变；**其后代**的上限由子 loop 的挂载 A 决定（`set(session.mode)` = `min(m, R)`），也与挂载 B 无关。
- **判断：保留。** 理由：(a) 它是一次无害的 `set` + `finally reset`，无性能与正确性代价；(b) 它把「派发即收窄」这一不变量显式化在派发边界上，读者不必从 `create_subagent` 内部反推；(c) 它是 #245「scheduler 可读的会话上限通道」在调度器侧的读写落点；(d) 对将来 `create_subagent` 钳制逻辑的改动提供纵深防御。**同时要求口径诚实**：本 change **不声称**它被测试保护——`design.md:127` 已做到这一点，我认为可以接受。
- **若维护者坚持「不可测的代码不保留」**：删除挂载 B 也不会使任何测试变红（我实测），`effective_mode()` 仍作为 #245 公共通道保留。这是产品取舍，记于此。

#### Issue #3（低）`agent/subagent/scheduler.py:49` 的 `current_mode_ceiling` 是**未使用导入**

- **证据**：`rg -c 'current_mode_ceiling' agent/subagent/scheduler.py` = 1（仅导入行）；调度器实际只用 `set_mode_ceiling` / `reset_mode_ceiling` / `manager.effective_mode`。
- **影响**：无行为影响；CI 未配置 lint 步骤，故不会红。
- **建议**：删除该行，或在调度器侧真正经它读取一次以获得对称性（不推荐为凑用法而引入无意义调用）。

#### Issue #4（低）挂载 A 的 `set` 位于 `try` 之外，恢复在 `finally` 之内

- **位置**：`agent/loop.py:553-554`（set 在 try 之前）vs `:582`（恢复在 finally）
- **期望 vs 实际**：若 `:553` 与 `:582` 之间、进入 `try` 之前的语句抛异常，上限不会被恢复。实际风险极低——中间只有两次属性赋值与一次 `set_sandbox_sink`，且**既有**的 `_active_on_event` / `_active_trace_recorder` 用完全相同的形态（assign 在 try 外、restore 在 finally），本 change 与既有风格一致。
- **建议**：不改（保持与既有风格一致优于单点加固）；若将来统一改造，应连同既有三项一起处理。

#### Issue #5（低）`mode_ceiling()` 在本 change 内**无生产调用方**

- **位置**：`agent/subagent/manager.py:1615-1623`
- **事实**：生产代码对它的调用为 0（唯一消费者是 `tests/agent/subagent/test_mode_ceiling.py`）；调度器实际用的是 `effective_mode()`。
- **判定：不构成冗余。** 它是 spec 中「系统 SHALL 提供一个只读访问器」的交付物（`specs/subagents/spec.md:32-38` 的 Scenario「提供 scheduler 可读的上限通道」），也是 #245 Q11 的显式前置契约。作为**跨 change 契约**保留是正当的；`_parent_mode()` 与它的关系（一对一转发）也足够直观。

#### Issue #6（低）`docs/agent-internals.md` 的文档更新**未提交**

- **事实**：`git diff --name-only HEAD` 显示工作区有一处未提交修改，内容为在 `_clamp_mode` 一节后补充「基准口径（issue #255）」段落（对应 tasks 5.3 的文档影响检查）。
- **影响**：`c3d482e` 的提交不含该文档更新；同一 worktree 内有另一 agent 在运行，这处改动归属与去留需由主 session 判定。
- **建议**：若要保留，请纳入本 change 的提交并复核其措辞与实现一致（我读过该段内容，与实现口径一致）；若属其它 agent 的在途改动，请在归档前确认其不污染本 change 的 diff。

---

## 实跑命令与输出

### 1. 目标测试文件

```text
$ uv run pytest tests/agent/subagent/test_mode_ceiling.py -q
17 passed in 1.45s
```

### 2. 稳定度（flake 检查，连跑 8 次）

```text
$ for i in $(seq 8); do uv run pytest tests/agent/subagent/test_mode_ceiling.py -q | tail -1; done
17 passed in 1.58s / 1.53s / 1.50s / 1.51s / 1.51s / 1.49s / 1.54s / 1.48s
```

无抖动；用例使用真实 `asyncio.Event` + `wait_for(timeout=5)`，不依赖本机环境（用 `tmp_path`，无 `/tmp` 硬编码）。

### 3. subagent 子集 & 全量

```text
$ uv run pytest tests/agent/subagent/ -q
557 passed in 23.38s

$ uv run pytest -q
2 failed, 3284 passed, 9 skipped, 77 warnings in 346.88s (0:05:46)

FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```

这两条失败是**本机环境坑、与本 change 无关**：本机 `/tmp` 本身是一个 git 仓库（`ls -d /tmp/.git` 命中），`_find_scope_root` 从 `/tmp/pytest-of-happy/...` 向上走会命中的 `/tmp/.git`，于是 `assert ... is None` 失败。证据链：(a) 这两个文件不在本 change 的 diff 内（`git diff 5752ca0..HEAD --name-only | grep persistent` 无输出）；(b) 失败断言的实际返回是 `PosixPath('/tmp')`，即向上走到了 `/tmp`。

### 4. 门禁

```text
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)

$ uv run python scripts/check_openspec_artifacts.py --base-ref 5752ca0
OpenSpec artifact checks passed

$ uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke --source-repo . \
    --runs-dir /tmp/gate255 --baseline benchmarks/baseline.json --require-baseline --skip-p95
BENCHMARK GATE
  success_rate: baseline=1.0000 current=1.0000 delta=+0.0000
  result: PASS

$ uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke255
Tasks: 72 | passed: 5 | warnings: 0 | unsupported: 38 | failed: 29
```

（benchmark smoke 的 5 passed / 29 failed 为 `--agent fake` 的既有基线形态，非本次变更引入；CI 真正的门是上面的 `benchmark-gate`，PASS。）

### 5. Spec 首行 `SHALL` 校验（脚本实读，非人工目测）

```text
--- specs/subagents/spec.md
  L7: 系统 SHALL 从**当前执行上下文的上限**推导子 agent 的有效 mode，...   SHALL in first non-empty line: True
--- specs/multi-agent-collaboration/spec.md
  L7: 系统 SHALL 让 workflow 节点的**有效** mode 等于 `min(...)`，...     SHALL in first non-empty line: True
```

两条 ADDED Requirement 覆盖 O1–O5：O1（嵌套/逐层收紧 → Scenario「节点自身的收窄随上下文传播到子孙」+「子孙继承父节点的有效 mode」）、O2（run 起点快照 → Scenario「会话上限在 run 起点快照」）、O3（保守回落 → Scenario「上限缺失时回落到保守的静态下界」+「提供 scheduler 可读的上限通道」）、O4（机制归属 → Requirement 正文首句「SHALL NOT 从任何跨 run 共享…可变状态推导」）、O5（派发点 + 不破坏收尾 → Scenario「执行上下文上限的 set 不破坏运行收尾」）。

---

## 独立探针（自写，不 import 作者测试）

脚本 `/tmp/probe255review/mine_probe.py`，18 条断言，全部经**真实 `AgentLoop.run` + 真实 `SubAgentManager` + 真实 `WorkflowScheduler`** 驱动：

```text
P1 fail-open sequence + dual
  [PASS] P1a build 会话 ⇒ build 节点得 build（不是无差别压低）
  [PASS] P1b 只读会话 ⇒ build 节点收窄为 read_only（#255 原时序 fail-open 已修）
P2 跨图污染
  [PASS] P2a 图 1 的 read_only 节点仍 read_only
  [PASS] P2b 图 2 的 build 节点未被图 1 静默降级
P3 直接 spawn 链（root=bypass → child(build) → grand(不声明)）
  [PASS] P3a child 得 build
  [PASS] P3b grand 继承 child 的**有效** mode（build），不是 root 的 bypass
P4 workflow 路径 (a)：bypass 会话 + 声明 read_only 的节点
  [PASS] P4 节点自身被收窄为 read_only
P5 直驱调度器（不经 loop）
  [PASS] P5a 回落到静态 parent_mode（read_only），非无界
  [PASS] P5b 显式上限覆盖静态回落（sanity）
P6 run 退出后的上限复原
  [PASS] P6a 正常返回后 ceiling == None
  [PASS] P6b 抛异常后 ceiling == None
  [PASS] P6c 被 cancel 后 ceiling 复原，且无 ValueError
  [PASS] P6d 同 task 内后续直驱仍保守（read_only）
P7 并行兄弟，两种构造序
  [PASS] ('bw','ro') 与 ('ro','bw') 均得 {bw: build, ro: read_only}
P8 resume 路径
  [PASS] P8a resume 到 read_only 后，派发前 ceiling 已是 read_only
  [PASS] P8b resume 后的 run 把 build 节点钳为 read_only
  [PASS] P8c resume run 退出后 ceiling 复原
==== 18/18 checks passed ====
```

附加两个判别性探针：`probe_pathB.py`（路径 b 在两种 `parent_mode` 下的可区分性）、`probe_widen.py`（Issue #1）。

---

## 变异验证结果

**方法**：因同一 worktree 另有 agent 在跑、且禁止改动仓库文件，我用 `PYTHONPATH` + `-p probe_plugin` 在**运行时**替换符号（`/tmp/probe255review/probe_plugin.py`），实现了 5 个变异体。**未对仓库任何文件做增删改**，故不存在污染工作区的风险。

| 变体 | 做了什么 | 作者 17 条测试 | 我的 18 条独立探针 |
|---|---|---|---|
| `fixed` | 无（基线） | **17 passed** | **18/18 PASS** |
| `defect` | `AgentLoop.__init__` 重新写入共享 provider，`_parent_mode` 优先读它（等价于修复前的缺陷形态） | **4 failed** / 13 passed | **15/18**（P1b / P2b / P5b 红） |
| `noA` | `agent.loop.set_mode_ceiling` 置为 no-op（挂载 A 整体失效） | **4 failed** / 13 passed | **15/18**（P1b / P8a / P8b 红） |
| `noB` | `scheduler.set_mode_ceiling` / `reset_mode_ceiling` 置为 no-op（挂载 B 整体失效） | **17 passed（全绿）** | **18/18（全绿）** |
| `A_norestore` | 挂载 A 只 set、不恢复（模拟被 grill 否决的「不清理」形态） | **2 failed** / 15 passed | **12/18**（P5a / P6a / P6b / P6c / P6d / P8c 红） |
| `noA_noB` | 两处挂载都失效 | **4 failed** / 13 passed | **15/18** |

**结论**：

1. **`defect` 变体必红** ⇒ 测试确实在保护修复，不是「改不改都绿」的空壳（符合 `design.md:235` 的验证判据）。特别是 issue #255 的**原始** fail-open 时序用例（`test_failopen_sequence_run_then_switch_then_dispatch_stays_readonly`，`test_mode_ceiling.py:147`）与跨图静默降级用例（`:336`）在 defect 下变红 —— 这两条是**有意义**的判别性用例。
2. **`A_norestore` 变体被显著捕获**（6 条红、含「run 退出后 ceiling 未恢复」）⇒ 挂载 A 的 `set(prior)` 恢复形态确实被回归锁住，`design.md` 高危订正项已落实。
3. **`noB` 变体一条都不红** ⇒ 挂载 B 是 outcome-idempotent 的防御性冗余，**独立证实**了作者在 `design.md:124-127` 的自述（见 Issue #2 的保留判断）。
4. **`noA` 下 `test_workflow_node_effective_mode_bounds_the_node_itself`（路径 a）仍绿**，与我的 `probe_pathB.py` 一致 —— 因为路径 a 的节点自身收窄由挂载 B + `create_subagent` 的 `_clamp_mode` 完成。**我进一步验证了路径 (b) 的可区分性**：只有当静态 `parent_mode` **宽于**节点声明 mode（`parent_mode=bypass`、`child=build`）时，`noA` 才把 `grand` 从 `build` 误判为 `bypass`：
   ```text
   variant=fixed  parent_mode=build   -> {'child': 'build', 'grand': 'build'}  OK
   variant=fixed  parent_mode=bypass  -> {'child': 'build', 'grand': 'build'}  OK
   variant=noA    parent_mode=build   -> {'child': 'build', 'grand': 'build'}  OK
   variant=noA    parent_mode=bypass  -> {'child': 'build', 'grand': 'bypass'} BAD
   ```
   作者的 `test_direct_spawn_chain_inherits_parent_effective_mode`（`test_mode_ceiling.py:246`）用的正是 `_manager(...)`（默认 `parent_mode=AgentMode.BUILD`）+ root loop `BYPASS`，即**恰好落在可区分的那个配置上**——这条用例设计正确，不是偶然绿。✅

---

## 重点挑战项的逐条回答

1. **mode 钳制双向正确性**：✅ 自写用例验证（P1a/P1b/P4/P7）。只读会话 + `build` 节点 ⇒ `read_only`；build 会话 + `build` 节点 ⇒ `build`（未被无差别压低）。
2. **contextvar 恢复形态**：✅ 挂载 A 用 `set(prior)`（`loop.py:582`，非 reset）；取消/异常/正常三条路径均不抛 `ValueError` 且不留陈旧上限（P6a/b/c）。挂载 B 为 `set` + `finally reset`（`scheduler.py:2125/2148`）。执行点**确实没有** reset（`manager.py:992-1003` 零 `reset_*`）。
3. **跨会话泄漏是否堵住**：✅ P6d 自写探针复现了 grill 的高危场景（同 task 内先跑 build 会话的 `AgentLoop.run`，再直驱 `parent_mode=read_only` 的 `WorkflowScheduler.run`），节点声明 `build` ⇒ 得 `read_only`。`A_norestore` 变体下这条**变红**，证明它确实是有效回归。
4. **测试是否经真实 `AgentLoop.run` 驱动**：✅ 全部 7 条会产出 mode 差异的用例都经真实 `root.run([...])`，hook 挂在 LLM 的 `chat` 里（`test_mode_ceiling.py:105-113`），未用 mock 手工 set 上限。变异验证（上表）证实这些用例真能区分 defect/fixed。唯一例外是通道回落用例（`:356`），它按定义不经过 loop，属设计允许的例外。
5. **嵌套两条路径**：✅ (a) `scheduler.py:2125` 在 `create_subagent` 之前 set，节点自身被钳；若静态 `parent_mode` 宽于节点声明，孙辈靠挂载 A 继承节点有效 mode。(b) P3 实测 `grand=build`。**grill 的订正被采纳**：回归测试用的是可达例子（root=`bypass`、`child=build`、`grand` 不声明），**没有**使用「`read_only` 子 agent 再起子 agent」这一默认权限下不可达的场景（`test_mode_ceiling.py:245-279` 与 tasks 4.4 的措辞一致）。
6. **删除 `parent_mode_provider` 的影响面**：✅ 生产代码零残留；`benchmarks/tasks/**/*.patch` 与 `docs/openspec-change-backlog.md` 的命中均为历史基线/历史引用，tasks 2.6 已显式排除，**无害**。
7. **Spec 对齐**：✅ 两条 ADDED Requirement 覆盖 O1–O5；首行含 `SHALL`（脚本实读）；`validate --all --strict` 29/29 通过。
8. **冗余度 / 可维护性 / 挂载 A 两处 set 自洽**：✅ 命名与注释贴合既有风格（中文注释解释约束、引用 issue 号）。`run()` 与 `_run()` resume 分支两处 set 自洽：resume 改 mode 时重快照（`loop.py:610-615`），不变时不重设也正确（ceiling 已等于 `current_mode`）——P8 实测覆盖。`mode_ceiling()` / `effective_mode()` 的必要性见 Issue #5。
9. **CI 完整性**：✅ 文件位于 `tests/agent/subagent/`（`testpaths=["tests"]`）且 CI 无路径排除，会被收集；`asyncio_mode=auto` 生效；8 次连跑无抖动；不依赖 `/tmp` 是/不是 git 仓库（用 `tmp_path`）；无浏览器依赖。
10. **横向同类潜伏缺陷**：除 change 已登记的两项（`RunSubagent` 不重钳、`loop` 复用 `runtime_state`）外，我另扫了 `SubAgentManager` / `AgentLoop` 上由构造期写入的实例字段：`llm` / `config` / `workspace_policy` / `cost_ledger` / `sandbox` / `max_active` / `max_depth`。其中 `configure_runtime` 仍会写 `llm` / `config` / `workspace_policy`（`manager.py:534-546`），但**唯一调用点 `loop.py:154` 只传 `llm`**，且子 loop 复用同一 manager 时传入的 `llm` 与既有值同源（幂等）⇒ **无可达覆写**。`max_active` / `max_depth` 仅在构造期赋值、无写入通道 ⇒ 无同类缺陷。**未发现新的生产可达同构缺陷**。

---

## 结论

**可以进入 PR。** 修复正确、与已确认的 O1–O5 一致、回归有效（变异验证可区分），三道门禁全绿。下列收尾事项建议在提 PR 前处理：

1. 处理 `docs/agent-internals.md` 的未提交改动（纳入提交或确认归属），确保本 change 的 diff 自洽（Issue #6）。
2. 顺手删除 `agent/subagent/scheduler.py:49` 的未使用导入（Issue #3）。
3. 在 `tasks.md` 6.6–6.8 完成后生成 review manifest（**必须在 `tasks.md` 最终化之后**），再执行归档。
4. Issue #1（挂载 A 在既有 session 重跑路径上放宽一级）**不阻塞本 change**——它与 defect 实现行为一致、属已登记 Non-Goal；建议作为 follow-up 处理，并考虑把 `design.md` / `docs/known-debt.md` 的登记口径从「该 session 自身保留冻结 mode」扩写为「该 session 运行期内新派生的子孙也继承该冻结 mode」，以如实反映外显面。
5. Issue #2（挂载 B 不可测）保留现形态，`design.md` 已如实标注无回归覆盖；若维护者要求「不留假保护」的更强口径，删除挂载 B 亦不破坏任何测试。
