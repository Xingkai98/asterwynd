# Q12: CI 与测试体系——怎么保证质量

## 讲稿

CI 解决"改动怎么验证、怎么防止回归"。Asterwynd 的 CI 有两个 job：**validate** 和 **benchmark-gate**。

**validate job** 跑三件事：
1. **全量 pytest**——1700+ 测试，分层覆盖（单测 / 工具协议 / AgentLoop / CLI / Web / benchmark）。
2. **OpenSpec strict validate**——校验所有 spec 和 active change 的文档完整性（proposal/design/tasks/spec delta 结构合法）。
3. **artifact checker**——机械校验 change 的受保护 artifact 证据：grill 设计追问记录、building 审阅报告 + manifest、workflow-events 结构化事件。这是"流程证据门禁"——没有审阅闭环就合不进来。

**benchmark-gate job** 跑冒烟 benchmark：用 `git worktree add` 建独立工作区，跑 gate-smoke 任务，验证 agent 能实际完成任务而非只过单测。

**测试体系**：测试分层（`docs/testing-guide.md`）——涉及 CLI / Web / benchmark / 工具协议 / AgentLoop 的变更必须覆盖对应层级测试；每个 bug fix 必须新增回归测试。环境依赖的测试（真实 API）用 skip 标记，CI 只跑可复现的。

面试重点：被问"怎么保证改进不导致衰退"——答案不只是"跑一下测试"，而是：全量 pytest + OpenSpec 文档门禁 + artifact 证据门禁 + benchmark 冒烟，四层防线。而且 protected-path 检查要求 full history（`fetch-depth: 0`），防止浅克隆跳过门禁。

## 代码走读

### 入口与调用链

```
GitHub Actions (.github/workflows/ci.yml)
  ├─ validate job: pytest → openspec validate → check_openspec_artifacts --base-ref
  └─ benchmark-gate job: gate-smoke benchmark
```

### 关键文件逐段

**`.github/workflows/ci.yml`**
- `validate` job：三步骤（`Run tests` / `Validate OpenSpec` / `Check OpenSpec artifacts`）。
  - `fetch-depth: 0`（full history）：protected-path 检查需 diff 与 PR base 对比，浅克隆会静默跳过门禁。
  - `--base-ref "$GITHUB_BASE_REF" --require-base`：artifact checker 显式 diff 改动范围，protected path 修改必须配 workflow-events 事件。
- `benchmark-gate` job：gate-smoke benchmark，用 `git worktree add <base_commit>` 建独立工作区（也要求 full history）。

**`scripts/check_openspec_artifacts.py`**
- `_check_impact_analysis`（248 行）：非平凡 change 必须维护结构化 Impact Analysis。
- `_check_reference_implementation_research`（304 行）：非 docs change 必须记录参考实现调研。
- `_check_design_review_task`（438 行）：**grill 门禁**——非 docs + 有 spec delta 的 change，写代码前必须有 `reviews/grill-design.md`（≥3 条决策 + Open Questions 全确认）。
- `_check_review_manifests`（732 行）：**审阅闭环门禁**——tasks 全勾选的完成 change，必须 building-review.md + manifest（绑定 reviewer run、base/head sha、报告 hash）且 PASS。
- `_check_benchmark_smoke_task`（594 行）：coding-agent 核心变更必须有 benchmark smoke 验证项。
- `_check_current_spec_sync_task`（421 行）：有 spec delta 的 change 必须含"当前规格同步"任务。

**`tests/`** — 测试分层。
- `tests/agent/`：运行时单测（loop / tools / memory / subagent / context ...）。
- `tests/agent/tools/`：工具协议测试。
- `tests/web_tests/`：Web/CLI 测试。
- `tests/agent/memory/test_reversibility.py`：本 change 新增的回归测试（20 个）。

**`docs/testing-guide.md`** — 测试分层规则。

### 设计理由

- **文档门禁不只是跑测试**：OpenSpec + artifact checker 校验的是"流程证据"——grill 设计、审阅闭环、workflow-events，这些是测试测不出来的工程纪律。
- **full history 防绕过**：浅克隆会让 protected-path 检查静默跳过，`fetch-depth: 0` 保证门禁真实生效。
- **benchmark 独立 gate**：单测过不代表 agent 真能干活，benchmark-gate 用真实任务验证（gate-smoke）。
- **回归测试纪律**：每个 bug fix 必须新增回归测试（AGENTS.md），bug 修复后测试先行证明根因被消灭。
