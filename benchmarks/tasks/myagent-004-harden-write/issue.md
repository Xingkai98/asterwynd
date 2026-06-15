# Harden WriteTool Against Accidental Overwrites

The `WriteTool` currently allows overwriting any file without warning. This is dangerous: if the agent accidentally writes over an existing file with different content, data loss occurs.

## Task

Add overwrite protection to `WriteTool` in `agent/tools/builtin/write.py`:

1. Before writing, check if the target file already exists
2. If the file exists AND the new content is different from the existing content, skip the write
3. Return a warning message indicating the file was NOT overwritten
4. If the file doesn't exist or the content is identical, proceed with the write

## Requirements

- Modify only `agent/tools/builtin/write.py`
- Existing files with different content must be protected
- New files must still be creatable
- The warning message should clearly indicate why the write was skipped
