# tests/agent/memory/test_persistent.py
import pytest
from pathlib import Path

from agent.memory.persistent import (
    PersistentMemory,
    _compute_project_hash,
    _find_git_root,
    _validate_name,
)


class TestProjectHash:
    def test_hash_is_16_hex_chars(self, tmp_path):
        h = _compute_project_hash(tmp_path)
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_path_produces_same_hash(self, tmp_path):
        assert _compute_project_hash(tmp_path) == _compute_project_hash(tmp_path)

    def test_different_paths_produce_different_hashes(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.mkdir()
        b.mkdir()
        assert _compute_project_hash(a) != _compute_project_hash(b)


class TestFindGitRoot:
    def test_returns_none_for_non_git_dir(self, tmp_path, monkeypatch):
        # Block all Path.exists calls for .git to simulate non-git dir
        original_exists = Path.exists

        def fake_exists(self):
            if self.name == ".git":
                return False
            return original_exists(self)

        monkeypatch.setattr(Path, "exists", fake_exists)
        assert _find_git_root(tmp_path) is None

    def test_finds_git_root_from_subdirectory(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        sub = tmp_path / "deep" / "sub"
        sub.mkdir(parents=True)
        assert _find_git_root(sub) == tmp_path.resolve()


class TestValidateName:
    def test_valid_names(self):
        assert _validate_name("user-role") is None
        assert _validate_name("test") is None
        assert _validate_name("my-memory-123") is None

    def test_rejects_empty(self):
        assert _validate_name("") is not None
        assert _validate_name("  ") is not None

    def test_rejects_non_kebab(self):
        assert _validate_name("User Role") is not None
        assert _validate_name("user_role") is not None
        assert _validate_name("用户") is not None


class TestPersistentMemory:
    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        """PersistentMemory backed by a temp memory dir."""
        # Override the base dir so we don't write to real ~/.asterwynd
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr(
            "agent.memory.persistent._MEMORY_DIR_BASE",
            fake_base,
        )
        return PersistentMemory(tmp_path)

    # --- load_index ---

    def test_load_index_returns_none_when_no_mem_dir(self, mem):
        assert mem.load_index() is None

    def test_load_index_returns_none_when_empty(self, mem):
        mem.memory_dir.mkdir(parents=True)
        mem._index_path.write_text("")
        assert mem.load_index() is None

    def test_load_index_returns_content(self, mem):
        mem.memory_dir.mkdir(parents=True)
        mem._index_path.write_text(
            "- [user](user-role.md) — description\n"
        )
        result = mem.load_index()
        assert "user-role.md" in result

    def test_load_index_truncates_lines(self, mem, monkeypatch):
        monkeypatch.setattr("agent.memory.persistent.MAX_INDEX_LINES", 3)
        mem.memory_dir.mkdir(parents=True)
        lines = [f"- [entry{i}](entry{i}.md) — desc{i}" for i in range(10)]
        mem._index_path.write_text("\n".join(lines))
        result = mem.load_index()
        assert result is not None  # type narrowing
        assert "WARNING" in result
        assert result.count("entry") < 10

    def test_load_index_truncates_bytes(self, mem, monkeypatch):
        monkeypatch.setattr("agent.memory.persistent.MAX_INDEX_BYTES", 50)
        mem.memory_dir.mkdir(parents=True)
        mem._index_path.write_text(
            "- [a-very-long-entry-name](a-very-long-entry-name.md) — a very long description\n" * 20
        )
        result = mem.load_index()
        assert result is not None
        assert "WARNING" in result

    # --- save ---

    def test_save_creates_memory_file(self, mem):
        result = mem.save("user", "my-role", "my role", "I am a backend engineer.")
        assert "saved" in result

        filepath = mem.memory_dir / "my-role.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "name: my-role" in content
        assert "type: user" in content
        assert "I am a backend engineer." in content

    def test_save_updates_existing_memory(self, mem):
        mem.save("user", "my-role", "original", "Old content.")
        result = mem.save("user", "my-role", "updated", "New content.")
        assert "updated" in result

        content = (mem.memory_dir / "my-role.md").read_text()
        assert "New content." in content
        assert "Old content." not in content

    def test_save_updates_memory_index(self, mem):
        mem.save("user", "entry-a", "desc a", "body a")
        mem.save("project", "entry-b", "desc b", "body b")

        index = mem._index_path.read_text()
        assert "entry-a.md" in index
        assert "desc a" in index
        assert "entry-b.md" in index

    def test_save_rejects_invalid_name(self, mem):
        result = mem.save("user", "not valid!", "desc", "body")
        assert "Error" in result
        assert not mem.memory_dir.exists()

    def test_save_rejects_invalid_name_no_files_written(self, mem):
        """When name is invalid, no files or directories should be created."""
        mem.memory_dir.mkdir(parents=True)
        preexisting = set(mem.memory_dir.iterdir()) if mem.memory_dir.exists() else set()
        result = mem.save("user", "bad name!", "desc", "body")
        assert "Error" in result
        if mem.memory_dir.exists():
            assert set(mem.memory_dir.iterdir()) == preexisting

    def test_save_creates_valid_yaml_frontmatter(self, mem):
        mem.save("feedback", "testing-rules", "test rules", "Always use real DB.")
        content = (mem.memory_dir / "testing-rules.md").read_text()
        # Verify frontmatter starts and ends with ---
        assert content.startswith("---")
        lines = content.splitlines()
        assert lines[0] == "---"
        # Second --- should appear before body
        assert "---" in content[3:]
        assert "Always use real DB." in content

    # --- recall ---

    def test_recall_returns_no_memories_when_empty(self, mem):
        assert "No memories" in mem.recall()

    def test_recall_returns_all_memories(self, mem):
        mem.save("user", "role", "role", "Backend engineer.")
        mem.save("project", "deadline", "deadline", "Ship by Friday.")

        result = mem.recall()
        assert "### role (user)" in result
        assert "Backend engineer." in result
        assert "### deadline (project)" in result
        assert "Ship by Friday." in result

    def test_recall_filters_by_type(self, mem):
        mem.save("user", "role", "role", "Backend engineer.")
        mem.save("project", "deadline", "deadline", "Ship by Friday.")

        result = mem.recall(type="user")
        assert "Backend engineer." in result
        assert "Ship by Friday." not in result

    def test_recall_skips_missing_files(self, mem):
        mem.save("user", "role", "role", "Content.")
        # Manually delete the .md file but keep the index
        (mem.memory_dir / "role.md").unlink()
        result = mem.recall()
        assert "No memories" in result or "No memories of type" in result

    # --- corrupt frontmatter handling ---

    def test_extract_type_missing_metadata(self, mem):
        """_extract_type returns 'unknown' when metadata key is missing."""
        content = "---\nname: test\n---\nbody"
        assert PersistentMemory._extract_type(content) == "unknown"

    def test_extract_type_broken_yaml(self, mem):
        """_extract_type returns 'unknown' for malformed frontmatter."""
        content = "---\nname: test\ntype: user\n"
        assert PersistentMemory._extract_type(content) == "unknown"

    def test_extract_body_missing_closing_dashes(self, mem):
        """_extract_body returns full content when closing --- is missing."""
        content = "---\nname: test\ntype: user\nbody here"
        body = PersistentMemory._extract_body(content)
        assert "body here" in body

    def test_extract_name_missing(self, mem):
        """_extract_name returns None when name field is missing."""
        content = "---\ntype: user\n---\nbody"
        assert PersistentMemory._extract_name(content) is None

    # --- _parse_index path traversal ---

    def test_parse_index_rejects_path_traversal(self, mem):
        """_parse_index regex only matches .md files, not path traversal patterns."""
        mem.memory_dir.mkdir(parents=True)
        mem._index_path.write_text(
            "- [escape](../outside.md) — tries to escape\n"
            "- [valid](valid.md) — valid entry\n"
        )
        entries = mem._parse_index()
        assert "valid.md" in entries
        assert "../outside.md" not in entries
