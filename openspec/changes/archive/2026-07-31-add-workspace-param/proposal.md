# Proposal: CLI/Web 增加 --workspace 参数与 Session 多 Workspace 支持

## Change Type

primary: feature
secondary:
  - cli
  - web
  - security

## 需求

1. `asterwynd --workspace /path run/web` 指定主工作目录启动
2. Session 中通过 `/session-workspace add/remove/list` 动态增删附加 workspace
3. 主 workspace 保护不可删除
4. 附加 workspace 只扩展读写边界，不参与 session/config/ASTER.md 管理

## 边界

| 项 | 决策 |
|----|------|
| --workspace 格式 | 绝对路径，支持 `~` |
| 路径不存在 | 报错退出 |
| 附加路径不存在 | 自动创建，权限不够返回友好提示 |
| 安全防护 | add 时 realpath 解析 + 拒绝系统敏感目录 + 拒绝祖先目录 |
| 多 workspace 存储 | 内存（Session 重启丢失，MVP 可接受） |

## 非目标

- ASTER.md 多文件读取（始终只读主 workspace 的 ASTER.md）
- 跨 session 持久化 workspace 列表
- workspace 权限细粒度控制（读写/只读分开）

## Impact Analysis

| 影响面 | 说明 |
|---------|------|
| CLI 入口 | `agent/main.py` callback + web 子命令 |
| Web 传递链 | `web/server.py` → `web/session.py` |
| WorkspacePolicy | `agent/workspace_policy.py` 扩展 additional_roots |
| 工具执行 | 所有工具通过 WorkspacePolicy 路由 |
| Session | Session 不存储 workspace（内存） |

## Reference Implementation Research
status: disabled
reason: CLI --workspace/--cwd 是常见模式，不需要参考实现调研。安全防护方案基于常见沙箱实践。
