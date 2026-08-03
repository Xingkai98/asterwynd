# Tasks: 长期记忆可逆写入（git commit-before-write + resolve_conflict）

## 1. 可逆写入基建

- [x] 1.1 `_ensure_git()` 懒初始化：首次破坏性写实际落盘前 `git init` memory_dir（幂等，已 init 跳过）；`__init__` 无副作用
- [x] 1.2 `_git_commit(action, name, reason)` helper：`git -c user.name="Asterwynd Memory" -c user.email="memory@asterwynd.local" commit`（内联 identity）；`git add -A -- <memory_dir>/` 全目录快照；区分 nothing-to-commit 与 git 真坏（abort 写保护）
- [x] 1.3 `save()` 覆盖分支（existing is not None）写入前 commit
- [x] 1.4 `apply_judgment()` supplement / update / conflict 分支写入前 commit（conflict 打标后**不**立即 commit，交给下一次破坏性写兜底）

## 2. resolve_conflict

- [x] 2.1 `PersistentMemory.resolve_conflict(name_a, name_b, loser=None, archive=False, reason="")`：清除双方 conflict_with + changelog resolve 事件 + 可选归档 loser（默认 name_b）
- [x] 2.2 `agent/tools/builtin/memory.py` 暴露 `ResolveMemoryConflict` 工具（PascalCase，AGENT_STATE_PERMISSION）

## 3. MemoryGitBackend（可选工具）

- [x] 3.1 `agent/memory/git_backend.py`：单工具 + action 参数（history/diff/revert），PascalCase 命名
- [x] 3.2 `agent/config.py` MemoryGitBackend 开关；`agent/tools/factory.py` 注册
- [x] 3.3 revert 两步 commit：先 commit 当前态 → checkout 回退正文 → 重建索引行 + changelog revert 事件 → 再 commit revert 产物（历史即时可见）

## 4. 回归测试

- [x] 4.1 update/supplement 前旧 body 有 pre-image 可恢复
- [x] 4.2 误判后可还原旧内容（revert 两步 commit：当前态先落盘 + revert 产物立即 commit，`git log -- <name>.md` 可见 v1→v2→v1）
- [x] 4.3 resolve 后 conflict_with 清空、changelog 有 resolve 事件
- [x] 4.4 git 不可用 / commit 失败 → abort 写保护（旧内容保留）
- [x] 4.5 fresh repo 首次写安全继续（nothing to commit 非失败）
- [x] 4.6 load_entries 不受 git init 影响
- [x] 4.7 revert 后 MEMORY.md 索引行与正文 description 一致（索引跟随）
- [x] 4.8 commit 用内联 -c identity，CI 无全局配置也可提交
- [x] 4.9 resolve_memory_conflict 工具注册 + 调用；MemoryGitBackend history/diff/revert 调用

## 5. 验证

- [x] 5.1 benchmark smoke：`uv run asterwynd run "用 Read 工具读 /tmp"` 冒烟验证 AgentLoop + 工具调用不因记忆可逆性改动回归（coding-agent 核心变更）
- [x] 5.2 全量 pytest 无新增失败

## 6. 收尾

- [ ] 6.1 当前规格同步：specs delta 合入 `openspec/specs/long-term-memory/spec.md`（受保护，需 workflow-events）
- [ ] 6.2 文档影响：AGENTS.md / 文档地图关键词扫描；ADR-0002 已同步
- [ ] 6.3 known-debt 登记并发丢更新债务（受保护，需 workflow-events）
- [ ] 6.4 归档 + 更新 backlog + artifact checker + openspec validate（archive/backlog 受保护，需 workflow-events）

## 审阅修复记录

### Round 1（CHANGES_REQUESTED，2026-08-03）

- [x] 1. [中] resolve_conflict 实现"默认 loser=name_b"（`archive=True` 未传 loser 时归档 name_b）
- [x] 2. [低] MemoryGitBackend history/diff/revert 入口加 `_validate_name` 校验
- [x] 3. [低] 补 `git_backend_enabled=False` 的 factory 开关回归测试
- [x] 4. [低] resolve_conflict 校验 `name_a != name_b`（同名自解防护）
- [x] 5. [低] 统一 resolve commit message 与 changelog 分隔符（均带空格）

### Round 2（CHANGES_REQUESTED，2026-08-03）

- [x] 6. [中/安全] resolve_conflict 校验 `loser`：`_validate_name` + 必须为 None/name_a/name_b（防路径穿越任意写/删 `.md`）；工具 schema 同步；补路径穿越回归测试
