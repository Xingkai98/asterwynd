from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

logger = logging.getLogger("asterwynd.memory.persistent")

_MEMORY_DIR_BASE = Path.home() / ".claude" / "projects"
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000
_VALID_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_VALID_TYPES = frozenset({"user", "feedback", "project", "reference"})


def _compute_project_hash(project_root: Path) -> str:
    resolved = project_root.resolve()
    return hashlib.sha256(str(resolved).encode()).hexdigest()[:16]


def _find_git_root(path: Path) -> Path | None:
    current = path.resolve()
    for _ in range(64):
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
    return None


def _validate_name(name: str) -> str | None:
    """Return error message if name is invalid, None otherwise."""
    if not name or not _VALID_NAME_RE.match(name):
        return f"Invalid memory name '{name}': must be kebab-case (lowercase letters, digits, hyphens)"
    return None


class PersistentMemory:
    """Cross-session persistent memory, compatible with Claude Code format.

    Maintains four types of memory files under
    ~/.claude/projects/<project-hash>/memory/.
    MEMORY.md serves as the index; each memory is a separate .md file.
    """

    def __init__(self, project_root: Path) -> None:
        git_root = _find_git_root(project_root)
        root = git_root or project_root.resolve()
        project_hash = _compute_project_hash(root)
        self.memory_dir = _MEMORY_DIR_BASE / project_hash / "memory"
        self._index_path = self.memory_dir / "MEMORY.md"

    # ------------------------------------------------------------------
    # Called by AgentLoop: load index
    # ------------------------------------------------------------------

    def load_index(self) -> str | None:
        """Read MEMORY.md index, truncated to MAX_INDEX_LINES/MAX_INDEX_BYTES.

        Returns the raw index content for system message injection.
        Returns None if the index does not exist or is empty.
        """
        if not self._index_path.exists():
            return None
        try:
            raw = self._index_path.read_text(encoding="utf-8").strip()
        except OSError:
            logger.warning("Failed to read MEMORY.md", exc_info=True)
            return None
        if not raw:
            return None
        lines = raw.splitlines()
        truncated = False
        if len(lines) > MAX_INDEX_LINES:
            lines = lines[:MAX_INDEX_LINES]
            truncated = True
        content = "\n".join(lines)
        if len(content.encode("utf-8")) > MAX_INDEX_BYTES:
            encoded = content.encode("utf-8")[:MAX_INDEX_BYTES]
            content = encoded.decode("utf-8", errors="replace")
            if "\n" in content:
                content = content[: content.rfind("\n")]
            truncated = True
        if truncated:
            content += (
                "\n\n[WARNING: MEMORY.md truncated at "
                f"{MAX_INDEX_LINES} lines / {MAX_INDEX_BYTES} bytes. "
                "Use RecallMemory to retrieve specific entries.]"
            )
        return content

    # ------------------------------------------------------------------
    # Called by SaveMemory tool
    # ------------------------------------------------------------------

    def save(self, type: str, name: str, description: str, body: str) -> str:
        """Create or update a memory entry. Returns a confirmation message."""
        if type not in _VALID_TYPES:
            return f"Error: Invalid memory type '{type}'. Must be one of: {', '.join(sorted(_VALID_TYPES))}."
        name_error = _validate_name(name)
        if name_error is not None:
            return f"Error: {name_error}"

        self.memory_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{name}.md"
        filepath = self.memory_dir / filename

        frontmatter = (
            f"---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            f"metadata:\n"
            f"  type: {type}\n"
            f"---\n\n"
            f"{body.strip()}\n"
        )

        existed = filepath.exists()
        try:
            filepath.write_text(frontmatter, encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to write memory file %s: %s", filepath, exc)
            return f"Error: Failed to write memory file '{filename}': {exc}"

        self._update_index(name, description, existed)
        action = "updated" if existed else "saved"
        return f"Memory '{name}' {action}."

    # ------------------------------------------------------------------
    # Called by RecallMemory tool
    # ------------------------------------------------------------------

    def recall(self, type: str | None = None) -> str:
        """Read full content of all memories matching the given type.

        Returns formatted markdown. When type is None, returns all memories.
        """
        entries = self._parse_index()
        if not entries:
            return "No memories found."

        parts: list[str] = []
        for entry_filename in entries:
            filepath = self.memory_dir / entry_filename
            if not filepath.exists():
                logger.warning("Memory file referenced in index not found: %s", entry_filename)
                continue
            try:
                content = filepath.read_text(encoding="utf-8")
            except OSError:
                logger.warning("Failed to read memory file: %s", entry_filename, exc_info=True)
                continue

            entry_type = self._extract_type(content)
            entry_name = self._extract_name(content) or entry_filename.removesuffix(".md")

            if type is not None and entry_type != type:
                continue

            body = self._extract_body(content)
            parts.append(f"### {entry_name} ({entry_type})\n\n{body}")

        if not parts:
            type_hint = f" of type '{type}'" if type else ""
            return f"No memories{type_hint} found."

        return "\n\n---\n\n".join(parts)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_index(self) -> list[str]:
        """Extract filenames from MEMORY.md index lines."""
        if not self._index_path.exists():
            return []
        try:
            raw = self._index_path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: list[str] = []
        for line in raw.splitlines():
            match = re.search(r"\]\(([^)]+\.md)\)", line)
            if match:
                filename = match.group(1)
                if ".." not in filename:
                    entries.append(filename)
        return entries

    @staticmethod
    def _extract_type(content: str) -> str:
        """Extract metadata.type from YAML frontmatter."""
        match = re.search(r"metadata:\s*\n\s*type:\s*(\S+)", content)
        if match:
            return match.group(1)
        return "unknown"

    @staticmethod
    def _extract_name(content: str) -> str | None:
        """Extract name from YAML frontmatter."""
        match = re.search(r"^name:\s*(\S+)", content, re.MULTILINE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _extract_body(content: str) -> str:
        """Extract body content after YAML frontmatter."""
        first = content.find("---")
        if first == -1:
            return content.strip()
        second = content.find("---", first + 3)
        if second == -1:
            return content.strip()
        return content[second + 3:].strip()

    def _update_index(self, name: str, description: str, existed: bool) -> None:
        """Update MEMORY.md index line for a memory entry."""
        filename = f"{name}.md"
        new_line = f"- [{name}]({filename}) — {description}"

        if not self._index_path.exists():
            self._index_path.write_text(new_line + "\n", encoding="utf-8")
            return

        lines = self._index_path.read_text(encoding="utf-8").splitlines()

        if existed:
            updated = False
            for i, line in enumerate(lines):
                if f"]({filename})" in line:
                    lines[i] = new_line
                    updated = True
                    break
            if not updated:
                lines.append(new_line)
        else:
            lines.append(new_line)

        self._index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
