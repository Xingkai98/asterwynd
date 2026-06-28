# Implement ReadTool and WriteTool

The agent framework has a `Tool` ABC and `SandboxExecutor`, but no built-in tools for reading and writing files. The agent needs these fundamental I/O tools to interact with the workspace.

## Task

Implement two built-in tools:

### ReadTool (`agent/tools/builtin/read.py`)
1. Subclass `Tool` with `read_only = True`
2. Accept a `path` parameter (file path to read)
3. Accept optional `offset` and `limit` parameters for partial reads
4. Return the file contents as a string

### WriteTool (`agent/tools/builtin/write.py`)
1. Subclass `Tool` with `read_only = False`
2. Accept `path` and `content` parameters
3. Write content to the specified file
4. Return a success confirmation

## Requirements

- Both tools must use the `@tool_parameters` decorator
- Both tools must handle file I/O errors gracefully
- Follow the existing tool pattern in the codebase
