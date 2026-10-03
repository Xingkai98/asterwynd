# Building Review: foreach 截断可见性（issue #279）

- 审阅者：独立零记忆代码审阅 subagent（`/review-loop` 等价流程）
- 分支：`foreach-truncation-visibility/2026-10-03`
- 审阅范围：`git diff c797bfa HEAD`（base = `master` `c797bfa`）；实现提交 `78774a3`（feat）+ `59222f9`（docs）
- 被审代码：`agent/subagent/scheduler.py`（+9）、`agent/tools/builtin/subagents.py`（+117）、新测试 `tests/agent/subagent/test_foreach_truncation_visibility.py`（+328）
- 方法：逐行走读被改代码 + 跑真实探针（`uv run python`，合成 LLM、隔离 workspace）验证每条边界；不采信实现方自述结论。

## Verdict

**PASS**

三条模型可见出口（声明期 warnings / dry-run / 运行期投影）的实现与 delta spec 的**全部** SHALL 与 Scenario 一致；边界（source 声明期静默、`max_items=0` 不报、不截断零噪声、与 `item_refs_omitted` 不混、空集合不静默）逐条实测守住；字段命名/后写落点与 design D2/D3 一致；测试 T1–T9 齐备且对 base 树**真会失败**（字段名在 base 不存在）。无高/中问题，仅 3 条低严重度观察（不影响 verdict）。

---

## 逐条任务验证（tasks.md 第 3 节）

| 任务 | 结论 | 证据 |
|---|---|---|
| **3.1** 先写失败测试（T1/T2/T3/T4/T5/T6/T7/source 声明期不报） | **完成** | `tests/agent/subagent/test_foreach_truncation_visibility.py` 18 用例；`git grep` 证实 `items_declared`/`items_omitted`/`empty_collection`/`items_declared_simulated`/`_foreach_truncation_warnings` 在 base `c797bfa` **零命中** ⇒ 断言新字段的用例在 base 必 KeyError，非假阳性 |
| **3.2** `_foreach_truncation_warnings(spec)` helper + 两条入口调用 | **完成** | helper `subagents.py:727-759`；`DeclareWorkflow` 调用 `subagents.py:875-876`；`RunWorkflow(spec=)` 调用 `subagents.py:1382`。实测：60 项字面 foreach ⇒ 两条入口均报「declares 60 … only the first 20 …」+ `max_items: 0` 行动指引、无「default」字样 |
| **3.3** dry-run 补 `items_declared`/`items_omitted`（三元；source 标模拟） | **完成** | foreach 条目 `subagents.py:1684-1697`；实测 60/20/40 三元齐、`20+40==60`；source 驱动标 `items_declared_simulated: true` |
| **3.4** 运行期 `GetWorkflow` 暴露静态截断信号（后写绕过 `_bounded_node`） | **完成** | `_attach_foreach_visibility` `subagents.py:1157-1177`，在 `parent_envelope()`（`:1081`）**之后**、`_attach_item_refs`（`:1093`）之后调用于 `:1097`。实测 `GetWorkflow(detail='nodes')` 真能看到 `items_declared: 60 / items_omitted: 40`（`_PARENT_NODE_FIELDS` `scheduler.py:389` 白名单不含新字段，若在 bounded 前写会被丢——此处正确绕过） |
| **3.4b（Q4）** 空集合 / source 无产出 ⇒ 显式标「集合为空」，区别于正常展开 0 项 | **完成** | `_foreach_visibility_fields` `:1148-1150`（`declared==0` 且非 source 驱动 ⇒ `empty_collection: true`）。实测：字面空集合 dry-run/运行期均 `empty_collection: true`；source 无产出（planner 产出取不到字段）运行期 `empty_collection: true` |
| **3.4c（Q5 + M1）** dry-run 对 source 的 `items_declared` 标「模拟/不可信」；M1 选 (b) 声明期警告不切片 | **完成** | `:1145-1147` 给 source 驱动加 `items_declared_simulated: true`；helper docstring `:743-745` 如实写「上界 = 节点数（受 `max_nodes` 间接约束），不切片、不漏项」且不引用 `warnings_omitted`（该界只在 dry-run 构造器 `:1661` 存在）。测试 `test_declare_emits_one_warning_per_truncated_node` 锁 3 节点 ⇒ 3 条 |
| **3.5** `_resolve_items` 记录声明/展开数供运行期读 | **完成** | `scheduler.py:2675` `state.items_declared = len(items)`，置于 `items[:node.max_items]`（`:2678`）**切片之前**；`items` 仍表切片后展开数（`:1926` `state.items = len(items)`）。`NodeState.items_declared` 声明于 `scheduler.py:254` |
| **3.6** 字段名扁平、绝不复用 `items_total`；运行期字段后写 | **完成** | 全量 `git grep items_total` 确认新代码**从不写** `items_total`；新增键仅 `items_declared`/`items_declared_simulated`/`items_omitted`/`empty_collection`。实测同 dict 共存：`items_total: 20`（既有 `_attach_item_refs` `:1228`）+ `items_declared: 60` + `items_omitted: 40` 无覆盖 |
| **3.7** 回归：workflow 既有测试 + 全量 | **完成** | 全量 `uv run pytest -q` ⇒ `2 failed, 3972 passed, 9 skipped`，2 个失败均为 `test_persistent.py::TestFindScopeRoot::*`（环境噪声，见下） |

**结论**：第 3 节全部任务真实现。

---

## 审阅维度结论

### 1. 任务逐项验证
见上表，3.1–3.7 + 3.4b/3.4c 全部落在代码上，无「文档说做了、代码没做」的落差。

### 2. 正确性（重点攻击项）

- **声明期 helper 边界（全部守住）**：
  - 只在**字面 `items`** 报：`if node.kind != "foreach" or node.items is None: continue`（`:747`）。`source` 驱动 `node.items is None` ⇒ **完全静默**，实测 `DeclareWorkflow` 对 source 驱动返回 `warnings: []`。
  - `max_items=0` 不报：`if node.max_items <= 0: continue`（`:749-750`），实测 `warnings: []`。
  - `items ≤ max_items` 不报：`if declared > node.max_items`（`:752`），实测 3 项 ⇒ `warnings: []`。
  - 措辞**不称「默认值」**：文案 `:754-757` 为「declares {N} … max_items={M} — only the first {M} will run. Reduce items, raise max_items, or set max_items: 0 to run all.」；断言 `"default" not in joined.lower()` 通过。
- **`_foreach_visibility_fields` 边界（守住）**：
  - `items_omitted` 只在**真截断**（`max_items>0 且 declared>expanded`，`:1151-1153`）出现。实测不截断（3≤20）⇒ 无 `items_declared`/`items_omitted`/`empty_collection`（零噪声）；`max_items=0` ⇒ 无静态截断字段（T6）。
  - **(a) source 驱动 dry-run `declared=0` 的语义**：实测输出 `items_expanded: 0, items_declared: 0, items_declared_simulated: true`，**不带** `empty_collection`。与「字面空集合」输出 `items_expanded: 0, empty_collection: true`（**不带** `items_declared`/`items_declared_simulated`）**结构上可区分**：区分子是 `items_declared_simulated`（模拟/未知）vs `empty_collection`（确认空集），二者不共现。**与 `empty_collection` 的区分成立**（这正是 design M2/Q5 的意图）。残留可读性风险见「低严重度观察 1」。
  - **(b) `items_total` 撞名**：实现**确认未用** `items_total`。运行期 probe：`{items: 20, items_total: 20, items_declared: 60, items_omitted: 40}` —— 既有 `items_total`（=展开数，`scheduler.py`/spec:858 钉死）语义不变，与新字段同 dict 共存、无覆盖。
- **运行期「后写」**：`_attach_foreach_visibility`（`:1097`）确在 `parent_envelope()`（`:1081`）之后。**实测** `GetWorkflow(detail='nodes')` 的 foreach 节点真带 `items_declared: 60`/`items_omitted: 40`（未被 `_bounded_node` 白名单丢弃）。
- **D4 独立性**：实测 12 项 / `max_items=10` / ref 界 monkeypatch=5 ⇒ `items_omitted=2` 与 `item_refs_omitted=5` **同 >0、值不同、来源不同**（前者 = `declared-expanded`，后者 = `items_total-len(item_refs)`）。语义不混。
- **delta spec「不截断但 ref 被截」Scenario**：实测 6 项 / `max_items=10` / ref 界=3 ⇒ `items_declared`/`items_omitted` 均**不出现**（静态省略 0），`item_refs_omitted=3` 独立报告。与 spec 一致。

### 3. Spec 对齐
delta spec 的 6 条 SHALL/Scenario 全部兑现：三出口一致报告（T1/T2/T3/T4）；source 声明期不猜（`warnings: []`）；dry-run 对 source 标模拟（`items_declared_simulated`）；无截断零噪声；`max_items=0` 不报；省略数与 ref 界不混；空集合/无产出不静默。**无未兑现 Scenario。**

### 4. 冗余度 / 可维护性
- `_foreach_truncation_warnings` 与 `_route_task_warnings`（`:710`）**风格一致**（同签名 `(spec) -> list[str]`、同遍历 `spec.nodes`、同两条入口共用）。
- `_attach_foreach_visibility` 与 `_attach_item_refs`（`:1180`）**同处后写、同签名**（`(nodes, scheduler)`）。
- `_foreach_visibility_fields` 被 dry-run 与运行期**共用**，无重复实现。未见冗余。

### 5. 测试覆盖
T1–T9 齐备：T1/T2（两条声明入口）、T3（dry-run 三元）、T4（运行期后写可见）、T5（不截断零噪声，dry-run+运行期两份）、T6（`max_items=0`，dry-run+运行期两份）、T7（与 ref 界不混）、T9（字面空集合 + source 无产出，dry-run+运行期）。边界齐全：`declared==0`、`max_items=0`、不截断、source 驱动、模拟标记均有断言。18 用例全绿。

### 6. CI 完整性
- **全量 pytest**：`2 failed, 3972 passed, 9 skipped`。2 个失败 = `tests/agent/memory/test_persistent.py::TestFindScopeRoot::{test_returns_none_for_non_git_dir, test_malformed_git_file_falls_back_to_scan}`。**核实为环境噪声、与 change 无关**：本机 `/tmp/.git` 是一个**空的目录**（`ls /tmp/.git/HEAD` → No such file）；`_find_scope_root`（`agent/memory/persistent.py:62-85`）用 `git_dir.is_dir()` 命中这个 stray 目录 ⇒ 返回 `/tmp`，测试期望 `None` 故失败。`git diff c797bfa HEAD -- agent/memory/ tests/agent/memory/` 为空，change 不触及该代码。属实。
- **OpenSpec strict validate**：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` ⇒ `29 passed, 0 failed`。
- **artifact checker**：`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py` ⇒ `OpenSpec artifact checks passed`。

### 7. 安全性
本 change 只新增**只读投影字段**（`items_declared`/`items_omitted`/`empty_collection`/`items_declared_simulated`）与声明期字符串警告；警告文案用 `node.id!r`（repr 转义）与整数字面量拼接，**无用户输入拼接进可执行路径**、无新 I/O、无新权限面、无泄漏（值均为计数/布尔）。`_foreach_visibility_fields` 返回值键集固定。**无注入/泄漏面。**

---

## Issues

**无高/中严重度问题。**

### 低严重度观察（不阻塞，记录备查）

1. **`_foreach_visibility_fields` 的 `source_driven` 形参名与实际语义不完全一致**（`agent/tools/builtin/subagents.py:1127`、调用点 `:1175`/`:1695`）。该形参真实含义是「`items_declared` 是模拟值（不可信）」，而非「该节点由 source 驱动」——运行期对 **source 驱动节点**故意传 `source_driven=False`（因为运行期解析出的 declared 是真实值），dry-run 才传 `node.items is None`。形参名会让人误以为运行期也是按 source 判别。docstring（`:1136-1140`）已澄清「仅 dry-run 传 True」。**期望**：形参名改 `declared_is_simulated` 更贴语义。**影响**：可读性，无行为风险。严重度：低。

2. **source 驱动 dry-run 的 `items_declared: 0` 仍可能被粗读为「集合为空」**（`agent/tools/builtin/subagents.py:1145-1147`）。实测 `{items_expanded: 0, items_declared: 0, items_declared_simulated: true}`：正确区分于 `empty_collection`（模拟 0 不标空集，符合 design M2），但一个只读数值、忽略 `items_declared_simulated` 标记的消费方仍可能把 0 读成「会跑 0 个」。这是 design Q5/M2 已确认接受的取舍，非缺陷。**期望**：如未来出现误读反馈，可考虑把模拟值改为不报数值、只报 `items_declared_simulated: true`。严重度：低。

3. **delta spec「空集合不静默」Scenario 在 dry-run 出口仅对字面空集合兑现**（`agent/tools/builtin/subagents.py:1148-1150`）。该 Scenario 的 GIVEN 列举「source 未产出、产出解析为空、上游成功但内容为空」，WHEN 含「dry run 报告该节点」；实现选择：dry-run 对 source 驱动**不**报 `empty_collection`（因模拟不可信，标 `items_declared_simulated` 代替），source 无产出的「空」信号落在**运行期**出口。此为 design M2/Q5 + 用户 2026-10-03 确认的显式边界（两个 Scenario 联读：source 的 dry-run 数应标模拟）——**非违规**，记录以免被后续读成遗漏。严重度：低。

---

## 附：关键实测证据

| 场景 | 出口 | 实测输出（关键字段） |
|---|---|---|
| 字面 60 项 / 默认 max_items | dry-run | `items_expanded=20, items_declared=60, items_omitted=40` |
| 字面 60 项 / 默认 max_items | 运行期 | `items=20, items_total=20, items_declared=60, items_omitted=40` |
| 字面 3 项（不截断） | dry-run / 运行期 | 三者均无 `items_declared`/`items_omitted`/`empty_collection` |
| 字面 60 项 / `max_items=0` | dry-run / 运行期 | 无静态截断字段（预算截断 Non-Goal） |
| 字面空集合 | dry-run / 运行期 | `empty_collection=true` |
| source 驱动 / 无产出 | dry-run | `items_declared=0, items_declared_simulated=true`（无 `empty_collection`） |
| source 驱动 / 无产出 | 运行期 | `empty_collection=true` |
| source 驱动 / 解析出 60 项 | 运行期 | `items_declared=60, items=20, items_omitted=40` |
| 12 项 / `max_items=10` / ref 界=5 | 运行期 | `items_omitted=2` 与 `item_refs_omitted=5` 同 >0 且独立 |
| 6 项 / `max_items=10` / ref 界=3 | 运行期 | 无 `items_omitted`（静态省略 0），`item_refs_omitted=3` |

行号基于本 worktree 当前 HEAD（分支 `foreach-truncation-visibility/2026-10-03`，`59222f9`）；若实现期后续改动上游文件，以符号名为准。
