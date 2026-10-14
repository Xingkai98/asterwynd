# 阶段 B 观测报告：guard-write-allowlist

> **本报告是归档 change `witnessloop-adoption` 的阶段 B 交付物**（它的 tasks `B.1`–`B.8` 全部标了 `(post-merge)`、住在 `openspec/changes/archive/2026-10-13-witnessloop-adoption/` 里，等一个真实小需求）。本 change 就是那个「真实小需求」，第 6 节逐条承接 B.1–B.8；本文件是那些条目的实测记录。
>
> **落点说明（为什么在 change 根目录、不在 `reviews/`）**：按 `design.md` Decision 6。理由是**witnessloop 的孤儿规则**——一旦 `reviews/` 下存在任意一份 witnessloop 形态 manifest，`reviews/**/*.md` 里**每一份**未被某份 manifest 的 `report_path` 绑定的报告都判孤儿报告（`src/witnessloop/contract.py:185-206`）。本 change **必须**建三份 witnessloop 形态 manifest（见 §2），孤儿规则**一定会被激活**；而一份「流程观测报告」不属于 witnessloop 固定的三个 stage（`grill` / `grill-adversarial` / `building`，`src/witnessloop/constants.py:65-76`），硬塞 `stage=building` 还会撞 `matching[0]` 的选择（同 stage 多份时按路径字典序只取首份）。⇒ 放 change 根目录：仍在 diff 里、随归档留痕，但不参与 `reviews/` 的证据一致性。

- **观测者**：本 change 的实现 agent（非独立审阅者——这里记录的是**流程观测**，不是审阅 verdict；审阅 verdict 在 `reviews/building-review.md`）
- **观测 revision**：`da861e8`（三份 witnessloop manifest 落库后的 HEAD）
- **基线**：`fd6d581`（`origin/master`）
- **口径**：所有计数用 `grep -c` / `wc -l` / 枚举，不用 `head` 截断；所有行号在**当前树**上现测

---

## 1.（对应 B.1）真实小需求的选择与它的「证据形状」

选本 change 自己当阶段 B 的样本，三条选择标准都命中：

| 标准（来自 `witnessloop-adoption` 的 B 节） | 本 change 的实际情况 | 实测依据 |
|---|---|---|
| **必须触达 `require_change_for`** | 改了 `agent/**`（含 `agent/workspace_policy.py`、`agent/tools/command_guard.py` 等 5 个文件）⇒ `code_hits` 非空 | `git diff --name-only fd6d581 da861e8 \| grep -c '^agent/'` = **5** |
| **必须能产生 spec delta 或受保护写入** | 两份 current spec 同步（`openspec/specs/workspace-safety/spec.md`、`openspec/specs/configuration/spec.md`）+ `docs/openspec-change-backlog.md` 与 `docs/known-debt.md` 的写入 | 本 change 的 `workflow-events.jsonl` 共 **10** 条事件，含 `current_spec_synced` ×3、`backlog_updated` ×3、`protected_artifact_explained` ×2 |
| **规模在一到两个文件级别的小需求** | 生产面 5 个 `agent/**` 文件 + 1 个 `web/session.py` + 1 个 `benchmarks/**` + 4 个测试文件 + 配置示例 | 累计 31 个变更文件（`git diff --name-only fd6d581 da861e8 \| wc -l` = **31**） |

> **与阶段 A 的对照**（这是选它的核心理由）：`witnessloop-adoption` **自己**做阶段 A 时 `code_hits` 为空（它的 diff 只碰 `docs/`、`.witnessloop/`、`.github/workflows/`），所以 `building` 与 `grill-adversarial` 两条 stage 判定**根本没被触发**。本 change 是第一次让那两条判定**真的跑起来**的样本（见 §2 的探针 #2）。

---

## 2.（对应 B.2）在新流程上跑完整链路——三态探针

**方法**：在同一条分支上取三个**递增**的 revision 归零点，各跑一次 `witnessloop check`，读 findings。三次的 diff 是**累积**口径（相对 `fd6d581`），这样每个探针的 `code_hits` 与 `changed_change_ids` 都能对上。

| 探针 | revision | diff（累积） | `check` 的 findings |
|---|---|---|---|
| **#1** | `8e5fc83`（只有立项 + 裁定 + 审阅文档） | 9 个变更文件，`agent/**` **0** 个 | **2 项**：① 缺 review manifest；② 无 `stage=grill` 的 manifest |
| **#2** | `59b48f2`（实现 + 审阅收口，落了 `agent/**`） | 28 个变更文件，`agent/**` **5** 个 | **4 项**：上述 2 项 + ③ **无 `stage=grill-adversarial` 的 manifest** + ④ **无 `stage=building` 的 manifest**（原文：「本 change 改了受管控代码，必须有实现后的独立审阅证据」） |
| **#3** | `da861e8`（追加三份 witnessloop 形态 manifest） | 31 个变更文件 | **`check：通过 ✓`**，CI 四项全绿 |

**当前树复核**（我自己在 `da861e8` 上跑，不照抄）：

```
$ cd /home/happy/witnessloop && uv run witnessloop check --root /home/happy/ax-wt/guard-write-allowlist
check：基线 origin/master...HEAD，31 个变更文件，1 个 change 目录
  change：guard-write-allowlist
check：通过 ✓
```

**#1 → #2 的增量是本阶段最有信息量的一格**：同样一份「有 change 目录、有 spec delta、有审阅报告」的改动，**只因为 diff 触达了 `agent/**`**，witnessloop 就多要两条 stage 证据。⇒ 那两条**确实是 `code_hits` 驱动的**，不是「有 change 目录就要求」。

### 2.1 负向对照：定制 policy 是必需的，不是装饰

同一探针 diff（#2 的形态）换成 witnessloop **出厂** `require_change_for`，`building` / `grill-adversarial` 两条判定**消失**——出厂值是 8 条目录 glob（`src/**`、`lib/**`、`app/**`、`apps/**`、`packages/**`、`server/**`、`cmd/**`、`internal/**`，`src/witnessloop/constants.py:43-52`），对 asterwynd 的 `agent/` / `scripts/` / `web/` **一条都不命中**。本仓用的是定制 policy（`.witnessloop/policy.json` 的 `require_change_for = ["agent/**", "scripts/**", "web/**"]`）。

⇒ **#2 里多出来的③④两条，就是定制 policy 的功劳**；这也复现了阶段 A 的结论（出厂 policy 会让两个核心门禁**静默失效**）。这条是阶段 B 唯一一条**证伪型**证据：它用「去掉配置 ⇒ 判定消失」证明配置在起作用，而不是靠推理。

### 2.2 测试执行点确实在 CI 里跑

`gate.yml` 的 `adopter tests` 步实测 **4380 passed / 101 skipped**（CI 干净 runner）。本机跑同一命令会多 2 条环境失败（见 §7）。测执行点的内容就是 `.github/witnessloop-tests.txt` 的一行 `uv run --extra dev pytest -q`。

---

## 3.（对应 B.3）已知红：如实记录，并按**成因**分类

| # | 现象 | 成因分类 | 处置 |
|---|---|---|---|
| **K1** | active change `add-minimal-tui-runtime-view` 没有 `reviews/` 目录 ⇒ 报「缺少 review manifest」+「无 `stage=grill` 的 manifest」 | **不在本 change 的处置面内**——它是 in-flight change 的历史事实（阶段 A 已实测记录），不是配置错误 | 不修、不放宽判据；阶段 C 决策时必须一并考虑 |
| **K2** | 本 change 在 #1/#2 阶段的 findings（2 条 / 4 条） | **纯「证据尚未产出」**——阶段 B 的验收顺序就是「先跑出红、再补证据变绿」，故 #1/#2 的红是**预期过程态**，不是缺陷 | #3 补齐三份 manifest 后归零（`check：通过 ✓`） |
| **K3** | **本 change 归档后**，witnessloop 会把 `docs/openspec-change-backlog.md` / `openspec/specs/**` 的写入报成「受保护路径被写入但没有结构化解释事件」 | **工具不兼容（工具侧缺口）** | **不属配置错误**：证据其实齐（本 change 的 `workflow-events.jsonl` 有 10 条事件、其中 `current_spec_synced` ×3 + `backlog_updated` ×3 + `protected_artifact_explained` ×2 覆盖了这些路径）。机制见 §3.1 |

### 3.1 K3 的机制（我独立验证的，不是转述）

witnessloop 收集事件用的是**一级** glob：

```python
# src/witnessloop/events.py:83
for events_file in sorted(root.glob(f"{policy.changes_root}/*/{policy.events_file}")):
```

即 `openspec/changes/*/workflow-events.jsonl` —— 归档 change 的事件在 `openspec/changes/archive/<date>-<id>/workflow-events.jsonl`，是**两级**，**匹配不到**。在当前树上实测：

```
witnessloop 用的 glob：openspec/changes/*/workflow-events.jsonl
  命中 1 份；其中在 archive/ 下的：0 份
归档目录下的实际事件文件（两级）：80 份 —— 上面的 glob 一份都匹配不到
```

⇒ **本 change 一归档，它自己的 10 条事件对 witnessloop 立刻不可见**，而 diff 里 `openspec/specs/**` 等受保护写入仍在 ⇒ 报「没有解释事件」。这是**工具侧缺口**（`events_file` 只扫一级），**不是**我们漏了事件。**注意**：这一点我在本步**无法端到端复现**（本 change 尚未归档），结论由「glob 语义 + 80 份归档事件零命中」共同支撑；归档后复跑即可确认。

**配置面已知红：无。** 本 change 全程没有出现配置类红（policy 字段、执行点命令、保护路径表都一次写对）——这一点本身是阶段 B 的一个结论：**定制 policy 的正确性在真实需求上没有付出返工代价**。

---

## 4.（对应 B.4）分叉清单：本地 checker 与 witnessloop 在同一段 diff 下的判断差异

**同一段 diff（`fd6d581..da861e8`）下两侧的最终态**：asterwynd 的 artifact checker **绿**（`OpenSpec artifact checks passed`）、`openspec validate --all --strict` **30 passed**、witnessloop `check` **通过 ✓**。**最终态一致**。分叉出现在**中间态与判定面的口径**上，逐条如下：

| # | 分叉项 | 本地（asterwynd） | witnessloop | 依据 |
|---|---|---|---|---|
| **F1** | **孤儿规则** | 无此概念——`reviews/` 下的 `.md` 不要求被 manifest 绑定 | 一旦落任意一份 witnessloop 形态 manifest，`reviews/**/*.md` **每份**都要求被某份 manifest 的 `report_path` 绑定 | `src/witnessloop/contract.py:185-206`；本 change 因此必须**三份报告各配一份** manifest（`grill-design.md` / `grill-adversarial.md` / `building-review.md`） |
| **F2** | **manifest 命名 / 字段 schema** | `reviews/building-review-manifest.json`，字段用 `phase` / `reviewer_run_id` / `base_sha` / `head_sha` / `tasks_hash` / `spec_hash` / `diff_hash` / `report_hash` | `reviews/building.manifest.json`，必填 `stage` / `reviewer_run_id` / **`author_run_id`** / `base_sha` / `head_sha` / `tasks_hash` / `spec_hash` / `report_hash` / **`report_path`** | 两者**并存不冲突**：glob `reviews/*.manifest.json` 要求**字面** `.manifest.json` 后缀，而 asterwynd 的文件名后缀是 `-manifest.json`（连字符）⇒ **匹配不上**，互不干扰。本 change 的 `reviews/` 下 4 个 json 文件实测：`building-review-manifest.json` + `grill.manifest.json` + `grill-adversarial.manifest.json` + `building.manifest.json` |
| **F3** | **`tasks_hash` 的严格性** | active change **严格**比对 `tasks.md` 的字节 hash；**归档态跳过**（`agent/workflow/review_manifest.py:175` 的 `if not archived`） | witnessloop 的 manifest 也带 `tasks_hash`，但它的 §「stale 豁免」把 `changes/*/reviews/**`、`*/workflow-events.jsonl`、`archive/**` 列为 `stale_exempt_paths` ⇒ 证据之后只允许动这几类 | 两侧都要求「先内容、后证据」。**实测代价（本 change 亲历）**：审阅 PASS（绑 `4d8e048`）之后我做了两次 delta——第一次含一次 `tasks.md` 的改动，asterwynd 侧**立刻**报 `tasks hash mismatch` 且 artifact checker `EXIT=1`；把 `tasks.md` **还原成与 `4d8e048` 逐字节一致**后 checker 回到 `EXIT=0`。而 witnessloop 侧两次 delta 都不受影响（它的 head 仍绑 `59b48f2`）。⇒ F3 的实际形态是：**asterwynd 的 `tasks_hash` 对 active change 是「动一个字节就红」，而它又是唯一会让 checker 红的绑定面**（`design.md` / `tests/**` / `docs/**` 的改动都不触发任何 hash 校验，`_verify_git_span` 只比对 manifest 里固定的 base/head sha）。两者的差别不在「谁更严」，而在**绑定的面不同**：asterwynd 绑 `tasks.md` 的字节，witnessloop 绑 `reviews/**` 的清单一致性 |
| **F4** | **Open Question 的抽取面** | 只读 `reviews/grill-design.md` 的 `## Open Questions` + `## User Confirmation`，按 `- **Q<n>**:` 的**行内**编号逐条比对 | 读同一份报告的**正文完备性**（`## Confirmed Decisions` 的块数 + 每块的 `来源:`），并要求 manifest 存在 | 本 change 实测：两侧都绿，但**判据不同**——asterwynd 关心「问题被确认了没」，witnessloop 关心「决策记录写全了没」。设计期这两条口径曾经撞过号（`design.md` 记了 Q 编号必须两边一致），已在裁定阶段修掉 |
| **F5** | **`_EXTRA` 判据面向的差异** | 额外要求 RIR / Impact Analysis / benchmark smoke / 归档点完成度门 | **没有** archive 门禁，也不看 RIR / Impact Analysis | 这是「witnessloop 接管流程骨架、asterwynd 保留项目规则」的直接体现（`design.md` Decision 5 的八项保留清单） |

**最值得注意的两条**：**F1（孤儿规则的方向相反）** 与 **F3（同一 delta 两侧判红/判绿）**。F1 是「多绑一份 manifest 才安全」，本地 checker 没有任何等价约束；F3 说明**两侧对「证据何时算过期」的定义不同**，并存期必须同时满足两边，取**更严**的那个。

---

## 5.（对应 B.5）本地守卫的行为变化

**前置核验（必做，否则会把「放行」误读成「证据完备」）**：witnessloop plugin 的 guard shim 调的是 **PATH 上的裸 `witnessloop`**，且退出码映射是「`1` → 拦（映射成 CC 的 `exit 2`），**其余一律放行**（含旧版 CLI 的 `invalid choice` → 2）」。⇒ PATH 上若是**没有 `guard` 子命令**的旧版 CLI，整个守卫**静默空转**。本机实测 PATH 上那份是 **0.1.0、没有 `guard`**（`docs/development-guide.md` 的「witnessloop 影子接入」节记录了同一条）。

**行为变化的定性**（沿用阶段 A 的结论，本 change 未改变它）：接入 plugin 后本地多一个 `PreToolUse` 守卫，但本仓原有守卫**解析 Bash 命令**（`scripts/workflow_guard.py`，matcher `Write|Edit|Bash`），而 witnessloop 的 guard **只看 `Write|Edit`** ⇒ **本地拦截面变窄**，不是变宽。真锚始终是 CI required check。

**本 change 特有的两点观察**：

1. **在 building worktree 里观察不到本仓守卫**：`.claude/` 被 gitignore（`.gitignore:9`）⇒ worktree 下没有本仓 hook 的副本，本仓守卫只在主 checkout 生效。这与阶段 A 的实测一致，本 change 未复测（需要真装 plugin 的宿主）。
2. **本 change 的 diff 触达 `agent/**` ⇒ 与阶段 A 不同，`building` / `grill-adversarial` 两条判定真的会触发**（§2 的探针 #2 已证）。

**3. 实测（本步做的前置核验与安装面盘点）**：

```
# PATH 上那份 CLI
$ command -v witnessloop          -> /home/happy/.local/bin/witnessloop
$ witnessloop --version           -> witnessloop 0.1.0
$ witnessloop --help | grep -c guard  -> 0        # 没有 guard 子命令 ⇒ 装上也会静默空转

# 主 checkout 的 hook 面
$ cat /home/happy/my-agent/.claude/settings.json
  {"PreToolUse":[{"matcher":"Write|Edit|Bash","command":"cd ${CLAUDE_PROJECT_DIR:-.} && python3 scripts/workflow_guard.py"}]}
  ⇒ 只有本仓那一个守卫；**witnessloop plugin 没有安装**（.claude/ 下只有 commands/ skills/ settings.json worktrees/）

# building worktree
$ ls -d .claude  -> 不存在（.gitignore:9 忽略）⇒ 本仓守卫在这里也不生效
```

⇒ **B.5 的结论是「本次实测中本地守卫的行为变化为零」**：plugin 未安装 ⇒ witnessloop 的 `Write|Edit` 守卫在这两棵树上都不存在；而**即便装上**，PATH 上那份 CLI（0.1.0、无 `guard`）也会让 shim 按「其余 → 放行」静默空转。所以「双守卫并存」的**合并语义与报错归属两项仍然未实测**——不是漏做，而是**前置条件（PATH 上有一份带 `guard` 的 CLI）当前不满足**；把它列为阶段 C 开工前的前置核验项（`docs/development-guide.md` 的「本地 `guard` 的前置核验（必做）」节已写）。

这不影响 §2 的任何结论（那些来自 `check` 与 CI，不来自本地 guard）。

---

## 6.（对应 B.6）「值不值得真打开」的判断依据

### 6.1 findings 的可读性与可行动性

探针 #1/#2 的 findings 是**一句话 + 明确缺什么**（如「本 change 改了受管控代码，必须有实现后的独立审阅证据」），**没有误报**：K1/K2 两条都能逐条对上真实缺失。**可行动性**：修法唯一且明确（补对应 stage 的 manifest），本 change 的执行路径就是「`cd <witnessloop> && uv run witnessloop manifest build …`」三次。

**扣分项**：findings **不指出「证据已经存在但落点不对」**——例如 #2 时 `reviews/building-review.md` 已经存在（审阅 PASS 了），但 witnessloop 只认 manifest，报的是「没有 manifest」。这是**口径差异**（它的证据模型是 manifest 而非报告文件），**不是误报**，但读者第一次会误以为审阅没跑。

### 6.2 误报率

- **正向**：探针三态的 findings 全部可归因，**零误报**（每条都能指到具体缺什么）。
- **反向（真误报 / 结构性判不了绿）**：本 change **没有**遇到 grill 正文字段的红（见 §8）。
- **已知的将来误报**：K3（归档后 `events_file` 只扫一级 ⇒ 把已解释的写入报成「没解释」）——**这是工具侧缺口**，会在每个 change 归档后复发，且**本地 checker 判绿**。⇒ **并存期的误报成本主要由 witnessloop 侧承担**。

### 6.3 与本地 checker 的重复劳动量

同一份改动要**同时**满足两套证据模型：**同一份报告产出两份 manifest**（两套 schema、两次 `manifest build`），本 change 三份报告 ⇒ **三次 `manifest build`**（外加一轮 stale 顺序约束的重建）。**没有一条机器能替你判断「该绑哪份报告」**——`report_path` 要手填，且填漏一份就触发 F1 的孤儿规则。

### 6.4 对 in-flight change 的影响面

- 阶段 A 已记录的 K1（`add-minimal-tui-runtime-view`）**不因本 change 变化**。
- 本 change **未**放宽任何判据、**未**给它补历史证据。
- **新增一条**：本 change 自己在 PASS 后做一次 docs+tests delta，就让 asterwynd 侧 `tasks_hash` 变红（F3）⇒ 在「真打开」之前，**任何 PASS 后的文档改动都要重跑一次证据回路**。这条对 in-flight change 的影响是：**先攒完所有文档改动、最后一次性产证据**，否则要反复重建。

### 6.5 结论：**倾向「值得真打开」，但有三条前置**

**支持**：① 门禁真的拦得住（#1/#2 的红不是摆设，且 #2 的两条是 `code_hits` 驱动的、有负向对照证明配置在起作用）；② 与本地 checker **最终态一致**（§4 首段）、无假绿；③ 归档点的「完成度门」本地已有等价物、不冲突；④ 本 change 全程**零配置类红**、零返工。

**三条前置（按重要性）**：
1. **先修 K3**（`events_file` 的 glob 要能扫到 `archive/`）——否则每个 change 归档后都会带一条假红，而「真打开」时它是 required check。
2. **决定 F3 的处置**（PASS 后的文档 delta 到底算不算 stale）——现在两侧口径不同，取更严的话流程会显著变重。
3. **保留 asterwynd 侧的 RIR / Impact Analysis / 归档点完成度门**（F5）——它们在 witnessloop 里没有对应物。

**倾向性判断**：作为**流程骨架**（change 契约、证据绑定、stage manifest、受保护写入事件、测试执行点）值得打开；但它**不能替代**本地 checker，二者是 F5 的互补关系。打开前**必须先解决 K3**，否则会引入一条会复发的假红。

---

## 7.（对应 B.7）测试执行点的已知边界

执行点 = `.github/witnessloop-tests.txt` 的**一行**：`uv run --extra dev pytest -q`。

**覆盖到**：主回归面（全量 pytest，CI 实测 `4380 passed / 101 skipped`）。

**覆盖不到（四条，都在本仓 `validate` job 里照跑）**：
1. 浏览器用例——`dev` extra 含 `playwright`，但干净 runner 上没装 chromium ⇒ 相关用例 skip（101 skipped 里的一部分）；
2. 编码 warn-as-error 门（`ci.yml` 的 `PYTHONWARNDEFAULTENCODING=1` 变体）；
3. `openspec validate --all --strict`；
4. artifact checker（`check_openspec_artifacts.py`）。

**本机实测的环境差异**：本机跑同一命令会多 **2 条**环境失败——`test_session_workspace_add_nonexistent_path`（依赖 `tmp_path` 落在 `/tmp` 之下，与本机 `/tmp` 是 git 仓库有关）与本机 `/tmp/.git` 对 `TestFindScopeRoot` 的污染。**CI 干净 runner 上不存在**。⇒ 执行点在本机与 CI 上的结论可能差 2 条，读本机结果时要扣掉。

---

## 8.（对应 B.8）`来源:` 判据的归因——**阶段 A 的那条结论在真实需求上不成立**

阶段 A 记录过一条「已知阻塞」：**grill 正文判据结构性判不了绿**——理由是「本仓 grill 记录通篇用加粗 `- **来源**:`，而 witnessloop 的 `_SOURCE_RE` 不认加粗」。

**本 change 的实测推翻了「通篇加粗」这个前提**：

- 本 change 的 `reviews/grill-design.md` 用的是**同行裸 `来源:`**（`- **决策**: …；理由: …；来源: <run id>`）⇒ **source 判据 7/7 全命中**，witnessloop 侧**没有** `来源:` 类红。
- 全仓复核（用 witnessloop 自己的 `grill_evidence_findings` 跑 63 份归档 `grill-design.md`）：**39 份零 finding（判绿）**、9 份只缺 `来源:`、15 份其它；使用**加粗** `来源` 写法的只有 **3 份**（独占行 2 + 同行内联 1），且这 3 份**都被判 src-only**。

⇒ 正确口径是：**`来源:` 是「取决于我们怎么写报告」的可选择项，不是结构性不兼容**。阶段 A 把那份报告（`witnessloop-adoption` 自己）的局部事实写成了本仓通例。**归因分类**（按 `design.md` Decision 8 的三分类）：
- **格式选择导致的红**：本 change **没有**（因为我们用了同行裸写法）；它是**可避免**的。
- **工具不兼容**：K3（§3.1）—— 与本条**不同源**，且本 change **不打算**为它改本仓写法。
- **配置问题**：无。

**上游**：witnessloop issue #20（`_SOURCE_RE` 认不认加粗）**仍然是有效的前置**——只要有人用加粗写法，那 3 份归档就是反例。但**它不再是本仓 grill 记录的阻塞**：本仓主流写法（同行裸 `来源:`）本来就判绿。

---

## 9. 并存成本与体验摩擦（如实记）

1. **两套 manifest**：同一份报告要产出两份 manifest（两套 schema、两次 `manifest build`）；本 change 三份报告 ⇒ **三次 `manifest build`**。**没有工具帮你同步两者**——`phase` vs `stage`、`report_path` 的有无、文件名的 `-manifest.json` vs `.manifest.json`，全靠人记。
2. **`manifest build` 的执行者是「人（在本地）」**：`gate.yml` 只做 `check`、**不产证据**。⇒ 证据的产出**不在 CI 里**，靠人记得跑，且必须**在本地**用 witnessloop 源码树跑（本 worktree 裸跑 `uv run witnessloop` 会落到 PATH 上那份 0.1.0，测不到补丁版本）。
3. **顺序硬约束**：`manifest build` 必须在**所有内容提交之后**（stale 约束）。本 change 因此把「审阅 PASS 后的 docs+tests delta」与「重建证据」排成两步，多了一轮往返。
4. **孤儿规则的心理负担**：`reviews/` 下每多一份 `.md` 就要多一份 manifest；**少绑一份就红**。这让「在 `reviews/` 下随手写一份中间稿」变成有代价的动作（本 change 的 `grill-adversarial.md` 里保留了 R1 的证伪过程记录，就必须为它单独建 manifest）。
5. **PATH 上那份 CLI 是陷阱**：`plugin/hooks/guard.sh` 硬编码裸 `witnessloop`，而本机 PATH 上那份是 0.1.0（无 `guard`）⇒ 本地守卫静默空转。文档已写明，但**机器不会提醒**。

---

## 10. 小结（阶段 B 的交付判据逐条对照）

| 阶段 B 的出口判据 | 结论 |
|---|---|
| findings 清单 | §2 三态探针（2 → 4 → 通过）；§3 的 K1/K2/K3 三类 |
| 与本地 checker 的**分叉清单** | §4 的 F1–F5，逐条给依据 |
| 已知红清单 | §3（含 K3 的机制实证） |
| 体验摩擦清单 | §9 五条 |
| **按成因分类**的红清单 | §3 表 + §8 的三分类 |
| 「值不值得真打开」的判断依据 | §6：倾向值得，但三条前置（K3 必须先修） |

> **本报告不写 manifest**：按 `design.md` Decision 6，观测报告**不在 `reviews/` 下**，故不参与 witnessloop 的孤儿绑定，也不需要为它建 manifest。三份 witnessloop 形态 manifest 只绑定 `reviews/` 下的三份**审阅**报告。
