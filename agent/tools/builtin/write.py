# agent/tools/builtin/write.py
from pathlib import Path
from agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="Write",
    description="写入内容到文件",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "写入内容"},
        },
        "required": ["path", "content"],
    },
)
class WriteTool(Tool):
    read_only = False

    async def execute(self, path: str, content: str, **kwargs) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, errors="replace")
            return f"已写入 {len(content)} 字符到 {path}"
        except PermissionError:
            return f"Error: 无权限写入: {path}"
        except Exception as e:
            return f"Error: {e}"