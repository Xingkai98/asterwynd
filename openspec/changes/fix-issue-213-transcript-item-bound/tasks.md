# Tasks — fix-issue-213-transcript-item-bound

## 实现

- [x] `agent/subagent/manager.py`：新增 `TRANSCRIPT_ITEM_LIMIT = 4000`（docstring 按 D3c 如实说明
      它约束模型面单条内容——`content`/`summary`/`arguments` 三者同质、与
      `web.session.TRANSCRIPT_CONTENT_LIMIT` 同值）；`TOOL_CALL_ARGUMENT_LIMIT` 降为兼容别名（D5）
- [x] `agent/subagent/manager.py`：`_format_run_envelope` 的 bounded 化**用固定上限**，
      不读 `max_tokens`（D3：界不可被被检视对象影响）
- [x] `agent/subagent/manager.py`：抽 `_clip(text, limit) -> (text, bool)`；
      `_bounded_arguments` 改为薄封装（签名/返回值不变）；新增 `_bounded_content`（D6）
- [x] `agent/subagent/manager.py`：`inspect_transcript` 的 **summary 分支**截断 `summary` +
      新增 `summary_truncated`；保持 `"truncated": False` 原语义（条数）；不动 `run.summary`（D1）
- [x] `agent/subagent/manager.py`：`inspect_transcript` 的 **recent_messages 分支**逐条截断
      `content` + 新增 `content_truncated`（覆盖 assistant 与 tool 两种角色）
- [x] `agent/subagent/manager.py`：`_format_run_envelope(..., *, full_summary: bool = False)`
      默认按**固定上限**裁剪 `summary`（不读 `max_tokens`——界不可被被检视对象影响）；
      保留 `bounded_summary` 键不动（D2/D3）
- [x] `agent/subagent/scheduler.py`：内部消费点（喂 `state.summary`）显式传 `full_summary=True`
- [x] `agent/subagent/patterns.py`：`_worker_entry` 的 `summary` 走固定上限（D9）；
      **补 `result_ref` 字段**，否则条目说「全文在 result_ref」而模型拿不到该 ref（Q5）
- [x] `agent/subagent/manager.py`：`_bounded_summary` 截断标记只在**确有 ref** 时提「全文在 X」，
      否则只说已截断（D4）；落盘调用点**显式传**「有 ref」，不读属性（D3b 顺序陷阱）
- [x] `agent/subagent/manager.py`：`to_result_dict()` 增 `summary_full_chars`（**全文**长度，与出口被裁短的 `summary` 消歧），
      让模型知道被裁了多少、值不值得翻页（Q3）
- [x] `web/session.py`：`content_truncated` 改为**取或**（与 `arguments_truncated` 对称），
      并透传上游标志（D7）；同步 docstring 与常量注释
- [x] `web/static/workflow_transcript.js`：content 截断补 UI 提示（对称于既有
      `arguments_truncated` 的「（参数已截断）」）（Q4）
- [x] `agent/tools/builtin/subagents.py`：`InspectSubagentTranscript` 描述校正——明说单条内容有上限、
      全文走 `GetSubagentRun` 的 ref / `ReadWorkflowResult`（D8）；**不在工具侧加第二道截断**

## 测试

- [x] `summary` scope：30000 字 → 有界且 `summary_truncated is True`
- [x] `recent_messages`：30000 字 assistant content → 有界且 `content_truncated is True`
- [x] `recent_messages`：一条 30000 字的 **tool 消息**（`include_tool_results=True`）→ 同样有界
- [x] `GetSubagentRun`：30000 字 → 返回的 `summary` 有界，且 ref 可取全文
- [x] `RunPattern`：worker summary 有界
- [x] HTTP 路由：`content_limit` 大于生产者上限时 `content_truncated` 仍为 `True`（取或判别）
- [x] 假话：`result_ref is None` 时 `bounded_summary` **不含** result_ref 字样
- [x] 常量：`TRANSCRIPT_ITEM_LIMIT` / `TOOL_CALL_ARGUMENT_LIMIT` / `TRANSCRIPT_CONTENT_LIMIT`
      三处同值；把既有 `test_workflow_node_transcript.py` 的「两个 4000」断言升级为三处
- [x] **参数教训**：新测试的输入必须**真的**超过上限（用 30000，不用 5000），否则「返回 ≤4000」恒真
- [x] 变异验证：`_bounded_content` 改回 identity / 取或改成只看本层 / envelope 传回 full
      → 对应测试必须变红 → 还原后变绿
- [x] 回归：`tests/agent/subagent/`（重点 `test_result_representations.py`、`test_workflow_result_refs.py`）、
      `tests/web_tests/` 全量通过

## 文档

- [x] `diagnosis.md`：bugfix 门禁要求的 6 章
- [x] spec delta：`specs/subagents/spec.md`（MODIFIED「子 transcript inspect 默认受限」）+
      `specs/agent-runtime/spec.md`（MODIFIED「父 run 通过显式运行时接口管理子 session」）
- [ ] **当前规格同步**：把 delta 合入 `openspec/specs/`（受保护路径，需 `current_spec_synced` 事件）
- [x] `docs/agent-internals.md` 的 inspect 示例已过时（只列 3 键、无截断说明）→ 更新
- [x] 关键词扫描 `docs/`、`README.md`、`CONTEXT.md`、`docs/architecture.md` 中与子 agent 结果/
      transcript/bounded 相关的段落
- [ ] `docs/openspec-change-backlog.md` 登记本 change（需 `backlog_updated` 事件），完成后移除

## 审阅闭环

- [ ] Round 1 独立 subagent 审阅（`/review-loop`）
- [ ] 生成 review manifest 绑定 reviewer run / base·head sha / tasks·spec·diff·report hash

## 验证

- [x] 全量 pytest：**2989 passed / 9 skipped**，唯二失败是
      `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 的两条——**在 master（7c23059）上
      同样失败**，与本 change 无关（git-dir 探测，不碰本 change 的代码路径）
- [x] OpenSpec strict validate 通过（30/30）
- [x] OpenSpec artifact checker 通过
- [x] 端到端验收：30000 字 run 逐个走 4 个出口——envelope 4000 / full_summary=True 30000 /
      inspect content 4000+标志 / worker summary 4000；假话修复实测（无 ref 只说 truncated，有 ref 才提 result_ref）
- [x] **benchmark smoke**：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-213`
      跑通（fake agent 为回显 stub，验证 CLI/AgentLoop/subagent 路径端到端无崩溃，非回归信号）
