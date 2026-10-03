"""Duration string parsing utilities.

The :func:`parse_duration` function converts a compact duration string such
as ``"1h30m"`` into a whole number of seconds, rejecting any input that does
not strictly match the supported grammar.
"""

import re

__all__ = ["parse_duration"]

# Seconds contributed by each supported unit.
_UNIT_SECONDS = {"h": 3600, "m": 60, "s": 1}

# A non-negative integer without leading zeros: "0" or a digit 1-9 followed
# by any number of digits.
_NUMBER = r"(?:0|[1-9]\d*)"

# Zero or one group per unit, strictly ordered h -> m -> s.  Anchoring is
# provided by `fullmatch`, so the pattern itself carries no `^`/`$`.
_PATTERN = re.compile(
    rf"(?:(?P<h>{_NUMBER})h)?(?:(?P<m>{_NUMBER})m)?(?:(?P<s>{_NUMBER})s)?"
)


def parse_duration(s: str) -> int:
    """Parse a compact duration string into a whole number of seconds.

    Accepted grammar (strictly):

    * one optional ``<digits>h`` group, then
    * one optional ``<digits>m`` group, then
    * one optional ``<digits>s`` group,

    with no whitespace, signs, separators, or other units in between.  At
    least one group must be present.  Each ``<digits>`` is a non-negative
    integer with no leading zeros (``"0"`` alone is allowed, ``"00"`` or
    ``"01"`` are not).

    Examples::

        parse_duration("1h30m") == 5400
        parse_duration("90s") == 90
        parse_duration("1h") == 3600
        parse_duration("0s") == 0

    Args:
        s: The duration string to parse.

    Returns:
        The duration expressed in whole seconds.

    Raises:
        ValueError: If ``s`` is not a string, is empty, or does not match the
            grammar above (e.g. ``"30"``, ``"30m1h"``, ``"1.5h"``, ``"1h 30m"``,
            ``"01h"``, ``"1d"``).
    """
    if not isinstance(s, str):
        raise ValueError(
            f"duration must be a string, got {type(s).__name__!r}"
        )
    if s == "":
        raise ValueError("duration must not be empty")

    match = _PATTERN.fullmatch(s)
    if match is None or not any(match.groups()):
        raise ValueError(
            f"invalid duration {s!r}: expected '<digits>h<digits>m<digits>s' "
            f"with at least one unit and numbers without leading zeros "
            f"(e.g. '1h30m')"
        )

    return (
        int(match.group("h") or 0) * _UNIT_SECONDS["h"]
        + int(match.group("m") or 0) * _UNIT_SECONDS["m"]
        + int(match.group("s") or 0) * _UNIT_SECONDS["s"]
    )
