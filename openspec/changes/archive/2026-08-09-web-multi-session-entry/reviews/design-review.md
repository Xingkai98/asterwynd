# Design Review: web-multi-session-entry (Round 1)

## Reviewer

- run id: `b5515634-0bdd-4c80-b10f-15c9a4d52a76`
- 时间: 2026-08-09
- 范围: 独立零记忆设计审阅。只读设计文档与相关代码，仅产出本审阅记录，未修改任何其他文件。

## Verdict

**CHANGES_REQUESTED**

## 逐项审阅

- **需求覆盖**: proposal 的 5 项需求、6 项非目标、验收标准在 design 中均有对应决策（D1 覆盖 hub 列表、D5 覆盖多标签、D3 覆盖按 workspace 分区存储与恢复、D2 覆盖新建指定 mode/workspace、D6 覆盖恢复优先级、D5 覆盖删除）。验收标准中"删除"一项存在实现缺口（见 I1）。无明显的范围蔓延：新增的 per-session run 互斥、host 默认改 127.0.0.1、reset 保留 workspace/mode 均来自已确认的开放问题与验收标准，属合理收口。proposal Impact Analysis 提到 uploads"不涉及"，design D7 采纳 grill Q2 推荐保持全局，一致。
- **决策可行性**: D1-D8 代码引用逐一核对基本准确：`list_sessions`（agent/session.py:143-182 按 updated_at 倒序）、`_create_session` 的 `initial_mode` kwarg（web/session.py:307-315）、`WorkspacePolicy(workspace_root=...)`（agent/workspace_policy.py:140-147）、`AgentLoop.session_store` 注入点（web/session.py:364）、`remove_session`（web/session.py:379-382）、reset 位置（web/server.py:424-433）、`--host` 默认 `0.0.0.0`（agent/main.py:661）、`_resolve_workspace`（agent/main.py:201-211）、`run()` 无 running guard（agent/loop.py:493-527）、chat.js 全局单例（chat.js:4-29）、恢复逻辑（chat.js:1430-1434）、debug.js `iterBlocks`（debug.js:6）、uploads `workdir` 参数（agent/uploads.py:92-156）均与真实代码一致。D8 用 `acquire_nowait()` 消除 check-then-act 竞态的设计正确。**两处未闭环**：(a) 会话删除只有前端按钮与 `remove_session` 签名改动，没有服务端 API 设计与实现任务（I1）；(b) resume 无 workspace 时命中 allowlist store 后，resumed session 的 `workspace_root`/`session_store` 归属未明确，会破坏"会话归属 workspace"不变量（I2）。
- **安全性**: `resolve_workspace()`（expanduser().resolve() + 有效集合成员判断）覆盖 `/api/sessions`、`/ws/new`、`/ws/{id}?workspace=` 三个入口，能防 `..`、符号链接、尾部斜杠；Linux 下大小写不构成绕过；空 allowlist 时有效集合 = {主 workspace}；主 workspace 由 `_resolve_workspace` 强制存在（main.py:208）。session_id 穿越由 `SessionStore._validate_session_id`（agent/session.py:196-203）兜底。0.0.0.0 + bypass 的远程暴露面已由 Q1 确认改默认 127.0.0.1 缓解。**未发现可绕过的安全漏洞**。但 design.md D4 中"本决策不改变 0.0.0.0 默认"的残留语句与已确认的 Q1 决策矛盾（I3），需修正以防实现时误读。
- **Spec 对齐**: delta（specs/web-ui/spec.md）新增 6 项 ADDED requirement + 1 项 MODIFIED，与现有 `openspec/specs/web-ui/spec.md` 无直接冲突；delta 声明的新行为（hub API、/ws/new mode/workspace、allowlist 拒绝、per-session 互斥、多标签、删除、恢复优先级）都有对应 tasks。**两处问题**：(a) MODIFIED 的"Web session 本地持久化与恢复"只保留了 2 个 scenario，丢掉了原规格的"run 结束后自动落盘""进程重启后按 id 恢复""未知 session id 回退新建"3 个 scenario，其中"未知 id 回退新建"在 delta 中无任何覆盖，属规格覆盖回退（I4）；(b) 删除 requirement 声明了行为但 delta 未定义请求机制（与 I1 同源）。
- **测试策略**: 后端集成测试与 Playwright smoke 覆盖了主路径（hub、多标签、新建、互斥、恢复、删除、跨 workspace、负向路径校验）。**盲区**：(a) 前端最高回归风险的 per-tab 隔离（审批/问题卡片、图片上传、reconnect、slash 匹配）没有 Playwright 用例，grill R5 已明确列出这些跨 tab 串扰点但测试清单未落地（I5）；(b) `/ws/{id}?workspace=` 非法 workspace 的拒绝路径与负向测试缺失（I6）；(c) "裸 `/ws/new` 仍保留 --resume 语义"这一回归点无测试（I5）；(d) resume 命中 allowlist store 后 re-run 落到正确 store 的集成测试未排（与 I2 同源）。
- **文档/门禁**: backlog 已登记（docs/openspec-change-backlog.md 未实现队列 #6，关联 issue #117）；grill-confirmation-gate 满足——13 项 Open Questions 全部在 grill-design.md `## User Confirmation` 有实质答复与确认时间；workflow-events.jsonl 覆盖了受保护 artifact 改动（docs/openspec-change-backlog.md 有 backlog_updated 事件；change 目录与 reviews/** 为豁免路径）；tasks.md 规格节 1.1-1.6 勾选诚实（1.7 未勾选，符合当前设计阶段）；Impact Analysis 无残留 unknown/TBD/待确认；Reference Implementation Research 完整（status/reason/questions/findings/design impact 齐备，并记录本地参考仓库不可用事实）。
- **一致性**: proposal / design / tasks / spec delta / grill / backlog 六者大体一致。矛盾点：D4 host 语句与 Q1 确认、spec delta、tasks 3.4 冲突（I3）；删除行为在 proposal/spec/tasks 均存在但 design 与 tasks 无对应 API（I1）；resume 归属在 design D3 与 spec delta 的"会话归属其创建时的 workspace"不变量之间存在未闭环（I2）。

## Issues

- **I1（严重度: 高）**: 会话删除没有服务端 API 设计与实现任务，验收标准无法按设计落地。
  - 证据: proposal.md:81（验收"会话删除（内存 + 磁盘快照）在 hub 提供"）；specs/web-ui/spec.md:100-110（"Web UI hub SHALL 提供会话删除"）；design.md D5（只有前端"删除按钮"与"删除时关闭同 id tab"）；design.md D3（只改 `remove_session(session_id)` 签名）；tasks.md 3.3（只新增 `GET /api/workspaces`、`GET /api/sessions`，无 DELETE 端点）。
  - 影响: 实现者无从得知删除走 HTTP `DELETE /api/sessions/{id}?workspace=` 还是 WS `delete_session` 消息；且 design D3 的 `remove_session` 依赖"用 session 的 workspace_root 解析 store"，对不在内存的冷会话（hub 删除一个未打开的会话是常态）没有 workspace_root 可查，磁盘快照无法定位。删除是一个明确验收项，缺 API = 该验收项不可实现。
  - 建议修复: 在 design D1/D3 与 tasks 3.3 补一个显式删除入口，例如 `DELETE /api/sessions/{session_id}?workspace=<path>`（workspace 经 `resolve_workspace()` 校验），并给 `remove_session(session_id, workspace=None)` 增加 workspace 参数：内存 pop 后，workspace 缺省时才回退到 session.workspace_root，否则直接用指定 workspace 的 store 删除快照；同步补后端集成测试（冷会话删除）。
  - 涉及文件: design.md / tasks.md / spec

- **I2（严重度: 高）**: resume 无 workspace 时命中 allowlist store 后，resumed session 的 workspace_root / session_store 归属未闭环，违反 spec"会话归属其创建时的 workspace"不变量。
  - 证据: design.md D3（`resume_session_async(session_id, workspace=None)` 按主→allowlist 序搜索，但未说明命中后 `_create_session` 用命中 workspace 构造 WorkspacePolicy 与注入 `_store_for(命中 workspace)`）；specs/web-ui/spec.md:53-69（"会话归属其创建时的 workspace""不写入其他 workspace 的目录"）。
  - 影响: 若实现只按 tasks 3.2 字面加 workspace 参数而漏掉"命中 store 即会话归属"的传递，未带 workspace 恢复的 allowlist 会话在下次 run 会落盘到主 workspace store，同一 session_id 出现在两个 store，下次搜索按主优先读到新快照，旧 allowlist 快照被静默孤立——会话"漂移"出原 workspace，且无任何测试拦截。
  - 建议修复: design D3 明确"resume 命中哪个 store，就用该 workspace 创建 session（workspace_root + `_store_for` + WorkspacePolicy 均用命中值）"；tasks 2.1 补"无 workspace 恢复 allowlist 会话后再次 run，快照仍写入该 allowlist store、主 store 不新增"的断言。
  - 涉及文件: design.md / tasks.md

- **I3（严重度: 中）**: design.md D4 的 host 绑定残留语句与已确认 Q1 决策、spec delta、tasks 3.4 直接矛盾。
  - 证据: design.md:77（"本决策不改变 `0.0.0.0` 默认"）；design.md:137（Q1 用户确认"改默认 `127.0.0.1`"）；specs/web-ui/spec.md:116（"Web 默认 host 绑定策略为 `127.0.0.1`"）；tasks.md:48（"`--host` 默认值改为 `127.0.0.1`"）。
  - 影响: D4 是安全边界决策，残留旧句会让实现者/审阅者对最终 host 策略产生歧义，也可能被 workflow_guard/artifact checker 判定为决策未收敛。
  - 建议修复: 把 D4 该句改为"Q1 已确认：默认 host 改 `127.0.0.1`（`agent/main.py:661`），显式 `--host 0.0.0.0` 才开放 LAN；allowlist 只限制可操作 workspace 集合，不限制端口访问者，`0.0.0.0` 下需文档明示边界"。
  - 涉及文件: design.md

- **I4（严重度: 中）**: spec delta 的 MODIFIED "Web session 本地持久化与恢复" 丢失 3 个既有 scenario，其中"未知 session id 回退新建"无任何覆盖。
  - 证据: specs/web-ui/spec.md:114-130（MODIFIED 仅保留"刷新页面回到原 session""显式恢复入口"2 个 scenario）；原 `openspec/specs/web-ui/spec.md:296-327` 含"run 结束后自动落盘""进程重启后按 id 恢复""未知 session id 回退新建"5 个 scenario。
  - 影响: OpenSpec 的 MODIFIED 语义是整体替换该 requirement；省略的 scenario 会被删除。"未知 session id 回退新建"是 #110 已实现且本 design 明确保留的行为（D3"全部未命中返回 None"→回退新建），从规格中消失属覆盖回退，违背"delta 覆盖所有新增行为且不丢既有契约"。
  - 建议修复: MODIFIED 段补回"未知 session id 回退新建"（以及"进程重启后按 id 恢复"若不被 ADDED requirement 完全覆盖）的 scenario；或将"按 workspace 恢复"的 ADDED scenario 显式标注为承接原"进程重启后按 id 恢复"。
  - 涉及文件: spec

- **I5（严重度: 中）**: 前端最高回归风险区域的 per-tab 隔离测试未排；裸 `/ws/new` 保留 `--resume` 语义无回归测试。
  - 证据: design.md D5 明示 `approvalCards`/`questionCards`/`pendingImages`/`shouldReconnect`/`slashMatches`/`iterBlocks` 若保持全局会跨 tab 串扰；tasks.md 2.2 的 Playwright 清单只有 hub/多标签消息隔离/新建/刷新/删除，未覆盖审批、图片上传、reconnect、slash 匹配的跨 tab 隔离；tasks.md 2.1 只测"带显式参数跳过 resume"，未测"裸 `/ws/new` 仍恢复"。
  - 影响: 这是 1451 行 chat.js 从全局单例重构为 per-tab 的最大回归面，D5/grill R5 自己都承认这些字段是串扰源，但测试不覆盖就无法在回归时兜住。
  - 建议修复: tasks 2.2 补 Playwright 用例：两个 tab 各自触发审批/图片上传，卡片与预览只落各自 tab；一个 tab 结束（continue_session=false）不影响另一 tab 的 shouldReconnect；tasks 2.1 补"`create_app(resume=...)` 下裸 `/ws/new` 仍返回 resume 会话"的断言。
  - 涉及文件: tasks.md

- **I6（严重度: 中）**: `/ws/{id}?workspace=` 非法 workspace 的拒绝路径未定义，负向测试未排，spec delta 无对应 scenario。
  - 证据: design.md:66 声称 `/ws/{id}?workspace=` 走 `resolve_workspace()` 拒绝；但 design.md 只对 `/ws/new` 写明"WS error 事件 workspace_not_allowed"，未定义 resume 路径被拒时的行为（error 事件后关闭？close 前发 error？）；tasks.md 2.1/2.3 负向清单只覆盖 `/api/sessions` 与 `/ws/new`；spec delta 的"显式恢复入口"scenario 只覆盖合法路径。
  - 影响: 该入口是 R1 安全绕过修复的核心之一，拒绝路径不定义会导致实现随意（静默回退主 workspace 新建 = 绕过校验语义），且无测试兜底。
  - 建议修复: design D3/D4 明确"`/ws/{id}?workspace=` 非法/未授权 → 回 `{"error": "workspace_not_allowed"}` 后关闭连接，不创建/恢复会话"；tasks 2.3 补该入口的负向用例；spec delta 补一个"恢复时指定未授权 workspace 被拒"的 scenario。
  - 涉及文件: design.md / tasks.md / spec

- **I7（严重度: 低）**: `/api/workspaces` 的 `exists` 字段在"有效集合只含存在路径"的设定下恒为 true，语义冗余且与运行期状态脱节。
  - 证据: design.md D1（响应含 `exists`）；design.md D4（有效集合 = {主} ∪ {allowlist 中 resolve 后存在}，即只有存在的路径才进集合）。
  - 影响: `exists` 恒真，前端无法据此感知"启动后目录被删/新建"；集合一次性解析使新建目录要重启才可见（设计已声明，可接受）。非安全问题。
  - 建议修复: 要么删除 `exists` 字段（proposal 要求含"是否存在"，需与 proposal 对齐后删），要么在 `/api/workspaces` 响应时对每个条目做一次 `Path.exists()` 实时判断并说明"有效集合一次性解析、exists 反映运行期状态"。
  - 涉及文件: design.md / proposal.md

- **I8（严重度: 低）**: design.md Risks 中 chat.js 行数"1353 行"与真实 1451 行不符。
  - 证据: design.md:167；`wc -l web/static/chat.js` = 1451。
  - 影响: 仅文档事实失真，不影响决策。
  - 建议修复: 改为 1451。
  - 涉及文件: design.md

- **I9（严重度: 低）**: design.md Risks 中"uploads 全局 vs workspace（中，Q2 未决时）"为 stale 措辞。
  - 证据: design.md:170；Q2 已在 grill-design.md `## User Confirmation` 确认保持全局。
  - 影响: 与已确认决策不一致的措辞残留，易误导。
  - 建议修复: 改为"（Q2 已确认保持全局；若后续隔离需补 HTTP 上传 workspace 线程与回归）"。
  - 涉及文件: design.md

- **I10（严重度: 低）**: `_store_for` 缺省 workspace（None）时的 key 规范化未精确说明。
  - 证据: design.md D3（"key 为 `str(Path(workspace).resolve())` 规范化后的值"；`_store_for(workspace_root)` 用 `(workspace_root or cwd)`）。
  - 影响: `Path(None or cwd)` 与 `Path(cwd)` 的规范化一致，但需写明"None → `Path.cwd().resolve()`"，否则实现可能用未 resolve 的 cwd 作 key 导致主 workspace 出现两个 store。
  - 建议修复: D3 补一句"`_store_for(None)` key 为 `str(Path.cwd().resolve())`"。
  - 涉及文件: design.md

- **I11（严重度: 低）**: `/ws/{id}` 快照未命中回退新建时忽略 `?workspace=` 参数，新建到默认 workspace。
  - 证据: web/server.py:179-185（未命中 `create_session_async(llm)` 无 workspace 参数）；design D2 只对 `/ws/new` 定义了 workspace 参数语义。
  - 影响: 用户显式带 `?workspace=X` 恢复一个不存在的 id，会被静默新建到主 workspace，与 URL 意图不一致（非安全，UX 困惑）。
  - 建议修复: 在 design D2/D3 中明确"resume 回退新建时若 URL 带合法 workspace，则以该 workspace 新建"。
  - 涉及文件: design.md

## 阻塞性缺陷

无。设计方向正确（hub + 多标签 per-tab + 按 workspace 分区 store + allowlist 边界 + per-session 互斥），无根本方向错误或需求无法满足的致命缺陷。

---

## Round 2

- run id: `b1a2f3c4-5d6e-4f80-9a1b-2c3d4e5f6a7b`
- 时间: 2026-08-09

### Verdict

**PASS**

### Round 1 修复核对

- **I1（删除 API 缺失，高）**: 已修复。design D1 新增 `DELETE /api/sessions/{session_id}?workspace=<path>`（design.md:44，冷会话无内存 `workspace_root` 可查，请求必须携带 workspace）；design D3 的 `remove_session(session_id, workspace=None)` 显式 workspace 走该 workspace 的 store，缺省回退内存 session 的 `workspace_root`（design.md:66，reset 路径保持现状语义）；tasks 3.3 排了 DELETE 端点（tasks.md:50）、tasks 2.1 排了冷会话删除断言（tasks.md:20）；spec delta 删除 requirement 定义请求机制、删除/冷会话/未授权 3 个 scenario（spec.md:115-139）。与既有 reset 语义不冲突——reset 仍走缺省 workspace 分支。
- **I2（resume 归属未闭环，高）**: 已修复。design D3 明确"命中哪个 store，就用该 workspace 创建 session——`workspace_root`、`WorkspacePolicy`、`_store_for(命中 workspace)` 全部用命中值"（design.md:65）；tasks 2.1 补"无 workspace 恢复 allowlist 会话后再次 run，快照仍写入该 allowlist store、主 store 不新增"断言（tasks.md:26）；spec delta 补 `未带 workspace 恢复时会话归属命中 workspace` scenario（spec.md:72-77，"恢复的 session SHALL 以 A 为 workspace_root"+"后续 run SHALL 仍写入 A 的 store"）。
- **I3（D4 host 残留矛盾，中）**: 已修复。design D4 host 语句已改为"默认 host 改 `127.0.0.1`（`agent/main.py:661`），显式 `--host 0.0.0.0` 才开放局域网访问"，无"不改变 0.0.0.0 默认"残留（design.md:79）；与 Open Questions Q1（design.md:154）、spec delta MODIFIED（spec.md:145）、tasks 3.4（tasks.md:51）一致。已核实 `agent/main.py:661` 现默认确为 `0.0.0.0`，`main.py:681` 的 `display_host` 逻辑改动点真实存在。
- **I4（spec delta 丢 scenario，中）**: 已修复。MODIFIED "Web session 本地持久化与恢复" 现含全部 5 个 scenario：run 结束后自动落盘（spec.md:147-151）、进程重启后按 id 恢复（spec.md:153-158）、刷新页面回到原 session（spec.md:160-165）、显式恢复入口（spec.md:167-172）、未知 session id 回退新建（spec.md:174-180，且新增"若连接 URL 携带合法 `?workspace=`，新建 session 使用该 workspace"承接 I11）。与原规格 5 个 scenario 一一对应，无覆盖回退。
- **I5（前端回归测试盲区，中）**: 已修复。tasks 2.2 补 per-tab 隔离 Playwright——"两个 tab 各自触发审批/图片上传，卡片与预览只落各自 tab；一个 tab 结束（continue_session=false）不影响另一 tab 的 reconnect"（tasks.md:32）；tasks 2.1 补"裸 `/ws/new` 仍保留 `--resume` 语义"回归（tasks.md:22）；design Testing Strategy 同步（design.md:203,209）。残余低项：slash 匹配的跨 tab Playwright 用例未单独列出（仅 审批/图片/reconnect），但 `slashMatches` 已在 Tab 字段（tasks 3.5）与 design D5 收口，属装饰性建议状态，不构成必须修。
- **I6（resume 拒绝路径未定义，中）**: 已修复。design D4 明确"`/ws/{id}?workspace=` 不在有效集合或路径不存在 → 回发 `{"error": "workspace_not_allowed"}` 事件后关闭连接，不创建/不恢复会话；不允许静默回退主 workspace 新建"（design.md:80）；tasks 2.1（tasks.md:27）与 tasks 2.3（tasks.md:36，覆盖三入口负向路径）已排；spec delta 补 `恢复时指定未授权 workspace 被拒` scenario（spec.md:79-84）。
- **I7（exists 恒真冗余，低）**: 已修复。design D1 改为"`exists` 在响应时对每个条目实时 `Path.exists()` 判断（集合启动时一次性解析，`exists` 反映运行期目录状态）"（design.md:42）；spec delta"每个 workspace SHALL 标注运行期是否存在"（spec.md:13）；tasks 2.1 断言 `exists` 字段正确（tasks.md:18）。
- **I8（chat.js 行数不符，低）**: 已修复。design Risks 为"`chat.js`（1451 行）"（design.md:184）；已核实 `wc -l web/static/chat.js` = 1451。
- **I9（uploads 措辞 stale，低）**: 已修复。design Risks 为"uploads 全局 vs workspace（低，Q2 已确认保持全局）"（design.md:187），"Q2 未决时"措辞已去除。
- **I10（`_store_for(None)` key 未精确，低）**: 已修复。design D3 补"`_store_for(None)` 的 key 为 `str(Path.cwd().resolve())`，与显式传主 workspace 时一致"（design.md:63）。该语义在 `self.workspace_root` 为 None（未传 `--workspace`）时与现状 `(workspace_root or Path.cwd())` 一致，不引入双 store。
- **I11（回退新建忽略 URL workspace，低）**: 已修复。design D3 明确"`/ws/{id}?workspace=X` 快照未命中回退新建时，若 URL 携带合法 workspace 则以该 workspace 新建"（design.md:67）；spec delta 未知 id 回退新建 scenario 同步（spec.md:180）。

### 新发现问题

- **I12（低）**: spec delta MODIFIED 正文丢失了原规格的规范性语句"Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）"，仅保留同名 scenario（spec.md:167-172）。行为仍被 scenario 覆盖、未回退契约，但 OpenSpec 惯例要求 scenario 有对应 SHALL 语句背书。建议在 MODIFIED 正文补回该句。
- **I13（低）**: tasks 2.2 的 per-tab 隔离 Playwright 只列审批/图片/reconnect，未列 slash 匹配状态只落各自 tab。slash 串扰为装饰性（建议下拉），非状态破坏；`slashMatches` 已入 Tab 字段。建议 building 阶段补一条即可。
- **I14（低）**: "路径不存在"拒绝条件与 `resolve_workspace` 的校验集合语义存在轻微歧义——D2/D1 各入口把"路径不存在"列为拒绝条件（design.md:55,43），而 D3/D4 对 `resolve_workspace` 的描述是"`expanduser().resolve()` + 集合成员判断"（design.md:68,77），集合又是启动时一次性解析（含存在性）。启动后目录被删的 allowlist 项仍在集合内，若 `resolve_workspace` 不查运行期存在性则"路径不存在"不生效。建议实现时让 `resolve_workspace` 同时检查集合成员与 `Path.exists()`，并在 D4 补一句。
- **I15（低）**: DELETE 端点缺失 `?workspace=` 参数的行为未显式定义。design D1 说"workspace 必须显式传入"（隐含拒绝），但 spec delta 无对应 scenario。建议补 400 拒绝场景。
- **I16（低）**: `remove_session(session_id, workspace=X)` 在内存 session 实际归属 Y 而请求带 X 的错配边界（前端传错 workspace）会删除 X store 快照、却把 Y store 快照留成孤儿。实际 hub 列表与请求同源（按选中 workspace 列出后删除），错配仅可能来自前端 bug 或恶意客户端，且重试自愈（Y 快照仍在列表，再次删除即清）。建议 D3 注明"内存 session 在时以 `session.workspace_root` 为准、workspace 参数仅用于定位冷会话 store"。
- **I17（低）**: `--host` 默认改 `127.0.0.1` 是 CLI 行为变更，tasks 3.4 只有实现没有对应 CLI 层级测试；现有 `tests/test_cli.py:807` 的 web 命令测试只断言 session_id/workspace_root，不断言 host 默认。按 AGENTS.md"涉及 CLI 的变更必须覆盖对应层级测试"，建议 tasks 2.4 或 3.4 补一条断言默认 host 为 `127.0.0.1` 的 CLI 测试。

### 阻塞性缺陷

无。修复自洽：新增 DELETE 端点与既有 `remove_session`/reset 语义兼容（reset 走缺省 workspace 分支、保留 workspace/mode）；resume 归属闭环与确定性搜索顺序（主→allowlist）一致；spec delta 与现有 `openspec/specs/web-ui/spec.md` 无冲突（新增 6 项 ADDED 均为新能力、MODIFIED 完整保留 5 个既有 scenario）；文档/门禁证据齐备（grill 13 项 User Confirmation、workflow-events.jsonl 覆盖 backlog_updated、backlog 登记 #6、Impact Analysis 无残留 unknown/TBD）。新增 6 项均为低改进项，不阻塞进入 building。

### Round 2 低项跟进（2026-08-09，PASS 后主 agent 补修）

PASS 判定后，Round 2 新增的 6 个低改进项已全部处理：

- **I12**（MODIFIED 正文缺"显式恢复入口"规范句）→ spec delta MODIFIED 正文补回"Web UI SHALL 提供显式恢复入口（URL `?session=<id>` 与 `GET /resume`）"。
- **I13**（slash 跨 tab Playwright 未列）→ tasks 2.2 补"两个 tab 的 slash 匹配状态互不串扰"。
- **I14**（resolve_workspace 运行期存在性歧义）→ design D4 明确 `resolve_workspace` 只做集合成员判断、不做运行期 `Path.exists()` 复检（`/api/workspaces` 的 `exists` 是唯一运行期反映）。
- **I15**（DELETE 缺 workspace 参数行为）→ design D1 补 HTTP 400 + `{"error": "missing_workspace"}`；spec delta 补"删除时缺 workspace 参数" scenario。
- **I16**（remove_session workspace 错配边界）→ design D3 补幂等 + 前端重试自愈说明，不做额外错误分支。
- **I17**（--host 默认缺 CLI 测试）→ tasks 2.4 补 `test_cli.py` web 命令 host 默认断言。

设计审阅闭环至此完结：Round 1 CHANGES_REQUESTED（6 必须修 + 5 低）→ 修复 → Round 2 PASS（6 低项后续跟进完成）。可进入 building。
