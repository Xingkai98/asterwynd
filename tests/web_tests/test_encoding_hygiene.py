"""编码卫生守卫（change ``fix-windows-encoding-and-guard``，L1 机械防线）。

**为什么需要它**：本地文件 I/O 不写 ``encoding=`` 时会按进程 locale 编解码，而本仓的
数据一律是 UTF-8——Windows 中文机器（GBK）上这会变成「会话保存失败」「Hub 列表 500」
这类真实故障（见 ``openspec/changes/archive/*-fix-windows-encoding-and-guard/diagnosis.md``）。
而 CI 跑在 Linux（locale = UTF-8），**这类缺陷在 CI 上不可能变红**，所以必须有静态守卫。

判据（AST 而非正则，覆盖跨行调用；扫 ``agent/ web/ benchmarks/ scripts/ tests/``）：

1. ``open(...)`` 未传 ``encoding=``，且 mode 不是二进制（``rb/wb/ab`` 等）；
2. ``Path.read_text()`` / ``Path.write_text()`` 未传 ``encoding=``；
3. ``subprocess.run/Popen/call/check_output/check_call(...)`` 传了
   ``text=True``/``universal_newlines=True``、argv 里出现 ``node``（我们的 node harness，
   输出确定是 UTF-8）却未传 ``encoding=``。

**为什么第 3 条只管 node**：子进程的输出编码是**子进程自己的契约**——我们自己那个
python CLI 在 Windows 上往管道写的是 locale 编码（GBK），父进程若强行按严格 UTF-8 解码
反而会崩（实测把 ``tests/test_flow_policy.py`` 的 ``show.stdout`` 变成 None）。
所以「子进程解码」不设统一规则，只钉住**确定跨平台输出 UTF-8 的 node harness**。

命中即失败并列出 ``文件:行号``。例外必须写进 :data:`ALLOWLIST` 并给出理由——白名单是
**可评审**的显式列表，不是「扫不到就算了」。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("agent", "web", "benchmarks", "scripts", "tests")

#: 显式例外：``相对路径:行号`` → 理由。**只允许**「确实必须依赖 locale 编码」或
#: 「二进制/无文本语义」的站点；新增例外必须在评审里说明为什么不能写显式编码。
ALLOWLIST: dict[str, str] = {}

SUBPROCESS_TEXT_KWARGS = ("text", "universal_newlines")
SUBPROCESS_FUNCS = {"run", "Popen", "call", "check_call", "check_output"}

#: 名字叫 ``open`` 但**不是文件文本 I/O** 的接收者（没有 encoding 语义）。
#: 显式列出而不是靠「看起来像」，是为了让例外可评审：``Image.open`` 是 PIL 的解码入口，
#: ``ZipFile``/``TarFile`` 等是归档容器——它们都不接受 ``encoding=``。
NON_FILE_OPENERS = frozenset({
    "Image", "ImageFile", "ZipFile", "TarFile", "GzipFile", "BZ2File", "LZMAFile",
})


def _iter_sources() -> list[Path]:
    return sorted(
        path
        for root in SCAN_ROOTS
        for path in (REPO_ROOT / root).rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _kwarg_names(call: ast.Call) -> set[str]:
    return {kw.arg for kw in call.keywords if kw.arg}


def _literal_mode(call: ast.Call) -> str | None:
    """``open()`` 的 mode 字面量（第 2 位置参数或 ``mode=``）；拿不到返回 None。"""
    mode_node: ast.expr | None = None
    if len(call.args) >= 2:
        mode_node = call.args[1]
    for kw in call.keywords:
        if kw.arg == "mode":
            mode_node = kw.value
    if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
        return mode_node.value
    return None


def _receiver_tail(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _is_open_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "open"
    if isinstance(func, ast.Attribute):
        # ``io.open`` / ``builtins.open`` 是文件 I/O；``Image.open`` 之类不是（见上表）
        if _receiver_tail(func.value) in NON_FILE_OPENERS:
            return False
        return func.attr == "open"
    return False


def _is_path_text_call(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    if node.func.attr in ("read_text", "write_text"):
        return node.func.attr
    return None


def _is_subprocess_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    return node.func.attr in SUBPROCESS_FUNCS


def _check_file(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    try:
        rel = path.relative_to(REPO_ROOT).as_posix()
    except ValueError:                      # 自检用例用的是 tmp_path 下的样本文件
        rel = path.name
    problems: list[str] = []

    for node in ast.walk(tree):
        key = f"{rel}:{getattr(node, 'lineno', 0)}"
        if key in ALLOWLIST:
            continue

        if _is_open_call(node):
            names = _kwarg_names(node)
            if "encoding" in names:
                continue
            mode = _literal_mode(node)
            if mode is not None and "b" in mode:
                continue          # 二进制模式没有编码语义
            if mode is None and len(node.args) >= 2:
                # mode 是动态表达式：静态判不出是否二进制，如实报出来（宁可让人看一眼）
                problems.append(f"{key}: open() 的 mode 非字面量且未指定 encoding=")
                continue
            if mode is None and len(node.args) <= 1:
                # 默认 mode="r"（文本）——同样必须显式编码；但 ``open(fd)`` 形态要排除
                first = node.args[0] if node.args else None
                if isinstance(first, ast.Constant) and isinstance(first.value, int):
                    continue      # 文件描述符形态，无编码参数
            problems.append(f"{key}: open() 未指定 encoding=")
            continue

        attr = _is_path_text_call(node)
        if attr:
            if "encoding" not in _kwarg_names(node):
                problems.append(f"{key}: {attr}() 未指定 encoding=")
            continue

        if _is_subprocess_call(node):
            names = _kwarg_names(node)
            wants_text = any(
                kw.arg in SUBPROCESS_TEXT_KWARGS
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
                for kw in node.keywords
            )
            if not wants_text or "encoding" in names:
                continue
            source_segment = ast.get_source_segment(source, node) or ""
            if "node" not in source_segment:
                continue          # 子进程编码由子进程决定，见模块 docstring
            problems.append(
                f"{key}: subprocess.{node.func.attr}() 跑 node harness 却未指定 encoding=")

    return problems


def test_local_file_io_always_declares_its_encoding():
    """全仓静态守卫：本地文件 I/O 与文本子进程必须显式声明编码。"""
    targets = _iter_sources()
    assert targets, "没有扫到任何 Python 源文件——扫描根目录配错了"

    problems = [line for path in targets for line in _check_file(path)]
    assert not problems, (
        "以下站点依赖进程 locale 的默认编码（Windows/GBK 上会坏，CI 的 Linux 上看不见）；"
        "请补 encoding=\"utf-8\"，确有必要则写进本文件的 ALLOWLIST 并说明理由：\n  "
        + "\n  ".join(problems)
    )


def test_guard_itself_would_catch_a_regression(tmp_path):
    """守卫必须**有牙齿**：故意造一个违规文件，扫描逻辑必须报出来。

    没有这条，守卫可能因为 AST 判据写错而恒绿（例如把所有 open 都当二进制跳过）。
    """
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import subprocess\n"
        "open('a.txt')\n"
        "open('b.txt', 'rb')\n"
        "open('c.txt', encoding='utf-8')\n"
        "from pathlib import Path\n"
        "Path('d.txt').read_text()\n"
        "Path('e.txt').open('r')\n"
        "subprocess.run(['python', '-c', 'x'], text=True)\n"
        "subprocess.run(['node', '-e', 'x'], text=True)\n"
        "subprocess.run(['node', '-e', 'x'], text=True, encoding='utf-8')\n"
        "from PIL import Image\n"
        "Image.open('f.png')\n",
        encoding="utf-8",
    )
    problems = _check_file(sample)
    joined = "\n".join(problems)
    assert "open() 未指定 encoding=" in joined, joined
    assert "read_text() 未指定 encoding=" in joined, joined
    assert "跑 node harness 却未指定 encoding=" in joined, joined
    # 二进制模式 / 已显式声明 / 非文件 open（PIL）/ 非 node 子进程 **不得**被误报
    assert len(problems) == 4, f"误报/漏报了：{joined}"
