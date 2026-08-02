# Building Review: context-engineering-deepening（issue #74）

> 独立零记忆 subagent 审阅（不继承开发上下文）。审阅范围：`git diff origin/master...HEAD`（3 个提交 760d57c / b1515bf / 1ae4023）。

## Verdict

**CHANGES_REQUESTED** — 所有 `[x]` 任务均有真实实现且测试通过，但存在 2 个需修复的中等问题：

- **[M1]** Anthropic `stream_chat` 流式路径缺少 cache_control 400 重试降级（task 2.3 只实现了一半）。
- **[M2]** ReadDoc 32KB 上限按字符截断而非按字节，多字节（CJK）文档会突破字节上限。

其余为 Low 级观察项。无阻塞性缺陷。

---

## Tasks Verification

### 子 change ①：增量 token 计数 + 静态源缓存 + 四字段摘要 + pending 标记 + L1/L2 层级压缩

| Task | 实现位置 | 验证结论 |
|------|----------|----------|
| 1.1 增量 token 计数 `Message._tokens` | `agent/message.py:100`（非序列化字段）、`agent/memory/manager.py:124-138`（惰性缓存） | PASS。`to_dict` 不含 `_tokens`；测试 `test_second_count_is_all_cache_hits`/`test_newly_appended_message_counts_once`/`test_message_tokens_field_not_serialized` 覆盖 |
| 1.2 ContextBuilder 静态源缓存 | `agent/context/builder.py:41-45,66-70,75-89`、`agent/context/sources.py:110-112,268-270` | PASS。P0/P1 `static=True` 以 `(name,cwd,mode,user_system_prompt)` 键缓存；P2 `MemoryIndexSource` 无 `static` 属性 → 每轮重渲染，防 SaveMemory 陈旧。测试 `test_static_source_cached_across_builds`/`test_mode_change_invalidates_static_cache`/`test_non_static_source_never_cached` |
| 1.3 四字段摘要模板替换 | `agent/context/summarizer.py:74-107` | PASS。`_LLM_SUMMARY_USER_TEMPLATE` 四标题为 已完成事项/待办事项/疑难点与决策/当前进行中，旧标题已移除；`_LLM_SUMMARY_SYSTEM_PROMPT`/`_MERGE_SYSTEM_PROMPT` 同步加入成对保留指令。测试 `test_template_has_exactly_four_new_headings_in_order`/`test_merge_prompt_contains_four_new_headings` |
| 1.4 pending 标记绑定 tool_call_id | `agent/memory/manager.py:402-452`（`_annotate_pending_calls`） | PASS。格式 `[call#<i>: <tool_call_id> pending]`；预扫 middle+recent 的 tool 结果集合，无匹配则标注；LLM 与 Truncation 路径均可见（标注进 content）。测试 `test_pending_call_annotated_in_summarizer_input`/`test_completed_middle_chain_not_marked_pending`/`test_multiple_pending_calls_numbered_sequentially`/`test_pending_annotation_visible_to_truncation_summarizer` |
| 1.5 L1/L2 层级压缩 + tier 元数据 | `agent/memory/manager.py:34-47,96-102,266-294,398-430,455-470`（`SummaryTier`/`_l1_chunks`/`_compress_to_l2`）、`agent/context/summarizer.py:215-244`（`compress`） | PASS。L1 摘要累积，`len>=2 且 tokens>=l2_trigger` 触发 L2（复用 `_compress_to_l2`，LLM `compress()` 失败降级拼接）；tier/source_range/generated_at 元数据入 `_tiers`。测试 `test_l2_compression_triggered_and_metadata_recorded`/`test_no_l2_below_threshold` |
| 1.6 单元测试 | `tests/agent/context/test_summarizer.py`、`tests/agent/memory/test_memory.py`、`tests/agent/context/test_builder.py` | PASS。四字段模板、pending、增量计数、L1/L2、静态源缓存均有断言 |
| 1.7 resume pending 链 | `tests/agent/memory/test_memory.py::test_resume_roundtrip_keeps_pending_marker` | PASS（单元级 resume 往返：`to_dict/from_dict` 保留 tool_calls、`_tokens` 重置后重算、再压缩仍含 pending）。非完整 AgentLoop snapshot/resume e2e，但核心机制已覆盖 |

### 子 change ②：Prefix Cache 注入顺序

| Task | 实现位置 | 验证结论 |
|------|----------|----------|
| 2.1 build_blocks()/render_layers() 返回 list[TextBlock] | `agent/context/builder.py:77-126`、`agent/loop.py:1238-1252` | PASS。`build()` 保持 str；`build_blocks` 每层独立 TextBlock，`cacheable` 层标 `cache=True`；loop 注入为 system 消息块列表。测试 `test_build_blocks_returns_textblocks_with_cache_flags`/`test_build_still_returns_str` |
| 2.2 工具 schema 确定性排序 + set_stable_tools | `agent/loop.py:956-959`（`CORE_STABLE_TOOL_NAMES`）、`agent/tools/governance/selector.py:58-60,86-108`、`agent/tools/registry.py:95-119` | PASS。注册序稳定（dict 插入序）；selector 存在时 loop 以核心 7 工具集调用 `set_stable_tools`，stable 前置不占 top-k。测试 `test_set_stable_tools_wired_when_selector_present` |
| 2.3 cache_control 断点 + 400 重试降级 | `agent/llm.py:20-31`（CachePlan）、`agent/loop.py:1030-1086`（按模式单断点）、`agent/anthropic_llm.py:166-214`（断点放置+400降级） | **部分 PASS（含 M1）**。非流式 `chat` 路径断点与 400 降级正确；`stream_chat` 路径缺 400 降级（见 M1）。测试 `test_breakpoint_on_last_stable_system_block`/`test_breakpoint_on_last_core_tool`/`test_cache_control_400_retry` |
| 2.4 openai_llm.py 按 provider 对齐 | `agent/openai_llm.py`（无 `supports_cache_control`）、`agent/loop.py:1041`（能力门控） | PASS。loop 门控 `supports_cache_control`，OpenAILLM 无此属性 → 永不被设置 plan，payload 无 cache_control。测试 `test_openai_payload_never_has_cache_control` |
| 2.5 稳定前缀冻结 | `agent/context/builder.py:145-179`（`_find_trimmable_index` 跳过 cacheable） | PASS。cacheable（P0/P1/P2）不参与预算裁剪，整块保留；预算只作用于 P4/P5。测试 `test_cacheable_source_survives_budget_pressure` |
| 2.6 单元/集成测试 | `tests/agent/test_context_cache.py`（303 行） | PASS。注入顺序、cache 分层、稳定前缀冻结、Anthropic/OpenAI payload、CachePlan 消费、400 重试均覆盖 |

### 子 change ③：分页读进度 + 深层 MD 按需加载

| Task | 实现位置 | 验证结论 |
|------|----------|----------|
| 3.1 ReadTool offset/pagination 进度 | `agent/tools/builtin/read.py:58-105` | PASS。仅显式 offset 时输出 `\n\n[ReadProgress file="<path>"; offset=<n>; total=<m>]`；默认 path+limit 字节兼容（`test_limit_only_unchanged_no_note`）。offset 0-based、>total 空内容+注记、负 offset 归 0。测试 `test_offset_slices_and_notes_progress`/`test_offset_beyond_total_returns_empty_plus_note` 等 |
| 3.2 压缩前写入 (file,offset,total) | `agent/memory/manager.py:454-465`（`_extract_read_progress`）、`agent/memory/manager.py:468-489`（`_decorate_for_summary`） | PASS。`_READ_PROGRESS_RE` 扫 tool-result 取每文件最后一条进度，注入 summary prompt「当前进行中」区。测试 `test_read_progress_injected_into_summary_prompt` + `test_progress_note_format_matches_regex` |
| 3.3 深层 MD 按需加载 tool | `agent/tools/builtin/read_doc.py`（新增 81 行）、`agent/tools/factory.py:50-53,230-232,311-313` | PASS（含 M2）。`.md` only、workspace-policy 走 `assert_read_allowed`、`KNOWN_BUILTIN_TOOL_NAMES` 与两个工具工厂列表均注册 ReadDoc。测试 `test_reads_deep_md`/`test_rejects_non_md`/`test_path_traversal_blocked`/`test_registered_in_default_factory` 等 |
| 3.4 单元测试 | `tests/agent/tools/test_read_doc_and_pagination.py`（173 行） | PASS。分页进度、深层 MD、offset 边界、工厂注册/权限均覆盖 |

### 8. 收尾校验

| Task | 实现位置 | 验证结论 |
|------|----------|----------|
| 8.1 batch-grill-me 设计审阅 | `openspec/changes/context-engineering-deepening/reviews/design-grill.md` | PASS。2026-08-02，workflow run `wf_09df918b-aec`，verdict CHANGES_REQUESTED → 裁定已落入 design.md Decision 4 与 tasks |

---

## Issues

### M1 (Medium) — `stream_chat` 流式路径缺少 cache_control 400 重试降级

- **证据**: `agent/anthropic_llm.py:237-241`（`stream_chat` 异常处理器只做 vision 降级，`if not try_vision: raise`）；对比 `agent/anthropic_llm.py:73-96`（`chat` 非流式路径已实现 cache_control 400 降级）。
- **说明**: task 2.3 / design Decision 4 承诺「400 重试降级」，但只在非流式 `chat()` 实现。若 AnthropicLLM 启用流式（`BaseLLM.stream=True`，`agent/llm.py:78`），DeepSeek-anthropic 等拒绝 cache_control 的兼容端点会直接 400 失败。当前 loop 默认走非流式（`_should_stream_llm` 因 `stream=False` 返回 False，`agent/loop.py:1088-1094`），故为潜在缺陷而非当前主路径故障。
- **建议**: 在 `stream_chat` 的异常处理器中复用 `_payload_has_cache_control`/`_strip_cache_control`，400 且含 cache_control 时去掉断点重试一次。

### M2 (Medium) — ReadDoc 32KB 上限按字符截断，多字节文档突破字节上限

- **证据**: `agent/tools/builtin/read_doc.py:80` `content = content[:MAX_DOC_SIZE_BYTES]`（`MAX_DOC_SIZE_BYTES = 32*1024`，`read_doc.py:22`）。
- **说明**: 字节检查 `if size > MAX_DOC_SIZE_BYTES` 正确（`read_doc.py:68`），但截断按 Python 字符切片。对 CJK 等多字节 UTF-8 文档，返回内容字节数可达 32KB 的 2-3 倍（40KB 中文文件 → 返回约 98KB），与设计「32K 字节上限」契约（design-grill Q10、`MAX_ASTER_SIZE_BYTES` 字节模式，`sources.py:121`）不符。本项目文档为中文，命中概率高。
- **建议**: 按字节截断（如 `content.encode("utf-8")[:MAX_DOC_SIZE_BYTES].decode("utf-8", errors="ignore")`），或复用 `MAX_ASTER_SIZE_BYTES` 的字节累计模式。

### L3 (Low) — tasks.md 4.1 已实现但未勾选

- **证据**: `openspec/changes/context-engineering-deepening/tasks.md:33` 仍为 `[ ] 4.1`；但实现已合入 `agent/loop.py:896-916`（memory_compaction 事件带 before/after tokens+tiers）与 `agent/trace_recorder.py:154-168`（`record_compaction`），且有测试 `tests/agent/test_loop.py::test_memory_compaction_event_carries_token_and_tier_stats`/`test_memory_compaction_recorded_to_trace`。
- **说明**: 收尾阶段勾选与代码不同步。4.2/4.3/4.4、8.2/8.3 未勾选属预期（closing 阶段工作），但 4.1 的实现已完成应勾选。

### L4 (Low) — L2 累积 token 每次 compact 重算

- **证据**: `agent/memory/manager.py:278` `accumulated = sum(_count_tokens(chunk) for chunk in self._l1_chunks)`。
- **说明**: 每次 compact 对全部累积 L1 块重新 tiktoken 编码，超长会话下为 O(累积 L1 内容) 开销，未复用增量计数。非正确性问题，纯性能观察项。

### L5 (Low) — 断点定位假设系统块数组以稳定块开头

- **证据**: `agent/loop.py:1063-1068` 按 cache 块计数，`agent/anthropic_llm.py:184` 按位置索引 `min(stable_system_block_count, len(system))-1`。
- **说明**: 若消息链中存在非 cache 的 system 消息先于注入上下文块，断点会落在 P1 而非 P2（缓存覆盖少一块）。当前 loop 流程唯一 system 消息即注入块（`agent/loop.py:1247`），resume 恢复时过滤掉 system（`agent/loop.py:531`），实际不可达。防御性说明。

---

## Test Results

指定 4 个文件（本地 `/home/happy/.local/bin` PATH）：

```
$ uv run pytest tests/agent/test_context_cache.py tests/agent/tools/test_read_doc_and_pagination.py tests/agent/memory/test_memory.py tests/agent/context/test_summarizer.py -q
93 passed in 3.44s
```

补充回归（touch 到的测试）：

```
$ uv run pytest tests/agent/test_loop.py tests/agent/context/test_builder.py tests/agent/tools/test_plan_mode_tools.py tests/agent/context/test_sources.py -q
101 passed in 10.54s

$ uv run pytest tests/benchmark/test_asterwynd_runner.py tests/web_tests/test_server.py -q
39 passed in 6.57s
```

全量 agent 测试（排除已知环境性 docker 失败）：

```
$ uv run pytest tests/agent -q --ignore=tests/agent/code_intelligence --ignore=tests/agent/tools/test_sandbox_backends.py
1121 passed in 170.18s
```

门禁：

```
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 32 passed, 0 failed
```

CI 配置无改动（`.github/workflows/ci.yml` 未出现在 diff 中），未弱化。

---

## 结论

实现质量高：所有 `[x]` 任务均有真实代码与测试支撑，核心承诺（四字段摘要、pending 标记、L1/L2 压缩、增量 token 计数、Prefix Cache 注入顺序+断点、ReadDoc 按需加载、压缩事件入 trace）全部落地，93+101+39 及全量 agent 测试（1121）通过，artifact checker 与 OpenSpec validate 通过。

需在合入前修复 2 个中等问题：
1. **M1** `stream_chat` 补 cache_control 400 降级（~5 行）。
2. **M2** ReadDoc 截断改按字节（~3 行）。

修复后建议重跑 `tests/agent/test_context_cache.py tests/agent/tools/test_read_doc_and_pagination.py` 及对应新增回归测试。
