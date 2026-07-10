# Fix AgentLoop Multi-Turn Repeater Bug

The agent has a critical bug in multi-turn conversations: after completing a turn with tool calls (e.g., editing a file), the next turn's agent cannot see its own prior response. It only sees tool calls and tool results, causing it to repeat similar edits — the "repeater" behavior.

## Root Cause

`AgentLoop.run()` returns without appending the assistant's final response to `messages`. The next turn starts with an incomplete message history.

## Secondary Issue

`MemoryManager.compact_if_needed()` operates on its own internal `self.messages` list, but `AgentLoop` uses a separate messages list. Compaction is never triggered because no code calls `memory.add()`.

## Task

1. Fix `agent/loop.py`: append the final assistant message (with reasoning_content if present) to messages before returning
2. Fix `agent/memory/manager.py`: make `compact_if_needed()` accept an external messages list parameter, so the agent loop's messages can be passed in for compaction
3. Ensure the fix works for both normal text responses and tool-call responses

## Requirements

- The agent must see its full conversation history across turns
- Memory compaction must actually trigger when token limits are exceeded
- All existing tests must continue to pass
