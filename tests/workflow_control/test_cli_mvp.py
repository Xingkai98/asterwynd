from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

from typer.testing import CliRunner

import agent.main as cli
from workflow_control import (
    SQLiteEventStore,
    SQLiteEventStoreConfig,
    default_coding_agent_template,
    start_workflow,
)


def test_workflow_cli_enter_status_report_and_gate_approve(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    runner = CliRunner()

    enter = runner.invoke(
        cli.app,
        ["workflow", "enter", "--workflow", "workflow-1", "--db", str(db_path), "--json"],
    )
    assert enter.exit_code == 0
    enter_data = json.loads(enter.stdout)
    assert enter_data["state"] == {"phase": "exploring", "sub_state": "chatting"}
    assert enter_data["work_item"]["work_item_id"] == "workflow-1:1"
    assert enter_data["waiting_for_human"] is False

    report = runner.invoke(
        cli.app,
        [
            "workflow",
            "report",
            "--workflow",
            "workflow-1",
            "--db",
            str(db_path),
            "--work-item-id",
            "workflow-1:1",
            "--expected-version",
            "1",
            "--summary",
            "drafted goal",
            "--json",
        ],
    )
    assert report.exit_code == 0
    assert json.loads(report.stdout)["state"] == {
        "phase": "requirements",
        "sub_state": "drafting",
    }

    status = runner.invoke(
        cli.app,
        ["workflow", "status", "--workflow", "workflow-1", "--db", str(db_path), "--json"],
    )
    assert status.exit_code == 0
    assert json.loads(status.stdout)["state"] == {
        "phase": "requirements",
        "sub_state": "drafting",
    }

    second_report = runner.invoke(
        cli.app,
        [
            "workflow",
            "report",
            "--workflow",
            "workflow-1",
            "--db",
            str(db_path),
            "--work-item-id",
            "workflow-1:2",
            "--expected-version",
            "2",
            "--summary",
            "requirements ready",
            "--json",
        ],
    )
    assert second_report.exit_code == 0
    assert json.loads(second_report.stdout)["state"] == {
        "phase": "requirements",
        "sub_state": "ready_for_review",
    }

    at_gate = runner.invoke(
        cli.app,
        ["workflow", "enter", "--workflow", "workflow-1", "--db", str(db_path), "--json"],
    )
    assert at_gate.exit_code == 0
    assert json.loads(at_gate.stdout)["waiting_for_human"] is True

    monkeypatch.setenv("ASTERWYND_WORKFLOW_TRUSTED_HOST", "1")
    approval = runner.invoke(
        cli.app,
        [
            "workflow",
            "gate",
            "approve",
            "--workflow",
            "workflow-1",
            "--db",
            str(db_path),
            "--user",
            "human",
            "--message",
            "ok",
            "--json",
        ],
    )
    assert approval.exit_code == 0
    assert json.loads(approval.stdout)["state"] == {
        "phase": "design",
        "sub_state": "writing_design",
    }


def test_workflow_manage_roots_add_list_remove(tmp_path) -> None:
    roots_path = tmp_path / "roots.json"
    root = tmp_path / "repo"
    root.mkdir()
    runner = CliRunner()

    add = runner.invoke(
        cli.app,
        ["workflow", "manage", "add", str(root), "--roots-file", str(roots_path), "--json"],
    )
    assert add.exit_code == 0
    assert json.loads(add.stdout)["managed_roots"] == [str(root.resolve())]

    listed = runner.invoke(
        cli.app,
        ["workflow", "manage", "list", "--roots-file", str(roots_path), "--json"],
    )
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["managed_roots"] == [str(root.resolve())]

    removed = runner.invoke(
        cli.app,
        ["workflow", "manage", "remove", str(root), "--roots-file", str(roots_path), "--json"],
    )
    assert removed.exit_code == 0
    assert json.loads(removed.stdout)["managed_roots"] == []


def test_workflow_cli_status_runs_lazy_aging_scan(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    workflow_id = "stale-exploration"
    template = default_coding_agent_template()
    store = SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path))
    store.append(
        workflow_id,
        replace(
            start_workflow(workflow_id, template),
            occurred_at=datetime.now(timezone.utc) - timedelta(days=2),
        ),
        expected_version=0,
    )

    result = CliRunner().invoke(
        cli.app,
        ["workflow", "status", "--workflow", workflow_id, "--db", str(db_path), "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["state"] == {
        "phase": "abandoned",
        "sub_state": "abandoned",
    }
