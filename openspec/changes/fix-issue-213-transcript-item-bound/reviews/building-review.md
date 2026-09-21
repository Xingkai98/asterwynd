# Building Review — fix-issue-213-transcript-item-bound（Round 2）

我是**独立代码审阅者（零记忆，不继承任何开发上下文）**。本会话未读开发者的任何对话、推理或
先前会话产物；下列每条结论只来自 (a) `git show d370d3c` 与 `git diff 7c23059...HEAD` 的实际代码、
(b) change 文档与 issue #224 原文、(c) 我在本仓库**实跑**的命令、变异体与 `/tmp/review_213r2/`
下的探针输出。所有「声称已修 X」都逐条对代码复验；凡未验证的明确写「未能验证」。

**方法核心是变异验证**：把 R2 的每条修复逐条改坏（5 个变异体：N1 去掉钳制 / N2 删 `result_ref`
赋值 / N3 落盘读属性 / N4 回归无条件 `result_ref` 键 / N5 删 `summary_truncated` 标志），跑
change 自己的回归测试看是否变红；「改坏了还全绿」的地方即断言覆盖漏洞。**所有仓库文件在每次
变异后即 `git checkout --` 还原**，收尾 `git status --short` 为空（见文末）。

## Reviewer

- run id: review-fix-issue-213-2026-09-21-r2
- 时间: 2026-09-21
- 审阅对象:
  - 本轮修复提交: `d370d3c`
  - 完整范围: `git diff 7c23059...HEAD`（`agent/subagent/{manager,patterns,scheduler}.py`、
    `agent/tools/builtin/subagents.py`、`web/session.py`、`web/static/{index.html,workflow_transcript.js}`）
  - 文档: `openspec/changes/fix-issue-213-transcript-item-bound/{proposal,design,diagnosis,tasks}.md`
    + `specs/{subagents,agent-runtime}/spec.md` + `reviews/{building-review,grill-design}.md`
    + `docs/agent-internals.md`
  - 测试: `tests/web_tests/test_workflow_node_transcript.py`、
    `tests/agent/subagent/{test_result_representations,test_workflow_result_refs}.py`
- 基线: `7c23059` → head `d370d3c`
- 审阅方法（实跑命令）:
  - `uv run pytest -q tests/web_tests/test_workflow_node_transcript.py tests/agent/subagent/ -p no:randomly` → 551 passed
  - `uv run pytest -q tests/agent/tools/ -p no:randomly` → 395 passed
  - `uv run pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py -p no:randomly` → 338 passed
  - `PYTHONPATH=. uv run python /tmp/review_213r2/probe_{e2e,worker,bus,sideeffect}.py`（4 个探针）
  - **变异验证 5 个**：N1 `_bounded_summary` 去掉 `min(..., TRANSCRIPT_ITEM_LIMIT)`；N2 `_worker_entry`
    删 `result_ref` 赋值；N3 落盘 `has_ref=True` 改读属性；N4 `result_ref` 回归无条件放键；
    N5 删 `entry["summary_truncated"]`。（每次改完即跑测试，随后 `git checkout --` 还原）
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref 7c23059 --require-base`（CI 同款）
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-213-transcript-item-bound --strict`
  - `gh api repos/Xingkai98/asterwynd/issues/224`、`gh api ".../issues?state=all&sort=created"`
  - 收尾 `git status --short` → 空

## Verdict

**CHANGES_REQUESTED**

理由：R1 的 **blocker 已真正修复并被我独立证伪性验证**——R2 的钳制确实堵住了 `bounded_summary`
这条「换个键再犯」的通道（N1 变异变红、端到端经真实工具 4 档 `max_tokens` 全不含全文）。
Issues 2/4/6 已修，Issue 3 的核心已修。但本 HEAD **不能让 CI 门禁通过**：R2 把
`reviews/building-review.md` 落进了仓库却**没有配套的 `building-review-manifest.json`**，
`scripts/check_openspec_artifacts.py`（`ci.yml:62` 的 required check）在 HEAD 上**实测 exit 1**，
而 `tasks.md` 同时把「artifact checker 通过」勾成了 `[x]`——这是一句**与事实不符的勾选**。
连带三处收尾缺口（见 Issues）：R1 Issue 7 未处理、Issue 5 改名不彻底（用户可见文档仍写旧名）、
R2 提交信息声称的「无条件断言」与代码不符（实际仍是条件断言，`summary_truncated` 标志零保护）。

这些都是小改，修完 + 生成 manifest 即可 PASS；但它们必须在本 PR 合入前清零。

## Round 1 Issue 验证

| R1 Issue | 声称的修复 | 我的独立验证结果 |
|---|---|---|
| **1 (blocker)** `bounded_summary` 随 `max_tokens` 放大 | `budget_chars = min(budget_chars, TRANSCRIPT_ITEM_LIMIT)`；回归测试改整包断言 | ✅ **成立**（4 个子项全部实测确认，见下） |
| **2 (major)** proposal Non-Goal 假话 + 无 bus issue | 改成如实描述 + 另立 #224 | ✅ **成立**（原句已删、新描述经我独立复现属实、#224 存在且对得上）；⚠️ 但有**新**的相关缺口：design.md 两处仍与 R2 实现不符（Issue 6） |
| **3 (major)** 恒真断言（条件恒 False） | 改为无条件断言 + 走真实 `run_pattern` | ⚠️ **核心修复成立**（N2 变红），但**声称的「无条件断言」与代码不符**——实际仍是 `if entry.get("summary_truncated"):` 条件式；N5（删标志）全绿 → 标志零保护（Issue 4） |
| **4 (minor)** D3b 顺序陷阱零保护 | 补 `test_artifact_summary_ref_is_navigable` | ✅ **成立**（N3 改回读属性 → 该测试变红，`test_workflow_result_refs.py:199`） |
| **5 (minor)** `summary_chars` 语义易混 | 改名 `summary_full_chars` | ⚠️ **部分**：实现/测试/design 已改，但 `manager.py:218` docstring 与 `docs/agent-internals.md:1001` 仍写旧名（Issue 5） |
| **6 (minor)** 出口 4 测试绕过 `RunPattern` | 改走 `run_pattern` | ✅ **成立**（`test_workflow_node_transcript.py:882-911` 经 `run_pattern`；探针实测 3 个 worker、整包不含全文） |
| **7 (minor)** tasks「三处同值」实为两处 | —— | ❌ **未处理、未说明**（`tasks.md:44-45` 仍以 `[x]` 声称「升级为三处」，`test:624` 仍是两处比较，无 `TRANSCRIPT_ITEM_LIMIT` 字面；Issue 7） |

### Issue 1 的 4 个子项逐一验证

**(a) 经真实工具路径返回体确不含全文** —— ✅ 实测（`/tmp/review_213r2/probe_e2e.py`：模型自撰
`spec.nodes[0].max_tokens` → `WorkflowScheduler.run` → `GetSubagentRunTool.execute`）：

```
max_tokens=None    summary=4000  bounded_summary=2040  整包 JSON=6763   全文在返回里? False
max_tokens=5000    summary=4000  bounded_summary=4040  整包 JSON=8763   全文在返回里? False
max_tokens=50000   summary=4000  bounded_summary=4040  整包 JSON=8764   全文在返回里? False
max_tokens=500000  summary=4000  bounded_summary=4040  整包 JSON=8765   全文在返回里? False
```

**(b) 整包断言真能杀死「去掉钳制」的变异** —— ✅ N1 实测：删掉 `manager.py:71`
`budget_chars = min(budget_chars, TRANSCRIPT_ITEM_LIMIT)` →
`tests/web_tests/test_workflow_node_transcript.py:761` 的 `assert HUGE not in json.dumps(payload)`
**变红**（1 failed, 33 passed）。该断言非恒真：钳制在时 payload 不含 HUGE（通过），去掉后
`bounded_summary`=30000=HUGE（失败）。

**(c) `bounded_summary` 上限与 `max_tokens` 独立** —— ✅ 上限 = `min(max(2000, max_tokens*4), 4000)`
= **4000 封顶**（`manager.py:68-71`）。实测 `max_tokens ∈ {5000, 50000, 500000}` 时全为 4040
（4000 + 标记），即 ≥2000 后**不再随 `max_tokens` 变化**。

**(d) 钳制副作用** —— ⚠️ **行为变更属实但非语义破坏**。实测（`probe_sideeffect.py`）：
`max_tokens=500000` 时落盘 `summary_ref` 由钳制前的 30000 字降到 **4040** 字（`result_ref` 全文
仍为 30000）。我独立核了两点判定它**不构成对 `workflow-result-aggregation` D5 的破坏**：
1. `summary_ref` 落盘件**唯一生产写点**是 `manager.py:1371`，**全仓无任何生产代码读取该落盘件正文**
   （`grep save_summary` 仅此一处生产调用；所有 `store.load(run.summary_ref)` 都在测试里）；
   下游聚合走的是 `_bounded_output`/`result_ref`（`scheduler.py:2356-2362`），与 `summary_ref` 正文无关。
2. 该字段名为 bounded summary、base 版注释即写「只保证比全文短、够定位」；钳到 4000 使其**更**符合
   「bounded」语义，且全文仍由 `result_ref` 完整保留。
→ 结论：**无功能回归**；但「落盘件在大预算下会变短」这一可观测变更**未写进 design「测试/契约影响」节**，
建议补一句（Issue 6 的一部分）。

## Issues

### Issue 1（severity: major）— CI / artifact checker 在 HEAD 上红灯，而 tasks 勾了「通过」

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/reviews/`（缺
  `building-review-manifest.json`）+ `tasks.md:72`（`- [x] OpenSpec artifact checker 通过`）
- 描述: R2 提交 `d370d3c` 把 R1 的 `building-review.md` 落进仓库，但**未附**
  `building-review-manifest.json`。`scripts/check_openspec_artifacts.py` 的
  `_check_review_manifests`（`:1034-1045`）只要 `reviews/*-review.md` 存在就调
  `verify_review_manifest`，manifest 缺失即报错。**CI（`.github/workflows/ci.yml:62`）直接跑这条检查。**
- 证据（实跑，CI 同款命令）:
  ```
  $ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref 7c23059 --require-base
  ERROR: fix-issue-213-transcript-item-bound: review manifest missing:
    openspec/changes/fix-issue-213-transcript-item-bound/reviews/building-review-manifest.json
  exit=1
  ```
  对照：在 R1 头 `022cc46` 上 `reviews/` 只有 `grill-design.md`（无 `*-review.md`），
  4 条任务未勾 → checker 通过；R2 加入报告后才变红。即**这是 R2 引入的门禁回归**。
- 说明与建议: 该 manifest 由 `/review-loop` 在 **PASS** 时生成（绑定 reviewer run / base·head sha /
  tasks·spec·diff·report hash），故本轮非 PASS 时红灯有一定内在性；但 (i) 必须在我判 PASS 后**立即**
  生成，否则 PR 的 required check 恒红；(ii) `tasks.md` 那行 `[x]` 在**当前 HEAD** 上是**不实勾选**，
  应收敛为未勾或在 manifest 落地后再勾——仓库明令禁止假话，机械门禁不得靠文字过关。

### Issue 2（severity: minor）— R2 提交信息/文档声称的「无条件断言」与代码不符

- 位置: `tests/web_tests/test_workflow_node_transcript.py:904-908` 对比提交信息 `d370d3c`
- 描述: 提交信息与任务声称「已改为**无条件断言** `entry["summary_truncated"] is True 且
  "result_ref" in entry`」，但实际代码是**条件式**：
  ```python
  if entry.get("summary_truncated"):          # :904 —— 仍是条件，非无条件
      assert "result_ref" in entry, ...
  ```
  R1 Issue 3 的核心（`_worker_entry` 删 `result_ref` 赋值导致断言的**条件恒 False**）确已修复——
  我的探针实测该 `if` 分支**真被执行**（3 个 worker 全 `summary_truncated=True`），且 N2 变红。
  但它并未做到「无条件」：断言被 `summary_truncated` 标志门控，标志一旦丢失，(b) 不变量即静默失守。
- 证据: N5（`patterns.py:366` 去掉 `entry["summary_truncated"] = True`）→
  `uv run pytest -q tests/web_tests/test_workflow_node_transcript.py tests/agent/subagent/`
  → **551 passed（全绿）**。即该模型面标志**零测试保护**，且删标志会连带关掉 (b) 断言。
- 建议: 对「本 change 已知被截断的构造」改真无条件断言，例如
  `assert entry["summary_truncated"] is True` 与 `assert "result_ref" in entry` 并列（不被 `if` 门控）；
  或保留条件式但**另加** `assert entry.get("summary_truncated") is True`。并修正提交信息措辞。

### Issue 3（severity: minor）— 改名不彻底：用户可见文档仍写 `summary_chars`

- 位置: `docs/agent-internals.md:1001`、`agent/subagent/manager.py:218`
- 描述: Issue 5 改名 `summary_chars → summary_full_chars` 只覆盖了实现（`manager.py:228`）、
  测试（`test_result_representations.py:95`）、design（`:251`）、tasks（`:24`）。但
  **本 change 自己新增**的 `docs/agent-internals.md:1001`（`summary_chars` 给出全文长度…）
  与 `manager.py:218` 的 `to_result_dict` docstring 仍写**旧字段名**——字段已不存在，读者按名索骥会扑空，
  正是本 change 要消灭的那类「指向不存在东西」的表述。
- 证据:
  ```
  $ grep -rn "summary_chars" docs/ agent/subagent/manager.py
  docs/agent-internals.md:1001:`summary_chars` 给出全文长度，模型据此判断值不值得翻页。
  agent/subagent/manager.py:218:        （issue #213：那里才区分「谁在看」）。``summary_chars`` 给出全文长度，让模型
  ```
- 建议: 两处改为 `summary_full_chars`。

### Issue 4（severity: minor）— R1 Issue 7 未处理、未说明，tasks 仍不实勾选

- 位置: `tasks.md:44-45` 与 `tests/web_tests/test_workflow_node_transcript.py:624`
- 描述: R1 Issue 7 指出 tasks 声称「把两个 4000 断言**升级为三处**同值」实际是两处。R2 **未改**
  任务文字、**未补**断言、也未如实说明。当前 `test:624` 仍是
  `assert TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT`，全仓无
  `TRANSCRIPT_ITEM_LIMIT ==` 字面比较。因 `TOOL_CALL_ARGUMENT_LIMIT = TRANSCRIPT_ITEM_LIMIT`
  是模块级别名，该断言**传递等价**地锁住三处同值——契约仍成立，但 tasks 的 `[x]` 勾选**与实现不符**。
- 证据: `grep -rn "TRANSCRIPT_ITEM_LIMIT ==" tests/` → 无命中；`tasks.md:44-45` 仍以 `[x]` 声称已升级。
- 建议: 二选一——补一条显式 `assert TRANSCRIPT_ITEM_LIMIT == TRANSCRIPT_CONTENT_LIMIT`（意图更直白），
  或把 tasks 文字改成实际（「两处显式比较 + 别名传递等价」）。

### Issue 5（severity: minor）— design.md 两处与 R2 实现不符（含钳制未入文档）

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/design.md:11` 与 `:194`
- 描述:
  1. `design.md:11` 的现状表仍写 `_bounded_summary` 预算 = `max(2000, max_tokens*4)`
     「**随节点预算浮动**」——这正是 R2 钳制掉的属性，表未更新，读者会以为它仍无界。
  2. `design.md:194`（D9）写出口 4「复用 `_bounded_summary(run.summary, run.max_tokens)`」，
     而实现是 `patterns._worker_entry` 用 `_clip(run.summary, TRANSCRIPT_ITEM_LIMIT)`
     （`patterns.py:352`）——**不是** `_bounded_summary`，且不带 `_bounded_summary` 的文本标记。
- 证据: `design.md:11`、`:194` 原文对照 `manager.py:71`、`patterns.py:352`。
- 建议: 更新 `:11` 为「`min(max(2000, max_tokens*4), 4000)`（**上限固定**）」；更新 `:194` 描述为
  `_clip` + 固定 `TRANSCRIPT_ITEM_LIMIT`；并在「契约/测试影响」补一句「落盘 `summary_ref` 在大预算下
  会变短（实测 30000→4040），但无生产消费者读取其正文，`result_ref` 仍为全文」。

### Issue 6（severity: minor）— 新测试首条断言偏弱（非恒真，但冗余）

- 位置: `tests/web_tests/test_workflow_node_transcript.py:925`
- 描述: `test_worker_entry_without_workflow_identity_does_not_lie` 的首条
  `assert entry.get("result_ref") is None` 在「键缺失」与「键存在但值为 None」两种情况下**都成立**，
  单独不具判别力。真正有判别力的是下一条 `assert "result_ref" not in json.dumps(entry)`。
- 证据: N4（`patterns.py:370-372` 回归无条件放键 `entry["result_ref"] = getattr(...)`）→
  `test_worker_entry_without_workflow_identity_does_not_lie` **变红**（`json.dumps` 含
  `"result_ref": null`），故整条测试**非恒真**、能杀死变异；只是首行作为「构造前提」写法偏弱。
- 建议: 首行改 `assert "result_ref" not in entry`，与语义一致。

## 未构成 issue、但我实测确认的事实

1. **proposal 的两处 bus 数字基本属实**（我独立复现）：`ReadBus` 单条 30000 字原样返回
   **30,158 字符**；`snapshot_payload()` 100×1600 字 → **173,305 字符**（proposal 写 172,703，
   差 ~600 属 JSON 结构/样本差异，**同量级、无实质出入**）。旧句「已有各自的 bounded 口径」
   仅见于 design/grill 的「已删除」上下文与本 R1 报告（后者由本报告覆盖）——
   `grep "已有各自的 bounded 口径"` 在 proposal 正文已**零命中**。
2. **issue #224 真实存在且对得上**：open 态，标题
   「【bugfix】message bus 出口无界：ReadBus 单条与 RunPattern.result.bus 可注入任意长度子 agent 文本」，
   正文含 ReadBus 单条 / snapshot / 发布侧 `max_tokens` 无上界三项、关联 #213/#212——与 proposal
   和 design 的引用一致。
3. **「有 ref 才放键」无消费方受损**：`workers[].result_ref` 在**生产代码**中无读取点
   （`_legacy_result` 只读 `worker['summary']`/`reason`/`status`），无测试此前断言该键恒存在。
   条件化 `result_ref` 安全。
4. **高危模式全仓扫描（`max_tokens` 决定模型面长度）**：除 `_bounded_summary`（已钳）外，
   剩余 `max_tokens*4` 模型面写点**只有** bus 路径（`agent/tools/builtin/subagents.py:280/289/291`
   的 `PublishBusMessage._summarize`），已被 **#224 明确纳管**；
   `agent/memory/summary.py:45` 是记忆摘要（非子 agent 撰写内容，不属本 change 范围）。
   **未发现未纳管的「换地方再犯」点。**

## Test Results

| 命令 | 结果 |
|---|---|
| `pytest -q tests/web_tests/test_workflow_node_transcript.py tests/agent/subagent/ -p no:randomly` | **551 passed**（与提交信息一致） |
| `pytest -q tests/agent/tools/ -p no:randomly` | 395 passed |
| `pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py -p no:randomly` | 338 passed |
| `check_openspec_artifacts.py --base-ref 7c23059 --require-base` | **exit 1（manifest missing，见 Issue 1）** |
| `openspec validate fix-issue-213-transcript-item-bound --strict` | `is valid` |

**变异验证（全部改完即还原）**

| 变异 | 改动 | 结果 | 判别力 |
|---|---|---|---|
| N1 | `_bounded_summary` 去掉 `min(..., TRANSCRIPT_ITEM_LIMIT)` | 1 failed（`test:761` 整包断言） | ✅ 有效（证实 R1 blocker 修复） |
| N2 | `_worker_entry` 删 `result_ref` 赋值 | 1 failed（`test_worker_entry_summary_is_bounded_and_navigable`） | ✅ 有效（R1 Issue 3 核心已修） |
| N3 | 落盘 `has_ref=True` 改读属性 | 1 failed（`test_artifact_summary_ref_is_navigable`） | ✅ 有效（R1 Issue 4 已修） |
| N4 | `result_ref` 回归无条件放键 | 1 failed（`test_worker_entry_without_workflow_identity_does_not_lie`） | ✅ 有效 |
| N5 | 删 `entry["summary_truncated"]` 标志 | **551 passed（全绿）** | ❌ **漏网**（标志零保护，Issue 2） |

**环境致因（已知、非本 change，按要求未复验）**：`TestFindScopeRoot` 2 条（`/tmp/.git` 致因）、
`test_workflow_graph_browser.py` 负载敏感 flake——我**未复现出别的失败**。

**零残留证据**：审阅结束 `git status --short` 输出为空（除本报告文件为覆盖写，见「审阅产物」）。
所有探针脚本在 `/tmp/review_213r2/`，仓库文件在每次变异后 `git checkout --` 还原。

## 结论

R2 把 R1 的 **blocker 真正堵住了**，且堵法（钳制 `_bounded_summary` 预算 + 整包断言）经我
**独立变异 + 端到端实跑**双重证实；Issues 2/4/6 也确实修好。核心行为面无回归——`_format_run_envelope`
默认 bounded 未破内部消费点（调度器 `full_summary=True` 正确）、`_bounded_summary` 钳制对落盘
`summary_ref` 的缩短无生产消费者受影响、`result_ref` 全文保持完整。

但当前 HEAD **不能按现状合入**：

1. **major**——`reviews/building-review.md` 落库但缺 `building-review-manifest.json`，
   `check_openspec_artifacts.py`（CI required check）**实测 exit 1**；而 `tasks.md` 把
   「artifact checker 通过」勾成 `[x]`，是不实勾选。
2. **minor**——R2 声称的「无条件断言」与代码不符（仍是 `if ...:` 条件式），`summary_truncated`
   模型面标志**零测试保护**（N5 全绿）。
3. **minor**——改名不彻底：`docs/agent-internals.md:1001`、`manager.py:218` 仍写 `summary_chars`。
4. **minor**——R1 Issue 7 未处理（tasks 仍不实勾选）；design.md 两处与 R2 实现不符，含钳制副作用未入文档。

建议处置：生成 review manifest（PASS 后）→ 修正 `tasks.md` 与环境事实不符的勾选 → 补
`summary_truncated` 的无条件断言与三处同值显式断言 → 扫掉两处旧字段名 → 更新 design.md 两处 →
重跑第 3 轮复审。以上均为一处一行级小改，预计一轮内可清。
