# Grill: flow-policy-source 设计追问

## Reviewer
- run id: grill-flow-policy-source-20260814
- 时间: 2026-08-14

## Confirmed Decisions
- **决策**: 采用独立 `scripts/flow-policy.json`（JSON 非 YAML）作为受保护路径规则单一策略源，guard 与 checker 同源加载；理由: guard stdlib-only 无 YAML，单策略源消除 guard 9 项子串与 checker 5 项 exact/prefix 双份漂移（workflow_guard.py:62-72 vs check_openspec_artifacts.py:122-128）；来源: grill-flow-policy-source-20260814
- **决策**: 规则表 schema 为 `path + match_type(exact|prefix|contains) + governance(guard_only|event_explained|manifest_verified|cli_written) + 可空 event_types`，guard 源码内嵌默认表且策略文件缺失/损坏时 fail-closed exit 2；理由: #122 决策 A，governance 模型消解 guard 子串与 checker exact/prefix 语义差异，fail-closed 防止静默放行；来源: grill-flow-policy-source-20260814
- **决策**: `workflow_methods.json` 与 `workflow_hook.example.json` 保留 management bypass（agent 可改方法映射），不入受保护清单，安全关键规则全部收进 flow-policy.json（governance=cli_written）；理由: #122 C1 编辑性冲突消解——策略（安全关键）与映射（可插拔）物理分离（workflow_guard.py:61, :381-383）；来源: grill-flow-policy-source-20260814
- **决策**: checker 内容门槛阶段感知（#123）：proposal 阶段只查结构门槛，tasks 全勾（`_tasks_all_complete`）时才对 Reference Implementation Research 字段做「自认未完成」短语级模式匹配，命中 exit 2；理由: 与 building-review 门禁同名判定一致（check_openspec_artifacts.py:705-723），避免在途 change 被误伤；来源: grill-flow-policy-source-20260814
- **决策**: `phases.<phase>.agent = {provider, model}` + 顶层 `review.agent` 只定义 schema + checker JSON Schema 校验，spawn 消费留 P4；provider/model 命名空间钉 paseo 侧；理由: #127 P0 边界，与 models.py:18 Executor 模态枚举区分；来源: grill-flow-policy-source-20260814
- **决策**: guard 4 个实测绕过（`echo > file`、`cat <<EOF`、`pathlib.write_text`、`docs/./` 变体）写入 P0 出口回归测试并全部拦截（exit 2）；理由: 我已实测确认这 4 个绕过形态在当前 guard 下全部 rc=0 放行（无空格重定向 `>docs/`、`python3 -c "Path(...).write_text(...)"`、`docs/./known-debt.md` 在 Write 与 Bash 均绕过）；来源: grill-flow-policy-source-20260814

## Open Questions
- **Q1**（design Q1）: P0 范围选完整 A（checker 也从 flow-policy.json 加载，推荐）还是 P0 变体（checker 暂硬编码 + parity 锁子集）？推荐答案: 完整 A——checker 无 stdlib-only 约束，读 JSON 成本低，完整 A 才是真单一源；变体 checker 侧双份源仍在，治标不治本。
- **Q2**（design Q2）: 三合一范围——本 change 合并 #122 + #123 + #127 为一个 P0，接受吗？推荐答案: 接受合并，三票已在 wayfinding 阶段 grill 确认，合并减少跨 change 交接成本；如需拆开，#123 与 #127 可后置但会与 #122 的 flow-policy.json 顶层结构耦合。
- **Q3**（design Q3）: D4 governance 分配表确认，特别是 guard-only 4 项（workflow-events.jsonl=cli_written、gate-approvals.json/handoff.json=guard_only、-review-manifest.json=manifest_verified）与 workflow-state.json 预留（cli_written），以及 Bash 扫描用「策略表 path 值集 contains」的保守双语义？推荐答案: 分配表确认；但「Bash contains 命中即 exit 2」的保守语义需先解决 Q7 的 CLI 通道豁免与只读误拦，否则会破坏现有 `test_guard_allows_workflow_state_cli_commands`（tests/test_workflow_guard.py:65-85，命令文本含 docs/known-debt.md 但期望 rc=0）。
- **Q4**（design Q4）: `policy-*` 子命令 P0 形态——只读/校验起步（policy-show + policy-validate，design 原推荐）还是含写通道？推荐答案: P0 增加 `policy-set` 写子命令（至少支持替换单条规则/整体 apply）；否则本 change 自己的 building 阶段被自己改造的 guard 锁死（见 Q8），agent 无法创建/修正 flow-policy.json。
- **Q5**（design Q5）: `phases.<phase>.agent` 与 `openspec/config.yaml` routing 节关系——P0 只定义 schema 不接线（推荐）还是本期就做替代/双轨 parity？推荐答案: P0 只定义不接线，config.yaml routing 保持现状，替代/迁移关系 P1/P4 定；两处语义重叠已记入 Risk。
- **Q6**（design Q6）: 内容门槛初始短语级模式集采用 D8 所列（`尚未完成`/`待补充`/`待调研`/`TBD`/`todo`/`待确认`/`暂无`/`未完成`），漏检记 known-debt，接受吗？推荐答案: 基本接受但删 `暂无`（会误伤「暂无参考仓库可用」这类合法 finding，本 change proposal.md:108 的参考仓库不可用表述即为近义场景）、删 `未完成`（与 `尚未完成` 子串重叠冗余，且「未完成目标」类中性表述易误伤）；匹配前统一 `.lower()` 大小写归一。
- **Q7**（新）: D7 的 Bash 扫描前移语义到底选哪种——「策略表 path 值集 contains 命中即 exit 2」（对每条 Bash 命令，含只读）还是「路径提取 + normpath + match_type 精确匹配」？推荐答案: 不能选 blanket contains——我已实测它会：① 破坏现有 `test_guard_allows_workflow_state_cli_commands`（artifact-event CLI 命令文本含 docs/known-debt.md 现期望 rc=0，见 tests/test_workflow_guard.py:65-85）；② 拦截 `git diff openspec/specs/...`、`cat docs/known-debt.md`、`grep` 等合法只读命令（现 rc=0）。推荐: contains 扫描保留但只在命令「有写意图且非 read-only allow 且非豁免 CLI 通道」时 exit 2，并显式豁免 `workflow_state.py (artifact-event|review-manifest|policy-*)` 合法写通道；D7 当前两个 bullet（blanket contains vs 路径提取归一化）自相矛盾，必须二选一并明确。
- **Q8**（新）: flow-policy.json 的自举与迭代写通道——guard 对 agent Write/Edit 拦截 flow-policy.json（governance=cli_written），且策略文件缺失时 fail-closed exit 2，那本 change 的 task 3.1（agent 创建 flow-policy.json）与后续 review 修正如何完成？推荐答案: 扩 P0 增加 `policy-set` 写子命令作为唯一 agent 可调用写通道（guard 豁免该 CLI），或 guard 对「创建当前缺失的 flow-policy.json」的 Write/Edit 放行一次；否则本 change 自己的 building 会被自己改造的 guard 锁死（创建前 fail-closed，创建后 Write/Edit 被 cli_written 拦截）。
- **Q9**（新）: D7 只修 guard 的 `_h2_section`/User Confirmation 正则，但 checker 的 `_extract_h2_sections`（check_openspec_artifacts.py:165-173）与 `_extract_user_confirmation_indexes`（:552）有完全相同的两个 bug（fenced code block 内 `##` 误判为 section；`- **Q8**（分支命名）:` 后缀无法提取）。我已实测两者当前行为一致（都错），若只修 guard 则 parity 测试（tests/test_workflow_guard.py:308）在 fenced-block / Q8 后缀 fixture 上失配。推荐答案: guard 与 checker 的提取正则同步修复（两个文件同 PR 改），并在 parity 测试新增这两类 fixture 锁死。
- **Q10**（新）: guard 内嵌默认表的定位——D3 说「guard 先于策略文件部署窗口期的兜底」但又「加载失败 fail-closed exit 2 不使用内嵌默认表继续放行」，两者矛盾；内嵌表到底参不参与 enforcement？推荐答案: 明确内嵌默认表为 parity-only（只作「磁盘表 == 内嵌表」对比锚点，从不参与运行时 enforcement），删除「兜底/fail-safe」表述，与 fail-closed-on-missing 语义一致；否则「guard 生效但磁盘表旧版」的漂移窗口理解混乱。

## User Confirmation

- **Q1**: 用户答复：完整 A（checker 也从 flow-policy.json 加载，真单一源）；确认时间: 2026-08-14
- **Q2**: 用户答复：合并（#122+#123+#127 一个 P0 change）；确认时间: 2026-08-14
- **Q3**: 用户答复：按推荐（D4 governance 分配表确认：workflow-events.jsonl=cli_written、gate-approvals.json/handoff.json=guard_only、-review-manifest.json=manifest_verified、workflow-state.json 预留=cli_written）；确认时间: 2026-08-14
- **Q4**: 用户答复：含 policy-set 写通道（policy-show + policy-validate + policy-set 原子写）；确认时间: 2026-08-14
- **Q5**: 用户答复：按推荐（P0 只定义 agent schema 不接线 config.yaml routing，迁移留 P1/P4）；确认时间: 2026-08-14
- **Q6**: 用户答复：按推荐（内容门槛短语集删 暂无/未完成，保留 尚未完成/待补充/待调研/TBD/todo/待确认，匹配前 lower 归一）；确认时间: 2026-08-14
- **Q7**: 用户答复：写意图感知（路径提取 token → normpath → match_type，只在有写意图且非豁免 CLI 写通道时拦）；确认时间: 2026-08-14
- **Q8**: 用户答复：policy-set 作为唯一 agent 可调用写通道（guard 显式豁免）；确认时间: 2026-08-14
- **Q9**: 用户答复：按推荐（checker 提取正则与 guard 同 PR 修复 + parity 新增 fenced-block/Q8 后缀 fixture）；确认时间: 2026-08-14
- **Q10**: 用户答复：按推荐（内嵌默认表 parity-only，不参与运行时 enforcement）；确认时间: 2026-08-14

## 风险
- **D7 blanket contains 误拦合法只读与 CLI 写通道（高）**: 若按「策略表 path 值集 contains 命中即 exit 2」实现，`git diff openspec/specs/...`、`cat docs/known-debt.md`、`grep` 等只读命令会被拦截（现 rc=0，我已实测）；且会破坏 `test_guard_allows_workflow_state_cli_commands`（tests/test_workflow_guard.py:65-85 期望 rc=0）。D7 两个 bullet 自相矛盾（design.md D7「对每条 Bash 命令先做 _mentions_protected_path 命中即 exit 2」vs「Bash 命令中提取的路径先 normpath 再匹配」）。
- **flow-policy.json 自举/迭代死锁（高）**: guard fail-closed on missing + flow-policy.json governance=cli_written 拦截 agent Write/Edit，导致本 change 自己无法创建/修正策略文件（tasks.md:26 任务 3.1 由 agent 执行；D6 P0 仅 policy-show/policy-validate 只读通道）。design.md 未提供 bootstrap 豁免或写通道。
- **checker 提取正则未同步修复（中）**: D7 只列 guard 修复，checker `_extract_h2_sections`/`_extract_user_confirmation_indexes` 同 bug 未列，parity 测试（tests/test_workflow_guard.py:308）会失配；我已实测两实现当前行为一致（都错），分叉后无法锁 parity。
- **event_explained 规则缺 event_types 时 checker 全量报错（中）**: `_allowed_event_types_for_protected_path`（check_openspec_artifacts.py:863-869）对空 event_types 返回空 tuple，`_protected_artifact_explanation_errors` 会判任何事件都不合法 → 该路径一变即错；design D2 声明 event_types 必填但未指定 checker 加载时校验规则 schema，policy-validate 也未列此项。
- **内容门槛短语误伤（低-中）**: `暂无` 会命中「暂无参考仓库可用」类合法 finding（本 change proposal.md:108 即近义场景）；`未完成` 与 `尚未完成` 子串重叠且可命中中性表述。设计已接受漏检记 known-debt，但初始集应去 `暂无`。
- **内嵌默认表定位表述矛盾（低）**: D3「窗口期兜底」与「fail-closed 不使用内嵌表继续放行」矛盾（design.md D3；proposal.md:63-64），需澄清为 parity-only，否则实现时可能误做运行时 fallback。
- **Bash 性能与并发写（低）**: guard 每次 hook 调用读 flow-policy.json + JSON parse（约 2KB），开销可忽略；但策略文件被非原子写（如直接 Write/Edit）时可能读到半截 JSON → 误 fail-closed；建议 `policy-set`/人类直改用 tmp+rename 原子写。
- **checker parity (b) 平凡化（低）**: 「checker 规则集 == 策略表 event_explained 子集」若 checker 从同一磁盘文件加载则恒真；parity 的真正意义在「guard 内嵌默认表 == 磁盘表」与「checker 无残留硬编码」，测试应链式断言 guard 内嵌表 event_explained 子集 == checker 加载集 == 磁盘子集。
