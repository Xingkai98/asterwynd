from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from agent.memory.model import MemoryEntry, MemoryHit

logger = logging.getLogger("asterwynd.memory.persistent")

_MEMORY_DIR_BASE = Path.home() / ".asterwynd" / "projects"
MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000
_VALID_NAME_RE = re.compile(r"^[a-z0-9-]+$")
_VALID_TYPES = frozenset({"user", "feedback", "project", "reference"})

# Long-term memory knobs (#75).  Overridable per-instance via MemoryConfig.
DEFAULT_IMPORTANCE = 3
IMPORTANCE_MIN = 1
IMPORTANCE_MAX = 5
ARCHIVE_AFTER_DAYS = 30
RECENCY_HALFLIFE_DAYS = 30
MAX_SUMMARY_TOKENS = 50
DEDUP_RECALL_THRESHOLD = 0.5
# Throttle: run decay archival at most once per window even when every
# read path triggers it, so a busy session does not scan the store per call.
DECAY_INTERVAL_SECONDS = 3600


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


def _clamp_importance(value: int | None) -> int:
    if value is None:
        return DEFAULT_IMPORTANCE
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_IMPORTANCE
    return max(IMPORTANCE_MIN, min(IMPORTANCE_MAX, value))


def _parse_dt(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _split_frontmatter(content: str) -> tuple[str | None, str]:
    """Split ``--- frontmatter ---`` from body. Returns (frontmatter, body)."""
    if not content.startswith("---"):
        return None, content
    first_end = content.find("\n", 3)
    if first_end == -1:
        return None, content
    second_start = content.find("\n---", first_end + 1)
    if second_start == -1:
        return None, content
    fm = content[first_end + 1 : second_start].strip()
    body = content[second_start + 4:].strip()
    return fm, body


class PersistentMemory:
    """Cross-session persistent memory, compatible with Claude Code format.

    Maintains typed memory files under
    ~/.asterwynd/projects/<project-hash>/memory/.
    MEMORY.md serves as the human-readable index; each memory is a separate
    .md file. Archived entries move to ``memory_dir/archive/``.

    The store is scoped to the git root (or resolved project root) so different
    projects never share memory files.
    """

    def __init__(
        self,
        project_root: Path,
        time_source: Callable[[], datetime] | None = None,
        *,
        archive_after_days: int = ARCHIVE_AFTER_DAYS,
        recency_halflife_days: int = RECENCY_HALFLIFE_DAYS,
        importance_default: int = DEFAULT_IMPORTANCE,
        summary_tokens: int = MAX_SUMMARY_TOKENS,
        decay_interval_seconds: int = DECAY_INTERVAL_SECONDS,
    ) -> None:
        git_root = _find_git_root(project_root)
        root = git_root or project_root.resolve()
        project_hash = _compute_project_hash(root)
        self.memory_dir = _MEMORY_DIR_BASE / project_hash / "memory"
        self._index_path = self.memory_dir / "MEMORY.md"
        self.scope = str(root.resolve())
        self._time_source = time_source or datetime.now
        self._archive_after_days = archive_after_days
        self._recency_halflife_days = recency_halflife_days
        self._importance_default = importance_default
        self._summary_tokens = summary_tokens
        self._decay_interval_seconds = decay_interval_seconds
        self._last_decay_run: datetime | None = None

    # ------------------------------------------------------------------
    # Time and decay
    # ------------------------------------------------------------------

    def _now(self) -> datetime:
        return self._time_source()

    def _clamp_importance(self, value: int | None) -> int:
        """Clamp importance to 1..5 using the instance default when None."""
        if value is None:
            return self._importance_default
        try:
            value = int(value)
        except (TypeError, ValueError):
            return self._importance_default
        return max(IMPORTANCE_MIN, min(IMPORTANCE_MAX, value))

    def decay_score(self, entry: MemoryEntry, now: datetime | None = None) -> float:
        """Importance × recency joint score (Decision 3).

        recency = 0.5 ^ (days_since_last_access / recency_halflife_days).
        """
        now = now or self._now()
        last = entry.last_accessed_at or entry.created_at or now
        days = max(0, (now - last).days)
        recency = 0.5 ** (days / self._recency_halflife_days)
        return entry.importance * recency

    def run_decay(self, now: datetime | None = None) -> int:
        """Archive active memories not retrieved for more than archive_after_days.

        Returns the number of archived entries.
        """
        now = now or self._now()
        archived = 0
        for entry in self.load_entries():
            last = entry.last_accessed_at or entry.created_at or now
            if (now - last).days > self._archive_after_days:
                self.archive(entry.name, reason="not retrieved within archive_after_days")
                archived += 1
        return archived

    def _run_decay_if_due(self, now: datetime | None = None) -> int:
        """Throttled decay trigger, called from every read entry point.

        Runs archival at most once per ``decay_interval_seconds`` so cold
        memories age out in production without scanning the store on every
        recall/search.
        """
        now = now or self._now()
        if self._last_decay_run is not None:
            elapsed = (now - self._last_decay_run).total_seconds()
            if elapsed < self._decay_interval_seconds:
                return 0
        self._last_decay_run = now
        return self.run_decay(now)

    # ------------------------------------------------------------------
    # Called by AgentLoop: load index / summary
    # ------------------------------------------------------------------

    def load_index(self) -> str | None:
        """Read MEMORY.md index, truncated to MAX_INDEX_LINES/MAX_INDEX_BYTES.

        Returns the raw index content for system message injection.
        Returns None if the index does not exist or is empty.
        """
        self._run_decay_if_due()
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

    def load_summary(self, max_tokens: int | None = None) -> str | None:
        """Generate a ~max_tokens global summary of active memories.

        Entries are ranked by importance (then recency) so the summary surfaces
        the most relevant facts first, and truncated to the token budget.
        Returns None when there are no active memories.
        """
        from agent.memory.summary import build_summary

        self._run_decay_if_due()
        if max_tokens is None:
            max_tokens = self._summary_tokens
        return build_summary(self.load_entries(), max_tokens=max_tokens)

    # ------------------------------------------------------------------
    # Entry loading
    # ------------------------------------------------------------------

    def _entry_path(self, name: str, archived: bool = False) -> Path:
        if archived:
            return self.memory_dir / "archive" / f"{name}.md"
        return self.memory_dir / f"{name}.md"

    def _load_entry_by_name(
        self, name: str, include_archived: bool = False
    ) -> MemoryEntry | None:
        active = self._parse_file(self._entry_path(name))
        if active is not None:
            return active
        if include_archived:
            return self._parse_file(self._entry_path(name, archived=True))
        return None

    def load_entries(self, include_archived: bool = False) -> list[MemoryEntry]:
        """Read all entries from the active (and optionally archive) dirs."""
        if not self.memory_dir.exists():
            return []
        entries: list[MemoryEntry] = []
        for path in sorted(self.memory_dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            entry = self._parse_file(path)
            if entry is not None:
                entries.append(entry)
        if include_archived:
            archive_dir = self.memory_dir / "archive"
            if archive_dir.exists():
                for path in sorted(archive_dir.glob("*.md")):
                    entry = self._parse_file(path)
                    if entry is not None:
                        entries.append(entry)
        return entries

    def _parse_file(self, filepath: Path) -> MemoryEntry | None:
        if not filepath.exists():
            return None
        try:
            raw = filepath.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read memory file %s", filepath, exc_info=True)
            return None
        fm, body = _split_frontmatter(raw)
        if fm is None:
            return None
        try:
            data = yaml.safe_load(fm) or {}
        except yaml.YAMLError:
            data = {}
        if not isinstance(data, dict):
            return None
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        name = data.get("name") or filepath.stem
        try:
            mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
        except OSError:
            mtime = datetime.min
        created_at = _parse_dt(metadata.get("created_at")) or mtime
        last_accessed_at = _parse_dt(metadata.get("last_accessed_at")) or created_at
        conflict_with = metadata.get("conflict_with") or []
        if isinstance(conflict_with, str):
            conflict_with = [conflict_with]
        try:
            importance = int(metadata.get("importance") or DEFAULT_IMPORTANCE)
        except (TypeError, ValueError):
            importance = DEFAULT_IMPORTANCE
        return MemoryEntry(
            name=str(name),
            description=str(data.get("description") or ""),
            body=body,
            type=str(metadata.get("type") or "project"),
            importance=self._clamp_importance(importance),
            created_at=created_at,
            last_accessed_at=last_accessed_at,
            scope=str(metadata.get("scope") or self.scope),
            archived=bool(metadata.get("archived") or filepath.parent.name == "archive"),
            conflict_with=list(conflict_with),
        )

    def _write_entry(self, entry: MemoryEntry) -> None:
        filepath = self._entry_path(entry.name, archived=entry.archived)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "name": entry.name,
            "description": entry.description,
            "metadata": {
                "type": entry.type,
                "importance": entry.importance,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "last_accessed_at": (
                    entry.last_accessed_at.isoformat() if entry.last_accessed_at else None
                ),
                "scope": entry.scope,
                "archived": entry.archived,
                "conflict_with": list(entry.conflict_with),
            },
        }
        text = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
            + "---\n\n"
            + entry.body.strip()
            + "\n"
        )
        try:
            filepath.write_text(text, encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to write memory file %s: %s", filepath, exc)
            raise

    # ------------------------------------------------------------------
    # Called by SaveMemory tool
    # ------------------------------------------------------------------

    def save(
        self,
        type: str,
        name: str,
        description: str,
        body: str,
        importance: int | None = None,
    ) -> str:
        """Create or update a memory entry. Returns a confirmation message."""
        if type not in _VALID_TYPES:
            return f"Error: Invalid memory type '{type}'. Must be one of: {', '.join(sorted(_VALID_TYPES))}."
        name_error = _validate_name(name)
        if name_error is not None:
            return f"Error: {name_error}"

        self.memory_dir.mkdir(parents=True, exist_ok=True)
        now = self._now()
        existing = self._load_entry_by_name(name)

        if existing is not None:
            existing.type = type
            existing.description = description
            existing.body = body.strip()
            if importance is not None:
                existing.importance = self._clamp_importance(importance)
            self._write_entry(existing)
            action = "updated"
        else:
            entry = MemoryEntry(
                name=name,
                description=description,
                body=body.strip(),
                type=type,
                importance=self._clamp_importance(importance),
                created_at=now,
                last_accessed_at=now,
                scope=self.scope,
            )
            self._write_entry(entry)
            action = "saved"

        self._update_index(name, description, action == "updated")
        return f"Memory '{name}' {action}."

    def apply_judgment(
        self,
        type: str,
        name: str,
        description: str,
        body: str,
        judgment: object,
        importance: int | None = None,
    ) -> str:
        """Apply a write-time dedup judgment (supplement/update/conflict/new).

        ``judgment`` exposes ``action`` and ``target_name``; see
        ``agent.memory.dedup.Judgment``. Falls back to a direct save for
        ``new``, unknown actions, or when the target vanished concurrently.
        """
        action = getattr(judgment, "action", "new")
        target = getattr(judgment, "target_name", None)
        reason = getattr(judgment, "reason", "") or action

        # Validate the LLM-provided target before it reaches path construction.
        if target is not None and _validate_name(str(target)) is not None:
            return self.save(type, name, description, body, importance=importance)

        if action == "supplement" and target:
            entry = self._load_entry_by_name(target)
            if entry is None or entry.archived:
                return self.save(type, name, description, body, importance=importance)
            entry.body = f"{entry.body}\n\n{body.strip()}"
            if importance is not None:
                entry.importance = self._clamp_importance(importance)
            self._write_entry(entry)
            self._update_index(target, entry.description, existed=True)
            self._append_changelog("supplement", target, reason)
            return f"Memory '{target}' supplemented (dedup)."

        if action == "update" and target:
            entry = self._load_entry_by_name(target)
            if entry is None or entry.archived:
                return self.save(type, name, description, body, importance=importance)
            entry.description = description
            entry.body = body.strip()
            if importance is not None:
                entry.importance = self._clamp_importance(importance)
            self._write_entry(entry)
            self._update_index(target, description, existed=True)
            self._append_changelog("update", target, reason)
            return f"Memory '{target}' updated (dedup)."

        if action == "conflict" and target:
            result = self.save(type, name, description, body, importance=importance)
            other = self._load_entry_by_name(target)
            incoming = self._load_entry_by_name(name)
            if other is not None and incoming is not None:
                if name not in other.conflict_with:
                    other.conflict_with.append(name)
                    self._write_entry(other)
                if target not in incoming.conflict_with:
                    incoming.conflict_with.append(target)
                    self._write_entry(incoming)
            self._append_changelog("conflict", f"{name}<->{target}", reason)
            return f"Memory '{name}' saved with conflict marked vs '{target}'."

        return self.save(type, name, description, body, importance=importance)

    # ------------------------------------------------------------------
    # Called by RecallMemory / SearchMemory tools
    # ------------------------------------------------------------------

    def recall(
        self,
        type: str | None = None,
        scope: str | None = None,
        include_archived: bool = False,
    ) -> str:
        """Read full content of active memories, optionally filtered by type/scope.

        Returns formatted markdown. When type is None, returns all memories.
        Scope is validated: a non-matching scope returns an empty result.
        """
        if scope is not None and scope != self.scope:
            return "No memories found."
        self._run_decay_if_due()
        entries = self.load_entries(include_archived=include_archived)
        if not entries:
            return "No memories found."
        if type is not None:
            entries = [e for e in entries if e.type == type]
        if not entries:
            type_hint = f" of type '{type}'" if type else ""
            return f"No memories{type_hint} found."

        parts: list[str] = []
        for entry in entries:
            self._touch(entry.name)
            parts.append(f"### {entry.name} ({entry.type})\n\n{entry.body}")
        return "\n\n---\n\n".join(parts)

    def search(
        self,
        query: str,
        top_k: int = 5,
        type: str | None = None,
        scope: str | None = None,
        include_archived: bool = False,
        embedder=None,
    ) -> list[MemoryHit]:
        """Semantic top-k recall over active memories (Decision 2 / 4).

        Uses the pluggable ``EmbeddingProvider`` (default NGramEmbedding from
        #77). Scope is validated; a non-matching scope returns no hits. Returned
        entries are touched (last_accessed_at) so decay reflects retrieval.
        """
        if scope is not None and scope != self.scope:
            return []
        from agent.embedding import NGramEmbedding

        self._run_decay_if_due()
        embedder = embedder or NGramEmbedding()
        entries = self.load_entries(include_archived=include_archived)
        if type is not None:
            entries = [e for e in entries if e.type == type]
        if not entries:
            return []

        query_vec = embedder.embed(query)
        scored: list[MemoryHit] = []
        for entry in entries:
            sim = embedder.cosine(query_vec, embedder.embed(entry.searchable_text))
            scored.append(MemoryHit(entry=entry, score=sim))
        scored.sort(key=lambda h: h.score, reverse=True)

        hits = scored[: max(0, top_k)]
        for hit in hits:
            self._touch(hit.entry.name)
        return hits

    def recall_similar(
        self,
        query: str,
        top_k: int = 5,
        embedder=None,
    ) -> list[MemoryHit]:
        """Write-dedup candidate recall: top-k similar active memories."""
        return self.search(query, top_k=top_k, embedder=embedder)

    # ------------------------------------------------------------------
    # Archival
    # ------------------------------------------------------------------

    def archive(self, name: str, reason: str | None = None) -> str:
        """Move an active memory into the archive directory."""
        entry = self._load_entry_by_name(name)
        if entry is None:
            return f"Error: memory '{name}' not found."
        if entry.archived:
            return f"Memory '{name}' already archived."
        archive_dir = self.memory_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        src = self._entry_path(name)
        dst = archive_dir / f"{name}.md"
        entry.archived = True
        self._write_entry_to(entry, dst)
        try:
            src.unlink()
        except OSError:
            pass
        self._remove_from_index(name)
        self._append_changelog("archive", name, reason or "archived")
        return f"Memory '{name}' archived."

    def restore(self, name: str) -> str:
        """Move an archived memory back into the active store."""
        entry = self._load_entry_by_name(name, include_archived=True)
        if entry is None or not entry.archived:
            return f"Error: memory '{name}' not found in archive."
        src = self._entry_path(name, archived=True)
        dst = self._entry_path(name)
        entry.archived = False
        self._write_entry_to(entry, dst)
        try:
            src.unlink()
        except OSError:
            pass
        self._update_index(name, entry.description, existed=False)
        self._append_changelog("restore", name, "restored from archive")
        return f"Memory '{name}' restored."

    def _write_entry_to(self, entry: MemoryEntry, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = {
            "name": entry.name,
            "description": entry.description,
            "metadata": {
                "type": entry.type,
                "importance": entry.importance,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "last_accessed_at": (
                    entry.last_accessed_at.isoformat() if entry.last_accessed_at else None
                ),
                "scope": entry.scope,
                "archived": entry.archived,
                "conflict_with": list(entry.conflict_with),
            },
        }
        text = (
            "---\n"
            + yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
            + "---\n\n"
            + entry.body.strip()
            + "\n"
        )
        filepath.write_text(text, encoding="utf-8")

    def _touch(self, name: str) -> None:
        """Update last_accessed_at on retrieval so decay reflects real access."""
        entry = self._load_entry_by_name(name)
        if entry is None or entry.archived:
            return
        entry.last_accessed_at = self._now()
        self._write_entry(entry)

    def _append_changelog(self, action: str, name: str, reason: str) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        changelog = self.memory_dir / "changelog.md"
        ts = self._now().isoformat(timespec="seconds")
        line = f"- [{ts}] {action} {name} → {reason}\n"
        with changelog.open("a", encoding="utf-8") as fh:
            fh.write(line)

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

    def _remove_from_index(self, name: str) -> None:
        """Remove an entry's line from MEMORY.md index."""
        if not self._index_path.exists():
            return
        filename = f"{name}.md"
        lines = self._index_path.read_text(encoding="utf-8").splitlines()
        kept = [line for line in lines if f"]({filename})" not in line]
        if len(kept) == len(lines):
            return
        self._index_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
