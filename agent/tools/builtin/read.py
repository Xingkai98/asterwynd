# agent/tools/builtin/read.py
from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy

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
    permission = WORKSPACE_READ_PERMISSION

    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(self, path: str, limit: int = None, **kwargs) -> str:
        try:
            p = self.policy.assert_read_allowed(path)
            if not p.exists():
                return f"Error: 文件不存在: {path}"
            content = p.read_text(errors="replace")
            if limit:
                lines = content.splitlines()
                content = "\n".join(lines[:limit])
            return content
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
