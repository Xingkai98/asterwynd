# Fix the Calculator Module Using LSP Diagnostics

A new module `agent/example/calculator.py` was recently added but contains a bug. The function `calculate_total` produces incorrect results when given a list with negative numbers. There is also a type-related defect that the LSP server should flag.

## Task

1. First, use the `LspDiagnostics` tool on `agent/example/calculator.py` to discover what the LSP server reports
2. Review the diagnostics and understand the error
3. Fix the error so that all tests pass

## Requirements

- Use the LSP diagnostics tool to find the issue before making changes
- Fix the code in `agent/example/calculator.py`
- Run the failing test to confirm your fix works
