from pathlib import Path
import asyncio
import socket

import pytest

from agent.config import load_config
from agent.config import McpServerConfig
from agent.mcp import McpManager, build_mcp_manager
from agent.run_config import AgentMode, AgentRunConfig, ModePolicy
from agent.tool_permissions import ToolCapability, ToolRiskLevel
from agent.tools.base import ToolCall
from agent.tools.factory import build_default_tool_registry


FIXTURE_SERVER = Path(__file__).parents[2] / "fixtures" / "mcp_stdio_server.py"
HTTP_FIXTURE_SERVER = Path(__file__).parents[2] / "fixtures" / "mcp_http_server.py"


@pytest.mark.asyncio
async def test_stdio_mcp_discovers_tools_prompts_and_resources(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        f"""
mcp:
  servers:
    fixture:
      type: stdio
      command: uv
      args: ["run", "python", "{FIXTURE_SERVER}"]
      default_permission:
        capabilities: ["network_read"]
        risk_level: low
""",
        encoding="utf-8",
    )
    config = load_config(start_dir=tmp_path)

    manager = await build_mcp_manager(config)
    try:
        statuses = manager.status()
        assert statuses[0].ready is True
        assert statuses[0].tools == 1
        assert statuses[0].prompts == 1
        assert statuses[0].resources == 1
        assert manager.tools[0].callable_name == "mcp__fixture__add"
        assert manager.prompts[0].prompt_name == "review_pr"
        assert manager.resources[0].uri == "docs://architecture/agent-loop"
    finally:
        await manager.aclose()


@pytest.mark.asyncio
async def test_mcp_tool_registers_and_executes_through_tool_registry(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        f"""
mcp:
  servers:
    fixture:
      type: stdio
      command: uv
      args: ["run", "python", "{FIXTURE_SERVER}"]
      default_permission:
        capabilities: ["network_read"]
        risk_level: low
""",
        encoding="utf-8",
    )
    config = load_config(start_dir=tmp_path)
    manager = await build_mcp_manager(config)
    try:
        registry = build_default_tool_registry(
            mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.READ_ONLY)),
            mcp_manager=manager,
        )

        schemas = registry.get_all_schemas()
        assert "mcp__fixture__add" in {
            schema["function"]["name"] for schema in schemas
        }
        result = await registry.execute(
            ToolCall(id="call-1", name="mcp__fixture__add", arguments={"a": 2, "b": 3})
        )

        assert result == "5"
    finally:
        await manager.aclose()


@pytest.mark.asyncio
async def test_mcp_prompt_and_resource_read_results_are_source_marked(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        f"""
mcp:
  servers:
    fixture:
      type: stdio
      command: uv
      args: ["run", "python", "{FIXTURE_SERVER}"]
      default_permission:
        capabilities: ["network_read"]
        risk_level: low
""",
        encoding="utf-8",
    )
    config = load_config(start_dir=tmp_path)
    manager = await build_mcp_manager(config)
    try:
        prompt = await manager.get_prompt(
            "fixture",
            "review_pr",
            {"repo": "asterwynd", "pr": 42},
        )
        resource = await manager.read_resource(
            "fixture",
            "docs://architecture/agent-loop",
        )

        assert "[MCP prompt: fixture/review_pr]" in prompt
        assert "Review PR 42 in asterwynd." in prompt
        assert "[MCP resource: fixture docs://architecture/agent-loop]" in resource
        assert "AgentLoop owns message state" in resource
    finally:
        await manager.aclose()


@pytest.mark.asyncio
async def test_high_risk_mcp_tool_requires_approval_before_remote_call(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        f"""
mcp:
  servers:
    fixture:
      type: stdio
      command: uv
      args: ["run", "python", "{FIXTURE_SERVER}"]
""",
        encoding="utf-8",
    )
    config = load_config(start_dir=tmp_path)
    manager = await build_mcp_manager(config)
    try:
        registry = build_default_tool_registry(
            mode_policy=ModePolicy(AgentRunConfig(mode=AgentMode.BUILD)),
            mcp_manager=manager,
        )

        result = await registry.execute(
            ToolCall(id="call-1", name="mcp__fixture__add", arguments={"a": 2, "b": 3})
        )

        assert result == "[Approval required: tool mcp__fixture__add requires approval in build mode]"
    finally:
        await manager.aclose()


def test_mcp_config_parses_permissions_and_rejects_tools_mcp(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        """
mcp:
  default_timeout_seconds: 12
  servers:
    docs:
      type: streamable_http
      url: "http://127.0.0.1:8765/mcp"
      headers:
        Authorization:
          env: DOCS_TOKEN
      default_permission:
        capabilities: ["network_read"]
        risk_level: low
      tools:
        create_page:
          capabilities: ["external_side_effect"]
          risk_level: high
""",
        encoding="utf-8",
    )

    config = load_config(start_dir=tmp_path)

    server = config.mcp.servers["docs"]
    assert server.type == "streamable_http"
    assert server.url == "http://127.0.0.1:8765/mcp"
    assert server.headers["Authorization"].env == "DOCS_TOKEN"
    assert server.default_permission is not None
    assert server.default_permission.capabilities == (ToolCapability.NETWORK_READ,)
    assert server.default_permission.risk_level is ToolRiskLevel.LOW
    assert server.tools["create_page"].risk_level is ToolRiskLevel.HIGH


@pytest.mark.asyncio
async def test_mcp_tool_timeout_returns_readable_error():
    class SlowSession:
        async def call_tool(self, name, arguments):
            await asyncio.sleep(1)

    manager = McpManager()
    manager._sessions["slow"] = SlowSession()
    manager._server_configs["slow"] = McpServerConfig(
        name="slow",
        type="stdio",
        command="unused",
        tool_timeout_seconds=1,
    )

    result = await manager.call_tool("slow", "wait", {})

    assert result.startswith("[MCP tool error: slow/wait: TimeoutError:")


@pytest.mark.asyncio
async def test_streamable_http_mcp_discovers_and_calls_tool(tmp_path):
    port = _free_port()
    process = await asyncio.create_subprocess_exec(
        "uv",
        "run",
        "python",
        str(HTTP_FIXTURE_SERVER),
        str(port),
    )
    try:
        await _wait_for_port(port)
        (tmp_path / "asterwynd.yaml").write_text(
            f"""
mcp:
  servers:
    http_fixture:
      type: streamable_http
      url: "http://127.0.0.1:{port}/mcp"
      default_permission:
        capabilities: ["network_read"]
        risk_level: low
""",
            encoding="utf-8",
        )
        config = load_config(start_dir=tmp_path)
        manager = await build_mcp_manager(config)
        try:
            assert manager.status()[0].ready is True
            assert manager.tools[0].callable_name == "mcp__http_fixture__echo"
            result = await manager.call_tool(
                "http_fixture",
                "echo",
                {"text": "hello"},
            )
            assert result == "hello"
        finally:
            await manager.aclose()
    finally:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


def test_tools_mcp_config_is_rejected(tmp_path):
    (tmp_path / "asterwynd.yaml").write_text(
        """
tools:
  mcp:
    servers: {}
""",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="top-level mcp.servers"):
        load_config(start_dir=tmp_path)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_for_port(port: int) -> None:
    deadline = asyncio.get_running_loop().time() + 10
    while True:
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()
            return
        except OSError:
            if asyncio.get_running_loop().time() > deadline:
                raise
            await asyncio.sleep(0.1)
