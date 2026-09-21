# Building Review — fix-issue-213-transcript-item-bound（Round 1）

我是**独立代码审阅者（零记忆，不继承任何开发上下文）**。本会话未读过开发者的任何对话、推理或
先前会话产物；下面每条结论只来自 (a) `git diff 7c23059...HEAD` 的实际代码、(b) change 文档与
issue #213 原文、(c) 我在本仓库**实跑**的命令与 `/tmp/review_213/` 下的探针输出。所有「实现声称
X」都逐条对代码验证过；未验证的明确写「未能验证」。

**方法的核心是变异验证**：把实现逐条改坏（6 个变异体），跑 change 自己的回归测试，看是否变红；
凡是「改坏了测试还全绿」的地方，就是断言的覆盖漏洞。仓库文件在所有变异后已逐一还原。

## Reviewer

- run id: review-fix-issue-213-2026-09-21-r1
- 时间: 2026-09-21
- 审阅对象:
  - 代码 diff: `git diff 7c23059...HEAD`（`agent/subagent/{manager,patterns,scheduler}.py`、
    `agent/tools/builtin/subagents.py`、`web/session.py`、`web/static/{index.html,workflow_transcript.js}`）
  - 文档: `openspec/changes/fix-issue-213-transcript-item-bound/{proposal,design,diagnosis,tasks}.md`
    + `specs/{subagents,agent-runtime}/spec.md` + `reviews/grill-design.md` + `docs/agent-internals.md`
  - 测试: `tests/web_tests/test_workflow_node_transcript.py`（新增 8 条）、
    `tests/agent/subagent/test_result_representations.py`
- 基线: `7c23059`（master） → head `022cc46`
- 审阅方法（实跑命令）:
  - `uv run pytest -q tests/web_tests/test_workflow_node_transcript.py -p no:randomly` → 33 passed
  - `uv run pytest -q tests/agent/subagent/ -p no:randomly` → 516 passed
  - `uv run pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py` → 337 passed
  - `uv run pytest -q tests/web_tests/test_workflow_graph_browser.py -p no:randomly`（3 次，含与 `test_browser.py` 并发）→ 3×20 passed
  - `uv run pytest -q "tests/agent/memory/test_persistent.py::TestFindScopeRoot" -p no:randomly` → 2 failed（环境致因，见 Test Results）
  - `uv run python /tmp/review_213/probe_{d,leak,e2e,nonwf,bus,m7,m8,probe_bus}.py`（8 个探针）
  - **变异验证 6 个**：M1 `_bounded_content`→identity；M2 路由取或→只看本层；M3 envelope 恒 full；
    M4 envelope 用 `max_tokens` 预算；M5 `_worker_entry` 去掉 `result_ref`；M5b `_worker_entry` identity；
    M6 `_bounded_summary` 忽略 `has_ref`；M7 落盘路径读属性。（每次改完即跑测试，随后 `cp` 还原）
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` → passed
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-213-transcript-item-bound --strict` → valid
  - `gh api repos/Xingkai98/asterwynd/issues/213`、`gh issue list --search ...`
  - 收尾 `git status --short` → 空（零残留，见文末）

## Verdict

**CHANGES_REQUESTED**

理由：出口 2/3 的修复在本 change **自己认定为核心威胁**的那条路径上不成立——run envelope 里
另一个字段 `bounded_summary` 仍在 `max_tokens` 放大时原样返回子 agent 全文（实测 30,000 字全量
进模型上下文），而 `max_tokens` 由发起调用的模型在 `spec.nodes[].max_tokens` / `worker_max_tokens`
里自设、无上界校验。这正是 design D3 推翻初版的理由，但它被留在了同一个返回体里。

## Tasks Verification

| tasks.md 条目 | 状态 | 证据（文件:行号 或 命令输出） |
|---|---|---|
| 新增 `TRANSCRIPT_ITEM_LIMIT = 4000` + 旧名降为别名 | ✅ 真实存在 | `agent/subagent/manager.py:83`、`:87`；`grep` 全仓仅此 2 处定义 |
| `_format_run_envelope` 用固定上限、不读 `max_tokens` | ✅ | `manager.py:1553-1556` 调 `_bounded_content`（内部用 `TRANSCRIPT_ITEM_LIMIT`），未见 `max_tokens` |
| 抽 `_clip`，`_bounded_arguments` 薄封装，新增 `_bounded_content` | ✅ 行为等价 | `manager.py:90-116`；签名/返回值与旧实现逐字等价（见 Issue 6 复核） |
| `inspect_transcript` summary 分支截断 + `summary_truncated` | ✅ | `manager.py:1109-1127`；变异 M1 使 3 条测试变红 |
| `inspect_transcript` recent_messages 逐条截断 content | ✅ | `manager.py:1144`；变异 M1 使 `test_inspect_message_content_is_bounded` / `..._tool_result_...` 变红 |
| `_format_run_envelope(..., full_summary=False)` 默认 bounded | ✅（但见 Issue 1） | `manager.py:1530-1557`；变异 M3 使 3 条测试变红 |
| 调度器内部消费点显式传 `full_summary=True` | ✅ | `scheduler.py:2172-2174`；唯一 `_launch_run`/`_await_run` 出口，`state.summary` 取到全文（`scheduler.py:1700`/`:1723` 消费） |
| `_worker_entry` summary 走固定上限 + 补 `result_ref` | ⚠️ 实现存在、测试未锁死 | 实现 `patterns.py:352-368`；但变异 M5 去掉 `result_ref` 后 **549 passed 全绿**（见 Issue 3） |
| `_bounded_summary` 标记只在确有 ref 时提 result_ref | ✅ | `manager.py:53-73`；实测：非 workflow run 尾部为 `…[truncated]`（probe_d 输出） |
| `to_result_dict()` 增 `summary_chars` | ✅ | `manager.py:219`；`test_result_representations.py:96` 断言 `== len(LONG)` |
| `web/session.py` 取或 + 透传 | ✅ | `web/session.py:762-764`；变异 M2 使 `test_route_content_truncated_ors_producer_flag` 变红 |
| `workflow_transcript.js` content 截断 UI 提示 | ✅ | `web/static/workflow_transcript.js:316-319`、`:384`；`index.html:175` 版本号 v2→v3 |
| 工具描述校正、不加第二道截断 | ✅ | `agent/tools/builtin/subagents.py:188-193`；execute 内无第二道 `_clip` |
| 测试：7 条口径 + 假话 + 常量 | ✅ 存在且多数有判别力 | 变异 M1/M2/M3/M4/M6 各自让对应测试变红 |
| 测试：**三处同值**断言升级 | ⚠️ **未按字面实现** | `test_workflow_node_transcript.py:624` 仍是**两处**比较（`TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT`），无 `TRANSCRIPT_ITEM_LIMIT` 字面出现；因别名赋值而**传递等价**，契约仍被锁住，但与 tasks 文字不符 |
| 测试：变异验证（identity / 只看本层 / full） | ✅ 我独立复跑成立 | M1/M2/M3/M4/M6 全红 |
| 测试：`tests/agent/subagent/` 全量通过 | ✅ | 516 passed |
| 文档：`diagnosis.md` 6 章 | ✅ | 文件存在，含 Symptom/Reproduction/Evidence/Root Cause/Recommended Direction/Regression Tests |
| 文档：spec delta 两个 MODIFIED | ✅ 已同步到 delta | `specs/subagents/spec.md`、`specs/agent-runtime/spec.md` |
| 文档：`docs/agent-internals.md` 更新 | ✅ | `git diff` 显示 inspect 示例与新契约一致 |
| 文档：关键词扫描 docs/README/CONTEXT | ✅（扫描痕迹可见） | `docs/agent-internals.md` 已改；其余未见漂移 |
| `docs/openspec-change-backlog.md` 登记 | ✅ 已登记 | backlog diff 新增「第十七批」条目，`workflow-events.jsonl` 有 `backlog_updated` 事件 |
| 全量 pytest 2989 passed / 2 环境失败 | 部分独立验证 | 只复跑了相关子集（见 Test Results）；memory 两条我独立确认与本 change 无关 |

## Issues

### Issue 1（severity: blocker）

- 位置: `agent/subagent/manager.py:220-222`（`to_result_dict` 的 `bounded_summary`）经
  `manager.py:1551-1556`（`_format_run_envelope`）进入模型面
- 描述: **出口 2/3 的 bounded 承诺不成立。** `_format_run_envelope` 只裁剪了 `summary` 键，
  同一返回体里另一个键 `bounded_summary` 仍由 `_bounded_summary(self.summary, self.max_tokens)`
  生成，预算是 `max(2000, max_tokens*4)`——**随 run 预算浮动，而 run 预算由发起调用的模型自设
  且无上界校验**。`max_tokens` 足够大时 `bounded_summary` 就是子 agent 全文。
  这正是 design D3 推翻初版方案、改选 `TRANSCRIPT_ITEM_LIMIT` 的理由，但那条论证只落在
  `summary` 键上，**未清理同一 dict 里的 `bounded_summary`**；spec delta
  `specs/agent-runtime/spec.md` 写的「返回给模型面的 run envelope SHALL bounded …… SHALL NOT
  默认返回子 agent 的全文输出」因此被违反。
- 证据（实跑，非推断）:
  - 直调 `to_result_dict`（`/tmp/review_213/probe_leak.py`）：
    ```
    max_tokens=    None  summary=  4000  bounded_summary=  2013  整包 JSON=  6406  全文在包内=False
    max_tokens=   50000  summary=  4000  bounded_summary= 30000  整包 JSON= 34393  全文在包内=True
    max_tokens=  500000  summary=  4000  bounded_summary= 30000  整包 JSON= 34394  全文在包内=True
    ```
  - **端到端经真实工具**（`/tmp/review_213/probe_e2e.py`：模型自撰 spec `nodes[0].max_tokens=500000`
    → `WorkflowScheduler.run` → `GetSubagentRunTool.execute`）：
    ```
    max_tokens = 500000
    工具返回 JSON 总长        : 34718
    payload['summary'] 长度   : 4000      ← 本 change 修好的那一份
    payload['bounded_summary']长度: 30000  ← 全文，未被约束
    全文仍在返回里? -> True
    ```
    对照 issue #213 原文的「修复前工具返回 34,507 字符」——**该函数在 500000 预算下返回 34,718
    字符**，比修复前**更大**。
  - `max_tokens` 的无界性我独立复核：`agent/subagent/workflow.py:451-454` 的 `_positive_int`
    只校验正整数、无 maximum（`_parse_node_max_tokens` 在 `:601-604` 走它），
    `RunPatternTool.params` 是无 schema 约束的 `object`（`subagents.py:386-390`）经
    `patterns._worker_budget`（`patterns.py:65-77`）落到 `node.max_tokens`。
  - 回归测试**抓不到**：`test_run_summary_limit_does_not_scale_with_max_tokens`
    （`tests/web_tests/test_workflow_node_transcript.py:734-758`）确实把 `run.max_tokens` 设为
    500000，但它只断言 `len(payload["summary"]) <= TRANSCRIPT_ITEM_LIMIT`——恰好在
    `bounded_summary` 已是 30000 的同一 payload 上通过。
- 建议: 三种改法任选（都小）：(a) `to_result_dict` / `_format_run_envelope` 里把
  `bounded_summary` 也按固定上限 `_clip` 一次；(b) 模型面 envelope **移除** `bounded_summary`
  键（它与 `summary` 语义重复，且设计已把 `summary` 定为唯一的模型面字段）；(c) 保留字段但让
  `_bounded_summary` 的预算同样钳到 `max(BOUNDED_SUMMARY_CHARS, TRANSCRIPT_ITEM_LIMIT)`。
  并补一条**按整包 JSON 长度**断言的回归测试（断言「工具返回体不含全文」），否则同一个洞
  会以「换个键再犯」的形式复发。

### Issue 2（severity: major）

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/proposal.md:87`
- 描述: **Non-Goal 的假话没被改掉。** `design.md:221-222` 明确写「原 Non-Goal 那句『bus 已有各自的
  bounded 口径』是**假话**，已删除；改为下面的如实描述，并另立 issue 跟踪」，`grill-design.md` 的
  Q2 用户确认也要求「Non-Goal 措辞必须改成如实描述」。但 proposal.md 该句**原样保留**：
  ```
  - **不动 bus / `ReadWorkflowResult` / `GetWorkflow`**：它们已有各自的 bounded 口径
    （`ReadWorkflowResult` 分页 + `total_chars`/`truncated`；`GetWorkflow` 走
    `parent_envelope()`，节点文本已裁到 `_PARENT_FIELD_LIMIT`）。
  ```
  括注只替 `ReadWorkflowResult` / `GetWorkflow` 举证，`bus` 被并列进来却没有任何依据——而
  grill 与我都**实测证伪**了它（见证据）。仓库明令禁止写假话，且该句在 proposal（读者第一入口）
  里，design 的「已删除」声明与实际不符。
  连带：Q2 要求「bus 另立 issue」，我在 tracker 上**未找到**任何 bus 相关 issue
  （`gh issue list --search "ReadBus|snapshot_payload|bus 出口"` 无命中，最新 issue 号为 220）。
- 证据:
  - `/tmp/review_213/probe_bus.py`：`bus.read()` 单条 30,000 字消息 → 返回 **30,122 字符**；
    `bus.snapshot_payload()` 100 条 × 1600 字 → **172,703 字符**（与 grill 的 173,303 同量级）。
    该出口经 `RunPatternTool`（`patterns.py:453` 的 `result["bus"] = bus.snapshot_payload()`）
    进模型上下文。
  - `grep -n "已有各自的 bounded 口径"` → 命中 `proposal.md:87`（未被删除）。
  - `gh issue list --state all --search ...` → 无 bus issue。
- 建议: 把 proposal.md 的 Non-Goal 按 Q2 改成如实描述（「bus 出口本次不覆盖，**实测无界**
  （单条 30,122 / 快照 172,703 字符），另开 issue 跟踪」），并**实际创建**跟踪 issue、回填编号；
  或若本 change 决定一并纳管，则改实现而非改文字。

### Issue 3（severity: major）

- 位置: `tests/web_tests/test_workflow_node_transcript.py:897-900`
- 描述: **新增测试里有一条恒真断言。** `test_worker_entry_summary_is_bounded_and_navigable` 的
  (b) 半部分写成条件式：
  ```python
  if "result_ref" in entry["summary"]:
      assert entry.get("result_ref"), ...
  ```
  但 `_worker_entry` 用的是 `_clip`（`manager.py:90-100`），它**不追加任何标记文本**——所以
  `"result_ref" in entry["summary"]` **恒为 False**，`:898` 的断言是一行永不执行的死代码。
  测试名与 docstring 声称「条目必须带 result_ref」，实际从未验证。
- 证据（实跑，非推断）:
  - `/tmp/review_213/probe_d.py` `[3]`：`'result_ref' textual marker in summary?: False`。
  - **变异 M5**：把 `patterns.py:365-367` 的
    `entry["result_ref"] = getattr(run, "result_ref", None)` 整行删掉 →
    `uv run pytest -q tests/agent/subagent/ tests/web_tests/test_workflow_node_transcript.py`
    → **549 passed**（全绿，无一条变红）。是 Q5 决策（补 result_ref，否则在出口 4 复制假话）的
    **零保护**。
- 建议: 改成无条件断言两条不变量：`entry["summary_truncated"] is True` 且
  `"result_ref" in entry`（有 workflow 身份的 run）；并在同一条测试里补一个
  **无 workflow 身份**（`result_ref is None`）的对照，断言条目**不含**「全文在 result_ref」字样。
  否则删掉这半条，别留死断言。

### Issue 4（severity: minor）

- 位置: `agent/subagent/manager.py:1362-1365`
- 描述: D3b 的「顺序陷阱」修复（落盘路径**显式**传 `has_ref=True`，不读属性）**没有测试保护**。
  实现本身正确且必要，但任何回归（改回读属性）都会静默把落盘的 `summary_ref` 从「可导航」降级为
  「只说到此为止」，且测试不变红。
- 证据: **变异 M7** —— 把 `has_ref=True` 改成
  `has_ref=bool(run.result_ref or run.summary_ref)`（模拟 grill 指出的顺序陷阱）：
  - `/tmp/review_213/probe_m7.py` 输出：`summary_ref tail: '…\n…[truncated]'`、
    `says navigable?: False`（而正确实现是 `…[truncated; full result in result_ref]`）；
  - 同一变异下 `uv run pytest -q tests/agent/subagent/ tests/web_tests/test_workflow_node_transcript.py`
    → **549 passed**（全绿）。
- 建议: 在 `test_workflow_result_refs.py` 补一条断言：workflow run 的
  `store.load(run.summary_ref)` **包含** `result_ref` 字样（且 `run.result_ref` 非空）。
  这是能杀死 M7 的最小测试。

### Issue 5（severity: minor）

- 位置: `agent/subagent/manager.py:219`（`summary_chars`）对比 `manager.py:1553-1556`（envelope 裁剪）
- 描述: `summary_chars` 的语义是**全文长度**，而同一 payload 的 `summary` 在默认出口是**截断后长度**。
  两条路径上 `summary_chars` 的语义**一致**（恒为全文长度），但字段名紧挨着一个被截断的 `summary`，
  极易被下游/前端误读为 `len(summary)`（非 workflow run 实测 `summary=4000` /
  `summary_chars=30000` 并存）。
- 证据: `/tmp/review_213/probe_d.py` `[1]`：`summary len: 30000 … summary_chars: 30000`（记录层）；
  `/tmp/review_213/probe_e2e.py`：`payload['summary']=4000` 而 `summary_chars` 仍为 30000。
- 建议: 保持实现，但在字段旁补一句 schema 说明（或改名 `summary_full_chars` / 增
  `summary_returned_chars`），让「同一 payload 里两个数」有明确语义。

### Issue 6（severity: minor）

- 位置: `tests/web_tests/test_workflow_node_transcript.py:876-892`
- 描述: 出口 4 的测试**绕过 `RunPattern`**，直接调 `_worker_entry`。实现路径
  `run_pattern → _legacy_result → _workers_from_node → _worker_entry` 中任何一环改写
  （例如 `_legacy_result` 把 `run.summary` 另塞进 `result["summary"]`）都不被这条测试覆盖。
- 证据: `tests/web_tests/test_workflow_node_transcript.py:889-892` 直接
  `from agent.subagent.patterns import _worker_entry`；`grep -rn "run_pattern(" tests/` 未见
  断言整包有界的测试（`_legacy_result` 的 `result["summary"]`= `"\n".join(parts)` 走的是 worker 的
  bounded summary，逻辑上正确，只是没被端到端锁住）。
- 建议: 加一条经 `RunPatternTool` 的端到端断言（N 个 worker 各产出 30000 字时，整包长度有界）。

### Issue 7（severity: minor）

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/tasks.md:44-45` 与
  `tests/web_tests/test_workflow_node_transcript.py:624`
- 描述: tasks 写「把既有的『两个 4000』断言**升级为三处**同值」，实际仍是两处比较，
  `TRANSCRIPT_ITEM_LIMIT` 未出现在任何断言里。因 `TOOL_CALL_ARGUMENT_LIMIT` 是
  `TRANSCRIPT_ITEM_LIMIT` 的模块级别名（`manager.py:87`），该断言**传递等价**地锁住了三处同值，
  spec 的「该相等关系 SHALL 有测试机械锁定」仍成立——属**文字与实现不符**，不是功能缺陷。
- 证据: `grep -n "TRANSCRIPT_ITEM_LIMIT ==" tests/` → 无命中；`test_workflow_node_transcript.py:624`
  为 `assert TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_CONTENT_LIMIT`。
- 建议: 二选一——把 tasks 文字改成实际情况，或把断言的显式比较补成三处（推荐后者，意图更直白）。

### 未构成 issue 的两处「疑似假话」（我实测后判定**不成立**）

1. **`patterns._worker_entry` 在无落盘时给 `result_ref: None` 会不会让模型看到「全文在 None」？**
   ——**不会**。`_clip` 不加标记文本，summary 里没有「result_ref」字样，`result_ref: None` 只是
   一个空字段（`/tmp/review_213/probe_d.py` `[2]`：`summary_truncated: True`、`result_ref: None`、
   `'result_ref' in summary: False`）。没有引入新的假话。
2. **D4 的假话修复是否真的生效？**——**生效**。非 workflow run（`workflow_id=None`、
   `result_ref=None`、`summary_ref=None`）的 `bounded_summary` 尾部是 `…[truncated]`，不含
   `result_ref` 字样（`/tmp/review_213/probe_nonwf.py`：`假话（声称 result_ref）?: False`）；
   workflow run 的落盘件则保留导航（`probe_m7` 正确实现分支输出 `full result in result_ref`）。

## Test Results

**通过（本 change 相关面）**

| 命令 | 结果 |
|---|---|
| `pytest -q tests/web_tests/test_workflow_node_transcript.py -p no:randomly` | 33 passed |
| `pytest -q tests/agent/subagent/ -p no:randomly` | 516 passed |
| `pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py` | 337 passed |

**变异验证（每条都在改完后还原；`git status --short` 收尾为空）**

| 变异 | 改动 | 结果 | 判别力 |
|---|---|---|---|
| M1 | `_bounded_content` → identity | 5 failed（transcript 测试） | ✅ 有效 |
| M2 | 路由 `content_truncated` → 只看本层 | 1 failed（`test_route_content_truncated_ors_producer_flag`） | ✅ 有效 |
| M3 | envelope 恒返回全文 | 3 failed（含 `test_result_representations.py:90`） | ✅ 有效 |
| M4 | envelope 用 `max_tokens` 预算 | 1 failed（`test_run_summary_limit_does_not_scale_with_max_tokens`） | ✅ 有效 |
| M5 | `_worker_entry` 去掉 `result_ref` | **549 passed（全绿）** | ❌ **漏网**（Issue 3） |
| M5b | `_worker_entry` summary → identity | 1 failed | ✅ 有效 |
| M6 | `_bounded_summary` 忽略 `has_ref` | 1 failed（`test_truncation_marker_does_not_promise_missing_ref`） | ✅ 有效 |
| M7 | 落盘路径读属性（顺序陷阱） | **549 passed（全绿）** | ❌ **漏网**（Issue 4） |

结论：change 的 7 条新测试里，M1/M2/M3/M4/M6 都有真实判别力（输入确实用了 30000 字，
不是「返回 ≤4000」的恒真构造）；但**有 2 个真实回归点无测试保护**，且新增测试中**存在 1 条死断言**。

**H 声称的独立核验**

- **(i) `TestFindScopeRoot` 两条在 master 上就失败 → 成立。**
  `uv run pytest -q "tests/agent/memory/test_persistent.py::TestFindScopeRoot"` → 2 failed
  （`test_returns_none_for_non_git_dir`、`test_malformed_git_file_falls_back_to_scan`）。
  两条失败的直接原因是 `_find_scope_root` 从 `/tmp/pytest-of-happy/.../a/b` 向上走时命中了
  **`/tmp/.git`**（该目录实际存在，`ls -la /tmp | grep '^d.*\.git'` 可见，属环境产物，与本仓库无关）。
  且 `git rev-parse 7c23059:agent/memory/persistent.py` 与 HEAD 版本**逐字节相同**
  （`4779b9660fd439ab9baba4d1043beee622c481c5`），`git diff 7c23059...HEAD -- tests/agent/memory/`
  为空。**该失败与本 change 无关，声称成立。**
- **(ii) `test_workflow_graph_browser.py` 是负载敏感的既存 flake → 未能复现，但也无法证伪。**
  我跑了 3 次（其中一次与 `tests/web_tests/test_browser.py` 并发制造负载）：
  `20 passed` / `20 passed` / `20 passed`（各约 60s）。该文件相对 base **零改动**
  （`git diff 7c23059...HEAD --stat` 无输出），所以分支与 master 对该文件行为一致。
  开发者报告的 6 failed / 1 failed / 20 passed 我**未能复现**，但因其自述为负载敏感型，
  我不下「声称不实」的结论——可确认的是**它不是本 change 引入的回归**。

**门禁**

| 命令 | 结果 |
|---|---|
| `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed`（exit 0） |
| `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-213-transcript-item-bound --strict` | `Change 'fix-issue-213-transcript-item-bound' is valid`（exit 0） |

注：checker 当前通过的原因之一是 `tasks.md` 尚有 4 条未勾选（spec 同步 / backlog 移除 /
审阅 / manifest），故 building-review + manifest 的强制检查**尚未触发**；收尾勾选后必须补
manifest，否则门禁会红。

**零残留证据**：审阅结束 `git status --short` 输出为空（仅本报告文件为新增，见「审阅产物」）。
所有探针脚本位于 `/tmp/review_213/`，仓库文件在每次变异后均已 `cp` 还原。

## 结论

实现的主体是扎实的：4 个出口里 **出口 1（`InspectSubagentTranscript` 的 content/summary）、
出口 4（`RunPattern` worker summary）确实被真正修好**，`full_summary` 默认值翻转没有打破任何内部
消费点（调度器唯一取全量的地点 `scheduler.py:2172` 正确传了 `True`，聚合器测试绿），D4 的假话
修复经我独立实测**确实生效**，`_clip` 重构行为等价，HTTP 取或的判别力经变异 M2 证实，bus 无界的
事实描述与我的实测一致（30,122 / 172,703 字符）。

但 change **不能以现状合入**：

1. **blocker**——出口 2/3 的修复被同一 payload 里的 `bounded_summary` 抵消。在模型自设的
   `max_tokens=500000` 下，`GetSubagentRunTool` 实测返回 **34,718 字符**，其中 30,000 字符是子 agent
   全文——比 issue #213 报告的修复前值（34,507）还大。这正是 design D3 自己论证过并否决的
   「界由被检视方决定」路径，只是换了个键继续存在。
2. **major**——proposal 的 Non-Goal 仍写着 design 已认定并声称删除的假话（bus「已有 bounded 口径」），
   且 Q2 承诺的跟踪 issue 未创建。
3. **major**——新增测试里有一条**永不执行的死断言**（`if "result_ref" in entry["summary"]`），
   它对应的 Q5 决策实测零保护（变异 M5 全绿）。

剩余风险：`TestFindScopeRoot` 两条与浏览器 flake 均与本 change 无关（前者已确认是 `/tmp/.git`
环境致因，后者文件零改动且我 3/3 未复现）；`summary_chars` 语义、出口 4 缺少端到端测试、
tasks 文字与实际不符属 minor，可在同一轮修复中一并处理。

建议处置：修 Issue 1（二选一：`bounded_summary` 一并钳制或从模型面 envelope 移除，并补
「整包不含全文」的回归测试）→ 补 Issue 3 / Issue 4 的测试 → 改 Issue 2 的文字并建 bus issue →
重跑 `/review-loop` 第 2 轮。
