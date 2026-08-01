# Tasks: 安全沙箱做深

## 1. bash AST 句型校验

- [ ] 1.1 引入 shell AST parser，解析命令为 AST
- [ ] 1.2 定义预定义句型白名单（git status/diff、pytest -k、cat/head/tail/ls 等）
- [ ] 1.3 参数类型+范围约束（timeout int [1,600]、路径落在 workspace、禁止通配符/重定向/管道组合）
- [ ] 1.4 `assert_command_allowed` 契约不变，校验逻辑升级
- [ ] 1.5 单元测试：AST 句型、参数约束、绕过面覆盖

## 2. cgroup v2 资源限制

- [ ] 2.1 `max_memory_mb` 生效：cgroup v2 限制 CPU/内存
- [ ] 2.2 超限自动 kill + 记录
- [ ] 2.3 低资源环境降级（无 cgroup 时退化为超时/警告）
- [ ] 2.4 单元测试：cgroup 限制逻辑（mock）

## 3. 攻击测试集

- [ ] 3.1 构建 50+ 恶意 prompt 攻击回归集（fork bomb、curl|sh、python -c、rm -rf /、dd if=、chmod 777、exfil、无限内存、/etc/passwd、git reset --hard 等）
- [ ] 3.2 端到端断言全部拦截（prompt → tool-call → sandbox 拒绝）
- [ ] 3.3 接入 benchmark runner（复用 PR #80）

## 4. 沙箱事件入 trace

- [ ] 4.1 结构化 sandbox 事件（denied/reason/kill/oom）入 trace_recorder
- [ ] 4.2 与 #78 事件 schema 对齐

## 5. 配置与收尾

- [ ] 5.1 config 新增 sandbox 配置段（AST 开关/资源上限/攻击集路径/后端切换）
- [ ] 5.2 OpenSpec spec 同步
- [ ] 5.3 全量 pytest + openspec validate + artifact checker
- [ ] 5.4 benchmark 量化（阻断率 100%、OOM kill 事件入 trace）

## 8. 收尾校验（checker 要求项）

- [ ] 8.1 pre-implementation grill-with-docs 或等价设计审阅任务（进入 building 前）
- [ ] 8.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 8.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
