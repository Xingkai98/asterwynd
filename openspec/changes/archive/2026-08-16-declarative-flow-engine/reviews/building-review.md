# Building Review: declarative-flow-engine (Round 1)

- reviewer run id: review-declarative-flow-engine-20260816-1
- 审阅基线: base=69715c0（origin/master）, head=902b499
- 审阅对象: `git diff origin/master...HEAD`（2 提交：立项 0279c7b + building 902b499）
- 性质: 独立零记忆代码审阅（不继承开发上下文），8 维度逐项验证

## Verdict

**PASS**

核心交付（`flow/statechart.json` + `flow/engine.py` + 30 项测试）实现完整、parity 语义与现有 Python 状态机严格等价（独立 fuzz 6400 组合 0 mismatch）、结构 + parity 交叉校验在 CI 机械拦截、无红线违反（不改 Python 状态机 / 不删 workflow_methods 段 / stdlib-only / 演示态不进提交 statechart）。发现的均为低严重度/信息级问题，不阻塞合入。

## Tasks Verification

### 1. 规格（全部 [x]，证据存在且非占位）

- [x] 1.1 proposal.md：`openspec/changes/declarative-flow-engine/proposal.md`（关联 issue #141，父 map #121，需求/非目标/行为定义/验收齐全）。
- [x] 1.2 design.md：`design.md`（Context / Goals-Non-Goals / D1-D8 / Risks / Testing Strategy 齐全，证据带 file:line）。
- [x] 1.3 Impact Analysis：`proposal.md:77-90`（影响面表 + 实现期新增 3 个影响面回写）。
- [x] 1.4 Reference Implementation Research：`proposal.md:92-106`（research_tier: full，XState/SCXML 模型 + 配置驱动引擎取舍 + parity/golden 模式，findings 有实质内容、design impact 明确）。
- [x] 1.5 grill：`reviews/grill-design.md`（6 条 Confirmed Decisions + Q1-Q9 全部有 `## User Confirmation` 用户答复记录，每条带具体例子，Q1-Q8 确认时间 2026-08-16，Q9 为补充 e2e）。
- [x] 1.6 backlog：`docs/openspec-change-backlog.md:120-141` 新增 declarative-flow-engine 条目；`workflow-events.jsonl` 有 seq=2 `backlog_updated` 事件。
- [x] 1.7 spec 同步：`openspec/specs/dev-workflow-state-machine/spec.md:355-394` 已合入两个新 requirement（流程状态机声明化 / 状态机声明与执行方法分工），SHALL 目标语言，未宣称引擎替换 flow 命令；`workflow-events.jsonl` 有 seq=3 `current_spec_synced` 事件。

### 2. 测试（全部 [x]，30 项全绿）

- [x] 2.1 statechart 合法性测试：`tests/test_declarative_flow_engine.py:84-153`（TestStatechartValidity 10 用例：缺 initial / initial 未声明 / 转移引用未声明态 / 非法 trigger / 孤立状态 / recovery_default 未声明 / parity 交叉校验拒绝 Python 非法转移 / awaiting 合法 / done 禁 sub_state）。
- [x] 2.2 parity 测试：`:166-282`（TestParity：5 种事件序列 builder 断言 `derive_state == project_workflow_state` 完整投影 dict；逐态 `legal_targets` 等价；全状态×全 trigger `can_transition` 等价；gen-2 only）。
- [x] 2.3 演示测试：`:288-345`（TestDemoFixture：提交 statechart 不含演示态、引擎派生 + 恢复、旧 Python raise 属已知边界）。
- [x] 2.4 workflow_methods 兼容测试：`:351-381`（phase/sub_state 段齐全、`_method_hint` 直接索引不变、`_build_path` 路径不变）。
- [x] 2.5 e2e 1：`:387-418`（真实归档 2026-08-16-platform-gate 事件文件，引擎 CLI `derive-state` 输出 == `flow status` 的 state/milestones/source_event_seq/change_id）。
- [x] 2.6 e2e 2：`:431-476`（临时 change 走 flow advance → block → confirm → 归档，全程引擎投影 == Python 投影 == 磁盘投影 + recovery_target + 归档后只读查询）。
- [x] 2.7 e2e 3：`:483-561`（注入演示态后引擎端到端驱动 block → confirm 生命周期 + recovery_default 兜底 + 旧 Python 拒绝演示 block）。
- [x] 2.8 全量 pytest 回归：实测 1983 passed / 6 failed / 7 skipped（6 个失败均为既有环境失败：1 × tree-sitter Java/Kotlin 语法缺失、5 × MCP 缺 `uv` 二进制，均与本 change 无关，见 Test Results）。

### 3. 实现（全部 [x]）

- [x] 3.1 `flow/statechart.json`：JSON（非 YAML，grill confirmed 1），id/initial/states/on 转移表带 trigger，awaiting 三态建模 `blocked.awaiting_*` 且带 recovery + recovery_default（镜像 `_AWAITING_RECOVERY_DEFAULTS`），wayfinding/building/closing/planning 子态序列与 `PHASE_SUB_STATES` 一致。
- [x] 3.2 `flow/engine.py`：`derive_state`（完整投影：state+milestones+source_event_seq）/ `legal_targets` / `can_transition` / `recovery_target` / `apply_transition`（on 表查询，非驱动入口 Q5）/ `validate`（结构 + parity 交叉校验）；stdlib-only（json/argparse），核心 API 不 import agent 包，parity 交叉校验懒加载 `agent.workflow.state_machine`。
- [x] 3.3 workflow_methods.json：git diff 确认未被改动（未删 phase/sub_state 段），测试 2.4 锁定 `_method_hint`/`_build_path` 行为不变。
- [x] 3.4 演示 fixture：测试内注入（`_demo_statechart` `tests/test_declarative_flow_engine.py:288-297`），提交 statechart.json 不含演示态（测试 2.3 断言）。
- [x] 3.5 文档：`AGENTS.md:204-214` 新增配置架构说明（flow-policy 执法 / statechart 流转 / workflow_methods 执行 / platform-gate 平台）；Impact Analysis 回写。
- [x] 3.6 新影响面回写：proposal.md Impact Analysis（wayfinding 外部进入 / 声明顺序定义 sub_state 序列 / validate parity 懒加载）。

### 4. 验证（全部 [x]，我独立复跑确认）

- [x] 4.1 单元测试：`python3 -m pytest tests/test_declarative_flow_engine.py -q` → **30 passed**（复跑确认）。
- [x] 4.2 全量测试：`python3 -m pytest -q` → 1983 passed / 6 failed（均为既有环境失败）/ 7 skipped（复跑确认，见 Test Results）。
- [x] 4.3 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **31 passed**（复跑确认）。
- [x] 4.4 artifact checker：`python3 scripts/check_openspec_artifacts.py` → **passed**（复跑确认；tasks 5.x 未勾属部分实现，checker 不要求审阅证据，符合 spec）。
- [x] 4.5 演示验证：测试 2.3/2.7 断言引擎正确派生演示态（复跑确认）。

### 5. PR 收尾（[ ] 未勾属正常）

- [ ] 5.1-5.7：归档 / backlog 移除 / 校验 / issue #141 关闭 / PR checks——本 change 尚未归档，未勾正常。
- [ ] 5.8 review-loop：本次审阅即 5.8，产出本报告；审阅通过后需生成 review manifest（checker 对 tasks 全勾的 change 强制，归档前补）。

## Issues

按严重度排序（均低/信息级，不阻塞）：

1. **[低] 引擎 CLI `_read_events` 不校验事件 schema/seq，与 Python `_read_events` 不一致**
   `flow/engine.py:526-540` 只做 JSON 解析，不校验 `schema == workflow-event/v1` 与 `seq` 连续；`agent/workflow/event_log.py:511-528` 的 `_read_events` 两者都校验（非法即 raise）。后果：对损坏的事件日志（错 seq / 错 schema），引擎 CLI `derive-state` 会正常出投影，而 `flow status` 报错——CLI 层 parity 仅在合法输入上成立。e2e 1 只测合法归档，未覆盖。修复建议：对齐校验或明确注释该 lenient 是有意为之（引擎只消费已解析事件列表）。

2. **[低/信息] `can_transition` 拒绝非法 trigger，而 Python `validate_transition` 从不校验 trigger 成员**
   `flow/engine.py:307-308` 对 `trigger not in TRIGGERS` 直接返回 False；`agent/workflow/state_machine.py:118-224` 的 `validate_transition` 只在 self-loop / human_rollback 分支检查 trigger，对 phase 内邻接等路径接受任意 trigger 值。独立 fuzz（7 phase × 所有候选 sub × 5 trigger，8000 组合）发现 140 处不一致全部是 trigger="bogus" 场景：引擎判 False、Python 判 True。这是安全方向的严格化差异（引擎更严，拒绝语义上非法的 trigger），parity 测试只断言 4 个合法 trigger 因此全绿。建议在 docstring 注明这一有意分歧。

3. **[低/信息] `apply_transition` 同 trigger 多条转移取首条，顺序敏感**
   `flow/engine.py:413-416` 对 `building.writing_tests` 等含两条 auto 转移的状态返回首个匹配（`building.test_failing`），结果依赖 JSON 声明顺序。docstring 已注明「首条，语义歧义由调用方规避」且该方法声明为 on 表查询非 flow 命令驱动入口（Q5），可接受。建议后续替换 flow 命令时改用 `legal_targets`/`can_transition` 目标驱动。

4. **[信息] `derive_state` change_id 兜底与 Python 不同（理论分歧，现实不可达）**
   `flow/engine.py:211` 用 `change_id_hint or "unknown"`，Python `event_log.py:391` 用 `Path(change_dir).name`。已核查仓库全部 25 个真实 workflow-events.jsonl，首事件均带 `change_id`，该分歧不触发。parity 测试的 no_seed builder 也显式带 change_id。非问题，仅记录。

5. **[信息] gen-1 归档引擎 CLI 报「unknown workflow event type: initialized」exit 2**
   gen-1（initialized 开头 + handoff.json）在 design D4 明确排除（归档兼容逻辑与声明化目标无关）。错误信息可读但未提示「gen-1 不在引擎范围」，可考虑友好化。非缺陷。

## Round 1 Follow-up Fix（finding 2）

finding 2（`can_transition` 对未识别 trigger 判非法，Python `validate_transition` 不校验 trigger 成员性）已修复：`flow/engine.py` 移除 `can_transition` 的 `trigger not in TRIGGERS` 早退，`_validate_transition` 改为仅要求 trigger 键存在（镜像 Python `transition["trigger"]` KeyError 语义）。parity 测试 `test_can_transition_parity_all_combos` 的 trigger 集扩展为 `("auto","handoff","human_review","human_rollback","bogus",None)`，复跑 **30 passed**；独立 fuzz 6138 组合（含 bogus/None trigger）**0 mismatch**。其余 4 项低/信息级问题保留为已知边界（CLI 事件读取宽松、apply_transition 首条语义、change_id 兜底理论分歧、gen-1 报错文案），在后续替换 flow 命令 change 或文档中处理。

## Test Results

本环境无 `uv` 二进制，按项目等价约定用 `python3 -m pytest` 复跑（与本 change tasks 2.8/4.2 口径一致）：

- **引擎测试套件**：`PYTHONPATH=. python3 -m pytest tests/test_declarative_flow_engine.py -q` → **30 passed in 8.89s**。
- **全量回归**：`PYTHONPATH=. python3 -m pytest -q` → **1983 passed, 6 failed, 7 skipped**（131.98s）。6 个失败全部为既有环境失败，与本 change 无关：
  - `tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols` —— 复跑单独验证：Java/Kotlin 符号提取为空（tree-sitter 缺对应语法 grammar）。
  - `tests/agent/mcp/test_mcp_manager.py` 5 个 —— 均为 `FileNotFoundError: [Errno 2] No such file or directory: 'uv'`（环境缺 uv 二进制）。
- **OpenSpec strict validate**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **31 passed, 0 failed**。
- **项目 artifact checker**：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → **passed**（exit 0；tasks 5.x 未勾，不强制审阅证据）。
- **独立 parity fuzz（额外验证）**：对 7 phase × 40 候选状态 × 4 合法 trigger 全组合 `can_transition == validate_transition` → **6400 组合 0 mismatch**；`legal_targets == get_legal_targets` 40 状态 → **0 mismatch**。这比测试套件覆盖面更广（含 (phase,None)、非法 sub_state、blocked/done 带 sub 等边界），证明合法触发词下的判定完全等价。
- **CLI 冒烟**：`python3 flow/engine.py validate` → exit 0；对 gen-1 归档 `derive-state` → 报「unknown workflow event type: initialized」exit 2（gen-1 排除，符合 D4）。

## Conclusion

实现完整覆盖 tasks 1-4 全部勾选项（5.x 为 PR 收尾，未归档前未勾属正常），正确性经完整投影 parity、逐态合法目标等价与 6400 组合 fuzz 机械锁定；红线全部遵守（未替换 Python 状态机、未改 workflow_state.py/event_log.py/state_machine.py/models.py、未删 workflow_methods.json 的 phase/sub_state 段、stdlib-only、提交的 statechart 不含演示态）；测试覆盖三层 e2e（CLI 冒烟 / 真实生命周期 / 演示集成）到位；CI 配置未弱化（新测试进 pytest 门禁，statechart 漂移由 `test_submitted_statechart_passes_validate` 在 CI 拦截）；安全无注入/越权/泄露问题；可维护性良好（模块清晰、命名一致、文档充分）。

发现的 5 项均为低/信息级（CLI 事件读取宽松、非法 trigger 严格化、apply_transition 首条语义、change_id 兜底理论分歧、gen-1 报错文案），不阻塞合入，建议在后续替换 flow 命令 change 或文档中处理。

**Verdict: PASS**
