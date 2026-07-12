## 1. 规格

- [ ] 1.1 更新受影响 capability 的 spec delta（agent-runtime, memory-context）。
- [ ] 1.2 明确本 change 的范围、非目标和验收标准。
- [ ] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`（已完成 2026-07-12）。
- [ ] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面。
- [ ] 1.5 维护 `## Reference Implementation Research`。
- [ ] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题（已完成）。

## 2. 测试

### Phase 1: ContextBuilder

- [ ] 2.1 按 TDD 先新增 ContextBuilder 注册/排序/渲染/截断单元测试。
- [ ] 2.2 覆盖 P0 层永不截断测试。
- [ ] 2.3 覆盖 token budget 超限与逐层截断测试（从 P5 尾部砍）。
- [ ] 2.4 覆盖层间 `---` 分隔符正确位置测试。
- [ ] 2.5 覆盖重构前后 context 内容对比快照测试（确保行为不变）。

### Phase 2: System Prompt

- [ ] 2.6 System Prompt 三段结构完整性验证。
- [ ] 2.7 `pyproject.toml` 版本解析 + `{cwd}` 占位符替换。
- [ ] 2.8 `--system` 参数追加在末尾（`---` 分隔）。

### Phase 3: ASTER.md

- [ ] 2.9 ASTER.md 上界确定逻辑（Git 根 / home fallback）。
- [ ] 2.10 全量拼合遍历（上界→CWD）+ 来源标注格式。
- [ ] 2.11 `ASTER.local.md` > `ASTER.md` 优先级。
- [ ] 2.12 `/init` 项目类型检测（pyproject.toml / package.json / go.mod）。
- [ ] 2.13 `/init` 已有 AGENTS.md/CLAUDE.md 导入逻辑。

### Phase 4: 压缩

- [ ] 2.14 LLMSummarizer 压缩行为 + 压缩后 token ≤ budget。
- [ ] 2.15 TruncationSummarizer 降级行为 + 警告。
- [ ] 2.16 摘要为 user message 验证。
- [ ] 2.17 90% 触发逻辑 + 最小间隔 5 轮防抖。
- [ ] 2.18 tool chain 完整性保护验证。

### 集成测试

- [ ] 2.20 CLI 和 Web 入口使用新 system prompt。
- [ ] 2.21 `/init` 在空目录、有项目文件的目录、有已有 AGENTS.md 的目录中运行。
- [ ] 2.22 无 LLM 降级路径。
- [ ] 2.23 Benchmark smoke：确保 AgentLoop 核心路径行为不变。

## 3. 实现

### Phase 1: ContextBuilder 核心

- [ ] 3.1 实现 `agent/context/__init__.py`。
- [ ] 3.2 实现 `agent/context/protocol.py`（BuildContext, ContextSource 协议）。
- [ ] 3.3 实现 `agent/context/builder.py`（ContextBuilder 类：register / set_budget / build）。
- [ ] 3.4 实现现有方法 → ContextSource 迁移：
  - `MemoryIndexSource` (P2): `_messages_with_run_context()` 中 memory_index 逻辑
  - `SkillIndexSource` (P4): `skill_runtime.render_skill_index()`
  - `SkillActiveSource` (P4): `skill_runtime.render_active_skill_context()`
  - `PlanModeSource` (P5): `_plan_mode_context()`
  - `PlanningStateSource` (P5): `_planning.render_context()`
  - `TodoSource` (P5): `_todo_context()`
- [ ] 3.5 重构 `AgentLoop._messages_with_run_context()` 委托给 ContextBuilder。
- [ ] 3.6 `AgentLoop.__init__()` 中初始化 ContextBuilder 并静态注册所有 source。

### Phase 2: System Prompt 优化

- [ ] 3.7 实现 `agent/context/sources.py` 中 `SystemPromptSource` (P0)。
- [ ] 3.8 重写 CLI `agent/main.py` 和 Web `web/session.py`，统一使用 `SystemPromptSource`。
- [ ] 3.9 `--system` 参数合并逻辑。

### Phase 3: ASTER.md 注入

- [ ] 3.10 实现 `AsterMdSource` (P1)：上界确定 + 全量拼合遍历 + 来源标注 + precedence。
- [ ] 3.11 实现 `AsterLocalMdSource`（追加在 ASTER.md 之后）。
- [ ] 3.12 实现 `/init` 核心逻辑（`agent/tools/builtin/init.py`）：项目检测 + AGENTS.md 导入 + 命令生成 + header 模板。
- [ ] 3.13 实现 `asterwynd init` CLI 入口。
- [ ] 3.14 在 ContextBuilder 中注册 `AsterMdSource` (P1)。

### Phase 4: 上下文压缩

- [ ] 3.15 实现 `agent/context/summarizer.py` 中 `Summarizer` 协议。
- [ ] 3.16 实现 `LLMSummarizer`（四段式结构化摘要：已完成/关键决策/进行中/阻塞与待办）。
- [ ] 3.17 实现 `TruncationSummarizer`（无 LLM 降级）。
- [ ] 3.18 重构 `agent/memory/manager.py` 中 `compact()` 委托给 Summarizer。
- [ ] 3.19 接入 AgentLoop 的压缩触发检查（90% 阈值 + 5 轮间隔）。

### 收尾

- [ ] 3.20 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单。
- [ ] 3.21 更新必要文档。

## 4. 验证

- [ ] 4.1 运行相关单元/集成测试。
- [ ] 4.2 运行全量测试 `uv run pytest -q`。
- [ ] 4.3 运行 OpenSpec strict validate。
- [ ] 4.4 运行项目 OpenSpec artifact checker。
- [ ] 4.5 确认 baseline CI 命令可本地通过。
- [ ] 4.6 涉及 AgentLoop 核心路径，跑通至少一个 benchmark smoke。
- [ ] 4.7 涉及 Web，运行 Web session/server 测试。
- [ ] 4.8 涉及 CLI，运行 CLI smoke。

## 5. PR 收尾

- [ ] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-implement-context-injection-pipeline/`。
- [ ] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change。
- [ ] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [ ] 5.4 确认 Reference Implementation Research 已记录最终调研状态。
- [ ] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
