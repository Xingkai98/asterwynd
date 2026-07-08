"""TUI slash command suggestions and filtering.

Pure helpers with no Textual dependency.
"""

from __future__ import annotations

from typing import Any


def filter_commands_by_prefix(
    catalog: list[dict[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    """Filter a slash command catalog by the current input prefix.

    Args:
        catalog: Output from SlashCommandRegistry.catalog().
        prefix: Current input prefix, with or without the leading slash.

    Returns:
        Matching catalog entries.
    """
    search = prefix.lstrip("/").lower()
    if not search:
        return list(catalog)

    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    for cmd in catalog:
        name = str(cmd.get("name", "")).lower()
        aliases = [str(a).lower() for a in cmd.get("aliases", [])]

        if name.startswith(search) or any(a.startswith(search) for a in aliases):
            if name not in seen:
                seen.add(name)
                results.append(cmd)

    return results


def strip_command_prefix(text: str) -> tuple[str, str]:
    """Extract command name and arguments from a slash command input.

    Returns:
        A tuple of command name without slash and the remaining argument text.
    """
    stripped = text.strip()
    if not stripped.startswith("/"):
        return "", ""
    without_slash = stripped[1:]
    parts = without_slash.split(maxsplit=1)
    command_name = parts[0].lower()
    remainder = parts[1] if len(parts) > 1 else ""
    return command_name, remainder
