# Proposal: 上下文工程做深 — 结构化摘要 + 层级压缩 + Prefix Cache 优化

## Change Type

primary: feature
secondary:
  - agent-runtime
  - memory

## 需求

1. 四字段结构化摘要：已完成事项 / 待办事项 / 疑难点与决策 / 当前进行中
2. tool_call/tool_result 成对保留，未完成标记 `[call#n pending]`
3. 层级压缩：一级摘要 → 累积超标 → 二级压缩（只保留最高层结论）
4. 分页大文件进度保留：压缩前把 `(file, offset, total)` 写入摘要
5. Prefix Cache 注入顺序：system prompt → MD → 工具描述 → 记忆索引 → 用户消息
6. 深层 MD 按需加载 tool（根 MD 注入，深层 MD 做成 tool 按需读取）

## 背景

当前上下文管线已有 ContextBuilder（P0-P6 注入）+ MemoryManager（90% 阈值 AutoCompact）+ LLMSummarizer（四段式），但：

- 摘要字段是"已完成/关键决策/进行中/阻塞与待办"，缺"疑难点"维度，"待办/阻塞"未拆开。
- tool_call 成对保留只在最近窗口，中间段摘要后未完成调用无 `[call#n pending]` 标记。
- 只有单层 running summary，无层级压缩。
- ReadTool 只有 path+limit，无 offset/进度续读。
- 所有层拼一个 system 消息，无 cache_control 断点；工具 schema 按注册序全量注入。
- 深层 MD 只在 git root→CWD 链上收集，无按需加载 tool。

面试表现："阈值触发 + LLM 做摘要"即被判定停留在原型阶段。光帆 Q15 标准答案给出四维度摘要结构。

## 非目标

- 不重做 ContextBuilder 架构（P0-P6 优先级模型已存在，本 change 在其上扩展）。
- 不改动单次运行语义与 artifact 结构（向后兼容）。
- 不实现 P3 自动召回 / P6 对话历史（属后续项）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/context/summarizer.py` | 四字段模板 + pending 标记 + L2 压缩入口 |
| `agent/memory/manager.py` | L1/L2 层级摘要状态 + 未完成 tool call 追踪 |
| `agent/context/builder.py` | cache 感知分层/输出 build report |
| `agent/context/sources.py` | source 排序与断点 |
| `agent/tools/builtin/read.py` | offset/pagination/(file,offset,total) 进度 |
| `agent/tools/registry.py` | 工具描述确定性排序 |
| `agent/anthropic_llm.py` | system/tools 分块 + cache_control 断点 |
| `agent/openai_llm.py` | 按 provider 对齐 |
| `agent/loop.py` | 注入顺序、resume 时 pending 链、压缩触发 |
| `agent/trace_recorder.py` | 压缩层级/缓存命中事件 |
| `benchmarks/` | 压缩率/token 节省量化（复用 PR #80 statistics） |

## Reference Implementation Research

- status: enabled
- reason: 上下文工程（结构化摘要、层级压缩、Prefix Cache、按需加载）是 Claude Code（Dream 机制、占位符）、MemGPT 等成熟系统的核心能力，应参考其实现。
- research questions:
  - Claude Code 的四字段摘要结构与层级压缩触发条件？
  - Prefix Cache（Anthropic cache_control）注入顺序与断点策略？
  - 分页读大文件的进度保留实现？
- findings:
  - 待 planning 阶段补充（本 proposal 阶段完成 status/reason/questions 登记；实质调研在本 change planning 阶段完成）。
- design impact:
  - 待 planning 阶段补充；先决条件：与 #77 约定工具注入缝「稳定层/可变层」分层策略（Prefix Cache 与动态 Top-K 的张力）。

## Dependencies

- 依赖 PR #80（已合入）：压缩率/token 节省量化复用 statistics。
- 依赖 #77 工具治理的注入契约（Prefix Cache 稳定层/可变层分层）。
- 与 #75 长期记忆共享 memory 子系统。

## 验收

- 压缩前后对比能证明 token 节省和关键状态保留，同时不破坏 tool-call 链。
- 面试可引用压缩比（90% 阈值 → 20-30%）、cache 命中率/首 token 延迟、工具链成对率。
