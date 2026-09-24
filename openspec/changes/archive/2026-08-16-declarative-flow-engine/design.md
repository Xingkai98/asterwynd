# Design: 声明化流程引擎（declarative-flow-engine，P4）

## Context

现状事实（file:line 证据）：

- **流程状态机硬编码在 Python**，且有三处职责不同的语义：
  - **投影派生**（`agent/workflow/event_log.py`）：`project_workflow_state`（:370）/`_project_new_gen`（:390-420）派生 state 是**跟随每条状态事件的 `transition.to`，从不查转移表**；awaiting 建模 `_apply_blocked_to_state`（:455-468）；`AWAITING_SUB_STATES`（:51-55）、`NON_STATE_EVENT_TYPES`（:17-23）、`MILESTONE_EVENT_TYPES`（:42-48）。未知事件类型 **raise**（:259-260, :412-413）；「容忍异构」仅指无 seed 事件。
  - **转移合法性**（`agent/workflow/state_machine.py`）：`validate_transition`（:118-224）、`WITHIN_PHASE_ADJACENT`（:80-115）、`CROSS_PHASE_FORWARD`（:64-77）、`get_legal_targets`（:227-251）、`_validate_sub_state`（:42-52，**拒绝不在 `PHASE_SUB_STATES` 的 sub_state**）。合法性依赖 `trigger`（auto/handoff/human_review/human_rollback，`models.py:14`）。
  - **flow 命令**（`scripts/workflow_state.py`）：目标驱动（`flow advance --to X` / `flow approve --phase P` / `flow block --awaiting A`，:572-715）；blocked 恢复目标是**数据依赖**（最后 `blocked_entered` 的 `transition.from`，`_awaiting_recovery_target` :833-844）或按 awaiting 类型默认（`_AWAITING_RECOVERY_DEFAULTS` :755-759）。
- **可插拔方法映射**：`scripts/workflow_methods.json` 是 per-sub_state 执行方法（skill/command/agent）；`workflow_state.py:_method_hint`（:167）、`_build_path`（:237）**直接 `methods[phase][sub_state]` 索引**，删字段即 KeyError。
- **策略源已声明化（P0）**：`scripts/flow-policy.json`（#122 选 JSON 非 YAML）。
- **决策已锁定**：#121（P4）、#124（验收线 = statechart 声明 + 薄引擎 parity 等价 pin + 演示改规则不改 Python；可拆缝契约收 `flow/`）、#122（JSON 做策略源）、用户 2026-08-16（只声明流程状态机 / parity 并存 / 方案 A 分工 / 演示加 awaiting_design_confirmation）。
- **grill 关键发现**（`reviews/grill-design.md`，独立零记忆 subagent）：投影从不查转移表、`on` 表只服务合法性校验、flow 命令目标驱动——事件驱动 `apply_transition` 不足以驱动 flow 命令；演示态旧 Python 一律 raise（无透明路径）；workflow_methods 抽取破坏 `_method_hint`；blocked 恢复目标无法静态声明；未知事件类型 P1 也 raise。

## Goals / Non-Goals

### Goals

- `flow/statechart.json` 声明流程状态机：状态（`<phase>.<sub_state>`）+ `on` 转移表（每转移带 `trigger`）+ awaiting 恢复语义 + `initial`。
- 薄引擎消费声明文件，提供与现有 Python **等价**的派生、合法性校验与合法目标（parity golden 锁定）。
- 演示「改规则不改 Python」：test-only fixture 注入新态，引擎正确派生，旧 Python 不需要处理该态。
- 方案 A 分工：statechart 管流转（状态集权威声明），workflow_methods.json 管执行方法（**不删字段**）。
- 引擎收进 `flow/` 目录（#124 可拆缝契约）。

### Non-Goals

- 不做 guard/checker 规则声明化（flow-policy.json 已驱动）。
- 不替换现有 Python 状态机（parity 并存；`state_machine.py` 常量抽取留替换 change）。
- 不引入 XState/SCXML/第三方依赖（stdlib-only 薄引擎）。
- 不做可安装产物（#124）。
- 不改 paseo / AgentLoop / ToolRegistry。
- `awaiting_design_confirmation` 是 test-only 演示 fixture，不产品化、不进提交的 statechart、不扩展 awaiting 三态集合。
- 不删 `workflow_methods.json` 的 phase/sub_state 段（破坏 `_method_hint`/`_build_path`）。

## Decisions

> 范围决策已由用户 2026-08-16 确认。D1-D8 已吸收独立 subagent grill 修正（`reviews/grill-design.md`，Q 标注对应 Open Questions 推荐答案，待用户逐项确认后定稿）。

### D1: 声明文件 schema——`states` + `on`（带 `trigger`）+ `recovery` + `initial`

- 声明文件定义流程状态机，对齐现有 Python 语义（`states`/`on`/`transition` 模型借鉴 XState，但**语义锚定现有代码**）：
  ```json
  {
    "_description": "流程状态机声明（P4）。状态 = <phase>.<sub_state>；on 表每转移带 trigger（auto/handoff/human_review/human_rollback）；awaiting 态声明恢复语义。",
    "id": "dev-flow",
    "initial": "planning.exploring",
    "states": {
      "planning.exploring": {
        "on": [
          {"trigger": "auto", "to": "planning.awaiting_proposal_confirmation", "_description": "proposal 完成 → 停轮"},
          {"trigger": "auto", "to": "planning.awaiting_design_confirmation"}
        ]
      },
      "planning.awaiting_proposal_confirmation": {
        "recovery": "from_blocked_from",
        "recovery_default": {"phase": "planning", "sub_state": "writing_design"},
        "on": [{"trigger": "human_review", "to": "planning.writing_design"}]
      },
      "blocked.awaiting_user_confirmation": {
        "recovery": "from_blocked_from",
        "recovery_default": {"phase": "planning", "sub_state": "writing_design"}
      }
    }
  }
  ```
- **每转移携带 `trigger`**（Q5）：合法性依赖 trigger（同一对状态可因 trigger 不同而合法性不同），`on` 表不携带则无法表达。
- **awaiting 态声明 `recovery` 语义**（Q4）：`recovery: "from_blocked_from"`（优先动态恢复到最后 `blocked_entered` 的 from）+ `recovery_default`（兜底，镜像 `_AWAITING_RECOVERY_DEFAULTS`）。**恢复目标是数据依赖**，不是静态 `user_confirmed: <固定目标>`。
- 状态名 = `<phase>.<sub_state>`；awaiting 态建模为 `blocked.awaiting_*`；派生 any-of + 容忍（无 seed 事件）。
- **演示态（`awaiting_design_confirmation`）不进提交的 statechart**（Q6），只在 parity 测试 fixture 内注入。

### D2: 声明文件格式——JSON（confirmed 1）

- `flow/statechart.json`（非 YAML）：与 `flow-policy.json`（#122 选 JSON）一致，stdlib `json` 零依赖解析；注释用 `_description` 键约定（沿用 workflow_methods.json 写法）。
- spec delta「或等价声明文件」允许文件名落地为 `.json`。

### D3: 薄引擎 API 与落点——`flow/` 目录 + stdlib-only

- `flow/engine.py`（stdlib-only：json/argparse）：
  - `derive_state(events) -> dict`：镜像 `project_workflow_state`（完整投影：state + milestones + source_event_seq），gen-2 语义。
  - `legal_targets(state) -> list[state]`：镜像 `get_legal_targets`（:227-251）。
  - `can_transition(from, to, trigger) -> bool`：镜像 `validate_transition`（:118-224）。
  - `apply_transition(state, event)`：`on` 表查询（声明阅读用），**不是 flow 命令的驱动入口**（Q5）。
  - `validate()`：结构校验（引用完整性 / initial 存在 / 无孤立状态）+ **parity 交叉校验**（confirmed 4）——逐条把声明的转移 `(from, to, trigger)` 对 `validate_transition` 验证，声明了 Python 判非法的转移即报错 exit 2。
- 落点 `flow/` 目录（#124 可拆缝契约）：`flow/statechart.json` + `flow/engine.py`。

### D4: parity 等价 pin——完整投影 + gen-2 only（confirmed 2/3/6）

- parity 测试落 `tests/test_declarative_flow_engine.py`，随全量 pytest 进 baseline CI。
- **断言完整投影 dict**（state + milestones + source_event_seq），不只比 state（milestones 推进器只在完整投影可见，Q8/confirmed 6）。
- **只做 gen-2**（change_created 开头或无 seed）；gen-1（initialized + handoff.json 老世代）排除并在 design 注明（归档兼容逻辑与声明化目标无关）。
- parity 逐态比对 `legal_targets` / `can_transition`（投影派生读 `transition.to` 弱断言，合法性等价才是真 parity）。
- **引擎超集**：同一序列含新态时引擎能派生、旧 Python 只 replay 认识子集（Q8）。

### D5: 演示——test-only fixture（Q1/Q6 修正）

- 演示态 `awaiting_design_confirmation` **不进提交的 statechart**；parity 测试在测试内注入该态、断言引擎派生与转移、跑完即弃（fixture）。
- 「改规则不改 Python」改述为：**引擎从 statechart 生成新态（fixture 注入），旧 Python 不需要处理该态**（本 change 不要求旧 Python 认识它——现有 `_validate_sub_state`/`_apply_blocked_to_state` 对未知 sub_state 一律 raise，无透明路径，Q1）。
- spec delta 场景同步改述：删除「现有 Python 逻辑 SHALL 不需要修改（对新态透明，容忍处理）」，改为「引擎 SHALL 正确派生新态与转移，且不要求现有 Python 处理该态」。

### D6: 方案 A 分工——statechart 成权威声明，workflow_methods **不删字段**（Q3 修正）

- **不删除** workflow_methods.json 的 phase/sub_state 段（`_method_hint`/`_build_path` 直接索引，删字段即 KeyError）。
- 「抽取」改义为：**statechart 成为状态集的权威声明**，workflow_methods.json 保留每状态执行方法映射；两文件共享状态名、职责不重叠（statechart 管流转、workflow_methods 管执行）。
- 真正的流程结构（`state_machine.py` 的 `WITHIN_PHASE_ADJACENT`/`CROSS_PHASE_FORWARD`/`PHASE_SUB_STATES` 常量）抽取**留替换 change**（P4 非目标「不替换现有 Python」下不做）。
- 双源真值（models.py/event_log.py + statechart.json）记为**已知债务**（P4 期间刻意并存，parity 需要）。

### D7: 容错——引擎与 Python 严格对齐（Q2 修正）

- **未知事件类型 raise**（不是"保持状态不抛错"）——P1 对未知类型也 raise，`容忍异构`仅指无 seed 事件（Q2 修正 D7 误读）。
- `NON_STATE_EVENT_TYPES` 跳过；`MILESTONE_EVENT_TYPES` 只收集进 milestones。
- 容忍仅保留「无 seed 事件」一种。
- `apply_transition` 对 `on` 表中未声明的事件才可「保持当前状态」并在文档注明这与派生不冲突（派生仍由 `transition.to` 驱动）。

### D8: flow 命令与引擎集成——不替换，parity 对照

- P4 **不替换** `flow` 命令的现有逻辑（workflow_state.py 不改）；引擎是独立交付 + parity 测试对照。
- `flow/statechart.json` **不入受保护路径**（Q7）：保持 agent 可编辑（「改规则不改 Python」的编辑通道不被门禁堵死）；但新增 pytest：对提交的 statechart 跑 `engine.validate()`（结构 + parity 交叉校验），漂移在 CI 拦截。
- 后续替换（flow 命令切到引擎）是独立 change。

## Pre-Implementation Review

独立 subagent design grilling 已完成第一轮（`reviews/grill-design.md`，2026-08-16，run `grill-declarative-flow-engine-zero-memory`）：6 条 Confirmed Decisions + 8 条 Open Questions（Q1-Q5 BLOCKING）+ 6 条风险。Q1-Q8 停轮等用户逐项确认（每条配真实场景例子），用户答复记录于 `## User Confirmation`；确认后本 section 回填最终口径。

## Risks / Trade-offs

- **演示态污染真实状态机（高，Q1/Q6 已缓解）**：`awaiting_design_confirmation` 不进提交 statechart，fixture 内注入（D5）。
- **parity 恒真（中，Q8/confirmed 6 已缓解）**：只比 state 会恒真（双方读同一 `transition.to`）→ 断言完整投影 + 逐态比 `legal_targets`/`can_transition`（D4）。
- **抽取破坏 workflow_methods（中，Q3 已缓解）**：不删字段，抽取改义为 statechart 成权威声明（D6）。
- **语义漂移（中，confirmed 4 已缓解）**：结构校验捕获不了语义漂移 → validate() 加 parity 交叉校验（对 `validate_transition` 逐条验证，D3）。
- **演示态旧 Python raise（高，Q1 已缓解）**：无透明路径 → 改述为"引擎派生新态，旧 Python 不需要处理该态"，spec delta 同步（D5）。
- **双源真值（低/已知债务）**：models.py/event_log.py + statechart.json 并存，P4 期间刻意（parity 需要），合并留替换 change（D6）。

## Testing Strategy

**单元测试层**：
- **statechart 合法性测试**：`validate()` 结构校验 + parity 交叉校验（非法转移 exit 2）。
- **parity 测试**：复用 `test_event_log.py` / `test_workflow_state_cli.py` 事件 fixture（Q8），断言 `engine.derive_state(events) == project_workflow_state(...)`（**完整投影** state+milestones+source_event_seq）+ 逐态 `legal_targets`/`can_transition` 等价；gen-2 only。
- **演示测试（fixture）**：注入 `awaiting_design_confirmation` → 引擎正确派生；旧 Python 对该态 raise 但本 change 不要求它处理（Q1/Q6）。
- **workflow_methods 兼容测试**：不删字段后，`_method_hint`/`_build_path` 行为不变（Q3）。
- **提交 statechart 校验**：pytest 对提交的 statechart 跑 `engine.validate()`（Q7）。

**端到端测试层（用户 Q9 补充——parity 是对比测试，证明不了引擎驱动真实流程）**：
- **e2e 1（引擎 CLI 冒烟）**：真实归档 change 的 `workflow-events.jsonl` 跑引擎 `derive_state`，输出 == `flow status`（覆盖派生 + 容忍异构）。
- **e2e 2（真实生命周期）**：临时 change 走 `flow block → confirm → advance → 归档`，全程断言投影正确（覆盖目标驱动 API + blocked 恢复语义）。
- **e2e 3（演示集成）**：注入新态后引擎**真实驱动** `flow block --awaiting` 进等待 + 确认恢复（"改规则不改 Python"的端到端证据）。

**合入后人工验证**：真实 change 走一遍完整生命周期（立项→proposal→grill→building→review→归档），确认引擎/statechart/现有 Python 三者在真实流程下无回归。
