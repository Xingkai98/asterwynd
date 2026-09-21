# Building Review: fix-issue-224-bus-unbounded (Round 2)

审阅者：独立零记忆 subagent（不继承任何开发上下文）
审阅范围：`git diff origin/master...HEAD`（base `abdcedfe397273936c3bf1659796445d30dec9d0`，head `4f7fd85`）
审阅方式：先读 Round 1 报告 → 读代码 → **实跑**验证（不采信修复者自述）→ 9 组变异逐项确认红/绿 → 还原后确认工作区干净。

## Verdict

PASS

## Tasks Verification

实现类（逐条读**代码**确认，非只看文件名）

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| 三常量（`BUS_MESSAGE_LIMIT` 派生 / `BUS_SNAPSHOT_LIMIT=20` / `BUS_PUBLISH_MAX_TOKENS`） | ✅ | `agent/subagent/bus.py:43`（`= TRANSCRIPT_ITEM_LIMIT`）、`:53`、`:62`；实跑值 `4000 / 20 / 1000` |
| `BusMessage.truncated` + `to_dict()` 透出 `summary_truncated` | ✅ | `bus.py:100` 字段（默认 False，构造点唯一 `bus.py:141`）、`bus.py:110` |
| `read()` 单条截断 + `dataclasses.replace` 新实例（D10） | ✅ | `bus.py:70-87` `_bounded_message`；`:77` 走 `manager._clip`；`:80-87` `replace(...)`；`:197` 投影。实跑 `read()[0] is bus._messages[0]` → **False** |
| `read()` 重算 `token_count`（D9） | ✅ | `bus.py:85`。实跑截断后 1000 == `estimate_tokens(截断文本)` ≠ 全文值 7500 |
| `read()` 保留「单条超窗仍返回最新一条」（D3） | ✅ | `bus.py:184-191`（`:189-190` 仍 append 后 break），返回的是**投影后**的该条 |
| `read()` 总量钳制（D4b/Q1） | ✅ | `bus.py:174` 钳 token 窗口、`:175` 钳条数、`:194` 用 `effective_limit` 断 |
| `snapshot_payload()` 条数 + 单条 + `messages_total`/`messages_omitted`，加固在方法本身 | ✅ | `bus.py:207-224`（`:218` 取最近 20、`:220` 逐条投影、`:222-223` 两新键）；两个调用点 `patterns.py:458` / `scheduler.py:2956` 均无额外处理 |
| `PublishBusMessageTool` 钳 `max_tokens` + 闸门 `>=` | ✅ | `agent/tools/builtin/subagents.py:276-277`、`:283` |
| `ReadBusTool` schema description 校正；工具侧不加第二道截断 | ✅ | `subagents.py:312-322`（明说单条/总量均有上限 + `summary_truncated`）、`:331-341`、`:357-361` 直接委派 `bus.read()` |
| 不声称「全文在 X」（D6） | ✅ | 全仓 grep 无 bus 截断与 `result_ref`/`summary_ref` 的关联断言；`bus.py:70-87` 只回流布尔标志 |
| **R1 修复**：回包走出口投影 | ✅ | `subagents.py:296` `json.dumps(_bounded_message(msg).to_dict(), ...)`；`:292-295` 注释如实说明 LLM 分支是 advisory |
| **R2 修复**：派生锁收紧 | ✅ | `tests/agent/subagent/test_bus.py:81-90` 正则断言赋值右侧就是 `TRANSCRIPT_ITEM_LIMIT` |

测试类

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| 单条 30,000 → ≤ 上限 + 标志 | ✅ | `test_bus.py:93-101`（`_OVERSIZED = 30_000`，`:15`） |
| Q5 拆两条（原语义保留 + 新增截断测试） | ✅ | `test_bus.py:53-69` 保留 400 字与全文断言、`:93` 另起截断测试 |
| `read()` 总量 `max_tokens=10**9, limit=10**9` | ✅ | `test_bus.py:136-147`；`:150-168` 单独锁 token 窗口维 |
| D10 回归 | ✅ | `test_bus.py:124-133` |
| D9 回归 | ✅ | `test_bus.py:114-122` |
| `snapshot_payload()` 条数/单条/omitted | ✅ | `test_bus.py:180-203` |
| 契约测试（两条出口） | ✅（含一处措辞水分，见 Issues #3） | `test_bus_bounded_exports.py:114-145`（ReadBus，真满载 bus）、`:166-177`（snapshot_payload，真满载 bus）、`:180-201`（run_pattern 端到端，仅锁「键存在且有界」） |
| 发布侧钳制 + 4001 边界（Q6） | ✅ | `test_bus_bounded_exports.py:204-221`、`:265-285`（4000/4001/4003/4004 四长度） |
| **R1 回归测试** | ✅ | `test_bus_bounded_exports.py:239-261`（`OverBudgetLLM` 返回 6000 字，`:224-236`） |
| 常量机械锁定（按 D1 派生路径落） | ✅ | `test_bus.py:72-90`；变异实测**变红** |
| 参数教训（输入真越界） | ✅ | 新增测试用 30_000 / 100 条；唯二例外见 Issues #3 |
| 变异验证 | ✅ | 本人独立复跑 9 组，见 Test Results |
| 回归 `tests/agent/subagent/` + `tests/agent/tools/` | ✅ | 934 passed |

文档类

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| `diagnosis.md` 6 章 | ✅ | 含 Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests |
| spec delta 两份 | ✅ | `specs/subagents/spec.md`（9 Scenario）、`specs/agent-runtime/spec.md`（3 Scenario） |
| 当前规格同步 + `current_spec_synced` ×2 | ✅ | `workflow-events.jsonl` seq 2/3；`openspec/specs/{subagents,agent-runtime}/spec.md` |
| **R4**：delta 与权威 spec 逐字一致 | ✅ | 见 Round 1 Issues Re-check R4 |
| 关键词扫描 | ✅ | `docs/interview-bullets/interview-prep.md:219,221,225`、`walkthrough.md:764+`、`docs/interview-script/questions/Q08-multi-agent.md:49-56`、`walkthrough/W03-multi-agent.md:37-48` |
| backlog 登记 | ✅ | `docs/openspec-change-backlog.md:144`，常量值与实现一致 |
| Non-Goals 补写 `workers[]` / 顶层 `summary` 仍无界 | ✅ | `proposal.md:100-105`、`design.md` Non-Goals 末条、**且**已同步进权威 `openspec/specs/agent-runtime/spec.md` |

## Round 1 Issues Re-check

**R1（中等）：发布回包在 LLM 摘要超预算时越界 —— 已真修好（独立实测）**

- 我的验证方式：自写脚本构造 `OverBudgetLLM`（`chat()` 恒返回 6000 字），跑
  `PublishBusMessageTool(mgr).execute(sender="w", topic="t", content="x"*30000, max_tokens=10**9)`（**不经** change 自带测试）。
- 实测输出：
  - 回包 `summary` 长 **4000** = `BUS_MESSAGE_LIMIT`，`summary_truncated` = **True**，`token_count` = **1000** = `max(1, 4000//4)`；
  - `bus._messages[0].summary` 长 **6000**（队列保留全文），`truncated` = **False**（队列条未被打标）；
  - 随后 `read()` 读回仍为 4000 / True。
- 判别力复核（变异）：把 `subagents.py:296` 的 `_bounded_message(msg).to_dict()` 还原成 `msg.to_dict()` →
  `test_publish_reply_is_bounded_when_summary_over_budget` **FAILED**（`assert len(out["summary"]) <= BUS_MESSAGE_LIMIT`，实测 6000），
  同批 `1 failed, 31 passed`。**新测试对 R1 的修复有真实判别力**，不是恒真断言。
- 结论：R1 闭环。发布侧「界由出口投影保证、不由阈值保证」现已在代码、delta spec、权威 spec、proposal C 节四处一致成立。

**R2（中等偏低）：常量派生锁是假保护 —— 已真修好（独立实测）**

- 我的验证方式：把 `bus.py:43` 改成 `BUS_MESSAGE_LIMIT = 4000`（字面量），跑
  `pytest tests/agent/subagent/test_bus.py::test_bus_message_limit_derives_from_transcript_item_limit`。
- 实测：**1 failed**（`test_bus.py:86` 的 `re.search` 断言失败）。Round 1 同一变异是 `1 passed` —— 修复确实把判别力补齐了。
- 还原：`git checkout agent/subagent/bus.py`，工作区干净。
- 结论：R2 闭环。锁的是**赋值右侧**（`^BUS_MESSAGE_LIMIT\s*=\s*TRANSCRIPT_ITEM_LIMIT\s*$`，多行模式），不是「模块里存在某个 import 子串」。

**R3（低）：`.gitignore` 越界改动 —— 已回滚**

- 实测：`git diff origin/master...HEAD -- .gitignore` **为空**（`4f7fd85` 里 `3 -` 行已撤）。
- `openspec/changes/fix-issue-224-bus-unbounded/handoff.json` **不存在**（`ls` 确认），未提交、也未留在工作区。
- 结论：R3 闭环。

**R4（低）：agent-runtime delta 与已同步权威 spec 漂移 —— 已补齐（独立比对）**

- 我的验证方式：分别抽出两文件的 Requirements 正文做 `diff` + 忽略空行归一化比对。
- 实测：`agent-runtime` 与 `subagents` 两份的 Requirement 正文**归一化后逐字相同**（唯一差异是文件末尾一个空行）；
  R2（design）的限定段「本 Requirement 只约束 `bus` 快照这一项。`RunPattern` 返回体中的 `workers[]` 与顶层 `summary` 的条数维**不在**本 Requirement 范围内」
  已在 **delta 与权威 spec 两处都出现**（`specs/agent-runtime/spec.md:23-24` ↔ `openspec/specs/agent-runtime/spec.md` 同段）。
- 结论：R4 闭环，delta 与合入结果不再漂移。

## Issues

### 1. 低：两处文档仍把「发布侧的界」归因于阈值钳制（结论已真、因果表述不准）

- 位置：`openspec/changes/fix-issue-224-bus-unbounded/proposal.md:28-29`（出口盘点后的「出口 4」说明：「`max_tokens` 钳住后 ≤ 单条上限（与出口 1/2 同界）」）、
  `openspec/changes/fix-issue-224-bus-unbounded/design.md:122-123`（D5 闸门段的末句：「改为 `if token_count >= max_tokens` 后，4000 字即触发 summarize，发布侧严格 ≤ 单条上限」）。
- 问题：Round 1 的 R1 修复要求「proposal 里那句对 LLM 分支不成立的断言」改写，**C 节（`proposal.md:68-80`）确实改了**，但出口盘点处这一句与 design D5 末句未同步改。它们把「≤ 单条上限」归因于阈值钳制/闸门，而**实际保证来自回包出口投影**（`subagents.py:296`）。与它们相邻的段落（`proposal.md:75-78`、`design.md:125-127`）已如实写明「界由出口投影保证、不由阈值保证」。
- 影响：**无行为缺陷**——修复后该结论本身已为真（回包经投影确实 ≤ 4000），只是成因写得不准；且同一文档的相邻段落已给出正确口径，不会误导实现者。**不阻塞**。
- 建议：把这两句的成因改为「经出口投影后 ≤ 单条上限」，与 C 节/权威 spec:171 的措辞对齐。

### 2. 低：`snapshot_payload()` 的 `max_read_tokens=2000` 键与实际返回体量不再自洽

- 位置：`agent/subagent/bus.py:221`（返回 `"max_read_tokens": self.max_read_tokens`），产出上限见 `bus.py:218,220`。
- 问题：修复后快照最多 20 条 × 4000 字符 = **80,000 字符 ≈ 20,000 token**，但返回体仍带 `max_read_tokens: 2000`。模型读到这个键容易以为「这批消息装得进 2000 token」。该键是既有键（`proposal.md` Non-Goals 明确「只截 bus 消息、不动既有键」），修复前也存在（当时 payload 甚至完全无界，更不自洽），**属既有遗产而非本 change 引入**。
- 影响：仅是自描述不精确，不放大任何被检视方可控的量。**不阻塞**。
- 建议：另案（不在本 change）考虑把该键改名为 `default_read_window` 或补一个 `messages_limit` 键。

### 3. 低：两条 run_pattern 端到端测试的实际判别力弱于其 docstring 自述

- 位置：`tests/agent/subagent/test_bus_bounded_exports.py:180-188`（`test_run_pattern_bus_export_is_bounded`）、`:192-201`（`test_run_pattern_tool_export_is_bounded`），辅助类 `PublishThenFinishLLM` 见 `:52-84`。
- 问题：docstring 自述「真实 `run_pattern` 里 worker 发布的**超长消息**被界住」。实测该场景下 bus 里那条消息只有 **4 个字符**：worker 用 `content="x"*30000` 调 `PublishBusMessage`，`_summarize` 走 LLM 分支，而 `PublishThenFinishLLM` 的第 2 次 `chat()`（被 `LLMSummarizer` 消费）返回 `"done"` → 入队 `summary == "done"`。实跑复核（`run_pattern(pattern="orchestrator-worker", params={"workers":1})`）：
  ```
  n messages: 1
    len(summary)= 4  trunc= False  repr= 'done'
  ```
  故 `_assert_bounded(result["bus"]["messages"])` 在这两条测试里是**恒真断言**。
- 判别力实测（变异）：把 `bus.py:220` 的逐条投影去掉（`[m.to_dict() for m in visible]`）→ 全文件跑出 `2 failed`
  （`test_bus.py::test_snapshot_payload_caps_single_message`、`test_bus_bounded_exports.py::test_snapshot_payload_export_is_bounded`），
  而**这两条 run_pattern 端到端测试仍然 passed**。即它们锁不住自己声称要锁的东西。
- 影响：**未造成契约缺口**——`run_pattern` 的 `result["bus"]` 就是 `bus.snapshot_payload()` 的返回值（`patterns.py:458` 直接赋值、无变换），而 `snapshot_payload()` 的二维界已被两条**用真满载 bus**的直接测试锁住（`:166-177` / `test_bus.py:180-203`），变异确实变红。这两条 e2e 测试真实锁的是「键存在 + 接线正确」，那部分它们做到了（`:186` 的 `assert result["bus"]["messages"]` 能抓住键被删）。**不阻塞**。
- 建议：让 worker 的摘要真的超预算即可恢复自述的判别力——把 `PublishThenFinishLLM` 第 2 次 `chat()` 改为返回超长摘要（如 `"y"*6000`），或在 e2e 里直接断言队列中那条的投影来源；同时把 docstring 的自述改成「端到端验证 `result["bus"]` 键经 `snapshot_payload()` 投影接线正确」。

### 无以下问题（核查后确认清白）

- **无循环导入**：`agent/subagent/manager.py` **没有**任何模块级 `agent.subagent.bus` 导入（AST 扫描模块级 import 集合确认）；`bus.py:35` 的 `bus → manager` 单向。四种加载顺序在**新解释器**中实跑均成功：`bus` 先、`manager` 先、`tools.builtin.subagents` 先、`patterns` 先。
- **无第二套口径**：未新造与 `TRANSCRIPT_ITEM_LIMIT` 并行的数字——`BUS_MESSAGE_LIMIT` 直接派生（`bus.py:43`，变异可判）、截断器复用 `manager._clip`（`bus.py:77`）、`BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4` 顺着 `estimate_tokens` 的换算口径（`test_bus_bounded_exports.py:306-308` 锁住 `×4 ==`）。
- **无注入 / 越权 / 信息泄露面变化**：改动只收窄输出体量与新增布尔标志，未新增参数解析、路径、凭据或权限路径。工具描述里插值的只有模块常量（非用户输入）。
- **无假话**：全仓扫描无 bus 截断与 `result_ref`/`summary_ref` 的关联；权威 spec `openspec/specs/subagents/spec.md:171,179` 与 `bus.py:59-61`、`proposal.md:75-78`、`design.md:125-127` 一致地声明「LLM 摘要分支是 advisory、硬界在消费侧 `read()`」。
- **未弱化 CI**：`git diff origin/master...HEAD --stat -- .github/ scripts/ flow/ pyproject.toml uv.lock .gitignore` **为空**。
- **未破坏既有语义**：`_clip` 在「恰好等于上限」时返回 `False`（实跑确认），故出口投影天然幂等，重复投影不会把「没截」报成「截了」；`publish()` 入队契约未改；`compact_summary()` / checkpoint 的 `bus_summary` 仍走队列全文（`manager.py:1492`）。
- **非整数参数非回归**：`limit="5"` / `max_tokens="1000"` 抛 `TypeError`，与改动前 `len(collected) >= "5"` 同样抛错（同一异常类型），非本 change 引入。

## Test Results

环境：`export PATH=/home/happy/.local/bin:$PATH`；本机 `/tmp/.git` **确认存在**（已知环境失败的成因）。

- `uv run pytest tests/agent/subagent/ tests/agent/tools/ -q` → **934 passed**（34.67s）。
- 全量 `uv run pytest -q` → **3013 passed, 9 skipped, 2 failed**（378.59s）。2 个 failed 均为
  `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir,test_malformed_git_file_falls_back_to_scan}`；
  `tests/agent/memory/` 在本 change diff 中**零改动**，`/tmp/.git` 存在 → 确认为本机环境恒失败，与 bus 无关。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 唯一报错为
  `review manifest missing: .../reviews/building-review-manifest.json`（本报告落盘后由 manifest 绑定，属预期）。
- `uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke` → **PASS**（success_rate delta +0.0000，baseline 1.0 → current 1.0）。

### 实跑验证（直接观测行为，不读代码下结论）

| 核查项 | 实测输出 | 结论 |
|---|---|---|
| **D10** 新实例 | `read()[0] is bus._messages[0]` → **False**；读后队列 `len(summary)==30000`、`truncated is False`；`compact_summary()` 读前读后同为 2003 字符且**相同**；返回值 4000 / `truncated True` | ✅ 未原地污染队列 |
| **Q1** 总量维 | 100 条 × 30,000 字，`read(max_tokens=10**9, limit=10**9)` → **2 条 / 8,000 字符**（修复前 100 条 / 3,000,000）；默认 kwargs → 1 条 / 4,000 | ✅ 界住 |
| **Q1 加严** | 1000 条 × 30,000 字，`read(max_tokens=10**18, limit=10**18)` → **2 条 / 8,000 字符** | ✅ 参数越大不出界 |
| `snapshot_payload()` | 100 条满载 → `len==20`、`total==100`、`omitted==80`、总字符 **80,000**（= 20×4000 上界）；1000 条满载 → `20/1000/980/80,000` | ✅ 二维界 + 如实报告 |
| 边界：空 bus | `read()==[]`；`snapshot_payload()=={"messages": [], "max_read_tokens": 2000, "messages_total": 0, "messages_omitted": 0}` | ✅ |
| 边界：恰好等于上限 | 4,000 字 → 不截断（`truncated False`）；4,001 字 → 截到 4,000（`truncated True`） | ✅ 边界正确 |
| 边界：`None` / `0` / 负数 | `limit=None, max_tokens=None` → 5 条（bus 只有 5 条）；`limit=0`/`limit=-5`/`max_tokens=0`/`max_tokens=-1` → 均 1 条（「单条超窗仍返回最新」路径），输出仍 ≤ 上限 | ✅ 非回归 |
| 边界：`max_read_tokens=10` + 单条 30,000 字 | 返回 1 条、4000 字符、`truncated True` | ✅ 「不失明」与「有界」同时成立 |
| 边界：非整数参数 | `limit=5.7` → 5 条；`limit="5"` / `max_tokens="1000"` → `TypeError`；`limit=True` → 1 条 | ✅ 与改动前同型异常，非回归 |
| **R1**（独立脚本，非 change 自带测试） | stub LLM 返回 6,000 字 → 回包 **4000** / `summary_truncated` **True** / `token_count` **1000**；队列 **6000** / `truncated` **False**；`read()` 读回 4000/True | ✅ R1 真修好 |
| **R2**（变异） | `BUS_MESSAGE_LIMIT = 4000` → 该测试 **1 failed**（Round 1 同变异为 passed） | ✅ R2 真修好 |
| **R4**（归一化逐字比对） | 两份 delta 与两份权威 spec 的 Requirement 正文归一化后**相同**；`workers[]`/顶层 `summary` 限定段两处都在 | ✅ 无漂移 |
| **导入无环** | `manager.py` 模块级 import 集合不含 `agent.subagent.bus`；四种加载顺序在新解释器均 OK | ✅ |
| run_pattern e2e 真实内容 | bus 里 1 条、`len==4`（`'done'`） | ⚠️ 见 Issues #3 |

### 变异验证复核（本人独立改坏 → 跑测试 → 确认红/绿 → `git checkout` 还原）

| # | 变异 | 结果 |
|---|---|---|
| M-DERIVE | `BUS_MESSAGE_LIMIT` 改字面量 `4000` | **1 failed** ✅（R2 修复有效；Round 1 为 passed） |
| M-REPLY | 回包去掉 `_bounded_message` 投影（还原成 `msg.to_dict()`） | **1 failed** ✅（R1 回归测试有判别力） |
| M1 | `read()` 截断改 identity（`return collected`） | **7 failed** ✅ |
| M2 | `snapshot_payload()` 去条数上限 | **2 failed** ✅ |
| M3 | `read()` 不钳 `max_tokens` | **1 failed** ✅ |
| M4 | `replace` 改回原地赋值 | **3 failed** ✅ |
| M5 | 发布侧闸门 `>=` 改回 `>` | **1 failed** ✅ |
| M6 | 发布侧 `max_tokens` 不钳 | **3 failed** ✅ |
| M7 | `read()` 不钳条数（`limit` 直传） | **1 failed** ✅ |
| M-SNAP-PROJ | `snapshot_payload()` 去掉逐条投影 | **2 failed** ✅（但两条 run_pattern e2e 未变红 → Issues #3） |

还原后基线复跑：`tests/agent/subagent/test_bus.py + test_bus_bounded_exports.py` **32 passed**；
收尾 `git status --porcelain` **为空**（工作区干净）。

## 结论

Round 1 的四项问题**逐条实跑确认已真修好**，不是纸面声明：R1——我用自写脚本（不借 change 自带测试）构造「如实但超预算」的 6000 字摘要，实测回包已被投影到 4000 且带 `summary_truncated`、队列仍保留 6000 全文，且把回包投影去掉后新回归测试立刻变红；R2——把派生改成字面量 `4000` 后该测试由 Round 1 的 passed 变为 failed，判别力是真的；R3——`.gitignore` 与 `handoff.json` 均已清干净；R4——两份 delta 与两份权威 spec 的 Requirement 正文归一化后逐字一致。主交付本身经得起独立复算：`read()` 与 `snapshot_payload()` 两条模型面出口在单条（≤ 4000）与总量（≤ 20 条 / ≤ 80,000 字符）两个维度都有固定上界，界施加在 `snapshot_payload()` 方法本身，D10 用 `dataclasses.replace` 正确落地（读后队列与 `compact_summary()` 分毫未动），D9、Q1、Q6、D6 全部实测成立；Q1 在 100 条与 1000 条满载、`10**9` 与 `10**18` 参数下都被压到 2 条 / 8,000 字符（修复前 100 条 / 3,000,000）。九组变异（含对 R1 修复与 R2 修复的定点变异）全部能让对应测试变红，还原后工作区干净；全量 pytest 3013 passed（仅 2 个与本 change 无关的本机环境失败，成因 `/tmp/.git` 已确认）、OpenSpec strict validate 30 passed、artifact checker 只剩预期中的 manifest 缺失、benchmark-gate PASS、CI/脚本/flow 配置零改动、导入无环由新解释器四种加载顺序实证。剩余三项均为低优先级、且不造成任何契约缺口：两处文档仍把发布侧的界归因于阈值钳制（结论已真、因果表述不准，相邻段落已给出正确口径）、`max_read_tokens=2000` 这一既有键与实际快照体量不再自洽（属修复前遗产）、两条 run_pattern e2e 测试的实际判别力弱于其 docstring 自述（其真实锁的是接线，二维界由直接测试锁住）。按判定标准「所有 `[x]` 有真实实现 + 无未解决的中等以上问题 + 测试通过」，本 change 判定 **PASS**，可进入收尾（spec 同步已完成，归档 + 生成 review manifest）。
