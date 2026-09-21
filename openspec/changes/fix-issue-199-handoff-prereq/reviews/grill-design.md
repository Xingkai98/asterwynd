# Grill: fix-issue-199-handoff-prereq 设计追问

## Reviewer

- run id: grill-fix-issue-199-handoff-prereq-2026-09-21-001（独立零记忆 subagent，未继承开发上下文）
- 时间: 2026-09-21
- 复核方式: 全部结论均以本仓库实跑/实读证据为准（tmp 目录冷启动复现、scratch 副本打补丁对照实验、`openspec archive` 真实归档实验、`git ls-files`/`git check-ignore`、全量 CLI 测试）

## Confirmed Decisions

- **决策**: 前置锚点必须是「change 目录存在 + `proposal.md` 存在」，**不得**改用 `_flow_require_change` 的「必须有 `workflow-events.jsonl`」口径。理由: `append_protected_artifact_event`（`agent/workflow/event_log.py:170-189` → `_append_event:220-230`）只做 `path.open("a")` 追加，`write_review_manifest`（`agent/workflow/review_manifest.py:108-132`）只写 `reviews/*-manifest.json`，两者全程不读 `handoff.json`。实测：在 tmp 目录构造 gen-1 change（首事件 `initialized` + `handoff.json`）与 gen-2 change（`change_created`、无 `handoff.json`），注入 `handoff.json` 后两者 `artifact-event` / `review-manifest` 均 exit 0，写入结果一致。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001
- **决策**: D2 成立——写入路径对两代 change 不做世代分支，老世代目录（首事件 `initialized` + `handoff.json`）里两条命令的前置解除没有副作用。理由: 见上条实测；补充一条：`_flow_is_gen1` 在此处无用武之地，因为两条命令的写入路径本就不需要知道世代，引入分支只会制造新的漂移点。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001
- **决策**: D4a 维持「本 change 不改 `_refresh_workflow_state`」，且**必须**维持——若让它不再写 `handoff.json`，当代 change 的 `flow approve` 会立刻新增两条 FAIL。理由: 实测在 gen-2 change 推进到 `planning.ready_for_review` 后删掉 `handoff.json`，`flow approve --phase planning` 的失败项从 4 条变成 6 条，新增 `FAIL: Missing required file: openspec/changes/flowchk/handoff.json — Workflow state file`（来自 `agent/workflow/doc_artifact_protocol_openspec.py:45` 的 `FileRequirement(f"{resolved}/handoff.json")`）与 `FAIL: handoff.json 不存在`（来自 `scripts/check_phase_done.py:319-336` `_check_handoff_at_gate`）。即 D4a 不是「删一条自愈写盘」，而是牵动 phase 协议的必填文件表，改动面确实大于收益。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001
- **决策**: D4b 的冷状态测试必须用「测试内直接落盘 `change_created` 事件」作种子，**不得**用 `WorkflowManager(...).init()`；且必须在调用 CLI 前断言 `not (change_dir / "handoff.json").exists()`。理由: `WorkflowManager.init`（`agent/workflow/manager.py:67-74`）内部调 `init_handoff_json` + `save_handoff_json` + `write_init_event`，而 `write_init_event`（`agent/workflow/event_log.py:69-78`）写的是首事件 `initialized` —— 用它做种子的 change 是 **gen-1**，会被新前置的旧实现（handoff 存在）判为合法而恒绿。既有测试 `tests/test_workflow_state_cli.py:293` 与 `:329` 正是这么种子的，可直接作为反例。测试内私人 `tmp_path` 保证跨测试不共享自愈产物；`_run_cli` 以 `cwd=tmp_path` 起子进程，只要不在同一测试内先跑 `flow status` / `flow advance` / `flow block` / `flow approve` / `flow confirm`，就不会触发自愈（实测：冷状态 `artifact-event` exit 1 + 报错 '没有 handoff.json'；先跑一次 `flow status --change <id>` 后同一命令 exit 0，目录里凭空多出 `handoff.json` 与 `workflow-state.json`）。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001
- **决策**: D5 的顺序确定：`is_workflow_enabled` 检查保持在最前，新的合法性前置**替换**原 `handoff.json` 检查的同一位置（`scripts/workflow_state.py:932-941`、`:961-970`）。理由: 原实现两处均为「disabled 检查 → handoff 前置 → 实际写入」；把新前置插到 disabled 检查之前会改变 workflow 禁用时的错误文案与退出路径（现为 `错误：workflow 已在 workflow_methods.json 中禁用，artifact-event 不可用` exit 1），而 `tests/test_workflow_guard.py` / `tests/test_flow_policy.py` 都依赖「CLI 是被 guard 豁免的独立调用」这一前提，保持分支序不变可零风险。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001
- **决策**: 本 change 不改 artifact checker / guard，也不会被它们的既有规则反锁。理由: `check_openspec_artifacts.py` 对受保护路径的判定只扫 `openspec/changes/**/workflow-events.jsonl` 里的事件（`:1108-1141`），不依赖 `handoff.json`；`workflow_guard.py:246-269` 的白名单正则只认「独立的 `workflow_state.py artifact-event|review-manifest|policy-*|flow status|confirm|approve|block|advance`」调用，本次不动该名单。基线实跑：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → `OpenSpec artifact checks passed`；`npx @fission-ai/openspec@1.4.1 validate --all --strict` → `30 passed, 0 failed`；`uv run pytest tests/test_workflow_state_cli.py -q` → `18 passed`。来源: grill-fix-issue-199-handoff-prereq-2026-09-21-001

## Open Questions

- **Q1**: D1 的锚点「必须有 `proposal.md`」会打掉一类老目标的写入能力：由 `spawn` 新建的子 change（以及任何尚未落 `proposal.md` 的老世代 change）。是否接受这个回归，还是把锚点放宽为「`proposal.md` 存在 **或** `handoff.json` 存在」？

  背景与权衡（实测，非推断）：用 scratch 副本把 D1 前置原样打进 `scripts/workflow_state.py` 后对照运行 —— `spawn --from parent-map --changes child-b` 生成的 `child-b/` 只含 `handoff.json` + `workflow-events.jsonl`（`cmd_spawn` 走 `init_handoff_json` + `save_handoff`，不写 proposal），旧前置对 `artifact-event` 返回 exit 0，新前置返回 `错误：change 'child-b' 不是合法 change（目录或 proposal.md 缺失）` exit 1。同类反例：手工构造的「首事件 `initialized` + `handoff.json`、无 `proposal.md`」目录，旧 exit 0 / 新 exit 1。这与 proposal「需求 3：不破坏老世代归档 change 的兼容性」和 design「非目标：老世代路径行为不变」直接冲突，而现有测试全绿也发现不了（`tests/test_workflow_state_cli.py` 没有一条覆盖「无 proposal.md 的老世代目标」）。
  推荐答案：锚点改为「目录存在 **且**（`proposal.md` 存在 **或** `handoff.json` 存在）」。这样当代 change 仍以 `proposal.md` 为准（新 change 立项即产出它），老世代（`spawn` 子 change、无 proposal 的历史 change）保持原行为；同时明确写进 spec 与回归测试（补一条「无 proposal.md 但有 handoff.json 的老世代仍可写」）。

- **Q2**: D1 是否要同时要求 `tasks.md` / `specs/`（把「最小合法 change」抬高一档）？

  背景与权衡（反例实测）：**不能**要求事件日志，否则自锁 —— `_flow_require_change`（`:762-770`）要求 `workflow-events.jsonl` 存在，但首次 `artifact-event` 恰恰是创建该文件的动作；本 change 自己的 `workflow-events.jsonl` 首事件就是 seq 1 `backlog_updated`（立项登记写进一个当时还没有事件日志的目录），换成事件日志锚点它自己就写不进去。要求 `tasks.md` / `specs/` 则会把「立项即登记 backlog / 说明债务」这类首日事件挡在门外（本 change 的首事件也是这么产生的），且这些字段的可信度并不比 `proposal.md` 高。
  推荐答案：写入通道只要求 `proposal.md`（**再加 Q1 的 handoff 兼容分支**）；「change 是否完整」交给 artifact checker（`check_change` 已把 `proposal.md` 缺失当 first-class error，`_check_current_spec_mapping` 管 `specs/`）把关，两条通道职责分离，不要在写通道里叠加文档完整性校验。

- **Q3**: D3 的「三处 legacy 引用」清单不完整（实测至少四处）；本次的处置范围定在哪一档？

  背景与权衡（实测新增第四处）：`discover` 对当代 change 完全静默 —— 在 tmp 目录放两个 gen-2 change（各自有 `proposal.md` + `change_created` 事件日志）后运行 `discover`，文本模式表头下**零行输出**，`discover --format json` 报 `"active_count": 2` 但 `"active_changes": []`（`_cmd_discover_text:364-374` / `_cmd_discover_json:404-406` 在 `_load_handoff` 返回 None 时直接 `continue`）。这是 design/issue/diagnosis 都没点到的同源漏网，比 `cmd_current`（停用后本就无产出）更容易误导使用者，因为它正是 CLI usage 里的默认命令。相比之下 `cmd_current`(:539) / `cmd_validate`(:996) / `cmd_spawn`(:875) 三条 route 都在老世代语义上，其中 `spawn` 还有两条既有测试（`tests/test_workflow_state_cli.py:226-290`）直接依赖 `handoff.json` + `verify_handoff_projection`。
  推荐答案：本次**只在受保护写通道**做解除（issue #199 的验收面），`current` / `validate` / `spawn` / `discover` 四处统一记为 known-debt 并写进 `docs/known-debt.md`（配 `protected_artifact_explained` 事件），其中 `discover` 单列一条、注明「gen-2 change 在默认 discover 命令下不可见」这一实测事实。不建议本次删子命令：删 `spawn` 连带删两条测试、`discover` 有完整实现面（path/next_action/gate_check），属独立 API 变更，风险大于收益。

- **Q4**: 确认 D4a 的收口口径：本次**不动** `_refresh_workflow_state`，但把「协议层仍把 `handoff.json` 当必填」记为独立债务 —— 是否接受？

  背景与权衡（实测证据见 Confirmed Decisions 第 3 条）：`_refresh_workflow_state`（`:858-872`）的调用方只有两处 —— `_flow_status_projection:829`（自愈重建）与 `_flow_refresh_after_event:855`（block/confirm/approve/advance 写事件后刷新），`grep -rn "_refresh_workflow_state" tests/` 无命中，所以**没有测试会因改它而变红**（这点要警惕：改动不会被现有测试拦住）。但真正的耦合不在自愈，而在 `agent/workflow/doc_artifact_protocol_openspec.py:45` 的 `FileRequirement(..., "handoff.json")` 与 `scripts/check_phase_done.py:319-336`：只要 `handoff.json` 不再存在，`flow approve` 立即多两条 FAIL（已实测）。另有一条附带事实：`handoff.json` / `workflow-state.json` 在 active change 下**既不被 git 跟踪也不在 `.gitignore`**（`git ls-files` 无命中；`git check-ignore` exit 1，仅 `.handoff/` 被忽略），自愈产物会以未跟踪文件形式出现在 `git status` 里，收尾 `git add -A` 有被误提交的风险。
  推荐答案：接受 D4a 不改；债务条目写清三层（自愈仍产出退役 artifact / 协议层 FileRequirement 仍要求它 / 该文件未 gitignore 易被误提交），并把「当代 change 自愈不该产出 handoff.json」与「phase 协议要改读投影」拆成一条，避免将来只改一半。

- **Q5**: D6 的 delta 形态怎么定？现状（MODIFIED 两个 Requirement）会**静默删掉 5 条既有 Scenario** —— 是否按「delta 正文必须是变更后的完整 Requirement 正文」重写？

  背景与权衡（实测 `openspec archive` 行为）：用仓库真实的 openspec CLI 在 tmp 副本里跑 `archive fix-issue-199-handoff-prereq --yes`，结果是对 `dev-workflow-state-machine/spec.md` 输出 `~ 1 modified` 并把**整段 Requirement 体**替换为 delta 体。归档后该 Requirement 的 Scenario 只剩 delta 里的 6 条：`当代 change 投影为 workflow-state.json` / `老世代 change 仍可投影` / `任意 change 可查询状态` / `受保护写通道不要求 handoff.json` / `受保护写通道拒绝非法目标` / `老世代 change 的受保护写通道保持可用`。当前正式 spec 里另外 5 条被无声删除：`新建 change 时初始化 workflow event log 和 handoff.json`、`agent 读取当前状态`、`WorkflowEngine 更新状态`、`handoff.json 被手动篡改`、`非状态 artifact 事件`（后两条分别承载「投影与事实源不一致即拒绝」和「支持的 artifact event type 至少含 4 类」，都是被代码实际执行的口径）。`change-documentation` 侧同样整段替换：3 条英文 Scenario 被 3 条中文改写 + 1 条新增覆盖（语义无丢失，属有意改写）。仓库既有先例支持「delta 正文 = 变更后完整正文」：`archive/2026-09-19-workflow-terminal-honesty/specs/web-ui/spec.md` 的 3 个 MODIFIED Requirement，其正文与归档后正式 spec 逐字节相同（含保留全部既有 Scenario）。
  推荐答案：**MODIFIED 两个 Requirement 的形态是对的**（两条 Requirement 在两份正式 spec 里都已存在，归档按名合并，实测 `~ 1 modified` × 2，strict validate 通过；不需要 ADDED 新 Requirement —— 「受保护写通道对当代 change 可用」是既有 Requirement 的行为修正，另立 Requirement 会与 `flow 命令与受保护路径` / `Protected artifact 变更解释` 三条重叠）。但 delta 正文必须补全：把上述 5 条按新口径改写后保留（例如 `新建 change 时初始化 workflow event log 和 handoff.json` → 只保留事件日志、`handoff.json 被手动篡改` → `投影被手动篡改`（两代口径：gen-1 比 handoff、gen-2 比 workflow-state）、`非状态 artifact 事件` 原样保留），确需退役的（如「新建 change 即生成 handoff.json」）在 design.md 的 D6 里显式列出退役清单与理由，不允许靠 delta 缺省静默消失。

- **Q6**: `artifact-event` / `review-manifest` 写完事件后是否顺带刷新投影？不刷新会让本 change 自己的端到端验收条件不稳。

  背景与权衡（实测）：在 tmp 目录里按「先 `flow status`（自愈产出投影）→ 再 `artifact-event`」的真实顺序操作后，`verify_projection(change_dir)` 直接报 `['workflow-state.json projection does not match workflow-events.jsonl']`；此时 `scripts/check_openspec_artifacts.py` 的 `_check_handoff_json:956-958` 会把这条挂到 change 上报错。再跑一次 `flow status` 才恢复 `[]`（`flow status` 的 stale 自愈顺带修好）。这正好命中 tasks.md 最后一条验收「新建一个无 `handoff.json` 的 change，两命令均成功写入且通过 `scripts/check_openspec_artifacts.py`」—— 该验收当前只有「写完之后恰好又跑了一次 flow status」才会通过，属顺序依赖的假保护。
  推荐答案：两条命令在成功追加后调用与 `_flow_refresh_after_event` 同源的刷新（gen-2 写 `workflow-state.json`，gen-1 维持既有 handoff replay 分支），使「写完即可被 checker 校验」；若不接受扩大改动面，退而求其次：在 tasks.md 的端到端验收里显式写成「写入后先 `flow status` 再跑 checker」并在测试注释里写明这是顺序依赖，且新增一条单测锁定「`artifact-event` 后 `verify_projection` 为空」——但这样等于把 stale 窗口固化成规格，不推荐。

## User Confirmation

- **Q1**: 用户答复：锚点放宽为「change 目录存在 且（`proposal.md` 存在 或 `handoff.json` 存在）」，保住 spawn 子 change 等无 proposal 老世代的可写能力，并补一条「无 proposal.md 但有 handoff.json 的仍可写」回归测试；确认时间: 2026-09-21
- **Q2**: 用户答复：写通道只要求 `proposal.md`（加 Q1 的 handoff 兼容分支），不叠加 `tasks.md`/`specs/`/事件日志要求——change 完整性交给 artifact checker，职责分离；确认时间: 2026-09-21
- **Q3**: 用户答复：本次只解除 `artifact-event` / `review-manifest` 两条受保护写通道；`discover` / `current` / `validate` / `spawn` 四处统一记入 `docs/known-debt.md`（配 `protected_artifact_explained` 事件），`discover` 单列一条注明「gen-2 change 在默认命令下不可见」；不删子命令、不改受保护 spec、不动既有测试；确认时间: 2026-09-21
- **Q4**: 用户答复：接受 D4a 不改 `_refresh_workflow_state`；债务条目写清三层——自愈仍产出退役 artifact / phase 协议层（`doc_artifact_protocol_openspec.py:45` + `check_phase_done.py:319-336`）仍把 `handoff.json` 当必填 / 该文件未 gitignore 且收尾 `git add -A` 有误提交风险；确认时间: 2026-09-21
- **Q5**: 用户答复：MODIFIED 形态不变，但 delta 正文必须重写为「变更后的完整 Requirement 正文」，保留既有 8 条 Scenario（按两代口径改写：如「新建 change 生成 handoff.json」改为只保留事件日志、「handoff.json 被手动篡改」改为「投影被手动篡改」两代口径、「非状态 artifact 事件」原样保留）；确需退役的在 design.md D6 显式列退役清单与理由，不靠 delta 缺省静默消失；确认时间: 2026-09-21
- **Q6**: 用户答复：两条命令成功追加事件后，调用与 `_flow_refresh_after_event` 同源的刷新（gen-2 写 `workflow-state.json`，gen-1 维持 handoff replay），使「写完即可被 checker 校验」，本 change 端到端验收不依赖顺序；确认时间: 2026-09-21

## 风险

- **【高】delta 静默删除 5 条既有 Scenario**（见 Q5 实测）：`openspec archive` 是整段替换，当前 delta 归档后会丢掉 `非状态 artifact 事件`（正是本 change 依赖的 artifact event type 清单）与 `handoff.json 被手动篡改`（对应的 `verify_projection` 拒绝逻辑仍被 checker 执行）。docs/specs 属受保护路径，此处的口径丢失日后很难追溯，必须在归档前补全 delta 正文。
- **【高】D1 锚点与 proposal 自身验收冲突**（见 Q1 实测）：`spawn` 子 change 与任何无 `proposal.md` 的老世代 change 会从「可写」变成「exit 1」，而现有测试无一覆盖，属会被绿灯放过的行为回归。
- **【中】冷状态测试的判别力依赖构造细节**（见 Confirmed Decisions 第 4 条）：任务清单里的「老世代兼容」用例若照抄 `WorkflowManager.init` 的种子方式，得到的是 gen-1 change，无法证明新前置对 gen-2 生效；反之若 gen-2 用例误用 `init`，会退化成恒绿。
- **【中】`discover` 的第四处同源漏网**（见 Q3 实测：`active_count: 2` 但 `active_changes: []`）：不在 issue #199 与 design 的风险表里，若不记入 known-debt 就会成为新的隐性债务。
- **【中】验收路径的顺序依赖**（见 Q6 实测）：`artifact-event` 后不刷新投影，`verify_projection` 立刻报 stale；本 change 的端到端验收与「跑 checker」这一步会因此变成偶发通过。
- **【低】锚点放宽不额外削弱防伪**：实测在 tmp 仓库里构造 `openspec/changes/totally-fake-change/proposal.md` + 一条 `protected_artifact_explained` 事件，`check_protected_path_explanations` 返回 PASS（伪造目录能糊过 CI 闸门）；但同一手法在**修复前**同样可行 —— 先跑 `flow status --change totally-fake-change` 让 CLI 自愈写出 `handoff.json`（事件首条为 non-state 事件也能投影成功），旧前置随即放行。即该缺口是既有属性，D1 不使其变差，本次不必连带修复，但值得在 known-debt 里与 D4 债务并列记录。
- **【低】事实性小口径**：proposal/diagnosis 称 `handoff.json`、`workflow-state.json` 都不被提交 —— 对 active change 成立（`git ls-files` 无命中、`git status` 干净），但归档目录里 `archive/2026-08-15-flow-event-projection/workflow-state.json` 确实被跟踪（历史遗留），措辞宜限定为「active change 下不提交」。
