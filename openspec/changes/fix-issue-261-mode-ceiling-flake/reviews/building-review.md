# Building Review: fix-issue-261-mode-ceiling-flake

- reviewer: 零记忆独立 subagent（未参与设计/实现）
- base sha: `ee06df7`　head sha: `574d6a6`
- 审阅时间: 2026-09-29
- 审阅方式: 全部结论基于亲自运行（含变异验证）与 `文件:行号` 级代码核读；未采信作者结论。

## Verdict

**PASS**

修复是**真实的语义修复**，不是「放宽断言 / 加重试」式的假修复：

- 生产改动是 `set(previous)` → 守护式 `reset(token)`（`agent/loop.py:575` / `:603-611`），
  断言本身**未改**（`tests/agent/subagent/test_mode_ceiling.py:583` 仍是 `assert modes["bw"] == "read_only"`）；
- 回归测试**确定性**（显式 `gc.collect()` 把 GC 终结钉进脆弱窗口，无 sleep 等待失败、无重试、无并发加压）；
- **变异验证成立**：我把 `agent/loop.py` 还原为 base 版本后，该用例**确实变红**，且失败形态与 CI 逐字一致
  （`AssertionError: assert 'build' == 'read_only'`）；还原后 20/20 绿。测试对实现敏感，不是假保护。
- 真实路径 A/B 亲自复现：base 树 **5/5 REPRODUCED**、修复树 **5/5 CLEAN**（与作者声称一致）。
- 门禁全绿：OpenSpec strict validate 29/29、artifact checker `--base-ref ee06df7` 通过、
  `tests/agent/subagent/` 640 passed、全量 3405 passed（仅 2 条既有环境坑失败，见下）。

遗留 2 条非阻塞 follow-up（一个同源载体未修且未立跟踪 issue、一个测试命名遮蔽），不构成对本 change 正确性的否定。

> **工作区已还原**：变异验证期间改过 `agent/loop.py`，已用备份还原，`git diff --exit-code` 为空、`git status --porcelain` 为空、sha256 与 HEAD 一致。

## Task Verification

| # | 任务 | 结论 | 独立证据 |
|---|------|------|---------|
| 1.1 | 复现 CI 失败 | ✅ 等价复现成立（原始并发读数已被作者自我作废） | `repro/realpath_ab.py` 在 base 树 5/5 REPRODUCED |
| 1.2 | 否证测试侧「断言太早」假设 | ⚪ 采信（未独立重跑延迟注入实验） | 我的独立证据方向一致：断言对实现敏感（变异必红） |
| 1.3 | 钉死机制（GC 终结跨上下文展开 finally） | ✅ **已独立验证** | `min_repro_261.py` exit 1；`carrier_stack.py` 栈证明 |
| 1.4 | 对照实验（cancel 不污染 / GC 终结污染） | ✅ 已独立验证 | 我的 `ContextVar.reset` 语义探针结果一致 |
| 1.5 | 最小脚本 + 真实路径脚本 + A/B 记录 | ✅ **已独立验证** | base 5/5 REPRODUCED → 修复 5/5 CLEAN（亲自跑） |
| 2.1 | 新增回归用例 | ✅ 存在且通过 | `test_mode_ceiling.py:566-585` |
| 2.2 | **先跑红** | ✅ **已独立验证** | base 树下该用例失败，形态与 CI 一致 |
| 2.3 | **变异验证** | ✅ **已独立验证** | 改回 `set(previous)` → 变红；还原 → 20/20 绿 |
| 3.1 | run 起点 token 化 | ✅ | `agent/loop.py:575` |
| 3.2 | `finally` 守护式 reset | ✅ | `agent/loop.py:603-611` |
| 3.3 | 删 `previous_ceiling` + 收窄 import | ✅ | grep 零命中；`agent/loop.py:42` |
| 3.4 | 就地注释 | ✅ | `agent/loop.py:563-574` |
| 4.1 | `sandbox_sink_repro.py`（形态 A） | ✅ 已复跑，exit 1 复现 | 见 Evidence |
| 4.2 | `sandbox_sink_misroute.py`（形态 B + 对照） | ✅ 已复跑，exit 1 复现 | 见 Evidence |
| 4.3 | 结论「能复现且可观测」 | ✅ 属实 | 两脚本均确定性复现 |
| 4.4 | 不改 `set_sandbox_sink` | ✅ 属实（diff 未触及） | 但**无跟踪载体**，见 Issue 1 |
| 5.1 | `test_mode_ceiling.py` | ✅ 18 passed | 亲自跑 |
| 5.2 | `tests/agent/subagent/` | ✅ 640 passed | 亲自跑 |
| 5.3 | 全量 `pytest -q` | ✅ 如实记录 | 3405 passed / 2 failed（既有环境坑，见下） |
| 5.4 | benchmark smoke | ⚪ **未核验**（本审阅未跑） | — |
| 5.5 | OpenSpec strict validate | ✅ 29 passed, 0 failed | 亲自跑 |
| 5.6 | artifact checker `--base-ref ee06df7` | ✅ `OpenSpec artifact checks passed` | 亲自跑 |
| 5.7 | 同步 current spec | ✅ **未完成是正确的** | 见 Spec 对齐节 |
| 6.1 | 独立审阅 | ✅ 本报告即产出 | — |
| 6.2 | review manifest | ✅ 未完成（正确：须在 tasks.md 最终化后生成） | — |
| 7.1–7.4 | 收尾项 | ✅ 未完成（正确，在途） | — |
| 7.5 | 关闭 issue（`post-merge`） | ✅ 已正确标注 `(post-merge)`，符合 #235 门禁 | `tasks.md:77` |

5.3 的 2 条失败：`tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}`。
根因已核实 = **本机环境坑**：`/tmp/.git` 是个空目录，`_find_scope_root` 到 `/tmp` 就停住
（失败信息 `assert PosixPath('/tmp') is None`）。该文件（`agent/memory/persistent.py`）**不在本 change diff 内**，
与本 change 无关；tasks.md 5.3 已预先如实记录该环境坑。

## Issues

### 1.［中］`set_sandbox_sink` 同源缺陷：确认复现，但既未修、也无跟踪载体

`agent/loop.py:602` 的 `set_sandbox_sink(previous_sandbox_sink)` 与挂载 A 是**同一个 `finally` 里同形态的裸
`ContextVar.set`**（`agent/sandbox_events.py:36-46`：默认 `_NOOP`，只有 `set` 没有 token/reset 版本），
由**同一条** GC 迟后终结路径执行。我复跑两个脚本均确定性复现（exit 1）：

- 形态 A（`sandbox_sink_repro.py`）：活跃 run 的 sink 被清成 `_NOOP` → 其 sandbox 事件**静默丢失**（LIVE trace 收 0 条）；
- 形态 B（`sandbox_sink_misroute.py`）：事件**串写进旧 run 的 trace**（LIVE 0 条 / OLD 1 条）。

**范围取舍本身是合理的**（独立载体、独立复现、独立回归，不该硬塞进 mode 上限这个 bugfix）。
问题在于**没有跟踪载体**：`gh issue list --search "set_sandbox_sink"` 无果，`docs/openspec-change-backlog.md`
不含本 change 也不含该缺陷，`docs/known-debt.md` 未改（diff 未触及 `docs/`）。证据目前只落在本 change 的
`diagnosis.md` + `repro/`，虽随归档保留在仓库内（可检索性尚可），但**不会进入 issue 队列**，容易被漏掉。

**建议（非阻塞）**：合入前后开一个 follow-up issue（标题沿用「【bug】`set_sandbox_sink` 的跨上下文收尾污染后续 run 的
sandbox sink：事件静默丢失 / 串写」），并在其中引用本 change 归档路径的两个复现脚本。
若愿意并入本 change，则需注意 `set_sandbox_sink` 的调用在 `if trace_recorder:` 门控内、而恢复是无条件的
（`agent/loop.py:578-582` vs `:602`）——「未 set 过却要 reset」的分支需一并处理（作者已在 `diagnosis.md` 指出）。

### 2.［低］测试文件内 `_CHILD_TASK` 被模块级重复定义（命名遮蔽）

`tests/agent/subagent/test_mode_ceiling.py:95` 定义 `_CHILD_TASK = "__CHILD_SPAWN_GRAND__"`；
`:495` 又把它重新绑定为 `"__CHILD_HANG__"`。由于模块体在 import 时全部执行，
第 249 行的用例（`:263`）在运行期读到的是**后者**。

当前**功能无害**：写标记（`:268`）与读标记（`:263`）是同一次全局读取，内部自洽；我已单独复跑该用例通过。
但两个语义完全不同的标记共用一个私有名字，离「一次局部重构引入真 bug」只差一步（例如将来只改一处字面量）。

**建议**：把 `:495` 的标记改名为 `_CHILD_HANG_MARKER`（或把 `:95` 的改为 `_GRAND_SPAWN_MARKER`），与本 change 的实现无耦合，改动很小。

### 3.［低］`except ValueError` 的收窄性依赖一个隐含前提（当前成立，仅作记录）

我实测了 `ContextVar.reset(token)` 的三类异常：

- 跨 Context → `ValueError`（"was created in a different Context"）← **目标情形**
- 跨 ContextVar → `ValueError`（"was created by a different ContextVar"）
- token 复用 → `RuntimeError`（"has already been used once"）← **未被捕获，正确**

在本代码里 token 由 `agent/loop.py:575` 自己创建、`finally` 每次 run 至多执行一次，因此**唯一可达**的 `ValueError`
就是跨上下文这件事——**不构成现实掩盖**。仅提示：`pass` 会把「将来有人误传 token」也一并吞掉，
现有注释已充分解释意图，属可接受。

### 4.［低］本 change 尚未登记进 `docs/openspec-change-backlog.md`

仓库规则要求非占位 change 进队列（同一时刻的另一个 active change `add-minimal-tui-runtime-view` 已登记）。
`tasks.md:74`（7.2）已列此项，属**诚实的在途状态**，非违规。提醒收尾时补上，且该写入是受保护路径，
需 `workflow-events.jsonl` 结构化解释事件。

## Correctness 深究（审阅维度 2/3/4 的独立结论）

**改动是否真的消除缺陷？** 是。机制链已由三条独立证据闭合：

1. `min_repro_261.py`（Python **3.11.15 与 3.12.13 均** exit 1）——纯 contextvar + Task 生命周期，不依赖生产类；
2. `carrier_stack.py` 捕获到遗留 run 的 `finally` 栈里出现
   `base_events._run_once → events.py:84 _run → carrier_stack.py:42 later → gc.collect`，
   且该 `finally` 内 `current_mode_ceiling()` 读到的**是活跃 run 的 `read_only`**（非它自己的 `build`）——
   直接证明这段收尾跑在**调用方上下文**里；
3. 生产代码本身就有记载：`agent/subagent/manager.py:1008-1011` 的既有注释写着
   「a reset in ``finally`` would itself raise when the task is torn down outside its context
   (``GeneratorExit`` during ``Task.__del__``)」——本 change 正是把这条既知约束落到了挂载 A 上。

**是否引入回归？** 我逐条核验了三条风险路径，均无回归：

- **同上下文恢复**：`reset(token)` 复原的是 token 记录的「那次 set 之前」的值，与旧 `set(previous_ceiling)` 语义等价。
  `test_run_exit_restores_ceiling_so_later_direct_drive_stays_conservative` 通过。
- **取消路径**：`cancel()` 把取消投递进 task **自己的**上下文，`reset` 不抛。
  `test_cancelled_run_does_not_raise_and_restores_ceiling` 通过。
- **resume 路径二次 set**（`agent/loop.py:644`）：我专门探针验证了「token 创建后、同上下文内又发生一次 set」的情形——
  `reset(outer_token)` **正确复原到 run 之前的值**（而非中间那次），语义与旧实现一致，无回归。
- **跨上下文情形**：`reset` 抛 `ValueError` → 跳过。此处**跳过是正确的、不是泄漏**：被遗留 task 的上下文已随其
  Context 消亡，那次 `set` 写的值本来就在一个死掉的 context 副本里，无需（也不该）在当前上下文清理。

**Spec 对齐（维度 3）**：`specs/subagents/spec.md` 的 MODIFIED delta 经我逐字比对——

- 第 7 段（原 Requirement 正文）与 `openspec/specs/subagents/spec.md` 现状**逐字一致**，属真正的 MODIFIED 而非
  借 MODIFIED 夹带 ADDED；
- 新增句（`:9`「该上限 SHALL 只对其所属执行上下文生效…SHALL NOT 写入任何**其它**执行上下文」）与新增 Scenario
  （`:49-55`「被遗留 run 的迟后收尾不改变活跃 run 的上限」）与实现一致，且**确有必要**：
  既有 Scenario「执行上下文上限的 set 不破坏运行收尾」（`:42-47`）只约束 run **自身**终态一致，未表达
  「已死 run 的收尾不得改写**另一个**活跃 run 的上限」这条不变量。
- 我核验 `openspec/specs/subagents/spec.md` **尚不含**该新增句与 Scenario → 5.7 未勾是**正确的**（收尾时同步）。

**测试覆盖（维度 4）**：`test_mode_ceiling.py:566-585` 的确定性来自**显式 `gc.collect()` 把终结钉进脆弱窗口**，
而非等待失败。我另行验证该用例的 setup 不脆弱：把 `_plant_abandoned_pending_run` 里的 `sleep(0.05)` 降到 `0`
仍 20/20 到达挂载 A——即那个 sleep 不是承重的，测试不依赖时序宽容。变异验证见 Verdict。

**冗余度/可维护性（维度 6）**：`previous_ceiling` 已删净（`agent/loop.py` 内 grep 零命中）；
import 已收窄为 `reset_mode_ceiling, set_mode_ceiling`（`:42`），`current_mode_ceiling` 在 `loop.py` 内已无消费者；
新注释 14 行虽长，但陈述的是代码本身无法表达的约束（GC/`GeneratorExit`/ContextVar 上下文语义），符合「注释只写约束」的口径。

**CI 完整性（维度 8）**：strict validate 29/29、artifact checker 通过、全量 pytest 仅剩 2 条与本 change 无关的环境坑失败（已核验）。

## Evidence

以下命令均在 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 后运行。

```
# 1. 最小复现（应 exit 1）—— 作者声称确定性；已亲验
$ .venv/bin/python openspec/changes/fix-issue-261-mode-ceiling-flake/repro/min_repro_261.py
Python 3.11.15
  abandoned task alive before later test: True
    [later test] mount A installed: ceiling = <AgentMode.READ_ONLY: 'read_only'>
    [abandoned-run] finally ran; ceiling here = <AgentMode.READ_ONLY: 'read_only'> -> writing None
    [later test] ceiling now     : None
    [later test] node would freeze as: build
>>> REPRODUCED: live read_only ceiling was clobbered; node froze as 'build' (expected 'read_only')
EXIT=1
# 同一脚本在 python3.12.13 + PYTHONPATH=. 下同样 REPRODUCED（版本无关性成立）

# 2. 真实路径 A/B —— 修复树
$ for i in 1..5: .venv/bin/python .../repro/realpath_ab.py
Python 3.11.15  node 'bw' frozen as: 'read_only'  (expected 'read_only')
>>> CLEAN: ceiling preserved            (5/5, EXIT=0)

# 3. 变异验证：把 agent/loop.py 还原为 ee06df7 版本（备份→改→跑→还原）
$ git show ee06df7:agent/loop.py > agent/loop.py
$ for i in 1..5: .venv/bin/python .../repro/realpath_ab.py
Python 3.11.15  node 'bw' frozen as: 'build'  (expected 'read_only')
>>> REPRODUCED: live read_only ceiling clobbered by an abandoned run's restore   (5/5, EXIT=1)

$ .venv/bin/python -m pytest tests/agent/subagent/test_mode_ceiling.py::test_abandoned_pending_run_teardown_does_not_clobber_live_ceiling -q
E       AssertionError: 遗留 run 的跨上下文收尾把活跃的只读上限清空了（节点被授予 build，fail-open）
E       assert 'build' == 'read_only'
FAILED ... 1 failed in 1.24s          # ← 失败形态与 CI 逐字一致
# 同树下整文件：1 failed, 17 passed（只有新用例变红，其余不受影响）

$ cp /tmp/loop_fixed_261.py agent/loop.py            # 还原
RESTORED sha256: c77ebcca...  (与 HEAD 一致)
$ git diff --exit-code agent/loop.py && echo OK      # OK
$ git status --porcelain                             # （空）

# 4. 还原后 20 次复跑新用例
PASS=20 FAIL=0 / 20

# 5. sandbox sink 两个载体（作者声称"能复现且可观测"）—— 已亲验，均 exit 1
$ .venv/bin/python .../repro/sandbox_sink_repro.py
  sink_before: 'TraceRecorderSandboxSink'   sink_after: 'NoopSandboxSink'
  LIVE trace 收到 sandbox 事件: []
>>> 复现：遗留 pending run 的跨上下文收尾覆盖了后续 run 的 sandbox sink（-> NoopSandboxSink）
EXIT=1
$ .venv/bin/python .../repro/sandbox_sink_misroute.py
  LIVE recorder sandbox steps : []
  OLD  recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
>>> 串写复现：LIVE run 的 sandbox 事件落进了 OLD recorder 的 trace。   EXIT=1
# ⇒ 该缺陷在【已应用本 change 修复】的树上仍复现，确为独立载体，作者的范围声明属实

# 6. carrier_stack.py：证明 finally 由活跃上下文的 gc.collect 触发
        events.py:84 _run  | self._context.run(self._callback, *self._args)
        carrier_stack.py:42 later  | gc.collect()
        carrier_stack.py:20 agent_loop_run_shape  | st = traceback.extract_stack()
    [abandoned] ceiling here = <AgentMode.READ_ONLY: 'read_only'> (live ctx)

# 7. reset 语义探针（自建，验证 resume 二次 set 与跨上下文）
after outer set: AgentMode.BUILD
after mid set (resume): AgentMode.READ_ONLY
after reset(outer): None   <- 正确复原到 run 之前（resume 无回归）
cross-context reset: ValueError -> ... was created in a different Context
main ctx ceiling after: AgentMode.BUILD   <- unchanged = 修复生效
wrong-var token reset: ValueError        reused token: RuntimeError

# 8. 门禁
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)        EXIT=0
$ .venv/bin/python scripts/check_openspec_artifacts.py --base-ref ee06df7
OpenSpec artifact checks passed               EXIT=0
$ .venv/bin/python -m pytest tests/agent/subagent/test_mode_ceiling.py -q   → 18 passed
$ .venv/bin/python -m pytest tests/agent/subagent/ -q                        → 640 passed
$ .venv/bin/python -m pytest -q
2 failed, 3405 passed, 9 skipped in 346.40s
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
# 根因核实：/tmp/.git 是空目录（本机环境坑），assert PosixPath('/tmp') is None；
# 该文件不在本 change diff 内，与本 change 无关。

# 9. 工作区最终状态
$ git diff --exit-code >/dev/null && echo "worktree clean"   → worktree clean
```

## 停轮事项（需用户/主 session 处置，非本 reviewer 可决）

1. **是否开 `set_sandbox_sink` follow-up issue**（Issue 1）。本 reviewer 建议开，但不改本 change 范围——请主 session 拍板。
2. 本报告**不构成** review manifest。按 AGENTS.md，6.2 的 manifest 必须在 `tasks.md` 最终化（含归档 move）**之后**生成，
   由主 session 在收尾时执行。
