from agent.code_intelligence.repo_map import build_repo_map, format_repo_map
from agent.workspace_policy import WorkspacePolicy


def test_build_repo_map_scans_python_files_and_skips_denied_paths(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "service.py").write_text(
        "import os\n\nclass Service:\n    def run(self):\n        pass\n"
    )
    (tmp_path / ".env").write_text("SECRET=value")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n")

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path))

    paths = [entry.path for entry in repo_map.files]
    assert paths == ["pkg/service.py"]
    assert "Service" in [symbol.name for symbol in repo_map.files[0].symbols]
    assert ".env" not in format_repo_map(repo_map)
    assert ".git" not in format_repo_map(repo_map)


def test_build_repo_map_keeps_non_python_file_entries_without_fake_symbols(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export function run() {}\n")
    (tmp_path / "README.md").write_text("# Project\n")

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path))

    entries = {entry.path: entry for entry in repo_map.files}
    assert entries["src/app.ts"].language == "typescript"
    assert entries["src/app.ts"].category == "source"
    assert entries["src/app.ts"].symbols == []
    assert entries["README.md"].language == "markdown"
    assert entries["README.md"].category == "docs"


def test_build_repo_map_respects_custom_ignore_patterns(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("def app():\n    pass\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "client.py").write_text("def client():\n    pass\n")

    repo_map = build_repo_map(
        policy=WorkspacePolicy(tmp_path),
        ignore_patterns=("generated",),
    )

    assert [entry.path for entry in repo_map.files] == ["src/app.py"]


def test_format_repo_map_marks_file_truncation(tmp_path):
    for index in range(3):
        (tmp_path / f"file_{index}.py").write_text(f"def func_{index}():\n    pass\n")

    repo_map = build_repo_map(policy=WorkspacePolicy(tmp_path), max_files=2)
    output = format_repo_map(repo_map)

    assert "file_0.py" in output
    assert "file_1.py" in output
    assert "file_2.py" not in output
    assert "... truncated, showing first 2 files" in output
