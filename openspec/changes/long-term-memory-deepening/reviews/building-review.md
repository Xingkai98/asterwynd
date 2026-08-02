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
