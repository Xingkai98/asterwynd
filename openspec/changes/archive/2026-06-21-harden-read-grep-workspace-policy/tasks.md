## 1. 回归测试

- [x] 1.1 新增 ReadTool 拒绝 workspace 外路径的回归测试。
- [x] 1.2 新增 ReadTool 拒绝 `.env` 或其他 denied pattern 路径的回归测试。
- [x] 1.3 新增 GrepTool 拒绝 workspace 外搜索起点的回归测试。
- [x] 1.4 新增 GrepTool 递归搜索跳过 denied paths 的回归测试。
- [x] 1.5 更新 WorkspacePolicy 对 read denied patterns 和路径逃逸的测试。

## 2. 实现

- [x] 2.1 为 ReadTool 增加可选 WorkspacePolicy 注入。
- [x] 2.2 为 GrepTool 增加可选 WorkspacePolicy 注入。
- [x] 2.3 调整 WorkspacePolicy 的 agent-facing read 校验，使其执行 denied patterns。
- [x] 2.4 确保 default tools 和 coding tools 向 ReadTool、GrepTool 注入共享 workspace policy。
- [x] 2.5 确认裸构造 ReadTool/GrepTool 时默认 policy root 为当前进程工作目录。

## 3. 验证

- [x] 3.1 运行相关 tool 和 workspace policy 测试。
- [x] 3.2 运行 benchmark runner 测试，确认隐藏任务文件处理仍然正常。
- [x] 3.3 运行 OpenSpec strict validation。
- [x] 3.4 归档 change 时更新受影响的当前 specs。
