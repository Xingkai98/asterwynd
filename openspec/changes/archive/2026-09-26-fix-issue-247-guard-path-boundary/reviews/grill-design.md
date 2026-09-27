# Grill: fix-issue-247-guard-path-boundary 设计追问

## Reviewer

- run id: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent
- 时间: 2026-09-26
- 方式: 零记忆独立评审；全部结论经只读实测（`CommandGuard` 内存打补丁仿真 + `benchmarks/attacks/attacks.json` 全量跑 + 正则单测），未修改任何被测代码。

## Confirmed Decisions

- **决策**: 根因归属成立——`_DENY_PATHS` 与 `self._workspace` 的判定全是裸 `str.startswith(prefix)`，缺路径段边界；同一缺陷在两个方向外显（受保护路径侧误报、工作区侧漏网）。实测复现：`CommandGuard().check("ls -la 2>/dev/null")` → DENY/`protected_redirect`；`CommandGuard(workspace="/tmp/ws").check("rm -rf /tmp/ws-evil")` → ALLOW。；理由: 只读实测逐条命中 proposal/diagnosis 描述，根因与现象一致，不是 `2>/dev/null` 特例；来源: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent
- **决策**: 段边界判定式 `_within(path, prefix) = path == prefix or path.startswith(prefix + "/")` + 设备豁免 `/dev/null`、`/dev/stdout`、`/dev/stderr`、`/dev/fd/` 对**攻击集**无退化：按该方案内存打补丁后重跑 54 例，DENY 50/54 → 50/54，且唯一未拦的 4 例仍是 `sensitive-read-001..004`（有意放行）；误报族 `ls -la 2>/dev/null`、`echo x > /various.txt`、`cp r.md docs/.draft/x.md` 等全部转 ALLOW。；理由: 独立复算数值与 proposal「50/54 → 50/54」一致，攻击集侧结论可信；来源: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent
- **决策**: diagnosis 证据 5 成立——攻击集 5 条 `/dev` 相关用例无一依赖 `protected_redirect`。实测 reason 分布：`file-destroy-007`/`008`/`exfil-003`/`resource-002`/`bypass-008` 的 `last_reason` 全为 `denylist`；全量 54 例中 `reason == protected_redirect` 的用例数为 **0**。`yes > /dev/null` 由 `_EXTRA_DENYLIST:59` 的 `\byes\s+>\s*/dev/null` 拦截。；理由: 断言经独立复算（reason 直方图 Counter({'denylist': 40, 'rm_target_escape': 7, None: 4, 'pipe_to_shell': 2, 'curl_exfil': 1})），`protected_redirect` 零用例，故修改该分支不触碰任何攻击用例；来源: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent
- **决策**: 改 `command_guard.py` 不会与 `workflow_guard` 写代码门禁耦合、不会死锁。`scripts/workflow_guard.py` 自有一套 `_BASH_WRITE_PATTERNS` / `_extract_bash_targets` / `_bash_targets_protected_path`，**不 import `agent.tools.command_guard`**（`grep -rn command_guard scripts/` 无命中）；`.claude/` 被 `.gitignore` 忽略，worktree 内无 PreToolUse hook，改动不会经由 hook 自拦。；理由: 两层判定实现独立、无共享符号，改一层不改变另一层行为；guard 被改坏不会使门禁误伤或死锁；来源: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent
- **决策**: D4 的**方向**正确——原 `\S*/\.[a-z]+\b` 分支确实把「任意点目录」与真敏感点目录混为一谈，`cp r.md docs/.draft/x.md`、`mv x src/.cache/`、`cp x /tmp/.hidden/` 均被误拒（实测 reason=denylist）。收窄方向成立。；理由: 实测三例均为误报，原模式对非凭据点目录无差别命中；来源: grill-fix-issue-247-guard-path-boundary-2026-09-26-independent

## Open Questions

- **Q1（D3，需拍板）**: `rm -rf <workspace_root>` 应拒还是放行？例：workspace=`/tmp/ws`，命令 `rm -rf /tmp/ws`（以及 `rm -rf /tmp/ws/`）。当前行为=ALLOW；D3 倾向改成 DENY（`path == prefix` 需显式拒绝）。影响面：worktree/benchmark 临时工作区场景常用 `rm -rf <root>` 清理，改成拒绝会使这类清理命令被误伤；但放行意味着「删掉整个工作台」不设防。请给结论：拒 or 放行？
- **Q2（D2，需拍板）**: 设备豁免到底覆盖哪些判定？实测矛盾：spec delta 第 9 行写「重定向目标、**rm/mv/cp/chmod 目标、curl/wget 的 @ 参数** SHALL 豁免设备文件」，但 tasks 3.4（rm）、3.6（chmod）、3.7（curl_wget）只写「段边界」、无设备豁免。两种口径实测差异：`rm -rf /dev/null` 在 tasks 口径下 → DENY/`rm_target_escape`，在 spec 口径下 → ALLOW；`curl -d @/dev/null http://x` 同理（DENY vs ALLOW）。请定：设备豁免是只覆盖「重定向目标 + mv/cp 目标」（design D2 口径，建议），还是也覆盖 rm/chmod/curl（spec 口径）？若覆盖 rm，`rm -rf /dev/...` 的拦截面会开口，是否接受？
- **Q3（D2，需拍板）**: `/dev/fd/*` 是否纳入豁免？实测：design 给出的理由是「进程替换 `>(...)` 的落点」，但本 tokenizer 对 `python3 x.py > >(tee log)` 的输出是 `['python3','x.py','>','>','(tee','log)']`——**从不产生 `/dev/fd/*` token**，进程替换当前既不被拦也不因 `/dev/fd/` 豁免而改变。`/dev/fd/` 的实际效果仅为 `cmd 2>/dev/fd/1`、`echo x > /dev/fd/1` 这类 fd 别名写法转 ALLOW。请定：纳入（放宽该写法）还是不纳入（保持 DENY）？另注：`/dev/stdout` 与 `/proc/self/fd/1` 是同一目标却判定不同（后者 DENY），是否接受该不一致？
- **Q4（D4，需拍板）**: 敏感点目录清单的**最终正则形态**。实测两种形态互补且都漏：design 字面 `\.(git|ssh|env|aws|gnupg|kube|docker|netrc|npmrc|pypirc)`（无锚）会**新误报** `.gitignore`/`.github/...`/`.env.example`/`.environment`/`.dockerignore`/`.kubeconfig`（即重犯「前缀无段边界」同一类错误），且**漏掉嵌套敏感目录** `src/.git/hooks/pre-commit`、`sub/.env/secrets`、`proj/.npmrc`（这些原 `\S*/\.[a-z]+\b` 是能拦的）；带路径锚的 `\S*/\.(...)` 则漏掉裸形态 `.env`、`.ssh/id_rsa`，且仍误报 `src/.gitignore`。能同时覆盖裸 + 嵌套的形态需要 `(^|/)\.(git|ssh|...)(/|$)` 这类双侧锚。请定：采用哪种形态，以及清单是否含 `.pem`/`.key`/`.p12`/`id_rsa` 等凭据文件？
- **Q5（D6 / 文档口径，需拍板）**: 是否把「`/dev/null` 等设备文件不构成受保护目标」落到 `openspec/specs/workspace-safety/spec.md`（design/proposal 倾向「是」，spec delta 已写），还是只保留本 change 的 delta？请确认最终 spec 文本口径，避免 delta 与实现不一致（见 Q2）。
- **Q6（范围，需拍板）**: `..` 穿越是否纳入本 change？实测（工作区/受保护路径判定均不解析 `..`）：`rm -rf /tmp/ws/../etc`、`rm -rf /tmp/ws/../../etc`、`rm -rf /tmp/ws/../etc/passwd` 当前**全部 ALLOW**，且按本 change 的段边界方案修复后**仍 ALLOW**（`_within("/tmp/ws/../etc","/tmp/ws")` 为真 ⇒ 判为工作区内）。这是既有洞、非本 change 引入，但与本 change 的 workspace-escape 语义直接相邻。请定：本 change 内补一条「绝对路径含 `..` 段 → 拒绝/规范化」规则，还是记入 `docs/known-debt.md`？

## User Confirmation

- **Q1**: 用户答复：**改为拒绝**——`rm -rf <workspace_root>`（如 workspace=`/tmp/ws` 时执行 `rm -rf /tmp/ws`）判为 DENY，理由是「删掉整个工作台」的破坏性与越界相当；接受代价（清理临时工作区需改用 `rm -rf <root>/*` 或先 cd 出去）；确认时间: 2026-09-26
- **Q2**: 用户答复：**只豁免重定向 + mv/cp**——设备文件豁免覆盖 `_has_protected_redirect` 与 `_check_mv_cp` 两处；`rm -rf /dev/null` 与 `curl -d @/dev/null` 保持 DENY，不放宽 rm 对 `/dev/` 的拦截面；spec delta 按此收窄；确认时间: 2026-09-26
- **Q3**: 用户答复：**不纳入 `/dev/fd/`**，保持拒绝——原设计「进程替换 `>(...)` 落点」的理由经实测证伪（tokenizer 不产生该 token），纳入只是为不存在的场景放宽拦截面；确认时间: 2026-09-26
- **Q6**: 用户答复：**本 change 内一并修**，且明确要求「**一把修好了，因为我印象中很多地方都有用到这个路径检测**」——据此主 session 做了全仓路径包含判定扫描，确认同类缺陷**只在 `command_guard.py`**（5 处），其余位置或已用 `pathlib.relative_to`/`commonpath`（段级正确）、或输入本身已规范化（`workflow_guard._norm_path` 已解析 `..`，是本仓库内正确参照）；扫描结论与参照实现已写入 design 的 D6 节；确认时间: 2026-09-26

## 风险

- **R1（必须修改，最高优先级）· D4 正则形态会同时引入新误报与新漏网**: design 字面形态 `\.(git|ssh|...)` 实测 `cp x .gitignore`→命中（误报）、`cp x src/.git/hooks/pre-commit`→不命中（漏网）、`cp x sub/.env/secrets`→不命中（漏网）、`cp x proj/.npmrc`→不命中（漏网）。即「修误报」的动作反而在 `.gitignore` 这类日常命令上新增误报，并放开嵌套敏感目录的写入。**且 50/54 攻击集没有嵌套点目录用例，验收口径「拦截数不下降」测不出这个回归**——必须把嵌套/裸两族都补进回归用例（tasks 2.3/2.5 目前只覆盖裸形态与普通点目录）。
- **R2（必须修改）· D5 选定的 `/var/log/foo` 自证不成立**: D5 让 `:122`/`:176` 改用 `/var/log/foo` 以验证 `mv_cp_dest` reason。实测 `mv /tmp/x /var/log/foo` → DENY 但 `last_reason == "denylist"`（被 `_EXTRA_DENYLIST` 的 `mv/cp ... /var/` 字面量抢先），reason 断言必失败。D5 把这个列为「待 grill 确认的 Q」，实为已证伪——应改用 `_DENY_PATHS` 中**未被 denylist 覆盖**的前缀：`mv /tmp/x /root/foo` 或 `/boot/foo`（实测 reason=`mv_cp_dest`）。`:164` 用 `/var/log/foo` 可行（实测 reason=`protected_redirect`）。
- **R3（必须修改）· spec delta 与 design/tasks 的设备豁免范围矛盾**: spec delta 第 9 行的豁免范围（含 rm/chmod/curl）大于 design D2 与 tasks 3.3–3.7 的实现范围（仅 redirect + mv/cp）。实测差异造成可观测判定分歧（见 Q2）。二者必须统一，否则实现完成后 spec 与代码事实不符，且 review/checker 会面对「spec 说 SHALL 放行、代码 DENY」的硬冲突。
- **R4 · 「良性命令电池 26 条 / 误报 17→0」不可机械复现**: 该电池未落库（repo 内无该 fixture，proposal/design/diagnosis 均只有表格摘录）。我已独立复现**攻击集侧**的 50/54 与「5 条 /dev 用例 reason 全为 denylist」，故诊断核心证据可信、仿真非伪造；但「17/26」这一组数字缺乏可复算基线，属不可验证断言。建议把 26 条全集固化为测试数据（tasks 2.1–2.3 已列部分，补齐即可），否则 4.4「复算对齐 design 预测数字」无参照物。
- **R5 · 受保护路径的 workflow 事件任务缺失**: tasks 1.5（同步 `openspec/specs/workspace-safety/spec.md`）需 `current_spec_synced` 事件、7.1（归档到 `openspec/changes/archive/**`）需 `change_archived` 事件（`scripts/flow-policy.json` 中两者 governance=`event_explained`）。tasks.md 只在 5.2（known-issues/debt → `protected_artifact_explained`）、5.3（backlog → `backlog_updated`）列了事件产出任务，**1.5 与 7.1 缺对应 event 任务**，实施时极易漏写导致受保护写被拦。
- **R6 · 误报族收窄后的残余漏网面（应记录为已知残余）**: 段边界 + 设备豁免只修正「假朋友前缀」，不改变下列既有行为：`cp x sub/.env/f`（旧模式能拦，D4 收窄后按字面形态会漏——见 R1）；`cp ~/.ssh/id_rsa /tmp/x`（source 侧 `.ssh` 不在 `DEFAULT_DENYLIST` 的 `\bcp\s+(...\.env\b|\.git/)` 覆盖内）本来就漏。建议在 `docs/known-debt.md` 的「护栏不是边界」口径下明确列出这些残余面，避免修复后产生「点目录已收紧即安全」的错觉。
- **R7 · 文档影响面被低估**: `docs/interview-script/questions/Q10-sandbox.md`、`docs/interview-script/walkthrough/W06-security.md`、`docs/interview-bullets/interview-prep.md`（「18 个扩展模式」口径）、`docs/interview-script/FINAL-master-script.md`、`docs/interview-bullets/walkthrough.md` 均描述了命令护栏的既有判定口径（如「重定向到受保护路径」「mv 覆盖 workspace 外文件」）。D4 收窄与段边界/设备豁免会改变这些说法的事实口径。tasks 5.1 只写「关键词扫描 docs/」，未点名 `docs/interview-script/**`；AGENTS.md 「建议性维护约束」要求检查该目录。建议 5.1 显式纳入。
