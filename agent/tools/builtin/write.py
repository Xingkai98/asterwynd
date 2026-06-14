# agent/tools/builtin/write.py
from pathlib import Path
from agent.tools.base import Tool, tool_parameters
from agent.workspace_policy import WorkspacePolicy

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

    def __init__(self, policy: WorkspacePolicy | None = None):
        # Keep direct WriteTool() backwards-compatible for existing tests and
        # callers. Agent tool sets inject a workspace-rooted policy explicitly.
        self.policy = policy or WorkspacePolicy(Path("/"))

    async def execute(self, path: str, content: str, **kwargs) -> str:
        try:
            p = self.policy.assert_write_allowed(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, errors="replace")
            return f"已写入 {len(content)} 字符到 {path}"
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error: {e}"
