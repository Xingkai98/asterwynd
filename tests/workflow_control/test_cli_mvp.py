from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from typer.testing import CliRunner

import agent.main as cli
from workflow_control import (
    EnforcementLevel,
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
            "--enforcement-level",
            "prompt_adapter",
            "--json",
        ],
    )
    assert report.exit_code == 0
    assert json.loads(report.stdout)["state"] == {
        "phase": "requirements",
        "sub_state": "drafting",
    }
    event = SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path)).list_events("workflow-1")[-1]
    assert event.work_result is not None
    assert event.work_result.enforcement_level == EnforcementLevel.PROMPT_ADAPTER

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


def test_workflow_chat_fake_executor_reaches_done_end_to_end(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    repo = _init_repo(tmp_path / "repo")
    worktrees_root = tmp_path / "worktrees"
    runner = CliRunner()
    workflow_id = "workflow-e2e"
    change_id = "change-e2e"
    base_args = [
        "workflow",
        "chat",
        "--workflow",
        workflow_id,
        "--db",
        str(db_path),
        "--executor",
        "fake",
        "--change-id",
        change_id,
        "--date",
        "2026-07-15",
        "--repo",
        str(repo),
        "--worktrees-root",
        str(worktrees_root),
        "--allow-local-base",
        "--json",
    ]

    first = runner.invoke(cli.app, [*base_args, "--message", "start"])
    assert first.exit_code == 0
    assert json.loads(first.stdout)["state"] == {
        "phase": "requirements",
        "sub_state": "ready_for_review",
    }

    monkeypatch.setenv("ASTERWYND_WORKFLOW_TRUSTED_HOST", "1")
    expected_states = [
        {"phase": "design", "sub_state": "ready_for_review"},
        {"phase": "building", "sub_state": "ready_for_review"},
        {"phase": "code-review", "sub_state": "ready_for_review"},
        {"phase": "closing", "sub_state": "ready_for_review"},
        {"phase": "done", "sub_state": "done"},
    ]
    for expected_state in expected_states:
        result = runner.invoke(cli.app, [*base_args, "--message", "ok"])
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["state"] == expected_state
        assert payload["enforcement_level"] == "strict_host"

    assert not (worktrees_root / change_id).exists()


def test_workflow_chat_command_executor_requires_existing_worktree(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "workflow",
            "chat",
            "--workflow",
            "command-workflow",
            "--db",
            str(db_path),
            "--executor",
            "command",
            "--executor-command",
            "python3",
            "--executor-arg",
            "-c",
            "--executor-arg",
            "print('command executor done')",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "requires an existing dedicated worktree" in result.stderr


def test_workflow_chat_command_executor_reports_strict_host_result(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    repo = _init_repo(tmp_path / "repo")
    worktrees_root = tmp_path / "worktrees"
    change_id = "command-change"
    workspace = worktrees_root / change_id
    worktrees_root.mkdir()
    _git(repo, "worktree", "add", "-b", f"{change_id}/2026-07-15", str(workspace))
    runner = CliRunner()
    monkeypatch.setenv("ASTERWYND_WORKFLOW_TRUSTED_HOST", "1")

    result = runner.invoke(
        cli.app,
        [
            "workflow",
            "chat",
            "--workflow",
            "command-workflow",
            "--db",
            str(db_path),
            "--executor",
            "command",
            "--executor-command",
            "python3",
            "--executor-arg",
            "-c",
            "--executor-arg",
            "import os; print(os.getcwd() + '|' + os.environ.get('ASTERWYND_WORKFLOW_AGENT_CONTEXT', '') + '|' + str(os.environ.get('ASTERWYND_WORKFLOW_TRUSTED_HOST')))",
            "--repo",
            str(repo),
            "--worktrees-root",
            str(worktrees_root),
            "--change-id",
            change_id,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == {"phase": "requirements", "sub_state": "drafting"}
    assert payload["summary"] == f"{workspace}|1|None"
    event = SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path)).list_events("command-workflow")[-1]
    assert event.work_result is not None
    assert event.work_result.enforcement_level == EnforcementLevel.STRICT_HOST


def test_workflow_chat_command_executor_blocks_on_failure(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    repo = _init_repo(tmp_path / "repo")
    worktrees_root = tmp_path / "worktrees"
    change_id = "failing-command-change"
    workspace = worktrees_root / change_id
    worktrees_root.mkdir()
    _git(repo, "worktree", "add", "-b", f"{change_id}/2026-07-15", str(workspace))
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "workflow",
            "chat",
            "--workflow",
            "failing-command-workflow",
            "--db",
            str(db_path),
            "--executor",
            "command",
            "--executor-command",
            "python3",
            "--executor-arg",
            "-c",
            "--executor-arg",
            "import sys; print('boom'); sys.exit(2)",
            "--repo",
            str(repo),
            "--worktrees-root",
            str(worktrees_root),
            "--change-id",
            change_id,
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["state"] == {"phase": "blocked", "sub_state": "blocked"}
    event = SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path)).list_events("failing-command-workflow")[-1]
    assert event.work_result is not None
    assert event.work_result.summary == "executor command failed: boom"


def test_workflow_chat_bypasses_unmanaged_roots_without_starting_workflow(tmp_path) -> None:
    db_path = tmp_path / "workflow.sqlite3"
    roots_file = tmp_path / "roots.json"
    managed = tmp_path / "managed"
    unmanaged = tmp_path / "unmanaged"
    managed.mkdir()
    unmanaged.mkdir()
    runner = CliRunner()
    runner.invoke(cli.app, ["workflow", "manage", "add", str(managed), "--roots-file", str(roots_file)])

    result = runner.invoke(
        cli.app,
        [
            "workflow",
            "chat",
            "--workflow",
            "workflow-1",
            "--db",
            str(db_path),
            "--cwd",
            str(unmanaged),
            "--roots-file",
            str(roots_file),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["bypassed"] is True
    assert SQLiteEventStore(SQLiteEventStoreConfig(db_path=db_path)).list_workflow_ids() == []


def test_workflow_attach_and_prompt_adapter_show_contract(tmp_path) -> None:
    runner = CliRunner()
    root = tmp_path / "repo"
    root.mkdir()
    roots_file = tmp_path / "roots.json"

    attached = runner.invoke(
        cli.app,
        [
            "workflow",
            "attach",
            str(root),
            "--cwd",
            str(root),
            "--session-id",
            "session-1",
            "--roots-file",
            str(roots_file),
            "--json",
        ],
    )
    assert attached.exit_code == 0
    assert json.loads(attached.stdout)["workflow_prompt_enabled"] is True

    adapter = runner.invoke(cli.app, ["workflow", "prompt-adapter", "show", "--json"])
    assert adapter.exit_code == 0
    adapter_payload = json.loads(adapter.stdout)
    assert adapter_payload["enforcement_level"] == "prompt_adapter"
    assert adapter_payload["approval_capability"] is False
    assert adapter_payload["status_command"] == "asterwynd workflow status --workflow <id>"


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "README.md").write_text("# repo\n", encoding="utf-8")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")
    return path


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
