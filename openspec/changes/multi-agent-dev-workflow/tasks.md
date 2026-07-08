## 1. 规格

- [ ] 1.1 完成 spec delta：`dev-workflow-state-machine`、`change-documentation`、`subagents`。
- [ ] 1.2 明确本 change 的范围、非目标和验收标准（见 design.md Goals / Non-Goals）。
- [ ] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认 state machine schema、handoff note 机制、human gate 行为、角色 agent 路由、单 agent 全流程兼容和回退路径都有最终方案。
- [ ] 1.4 维护 `## Impact Analysis`，确认各影响面分析准确。
- [ ] 1.5 维护 `## Reference Implementation Research`（本 change 已设为 disabled，如后续发现需要调研则更新）。
- [ ] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录设计追问结论。

## 2. 测试

- [ ] 2.1 handoff.json schema 校验单元测试：合法流转通过、非法流转拒绝、必填字段缺失报错。
- [ ] 2.2 状态机流转单元测试：四种 trigger 类型、所有合法 phase 流转路径、回退路径、skip 路径。
- [ ] 2.3 handoff note 生成单元测试：handoff skill 可用路径、fallback prompt 路径、文件写入 `.handoff/` 目录。
- [ ] 2.4 角色 agent 路由集成测试：给定 state 创建正确类型子 session；同一 agent 连续多阶段不切换。
- [ ] 2.5 code-review phase 流转测试：`reading_diff` → `analyzing_tests` → `reviewing_code` ⇄ `requesting_changes` → `ready_for_review` → 回退到 `building`。
- [ ] 2.6 human review gate 流转测试：`human_review` trigger 通过、跳过、回退。
- [ ] 2.7 阻塞状态流转测试：进入 blocked 和解除阻塞。
- [ ] 2.8 Artifact checker 新增校验项测试：`handoff.json` 存在性、必填字段非空。
- [ ] 2.9 路由配置单元测试：executor 枚举校验、session_mode 枚举校验、两层覆盖（全局默认 + per-change）逻辑。

## 3. 实现

- [ ] 3.1 实现 `handoff.json` schema 定义（Pydantic model 或 dataclass），包含所有字段和 trigger 枚举。
- [ ] 3.2 实现状态机流转引擎：合法流转表校验、transition 日志追加、当前状态更新。
- [ ] 3.3 实现 `handoff.json` 初始化逻辑（创建 change 时自动生成，初始状态 `planning.exploring`）。
- [ ] 3.4 实现 handoff note 生成模块：优先调用 `handoff` skill，不可用时使用内置 fallback prompt。
- [ ] 3.5 实现 `.handoff/` 目录创建和 `.gitignore` 规则。
- [ ] 3.6 实现角色 agent 类型注册表（Planner / Reviewer / Builder / CodeReviewer / Closer），映射到 phase 和 sub_state。
- [ ] 3.7 实现角色 agent 路由逻辑：根据 `handoff.json` state 选择 agent 类型并创建子 session。
- [ ] 3.8 实现路由配置模块：两层覆盖（全局默认 + per-change）、executor 分发（inline / subagent / claude-code）、session_mode 控制。
- [ ] 3.9 实现创建 change 时路由配置提示交互：展示默认配置、询问是否调整。
- [ ] 3.10 更新项目 artifact checker（`scripts/check_openspec_artifacts.py`）：新增 `handoff.json` 存在性检查、必填字段非空检查。
- [ ] 3.11 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单。

## 4. 验证

- [ ] 4.1 运行 handoff.json / 状态机 / handoff note 相关单元测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [ ] 4.4 运行项目 OpenSpec artifact checker `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 4.5 因涉及 subagents（核心 coding-agent 路径），跑通至少一个 benchmark smoke。
- [ ] 4.6 验证 `.handoff/` 目录被 `.gitignore` 排除。

## 5. 文档与 spec 同步

- [ ] 5.1 将 `dev-workflow-state-machine` spec delta 合并到 `openspec/specs/dev-workflow-state-machine/spec.md`。
- [ ] 5.2 将 `change-documentation` spec delta 合并到 `openspec/specs/change-documentation/spec.md`。
- [ ] 5.3 将 `subagents` spec delta 合并到 `openspec/specs/subagents/spec.md`。
- [ ] 5.4 更新 `docs/requirements-process.md` 开发流程章节，反映新的四阶段状态机模型。
- [ ] 5.5 更新 `AGENTS.md` 自然语言路由表，补充角色 agent 路由说明。

## 6. PR 收尾

- [ ] 6.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-multi-agent-dev-workflow/`。
- [ ] 6.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步并行开发批次。
- [ ] 6.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 6.4 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
