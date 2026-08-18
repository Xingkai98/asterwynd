# Bullet 7 面试讲稿：全链路可观测体系与 Benchmark

> 建立全链路可观测体系与 Benchmark 评测闭环：TraceRecorder 全链轨迹记录 + CostLedger 三层成本归因 + ErrorClassifier 错误类型自动打标；72 个 coding 任务（34 本地 = 22 A 轨回归基线 + 12 B 轨当前演进 + 38 SWE-bench Verified 子集）在 git worktree / Docker 隔离执行，pass@1/pass^k/成本（cache-aware）与 fault_owner 归因统计，场景×难度分层覆盖矩阵，支持跨 Agent 配对比较与 CI 回归门禁

---

## 主讲述稿（~450 字）

可观测体系和 Benchmark 评测闭环是我认为做 Agent 框架必须有的东西——没有数据，所有优化都是拍脑袋。

可观测侧有三个组件。TraceRecorder 是全链轨迹记录器，定义了 18 种事件类型——run 开始、LLM 调用、工具调用和结果、沙箱事件、审批请求和响应、文件编辑、内存压缩等。每个事件携带时间戳和结构化 data，最终序列化为 JSON 写入文件。我特别关注了 benchmark 场景——runner 为每个 task 创建独立 TraceRecorder 实例，注入 task_id，基准测试结果可以逐 task 追溯。

CostLedger 是成本归因系统，bill 方法返回三层聚合——by_session 按会话、by_phase 按运行阶段（building/review/planning/bypass）、by_tool 按工具。定价表是 cache-aware 四档（fresh input / cache read / cache write / output），按前缀匹配计算成本，覆盖 17 个主流模型。Ledger 通过 JSONL 持久化，支持增量 flush。三层归因的价值在于——你可以回答"review 阶段的成本占比是多少"、"哪个工具消耗了最多的 token"。

ErrorClassifier 是错误自动打标，5 大类：PERMISSION_DENIED、NETWORK_TIMEOUT、MODEL_ERROR、PARAMETER_ERROR、UNKNOWN。三级优先级分类——结构化 error_type 最优先（17 条映射），finish_reason 次之，文本正则 fallback 兜底。我用的是确定性规则而非 LLM 分类，保证打标的稳定性和零成本。

Benchmark 评测侧，72 个 coding 任务——34 个本地任务分双轨（22 个 A 轨历史重建回归基线 + 12 个 B 轨当前演进），38 个 SWE-bench Verified 子集覆盖 requests/flask/pytest/sympy/seaborn/pylint 外部仓库。本地任务通过 git worktree 隔离执行，task 文件隐藏防止作弊；SWE-bench 通过 SwebenchAdapter 调用官方 Docker 验证器。指标分三层：pass@1 是用户实际获得的有效轮通过率，pass@k 是能力上限，pass^k 是全部有效轮成功的可靠性；成本用 cache-aware 定价算 $/resolved-task，失败轮次用 reason × fault_owner 交叉表归因。任务按 scenario × difficulty 双标签分层，套件级能力覆盖矩阵机械校验；跨 Agent 对比用配对统计（per-task delta + 差异 CI + win-rate）。CI 回归门禁检查 success_rate 绝对下降不超过 5pp 和 p95 延迟回归不超过 5%。

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

承认——当前 MODEL_PRICES 是硬编码常量，模型更新需要改源码。这是有意为之的简单设计——17 个模型的四档定价表维护成本极低，而且定价不是实时变化的数据。价格变动一年几次，动态加载（配置缺失、格式错误、恶意注入）的复杂度超过收益。

评测升级后定价表变成 cache-aware 四档（fresh / cache read / cache write / output），并带 `PRICING_TABLE_VERSION` 版本号写进报告元组——即便价格调整，报告仍能追溯到用的是哪一版定价口径。这比"过期定价"更致命的是"不知道用的是哪版定价"。

更重要的设计是 CostLedger 和 TraceRecorder 解耦——即便定价表过期，token 消耗数据仍然准确，只是换算成美元的部分需要手动修正。token 数据是永久正确的。

---

## 追问 3：34 个本地任务怎么设计出来的？A 轨和 B 轨怎么分工？

**回答（~250 字）：**

34 个本地任务分双轨。**A 轨是历史重建回归基线（22 个）**——从本仓库 2026-06 前合入特性的 git 历史重建，任务是"回到过去改同一个 bug / 加同一个功能"，验证命令是确定性的 pytest。它的定位是回归基线而非公平评测：agent 在完整 git 历史里运行，base_commit 之后的提交可见，有答案泄漏面，所以结果页必须披露"A 轨非公平评测"。

**B 轨是当前演进（12 个）**——基于当前 HEAD 的真实缺陷和增强构造，是面试核心。覆盖面包括沙箱执行器、benchmark CLI、LSP diagnostics、ListRunningBenchmarks 只读工具装配链、statechart 新态、结果页 track 分组、SwebenchAdapter model name 转义回归、memory project scope 隔离、记忆注入归属下沉等。B 轨任务刻意不给文件路径，只给行为症状，agent 需要自己通读管线定位；验证是确定性 test_command + test.patch 新增回归断言，base 红/gold 绿可复现。

关键设计是每个任务有可自动验证的正确性标准，且 task 文件在 agent 执行前被移动到 .hidden 目录——防止 agent 读取测试文件"作弊"。worktree 隔离保证任务间的文件变更不互相污染。

---

## 追问 4：Gate 的门禁指标为什么是 5pp success_rate 和 5% p95？不是更严？

**回答（~200 字）：**

5pp 和 5% 是 CI 门禁的"防退步底线"，不是"质量目标"。门禁要做的是拦截显著的回归——改一行代码导致 10% 的任务失败，那就肯定有问题。但如果严格要求 success_rate 不下降，会导致两个问题：第一是假阳性——模型 API 本身有非确定性，同一任务同一配置跑两次结果可能略有不同，严格不下降会导致 CI 频繁误报；第二是抑制改进——有些重构可能稍微降低某个边缘 case 的通过率但整体架构改善很多，5pp 的门槛允许合理权衡。

p95 延迟还有特殊处理——当 baseline p95 < 1s 时，用绝对 floor 1s 代替相对 fraction。因为 sub-second 任务的相对波动（0.3s→0.4s 就是 33%）没有实际意义，可能是随机噪声。abs_p95_floor 解决了这个"sub-second baseline 不适用相对比较"的计量问题。

---

## 追问 5：Benchmark 结果怎么跟其他 Agent 对比？

**回答（~200 字）：**

对比的核心原则是**同任务、同 harness、仅换一个变量**——换 agent 对照（Asterwynd vs 参照 agent）和换 model 对照（本地主力 vs API 前沿）分开写，数字仅在同一 harness 内可比。

compare.py 是独立 CLI，输入是多个 run 目录，输出 Markdown 和 HTML 对比报告。当输入恰好两个 run 时，追加**配对比较段**：per-task delta（同一任务上 A 的 pass@1 减 B 的 pass@1）、差异 95% CI（paired bootstrap——重采样时同一任务索引同时读两侧，保持配对性，否则方差会高估）、win-rate（A 胜/B 胜/平的任务数）、McNemar 检验（在 pass^k 布尔上做 exact-binomial 显著性）。SWE-bench 任务使用官方验证器（swebench.harness.run_evaluation）确保判定标准一致。

目前的局限是仅支持文件级 run 目录对比，没有 Web dashboard。这适合 CI 集成和本地对比，不适合对外公开展示——这也是后续可以做的一个方向。

---

## 追问 6：pass@1、pass@k、pass^k 有什么区别？为什么成本要用 cache-aware 定价？

**回答（~200 字）：**

三个指标回答三个不同的问题。**pass@1** 是用户实际获得的——把有效轮次里通过的比例直接算出来，它是"开箱即用的体验"。**pass@k** 是能力上限——同一个任务跑 k 次至少一次通过的组合概率（Chen et al. 2021），回答"如果允许重试，这个 agent 能不能解决"。**pass^k** 是可靠性——要求一个任务的全部有效轮都通过才算成功，回答"能不能稳定复现"，这是 CI 门禁和工程交付最关心的。

成本为什么用 cache-aware 定价？因为 Agent 系统的真实账单里 cache hit 占比很高——稳定前缀（system + 工具 schema）每轮重复发送，命中 cache 的价格只有 fresh input 的 10%。如果只用两档定价，同一任务不同前缀命中率的成本会被系统性低估或高估，$/resolved-task 就不可比。四档定价（fresh / cache read / cache write / output）+ `PRICING_TABLE_VERSION` 版本戳，让成本数字可追溯、可复现。
