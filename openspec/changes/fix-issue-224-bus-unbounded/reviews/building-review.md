# Building Review: fix-issue-224-bus-unbounded (Round 1)

审阅者：独立零记忆 subagent（不继承开发上下文）
审阅范围：`git diff origin/master...HEAD`（base `abdcedfe397273936c3bf1659796445d30dec9d0`，head `80b4770`）
审阅方式：先读 change 文档（design D1-D10 / grill 六条 User Confirmation），再审代码，**实跑**验证 D10/Q1/Q6 与变异，不采信文档自述。

## Verdict

CHANGES_REQUESTED

核心交付（`read()` 单条 + 总量界、`snapshot_payload()` 二维界、D10 非原地截断、D9 token_count 重算、Q6 `>=` 闸门）**实测全部成立且变异可判**；唯有一处 change 自己承诺要避免的措辞不实仍未清除（权威 spec + proposal 仍声称「发布侧严格不超过单条上限」，实测在 LLM 摘要分支为假），外加一处测试自述的判别力与实际不符。均非阻塞性缺陷。

## Tasks Verification

实现类（逐条读代码确认，非只看文件名）

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| 新增三常量（`BUS_MESSAGE_LIMIT` 派生 / `BUS_SNAPSHOT_LIMIT=20` / `BUS_PUBLISH_MAX_TOKENS`） | ✅ | `agent/subagent/bus.py:43` `BUS_MESSAGE_LIMIT = TRANSCRIPT_ITEM_LIMIT`；`:53` `= 20`；`:62` `= BUS_MESSAGE_LIMIT // 4`。实测值 `4000 / 20 / 1000` |
| `BusMessage.truncated` + `to_dict()` 透出 `summary_truncated` | ✅ | `bus.py:100` 字段（有默认值，构造点唯一 `bus.py:141` 用关键字参数）；`bus.py:110` `"summary_truncated": self.truncated` |
| `read()` 截断 + `dataclasses.replace` 新实例 | ✅ | `bus.py:70-87` `_bounded_message`，`:80` `replace(msg, summary=text, token_count=..., truncated=True)`；`:197` `return [_bounded_message(m) for m in collected]`。实测 `bus.read()[0] is bus._messages[0]` → **False** |
| `read()` 重算 `token_count` | ✅ | `bus.py:85` `token_count=estimate_tokens(text)`。实测截断后 1000 == `estimate_tokens(截断文本)`，≠ 全文记账值 7500 |
| `read()` 保留「单条超窗仍返回最新一条」 | ✅ | `bus.py:184-191` 分支保留，`:189-190` 仍 append 后 break |
| `read()` 总量钳制（D4b/Q1） | ✅ | `bus.py:174` `budget = min(budget, BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS)`；`:175` `effective_limit = BUS_SNAPSHOT_LIMIT if limit is None else min(limit, BUS_SNAPSHOT_LIMIT)`；`:194` 用 `effective_limit` 断 |
| `snapshot_payload()` 条数 + 单条 + `messages_total`/`messages_omitted`，加固在方法本身 | ✅ | `bus.py:207-224`；`:218` `visible = list(self._messages)[-BUS_SNAPSHOT_LIMIT:]`；`:220` 逐条 `_bounded_message(...).to_dict()`；`:222-223` 两新键。调用点 `patterns.py:458`、`scheduler.py:2956` 均未经额外处理 |
| `PublishBusMessageTool` 钳 `max_tokens` + 闸门 `>=` | ✅ | `subagents.py:275-276` `requested = kwargs.get("max_tokens", 400)` → `min(max(int(requested),1), BUS_PUBLISH_MAX_TOKENS)`；`:282` `if token_count >= max_tokens:` |
| `ReadBusTool` schema description 校正、工具侧不加第二道截断 | ✅ | `subagents.py:312-317`（`capped at {BUS_MESSAGE_LIMIT} characters and at most {BUS_SNAPSHOT_LIMIT} messages`）；`:335`；`:352-356` 直接委派 `bus.read()`，无二次截断 |
| 不声称「全文在 X」（D6） | ✅ | 代码/测试/spec 全仓 grep 无 `result_ref` / `summary_ref` 与 bus 截断关联的断言；`bus.py:70-87` 与测试仅回流布尔标志 |

测试类（逐条对应到真实存在的测试）

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| 单条 30,000 字 → ≤ 上限 + 标志 | ✅ | `tests/agent/subagent/test_bus.py:295-303` `test_read_truncates_oversized_message_with_flag`（`_OVERSIZED = 30_000`，`:21`） |
| Q5 拆两条：原语义保留 + 新增截断测试 | ✅ | 原测试 `test_bus.py:53-66` 保留 400 字输入与 `summary == "x"*400` 全文断言（未改语义）；截断测试另起 `:295`。两条判别对象不同 |
| `read()` 总量：`max_tokens=10**9, limit=10**9` | ✅ | `test_bus.py:338-349`；另有 `:352-370` 单独锁 token 窗口维（断言与「钳后窗口」逐条等价） |
| D10 回归（队列仍全文 + compact 不变） | ✅ | `test_bus.py:326-335` |
| D9 回归 | ✅ | `test_bus.py:316-323` |
| `snapshot_payload()` 条数/单条/omitted | ✅ | `test_bus.py:177-205`（100 条 → `len==20`、`total==100`、`omitted==80`） |
| 契约测试（两条模型面出口） | ✅ | `tests/agent/subagent/test_bus_bounded_exports.py:132-158`（ReadBusTool JSON）、`:166-186`（`run_pattern` → `result["bus"]`）、`:189-198`（RunPatternTool）、`:107-129`（D10/上限跨出口） |
| 发布侧 10**9 钳制 + 4001 字边界（Q6） | ✅ | `test_bus_bounded_exports.py:206-232`、`:235-256`（4000/4001/4003/4004 四长度） |
| 常量机械锁定（按 D1 派生路径落） | ⚠️ 形式已按派生落，但**锁不住**它自述要锁的东西 | `test_bus.py:277-293`，见 Issues #2 |
| 参数教训（输入真越界） | ✅ | 所有新测试用 30_000 / 100 条 |
| 变异验证 5 项 | ✅（另有一项未覆盖，见 Issues #2） | 本人独立复跑 6 组，见 Test Results |
| 回归 `tests/agent/subagent/` + `tests/agent/tools/` | ✅ | 933 passed |

文档类

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| `diagnosis.md` 6 章 | ✅ | 文件含 Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests |
| spec delta 两份 | ✅ | `specs/subagents/spec.md`（8 Scenario）、`specs/agent-runtime/spec.md`（3 Scenario） |
| 当前规格同步 + `current_spec_synced` ×2 | ✅ | `openspec/specs/subagents/spec.md:163+`、`openspec/specs/agent-runtime/spec.md:198+`；`workflow-events.jsonl` seq 2/3。Requirement 正文逐字比对：subagents delta == synced（True） |
| 关键词扫描（含 grill R3 漏项） | ✅ | `docs/interview-bullets/interview-prep.md:219,221`、`docs/interview-bullets/walkthrough.md`、`docs/interview-script/walkthrough/W03-multi-agent.md:37+`、`docs/interview-script/questions/Q08-multi-agent.md:49+` 均已更新（含把「53 行」改为 224 行、补 `summary_truncated`/`messages_omitted`） |
| backlog 登记 | ✅ | `docs/openspec-change-backlog.md:142+` 第十七批；常量值与实现一致（4000/20//4） |
| Non-Goals 补写 `workers[]` / 顶层 `summary` 仍无界 | ✅ | `proposal.md` Non-Goals 首条、`design.md` Non-Goals 首条、**且**已同步进权威 spec `openspec/specs/agent-runtime/spec.md`（R2 落实） |

「审阅闭环」一节的 3 个 `[x]` 属本次审阅自身，不计入实现任务；`## 验证` 一节实跑复核见 Test Results。

## Issues

### 1. 中等：权威 spec 与 proposal 仍声称「发布侧严格不超过单条上限」——在 LLM 摘要分支实测为假（R5 未闭环）

- 位置：`openspec/specs/subagents/spec.md:169`（权威）+ `openspec/changes/fix-issue-224-bus-unbounded/specs/subagents/spec.md:11`（delta，同句）+ `openspec/changes/fix-issue-224-bus-unbounded/proposal.md` 出口盘点第 4 行（「`max_tokens` 钳住后 ≤ 单条上限（与出口 1/2 同界）」）+ `design.md` grill R6（「D5 钳住后它 ≤ 单条上限，无新增漏洞」）。
- 问题：该句的因果断言是「阈值钳制 + `>=` 闸门 ⇒ 发布侧严格不超过单条上限」。这只在 `_summarize` 的**降级分支**（`subagents.py:295` `content[: max_tokens * 4]`，钳后 ≤ 4000）成立；**LLM 分支**把预算当建议拼进 prompt（`agent/context/summarizer.py:169-172`「Keep the summary under approximately {budget} tokens」），返回体原样透传（`summarizer.py:177`），可能超过 4000。
- 实测（本人构造一个「如实摘要但超预算」的 stub LLM，返回 6000 字）：`PublishBusMessageTool.execute(content="x"*30_000, max_tokens=10**9)` 的回包 `summary` 长 **6000 字符 > BUS_MESSAGE_LIMIT(4000)**，且 `bus._messages[0].summary` 同样是 6000。即**第 5 条模型面出口（发布回包）在 LLM 分支未被界住**，与 proposal/design 的断言不符。
- 该 change 自己已经识别了这个陷阱（`design.md:257`「design D5 不得声称发布侧『两侧同界』」、`design.md` Non-Goals 末条「发布侧对 LLM 摘要分支没有硬界」），但**权威 spec 与 proposal 未按该承诺改写**——属于「change 自我承诺的诚实措辞未闭环」，也正是审阅重点核查项 R5 问的那件事。
- 建议（二选一，均可）：
  1. 如实改写：把 `openspec/specs/subagents/spec.md:169` 与 delta 同句的尾句改为「使**降级分支**不超过单条上限；LLM 摘要分支的预算是建议值，单条的硬保证在消费侧 `read()`」，并同步 proposal 出口 4 的措辞（去掉无条件「≤ 单条上限」）。
  2. 真正做到：在 `subagents.py:288-295` 的 `_summarize` 返回处加一道出口投影截断（`_clip(summary, BUS_MESSAGE_LIMIT)`）——与 D2「截断只在出口投影」范式一致，可让断言成真且第 5 条出口真正有界（当前测试 `test_publish_bus_message_clamps_max_tokens` 把 `manager.llm = None`，只覆盖了降级分支，故该洞无测试）。

### 2. 中等偏低：常量「派生锁」测试不具备其 docstring 声称的判别力

- 位置：`tests/agent/subagent/test_bus.py:277-293`（`test_bus_message_limit_derives_from_transcript_item_limit`）。
- 问题：docstring 明说「把它改成 `BUS_MESSAGE_LIMIT = 4000` 时，下面的 `is` 断言仍绿（小整数缓存），故再断言模块源码里确实是 import 派生」——但源码检查只断言整份模块**存在** `from agent.subagent.manager import` 与 `TRANSCRIPT_ITEM_LIMIT` 两个子串，而该 import 行因为要引入 `_clip` **无论如何都在**（`bus.py:35`）。
- 实测变异：把 `bus.py:43` 改成 `BUS_MESSAGE_LIMIT = 4000`（字面量），该测试 **仍然 passed**（`1 passed, 20 deselected`）。即它锁不住它声称要锁的那次变异，属「假保护」。
- 影响面：spec Scenario「截断上限与其它模型面出口同值」要求「该相等关系 SHALL 有测试机械锁定」。在派生写法下相等由结构保证，但测试自述的判别对象并未被真的锁定；后续若有人把派生改成字面量，spec 的「同值」保证将没有机械保护（且不会有任何红灯）。
- 建议：把源码断言收紧到赋值行本身，例如 `assert re.search(r"^BUS_MESSAGE_LIMIT\s*=\s*TRANSCRIPT_ITEM_LIMIT\s*$", src, re.M)`；或改为运行时断言 `BUS_MESSAGE_LIMIT is TRANSCRIPT_ITEM_LIMIT`。同时修掉 docstring 的过强自述。

### 3. 低：`.gitignore` 新增 `**/handoff.json` 属越界改动

- 位置：`.gitignore:27`（本 change 新增，与 issue #224 无因果关系）。
- 问题：与 bus bounded 化无关的 drive-by 改动；虽无害（已被跟踪的 `openspec/changes/archive/*/handoff.json` 不会因 ignore 规则被移出索引，实测 `git ls-files` 仍在），但混入了本 change 的 diff，收尾时会让「这个改动属于哪个 change」难以追溯。同时 change 目录下的 `handoff.json` 未提交（正确；`check_openspec_artifacts.py:891` 只在存在时校验它，本机校验通过）。
- 建议：要么从本 change 摘出（另开 chore），要么在 `design.md`/`proposal.md` 里补一句它属于「旧仪式残留清理」。不阻塞。

### 4. 低：agent-runtime 的 delta spec 与已同步的权威 spec 发生了内容漂移

- 位置：`openspec/changes/fix-issue-224-bus-unbounded/specs/agent-runtime/spec.md` vs `openspec/specs/agent-runtime/spec.md`。
- 问题：权威 spec 比 delta **多**一段（grill R2 的 `workers[]` / 顶层 `summary` 不在本 Requirement 范围）。delta 是「变更记录」，收尾审阅按 delta 复核时会看不到这条关键限定（subagents 那份 delta 与 synced 逐字相同，无此问题）。
- 建议：把该段补进 delta，保持 delta 与合入结果一致。

### 无以下问题（核查后确认清白）

- 无循环导入：`bus.py:35` 的 `bus → manager` 导入无环（AST 建 `manager.py` 模块级 import 闭包，`agent.subagent.bus` 不在闭包内；三种加载顺序在**新解释器**里实跑均成功）。
- 无与已有工具重复的代码：未新造与 `TRANSCRIPT_ITEM_LIMIT` 并行的第二套口径，也未复制 `_clip`（复用 `manager._clip`）。
- 无注入 / 越权 / 信息泄露面变化：改动只收窄输出体量，未新增参数解析、路径、凭据或权限路径。
- 未弱化 CI：`.github/workflows/ci.yml` 与 `scripts/`、`flow/` 在 diff 中零改动（`git diff --stat -- .github/ scripts/ flow/` 为空）。

## Test Results

环境：`export PATH=/home/happy/.local/bin:$PATH`；本机 `/tmp` 下有 `.git`（已知环境失败与本 change 无关）。

- `uv run pytest tests/agent/subagent/ tests/agent/tools/ -q` → **933 passed**（33.0s）。
- 全量 `uv run pytest -q` → **3012 passed, 9 skipped, 2 failed**（359s）。2 个 failed 均为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir,test_malformed_git_file_falls_back_to_scan}`——任务书已确认为本机环境恒失败、与 bus 无关，不判缺陷。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 唯一报错为 `building-review.md missing`（即本次审阅本身，属预期；本报告落盘后应由 manifest 绑定）。
- `uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke` → **PASS**（success_rate delta +0.0000）。另跑的 `asterwynd benchmark benchmarks/tasks --agent fake` 为 5 passed / 29 failed，属 fake agent 不能真解题的既有现象（28 个 `test_failure` + 38 个 `docker_unavailable` unsupported），非本 change 引入。

### 实跑验证（不读代码，直接观测行为）

| 核查项 | 实测输出 | 结论 |
|---|---|---|
| **D10** 新实例 | `read()[0] is bus._messages[0]` → **False**；读后队列 `len(_messages[0].summary) == 30000`、`truncated is False`、`compact_summary()` 与读前**相同**；返回值 `len(summary)==4000`、`truncated is True` | ✅ 通过（未原地污染队列） |
| **D9** token 重算 | 返回 `token_count == 1000`，`== estimate_tokens(截断文本)` True，`!= estimate_tokens(全文)` True | ✅ |
| **Q1** 总量维 | 100 条 × 30,000 字，`read(max_tokens=10**9, limit=10**9)` → **2 条 / 8,000 字符**（修复前 100 条 / 3,000,000）；默认 kwargs → 1 条 / 4,000 | ✅ 界住 |
| **Q6** 闸门含等号 | 变异 M5（`>=` 改回 `>`）→ `test_publish_bus_message_threshold_is_inclusive` 红灯 | ✅ 4001 字确实触发 summarize |
| `snapshot_payload()` | 100 条满载 → `len(messages)==20`、`total==100`、`omitted==80`、总字符 80,000 | ✅ |
| 边界：空 bus | `read()==[]`；`snapshot_payload()=={"messages": [], "max_read_tokens": 2000, "messages_total": 0, "messages_omitted": 0}` | ✅ |
| 边界：恰好等于上限 | 4,000 字 → 不截断（`truncated False`）；4,001 字 → 截到 4,000（`truncated True`） | ✅ 边界正确 |
| 边界：`limit=0 / -5`、`max_tokens=0 / -1` | 均返回 1 条（「单条超窗仍返回最新」路径），输出仍 ≤ 上限；与改动前语义一致 | ✅ 非回归 |
| 边界：非整数参数 | `limit=5.7` → 正常（5.7 参与 `>=` 比较）；`limit="5"` → `TypeError`。改动前 `len(collected) >= "5"` 同样 TypeError，**非回归** | ✅ 非回归 |
| **发布侧 LLM 分支** | stub LLM 返回 6,000 字 → 回包 6,000 字 > 4,000、队列条目 6,000 字（`read()` 读回仍被截到 4,000） | ⚠️ 见 Issues #1 |

### 变异验证复核（本人独立改坏 → 跑测试 → 确认红 → `git checkout` 还原；收尾 `git status --porcelain` 为空）

| # | 变异 | 结果 |
|---|---|---|
| M1 | `read()` 截断改 identity（`return collected`） | **7 failed**（含两个契约测试） |
| M2 | `snapshot_payload()` 去掉条数上限 | **2 failed** |
| M3 | `read()` 不钳 `max_tokens` | **1 failed**（`test_read_clamps_token_window_not_just_count`） |
| M4 | `replace` 改回原地赋值 | **2 failed**（`test_read_does_not_mutate_queued_message` 等） |
| M5 | 发布侧闸门 `>=` 改回 `>` | **1 failed** |
| M6 | 发布侧 `max_tokens` 不钳（额外加试） | **2 failed** |
| M7 | `BUS_MESSAGE_LIMIT` 改字面量 `4000`（额外加试） | **未变红**（`1 passed`）→ Issues #2 |

还原后基线复跑：`tests/agent/subagent/test_bus.py + test_bus_bounded_exports.py` **31 passed**；工作区干净。

## 结论

本 change 的核心主张有真实实现且经得起独立复算：`read()` 与 `snapshot_payload()` 两条模型面出口在单条（≤ `TRANSCRIPT_ITEM_LIMIT` = 4000）与总量（≤ 20 条 / ≤ 80,000 字符）两个维度都被固定上界锁住，且界真正施加在 `snapshot_payload()` 方法本身（不必依赖调用点）；最关键的 D10 落地坑已用 `dataclasses.replace` 正确处理——实测 `read()` 返回新实例、队列与 `compact_summary()` 仍是全文——D9、Q6、Q1 三项亦全部实测成立，六组变异中五组（含本人加试的发布侧不钳）都能让对应测试立刻变红。剩余问题不阻塞主交付：一处是 change 自己承诺要避免的「发布侧严格 ≤ 单条上限」措辞仍留在权威 spec 与 proposal 里，而实测在 LLM 摘要分支为假（stub LLM 返回 6,000 字时，发布回包与队列条目均超 4,000，且该分支无测试覆盖）；另一处是常量「派生锁」测试的源码断言过于宽松，把它声称能抓的字面量变异放了过去。建议按 Issues #1/#2 修正（改措辞或补出口截断 + 收紧断言）后即可 PASS；Issues #3/#4 为低优先级清理项。
