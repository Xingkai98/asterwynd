# Grill: declarative-flow-engine 设计追问

## Reviewer

- run id: grill-declarative-flow-engine-zero-memory
- 时间: 2026-08-16
- 性质: 独立零记忆设计评审（不继承任何开发上下文，仅依据 proposal.md / design.md / tasks.md / spec delta 与现有代码证据）

## 评审范围与证据基线

对 design.md 的 D1-D8 逐项挑战，对照以下现有语义证据（file:line）：

- 投影与事件应用：`agent/workflow/event_log.py`（`replay_handoff_projection` :233-262、`_apply_transition_event` :265、`_apply_blocked_event` :292、`_apply_unblocked_event` :310、`project_workflow_state` :370、`_project_new_gen` :390-420、`_apply_blocked_to_state` :455-468、`AWAITING_SUB_STATES` :51-55、`NON_STATE_EVENT_TYPES` :17-23、`MILESTONE_EVENT_TYPES` :42-48）
- 转移合法性：`agent/workflow/state_machine.py`（`validate_transition` :118-224、`WITHIN_PHASE_ADJACENT` :80-115、`CROSS_PHASE_FORWARD` :64-77、`get_legal_targets` :227-251、`_validate_sub_state` :42-52）
- 状态常量：`agent/workflow/models.py`（`PHASES` :9、`PHASE_SUB_STATES` :85-90、`GATE_SUB_STATE` :92、`TRIGGERS` :14）
- flow 命令：`scripts/workflow_state.py`（`flow block` :572、`flow confirm` :613、`flow approve` :651、`flow advance` :715、`_AWAITING_RECOVERY_DEFAULTS` :755-759、`_awaiting_recovery_target` :833-844、`_method_hint` :167、`_build_path` :237）
- 执法与门禁：`scripts/workflow_guard.py`、`scripts/flow-policy.json`、`scripts/check_openspec_artifacts.py`

## 核心判断摘要

**最大的架构性发现**：现有投影 `project_workflow_state` 派生 state 的方式是「跟随每条状态事件的 `transition.to`」，**从不查转移表**；`on` 转移表只被 `validate_transition` / `get_legal_targets` 用于「生成下一个合法目标 / 校验一次转移是否合法」。因此：

1. 引擎 `derive_state(events)` 与 Python 的 parity 若只比 state，是**弱断言**（双方都读同一个 `transition.to`），真正有价值的 parity 在 `legal_targets` / `can_transition` 与 `validate_transition` 的等价。
2. 引擎 API 只给 `apply_transition(state, event)`（事件驱动）不足以驱动 flow 命令——flow 命令是**目标驱动**（`flow advance --to X` / `flow approve --phase P` / `flow block --awaiting A`），且合法性依赖 `trigger`，而 `on: <event>: <target>` 不携带 trigger。

**最严重的事实错误**（BLOCKING）：design D5/D7 声称「旧 Python 对演示新态 `awaiting_design_confirmation` 透明/容忍不报错」——但现有代码对未知 sub_state **一律 raise**：

- `state_machine.py:_validate_sub_state`（:42-52）拒绝不在 `PHASE_SUB_STATES["planning"]` 里的 planning sub_state → `transition_applied` 到 `planning.awaiting_design_confirmation` 会 `StateMachineError`。
- `event_log.py:_apply_blocked_to_state`（:462-466）拒绝不在 `AWAITING_SUB_STATES` 里的 blocked sub_state → `blocked_entered` 到 `blocked.awaiting_design_confirmation` 会 `StateMachineError`。

`awaiting_design_confirmation` 无论建模成 `planning.awaiting_*` 还是 `blocked.awaiting_*`，旧 Python 都会抛错，不存在「容忍」路径。spec delta 场景「AND 现有 Python 逻辑 SHALL 不需要修改（对新态透明，容忍处理）」按字面**不可实现**。

## Confirmed Decisions

- **决策**: 声明文件采用 JSON（`flow/statechart.json`）而非 YAML，与 #122 `flow-policy.json` 选 JSON 一致、stdlib `json` 零依赖解析；注释用 `_description` 键约定（沿用 `workflow_methods.json` 的既有写法）；spec delta 已写「或等价声明文件」允许文件名落地为 `.json`。理由: stdlib 无 YAML 解析器，引入 PyYAML 违反「不引入新依赖」红线；JSON 与 P0 策略源先例一致，`_description` 键可承载转移表可读性。
- **决策**: parity 测试作为普通 pytest 落在 `tests/test_declarative_flow_engine.py`，随 `uv run pytest -q` 进 baseline CI 门禁，不引入独立 CI 步骤；任务 2.2/4.2 已规划为 pytest，无需额外接线。理由: #124 验收线「parity 等价 pin」需要可机械执行的 golden 断言，复用现有 pytest 门禁最简且已被 tasks 覆盖。
- **决策**: 引擎 parity 范围明确为 gen-2（`change_created` 开头或无 seed 事件）；gen-1（`initialized` + handoff.json 老世代）**排除**并在 design 文档注明。理由: gen-1 映射路径（`_map_handoff_to_workflow_state`）是归档兼容逻辑，与「改规则不改 Python」的声明化目标无关；纳入会显著扩大 parity 面且对验收无贡献。
- **决策**: 引擎 `validate()` 除结构校验（引用完整性 / initial 存在 / 无孤立状态）外，必须提供 parity 交叉校验模式：逐条把 statechart 声明的转移 `(from, to, trigger)` 对 `validate_transition` 验证，声明了 Python 判非法的转移即报错 exit 2。理由: 仅结构校验无法捕获语义漂移；parity 测试是事后 golden，结构+语义交叉校验是事前机械拦截，二者互补（design「语义漂移」风险单靠 parity 测试压不住）。
- **决策**: 引擎 API 至少需要 `legal_targets(state) -> list[state]`（镜像 `get_legal_targets`）与 `can_transition(from, to, trigger) -> bool`（镜像 `validate_transition`）；`apply_transition(state, event)` 保留为 `on` 表查询，但不是 flow 命令的驱动入口。理由: flow advance/approve/block 都是目标指定（`--to`/`--phase`/`--awaiting`），事件驱动的 `on` 表单独无法驱动它们；且合法性依赖 trigger，schema 每条转移必须携带 trigger。
- **决策**: 引擎 `derive_state(events)` 的 parity 断言目标是**完整投影 dict**（`state` + `milestones` + `source_event_seq`），而非仅 `state`。理由: milestones 推进器（`MILESTONE_EVENT_TYPES` 5 类事件只收集不改 state）只在完整投影可见，只比 `state` 会让 milestones 处理完全脱离 parity 覆盖。

## Open Questions

- **Q1**（BLOCKING）: 演示态 `awaiting_design_confirmation` 旧 Python 不透明——`state_machine.py:_validate_sub_state`（:42-52）拒绝不在 `PHASE_SUB_STATES` 的 planning sub_state，`event_log.py:_apply_blocked_to_state`（:462-466）拒绝不在 `AWAITING_SUB_STATES` 的 blocked sub_state，两条路径对演示态都会 `StateMachineError`。design D5「旧 Python 行为对演示新态不报错（容忍）」与 spec delta 场景「现有 Python 逻辑 SHALL 不需要修改（对新态透明，容忍处理）」按字面不可实现。场景例：演示态建模为 `planning.awaiting_design_confirmation`，跑 `flow advance --to awaiting_design_confirmation` 写 `transition_applied`，旧 Python 投影对 `to={phase:planning, sub_state:awaiting_design_confirmation}` 调 `validate_transition` → `invalid sub_state ... for phase planning` exit。建模为 `blocked.awaiting_*` 则 `blocked_entered` 被 `_apply_blocked_to_state` 以「blocked sub_state must be an awaiting type or null」拒绝。两种建模都 raise。; 推荐答案: 演示改为 test-only fixture——parity 测试内临时向 statechart 注入新态、断言引擎派生、跑完即弃，**不落入提交的 `flow/statechart.json`**；「改规则不改 Python」的演示改述为「引擎从 statechart 生成新态，旧 Python 只 replay 它认识的子集、且本 change 不要求旧 Python 处理新态」；同步改写 spec delta 场景，删除「透明/容忍」表述，改为「引擎 SHALL 正确派生新态与转移，且不要求现有 Python 处理该态」; 为什么必须现在定: 这是本 change 的核心验收证据（#124「演示一次真实规则变更不改 Python」），Q1 不修正则任务 3.4/4.5/演示测试不可实现，且 spec delta 含不可达的 SHALL。
- **Q2**（BLOCKING）: D7「未知事件类型按 NON_STATE 处理不抛错（P1 语义）」是对 P1 的误读——`replay_handoff_projection`（event_log.py:259-260）与 `_project_new_gen`（:412-413）对未知事件类型**都 raise** `StateMachineError`；P1 的「容忍异构」仅指**无 seed 事件**（首事件非 `change_created` 仍按默认 seed 投影）。D7 若实现为「未知事件保持状态不抛错」，引擎派生语义与 Python 不一致，parity 测试无法机械成立。; 推荐答案: 引擎派生语义与 Python 严格对齐——未知事件类型 raise（parity 要求）、`NON_STATE_EVENT_TYPES` 跳过、`MILESTONE_EVENT_TYPES` 只收集进 milestones；「容忍」只保留「无 seed 事件」一种；`apply_transition` 对 `on` 表中未声明的事件才可「保持当前状态」并在文档注明这与派生不冲突（派生仍由 `transition.to` 驱动）。; 为什么必须现在定: 引擎容错语义决定 parity 测试能否机械成立，D7 现状会让「未知事件类型」parity 断言失败。
- **Q3**（BLOCKING）: D6「把 workflow_methods.json 已有的流程结构（phases 映射）抽到 statechart」要么无操作要么破坏——真正转移结构在 `state_machine.py`（`WITHIN_PHASE_ADJACENT`/`CROSS_PHASE_FORWARD`/`PHASE_SUB_STATES`），`workflow_methods.json` 里只是 per-sub_state 执行方法 + `require_worktree`/`required_files_before_write`；且 `workflow_state.py:_method_hint`（:167）、`_method_review_dims`（:183）、`_build_path`（:237）直接 `methods[phase][sub_state][...]` 索引，**删除 phase/sub_state 键即 KeyError**。场景例：若「抽取」= 从 workflow_methods.json 删掉 `planning`/`building` 等 phase 段，`flow discover` 的 `_build_path` 对每个 sub_state 调 `_method_hint` → `methods[phase]` KeyError，discover 直接崩。若保留则什么都没抽。; 推荐答案: P4 明确**不删除** workflow_methods.json 的 phase/sub_state 段（删除即破坏 `_method_hint`/`_build_path`），「抽取」仅指「statechart 成为状态集的权威声明、workflow_methods 保留每状态执行方法映射」，两文件共享状态名、职责不重叠；真正的流程结构抽取对象是 `state_machine.py` 常量，留替换 change（P4 非目标「不替换现有 Python」下不做）。; 为什么必须现在定: D6 是方案 A 分工的核心，抽取边界不界定会在实现时删除字段破坏 CLI 且破坏 workflow_methods 兼容测试（任务 2.4）的语义。
- **Q4**（BLOCKING）: schema 无法静态表达 blocked 恢复目标——恢复目标是数据依赖（最后一条 `blocked_entered` 的 `transition.from`，`workflow_state.py:_awaiting_recovery_target` :833-844）或按 awaiting 类型默认（`_AWAITING_RECOVERY_DEFAULTS` :755-759：awaiting_proposal_confirmation→planning.writing_design、awaiting_human_review→planning.reviewing_artifacts、awaiting_user_confirmation→planning.writing_design）。D1 示例 `blocked.awaiting_user_confirmation: on: user_confirmed: <恢复目标>` 用占位符回避建模；且 D1 中 `awaiting_design_confirmation: user_confirmed: planning.building_ready` 语义错误——恢复应回到进入阻塞前状态（planning.writing_design 附近），而非跳到 building_ready（`flow confirm` 走 `_awaiting_recovery_target` 恢复 pre-blocked 态，不是前进）。场景例：change 在 `planning.exploring` 被 `flow block --awaiting awaiting_user_confirmation`，`flow confirm` 应恢复到 `planning.exploring`（blocked_from）；statechart 若写死 `user_confirmed: planning.writing_design` 就与动态恢复矛盾。; 推荐答案: statechart 增加 `recovery` 语义——每个 awaiting 态声明 `recovery: "from_blocked_from"`（优先动态恢复）与 `recovery_default: {phase, sub_state}`（兜底，镜像 `_AWAITING_RECOVERY_DEFAULTS`）；引擎的 flow-confirm 恢复逻辑显式消费该字段；演示态 `awaiting_design_confirmation` 的恢复目标用 `from_blocked_from` + 默认 `planning.writing_design`。; 为什么必须现在定: blocked 建模是 awaiting 语义核心，不建模则引擎无法对 `flow confirm` 恢复路径做 parity，且 D1 示例当前是错误语义。
- **Q5**（BLOCKING）: 引擎 API 与 flow 命令目标驱动语义不匹配——`apply_transition(state, event)` 是事件驱动（`on` 表 `proposal_done → ...`），但 `flow advance --to X` / `flow approve --phase P` / `flow block --awaiting A` 都是**目标指定**，且 `validate_transition` 合法性依赖 `trigger`（auto/handoff/human_review/human_rollback，models.py:14），`on: <event>: <target>` 不携带 trigger。场景例：`flow advance --to writing_design` 需要回答「planning.exploring 能否到 planning.writing_design（trigger=auto）」，事件驱动 API 无法回答；`planning.ready_for_review → planning.exploring` 需要 trigger=human_rollback 才合法，`on` 表无法表达同一对状态因 trigger 不同而合法性不同。; 推荐答案: 每条转移携带 `trigger`（可省略默认 auto）；引擎提供 `legal_targets(state)` 与 `can_transition(from, to, trigger)`（镜像 get_legal_targets/validate_transition）作为 flow 命令驱动入口；`apply_transition(state, event)` 保留为 `on` 表查询供声明阅读，parity 测试对 `legal_targets`/`can_transition` 逐态断言。; 为什么必须现在定: 引擎 API 形状决定 parity 测试构造与后续替换 flow 命令的可行性，D3 当前 API 不足以支撑「引擎驱动 flow 命令」的验证价值。
- **Q6**: 演示态是随 change 提交进 `flow/statechart.json` 还是 test-only fixture？design D5 与任务 3.4 读起来像提交一个 `planning.awaiting_design_confirmation` 态，但任务 4.5 又写「改 statechart（加 awaiting_design_confirmation）→ 跑 parity 测试」，暗示是演示时临时修改。若提交：声明化状态机含一个真实流程永不使用的死态，污染后续替换；且旧 Python 拒绝它（Q1）。; 推荐答案: test-only fixture——提交的 `flow/statechart.json` 不含演示态；演示测试在测试内注入新态并断言引擎派生，跑完即弃；任务 3.4 改述为「演示 fixture：构造含 awaiting_design_confirmation 的 statechart，断言引擎派生 + 旧 Python 不需要处理」。; 为什么必须现在定: 决定提交的 statechart 是否被演示态污染，直接关系「引擎是真实状态机的声明源」的可信度。
- **Q7**: `flow/statechart.json` 是否加入 `flow-policy.json` 受保护路径（governance）？当前策略表无 `flow/` 规则，agent 可直接编辑。若加入受保护，与「改规则不改 Python」（agent 需要编辑它）冲突；若不加入，agent 可随意改声明文件，因引擎是影子交付、漂移不可见。; 推荐答案: P4 不加入受保护路径（保持 agent 可编辑），但新增一个 pytest：对提交的 `flow/statechart.json` 跑 `engine.validate()`（结构 + parity 交叉校验），漂移在 CI 拦截；是否升级为受保护治理留替换 change。; 为什么必须现在定: 决定配置文件治理边界与「改规则不改 Python」的编辑通道是否被门禁堵死。
- **Q8**: 引擎 parity 测试的事件序列从哪里来？现有测试 `tests/agent/workflow/test_event_log.py` 已有构造成熟的事件序列（blocked 进入/解除、transition 应用），是复用还是另造？; 推荐答案: 复用 `test_event_log.py` / `test_workflow_state_cli.py` 的事件 fixture，parity 测试对同一序列断言 `engine.derive_state(events) == project_workflow_state(change_dir)`，避免两套序列语义漂移；另加一个「引擎超集」用例：同一序列含新态时引擎能派生、旧 Python 只 replay 认识子集。; 为什么必须现在定: parity 测试的可测边界依赖序列来源，复用现有 fixture 可减少测试口径分叉。

## User Confirmation

- **Q1**: 用户答复：按推荐——演示改 test-only fixture，`awaiting_design_confirmation` 不进提交的 statechart；「改规则不改 Python」改述为"引擎从 statechart 生成新态，旧 Python 不需要处理该态"；spec delta 场景同步改述；确认时间: 2026-08-16
- **Q2**: 用户答复：按推荐——引擎派生语义与 Python 严格对齐（未知事件类型 raise、NON_STATE 跳过、milestones 只收集），容忍只保留"无 seed 事件"一种；确认时间: 2026-08-16
- **Q3**: 用户答复：按推荐——不删 workflow_methods.json 的 phase/sub_state 段（`_method_hint`/`_build_path` 直接索引），「抽取」改义为 statechart 成状态集权威声明、workflow_methods 保留执行方法映射；state_machine.py 常量抽取留替换 change；确认时间: 2026-08-16
- **Q4**: 用户答复：按推荐——awaiting 态声明 `recovery: "from_blocked_from"` + `recovery_default`（镜像 `_AWAITING_RECOVERY_DEFAULTS`），恢复目标是数据依赖而非静态；确认时间: 2026-08-16
- **Q5**: 用户答复：按推荐——引擎 API 补 `legal_targets(state)` + `can_transition(from, to, trigger)`（镜像现有校验），每条转移带 `trigger`；`apply_transition` 保留为 on 表查询非驱动入口；确认时间: 2026-08-16
- **Q6**: 用户答复：按推荐——演示态 test-only fixture，提交的 statechart 干净不含演示态；确认时间: 2026-08-16
- **Q7**: 用户答复：按推荐——statechart.json 不入受保护路径（保持 agent 可编辑），加 pytest 对提交 statechart 跑 `engine.validate()`（结构 + parity 交叉校验），漂移在 CI 拦截；确认时间: 2026-08-16
- **Q8**: 用户答复：按推荐——parity 测试复用 `test_event_log.py` / `test_workflow_state_cli.py` 事件 fixture，对同一序列断言引擎 == Python；确认时间: 2026-08-16
- **Q9（新增，用户提出）**: 用户答复：测试不能只靠单元测试——parity 是"引擎==Python"的对比测试，证明不了引擎能驱动真实流程、statechart 声明正确、真实 change 生命周期不崩。**补端到端测试**三个层次：(a) 引擎 CLI 冒烟（真实归档 change 事件文件跑引擎，输出 == `flow status`）；(b) 真实生命周期（临时 change 走 flow block→confirm→advance，断言投影正确）；(c) 演示集成（注入新态后引擎真实驱动 flow block 进等待 + 确认恢复）；确认时间: 2026-08-16

## 风险

- **演示态污染真实状态机（高）**：若 `awaiting_design_confirmation` 随提交进 `flow/statechart.json`，声明化状态机含真实流程永不使用的死态；且旧 Python 拒绝该态（Q1），`flow block --awaiting` 的 choices 来自 `AWAITING_SUB_STATES`（workflow_state.py:1205）不会接受它——声明与执法两个集合不一致，后续替换时须清理。
- **parity 恒真/恒假（中）**：`derive_state` 双方都读 `transition.to`，若 parity 只断言 state 相等则基本恒真（同路径弱验证）；若断言完整投影则能覆盖 milestones/NON_STATE 跳过。Q8 决定序列来源，Confirmed Decision 6 决定断言粒度。
- **抽取破坏 workflow_methods（中）**：若实现按字面「把 phases 映射抽到 statechart」删字段，`_method_hint`/`_build_path` 立即 KeyError（Q3），`flow discover` 崩。
- **语义漂移（中）**：statechart 声明的转移与 `validate_transition` 不一致 → 结构校验捕获不了，需 parity 交叉校验（Confirmed Decision 4）在 CI 事前拦截，而非只靠事后 golden。
- **双源真值（低/已知债务）**：状态集与 awaiting 集同时存在于 `models.py`/`event_log.py` 与 `statechart.json`，P4 期间刻意并存（parity 需要），合并留替换 change，需在 design 文档记为已知债务。
- **演示规则误入产品化（低）**：`awaiting_design_confirmation` 若被当作新 awaiting 态写入 flow 命令流程，违背非目标「不扩展 awaiting 三态集合」——非目标声明 + 演示 fixture 化（Q6）双保险。
