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

### D1: 前置判定用「目录存在 + proposal.md 存在」而非 `handoff.json`

`cmd_artifact_event` / `cmd_review_manifest` 的前置替换为：`change_dir` 存在且 `change_dir / "proposal.md"` 存在。理由：

- `proposal.md` 是**所有** change（两代）共有的最低配置产物（`check_openspec_artifacts.check_change` 也以 `proposal.md` 缺失为 first-class error）。
- issue #199 的「建议方向」原文即「change 目录存在且 `proposal.md` 存在即可视为合法目标」。
- 比「事件日志存在」更宽：首次写入事件本身发生在事件日志创建之前（事件由本 CLI 追加），以事件日志为前置会形成自锁——首次 `artifact-event` 恰是创建日志的动作。故**不**选用 `_flow_require_change` 的「有 workflow-events.jsonl」作为唯一条件，而用 `proposal.md` 作为目标合法性锚点。

> 待 grill 确认：是否同时要求 `specs/` 目录或 `tasks.md`（更严）——本设计倾向只要求 `proposal.md`（最小合法 change 由立项即产生）。

### D2: 保留老世代路径，不做世代分支的额外逻辑

`handoff.json` 存在与否不再是前置，但**不影响**写入正确性：`append_protected_artifact_event` 只往 `workflow-events.jsonl` 追加事件，`write_review_manifest` 只写 `reviews/` 下的 manifest，两者都不读 `handoff.json`。因此前置解除后两代自然兼容，无需 `if gen1: ... else: ...` 分支。

> 待 grill 确认：是否为老世代目录保留 `handoff.json` 相关的 assert 以做「防误删」保护。

### D3: 其余 `handoff.json` 引用的处置（`\":542\"` / `\":881\"` / `\":999\"`）

逐条判定：

- `:542` `cmd_current`：读 handoff 状态并打印 `state`。停用状态机后无产出，但 `flow status` 已是当代等价（打印投影 state）。→ **决策点**：删除 `current` 子命令（连带 parser 注册）／保留但标注 legacy 并在无 handoff 时回退到投影／完全不动。本设计倾向**保留现状 + 不改**（非本次范围，删命令属 API 移除，风险大于收益），若 grill 认为应清理则单列任务。
- `:881` `cmd_spawn`：wayfinding 时代子 change 派生命令，依赖 `handoff.json` 状态（父 change 必须 `wayfinding.<gate>`）。停用状态机后无 wayfinding phase 推进，该命令实际不可用。→ **决策点**：同 `current`，倾向保留现状不改（明确记录为已知债务而非本次范围）。
- `:999` `cmd_validate`：校验 `handoff.json` 结构。对当代 change 恒报「没有 handoff.json」。→ **决策点**：同 `current`。

> 待 grill 确认：三处是「本次一并删/改」还是「本次只修 `artifact-event` / `review-manifest`，其余记为 known-debt 另立」。**本设计倾向后者**（issue 验收只要求两条 CLI 可用 + 不破坏老归档兼容；删除 CLI 子命令属独立的 API 变更，应单独评估）。

### D4: 处理「`flow status` 自愈生成 handoff.json」造成的掩蔽

**实测发现的隐藏耦合**（本 change 立项时复现）：

1. 冷状态（无 `handoff.json`）下 `artifact-event` 报错 exit 1 —— 这是 issue 的核心症状。
2. 但只要先跑一次 `flow status --change <id>`，`_flow_status_projection` 的**自愈重建**分支（`workflow_state.py:828`）会调 `_refresh_workflow_state`，后者**同时写** `workflow-state.json` **和** 映射用的 `handoff.json`（`workflow_state.py:859-873`）。
3. 于是 `handoff.json` 出现在本地，`artifact-event` **立刻变可用**（实测 exit 0）。

后果：该 bug 是**顺序依赖**的——先跑 `flow status` 就把症状掩盖掉。而 `handoff.json` **不被任何 change 提交**（active 与归档 change 的 `git ls-files` 均无该文件；`workflow-state.json` 同样不提交），所以**新建的 worktree / 新 clone 冷启动时必然命中**。这解释了为什么「最近若干 change 都在 commit message 里记过这个坑」却一直没被修——本地长期存在自愈产物时不易复现。

**决策点**（待 grill 确认）：

- **D4a**：本次修复是否顺带让 `_refresh_workflow_state` **不再写 `handoff.json`**？不写会与「gen-1 兼容映射」的既有注释冲突（`:858` 明说「同步映射 handoff.json」），但当代 change 本不该产出该文件。倾向：**本 change 不动 `_refresh_workflow_state`**（它服务于老世代兼容投影，改动面大于收益，且移除后仍可能有别的调用方依赖该映射）；把「当代 change 的自愈不应产出退役 artifact」记为独立债务。
- **D4b**：回归测试必须**从冷状态**构造（测试内不得先调 `flow status`），否则测试会因自愈产物而恒绿——这是本 change 的「假保护」风险点，必须在测试里显式注释。

### D5: 非法目标仍拒绝

不存在的 change 目录、存在但不是 change（无 `proposal.md`）的目录，两命令仍 exit 1 并给出明确错误文案。新增回归测试锁定，防止「任意路径都能写受保护事件」。

### D6: spec delta 面

- `change-documentation/spec.md`：MODIFIED「Handoff state file artifact」——把「Every OpenSpec change SHALL include a `handoff.json` artifact」修正为「老世代 change 由 `handoff.json` 记录；当代 change 由 `workflow-state.json` / 事件日志记录，SHALL NOT 要求 `handoff.json`」。
- `dev-workflow-state-machine/spec.md`：MODIFIED 与受保护写通道相关的 Requirement（或新增 Scenario）——明确无 `handoff.json` 的当代 change SHALL 能经 `artifact-event` / `review-manifest` 写入。

> 待 grill 确认：delta 是 MODIFIED 两个 Requirement 还是「MODIFIED + ADDED 一条新 Requirement」（新 Requirement 显式写「受保护写通道对当代 change 可用」）。

## Pre-Implementation Review

非平凡 change，进入实现前由独立零记忆 subagent 执行 `/grill`，产出结构化决策记录到 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），Open Questions 停轮抛用户确认后写入 `## User Confirmation`。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 前置放松导致任意路径可写受保护事件 | 保留「目录存在 + proposal.md 存在」双重判定 + 回归测试锁定非法目标拒绝 |
| 半清理：只修两条 CLI，其余引用留坑 | D3 显式记录处置决策；未清理项写入 known-debt（配事件） |
| 老世代兼容回归 | 回归测试覆盖「有 handoff.json 的老世代仍可写」 |
| spec 口径与实现不一致 | D6 同步改 spec；`current_spec_synced` 事件随收尾 |
| 顺序依赖掩蔽：先跑 `flow status` 会让 bug 不复现 | D4 记录机制；回归测试强制冷状态构造（D4b）；不依赖本地自愈产物 |

## Testing Strategy

- CLI 层：
  - 无 `handoff.json` + `proposal.md` + `change_created` → `artifact-event` exit 0 且事件写入。
  - 同条件 → `review-manifest` exit 0 且 manifest 写入。
  - 老世代（`initialized` + `handoff.json`）→ 两命令仍 exit 0。
  - 不存在 change / 缺 `proposal.md` → exit 1。
- 端到端：新建无 `handoff.json` change，两命令成功 + `check_openspec_artifacts.py` 通过（issue 验收原文）。
- 回归：全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
