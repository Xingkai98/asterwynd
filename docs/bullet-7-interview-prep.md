# Bullet 7 面试讲稿：全链路可观测体系与 Benchmark

> 建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；36+ 个 coding 任务（26 本地 + 10 SWE-bench 外部）在 git worktree 隔离执行，bootstrap 95% CI 统计，支持 SWE-bench 跨 Agent 对比和 CI 回归门禁

---

## 主讲述稿（~450 字）

可观测体系和 Benchmark 评测闭环是我认为做 Agent 框架必须有的东西——没有数据，所有优化都是拍脑袋。

可观测侧有三个组件。TraceRecorder 是全链轨迹记录器，定义了 18 种事件类型——run 开始、LLM 调用、工具调用和结果、沙箱事件、审批请求和响应、文件编辑、内存压缩等。每个事件携带时间戳和结构化 data，最终序列化为 JSON 写入文件。我特别关注了 benchmark 场景——runner 为每个 task 创建独立 TraceRecorder 实例，注入 task_id，基准测试结果可以逐 task 追溯。

CostLedger 是成本归因系统，bill 方法返回三层聚合——by_session 按会话、by_phase 按运行阶段（building/review/planning/bypass）、by_tool 按工具。硬编码了 8 个主流模型的价格表，按前缀匹配计算成本。Ledger 通过 JSONL 持久化，支持增量 flush。三层归因的价值在于——你可以回答"review 阶段的成本占比是多少"、"哪个工具消耗了最多的 token"。

ErrorClassifier 是错误自动打标，5 大类：PERMISSION_DENIED、NETWORK_TIMEOUT、MODEL_ERROR、PARAMETER_ERROR、UNKNOWN。三级优先级分类——结构化 error_type 最优先（17 条映射），finish_reason 次之，文本正则 fallback 兜底。我用的是确定性规则而非 LLM 分类，保证打标的稳定性和零成本。

Benchmark 评测侧，36 加个 coding 任务——26 个本地任务覆盖 asterwynd 自身各模块（从 tool registry 到 subagent manager 到 LSP），10 个 SWE-bench Verified 任务覆盖 requests/flask/pytest 外部仓库。本地任务通过 git worktree 隔离执行，task 文件隐藏防止作弊。SWE-bench 通过 SwebenchAdapter 调用官方 Docker 验证器。统计用 bootstrap 百分位法——2000 次重采样、固定种子可复现、95% 置信区间。CI 回归门禁检查 success_rate 绝对下降不超过 5pp 和 p95 延迟回归不超过 5%。跨 Agent 对比工具支持多 run 横向对比——任务级表格、延迟分位、成本估算。

---

## 追问 1：为什么不直接用 Langfuse / OpenTelemetry 而是自己实现？

**回答（~250 字）：**

三个原因。第一是零外部依赖——Asterwynd 的定位是 pip install 即可用，不要求用户部署一个 Langfuse 服务器或配置 OpenTelemetry collector。对于一个单机开发工具来说，依赖外部可观测平台是过重的。

第二是结构化深于通用框架——我的事件类型不是泛化的"LLM call + metadata"，而是精确到"并行工具执行开始""压缩前后 token 变化""审批被拒"。这些事件的 schema 和 AgentLoop 的内部状态紧密耦合。可以类比——Langfuse 给你的是"HTTP request trace"，我给你的是"函数级 execution trace"。

第三是 benchmark 集成——TraceRecorder 的 task_id 注入、runner 的 diff snapshot、测试执行记录，这些都是 benchmark 评测闭环的一部分，不是独立的可观测。把 trace 和 benchmark 产出放在同一个 task 目录下（trace.json 和 result.json），后续分析不需要跨系统关联。

如果未来需要对接企业级可观测平台，TraceRecorder 的 to_dict 输出可以直接适配 OpenTelemetry span exporter。

---

## 追问 2：CostLedger 的价格表硬编码了，模型更新或降价了怎么办？

**回答（~150 字）：**

承认——当前 MODEL_PRICES 是硬编码常量，模型更新需要改源码。这是有意为之的简单设计——8 个模型的定价表维护成本极低，而且定价不是实时变化的数据。GPT-5 的价格几个月才变一次。

如果要做成运行时可配置的，方案很简单——把 MODEL_PRICES 从代码常量改为配置文件或环境变量加载。但因为价格更新频率极低（一年几次），动态加载的复杂度增加（需要处理配置缺失、格式错误、恶意注入）超过收益。

更重要的设计是 CostLedger 和 TraceRecorder 解耦——即便定价表过期，token 消耗数据仍然准确，只是换算成美元的部分需要手动修正。token 数据是永久正确的。

---

## 追问 3：26 个本地任务怎么设计出来的？覆盖了什么？

**回答（~200 字）：**

26 个本地任务的设计原则是"每个模块至少一个任务，每个任务有可自动验证的正确性标准"。覆盖了 tool registry（读写工具、注册去重）、sandbox executor、agent loop trace、benchmark CLI、Bash workspace 边界、memory manager 的 CRUD、skill loader、parent channel 通信、subagent manager 的 create/run/resume、SSE streaming、hook manager 注册和分发、retry/budget 逻辑、LSP diagnostics 等。

每个任务有一个 task.json 定义验证命令（通常是 pytest），runner 执行 agent 后跑测试。关键设计是 task 文件在 agent 执行前被移动到 .hidden 目录——这防止 agent 读取测试文件来"作弊"（比如看到需要实现什么函数）。worktree 隔离保证任务间的文件变更不互相污染。

设计缺陷会坦白说——26 个任务的覆盖偏向"模块功能测试"而非"端到端用户意图测试"。用户说"帮我写一个 REST API"这种真实场景还没有对应的 benchmark task。

---

## 追问 4：Gate 的门禁指标为什么是 5pp success_rate 和 5% p95？不是更严？

**回答（~200 字）：**

5pp 和 5% 是 CI 门禁的"防退步底线"，不是"质量目标"。门禁要做的是拦截显著的回归——改一行代码导致 10% 的任务失败，那就肯定有问题。但如果严格要求 success_rate 不下降，会导致两个问题：第一是假阳性——模型 API 本身有非确定性，同一任务同一配置跑两次结果可能略有不同，严格不下降会导致 CI 频繁误报；第二是抑制改进——有些重构可能稍微降低某个边缘 case 的通过率但整体架构改善很多，5pp 的门槛允许合理权衡。

p95 延迟还有特殊处理——当 baseline p95 < 1s 时，用绝对 floor 1s 代替相对 fraction。因为 sub-second 任务的相对波动（0.3s→0.4s 就是 33%）没有实际意义，可能是随机噪声。abs_p95_floor 解决了这个"sub-second baseline 不适用相对比较"的计量问题。

---

## 追问 5：Benchmark 结果怎么跟其他 Agent 对比？

**回答（~150 字）：**

compare.py 是一个独立的 CLI 工具，支持多 run 目录横向对比。输入是多个 `--runs-dir` 路径（可以是不同 agent 的产出），输出 Markdown 和 HTML 对比报告。

对比维度包括：逐任务按 agent 的 status 表格（passed/failed/error/unsupported）、每个 agent 的 summary 分布、p50/p95/p99/max 延迟分位、Input/Output Tokens 和估算成本。报告产物写回 `benchmarks/reports/comparison.*`。

SWE-bench 任务使用官方验证器（swebench.harness.run_evaluation）以确保对比的公平性——所有 agent 跑同一套 Docker test harness，pass/fail 判定标准一致。如果跑的是非 SWE-bench 的本地任务，则 check 各自的 test.patch 断言文件。

目前的局限是仅支持文件级 run 目录对比，没有 Web dashboard。这适合 CI 集成和本地对比，不适合对外公开展示——这也是后续可以做的一个方向。
