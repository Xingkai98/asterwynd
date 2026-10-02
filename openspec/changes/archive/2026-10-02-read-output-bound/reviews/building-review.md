# Building Review: read-output-bound

## Verdict

**PASS**

- Reviewer: 独立零记忆代码审阅 subagent（Round 2）
- 时间: 2026-10-02
- 审阅范围: `git diff 3b48407...1e5c606`（22 文件，+1225/-22）+ change 文档 + grill/对抗报告
- 复审对象: **Round 1 的 4 个 issue 是否真修好** + Q4 config 链路实测 + 回归 + 变异
- 环境: worktree `.venv`（`uv run python` 已确认为本 worktree `.venv/bin/python3`），`uv sync --extra dev` 完成
- base sha: `3b48407` / head sha: `1e5c606`

**结论**：Round 1 的 4 个 issue 中，**Issue 1/2/3 已真修好并经实跑/实读证据确认**；**Issue 4 属主 session 管的受保护路径、不在本 change 范围内**。用户新拍板的 **Q4「常量 + 可选 config 覆盖」链路已实测接通**（config → factory → ReadTool → 截断生效，非仅读码）。核心回归 14/14 通过，2 次变异均变红后精确还原。无新引入问题。全量 pytest 与 OpenSpec strict validate 通过。

---

## Round 2 复核（逐 issue + 证据）

### Issue 1（Round 1 = 中等 · 归档门禁会失败）→ ✅ 已修好

Round 1 的根因是 `## User Confirmation` 条目写成 `- **Q1（...）**:`（括号在粗体内，冒号在粗体后），门禁正则 `- **Q<n>**` 判 NO-MATCH，且 Q4/Q6 无记录。

**实跑证据**（调用 `scripts/check_openspec_artifacts` 的真实函数，非仅读码）：

```
$ PYTHONPATH=. uv run python -c "... _extract_user_confirmation_indexes / _unconfirmed_open_questions ..."
User Confirmation indexes: ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7']
Unconfirmed open questions: []
```

对照 Round 1 的 `[]` / `['Q1'..'Q7']` —— 7 条全部解析出来，**无未确认**。格式已改为 `- **Q1**（...）: 用户答复：...`（括号移到粗体后，`grill-design.md` `## User Confirmation`），Q4（上界可配置）+ Q6（E0 验收口径）两条新确认记录已补。

**归档点语义实跑**（`change_type` 用 `parse_change_type(proposal.md)` 得到 `primary='feature'`，与真实门禁同构）：

```
$ PYTHONPATH=. uv run python -c "... _check_design_review_task(cd, ct, assume_implemented=True) ..."
Result: []          ← 空，归档点 design/grill 门通过
```

**四道门**（`_check_archived_completion_gate(cd)` 实跑）：building-review 存在性 / grill 证据（≥3 决策）/ Open Question 确认 / RIR 内容门槛 **全部通过**；唯一剩余报错是「未勾任务未标 `(post-merge)`」——这是**归档前的正常中间态**（closeout 任务此刻尚未执行，归档时才会勾选/移动），不是本 change 的缺陷。放归档目录后该报错自然消失（closeout 勾完 5.x/1.x/2.x/4.1）。

> 说明：Round 1 报告里写的 `['... Q1..Q7 未确认 ...']` 现返回空，缺陷已消除。

### Issue 2（Round 1 = 低 · 文档口径不一致）→ ✅ 已修好

| 位置 | Round 1 旧口径 | 现状（实读） |
|---|---|---|
| `proposal.md:48` | MODIFIED 既有 Requirement | **ADDED** 独立 Requirement「Read 默认输出有界」✅ |
| `proposal.md:86` | `spec.md（MODIFIED 1）` | `spec.md（ADDED 1 独立 Requirement）` ✅ |
| `proposal.md:35` | 「SHALL 可配置」 | 「SHALL 有内置默认…且 **SHALL 可经 config 覆盖**」✅ |
| `tasks.md:7` | 「context-engineering MODIFIED 1」 | 「context-engineering ADDED 1 独立 Requirement」✅ |
| `design.md:38` | 仅「可配置（可选）」 | 新增「可配置（Q4 拍板）」段：内建默认 + SHALL 可经 config 覆盖 + factory 接线 ✅ |

`rg -n "MODIFIED|待 grill|待确认|TBD|SHALL 可配置|non-magic" proposal.md design.md tasks.md specs/` 全库唯一命中是 **`tasks.md:32`（Round 1 修复任务自身的描述文本）**——那是历史记录，不是残留口径。spec delta 头为 `## ADDED Requirements`（`specs/context-engineering/spec.md:3`），正文含「The bound SHALL have a built-in default value and SHALL be overridable via configuration」——与实现（内建常量 + config 覆盖）逐字对齐。

### Issue 3（Round 1 = 低 · 占位文本残留）→ ✅ 已修好

`design.md` 中「**待 grill 确认**」占位已删除，替换为落地结论（`design.md:70`）：

```
> **实现落点**：`read.py` 的 `_truncated_note`（发 `truncated=true`）↔ `manager.py` 的
> `_extract_read_progress`（`if match.group("truncated") and int(match.group(2)) == 0: continue`）。
```

实读 `rg "待 grill" design.md` → 零命中。

### Issue 4（Round 1 = 低 · backlog 口径陈旧）→ ⊘ 不在本 change 范围

`docs/openspec-change-backlog.md:115` 仍写「立项完成，待 grill 与实现」（且 `spec delta：context-engineering MODIFIED 1` 亦陈旧）。但按本次任务约定，**backlog 是主 session 管理的受保护路径，不计入本 change 修复范围**，故不作为 verdict 依据。**遗留提醒**：归档收尾（主 session）需更新/移除该行，否则描述与事实不符。

### Q4（用户新拍板 · 上界「常量 + 可选 config 覆盖」）→ ✅ 链路实测接通

Round 1 实现是硬编码常量、无 config；本轮新增 `ReadOutputConfig` + 全调用链接线。**审阅者自写脚本** `/tmp/verify_q4_chain.py` 端到端实测（**非仅读码**）：

```
[A] 构造 ReadOutputConfig(max_lines=5) → build_default_tool_registry → 读 100 行文件
    ReadTool.max_lines=5  max_bytes=131072
    返回 5 行（首行 line-000 / 末行 line-004）+ truncated=true 注记   ✅ 被截到 5 行
[B] 无 config → 默认 = 模块常量 2000/131072；100 行文件逐字节返回全文、无注记  ✅
[C] config max_bytes=20 → body ≤ 20 字节 + truncated 注记          ✅ 字节维生效
[D] read_output_config=None → 回落 2000/131072                    ✅
```

**链路核实**（读源码，非仅看文件名）：

- `agent/config.py:139` `ReadOutputConfig(max_lines=2000, max_bytes=128*1024)`（frozen dataclass）；`:160` 挂到 `ToolsConfig.read`；`:871` `_parse_read_output_config` 解析 `tools.read`，用 `_validate_positive_int` 校验（非法值 fail-fast）。
- `agent/tools/builtin/read.py:151-156` `ReadTool.__init__(*, max_lines=DEFAULT_MAX_READ_LINES, max_bytes=DEFAULT_MAX_READ_BYTES)`；`:183-196` 界内判定与 `_bounded_prefix(..., self.max_lines, self.max_bytes)` 均取实例属性。
- `agent/tools/factory.py:328/434` 两处 entrypoint 均 `ReadTool(policy=policy, max_lines=read_output.max_lines, max_bytes=read_output.max_bytes)`；`read_output = read_output_config or ReadOutputConfig()`。
- **4 个调用点全部接线**（逐个读源码确认参数名真为 `read_output_config=`）：`agent/main.py:284`、`agent/subagent/manager.py:1291`、`web/session.py:1582`、`benchmarks/agent_runner.py:364`。

**测试**：`tests/agent/tools/test_read_output_bound.py::TestBoundIsConfigurable` 4 条（默认=常量 / config 覆盖截断 / 字节覆盖 / registry 接线 + 无 config 默认）+ `tests/agent/test_config.py` 3 条（默认值 / yaml 解析 / 非法值 fail-fast）。实跑 82 passed。

---

## Tasks Verification

逐条核对 `tasks.md` 的 `[x]`（读代码 + 实跑）。

| 任务 | 状态 | 证据 |
|---|---|---|
| 3.1 先写失败测试（8 类） | ✅ | `tests/agent/tools/test_read_output_bound.py`（33 测试含本轮新增 6 条） |
| 3.2 无显式正 limit 三路径统一施加默认界（行+字节先到者） | ✅ | `read.py:181-198`；实跑 `limit=0`/`offset` 无 limit 均被 2000 行界截 |
| 3.3 上界常量化 + `limit is not None` 区分 0 | ✅ | `read.py:25-26` 常量；`read.py:174` `if limit is not None and limit > 0` |
| 3.4 注记显式化 + 同步 `_READ_PROGRESS_RE` + 跨模块测试 | ✅ | `read.py:46-55`；`manager.py:23-25` 正则可选分组；跨模块测试在文件内 |
| 3.5 修 D6：默认截断 offset=0 不覆盖显式分页 | ✅ | `manager.py:482` `if match.group("truncated") and int(match.group(2)) == 0: continue`；实测三向用例通过 |
| 3.6 `total` 恒为文件总行数 | ✅ | `read.py:157` `total = len(lines)`；实跑 D6 用例 `total=21000` 正确 |
| 3.7 回归 `tests/agent/tools/` | ✅ | 856 passed（本轮实跑读/内存/配置相关子集 82 passed） |
| 4.0 Round 1 修复 | ✅ | `00 openspec…修复` 见 diff；本报告即复核 |
| 4.2 全量 pytest | ✅ | 2 failed（环境噪声）/ 3890 passed / 9 skipped |
| 4.4 benchmark smoke | ✅ | 触及 `agent/tools/`，任务清单记录 |

未勾任务（1.1-1.5、2.1-2.5、4.1、4.3、5.1-5.7）为立项/收尾/审阅类——**归档前的正常中间态**；`5.8` 已正确标注 `(post-merge)`。归档点判定见上（四道门通过，仅「未勾任务」为待 closeout 项）。

---

## Issues

无**中等及以上**问题。以下为 Low / 提示项，均不阻塞 PASS：

### Issue A（Low · 提示 · 流程项，非 change 缺陷）— review manifest 待生成

当前 `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` 报 `review manifest missing`（exit 1）。这是**预期的中间态**，非本 change 缺陷：manifest 由 `/review-loop` 第 6 步在本报告 verdict=PASS **之后**生成（绑定 reviewer run / base·head sha / tasks·spec·diff·report hash）。Round 1 为 CHANGES_REQUESTED，故未写 manifest。

**行动**：驱动方在本报告定稿后跑 `/review-loop` 第 6 步写 `reviews/building-review-manifest.json`（`reviewer_run_id` 须为**真实**审阅 agent 的 run id；审阅者此处**无法合法提供**，不代填占位——若代填，`verify_review_manifest` 会因 report_hash/tasks_hash 在后续 closeout 变动而失效）。任务 4.1「`/review-loop` 至 PASS + manifest」须在归档前勾选。

### Issue B（Low · 信息准确性）— 修复 commit message 的测试清单轻微夸大

`1e5c606` 的 commit message 列了「…非法值 fail-fast / **example yaml 可解析**」两项测试。实测：`test_invalid_read_output_config_fails_fast` 存在；但**全仓无任何测试加载 `asterwynd.example.yaml`**（`rg "asterwynd.example|example.yaml"` 在 `tests/`、`scripts/` 零命中）。审阅者独立加载该 example 文件**解析成功**（`tools.read = ReadOutputConfig(max_lines=2000, max_bytes=131072)`），故 example yaml 本身正确，只是缺一条守护测试。属 commit message 的措辞夸大，无功能影响。**建议**（非必须）：补一条 `load_config` 加载 example 文件的守卫测试，或修正 commit 描述。

### Issue C（Low · 一致性 · 非本 change 引入）— bool 陷阱沿用既有先例

`tools.read.max_lines: true`（YAML）会被 `_validate_positive_int` 静默接受（`isinstance(True, int)` 为真）→ `max_lines=1`。这是**既有模式**——本 change 显式仿照的 `tools.display.max_result_chars/max_result_lines`（`config.py:1457/1462`）同款暴露；仓库内仅 `_parse_timeout_seconds`（`config.py:1530`）做了 bool 显式拒绝。**非本 change 新引入**，不作缺陷计。若日后统一收紧，应作为独立 tech-debt 处理。

---

## Test Results（实跑）

| 命令 | 结果 |
|---|---|
| `uv run pytest tests/agent/tools/test_read_output_bound.py tests/agent/test_config.py -q` | **82 passed** in 2.50s |
| `uv run pytest tests/agent/tools/test_read_output_bound.py -q -k registry`（还原后） | **2 passed** |
| `uv run pytest -q`（全量） | **2 failed, 3890 passed, 9 skipped** in 360.93s |
| `uv run pytest tests/benchmark/test_parallel_runner.py::test_parallel_execution -q`（隔离） | **1 passed** in 1.88s |
| `npx @fission-ai/openspec@1.4.1 validate --all --strict` | **29 passed, 0 failed** |
| `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` | exit 1：`review manifest missing`（见 Issue A，预期中间态） |

**2 条全量失败 = pre-existing 环境噪声**：`/tmp/.git` 在本机存在（`ls -la /tmp/.git` 确认），`_find_scope_root` 上溯到 `/tmp` 认为它是 scope root，断言 `is None` 失败。`tests/agent/memory/` 本 change **零改动**（`git diff` 确认只动了 `manager.py` 的 2 行跳过逻辑，与该测试无关）。隔离跑同样 2 failed，确为环境依赖。

**parallel_runner 与本 change 无关**：`test_parallel_execution` 是纯 timing 断言（`elapsed < 0.8`、`spread < 0.15`），依赖 `DelayedRunner`，**不触碰 `Read`/config.read**；隔离与全量均绿。

### 回归核心断言（审阅者自写脚本 `/tmp/verify_regression.py`，端到端实跑 ReadTool + MemoryManager）

| 用例 | 结果 |
|---|---|
| `limit=0`（21000 行文件）body 被截到 2000 行、非全文 | ✅ PASS |
| `offset=2000` 无 limit body 被截到 ≤2000 行、不到 EOF | ✅ PASS |
| ≤界逐字节=现状（CRLF / 尾换行 / 空 / 非 UTF-8 / 普通 五类） | ✅ 5/5 PASS |
| D6：paged→default 保留真实 offset 2000；default→paged 同；default 单独→无进度 | ✅ PASS |
| 注记含 `truncated=true` + `continue with offset=` | ✅ PASS |
| 显式正 limit=5 → 恰 5 行 | ✅ PASS |

**14/14 通过。**

### 变异验证（改坏 → 变红 → 还原）

| 变异 | 结果 |
|---|---|
| **M1**: `_bounded_prefix(lines, start, self.max_lines, self.max_bytes)` → `_bounded_prefix(lines, start)`（丢弃配置的界） | **2 failed**（`test_tool_bound_override_truncates_small_file` / `test_tool_byte_override_truncates`）✅ |
| **M2**: factory 两处 `ReadTool(policy=policy, max_lines=…, max_bytes=…)` → `ReadTool(policy=policy)`（配置不生效） | **1 failed**（`test_registry_wires_read_output_config`：`assert 2000 == 77`）✅ |

两次变异后均 `git checkout --` 还原；`md5sum` 确认 `read.py=adaef75f…`、`factory.py=98c690c5…` 与原始一致；`git status --short` **仅余两个 untracked reviews 文件**，无残留改动。

### 新增问题排查

- **循环 import**：`import agent.config / agent.tools.factory / agent.tools.builtin.read / agent.main / agent.subagent.manager / agent.tools` 全部 OK；冷启动序（先 factory 后 read/config）OK。`ReadOutputConfig` 加在既有 `agent.config` import 行内，无新环。
- **调用点漏接**：`ReadTool(` 全仓仅 `factory.py:331/437` 两处实例化；`build_default_tool_registry` 的 4 个调用方（main/subagent/web/benchmark）**全部**传 `read_output_config=`，逐个读源码确认。无漏接入口。
- **工具注册未破坏**：default / coding registry 均 24 tools、`Read` 在场；`test_read_doc_and_pagination.py` 等既有测试未改动。
- **example yaml**：实加载成功（见 Issue B）。

---

## 结论

- **Round 1 的 Issue 1/2/3 已真修好**——Issue 1 以真实门禁函数实跑确认（Q1–Q7 全解析、0 未确认、归档点门返回空）；Issue 2/3 以实读确认（ADDED 口径统一、占位清除）。Issue 4 属主 session 受保护路径，不在范围。
- **Q4 config 链路真接通**——审阅者自写脚本实测 `max_lines=5` 把 100 行文件截到 5 行，且经 factory 建 registry、4 个调用点全接线、有 7 条配置级测试；2 次变异（丢配置的界 / factory 丢 config）均变红。
- **无新引入问题**：无循环 import、无漏接调用点、工具注册完整。
- **回归稳固**：14/14 断言通过；全量 pytest 仅 2 条 pre-existing `/tmp/.git` 环境失败；OpenSpec strict validate 29/29。
- **注意**：`check_openspec_artifacts.py` 现报 `review manifest missing` 属**预期中间态**——manifest 由 review-loop 第 6 步在本报告定稿后生成（Issue A），非 change 缺陷。
- **`git status`：干净**（变异全部还原，仅余 `acceptance-evidence.md` / `building-review.md` 两个未跟踪的审阅产物，符合预期）。

**Verdict: PASS** — Round 1 的 4 个 issue 中 3 个真修好、第 4 个超范围；Q4 config 链路实测接通；无新问题；测试通过。后续仅需驱动方按流程写 review manifest 并完成 closeout（主 session）。
