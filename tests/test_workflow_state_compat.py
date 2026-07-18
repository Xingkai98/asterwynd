from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_workflow_state_advance_is_read_only_compat(tmp_path) -> None:
    change_dir = tmp_path / "openspec" / "changes" / "change-1"
    change_dir.mkdir(parents=True)
    (change_dir / "handoff.json").write_text(
        json.dumps(
            {
                "change_id": "change-1",
                "state": {"phase": "building", "sub_state": "implementing"},
                "transitions": [],
            },
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "workflow_state.py"),
            "advance",
            "--change",
            "change-1",
            "--to",
            "ready_for_review",
        ],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        check=False,
    )

    assert result.returncode == 2
    assert "只读兼容入口" in result.stderr
    data = json.loads((change_dir / "handoff.json").read_text(encoding="utf-8"))
    assert data["state"]["sub_state"] == "implementing"
