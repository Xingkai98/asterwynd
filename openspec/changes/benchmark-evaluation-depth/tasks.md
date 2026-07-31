## 1. 规格与设计定稿

- [ ] 1.1 确认 proposal 的 Change Type、Impact Analysis、Reference Implementation Research 完整（含本地参考仓库不可用事实与替代依据）。
- [ ] 1.2 开发前使用 `grill-with-docs` 审视 `design.md`，逐项确认分层字段、bootstrap/Pass@k 统计、judge 判定、失败归因、结果页渲染、CLI `--repeat`、依赖策略和测试策略；不得把 agent 推荐答案当作用户确认。
- [ ] 1.3 在 `design.md` 的 `## Pre-Implementation Review` 记录 grill 结论：已解决问题、备选方案、否决方案、最终确认、剩余风险。
- [ ] 1.4 确认 spec delta（全部作为 `benchmark` 追加）与 proposal 的 Modified Capabilities 一致，且为向后兼容扩展。

## 2. 任务分层与 schema

- [ ] 2.1 在 `benchmarks/task_schema.py` 增加可选能力分层字段（如 `evaluation_layer`，取值 `execution`/`tool-usage`/`context-planning`/`multi-step-solving`），缺省归入默认层。
- [ ] 2.2 为分层字段补充解析与默认层 fallback 的单元测试。
- [ ] 2.3 盘点 `benchmarks/tasks/` 下现有活动任务，按能力分层打标（含 swebench 任务归类），形成任务盘点清单（记录在 change 文档或结果页的按层视图）。

## 3. 重复运行聚合

- [ ] 3.1 在 benchmark CLI 增加 `--repeat N` 参数（缺省 1 保持既有行为），并传入 runner。
- [ ] 3.2 在 runner/聚合层支持对同一任务集合执行 N 轮，每轮保留独立 result 记录。
- [ ] 3.3 增加聚合数据模型（按任务、按层的分布结果），扩展 `benchmarks/models.py`（新增字段，保留既有字段向后兼容）。
- [ ] 3.4 为重复运行与聚合补单元测试与 benchmark 层级测试。

## 4. 统计指标

- [ ] 4.1 实现均值/标准差与 95% 置信区间（bootstrap 百分位法，固定随机种子保证可复现）。
- [ ] 4.2 实现 `Pass@k` 计算（通过类任务；开放式任务跳过改用 judge）。
- [ ] 4.3 为统计计算补单元测试（含固定种子可复现断言）。
- [ ] 4.4 确认统计依赖策略（是否新增 numpy/scipy；如新增需在 design 记录并在 tasks/Impact 回写）。

## 5. 开放式任务 judge 与人工回流

- [ ] 5.1 在 task schema 标记开放式任务（无 hidden test）的方式。
- [ ] 5.2 实现 judge 判定流程（对开放式任务输出给出一致判分），判分结果写入 result。
- [ ] 5.3 记录 `human_reviewed` 标记与判定理由，支持人工回流审计。
- [ ] 5.4 为 judge 判定与回流标记补单元测试。

## 6. 失败归因

- [ ] 6.1 按失败 `reason` 分类统计各层失败模式占比。
- [ ] 6.2 每个失败模式输出可回查的任务 id + 运行轮次 + trace 路径（为 git bisect 定位提供入口）。
- [ ] 6.3 为失败归因补单元测试。

## 7. 量化结果页渲染

- [ ] 7.1 实现结果页渲染模块（markdown/HTML），输入一次带重复运行+统计的 run 聚合，复用 `compare.py` 的延迟/成本口径。
- [ ] 7.2 结果页包含 Pass@k、均值/标准差、置信区间、延迟分布、token 成本，并按能力层级组织。
- [ ] 7.3 为结果页渲染补单元测试（golden 片段）。

## 8. 同步与验证

- [ ] 8.1 将本 change 的 `benchmark` delta（ADDED requirements）同步到当前规格 `openspec/specs/benchmark/spec.md`。
- [ ] 8.2 维护 Impact Analysis，清理开发中发现的 `unknown`/`TBD`/`待确认`。
- [ ] 8.3 维护 Reference Implementation Research 最终结论；如调研结论变化先回写 change 文档。
- [ ] 8.4 运行相关单元/集成测试与全量测试。
- [ ] 8.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 与 `uv run python scripts/check_openspec_artifacts.py`。
- [ ] 8.6 跑通至少一个 benchmark smoke（`--repeat 3` 一组小任务），确认重复运行+聚合+结果页全链路。

## 9. PR 收尾

- [ ] 9.1 将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-<change-id>/`。
- [ ] 9.2 从 `docs/openspec-change-backlog.md` 移除/更新本 change 并同步批次。
- [ ] 9.3 更新受影响的文档入口（`docs/benchmark-plan.md`、README 同步 README_EN）并跑关键字扫描。
- [ ] 9.4 确认 Impact Analysis 与 Reference Implementation Research 无残留未解释项，跑最终 validate + artifact checker。
