# Proposal: Verified 40 fixture 生成管线（evaluation-verified-subset）

关联跟踪 issue：[#163](https://github.com/Xingkai98/asterwynd/issues/163)。系列 follow-up：[#156](https://github.com/Xingkai98/asterwynd/issues/156)（C1 后续项 1）。

## Change Type

- primary: feature
- secondary: []

## Why

C1 `evaluation-task-spec`（#154）交付了 Verified 子集的**选择逻辑**（`benchmarks/swebench_subset.py::build_subset`）和**落盘模板**（`benchmarks/swebench_convert.py::generate_tasks`），但**生成管线未接通**——CLI 无 `build_subset` 入口，40 条新 fixture 从未实际生成（当前仅 10 条既有 `<15 min fix` 且 requests 6/10）。follow-up #156 记为 C3 前置项。

本机网络实测（2026-08-18）：
- `huggingface.co` 直连不可达（超时）——C1 当时认为"数据环境不可达"。
- **`hf-mirror.com` 可达**（HTTP 200），`princeton-nlp/SWE-bench_Verified` 数据集完整存在（`data/` + README）。
- `HF_ENDPOINT=https://hf-mirror.com` 可让 `datasets` 库走镜像。

即"数据可达环境"其实就在本机（加一个环境变量），无需换机器。

## What Changes

- **接通生成管线**：`benchmarks/swebench_subset.py` CLI 新增 `build-subset` 命令——加载 Verified 数据集（`HF_ENDPOINT` 镜像）→ 调 `build_subset`（过滤 KNOWN_BAD/重 repo/空 test_patch + 按 OQ-V1 配比 requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8）→ 调 `swebench_convert.generate_tasks` 落 `benchmarks/tasks/swebench-*/task.json` + test.patch + gold.patch。
- **本机实际生成（2026-08-18）**：`HF_ENDPOINT=https://hf-mirror.com uv run python benchmarks/swebench_subset.py build-subset` 跑通，验证镜像通路 + 字段兼容。按 OQ-V1 配比实际补 **28 条新**（requests+2/flask+0/pytest+8/sympy+8/seaborn+2/pylint+8），加既有 10 条共 **38 条**——flask 全数据集仅 1 条、seaborn 仅 2 条（均被既有占用），轻量池上限即 28（数字按实际，OQ-V6）。
- **元数据校验**：`validate_fixtures_dir` 全过（38 条；instance_id/dataset_name/dataset_split/track=verified/scenario=bug-fix/difficulty 归一化/task_family=swebench/execution_environment）。
- **L3 金补丁自检**：抽样每 repo ≥1——requests-2931/flask-5014/pytest-5631 三条 PASS（gitee 可达 + PyPI 装依赖）；sympy/seaborn/pylint 未自检（github 不可达，clone 超时记录）；坏实例只记录不删除（OQ-V2③）。
- **manifest 登记**：`benchmarks/tasks/manifest.json` 登记 verified 摘要段（count=38/by_repo/by_difficulty，不占 coverage 矩阵；与 B 轨扩展共用此文件，错开合入）。
- **disclosure**：结果页新增「Verified 子集披露」段（OQ-V6②）。
- **follow-up 闭环**：归档时在 #156 标注 Verified 38 完成。

## Capabilities

### New Capabilities

无。全部为既有 `benchmark` 能力域的 C1 未完交付补全。

### Modified Capabilities

- `benchmark`: 任务集补齐 Verified 子集（10→50 条）；生成管线（subset 选择 → convert 落盘）接通；无 spec delta（C1 已落子集接入 Requirement，本 change 是实现）。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规功能补全（C1 已调研 Verified 子集可行性 R2 #146 与选择口径 G2 #149）；本 change 是既有工具链的接线与执行，无新方法论。
- research questions: 无（light）。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。本机网络实测 hf-mirror 可达（2026-08-18），数据集完整；`swebench_subset.py` 的 `build_subset` 与 `swebench_convert.py` 的 `load_verified`/`generate_tasks` 均已实现、接口匹配（subset 输出 instance 选择，convert 消费 instance_id 落盘）。**最终闭环（2026-08-18）**：`HF_ENDPOINT=https://hf-mirror.com` 实际跑通 build-subset，生成 28 新/38 总 fixture，validate 全过，difficulty 列真实值（`<15 min fix`/`15 min - 1 hour`/`1-4 hours`/`>4 hours`）已收录映射。
- design impact: 管线接线方案见 design.md D1–D5；实测发现轻量池上限（flask 1/seaborn 2）与 github 不可达（L3 抽样 3 PASS/3 未自检），已回写 design 实测结果。

## Impact Analysis

- **能力域**: `benchmark`（Verified 子集补齐）。
- **代码**: `benchmarks/swebench_subset.py`（`build-subset`/`validate-dir`/`gold-check` 子命令 + gold_check external_repo + manifest 摘要）、`benchmarks/swebench_convert.py`（difficulty 归一化 + track/scenario/version + gitee 优先）、`benchmarks/disclosure.py`（Verified 披露段）、`benchmarks/tasks/`（28 条新 swebench-* fixture + manifest verified 摘要登记）。
- **测试**: `validate_fixtures_dir` 全过（38 条）；`gold_check` 抽样自检 3 PASS；新增管线单测（mock 数据集 → build_subset 选择 → generate_tasks 落盘字段校验）；既有 benchmark 测试不回归。
- **文档**: `docs/openspec-change-backlog.md`（#156 后续项 1 状态）、`benchmarks/tasks/README.md`（Verified 计数 10→38）。
- **基准**: 新增 28 条 fixture 是纯增量；既有 10 条不动；任务 schema/manifest 结构不变（verified 为新增顶层键，既有消费方安全）。
- **流程（process）**: Verified 子集生成管线落地，后续子集调整走同一 CLI。
