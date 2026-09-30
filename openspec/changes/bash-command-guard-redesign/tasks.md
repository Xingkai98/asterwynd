# Tasks: Bash 命令护栏的单一解析管线重构

> 测试先行（TDD）：每个实现任务前的测试任务先落地为失败用例，再写实现。
> **本版为 grill 后 + 用户拍板后修订版（v3）**：首版经 4 个独立零记忆 subagent 追问后发现 9 项阻塞问题，其中「heredoc→解释器会静默变成漏报」是首版自身引入的安全回归；5 条 Open Question 已由用户于 2026-09-30 拍板（`reviews/grill-design.md` 的 `## User Confirmation`）。修订见 `reviews/grill-design.md` / `reviews/grill-settled.md`，回写见 design.md 的 D3/D4/D6/D8/D9/D10/**D12**。
> 完成度门禁：closeout 类任务（PR 合入后才执行）标注 `(post-merge)`。

## 0. 设计追问（实现前门禁）

- [x] 0.1 跑 `batch-grill`（独立零记忆 subagent 审视 design.md），产出 `reviews/grill-design.md`（≥3 Confirmed Decisions 且每条带 `来源:` + Open Questions）。**4 个独立零记忆 subagent、四种视角（绕过面 / 成本 / 可行性 / 证据审计）并行执行**，合计 9 项阻塞问题 + 5 项待用户拍板的 Open Question。
- [x] 0.2 停轮把 `## Open Questions` 逐条抛给用户（每条配具体场景例子），答复记录进 `## User Confirmation`。**用户于 2026-09-30 拍板 Q1–Q5**（含 Q3 三条子决定）；Q3 经三轮补测（用户追问「调试配 API key 怎么写 `.env`」引出），补测证据见 `reviews/grill-settled.md`。**grill gate 已放行，可写实现代码。**
- [x] 0.3 把拍板结论回写进 `design.md`（D3/D4/D6/D8/D9/D10/D12）、本 `tasks.md` 与 spec delta；更新 `## Pre-Implementation Review`。

## 1. 解析层：tree-sitter-bash 接入与 IR 构造（D1/D2）

- [x] 1.1 `pyproject.toml` 新增 `tree-sitter-bash` 依赖并写入 `uv.lock`（grill 指出首版实验依赖未入锁、实验不可复现；已 `uv add tree-sitter-bash`→`pyproject.toml:45`，`uv.lock` 锁定）。确认 wheel 在本机安装成功（226.5 KiB，cp310-abi3，manylinux/macos/win 覆盖完整、无需编译器）。
- [ ] 1.2 **测试先行**：IR 契约测试——同一语义的不同写法产出相同 IR（`rm -rf /` / `rm -fr /` / `rm -r -f /` / `rm -rf -- /`）；**且 per-field 断言**（redirect / env_assign / dynamic / heredoc 绑定 / write_targets 各自单独断言，不只比整树——grill 的 140 行原型第一次就把 redirect 提取写错）。
- [ ] 1.3 新增 `agent/tools/bash_ir.py`：用 `tree_sitter_symbols.py` 同款写法加载 bash 语法，用 `Query("(command) @c")` + `QueryCursor` 构造 IR。**禁止递归 Python 遍历**（实测 ~2,000 字符 `$(( ))` 触发 `RecursionError`）。
- [ ] 1.4 IR 字段：`segments[]`（argv）、**`write_targets[]`**（由 per-command spec 解析，含 `-t`/`--target-directory`/`of=` 携带形式）、`redirects[]`（fd/操作符/目标）、`env_assignments[]`、`dynamic_words`（bool + 位置）、`parse_errors`（bool + 位置 + `is_missing`）、`unsupported_nodes[]`、**`heredoc[]`（delim + body 节点 + 绑定 fd + 消费方命令）**、`source_span`。
- [ ] 1.5 **测试先行**：heredoc 的 IR 必须记录**绑定关系**（delim / body / 绑定到哪个命令的 stdin），而不只是「不产生 segment」。这是 D4 heredoc 规则的前提。
- [ ] 1.6 **测试先行**：错误信号覆盖——`has_error` 与零宽 `is_missing` 两条都被捕获。**注意**：`rm -rf !(keep)` 实测 `has_error=True`（grill 更正首版措辞），且此时 `(command)` 捕获退化为 `['rm -rf !', 'keep']`（argv 是垃圾）⇒ 断言「`parse_errors` 命中时禁用 argv」。
- [ ] 1.7 **测试先行**：预算与深度——节点数/输入长度/嵌套深度上界命中时返回确定处置而非崩溃。
- [ ] 1.8 **测试先行**：解析器**从不抛异常**契约（空串、纯空白、未闭合引号、NUL 字节、`$((`、超深嵌套）。
- [ ] 1.9 **测试先行**：枚举命令节点**不得递归**——构造 ~2,000 字符的 `$(( … ))` 断言不抛 `RecursionError`，且 `QueryCursor` 路径正常返回。

## 2. evaluator 层：三套机制合并为消费 IR 的 evaluator（D2/D7/D9）

- [ ] 2.1 重定向 evaluator 改为读 IR 的 `redirects[]`；保留 `/dev/null` 族豁免与分量边界判定；**新增敏感点目录判定**（复用 `_dest_is_sensitive`）——`echo X > .env`、`cat payload > ~/.ssh/authorized_keys` 当前 allow。
- [ ] 2.2 `_check_rm` / `_check_mv_cp` / `_check_chmod` / `_check_curl_wget` 改为读 IR 的 argv 与 `write_targets`；新增 **`dd`**（`of=` 目标）与 **`tee`**（目标）evaluator；`_normalize_path` / `_within` / `_is_device_exempt` 语义不变（D7）。
- [ ] 2.3 **测试先行**：写目标**经选项传递**——`cp -t .env x`、`mv --target-directory=.env x`、`install -t .env x` 必须被判 deny/ask（当前全 allow，因 `_check_mv_cp` 只读 `args[-1]`）。
- [ ] 2.4 **测试先行**：`cp x ~/.{ssh}/f`（brace）被判 deny/ask，目标不得被销毁；对照 `cp x .env.example` 仍放行。
- [ ] 2.5 **测试先行**：`cat <<'EOF'` + `cp x .env` + `EOF` 从 deny 变 allow（修误报），并确认 `grep -rn "cp x .env" docs/` 仍放行。
- [ ] 2.6 **测试先行**：`eval 'cp x .env'`（引号载荷）与 `eval cp x .env` 判定一致；把「字符串型载荷」统一到 `-c` payload / `eval` argv[1] / `env -S` value 的同一机制。
- [ ] 2.7 全文 denylist **保留为显式的字面模式通道**（D9）：实测清空后攻击集 deny 从 54→20，34 条只靠它拦下。把它标注为「字面深度防御层」，并**移除**其中与 evaluator 重复实现的语义（消除双实现等价性负担的是这部分）；`_CODE_EXEC_INTERPRETERS`（当前全仓零引用的死代码）一并清理。具体地（D9 的第一批）：把 `workspace_policy.py:121-122` 的 `\b(mv|cp)\s+<源>` 两条**源位置正则**迁移到 evaluator（IR 的 `write_targets[]` 已表达「源/目标是谁」），迁移后 `cp .env.example /tmp/backup.txt`（源为模板、目标为普通路径）的**源位置误伤自然消失**。
- [ ] 2.9 **（[Q3] 新增，D12）提取「敏感 dot 名」共享谓词**——新建一份**代码谓词**（分段判定，SHALL NOT 用 glob：实测 `fnmatch` 不支持 extglob，`fnmatch('.env.local', ".env.!(example|…)")` 返回 False，写成 glob 会静默放开两边），并让三处定义全部消费它：`workspace_policy.DEFAULT_DENIED_PATTERNS`、`workspace_policy.py:121-122` 的两条正则（迁往 evaluator，见 2.7）、`command_guard._SENSITIVE_DOTDIRS`/`_SENSITIVE_DOTFILES`。位置与命名由实现决定，但 SHALL 满足 D10 的「同一语义只在一处定义」。
- [ ] 2.10 **测试先行（含对照组 + 变异验证）**：敏感 dot 名谓词的契约测试——判据「`.env` 之后的每一个 `.` 分段都是模板词」。**对照组必测**：`.env.local` deny ↔ `.env.example` allow；`.env.example.local` deny ↔ `.env.example` allow；复合后缀 `.env.local.example` / `.env.production.sample` / `.env.j2` / `.env.example.bak` deny。**不误伤**：`.envrc` / `.environment` / `app.env` / `config.env` / `my.env` / `.env2` / `.env-file` / `environment` allow。**变异验证**：把谓词的模板词表改坏一个词（如删掉 `example`），必须有测试变红——防止「三处又各写一遍」导致谓词形同虚设。
- [ ] 2.11 **测试先行（[Q3] 新增范围）**：`.env` **凭据变体**在**所有**写目标通道被判 deny——`cp x .env.local`、`tee .env.production`、`dd of=.env.development`、`echo X >> .env.test`、`mv .env.staging /tmp/x`。回归基线：**这些命令当前全部 allow**（`_dest_is_sensitive` 按 basename 精确相等、字面通道否定前瞻排除 `.env.` 后续字符），且实测 `cp src.txt .env.local` 经 `BashTool` 真的执行并写入。
- [ ] 2.12 **测试先行（[Q3] 新增）**：`.env` **模板读写豁免**——`cat .env.example`（读工具）、`cp x .env.example`（写）、`cp .env.example /tmp/backup.txt`（源为模板）SHALL 放行；并断言文件工具与护栏两侧**判定一致**（`workspace_policy.is_denied` 是读写共用谓词，见 D12）。
- [ ] 2.8 **测试先行**：`bash -c` / `env -S` / 命令替换的递归判定改走 IR，深度上界行为与现状一致。

## 3. 决策模型与审批接线（D3）

- [ ] 3.1 `CommandVerdict` 扩展为 `ALLOW / DENY / ASK`；`last_reason` 补 `ask` 类原因。
- [ ] 3.2 **（改造面大于首版估计）** 打通「工具执行中请求审批」通路：`BashTool` 增无条件审批回调（先例 `bash.py:57-58` 的 `run_in_background_cb`，但那条仅在 `background_manager is not None` 时可用）；新增由 `CommandVerdict` + `cmd` 构造审批请求的路径（`build_approval_request` 现强制要 `PermissionDecision`，`approval.py:123-149`）。
- [ ] 3.3 **3 处内部早返回改为 ASK 透传**（`command_guard.py:381/439/451`——它们今天在「非 DENY」时落到 `return ALLOW`）+ 2 处递归传播点。
- [ ] 3.4 新增执行中审批的 trace/quality 事件（`loop.py:917-952` 的 `approval_required`/`approval_granted` 来自执行前那层，第二次审批不会进 trace）。
- [ ] 3.5 **测试先行**：按运行时分别断言 `ask` 行为——交互 CLI 弹窗；非 TTY CLI → `UNAVAILABLE`（拒绝）；Web 弹卡片；benchmark（不传 handler）恒 `FailClosed` 拒绝、命令失败。
- [ ] 3.6 逐点复核既有 `is CommandVerdict.DENY` 调用点，确认「应当 ask 的地方」没有被 `is DENY` 漏掉；同步 `test_command_guard.py` 中 `assert verdict in (ALLOW, DENY)` 形态的断言。
- [ ] 3.7 **（[Q1] 拍板落点）ask 分层口径**：实现「归一化（含乙类展开）后命中敏感名/受保护路径 ⇒ deny，否则 ⇒ ask」，且**归一化必须先于 deny/ask 分流**（否则 `cp x ~/.{ssh}/f` 会落到 `ask` 而非 `deny`）。测试先行：`cp $SRC build/` ⇒ ask、`cp $SRC $DST` ⇒ ask、`cp x ~/.{ssh}/f` ⇒ **deny**、`echo "$PATH"`（非目标位）⇒ allow。
- [ ] 3.8 **（[Q1] 更正运行时矩阵）**：D3 的运行时表须写明 benchmark **默认 `--mode build` 下 Bash 在 loop 层即被拒、护栏跑不到**；`ask` = 拒绝只在 `--mode bypass` 成立。补一条测试锁定该事实（`decide_tool(Bash)` 在 build 模式下为 `REQUIRE_APPROVAL`）。

## 4. 未知与失败策略（D4）

- [ ] 4.1 **测试先行**：解析错误（`has_error` 或 `is_missing`）⇒ ask，**且禁用 argv**。
- [ ] 4.2 **测试先行（安全关键）**：命令替换 / 进程替换 / 反引号**无论位置**都递归判定；`echo $(rm -rf /tmp/x)`、`` echo `rm -rf /tmp/x` ``、`$(echo rm -rf /)` **必须仍被拒**（当前靠全文正则，D9 后须由 evaluator 独立兜住）。
- [ ] 4.3 **测试先行（安全关键）**：heredoc 绑定解释器 ⇒ 正文**全量按命令判定**（[Q2] 用户拍板 (a)）——`bash <<EOF` + `cp x .env` + `EOF`、`sh <<EOF…`、`bash -s <<EOF…`、`python3 - <<PY…` SHALL 拒绝（**当前靠分词器误报的巧合被拦，首版 design 会把它变成 allow**）。**对照（(a) 与更窄规则 (b) 的差异必须被测试锁住）**：正文为 `rm -rf $HOME` / `dd of=$DEST` / `cp -t $T` / `mv --target-directory=$D` / `rm -rf $BUILD` / `tee $OUT` SHALL 被拒或 ask（这些正是 (b) 会漏的 7 条）；正文为 `npm ci` / `git pull` / `rm -rf build`（工作区内相对路径）SHALL 放行。**正文判定须落到 evaluator（含 `_check_rm` 的 `$HOME`/`~`/`/` 特例），SHALL NOT 依赖字面通道兜底。**
- [ ] 4.4 **测试先行**：heredoc 绑定非解释器 ⇒ 正文是数据；`cat <<EOF` + 正文含危险字样 + `EOF` SHALL 放行。
- [ ] 4.5 **测试先行**：动态词在**写目标位置**（`cp $SRC $DST`、`cp x *.env`、`cp -t $D x`）⇒ 归一化后命中敏感名 ⇒ deny，否则 ask；在**非目标位置**（`echo "$PATH"`）⇒ allow。
- [ ] 4.6 **测试先行**：不支持的语法节点 ⇒ ask（对齐 zcode `isBashCommandPermissionSafe`）。
- [ ] 4.7 **测试先行**：嵌套超深 / 预算耗尽 ⇒ ask。
- [ ] 4.8 **测试先行**：后端不可用 ⇒ deny 且**不因护栏判定 allow 而放行**。

## 5. launcher 族与已知残余收口（D8）

- [ ] 5.1 剥离循环改为 **wrapper/launcher 交替到不动点**（`nohup setsid cp x .env`、`env -i nice cp x .env`、`xargs -0 busybox cp x .env` 当前全 allow）。**且 SHALL 同时作用于 `<shell> -c <string>` 的 payload 通道**——实测 `_shell_dash_c_payloads` 的 wrapper 剥离只认 `env`/`command`/`nohup`/shell 关键字，故 `doas sh -c 'cp x .env'` / `nice bash -c 'cp x .env'` / `nohup setsid sh -c 'cp x .env'` / `unshare -m bash -c 'cp x .env'` 今天全 allow。测试先行，四条各一例。
- [ ] 5.2 **launcher 兜底策略按 [Q4] 拍板的 (c') 实现**：未识别前导 token **仅当其后（滑窗内）跟着护栏真正会判的命令**（`rm`/`mv`/`cp`/`chmod`/`curl`/`wget`/`dd`/`tee`）时 ⇒ `ask`；**纯未识别程序保持 default-allow**。`doas` / `unshare -m` / `nsenter` / `script -q` / `ionice` / `watch` / `strace` / `setpriv` / `chrt` / `systemd-run` / `runuser` / `setarch` / `perf` / `ltrace` + 写命令 SHALL 被拒或要求审批。**注意**：首版的 9 条穷举表已证伪（任何单条缺失即证伪整个属性）；(b)「未知即 ask」被实测噪音否决（59 条真实命令上 63% 被拉去审批）。
- [ ] 5.6 **测试先行（[Q4] (c') 的对照组）**：`my-custom-tool --flag` / `terraform plan` / `./scripts/run.sh` / `bun run dev` SHALL **allow**（不误伤）；`nsenter -t 1 cp x .env` / `watch -n 1 cp x .env` / `setarch x86_64 cp x .env` / `flock /tmp/l cp x .env` SHALL `ask`。断言 (c') 在真实命令语料上噪音为 0。
- [ ] 5.3 **测试先行**：launcher + 裸点名（`nice cp x .env`）与 launcher + 非 `cp`/`mv` 写命令（`nice tee ~/.ssh/authorized_keys`）从 allow 变 deny/ask。
- [ ] 5.4 **测试先行**：混淆形态归一化——反斜杠转义、`?`、`*`、字符类、brace 展开 × 敏感名，用 `fnmatch` 反向匹配；**反例**：`.env.example` / `.gitignore` / `.github/` 不得误报。
- [ ] 5.5 回写 `docs/known-debt.md`「命令护栏的残余覆盖缺口」节：甲类/乙类 + grill 新发现的三类逐项标注收口结论，表格数据由实测脚本生成（受保护路径，需 `artifact-event`）。

## 6. 能力范围声明、度量与迁移（D5/D9/D10）

- [ ] 6.1 把能力范围矩阵落进 spec delta；每行「测试证据」列**只写当前真实存在的测试名**（grill 指出首版 12/16 行引用了不存在的测试名，其中 6 行未标「（新增）」，等于把待办伪装成证据）。新增一条校验：矩阵每行的测试名可被 `pytest --collect-only` 解析。
- [ ] 6.2 **测试先行**：为矩阵中每条尚无测试的形态补 fixture（launcher 兜底、heredoc→解释器、进程替换、动态写目标、`dd`/`tee` 目标、重定向敏感点目录、CVE-inspired）。
- [ ] 6.3 攻击集 `benchmarks/attacks/attacks.json` **只增不减**：新增 heredoc→解释器族、launcher 兜底族、混淆形态、重定向敏感点目录、**`.env` 凭据变体（`.env.local` 等）**、`dd`/`tee` 目标、CVE-inspired；断言拦截数**不下降**（[Q5] 谓词 = `verdict is not ALLOW`）。
- [ ] 6.4 **测试先行**：4 个 Claude Code CVE 各补用例——CVE-2025-54795（`echo` 解析绕过）断言被拦；CVE-2025-54794 / 55284 / 59536 断言**被显式标注为「本层不声称能防」**。
- [ ] 6.5 **（[Q5] 拍板落点）ASK 计数口径与用例集拆分**：① 攻击集（`attacks.json`）**只允 `deny`**，SHALL NOT 混入 `ask`；② **另建「应 ask」用例集**（如 `test_launcher_ask_suite.py`），断言 `is ASK`，收录 launcher 限定 ask 等形态；③ 无回归计数谓词定义为 **`verdict is not ALLOW`**；④ 同步 `test_command_guard.py` 中 `assert verdict in (ALLOW, DENY)` 形态的断言。**注**：实测既有 50 条 guard-deny 用例过新管线 50/50 保持 DENY，故 `tests/benchmark/test_attack_suite.py:46` 的 `is DENY` 对既有 54 条**无需修改**。
- [ ] 6.6 **度量改为三条可机械验证的指标**（首版的「常量数下降」是不诚实弱代理，实测常量数 15→13–18 持平）：① 「从原文重推 argv 的入口数 == 1」（断言只有 `bash_ir.py` 加载 tree-sitter、evaluator 不调 `re.split`/`tokenize_command`）；② 「手工维护的等价性对数 == 0」——**「敏感 dot 名」是这条指标的第一个具体实例（D12）**，SHALL 断言该语义只有一份定义、三处消费方均引用它；③ 代码量三栏对照（新增 / 删除 / net），**如实报告预估 net 577 → 600–800 行**。
- [ ] 6.8 **（[Q3] 新增）文档影响**：`docs/known-debt.md`「命令护栏的残余覆盖缺口」一节登记 `.env` 凭据变体（甲类：非本 change 引入、两版同为漏洞）与模板误伤（乙类收口）的实测结论；并如实记录「三处定义漂移」的根因与收敛方案（受保护路径，需 `artifact-event`）。
- [ ] 6.7 **新旧对拍与回退开关（迁移对冲）**：对 `attacks.json` 全量 + 现有 81 个 guard 单测的命令串做旧 vs 新 verdict 对拍，断言 **`旧 DENY ⊆ 新 DENY ∪ 新 ASK`**；提供环境变量回退开关，对拍全绿前保留。对拍报告作为验收证据。

## 7. 文档与收尾

- [ ] 7.1 同步当前规格：把 change spec delta 合入 `openspec/specs/workspace-safety/spec.md`（`current spec sync`）。
- [ ] 7.2 文档影响检查：`docs/known-debt.md`、`docs/architecture.md`、`README.md` / `README_EN.md`（命令护栏相关段落）、`docs/openspec-change-backlog.md`；只改本变更造成的事实变化。
- [ ] 7.3 跑 `/review-loop` 独立审阅闭环，产出 `reviews/building-review.md` + review manifest（PASS 或 3 轮封顶）。
- [ ] 7.4 跑全量 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`。
- [ ] 7.5 跑 benchmark smoke 验证（`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 仍绿）。
- [ ] 7.6 归档 change 到 `openspec/changes/archive/YYYY-MM-DD-bash-command-guard-redesign/`，从 `docs/openspec-change-backlog.md` 移除。
- [ ] 7.7 (post-merge) PR 合入后给 issue #254 添加完成说明 comment 并关闭。
