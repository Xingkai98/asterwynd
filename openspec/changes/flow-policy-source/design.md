# Design: 开发流程策略单一源（flow-policy-source，P0）

## Context

P0 目标是把开发流程规则从「guard/checker 双份硬编码」收敛为「单一策略源」。现状事实（file:line 证据）：

- `scripts/workflow_guard.py`（426 行，stdlib-only 单文件，PreToolUse hook）：
  - `_PROTECTED_PATH_FRAGMENTS`（:62-72）9 项子串匹配，`_mentions_protected_path`（:160-162）做 `fragment in normalized` 判定。
  - `_MANAGEMENT_FILES = {"workflow_methods.json", "workflow_hook.example.json"}`（:61），main() 对这两个文件**写操作 always bypass（exit 0）**（:381-383）——workflow_methods.json 当前是 agent 可自由编辑的。
  - `_BASH_WRITE_PATTERNS`（:75-111）+ `_READ_ONLY_ALLOW`（:113-128）硬编码；`_is_write_bash`（:131-157）尾部「unknown command → conservative: treat as safe」。
  - grill gate（issue #95）：`_current_change_id`（:172-201）、`_grill_evidence_missing`（:204-242）、`_UNCONFIRMED_*` 词表（:249-257）、`_extract_open_question_indexes`/`_extract_user_confirmation_indexes`/`_h2_section`（:274-337）、`_is_change_doc_write`（:340-354）。
  - `main()`（:359-422）：**is_write 判定先于受保护路径扫描**——Bash 命令被判定为「非写」时直接 exit 0，受保护路径扫描（:394-400）根本不会执行（4 个绕过根因）。
  - `_resolve_changes_dir`（:33-50）已读 workflow_methods.json 的 `doc_artifact.paths.change_dir_template`。
- `scripts/check_openspec_artifacts.py`（1153 行，CI 权威）：
  - `PROTECTED_PATH_RULES`（:122-128）5 项 exact/prefix → 事件类型，**checker 全文不引用 workflow_methods.json**——同一套治理规则两份实现。
  - `UNCONFIRMED_EXACT`/`UNCONFIRMED_STRONG`（:91-101）与 guard `_UNCONFIRMED_*`（:249-257）重复实现；parity 测试（`tests/test_workflow_guard.py:308`）只锁 Open Questions / User Confirmation 正则提取，未覆盖受保护路径/bash 写正则/词表。
  - 已实现受保护路径事件解释检查（`check_protected_path_explanations` :777-798）、backlog 一致性（:1008-1034）、review manifest 验证（:732-774）、内容门槛结构检查（`_check_reference_implementation_research` :304-356）。
- `scripts/workflow_methods.json`（263 行，schema 1.2 可插拔方法映射）：`doc_artifact`/`ticket_tracker`/`workflow`/`wayfinding`/`planning`/`building`/`closing`/`on_ramps`/`cross_cutting`/`review_protocol` 节；`ticket_tracker.repo=Xingkai98/asterwynd` 等 repo 专属字段；`_description` 明言「修改此 JSON 即可替换每个 sub_state 使用的 skill/command，无需改代码」。
- `openspec/config.yaml`：已存在 `routing` 节（planning/reviewing/building/code-review/closing 的 `executor`/`session_mode`）——#127 Q5 待定关系。
- 4 个实测绕过（根因 is_write 先于 protected 扫描）：`echo > file`、`cat <<EOF`、`pathlib.write_text`（python -c 词表缺 pathlib 写方法）、`docs/./` 变体（无路径归一化）。

决策依据（均已关闭并带用户确认记录）：
- #122（2026-08-14）：选 A 独立 `scripts/flow-policy.json`；规则表 `match_type + governance + 可空 event_types`；guard 内嵌默认表 fail-safe + 缺失/损坏 fail-closed exit 2；合法更新通道=人类直改 + `policy-*` 子命令；flow-policy.json 入受保护路径；workflow_methods.json 保留可插拔 + management bypass。遗留 Q4 P0 范围待定。
- #123（2026-08-14）：内容门槛阶段感知；「来源缺失/设计对比」不作硬红；`--check-archived` 不扩展；漏检记 known-debt。
- #127（2026-08-14）：`phases.<phase>.agent={provider,model}` + 顶层 `review.agent`；删 tool；不叫 executor；provider 命名空间钉 paseo 侧；P0 只定义 schema + JSON Schema 校验接 checker，spawn 留 P4。

## Goals / Non-Goals

### Goals

- `scripts/flow-policy.json` 成为受保护路径规则唯一来源：guard 与 checker 均从它加载。
- guard 内嵌默认表（fail-safe）+ 策略文件缺失/损坏 fail-closed（exit 2）。
- 修 guard 4 个绕过 + 路径归一化 + User Confirmation 正则死锁。
- parity 测试锁「磁盘表 == 内嵌默认表」+「checker 规则集 == 策略表子集」+ bash 写正则/词表纳入。
- `workflow_state.py` 提供 `policy-*` 结构化通道。
- checker 内容门槛阶段感知（#123）+ `flow-policy.json` agent schema 定义与 JSON Schema 校验（#127 P0 边界）。

### Non-Goals

- P1 事件投影（workflow-state.json 落盘 / guard 读投影 / `flow status` / confirm/approve append 事件）——只预留受保护路径条目。
- #127 spawn 消费（P4）。
- 改 `workflow_methods.json` 可插拔语义或 management bypass。
- 改 hook 部署机制、`.claude/settings.json`。
- P2 平台闸门（GitHub required checks / approve=1 / CI guard-parity job）。
- 第三方依赖（guard 保持 stdlib-only）。

## Decisions

### D1: 策略文件位置与格式

`scripts/flow-policy.json`，JSON（非 YAML）——guard stdlib-only 硬约束（Python stdlib 无 YAML）。顶层结构：

```json
{
  "schema": "1.0",
  "protected_paths": [
    {"path": "docs/known-debt.md", "match_type": "exact", "governance": "event_explained", "event_types": ["protected_artifact_explained"]}
  ],
  "phases": {
    "wayfinding": {"agent": {"provider": "claude", "model": "claude-sonnet-5"}}
  },
  "review": {"agent": {"provider": "codex", "model": "gpt-5.4"}}
}
```

### D2: 受保护路径规则表 schema 与 match_type 语义

每条规则：`path`（仓库相对路径模式）+ `match_type` + `governance` + 可空 `event_types`。

- `match_type`：`exact`（归一化后路径精确相等）/ `prefix`（归一化后路径以该前缀开头）/ `contains`（归一化路径或命令文本中包含该片段）。
- `governance` 四种语义（#122 决策）：
  - `event_explained`：变更需 `workflow-events.jsonl` 结构化解释事件（`event_types` 必填）——checker 对 CI diff 强制，guard 对 agent 直写拦截。**规则 schema 校验**（grill 缺陷 4）：guard/checker 加载时校验每条 `event_explained` 规则必须带非空 `event_types`，缺失视为策略文件非法 → fail-closed（checker 对空事件类型会判任何事件不合法导致全量误报，见 `check_openspec_artifacts.py:863-869`）。
  - `cli_written`：只允许人类直改或 `policy-*`/`artifact-event` 等 CLI 通道写，guard 拦截 agent 直写，checker 不要求事件（CLI 自身即合法通道）。
  - `manifest_verified`：变更由 review manifest 内容寻址校验绑定（`-review-manifest.json`），guard 拦截 agent 直写。
  - `guard_only`：本地 backstop，仅 guard 拦截 agent 直写，checker 无 diff 规则（历史遗留/状态机仪式停用后不活跃）。
- **Bash 扫描与 match_type 的关系**（关键设计，grill 修正 + Q3/Q7 待确认）：guard 对 Write/Edit 的 `file_path` 与 checker 对 git diff 的 `changed_paths` 都按归一化路径 + match_type 精确解释。guard 对 **Bash 命令文本**的受保护路径扫描**不是 blanket contains**（会误拦 `git diff openspec/specs/...` 等只读命令、破坏 `test_guard_allows_workflow_state_cli_commands`，grill 已实测），而是：
  1. 从命令文本中提取路径 token（含重定向目标 `>`/`>>`/`tee` 后、here-doc `<<` 前、`cp/mv/touch` 等目标位置），normpath 归一化后按 match_type 匹配；
  2. 受保护路径检查**前移到 is_write 判定之前**（修 4 个绕过根因），但**只在命令具有写意图且非 read-only allow 且非豁免 CLI 写通道时 exit 2**；
  3. 显式豁免 `workflow_state.py (artifact-event|review-manifest|policy-*)` 合法写通道（现状 `test_guard_allows_workflow_state_cli_commands` 期望 rc=0）。
  该语义写入 parity 测试与回归测试固定预期。

### D3: 同源加载形态（#122 Q4 P0 范围，推荐完整 A）

**完整 A（推荐）**：guard 与 checker 各自从 `scripts/flow-policy.json` 加载规则。
- guard：加载成功后用磁盘表；加载失败（缺失/损坏/非法 schema）→ **fail-closed exit 2**。源码内嵌同一份默认规则表**仅作 parity 对比锚点，从不参与运行时 enforcement**（grill 缺陷 5 + Q10 确认：消除「窗口期兜底」与 fail-closed 的表述矛盾，避免实现时误做运行时 fallback）。
- checker：`PROTECTED_PATH_RULES` 改为从策略文件加载（取 `governance == event_explained` 条目，映射 path/match_type/event_types），替换硬编码常量（:122-128）；策略文件缺失/损坏/非法 → fail-closed（CI 门禁不能静默跳过受保护路径检查）。
- parity 测试**链式断言**（grill 风险补充）：guard 内嵌默认表 `event_explained` 子集 == checker 加载集 == 磁盘表 `event_explained` 子集（避免「checker 从同一磁盘文件加载」导致 parity 平凡化）。

**P0 变体（备选）**：checker 暂保持硬编码，parity 测试锁「checker 5 项 == 策略表子集」作为过渡——改动更小，但 checker 侧仍是双份源，非真单一源。

### D4: 受保护路径合并清单与 governance 分配（初版，Q3 确认）

| path | match_type | governance | event_types | 来源 |
|---|---|---|---|---|
| `docs/known-debt.md` | exact | event_explained | `protected_artifact_explained` | guard+checker |
| `docs/known-issues.md` | exact | event_explained | `protected_artifact_explained` | guard+checker |
| `docs/openspec-change-backlog.md` | exact | event_explained | `backlog_updated` | guard+checker |
| `openspec/specs/` | prefix | event_explained | `current_spec_synced` | guard+checker |
| `openspec/changes/archive/` | prefix | event_explained | `change_archived` | guard+checker |
| `workflow-events.jsonl` | contains | cli_written | — | guard 有 / checker 无 |
| `gate-approvals.json` | contains | guard_only | — | guard 有 / checker 无 |
| `-review-manifest.json` | contains | manifest_verified | — | guard 有 / checker 无 |
| `handoff.json` | contains | guard_only | — | guard 有 / checker 无 |
| `scripts/flow-policy.json` | exact | cli_written | — | 新增（#122：策略文件自身入受保护） |
| `workflow-state.json` | contains | cli_written | — | 预留（#128/#129 定，本期不实现） |

### D5: workflow_methods.json 保留可插拔（#122 C1 消解）

`workflow_methods.json` 与 `workflow_hook.example.json` **保持 management bypass**（agent 可改方法映射），不入受保护清单；安全关键规则全部收进 `flow-policy.json`（governance=cli_written，agent 不可写）。安全边界：策略（安全关键，不可 agent 改）与映射（可插拔，agent 可换）物理分离。

### D6: 合法更新通道

- (a) 人类直接编辑 `scripts/flow-policy.json`（governance=cli_written 允许人类写）。
- (b) `workflow_state.py` 新增 `policy-*` 子命令：**推荐 P0 提供 `policy-show`（展示生效规则）+ `policy-validate`（校验 schema 合法性与默认表 parity）+ `policy-set`（写通道，至少支持替换单条规则/整体 apply，原子写 tmp+rename）**——写通道同时解决 flow-policy.json 的**自举/迭代死锁**（grill 缺陷 2 + Q4/Q8 待确认）：guard 对缺失策略文件 fail-closed 且 governance=cli_written 拦截 agent Write/Edit，本 change 自己的 task 3.1（创建策略文件）若无合法写通道会被自己改造的 guard 锁死。`policy-set` 作为 guard 显式豁免的合法写通道。
- 否掉 (c) 通过 workflow-events 解释事件例外改写策略（#122 决策：与红线「策略不可 agent 改」冲突）。

### D7: guard bug 修复

- **main() is_write 顺序**：把 Bash 受保护路径扫描前移到 is_write 提前 exit 之前（修 4 个绕过根因），但**不是 blanket contains 命中即 exit 2**（grill 缺陷 1 实测会误拦 `git diff openspec/specs/...`、`cat docs/known-debt.md` 等只读命令并破坏 `test_guard_allows_workflow_state_cli_commands`），而是按 D2 的写意图感知语义：提取路径 token → normpath → match_type 匹配，**只在命令有写意图且非 read-only allow 且非豁免 CLI 写通道时 exit 2**。Write/Edit 保持 is_write=True → 直接进受保护检查。
- **路径归一化**：Write/Edit 的 `file_path` 与 Bash 命令中提取的路径先 `os.path.normpath`（剥离 `./`、解析 `..`），再按 match_type 匹配；`docs/./known-debt.md` 不再绕过。
- **User Confirmation 正则死锁（guard 与 checker 同步修复，grill 缺陷 3 + Q9）**：`_extract_user_confirmation_indexes` 容忍 `- **Q8**（分支命名）:` 后缀（当前正则 `^-\s+\*\*Q(\d+)\*\*\s*[:：]` 不匹配带 `（…）` 的索引）；`_h2_section`（guard）/`_extract_h2_sections`（checker，:165-173）跳过 fenced code block（``` 块内 `##` 不当作 section 标题）。**checker 的 `check_openspec_artifacts.py:_extract_user_confirmation_indexes`（:552）与 `_extract_h2_sections` 有完全相同两个 bug（grill 已实测两实现当前行为一致都错），必须同 PR 修复**，否则 parity 测试（`tests/test_workflow_guard.py:308`）在 fenced-block / Q8 后缀 fixture 上失配。

### D8: 内容门槛阶段感知（#123）

- 结构门槛（proposal 阶段）照旧：section 存在 + status/reason/findings/design impact 非空（现有 `_check_reference_implementation_research`）。
- 内容门槛**仅 tasks 全勾时生效**（`_tasks_all_complete`）：对 Reference Implementation Research 各字段正文做「自认未完成」短语级模式匹配，命中 → checker exit 2（错误信息指明命中短语 + 字段）。
- 「来源缺失」「design impact 须 采用X而非Y」**不作硬红**（误伤无 URL 优质 findings / 语义对比无法机械抠），设计质量归 building-review。
- `--check-archived` 不扩展。
- 初始短语模式集（Q6 确认，grill 修正）：`尚未完成`、`待补充`、`待调研`、`TBD`、`todo`、`待确认` 等（**删 `暂无`**——误伤「暂无参考仓库可用」类合法 finding，本 proposal 参考仓库不可用表述即为近义场景；**删 `未完成`**——与 `尚未完成` 子串重叠且「未完成目标」类中性表述易误伤）；匹配前统一 `.lower()` 大小写归一；语义化占位漏检记 `docs/known-debt.md`，不无限扩表。

### D9: agent schema 定义 + JSON Schema 校验接 checker（#127 P0 边界）

- `phases.<phase>.agent = {provider, model}`（可选，缺省=当前会话 inline）+ 顶层 `review.agent`；**删 tool**、不叫 executor（`agent/workflow/models.py:18` Executor 模态枚举已占用）。
- phase 命名用 repo 规范 phase（wayfinding/planning/building/closing），review 用顶层覆盖节。
- provider/model 命名空间钉 paseo 侧（`claude/...`、`codex/...` 形式），与 repo 内 `build_llm` 的 anthropic/openai 命名空间区分。
- **P0 消费边界**：定义 schema + checker 对 `scripts/flow-policy.json` 的 `phases`/`review` 节做 JSON Schema 校验（非法 provider/model 类型、未知 phase 键 → checker 报错）；spawn 消费留 P4。
- 与 `openspec/config.yaml` `routing` 节的关系（#127 Q5，Q5 确认）：P0 只定义 schema 不接线消费，config.yaml routing 暂保持现状，替代/迁移关系留 P1/P4。

## Pre-Implementation Review

独立 subagent design grilling 已完成（`reviews/grill-design.md`，run `grill-flow-policy-source-20260814`，2026-08-14）：6 条 Confirmed Decisions + Q1-Q10 Open Questions + 风险清单。grill 实测确认 4 个绕过在当前 guard 下全部 rc=0 放行，并发现 5 个必须修改的设计缺陷，已整合进本 design：

- **缺陷 1（高，已修正 D2/D7）**：Bash 受保护路径扫描不能 blanket contains（误拦只读命令 + 破坏 `test_guard_allows_workflow_state_cli_commands`）——改为写意图感知 + 路径提取 normpath + 显式豁免 `workflow_state.py (artifact-event|review-manifest|policy-*)` 写通道。
- **缺陷 2（高，已修正 D6）**：flow-policy.json 自举/迭代死锁——guard fail-closed on missing + cli_written 拦截 agent Write/Edit，需 `policy-set` 写通道（Q4/Q8 待用户确认）。
- **缺陷 3（中，已修正 D7）**：checker 提取正则与 guard 有完全相同两个 bug，必须同 PR 修复（否则 parity 失配）。
- **缺陷 4（中，已修正 D2）**：`event_explained` 规则缺 `event_types` 时 checker 全量误报，加载时须校验规则 schema。
- **缺陷 5（低，已修正 D3）**：内嵌默认表定位矛盾，明确 parity-only 不参与 enforcement。

- 已确定（决策票 + grill 确认，本 change 沿用）：独立 `flow-policy.json`（JSON）、match_type+governance+event_types 规则表、guard 内嵌默认表 parity-only + 缺失/损坏 fail-closed、checker 同源加载（链式 parity）、workflow_methods.json 保留 management bypass、内容门槛阶段感知（短语集去 `暂无`/`未完成`）、agent schema P0 只定义不消费。
- **全部 Open Questions（Q1-Q10）已由用户确认**（2026-08-14，记录于 grill-design.md `## User Confirmation`）：Q1 完整 A；Q2 合并三合一；Q3 governance 分配表按推荐；Q4 含 policy-set 写通道；Q5 agent schema 只定义不接线；Q6 短语集删 `暂无`/`未完成`；Q7 写意图感知 Bash 扫描；Q8 policy-set 为唯一 agent 写通道；Q9 checker 正则同步修复；Q10 内嵌默认表 parity-only。grill-confirmation-gate 已满足，进入 building 写代码门禁放行。

## Open Questions

全部已确认（2026-08-14，详见 `reviews/grill-design.md` `## User Confirmation`）。

- **Q1**（#122 遗留 Q4）：P0 范围选**完整 A**（checker 也从 `flow-policy.json` 加载，推荐）还是 **P0 变体**（checker 暂硬编码 + parity 锁子集）？完整 A 才是真单一源，checker 无 stdlib-only 约束读 JSON 成本低；变体改动小但 checker 侧双份源仍在。
- **Q2**：范围三合一确认——本 change 合并 #122（策略单一源）+ #123（内容门槛）+ #127（agent schema P0 边界）为一个 P0 change，接受吗？（#121 frontier 指示如此；如需拆开请说明优先级）
- **Q3**：D4 governance 分配表确认——特别是 guard-only 4 项（`workflow-events.jsonl`=cli_written、`gate-approvals.json`/`handoff.json`=guard_only、`-review-manifest.json`=manifest_verified）与 `workflow-state.json` 预留条目（cli_written）。
- **Q4**：`policy-*` 子命令 P0 形态——**推荐含写通道**（`policy-show` + `policy-validate` + `policy-set`，后者解决自举死锁，grill 缺陷 2）还是只读/校验起步（grill Q8 补充：无写通道则本 change 自己的 building 会被自己改造的 guard 锁死）？
- **Q5**（#127 Q5）：`phases.<phase>.agent` 与 `openspec/config.yaml` `routing` 节的关系——P0 只定义 schema 不接线（推荐，config.yaml 保持现状，迁移留 P1/P4）还是本期就做替代/双轨 parity？
- **Q6**（#123 待用户再看 Q2）：内容门槛初始短语级模式集采用 D8（grill 修正后：`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`，删 `暂无`/`未完成`，匹配前 lower 归一），漏检记 known-debt，接受吗？
- **Q7**（grill 新增）：D7 的 Bash 受保护路径扫描语义——接受「写意图感知 contains + 路径提取 normpath + 显式豁免 `workflow_state.py (artifact-event|review-manifest|policy-*)`」（推荐，grill 实测避免误拦只读命令与破坏现有测试）还是 blanket contains 命中即 exit 2？
- **Q8**（grill 新增）：flow-policy.json 自举/迭代写通道——接受 `policy-set` 写子命令作为唯一 agent 可调用写通道（推荐），还是 guard 对「创建当前缺失的 flow-policy.json」的 Write/Edit 放行一次？两种都不接受则本 change 自己无法创建策略文件（死锁）。
- **Q9**（grill 新增）：checker 提取正则（`_extract_h2_sections`/`_extract_user_confirmation_indexes`）与 guard 同步修复 + parity 新增 fenced-block / Q8 后缀 fixture——接受吗？（grill 实测两实现当前行为一致都错，只修 guard 会 parity 失配）
- **Q10**（grill 新增）：guard 内嵌默认表定位为 parity-only（不参与运行时 enforcement，删除「窗口期兜底」表述）——接受吗？

## Risks / Trade-offs

- **guard fail-closed 可能误伤正常开发（中）**：策略文件缺失/损坏时 guard 直接 exit 2，会阻塞所有代码写——这正是 fail-closed 意图（防止静默放行），但需在报错文案明确「恢复命令」（检查/修复 flow-policy.json）。异常恢复路径要有文档。
- **flow-policy.json 自举/迭代死锁（高，grill 缺陷 2）**：guard fail-closed on missing + governance=cli_written 拦截 agent Write/Edit，本 change 自己无法创建/修正策略文件——依赖 Q4/Q8 确认 `policy-set` 写通道或创建豁免。
- **Bash 扫描误拦合法命令（中，grill 缺陷 1）**：若按 blanket contains 实现会误拦 `git diff openspec/specs/...`、`cat docs/known-debt.md` 等只读命令并破坏 `test_guard_allows_workflow_state_cli_commands`（grill 已实测）——设计改为写意图感知 + 路径提取 + CLI 写通道豁免（D2/D7），回归测试固定预期。
- **checker 加载行为变化（中）**：`PROTECTED_PATH_RULES` 从常量变 JSON 加载，若策略文件损坏 checker 需 fail-closed（现有 CI 门禁不能静默跳过 protected-path 检查）；策略文件损坏时 guard 与 checker 报错口径需一致。
- **checker 提取正则分叉（中，grill 缺陷 3）**：checker `_extract_h2_sections`/`_extract_user_confirmation_indexes` 与 guard 有相同两个 bug，只修 guard 会 parity 失配——同 PR 修复 + 新增 fixture（Q9）。
- **策略文件并发写读到半截 JSON（低）**：guard 每次 hook 调用读 flow-policy.json + JSON parse（约 2KB，开销可忽略），但非原子写可能读到半截 JSON 误 fail-closed——`policy-set`/人类直改采用 tmp+rename 原子写。
- **parity 平凡化（低，grill 风险补充）**：「checker 规则集 == 策略表子集」若 checker 从同一磁盘文件加载则恒真——链式断言 guard 内嵌表子集 == checker 加载集 == 磁盘子集。
- **guard 内嵌默认表与磁盘表漂移（低）**：内嵌默认表更新策略文件后不同步会导致 parity 失败——parity 测试机械强制，实现时同步改。
- **内容门槛误伤（低）**：短语级模式可能误伤「引用他人尚未完成的调研」这类合法文本——错误信息指明命中短语与字段，开发者可改写；语义化占位漏检记 known-debt。
- **#127 schema 与 config.yaml routing 并存（低）**：两处都可能声明 executor/routing，语义重叠——P0 只定义不接线，迁移关系 P1/P4 定。
- **替代方案权衡**：
  - 扩 workflow_methods.json 加 guard 节（#122 选项 B）：编辑性冲突——整个文件受保护则方法映射改动过重仪式，不保护则策略可被 agent 自改——否决。
  - 双轨（#122 选项 C）：P0 先扩 workflow_methods.json 再迁 flow-policy.json——本期即目标形态，不做两步。
  - 生成器展开 guard 内嵌快照（#122 Q4 选项 b）：guard 更自包含但生成步引入构建复杂度，且 checker 仍需读文件——本期选各自读 JSON + parity。

## Testing Strategy

- 单元测试（guard）：从策略文件加载、内嵌默认表、fail-closed（缺失/损坏/非法 schema）、路径归一化（`docs/./`、`..`）、match_type 语义、4 个绕过回归（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./`）、User Confirmation 正则死锁修复（`- **Q8**（分支命名）:` 后缀、代码块内 `##`）。
- 单元测试（checker）：`PROTECTED_PATH_RULES` 从策略文件加载、checker 规则集 == 策略表 event_explained 子集、内容门槛（tasks 全勾 + 命中短语 → exit 2）、agent schema JSON Schema 校验。
- 同源 parity 测试：磁盘表 == guard 内嵌默认表；guard Bash fragment 集 == 策略表 path 值集；bash 写正则 / unconfirmed 词表 guard↔checker 一致（扩展现有 `tests/test_workflow_guard.py:308`）。
- 集成测试：策略文件变更后 guard 与 checker 同时生效；`policy-show`/`policy-validate` 子命令。
- 全量回归：`uv run pytest -q` + `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` + `uv run python scripts/check_openspec_artifacts.py`。
