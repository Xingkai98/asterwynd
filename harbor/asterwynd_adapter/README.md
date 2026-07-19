# Asterwynd Harbor Adapter

Harbor agent adapter for [Asterwynd](https://github.com/Xingkai98/asterwynd) coding agent.

## Quick Start

1. Build Asterwynd wheel:
   ```bash
   cd asterwynd/
   uv build
   ```

2. Build Docker image (wheel must be in `dist/`):
   ```bash
   docker build -t asterwynd-harbor -f harbor/asterwynd_adapter/environment/Dockerfile .
   ```

3. Run with Harbor:
   ```bash
   harbor run \
     --agent-import-path harbor.asterwynd_adapter.adapter:AsterwyndAgent \
     --task-dir <harbor-task-directory>
   ```

## How It Works

- `install()`: pip installs the pre-built Asterwynd wheel into the container
- `run()`: calls `asterwynd run --auto-approve --output-dir /logs/agent <instruction>`
- `populate_context_post_run()`: parses trace.json and populates ATIF metadata

`--auto-approve` uses the `build_legacy_auto_high_risk` permission profile, which
auto-approves all built-in tools (risk ≤ HIGH) without requiring user interaction.
