# Handoff: Claw-SWE-Bench 多 Agent 评测 — WSL 迁移指南

**日期**: 2026-06-27  
**分支**: `integrate-claw-swe-bench` (已推送)  
**目标**: 在个人笔记本 WSL 上完成 MyAgent vs Aider 的 SWE-bench Verified-Mini (50实例) 评测

---

## 当前进度

| 阶段 | 状态 | 详情 |
|------|------|------|
| MyAgent adapter 开发 | ✅ | `claw-swe-bench/claw_swebench/claws/myagent.py` |
| Aider adapter 开发 | ✅ | `claw-swe-bench/claw_swebench/claws/aider.py` |
| OpenCode adapter | ❌ | 不支持自定义 API endpoint |
| MyAgent 50实例推理 | ✅ | 50/50 patch_collected，avg 9.6min，零失败 |
| Aider 50实例推理 | ✅ | 50/50 patch_collected，avg 47s (Host模式)，零失败 |
| 评测 (resolve rate) | ❌ | Docker VFS 导致超时，待在有 overlay2 的环境重跑 |

## Patch 数据位置

```
claw-swe-bench/artifacts/
├── myagent-50/
│   ├── predictions.jsonl          # 50 patches, MyAgent
│   └── <instance_id>/
│       ├── git.patch              # 每个实例的 patch
│       ├── agent_stdout.log
│       └── agent_stderr.log
└── aider-host-50/
    ├── predictions.jsonl          # 50 patches, Aider (Host模式)
    └── <instance_id>/
        ├── git.patch
        ├── agent_stdout.log
        └── agent_stderr.log
```

patch 数据可以带到任何环境直接评测，不需要重新跑推理。

## WSL 上跑的步骤

### 0. 前置条件

```bash
# WSL2 Ubuntu 22.04+
# Docker (overlay2 驱动) + docker 组权限
# Python 3.12 + uv
# SSH key 配置到 GitHub

git clone git@github.com:Xingkai98/my-agent.git
cd my-agent
git checkout integrate-claw-swe-bench
```

### 1. 安装依赖

```bash
uv sync --extra dev
uv pip install datasets pyyaml swebench docker

# Aider (用于跑 Aider 推理，评测不需要)
pip install aider-chat
```

### 2. 拉取 Docker 镜像（二选一）

**方案A: 轩辕国内镜像**（快）
```bash
# 需要先注册 xuanyuan.cloud 账号
docker login docker.xuanyuan.run -u <手机号> -p <密码>
uv run python claw-swe-bench/pull_images.py
```

**方案B: 官方自动构建**（需要 Docker Hub 和 GitHub 能访问）
```bash
# swebench 会为每个 instance 自动构建镜像
# 评测时会自动触发，不需要手动操作
```

方案A更快（直接拉 2-3GB 镜像），方案B更标准。

### 3. 评测 — 关键命令

**不推荐用 `run_eval.py`**（它创建容器时 Docker timeout 太短）。

直接用官方 harness：

```bash
cd claw-swe-bench

# MyAgent 评测
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path artifacts/myagent-50/predictions.jsonl \
  --max_workers 4 \
  --run_id eval-myagent \
  --namespace ''

# Aider 评测  
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path artifacts/aider-host-50/predictions.jsonl \
  --max_workers 4 \
  --run_id eval-aider \
  --namespace ''
```

评测结果在 `logs/run_evaluation/<run_id>/` 下，每个实例一个 `run_instance.log`，最终有 `report.json`。

### 4. 查看结果

```bash
# 查看 resolve rate
cat logs/run_evaluation/eval-myagent/deepseek-v4-pro/report.json
cat logs/run_evaluation/eval-aider/deepseek-v4-pro/report.json
```

## 环境差异说明

当前服务器环境的问题（WSL 不会有）：

| 问题 | 服务器 | WSL |
|------|--------|-----|
| Docker 存储驱动 | VFS（每层全量复制） | overlay2（正常） |
| Docker Hub | 被墙，需镜像 | 需配置代理或镜像 |
| GitHub HTTPS | 不稳定 | 正常 |
| 内存 | 7.6GB | 取决于笔记本 |
| Docker API 超时 | VFS 太慢导致 60s 超时 | overlay2 正常，2-3s 启动 |

## 文件清单

```
├── aider_host_run.py                       # Aider Host 运行器
├── claw-swe-bench/
│   ├── pull_images.py                      # 轩辕镜像拉取
│   ├── build_images.py                     # 镜像构建（备用）
│   ├── claw_swebench/claws/
│   │   ├── myagent.py                      # MyAgent adapter ✅
│   │   ├── aider.py                        # Aider adapter ✅
│   │   └── opencode_adapter.py             # OpenCode ❌
│   ├── config.py                           # 已注册 aider/opencode
│   ├── workspace.py                        # 支持 CLAW_NO_RESOURCE_LIMITS
│   └── artifacts/
│       ├── myagent-50/predictions.jsonl    # MyAgent 50 patches
│       └── aider-host-50/predictions.jsonl # Aider 50 patches
└── eval_runner.py                          # 持久容器评测脚本（待调试）
```

## 注意事项

- `eval_runner.py` 在当前环境跑出了 0% resolve rate — 说明测试命令格式有问题，WSL 上优先用官方 harness（步骤3）
- Aider 的 predictions.jsonl 是从 Host git repo 生成的 diff，官方 harness 应该能正确 apply
- 如果在 WSL 上也要跑推理（而不仅是评测），需要先拉镜像，然后跑 `run_infer.py`
- 当前 `integrate-claw-swe-bench` 分支已推送，其中 `myagent.py` adapter 的 `container_run_args` 已修复为正确 mount Python 3.12
