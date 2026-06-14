Add a benchmark runner adapter that can execute MyAgent itself.

The benchmark harness already supports fake and shell runners. Add a MyAgent
runner that:

- builds a coding-agent prompt from the task issue and validation command,
- creates an `AgentLoop` with coding tools scoped to the task workspace,
- runs the agent without requiring benchmark tests to call a real API,
- reports iterations, tool call count, edit count, status, and output.

Keep the implementation deterministic under unit tests. Tests should be able to
inject a scripted LLM.

