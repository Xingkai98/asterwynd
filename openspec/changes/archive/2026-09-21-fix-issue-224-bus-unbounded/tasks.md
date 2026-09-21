# Tasks — fix-issue-224-bus-unbounded

## 实现

- [x] `agent/subagent/bus.py`：新增常量 `BUS_MESSAGE_LIMIT = TRANSCRIPT_ITEM_LIMIT`、
      `BUS_SNAPSHOT_LIMIT = 20`、`BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4`——
      单条上限从 `manager.TRANSCRIPT_ITEM_LIMIT` **派生**（D1）；导入无环已由 grill 动态验证
      （AST import-time 闭包 + 三种加载顺序），若未来成环则退化为 inline + parity 测试（D7 回退方案）
- [x] `agent/subagent/bus.py`：`BusMessage` 增 `truncated: bool = False` 字段；`to_dict()` 增
      `"summary_truncated": self.truncated`（D8，命名沿用 #213 的 `<字段>_truncated` 家族）
- [x] `agent/subagent/bus.py`：`read()` 对返回的每条 `summary` 按 `BUS_MESSAGE_LIMIT` 截断，并
      **用 `dataclasses.replace` 构造新实例**（D10，SHALL NOT 原地赋值——`read()` 目前返回队列里的
      同一对象，实测 `is` 为 True，原地改会污染 `compact_summary()` 与 checkpoint）
- [x] `agent/subagent/bus.py`：`read()` 对被截断的消息**重算 `token_count`**（`estimate_tokens(截断后)`，
      D9）；内部挑消息的预算累计仍用原始 `token_count`（更保守）
- [x] `agent/subagent/bus.py`：`read()` **保留**「单条超窗仍返回最新一条」语义（返回截断后的该条，D3）
- [x] `agent/subagent/bus.py`：`read()` **总量钳制**——`max_tokens = min(max_tokens,
      BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS)`、`limit = min(limit, BUS_SNAPSHOT_LIMIT)`
      （D4b，Q1 确认；不钳则单条截断后总量仍可 300 万字符）
- [x] `agent/subagent/bus.py`：`snapshot_payload()` 加**条数上限**（取最近 `BUS_SNAPSHOT_LIMIT`
      条）+ **单条上限**，新增 `messages_total` / `messages_omitted` 显式报告（D4，加固在方法
      本身——唯一模型面调用点是 `patterns.py:458`，`scheduler._envelope()` 为纵深防御）
- [x] `agent/tools/builtin/subagents.py`：`PublishBusMessageTool` 的 `max_tokens` 钳到
      `[1, BUS_PUBLISH_MAX_TOKENS]`，且闸门由 `>` 改 `>=`（D5 + Q6 确认；`estimate_tokens` 向下取整，
      `>` 会留 4001-4003 字缝）
- [x] `agent/tools/builtin/subagents.py`：`ReadBusTool` 的 schema description 校正——明说单条与总量
      均有上限、超限携带 `summary_truncated`；**不在工具侧加第二道截断**（D2）
- [x] 全文截断标记复核：bus 出口**不**声称「全文在 X」（bus 不落盘，D6）

## 测试

- [x] `read()`：单条 30,000 字消息 → 返回的 `summary` 长度 ≤ `TRANSCRIPT_ITEM_LIMIT` 且
      `summary_truncated is True`
- [x] **Q5 拆两条**（用户确认）：
      - 保留 `test_read_returns_newest_when_single_message_exceeds_window` 的**原语义**（输入 400 字、
        不涉截断，断言仍为「超窗返回最新一条」全文可见）——该测试**不再**承担截断断言
      - **新增**一条「截断」测试（输入 30,000 字，断言 ≤ 上限且 `summary_truncated is True`），
        使两条测试各自有判别力（400 字输入下 `truncated` 恒 False，会把截断实现删掉仍绿）
- [x] `read()` 总量：满载 100 条 × 30000 字，`read(max_tokens=10**9, limit=10**9)` 返回的总量 ≤ 固定上界
- [x] **D10 回归**：`read()` 之后 `bus._messages` 中该条 `summary` 仍为全文、`compact_summary()`
      不变（变异：`replace` 改回直接赋值 → 变红）
- [x] **D9 回归**：被截断条目的 `token_count` == `estimate_tokens(截断后文本)`，不等于全文记账值
- [x] `snapshot_payload()`：100 条满载 → `len(messages) == BUS_SNAPSHOT_LIMIT`、
      `messages_total == 100`、`messages_omitted == 100 - BUS_SNAPSHOT_LIMIT`；单条 30,000 字 →
      该条 `summary` ≤ 上限且 `summary_truncated is True`
- [x] `PublishBusMessage`：`max_tokens=10**9` → 读回不超单条上限；**4001 字输入**（Q6 边界）→
      发布侧即触发 summarize，不留给消费侧再截
- [x] 常量：`BUS_MESSAGE_LIMIT == TRANSCRIPT_ITEM_LIMIT` 机械锁定——**按 D1 主方案（派生）落**，
      该测试锁的是「派生关系没被改成字面量」（tasks 须写明形式，供收尾审阅判断）
- [x] **契约测试（issue 建议的核心）**：构造同一份 bus 内容（1 条 30k + 满载 100 条），断言
      **两条模型面出口**（`ReadBusTool.execute()` 的 JSON 与 `run_pattern` 的 `result["bus"]`）
      每条 `summary` ≤ `TRANSCRIPT_ITEM_LIMIT`、条数 ≤ `BUS_SNAPSHOT_LIMIT`
- [x] **参数教训**：新测试输入必须**真的**超过上限（单条用 30000、条数用 >20），否则「≤ 上限」恒真
- [x] 变异验证：`read()` 截断改 identity / `snapshot_payload()` 去条数上限 / `max_tokens` 不钳 /
      `replace` 改回原地赋值 / 闸门改回 `>` → 对应测试必须变红 → 还原后变绿
- [x] 回归：`tests/agent/subagent/`（重点 `test_bus.py`、`test_patterns.py`、`test_scheduler.py`、
      `test_workflow_graph_snapshot*.py`）、`tests/agent/tools/` 全量通过

## 文档

- [x] `diagnosis.md`：bugfix 门禁要求的 6 章
- [x] spec delta：`specs/subagents/spec.md`（ADDED「message bus 模型面出口有界」，含总量维）+
      `specs/agent-runtime/spec.md`（ADDED「编排结果中的 bus 快照有界」，界施在方法本身）
- [x] **当前规格同步**：delta 合入 `openspec/specs/{subagents,agent-runtime}/spec.md`
      （含 `current_spec_synced` 事件 ×2）
- [x] 关键词扫描（**含 grill R3 指出的漏项**）：`docs/`、`README.md`、`CONTEXT.md`、
      `docs/architecture.md`、`docs/agent-internals.md`，以及
      `docs/interview-bullets/interview-prep.md:219,221`（发布侧 400 token 上限、单条超预算保留最新一条）、
      `docs/interview-bullets/walkthrough.md:750-808`、`docs/interview-script/walkthrough/W03-multi-agent.md:40`、
      `docs/interview-script/questions/Q08-multi-agent.md:49`（`MessageBus` 行数已漂移）
- [x] `docs/openspec-change-backlog.md` 登记本 change（**已完成**，含 `backlog_updated` 事件）；
      收尾时移除本 change 条目（含 `backlog_updated` 事件）并**同步 backlog 里写死的常量值**（grill R4）
- [x] Non-Goals 补写：`RunPattern` 的 `workers[]` 与顶层 `summary` 的条数维仍无界（grill R2），
      避免 spec 被读成「`RunPattern` 已 bounded」

## 审阅闭环

- [x] Round 1 独立 subagent 审阅（`/review-loop fix-issue-224-bus-unbounded`）→ CHANGES_REQUESTED
- [x] 按 verdict 修复 + 加回归测试（见下「审阅修复」节）
- [x] Round 2 独立 subagent 复审 → PASS
- [x] Round 3 delta 复审（head `a308e39`，审阅者要求覆盖真正合入的 head）→ PASS
- [x] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash
      （reviewer run = `ad7b0b26c68e88869`；复审覆盖到 `a308e39`，其后 `1fad39e` 只按审阅者 L1 建议
      清理 design/proposal 措辞，无代码变化——manifest 的 `head_sha` 绑定实际合入 head）

### 审阅修复（Round 1 → Round 2）

- **R1（中等）**：`PublishBusMessage` 的**回包**（第 5 条模型面出口）在 `_summarize` 的 LLM 分支
  返回超预算摘要时**越界**——实测 `OverBudgetLLM` 返回 6000 字时回包 6000 字。钳住阈值只保证
  summarize **触发**、不保证它**产出有界**（该分支是 advisory）。修法：回包同样走出口投影
  `_bounded_message`（队列仍保留全文，符合 D2）。同步修正 `specs/subagents/spec.md`（delta + 权威）
  与 `proposal.md` 里「使发布侧严格不超过单条上限」这句**对 LLM 分支不成立**的断言，改为「发布侧的
  界由出口投影保证，不由阈值保证」+ 新增 Scenario「发布回包不因摘要超预算而越界」。
  回归测试：`test_publish_reply_is_bounded_when_summary_over_budget`（覆盖 LLM 分支，此前测试只覆盖
  `llm=None` 的降级分支）。
- **R2（中等）**：常量「派生锁」是假保护——`test_bus_message_limit_derives_from_transcript_item_limit`
  只查 `from agent.subagent.manager import` / `TRANSCRIPT_ITEM_LIMIT` 两个子串，而该 import 行因 `_clip`
  无论如何都在；实测把 `BUS_MESSAGE_LIMIT` 改成字面量 `4000` 该测试**仍 passed**。修法：改为正则断言
  赋值右侧就是 `TRANSCRIPT_ITEM_LIMIT`。
- **R3（低）**：`.gitignore` 新增 `**/handoff.json` 属越界改动 → 回滚，`handoff.json` 用完即删。
- **R4（低）**：`specs/agent-runtime/spec.md` 的 delta 比已同步的权威 spec 少 grill R2 的限定段
  （delta 与合入结果漂移）→ 补齐，两处逐字一致。

### 审阅修复（Round 2 → Round 3）

- **L1（低）**：`proposal.md` / `design.md` 仍把发布侧的界归因于「阈值钳制」。修法：统一因果为
  「阈值钳制只保证 summarize **触发**；回包与其它出口一样由**出口投影**保证有界」，并把准确表述写死为
  「出口投影保证两侧的模型面输出同界」，不是「发布侧与消费侧同界」。D5 理由段、备选段、Non-Goals
  的 R5 条、grill R6 记录四处同步。
- **L2（低）**：`max_read_tokens` 键与 80k 快照不自洽——既有键，design 已显式 Non-Goal 不动，保持现状。
- **L3（低但有实义）**：两条 `run_pattern` 端到端测试自称界住「超长消息」，实测 bus 里只有 4 字
  （`_summarize` 的 LLM 分支返回了 worker 的收尾文本）——去掉 snapshot 逐条投影后仍绿，无判别力。
  修法：fake LLM 在 `_summarize` 那一步返回 6000 字超预算摘要，并以 `summary_truncated is True`
  作判别力锚点。实测去掉逐条投影后变红测试数 1 → 3。

## 验证

- [x] 全量 pytest：`uv run pytest -q`
- [x] OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] OpenSpec artifact checker：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`
- [x] 端到端验收：30000 字单条 + 100 条满载，逐个走 `ReadBus`（默认 + 超大 kwargs）与 `RunPattern`
      出口，实测均不超过固定上限且 `messages_omitted` 如实
- [x] **benchmark smoke**：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-224`
