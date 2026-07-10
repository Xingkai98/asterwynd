import asyncio
import sys

from mcp.server.fastmcp import FastMCP


port = int(sys.argv[1])
mcp = FastMCP("fixture-http-mcp", host="127.0.0.1", port=port)


@mcp.tool(description="Echo text")
def echo(text: str) -> str:
    return text


@mcp.prompt(description="Summarize text")
def summarize(topic: str) -> str:
    return f"Summarize {topic}."


@mcp.resource("docs://http/resource", description="HTTP MCP resource")
def http_resource() -> str:
    return "HTTP MCP resource content."


if __name__ == "__main__":
    asyncio.run(mcp.run_streamable_http_async())
