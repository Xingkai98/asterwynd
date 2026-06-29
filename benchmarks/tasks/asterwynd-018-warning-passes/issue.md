# Distinguish Benchmark Warning Passes

The benchmark runner currently only reports "passed" or "failed". When a task's tests produce warnings (e.g., deprecation warnings) but still pass, the runner should distinguish this as a separate status for more nuanced evaluation.

## Task

Update the benchmark system to support warning-level passes:

1. In `benchmarks/models.py`: add a mechanism to detect warnings in test output
2. In `benchmarks/runner.py`: after running the test command, check if the output contains Python warnings (e.g., `DeprecationWarning`, `UserWarning`)
3. If tests pass (exit code 0) but the output contains warnings, mark the task as `passed_with_warnings`
4. In `cli.py`: display a distinct icon for warning passes in the summary output

## Requirements

- Warning detection must not break normal pass/fail logic
- The status value `passed_with_warnings` must be stable and documented
- The CLI must visually distinguish passed vs passed_with_warnings
