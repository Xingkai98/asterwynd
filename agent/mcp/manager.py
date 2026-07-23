from __future__ import annotations

import asyncio
import json
import os
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from pydantic import AnyUrl

from agent.config import AsterwyndConfig, McpServerConfig
from agent.mcp.naming import (
    ensure_unique_name,
    mcp_prompt_callable_name,
    mcp_resource_callable_name,
    mcp_tool_callable_name,
)
from agent.mcp.types import (
    DEFAULT_MCP_PERMISSION,
    McpActionKind,
    McpPromptMetadata,
    McpResourceMetadata,
    McpServerStatus,
    McpToolMetadata,
)
from agent.tool_permissions import ToolPermission


class McpManager:
    def __init__(self) -> None:
        self._exit_stack = AsyncExitStack()
        self._sessions: dict[str, ClientSession] = {}
        self._server_configs: dict[str, McpServerConfig] = {}
        self._statuses: dict[str, McpServerStatus] = {}
        self._tools: dict[str, McpToolMetadata] = {}
        self._prompts: dict[tuple[str, str], McpPromptMetadata] = {}
        self._resources: dict[tuple[str, str], McpResourceMetadata] = {}

    @property
    def tools(self) -> list[McpToolMetadata]:
        return list(self._tools.values())

    @property
    def prompts(self) -> list[McpPromptMetadata]:
        return list(self._prompts.values())

    @property
    def resources(self) -> list[McpResourceMetadata]:
        return list(self._resources.values())

    def status(self) -> list[McpServerStatus]:
        return [self._statuses[name] for name in sorted(self._statuses)]

    def get_prompt_permission(self, server_name: str, prompt_name: str) -> ToolPermission:
        return self._prompts[(server_name, prompt_name)].permission

    def get_resource_permission(self, server_name: str, uri: str) -> ToolPermission:
        return self._resources[(server_name, uri)].permission

    async def connect_from_config(self, config: AsterwyndConfig) -> None:
        used_names = {tool.callable_name for tool in self._tools.values()}
        for server_name, server_config in config.mcp.servers.items():
            self._server_configs[server_name] = server_config
            if not server_config.enabled:
                self._statuses[server_name] = McpServerStatus(
                    name=server_name,
                    ready=False,
                    error="disabled",
                )
                continue
            try:
                async with asyncio.timeout(server_config.startup_timeout_seconds):
                    await self._connect_server(server_config, used_names)
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._statuses[server_name] = McpServerStatus(
                    name=server_name,
                    ready=False,
                    error=message,
                )
                if server_config.required:
                    await self.aclose()
                    raise RuntimeError(
                        f"MCP server {server_name!r} failed to start: {message}"
                    ) from exc

    async def _connect_server(
        self,
        server_config: McpServerConfig,
        used_names: set[str],
    ) -> None:
        if server_config.type == "stdio":
            params = StdioServerParameters(
                command=server_config.command or "",
                args=list(server_config.args),
                env=server_config.env or None,
                cwd=server_config.cwd,
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(params)
            )
        else:
            http_client = await self._exit_stack.enter_async_context(
                httpx.AsyncClient(
                    headers=_resolve_headers(server_config),
                    timeout=server_config.tool_timeout_seconds,
                )
            )
            read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
                streamable_http_client(
                    server_config.url or "",
                    http_client=http_client,
                )
            )

        session = await self._exit_stack.enter_async_context(
            ClientSession(
                read_stream,
                write_stream,
                read_timeout_seconds=timedelta(seconds=server_config.tool_timeout_seconds),
            )
        )
        await session.initialize()
        self._sessions[server_config.name] = session

        tools = await _list_or_empty(session.list_tools)
        prompts = await _list_or_empty(session.list_prompts)
        resources = await _list_or_empty(session.list_resources)

        for tool in tools:
            raw_name = str(tool.name)
            callable_name = ensure_unique_name(
                mcp_tool_callable_name(server_config.name, raw_name),
                f"{server_config.name}\0tool\0{raw_name}",
                used_names,
            )
            self._tools[callable_name] = McpToolMetadata(
                server_name=server_config.name,
                tool_name=raw_name,
                callable_name=callable_name,
                description=str(tool.description or ""),
                input_schema=_schema_dict(getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)),
                permission=_permission_for(server_config, McpActionKind.TOOL, raw_name),
            )

        for prompt in prompts:
            raw_name = str(prompt.name)
            self._prompts[(server_config.name, raw_name)] = McpPromptMetadata(
                server_name=server_config.name,
                prompt_name=raw_name,
                callable_name=mcp_prompt_callable_name(server_config.name, raw_name),
                description=str(prompt.description or ""),
                permission=_permission_for(server_config, McpActionKind.PROMPT, raw_name),
            )

        for resource in resources:
            uri = str(resource.uri)
            self._resources[(server_config.name, uri)] = McpResourceMetadata(
                server_name=server_config.name,
                uri=uri,
                callable_name=mcp_resource_callable_name(server_config.name, uri),
                name=str(resource.name or uri),
                description=str(resource.description or ""),
                mime_type=getattr(resource, "mimeType", None) or getattr(resource, "mime_type", None),
                permission=_permission_for(server_config, McpActionKind.RESOURCE, uri),
            )

        self._statuses[server_config.name] = McpServerStatus(
            name=server_config.name,
            ready=True,
            tools=len(tools),
            prompts=len(prompts),
            resources=len(resources),
        )

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        session = self._sessions[server_name]
        server_config = self._server_configs[server_name]
        try:
            result = await asyncio.wait_for(
                session.call_tool(tool_name, arguments or {}),
                timeout=server_config.tool_timeout_seconds,
            )
        except Exception as exc:
            return f"[MCP tool error: {server_name}/{tool_name}: {type(exc).__name__}: {exc}]"
        return _format_call_tool_result(result)

    async def get_prompt(
        self,
        server_name: str,
        prompt_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> str:
        session = self._sessions[server_name]
        server_config = self._server_configs[server_name]
        result = await asyncio.wait_for(
            session.get_prompt(prompt_name, _string_arguments(arguments or {})),
            timeout=server_config.tool_timeout_seconds,
        )
        return _format_prompt_result(server_name, prompt_name, arguments or {}, result)

    async def read_resource(self, server_name: str, uri: str) -> str:
        session = self._sessions[server_name]
        server_config = self._server_configs[server_name]
        result = await asyncio.wait_for(
            session.read_resource(AnyUrl(uri)),
            timeout=server_config.tool_timeout_seconds,
        )
        return _format_resource_result(server_name, uri, result)

    async def aclose(self) -> None:
        await self._exit_stack.aclose()


async def build_mcp_manager(config: AsterwyndConfig) -> McpManager:
    manager = McpManager()
    await manager.connect_from_config(config)
    return manager


def _resolve_headers(server_config: McpServerConfig) -> dict[str, str]:
    headers: dict[str, str] = {}
    for name, value in server_config.headers.items():
        if value.value is not None:
            headers[name] = value.value
        elif value.env is not None:
            headers[name] = os.environ.get(value.env, "")
    return headers


async def _list_or_empty(list_fn):
    try:
        result = await list_fn()
    except Exception:
        return []
    if hasattr(result, "tools"):
        return result.tools
    if hasattr(result, "prompts"):
        return result.prompts
    if hasattr(result, "resources"):
        return result.resources
    return []


def _permission_for(
    server_config: McpServerConfig,
    kind: McpActionKind,
    action_name: str,
) -> ToolPermission:
    if kind is McpActionKind.TOOL and action_name in server_config.tools:
        return server_config.tools[action_name].to_permission()
    if kind is McpActionKind.PROMPT and action_name in server_config.prompts:
        return server_config.prompts[action_name].to_permission()
    if kind is McpActionKind.RESOURCE and action_name in server_config.resources:
        return server_config.resources[action_name].to_permission()
    if server_config.default_permission is not None:
        return server_config.default_permission.to_permission()
    return DEFAULT_MCP_PERMISSION


def _schema_dict(schema: Any) -> dict[str, Any]:
    if schema is None:
        return {"type": "object", "properties": {}}
    if hasattr(schema, "model_dump"):
        value = schema.model_dump(by_alias=True, exclude_none=True)
    elif isinstance(schema, dict):
        value = schema
    else:
        value = dict(schema)
    if "properties" not in value or value["properties"] is None:
        value = {**value, "properties": {}}
    value.setdefault("type", "object")
    return value


def _format_call_tool_result(result: Any) -> str:
    parts = []
    for content in getattr(result, "content", []) or []:
        text = getattr(content, "text", None)
        if text is not None:
            parts.append(str(text))
        elif hasattr(content, "model_dump"):
            parts.append(json.dumps(content.model_dump(), ensure_ascii=False))
        else:
            parts.append(str(content))
    structured = getattr(result, "structuredContent", None)
    if structured is not None and not parts:
        parts.append(json.dumps(structured, ensure_ascii=False))
    if getattr(result, "isError", False):
        return "[MCP tool error: " + ("\n".join(parts) or "unknown error") + "]"
    return "\n".join(parts)


def _format_prompt_result(
    server_name: str,
    prompt_name: str,
    arguments: dict[str, Any],
    result: Any,
) -> str:
    lines = [
        f"[MCP prompt: {server_name}/{prompt_name}]",
        f"Arguments: {json.dumps(arguments, ensure_ascii=False)}",
        "",
    ]
    for message in getattr(result, "messages", []) or []:
        role = getattr(message, "role", "unknown")
        content = getattr(message, "content", "")
        text = getattr(content, "text", None)
        lines.append(f"{role}: {text if text is not None else content}")
    return "\n".join(lines).rstrip()


def _format_resource_result(server_name: str, uri: str, result: Any) -> str:
    lines = [f"[MCP resource: {server_name} {uri}]", ""]
    for content in getattr(result, "contents", []) or []:
        text = getattr(content, "text", None)
        if text is not None:
            lines.append(str(text))
        elif hasattr(content, "model_dump"):
            lines.append(json.dumps(content.model_dump(), ensure_ascii=False))
        else:
            lines.append(str(content))
    return "\n".join(lines).rstrip()


def _string_arguments(arguments: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in arguments.items()}
