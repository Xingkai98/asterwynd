## 1. 回归测试

- [x] 1.1 新增 denylist 覆盖 allowlist 的 WorkspacePolicy 测试。
- [x] 1.2 新增 `python -c` / `python3 -c` 被拒绝的测试。
- [x] 1.3 新增 `python -m pytest` / `uv run pytest` 仍允许的测试。
- [x] 1.4 新增 `cp /etc/passwd`、`mv .env ...` 被拒绝的测试。
- [x] 1.5 新增 BashTool policy 拒绝时返回错误文本的测试。

## 2. 实现

- [x] 2.1 调整 `assert_command_allowed()` 为 denylist 优先。
- [x] 2.2 收窄 `_match_allowlist()` 中的 Python、cp、mv 等宽泛前缀。
- [x] 2.3 增加必要 denylist 模式覆盖已知绕过。
- [x] 2.4 保持常规测试、git diff、搜索和查看命令可用。

## 3. 验证

- [x] 3.1 运行 WorkspacePolicy 和 BashTool 相关测试。
- [x] 3.2 运行全量测试。
- [x] 3.3 跑通至少一个 benchmark smoke。
- [x] 3.4 归档 change 并更新当前 specs。
