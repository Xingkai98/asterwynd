"""Duration string parsing utilities.

The :func:`parse_duration` function converts human-readable duration strings
such as ``"1h30m"``, ``"45s"``, ``"2m"`` and ``"1h"`` into a total number of
seconds as an integer.
"""

from __future__ import annotations

import re

__all__ = ["parse_duration"]

#: Seconds contributed by one unit of each supported suffix.
_UNIT_SECONDS = {
    "h": 3600,
    "m": 60,
    "s": 1,
}

# Strict full-match pattern. Each unit may appear at most once and the
# components must appear in the canonical order hours -> minutes -> seconds.
# The leading ``(?!$)`` guarantees the string is not empty.
_DURATION_RE = re.compile(r"^(?!$)(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def parse_duration(s: str) -> int:
    """Parse a duration string into a total number of seconds.

    Supported format is an ordered, non-repeating combination of the ``h``,
    ``m`` and ``s`` units, each preceded by a non-negative integer, e.g.
    ``"1h30m"``, ``"45s"``, ``"2m"``, ``"1h"``, ``"1h2m3s"``.

    The input is validated strictly: an empty string, an unknown unit, a
    negative value, a repeated unit, a missing unit, or any stray/whitespace
    character raises :class:`ValueError`.

    Returns the total number of seconds as an :class:`int`.
    """

    if not isinstance(s, str):
        raise ValueError(
            f"duration must be a string, got {type(s).__name__}"
        )

    if not s:
        raise ValueError("duration string must not be empty")

    match = _DURATION_RE.fullmatch(s)
    if match is None:
        raise ValueError(f"invalid duration string: {s!r}")

    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)

    return hours * _UNIT_SECONDS["h"] + minutes * _UNIT_SECONDS["m"] + seconds * _UNIT_SECONDS["s"]
