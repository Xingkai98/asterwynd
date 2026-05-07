# agent/tools/builtin/web_search.py
import httpx
from agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="WebSearch",
    description="搜索网页",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 5},
        },
        "required": ["query"],
    },
)
class WebSearchTool(Tool):
    read_only = True

    async def execute(self, query: str, limit: int = 5, **kwargs) -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    timeout=10.0,
                )
                lines = [l.strip() for l in response.text.splitlines() if query.lower() in l.lower()][:limit]
                if not lines:
                    return "未找到结果"
                return "\n".join(lines[:limit])
        except Exception as e:
            return f"Error: {e}"