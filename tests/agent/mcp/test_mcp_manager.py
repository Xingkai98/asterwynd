from pathlib import Path
import asyncio
import socket

import pytest

from agent.config import load_config
from agent.config import McpServerConfig
from agent.mcp import McpManager, build_mcp_manager
from agent.mcp.types import McpCallError
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

        assert result.text == "5"
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

        assert result.text == "[Approval required: tool mcp__fixture__add requires approval in build mode]"
        assert result.error_type == "approval_required"
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

    with pytest.raises(McpCallError) as exc_info:
        await manager.call_tool("slow", "wait", {})

    assert exc_info.value.text.startswith("[MCP tool error: slow/wait: TimeoutError:")
    assert exc_info.value.error_type == "timeout"


@pytest.mark.asyncio
async def test_mcp_call_error_raises_typed_error_on_generic_exception():
    """异常路径：非超时/非连接异常抛 McpCallError(error_type='mcp_error')，
    __str__ 返回 user-facing text（grill R4）。"""
    class FailingSession:
        async def call_tool(self, name, arguments):
            raise RuntimeError("boom")

    manager = McpManager()
    manager._sessions["srv"] = FailingSession()
    manager._server_configs["srv"] = McpServerConfig(
        name="srv", type="stdio", command="unused", tool_timeout_seconds=5,
    )

    with pytest.raises(McpCallError) as exc_info:
        await manager.call_tool("srv", "t", {})
    assert exc_info.value.error_type == "mcp_error"
    assert "boom" in str(exc_info.value)
    assert str(exc_info.value) == exc_info.value.text


@pytest.mark.asyncio
async def test_mcp_call_error_connection_error_maps_to_network_error():
    """连接类异常映射 network_error（可被 RetryHook 识别）。"""
    class ConnFailingSession:
        async def call_tool(self, name, arguments):
            raise ConnectionError("connection refused")

    manager = McpManager()
    manager._sessions["srv"] = ConnFailingSession()
    manager._server_configs["srv"] = McpServerConfig(
        name="srv", type="stdio", command="unused", tool_timeout_seconds=5,
    )

    with pytest.raises(McpCallError) as exc_info:
        await manager.call_tool("srv", "t", {})
    assert exc_info.value.error_type == "network_error"


@pytest.mark.asyncio
async def test_mcp_iserror_result_maps_to_mcp_error_tool_result():
    """isError 结果：协议层返回 success 但 isError=true → ToolResult(mcp_error)。"""
    class ErrorResult:
        isError = True
        content = [type("C", (), {"text": "server error"})()]
        structuredContent = None

    class ErrSession:
        async def call_tool(self, name, arguments):
            return ErrorResult()

    from agent.tools.base import ToolResult

    manager = McpManager()
    manager._sessions["srv"] = ErrSession()
    manager._server_configs["srv"] = McpServerConfig(
        name="srv", type="stdio", command="unused", tool_timeout_seconds=5,
    )

    result = await manager.call_tool("srv", "t", {})
    assert isinstance(result, ToolResult)
    assert result.error_type == "mcp_error"
    assert "server error" in result.text

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
