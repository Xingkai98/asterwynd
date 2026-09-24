# Building Review: fix-issue-232-archived-manifest-gate

## Verdict
PASS

## Reviewer
- run id: `cf4bb6d7-f877-4bc7-a2bb-7ffb6c07787b`（独立零记忆 subagent，未继承开发上下文）
- 审阅范围: `origin/master...678347e`（base `cea1e53a521d37d5c18d23700c811909f1095d6c`；diff 16 文件 / +707 −13）
- 复核方式（全部实读 + 实跑；变异验证后已 `git checkout --` 还原，`git status --porcelain` 仅剩两个既有 untracked 文件）：

  **读**
  - `agent/workflow/review_manifest.py`（`verify_review_manifest` :135-180，A′ 落点 :175；`_verify_git_span` :209-232）
  - `scripts/check_openspec_artifacts.py`（`_check_review_manifests` :1009-1051，归档分支 :1425-1447，main 的 errors→exit :1456+）
  - `scripts/check_phase_done.py:274-276`（第三个调用方，恒 `archived=False`）
  - `.github/workflows/ci.yml:57-72`、`AGENTS.md:111`、`docs/development-guide.md:251-266`、`docs/known-debt.md`、`docs/openspec-change-backlog.md`
  - change 文档：`proposal.md` / `design.md` D1–D6 / `tasks.md` / delta spec / `reviews/grill-design.md`
  - `openspec/specs/dev-workflow-state-machine/spec.md:140-158`（正式 spec 对照）
  - 测试：`tests/agent/workflow/test_review_manifest.py`、`tests/test_openspec_artifact_checker.py`（含 diff 逐行核对）

  **实跑**
  - `uv run pytest tests/agent/workflow/test_review_manifest.py tests/test_openspec_artifact_checker.py -q` → **93 passed**
  - `uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py -q` → **25 passed**
  - 全量 `uv run pytest -q` → **6 failed, 3041 passed**（6 条全部与本 change 无关，见下）
  - `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog` → **exit 0**，stderr **恰 1 行**汇总
  - CI 原样命令 `uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog`（**无 `PYTHONPATH`**）→ **exit 0**（确认 CI 形态可用，非只在本地成立）
  - `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` → **30 passed, 0 failed**
  - **变异验证 ×3**（详见关键点 1/3）
  - 自建 `/tmp` 隔离探针 ×2（归档无 review、归档 spec 漂移）

## Tasks Verification

| # | 任务 | 状态 | 证据（文件:行号） |
|---|------|------|------------------|
| 0 | 跑设计追问，产出 grill-design.md（≥3 决策 + 停轮确认） | ✅ | `reviews/grill-design.md`：6 条 Confirmed Decisions + Q1–Q5 各带「用户答复 + 确认时间: 2026-09-22」 |
| 1 | `verify_review_manifest` 的 `tasks_hash` 加 `not archived` 前置，其余校验不动 | ✅ | `agent/workflow/review_manifest.py:175`；`spec_hash` :177、`report_hash` :166、字段 :154-161、存在性 :143、git span :179-180 均未变（diff 仅 1 行逻辑 + 6 行注释） |
| 2 | 可见输出落调用方、按 change 计数汇总一行到 stderr、note 不进返回值、签名不变 | ✅ | `scripts/check_openspec_artifacts.py:1428,1438-1439,1442-1447`；`verify_review_manifest` 签名仍返回 `list[str]`（:135-176 无 note 追加） |
| 3 | CI `validate` job 增 step（参数钉死 3 个） | ✅ | `.github/workflows/ci.yml:64-71` |
| 4 | `docs/development-guide.md` 立「manifest 在 tasks.md 最终化后生成」纪律 | ✅ | `docs/development-guide.md:251-266`（含反例说明 :256、归档后勿编辑 :258、命令 :262-265） |
| 5 | 保留盲区 A 全部行为 | ✅ | `tests/test_workflow_archive_write_channel.py` + `tests/test_workflow_protected_write_channel.py` 25 passed；`write_review_manifest(..., archived=)` 路径未改 |
| 6 | 归档态 tasks 漂移 → 无错 | ✅ | `tests/agent/workflow/test_review_manifest.py::test_archived_tasks_hash_drift_is_not_an_error` |
| 7 | 同输入 active 态 → `tasks hash mismatch`（判别性对照） | ✅ | `...::test_same_tasks_drift_is_rejected_in_active_context`；变异 2a 下实跑转红 |
| 8 | 归档态 `spec_hash` 漂移仍报错 | ✅ | `...::test_archived_spec_hash_drift_is_still_rejected` |
| 9 | 归档态 `report_hash` 漂移仍报错 | ✅ | `...::test_archived_report_hash_drift_is_still_rejected` |
| 10 | 归档态缺 manifest 仍报错 | ✅ | `...::test_archived_missing_manifest_is_still_rejected` |
| 11 | **改写**既有 `test_verify_review_manifest_archived_path`（不得删断言） | ✅ | 断言数 **2 → 3**（原 :1708 `assert any("tasks hash mismatch"...)` 换成更强的 `assert errors == []` + 新增 `assert any("spec hash mismatch"...)`）——是改写并补判定，非删断言 |
| 12 | 变异验证（去 `not archived` → 归档红；降级扩 active → 对照红；还原变绿） | ✅ | 本审阅独立复现：变异 1 → 3 红；变异 2a → 2 红；还原后 93 passed |
| 13 | 端到端 `--check-archived` 全仓 exit 0 + stderr 恰一行 | ✅ | 实跑 exit 0；`wc -l` = 1；文案 `[archived manifest check] tasks_hash 已按归档语境跳过（43 个 change；其余 hash 与字段仍校验）` |
| 14 | CI 走查：validate job 含 `--check-archived` 且带两个 skip 参数 | ✅ | `.github/workflows/ci.yml:70-71` + `tests/test_openspec_artifact_checker.py::test_ci_validate_job_runs_check_archived` |
| 15 | 回归：两个测试文件 | ✅ | 93 passed |
| 16 | spec delta：补全为变更后完整正文，保留既有 2 条 + 新增 2 条，退役 0 | ✅ | 见关键点 5 的逐条比对（main 2 条 / delta 4 条 / retired 0 / preserved 2） |
| 17 | delta 顺手改措辞删「`head_sha` 匹配当前 `HEAD`」 | ✅ | delta :23 与 main :158 逐字 diff；理由与原始意图落 `docs/known-debt.md`「head_sha 校验口径债」节 |
| 18 | `docs/known-debt.md` 更新 #232 + 残余风险 + head_sha 债 | ✅ | 受保护路径，有 `protected_artifact_explained` 事件（`workflow-events.jsonl` seq 2） |
| 19 | 关键词扫描 docs/AGENTS.md/dev-guide | ✅ | `AGENTS.md:111` 新增归档校验范围段；dev-guide 新增「Review manifest 纪律」节 |
| 20 | 全量 pytest | ✅ | 6 failed / 3041 passed，6 条均为环境相关既有失败（见 Test Results） |
| 21 | OpenSpec strict validate | ✅ | 30 passed / 0 failed |
| 22 | artifact checker（active 模式） | ✅ | `PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` → exit 0 |
| 23 | 端到端验收（issue #232 盲区 B 原文） | ✅ | CI validate job 对归档 change 执行 manifest 校验，全仓 exit 0 |

**未勾选项的合理性**（`tasks.md` 剩余 5 项 + backlog）：全部属**收尾阶段**任务——「当前规格同步」「backlog 登记+移除」「独立审阅（本轮）」「manifest 在 tasks 最终化后生成」「生成 review manifest」「issue #232 收尾 comment」。按仓库流程在归档 PR 内闭环，此刻未勾是正确的，不构成缺失。

## Issues

### 阻塞 / 中等：无

未发现需修复的阻塞或中等问题。核心放宽面（A′）实现最小、判别性有实跑证据、其余校验面零波及。

### 低（观察项，不阻塞，无需本 change 处理）

**L1. 新增 CI 门对「归档时压根没有 `reviews/` 的 change」是盲的——与 spec 措辞「不脱离校验范围」的覆盖度存在口径差**

- 证据：`scripts/check_openspec_artifacts.py:1040-1041` 在 `review_dir` 不存在时直接 `return []`；`requires_building_review` 在 :1027-1032 含 `not archived`，注释 :1024-1026 明写 archived 模式「only verifies that EXISTING manifests still bind their artifacts (drift detection), it does not demand a historical review」。
- 实测（`/tmp` 隔离探针）：造一个 `archive/2026-08-02-no-review/`（`primary: refactor`、tasks 全勾、**无 `reviews/`**）→ `--check-archived` **exit 0**（`OpenSpec artifact checks passed`）。
- 全仓实况：86 个可解析 Change Type 的归档目录中，**43 个有 `*-review.md`（且 43/43 有 manifest，无缺件）**，**42 个非 docs 归档 change 完全没有 review**。
- 性质：**非本 change 引入**（改前 `--check-archived` 根本不进 CI，归档 change 完全无人校验；本 change 是严格收紧）。归档模式「不索取历史 review」是既有代码的显式设计（:1024-1026）。
- 建议（可选，另立 change）：spec 正文若继续用「使 change 归档后不脱离校验范围」这类全称表述，宜补一句覆盖面限定（「对已有 manifest 的归档 change 做漂移校验」），或后续一次收紧为「非 docs 归档 change 必须有 PASS manifest」。**不构成对本 change 的修改要求**——本 change 的 spec Requirement（「CI SHALL 对已归档 change 执行 manifest 校验」）已按其字面与 Scenario 达成。

**L2. `test_ci_validate_job_runs_check_archived` 的断言是「整文件子串匹配」，而非绑定到 step 结构**

- 证据：`tests/test_openspec_artifact_checker.py` 中该测试仅 `assert "--check-archived" in text` + 两个 skip 参数子串存在于 `ci.yml` 全文。
- 局限：不断言三个参数出现在**同一条命令**、不断言位于 `validate` job、不断言无 `continue-on-error`。当前 `ci.yml` 下有效（注：ci.yml 的注释 :68 含两个 skip 参数但**不含** `--check-archived`，故删掉命令行会使断言转红，守卫不至失效），但强度弱于结构断言。
- 严重度：低。真正的门禁有效性已由我在**变异 3 与镜像探针**下实跑证明（见下）。

**L3. 归档跳过计数按「有 manifest」而非「确有 tasks_hash 被跳过」计数**

- 证据：`scripts/check_openspec_artifacts.py:1438-1439` 判据是 `any((change_dir / "reviews").glob("*-review-manifest.json"))`。
- 影响：若某归档 change 有 manifest 但**无对应 `*-review.md`**，verify 根本不会被调用（:1046 循环遍历 report），计数仍 +1 → 轻微高估。全仓实测「manifest 有而 report 无」为 **0 例**，当前无实际影响。
- 严重度：低（文案为「N 个 change」，语义上仍可读作「N 个归档 change 的 manifest 走了降级口径」，不构成误导）。

**L4. `docs/development-guide.md` 与 CI 的命令形态不一致（`PYTHONPATH=. python3` vs `uv run python`）**

- 证据：`docs/development-guide.md:263` 用 `PYTHONPATH=. python3 ...`；`.github/workflows/ci.yml:70` 用 `uv run python ...`（无 `PYTHONPATH`）。
- 实跑两者**均 exit 0**，均可用，非错误。仅提示维护者注意二者并非同一调用形态。
- 严重度：低（纯一致性观察）。

## Test Results

```
# 核心回归（授权范围内必跑）
$ uv run pytest tests/agent/workflow/test_review_manifest.py tests/test_openspec_artifact_checker.py -q
93 passed in 6.13s

$ uv run pytest tests/test_workflow_archive_write_channel.py tests/test_workflow_protected_write_channel.py -q
25 passed in 34.92s

# 端到端（issue #232 B 原文验收）
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
[stderr] [archived manifest check] tasks_hash 已按归档语境跳过（43 个 change；其余 hash 与字段仍校验）
[stdout] OpenSpec artifact checks passed
EXIT=0；stderr 行数 = 1，无 ERROR

# CI 原样形态（无 PYTHONPATH）
$ uv run python scripts/check_openspec_artifacts.py --check-archived --skip-protected-paths --skip-backlog
EXIT=0（与上同）

# OpenSpec
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)

# artifact checker（active 模式，本 change 自身）
$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
OpenSpec artifact checks passed (EXIT=0)

# 全量
$ uv run pytest -q
6 failed, 3041 passed, 10 skipped, 76 warnings in 472.82s
```

**全量 6 条失败的逐条定性（均与本 change 无关，非本 change 回归）**

| 失败用例 | 定性 |
|---|---|
| `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` | 授权范围内已声明：pristine HEAD 也失败（环境相关） |
| `tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan` | 同上 |
| `tests/agent/tools/test_factory_sandbox_wiring.py::TestBuildSandboxFromConfig::test_docker_backend` | 本机**无 docker daemon**（`docker info` 失败）；`git diff --name-only` 显示无 sandbox/factory 相关文件被改 |
| `tests/agent/tools/test_sandbox_backends.py::TestBackendSelection::test_docker_backend_available` | 同上 |
| `tests/web_tests/test_workflow_graph_browser.py::test_collapsed_group_expands_from_the_detail_drawer` | 授权范围内已声明：已知 flake |
| `tests/web_tests/test_workflow_graph_browser.py::test_legend_is_visible_and_collapsible` | 同上 |

## 必须核实的关键点（逐条给证据）

### 1. 判别性对照真实存在且有判别力 —— ✅ 已实跑变异（3 组）

原始状态：`md5(agent/workflow/review_manifest.py) = 86d84fcb6eddf365efcd2cd6d9642b23`。

- **变异 1（去掉 `not archived` 前置）** → `uv run pytest ...` = **3 failed, 90 passed**：
  `test_archived_tasks_hash_drift_is_not_an_error`、`test_verify_review_manifest_archived_path`、`test_check_archived_prints_visible_tasks_hash_skip_summary` 全部转红。
  → 归档侧的 `not archived` 是**载荷性**前置，不是装饰。
- **变异 2a（条件改恒 `False`，把降级扩到 active）** → **2 failed, 91 passed**：
  `test_same_tasks_drift_is_rejected_in_active_context`（新用例，:218 断言失败）+ 既有 `test_tasks_hash_mismatch_is_rejected` 转红。
  → active 对照**有判别力**，锁住「只放宽归档」。
- **变异 3（note 追加进返回值）** → **3 failed, 90 passed**，且端到端复现 A′ 失效：
  `--check-archived` **EXIT=1**，stderr 出现 `ERROR: note: archived change — tasks_hash drift ignored` **共 44 行**。
  → 直接证实 design D2 / grill Q1 的核心论断：note 进返回值即被 `errors.extend` 收走 → 误红。
- **还原**：`git checkout -- agent/workflow/review_manifest.py`，md5 复原为 `86d84fcb…`，`git status --porcelain` 仅剩两个既有 untracked 文件，`:175` 前置完好。

### 2. 端到端 —— ✅

`--check-archived --skip-protected-paths --skip-backlog` → **EXIT=0**；stderr **恰好 1 行**（`tasks_hash 已按归档语境跳过（43 个 change；其余 hash 与字段仍校验）`），无逐 change 刷屏、无 `ERROR:`、无 `WARNING:`。与「放宽前 15 红」的立项实测互补（现 15 条由红转绿，且不作弊——manifest 文件零改写，`git diff --stat` 未见任何 `openspec/changes/archive/**` 改动）。

### 3. 降级说明未混入返回值 —— ✅（结构 + 实跑双重）

- **结构**：`verify_review_manifest`（`review_manifest.py:135-180`）返回路径共 4 处（:143 missing、:147 invalid JSON、末尾 `return errors`），全部是纯错误列表，无 note 追加。
- **唯一降级路径必有可见输出**：全仓只有 `check_openspec_artifacts.py:1434` 以 `archived=True` 调 `_check_review_manifests`，而它处于 `if args.check_archived and not args.change:`（:1425）内，该分支在 `tasks_hash_skipped` > 0 时**必然**打印汇总（:1442-1447）。不存在「降级发生但无可见说明」的路径。
- **实跑**：变异 3 下 note 一进返回值，checker 立刻 **exit 1 + 44 行 ERROR**（见关键点 1）。反向证明落点选择的正确性。

### 4. 既有测试是被改写而非删断言 —— ✅

`tests/test_openspec_artifact_checker.py::test_verify_review_manifest_archived_path`：

- 断言数 **2（origin/master）→ 3（HEAD）**。
- 原 `assert any("tasks hash mismatch" in e for e in errors)`（归档态 tasks 漂移判红）被替换为 `assert errors == []`（**更强**：零错误）**并新增** `assert any("spec hash mismatch" in e for e in errors)`（归档态 spec 漂移仍判红）。
- 无空断言、无 `pass` 占位、无删除式弱化。判别性对照另由 `tests/agent/workflow/test_review_manifest.py` 的 5 条新用例承担（tasks 漂移免错 / active 同输入必红 / spec / report / 缺 manifest）。

### 5. spec delta 完整性 —— ✅（逐条机械比对）

以脚本切分两文件的「Review evidence manifest」Requirement（main `spec.md:140-158`，delta 全文）：

| 项 | 结果 |
|---|---|
| 正式 spec Scenario 数 | **2**：`review report 缺少 manifest`、`manifest 字段和 hash 校验` |
| delta Scenario 数 | **4**：上述 2 条 + `归档 change 的 manifest 校验不因 tasks_hash 漂移而失败` + `active change 的 tasks_hash 漂移仍判失败` |
| 退役 | **0** |
| 新增 | **2**（精确吻合 design D6 修正后的计数；grill 指出的「D6 原写 1，应为 2」已修正） |
| 保留且逐字相同 | 1 条（`review report 缺少 manifest`，归一化后 `identical: True`） |
| 保留但**有意改措辞** | 1 条（`manifest 字段和 hash 校验`）——两处改动**均为本 change 已披露的意图**：① `checker SHALL 验证 report_hash、tasks_hash、spec_hash` → 加「（**已归档** change 除外，见下述归档 Scenario）」（D2）；② 删「`head_sha` 匹配当前 `HEAD`」（D5/Q4）。**无静默删除**。 |

补充：`design.md` D6 称保留的 2 条「逐字相同」，就第 2 条而言措辞上不精确（实为有意修改且已在 D5/Q4 披露），**不影响归档正确性**，也不构成需修复项——但归档前核对 Scenario 数时应按「保留 2 + 新增 2 = 4」而非「逐字相同」来验。

### 6. A′ 只放宽归档 —— ✅

`git diff origin/master...HEAD -- agent/workflow/review_manifest.py` 全部改动就是 1 行条件 + 6 行注释：

- `spec_hash` 校验（:177）**未动**
- `report_hash` 校验（:166）**未动**
- 必填字段校验（:154-161，`REQUIRED_REVIEW_FIELDS`）**未动**
- manifest 存在性（:143）/ JSON 合法性（:145-147）**未动**
- `change_dir_for` 归档解析 **未动**
- `_verify_git_span` 的 `base_sha`/`head_sha` 存在性 + `diff_hash`（:179-180、:209-232）**未动**
- 签名与返回类型 **未动**

端到端侧证：`--check-archived` 对**人为注入 spec 漂移**的归档 change 仍 **exit 1 + `ERROR: spec hash mismatch`**（`/tmp` 隔离探针）；单测侧证：`test_archived_spec_hash_drift_is_still_rejected`、`test_archived_report_hash_drift_is_still_rejected`、`test_archived_missing_manifest_is_still_rejected` 三条守卫（变异 2a 下仍全绿，说明它们独立于 tasks 前置）。

### 7. 盲区 A 未被破坏 —— ✅

`tests/test_workflow_archive_write_channel.py` + `tests/test_workflow_protected_write_channel.py` → **25 passed in 34.92s**。写通道（`write_review_manifest(..., archived=)`、`_after_protected_write`、归档回退、只读投影）代码路径本 change 零改动。

### 附加：CI 完整性（维度 8，重点核实「是否摆设」）—— ✅ 是有效门禁

- 位置：`.github/workflows/ci.yml:64-71`，在**同一个 `validate` job** 内（复用 `fetch-depth: 0` 与已装依赖），不是独立 job。
- **无 `continue-on-error`**、**无 `|| true`**、**无 `if:` 条件绕过**；block 最后一条命令即该 checker，退出码直接决定 step 结果。
- `validate` 是 `scripts/platform-gate.json` 声明的 required status check（`strict: true`，`enforce_admins: true`）→ 红灯**阻塞合入**，且无 admin 绕过。
- **未弱化任何既有门禁**：本 change 纯新增 step，第一步（`--base-ref "$BASE_REF" --require-base`，含受保护路径检查）保持原样；第二步的 `--skip-protected-paths --skip-backlog` 只作用于新 step 自身，避免重复与 CI-only 的 base-ref WARNING，不减少第一步的覆盖面。
- **实证有效性**：`/tmp` 探针两则——归档 change 的 `tasks_hash` 漂移 → exit 0（符合 A′ 设计）；同 change 的 **spec 漂移 → exit 1**（`ERROR: spec hash mismatch`）。即新门**确实会拦**，非摆设。
- 附带说明：第二步因不带 `--change`，也会重跑一遍 active change 检查（`iter_change_dirs` 路径）。属**重复执行**而非削弱；design D4/Q3 已就参数选择做过论证（本地 `master` 可解析故本地看不到的 base-ref WARNING，只在 CI 现形，因此钉死 skip 参数）——处理得当。

## 结论

本 change 以**最小改动面**（1 行逻辑前置 + 调用方 20 行可见性汇总 + 1 个 CI step + 文档纪律）收口 issue #232 盲区 B，且在三个方向上都经得起对抗性检验：

1. **放宽有判别力**——三组变异实跑证明：去掉前置归档用例转红、把降级扩到 active 对照转红、note 混进返回值端到端转红（exit 1 / 44 行 ERROR）。核心机制不是靠单侧断言自证。
2. **不放宽其他任何一维**——`spec_hash` / `report_hash` / 必填字段 / 存在性 / git span / 解析路径全部零改动，且各有独立守卫测试 + 端到端 spec 漂移探针佐证。
3. **不静默、不伪装**——唯一降级路径（`check_openspec_artifacts.py:1434`）结构上必然伴随一行 stderr 汇总；全仓 43 个归档 change 全绿，靠的是语义放宽而非改写历史证据文件（archive 目录零 diff）。

`--check-archived` 全仓 exit 0 且 stderr 恰一行、OpenSpec strict 30/0、核心回归 118 passed、全量仅 6 条环境相关既有失败（2 条已声明环境 + 2 条无 docker daemon + 2 条已知 flake），未发现阻塞或中等问题。

**Verdict: PASS**

（记录三条低severity 观察项 L1–L4 供后续参考，均**不构成本 change 的修改要求**；其中 L1 建议在归档时若沿用「不脱离校验范围」的全称措辞，可考虑补一句覆盖面限定，或另立 change 收紧为非 docs 归档必须有 PASS manifest。）

> **收尾提醒（本 change 自身遵守 D3）**：本报告落盘后，active 语境下 `_check_review_manifests` 的 `glob("*-review.md")` 循环（`scripts/check_openspec_artifacts.py:1046-1050`）会立刻开始要求对应 manifest。故 `building-review-manifest.json` **必须在本 change 的 `tasks.md` 最终化（含归档 move 与剩余收尾勾选）之后**生成，且归档后不得再编辑 `tasks.md` 或本报告（后者受 `report_hash` 强校验）。
