# Plan 1: 项目脚手架

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建项目目录结构、pyproject.toml、README.md、基础 __init__.py 文件

**Architecture:** 标准 Python 项目布局，agent/ 为核心包，skills/ 为数据目录，cli.py 为入口

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio

---

## 文件清单

```
MyAgent/
├── agent/
│   ├── __init__.py
│   ├── loop.py
│   ├── llm.py
│   ├── message.py
│   ├── result.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── registry.py
│   │   ├── base.py
│   │   ├── sandbox.py
│   │   └── builtin/
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── manager.py
│   │   └── builtin/
│   ├── memory/
│   │   ├── __init__.py
│   │   └── manager.py
│   ├── skills/
│   │   ├── __init__.py
│   │   └── loader.py
│   └── subagent/
│       ├── __init__.py
│       ├── manager.py
│       └── protocol.py
├── skills/
│   ├── code-review.md
│   └── research.md
├── tests/
│   └── ...
├── cli.py
├── pyproject.toml
├── README.md
└── .gitignore
```

---

### Task 1: 创建目录结构

- [ ] **Step 1: 创建所有目录**

Run:
```bash
mkdir -p agent/tools/builtin agent/hooks/builtin agent/memory agent/skills agent/subagent skills tests
touch agent/__init__.py agent/tools/__init__.py agent/tools/builtin/__init__.py agent/hooks/__init__.py agent/hooks/builtin/__init__.py agent/memory/__init__.py agent/skills/__init__.py agent/subagent/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "chore: 创建项目目录结构"
```

---

### Task 2: 编写 pyproject.toml

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "myagent"
version = "0.1.0"
description = "A lightweight general-purpose AI agent framework"
requires-python = ">=3.11"
dependencies = [
    "aiohttp>=3.9.0",
    "psutil>=5.9.0",
    "tiktoken>=0.7.0",
    "typer>=0.12.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.12.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Commit**

```bash
git add pyproject.toml && git commit -m "chore: 添加 pyproject.toml"
```

---

### Task 3: 编写 .gitignore

- [ ] **Step 1: 创建 .gitignore**

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.venv/
*.egg-info/
dist/
build/
.coverage
.env
*.db
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore && git commit -m "chore: 添加 .gitignore"
```

---

### Task 4: 编写 README.md

- [ ] **Step 1: 创建 README.md**

```markdown
# MyAgent

A lightweight general-purpose AI agent framework in Python.

## Features

- **Plugin Architecture**: ToolRegistry, HookManager, MemoryManager, SkillLoader, SubAgentManager
- **Sandbox Execution**: subprocess-based sandbox with resource limits
- **Hook Lifecycle**: before_iteration, before_tool_execute, after_tool_execute, etc.
- **AutoCompact**: Token budget-based context compression
- **SubAgent Delegation**: Background task spawning with mid-turn injection
- **Markdown Skills**: Dynamic skill loading from .md files

## Quick Start

```bash
pip install -e ".[dev]"
python cli.py --model gpt-4 "Hello, what can you do?"
```

## Architecture

See `docs/superpowers/specs/` for design documents.

## License

MIT
```

- [ ] **Step 2: Commit**

```bash
git add README.md && git commit -m "docs: 添加 README.md"
```
