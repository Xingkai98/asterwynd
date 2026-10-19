# Tasks: 命令护栏工作区包含判定两侧统一 realpath 归一

> **结算次序（收尾）**：本文件在最后一个内容提交上落定 → backlog 移除 → 归档 move（独立提交）
> → 本地复验 → **结算 `tasks.md`（未勾且未标 `(post-merge)` 必须为 0）** → **用归档目录名**
> 重建 witnessloop 三份 manifest → `gate / check` 机械复核 → 发起 PR。PR 创建与合入不写回
> `tasks.md`；closeout 类任务（合入后动作）标 `(post-merge)`。

## 0. 设计追问与对抗收敛（前置门，不完成不开工）

- [x] 0.1 用 `grilling`（独立零记忆子代理）执行设计追问，产出 `reviews/grill-design.md`（`## Confirmed Decisions` ≥ 3 条，每条含同行裸 `来源:`；`## Open Questions` 与 `## User Confirmation` 无条件存在）。
- [x] 0.2 逐项确认：两侧 realpath 归一、相对路径保持词法、`_allow_covers` 同类修复、fail-closed、工作区内链接逃逸收紧、无平台分支、测试矩阵、Non-Goals。
- [x] 0.3 设计阶段对抗闭环 → `reviews/grill-adversarial.md`，按批次模型收敛到 PASS。
- [x] 0.4 停轮检查：无 Open Question 或已确认；设计环出口 PASS。
- [x] 0.5 回填 `design.md` 的 `## Pre-Implementation Review`。

## 1. 测试（TDD）

- [x] 1.1 在 `tests/agent/tools/test_command_guard.py` 新增 `TestSymlinkedWorkspaceContainment`：`tmp_path` + `os.symlink`；`os.name != "posix"` 或 `os.symlink` 抛 `OSError` 时 `pytest.skip`（POSIX 语义测试不伪装成 Windows 失败）。
- [x] 1.2 四行 ALLOW 矩阵：workspace ∈ {link, real} × 目标 ∈ {link/build, real/build}。
- [x] 1.3 负例：`<ws>-evil` 前缀碰撞、`<ws>/../etc`、`rm -rf <ws>`（link/real 两种表示）。
- [x] 1.4 fail-open 闭合：工作区内 `escape → outside` 的 `rm -rf <ws>/escape`（含尾斜杠）DENY；`rm -rf <ws>/escape/../victim` DENY（区分 resolve-first 与 normpath-first 的关键用例）；工作区内 `loop → loop` 的 `rm -rf <ws>/loop/x` DENY（strict-first fail-closed，3.11–3.14 语义一致）。
- [x] 1.5 写白名单同源：`allowed_write_paths=(".env",)` 下用 `tee <ws>/.env`、`echo K >> <ws>/.env`、`dd of=<ws>/.env` 验证 link/real 双向表示 ALLOW（`cp`/`mv` 会被 denylist 先拦，不可用）；前缀碰撞与逃逸目标 DENY；工作区内 `.env → config/dev.env` 时 allowlist `.env` 不覆盖、`config/dev.env` 覆盖（白名单按真实目标相对路径匹配）。
- [x] 1.6 记录修复前红/绿：正向与白名单用例红、既有负例绿；运行 `uv run pytest -q tests/agent/tools/test_command_guard.py -k symlink`。
- [x] 1.7 变异验证：把 helper 退回纯词法 → 新增正向用例变红；恢复后全绿。

## 2. 实现（command guard）

- [x] 2.1 新增统一归一化 helper：POSIX 绝对路径**直接** strict-first `Path.resolve()`（不做 normpath 前置；仅 `FileNotFoundError` 回退非严格解析）；相对路径 `os.path.normpath`；循环/权限等解析失败返回 `None`。
- [x] 2.2 `_check_rm()` 拆词法/canonical 两个变量：`_DENY_PATHS` 与特殊 token 用词法，工作区包含与根删除用 canonical；`None` 在字符串操作前显式判 DENY。
- [x] 2.3 `_allow_covers()` 改用同一 helper 计算 workspace 相对路径（`None` ⇒ 不覆盖）。
- [x] 2.4 无平台分支；`_DENY_PATHS` 判定、相对路径语义与 Windows 盘符路径既有口径保持不变；同步 `_normalize_path()` 注释。
- [x] 2.5 定向测试全绿（含既有 `TestPathSegmentBoundary`、三态、攻击集、ask 集）。

## 3. 规格与文档

- [x] 3.1 `specs/workspace-safety/spec.md` delta（MODIFIED 命令护栏 Requirement 的规范化条款 + 4 个 Scenario：工作区放行、链接逃逸、`escape/../victim`、循环 fail-closed）。
- [x] 3.2 把 delta 施加进 `openspec/specs/workspace-safety/spec.md`，记录 Requirement 计数，写 `current_spec_synced` 事件；OpenSpec strict validate 通过。
- [x] 3.3 `docs/openspec-change-backlog.md` 登记本 change（issue #310）并写 `backlog_updated` 事件。
- [x] 3.4 文档影响检查：change 自身文档、backlog、`docs/` / `README*` / `AGENTS.md` / `CONTEXT.md` 相关段落 grep，只改事实变化。
- [x] 3.5 新增 `docs/adr/ADR-0008-guard-workspace-realpath-containment.md`：single realpath vs 双表示 vs normpath-first、strict-first 与 `None` 处置，≥2 备选及拒绝理由。

## 4. 验证（实测）

- [x] 4.1 `uv run pytest -q tests/agent/tools/test_command_guard.py`（本分支基线实测 **272 passed**）。
- [x] 4.2 全量 `uv run pytest -q`：**2 failed / 4383 passed / 9 skipped**（364.30s）。2 条失败均为既有 `TestFindScopeRoot` 本机 `/tmp` 环境失败，与基线同因；基线 4 failed 中的 `test_sandbox_backends[docker]`（无 Docker）与 `test_parallel_execution`（计时 flake）本轮通过。无新增失败类型。
- [x] 4.3 本机 / ubuntu 语义下的显式符号链接命令级实测矩阵（ALLOW ×4、DENY ×6）已由审阅者独立复核并记录进 `reviews/building-review.md` 的「符号链接命令级实测矩阵」节。
- [x] 4.4 `npx --yes @fission-ai/openspec@1.4.1 validate --all --strict` 通过。
- [x] 4.5 `uv run python scripts/check_openspec_artifacts.py --base-ref origin/master --require-base` EXIT=0。
- [x] 4.6 **benchmark smoke**：本 change 触及 `agent/tools/`（命中 checker 的 benchmark smoke 触发面），跑 `uv run asterwynd benchmark benchmarks/tasks --agent fake --source-repo . --runs-dir /tmp/smoke-310` 确认工具策略接线未破。

## 5. 实现后独立审阅闭环

- [x] 5.1 独立零记忆审阅，产出 `reviews/building-review.md`（含 `## 闭环出口`），收敛到 PASS（第 1 轮 medium+ 为空，low/nit 5 条已复核处置）。
- [x] 5.2 全部 medium+ 修复并补回归测试；low/nit 登记并写理由（L-1～L-5 已修并复核 PASS）。

## 6. 收尾（合入后）

> 归档 move、本地复验、`tasks.md` 结算与三份 manifest 的次序见文件头；PR 创建与合入在
> manifest 之后执行，不写回 `tasks.md`。

- [ ] (post-merge) 6.1 用 `--merge` 合入 PR；合入后确认 active 目录不存在、backlog 干净、本地 `master` 已快进。
- [ ] (post-merge) 6.2 给 issue #310 添加完成说明 comment（PR 号与验证结果）并关闭 issue。
