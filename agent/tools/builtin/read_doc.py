# agent/tools/builtin/read_doc.py
"""ReadDocTool: on-demand loading of deep Markdown documents.

The root-chain ASTER.md files are injected by ``AsterMdSource`` (P1).  Deep
Markdown documents outside that chain (e.g. ``docs/*.md`` nested docs) are
loaded on demand through this tool, per the Prefix Cache / on-demand MD design
(issue #74).  Reuses the workspace read policy for path-traversal / symlink
safety and caps the document size.
"""
import logging
from typing import TYPE_CHECKING

from agent.tools.base import Tool, tool_parameters
from agent.tool_permissions import WORKSPACE_READ_PERMISSION
from agent.workspace_policy import WorkspacePolicy

if TYPE_CHECKING:
    from agent.message import ContentBlock

logger = logging.getLogger("asterwynd.tools.read_doc")

MAX_DOC_SIZE_BYTES = 32 * 1024  # 与 MAX_ASTER_SIZE_BYTES 对齐

_TRUNCATION_NOTE = (
    "\n\n[文档已截断，超过 {limit_kb}KB 上限；如需分页续读请使用 Read 工具并指定 offset]"
)


@tool_parameters(
    name="ReadDoc",
    description=(
        "按需读取深层 Markdown 文档（例如 docs/ 下的嵌套文档）。"
        "项目根链 ASTER.md 已自动注入系统上下文，此工具用于读取未被注入的深层 MD 内容。"
        "仅支持 .md 文件，单文档上限 32KB。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "相对工作区的 Markdown 文档路径"},
        },
        "required": ["path"],
    },
)
class ReadDocTool(Tool):
    read_only = True
    parallelizable = True
    permission = WORKSPACE_READ_PERMISSION

    def __init__(self, policy: WorkspacePolicy | None = None):
        self.policy = policy or WorkspacePolicy()

    async def execute(self, path: str, **kwargs) -> str | list["ContentBlock"]:
        try:
            p = self.policy.assert_read_allowed(path)
        except PermissionError as e:
            return f"Error: {e}"
        if not p.exists():
            return f"Error: 文档不存在: {path}"
        if p.suffix.lower() != ".md":
            return f"Error: 只支持 Markdown 文档 (.md): {path}"

        try:
            size = p.stat().st_size
        except OSError as e:
            return f"Error: 无法读取文档信息 {path}: {e}"

        limit_kb = MAX_DOC_SIZE_BYTES // 1024
        if size > MAX_DOC_SIZE_BYTES:
            logger.warning(
                "ReadDoc %s is %d bytes (limit %d) — truncating",
                path, size, MAX_DOC_SIZE_BYTES,
            )

        try:
            content = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error: 读取失败 {path}: {e}"

        if size > MAX_DOC_SIZE_BYTES:
            # 按字节截断（CJK 多字节字符不会突破字节上限）
            data = content.encode("utf-8")[:MAX_DOC_SIZE_BYTES]
            content = data.decode("utf-8", errors="replace")
            content += _TRUNCATION_NOTE.format(limit_kb=limit_kb)
        return content
