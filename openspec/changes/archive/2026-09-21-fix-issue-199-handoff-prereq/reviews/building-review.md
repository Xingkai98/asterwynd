# Building Review — fix-issue-199-handoff-prereq（第 3 轮 / 封顶轮）

- **Reviewer**: 独立零记忆 subagent（`/review-loop`，issue #90 闭环第 3 轮）
- **审阅对象**：`git diff origin/master...HEAD`
- **base / head**：`origin/master` (`abdcedf`) / HEAD `c32f034`
- **审阅提交序列**：`5fa99aa` 立项 → `3a13ec9` 实现 → `bc5bb16` R1 修复 → `5af5632` 停止跟踪自愈产物 → `0d186fb` 保留 R1 报告 → `d0d3389` **New-1 修复** → `c32f034` R2 报告
- **审阅时间**：2026-09-21
- **前置轮次**：`reviews/building-review-r1.md`（CHANGES_REQUESTED，4 条 Issue）；R2 报告（PASS + 2 条 Low，已随 `c32f034` 落在本文件并被本轮覆盖）
- **本轮任务**：R2 的 PASS 是在 **New-1 未修**状态下给出的；本轮审 **New-1 已修**（`d0d3389`）之后的最终状态

## Verdict

**PASS**

New-1 的修复**正确、不过度、有余量**：既消除了本 change 引入的回归（gen-1 + 路径型 `--change` 的裸 traceback + 半写），也**顺带封住了 R1 问题 4 的仓库外写入缺口**（我独立复现了修复前的逃逸与修复后的封堵，见下）。修复未误伤任何合法调用（全仓 grep 与实测双向确认），未引入新的中等以上问题。R1/R2 的全部 Issue 已收敛，两个 spec delta 无 Scenario 静默丢失，变异验证有判别力，测试全绿。

本轮新发现 **1 条 Low**（`design.md` D6 汇总行计数与退役清单表不一致，属 `d0d3389` 修文时引入的文档内部矛盾）与 **1 条 Low 观察项**（`--change ..` 这一同族词法形态未被 id 前置覆盖；在本仓库不可利用，且 spec delta 对该 Scenario 的措辞本就把拒绝面限定为「绝对路径或含 `/`」）。两条均不阻塞。

### 全部 Issue 收敛总览

| # | 严重程度 | 来源 | 状态 |
|---|---|---|---|
| R1-1 `known-debt.md` 缺本 change 的 `protected_artifact_explained` 事件 | 中 | R1 | **已修复**（隔离仓 `[]` + 反例对照，本轮独立复验） |
| R1-2 `tasks.md` 零勾选短路完成态门禁 | 中 | R1 | **已修复**（25 勾；checker 已对 manifest 生效） |
| R1-3 `review-manifest` 侧 D7 刷新无测试覆盖 | 低 | R1 | **已修复**（本轮变异 M5 变红） |
| R1-4 `--change` 绝对路径可把事件写到仓库外 | 低 | R1 | **已修复**（被 `d0d3389` 的 id 前置一并封住；修复前逃逸/修复后封堵均已实测） |
| R1-5 `git add -A` 误吞自愈产物 | 中 | 主 session | **已修复**（`git ls-files` active 零命中；纪律条目按惯例留到收尾） |
| R2 New-1 D7 刷新对 gen-1 + 路径型目标抛裸 traceback | 低（本 change 引入） | R2 | **已修复并验证**（见下节，含修复前/后对照） |
| R2 New-2 `design.md` D6 退役清单表精度 | 低 | R2 | **已修复**（表已改为 5 改写 / 3 原样，与正文级比对一致）；但修复引入新的汇总行矛盾 → **R3-1** |
| R2 Obs-1 完成态门禁对未全勾 change 的 in-flight 豁免 | 观察 | R2 | 仓库既有设计属性，非本 change 引入，沿用 R2 结论不记缺陷 |
| R3-1 `design.md` D6 汇总行「4 改写 / 4 原样」与表内 5/3 不一致 | 低 | R3 | 新发现，文档精度，不阻塞 |
| R3-2 `--change ..` 未被 id 前置拒绝（同族词法残留） | 低 | R3 | 新发现观察项；本仓库不可利用，且与 spec 措辞一致 |

## New-1 修复复核（本轮核心）

### 修复内容

`scripts/workflow_state.py:869-871`（`_require_change_target` 内，`change_dir = CHANGES_ROOT / change_id` **之前**）：

```python
    if Path(change_id).is_absolute() or "/" in change_id or "\\" in change_id:
        print(f"错误：change id '{change_id}' 非法（应为单段目录名）", file=sys.stderr)
        return None
```

### 结论：修复正确，且覆盖了 New-1 与 R1-4 两个缺口

**证据 1 — 修复前的回归确实存在，且我复现出了 R2 描述的确切形态。** 用 `git show 0d186fb:scripts/workflow_state.py`（New-1 未修）在 gen-1 + 相对路径型目标上运行：

```
# 目标：openspec/changes/group/leg（首事件 initialized 且内嵌 handoff 载荷 + handoff.json）
$ python3 <0d186fb CLI> artifact-event --change group/leg --event-type protected_artifact_explained ...
  File ".../workflow_state.py", line 882, in _flow_refresh_after_event
    _save_handoff(change_dir.name, replay_handoff_projection(change_dir))
  File ".../workflow_state.py", line 224, in _save_handoff
    with open(tmp, "w", encoding="utf-8") as f:
FileNotFoundError: [Errno 2] No such file or directory: 'openspec/changes/leg/handoff.json.tmp'
exit=1
# 半写确认：事件已追加（workflow-events.jsonl 2 行：initialized + protected_artifact_explained），
# 但投影未刷新、命令以未捕获异常退出
```

**证据 2 — 同一输入在 base（`abdcedf`）与 HEAD（`c32f034`）的对照**：

| 输入 | base `abdcedf` | pre-fix HEAD `0d186fb` | **HEAD `c32f034`（本轮）** |
|---|---|---|---|
| `--change group/leg`（gen-1 嵌套，有 `handoff.json`） | exit 0 | **裸 `FileNotFoundError` exit 1（半写）** | **exit 1 +「非法（应为单段目录名）」无 traceback** |
| `--change /tmp/r3-199/.../group/leg`（绝对路径 gen-1） | exit 0 | 同上裸 traceback | **exit 1 + 明确文案** |
| `--change /tmp/evil_pre`（仓库外，有 `proposal.md`） | exit 1（旧 handoff 前置拦住） | **exit 0，并在 `/tmp/evil_pre` 落盘 4 个文件** | **exit 1，`/tmp/evil_pre` 无任何新文件** |

第三行是本轮独立复现的 **R1 问题 4 逃逸**（`/tmp/evil_pre` 修复前被写入 `handoff.json` / `workflow-events.jsonl` / `workflow-state.json`），修复后被同一条前置封住——R2 的「Low / 既有属性 / 可留债」判断因此**被作者主动收敛为已修**，风险净下降。

**证据 3 — 不过度，不误伤合法调用（自己 grep 验证）。** 全仓穷举 `artifact-event` / `review-manifest` 的调用方：

```
$ grep -rn "artifact-event\|review-manifest" . | grep -v "^./.git/"
大仓内命中：scripts/workflow_state.py:16-17（usage 文档）、:1275（子命令定义）
          scripts/workflow_guard.py 白名单正则（匹配子命令名，不校验 --change 取值）
          tests/test_flow_policy.py:137 / :404（guard 策略用例，`--change test` / `--change x`，均为裸 id）
          tests/test_workflow_protected_write_channel.py（全部裸 id）
          四个 legacy 子命令的 known-debt 文本（无 --change 调用）
→ **零个调用方传含 `/` 或绝对路径的 change id**，前置不误伤任何真实路径。
```

归档 change 的写事件路径也不受影响：`check_protected_path_explanations` 扫的是 `openspec/changes/**/workflow-events.jsonl`（`scripts/check_openspec_artifacts.py:1112`），事件的物理位置不限，收尾只需用**裸 id** 在本 change 归档前写 `change_archived`（与 `archive/2026-09-20-fix-issue-191` 的既有做法一致）。

**证据 4 — 三重判定的边界合理（实测穷举）。**

| 输入 id | 结果 | 判定 |
|---|---|---|
| `group/leg` | exit 1「非法（应为单段目录名）」 | 正确（同时含 `/`） |
| `/tmp/.../group/leg` | exit 1「非法」 | 正确（`is_absolute()`） |
| `./group/leg` / `../fixt` / `group//leg` / `openspec/changes/group/leg` | exit 1「非法」 | 正确 |
| `a\b` | exit 1「非法」 | 正确（`\\` 分支；Linux 下 `is_absolute()` 为假，靠显式检查兜住） |
| `group`（存在但无锚点） | exit 1「不是合法 change」 | 正确（走锚点分支） |
| `archive` / `no-such` | exit 1「不存在」 | 正确 |
| `..` | 本仓库 exit 1「不是合法 change」 | **残留词法口子 → R3-2** |

`Path(change_id).is_absolute()` 覆盖根锚定；`"/"` 分支覆盖 `a/b` 这类相对路径（下游 `_save_handoff` 按 `change_dir.name` 重拼会落到不存在父目录）；`"\\"` 分支覆盖 Windows 分隔符（在 POSIX 上 `is_absolute()` 判不出）。三分支均非冗余，无过度拒绝。

**证据 5 — 回归测试有判别力。** 变异 M0（删掉这三行前置）→ `test_artifact_event_rejects_path_bearing_change_id` 变红（`1 failed / 10 passed`，断言 `artifact-event 'group/leg' 应被拒绝` 实际 `returncode == 0`）；还原后 sha256 与变异前一致。该用例同时覆盖两条命令 × 相对/绝对两种路径型 id，并断言「不抛 `Traceback`」。

**证据 6 — 文档同步到位。** `d0d3389` 同提交更新了 `design.md` D7 的「R2 审阅补丁（New-1）」段（`design.md:139`）、spec delta 的「受保护写通道拒绝非法目标」Scenario（`specs/dev-workflow-state-machine/spec.md:73-76`，新增「路径型 `--change`」触发条件与「SHALL NOT 抛出未捕获的 traceback，也 SHALL NOT 写入仓库外路径」）与 `tasks.md:22` 的回归测试项。

## Tasks Verification

`tasks.md` 现状：`- [x]` = **25** / `- [ ]` = **5**。逐条核验（每条带 `文件:行号`）。

### 实现

| # | 任务（`tasks.md` 行） | 状态 | 证据 |
|---|---|---|---|
| 1 | `cmd_artifact_event` 解除 `handoff.json` 硬前置（`:5`） | 已完成 | `scripts/workflow_state.py:979-981` 调 `_require_change_target`；判定体 `:853-882`（id 前置 `:869-871`、目录存在 `:872-875`、两锚点或分支 `:876-881`） |
| 2 | `cmd_review_manifest` 同上（`:6`） | 已完成 | `scripts/workflow_state.py:1008-1010`，复用同一函数 |
| 3 | 抽出共用前置函数、两命令复用（`:7`） | 已完成 | `scripts/workflow_state.py:853-882`；调用点 `:979` / `:1008`；错误文案单点定义 `:870` / `:874` / `:877-880` |
| 4 | 前置保持 `is_workflow_enabled` 之后、原检查同位置（`:8`） | 已完成 | `:973-978`（disabled）→ `:979`（target）；`:1002-1007` → `:1008`。分支序与替换位置均未变（D5） |
| 5 | 成功后调 `_flow_refresh_after_event`（`:9`） | 已完成 | `scripts/workflow_state.py:996`（artifact-event）、`:1032`（review-manifest）；函数体 `:885-893` |
| 6 | 四处 `handoff.json` 引用按 D3 保留 + legacy 注释（`:10`） | 已完成 | 四处均在且各带「为什么」注释：`_cmd_discover_text:367-369`、`cmd_current:543-545`、`cmd_spawn:914-916`、`cmd_validate:1038-1039`；四条均给出当代等价物/不可用理由 + 跟踪 issue #227 |

### 测试

| # | 任务（`tasks.md` 行） | 状态 | 证据 |
|---|---|---|---|
| 7 | 无 handoff + proposal → `artifact-event` exit 0 且事件写入（`:16`） | 已完成 | `tests/test_workflow_protected_write_channel.py:146-156`（冷状态断言 `:149`、事件落盘断言 `:154-156`） |
| 8 | 同条件 → `review-manifest` exit 0 且 manifest 写入（`:17`） | 已完成 | `:159-172`（`verify_review_manifest == []` `:169`、D7 投影断言 `:171-172`） |
| 9 | 老世代（`initialized` + handoff + proposal）→ 两命令 exit 0（`:18`） | 已完成 | `:190-209`；种子 `_seed_gen1_change:60-90`（首事件内嵌 handoff 载荷 `:79`） |
| 10 | 无 proposal 但有 handoff（spawn 形态）→ exit 0（`:19`） | 已完成（部分覆盖） | `:212-223` 覆盖 `artifact-event`；`review-manifest` 未在此形态单独覆盖——同一 `_require_change_target` 单点判定，属可接受省略（R1 已记为观察项，本轮复核同意） |
| 11 | 不存在的 change → exit 1（`:20`） | 已完成 | `:229-242`；并断言错误来自目标检查本身（`:234` / `:242`），保证对「前置被删」有判别力 |
| 12 | 目录存在但两锚点皆无 → exit 1（`:21`） | 已完成 | `:245-264`，附零落盘断言（`:253` 未写事件日志、`:264` 未建 `reviews/`） |
| 13 | 路径型 `--change` → 两命令 exit 1、无裸 traceback（`:22`） | 已完成（本轮新增验证） | `:256-273`，覆盖 2 命令 × 2 种路径型 id，断言 `returncode == 1` + `"非法" in stderr` + `"Traceback" not in stderr` |
| 14 | 写入后 `verify_projection` 为空（`:23`） | 已完成 | `:175-184`；我独立复跑端到端确认 `verify_projection == []` 且 `workflow-state.json` 存在 |
| 15 | 变异验证（`:24`） | 已完成 | 本轮独立重跑 6 组变异，全部有判别力（见 Test Results §3） |
| 16 | 回归 `test_workflow_state_cli.py` + 全量 pytest（`:25`） | 已完成（如实记录） | 三文件 54 passed；全量 2 failed / 3002 passed，2 例均为已知环境失败（见 Test Results §1） |

### 文档

| # | 任务（`tasks.md` 行） | 状态 | 证据 |
|---|---|---|---|
| 17 | `diagnosis.md` 6 章（`:29`） | 已完成 | `diagnosis.md`：Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests 六节齐备 |
| 18 | spec delta 正文补全为变更后完整正文（`:30`） | 已完成 | 程序化逐条比对：`dev-workflow-state-machine` 正式 8 → delta 11；`change-documentation` 正式 3 → delta 4。详见「Spec 对齐」 |
| 19 | `docs/known-debt.md` 新增条目（配事件）（`:31`） | 已完成 | diff +64 行，三个新 H2（#227 / #228 / #229）+ `workflow-events.jsonl` seq 2 `protected_artifact_explained` → `docs/known-debt.md`；隔离仓 `[]`（见 Test Results §4） |
| 20 | 关键词扫描 `docs/` / `AGENTS.md` / `dev-guide`（`:33`） | 已完成 | `grep -rn handoff docs/development-guide.md AGENTS.md CONTEXT.md README.md README_EN.md` 仅命中 `AGENTS.md:89`「旧的四阶段状态机仪式（… handoff.json …）已停用」——口径与实现一致，无本次造成的事实漂移 |
| 21 | 当前规格同步（`:32`，未勾） | 未执行（属收尾） | `openspec/specs/{change-documentation,dev-workflow-state-machine}/spec.md` 未修改，事件日志无 `current_spec_synced`。归档前必须完成 |
| 22 | backlog 移除本 change（`:34`，未勾） | 未执行（属收尾） | 本 change 仍为 `docs/openspec-change-backlog.md`「未实现队列」第 5 号条目（`:104`）；`backlog_updated` 事件已在 seq 1 |
| 23 | 收尾纪律（`:35`，未勾） | 未执行（属收尾，且**必须**遵守） | `git ls-files openspec/changes/ \| grep -E "handoff.json\|workflow-state.json"` → active 零命中，仅 6 条归档历史遗留。我本轮实跑 `flow status` 复现了自愈重建（`?? .../handoff.json`、`?? .../workflow-state.json`），已清理，确认该纪律有实据 |

### 审阅闭环 / 验证

| # | 任务（`tasks.md` 行） | 状态 | 说明 |
|---|---|---|---|
| 24 | 独立 subagent 审阅 → verdict（`:39`） | 已完成 | R1 CHANGES_REQUESTED（保留为 `building-review-r1.md`）→ R2 PASS → **本轮 R3 PASS（终审）** |
| 25 | 生成 review manifest（`:40`，未勾） | 待生成 | 第 3 轮 PASS 后生成。注意 `tasks_hash` 绑定当前 25/30 勾的 `tasks.md`（与 `archive/2026-09-20-fix-issue-191` 的既有惯例一致） |
| 26 | 全量 pytest（`:44`，未勾） | 未勾，判定合理 | 本轮实跑 2 failed / 3002 passed，2 例均为已知环境失败（`/tmp/.git`）。保持未勾符合「不确定项不勾」的纪律 |
| 27 | OpenSpec strict validate（`:45`） | 已完成 | 本轮实跑 `Totals: 30 passed, 0 failed (30 items)` exit=0 |
| 28 | artifact checker（`:46`） | 勾了，当前 exit 1 | `ERROR: ... review manifest missing`。这是完成态门禁打开后的**正确中间态**（R1 修复的直接结果），非虚勾；生成 manifest 后即可复现 |
| 29 | 端到端验收（`:47`） | 已完成 | 本轮独立复现冷状态端到端（**全程不跑 `flow status`**）：两命令 exit 0、`verify_projection == []`、`verify_review_manifest == []`。见 Test Results §5 |
| 30 | `flow status` 反映投影（`:48`） | 已完成 | 实跑输出 `state.phase=planning / sub_state=exploring / source_event_seq=2 / stale=true` |

**结论**：25 个 `[x]` 全部有真实实现，零虚勾；5 个 `[ ]`（`:32` / `:34` / `:35` / `:40` / `:44`）经逐条核对确实全部属归档收尾或终审 PASS 之后的步骤。

## 8 个审阅维度结论

1. **任务逐项验证** — 见上表：25/25 `[x]` 有实现证据，5 项未勾均为收尾/终审后步骤，无虚勾。
2. **正确性** — `_require_change_target:853-882` 与 design D1 + D7 补丁逐字一致；id 前置在 `CHANGE_ROOT / change_id` 之前生效，三重判定边界经 8 种输入穷举验证无冗余、无误伤；6 组变异全部有判别力。**New-1 修复正确，无过度拒绝。**
3. **Spec 对齐** — 见下节，程序化比对：11 条 delta Scenario = 8 条既有全部保留（5 条改写、3 条逐字相同）+ 3 条新增；`change-documentation` 4 = 3 保留 + 1 新增；Requirement 级正文新增 3 句规范性语句、零删除。
4. **冗余度** — `_require_change_target` 与 `_flow_require_change:768-776` 的**有意分叉**成立：后者以 `workflow-events.jsonl` 为前置，而首次 `artifact-event` 恰是创建该文件的动作（自锁），`design.md:41` 已论证，代码 docstring `:857-860` 亦写明。未引入 `_flow_is_gen1` 分支，理由见 `design.md:50`。判定单点、两命令复用，无重复实现。
5. **测试覆盖与判别力** — 6 组变异全部有判别力（R1-3 的缺口在 M5 下已变红，New-1 在 M0 下已变红）；冷状态构造约束（模块 docstring `:1-15`）严格执行，无「恒绿」用例。
6. **安全性** — 锚点放宽后仍拒绝不存在目录、两锚点皆无的目录与路径型 id；R1-4 的仓库外写入缺口**已被封堵并实测**（修复前 `--change /tmp/evil_pre` 落盘 4 个文件、修复后零落盘）；受保护路径解释事件的校验逻辑未改；`docs/` 与 `openspec/changes/archive/` 门禁面零改动。残留 `..` 词法口子记为 R3-2（本仓库不可利用）。
7. **可维护性** — 四处 legacy 注释（`:367-369` / `:543-545` / `:914-916` / `:1038-1039`）均解释「为什么」（停用状态机、当代等价物、为何本次不改、跟踪 issue 号），非复述「是什么」；`_require_change_target` docstring 解释了「为何用 `proposal.md` 而非事件日志」「为何保留 `handoff.json` 分支」，新增的 id 前置注释解释了「为何必须拒绝路径型 id」（下游 `_save_handoff` 按 `change_dir.name` 重拼）。命名与文件既有风格一致。
8. **CI 完整性** — 本 change 的两个受保护 artifact 改动均有属于**本 change 自己的**结构化事件：隔离仓（只放本 change 的 `workflow-events.jsonl` + `flow-policy.json`）跑 `check_protected_path_explanations` 对 `docs/known-debt.md` 与 `docs/openspec-change-backlog.md` 均返回 `[]`，删掉 seq 2 后立刻报 error（反例对照成立）；真实仓库按 `git diff --name-only abdcedf...HEAD` 全量跑亦为 `[]`。`git diff abdcedf...HEAD -- AGENTS.md scripts/workflow_guard.py scripts/flow-policy.json .github/` 为空（guard 白名单、策略表、CI 配置零改动，与 `proposal.md:40` 的非目标一致）。

### Spec 对齐（独立核实，不只看 delta 自己）

程序化按 `### Requirement` / `#### Scenario` 结构 + 正文级逐行比对 delta 与正式 spec：

```
===== dev-workflow-state-machine =====
  Requirement: 工作流事件日志与 handoff.json projection
    formal (8) / delta (11)
    逐行正文完全一致 (3): 当代 change 投影为 workflow-state.json / 老世代 change 仍可投影 / 任意 change 可查询状态
    正文按两代口径改写 (3): agent 读取当前状态 / WorkflowEngine 更新状态 / 非状态 artifact 事件
    改名 + 改写 (2): 新建 change 时初始化 workflow event log 和 handoff.json
                    → 新建 change 时初始化 workflow event log
                    handoff.json 被手动篡改 → 投影被手动篡改
    新增 (3): 受保护写通道不要求 handoff.json / 受保护写通道拒绝非法目标 /
              老世代 change 的受保护写通道保持可用
    → 无 Scenario 因 delta 缺省而静默消失（2 条改名项正是 design.md:116-126 退役清单显式列出的）
  Requirement 正文级：+3 句新增规范性语句（前置 SHALL 接受 proposal.md 或 handoff.json /
    两条命令 SHALL NOT 要求 handoff.json / 写入后 SHALL 重新生成投影），-0 句
===== change-documentation =====
  Requirement: Handoff state file artifact
    formal (3) / delta (4)：3 条既有全部保留（「handoff.json is created with the change」等
    按老世代口径限定）+ 1 条新增（当代 change 不要求 handoff.json）
    dropped: []
```

两条新增 Scenario 的正文与 `tasks.md` 的测试项一一对应（「受保护写通道不要求 handoff.json」↔ `tests/test_workflow_protected_write_channel.py:146-172`；「受保护写通道拒绝非法目标」↔ `:229-284`；「老世代…保持可用」↔ `:190-223`）。d0d3389 对「拒绝非法目标」Scenario 的补写（路径型 `--change` + 不抛 traceback + 不写仓库外）与实现 + 回归测试三者一致。

## Issues

### R3-1（低，文档精度·`d0d3389` 引入）— `design.md` D6 汇总行与退役清单表计数不一致

`design.md:129` 的汇总行写「既有 8 条**全部保留**（其中 **4 条**按两代口径改写、**4 条**原样）」，而同一节的退役清单表（`design.md:116-126`）实际是 **5 改写 / 3 原样**：

```
rows: 8  改写: 5  原样: 3
  改写 - 新建 change 时初始化 workflow event log 和 handoff.json
  改写 - agent 读取当前状态
  改写 - WorkflowEngine 更新状态
  改写 - handoff.json 被手动篡改
  改写 - 非状态 artifact 事件
  原样 - 当代 change 投影为 workflow-state.json
  原样 - 老世代 change 仍可投影
  原样 - 任意 change 可查询状态
```

**表是对的、汇总行是错的**：正文级比对显示只有后 3 条与正式 spec 逐行完全相同，另 5 条（含 2 条改名）均被改写——与 R2 的 New-2 结论一致。`d0d3389` 把表从「2 改写」修正为「5 改写」时漏改了汇总行（该行是同一提交新增的），属笔误级不一致。**影响**：纯文档，无功能影响，delta 本身超集安全。**建议**：收尾时把汇总行改为「其中 5 条按两代口径改写（含 2 条改名）、3 条逐字保留」。

### R3-2（低，观察项）— `--change ..` 未被 id 前置拒绝

**实测**（scratch 仓，`openspec/proposal.md` 存在）：

```
$ python3 scripts/workflow_state.py artifact-event --change .. --event-type protected_artifact_explained ...
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)      exit=0
$ find <root> -maxdepth 3 -type f
<root>/openspec/handoff.json
<root>/openspec/proposal.md
<root>/openspec/workflow-events.jsonl
<root>/openspec/workflow-state.json
```

`Path("..").is_absolute()` 为假、`..` 不含 `/`，故未被前置拦下；`CHANGES_ROOT / ".."` 词法上落到 `openspec/`，锚点相对该目录解析，命中 `openspec/proposal.md` 后放行，事件与投影落在 `openspec/`（change 目录树之外）。

**为何是 Low 而非缺陷**：
- **本仓库不可利用**：`openspec/proposal.md` 与 `openspec/handoff.json` 均不存在（实测 `--change ..` → exit 1「不是合法 change」），要触发必须先往 `openspec/` 放一个异常文件。
- **非本次引入**：base（`abdcedf`）同一 scratch 输入同样 exit 0（我实测确认），D1/D7 未使其变差。
- **与 spec 口径一致**：delta 的「受保护写通道拒绝非法目标」Scenario 把拒绝面显式限定为「绝对路径或含 `/`，非单段 change id」，`..` 不在声明的范围内，实现与规格无矛盾。
- **危害面小**：`..` 落点在仓库内（`openspec/`），且需前置异常文件；最坏的仓库外逃逸（绝对路径）已被 R1-4 的修复封死。

**建议**（可并入 #228/#229 同族债务，或收尾顺手加）：把前置改为词法白名单——`Path(change_id).name == change_id and change_id not in {".", ".."}`，一行收敛全部单段目录名之外的形态。

## Test Results

环境准备：`export PATH=/home/happy/.local/bin:$PATH`；所有 scratch 均在 `/tmp/r3-199/` 下，未污染仓库。

### 1. 目标测试与全量回归

```
$ uv run pytest tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py tests/test_workflow_guard.py -q
54 passed in 43.58s

$ uv run pytest -q
2 failed, 3002 passed, 9 skipped, 76 warnings in 348.46s (0:05:48)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
```

- 两例均为**已知环境失败**（环境存在 `/tmp/.git` 导致向上扫描误判），base 已复现，与本 change 无关，不计缺陷。
- 浏览器用例（`test_multi_session_browser.py` / `test_workflow_graph_browser.py`）本轮全绿，未出现 flaky。

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)          exit=0

$ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
ERROR: fix-issue-199-handoff-prereq: review manifest missing:
       openspec/changes/fix-issue-199-handoff-prereq/reviews/building-review-manifest.json    exit=1
```

checker 的 exit 1 是**完成态门禁已生效**的正确中间态（R1 Issue 2 修复的直接结果）；生成 manifest 后应转 `OpenSpec artifact checks passed`。

### 2. 变异验证（本轮独立执行；每组跑完均还原并核对 sha256）

变异前 sha256：`1de2ff4951336b4981b89244712c6d0e1e1a98e340eaf6dce666d3353bf475cb`
全部变异结束后再次核对 = **同一值**；`git status --porcelain` 为空；`diff` 与备份逐字节相同。

| # | 变异 | 结果 | 判定 |
|---|---|---|---|
| **M0** | 删掉 `_require_change_target:869-871` 的 id 合法性前置 | **1 failed / 10 passed**：`test_artifact_event_rejects_path_bearing_change_id` | **充分** —— New-1 的回归面被锁住（R3 核心验证） |
| M1 | 前置改回硬要求 `handoff.json` | **7 failed / 4 passed**：`works_without_handoff_json` ×2、`refreshes_projection`、`rejects_unknown_change` ×2、`rejects_dir_without_proposal_or_handoff` ×2 | 充分 |
| M2 | 前置整个去掉（`return CHANGES_ROOT / change_id`） | **5 failed / 6 passed**：两个 `rejects_unknown_change`、两个 `rejects_dir_without_proposal_or_handoff`、`rejects_path_bearing_change_id` | 充分（D5 锚点与 id 前置均被锁住） |
| M3 | 去掉 `handoff.json` 兼容分支（只认 `proposal.md`） | **1 failed**：`test_spawn_style_child_without_proposal_still_writable` | 充分（Q1 回归面被锁住） |
| M4 | 同时删掉两条命令的 `_flow_refresh_after_event` 调用 | **2 failed**：`test_review_manifest_works_without_handoff_json`、`test_artifact_event_refreshes_projection_without_flow_status` | 充分 |
| M5 | 只删 `cmd_review_manifest` 侧的刷新（`:1032`） | **1 failed**：`test_review_manifest_works_without_handoff_json`（`:171` 断言假） | 充分（R1-3 判别力缺口确已补齐） |

> 注：M4 首轮脚本用「替换全部 2 处 `_flow_refresh_after_event(change_dir)` 行」的口径失败（文件内共 6 处调用），已改为按调用点上下文精确匹配后重跑，结果如上表（其余 4 处为 `flow advance/block/confirm/approve` 的既有调用，不在本 change 范围）。

### 3. 冷状态端到端验收（issue #199 验收原文，全程**不跑 `flow status`**）

```
$ cd /tmp/r3-199/e2e   # openspec/changes/e2e-cold/ = proposal.md + reviews/building-review.md + tasks.md + change_created 首事件
handoff.json exists before: NO
$ python3 <repo>/scripts/workflow_state.py artifact-event --change e2e-cold \
    --event-type protected_artifact_explained --artifact-path docs/known-debt.md --reason "e2e cold R3" --approved-by human
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)      exit=0
$ python3 <repo>/scripts/workflow_state.py review-manifest --change e2e-cold --phase building \
    --reviewer-run-id r3 --base-sha deadbeef --head-sha deadbeef
已写入 review manifest: .../e2e-cold/reviews/building-review-manifest.json   exit=0
verify_projection          -> []
verify_review_manifest     -> []
workflow-state.json exists -> True
```

### 4. 隔离验证（维度 8 / R1-1 复验）

```
# 只把本 change 的 workflow-events.jsonl + scripts/flow-policy.json 放进隔离仓
isolated (only this change's event log):
  docs/known-debt.md                 -> []
  docs/openspec-change-backlog.md    -> []
  event types: ['backlog_updated', 'protected_artifact_explained']

# 反例：删掉 seq 2 后同一隔离仓
  docs/known-debt.md -> ['protected path `docs/known-debt.md` changed without workflow event explanation']

# 真实仓库（changed_paths = git diff --name-only abdcedf...HEAD）
  all changed -> []      known-debt only -> []      backlog only -> []
```

→ 两个受保护路径的 `[]` 是本 change 自己的 seq 1/seq 2 挣来的（反例对照成立），不再依赖其它归档 change 的兜底事件。

### 5. New-1 前后对照（本轮核心证据，命令与输出摘要）

见上文「New-1 修复复核」证据 1/2/3 三张表。关键三条：

```
base   abdcedf : --change group/leg                          -> exit 0
pre-fix 0d186fb: --change group/leg                          -> FileNotFoundError 裸 traceback, exit 1（事件已半写）
HEAD   c32f034 : --change group/leg                          -> 错误：change id 'group/leg' 非法（应为单段目录名）, exit 1
base   abdcedf : --change /tmp/r3-199/.../group/leg          -> exit 0
HEAD   c32f034 : --change /tmp/r3-199/.../group/leg          -> exit 1，无 traceback
pre-fix 0d186fb: --change /tmp/evil_pre（仓外,有 proposal）  -> exit 0 且仓外落盘 4 个文件
HEAD   c32f034 : --change /tmp/evil_pre                      -> exit 1，仓外零落盘
```

### 6. 其他实跑

```
$ python3 scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq
{"schema":"workflow-state/v1","change_id":"fix-issue-199-handoff-prereq",
 "state":{"phase":"planning","sub_state":"exploring"},"milestones":[],
 "source_event_seq":2,"stale":true}                      # stale=true 是投影文件在冷 worktree 不存在所致，非缺陷

$ git ls-files openspec/changes/ | grep -E "handoff.json|workflow-state.json"
（active change 零命中；仅 6 条归档历史遗留）
```

**工作树完整性**：本轮所有变异、探测、端到端产物均已还原/清理——我因实跑 `flow status` 产生的两个自愈产物（`openspec/changes/fix-issue-199-handoff-prereq/{handoff.json,workflow-state.json}`）已删除；`scripts/workflow_state.py` sha256 = `1de2ff49…` 与审阅开始时一致；`git status --porcelain` 为空。（**收尾提醒**：`write` 通道与 `flow status` 都会重建这两个文件，归档提交务必按 `tasks.md:35` 的纪律显式列路径，勿用 `git add -A`。）

## 结论

**New-1 的修复正确、不过度，且比修复要求做得更多**：新增的 id 合法性前置（`scripts/workflow_state.py:869-871`）同时收敛了两个同源缺口——R2 的 New-1（gen-1 + 路径型 `--change` 的裸 traceback 与半写，我复现了确切形态并在修复后确认消失）与 R1 的问题 4（绝对路径可把受保护事件写到仓库外，我复现了修复前的仓外落盘与修复后的零落盘）。全仓 grep + 8 种 id 形态穷举 + 6 组变异共同确认修复不误伤任何合法调用、无冗余判定、判别力充分。回归测试 `test_artifact_event_rejects_path_bearing_change_id` 对「删掉该前置」变红。

R1 的 5 条（含主 session 新发现）与 R2 的 2 条 Low 逐条收敛到位并独立复验：R1-1 用隔离仓 + 反例对照证明事件自证；R1-2 勾选后 checker 已对 manifest 生效（当前 exit 1 是门禁生效的正确中间态）；R1-3 经 M5 变红；R1-5 经 `git ls-files` 与自愈复现双向确认；R2 New-2 的表已修正。spec delta 经结构 + 正文级 + Requirement 级三重独立比对，无 Scenario 静默丢失、无规范性语句被无意删除。

新发现两条 **Low**（R3-1 `design.md` D6 汇总行计数笔误；R3-2 `--change ..` 词法残留，本仓库不可利用且与 spec 措辞一致）——均不阻塞，建议收尾时顺手改文 / 归并入 #228 同族债务。

**Verdict: PASS**（终审，第 3 轮封顶）。

收尾待办（不属缺陷，按 `tasks.md` 未勾项）：`:32` 当前规格同步（`current_spec_synced` ×2）、`:34` backlog 移除（`backlog_updated`）、`:35` 收尾纪律（禁 `git add -A`）、`:40` 生成 review manifest（绑定 base `abdcedf` / head `c32f034` 或收尾 head）、`:44` 全量 pytest 重跑确认。
