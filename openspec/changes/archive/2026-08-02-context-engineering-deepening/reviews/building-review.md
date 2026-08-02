# Building Review: context-engineering-deepening（issue #74）

> 独立零记忆 subagent 审阅（不继承开发上下文）。审阅范围：`git diff origin/master...HEAD`（4 个提交 760d57c / b1515bf / 1ae4023 / baa510d）。
> Round 1（CHANGES_REQUESTED）后主 agent 已修复全部 5 个 finding（fix commit `baa510d`）。本报告为 Round 2 复审，逐一验证修复是否到位。

## Verdict

**PASS** — Round 1 的 5 个 finding（M1 / M2 / L3 / L4 / L5）全部修复到位，均有真实代码实现与回归测试支撑；Round 2 指定测试全部通过。修复未引入新的阻塞性问题。

Round 1 verdict：**CHANGES_REQUESTED**（2 个 Medium + 3 个 Low），详见下方「Round 1 修复验证」逐条记录。

---

## Round 1 修复验证（逐条）

### M1 (Medium) — `stream_chat` 流式路径补 cache_control 400 重试降级 → 已修复

- **验证结论**: PASS
- **代码**: `agent/anthropic_llm.py:239-261`。`stream_chat` 异常处理器：`_is_400_error` 过滤后，读取 `_last_cache_plan`（`anthropic_llm.py:247`），`had_cache` 判定为 plan 任一 count > 0（`:248-251`）；命中则重试一次 `_stream_chat_impl`（`:254-260`）。`_apply_cache_plan` 在 `_build_payload` 中 read-and-clear `cache_plan` 并保存 `_last_cache_plan`（`:177-179`），因此重试时 `cache_plan is None` → `_apply_cache_plan` 直接 return，重试 payload **不重建 plan、不误消费、天然无 cache_control**。降级判断基于已保存的 plan，不重建 payload。
- **回归测试**: `tests/agent/test_context_cache.py:241-294` `test_stream_cache_control_400_retry`。fake `client.stream` 首次抛 HTTP 400，二次成功返回 SSE；断言 `attempts["n"] == 2` 且产出 `complete` 事件。真实驱动流式降级路径（非 `chat()` 非流式）。

### M2 (Medium) — ReadDoc 32KB 上限按字节截断 → 已修复

- **验证结论**: PASS
- **代码**: `agent/tools/builtin/read_doc.py:79-84`。`content.encode("utf-8")[:MAX_DOC_SIZE_BYTES].decode("utf-8", errors="replace")`，CJK 多字节不会突破 32KB 字节上限；截断后追加截断注记。
- **回归测试**: `tests/agent/tools/test_read_doc_and_pagination.py:130-140` `test_size_cap_is_byte_based_for_multibyte`。写入 `"中"*(32KB/3+500)`（约 34KB 字节、1.1 万字符），断言 `len(result.encode("utf-8")) <= MAX_DOC_SIZE_BYTES + 200`。

### L3 (Low) — tasks.md 4.1 勾选与实现同步 → 已修复

- **验证结论**: PASS
- **代码**: `openspec/changes/context-engineering-deepening/tasks.md:33` 已为 `[x] 4.1`；实现真实存在：`agent/loop.py:896-916`（compaction 后 `on_event("memory_compaction", {...})` 携带 before/after tokens + `tier_metadata()`，并调 `trace_recorder.record_compaction`）、`agent/trace_recorder.py:154-170`（`record_compaction`）。
- **测试**: `tests/agent/test_loop.py:1026` `test_memory_compaction_event_carries_token_and_tier_stats`、`:1057` `test_memory_compaction_recorded_to_trace`，均通过（`-k compaction` 4 passed）。

### L4 (Low) — L2 累积 token 每次 compact 重算 → 已修复

- **验证结论**: PASS
- **代码**: `agent/memory/manager.py`。新增 `_l1_accumulated_tokens` 增量累加器（`:99` 初始化），`compact()` 每次追加新 L1 summary 时 `+= _count_tokens(new_summary)`（`:280`），触发判断与 L2 budget 改用累加值（`:281,:286`），L2 压缩后清零（`:296`）；`clear()` 同步重置（`:543`）。与旧 `sum(_count_tokens(chunk) for chunk in self._l1_chunks)` 数学等价（chunk 即各次 `new_summary`），无累积漂移。

### L5 (Low) — 断点定位假设系统块数组以稳定块开头 → 已修复

- **验证结论**: PASS
- **代码**: `agent/loop.py:1063-1077`。`_compute_cache_plan` 不再按 cache 块计数，改为遍历所有 system 消息、以**全局 block index** 记录最后一个 `TextBlock.cache` 块的 `block_index + 1`；前置非 cache system 消息（plain-string 也计 1 块，`:1077`）不再导致错位。selector OFF 返回 `stable_system_block_count=stable_system_breakpoint`（`:1079-1084`）。
- **回归测试**: `tests/agent/test_context_cache.py:332-345` `test_compute_cache_plan_with_preceding_system_block`。消息链为「plain-string system 块 + 3 个 cache TextBlock」，断言 `stable_system_block_count == 4`（最后 cache 块全局 index 3 + 1）。该断言对旧实现（计数 3）会失败，真实覆盖修复。

---

## Tasks Verification

Round 1 已验证的 tasks 结论全部保留有效（见 git 历史 Round 1 报告版本）；Round 2 复审确认无回退：

| Task | 结论 | 备注 |
|------|------|------|
| 子 change ①（1.1-1.7）增量计数/静态缓存/四字段摘要/pending/L1/L2/resume | PASS | 原结论保持 |
| 子 change ②（2.1-2.6）注入顺序/稳定工具/cache_control 断点/OpenAI 对齐/稳定前缀冻结 | PASS | M1 修复后 2.3 全量成立；新增流式 400 降级测试 |
| 子 change ③（3.1-3.4）分页进度/深层 MD | PASS | M2 修复后 3.3 全量成立；新增 CJK 字节上限测试 |
| 4.1 压缩/缓存事件入 trace | PASS | L3 勾选同步；loop + trace_recorder 实现及测试均存在 |
| 4.2/4.3/4.4、8.2/8.3 | — | closing 阶段工作，未勾选属预期 |

---

## New Issues

Round 2 复审未发现修复引入的新缺陷。以下为观察项（非阻塞）：

- **O1（观察）**: M2 修复后返回串字节数为「32KB 内容 + 截断注记（约 60 字节）」，严格上略超 32KB；这是设计注记的刻意附加，测试容差 `+200` 覆盖，符合「文档内容 32KB 上限」契约，无需改动。
- **O2（过程）**: `scripts/check_openspec_artifacts.py` 当前报 `building-review-manifest.json` 缺失——因为 Round 1 为 CHANGES_REQUESTED 从未生成 manifest。本报告 PASS 后，review-loop 收尾需生成 manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）方可过门禁。属流程项，非代码缺陷。

---

## Test Results

Round 2 指定测试（本仓库 `/home/happy/.local/bin` PATH）：

```
$ uv run pytest tests/agent/test_context_cache.py tests/agent/tools/test_read_doc_and_pagination.py tests/agent/memory/test_memory.py -q
61 passed in 6.71s
```

补充回归（修复触及文件对应的测试面）：

```
$ uv run pytest tests/agent/test_loop.py tests/agent/context/test_builder.py tests/agent/context/test_summarizer.py -q
113 passed in 10.22s

$ uv run pytest tests/agent/test_llm.py tests/agent/tools/test_plan_mode_tools.py tests/agent/context/test_sources.py -q
26 passed in 2.04s

$ uv run pytest tests/agent/test_anthropic_llm.py tests/agent/test_openai_llm.py tests/support/test_llm_harness.py -q
31 passed in 1.76s

$ uv run pytest tests/agent/test_loop.py -q
62 passed in 10.36s
```

定向验证：`test_loop.py -k compaction` 4 passed（L3 两个事件测试在内）。

门禁：OpenSpec validate 与全量 agent 测试已在 Round 1 跑通（1121 passed）；Round 2 修复只改 4 个源文件 + 3 个测试文件，未触碰 CI 配置。artifact checker 仅剩 manifest（见 New Issues O2），PASS 后由 review-loop 收尾补齐。

---

## 结论

Round 1 的 5 个 finding 全部修复并验证通过：M1 流式 400 降级（`_last_cache_plan` 检测 + 重试不误消费 plan）、M2 字节截断、L3 勾选同步、L4 增量累加器、L5 全局 index 断点，均有实现 + 回归测试支撑。无新增缺陷。**Verdict: PASS。**
