# Building Review: slim-gates

## Reviewer
- run id: review-slim-gates-20261018-r1（Round 1 开批）/ review-slim-gates-20261018-r2（修复验证）
- base/head: 528d02f / c424eff（Round 1 审阅 revision 为 4ada5c7）

## 任务逐项验证

- **0. 设计追问与对抗收敛：通过。** `reviews/grill-design.md` 含 6 条 `- **决策**:`（≥3）、`## Open Questions` 为「无」、`## User Confirmation` 记录 0 问；`reviews/grill-adversarial.md` Round 2 收口为空批、`## 闭环出口` 为 `PASS`。
- **1. 规格：通过。** 三份 delta 均已就地施加；`openspec/specs/dev-workflow-state-machine/spec.md` 已删除，`openspec/project.md` 能力域地图已移除该条目；`dev-workflow-gate` 的 `## Purpose` 已改写为现行形态（`openspec/specs/dev-workflow-gate/spec.md:7`）；`npx … validate --all --strict` 实测 29 passed / 0 failed。文档正文另有一条陈旧事实，见 I-8。
- **2. 测试先行：不通过（2.9）。** 2.1–2.8 的用例存在且 targeted 套件 222 passed；但 2.9「按 Decision 12 逐项核对」不成立：旧实现中「归档点不因未勾任务降级」的三条核心用例没有搬入，CLI 行为用例也有缺口，变异验证可静默放过回归，见 I-7。
- **3. 实现：部分通过。** 3.1 六条规则函数与旧实现逐函数对照一致（仅新增归档点 grill 证据函数）；3.3 示例 hook 已入库；3.4/3.5 删除面与 CI 步骤符合设计；3.6 文档主体已改写。3.2 的 Bash guard 存在可复现的常见命令绕过与策略损坏 fail-open，见 I-1～I-5。
- **4. 验证：部分通过。** 4.1 targeted 222 passed；4.2 全量实测 `2 failed / 4339 passed / 9 skipped`，两条失败均为 `tests/agent/memory/test_persistent.py::TestFindScopeRoot` 的 `/tmp` 环境坑，与基线同类同因；4.3 strict validate 29 passed；4.4 checker exit 0；4.5 `platform_gate.py --verify` 一致（5 字段全等）。4.6 本次未重跑 benchmark-gate（未发现与该命令相关的代码变化）；4.7 行为可复现但原始输出未入库；4.8 的证据是「命令级」harness，见 L-6/L-7。
- **5. 实现后独立审阅闭环：进行中。** 本报告即 5.1 的 Round 1 开批；5.2/5.3 待在修复验证后收口。
- **6. 证据与归档：未开始（预期）。** active change 仍有未勾任务，尚未写事件/归档/manifest；归档点门尚未启用。
- **7. 合入之后：未开始（预期）。** 全部 `(post-merge)` 标记正确。

### 横切核对

- **删除面：通过。** `agent/workflow/*`、`scripts/{workflow_state,workflow_guard}.py`、`scripts/{flow-policy,workflow_methods}.json`、对应 7 个测试文件均已删除；全仓非归档代码/文档无对这些模块的活 import 或活命令引用。`tests/agent/workflow/` 与 `agent/workflow/` 仅剩 `__pycache__`（未进 git）。
- **platform gate 四项：通过。** `scripts/platform_gate.py`、`scripts/platform-gate.json`、`tests/test_platform_gate.py`、`openspec/specs/platform-gate/spec.md` 均在 `origin/master..HEAD` 中零改动，`--verify` 与实况一致。
- **历史数据：通过。** `openspec/changes/archive/**` 与全部 `workflow-events.jsonl` 在本次 diff 中零改动。
- **有界批次模型守卫：通过。** `tests/test_round_model_alignment.py` 仍覆盖 ALLOWLIST、per-file 要素与旧口径负例；被删除的只有已退役状态机规格的两处条目与一个专用单测，`scripts/check_openspec_artifacts.py` 的提示文案断言仍在。
- **CI：通过。** `.github/workflows/ci.yml` 只改 `validate` 的 checker 步骤与 `fetch-depth` 注释，删除 `Check archived changes`；`benchmark-gate` / `windows-platform` / `witnessloop.yml` 未动；`--base-ref` + `--require-base` 可用（空值实测回退 merge-base 并仍求值归档门）。
- **Checker 判据一致性：通过（除新增归档点 grill 证据外）。** 与 `528d02f` 共有的 20 余个函数逐字比较无差异；`AR` + base 树、非日期归档、`(post-merge)` 变体、`## 闭环出口` 全参数表、backlog、RIR、Impact、benchmark smoke 均未放宽。新增归档点 grill 证据的触发面为「非 docs + DESIGN_TYPES + spec delta」，不会误伤 bugfix/docs/无 spec delta。

## 批次（blocker/high/medium）

- **I-1（medium）｜policy 是合法 JSON 但形状不对时 guard fail-open，而不是退回内嵌默认表。** 证据: `scripts/bash_write_guard.py:79-93` 直接对解析结果调用 `data.get(...)`，没有先判 `isinstance(data, dict)`；异常被 `scripts/bash_write_guard.py:598-600` 的兜底 `except` 吞掉并放行。复现: 在临时 root 写 `.witnessloop/policy.json` 为 `[]`，运行 `python3 scripts/bash_write_guard.py --root <root> --command 'echo x > agent/y'` → stderr `parser error ('list' object has no attribute 'get'); allowing command.`、exit 0；期望 exit 2（用内嵌默认表继续判）。这违反 `openspec/changes/slim-gates/specs/dev-workflow-gate/spec.md:205`「policy 缺失或损坏时 SHALL 使用内嵌默认表继续判定，SHALL NOT 因加载失败直接放行」。修法：`_load_policy` 中非 dict / 缺字段都走默认表分支，只有真正的解析器异常才 fail-open。
- **I-2（medium）｜嵌套 shell 与包装前缀的组合形态绕过：`timeout 5 bash -c`、`nohup sh -c`、`bash -lc`、`bash -ec`、`sudo -u root touch`、`nice -n 10 touch`、`env -i touch` 全部放行。** 证据: `scripts/bash_write_guard.py:477-482` 的前缀剥离只弹掉前缀名本身（以及 timeout 的时长），不跳前缀的选项/值；`scripts/bash_write_guard.py:571-575` 的嵌套 shell 判定发生在 `_command_targets` 剥离前缀之前，且只认单词 `-c`，不认 `-lc` / `-ec`。复现: `evaluate_command("timeout 5 bash -c 'touch agent/y'", root)`、`("nohup sh -c 'echo x > agent/y'", root)`、`("bash -lc 'echo x > agent/y'", root)`、`("sudo -u root touch agent/y", root)`、`("nice -n 10 touch agent/y", root)`、`("env -i touch agent/y", root)` 均返回 `[]`；对照 `sudo touch agent/y` 会被拦。这违反 delta `spec.md:205`「递归解析 `bash -c` / `sh -c`」，且属于常见命令形态而非已登记的对抗性绕过。修法：先把包装前缀（含其选项与值）统一归一化，再判定嵌套 shell；`-c` 按「短选项簇包含 c 且后续参数为命令串」识别。
- **I-3（medium）｜`git -C <dir> restore` / `--git-dir=` / `--work-tree=` 让显式路径的 restore/checkout 漏检。** 证据: `scripts/bash_write_guard.py:519-521` 弹掉 `-C <dir>` 后丢弃目录、未调整 cwd，也不识别 `--git-dir=…` / `--work-tree=…` 的等号形态；后续目标按仓库根归一化。复现: `git -C agent restore y`（实际恢复 `agent/y`）、`git --git-dir=.git restore agent/y`、`git --work-tree=. checkout -- agent/y` 均返回 `[]`；对照 `git -C . restore agent/y` 会被拦。delta `spec.md:199` 要求显式路径命中受管/受保护时阻断。修法: `-C` 的值参与 cwd 计算；等号形态同样剥离/识别。
- **I-4（medium）｜紧凑输出参数与 `>&` 重定向不被识别。** 证据: `scripts/bash_write_guard.py:48` 的 `_REDIRECT_OPS` 不含 `>&`；`scripts/bash_write_guard.py:416-423` 的 `_output_arg` 只匹配「独立 flag + 下一参数」或 `--long=value`。复现: `curl -oagent/y https://x`、`wget -Oagent/y https://x`、`cmd >& agent/y` 均返回 `[]`；对照 `curl -o agent/y …`、`wget -O agent/y …`、`cmd &> agent/y` 会被拦。delta `spec.md:191` 把重定向与 `curl -o` / `wget -O` 列为拦截面，紧凑写法是同一选项。修法: 短选项值粘连形态（`-oPATH` / `-OPATH`）纳入解析；`>&` 与 `&>` 同等处理。
- **I-5（medium）｜HEAD 上 `python -c` 只识别带 `/` 的路径，写到受管目录本身时漏检。** 证据（审阅 revision `4ada5c7`）: `scripts/bash_write_guard.py:466-469` 的路径正则要求 `agent|scripts|web` 后必须跟 `/`。复现: `python -c "import shutil; shutil.rmtree('agent')"`、`python -c "open('scripts','w')"` 均返回 `[]`；`open('agent/y','w')` 会被拦。工作区目前有一份未提交的 `_python_code_targets` 正则修改（把后缀改为可选并加边界）可覆盖该形态，但不在 `base..HEAD` 审阅面；需作为正式提交落盘并由本批验证。
- **I-6（medium）｜两份规格对「瘦 checker 是否检查 grill 证据」互相矛盾。** 证据: `openspec/changes/slim-gates/specs/change-documentation/spec.md:16`（施加后 `openspec/specs/change-documentation/spec.md:41`）无条件写 “The slim project-rule checker SHALL NOT check grill evidence.”；同一施加后规格 `:201-203`、`:215` 又写归档点 grill 证据属于归档完成度规则，`dev-workflow-gate` delta `:157` 明确要求非 docs + DESIGN_TYPES + spec delta 的新归档检查 grill 证据，实现也这么做（`scripts/check_openspec_artifacts.py:1046-1089,1139-1142`）。复现: `grep -n "SHALL NOT check grill\|archive-point grill" openspec/specs/change-documentation/spec.md` 同时命中两套口径。这是设计对抗 D-1 的残留（只修了 Mechanical artifact checks 一行，未修 Pre-implementation design grilling 段落）。修法: 把 `:16` 改为「不检查 active-stage grill 证据；归档点 grill 证据属于归档完成度（见 dev-workflow-gate rule 4）」。
- **I-7（medium）｜旧 checker 的核心归档点反绕过用例未搬迁，测试对关键判据没有牙齿。** 证据: 旧 `528d02f:tests/test_openspec_artifact_checker.py` 的 `test_archived_gate_requires_grill_evidence_even_when_tasks_incomplete`（:2232）、`test_archived_gate_flags_unconfirmed_open_question_when_tasks_incomplete`（:2262）、`test_archived_gate_rir_content_threshold_applies_when_tasks_incomplete`（:2281）在 `tests/test_slim_project_rules.py` 中没有对应用例（`grep` 无命中）；CLI 侧的 `test_bare_check_does_not_trace_historical_archives`、`test_empty_base_ref_does_not_skip_checks`、`test_explicit_base_ref_still_wins` 同样缺失。变异复现: 把 `scripts/check_openspec_artifacts.py:1118` 的 `assume_implemented=True` 改为 `False`（即让归档点 RIR 内容门槛因未勾任务失灵），`uv run pytest -q tests/test_slim_project_rules.py` 仍 **73 passed**。这违反 `dev-workflow-gate` delta `:186-187`「旧实现已覆盖的边界 SHALL 继续被测试覆盖」与 design Decision 12 的映射表；tasks 2.9 的 [x] 不成立。修法: 原参数表搬入至少这三条归档点用例，并补空/空白 `--base-ref` 不跳过检查、`--skip-backlog`、`--change` 模式的 main 级用例。
- **I-8（medium）｜`openspec/project.md` 仍把已退役的文档形状检查写成现行机械检查。** 证据: `openspec/project.md:61` 写「`diagnosis.md` 属于项目条件规则，由项目本地文档规则脚本检查」；`:63` 写「项目本地脚本只做机械校验：`Change Type` 合法、文件存在、必填章节存在、章节非空、没有模板占位符、条件验证项存在、backlog 不引用已归档或不存在的 change」。本 change 的 Decision 11 已明确退役 design/diagnosis 必填章节与占位检查，瘦 checker 只保留六条规则（`scripts/check_openspec_artifacts.py` 中已无 `_check_required_sections` / `_check_design_review_task`）。复现: `grep -n "必填章节\|diagnosis.md" openspec/project.md`。后果: 后续 agent 会误以为 diagnosis/设计章节仍被机械兜底。修法: 改成「六条项目规则 + Change Type 前置解析」的准确描述，并注明 diagnosis/design 章节由人工评审负责。

## low/nit 登记

- **L-1（low）｜瘦 checker 残留死代码与指向已删除文件的注释**：`scripts/check_openspec_artifacts.py:457-462`（HANDOFF / VALID_PHASES 常量，无消费者）、`:903-910`（四个事件常量与 `_POLICY_REL_PATH = scripts/flow-policy.json`，后者文件已删除且注释仍称「受保护路径规则从 flow-policy.json 加载」）、`:1018-1025` 第二次定义 `PLACEHOLDER_ONLY`（覆盖前一处且少一个 token，行为与旧实现一致但重复）、`:152-153` 与 `:970-971` 仍引用 `workflow_guard._h2_section` / `workflow_guard._extract_user_confirmation_indexes`。理由: 无行为影响，归档前顺手清理即可，不单开 medium。
- **L-2（low）｜`docs/known-debt.md:120-123` 仍以现在时描述已删除 guard 的 awaiting 硬拦截**：「保留且不弱化——`scripts/workflow_guard.py` 的 `_awaiting_block_reason` 仍会……」。文件顶部横幅已声明旧脚本提及属历史记录，但该段本身没有退役标记，读者可能以为 awaiting 当前仍被执法。理由: 纯文档口径，随 known-debt 历史化改写处理。
- **L-3（low）｜here-doc 正则与命令替换解析的两个边界绕过**：`_strip_heredocs`（`scripts/bash_write_guard.py:168-187`）不区分引号，`rg 'x <<EOF' &&\necho x > agent/y\nEOF` 会把后续命令行当 heredoc 正文吞掉（实测放行）；`_collect_substitutions`（`:190-242`）不感知括号内引号，`echo "$(echo ')'; touch agent/y)"` 也会漏检（实测放行）。理由: 形态刻意且不常见，guard 定位是本地 checkpoint；已在测试中登记更常见的残余绕过面。
- **L-4（low）｜T4c 的 parity 测试只比较「内嵌默认表 == policy.json 列表」，没有比较匹配语义**：`tests/test_bash_write_guard.py:161-165`；实现 `_matches`（`scripts/bash_write_guard.py:127-136`）对 `agent/**` 额外匹配目录本身 `agent`，而 witnessloop v1.7.0 `paths.matches_any` 不匹配（`paths.py:52-57`）。这只会多拦 `rm -rf agent` 一类目录删除，方向安全，但「与 witnessloop 同款语义」的规格表述不精确。理由: 无放宽风险；补一条对照测试或改措辞即可。
- **L-5（low）｜`python -c` 写调用判据不区分读写，存在只读误伤**：`_WRITE_CALL_RE`（`scripts/bash_write_guard.py:54-57`）把任意 `open(` 当写调用，`python -c "print(open('agent/loop.py').read())"` 会被拦。旧实现同样如此，不是回归；但与 design 所述「`open(..., 'w')` / `write_text` 等写调用」不一致。理由: 本地 checkpoint 偏保守，记录为已知误伤即可。
- **L-6（low）｜tasks 4.8 的证据是「命令级」harness，不是任务要求的临时 Claude Code settings 同时安装实测**：`docs/development-guide.md:440-441` 自述「命令级」，`tasks.md` 4.8 要求「在临时 Claude Code settings 中同时挂」并禁止用「分别调用」冒充；文档另以阶段 A 的真实 CC 2.1.231 记录补足合并/并行/并集语义。理由: 阶段 A 已实测 CC 调度语义，新 guard 只是另一个 command hook，行为问题（哪个 hook 看哪个工具）已由表格回答；若不接受组合证据，应在 CC settings 中重跑一次并替换表格。
- **L-7（low)｜tasks 4.7 要求「记录原始输出」，仓库内只有结论没有原始命令输出**：`tasks.md` 4.7；建议把 4.7/4.8 的原始命令与输出写进 PR 描述或 tasks 行内。
- **L-8（nit）｜`docs/development-guide.md:419` 仍是将来时**「本 change 的 4.8 会按同一方法再记录一次」，而 4.8 已勾选、记录已在下方表格。
- **L-9（low，Round 1 I-7 残留）｜CLI 级补充用例仍未补**：空/空白 `--base-ref` 不只是「解析为非空」，还要断言不跳过归档门；`--skip-backlog` 与 `--change` 模式也没有 main 级用例（旧测试 `test_empty_base_ref_does_not_skip_checks`、`test_bare_check_does_not_trace_historical_archives`、`test_explicit_base_ref_still_wins` 未迁移）。理由：`_resolve_base_ref` / main 的归档门调用是逐字搬运且本轮手工验证通过，风险低于三条归档反绕过用例；补测试即可，不需改判据。

## 验证（Round 1 批次，revision c424eff）

> 只核对 I-1…I-8 的修复落点与测试牙齿；验证期新发现的 medium+ 只进下方 deferred。测试在 `c424eff` 的脚本/测试快照上运行（`/tmp/verify-c424eff`），未使用工作区未提交改动。

- **I-1 已修复。** `scripts/bash_write_guard.py:79-84` 新增 `isinstance(data, dict)` 拒绝分支并退回内嵌默认表；`tests/test_bash_write_guard.py:173-175` 的 `test_non_object_policy_falls_back_to_embedded_defaults` 在 `c424eff` 上通过。变异（删掉该分支）实测该用例 1 failed。
- **I-2 已修复（已报告形态）。** `scripts/bash_write_guard.py:496-529` 的 `_unwrap_prefixes` 在嵌套检测前剥离 `sudo`/`env`/`timeout`/`nice`/`nohup`/`command` 的选项与值；`:532-542` 的 `_nested_shell_code` 支持 `-c`、`-lc`、`-ec` 与紧贴参数。`tests/test_bash_write_guard.py:89-96` 覆盖 `timeout 5 bash -c`、`nohup sh -c`、`bash -lc`、`bash -ec`、`sudo -u root`、`nice -n 10`、`env -i`，全部通过；变异（改回只认 `-c`）实测 2 failed。
- **I-3 未完全修复（本轮不通过）。** `c424eff` 上 `git -C .`、`git --git-dir=.git`、`git --work-tree=.` 已能拦截并有测试；但 Round 1 报告的首要复现 **`git -C agent restore y`（以及 `git -Cagent restore y`、`git -C agent checkout -- y`）在 `c424eff` 上仍放行**：`scripts/bash_write_guard.py:584-596` 在 `-C` 分支里仍直接丢弃目录、未把它并入目标路径归一化。实测（c424eff 快照）三者均 `evaluate_command(...) == []`。工作区现有未提交的 `git_cwd` 修复与两条 `git -C agent` 测试可覆盖该形态，但不在审阅 revision；提交并复验后方可关闭。
- **I-4 已修复（已报告形态）。** `_REDIRECT_OPS` 加入 `>&`（`scripts/bash_write_guard.py:48`），`_output_arg` 支持紧贴短选项值（`:430-431`）。`curl -oagent/y`、`wget -Oagent/y`、`cmd >& agent/y` 均被拦；对应参数化用例通过；变异（去掉 `>&` 或删掉紧贴分支）分别实测 1 failed / 2 failed。
- **I-5 已修复。** `scripts/bash_write_guard.py:466-478` 的路径正则支持不带 `/` 的受管根；`shutil.rmtree('agent')`、`open('scripts','w')` 被拦，`print('agent')` / `print('agent/y')` 仍放行；对应用例通过。变异（还原旧正则）实测 3 failed。
- **I-6 已修复。** delta 与 applied spec 同句均改为「不重复 active-stage grill 检查；归档点 grill 证据按 `dev-workflow-gate` rule 4 检查」（`openspec/changes/slim-gates/specs/change-documentation/spec.md:16`、`openspec/specs/change-documentation/spec.md:41`），与 `dev-workflow-gate` rule 4 及实现一致；grep 无残留的无条件 `SHALL NOT check grill evidence`。
- **I-7 已修复（核心反绕过）。** 新增 `test_archive_rir_content_threshold_applies_when_tasks_incomplete`、`test_archive_grill_evidence_required_even_when_tasks_incomplete`、`test_archive_unconfirmed_open_question_when_tasks_incomplete`（`tests/test_slim_project_rules.py:612-663`），在 `c424eff` 上通过；把 `assume_implemented=True` 改成 `False` 后第一条实测 1 failed。CLI 级补充用例（空/空白 `--base-ref` 不跳过检查、`--skip-backlog`、`--change`）仍未补，降级登记为 L-9，不阻断本轮。
- **I-8 已修复。** `openspec/project.md:54-56,61,63` 已把类型并集章节、capability 映射/current spec 同步任务、diagnosis 机械检查改为退役或人工评审；末段改为六条规则。grep 不再有条件规则旧口径。
- **low 修复核对。** L-1 的 `flow-policy` 事件常量、`_POLICY_REL_PATH` 与 `workflow_guard` 注释已删除；HANDOFF 常量与重复 `PLACEHOLDER_ONLY` 仍在（L-1 保留）。L-7 已补 4.7 手动验收表；L-8 已改成已记录。L-2/L-3/L-4/L-5/L-6 未处理，保留为 low。

### 机械复核（修复轮）

- `c424eff` 快照的 `tests/test_bash_write_guard.py` + `tests/test_slim_project_rules.py`：**192 passed**；工作区 targeted 套件 **238 passed**（另含 round-model / platform-gate）。
- `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`：29 passed / 0 failed。
- 瘦 checker：`uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` exit 0（在本报告写 CHANGES_REQUESTED 前；写入后 active 宽触发会按预期转红，待下一轮 PASS 覆盖）。
- 工作区另有两处**非本次验证产生的未提交改动**（`scripts/bash_write_guard.py`、`tests/test_bash_write_guard.py`），包含 I-3 子目录修复；不在 `c424eff` 审阅面内，未计入本轮通过。

## deferred（验证期若发现新 medium+ 才写）

- **D-1（medium，下一批）｜组合短选项簇仍能绕过 `curl` / `wget` / 嵌套 shell 解析**：`scripts/bash_write_guard.py:427-431` 只识别「输出 flag 位于参数开头」的紧贴值；`wget -qO agent/y …`、`wget -qOagent/y …`、`curl -so agent/y …` 实测放行。`_nested_shell_code`（`:532-542`）取 `c` 后的残余字符作为命令串，`bash -cl 'touch agent/y'` 实测放行（`-cl` 中 `l` 被当成命令串）。这是本轮修复同一解析面的残余，需在下一批处理。

## 闭环出口
CHANGES_REQUESTED（I-3 未完全修复：c424eff 上 `git -C <subdir> restore <relpath>` 与 `git -C <subdir> checkout -- <relpath>` 仍放行；I-1/I-2/I-4/I-5/I-6/I-7/I-8 已验证通过。工作区未提交的 `git_cwd` 修复可覆盖 I-3，提交到审阅 revision 并复验后收口。）
