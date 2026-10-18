# Tasks: 下掉旧门禁主体 + 瘦 checker + Bash guard

> 前置门（第 0 节）不完成不得写实现代码或测试代码。grill 由独立零记忆 subagent 执行（`/grill`），
> 随后按 issue #298 跑设计阶段对抗闭环，产出 `reviews/grill-design.md` 与 `reviews/grill-adversarial.md`。
> **停轮口径**：用户已在 issue #322 拍板形态；设计里不应有需要用户拍板的问题。若确实冒出一个，
> 停下来写清楚附例子与推荐，不代拟答案。
>
> **证据顺序与 commit 边界（grill H1 + 对抗 I-4）**：witnessloop manifest 绑定
> `tasks_hash` / `spec_hash` / `head_sha`，`tasks.md` 与 `docs/**` 不在 stale 豁免集。必须按
> 「事件 → backlog 清理 → tasks 结算 → **提交所有内容** → 归档 move **提交纯 rename** →
> 用归档目录名 build manifest → **提交 evidence（reports + manifests）** → 最终 check → PR」
> 执行。先 build 再结算 tasks、或把内容改动随证据一起提交，都会让 manifest stale。

## 0. 设计追问与对抗收敛（前置门）

- [x] 0.1 用 `grilling` skill（独立零记忆 subagent）对 `design.md` 做设计追问，产出
  `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含决策 / 理由 / 来源）。
- [x] 0.2 跑设计阶段对抗闭环（与 `/review-loop` 同构、审设计而非代码），产出
  `reviews/grill-adversarial.md`；重点挑战 6 条规则的触发矩阵、Bash guard 的拦截面与残余绕过面、
  platform gate 保留边界；能由代码/实测判定的 Open Question 当场判掉。
- [x] 0.3 停轮检查：确认没有需要用户拍板的问题；有则停下报告。
- [x] 0.4 把 grill 与对抗闭环结论回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 规格

- [x] 1.1 `openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md`：MODIFIED 承载分工、policy
  前置、本地守卫退步、保留项目规则、manifest 承载、双守卫并存；ADDED 瘦 checker 六条判据、
  Bash 写前拦截、事件投影退役。
- [x] 1.2 `openspec/changes/slim-gates/specs/change-documentation/spec.md`：MODIFIED grill 机械强制、
  机械检查、CI、RIR、handoff、信任边界；删除对 `dev-workflow-state-machine` 的交叉引用。
- [x] 1.3 `openspec/changes/slim-gates/specs/multi-agent-collaboration/spec.md`：MODIFIED
  `Orchestration Reuses Workflow Persistence Discipline`，把 `agent/workflow/` 改指
  `agent/subagent/workflow_store.py`。
- [x] 1.4 `docs/openspec-change-backlog.md`：登记本 change 到合适批次。
- [x] 1.5 同步 current spec：施加 delta 前**先从 HEAD 恢复 `openspec/specs/**`**（不接受 SPIKE 的
  规格改写），再把三份 delta 就地覆盖；删除 `openspec/specs/dev-workflow-state-machine/spec.md`；
  **手工改写 `dev-workflow-gate` 的 `## Purpose` 段**（现行版本说旧门禁「全部继续照跑」，SPIKE
  版本说六条规则「无机械实现」，两者都要改成最终形态）；从 `openspec/project.md` 的能力域地图
  移除或改写 `dev-workflow-state-machine` 条目。

## 2. 测试先行（TDD）

- [x] 2.1 新增 `tests/test_slim_project_rules.py`：RIR / Impact Analysis / benchmark smoke 三条规则
  各至少 1 正例 + 1 否定用例，覆盖 `research_tier` 结构门槛、多行字段、tasks 全勾后的内容门槛。
- [x] 2.2 同文件覆盖 tasks / 归档点完成度：未勾无标记红、`(post-merge)` 8 变体豁免与 3 负例、
  缺 tasks / 无 checkbox / 全未勾红、`AR` 新归档与「旧归档补文件」区分、**本次 diff 触及的非
  日期前缀归档目录**红、`.gitkeep` 不误报；非 docs + DESIGN_TYPES + spec delta 的归档缺
  `grill-design.md`（<3 决策 / Open Question 未确认）或 `grill-adversarial.md` 红。
- [x] 2.3 同文件覆盖 backlog 一致性与 building review `## 闭环出口`：引用已归档 / 不存在 change 红；
  原 `_review_exit_verdict` 参数表逐条搬入（`PASS`、`BLOCKED`、`CHANGES_REQUESTED`、`PASSED`、
  `未定`、全角 `｜`、`|` 多出口、fenced block 模板、有序列表前缀、重复出口、缺小节）。
- [x] 2.4 新增 `tests/test_bash_write_guard.py`：写受管路径（重定向 / `cp` 目的 / `mv` / `tee` /
  `sed -i` / `dd` / `install` / `rm` / `touch` / `mkdir` / `rmdir` / `unlink` / `truncate` / `ln` /
  `chmod` / `chown` / `perl -i` / `ruby -i` / `curl -o` / `wget -O`）被拦；写受保护 artifact 被拦；
  `cd` 链、`bash -c` / `sh -c` / `eval`、命令替换、绝对路径、`..` 归一化全覆盖；
  `git checkout -- <managed>` / `git restore <managed>` / `git apply`（无 `--check`）被拦，
  `git rm` / `git mv` 放行。
- [x] 2.5 同文件覆盖防误伤（grill H3）：`rg 'echo > agent/y'`、`git commit -m "cp x agent/y"`、
  `cp agent/x /tmp/y`、`sed -i 's|agent/|x|' docs/y`、`>/dev/null`、`2>&1`、here-doc 数据、
  `git apply --check`、`git restore --staged`、`rsync` 源/目的，全部放行。
- [x] 2.6 同文件覆盖 match 语义与 parity（grill M6）：`**` 跨目录、`*` 不跨 `/`、
  `scriptsfoo/` 不命中 `scripts/**`、`.witnessloop/**`；内嵌默认表与 `.witnessloop/policy.json`
  当前值一致。
- [x] 2.7 残余绕过面（变量展开、符号链接、`find -exec`、shell 函数、VCS 内容写入、被执行程序）写成显式
  「已知绕过」用例并登记在测试与文档中（不追求挡死，但不能静默）。
- [x] 2.8 调整 `tests/test_round_model_alignment.py` 的**三处**引用：ALLOWLIST 条目、
  `PER_FILE_REQUIRED` 映射、专用单测；保留有界批次模型守卫与 checker 提示断言。
  `tests/agent/tools/test_guard_three_state.py` 的示例命令可保留 SPIKE 的替换（非必须）。
- [x] 2.9 按 `design.md` Decision 12 的「旧用例 → 新用例」表逐项核对，确认没有判据边界随旧测试
  删除而消失。

## 3. 实现

- [x] 3.1 重写 `scripts/check_openspec_artifacts.py`：只保留 6 条规则与必要的前置解析
  （`parse_change_type` / H2 提取 / 归档 diff 识别 / backlog 解析 / exit 语义）；Change Type
  无法解析时 exit 1 并明确报错，不静默跳过。
- [x] 3.2 新增 `scripts/bash_write_guard.py`：Bash-only PreToolUse guard，quote-aware tokenizer，
  策略读 `.witnessloop/policy.json`，复用旧写意图模式表并补 `cd` 链 / 嵌套 shell / 命令替换；
  只放行 `git rm` / `git mv`；显式路径的 restore/checkout/apply 拦截；merge/rebase/cherry-pick/stash/am 登记为绕过面。
- [x] 3.3 新增 `scripts/bash_write_guard.example.json`：PreToolUse / matcher `Bash` 示例。
- [x] 3.4 用 `git cherry-pick -n e9d23af` **只取代码 / 测试 / CI 的删除**（SPIKE 仅本地存在；
  删除清单以 proposal 为准）；cherry-pick 后立即从 HEAD 恢复**所有文档与规格**：
  `AGENTS.md`、`docs/**`（含 `docs/known-debt.md`、`docs/adr/**`、interview-script）、
  `openspec/specs/**`、`openspec/project.md`、`openspec/templates/tasks.md`、
  `docs/openspec-change-backlog.md`，再手工重写（SPIKE 文档不作为事实来源）；随后从 HEAD
  恢复 platform gate 四项（脚本 / JSON / 测试 / 规格）；跳过 `d48fd93`。
- [x] 3.5 更新 `.github/workflows/ci.yml`：`validate` 的 checker 步骤改为调用瘦 checker；删除
  `Check archived changes` 步骤；`fetch-depth` 注释同步改为新 checker 的 diff 用途；其余 job 不动。
- [x] 3.6 更新 AGENTS.md / docs/development-guide.md / docs/requirements-process.md /
  docs/agents/issue-tracker.md / docs/known-debt.md / openspec/project.md /
  openspec/templates/tasks.md / docs/interview-script（Q12/Q14）相关条目：
  - 清理旧脚本、旧 policy、`flow status` 引用；`docs/requirements-process.md` 的 workflow 总开关
    （`workflow_methods.json` / `workflow_state.py disable/enable`）改为历史说明；
    `AGENTS.md` 的「门禁依赖分支名推导 change-id」句改为新现实；
  - **改语义而不只是删名字**：`openspec/changes/archive/**` 不再要求解释事件（由 witnessloop
    归档到达校验承担）；`workflow-state.json` / `workflow-events.jsonl` 不再有 CLI 写通道；
  - 写入 checker 命令与 exit 语义（0/1/2）；
  - 写入 Bash guard 安装方式（user-level settings 或用绝对路径在每个 worktree 手动安装）、
    两 hook 分工与残余绕过面。
- [x] 3.7 未发现需要回写的新影响面（实现与 delta 一致）。

## 4. 验证

- [x] 4.1 `uv run pytest -q tests/test_slim_project_rules.py tests/test_bash_write_guard.py
  tests/test_round_model_alignment.py tests/test_platform_gate.py`。
- [x] 4.2 `uv run pytest -q` 全量；与基线（2 failed / 4530 passed / 9 skipped，失败均为本机 `/tmp`
  环境坑）对比，不得新增失败类型。
- [x] 4.3 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base`。
- [x] 4.5 `uv run python scripts/platform_gate.py --verify`（只读，与实况一致）。
- [x] 4.6 `uv run asterwynd benchmark-gate benchmarks/tasks/gate-smoke --source-repo . --runs-dir
  /tmp/benchmark-gate-runs-slim-gates --baseline benchmarks/baseline.json --require-baseline --skip-p95`。
- [x] 4.7 手工验收 Bash guard：`echo x > agent/y` / `cp x agent/y` / `tee docs/known-debt.md` /
  `sed -i ... agent/loop.py` 被拦；`ls` / `grep` / `cat` / 2.5 的防误伤清单放行；记录原始输出。
- [x] 4.8 两 hook **同时安装**实测：在临时 Claude Code settings 中同时挂 witnessloop plugin
  guard（`Write|Edit`）与 `scripts/bash_write_guard.py`（`Bash`），用同一组 Write / Edit / Bash
  payload 触发；记录（a）两个 hook 是否都执行、（b）串行/并行与并集阻断语义、（c）被拦时提示归属、
  （d）Write/Edit 只由 witnessloop 求值、Bash 只由本仓 guard 求值。命令与原始输出记入
  `docs/development-guide.md` 的本地守卫节；若本机无法安装 plugin，如实记录「未实测」并停下报告，
  不得用「分别调用」冒充同时启用。

## 5. 实现后独立审阅闭环

- [ ] 5.1 跑 `/review-loop slim-gates`，产出 `reviews/building-review.md`（含 `## 闭环出口` PASS）。
- [ ] 5.2 CHANGES_REQUESTED 则按有界批次模型修复并复审，直到 PASS。
- [ ] 5.3 清理中间轮产物（不在任何 manifest `report_path` 上的报告）。

## 6. 证据与归档（严格按此顺序）

> **结算体例（与 `stage-c-required-switch` 相同，但修正了勾选提交点）**：6.4–6.6 是同一收尾
> 序列中的机械动作，在 **6.3 的最终内容提交**里按**终态**勾选；6.4 的归档 move 提交必须是纯
> rename（不再改 `tasks.md`），6.5 的 evidence 提交只含 reports/manifests。它们对应的命令与原始
> 输出记录在本任务行或 PR 描述。6.1–6.2 按实际完成时点勾选。section 7 的合入后动作才用
> `(post-merge)`。

- [ ] 6.1 写 `workflow-events.jsonl`，逐路径覆盖本次 diff 的受保护写入：
  - `current_spec_synced`：`openspec/specs/dev-workflow-gate/spec.md`、
    `openspec/specs/change-documentation/spec.md`、
    `openspec/specs/multi-agent-collaboration/spec.md`、
    `openspec/specs/dev-workflow-state-machine/spec.md`（删除）；
  - `backlog_updated`：`docs/openspec-change-backlog.md`；
  - `protected_artifact_explained`：`docs/known-debt.md`（本 change 会修改它，**无条件**写事件）；
  - `change_archived`：本 change 的归档目录。
  `approved_by` 非空。
- [ ] 6.2 从 `docs/openspec-change-backlog.md` 移除本 change（这是生命周期要求；不要以
  「backlog 一致性会判红」为由——当前条目是散文 bullet，不匹配 checker 的引用模式）。
- [ ] 6.3 结算 `tasks.md`：全部已完成项勾选；section 7 的 closeout 项标 `(post-merge)`；未勾且未标
  `(post-merge)` 的任务必须为 0 条。**随后提交所有内容改动**（6.1–6.3、docs/specs/backlog/
  reviews 报告），确保 manifest build 的 `head_sha` 包含最终 `tasks_hash` / `spec_hash`。
- [ ] 6.4 手工 `git mv` 归档到 `openspec/changes/archive/2026-10-18-slim-gates/`，**单独提交纯
  rename**（不跑 `openspec archive`；此提交不得夹带内容改动）。
- [ ] 6.5 归档 move 之后，用 **v1.7.0** 的 `witnessloop manifest build` 以归档目录名重建三份
  manifest（`grill` / `grill-adversarial` / `building`），绑定 `reviews/` 下全部 `.md`；
  然后**单独提交 evidence 改动**（reports + manifests）。可执行锚点：
  `/home/happy/wl170/bin/witnessloop`（tag object `00192ab` → commit `c9b2811`；
  `/home/happy/witnessloop` 当前不是 v1.7.0，不要用）。
- [ ] 6.6 最终机械复核（在最终 head 上）：`/home/happy/wl170/bin/witnessloop check --root .
  --base origin/master --head HEAD` 通过；
  `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` exit 0；
  OpenSpec strict validate 通过；`platform_gate.py --verify` 一致。

## 7. 合入之后

- [ ] (post-merge) 7.1 发起 PR，在 `gate / check` 判绿后用 `--merge` 合入（不 squash）。
- [ ] (post-merge) 7.2 在 issue #322 追加完成说明 comment 并关闭；在 #305 追加 comment（「逐项
  下掉旧件」完成一刀，issue 保持 OPEN 或按用户口径收口）。
- [ ] (post-merge) 7.3 确认 active change 目录不再存在、backlog 干净、本地 `master` 已快进；
  复核 `master` required 仍为 `["gate / check"]`。
