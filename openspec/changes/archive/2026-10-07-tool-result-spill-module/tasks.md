## 1. 规格

- [x] 1.1 更新受影响 capability 的 spec delta：`openspec/changes/tool-result-spill-module/specs/context-engineering/spec.md`（ADDED Requirement「工具结果有界化的单一内聚宿主与单一判据来源」）。
- [x] 1.2 明确本 change 的范围（纯重构：内聚 spill 生命周期）、非目标（不改可观测行为 / 不改 policy 纯函数 / 不收账本路径）和验收标准（R0–R4）。
- [x] 1.3 开发前使用 `grilling` 或等价设计追问审视 `design.md`，逐项确认 OQ1–OQ5、依赖、风险（尤其 D2 counter 缝）、测试策略和文档影响都有最终方案；不得把 agent 自己的推荐答案当作用户确认。
- [x] 1.4 维护 `## Impact Analysis`，列出影响、不影响和待确认影响面；开发前把待确认项清理为明确结论或阻塞项。
- [x] 1.5 维护 `## Reference Implementation Research`；本 change `research_tier: light` + `status: enabled`，记录 findings 与 design impact；如调研结论变化，先回写 change 文档。
- [x] 1.6 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。
- [x] 1.7 grill 后、停轮前跑设计阶段审阅闭环，产出 `openspec/changes/tool-result-spill-module/reviews/grill-adversarial.md`；能由代码判定的 Open Question 用代码给出带证据（`文件:行号`）的答案并移出停轮队列。

## 2. 测试

- [x] 2.1 按 TDD 先新增 `tests/agent/memory/test_tool_result_spiller.py`：`mark` 后剪陈旧 / 未标记不剪、`reset` 预置 `-1`、`spill` 幂等、`PruneStats` 数值、**counter 注入（monkeypatch 后阈值随之变化——覆盖 D2 头号风险）**。
- [x] 2.2 覆盖跨模块行为：`loop` → spiller → policy 的完整剪枝链（复用既有 `tests/agent/test_tool_result_lifecycle_loop.py` 场景，确认真实路径不变）。
- [x] 2.3 覆盖入口层：跑 `scripts/e0_tool_result_lifecycle.py` A/B 对照冒烟，确认 monkeypatch 目标未破、常驻字符量级不变。
- [x] 2.4 覆盖负向路径与回归：未标记不剪、无 ref 不谎称、幂等、resume 历史被剪、`_tokens` 重置（既有测试保持全绿即覆盖）。

## 3. 实现

- [x] 3.1 新增 `agent/memory/tool_result_spiller.py`：`ToolResultSpiller`（`mark` / `reset` / `spill`，构造期注入 `max_tokens` / `recent_window` / `counter`）+ `PruneStats`。
- [x] 3.2 把 `MemoryManager.prune_tool_results` 循环主体迁入 `spiller.spill`；**删除 `prune_tool_results`**（Q1 定案，不留薄委托）；`MemoryManager` 构造并持有 spiller；`PruneStats` 自 `manager.py` 迁出（无需重导出，e0 import 一并改 spiller）；`is_oversized_result` 保留。
- [x] 3.3 接入 `agent/loop.py`：两处迭代标记写入改经 `self.memory.tool_result_spiller.mark`、`_reset_tool_result_iterations` 改经 `self.memory.tool_result_spiller.reset`、`_spill_and_prune` 改调 `self.memory.tool_result_spiller.spill`；同步改 e0 monkeypatch 目标 `loop.memory.tool_result_spiller.spill`；**事件/trace 发射点不动**。
- [x] 3.4 更新文档：`CONTEXT.md`（新词条）、`docs/architecture.md`（`MemoryManager` 职责收敛 + 新增 `ToolResultSpiller` 行）；关键词扫描 `README.md` / `README_EN.md`（预计无影响）。
- [x] 3.5 如果实现中发现新影响面，先回写 Impact Analysis 和本任务清单，再继续无关实现。
- [x] 3.6 如果实现中发现参考实现调研结论需要修正，先回写 Reference Implementation Research 和本任务清单。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试：`uv run pytest tests/agent/memory tests/agent/test_tool_result_lifecycle_loop.py tests/agent/test_trace_recorder_bounded.py -q`。
- [x] 4.2 运行全量测试：`uv run pytest -q`。
- [x] 4.3 运行 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`。
- [x] 4.4 运行项目 OpenSpec artifact checker：`PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.5 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.6 跑通至少一个 benchmark smoke（本 change 触及 `agent/loop.py` 核心路径）。
- [x] 4.7 确认纯重构等价：既有 `tests/agent/memory/test_tool_result_lifecycle.py` 与 `tests/agent/test_tool_result_lifecycle_loop.py` **未作语义修改**即全绿（R0）。

## 5. 同步 spec

- [x] 5.1 归档前把 delta spec 合入 current spec `openspec/specs/context-engineering/spec.md`（受保护路径，需结构化解释事件）。

## 6. PR 收尾

- [x] 6.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-tool-result-spill-module/`。
- [x] 6.2 从 `docs/openspec-change-backlog.md` 移除或更新本 change，并同步并行开发批次。
- [x] 6.3 确认 Impact Analysis 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 6.4 确认 Reference Implementation Research 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [x] 6.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py`。
- [ ] 6.6 (post-merge) PR 合入后给关联 issue #300 添加完成说明 comment 并关闭。
