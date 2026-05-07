# agent/tools/builtin/web_fetch.py
import httpx
from agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="WebFetch",
    description="获取网页内容",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "网页URL"},
            "limit": {"type": "integer", "description": "最多返回字符数", "default": 2000},
        },
        "required": ["url"],
    },
)
class WebFetchTool(Tool):
    read_only = True

    async def execute(self, url: str, limit: int = 2000, **kwargs) -> str:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10.0)
                content = response.text[:limit]
                if len(response.text) > limit:
                    content += f"\n...[截断，超出 {len(response.text) - limit} 字符]"
                return content
        except Exception as e:
            return f"Error: {e}"