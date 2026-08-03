# Tasks: 长期记忆可逆写入（git commit-before-write + resolve_conflict）

## 1. 可逆写入基建

- [ ] 1.1 `_ensure_git()` 懒初始化：首次破坏性写实际落盘前 `git init` memory_dir（幂等，已 init 跳过）；`__init__` 无副作用
- [ ] 1.2 `_git_commit(action, name, reason)` helper：`git -c user.name="Asterwynd Memory" -c user.email="memory@asterwynd.local" commit`（内联 identity）；`git add -A -- <memory_dir>/` 全目录快照；区分 nothing-to-commit 与 git 真坏（abort 写保护）
- [ ] 1.3 `save()` 覆盖分支（existing is not None）写入前 commit
- [ ] 1.4 `apply_judgment()` supplement / update / conflict 分支写入前 commit（conflict 打标后**不**立即 commit，交给下一次破坏性写兜底）

## 2. resolve_conflict

- [ ] 2.1 `PersistentMemory.resolve_conflict(name_a, name_b, loser=None, archive=False, reason="")`：清除双方 conflict_with + changelog resolve 事件 + 可选归档 loser（默认 name_b）
- [ ] 2.2 `agent/tools/builtin/memory.py` 暴露 `ResolveMemoryConflict` 工具（PascalCase，AGENT_STATE_PERMISSION）

## 3. MemoryGitBackend（可选工具）

- [ ] 3.1 `agent/memory/git_backend.py`：单工具 + action 参数（history/diff/revert），PascalCase 命名
- [ ] 3.2 `agent/config.py` MemoryGitBackend 开关；`agent/tools/factory.py` 注册
- [ ] 3.3 revert 两步 commit：先 commit 当前态 → checkout 回退正文 → 重建索引行 + changelog revert 事件 → 再 commit revert 产物（历史即时可见）

## 4. 回归测试

- [ ] 4.1 update/supplement 前旧 body 有 pre-image 可恢复
- [ ] 4.2 误判后可还原旧内容（revert 两步 commit：当前态先落盘 + revert 产物立即 commit，`git log -- <name>.md` 可见 v1→v2→v1）
- [ ] 4.3 resolve 后 conflict_with 清空、changelog 有 resolve 事件
- [ ] 4.4 git 不可用 / commit 失败 → abort 写保护（旧内容保留）
- [ ] 4.5 fresh repo 首次写安全继续（nothing to commit 非失败）
- [ ] 4.6 load_entries 不受 git init 影响
- [ ] 4.7 revert 后 MEMORY.md 索引行与正文 description 一致（索引跟随）
- [ ] 4.8 commit 用内联 -c identity，CI 无全局配置也可提交
- [ ] 4.9 resolve_memory_conflict 工具注册 + 调用；MemoryGitBackend history/diff/revert 调用

## 5. 验证

- [ ] 5.1 benchmark smoke：`uv run asterwynd run "用 Read 工具读 /tmp"` 冒烟验证 AgentLoop + 工具调用不因记忆可逆性改动回归（coding-agent 核心变更）
- [ ] 5.2 全量 pytest 无新增失败

## 6. 收尾

- [ ] 6.1 当前规格同步：specs delta 合入 `openspec/specs/long-term-memory/spec.md`（受保护，需 workflow-events）
- [ ] 6.2 文档影响：AGENTS.md / 文档地图关键词扫描；ADR-0002 已同步
- [ ] 6.3 known-debt 登记并发丢更新债务（受保护，需 workflow-events）
- [ ] 6.4 归档 + 更新 backlog + artifact checker + openspec validate（archive/backlog 受保护，需 workflow-events）
