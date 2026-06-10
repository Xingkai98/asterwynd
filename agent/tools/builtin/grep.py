# agent/tools/builtin/grep.py
import re
from pathlib import Path
from agent.tools.base import Tool, tool_parameters

@tool_parameters(
    name="Grep",
    description="在文件中搜索匹配的文本行",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "正则表达式模式"},
            "path": {"type": "string", "description": "文件或目录路径"},
            "recursive": {"type": "boolean", "description": "递归搜索目录", "default": False},
        },
        "required": ["pattern", "path"],
    },
)
class GrepTool(Tool):
    read_only = True

    async def execute(self, pattern: str, path: str, recursive: bool = False, **kwargs) -> str:
        try:
            regex = re.compile(pattern)
            p = Path(path)
            if not p.exists():
                return f"Error: 路径不存在: {path}"
            files = [p] if p.is_file() else (list(p.rglob("*")) if recursive else list(p.glob("*")))
            files = [f for f in files if f.is_file()]
            results = []
            for f in files:
                try:
                    for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                        if regex.search(line):
                            results.append(f"{f}:{i}: {line.rstrip()}")
                except Exception:
                    pass
            if not results:
                return "未找到匹配"
            output = "\n".join(results[:50])
            if len(results) > 50:
                output += f"\n...[还有 {len(results) - 50} 条匹配]"
            return output
        except Exception as e:
            return f"Error: {e}"
