# Grill: read-output-bound 设计追问

## Reviewer

- run id: `grill-read-output-bound-2026-10-02`（独立零记忆 subagent，只读 `design.md`/`proposal.md`/`tasks.md`/spec delta + 被改代码 + 参考仓库）
- 时间: 2026-10-02
- 被审对象: `openspec/changes/read-output-bound/{proposal,design,tasks}.md` + `specs/context-engineering/spec.md` delta
- 复核的实测证据（本 worktree 实跑，非推断）：
  - `offset=2000`（不传 limit）读 100k 行文件 → **返回 98,000 行 / 1,070,074 字节**（缓存改动后的同一支逻辑即现状）。
  - 1 行 4MB 的 `bundle.min.js` 无参数读 → **返回 4,194,304 字节**（`total=1 ≤ 2000` 走全文路径）。
  - `ReadDoc`（`read_doc.py:22`）已有 `MAX_DOC_SIZE_BYTES = 32*1024` 的**字节**截断 + 显式 `已截断` 注记先例；`tools.display.max_result_chars/max_result_lines` 配置先例（`agent/config.py:1425-1432`）。
  - `[ReadProgress]` 是**双模块契约**：`read.py:100` 发射 ↔ `memory/manager.py:21` `_READ_PROGRESS_RE` 解析（正则右端锚定 `total=(\d+)\]`）。

---

## Confirmed Decisions

- **决策**: 确认「超界 → 首 N 行 + `[ReadProgress]` 注记；≤ 界 → 逐字节全文；显式 `limit`/`offset` 走既有逻辑」的三分支语义方向正确，与既有 offset 分页语义和 `context-engineering` 的 `Pagination Progress Preservation` 对齐，不需要为新行为另立一套机制；理由: `read.py:92-105` 已有 offset 分页 + 注记，本 change 只是把「无参数」这一支从 `return content` 收紧为默认上界，属既有意图的默认值落地，改动面最小；来源: `design.md` D1/D2/D3、spec delta Scenario 1-4、`read.py:78-105`。

- **决策**: 上界取值 **2000 行**作为行上界有业界收敛证据支撑，保留 2000 合理，不必按本仓库统计（中位 107/90 分位 540）另行拍数；理由: `opencode` 与 `pi` 两个独立实现都取 2000——`opencode/packages/core/src/tool-output-store.ts:11` `MAX_LINES = 2_000`，`pi/packages/coding-agent/src/core/tools/truncate.ts:11` `DEFAULT_MAX_LINES = 2000`，且 pi 的 read 工具描述明写「truncated to 2000 lines or 50KB (whichever is hit first)」（`pi/.../read.ts:76`）；这意味着 2000 是行业默认而非拍脑袋，本仓库 90 分位文件（540 行）在 2000 下无影响；来源: 参考仓库 `opencode`/`pi` 实读。

- **决策**: 「复用既有 `[ReadProgress]` 格式、不新增标记」的**方向**成立，但必须把它登记为 `read.py` 与 `memory/manager.py` 的**双模块契约**——任何字段增删（如加 `truncated=true` 或 next offset）必须同时改发射端与 `_READ_PROGRESS_RE`，并补一条跨模块测试；理由: `manager.py:21` 正则为 `\[ReadProgress file="([^"]*)"; offset=(\d+); total=(\d+)\]`，右端以 `\]` 锚定，在 `total` 后追加字段会**静默失配**（正则返回 None），summary 的续读提示会无声消失——这是「不静默」纪律（#248/#275）最容易被破坏的点；来源: `read.py:100`、`memory/manager.py:20-21,449-473`、`tests/agent/tools/test_read_doc_and_pagination.py:73-83`（已有该正则的格式测试）。

- **决策**: 确认 D4（图片路径 `_read_image` 返回 `ContentBlock` 不动）与 D5 的 `limit` 部分（显式 `limit` 行为不变）为正确边界；理由: 图片 base64 驻留是 #280 对抗验证列的独立问题，与本 change 的「文本单条上界」正交；显式 `limit` 是模型主动要求的行为，不应被默认上界覆盖；来源: `read.py:84-86,103-105`、`design.md` D4/D5、proposal Non-Goals。

- **决策**: 确认本 change 的**代码改动面**与**回滚性**判断成立——`read.py` 单个函数的一支分支 + 一个常量，回滚 = revert；理由: `ReadTool.execute` 的 `offset is None` 分支是唯一改动点（`read.py:103-105`），现有 Read 相关测试（`test_read_write_tools.py`、`test_read_doc_and_pagination.py`）全部使用小文件，不会被默认上界波及；来源: `read.py:78-105`、`tests/agent/tools/test_read_write_tools.py`、`tests/agent/tools/test_read_doc_and_pagination.py`。

- **决策**: 确认 E0 只作对照、不设门槛是**正确**的口径，但必须明确它是**非 CI 门禁的人工观测**，真正的 CI 门禁是 R0/R1/R2；理由: #278 复现器依赖真实 LLM 多 agent 并发，无法进 CI；「B 值不值得」的判据本来就依赖一次人工实测（proposal 明确 B 的价值之一是「用一次实测把要不要做 A 从判断变成数据」）；来源: `proposal.md` 验收表 E0、`design.md` Testing Strategy。

---

## Open Questions

> 每条给出**推荐答案 + 该 change 真实场景的具体例子**，供用户快速拍板。按影响面排序。

- **Q1（关键 · 逃逸面）**：offset 续读路径**本身无上界**——`read.py:98` `end = (start + limit) if limit else None`，即 `offset` 不带 `limit` 时读到 EOF。D2 又恰恰把模型引导到「传 `offset=N` 续读」。于是：默认读给出 `offset=0` 提示 → 模型照做 `Read(path, offset=2000)` → **若文件很大，巨型单条重现**，本 change 的源头治理被自己的续读提示打穿。
  - **例子**：100k 行日志文件。现状无参数读回全文（巨型，本 change 要治）；**本 change 后**默认返回 2000 行 + `[ReadProgress ...; offset=0; total=100000]`，模型按提示 `Read(offset=2000)` **不传 limit** → 实测返回 **98,000 行 / 1,070,074 字节**——巨型单条原样回来。
  - **推荐**：把默认上界**也施加到 offset 路径**，与 pi/opencode 一致——「模型显式传 `limit` 时优先，否则无论有无 offset 都按 2000 行/50KB 截断，并把**下一个 offset** 写进注记」。pi 的 read 就是这样：`if (limit !== undefined) 用用户 limit；否则 truncateHead(...)`（`pi/.../read.ts:147-171`），注记 `Use offset=${nextOffset} to continue.`。**代价**：会改到 `test_offset_without_limit_reads_to_eof`（`test_read_doc_and_pagination.py:48-54`）——该测试当前断言 offset 读到 EOF，需随语义更新（这本就是设计要触碰的测试面）。若坚持 D5「offset 行为完全不变」，则**至少**在注记里给出 next offset 并显式说明续读须带 limit。

- **Q2（关键 · 字节 vs 行数）**：D1 只限**行数**，对「少行超长行」文件（minified JS、大 JSON、单行长数据）**完全无效**；opencode 与 pi **都**同时限字节（`MAX_BYTES = 50*1024`），且本仓库 `ReadDoc` 已有字节截断先例。
  - **例子**：`bundle.min.js` 1 行 4MB。`total=1 ≤ 2000` → 现设计走「全文」路径，**实测返回 4,194,304 字节**——R0（单次超大 Read 受上界约束）对这类文件**不成立**。同理一个 2000 行、每行 10KB 的 20MB 文件也被放行。
  - **推荐**：加 **50KB 字节上界**（与 opencode/pi 同为 50KB），语义取「行数**或**字节，先到者截」；并相应把 **D3 / R1** 从「≤ N 行逐字节全文」改为「**≤ N 行且 ≤ maxBytes** 才逐字节全文」（否则被字节截的是小行数文件，与 D3 表述冲突）。代价：R1 的「逐字节不变」覆盖面从「所有 ≤2000 行文件」收窄为「≤2000 行且 ≤50KB」，需在 spec/验收同步措辞。

- **Q3（关键 · 不静默纪律）**：D2 复用 `[ReadProgress file=...; offset=0; total=M]`，注记**不显式说「已截断」、也不给 next offset**——模型须自行从「返回行数 < total」推断被截，弱于 pi（`[Showing lines 1-2000 of 3196 ... Use offset=2001 to continue.]`）。本仓库 #248/#275 的纪律是「截断/上限必须显式可见」。
  - **例子**：3196 行文件默认读 → 模型只看到 `offset=0; total=3196` 与 2000 行正文；若模型不细算 2000<3196，可能误以为已读全而**漏掉尾部**（如文件末尾的 `__main__` 块 / 注册表 / 导出列表）。
  - **推荐**：注记加显式截断语义 + next offset（如追加 `; truncated=true` 或改写为 human-readable 提示）。**注意**：这会触到 Q 的**双模块契约**（需同步 `manager.py:21` 正则 + 跑 `test_progress_note_format_matches_regex`），是 Q1 的一部分工作，别拆成两次改。

- **Q4（口径一致性 · 可配置）**：「上界是否可配置」在 change 文档内**三处不一致**——proposal 说「默认上界 **SHALL 可配置**（config）」（proposal.md:35）并列为 IMPACT 的可选改动；design D1 说「可配置（**可选**）」；spec delta 只写「a defined, **non-magic constant**」**不含可配置**。
  - **例子**：若实现按 spec delta 只放一个模块常量 `DEFAULT_MAX_READ_LINES = 2000`，则 proposal 的「SHALL 可配置」未兑现，CI 的 spec↔proposal 一致性无从校验；若实现加 config，则 spec delta 缺对应条款。
  - **推荐**：定调**常量 + 可选 config**，与既有风格一致（`tools.display.max_result_chars/max_result_lines`，`agent/config.py:1425-1432`），并**三处同步**：proposal 的 SHALL 措辞、design D1 去掉「可选」歧义、spec delta 增加「SHALL 有内置默认，SHALL 可经 config 覆盖」。同时删掉 spec delta 的「non-magic constant」表述——那是实现细节，进 spec 层是噪音（spec 应写可观察契约，不写命名约定）。

- **Q5（依赖 · manager 语义偏移）**：默认读大文件现在会**发射** `[ReadProgress ...; offset=0 ...]`，而 `manager._extract_read_progress` 会把**每个文件最后一次**匹配当作「续读候选」写进 summary hint（`manager.py:449-473,489-505`）。改动前，一次「读全」不产生注记、不进 hint；改动后，每次默认读大文件都会给 hint 加一条 `- /path: offset=0, total=M`。
  - **例子**：agent 读了 3196 行的 `scheduler.py`（默认截到 2000 行），summary hint 出现 `- scheduler.py: offset=0, total=3196`。这条语义上**不是**「未读完的分页」，却会被当成 resume 候选，可能诱导模型在每次 compaction 后**从 0 重读**（虽被上界约束、不致命，但无谓涨字节）。
  - **推荐**：确认可接受（offset=0 重读是有界且幂等的，代价可控）；若要求更干净，则让 hint 只纳入「真正未读完」的读——但这需要区分「默认截断」与「显式分页」，会加复杂度。**建议采前者**并在 design 的 Risks 显式记一条。

- **Q6（验收可测性 · E0）**：E0 需真实 LLM 多 agent 并发跑 #278 复现器「缩比版」，**无法进 CI**、也无确定阈值。若无人跑，R0/R1/R2 过了但「B 是否值得、A 是否必须」的判据落空。
  - **例子**：tasks 3.5「端到端对照」若只写在 checklist 而无落地脚本，PR 很可能只跑单测就提交，E0 实测缺失 → proposal 里「B 的价值之一是产生 A 的判据」无法兑现。
  - **推荐**：(a) 明确 E0 为**人工观测**产物，在 PR 描述记录（tasks 3.5/4.3 保持手动）；(b) **补一条确定性单测**替代 E0 做 CI 回归——断言「读 3196 行文件返回的**字节数** ≤ 上界对应的字节阈值」（这也正好把 Q2 的字节上界锁进回归网）。E0 只作「A 是否必须」的对照，不进 CI。

- **Q7（spec 归属与措辞）**：spec delta 把「默认输出上界」**并入**既有 Requirement `Pagination Progress Preservation`，导致该 requirement 名（讲「进度持久化」）已不能覆盖新增的「默认上界」内容。
  - **例子**：base spec 该 requirement 是「Read 支持 `(file, offset, total)` 进度，且上下文系统在压缩前持久化该进度」（`openspec/specs/context-engineering/spec.md:49-58`）；delta 塞进「默认上界 + 超界注记 + ≤界全文」三段后，同一 requirement 下混了「默认值收紧」与「进度持久化」两个关注点。
  - **推荐**：二选一并统一——(a) 维持 MODIFIED（承认二者同属「大文件读取的上下文行为」，但**建议微调 requirement 正文**使其自洽）；或 (b) 改为 **ADDED 一条独立 Requirement**（如 `Read Default Output Bound`），更清晰、也不动既有条款。**倾向 (b)**：默认上界是独立可观察契约，与「压缩前持久化进度」不是一回事。注意 strict validate 只校验 requirement **名**在新旧间的一致性——若改名/新增，需确认 delta 头写 `## ADDED Requirements` 而非 `## MODIFIED Requirements`。

---

## User Confirmation

> 2026-10-02 用户逐条拍板（经独立对抗验证 `grill-adversarial.md` 后的结论）。

- **Q1（逃逸面：offset 无 limit / limit=0）**: 用户答复：**三处都堵**——① 用 `limit is not None` 语义（`limit=0` 也当显式值，不再落全文）；② `offset` 路径在无显式 `limit` 时也施加默认行数界；③ 加字节兼底。三个口子一起堵才算「源头有界」；确认时间: 2026-10-02
- **Q2（字节兼底阈值）**: 用户答复：**不用 50KB**（会误截 5 个核心文件 config.py/loop.py/main.py/manager.py/command_guard.py，52–72KB），改为**只兜「少行超长行」**——行数 ≤ 默认界但字节 > **128KB** 时才截（避开核心文件，只治 1 行 4MB 那类 minified/大 JSON）；确认时间: 2026-10-02
- **Q3（注记显式）+ Q5（offset 回退）**: 用户答复：**两项都做**——① 注记显式写「已截断，续读传 offset=<next>」（符合 #248/#275 不静默纪律），并同步 `_READ_PROGRESS_RE` 双模块契约；② **修 offset 回退**——默认截断的 `offset=0` 不得覆盖真实的显式分页进度（实测 last-wins 会让 summary 建议「从头续读」）；确认时间: 2026-10-02
- **Q7（spec 归属 + R0 口径）**: 用户答复：**新增独立 ADDED Requirement**（不并入 `Pagination Progress Preservation`），且 **R0 验收同时绑行维与字节维**（避免「看着小了其实还很大」——2000 行 scheduler.py 仍 ~7.9 万字节 / ~2.7 万 token）；确认时间: 2026-10-02

**依对抗验证修正（一并落实）**：CD「改动面极小」需修订（Q1+Q2+Q3 使改动扩到 `read.py` + `memory/manager.py` 两模块 + 跨模块测试）；D3/spec 的「逐字节等于文件」改为「**与当前无界输出逐字节相同**」（`read_text(errors="replace")` 今天已做换行/编码归一化，"与文件相同"字面为假）；R0 缺字节维、`total` 语义需在 spec 钉死（恒为文件总行数，与 offset 无关）。

---

## 风险

- **尾部内容丢失（head-only 截断的固有代价）**：只返回首 N 行会系统性地**丢掉文件尾部**——而尾部常是关键（`if __name__ == "__main__"`、模块末尾的注册表/导出/插件清单、`__all__`）。opencode 用 **head+tail 采样**规避（`tool-over-store.ts` 的 `preview()` 取首尾各半），pi 用**显式 next offset 指引**规避。本设计 head-only + 弱注记（Q3），两者都没做 → 真实任务（逐文件审查时模型需通读）有被做坏的风险。**缓解**：见 Q3（显式续读指引）；若仍不足，考虑 head+tail 采样。

- **默认上界可被模型习惯性绕过**：模型显式 `limit=100000` 或带 `offset` 续读即绕过（本 change 的 D5 + Q1）。实测 `limit=90000` 返回 978KB。若模型偏好「一次给个大 limit 更省事」，默认上界形同虚设。**缓解**：Q1（bound offset 路径）+ 可选对 `limit` 设绝对上限。

- **注记格式是双模块契约，改格式易静默破坏**：`read.py` ↔ `memory/manager.py:_READ_PROGRESS_RE`。任何字段增删若不改正则，`finditer` 静默返回空 → summary 的续读提示**无声消失**（不报错、不告警），违反「不静默」纪律。**缓解**：把「改注记格式 = 同改两处 + 跨模块测试」写进 tasks；已有 `test_progress_note_format_matches_regex`（`test_read_doc_and_pagination.py:73-83`）是这一契约的守门测试，新增字段时它必须同步。

- **`splitlines()` 归一化使截断路径非逐字节**：`total > N` 分支用 `"\n".join(lines[:N])`，`splitlines()` 会吃掉 `\r\n`/`\r`/Unicode 行分隔符并丢弃尾换行——截断输出与原始字节不完全一致。仅影响大文件（被截的那批），不影响 D3 的 ≤界全文红线。**缓解**：在 design 明记这是**预期**（截断本就非无损）；若要求无损，需改用按字节切片。

- **E0 不是门禁 → 「B 值不值得」的判据可能落空**：见 Q6。若 PR 只跑单测，proposal 中「用一次实测把要不要做 A 从判断变成数据」的核心价值无法兑现，A 的决策会被悬置。

---

## 与参考仓库调研的对应（补强 proposal 的 RQ1）

- `opencode`：`packages/core/src/tool-output-store.ts:11-12` → `MAX_LINES = 2_000`、`MAX_BYTES = 50 * 1024`；`packages/core/src/tool/read.ts` 支持 `offset`/`limit` 分页。工具输出**行数与字节先到者截**，marker + `truncated` 标志。
- `pi`：`packages/coding-agent/src/core/tools/truncate.ts:11-12` → `DEFAULT_MAX_LINES = 2000`、`DEFAULT_MAX_BYTES = 50*1024`；`read.ts:76` 工具描述明说「truncated to 2000 lines or 50KB (whichever is hit first). Use offset/limit ... When you need the full file, continue with offset until complete.」；`read.ts:147-171` **显式 limit 优先，否则（含 offset 路径）仍 truncateHead**，注记带 `Use offset=<next> to continue.`。
- **对本 change 的三点直接启示**：(1) **2000 行**取值有据（CD3）；(2) 业界**都同时限字节**（Q2）；(3) 业界**都对续读路径设界并给 next offset**（Q1/Q3）。本 design 当前三点都只做了第 (1) 点。
- 说明：`codex`/`kimi-code`/`zcode`/`deepseek-harness` 未命中「读文件工具默认行/字节上限」的等价常量（`kimi-code` 的 `readLineRange` 走 `maxLines ?? +Infinity`，即**默认不限**——恰好是反例），故本调研以 `opencode` + `pi` 两个正例为准。
