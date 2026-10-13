# Grill: web-agent-group-chat 设计追问

## Reviewer

- run id: paseo-grill-web-agent-group-chat
- 时间: 2026-10-12
- 方式: 零记忆独立审阅；逐条把 `design.md` 的断言拿真实代码核实（不是复述 design 自述）；参照实现按 `proposal.md` 声明的路径实际打开比对（`/home/shared/agent-study/dsh-bot-research/DeepSeek-Bot-main/ds-bot/`）。

## Confirmed Decisions

- **决策**: 人设承载走「一人设一 `AgentSession`」可行，且人设指令有现成注入面——建 session 后调 `AgentSession.init_messages(<人设指令>)`，值落到 `agent._user_system_prompt`，随 `SessionSnapshot.user_system_prompt` 落盘、随 resume 回灌，不需要新运行时。；理由: 这是「长期人设」语义的必要条件（指令必须跨重启可恢复），现成机制已完全满足，Decision 1 的复用面判断成立；来源: paseo-grill-web-agent-group-chat（`web/session.py:1378-1380`、`agent/loop.py:223`、`agent/loop.py:713-714`、`agent/session.py:27`）

- **决策**: 群聊编排器与既有 DAG 调度器并列新建（Decision 3）成立。调度器节点种类是封闭四值（`subagent` / `foreach` / `aggregate` / `route`），没有任何交互节点、轮次节点或「图跑完再追加节点」的入口；把「轮次 + `@` 接力 + 用户中途插话」塞进 DAG 会同时破坏两套语义。；理由: 代码证据是决定性的，且与 tasks 3.3「新增会话式群聊编排器」一致；来源: paseo-grill-web-agent-group-chat（`agent/subagent/scheduler.py:1722-1732`）

- **决策**: 「单聊/群聊内容不耦合」在会话层与事件层是**结构性保证**，不是需要额外防护的性质：`run_lock` 与 `event_channel` 都是 per-`AgentSession`，单聊 tab 与房间 WS 各自 attach 到不同 session 的通道，不存在跨 pane 事件串流；`chat.js` 也是每 tab 一条 WebSocket。；理由: 这澄清了 design「群聊内容意外泄漏进单聊」这条风险的真实边界——真正的泄漏面在记忆/资产等**跨会话共享存储**，不在会话通道；来源: paseo-grill-web-agent-group-chat（`web/session.py:1359`、`web/session.py:1367`、`web/session.py:1770-1780`、`web/static/chat.js:436`）

- **决策**: 群聊「静默（PASS）」首版用「提示词约定哨兵文本 + 解析 run 的最终 content」，不新增控制工具。；理由: 参照实现的真实机制就是这个——成员被要求 `Reply [PASS] to stay silent`，由宿主解析文本；本仓也没有 `Pass` 类控制工具先例（`agent/tools/builtin/` 无同类），而新增工具会污染所有既有 agent 的工具面，哨兵文本只影响群聊会话的 system prompt；来源: paseo-grill-web-agent-group-chat（参照实现 `ds-bot/src/host/groups.js:99`；本仓工具清单 `agent/tools/builtin/`）

- **决策**: 每轮发言预算采用参照实现的形态：一轮上限 = 成员数 + 固定额外轮次（群有 admin 时再加固定额度），并按成员分别计数封顶。；理由: 这是「防成员无限互相应答」的最小可实现、可测约束，且已有可移植的具体形态与数值，优于 design 里「上限待定」的空洞表述；来源: paseo-grill-web-agent-group-chat（参照实现 `ds-bot/src/host/groups.js:24-25`、`ds-bot/src/host/groups.js:262`、`ds-bot/src/host/constants.js:54`）

## Code-Resolved Questions

- **Q1（原 Open Question）**: 结论 **全新独立模块，不扩 `SubAgentManager`**。三条代码级否证：(a) 它的 child session 由**父 `AgentLoop` 拥有**——`AgentLoop.__init__` 构造时就调 `configure_runtime(llm=...)` 把它绑到父 loop，人设会话不该挂在某个父 loop 之下；(b) 它的 child system prompt 是硬编码的「你是一个受限的子 agent。按任务目标完成工作并汇报结果。」，写死在两处，与「长期人设指令」语义直接冲突；(c) 它没有 `SessionStore` 会话快照，`_sessions` 是进程内存字典，只有 run 级 checkpoint 落盘（走 `.asterwynd/subagents/<run_id>/`）——与「长期、可跨进程恢复、面向用户」不符。；证据: `agent/subagent/manager.py:470`、`agent/subagent/manager.py:580`、`agent/subagent/manager.py:817`、`agent/loop.py:167`、`agent/subagent/snapshot.py:1-10`

- **Q2（原 Open Question）**: 结论 **在既有 `PersistentMemory` 上加 persona 维（同一个 store 类，细分目录布局），不另起独立 store**；但**必须先修一个现存缺陷**：Web 路径今天**完全没接** persistent memory——`_create_session` 调 `build_default_tool_registry` 与 `AgentLoop` 时都没传 `persistent_memory`（该参数两处都支持），于是 `SaveMemory` / `RecallMemory` / `SearchMemory` 三件工具退化到工厂默认的**项目级**实例 `PersistentMemory(policy.workspace_root, ...)`，而 `MemoryIndexSource` 拿到 `None` 直接返回空串（Web 里的 agent 读不到任何记忆索引）。照现状给 N 个人设建 session，所有 `SaveMemory` 会写进**同一个项目级记忆目录**，spec delta 的「不同人设的人设级记忆 SHALL NOT 互相检索到」直接挂掉。另注意 `agent/tools/builtin/memory.py` 有 5 处 `_get_memory()` 兜底 `PersistentMemory(Path.cwd())`，只要有人设 session 忘了注入实例，就会静默写回项目作用域。；证据: `web/session.py:1648-1664`、`web/session.py:1674-1688`、`agent/tools/factory.py:202`、`agent/tools/factory.py:319-327`、`agent/tools/factory.py:353-359`、`agent/tools/builtin/memory.py:69-72`（另 130-133、183、254、318 同型）、`agent/context/sources.py:295-297`、`agent/memory/persistent.py:180-185`

- **Q3（原 Open Question）**: 结论 **Chief/admin 是被指派的普通人设（可指定、可多个），不是系统内置不可删角色**。依据是本 change 自己声明的参照实现的真实形态：`mainBotIds` 只是 roster 上的一个 id 列表（「团队可以有不止一个 Main Bot，`list_bots` 会标出它们」），群 admin 是**群属性**（建群者默认当 admin，也可指定别人），所以连「群主」都可以是任意成员，没有内置角色的必要。；证据: 参照实现 `ds-bot/src/host/prompt.js:25-36`、`ds-bot/src/client/sources.js:19,21`、`ds-bot/src/client/bot-settings.js:201`

- **Q4（原 Open Question，机制部分）**: 结论 **「懒构造 + 有上限」中的「懒构造」不是可选项而是必须项，这部分可以定死**。理由是每个 `AgentSession` 的构造成本包含：一次 `build_mcp_manager()` → `connect_from_config()`（会起 MCP server 子进程并挂健康监控任务）、一份自带独立并发额度（`max_active` 默认 5、`max_queued_runs` 20）的 `SubAgentManager`、一份 sandbox + 完整工具注册表 + `SkillRuntime`。全量常驻 = 人设数 × 上述全部；且 "Web 一 session 一 loop" 的现状里，全局**没有任何**会话/标签页数量上限可当现成闸门（全仓无 `max_sessions`/`max_tabs` 类配置），上限必须新引入。剩给用户取舍的只有「上限数值 / 是否暴露配置项」——见 Open Questions。；证据: `agent/mcp/manager.py:364-376`、`web/session.py:1531`、`web/session.py:1648-1671`、`agent/subagent/manager.py:479-499`、`agent/config.py:403-418`

- **Q5（原 Open Question，部分）**: 结论 **「引用另一段对话作为上下文」在本仓没有可复用 primitive，且参照实现的做法不可移植**。DS Bot 的 relay 会话根本不调模型——它在宿主 `llm/stream` 钩子里**合成**一个 `group_relay` 假工具调用（`block-start` / `tool-call-delta` / `finish(tool-calls)` 三段）来驱动成员发言；本仓 `HookManager` 只有生命周期观察钩子（`on_run_started` / `before_iteration` / `after_llm_call` / `before_tool_execute` / `after_tool_execute` / `on_error` / `on_completion`，全部返回 `None`），`AgentLoop` 直接驱动 LLM，没有「拦截并替换模型输出」的流层扩展点。所以「照抄 relay 架构」这条路可以直接判死；是否在 v1 做跨会话引用则降级为纯范围取舍（见 Open Questions）。另：本仓 `Message` 没有 timestamp / speaker 字段，`build_history_payload` 只发 role，跨会话拼接时间线也没有现成依据。；证据: 参照实现 `ds-bot/src/host/groups.js:493-518`；本仓 `agent/hooks/manager.py:15-64`、`web/session.py:1677`、`agent/message.py:147-155`、`web/session.py:62-94`

## Open Questions

- **Q4（收窄后）**: 首版默认**人设数量上限**取多少，以及是否暴露为配置项？（机制半边已由代码证据定死：必须懒构造 + 必须有上限，因为全量常驻 = 人设数 ×（MCP 子进程 + 独立 subagent 并发额度 + 工具注册表），而全局没有任何现成上限闸门。剩余取舍：具体数值、是否算上「每群 × 每成员」的群内会话数、超过上限时的行为是拒绝创建还是排队。）
- **Q5（收窄后）**: 首版是否排除「引用另一段对话作为上下文」（DS Bot 的 `+` → Reference）与「群共享 notice」？（两者在本仓都没有可复用 primitive，参照实现的 relay 架构不可移植，因此这是纯范围取舍：做则要为跨会话读取新开一个受限只读工具面，不做则记入 Non-Goals。）

## 风险

- **[设计必须改] 决策 4 的前提写错了**：design 把「人设级记忆」写成「在既有 `PersistentMemory` 之上引入人设维、只做作用域维度扩展」，`proposal.md` 的 Dependencies 也写「可复用：… per-loop `persistent_memory`（`agent/loop.py:132`）」。事实是 Web 路径**一次都没有传过** `persistent_memory`（`web/session.py:1648-1688`），Web session 今天没有任何长期记忆——`MemoryIndexSource` 拿到 `None` 返回空串。「再加一个 scope 维」实际是「先补 Web 的接线，再加维度」，且接线方式会直接改变**既有单会话 Web 行为**（一旦给普通 session 也注入记忆索引，其上下文就多了一块 `## Project Memory`）。设计必须明确：是只给人设会话接线，还是同时给普通 Web 会话接线；后者要评估既有 web-ui 测试与提示词稳定性回归。
- **[设计必须改] 缺少「房间日志」这一权威数据的设计**：spec delta 要求「后发言的成员 SHALL 能看到本轮此前已发布的内容」、`web-ui` delta 要求「按发言人区分不同 agent 的消息」，但 `Message` 没有 timestamp / speaker 字段（`agent/message.py:147-155`），`build_history_payload` 只发 role（`web/session.py:62-94`）。也就是说，重连后无法靠合并 N 个 per-session 历史还原一条有序的群时间线。design 只在 Decision 3 里提了一句「把产出写回房间日志」，没有房间日志的 schema、持久化位置、与成员会话历史的权威关系，也没有把「本轮此前内容如何注入下一成员会话」写成机制（参照实现是`groupSessionFor` 给每个成员一个固定 brief + 每轮把房间日志切片作为消息注入）。这一块缺失会让 tasks 2.2/2.5 无法写出可执行断言。
- **[设计必须改] 编排器落在哪一层没定，存在反向依赖**：`proposal.md` 的 Impact Analysis 把人设/房间模型与编排器放在 `agent/`（如 `agent/team/`），但成员会话是 `web.AgentSession`、驱动入口是 `web.SessionManager.run_session`。本仓分层是单向的 `web/ → agent/`（`agent/` 只在 CLI 入口函数内延迟 import `web.server`，`agent/main.py:684`）。把编排器放进 `agent/team/` 再调 web 层就是反向依赖。设计必须给出接口形态（编排器依赖一个「能跑一个会话并拿回最终文本」的抽象，由 web 层实现/注入），否则实现时会临时发明分层。
- **[设计必须改] 会话标识与可见性未定**：`new_session_id()` 是 `uuid4().hex[:12]` 随机值（`agent/run_identity.py:6-7`），`SessionSnapshot` 没有任何 kind/persona/room 字段（`agent/session.py:15-38`），而 `SessionStore.list_sessions()` 会枚举该 workspace 下**全部** session 目录（`agent/session.py:146-206`）并由 `GET /api/sessions` 直接暴露给 hub（`web/server.py:320`）。不处理的话：人设单聊会话与每个 (人设, 群) 会话都会以普通会话身份出现在 hub 会话列表里，且用户可用 `DELETE /api/sessions/{id}`（`web/server.py:334`）删掉人设会话的底座快照。设计必须给出「人设 → 单聊会话 id」「(人设, 群) → 群内会话 id」的稳定映射与 hub 过滤/标记口径。
- **[设计必须改] 群聊里的 pending 交互（审批/提问）没有设计**：成员 run 走的是同一套 `_create_session`，会装上 `WebApprovalHandler`（默认 600s 超时、fail-closed）与 `WebQuestionHandler`（默认 300s），`agent-runtime` 规格要求 AgentLoop 中介审批类工具调用。一个无人值守的群聊轮次里，成员一旦触发审批或 `AskUserQuestion`，整轮会阻塞到超时（最长 600s）才继续。设计要么把房间 WS 接上这些 pending 交互并按成员区分来源，要么在群聊会话里显式降级（禁掉 ask 类工具 / 缩短超时）。；证据: `web/session.py:1630-1637`、`agent/config.py:398-399`、`web/session.py:444`
- **[设计必须改] 「渲染 per-pane 化」的依据是错的，会误导实现**：design 与 proposal 都称前端「现为全局单会话假设（`web/static/chat.js:71-77`）」。`chat.js:71-77` 确实是模块级 DOM 引用，但它们**已经被 per-tab 重绑**——`createTab` 每条 tab 持有自己的 `messagesEl`/`ws`/`currentAssistantMsg`，`bindActiveTab` 切换时把模块级变量指向该 tab 的 DOM（`chat.js:211-244`），且 `web-ui` 规格里已有「Web UI 支持多标签会话」与「多标签页瞬态交互状态按标签页隔离」两条 Requirement。真正的工作是新增一种 **pane 类型 + 新 WS 协议**（`chat.js:436` 把 URL 写死成 `/ws/${sessionId}`，`web/server.py:402` 的路由也只认 session），不是「把全局单会话改成 per-pane」。按错误前提实现会做无用重构。
- **[设计必须改] 参照实现研究的证据链有误**：`proposal.md` 用 `agent/subagent/manager.py:470` + `agent/subagent/snapshot.py:3` 论证「子 agent session 仅内存」。`snapshot.py:1-10` 恰恰说明 subagent 的 run checkpoint **是落盘的**（`.asterwynd/subagents/<run_id>/`，复用 `SessionStore`）。结论（不复用 `SubAgentManager`）仍成立，但支撑它的三条正确理由应换成 Q1 里那三条代码级否证（父 loop 拥有 / 硬编码受限 prompt / 无会话快照）。同一段的「无 persona/roster 抽象」「Web 假设一 session 一 AgentLoop」两条经核实为真（`web/session.py:1335-1346`）。
- **[新增风险] 跨人设的隐式信息通道不止记忆一处**：workflow 资产库是**仓库级共享**的（`~/.asterwynd/projects/<hash>/workflow-assets/`，规格 `openspec/specs/multi-agent-collaboration/spec.md:703-720`，实现 `agent/subagent/workflow_assets.py:26-38`），且资产索引默认注入每个 loop 的上下文（`agent/loop.py:155`，默认 `True`）。只要人设能 `SaveWorkflowAsset`，人设 A 存的资产就会出现在人设 B 的上下文里——「人设间隔离」的验收若只测 `PersistentMemory` 会漏掉这条。建议在 spec delta 里显式声明「资产库是共享面」或按人设分桶，别让它成为未声明的泄漏。
- **[新增风险] 同一人设的单聊与群聊会并发写同一份记忆**：会话分离保证了两个不同 session，但同一个人的记忆目录是**一份**（这正是需求）。这会带来两个后果：一是 `PersistentMemory` 的可逆写保护是 `git commit-before-write`，`_git_commit` 在 git 缺失/提交失败时**抛 `RuntimeError` 中止写入**（不是降级），并发写会命中「nothing-to-commit 之外」的竞态；二是每个 `PersistentMemory` 实例各有一份 `_last_decay_run`，衰减扫描会在同一目录上重复跑。设计应明确「必须共享同一个 `PersistentMemory` 实例」还是「允许每会话一份实例但有并发写保护」，并把「同一人设单聊/群聊并发写记忆」写进测试矩阵。
- **[新增风险] `long-term-memory` 没有被列为本 change 的 modified capability**：proposal 的 Capabilities 只声明 `multi-agent-collaboration` 与 `web-ui`，但 Decision 4 实质改变了记忆的作用域模型，而既有规格明写「长期记忆系统 SHALL 用 project/repo scope 标记记忆，SHALL 在项目间强制 scope 隔离」（`openspec/specs/long-term-memory/spec.md:76`）。加一个 `specs/long-term-memory/spec.md` 的 delta（MODIFIED Requirement）比在 `multi-agent-collaboration` 里加一条「人设级长期记忆」更贴合能力域边界；checker 不校验 capability 声明与 `specs/` 目录的一致性，正因如此漏声明不会报错、只会漂移。
- **[新增风险] 参照实现调研少覆盖两个同主题插件**：`/home/shared/agent-study/dsh-bot-research/` 下除 `DeepSeek-Bot-main` 外还有 `dsh-adrian-agents-group-work-main` 与 `dsh-agent-group-main`（名字直指 agent 群组/群工作）。design 只研读了 DS Bot 一家。RIR 是 `full` 档，建议至少花 15 分钟核对另两家在「轮次终止条件 / 静默机制 / 成本上限」上的分歧点，避免把 DS Bot 的早期形态当成业界唯一形态。
- **[新增风险] 群聊的「轮次终止」既不在 design 也不在 spec delta 里可测**：spec delta 只写了「至多一个成员在发言」「不发言则推进到下一个成员」「达到上限不再追加」，没有定义一轮什么时候**结束**、下一轮何时开始、用户消息是否开启新一轮、轮次上限到达后是静默停止还是回报用户。参照实现是「上限 = 成员数 + 固定额外轮次」且「用户再说话才开新一轮」，建议照此写进 spec delta，否则 tasks 2.2 的「轮次顺序」测试没有可断言的成功/终止条件。
- **[低风险] 群成员循环内的 `@` 接力缺少可测定义**：spec delta 只说「管理员 SHALL 能点名其他成员」「被 `@` 的成员成为下一个发言者」，没有规定点名**不在成员列表**的人、点名**多个**人、点名自己、以及 `@` 出现在句中（非开头）时的行为。这类边界不定义，实现会各自发明，回归测试也写不出边界用例。

## 停轮说明

- 本记录留下 **2 条 Open Questions**（Q4 名额上限数值 / Q5 首版范围），均需用户拍板；机制半边的判定已移入 `## Code-Resolved Questions`，不再占用停轮队列。
- 用户答复后应记录进本文件新增的 `## User Confirmation` 节（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`，占位文本不计入）；该节待答复时创建。
- `## Open Questions` 未全部确认前，不得开始写实现代码或测试代码。

## User Confirmation

- **Q4**: 用户答复：首版默认会话数上限取 **50**，**超出排队**（不拒绝）；口径为会话数 = 人设数 ×（1 + 群数）。；确认时间: 2026-10-12
- **Q5**: 用户答复：原 Q5 已拆为两问并均拍板——**做**「群共享 notice」（细化见 Q5a）、**不做**「引用另一段对话作为上下文」（细化见 Q5b）。；确认时间: 2026-10-12
- **Q5a**: 用户答复：首版**做**「群共享 notice」（房间模型加 `notice` 字段，每个成员发言前注入群级共享指令）。；确认时间: 2026-10-12
- **Q5b**: 用户答复：首版**不做**「引用另一段对话作为上下文」（记入 Non-Goals；不新开跨会话只读工具面）。；确认时间: 2026-10-12
- **Q6**（记忆粒度，2026-10-12 追加确认）: 用户答复：记忆**每个群独立**——同一人设的单聊 / 群 A / 群 B 各一份、互不可见（与 DS Bot 的「每 bot 一份、跨会话共享」为**故意分歧**）；不同人设之间亦隔离。；确认时间: 2026-10-12
- **Q7**（记忆 review 触发，2026-10-12 追加确认）: 用户答复：采用「**每人自己发言后 review 自己 + 静默成员落后补齐**」（= DS Bot 的 `agent/status` idle 触发 + `queueLaggingMembers` 兜底）；非「每轮所有人都 review」。；确认时间: 2026-10-12

