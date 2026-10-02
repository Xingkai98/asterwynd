# 对抗验证: read-output-bound grill 结论

## Reviewer

- run id: `grill-adversarial-read-output-bound-2026-10-02`（独立零记忆对抗 subagent，只读 grill 报告 + change 文档 + 被改代码 + 参考仓库，实跑 `ReadTool`）
- 时间: 2026-10-02
- 方法：对每条 grill 主张**先复现、再构造反例证伪**；凡"实测"均在本 worktree 跑 `ReadTool.execute` 得到，非推断。所有实验脚本随 run 临时落盘（`/tmp/adv_exp1.py` 等），可复跑。
- 攻击结论概览：**grill 的三条关键"无上界"事实全部复现（未被证伪）**；但 grill **高估了 Q1 的修复代价、低估了 50KB 字节界的实伤、把 D3「逐字节」说得比事实更强**，并**漏掉一条与 Q1 同级的逃逸路径（`limit=0`）和一条真正的续读回退 bug（offset hint 被覆盖）**。

---

## 对「必须改」的裁决

### Q1｜offset 续读路径无上界 —— **survives（事实正确，但代价被 overstated）**

- **事实复核（复现）**：`read.py:98` `end = (start + limit) if limit else None`。实测 100k 行文件 `Read(offset=2000)` 不传 limit → **1,462,074 字节 / 98,002 行**（grill 报 1,070,074 字节 / 98,000 行，差异仅因 fixture 文本不同，结论一致）。**grill 正确**：D2 把模型引向 offset 续读，而 offset 路径本身无界，源头治理被自己的提示打穿。
- **但"代价"被 overstated（本次证伪点）**：grill Q1 推荐写「**代价**：会改到 `test_offset_without_limit_reads_to_eof`（`test_read_doc_and_pagination.py:48-54`）……需随语义更新」。实测反例：该测试 fixture 是 **50 行文件 + offset=48**（`test_read_doc_and_pagination.py:49-51`）。把默认上界（2000 行）施加到 offset 路径后，`lines[48:48+2000]` 仍只命中 `['line-48','line-49']` → 断言 `line-48 in / line-49 in / line-0 not in` **全部通过**。**该测试不会机械失败**。grep 全仓 offset 测试 fixture 均 ≤100 行（`:31,:42,:49,:58,:67`），无一大于上界 → 「bound offset 路径」在当前测试面上**零破坏**。
  - 修正：Q1 的真实代价不是"改测试"，而是"测试的 *意图/命名* 变陈旧（小文件仍看似读到 EOF）+ 需补一条新测试锁住新语义"。这把 Q1 的**修复成本从"要动既有断言"降到"纯新增"**——Q1 比 grill 说的更划算。
- **裁决**：主张 survives（逃逸面真实）；`代价` 部分 **refuted**（测试不破）；**严重度应为 Top（维持）**。

### Q2｜只限行数漏掉 minified 大文件 —— **survives（事实正确）；但 50KB 推荐 needs-revision（实伤被低估）**

- **事实复核（复现）**：1 行 4MB `bundle.min.js` 无参读 → **4,194,304 字节**（`total=1 ≤ 2000` 走全文路径），与 grill 数字**逐字节一致**。1000 行 ×10KB 的 20MB 文件 → **20,481,999 字节**。grill 正确。
- **50KB 取值的 provenance —— 攻击失败，survives**：我尝试证伪「pi/opencode 的 MAX_BYTES 是**终端显示**场景，不能类比喂给 LLM 的工具结果」。读参考仓库源码：`pi .../tools/read.ts:156` 的 `truncateHead(selectedContent)` 在 `execute()` 内直接作用于**返回给模型**的 content（工具描述 `read.ts:76` 亦写明 truncate 语义）；`opencode .../tool-output-store.ts` 是模型可见的 tool-output 存储层。**二者都是 model-facing，不是 terminal-display** → grill 的类比成立，攻击失败。
- **50KB 推荐 needs-revision（本仓实伤被抽象化）**：grill 把代价写成「R1 的『逐字节不变』覆盖面从『所有 ≤2000 行文件』收窄为『≤2000 行且 ≤50KB』」——过于抽象，掩盖了**本仓的确切受害者**。实测：
  - `agent/config.py` 1913 行 / **71.0KB**
  - `agent/subagent/manager.py` 1709 行 / **71.3KB**
  - `agent/loop.py` 1614 行 / **70.8KB**
  - `agent/main.py` 1490 行 / **57.5KB**
  - `agent/tools/command_guard.py` 1199 行 / **52.4KB**
  - （`agent/` 共 **5 个 .py 文件 ≤2000 行但 >50KB**。）
  取「行数**或**字节先到」后，agent 读自己的 `config.py`（一个开发任务里高频读改的核心文件）**会被截**——尽管它只有 1913 行、远低于行上界。这不是"覆盖面收窄"这种中性描述，而是**对核心源文件的读功能回归**。
  - 另一重内在矛盾：grill 的 CD3 **自己引用了本仓 32KB 先例**（`read_doc.py:22` `MAX_DOC_SIZE_BYTES = 32*1024`，与 `sources.py:121` `MAX_ASTER_SIZE_BYTES` 对齐），却在 Q2 推荐**外部**的 50KB，未解释为何**弃内取外**。两个候选（32KB 内例 vs 50KB 外例）都没解决"核心文件被截"这一具体伤。
  - 建议改法：若保留字节维，**不要用「先到者截」的 50KB 硬顶**；改为「字节界只兜**少行超长行**的病理情形」——例如仅当 `total` 很小而 `bytes` 极大（minified/大 JSON）时用字节兜底，避免动到 ≤2000 行的稠密代码；或把字节阈值抬到不会命中 `config.py` 档（>~80KB）。这样 Q2 能吃到"单行 4MB"，又不制造 5 个核心文件的截断回归。
- **裁决**：事实 survives；50KB **具体数值与形态 needs-revision**；严重度 Top（维持）。

### Q3｜注记是双模块契约、不显式说截断 —— **survives**

- **事实复核（复现）**：`_READ_PROGRESS_RE`（`manager.py:21`）= `\[ReadProgress file="([^"]*)"; offset=(\d+); total=(\d+)\]`，右端 `\]` 锚定。实测：当前注记 `...; total=3196]` → **匹配**；追加字段 `...; total=3196; truncated=true]` → **正则返回 None**（静默失配）。grill 正确。
- **消费者面**：全仓 `_READ_PROGRESS_RE` 消费者只有两处——`manager._extract_read_progress`（`manager.py:470`，喂 summary hint）与 `test_progress_note_format_matches_regex`（`test_read_doc_and_pagination.py:73-83`）。失配即 hint 无声消失，与「不静默」纪律（#248/#275）冲突。grill 正确。
- **裁决**：survives；严重度正确（中高，因"无声"特性）。**注**：Q3 与 Q1 绑定的建议正确（别拆两次改）——但见上，Q1 成本其实更低。

### 风险｜「尾部内容丢失（head-only 截断）」 —— **survives，属实**

- grill 指出 head-only 会系统性丢尾部（`__main__` / 导出表 / 注册表）。这是 head 截断的**固有**性质，属实。pi 用显式 next offset 缓解、opencode 用 head+tail 采样——grill 描述准确。无新反例。

### 风险｜「默认上界可被模型习惯性绕过」 —— **partially survives；漏掉一条同级逃逸**

- grill 举 `limit=100000` 绕过（实测 `limit=90000` → 1,338,889 字节；grill 报 978KB，fixture 差异，同结论）。属实。
- **但 grill 漏掉 `limit=0`（新发现，见下「grill 漏掉的」M1）**——同为无界逃逸，且比 `limit=100000` 更隐蔽。

### Confirmed 裁决

- **CD「三分支语义方向正确」→ survives**：与 `read.py:92-105` 现状一致，方向无误。
- **CD「2000 行有业界收敛证据」→ survives**：实测 `pi .../tools/truncate.ts:11` `DEFAULT_MAX_LINES = 2000`、`opencode .../tool-output-store.ts` `MAX_LINES = 2_000`，两条引用**逐字属实**。2000 取值可信。
- **CD「图片路径/D4 正交」「E0 只作对照」→ survives**，属边界与流程判断，无代码反例。
- **CD「改动面极小——唯一改动点 `read.py:103-105`，回滚=revert」→ needs-revision（内部不自洽）**：该结论**只对"最小设计"成立**。一旦采纳 grill 自己的 Q1（bound offset 路径，动 `read.py:92-101`）+ Q2（加字节维）+ Q3（改注记格式，动 `read.py:100` **且** `manager.py:21` **且** 跨模块测试），改动面**不再是一个分支 + 一个常量**：它横跨两个模块、两个测试文件、并新增 spec 条款。「改动面极小 / 回滚 = revert」与 Q1/Q2/Q3 推荐**互相打架**；grill 未调和。建议：把该 Confirmed 改写为"**最小设计**改动面极小"，并把 Q1-Q3 采纳后的**真实改动面**单列。

---

## 对 6 条 Confirmed + 7 个推荐的裁决

| 条目 | 裁决 | 证据 / 说明 |
|---|---|---|
| CD-三分支方向 | **survives** | `read.py:92-105`；方向正确 |
| CD-2000 有业界依据 | **survives** | pi `truncate.ts:11`、opencode `tool-output-store.ts` 实读逐字属实 |
| CD-双模块契约 | **survives** | 正则右锚定实测失配（EXP B） |
| CD-D4/D5 边界 | **survives** | 图片与显式参数量分属独立面，无矛盾 |
| CD-改动面极小/可回滚 | **needs-revision** | 与 Q1/Q2/Q3 推荐互斥（见上） |
| CD-E0 只作对照 | **survives** | 流程判断，grill 与 proposal 一致 |
| **Q1** offset 也施加界 | **survives（推荐方向正确）；代价 refuted** | 逃逸真实（EXP1）；但"会改到 test_offset_without_limit_reads_to_eof"**证伪**——该测试在上界下仍通过 |
| **Q2** 加 50KB 字节界 | **needs-revision** | provenance 属实（攻击失败）；但 50KB 实截 5 个核心文件（config.py/loop.py/main.py/manager.py/command_guard.py）→ 形态应改为"只兜少行超长行" |
| **Q3** 注记显式截断+next offset | **survives** | 契约真实；**新副作用见 M2（改格式=跨模块改，影响面 grill 已大致覆盖）** |
| **Q4** 上界可配置三处不一致 | **overstated（轻微）** | proposal:35「SHALL 可配置」、design D1「可配置（可选）」、spec delta「non-magic constant」——三者是**遗漏**（spec 未提配置）而非**矛盾**；grep 确认 proposal 与 design 均提、spec 未提。方向（统一为"常量+可选 config"）对 |
| **Q5** 默认读给 summary hint 加 offset=0 | **survives 且应升权（grill 低估）** | last-wins 实测：同文件先 offset=0 后 offset=2000 → hint=2000（正确）；**先 2000 后 offset=0 → hint=0（回退！）**。grill 只说"每次默认读加一条 offset=0"（幂等无谓），**漏了它会覆盖真实的续读进度**——见 M3 |
| **Q6** E0 可测性 | **survives** | 与 proposal「E0 不设门槛」一致；建议补确定性字节单测锁 Q2 合理 |
| **Q7** spec 归属（并入 vs 新增 Requirement） | **survives（且方向对）** | base spec `spec.md:49-58` 该 requirement 仅讲"分页+持久化"，delta 塞入"默认上界"确使名字不覆盖；倾向新增独立 Requirement 合理 |

**是否会引入新问题**：
- Q2 的 50KB（若照字面采纳）→ **是**，制造 5 个核心文件的读截断回归（新问题）。
- Q3 的改格式 → 需同步 `manager.py:21`，否则 hint 静默消失（grill 已警示）。
- Q5 的 offset=0 hint → **是**，可覆盖真实续读 offset（M3）。
- Q1 的 bound offset → 若实现为 `if limit:` 真值判断，**会与 M1（limit=0）叠加**：`limit=0` 落 else 支时需决定是否给界。

---

## grill 漏掉的

- **M1（同级逃逸）`limit=0` 是一条无界路径**。实测：`Read(path, limit=0)`（无 offset）→ **返回全文**（`read.py:103` `if limit:` 对 0 为假 → 落 `return content`）；`Read(path, offset=0, limit=0)` → `read.py:98` `(start+limit) if limit else None` 对 0 为假 → `end=None` → **读到 EOF**（实测 28,959 字节 = 全文 + 注记）。若修复用 `if limit:` 真值分支实现默认界，`limit=0` 会**绕过**上界。grill 的 Q1/Risks 只举了 `limit=100000`（大值），**没提 limit=0（0 值）**。修复须用 `if limit is not None` 语义，或显式处理 0。**严重度：高（与 Q1 同级，逃逸面）**。

- **M2（spec 措辞失真）D3 / spec delta 的「byte-for-byte identical to the file's full content」在今天就已不成立**。实测：`Read` 走 `p.read_text(errors="replace")`（`read.py:88`）+ 通用换行翻译——CRLF 文件 `a\r\nb\r\nc` → 返回 `a\nb\nc`（`\r` 被吃掉）；非法 UTF-8 字节 → 返回替换字符（22 字节原始 → 26 字节返回）。**默认全量读从来不是"逐字节等于文件"**。因此：
  - spec delta 的 Scenario「small file is returned in full → byte-for-byte identical to **the file's** full content」**字面为假**（CRLF/非 UTF-8 文件即反例）→ 应改为「与**当前无界输出**逐字节相同」（回归-vs-现状），而非"与文件相同"。
  - grill 的 Risks 里「`splitlines()` 归一化……**仅影响大文件（被截的那批）**」是**错误归因**：换行/编码归一化是**全局且既有**的（作用于所有文件、包括全文路径），不是截断路径的问题。grill 把"截断路径 splitlines 的轻微损失"与"read_text 全局有损"混为一谈，导致 D3「逐字节」红线被说成可达成。**严重度：中（spec 级措辞 bug，会被 strict validate 之外的语义审阅抓住）**。

- **M3（续读回退，Q5 的真问题）默认读会把真实的续读 offset「覆盖」为 0**。`_extract_read_progress` 是**每文件取最后一次匹配**（`manager.py:459` docstring「last-window semantics」）。实测：tool 结果序列 `[offset=2000 注记, offset=0 注记]` → 提取 `('sched.py', 0, 3196)`；**顺序反过来才得 2000**。即：模型读到 offset=2000（正进行分页）后，**任何一次对同一文件的默认读**都会把 hint 回退成 `offset=0`，summary 随后建议"**从头**续读"——丢失真实进度。grill 的 Q5 只把它当作"无谓涨字节/幂等重读"，**低估为可接受**；实际是**分页进度的正确性回退**（虽被上界兜住不致命，但直接破坏 Pagination Progress Preservation 的意图）。**应升权，且缓解不能只是"记入 Risks"**：需让 hint 区分"默认截断(offset=0)"与"显式分页"（例如新增字段标记 offset=0 是否来自默认截断），或 hint 只纳入"真正的分页读"。**严重度：中高**。

- **M4（小）R0 的"受约束"只有行维、缺字节维**。proposal R0「单次超大文件返回字节数受默认上界约束」——但 2000 行 `scheduler.py` 实测 **78,802 字节 / ~44,153 token 原文（首 2000 行 ~27,684 token）**，单条仍占 80k 预算的 ~35%。"受约束"若只用行数衡量，读者会误以为结果变小很多；R0 应绑一个**字节/token 阈值**（这也正好是 Q6 建议的确定性单测该断言的对象）。严重度：低（验收口径，非代码）。

- **M5（小）`:total` 的语义未与"offset 越界"路径对齐验证**：`offset=100` 于 10 行文件 → 实测返回空体 + `offset=100; total=10]`（`test` 亦锁定）。默认界引入后，`total` 仍是**文件总行数**（不是剩余行数）——grill 默认 `total=M` 正确，但设计未显式说明"total 恒为文件总行数、与 offset 无关"，易在改造中被误解为"剩余"。建议 spec/design 一句话钉死。严重度：低。

---

## 总体

**可信（grill 说对了、我复现且未能证伪）**：
1. Q1 逃逸面（offset 无界）——事实逐字复现（1.46MB / 98k 行）。
2. Q2 minified/少行超长行绕行——4,194,304 字节逐字节复现。
3. Q3 双模块契约 + 正则右锚定静默失配——复现（追加字段 → None）。
4. CD-2000 业界依据——pi/opencode 引用逐字属实。
5. 尾部丢失、`limit` 大值绕过、E0 口径、Q7 spec 归属——方向均正确。

**需修正**：
1. **Q1 代价 overstated**：`test_offset_without_limit_reads_to_eof`（50 行 fixture）在上界下**仍通过**，不构成破坏；Q1 比 grill 说的更划算（纯新增测试即可）。→ 修正 Q1 的"代价"表述与 CL 措辞。
2. **Q2 的 50KB needs-revision**：会实截 5 个核心 `agent/*.py`（config/loop/main/manager/command_guard），且 grill 自己的 32KB 内例被弃用未解释。→ 改为"只兜少行超长行"的形态或抬高阈值。
3. **CD-改动面极小 needs-revision**：与 Q1/Q2/Q3 推荐互斥，两种口径须拆开写。
4. **Q4 overstated**：是"遗漏"不是"矛盾"。
5. **Q5 应升权**：不是"幂等重读"，而是**覆盖真实续读 offset 的回退**（M3）。grill 缓解不足。
6. **D3「byte-for-byte」措辞失真**（M2）：spec delta 字面为假，应改为"与当前无界输出逐字节相同"；grill 对 splitlines 的影响归因有误。

**新发现（grill 完全未提）**：
- **M1 `limit=0` 无界逃逸**（与 Q1 同级，修复必须处理 0 值真值陷阱）。
- **M3 summary hint 被默认读覆盖为 offset=0**（分页进度正确性回退）。
- **M2 spec「逐字节」措辞 + 全局 read_text 有损**。
- M4 R0 缺字节维、M5 `total` 语义未钉。

**严重度排序（修正后）**：Q1 ≈ **M1**（逃逸面）> Q2（byte，但形态要改）> **M3**（Q5 升权，续读回退）> Q3（不静默契约）> Q5-原述 > Q4/Q6/Q7 > M2/M4/M5（措辞/口径）。**grill 把 M1、M3 两处漏在排序之外，是本次对抗的主要增量。**
