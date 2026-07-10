from __future__ import annotations

import hashlib
import re


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_]+")


def sanitize_mcp_name(value: str) -> str:
    sanitized = _SAFE_NAME_RE.sub("_", value).strip("_")
    if not sanitized:
        return "unnamed"
    if sanitized[0].isdigit():
        return f"_{sanitized}"
    return sanitized


def mcp_tool_callable_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{sanitize_mcp_name(server_name)}__{sanitize_mcp_name(tool_name)}"


def mcp_prompt_callable_name(server_name: str, prompt_name: str) -> str:
    return f"mcp__{sanitize_mcp_name(server_name)}__prompt__{sanitize_mcp_name(prompt_name)}"


def mcp_resource_callable_name(server_name: str, uri: str) -> str:
    digest = hashlib.sha1(uri.encode("utf-8")).hexdigest()[:8]
    return f"mcp__{sanitize_mcp_name(server_name)}__resource__{digest}"


def ensure_unique_name(name: str, raw_identity: str, used: set[str]) -> str:
    if name not in used:
        used.add(name)
        return name
    digest = hashlib.sha1(raw_identity.encode("utf-8")).hexdigest()[:8]
    candidate = f"{name}_{digest}"
    counter = 2
    while candidate in used:
        candidate = f"{name}_{digest}_{counter}"
        counter += 1
    used.add(candidate)
    return candidate
