Add a CLI entry point for running local benchmark tasks.

Users should be able to run benchmark tasks from the command line without
writing Python code. Add a `benchmark` command to the Typer CLI that supports:

- selecting `fake`, `shell`, or `asterwynd` runner,
- passing `--source-repo` and `--runs-dir`,
- passing fake-runner edit parameters for deterministic smoke tests,
- printing the run directory and pass/fail summary.

The command must not require real API keys when `--agent fake` is used.

