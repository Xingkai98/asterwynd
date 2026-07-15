from __future__ import annotations

import json

from workflow_control import (
    StateSnapshot,
    WorkflowSnapshot,
    export_handoff_compat,
    import_handoff_read_only,
)


def test_import_handoff_read_only_supports_legacy_shape(tmp_path) -> None:
    path = tmp_path / "handoff.json"
    path.write_text(
        json.dumps(
            {
                "change_id": "change-1",
                "state": {"phase": "building", "sub_state": "implementing"},
            },
        ),
        encoding="utf-8",
    )

    snapshot = import_handoff_read_only(path)

    assert snapshot.change_id == "change-1"
    assert snapshot.phase == "building"
    assert snapshot.sub_state == "implementing"


def test_export_handoff_compat_marks_event_store_as_source_of_truth() -> None:
    payload = export_handoff_compat(
        WorkflowSnapshot(
            workflow_id="change-1",
            state=StateSnapshot(phase="building", sub_state="implementing"),
            version=7,
            events_seen=7,
        ),
    )

    assert payload["change_id"] == "change-1"
    assert payload["source_of_truth"] == "workflow_control_event_store"
    assert payload["compatibility"] == "read_only_export"
