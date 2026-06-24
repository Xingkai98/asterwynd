## 1. 规格

- [x] 1.1 修改 benchmark 规格，定义 Docker-based SWE-bench 任务执行路径。
- [x] 1.2 修改 benchmark 规格，定义 Docker preflight 与 `unsupported` 语义。
- [x] 1.3 开发前使用 `grill-with-docs` 或等价设计追问审视 `design.md`，确认 task metadata、preflight、status 模型、summary 统计和文档边界。
- [x] 1.4 实现后同步 current spec 到 `openspec/specs/benchmark/spec.md`。

## 2. 测试

- [x] 2.1 新增 Docker preflight 可用 / 不可用测试。
- [x] 2.2 新增 Docker-based 任务在 daemon 不可用时标记 `unsupported` 的测试。
- [x] 2.3 新增 `status + reason` 结果模型、summary renderer 和 CLI benchmark 对 `unsupported` 状态的测试。
- [x] 2.4 新增混合任务集测试，确认 `myagent-*` 本地任务不受影响。

## 3. 实现

- [x] 3.1 增加 Docker-based SWE-bench 任务的执行分流。
- [x] 3.1.1 为 task schema 增加 `task_family`、`execution_environment`、`instance_id`、`dataset_name`、`dataset_split`，并将现有 `swebench-*` 任务迁移为 `docker`。
- [x] 3.2 移除或绕过外部任务上的本地 venv 依赖安装路径，不再把它作为 Docker 不可用时的 fallback。
- [x] 3.3 增加 run 级 Docker preflight 缓存与 `unsupported` artifact 写入。
- [x] 3.3.1 将 benchmark `failure_category` 替换为统一 `reason` 字段。
- [x] 3.4 补充当前容器开发环境的文档说明和备用脚本。

## 4. 验证

- [x] 4.1 运行 benchmark 相关单元/集成测试。
- [x] 4.2 运行全量测试。
- [x] 4.3 如果环境支持 Docker，跑通至少一个 `swebench-*` smoke；否则记录受限原因并以测试覆盖替代。
- [x] 4.4 运行 OpenSpec strict validate。
- [x] 4.5 运行 `uv run python scripts/check_openspec_artifacts.py`。
