"""Shared brand copy and terminal banner rendering."""
from __future__ import annotations

import shutil
from importlib import resources

BRAND_NAME = "Asterwynd"
SLOGAN_EN = "Navigate by stars. Prove with traces."
SLOGAN_ZH = "以星为引，变更有证。"

_WIDE_MIN_COLUMNS = 92


def render_tui_banner(*, columns: int | None = None) -> str:
    """Return the startup banner for an interactive terminal."""
    if columns is None:
        columns = shutil.get_terminal_size(fallback=(100, 24)).columns

    asset_name = "asterwynd-wordmark.txt"
    if columns < _WIDE_MIN_COLUMNS:
        asset_name = "asterwynd-wordmark-compact.txt"

    wordmark = resources.files("agent.assets").joinpath(asset_name).read_text(
        encoding="utf-8"
    ).rstrip()
    return f"{wordmark}\n\n{SLOGAN_EN}\n{SLOGAN_ZH}"
