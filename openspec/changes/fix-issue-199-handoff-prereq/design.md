# Design — fix-issue-199-handoff-prereq

## Context

见 `proposal.md` 与 `diagnosis.md`。核心事实：

- `cmd_artifact_event`（`scripts/workflow_state.py:925`）与 `cmd_review_manifest`（`:957`）都以 `(change_dir / "handoff.json").exists()` 为前置，这是四阶段状态机遗留（`_require_handoff` 一类检查未随状态机清理）。
- 当代 change 的合法形态由事件日志定义：首事件 `change_created`（或异构派生），无 `handoff.json`；投影为 `workflow-state.json`。
- 代码库已有现成世代判定：`_flow_is_gen1(change_dir)`（`:773`）——首事件 `initialized` 返回 True（老世代），否则 False（当代）。且有 `_flow_require_change(change_id)`（`:761`）做「目录存在 + 有 workflow-events.jsonl」的合法性判定。
- `project_workflow_state`（`agent/workflow/event_log.py:370`）已统一两代投影；`verify_projection`（`:481`）已统一两代校验。

## Goals / Non-Goals

**Goals**

- `artifact-event` 与 `review-manifest` 对无 `handoff.json` 的当代 change 可用。
- 老世代归档 change 兼容性不变。
- 非法目标（不存在的 change、非 change 目录）仍被明确拒绝。
- 其余 `handoff.json` 引用有显式处置决策，不半清理。

**Non-Goals**

- 不恢复状态机；不生成新的 `handoff.json`。
- 不动 guard / flow-policy 规则表。
- 不重构 `cmd_current` / `cmd_spawn` / `cmd_validate` 的功能面（只在「是否借本次一并清理前置」上做决策）。

## Decisions

### D1: 前置判定用「目录存在 + （`proposal.md` 或 `handoff.json`）」（grill Q1/Q2 确认）

`cmd_artifact_event` / `cmd_review_manifest` 的前置替换为：

```
change_dir 存在 且 (change_dir/"proposal.md" 存在 或 change_dir/"handoff.json" 存在)
```

理由：

- `proposal.md` 是所有**当代** change 共有的最低配置产物（`check_openspec_artifacts.check_change` 也以 `proposal.md` 缺失为 first-class error）。
- issue #199 的「建议方向」原文即「change 目录存在且 `proposal.md` 存在即可视为合法目标」。
- 比「事件日志存在」更宽：首次写入事件本身发生在事件日志创建之前（事件由本 CLI 追加），以事件日志为前置会形成自锁——首次 `artifact-event` 恰是创建日志的动作。故**不**选用 `_flow_require_change` 的「有 workflow-events.jsonl」作为唯一条件。
- **`handoff.json` 兼容分支（Q1 实测确认必需）**：`cmd_spawn`（`:881`）生成的子 change 目录只有 `handoff.json` + `workflow-events.jsonl`，**没有** `proposal.md`（`cmd_spawn` 走 `init_handoff_json` + `_save_handoff` + `write_init_event`，不写 proposal）。只认 `proposal.md` 会让这类老世代目标从「可写」（旧前置 exit 0）退化为 exit 1，与 proposal 需求 3「不破坏老世代兼容性」冲突，且现有 18 条 CLI 测试全绿也发现不了。故锚点取二者的**或**。

**不**叠加 `tasks.md` / `specs/` / 事件日志要求（Q2 确认）：change 完整性由 artifact checker 把关（`check_change` 已把 `proposal.md` 缺失当 first-class error，`_check_current_spec_mapping` 管 `specs/`），写入通道只做目标合法性判定，职责分离；在写通道里叠加文档完整性校验会把「立项即登记 backlog」这类首日事件挡在门外。

### D2: 保留老世代路径，不做世代分支的额外逻辑

`handoff.json` 存在与否不再是**唯一**前置，但**不影响**写入正确性：`append_protected_artifact_event`（`agent/workflow/event_log.py:170-189` → `_append_event:220-230`）只做 `path.open("a")` 追加，`write_review_manifest`（`agent/workflow/review_manifest.py:108-132`）只写 `reviews/*-manifest.json`，两者全程不读 `handoff.json`。因此前置解除后两代自然兼容，无需 `if gen1: ... else: ...` 写入分支。

Q1 的或分支只体现在**前置谓词**里，不引入世代判定（不需要调 `_flow_is_gen1`）。不额外加「老世代目录必须保留 `handoff.json`」的 assert（防误删）：那是写入前置之外的独立语义，加进来只会给「老世代目录 handoff 被误删」这一状态增加第二个错误来源，而本次目标是解除前置而非加固。

### D3: 其余 `handoff.json` 引用的处置 —— 四处统一记 known-debt，本次不删（grill Q3 确认）

实测同源漏网共**四处**（design 原清单只有三处，grill 补出第四处 `discover`）：

- `cmd_current`（`:539`）：读 handoff 状态并打印 `state`。停用状态机后无产出；当代等价是 `flow status`（打印投影 state）。对当代 change 恒报「没有 handoff.json」。
- `cmd_spawn`（`:881`）：wayfinding 时代子 change 派生命令，依赖父 change `handoff.json` 状态（须 `wayfinding.<gate>`）。停用状态机后无 wayfinding phase 推进，实际不可用。
- `cmd_validate`（`:996`）：校验 `handoff.json` 结构。对当代 change 恒报「没有 handoff.json」。
- `discover`（`_cmd_discover_text:364-374` / `_cmd_discover_json:404-406`）：`_load_handoff` 返回 None 时直接 `continue`，**对当代 change 完全静默**。实测：两个 gen-2 change（各有 `proposal.md` + `change_created` 事件日志）下文本模式零行输出，`--format json` 报 `"active_count": 2` 但 `"active_changes": []`。这是 CLI usage 里的**默认命令**，比 `cmd_current` 更容易误导使用者。

**处置决策（Q3）**：本次**只解除两条受保护写通道**（issue #199 的验收面）。四处统一记入 `docs/known-debt.md`（配 `protected_artifact_explained` 事件），其中 `discover` 单列一条并注明「gen-2 change 在默认命令下不可见」这一实测事实；跟踪 issue 见 [#227](https://github.com/Xingkai98/asterwynd/issues/227)。**不删子命令**：删 `spawn` 会连带删两条既有测试（`tests/test_workflow_state_cli.py:226`、`:256`），`discover` 有完整实现面（path/next_action/gate_check），属独立 API 变更，风险大于收益。

### D3a: 已知债务的附带记录项（grill 风险表）

除上述四处 CLI 漏网，另记两条同源事实到 known-debt（本次不修）：

- **伪造 change 目录可糊过 CI 闸门**：构造 `openspec/changes/<fake>/proposal.md` + 一条 `protected_artifact_explained` 事件，`check_protected_path_explanations` 返回 PASS。但该缺口在**修复前同样可行**（先跑 `flow status` 让自愈写出 `handoff.json` 即放行），D1 不使其变差，仅记录；跟踪 issue 见 [#229](https://github.com/Xingkai98/asterwynd/issues/229)。
- **`handoff.json` / `workflow-state.json` 在 active change 下不被 git 跟踪也不在 `.gitignore`**：自愈产物以未跟踪文件形式出现在 `git status`，收尾 `git add -A` 有误提交风险。口径修正：归档目录里 `archive/2026-08-15-flow-event-projection/workflow-state.json` 确实被跟踪，属历史遗留——故措辞限定为「active change 下不提交」。

### D4: 处理「`flow status` 自愈生成 handoff.json」造成的掩蔽

**实测发现的隐藏耦合**（本 change 立项时复现）：

1. 冷状态（无 `handoff.json`）下 `artifact-event` 报错 exit 1 —— 这是 issue 的核心症状。
2. 但只要先跑一次 `flow status --change <id>`，`_flow_status_projection` 的**自愈重建**分支（`workflow_state.py:828`）会调 `_refresh_workflow_state`，后者**同时写** `workflow-state.json` **和** 映射用的 `handoff.json`（`workflow_state.py:859-873`）。
3. 于是 `handoff.json` 出现在本地，`artifact-event` **立刻变可用**（实测 exit 0）。

后果：该 bug 是**顺序依赖**的——先跑 `flow status` 就把症状掩盖掉。而 `handoff.json` **不被任何 change 提交**（active 与归档 change 的 `git ls-files` 均无该文件；`workflow-state.json` 同样不提交），所以**新建的 worktree / 新 clone 冷启动时必然命中**。这解释了为什么「最近若干 change 都在 commit message 里记过这个坑」却一直没被修——本地长期存在自愈产物时不易复现。

**决策（grill Q4 确认）**：

- **D4a 维持「本次不动 `_refresh_workflow_state`」——且是证据锁定，不是偏好**。grill 实测：在一个 gen-2 change 推进到 `planning.ready_for_review` 后删掉 `handoff.json`，`flow approve --phase planning` 的 FAIL 从 4 条变 6 条，新增
  - `FAIL: Missing required file: openspec/changes/<id>/handoff.json — Workflow state file`（`agent/workflow/doc_artifact_protocol_openspec.py:45` 的 `FileRequirement(f"{resolved}/handoff.json")`）
  - `FAIL: handoff.json 不存在`（`scripts/check_phase_done.py:319-336` `_check_handoff_at_gate`）

  即真正的耦合在 **phase 协议层的必填文件表**，不在自愈。`_refresh_workflow_state` 的调用方只有 `_flow_status_projection:829` 与 `_flow_refresh_after_event:855` 两处，`grep -rn "_refresh_workflow_state" tests/` 无命中——**没有测试会因改它而变红**（这点要警惕：改动不会被现有测试拦住）。
- **D4b**：回归测试必须**从冷状态**构造，种子用「测试内直接落盘 `change_created` 事件」，**不得**用 `WorkflowManager(...).init()`——后者内部调 `init_handoff_json` + `save_handoff_json` + `write_init_event`，而 `write_init_event`（`agent/workflow/event_log.py:69-78`）写的是首事件 `initialized`，得到的是 **gen-1** change，会被旧前置判为合法而**恒绿**。既有测试 `tests/test_workflow_state_cli.py:293` / `:329` 正是这么种子的，可直接作为反例。调用 CLI 前须断言 `not (change_dir / "handoff.json").exists()`；测试内不得先跑 `flow status` / `flow advance` / `flow block` / `flow approve` / `flow confirm`（它们都会经 `_flow_refresh_after_event` / 自愈写出 handoff.json）。

**债务登记（Q4 确认）**：本次把「当代 change 的自愈仍产出退役 `handoff.json`」按**三层**记入 `docs/known-debt.md`（配 `protected_artifact_explained` 事件）：

1. 自愈仍产出退役 artifact（`_refresh_workflow_state:858-872` 同时写 `workflow-state.json` 与 `handoff.json`）；
2. phase 协议层仍把 `handoff.json` 当必填（`doc_artifact_protocol_openspec.py:45` + `check_phase_done.py:319-336`）；
3. 该文件在 active change 下未 gitignore，收尾 `git add -A` 有误提交风险。

拆成一条写清三层，避免将来只改一半；跟踪 issue 见 [#228](https://github.com/Xingkai98/asterwynd/issues/228)。

### D5: 非法目标仍拒绝

不存在的 change 目录、存在但既无 `proposal.md` 也无 `handoff.json` 的目录，两命令仍 exit 1 并给出明确错误文案。新增回归测试锁定，防止「任意路径都能写受保护事件」。

**顺序（grill 确认）**：`is_workflow_enabled` 检查保持在最前，新前置**替换**原 `handoff.json` 检查的同一位置（`:932-941`、`:961-970`）。原实现两处均为「disabled 检查 → handoff 前置 → 实际写入」；把新前置插到 disabled 检查之前会改变 workflow 禁用时的错误文案与退出路径（现为 `错误：workflow 已在 workflow_methods.json 中禁用，artifact-event 不可用` exit 1），而 `tests/test_workflow_guard.py` / `tests/test_flow_policy.py` 依赖「CLI 是被 guard 豁免的独立调用」这一前提。保持分支序不变可零风险。

### D6: spec delta 面（grill Q5 确认：MODIFIED 形态不变，正文必须补全）

**形态**：两个 MODIFIED Requirement（不新增 ADDED Requirement）——「受保护写通道对当代 change 可用」是既有 Requirement 的行为修正；另立 Requirement 会与「flow 命令与受保护路径」「Protected artifact 变更解释」重叠。

- `change-documentation/spec.md`：MODIFIED「Handoff state file artifact」。
- `dev-workflow-state-machine/spec.md`：MODIFIED「工作流事件日志与 handoff.json projection」。

**关键约束（grill 实测：`openspec archive` 是整段替换 Requirement 体，不是按 Scenario 合并）**：`openspec archive` 用 delta 正文**整段替换**正式 spec 中同名 Requirement 的正文。仓库既有先例支持「delta 正文 = 变更后完整正文」——`archive/2026-09-19-workflow-terminal-honesty/specs/web-ui/spec.md` 的 MODIFIED Requirement 正文与归档后正式 spec **逐字节相同**（含保留全部既有 Scenario）。

因此 delta 正文必须补全为**变更后的完整正文**。当前正式 spec 的「工作流事件日志与 handoff.json projection」有 8 条 Scenario，现 delta 只带 6 条（其中 3 条复用既有名），归档会静默删掉 5 条。补全后应覆盖既有的 8 条（按两代口径改写）+ 本 change 新增的 3 条。

**退役清单（显式列出，不靠 delta 缺省静默消失）**：

| 既有 Scenario | 处置 | 理由 |
|---|---|---|
| `新建 change 时初始化 workflow event log 和 handoff.json` | 改写为只保留事件日志初始化（两代共用 `workflow-events.jsonl`），删除「同时生成 handoff.json」的当代断言 | 当代 change 不再产出 `handoff.json`（本 change 的核心事实） |
| `agent 读取当前状态` | 保留 | 状态读取语义两代不变 |
| `WorkflowEngine 更新状态` | 保留 | 状态更新语义两代不变 |
| `handoff.json 被手动篡改` | 改写为「投影被手动篡改」，两代口径：gen-1 比 `handoff.json`，gen-2 比 `workflow-state.json` | `verify_projection`（`event_log.py:481`）已按两代实现，spec 应对齐 |
| `非状态 artifact 事件` | 原样保留 | 承载「支持的 artifact event type 至少含 4 类」，本 change 依赖该清单 |
| `当代 change 投影为 workflow-state.json` | 原样保留 | 既有 |
| `老世代 change 仍可投影` | 原样保留 | 既有 |
| `任意 change 可查询状态` | 原样保留 | 既有 |

**本 change 新增 3 条 Scenario**：`受保护写通道不要求 handoff.json`、`受保护写通道拒绝非法目标`、`老世代 change 的受保护写通道保持可用`。

### D7: 两条命令成功写入后刷新投影（grill Q6 确认）

`artifact-event` / `review-manifest` 成功追加后，调用与 `_flow_refresh_after_event`（`:850-856`）同源的刷新：gen-2 写 `workflow-state.json`，gen-1 维持既有 handoff replay 分支。

**问题**（grill 实测）：不刷新时，`artifact-event` 追加事件后 `verify_projection` 立刻返回 `['workflow-state.json projection does not match workflow-events.jsonl']`，`check_openspec_artifacts.py` 据此 FAIL，必须再跑一次 `flow status`（stale 自愈）才恢复。这恰好命中本 change 自己的端到端验收（tasks.md「新建无 `handoff.json` 的 change，两命令成功写入且通过 checker」）——不修则验收只在「写完之后恰好又跑了一次 `flow status`」时通过，属顺序依赖的假保护。注意：**冷状态（无 `workflow-state.json`）与 CI 新 checkout 不受影响**（`verify_projection` 在投影文件不存在时返回 `[]`），所以这是本地/顺序依赖的 papercut，不是 CI 门禁失败。

**决策**：采纳「写入后刷新」。理由：既有 spec 正文本就规定「所有状态变化 SHALL 通过 CLI 追加事件并**重新生成投影**」，刷新使实现与 spec 对齐，且让本 change 的端到端验收不依赖顺序。实现复用 `_flow_refresh_after_event(change_dir)`，不新增逻辑分支。

## Pre-Implementation Review

非平凡 change，进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 前置放松导致任意路径可写受保护事件 | 保留「目录存在 + （proposal.md 或 handoff.json）」双重判定 + 回归测试锁定非法目标拒绝 |
| **锚点只认 `proposal.md` 会打掉 spawn 子 change 等老目标**（grill Q1 实测，现有测试全绿也发现不了） | D1 加 `handoff.json` 兼容分支；补「无 proposal.md 但有 handoff.json 仍可写」回归测试 |
| **delta 静默删掉 5 条既有 Scenario**（grill Q5 实测：archive 整段替换） | D6 delta 正文补全为变更后完整正文；退役清单显式列出 |
| 半清理：只修两条 CLI，其余引用留坑 | D3 显式处置四处（含 grill 补出的 `discover`）；未清理项写入 known-debt（配事件） |
| 老世代兼容回归 | 回归测试覆盖「有 handoff.json 的老世代仍可写」+「无 proposal.md 但有 handoff.json 仍可写」 |
| spec 口径与实现不一致 | D6 同步改 spec；`current_spec_synced` 事件随收尾 |
| 顺序依赖掩蔽：先跑 `flow status` 会让 bug 不复现 | D4b 记录机制；回归测试强制冷状态构造；不依赖本地自愈产物 |
| **写入后投影 stale 让端到端验收顺序依赖**（grill Q6 实测） | D7 写入后复用 `_flow_refresh_after_event` 刷新投影 |
| 冷状态测试判别力依赖构造细节（误用 `WorkflowManager.init` → 恒绿） | D4b 钉死种子方式（直接落盘 `change_created`）+ 调用前断言无 `handoff.json` |

## Testing Strategy

- CLI 层（全部从**冷状态**构造，种子为直接落盘的 `change_created` 事件；调用前断言无 `handoff.json`）：
  - 无 `handoff.json` + `proposal.md` → `artifact-event` exit 0 且事件写入（断言事件确在 `workflow-events.jsonl`）。
  - 同条件 → `review-manifest` exit 0 且 manifest 写入（断言文件存在 + `verify_review_manifest` 为空）。
  - 老世代（`initialized` + `handoff.json`）→ 两命令仍 exit 0。
  - **无 `proposal.md` 但有 `handoff.json`（Q1 兼容分支）→ 两命令仍 exit 0**。
  - 不存在 change / 既无 `proposal.md` 也无 `handoff.json` → exit 1。
  - **写入后 `verify_projection` 为空**（D7 刷新生效，不依赖再跑 `flow status`）。
- 变异验证：把前置改回「必须有 `handoff.json`」→ 当代 change 测试变红；把前置整个去掉（任意路径可写）→ 非法目标测试变红；还原后变绿。
- 端到端：新建无 `handoff.json` change，两命令成功 + `check_openspec_artifacts.py` 通过（issue 验收原文）。
- 回归：全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
