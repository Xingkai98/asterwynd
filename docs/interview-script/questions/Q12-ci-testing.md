# Q12: CI 与测试体系——怎么保证质量

## 讲稿

CI 解决"改动怎么验证、怎么防止回归"。Asterwynd 的自建 CI 有三个 job：**validate**、**benchmark-gate** 和 **windows-platform**；另有接入的 witnessloop caller 提供的 **`gate / check`**。**阶段 C 之后 `master` 的 required check 只有 `gate / check`**——上面三个照跑、只是不再拦合并（降级不是关闭）。

**validate job** 跑三件事：
1. **全量 pytest**——4500+ 测试，分层覆盖（单测 / 工具协议 / AgentLoop / CLI / Web / benchmark）。
2. **OpenSpec strict validate**——校验所有 spec 和 active change 的文档完整性（proposal/design/tasks/spec delta 结构合法）。
3. **瘦项目规则 checker**——只做 witnessloop 不覆盖的 6 条项目规则：Reference Implementation Research、Impact Analysis、benchmark smoke 任务、tasks / 归档点完成度、backlog 一致性、building review 的 `## 闭环出口` PASS。change 契约、review manifest、grill stage 证据与受保护写入解释由 witnessloop `gate / check` 负责，不在这里重复。

**benchmark-gate job** 跑冒烟 benchmark：用 `git worktree add` 建独立工作区，跑 gate-smoke 任务，验证 agent 能实际完成任务而非只过单测。

**测试体系**：测试分层（`docs/testing-guide.md`）——涉及 CLI / Web / benchmark / 工具协议 / AgentLoop 的变更必须覆盖对应层级测试；每个 bug fix 必须新增回归测试。环境依赖的测试（真实 API）用 skip 标记，CI 只跑可复现的。

面试重点：被问"怎么保证改进不导致衰退"——答案不只是"跑一下测试"，而是：全量 pytest + OpenSpec strict validate + 6 条项目规则 + benchmark 冒烟 + witnessloop 流程门禁。归档点完成度要 diff 到 PR base，所以 `fetch-depth: 0`；浅克隆会让 base 不可解析，checker 用 `--require-base` fail-closed。

## 代码走读

### 入口与调用链

```
GitHub Actions (.github/workflows/ci.yml)
  ├─ validate job: pytest → openspec validate → slim project-rule checker --base-ref
  ├─ benchmark-gate job: gate-smoke benchmark
  └─ windows-platform job: Windows 平台语义回归
GitHub Actions (.github/workflows/witnessloop.yml)   ← required（阶段 C 之后）
  └─ gate job → reusable gate.yml@v1.7.0 的 check job
     （合入结论只由它决定；上面三个 job 照跑但不拦）
```

### 关键文件逐段

**`.github/workflows/ci.yml`**
- `validate` job：`Run tests` / 编码 warn-as-error 子集 / `Validate OpenSpec` / `Check project rules`。
  - `fetch-depth: 0`（full history）：归档点完成度要 `git diff <PR base>` 找新归档目录，浅克隆会让 base 不可解析。
  - `--base-ref "${{ github.event.pull_request.base.sha }}" --require-base`：瘦 checker 显式绑定 PR base，不能静默跳过归档门。
- `benchmark-gate` job：gate-smoke benchmark，用 `git worktree add <base_commit>` 建独立工作区（也要求 full history）。
- `witnessloop.yml`：required 的 `gate / check`，承载 change 契约、三份 stage manifest、grill 报告正文与受保护写入解释。

**`scripts/check_openspec_artifacts.py`（瘦 checker）**
- `_check_reference_implementation_research`：结构门槛（`research_tier` / `status` / `reason`）在 proposal 阶段生效；tasks 全勾或归档点时再查内容门槛与 exempt 证据。
- `_check_impact_analysis`：非 docs change 的 proposal 或 design 必须有非占位 `## Impact Analysis`。
- `_check_benchmark_smoke_task`：proposal 命中核心能力 / 代码模式时，tasks 文本必须同时出现 benchmark 与 smoke。
- `_check_archived_completion_gate`：新归档目录（`--diff-filter=AR` 且 base 树不存在）检查 building review、grill 证据、RIR 内容门槛与 tasks 完成度；未勾且无 `(post-merge)` 一律红。
- `_review_exit_verdict` / `_check_building_review`：解析 `## 闭环出口`，`BLOCKED` / `CHANGES_REQUESTED` 宽触发红，完成面必须 PASS。
- `check_backlog_consistency`：backlog 不得引用已归档或不存在 active change。

**`scripts/bash_write_guard.py`（本地 Bash guard）**
- 只处理 `Bash` 工具调用；写受管路径（`agent/**`、`scripts/**`、`web/**`）或受保护 artifact 时 exit 2，只读命令放行。
- quote-aware tokenizer + `cd` 链 / 嵌套 shell / 命令替换；`git rm` / `git mv` 放行，显式路径的 `git restore` / `checkout --` 与 `git apply` 拦截。
- 已知绕过面（变量展开、符号链接、merge/rebase/cherry-pick 等）如实登记；CI 仍是最终防线。

**`tests/`** — 测试分层。
- `tests/agent/`：运行时单测（loop / tools / memory / subagent / context ...）。
- `tests/agent/tools/`：工具协议测试。
- `tests/web_tests/`：Web/CLI 测试。
- `tests/agent/memory/test_reversibility.py`：本 change 新增的回归测试（20 个）。

**`docs/testing-guide.md`** — 测试分层规则。

### 设计理由

- **文档门禁不只是跑测试**：OpenSpec + witnessloop + 瘦 checker 校验的是"流程证据"——change 契约、grill / 审阅闭环、项目规则，这些是测试测不出来的工程纪律。
- **full history 防绕过**：浅克隆会让归档点 diff 的 base 不可解析，`--require-base` + `fetch-depth: 0` 保证门禁真实生效。
- **benchmark 独立 gate**：单测过不代表 agent 真能干活，benchmark-gate 用真实任务验证（gate-smoke）。
- **回归测试纪律**：每个 bug fix 必须新增回归测试（AGENTS.md），bug 修复后测试先行证明根因被消灭。
