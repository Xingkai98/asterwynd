## 1. 规格

- [x] 1.1 更新 `skills` spec delta，定义 runtime 加载、always 注入、matched 注入和 reload 语义。
- [x] 1.2 更新 `configuration` spec delta，定义 skill roots 配置。
- [x] 1.3 更新 `cli` spec delta，定义 `/skills`、`/skills reload` 和 user-invocable skill commands。
- [x] 1.4 同步对应 current spec 到 `openspec/specs/<capability>/spec.md`。
- [x] 1.5 明确本 change 依赖已归档的 slash command framework，不包含 skill authoring、marketplace 或 semantic search。
- [x] 1.6 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，逐项确认 skill roots 默认值、注入位置、匹配算法、trace 可观测性、错误诊断和测试策略。
- [x] 1.7 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.8 维护 `## Reference Implementation Research`；开发前补充更具体的参考实现文件和设计影响。
- [x] 1.9 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。

## 2. 测试

- [x] 2.1 新增 skill runtime 测试，覆盖多 root 加载、无效 skill 诊断和重复名称处理。
- [x] 2.2 新增 always skill 注入测试。
- [x] 2.3 新增 matched skill 当前 run 注入测试。
- [x] 2.4 新增配置解析测试，覆盖 `skills.roots` 默认值、路径展开和非法配置 fail fast。
- [x] 2.5 新增 CLI `/skills` 和 `/skills reload` 测试。
- [x] 2.6 新增 trace/debug 或运行事件测试，覆盖 loaded/matched skill 可观测性。
- [x] 2.7 新增 `ActivateSkill` 工具测试，覆盖 LLM 主动激活、未知 skill 和重复激活。
- [x] 2.8 新增 user-invocable slash skill 测试，覆盖 `/skill-name args` prompt 组装和 Agent run 启动。

## 3. 实现

- [x] 3.1 扩展配置模型，增加 skill roots。
- [x] 3.2 增强 SkillLoader 或新增 skill runtime/cache，记录来源和加载诊断。
- [x] 3.3 将现有 `skills/*.md` 样例迁移到目录式 `skills/<name>/SKILL.md`。
- [x] 3.4 将短 skill index 注入每个 run 上下文。
- [x] 3.5 将 always 和 matched skill 注入当前 run 上下文，并避免永久污染 memory。
- [x] 3.6 实现 `ActivateSkill` runtime tool。
- [x] 3.7 接入 slash command registry，实现 `/skills`、`/skills reload` 和 user-invocable skill commands。
- [x] 3.8 更新必要文档。

## 4. 验证

- [x] 4.1 运行 skills 相关测试。
- [x] 4.2 运行配置和 CLI 相关测试。
- [x] 4.3 运行全量测试。
- [x] 4.4 运行 OpenSpec strict validate。
- [x] 4.5 运行项目 OpenSpec artifact checker。
- [x] 4.6 如实现触碰 AgentLoop 核心运行路径，跑通至少一个 benchmark smoke。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-integrate-skill-runtime/`。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [x] 5.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
