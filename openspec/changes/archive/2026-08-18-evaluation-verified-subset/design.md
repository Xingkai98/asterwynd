# Design: evaluation-verified-subset

## Context

C1 已交付：`benchmarks/swebench_subset.py::build_subset(instances, targets, known_bad, heavy_repos)` 纯函数（过滤 KNOWN_BAD/重 repo/空 test_patch + 按 repo 配比选实例，`SUBSET_TARGETS` = requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8）、`benchmarks/swebench_convert.py::load_verified()`（`datasets.load_dataset("princeton-nlp/SWE-bench_Verified", split="test")`）+ `generate_tasks(instance_ids, output_base)`（写 task.json/test.patch/gold.patch，`dataset_name=princeton-nlp/SWE-bench_Verified`/`dataset_split=test`）。

**缺口**：subset 的 `build_subset` 无 CLI 入口；convert 的 `generate_tasks` 只被 `--all-requests`（硬编码 6 条 requests）调；两者从未串成"选 40 → 落盘"。

本机网络实测：`huggingface.co` 超时、**`hf-mirror.com` 200 可达**、`HF_ENDPOINT=https://hf-mirror.com` 走镜像。SWE-bench_Verified 数据集在 hf-mirror 完整存在。

## Goals / Non-Goals

**Goals:**

- `build-subset` CLI 接通：加载 → 按配比选实例 → 落 fixture。
- 本机 hf-mirror 实际生成 Verified fixture，`validate_fixtures_dir` 全过。
- L3 `gold_check` 对生成 fixture 抽样自检（每 repo ≥1 跑通，其余记录未自检）。
- manifest 登记 verified 摘要条目 + disclosure 披露。
- #156 后续项 1 闭环。

**实测结果（2026-08-18，hf-mirror）**：Verified 轻量池有上限——flask 全数据集仅 1 条、seaborn 仅 2 条（均被既有 fixture 占用），requests 8 条中 6 条既有。故按 OQ-V1 配比实际补 28 条新（requests+2/flask+0/pytest+8/sympy+8/seaborn+2/pylint+8），总计 **38** 条（10 既有 + 28 新），而非目标 40/50。difficulty 列真实值为 `<15 min fix`/`15 min - 1 hour`/`1-4 hours`/`>4 hours`，映射后分布 17 easy/16 medium/5 hard。L3 抽样自检：requests/flask/pytest 3 条 PASS（gitee 可达 + PyPI 装依赖），sympy/seaborn/pylint 未自检（github 不可达，clone 超时记录）。

**Non-Goals:**

- **不重写既有选择逻辑**（`build_subset`/`SUBSET_TARGETS` 复用 C1 交付）。
- **不改 L2 Docker 验证路径**（归既有 SwebenchAdapter；本 change 只生成 fixture + L3 自检）。
- **不跑真实评测**（烧钱，用户定只定协议）。
- **不扩 B 轨**（归并行的 evaluation-btrack-expansion）。
- **不改面试叙事**（C4 已合入；任务数变化由 B 轨扩展 change 校准）。

## Decisions

### Decision D1: CLI 形态——`build-subset` 子命令

**方案**：`benchmarks/swebench_subset.py` 的 argparse 新增 `build-subset` 子命令：
```
uv run python benchmarks/swebench_subset.py build-subset \
  --output benchmarks/tasks --targets requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8
```
流程：`swebench_convert.load_verified()` → `build_subset(instances, targets)` → 对 `plan.selected` 的 instance_id 调 `swebench_convert.generate_tasks()` 落盘。`HF_ENDPOINT` 环境变量由 `datasets` 库自动读取（无需代码处理镜像逻辑）。

**备选**：改 `swebench_convert.py` 的 main 支持配比。被拒：选择逻辑在 subset、落盘在 convert，subnet 侧加 CLI 更贴合职责边界（convert 保持"给定 instance_id 落盘"）。

**理由**：职责单一；`--targets` 显式传配比（默认用 `SUBSET_TARGETS`），可复现。

### Decision D2: 数据集加载走镜像

**方案**：不硬编码 `HF_ENDPOINT`；文档 + smoke 命令注明 `HF_ENDPOINT=https://hf-mirror.com`。`load_verified()` 用 `datasets.load_dataset` 天然读该环境变量。

**理由**：本机直连不可达、镜像可达（实测）；环境变量方案不污染代码、对其它环境（有直连的机器）同样适用。

### Decision D3: 生成即校验——validate + gold_check 内置进管线

**方案**：`build-subset` 落盘后自动跑 `validate_fixtures_dir(output)`，任一 invalid 打印清单 + exit 1；提供 `--skip-gold-check` 开关（默认跑 L3 自检，但 gold_check 对每实例要 clone + 装依赖，耗时长，允许跳过时在输出注明"未自检"）。

**备选**：只落盘不校验。被拒：G2 Q3 明确 L3 金补丁自检剔除 flaky/坏实例，生成即校验保证 fixture 质量。

**理由**：校验内建于管线避免"生成了一堆坏 fixture"；`--skip-gold-check` 提供灵活度。

### Decision D4: manifest 登记 verified 条目

**方案**：`benchmarks/tasks/manifest.json` 新增 `verified` 段或扩展现有结构，登记 50 条（10 既有 + 40 新增）的 track=verified 元数据（不占 coverage 矩阵——覆盖矩阵只统计本地 A+B，G2 口径）。

**理由**：C3 disclosure 的污染披露/反作弊段读 manifest；verified 条目登记使结果页能展示子集规模与偏置披露。

### Decision D5: 与 B 轨扩展并行——manifest 错开合入

**方案**：本 change 只改 manifest 的 verified 段；`evaluation-btrack-expansion` 改 coverage 矩阵段。错开合入（先合者先进，后合者 rebase 追加），避免同段冲突。

**理由**：G4 系列并行模式；两 change 各改 manifest 不同段，冲突面最小。

## Reference Implementation Research

- status: enabled
- research_tier: light
- reason: 常规补全（C1 已调研 R2 #146 与 G2 #149）；本机网络实测补充 hf-mirror 可达事实。
- findings: 本地 `.dev/reference-repos.txt` 不存在（已记录）。hf-mirror 实测 200 且数据集完整（2026-08-18）；`build_subset`/`load_verified`/`generate_tasks` 接口匹配，接线即可。实现期补充：difficulty 列真实 4 值、flask/seaborn 池上限、github 不可达（L3 抽样受限）——见「实测结果」。
- design impact: D1–D5 全部来自 C1 交付物 + 本机实测；无新增调研依赖。

## Risks / Trade-offs

- **[hf-mirror 数据集字段与直连不一致] → `load_verified` 加载后先打印字段名/dataset_size 再 build，字段缺失早暴露；gold_check 兜底。**
- **[轻量池上限不足 40] → 实测 flask 1 条/seaborn 2 条/requests 8 条（6 既有），按配比实际补 28 新、总 38；接受略少于 40（OQ-V6 数字按实际，manifest/disclosure 如实登记）。**
- **[40 条中含 KNOWN_BAD/坏实例] → build_subset 已过滤 KNOWN_BAD；gold_check 自检剔除 flaky；宁可略少于 40 也不混入坏实例（G2 口径）。**
- **[gold_check 耗时长（clone+装依赖×40）] → 默认跑但允许 `--skip-gold-check`；结果页标注自检覆盖。**
- **[manifest 与 B 轨并行冲突] → 只改 verified 段 + 错开合入（D5）。**
- **[网络不稳定导致生成中断] → CLI 支持 `--resume`（跳过已存在的 instance_id）或重复执行幂等（generate_tasks 覆盖写）。**

## Pre-Implementation Review

独立零记忆 grill（run `grill-evaluation-verified-subset-2026-08-18`，2026-08-18，详见 `reviews/grill-design.md`）已对 D1–D5 逐项追问，结论如下：

**已确认**：
- D2 镜像加载方向确认——`load_verified()` 即 `datasets.load_dataset`，天然读 `HF_ENDPOINT` 环境变量，无代码污染。
- D1 职责边界（选择在 subset、落盘在 convert）方向确认——接口天然匹配；CLI 细节缺口见 Open Questions。
- D4/D5 manifest 只改 verified 段 + 与 B 轨错开合入方向确认——manifest 既有消费方（`task_set.py`/`disclosure.py`）只读固定键，新增顶层键安全。
- 落盘后自动 `validate_fixtures_dir`、invalid exit 1 内建方向确认。

**必须修改（阻塞项，Open Questions 定稿后落实）**：
- `generate_tasks` 落盘缺 `track`/`scenario` 且 `difficulty` 未归一化 → 直接跑管线必 fail `validate_fixture` 3 类错误（D1–D5 未含 convert 侧改动）。
- `gold_check` 对 `external_repo` 直接 SystemExit，D3「默认跑 L3 自检」在当前实现下不可行，需定自检机制。
- 选择池若不排除既有 10 条 instance_id，覆盖写会把既有 fixture 改回非法字段且新生成 <40、总数 46。

**Open Questions（停轮等用户确认，逐条配例子见 `reviews/grill-design.md`）**：
OQ-V1 落盘字段修复位置；OQ-V2 L3 自检机制/默认行为/坏实例剔除；OQ-V3 既有 10 条重叠与 `--resume` 语义；OQ-V4 KNOWN_BAD 来源；OQ-V5 CLI 结构与 `--targets` 解析；OQ-V6 manifest verified 段 schema 与消费方。

## Testing Strategy

- 单元测试（mock 数据集，不依赖网络）：build-subset 选择逻辑（配比/过滤/KNOWN_BAD）、generate_tasks 落盘字段校验、validate_fixtures_dir。
- 集成测试：真实 hf-mirror 拉取（标记 @integration，CI 可能跳过）+ 本机 smoke 实际生成。
- L3 gold_check 至少对 1-2 条生成 fixture 跑通（验证克隆/装依赖/金补丁绿）。
- 既有 benchmark 测试不回归。
- 每个 bug fix 新增回归测试；涉及 benchmark 路径必须覆盖 benchmark 层级测试。
