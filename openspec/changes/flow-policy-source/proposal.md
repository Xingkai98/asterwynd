# Proposal: 开发流程策略单一源（flow-policy-source，P0）

关联跟踪 issue：[#131](https://github.com/Xingkai98/asterwynd/issues/131)（【feature】flow-policy-source：开发流程策略单一源（P0））。父 map：[#121](https://github.com/Xingkai98/asterwynd/issues/121)。

## Change Type

- primary: process
- secondary: []

## 需求

1. 新建 `scripts/flow-policy.json` 作为开发流程规则的**单一策略源**：受保护路径规则表合并 guard 硬编码 9 项 + checker `PROTECTED_PATH_RULES` 5 项 + `workflow-events.jsonl` + 策略文件自身 + 预留 `workflow-state.json`；每条规则带 `match_type(exact|prefix|contains)` + `governance(guard_only|event_explained|manifest_verified|cli_written)` + 可空 `event_types`。
2. guard 与 checker **同源加载**：guard 从 `flow-policy.json` 加载受保护路径规则（内嵌默认表作 fail-safe，策略文件缺失/损坏时 fail-closed exit 2）；checker 的 `PROTECTED_PATH_RULES` 改为从策略文件加载，替换硬编码常量。
3. 修 guard 现有缺陷：`main()` is_write 顺序（Bash 受保护路径扫描前移到 is_write 提前 exit 之前）；路径归一化（normpath / 剥离 `./`、`docs/./` 变体不再绕过）；User Confirmation 正则死锁（`_extract_user_confirmation_indexes` 容忍 `- **Q8**（分支命名）:` 后缀、`_h2_section` 跳过 fenced code block）。
4. parity 测试锁「磁盘表 == guard 内嵌默认表」+「checker 规则集 == 策略表子集」+ bash 写正则与 unconfirmed 词表纳入 parity。
5. `workflow_state.py` 新增 `policy-*` 子命令，作为策略文件的合法更新通道之一（人类直改之外的结构化通道）。
6. checker 内容门槛**阶段感知**（#123）：proposal 阶段照旧只查结构（section 存在 + 非空）；tasks 全勾时命中「自认未完成」短语级模式 → exit 2。
7. `flow-policy.json` 内定义 `phases.<phase>.agent = {provider, model}` + 顶层 `review.agent` schema（#127，P0 只定义 + JSON Schema 校验接 checker，spawn 消费留 P4）。

## 背景

P0 是 #121「开发流程可安装化」的第一阶段，目标是把开发流程规则从「guard/checker 双份硬编码」收敛为「单一策略源」。现状问题：

- 受保护路径规则**双份漂移**：`workflow_guard.py:_PROTECTED_PATH_FRAGMENTS` 9 项（子串匹配）与 `check_openspec_artifacts.py:PROTECTED_PATH_RULES` 5 项（exact/prefix → 事件类型）各自硬编码；checker 全文不读 `workflow_methods.json`，同一套治理规则两份实现。
- guard 存在 4 个**实测绕过**（根因是 `main()` 里 is_write 判断先于受保护路径扫描）：`echo > file`（部分重定向形态不匹配写模式）、`cat <<EOF`（here-doc 不在写模式）、`pathlib.write_text`（python -c 词表缺 pathlib 写方法）、`docs/./` 变体（无路径归一化）。
- guard 与 checker 的**正则提取实现重复**（`_extract_open_question_indexes` 等），parity 测试仅覆盖 Open Questions / User Confirmation 提取，未覆盖受保护路径、bash 写正则、unconfirmed 词表。
- guard 写操作门禁先于受保护路径扫描，导致「非写」判定可绕过保护。

决策依据（均已关闭并带用户确认记录）：#122（策略源落点 A：独立 `flow-policy.json`；governance 模型；fail-closed；合法更新通道）+ #123（内容门槛阶段感知）+ #127（agent schema P0 边界）。

## 非目标

- **不做 P1 事件投影**：`workflow-state.json` 落盘、guard 改读投影、`flow status`、confirm/approve 命令 append 事件——本次只在受保护路径清单中**预留** `workflow-state.json` 条目（governance 待 #128/#129 定）。
- **不做 #127 的 spawn 消费**（P4）：`phases.<phase>.agent` 只定义 schema + JSON Schema 校验，不实现按阶段 spawn agent。
- **不改 `workflow_methods.json` 的可插拔语义**：保留 management bypass（agent 可改方法映射），`flow-policy.json` 独立承载安全关键规则（#122 C1 编辑性冲突由此消解）。
- **不改 hook 部署机制**（`.claude/settings.json` / workflow_hook 部署形态不变）。
- **不做 P2 平台闸门**（GitHub required checks / approve=1 / CI guard-parity job）。
- **不引入第三方依赖**：guard 保持 stdlib-only 单文件。

## 用户故事

- agent 尝试用 `echo > docs/known-debt.md`、`cat <<EOF > openspec/specs/x/spec.md`、`python3 -c "Path(...).write_text(...)"` 或 `docs/./known-debt.md` 变体改写受保护 artifact → 全部被 guard 拦截（exit 2）。
- 开发者调整受保护路径或事件类型映射 → 只改 `scripts/flow-policy.json` 一处，guard 与 CI checker 同时生效；改后跑 parity 测试确认没有漂移。
- 策略文件被误删或损坏 → guard fail-closed（exit 2），不会静默放行。
- 完成实现后的 change 的 `Reference Implementation Research` 写了「尚未完成调研」→ artifact checker 在 tasks 全勾时报错，指明命中短语与字段。
- 开发者想声明某阶段使用特定 agent/模型 → 在 `flow-policy.json` 的 `phases.<phase>.agent` 声明，JSON Schema 校验保证格式合法（实际 spawn 是 P4）。

## 行为定义

### 策略文件 `scripts/flow-policy.json`

- 顶层结构：`{"schema": "1.0", "protected_paths": [...], "phases": {...}, "review": {...}}`。
- `protected_paths` 每条：`{"path": "<绝对或仓库相对路径模式>", "match_type": "exact"|"prefix"|"contains", "governance": "guard_only"|"event_explained"|"manifest_verified"|"cli_written", "event_types": ["..."]?}`。
- `phases.<phase>.agent`（可选）：`{"provider": "...", "model": "..."}`；顶层 `review.agent` 同理。
- 受保护路径合并清单（初版，具体 governance 分配见 design.md D4）：
  - `docs/known-debt.md`、`docs/known-issues.md`、`docs/openspec-change-backlog.md`
  - `openspec/specs/`、`openspec/changes/archive/`
  - `workflow-events.jsonl`、`gate-approvals.json`、`-review-manifest.json`、`handoff.json`
  - `scripts/flow-policy.json`（自身）、`workflow-state.json`（预留，governance 待 #128/#129 定）

### guard 同源加载与 fail-closed

- guard 启动时读 `scripts/flow-policy.json`；加载成功 → 用磁盘表；加载失败（缺失/损坏/非法 schema）→ **fail-closed exit 2**，不使用内嵌默认表继续放行。
- guard 源码内嵌同一份默认规则表（防止策略文件与 guard 发布时间差导致 hook 无规则可用），parity 测试锁「磁盘表 == 内嵌默认表」。

### checker 同源加载

- `PROTECTED_PATH_RULES` 从 `scripts/flow-policy.json` 加载（governance 为 `event_explained` 的条目，取其 path/match_type/event_types 映射），替换硬编码常量；规则集漂移由 parity 测试兜底。

### 合法更新通道

- (a) 人类直接编辑 `scripts/flow-policy.json`；
- (b) `workflow_state.py` 新增 `policy-*` 子命令（如 `policy-validate` 校验、`policy-show` 展示），结构化修改通道，P0 至少提供只读/校验能力。

### 内容门槛（#123 阶段感知）

- proposal 阶段：结构门槛照旧（section 存在 + status/reason/findings/design impact 非空）。
- tasks 全勾时：命中「自认未完成」短语级模式（如「尚未完成」「待补充」「待调研」）→ checker exit 2，错误信息指明命中短语与字段。
- 不把「来源缺失」「design impact 须 采用X而非Y」作硬红（设计质量归 building-review 维度）；`--check-archived` 不扩展。

## 验收

- `scripts/flow-policy.json` 是受保护路径规则唯一来源：guard 与 checker 均从它加载（guard 内嵌默认表仅作 fail-safe 兜底 + parity 对比）。
- 4 个实测绕过用例（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）写入回归测试并全部被拦（exit 2）。
- 策略文件缺失/损坏 → guard fail-closed exit 2（有测试覆盖）。
- 归档校验不变：全量 pytest + `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` + `check_openspec_artifacts.py` 通过。
- parity 测试覆盖：磁盘表 == guard 内嵌默认表；checker 规则集 == 策略表子集；bash 写正则与 unconfirmed 词表 guard↔checker 一致。
- 内容门槛：含「自认未完成」短语且 tasks 全勾的 change 被 checker exit 2（有测试覆盖）。
- `flow-policy.json` 中 `phases.<phase>.agent` / `review.agent` 定义经 JSON Schema 校验，非法格式被 checker 拒绝。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| 开发流程治理（guard/checker） | `workflow_guard.py` 受保护路径规则从硬编码改为策略文件加载（内嵌默认表 fail-safe）；`check_openspec_artifacts.py` 的 `PROTECTED_PATH_RULES` 改从策略文件加载 |
| guard bug 修复 | `main()` is_write 顺序调整（Bash 受保护路径扫描前移）、路径归一化、User Confirmation 正则死锁修复——行为变化是「更多绕过被拦」，正常写操作不受影响 |
| CLI | `workflow_state.py` 新增 `policy-*` 子命令（只读/校验起步） |
| Specs | `openspec/specs/dev-workflow-state-machine/spec.md` 合入单一策略源、同源加载、fail-closed、内容门槛、agent schema 要求 |
| Tests | guard/checker 同源 parity 测试、4 个绕过回归、fail-closed 测试、内容门槛测试、JSON Schema 校验测试 |
| CI | checker 行为不变（仍为 CI 权威），规则来源变化；新增规则表一致性的测试保障 |
| Docs | `AGENTS.md`（策略文件位置与更新通道）、`docs/known-debt.md`（内容门槛漏检项）如有需要 |
| Migration / compatibility | guard 行为收敛（更多绕过被拦），正常流程零行为变化；`workflow_methods.json` 可插拔语义与 management bypass 保留 |
| 明确不受影响 | AgentLoop、工具系统、Web/TUI、benchmark、配置格式、hook 部署机制 |

## Reference Implementation Research

- status: disabled
- reason: 纯内部开发流程改造，无外部同类「开发流程策略单一源」实现可比；规则收敛自本仓库既有实现（guard `_PROTECTED_PATH_FRAGMENTS` + checker `PROTECTED_PATH_RULES` + 事件类型映射），决策依据来自 #121 架构评审（2026-08-14 交接文档 `/tmp/handoff-asterwynd-flow-2026-08-14.md` + 架构评审输出，未重复运行评审工作流）。本地参考仓库不可用（`.dev/reference-repos.txt` 不存在，已确认）。
- research questions:
  - 受保护路径规则如何建模为「match_type + governance + event_types」的机器可解析表？（#122 已决策，见 issue 决策记录）
  - 同源加载形态：各自读 JSON + parity vs 生成器展开 guard 内嵌快照？（#122 Q4 P0 范围，本 change 立项时定）
- findings:
  - guard 现状 9 项子串匹配、checker 5 项 exact/prefix→事件类型；guard 有 checker 无的 4 项（`workflow-events.jsonl`/`gate-approvals.json`/`-review-manifest.json`/`handoff.json`）无事件类型，需显式标 governance。
  - 4 个实测绕过根因是 is_write 判断先于受保护路径扫描 + 路径无归一化。
- design impact:
  - 采用 #122 决策 A：独立 `scripts/flow-policy.json`（JSON 非 YAML），governance 模型消解 guard 子串 vs checker exact/prefix 差异。
  - guard 内嵌默认表 + fail-closed + parity 锁，checker 同源加载，`workflow_methods.json` 保留可插拔。
  - 4 个绕过修复进入 P0 出口验收线。

## 测试计划

- 单元测试：guard/checker 从策略文件加载、fail-closed（缺失/损坏）、路径归一化、4 个绕过回归、正则死锁修复、内容门槛、JSON Schema 校验。
- 同源 parity 测试：磁盘表 == guard 内嵌默认表；checker 规则集 == 策略表子集；bash 写正则 / unconfirmed 词表 guard↔checker 一致。
- 集成测试：策略文件变更后 guard 与 checker 同时生效；`policy-*` 子命令校验。
- 全量回归：`uv run pytest -q` + OpenSpec strict validate + artifact checker。
