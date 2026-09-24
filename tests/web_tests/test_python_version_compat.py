# tests/web_tests/test_python_version_compat.py
"""语法级版本兼容守卫：CI 跑 Python 3.11，本地开发常在更新的解释器上。

issue #191 的 PR 首轮 CI 就是被这类问题拦下的：本地（3.12）能跑的
``f"...{x!r}...\\"...\\"..."`` 在 3.11 上是 ``SyntaxError: f-string expression part
cannot include a backslash``（3.12 的 PEP 701 才放开这个限制）。这种错误在本地
**跑不起来任何提示**——它只在 CI 的 collect 阶段炸，而且与本次改动的逻辑无关，
排查成本全花在「本地明明过了」。

这里按仓库声明的**最低**支持版本（``requires-python``，当前 3.11）起子进程，用内建
``compile()`` 解析 ``tests/``、``web/``、``agent/``、``benchmarks/``、``scripts/`` 下的
全部源码，把该限制变成一条本地可跑的断言。
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _declared_min_python() -> str | None:
    """从 pyproject.toml 读 ``requires-python`` 的最低版本（如 '>=3.11' → '3.11'）。"""
    pyproject = REPO_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return None
    match = re.search(
        r'^requires-python\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M
    )
    if not match:
        return None
    version = re.search(r"(\d+\.\d+)", match.group(1))
    return version.group(1) if version else None


def _interpreter_for(version: str) -> str | None:
    """找一个该版本的解释器；找不到就跳过（不把缺解释器当成失败）。"""
    direct = shutil.which(f"python{version}")
    if direct:
        return direct
    try:
        found = subprocess.run(
            ["uv", "python", "find", version],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if found.returncode == 0 and found.stdout.strip():
            return found.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def test_source_compiles_on_lowest_supported_python():
    """全仓源码必须能在 pyproject 声明的最低 Python 上编译通过。

    用子进程显式按该版本编译，而不是 ``ast.parse``——后者在当前解释器上运行，
    恰恰会放过「新解释器才允许、旧版本是语法错误」的那类写法（这正是要防的）。
    """
    version = _declared_min_python()
    assert version, "pyproject.toml 缺少 requires-python，无法判定最低支持版本"

    interpreter = _interpreter_for(version)
    if interpreter is None:
        pytest.skip(f"找不到 Python {version} 解释器，跳过语法兼容检查")

    targets = sorted(
        p
        for root in ("tests", "web", "agent", "benchmarks", "scripts")
        for p in (REPO_ROOT / root).rglob("*.py")
        if "__pycache__" not in p.parts
    )
    assert targets, "没有找到待检查的 Python 源文件"

    # 两个关键点，缺一不可：
    #  1. 必须**用那个解释器**解析，不能在当前进程里比较 —— 后者用当前版本，恰好会
    #     放过「新版本才允许、旧版本是语法错误」的写法（本测试要防的正是它）。
    #  2. 必须用内建 `compile()`，**不能**用 `py_compile.compile(..., cfile=...)` ——
    #     实测后者对这类错误会「成功返回」（错误被吞进它自己的写入路径），
    #     `compile(src, ..., 'exec')` 才会如实抛 SyntaxError。
    # 一次子进程批量解析，避免 300+ 次进程启动。
    script = (
        "import sys, json, pathlib\n"
        "bad = []\n"
        "for path in json.loads(sys.argv[1]):\n"
        "    try:\n"
        "        src = pathlib.Path(path).read_text(encoding='utf-8')\n"
        "        compile(src, path, 'exec')\n"
        "    except SyntaxError as exc:\n"
        "        bad.append(f\"{path}:{exc.lineno}: {str(exc).splitlines()[-1][:120]}\")\n"
        "    except Exception as exc:\n"
        "        bad.append(f\"{path}: {type(exc).__name__}: {exc}\")\n"
        "print(json.dumps(bad))\n"
    )
    proc = subprocess.run(
        [interpreter, "-c", script, json.dumps([str(p) for p in targets])],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"用 Python {version}（{interpreter}）批量编译失败：\n{proc.stderr[-2000:]}"
        )
    failures = json.loads(proc.stdout.strip().splitlines()[-1])

    if failures:
        pytest.fail(
            f"以下文件在最低支持版本 Python {version} 上编译失败"
            f"（本地解释器 {sys.version.split()[0]}）。"
            "常见原因：f-string 表达式里含反斜杠（3.12 的 PEP 701 才允许）：\n  "
            + "\n  ".join(failures)
        )
