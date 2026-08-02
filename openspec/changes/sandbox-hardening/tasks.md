# Tasks: 安全沙箱做深

> **批次范围**：第一批 = 第 1-4 节（ExecutionBackend 抽象 + ProcessBackend/DockerBackend + 命令护栏 + 攻击回归集 + 彻底迁移）；cgroup v2 为后续批（Docker 自带 --memory 资源限制）。

## 1. 命令护栏（command_guard.py）

- [x] 1.1 轻量命令分词器（识别命令名/参数/重定向/管道/子 shell/引号/通配符）
- [x] 1.2 argv 语义校验：`rm` 目标越界、`cp/mv` 目标敏感、`chmod` 权限位、`timeout` 范围、路径落 workspace
- [x] 1.3 denylist 增强覆盖绕过面：`rm -fr`/`rm -r -f`/`rm -rf --`、`chmod 0777`/`chmod a+rwx`、`kill -SIGKILL`/`kill -KILL`、`node -e`/`deno eval`/`awk system()`、`base64 -d | bash`、`mv` 目标越界
- [x] 1.4 `assert_command_allowed` 接入 command_guard（契约不变，逻辑升级）
- [x] 1.5 单元测试：分词、argv 校验、denylist 增强、绕过面回归

## 2. ExecutionBackend 抽象 + 后端（sandbox/ 包）

- [x] 2.1 `sandbox/` 包重构：`base.py`（ExecutionBackend Protocol + SandboxResult + BackgroundProcessHandle 从 sandbox.py 迁移）
- [x] 2.2 `process_backend.py`：ProcessBackend（现有 subprocess 实现重构）
- [x] 2.3 `docker_backend.py`：DockerBackend（`docker run --rm --network none --memory 512m --cpus 2 -v <ws>:/workspace -w /workspace <image> sh -c "<cmd>"`）
- [x] 2.4 `factory.py`：`build_execution_backend(name)` → ProcessBackend/DockerBackend
- [x] 2.5 后端契约测试（统一跑 run/run_background/is_available；DockerBackend 真实 Docker 验证，`sg docker` 访问）
- [x] 2.6 **彻底迁移**：删除 `SandboxExecutor`，调用方（main.py/background.py/bash.py/__init__.py）改用 factory

## 3. 攻击回归集（数据驱动）

- [x] 3.1 构建 50+ 恶意命令攻击回归集（8 类：文件破坏/敏感读取/提权/任意代码执行/外传/资源耗尽/绕过变体/git 破坏），JSON case 清单
- [x] 3.2 测试读取清单 → 走命令护栏 + 后端 → 断言全部拦截
- [x] 3.3 接入 benchmark（复用 PR #80 runner）

## 4. config + 收尾

- [x] 4.1 config 新增 sandbox 配置段（backend 切换/镜像/资源上限）
- [x] 4.2 OpenSpec spec 同步
- [x] 4.3 全量 pytest + openspec validate + artifact checker
- [x] 4.4 benchmark 量化（阻断率、Docker 隔离验证）

## 5. cgroup v2 资源限制（后续批）

- [ ] 5.1 `max_memory_mb` 生效：cgroup v2 限制 CPU/内存（本地 ProcessBackend）
- [ ] 5.2 超限自动 kill + 记录
- [ ] 5.3 低资源环境降级（无 cgroup 时退化为超时/警告）
- [ ] 5.4 单元测试：cgroup 限制逻辑（mock）

## 6. 沙箱事件入 trace（后续批，与 #78 协调）

- [ ] 6.1 结构化 sandbox 事件（denied/reason/kill/oom）入 trace_recorder
- [ ] 6.2 与 #78 事件 schema 对齐

## 7. 收尾校验（checker 要求项）

- [ ] 7.1 pre-implementation batch-grill-me 或等价设计审阅任务（进入 building 前）
- [ ] 7.2 benchmark smoke verification（coding-agent core change 要求）
- [ ] 7.3 当前规格同步：把 spec delta 合并到 `openspec/specs/<capability>/spec.md`
