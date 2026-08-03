# Diagnosis: 长期记忆写时去重误判导致内容永久丢失，无恢复手段

## Symptom

- LLM 去重判断误判（supplement / update / conflict）后，旧记忆内容被覆盖/污染，无法还原。
- 用户无法区分"这条记忆以前长什么样"，changelog 只有 action 级审计，无内容级恢复。
- conflict_with 标记越积越多，无解除途径。

## Reproduction

1. `apply_judgment(action="update", target="X")`：X 的 body 被整体替换为 incoming，旧 body 消失。
2. `apply_judgment(action="supplement", target="X")`：一条独立新记忆被并进 X 的 body（`旧body \n\n 新body`），X 被污染且无法撤销。
3. `apply_judgment(action="conflict", target="X")`：X 与 incoming 互相打 `conflict_with` 标记，无 API 可解除。
4. `save()` 同名覆盖：旧 body 无 pre-image。
5. memory 目录位于 `~/.asterwynd/projects/<hash>/memory/`，在项目 git 仓库之外，无 VCS 兜底。

## Evidence

- `agent/memory/persistent.py:500-511` update 分支：`entry.body = body.strip()` 整体替换，无 pre-image。
- `agent/memory/persistent.py:488-498` supplement 分支：`entry.body = f"{entry.body}\n\n{body.strip()}"` 追加合并，无法撤销。
- `agent/memory/persistent.py:513-525` conflict 分支：双方 `conflict_with` 只增不减，无消费点。
- `agent/memory/persistent.py:421-463` save() 覆盖分支：`existing.body = body.strip()` 直接覆盖。
- `agent/memory/persistent.py:692-702` changelog 只记 `- [时间] <action> <name> → <reason>`（action 级，无内容）。
- `~/.asterwynd/` 无 `.git`，且不在项目仓库内。

## Root Cause

#75 设计的写时去重三分支由 LLM 判断，其"可人工复核、change log 可回溯"承诺（design Risk 表）停留在 action 级审计，未落地内容级可恢复。写路径全部是破坏性覆盖/追加，无任何 pre-image 或版本机制；`memory_dir` 又在 VCS 之外，导致误判即永久丢失。`conflict_with` 标记设计为"检索 ranker 决定当前事实"，但实际无 ranker 消费它，标记只增不减。

## Recommended Direction

采用 git 管理可逆写入（ADR-0002）：

1. `memory_dir` 幂等 `git init`，破坏性写（save 覆盖 / supplement / update / conflict）前 commit-before-write，旧状态先落盘。
2. commit message 对齐 changelog：`<action> <name> → <reason>`，`git log -- <name>.md` 即内容级审计。
3. 新增 `resolve_conflict` API + 工具，清除双方 conflict_with 标记 + changelog resolve 事件。
4. 可选 MemoryGitBackend（history / diff / revert）暴露给 agent。
5. git 不可用时优雅降级（warning + 仍写入），不阻塞记忆功能。

## Regression Tests

- update/supplement 前旧 body 有 pre-image（git 历史）可恢复。
- 误判后可还原旧内容（revert）。
- resolve 后 conflict_with 清空、changelog 有 resolve 事件。
- git 不可用降级路径（仍写入 + warning）。
- load_entries 不受 git init 影响。
- resolve_memory_conflict 工具注册 + 调用。
