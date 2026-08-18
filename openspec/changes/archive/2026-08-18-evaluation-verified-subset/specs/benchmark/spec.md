# benchmark 规格（delta）

本文件是 `evaluation-verified-subset` change 对既有 `benchmark` capability 的增补。C1 已落「外部测试集精选子集接入」Requirement（过滤 KNOWN_BAD/重实例、L1/L2/L3 分级验证、污染披露）；本 change 实现该 Requirement 的**生成管线**（选子集 → 落 fixture）。

## ADDED Requirements

### Requirement: 外部测试集子集生成管线

benchmark SHALL 提供外部测试集（如 SWE-bench Verified）精选子集的生成管线：从数据集加载实例 → 按配比过滤（KNOWN_BAD/重 repo/空 test_patch）选择 → 落盘为任务 fixture（task.json/test.patch/gold.patch）→ 元数据校验。生成管线 SHALL 支持通过镜像端点（如 `HF_ENDPOINT`）访问数据集，并支持 L3 金补丁自检剔除 flaky/坏实例。

#### Scenario: 生成子集 fixture

- **GIVEN** 数据集可访问（含镜像端点）
- **WHEN** 运行生成管线
- **THEN** 系统 SHALL 按配比选择实例并落盘 fixture
- **AND** fixture 元数据 SHALL 通过校验（instance_id/dataset_name/dataset_split/track/scenario/difficulty/task_family/execution_environment）

#### Scenario: 镜像端点访问数据集

- **GIVEN** 直连数据集不可达但镜像端点可达
- **WHEN** 运行生成管线（设置 `HF_ENDPOINT`）
- **THEN** 系统 SHALL 经镜像端点加载数据集
- **AND** 生成的 fixture 字段与直连一致

#### Scenario: 金补丁自检剔除坏实例

- **GIVEN** 生成的 fixture 中某实例金补丁无法复现
- **WHEN** 运行 L3 自检
- **THEN** 系统 SHALL 标记/剔除该实例
- **AND** 结果页/文档 SHALL 记录自检覆盖与剔除情况
