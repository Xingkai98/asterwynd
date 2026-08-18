# Grill: evaluation-verified-subset 设计追问

## Reviewer

- run id: grill-evaluation-verified-subset-2026-08-18
- 时间: 2026-08-18
- 审查对象: `openspec/changes/evaluation-verified-subset/design.md`（D1–D5）
- 独立零记忆审查声明：本 reviewer 未继承任何开发上下文；全部结论基于对 change 文档与代码文件的逐一实际核验（`benchmarks/swebench_subset.py`、`benchmarks/swebench_convert.py`、`benchmarks/task_schema.py`、`benchmarks/task_set.py`、`benchmarks/adapters.py`、`benchmarks/disclosure.py`、`benchmarks/report.py`、`benchmarks/runner.py`、`benchmarks/tasks/` 全部 10 条 swebench fixture 的 task.json、`tests/benchmark/test_swebench_subset.py`、`test_swebench_convert.py`、C1 grill 记录、backlog #154/#156/#157/#159/#163）。

## 核验到的事实基线（与 design 交叉比对，标出矛盾）

以下均为本 reviewer 直接读代码/文件确认：

- **B1** `build_subset(instances, targets, known_bad, heavy_repos)` 已实现，`SUBSET_TARGETS` = requests+4/flask+6/pytest+8/sympy+8/seaborn+6/pylint+8，`KNOWN_BAD_ENTRIES` 默认空集，`HEAVY_REPOS` 含 django/scikit-learn/sphinx/matplotlib/xarray/astropy。选择逻辑按 instance_id 升序取每 repo 前 N。
- **B2** `generate_tasks(instance_ids, output_base)` 写 task.json 时：`difficulty` 取原始值 `ex.get("difficulty", "")`；**不写** `track`/`scenario`/`version` 三字段；`execution_environment` 恒为 `"docker"`；`external_repo` 来自 `REPO_URLS`（默认 **github.com** URL）；`timeout_seconds` 硬编码 300；`hints.md` 只在 `hints_text` 存在时写。
- **B3** 现有 10 条 fixture（requests×6 + flask×1 + pytest×3）的 task.json 带 `track: verified`/`scenario: bug-fix`/`difficulty: easy`/`version`，且 `external_repo` 指向 **gitee.com/mirrors/*.git**（C1 手工迁移补的）。→ **与 B2 对照的矛盾 1**：管线若直接跑 `generate_tasks` 落盘，写出的 `external_repo` 是 github URL，与既有 10 条（gitee）不一致；若覆盖写既有目录，会把难度/track/scenario 改回不合法值。
- **B4** `validate_fixture` 要求：`track=verified`、`scenario=bug-fix`、`difficulty∈{easy,medium,hard}`、`task_family=swebench`、`execution_environment∈{local,docker}`、instance_id/dataset_name/dataset_split 非空。→ **当前 `generate_tasks` 落盘必 fail 3 项**（track/scenario 缺失 + difficulty 非归一化）。**D1–D5 没有任何 convert 侧改动条目，目标「validate 全过」在 D1–D5 下不可达。**
- **B5** `gold_check(task_dir)`：`external_repo` 非空即 `raise SystemExit`（"需先 clone 到工作区"）；对非外部实例用 `git worktree add <base_commit>`（base_commit 必须存在于当前仓库对象库）。swebench fixture 全部 `external_repo` 非空且 `base_commit` 是外部 repo hash → **当前 gold_check 对 swebench fixture 100% SystemExit，无法自检**。且 gold_check **不装依赖、不建 venv**，只在裸 checkout 里 `git apply` + 直接跑 `test_command`。
- **B6** `REPO_TEST_COMMAND_TEMPLATES` 是**死代码**：全仓只在声明处出现（`swebench_convert.py:41`），`build_test_command` 完全不用它。test_command 由 `build_test_command(repo, FAIL_TO_PASS)` 直接拼 node id。
- **B7** `SwebenchAdapter.verify`（L2 Docker）只用 `instance_id`/`dataset_name`/`dataset_split`/`timeout_seconds`，**不用 `version`、不用 `external_repo`**。
- **B8** `manifest.json` 顶层键 = version/task_set/anti_cheat_disclosure/capabilities/coverage。`task_set.py::Manifest.load` 只读 version/capabilities/coverage；`disclosure.py` 读 anti_cheat_disclosure/capabilities/coverage → **新增顶层键安全（F8 确认）**。但 `disclosure.py` 全文件 grep 无 `verified` 命中——**当前没有任何消费方渲染 manifest 的 verified 段**。
- **B9** CLI 现状：`swebench_subset.py` 是平铺 argparse，仅 `--validate-dir`/`--gold-check` 两个可选参数；`swebench_convert.py` 是独立 main（`--all-requests`/`--batch`/`--instances`/`--output`/`--mirror`）。全仓无外部 CLI 调用者。
- **B10** `generate_tasks` 内部自己调 `load_verified()`（`swebench_convert.py:91`）。build-subset 若先 `load_verified()` 做选择、再调 `generate_tasks`，**数据集会被加载两次**（一次网络 + 内存）。
- **B11** runner 任务发现 = 顶层 `*/task.json` 平铺扫描（`runner.py:193-194`）→ 新增 swebench-* 目录自动被发现，无登记遗漏风险。
- **B12** proposal 声称「无 spec delta（本 change 是实现）」；但 change 实际携带 `specs/benchmark/spec.md` delta，tasks 5.3b 要求「将本 change 的 benchmark delta 同步到当前规格」。→ **proposal 与 tasks/delta 文件自相矛盾**，需在任务 5.1 Impact Analysis 维护时修正。
- **B13** C1 grill 的 OQ-V1 明确写过「KNOWN_BAD 列表来源需钉住（design 只引 R2，未给具体 URL/commit/版本）」，用户确认「从轻量+中等池过滤 KNOWN_BAD 后选择」，但**从未交付具体清单**；`KNOWN_BAD_ENTRIES` 至今空集。

## Confirmed Decisions

- **决策**: D2 数据集加载走镜像端点、不硬编码 `HF_ENDPOINT`，由 `datasets` 库读环境变量；理由: 代码事实支持——`load_verified()` 就是 `datasets.load_dataset("princeton-nlp/SWE-bench_Verified")`，无任何镜像逻辑可污染，环境变量方案对直连/镜像两环境通用；来源: grill-evaluation-verified-subset-2026-08-18
- **决策**: D1 职责边界方向确认——选择逻辑在 `swebench_subset.py`（`build_subset`），落盘在 `swebench_convert.py`（`generate_tasks` 给定 instance_id 落盘），CLI 加在 subset 侧不污染 convert 的「给定 ID 落盘」语义；理由: 代码事实支持接口天然匹配（subset 输出 instance 选择、convert 消费 instance_id）；来源: grill-evaluation-verified-subset-2026-08-18
- **决策**: D4/D5 方向确认——manifest 只登记 verified 段、不占 coverage 矩阵，且只改本段与 B 轨错开合入；理由: 代码事实支持——manifest 所有现有消费方只读 version/capabilities/coverage/anti_cheat_disclosure，新增顶层键对 `task_set.py`/`disclosure.py` 安全，改段不冲突（F8）；来源: grill-evaluation-verified-subset-2026-08-18
- **决策**: 落盘后自动跑 `validate_fixtures_dir`、invalid exit 1 的校验内建方向确认；理由: `validate_fixtures_dir` 已是现成纯函数、输出格式稳定，内建成本低、避免「生成一堆坏 fixture」；来源: grill-evaluation-verified-subset-2026-08-18

## D1–D5 逐项独立判断

| Decision | 判断 | 说明 |
|---|---|---|
| D1 CLI 形态：`build-subset` 子命令 | ⚠️ 方向确认 / 细节缺口 | 职责边界正确；但 ① 与既有平铺 `--validate-dir`/`--gold-check` 的混用方式未定；② `--targets` 示例 `requests+4/flask+6` 用 `/` 分隔与 repo 名 `psf/requests` 内含 `/` 冲突（`psf/requests+4/flask+6` 按 `/` split 得 `['psf','requests+4','flask+6']` 解析失败）；③ 未处理「加载两次数据集」；④ **未含 convert 侧字段修复**（见 OQ-V1） |
| D2 镜像加载 | ✅ 确认 | 代码事实支持（见 Confirmed） |
| D3 生成即校验（validate + gold_check 内建） | ❌ 部分不可行 | validate 内建可行；但「默认跑 L3 自检」**在当前 gold_check 实现下直接 SystemExit**（external_repo 非空即退出，B5），且 design 描述 gold_check「要 clone + 装依赖」与代码事实不符（代码不 clone 外部 repo、不装依赖）。「至少 1-2 条跑通」无可行机制承载。见 OQ-V2 |
| D4 manifest 登记 verified 条目 | ⚠️ 方向确认 / 消费方缺口 | 新增键安全；但「结果页能展示子集规模与偏置披露」无消费方（disclosure.py 无 verified 渲染，B8），且「50 条」数字依赖 OQ-V3 重叠问题的解（可能 46）。见 OQ-V6 |
| D5 与 B 轨并行错开合入 | ✅ 确认 | manifest 消费方只读固定键，改不同段冲突面最小（F8） |

## 9 个重点核查项独立判断

| # | 核查项 | 判断 | 结论 |
|---|---|---|---|
| A1 | difficulty 归一化 + track/scenario 缺失 | **设计有缺口（阻塞）** | D1–D5 未含任何 convert 侧改动；`generate_tasks` 落盘必 fail `validate_fixture` 3 项（B4）。「已交付模板」前提不完整——模板交付了结构，但字段值与校验规则不兼容。最小改动面 = convert 侧写 track/scenario + difficulty 归一化（或 build-subset 落盘后 post-process），见 OQ-V1 |
| A2 | gold_check external_repo 机制 | **设计有缺口（阻塞）** | 代码对 external_repo 直接 SystemExit（B5），D3「默认跑」不可行；需定义 clone→checkout→装依赖→apply→run 机制，或改用 L2 Docker harness 自检，或降级为「抽样 + 记录未自检」。tasks 3.3「至少 1-2 条」与 design「默认跑」、proposal「剔除 flaky」三处口径不一致，见 OQ-V2 |
| A3 | 40 与既有 10 重叠 | **设计有缺口（阻塞）** | requests+4 按 instance_id 升序取前 4 = 1142/1724/1766/1921 全是既有 fixture（B3）；不排除则新生成 <40、总数 46；且覆盖写会把既有 10 条的合法字段改坏（B2/B3）。`--resume` 与覆盖写语义冲突，见 OQ-V3 |
| A4 | KNOWN_BAD 来源 | **需用户拍板** | C1 遗留未钉（B13），当前空集 = build_subset 的 KNOWN_BAD 过滤什么都不滤；需定：硬编码清单 / `--known-bad-file` / 接受空集靠 L2 兜底，见 OQ-V4 |
| A5 | CLI 结构 | **需用户拍板** | 平铺 argparse + 子命令混用方式、`--targets` 分隔符歧义（D1 ③）需定，见 OQ-V5 |
| A6 | manifest verified 段 schema | **需用户拍板** | 登记明细（50×instance_id+repo+difficulty）vs 摘要计数；无消费方（B8）——只登记不渲染则 D4 声称的结果页展示不成立；与 B 轨只改本段并行可行（Confirmed） |
| A7 | test_command 覆盖 | **需用户拍板** | `REPO_TEST_COMMAND_TEMPLATES` 死代码（B6），实际全靠 `build_test_command` 拼 FAIL_TO_PASS node id；风险 = node id 超长/特殊字符/参数化空格、`timeout_seconds=300` 硬编码对慢实例过短、旧 base_commit 下依赖装不上连 pytest 都起不来（L3 无法绿）。seaborn 无模板无害（模板未被使用） |
| A8 | execution_environment=docker + 本地 L3 一致性 | **设计有缺口** | fixture 标 docker（走 L2 harness，B7），但 L3 自检在无依赖裸 checkout 里跑 test_command（B5）——两者对同一实例的「可复现性」判定完全脱节；test_command 在旧 base_commit 下的可运行性无保证。见 OQ-V2 |
| A9 | 坏实例剔除落地 | **需用户拍板** | spec Scenario 说「标记/剔除」，design 说「宁可略少于 40」，但无落地机制（删目录/记录/隔离/补选？），「略少」的具体口径未定，见 OQ-V2 |

## Open Questions

### OQ-V1: 落盘字段修复——track/scenario/difficulty 归一化的最小改动面（A1）

`generate_tasks` 当前写出的 task.json 缺 `track`/`scenario`、`difficulty` 是原始值。**具体前后对比**：跑 `build-subset` 生成 40 条后 `uv run python benchmarks/swebench_subset.py --validate-dir benchmarks/tasks`，输出 40 条 ×3 类错误 `track must be 'verified'` / `scenario must be 'bug-fix'` / `difficulty not normalized: '<15 min fix>'`。请拍板修复位置：

**① convert 侧改 `generate_tasks`（写死 track=verified/scenario=bug-fix + difficulty 归一化）还是 build-subset 落盘后 post-process task.json？** convert 侧改是「模板补齐」的最小改动面（一处函数），但 `generate_tasks` 名义上是通用转换器，写死 verified 语义后若未来转其它数据集（SWE-bench Full）需再改；post-process 不动 convert 但管线多一步、字段修复逻辑散在 CLI。请选。

**② difficulty 映射输入是否存在？** Verified 数据集是否真的带 per-instance `difficulty` 列（`<15 min fix`/`15min-2h`/`≥2h`），本 reviewer 无法离线确认；`ex.get("difficulty", "")` 的兜底空串说明作者也没把握。**场景**：若某实例 difficulty 缺失，映射得 `""`，validate 报 `difficulty not normalized: ''`。请确认本机 hf-mirror 首拉后先打印字段名（design Risks 已有此意，需落成 CLI 的显式字段探针 + 缺失实例的兜底映射口径）。

**③ 顺带拍板两个小项**：`version` 字段（现有 10 条有、generate_tasks 不写——L2 harness 不用它（B7），仅元数据一致性，写不写？）；`external_repo` 用 github 还是 gitee（B2/B3 矛盾，本机 github 可达性未实证，现有 fixture 全用 gitee 镜像）。

### OQ-V2: L3 自检机制、默认行为与坏实例剔除落地（A2/A8/A9）

gold_check 对 external_repo 直接 SystemExit（B5），design 的「默认跑」在当前代码下 100% 崩。**具体场景**：`build-subset --output benchmarks/tasks` 落盘 40 条后自动跑 gold_check，第 1 条 `swebench-psf__requests-XXXX` 即 `SystemExit: external_repo 实例需先 clone 到工作区后再跑 gold_check`，管线崩溃。请拍板：

**① 自检机制三选一**：(a) 扩展 gold_check——按 `external_repo` clone 到工作区 → checkout `base_commit` → 装依赖（pip/uv，旧 base_commit 的 pin 可能装不上）→ apply gold.patch + test.patch → 跑 test_command，40 条 ×(clone+装依赖+跑) 本机/CI 时间不可忽略（单条 timeout 默认 600s，串行最坏 ~6.7h）；(b) 自检改用 L2 Docker `SwebenchAdapter`（run_evaluation，官方 harness 会装依赖）——但这与 design Non-Goals「不改 L2 路径」冲突，需改判；(c) 抽样 1-2 条跑 L2、其余只 validate 元数据 + 结果文档标注「未自检」——与 tasks 3.3 措辞最接近。

**② 「默认跑」与「至少 1-2 条」的口径统一**：design D3「默认跑 L3 自检」、tasks 3.3「至少 1-2 条跑通，其余记录覆盖」、proposal「剔除 flaky/坏实例（若生成即含）」三处不一致。请拍板 `build-subset` 的默认行为：默认全量自检（耗时长）、默认抽样、还是默认跳过（`--gold-check` 显式开启）？`--skip-gold-check` 开关语义随之定。

**③ 坏实例剔除落地**：检出坏实例后是删除 fixture 目录（不可逆，40→38）、移到 quarantine、只记录（spec Scenario 的「标记」）还是自动补选（C1 口径「补齐至 50」暗示补选）？「宁可略少于 40」的具体口径 = 40 条里 2 条坏 → 最终 38 条还是补选到 40？

### OQ-V3: 40 与既有 10 重叠 + `--resume` 语义（A3）

requests+4 按 instance_id 升序取前 4 = 1142/1724/1766/1921，**全是既有 fixture**（B3）。**具体前后对比**：若选择池不排除既有实例，`generate_tasks` 覆盖写这 4 个目录——在 OQ-V1 未修前，重写后 difficulty 变回 `<15 min fix`、track/scenario 消失，`validate_fixtures_dir` 对既有 10 条中的 4 条立刻红（把好 fixture 改坏）；修了 OQ-V1 后覆盖写内容一致但「新生成」只有 36 条、总数 46。请拍板：

**① 选择池是否排除既有 instance_id？** 排除（40 新 + 10 既有 = 50，最贴合「补齐 40 条」口径）还是不排除（接受新生成 <40）？

**② `--resume` 语义**：Risks 里「跳过已存在的 instance_id」与「重复执行幂等（覆盖写）」是两种不同行为。`--resume` 若跳过一切已存在目录，会把既有 10 条也跳过（网络中断续跑场景与「既有 fixture 保护」纠缠）。请定：`--resume` 只跳过**本管线本次已生成**的目录（续跑），既有 fixture 一律不动/覆盖？

### OQ-V4: KNOWN_BAD 来源（A4）

`KNOWN_BAD_ENTRIES` 空集（B1），C1 遗留未钉（B13）。**具体场景**：本次生成 40 条全绿，但池中某条 R2 审计清单内的坏实例 `psf__requests-XXXX` 因空集未被过滤而被选中落盘——「过滤 KNOWN_BAD」形同虚设。请拍板：本次生成的 known_bad 清单来源 = 硬编码进 CLI（需要主 session 从 #146 审计补清单）/ `--known-bad-file` 外部加载（文件不入库）/ 接受空集（Verified 500 本身人工验证过，坏实例靠 L2 兜底，known_bad 过滤仅留接口）？

### OQ-V5: CLI 结构与 `--targets` 解析格式（A5）

**① 平铺 + 子命令混用方式**：`build-subset` 加为子命令后，现有 `--validate-dir`/`--gold-check` 留在顶层（argparse 支持但用法分裂，`python benchmarks/swebench_subset.py --validate-dir X build-subset ...` 会出二义性）还是一并迁入子命令（`build-subset`/`validate-dir`/`gold-check` 三个子命令）？请选。

**② `--targets` 分隔符**：示例 `requests+4/flask+6/...` 用 `/` 分隔，但 repo 键是 `psf/requests` 含 `/`。**具体场景**：`--targets psf/requests+4/flask+6` 按 `/` split 得 `['psf','requests+4','flask+6']`，解析失败或错位。请定：短名映射表（requests→psf/requests）+ `/` 分隔；或逗号分隔 `requests+4,flask+6`；或空格分隔；或直接用完整 repo 名 + 其它分隔符。

### OQ-V6: manifest verified 段 schema 与消费方（A6）

disclosure.py 无 verified 渲染（B8），`report.py` 只透传 manifest。**具体前后对比**：合入后跑 `uv run asterwynd benchmark` + 结果页，反作弊披露段与能力覆盖矩阵照旧，页面上找不到任何「Verified 子集规模/难度披露」字样——D4 声称的「结果页能展示子集规模与偏置披露」在当前代码下不成立（C1 的 G2 口径是「verified 单独披露」，但没有渲染实现）。请拍板：

**① 登记 schema**：50 条明细数组（每条 instance_id/repo/difficulty/track）还是摘要计数（`{count, by_repo, by_difficulty}`）？明细更利于未来渲染/审计，摘要更轻。

**② 消费方**：本 change 是否顺带在 disclosure.py 加 verified 段渲染（扩 scope，把「结果页披露」真正落地）？还是只登记、渲染留给后续 change（D4 声称的结果页展示暂不成立，需在 change 文档如实标注）？数字「50」依赖 OQ-V3 的解（可能 46），登记口径随之定。

## 风险（design 自身 Risks 之外新发现）

- **R1 gold_check 机制误判（新）**：design 描述 gold_check「要 clone + 装依赖」，代码事实是**不 clone 外部 repo、不装依赖、不建 venv**（B5）。基于错误前提的 D3 会把「不可复现」误判为「坏实例」——旧 base_commit 下依赖装不上导致 test_command 起不来时，gold_check 返回非 0，管线会错误剔除良实例或误报 flaky。
- **R2 覆盖写破坏既有 10 条（新，A3 强化）**：generate_tasks 对已存在目录直接覆盖写（`exist_ok=True`）。在 OQ-V1 修复前跑一次管线，既有 10 条合法 fixture 会被写回非法字段，`test_existing_swebench_fixtures_pass_metadata_validation` 单测当场红。此失败模式与网络无关、纯由「选择池含既有 + 覆盖写」触发。
- **R3 双次数据集加载（新，B10）**：`load_verified()` 在 build-subset 选择阶段与 `generate_tasks` 内部各加载一次——500 条数据集两次网络 + 内存。非阻塞但浪费；可让 build-subset 把已加载的 dict 传给 convert（改签名）或接受现状。
- **R4 `timeout_seconds=300` 硬编码（B2）**：对 sympy 等慢实例，L2 Docker harness 传 `--timeout 300` 可能在真实评测时误杀（SWE-bench 官方超时更长）；本 change 不跑真实评测，但生成的 fixture 会带着这个值进入后续评测，属隐性债务。
- **R5 node id 特殊字符（A7）**：`build_test_command` 把 FAIL_TO_PASS node id 直接拼 shell 命令，参数化 id 含空格/引号/`*`/`?` 时可能断词；现有代码只兜了 `\r\n` 一种情况（`-k` 回退）。L3 自检与 L1 跑 test_command 时可能因 shell 解析错位误报。
- **R6 proposal「无 spec delta」矛盾（B12）**：proposal 声称无 spec delta 但 change 携带 `specs/benchmark/spec.md` 且 tasks 5.3b 要求 sync。影响：文档口径不一致 + 若后续有人按 proposal 的「无 delta」判断，会漏掉 sync/审阅门禁；任务 5.1 必须修正。
- **R7 门禁自检（结论：无自死锁）**：本 change 非 docs + 有 spec delta + tasks 全勾选后，artifact checker 强制 `reviews/building-review.md` + review manifest——tasks 6.1 已走 `/review-loop`，可满足。但 building-review 的「Spec 对齐」维度会对照 delta spec 逐条断言，spec 的「金补丁自检剔除坏实例」Scenario 在 OQ-V2 定稿前无实现可对齐，审阅会判 CHANGES_REQUESTED——**OQ-V2 未决前不要全勾 tasks**，否则审阅闭环空转。

## User Confirmation

主 session 转达用户答复（2026-08-18，OQ-V1~V6 全部按推荐执行）。

- **OQ-V1 落盘字段修复**: 用户答复：按推荐——修复放 convert 侧（`generate_tasks` 写死 track=verified/scenario=bug-fix/difficulty 归一化），未来转 SWE-bench Full 再改可接受；本机 hf-mirror 首拉后先打印数据集字段名，无 per-instance difficulty 列时按 FAIL_TO_PASS 测试数启发式兜底（`<15min`→easy/`15min-2h`→medium/`≥2h`→hard）；写 version 字段；external_repo 沿用 gitee 镜像（与既有 10 条一致）；确认时间: 2026-08-18
- **OQ-V2 L3 自检**: 用户答复：按推荐——抽样 1-2 条跑通 gold_check（每 repo ≥1），其余记录「未自检」；默认抽样跑、`--skip-gold-check` 跳过、`--full-gold-check` 全量可选（统一 design/tasks/proposal 三处口径）；坏实例只记录不删除（文档标注，40 可略少）；确认时间: 2026-08-18
- **OQ-V3 既有重叠与 resume**: 用户答复：按推荐——选择池排除既有 instance_id（40 新 + 10 既有 = 50）；`--resume` 只用于续跑已存在 instance_id，既有 10 条永不被选中/覆盖；确认时间: 2026-08-18
- **OQ-V4 KNOWN_BAD 来源**: 用户答复：按推荐——接受空集并记录事实（Verified 500 人工验证过，坏实例靠 L2 兜底），CLI 保留 `--known-bad-file` 接口；确认时间: 2026-08-18
- **OQ-V5 CLI 结构**: 用户答复：按推荐——`build-subset`/`validate-dir`/`gold-check` 全部迁入子命令；`--targets` 逗号分隔短名（`requests+4,flask+6`，短名映射 `psf/requests`）；确认时间: 2026-08-18
- **OQ-V6 manifest verified 段**: 用户答复：按推荐——摘要计数（count/by_repo/by_difficulty），不登记明细数组；本 change 顺带在 disclosure.py 加最小 verified 披露段（D4 承诺落地）；数字按实际（40 或略少）；确认时间: 2026-08-18
