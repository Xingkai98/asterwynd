# 阶段 A 验收报告：witnessloop 影子接入

> 本文件是 `witnessloop-adoption` 阶段 A 的验收报告（tasks A.1.1 / A.1.2 / A.5.5 的落盘载体）。
> **它不是 `*-review.md`**，不参与本仓 checker 的 review-manifest glob（`scripts/check_openspec_artifacts.py:1150`）；
> 也**不是** witnessloop 形态证据——阶段 A 默认一份 witnessloop manifest 都不落（Decision 7 / A.5.6）。

## 1. 阶段 A 验收判据（A.1.1，测试先行）

> 写判据在先、落产物在后。以下 7 条在**产物落盘之前**写定，落盘后逐条填实测结果（各条证据见后续小节）。

| # | 判据 | 证据位置 | 结果 |
|---|---|---|---|
| ① | `init --dry-run` 待建文件 = **4 个**且**零冲突**（全为新建） | §3.1 | 见 §3.1 |
| ② | 本分支 PR 的 CI 里**出现** `gate / check` job 并**跑出结果** | §7.1 | 见 §7.1 |
| ③ | **触发面验证**：探针 diff（改 `agent/**`）下，定制 policy 让 `building` / `grill-adversarial` 两条 stage 判定**出现** | §5.1 | 见 §5.1 |
| ④ | **负向对照**：同一探针 diff 换**出厂 policy**，这两条判定**消失** | §5.2 | 见 §5.2 |
| ⑤ | `validate` / `benchmark-gate` 行为与本 change 前**逐字节一致**，branch protection 的 `contexts` **未变** | §6 / §7.2 | 见 §6、§7.2 |
| ⑥ | **双守卫实测**（A.4.5，主 checkout 与 building worktree **各一次**） | §8 | 见 §8 |
| ⑦ | **`reviews/` 处于一致状态**——「要么每份报告都有 witnessloop 形态 manifest，要么**一份都没有**」，**默认选后者** | §9 | 见 §9 |

**判据 ③ 为什么要用探针**：本 change 自己的 diff **不触** `require_change_for`（不改 `agent/**` / `scripts/**` / `web/**`）⇒ `code_hits` 为空 ⇒ `building` / `grill-adversarial` 两条判定**本来就不触发**，用本 change 自身**无法**验证触发面（只能用探针）。

**已被证伪而删除的原判据**：原「阶段 A 验收里第一次出现**绿的一侧**」——对抗轮实测证伪（样板 manifest 会激活孤儿规则，红数 2 → 14 → 16；且 grill stage 因 `来源:` 谓词结构性判不了绿）。见 `design.md` Decision 7。

## 2. 基线（A.1.2）

**采集时刻**：2026-10-13，阶段 A 开工前，分支 `witnessloop-adoption/2026-10-13`，HEAD `7c37ef1`，`origin/master` = `da3fd4f`。

命令：`gh api repos/Xingkai98/asterwynd/branches/master/protection`（**只读**，未 apply）

| 字段 | 基线实况 |
|---|---|
| `required_status_checks.contexts` | `["validate", "benchmark-gate"]` |
| `required_status_checks.strict` | `true` |
| `required_pull_request_reviews.required_approving_review_count` | `0` |
| `required_conversation_resolution.enabled` | `true` |
| `enforce_admins.enabled` | `true`（附记） |

**另记**：`.github/workflows/ci.yml` 的 sha256 基线 = `b5417b87e69af0556232a045be6ebabd7728e999c7e77eda3da102f57fea8a33`（供判据 ⑤ 的「逐字节不变」比对）。

## 3. A.2 定制 policy seed（仓外临时文件，不入库）

**seed 路径**：`/tmp/witnessloop-asterwynd-policy.json`（仓外；A.2.3 核过 `git status` 里没有它，入库的只有 init 写出的 `.witnessloop/policy.json`）。

**A.2.2 自查结果**（脚本断言，全绿）：

| 检查项 | 结果 |
|---|---|
| `protected_paths` **不含** `openspec/changes/archive/**` | ✓（Decision 3） |
| `review_manifest_glob` = `reviews/*.manifest.json`（**未**放宽成 `*-manifest.json`） | ✓（Decision 2） |
| `changes_root` = `openspec/changes` | ✓ |
| `required_artifacts` = `["proposal.md","design.md","tasks.md","specs","reviews"]`（与现有 change 目录必需件同形） | ✓ |
| `protected_paths` 与 `protected_write_event_types` 配套 | ✓ —— 三条受保护文档路径分别消费 `backlog_updated` / `protected_artifact_explained`，`openspec/specs/**` 消费 `current_spec_synced` |
| `require_change_for` = `["agent/**","scripts/**","web/**"]`（U2，不含 benchmark 目录） | ✓ |

**落地值**（与 `design.md` Decision 1 的定稿 JSON 一致）：`init` 写出的 `.witnessloop/policy.json` 逐字段等于 seed（init 对 `--policy` 是整份替换，不增删字段）。

### 3.1 判据 ①：`init --dry-run` 的待建文件

```
$ uv run witnessloop init --root <worktree> --dry-run \
    --policy /tmp/witnessloop-asterwynd-policy.json --test-command "uv run --extra dev pytest -q"
[dry-run] init 将创建（不落盘、不 commit）：
  + .witnessloop/policy.json
  + .github/workflows/witnessloop.yml
  + .witnessloop/init-manifest.json
  + .github/witnessloop-tests.txt
```

⇒ **4 个文件、全为 `+`（新建）、零冲突**（本仓 `.github/workflows/` 下只有 `ci.yml`）。**判据 ① 通过。**

## 4. A.3 接入产物与本地 `check`

### 4.1 产物清单与「`ci.yml` 未变」

| 产物 | 说明 |
|---|---|
| `.witnessloop/policy.json` | 定制 policy（定稿值见 §3） |
| `.witnessloop/init-manifest.json` | init 台账（`base_sha` = 落盘前 HEAD、三个文件的 sha256） |
| `.github/workflows/witnessloop.yml` | caller，`uses: Xingkai98/witnessloop/.github/workflows/gate.yml@v1` |
| `.github/witnessloop-tests.txt` | 内容一行：`uv run --extra dev pytest -q`（U4） |

**`.github/workflows/ci.yml` 逐字节未变**：落盘前后 sha256 均为 `b5417b87e69af0556232a045be6ebabd7728e999c7e77eda3da102f57fea8a33` ⇒ **判据 ⑤ 的「`ci.yml` 逐字节不变」成立**。

### 4.2 本地 `check` 的原始输出（A.3.3）

用 **witnessloop 仓源码版**（`uv run witnessloop`），`--root` 指向本 worktree：

```
$ cd <witnessloop> && uv run witnessloop check --root <worktree>
check：基线 origin/master...HEAD，16 个变更文件，1 个 change 目录
  change：witnessloop-adoption
check：未通过 ✗（2 项）
  1. openspec/changes/witnessloop-adoption：缺少 review manifest（审阅证据必须「报告 + manifest」成对，glob=reviews/*.manifest.json）
  2. openspec/changes/witnessloop-adoption：无 stage=grill 的 manifest（现有 stage：（无））——grill 决策记录必须有对应的审阅证据
```

**红数 = 2**，与 `design.md` U7 的预测**逐条一致**：两条都是「**缺 manifest**」这一类；`code_hits` 为空 ⇒ `building` / `grill-adversarial` 两条**未触发**；`来源:` 谓词那组**根本不会被触发**（没有 `stage=grill` 的 manifest，正文判据到不了）。

**两条附带观测**（不构成判据，如实记录）：
- 产物落盘**前**（未提交时）`check` 报的是同样 2 条——因为 `check` 的基线是 `origin/master...HEAD` 的**提交 diff**，未提交/未跟踪文件不在其中。**注意这个口径**：本地「未提交时跑 `check`」看不到新产物的影响。
- `.witnessloop/policy.json` 本身列在 `protected_paths` 里，但本 PR **新增**它**没有**产生「受保护路径被写入但没有结构化解释事件」的红——`init` 新增自身产物不触发该判定（与 `change_archived` 只认纯改名同理，本 change 未据此事先假设，是实测）。

## 5. A.3.4 触发面验证与负向对照（判据 ③/④）

**为什么必须用探针**：本 change 自己的 diff **不触** `require_change_for`（不改 `agent/**` / `scripts/**` / `web/**`）⇒ `code_hits` 为空 ⇒ 两条 stage 判定本来就不触发，无法用本 change 自身验证触发面。

**探针构造**（**隔离副本** `/tmp/wl-probe-a`，由 `git archive HEAD | tar -x` 重建，**不在被审 worktree 上操作**）：

```
base commit      = 本 change 的 HEAD 树（含已提交的接入产物）
origin/master    := base commit
probe commit     = 新增 agent/probe.py（2 行）
                 + 在 openspec/changes/witnessloop-adoption/design.md 追加 1 行注释
```

两处改动缺一不可：**只改 `agent/**` 不会让 stage 判定出现**——`stage_manifest_findings_in_change` 挂在「本次 diff 命中的 change 目录」循环里（`src/witnessloop/checkcmd.py:77` 的 `code_hits` 与 `:81 for change_id in change_ids`），`change_ids` 为空时循环一次都不进。第一次探针只改 `agent/**` 时实测输出是：

```
check：基线 origin/master...HEAD，1 个变更文件，0 个 change 目录
check：未通过 ✗（1 项）
  1. agent/probe.py：agent/probe.py 属于必须挂 change 的路径（policy.require_change_for），但本次 diff 里没有任何 change 目录（openspec/changes/<id>/）。…
```

（这条本身就是「定制 policy 的 `require_change_for` 生效」的旁证：出厂 policy 下同一条**不会**出现，见 §5.2。）

### 5.1 ① 定制 policy（探针 diff 下）

```
$ cd <witnessloop> && uv run witnessloop check --root /tmp/wl-probe-a
check：基线 origin/master...HEAD，2 个变更文件，1 个 change 目录
  change：witnessloop-adoption
check：未通过 ✗（4 项）
  1. openspec/changes/witnessloop-adoption：缺少 review manifest（…glob=reviews/*.manifest.json）
  2. openspec/changes/witnessloop-adoption：无 stage=grill 的 manifest（现有 stage：（无））——grill 决策记录必须有对应的审阅证据
  3. openspec/changes/witnessloop-adoption：无 stage=grill-adversarial 的 manifest（现有 stage：（无））——设计阶段的对抗验证轮（grill 之后、停轮之前的证伪环节）必须有审阅证据
  4. openspec/changes/witnessloop-adoption：无 stage=building 的 manifest（现有 stage：（无））——本 change 改了受管控代码，必须有实现后的独立审阅证据（review-loop）
```

⇒ **第 3、4 条（`grill-adversarial` / `building`）出现** = 触发面成立。**判据 ③ 通过。**

### 5.2 ② 负向对照：同一探针 diff 换**出厂 policy**

出厂 policy 由 `witnessloop init`（不带 `--policy`，在空 scratch 仓里生成）取出，**逐字节**覆盖探针副本的 `.witnessloop/policy.json`：

```json
{"schema":"witnessloop/policy@v1","changes_root":"openspec/changes",
 "protected_paths":["openspec/specs/**",".witnessloop/**"],
 "require_change_for":["src/**","lib/**","app/**","apps/**","packages/**","server/**","cmd/**","internal/**"],
 "required_artifacts":["proposal.md","design.md","tasks.md","specs","reviews"],
 "evidence":{"review_manifest_glob":"reviews/*.manifest.json","events_file":"workflow-events.jsonl",
             "protected_write_event_types":["protected_path_write"],
             "grill_stage":"grill","grill_adversarial_stage":"grill-adversarial","building_stage":"building"}}
```

```
$ cd <witnessloop> && uv run witnessloop check --root /tmp/wl-probe-a
check：基线 origin/master...HEAD，2 个变更文件，1 个 change 目录
  change：witnessloop-adoption
check：未通过 ✗（2 项）
  1. openspec/changes/witnessloop-adoption：缺少 review manifest（…）
  2. openspec/changes/witnessloop-adoption：无 stage=grill 的 manifest（现有 stage：（无））…
```

⇒ **第 3、4 条消失**，输出与「完全不带探针的基线」**逐字一致**（同为 2 条）。**判据 ④ 通过。**

**这是「定制 policy 必要」的证伪证据，不是推理**：同一段 diff、同一个 CLI，只换 policy，两条核心门禁从「出现」变成「静默消失」——正是 `design.md` Decision 1 说的「用出厂 policy 接入 = 接入名存实亡」。

**顺带核实**：出厂 policy 含 `grill_stage` / `grill_adversarial_stage` / `building_stage` 三个键，而本 change 的定制 policy 按 U1/U6 定稿值**不含**它们（走 witnessloop 默认值）——两条 stage 判定在定制 policy 下**照常出现**（§5.1 第 3、4 条），说明这三个键的缺省等价于默认值。**这是实测结论，不是推断。**

**另一条被现场推翻的测试方法**：不能靠「删掉 `.witnessloop/policy.json` 再看 `check`」来模拟出厂 policy——`check` 对缺失 policy **fail-closed**：

```
check：未接入 witnessloop ✗
  没有找到 .witnessloop/policy.json。门禁 fail-closed：未接入 = 不放行。
```

## 6. 回归确认（判据 ⑤ 的仓库侧）

| 检查 | 命令 | 结果 |
|---|---|---|
| 全量 pytest | `uv run --extra dev pytest -q` | `2 failed, 4331 passed, 9 skipped, 110 warnings in 446.07s` |
| OpenSpec strict validate | `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` | `Totals: 30 passed, 0 failed (30 items)` |
| 项目 artifact checker | `PYTHONPATH=. uv run python scripts/check_openspec_artifacts.py` | `OpenSpec artifact checks passed`（exit 0） |
| `ci.yml` 逐字节 | `sha256sum .github/workflows/ci.yml` | 与基线同为 `b5417b8…`（见 §4.1） |

### 6.1 那 2 条 pytest 失败：**环境性，与本 change 无关**（如实记录，不掩盖）

失败用例：`tests/agent/memory/test_persistent.py::TestFindScopeRoot::test_returns_none_for_non_git_dir` 与 `::test_malformed_git_file_falls_back_to_scan`。

**根因（已定位，不是猜测）**：两个用例都断言 `_find_scope_root(tmp_path) is None`，实测返回 `PosixPath('/tmp')`。`_find_scope_root`（`agent/memory/persistent.py:72-85`）向上走时**只判 `.git` 是不是目录**；而**本机 `/tmp/.git` 确实存在一个空目录**（`drwxr-xr-x 2 happy happy 4096 Sep 21 10:43`，非合法 git 仓库，`git rev-parse` 在 `/tmp` 下报 `not a git repository`），于是走查在 `/tmp` 处提前判定为 scope root。

**证伪实验**：把 pytest 的 `basetemp` 挪出 `/tmp`，同两个用例**全绿**：

```
$ uv run --extra dev pytest tests/agent/memory/test_persistent.py::TestFindScopeRoot -q --basetemp=/home/happy/wl-basetemp
.....                                                                    [100%]
5 passed in 1.36s
```

⇒ **与本次变更无关**（本 change 未触碰 `agent/**`，也未触碰任何测试）；属本机 `/tmp` 的环境坑（同类坑在 issue #226 的排查中已记录过一次）。**如实记录、不修、不掩盖**——修它属于另一个 change。

## 7. 本分支 PR 的 CI（A.5.1–A.5.3）

（PR 开出后回填：`gate / check` 是否出现并跑出结果、是否未进 required、`validate` / `benchmark-gate` 与 §2 基线逐项比对。）

## 8. 双守卫并存实测（A.4.5，判据 ⑥）

### 8.1 A.4.5.1 前置核验（必做，否则后面全是假象）

```
$ command -v witnessloop
/home/happy/.local/bin/witnessloop
$ witnessloop --version
witnessloop 0.1.0
$ witnessloop --help | grep guard          # 无输出
位置参数: init / uninit / check / manifest   ← **没有 guard**
$ witnessloop guard --root <worktree> --path <agent/…>
witnessloop: error: argument <命令>: invalid choice: 'guard' (choose from init, uninit, check, manifest)
$ echo $?
2
```

⇒ **PATH 上那份 CLI 没有 `guard` 子命令，退出码 2**；而 `plugin/hooks/guard.sh:38-41` 的映射是「`1` → `exit 2`（拦），**其余 → `exit 0`（放行）**」⇒ **plugin 守卫在真实 PATH 下静默空转**。**结论：本机装 plugin 也不会拦任何写入**；「放行」**不能**读作「证据完备」。`uv run witnessloop` 覆盖不到它（`guard.sh:32` 硬编码裸命令）。

### 8.2 A.4.5.2 合并语义与报错归属（**实测，非推理**）

方法：用 Claude Code `2.1.231` 的**真宿主**跑 `claude -p`（`--plugin-dir <witnessloop>/plugin`，`--permission-mode bypassPermissions`），让模型对一条 `agent/**` 路径发一次 `Write`。两个 hook 分别做可观测化：plugin 侧在 PATH 前置一个**记录调用并可控退出码**的 `witnessloop` shim（不修改 upstream plugin）；settings 侧用 `--settings` 注入一个**同样可控**的 hook。四次运行的实测：

| 运行 | settings hook | plugin hook | 实测结果 |
|---|---|---|---|
| A | 放行(0) | 拦(1→2) | **两侧都被调用**（settings 日志 1 行 + shim 日志 1 行）；Write **被拦**、文件未落盘；报错指名 `[bash "${CLAUDE_PLUGIN_ROOT}/hooks/guard.sh"]` |
| B | 拦(2) | 放行(0) | **两侧都被调用**（settings 日志 1 行 + shim 日志 1 行）；Write 被拦；报错指名 settings 那条 hook |
| C | 拦(2) | 拦(1→2) | Write 被拦；提示**只出其中一个**（本次出的是 plugin 那条） |
| D | 放行(0，**先睡 4s**) | 放行(0) | 两次调用时刻**相差 0.112s**（远小于 4s）⇒ **并行**；文件**落盘成功** |

**三项结论**（A.4.5.2 要求的）：

1. **两个 hook 是否都执行**：**都执行**。运行 A、B 各拦一侧，另一侧**仍被调用**（日志计数为证）。
2. **串行还是并行**：**并行**。运行 D 上一侧睡 4s，另一侧的启动时刻只差 **0.112s**。
3. **任一 `exit 2` 即拦，还是首个非零即终止**：**并集——任一 `exit 2` 即拦**（A、B、C 三次都拦），**不是**「首个非零即终止」（若是，B 拦下后 plugin 就不该被调用，但它的日志照样出现）。
4. **被拦时提示归属哪个守卫**：**只出一个**——CC 报的是其中一个阻断 hook 的命令原文 + 该 hook 的 stderr；**未阻断那一侧的 stderr 不出现**（运行 A 里 settings hook 打出的 `SETTINGS-HOOK-STDERR` 在提示中不可见）。

**附带实测**：`--permission-mode bypassPermissions` **不能**绕过 PreToolUse hook（运行 A/B/C 在 bypass 模式下照样被拦）。

### 8.3 A.4.5.3 两棵树各做一次

| 树 | `.claude/` | 实际观察 |
|---|---|---|
| 主 checkout（`/home/happy/my-agent`） | **有**（`settings.json` 的 `PreToolUse` matcher `Write\|Edit\|Bash` → `scripts/workflow_guard.py`） | 两个 hook 并存；实测对 `agent/probe-dual-guard.py` 的 `Write`：plugin hook 执行并拦住（`--root`/`--path` 指向主 checkout）；**本仓守卫对该 payload 放行**（直跑同 payload `exit=0`——该分支的 change 有 grill 证据，故不触发 `_grill_evidence_missing`） |
| building worktree（`/home/happy/ax-wt/witnessloop-adoption`） | **无**（`ls: cannot access '…/.claude': No such file or directory`） | 只能观察到 plugin 一个 hook（shim 被调 1 次、无本仓守卫消息） |

⇒ 与 `design.md` Decision 8 的预测一致：**worktree 下没有 `.claude/`**（`.gitignore:9` 忽略 + worktree 无副本），本仓守卫的 hook 只挂在主 checkout。**清理**：探针文件已删，两棵树 `git status` 均无我的残留（主 checkout 的 24 项未提交改动是用户既有改动，未被触碰）。

### 8.4 A.4.5.4 命令命名空间（静态判定）

`plugin/.claude-plugin/plugin.json` 的 `"name": "witnessloop"` ⇒ 命令命名空间化。**实测确认**（嵌套宿主 init 事件）：`slash_commands` 里出现 `witnessloop:grill` / `witnessloop:review-loop`，`plugins` 字段为 `[{"name":"witnessloop","path":"<witnessloop>/plugin","source":"witnessloop@inline","version":"0.1.0"}]`；与仓内 `.claude/commands/` 下的 `grill.md` / `review-loop.md` **不同名、不冲突**。

### 8.5 A.4.1 / A.4.2 / A.4.4：本地层与 CI 层

- **A.4.1 安装形态（与 design 的预设不同，如实记录）**：上游**没有 marketplace 清单**（`plugin/.claude-plugin/plugin.json` 存在，仓根**没有** `.claude-plugin/marketplace.json`）⇒ **没有 `claude plugin install` 这条路**。按上游 README 的既定分发方式，安装 = **启动参数** `claude --plugin-dir <witnessloop>/plugin`。因此 `claude plugin list` 显示 `No plugins installed` 是**正常的**，判定「真加载了」看会话 init 事件的 `plugins` 字段与 `witnessloop:*` slash command（§8.4 即以此判定）。
- **A.4.2 本地动作、不进 diff**：安装是启动参数，**连 `.claude/` 都不落**（比「`.claude/` 被 gitignore」更强）；实测安装前后 worktree `git status` 无新增。
- **A.4.4 两层互不依赖**：caller workflow（`.github/workflows/witnessloop.yml`）只 `uses:` 上游 `gate.yml@v1`，**不含任何 plugin 引用**；不装 plugin 时 CI 门禁照跑；装 plugin 也不改动 required（required 只能由 `platform_gate.py --apply` 改，见 §7 的实况比对）。

## 9. `reviews/` 的一致状态与已知红（判据 ⑦ / A.5.6）

### 9.1 判据 ⑦：选「一份 witnessloop 形态 manifest 都不落」

- **实测红数**：本 change 自身 **2 条**（§4.2），全部属「**缺 manifest**」类。
- **依据**（Decision 7 / A.5.6）：glob 匹配 0 份时 witnessloop 的 manifest 循环早退、孤儿规则**不执行**；一旦落**任意一份** witnessloop 形态 manifest，`reviews/**/*.md` 里每份未绑定 `report_path` 的报告都判孤儿，红数 **2 → 14 → 16**。⇒ 中间态比不落更红，**默认走「一份都不落」，K2 保持 2 条红**。
- **A.5.6.1 条件式样板**：**未启用**（不需要验证 `manifest build` 通路——那是阶段 B 的 B.2）。因此三条同时满足的约束在本阶段不触发。
- **A.5.6.2 执行者**：阶段 A **没有产出任何 witnessloop 形态证据**；`gate.yml` 只做 `check`、不产证据——本报告 §4–§5 的 `check` 输出全部是**人在本地跑**的。

### 9.2 A.5.6.3 中间轮产物的处置（**留给 v1，理由是「或」的另一支已满足**）

`reviews/` 下现有 4 份报告：`grill-design.md`、`grill-adversarial.md`（**最终版，R3 判 PASS**）、`grill-adversarial-v1.md`（R1 的原始轮）、本报告 `acceptance-stage-a.md`。

A.5.6.3 的两个分支：「清理中间轮产物」**或**「把最终版落到规范名 `grill-adversarial.md`」。**第二个分支已经满足**（最终版就在规范名上）。因此**不删** `grill-adversarial-v1.md`，理由两条：

1. 它是 R1「7 条阻塞」的**原始证伪记录**，被 `design.md` / `proposal.md` / `tasks.md` / `workflow-events.jsonl` 多处引用；删它会让那些引用悬空，属于「抹掉证据链」而非「收敛」。
2. **它的孤儿风险在当前状态下不成立**：阶段 A 一份 manifest 都不落 ⇒ 孤儿规则不被激活。真打开（阶段 B/C 建 witnessloop 形态证据）时这一整类问题会一起浮上来，已登记为 `tasks.md` 的 **N.6**（归档里非规范 `.md` 报告的孤儿化，另立 change 处理）。

### 9.3 已知红清单（K1 / K2）

| # | 对象 | 红的原因 | 处置 |
|---|---|---|---|
| **K1** | active change `add-minimal-tui-runtime-view` | 没有 `reviews/` 目录 ⇒ 缺 review manifest + 无 `stage=grill` 的 manifest | **不修**（给它补证据 = 替一个 in-flight change 补历史证据，会让「它到底实现了没有」的语义漂移）。留作阶段 C 「真打开」时必须一并决策的收尾项 |
| **K2** | **本 change 自己** | 缺 witnessloop 形态 manifest（本仓工具链只产 `phase` 形态）；且 `code_hits` 为空 ⇒ `building` / `grill-adversarial` 两条**本来就不触发** | **不修、不放宽任何判据**。阶段 A 不勾 required ⇒ 不造成实际拦截 |

**两条红都不挡合入、不挡归档**：阶段 A 的 `gate / check` 未进 required；本报告与 `tasks.md` 都不要求产出 witnessloop 形态 manifest。
