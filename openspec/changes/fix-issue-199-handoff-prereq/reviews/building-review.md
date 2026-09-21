# Building Review — fix-issue-199-handoff-prereq（第 2 轮 / 最终）

- **Reviewer**: 独立零记忆 subagent（`/review-loop`，issue #90 闭环第 2 轮）
- **审阅对象**：`git diff origin/master...HEAD`（`5fa99aa` 立项 / `3a13ec9` 实现 / `bc5bb16` R1 修复 / `5af5632` 停止跟踪自愈产物 / `0d186fb` 保留 R1 报告）
- **base / head**：`origin/master` (abdcedf) / `0d186fb`
- **审阅时间**：2026-09-21
- **上一轮**：`reviews/building-review-r1.md`（CHANGES_REQUESTED，4 条 Issue）

## Verdict

**PASS**

R1 的 4 条 Issue 与主 session 新发现的第 5 条全部修复到位，且修复本身未引入中等以上新问题。本轮独立复跑了全部维度（任务逐项核验、正确性、spec 对齐、冗余度、变异判别力、安全、可维护性、CI 完整性），并额外发现 **2 条 Low 级新问题**（D7 刷新对 `gen-1 + 带斜杠/绝对路径目标` 引入未捕获异常；design D6 退役清单少列 2 条改写项）——均不阻塞，已在下文给出证据与建议。

判定依据（issues 全览）：

| # | 严重程度 | 状态 |
|---|---|---|
| R1-1 `known-debt` 缺本 change 事件 | 中 | **已修复**（隔离验证 `[]` + 反例对照） |
| R1-2 `tasks.md` 0 勾选关闭完成态门禁 | 中 | **已修复**（24 勾；门禁对 manifest 已生效） |
| R1-3 `review-manifest` 侧 D7 刷新无测试覆盖 | 低 | **已修复**（确认 B：变异红、还原 sha 一致） |
| R1-4 `--change` 绝对路径可写仓库外 | 低 | **未修，属既有属性**，已显式记债；但发现同族新增回归，见 New-1 |
| R1-5 `git add -A` 误吞自愈产物 | 中 | **已修复**（`git ls-files` 零命中；tasks.md 加收尾纪律项） |
| New-1 D7 刷新在 gen-1 + 非裸 id 目标上抛裸 traceback | 低 | 新发现，建议修但不阻塞 |
| New-2 design D6 退役清单漏列 2 条改写项 | 低 | 文档精度问题，不影响 delta 正确性 |
| Obs-1 完成态门禁的 in-flight 豁免仍在（见「问题 2 复核」） | 观察 | 仓库既有设计属性，非本 change 引入 |

## 问题 1–5 逐条复核（主 session 指定）

### 问题 1（R1 Issue 1）：本 change 的 `workflow-events.jsonl` 未覆盖 `docs/known-debt.md` → **已修复**

- 事件现状：`openspec/changes/fix-issue-199-handoff-prereq/workflow-events.jsonl` 现为 2 行。seq 2 = `protected_artifact_explained` → `docs/known-debt.md`，`approved_by: human`，字段集为 `[approved_by, artifact_path, change_id, event_type, reason, schema, seq]`（与 `append_protected_artifact_event` 写入的键完全一致，`agent/workflow/event_log.py:170-189`）。
- **隔离验证**（把本 change 的事件日志 + `scripts/flow-policy.json` 单独放进 `/tmp/iso199`，排除其它 change 的归档事件）：

  ```
  isolated (only this change's event log):
     docs/known-debt.md              -> []
     docs/openspec-change-backlog.md -> []
     event types: ['backlog_updated', 'protected_artifact_explained']
  ```

- **反例对照**（删掉 seq 2 后同一隔离仓）：

  ```
  isolated WITHOUT seq2 -> ['protected path `docs/known-debt.md` changed without workflow event explanation']
  ```

  → 证明现在的 `[]` 是本 change 自己的 seq 2 事件挣来的，**不再依赖别的 change 兜底**。
- 真实仓库全量：`check_protected_path_explanations(repo_root, changed_paths=<git diff --name-only origin/master...HEAD>)` → `[]`；受保护候选路径只有 `docs/known-debt.md` 与 `docs/openspec-change-backlog.md` 两个，两者分别单独跑也都是 `[]`。

### 问题 2（R1 Issue 2）：`tasks.md` 0 勾选短路完成态门禁 → **已修复，但门禁只开了一半（如实报告）**

- 勾选现状：`- [x]` = **24**，`- [ ]` = **5**（`tasks.md:31` 当前规格同步 / `:33` backlog 移除 / `:34` 收尾纪律 / `:39` review manifest / `:43` 全量 pytest）。未勾的 5 项经逐条核对**确实全部属归档收尾或第 2 轮之后**，无虚勾。
- **实跑门禁状态**（`scripts/check_openspec_artifacts.py:1027-1032` 的 `requires_building_review` 依赖 `_tasks_all_complete`，而后者要求 `unchecked == 0`，`:982-1000`）：

  ```
  # 1) 当前状态（三个 review 文件都在）
  $ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
  ERROR: fix-issue-199-handoff-prereq: review manifest missing:
         openspec/changes/fix-issue-199-handoff-prereq/reviews/building-review-manifest.json
  exit=1

  # 2) 临时移走 reviews/building-review.md
  $ PYTHONPATH=. python3 scripts/check_openspec_artifacts.py
  OpenSpec artifact checks passed
  exit=0
  ```

- **明确结论（不做想当然）**：当前 `_tasks_all_complete == False`（因 5 项未勾），故 `requires_building_review` **仍为假**，`building-review.md` 缺失不会被 `:1034-1038` 拦下；但 `:1048-1050` 的 manifest 校验循环**不看** `_tasks_all_complete`，只要 `reviews/*-review.md` 存在就逐条 `verify_review_manifest`——所以**基线（当前）状态 checker 会因缺 manifest 而 FAIL**。即 R1 Issue 2 的核心症状（「删掉报告即可零审阅证据合入」当初的实测）在**门禁语义上已恢复**：本 change 现在必须有 PASS manifest 才能过。
- **我独立验证「门禁在 tasks 全勾时确实会打开」**（隔离副本 `/tmp/gate199`，把 5 项也勾上并删掉 `building-review.md`）：

  ```
  checked=29 unchecked=0
  ERROR: fix-issue-199-handoff-prereq: building-review.md missing — 独立 subagent 审阅未运行。
  exit=1
  ```
  → 强制审阅门禁的触发条件本身工作正常。
- **Obs-1（观察，非缺陷）**：由于 `:34` 的收尾纪律项与 `:39` 的 manifest 项按惯例在归档时也不勾（对照 `openspec/changes/archive/2026-09-20-fix-issue-191/tasks.md`：28 勾 / 6 未勾，归档时仍未勾），`requires_building_review` 对本 change 大概率**终其一生不触发**；实际把门的仍是「manifest 存在 + `verify_review_manifest` 通过」这条路径。这是仓库既有设计属性（`:1018-1026` 注释明确写了「partially-implemented changes must not be flagged」），**不是本 change 引入的缺陷**；建议后续单独记一条债务收紧（例如把「删掉 review 报告即可绕过」写成守卫条件），不在本 change 范围内。

### 问题 3（R1 Issue 3）：`review-manifest` 侧 D7 刷新无测试覆盖 → **已修复（见确认 B）**

修复内容为 `tests/test_workflow_protected_write_channel.py:171-172` 增加两行断言：

```python
    # D7 同样覆盖 review-manifest 这条命令：写入后投影即新鲜（删除该刷新会让本断言变红）
    assert (change_dir / "workflow-state.json").exists()
    assert verify_projection(change_dir) == []
```

变异验证见「确认 B」——判别力已实测成立。

### 问题 4（R1 Issue 4）：`--change` 传绝对路径可把事件写到仓库外 → **未修（既有属性），但发现同族的新增回归（New-1）**

- **绝对路径 + gen-2 目标**：仍可写到仓库外（与 base 行为一致，非本次引入）：

  ```
  $ python3 scripts/workflow_state.py artifact-event --change /tmp/ext199b ...   # /tmp/ext199b 有 proposal.md
  已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)   exit=0
  $ ls /tmp/ext199b
  handoff.json  proposal.md  workflow-events.jsonl  workflow-state.json
  ```
  根因仍在 `scripts/workflow_state.py:865` 的 `CHANGES_ROOT / change_id`（`pathlib` 对绝对路径整体替换）。R1 判定为 Low / 既有属性 / 可留债务，我复核后**同意**：base 提交 `5fa99aa:scripts/workflow_state.py:936-941` 使用同一拼接方式，D1 未使其变差。
- **`..` 遍历不可用**（我实测补充）：`--change ../outside199` 被拒（`openspec/changes/../outside199` 不存在，`pathlib` 不做词法归一化）→ exit 1，不构成独立的新攻击面。
- **New-1（新发现，低）**：见 Issues。

### 问题 5（主 session 新发现）：R1 提交误吞 `handoff.json` / `workflow-state.json` → **已修复**

- `5af5632` 已 `git rm --cached` 二者并删工作区文件；`0d186fb` 之后的工作树干净。
- **独立复核（`git ls-files`）**：

  ```
  $ git ls-files openspec/changes/ | grep -E "handoff.json|workflow-state.json"
  openspec/changes/archive/2026-07-08-multi-agent-dev-workflow/handoff.json
  openspec/changes/archive/2026-07-09-refactor-cli-entry-point-for-pypi/handoff.json
  openspec/changes/archive/2026-07-14-add-workflow-automation/handoff.json
  openspec/changes/archive/2026-07-31-add-workspace-param/handoff.json
  openspec/changes/archive/2026-08-15-flow-event-projection/handoff.json
  openspec/changes/archive/2026-08-15-flow-event-projection/workflow-state.json
  ```
  → **active change 下零命中**，只剩 6 条归档历史遗留（与 design.md:68 的口径限定一致）。
- `tasks.md:34` 已加收尾纪律条目（禁 `git add -A`/`git add .`，只显式列路径），且该条目**保持未勾**——正确，它属收尾阶段。
- 我实跑复现了该纪律的必要性：`uv run python scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq` 后 `git status --short` 立刻出现

  ```
  ?? openspec/changes/fix-issue-199-handoff-prereq/handoff.json
  ?? openspec/changes/fix-issue-199-handoff-prereq/workflow-state.json
  ```
  → 自愈产物确实会被重建，纪律条目有实据。（我已删除这两个我自己的实跑产物，工作树恢复为无未跟踪文件、无 tracked 改动。）
- **补充观察**：D7 新增的 `_flow_refresh_after_event`（`:989` / `:1025`）经 `_refresh_workflow_state`（`:889-903`）在每次写事件后**同时写 `workflow-state.json` 与 `handoff.json`**，即**写通道自己成了这两个未跟踪产物的生产者**——这正是 R1-5 事故的直接机制。该耦合已在 `docs/known-debt.md` 的 #228 三层债务里记明（自愈产出退役 artifact / 协议层必填 / 未 gitignore），本 change 不修属正确边界；但收尾时若有人再跑一次写通道命令，产物会重新出现，**收尾纪律条目必须遵守**。

## 确认 A / 确认 B（主 session 指定）

### 确认 A：seq 2 事件由**修好的 CLI** 写入，非绕底层函数 → **确认为真**

依据（四条互相独立，逐条可复现）：

1. **旧 CLI 不可能产出该事件**（决定性证据）：base `5fa99aa:scripts/workflow_state.py` 的 `cmd_artifact_event`（`:936-941`）与 `cmd_review_manifest`（`:964-970`）仍是硬前置 `if not (change_dir / "handoff.json").exists(): ... return 1`。该 change 目录的 `handoff.json` 从未被 git 跟踪（本报告问题 5 的 `git ls-files` 输出可证），所以旧 CLI 只会输出 `错误：change 'fix-issue-199-handoff-prereq' 没有 handoff.json` 并 exit 1，**无法追加 seq 2**。我用 base 版脚本在冷状态复现了该错误：

   ```
   $ python3 <base 5fa99aa workflow_state.py> artifact-event --change pre199 ...
   错误：change 'pre199' 没有 handoff.json        exit=1
   ```
2. **命令原文与结果**：本 worktree 的开发会话转录中，工具调用（`.claude/projects/-home-happy--paseo-worktrees-0frj3kg8-fix-issue-199-handoff-prereq-2026-09-21/0389765d-…jsonl` 第 495→496 条）为

   ```
   uv run python scripts/workflow_state.py artifact-event \
     --change fix-issue-199-handoff-prereq \
     --event-type protected_artifact_explained \
     --artifact-path docs/known-debt.md \
     --reason "fix-issue-199 收尾：在 known-debt.md 新增三条债务条目（issue #227 … / #228 … / #229 …）…" \
     --approved-by human
   ```
   紧接的结果为 `已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)` / `EXIT=0`，且同一命令紧接着列出 `2 protected_artifact_explained -> docs/known-debt.md`。
3. **事件载荷是 CLI 参数的字面产物**：程序化比对 `event["reason"] == 上述 --reason 字符串` → **True**（逐字节相同），`approved_by == "human"`、`artifact_path == "docs/known-debt.md"`、`seq == 2`（与 `_append_event` 的 `len(existing)+1` 语义一致）。
4. **无绕底层函数证据**：全转录（含 subagents）中 `append_protected_artifact_event` 只出现在 `grep` 与文件阅读里，**没有任何 `python -c "...append_protected_artifact_event(...)"` 直接调用**；提交历史 `scripts/` 侧也只有 `3a13ec9` / `bc5bb16` 两次改动，无临时绕过脚本。

结论：seq 2 是本次修复后的 `workflow_state.py artifact-event` CLI 写入的（dogfooding 成立），不是绕底层函数。

### 确认 B：重跑变异验证 `cmd_review_manifest` 侧 `_flow_refresh_after_event` → **变红，还原后 sha256 一致**

命令与结果（完整实录）：

```
$ cd <worktree>
$ sha256sum scripts/workflow_state.py
544744a054c2d977e5204bbbd6d5888a731b1a930b89087c99bf5e3a58a6aa1d  scripts/workflow_state.py
$ cp scripts/workflow_state.py /tmp/ws_backup_r2.py
$ python3 - <<'PY'   # 只删 scripts/workflow_state.py:1025 的 _flow_refresh_after_event(change_dir)
   （替换 "    _flow_refresh_after_event(change_dir)\n    print(f\"已写入 review manifest: {path}\")"
     → "    print(f\"已写入 review manifest: {path}\")"，断言 count==1）
PY
mutated: removed review-manifest-side refresh
$ uv run pytest tests/test_workflow_protected_write_channel.py -q
FAILED tests/test_workflow_protected_write_channel.py::test_review_manifest_works_without_handoff_json
  E  AssertionError: assert False
  E   +  where False = exists()
  E   +    where exists = (PosixPath('.../openspec/changes/test-change') / 'workflow-state.json').exists
  tests/test_workflow_protected_write_channel.py:171: AssertionError
1 failed, 9 passed in 13.19s
$ cp /tmp/ws_backup_r2.py scripts/workflow_state.py
$ sha256sum scripts/workflow_state.py
544744a054c2d977e5204bbbd6d5888a731b1a930b89087c99bf5e3a58a6aa1d  scripts/workflow_state.py
```

- **变红用例名**：`test_review_manifest_works_without_handoff_json`
- **还原后 sha256 与变异前一致**：是（`544744a054c2d977…` 变异前 = 变异后）
- **工作树无残留**：变异与还原后 `git status --short` 为空（除我稍后自行清理的两次实跑自愈产物）

→ R1 Issue 3 的修复**确实有判别力**，不再是「单独删掉它全绿」。

## Tasks Verification

`tasks.md` 现状：`- [x]` = 24 / `- [ ]` = 5。逐条核验如下（每条带实现证据 `文件:行号`）。

### 实现

| # | 任务（tasks.md 行） | 状态 | 证据 |
|---|---|---|---|
| 1 | `cmd_artifact_event` 解除硬前置（`:5`） | 已完成 | `scripts/workflow_state.py:972-974` 调 `_require_change_target`；判定体 `:853-875`（目录存在 `:866-868`，两锚点或分支 `:869-874`） |
| 2 | `cmd_review_manifest` 同上（`:6`） | 已完成 | `scripts/workflow_state.py:1001-1003`，复用同一函数 |
| 3 | 抽共用前置函数（`:7`） | 已完成 | `scripts/workflow_state.py:853-875`；两处调用点 `:972` / `:1001`；错误文案单点定义 `:867` / `:870-873` |
| 4 | 前置保持 `is_workflow_enabled` 之后（`:8`） | 已完成 | `:966`（disabled）→ `:972`（target）；`:995` → `:1001`。分支序与替换位置均未变（D5） |
| 5 | 写入后调 `_flow_refresh_after_event`（`:9`） | 已完成 | `scripts/workflow_state.py:989`（artifact-event）、`:1025`（review-manifest） |
| 6 | 其余四处 `handoff.json` 引用按 D3 保留 + legacy 注释（`:10`） | 已完成 | 四处均未删且各带「为什么」注释：`discover` `:367-369`、`cmd_current` `:543-545`、`cmd_spawn` `:907-909`、`cmd_validate` `:1031-1032`；四条注释均给出当代等价物/不可用理由 + 跟踪 issue #227；文本已落入 `docs/known-debt.md`（#227 条目，含 grill 补出的 `discover` 单列与 `docs/requirements-process.md` 口径漂移） |

### 测试

| # | 任务（tasks.md 行） | 状态 | 证据 |
|---|---|---|---|
| 7 | 无 handoff + proposal → `artifact-event` exit 0 且事件写入（`:16`） | 已完成 | `tests/test_workflow_protected_write_channel.py:146-156`（冷状态断言 `:149`、事件落盘断言 `:154-156`） |
| 8 | 同条件 → `review-manifest` exit 0 且 manifest 写入（`:17`） | 已完成 | `:159-172`（`verify_review_manifest == []` `:169`；R1 新增 `:171-172`） |
| 9 | 老世代（initialized + handoff + proposal）→ 两命令 exit 0（`:18`） | 已完成 | `:190-209`；种子 `_seed_gen1_change:60-90`（`initialized` 首事件内嵌 handoff 载荷 `:79`） |
| 10 | 无 proposal 但有 handoff（spawn 形态）→ exit 0（`:19`） | 已完成（部分覆盖） | `:212-223` 覆盖 `artifact-event`；`review-manifest` 未在此形态单独覆盖——同一 `_require_change_target` 单点判定，属可接受的覆盖省略（R1 已记为观察项，我复核同意） |
| 11 | 不存在的 change → exit 1（`:20`） | 已完成 | `:229-242`；并断言错误来自目标检查本身（`:234` / `:242`），保证对「前置被删」有判别力 |
| 12 | 目录存在但两锚点皆无 → exit 1（`:21`） | 已完成 | `:245-264`，附「零落盘」断言（`:253` 未写 `workflow-events.jsonl`、`:264` 未建 `reviews/`） |
| 13 | 写入后 `verify_projection` 为空（`:22`） | 已完成 | `:175-184`（`workflow-state.json` 存在 `:183` + `verify_projection == []` `:184`），override 了「必须先跑 flow status」的顺序依赖 |
| 14 | 变异验证（`:23`） | 已完成 | 我本轮独立重跑 5 组变异，见 Test Results「变异验证」表 |
| 15 | 回归 `test_workflow_state_cli.py` + 全量 pytest（`:24`） | 已完成（如实记录） | 目标三文件 53 passed；全量 4 failed / 2999 passed，4 例均与本 change 无关（见 Test Results） |

### 文档

| # | 任务（tasks.md 行） | 状态 | 证据 |
|---|---|---|---|
| 16 | `diagnosis.md` 6 章（`:28`） | 已完成 | `diagnosis.md` 含 Symptom / Reproduction / Evidence / Root Cause / Recommended Direction / Regression Tests 六节 |
| 17 | spec delta 正文补全（`:29`） | 已完成 | 程序化逐条比对：`dev-workflow-state-machine` 正式 8 → delta 11（8 保留 + 3 新增），`change-documentation` 正式 3 → delta 4（3 保留 + 1 新增）。详见「Spec 维度」 |
| 18 | `known-debt.md` 新增条目（配事件）（`:30`） | 已完成 | `docs/known-debt.md`（diff +64 行，三个新 H2 条目，分别跟踪 #227/#228/#229）+ seq 2 `protected_artifact_explained` 事件；隔离验证 `[]` |
| 19 | 当前规格同步（`:31`，未勾） | 未执行（属收尾） | `openspec/specs/{change-documentation,dev-workflow-state-machine}/spec.md` 尚未修改，事件日志无 `current_spec_synced`。归档前必须完成 |
| 20 | 关键词扫描（`:32`） | 已完成 | `grep -rn "没有 handoff.json\|handoff.json 存在\|强制要求 handoff" docs/ AGENTS.md CONTEXT.md README.md` 只命中 `docs/known-debt.md`（本 change 新写的事实描述）与 `docs/openspec-change-backlog.md`（本 change 的 backlog 条目），无本次造成的事实漂移；`AGENTS.md:89` 的「handoff.json 已停用」口径与实现一致 |
| 21 | backlog 移除本 change（`:33`，未勾） | 未执行（属收尾） | 本 change 仍作为第 5 号条目在 `docs/openspec-change-backlog.md` 的「未实现队列」；已有 `backlog_updated` 事件（seq 1） |

### 审阅闭环 / 验证

| # | 任务（tasks.md 行） | 状态 | 说明 |
|---|---|---|---|
| 22 | 独立 subagent 审阅 → verdict（`:38`） | 已完成 | 第 1 轮 CHANGES_REQUESTED（`reviews/building-review-r1.md`，已随 `0d186fb` 保留），本轮 PASS |
| 23 | 生成 review manifest（`:39`，未勾） | 待生成 | 第 2 轮 PASS 后生成；注意 `tasks_hash` 绑定的是当前 24/29 勾的 `tasks.md`（与 `archive/2026-09-20-fix-issue-191` 的既有惯例一致，其归档时 28 勾 / 6 未勾，manifest verify 仍 `[]`） |
| 24 | 全量 pytest（`:43`，未勾） | 未勾，正确 | 当前 4 failed / 2999 passed，4 例均与本 change 无关。保持未勾符合「不确定项不勾」的纪律 |
| 25 | OpenSpec strict validate（`:44`） | 已完成 | 我实跑：`Totals: 30 passed, 0 failed (30 items)` exit=0 |
| 26 | artifact checker（`:45`） | 勾了，但**当前不可复现** | 该勾是 R1 修复前打的（当时 known-debt 靠旧事件兜底、manifest 门禁未开）。现状为 `ERROR: review manifest missing` exit=1——**这是 R1 修复把门禁打开后的正确中间态**，非虚勾。收尾生成 manifest 后即可复现；建议收尾时重跑确认 |
| 27 | 端到端验收（`:46`） | 已完成 | 我独立复现（冷状态、全程不跑 `flow status`）：两命令 exit 0，`verify_projection == []`，`verify_review_manifest == []`。见 Test Results |
| 28 | `flow status` 反映投影（`:47`） | 已完成 | 实跑输出 `{"schema":"workflow-state/v1", "change_id":"fix-issue-199-handoff-prereq", "state":{"phase":"planning","sub_state":"exploring"}, "milestones":[], "source_event_seq":2, "stale":true}` |

**结论**：24 个 `[x]` 全部有真实实现，无虚勾；5 个 `[ ]`（`:31`/`:33`/`:34`/`:39`/`:43`）经核对确实全部属归档收尾或第 2 轮 PASS 之后的步骤。

## 8 个审阅维度结论

1. **任务逐项验证** — 见上表。24/24 有实现证据，无虚勾。
2. **正确性** — `_require_change_target:853-875` 与 design D1（目录存在 且（`proposal.md` 或 `handoff.json`））逐字一致；`is_workflow_enabled` 仍在最前（`:966` / `:995`）；非法目标零落盘（变异 M3 下两个「零落盘」用例红，且用例自带文件不存在断言）。补充实测：对 `openspec/changes/archive` 本身调用会被正确拒绝（该目录无 `proposal.md`，无 `handoff.json`）。
3. **Spec 对齐** — 见「Spec 维度」节，无静默丢失。
4. **冗余度** — 与 `_flow_require_change:768-776` 的分叉是**有意且有据**的（后者以 `workflow-events.jsonl` 为前置，首次写入会自锁，`design.md:41` 已论证）；未引入 `_flow_is_gen1` 分支，理由见 `design.md:50`（写入路径本就不需要世代判定）。判定单点、两命令复用，无重复实现。
5. **测试覆盖与判别力** — 5 组变异全部有判别力（见下表）；R1 Issue 3 的判别力缺口已补齐。
6. **安全性** — 锚点放宽后仍拒绝不存在目录与两锚点皆无的目录；受保护路径解释事件的校验逻辑（`scripts/check_openspec_artifacts.py:1071-1141`）未改；`pathlib` 词法 `..` 不可用。绝对路径缺口是既有属性（问题 4），另发现 New-1（低）。
7. **可维护性** — 四处 legacy 注释（`:367-369` / `:543-545` / `:907-909` / `:1031-1032`）都解释「为什么」（停用状态机、当代等价物、为何本次不改、跟踪 issue 号），非复述「是什么」；`_require_change_target` 的 docstring 亦解释了为何不用事件日志作锚点、为何保留 `handoff.json` 分支。命名与文件内既有风格一致。
8. **CI 完整性** — 受保护 artifact 两处均有结构化事件（问题 1 已复核定论）；`git diff origin/master...HEAD -- AGENTS.md scripts/workflow_guard.py scripts/flow-policy.json .github/` **为空**（guard 白名单、策略表、CI 配置零改动，与 `proposal.md:40` 的非目标一致）。

### Spec 维度（独立核实，不只看 delta 自己）

程序化按 `### Requirement` / `#### Scenario` 结构比对 delta 与正式 spec：

```
===== dev-workflow-state-machine =====
  Requirement: 工作流事件日志与 handoff.json projection
    formal (8): 当代 change 投影为 workflow-state.json / 老世代 change 仍可投影 / 任意 change 可查询状态 /
                新建 change 时初始化 workflow event log 和 handoff.json / agent 读取当前状态 /
                WorkflowEngine 更新状态 / handoff.json 被手动篡改 / 非状态 artifact 事件
    delta (11): 上述 8 条（2 条改名改写、2 条正文按两代口径改写）+ 3 条新增
    dropped: ['新建 change 时初始化 workflow event log 和 handoff.json', 'handoff.json 被手动篡改']
===== change-documentation =====
  Requirement: Handoff state file artifact
    formal (3) / delta (4)：3 条既有全部保留 + 1 条新增（当代 change 不要求 handoff.json）
    dropped: []
```

- 两条 `dropped` 正是 `design.md:114-126` 退役清单显式列出的**改名 + 改写**项（`新建 change 时初始化 workflow event log`、`投影被手动篡改`），**非缺省消失**。
- 正文级比对：`当代 change 投影为 workflow-state.json` / `老世代 change 仍可投影` / `任意 change 可查询状态` 三条逐行**完全一致**；`agent 读取当前状态` / `WorkflowEngine 更新状态` / `非状态 artifact 事件` 三条为**语义保留的两代改写**（把 `handoff.json` 换为「该 change 的投影状态 / 该 change 世代的投影 / 投影」），每条正式子句在 delta 中都有对应子句，无丢失。`非状态 artifact 事件` 保留了本 change 依赖的「至少 4 类 artifact event type」清单（`design.md:122` 的承诺成立）。
- 3 条新增 Scenario（`受保护写通道不要求 handoff.json` / `受保护写通道拒绝非法目标` / `老世代 change 的受保护写通道保持可用`）在正式 spec 中不存在，在 delta 中完整存在；正文与 tasks.md 的测试项一一对应。
- 详见 New-2：design D6 退役清单表只列了 2 条「改写」，实际正文被改写的场景是 4 条（另 2 条标为「保留」，但正文实际新增了当代分支）。属**文档精度问题**，delta 本身是超集安全的。

## Issues

### New-1（低，新发现·本 change 引入）— D7 刷新对 `gen-1 + 非裸 id 目标` 抛未捕获异常

**证据**（同一输入，base vs head 对照）：

```
# 目标：openspec/changes/archive/2026-07-14-add-workflow-automation（首事件 initialized，有 handoff.json）
$ python3 <base 5fa99aa CLI> artifact-event --change archive/2026-07-14-add-workflow-automation \
    --event-type change_archived --artifact-path openspec/changes/archive/ --reason probe5 --approved-by human
已记录 artifact 事件: change_archived (openspec/changes/archive/)      base exit=0

$ python3 <HEAD CLI> 同一命令
  File ".../scripts/workflow_state.py", line 224, in _save_handoff
    with open(tmp, "w", encoding="utf-8") as f:
FileNotFoundError: [Errno 2] No such file or directory:
    'openspec/changes/2026-07-14-add-workflow-automation/handoff.json.tmp'   head exit=1
```

同样地，`--change /tmp/ext199d`（绝对路径指向有 `handoff.json` 的 gen-1 目录）在 base 下 exit=0，在 HEAD 下抛同一条 `FileNotFoundError`。

**根因**：`scripts/workflow_state.py:989` / `:1025` 新增的 `_flow_refresh_after_event(change_dir)`（`:878-886`）在 gen-1 分支走 `_save_handoff(change_dir.name, …)`（`:882` → `:221-225`），而 `_save_handoff` 内部用 `CHANGES_ROOT / change_id`（`:222`）**重新拼路径**，丢弃了调用方解析出的实际 `change_dir`。当 `--change` 不是裸目录名（含 `/` 或绝对路径）时，`change_dir.name` 与真实路径不再对应，`.tmp` 父目录不存在 → 裸 traceback。

**影响面（已实测界定）**：只影响 **gen-1（有 `handoff.json`）且 `--change` 含 `/` 的目标**，即 `archive/<archived-id>` 形态的归档 change 与绝对路径指向的 gen-1 目录；gen-2 目标走 `_refresh_workflow_state(change_dir)`（`:889`）用真实路径，不受影响。危害为**半写 + 响亮失败**：事件已追加、随后抛裸 traceback exit 1；状态未损坏（我对该目录跑 `verify_projection` 仍返回 `[]`）。仓库内无任何脚本/文档/测试使用带斜杠的 `--change`，归档目录在 `_flow_resolve_change_dir:796` 的文档口径里本就是「只读可查」。

**建议**（可本 change 顺手修，也可并入既有债务）：

- 最小修法：把调用点改为把 `change_dir` 传下去（`_flow_refresh_after_event` / `_save_handoff` 接受路径而非 id），或在 `_require_change_target:853` 增加 `if Path(change_id).is_absolute() or "/" in change_id: 明确拒绝`——后者同时封住问题 4 的绝对路径缺口，一次性收敛两者。
- 若留债：建议与问题 4 合并成一条（两者同源：`CHANGES_ROOT / change_id` 的拼接语义），并在该条目里写明「本 change 后该输入由 exit 0 变为裸 traceback exit 1」。

**为何不阻塞**：非文档化输入面、仓库零使用、无状态损坏、失败响亮；与 R1 对问题 4 的定性（Low/既有属性）同族。

### New-2（低，文档精度）— `design.md` D6 退役清单表漏列 2 条实际被改写的 Scenario

`design.md:116-126` 的退役清单把 `agent 读取当前状态` 与 `WorkflowEngine 更新状态` 标为「保留 / 语义两代不变」，但按正文级比对，这两条实际被改写为两代口径（`handoff.json` → 「该 change 的投影状态」/「该 change 世代的投影」+「磁盘投影与 replay 一致」）。R1 已指出同一表格的「5 条 vs 2 条」偏差并在 `bc5bb16` 里澄清了措辞，但「保留」标签与实际改写状态仍未对齐。

**影响**：无功能影响，delta 是语义超集（改写后保留原 gen-1 子句）。**建议**：归档前把该表两个「保留」改为「保留（正文按两代口径改写）」，或补一行说明。

## Test Results

### 1. 目标测试

```
$ uv run pytest tests/test_workflow_protected_write_channel.py tests/test_workflow_state_cli.py tests/test_workflow_guard.py -q
53 passed in 51.92s
```

### 2. 全量 pytest

```
$ uv run pytest -q
4 failed, 2999 passed, 9 skipped, 76 warnings in 471.11s (0:07:51)
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir
FAILED tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_malformed_git_file_falls_back_to_scan
FAILED tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect
FAILED tests/web_tests/test_workflow_graph_browser.py::test_foreach_candidate_drilldown_shows_that_item
```

- 前两例为**已知环境失败**（环境存在 `/tmp/.git` 导致向上扫描误判），base 已复现，与本 change 无关（主 session 已认定为环境问题，不计缺陷）。
- 后两例为**浏览器时序 flaky**：单独重跑 `uv run pytest tests/web_tests/test_multi_session_browser.py::test_multi_tab_exit_does_not_affect_other_tab_reconnect tests/web_tests/test_workflow_graph_browser.py::test_foreach_candidate_drilldown_shows_that_item -q` → **2 passed in 9.02s**，与本 change 无关。

### 3. 变异验证（本轮我独立执行；每组跑完均还原并核对 sha256）

变异前的 sha256：`544744a054c2d977e5204bbbd6d5888a731b1a930b89087c99bf5e3a58a6aa1d`；全部变异结束后再次核对 = **同一值**，`git status --short` 为空。

| # | 变异 | 结果 | 判别力 |
|---|---|---|---|
| M0（确认 B，主 session 指定） | 只删 `cmd_review_manifest` 侧的 `_flow_refresh_after_event`（`:1025`） | **1 failed / 9 passed**：`test_review_manifest_works_without_handoff_json` | **充分**（R1 Issue 3 已修复） |
| M1 | `_require_change_target` 改回硬要求 `handoff.json` | **5 failed / 5 passed**：`test_artifact_event_works_without_handoff_json`、`test_review_manifest_works_without_handoff_json`、`test_artifact_event_refreshes_projection_without_flow_status`、`test_artifact_event_rejects_dir_without_proposal_or_handoff`、`test_review_manifest_rejects_dir_without_proposal_or_handoff` | 充分 |
| M2 | 去掉 `handoff.json` 兼容分支（只认 `proposal.md`） | **1 failed**：`test_spawn_style_child_without_proposal_still_writable` | 充分（Q1 回归面被锁住） |
| M3 | 整个去掉前置（存在性 + 锚点检查） | **4 failed**：两个 `rejects_unknown_change` + 两个 `rejects_dir_without_proposal_or_handoff` | 充分（D5「不退化为任意路径可写」被锁住） |
| M4（附带探测） | gen-1 目标（含 `archive/<id>` 形态）触发 D7 刷新 | 抛 `FileNotFoundError` 裸 traceback（New-1） | **无覆盖** → 已在 Issues 记录 |

### 4. 隔离验证（问题 1 / 维度 8）

```
# 只把本 change 的 workflow-events.jsonl + scripts/flow-policy.json 放进 /tmp/iso199
docs/known-debt.md              -> []
docs/openspec-change-backlog.md -> []
event types: ['backlog_updated', 'protected_artifact_explained']

# 反例：删掉 seq 2
docs/known-debt.md              -> ['protected path `docs/known-debt.md` changed without workflow event explanation']

# 真实仓库（changed_paths = git diff --name-only origin/master...HEAD）
all changed paths -> []      known-debt only -> []      backlog only -> []
```

### 5. 冷状态端到端验收（issue #199 验收原文，全程**不跑 `flow status`**）

```
$ cd /tmp/cold199b   # openspec/changes/e2e-cold/ = proposal.md + reviews/building-review.md + change_created 首事件
handoff exists before: NO
$ python3 <repo>/scripts/workflow_state.py artifact-event --change e2e-cold \
    --event-type protected_artifact_explained --artifact-path docs/known-debt.md --reason "e2e cold" --approved-by human
已记录 artifact 事件: protected_artifact_explained (docs/known-debt.md)      exit=0
$ python3 <repo>/scripts/workflow_state.py review-manifest --change e2e-cold --phase building \
    --reviewer-run-id r1 --base-sha deadbeef --head-sha deadbeef
已写入 review manifest: .../e2e-cold/reviews/building-review-manifest.json   exit=0
$ verify_projection(...)       -> []
$ verify_review_manifest(...)  -> []
```

修复前后对照（同一冷状态输入）：

```
# base（5fa99aa 的 CLI）
$ python3 <base CLI> artifact-event --change pre199 ...
错误：change 'pre199' 没有 handoff.json          exit=1
# head（本次修复）
$ python3 <repo>/scripts/workflow_state.py artifact-event --change e2e-cold ...
已记录 artifact 事件: ...                        exit=0
```

→ 顺序依赖掩蔽已解除：冷状态直接可用，不再需要先跑 `flow status` 自愈。

### 6. 门禁复核（问题 2）

见「问题 2 复核」节：当前 baseline `ERROR: review manifest missing` exit=1（门禁对 manifest 生效）；移走 `building-review.md` 后 PASS exit=0（`requires_building_review` 仍因 5 项未勾而短路）；隔离副本把 29 项全勾后正确报 `building-review.md missing` exit=1（触发条件本身正常）。

### 7. 其他实跑

```
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 30 passed, 0 failed (30 items)          exit=0

$ uv run python scripts/workflow_state.py flow status --change fix-issue-199-handoff-prereq
{"schema":"workflow-state/v1","change_id":"fix-issue-199-handoff-prereq",
 "state":{"phase":"planning","sub_state":"exploring"},"milestones":[],
 "source_event_seq":2,"stale":true}

$ git ls-files openspec/changes/ | grep -E "handoff.json|workflow-state.json"
（active change 零命中；仅 6 条归档历史遗留）

$ git diff --name-only origin/master...HEAD -- AGENTS.md scripts/workflow_guard.py scripts/flow-policy.json .github/
（空）
```

**工作树完整性**：本轮所有变异/探测均已还原——`git status --short` 为空（我在问题 5 复核中因跑 `flow status` 产生的两个自愈产物 `handoff.json` / `workflow-state.json` 已删除，`scripts/workflow_state.py` sha256 与审阅开始时一致，归档目录的探测改动已 `git checkout` 还原）。

## 结论

R1 的 4 条 Issue 与主 session 发现的第 5 条**逐条修复到位且经独立复核**：问题 1 用隔离仓 + 反例对照证明事件是本 change 自证（不再靠旧事件兜底）；问题 2 勾选后 checker 已对 manifest 生效、门禁触发条件在 tasks 全勾时正常（残余的 in-flight 豁免是仓库既有设计，已作 Obs-1 记录）；问题 3 经确认 B 变异验证判别力成立且还原 sha 一致；问题 5 经 `git ls-files` 与实跑复现双向确认。

实现层面（前置判定、顺序、拒非法目标、写入后刷新）与 design D1/D5/D7 一致；测试从冷状态构造、5 组变异均有判别力；spec delta 的「整段替换」风险已按 D6 处理并通过结构 + 正文级独立比对验证，无静默丢失。新发现 2 条 **Low** 问题（D7 刷新在 gen-1 + 带斜杠/绝对路径目标上抛裸 traceback；design D6 退役清单漏列 2 条改写项）——均不阻塞，建议在收尾时顺手收敛 New-1（修法可与问题 4 的绝对路径缺口合并到同一处 `_require_change_target` 守卫），或在 known-debt 中合并记一条并写明「本 change 后该输入由 exit 0 变为 traceback exit 1」。

**Verdict: PASS**。收尾提醒（不属缺陷）：`tasks.md:31` 当前规格同步与 `:33` backlog 移除、`:39` 生成 review manifest、`:43` 全量 pytest 重跑确认、`:34` 收尾纪律（禁用 `git add -A`，因为 `flow status` 与写通道都会重建 `handoff.json` / `workflow-state.json`）。
