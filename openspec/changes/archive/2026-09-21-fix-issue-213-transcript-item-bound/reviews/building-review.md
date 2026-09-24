# Building Review — fix-issue-213-transcript-item-bound（Round 3）

我是**独立代码审阅者（零记忆，不继承任何开发上下文）**。本会话未读开发者的任何对话、推理或
先前会话产物；下列每条结论只来自 (a) `git show 71d3594` 与 `git diff 7c23059...HEAD` 的实际代码、
(b) change 文档与 issue #224 原文、(c) 我在本仓库**实跑**的命令、7 组变异体与 `/tmp/review_213r3/`
下的探针输出。所有「声称已修 X」都逐条对代码复验；凡未验证的明确写「未能验证」。

**方法核心是变异验证 + 端到端探针**：把本轮（R2）与历史每一条关键修复逐条改坏，跑该 change 自己的
回归测试看是否变红；同时用两个独立探针走**真实工具路径**复现 4 个出口的边界行为。
**所有仓库文件在每次变异后即 `git checkout --` 还原**，收尾 `git status --short` 为空（见文末）。

## Reviewer

- run id: review-fix-issue-213-2026-09-21-r3
- 时间: 2026-09-21
- 本轮修复提交: `71d3594`
- 基线: `7c23059`（master） → head `71d3594`（分支 `fix-issue-213-transcript-item-bound/2026-09-21`）
- 审阅方法（实跑命令）:
  - `uv run pytest -q tests/web_tests/test_workflow_node_transcript.py tests/agent/subagent/ -p no:randomly` → **551 passed**
  - `uv run pytest -q tests/agent/tools/ tests/agent/subagent/ -p no:randomly` → **912 passed**
  - `uv run pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py -p no:randomly` → **338 passed**
  - `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref 7c23059 --require-base` → **exit 1**（见 Issue 1）
  - `npx --yes @fission-ai/openspec@1.4.1 validate fix-issue-213-transcript-item-bound --strict` → `is valid`
  - **变异验证 7 组**（每组改完即跑测试，随后 `git checkout --`）：
    N1 去掉 `_bounded_summary` 钳制；N2 `_worker_entry` 删 `result_ref` 赋值；
    N3 落盘 `has_ref=True` 改读属性；N4 `_format_run_envelope` 默认值翻成 `full_summary=True`；
    N5 删 `entry["summary_truncated"]`；N5b 标志恒 `False`；N6 调度器去掉 `full_summary=True`（出口 3）；
    N7 路由丢掉 `content_truncated` 取或；M6 别名被拆开；M7/M8 三处同值漂移
  - `PYTHONPATH=. uv run python /tmp/review_213r3/probe_exits.py`（真实工具路径 4 出口 × 4 档 `max_tokens`）
  - `PYTHONPATH=. uv run python /tmp/review_213r3/probe_bus.py`（bus 出口现状独立复现）
  - `gh api repos/Xingkai98/asterwynd/issues/224`
  - 收尾 `git status --short` → 空

## Verdict

**PASS**

R2 报告列出的 4 条 issue（1 major + 3 minor）**全部真正修复**，且每一条修复我都做了**变异验证**
（改坏→测试变红→还原），没有一条是「改坏了还全绿」。前两轮的核心设计在本 HEAD 上仍然成立并被
正确实现，我独立复现确认（见「核心设计独立复验」）。**未发现任何新的模型面出口仍无界**——唯一
遗漏的 bus 出口被**如实**记录为未覆盖（proposal Non-Goal + design + issue #224），没有伪装成已修。

**唯一附带的合入前动作**（见 Issue 1，非代码问题）：`reviews/building-review.md` 已入库但
缺 `building-review-manifest.json`，`check_openspec_artifacts.py` 在 HEAD 上**实测 exit 1**；
而 `tasks.md:72` 仍把「artifact checker 通过」勾成 `[x]`——在**当前 HEAD** 上这是一句**不实勾选**。
manifest 只能在审阅判 PASS 后生成（它绑定 `verdict=PASS` 与报告 hash，先于 PASS 生成在逻辑上
不可能），故这一条**由本报告判 PASS 后立即生成 manifest 即可消除**（生成后 `[x]` 自动成真）。
我把它列为需在 PR 合入前清零的动作，而不是代码缺陷。

## Round 2 Issue 验证

| R2 Issue | 声称的修复 | 我的独立验证结果 |
|---|---|---|
| **1 (major)** 缺 manifest → checker exit 1；tasks 勾 `[x]` 为不实 | 「manifest 在审阅 PASS 后生成，属收尾顺序问题」 | ⚠️ **半成立**：(a) 我实跑 checker **确实仍 exit 1**（manifest missing）；(b) `tasks.md:72` 的 `[x]` 在**当前 HEAD**上**仍是不实勾选**（无 manifest 则 checker 必红）。该 false check 由 `022cc46` 引入（那时 reviews/ 只有 grill-design.md，checker 真通过），在 `d370d3c` 加入 review 报告后失效，R3 未纠正。**但**manifest 不可能先于 PASS 生成——判 PASS 后立即生成即可消除。列为 Issue 1。 |
| **2 (minor)** `summary_truncated` 标志零保护（`if entry.get(...)`） | 改为无条件断言「确实存在被裁过的条目」 | ✅ **成立**：代码已改为 `entry["summary_truncated"]`（直接索引，`:911`）+ `assert truncated_entries`（`:914`）。变异 N5（删标志）→ `KeyError` 变红；N5b（标志恒 False）→ `assert truncated_entries` 变红。**不再是条件式**。 |
| **3 (minor)** 改名不彻底（`manager.py:218`、`docs/agent-internals.md:1001` 写 `summary_chars`） | 清干净，全仓 0 残留 | ✅ **成立**：全仓 grep `summary_chars` 在 **代码/文档/测试** 0 命中，仅剩 `reviews/{building-review,grill-design}.md` 两处历史审阅记录（属历史快照，不应回改）。`manager.py:218`/`docs/agent-internals.md:1001` 均为 `summary_full_chars`。 |
| **4 (minor)** design.md 两处与实现矛盾（D3 表、D9） | 按实现更正 + 新增 D10 | ✅ **成立**：`design.md:11` 已写 `min(max(2000, max_tokens*4), TRANSCRIPT_ITEM_LIMIT)`；D9 已改为「走固定的 `TRANSCRIPT_ITEM_LIMIT`（经 `_clip`）」；新增 D10 如实记录钳制修法 + 副作用。仅剩 **D3b 一处轻微残留**（见 Issue 3）。 |
| **R1 Issue 7**「三处同值」实为两处 | 补成真的三处 | ✅ **成立**：`test_workflow_node_transcript.py:627` 新增 `TOOL_CALL_ARGUMENT_LIMIT == TRANSCRIPT_ITEM_LIMIT`；`:630` 保留 `TRANSCRIPT_ITEM_LIMIT == TRANSCRIPT_CONTENT_LIMIT`。变异 **M6**（别名拆开 3500）→ `:627` 红；**M8**（新名漂到 4001、别名跟随）→ `:630` 红；**M7**（新名漂 + 别名钉旧值）→ `:627` 红。三处**真的**被锁死。 |

### 核心设计独立复验（`/tmp/review_213r3/probe_exits.py`，真实工具路径）

`WorkflowScheduler.run` → 模型自撰 `spec.nodes[0].max_tokens` → 4 个出口的**工具返回体**：

```
TRANSCRIPT_ITEM_LIMIT = 4000, HUGE = 30000
max_tokens=None     exit2 GetSubagentRun: summary=4000 bounded_summary=2040 整包含HUGE=False bs含HUGE=False
max_tokens=5000     exit2:                summary=4000 bounded_summary=4040 整包含HUGE=False bs含HUGE=False
max_tokens=50000    exit2:                summary=4000 bounded_summary=4040 整包含HUGE=False bs含HUGE=False
max_tokens=500000   exit2:                summary=4000 bounded_summary=4040 整包含HUGE=False bs含HUGE=False
（每档）exit1a inspect summary len=4000 flag=True 含HUGE=False
（每档）exit1b inspect messages max_content=4000 any_flag=True 含HUGE=False
（每档）exit3 state.summary 全文? True
（每档）route content_flags=True 含HUGE=False
exit4 RunPatternTool: workers=3 max_summary=4000 含HUGE=False  flags=[T,T,T] refs=[T,T,T]
```

- **固定上限不随 `max_tokens` 放大** ✅：`bounded_summary` 恒 4040（= 4000 截断 + 40 字标记），
  与 grill 决策 Q1 一致；`summary_full_chars=30000` 如实给出全文长度。
- **`_format_run_envelope` 默认 bounded + 调度器 `full_summary=True`** ✅：exit2 工具面 4000；
  exit3 `state.summary` 保持 30000 全量（下游聚合不被饿死）。
- **`_bounded_summary` 预算钳制** ✅：见上。
- **HTTP 取或** ✅：route `content_flags=True` 且不含全文。
- **4 个结果出口全覆盖** ✅：exit1a/1b/2/4 全部 ≤4000，exit3 全量。

## Tasks Verification

| tasks.md 条目 | 状态 | 证据 |
|---|---|---|
| `TRANSCRIPT_ITEM_LIMIT = 4000` + 旧名 alias | ✅ | `manager.py:89` / `:93` |
| `_format_run_envelope` 按固定上限、不读 `max_tokens` | ✅ | `manager.py:1562-1565` 用 `_bounded_content`（→`TRANSCRIPT_ITEM_LIMIT`） |
| `_clip` / `_bounded_arguments` 薄封装 / `_bounded_content` | ✅ | `manager.py:96-116` |
| `inspect_transcript` summary 分支截断 + `summary_truncated` | ✅ | `manager.py:1122-1133` |
| `recent_messages` 逐条截断 + `content_truncated` | ✅ | `manager.py:1153`（`_bounded_content_message`） |
| `_format_run_envelope(..., full_summary=False)` 默认 bounded | ✅ | `manager.py:1539-1566`；N4 变红 |
| `scheduler` 内部消费传 `full_summary=True` | ✅ | `scheduler.py:2173`；N6 变红 |
| `patterns._worker_entry` summary 固定上限 + 补 `result_ref` | ✅ | `patterns.py:342-370`；N2 变红 |
| `_bounded_summary` 只在确有 ref 时提「全文在 X」 | ✅ | `manager.py:66-74`；N3（落盘改读属性）变红 |
| `to_result_dict()` 增 `summary_full_chars` | ✅ | `manager.py:228` |
| `web/session.py` `content_truncated` 取或 + 透传 | ✅ | `web/session.py:763`；N7 变红 |
| `workflow_transcript.js` content 截断 UI 提示 | ✅ | `workflow_transcript.js:317-319`（`（内容已截断）`）+ index.html 版本号 v2→v3 |
| `InspectSubagentTranscript` 描述校正 | ✅ | `subagents.py:187-193` |
| 常量「三处同值」断言升级为真三处 | ✅ | `test:627` + `:630`；M6/M7/M8 变红 |
| 变异验证（identity / 取或 / envelope full） | ✅ | 我独立复跑 N1–N7 全部变红 |
| 回归 `tests/agent/subagent/`、`tests/web_tests/` | ✅ | 551 / 912 / 338 passed |
| `docs/agent-internals.md` 示例更新 | ✅ | `:1001` `summary_full_chars`；`:963-1001` 含截断说明 |
| `diagnosis.md` / spec delta | ✅ | 文件在，格式与 strict validate 通过 |
| **当前规格同步 / backlog 移除**（`[ ]`） | 未做（收尾阶段） | 受保护路径，待 `current_spec_synced`/`backlog_updated` 事件——**与本轮代码无关** |
| **生成 review manifest**（`[ ]`） | 未做 | 见 Issue 1 |
| `tasks.md:72` `artifact checker 通过`（`[x]`） | ❌ **与 HEAD 事实不符** | checker 实测 exit 1；见 Issue 1 |
| 全量 pytest / strict validate | ✅（未复跑全量，按要求） | strict validate 我实跑通过；全量 pytest 按环境约束未复跑 |

## Issues

### Issue 1（severity: minor，但须在 PR 合入前清零）— HEAD 上 checker 仍红，而 tasks 勾了「通过」

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/reviews/`（缺
  `building-review-manifest.json`）+ `tasks.md:72`
- 描述: R2 报告已入库，但 manifest 未生成。`scripts/check_openspec_artifacts.py`
  （`.github/workflows/ci.yml:62` 的 required check）在 HEAD 上**实测 exit 1**：
  ```
  $ PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py --base-ref 7c23059 --require-base
  ERROR: fix-issue-213-transcript-item-bound: review manifest missing:
    openspec/changes/fix-issue-213-transcript-item-bound/reviews/building-review-manifest.json
  exit=1
  ```
  而 `tasks.md:72` 仍写作 `- [x] OpenSpec artifact checker 通过`。无 manifest 则 checker 必红，
  故该 `[x]` 是**当前 HEAD 上的不实勾选**（`d370d3c` 加入 review 报告后失效，R3 未纠正），
  违反本仓库「禁止虚假完成」的规则。同一文件 `:64` 又把「生成 review manifest」留作 `[ ]`——
  两者自相矛盾。
- 说明（为何判 PASS 而非阻塞）: manifest 由 `/review-loop` 在 **PASS** 时生成并绑定
  `verdict=PASS` 与报告 hash（`agent/workflow/review_manifest.py` 的 `REQUIRED_REVIEW_FIELDS`），
  **不可能先于 PASS 生成**——要求 PASS 前 checker 绿是逻辑闭环。故这是收尾时序问题而非代码缺陷。
  且 CI 自身会拦住合入：manifest 不落地，`validate` 这条 required check 恒红，PR 合不进去。
- 建议: 本报告判 PASS 后**立即**生成 `building-review-manifest.json`（绑定 reviewer run /
  base·head sha / tasks·spec·diff·report hash）→ 重跑 checker 应变绿 → `tasks.md:72` 的 `[x]`
  随之成真。若因故暂不生成，应把 `:72` 改为 `[ ]` 直到 manifest 落地，切勿留不实 `[x]`。

### Issue 2（severity: minor）— `patterns._worker_entry` 的 `result_ref` 是「有则放、无则不放」的键存在性，测试只覆盖有值路径

- 位置: `agent/subagent/patterns.py:365-370`、`tests/web_tests/test_workflow_node_transcript.py:931-946`
- 描述: 实现正确（`if truncated: entry["summary_truncated"]=True; ref=getattr(...); if ref: entry["result_ref"]=ref`）。
  但 **`summary_truncated=True` 而 `summary` 未被裁到上限之下** 的组合下，条目会带 `summary_truncated`
  却不带 `result_ref`——即「说截断了但拿不到全文」。当前 `_clip` 只在该分支返回 `truncated=True` 当且
  仅当真的超限，故**当下不会触发**；我未构造出该状态，故不作为缺陷，仅记录为**契约敏感点**：
  将来若 `_worker_entry` 改为「无条件标记 truncated」（如为对齐其他出口），会立刻在出口 4 造出
  「截断却无 ref」的表述。已有测试 `test_worker_entry_without_workflow_identity_does_not_lie`
  锁住「无 ref 不放键」，但**没有**锁「`summary_truncated=True` ⟹ `result_ref` 在场且真能取全文」。
- 证据: 探针 exit4 实测 `workers` 三条全 `flags=[T,T,T] refs=[T,T,T]`（当前构造下二者同步）；
  变异 N2（删 `result_ref` 赋值）→ `test_worker_entry_summary_is_bounded_and_navigable` 变红
  （`:918` `assert "result_ref" in entry` 触发），说明**有值路径**受保护。
- 建议（可选，不阻塞）: 加一条断言把不变量钉在**语义**上：
  `assert all((not w["summary_truncated"]) or w.get("result_ref") for w in workers)`——
  覆盖「有值」与「无值」两种组合，而不依赖当前实现的巧合同步。

### Issue 3（severity: minor）— design.md D3b 仍写「调用点是三个」，与实现（两个）不符

- 位置: `openspec/changes/fix-issue-213-transcript-item-bound/design.md:124-125`
- 描述: D3b 写「且 D9 落地后调用点是**三个**（`to_result_dict` / `_write_result_artifacts` /
  `patterns._worker_entry`），第三个的语义见 Open Question Q4」。但 R3 已按 D9 更正实现为
  **`_clip`**——`patterns._worker_entry` **不调用** `_bounded_summary`。全仓 `_bounded_summary(`
  生产调用点只有**两个**：`manager.py:229`（`to_result_dict`）与 `manager.py:1373`（落盘）。
  R2 Issue 4 只点名 D3 表与 D9，未覆盖 D3b，R3 亦未改。同一类「design 与实现不符」，属残留。
- 证据: `grep -rn "_bounded_summary(" agent/` → 仅 `:52`(定义)/`:229`/`:1373`。
- 建议: 把 `:124-125` 改为「调用点是**两个**」，或注明第三个已改为 `_clip`；顺带校正同一节
  里的行号（`manager.py:1308/1301/1311/1313` 等已随文件增长漂移，属历史遗留口径）。

## 未构成 issue、但我实测确认的事实

1. **bus 出口确实仍无界，且被如实记录为未覆盖**（proposal Non-Goal + design「明确不做」+ issue #224）。
   我独立复现：`ReadBus` 单条 30000 字 → 返回 **30,150 字符**（原样含全文）；
   `RunPattern.result.bus`（`snapshot_payload()` 100×1600）→ **172,700 字符 JSON**。
   与 proposal 写的 172,703 同量级、无实质出入。**没有伪装成已修**——措辞已收敛为
   「**结果出口**的模型面文本一律 bounded」，正是本 change 的交付边界。issue #224 open，
   标题/正文/关联（#213/#212）与 change 引用一致。
2. **无其他未纳管的「换地方再犯」点**。全仓扫 `max_tokens * 4` 模型面写点：除 bus 路径
   （`subagents.py:280/289/291` 的 `PublishBusMessage._summarize`，已入 #224）外，只剩
   `agent/memory/summary.py:45`（记忆摘要，非子 agent 撰写内容，不属本 change 范围）与
   `agent/context/builder.py`（token 估算，非截断上限）。模型面工具我逐个核过：
   `ListSubagents`（仅元数据）、`GetWorkflow`/`StartWorkflow`/`RunWorkflow`（走 `parent_envelope`，
   节点文本裁到 `_PARENT_FIELD_LIMIT=200`）、`ReadWorkflowResult`（分页 + `total_chars`/`truncated`），
   均有界。**未发现新的无界出口。**
3. **exit3（调度器全量）确有测试保护**：变异 N6（去掉 `full_summary=True`）→
   `test_workflow_aggregator.py::test_collect_aggregate_compresses_through_the_summarizer`
   **变红**。即「提前裁短会让聚合器静默跳过压缩」这条不变量被机械锁定，不是空口。
4. **`summary_full_chars` 与出口被裁的 `summary` 消歧正确**：`to_result_dict` 给出全文长度
   （30000），同 payload 的 `summary` 被裁到 4000——命名带 `full_` 前缀避免了「读成 `len(summary)`」。
5. **`bounded_summary` 钳制的副作用仍良性**：`save_summary` 生产写点全局唯一
   （`manager.py:1373`），全仓无生产代码读取其正文（`grep save_summary` 仅测试命中）；
   全文由 `result_ref` 完整保留。D10 已如实记录。

## Test Results

| 命令 | 结果 |
|---|---|
| `pytest -q tests/web_tests/test_workflow_node_transcript.py tests/agent/subagent/ -p no:randomly` | **551 passed**（与提交信息一致） |
| `pytest -q tests/agent/tools/ tests/agent/subagent/ -p no:randomly` | **912 passed** |
| `pytest -q tests/web_tests/ --ignore=test_workflow_graph_browser.py --ignore=test_browser.py -p no:randomly` | **338 passed** |
| `check_openspec_artifacts.py --base-ref 7c23059 --require-base` | **exit 1（manifest missing，见 Issue 1）** |
| `openspec validate ... --strict` | `is valid` |
| `probe_exits.py`（4 出口 × 4 档 `max_tokens`，真实工具路径） | 全部 bounded，无全文泄漏，exit3 全量 ✅ |

**变异验证（全部改完即还原）**

| 变异 | 改动 | 结果 | 判别力 |
|---|---|---|---|
| N1 | `_bounded_summary` 去掉 `min(..., TRANSCRIPT_ITEM_LIMIT)` | 1 failed（`test_run_summary_limit_does_not_scale_with_max_tokens`） | ✅ 有效（R1 blocker 修复稳固） |
| N2 | `_worker_entry` 删 `result_ref` 赋值 | 1 failed（`test_worker_entry_summary_is_bounded_and_navigable`） | ✅ 有效 |
| N3 | 落盘 `has_ref=True` 改读属性 | 1 failed（`test_artifact_summary_ref_is_navigable`） | ✅ 有效 |
| N4 | `_format_run_envelope` 默认翻成 `full_summary=True` | 2 failed | ✅ 有效 |
| N5 | 删 `entry["summary_truncated"]` 标志 | 1 failed（`KeyError`，`:911`） | ✅ **有效（R2 Issue 2 已修）** |
| N5b | 标志恒 `False` | 1 failed（`assert truncated_entries`，`:914`） | ✅ 有效（无条件断言生效） |
| N6 | 调度器去掉 `full_summary=True` | 1 failed（聚合压缩测试） | ✅ 有效（出口 3 受保护） |
| N7 | 路由丢掉 `content_truncated` 取或 | 1 failed（`:844` 取或判别） | ✅ 有效 |
| M6 | 别名 `TOOL_CALL_ARGUMENT_LIMIT` 拆成 3500 | 1 failed（`:627`） | ✅ 有效（R1 Issue 7 已补） |
| M7 | 新名漂到 4001 + 别名钉 4000 | 1 failed（`:627`） | ✅ 有效 |
| M8 | 新名漂到 4001（别名跟随） | 1 failed（`:630`） | ✅ 有效 |

**环境致因（已知、非本 change，按要求未复验）**：`TestFindScopeRoot` 2 条、
`test_workflow_graph_browser.py` 负载敏感 flake——我**未复现出别的失败**。

**零残留证据**：审阅结束 `git status --short` 输出为**空**。所有探针在 `/tmp/review_213r3/`，
仓库文件在每次变异后 `git checkout --` 还原（本报告文件为覆盖写）。

## 结论

R2 的 4 条 issue **全部真修**，且每条都经我**变异验证**（改坏→变红→还原），无一漏网。
前两轮确立的核心设计在本 HEAD 上**仍然成立并被正确实现**，我以真实工具路径 + 4 档 `max_tokens`
独立复现：固定上限 4000 不随预算放大、`_format_run_envelope` 默认 bounded、调度器 `full_summary=True`
取全量、`_bounded_summary` 钳制、HTTP 取或、4 个结果出口全覆盖——全部实测确认。
**未发现任何遗漏的模型面出口仍无界**；唯一在范围外的 bus 出口被**如实**记录为未覆盖（#224），
没有伪装成已修。测试覆盖在每条关键不变量上都有机械保护（7 组变异全变红）。

**判 PASS。** 唯一需在 PR 合入前清零的是 **Issue 1**：`building-review-manifest.json` 必须由
`/review-loop` 在本 PASS 后**立即生成**（生成后 checker 转绿、`tasks.md:72` 的 `[x]` 随之成真）；
在此之前，该 `[x]` 在 HEAD 上不实，不得留作不实勾选。Issue 2/3 为可选加固与文档一致性补正，
不阻塞合入。
