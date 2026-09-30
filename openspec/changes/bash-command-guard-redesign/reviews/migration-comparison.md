# 迁移对拍报告（design D10 / tasks 6.7）

本报告由实测脚本生成，非手写。断言：**旧 `DENY` ⊆ 新 `DENY` ∪ 新 `ASK`**。

## 方法

- **「旧」代码**：`git worktree add --detach /tmp/mig-old 9373e9c`——本 change 实现开始前的 commit（`proposal/design/tasks/spec delta` 已定稿、`agent/**` 未改）。用独立 worktree 跑真实旧代码，不用回退开关近似。
- **「新」代码**：当前 HEAD。
- **语料（355 条）**：`benchmarks/attacks/attacks.json` 全部用例 + `tests/agent/tools/test_command_guard.py` 与 `tests/agent/test_workspace_policy.py` 中出现的命令串。
- **脚本**：`/tmp/bcg-probe/mig_cases.py`（收集语料）、`/tmp/bcg-probe/mig_run.py`（对任一版本跑 `CommandGuard(workspace="/tmp/ws").check(c)`）。

## 结果

```
corpus 355: old deny 194, new deny 194, new ask 5
旧 DENY ⊆ 新 DENY ∪ 新 ASK : PASS   (violations: 0)
```

**结论：没有一条旧 DENY 在新实现下变成 ALLOW。** 新实现还多出 5 条 ASK（见下）。

## 新增的 ASK（5 条，均为语料中的字符串片段，非真实命令）

```
'"'                                            (allow->ask)
'>'                                            (allow->ask)
'|'                                            (allow->ask)
'-fr 和 -r -f 都应识别 rm 的递归+强制 flag'      (allow->ask)
'豁免不扩展到 rm（Q2 拍板：不放宽 rm 对 /dev/ 的拦截面）。' (allow->ask)
```

前三条是单字符片段（从测试的断言文本里收集到的引号/管道符），后两条是测试的说明文字。它们经解析都是**畸形输入**，按 D4 的 fail-closed 处置返回 `ask`——**narrow 方向安全**（无 UI 环境 `ask` = 拒绝），且它们不是任何人会执行的命令。

## 新放宽（deny -> allow）

**无。**

## 攻击集拦截数

- 语料内 attacks.json 全部 guard-deny 用例：**新实现 69/69 DENY**（原 54 条中的 50 条 guard-deny 用例保持 50/50）。
- `attacks.json` 只增不减：54 → 73 条，**0 条被修改或删除**（`git diff origin/master...HEAD -- benchmarks/attacks/attacks.json` 只有新增行）。

## 回退开关的忠实度

`ASTERWYND_GUARD_LEGACY=1` 关闭 IR 驱动规则。在**同一份 377 条历史基线**上：

```
legacy 模式 vs 旧实现: 377/377 裁决一致
```

即回退开关可完整还原旧行为（含旧实现的数据 heredoc 误报），迁移窗口内可随时回退。注意：legacy 模式**不**还原本 change 新增的 19 条攻击用例的覆盖（那些形态旧实现本来就不拦），守卫测试 `test_legacy_never_weakens_the_attack_set` 锁住这一点。
