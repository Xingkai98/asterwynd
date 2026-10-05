# Tasks: README 叙事重做（readme-narrative-refresh）

> docs-only change。无 spec delta、无业务代码改动。数字口径以 master `8a255b0` 实测为准。

## 1. 事实核查（writes 前）

- [x] 1.1 实测锚定数字：`agent/` LOC / 文件数、测试文件与测试函数数、内置工具数、上下文源数、Hook 切面数、编排模式数、workflow 节点类型数、benchmark 任务分轨数。
- [x] 1.2 核对 workflow 能力面：DSL 工具名（Declare/Start/Run/Get/Cancel/ReadResult/DryRun/Asset 系列）、4 节点类型、汇合语义、四维预算、四维成本归因、图可视化、DryRun。
- [x] 1.3 核对安全面：三层（WorkspacePolicy / CommandGuard / Sandbox）、权限模型、降级原则。

## 2. 绘图（Excalidraw → SVG）

- [x] 2.1 重画系统架构图 `architecture`（覆盖编排层 + 可观测层）。
- [x] 2.2 画特色图 `workflow-orchestration`（声明 DSL / 调度 DAG / 预算账本可见 / 底部能力带）。
- [x] 2.3 画特色图 `feature-context`（9 源分层注入 + 前缀缓存 + L1/L2 压缩）。
- [x] 2.4 画特色图 `feature-memory`（写时去重 + git 可逆 + 衰减归档）。
- [x] 2.5 画特色图 `feature-safety`（三层纵深 + 权限审批链 + 降级原则）。
- [x] 2.6 画特色图 `feature-tools`（BM25+embedding Top-K + 稳定核心层 + 质量软降级）。
- [x] 2.7 画特色图 `feature-observability`（trace 流 + 四维成本 + 错误分类 + benchmark 闭环）。
- [x] 2.8 每张图导出 `.svg`（内嵌 Virgil 字体、无 foreignObject、无外链），`.excalidraw` 源一并入库 `docs/assets/readme/`。
- [x] 2.9 逐张目视验收：无自环箭头、无文字溢出/重叠、对比度达标。

## 3. README 重写

- [x] 3.1 `README.md`：Hero + 徽章 + 电梯 pitch + 架构图。
- [x] 3.2 `README.md`：特色区 6 张卡（每张配图）。
- [x] 3.3 `README.md`：自举工程闭环 banner。
- [x] 3.4 `README.md`：快速开始精简 + 长内容 `<details>` 折叠（内置工具表/项目结构/AutoCompact/Sub-Session/扩展指南/Web UI/环境变量/评测流程）。
- [x] 3.5 `README.md`：架构 / Benchmark / 文档地图 / 技术栈 / 致谢。
- [x] 3.6 `README_EN.md`：与中文同步的英文全文（章节、命令、图片、事实口径一致）。

## 4. 文档影响

- [x] 4.1 `docs/architecture.md`：补多 Agent 编排与 workflow 运行态可视化段落。
- [x] 4.2 `docs/openspec-change-backlog.md`：批次条目（受保护路径，走 workflow-events 事件）。

## 5. 验证

- [x] 5.1 README 图片路径全部可达（`docs/assets/readme/*.svg` 存在）。
- [x] 5.2 README.md / README_EN.md 章节、命令、事实数字一致性核对。
- [x] 5.3 独立零记忆 subagent 对抗式事实校对：逐条断言 vs 代码，找出任何与代码不符的表述（落 `reviews/fact-check.md`，逐条修复）。
- [x] 5.4 benchmark smoke：跑 CI 同款 `benchmark-gate`（`gate-smoke` + `--baseline`）确认本 change 未影响 benchmark 基础设施；并核实无任何测试断言 README 内容、`benchmark-gate` 不读 README（fake runner 默认不编辑文件）。
- [x] 5.5 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过。
- [x] 5.6 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 通过。
- [x] 5.7 全量 `uv run pytest -q` 相对 baseline 无新增失败。

## 6. 收尾

- [x] 6.1 归档 change 到 `openspec/changes/archive/2026-10-06-readme-narrative-refresh/`。
- [x] 6.2 清理 backlog 中本 change 的 active 条目（受保护路径，走事件）。
- [x] 6.3 发起 PR，关联 issue #296，写明验证结果。
- [ ] 6.4 (post-merge) PR 合入后给 issue #296 添加完成说明 comment 并关闭。
