import pytest

from agent.workspace_policy import WorkspacePolicy


def test_workspace_policy_allows_path_inside_root(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    target = tmp_path / "src" / "app.py"

    assert policy.assert_write_allowed(target) == target.resolve()


def test_workspace_policy_rejects_path_traversal(tmp_path):
    policy = WorkspacePolicy(tmp_path)

    with pytest.raises(PermissionError, match="outside workspace"):
        policy.assert_write_allowed(tmp_path / ".." / "outside.txt")


@pytest.mark.parametrize(
    "path",
    [
        ".git/config",
        ".env",
        ".env.local",
        "secret.pem",
        "id_rsa",
        "__pycache__/x.pyc",
        "node_modules/pkg/index.js",
        "benchmarks/runs/run/result.json",
    ],
)
def test_workspace_policy_rejects_denied_writes(tmp_path, path):
    policy = WorkspacePolicy(tmp_path)

    with pytest.raises(PermissionError):
        policy.assert_write_allowed(path)


def test_workspace_policy_allows_reads_inside_root_even_for_task_files(tmp_path):
    policy = WorkspacePolicy(tmp_path)
    path = tmp_path / "benchmarks" / "tasks" / "task.json"

    assert policy.assert_read_allowed(path) == path.resolve()

