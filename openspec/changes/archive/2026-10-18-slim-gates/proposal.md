# Proposal: 下掉旧门禁主体 + 瘦 checker（6 条项目规则）+ 补回 Bash 写前拦截

关联 issue：[#322](https://github.com/Xingkai98/asterwynd/issues/322)（本 change 的形态与验收）、
[#305](https://github.com/Xingkai98/asterwynd/issues/305)（witnessloop 接入总账，阶段 C 后「逐项下掉旧件」线）。

前置：`retire-old-gates-spike` 分支（本地 `e9d23af` / `d48fd93`，未 push）已完成「全删旧件」的影响实测，
报告见 `/tmp/retire-old-gates-spike.md`；本 change 复用其删除结果，并另外补回两个被它一并删掉的能力
（项目规则机械检查、Bash 写前拦截）与一个不该删的配置即代码（platform gate）。

## Change Type

- primary: process
- secondary: []

## Why

阶段 C（2026-10-17，PR #311 / merge `4b5cc7d1`）之后，`master` 的唯一 required check 是 witnessloop 的
`gate / check`；本仓自建的旧门禁仍然照跑，但**不再决定能否合入**。旧件与 witnessloop 高度重复，
同时维护两套证据与两套写通道的成本已经超过收益。

SPIKE 实测给出了删旧件的边界：

- **删是安全的**：49 文件、−13740 行；产品代码零依赖；全量 pytest 4137 passed（仅本机 `/tmp` 环境坑失败）；
  OpenSpec strict validate 27 passed；witnessloop 对「流程骨架」的覆盖成立（C1/C2/C4b）。
- **但会丢 6 条项目规则**：witnessloop v1.7.0 对 RIR、Impact Analysis、benchmark smoke 任务、
  tasks / 归档点完成度、backlog 一致性、building review 的 `## 闭环出口` PASS **全部判绿**（C3/C5/C6/C7）。
- **还会丢两样东西**：`scripts/platform_gate.py` 的 branch protection 配置即代码 / 漂移检测；
  以及本地 **Bash 写前拦截**（witnessloop 的 guard 明确只覆盖 `Write|Edit`，
  `src/witnessloop/guardcmd.py:16-18` 自述 Bash 是已知缺口）。

因此本 change 的形态是：**删旧门禁主体 → 新写只做 6 条项目规则的瘦 checker → 补回 Bash-only 本地 guard
→ 保留 platform gate 与 witnessloop 四件套**。不是「把所有门禁删掉」，也不是「原样保留」。

## What Changes

1. **删除旧门禁主体**：
   - `scripts/workflow_state.py`、`agent/workflow/*`（事件投影 / 状态机残件）；
   - `scripts/flow-policy.json`、`scripts/workflow_methods.json`；
   - 旧 `scripts/workflow_guard.py`（`Write|Edit|Bash` 面）；
   - 旧 `scripts/check_openspec_artifacts.py`（1934 行，重写为瘦 checker）；
   - 旧门禁测试约 6526 行（`tests/test_openspec_artifact_checker.py`、`tests/test_workflow_guard.py`、
     `tests/test_workflow_state_cli.py`、`tests/test_flow_policy.py`、`tests/test_workflow_archive_write_channel.py`、
     `tests/test_workflow_protected_write_channel.py`、`tests/test_retire_manifest_check.py`、`tests/agent/workflow/`；
     SPIKE 统计的 7028 行含 `tests/test_platform_gate.py` 的 502 行，这 502 行会恢复保留）；
   - 旧 hook 示例 `scripts/workflow_hook.example.json`；
   - `openspec/specs/dev-workflow-state-machine/spec.md`（四阶段状态机规格）。
2. **重写瘦 checker** `scripts/check_openspec_artifacts.py`，只实现 6 条项目规则（判据逐条从旧实现搬移，不放宽）：
   - RIR：`## Reference Implementation Research` 存在、`research_tier` / `status` / `reason` 结构门槛，
     enabled 时 findings / design impact（full 档另需 research questions），tasks 全勾或归档点时启用内容门槛；
   - Impact Analysis：`proposal.md` 或 `design.md` 的 `## Impact Analysis` 存在且非占位；
   - benchmark smoke：proposal 命中核心能力 / 代码模式时，`tasks.md` 必须有 benchmark + smoke 条目；
   - tasks / 归档点完成度：新增归档目录（diff `AR` 且 base 树不存在）必须有 ≥1 已勾任务，
     未勾且未标 `(post-merge)` ⇒ 红；归档目录名必须是 `YYYY-MM-DD-<id>`；
   - backlog 一致性：引用已归档 change 或不存在 active change ⇒ 红；
   - building review `## 闭环出口`：完成面必须存在且 PASS；宽触发下 terminal `BLOCKED` /
     `CHANGES_REQUESTED` / 重复出口 ⇒ 红；保留 `PASSED`、全角标点、`|` 多出口等边界判据。
3. **新写 Bash-only 本地 guard** `scripts/bash_write_guard.py`：
   - 解析 Bash 里的写操作（重定向、`cp` / `mv` / `tee` / `dd` / `sed -i` / `install` / `rm` 等）；
   - 拦写入受管路径（`agent/**`、`scripts/**`、`web/**`）与受保护 artifact（`.witnessloop/policy.json`
     的 `protected_paths`）；普通只读命令（`ls` / `grep` / `cat` / `git status` 等）放行；
   - 支持 `cd` 链、嵌套 `bash -c` / `sh -c`、命令替换、绝对路径归一化；无法静态判定的绕过面
     在文档与测试中如实登记；
   - 提供可提交的示例 hook 配置 `scripts/bash_write_guard.example.json` 与文档安装说明；
     `.claude/` 继续被 gitignore，不进入版本控制。
4. **保留**：`scripts/platform_gate.py` + `scripts/platform-gate.json` + 其测试与 `platform-gate` 规格；
   witnessloop 四件套；`validate` 的 OpenSpec strict validate 与编码 warn-as-error；`benchmark-gate`、
   `windows-platform`；`openspec/changes/archive/**`；历史 `workflow-events.jsonl`；`tests/test_round_model_alignment.py`
   （只去掉对已删状态机规格的引用）。
5. **CI**：`validate` 里旧的 `Check OpenSpec artifacts` 步骤改为调用瘦 checker；删除 `Check archived changes`
   步骤（事件投影已退役，归档点完成度由瘦 checker 在第一步的 diff 上评估）。其余 job 不动。
6. **文档**：AGENTS.md、docs/development-guide.md 等把「旧脚本 / 旧 policy / `flow status`」引用改成新现实；
   明确 checker 的命令与 exit 语义（0 通过 / 1 规则违规 / 2 用法或根缺失）。`AGENTS.md` 中
   `openspec/changes/archive/**` 的事件要求与 `workflow-state.json` 的 CLI 写通道描述要一并改成
   witnessloop 实况，而不只是删脚本名。
7. **规格面**：除 `dev-workflow-gate` 与 `change-documentation` 外，`multi-agent-collaboration` 的
   `Orchestration Reuses Workflow Persistence Discipline` 也要从 `agent/workflow/` 改指
   `agent/subagent/workflow_store.py`（否则删除 `agent/workflow/*` 后会留下悬空引用）；
   `dev-workflow-gate` 的 `## Purpose` 段手工改写为最终形态。

旧 checker 中不属于六条规则的检查（必填章节、Change Type 完整合法性、current spec 映射/同步任务、
设计审阅任务、handoff、受保护事件、review manifest）逐项在 `design.md` Decision 11 给出处置：
移交 witnessloop、退役为人工评审，或作为解析前置保留。本 change 不声称「只删了六条规则之外无损失」。

## Capabilities

### New Capabilities

无新能力域。

### Modified Capabilities

- `dev-workflow-gate`：承载分工从「旧 checker / guard / 事件投影 / platform gate 全部保留」改为
  「witnessloop（流程骨架）+ 瘦 checker（6 条项目规则）+ Bash-only guard（本地写前拦截）+ platform gate」；
  事件投影退役；新增瘦 checker 与 Bash guard 的规范性判据。
- `change-documentation`：把 grill / 机械检查 / CI / RIR / handoff / 信任边界等条目从旧 checker、
  `workflow-state.json`、`flow status` 改指新现实（瘦 checker、witnessloop 证据、历史只读）。
- `multi-agent-collaboration`：`Orchestration Reuses Workflow Persistence Discipline` 的持久化
  纪律从已删除的 `agent/workflow/` 改指 `agent/subagent/workflow_store.py`。

## 需求

1. **旧件删除**：上述文件 SHALL 被删除；产品代码 SHALL NOT 依赖它们；历史 `workflow-events.jsonl`
   与 `openspec/changes/archive/**` SHALL 保持不变（不重算、不删除、不迁移）。
2. **六条规则保留**：瘦 checker SHALL 实现 RIR / Impact Analysis / benchmark smoke / tasks + 归档点完成度 /
   backlog 一致性 / building review `## 闭环出口` 六条规则，判据 SHALL 与旧实现一致（`别改判据`）。
3. **正反例**：每条规则 SHALL 至少有一组正例与一组否定用例；旧实现已覆盖的边界（`PASSED`、全角符号、
   多出口、`(post-merge)` 标记变体、`AR` 重命名、base 树已有归档）SHALL 继续被覆盖。
4. **Bash 写前拦截**：本地 PreToolUse guard SHALL 拦住 Bash 写入受管路径与受保护 artifact；
   SHALL 放行普通只读命令；Write/Edit 面 SHALL 继续交给 witnessloop plugin guard，不重复实现。
5. **platform gate 保留**：`scripts/platform_gate.py --verify` SHALL 仍可用且与实况一致；
   本 change SHALL NOT 改 branch protection 实况，也 SHALL NOT 在合入前跑 `--apply`。
6. **CI 收口**：`validate` SHALL 调用瘦 checker；其余 job SHALL 不改。
7. **文档一致**：仓库内对旧脚本 / 旧 policy / `flow status` 的现行引用 SHALL 被清理或改为历史说明；
   checker 命令与 exit 语义 SHALL 写入 AGENTS.md 的验证命令表与开发指南。

## Non-Goals

- 不删除历史数据（`openspec/changes/archive/**`、`workflow-events.jsonl`）。
- 不改变 witnessloop 的工作流、required 集合、policy 或 `v1.7.0` 引用。
- 不碰 witnessloop 仓库与 `v1` / `v1.7.0` tag。
- 不把瘦 checker 做成「文档质量评分器」：只做机械判据，不判断设计质量。
- 不在本 change 里重写 `platform_gate.py` 或调整 branch protection。
- 不恢复事件投影 / `flow status` / `handoff.json` 写通道。
- 不追求 Bash guard 的完全静态解析（shell 不可判定性）；挡不住的绕过面如实登记，CI 仍是最终防线。

## Impact Analysis

- **影响能力域**：`dev-workflow-gate`（主要）、`change-documentation`（引用与机械检查口径）、
  `multi-agent-collaboration`（持久化纪律引用）、`platform-gate`（只保留，不改语义）。
- **影响代码**：
  - 删除 `agent/workflow/**`、`scripts/workflow_state.py`、`scripts/workflow_guard.py`、
    `scripts/flow-policy.json`、`scripts/workflow_methods.json`、`scripts/workflow_hook.example.json`；
  - 重写 `scripts/check_openspec_artifacts.py`；
  - 新增 `scripts/bash_write_guard.py`、`scripts/bash_write_guard.example.json`。
- **不影响产品代码**：SPIKE 实测 `agent/` 运行时、工具、Web、benchmark 对旧门禁零依赖；
  `agent/subagent/workflow_store.py` 与旧 `agent/workflow/` 不是同一模块。
- **影响测试**：
  - 删除旧门禁测试约 6526 行；
  - 新增瘦 checker 正反例测试与 Bash guard 测试；
  - `tests/test_round_model_alignment.py` 去掉对已删状态机规格与旧 checker 内部提示的过时引用
    （保留有界批次模型的文档守卫）；
  - `tests/agent/tools/test_guard_three_state.py` 的示例命令改为仍存在的脚本。
- **影响 CI**：`.github/workflows/ci.yml` 的 `validate` 只改 checker 步骤（改名 / 调用瘦 checker /
  删除 `--check-archived` 步骤）；`benchmark-gate`、`windows-platform`、`witnessloop.yml` 不动。
- **影响文档**：AGENTS.md、docs/development-guide.md、docs/requirements-process.md、
  docs/agents/issue-tracker.md、docs/interview-script/（Q12/Q14）、openspec/project.md、
  openspec/templates/tasks.md、docs/openspec-change-backlog.md、docs/known-debt.md 与相关 ADR 横幅。
- **不影响**：`README.md` / `README_EN.md` 的架构叙事（门禁细节不在 README 的事实面内；如扫描发现
  现行引用则同步中英文）。
- **未决影响面**：无（用户已在 issue #322 拍板形态；实现细节由 grill 与对抗环收敛）。

## Reference Implementation Research

- research_tier: full
- status: enabled
- reason: 命中判据表「走 grill 的非平凡 change」与「架构级改造」——本 change 要删除一块门禁实现、
  重写另一块，必须逐条确认 witnessloop 的覆盖边界、业界 coding agent 仓的本地/CI 检查分工，
  以及旧 Bash 解析逻辑里哪些是可复用的、哪些是已知绕过面。
- research questions:
  1. witnessloop v1.7.0 的 `check` / `guard` 究竟覆盖哪些流程骨架？哪些项目规则、Bash 写面没有替代物？
  2. 同类 coding agent 仓库（codex / deepseek-harness / kimi-code / pi / opencode / zcode）如何分工
     本地 hook 与 CI 门禁？哪些模式适合本仓的项目规则 checker 与 Bash guard？
  3. 旧 `workflow_guard.py` 的 Bash 解析实现与测试中，哪些逻辑可以直接复用？已知绕过面有哪些，
     新 guard 应如何在不引入 shell 解析器的前提下尽量收窄？
- findings:
  1. **witnessloop 的覆盖边界已在源码与实测两侧钉死**：`src/witnessloop/guardcmd.py:16-18` 明确写
     「本动词是防遗忘，不是防对抗——agent 可以改用 Bash 写文件」；`checkcmd.py:188-192` 不解析报告
     verdict 文本；SPIKE 用真实 git commit 实测 C3/C5/C6/C7：缺 RIR / Impact / benchmark smoke、
     tasks 全未勾、backlog 引用不存在的 change、building review 为 `BLOCKED`，`check` 全部 PASS。
     ⇒ 6 条项目规则与 Bash 面确实必须由本仓补，删除旧件不是「零损失」。
  2. **本地 hook 与 CI 的分工在参考仓库里是共识**：deepseek-harness 的 `lefthook.yml:1-3` 自述
     「Keep these local checkpoints fast; CI owns the full repository-wide gate matrix」；
     kimi-code 的 hook 文档以 exit 2 阻断、stderr 给原因，并明确 hook 失败是 fail-open、
     「不应作为唯一的安全防线」（`docs/zh/customization/hooks.md`）；codex 的 execpolicy 用声明式规则
     并为每条规则要求 match / not-match 示例（`codex-rs/execpolicy/src/parser.rs`）；pi 把仓库特有检查
     聚合成 `npm run check` 脚本（`package.json:21-36`）。⇒ 本仓的选择是：瘦 checker 作为单一聚合入口
     （CI 与本地同一条命令），Bash guard 只做本地 checkpoint，required `gate / check` 与 CI 仍是权威。
  3. **旧 Bash 解析可复用的部分与边界**：旧 `workflow_guard.py` 的 `_is_write_bash` 写意图模式表
     （重定向 / tee / cp / mv / sed -i / dd of= / install / rm 等，含 no-space 重定向下与 here-doc）、
     `_extract_bash_targets`、`_norm_path` 与受保护路径 contains 语义已被 661 行测试打磨；但其
     `cd` 不跟踪、嵌套 shell 只看外层、`cp` 源与目标不区分、策略来自已要删除的 `flow-policy.json`。
     ⇒ 新 guard 复用模式表与归一化，补 `cd` 链、`bash -c` / `sh -c` 递归、命令替换、目的参数语义，
     策略改读 `.witnessloop/policy.json`；变量展开、符号链接、`find -exec` 等不可静态判定的面
     如实登记为残余绕过面（CI 兜底）。
  4. **旧 checker 的判据细节必须逐字搬移**：SPIKE 与源码显示这些边界不是可有可无的修饰——
     RIR 的 `research_tier` / `status` / enabled 字段与「tasks 全勾才查内容」的阶段感知；
     benchmark 触发用的 5 个 capability 名与 4 个代码模式；归档点 diff 的 `--diff-filter=AR`
     且目录必须不在 base 树（否则往旧归档补文件会拖全量门禁）；`## 闭环出口` 的 `PASSED` 拒绝、
     全角 `｜` 多出口歧义、fenced code block 跳过；`(post-merge)` 的编号/粗体/全半角括号变体。
     ⇒ 瘦 checker 直接搬运这些函数与正则，并以旧测试用例做对照回归。
  5. **platform gate 没有 upstream 替代物**：witnessloop 不读 branch protection；`platform-gate.json` +
     `platform_gate.py --verify` 是本仓唯一的配置即代码与漂移检测。SPIKE 曾把它一并删除，本 change
     明确恢复保留，且不改平台实况。
- design impact:
  - ⇒ 重写 `scripts/check_openspec_artifacts.py` 为只含 6 条规则的 stdlib checker；保留原路径与
    exit 语义，CI 只改调用面。
  - ⇒ 新增 `scripts/bash_write_guard.py`（stdlib、Bash-only），策略读 `.witnessloop/policy.json`；
    提交示例 hook 配置，`.claude/` 不入库。
  - ⇒ 删除 `agent/workflow/*`、`workflow_state.py`、`flow-policy.json`、`workflow_methods.json` 与
    旧 guard；历史事件日志与归档保持只读。
  - ⇒ platform gate 四项（脚本 / JSON / 测试 / 规格）原样保留。
  - ⇒ 文档把「双守卫并存 / 退步记录」改写为「witnessloop Write|Edit + 本仓 Bash-only guard」的现行形态，
    并把残余绕过面写进开发指南而不是假装已封死。

## 用户故事

- 作为本仓维护者，我不再维护两套 change 证据与两套写通道；CI 里只剩一个瘦 checker 承载 witnessloop
  没有的项目规则。
- 作为审阅者，我仍能被机械提醒：缺 RIR、缺 Impact、缺 benchmark smoke、归档留了未勾任务、backlog
  引用了不存在的 change、building review 终结为 `BLOCKED`——这些不会被「删旧件」顺手削弱。
- 作为在本仓跑 agent 的人，我用 Bash 重定向写 `agent/**` 或受保护文档时会在执行前被拦住，
  而 `ls` / `grep` / `cat` 不受影响。
- 作为平台维护者，我仍能用 `platform_gate.py --verify` 发现 branch protection 漂移。
