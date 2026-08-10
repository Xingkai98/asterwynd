# Bullet 2 面试讲稿：动态工具编排

> 实现动态工具编排：BM25 粗筛 + 向量精排两阶段按对话上下文 Top-K 注入工具 schema，核心工具稳定层常驻且不占 Top-K 预算、配合 cache_control 断点保 LLM Prefix Cache 命中，工具语义去重 + 质量评分驱动软降级

---

## 主讲述稿（~400 字）

这个功能要解决一个很实际的问题：38 个工具全量注入给 LLM 成本太高——每个工具的 JSON Schema 占几百 token，38 个就是好几千，而且大部分工具当前任务根本用不到。我的方案是每次迭代只选最相关的几个注入。

代码在 `agent/tools/governance/` 目录。核心是 `ToolSelector` 类——每次 LLM 调用前，用"用户最新消息 + 最近 3 个工具调用名"拼成 query，然后走两阶段检索。

第一个设计决策是"稳定层"——Read、Edit、Write、Bash、Glob、Grep、InspectGitDiff 这 7 个工具在任何 coding 任务中都会用到，我让它们永远排在工具列表最前面且位置固定。因为 schema 字节级不变，可以在上面打 `cache_control` 断点，Anthropic API 就不会重复计算这部分的 KV cache。

剩下 ~30 个变层工具走两阶段筛选。BM25 粗筛做关键词匹配，取 top 50。向量精排用 embedding 做 cosine 相似度重排，取 top 5。最终注入 LLM 的是 7 稳定 + 5 变层 = 12 个 tool schema。

还有两个辅助机制。语义去重在每个新工具注册时跟已有工具做 cosine 比较，超过阈值标记 `duplicate_of`，软标记不影响功能。质量评分用 50 次滑动窗口——成功率 + 耗时因子 + 审批率的加权——低于 0.4 就从变层候选剔除，但稳定层不受影响、全量 schema 仍可见。这就是"软降级"。

---

## 追问 1：为什么选 BM25 + embedding 两阶段而不是直接用 embedding？

**回答（~250 字）：**

两阶段是成本和质量之间的权衡。直接用 embedding cos 精排对所有 30 个工具做全量比较，每次 LLM 调用前都要做 30 次 cosine 计算。BM25 粗筛几乎零成本——标准的倒排索引加 TF-IDF 变体，纯 CPU 毫秒级——先把候选池从 30 个收到 50 个（未来工具数 100+ 时会更有意义），然后 embedding 只在 50 个候选中做精排。

BM25 的优势是关键词匹配很准——如果用户说"帮我读文件"，BM25 会对 Read 和 Grep 打高分，因为它直接匹配 description 中的"读取"和"文件"。但 BM25 完全不懂语义——"检查代码"和"review code"对它来说是无关的。Embedding（即使是最简单的 n-gram 哈希向量）能捕捉到字面上的字符共现——Read 和 Grep 的 description 里有很多共同的英文词。

未来工具数增加到 100+ 时，BM25 真正的筛选价值会体现出来——把全量搜缩小到 50 候选，减少 50% 的 embedding 计算量。

---

## 追问 2：当前用的 NGramEmbedding 效果如何？为什么不直接用 sentence-transformers？

**回答（~200 字）：**

NGramEmbedding 是字符 n-gram 的 MD5 哈希拼成的 256 维向量，零外部依赖、确定性（同输入永远同输出）、不需要 GPU、不需要下载模型。对于工具 description 这种几十字的英文短文本，效果其实不差——因为工具名本身就是很强的语义信号，"Read"和"Grep"的 description 里都有"file""search""pattern"这些词，n-gram 向量能捕捉到这种字面共现。

但它的局限也很明显——同义词完全感知不到。"Read"和"View"功能相似，但字面上没有重叠，n-gram cosine 会很低。

不用 sentence-transformers 的核心原因是**零依赖优先**。Asterwynd 的定位是 pip install 即可用，不强制用户装 PyTorch。代码已经预留了 `EmbeddingProvider` Protocol 的插拔缝——只要实现 `embed` 和 `cosine` 两个方法就能替换。如果业务场景对语义精度要求高，一行配置就能切到 all-MiniLM-L6-v2。

---

## 追问 3：Prefix Cache 断点怎么打？如果变层工具变了不会破坏缓存吗？

**回答（~250 字）：**

断点打在**最后一个稳定工具**上，这是精心设计的位置。Anthropic 的 prompt caching 机制是：从 prompt 开头到 `cache_control` 断点之间的所有内容被缓存，断点之后的内容每次重新计算。

我的稳定层是 7 个工具，按注册顺序固定排列，schema 字节级不变。变层的 5 个工具排在后面，每次可能不同。断点打在最后一个稳定工具的位置，意味着 system 消息 + 稳定工具全部被缓存，只有变层的 5 个工具每次重新计算。

95% 以上的迭代中变层工具不会改变——如果用户一直在做文件操作，稳定层就够了，变层可能一直是空的或相同工具。这时整个 tools 数组都被缓存了。只有当用户切换任务类型时变层才变化——比如从读文件变成搜网页。

这里还有个细节：`cacheable` 属性不仅打给稳定工具，还打给 ContextBuilder 的 P0/P1 上下文源。`_compute_cache_plan` 扫描所有 system block 找最后一个 `cache=True` 的位置。默认（Selector OFF）时断点只打 system block，Selector ON 时考虑 tool 层。

---

## 追问 4：质量评分公式的三个权重（0.5/0.3/0.2）是怎么定的？

**回答（~200 字）：**

坦白说，当前公式是一个启发式的起点，不是经过实验验证的最优解。0.5 给成功率是最自然的——工具调用成功与否是最直接的质量信号。0.3 给耗时因子和 0.2 给审批率是直觉分配。

走读代码后我发现了两个问题（已提 issue #120）。第一，耗时因子 `1.0 - avg_duration/30000` 把"快=好"当成普适逻辑，但 git clone 就是比 ls 慢，不代表质量差，业界没人这样用。第二，审批率是安全策略偏好，不是工具质量信号——应该独立存在。

后续改进方向：去掉 duration 和 approval，引入 Tool Selection Accuracy（模型选了不该选工具的比例）和 Invalid Tool Rate（幻觉出不存在的工具），把错误类型分类（超时 vs 参数错误 vs 权限错误）也纳入评分。质量评分应该只问一个核心问题——"这个工具被正确选中的概率有多高"。

---

## 追问 5：如果 selector 功能默认关闭，简历写的这些有什么意义？

**回答（~150 字）：**

代码完整实现了，测试覆盖到位，通过配置开关控制——这是成熟的工程实践，不是 vaporware。就像 nginx 的 gzip 压缩默认关闭不代表没实现。

而且设计上关闭时有合理的降级行为——走 `get_all_schemas()` 全量注入，cache_control 断点打在最后一个 cacheable system block 上。用户不需要证明"我需要动态工具选择"才能用一个功能完整的 agent。随着 MCP 工具接入量增加，这个开关的价值会越来越明显。
