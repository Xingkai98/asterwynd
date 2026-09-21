# Building Review: fix-issue-224-bus-unbounded (Round 3 — delta 复审)

审阅者：独立零记忆 subagent（不继承任何开发上下文）
复审 head：**`a308e39`**（Round 2 审的是 `4f7fd85`；本轮聚焦 `git diff 4f7fd85..a308e39`，未重跑全量）
base：`abdcedfe397273936c3bf1659796445d30dec9d0`
审阅方式：读 delta 代码/文档 → **实跑**验证（自写探针，不借 change 自带测试）→ 变异确认 → 还原确认工作区干净。

## Verdict

PASS（复审 head = `a308e39`）

Round 2 判 PASS 时保留的三条低优先项中，**L1 与 L3 已按预期修好且经独立实测确认，L2 为「显式不动」**。
本轮未发现新增缺陷；仅遗留若干**低优先、不影响任何已交付契约**的措辞残句（见 Issues），均不改变
「权威 spec / delta spec / 代码行为 / 测试判别力」四者的正确性，故维持 PASS。

## Round 3 delta 复审（本轮新增）

改动范围：`git diff 4f7fd85..a308e39 --name-only` = `design.md` / `proposal.md` /
`reviews/building-review.md`（Round 2 报告落盘）/ `tests/agent/subagent/test_bus_bounded_exports.py`。
**代码（`agent/subagent/bus.py`、`agent/tools/builtin/subagents.py`）在本 delta 中零改动**，故 Round 2 已
实测的 D10 / D9 / Q1 / Q6 / D6 结论在 `a308e39` 上原样成立（本轮复跑回归确认，见 Test Results）。

### L1（措辞因果）—— 已修好，两处被点名位置均已改正

| 位置 | Round 2 状态 | `a308e39` 实测 |
|---|---|---|
| `proposal.md` 出口盘点后的「出口 4」说明 | 称「`max_tokens` 钳住后 ≤ 单条上限（与出口 1/2 同界）」 | **已改**（`:28-30`）：「钳住 `max_tokens` 只保证 summarize **触发**、不保证它**产出有界**（LLM 分支 advisory，见 C 节），故回包与其它出口一样走**出口投影**才 ≤ 单条上限」——因果正确 |
| `design.md` D5 闸门段末句 | 称「改为 `>=` 后……发布侧严格 ≤ 单条上限」 | **已改**（`:118-122`）：「……**summarize 必然触发**」，并新增 `:124-129` 边界补充：「发布侧对 LLM 摘要分支**没有硬界**……**发布侧的模型面输出由出口投影保证**……design 与 spec 均不得声称……「两侧同界」——准确表述是「**出口投影**保证两侧的模型面输出同界」」 |

权威 spec `openspec/specs/subagents/spec.md:171` 与 delta `specs/subagents/spec.md:13` 的对应句
（「发布侧的界由出口投影保证，不由阈值保证……SHALL NOT 声称『阈值钳制使发布侧严格不超过上限』」）
在 `a308e39` 上未再改动，仍正确（Round 2 已比对为与 delta 逐字一致）。

### L2（`max_read_tokens` 键）—— 按 Non-Goal 显式不动，符合预期

`bus.py:221` 仍返回 `"max_read_tokens": self.max_read_tokens`；`design.md` / `proposal.md` 的 Non-Goals
已显式声明「只截 bus 消息、不动既有键」。该项本就是 Round 2 判定的**既有遗产（修复前更不自洽）**，
本轮确认其边界清晰、不影响任何保证。保留为 Round 2 的 Issues #2（低）。

### L3（e2e 判别力）—— 已修好，独立实测确认真判别

- **bus 里真的躺一条超限消息**：我用探针包住 `MessageBus.publish` 记录入队原文（不改测试），以
  `PublishThenFinishLLM("x"*30000, summary="s"*6000)` 跑真实
  `run_pattern(pattern="orchestrator-worker", params={"workers": 1})`：
  ```
  queue raw publish lengths: [6000]   prefixes: ['ssssssssssssssssssss']
  BUS_MESSAGE_LIMIT: 4000
  exported: [(4000, True)]
  raw > limit? True
  ```
  即队列里是 **6000 字**的超预算摘要（Round 2 实测此处只有 4 字 `'done'`），入口真越界 →
  `_assert_bounded` 不再是恒真断言；两条 e2e 现在各自带 `summary_truncated is True` 判别力锚点（`:196-198`、`:213-215`）。
- **变异复核**：去掉 `snapshot_payload()` 的逐条 `_bounded_message` 投影 →
  - 仅跑 `test_bus_bounded_exports.py`：**3 failed**（`test_snapshot_payload_export_is_bounded`、
    `test_run_pattern_bus_export_is_bounded`、`test_run_pattern_tool_export_is_bounded`）
    —— Round 2 同口径为 **1 failed**，即「1 → 3」如 coordinator 所述，两条 e2e 确实获得了判别力；
  - 两个测试文件一起跑：**4 failed**（Round 2 同口径为 2 failed）；
  - `git checkout agent/subagent/bus.py` 还原后 `git status --porcelain` **为空**。

### 无新问题引入（本轮核查）

- `PublishThenFinishLLM.__init__` 新增必填 `summary`：全仓构造点仅 2 处（`test_bus_bounded_exports.py:193,209`），均已传入，无遗漏调用点。
- 该 fake 的第 2 次 `chat()` 确实被 `_summarize` 的 LLM 分支消费（探针实测入队原文 = `summary` 参数），
  第 3 次返回 `"done"` 收尾——调用序假设成立，无「多一次/少一次 LLM 调用」的隐性依赖。
- delta 未触碰 `agent/`、`scripts/`、`flow/`、`.github/`；权威 spec 与 delta 的相对关系未变。
- `tasks.md` 不在 delta 中；「审阅闭环」两条 `[ ]` 属本循环自身，未越权勾选。

## Tasks Verification

实现类（在 `a308e39` 上复核；Round 2 已逐条读过代码，本 delta 未改代码，故结论继承）

| tasks.md 条目 | 结论 | 证据 |
|---|---|---|
| 三常量（`BUS_MESSAGE_LIMIT` 派生 / `BUS_SNAPSHOT_LIMIT=20` / `BUS_PUBLISH_MAX_TOKENS`） | ✅ | `agent/subagent/bus.py:43`、`:53`、`:62`；实跑值 `4000 / 20 / 1000` |
| `BusMessage.truncated` + `to_dict()` 透出 `summary_truncated` | ✅ | `bus.py:100`、`bus.py:110`（构造点唯一 `bus.py:141`） |
| `read()` 单条截断 + `dataclasses.replace` 新实例（D10） | ✅ | `bus.py:70-87`、`:197`；实跑 `read()[0] is bus._messages[0]` → **False** |
| `read()` 重算 `token_count`（D9） | ✅ | `bus.py:85`；实跑截断后 1000 == `estimate_tokens(截断文本)` ≠ 全文值 7500 |
| `read()` 保留「单条超窗仍返回最新一条」（D3） | ✅ | `bus.py:184-191`，返回投影后的该条 |
| `read()` 总量钳制（D4b/Q1） | ✅ | `bus.py:174`、`:175`、`:194` |
| `snapshot_payload()` 二维界 + `messages_total`/`messages_omitted`，加固在方法本身 | ✅ | `bus.py:207-224`；调用点 `patterns.py:458`、`scheduler.py:2956` 无额外处理 |
| `PublishBusMessageTool` 钳 `max_tokens` + 闸门 `>=` | ✅ | `agent/tools/builtin/subagents.py:276-277`、`:283` |
| `ReadBusTool` schema description 校正；工具侧不加第二道截断 | ✅ | `subagents.py:312-322`、`:331-341`、`:357-361` |
| 不声称「全文在 X」（D6） | ✅ | 全仓无 bus 截断与 `result_ref`/`summary_ref` 的关联断言 |
| **R1 修复**：回包走出口投影 | ✅ | `subagents.py:296`；`:292-295` 注释如实说明 LLM 分支 advisory |
| **R2 修复**：派生锁收紧 | ✅ | `tests/agent/subagent/test_bus.py:81-90` 正则断言赋值右侧 |
| **L3 修复**：e2e 真越界 + 判别力锚点 | ✅ | `test_bus_bounded_exports.py:52-91`（`summary` 参数）、`:180-215`；探针实测队列 6000 字 |

测试类：Round 2 已逐条对应到真实存在的测试（`test_bus.py:53-69/72-90/93-215/180-213`、
`test_bus_bounded_exports.py:114-221/239-308`），本 delta 只改了 `PublishThenFinishLLM` 与两条 e2e，
其余测试未动；`test_bus_bounded_exports.py`（11 passed）与两文件合跑（32 passed）本轮均复跑通过。

文档类：`diagnosis.md` 6 章、两份 spec delta、`current_spec_synced` ×2（`workflow-events.jsonl` seq 2/3）、
关键词扫描、backlog 登记（`docs/openspec-change-backlog.md:144`）、Non-Goals 补写 `workers[]`/顶层 `summary`
——Round 2 已逐项验证，本 delta 未回改这些文件，结论继承。

## Round 1 Issues Re-check（结论继承，`a308e39` 上仍成立）

- **R1（中等，发布回包在 LLM 分支越界）**：Round 2 用自写脚本实测「回包 4000 / `summary_truncated` True /
  队列 6000 全文 / 队列条 `truncated` False」，并实测去掉回包投影后回归测试变红。本 delta 未改
  `subagents.py`，该项在 `a308e39` 上原样成立（本轮 L3 探针再次观测到同一条路径：入队 6000 → 出口 4000 + True）。
- **R2（中等偏低，常量派生锁是假保护）**：Round 2 实测把 `BUS_MESSAGE_LIMIT` 改成字面量 `4000` → 该测试
  **1 failed**（Round 1 同变异为 passed）。`tests/agent/subagent/test_bus.py:72-90` 本 delta 未改动。
- **R3（低，`.gitignore` 越界改动）**：`git diff origin/master...a308e39 -- .gitignore` **为空**；
  `handoff.json` 不存在。Round 2 已确认回滚，本轮复核仍成立。
- **R4（低，agent-runtime delta 与权威 spec 漂移）**：Round 2 归一化逐字比对两份 delta 与两份权威 spec 的
  Requirement 正文**相同**，含 `workers[]`/顶层 `summary` 限定段。本轮复核 spec 文件未在 delta 中改动，
  结论成立。

## Round 2 Issues Re-check

| Round 2 Issue | 本轮结论 |
|---|---|
| #1（低）`proposal.md`/`design.md` 把发布侧的界归因于阈值钳制 | **两处被点名的位置已修好**（见 L1 表）。**仍有残句未清**，降级为 Round 3 Issues #1 |
| #2（低）`snapshot_payload()` 的 `max_read_tokens=2000` 键不再自洽 | **按 Non-Goal 显式不动**（L2），维持低优先、非阻塞 |
| #3（低）两条 run_pattern e2e 测试判别力弱于自述 | **已修好**（L3）：探针实测队列 6000 字，去掉投影变异 1 → 3 红 |

## Issues

### 1. 低：`design.md` 仍有若干「发布侧的界归因于阈值」的残句（L1 未清干净）

- **`design.md:115-116`（本轮新发现，**live 决策段**）**：D5 的「理由」段写道「`max_tokens` 是 summarize 的**阈值**……钳住阈值就堵住了出口 4。」
  ——「出口 4」在 `proposal.md` 的盘点里就是**发布回包**，而「钳住阈值就堵住了出口 4」正是权威 spec
  `openspec/specs/subagents/spec.md:171` 明文禁止的那种断言（对 LLM 分支不成立）。同一份 design 的
  `:124-129` 在 13 行之后已给出正确口径，「堵住出口 4」应由**出口投影**保证，故这是文档内部自相矛盾。
- **`design.md:260-261`（Round 2 Issue #1 点过的最后一处，未处理）**：grill R6 记录仍写「D5 钳住后它 ≤ 单条上限，无新增漏洞」。
  该段属 `### 必须落实（grill 发现的落地坑）` 的**历史记录**，保留原始发现有其溯源价值，但该句本身是对 LLM 分支不成立的断言。
- **`design.md:133`**：弃用备选的理由里仍用裸短语「两侧同界最稳」，而 `:128-129` 已明令「不得声称「两侧同界」」。
- **`design.md:286-289`（Non-Goal）**：写「单条的**硬保证在消费侧 `read()`**；发布侧只做「阈值对齐」」。
  R1 修复后发布侧的**模型面输出**（回包）同样有硬界（走 `_bounded_message`），故「只做阈值对齐」低估了
  实际实现；无硬界的只是**入队原文**。方向是保守的（少宣称），不产生假保证，但与实现不再逐字相符。
- **`agent/tools/builtin/subagents.py:282` 与 `tests/agent/subagent/test_bus_bounded_exports.py:286`**：
  两处注释/docstring 仍用「把『发布侧与消费侧同界』变成一句假话」解释 `>=` 闸门的必要性。该闸门确有
  **独立的行为理由**（不带 `>=` 时 4001–4003 字不触发 summarize，原文直入队列，`test_publish_bus_message_threshold_is_inclusive`
  对队列长度的断言会红——Q6 语义成立），但用被禁的裸短语解释它，与 `design.md:128-129` 的口径不一致。
- 影响：**无行为缺陷，不影响任何已交付契约**——权威 spec、delta spec（与权威逐字一致）、proposal C 节、
  代码注释 `subagents.py:292-295`、`bus.py:59-61` 均已给出正确口径；上述残句只影响 design 这一份
  变更内部文档的自洽性与未来读者的因果模型。**不阻塞**。
- 建议（择一或全做）：把 `:116` 改为「钳住阈值只保证 summarize 触发；出口 4 的有界由回包出口投影保证」；
  `:261` 后追加一行「（R1 修复后更正：回包经出口投影才有界）」；`:133` 的裸短语改为「两侧模型面输出同界」；
  `:289` 的 Non-Goal 补一句「发布侧**模型面输出**亦经投影有界，无硬界的是入队原文」；
  两处注释把「两侧同界」改为「出口投影保证两侧模型面输出同界」。

### 2. 低：`snapshot_payload()` 的 `max_read_tokens=2000` 键与实际返回体量不再自洽

- 位置：`agent/subagent/bus.py:221`；上限见 `bus.py:218,220`。
- 问题：修复后快照最多 20 × 4000 = **80,000 字符 ≈ 20,000 token**，而返回体仍带 `max_read_tokens: 2000`。
  该键是既有键，修复前也存在（当时 payload 完全无界，更不自洽），**属既有遗产而非本 change 引入**。
- 影响：仅自描述不精确，不放大任何被检视方可控的量。**不阻塞**（L2 已按 Non-Goal 显式不动）。
- 建议：另案考虑改名 `default_read_window` 或补 `messages_limit` 键。

## Test Results

环境：`export PATH=/home/happy/.local/bin:$PATH`。本轮为 delta 复审，**未重跑全量**（Round 2 已在
`4f7fd85` 上跑过全量 3013 passed / 2 known-env failures，本 delta 未改 `agent/` 代码）。

- `uv run pytest tests/agent/subagent/test_bus_bounded_exports.py -q` → **11 passed**（1.60s）。
- `uv run pytest tests/agent/subagent/test_bus.py tests/agent/subagent/test_bus_bounded_exports.py -q` → **32 passed**（1.51s）。
- `uv run pytest tests/agent/subagent/ tests/agent/tools/ -q` → **934 passed**（33.60s）。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**。
- `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → 唯一报错 `review manifest missing`（本报告落盘后由 manifest 绑定，属预期）。

### 本轮实跑验证（delta 相关）

| 核查项 | 实测输出 | 结论 |
|---|---|---|
| **L3 队列真越界**（探针包 `MessageBus.publish`，不改测试） | `run_pattern(workers=1)` 下入队原文长度 = **[6000]**（前缀 `ssss…`）> `BUS_MESSAGE_LIMIT` 4000；导出 `(4000, True)`；`raw > limit? True` | ✅ 不再是 4 字 `'done'`，e2e 断言有判别力 |
| **L3 变异**：去掉 `snapshot_payload()` 逐条投影 | 仅 exports 文件：**3 failed**（Round 2 同口径 1 failed）；两文件：**4 failed**（Round 2 2 failed） | ✅ 「1 → 3」复核成立 |
| **还原** | `git checkout agent/subagent/bus.py` 后 `git status --porcelain` **为空**；基线复跑 32 passed | ✅ 工作区干净 |
| **L1 措辞 grep**（全仓，排除 archive/本报告/grill 历史记录） | 见 Issues #1：被点名两处已改正；残句集中在 `design.md:116,133,261,286-289` + 两处注释 | ⚠️ 低优先残句，非阻塞 |
| **dangerous-direction grep**（「钳住…⇒ 有界」类） | 命中 `design.md:116`（live）、`design.md:261`（历史）、`tasks.md:86`（正确：说「钳住阈值只保证…」）、`subagents.py:292`（正确）、`reviews/grill-design.md:74`（历史 grill 记录，保留） | ⚠️ 见 Issues #1 |
| **无新问题** | fake 构造点仅 2 处且都已更新；delta 未触碰 `agent/`、`scripts/`、`flow/`、`.github/`；`tasks.md` 未在 delta 中 | ✅ |

## 结论

本轮为聚焦 delta 复审，覆盖真正要合入的 head `a308e39`。三条低优先项：**L1 的两处被点名位置
（`proposal.md` 出口 4 说明、`design.md` D5 闸门段）已按正确因果改写**，但同一份 design 里仍留有四处
把发布侧的界归因于阈值钳制的残句（其中 `design.md:116` 属 live 决策段、`design.md:261` 是 Round 2 点过
却未处理的历史记录段）；**L2 按 Non-Goal 显式不动**，维持既有遗产、不阻塞；**L3 已真修好**——我用独立探针
（包 `MessageBus.publish`、不借 change 自带测试）实测真实 `run_pattern` 下 bus 里躺的是 **6000 字**超预算
摘要而非 4 字收尾文本，导出 4000 + `summary_truncated` True，其谓词真判「入口越界」；把
`snapshot_payload()` 的逐条投影去掉后，仅 exports 文件的变红数由 Round 2 的 **1 → 3**（两文件口径
**2 → 4**），两条 e2e 确实获得了判别力，还原后工作区干净。代码本身在本 delta 中零改动，故 Round 2 已
实测的 D10（`read()[0] is bus._messages[0]` 为 False、队列与 `compact_summary()` 不受污染）、D9、Q1
（100/1000 条满载 × 10^9~10^18 参数均压到 2 条 / 8,000 字符）、Q6、D6 与九组变异结论在 `a308e39` 上
原样成立；权威 spec 与 delta spec 仍逐字一致、OpenSpec strict 30 passed、artifact checker 仅余预期中的
manifest 缺失。剩余为低优先措辞残句（含一条既有遗产键名），不改变任何已交付契约的正确性，按判定标准
维持 **PASS**，可进入收尾（归档 + 生成 review manifest，收尾时顺手清 Issues #1 的四处残句更佳）。
