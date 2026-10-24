# Tasks: 群聊 everyone 模式无限讨论链（讨论链 + 停止按钮 + 安全阀）

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → 本地复验 → **结算 `tasks.md`（未勾且未标 `(post-merge)` 必须为 0）** → 用归档目录名重建
> witnessloop 三份 manifest → `gate / check` 机械复核 → 发起 PR。PR 创建与合入不写回 `tasks.md`；
> closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling` 同等标准（独立零记忆 subagent）执行设计追问，产出 `reviews/grill-design.md`
  （12 条 Confirmed Decisions、4 条 Open Questions、22 条 Design Corrections；`## User Confirmation` 已回填）。
- [x] 0.2 逐项落实 grill 的 C1–C22，回写 `design.md`。
- [ ] 0.3 设计阶段对抗闭环 → `reviews/grill-adversarial.md`：r1 = CHANGES_REQUESTED（批次 I 12 条已全修，design v4）；r2 只做修复验证，`PASS` 后方可写码。
- [x] 0.4 停轮确认：4 个 Open Questions（每条配具体例子）已抛给用户，答复写入
  `reviews/grill-design.md` 的 `## User Confirmation` 与 `design.md` 的 `## User Rulings`（Q1 不收敛 / Q2 保持现状+日志 / Q3 单轮不停止 / Q4 slot 间检查）。
- [ ] 0.5 回填 `design.md` 的 `## Pre-Implementation Review`（grill 决策、对抗轮次、修复项、出口）。

## 1. 测试（TDD，先红后绿）

- [ ] 1.1 `tests/agent/team/test_team_store.py`：`Room.discussion_mode` 缺省 `single`、roundtrip、旧 JSON 缺字段兼容。
- [ ] 1.2 `tests/agent/test_config.py`：`TeamConfig` 三参数默认 200/600/6000、YAML 覆盖、非法值 `ConfigError`。
- [ ] 1.3 扩展 `tests/agent/team/test_orchestrator.py`（FakeRunner + 可注入 clock）：
  - unlimited 连开 ≥3 轮（发言 → 部分静默 → 全员静默 `converged`）；每轮每人一次、admin 先；
  - single 模式只跑一轮且事件/payload 与现状逐字段一致（快照断言）；
  - 用户插话：链中进日志 + 行首 `@` 插当前轮；轮间窗口进 `pending_mentions` 并在下一轮生效；
  - 停止：成员回合进行中请求 → 回合完成后结束当前轮、剩余 slot 不跑；`round_ended(stopped)` +
    `discussion_ended(stopped)` + system 日志；重复停止/无链 no-op；
  - 安全阀四路各自期望值：`max_rounds`；`max_turns`（额度在轮末恰好耗尽）；`max_seconds`（clock 注入 + slot 间检查）；`round_limit`（`extra_turns=0` 截断当前轮）。
  - 链中把 `discussion_mode` 改回 `single` → 本轮后 `mode_changed`；
  - 取消（`CancelledError`）→ `round_ended(cancelled)` + `discussion_ended(cancelled)` + 状态 reset；
  - 链结束释放房间认领、`is_round_active` 语义、review sink 每轮 `on_round_end`；
  - 空成员房间 unlimited → 退化单轮、无 `discussion_*`；
  - 未消费用户消息：回合切片构造后到达且本轮 0 发言 → 不收敛、强制再开一轮；安全阀耗尽则按 cap reason；
  - 收尾同步区竞态（gate 卡在最后一个 slot 结束后）：停止/取消/新消息三路断言；
  - review sink 抛异常不中断链；`chain_id` 单调递增；`rounds`/`rounds_started`/`turns`/`elapsed_seconds` 精确值；
  - 控制台断言 `single` 房 `request_stop=False`、不产生 `stopped`、无 `discussion_*`/`system_entry` 事件；
  - 链中 `delete_room` → 收尾 `completed` 且不复活日志；可挂起 emit sink 覆盖首轮骨架窗口（grill I1）。
- [ ] 1.4 扩展 `tests/web_tests/test_group_chat_server.py` / `test_group_chat_team.py`：
  - 房间 create/patch 校验（`unlimited`+`admin` → 400 `discussion_mode_requires_everyone`；
    改 `reply_mode` 冲突 → 400；非法值 → 400 `invalid_discussion_mode`）；
  - `room_state`：`room.discussion_mode` + `discussion_round` + `discussion_reason`（**不新增 `discussion_active`**）；
  - REST stop 幂等 + 跨 workspace 回落；WS `stop_discussion` 生效；事件顺序
    `discussion_started → member_* → discussion_stop_requested → round_ended(stopped) → discussion_ended(stopped)`；
    单轮房间事件流与现状一致。
- [ ] 1.5 前端测试：`group_status.js` 新增纯函数 `describeRoundEnd` / `describeDiscussionEnd` /
  `shouldShowStop` / `shouldApplyChainEvent`（chain_id 守卫）的 JS 用例（`test_group_status_js.py` 同形）；
  设置下拉仅 everyone 可选 unlimited（disabled）；停止按钮可见性/置灰/恢复；`system_entry` 追加时间线；
  390px 头部不溢出（现有浏览器测试模式）。

## 2. 实现

- [ ] 2.1 `agent/team/models.py`：`DISCUSSION_MODES`、`Room.discussion_mode`、`to_dict/from_dict`。
- [ ] 2.2 `agent/config.py`：`TeamConfig` 三参数 + `_parse_team_config` 解析校验；`asterwynd.example.yaml` `team:` 示例。
- [ ] 2.3 `agent/team/orchestrator.py`：`_ChainState` + `_run_discussion` 循环 + `_drive(chain, state)` +
  `_run_slot(chain, state, pid)` 签名 + 停止请求/续轮判定/安全阀/链 teardown + `clock` 注入；
  `RoundResult` 扩展字段；`unlimited` 提示词增强。
- [ ] 2.4 `web/team.py`：`TeamService.stop_discussion`、房间 create/update 校验、`discussion_*` 状态透出。
- [ ] 2.5 `web/server.py`：REST stop 端点、房间 WS `stop_discussion` 消息、`room_state` 扩展。
- [ ] 2.6 `web/static/group.js` + `index.html` + `style.css`：讨论模式设置、停止按钮、状态文案、
  事件处理与 WS/REST 降级。
- [ ] 2.7 全量回归：`uv run pytest -q`。

## 3. 规格与文档同步

- [ ] 3.1 `openspec/specs/multi-agent-collaboration/spec.md`：MODIFIED「房间级互斥与轮次终止」、
  MODIFIED「房间应答模式」、ADDED「讨论链自动续轮与收敛」。
- [ ] 3.2 `openspec/specs/web-ui/spec.md`：MODIFIED「人设与房间的管理入口」（讨论模式字段）、
  ADDED「群聊讨论链状态与停止讨论控件」。
- [ ] 3.3 `openspec/specs/configuration/spec.md`：ADDED「群聊讨论链安全阀可配置」。
- [ ] 3.4 `docs/architecture.md` 群聊小节改「单轮 / 讨论链」终止口径 + 停止与安全阀；`CONTEXT.md` 补「讨论链」；
  检查 `docs/interview-script/` 相关表述。
- [ ] 3.5 `openspec/changes/group-unlimited-discussion/workflow-events.jsonl` 补 `current_spec_synced` 事件。
- [ ] 3.6 实现后独立审阅闭环 `/review-loop` → `reviews/building-review.md`（`## 闭环出口` PASS）。

## 4. 收尾

- [ ] 4.1 `docs/openspec-change-backlog.md` 移除本 change（`backlog_updated` 事件）。
- [ ] 4.2 归档 move 到 `openspec/changes/archive/2026-10-24-group-unlimited-discussion/`（独立提交，纯 rename）。
- [ ] 4.3 用归档目录名重建 witnessloop 三份 manifest（grill / grill-adversarial / building）。
- [ ] 4.4 本地复验：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`。
- [ ] 4.5 发起 PR；PR 描述写明验证结果与 issue #333 关联。
- [ ] 4.6 issue #333 追加完成说明并关闭。(post-merge)
