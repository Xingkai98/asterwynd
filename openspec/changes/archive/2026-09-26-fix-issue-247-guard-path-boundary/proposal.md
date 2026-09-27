# Proposal: 命令护栏路径边界误报与漏网根治（fix-issue-247-guard-path-boundary）

关联跟踪 issue：[#247](https://github.com/Xingkai98/asterwynd/issues/247)（【bugfix】命令护栏把 `2>/dev/null` 误判为「重定向到受保护路径」）。

## Change Type

- primary: bugfix
- secondary: []

## Why

session `edd3b6ded5eb`（2026-09-25 真 LLM 跑 workflow 演示）的**第一条** Bash 调用即被拒：

```
命令：ls -la && echo "---" && git log --oneline -5 2>/dev/null | head
返回：Error: Command denied by sandbox command guard
```

从该现象出发排查，发现根因是**一个根因、两个方向**的缺陷：`CommandGuard` 判定「路径是否落在受保护前缀/工作区内」时，全部使用裸 `str.startswith(prefix)`，**缺少路径段边界**。同一个缺陷：

- 在**受保护路径**侧造成**误报**（拒绝合法命令）——issue #247 记录的方向；
- 在**工作区边界**侧造成**漏网**（放行应当拒绝的命令）——本 change 排查时新发现的方向，`#247` 正文未记录。

### 根因：`startswith` 缺路径段边界

`_DENY_PATHS = ("/etc", "/proc", "/sys", "/dev", "/root", "/boot", "/var")`（`agent/tools/command_guard.py:25`）与 `self._workspace` 都按**裸前缀**比较。后果分两侧：

**误报侧（13 类，实测）**——合法命令被拒：

| 族 | 机制 | 实测被拒样本 |
|---|---|---|
| A. fd 前缀重定向 | `tokenize_command` 把 `2>/dev/null` 拆成 `['2', '>', '/dev/null']`，`/dev` 命中 `_DENY_PATHS` | `ls -la 2>/dev/null`、`echo hi > /dev/null`、`git log 2>/dev/null \| head` |
| B. 受保护前缀的「假朋友」 | `/various` 以 `/var` 开头、`/rooted.log` 以 `/root` 开头、`/etcetera.conf` 以 `/etc` 开头 | `echo x > /various.txt`、`echo x > /rooted.log`、`echo x > /bootstrap.log` |
| C. 普通点目录 | `_EXTRA_DENYLIST` 的 `\S*/\.[a-z]+\b` 分支匹配**任意**点目录 | `cp r.md docs/.draft/x.md`、`mv x src/.cache/`、`cp x /tmp/.hidden/` |

误报面**不限于 `2>/dev/null`**：本 change 的良性命令电池（26 条日常命令）实测**误拒 17 条**。且拒绝理由是 `protected_redirect`，**误导性极强**——agent 会以为自己写了危险命令。

**漏网侧（安全缺陷，实测）**——应拒命令被放行：

```python
if self._workspace and normalized.startswith("/") and not normalized.startswith(self._workspace):
```

`rm -rf /tmp/ws-evil` 在 `workspace=/tmp/ws` 时 `startswith("/tmp/ws")` 为真 ⇒ **放行**，但它落在工作区**之外**。同类还有 `/tmp/wsX`、`/tmp/ws-evil/x`。该分支是「rm 递归+强制不得越出工作区」的最后一道判断（`_check_rm`），前缀碰撞即绕过。

### 影响面

`CommandGuard` 由 `agent/tools/builtin/bash.py:54` 构造，**所有 AgentLoop 的 Bash 调用**都过它（main/web/benchmark 三入口一致），影响不限于 workflow 场景：

- **误报**每天都在降低 agent 的 shell 可用性，且报告的是误导性理由；
- **漏网**削弱「rm 越界防护」，是本仓库 `workspace-safety` spec 明文要求的能力（`:207`「SHALL 拒绝……rm 递归+强制目标越界」）。

### 不修则无法验收的既有测试

`tests/agent/tools/test_command_guard.py:122,164,176` 用 `/etc-passwd/foo` 这类**假朋友路径**断言「应拒绝」，即**把误报固化成了契约**。修 `startswith` 边界后这三条断言会失效（`/etc-passwd` 不再命中 `/etc`）。它们需要改用**真受保护路径**（如 `/etc/passwd`）重新表达意图——这不是「为过测试而改测试」，而是纠正被写错的契约：`/etc-passwd/foo` 从来不是 `/etc` 下的文件。

## Goals

1. 消除受保护路径侧的误报：`2>/dev/null`、`> /dev/null` 等 fd 重定向与假朋友前缀路径不再被拒。
2. 消除工作区边界侧的漏网：`rm -rf` 不得越出工作区（前缀碰撞不再绕过）。
3. 收窄 `_EXTRA_DENYLIST` 的 `mv/cp` 点目录分支，只拦真敏感点目录（`.git`/`.ssh`/`.env` 等）。
4. **不削弱任何既有攻击拦截**：`benchmarks/attacks/attacks.json` 的 guard-deny 用例拦截数不得下降。
5. 新增回归测试并修正被误报固化的既有断言。

## Non-Goals

- 不重构 `CommandGuard` 的整体架构（不引入 AST 解析、不做 shell 语义模拟）。
- 不扩大 denylist 覆盖面（那是另一个议题，与本 change 的「修正边界判定」正交）。
- 不改动 `_has_pipe_to_shell`（该判定不涉及路径前缀）。
- 不改动 sandbox 后端（`ProcessBackend`/`DockerBackend`）——护栏不是边界，本 change 只修正护栏的判定精度。
- 不处理 #247 正文提到的方案 2（tokenizer 层面区分 `2>`）——见 design 的备选方案评估。

## 两个方向的修复策略

### 方向一：受保护路径判定 —— 改为路径段边界 + 设备文件豁免

引入路径段边界判定（`target == prefix or target.startswith(prefix + "/")`），替换 5 个调用点的裸 `startswith`：

| 调用点 | 行 |
|---|---|
| `_has_protected_redirect` | `command_guard.py:178-186` |
| `_check_rm` | `command_guard.py:216-233` |
| `_check_mv_cp` | `command_guard.py:236-245` |
| `_check_chmod` | `command_guard.py:248-259` |
| `_check_curl_wget` | `command_guard.py:262-270` |

并**豁免设备文件**：`/dev/null`、`/dev/stdout`、`/dev/stderr`、`/dev/fd/*` 不是可被破坏的受保护资产，是黑洞/标准流设备。豁免范围**仅限这四类**，其余 `/dev/*`（`/dev/sda`、`/dev/tcp/*` 等）保持拦截。

### 方向二：工作区边界判定 —— 同样改路径段边界

`_check_rm` 的工作区判断改为段级比较，消除 `/tmp/ws-evil` 绕过。同时明确 **workspace 根本身**是否可被 `rm -rf`：当前实现放行（`startswith` 为真），本 change 需给出结论（见 design 的 D3）。

## 安全性预验证（只读模拟，未改代码）

以本 change 拟采用的方案对全量攻击集（`benchmarks/attacks/attacks.json`，54 例）与良性命令电池（26 条）做只读仿真：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 攻击集 DENY | 50/54 | **50/54**（不变） |
| 良性命令误拒 | 17/26 | **0/26** |
| 真危险漏网 | 0 | **0** |

- 攻击集未拦截的 4 例是 `sensitive-read-001..004`（`cat /etc/passwd` 等），属**有意放行**（guard 是护栏不是边界，由 sandbox 隔离；`tests/benchmark/test_attack_suite.py` 显式单列该分类），修复前后一致。
- `yes > /dev/null` 修复后**仍被拦**——它走 `_EXTRA_DENYLIST` 的 `\byes\s+>\s*/dev/null`（`command_guard.py:59`），**不依赖** `protected_redirect`。
- 仿真为纯只读（未落盘、未提交），结论待实现阶段以真实测试坐实。

## Impact Analysis

### 受影响

- `agent/tools/command_guard.py`：5 个路径判定调用点 + `_EXTRA_DENYLIST` 的 `mv/cp` 点目录分支。
- `tests/agent/tools/test_command_guard.py`：`:122`、`:164`、`:176` 三条断言把误报当契约（`/etc-passwd/foo`），须改用真受保护路径重新表达。
- 新增回归测试：fd 重定向放行、假朋友路径放行、workspace 前缀碰撞拒绝、点目录收窄放行 + 真敏感点目录仍拒。

### 不受影响

- `benchmarks/attacks/attacks.json`：不改数据；拦截数保持 50/54（4 例 sensitive-read 为有意放行）。
- `agent/tools/sandbox/**`：护栏不是边界，后端不动。
- `_has_pipe_to_shell`、`_check_timeout` 的数值范围判定：不涉及路径前缀。
- denylist 的其它 57 条模式：不动。

### 待确认影响面

- **D3**：`rm -rf <workspace_root>`（工作区根本没有路径段边界可比）应拒还是应放行？倾向**拒绝**（删整个工作区是毁灭性操作，且历史上 `/tmp/ws` 这类路径常用于临时工作区）。
- **D4**：设备文件豁免是否应包含 `/dev/fd/*`（进程替换 `>(...)` 会用到，但当前 tokenizer 不解析进程替换）。倾向**纳入**，与 `/dev/null` 同性质。
- **D5**：`_EXTRA_DENYLIST` 点目录分支收窄后，敏感点目录白名单应含哪些（`.git`/`.ssh`/`.env`/`.aws`/`.gnupg`/`.kube`/`.docker`/`.netrc`/`.npmrc`/`.pypirc`）？倾向按此清单，但需确认无遗漏的既有攻击用例。
- **D6**：是否要同时把「`/dev/null` 不算受保护目标」写进 `workspace-safety` spec（本 change 已含 spec delta，见下）。

以上 D3–D6 是 grill 阶段逐项追问的输入。

## Spec 影响

`openspec/specs/workspace-safety/spec.md:205-227` 的 Requirement「命令护栏（轻量分词 + argv 语义校验）」钉了「SHALL 拒绝危险命令模式（rm 递归+强制目标越界、重定向到受保护路径……）」。本 change：

- **不删除**该 Requirement；
- 追加两条 Scenario 澄清判定精度：`/dev/null` 等设备文件**不构成**「重定向到受保护路径」；受保护路径按**路径段**判定（`/various.txt` 不因以 `/var` 开头而被拒）。
- 追加一条 Scenario 澄清工作区边界按路径段判定（`/tmp/ws-evil` 不得因以 `/tmp/ws` 开头而放行）。

属 **MODIFIED**（在原 Requirement 下追加 Scenario，澄清既有意图的实现精度）。

## Reference Implementation Research

- research_tier: exempt
- status: disabled
- reason: 本 change 是 bugfix（无新增能力面，只修正既有判定的边界精度——`startswith` → 路径段比较 + 设备文件豁免），且已有回归测试覆盖要求。依据：`#247`（本 change 关联的已登记 bugfix issue）；`openspec/changes/archive/2026-09-24-fix-issue-226-browser-test-flake`（同类 bugfix 的先例，其 RIR 亦为 exempt）。
- findings: 本工作区 `.dev/reference-repos.txt` 所列本地参考仓库与 `.codegraph/` 目录均不可用（已核实不存在），故未做参考仓库对比。业界依据：命令护栏的「前缀匹配需带路径段边界」是 POSIX 路径语义的常规要求（`/var` 与 `/various` 是不同目录），设备文件（`/dev/null` 等）在任何 Unix 权限模型下都不属于「受保护的系统目录」语义；本仓库 `command_guard.py:1-15` 自述「guardrail, not boundary」，与业界共识（正则/前缀命令校验可绕过，真实边界在执行后端）一致。
- design impact: 无新增依赖、无新协议、无架构改动；仅收敛判定函数并补回归测试。

## 测试策略

1. **回归测试（必须，仓库硬规则）**：新增数据驱动用例表，覆盖误报侧（fd 重定向 / 假朋友路径 / 普通点目录 → 应 ALLOW）与漏网侧（workspace 前缀碰撞 → 应 DENY），外加真危险对照（真受保护路径 / 真敏感点目录 → 应 DENY）。
2. **修正被误报固化的既有断言**：`test_command_guard.py:122,164,176` 改用真受保护路径；同时确认 `test_reason_protected_redirect`（`:164`）仍能验证 `protected_redirect` 这条 reason 可达（改用 `/etc/passwd` 之外的、denylist 不覆盖的真受保护路径，如 `/var/log/x`）。
3. **攻击集回归**：`tests/benchmark/test_attack_suite.py` 必须保持全绿且拦截数不下降。
4. **变异验证（判别力证明）**：还原 `startswith` → 新回归测试必红；应用修复 → 必绿。

## 文档影响

- `docs/known-issues.md` / `docs/known-debt.md`：**待核实**是否已有 #247 相关记录（收尾阶段关键词扫描），无则新增。
- `docs/openspec-change-backlog.md`：登记本 change（受保护路径，需 `workflow-events.jsonl` 解释事件）。
- `docs/development-guide.md` / `docs/testing-guide.md`：待扫描是否提及命令护栏的判定口径。

## 跟踪约定

- 关联 issue：#247（PR 合入后 comment + 关闭）。
- 分支：`fix-issue-247-guard-path-boundary/2026-09-26`（worktree 隔离）。
- 流程：grill（`batch-grill-me`，含停轮确认 Open Questions）→ `/opsx:apply` 实现 → `/review-loop` 独立审阅 → PR 含归档收尾。
