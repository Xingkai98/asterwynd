# Proposal: 长期记忆可逆写入 — commit-before-write 快照 + resolve_conflict 解除

## Change Type

primary: bugfix
secondary:
  - memory
  - tools

## 需求

1. **可逆写入**：update / supplement / save 覆盖前，旧 body 先落盘为可恢复快照，误判后能还原旧内容。
2. **冲突解除**：矛盾双方 `conflict_with` 标记可主动解除（resolve），changelog 记录 resolve 事件。
3. **内容级审计**：changelog 从 action 级审计（`- [时间] update <name> → reason`）提升到内容级可恢复（旧内容可从 git 历史还原）。

## 背景

#75 长期记忆做深的写时去重三分支（supplement / update / conflict）由 LLM 判断，**误判时内容永久丢失**：

- `apply_judgment()` update 分支整体替换旧 body，无 pre-image（`agent/memory/persistent.py:500-511`）。
- supplement 分支把独立新记忆并进无关旧记忆，污染后无法撤销（`persistent.py:488-498`）。
- conflict_with 标记只增不减，无解除/清除 API、无消费点（`persistent.py:513-525`）。
- `memory_dir` 位于 `~/.asterwynd/projects/<hash>/memory/`，**在项目 git 仓库之外、无 VCS 兜底**。

源自 #75 batch grill 决策树（Round 2）Decision 2 / R1-Q4，用户确认作为 follow-up 新 change 立项。本 change 采用 **git 管理可逆写入**（ADR-0002），并修正 #75 归档 design"判断结果可人工复核、change log 可回溯"从 action 级提升到内容级的过度承诺。

## 非目标

- 不做 mem0 V3 式 ADD-only + 读时多信号 ranker（ADR-0002 拒绝，需重写 read 路径，留待未来引入多信号 ranker 时重估）。
- 不重做写时去重语义本身（LLM 三分支保留，本次只加可逆性对冲）。
- 不把 `~/.asterwynd/` 纳入项目 git 仓库（它独立 git init，在用户主目录）。

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| `agent/memory/persistent.py` | commit-before-write（save/apply_judgment 破坏性写前 git commit）+ resolve_conflict API |
| `agent/tools/builtin/memory.py` | resolve_conflict 工具；可选 MemoryGitBackend（history/diff/revert）工具 |
| `agent/memory/dedup.py` | 无改动（LLM 三分支语义保留） |
| `~/.asterwynd/projects/<hash>/memory/` | 首次写前 git init，`.git` 目录出现于用户主目录 |
| `agent/config.py` | 可选：记忆可逆性开关 / MemoryGitBackend 工具开关 |
| `docs/adr/ADR-0002` | 新增可逆记忆方案对比 ADR |
| 测试 | 回归测试：update/supplement 前有 pre-image、误判后可还原、resolve 后 conflict_with 清空、revisions 不污染 load_entries |

## Reference Implementation Research

- status: enabled
- reason: 记忆可逆性（pre-image / git 版本化 / 冲突解除）是记忆系统核心能力，参考 mem0 / Letta / Zep 的实现取舍。
- research questions:
  - mem0 为什么从写时 reconciliation 转向 ADD-only？其 dedup 与读时 ranker 如何取舍？
  - Letta 如何用 git（Context Repositories）做记忆版本化与并发协作？
  - Zep/Graphiti 如何用 valid_from/valid_to 做"失效而非删除"的历史保留？
  - 写时留底（pre-image）与"从不覆盖"（ADD-only）对误判的抵抗力差异？
- findings:
  - mem0 V3 删除写时 LLM diff，改 single-pass ADD-only + MD5 精确去重，读时用语义+BM25+实体+时间多信号排序挑当前事实——因"写时判错会静默污染"。
  - Letta memory block 写时增量 version + block_edit_log；Letta Code 用 Context Repositories（git 管理记忆）自动版本化 + 子 agent 并发协作走标准 git。
  - Zep/Graphiti 用 temporal edge invalidation（旧边打 invalid_at、新建边）保留历史，支持点查。
  - 结论：Asterwynd 当前无多信号 ranker，直接 ADD-only 会让矛盾记忆无序浮出；git 管理是"保留写时去重 + 补可逆性"的最小成本路径。
- design impact:
  - 采用 git 管理可逆写入（ADR-0002 Decision）；conflict_with 解除仍需 resolve_conflict API（git 只管内容恢复，不管标记累积）。

## Dependencies

- 依赖 #75 long-term-memory-deepening（已合入）：`PersistentMemory`、`apply_judgment()`、changelog、conflict_with 标记。
- 复用 #79 multi-agent-collaboration（已合入）：git 管理记忆可与子 agent 并发写衔接。

## 验收

- update/supplement 前旧 body 有 pre-image 可恢复（回归测试覆盖）。
- 误判后可还原旧内容（`git checkout <commit> -- <name>.md` 或 MemoryGitBackend.revert）。
- resolve 后 conflict_with 清空、changelog 有 resolve 事件。
- git 历史与 changelog 行对齐：`git log -- <name>.md` 的 commit message 与 changelog `- [时间] <action> <name> → <reason>` 对应。
- spec delta 新增"可逆写入"与"冲突解除"两个 requirement。
