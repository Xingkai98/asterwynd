# Implement ParentChannel Communication Protocol

The agent needs to support spawning sub-agents (child agents) that can run tasks in the background and report results back to the parent. Before implementing the full sub-agent manager, we need the communication protocol.

## Task

Implement `ParentChannel` in `agent/subagent/protocol.py`:

1. Define a `ParentChannel` ABC with:
   - `send(child_id: str, message: dict)` — send a message to a child
   - `receive() -> dict` — receive the next message from any child
2. Messages are dictionaries with at minimum a `type` field
3. The protocol supports bidirectional communication between parent and child agents

## Requirements

- Create `agent/subagent/protocol.py`
- Use `ABC` for the abstract base class
- Keep the protocol simple — it's a message-passing interface, not a full RPC system
- Tests will verify send/receive behavior with a mock implementation
