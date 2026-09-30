# Building Review: bash-command-guard-redesign

> 独立零记忆审阅者执行（每轮独立 spawn，不继承开发上下文）。base = `origin/master`（`merge-base` = `e0e3c87`）。
> 本报告为**收敛后的合并版**：逐轮原文见 git 历史（每轮写回本文件后被下一轮覆盖）。

## Verdict

**PASS**（第 6 轮，最终）

**为什么不是 3 轮封顶就停**：前 5 轮每轮都在**同一族**（命令经选项值传给解释器/launcher）里发现一种**与上一轮修复不同的** fail-open：

| 轮 | 发现 | 性质 |
|---|---|---|
| 1 | `script -c '<cmd>'` 被当普通选项值剥掉；`weird a b c d cp …` 用填充 token 把命令推出 `rest[1:5]` 窗口 | 本 change 引入（新增的 launcher 机制） |
| 2 | 轮 1 的修复作用域过宽（`-c` 当所有命令的命令选项 → `grep -c` 误伤）且不完备（重复 `-c` 只判第一个） | 轮 1 修复自身 |
| 3 | 轮 2 删掉 payload 路径后 `nice script -c '…'` 失明；`watch -d` 被当吃值选项 | 轮 2 修复自身 |
| 4 | 轮 3 的修复依赖 launcher arity 表 ⇒ `flock`/`chroot`/`taskset -c`/`perf`/`setarch` 等 10 个变体仍失明 | 轮 3 修复自身 |
| 5 | 连写取值拼法（`script -c'…'`、`--command=…`、`env -S'…'`）落在精确 token 比较之外 | 轮 4 修复自身 |
| **6** | **穷举 4224 组合，敏感载荷 0 条放行** | **收敛** |

第 6 轮不再逐条打补丁，而是**穷举整个拼写空间**（载体 × 拼写 × 载荷 × 前导 launcher）后一次修完，并把该穷举固化为测试 `TestOptionSpellingSpaceClosed`。**此前每一轮的「修好」都是真的，但都不完整**；现在覆盖面由穷举定义，而非由枚举表定义。

## 端到端安全的最终状态

| 检查 | 结果 |
|---|---|
| attack suite（73 条，guard-deny 69 条） | **69/69 DENY**；attacks.json 只增不减（54→73，0 修改/删除） |
| 迁移对拍 `旧 DENY ⊆ 新 DENY ∪ 新 ASK` | **PASS**（355 条语料，0 违规；4 条有意豁免见 `migration-comparison.md`） |
| 选项拼写穷举（4224 组合） | **敏感载荷 0 条 ALLOW**；144 条良性对照全 ALLOW |
| launcher × `script -c`（`_LAUNCHERS` 全集 27 个） | **0 条 ALLOW** |
| 回退开关忠实度（`ASTERWYND_GUARD_LEGACY=1` vs 旧代码） | **377/377 一致** |
| 全量 `uv run pytest -q` | 只有 2 条**已知环境失败**（`tests/agent/memory/test_persistent.py::TestFindScopeRoot::*`，本机 `/tmp` 是 git 仓库所致，基线同样失败） |
| `openspec validate --all --strict` | 29/29 |

## 变异验证（每轮独立复跑，均已还原）

| 变异 | 变红测试数 |
|---|---|
| 谓词模板词表删 `example`（`workspace_policy`） | 3 |
| `is_env_template_name` 的 `all()` → `any()` | 5 |
| `_check_analysis` 丢弃 argv 的分支改 `if False` | 1（直构路径） |
| `if verdict is CommandVerdict.ASK` → `if False`（fail-open） | 4 |
| `-d` 加回 `watch` 的取值集 | 2 |
| `_LAUNCHER_COMMAND_OPTION` 改坏 | 10 |

## 记为本 change 之外 / 已知债务（不影响通过判定）

- **`_env_source_is_credential`（`workspace_policy.py:116-127`）是「mv/cp 源敏感」的第 3 处实现**——D9 / tasks 2.7 计划把这类判定统一到 IR，但源位置在 policy 层没有 IR 可消费。**属真实债务**，建议后续 change 收敛。
- **spec 说 launcher 族 `SHALL ask`，实现返回 `DENY`**（`nsenter -t 1 cp x .env` 等）：实现更安全，但文本未对齐。
- **护栏不覆盖「Bash 读凭据变体」**（`cat .env.local`）：本 change 的范围是写侧；读侧由 `workspace_policy` 覆盖（文件工具），Bash 的读未纳入。
- **3 项未实现任务**（tasks.md 已标 `⛔` 并说明处置）：3.4（执行中审批的 trace 事件，属可观测性增量）、4.6（已被 4.1 的等价机制覆盖）、4.8（不属护栏层）。
- **能力范围矩阵的「测试名可被 `pytest --collect-only` 解析」无机械校验**（tasks 6.1 的附加项）。

## Test Results

```
$ uv run pytest -q
2 failed, 3766 passed, 9 skipped  （2 failed = 已知环境失败）
$ npx --yes @fission-ai/openspec@1.4.1 validate --all --strict
Totals: 29 passed, 0 failed
```

## 结论

核心安全线成立：攻击集拦截数未降、迁移对拍零违规、拼写穷举零放行、回退开关忠实。**五轮发现的 fail-open 全部是本 change 新增 launcher 机制的路径**（旧实现没有这套机制，因此也不是「相对 master 的回归」），且每轮都由独立审阅者用可执行证据发现并修复——没有引入未解决的 fail-open。债务项已如实登记，不阻塞归档。
