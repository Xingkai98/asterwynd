# Tasks: workflow 资产化（workflow-asset-persistence）

## 1. 规格与设计

- [x] 1.1 维护 `specs/multi-agent-collaboration/spec.md` delta：资产可寻址性 / 显式保存 / 两类载体与覆盖面 / 加载期闸值与能力面钳制 / 命名与同名语义。
- [x] 1.2 维护 `specs/subagents/spec.md` delta：`深度到限撤 spawn 工具` 的工具枚举扩展（含 `RunWorkflowAsset`）。
- [x] 1.3 实现完成后把本 change 的 delta 同步进 current spec：`openspec/specs/multi-agent-collaboration/spec.md`（**7 条 ADDED Requirement**：可寻址性 / 仓库级作用域 / 可发现面 / 显式保存 / 两类载体与覆盖面 / 加载期钳制 / 命名与同名语义）与 `openspec/specs/subagents/spec.md`（1 条 MODIFIED Requirement）。
- [x] 1.4 明确本 change 的范围、非目标和验收标准（design.md 的 Goals / Non-Goals；确认「不做可提交共享路径」「不改 `workflow_id` 与 per-run 结果落点」「不合并 benchmark `workflow_record.json`」三条边界未被实现期偏离）。
- [x] 1.5 开发前使用 `batch-grill-me` 或等价独立零记忆 subagent 设计追问审视 `design.md`，逐项确认 D1–D7 与 Open Questions 的实现细节、依赖、风险、测试策略和文档影响；**每条 Open Question 必须由用户答复并记录进 `reviews/grill-design.md` 的 `## User Confirmation`**，不得把 agent 自己的推荐答案当作用户确认。**（第一轮已完成 2026-09-26：Q1–Q6 与两条实现期确认项拍板；第二轮已完成 2026-09-26：Q7–Q9 拍板。两轮记录都在 `reviews/grill-design.md`。）**
- [x] 1.6 维护 `## Impact Analysis`：全部「待确认影响面」已按用户答复定为结论——落点 = per-repo（`~/.asterwynd/projects/<hash>/workflow-assets/`）、闸值钳制只作用于资产加载路径且**不回写 spec**（方案 C）、可发现面 = 受限形态（仅资产名 + 单行截断 description，20 条 / 120 字符 / slug 64，**只注入 root 会话**）、mode 上限走 **contextvar** 且**以 #255 为前置**。核对「不影响」清单在实现后仍然成立。
- [x] 1.7b 按 Q7/Q8 拍板结论回写 `design.md` 的 D3（**已完成 2026-09-26**）：Q7 整体重写为用户语义模型 + contextvar 方案 + 快照/嵌套语义 + issue #255 引用；Q8 记为方案 C（scheduler 读取处取 min，不回写 spec）；Q9 记为具体数字与范围。**同一变更已同步 proposal（口径订正为「直接改 1 处 + 前置依赖 1 处」）。**
- [x] 1.7c 按 grill 风险 9 订正 `design.md` 的引用行号漂移：`_legacy_result` 定义在 `patterns.py:376`（design 写的 447-461 是 `run_pattern` 尾部）、`RunPatternTool.execute` 在 `subagents.py:435-442`（非 409-427）、`_unknown_workflow` 定义在 `subagents.py:500`。另订正「C3/C5 逐字节断言」的表述——实测两条具名测试是**超集/成员**断言（`test_workflow_graph_snapshot.py:374-385`、`test_workflow_graph_snapshot_additions.py:283-292`），结论（不会被新属性打红）正确但性质需改写。
- [x] 1.7 维护 `## Reference Implementation Research`：确认两层调研（5 个本地参考仓库 + 4 家业界实践）的 findings 与 design impact 在实现期未被推翻；若实现中发现某条借鉴不成立，先回写本 change 文档再继续。
- [x] 1.8 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认和剩余风险。

## 2. 测试（TDD：先写测试）

- [x] 2.1 新增资产 round-trip 单元测试：pattern 资产（`compile_pattern` 编译结果与「保存→加载」结果 `spec_hash` 一致；改 `params` 后 foreach 展开项数随之变化）；DSL 资产（`to_dict()` 往返 + 覆盖面应用后仍过 `parse_spec_for_manager`）。
- [x] 2.2 新增负向与安全测试：slug 越界（`../escape`/`a/b`/大写/空串）、写入路径 symlink 拒绝穿透、`unsupported_asset_version`（高版本明确拒绝 + 缺版本键报错）、`reserved_name`（4 个内置模式名）、`override_not_declared`、覆盖破坏既有不变量时由既有校验拒绝。**每条都要有对照的「合法路径必须成功」用例。**
- [x] 2.3 新增信任边界测试：闸值钳制（`min(声明值, 配置值)` 双向对照）、`limits_clamped` 报告、**模型当轮声明路径行为逐字不变的回归锁**、节点 `mode` 只收窄不放宽、返回体列出以声明 mode 运行的节点。
  - **必须补的对照（grill 风险 7）**：既有 `test_spec_level_limits_override_defaults`（`tests/agent/subagent/test_workflow_spec.py:330-334`）用的是 7 / 11 两个**小于**默认的值，无法区分「取 min」与「无差别压低」。必须新增一条**声明值高于配置值仍原样生效**的用例（声明 `max_runs: 5000`、配置 300 ⇒ 该路径下仍为 5000）。**没有这条，`min` 方向是单向假保护。**
  - **mode 对照用例的稳定性（grill 风险 8）**：「会话允许 build 时 `build` 原样生效」这条在 mode 基准缺陷（见 2.3b）下**结果取决于同图内是否先跑过 read_only 节点**，会写成顺序敏感的不稳定测试。必须先用**单节点**图（不含 read_only 兄弟）建立对照，多节点顺序敏感性交给 2.3b 单独锁。
- [x] 2.3b **（✅ 已解禁：前置 [#255](https://github.com/Xingkai98/asterwynd/issues/255) 已于 2026-09-27 合入 PR #259）** 新增 mode 上限的**六条**回归锁（Q7 已确认走 contextvar）。**若 #255 尚未合入，本任务先在 #255 侧落测试，本 change 只保留消费侧断言，且不得标为完成。** **每条都必须配「合法路径必须成功」的对照，防「永远收紧」的假保护**：
  1. **fail-open 方向**：BUILD 会话跑过图 → 切 READ_ONLY → 声明 `mode: build` 的节点 ⇒ 必须得 `read_only`。**对照**：会话保持 BUILD ⇒ 得 `build`。**复现基线**：`/tmp/myprobe2.py`（主 session 已在共享 provider 方案上稳定复现 fail-open）。
  2. **并发时序**：并行节点 A(`read_only`)/B(`build`) 的构造序互换 ⇒ 各自子 spawn 上限**都正确**、不被对方覆盖。**对照**：单节点图上 `build` 正常生效（并发修复没把正常路径压死）。
  3. **嵌套 grandchild**：A(`read_only`) 的孙 spawn 请求 `build` ⇒ 上限 = A 的**有效** mode（非 root 的）。**对照**：B(`build`) 的孙 ⇒ 得 `build`。**机制可行性已由探针实证**（`/tmp/probe_nested_mode2.py`：grandchild 穿透 + 并发兄弟隔离 + 交错执行全 PASS）；实现期须在**真实**挂点（**派发点 `_launch_run`**，`scheduler.py:2112-2141`——**不是** `_execute_run_in_context`）上重跑同形断言。
  4. **快照语义**：workflow **启动时**快照 root mode，运行中途切 root 模式**不影响本次 run**。**对照**：下一次 workflow 启动按**新** root mode 快照。**边界 = 下一次 `WorkflowScheduler.run()` 调用**，覆盖同会话第二次、新会话、`wait=false` 后台图与嵌套图 B 的全部情形。
  5. **落点对照（grill 第二轮的核心发现，必须有）**：会话 `read_only` + 节点声明 `build` ⇒ 必须收窄。**这条专门证明上限挂对了地方**——只挂 `_execute_run_in_context` 时该用例**仍授予 build**（主 session 独立复现 `/tmp/mine_landing.py`：runctx ⇒ FAIL-OPEN，dispatch ⇒ 已收窄）。**没有这条，落点写错也发现不了。**
  6. **排队延迟不改变上限**：`max_active=1` 强制第二个 run 排队等槽位后，两 run 各自的上限仍正确、互不串味。
  - **测试盲区提醒**：`rg 'parent_mode_provider|_clamp_mode' tests/` 今天**零命中**。
- [x] 2.4 新增容错测试：资产目录混入非法 JSON / 缺 `name` / 半截文件时，`ListWorkflowAssets` 照常返回其余资产 + diagnostics。**必须区分三种状态（grill 风险 6）**：全损坏 ⇒ `total == 0` 且 diagnostics **非空**且含被跳过文件计数；完全无资产 ⇒ `total == 0` 且 diagnostics **为空**；有健康资产 ⇒ 正常返回且 diagnostics 为空。**没有这个区分，一个「吞掉所有异常并返回空列表」的实现同样能通过。**
- [x] 2.4b 新增闸值「对外报值 = 实际生效值」一致性测试（Q8 已确认 = 方案 C）。**前提订正（grill 第二轮实测）**：`status()` / `parent_envelope()` / `workflow_graph_snapshot()` / `_envelope()` **今天根本不报**这三个限制值（主 session 复核：三出口 `limit-value hits=(none)`）——所以这是**新增字段**，不是订正既有漂移。**禁止**照「断言既有键 == 生效值」写测试（键不存在，会写成永远为真或永远报错的假测试）。正确写法：先定义这三个字段加在哪一层，再断言其 == 钳制后的实际生效值。
  - **另注意**：`_envelope` 的 `budget` 块报的是 **C4** 的 `max_total_runs`（`agent/config.py:306`），与本 change 的 **C2** `max_runs` 是不同旋钮，不得混为一谈。
  - 既有漂移锁是**超集断言**（`test_workflow_graph_snapshot.py:380`、`test_workflow_graph_snapshot_additions.py:288` 均为 `set(...) >= {...}`），**加顶层键不会打红**——这点已核实，是利好。
- [x] 2.5 新增跨会话可用性集成测试：fake LLM 跑 `RunPattern` → 保存 → **新建 manager 与 store 实例**（模拟新会话）→ 列出可见 → 按名调用跑通并起出新的 `wf_<uuid8>`；断言资产文件**字节**在复用后未变（fork 语义；不要只断言 mtime，快速文件系统上 mtime 粒度会假通过）。
- [x] 2.5b **新增仓库级作用域测试（Q1 已确认，必须有）**：构造两个指向同一仓库的 workspace root（一个是主 checkout，一个是 `.git` 为**文件**的 worktree，含 `commondir`），断言在其中一个保存的资产在另一个**可见且可调用**；反向对照：不同仓库（不同 hash 桶）之间**互不可见**。**复用既有可测机制**：`agent/memory/persistent.py:62-87` 的 `_find_scope_root` 已被 `tests/agent/memory/test_persistent.py:50-77` 用伪造的 `.git` 文件 + `commondir` 钉死，照该 harness 写。
- [x] 2.5c **新增 pattern 溯源往返测试（grill 挑战 1 的缺口）**：`RunPattern` 产出的 `workflow_id` 经 `SaveWorkflowAsset` 后，资产 SHALL 为 `source == "pattern"` 且 `recipe` 含原始 `pattern`/`params`/`task`；`RunWorkflow` 产出的 `workflow_id` 保存后 SHALL 为 `source == "dsl"`。**这是 3.2b（本 change 唯一改动既有运行路径处）的验收面，design 的 Testing Strategy 目前只覆盖了加载半程、漏了保存半程。**
- [x] 2.6 新增工具面与深度闸测试：`RunWorkflowAsset` ∈ `SPAWN_TOOL_NAMES` 且深度到限时被撤；`ListWorkflowAssets`/`GetWorkflowAsset`/`SaveWorkflowAsset` **不在**该清单且深度到限时仍在；命名空间隔离（`RunWorkflowAsset(name="wf_...")` 拒绝、`GetWorkflow(workflow_id="slug")` 走既有未知路径）。**最贴切的既有用例出处**是 `tests/agent/subagent/test_workflow_tools.py:193-196`（`StartWorkflow`/`RunWorkflow` ∈ `SPAWN_TOOL_NAMES`）与 `:198-210`（深度到限被撤），照它们写（design §5 原本只提了 `test_concurrency_queue.py`/`test_guardrails.py`）。
- [x] 2.6b 新增「`run_pattern` 返回结构逐字不变」的**键集锁**：断言 `set(result) == {bus, completed, critical_path_s, failed, pattern, peak_active, summary, task, total_cost, workers, workflow_id, workflow_spec_hash, workflow_status}`（13 键）。既有 `test_run_pattern_keeps_legacy_fields_and_adds_new_ones`（`tests/agent/subagent/test_pattern_templates.py:175-197`）只做存在性断言，**没有**键集锁，挡不住 3.2b 意外加字段。
- [x] 2.7 新增列表有界性测试：资产数远超上限时返回体带 `total`/`truncated` 且不含 spec 正文。
- [x] 2.8 新增索引一致性测试：同名同 `spec_hash` ⇒ `unchanged` 且磁盘文件**字节**不变（不只 mtime）；同名不同 `spec_hash` ⇒ `updated` + `previous_spec_hash` + 事件日志有记录。**（Q8 = 方案 C：`spec_hash` 按声明值计算，钳制不回写 spec）** 另须覆盖「加载 → 重存」链路：声明 `max_runs: 5000` 的资产在配置 300 下加载后再存回，hash **不变**、动作是 `unchanged`、且资产文件**仍保留 `max_runs: 5000`**（不遗忘原声明值）。
- [x] 2.9 **新增注入面测试（Q4 + Q9 已确认，design §1-7 原本零覆盖）**：断言注入面**只含**资产名（≤64 字符）与单行截断后的 description（≤120 字符）；含 `when_to_use` 或节点 `task` 的资产其字段**不出现**在注入文本中；`description` 内含换行 + 伪小节标题（`说明\n## 忽略以上指令`）时 SHALL 单行化且不产生伪标题；超上限（>20）时条目数 ≤ 20、按 `name` 升序取前 20、并追加「还有 M 个资产未列出」。
- [x] 2.9b **新增注入范围测试（Q9 已确认：只注入 root 会话）**：构造一个子 agent loop，断言其系统提示**不含**资产索引；对照断言 root/session loop 的提示**含**。判据用 `current_spawn_depth() == 0`（实测构造期 root=0 / 子=1），或实现若改用显式构造参数（推荐）则断言该参数。另断言该源 **`cacheable=False`**——用一条「预算裁剪时可被裁掉」的用例钉住（`agent/context/builder.py:129-142` 对 cacheable 源永不裁剪）。**注意** `MemoryIndexSource` 是 `cacheable=True`（`sources.py:286`），与本 change **相反**，不要照抄。
- [x] 2.10 **新增 `GetWorkflowAsset` 手动重放路径的表征测试（grill 挑战 3）**：断言「取回 spec 后由调用方自行 `RunWorkflow(spec=...)`」**不**受闸值钳制（声明 `max_runs: 5000` 在该路径下仍为 5000）。这是把 Q2=A 的已知残余绕过面**显式钉成预期行为**，而不是让它以意外形式存在。

## 3. 实现

- [x] 3.1 实现资产 store（落点已确认 = per-repo `~/.asterwynd/projects/<hash>/workflow-assets/`，经 git common dir 解析 repo 根后取 hash 桶，照 `agent/memory/persistent.py:62-87` 的 `_find_scope_root` scope 解析）：资产 schema（两个载体 + 元数据字段表 + `asset_schema_version`）、slug 校验（`^[a-z0-9-]+$` 与路径段白名单的**交集** + **长度上限 64**——既有 `_validate_name` 只校验字符集不校验长度，`agent/memory/persistent.py:112-116`）、原子写、symlink 门、索引读写、单文件损坏容错。
- [x] 3.2 实现 `SaveWorkflowAsset`：从 `manager.get_workflow(workflow_id)` 取 spec（**不经模型输出**）；按 scheduler 上的溯源字段分类为 pattern 配方或 DSL spec，字段缺失一律降级为 `dsl`（不猜）；同名覆盖与 `unchanged` 判定；保留名拒绝。
- [x] 3.2b 补 pattern 溯源（design.md D1「实现前提」）：在 `WorkflowScheduler.__init__` 里**声明并默认** `asset_source = {"kind": "dsl"}`，由 `run_pattern` 在 `scheduler.run()` 前覆盖为 `{kind:"pattern", pattern, params, task}`。**不要**只在 `run_pattern` 里 ad-hoc 赋值——`RunWorkflowTool.execute` 从不设置 `scheduler.spec`（对比 `DeclareWorkflowTool` 会设），只写一边会让 dsl 路径上该字段**永不存在**，把「预期值」实现成「异常路径」（grill 风险 10）。**纯附加字段**——不改 `run_pattern` 返回结构、不改 `_legacy_result`、不加任何新执行分支；本字段不在 `_envelope`/`parent_envelope` 的显式挑字段清单内，故不污染契约（由 2.6b 的键集锁 + 既有超集断言共同护栏）。
  - 备选（grill 挑战 1 的「第三条路」）：把溯源记在 manager 侧按 `workflow_id` 索引的 dict，让 scheduler 保持纯粹。两条路等价性由 `compile_pattern` 的**确定性**保证——同一配方重编译得到的 `spec_hash` 与当次实跑逐字相同（reviewer probe12 实证），故可用 `spec_hash` 交叉校验真实性。实现期在两者间择一，并在 design 里记明选择理由。
- [x] 3.3 实现 `ListWorkflowAssets` 与 `GetWorkflowAsset`：有界列表面（`total`/`truncated`，不含正文）+ 单资产正文读取。
- [x] 3.4 **（✅ 已解禁：前置 [#255](https://github.com/Xingkai98/asterwynd/issues/255) 已合入）** 实现 `RunWorkflowAsset`：加载 → 应用覆盖面（未声明组合拒绝）→ 闸值取 min → **消费 #255 修好后的 mode 上限（含会话上限通道）** → `parse_spec_for_manager` → 驱动调度器；返回体带 `limits_clamped` 与「以声明 mode 运行的节点」清单。
  - **依赖外部 issue（非「待确认」）**：**#255 必须先合入**，否则「列出以声明 mode 运行的节点」列的是错的基准。**#255 未合入前，本任务停在「只记 diagnostics、不承诺列表正确」的降级口径**，不得对外承诺批准面可信，**且不得标为完成**。执行顺序（用户确认）：**#255 → 本 change（#245）→ #246**。
  - Q11 已确认走**候选 A**：上限的「发起会话 mode」由 **#255 提供的 scheduler 可读通道**取得，本 change 只消费。若 #255 未提供该通道，回退候选 B（工具层显式传参）。
  - **落点订正（grill 第二轮实证 + 主 session 独立复现）**：mode 上限必须挂在 scheduler 的**派发点** `_launch_run`（`scheduler.py:2112-2141`），**不是** `_execute_run_in_context`——后者晚于节点自身 mode 的冻结（`create_subagent` 在 `_launch_run` 内调用），只挂它时「只读会话 + build 节点」**仍授予 build**（`/tmp/mine_landing.py` 双向对照）。**该处 set 不得配对 `finally reset`**（跨 context teardown 会抛 `ValueError`，既有注释 `manager.py:999-1002` 已写明）。
  - `mode` 收窄本身由 `create_subagent` → `_clamp_mode` 结构性保证（`run_subagent` 签名无 `mode` 参数，全部节点 run 都经 `create_subagent`；`route` 与 `aggregate(strategy="collect")` 不起 run），故本条净新增是 diagnostics + 返回字段 + 对 #255 语义的消费。
- [x] 3.5 实现闸值钳制（**Q8 = 方案 C：不回写 spec**）——在 **scheduler 读取** `spec.max_runs`/`spec.max_nodes`/`spec.recursion_limit` 的**所有**入口处取 `min(declared, config)`，`WorkflowSpec` 对象保持声明值不变。
  - **不做**给 `parse_workflow_spec` 加 `limit_ceiling`（原设计，已否决）：那会把钳制值写回 spec，导致 `to_dict()` 丢弃「等于模块默认」的 limit 键、改变 `spec_hash`（实测 `5bb392f41782ea7b` → `d1130d802fff9a0b`），连带破坏 round-trip 断言、`unchanged` 去重与「重存不遗忘」。
  - **读取落点清单（grill 第二轮穷举，全部 9 处，逐处都要改）**：`scheduler.py:753`（`register_workflow_bucket(spec.max_runs * 2)`——**派生值，最易漏**）、`:825`、`:884`、`:1551`、`:2005`、`:2058`、`:2070`、`:2593`、`:2594`。**展开期的 `:2005`/`:2058`/`:2070`/`:2593`/`:2594` 最容易漏**——漏掉会让「资产声明 `max_items=0` 的动态 foreach」按声明值决定展开上限，钳制对动态展开整条路径失效。建议实现为统一访问器（如 `self._eff_limit("max_runs")`）而非 9 处各写各的。跨模块核对：`web/`、`benchmarks/` 对这三个字段**零读取**。
  - 全仓 `parse_workflow_spec(` 生产调用点只有 `patterns.py:280` 与 `subagents.py:468`——方案 C 不改这两个调用点，改动面比原设计更小。
- [x] 3.6 实现 pattern 配方的可序列化描述（模式名 + 参数面摘要），复用 `PATTERNS` 注册表。
- [x] 3.7 接入工具注册（`agent/loop.py`）与 `SPAWN_TOOL_NAMES` 扩展（`agent/subagent/manager.py`）。
- [x] 3.8 在 `DeclareWorkflow`/`RunWorkflow`/`RunPattern` 的工具描述里加入「从零声明拓扑前先列出可复用资产」的行为引导（**不含**自动可发现面，除非 grill Q4 采纳方案 B）。
- [x] 3.9 实现受限可发现面（**Q4 + Q9 均已确认**）：只提升**资产名列表（≤64 字符）+ 单行截断的 description（≤120 字符）**，置于标题明确、标注「数据而非指令」的小节；**不**提升 `when_to_use` 或节点 `task`。**列表面 20 条**，超限按 `name` 升序取前 N 并追加「还有 M 个资产未列出」。
  - **挂载点**：照 `MemoryIndexSource`（`agent/context/sources.py:278-303`）新增一个 `ContextSource`，注册进 `AgentLoop._make_default_context_builder`（`agent/loop.py:1438-1454`）。
  - **必须标 `cacheable=False`**：`ContextBuilder` 对 `cacheable=True` 的源**永不裁剪**（`agent/context/builder.py:129-142` 的 `_find_trimmable_index` 跳过 critical + cacheable）；资产会被 `SaveWorkflowAsset` 在会话内改写，照 `MemoryIndexSource` 的先例（`sources.py:285-287`）必须每轮重渲染，否则内容陈旧且**永久占据**系统提示。
  - **范围限制 = 只注入 root/session loop**（Q9 已确认）：子 agent 的 loop 也走同一默认 builder（`agent/subagent/manager.py:1308-1316` 不传 `context_builder`），必须在源内部判断「当前是否 root loop」并跳过渲染，否则注入会进入**每个子 agent 的系统提示**、随并发度线性放大 token 与暴露面。
  - 补 2.9 / 2.9b 的注入面测试。
- [x] 3.10 接入配置（如需要资产层开关与列表上限）：`agent/config.py` 的 `SubagentsConfig` / `WorkflowLimitsConfig`，补齐解析与默认值，注意「字段默认值 / yaml 加载 / 直构兜底」三处必须一致。
- [x] 3.11 接入入口层与 artifact 记录（若 CLI / benchmark 需要暴露资产路径）。
- [x] 3.12 如果实现中发现新影响面，先回写 `## Impact Analysis` 和本任务清单，再继续无关实现。
- [x] 3.13 如果实现中发现参考实现调研结论需要修正，先回写 `## Reference Implementation Research` 和本任务清单。
- [x] 3.14 更新必要文档（`docs/architecture.md` 的 subagent/workflow 段落、`README.md` + `README_EN.md` 若工具清单被列出）。**核对 `.asterwynd/` 已在 `.gitignore`**；若最终落点改到可提交路径，必须回写 Non-Goals 并停下重新评估。
- [x] 3.15 **前置依赖：确认 issue [#255](https://github.com/Xingkai98/asterwynd/issues/255)（workflow 节点 mode 钳制基准错误）已合入且其 acceptance criteria 含「提供一个 scheduler 可读的会话 mode 通道」**（Q11 候选 A 的前置条件，grill 第二轮提出）。本 change 的 mode 批准面（3.4）依赖它。若 #255 未合入或未含该通道，则：①3.4 停在降级口径（只记 diagnostics）；②回退 Q11 候选 B（本 change 从工具层显式传会话 mode 参数）；③**不得**把 3.4 标为完成。
- [x] 3.16 **（✅ 已解禁；结论：由 #255 的 spec 承担）** 按 Q10/Q11 的拍板结论补 spec delta（design 已回写，本任务落 spec）：
  - **Q10 = 口径 1（继承）**：补一条**跨图** Scenario——图 A 的节点（有效 mode 被收窄为只读）内 `RunWorkflow` 起新图 B，B 的节点上限 SHALL = 该节点的**有效** mode（只读），SHALL NOT 重快照会话 mode。
  - **Q11 = 候选 A**：spec 需说明「启动时快照的发起会话 mode」由 **#255 提供的 scheduler 可读通道**取得。
  - `openspec validate --strict` 抓不到这类语义缺口（实测全绿），必须人工核对。
  - **✅ 落地方式（2026-09-28 订正）**：本任务**不再向本 change 的 delta 补 mode 机制 Scenario**——落地顺序改为**先做阶段 1 的裁剪**（删除本 change delta 里与 #255 主 spec 重复的 mode 机制描述与 6 个 Scenario）。Q10 的跨图继承 Scenario 与 Q11 的「可读通道」语义**由 #255 的 spec 承担**：主 spec 的「workflow 节点 mode 有效值受会话上限钳制」Requirement 的 Scenario「节点自身的收窄随上下文传播到子孙」已明写含「它内启动的另一张图」，即跨图继承；通道侧由 `SubAgentManager.mode_ceiling()` 提供（#255 已合入）。本 change 只保留资产面：被收窄节点记 diagnostics + 「以声明 mode 运行」清单（`RunWorkflowAsset` 消费 `manager.effective_mode`）。

## 4. 验证

- [x] 4.1 运行相关单元/集成测试（`uv run pytest tests/agent/subagent -v`）。
- [x] 4.2 运行全量测试（`uv run pytest -q`）。
- [x] 4.3 运行 OpenSpec strict validate（`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`）。
- [x] 4.4 运行项目 OpenSpec artifact checker（`uv run python scripts/check_openspec_artifacts.py`）。
- [x] 4.5 确认 baseline CI 命令可本地通过：`uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`uv run python scripts/check_openspec_artifacts.py`。
- [x] 4.6 跑通至少一个 benchmark smoke（本 change 触及工具协议与 subagent manager 这条核心 coding-agent 路径）：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke`。
- [x] 4.7 变异验证（改坏实现 → 指定测试变红 → 还原），**逐条照做并记录实际红/绿**：
  1. 把钳制改成 `applied = config`（无条件取下限，去掉 min）→ **仅** 2.3 的「声明值高于配置值仍原样生效」用例应变红；若其他用例也红，说明该用例没把方向单独钉住。
  2. 从返回体删掉 `limits_clamped` 键 → 2.3 的报告断言应变红。
  3. 从 `SPAWN_TOOL_NAMES`（`agent/subagent/manager.py:423-430`）移除 `"RunWorkflowAsset"` → 2.6 的深度闸断言应变红。
  4. 让 `SaveWorkflowAsset` 恒返回 `reserved_name` → 2.2 配对里的**「合法路径必须成功」**用例应变红（**这条专门验证负向套件不是「永远报错的实现也能过」的假保护**）。
  5. 删掉复用后的资产文件**字节**比对断言 → 2.5 应变红。
  6. 在注入面里放回 `when_to_use` → 2.9 应变红。
  7. 把 `cacheable` 误标为 `True` → 需有一条断言「资产源可被预算裁剪」的用例；若无此用例，先补再变异。
  每条记录「改了哪一行 / 哪个测试红了 / 还原后是否复绿」。
- [x] 4.8 显式记录不适用项与理由：本 change 不涉及 Web / TUI / browser / 外部服务入口，故不跑对应 smoke（不留空白，避免被读成「漏做」）。

## 5. PR 收尾

- [x] 5.1 PR 发起前，将本 change 归档到 `openspec/changes/archive/YYYY-MM-DD-workflow-asset-persistence/`（日期前缀为硬性要求）。
- [x] 5.2 从 `docs/openspec-change-backlog.md` 移除本 change，并同步「并行开发批次」章节。
- [x] 5.3 确认 `## Impact Analysis` 不再残留未解释的 `unknown`、`TBD` 或 `待确认`。
- [x] 5.4 确认 `## Reference Implementation Research` 已记录最终调研状态、发现和设计影响，且没有把本地参考仓库路径写成项目依赖。
- [x] 5.5 运行 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 和 `uv run python scripts/check_openspec_artifacts.py`。
- [x] 5.6 运行 `/review-loop workflow-asset-persistence`，产出 `reviews/building-review.md` 与 review manifest（manifest 必须在 `tasks.md` 最终化之后生成）。
- [ ] 5.7 (post-merge) 在实现 PR 合入后，给 issue #245 添加完成说明 comment（写明 PR 号与验证结果）并关闭。

## 6. 审阅闭环修复记录

- [x] 6.1 **Round 1（`reviews/building-review.md`）：CHANGES_REQUESTED**，独立零记忆 subagent 审阅。逐条修复：
  - **M1（中）覆盖面声明了 spec 中不存在的节点 ⇒ 未捕获 `KeyError`**：`_apply_asset_overrides` 增加节点存在性检查，返回结构化 `override_not_declared`。**回归测试**：`test_workflow_asset_tools.py::test_run_asset_rejects_override_for_missing_node`（对照：合法节点覆盖仍成功，见 `test_run_asset_applies_declared_override`）。
  - **L1（低）`RunWorkflowAsset(wait=False)` 返回体不报生效值**：报告改从**已解析的 spec** 直接算（`limits_report(spec, ceiling)`），两条路径口径一致。**回归测试**：`test_run_asset_reports_limits_when_not_waiting`。
  - **L2（低）任务 1.3 标 `[x]` 但 delta 未同步**：本轮完成 spec 同步（`openspec/specs/multi-agent-collaboration/spec.md` 7 条 ADDED + `openspec/specs/subagents/spec.md` 1 条 MODIFIED），1.3 的勾选此时为真。
  - **L3（整洁度）**：删除无调用方的 `_spec_for_asset`、`workflow_assets.py` 未用的 `import os`/`import uuid`、测试里未用的 `_Ctx`。
  - **I1（非本 change）**：`workflow.py` 的 `with_limits` 死代码系 `workflow-dsl-scheduler` 遗留（`git log -S` 指向 `4923883`，base 亦存在），不在本 change 责任面。
  - **I2**：mode 六条回归锁由 #255（`tests/agent/subagent/test_mode_ceiling.py`，`291ed7c` 引入）交付；本 change 的净新增是消费侧断言。
  - 修复后复跑：`tests/agent/subagent` 639 passed；全量 pytest 与门禁见 4.x。
