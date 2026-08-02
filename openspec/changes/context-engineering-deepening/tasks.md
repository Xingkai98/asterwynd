# Tasks: 上下文工程做深

## 子 change ①：增量 token 计数 + 缓存 + 四字段摘要 + pending 标记

- [ ] 1.1 增量 token 计数（避免每次迭代 O(N) 重算全部消息 token）
- [ ] 1.2 ContextBuilder 静态源缓存（避免每轮重建）
- [ ] 1.3 四字段摘要模板替换（已完成/待办/疑难点与决策/当前进行中）
- [ ] 1.4 tool_call/tool_result 成对保留 + `[call#n pending]` 标记（中间段摘要后未完成调用）
- [ ] 1.5 单元测试：四字段摘要、pending 标记、增量计数

## 子 change ②：Prefix Cache 注入顺序

- [ ] 2.1 注入顺序 system → MD → 工具 → 记忆索引 → 用户消息
- [ ] 2.2 工具 schema 确定性排序
- [ ] 2.3 anthropic_llm.py 加 cache_control（ephemeral）断点
- [ ] 2.4 openai_llm.py 按 provider 对齐
- [ ] 2.5 与 #77 约定「稳定层/可变层」分层策略
- [ ] 2.6 单元/集成测试：注入顺序、cache 分层

## 子 change ③：分页读进度 + 深层 MD 按需加载

- [ ] 3.1 ReadTool 增加 offset/pagination/(file,offset,total) 进度
- [ ] 3.2 压缩前把 (file,offset,total) 写入摘要
- [ ] 3.3 深层 MD 按需加载 tool（根 MD 注入，深层 tool 化）
- [ ] 3.4 单元测试：分页进度、深层 MD 加载

## 收尾

- [ ] 4.1 压缩/缓存命中事件入 trace（与 #78 对齐）
- [ ] 4.2 OpenSpec spec 同步
- [ ] 4.3 全量 pytest + openspec validate + artifact checker
- [ ] 4.4 benchmark 量化（压缩比 90%→20-30%、cache 命中率、工具链成对率）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
