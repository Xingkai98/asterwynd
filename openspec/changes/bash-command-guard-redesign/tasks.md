# Tasks: Bash 命令护栏的单一解析管线重构

> 测试先行（TDD）：每个实现任务前的测试任务先落地为失败用例，再写实现。
> 完成度门禁：closeout 类任务（PR 合入后才执行）标注 `(post-merge)`。

## 0. 设计追问（实现前门禁）

- [ ] 0.1 跑 `batch-grill`（独立零记忆 subagent 审视 design.md），产出 `reviews/grill-design.md`（≥3 Confirmed Decisions 且每条带 `来源:` + Open Questions）。
- [ ] 0.2 停轮把 `## Open Questions` 逐条抛给用户（每条配具体场景例子：真实参数/输入输出/前后对比），答复记录进 `## User Confirmation`。**收到答复前不得写实现代码。**

## 1. 解析层：tree-sitter-bash 接入与 IR 构造（D1/D2）

- [ ] 1.1 `pyproject.toml` 新增 `tree-sitter-bash` 依赖；确认 `uv sync` 在本机与 CI 平台安装成功（wheel 226 KiB，cp310-abi3 manylinux）；记录降级路径（wheel 不可用时 `ask` 还是硬失败）。
- [ ] 1.2 **测试先行**：IR 契约测试——同一语义的不同写法产出相同 IR（`rm -rf /` / `rm -fr /` / `rm -r -f /` / `rm -rf -- /`）；不同语义产出不同 IR。
- [ ] 1.3 新增 `agent/tools/bash_ir.py`（或 `command_guard.py` 内的独立段）：用既有 `tree_sitter_symbols.py` 同款写法加载 bash 语法，用 `Query("(command) @c")` + `QueryCursor` 构造 IR。**禁止递归 Python 遍历**。
- [ ] 1.4 IR 字段：`segments[]`（argv）、`redirects[]`（fd/操作符/目标）、`env_assignments[]`、`dynamic_words`（bool + 位置）、`parse_errors`（bool + 位置）、`unsupported_nodes[]`、`source_span`。
- [ ] 1.5 **测试先行**：heredoc 正文不产生 segment（`cat <<'EOF'\ncp x .env\nEOF` 的 IR 只有一个 `cat`）；`$(...)`/`<(...)`/`` ` `` 归类为「嵌套内容 + 动态标记」。
- [ ] 1.6 **测试先行**：错误信号覆盖——`has_error` 与零宽 `is_missing` 两条都被捕获（含 `rm -rf !(keep)` 这类只产生 `MISSING` 的输入）。
- [ ] 1.7 **测试先行**：预算与深度——节点数/输入长度/嵌套深度上界命中时返回确定处置而非崩溃；构造 ~1,300 字符的 `$(( … ))` 断言**不抛 `RecursionError`**。
- [ ] 1.8 **测试先行**：解析器**从不抛异常**契约（含空串、纯空白、未闭合引号、NUL 字节、超深嵌套）。

## 2. evaluator 层：三套机制合并为消费 IR 的 evaluator（D2/D5/D7）

- [ ] 2.1 重定向 evaluator 改为读 IR 的 `redirects[]`（取代独立 token 扫描）；保留 `/dev/null` 族豁免与分量边界判定。
- [ ] 2.2 `_check_rm` / `_check_mv_cp` / `_check_chmod` / `_check_curl_wget` 改为读 IR 的 `argv`；`_normalize_path` / `_within` / `_is_device_exempt` 语义不变（D7）。
- [ ] 2.3 **测试先行**：`cp x ~/.{ssh}/f`（brace 展开）被判 deny/ask —— 目标不得被销毁；对照 `cp x .env.example` 仍放行。
- [ ] 2.4 **测试先行**：`cat <<'EOF'\ncp x .env\nEOF` 从 deny 变 allow（修掉当前误报），并确认 `grep -rn "cp x .env" docs/` 仍放行。
- [ ] 2.5 全文 denylist 降级为「消费 IR argv/redirect 目标做字面模式匹配」的一层 evaluator，不再是独立入口；`DEFAULT_DENYLIST` 与 `_EXTRA_DENYLIST` 按 IR 可表达的语义重新归类。
- [ ] 2.6 **测试先行**：`bash -c` / `env -S` / 命令替换的递归判定改走 IR，深度上界行为与现状一致。

## 3. 决策模型与审批接线（D3）

- [ ] 3.1 `CommandVerdict` 扩展为 `ALLOW / DENY / ASK`；`last_reason` 补 `ask` 类原因。
- [ ] 3.2 **测试先行**：`agent/tools/builtin/bash.py` 的 `ask` 分支路由到既有 `ApprovalHandler.request_approval`；无 UI 时 `FailClosedApprovalHandler` 拒绝；`sandbox` 事件的 `denied` 载荷与现有 schema 兼容。
- [ ] 3.3 逐点复核既有 `is CommandVerdict.DENY` 调用点，确认「应当 ask 的地方」没有被 `is DENY` 漏掉。

## 4. 未知与失败策略（D4）

- [ ] 4.1 **测试先行**：解析错误 ⇒ ask。
- [ ] 4.2 **测试先行**：动态词在**目标位置**（`cp $SRC $DST`、`cp x *.env`、`cp x ~/.{ssh}/f`）⇒ ask；在**非目标位置**（`echo "$PATH"`）⇒ allow。
- [ ] 4.3 **测试先行**：不支持的语法节点 ⇒ ask（对齐 zcode 的 `isBashCommandPermissionSafe`）。
- [ ] 4.4 **测试先行**：嵌套超深 / 预算耗尽 ⇒ ask（不得无界递归、不得崩溃）。
- [ ] 4.5 **测试先行**：后端不可用 ⇒ deny 且**不因护栏判定 allow 而放行**（反例测试：护栏 allow + 后端不可用，断言整体不放行）。

## 5. launcher 族与已知残余收口（D8）

- [ ] 5.1 **测试先行**：per-launcher 参数表——`flock <file> cmd`、`chroot <dir> cmd`、`nice -n N cmd`、`setsid`、`xargs`、`busybox`、`stdbuf -o0 cmd`、`taskset -c 0 cmd` 的位置参数与选项混排后，真实命令被判定。
- [ ] 5.2 **测试先行**：launcher + 裸点名（`nice cp x .env`）与 launcher + 非 `cp`/`mv` 写命令（`nice tee ~/.ssh/authorized_keys`）从 allow 变 deny/ask；补 `tee` 目标的写判定。
- [ ] 5.3 **测试先行**：混淆形态归一化——反斜杠转义、`?`、`*`、字符类、brace 展开 5 种 × 敏感名，用 `fnmatch` 反向匹配；**反例**：`.env.example` / `.gitignore` / `.github/` 不得误报。
- [ ] 5.4 回写 `docs/known-debt.md`「命令护栏的残余覆盖缺口」节：甲类/乙类逐项标注收口结论，表格数据由实测脚本生成（受保护路径，需 `artifact-event` 结构化解释事件）。

## 6. 能力范围声明与测试矩阵（D5/D9）

- [ ] 6.1 把能力范围矩阵（输入形态 × Guard/Backend/Unsupported）落进 spec delta；每行「测试证据」列指向真实测试名。
- [ ] 6.2 **测试先行**：为矩阵中每条尚无测试的形态补 fixture（分组、进程替换、heredoc、动态词、launcher、CVE-inspired）。
- [ ] 6.3 攻击集 `benchmarks/attacks/attacks.json` **只增不减**：新增 launcher 族、混淆形态、brace 展开、CVE-inspired 用例；断言拦截数**不下降**。
- [ ] 6.4 **测试先行**：4 个 Claude Code CVE 各补用例——CVE-2025-54795（`echo` 解析绕过）断言被拦；CVE-2025-54794 / 55284 / 59536 断言**被显式标注为「本层不声称能防」**（防止能力范围声明被写乐观）。
- [ ] 6.5 度量「单一解析管线」目标：统计重构后 `command_guard.py` 的模块级常量数与行数，对比重构前（15 个 `_CONST`、77 条 denylist、577 行），把结果写回 design.md。

## 7. 文档与收尾

- [ ] 7.1 同步当前规格：把 change spec delta 合入 `openspec/specs/workspace-safety/spec.md`（`current spec sync`）。
- [ ] 7.2 文档影响检查：`docs/known-debt.md`、`docs/architecture.md`、`README.md` / `README_EN.md`（命令护栏相关段落）、`docs/openspec-change-backlog.md`；只改本变更造成的事实变化。
- [ ] 7.3 跑 `/review-loop` 独立审阅闭环，产出 `reviews/building-review.md` + review manifest（PASS 或 3 轮封顶）。
- [ ] 7.4 跑全量 `uv run pytest -q`、`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`、`PYTHONPATH=. python3 scripts/check_openspec_artifacts.py`。
- [ ] 7.5 跑 benchmark smoke 验证（守卫变更后 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke` 仍绿）。
- [ ] 7.6 归档 change 到 `openspec/changes/archive/YYYY-MM-DD-bash-command-guard-redesign/`，从 `docs/openspec-change-backlog.md` 移除。
- [ ] 7.7 (post-merge) PR 合入后给 issue #254 添加完成说明 comment 并关闭。
