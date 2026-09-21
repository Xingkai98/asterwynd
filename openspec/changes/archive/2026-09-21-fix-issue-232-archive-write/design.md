# Design — fix-issue-232-archive-write

## Context

见 `proposal.md` 与 `diagnosis.md`。核心事实：

- `_require_change_target`（`scripts/workflow_state.py:853`）只看 active 目录，无 archive 回退。
- **`_flow_resolve_change_dir`（`:795`）的回退对真实归档目录失效**：它拼 `CHANGES_ROOT/"archive"/<裸 id>`，而仓库 89 个归档目录**全部**带 `YYYY-MM-DD-` 前缀 → 该分支是**死代码**（实测 `_flow_resolve_change_dir('fix-issue-199-handoff-prereq')` → `None`；`flow status --change <该 id>` → exit 1）。它**不是**可复用的口径。
- `review_manifest.change_dir_for(archived=True)` 已能按 `<date>-<id>` 扫描定位归档目录（实测可用）——能力存在，只是调用方没用。
- `cmd_review_manifest` 调 `write_review_manifest(...)` **不传 `archived=`**（默认 False）→ `build_review_manifest` 先抛 `FileNotFoundError: review report missing: <active>/reviews/building-review.md` → exit 1；`mkdir` 在其后，active 目录**不会**被新建（真实危害是误导性报错，非污染）。
- 成功后调 `_flow_refresh_after_event(change_dir)`；对归档目录实测**会写出 `handoff.json` + `workflow-state.json` 到归档目录**（立项复现并清理）。

## Goals / Non-Goals

**Goals**

- 归档 change 可经合法 CLI 写受保护 artifact（事件 + manifest），落在归档目录内。
- 归档目录**不被污染**（不产出投影文件、不在 active 路径新建目录）。
- 归档目标契约收紧：解析结果必须与查询 id 一致（fail-closed），带日期前缀的 id 被拒。
- active change 与 #199 行为零回归。

**Non-Goals**

- 不做盲区 B（CI `--check-archived`）——实测有 15 条既有 `tasks hash mismatch`，需先决策。
- **不修 `flow status` 的归档查询**（Q1 选 A）：`_flow_resolve_change_dir` / `flow status` 对归档 id 不可用是既存缺陷（实测 exit 1），与写通道无关，单独记账。
- 不改 `review_manifest.py` 的 `change_dir_for` 正则（Q2）——它是 checker 共用的，改动面超出本 change；改为调用侧事后断言 + 记入 known-debt。
- 不改 `.gitignore`（#228 范围）。

## Decisions

### D1: 委托 `change_dir_for` 解析归档目标（**不**复用 `_flow_resolve_change_dir`）

`_require_change_target` 的目标解析改为：active 目录优先 → 否则**委托 `agent.workflow.review_manifest.change_dir_for(repo_root, change_id, archived=True)`**。

理由（grill 实测，原设计的「复用 `_flow_resolve_change_dir`」前提**不成立**）：`_flow_resolve_change_dir` 的 archive 回退拼裸 id（`CHANGES_ROOT/"archive"/<id>`），而 89/89 归档目录都带日期前缀，故它是**死代码**（`_flow_resolve_change_dir(<归档 id>)` → `None`），照抄它等于没修。而 `change_dir_for(archived=True)` 实测可用，且它本来就是 manifest 落点的决定者——委托它可保证「事件落点」与「manifest 落点」由**同一算法**决定，避免再次漂移。

**`repo_root` 陷阱（必须遵守）**：委托时 `repo_root` 必须由 `CHANGES_ROOT.parent.parent`（实测 `openspec/changes` → `.`，cwd 相对）推导，**不能**用 `_PROJECT_ROOT`——后者是真实仓库绝对路径（`/home/happy/my-agent`），会让 tmp 冷状态测试的解析逃逸到真实仓库而**恒红**（实测 `change_dir_for(_PROJECT_ROOT, ...)` → `is_dir=False`）。

**解析与判定分离**：`change_dir_for` 只负责定位，合法性判定（`proposal.md` 或 `handoff.json`）仍在 `_require_change_target` 内做，#199 锚点不变。

### D2: 归档目标契约——保留 #199 锚点 + 新增一致性断言 + 拒绝日期前缀 id

**合法性锚点维持 #199 口径**：归档目录同样按「`proposal.md` 存在 **或** `handoff.json` 存在」判定（归档 change 普遍有 `proposal.md`；老世代归档只有 handoff 也应可写）。**不**把「归档目录名必须是 `<date>-<id>`」作为硬前置——`change_dir_for` 有 `name == change_id` 的裸 id 分支（`review_manifest.py:45`），硬前置会与它分叉；#199 锚点已足以防止 archive 下的非 change 目录被当作目标。

**新增一致性断言（Q2，fail-closed）**：解析出的目录名必须满足 `name == change_id` **或** `re.fullmatch(r"\d{4}-\d{2}-\d{2}-" + re.escape(change_id), name)`，否则 exit 1。理由（实测）：`change_dir_for` 的前缀正则 `re.match` 缺 `$` 锚点，archive 下同时有 `2026-09-21-alpha/` 与 `2026-09-22-alpha-beta/` 时查询 `alpha` 会命中**另一个 change** 的目录，且依赖 `iterdir()` 顺序（两次构造跑出相反结果）——静默写错 change。断言让它在源头 fail-closed（宁可不写也不写错）。当前 89 个归档 id 无前缀碰撞，属潜在缺陷；`change_dir_for` 自身正则的修复记入 `docs/known-debt.md` 另案。

**拒绝带日期前缀的 `--change` id（Q4）**：`--change 2026-09-21-<id>` 会让写入事件的 `change_id` 字段带日期，而 CI 的 `_change_id_for_event_log` 剥前缀后比对 → `change_id mismatch`（PR 门禁红且难查）。显式拒绝并给可读提示（「请用不含日期前缀的裸 change id」），写进 spec 归档 Scenario + 回归用例。

### D3: 把「已归档」显式传给 `write_review_manifest`，判定用路径前缀

调用方据解析结果传 `archived=True`。理由：`change_dir_for` 按 `archived` 决定路径；不传则 `build_review_manifest` 抛 `FileNotFoundError: review report missing: <active 路径>` → exit 1（`mkdir` 在其后，active 目录不会新建，但报错指向不存在的 active 路径、误导排查）。

判定方式：解析结果是否位于 `CHANGES_ROOT / "archive"` 之下（用路径前缀判断，不用目录名猜）。实测在 active 优先的解析下，「路径在 archive 下」⟺「active 目录不存在」，两种判据等价；路径前缀更直接，且在 active 与 archive 同名并存的极端情形下不误判（实测并存时 `archived=False` 与 `archived=True` 落到不同文件）。

### D4: 归档目标跳过投影刷新 + 只读一致性校验

`_flow_refresh_after_event` 对归档目录**不调用**。理由（实测）：对归档 change 调用它会走 gen-2 分支（归档 change 首事件常是 `backlog_updated`，`_flow_is_gen1` 为 False），在归档目录写出 `handoff.json` + `workflow-state.json`——它们是**已提交**目录里的未跟踪产物，比 active 目录的同类污染更严重（会被 `git add -A` 吞进后续提交）。

**跳过刷新不会立即报错**（grill 实测成立）：归档追加事件后 `verify_projection` = `[]`；仓库全部 89 个归档目录跑一遍 0 报错；`--check-archived` 只验「可投影」、不比磁盘投影（`check_change` 里的 `verify_projection` 只作用于 active 目录）。

**但有一个例外必须补偿（Q3）**：若归档目录磁盘上已有**已提交的** `workflow-state.json`（仓库实测 1/89：`archive/2026-08-15-flow-event-projection/`），跳过刷新会让投影**永久 stale**——实测追加一条事件不刷新后 `verify_projection` 立即返回 `workflow-state.json projection does not match workflow-events.jsonl`，而今天无任何调用方校验归档投影会把它彻底掩盖（盲区 B 一开就爆）。故归档写入成功后做一次**只读** `verify_projection`，仅在返回非空错误列表时 stderr 打印告警，**exit 仍 0、绝不落盘**。不做 fail-closed（会让 88/89 场景无用的检查阻断正常收尾）。

### D5: spec delta 补全为完整 Requirement 正文

按 #199 教训：`openspec archive` 是整段替换 Requirement，delta 必须含变更后的**完整**正文。

grill 实测核对：正式 spec 该 Requirement 有 **11** 条 Scenario，delta 起初为 **12** 条（新增 {受保护写通道支持已归档 change}），既有 11 条零丢失、语义退役 **0**。

**修文档时同步补 delta**：删除「目标解析 SHALL 与 `flow status` 的既有口径一致」这条**不成立的事实**（`flow status` 对归档 id 实测 exit 1），改为写明写通道自身的解析口径；并补入 Q2 一致性断言与 Q4 拒绝日期前缀 id 的契约 → 新增第 2 条 Scenario「受保护写通道拒绝归档语境下的非法 change id」，delta 最终为 **13** 条（既有 11 + 新增 2）。

### D6: 非目标锁定——盲区 B 不在本 change

CI 是否加 `--check-archived` 是独立决策（15 条既有 hash 漂移需先定「重绑 vs 容忍」）。本 change 只在 `proposal.md` / 本设计的 Non-Goals 中记明，不顺手改 `ci.yml`。

## Pre-Implementation Review

非平凡 change（有 spec delta + 非 docs），进入实现前由独立零记忆 subagent 执行 `/grill`。

- run id: `grill-fix-issue-232-archive-write-2026-09-21-001`；产出 `reviews/grill-design.md`（14 条 Confirmed Decisions + 5 条 Open Questions + 7 条风险）。
- **grill 推翻了本设计的三处事实前提**（均已按实测改写进上面的 D1/D2/D4 与 `proposal.md` / `diagnosis.md`）：①「复用 `_flow_resolve_change_dir` 回退」——该回退对全部带日期前缀的归档目录是死代码；②「幽灵目录」——实际先抛 `FileNotFoundError`、目录不新建；③「目标解析与 `flow status` 口径一致」——`flow status` 对归档 id 实测 exit 1，无此口径。
- Open Questions Q1–Q5 已停轮抛用户确认，答复回填 `reviews/grill-design.md` 的 `## User Confirmation`（2026-09-22）：Q1 选 A（不修 `flow status`）、Q2 调用侧断言 + 不改 `change_dir_for`、Q3 只读校验 + 告警、Q4 拒绝日期前缀 id、Q5 按实测改写措辞。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 归档目录被投影文件污染（立项已实测复现） | D4 跳过刷新 + 判别性回归测试（断言归档目录无 handoff/workflow-state） |
| 落点错到 active 路径 | D3 显式传 `archived=True` + 测试断言落点在 archive、active 路径未被新建。**实测危害是误导性报错而非污染**：对归档目标传 `archived=False` 时 `build_review_manifest` 先抛 `FileNotFoundError: review report missing: <active>/reviews/building-review.md` → exit 1，`mkdir` 在其后，active 目录**不会**被新建 |
| 两个解析入口再次漂移 | D1 委托 `change_dir_for`（不新写回退），使事件与 manifest 落点由同一算法决定 |
| 委托 `change_dir_for` 时 `repo_root` 用错（`_PROJECT_ROOT`）导致测试逃逸到真实仓库 | D1 明确要求 `CHANGES_ROOT.parent.parent`；实现与测试统一 |
| `change_dir_for` 前缀正则缺 `$`，选到另一个 change 的归档目录（实测顺序依赖） | D2 解析后一致性断言 fail-closed；`change_dir_for` 正则修复记入 `docs/known-debt.md` 另案 |
| 已有已提交投影的归档目录（1/89）因跳过刷新而永久 stale | D4 只读 `verify_projection` + stderr 告警（exit 0、不落盘） |
| delta 静默删既有 Scenario | D5 完整正文 + 归档前核对 Scenario 数 |
| 归档写入是否该被允许的语义争议 | 证据：manifest 必须绑定归档后的最终 head（#199 真实踩到），归档写入是收尾固有需求；由 grill 复核该立场 |

## Testing Strategy

- CLI 层（新增独立测试文件 `tests/test_workflow_archive_write_channel.py`；归档用例全部在 tmp 仓库冷状态构造）：
  - 归档 change + `artifact-event` → exit 0，事件落归档目录事件日志。
  - 归档 change + `review-manifest` → exit 0，manifest 落 `archive/<date>-<id>/reviews/`，`verify_review_manifest(archived=True)` 为空。
  - **污染判别**：写入后归档目录**无** `handoff.json` / `workflow-state.json`；active 路径 `openspec/changes/<id>/` 未被新建。
  - 归档 + 路径型 id / 不存在 id → 仍拒绝；带日期前缀 id → exit 1 且不写文件。
  - 一致性断言：构造前缀碰撞（`<date>-alpha/` 与 `<date>-alpha-beta/`）→ 查询 `alpha` 必须解析到 `alpha` 而非 `alpha-beta`，否则 exit 1。
  - 只读校验：归档目录投影一致 → 无告警；预置已提交 `workflow-state.json` 后追加事件 → stderr 有告警且 exit 0、盘点未落盘。
- 回归：#199 的 `tests/test_workflow_protected_write_channel.py`（10 条）+ `tests/test_workflow_state_cli.py` 全绿。
- 变异验证：去 archive 回退 → 归档用例红；去「归档跳过刷新」→ 污染用例红；不传 `archived=` → 落点用例红；去一致性断言 → 前缀碰撞用例红。
- 全量 `uv run pytest -q` + `npx @fission-ai/openspec@1.4.1 validate --all --strict`。
