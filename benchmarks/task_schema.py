from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TaskSpec:
    id: str
    repo: str
    base_commit: str
    problem_statement_file: str
    test_command: str
    timeout_seconds: int = 300
    gold_patch_file: str | None = None
    test_patch_file: str | None = None
    hints_text: str | None = None
    category: str | None = None
    difficulty: str | None = None
    external_repo: str | None = None  # e.g. "https://github.com/psf/requests.git"
    version: str | None = None  # SWE-bench version key for MAP_REPO_VERSION_TO_SPECS lookup

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        required = (
            "id",
            "repo",
            "base_commit",
            "problem_statement_file",
            "test_command",
        )
        missing = [field for field in required if field not in data]
        if missing:
            raise ValueError(f"Missing required task fields: {', '.join(missing)}")
        task = cls(
            id=data["id"],
            repo=data["repo"],
            base_commit=data["base_commit"],
            problem_statement_file=data["problem_statement_file"],
            test_command=data["test_command"],
            timeout_seconds=data.get("timeout_seconds", 300),
            gold_patch_file=data.get("gold_patch_file"),
            test_patch_file=data.get("test_patch_file"),
            hints_text=data.get("hints_text"),
            category=data.get("category"),
            difficulty=data.get("difficulty"),
            external_repo=data.get("external_repo"),
            version=data.get("version"),
        )
        task.validate()
        return task

    def validate(self) -> None:
        if not self.id:
            raise ValueError("Task id must not be empty")
        if not isinstance(self.timeout_seconds, int) or self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive integer")


@dataclass(frozen=True)
class LoadedTask:
    task: TaskSpec
    task_dir: Path
    problem_statement: str
    gold_patch_path: Path | None = None
    test_patch_path: Path | None = None


def load_task(task_dir: str | Path) -> LoadedTask:
    root = Path(task_dir).resolve()
    task_json = root / "task.json"
    if not task_json.exists():
        raise FileNotFoundError(f"task.json not found in {root}")

    task = TaskSpec.from_dict(json.loads(task_json.read_text()))
    problem_path = _resolve_task_file(root, task.problem_statement_file)
    if not problem_path.exists():
        raise FileNotFoundError(f"Problem statement file not found: {problem_path}")

    gold_patch_path = _optional_task_file(root, task.gold_patch_file)
    test_patch_path = _optional_task_file(root, task.test_patch_file)
    return LoadedTask(
        task=task,
        task_dir=root,
        problem_statement=problem_path.read_text(errors="replace"),
        gold_patch_path=gold_patch_path,
        test_patch_path=test_patch_path,
    )


def _optional_task_file(root: Path, filename: str | None) -> Path | None:
    if not filename:
        return None
    path = _resolve_task_file(root, filename)
    return path if path.exists() else None


def _resolve_task_file(root: Path, filename: str) -> Path:
    path = (root / filename).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Task file escapes task directory: {filename}") from exc
    return path

