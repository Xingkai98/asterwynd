# Tasks: platform-gate

## 1. 规格

- [x] 1.1 创建 proposal.md，明确需求、非目标、行为定义与验收（关联 issue #138，父 map #121）。
- [x] 1.2 创建 design.md，记录 Context、Goals/Non-Goals、Decisions（D1-D8）、Risks、Testing Strategy。
- [x] 1.3 维护 `## Impact Analysis`（proposal.md），列出影响/不影响面。
- [x] 1.4 维护 `## Reference Implementation Research`（research_tier: full + GitHub 平台能力与配置即代码调研结论）。
- [x] 1.5 开发前使用 batch-grill-me（独立零记忆 subagent 等价设计追问）审视 `design.md`，产出 `reviews/grill-design.md`（≥3 条 Confirmed Decisions），逐项确认实现细节；停轮获得用户对 `## Open Questions` 的确认并记录到 `## User Confirmation`。
- [x] 1.6 更新 `docs/openspec-change-backlog.md`，把 platform-gate 加入未实现队列（配 workflow-events.jsonl 解释事件）。
- [x] 1.7 当前规格同步：把 spec delta 合并到现有 `openspec/specs/platform-gate/spec.md`（覆盖占位「预留能力域」内容，SHALL 目标语言，确认未实现能力没有被写成已实现），配 workflow-events.jsonl `current_spec_synced` 事件（flow-policy `openspec/specs/` prefix → event_explained）。

## 2. 测试

- [x] 2.1 payload 构造单测：`--apply` 执行 GET-modify-PUT 构造的 payload 符合 GitHub PUT 形状（完整四必需字段 + `restrictions: null`、剔除只读派生字段、reviews 保留 GET 可写子字段仅覆盖 count）；幂等（两次 apply 构造同一 payload）；断言任意深度 `_description` 不出现在 PUT body（嵌套场景）。
- [x] 2.2 verify 比对单测：mock GET 返回当前实况 → 归一化比对 → 一致 exit 0 / 漂移 exit 1；忽略只读派生字段（checks/url/contexts_url 等）；contexts 按集合比对（顺序无关）。
- [x] 2.3 错误处理单测：gh 不存在 / 认证失败 / API 非零退出 → exit 2 fail-closed；目标 JSON schema 非法 → exit 2。
- [x] 2.4 JSON schema 校验单测：`platform-gate.json` 满足脚本期望结构；`_description` 注释字段不影响解析。
- [x] 2.5 全量 pytest 回归：现有测试保持全绿（pre-existing tree-sitter 环境失败除外）。

## 3. 实现

- [x] 3.1 创建 `scripts/platform-gate.json`：目标状态声明（required_status_checks strict + contexts=[validate, benchmark-gate]、required_conversation_resolution enabled、required_pull_request_reviews count=0 + approve=1 触发条件注释、enforce_admins），schema 风格对齐 flow-policy.json。
- [x] 3.2 创建 `scripts/platform_gate.py`：stdlib-only，`--apply`（GET-modify-PUT——GET → merge 声明字段 → 剔除只读派生 → 变换 → PUT 完整 payload 含四必需字段 + `restrictions: null`，apply 前预检复用 verify 的归一化/diff，diff 走 stderr 不交互）、`--verify`（GET → 白名单归一化比对 → diff → 漂移 exit 1，null/缺失视为漂移）、`--config` 输入路径 + 唯一 JSON 输出、`--repo` 短路 git remote 解析、错误 fail-closed。
- [x] 3.3 文档：AGENTS.md 补合入门禁描述（required checks 全绿 + conversations 全 resolve + approve=1 触发条件 + `platform_gate.py --verify` 命令）；Impact Analysis 回写。
- [x] 3.4 实现中发现的新影响面已回写 Impact Analysis 和本任务清单。

## 4. 验证

- [x] 4.1 运行相关单元测试（payload/verify/错误处理/schema）。
- [x] 4.2 运行全量测试 `uv run pytest -q`。
- [x] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行项目 artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.5 平台实况验证（合入后由主 session 执行）：`python scripts/platform_gate.py --apply` + `--verify`，确认 required checks 含 validate+benchmark-gate、conversation resolution 开启（见任务 5.6 顺序说明）。**实现期已用临时分支 `platform-gate-put-probe` 做非破坏性 PUT 实测验证 payload 形状（design D3，零残留）；真实 master 的 apply 由主 session 在 PR 合入后执行。**

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-platform-gate/`，配 workflow-events.jsonl `change_archived` 事件（flow-policy `openspec/changes/archive/` prefix → event_explained）。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次章节，配 workflow-events.jsonl `backlog_updated` 事件（flow-policy `docs/openspec-change-backlog.md` exact → event_explained）。
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [x] 5.6 PR 合入后，主 session 依次执行 `python scripts/platform_gate.py --apply` → `--verify`；两者均通过后才关闭 issue #138，关闭 comment 记录 apply+verify 结果；若失败，暂不关 issue，保持 open 记录失败原因与重试命令（apply 幂等，可安全重试）。**顺序红线**：`--apply` 必须在 PR 合入后执行——合入前 apply 会开启 conversation resolution 把 PR 锁在闸门下。（本任务由主 session 在 PR 合入后执行，实现 agent 不执行，勾选仅用于完成 change 收尾。）
- [x] 5.7 合入前用 `gh pr checks <PR>`（或 GitHub UI）核对本 PR 的 `benchmark-gate` 与 `validate` check 均存在且 state 为 SUCCESS，避免合入后 apply 把 benchmark-gate 设为 required 时全仓立即锁死。
- [x] 5.8 运行 `/review-loop` 直至 PASS（或 3 轮封顶），产出 `reviews/building-review.md` + review manifest（checker 对 tasks 全勾的 change 强制）。
