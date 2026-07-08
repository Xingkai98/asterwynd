import asyncio

from mcp.server.fastmcp import FastMCP


mcp = FastMCP("fixture-mcp")


@mcp.tool(description="Add two numbers")
def add(a: int, b: int) -> str:
    return str(a + b)


@mcp.prompt(description="Review a pull request")
def review_pr(repo: str, pr: str) -> str:
    return f"Review PR {pr} in {repo}."


@mcp.resource("docs://architecture/agent-loop", description="Agent loop docs")
def agent_loop_docs() -> str:
    return "AgentLoop owns message state and tool execution."


if __name__ == "__main__":
    asyncio.run(mcp.run_stdio_async())
