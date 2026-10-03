# Building Review: tool-result-lifecycle (issue #282)

**Verdict**: PASS （Round 2 复审；第 1 轮 CHANGES_REQUESTED 的中等问题 M1/M2 已修复并复现核实，无新引入的高/中问题——见文末 `## Round 2 Re-review`）

审阅者：独立零记忆 subagent。范围：`git diff fdd53e0 01da049`（base = master `fdd53e0`，head = `01da049`，33 文件 / +3399）。环境：`uv run pytest`。

## 结论摘要

核心机制**已真实现**（非声称）：三持有者有界化、`messages` spill+ref、`_tokens` 重置、
硬顶双维度、Web 按需回读、GC 不变量测试（**确实断言内存字段**，非只靠弱引用）都在代码里，
且全量测试**除 2 个 pre-existing `/tmp` 环境失败外全绿**，OpenSpec strict validate **29/29 通过**。

但存在 **2 个中等严重度的「静默失效有界保证」缺陷**（都可复现），违反 spec ADDED Requirement
「任何持有工具结果全文的常驻池 SHALL 有界」的核心 SHALL：

1. `_result_ref_present` 用子串 `"[truncated"` 判幂等 → 真实结果含该子串即被误判「已 spill」→
   **永不剪枝、全文常驻**（可复现）。
2. resume 路径：`_reset_tool_result_iterations` 每次 run 清空标记 → 重载的历史工具结果
   **无标记、永不剪枝** → 恢复的会长结果常驻。

另有 4 个低严重度项（图片无 file_path 数据丢失、新端点跨 scope 读、可观测欠计、债未记）。
**无高危（数据损失/安全/协议破坏）问题。**

## 逐条任务验证（tasks.md §3，3.1–3.13）

| # | 状态 | 证据 |
|---|---|---|
| 3.1 前置核实 D11 | 已实现 | `benchmarks/runner.py:406-413` 显式 `full_trace=True`；`trace_recorder.py:59-63` 注释；design D2 核对表 |
| 3.2 先写失败测试 | 已实现 | `tests/agent/test_tool_result_lifecycle_loop.py`、`tests/agent/memory/test_tool_result_lifecycle.py`、`tests/agent/test_trace_recorder_bounded.py`、`tests/agent/test_artifact_store.py`、`tests/agent/test_read_artifact_resolver.py`、`tests/web_tests/test_tool_result_expand.py` |
| 3.3 agent 通用 ref 存储 | 已实现 | `agent/artifact_store.py`（`AgentArtifactStore` / `ArtifactRef` / `atomic_write`）；`agent/session.py:193-207` 显式清理；`workflow_store.py` 委托共享实现 |
| 3.4 泛化 ReadWorkflowResult | 已实现 | `agent/tools/builtin/subagents.py:917-984`（`_resolver` 按前缀分派；description 已改写；注册路径 `loop.py:439`） |
| 3.5 两段式判定 | 已实现 | `agent/memory/tool_result_policy.py`（纯函数）+ `loop.py:1604-1636`（注入 store/scope） |
| 3.6 `prune_tool_results` | 部分（见 M1/M2） | `manager.py:212-276`；两 append 点记 `added_iteration`（`loop.py:885,1080`）；`_tokens=None`（`:268`）。幂等判据有缺陷 |
| 3.7 trace bounded + arguments | 已实现 | `trace_recorder.py:23-52,116-155,201-204`；`test_trace_recorder_bounded.py` |
| 3.8 `ToolCallMade.result/arguments` bounded | 已实现 | `loop.py:888-889,1084-1087`；`_bound_ledger_result`/`_bound_arguments`（`:1572-1592`） |
| 3.9 硬顶双维度 | 已实现 | `manager.py:296-344`；`HARD_CEILING_MULTIPLIER/BYTES_PER_TOKEN/MIN_BYTES`；`test_tool_result_lifecycle.py:293-351` |
| 3.10 spill 可观测 | 已实现 | `trace_recorder.py:230-246`；`loop.py:1625-1634`（`tool_result_spill` 事件+step）。计数欠计见 L3 |
| 3.11 D12 Web 按需回读 | 已实现 | `loop.py:875-881,1061-1067`（去全文+`tool_call_id`）；`web/server.py:245-262`；`web/session.py:907-947`；`web/static/chat.js:923-1010` |
| 3.12 回归 | 已实现 | `tests/web_tests/test_server.py`/`test_session.py` 断言更新到 D12 契约 |
| 3.13 E0 端到端 | 已实现 | `scripts/e0_tool_result_lifecycle.py`；`reviews/e0-record.md`（如实记录 RSS 缩比不可判） |

**总评**：13 项均落地（3.6 有可复现缺陷），无「声称未做」。

## Issues

### 高
无。

### 中

**M1 — `_result_ref_present` 子串误判 → 有界保证静默失效**
`agent/memory/manager.py:37-39` 定义 `_result_ref_present(content) = "[truncated" in content`，
`:247` 用它做幂等判据（「已是 preview ⇒ 跳过」）。任何**真实**工具结果只要正文含子串
`[truncated`（例如 `Read` 一个含该字面量的日志/文档——**本仓库自己的 `agent/subagent/manager.py`、
`docs/` 多处含 `…[truncated]`**），就会被误判为已 spill → 永不替换 → 全文**永久常驻**，且**无任何告警**。
- 期望：仅当内容确为「本管线产生的 preview + ref 标记」时跳过。
- 实际：子串命中即跳过。
- 复现：
  ```
  body = 'x'*400_000 + '\n[truncated] more'   # 含字面量
  mm.prune_tool_results(msgs, current_iteration=5, added_iterations={'c1':1}, save=...)
  # → messages_spilled = 0，len(content) 仍 400031（应为 1 / 已剪）
  ```
- 违反：`specs/context-engineering/spec.md` ADDED Requirement 第 1 段（SHALL 有界）与 Scenario
  「超大单条结果在消费一轮后穿透近期窗口被替换」。
- 建议：改为锚定 `extract_result_ref()` 或匹配完整标记（`…[truncated; full result in result_ref: …]` /
  `…[truncated]` 结尾），而非裸子串；补回归测试（结果内含 `[truncated]` 仍被剪）。

**M2 — resume 后重载的历史工具结果永不剪枝**
`agent/loop.py:1550-1556` 的 `_reset_tool_result_iterations` 每次 `run()` 把
`self._tool_result_iterations` 清空；而重载的历史消息（`loop.py:705-715` 从 `resume_snapshot.messages` 恢复）
其工具结果的 `tool_call_id` 不在新字典里 → `manager.py:249-251` 因 `added is None` 跳过 → **永不剪枝**。
若快照时刻某大结果仍是全文（落在 recent 窗口内），resume 后它将**常驻到底**，与本 change 的降峰目标相悖。
- 期望：重载的历史工具结果已被模型消费过；应可被剪。
- 实际：无标记 ⇒ 永久保全文。
- 复现：
  ```
  msgs = [user, tool_result_message('c1', 'Z'*400_000)]
  mm.prune_tool_results(msgs, current_iteration=99, added_iterations={}, save=...)
  # → messages_spilled = 0，len 仍 400000
  ```
- 违反：`specs/context-engineering/spec.md` ADDED Requirement 第 1 段；Scenario「陈旧的工具结果被替换」。
- 建议：`_reset_tool_result_iterations` 改为**给重载的、role=tool 的历史消息预置**一个「已消费」的
  iteration 标记（如 `-1` 或 `current_iteration`），而非一律清空；补 resume 回归测试。
- 备注：design D3 把「未标记不剪」当保守选择，但对 resume 历史而言该保守被过度放宽——设计未覆盖此路径。

### 低

**L1 — 图片（`file_path is None`）base64 静默丢失，`image_refs` 为死参数**
`tool_result_policy.py:122-146`（`flatten_content`）与 `:161-177`（`make_preview`）支持
`image_refs`，但**无任何调用方传入**（grep 仅命中本模块）。design D6 第 3 点要求
「`file_path is None` 时把 base64 落 ref store、标 `[image: <ref>]`」——**未实现**。
落盘件 `_flatten(content)` 同样丢 base64 ⇒ 即便人工回读也拿不回像素，与「逐字节无损回读」
Scenario 不符。实践中 upload/read/screenshot **都设 `file_path`**，故影响有限，但属未兑现的设计点。
- 建议：要么实现 D6.3，要么在 design 明确「图片一律经 `file_path` 引用、`image_refs` 不做」并删死参。

**L2 — 新端点按内容内嵌 ref 决定 scope，未校对本 session scope**
`web/session.py:907-947`：`resolve_tool_result` 从消息文本 `extract_result_ref` 取 ref，再
`AgentArtifactStore.for_workspace(workspace_root, parsed.scope_id)`——scope 完全取自 ref 本身，
**未校验 ref 是否属于本 session**。若某消息文本内嵌了 `artifact://agent/<其它 scope>/<key>`，端点会去读那个
scope（同一 workspace 内）。因 key 为随机 hex16 且需内容注入，**实际不可达**，但为纵深防御缺口。
- 建议：端点读 ref 时限定 `parsed.scope_id == session 自身的 artifact scope`。端点只读、与既有
  `/timeline` 同为「session 在内存即放行」的无鉴权姿态，与既有面一致（不计安全高危）。

**L3 — 可观测欠计**
`loop.py:1081-1091` 的 `bounded_ledger` 只统计 Phase-3 的 `tool_calls_made` 有界次数；
trace 的有界（在 `record_tool_result` 内部发生）与**错误路径**（`loop.py:889`，parse-error 分支）
的有界**未被计数**。`tool_result_spill` 事件的 `bounded_ledger` 因此偏小。
- 建议：把 trace/错误路径的有界也纳入计数（或明确 `bounded_ledger` 语义仅为 tcm）。

**L4 — `MAX_IMAGE_SIZE` 矛盾未记债**
design D6 明写「20MB/张 与常驻有界的矛盾先记为单位债务（`docs/known-debt.md` 或 #283 一并评估）」；
`docs/known-debt.md` 无相应条目（grep 无命中），本 change diff 也未触及。属文档收尾遗漏。
- 建议：补一条 known-debt 或写进 #283 body。

## 质量维度结论（无问题项也明确「通过」）

- **正确性（除 M1/M2）**：窗口边界（`index < len-window`）、`added <= current-1` 语义、
  `_tokens=None` 重置（`manager.py:268`）、剪枝→硬顶→压缩次序（`loop.py:1092-1099`）均正确，有测试。
- **GC 不变量测试真能抓假通过**：`test_gc_invariant_three_holders_all_bounded` **同时**断言
  `trace.steps[*].data["observation"]` 与 `tool_calls_made[*].result` 的内存字段 < 400K，并 `weakref` 回 None ——
  满足 D0 硬约束（`asdict` 对 `_WeakStr` 复制导致的假通过被内存字段断言拦住）。**通过**。
- **安全性（新端点）**：只读、无写、不写回 `messages`；ref 路径**段级拒绝 `..` + `resolve()` 包含性校验**
  （实测 `artifact://agent/s-abc/../../etc/passwd` 等全部 blocked）；跨 workspace 由 workspace_root 隔离。
  唯一缺口为 L2（跨 scope，实际不可达）。**通过（附 L2）**。
- **冗余度**：`WorkflowStore` 与 `AgentArtifactStore` 共享 `ArtifactReader`/`ArtifactRef`/`atomic_write`
  （单一来源），无漂移；`RESULT_REF_PREFIX` 等旧名以别名保留向后兼容。**通过**。
- **测试覆盖**：token/字节边界、图片字节、预览保尾、arguments、resume 同 scope 不覆盖、
  `_tokens` 重置、hard ceiling token+字节、missing 端点降级均有。缺口：M1（含 `[truncated` 的结果）、
  M2（resume）无测试。**部分**。
- **可维护性**：模块 docstring 完整，命名清晰，单一来源纪律良好。`flatten_content` 的 `image_refs` 为死参（L1）。
- **CI 完整性**：全量 pytest 2 failed / 3950 passed（2 失败 = pre-existing `/tmp` git 环境坑，
  `persistent.py` 本 change 未改）；OpenSpec strict validate 29/29。**通过**。

## 关键证据（命令）

- `git diff fdd53e0 01da049 --stat` → 33 files, +3399/-139。
- `uv run pytest -q` → `2 failed, 3950 passed, 9 skipped`。失败项均为
  `test_persistent.py::TestFindScopeRoot::*`；`ls /tmp/.git` 存在，`git diff … -- agent/memory/persistent.py` 无输出 ⇒ pre-existing。
- `npx @fission-ai/openspec@1.4.1 validate --all --strict` → 29 passed / 0 failed。
- M1 复现（400KB 结果含 `[truncated` → `messages_spilled=0` 且正文仍 400031 字符）。
- M2 复现（无标记 → 400000 字符不被剪）。
- 路径逃逸 3 例全部 `blocked`。

## 复审建议

M1、M2 各配一条回归测试并修法后重跑 `/review-loop`；L1–L4 可本轮修或转 issue/债务记录。

---

## Round 2 Re-review

**Verdict**: PASS

复审范围：修复提交 `0e17694`（`git show 0e17694`，9 文件 / +152·-39），只审「修复是否真解决 + 是否引入新问题」。
方法：读 diff + 亲自构造反例攻击新判据 + 跑相关测试子集与全量。

### 逐条修复核实

**M1（`_result_ref_present` 子串误判）— 真解决**
- 修法：`tool_result_policy.py:61-79` 新增 `is_spilled_preview()`，正则 `_PREVIEW_SUFFIX_RE = …\[truncated(?:; full result in result_ref: artifact://[^\s\]]+)?\]\s*$`（`…` 前导 + 行尾锚定）；`manager.py:243` 改用它。
- 复现：400KB 结果含 `[truncated]` 字面量 + `save=` → `messages_spilled=1`（修复前为 0），`extract_result_ref` 非空，正文 < 400K。✓
- 反例攻击（无漏判/误判）：
  - 真 preview 全命中：无 ref、有 ref、带 `[ReadProgress]` 尾注 三种形态 `is_spilled_preview` 均 **True**（**无漏判**）。
  - 含字面量的真实结果：`'log [truncated] continues'`、`'body [truncated]'`（无 `…` 前导）、subagent 的 `…[truncated; full result in result_ref]`（无 `artifact://`）均 **False**（**无误判**）。
- 回归测试 `test_prune_still_spills_result_containing_truncated_literal` / `test_is_spilled_preview_anchors_not_bare_substring` **PASS**；已核对旧判据在相同输入上返回 `True`/`None` ⇒ 测试在旧代码上**确会失败**（非假绿）。
- **残留（低、非阻塞）**：一个真实结果若**恰好以**字面量 `\n…[truncated]`（或 `…[truncated; full result in result_ref: artifact://…]`）**结尾**，仍会被判为 preview 而保留全文。但此类内容本身**就已是一条 preview**（形状完全相同），保留它不违反有界性；且要求 `…` 前导 + 四种 `]` 结尾 + 无后续内容，是本 change 自身哨兵形态。**不构成缺陷。**

**M2（resume 重载历史结果永不剪）— 真解决，且无「误剪当轮新结果」副作用**
- 修法：`loop.py:1575-1607` `_reset_tool_result_iterations` 改为给已在 `messages` 里的 `role=tool` 消息**批量预置 `-1`**；并在 `_run()` 的 resume 重建历史**之后**（`loop.py:723-726`）**再跑一次**（首次在第 600 行覆盖不了重建后的历史）。`-1` 恒满足 `added <= current-1`。
- 复现：构造含 400KB 全文工具结果的 `SessionSnapshot` → `run(resume_snapshot=…)` → 该历史结果被替换为 preview + ref，正文 < 400K。✓
- **安全性攻击（关键）**：预置 `-1` 只命中历史（本 run 前已产生）。构造「历史 `-1` + 当轮新结果（birth iteration=7）」同处 `messages`：iteration 7 剪枝 → **仅历史被剪（1），当轮新结果保持全文 400K**；iteration 8 新结果已消费 → **两条都被剪（2）**。**「当轮不剪新鲜结果」（spec Scenario「当轮工具结果不被替换」）语义未破。** ✓
- 回归 `test_resumed_history_tool_result_is_spilled` **PASS**；已核对旧逻辑下该 id 无标记 ⇒ 被 `added is None` 跳过 ⇒ 测试在旧代码上**确会失败**。
- 备注：docstring 已说明「同 run 先 append 后重入 `_run`」的理论路径也不破坏当轮保留语义（剪枝在 Phase-3 末尾，产生轮本就不剪）。

**L1（`image_refs` 死参 / 图片 base64 丢字节）— 已关闭（按备注接受）**
- 修法：`flatten_content`/`make_preview` 删 `image_refs` 死参，一律经 `file_path` 引用；design D6 第 3 点加删除线并注记「不采用 base64→ref」+ 理由（所有图片工具都设 `file_path`）。
- 核实：`grep -rn image_refs agent/ tests/` **零命中**（无残留引用）；所有 `ImageBlock` 构造点（`read.py:244`、`browser_screenshot.py:25`、`uploads.py:133/153`）均设 `file_path`，与 design 理由一致。极端 `file_path is None`（反序列化旧块）退化为 `[image: pasted image]`——**非本 change 引入**，且字节维度仍约束该块。**接受**。

**L2（新端点跨 scope 读）— 已关闭**
- 修法：`web/session.py` `resolve_tool_result` 增加 `session_scope = session.session_id`，并要求 `parsed.scope_id == session_scope`，否则返回 missing。
- 复现：消息内嵌 `artifact://agent/s-OTHER/…` 的 ref → 端点返回 `missing=True`/`content=""`（不再读他人 scope）。✓ 回归 `test_resolve_refuses_cross_scope_ref` **PASS**。
- 正确性：根 session 的 artifact scope 就是 `session_id`（`loop.py:_make_artifact_store`，`artifact_scope_is_run=False`），故校验口径正确；Web 端点只服务根级工具结果（子 agent 无 `on_event`）。**真解决。**

**L3（可观测欠计）— 已关闭**
- 修法：`_bounded_ledger_count`（`loop.py:213`）在 `_bound_ledger_result`（`loop.py:1602`）**与** `_bound_arguments`（`loop.py:1612`）内自增，每 iteration 顶部归零（`loop.py:763`）；`_spill_and_prune` 读它（`loop.py:1104`）。docstring 明确「仅计 `tool_calls_made` 条目，trace 有界单独可见、不计入」。
- 复现：真实 loop run 带一个 400KB `Write` 参数 → `tool_result_spill` 事件 `bounded_ledger=1`（旧：0），tcm `arguments` 已 bounded（4012 字符）。✓ 无重复计数。
- 残留（极低）：错误路径的 `_bound_ledger_count` 自增只在同 iteration 也跑正常 Phase-3 时才经事件外发（错误路径 `continue` 不调 `_spill_and_prune`）；但 parse-error 结果恒为小字符串（`"[Error: …]"`），**永不超阈 ⇒ 永不 bounded**，该分支实际不产生计数。**不构成缺陷。**

### Round 2 新增问题

**无高/中/低新增问题。** 未发现 M1/M2 修法引入的任何回归；L1–L3 收口正确；L4（`MAX_IMAGE_SIZE` 债未记）本轮**未改**，维持第 1 轮的「低、非阻塞、收尾补记」判定（不阻塞 PASS——属文档收尾项，非代码正确性）。

### Round 2 测试证据

- 4 条命名回归全 **PASS**（`test_prune_still_spills_result_containing_truncated_literal` / `test_is_spilled_preview_anchors_not_bare_substring` / `test_resumed_history_tool_result_is_spilled` / `test_resolve_refuses_cross_scope_ref`）。
- 相关子集 `uv run pytest -q tests/agent/subagent/ test_trace_recorder*.py test_artifact_store.py test_read_artifact_resolver.py test_tool_result_lifecycle_loop.py tests/agent/memory/ tests/web_tests/test_tool_result_expand.py tests/web_tests/test_server.py tests/web_tests/test_session.py` → **1114 passed, 2 failed**，2 失败 = `test_persistent.py::TestFindScopeRoot::*`（pre-existing `/tmp` git 环境坑，与本 change 无关）。
- 全量 `uv run pytest -q` → **2 failed, 3954 passed, 9 skipped**（346s）。2 失败与 Round 1 同：`test_persistent.py::TestFindScopeRoot::*`（pre-existing `/tmp` git 环境坑，与本 change 无关）；新增 4 条回归使通过数 3950→3954。
- OpenSpec strict validate 未受本轮影响（本轮无 spec delta 改动）。

**判定**：第 1 轮两个中等问题 M1/M2 **真解决并复现核实**，无新引入问题 ⇒ **PASS**。L4 建议在收尾（归档/PR）前补记 `docs/known-debt.md` 或写进 #283。
