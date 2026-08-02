# Building Review — sandbox-hardening（第二批，Round 2）

- 审阅范围：`git diff origin/master...HEAD`（HEAD=`b8927b6`，含 3f00f94 第二批实现 + b8927b6 Round 1 修复）
- 审阅方式：独立零记忆 subagent（不继承开发上下文），逐条验证 Round 1 的 5 项修复 + 全量跑批
- 审阅时间：2026-08-02
- Round 1 verdict：CHANGES_REQUESTED（1 中等 `sandbox.timeout_seconds` 不生效 + 4 minor）

## Verdict: CHANGES_REQUESTED

Round 1 的 5 项修复在**代码层面全部正确**：timeout_seconds 主路径生效、cgroup sweep_stale、`_setup_cgroup` catch Exception、Docker 超时容器清理、attach 三态语义。OpenSpec strict validate 通过（32/32）、全量 pytest 通过（1516 passed, 7 skipped, 1 deselected）。

但本轮**两次实际观测到**批内测试 `test_limits_apply_cgroup_when_supported` 偶发失败（`fake.attached is True` 断言失败）——这是 Round 1 fix 9.5（attach 三态）与既有快命令测试的时序竞态，属本 change 自带测试的 flaky，威胁 CI 稳定性（中等）。且 9.5 的修复缺少**确定性**回归测试（"进程先于 attach 退出 → 不 degraded"路径无测试钉住）。修复这两个测试问题后即可 PASS。

## Round 1 五项修复逐条验证

| # | Round 1 发现 | 修复位置 | 代码验证 | 回归测试 | 结论 |
|---|---|---|---|---|---|
| 9.1 | `sandbox.timeout_seconds` 主路径不生效（中等） | `agent/tools/builtin/bash.py:84-88` `timeout=timeout`（None→后端默认），删除 `timeout or 30.0` | ✅ `build_sandbox_from_config`（factory.py:41-61）把 `config.sandbox.timeout_seconds` 传入后端构造（factory.py:53）→ `ProcessBackend(timeout=...)` 默认值生效（process_backend.py:160 `timeout = timeout or self.timeout`） | ✅ `test_backend_default_timeout_used_when_none_passed`（test_bash_tool_events.py:104-118）：ProcessBackend(timeout=0.2) + 不传 timeout → sleep 60 快速 timed_out | **充分** |
| 9.2 | cgroup 遗留目录清扫（minor） | `agent/tools/sandbox/cgroup.py:117-136` `sweep_stale`（dead pid 清理、live pid 不动），`create()` 触发（cgroup.py:141） | ✅ pid 解析 `split("-")[1]` + `_pid_alive`（os.kill(pid,0)）；live pid 跳过；普通 fs 子文件先 unlink 再 rmdir；真实 cgroup fs 上 live cgroup 的 rmdir 会 EBUSY 被吞，安全 | ✅ `TestSweepStale` 4 用例（test_cgroup.py:96-125）：removes dead / keeps live / create sweeps first / malformed 容错 | **充分** |
| 9.3 | `_setup_cgroup` 仅 catch OSError（minor） | `process_backend.py:124` `except Exception` | ✅ 非 OSError（如控制器 RuntimeError）不再丢 degraded 标志 | ✅ `test_non_oserror_setup_failure_still_degrades`（test_process_backend_cgroup.py:153-166）：RuntimeError → degraded=True + exit_code=0 | **充分** |
| 9.4 | Docker 超时容器残留（minor） | `docker_backend.py:132-202` `--cidfile` + 超时后 `_remove_orphaned_container`（`docker rm -f`） | ✅ mkstemp 预留唯一路径再 unlink（docker 拒绝已存在 cidfile）；超时 kill CLI → wait → 读 cidfile → `docker rm -f`；finally unlink cidfile；`_remove_orphaned_container` best-effort 吞异常 | ⚠️ 契约测试 `test_contract`（test_sandbox_backends.py:60-61）真实 Docker 跑 `sleep 5` timeout=1.0 触发该路径，但**不断言无孤儿容器残留**（仅断言 timed_out） | **充分（断言偏弱）** |
| 9.5 | attach 语义：快命令不误标 degraded | `process_backend.py:140-153` `_attach` 三态（True/False/None=已退出跳过）+ `effective_degraded = degraded or (attached is False)` | ✅ `echo` 类快命令进程先退出 → returncode 非 None → 返回 None → 不 degraded（对照 3f00f94 旧实现返回 False → 误标 degraded） | ⚠️ **无确定性回归测试**钉住 skip 路径；且既有快命令测试 flaky（见 Issue 1） | **代码正确，测试有问题** |

## Issues

### Issue 1（中等，需修复）— 批内测试 `test_limits_apply_cgroup_when_supported` flaky

`tests/agent/tools/test_process_backend_cgroup.py:46-57` 用 `echo hi`（近瞬时退出）断言 `fake.attached is True`。9.5 修复后 `_attach` 在 `proc.returncode is not None`（进程已退出且被 asyncio reap）时返回 None 跳过 attach——`echo hi` 在慢调度/并发负载下先于 attach 退出，`fake.attached` 保持 False → 断言失败。

**实际观测**：Round 2 审阅中该测试两次失败（一次在 5 文件组合跑，一次在 `test_process_backend_cgroup.py + test_sandbox.py` 组合跑），单跑均通过——典型时序竞态 flaky。CI 在任意负载下都可能红。

修复方向（二选一，均一分钟内完成）：
1. 测试改用存活足够久的命令（如 `sleep 0.2; echo hi`，与 `test_attach_failure_degrades` 一致），确定性触发 attach；
2. 或对快命令放宽断言（`echo hi` 场景断言 `degraded is False` 即可，不要求 `attached is True`——进程已退出时跳过 attach 正是修复语义）。

### Issue 2（minor）— 9.5 缺确定性回归测试

tasks.md 9.5 声称修复"进程先于 attach 退出（快命令）不视为 degraded"，但无测试钉住该行为：`test_limits_apply_cgroup_when_supported` 的 skip 依赖时序（即 Issue 1），没有直接断言"returncode 非 None → `_attach` 返回 None → 不 degraded"。建议补一个确定性单测（直接构造 `proc.returncode` 场景，或对 `_attach` 做纯函数级断言）。

### Issue 3（minor）— Docker cidfile 清理缺孤儿断言

tasks.md 9.4 声称"Docker 契约测试验证"，但 `test_contract` 仅断言 `timed_out`，未在超时后断言 daemon 中无残留容器（如 `docker ps -a --filter ...`）。机制本身正确（`--rm` 只在容器自然退出时移除，kill CLI 后孤儿容器由 `docker rm -f <cid>` 兜底），但缺少"无残留"的强断言。可在契约测试超时分支后追加一次 `docker ps -aq | grep -c <cid>` 类校验（docker 环境跳过条件已存在）。

### Issue 4（minor，观察项）— 后台路径仍不应用 config timeout

`BashTool._execute_background` → `BackgroundTaskManager.start(timeout=None)` → `_monitor` 无超时（`background.py:135-138`）。Round 1 Issue 1 提及后台路径"同理"，但 9.1 只修了前台。判定为**设计合理而非缺陷**：design.md line 92 把 timeout 默认语义限定在 `ExecutionBackend.run()`（后台走 `run_background()`，无 timeout 参数），后台任务"无显式 timeout 则一直运行"是标准语义（长任务 + TaskOutput 轮询/stop），且工具 schema 的 `"default": 30` 仅作 LLM 提示、框架不注入默认值（`registry.execute` 直接 `tool.execute(**arguments)`）。无需修复，记录为设计事实。

### Issue 5（minor，观察项）— attach 残留窄竞态

`_attach` 的 `proc.returncode` 检查存在窄窗口：子进程已退出但 asyncio 尚未 reap（returncode 仍 None）时，attach 写死 pid 到真实 cgroup.procs 会 ESRCH → 返回 False → 快命令偶发误标 degraded。仅影响真实 cgroup 宿主（本环境走 degraded 路径不触发），且 degraded 仅标志位+单次事件，影响低。非阻塞项。

## 8 维度评估

- **任务逐项验证**：tasks.md 第 5/6/8/9 节全部 `[x]` 均有真实代码 + 测试；第 7 节收尾（设计审阅任务/benchmark smoke/spec 同步）证据充分。9.4/9.5 测试覆盖偏弱（见 Issue 1/2/3）。
- **正确性**：cgroup v2 工程细节（per-run 唯一目录、starttime 防 pid 复用、oom 基线、cleanup 幂等、cpuset 初始化）正确；timeout 透传正确；attach 三态语义正确（旧实现把"进程先退出"误判为 degraded 是真实 bug，已修）。
- **Spec 对齐**：`openspec/specs/workspace-safety/spec.md` 含 cgroup v2 资源限制 + 沙箱事件入 trace 两个 ADDED requirement + ExecutionBackend 2 新 scenario，与实现一致；spec delta 同步完成（workflow-events seq 3）。
- **冗余度**：sweep_stale/cleanup 与 `is_supported` 职责边界清晰；`run_sync` 标注为无 cgroup 的辅助方法（design 限定 async run()）。无重复实现。
- **测试覆盖**：回归测试整体充分（timeout 透传/sweep/非 OSError degrade/attach 失败 degrade/超时杀进程树均有），但 9.5 skip 路径无确定性测试、Docker 孤儿无强断言（Issue 2/3）。
- **安全性**：sweep_stale 不触碰 live pid（os.kill(pid,0) + rmdir EBUSY 兜底）；cleanup 只在 starttime 匹配时 `cgroup.kill`；docker `rm -f` 只针对本 run 的 cid；无越权路径。timeout 透传后默认仍受后端构造值约束，无无限运行回归。
- **可维护性**：sandbox_events contextvar sink + loop save/restore（镜像 `_active_trace_recorder` 模式）清晰；`_attach` 三态 docstring 明确；`--cidfile` 流程注释充分。
- **CI 完整性**：全量 pytest 绿（1516 passed, 7 skipped, 1 deselected=已知环境失败）；OpenSpec strict validate 32/32；`check_openspec_artifacts.py` 仅报 review manifest missing（预期，PASS 后生成）。**但 Issue 1 的 flaky 测试是 CI 稳定性隐患**。

## Test Results（Round 2）

- 第二批相关测试文件：`test_cgroup` / `test_process_backend_cgroup` / `test_bash_tool_events` / `test_sandbox_backends` / `test_sandbox` / `test_background` / `test_config` / `test_sandbox_events` / `test_loop_sandbox_events` / `test_factory_sandbox_wiring` / `test_command_guard`：**136 passed**（首轮组合跑 1 failed=flaky 复现，重跑绿）
- 全量 pytest（排除已知 `test_tree_sitter_extracts_java_and_kotlin_symbols`）：**1516 passed, 7 skipped, 1 deselected**
- OpenSpec strict validate：**32 passed, 0 failed**
- 受保护 artifact：b8927b6 修复提交未改动 `openspec/specs/**` / `docs/openspec-change-backlog.md` / archive / known-*，workflow-events seq 1-3 覆盖此前的 spec 同步与设计审阅事件，无缺事件

## 结论

Round 1 的 1 中等 + 4 minor 在代码层面全部修复到位，修复质量高且未引入新的生产代码缺陷；timeout_seconds 主路径生效、cgroup 清扫/异常兜底/Docker 容器清理/attach 三态均正确，且有对应回归测试（9.4/9.5 断言偏弱）。唯一需修复的中等问题是**批内 flaky 测试** `test_limits_apply_cgroup_when_supported`（两次实际观测失败，威胁 CI 稳定性），外加 9.5 缺确定性回归测试的 minor 覆盖缺口。修复这两个测试问题后即可 PASS。
