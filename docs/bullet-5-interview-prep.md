# Bullet 5 面试讲稿：长期记忆系统

> 构建长期记忆系统，LLM 写时四分支去重（supplement/update/conflict + new 兜底），importance × recency 联合时效衰减（30 天半衰期）、超期未访问自动归档且可恢复，git commit-before-write + revert 机制保障数据可逆

---

## 主讲述稿（~400 字）

长期记忆系统解决的是跨 session 知识积累的问题。每次 agent 运行完，用户偏好、项目约定、踩过的坑都应该保留下来，下次运行时自动注入上下文。

每条记忆是一个独立的 Markdown 文件，YAML frontmatter 存元数据（importance 1-5、创建时间、最后访问时间、类型标签），正文存实际内容。有一个 MEMORY.md 索引文件做人类可读的目录。5 个工具暴露给 LLM——SaveMemory、RecallMemory、SearchMemory、ResolveMemoryConflict、MemoryGitBackend。

写路径的核心是四分支去重。每次写入前，先向量召回 top 5 相似记忆，然后调 LLM 判决新内容和已有记忆的关系——完全新的就新建文件（new），对已有记忆补充细节就追加到原文尾部（supplement），新内容取代旧内容就整体替换（update），内容矛盾两边都保留并双向标记 conflict_with（conflict）。所有异常路径都 fallback 到 new——宁可重复存，不丢信息。

读路径的核心是 importance × recency 联合衰减。公式是 `importance × 0.5^(days/30)`——30 天半衰期，importance 高的记忆即使不访问也能存活更久。每次 recall/search 命中就刷新 last_accessed_at。超过 30 天未访问且衰减分数低于 1.5 的自动归档到 archive/ 子目录。可手动恢复。

最特别的是 git 可逆机制——memory 目录是一个独立的 git 仓库，懒初始化。每次破坏性写（supplement/update/conflict）前先 git commit 当前状态，commit 失败就中止写入。Revert 是两阶段 commit——先 commit 当前状态做 undo 凭证，再 checkout 旧内容并重建索引。

---

## 追问 1：为什么选文件+Git 而不是数据库？对比过什么方案？

**回答（~250 字）：**

三个核心原因。第一是"人类可读性"——Markdown 文件 + MEMORY.md 索引可以直接用任何编辑器打开查看和修改，不需要专门的查询工具。这在调试记忆系统本身时特别有价值——你可以直接看每一条记忆的内容，不需要写 SQL。

第二是"git 是现成的版本控制"——如果自己实现版本管理，需要做 diff、log、restore，还要处理并发写入和原子性。而 git 已经完美解决了这些问题，加上 Git Worktree 感知的作用域复用——同一个仓库的多个 worktree 共享一份 memory 存储——更是直接拿到了项目隔离和跨 session 持久化。

ADR-0002 里对比了三个替代方案：mem0 V3 的 ADD-only + 读时 ranker（需要多信号排序引擎，Asterwynd 当前只有 NGramEmbedding，弱 ranker 下矛盾记忆会无序浮出）、侧车 revisions 目录（"自己发明的残缺版 git"——缺 diff/log/restore）、单文件 .bak（误判链覆盖中间版本）。最终选择文件+Git 是工程上最务实的方案。

---

## 追问 2：四分支去重里 LLM 判错了怎么办？有纠正机制吗？

**回答（~200 字）：**

多层兜底。第一层是向量召回阈值——相似度低于 0.5 的候选直接短路为 new，不经过 LLM，零成本零误判。第二层是 LLM 不可用时的 fallback——直接 new，不阻塞写入。第三层是 LLM 输出校验——JSON 解析失败、未知 action、target 文件名非法（如 `../etc/passwd`）全部 fallback 到 new。第四层是 target 校验——supplement/update 的目标如果不存在或已归档，退化为 new。

纠正机制有两层。第一层是 git revert——通过 MemoryGitBackend 工具随时回退到任意历史版本，两阶段 commit 保留完整审计链。第二层是 ResolveMemoryConflict 工具——当 conflict 标记存在时，LLM 可以主动调用此工具选择保留一方并归档败者。

核心设计哲学是"宁可多存不丢"——fallback 全部偏向 new 而非拒写。误存可以事后清理，漏存就永久丢失了。

---

## 追问 3：衰减公式里的 30 天半衰期和 1.5 阈值是怎么定的？

**回答（~150 字）：**

30 天半衰期是直觉选值——大部分项目的开发周期以周为单位，30 天意味着一个月不碰的记忆权重降一半，两个月降到 1/4，这是一个温和但持续的衰减曲线。1.5 阈值是基于默认 importance=3——3×0.5=1.5，意味着默认重要度的记忆刚好在 30 天时触碰归档边界。importance=5 的记忆在 60 天后 score=1.25 才会被归档。

这些参数都可配置——构造 PersistentMemory 时可以覆盖 archive_after_days、recency_halflife_days、decay_threshold。也支持关闭衰减（decay_threshold=None），变成纯时间归档。

---

## 追问 4：git commit-before-write 怎么保证不丢数据？

**回答（~200 字）：**

核心设计是"commit 失败 = 写入中止"。`_git_commit` 方法里每个 git 操作都检查返回值——git 不可用抛 RuntimeError、git init 失败抛 RuntimeError、git add 失败抛 RuntimeError、git commit 失败抛 RuntimeError。所有异常在调用方（save/apply_judgment）被捕获，写入操作不会执行。

特殊处理是 nothing-to-commit——当 repo 是全新的（第一次写入前没有任何内容需要快照），git diff --cached --quiet 返回 0，直接安全通过不抛异常。这是合理的——第一次写入确实没有"旧内容"需要保护。

两阶段 revert 是另一个保障——revert 前先 commit 当前状态，所以被覆盖的"当前版本"也有一个快照。这意味着 revert 本身是可 revert 的——你可以回退到回退之前的状态。changelog 保留完整审计，不受 revert 影响。

---

## 追问 5：如果不用 LLM 做去重判决，有什么替代方案？

**回答（~150 字）：**

最直接的替代是纯向量去重——cosine 相似度超过阈值就判定为"相同"，直接 update。但这有个致命问题：无法区分 supplement（补充细节）和 conflict（内容矛盾）。两个描述同一件事的记忆可能 high cosine 但一个是"用 Redis 做缓存"另一个是"用 Memcached 做缓存"——语义相似但内容矛盾。

这就是为什么选了 LLM 判决——它不仅能识别"相似"，还能判断关系的性质（补充/取代/矛盾）。代价是每次写入多一次 LLM 调用，但写操作本身是低频的。mem0 V3 的 ADD-only 方案反过来——不在写时判断，在读时用多信号排序让最佳记忆浮出来。但 Asterwynd 的读路径只有 NGramEmbedding，弱 ranker 下矛盾记忆会无序浮出，所以 ADD-only 不适合当前架构。
