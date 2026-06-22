import json

from agent.trace_recorder import TraceRecorder


def test_trace_recorder_records_required_step_types(tmp_path):
    recorder = TraceRecorder(task_id="task-1")
    recorder.record_tool_call("Edit", {"path": "app.py"})
    recorder.record_edit("app.py", "ok", "1 replacement")
    recorder.record_diff(str(tmp_path / "final.diff"), "1 file changed")
    recorder.record_test("pytest -q", 0, 12.2, "1 passed")

    data = recorder.to_dict()
    assert [step["type"] for step in data["steps"]] == [
        "tool_call",
        "edit",
        "diff",
        "test",
    ]


def test_trace_recorder_preserves_full_observation():
    recorder = TraceRecorder(task_id="task-1")
    long_output = "x" * 1000
    recorder.record_tool_result("Bash", "ok", 1, long_output)

    output = recorder.to_dict()["steps"][0]["data"]["observation"]
    assert len(output) == 1000
    assert output == long_output


def test_trace_recorder_writes_json(tmp_path):
    recorder = TraceRecorder(task_id="task-1")
    recorder.record_completion("passed")
    path = tmp_path / "trace.json"

    recorder.write_to_file(path)

    assert json.loads(path.read_text())["task_id"] == "task-1"


def test_trace_recorder_records_mode_metadata_and_run_started():
    recorder = TraceRecorder(task_id="task-1", mode="read_only")
    recorder.record_run_started()

    data = recorder.to_dict()

    assert data["mode"] == "read_only"
    assert data["steps"][0]["type"] == "run_started"
    assert data["steps"][0]["data"]["mode"] == "read_only"
