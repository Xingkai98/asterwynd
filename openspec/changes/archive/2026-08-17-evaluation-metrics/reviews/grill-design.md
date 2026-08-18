# Grill: evaluation-metrics 设计追问

## Reviewer
- run id: grill-evaluation-metrics-20260817
- 时间: 2026-08-17

## Confirmed Decisions

- **决策**: D2 独立 pass^k 聚合，不复用 `pass_at_k(k=n)`；理由: `statistics.py:76-92` 证实 k=n 时 `1 - C(n-c,n)/C(n,n)` 坍缩为「≥1 成功」，与「全部成功」语义不同，独立函数正确；来源: grill-evaluation-metrics-20260817
- **决策**: D5 fault_owner 不做 reason→owner 查表推导；理由: spec delta「失败归因与 fault_owner」原文明确「不做 reason→owner 查表推导」（`openspec/changes/evaluation-metrics/specs/benchmark/spec.md:46`），查表会把 reason 分类噪声固化进 owner，design 与该约束一致；来源: grill-evaluation-metrics-20260817
- **决策**: D1 字段可选 + from_dict/to_dict 向后兼容机制；理由: `benchmarks/models.py:80-92` 证实 to_dict 省略 None、from_dict 忽略未知 key 且缺失走默认，旧 artifact 天然兼容；来源: grill-evaluation-metrics-20260817
- **决策**: 纯 Python 统计扩展（不引入 numpy/scipy）；理由: `benchmarks/statistics.py:1-5` 声明纯 Python + 固定 seed bootstrap，paired bootstrap 与精确二项 McNemar 均可同风格实现；来源: grill-evaluation-metrics-20260817
- **决策**: D7 保留 f2p/p2p/reward 的方向；理由: `benchmarks/adapters.py:132-137` 现状只取 resolved 布尔、丢弃 report.json 其余字段，spec delta「SWE-bench 部分成功保留」要求透传，低成本且必要；来源: grill-evaluation-metrics-20260817
- **决策**: D3/D4 cache-aware 定价方向；理由: spec delta「成本与延迟联合展示」要求四档定价 + cache hit rate，`agent/cost_tracker.py:5-25` 现状两档且无 cache 语义，方向正确（但实现路径有缺口，见 Q5）；来源: grill-evaluation-metrics-20260817

## Open Questions

- **Q1**（D2）: pass^k 无效轮次排除谓词未定义，且「approval-unavailable」在 benchmark artifact 中无生产者；推荐答案: 排除判据显式定义为「status=='unsupported' 或 reason ∈ {docker_unavailable, task_family_unsupported, approval_unavailable}」，并新增 fail-closed 时显式写入 approval-unavailable 状态/原因的 producer。
  **例子**: 任务 T 三轮 [failed(docker_runtime_error), unsupported(docker_unavailable), passed]。docker_runtime_error（docker 可用但 harness 崩溃，`adapters.py:108-112`）算无效还是真失败？若按 status 排除 → 有效 2 轮 pass@1=0.5；若把所有 docker 相关都当无效 → 有效 1 轮 pass@1=1.0。同一数据两种口径。且 approval_unavailable 目前只存在于 agent loop 的 tool error_type（`agent/loop.py:833`），不会成为 benchmark 的 status/reason（`agent_runner.py:146,161` 记成 failed/tool_error），spec 枚举的排除项对真实数据是死代码。
- **Q2**（D2）: design D2 声称「pass@1 = 有效轮经验通过率（现有 layer_pass_rate 语义）」与现有实现矛盾；推荐答案: pass@1 定义为新聚合（排除无效轮），并显式决策是否替换结果页现有 layer_pass_rate。
  **例子**: layer 两任务 A[passed,passed,passed]、B[passed,unsupported,unsupported]。现有 `layer_pass_rate`（`report.py:186-187` 把 unsupported 当 False 计入分母 + `statistics.py:95-99`）输出 4/6≈0.667；规格口径 pass@1（排除无效轮）输出 (3/3+1/1)/2=1.0。差 0.33。若替换会改变既有报告数字与 golden 测试 `test_render_report_contains_golden_fragments`；不替换则违反 spec「无效轮次 SHALL NOT 计入 pass@1 分母」（`openspec/specs/benchmark/spec.md:259`）。
- **Q3**（D2）: 部分有效/全无效边界与 n/k 有效性声明未定义；推荐答案: 全无效任务从分子分母同时剔除并标注；有效轮数 <3 时 pass^k 标注「样本不足」不展示；结果页声明 n 与 k 关系（n=k 时仅 pass@1/pass^k 有意义，1<k<n 不推荐）。
  **例子**: 任务 T 三轮 [passed, unsupported, unsupported]，有效 1 轮 → pass^k=1/1=1.0 平凡成立。与 [passed,passed,passed] 同样显示 1.0，但证据强度天差地别。spec「N>=3 才有 pass^k 意义」（`openspec/specs/benchmark/spec.md:372`）未落地为 min-valid-rounds 规则。
- **Q4**（D3）: MODEL_PRICES 四档改造破坏 6 个既有调用点；推荐答案: 显式迁移——MODEL_PRICES 统一改 4 元组，`compute_cost` 同步改为解包 4 档（沿用前缀最长匹配），5 个消费点行为不变；或用独立 CACHE_MODEL_PRICES 保留两档字典不动。
  **例子**: `agent/cost_tracker.py:21-24` 现在 `in_price, out_price = MODEL_PRICES[prefix]`，改 4 元组后直接 `ValueError: too many values to unpack`。消费点 `CostLedger.record`（64）、`report.py:229,323`、`compare.py:122,191` 共 5 处全部崩。design 只说「扩展为四档结构」，未提兼容策略。
- **Q5**（D3）: cache token 数据源整条链路缺失，D3/D4 在真实 run 上永远算不出 cache 收益；推荐答案: C2 补采集链——`agent/llm.py Usage` 加 cache_read/cache_creation 字段 → anthropic_llm 解析 response → loop 累加 → AgentRunResult → TaskResult，并加对应任务。
  **例子**: `Usage` 只有 input/output（`agent/llm.py:47-50`），anthropic_llm 不读 cache 用量，loop 只累加 input/output（`loop.py:633-634`），agent_runner→TaskResult 只传 input/output（`agent_runner.py:381-382`）。claude-sonnet-5 一轮 100K input（80K cache read、10K cache write）+2K output：无采集时按 100K fresh 计费，有采集时 20K fresh+80K read+10K write+2K output，$/resolved-task 差一个数量级。design 的「核算 cache 收益」落空，cache hit rate 恒 0%。
- **Q6**（D4）: $/resolved-task 分子分母边界未定；推荐答案: (a) 明确 passed_with_warnings 计入分母的规则及 SWE-bench「严格 resolved」的透传机制（Verdict 加 resolved 字段或显式声明 resolved==passed）；(b) resolved=0 返回 (None, "no resolved tasks") 供渲染显示「—」；(c) 分子为 0/self-hosted 输出 $0.00 + 「self-hosted 不计费」注记；(d) 成本聚合内部用 compute_cost_cached 自算。
  **例子**: swebench 任务 patch 全过（resolved=true）但 agent 撞 max_iterations → runner 记 passed_with_warnings（`runner.py:338-344`）。D4 计入分母，但「SWE-bench 严格 resolved 由 adapter 透传」没有机制——Verdict 只有 status/reason/detail/score（`adapters.py:22-28`），resolved 布尔被映射成 status 后丢弃（`adapters.py:132-137`）。layer 10 任务全失败、总成本 $5 → 5/0 除零，输出什么？全部 self-hosted → 分子 0 → 输出 $0.0 还是 n/a？
- **Q7**（D5）: fault_owner 写入路径与校验未定义；推荐答案: 增加最小标注工具（`benchmark annotate <run-dir> (task,round) --owner agent|task|environment|unknown`，更新 result.json）或明确「手改 JSON + 重渲染」为唯一路径；聚合层对非法字符串归 unknown 并警告；κ helper（双人标注一致性）归 C2 统计层。
  **例子**: 20 个失败样本，人审标 5 个 task 缺陷。目前无任何工具路径（tasks 无 annotation CLI，report.py 只读不写）。手滑写 "taskk" 进 str 字段，from_dict 照收（`models.py:84-92`），交叉表按什么归并？双人标注不一致 1 个 → κ=(Po-Pe)/(1-Pe)，C2 不提供 κ 统计，C3 的「标注来源声明」没有数据可渲染。
- **Q8**（D6）: 配对比较的二元定义/输入形态/缺对处理未定义；推荐答案: per-task 连续指标用 pass@1（有效轮通过率），McNemar 用 pass^k 布尔做 2x2；输入为两个聚合后的 repeat 集（复用 report.aggregate_results）；不重合任务剔除并注记（或缺失计 0 二选一，必须在文档声明）。
  **例子**: 任务 T，run A [p,p,f]、run B [p,f,f]。pass@1: A=2/3,B=1/3，delta=1/3；pass^k: 均 0 → McNemar 落入 both-fail 格，b=0,c=0 无意义；majority(>0.5): A 胜 → 2x2 得 b=1,c=0，精确二项 p=0.5。三种二元定义三套结论。compare.py 现读单轮 run dir（`compare.py:27-37`），--repeat 每轮独立 run_id 目录（`main.py:765`），paired_comparison 参数形态未定。
- **Q9**（D7）: f2p/p2p 承载位置二选一其实只有一个可行；推荐答案: Verdict 新增 `partial: dict|None` 字段 + runner 构造 TaskResult 时透传到 `TaskResult.partial`，「在 detail 承载」不成立应删除。
  **例子**: report.json {"resolved": false, "f2p_rate": 0.8, "p2p_rate": 0.5, "reward": 0.3}。Verdict.detail 是 str（`adapters.py:27`），runner 把 detail 写 test_output.txt（`runner.py:330-333`）后构造 TaskResult 不带 detail（`runner.py:348-365`）。「在 detail 透传」最远到 test_output.txt 就断了，C3 的「部分成功档」（spec delta 100-105）无结构化数据可渲染。
- **Q10**（D8）: 小 N 声明挂渲染层与 Non-Goal「披露渲染归 C3」冲突；推荐答案: C2 只做统计层输出样本量 N（spec 原文「统计层 SHALL 输出样本量 N 供渲染层判断」，`openspec/specs/benchmark/spec.md:459`），声明文案由 C3 渲染；tasks 7.2 的「渲染层」措辞改掉。
  **例子**: report.py 对 N=3 的任务渲染 per-task CI（`report.py:206-223`）。C2 若直接加「小样本 N=3，区间证据有限」脚注，就改了结果页渲染输出，触碰 Non-Goal，还会改变 golden 测试 `test_render_report_contains_golden_fragments`。
- **Q11**（D9）: 采样参数记录粒度与字段集遗漏；推荐答案: RunMetadata 新增 `temperature`/`seed`/`model_version`（轮级共享，run.json 可读），TaskResult 保留温度/seed 便于 (task,round) 回查；D1 字段集补 `model_version`。
  **例子**: --repeat 3 --seeds 0 1 2 --temperature 0.2 --model-version v-20260817。D1 把 temperature/seed 放 TaskResult（`design.md:43`）、RunMetadata 只加 task_set_hash 等 7 字段，model_version 两处皆无。r2 的 run.json（`models.py:101-119` asdict 写出）里找不到 seed=1/temp=0.2/model_version，C3 报告元组（spec「run artifact SHALL 记录…温度/seed」`openspec/specs/benchmark/spec.md:411`）无从引用。
- **Q12**（D9 补充）: --seeds 与 --repeat 长度不匹配、--repeat 3–5 约束、temperature 是否真实接入采样；推荐答案: 长度不一致时报错（防静默丢弃）；--repeat 上限 5、N<3 警告；C2 只记录不接线，但在结果页声明「temperature/seed 为记录值，部分 provider 不承诺 seed 语义」。
  **例子**: --seeds 0 1 2 3 --repeat 3 → 三轮用 0/1/2，seed 3 静默丢弃还是报错？LLM.chat 无 temperature 参数（`agent/llm.py:35-43`），--temperature 0.2 对真实 run 完全不影响采样，仅记录。面试叙事「采样显式化」需如实区分「记录」与「生效」。
- **Q13**（新/spec-delta 覆盖）: spec delta 9 条 MODIFIED Requirement 中两条带「实现归 C2」注记但 design D1-D9 完全未覆盖；推荐答案: 新增 D10 过程效率指标（trace 采集 time-to-first-successful-edit + exploration fraction，渲染归 C3）+ D11 SWE-bench 污染披露数据层（RunMetadata 补 swebench_dataset_version/swebench_package_version 并 populate），tasks 补对应任务。
  **例子**: (a) 过程效率指标（`openspec/changes/evaluation-metrics/specs/benchmark/spec.md:117-125`）：trace 有 edit 事件带 timestamp（`agent/trace_recorder.py:161-162`），time-to-first-successful-edit = 首次 status 成功 edit 的时间戳 - run 开始；但 exploration fraction 的分子分母无定义，design 无对应决策，tasks 9.1「REVISED 去注记 + 补充具体化细节」对此条无法诚实完成。(b) SWE-bench 污染披露（delta 68-77）：「run metadata SHALL 记录 swebench 数据集版本与 swebench 包版本」是数据层工作，D1 的 RunMetadata 字段集没有这两个字段，task_schema.py 只有 dataset_name/dataset_split（`task_schema.py:34-35`）无版本钉住。C3 渲染「数据集版本与 swebench 包版本钉住」注记时 run.json 无数据可引用。

## User Confirmation

用户原始答复：「看晕了，代码层面且逻辑 ok 的过滤掉，按推荐就行」；主 session 审核后判定全部 13 条按 grill 推荐执行，无例外。

- **Q1**: 用户答复：按 grill 推荐执行（pass^k 排除判据 =「status==unsupported 或 reason ∈ {docker_unavailable, task_family_unsupported, approval_unavailable}」，并补 fail-closed 时显式写 approval-unavailable 状态的 producer）；确认时间: 2026-08-17
- **Q2**: 用户答复：按 grill 推荐执行（pass@1 定义为排除无效轮的新聚合，结果页 layer_pass_rate 按规格口径替换）；确认时间: 2026-08-17
- **Q3**: 用户答复：按 grill 推荐执行（全无效任务从分子分母同时剔除并标注；有效轮 <3 时 pass^k 标注「样本不足」不展示；结果页声明 n 与 k 关系）；确认时间: 2026-08-17
- **Q4**: 用户答复：按 grill 推荐执行（MODEL_PRICES 统一改四档元组，compute_cost 同步解包四档沿用前缀最长匹配，消费点行为不变）；确认时间: 2026-08-17
- **Q5**: 用户答复：按 grill 推荐执行（C2 补 cache token 采集链：Usage 加 cache_read/cache_creation 字段 → anthropic_llm 解析 → loop 累加 → AgentRunResult → TaskResult）；确认时间: 2026-08-17
- **Q6**: 用户答复：按 grill 推荐执行（passed_with_warnings 计入分母 + Verdict 加 resolved 字段透传严格 resolved；resolved=0 返回 (None, "no resolved tasks")；分子 0/self-hosted 输出 $0.00 + 注记；成本聚合内部用 compute_cost_cached 自算）；确认时间: 2026-08-17
- **Q7**: 用户答复：按 grill 推荐执行（增加最小标注工具 benchmark annotate 更新 result.json；聚合层非法字符串归 unknown 并警告；κ helper 归 C2 统计层）；确认时间: 2026-08-17
- **Q8**: 用户答复：按 grill 推荐执行（per-task 连续指标用 pass@1 有效轮通过率，McNemar 用 pass^k 布尔做 2×2；输入为两个聚合后的 repeat 集；不重合任务剔除并注记）；确认时间: 2026-08-17
- **Q9**: 用户答复：按 grill 推荐执行（Verdict 新增 partial: dict|None 字段 + runner 透传到 TaskResult.partial，删除「在 detail 承载」表述）；确认时间: 2026-08-17
- **Q10**: 用户答复：按 grill 推荐执行（C2 只做统计层输出样本量 N，小样本声明文案由 C3 渲染；tasks 7.2「渲染层」措辞改掉）；确认时间: 2026-08-17
- **Q11**: 用户答复：按 grill 推荐执行（RunMetadata 新增 temperature/seed/model_version 轮级字段，TaskResult 保留 temperature/seed 便于 (task,round) 回查，D1 字段集补 model_version）；确认时间: 2026-08-17
- **Q12**: 用户答复：按 grill 推荐执行（--seeds/--repeat 长度不一致报错；--repeat 上限 5、N<3 警告；C2 只记录不接线，结果页声明「temperature/seed 为记录值，部分 provider 不承诺 seed 语义」）；确认时间: 2026-08-17
- **Q13**: 用户答复：按 grill 推荐执行（新增 D10 过程效率指标 trace 采集 + D11 SWE-bench 污染披露数据层，RunMetadata 补 swebench_dataset_version/swebench_package_version，tasks 补对应任务）；确认时间: 2026-08-17

## 风险

- 高: spec-delta 覆盖缺口（Q13）——「过程效率指标」「SWE-bench 污染披露」两条带「实现归 C2」的 Requirement 在 D1-D9 中无对应决策，tasks 9.1 的 REVISED 去注记清单无法诚实完成，validate/artifact checker 会拦截。
- 高: cache token 数据源缺失（Q5）——D3/D4 在真实 run 上 cache 字段恒 None，cache hit rate 恒 0%，cache-aware 定价退化为两档，与面试口径不符。
- 高: D1 字段集对照「报告元组结构化披露」遗漏 model_version/grader_version/轮级 temperature·seed/swebench 版本（`design.md:43` vs `openspec/specs/benchmark/spec.md:411`），C3 报告元组无字段可读。
- 中: MODEL_PRICES 4 元组 arity 破坏 5 个消费点（`cost_tracker.py:21-24,64`、`report.py:229,323`、`compare.py:122,191`）。
- 中: 「pass@1 = 现有 layer_pass_rate 语义」事实错误（`report.py:186-187` 把 unsupported 计入分母），替换会改既有报告数字与 golden 测试。
- 中: approval-unavailable 无 benchmark 生产者（`loop.py:833` 是 error_type，非 status/reason），pass^k 排除枚举含死代码。
- 中: D8 渲染层措辞触碰 Non-Goal（`design.md:33` vs `design.md:97`），C2/C3 边界未收敛。
- 低: fault_owner 无写入工具链、无非法值校验、κ helper 归属未定（Q7）。
- 低: --seeds/--repeat 长度不匹配未定义、temperature 记录与生效分离（Q12）。

## Testing Strategy 缺口（按 D 补）

- D2: 全无效轮（分母 0）、部分有效、有效轮 <3 时 pass^k、排除谓词两种候选的对照测试缺失。
- D3: MODEL_PRICES arity 迁移回归（现有 compute_cost 消费点）、cache_hit_rate 分母含不含 cache_write、未知模型估算规则测试缺失。
- D4: resolved=0、分子=0/self-hosted、passed_with_warnings 边界、严格 resolved 透传契约测试缺失。
- D5: 非法 fault_owner 字符串、双人 κ 一致性、标注写回路径测试缺失。
- D6: 任务集不完全重合、McNemar 二元定义三选一、repeat 聚合输入形态测试缺失。
- D7: Verdict partial 契约（现有 `test_adapters.py:217-243` 用 hasattr 检查，加字段不破坏，但 runner 透传测试缺失）。
- D8: N>5 不声明、统计层只输出 N 的边界测试缺失。
- D9: --seeds 长度不匹配、N<3 警告、run.json 采样参数字段存在性测试缺失。

---

**审阅结论**：design 的 D1–D9 九个决策中六个方向成立（pass^k 独立函数、fault_owner 不查表、字段向后兼容机制、纯 Python 统计、f2p/p2p 保留、cache-aware 方向），但存在 13 个需要用户拍板的开放问题。最严重的三个结构性缺陷是：① spec delta 9 条 MODIFIED Requirement 中「过程效率指标」与「SWE-bench 污染披露」两条带「实现归 C2」注记却完全没有对应决策（Q13）；② cache token 从 provider 到 TaskResult 的采集链路全缺，D3/D4 在真实数据上必然退化为两档定价（Q5）；③ D1 字段集对照「报告元组结构化披露」遗漏 model_version、grader_version、轮级温度/seed、swebench 版本等多个必录字段（Q11）。建议主 agent 停轮，将 Q1–Q13 逐条（每条带例子）抛给用户确认后，再进入实现。
