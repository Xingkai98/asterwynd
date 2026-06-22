import pytest

from agent.planning import PlanningManager


def test_set_plan_creates_pending_items_with_stable_ids():
    manager = PlanningManager()

    snapshot = manager.set_plan(["Read docs", "Implement manager"])

    assert snapshot["items"] == [
        {"id": "item-1", "content": "Read docs", "status": "pending", "note": None},
        {"id": "item-2", "content": "Implement manager", "status": "pending", "note": None},
    ]
    assert snapshot["summary"]["total"] == 2
    assert snapshot["summary"]["pending"] == 2
    assert snapshot["summary"]["current_item"] is None


def test_set_plan_replaces_items_without_reusing_ids():
    manager = PlanningManager()
    manager.set_plan(["First"])

    snapshot = manager.set_plan(["Replacement"])

    assert snapshot["items"][0]["id"] == "item-2"
    assert snapshot["items"][0]["content"] == "Replacement"


def test_update_item_status_and_note():
    manager = PlanningManager()
    manager.set_plan(["Run tests"])

    snapshot = manager.update_item("item-1", "failed", note="pytest failed")

    assert snapshot["items"][0]["status"] == "failed"
    assert snapshot["items"][0]["note"] == "pytest failed"
    assert snapshot["summary"]["failed"] == 1


def test_allows_retrying_failed_item():
    manager = PlanningManager()
    manager.set_plan(["Run tests"])
    manager.update_item("item-1", "failed", note="pytest failed")

    snapshot = manager.update_item("item-1", "in_progress", note="retrying")

    assert snapshot["items"][0]["status"] == "in_progress"
    assert snapshot["items"][0]["note"] == "retrying"
    assert snapshot["summary"]["current_item"]["id"] == "item-1"


def test_rejects_multiple_in_progress_items():
    manager = PlanningManager()
    manager.set_plan(["One", "Two"])
    manager.update_item("item-1", "in_progress")

    with pytest.raises(ValueError, match="only one in_progress"):
        manager.update_item("item-2", "in_progress")


def test_rejects_unknown_status_and_item_id():
    manager = PlanningManager()
    manager.set_plan(["One"])

    with pytest.raises(ValueError, match="unknown plan item"):
        manager.update_item("missing", "completed")

    with pytest.raises(ValueError, match="invalid plan status"):
        manager.update_item("item-1", "blocked")


def test_rejects_empty_content():
    manager = PlanningManager()

    with pytest.raises(ValueError, match="content must not be empty"):
        manager.set_plan([" "])


def test_render_context_only_when_plan_exists():
    manager = PlanningManager()
    assert manager.render_context() == ""

    manager.set_plan(["Read docs"])
    manager.update_item("item-1", "completed")

    assert manager.render_context() == (
        "Current structured planning state:\n"
        "- [completed] Read docs"
    )
