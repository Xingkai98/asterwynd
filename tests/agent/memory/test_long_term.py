# Tests for long-term memory deepening (#75): schema, decay, archival,
# semantic search, global summary, scope isolation, and write-time judgments.
from datetime import datetime, timedelta

import pytest

from agent.memory.dedup import Judgment
from agent.memory.persistent import PersistentMemory


class Clock:
    """Mutable time source so tests can control now()."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def make_mem(tmp_path, monkeypatch):
    def _make(clock=None):
        fake_base = tmp_path / "fake-claude" / "projects"
        monkeypatch.setattr("agent.memory.persistent._MEMORY_DIR_BASE", fake_base)
        time_source = clock if clock is not None else lambda: datetime(2026, 8, 2, 12, 0, 0)
        return PersistentMemory(tmp_path, time_source=time_source)

    return _make


def _reload(mem: PersistentMemory, name: str):
    return mem._load_entry_by_name(name)


def _load_archived(mem: PersistentMemory, name: str):
    return mem._load_entry_by_name(name, include_archived=True)


# ---------------------------------------------------------------------------
# Schema: importance / created_at / last_accessed_at / scope
# ---------------------------------------------------------------------------


class TestSchema:
    def test_save_writes_importance_scope_created_at(self, make_mem):
        mem = make_mem()
        mem.save("user", "my-role", "role", "I write Go.", importance=5)
        entry = _reload(mem, "my-role")
        assert entry is not None
        assert entry.importance == 5
        assert entry.scope == mem.scope
        assert entry.created_at is not None
        assert entry.last_accessed_at is not None
        assert entry.type == "user"

    def test_save_default_importance_is_3(self, make_mem):
        mem = make_mem()
        mem.save("user", "role", "role", "I write Go.")
        assert _reload(mem, "role").importance == 3

    def test_instance_importance_default_applied(self, make_mem):
        """Regression (review): importance_default from config must be used."""
        mem = make_mem()
        mem._importance_default = 4
        mem.save("user", "role", "role", "I write Go.")
        assert _reload(mem, "role").importance == 4

    def test_importance_is_clamped_to_1_5(self, make_mem):
        mem = make_mem()
        mem.save("user", "a", "a", "x", importance=99)
        mem.save("user", "b", "b", "x", importance=-1)
        assert _reload(mem, "a").importance == 5
        assert _reload(mem, "b").importance == 1

    def test_save_preserves_created_at_on_update(self, make_mem):
        mem = make_mem()
        mem.save("user", "role", "v1", "Old.")
        original_created = _reload(mem, "role").created_at
        mem.save("user", "role", "v2", "New.")
        entry = _reload(mem, "role")
        assert entry.created_at == original_created
        assert entry.body == "New."

    def test_save_update_changes_type(self, make_mem):
        """Regression (review): save() update must apply the passed type, not
        silently keep the old one."""
        mem = make_mem()
        mem.save("user", "role", "v1", "Old.")
        mem.save("project", "role", "v2", "New.")
        assert _reload(mem, "role").type == "project"

    def test_old_format_memory_migrates_with_defaults(self, make_mem, tmp_path):
        """Memories written without new fields parse with safe defaults."""
        mem = make_mem()
        mem.memory_dir.mkdir(parents=True)
        (mem.memory_dir / "legacy.md").write_text(
            "---\nname: legacy\ndescription: old\nmetadata:\n  type: user\n---\n\nbody here\n",
            encoding="utf-8",
        )
        entry = _reload(mem, "legacy")
        assert entry is not None
        assert entry.importance == 3
        assert entry.scope == mem.scope
        assert entry.body == "body here"


# ---------------------------------------------------------------------------
# Decay: importance × recency, run_decay, archive/restore
# ---------------------------------------------------------------------------


class TestDecay:
    def test_decay_score_is_importance_times_recency(self, make_mem):
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "deadline", "deadline", "Ship Friday.", importance=4)
        entry = _reload(mem, "deadline")
        # Fresh: recency = 1.0
        assert mem.decay_score(entry) == pytest.approx(4.0)
        # 30 days ago: recency = 0.5^1 = 0.5
        entry.last_accessed_at = clock.now - timedelta(days=30)
        assert mem.decay_score(entry) == pytest.approx(2.0)

    def test_run_decay_archives_memories_not_accessed_in_30_days(self, make_mem):
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "deadline", "deadline", "Ship Friday.")
        entry = _reload(mem, "deadline")
        entry.last_accessed_at = clock.now - timedelta(days=31)
        mem._write_entry(entry)

        archived = mem.run_decay()
        assert archived == 1
        assert _reload(mem, "deadline") is None  # not active anymore
        archived_entry = _reload(mem, "deadline")
        assert archived_entry is None

        archived_entry = mem._load_entry_by_name("deadline", include_archived=True)
        assert archived_entry is not None
        assert archived_entry.archived
        # archived entries are excluded from active lists
        assert mem.load_entries() == []

    def test_recently_accessed_memory_not_archived(self, make_mem):
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "hot", "hot", "still active")
        entry = _reload(mem, "hot")
        entry.last_accessed_at = clock.now - timedelta(days=29)
        mem._write_entry(entry)
        assert mem.run_decay() == 0

    def test_archive_and_restore(self, make_mem):
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "old", "old", "cold fact")
        result = mem.archive("old", reason="test")
        assert "archived" in result
        assert not (mem.memory_dir / "old.md").exists()
        assert (mem.memory_dir / "archive" / "old.md").exists()
        assert "No memories" in mem.recall()

        restore = mem.restore("old")
        assert "restored" in restore
        assert (mem.memory_dir / "old.md").exists()
        assert "cold fact" in mem.recall()

    def test_archive_unknown_memory_returns_error(self, make_mem):
        mem = make_mem()
        assert "not found" in mem.archive("nope")

    def test_run_decay_fires_from_read_paths(self, make_mem):
        """Regression (review): decay archival must fire from production read
        paths (recall/search/load_summary), not only when called directly."""
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "cold", "cold", "stale fact")
        entry = _reload(mem, "cold")
        entry.last_accessed_at = clock.now - timedelta(days=40)
        mem._write_entry(entry)

        # recall triggers run_decay_if_due → archives the cold memory
        result = mem.recall()
        assert "No memories" in result
        assert _load_archived(mem, "cold") is not None

    def test_run_decay_throttled_within_interval(self, make_mem):
        """Regression (review): read-path decay is throttled so a busy session
        does not scan the store on every call."""
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "cold", "cold", "stale fact")
        entry = _reload(mem, "cold")
        entry.last_accessed_at = clock.now - timedelta(days=40)
        mem._write_entry(entry)

        mem.recall()  # first read triggers decay → archived
        assert _load_archived(mem, "cold") is not None

        # advance a little (within the 3600s throttle window) and re-save
        # a stale memory; a second read must NOT re-archive prematurely
        clock.advance(seconds=60)
        mem.save("project", "cold2", "cold", "another stale fact")
        entry2 = _reload(mem, "cold2")
        entry2.last_accessed_at = clock.now - timedelta(days=40)
        mem._write_entry(entry2)
        mem.recall()
        # cold2 was just saved (created_at now) so it must still be active;
        # the important assertion is that the throttled run did not error
        assert _reload(mem, "cold2") is not None


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_returns_most_similar_first(self, make_mem):
        mem = make_mem()
        mem.save("feedback", "go-preference", "likes Go", "User prefers Go for backend services.")
        mem.save("feedback", "python-preference", "likes Python", "User prefers Python for scripting.")
        hits = mem.search("user likes the Go programming language", top_k=5)
        assert len(hits) >= 1
        assert hits[0].entry.name == "go-preference"
        assert hits[0].score > 0

    def test_search_respects_top_k(self, make_mem):
        mem = make_mem()
        for i in range(5):
            mem.save("project", f"item{i}", f"item {i}", f"the quick brown fox number {i}")
        hits = mem.search("quick brown fox", top_k=2)
        assert len(hits) == 2

    def test_search_type_filter(self, make_mem):
        mem = make_mem()
        mem.save("user", "role", "role", "backend engineer")
        mem.save("project", "deadline", "deadline", "backend release")
        hits = mem.search("backend", type="user")
        assert all(h.entry.type == "user" for h in hits)
        assert {h.entry.name for h in hits} == {"role"}

    def test_search_scope_isolation_blocks_foreign_scope(self, make_mem):
        mem = make_mem()
        mem.save("project", "secret", "secret", "internal detail")
        assert mem.search("secret", scope="/other/project") == []

    def test_search_touches_last_accessed(self, make_mem):
        clock = Clock(datetime(2026, 8, 2, 12, 0, 0))
        mem = make_mem(clock)
        mem.save("project", "hot", "hot", "data")
        clock.advance(days=10)
        mem.search("data")
        assert _reload(mem, "hot").last_accessed_at == clock.now


# ---------------------------------------------------------------------------
# Global summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_none_when_empty(self, make_mem):
        mem = make_mem()
        assert mem.load_summary() is None

    def test_summary_ranks_by_importance(self, make_mem):
        mem = make_mem()
        mem.save("project", "low", "low importance fact", "x", importance=1)
        mem.save("project", "high", "high importance fact", "y", importance=5)
        summary = mem.load_summary()
        assert summary is not None
        assert summary.index("high: high importance fact") < summary.index("low: low importance fact")

    def test_summary_truncates_to_token_budget(self, make_mem):
        mem = make_mem()
        for i in range(20):
            mem.save("project", f"m{i}", f"memory number {i} with a fairly long description", "body")
        summary = mem.load_summary(max_tokens=50)
        assert summary is not None
        # ~50 tokens (chars/4 heuristic ≈ 200 chars) plus the hint line
        assert len(summary) < 400
        assert "use SearchMemory for details" in summary

    def test_summary_excludes_archived(self, make_mem):
        mem = make_mem()
        mem.save("project", "keep", "keep me", "x")
        mem.save("project", "drop", "drop me", "y")
        mem.archive("drop", reason="test")
        summary = mem.load_summary()
        assert summary is not None
        assert "keep" in summary
        assert "drop" not in summary


# ---------------------------------------------------------------------------
# Write-time judgment application (dedup)
# ---------------------------------------------------------------------------


class TestApplyJudgment:
    def test_new_creates_new_entry(self, make_mem):
        mem = make_mem()
        result = mem.apply_judgment(
            "user", "fresh", "new fact", "brand new body", Judgment("new")
        )
        assert "saved" in result
        assert _reload(mem, "fresh") is not None

    def test_update_replaces_target(self, make_mem):
        mem = make_mem()
        mem.save("user", "role", "v1", "Old content.")
        result = mem.apply_judgment(
            "user", "incoming", "v2", "New content.", Judgment("update", target_name="role", reason="supersedes")
        )
        assert "updated" in result
        entry = _reload(mem, "role")
        assert entry.body == "New content."
        # no new file for the incoming name
        assert _reload(mem, "incoming") is None
        changelog = (mem.memory_dir / "changelog.md").read_text()
        assert "update role" in changelog

    def test_supplement_appends_to_target(self, make_mem):
        mem = make_mem()
        mem.save("user", "prefs", "prefs", "Likes Go.")
        result = mem.apply_judgment(
            "user", "incoming", "prefs", "Also likes Python.",
            Judgment("supplement", target_name="prefs", reason="adds detail"),
        )
        assert "supplemented" in result
        entry = _reload(mem, "prefs")
        assert "Likes Go." in entry.body
        assert "Also likes Python." in entry.body
        assert _reload(mem, "incoming") is None

    def test_conflict_keeps_both_and_marks(self, make_mem):
        mem = make_mem()
        mem.save("project", "deadline-a", "release", "Release in August.")
        result = mem.apply_judgment(
            "project", "deadline-b", "release", "Release in December.",
            Judgment("conflict", target_name="deadline-a", reason="contradicts"),
        )
        assert "conflict marked" in result
        a = _reload(mem, "deadline-a")
        b = _reload(mem, "deadline-b")
        assert b is not None  # incoming kept
        assert "deadline-b" in a.conflict_with
        assert "deadline-a" in b.conflict_with
        changelog = (mem.memory_dir / "changelog.md").read_text()
        assert "conflict" in changelog

    def test_supplement_falls_back_when_target_missing(self, make_mem):
        mem = make_mem()
        result = mem.apply_judgment(
            "user", "fresh", "x", "y", Judgment("supplement", target_name="ghost")
        )
        assert "saved" in result
        assert _reload(mem, "fresh") is not None
