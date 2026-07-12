"""``/init`` command: generate ASTER.md for the current project."""

from __future__ import annotations

from pathlib import Path


_PROJECT_DETECTORS: list[tuple[str, str, list[str]]] = [
    ("pyproject.toml", "Python",
     [
         "uv sync --extra dev",
         "uv run pytest -q",
     ]),
    ("package.json", "Node.js",
     [
         "npm install",
         "npm test",
     ]),
    ("go.mod", "Go",
     [
         "go mod tidy",
         "go test ./...",
     ]),
    ("Cargo.toml", "Rust",
     [
         "cargo build",
         "cargo test",
     ]),
    ("Makefile", "C/C++",
     [
         "make",
         "make test",
     ]),
]

_ASTER_MD_HEADER = """\
# ASTER.md

本文件供 Asterwynd 在该项目中读取项目专属的指令和约束。
"""

_IMPORT_BANNER = "\n\n> 以下内容从 {source} 导入\n"


def _detect_project(cwd: Path) -> dict:
    """Detect project type and generate a starter commands section."""
    for filename, label, commands in _PROJECT_DETECTORS:
        if (cwd / filename).is_file():
            return {
                "type": label,
                "file": filename,
                "commands": "\n".join(f"- {c}" for c in commands),
            }
    return {"type": "Unknown", "file": None, "commands": ""}


def _find_entry_file(cwd: Path) -> str | None:
    candidates = [
        "main.py", "app.py", "src/main.py",
        "index.js", "src/index.js", "main.js",
        "main.go", "cmd/main.go",
        "src/main.rs",
    ]
    for candidate in candidates:
        if (cwd / candidate).is_file():
            return candidate
    return None


def _ensure_gitignore(cwd: Path) -> bool:
    """Append ``ASTER.local.md`` to ``.gitignore`` if not already present.

    Returns True if the gitignore was modified.
    """
    gi = cwd / ".gitignore"
    entry = "ASTER.local.md"
    try:
        if gi.is_file():
            lines = gi.read_text(encoding="utf-8").splitlines()
            if any(l.strip() == entry for l in lines):
                return False
            gi_text = gi.read_text(encoding="utf-8")
            if not gi_text.endswith("\n"):
                gi_text += "\n"
            gi_text += f"{entry}\n"
        else:
            gi_text = f"{entry}\n"
        gi.write_text(gi_text, encoding="utf-8")
        return True
    except OSError:
        return False


def generate_aster_md(cwd: Path | None = None) -> str:
    """Generate ASTER.md content for the current project.

    Returns the full Markdown content to write to ``ASTER.md``.
    """
    cwd = (cwd or Path.cwd()).resolve()
    project = _detect_project(cwd)

    sections = [_ASTER_MD_HEADER.strip()]

    # Import existing AGENTS.md / CLAUDE.md
    for source in ("AGENTS.md", "CLAUDE.md"):
        source_path = cwd / source
        if source_path.is_file():
            try:
                content = source_path.read_text(encoding="utf-8").strip()
                sections.append(
                    _IMPORT_BANNER.format(source=source) + content
                )
            except OSError:
                pass

    # Add commands section
    commands_part = project["commands"]
    entry_file = _find_entry_file(cwd)
    if entry_file:
        commands_part += f"\n- 启动服务: 运行 `{entry_file}`"
    if commands_part:
        sections.append("\n\n## 常用命令\n" + commands_part)

    sections.append("")
    return "\n".join(sections)


def write_aster_md(cwd: Path | None = None) -> str:
    """Generate and write ``ASTER.md`` to disk.

    Returns a one-line confirmation message.
    """
    cwd = (cwd or Path.cwd()).resolve()
    aster_path = cwd / "ASTER.md"

    content = generate_aster_md(cwd)
    aster_path.write_text(content, encoding="utf-8")

    gi_updated = _ensure_gitignore(cwd)
    parts = [f"已创建 {aster_path}"]
    if gi_updated:
        parts.append("已更新 .gitignore（添加 ASTER.local.md）")
    return "；".join(parts)
