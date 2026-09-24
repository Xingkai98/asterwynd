from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORKFLOW_METHODS_PATH = "scripts/workflow_methods.json"


def _get_workflow_methods_path(repo_root: str | Path = ".") -> Path:
    return Path(repo_root) / WORKFLOW_METHODS_PATH


def load_workflow_methods(repo_root: str | Path = ".") -> dict[str, Any]:
    """Load workflow_methods.json from the repository root."""
    methods_path = _get_workflow_methods_path(repo_root)
    try:
        if methods_path.exists():
            loaded = json.loads(methods_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def is_workflow_enabled(repo_root: str | Path = ".") -> bool:
    """Return whether the workflow automation is enabled."""
    methods = load_workflow_methods(repo_root)
    workflow = methods.get("workflow", {})
    if not isinstance(workflow, dict):
        return True
    return workflow.get("enabled", True) is not False
