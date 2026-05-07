# agent/tools/builtin/read.py
from pathlib import Path
from agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="Read",
    description="读取文件内容",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "limit": {"type": "integer", "description": "最多读取行数", "default": None},
        },
        "required": ["path"],
    },
)
class ReadTool(Tool):
    read_only = True

    async def execute(self, path: str, limit: int = None, **kwargs) -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"Error: 文件不存在: {path}"
            content = p.read_text(errors="replace")
            if limit:
                lines = content.splitlines()
                content = "\n".join(lines[:limit])
            return content
        except PermissionError:
            return f"Error: 无权限读取: {path}"
        except Exception as e:
            return f"Error: {e}"