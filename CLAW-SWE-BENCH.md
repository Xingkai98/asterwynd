# Claw-SWE-Bench 集成 — 跑 benchmark 指南

本分支（`integrate-claw-swe-bench`）将 MyAgent 接入 [Claw-SWE-Bench](https://github.com/opensquilla/claw-swe-bench) 统一 harness 对比框架。

## 做了什么

- **`claw_swebench/claws/myagent.py`** — `MyAgentAdapter(BaseClawAdapter)`，实现容器的 Docker exec 调用
- **`agent/claw_solve.py`** — MyAgent headless solver 入口，运行在目标容器内
- **`claw_swebench/claws/__init__.py`** — 注册 myagent claw
- **`claw_swebench/config.py`** — 添加 `CLAW_DEFAULTS["myagent"]`

## 环境要求

### 1. Python 依赖

```bash
pip install datasets pyyaml swebench>=4.1.0 docker
```

### 2. 独立 Python 3.12（用于 bind-mount 进容器）

```bash
uv python install 3.12.13
# 安装后路径: ~/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12
```

### 3. MyAgent venv（依赖安装）

```bash
cd /path/to/my-agent
uv sync --extra dev
# 确保 agent/claw_solve.py 存在
```

### 4. SWE-bench Docker 镜像

Claw-SWE-Bench 需要每个 instance 的 Docker 镜像预构建好。镜像名格式：`sweb.eval.x86_64.<instance_id>:latest`

构建方式（使用 SWE-bench harness）：

```python
from swebench.harness.docker_build import build_instance_image
from swebench.harness.test_spec import make_test_spec
from datasets import load_dataset

# 构建所有需要的镜像
ds = load_dataset("princeton-nlp/SWE-bench_Verified", split="test")
for instance in ds:
    spec = make_test_spec(instance)  # depends on swebench version
    build_instance_image(spec, ...)
```

或用 Claw-SWE-bench 自带的 lite set（50 个 instance）：

```bash
# 先检查需要哪些 image
cat claw-swe-bench/config/verified_mini_50.txt
```

### 5. Docker daemon

确保当前用户能访问 Docker（`docker ps` 正常）。

### 6. API Key

```bash
export ANTHROPIC_API_KEY="sk-xxx"
export ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"  # 如用 DeepSeek
```

## 配置（首次使用）

编辑环境变量，指向你的路径：

```bash
# Python 独立安装路径
export CLAW_PYTHON_BIN="$HOME/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"

# MyAgent 源码和 venv 路径
export MYAGENT_SRC="/path/to/my-agent"
export MYAGENT_VENV="/path/to/my-agent/.venv"

# 模型（默认 deepseek-v4-pro，可在命令行覆盖）
export MYAGENT_MODEL="deepseek-v4-pro"
```

## 跑 benchmark

### 跑单实例测试

```bash
cd claw-swe-bench
python run_infer.py \
  --claw myagent \
  --dataset verified \
  --instance_ids psf__requests-1142 \
  --run_id myagent-test-1 \
  --model deepseek-v4-pro
```

### 跑 lite 全量（50 个 instance）

```bash
python run_infer.py \
  --claw myagent \
  --dataset verified \
  --instance_file config/verified_mini_50.txt \
  --run_id myagent-lite \
  --model deepseek-v4-pro \
  --workers 2
```

### 评估

```bash
python run_eval.py --run_id myagent-lite --dataset verified
```

评估需要 SWE-bench 的 eval venv：
```bash
export SWEBENCH_VENV="/path/to/swe-bench-venv"
export SWEBENCH_WORK_DIR="/tmp/swebench-eval"
```

### 和已有关卡对比

Claw-SWE-bench 自带排行榜数据（`config/verified_mini_50.txt` 上的结果）：

| Claw | 模型 | Pass@1 (verified_mini_50) |
|------|------|--------------------------|
| openclaw | claude-opus-4.6 | TBD |
| hermes | glm-5.1 | TBD |
| myagent | deepseek-v4-pro | **见你的结果** |

论文已报告的数据对应 Claw-SWE-Bench 论文 Table 1。

## 架构说明

```
run_infer.py
  └── orchestrator.run_one_instance(instance)
        ├── SWEBenchWorkspace.start()  # 启动 Docker 容器（sweb.eval.x86_64.xxx）
        ├── adapter.send_task(prompt)  # docker exec 运行 MyAgent
        │     └── docker exec <container> python3.12 /opt/myagent/agent/claw_solve.py
        │           ├── AgentLoop 在 /testbed 中迭代
        │           └── 输出 MYAGENT_RESULT sentinel
        ├── collect_patch()            # 从容器内 git diff 收集 patch
        └── cleanup()

run_eval.py  # 用 SWE-bench 官方 harness 评估 patches
```

MyAgent adapter 的 container_run_args 会 bind-mount：
- `$MYAGENT_SRC → /opt/myagent:ro`（源码）
- `$MYAGENT_VENV → /opt/myagent-venv:ro`（依赖包）

然后在容器内通过 `docker exec` 调用 Python 3.12 执行 `/opt/myagent/agent/claw_solve.py`。

## 故障排查

1. **Docker image not found** — 需要先构建 SWE-bench 镜像
2. **Permission denied (docker)** — 确保用户在 `docker` 组中
3. **ANTHROPIC_API_KEY not set** — 检查环境变量是否传入容器（`_FORWARDED_ENV_VARS`）
4. **ModuleNotFound** — 检查 `MYAGENT_SRC` 和 `MYAGENT_VENV` 路径，以及 `PYTHONPATH`

## 分支内容

```
integrate-claw-swe-bench/
├── agent/claw_solve.py          # MyAgent headless solver（容器内执行）
├── claw-swe-bench/              # Claw-SWE-Bench 框架（含自定义 adapter）
│   └── claw_swebench/claws/myagent.py  # MyAgentAdapter
└── CLAW-SWE-BENCH.md            # 本文档
```
