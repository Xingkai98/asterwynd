# Tasks — fix-issue-247-guard-path-boundary

## 0. 前置（grill + 停轮确认）

- [x] 0.1 运行 `batch-grill-me`（或等价设计追问）审视 `design.md`，产出 `reviews/grill-design.md`（含 ≥3 条 `## Confirmed Decisions`）
- [x] 0.2 **停轮**：把 `## Open Questions` 逐项抛给用户，每条配具体例子（真实场景、参数/输入输出、前后对比），等待明确答复
- [x] 0.3 把用户答复回填 `reviews/grill-design.md` 的 `## User Confirmation` 节（每条 `- **Q<n>**: 用户答复：<实质内容>；确认时间: <date>`）
- [x] 0.4 按答复回写 `design.md` 的 Decisions 与 `proposal.md` 的待确认影响面，清理 `unknown`/`TBD`/`待确认`

## 1. 规格

- [x] 1.1 维护 `specs/workspace-safety/spec.md` delta（MODIFIED「命令护栏」Requirement：路径段边界 + 设备文件豁免 + 4 条新 Scenario）
- [x] 1.2 维护 `## Impact Analysis`，开发前把待确认项清理为明确结论
- [x] 1.3 维护 `## Reference Implementation Research`（已初稿：`research_tier: exempt`）
- [x] 1.4 在 `design.md` 的 `## Pre-Implementation Review` 记录已解决问题、备选方案、否决方案、最终确认与剩余风险
- [x] 1.5 落地 spec delta 到 `openspec/specs/workspace-safety/spec.md`（当前规格同步；收尾阶段执行）

## 2. 测试（TDD：先写回归测试，必须先红）

- [x] 2.1 **误报侧放行用例**（`tests/agent/tools/test_command_guard.py`）：fd 前缀重定向族（`ls -la 2>/dev/null`、`echo hi > /dev/null`、`cmd > /dev/null 2>&1`、`python3 x.py > /dev/null 2>&1`、`git log 2>/dev/null | head`）断言 `ALLOW`
- [x] 2.2 **误报侧放行用例**：假朋友前缀族（`echo x > /various.txt`、`echo x > /rooted.log`、`echo x > /bootstrap.log`、`echo x > /etcetera.conf`、`echo x > /sysadmin.log`）断言 `ALLOW`
- [x] 2.3 **误报侧放行用例**：普通点目录族（`cp r.md docs/.draft/x.md`、`mv x src/.cache/`、`cp x /tmp/.hidden/`）断言 `ALLOW`
- [x] 2.3b **点目录误报检查（grill R1 新增，防重犯前缀错误）**：`cp x .gitignore`、`cp x .env.example`、`cp x .dockerignore`、`cp x .github/w.yml`、`cp x src/.gitignore` 断言 `ALLOW`
- [x] 2.3c **嵌套敏感点目录拦截（grill R1 新增，原模式能拦、正则形态会漏）**：`cp x src/.git/hooks/pre-commit`、`cp x sub/.env/secrets`、`cp x proj/.npmrc`、`cp x a/.git/` 断言 `DENY`
- [x] 2.4 **漏网侧拦截用例**：`workspace=/tmp/ws` 时 `rm -rf /tmp/ws-evil`、`rm -rf /tmp/ws-evil/x`、`rm -rf /tmp/wsX` 断言 `DENY` 且 `last_reason == "rm_target_escape"`
- [x] 2.5 **真危险对照（不得放松）**：`echo x > /etc/passwd`、`echo x > /var/log/syslog`、`rm -rf /`、`rm -rf /var`、`cp a /etc/x`、`chmod 777 /etc/x`、`cp x .git/config`、`mv y .ssh/id_rsa`、`cp x .env`、`dd if=/dev/zero of=/dev/sda`、`yes > /dev/null` 断言 `DENY`
- [x] 2.6 **修正被误报固化的既有断言（grill R2 修正路径）**：`:122`/`:176` 改用 `/root/foo`（实测 reason=`mv_cp_dest`；`/var/log/foo` 会被 denylist 抢先、**不可用**）；`:164` 改用 `/var/log/foo`（实测 reason=`protected_redirect`）
- [x] 2.7 **运行新测试确认必红**（修复前），记录输出
- [x] 2.8 确认新用例不依赖机器负载/时序（纯函数，无 sleep）
- [x] 2.9 **把良性命令电池全集固化为测试数据**（grill R4：proposal 的「26 条 / 误报 17→0」当前不可复算，须落库为可执行 fixture，使 4.4 有参照物）

## 3. 实现

- [x] 3.1 引入路径段边界判定辅助函数 `_within(path, prefix)`（`agent/tools/command_guard.py`）
- [x] 3.2 引入设备文件豁免常量 `_DEVICE_EXEMPT`（`/dev/null`、`/dev/stdout`、`/dev/stderr`；Q3 拍板**不含** `/dev/fd/`），豁免只用于重定向与 mv/cp（Q2 拍板）
- [x] 3.3 `_has_protected_redirect`（`:178-186`）改用段边界 + 设备豁免
- [x] 3.4 `_check_rm`（`:216-233`）改用段边界；工作区判断改为「在内且不等于根」（按 D3/grill 答复）
- [x] 3.5 `_check_mv_cp`（`:236-245`）改用段边界 + 设备豁免
- [x] 3.6 `_check_chmod`（`:248-259`）改用段边界
- [x] 3.7 `_check_curl_wget`（`:262-270`）改用段边界
- [x] 3.8 从 `_EXTRA_DENYLIST` **移除** `mv/cp` 的点目录正则分支，改在 `_check_mv_cp` 内做**段级**判定 `_dest_is_sensitive(dest)`（grill R1 修正：正则形态两向都不成立，清单按 Q4 答复定）
- [x] 3.9 更新 `command_guard.py` 模块 docstring，如实反映新的判定口径（段边界 + 设备豁免 + 段级敏感点目录）
- [x] 3.10 如实现中发现新影响面，先回写 `## Impact Analysis` 和本任务清单，再继续
- [x] 3.11 **按 Q1 答复**实现 `rm -rf <workspace_root>` 的行为（D3：倾向拒绝）
- [x] 3.12 **按 Q6 答复**决定 `..` 穿越是否在本 change 内补规则，或记入 `docs/known-debt.md`

## 4. 验证

- [x] 4.1 运行 `uv run pytest tests/agent/tools/test_command_guard.py -q`（新用例转绿）
- [x] 4.2 运行 `uv run pytest tests/benchmark/test_attack_suite.py -q`，确认全绿且拦截数 ≥ 50
- [x] 4.3 **变异验证**：还原裸 `startswith` → 2.1–2.5 必红；应用修复 → 必绿。记录两向实测结果
- [x] 4.4 重跑只读仿真复算（良性命令电池 + 真危险对照），与 design 预测数字对齐（误报 17→0、漏网 0、攻击集 50/54）
- [x] 4.5 运行全量测试：`uv run pytest -q`
- [x] 4.6 运行 OpenSpec strict validate：`npx --yes @fission-ai/openspec@1.4.1 validate --all --strict`
- [x] 4.7 运行项目 artifact checker：`uv run python scripts/check_openspec_artifacts.py`
- [x] 4.8 确认 Bash 工具层未受影响：运行 `tests/agent/tools/test_bash*.py` 或等价（护栏是 Bash 入口）
- [x] 4.9 跑 benchmark smoke 确认改护栏没有破坏 agent 主循环的命令执行路径：`uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-247`（fake agent 不依赖真实 LLM；本 change 触及 coder agent core 的 Bash 入口，按 checker 要求须有此冒烟）

## 5. 文档影响

- [x] 5.1 关键词扫描 `docs/`、`README.md`、`AGENTS.md`、`CONTEXT.md` 中与命令护栏 / 沙箱 / 受保护路径相关的段落，**并显式纳入 `docs/interview-script/**` 与 `docs/interview-bullets/**`**（grill R7：`Q10-sandbox.md`、`W06-security.md`、`FINAL-master-script.md` 等描述了护栏既有判定口径，AGENTS.md 有对应维护约束）
- [x] 5.2 `docs/known-issues.md` / `docs/known-debt.md`：核实是否已有 #247 相关记录，无则新增；**并记录 grill R6 的残余漏网面**（source 侧 `.ssh`、`..` 穿越若 Q6 决定不纳入）——受保护路径，需 `workflow-events.jsonl` 的 `protected_artifact_explained` 事件
- [x] 5.3 本 change 在同一 PR 内完成实现与归档，从未登记进 backlog（已核实 grep 0 命中）——故无需 `backlog_updated` 事件；归档时从 backlog 移除亦不适用
- [x] 5.4 已核实：`development-guide.md:216` 仅列 `tools.command_denylist` 配置项名、`testing-guide.md` 无护栏判定描述 —— 无影响，不强改
- [x] 5.5 同步 spec delta 到 `openspec/specs/workspace-safety/spec.md`（grill R5：受保护路径，需 `current_spec_synced` 事件——原 tasks 1.5 只说同步、未列事件产出）

## 6. 审阅闭环

- [x] 6.1 Round 1 独立 subagent 审阅（`/review-loop fix-issue-247-guard-path-boundary`）→ verdict
- [x] 6.2 按 verdict 修复 + 补回归测试（若有 CHANGES_REQUESTED）
- [x] 6.3 复审至 PASS（或 3 轮封顶）
- [x] 6.4 生成 review manifest（绑定 reviewer run / base·head sha / tasks·spec·diff·report hash），在 `tasks.md` 最终化（含归档 move）之后生成

## 7. PR 收尾

- [ ] 7.1 PR 发起前归档到 `openspec/changes/archive/YYYY-MM-DD-fix-issue-247-guard-path-boundary/`（日期前缀硬性要求；**受保护路径，需 `change_archived` 事件**——grill R5）
- [ ] 7.2 从 `docs/openspec-change-backlog.md` 移除本 change
- [x] 7.3 确认 Impact Analysis 不再残留 `unknown`/`TBD`/`待确认`
- [x] 7.4 确认 RIR 已记录最终状态、发现与设计影响
- [ ] 7.5 再次运行 OpenSpec strict validate + artifact checker
- [ ] 7.6 (post-merge) PR 合入后给 issue #247 添加完成说明 comment 并关闭 issue
