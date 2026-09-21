# Grill: fix-issue-224-bus-unbounded 设计追问

## Reviewer
- run id: grill-224-r1
- 时间: 2026-09-21

## Confirmed Decisions

- **决策**: D1/D7 的「`bus.py` → `manager.py` 常量导入无环」站得住，且导入方向正确（常量应定义在 `bus.py`）。；理由: 用 AST 建 `manager.py` 的**模块级**（import-time）导入闭包，`agent.subagent.bus` **不在**闭包内（`manager.py:1268` 的 `from agent.loop import AgentLoop` 是函数内延迟导入，不参与 import-time 环）；动态验证三种加载顺序（`import agent` / `import agent.tools.builtin.subagents` / `import agent.subagent.bus`）注入该 import 后**全部成功**（实测 `TRANSCRIPT_ITEM_LIMIT = 4000`）。现有仓库已有同向先例（`patterns.py:342`）。；来源: grill-224-r1

- **决策**: D6「不设全文引用、不声称『全文在 X』」正确，是 #213 教训的必要延续。；理由: bus 确无落盘件（`agent/subagent/bus.py:25-26` 文档头「The bus is not persisted across runs」）；唯一持久化的是 `session.py:38` 的 `bus_summary`（字符串），而它由 `compact_summary()`（`bus.py:135-141`）生成并已被 `max_chars` 界住，`manager.py:1490-1492` 只在 checkpoint 写入时使用，不是模型面出口。截断只回流布尔标志是本 change 唯一诚实的做法。；来源: grill-224-r1

- **决策**: D8 的命名 `summary_truncated` 与既有口径一致，不是新造。；理由: `patterns.py:366` 已在 `_worker_entry` 里用 `entry["summary_truncated"] = True`（#213 引入）；`manager.py:122` 用 `content_truncated`、`manager.py:147` 用 `arguments_truncated`。标志挂在 `BusMessage` 上而非 `read()` 返回壳上，能让 `read()` 与 `snapshot_payload()` 两条路径自动同构——这是对的。；来源: grill-224-r1

- **决策**: `snapshot_payload()` 新增 `messages_total` / `messages_omitted` 两个键**不会**破坏既有消费者。；理由: 全仓 `snapshot_payload` 的消费点只有 `patterns.py:458`、`scheduler.py:2956` 两处调用与两个测试（`test_bus.py:75-77` 断言 `len(payload["messages"])` 与 `payload["max_read_tokens"]`；`test_bounded_envelope.py:213` 断言 `"messages" in result["bus"]`）。没有任何地方做键集合全等断言（`grep "set(.*envelope\|set(.*payload"` 在 `tests/agent/subagent/` 只命中 `>=` 子集断言）。；来源: grill-224-r1

- **决策**: D2「截断发生在出口投影、队列保留全文」的方向正确，与 #213 范式一致。；理由: `compact_summary()`（会话恢复注入，`manager.py:1492`）与 `max_messages` 的 drop-oldest 语义都依赖队列持有原文；入口截断不可逆且会污染这两条非模型面路径。；来源: grill-224-r1

- **决策**: 本 change **不影响 grill / review 门禁本身**，无死锁风险。；理由: `grep -rn "MessageBus\|subagent.bus\|snapshot_payload\|BUS_" scripts/ flow/` **零命中**——门禁脚本（`check_openspec_artifacts.py` / `workflow_guard` / `flow-policy.json`）完全不读 bus 出口；bus 的两条出口都不在 `scripts/` 的依赖图上。；来源: grill-224-r1

## Open Questions

- **Q1（阻塞性）：`ReadBus` 的**总量**仍然无界——本 change 只界住了「单条」，而 `max_tokens` / `limit` 两个参数都由调用方（模型）给，设计未给它们设界。** 具体场景：bus 满载 100 条、每条 30,000 字（`max_messages=100` 默认，`bus.py:65`）。
  - 现状（不改）：`ReadBus()` 默认返回 **1 条 / 4,070 字符**。
  - 按 design D2/D3/D8 落地后：`ReadBus()` 默认仍返回 **1 条 / 4,070 字符**（不变）；但 `ReadBus(max_tokens=10**9)` 返回 **100 条 / 404,428 字符**——单条被截到 4000 了，**总量反而比修复前的 172,703 更大**（因为单条截断后仍计入原 `token_count`，见 Q3）。
  - 也就是说：**同一个工具，父上下文被灌多少，仍由被检视方自己决定**——这正是 #213 在 `manager.py:82-88` 写下的「界不可被被检视对象影响」要禁的那件事。proposal 的验收标准写的是「**所有模型面出口**都不超过固定上限」，而按现 design 写出的契约测试（用默认 kwargs）会**绿着通过**，洞照旧。
  - 候选：(a) `read()` 同时钳**条数**上限（如 `min(limit or INF, BUS_SNAPSHOT_LIMIT)`）与**窗口**上限（如 `min(max_tokens, BUS_SNAPSHOT_LIMIT * BUS_PUBLISH_MAX_TOKENS)`），使两条 bus 出口同界；(b) 明确把本 change 收窄为「单条 bounded」，并把 proposal/spec 里「所有出口」「一律 bounded」的措辞改为「单条 bounded，总量仍由调用方参数决定」，同时**另开 issue** 记总量维；
  - 推荐 (a)：issue #224 的标题与 proposal 的核心主张就是「出口一律 bounded」，只修单条等于把 #213 的漏口换个坐标留下。

- **Q2（阻塞性）：`DeclareWorkflow` **不是** bus 的模型面出口——design D4 与 `specs/agent-runtime/spec.md` 的前提与代码不符。** 具体场景：父 agent 调 `DeclareWorkflow(spec=...)`。
  - 实跑 `DeclareWorkflowTool(manager).execute(spec={...})` → 返回键为 `['entry','goal','max_nodes','max_runs','nodes','recursion_limit','spec_hash','status','terminal','workflow_id']`，**`'bus' in output == False`**（`subagents.py:536-560` 手工构造固定 dict，从不调 `snapshot_payload()`）。
  - `scheduler.py:2955-2956` 的 `_envelope()["bus"]` 只经 `status()`（`scheduler.py:696-698`）→ `run()` 的返回值（`scheduler.py:768`）流出；而 `run()` 的返回值在两个模型面工具里都被**丢弃**（`subagents.py:620`、`subagents.py:835` 都 `await scheduler.run(spec)` 后改返回 `parent_envelope()`），第三条路径 `patterns.py:454` 交给 `_legacy_result`，后者只读 `envelope["nodes"]/["workflow_id"]/...`（`patterns.py:378-406`）**从不解引用 `envelope["bus"]`**。而 `parent_envelope()` 在 `scheduler.py:2973` 明确 `payload.pop("bus", None)`。
  - 结论：`RunPattern` 的 `result["bus"]` 唯一来源是 `patterns.py:458`。design D4 的「两个调用点同时受界」与 spec 的场景「DeclareWorkflow 声明期的 bus 快照同样有界」**描述了一条不存在的路径**——按现 spec 写出的回归测试无法构造（拿不到带 bus 的 Declare 返回体）。
  - 候选：(a) 把 D4 与 `agent-runtime` spec 的措辞改为「加固在 `snapshot_payload()` 本身（唯一模型面调用点是 `patterns.py:458`），并覆盖 `_envelope()` 这条当前不可达但同样未加固的路径作为纵深防御」；(b) 保留现有措辞但在 tasks 里明确「DeclareWorkflow 场景测试通过直接调 `scheduler.status()` 覆盖」。
  - 推荐 (a)：spec 是权威契约，写一条不可达路径的 Scenario 会在收尾 artifact checker / 审阅时被判为无法验证。

- **Q3：`read()` 截断后 `token_count` 是否同步？design 通篇未提，但它是 `read()` 唯一的预算记账字段。** 具体场景：一条 30,000 字消息，`estimate_tokens` = 7500（`bus.py:36-38`：`max(1, len//4)`）。
  - 按现 design（只截 `summary`、`token_count` 留原值）：`read(max_tokens=10)` 返回 `summary` 长 4000、`token_count=7500`、`summary_truncated=True`。调用方若按 `token_count` 累计预算，会把「实际 1000 token 的返回」记成 7500——**记账与实际返回体脱钩**；同时 `snapshot_payload()` 里同一条消息的 `token_count` 与 `summary` 长度也不再自洽。
  - 候选：(a) `read()` 返回前用截断后的文本重算 `token_count`（`estimate_tokens(summary)`），使记账与返回体一致；(b) 保留原值并在 `to_dict()` 里同时透出原值（如 `token_count_full`），让调用方能区分；
  - 推荐 (a)：`token_count` 在 `bus.py` 里本就是「这条消息占多少预算」的记账口径（`bus.py:93-95`），截断后仍报原值会让预算累计失真；(b) 引入第三个 token 字段，与「模型面数字越少越好」相悖。

- **Q4：`BUS_SNAPSHOT_LIMIT = 20` 的取值缺少预算推导，且与仓库既有父面投影口径不一致。** 具体场景：同一个 100 条满载 bus，两条父面出口同时暴露。
  - `snapshot_payload()` 按 D4：20 条 × 4000 字 ≈ **80,000 字符**。
  - 同仓库的图节点父面投影：`_PARENT_NODES_LIMIT = 200`（`scheduler.py:116`）× `_PARENT_FIELD_LIMIT = 200`（`scheduler.py:118`）= **40,000 字符**，并已被 `test_bounded_envelope.py:166` 用 `< 60_000` 钉住。
  - 即：bus 这一项的预算被定成既有父面投影的 **2 倍**，而 design D4 的理由只写了「已是能进父上下文的上限量级」——没有一个可检验的预算数字支撑「20」而非「10」或「40」。
  - 候选：(a) 把 20 对齐到既有父面预算（如 10，使 10×4000 = 40k 与节点投影同量级）；(b) 保留 20 但在 design 里补一句可检验推导（例如「父面新增注入预算 ≤ 80k，与节点投影 40k 合计 ≤ 120k，低于 #213 实测的 172k 的 70%」）；(c) 做成配置项（与 `subagents.workflow.aggregation` 同层）；
  - 推荐 (b)：改数字需要连带改 spec/测试；补推导成本最低，且能让后续审阅者判断这个数是否该调。

- **Q5：`test_read_returns_newest_when_single_message_exceeds_window` 的改造方案会让测试**失去判别力**。** 具体场景：现有输入是 `summary="x"*400` + `read(max_tokens=10)`（`tests/agent/subagent/test_bus.py:43-50`）。
  - `truncated` 的判据是 `len(summary) > 4000`：400 **不** > 4000 → 恒为 `False`。
  - `len(summary) <= 4000` 的断言：400 恒 ≤ 4000 → **恒真**。
  - 即：把 `summary == "x"*400` 换成「截断后长度 + 标志」（tasks.md:26-27）后，**把 `read()` 的截断实现整体删掉，这条测试仍然绿**——正好落进 tasks.md:39「参数教训」自己警告的坑，但该条只写在「测试」段末尾，没有落到这条具体测试上。
  - 候选：(a) 把该测试的输入从 400 提到 30,000（与 tasks.md:24 的其它新测试一致），再断言 `len(summary) <= TRANSCRIPT_ITEM_LIMIT` 且 `summary_truncated is True`，同时保留「最新一条仍可见」；(b) 拆成两条测试（原「超窗仍返回」语义 + 新的「截断」语义），各自用能判别的输入；
  - 推荐 (a)：一条测试同时覆盖两个语义、且输入真的越界，是与 tasks.md:24 同口径的最小改动。

- **Q6：`BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4` 与 `estimate_tokens` 的实际换算**不是**等价的，proposal 声称的「不存在双重截断」为假。** 具体场景：`estimate_tokens` 是 `max(1, len//4)`（`bus.py:36-38`），而发布侧闸门是**严格大于**（`subagents.py:265`：`if token_count > max_tokens`）。
  - 实推：`content` 长 **4001 / 4002 / 4003** → `estimate_tokens` = **1000**，不满足 `> 1000` → **不触发 summarize**，原文（4001–4003 字）直接 `bus.publish(summary=content)`。
  - 这比 `BUS_PUBLISH_MAX_TOKENS * 4 = 4000` **多出 1–3 字**，仍需 `read()` 再截一次 → proposal.md:62 的「发布侧与消费侧从此同界，不存在『发布侧承诺 ≤N、消费侧再截一次』的双重截断」不成立。
  - 候选：(a) 把闸门改成 `>=`（`token_count >= max_tokens`），使「阈值等于上限」时也 summarize，从而发布侧严格 ≤ 4000；(b) 钳到 `BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4` 时把闸门改为 `eprint`——即在 `execute()` 内对 `content` 先 `content[:BUS_MESSAGE_LIMIT]` 再走原逻辑；(c) 接受 3 字误差，但把 proposal.md:62 的措辞改成「两侧界在 ±3 字内一致」；
  - 推荐 (a)：一行改动、语义最直白（`estimate_tokens(content) >= max_tokens` → summarize），且不会像 (b) 那样在发布侧引入第二次截断。

## 风险

- **`read()` 若在共享对象上原地截断，会污染队列本身**——`read()` 目前把**同一个** `BusMessage` 实例放进 `collected`（`bus.py:126`），实测 `bus.read()[0] is bus._messages[0]` 为 `True`，改其 `summary` 会让 `bus._messages[0].summary` 同步变化、`compact_summary()`（`bus.py:137`）与 checkpoint 的 `bus_summary`（`manager.py:1492`）一起被截短。design D2（「队列保留全文」）与 D3（「read 返回截断后」）在实现上**互相冲突**，除非实现显式构造新 `BusMessage`（`dataclasses.replace(msg, summary=..., truncated=True)`）而非原地赋值。design 与 tasks 都未写明这一点，是最容易踩的落地坑。

- **`RunPattern` 返回体的主要放大项**不是** bus，本 change 修完后它仍可 165,763 字符**——实跑 `run_pattern(pattern="orchestrator-worker", params={"workers": 300, "worker_max_tokens": 100})`：总体 JSON **165,763** 字符，其中 `workers[]` **85,180**、顶层 `summary` **80,239**、`bus` 仅 **41**。`workers[]` 的条数由 `params["workers"]`（`patterns.py:81` `max(1, int(params.get("workers", 3)))`，无上限）决定，`_legacy_result` 再把 N 条 summary 拼成顶层 `summary`（`patterns.py:388-399`）——`BUS_SNAPSHOT_LIMIT=20` 一个字都碰不到这两项。本 change 标题限定为 bus 出口，「只修 bus」本身合理；但 `specs/agent-runtime/spec.md` 的 Requirement 措辞（「SHALL NOT 把无界子 agent 文本折进父上下文」）读起来像是对整个 `RunPattern` 返回体的承诺，**会误导后续读者以为 RunPattern 已 bounded**。建议在 spec 或 design 的 Non-Goals 里显式写明「`RunPattern` 的 `workers[]` / 顶层 `summary` 的条数维仍无界，另案处理」。

- **文档影响清单漏了真正命中的文件**——tasks.md:52 的关键词扫描清单是 `docs/`、`README.md`、`CONTEXT.md`、`docs/architecture.md`、`docs/agent-internals.md`，但实测与 bus 三层预算描述**强相关**的文件在 `docs/interview-bullets/` 与 `docs/interview-script/`：`docs/interview-bullets/interview-prep.md:219` 写「如果内容超过 400 token，自动调 LLM 做摘要再入队」（D5 落地后上限变 1000，事实漂移）、`:221` 写「单条超预算也保留最新一条」；`docs/interview-bullets/walkthrough.md:750-808` 直接贴 `MessageBus` 代码与 `result["bus"] = bus.snapshot_payload()`（`:808`）；`docs/interview-script/walkthrough/W03-multi-agent.md:40` 写「折叠到 `max_tokens`（默认 400）以下再发」；`docs/interview-script/questions/Q08-multi-agent.md:49` 写「`MessageBus`（53 行）」而 `bus.py` 现为 147 行（改动前已漂移，本次会更远）。AGENTS.md 把 interview-script 同步列为「建议性」，但 `interview-prep.md` / `walkthrough.md` 里被本 change 直接改变的事实（发布侧上限 400 → 1000、`to_dict()` 新增 `summary_truncated`）属于「当前变更造成的事实变化」，按 AGENTS.md 文档影响检查规则应更新。

- **`docs/openspec-change-backlog.md:144` 已把常量值写死进 backlog 描述**（含 `BUS_SNAPSHOT_LIMIT = 20` / `BUS_PUBLISH_MAX_TOKENS = BUS_MESSAGE_LIMIT // 4`）。若 Q4/Q6 的取值调整，backlog 那条文本必须同步，否则收尾时会留下一处与最终实现不符的登记。

- **`_summarize` 的降级路径不受 `BUS_MESSAGE_LIMIT` 约束**——`subagents.py:280` 与 `:289`、`:291` 的降级分支返回 `content[: max_tokens * 4]`，其长度只由 `max_tokens` 决定（D5 钳到 1000 后即 4000）；但 `LLMSummarizer.summarize` 的 `budget` 在 `agent/context/summarizer.py:33-35` 被**显式声明为「advisory token target … not a hard guarantee」**，`agent/context/summarizer.py:169-172` 也只把它拼进 prompt（「Keep the summary under approximately {budget} tokens」）。即 LLM 摘要**可能超过 `max_tokens`**，发布侧对这条路径没有硬界——本 change 的单条界实际由消费侧 `read()` 兜底。这不违反验收标准（消费侧确实界住了），但 design D5 把发布侧描述成「两侧同界」是不准确的：发布侧对 LLM 摘要分支**只有建议、没有保证**。

- **`PublishBusMessageTool` 的回包本身是第三条模型面出口，design 未纳入清单**——`subagents.py:274` 返回 `msg.to_dict()`，即订阅者自己刚发布的那条（含 `summary`）。D5 钳住 `max_tokens` 后它 ≤ 4000 字，因此**没有新增漏洞**；但 proposal 的「出口盘点」表（proposal.md:16-21）只列了 4 条，这条是第 5 条，且它正是 D5 生效与否的直接观测点，建议在 design 的出口清单里补一句「发布回包经 D5 钳制后与单条上限同界」，以免审阅者再按 4 条盘点时漏看。

- **常量 parity 的机械锁定在 tasks 里只是「有测试」，未指定形式**——tasks.md:33 要求「`BUS_MESSAGE_LIMIT == TRANSCRIPT_ITEM_LIMIT` 有测试机械锁定」。若按 D7 的回退方案（inline `BUS_MESSAGE_LIMIT = 4000` + parity 测试），该测试必须真的 import 两侧常量比较；若按 D1 主方案（`from agent.subagent.manager import TRANSCRIPT_ITEM_LIMIT`），该测试是**恒真**的（派生关系使然），此时它锁的其实是「派生关系没被改成字面量」——两种情形下测试的判别对象不同，tasks 应写明按哪条路径落，否则收尾审阅时无法判断该测试是否真的在锁东西。

## User Confirmation

- **Q1**: 用户答复：ReadBus 总量维一并钳死（采纳推荐）。read() 的 max_tokens / limit 钳到与 snapshot_payload 同界的上界，「出口一律 bounded」的主张才成立，只修单条等于把 #213 的漏口换个坐标留下。；确认时间: 2026-09-21
- **Q2**: 用户答复：改为「界 SHALL 施加在 snapshot_payload() 方法本身」的措辞（采纳推荐）。spec 去掉不可达的 DeclareWorkflow 场景，测试直接调 MessageBus.snapshot_payload() 断言有界，再补一条 run_pattern 端到端；scheduler._envelope() 作为纵深防御路径在 Non-Goal 写明。；确认时间: 2026-09-21
- **Q3**: 用户答复：同步为截断后的值（采纳推荐）。截断过的消息用 estimate_tokens(截断后文本) 重算 token_count，使记账与返回体一致；read() 内部挑消息的预算窗口仍按原始 token_count 累计（更保守，不影响正确性）。；确认时间: 2026-09-21
- **Q4**: 用户答复：保留 BUS_SNAPSHOT_LIMIT = 20，补写可检验的预算推导（采纳推荐），不改成 10。在 design 的 D4 里补上「父面新增注入预算 ≤80k 字符，与节点投影 40k 合计 ≤120k，低于 #213 实测 172k 的 70%」这类可检验推导。；确认时间: 2026-09-21
- **Q5**: 用户答复：拆成两条测试（不采纳「单条输入提到 30000」的推荐）。一条保留 test_read_returns_newest_when_single_message_exceeds_window 的原「超窗仍返回最新一条」语义（输入 400 字，不涉截断，断言保持 summary == "x"*400）；另一条新写「截断」语义（输入 30000 字，断言长度 ≤ TRANSCRIPT_ITEM_LIMIT 且 summary_truncated 为 True），两条各有判别力、职责分明。；确认时间: 2026-09-21
- **Q6**: 用户答复：发布侧闸门由严格大于改为大于等于（采纳推荐）。if token_count >= max_tokens 时即触发 summarize，使发布侧严格 ≤ 单条字符上限，消除 4001-4003 字带的双重截断，proposal 的「两侧同界」措辞据实成立。；确认时间: 2026-09-21
