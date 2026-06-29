# Upgrade SubAgentManager to a child-session runtime

The current subagent implementation is still a one-shot background helper built
around `delegate()` and `ParentChannel`. That shape is not enough for the
current agent runtime. A subagent should behave like a child session with its
own transcript and multiple runs, and the parent should manage it through
explicit runtime tools instead of mid-turn message injection.

## Task

Implement a child-session runtime for `agent/subagent/manager.py` and expose it
through narrow built-in tools.

### SubAgentManager (`agent/subagent/manager.py`)
1. Create named child sessions with `subagent_id`, session metadata, and mode
2. Start tasks inside an existing child session and return structured run
   results with `run_id`, `status`, `summary`, `reason`, and usage
3. Allow multiple child sessions to exist concurrently, but reject a second
   active run inside the same session
4. Support `wait`, `get`, `cancel`, and bounded transcript inspection

### AgentLoop / built-in tools
1. Add built-in tools for:
   - `CreateSubagent`
   - `RunSubagent`
   - `ListSubagents`
   - `GetSubagentRun`
   - `CancelSubagentRun`
   - `InspectSubagentTranscript`
2. `AgentLoop` should expose these tools only when explicitly enabled
3. Child subagent loops must not recursively expose the same subagent tools

## Requirements

- Keep child session mode at or below the parent mode
- Use explicit runtime queries/results instead of injecting child results into
  the parent transcript
- `InspectSubagentTranscript` should return a summary or bounded recent
  messages, not the full transcript by default
