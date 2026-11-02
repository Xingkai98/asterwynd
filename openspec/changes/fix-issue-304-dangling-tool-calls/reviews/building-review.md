# Building Review: fix-issue-304-dangling-tool-calls

- Reviewer: 独立零记忆审阅者（reviewer ≠ author，不继承开发上下文）
- 审阅对象：`git diff origin/master...HEAD`（base `604b56cc`）；任务书指定 head 为 `e56576ee`，审阅期间分支新增 `35ad4c3d`（tasks 4.7 记录）、`f38573cf`（B1 spec 事件 + 测试 import 清理）与 `a38159dd`（low/nit 修复）。代码证据以 `e56576ee` 为准；门禁与最终证据复跑于 `a38159dd`。
- 审阅日期：2026-11-02
- 工作区状态：干净；`f38573cf` 清理了两处测试 unused import，`a38159dd` 修复 low/nit。唯一未提交文件是本报告 `reviews/building-review.md`。

## 本轮判定

**PASS**（B1 与 low/nit 可修项均验证通过；本轮收口，最终审阅 head `a38159dd`，闭环出口见文末 `## 闭环出口`）

B1 已修复并验证；L3/L4/L6/L9/L10/L11 已修复并验证；deferred 0。

### 第 1 轮 · 批次

#### B1 [high] `observability` / `web-ui` 两个受保护 spec 缺少 path-specific 的结构化解释事件（已修复）

**证据**

- 本次 diff 修改了四个受保护路径：
  `docs/openspec-change-backlog.md`、`openspec/specs/agent-runtime/spec.md`、
  `openspec/specs/observability/spec.md`、`openspec/specs/web-ui/spec.md`
  （`git diff --name-only origin/master...HEAD`）。
- 但 `workflow-events.jsonl` 只有一条 `current_spec_synced` 事件，其
  `artifact_path` 为 `openspec/specs/agent-runtime/spec.md`
  （`openspec/changes/fix-issue-304-dangling-tool-calls/workflow-events.jsonl:4`）。
  `reason` 虽提到三个 spec，但 witnessloop 的 `events.covers` 只做
  **规范化后的精确路径相等**，不读取 reason 中提到的其他路径
  （`/home/happy/witnessloop/src/witnessloop/events.py:106-121`；
  `checkcmd.py:396` 逐路径调用 `covers`）。
- 在 `35ad4c3d` 上复跑
  `/home/happy/.local/bin/witnessloop check --root /home/happy/ax-wt/repro-304 --base origin/master --head HEAD`
  退出 1，第 2、3 项 finding 正是：
  - `openspec/specs/observability/spec.md`：受保护路径被写入，但没有结构化解释事件；
  - `openspec/specs/web-ui/spec.md`：受保护路径被写入，但没有结构化解释事件。
- 这不是可选检查：`.github/workflows/witnessloop.yml:1-15` 的 `gate` job 是
  PR required check 的承载者；不修会导致 `gate / check` 红。

**修复要求**

在 change 的 `workflow-events.jsonl` 追加两条允许类型的事件（建议
`current_spec_synced`，或用 `protected_artifact_explained`），分别：

- `artifact_path` = `openspec/specs/observability/spec.md`
- `artifact_path` = `openspec/specs/web-ui/spec.md`

两条事件的 `reason` / `approved_by` 均非空，说明本次把 delta 施加进正式规格。
追加后复跑 witnessloop check，确认该两项 finding 消失。

**影响面**：流程/门禁完整性，不是产品代码缺陷；但会阻断合入所需的 witnessloop gate。

### 修复验证

**B1: verified**

- `f38573cf` 在 `workflow-events.jsonl` 新增 seq 5（`artifact_path=openspec/specs/observability/spec.md`）与 seq 6（`artifact_path=openspec/specs/web-ui/spec.md`）；加上 seq 4 的 `agent-runtime`，三份受保护 spec 均有 per-path `current_spec_synced`，`reason`/`approved_by` 非空。
- 在 `f38573cf` 上复跑 witnessloop check，exit 1 只剩“缺少 review manifest”一项；B1 的两个受保护路径 finding 已消失。manifest 按流程在内容提交、归档 move 之后构建，属后续收尾步骤，不是 B1 残留。
- `f38573cf` 同时提交了两处测试文件 unused import 清理；`tests/agent/test_issue304_dangling_tool_calls.py` 与 `tests/web_tests/test_issue304_web_resume.py` 复跑 **8 passed**。
- 验证期未发现新的 medium+；deferred 0。

### 低优先级修复验证

**L3/L4/L6/L9/L10/L11: verified**

- **L3: verified**。`tests/agent/test_message_chain_repair.py:280-294` 新增
  `test_pairing_event_ids_are_bounded`，断言 20 条上限、`truncated=True`、每个 id
  为 128 字符加省略号；单独运行 1 passed。手工探针（25 个 id）也得到 20 条、
  `truncated=True`、首条长度 129。
- **L4: verified**。`tests/agent/test_llm_http_body.py:138-166` 增加第二个 assistant
  的 `c2`，断言 `sorted(call_ids) == sorted(tool_ids)` 且 `tool_ids` 无重复；单独
  运行通过。
- **L6: verified**。`tests/agent/test_message_chain_repair.py:238-266` 先从悬空链调用
  `repair_tool_call_pairing`，再对修复产物执行 `compact`；单独运行通过。
- **L9: verified**。`tasks.md:50` 的 1.2.1 已改为
  `tests/agent/test_issue304_dangling_tool_calls.py`。
- **L10: verified**。`web/session.py:2183-2190` 在 HTTP 错误时无条件保留
  `status_code`，`detail` 仍只在 body 非空时出现；
  `tests/web_tests/test_llm_error_detail.py:161-175` 的
  `test_empty_body_http_error_still_carries_status_code` 断言空 body 事件带
  `status_code=400`、无 `detail`，群聊摘要为 `HTTP 400 (unknown)`。
- **L11: verified（代码路径）**。`web/session.py:2251-2256` 只在
  `_group_failure_summary` 非空时覆盖 `turn_error_message`，后续无状态码 error 不会
  清空已有 HTTP 摘要。该路径以代码审阅确认；无独立回归测试，属 low 级可接受。
- 回归：受影响测试集
  `test_issue304_dangling_tool_calls.py`、`test_message_chain_repair.py`、
  `test_llm_http_body.py`、`test_issue304_web_resume.py`、`test_llm_error_detail.py`
  共 **42 passed**；L4/L6/L10 单独 **3 passed**；L3 单独 **1 passed**。

**未修项确认（理由可接受，登记保留）**

- **L1**：跨 assistant 重复 id 仍可能各合成一条。输入本身畸形，spec 明确不承诺修复；
  做跨 turn 全局 id 去重会引入 new 语义，超出本 change。
- **L2**：provider 控制的 `name`/`id` 含 lone surrogate 时，合成内容可能保存失败；但同一
  assistant 的 `tool_calls.arguments/id` 也会先让既有 `Message.to_dict` 失败，属既有畸形
  输入面，局部清洗反而会掩盖问题。
- **L5**：未补“超长 body 尾部 reasoning 标记仍触发重试”的专项用例；`_http_error_text`
  已优先返回完整 attr，helper 测试覆盖全量属性；该组合属低概率 provider 行为，登记。
- **L7**：benchmark smoke 4/68 已如实记录为接线验证，不读成任务包通过率。
- **L12**：4096 与 4000 分属 Web 展示与 trace 预览，保留不同值。
- **L13**：backlog active 文案待归档移除。
- **L14**：前缀碰撞为已记录已知限制，1.4.10 测试已钉住。

### 第 1 轮 · 下一批（deferred）

无。B1 已 verified；验证期未发现新的 medium+ 问题，deferred 0。以下三类**不进入本轮批次**：

1. `review manifest` 缺失：witnessloop 第 1 项 finding 是
   `openspec/changes/fix-issue-304-dangling-tool-calls` 缺少 `reviews/*.manifest.json`。
   这是审阅阶段 5.1/5.2 与归档前 manifest 生成待办，不是实现缺陷；本报告落地后应按
   流程生成 grill/building manifests。
2. 4.7 benchmark smoke 的 4 passed / 68 failed：`--agent fake` 未带
   `--fake-edit-file/--fake-old-string/--fake-new-string`，fake runner 默认不产生 edit，
   因此 37 `no_change`、30 `test_failure`、1 `setup_error` 是工具接线 smoke 的
   预期形态，不是本 change 的代码回归；作者已在 `35ad4c3d` 如实记录。详见 L7。
3. 全量 pytest 的 5 个 MCP 失败：环境 PATH 缺少 `uv`（`FileNotFoundError: ... 'uv'`），
   用 `PATH="$HOME/.local/bin:$PATH"` 重跑同一组 5 条测试得到 5 passed。不是新增代码失败。
   3 条 `TestFindScopeRoot` ×2 + `test_task_output_truncated` 为任务书明确的既有基线失败。

## 任务逐项验证

对照 `tasks.md` 的每个 `[x]` 读代码/测试确认真实存在；`[ ] (post-merge)` 与 5.x/6.x
不计入实现缺陷。3.4 已随 B1 修复验证，checked 项均已验证。

| 任务 | 验证结果与证据 |
| --- | --- |
| 0.1–0.5 | 已验证。`reviews/grill-design.md` 有 `## Confirmed Decisions`（≥3 条、含来源）、`## Code-Resolved Questions`、`## Open Questions`、`## User Confirmation`；`reviews/grill-adversarial.md:127` 的 `## 闭环出口` 为 PASS；`design.md` 有 `## User Rulings` 与 `## Pre-Implementation Review`；U1 记录在 `workflow-events.jsonl:3`。 |
| 1.1.1–1.1.11 | 已验证。`tests/agent/test_message_chain_repair.py:36-210` 覆盖末尾、并行、连续、插入位置、正常链字节不变、幂等、orphan-before/misplaced-after、空 id、spill preview、文本/reasoning 保留与有界文案。 |
| 1.1.12 | 已验证。`tests/agent/test_issue304_dangling_tool_calls.py:465-532` 在 `mode_changed` await 点取消，断言原历史 + 新输入、todos、skills、`user_system_prompt` 均保留。 |
| 1.2.1–1.2.9 | 已验证。`tests/agent/test_issue304_dangling_tool_calls.py:262-565` 覆盖中断中断言、落盘配对、同进程重试、直接悬空快照 resume、正常对照、`source="run"` 事件、finally trace；`tests/agent/test_message_chain_repair.py:213-253` 覆盖 spill/annotate/compaction；`tests/web_tests/test_llm_error_detail.py:117-132` 覆盖只读历史展示。1.2.1 的文件名已由 `_repro.py` 演进为 `_dangling_tool_calls.py`（L9）。 |
| 1.3.1–1.3.3 | 已验证。`tests/web_tests/test_issue304_web_resume.py:48-108` 覆盖 Web cancel→unload→resume→rerun 与群聊 timeout 后下一轮可用；`tests/agent/test_llm_http_body.py:138-158` 覆盖 OpenAI 合成结果 `Error:` 前缀。OpenAI 的逐 id 配对断言仍需补强（L4）。 |
| 1.4.1–1.4.10 | 已验证。`tests/agent/test_llm_http_body.py:31-196` 覆盖流式/非流式 Anthropic+OpenAI body 属性、trace 有界 detail、合成 `is_error`、真实结果无标记、空 body、前缀碰撞记录；`tests/web_tests/test_llm_error_detail.py:47-157` 覆盖 Web detail/status、非 HTTP 形状、群聊固定摘要与哨兵；`tests/web_tests/test_llm_error_detail_js.py:43-50` 覆盖前端拼接。1.4.8 的“完整 body 供 `_is_reasoning_400`、展示才截断”缺少专项测试（L5）。 |
| 2.1–2.11 | 已验证。`agent/message.py:217-356` 实现常量、`RepairReport`、确定性合成、有界文案与幂等扫描；`agent/loop.py:673,793-797,1802-1852` 实现 finally 与 run 起点调用、事件/trace 有界；`agent/llm.py:26-59,178`、`agent/anthropic_llm.py:83,283-291,634`、`agent/openai_llm.py:87` 实现 body 保留与合成错误信号；`agent/trace_recorder.py:289-302` 增加有界 detail；`web/session.py:58-99,134,2182-2190,2234,2251,2287` 实现 error detail、固定群聊摘要、只读历史修复与 `TurnOutcome.message`；`web/static/chat.js:736-741,975-976` 用 `textContent` 展示。 |
| 3.1–3.7 | 3.1–3.3 已验证（delta 与 `openspec/specs/agent-runtime/spec.md:26`、`:671`、`observability/spec.md:139`、`web-ui/spec.md:1808,1820` 一致）；3.4 已验证：seq 4/5/6 分别覆盖 agent-runtime/observability/web-ui，`f38573cf` 上 witnessloop 仅剩 manifest 待办；3.5 backlog 已登记（`docs/openspec-change-backlog.md:122`）；3.6 `docs/adr/ADR-0009-resume-tool-call-pairing-repair.md` 存在且含 ≥2 被拒备选；3.7 `docs/architecture.md` 与 `docs/testing-guide.md` 已同步事实变化，README 无必要事实变更。 |
| 4.1–4.7 | 4.1 定向+回归 243 passed；4.2 全量 4478 passed / 10 skipped / 8 failed，其中 5 条 MCP 为环境 `uv` PATH 问题（复跑 5 passed）、3 条为任务书已知基线；4.3 协议 fake 覆盖；4.4 OpenSpec 29/29；4.5 瘦 checker exit 0；4.6 变异见下；4.7 已记录工具接线 smoke 4/68（L7）。 |
| 5.1–5.2 | 5.1 由本报告承担；5.2 的 low/nit 登记见下。manifests 待审阅阶段生成。 |
| 6.1–6.2 | `(post-merge)`，不计入实现缺陷。 |

## 验证证据

- **定向 + 回归**：`uv run pytest -q` 覆盖 message/repair、issue #304、HTTP body、Web resume、
  error detail、JS 契约及既有 anthropic/openai/loop/message/trace/web session：
  **243 passed**。
- **全量 pytest**：**4478 passed, 10 skipped, 8 failed**。
  - 既有基线 3 条：`TestFindScopeRoot::test_returns_none_for_non_git_dir`、
    `TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan`、
    `test_task_output_truncated`。
  - 5 条 MCP 失败均为 `FileNotFoundError: ... 'uv'`（测试 fixture 用 `command: uv`，
    当前 shell PATH 无 `uv`）；加 `PATH="$HOME/.local/bin:$PATH"` 重跑该 5 条：
    **5 passed, 6 deselected**。不是本 change 引入的失败。
- **变异验证（临时 pytest 插件注入，未修改仓库源码）**：
  - 把 `agent.message/loop/web.session` 的 `repair_tool_call_pairing` 替换为 no-op：
    **16 failed, 14 passed**（repair/recovery/idempotence/display 用例变红）。
  - 把 `raise_for_status_with_body` 替换为不附加 body：**5 failed, 11 passed**
    （body 属性、流式/非流式 detail、空 body 用例变红）。
  - 两次变异后无生产代码改动；随后 `f38573cf` 提交了两处测试文件 unused import 清理。
- **OpenSpec strict validate**：`29 passed, 0 failed (29 items)`。
- **瘦项目规则 checker**：`uv run python scripts/check_openspec_artifacts.py
  --base-ref origin/master --require-base` exit 0（“Project rule checks passed”）。
- **witnessloop check**：在 `a38159dd` 上 exit 1，只剩 1 项 finding：
  缺 review manifest（审阅阶段待办）。B1 的两个受保护 spec 缺解释事件已由 seq 5/6 修复并复验消失。
- **low/nit 修复回归**：受影响五个测试文件共 **42 passed**；L4/L6/L10 单独
  **3 passed**；L3 单独 **1 passed**。
- **benchmark smoke**：72 tasks，4 passed / 68 failed；reason 分布 37 `no_change`、
  30 `test_failure`、1 `setup_error`。`benchmarks/tasks/README.md:15-21` 的 fake-runner
  artifact smoke 需要 `--fake-edit-file` 等参数；当前命令只验证工具接线，不代表
  任务包通过率。

## 8 维审阅结论

1. **任务逐项验证**：checked 项均有代码/测试/文档证据；3.4 的 B1 已修复验证；见上表。
2. **正确性**：核心算法正确——有序扫描、只对整条历史无同 id 结果的悬空调用合成、
   并行/连续/末尾插入位置、幂等与字节稳定、Case B 不重复合成、正常链返回原列表；
   finally 同步修复不掩盖取消；resume 早期取消先恢复全部同步状态；HTTP body 保留
   不改变异常类型/重试；Anthropic `is_error` 只对固定前缀生效；OpenAI 合成结果保留
   `Error:` 文本。未发现 medium+ 代码缺陷。
3. **Spec 对齐**：B1 是唯一 high，已 verified；L10 已修复，L3/L4/L6 测试缺口已补；
   其余 low/nit（L1、L2、L5）保留并确认理由，不影响主路径。
4. **冗余度**：修复函数纯函数、单一入口；`_bounded_text` 与 `bound_text`、
   `LLM_ERROR_DETAIL_LIMIT` 与 `TRACE_PREVIEW_CHARS` 有轻微重复，但分层合理，
   未达 medium。
5. **测试覆盖**：核心失败路径、幂等、字节稳定、正常链、finally、resume early cancel、
   Web/群聊、诊断传播均有测试；L3/L4/L6 的专项缺口已在 `a38159dd` 补齐；仅 L5 的
   reasoning 全量 body 组合保留为 low 登记。
6. **安全性**：前端用 `textContent`；群聊共享日志只允许 `HTTP <status>` + 固定错误类型
   枚举，哨兵测试证明不写 `error.message`/原始 body；detail 有界；未发现凭据/payload
   拼接。合成文案提示“可能已部分执行、重试前先检查状态”，不伪造成功。
7. **可维护性**：修复逻辑集中在 `agent/message.py`，loop 只调用；事件/trace/日志有界；
   `RepairReport` 与常量清晰；未发现结构性问题。
8. **CI 完整性**：OpenSpec strict validate 与瘦 checker 通过；全量 pytest 除既有基线 +
   环境 MCP 外无新增失败；变异验证证明关键测试真会红；B1 已修复，`f38573cf` 上
   witnessloop 只剩 review manifest 待办（内容提交、归档 move 后构建），不属于 B1 残留。

## low / nit 登记表（不阻塞本轮）

> 本表为初审登记。L3/L4/L6/L9/L10/L11 已在 `a38159dd` 修复并验证；L8 已由
> `f38573cf` 清理；L1/L2/L5/L7/L12/L13/L14 保留，理由见上节。

| ID | 级别 | 位置 | 说明与建议 |
| --- | --- | --- | --- |
| L1 | low | `agent/message.py:307-312` | 同一 assistant 内重复 id 被静默跳过；无匹配 assistant 的 orphan tool result 也没有 warning；spec/design 写“畸形输入只记录”。跨 assistant 重复 id 实测会各合成一条（`dup` ×2），因为 `tool_ids_in_history` 在合成前一次性计算。输入已畸形且 spec 不承诺修复，但建议至少补 warning，避免“合成重复结果”与“只记录”口径冲突。 |
| L2 | low | `agent/message.py:241-256`；`agent/session.py:310-312` | 合成文案直接嵌入 provider 控制的 `name`/`id`；若含 lone surrogate，`json.dump(ensure_ascii=False)` / `_hash_dict` 会抛 `UnicodeEncodeError`（实测），导致本次快照保存失败。建议对展示标签 strip surrogate 或复用既有清洗。 |
| L3 | low | `agent/loop.py:1786-1790`；`tests/agent/test_issue304_dangling_tool_calls.py:534` | 事件 `tool_call_ids` 的 20 条上限与 128 字符截断无专项测试；该测试只断言 `source`/`count`。建议补 >20 个悬空与超长 id 的断言。 |
| L4 | low | `tests/agent/test_llm_http_body.py:138-158` | task 1.3.3 要求 OpenAI 每个 `tool_calls[].id` 恰有一条 `role="tool"`；当前测试只断言合成前缀与无 `is_error`，未做逐 id 配对计数。既有 `tests/agent/test_openai_llm.py:202-260` 只覆盖单个 tool 消息。代码按构造配对正确，但测试承诺未完全兑现。 |
| L5 | low | `tests/agent/test_llm_http_body.py:31,92`；`tests/agent/test_anthropic_llm.py:985` | 1.4.8 要求 `_is_reasoning_400` 使用完整 body、只有展示才截断；当前只有 helper 属性全量断言 + trace 截断断言，没有“超过 4000 字符的 body 中尾部 reasoning 标记仍触发重试”的专项用例。 |
| L6 | low | `tests/agent/test_message_chain_repair.py:238-253` | 1.2.6 写“修复 → compact → 序列化仍合法”；该测试直接构造已配对链，未先调用 `repair_tool_call_pairing`。`tests/agent/test_loop.py:493-510` 覆盖 compaction 保留配对，但未覆盖 repair 产物。 |
| L7 | low | `tasks.md:168-170`；`benchmarks/tasks/README.md:15-21` | 4.7 的 benchmark smoke 未带 README 给出的 `--fake-edit-*`，4/68 只验证工具接线；作者已在 `35ad4c3d` 如实记录，不能把它读成任务包通过率。 |
| L8 | nit | `tests/agent/test_issue304_dangling_tool_calls.py:19-20`；`tests/web_tests/test_issue304_web_resume.py:3` | 已由 `f38573cf` 提交清理（`os`/`json`）；工作区干净。 |
| L9 | nit | `tasks.md:50` | 1.2.1 仍写 `test_issue304_dangling_tool_calls_repro.py`，实际文件为 `test_issue304_dangling_tool_calls.py`；建议改文案。 |
| L10 | low | `web/session.py:2182-2188`；`:81-99` | HTTP 错误无 body 时 error 事件不写 `status_code`，`_group_failure_summary` 返回空；design 写“非 JSON 时只保留 `HTTP <status>`”。空 body 的群聊失败原因会退化为“运行失败”。建议对 HTTP 错误即使 body 为空也带上 status（仍不泄漏 body）。 |
| L11 | low | `web/session.py:2249-2251` | `turn_error_message` 被每个 error 事件覆盖；若先 HTTP 错误、后一个无 status 的 error，HTTP 摘要会被清空。建议只在摘要非空时覆盖，或保留首个/最相关摘要。 |
| L12 | nit | `web/session.py:58`；`agent/trace_recorder.py:23` | `LLM_ERROR_DETAIL_LIMIT=4096` 与 `TRACE_PREVIEW_CHARS=4000` 不一致；不影响正确性，建议统一或注明。 |
| L13 | nit | `docs/openspec-change-backlog.md:122` | backlog 条目仍写“设计阶段，待实现”；归档收尾时会移除，留在 active 阶段不影响门禁。 |
| L14 | nit | `agent/message.py:248-256`（`_synthetic_tool_result` 文案） | 若真实工具结果恰好以固定前缀开头会被标 `is_error`（1.4.10 测试已钉住该已知限制）；属已知限制，无需修。 |

## 收口确认

- 批次项数：1（B1 high）
- B1 修复验证：是（`f38573cf` 的 seq 5/6 事件 + witnessloop 复验通过）
- 低优先级修复验证：6/6 verified（L3/L4/L6/L9/L10/L11）
- 未修项：L1/L2/L5/L7/L12/L13/L14 理由已确认，登记保留
- deferred：0
- 出口：**PASS**（第 1 轮批次 + 低优先级修复均收口）

## 闭环出口

PASS

B1 已由 `f38573cf` 的 seq 5/6 事件修复并复验；L3/L4/L6/L9/L10/L11 已由 `a38159dd`
修复并验证；L1/L2/L5/L7/L12/L13/L14 理由已确认保留；deferred 0。
最终审阅 head：`a38159dd`。witnessloop check 只剩 review manifest 待办（内容提交、
归档 move 之后构建），不改变 PASS。
