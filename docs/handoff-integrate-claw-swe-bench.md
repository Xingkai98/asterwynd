# Handoff: Claw-SWE-Bench 集成与多 Agent 对比

**日期**: 2026-06-26  
**分支**: `integrate-claw-swe-bench` (已推送到 `origin`)  
**当前状态**: MyAgent 50-instance benchmark 运行中

---

## 做了什么

在 Claw-SWE-Bench 统一框架下集成了 MyAgent、Aider、OpenCode 三个 coding agent，实现同模型 (DeepSeek V4 Pro)、同环境、同 prompt 的可控对比。

### 完成的工作

1. **MyAgent adapter 修复** (`claw-swe-bench/claw_swebench/claws/myagent.py`)
   - 添加 `docker exec -i` 传 stdin
   - 挂载 standalone Python 3.12 到容器
   - 修正 `claw_solve.py` 路径 (`/opt/myagent/agent/claw_solve.py`)
   - 修正 AnthropicLLM 导入路径

2. **agent/claw_solve.py 修复**
   - `AnthropicLLM` 从 `agent.anthropic_llm` 导入
   - `build_messages()` 添加 `workspace` 参数

3. **Aider adapter** (`claw-swe-bench/claw_swebench/claws/aider.py`)
   - Headless 模式: `aider --yes --no-auto-commits --message-file`
   - 通过 standalone Python + PYTHONPATH 运行（绕过 venv symlink 问题）
   - 单实例验证通过 (327s, patch 正确)

4. **OpenCode adapter** (`claw-swe-bench/claw_swebench/claws/opencode_adapter.py`)
   - headless 模式: `opencode run --format json --dangerously-skip-permissions`
   - **暂不可用**: OpenCode 不支持自定义 API endpoint，无法接入 DeepSeek V4 Pro

5. **workspace.py 修改** — 支持 `CLAW_NO_RESOURCE_LIMITS=1` 绕过 cgroup 限制

6. **镜像拉取**
   - 从轩辕镜像 (`docker.xuanyuan.run`) 拉取全部 50 个 SWE-bench Verified-Mini 镜像
   - 使用 `pull_images.py` 批量拉取 + re-tag
   - 登录凭据: 见环境变量

### 关键环境变量

```bash
export CLAW_NO_RESOURCE_LIMITS=1
export CLAW_PYTHON_HOME=/home/happy/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu
export MYAGENT_SRC=/home/shared/agent-study/my-agent
export MYAGENT_VENV=/home/shared/agent-study/my-agent/.venv
export AIDER_VENV=/home/shared/agent-study/aider-venv
export OPECODE_HOST_BIN=/home/happy/.npm-global/bin/opencode
export HF_HUB_OFFLINE=1
export ANTHROPIC_API_KEY=<sk-...>
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export OPENAI_API_KEY=<sk-...>  # for Aider
export OPENAI_API_BASE=https://api.deepseek.com/v1  # for Aider
```

---

## 当前运行状态

MyAgent 50-instance benchmark 运行中:
- 日志: `/tmp/myagent-50.log`
- 命令: `cd /home/shared/agent-study/my-agent/claw-swe-bench && sg docker -c "env ... uv run python run_infer.py --claw myagent --dataset verified --instance_file config/verified_mini_50.txt --run_id myagent-50 --model deepseek-v4-pro --timeout 600 --workers 2"`
- 启动时间: 2026-06-26 15:43 CST
- 预计耗时: 3-5 小时
- 镜像: 全部 50 个已 tag 为 `sweb.eval.x86_64.<instance_id>:latest`

### 待执行

Aider 50-instance (MyAgent 完成后):
```bash
cd /home/shared/agent-study/my-agent/claw-swe-bench && sg docker -c "env \
  HF_HUB_OFFLINE=1 CLAW_NO_RESOURCE_LIMITS=1 \
  CLAW_PYTHON_HOME=... AIDER_VENV=... \
  OPENAI_API_KEY=... OPENAI_API_BASE=... \
  uv run python run_infer.py \
    --claw aider --dataset verified \
    --instance_file config/verified_mini_50.txt \
    --run_id aider-50 --model deepseek-v4-pro --timeout 600 --workers 2"
```

---

## 环境注意事项

- **Docker**: VFS 存储驱动（不支持 overlay2），容器启动慢但可用
- **网络**: Docker Hub 不可达（用轩辕镜像替代），GitHub HTTPS 不稳定但 SSH 可用，DeepSeek API 正常
- **Git push**: 已切换 remote 到 SSH (`git@github.com:Xingkai98/my-agent.git`)
- **HuggingFace**: 不可达，用缓存 + `HF_HUB_OFFLINE=1`
- **内存**: 7.6GB，跑 Docker 容器时注意并发数

---

## 文件清单

```
claw-swe-bench/
├── build_single.py              # 单镜像手动构建（绕过 Docker build OOM）
├── build_all_images.py          # 批量构建脚本（未完全验证）
├── pull_images.py               # 轩辕镜像批量拉取
├── claw_swebench/claws/
│   ├── myagent.py               # MyAgent adapter ✅
│   ├── aider.py                 # Aider adapter ✅
│   ├── opencode_adapter.py      # OpenCode adapter ❌ (DeepSeek 不支持)
│   ├── __init__.py              # 已注册全部三个
├── config.py                    # 已添加 aider/opencode defaults
├── workspace.py                 # 支持 CLAW_NO_RESOURCE_LIMITS
└── artifacts/                   # 单实例测试结果

agent/claw_solve.py              # 修复了导入和参数
```

---

## Suggested Skills

- **review**: MyAgent 跑完后 review 结果
- **qa**: 如果 benchmark 有问题需要排查
- **handoff**: 继续下一阶段时 handoff
