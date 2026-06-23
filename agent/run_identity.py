from __future__ import annotations

import uuid


def new_session_id() -> str:
    return uuid.uuid4().hex[:12]


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]
