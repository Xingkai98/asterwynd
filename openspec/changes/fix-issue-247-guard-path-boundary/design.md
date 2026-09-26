# Design: 命令护栏路径边界误报与漏网根治（fix-issue-247-guard-path-boundary）

## Context

issue #247 记录 `2>/dev/null` 被误判为「重定向到受保护路径」。本次诊断（见 `diagnosis.md`）确认真实根因不是 `2>/dev/null` 这一个特例，而是 `CommandGuard` 的**路径前缀判定缺路径段边界**——同一个缺陷在受保护路径侧表现为**误报**（良性命令电池 26 条误拒 17 条），在工作区边界侧表现为**漏网**（`rm -rf /tmp/ws-evil` 绕过 rm 越界防线）。

`CommandGuard` 是**所有 AgentLoop Bash 调用**的入口（`agent/tools/builtin/bash.py:54`，main/web/benchmark 三入口一致）。它自述为「guardrail, not boundary」（`command_guard.py:1-15`）：真实边界在执行后端（ProcessBackend/DockerBackend），护栏只拦常规绕过模式。这一自我定位是本 design 的**边界条件**——修复目标是「判定精度」，不是「把护栏做成安全边界」。

约束：
- 攻击集 `benchmarks/attacks/attacks.json`（54 例）的拦截数不得下降（`workspace-safety` spec `:229` 钉了「SHALL 断言所有 guard-deny case 被拦截」）。
- 既有测试 `test_command_guard.py:122,164,176` 把误报写成了契约，修复必然使其失效，需重新表达而非删除。
- 本 change 是 bugfix，走 `exempt` 调研档位（无新增能力面）。

## Goals / Non-Goals

### Goals

1. 受保护路径判定引入**路径段边界**，消除假朋友前缀误报（`/various.txt` 不再被当作 `/var` 下路径）。
2. **设备文件豁免**：`/dev/null` 等不再是「受保护路径」语义，消除 fd 重定向误报。
3. 工作区边界判定同样引入路径段边界，消除 `rm -rf` 前缀碰撞漏网。
4. `_EXTRA_DENYLIST` 的 `mv/cp` 点目录分支收窄，只拦真敏感点目录。
5. 攻击集拦截数不下降；新增回归测试 + 修正被误报固化的断言。

### Non-Goals

- 不把护栏升级为安全边界（不引入 AST 解析、不做 shell 语义模拟、不解析进程替换）。
- 不重构 tokenizer（备选方案 B 被否，见 Decisions）。
- 不扩充 denylist 覆盖面（正交议题）。
- 不改 sandbox 后端、不改 `_has_pipe_to_shell`、不改 `_check_timeout` 的数值范围判定。

## Decisions

### D1：路径段边界的判定式

**选定**：

```python
def _within(path: str, prefix: str) -> bool:
    """path 是否等于 prefix 或位于 prefix 之下（路径段边界，非裸前缀）。"""
    return path == prefix or path.startswith(prefix + "/")
```

**理由**：POSIX 路径语义中 `/var` 与 `/various` 是无关的两个顶层项；只有 `path == "/var"` 或 `path` 以 `"/var/"` 开头才算「在 `/var` 下」。`prefix + "/"` 拼接天然截断了「前缀碰撞」这一类。

**备选（否决）**：用 `pathlib.PurePosixPath` 做 `is_relative_to`。否决理由——`PurePosixPath` 会规范化路径（折叠 `..`、去掉重复 `/`），而护栏面对的是**未求值的原始字符串**（可能含 `$VAR`、`~`、glob），规范化会掩盖绕过变体；且引入对象分配，而护栏是每条命令都跑的热路径。

### D2：设备文件豁免的范围（用户拍板 Q2 + Q3）

**选定**：
1. 豁免目标 `_DEVICE_EXEMPT = ("/dev/null", "/dev/stdout", "/dev/stderr")`；**不含** `/dev/fd/`（Q3 拍板）。
2. 豁免**只覆盖两处判定**：重定向目标（`_has_protected_redirect`）与 mv/cp 目标（`_check_mv_cp`）。**rm / chmod / curl-wget 的 `@` 参数保持拒绝设备文件**（Q2 拍板）。

**理由**：这三类在任何 Unix 权限模型下都不是「受保护的系统目录内容」——`/dev/null` 是黑洞设备，`/dev/stdout`/`/dev/stderr` 是当前进程的标准流别名。重定向/复制到它们是**写入本进程的输出流**，不构成对系统资产的破坏。`yes > /dev/null`（CPU spin）之所以危险不是因为重定向目标，而是因为 `yes` 本身——由 `_EXTRA_DENYLIST:59` 的专用正则拦截，与本豁免正交（见 `diagnosis.md` 证据 5）。

**Q3 拍板理由（不纳入 `/dev/fd/`）**：design 原写的纳入理由是「进程替换 `>(...)` 的落点」，**已被 grill 实测证伪**——本仓库 tokenizer 对 `python3 x.py > >(tee log)` 输出 `['python3','x.py','>','>','(tee','log)']`，**从不产生 `/dev/fd/*` token**。纳入的唯一实际效果是让 `cmd 2>/dev/fd/1` 转为放行，属「为一个不存在的场景放宽拦截面」。豁免面越小越安全。

**Q2 拍板理由（豁免范围收窄到重定向 + mv/cp）**：不放宽 `rm` 对 `/dev/` 的拦截面——`rm -rf /dev/...` 本就被视为危险操作（符号链接与设备节点的 `rm` 可能产生超出预期的破坏）；`curl -d @/dev/null` 同理保持拒绝。代价：spec delta 的原文需按此收窄（原写「rm/mv/cp/chmod 目标、curl/wget 的 @ 参数」全豁免，与 tasks 口径矛盾——见 grill R3）。

**备选（否决）**：把整个 `/dev` 从 `_DENY_PATHS` 移出，靠 denylist 承担 `/dev/sd*` 等。否决理由——denylist 是**字面正则**，只覆盖已知变体（`>\s*/dev/sd[a-z]`、`dd\s+of=/dev/`），移出 `_DENY_PATHS` 会让 `echo x > /dev/sda`（非 `dd`）这类未知变体漏网。保留 `/dev` 在 `_DENY_PATHS`、只豁免三个已知良性目标，是「最小豁免面」原则。

### D6：`..` 穿越规范化（用户拍板：本 change 内一并修，且「一把修好」）

**用户答复**：「穿越这个按你推荐，不过要**一把修好了**，因为我印象中很多地方都有用到这个路径检测」。

**选定**：`_within` 之前先做路径规范化（`os.path.normpath`），消除 `..` 穿越：

```
_within(normpath("/tmp/ws/../etc"), "/tmp/ws")  # normpath → /tmp/etc → False → DENY ✓
```

**为什么必须做**（grill Q6 实测）：`rm -rf /tmp/ws/../etc`（workspace=`/tmp/ws`）当前 **ALLOW**，且**仅加段边界判定仍 ALLOW**——`"/tmp/ws/../etc".startswith("/tmp/ws/")` 为真，`..` 未被解析。这与本 change 的 workspace-escape 语义直接冲突，同一函数修完还留绕过。

**「一把修好」的范围界定**（主 session 全仓扫描结果）：用户提示「很多地方都用到」，故本 change 做了一次全仓路径包含判定扫描，区分出**同类缺陷**与**已正确实现**：

| 位置 | 手法 | 是否同类缺陷 | 处置 |
|---|---|---|---|
| `agent/tools/command_guard.py` 5 处 | 裸 `startswith`，无规范化 | **是**（误报 + 漏网 + `..`） | 本 change 修 |
| `scripts/workflow_guard.py:524` `_is_change_doc_write` | `startswith(prefix)`，但 prefix 已带尾 `/`，且源是 hook 传入的规范化路径 | 否（尾 `/` 已提供段边界） | 不改 |
| `scripts/workflow_guard.py:127` `_norm_path` | `os.path.normpath` **已解析 `..`** | **否——这是正确参照** | 不改；`command_guard` 应对齐它的做法 |
| `scripts/check_openspec_artifacts.py:1274` | `path.startswith(pattern)` 用于 `openspec/specs/` 等 | 否（输入是 CI diff 的 canonical 路径，非任意用户串） | 不改 |
| `agent/session.py:201` | `os.path.commonpath([full, root_real]) != root_real` | 否（commonpath 已按段比较） | 不改 |
| `agent/workspace_policy.py:163,219,233` 等 | `Path.relative_to()` | 否（pathlib 已是段级） | 不改 |
| `agent/subagent/workflow_store.py:parse_ref` | 段级白名单 + 显式拒 `.`/`..` | 否（**已是正确实现，可参照**） | 不改 |

**结论**：真正的同类缺陷**只在 `command_guard.py` 内**（5 处判定）。仓库其余路径包含判定要么用 `pathlib.relative_to`/`commonpath`（段级正确），要么输入本身已规范化。`command_guard` 是**唯一**对「任意用户输入的原始命令串」做前缀近似匹配的地方——这既是它缺陷集中的原因，也界定了本 change 的边界。

**参照实现**：`workflow_guard._norm_path`（`os.path.normpath` + 剥离 `./`）与 `workflow_store.parse_ref`（段级白名单 + 拒 `.`/`..`）是本仓库内两处正确做法，`command_guard` 的修复对齐它们。

**残留说明**：`os.path.normpath("a/../../etc/passwd")` → `"../etc/passwd"`（相对路径的 `..` 溢出无法完全消除）。对**绝对路径**（`_DENY_PATHS` 与 workspace 判定的主要输入）规范化是完备的；对相对路径溢出，`_within` 返回 False ⇒ 判为「不在保护前缀内/不在工作区内」⇒ 对 rm 走 workspace 分支时**拒绝**（安全方向）。

### D3：`rm -rf <workspace_root>` 本身应拒还是应放行

**选定（用户拍板：拒绝）**：**拒绝**。

**理由**：`_check_rm` 的工作区判断语义是「rm 递归+强制不得越出工作区」。`rm -rf /tmp/ws` 删除的是工作区**本身**，等价于把 agent 的工作台连根拔起——它虽然是「边界上」的路径，但破坏性与越界相当。当前实现因 `startswith` 为真而**放行**，与语义不符。改用 `_within` 后，`path == prefix` 为真仍需**显式拒绝**——即工作区判断要写成「`path` 在工作区内**且不等于**工作区根」才放行。

**备选（否决）**：维持放行。否决理由——`/tmp/ws` 这类路径在本仓库的 worktree / benchmark 临时工作区场景中很常见，误删整个工作区会静默毁掉进行中的工作。

### D4：点目录判定改为**段级**，不用正则（grill R1 修正，已实测）

**原设计（已否决）**：把 `\S*/\.[a-z]+\b` 换成白名单正则 `\.(git|ssh|env|...)`。**实测证伪**——正则形态两边都不成立：

| 形态 | 误报 | 漏网 |
|---|---|---|
| 无锚 `\.(git\|ssh\|...)` | `cp x .env.example`、`cp x .github/w.yml`、`cp x .dockerignore` 被判 DENY（重犯「前缀无段边界」同一类错误） | `cp x src/.git/hooks/x`、`cp x sub/.env/secrets`、`cp x proj/.npmrc` 全部漏过（原 `\S*/\.[a-z]+\b` 本可拦住这些**嵌套**敏感目录） |
| 「锚定」`(^|/)\.(...)(/\|$)` | 同样漏（`(^|/)` 在 token 中间失效） | 裸形态 `.env`、`.ssh/id_rsa` 全漏 |

**选定**：把该分支从 `_EXTRA_DENYLIST` 正则**移除**，改在 `_check_mv_cp` 里做**路径段判定**：

```python
_SENSITIVE_DOTDIRS = {".git",".ssh",".env",".aws",".gnupg",".kube",".docker",".netrc",".npmrc",".pypirc"}
_SENSITIVE_DOTFILES = {".env",".netrc",".npmrc",".pypirc",".gitconfig",".git-credentials"}

def _dest_is_sensitive(dest: str) -> bool:
    parts = [p for p in dest.split("/") if p not in ("", ".")]
    if any(p in _SENSITIVE_DOTDIRS for p in parts):
        return True
    return bool(parts) and parts[-1] in _SENSITIVE_DOTFILES
```

**理由**：段级判定天然带边界（「段**等于** `.git`」而非「以 `.git` 开头」），同时覆盖裸形态（`.env`、`.ssh/id_rsa`）与嵌套形态（`src/.git/hooks/x`、`sub/.env/secrets`），且不误报 `.gitignore`/`.github/`/`.env.example`/`.dockerignore`。实测 19 条用例全部正确（含 6 条误报检查 + 4 条嵌套敏感 + 4 条裸敏感 + 5 条普通点目录）。

**为什么不用正则**：正则要做对，需要同时表达「段起始」「段结束」「既可裸又可嵌套」三个约束，`(^|/)` 在 token 中间无法表达段起始（`^` 只匹配串首）。段级判定是这类问题的正确工具，继续堆正则会重蹈本 change 正在修的「字符串前缀近似路径语义」覆辙。

**待确认（grill Q4）**：清单是否纳入 `.pem`/`.key`/`.p12`/`id_rsa` 等**凭据文件后缀**。倾向不纳入——它们是文件后缀而非点目录，属另一类语义，纳入会扩大范围；当前清单已覆盖点目录族的凭据面。

**残余漏网（grill R6，应记录）**：`cp ~/.ssh/id_rsa /tmp/x` 的 **source 侧** `.ssh` 不在 `DEFAULT_DENYLIST` 的 `\bcp\s+(...\.env\b|\.git/)` 覆盖内，本来就漏；`_dest_is_sensitive` 只看 destination，不改这个既有面。按「护栏不是边界」口径记入 `docs/known-debt.md`，避免修复后产生「点目录已收紧即安全」的错觉。

### D5：既有断言的重写方式（grill R2 修正，已实测）

`test_command_guard.py:122,164,176` 用 `/etc-passwd/foo` 断言 DENY（假朋友路径，修复后必然失效）。改用真受保护路径重写。

**原设计（已证伪）**：`:122`/`:176` 改用 `/var/log/foo`。**实测证伪**——`mv /tmp/x /var/log/foo` 被 `DEFAULT_DENYLIST` 的字面量规则抢先（reason = `denylist`，而非 `mv_cp_dest`），reason 断言必失败。

**选定（实测 reason 已确认）**：

| 行 | 原断言 | 改用 | 实测 reason |
|---|---|---|---|
| `:122` | `timeout 5 mv /tmp/x /etc-passwd/foo` → `mv_cp_dest` | `timeout 5 mv /tmp/x /root/foo` | `mv_cp_dest` ✓ |
| `:176` | `mv /tmp/x /etc-passwd/foo` → `mv_cp_dest` | `mv /tmp/x /root/foo` | `mv_cp_dest` ✓ |
| `:164` | `echo x > /etc-passwd/foo` → `protected_redirect` | `echo x > /var/log/foo`（或 `/root/foo`） | `protected_redirect` ✓ |

**理由**：三条断言的**意图**是验证「真受保护路径被拦」与「两条 reason 可达」，`/etc-passwd/foo` 只是当年路径选择错误。`/root/foo` 与 `/boot/foo` 在 `_DENY_PATHS` 内且**不被** `DEFAULT_DENYLIST` 的 mv/cp 字面量覆盖，故能真正走到 argv 的 `mv_cp_dest` 分支；`echo x > /var/log/foo` 的 denylist 重定向规则只覆盖 `>\s*/etc/`、`/proc/`、`/sys/`，故能走到 `protected_redirect`。

**残余风险**：若将来 denylist 扩充覆盖 `/root/`，这两条 reason 断言会再次失效——已在实现时以实测坐实（见 tasks 2.6）。

## Pre-Implementation Review

### 已解决

- **根因归属**：不是 `2>/dev/null` 特例，是路径前缀判定缺段边界（`diagnosis.md` 证据 1）。
- **两个方向的确认**：受保护路径侧误报 + 工作区侧漏网，同根因。
- **攻击集安全性**：证据 5 确认 5 条 `/dev` 相关用例无一条依赖被修行为；只读仿真 50/54 → 50/54。
- **既有测试影响面**：定位到 3 条（`:122,164,176`），重写方案见 D5。

### 备选方案与否决

| 方案 | 内容 | 判定 |
|---|---|---|
| 仅豁免 `/dev/null` | 只修 issue #247 字面现象 | **否决**：漏掉假朋友前缀、点目录、workspace 漏网三族 |
| 修 tokenizer 识别 `2>` | 在分词层区分 fd 前缀 | **否决**：tokenizer 输出被多处消费（`_check_argv` 等），改输出形态影响面大；且 fd 前缀只是假朋友问题的一个特例，段边界判定能一并覆盖 |
| `PurePosixPath.is_relative_to` | 用 pathlib 做段级判定 | **否决**：会规范化路径，掩盖 `..`/变量类绕过（见 D1） |
| 移出整个 `/dev` | `_DENY_PATHS` 去掉 `/dev` | **否决**：denylist 是字面正则，移出会让未知 `/dev/*` 变体漏网（见 D2） |

### 剩余风险

1. **点目录清单遗漏**（D4）：段级判定的清单可能不含某些敏感项。缓解：只拦凭据/元数据面，其余按「护栏不是边界」口径接受并记 known-debt。
2. **`rm -rf <workspace_root>` 的行为变更**（D3）：从放行改为拒绝，可能影响既有用例或工作区清理流程。缓解：全量 pytest 验证 + 用户拍板（Q1）。
3. **`..` 穿越是既有绕过**（grill Q6，实测）：`rm -rf /tmp/ws/../etc` 当前 ALLOW，且按本 change 的段边界方案修复后**仍 ALLOW**（`_within("/tmp/ws/../etc", "/tmp/ws")` 为真）。这是既有洞、非本 change 引入，但与 workspace-escape 语义直接相邻，是否纳入需拍板。
4. **设备豁免范围**（Q2/Q3）：spec delta 与 tasks 口径不一致，须统一后再实现。
5. **良性命令电池未落库**（grill R4）：proposal/diagnosis 的「26 条 / 误报 17→0」缺可复算基线。缓解：把全集固化为测试数据（tasks 2.1–2.3 已列大部分，需补齐）。

### 最终确认

以下 Open Questions 已由独立 grill agent 产出并**经主 session 逐条实测复核**，须停轮获用户答复后方可写实现代码：

| # | 问题 | 主 session 复核结论 | 倾向 |
|---|---|---|---|
| Q1 | `rm -rf <workspace_root>` 应拒还是放行 | 当前 ALLOW；D3 倾向 DENY | 待拍板 |
| Q2 | 设备豁免覆盖哪些判定（spec 与 tasks 矛盾） | 实测 `rm -rf /dev/null` 两口径分歧 | 倾向重定向 + mv/cp |
| Q3 | `/dev/fd/*` 是否纳入豁免 | design 的原理由被证伪（tokenizer 不产生该 token） | 倾向不纳入 |
| Q4 | 敏感点目录清单是否含凭据文件后缀 | 段级判定已验证；清单范围待定 | 倾向不含 |
| Q5 | spec 最终文本口径 | 随 Q2 定 | 随 Q2 |
| Q6 | `..` 穿越是否纳入本 change | 实测确认是既有绕过，修复后仍在 | 待拍板 |

## Risks / Trade-offs

- **放宽 vs 收紧的净效应**：本 change 同时放宽（误报族）与收紧（漏网族 + workspace 根）。攻击集拦截数不变 + 真危险对照全拦，是这个权衡的量化验收口径。
- **白名单的维护成本**（D4）：新增敏感点目录需改代码。相比原模式「任意点目录」，这是精确性的代价，可接受。
- **设备豁免的边界**（D2）：豁免面越小越安全，但过小会留下误报。选定四类是该权衡下的最小充分集。

## Testing Strategy

1. **回归测试（TDD 先行，仓库硬规则）**：数据驱动用例表，分三组——误报侧放行（含 `2>/dev/null` 各族）、漏网侧拦截（workspace 前缀碰撞）、真危险对照（不得放松）。逐条断言 `CommandVerdict` 与（关键项）`last_reason`。
2. **既有断言修正**：按 D5 重写三条，保持其原意图。
3. **攻击集回归**：`tests/benchmark/test_attack_suite.py` 全绿、拦截数 ≥ 50。
4. **变异验证**：还原裸 `startswith` → 新增用例必红；应用修复 → 必绿。记录两向结果。
5. **全量回归**：`uv run pytest -q`（护栏是 Bash 入口，影响面广）。
6. **只读仿真复算**：实现后重跑本 change 的良性命令电池 + 真危险对照，与 design 的预测数字对齐。

## Impact Analysis

见 `proposal.md` 的 `## Impact Analysis`（受影响 / 不受影响 / 待确认影响面）。待确认项 D3–D6 与本文档 Decisions 一一对应，grill 后清理为明确结论。

## Reference Implementation Research

见 `proposal.md` 的 `## Reference Implementation Research`（`research_tier: exempt`）。
