# Proposal: 群聊 everyone 模式无限讨论轮（停止按钮 + 安全阀参数）

关联跟踪 issue：[#333](https://github.com/Xingkai98/asterwynd/issues/333)（【feature】群聊 everyone 模式支持无限讨论轮（停止按钮 + 安全阀参数））。

## Change Type

- primary: feature
- secondary: []

## Why

群聊 `reply_mode = everyone` 当前的行为：用户发一条消息 → 全体成员按序各得一次发言机会 → 本轮结束 → 必须等用户再发一条才能继续（`agent/team/orchestrator.py:315-341` 的 `submit_user_message` 是唯一开轮入口；`:347-407` 的 `_run_round` 走完 slot 即收尾；`:428-434` 的 `_drive` 线性遍历）。

这**不是缺陷而是首版刻意的收紧**：`openspec/changes/archive/2026-10-13-web-agent-group-chat/design.md:131` 明确声明「本 change **不**允许成员自行开轮次（参照实现允许、上限 3，`ds-bot/.../constants.js` `ROOM_BOT_ROUNDS`）。理由：无人值守的 Web 面板下，成员互开轮次会放大成本且无用户在场收敛」；规格亦钉死「系统 SHALL NOT 在用户再次发言前自行开启新一轮」（`openspec/specs/multi-agent-collaboration/spec.md:1304`）。

用户现在要求收回这条分歧：像真实群聊一样，成员自动连续多轮讨论，直到**讨论自然收敛**（某轮全员静默）或用户点**停止讨论**；同时保留现在的"单轮"形态，房间级可切换。因此本 change 新增「讨论链（discussion chain）」语义，并把成本控制从"禁止续轮"换成"有界收敛 + 安全阀 + 用户停止"。

## What Changes

- **房间级讨论模式**：`Room.discussion_mode` 新增字段，取值 `single`（默认，现状）/ `unlimited`；仅 `reply_mode = everyone` 时允许 `unlimited`（与 `admin` 组合为非法配置，REST 400）。
- **讨论链**：`unlimited` 下一轮正常结束且本轮有人发言，自动开启下一轮（无需用户消息），每轮每名成员仍各得一次机会、自行决定发言或 `[PASS]` 静默；**某轮全员静默（0 条成员发言）即自然收敛，链结束**。
- **停止讨论**：房间 WS 消息 `stop_discussion` + REST 端点；语义为**优雅停止**——当前成员回合跑完后结束当前轮、不再续轮；无活动讨论时幂等 no-op。
- **用户插话不打断**：讨论链进行中用户发消息照旧进房间日志、行首 `@` 插到当前位次之后，讨论链继续。
- **安全阀参数**（`asterwynd.yaml` 的 `team:` 节，可配置）：讨论链最大轮数、最大成员回合数、最大墙钟秒数；默认取用户拍板的 10 倍档（200 轮 / 600 回合 / 6000 秒）。任一到达即停止并写 `system`。
- **事件契约**：`round_ended` 增加 `chain_id` / `round_index` / `chain_continues` / 新终止值 `stopped`；新增 `discussion_started` / `system_entry`（链内 `system` 条目实时广播）/ `discussion_stop_requested` / `discussion_ended`（携带 `chain_id`、结束原因、已完成轮数、进入轮数、总回合、耗时；每链至多一次）。
- **Web UI**：房间设置增加「讨论模式」下拉（仅 everyone 可选 unlimited）；房间工具栏增加「停止讨论」按钮；状态文案区分「讨论中（第 k 轮）/ 讨论已收敛 / 讨论已停止 / 讨论达安全上限」。
- **规格同步**：MODIFIED `multi-agent-collaboration` 的「房间级互斥与轮次终止」与「房间应答模式」；MODIFIED `web-ui` 的「人设与房间的管理入口」+ ADDED「群聊讨论链状态与停止讨论控件」；ADDED `configuration` 的「群聊讨论链安全阀可配置」（当前 `configuration` 规格没有任何 `team:` 运行参数 Requirement，不能写 MODIFIED）。
- **兼容性**：`discussion_mode` 缺省 `single`，旧房间记录、既有规格与既有测试行为不变。

## Capabilities

### Modified Capabilities

- `multi-agent-collaboration`: 扩展「房间应答模式」加入 `discussion_mode`；重写「房间级互斥与轮次终止」——房间认领覆盖整条讨论链、新增第四出口「用户停止」、新增链级安全阀与收敛语义；新增「讨论链自动续轮」Requirement。
- `web-ui`: 房间设置新增讨论模式字段、房间视图新增停止讨论控件与讨论状态文案；扩展房间级 WS 事件契约（`discussion_started` / `discussion_stop_requested` / `discussion_ended`，`round_ended` 扩展字段）。
- `configuration`: `team:` 运行参数新增 `discussion_max_rounds` / `discussion_max_turns` / `discussion_max_seconds`，含缺省值、校验与配置示例。

## Dependencies

- 复用既有：群聊编排器（`agent/team/`）、房间事件总线与房间 WS（`web/team.py`、`web/server.py`）、`TeamConfig` 配置解析、前端群聊 pane（`web/static/group.js`）。
- 无新增第三方依赖、无新协议、无新服务。

## Impact Analysis

| 影响面 | 内容 | 处置 |
| --- | --- | --- |
| 模型/持久化 | `Room.discussion_mode` 新字段；旧房间 JSON 缺字段按 `single` 读 | `agent/team/models.py` 增字段 + `to_dict`/`from_dict` 兼容；store roundtrip 测试 |
| 编排器 | 轮次驱动改为「讨论链」驱动；房间认领覆盖整链；新增停止、续轮判定、安全阀、收敛 | `agent/team/orchestrator.py` 重构 `_run_round` → `_run_discussion` + per-round `_run_round`；单轮模式走同一循环（只跑一轮） |
| 配置 | `TeamConfig` 三个新参数 + 解析/校验；`asterwynd.yaml` 文档示例 | `agent/config.py`、`asterwynd.example.yaml`、`tests/agent/test_config.py` |
| Web API/WS | 房间 create/patch 校验 `discussion_mode`；停止讨论 REST；房间 WS 新增 `stop_discussion` 消息；`room_state` 增加讨论态 | `web/team.py`、`web/server.py`、`tests/web_tests/test_group_chat_server.py`、`test_group_chat_team.py` |
| 前端 | 设置下拉、停止按钮、状态文案与事件处理 | `web/static/group.js`、`web/static/index.html`、`web/static/style.css`；JS/浏览器测试 |
| 当前规格 | `openspec/specs/{multi-agent-collaboration,web-ui,configuration}/spec.md` | 本 change 的 spec delta；收尾时同步 + `current_spec_synced` 事件 |
| 开发文档 | `docs/architecture.md` 群聊小节（轮次终止口径已过时：会写"仅用户开轮"）；`CONTEXT.md` 词汇表补「讨论链」 | 同步为讨论链口径；不扩大改动面 |
| backlog | `docs/openspec-change-backlog.md` 登记本 change，收尾时移除 | `backlog_updated` 事件 |
| 测试面 | 编排器讨论链（续轮/收敛/停止/安全阀/插话/取消）、模型与配置、REST/WS 契约、前端状态文案 | 见 design 的 Test Plan；每条都先红后绿 |
| 成本 | `everyone` 单轮 = N 次模型调用，无限链放大 | 默认 `single`；安全阀可配；提示词显式要求收敛即 `[PASS]`；用户可随时停止 |
| 风险 | 模型不愿收敛导致长链烧钱；停止语义与 WS 取消竞态；事件契约破坏旧前端 | 安全阀 + 停止按钮 + 默认关闭；cancel teardown 单测；事件只做增量扩展 |
| 回滚 | 需要回到"仅用户开轮"：把房间 `discussion_mode` 置回 `single`（或回滚本 PR） | 数据层向后兼容，无需迁移脚本 |

## Reference Implementation Research

research_tier: full
status: enabled
reason: 本 change 收回首版对参照实现的**故意分歧**（成员自行开轮），属于非平凡行为/规格变更且走 grill；需核对参照实现的轮次自启动语义、业界多 agent 群聊框架的终止条件实践，避免把"无限讨论"做成无界烧钱循环。

research questions:
- 参照实现（DS Bot）如何允许 bot 自行开轮次？上限与终止条件是什么？
- 业界多 agent 群聊框架（如 AutoGen）如何约束自动讨论的终止？是否有"全员安静即结束"的成熟口径？
- 本仓既有轮次语义（slot、`@` 接力、`[PASS]` 静默、房间互斥、三出口）在加入"链"之后哪些契约必须保留？

findings:
- **参照实现对照**：DS Bot 的群聊轮次由 `ds-bot/src/host/groups.js` 驱动，本轮既有研究记录其允许成员自行开轮次、上限 `ROOM_BOT_ROUNDS = 3`（见 `openspec/changes/archive/2026-10-13-web-agent-group-chat/design.md:131` 与同 change 的 `reviews/grill-adversarial.md` Issue 12：原引用 `ds-bot/src/host/constants.js:53-54`，constants 里有注释「Rounds Bots may start in one group by posting, before the user speaks there again」）。**本轮复核（2026-10-24）用 GitHub API 读取上游 `Fei2411/DeepSeek-Bot` 当前 HEAD**：`ds-bot/src/host/constants.js` 已无 `ROOM_BOT_ROUNDS`（同位置现为 `ROOM_MODES` / `ROOM_NAME_MAX` / `ROOM_NOTICE_MAX`），代码搜索 `ROOM_BOT_ROUNDS repo:Fei2411/DeepSeek-Bot` 返回 0 命中，`groups.js` 中只剩建群 kickoff 轮次（`round.kickoff`，`:245,433,752`），即上游已演进出不同的轮次模型。⇒ 参照证据按**历史引用**（归档 design / grill-adversarial 的原始行号与注释）采信，不按当前上游 HEAD 声称"照着抄"；本 change 不复制其实现，只确认"成员自行续轮"在同类实现中确有先例，且本仓首版是**更保守的有意分歧**。
- **本地参考仓库**：`.dev/reference-repos.txt` 在当前工作区不存在（`docs` 规定的本地参考仓库路径未配置），`ds-bot` 本地克隆不可用。按仓库规则如实记录该不可用事实，替代依据 = GitHub API 读取的上游源码 + 归档 change 内的历史引用行号。
- **业界框架的终止实践**：AutoGen AgentChat 把自动讨论的终止做成**显式终止条件**（`MaxMessageTermination`（消息数上限）、`TextMentionTermination`、`TimeoutTermination`、`ExternalTermination`（外部停止）等，可组合），而不是任其自循环；参见 [autogen_agentchat.conditions](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html) 与 [AutoGen Termination 教程](https://microsoft.github.io/autogen/0.4.1/user-guide/agentchat-user-guide/tutorial/termination.html)。同类多 agent 群聊实现也普遍是「显式上限 + 外部终止信号」组合（如 [swarms GroupChat](https://pypi.org/project/swarms/15.0.2/)）。**外推边界（如实声明）**：AutoGen 是"消息数上限"单档；本设计是 rounds / turns / seconds 三档，且 `max_turns` 与 `max_rounds` 在 3~5 人 everyone 房下**并不独立**（每轮回合数 ≥ 成员数、且可被成员互相 `@` 接力放大到「成员数 + extra_turns + admin_extra_turns」；`max_turns` 在绑定意义通常先到，但上报 reason 时多被 `round_limit` 吸收，见 design Decision 6）——因此只借"显式终止条件组合"这一形态，不把 AutoGen 的档位设计当作本设计的依据。
- **上游结论的可复核性（如实声明）**：`ROOM_BOT_ROUNDS` 已从上游当前 HEAD 消失这一结论，来自 2026-10-24 用 GitHub API 读取 `Fei2411/DeepSeek-Bot` 的源码（`constants.js` / `groups.js` + code search 0 命中），**无法从本仓内复核**；归档 change 的行号引用属历史引用。因此本 change 只在"同类实现确有成员自行续轮先例、本仓首版为更保守的有意分歧"这一层采信，不依赖上游现状细节。
- **本仓既有契约**（代码调研，非泛读）：槽位序列与 `@` 接力（`agent/team/orchestrator.py:153-192,731-769`）、`[PASS]` 静默哨兵（`:501-504`）、房间级互斥与三出口（`:315-341,347-434`）、成员状态表（`:559-599`）、事件经房间总线转发（`web/server.py:663-750`）、配置注入（`web/team.py:200-209`）。这些是讨论链必须保留的外壳；本 change 只扩展"链在轮之上"。

design impact:
- 采纳「显式终止条件组合」：**全员静默收敛**（业务出口）+ **用户停止**（外部出口）+ **安全阀（轮数/回合/墙钟）**（硬出口），而非无界循环；默认关闭（`single`）保证成本默认不放大。
- 否决直接照搬 `ROOM_BOT_ROUNDS` 的"固定 3 轮"形态：用户要求的是"直到自然收敛或手动停止"，固定 3 轮不满足；且上游该常量已消失，不复刻。
- 房间互斥从"单轮"提升为"整条讨论链"，否则讨论链轮间窗口会被用户消息误判为"新一轮"而与续轮并发；`round_ended` / 新 `discussion_ended` 事件分层让前端区分"一轮结束"与"整条讨论结束"。
