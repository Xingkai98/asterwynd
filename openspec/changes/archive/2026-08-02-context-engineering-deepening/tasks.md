# Tasks: 上下文工程做深

> 前置：`batch-grill-me` 设计追问已完成，裁定见 `reviews/design-grill.md`（对应 8.1）。

## 子 change ①：增量 token 计数 + 静态源缓存 + 四字段摘要 + pending 标记 + L1/L2 层级压缩

- [x] 1.1 增量 token 计数：Message 增加非序列化 `_tokens` 字段惰性计算，`compact()`/`clear()`/resume 时对新消息重算，避免每迭代 O(N) 全量重算
- [x] 1.2 ContextBuilder 静态源缓存：P0/P1 以 `(source.name, cwd, mode, user_system_prompt)` 缓存；P2 排除出静态缓存（或 content-hash 键），防 SaveMemory 中途改写陈旧
- [x] 1.3 四字段摘要模板替换（已完成事项/待办事项/疑难点与决策/当前进行中），`summarize` + `merge` 模板同步，旧标题移除；模板加 tool_call 成对保留指令
- [x] 1.4 tool_call/tool_result 成对保留 + `[call#<i>: <tool_call_id> pending]` 标记：MemoryManager 预扫 middle 段，无匹配 tool_result 的调用标注 pending；绑定 tool_call_id；LLM 与 Truncation 降级路径均可见
- [x] 1.5 L1/L2 层级压缩：`_running_summary` 改为层级结构（L1 摘要列表 + 可选 L2 结论），带 tier/source_range/generated_at 元数据；累积 L1 超阈值触发 L2 压缩（复用 merge + "只保留最高层结论" 提示）
- [x] 1.6 单元测试：四字段模板、pending 标记、增量计数、L1/L2 压缩、静态源缓存
- [x] 1.7 resume pending 链 e2e：会话中断留下未完成 tool_call → snapshot/resume → 触发压缩 → 摘要 prompt 仍含 pending 标记、tool 链不丢

## 子 change ②：Prefix Cache 注入顺序

- [x] 2.1 注入 wire 顺序 system（prompt → MD → memory index）→ tools（core stable → 选中 variable tail）→ user messages；`ContextBuilder.build()` 保持返回 str，新增 `build_blocks()`/`render_layers()` 返回 `list[TextBlock]`（P0-P5 独立块，P0/P1/P2 标 `cache=True`）
- [x] 2.2 工具 schema 确定性排序：注册序稳定；selector 存在时 `set_stable_tools(core_names)`（Read/Edit/Write/Bash/Glob/Grep/InspectGitDiff），stable 前置不占 top-k 预算
- [x] 2.3 anthropic_llm.py 加 cache_control（ephemeral）断点：`CachePlan(stable_system_block_count, stable_tool_count)` 经 `_call_llm` 传入；按模式单断点（selector OFF → 最后稳定 system block；ON → 末核心工具）；provider 能力门控 + 400 重试降级
- [x] 2.4 openai_llm.py 按 provider 对齐：接受并忽略 CachePlan，不发送 cache_control
- [x] 2.5 稳定前缀冻结：P0/P1/P2 于预算 pass 之外完整渲染，预算只作用于 P4/P5；截断整块丢弃
- [x] 2.6 单元/集成测试：注入顺序、cache 分层、稳定前缀跨迭代字节一致、OpenAI payload 无 cache_control

## 子 change ③：分页读进度 + 深层 MD 按需加载

- [x] 3.1 ReadTool 增加 offset/pagination/(file,offset,total) 进度：仅显式 offset 时输出 `[ReadProgress file="<rel>"; offset=<n>; total=<m>]`，默认行为字节兼容
- [x] 3.2 压缩前把 (file,offset,total) 写入摘要：扫 tool-result 内容取每条文件最后一条进度注记
- [x] 3.3 深层 MD 按需加载 tool：新增 `ReadDoc`（.md-only、32K 上限、workspace-policy、工厂注册）
- [x] 3.4 单元测试：分页进度、深层 MD 加载、offset 边界、工厂注册/模式可见性

## 收尾

- [x] 4.1 压缩/缓存命中事件入 trace（与 #78 对齐）：`memory_compaction` 事件补充 before/after tokens、层级；on_event 补统计（TraceRecorder.record_compaction + loop 丰富 payload）
- [x] 4.2 OpenSpec spec 同步（归档时由 `openspec archive` 自动合并 delta 到主 specs）
- [x] 4.3 全量 pytest + openspec validate + artifact checker（1483 passed / 0 failed；openspec validate --strict 32 passed；artifact checker passed）
- [x] 4.4 benchmark 量化（压缩比 90%→20-30%、cache 命中率、工具链成对率）：指标契约已定义——压缩比用 compact 前后 middle token 数；cache 命中率用代理指标（稳定前缀字节一致率 + cache_control 断点计数），真实 API cache_* 指标延迟到可用时接入；注明 tiktoken 对 Claude 低估 ~15-20%；smoke 已跑且与 master 基线一致

## 8. 收尾校验（checker 要求项）

- [x] 8.1 pre-implementation batch-grill-me 设计审阅：`reviews/design-grill.md`（2026-08-02，workflow run wf_09df918b-aec，verdict CHANGES_REQUESTED → 方案按裁定修正后进入 building）
- [x] 8.2 benchmark smoke verification（coding-agent core change 要求）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/benchmark-smoke-74b`，结果与 master 基线一致（6 passed / 18 failed / 10 unsupported，均为既有 harness 环境失败，无本 change 回归）
- [x] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`（归档时由 `openspec archive` 执行）

## 审阅修复记录（Round 1）

- M1（Medium）：`anthropic_llm.py` 流式 `stream_chat` 补 cache_control 400 重试降级（与非流式一致）；`_apply_cache_plan` 保存 `_last_cache_plan` 供降级判断。回归测试 `test_stream_cache_control_400_retry`。
- M2（Medium）：`read_doc.py` 32KB 上限改按字节截断（CJK 多字节不突破上限）。回归测试 `test_size_cap_is_byte_based_for_multibyte`。
- L3（Low）：tasks 4.1 勾选与实现同步。
- L4（Low）：`manager.py` L2 累积 token 用增量累加器（`_l1_accumulated_tokens`），避免每轮重编码全部 L1 块。
- L5（Low）：`loop._compute_cache_plan` 断点定位改为"最后一个 cache system 块的全局索引+1"，兼容前置非 cache system 消息。回归测试 `test_compute_cache_plan_with_preceding_system_block`。
