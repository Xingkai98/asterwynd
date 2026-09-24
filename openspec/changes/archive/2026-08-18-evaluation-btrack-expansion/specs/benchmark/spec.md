# benchmark 规格（delta）

本文件是 `evaluation-btrack-expansion` change 对既有 `benchmark` capability 的增补。C1 已落「任务集由三来源组成」Requirement（B 轨 12–16、能力覆盖矩阵、每场景 ≥1–2）；本 change 实现该 Requirement 的 **B 轨任务补齐**（context-planning 3–5 等能力空白）。

## ADDED Requirements

### Requirement: B 轨任务补齐能力空白

benchmark 任务集 SHALL 通过 B 轨任务补齐能力覆盖空白：context-planning、long-term-memory、long-context 等能力列 SHALL 有 B 轨任务覆盖（不依赖 A 轨兜底）；每任务 SHALL 测试先行（确定性 test_command 判别力 + 红绿可复现）。B 轨任务 SHALL 设计为不给目标文件路径、迫使 agent 先 repo-map 再规划。

#### Scenario: context-planning 有 B 轨覆盖

- **GIVEN** 能力覆盖矩阵中 context-planning 列仅由 A 轨覆盖
- **WHEN** B 轨任务补齐
- **THEN** context-planning 列 SHALL 有 B 轨任务登记
- **AND** 每任务 SHALL 通过「base 红 + gold 绿」判别力验证

#### Scenario: 每场景至少一个 B 轨任务

- **GIVEN** 任务集包含 bug-fix/feature-dev/refactor/debug/integration 五场景
- **WHEN** 校验场景覆盖
- **THEN** 每场景 SHALL 至少有一个任务（A 轨或 B 轨）

### Requirement: 面试叙事任务数同步

benchmark 任务数变化（如 B 轨扩展）SHALL 同步到引用该数字的面试文档（FINAL-master-script/walkthrough/resume/README），保持「现状口径与当前实现一致」。

#### Scenario: 任务数变化同步

- **GIVEN** B 轨扩展合入后任务数变化
- **WHEN** 检查面试文档
- **THEN** 引用任务数的文档 SHALL 更新为当前实测值
- **AND** 升级方向标注（如「当前已落 N」）SHALL 同步
