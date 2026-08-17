# Review: evaluation-metrics 实现审阅（Round 1 + Round 2）

## Reviewer
- Round 1 run id: review-evaluation-metrics-20260817
- Round 2 run id: review-evaluation-metrics-20260817-round2
- 时间: 2026-08-17
- 审阅范围: 4ed4b4f..HEAD（grill 确认 1 + 实现 9 + 收尾 1 + review-loop Round 1 修复 1）

## Verdict
**PASS**（Round 1 CHANGES_REQUESTED → 修复 → Round 2 复核 PASS）

## Round 1 审阅（CHANGES_REQUESTED）

数据层完成度高、测试扎实、门禁全绿；发现 1 个可实证的统计正确性缺陷（paired bootstrap 实际未配对）与若干规格/渲染口径缺口。任务逐项验证 2.1-11.6 全部 [x] 名实相符（2 项带 △：4.4 cache 采集链仅非流式全通、9.2 swebench 版本语义偏差）。

### Round 1 Issues
- **[HIGH/正确性] paired bootstrap 实际未配对**（statistics.py 独立取两个任务索引）；实证：A/B 相同数据 CI=[-0.2167, 0.2333] 而非 [0,0]。
- **[MEDIUM/Spec 对齐] 任务级 Pass^k 缺 min_valid_rounds=3 门槛**（report.py），与 Q3 及层口径矛盾。
- **[MEDIUM/正确性] 流式路径丢失 cache/input token**（anthropic_llm.py 只解析 output_tokens），默认流式配置下 Q5 采集链不成立。
- **[MEDIUM/Spec 对齐] 未知模型「估算并警告」只实现估算**（无警告日志）。
- **[MEDIUM/Spec 对齐] REVISED spec 保留结果页渲染子句但未渲染**（overclaim，归 C3）。
- **[MEDIUM/数据层] swebench_dataset_version 误用 repo version**。
- **[LOW/安全] annotate task_id 无路径校验**。
- **[LOW/可维护性] approval-unavailable producer 未落地**（防御性死代码）。
- **[LOW/可维护性] failure_attribution 与 fault_owner_cross 失败集合不一致**。
- **[LOW/测试] RunMetadata 无 from_dict**。

## Round 1 修复（commit 2c2b1c5）
H1 paired bootstrap 配对 + CI=[0,0] 回归测试；M1 任务级 Pass^k min_valid_rounds=3 门槛；M3 流式 usage 解析补 input/cache；M2 未知模型警告；M5 swebench_dataset_version 改 dataset_name@split；M4 正式规格 + delta 加 C3 渲染边界；L1 annotate 路径穿越校验；L4 RunMetadata from_dict；L3 failure_attribution 失败集合统一；L2 approval 无 producer 注记。

## Round 2 复核（PASS）

Round 1 的 10 项修复全部真实生效且回归测试能捕获原缺陷，未引入新的正确性缺陷。

- **H1** [x] `_paired_delta_ci` 每轮重采样先取任务索引再取 A/B 双方通过率（真配对）；模拟旧实现 CI=(-0.3, 0.3) vs 新实现 (0.0, 0.0)。
- **M1** [x] markdown + HTML 任务级 Pass^k `len(valid) >= 3` 门槛，不足显示「—」；恰 3 有效轮边界正确。
- **M3** [x] `_chat_stream` 与 `_stream_chat_impl` 两处 message_start 解析 input/cache，message_delta 只合并 output。
- **M2** [x] 未知模型 `logger.warning`（`asterwynd.cost_tracker`），caplog 断言。
- **M5** [x] `swebench_versions` 从 dataset_name@split 构造，缺失降级，不再读 repo version。
- **M4** [x] 正式规格 + delta 的 Purpose/Intro 渲染边界声明（归 C3 evaluation-protocol-reporting）。
- **L1** [x] `is_relative_to(tasks_root)` 防穿越（含 symlink）。
- **L4** [x] `RunMetadata.from_dict` 向后兼容。
- **L3** [x] `FAILURE_STATUSES` 收敛 failed/error，与 fault_owner_cross 一致。
- **L2** [x] approval_unavailable 无 producer 注记。

### Round 2 新发现问题（LOW，已处理）
- **[LOW] failure_attribution docstring 过期**（仍写含 unsupported）→ 已同步。
- **[LOW] M3 回归测试只覆盖 `_chat_stream` 单路径** → 已补 `stream_chat` 生成器路径测试（input/cache/output 全断言）。
- **[LOW/流程] artifact checker 需 manifest 才转绿** → 本 PASS 后生成 review manifest。

## 最终验证
- benchmark + agent 相关测试 420 passed（含 Round 2 后新增 stream_chat 测试 422 通过）；全量 pytest 2104 passed（2 个预存环境失败与本次无关：tree-sitter 语言包缺失、flow/engine 测试 sys.executable 环境）。
- openspec validate --all --strict 30/30 passed。
- artifact checker：生成 manifest 后通过。
- benchmark smoke（--repeat 3 --seeds 0 1 2）采样参数 + 指标层全链路验证通过。

## 亮点
数据模型向后兼容干净；无效轮排除谓词单一来源；测试覆盖密度高（100+ 新测试）；纯 Python 统计可复现；门禁完整。
