# Design: 下掉旧门禁主体 + 瘦 checker + Bash guard

## Context

阶段 C 之后，本仓的流程骨架已由 witnessloop 承载（`gate / check` 是唯一 required）；旧门禁仍在跑但
不决定合入。SPIKE（`/tmp/retire-old-gates-spike.md`，分支 `retire-old-gates-spike/2026-10-18`）证明了
全删的安全性，也证明了它会丢掉 6 条项目规则、platform gate 与 Bash 写前拦截。用户已在 issue #322
拍板最终形态：**删旧主体 + 瘦 checker + 保留 platform gate + 退役事件投影 + 补回 Bash guard**。

本设计只回答「怎么实现这个已拍板的形态」，不重新讨论是否要下掉旧件。三个来自实测的硬事实约束形状：

1. **witnessloop 对 6 条项目规则全判绿**（SPIKE C3/C5/C6/C7），且 `guard` 只覆盖 `Write|Edit`
   （`src/witnessloop/guardcmd.py:16-18` 自述 Bash 是已知缺口）。⇒ 6 条规则与 Bash 面必须本仓补。
2. **旧 checker 的判据细节有大量边界**（`AR` 重命名、base 树过滤、`PASSED`、全角 `｜`、
   `(post-merge)` 变体）。⇒ 搬运函数与正则，不重写判据。
3. **旧 `workflow_guard.py` 的 Bash 解析是 regex 管线**，不是完整 shell 解析器。⇒ 新 guard 在同一
   抽象层上补关键绕过面（cd 链、嵌套 shell、命令替换），其余如实登记。

## Goals / Non-Goals

**Goals:**

- 删除旧门禁主体与约 6526 行旧测试（7028 − 恢复保留的 502 行 platform gate 测试），产品代码零依赖。
- 用同一个路径 `scripts/check_openspec_artifacts.py` 承载 6 条项目规则，判据与旧实现一致。
- 新增 Bash-only 本地 guard，拦住写受管路径 / 受保护 artifact 的常见 Bash 写操作。
- 保留 platform gate 四项与 witnessloop 四件套；历史数据只读。
- 文档与 CI 同步到新现实，checker 命令与 exit 语义可复核。

**Non-Goals:**

- 不实现完整 shell 解析器，不追求挡掉所有绕过。
- 不改变 witnessloop 配置、required 集合、platform protection 实况。
- 不恢复事件投影 / `flow status` / `handoff.json` 写通道，不迁移历史 manifest。
- 不在本 change 中重构 `platform_gate.py` 或增加新的 CI job。

## Decisions

### Decision 1: 保留 checker 路径与 exit 语义，内部只留 6 条规则

`scripts/check_openspec_artifacts.py` 路径不变；`main()` 的 exit 语义保持旧行为：
`0` 全部通过、`1` 规则违规、`2` changes root 缺失或参数用法错误。CLI 保留
`--changes-root`、`--change`、`--backlog`、`--base-ref`、`--skip-backlog`、`--require-base`；
删除 `--current-specs-root`、`--skip-protected-paths`、`--check-archived`（受保护写入与事件投影
分别由 witnessloop 和「退役」承担，保留这些 flag 会暗示仍有检查）。

**理由**：CI 与文档已按这个命令书写；保留路径与退出码可以把「换实现」与「换调用协议」分开，
减少无关改动。**来源**：issue #322 验收「命令与 exit 语义要写进文档」。

### Decision 2: 6 条规则的判据逐条搬运，明确 active / archive 触发矩阵

| 规则 | active change | 新归档目录 | 搬运来源（`528d02f`） |
|---|---|---|---|
| RIR | 非 docs：结构门槛；tasks 全勾时内容门槛 | `assume_implemented=True` 强制内容门槛 | `_check_reference_implementation_research:524` |
| Impact Analysis | 非 docs：proposal 或 design 存在且非占位 | 不新增检查（沿用旧归档门判据） | `_check_impact_analysis:451` |
| benchmark smoke | proposal 命中 capability / 代码模式 ⇒ tasks 须含 benchmark + smoke | 不新增检查 | `_check_benchmark_smoke_task:903` |
| tasks / 归档完成度 | tasks 全勾触发 building review 完成面 | `≥1` 已勾；未勾且无 `(post-merge)` ⇒ 红；缺 tasks / 无 checkbox / 全未勾 ⇒ 红；非 docs + DESIGN_TYPES + spec delta ⇒ `grill-design.md`（≥3 决策、Open Question 已确认）与 `grill-adversarial.md` 存在 | `_untagged_unchecked_tasks:1027`、`_tasks_missing_evidence:1051`、`_check_design_review_task:739`、归档门 `:1753-1762` |
| backlog 一致性 | 每次运行（除非 `--skip-backlog`） | 同左 | `check_backlog_consistency:1490` |
| building `## 闭环出口` | 完成面：非 docs + spec delta + tasks 全勾 ⇒ 存在且 PASS；宽触发：报告存在即解析 | 非 docs + spec delta ⇒ 存在且 PASS；报告存在即宽触发 | `_check_building_review:1192`、`_check_archived_completion_gate:1678` |

归档点识别沿用旧实现：`git diff --name-only --diff-filter=AR <base>`（`A` 与 `R` 都要，`git mv`
会以 rename 出现）+ 目录必须不在 base 树的 archive 列表里（防止「往旧归档补文件」被当新归档）；
任何本次 diff 触及的非日期前缀归档目录直接红；base 解析沿用 merge-base of `HEAD` 与
`origin/master`（再退 `master`），`--require-base` 时 base 不可解析直接红。

**grill 证据的触发面差异（对抗轮 I-2）**：witnessloop 的 `grill` / `grill-adversarial` stage 只在
`code_hits` 非空时要求，而本仓的 `require_change_for` 只含 `agent/**`、`scripts/**`、`web/**`。
一个只改 `openspec/specs/**` + `docs/**` 的 process change 在 witnessloop 侧不会触发这两个 stage。
旧归档门对 `非 docs + DESIGN_TYPES + spec delta` 无条件要求 `grill-design.md` 与
`grill-adversarial.md`，因此瘦 checker 在**新归档点**保留这两条存在性/正文校验（见 Decision 11）；
这不是新增规则，而是防止「删除旧件」把旧的正确行为放松。

**理由**：这 6 条规则的边界是被历史审阅与实测打磨出来的；重写判据等于引入未经验证的新规则。
**来源**：issue #322「把它们从旧实现里准确搬过来（别改判据）」；SPIKE 报告「最小保留集」。

### Decision 3: 删除事件投影与 flow-policy，策略源收敛

删除 `scripts/workflow_state.py`、`agent/workflow/*`、`scripts/flow-policy.json`、
`scripts/workflow_methods.json`、旧 `scripts/workflow_guard.py` 与旧 hook 示例；历史
`workflow-events.jsonl` 与归档目录**只读保留**。受保护路径的**CI 规则源**收敛到
`.witnessloop/policy.json`；本地 Bash guard 也从该文件读取 `require_change_for` 与
`protected_paths`，并在文件缺失/损坏时退回内嵌默认表（不是放行）。

**理由**：两个 policy 源（`flow-policy.json` 与 `.witnessloop/policy.json`）会漂移；事件投影已无
消费者，保留 CLI 只会让文档继续描述一个不存在的流程。**来源**：issue #322 第 4 条；
SPIKE「事件投影已无人实现」。

### Decision 4: Bash guard 只做 Bash 面，Write/Edit 交给 witnessloop

新脚本 `scripts/bash_write_guard.py`：

- **输入**：Claude Code PreToolUse JSON（stdin，`tool_name == "Bash"`，取 `tool_input.command`）；
  另提供 `--command` / `--root` 便于测试与手工调用。
- **输出**：`exit 0` 放行；`exit 2` 阻断并在 stderr 给出命中的路径与原因（Claude Code hook 约定）。
- **拦截面**：受管路径（policy `require_change_for`：`agent/**`、`scripts/**`、`web/**`）与
  受保护 artifact（policy `protected_paths`）。**直接文件写入**受管路径都拦——合法写代码通道是
  Write/Edit（由 witnessloop guard 做 change/grill 检查），Bash 不是第二写通道。
- **写操作识别**（复用旧 `_is_write_bash` 模式表并扩展，使用 quote-aware 的轻量 tokenizer，
  不直接对原始命令文本跑正则）：
  - 重定向 `>` / `>>` / `2>` / `&>` / `>|`（含无空格）；`2>&1` / `>&2` 等 fd 复制与
    `/dev/null` 目标不算写受管路径；
  - `cp`（只取目的参数）、`rsync`（只取目的参数）、`mv` / `rm` / `rmdir` / `unlink` /
    `truncate` / `touch` / `mkdir` / `ln` / `chmod` / `chown` / `install` / `tee` /
    `sed -i` / `dd of=` / `perl -i` / `ruby -i`；
  - `python -c` 里出现 `open(..., 'w')` / `write_text` 等写调用且命令文本含受管路径；
  - `curl -o` / `wget -O`。
- **VCS 命令分两类处理**：
  - `git rm` / `git mv` **放行**：Write/Edit 无法删除或改名文件，若连它们都拦，本 change 自己删
    `scripts/*` 与 `agent/workflow/*` 就没有合法通道。
  - `git checkout -- <path>` / `git restore <path>` **拦**（解析出显式路径且命中受管/受保护时）；
    `git apply` **拦**（无法静态知道 patch 目标；`--check` / `--stat` 等只读形态放行）。
  - `git merge` / `git rebase` / `git cherry-pick` / `git stash` / `git am` **无法可靠解析目标**，
    登记为**已知的内容写入绕过面**（它们会改写受管路径，CI 兜底），不伪装成「簿记操作」。
    本 change 自己的一次性 cherry-pick 在没有安装 hook 的工作区执行，不受本地 guard 影响。
- **归一化与 match 语义**：路径按 `/` 归一、解析 `..`、绝对路径若落在 repo 内则转相对；
  policy 的 glob 按 witnessloop 同款语义匹配（`**` 跨目录、`*` 不跨 `/`、精确文件名）；
  `scriptsfoo/` 不得命中 `scripts/**`。跟踪 `cd <dir> && ...`；递归解析
  `bash -c` / `sh -c` / `eval` 与 `$(...)` / 反引号；递归深度有上限。
- **防误伤边界**（测试必须覆盖）：引号内的写样式文本（`rg 'echo > agent/y'`、
  `git commit -m "cp x agent/y"`）不触发；`cp agent/x /tmp/y`（源受管、目的仓外）放行；
  `sed -i 's|agent/|x|' docs/y` 放行（写目标是 docs/y）；here-doc 内容只当数据；
  `>/dev/null`、`2>&1` 放行。
- **已知残余绕过面**（不假装封死，写入开发指南并配测试标记）：变量展开 `$VAR/agent/x`、符号链接、
  `find -exec` / `xargs` 的路径、shell 函数/alias、进程替换、`git merge` / `rebase` /
  `cherry-pick` / `stash` / `am`、`cp -t dir` / `mv -t dir` 这类选项携带目标的形态、`install`
  的源/目的歧义，以及**任何被执行的程序**（`python x.py`、`make`、`uv run …`）都可以自行写文件。
- **失败策略**：policy 缺失/损坏 ⇒ 用内嵌默认表继续判；解析器内部异常 ⇒ `exit 0` + stderr 警告
  （本地 checkpoint fail-open，CI `gate / check` 仍是最终防线）。内嵌默认表 SHALL 与
  `.witnessloop/policy.json` 当前值一致，并用 parity 测试锁定。这与 witnessloop guard 的
  「防遗忘不是防对抗」定位一致。

**理由**：Bash 是 shell 语言，静态判定不可能完备；本地 guard 的价值是把常见误写挡在执行前，
而不是替代 CI。**来源**：issue #322 第 5 条；witnessloop `guardcmd.py:16-18`；
kimi-code hooks 文档的 fail-open 约定。

### Decision 5: hook 示例入库，本地安装不入库

新增 `scripts/bash_write_guard.example.json`，只含 PreToolUse / matcher `Bash` / 调用
`python3 scripts/bash_write_guard.py`。安装说明放 `docs/development-guide.md`：复制到
`.claude/settings.local.json`（或用户级 settings）。`.claude/` 继续被 `.gitignore` 忽略；
本 change 不写入任何 `.claude/` 文件。

**理由**：issue #322 明确要求「提供可提交的示例 hook 配置 + 文档说明；不要把本地 `.claude/` 塞进
版本控制」。**来源**：issue #322 第 5 条。

### Decision 6: platform gate 四项原样保留，不 apply

保留 `scripts/platform_gate.py`、`scripts/platform-gate.json`、`tests/test_platform_gate.py` 与
`openspec/specs/platform-gate/spec.md`。SPIKE 的删除提交会删掉它们，本 change 在复用删除结果后
显式恢复四项。合入前后只跑 `--verify`（只读），不跑 `--apply`。

**理由**：witnessloop 不覆盖 branch protection；配置即代码是仓库级安全边界。issue #322 已拍板保留。
**来源**：issue #322 第 3 条；SPIKE「platform gate 无替代物」。

### Decision 7: 复用 SPIKE 删除结果，但只接受它的代码/测试/CI 删除，文档全部重写

SPIKE 提交 `e9d23af` / `d48fd93` **仅本地存在、未 push**，干净 clone 不可复现；且它是「全删」
版本：其 `AGENTS.md`、`docs/development-guide.md`、`docs/known-debt.md`、ADR 横幅与
interview-script 都写着「checker / platform gate 已删除、六条规则无机械实现」，与本 change
的最终形态**相反**；它的 `openspec/specs/**` 改写也会让本 change 的 delta 失配（grill 实测
`openspec archive` 因 `Mechanical artifact checks` not found 中止）。因此：

1. 以 `git cherry-pick -n e9d23af` 只取**代码 / 测试 / CI** 的删除；
2. cherry-pick 后立即从当前 HEAD 恢复所有**文档与规格**：
   - `openspec/specs/**`、`openspec/project.md`、`openspec/templates/tasks.md`；
   - `AGENTS.md`、`docs/**`（含 `docs/known-debt.md`、`docs/adr/**`、interview-script）；
   - `docs/openspec-change-backlog.md`；
   然后由本 change **手工重写**这些文件到最终形态（SPIKE 只作为对照，不作为事实来源）；
3. 从 HEAD 恢复 platform gate 四项（脚本 / JSON / 测试 / 规格）；
4. 用瘦 checker 覆盖被删的 `scripts/check_openspec_artifacts.py`；新增 Bash guard 与示例 hook；
5. 手工施加本 change 的 delta，并单独删除 `dev-workflow-state-machine` 规格；
6. 跳过 `d48fd93`（backlog 口径订正，本 change 自己重写相关段落）。

删除清单以本 proposal 的 What Changes 为准，不依赖 SPIKE 分支长期存在；`e9d23af` 只是本工作区的
一次性加速手段。

**理由**：SPIKE 已实测删除的编译/测试影响；手工重做 49 文件的删除容易漏项。但它的文档结论不能
直接继承。**来源**：issue #322「可以复用它的删除结果（git cherry-pick 或对照）」；grill 对
cherry-pick 与 delta 冲突的实测；对抗轮 I-1 对「SPIKE 文档与最终形态相反」的实测。

### Decision 8: CI 只改 checker 步骤

`validate` job：
- `Check OpenSpec artifacts` → `Check project rules`，调用 `uv run python scripts/check_openspec_artifacts.py
  --base-ref "$BASE_REF" --require-base`；
- 删除 `Check archived changes`（`--check-archived` 已不存在；归档点完成度在第一步的 diff 上求值）。
`benchmark-gate`、`windows-platform`、`witnessloop.yml` 不改。

**理由**：issue #322「CI：`validate` 里的旧 checker 步骤改成调用新的瘦 checker；其余不动」。
**来源**：issue #322 第 7 条。

### Decision 9: 规格面用 MODIFIED / ADDED 覆盖，不平行新开

- `dev-workflow-gate`：MODIFIED 承载分工、policy 前置、本地守卫退步、保留项目规则、manifest 承载、
  双守卫并存；ADDED 瘦 checker 六条判据、Bash 写前拦截、事件投影退役。
- `change-documentation`：MODIFIED grill 机械强制、机械检查、CI、RIR、handoff、信任边界；
  删除对 `dev-workflow-state-machine` 的交叉引用。
- `multi-agent-collaboration`：MODIFIED `Orchestration Reuses Workflow Persistence Discipline`，
  把 `agent/workflow/` 持久化纪律改指 `agent/subagent/workflow_store.py`（删除 `agent/workflow/*`
  后该 Requirement 不能继续指向已删模块）。
- `dev-workflow-state-machine` 规格：删除（四阶段状态机已无实现）。OpenSpec strict validate 已由 SPIKE
  实测接受「删除 current spec、不写 delta」；本 change 在 design 与 proposal 记录该删除。
- `dev-workflow-gate` 的 `## Purpose` 段没有 delta 载体：施加 delta 时**手工就地改写**，把
  「旧 checker / guard / 状态机全部继续照跑」改为「witnessloop + 瘦 checker + Bash guard +
  platform gate」的现行形态。SPIKE 版本的 Purpose 也不能直接采用（它把六条规则说成无机械实现）。

**理由**：避免同一不变量在两处写两遍（历史漂移点）。**来源**：AGENTS.md「文档影响检查」；
SPIKE 的 OpenSpec 校验实测；grill 对悬空引用的检查。

### Decision 10: 文档守卫与示例命令的最小适配

- `tests/test_round_model_alignment.py`：保留有界批次模型的 ALLOWLIST / per-file 断言；
  **三处**引用已删状态机规格的位置都要处理——ALLOWLIST 条目、`PER_FILE_REQUIRED` 映射、
  专用单测 `test_dev_workflow_spec_replaces_old_termination_requirement`；瘦 checker 的 building
  review 错误文案继续包含「非空 medium+ 批次 / 20 个已收口轮 / 建议推倒重开」。
- `tests/agent/tools/test_guard_three_state.py`：SPIKE 把示例命令换成 `scripts/self_check.py`；
  这不是必须修改（checker 路径仍存在），保留或改回均可，不影响测试意图。

**理由**：这两个测试锁的是**现行文档/协议**，不是旧实现；不能让删除旧件把守卫静默弄失效。
**来源**：issue #322「保留 tests/test_round_model_alignment.py」。

### Decision 11: 旧 checker 的非六条检查逐项给出归属

旧 `check_change` 除六条规则外还查一批文档形状。瘦 checker 不再实现它们，但必须有明确归属，
不能留给实现猜测：

| 旧检查 | 处置 | 理由 |
|---|---|---|
| `design.md` / `diagnosis.md` 必填章节、占位正文 | 退役，人工评审 | witnessloop 只要求文件存在；本 change 只保留六条项目规则 |
| Change Type 合法性 / docs 组合规则 | **解析失败即 exit 1**（前置，不是完整合法性校验） | 六条规则的 docs 豁免依赖 `primary`；无法解析就不能安全评估 |
| current spec 映射（delta capability 有对应 current spec） | 退役，人工评审 + `openspec validate --strict` | 语法/引用完整性由 OpenSpec 负责 |
| current spec 同步任务（tasks 里必须有） | 退役，人工评审 | 不再是机械规则 |
| 设计审阅任务 / grill 证据（active） | 移交 witnessloop（`grill` stage manifest + 报告正文） | 已由 `gate / check` 覆盖（仅 `code_hits` 非空时） |
| grill 证据（新归档点） | **保留在瘦 checker 的归档完成度**：非 docs + DESIGN_TYPES + spec delta ⇒ `grill-design.md`（≥3 决策、Open Question 已确认）与 `grill-adversarial.md` 存在 | witnessloop 对纯 specs/docs change 不触发该 stage（I-2 的触发面差异） |
| `handoff.json` 结构 / 事件可投影 | 退役（事件投影删除） | 历史文件只读保留 |
| 受保护路径解释事件 / review manifest | 移交 witnessloop | `protected_write_event_types` 与 manifest 校验 |
| 事件 `schema` / `change_id` 与事件日志目录的一致性 | **退役（不校验）** | witnessloop 只解析 `event_type/artifact_path/reason/approved_by`（`events.py:37-46,106-121`），不读 `schema`/`change_id`；这是相对旧 checker 的已知退步，写入信任边界规格 |
| RIR / Impact / benchmark / tasks / backlog / building exit | **保留在瘦 checker** | issue #322 的六条规则 |

Change Type 解析失败的具体行为：`proposal.md` 缺失或 `## Change Type` 无法解析出合法 `primary`
时，该 change 报错（exit 1），且不继续套用 docs 豁免；这样既不会误判，也不会静默跳过。

**理由**：grill 指出「只丢 6 条规则」的表述不完整；把每一项的归属写死，删除才可审计。
**来源**：grill Code-Resolved Questions「旧 checker 还有哪些不在六条里的检查」；SPIKE 报告。

### Decision 12: 旧测试到新测试的映射

删除旧测试前，先把判据边界映射到新测试，避免「删了测试 = 放松判据」：

| 旧测试区域 | 新测试覆盖 |
|---|---|
| `_extract_record_field` 续行 / 字段边界 | RIR 的 `research questions` / `findings` / `design impact` 多行与空值 |
| RIR 结构门槛 + tier/status 组合 | full/light/exempt 三档正反例；tasks 未全勾 vs 全勾 |
| Impact / benchmark / docs 豁免 | 各一条正例 + 否定用例 |
| `_review_exit_verdict` 全参数表（`PASSED`、`未定`、`｜`、fenced block、有序列表） | 原表逐条搬入新测试 |
| building review 完成面 / 宽触发 / docs / 无 spec delta 豁免 | 四类 fixture |
| `AR` 重命名、base 树过滤、非规范归档命名、`.gitkeep` | 临时 git 仓库 fixture 原样搬入 |
| `(post-merge)` 8 变体 + 3 负例 | 原参数表搬入 |
| 缺 tasks / 无 checkbox / 全未勾 | 三条区分性断言搬入 |
| backlog 已归档 / 不存在 / 正常 active | 三条搬入 |
| `--require-base` fail-closed、`--skip-backlog`、`--change` 模式 | CLI 行为测试 |
| 空/空白 `--base-ref` 视同省略（不得跳过 diff 检查） | CLI 行为测试 |
| `--change <id>` 的「归档后缀 decoy」不匹配（`test_change_dir_in_any_form_rejects_suffix_decoy`） | CLI 行为测试 |

**理由**：grill 指出旧测试搬迁覆盖不足；这张表是 tasks 2.x 的验收清单。
**来源**：grill 风险「旧 checker 测试的搬迁覆盖不足」。

## Pre-Implementation Review

> 本节由 grill 与设计阶段对抗闭环的结论回填；两份报告原文见 `reviews/grill-design.md` 与
> `reviews/grill-adversarial.md`。

**独立设计追问（grill，run `grill-slim-gates-20261018-r1`）**：零记忆 subagent 逐项挑战 7 个维度，
产出 7 条 Confirmed Decisions、0 Open Questions、15 项风险（2 blocker / 5 high / 若干 medium）。
结论：设计方向成立，但按初稿直接开工会在三处走不完。已落实的修正：

| # | grill 发现 | 处置 |
|---|---|---|
| B1 | SPIKE 改写了 `openspec/specs/**`，与 delta 的 MODIFIED 标题冲突（实测 `openspec archive` 中止） | Decision 7 改为 cherry-pick 后**从 HEAD 恢复全部 specs**，手工施加 delta；platform gate 规格一并恢复 |
| B2 | tasks 6.7（PR/merge）在归档时刻无法勾选，会让本 change 自己的归档点判红 | 移入 section 7 并标 `(post-merge)`，section 6 只保留归档前可完成项 |
| H1 | witnessloop manifest 的 `tasks_hash` / `head_sha` 绑定顺序错误 | 顺序改为：事件 → tasks 结算 → 归档 move → 用归档目录名 build → 最终 check → PR |
| H2 | Bash guard 拦 VCS 删除/改名会让本 change 自己的删除没有合法通道 | Decision 4 只放行 `git rm`/`git mv`，拦截显式路径的 restore/checkout/apply，其余 VCS 内容写入登记为绕过面 |
| H3 | Bash guard 缺防误伤测试 | 新增 T4b（引号内文本、源/目的语义、`/dev/null`、`2>&1`、here-doc 数据） |
| H4 | 本 change 的受保护事件未逐路径覆盖 | tasks 6.1 逐路径列出 `current_spec_synced` / `backlog_updated` / `protected_artifact_explained` / `change_archived` |
| H5 | `multi-agent-collaboration` 的 current spec 改动未登记、无 delta | Decision 9 增加 MODIFIED delta，proposal Impact Analysis 登记该能力域 |
| H6 | `dev-workflow-gate` Purpose 会残留错误事实 | Decision 9 增加 Purpose 手工就地改写任务 |
| M1 | 「只丢 6 条规则」不完整 | 新增 Decision 11「旧检查 → 处置」表 |
| M2 | 旧测试搬迁覆盖不足 | 新增 Decision 12「旧用例 → 新用例」映射 |
| M3 | 归档命名判据被收窄成「新建目录」 | spec delta 与任务改为「本次 diff 触及的非日期归档目录」，与旧实现一致 |
| M4 | AGENTS 对 archive 事件与 `workflow-state.json` 的口径矛盾 | tasks 3.6 明确改语义 |
| M5 | building worktree 内本地 guard 不生效 | 文档写清 user-level settings / 每个 worktree 手动安装；本 change 自身以 CI 兜底 |
| M6 | policy glob 语义与 parity 未钉死 | Decision 4 写明 match 语义；新增 T4c parity 测试 |
| L1 | SPIKE 提交不可复现 | Decision 7 写明删除清单以 proposal 为准，SPIKE 只是一次性加速 |
| L2 | 事实数字与注释陈旧 | 删除测试行数改为 6526（7028 − 恢复的 502 行 platform gate 测试）；Decision 6 的「三件套」改为四项；CI 注释随步骤改写（均已落实） |

**Code-resolved**：v1.7.0 `manifest build` 支持归档目录名重建（`manifestcmd.py:33-67`）；
`platform_gate.py` 仅依赖 stdlib 且测试不引用被删模块；事件投影无产品代码消费者；
本 change 自身在旧六条规则下 0 错误（除任务结算与待产出的 review 证据）。

### 设计阶段对抗闭环（Round 1–2，PASS）

独立零记忆审阅者（run `grill-adversarial-slim-gates-20261018-r1`）以「试图推翻」为默认立场：

- **Round 1**：开批 12 条 medium+（1 blocker / 4 high / 7 medium）——SPIKE 文档与最终形态相反、
  grill 证据在非代码 change 上被放宽、delta 删掉 stale/孤儿 Scenario、commit 边界缺失、
  v1.7.0 锚点不可执行、multi-agent 括注失实、project.md 悬空、两 hook 实测缺失、
  VCS 放行理由不成立、事件 schema/change_id 校验退步、benchmark 判据收紧。全部修复。
- **Round 1 验证**：I-9（两 hook 同时安装实测）未修复，`CHANGES_REQUESTED`；验证期发现 D-1
  （两份 delta 职责边界矛盾）与 D-2（终态勾选点与纯 rename 冲突），进 deferred。
- **Round 2**：I-9 + D-1 + D-2 全部修复并验证通过，收口确认为空批，`## 闭环出口` = **PASS**。
- **Open Questions：0**，不需要停轮拍板；所有争点均由仓库事实/代码判定。

**遗留登记**：事件 `schema` / `change_id` 绑定不再校验（I-11）已作为已知退步写入
`change-documentation` 的信任边界规格与本文件 Decision 11；不另立第七条规定。

## Risks / Trade-offs

| 风险 | 影响 | 缓解 |
|---|---|---|
| Bash guard 的静态解析挡不住所有绕过（变量、符号链接、VCS 内容写入、动态命令） | 本地可被绕过 | 文档如实登记；CI `gate / check` + 瘦 checker 兜底；测试覆盖常见绕过 |
| Bash guard 误伤正常命令（引号内文本、`cp` 源、`/dev/null`、here-doc 数据） | 开发体验受损 | quote-aware tokenizer；T4b 防误伤用例；只对「写操作 + 受管/受保护目标」拦截；内部异常 fail-open |
| 瘦 checker 搬运判据时漏边界 | 项目规则被放松 | Decision 12 的旧→新测试映射；每条规则正例 + 否定用例；对抗审阅专门挑战判据一致性 |
| 删除 `flow-policy.json` 后受保护路径规则源变化 | 本地与 CI 规则不再同源 | 两者都读 `.witnessloop/policy.json`；guard 内嵌默认表仅在 policy 缺失时兜底，并用 parity 测试锁定 |
| `validate` 已非 required | 瘦 checker 判红不拦合入 | 文档明确「CI 绿 ≠ 项目规则满足」；平台 required 集合不在本 change 改动 |
| 历史事件日志与归档被误删 | 丢历史证据 | 明确只读保留；`git diff` 检查删除清单；归档目录零改动 |
| SPIKE 删除提交不可复现、与 delta 冲突 | 实现步骤走不完 | Decision 7：从 HEAD 恢复 specs、手工施加 delta；删除清单以 proposal 为准 |
| building worktree 内无本地 hook | 实现阶段没有本地 Bash 保护 | 文档写明 user-level settings / 每个 worktree 手动安装；本 change 以 CI 兜底 |

## Testing Strategy

| 编号 | 测什么 | 怎么测 | 判据 |
|---|---|---|---|
| T1 | 瘦 checker 6 条规则 | 新增 `tests/test_slim_project_rules.py`：每条规则至少 1 正例 + 1 否定用例；旧边界逐条搬测试 | 全部通过；缺 RIR / Impact / benchmark smoke / 未勾任务 / backlog 坏引用 / 非 PASS 出口均判红 |
| T2 | 归档点完成度 | 临时 git 仓库构造 `A` 与 `R` 新归档、旧归档补文件、非日期前缀、`(post-merge)` 变体 | 仅新归档被评估；未勾任务红；带标记豁免；旧归档补文件不触发 |
| T3 | backlog 一致性 | 构造引用已归档 / 不存在的 active / 正常 active | 前两者红，后者绿 |
| T4 | Bash guard 拦截面 | `tests/test_bash_write_guard.py`：`echo x > agent/y`、`cp x agent/y`、`tee docs/known-debt.md`、`sed -i`、`rm`、`cd agent && echo > y`、`bash -c`、`python -c` | 写受管/受保护被拦（exit 2） |
| T4b | Bash guard 防误伤 | 引号内写样式文本（`rg 'echo > agent/y'`、`git commit -m "cp x agent/y"`）、`cp agent/x /tmp/y`、`sed -i 's|agent/|x|' docs/y`、`>/dev/null`、`2>&1`、here-doc 数据、`git apply --check`、`git restore --staged` | 全部放行（exit 0）；修复误伤不得放松 T4 |
| T4c | Bash guard 匹配语义 | `**` 跨目录、`*` 不跨 `/`、`scriptsfoo/` 不命中、`.witnessloop/**`、policy 与内嵌默认表 parity | 与 witnessloop `paths.matches_any` 语义一致 |
| T5 | 全量 pytest | `uv run pytest -q` | 与基线同类同因（本机 `/tmp` 两条环境失败），无新增失败类型 |
| T6 | OpenSpec strict validate | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | 0 failed |
| T7 | 瘦 checker 自检 | `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` | exit 0（本 change 自身合规） |
| T8 | witnessloop | 用 CI 同版本 v1.7.0 跑 `check`：`/home/happy/wl170/bin/witnessloop check --root . --base origin/master --head HEAD`（tag object `00192ab` → commit `c9b2811`；`/home/happy/witnessloop` 当前不是 v1.7.0，不要用） | 通过 |
| T9 | platform gate | `uv run python scripts/platform_gate.py --verify` | exit 0，与实况一致 |
| T10 | 文档守卫 | `uv run pytest -q tests/test_round_model_alignment.py` | 通过 |

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis`（同一份清单，避免两处维护漂移）。
