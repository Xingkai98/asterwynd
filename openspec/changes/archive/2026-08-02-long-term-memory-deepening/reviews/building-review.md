# Building Review: long-term-memory-deepening

## Verdict

**CHANGES_REQUESTED**

两个 major 问题需要修复后才能进入合入闸门：

1. `run_decay()` 未接入任何生产调用路径，spec「超 30 天未检索自动归档」在运行系统中实际不生效。
2. `MemoryDedupJudge` 硬编码 `model="gpt-4"`，对 anthropic provider 会静默失败回退「new」，核心三分支去重能力在该 provider 下完全失效；对 openai provider 也会覆盖用户配置的模型。

修复这两点并补上回归测试后，建议重新审阅。其余实现（schema、三分支存储语义、衰减公式、归档/恢复、SearchMemory、摘要注入、scope 隔离、ADR、spec 同步、benchmark 任务）均有真实实现与测试覆盖，质量良好。

## Tasks Verification

| task | 验证结果 | 代码位置 |
|------|---------|---------|
| 1.1 schema 扩展 importance/created_at/last_accessed_at/scope（pyyaml frontmatter） | 真实实现 | agent/memory/model.py:13-36（MemoryEntry 字段）；agent/memory/persistent.py:259-335（_parse_file/_write_entry，yaml.safe_load/safe_dump）；测试 tests/agent/memory/test_long_term.py:44-89（TestSchema，含旧格式迁移默认值） |
| 1.2 embedding 召回 top5 相似（复用 #77） | 真实实现 | agent/memory/persistent.py:476-521（search/recall_similar 用 NGramEmbedding embed+cosine 线性扫描）。注：直接复用 agent/embedding 的 NGramEmbedding，未用 InMemoryVectorStore 类，功能等价 |
| 1.3 LLM 三分支判断（llm 可空 fallback） | 真实实现，但见 major-2 | agent/memory/dedup.py:65-139（MemoryDedupJudge + _parse_judgment，action 白名单 new/supplement/update/conflict，llm=None 或失败回退 new） |
| 1.4 矛盾标记 + change log | 真实实现 | agent/memory/persistent.py:428-440（conflict 分支互标 conflict_with）；agent/memory/persistent.py:599-605（_append_changelog → memory_dir/changelog.md）；测试 test_long_term.py:282-296 |
| 1.5 SaveMemoryTool 去重语义（factory 注入 llm） | 真实实现 | agent/tools/builtin/memory.py:59-100；agent/tools/factory.py:125-131（_build_memory_dedup_judge）、265/345（SaveMemoryTool(memory, judge)） |
| 1.6 单元测试三分支/矛盾/change log | 通过 | tests/agent/memory/test_dedup.py:34-115；test_long_term.py:246-304；tests/agent/tools/test_memory_tools.py:204-274 |
| 2.1 importance × recency（0.5^(days/30)，时钟可注入） | 真实实现 | agent/memory/persistent.py:124-133（decay_score）；persistent.py:104-115（time_source 注入）；测试 test_long_term.py:97-107 |
| 2.2 超 30 天未检索自动归档 + 归档/恢复 API（run_decay 惰性执行） | 部分实现，见 major-1 | archive/restore：persistent.py:527-563，测试 test_long_term.py:138-155；run_decay：persistent.py:135-148。但 run_decay 无任何生产调用点 |
| 2.3 单元测试衰减公式/归档 | 通过 | test_long_term.py:97-155（TestDecay） |
| 3.1 SearchMemory 语义检索工具（top-k，scope/type 过滤） | 真实实现 | agent/tools/builtin/memory.py:137-202（SearchMemoryTool）；persistent.py:476-512（search）；注册 factory.py:31/267/347、KNOWN_BUILTIN_TOOL_NAMES factory.py:67 |
| 3.2 MemoryIndexSource 全局摘要 ~50 token（summary.py 启发式） | 生效但来源有冗余，见 minor-5 | agent/context/sources.py:274-301（MemoryIndexSource → load_summary）；persistent.py:189-218（load_summary 实际实现）；agent/memory/summary.py:15-45（build_summary 未被任何代码引用） |
| 3.3 集成测试摘要注入 + 检索 | 通过 | tests/agent/test_memory_e2e.py:160-191（摘要注入且不注入全文）、382-416（SearchMemory e2e） |
| 4.1 project/repo scope 标签 + 跨项目校验 | 真实实现 | persistent.py:114（scope=self.scope）、301（解析 metadata.scope）、459-460/491-492（recall/search scope 拒绝）；测试 test_long_term.py:188-191、test_memory_tools.py:170-175 |
| 4.2 单元测试 scope 隔离 | 通过 | 同上 |
| 5.1 ADR 三层存储成本论证 | 通过 | docs/adr/ADR-0001-long-term-memory-storage.md（accepted，含备选方案与 Revisit Conditions） |
| 5.2 OpenSpec spec 同步 | 通过 | openspec/specs/long-term-memory/spec.md（4 个 ADDED requirements 已合入）；delta openspec/changes/long-term-memory-deepening/specs/long-term-memory/spec.md |
| 5.3 全量 pytest + openspec validate + artifact checker | 部分 | pytest 1495 passed / 1 failed（tree-sitter，与本 change 无关，pre-existing）；openspec validate strict 32/32 passed；artifact checker 当前报 building-review.md missing（本报告即产出物） |
| 5.4 benchmark 量化 | 通过 | benchmarks/tasks/asterwynd-022-long-term-memory/（issue.md / task.json / gold.patch / test.patch，test_command 跑 test_long_term + test_dedup，issue 含注入 token 节省 / 三分支 / 衰减留存率量化口径） |
| 8.1 pre-implementation batch-grill-me / 等价设计审阅 | 通过 | design.md:64-83（Pre-Implementation Review，R1-Q1~Q14 全部确认并记录） |
| 8.2 benchmark smoke verification | 无提交内证据 | 任务勾选但 change 目录/仓库中未见 smoke run 产物；仅有 task 定义文件 |
| 8.3 spec delta 合并到正式 spec | 通过 | 见 5.2；workflow-events.jsonl seq=1 记录 current_spec_synced 事件 |

## Issues

### Major

- **[major] run_decay 无生产调用点，spec「自动归档」在运行系统不生效**
  - agent/memory/persistent.py:135-148（run_decay 定义）、154-218（load_index/load_summary）、448-512（recall/search）——四个本应触发 run_decay 的入口都没有调用它；agent/context/sources.py:288-301（MemoryIndexSource.render 直接 load_summary）也没有；agent/loop.py:1180 只注册 source。
  - 全仓 grep：run_decay 仅在定义处和测试（test_long_term.py:117/136）出现，无生产调用。
  - design.md:76（R1-Q7）明确约定「run_decay() 在 load_index / recall / search / 摘要生成前调用」，实现未兑现。spec（openspec/specs/long-term-memory/spec.md「超 30 天未检索自动归档」）的验收场景在真实运行中不可达。功能机制完整（评分、归档、恢复均可用且测试通过），属于接线缺失，修复成本低（在 load_summary/search/recall/load_index 前加一次惰性调用即可），但当前是规格与实现间的真实缺口。

- **[major] MemoryDedupJudge 硬编码 model="gpt-4"，anthropic provider 下核心去重能力静默失效**
  - agent/memory/dedup.py:97：model=self._model or "gpt-4"。
  - agent/tools/factory.py:125-131：_build_memory_dedup_judge 只传 llm=llm，_model 恒为 None → judge 恒用 "gpt-4"。
  - agent/anthropic_llm.py:52-54：resolved_model = model or self.model，于是 "gpt-4" 会被原样发给 Anthropic API → 400 → 被 dedup.py:99-101 的 try/except 吞掉，静默回退 Judgment("new", ...)。结果：anthropic 用户的三分支去重完全不会发生（也不报错）；openai 用户则被强制用 gpt-4，覆盖其配置的模型。
  - 建议：model=self._model（None 时交由 LLM 实例用自身模型），并补一个跨 provider 的回归测试。

### Minor

- **[minor] MemoryConfig 是死配置**：agent/config.py:202-215 定义、251 挂载，但 _load_yaml_config（config.py:372-381）从不解析 memory: 段，PersistentMemory.__init__（persistent.py:104-115）也不接受 config。6 个旋钮（archive_after_days / recency_halflife_days / importance_default / recall_top_k / summary_tokens / dedup_recall_threshold）全部未接线，实际生效的是 persistent.py:23-29 的模块常量。design R1-Q11 声称「挂到 AsterwyndConfig.memory」可配置，未兑现。
- **[minor] dedup_recall_threshold 从未应用**：agent/tools/builtin/memory.py:82-93 只要有条目就调 judge；persistent.py:514-521 recall_similar 无阈值过滤。design R1-Q3（design.md:72）明确要求 max_sim < 阈值时短路直接新建以省一次 LLM 调用，未实现——每次带 LLM 的 SaveMemory 都会白花一轮 judge 调用。
- **[minor] agent/memory/summary.py 是死代码**：summary.py:15 build_summary 全仓无引用（grep 仅命中定义），实际用的是 persistent.py:189-218 load_summary 内联的同构逻辑。两份实现需双维护，应择一。
- **[minor] apply_judgment 的 target_name 未校验**：persistent.py:403-440 直接用 LLM 返回的 target 构造路径（_entry_path，persistent.py:224-227）并写入 conflict_with。_parse_judgment（dedup.py:120-139）不限制 target 必须是候选名。真实风险低（memory_dir 按项目 hash 隔离、_parse_file 要求 frontmatter），但作为纵深防御应在 _parse_judgment 或 apply_judgment 用 _VALID_NAME_RE / 候选名单校验 target。
- **[minor] 死代码残留**：persistent.py:154-187 load_index、persistent.py:629-653 _extract_body/_extract_type/_extract_name 仅被旧测试 test_persistent.py 引用，AgentLoop 已改用 load_summary。可保留兼容，但属维护面。
- **[minor] save() 更新路径忽略 type 参数**：persistent.py:360-366 更新时保留 existing.type，丢弃新的 type。origin/master 旧行为是覆盖 metadata.type。属于行为变更（多数情况下更合理），但未记录、无测试。
- **[minor] backlog 命名过时**：docs/openspec-change-backlog.md:126 仍写 search_memory，规格与实现已用 SearchMemory。后续归档时需一并修正（并配 workflow-events 事件）。

## Test Results

```
$ uv run pytest tests/agent/memory/test_long_term.py tests/agent/memory/test_dedup.py tests/agent/tools/test_memory_tools.py tests/agent/test_memory_e2e.py -q
66 passed in 2.43s

$ uv run pytest tests/agent/memory/ tests/agent/tools/test_memory_tools.py tests/agent/test_memory_e2e.py -q
107 passed in 2.18s

$ uv run pytest -q            # 全量
1495 passed, 7 skipped, 1 failed in 230.39s
FAILED tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols
# 与本 change 无关：diff 未触碰 agent/code_intelligence 任何文件，
# 属环境性 tree-sitter 语法包缺失（Java/Kotlin 符号提取为空），判定为 pre-existing。

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 32 passed, 0 failed

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: building-review.md missing — 独立 subagent 审阅未运行   # 本报告产出后消除；
# 但 verdict 为 CHANGES_REQUESTED，/review-loop 需修复→再审直至 PASS 并生成
# reviews/building-review-manifest.json（verdict=PASS）后闸门才真正通过。
```

## 结论

实现整体扎实：schema/三分支存储语义/衰减公式/归档恢复/SearchMemory/摘要注入/scope 隔离均有真实代码与测试，openspec strict validate 通过，目标测试全绿，全量仅一个与本次无关的 pre-existing tree-sitter 失败。

但存在两个必须修复的 major 问题：(1) run_decay() 未接入任何生产路径，spec 的自动归档能力在真实运行中不生效；(2) 去重 judge 硬编码 model="gpt-4"，使 anthropic provider 下的核心三分支去重静默失效。另有若干 minor（MemoryConfig 未接线、dedup_recall_threshold 未应用、summary.py 死代码重复、target_name 未校验等）。

**Verdict: CHANGES_REQUESTED**。修复两个 major 并补回归测试后，重新审阅至 PASS 并生成 review manifest，方可合入。


---

# Round 2 Review (2026-08-02)

## Verdict

**PASS**

Round 1 的 8 项修复全部真实落地，每项均有回归测试覆盖且通过。目标测试全绿、OpenSpec strict validate 通过、benchmark 任务在 base commit 上独立验证可用。artifact checker 目前唯一报错是 `reviews/building-review-manifest.json` 缺失——该 manifest 由 `/review-loop` 在 verdict=PASS 后生成（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash），非本 reviewer 产出物；生成后闸门即通过。剩余问题均为 minor（两个残留死配置旋钮、config 接线缺直接测试、个别健壮性/措辞），不阻塞合入。

## Round 1 修复项验证（逐一）

| # | 修复要求 | 结果 | 代码证据（文件:行号） |
|---|---------|------|----------------------|
| 1 | run_decay 接入读路径 + 节流 | 已修复 | `agent/memory/persistent.py:164-177` `_run_decay_if_due()`（节流 `DECAY_INTERVAL_SECONDS=3600`，persistent.py:32）接入 load_index(:189) / load_summary(:228) / recall(:479) / search(:514)。回归测试 `test_run_decay_fires_from_read_paths`（tests/agent/memory/test_long_term.py:169-182）、`test_run_decay_throttled_within_interval`（test_long_term.py:184-207） |
| 2 | dedup judge 硬编码 gpt-4 | 已修复 | `agent/memory/dedup.py:113` `model=self._model`（不再 `or "gpt-4"`）；factory `_build_memory_dedup_judge`（agent/tools/factory.py:125-135）不传 model → None；AnthropicLLM（agent/anthropic_llm.py:54 `resolved_model = model or self.model`）与 OpenAILLM（agent/openai_llm.py:35）均以 None 回退自身模型。回归测试 `test_does_not_override_provider_model`（tests/agent/memory/test_dedup.py:103-109）断言 `llm.last_model is None` |
| 3 | MemoryConfig 死配置接线 | 已修复（含残留 minor，见下） | `_parse_memory_config`（agent/config.py:1185-1216）接入 `_load_yaml_config`（config.py:381）；main.py:247-253 把 archive_after_days / recency_halflife_days / importance_default / summary_tokens 传给 PersistentMemory；factory.py:131-135 把 `memory_config.dedup_recall_threshold` 传给 judge |
| 4 | dedup_recall_threshold 未应用 | 已修复 | `agent/memory/dedup.py:93-95` 过滤 `c.score >= self._recall_threshold`，低于阈值短路 `Judgment("new", None, "below_recall_threshold")`；factory.py:134 传入配置值。回归测试 `test_below_recall_threshold_short_circuits_to_new`（test_dedup.py:111-117） |
| 5 | summary.py 死代码 | 已修复 | `agent/memory/persistent.py:226,231` load_summary 委托 `summary.build_summary`（agent/memory/summary.py:15 为唯一实现），内联同构逻辑已删除 |
| 6 | apply_judgment target 路径安全 | 已修复 | `agent/memory/persistent.py:418-419` `_validate_name(str(target))` 校验通过后才进入 supplement/update/conflict 分支与 `_entry_path` 构造 |
| 7 | save() update 丢 type | 已修复 | `agent/memory/persistent.py:374` `existing.type = type`。回归测试 `test_save_update_changes_type`（test_long_term.py:81-87） |
| 8 | backlog search_memory → SearchMemory | 已修复 | `docs/openspec-change-backlog.md:113` 状态改为「已实现并归档（2026-08-02）」、:126 `SearchMemory` 语义检索；delta spec 与正式 spec（openspec/specs/long-term-memory/spec.md）均已同步为 `SearchMemory` |

## 八维复查

**1. 任务逐项验证**：tasks.md 1.1-1.6、2.1-2.3、3.1-3.3、4.1-4.2、5.1-5.4、8.1-8.3、9.1-9.8 全部 `[x]`，每项均有真实实现（对照上表 #1-#8，无 checkbox 假勾选）。

**2. 正确性**：
- 节流边界：`_run_decay_if_due` 首次调用立即执行（`_last_decay_run is None`），窗口内（3600s）跳过；run_decay 内部走 `load_entries()` 不触发读入口，无递归。
- 空候选：`judge` 在 `llm is None or not candidates` 时直接 new（dedup.py:90-91）。
- target 校验：非 kebab-case 直接回退 save；supplement/update 目标缺失或已归档回退 save（persistent.py:423-424/435-436）；conflict 分支目标不存在时跳过互标但不丢写入。
- decay 公式：`0.5**(days/30)`、归档条件 `days > 30`（persistent.py:159）与 spec「超 30 天」一致；recall/search 对命中条目 `_touch` 刷新 last_accessed_at（persistent.py:491, 531），检索防归档闭环成立。
- 残留：`_parse_memory_config` 中 `dedup_recall_threshold=float(...)`（config.py:1213-1215）未走 `_parse_positive_float` 防护，非数值会抛未捕获 ValueError 而非 ConfigError。

**3. Spec 对齐**：4 个 ADDED requirements（写入去重与冲突检测 / importance×recency 时效性衰减 / 按需语义检索与全局摘要 / Scope 隔离）在 delta 与正式 spec 均存在，且已合入 `openspec/specs/long-term-memory/spec.md`。小措辞出入：decay 场景写「When the decay score falls below the threshold」，实现是「未检索天数 > 30 触发归档」（score 阈值门按 design R1-Q6 默认关闭）——语义等价，不构成缺口。

**4. 冗余度**：summary.py 双实现已归一（fix 5）。残留：`persistent.py:319-348 _write_entry` 与 `:585-609 _write_entry_to` 近重复（frontmatter 序列化逻辑两份）；`_extract_type/_extract_name/_extract_body`（:648-673）与 `load_index`（:183-217）仍仅被旧测试引用（Round 1 minor，保留兼容）。

**5. 测试覆盖**：8 项回归测试全部存在且通过。缺口：MemoryConfig 接线无直接测试——没有测试断言 yaml 中的 `memory.archive_after_days` / `dedup_recall_threshold` 能传播到 PersistentMemory / judge；阈值过滤测试是直接构造 judge（不经 factory）。建议后续补一个 factory/config 级传播测试。

**6. 安全性**：
- 路径安全：LLM 提供的 `target_name` 在进入路径构造前经 `_VALID_NAME_RE`（persistent.py:19, 418）校验 + 存在性检查 + 失效回退；`memory_dir` 按 git-root hash 隔离（persistent.py:35-37, 118-123）。
- Scope 隔离：recall/search 在读取前拒绝非本 scope（persistent.py:477-478, 510-511），测试 test_search_scope_isolation_blocks_foreign_scope / test_scope_mismatch_returns_nothing 覆盖。
- Prompt injection：judge 输出受 action 白名单（dedup.py:24, 149）+ target 校验双重约束，最坏情况回退 new/direct-save，无任意文件写入面。
- changelog 追加无危险注入面。

**7. 可维护性**：模块职责清晰（model/persistent/dedup/summary 四模块 + 工具薄壳）；config 旋钮集中。残留两个死旋钮（见下 #1）与 `_write_entry` 重复是最主要维护负担。

**8. CI 完整性**：目标测试 113 passed；`npx openspec validate --all --strict` 32/32 passed；artifact checker 唯一报错为 review manifest 缺失（PASS 后由 /review-loop 生成）；benchmark 任务独立验证可用（见 Test Results）。全量 pytest 结果见下。

## 遗留 minor（均不阻塞合入）

1. **`importance_default` 存而未用、`recall_top_k` 解析后未消费**：`self._importance_default`（persistent.py:127）从未被引用，`_clamp_importance`（persistent.py:59-66）与 `_parse_file`（:303）仍用模块级 `DEFAULT_IMPORTANCE=3`；`recall_top_k`（config.py:1203-1205）解析后无任何消费点（SaveMemoryTool 硬编码 `top_k=5`，agent/tools/builtin/memory.py:84）。即 6 个 MemoryConfig 旋钮中 2 个仍为死配置——默认值（3 / 5）下行为不变，仅用户显式配置时静默失效。
2. **config 接线缺直接测试**：无测试断言 yaml `memory:` 段 → PersistentMemory 构造参数 / judge 阈值的传播（见「测试覆盖」）。
3. **`dedup_recall_threshold` 浮点解析无 ConfigError 防护**：config.py:1213-1215 `float(...)` 对非数值抛裸 ValueError。
4. **spec decay 场景措辞**与实现触发条件（score 阈值 vs 天数）略有出入，见「Spec 对齐」。
5. **`_write_entry` / `_write_entry_to` 近重复**、`_extract_*` 与 `load_index` 遗留旧接口（Round 1 minor 保留，属维护面非缺陷）。
6. **8.2 benchmark smoke 无提交内 run 产物**：与「不提交 benchmark runs」工作区规则一致，属预期；本轮已独立复验任务可用性（见 Test Results）。

## Test Results（Round 2）

```
$ uv run pytest tests/agent/memory/ tests/agent/tools/test_memory_tools.py tests/agent/test_memory_e2e.py -q
113 passed in 2.17s

$ uv run pytest -q            # 全量
1501 passed, 7 skipped, 1 failed in 272.79s
FAILED tests/agent/code_intelligence/test_tree_sitter_symbols.py::test_tree_sitter_extracts_java_and_kotlin_symbols
# 与本 change 无关：diff 未触碰 agent/code_intelligence 任何文件，
# 属环境性 tree-sitter Java/Kotlin 语法包缺失（与 Round 1 全量 1495 passed/1 failed 同一失败，
# 目标测试新增 6 个回归用例，其余全绿）。

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 32 passed, 0 failed

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: long-term-memory-deepening: review manifest missing: .../reviews/building-review-manifest.json
# 唯一剩余项：verdict=PASS 后由 /review-loop 生成 manifest（绑定 reviewer run、base/head sha、tasks/spec/diff/report hash）。

# benchmark 任务独立复验（base_commit dc83b4c 上）
$ git apply gold.patch && git apply test.patch
$ uv run pytest -q tests/agent/memory/test_long_term.py tests/agent/memory/test_dedup.py
37 passed in 4.80s
```

## 结论

Round 1 的两个 major（run_decay 未接线、judge 硬编码 gpt-4）与六个 minor 均真实修复并有回归测试；4 个 ADDED requirements 在 delta 与正式 spec 双对齐；目标测试与 OpenSpec 校验全绿；benchmark 任务在 base commit 上独立验证通过。残留问题全部为 minor，不影响规格验收路径。

**Verdict: PASS**。生成 review manifest（verdict=PASS）后，CI 闸门即可通过。


---

# Round 3 Review（2026-08-02，补做 batch grill 后修订提交 2eef1fd）

## 审阅范围

- 对象：`2eef1fd`（`git diff b85876b...HEAD`）——用户补做 batch grill（Round 2 决策树）拍板后落地的四项实质修订 + Q3/Q5/Q6/Q9 follow-up + 文档回写。
- 方法：独立零记忆 subagent，8 维 workflow 审阅；对照 `grill-design.md` Round 2 决策树、`design.md` Round 2 用户确认、归档 tasks.md 逐项核验实现（读代码，不只看文件名）。
- 本报告为补做 grill 修订的独立复评，verdict 覆盖 `2eef1fd` 引入的全部变更。

## Verdict

**PASS**

四项用户拍板（R2-1 归档评分门、R2-2 scope 解析、R2-3 embedding 口径、R2-4 可逆性→#99 follow-up）与 Q3/Q5/Q6/Q9 全部真实落地，均有回归测试覆盖且通过。正式 spec 的时效性衰减 requirement 已同步评分门语义，实现与 spec 一致。目标测试 161 passed、全量 1651 passed（6 失败全部为已知环境问题：5 个 MCP 缺 uv、1 个 tree-sitter Java/Kotlin）、openspec strict validate 29/29、artifact checker（含 `--check-archived`）通过。剩余问题均为 minor 观察，不阻塞合入。

## 用户拍板项验证（逐一）

| 项 | 用户决定 | 验证结果 | 代码证据 |
|----|---------|---------|---------|
| R2-1 归档判定评分门 | A 评分门，decay_threshold 默认 1.5（None 关闭） | 已落地 | `agent/memory/persistent.py:34` `DECAY_THRESHOLD=1.5`；`:208-229` `run_decay` 双条件 `days > archive_after_days AND (threshold is None OR decay_score < threshold)`；`:195-206` `decay_score` 分数天（`total_seconds()/86400`）修 30.9 天边界；`agent/config.py:218-219` MemoryConfig 两新字段、`:1198-1207` yaml 解析（null→None）、`:1235-1240` 接线；`agent/main.py:252-253`、`agent/tools/factory.py:308-309/404-405` 传入 PersistentMemory |
| R2-2 scope 解析 | A git common-dir 派生，同仓 worktree 共享 | 已落地 | `agent/memory/persistent.py:45-68` `_find_scope_root`（.git 目录=checkout root；.git 文件=解析 `gitdir:`→`commondir`）；`:71-92` `_git_common_dir`；本 worktree 实测 `_find_scope_root` 解析到主仓 `/home/happy/my-agent`，验证共享生效 |
| R2-3 embedding 口径 | A dim=2048 对齐 + InMemoryVectorStore + seam 降级协议层 | 已落地 | `agent/embedding/provider.py:22` `DEFAULT_EMBEDDING_DIM=2048` 共享常量；`agent/memory/persistent.py:579-605` `search()` 默认 embedder `NGramEmbedding(dim=DEFAULT_EMBEDDING_DIM)` 且改走 `InMemoryVectorStore`；`agent/tools/factory.py:119-121` `_wire_governance` 改用共享常量消魔数 |
| R2-4 写时去重可逆性 | A，作为 follow-up 新 change（issue #99） | 已按决定登记 | 本 change 不原地修订；`docs/known-debt.md` 「写时去重可逆性缺口（R2-4 → issue #99）」条目；design.md Round 2 记录偏差 |
| Q3 decay_interval_seconds 第 7 旋钮 | 补接线 | 已落地 | `agent/config.py:1236-1240` `_parse_memory_config` 解析（`_validate_positive_int`）；main.py/factory.py 传递；测试 `tests/agent/test_config.py:602-658`（yaml 解析 + 默认值 + null + 非法值） |
| Q5 CI 事件门禁 | fetch-depth:0 + base-ref + fail-closed | 已落地 | `.github/workflows/ci.yml:17-20` fetch-depth:0；`:48-56` 传 `--base-ref`（PR base.sha / push HEAD）+ `--require-base`；`scripts/check_openspec_artifacts.py:914-941` `_changed_paths_since_base` 返回 `(paths, warning)`，base 不可解析时 warning；`:961-966` `--require-base` 参数；`:1000-1009` fail-closed 把 warning 升为 error |
| Q6 manifest 校验 | verify 支持归档 + --check-archived + 重建漂移 manifest | 已落地 | `agent/workflow/review_manifest.py:23-49` `change_dir_for`（archived 扫描 date 前缀）；`:135-175` `verify_review_manifest(archived=)`；`scripts/check_openspec_artifacts.py:597-600` `_change_id_from_dir_name`；`:603-645` `_check_review_manifests(archived=)` 仅漂移检测不要求历史审阅；`:987-995` `--check-archived`。4 个历史漂移 manifest（context-engineering / grill-enforcement / long-term-memory / sandbox-hardening）已重建，实测 tasks_hash/spec_hash/report_hash 全部与当前 artifact 匹配（脚本复算通过） |
| Q9 SearchMemory 描述 | 改「文本相似度召回」 | 已落地 | `agent/tools/builtin/memory.py:141-145` 「by text similarity (char n-gram embedding recall, not full semantic understanding)」 |

## 八维复查

**1. 任务逐项验证**：tasks.md 1.x-9.x 全部 `[x]`；本修订涉及项（2.2 衰减归档、4.1 scope、9.x 审阅修复）实现真实存在（见上表），无 checkbox 假勾选。R2-4 不落地为独立任务因属 follow-up #99，已按用户决定在 known-debt 登记。

**2. 正确性**：
- 衰减双条件：`days <= archive_after_days → continue`；`threshold is not None and decay_score >= threshold → continue`；否则归档。与 spec「超 30 天未检索且衰减评分低于阈值」字面一致。默认 importance=3 第 31 天 score≈1.465<1.5 归档；importance=4/5 延长至约 43/53 天（设计口径吻合）。
- 30.9 天边界：`(now-last).total_seconds()/86400` 分数天，30.9 > 30 触发归档；回归测试 `test_decay_boundary_uses_fractional_days`（test_long_term.py:262-272）与 `test_decay_score_fractional_recency`（:274-289）锁定。
- worktree .git 解析：`gitdir:` 相对路径按 `.git` 文件父目录 resolve；`commondir` 相对路径按 gitdir resolve；标准布局 `main/.git/worktrees/<name>/commondir=../..` → main 仓 checkout root。真实 git worktree 集成测试 `test_real_worktrees_share_scope`（test_persistent.py:101-133）双 checkout scope/hash 相等。
- fail-closed CI：`--require-base` 下 base 不可解析 → error（exit 1）；默认 best-effort → stderr WARNING 不阻断。回归测试 `test_require_base_fails_closed_when_base_unresolvable` / `test_require_base_defaults_to_best_effort_warning`。
- manifest archived 路径：`change_dir_for` 扫描 date 前缀 dir → `verify_review_manifest(archived=True)` 按归档目录校验 tasks/spec/report hash；漂移检测测试 `test_verify_review_manifest_archived_path`（改 tasks.md 后报 tasks hash mismatch）。

**3. Spec 对齐**：正式 spec（`openspec/specs/long-term-memory/spec.md:45-61`）时效性衰减 requirement 已改为「超 30 天未检索且衰减评分低于可配置阈值」，并新增「高重要度记忆豁免归档」场景；与实现（run_decay 双条件）完全一致。归档 delta spec 保留旧「30 天」措辞为冻结历史，正式 spec 是活契约、已对齐（已知 minor，见下）。

**4. 冗余度**：`search()` 手写线性扫描由 `InMemoryVectorStore` 复用替代（消除重复 cosine 循环）；`DEFAULT_EMBEDDING_DIM` 共享常量消除 2048 魔数两处（persistent.py / factory.py）。Round 1 遗留 `_write_entry`/`_write_entry_to` 近重复未在本修订引入，维持原状。

**5. 测试覆盖**：新增回归测试全部通过：衰减门（高 importance 保留/None 关闭/分数天边界/分数 recency）、search dim 锁（monkeypatch RecordingNGram 断言 2048）、scope worktree（伪造 layout/畸形回退/真实 git 集成）、config 解析（段解析/默认/null/非法）、require-base（fail-closed/warning）、archived manifest（id 剥离/漂移检测）。已知缺口：factory/config→PersistentMemory 传播无直接测试（Round 2 minor 遗留，见下 #1）。

**6. 安全性**：`_git_common_dir` 解析的路径仅用于派生 `self.scope`（字符串）与 project hash；记忆文件恒写入 `~/.asterwynd/projects/<hash>/memory`，恶意 `.git` 文件内容最多改变所用 hash 目录，无任意写面、无路径逃逸、无提权。scope 校验为字符串相等、fail-safe（不匹配返回空集），无绕过读他人 scope 的路径（memory_dir 按 hash 隔离是真正的隔离边界）。无新增注入面。

**7. 可维护性**：`_find_scope_root`/`_git_common_dir` 注释清晰、分工明确；`change_dir_for` 的 archive 扫描有 docstring 说明 date 前缀约定；配置旋钮集中且命名一致；`_changed_paths_since_base` 元组返回 + warning 语义文档化。良好。

**8. CI 完整性**：CI 显著增强而非弱化——fetch-depth:0 + `--require-base` fail-closed 堵住「浅克隆静默跳过受保护路径门禁」的既有漏洞；checker 新增 `--check-archived` 归档漂移检测（默认不启用，按设计 opt-in）。push 事件下 `BASE_REF=GITHUB_SHA` diff 自身恒空、门禁空转（见 minor #3），但 PR 事件是实际闸门，属既定设计。

## Issues（全部 minor，不阻塞）

1. **[minor] factory/config→PersistentMemory 传播无直接测试**（grill Q3 推荐项未完全兑现）：yaml→MemoryConfig 解析已测（test_config.py:602-658），但没有任何测试从 `get_default_tools(memory_config=...)` / `_build_agent_core` 断言 `decay_threshold`/`decay_interval_seconds` 真正传入 PersistentMemory 实例。若日后有人在 factory/main 调用中漏传某个旋钮（R1-Q11 死配置家族同款风险），无测试兜底。建议补一条 factory 级传播回归测试。
2. **[minor] `decay_threshold: false` 会被解析为 0.0**（`config.py:1201` `float(False)`）：YAML `false` 是 bool，`float` 得 0.0，语义变成「几乎永不归档」而非「关闭评分门」。文档已写 null 才是关闭方式，但 bool 值应显式拒绝（`isinstance(decay_threshold_raw, bool)` 报 ConfigError）以避免误配。低风险脚枪。
3. **[minor] CI push 事件受保护路径门禁空转**：`.github/workflows/ci.yml:51-55` push 分支时 `BASE_REF=$GITHUB_SHA`，`git diff --name-only <自身>` 恒空 → 直接 push master 可绕过事件校验。PR 事件是实际闸门，直接 push 属非主流路径，与既定设计一致（review 描述明确「or HEAD on a push」），仅记录观察。可用 `$GITHUB_SHA^` 或依赖 PR 流程收紧。
4. **[minor] `change_dir_for` 归档扫描非确定性**（`review_manifest.py:39-49`）：若未来出现两个不同日期的归档目录共享同一 change_id，`iterdir()` 顺序任意，返回不保证；当前仓库无此冲突（实测 `--check-archived` 全绿）。可排序或精确匹配锁定。
5. **[minor] `_git_common_dir` commondir 缺失回退**（`persistent.py:90-91`）：非标准布局下 fallback `worktree_gitdir.parent.parent` 可能得到错误 scope root（如 `main/.git`）。git 对 linked worktree 恒写 commondir，此路径仅防御性存在，无实际触发面。
6. **[minor] 重建 manifest 绑定 post-review tasks.md**（Q6 既定妥协）：long-term-memory-deepening 的 tasks_hash 从 c0df38（审阅时）重建为 d2bfea（当前，含 closeout 补充的 9.x 节与实测数据）。manifest 现在绑定的是审阅后编辑过的 tasks.md 而非审阅当时快照——这是用户批准的漂移修复机制（known-debt Q6 已记录），`head_sha`/`diff_hash` 仍固定原范围，可接受。
7. **[minor] 归档 delta spec 时效性衰减措辞保留旧语义**：归档 delta（`archive/.../specs/long-term-memory/spec.md`）requirement 仍写「SHALL auto-archive memories not retrieved for 30 days」，未含评分门从句；正式 spec 已同步为双条件。归档 delta 是冻结历史不回放，正式 spec 为权威，仅记录观察。

## Test Results（Round 3）

```
$ python3 -m pytest tests/agent/memory/test_long_term.py tests/agent/memory/test_persistent.py \
    tests/agent/test_config.py tests/test_openspec_artifact_checker.py \
    tests/agent/workflow/test_review_manifest.py tests/agent/tools/test_factory_sandbox_wiring.py -q
161 passed in 4.33s

$ python3 -m pytest tests/agent/memory tests/agent/test_config.py tests/agent/tools \
    tests/agent/workflow tests/test_openspec_artifact_checker.py tests/agent/test_memory_e2e.py -q
729 passed in 16.03s

$ python3 -m pytest -q     # 全量
1651 passed, 7 skipped, 6 failed in 95.50s
# 6 失败全部为已知环境问题：5 个 tests/agent/mcp/test_mcp_manager.py 缺 uv（issue #82），
# 1 个 tests/agent/code_intelligence/test_tree_sitter_symbols.py Java/Kotlin 语法包缺失。
# 均与本修订无关（diff 未触碰 mcp/code_intelligence）。

$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --base-ref origin/master
OpenSpec artifact checks passed

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived
OpenSpec artifact checks passed

# 复算 4 个重建 manifest：tasks_hash/spec_hash/report_hash 全部与当前 artifact 匹配（脚本核验通过）
```

## 结论

用户补做 batch grill 拍板的四项实质修订与 Q3/Q5/Q6/Q9 follow-up 全部真实落地，代码、spec、文档、事件四层一致：归档判定评分门使 decay_score 真正进入生产路径并修复 30.9 天边界；scope 解析使同仓 worktree 共享记忆（本仓库自身即受益）；embedding 对齐 dim=2048 且复用 InMemoryVectorStore，0.5 阈值语义成立；CI 门禁 fail-closed、manifest 支持归档漂移检测且历史漂移已重建绑定。回归测试完备、全量校验通过、无安全面引入。

**Verdict: PASS**。残留 7 项均为 minor 观察（多为既有遗留或既定妥协），不阻塞合入。建议后续补 factory 级 config 传播测试（minor #1），可在 #99 follow-up 一并处理。
