# Building Review: fix-issue-251-sse-done-warning

## Reviewer

- run id: `b38c68be-3c78-49a8-b48b-3fa4c3f9ce94`（独立零记忆 subagent，未继承开发上下文；结论只来自实读代码 / 实跑输出 / change 文档）
- 时间：2026-09-26
- base: `14f6e24`（master），被审 head: `1b4cf88`
- 审阅方法（作者自述一律不作依据）：
  - 逐条核对 `tasks.md` 的 `[x]` 是否真的完成，带 `文件:行号` 证据
  - **base/head 对照探测**：同一 Python 探测脚本直调 `_stream_events`，逐输入比对事件序列与告警条数
  - **4 组变异验证**（A–D），每次改完立即 `git checkout -- agent/llm.py` 还原
  - 独立实跑 OpenSpec strict validate 与 artifact checker
  - 独立核验「预先存在的失败」（在独立 worktree `14f6e24` 上跑同一测试）
  - 收尾核验工作区 hash 与 head blob 一致（`ad7e046…`）

## Verdict

**PASS**

实现正确、判别力覆盖了三个具名失败模式、spec 逐字一致、门禁全绿。仅 6 条 low-severity 问题，不阻塞。

**最关键的一条（失败模式 B）已被真实拦住**：把整条 `logger.warning` 删掉（即本 change 的失败模式——「用静默换安静」）→ `test_genuinely_bad_sse_line_still_logs_warning` **变红**（`assert 0 == 1`）。

### 审阅后追加（`head` 之后）

审阅的 Issue 1 已落实：补 `test_done_like_variant_is_not_treated_as_sentinel`，锁定 design D2 的「精确匹配」意图（变异验证：把 `==` 改成 `startswith` 后该测试变红——此前该变异能全身而过）。Issue 3/4/5 的记账与文案已对齐。

## 任务逐项验证

| 任务 | 状态 | 核实方式与证据 |
|---|---|---|
| 0.1 端到端复现 | ✅ | 无法独立重跑（需真实凭据），但其代码路径用 mock 本地重建；base 上 `data: [DONE]` 确实报 1 条告警 |
| 0.2–0.5 issue/诊断/设计/RIR | ✅ | `proposal.md` 关联 #251；`diagnosis.md`/`design.md`（D1/D2/D4/D5）齐全；`research_tier: exempt` 且 reason 引用了 archive 路径与协议事实，非占位 |
| 1.1 delta spec | ✅ | 存在，3 个 Scenario 齐全 |
| 1.2 落地 spec | ✅ | **逐字一致**（delta 正文是主规格的精确子串，实测 `True`） |
| 1.3 Impact Analysis / RIR | ✅ | `proposal.md` 相应节 |
| 2.1 正向测试 | ✅ | 存在；base 探测确认修复前 RED（`good_then_sentinel` 报 1 条） |
| 2.2 反向守护 | ✅ | 存在；base 探测确认修复前 RED（坏行 + 哨兵共 **2** 条） |
| 2.3 变异验证 | ✅ | 审阅者重做，见下 |
| 3.1/3.2 常量+辅助+前置放行 | ✅ | `agent/llm.py` 的常量、`_is_sse_stream_end()`、放行在 `json.loads` **之前** |
| 3.3 事件序列零变化 | ✅ | base/head 事件序列逐字相同 |
| 4.1 单文件测试 | ✅ | 13 passed（审阅时）→ 14 passed（补 Issue 1 测试后） |
| 4.2 全量 pytest | ⚠️ 已修正文案 | 实测 `3 failed, 3066 passed`，均为**预先存在**环境失败（独立核验：`14f6e24` 上同样失败）。任务文案已补明 |
| 4.3 端到端复验 | ✅ | 同一代码路径已由探测覆盖 |
| 4.4 strict validate | ✅ | 审阅者实跑 `29 passed, 0 failed` |
| 4.5 artifact checker | ✅ | 审阅者实跑 `OpenSpec artifact checks passed`（exit 0） |
| 5.1 / 5.3 / 5.4 / 5.5 | — | 5.1 本报告；5.3 已勾（见 Issue 4）；5.4/5.5 属待办收尾 |

无「勾了没做」的严重项。

## Issues

### 严重

无。

### 中

无。

### 低

**Issue 1 — `startswith` 变异能全身而过，D2 设计意图未被测试锁定｜已修复**

`test_legal_json_containing_done_literal_is_parsed_not_skipped` 依赖 `events == ["assistant_delta","complete"]`，而 `startswith("[DONE]")` 不误伤含字面量的**合法 JSON**，故把判据从 `strip() == SENTINEL` 改成 `strip().startswith(SENTINEL)` 后 **13 条全绿**。`design.md` D2 明确以「`startswith` 会误吞 `[DONE]extra` 这类真坏行」为由否决了它，但该理由无测试锁定。
**处置**：已补 `test_done_like_variant_is_not_treated_as_sentinel`（`data: [DONE]extra` 须仍告警恰好 1 条）；变异验证 `== → startswith` 后该测试**变红**，设计意图现已锁定。

**Issue 2 — `data:`（无尾随空格）被忽略，属未改变的历史行为**

不匹配 `startswith("data: ")`，被完全忽略、不告警。base 与 head 行为一致，非本 change 引入，仅记录为已知边界。

**Issue 3 — 任务 4.2 `[x] 全量 pytest 通过` 文案与事实不符｜已修正**

实测 3 条失败（tree-sitter grammar 缺失、`TestFindScopeRoot` 两条因本机 `/tmp` 是 git 仓库）。审阅者独立核验其预先存在。任务文案已补明「除预先存在的 3 条环境失败外通过」。

**Issue 4 — 任务 5.3 未勾选但其工作已完成｜已修正**

`docs/openspec-change-backlog.md` 已更新、`workflow-events.jsonl` 已有 `backlog_updated` 事件，但 `tasks.md` 未勾。属记账不一致，无功能影响。已勾选。

**Issue 5 — 第三条测试 docstring 与 spec 举例的数据形态不一致｜已修正**

docstring 写 `[DONE]` 字面量、spec Scenario 3 举例 `{"text":"[DONE]"}`，而实际喂 OpenAI chunk 形态。语义等价、覆盖到位。已在 docstring 注明两者关系。

**Issue 6 — 审阅起始时工作区带一处未提交的变异改动（非交付缺陷）**

审阅者首次 `git status` 看到 `M agent/llm.py`（warning 被整条删除）——那是实现方在同一 worktree 并发跑变异测试留下的瞬时状态。**已提交的 head 正确**：`git show 1b4cf88:agent/llm.py` 含 `logger.warning`，且工作区 hash 与 head blob 一致（`ad7e046…`），审阅结束时 `git status --short` 为空。仅作说明。

## 变异验证实测

全部由审阅者亲手改 `agent/llm.py` 后跑测试，每次立即还原：

| 变异 | 结果 | 期望 | 判定 |
|---|---|---|---|
| **A** 整条删掉 `logger.warning`（只留 `continue`） | `test_genuinely_bad_sse_line_still_logs_warning` **RED**（`assert 0 == 1`） | 应红 | ✅ 失败模式被拦住 |
| **B** `_is_sse_stream_end` 短路为 `False` | **3 failed, 10 passed**（三条新测试全 RED） | 应红 | ✅ 判别力足 |
| **C** `==` 改为 `in` | `test_legal_json_containing_done_literal_...` **RED** | 应红 | ✅ |
| **D** `==` 改为 `startswith` | **13 passed**（全绿） | 按 D2 应红 | ⚠️ 见 Issue 1（已补测试闭合） |

> 审阅后补充：Issue 1 修复后，变异 D 已被 `test_done_like_variant_is_not_treated_as_sentinel` 拦下（实测 RED）。

## 独立复现结果

**base(`14f6e24`) vs head(`1b4cf88`) 对照**（同一探测脚本，`_stream_events` 直调）：

| 输入 | base 事件 / 告警 | head 事件 / 告警 | 结论 |
|---|---|---|---|
| `data: [DONE]` | `[]` / **1** | `[]` / **0** | 误报消除 ✅ |
| `data:  [DONE]`（2 空格） | `[]` / 1 | `[]` / **0** | `strip()` 生效 ✅ |
| `data: [DONE]  `（尾空白） | `[]` / 1 | `[]` / **0** | ✅ |
| `data: [done]`（小写） | `[]` / 1 | `[]` / 1 | 行为不变（刻意决策）✅ |
| `data: [DONE]extra` | `[]` / 1 | `[]` / 1 | 行为不变 ✅ |
| `data: `（空） | `[]` / 1 | `[]` / 1 | 行为不变 ✅ |
| `data:`（无空格） | `[]` / 0 | `[]` / 0 | 行为不变 ✅ |
| 合法 JSON 含 `"[DONE]"` | 2 事件 / 0 | 2 事件 / 0 | **未被误伤** ✅ |
| 坏行 | `[]` / 1 | `[]` / 1 | 坏行仍告警 ✅ |
| 坏行 + `[DONE]` | `[]` / **2** | `[]` / **1** | 哨兵不再额外贡献告警 ✅ |
| 正常流 + `[DONE]` | 2 事件 / **1** | 2 事件 / **0** | 事件序列零变化 ✅ |

**事件序列零变化**：上表每行 base/head 的 `events` 逐字相同——`[DONE]` 修复前后都**不产生事件**，`proposal.md` 的「事件序列逐字不变」属实。

**Anthropic 路径**：同样消费 `_stream_events`，但 `grep DONE agent/anthropic_llm.py` 零命中（不发该哨兵）；判据是纯字符串比较，对 JSON 行恒为 `False`，行为零变化。✅

**门禁**：OpenSpec strict validate `29 passed, 0 failed`；artifact checker `OpenSpec artifact checks passed`（exit 0）——均在还原后的干净树上跑出。

## 审阅自查

- 变异与探测全部在 `/tmp` 或即时还原；结束时 `git status --short` 为空，`git hash-object agent/llm.py` == `git rev-parse 1b4cf88:agent/llm.py` == `ad7e046…`，无 worktree 残留。
- 未使用 `AskUserQuestion`。
- 作者自述的「修复前 RED」「逐字一致」「事件序列零变化」均被独立复算，未采信转述。
