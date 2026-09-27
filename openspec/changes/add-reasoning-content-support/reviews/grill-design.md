# Design Grill: add-reasoning-content-support

> 独立零记忆 grill（issue #95）。所有结论来自本次亲自读到的代码与亲自跑出的结果，
> 不采信 `design.md` 自述。代码引用均为 worktree 内当前 `file:line`。

## Confirmed Decisions

- **决策**：D1/消息模型形态 ——`ReasoningBlock[]`（每段 `text` + 可选 `opaque`）优于单字符串 + 旁挂签名。
  依据: 亲自读 `agent/message.py:92-142`，现有 `Message` 是扁平 dataclass，`reasoning_content: Optional[str]`（`message.py:98`）确实表达不了「一段文本 + 一段 opaque」的多段组合；`to_dict/from_dict`（`message.py:103-142`）是手写字段级映射，加数组字段的改动面可控。而 `_build_payload`（`anthropic_llm.py:139-154`）已经按 `content_parts` 列表逐块拼装 assistant content，结构化段正好能映射成 thinking/text/tool_use 的顺序序列。

- **决策**：D5/事件隔离 ——reasoning 增量必须走独立事件，不能复用 `assistant_delta`。
  依据: `web/static/chat.js:573-583` 的 `assistant_delta` 分支把 `data.delta` 交给 `appendAssistantContent`（`chat.js:823-831`），后者**把 delta 累加进 `body.dataset.markdownSource` 并整体重渲染 markdown**。若思维链混入该事件，会被当作 markdown 正文持久写进 `markdownSource`，无法再拆出——design D5 的「必须独立事件」判断经代码验证成立。

- **决策**：D7/自愈前提 ——错误体不被包装、且流式路径也能读到 body。
  依据: `anthropic_llm.py:457` 非流式走 `response.raise_for_status()`（普通 response，body 可读）；流式走 `BaseLLM._stream_events`（`llm.py:125-153`）的 `async with client.stream(...)` + `response.raise_for_status()`。实测（httpx 0.28.1，本次用 MockTransport 复现）：即便在 streaming 上下文里，捕获到的 `httpx.HTTPStatusError.response.text` / `.content` **仍可读**（`httpx.ResponseNotRead` 未触发），body 为 `{"error":{"message":"...thinking..."}}`。注意错误体在 `error.message` 里，不在顶层。

- **决策**：D2 子结论 ——「最新 assistant 轮必然存活于 compaction 的 recent 窗口」在本仓库默认配置下成立。
  依据: 亲自跑 `MemoryManager._recent_with_tool_chains`（`memory/manager.py:371-389`）：`recent_window` 默认 10（`manager.py:82`），生产三处构造均为默认（`agent/main.py:288`、`benchmarks/agent_runner.py:385`、`web/session.py:1588`、`agent/subagent/manager.py:1307`）。实测 recent_window∈{10,2,1} 时最新 assistant 都在 `recent` 中；只有 `recent_window<=0` 才会落进被摘要改写的 `middle`。但这只保护「不丢」，不保护「不重写」——见 Open Questions Q5。

- **决策**：opaque 逐字节不变 ——在 JSON 往返层面成立（前提是不对它跑 `_strip_surrogates` / 不改写）。
  依据: 亲自跑：`json.dumps(..., ensure_ascii=False)` + `.encode("utf-8")`、以及 `ensure_ascii=True` 路径，base64 类签名与非 ASCII 签名往返均 `==` 原值（`agent/session.py:214-220` 的 `_write` 用 `ensure_ascii=False`；`session.py:237-239` 的 `_hash_dict` 用 `sort_keys=True` 只影响字段序不影响值）。真正会破坏字节一致的是 `agent/anthropic_llm.py:24-26` 的 `_strip_surrogates`：实测它把 `\ud800` 替换成 `�`（不等），所以实现里**绝不能把 opaque 走这条函数**。

## Open Questions

> 每条都是停轮项。请主 session 逐条转达用户，`- **Q<n>**` 编号与 design.md 的 Q1–Q4 对齐，Q5–Q9 为本次 grill 新增。

- **Q1（对应 design Q1，字段命名与旧数据兼容）**：新字段用 `reasoning` 数组、旧 `reasoning_content` 保留为「只读兼容」还是「改名为数组」？
  例子：现有一个旧会话 `sessions/abc/messages.json`（`agent/session.py:113` 读这个文件）含
  `{"role":"assistant","content":"...","reasoning_content":"我之前在想..."}`
  - 选 (a)：`Message.from_dict`（`message.py:120-142`）收到旧字段时把它包成一个 `ReasoningBlock(text=值, opaque=None)`；新写入 `to_dict` 只输出 `reasoning`。旧会话照常加载，但**同一份持久化里会长期存在两种字段名**，`_hash_dict`（`session.py:235-240`）去重哈希因字段集变化会触发一次重写。
  - 选 (b)：`from_dict` 读旧字段后**立即规范化为 `reasoning`**，下一次 `save` 就把该会话文件改成新格式（旧版本 asterwynd 再打开会因 `reasoning_content` 消失而丢 reasoning 回传）。
  请用户选边：(a) 旧文件永不改写，或 (b) 一次性升级旧文件。

- **Q2（对应 design Q2，多段 thinking 的展示粒度）**：一个响应里 Anthropic 给出多段 thinking 时，前端折叠区合并成一个还是每段一个？
  例子：某轮 content 数组为 `[thinking("先看文件A", 签名A), thinking("再看文件B", 签名B), tool_use(Read), text("已改完")]`。
  - 选 (a)：折叠区标题「思考过程」展开后显示「先看文件A\n\n再看文件B」——简洁，但用户看不出这是两段独立推理（在 interleaved thinking 场景下，段边界对应两次不同工具决策，是有信息量的）。
  - 选 (b)：每段一个折叠区——保真，但一份回复里可能冒出 3–5 个折叠块，正文被挤下去。
  请用户选边（design 推荐 (a)；本条我确认「存储必须分段」无争议，只问展示）。

- **Q3（对应 design Q3，是否本 change 一并做「关 thinking」开关）**：本 change 只做采集/回传/展示，还是顺带做关闭开关？
  例子：用户当前拿 `deepseek-v4-flash` 跑「把 a.py 里 3 改成 4」，实测**不传任何参数**也会先产出数百 token 思考（proposal Why 第 12 行），这些 token 计入 output 计费。加开关要多处理一个反馈耦合：`anthropic_llm.py` 采集侧要能区分「本轮被要求关」，`_build_payload` 回传侧（`anthropic_llm.py:139-154`）要同步不带，否则触发官方「禁用 thinking 后当轮再传 thinking 会失败」的陷阱。
  请用户选边：(a) 另立 issue（范围小），或 (b) 本 change 一起做（范围变大）。

- **Q4（对应 design Q4，compaction 丢旧轮的边界）**：compaction 对旧轮 reasoning 是「无条件丢弃」还是「保留但可被摘要改写」？
  例子：历史 5 轮 assistant（各带 thinking），`compact_if_needed`（`agent/loop.py:987`）触发，`compact`（`memory/manager.py:305`）执行 `msgs[:] = system + [summary_msg] + recent`——**注意这一行把 `middle` 的整套 Message 对象直接丢弃**，只留摘要文本。被丢进 middle 的旧轮 assistant 的 reasoning 段随之消失（这正是 D6 想要的）。真正要用户拍板的是：`recent` 里那几条 assistant 的 reasoning 要**原样保留**（实现上要保证 `recent` 列表是同一批对象、不被 `_annotate_pending_calls`（`manager.py:409-454`）在此路径上拷贝改写），还是允许被摘要版本替换。
  请用户确认：recent 窗口内的 reasoning **原样保留**（推荐），还是允许被改写。

- **Q5（新增：D6 的「最新轮必留」与 D2 的「默认全带」在 compaction 后自相矛盾，需用户裁决）**：compaction 重写历史后，被摘要掉的那些旧轮，下一轮请求到底带不带 reasoning？
  例子：历史 8 轮 assistant 全带 thinking，compaction 把前 6 轮压成一条 user 摘要消息。新历史里只剩「摘要 user + recent 里的 1–2 条 assistant(+thinking)」。
  - `design.md:103` 的边界说「保证被改写后仍是带 thinking 的最新轮」，暗示**允许改写**；
  - 但 `design.md:99` 又说旧轮 reasoning「可安全丢弃」、`design.md:61-66`（D2）说默认**全带**——如果实现是「所有存活的带 reasoning 的 assistant 轮都回传」，那 compaction 之后只有存活的 recent 轮带 reasoning，**这在语义上已经不是「全带」了**。
  这不只是措辞：DS-Anthropic 端点实测要求回传 `content[].thinking`，而官方对「更早轮可省」的容忍度在 **DS 侧未验证**（proposal 的实测结论是「不回传就 400」，但没区分「最新轮不回传」与「旧轮不回传」）。
  请用户裁决：(a) compaction 后只回传存活的 recent 轮 reasoning（接受「全带」降级为「存活的都带」）；(b) compaction 时**保留所有 survived 轮的 reasoning 且不去重**，尽量贴近官方「全带」语义；或 (c) 先按 (a) 实现，把 DS 侧「旧轮可省」的验证列为实现期必做实验（若 DS 也 400 则回退到 (b)）。

- **Q6（新增：D2 的「全带不挤占上下文窗口」在 keep-all 模型上是错的，需用户决定是否改口径 + 加清理策略）**：D2 理由 3（`design.md:65`）写「上下文窗口计算里历史轮 thinking 会被剔除——即全带不会挤占上下文预算」。我查证这条**只在 last-turn-only 模型成立**，对 keep-all 模型是反的：Opus 4.5+ / Sonnet 4.6+ / Fable 5 / Mythos 5 这类 keep-all 模型，历史轮 thinking **会留在上下文窗口、按 input token 计费**（官方「thinking block preservation by model」「preserved thinking」文档）。
  例子：用户用 keep-all 模型跑长会话，10 轮各带 2k token thinking，全带策略下每轮请求都把这 20k thinking 一起发上去，**按 input 计费并占窗口**——与 D2 的「成本可控」论断相反。
  请用户裁决：(a) 把「全带」改成「最新轮必带 + 更早轮默认不带」（省 token，且官方明确更早轮可省）；(b) 保持全带，但改用 beta 的 `clear_thinking_20251015` 上下文编辑策略只保留最近 N 轮（本仓库 `anthropic_llm.py:52-58` 的 `_get_headers` **目前完全没有 `anthropic-beta` 头**，需要新增）；(c) 保持全带且不做清理，仅修正 design 文档口径（接受成本）。
  这条直接推翻 design.md R2/理由 3 的一处事实，建议优先裁决。

- **Q7（新增：keep-all 模型的 prefix binding 让 D6「旧轮可丢」也不安全，需用户确认退路）**：在更新的模型上（Fable 5.1 / Opus 5.5），thinking block 被**绑定到精确的对话前缀**（system + tools + 之前每一条消息），**编辑任何更早历史都会让签名失配**，默认直接 400（新组织默认 hard 400）；官方给的退路是 beta 头 `thinking-binding-controls-2026-08-01` + `thinking.block_binding.prefix_mismatch_behavior: "drop_block"`。
  例子：compaction 在 keep-all + prefix-binding 模型上把早前消息替换成摘要 user 消息 → 前缀变了 → 下一轮请求里 recent 保留的 thinking 签名失配 → 400。`design.md` 的 D7 自愈**只匹配错误文案**，没有覆盖「前缀绑定」这种结构性失效，且 `_get_headers` 没有 beta 头通道。
  请用户裁决：(a) 本 change 增加 beta 头 + `drop_block` 配置作为主要的等第退路（并在 D7 里补上这条策略），还是 (b) 只保留文案匹配式自愈（接受在 keep-all + prefix-binding 模型上会 400）。

- **Q8（新增：D7 自愈的降级粒度——全局禁用还是本轮禁用）**：命中 signature 相关 400 后，「移除历史 thinking 重试并持续不带」的作用域是什么？
  例子：DS-Anthropic 端点某一轮因 signature 失配报 400。若按 Claude Code 的策略「该对话后续请求持续不带」，则当前 session 后续所有轮都不再回传 thinking——但 DS 端点**本来就要求回传**，持续不带会把「一轮失败」放大成「整个会话余下全部 400」。若只「本轮不带、下轮恢复带」，则若根因是持久性的（签名真失配），会**每轮都重试一次、每轮都 400 一次**，浪费一轮往返。
  请用户裁决：(a) 本轮重试 + 记录一个 session 级「本会话禁用 reasoning 回传」标志（并在 UI/debug 上可见）；(b) 本轮重试 + 只丢弃失败轮的 thinking block、其他轮照带；(c) 其他。

- **Q9（新增：spec delta 里两条 Scenario 目前无法机械验证，需确认测试口径）**：
  (1) `agent-runtime/spec.md:39-44`「无 reasoning 的 provider 行为不变」——要求「请求体与响应处理 SHALL 与未引入本能力时逐字段一致」。例子：现在 `_build_payload` 对无 reasoning 的 assistant 消息产出 `[{"type":"text",...},{"type":"tool_use",...}]`（`anthropic_llm.py:139-154`）；引入结构化段后，若实现改成「只要有 `reasoning` 字段就先插 thinking block」，无 reasoning 时应仍然逐字段一致。这条**可以**用固定 payload 快照测，但需要用户确认「快照对比」是否算合格验收（还是只要求「不含 thinking 键」）。
  (2) `web-ui/spec.md:25-30`「单击标题行切换展开」——例子：`chat.js` 目前**没有** `<details>`/`summary` 用法（grep 零命中），也没有现成的折叠组件，落点要自建 DOM + 事件。浏览器回归（tasks 2.7）要能以「点击标题行 → 该区文本可见 → 再点 → 文本不可见」断言。请用户确认这条可作为机械验收（而不是只能人工肉眼）。

## 挑战记录

### 经得起推敲的

1. **`signature` 必须是独立 opaque 字段**（D1）— 成立。`_build_payload`（`anthropic_llm.py:139-154`）当前把 assistant 消息拆成 `text` + `tool_use` 两类块，**没有任何承载「既有文本又有不可展示载荷」的位置**；且顺序被硬编码为 text 先于 tool_use（`anthropic_llm.py:141-153`）。若把 signature 硬塞进某个字符串字段，回传顺序与原文一致性无法保证。结构化段 + 明确的「thinking 段按原序输出」是必要的。
2. **事件隔离**（D5）— 成立，见 Confirmed Decisions。
3. **opaque 的 JSON 往返（不含 surrogate）** — 成立，见 Confirmed Decisions。
4. **D7 的前提「无 body 包装」** — 成立，且流式/非流式都能拿到错误体，见 Confirmed Decisions。
5. **D1 候选 C（存 provider 原生 dict）应予否决** — 成立。`_hash_dict`（`session.py:235-240`）对每条消息 `json.dumps` 参与去重哈希，原生 dict 结构会让哈希与 provider 强耦合（同一逻辑状态因 provider 字段差异被判为「变了」而反复写盘）；且 `Message.from_dict`（`message.py:120-142`）无法在不知道 provider 的情况下反序列化原生 dict。
6. **「无 reasoning 时不产生字段」在本仓库有天然的兼容位** — `to_dict`（`message.py:103-118`）已经遵循「字段为 None/空则不写」的约定（`tool_call_id`/`reasoning_content` 都如此）。新的 `reasoning` 字段延续这个约定即可满足 spec 的「无则不产生」。

### 被证伪或有漏洞的

1. **【证伪】D2 理由 3「历史轮 thinking 会被剔除，全带不挤占上下文预算」（`design.md:65`）过度外推到所有模型。**
   官方区分两档：keep-all 模型（Opus 4.5+ / Sonnet 4.6+ / Fable 5 / Mythos 5）历史 thinking **留在窗口、按 input 计费**；只有 last-turn-only 模型才自动剔除。本仓库默认模型含 `claude-sonnet-4-20250514`（`anthropic_llm.py:45`），是会剔除的老模型，**碰巧能跑通，但一旦用户升到 keep-all 模型即失效**。→ 转成 Open Question Q6。
   来源：[claude-wiki thinking guide（官方文档镜像）](https://raw.githubusercontent.com/johnzfitch/claude-wiki/refs/heads/master/04-API-Reference/Guides/build-with-claude-thinking-03550646e4.md)、[Claude 平台 preserved thinking 文档](https://platform.claude.com/docs/en/build-with-claude/preserved-thinking.md)。

2. **【重大漏洞】D6 说「最新轮必留」，但 compaction 实际实现会重写/丢弃整个 middle，且 `recent` 列表里的对象可能被 `_annotate_pending_calls` 拷贝重建。**
   - `compact`（`memory/manager.py:305`）最终执行 `msgs[:] = system + [summary_message] + recent`，**middle 的 Message 对象整体消失**——若某轮 assistant 的 reasoning 落在 middle（recent_window<=0 时可能，默认不会），直接丢失。
   - 更隐蔽的路径：`_decorate_for_summary`（`manager.py:474-499`）调用 `_annotate_pending_calls`（`manager.py:409-454`），后者在 `pending` 非空时 `Message(...)` **重新构造一条 assistant 副本**，并显式搬运 `reasoning_content=m.reasoning_content`（`manager.py:447-453`）。引入结构化 `reasoning` 后，**这处构造函数如果不显式搬运新字段，decorated middle 的 reasoning 会丢**——但这段 decorated 副本只进摘要 prompt、不回写 messages，所以它是「摘要看不到 reasoning」而非「回传丢 reasoning」。真正的风险在 `recent` 侧：需确认 `recent` 是同一批对象、`msgs[:] = ... + recent` 是引用复用（看起来是），且实现新模型时不能在该路径重建对象。
   - 结论：D6 的「最新轮必留」是**设计意图**而非**现状保证**，实现必须显式约束并在测试里固定。→ 转成 Q4/Q5。
3. **【重大遗漏】D2 的「默认全带」与 D6 的「旧轮可丢」在 compaction 后语义冲突**（见 Q5）。design 没有写清 compaction 之后「全带」的集合到底是哪些轮，也没验证 DS-Anthropic 端点对「旧轮省略」的容忍度。
4. **【遗漏】design 完全没提 prefix binding / beta 头通道**（见 Q7）。`anthropic_llm.py:52-58` 确认 `_get_headers` 里没有 `anthropic-beta`，D7 也没有对应的结构性退路。
5. **【遗漏】design 没提 `build_history_payload`（`web/session.py:42-65`）这个重连重绘路径。**
   它把消息映射成 `{"role":..., "content": extract_text(message.content)}`——**只取 `content`，结构化 reasoning 完全不在 payload 里**。这意味着：重连后 `renderHistory`（`chat.js:708-720`）重绘历史时**看不到 reasoning**，用户重连后之前那条消息的折叠区会消失（或初始就不渲染）。Tasks 里 `3.7 web/server.py` 只提「转发 reasoning 增量事件」，**没有覆盖历史重绘**——而历史重绘的改动点在 `web/session.py`，不是 `web/server.py`（`web/server.py:444` 只是调用方）。→ 见新增/修正建议。
6. **【遗漏】design 的 Impact Analysis（proposal 第 87-100 行）列了 `web/server.py` 却漏了 `web/session.py` 的 `build_history_payload`**，而后者才是重连补发的实际拼装点。
7. **【证据不足】D3「OpenAI 路径既有回传行为不变」缺少对「空 reasoning 会不会被发出」的检查。**
   `_message_to_dict`（`openai_llm.py:264-265`）用 `if msg.reasoning_content:`（**真值判断**）——空串不写。结构化段实现后若改成 `if msg.reasoning:`（列表真值），需保证空列表同样不写，否则无 reasoning 的路径会凭空多出 `"reasoning":[]`，违反 spec `agent-runtime/spec.md:39-44` 的「逐字段一致」。
8. **【证据不足】D2「先全带、靠 D7 自愈兜底」把两条路径的安全边界混在了一起。**提案第 23-40 行的 400 风险是针对 **DS-Anthropic 端点的 id 启发式**；官方 Anthropic 规则是针对**签名顺序**。两者不是同一失败模式，自愈文案也不同（`thinking must be passed back` vs `bound to a different conversation` / `prefix mismatch`）。D7 需要至少两套匹配规则。

### 调查过的但确认无碍的

- **`LLMStreamEvent` 新增类型不破坏既有消费方**：`chat.js:486-487` 的 `switch (event.type)` **没有 `default` 分支**（全文件 grep `default:` 零命中），未知 type 不匹配任何 case、不执行任何分支，效果即静默忽略；`agent/loop.py:1142-1162` 对 `event.type` 是 `if`/`if` 两分支（`assistant_delta` / `complete`），新类型同样不匹配、不改变控制流。→ D5 可安全新增。
- **benchmark 不消费 reasoning**：`benchmarks/agent_runner.py` 的 `CountingLLM`（`agent_runner.py:267-283`）通过 `__getattr__` 全透传，`chat` 只是计数包装；`benchmarks/workflow_replay.py` 记录的是 workflow spec（不是消息），reasoning 不进入回放面。→ tasks 4.6 的 smoke 不会因本 change 变化。
- **`agent/trace_recorder.py`**：`record_completion`（`trace_recorder.py:228`）只记 `content`（字符串），不回传消息体；trace 不落 reasoning 也可以（因为它不是「回传面」）。→ 不是必然影响面，但值得在文档同步时提一句「trace 不含 reasoning」。
- **`cost_tracker.py`**：只按 `input_tokens`/`output_tokens` 计费（`cost_tracker.py:58-63`），reasoning 已包含在它们里，**无需改动**。
- **`agent/subagent/manager.py`**：子 agent 通过 `message.role` + `extract_text(message.content)` 投影（`subagent/manager.py:119-149`），不走 reasoning 字段。若将来要让子 agent 的 reasoning 也回传，它自身的 AgentLoop 会自然处理（同一个 `_build_payload`）。→ 本 change 无必然改动。

## 新增/修正建议

1. **重写 D2 的成本理由，并把「全带」重新定义清楚（对齐 Q5/Q6）。**
   建议把 D2 的一句「官方文档说会被剔除」替换为分模型的准确表述，并显式写出「全带 = 所有**当前存在于 messages 中且带 reasoning** 的 assistant 轮都回传」（而非「原始全部历史」），以消除与 D6 的冲突。推荐实现档位：全带 + 在 keep-all 模型上可配置 `clear_thinking_20251015`（见 Q6）。

2. **把「opaque 不得经 `_strip_surrogates`」写成显式不变量并加测试。**
   现在 `_strip_surrogates`（`anthropic_llm.py:24-26`）被用于所有文本路径（`anthropic_llm.py:143,336,483,514,578,583,595,599`）。若实现时顺手把 assistant 的 thinking 文本走这条函数，**包含 surrogate 的签名会被替换成 `�`**（实测不等），直接破坏 spec 的「逐字节不变」。建议：`ReasoningBlock.opaque` 单独存原始值、序列化时不进任何清洗函数，并加一条「含非 ASCII/特殊字符的 opaque 往返 == 原值」的回归。

3. **补 `web/session.py:build_history_payload` 到影响面与 tasks。**
   建议 tasks 3.7 从「`web/server.py` 转发事件」扩为「`web/session.py` 的 `build_history_payload` 带 reasoning（历史重绘）+ `web/session.py` 的 `on_event` 转发 reasoning 增量」。否则重连后折叠区会消失。`chat.js:506` 的 `renderHistory` 需要对 `message.reasoning` 做渲染，且要沿用 `currentAssistantMsg = null` 的重置语义（`chat.js:510`）。

4. **D7 需要至少两套匹配规则，且要记录「禁用」状态的作用域（对齐 Q7/Q8）。**
   建议 D7 里明确列出要匹配的文案族：(a) `thinking.*must be passed back`（缺回传）；(b) `bound to a different conversation` / `prefix` mismatch（签名/前缀失配）。并新增 D7 的 beta 头通道（`_get_headers` 目前不带 `anthropic-beta`）。

5. **D6 落成可测的不变量。**
   建议把「最新轮必留」改写为可机械验证的三条断言：(i) compaction 后 `messages` 中最后一条带 `reasoning` 的 assistant 消息的 `reasoning` 等于压缩前同一条的值；(ii) 若 `pending` 非空触发 `_annotate_pending_calls`，其重建的 Message 必须保真搬运 `reasoning`（否则摘要路径丢信息）；(iii) `recent` 列表里的 assistant 对象是同一引用（不被重建）。tasks 2.5 应把这三条都覆盖，而不只是「压缩后最新轮 reasoning 仍在」。

6. **spec delta 的可测性补强。**
   - `agent-runtime/spec.md:39-44`「逐字段一致」建议改成可机械验证的「请求体快照对比」（固定 messages 输入 → 序列化后的 payload 与基线逐字段相等），否则「逐字段一致」容易被解读成「只要不含 thinking 键」。
   - `web-ui/spec.md:41-46` 的「折叠态静默累积」当前 Scenario 只断言「展开后能看到完整内容」——建议补一条「折叠态收到增量时，`<details>`/容器的 `content` 已包含该文本但不可见」的断言，避免实现成「折叠态丢弃增量、展开时重拉」这种不满足流式语义的写法。

7. **Proposal/Tasks 影响面补漏。**
   `proposal.md:87-100` 的代码影响表建议补 `web/session.py`（history payload + on_event）与 `agent/memory/manager.py:447-453`（annotate 重建处的字段搬运）；`docs/agent-internals.md:604,736` 与 `docs/lessons-learned.md:21` 已经记录了 `reasoning_content: Optional[str]` 和「必须原样回传」的口径，收尾阶段要同步更新（tasks 5.2 已列，但漏了 `docs/lessons-learned.md`）。

## User Confirmation

> 停轮确认记录（2026-09-27）。以下为用户对各 Open Question 的明确答复。

- **Q1**: 用户答复：**保留旧字段只读**（选项 a）。`Message.from_dict` 读旧 `reasoning_content` 时包成一个 reasoning 段；新写入只输出 `reasoning`；旧文件永不被改写。确认时间: 2026-09-27
- **Q2**: 用户答复：**合并成一个折叠区**（选项 a）。存储层仍分段（无争议），展示层把所有段文本按序拼接进同一个折叠区。确认时间: 2026-09-27
- **Q3**: 用户答复：**先不搞关闭 thinking 的开关**（选项 a 变体）。本 change 只做采集/回传/展示；关闭能力不在本次范围（原选项 (b) 一并做被否决）。确认时间: 2026-09-27
- **Q4/Q5**: 用户答复：**按推论实现**。recent 窗口内的 reasoning 原样保留（对象引用不重建、不摘要改写）；被压缩掉的旧轮 reasoning 随消息对象自然消失。即「全带」= 所有当前存活且带 reasoning 的 assistant 轮都回传。并加回归测试固定不变量。确认时间: 2026-09-27
- **Q6**: 用户答复：**全带 + 留清理通道（业界标准）**。默认全带（保缓存命中，与 Claude Code 同构）；另新建 `anthropic-beta` 头通道，提供 `clear_thinking_20251015` 上下文编辑能力（`keep` 参数可配）在需要时回收窗口。用户先追问「业界对于 keep-all 模型咋做的」，在收到业界事实（keep-all 历史 thinking 占窗口并按 input 计费；官方明示「留着=缓存命中、清掉=缓存失效」；Claude Code 不手工裁剪而靠 context-editing）后选择此选项。确认时间: 2026-09-27
- **Q7**: 用户答复：**一并加 drop_block**。既然 Q6 要建 beta 头通道，顺带配置 `thinking.block_binding.prefix_mismatch_behavior: "drop_block"`（beta 头 `thinking-binding-controls-2026-08-01`）作为主动退路，而非等 400 再靠文案匹配。确认时间: 2026-09-27
- **Q8**: 用户答复：**本轮降级 + 记状态**（选项 a）。本轮去掉 thinking 重试；若再失败则记 session 级「本会话禁用 reasoning 回传」标志（debug/UI 可见）。确认时间: 2026-09-27
- **Q9**: 用户答复：未单独提问（属测试口径的实现细节，由 agent 按可机械验证标准决定）：采用「请求体快照对比」验证「无 reasoning 时逐字段一致」；折叠区采用 DOM 断言（点击标题行 → 文本可见 → 再点 → 不可见）。确认时间: 2026-09-27
