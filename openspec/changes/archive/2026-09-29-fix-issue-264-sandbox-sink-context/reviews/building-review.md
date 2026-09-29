# Building Review: fix-issue-264-sandbox-sink-context

- reviewer: 零记忆独立 subagent（未参与设计/实现；不采信作者任何结论）
- base sha: `7acde2b`　head sha: `a97d4f8`
- 审阅时间: 2026-09-29
- 审阅方式: 全部结论基于**亲自运行**（repro 脚本 / 基线置换 / 变异验证 / 门禁 / 自建 contextvars 探针）与
  `文件:行号` 级代码核读；关键论断均以我自己的原始输出为准。

## Verdict

**PASS**

这是一个**真实的语义修复**，不是「放宽断言 / 加重试」式的假修复，且证据链在**独立复现**下完全闭合：

- 生产改动是 `set_sandbox_sink(previous)` → 守护式 `reset_sandbox_sink(token)`
  （`agent/loop.py:587-589` 捕获 token、`:609-618` 守护式重置），`agent/sandbox_events.py:46-72`
  新增 `reset_sandbox_sink` 并把 `set_sandbox_sink` 改为返回 token（与 `context.py` 的
  `set_mode_ceiling`/`reset_mode_ceiling` 同形）。
- **两个 repro 脚本亲自复跑**：实现后均**未复现（exit 0）**；把 `agent/loop.py` 换成 base 版本后
  两者**均复现（exit 1）**——证明修复真的改变了行为，脚本不是本来就绿。
- **变异验证成立（我亲自做，两轮）**：① 整个 `loop.py` 换回 base → 新回归用例**变红**
  （`assert 0 == 1`，活跃 trace 收 0 条 sandbox 事件）；② 更严格的**外科式变异**——只把 `finally` 的
  `if sink_token is not None: reset_sandbox_sink(sink_token)` 换回 `set_sandbox_sink(previous_sandbox_sink)`
  （保留 HEAD 的 token 捕获）→ **同样变红**。还原后**变绿**，`git diff --exit-code` 为空、
  `git status --porcelain` 为空、三个文件的 sha256 与 HEAD 一致。
- **contextvars 语义核验（我自建探针，不采信注释）**：跨 Context `reset` 抛 `ValueError`
  （"was created in a different Context"）；token 二次消费抛 `RuntimeError`（"has already been used once"）
  ——`reset_sandbox_sink` docstring 的两句话**逐条属实**。
- 门禁全绿：OpenSpec strict validate **29 passed / 0 failed**、artifact checker `--base-ref 7acde2b`
  **passed**、`--check-archived` **passed**、CI benchmark-gate **PASS**；`tests/agent/subagent/` 710 passed、
  全量 `pytest -q` **3477 passed / 2 failed**（2 条为本机 `/tmp` 环境坑，见下）。
- 安全维度（本 change 的核心）：**形态 B「`denied` 事件串写进错误 trace」已被真正消除**——base 树上
  gcwindow 变体 10/10 复现（LIVE [] / OLD 1 条），HEAD 树上未复现。

无未解决的中等及以上问题。遗留 2 条**低**severity 的观察项（见 `## Issues`），不构成对正确性的否定。

> **工作区已还原核验（硬约束）**：变异验证期间两次改过 `agent/loop.py`、一次改过测试文件的
> `sleep(0.05)`。全部已还原：`git status --porcelain` 空、`git diff --exit-code` 空、
> `git diff --cached --exit-code` 空、`git rev-parse HEAD` = `a97d4f8`（与审阅基准一致）、
> `agent/loop.py` sha256 = `2c011d6a…`、`tests/agent/test_loop_sandbox_events.py` sha256 = `7d69b225…`
> 均与 HEAD 一致。**未留下任何改动，未 commit、未 push、未建 PR。**

## Task Verification

对照 `tasks.md` 逐条核验实现是否真实存在（读代码，不只看文件名）。
**归档类任务（第 6 节）此刻在途未勾是正确的**，不据此判红；第 5 节（审阅闭环）与 4.x 中
依赖「实现已完成」的项由我在本次审阅中亲自补跑后确认成立，但**是否由作者回勾由主 session 决定**
（见文末停轮事项）。

| # | 任务 | 结论 | 独立证据 |
|---|------|------|---------|
| 1.1 | 重跑形态 A（5/5 复现） | ✅ **已独立复核** | base 树 `sandbox_sink_repro.py` exit 1：`sink_clobbered: True`、`LIVE trace 收到 sandbox 事件: []`；HEAD exit 0 |
| 1.2 | 重跑形态 B，定位脚本 GC 脆弱 | ✅ **已独立复核** | `sandbox_sink_misroute.py` 我本体上 base/HEAD 均 exit 0（0/10 口径一致）；`.._gcwindow.py` base exit 1（`LIVE [] / OLD 1 条`）、HEAD exit 0 ⇒ 「脚本脆弱、缺陷不消失」属实 |
| 1.3 | 探针确认 finally 跑在活跃上下文 | ⚪ 采信（我未独立复造栈探针） | 与我的结论方向一致：变异后行为可观测（见 Verdict）；`design_points_probe.py` D3 段亲验 |
| 1.4 | 三个设计点留一手实测 | ✅ **已独立复核** | 亲跑 `repro/design_points_probe.py` exit 0，输出与 `diagnosis.md` §Evidence 4 逐字一致；我另建独立探针复验 D1/D2 结论 |
| 1.5 | 证据脚本归档到 `repro/` | ✅ | 4 个脚本 + `README.md` 均在树内，`README.md` 记录适配理由 |
| 2.1 | 新增确定性回归用例 | ✅ | `tests/agent/test_loop_sandbox_events.py:206-234`，15/15 稳定绿 |
| 2.2 | **先跑红** | ✅ **已独立复核** | 用 base `loop.py` 跑该用例：`AssertionError: … 活跃 trace 收到 0 条 sandbox 事件（应为 1）` |
| 2.3 | **变异验证** | ✅ **已独立复核** | 两轮变异均变红，还原后绿（见 Verdict） |
| 2.4 | 嵌套同上下文恢复断言 | ✅ | `tests/agent/test_loop_sandbox_events.py:237-273`，绿 |
| 3.1 | `set_sandbox_sink` 返回 token + docstring | ✅ | `agent/sandbox_events.py:46-55`，`-> Any` 与 `context.py` 约定一致 |
| 3.2 | 新增 `reset_sandbox_sink(token)` | ✅ | `agent/sandbox_events.py:58-72`，转发 `_current_sink.reset(token)` |
| 3.3 | run 起点 `sink_token = None` / 门控捕获 | ✅ | `agent/loop.py:583` / `:587-589` |
| 3.4 | `finally` 守护式 reset + `except ValueError` | ✅ | `agent/loop.py:609-618` |
| 3.5 | 删 `previous_sandbox_sink` + 收窄 import | ✅ | grep：`current_sandbox_sink` 在 `agent/` 内**仅**剩 `sandbox_events.py:42,100`；`agent/loop.py:76` 已收窄 |
| 3.6 | 就地注释指向 issue #264 | ✅ | `agent/loop.py:575-582`（run 起点）、`:612-617`（finally） |
| 4.1 | `test_sandbox_events.py` + `test_loop_sandbox_events.py` | ✅ **已亲自跑** | `12 passed in 1.54s` |
| 4.2 | `test_background.py` + cgroup + bash events | ✅ **已亲自跑** | `27 passed in 16.59s` |
| 4.3 | `tests/agent/subagent/` | ✅ **已亲自跑** | `710 passed in 26.16s` |
| 4.4 | 全量 `pytest -q` | ✅ **已亲自跑** | `2 failed, 3477 passed, 9 skipped`（2 条环境坑，见下） |
| 4.5 | benchmark smoke | ✅ **已亲自跑** | `uv run asterwynd benchmark … --agent fake` 正常退出；CI 口径的 `benchmark-gate` **PASS**（success_rate delta +0.0000） |
| 4.6 | 复跑两个 repro 应变未复现 | ✅ **已亲自跑** | 两个脚本 HEAD 均 exit 0；base 均 exit 1 |
| 4.7 | OpenSpec strict validate | ✅ **已亲自跑** | `Totals: 29 passed, 0 failed (29 items)` |
| 4.8 | Artifact checker `--base-ref 7acde2b` | ✅ **已亲自跑** | `OpenSpec artifact checks passed` |
| 4.9 | 同步 current spec | ✅ **已核验** | delta block 与 `openspec/specs/workspace-safety/spec.md` 逐字一致（脚本比对 `==` True） |
| 5.1 | 独立审阅闭环 | ✅ **本报告即产出** | — |
| 5.2 | review manifest | ⬜ 未完成（**正确**：须在 `tasks.md` 最终化后生成） | 见文末 |
| 6.1–6.5 | 文档影响 / backlog / 事件 / 归档 / 关 issue | ⬜ 未勾（**正确**：在途；6.5 已标 `(post-merge)`） | 6.2 实际已登记 backlog（见 `workflow-events.jsonl` seq 1）；6.3 已写事件（seq 1/2） |

4.4 的 2 条失败：`tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir,
test_malformed_git_file_falls_back_to_scan}`。根因已亲自核实 = **本机环境坑**：`_find_scope_root` 向上走到 `/tmp`
就停住（失败信息 `assert PosixPath('/tmp') is None`，用户记忆亦记录「本机 `/tmp` 是 git 仓库」）。
该文件（`agent/memory/persistent.py`）**不在本 change 的 diff 内**，与本 change 无关；
tasks.md 4.4 已预先如实记录该环境坑。

## Issues

### 1.［低］`docs/interview-script/` 与 `docs/interview-bullets/` 的「恢复 sandbox sink」表述未跟进（非事实错误）

`docs/agent-internals.md:30` 已正确改为 `reset_sandbox_sink`（本 change diff 内，属实）。
但同类描述仍散落在：

- `docs/interview-script/walkthrough/W01-agent-loop.md:60`：「恢复 sandbox sink」
- `docs/interview-script/walkthrough/self-test-QA.md:18`：「恢复 sandbox sink」
- `docs/interview-bullets/walkthrough.md:2817,3060`：仅列 `agent/sandbox_events.py` 的职责

**判定为非缺陷**：这几处写的是**行为**（「恢复 sandbox sink」），不是**实现调用**
（未点名 `set_sandbox_sink`），修复后该行为仍成立（只是手段由 `set` 变 `reset`），
**不构成事实变化**，故无需改。仅作为「文档影响检查」的完整性记录：作者 6.1 的范围判断
（只改点名了 `set_sandbox_sink` 的 `agent-internals.md`）**是正确的最小面**。
**建议**：无（可选：若日后要统一口径，可把这句补成「按 token 守护式恢复」，属历史债务、非本 change 责任）。

### 2.［低］`except ValueError: pass` 的窄化依赖一个隐含前提（当前成立，仅作记录）

与 #261 审阅同一形态。我实测 `ContextVar.reset(token)` 的两类异常：
跨 Context → `ValueError`（目标情形）；token 二次消费 → `RuntimeError`（**未被捕获，正确**）。
本代码里 token 由 `agent/loop.py:589` 自己创建、`finally` 每 run 至多执行一次、reset 仅一处调用点，
因此**唯一可达**的 `ValueError` 就是「跨上下文」这件事——**不构成现实掩盖**。
注释（`:612-617`）已明确写出「reused token raises RuntimeError and stays loud」，属可接受的防御式设计。
**建议**：无。

> 说明：**未见任何中等及以上问题**。作者在 `proposal.md` / `design.md` 中主动澄清的两处潜在误读点
> （`_NOOP` 哨兵是否需改 `None`、`set_sandbox_sink` 改签名是否破坏公开 API）我已独立核验：
> 前者**不需要改**（`reset` 的跨上下文判据是 Context 身份，与 default 取值无关——我自建探针复验：
> `_NOOP`-default 与 `None`-default 均抛 `ValueError`）；后者**运行期兼容**（非测试调用点仅
> `agent/loop.py` 两处，均已同步改造；测试调用点全部忽略返回值，`test_sandbox_events.py`、
> `test_background.py`、`test_process_backend_cgroup.py`、`test_bash_tool_events.py` 全绿）。

## Correctness 深究（审阅维度 2/4/6）

**缺陷是否真的被消除？** 是。三条独立证据闭合：

1. base 树 / HEAD 树的 A/B：形态 A（repro.py）与形态 B（gcwindow 变体）在 base **exit 1**、HEAD **exit 0**。
2. 新回归用例在 base `loop.py` 下**确定性变红**（0 条事件）、在 HEAD 下**15/15 绿**。
3. 外科式变异（只动 `finally` 那一句）**同样变红** ⇒ 测试**精确锚定**这一行，不是被别处的改动顺带满足。

**为何守护式 reset 能修（机制核验）**：`reset(token)` 的语义是「恢复该 token 记录的那次 `set` 之前的值」，
且 CPython 强制 token 只能在其创建时的 Context 里 reset，跨 Context 主动抛 `ValueError`。
**关键点（我特别验证过）**：这个 `ValueError` **必须真的抛出**，修复才成立——
若 `reset` 跨上下文「静默成功」，它会恢复成被遗留 task 快照到的 `previous`（形态 A 下即 `_NOOP`），
**同样会污染**。新回归用例在 HEAD 下**绿**（活跃 trace 收到 1 条事件）直接证明 `reset` **没有写入**活跃上下文；
我自建的独立探针与 `design_points_probe.py` D3 段亦给出同样结论（`形态=reset -> 终结后活跃 sink: 'LIVE-sink' [clean]`）。
**结论：`ValueError` 确实被抛出并被吸收，污染路径真实闭合。**

**token 门控（D4）在所有路径上语义正确**（逐条核读）：

- **有 recorder 的正常退出**：`sink_token` 非 None → `reset` 复原 run 起点前的值。`test_sink_restored_after_run` 绿。
- **无 recorder 的 run**：`sink_token` 恒为 None → 不 reset。**这与 base 行为等价**——base 的
  `set(previous)` 在 in-context 下就是「把读到的值原样写回」（纯无操作）；跨上下文时它才是污染载体，
  门控掉它即消除载体。我有独立证据：`emit_sandbox_event` 在 `agent/` 内**唯一**消费者是
  `sandbox_events.py:100`，且 run 体内**没有**第二次 `set_sandbox_sink` 调用点
  （grep `agent/loop.py`：仅 `:589` 一处 set），故门控不会漏掉需要复原的中间写入。
- **嵌套子 run**：`test_nested_run_sandbox_events_return_to_parent_trace`（`:237-273`）锁住
  「子 run 退出 → 父 sink 复原」；子 run 的 token 在**同一** Context（直驱嵌套，非 manager 派生）内有效，
  `reset` 正常复原。绿。
- **取消路径**：`cancel()` 把取消投递进 task **自己的** Context，`reset` 不抛；`tests/agent/subagent/`
  710 passed 覆盖。
- **`resume_snapshot` 路径**：我专门核读——该分支在 `agent/loop.py:658-661` **只**重新快照 mode ceiling
  （`set_mode_ceiling`），**没有**第二次 `set_sandbox_sink`。故「token 至多消费一次」的前提成立，
  不存在二次 reset ⇒ 不可达的 `RuntimeError` 分支确实不可达。

**`finally` 体全同步**：我核验 `finally` 内**无 await**（`background_manager.cleanup()` 是同步 `def`），
故 `GeneratorExit` 展开时会**完整执行**到 `reset`——修复语句不会被中途跳过。

**import 收窄核验**：`grep -rn current_sandbox_sink agent/` 仅命中 `agent/sandbox_events.py:42`（定义）与 `:100`
（`emit_sandbox_event` 内部），**`agent/loop.py` 内已无消费者** ⇒ import 收窄正确、无悬空引用。

**形态 B 是否真被消除（安全维度，重点）**：是。base 树 gcwindow 变体 10/10 把
`denied rm -rf /` 写进 OLD trace（`LIVE [] / OLD 1 条`）；HEAD 树该脚本未复现，
且对照组 `PLANT_ABANDONED=False` 全程无串写（脚本内建，我亲跑确认 `PLANT_ABANDONED=True` 在 base 复现、
在 HEAD 不复现）。审计证据「张冠李戴」的路径已被切断。

## Spec 对齐（审阅维度 3）

我用脚本逐字比对（非目测）：

- **delta Requirement 块与 current spec 逐字一致**：`== True`。
- **原正文逐字保留**：`openspec/specs/workspace-safety/spec.md` 的需求正文行与 base `7acde2b` 版本
  `== True`（真正的 MODIFIED，非借 MODIFIED 夹带 ADDED）。
- **追加不变量段**：`:317`「该 sink SHALL 只对其所属执行上下文生效…SHALL NOT 写入任何**其它**执行上下文」。
- **新增 Scenario**：「被遗留 run 的迟后收尾不改变活跃 run 的事件归属」（`:332-342`）。
- **既有 Scenario 保住**：「命令拒绝事件」「超时 kill 事件」均在（`#### Scenario:` 计数 = 3）。
- **backlog 同步**：`docs/openspec-change-backlog.md` 新增第十七批登记条目（diff 亲验）。
- **受保护路径事件**：`workflow-events.jsonl` seq 1（backlog_updated）、seq 2（current_spec_synced）
  均为**结构化**事件、带 `reason` 与 `approved_by`，满足 governance=event_explained 要求。
- `openspec validate --all --strict` **29/29** ⇒ Requirement 首行含 SHALL 等硬约束满足（无 strict 报错）。
- `docs/agent-internals.md:30` 改动**属实**（`set_sandbox_sink` → `reset_sandbox_sink` 并注明守护式 token 恢复）。

**余量**：MODIFIED 的 Requirement **未新增**任何与实现不符的约束（我核读实现与三条 `THEN` 一一对应）。

## 冗余度 / 可维护性 / CI 完整性（审阅维度 4/7/8）

- **冗余度**：无重复实现。`reset_sandbox_sink` 是 `context.py` 既有 `reset_mode_ceiling` 的**同形复制**，
  与 `#255` 建立的 token/reset 约定一致，未另造机制；`_NOOP` 哨兵、事件分发语义、trace schema **均未动**。
- **可维护性**：命名（`sink_token` / `reset_sandbox_sink`）与 #261 的 `ceiling_token` / `reset_mode_ceiling`
  对称；两处新注释（`agent/loop.py:575-582`、`:612-617`、`agent/sandbox_events.py:47-71`）陈述的是
  代码本身无法表达的 ContextVar/GC 约束，符合「注释只写约束」口径。
- **CI 完整性**：**无弱化**。`.github/workflows/ci.yml`、`scripts/flow-policy.json`、
  `scripts/workflow_methods.json`、`scripts/platform-gate.json` **均不在 diff 内**（`git diff --stat` 亲验）。
  新增回归用例是**确定性**的（显式 `gc.collect()`，非碰运气）；我把 plant 阶段的 `sleep(0.05)` 降到 `0`
  后 8/8 仍绿 ⇒ 该 sleep **不承重**，测试不依赖时序宽容。
- 我在 HEAD 上对 CI 的两道 job 口径**分别亲自跑通**：`validate` 的 pytest/validate/checker 与
  `benchmark-gate` 的 `benchmark-gate … --require-baseline`（**PASS**）。

## Evidence

以下命令均在 worktree 根目录、`export PATH=/home/happy/.local/bin:$PATH` 后运行。
所有输出为**我的原始输出**（截取关键行）。

```
# 1. 树与基准
$ git rev-parse HEAD                                    → a97d4f8cc3fbe79d9398abe92ab76fcc03e8db3a
$ git merge-base HEAD origin/master                     → 7acde2b396229e3729dc177032f90f29bfe891b9
$ git status --porcelain                                → （空）

# 2. repro A（形态 A），HEAD
$ .venv/bin/python -u openspec/changes/fix-issue-264-…/repro/sandbox_sink_repro.py
  sink_before: 'TraceRecorderSandboxSink'
  sink_after: 'TraceRecorderSandboxSink'
  sink_clobbered: False
  LIVE trace 收到 sandbox 事件: [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
>>> 未复现：遗留 task 的收尾没有改变后续 run 的 sandbox sink。
EXIT=0

# 3. 基线置换：git show 7acde2b:agent/loop.py > agent/loop.py
$ .venv/bin/python -u …/repro/sandbox_sink_repro.py
  sink_before: 'TraceRecorderSandboxSink'
  sink_after: 'NoopSandboxSink'
  sink_clobbered: True
  LIVE trace 收到 sandbox 事件: []
>>> 复现：遗留 pending run 的跨上下文收尾覆盖了后续 run 的 sandbox sink（-> NoopSandboxSink）
EXIT_A=1

# 4. repro B（形态 B 确定性变体，gcwindow），base vs HEAD
$ .venv/bin/python -u …/repro/sandbox_sink_misroute_gcwindow.py   # base
  LIVE recorder sandbox steps : []
  OLD  recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
>>> 串写复现：LIVE run 的 sandbox 事件落进了 OLD recorder 的 trace。
EXIT_B=1
$ .venv/bin/python -u …/repro/sandbox_sink_misroute_gcwindow.py   # HEAD
  LIVE recorder sandbox steps : [{'event': 'denied', 'command': 'rm -rf /', 'reason': 'live'}]
  OLD  recorder sandbox steps : []
>>> 无串写：LIVE 事件落在 LIVE trace（对照或未触发）。
EXIT=0
# 非 gcwindow 变体（#261 归档原版，作者称 0/10 脆弱）：base 与 HEAD 均 exit 0 ⇒ 脆弱声明属实

# 5. 变异验证（第一轮：整个 loop.py 换回 base）
$ pytest tests/agent/test_loop_sandbox_events.py::test_abandoned_pending_run_teardown_does_not_clobber_live_sink -q
E   AssertionError: 遗留 run 的跨上下文收尾把活跃 run 的 sandbox sink 改写了：活跃 trace 收到 0 条 sandbox 事件（应为 1）
E   assert 0 == 1
FAILED … 1 failed in 1.16s

# 6. 变异验证（第二轮：外科式——只把 finally 的 reset 换回 set(previous)，保留 token 捕获）
$ pytest tests/agent/test_loop_sandbox_events.py::test_abandoned_pending_run_teardown_does_not_clobber_live_sink -q
FAILED … 1 failed in 1.18s
# 还原 HEAD 后
$ pytest …::test_abandoned_pending_run_teardown_does_not_clobber_live_sink -q
1 passed in 1.08s
$ git status --porcelain            → （空）
$ git diff --exit-code; echo $?     → 0
$ sha256sum agent/loop.py           → 2c011d6a976c3b0775a4aa557f2e133b7bd7a6239ff901bbf490203a2d792608（与 HEAD 一致）
$ git rev-parse HEAD                → a97d4f8（HEAD OK）

# 7. 新回归用例稳定性：15/15 绿
PASS=15 FAIL=0 / 15
# sleep(0.05)→0 后仍 8/8 绿（sleep 不承重），随后还原测试文件（sha256 7d69b225… 与 HEAD 一致）

# 8. 我自建的 contextvars 语义探针（不采信注释）
A) default when unset: True
B) set returns token: True | get: sink-A
C) reset(t1) restores default: True
E) cross-context reset -> ('ValueError', "… was created in a different Context")
F) double reset -> RuntimeError … has already been used once
G) reset in own ctx ok
   ⇒ reset_sandbox_sink docstring 的「跨上下文抛 ValueError」「二次消费抛 RuntimeError」两句逐条属实

# 9. 作者的设计点探针（亲跑，与 diagnosis.md 输出一致）
$ .venv/bin/python -u …/repro/design_points_probe.py
  形态=set   -> 终结后活跃 sink: 'STALE-SINK'  [POLLUTED]
  形态=reset -> 终结后活跃 sink: 'LIVE-sink'   [clean]
EXIT=0

# 10. 测试
$ uv run pytest tests/agent/test_loop_sandbox_events.py tests/agent/test_sandbox_events.py -q   → 12 passed in 1.54s
$ uv run pytest tests/agent/subagent/ -q                                                        → 710 passed in 26.16s
$ uv run pytest tests/agent/test_background.py tests/agent/tools/test_process_backend_cgroup.py \
    tests/agent/tools/test_bash_tool_events.py -q                                               → 27 passed in 16.59s
$ uv run pytest -q
2 failed, 3477 passed, 9 skipped, 80 warnings in 345.02s
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
  FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
# 根因亲验：assert PosixPath('/tmp') is None —— /tmp 被当作 scope root（本机环境坑）；
# 该文件不在本 change diff 内。

# 11. 门禁
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed (29 items)
$ uv run python scripts/check_openspec_artifacts.py --base-ref 7acde2b
OpenSpec artifact checks passed
$ uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
[archived manifest check] tasks_hash 已按归档语境跳过（58 个 change；其余 hash 与字段仍校验）
OpenSpec artifact checks passed

# 12. CI 口径的 benchmark 闸门
$ uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke --source-repo . --runs-dir /tmp/bg264 \
    --baseline benchmarks/baseline.json --require-baseline --skip-p95
BENCHMARK GATE
  success_rate: baseline=1.0000 current=1.0000 delta=+0.0000
  result: PASS

# 13. 无 CI/策略弱化
$ git diff 7acde2b..HEAD --stat -- .github/ scripts/flow-policy.json scripts/workflow_methods.json scripts/platform-gate.json
（空）

# 14. import 收窄 / 调用点
$ grep -rn "current_sandbox_sink" agent/     → 仅 sandbox_events.py:42(定义) 与 :100(emit 内部)
$ grep -rn "set_sandbox_sink\|reset_sandbox_sink" agent/  → loop.py:76/589/611, sandbox_events.py:46/58
$ grep -n "await" (loop.py:596-640 finally 体)  → （无）⇒ finally 体全同步
```

## 停轮事项（需用户 / 主 session 处置，非本 reviewer 可决）

1. **本报告不构成 review manifest**。按 AGENTS.md，5.2 的 manifest 必须在 `tasks.md`
   最终化（含归档 move）**之后**生成，由主 session 在收尾时执行。
2. **tasks.md 的 `[ ]` 回勾**：第 2/3/4 节共 21 项在我本次审阅前**未勾选**，但其实现与验证
   **经我亲自复核已全部成立**（见 `## Task Verification` 表）。请主 session 决定回勾时机——
   注意这是**在途的正常状态**（作者尚未回写），**不是缺陷**；若决定回勾，属作者职责范围内的
   常规勾选，本 reviewer 不代为修改（硬约束：不改动工作区）。
3. **第 5/6 节的未勾项**（审阅 manifest、归档、关闭 issue）**在途未勾是正确的**，不构成缺陷；
   6.5 已正确标注 `(post-merge)`。
4. **无阻塞项**：本 change 可进入收尾（归档 + 生成 manifest）。
